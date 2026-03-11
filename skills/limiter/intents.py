"""
Limiter intent dataclasses.

Each intent represents a parsed, typed user request.
Intents are pure data — no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from skills.limiter.domain import OrderDraft, OverlimitMode, OverlimitResolution


@dataclass
class CreateOrderIntent:
    """User wants to create a new order for a delivery date."""
    draft: OrderDraft


@dataclass
class SummaryIntent:
    """User wants a capacity summary for a specific date."""
    delivery_date: date


@dataclass
class DaysLoadIntent:
    """User wants an overview of load across upcoming days."""
    days_ahead: int = 14


@dataclass
class ExportIntent:
    """User wants to export data for a specific date."""
    delivery_date: date


@dataclass
class OverlimitResolutionIntent:
    """User has chosen how to resolve an overlimit situation.

    This intent is produced when the user responds to a clarification_required
    result with a resolution choice. The original draft is re-attached so the
    planner can build the final ActionPlan without re-parsing.
    """
    draft: OrderDraft
    resolution: OverlimitResolution


# Union type for type hints
LimiterIntent = (
    CreateOrderIntent
    | SummaryIntent
    | DaysLoadIntent
    | ExportIntent
    | OverlimitResolutionIntent
)
