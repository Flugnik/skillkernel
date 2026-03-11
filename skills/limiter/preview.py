"""
Limiter preview layer — formats human-readable text for all skill responses.

All functions are pure: take domain objects, return strings.
No side effects.
"""

from __future__ import annotations

from datetime import date

from skills.limiter.domain import (
    LimitCheckResult,
    OrderDraft,
    ProductionDay,
)


# ---------------------------------------------------------------------------
# Order preview (normal — within limits)
# ---------------------------------------------------------------------------


def format_normal_order_preview(
    draft: OrderDraft,
    check_result: LimitCheckResult,
    day_was_created: bool = False,
) -> str:
    """Format a preview for a normal order (all within limits)."""
    d = draft.delivery_date.isoformat()
    lines = [
        f"[Limiter] Новый заказ на {d}",
    ]
    if draft.client_name:
        lines.append(f"Клиент: {draft.client_name}")

    lines.append("")
    lines.append("Позиции:")
    for item in check_result.items:
        lines.append(f"  {item.title}: {item.requested} {item.unit}")

    total_items = len(draft.items)
    total_units = sum(i.requested_qty for i in draft.items)
    lines += [
        "",
        "Итого:",
        f"  позиций: {total_items}",
        f"  единиц: {total_units}",
        "  лимиты: в пределах нормы",
        "",
        "Важно:",
        "Это пока черновик.",
    ]

    if day_was_created:
        lines.append(
            f"Дата {d} ещё не создана и будет создана только после подтверждения."
        )
        lines.append("Заказ тоже будет сохранён только после подтверждения.")
    else:
        lines.append("Заказ будет сохранён только после подтверждения.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Clarification (overlimit)
# ---------------------------------------------------------------------------


def format_overlimit_clarification(
    draft: OrderDraft,
    check_result: LimitCheckResult,
) -> str:
    """Format a clarification message when the order exceeds limits."""
    d = draft.delivery_date.isoformat()
    lines = [
        f"Обнаружен перегруз по дате {d}.",
        "",
        "Заказ пока не создан.",
        "Сначала нужно выбрать, как поступить с перегрузом.",
        "",
        "Проблемные позиции:",
    ]
    for item in check_result.over_limit_items:
        lines.append(
            f"  {item.title} ({item.sku}): запрошено {item.requested} {item.unit},"
            f" свободно {item.free}, нехватка {item.shortage}"
        )

    lines += [
        "",
        "Варианты:",
        "  - провести заказ полностью, даже если лимит уйдёт в минус",
        "  - принять только свободный объём",
        "  - указать другую дату",
        "  - отменить заказ",
        "",
        "Введите одну из команд:",
        "  force_negative",
        "  accept_free_only",
        "  move_date ГГГГ-ММ-ДД",
        "  cancel",
        "",
        "После выбора решения система подготовит новый черновик для подтверждения.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Force-negative preview
# ---------------------------------------------------------------------------


def format_force_negative_preview(
    draft: OrderDraft,
    check_result: LimitCheckResult,
    day_was_created: bool = False,
) -> str:
    """Format a preview for force_negative resolution."""
    d = draft.delivery_date.isoformat()
    lines = [
        f"[Limiter] Заказ на {d} — принять с перегрузом",
        "",
        "Позиции:",
    ]
    for item in check_result.items:
        flag = "  ⚠ сверх лимита" if item.shortage > 0 else ""
        lines.append(f"  {item.title}: {item.requested} {item.unit}{flag}")

    lines += [
        "",
        "Важно:",
        "Это пока черновик.",
    ]
    if day_was_created:
        lines.append(
            f"Дата {d} ещё не создана и будет создана только после подтверждения."
        )
        lines.append("Заказ тоже будет сохранён только после подтверждения.")
    else:
        lines.append("Заказ будет сохранён только после подтверждения.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Accept-free-only preview
# ---------------------------------------------------------------------------


def format_accept_free_only_preview(
    draft: OrderDraft,
    check_result: LimitCheckResult,
    day_was_created: bool = False,
) -> str:
    """Format a preview for accept_free_only resolution."""
    d = draft.delivery_date.isoformat()
    lines = [
        f"[Limiter] Заказ на {d} — принять только свободный объём",
        "",
        "Позиции:",
    ]
    for item in check_result.items:
        accepted = item.free if item.shortage > 0 else item.requested
        if item.shortage > 0:
            lines.append(
                f"  {item.title}: запрошено {item.requested}, принято {accepted} {item.unit}"
                f"  (урезано из-за перегруза)"
            )
        else:
            lines.append(f"  {item.title}: {item.requested} {item.unit}")

    lines += [
        "",
        "Важно:",
        "Это пока черновик.",
    ]
    if day_was_created:
        lines.append(
            f"Дата {d} ещё не создана и будет создана только после подтверждения."
        )
        lines.append("Заказ тоже будет сохранён только после подтверждения.")
    else:
        lines.append("Заказ будет сохранён только после подтверждения.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def format_summary(
    day: ProductionDay,
    reserved_by_sku: dict[str, int],
) -> str:
    """Format a capacity summary for a production day."""
    lines = [
        f"[Limiter] Сводка на {day.delivery_date.isoformat()}",
        "",
        f"  {'SKU':<20} {'Лимит':>8} {'Резерв':>8} {'Свободно':>10}",
        "  " + "-" * 50,
    ]
    for lim in day.limits:
        reserved = reserved_by_sku.get(lim.sku, 0)
        free = max(0, lim.limit - reserved)
        lines.append(
            f"  {lim.sku:<20} {lim.limit:>8} {reserved:>8} {free:>10}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Days load
# ---------------------------------------------------------------------------


def format_days_load(
    day: ProductionDay,
    reserved_by_sku: dict[str, int],
) -> str:
    """Format a single-line load summary for a production day.

    Load % = total_reserved / total_limit * 100 across all SKUs.
    """
    total_limit = sum(lim.limit for lim in day.limits)
    total_reserved = sum(reserved_by_sku.get(lim.sku, 0) for lim in day.limits)

    if total_limit == 0:
        pct = 0.0
    else:
        pct = total_reserved / total_limit * 100

    bar_len = 20
    filled = int(pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    return (
        f"  {day.delivery_date.isoformat()}  [{bar}] {pct:5.1f}%"
        f"  (резерв {total_reserved} / лимит {total_limit})"
    )
