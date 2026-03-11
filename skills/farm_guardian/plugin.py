"""
FarmGuardian skill implementation.

Handles farm observation records: animals, weather, protocols, journals.
Score is based on keyword matching against a predefined trigger set.
Returns an ActionPlan with a write_markdown action — no side effects here.
"""

from __future__ import annotations

import re

from core.models import (
    Action,
    ActionPlan,
    ActionType,
    IncomingEvent,
    SkillContext,
    SkillResult,
    SkillStatus,
)
from skills.base import BaseSkill
from skills.farm_guardian.manifest import (
    JOURNAL_PATH,
    SKILL_DESCRIPTION,
    SKILL_EXAMPLES,
    SKILL_NAME,
    SKILL_VERSION,
    TRIGGER_KEYWORDS,
)


def _tokenize(text: str) -> set[str]:
    """Lowercase and split text into word tokens."""
    return set(re.findall(r"[а-яёa-z]+", text.lower()))


class FarmGuardianSkill(BaseSkill):
    """Records farm observations to a journal log file."""

    name = SKILL_NAME
    version = SKILL_VERSION
    description = SKILL_DESCRIPTION
    examples = SKILL_EXAMPLES

    def score(self, event: IncomingEvent) -> float:
        """Return score based on fraction of trigger keywords found in text."""
        tokens = _tokenize(event.text)
        hits = tokens & TRIGGER_KEYWORDS
        if not hits:
            return 0.0
        # Score scales with number of hits, capped at 1.0
        raw = len(hits) / max(len(TRIGGER_KEYWORDS) * 0.15, 1)
        return min(round(raw, 4), 1.0)

    def handle(self, ctx: SkillContext) -> SkillResult:
        """Build an ActionPlan to append the user's text to the journal."""
        event = ctx.event
        preview = (
            f"[FarmGuardian] Запись в журнал:\n"
            f"  Файл: {JOURNAL_PATH}\n"
            f"  Текст: {event.text}"
        )
        plan = ActionPlan(
            skill_name=self.name,
            event_id=event.event_id,
            actions=[
                Action(
                    action_type=ActionType.write_markdown,
                    params={
                        "path": JOURNAL_PATH,
                        "content": event.text,
                    },
                )
            ],
            preview_text=preview,
            requires_confirmation=True,
        )
        return SkillResult(status=SkillStatus.plan_ready, plan=plan)
