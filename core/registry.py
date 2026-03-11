"""
SkillRegistry — stores and retrieves registered skills by name.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.exceptions import SkillAlreadyRegisteredError, SkillNotFoundError

if TYPE_CHECKING:
    from skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Central registry for all pluggable skills.

    Skills are registered explicitly (no auto-discovery magic).
    """

    def __init__(self) -> None:
        self._skills: dict[str, "BaseSkill"] = {}

    def register(self, skill: "BaseSkill") -> None:
        """Register a skill instance.

        Raises:
            SkillAlreadyRegisteredError: if a skill with the same name is
                already registered.
        """
        name = skill.name
        if name in self._skills:
            raise SkillAlreadyRegisteredError(name)
        self._skills[name] = skill
        logger.info("Registered skill: '%s' v%s", name, skill.version)

    def get(self, skill_name: str) -> "BaseSkill":
        """Return a skill by name.

        Raises:
            SkillNotFoundError: if no skill with that name is registered.
        """
        if skill_name not in self._skills:
            raise SkillNotFoundError(skill_name)
        return self._skills[skill_name]

    def list_skills(self) -> list["BaseSkill"]:
        """Return all registered skills."""
        return list(self._skills.values())

    def __len__(self) -> int:
        return len(self._skills)
