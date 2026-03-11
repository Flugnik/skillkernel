"""
Limiter repository — file-based storage layer.

All reads are pure (return domain objects).
All writes return the data dict to be passed to executor actions —
the repository itself does NOT write files directly.

Exception: load_* methods read existing files (read-only side effect,
acceptable for a skill that must read domain state).

NOTE: All path lookups go through the manifest module at call time
(not at import time) so that tests can monkeypatch manifest constants.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from skills.limiter.domain import (
    OrderRecord,
    OrderStatus,
    Product,
    ProductionDay,
    ProductionDayLimit,
)
import skills.limiter.manifest as _mf


# ---------------------------------------------------------------------------
# Internal helpers — read manifest paths at call time
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _day_path(delivery_date: date) -> Path:
    return Path(_mf.PRODUCTION_DAYS_DIR) / f"{delivery_date.isoformat()}.json"


def _order_path(order_id: str) -> Path:
    return Path(_mf.ORDERS_DIR) / f"order_{order_id}.json"


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


def load_products() -> list[Product]:
    """Load all products from products.json."""
    path = Path(_mf.PRODUCTS_PATH)
    if not path.exists():
        return []
    raw = _read_json(path)
    return [Product.model_validate(p) for p in raw]  # type: ignore[arg-type]


def get_product(sku: str) -> Optional[Product]:
    """Return a single product by SKU, or None if not found."""
    for p in load_products():
        if p.sku == sku:
            return p
    return None


def products_by_sku() -> dict[str, Product]:
    """Return all active products keyed by SKU."""
    return {p.sku: p for p in load_products() if p.active}


def build_alias_index(products: Optional[list[Product]] = None) -> dict[str, str]:
    """Build a mapping of normalised alias → sku for all active products.

    The index is keyed by the *normalised* alias (lowercase, ё→е, collapsed
    whitespace) so callers can look up with the same normalisation applied to
    user input.

    Args:
        products: Optional pre-loaded product list. If None, loads from disk.

    Returns:
        Dict mapping normalised_alias → sku.
    """
    from skills.limiter.parser import _normalize_alias  # local import to avoid circular

    if products is None:
        products = load_products()

    index: dict[str, str] = {}
    for product in products:
        if not product.active:
            continue
        for alias in product.aliases:
            key = _normalize_alias(alias)
            if key:
                index[key] = product.sku
    return index


def find_product_by_alias(
    text_fragment: str,
    alias_index: Optional[dict[str, str]] = None,
) -> Optional[Product]:
    """Find a product whose alias matches the given text fragment exactly.

    Uses normalised comparison (lowercase, ё→е, collapsed whitespace).

    Args:
        text_fragment: A piece of user text to look up.
        alias_index: Pre-built alias index. If None, builds one from disk.

    Returns:
        Matching Product or None.
    """
    from skills.limiter.parser import _normalize_alias  # local import to avoid circular

    if alias_index is None:
        alias_index = build_alias_index()

    key = _normalize_alias(text_fragment)
    sku = alias_index.get(key)
    if sku is None:
        return None
    return get_product(sku)


def resolve_product_token(token: str) -> Optional[Product]:
    """Resolve a single token to a Product by trying SKU first, then aliases.

    Args:
        token: A raw token from user input (SKU or alias).

    Returns:
        Matching Product or None.
    """
    from skills.limiter.parser import _normalize_alias  # local import to avoid circular

    # Try exact SKU match first
    product = get_product(token)
    if product is not None:
        return product

    # Try alias lookup
    alias_index = build_alias_index()
    key = _normalize_alias(token)
    sku = alias_index.get(key)
    if sku:
        return get_product(sku)

    return None


# ---------------------------------------------------------------------------
# Production days
# ---------------------------------------------------------------------------


def load_production_day(delivery_date: date) -> Optional[ProductionDay]:
    """Load a production day from disk, or None if it doesn't exist."""
    path = _day_path(delivery_date)
    if not path.exists():
        return None
    raw = _read_json(path)
    return ProductionDay.model_validate(raw)


def production_day_data(day: ProductionDay) -> dict:
    """Serialise a ProductionDay to a JSON-compatible dict for executor."""
    return day.model_dump(mode="json")


def build_production_day_from_products(
    delivery_date: date,
    products: list[Product],
) -> ProductionDay:
    """Create a new ProductionDay from the product catalogue defaults."""
    limits = [
        ProductionDayLimit(sku=p.sku, limit=p.limit_default)
        for p in products
        if p.active
    ]
    return ProductionDay(
        delivery_date=delivery_date,
        created_at=datetime.now(tz=timezone.utc),
        limits=limits,
    )


def ensure_production_day(delivery_date: date) -> tuple[ProductionDay, bool]:
    """Return (ProductionDay, was_created).

    If the day file exists, load it.
    If not, build one from products.json (caller must persist via executor).
    """
    existing = load_production_day(delivery_date)
    if existing is not None:
        return existing, False

    products = load_products()
    day = build_production_day_from_products(delivery_date, products)
    return day, True


def production_day_path(delivery_date: date) -> str:
    """Return the file path string for a production day."""
    return str(_day_path(delivery_date))


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def next_order_id() -> str:
    """Generate the next sequential order ID (6-digit zero-padded)."""
    orders_dir = Path(_mf.ORDERS_DIR)
    orders_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(orders_dir.glob("order_*.json"))
    if not existing:
        return "000001"

    last = existing[-1].stem  # e.g. "order_000003"
    last_num = int(last.replace("order_", ""))
    return str(last_num + 1).zfill(6)


def save_order_data(order: OrderRecord) -> dict:
    """Serialise an OrderRecord to a JSON-compatible dict for executor."""
    return order.model_dump(mode="json")


def order_path(order_id: str) -> str:
    """Return the file path string for an order."""
    return str(_order_path(order_id))


def load_orders_by_date(delivery_date: date) -> list[OrderRecord]:
    """Load all orders for a given delivery date."""
    orders_dir = Path(_mf.ORDERS_DIR)
    if not orders_dir.exists():
        return []

    result: list[OrderRecord] = []
    for path in orders_dir.glob("order_*.json"):
        try:
            raw = _read_json(path)
            order = OrderRecord.model_validate(raw)
            if order.delivery_date == delivery_date:
                result.append(order)
        except Exception:  # noqa: BLE001
            continue
    return result


def load_all_production_days() -> list[ProductionDay]:
    """Load all production day files from disk."""
    days_dir = Path(_mf.PRODUCTION_DAYS_DIR)
    if not days_dir.exists():
        return []

    result: list[ProductionDay] = []
    for path in sorted(days_dir.glob("*.json")):
        try:
            raw = _read_json(path)
            result.append(ProductionDay.model_validate(raw))
        except Exception:  # noqa: BLE001
            continue
    return result


# ---------------------------------------------------------------------------
# Reserved calculation (source of truth: accepted_qty on active orders)
# ---------------------------------------------------------------------------

_ACTIVE_STATUSES = {OrderStatus.Confirmed, OrderStatus.Written}


def compute_reserved(delivery_date: date) -> dict[str, int]:
    """Compute reserved qty per SKU for a date from active orders.

    Reserved = sum of accepted_qty for orders with status Confirmed or Written.
    """
    orders = load_orders_by_date(delivery_date)
    reserved: dict[str, int] = {}
    for order in orders:
        if order.status not in _ACTIVE_STATUSES:
            continue
        for item in order.items:
            reserved[item.sku] = reserved.get(item.sku, 0) + item.accepted_qty
    return reserved
