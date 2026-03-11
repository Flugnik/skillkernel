"""
Tests for core Pydantic models.
"""

import pytest
from pydantic import ValidationError

from core.models import (
    Action,
    ActionPlan,
    ActionType,
    DispatchDecision,
    ExecutionResult,
    IncomingEvent,
    RoutingStatus,
    SkillContext,
    SkillResult,
    SkillStatus,
)


class TestIncomingEvent:
    def test_defaults_populated(self):
        event = IncomingEvent(text="hello")
        assert event.event_id
        assert event.source == "cli"
        assert event.timestamp is not None
        assert event.metadata == {}

    def test_custom_fields(self):
        event = IncomingEvent(text="test", source="api", metadata={"key": "val"})
        assert event.source == "api"
        assert event.metadata["key"] == "val"

    def test_text_required(self):
        with pytest.raises(ValidationError):
            IncomingEvent()  # type: ignore[call-arg]


class TestDispatchDecision:
    def test_matched(self):
        d = DispatchDecision(
            event_id="abc",
            status=RoutingStatus.matched,
            matched_skill="farm_guardian",
            scores={"farm_guardian": 0.8},
        )
        assert d.matched_skill == "farm_guardian"
        assert d.status == RoutingStatus.matched

    def test_unknown_no_skill(self):
        d = DispatchDecision(event_id="x", status=RoutingStatus.unknown)
        assert d.matched_skill is None
        assert d.scores == {}

    def test_ambiguous(self):
        d = DispatchDecision(
            event_id="y",
            status=RoutingStatus.ambiguous,
            scores={"a": 0.5, "b": 0.48},
        )
        assert d.status == RoutingStatus.ambiguous


class TestActionPlan:
    def test_plan_defaults(self):
        plan = ActionPlan(
            skill_name="test_skill",
            event_id="evt-1",
            actions=[Action(action_type=ActionType.noop)],
            preview_text="Preview here",
        )
        assert plan.plan_id
        assert plan.requires_confirmation is True
        assert plan.ttl_seconds == 300

    def test_write_markdown_action(self):
        action = Action(
            action_type=ActionType.write_markdown,
            params={"path": "/tmp/test.md", "content": "hello"},
        )
        assert action.action_type == ActionType.write_markdown
        assert action.params["path"] == "/tmp/test.md"

    def test_plan_serialization(self):
        plan = ActionPlan(
            skill_name="s",
            event_id="e",
            actions=[Action(action_type=ActionType.noop)],
            preview_text="p",
        )
        data = plan.model_dump(mode="json")
        restored = ActionPlan.model_validate(data)
        assert restored.plan_id == plan.plan_id
        assert restored.skill_name == plan.skill_name


class TestSkillResult:
    def test_plan_ready(self):
        plan = ActionPlan(
            skill_name="s",
            event_id="e",
            actions=[],
            preview_text="p",
        )
        result = SkillResult(status=SkillStatus.plan_ready, plan=plan)
        assert result.plan is not None

    def test_clarification(self):
        result = SkillResult(
            status=SkillStatus.clarification_needed,
            clarification_message="Please clarify.",
        )
        assert result.clarification_message == "Please clarify."
        assert result.plan is None


class TestExecutionResult:
    def test_success(self):
        er = ExecutionResult(
            plan_id="p1",
            success=True,
            executed_actions=["[0] write_markdown"],
        )
        assert er.success is True
        assert len(er.executed_actions) == 1
        assert er.errors == []

    def test_failure(self):
        er = ExecutionResult(
            plan_id="p2",
            success=False,
            errors=["[0] write_markdown failed: permission denied"],
        )
        assert er.success is False
        assert len(er.errors) == 1
