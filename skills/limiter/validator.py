"""
Limiter validator — checks OrderDraft before capacity check.

Returns a list of error strings (empty = valid).
No side effects.
"""

from __future__ import annotations

from datetime import date

from skills.limiter.domain import OrderDraft, Product


def validate_draft(
    draft: OrderDraft,
    known_products: dict[str, Product],
) -> list[str]:
    """Validate an OrderDraft against the product catalogue.

    Args:
        draft: The order draft to validate.
        known_products: Mapping of sku → Product from the repository.

    Returns:
        List of human-readable error strings. Empty list means valid.
    """
    errors: list[str] = []

    # Date must be present (always is, since it's a required field, but guard anyway)
    if draft.delivery_date is None:
        errors.append("Дата доставки не указана.")

    # Items must not be empty
    if not draft.items:
        errors.append("Список товаров пуст — укажите хотя бы один SKU и количество.")

    for item in draft.items:
        # SKU must exist in catalogue
        product = known_products.get(item.sku)
        if product is None:
            errors.append(f"Неизвестный SKU: '{item.sku}'.")
            continue

        # Product must be active
        if not product.active:
            errors.append(f"SKU '{item.sku}' ({product.title}) неактивен.")

        # Quantity must be positive
        if item.requested_qty <= 0:
            errors.append(
                f"SKU '{item.sku}': количество должно быть больше 0 "
                f"(получено {item.requested_qty})."
            )

    return errors
