"""
Tests for skills/limiter/planner.py
"""

from __future__ import annotations

from datetime import date

import pytest

from core.models import ActionType
from skills.limiter import capacity_engine, planner
from skills.limiter.domain import (
    LimitCheckStatus,
    OrderDraft,
    OrderItemDraft,
    ProductionDay,
    ProductionDayLimit,
)
from tests.limiter.conftest import PRODUCTS_BY_SKU


def _make_draft(items: list[tuple[str, int]], d: date = date(2026, 3, 15)) -> OrderDraft:
    return OrderDraft(
        delivery_date=d,
        items=[OrderItemDraft(sku=sku, requested_qty=qty) for sku, qty in items],
    )


class TestBuildNormalOrderPlan:
    def test_plan_has_write_json_action(self, domain_root, sample_day):
        draft = _make_draft([("milk_1_5", 10)])
        check = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        plan = planner.build_normal_order_plan(
            event_id="evt-001",
            draft=draft,
            check_result=check,
            products=PRODUCTS_BY_SKU,
            day_was_created=False,
            day_data=None,
            day_path=None,
            preview_text="preview",
        )

        assert plan.skill_name == "limiter"
        action_types = [a.action_type for a in plan.actions]
        assert ActionType.write_json in action_types

    def test_plan_requires_confirmation(self, domain_root, sample_day):
        draft = _make_draft([("milk_1_5", 10)])
        check = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        plan = planner.build_normal_order_plan(
            event_id="evt-001",
            draft=draft,
            check_result=check,
            products=PRODUCTS_BY_SKU,
            day_was_created=False,
            day_data=None,
            day_path=None,
            preview_text="preview",
        )

        assert plan.requires_confirmation is True

    def test_plan_includes_ensure_json_when_day_created(self, domain_root):
        """When production day is new, plan must include ensure_json_file action."""
        day, was_created = planner.repository.ensure_production_day(date(2026, 4, 1))
        assert was_created

        draft = _make_draft([("milk_1_5", 10)], d=date(2026, 4, 1))
        check = capacity_engine.check_order(draft, day, PRODUCTS_BY_SKU)
        day_data = planner.repository.production_day_data(day)
        day_path = planner.repository.production_day_path(date(2026, 4, 1))

        plan = planner.build_normal_order_plan(
            event_id="evt-002",
            draft=draft,
            check_result=check,
            products=PRODUCTS_BY_SKU,
            day_was_created=True,
            day_data=day_data,
            day_path=day_path,
            preview_text="preview",
        )

        action_types = [a.action_type for a in plan.actions]
        assert ActionType.ensure_json_file in action_types
        assert ActionType.write_json in action_types


class TestBuildForceNegativePlan:
    def test_accepted_qty_equals_requested(self, domain_root, sample_day):
        """force_negative: accepted_qty must equal requested_qty even when over limit."""
        # Exhaust capacity first
        draft = _make_draft([("milk_1_5", 120)])  # limit=100, shortage=20
        check = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)
        assert check.status == LimitCheckStatus.over_limit

        plan = planner.build_force_negative_plan(
            event_id="evt-003",
            draft=draft,
            check_result=check,
            products=PRODUCTS_BY_SKU,
            day_was_created=False,
            day_data=None,
            day_path=None,
            preview_text="preview",
        )

        # Find the write_json action and inspect the order data
        write_action = next(a for a in plan.actions if a.action_type == ActionType.write_json)
        order_data = write_action.params["data"]
        milk_item = next(i for i in order_data["items"] if i["sku"] == "milk_1_5")
        assert milk_item["accepted_qty"] == 120  # full requested, not capped


class TestBuildAcceptFreeOnlyPlan:
    def test_accepted_qty_capped_at_free(self, domain_root, sample_day, confirmed_order):
        """accept_free_only: accepted_qty = min(requested, free)."""
        # confirmed_order: milk_1_5 reserved=30, free=70
        # Request 90 → free=70, accepted should be 70
        draft = _make_draft([("milk_1_5", 90)])
        check = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)
        assert check.status == LimitCheckStatus.over_limit

        plan = planner.build_accept_free_only_plan(
            event_id="evt-004",
            draft=draft,
            check_result=check,
            products=PRODUCTS_BY_SKU,
            day_was_created=False,
            day_data=None,
            day_path=None,
            preview_text="preview",
        )

        write_action = next(a for a in plan.actions if a.action_type == ActionType.write_json)
        order_data = write_action.params["data"]
        milk_item = next(i for i in order_data["items"] if i["sku"] == "milk_1_5")
        assert milk_item["accepted_qty"] == 70  # capped at free

    def test_within_limit_items_not_truncated(self, domain_root, sample_day):
        """Items within limit should not be truncated in accept_free_only."""
        draft = _make_draft([("milk_1_5", 10), ("kefir_1", 200)])
        check = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        plan = planner.build_accept_free_only_plan(
            event_id="evt-005",
            draft=draft,
            check_result=check,
            products=PRODUCTS_BY_SKU,
            day_was_created=False,
            day_data=None,
            day_path=None,
            preview_text="preview",
        )

        write_action = next(a for a in plan.actions if a.action_type == ActionType.write_json)
        order_data = write_action.params["data"]
        milk_item = next(i for i in order_data["items"] if i["sku"] == "milk_1_5")
        assert milk_item["accepted_qty"] == 10  # not truncated


class TestBuildSummaryResponse:
    def test_summary_shows_sku_data(self, domain_root, sample_day, confirmed_order):
        text = planner.build_summary_response(date(2026, 3, 15))
        assert "milk_1_5" in text
        assert "kefir_1" in text

    def test_summary_missing_day(self, domain_root):
        text = planner.build_summary_response(date(2026, 5, 1))
        assert "не создан" in text.lower() or "не создан" in text


class TestBuildDaysLoadResponse:
    def test_days_load_shows_percentage(self, domain_root, sample_day, confirmed_order):
        text = planner.build_days_load_response(days_ahead=30)
        assert "2026-03-15" in text
        assert "%" in text

    def test_days_load_empty(self, domain_root):
        text = planner.build_days_load_response(days_ahead=14)
        assert "нет" in text.lower() or "Нет" in text
