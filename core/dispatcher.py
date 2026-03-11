"""
Dispatcher — the central orchestrator of SkillKernel.

Flow:
  IncomingEvent
    → SkillRouter  (routing decision)
    → BaseSkill.handle()  (skill result + ActionPlan)
    → if requires_confirmation: ConfirmManager.store_plan() → return preview
    → else: ActionExecutor.execute() → return ExecutionResult
"""

from __future__ import annotations

import logging
from typing import Any

from core.confirm_manager import ConfirmManager
from core.event_log import EventLogger
from core.executor import ActionExecutor
from core.models import (
    DispatchDecision,
    ExecutionResult,
    IncomingEvent,
    RoutingStatus,
    SkillContext,
    SkillResult,
    SkillStatus,
)
from core.registry import SkillRegistry
from core.router import SkillRouter

logger = logging.getLogger(__name__)


class DispatchOutcome:
    """Carries the result of a full dispatch cycle back to the caller."""

    def __init__(
        self,
        *,
        decision: DispatchDecision,
        skill_result: SkillResult | None = None,
        execution_result: ExecutionResult | None = None,
        preview_text: str | None = None,
        plan_id: str | None = None,
        message: str = "",
    ) -> None:
        self.decision = decision
        self.skill_result = skill_result
        self.execution_result = execution_result
        self.preview_text = preview_text
        self.plan_id = plan_id
        self.message = message

    @property
    def requires_confirmation(self) -> bool:
        return self.plan_id is not None and self.execution_result is None

    @property
    def is_executed(self) -> bool:
        return self.execution_result is not None


class Dispatcher:
    """Orchestrates routing, skill invocation, confirmation, and execution."""

    def __init__(
        self,
        registry: SkillRegistry,
        router: SkillRouter,
        confirm_manager: ConfirmManager,
        executor: ActionExecutor,
        event_logger: EventLogger,
    ) -> None:
        self._registry = registry
        self._router = router
        self._confirm_manager = confirm_manager
        self._executor = executor
        self._event_logger = event_logger

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def dispatch(self, event: IncomingEvent) -> DispatchOutcome:
        """Process an IncomingEvent through the full dispatch pipeline."""
        logger.info("Dispatching event_id=%s text=%r", event.event_id, event.text[:80])
        self._event_logger.log_incoming_event(event.model_dump(mode="json"))

        # 1. Route
        decision = self._router.route(event)
        self._event_logger.log_routing_decision(decision.model_dump(mode="json"))

        if decision.status != RoutingStatus.matched:
            logger.info(
                "Routing returned '%s' for event_id=%s — not dispatching to skill.",
                decision.status.value, event.event_id,
            )
            return DispatchOutcome(
                decision=decision,
                message=decision.message,
            )

        # 2. Invoke skill
        skill = self._registry.get(decision.matched_skill)  # type: ignore[arg-type]
        ctx = SkillContext(event=event, decision=decision)

        try:
            skill_result = skill.handle(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.error("Skill '%s' raised during handle(): %s", skill.name, exc)
            self._event_logger.log_error({
                "event_id": event.event_id,
                "skill": skill.name,
                "error": str(exc),
            })
            return DispatchOutcome(
                decision=decision,
                message=f"Skill '{skill.name}' encountered an error: {exc}",
            )

        self._event_logger.log_skill_result(skill_result.model_dump(mode="json"))

        # 3. Handle non-plan statuses
        if skill_result.status in (
            SkillStatus.clarification_needed,
            SkillStatus.clarification_required,
            SkillStatus.informational,
            SkillStatus.rejected,
        ):
            return DispatchOutcome(
                decision=decision,
                skill_result=skill_result,
                message=skill_result.clarification_message or "Please clarify your request.",
            )

        if skill_result.status == SkillStatus.error:
            return DispatchOutcome(
                decision=decision,
                skill_result=skill_result,
                message=skill_result.error_message or "Skill returned an error.",
            )

        # 4. Plan is ready
        plan = skill_result.plan
        if plan is None:
            logger.error("Skill '%s' returned plan_ready but plan is None.", skill.name)
            return DispatchOutcome(
                decision=decision,
                skill_result=skill_result,
                message="Skill returned plan_ready but provided no plan.",
            )

        if plan.requires_confirmation:
            self._confirm_manager.store_plan(plan)
            logger.info(
                "Plan plan_id=%s stored for confirmation (skill=%s).",
                plan.plan_id, skill.name,
            )
            return DispatchOutcome(
                decision=decision,
                skill_result=skill_result,
                preview_text=plan.preview_text,
                plan_id=plan.plan_id,
                message=(
                    f"Preview ready. Confirm with: confirm {plan.plan_id}\n"
                    f"Reject with: reject {plan.plan_id}"
                ),
            )

        # 5. Execute immediately (no confirmation required)
        execution_result = self._executor.execute(plan)
        self._event_logger.log_execution_result(execution_result.model_dump(mode="json"))

        return DispatchOutcome(
            decision=decision,
            skill_result=skill_result,
            execution_result=execution_result,
            message="Executed without confirmation.",
        )

    # ------------------------------------------------------------------
    # Confirm / reject
    # ------------------------------------------------------------------

    def confirm_plan(self, plan_id: str) -> DispatchOutcome:
        """Confirm a pending plan and execute it."""
        logger.info("Confirming plan_id=%s", plan_id)
        plan = self._confirm_manager.confirm(plan_id)
        execution_result = self._executor.execute(plan)
        self._event_logger.log_execution_result(execution_result.model_dump(mode="json"))

        # Build a minimal decision for the outcome
        decision = DispatchDecision(
            event_id=plan.event_id,
            status=RoutingStatus.matched,
            matched_skill=plan.skill_name,
            message="Confirmed and executed.",
        )
        return DispatchOutcome(
            decision=decision,
            execution_result=execution_result,
            message="Plan confirmed and executed.",
        )

    def reject_plan(self, plan_id: str) -> str:
        """Reject and discard a pending plan. Returns a status message."""
        self._confirm_manager.reject(plan_id)
        logger.info("Plan plan_id=%s rejected by user.", plan_id)
        return f"Plan {plan_id} rejected."
