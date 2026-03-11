"""
Tests for skills/limiter/capacity_engine.py
"""

from __future__ import annotations

from datetime import date

import pytest

from skills.limiter import capacity_engine
from skills.limiter.domain import (
    LimitCheckStatus,
    OrderDraft,
    OrderItemDraft,
)
from tests.limiter.conftest import PRODUCTS_BY_SKU


def _make_draft(items: list[tuple[str, int]], d: date = date(2026, 3, 15)) -> OrderDraft:
    return OrderDraft(
        delivery_date=d,
        items=[OrderItemDraft(sku=sku, requested_qty=qty) for sku, qty in items],
    )


class TestCheckOrderWithinLimit:
    def test_ok_when_all_within_limit(self, domain_root, sample_day):
        """Order within limits → status ok, no shortage."""
        draft = _make_draft([("milk_1_5", 30), ("kefir_1", 10)])
        result = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        assert result.status == LimitCheckStatus.ok
        assert all(item.shortage == 0 for item in result.items)

    def test_free_equals_limit_when_no_orders(self, domain_root, sample_day):
        """With no existing orders, free = limit."""
        draft = _make_draft([("milk_1_5", 1)])
        result = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        milk = next(i for i in result.items if i.sku == "milk_1_5")
        assert milk.reserved == 0
        assert milk.free == 100
        assert milk.limit == 100

    def test_reserved_reduces_free(self, domain_root, sample_day, confirmed_order):
        """Existing confirmed order reduces free capacity."""
        # confirmed_order has milk_1_5=30, kefir_1=10
        draft = _make_draft([("milk_1_5", 1)])
        result = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        milk = next(i for i in result.items if i.sku == "milk_1_5")
        assert milk.reserved == 30
        assert milk.free == 70


class TestCheckOrderOverLimit:
    def test_over_limit_detected(self, domain_root, sample_day, confirmed_order):
        """Requesting more than free → over_limit status."""
        # confirmed_order: milk_1_5 reserved=30, free=70
        # Request 80 → shortage = 10
        draft = _make_draft([("milk_1_5", 80)])
        result = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        assert result.status == LimitCheckStatus.over_limit
        milk = next(i for i in result.items if i.sku == "milk_1_5")
        assert milk.shortage == 10

    def test_shortage_calculation(self, domain_root, sample_day):
        """Shortage = requested - free (when positive)."""
        # No existing orders, limit=100, request 120 → shortage=20
        draft = _make_draft([("milk_1_5", 120)])
        result = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        assert result.status == LimitCheckStatus.over_limit
        milk = next(i for i in result.items if i.sku == "milk_1_5")
        assert milk.shortage == 20

    def test_partial_over_limit(self, domain_root, sample_day):
        """Only one SKU over limit → still over_limit overall."""
        draft = _make_draft([("milk_1_5", 10), ("kefir_1", 200)])
        result = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        assert result.status == LimitCheckStatus.over_limit
        over = result.over_limit_items
        assert len(over) == 1
        assert over[0].sku == "kefir_1"

    def test_over_limit_items_property(self, domain_root, sample_day):
        """over_limit_items returns only items with shortage > 0."""
        draft = _make_draft([("milk_1_5", 5), ("kefir_1", 200)])
        result = capacity_engine.check_order(draft, sample_day, PRODUCTS_BY_SKU)

        over = result.over_limit_items
        skus = {i.sku for i in over}
        assert "kefir_1" in skus
        assert "milk_1_5" not in skus
