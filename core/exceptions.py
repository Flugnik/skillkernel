"""
Custom exceptions for SkillKernel core.
"""


class SkillKernelError(Exception):
    """Base exception for all SkillKernel errors."""


class SkillNotFoundError(SkillKernelError):
    """Raised when a requested skill is not registered."""

    def __init__(self, skill_name: str) -> None:
        super().__init__(f"Skill not found: '{skill_name}'")
        self.skill_name = skill_name


class SkillAlreadyRegisteredError(SkillKernelError):
    """Raised when attempting to register a skill with a duplicate name."""

    def __init__(self, skill_name: str) -> None:
        super().__init__(f"Skill already registered: '{skill_name}'")
        self.skill_name = skill_name


class PlanNotFoundError(SkillKernelError):
    """Raised when a pending plan cannot be found by plan_id."""

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Pending plan not found: '{plan_id}'")
        self.plan_id = plan_id


class PlanExpiredError(SkillKernelError):
    """Raised when a pending plan has exceeded its TTL."""

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Plan has expired: '{plan_id}'")
        self.plan_id = plan_id


class ExecutorNotFoundError(SkillKernelError):
    """Raised when no executor is registered for a given action type."""

    def __init__(self, action_type: str) -> None:
        super().__init__(f"No executor registered for action type: '{action_type}'")
        self.action_type = action_type


class RoutingError(SkillKernelError):
    """Raised when routing cannot produce a usable decision."""
