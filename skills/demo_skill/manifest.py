
"""Demo skill manifest.

Minimal static metadata matching the existing skill pattern.
"""

SKILL_NAME = "demo_skill"
SKILL_VERSION = "0.1.0"
SKILL_DESCRIPTION = "Minimal demo skill skeleton."
SKILL_EXAMPLES = ["demo skill", "test demo skill"]

TRIGGER_KEYWORDS: frozenset[str] = frozenset({"demo", "demo skill", "/demo"})
