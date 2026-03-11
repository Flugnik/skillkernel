"""
Tests for skills/limiter/repository.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from skills.limiter import repository
from skills.limiter.domain import OrderStatus, Product, ProductionDay, ProductionDayLimit


class TestLoadProducts:
    def test_loads_all_products(self, domain_root):
        products = repository.load_products()
        assert len(products) == 3
        skus = {p.sku for p in products}
        assert "milk_1_5" in skus
        assert "kefir_1" in skus

    def test_products_by_sku_returns_dict(self, domain_root):
        by_sku = repository.products_by_sku()
        assert "milk_1_5" in by_sku
        assert by_sku["milk_1_5"].limit_default == 100

    def test_get_product_known(self, domain_root):
        p = repository.get_product("kefir_1")
        assert p is not None
        assert p.title == "Кефир 1%"

    def test_get_product_unknown(self, domain_root):
        p = repository.get_product("nonexistent_sku")
        assert p is None


class TestProductionDay:
    def test_load_existing_day(self, domain_root, sample_day):
        day = repository.load_production_day(date(2026, 3, 15))
        assert day is not None
        assert day.delivery_date == date(2026, 3, 15)
        assert len(day.limits) == 3

    def test_load_missing_day_returns_none(self, domain_root):
        day = repository.load_production_day(date(2026, 4, 1))
        assert day is None

    def test_ensure_production_day_existing(self, domain_root, sample_day):
        day, was_created = repository.ensure_production_day(date(2026, 3, 15))
        assert not was_created
        assert day.delivery_date == date(2026, 3, 15)

    def test_ensure_production_day_creates_new(self, domain_root):
        day, was_created = repository.ensure_production_day(date(2026, 4, 1))
        assert was_created
        assert day.delivery_date == date(2026, 4, 1)
        # Limits should be built from products.json
        assert len(day.limits) == 3
        limit_skus = {lim.sku for lim in day.limits}
        assert "milk_1_5" in limit_skus

    def test_build_production_day_from_products(self, domain_root):
        products = repository.load_products()
        day = repository.build_production_day_from_products(date(2026, 5, 1), products)
        assert day.delivery_date == date(2026, 5, 1)
        assert any(lim.sku == "milk_1_5" and lim.limit == 100 for lim in day.limits)


class TestOrders:
    def test_load_orders_by_date_empty(self, domain_root, sample_day):
        orders = repository.load_orders_by_date(date(2026, 3, 15))
        assert orders == []

    def test_load_orders_by_date_with_order(self, domain_root, sample_day, confirmed_order):
        orders = repository.load_orders_by_date(date(2026, 3, 15))
        assert len(orders) == 1
        assert orders[0].id == "000001"

    def test_next_order_id_first(self, domain_root):
        oid = repository.next_order_id()
        assert oid == "000001"

    def test_next_order_id_increments(self, domain_root, confirmed_order):
        oid = repository.next_order_id()
        assert oid == "000002"

    def test_compute_reserved_empty(self, domain_root, sample_day):
        reserved = repository.compute_reserved(date(2026, 3, 15))
        assert reserved == {}

    def test_compute_reserved_with_confirmed_order(self, domain_root, sample_day, confirmed_order):
        reserved = repository.compute_reserved(date(2026, 3, 15))
        assert reserved["milk_1_5"] == 30
        assert reserved["kefir_1"] == 10

    def test_compute_reserved_ignores_cancelled(self, domain_root, sample_day, tmp_path):
        """Cancelled orders must not count toward reserved."""
        from skills.limiter.domain import OrderRecord, OrderItemRecord
        cancelled = OrderRecord(
            id="000099",
            delivery_date=date(2026, 3, 15),
            status=OrderStatus.Cancelled,
            items=[
                OrderItemRecord(sku="milk_1_5", requested_qty=50, accepted_qty=50,
                                price=65.0, line_total=3250.0),
            ],
        )
        import skills.limiter.manifest as mf
        path = Path(mf.ORDERS_DIR) / "order_000099.json"
        path.write_text(json.dumps(cancelled.model_dump(mode="json")), encoding="utf-8")

        reserved = repository.compute_reserved(date(2026, 3, 15))
        assert reserved.get("milk_1_5", 0) == 0


# ---------------------------------------------------------------------------
# Alias index tests (v1.1)
# ---------------------------------------------------------------------------


class TestBuildAliasIndex:
    def test_returns_dict(self, domain_root):
        index = repository.build_alias_index()
        assert isinstance(index, dict)

    def test_known_alias_maps_to_sku(self, domain_root):
        index = repository.build_alias_index()
        # conftest PRODUCTS have aliases: молоко → milk_1_5
        assert index.get("молоко") == "milk_1_5"

    def test_multiple_aliases_for_same_sku(self, domain_root):
        index = repository.build_alias_index()
        assert index.get("молока") == "milk_1_5"
        assert index.get("молочко") == "milk_1_5"

    def test_inactive_product_excluded(self, domain_root):
        """Aliases of inactive products must not appear in the index."""
        import skills.limiter.manifest as mf
        from pathlib import Path
        import json

        # Write an inactive product with an alias
        inactive = Product(
            sku="inactive_sku",
            title="Неактивный",
            price=100.0,
            limit_default=5,
            unit="шт",
            active=False,
            aliases=["неактивный"],
        )
        products_path = Path(mf.PRODUCTS_PATH)
        existing = json.loads(products_path.read_text(encoding="utf-8"))
        existing.append(inactive.model_dump(mode="json"))
        products_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")

        index = repository.build_alias_index()
        assert "неактивный" not in index

    def test_alias_normalised_lowercase(self, domain_root):
        """Index keys must be lowercase (normalised)."""
        index = repository.build_alias_index()
        for key in index:
            assert key == key.lower(), f"Key not lowercase: {key!r}"

    def test_accepts_preloaded_products(self, domain_root):
        """build_alias_index accepts a pre-loaded product list."""
        products = repository.load_products()
        index = repository.build_alias_index(products=products)
        assert "молоко" in index


class TestFindProductByAlias:
    def test_finds_by_exact_alias(self, domain_root):
        p = repository.find_product_by_alias("молоко")
        assert p is not None
        assert p.sku == "milk_1_5"

    def test_finds_by_alias_case_insensitive(self, domain_root):
        p = repository.find_product_by_alias("МОЛОКО")
        assert p is not None
        assert p.sku == "milk_1_5"

    def test_returns_none_for_unknown(self, domain_root):
        p = repository.find_product_by_alias("несуществующий")
        assert p is None

    def test_multi_word_alias(self, domain_root):
        p = repository.find_product_by_alias("сливочное масло")
        assert p is not None
        assert p.sku == "butter_72"

    def test_accepts_prebuilt_index(self, domain_root):
        index = repository.build_alias_index()
        p = repository.find_product_by_alias("кефир", alias_index=index)
        assert p is not None
        assert p.sku == "kefir_1"


class TestResolveProductToken:
    def test_resolves_by_sku(self, domain_root):
        p = repository.resolve_product_token("milk_1_5")
        assert p is not None
        assert p.sku == "milk_1_5"

    def test_resolves_by_alias(self, domain_root):
        p = repository.resolve_product_token("молоко")
        assert p is not None
        assert p.sku == "milk_1_5"

    def test_returns_none_for_unknown(self, domain_root):
        p = repository.resolve_product_token("неизвестно")
        assert p is None

    def test_sku_takes_priority_over_alias(self, domain_root):
        """If a token matches both a SKU and an alias, SKU wins."""
        # milk_1_5 is a valid SKU — should resolve directly
        p = repository.resolve_product_token("milk_1_5")
        assert p is not None
        assert p.sku == "milk_1_5"
