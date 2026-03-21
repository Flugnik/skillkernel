"""Demo skill implementation."""

from __future__ import annotations

from core.models import IncomingEvent, SkillContext, SkillResult, SkillStatus
from skills.base import BaseSkill
from skills.demo_skill.manifest import (
    SKILL_DESCRIPTION,
    SKILL_EXAMPLES,
    SKILL_NAME,
    SKILL_VERSION,
    TRIGGER_KEYWORDS,
)


class DemoSkill(BaseSkill):
    name = SKILL_NAME
    version = SKILL_VERSION
    description = SKILL_DESCRIPTION
    examples = SKILL_EXAMPLES

    def score(self, event: IncomingEvent) -> float:
        text = event.text.lower()
        return 1.0 if any(keyword in text for keyword in TRIGGER_KEYWORDS) else 0.0

    def handle(self, ctx: SkillContext) -> SkillResult:
        return SkillResult(
            status=SkillStatus.informational,
            plan=None,
            clarification_message=f"[DemoSkill] {ctx.event.text}",
        )
