"""
Limiter planner — builds ActionPlans and informational responses.

All methods return either:
  - ActionPlan (for create/confirm flows)
  - str (for informational responses like summary/days load)

No side effects. No file writes here.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from core.models import Action, ActionPlan, ActionType

from skills.limiter.domain import (
    LimitCheckResult,
    OrderDraft,
    OrderItemRecord,
    OrderRecord,
    OrderStatus,
    OverlimitMode,
    OverlimitResolution,
    Product,
)
from skills.limiter import repository
from skills.limiter.manifest import SKILL_NAME


# ---------------------------------------------------------------------------
# Order record builders
# ---------------------------------------------------------------------------


def _build_order_record(
    draft: OrderDraft,
    products: dict[str, Product],
    accepted_qtys: dict[str, int],
    status: OrderStatus,
    resolution: Optional[OverlimitResolution] = None,
) -> OrderRecord:
    """Build an OrderRecord from a draft and accepted quantities."""
    order_id = repository.next_order_id()
    items: list[OrderItemRecord] = []

    for item_draft in draft.items:
        product = products[item_draft.sku]
        accepted = accepted_qtys.get(item_draft.sku, item_draft.requested_qty)
        line_total = round(accepted * product.price, 2)
        items.append(OrderItemRecord(
            sku=item_draft.sku,
            requested_qty=item_draft.requested_qty,
            accepted_qty=accepted,
            price=product.price,
            line_total=line_total,
        ))

    return OrderRecord(
        id=order_id,
        delivery_date=draft.delivery_date,
        client_name=draft.client_name,
        phone=draft.phone,
        address=draft.address,
        status=status,
        note=draft.note,
        items=items,
        overlimit_resolution=resolution,
    )


def _order_to_actions(
    order: OrderRecord,
    day_was_created: bool,
    day_data: Optional[dict],
    day_path: Optional[str],
) -> list[Action]:
    """Build the list of executor actions for saving an order (and optionally a new day)."""
    actions: list[Action] = []

    # If production day was just created, persist it first
    if day_was_created and day_data is not None and day_path is not None:
        actions.append(Action(
            action_type=ActionType.ensure_json_file,
            params={
                "path": day_path,
                "default_data": day_data,
            },
        ))

    # Save the order
    actions.append(Action(
        action_type=ActionType.write_json,
        params={
            "path": repository.order_path(order.id),
            "data": repository.save_order_data(order),
        },
    ))

    return actions


# ---------------------------------------------------------------------------
# Normal order plan (all within limits)
# ---------------------------------------------------------------------------


def build_normal_order_plan(
    event_id: str,
    draft: OrderDraft,
    check_result: LimitCheckResult,
    products: dict[str, Product],
    day_was_created: bool,
    day_data: Optional[dict],
    day_path: Optional[str],
    preview_text: str,
) -> ActionPlan:
    """Build an ActionPlan for an order that fits within limits."""
    accepted_qtys = {item.sku: item.requested_qty for item in draft.items}

    order = _build_order_record(
        draft=draft,
        products=products,
        accepted_qtys=accepted_qtys,
        status=OrderStatus.Confirmed,
    )

    actions = _order_to_actions(order, day_was_created, day_data, day_path)

    return ActionPlan(
        skill_name=SKILL_NAME,
        event_id=event_id,
        actions=actions,
        preview_text=preview_text,
        requires_confirmation=True,
    )


# ---------------------------------------------------------------------------
# Overlimit resolution plans
# ---------------------------------------------------------------------------


def build_force_negative_plan(
    event_id: str,
    draft: OrderDraft,
    check_result: LimitCheckResult,
    products: dict[str, Product],
    day_was_created: bool,
    day_data: Optional[dict],
    day_path: Optional[str],
    preview_text: str,
) -> ActionPlan:
    """Build a plan accepting full requested qty even if over limit."""
    accepted_qtys = {item.sku: item.requested_qty for item in draft.items}
    resolution = OverlimitResolution(mode=OverlimitMode.force_negative)

    order = _build_order_record(
        draft=draft,
        products=products,
        accepted_qtys=accepted_qtys,
        status=OrderStatus.Confirmed,
        resolution=resolution,
    )

    actions = _order_to_actions(order, day_was_created, day_data, day_path)

    return ActionPlan(
        skill_name=SKILL_NAME,
        event_id=event_id,
        actions=actions,
        preview_text=preview_text,
        requires_confirmation=True,
    )


def build_accept_free_only_plan(
    event_id: str,
    draft: OrderDraft,
    check_result: LimitCheckResult,
    products: dict[str, Product],
    day_was_created: bool,
    day_data: Optional[dict],
    day_path: Optional[str],
    preview_text: str,
) -> ActionPlan:
    """Build a plan accepting only the free (non-overloaded) quantity per SKU."""
    # accepted_qty = min(requested, free) per item
    free_by_sku = {item.sku: item.free for item in check_result.items}
    accepted_qtys = {
        item.sku: min(item.requested_qty, free_by_sku.get(item.sku, item.requested_qty))
        for item in draft.items
    }
    resolution = OverlimitResolution(mode=OverlimitMode.accept_free_only)

    order = _build_order_record(
        draft=draft,
        products=products,
        accepted_qtys=accepted_qtys,
        status=OrderStatus.Confirmed,
        resolution=resolution,
    )

    actions = _order_to_actions(order, day_was_created, day_data, day_path)

    return ActionPlan(
        skill_name=SKILL_NAME,
        event_id=event_id,
        actions=actions,
        preview_text=preview_text,
        requires_confirmation=True,
    )


# ---------------------------------------------------------------------------
# Informational responses (no ActionPlan needed)
# ---------------------------------------------------------------------------


def build_summary_response(delivery_date: date) -> str:
    """Build a text summary of capacity for a given date."""
    from skills.limiter.preview import format_summary
    day = repository.load_production_day(delivery_date)
    if day is None:
        return (
            f"Производственный день {delivery_date.isoformat()} не создан.\n"
            f"Создайте первый заказ на эту дату, чтобы инициализировать день."
        )
    reserved_by_sku = repository.compute_reserved(delivery_date)
    return format_summary(day, reserved_by_sku)


def build_days_load_response(days_ahead: int = 14) -> str:
    """Build a text overview of load across upcoming production days."""
    from skills.limiter.preview import format_days_load
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)

    all_days = repository.load_all_production_days()
    upcoming = [d for d in all_days if today <= d.delivery_date <= cutoff]
    upcoming.sort(key=lambda d: d.delivery_date)

    if not upcoming:
        return "Нет производственных дней в ближайшие {} дней.".format(days_ahead)

    lines: list[str] = []
    for day in upcoming:
        reserved_by_sku = repository.compute_reserved(day.delivery_date)
        lines.append(format_days_load(day, reserved_by_sku))

    return "\n".join(lines)
