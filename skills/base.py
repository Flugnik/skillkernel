"""
BaseSkill — abstract contract for all pluggable domain skills.

Every skill must:
  1. Declare metadata (name, version, description, examples).
  2. Implement score() — return a float in [0.0, 1.0] indicating relevance.
  3. Implement handle() — return a SkillResult (with an ActionPlan if ready).

Skills MUST NOT produce side effects. They only return data.
Side effects are handled by ActionExecutor after user confirmation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import IncomingEvent, SkillContext, SkillResult


class BaseSkill(ABC):
    """Abstract base class for all SkillKernel domain skills."""

    #: Unique identifier used for routing and registration.
    name: str

    #: Semantic version string, e.g. "0.1.0".
    version: str

    #: Human-readable description of what this skill handles.
    description: str

    #: Example phrases that would trigger this skill (for documentation).
    examples: list[str]

    @abstractmethod
    def score(self, event: IncomingEvent) -> float:
        """Return a relevance score in [0.0, 1.0] for the given event.

        Higher score = more confident this skill should handle the event.
        Must not raise exceptions — return 0.0 on any internal error.
        """

    @abstractmethod
    def handle(self, ctx: SkillContext) -> SkillResult:
        """Process the event and return a SkillResult.

        Must NOT produce side effects (no file writes, no network calls).
        Return an ActionPlan describing what should happen; the executor
        will carry it out after optional user confirmation.
        """

    def __repr__(self) -> str:
        return f"<Skill name={self.name!r} version={self.version!r}>"
