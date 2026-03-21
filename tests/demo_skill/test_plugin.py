
"""Tests for the demo_skill plugin."""

from __future__ import annotations

from core.models import DispatchDecision, IncomingEvent, RoutingStatus, SkillContext, SkillStatus
from skills.demo_skill.plugin import DemoSkill


def _make_ctx(text: str) -> SkillContext:
    event = IncomingEvent(text=text, source="test")
    decision = DispatchDecision(event_id=event.event_id, status=RoutingStatus.matched, matched_skill="demo_skill")
    return SkillContext(event=event, decision=decision)


def test_score_matches_demo_keywords():
    skill = DemoSkill()

    assert skill.score(IncomingEvent(text="demo skill", source="test")) == 1.0
    assert skill.score(IncomingEvent(text="unrelated text", source="test")) == 0.0


def test_score_rejects_generic_test_phrase():
    skill = DemoSkill()

    assert skill.score(IncomingEvent(text="unit test failed", source="test")) == 0.0


def test_handle_returns_informational_result():
    skill = DemoSkill()

    result = skill.handle(_make_ctx("demo skill"))

    assert result.status == SkillStatus.informational
    assert result.plan is None
    assert "demo skill" in result.clarification_message
