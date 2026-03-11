"""
Tests for Dispatcher orchestration logic.

Uses tmp_path fixtures to avoid polluting real memory/ directories.
"""

from __future__ import annotations

import pytest

from core.config import PlatformConfig
from core.confirm_manager import ConfirmManager
from core.dispatcher import Dispatcher
from core.event_log import EventLogger
from core.executor import ActionExecutor
from core.models import IncomingEvent, RoutingStatus, SkillStatus
from core.registry import SkillRegistry
from core.router import SkillRouter
from executors.file_executor import (
    execute_noop,
    execute_write_markdown,
    execute_write_json,
    execute_ensure_json_file,
)
from executors.registry import ExecutorRegistry
from skills.farm_guardian.plugin import FarmGuardianSkill
from skills.limiter.plugin import LimiterSkill


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config() -> PlatformConfig:
    return PlatformConfig(
        threshold_unknown=0.2,
        threshold_ambiguous_gap=0.15,
        confirmation_ttl_seconds=300,
    )


@pytest.fixture()
def skill_registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(FarmGuardianSkill())
    reg.register(LimiterSkill())
    return reg


@pytest.fixture()
def executor_registry() -> ExecutorRegistry:
    reg = ExecutorRegistry()
    reg.register("write_markdown", execute_write_markdown)
    reg.register("write_json", execute_write_json)
    reg.register("ensure_json_file", execute_ensure_json_file)
    reg.register("noop", execute_noop)
    return reg


@pytest.fixture()
def dispatcher(tmp_path, config, skill_registry, executor_registry) -> Dispatcher:
    log_dir = tmp_path / "event_log"
    pending_path = tmp_path / "runtime" / "pending_plans.json"

    event_logger = EventLogger(log_dir=str(log_dir))
    confirm_manager = ConfirmManager(store_path=str(pending_path))
    router = SkillRouter(registry=skill_registry, config=config)
    action_executor = ActionExecutor(executor_registry=executor_registry)

    return Dispatcher(
        registry=skill_registry,
        router=router,
        confirm_manager=confirm_manager,
        executor=action_executor,
        event_logger=event_logger,
    )


# ---------------------------------------------------------------------------
# Tests: unknown / ambiguous routing
# ---------------------------------------------------------------------------


class TestDispatcherRouting:
    def test_unknown_event_returns_no_plan(self, dispatcher):
        event = IncomingEvent(text="Привет, как дела?")
        outcome = dispatcher.dispatch(event)
        assert outcome.decision.status == RoutingStatus.unknown
        assert outcome.plan_id is None
        assert outcome.execution_result is None

    def test_ambiguous_event_returns_no_plan(self, tmp_path, executor_registry):
        """Force ambiguous by setting a very high gap threshold."""
        cfg = PlatformConfig(
            threshold_unknown=0.0,
            threshold_ambiguous_gap=1.0,
        )
        reg = SkillRegistry()
        reg.register(FarmGuardianSkill())
        reg.register(LimiterSkill())
        router = SkillRouter(registry=reg, config=cfg)
        confirm_manager = ConfirmManager(store_path=str(tmp_path / "p.json"))
        event_logger = EventLogger(log_dir=str(tmp_path / "logs"))
        action_executor = ActionExecutor(executor_registry=executor_registry)

        d = Dispatcher(
            registry=reg,
            router=router,
            confirm_manager=confirm_manager,
            executor=action_executor,
            event_logger=event_logger,
        )
        event = IncomingEvent(text="Маша корова кг корм лимит журнал")
        outcome = d.dispatch(event)
        assert outcome.decision.status == RoutingStatus.ambiguous
        assert outcome.plan_id is None


# ---------------------------------------------------------------------------
# Tests: matched → preview → confirm → execute
# ---------------------------------------------------------------------------


class TestDispatcherFarmGuardian:
    def test_dispatch_returns_preview(self, dispatcher):
        event = IncomingEvent(text="Маша сегодня хорошо поела, записать в журнал")
        outcome = dispatcher.dispatch(event)

        assert outcome.decision.status == RoutingStatus.matched
        assert outcome.decision.matched_skill == "farm_guardian"
        assert outcome.requires_confirmation is True
        assert outcome.plan_id is not None
        assert outcome.preview_text is not None
        assert "Маша" in outcome.preview_text or "journal" in outcome.preview_text.lower()
        assert outcome.execution_result is None

    def test_confirm_executes_plan(self, dispatcher, tmp_path):
        event = IncomingEvent(text="Плюша отелилась, записать в журнал")
        outcome = dispatcher.dispatch(event)
        assert outcome.plan_id is not None

        confirm_outcome = dispatcher.confirm_plan(outcome.plan_id)
        assert confirm_outcome.execution_result is not None
        assert confirm_outcome.execution_result.success is True

    def test_reject_removes_plan(self, dispatcher):
        event = IncomingEvent(text="Корова заболела, наблюдение")
        outcome = dispatcher.dispatch(event)
        plan_id = outcome.plan_id
        assert plan_id is not None

        msg = dispatcher.reject_plan(plan_id)
        assert plan_id in msg or "rejected" in msg.lower()

        # Plan should no longer exist
        from core.exceptions import PlanNotFoundError
        with pytest.raises(PlanNotFoundError):
            dispatcher.confirm_plan(plan_id)


class TestDispatcherLimiter:
    def test_dispatch_summary_returns_informational(self, dispatcher):
        """/summary command routes to limiter and returns informational (no plan)."""
        event = IncomingEvent(text="/summary 2026-03-15")
        outcome = dispatcher.dispatch(event)

        assert outcome.decision.status == RoutingStatus.matched
        assert outcome.decision.matched_skill == "limiter"
        # summary is informational — no plan, no confirmation needed
        assert outcome.plan_id is None
        assert outcome.execution_result is None

    def test_dispatch_days_returns_informational(self, dispatcher):
        """/days command routes to limiter and returns informational."""
        event = IncomingEvent(text="/days")
        outcome = dispatcher.dispatch(event)

        assert outcome.decision.status == RoutingStatus.matched
        assert outcome.decision.matched_skill == "limiter"
        assert outcome.plan_id is None

    def test_dispatch_order_within_limit_returns_preview(self, dispatcher, tmp_path, monkeypatch):
        """A valid order within limits produces a plan_ready with confirmation."""
        import json
        import skills.limiter.manifest as mf

        # Set up isolated domain in tmp_path
        root = tmp_path / "limiter_domain"
        (root / "production_days").mkdir(parents=True)
        (root / "orders").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)

        from tests.limiter.conftest import PRODUCTS
        products_data = [p.model_dump(mode="json") for p in PRODUCTS]
        (root / "products.json").write_text(
            json.dumps(products_data, ensure_ascii=False), encoding="utf-8"
        )

        monkeypatch.setattr(mf, "DOMAIN_ROOT", str(root))
        monkeypatch.setattr(mf, "PRODUCTS_PATH", str(root / "products.json"))
        monkeypatch.setattr(mf, "PRODUCTION_DAYS_DIR", str(root / "production_days"))
        monkeypatch.setattr(mf, "ORDERS_DIR", str(root / "orders"))
        monkeypatch.setattr(mf, "EXPORTS_DIR", str(root / "exports"))

        event = IncomingEvent(text="2026-03-15 milk_1_5 10")
        outcome = dispatcher.dispatch(event)

        assert outcome.decision.status == RoutingStatus.matched
        assert outcome.decision.matched_skill == "limiter"
        assert outcome.requires_confirmation is True
        assert outcome.plan_id is not None

    def test_confirm_order_executes(self, dispatcher, tmp_path, monkeypatch):
        """Confirming a limiter order plan executes write_json actions."""
        import json
        import skills.limiter.manifest as mf

        root = tmp_path / "limiter_domain2"
        (root / "production_days").mkdir(parents=True)
        (root / "orders").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)

        from tests.limiter.conftest import PRODUCTS
        products_data = [p.model_dump(mode="json") for p in PRODUCTS]
        (root / "products.json").write_text(
            json.dumps(products_data, ensure_ascii=False), encoding="utf-8"
        )

        monkeypatch.setattr(mf, "DOMAIN_ROOT", str(root))
        monkeypatch.setattr(mf, "PRODUCTS_PATH", str(root / "products.json"))
        monkeypatch.setattr(mf, "PRODUCTION_DAYS_DIR", str(root / "production_days"))
        monkeypatch.setattr(mf, "ORDERS_DIR", str(root / "orders"))
        monkeypatch.setattr(mf, "EXPORTS_DIR", str(root / "exports"))

        event = IncomingEvent(text="2026-03-15 milk_1_5 5")
        outcome = dispatcher.dispatch(event)
        assert outcome.plan_id is not None

        confirm_outcome = dispatcher.confirm_plan(outcome.plan_id)
        er = confirm_outcome.execution_result
        assert er is not None
        assert er.success is True
        assert len(er.executed_actions) >= 1


# ---------------------------------------------------------------------------
# Tests: immediate execution (no confirmation)
# ---------------------------------------------------------------------------


class TestDispatcherNoConfirmation:
    def test_no_confirmation_executes_immediately(self, tmp_path, executor_registry, config):
        """A skill that sets requires_confirmation=False should execute immediately."""
        from core.models import (
            Action, ActionPlan, ActionType, SkillContext, SkillResult, SkillStatus,
        )
        from skills.base import BaseSkill

        class ImmediateSkill(BaseSkill):
            name = "immediate"
            version = "0.1.0"
            description = "Always matches, no confirmation."
            examples = []

            def score(self, event: IncomingEvent) -> float:
                return 0.9

            def handle(self, ctx: SkillContext) -> SkillResult:
                plan = ActionPlan(
                    skill_name=self.name,
                    event_id=ctx.event.event_id,
                    actions=[Action(action_type=ActionType.noop)],
                    preview_text="noop preview",
                    requires_confirmation=False,
                )
                return SkillResult(status=SkillStatus.plan_ready, plan=plan)

        reg = SkillRegistry()
        reg.register(ImmediateSkill())
        router = SkillRouter(registry=reg, config=config)
        confirm_manager = ConfirmManager(store_path=str(tmp_path / "p.json"))
        event_logger = EventLogger(log_dir=str(tmp_path / "logs"))
        action_executor = ActionExecutor(executor_registry=executor_registry)

        d = Dispatcher(
            registry=reg,
            router=router,
            confirm_manager=confirm_manager,
            executor=action_executor,
            event_logger=event_logger,
        )

        event = IncomingEvent(text="anything")
        outcome = d.dispatch(event)

        assert outcome.is_executed is True
        assert outcome.requires_confirmation is False
        assert outcome.execution_result is not None
        assert outcome.execution_result.success is True
