"""Runtime contracts used by the CLI adapter and handler."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CoreEvent(BaseModel):
    """Normalized user input flowing into the runtime."""

    text: str
    meta: dict[str, Any] = Field(default_factory=dict)


class ConfirmationRequest(BaseModel):
    """Active confirmation context for a follow-up reply."""

    plan_id: str
    plan_event_id: str
    skill_name: str
    source: str = "telegram"


class CoreResult(BaseModel):
    """Normalized runtime output returned to adapters."""

    type: str
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)

