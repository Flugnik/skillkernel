"""
Core Pydantic models for SkillKernel dispatcher.

All data flowing through the system is typed via these models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RoutingStatus(str, Enum):
    """Result of routing an incoming event."""

    matched = "matched"
    ambiguous = "ambiguous"
    unknown = "unknown"


class SkillStatus(str, Enum):
    """Status returned by a skill after handling an event."""

    plan_ready = "plan_ready"
    clarification_needed = "clarification_needed"
    clarification_required = "clarification_required"
    informational = "informational"
    rejected = "rejected"
    error = "error"


class ActionType(str, Enum):
    """Supported action types for the executor."""

    write_markdown = "write_markdown"
    write_json = "write_json"
    ensure_json_file = "ensure_json_file"
    noop = "noop"
    write_xlsx_export = "write_xlsx_export"


# ---------------------------------------------------------------------------
# Incoming event
# ---------------------------------------------------------------------------


class IncomingEvent(BaseModel):
    """Represents a raw user input arriving at the dispatcher."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    source: str = "cli"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfirmationRequest(BaseModel):
    """Pending confirmation context attached to a follow-up user reply."""

    plan_id: str
    plan_event_id: str
    skill_name: str
    confirmation_type: str = "plan"


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class DispatchDecision(BaseModel):
    """Result of routing an IncomingEvent through registered skills."""

    event_id: str
    status: RoutingStatus
    matched_skill: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    message: str = ""


# ---------------------------------------------------------------------------
# Skill context & result
# ---------------------------------------------------------------------------


class SkillContext(BaseModel):
    """Context passed to a skill's handle() method."""

    event: IncomingEvent
    decision: DispatchDecision


class Action(BaseModel):
    """A single executable action inside an ActionPlan."""

    action_type: ActionType
    params: dict[str, Any] = Field(default_factory=dict)


class ActionPlan(BaseModel):
    """A plan produced by a skill, containing one or more actions."""

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str
    event_id: str
    actions: list[Action]
    preview_text: str
    requires_confirmation: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    ttl_seconds: int = 300


class SkillResult(BaseModel):
    """Result returned by a skill after processing a SkillContext."""

    status: SkillStatus
    plan: ActionPlan | None = None
    clarification_message: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class ExecutionResult(BaseModel):
    """Result of executing an ActionPlan."""

    plan_id: str
    success: bool
    executed_actions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
