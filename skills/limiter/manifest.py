"""
Limiter skill manifest — static metadata for Limiter v1.0.

Production day planner and SKU load limiter.
"""

SKILL_NAME = "limiter"
SKILL_VERSION = "1.0.0"
SKILL_DESCRIPTION = (
    "Production day planner and SKU overload limiter. "
    "Creates orders, checks capacity limits per SKU per date, "
    "shows daily load summary and days-ahead load overview."
)
SKILL_EXAMPLES = [
    "2026-03-15 milk_1_5 12",
    "15.03 Ирина milk_1_5 12 kefir_1 6",
    "на 15 марта milk_1_5 20",
    "/summary 2026-03-15",
    "summary 2026-03-15",
    "сводка на 2026-03-15",
    "/days",
    "days",
    "загрузка по датам",
    "/export 2026-03-15",
    "export 2026-03-15",
]

# Keywords that raise the score for this skill
TRIGGER_KEYWORDS: frozenset[str] = frozenset({
    # command words
    "summary", "сводка", "days", "загрузка", "export", "экспорт",
    # order creation signals
    "заказ", "order", "на", "молоко", "кефир", "сметана", "творог", "масло",
    # sku fragments
    "milk", "kefir", "sour", "cream", "butter", "cottage",
    # date signals
    "марта", "апреля", "мая", "июня", "июля", "августа",
    "сентября", "октября", "ноября", "декабря", "января", "февраля",
    # limiter domain
    "лимит", "свободно", "резерв", "перегруз",
})

# Domain storage root
DOMAIN_ROOT = "memory/domains/limiter"
PRODUCTS_PATH = f"{DOMAIN_ROOT}/products.json"
PRODUCTION_DAYS_DIR = f"{DOMAIN_ROOT}/production_days"
ORDERS_DIR = f"{DOMAIN_ROOT}/orders"
EXPORTS_DIR = f"{DOMAIN_ROOT}/exports"
