"""
Limiter skill v1.0 — production day planner and SKU overload limiter.

Handles:
  - CreateOrderIntent  → plan_ready | clarification_required
  - SummaryIntent      → informational
  - DaysLoadIntent     → informational
  - ExportIntent       → rejected (not implemented in v1.0)
  - OverlimitResolutionIntent → plan_ready (after user chose resolution)

Philosophy:
  - Skill only reads domain state and returns SkillResult.
  - All file writes go through executor via ActionPlan.
  - Overload is allowed but flagged — human decides.
"""

from __future__ import annotations

import re
import logging

from core.models import (
    IncomingEvent,
    SkillContext,
    SkillResult,
    SkillStatus,
)
from skills.base import BaseSkill
from skills.limiter import repository
from skills.limiter import capacity_engine
from skills.limiter import planner
from skills.limiter import preview as preview_mod
from skills.limiter.domain import OverlimitMode, OverlimitResolution
from skills.limiter.examples import EXAMPLES
from skills.limiter.intents import (
    CreateOrderIntent,
    DaysLoadIntent,
    ExportIntent,
    OverlimitResolutionIntent,
    SummaryIntent,
)
from skills.limiter.manifest import (
    SKILL_DESCRIPTION,
    SKILL_NAME,
    SKILL_VERSION,
    TRIGGER_KEYWORDS,
)
from skills.limiter.parser import parse
from skills.limiter.validator import validate_draft

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Overlimit resolution parser (for the second-turn response)
# ---------------------------------------------------------------------------

_RE_FORCE = re.compile(r"^force[_\s]?negative$", re.IGNORECASE)
_RE_FREE = re.compile(r"^accept[_\s]?free[_\s]?only$", re.IGNORECASE)
_RE_MOVE = re.compile(r"^move[_\s]?date\s+(\S+)$", re.IGNORECASE)
_RE_CANCEL = re.compile(r"^cancel$", re.IGNORECASE)

# In-memory pending overlimit state: event_id → OrderDraft
# This is intentionally simple runtime state (not persisted).
# In a multi-user system this would need a proper store.
_pending_overlimit: dict[str, object] = {}  # event_id → OrderDraft


def _parse_resolution(text: str) -> OverlimitResolution | None:
    """Try to parse a resolution choice from user text."""
    t = text.strip()
    if _RE_FORCE.match(t):
        return OverlimitResolution(mode=OverlimitMode.force_negative)
    if _RE_FREE.match(t):
        return OverlimitResolution(mode=OverlimitMode.accept_free_only)
    m = _RE_MOVE.match(t)
    if m:
        from skills.limiter.parser import _parse_date
        d = _parse_date(m.group(1))
        if d:
            return OverlimitResolution(mode=OverlimitMode.move_date, new_date=d)
    if _RE_CANCEL.match(t):
        return OverlimitResolution(mode=OverlimitMode.cancel)
    return None


# ---------------------------------------------------------------------------
# Score helper
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Tokenize text, splitting on whitespace AND underscores for keyword matching."""
    raw = re.findall(r"[а-яёa-z0-9_]+", text.lower())
    tokens: set[str] = set()
    for tok in raw:
        tokens.add(tok)
        # Also add sub-tokens split by underscore (e.g. milk_1_5 → milk, 1, 5)
        tokens.update(tok.split("_"))
    return tokens


# ---------------------------------------------------------------------------
# LimiterSkill
# ---------------------------------------------------------------------------


class LimiterSkill(BaseSkill):
    """Production day planner and SKU overload limiter."""

    name = SKILL_NAME
    version = SKILL_VERSION
    description = SKILL_DESCRIPTION
    examples = EXAMPLES

    def score(self, event: IncomingEvent) -> float:
        """Score based on keyword hits + command prefix detection."""
        text = event.text.strip()

        # Hard-match command prefixes
        lower = text.lower()
        if any(lower.startswith(p) for p in ("/summary", "/days", "/export", "summary ", "days", "export ", "сводка", "загрузка по датам")):
            return 0.95

        # Check for pending overlimit resolution
        if _pending_overlimit and _parse_resolution(text) is not None:
            return 0.95

        # Keyword scoring
        tokens = _tokenize(text)
        hits = tokens & TRIGGER_KEYWORDS
        if not hits:
            return 0.0
        raw = len(hits) / max(len(TRIGGER_KEYWORDS) * 0.12, 1)
        return min(round(raw, 4), 1.0)

    def handle(self, ctx: SkillContext) -> SkillResult:
        """Route to the appropriate handler based on parsed intent."""
        text = ctx.event.text.strip()
        event_id = ctx.event.event_id

        # --- Check for pending overlimit resolution first ---
        if _pending_overlimit:
            resolution = _parse_resolution(text)
            if resolution is not None:
                # Find the most recent pending draft (simple: take first)
                pending_event_id, draft = next(iter(_pending_overlimit.items()))
                _pending_overlimit.pop(pending_event_id, None)
                intent = OverlimitResolutionIntent(draft=draft, resolution=resolution)
                return self._handle_overlimit_resolution(event_id, intent)

        # --- Parse intent (with alias index for Russian text support) ---
        alias_index = repository.build_alias_index()
        intent = parse(text, alias_index=alias_index)

        if intent is None:
            return SkillResult(
                status=SkillStatus.clarification_needed,
                clarification_message=(
                    "Не удалось распознать команду limiter.\n\n"
                    "Примеры заказов на русском:\n"
                    "  26 марта фермерского 2 шт, брынза 2 шт\n"
                    "  на 26 марта 2 упаковки творога и йогурт с клубникой 2 шт\n"
                    "  26.03 молока 3 шт, масла 1 шт\n\n"
                    "Примеры через SKU:\n"
                    "  2026-03-15 milk_1_5 12\n\n"
                    "Команды:\n"
                    "  /summary 2026-03-15\n"
                    "  /days"
                ),
            )

        if isinstance(intent, SummaryIntent):
            return self._handle_summary(intent)

        if isinstance(intent, DaysLoadIntent):
            return self._handle_days_load(intent)

        if isinstance(intent, ExportIntent):
            return self._handle_export(intent)

        if isinstance(intent, CreateOrderIntent):
            return self._handle_create_order(event_id, intent)

        # Fallback
        return SkillResult(
            status=SkillStatus.error,
            error_message=f"Неизвестный тип интента: {type(intent).__name__}",
        )

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _handle_summary(self, intent: SummaryIntent) -> SkillResult:
        text = planner.build_summary_response(intent.delivery_date)
        return SkillResult(
            status=SkillStatus.informational,
            clarification_message=text,
        )

    def _handle_days_load(self, intent: DaysLoadIntent) -> SkillResult:
        text = planner.build_days_load_response(intent.days_ahead)
        return SkillResult(
            status=SkillStatus.informational,
            clarification_message=text,
        )

    def _handle_export(self, intent: ExportIntent) -> SkillResult:
        event_id = intent.delivery_date.isoformat()  # stable id for export plans
        action_plan = planner.build_export_plan(
            event_id=event_id,
            delivery_date=intent.delivery_date,
        )
        return SkillResult(
            status=SkillStatus.plan_ready,
            plan=action_plan,
        )

    def _handle_create_order(
        self, event_id: str, intent: CreateOrderIntent
    ) -> SkillResult:
        draft = intent.draft
        products = repository.products_by_sku()

        # 1. Validate
        errors = validate_draft(draft, products)
        if errors:
            return SkillResult(
                status=SkillStatus.clarification_needed,
                clarification_message="Ошибки в заказе:\n" + "\n".join(f"  • {e}" for e in errors),
            )

        # 2. Ensure production day
        day, day_was_created = repository.ensure_production_day(draft.delivery_date)
        day_data = repository.production_day_data(day) if day_was_created else None
        day_path = repository.production_day_path(draft.delivery_date) if day_was_created else None

        # 3. Check capacity
        check_result = capacity_engine.check_order(draft, day, products)

        # 4. All within limits → normal plan
        if check_result.status.value == "ok":
            preview_text = preview_mod.format_normal_order_preview(
                draft, check_result, day_was_created=day_was_created
            )
            action_plan = planner.build_normal_order_plan(
                event_id=event_id,
                draft=draft,
                check_result=check_result,
                products=products,
                day_was_created=day_was_created,
                day_data=day_data,
                day_path=day_path,
                preview_text=preview_text,
            )
            return SkillResult(
                status=SkillStatus.plan_ready,
                plan=action_plan,
            )

        # 5. Over limit → clarification required
        # Store draft in pending state so next message can resolve it
        _pending_overlimit[event_id] = draft

        clarification = preview_mod.format_overlimit_clarification(draft, check_result)
        return SkillResult(
            status=SkillStatus.clarification_required,
            clarification_message=clarification,
        )

    def _handle_overlimit_resolution(
        self, event_id: str, intent: OverlimitResolutionIntent
    ) -> SkillResult:
        draft = intent.draft
        resolution = intent.resolution
        products = repository.products_by_sku()

        # cancel → nothing to do
        if resolution.mode == OverlimitMode.cancel:
            return SkillResult(
                status=SkillStatus.informational,
                clarification_message="Заказ отменён. Ничего не сохранено.",
            )

        # move_date → ask user to re-submit with new date
        if resolution.mode == OverlimitMode.move_date:
            new_date = resolution.new_date
            if new_date:
                return SkillResult(
                    status=SkillStatus.informational,
                    clarification_message=(
                        f"Хорошо, выбрана новая дата: {new_date.isoformat()}.\n"
                        f"Отправьте заказ заново с этой датой.\n"
                        f"Пример: {new_date.isoformat()} <sku> <количество>"
                    ),
                )
            return SkillResult(
                status=SkillStatus.clarification_needed,
                clarification_message=(
                    "Чтобы перенести заказ, укажите новую дату в формате:\n"
                    "  move_date ГГГГ-ММ-ДД\n"
                    "\n"
                    "Пример:\n"
                    "  move_date 2026-03-20"
                ),
            )

        # Re-check capacity for the plan builders
        day, day_was_created = repository.ensure_production_day(draft.delivery_date)
        day_data = repository.production_day_data(day) if day_was_created else None
        day_path = repository.production_day_path(draft.delivery_date) if day_was_created else None
        check_result = capacity_engine.check_order(draft, day, products)

        if resolution.mode == OverlimitMode.force_negative:
            preview_text = preview_mod.format_force_negative_preview(
                draft, check_result, day_was_created=day_was_created
            )
            action_plan = planner.build_force_negative_plan(
                event_id=event_id,
                draft=draft,
                check_result=check_result,
                products=products,
                day_was_created=day_was_created,
                day_data=day_data,
                day_path=day_path,
                preview_text=preview_text,
            )
            return SkillResult(status=SkillStatus.plan_ready, plan=action_plan)

        if resolution.mode == OverlimitMode.accept_free_only:
            preview_text = preview_mod.format_accept_free_only_preview(
                draft, check_result, day_was_created=day_was_created
            )
            action_plan = planner.build_accept_free_only_plan(
                event_id=event_id,
                draft=draft,
                check_result=check_result,
                products=products,
                day_was_created=day_was_created,
                day_data=day_data,
                day_path=day_path,
                preview_text=preview_text,
            )
            return SkillResult(status=SkillStatus.plan_ready, plan=action_plan)

        return SkillResult(
            status=SkillStatus.error,
            error_message=f"Неизвестный режим разрешения: {resolution.mode}",
        )
