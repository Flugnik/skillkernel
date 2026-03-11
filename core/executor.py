"""
ActionExecutor — executes an ActionPlan by dispatching each Action
to the appropriate executor from the ExecutorRegistry.
"""

from __future__ import annotations

import logging

from core.models import Action, ActionPlan, ExecutionResult

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes all actions in an ActionPlan using registered executors.

    Executors are looked up from an ExecutorRegistry instance.
    Side effects happen here — skills themselves remain pure.
    """

    def __init__(self, executor_registry: "ExecutorRegistry") -> None:  # noqa: F821
        self._registry = executor_registry

    def execute(self, plan: ActionPlan) -> ExecutionResult:
        """Execute every action in the plan sequentially.

        Continues on individual action errors, collecting them in the result.
        """
        executed: list[str] = []
        errors: list[str] = []

        logger.info(
            "Executing plan plan_id=%s skill=%s actions=%d",
            plan.plan_id, plan.skill_name, len(plan.actions),
        )

        for i, action in enumerate(plan.actions):
            label = f"[{i}] {action.action_type.value}"
            try:
                executor_fn = self._registry.get(action.action_type.value)
                executor_fn(action)
                executed.append(label)
                logger.debug("Action %s executed successfully.", label)
            except Exception as exc:  # noqa: BLE001
                msg = f"{label} failed: {exc}"
                errors.append(msg)
                logger.error("Action %s failed: %s", label, exc)

        success = len(errors) == 0
        result = ExecutionResult(
            plan_id=plan.plan_id,
            success=success,
            executed_actions=executed,
            errors=errors,
        )
        logger.info(
            "Plan plan_id=%s finished: success=%s executed=%d errors=%d",
            plan.plan_id, success, len(executed), len(errors),
        )
        return result
