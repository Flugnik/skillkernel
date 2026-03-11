"""
Tests for skills/limiter/plugin.py — LimiterSkill integration tests.

These tests exercise the full skill handle() flow end-to-end,
using the domain_root fixture to isolate file I/O.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from core.models import (
    DispatchDecision,
    IncomingEvent,
    RoutingStatus,
    SkillContext,
    SkillStatus,
)
from skills.limiter.plugin import LimiterSkill, _pending_overlimit


def _make_ctx(text: str) -> SkillContext:
    event = IncomingEvent(text=text, source="test")
    decision = DispatchDecision(
        event_id=event.event_id,
        status=RoutingStatus.matched,
        matched_skill="limiter",
    )
    return SkillContext(event=event, decision=decision)


@pytest.fixture(autouse=True)
def clear_pending():
    """Clear the in-memory pending overlimit state before each test."""
    _pending_overlimit.clear()
    yield
    _pending_overlimit.clear()


@pytest.fixture()
def skill():
    return LimiterSkill()


# ---------------------------------------------------------------------------
# Score tests
# ---------------------------------------------------------------------------


class TestScore:
    def test_summary_command_high_score(self, skill):
        event = IncomingEvent(text="/summary 2026-03-15", source="test")
        assert skill.score(event) >= 0.9

    def test_days_command_high_score(self, skill):
        event = IncomingEvent(text="/days", source="test")
        assert skill.score(event) >= 0.9

    def test_order_text_scores_positive(self, skill):
        event = IncomingEvent(text="2026-03-15 milk_1_5 12", source="test")
        assert skill.score(event) > 0.0

    def test_unrelated_text_scores_zero(self, skill):
        event = IncomingEvent(text="погода в москве", source="test")
        assert skill.score(event) == 0.0


# ---------------------------------------------------------------------------
# CreateOrderIntent — within limits
# ---------------------------------------------------------------------------


class TestCreateOrderWithinLimit:
    def test_plan_ready_when_within_limit(self, skill, domain_root, sample_day):
        ctx = _make_ctx("2026-03-15 milk_1_5 10")
        result = skill.handle(ctx)

        assert result.status == SkillStatus.plan_ready
        assert result.plan is not None

    def test_plan_has_actions(self, skill, domain_root, sample_day):
        ctx = _make_ctx("2026-03-15 milk_1_5 10")
        result = skill.handle(ctx)

        assert len(result.plan.actions) >= 1

    def test_auto_creates_production_day(self, skill, domain_root):
        """First order on a new date should auto-create the production day."""
        ctx = _make_ctx("2026-04-01 milk_1_5 5")
        result = skill.handle(ctx)

        assert result.status == SkillStatus.plan_ready
        # Plan must include ensure_json_file for the new day
        from core.models import ActionType
        action_types = [a.action_type for a in result.plan.actions]
        assert ActionType.ensure_json_file in action_types


# ---------------------------------------------------------------------------
# CreateOrderIntent — over limit
# ---------------------------------------------------------------------------


class TestCreateOrderOverLimit:
    def test_clarification_required_when_over_limit(self, skill, domain_root, sample_day):
        """Requesting more than limit → clarification_required."""
        ctx = _make_ctx("2026-03-15 milk_1_5 200")
        result = skill.handle(ctx)

        assert result.status == SkillStatus.clarification_required
        assert result.plan is None
        assert result.clarification_message is not None
        assert "Перегруз" in result.clarification_message or "перегруз" in result.clarification_message.lower()

    def test_clarification_shows_shortage_info(self, skill, domain_root, sample_day):
        ctx = _make_ctx("2026-03-15 milk_1_5 200")
        result = skill.handle(ctx)

        msg = result.clarification_message
        assert "milk_1_5" in msg
        assert "force_negative" in msg
        assert "accept_free_only" in msg

    def test_overlimit_stored_in_pending(self, skill, domain_root, sample_day):
        ctx = _make_ctx("2026-03-15 milk_1_5 200")
        skill.handle(ctx)

        assert len(_pending_overlimit) == 1


# ---------------------------------------------------------------------------
# Overlimit resolution — force_negative
# ---------------------------------------------------------------------------


class TestForceNegativeResolution:
    def test_force_negative_builds_plan(self, skill, domain_root, sample_day):
        # First: create overlimit situation
        ctx1 = _make_ctx("2026-03-15 milk_1_5 200")
        skill.handle(ctx1)

        # Second: resolve with force_negative
        ctx2 = _make_ctx("force_negative")
        result = skill.handle(ctx2)

        assert result.status == SkillStatus.plan_ready
        assert result.plan is not None

    def test_force_negative_accepted_qty_equals_requested(self, skill, domain_root, sample_day):
        ctx1 = _make_ctx("2026-03-15 milk_1_5 200")
        skill.handle(ctx1)

        ctx2 = _make_ctx("force_negative")
        result = skill.handle(ctx2)

        from core.models import ActionType
        write_action = next(
            a for a in result.plan.actions if a.action_type == ActionType.write_json
        )
        order_data = write_action.params["data"]
        milk = next(i for i in order_data["items"] if i["sku"] == "milk_1_5")
        assert milk["accepted_qty"] == 200


# ---------------------------------------------------------------------------
# Overlimit resolution — accept_free_only
# ---------------------------------------------------------------------------


class TestAcceptFreeOnlyResolution:
    def test_accept_free_only_builds_plan(self, skill, domain_root, sample_day):
        ctx1 = _make_ctx("2026-03-15 milk_1_5 200")
        skill.handle(ctx1)

        ctx2 = _make_ctx("accept_free_only")
        result = skill.handle(ctx2)

        assert result.status == SkillStatus.plan_ready

    def test_accept_free_only_truncates_qty(self, skill, domain_root, sample_day):
        # limit=100, no existing orders → free=100
        # request 200 → accepted should be 100
        ctx1 = _make_ctx("2026-03-15 milk_1_5 200")
        skill.handle(ctx1)

        ctx2 = _make_ctx("accept_free_only")
        result = skill.handle(ctx2)

        from core.models import ActionType
        write_action = next(
            a for a in result.plan.actions if a.action_type == ActionType.write_json
        )
        order_data = write_action.params["data"]
        milk = next(i for i in order_data["items"] if i["sku"] == "milk_1_5")
        assert milk["accepted_qty"] == 100  # capped at free


# ---------------------------------------------------------------------------
# Overlimit resolution — cancel
# ---------------------------------------------------------------------------


class TestCancelResolution:
    def test_cancel_returns_informational(self, skill, domain_root, sample_day):
        ctx1 = _make_ctx("2026-03-15 milk_1_5 200")
        skill.handle(ctx1)

        ctx2 = _make_ctx("cancel")
        result = skill.handle(ctx2)

        assert result.status == SkillStatus.informational
        assert result.plan is None

    def test_cancel_clears_pending(self, skill, domain_root, sample_day):
        ctx1 = _make_ctx("2026-03-15 milk_1_5 200")
        skill.handle(ctx1)

        ctx2 = _make_ctx("cancel")
        skill.handle(ctx2)

        assert len(_pending_overlimit) == 0


# ---------------------------------------------------------------------------
# SummaryIntent
# ---------------------------------------------------------------------------


class TestSummaryIntent:
    def test_summary_returns_informational(self, skill, domain_root, sample_day):
        ctx = _make_ctx("/summary 2026-03-15")
        result = skill.handle(ctx)

        assert result.status == SkillStatus.informational
        assert result.plan is None
        assert result.clarification_message is not None

    def test_summary_contains_sku_data(self, skill, domain_root, sample_day):
        ctx = _make_ctx("summary 2026-03-15")
        result = skill.handle(ctx)

        assert "milk_1_5" in result.clarification_message


# ---------------------------------------------------------------------------
# DaysLoadIntent
# ---------------------------------------------------------------------------


class TestDaysLoadIntent:
    def test_days_returns_informational(self, skill, domain_root, sample_day):
        ctx = _make_ctx("/days")
        result = skill.handle(ctx)

        assert result.status == SkillStatus.informational

    def test_days_shows_date(self, skill, domain_root, sample_day):
        ctx = _make_ctx("days")
        result = skill.handle(ctx)

        assert "2026-03-15" in result.clarification_message


# ---------------------------------------------------------------------------
# ExportIntent
# ---------------------------------------------------------------------------


class TestExportIntent:
    def test_export_returns_rejected(self, skill, domain_root):
        ctx = _make_ctx("/export 2026-03-15")
        result = skill.handle(ctx)

        assert result.status == SkillStatus.rejected
        assert "не реализован" in result.clarification_message.lower() or "not implemented" in result.clarification_message.lower()


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_unknown_sku_returns_clarification(self, skill, domain_root, sample_day):
        ctx = _make_ctx("2026-03-15 unknown_sku_xyz 10")
        result = skill.handle(ctx)

        assert result.status == SkillStatus.clarification_needed
        assert "unknown_sku_xyz" in result.clarification_message

    def test_unparseable_text_returns_clarification(self, skill, domain_root):
        ctx = _make_ctx("абракадабра без смысла")
        result = skill.handle(ctx)

        # Either clarification_needed (parse failed) or unknown routing
        assert result.status in (SkillStatus.clarification_needed, SkillStatus.error)
