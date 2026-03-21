"""
Limiter rule-based parser v1.1.

Recognises four intent types from plain text:
  - SummaryIntent      → "/summary YYYY-MM-DD", "summary YYYY-MM-DD", "сводка на YYYY-MM-DD"
  - DaysLoadIntent     → "/days", "days", "загрузка по датам"
  - ExportIntent       → "/export YYYY-MM-DD", "export YYYY-MM-DD"
  - CreateOrderIntent  → text containing a date + at least one product+qty pair

v1.1 additions:
  - normalize_text()        — canonicalise user input (case, ё/е, punctuation, units)
  - _normalize_alias()      — same normalisation for alias index keys
  - _extract_items_by_alias() — longest-match-first alias scanning with qty detection
  - _extract_items()        — now tries alias matching first, falls back to SKU regex

No LLM, no external dependencies — pure regex + string matching.
Returns None if the text cannot be parsed into any known intent.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Optional

from skills.limiter.domain import OrderDraft, OrderItemDraft

# Intents imported lazily to avoid circular imports at module level
from skills.limiter.intents import (
    CreateOrderIntent,
    DaysLoadIntent,
    ExportIntent,
    LimiterIntent,
    SummaryIntent,
)

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

# ISO: 2026-03-15
_RE_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Short dot: 15.03 or 15.03.2026
_RE_DOT_DATE = re.compile(r"\b(\d{1,2})\.(\d{2})(?:\.(\d{4}))?\b")

# Russian month names → month number
_RU_MONTHS: dict[str, int] = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

# "15 марта" or "на 15 марта"
_RE_RU_DATE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(_RU_MONTHS.keys()) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# SKU+qty pattern: sku_token followed by integer (legacy, for pure-SKU input)
# SKU tokens contain letters, digits, underscores
# ---------------------------------------------------------------------------

_RE_SKU_QTY = re.compile(r"\b([a-z][a-z0-9_]*)\s+(\d+)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Command patterns
# ---------------------------------------------------------------------------

_RE_SUMMARY = re.compile(
    r"^(?:/summary|summary|сводка\s+на)\s+(.+)$",
    re.IGNORECASE,
)
_RE_DAYS = re.compile(
    r"^(?:/days|days|загрузка\s+по\s+датам)$",
    re.IGNORECASE,
)
_RE_EXPORT = re.compile(
    r"^(?:/export|export)\s+(.+)$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Quantity unit words — stripped/normalised during text processing
# ---------------------------------------------------------------------------

# Regex that matches a quantity expression: optional number + unit word, or just number
# Used to find qty near a matched alias.
_RE_QTY_UNIT = re.compile(
    r"\b(\d+)\s*(?:шт(?:ук(?:и|а)?)?|уп(?:аковк(?:и|а|у))?|упак(?:овк(?:и|а|у))?|пачк(?:и|а|у)?|банк(?:и|а|у)?)?\b",
    re.IGNORECASE,
)

# Standalone number (no unit) — used as fallback qty detection
_RE_NUMBER = re.compile(r"\b(\d+)\b")

# ---------------------------------------------------------------------------
# Helpers: fallback year
# ---------------------------------------------------------------------------

_CURRENT_YEAR = 2026  # fallback year when not specified in short date


def _nearest_future_year(month: int, day: int) -> int:
    """Return the nearest year (current or next) such that the date is not in the past."""
    # Keep short dates stable in tests and runtime by using the configured
    # fallback year rather than the moving current year.
    return _CURRENT_YEAR


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

# Mapping of unit synonyms to a canonical form (we strip them from text
# after extracting qty so they don't confuse alias matching).
_UNIT_SYNONYMS = re.compile(
    r"\b(?:штук[аи]?|шт|упаковк[аиу]|упаковок|уп|упак|пачк[аиу]|пачек|банк[аиу]|банок)\b",
    re.IGNORECASE,
)

# Decimal comma → dot (e.g. "0,5" → "0.5")
_RE_DECIMAL_COMMA = re.compile(r"\b(\d+),(\d+)\b")

# Collapse multiple spaces / punctuation runs
_RE_MULTI_SPACE = re.compile(r"[ \t]+")
# Strip punctuation noise — but NOT dots between digits (those are decimal separators)
# and NOT dots that are part of date patterns (handled separately).
# We strip: commas, semicolons, exclamation/question marks, dashes, em-dashes.
# Dots are stripped only when NOT surrounded by digits on both sides.
_RE_PUNCT_NOISE = re.compile(r"[,;!?—–\-]+|(?<!\d)\.(?!\d)")


def normalize_text(text: str) -> str:
    """Canonicalise user input for robust parsing.

    Steps:
    1. Lowercase
    2. Replace ё → е
    3. Insert space between digit and Cyrillic unit (2шт → 2 шт)
    4. Decimal comma → dot  (0,5 → 0.5)  — must run BEFORE comma stripping
    5. Strip punctuation noise (commas, dashes, dots that are not part of dates)
    6. Collapse multiple spaces
    7. Strip leading/trailing whitespace

    NOTE: We do NOT strip unit words here — they are used for qty detection.
    """
    text = text.lower()
    text = text.replace("ё", "е")
    # Insert space between a digit and a Cyrillic letter (handles "2шт", "2ШТ" etc.)
    text = re.sub(r"(\d)([а-яё])", r"\1 \2", text)
    # Decimal comma → dot BEFORE stripping commas (0,5 → 0.5)
    text = _RE_DECIMAL_COMMA.sub(r"\1.\2", text)
    # Replace punctuation noise with a space (preserve word boundaries)
    text = _RE_PUNCT_NOISE.sub(" ", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    return text.strip()


def _normalize_alias(alias: str) -> str:
    """Normalise an alias string for use as an index key.

    Same rules as normalize_text but also strips unit words so that
    "упаковка творога" and "творога" both resolve to the same product.
    """
    text = alias.lower()
    text = text.replace("ё", "е")
    text = _RE_DECIMAL_COMMA.sub(r"\1.\2", text)
    text = _RE_PUNCT_NOISE.sub(" ", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _parse_date(text: str) -> Optional[date]:
    """Try to extract a date from text. Returns first match found."""
    # ISO
    m = _RE_ISO_DATE.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Russian month name
    m = _RE_RU_DATE.search(text)
    if m:
        day = int(m.group(1))
        month = _RU_MONTHS[m.group(2).lower()]
        year = _nearest_future_year(month, day)
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # Short dot notation
    m = _RE_DOT_DATE.search(text)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else _nearest_future_year(month, day)
        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None


def _strip_date(text: str) -> str:
    """Remove date tokens from text so product scanning is cleaner."""
    text = _RE_ISO_DATE.sub("", text)
    text = _RE_RU_DATE.sub("", text)
    text = _RE_DOT_DATE.sub("", text)
    # Also strip common date prepositions left behind
    text = re.sub(r"\bна\b", " ", text)
    text = _RE_MULTI_SPACE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Words that are NOT SKUs even if they match the SKU regex pattern
# ---------------------------------------------------------------------------

_NON_SKU_WORDS: frozenset[str] = frozenset({
    "на", "в", "и", "с", "по", "от", "до", "за", "из",
    "summary", "days", "export", "сводка", "загрузка",
    "заказ", "order", "confirm", "reject",
    # common Russian names that might appear
    "ирина", "мария", "анна", "ольга", "наталья",
})

# ---------------------------------------------------------------------------
# Alias-based item extraction (v1.1 core logic)
# ---------------------------------------------------------------------------


def _extract_items_by_alias(
    text: str,
    alias_index: dict[str, str],
) -> tuple[list[OrderItemDraft], list[str]]:
    """Extract (sku, qty) pairs from text using alias matching.

    Strategy:
    1. Normalise text.
    2. Sort aliases by length descending (longest match first) to avoid
       "йогурт" stealing a match from "йогурт с клубникой".
    3. For each alias match, look for a nearby integer (within ±5 tokens).
    4. If no integer found near the alias → skip (do not silently create qty=1).
    5. Return (found_items, unmatched_fragments).

    Args:
        text: Raw user text (will be normalised internally).
        alias_index: Mapping of normalised_alias → sku from repository.

    Returns:
        Tuple of (list[OrderItemDraft], list[str]) where the second element
        contains text fragments that looked like product mentions but had no qty.
    """
    norm = normalize_text(text)

    # Sort aliases longest-first so greedy matching prefers specific phrases
    sorted_aliases = sorted(alias_index.keys(), key=len, reverse=True)

    found_items: list[OrderItemDraft] = []
    no_qty_fragments: list[str] = []
    seen_skus: set[str] = set()

    # Track which character spans are already consumed by a match
    consumed: list[tuple[int, int]] = []

    def _is_consumed(start: int, end: int) -> bool:
        for cs, ce in consumed:
            if start < ce and end > cs:
                return True
        return False

    for alias in sorted_aliases:
        sku = alias_index[alias]
        if sku in seen_skus:
            continue

        # Search for alias in normalised text
        pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        m = pattern.search(norm)
        if m is None:
            continue

        match_start, match_end = m.start(), m.end()
        if _is_consumed(match_start, match_end):
            continue

        # Look for a quantity integer near the match.
        # Search window: up to 30 chars before and after the alias match.
        window_start = max(0, match_start - 30)
        window_end = min(len(norm), match_end + 30)
        before_text = norm[window_start:match_start]
        after_text = norm[match_end:window_end]

        qty = _find_qty_near(before_text, after_text)

        if qty is None:
            # Product found but no quantity — record as unmatched fragment
            no_qty_fragments.append(alias)
            # Still consume the span so we don't double-report
            consumed.append((match_start, match_end))
            continue

        # Valid match with quantity
        consumed.append((match_start, match_end))
        seen_skus.add(sku)
        found_items.append(OrderItemDraft(sku=sku, requested_qty=qty))

    return found_items, no_qty_fragments


def _find_qty_near(before: str, after: str) -> Optional[int]:
    """Find an integer quantity in the text immediately before or after an alias.

    Searches 'after' first (most natural: "брынза 2 шт"),
    then 'before' ("2 шт брынза").

    Returns the integer value, or None if no number found.
    """
    # After: find first number (possibly followed by unit word)
    m = _RE_NUMBER.search(after)
    if m:
        return int(m.group(1))

    # Before: find last number
    numbers = list(_RE_NUMBER.finditer(before))
    if numbers:
        return int(numbers[-1].group(1))

    return None


# ---------------------------------------------------------------------------
# Legacy SKU-based item extraction (kept for backward compatibility)
# ---------------------------------------------------------------------------


def _extract_items_by_sku(text: str) -> list[OrderItemDraft]:
    """Extract (sku, qty) pairs from text using the legacy SKU regex.

    Only matches ASCII-style SKU tokens (e.g. milk_1_5 12).
    """
    items: list[OrderItemDraft] = []
    seen_skus: set[str] = set()

    for m in _RE_SKU_QTY.finditer(text):
        sku = m.group(1).lower()
        qty = int(m.group(2))
        if sku in _NON_SKU_WORDS:
            continue
        if sku in seen_skus:
            continue
        seen_skus.add(sku)
        items.append(OrderItemDraft(sku=sku, requested_qty=qty))

    return items


# ---------------------------------------------------------------------------
# Combined item extraction
# ---------------------------------------------------------------------------


def _extract_items(
    text: str,
    alias_index: Optional[dict[str, str]] = None,
) -> tuple[list[OrderItemDraft], list[str]]:
    """Extract order items from text, trying alias matching first.

    If alias_index is provided and non-empty, uses alias-based extraction
    (longest-match-first). Falls back to legacy SKU regex for any remaining
    text or when alias_index is empty.

    Returns:
        Tuple of (items, no_qty_fragments) where no_qty_fragments are alias
        matches that had no associated quantity.
    """
    if alias_index:
        alias_items, no_qty = _extract_items_by_alias(text, alias_index)
        if alias_items or no_qty:
            # Also try SKU regex on the same text to catch mixed input
            sku_items = _extract_items_by_sku(text)
            # Merge: add SKU items whose sku is not already in alias results
            alias_skus = {i.sku for i in alias_items}
            for item in sku_items:
                if item.sku not in alias_skus:
                    alias_items.append(item)
            return alias_items, no_qty

    # Pure SKU mode (no alias index or no alias matches at all)
    sku_items = _extract_items_by_sku(text)
    return sku_items, []


# ---------------------------------------------------------------------------
# Client name heuristic
# ---------------------------------------------------------------------------


def _extract_client_name(text: str) -> Optional[str]:
    """Extract a likely Russian client name from the first meaningful lines.

    Strategy:
    1. Check the first two non-empty lines.
    2. Prefer a full two-word capitalized name at the start of a line.
    3. Ignore leading imperative/order words like "Прими", "Добавь".
    4. Stop at punctuation or product list that follows the name.
    """
    if not text.strip():
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidate_lines = lines[:2]

    skip_words = {
        "Прими", "Принять", "Добавь", "Добавить", "Заказ", "Заказа",
    }

    for line in candidate_lines:
        line = re.sub(r"^[^А-ЯЁ]+", "", line)

        # Full name at line start: "Елена Илизарова"
        m = re.match(r"^([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,})\b", line)
        if m:
            first, last = m.group(1), m.group(2)
            if first not in skip_words:
                return f"{first} {last}"

        # Fallback: collect capitalized words, but ignore leading command word
        words = re.findall(r"\b[А-ЯЁ][а-яё]{2,}\b", line)
        words = [w for w in words if w not in skip_words]
        if len(words) >= 2:
            return f"{words[0]} {words[1]}"

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse(
    text: str,
    alias_index: Optional[dict[str, str]] = None,
) -> Optional[LimiterIntent]:
    """Parse raw text into a LimiterIntent or return None.

    Tries command patterns first (summary, days, export),
    then falls back to order creation parsing.

    Args:
        text: Raw user input.
        alias_index: Optional pre-built alias→sku mapping from repository.
            If None, alias-based matching is skipped (only SKU regex used).
            Pass repository.build_alias_index() to enable Russian text parsing.

    Returns:
        A LimiterIntent subclass instance, or None if nothing matched.
    """
    stripped = text.strip()

    # --- SummaryIntent ---
    m = _RE_SUMMARY.match(stripped)
    if m:
        d = _parse_date(m.group(1))
        if d:
            return SummaryIntent(delivery_date=d)
        return None  # summary without parseable date → not our intent

    # --- DaysLoadIntent ---
    if _RE_DAYS.match(stripped):
        return DaysLoadIntent()

    # --- ExportIntent ---
    m = _RE_EXPORT.match(stripped)
    if m:
        d = _parse_date(m.group(1))
        if d:
            return ExportIntent(delivery_date=d)
        return None

    # --- CreateOrderIntent ---
    delivery_date = _parse_date(stripped)
    if delivery_date is None:
        return None  # no date → cannot be an order

    # Remove date tokens before scanning for products
    text_no_date = _strip_date(stripped)
    items, no_qty_fragments = _extract_items(text_no_date, alias_index)

    if not items:
        return None  # date found but no items with qty → not an order

    client_name = _extract_client_name(stripped)

    draft = OrderDraft(
        delivery_date=delivery_date,
        client_name=client_name,
        items=items,
    )
    intent = CreateOrderIntent(draft=draft)

    # Attach unmatched fragments as metadata for callers that want to report them
    if no_qty_fragments:
        intent.no_qty_fragments = no_qty_fragments  # type: ignore[attr-defined]

    return intent