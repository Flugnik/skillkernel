"""
Limiter skill — example phrases for documentation and testing.
"""

EXAMPLES = [
    # Create order — ISO date
    "2026-03-15 milk_1_5 12",
    "2026-03-15 milk_1_5 12 kefir_1 6",
    # Create order — dot date
    "15.03 milk_1_5 20",
    "15.03.2026 milk_3_2 10 sour_cream_20 5",
    # Create order — Russian date
    "на 15 марта milk_1_5 12",
    "15 марта Ирина milk_1_5 12 kefir_1 6",
    # Summary
    "/summary 2026-03-15",
    "summary 2026-03-15",
    "сводка на 2026-03-15",
    # Days load
    "/days",
    "days",
    "загрузка по датам",
    # Export
    "/export 2026-03-15",
    "export 2026-03-15",
]
