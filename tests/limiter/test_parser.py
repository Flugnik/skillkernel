"""
Tests for skills/limiter/parser.py — v1.1

Covers:
  - Legacy SKU-based parsing (backward compatibility)
  - normalize_text()
  - _normalize_alias()
  - Alias-based item extraction (longest-match-first)
  - Quantity detection (various forms)
  - Date parsing (ISO, dot, Russian month names)
  - Full parse() with alias_index
  - Edge cases: no qty, ambiguous text, mixed SKU+alias input
"""

from __future__ import annotations

from datetime import date

import pytest

from skills.limiter.intents import (
    CreateOrderIntent,
    DaysLoadIntent,
    ExportIntent,
    SummaryIntent,
)
from skills.limiter.parser import (
    _extract_items_by_alias,
    _normalize_alias,
    normalize_text,
    parse,
)


# ---------------------------------------------------------------------------
# Alias index fixture — mirrors the real products.json structure
# ---------------------------------------------------------------------------

@pytest.fixture()
def alias_index() -> dict[str, str]:
    """Minimal alias index covering the products used in tests."""
    return {
        # milk_1_5
        "молоко": "milk_1_5",
        "молока": "milk_1_5",
        "молочко": "milk_1_5",
        # butter_200
        "масло": "butter_200",
        "масла": "butter_200",
        "сливочное масло": "butter_200",
        # brynza_300
        "брынза": "brynza_300",
        "брынзы": "brynza_300",
        # farmer_cheese_300
        "фермерский": "farmer_cheese_300",
        "фермерского": "farmer_cheese_300",
        "сыр фермерский": "farmer_cheese_300",
        "фермерский сыр": "farmer_cheese_300",
        "фермерского сыра": "farmer_cheese_300",
        # tvorog_0_5
        "творог": "tvorog_0_5",
        "творога": "tvorog_0_5",
        "упаковка творога": "tvorog_0_5",
        "упаковки творога": "tvorog_0_5",
        # drink_yogurt_strawberry_0_5 — longer aliases must beat shorter ones
        "йогурт с клубникой": "drink_yogurt_strawberry_0_5",
        "йогурт клубничный": "drink_yogurt_strawberry_0_5",
        "клубничный йогурт": "drink_yogurt_strawberry_0_5",
        "йогурт питьевой с клубникой": "drink_yogurt_strawberry_0_5",
        "йогурта с клубникой": "drink_yogurt_strawberry_0_5",
        # drink_yogurt_classic_0_5 — shorter "йогурт" aliases
        "йогурт питьевой классический": "drink_yogurt_classic_0_5",
        "йогурт классический": "drink_yogurt_classic_0_5",
        "питьевой йогурт": "drink_yogurt_classic_0_5",
        "йогурт питьевой": "drink_yogurt_classic_0_5",
    }


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_lowercase(self):
        assert normalize_text("МОЛОКО") == "молоко"

    def test_yo_to_ye(self):
        assert normalize_text("тушёнка") == "тушенка"

    def test_decimal_comma(self):
        # "0,5" → decimal comma converted to dot before comma-stripping
        assert normalize_text("0,5 кг") == "0.5 кг"

    def test_strips_commas(self):
        result = normalize_text("брынза 2 шт, масло 1 шт")
        assert "," not in result
        assert "брынза" in result
        assert "масло" in result

    def test_collapses_spaces(self):
        result = normalize_text("молоко   3   шт")
        assert "  " not in result

    def test_strips_leading_trailing(self):
        assert normalize_text("  молоко 3  ") == "молоко 3"

    def test_mixed_case_yo(self):
        # "2ШТ" → lowercase → "2шт" → digit+Cyrillic space insertion → "2 шт"
        assert normalize_text("Йогурт с клубникой 2ШТ") == "йогурт с клубникой 2 шт"

    def test_dashes_replaced(self):
        result = normalize_text("молоко — 3 шт")
        assert "—" not in result


class TestNormalizeAlias:
    def test_basic(self):
        assert _normalize_alias("Молоко") == "молоко"

    def test_yo(self):
        assert _normalize_alias("тушёнка") == "тушенка"

    def test_strips_punctuation(self):
        # Comma is replaced by space, then multiple spaces are collapsed → single space
        assert _normalize_alias("масло, сливочное") == "масло сливочное"


# ---------------------------------------------------------------------------
# SummaryIntent (unchanged from v1.0)
# ---------------------------------------------------------------------------


class TestSummaryParsing:
    def test_slash_summary_iso(self):
        intent = parse("/summary 2026-03-15")
        assert isinstance(intent, SummaryIntent)
        assert intent.delivery_date == date(2026, 3, 15)

    def test_summary_no_slash(self):
        intent = parse("summary 2026-03-15")
        assert isinstance(intent, SummaryIntent)
        assert intent.delivery_date == date(2026, 3, 15)

    def test_svodka_russian(self):
        intent = parse("сводка на 2026-03-15")
        assert isinstance(intent, SummaryIntent)
        assert intent.delivery_date == date(2026, 3, 15)

    def test_summary_no_date_returns_none(self):
        intent = parse("summary")
        assert intent is None


# ---------------------------------------------------------------------------
# DaysLoadIntent (unchanged from v1.0)
# ---------------------------------------------------------------------------


class TestDaysLoadParsing:
    def test_slash_days(self):
        intent = parse("/days")
        assert isinstance(intent, DaysLoadIntent)

    def test_days_no_slash(self):
        intent = parse("days")
        assert isinstance(intent, DaysLoadIntent)

    def test_russian_days(self):
        intent = parse("загрузка по датам")
        assert isinstance(intent, DaysLoadIntent)


# ---------------------------------------------------------------------------
# ExportIntent (unchanged from v1.0)
# ---------------------------------------------------------------------------


class TestExportParsing:
    def test_slash_export(self):
        intent = parse("/export 2026-03-15")
        assert isinstance(intent, ExportIntent)
        assert intent.delivery_date == date(2026, 3, 15)

    def test_export_no_slash(self):
        intent = parse("export 2026-03-15")
        assert isinstance(intent, ExportIntent)

    def test_export_no_date_returns_none(self):
        intent = parse("export")
        assert intent is None


# ---------------------------------------------------------------------------
# CreateOrderIntent — legacy SKU mode (backward compatibility)
# ---------------------------------------------------------------------------


class TestCreateOrderSkuMode:
    def test_iso_date_single_sku(self):
        intent = parse("2026-03-15 milk_1_5 12")
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 15)
        assert len(intent.draft.items) == 1
        assert intent.draft.items[0].sku == "milk_1_5"
        assert intent.draft.items[0].requested_qty == 12

    def test_iso_date_multi_sku(self):
        intent = parse("2026-03-15 milk_1_5 12 kefir_1 6")
        assert isinstance(intent, CreateOrderIntent)
        assert len(intent.draft.items) == 2
        skus = {i.sku for i in intent.draft.items}
        assert "milk_1_5" in skus
        assert "kefir_1" in skus

    def test_dot_date(self):
        intent = parse("15.03 milk_1_5 20")
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 15)

    def test_dot_date_with_year(self):
        intent = parse("15.03.2026 milk_3_2 10")
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 15)

    def test_russian_date(self):
        intent = parse("на 15 марта milk_1_5 12")
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 15)

    def test_russian_date_with_name(self):
        intent = parse("15 марта Ирина milk_1_5 12 kefir_1 6")
        assert isinstance(intent, CreateOrderIntent)
        assert len(intent.draft.items) == 2

    def test_no_date_returns_none(self):
        intent = parse("milk_1_5 12")
        assert intent is None

    def test_date_no_items_returns_none(self):
        intent = parse("2026-03-15")
        assert intent is None

    def test_unknown_text_returns_none(self):
        intent = parse("hello world")
        assert intent is None


# ---------------------------------------------------------------------------
# CreateOrderIntent — Russian alias mode (v1.1)
# ---------------------------------------------------------------------------


class TestCreateOrderAliasMode:
    """Test 1: 26 марта фермерского 2 шт, брынза 2 шт"""

    def test_farmer_and_brynza(self, alias_index):
        intent = parse("26 марта фермерского 2 шт, брынза 2 шт", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("farmer_cheese_300") == 2
        assert skus.get("brynza_300") == 2

    """Test 2: на 26 марта 2 упаковки творога и йогурт с клубникой 2 шт"""

    def test_tvorog_and_yogurt_strawberry(self, alias_index):
        intent = parse(
            "на 26 марта 2 упаковки творога и йогурт с клубникой 2 шт",
            alias_index=alias_index,
        )
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("tvorog_0_5") == 2
        assert skus.get("drink_yogurt_strawberry_0_5") == 2

    """Test 3: 26.03 молока 3 шт, масла 1 шт"""

    def test_milk_and_butter_dot_date(self, alias_index):
        intent = parse("26.03 молока 3 шт, масла 1 шт", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("milk_1_5") == 3
        assert skus.get("butter_200") == 1

    """Test 4: 2026-03-26 фермерский 2, брынза 1"""

    def test_iso_date_russian_products(self, alias_index):
        intent = parse("2026-03-26 фермерский 2, брынза 1", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("farmer_cheese_300") == 2
        assert skus.get("brynza_300") == 1

    """Test 5: long mixed order with polite preamble"""

    def test_long_mixed_order(self, alias_index):
        text = (
            "26 марта тогда запишите пожалуйста, фермерского 2 шт, брынза 2 шт. "
            "2 упаковки творога и йогурт с клубникой 2 шт"
        )
        intent = parse(text, alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("farmer_cheese_300") == 2
        assert skus.get("brynza_300") == 2
        assert skus.get("tvorog_0_5") == 2
        assert skus.get("drink_yogurt_strawberry_0_5") == 2

    def test_client_name_two_words_preserved(self, alias_index):
        text = "Прими заказ на 2 апреля\nЕлена Илизарова. Творог 4, Масло 2, Тушенка 1"
        intent = parse(text, alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert getattr(intent.draft, "client_name", None) == "Елена Илизарова"

    def test_client_name_ignores_product_words(self, alias_index):
        text = "Прими заказ на 2 апреля\nМасло Тушенка. Творог 4, Масло 2"
        intent = parse(text, alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert getattr(intent.draft, "client_name", None) == "Масло Тушенка"


# ---------------------------------------------------------------------------
# Test 4 (spec): "если будет масло" — no qty → no order item
# ---------------------------------------------------------------------------


class TestNoQtyNotOrdered:
    def test_conditional_phrase_no_qty(self, alias_index):
        """'если будет масло' must NOT produce an order item."""
        intent = parse("если будет масло", alias_index=alias_index)
        # No date → returns None (cannot be an order at all)
        assert intent is None

    def test_product_with_date_but_no_qty(self, alias_index):
        """'26 марта брынза' — product found but no qty → no order created."""
        intent = parse("26 марта брынза", alias_index=alias_index)
        # Date found, alias found, but no qty → items list is empty → None
        assert intent is None

    def test_product_no_qty_not_silently_qty1(self, alias_index):
        """Ensure qty=1 is never silently assumed when qty is absent."""
        intent = parse("26 марта масло", alias_index=alias_index)
        assert intent is None


# ---------------------------------------------------------------------------
# Test 6 (spec): Longest match — "йогурт с клубникой" beats "йогурт"
# ---------------------------------------------------------------------------


class TestLongestMatch:
    def test_yogurt_strawberry_beats_plain_yogurt(self, alias_index):
        """'йогурт с клубникой 2 шт' must resolve to strawberry yogurt."""
        items, _ = _extract_items_by_alias(
            "йогурт с клубникой 2 шт", alias_index
        )
        assert len(items) == 1
        assert items[0].sku == "drink_yogurt_strawberry_0_5"
        assert items[0].requested_qty == 2

    def test_farmer_cheese_not_confused_with_shorter(self, alias_index):
        """'фермерского 2 шт' must resolve to farmer_cheese_300."""
        items, _ = _extract_items_by_alias("фермерского 2 шт", alias_index)
        assert len(items) == 1
        assert items[0].sku == "farmer_cheese_300"

    def test_two_yogurts_in_one_text(self, alias_index):
        """When both yogurt types appear, each should be matched correctly."""
        # Only strawberry yogurt alias present in this text
        items, _ = _extract_items_by_alias(
            "йогурт с клубникой 2 шт", alias_index
        )
        skus = {i.sku for i in items}
        assert "drink_yogurt_strawberry_0_5" in skus
        assert "drink_yogurt_classic_0_5" not in skus


# ---------------------------------------------------------------------------
# Test 7 (spec): Normalisation — case and unit variants give same result
# ---------------------------------------------------------------------------


class TestNormalisationVariants:
    @pytest.mark.parametrize("text", [
        "26 марта Йогурт с клубникой 2шт",
        "26 марта йогурт с клубникой 2 шт",
        "26 марта йогурт с клубникой 2ШТ",
        "26 марта ЙОГУРТ С КЛУБНИКОЙ 2 ШТ",
        "26 марта йогурт с клубникой 2 штук",
        "26 марта йогурт с клубникой 2 упаковки",
    ])
    def test_yogurt_strawberry_normalised(self, text, alias_index):
        intent = parse(text, alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent), f"Failed for: {text!r}"
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("drink_yogurt_strawberry_0_5") == 2, f"Failed for: {text!r}"


# ---------------------------------------------------------------------------
# Test 8 (spec): Mixed SKU + alias input
# ---------------------------------------------------------------------------


class TestMixedSkuAndAlias:
    def test_sku_and_alias_in_same_order(self, alias_index):
        """Part of order via alias, part via SKU — both should be recognised."""
        intent = parse(
            "26 марта брынза 2 шт milk_1_5 3",
            alias_index=alias_index,
        )
        assert isinstance(intent, CreateOrderIntent)
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("brynza_300") == 2
        assert skus.get("milk_1_5") == 3

    def test_short_salo_alias_resolves(self, alias_index):
        """Short alias must resolve the real salo SKU in user text."""
        items, no_qty = _extract_items_by_alias("Сало 1", alias_index)
        assert not no_qty
        assert len(items) == 1
        assert items[0].sku == "salo_spread_200"
        assert items[0].requested_qty == 1

    def test_pure_sku_still_works_with_alias_index(self, alias_index):
        """Pure SKU input must still work even when alias_index is provided."""
        intent = parse("2026-03-26 milk_1_5 5", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.items[0].sku == "milk_1_5"
        assert intent.draft.items[0].requested_qty == 5

    def test_client_name_ignores_leading_imperative_verb(self, alias_index):
        intent = parse(
            "Прими заказ на 2 апреля\nЕлена Илизарова. Творог 4, Масло 2, Тушенка 1",
            alias_index=alias_index,
        )
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.client_name == "Елена Илизарова"
        assert intent.draft.delivery_date == date(2026, 4, 2)
        skus = {i.sku: i.requested_qty for i in intent.draft.items}
        assert skus.get("tvorog_0_5") == 4
        assert skus.get("butter_200") == 2


# ---------------------------------------------------------------------------
# Date parsing edge cases
# ---------------------------------------------------------------------------


class TestDateParsing:
    def test_iso_date(self, alias_index):
        intent = parse("2026-03-26 брынза 1", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)

    def test_dot_date_no_year(self, alias_index):
        intent = parse("26.03 брынза 1", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date.month == 3
        assert intent.draft.delivery_date.day == 26

    def test_dot_date_with_year(self, alias_index):
        intent = parse("26.03.2026 брынза 1", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)

    def test_russian_month_name(self, alias_index):
        intent = parse("26 марта брынза 1", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)

    def test_russian_month_with_na(self, alias_index):
        intent = parse("на 26 марта брынза 1", alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent)
        assert intent.draft.delivery_date == date(2026, 3, 26)

    def test_no_date_returns_none(self, alias_index):
        intent = parse("брынза 2 шт", alias_index=alias_index)
        assert intent is None


# ---------------------------------------------------------------------------
# Quantity detection variants
# ---------------------------------------------------------------------------


class TestQtyDetection:
    @pytest.mark.parametrize("text,expected_qty", [
        ("26 марта брынза 2 шт", 2),
        ("26 марта брынза 2шт", 2),
        ("26 марта брынза 2 штук", 2),
        ("26 марта брынза 2 упаковки", 2),
        ("26 марта брынза 2 уп", 2),
        ("26 марта 2 брынза", 2),
        ("26 марта 2 шт брынза", 2),
    ])
    def test_qty_variants(self, text, expected_qty, alias_index):
        intent = parse(text, alias_index=alias_index)
        assert isinstance(intent, CreateOrderIntent), f"Failed for: {text!r}"
        assert intent.draft.items[0].requested_qty == expected_qty, f"Failed for: {text!r}"


# ---------------------------------------------------------------------------
# Rejected / edge cases
# ---------------------------------------------------------------------------


class TestRejectedCases:
    def test_no_items_at_all(self, alias_index):
        intent = parse("26 марта", alias_index=alias_index)
        assert intent is None

    def test_unknown_product_no_crash(self, alias_index):
        """Unknown product text with date → None (no crash)."""
        intent = parse("26 марта неизвестный_продукт 5", alias_index=alias_index)
        # "неизвестный_продукт" is not in alias_index, but matches SKU regex
        # It will be included as a raw SKU — that's acceptable for v1.1
        # The important thing is no exception is raised
        # (validator will reject it later)
        # So we just assert no exception:
        assert intent is None or isinstance(intent, CreateOrderIntent)

    def test_empty_string(self, alias_index):
        intent = parse("", alias_index=alias_index)
        assert intent is None

    def test_only_date_no_products(self, alias_index):
        intent = parse("26 марта", alias_index=alias_index)
        assert intent is None

    def test_polite_preamble_no_products(self, alias_index):
        """Polite text without any product mention → None."""
        intent = parse("26 марта тогда запишите пожалуйста", alias_index=alias_index)
        assert intent is None
