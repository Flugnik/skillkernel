"""
ConfirmManager — stores pending ActionPlans awaiting user confirmation.

Plans are persisted to a JSON file so they survive process restarts
(within their TTL window).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from core.exceptions import PlanExpiredError, PlanNotFoundError
from core.models import ActionPlan

logger = logging.getLogger(__name__)


class ConfirmManager:
    """Manages pending plans that require explicit user confirmation.

    Storage format: a JSON object mapping plan_id → serialised ActionPlan dict.
    """

    def __init__(self, store_path: str = "memory/runtime/pending_plans.json") -> None:
        self._store_path = Path(store_path)
        self._store_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_plan(self, plan: ActionPlan) -> None:
        """Persist a plan as pending confirmation."""
        store = self._load()
        store[plan.plan_id] = plan.model_dump(mode="json")
        self._save(store)
        logger.info("Stored pending plan plan_id=%s skill=%s", plan.plan_id, plan.skill_name)

    def get_plan(self, plan_id: str) -> ActionPlan:
        """Retrieve a pending plan by ID.

        Raises:
            PlanNotFoundError: plan_id not in store.
            PlanExpiredError: plan TTL has elapsed.
        """
        store = self._load()
        if plan_id not in store:
            raise PlanNotFoundError(plan_id)

        raw = store[plan_id]
        plan = ActionPlan.model_validate(raw)
        self._assert_not_expired(plan)
        return plan

    def confirm(self, plan_id: str) -> ActionPlan:
        """Confirm a plan: validate, remove from store, return it for execution."""
        plan = self.get_plan(plan_id)
        self._remove(plan_id)
        logger.info("Confirmed plan plan_id=%s", plan_id)
        return plan

    def reject(self, plan_id: str) -> None:
        """Reject and discard a pending plan."""
        store = self._load()
        if plan_id not in store:
            raise PlanNotFoundError(plan_id)
        self._remove(plan_id)
        logger.info("Rejected plan plan_id=%s", plan_id)

    def cleanup_expired(self) -> int:
        """Remove all expired plans from the store.

        Returns:
            Number of plans removed.
        """
        store = self._load()
        now = datetime.now(tz=timezone.utc)
        expired = []
        for pid, raw in store.items():
            plan = ActionPlan.model_validate(raw)
            created = plan.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age = (now - created).total_seconds()
            if age > plan.ttl_seconds:
                expired.append(pid)

        for pid in expired:
            del store[pid]

        if expired:
            self._save(store)
            logger.info("Cleaned up %d expired plan(s): %s", len(expired), expired)

        return len(expired)

    def list_pending(self) -> list[str]:
        """Return all pending plan IDs (including potentially expired ones)."""
        return list(self._load().keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        if not self._store_path.exists():
            return {}
        try:
            with self._store_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load pending store: %s", exc)
            return {}

    def _save(self, store: dict) -> None:
        with self._store_path.open("w", encoding="utf-8") as fh:
            json.dump(store, fh, ensure_ascii=False, indent=2, default=str)

    def _remove(self, plan_id: str) -> None:
        store = self._load()
        store.pop(plan_id, None)
        self._save(store)

    @staticmethod
    def _assert_not_expired(plan: ActionPlan) -> None:
        now = datetime.now(tz=timezone.utc)
        created = plan.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (now - created).total_seconds()
        if age > plan.ttl_seconds:
            raise PlanExpiredError(plan.plan_id)
