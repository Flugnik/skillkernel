"""
Shared fixtures for limiter tests.

Uses tmp_path to isolate all file I/O from the real domain storage.
Patches manifest module attributes at call time so repository functions
use tmp_path instead of the real storage.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from skills.limiter.domain import (
    OrderItemRecord,
    OrderRecord,
    OrderStatus,
    Product,
    ProductionDay,
    ProductionDayLimit,
)


# ---------------------------------------------------------------------------
# Sample products (only 3 — used in tests that assert len == 3)
# ---------------------------------------------------------------------------

PRODUCTS = [
    Product(
        sku="milk_1_5",
        title="Молоко 1.5%",
        price=65.0,
        limit_default=100,
        unit="л",
        aliases=["молоко", "молока", "молочко"],
    ),
    Product(
        sku="kefir_1",
        title="Кефир 1%",
        price=70.0,
        limit_default=60,
        unit="л",
        aliases=["кефир", "кефира"],
    ),
    Product(
        sku="butter_72",
        title="Масло 72.5%",
        price=350.0,
        limit_default=20,
        unit="кг",
        aliases=["масло", "масла", "сливочное масло"],
    ),
]

PRODUCTS_BY_SKU: dict[str, Product] = {p.sku: p for p in PRODUCTS}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def domain_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Set up a temporary domain root and patch all manifest path constants
    so repository functions use tmp_path instead of the real storage.

    Writes only the 3 test products to products.json (not the real 6-product file).
    """
    root = tmp_path / "limiter"
    root.mkdir()
    (root / "production_days").mkdir()
    (root / "orders").mkdir()
    (root / "exports").mkdir()

    # Write only the 3 test products
    products_data = [p.model_dump(mode="json") for p in PRODUCTS]
    (root / "products.json").write_text(
        json.dumps(products_data, ensure_ascii=False), encoding="utf-8"
    )

    # Patch manifest constants used by repository (read at call time via _mf)
    import skills.limiter.manifest as mf
    monkeypatch.setattr(mf, "DOMAIN_ROOT", str(root))
    monkeypatch.setattr(mf, "PRODUCTS_PATH", str(root / "products.json"))
    monkeypatch.setattr(mf, "PRODUCTION_DAYS_DIR", str(root / "production_days"))
    monkeypatch.setattr(mf, "ORDERS_DIR", str(root / "orders"))
    monkeypatch.setattr(mf, "EXPORTS_DIR", str(root / "exports"))

    return root


@pytest.fixture()
def sample_day(domain_root: Path) -> ProductionDay:
    """Create and persist a sample production day for 2026-03-15."""
    day = ProductionDay(
        delivery_date=date(2026, 3, 15),
        limits=[
            ProductionDayLimit(sku="milk_1_5", limit=100),
            ProductionDayLimit(sku="kefir_1",  limit=60),
            ProductionDayLimit(sku="butter_72",limit=20),
        ],
    )
    path = domain_root / "production_days" / "2026-03-15.json"
    path.write_text(
        json.dumps(day.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return day


@pytest.fixture()
def confirmed_order(domain_root: Path) -> OrderRecord:
    """Create and persist a confirmed order that consumes some capacity."""
    order = OrderRecord(
        id="000001",
        delivery_date=date(2026, 3, 15),
        status=OrderStatus.Confirmed,
        items=[
            OrderItemRecord(sku="milk_1_5", requested_qty=30, accepted_qty=30,
                            price=65.0, line_total=1950.0),
            OrderItemRecord(sku="kefir_1",  requested_qty=10, accepted_qty=10,
                            price=70.0, line_total=700.0),
        ],
    )
    path = domain_root / "orders" / "order_000001.json"
    path.write_text(
        json.dumps(order.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return order
