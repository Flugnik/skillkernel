"""
FarmGuardian skill manifest — static metadata declaration.
"""

SKILL_NAME = "farm_guardian"
SKILL_VERSION = "0.1.0"
SKILL_DESCRIPTION = (
    "Handles farm observation records: animals, weather, protocols, journals. "
    "Writes entries to the farm guardian journal log."
)
SKILL_EXAMPLES = [
    "Маша сегодня хорошо поела",
    "Плюша отелилась, записать в журнал",
    "Погода: -5, снег, коровы в стойле",
    "Протокол наблюдения за телёнком",
    "Записать в журнал: корова заболела",
]

# Keywords that raise the score for this skill
TRIGGER_KEYWORDS: frozenset[str] = frozenset({
    "маша", "плюша", "корова", "коровы", "теленок", "телёнок",
    "журнал", "протокол", "погода", "наблюдение", "стойло",
    "отелилась", "отёл", "ферма",
})

# Output path for journal entries
JOURNAL_PATH = "memory/domains/farm_guardian/journal.log"
