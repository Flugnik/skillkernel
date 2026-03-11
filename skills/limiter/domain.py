"""
Limiter domain models — all Pydantic, no side effects.

These are the canonical data structures for the limiter skill.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OrderStatus(str, Enum):
    Draft = "Draft"
    NeedsConfirmLimit = "NeedsConfirmLimit"
    Confirmed = "Confirmed"
    Written = "Written"
    Cancelled = "Cancelled"


class OverlimitMode(str, Enum):
    force_negative = "force_negative"
    accept_free_only = "accept_free_only"
    move_date = "move_date"
    cancel = "cancel"


class LimitCheckStatus(str, Enum):
    ok = "ok"
    over_limit = "over_limit"


# ---------------------------------------------------------------------------
# Product catalogue
# ---------------------------------------------------------------------------


class Product(BaseModel):
    sku: str
    title: str
    price: float
    limit_default: int
    unit: str
    active: bool = True
    group: Optional[str] = None
    aliases: list[str] = []


# ---------------------------------------------------------------------------
# Order drafts (input structures, not persisted)
# ---------------------------------------------------------------------------


class OrderItemDraft(BaseModel):
    sku: str
    requested_qty: int


class OrderDraft(BaseModel):
    delivery_date: date
    client_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    items: list[OrderItemDraft]
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Order records (persisted)
# ---------------------------------------------------------------------------


class OrderItemRecord(BaseModel):
    sku: str
    requested_qty: int
    accepted_qty: int
    price: float
    line_total: float


class OverlimitResolution(BaseModel):
    mode: OverlimitMode
    new_date: Optional[date] = None


class OrderRecord(BaseModel):
    id: str
    delivery_date: date
    client_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    status: OrderStatus
    note: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    items: list[OrderItemRecord]
    overlimit_resolution: Optional[OverlimitResolution] = None


# ---------------------------------------------------------------------------
# Production day
# ---------------------------------------------------------------------------


class ProductionDayLimit(BaseModel):
    sku: str
    limit: int


class ProductionDay(BaseModel):
    delivery_date: date
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    limits: list[ProductionDayLimit]


# ---------------------------------------------------------------------------
# Capacity check
# ---------------------------------------------------------------------------


class LimitCheckItem(BaseModel):
    sku: str
    title: str
    unit: str
    limit: int
    reserved: int
    free: int
    requested: int
    shortage: int  # max(0, requested - free)


class LimitCheckResult(BaseModel):
    status: LimitCheckStatus
    items: list[LimitCheckItem]

    @property
    def over_limit_items(self) -> list[LimitCheckItem]:
        return [i for i in self.items if i.shortage > 0]
