"""
Capacity engine — checks order drafts against production day limits.

Pure computation: reads domain state, returns LimitCheckResult.
No side effects.
"""

from __future__ import annotations

from skills.limiter.domain import (
    LimitCheckItem,
    LimitCheckResult,
    LimitCheckStatus,
    OrderDraft,
    Product,
    ProductionDay,
)
from skills.limiter import repository


def check_order(
    draft: OrderDraft,
    day: ProductionDay,
    products: dict[str, Product],
) -> LimitCheckResult:
    """Check whether the draft fits within the production day limits.

    Args:
        draft: The order draft with requested quantities.
        day: The production day with per-SKU limits.
        products: Product catalogue keyed by SKU.

    Returns:
        LimitCheckResult with status ok or over_limit.
    """
    # Build limit lookup from production day
    limits_by_sku: dict[str, int] = {
        lim.sku: lim.limit for lim in day.limits
    }

    # Compute reserved from existing confirmed/written orders
    reserved_by_sku: dict[str, int] = repository.compute_reserved(draft.delivery_date)

    items: list[LimitCheckItem] = []
    has_shortage = False

    for item_draft in draft.items:
        sku = item_draft.sku
        product = products.get(sku)
        if product is None:
            # Should have been caught by validator, but be defensive
            continue

        limit = limits_by_sku.get(sku, 0)
        reserved = reserved_by_sku.get(sku, 0)
        free = max(0, limit - reserved)
        requested = item_draft.requested_qty
        shortage = max(0, requested - free)

        if shortage > 0:
            has_shortage = True

        items.append(LimitCheckItem(
            sku=sku,
            title=product.title,
            unit=product.unit,
            limit=limit,
            reserved=reserved,
            free=free,
            requested=requested,
            shortage=shortage,
        ))

    status = LimitCheckStatus.over_limit if has_shortage else LimitCheckStatus.ok
    return LimitCheckResult(status=status, items=items)
