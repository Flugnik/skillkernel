"""Runtime handler that bridges CoreEvent to the existing dispatcher."""

from __future__ import annotations

from core.config import load_config
from core.confirm_manager import ConfirmManager
from core.dispatcher import Dispatcher
from core.event_log import EventLogger
from core.executor import ActionExecutor
from core.registry import SkillRegistry
from core.router import SkillRouter
from executors.file_executor import (
    execute_ensure_json_file,
    execute_noop,
    execute_write_json,
    execute_write_markdown,
    execute_write_xlsx_export,
)
from executors.registry import ExecutorRegistry
from skills.farm_guardian.plugin import FarmGuardianSkill
from skills.limiter.plugin import LimiterSkill

from .contract import CoreEvent, CoreResult


def _build_dispatcher() -> Dispatcher:
    config = load_config()

    skill_registry = SkillRegistry()
    skill_registry.register(FarmGuardianSkill())
    skill_registry.register(LimiterSkill())

    executor_registry = ExecutorRegistry()
    executor_registry.register("write_markdown", execute_write_markdown)
    executor_registry.register("write_json", execute_write_json)
    executor_registry.register("ensure_json_file", execute_ensure_json_file)
    executor_registry.register("noop", execute_noop)
    executor_registry.register("write_xlsx_export", execute_write_xlsx_export)

    event_logger = EventLogger(log_dir=config.log_dir)
    confirm_manager = ConfirmManager(store_path=config.pending_store_path)
    confirm_manager.cleanup_expired()

    router = SkillRouter(registry=skill_registry, config=config)
    executor = ActionExecutor(executor_registry=executor_registry)

    return Dispatcher(
        registry=skill_registry,
        router=router,
        confirm_manager=confirm_manager,
        executor=executor,
        event_logger=event_logger,
    )


_DISPATCHER = _build_dispatcher()


def handle(event: CoreEvent) -> CoreResult:
    """Handle a normalized event and return a normalized runtime result."""

    outcome = _DISPATCHER.dispatch(
        __import__("core.models", fromlist=["IncomingEvent"]).IncomingEvent(
            text=event.text,
            source=event.meta.get("source", "cli"),
            metadata=dict(event.meta),
        )
    )

    if outcome.execution_result is not None:
        return CoreResult(type="message", content=outcome.message, meta={"plan_id": outcome.plan_id})
    if outcome.requires_confirmation:
        return CoreResult(type="confirm", content=outcome.preview_text or outcome.message, meta={"plan_id": outcome.plan_id})
    if outcome.decision.status.value in {"unknown", "ambiguous"}:
        return CoreResult(type="clarify", content=outcome.message, meta={"decision": outcome.decision.model_dump(mode="json")})
    return CoreResult(type="message", content=outcome.message)

