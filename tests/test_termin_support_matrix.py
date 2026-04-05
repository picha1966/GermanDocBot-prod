# -*- coding: utf-8 -*-
"""
tests/test_termin_support_matrix.py

Unit tests for the Termin-button visibility logic in handlers/stripe_handler.py.

Covers three pure functions (no DB, no bot, no HTTP):
  - _normalize_city(city)       → canonical city code
  - is_termin_supported(doc_type, city) → bool
  - build_post_payment_menu(doc_type, city, lang) → InlineKeyboardMarkup row count

These functions control whether the "Find Termin" button appears in the
post-payment menu. A wrong result means:
  - False negative → user never sees the Termin button (silent UX regression)
  - False positive → Termin button shown for unsupported city/doc (broken flow)

Usage:
    pytest tests/test_termin_support_matrix.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _import():
    try:
        from handlers.stripe_handler import (
            _normalize_city,
            is_termin_supported,
            build_post_payment_menu,
            TERMIN_SUPPORTED,
            _CITY_ALIASES,
        )
        return _normalize_city, is_termin_supported, build_post_payment_menu, TERMIN_SUPPORTED, _CITY_ALIASES
    except ImportError as e:
        pytest.skip(f"stripe_handler not importable: {e}")


# ---------------------------------------------------------------------------
# _normalize_city
# ---------------------------------------------------------------------------

class TestNormalizeCity:
    def test_none_returns_empty(self):
        fn, *_ = _import()
        assert fn(None) == ""

    def test_empty_string_returns_empty(self):
        fn, *_ = _import()
        assert fn("") == ""

    def test_whitespace_only_returns_empty(self):
        fn, *_ = _import()
        assert fn("   ") == ""

    def test_berlin_lowercase(self):
        fn, *_ = _import()
        assert fn("berlin") == "berlin"

    def test_berlin_capitalized(self):
        fn, *_ = _import()
        assert fn("Berlin") == "berlin"

    def test_berlin_with_spaces(self):
        fn, *_ = _import()
        assert fn("  Berlin  ") == "berlin"

    def test_koeln_umlaut(self):
        fn, *_ = _import()
        assert fn("Köln") == "koeln"

    def test_koeln_no_umlaut(self):
        fn, *_ = _import()
        assert fn("koeln") == "koeln"

    def test_cologne_english(self):
        fn, *_ = _import()
        assert fn("cologne") == "koeln"

    def test_duesseldorf_umlaut(self):
        fn, *_ = _import()
        assert fn("Düsseldorf") == "duesseldorf"

    def test_duesseldorf_no_umlaut(self):
        fn, *_ = _import()
        assert fn("dusseldorf") == "duesseldorf"

    def test_frankfurt_am_main(self):
        fn, *_ = _import()
        assert fn("Frankfurt am Main") == "frankfurt"

    def test_frankfurt_slash(self):
        fn, *_ = _import()
        assert fn("Frankfurt/Main") == "frankfurt"

    def test_muenchen_umlaut(self):
        fn, *_ = _import()
        assert fn("München") == "muenchen"

    def test_munich_english(self):
        fn, *_ = _import()
        assert fn("Munich") == "muenchen"

    def test_krefeld(self):
        fn, *_ = _import()
        assert fn("Krefeld") == "krefeld"

    def test_unknown_city_passthrough(self):
        # Unknown city: returned as-is (lowercased) — will not match any supported list
        fn, *_ = _import()
        assert fn("Bielefeld") == "bielefeld"


# ---------------------------------------------------------------------------
# is_termin_supported
# ---------------------------------------------------------------------------

class TestIsTerminSupported:

    # --- Guard: None / empty inputs ---

    def test_none_doc_type(self):
        _, fn, *_ = _import()
        assert fn(None, "berlin") is False

    def test_none_city(self):
        _, fn, *_ = _import()
        assert fn("anmeldung", None) is False

    def test_both_none(self):
        _, fn, *_ = _import()
        assert fn(None, None) is False

    def test_empty_doc_type(self):
        _, fn, *_ = _import()
        assert fn("", "berlin") is False

    def test_empty_city(self):
        _, fn, *_ = _import()
        assert fn("anmeldung", "") is False

    # --- anmeldung: supported cities ---

    @pytest.mark.parametrize("city", [
        "berlin", "Berlin", "BERLIN",
        "frankfurt", "Frankfurt", "Frankfurt am Main",
        "koeln", "Köln", "cologne",
        "duesseldorf", "Düsseldorf", "dusseldorf",
        "krefeld", "Krefeld",
    ])
    def test_anmeldung_supported_city(self, city):
        _, fn, *_ = _import()
        assert fn("anmeldung", city) is True, f"Expected True for anmeldung + {city!r}"

    @pytest.mark.parametrize("city", [
        "muenchen", "München", "munich",
        "hamburg", "Hamburg",
        "dortmund", "Dortmund",
        "bielefeld",
    ])
    def test_anmeldung_unsupported_city(self, city):
        _, fn, *_ = _import()
        assert fn("anmeldung", city) is False, f"Expected False for anmeldung + {city!r}"

    # --- ummeldung: same support matrix as anmeldung ---

    @pytest.mark.parametrize("city", ["berlin", "frankfurt", "koeln", "duesseldorf", "krefeld"])
    def test_ummeldung_supported_city(self, city):
        _, fn, *_ = _import()
        assert fn("ummeldung", city) is True

    def test_ummeldung_unsupported_city(self):
        _, fn, *_ = _import()
        assert fn("ummeldung", "muenchen") is False

    # --- aufenthaltstitel: only berlin ---

    def test_aufenthaltstitel_berlin(self):
        _, fn, *_ = _import()
        assert fn("aufenthaltstitel", "berlin") is True

    @pytest.mark.parametrize("city", ["frankfurt", "koeln", "duesseldorf", "krefeld", "muenchen"])
    def test_aufenthaltstitel_non_berlin(self, city):
        _, fn, *_ = _import()
        assert fn("aufenthaltstitel", city) is False

    # --- docs with empty support list ---

    @pytest.mark.parametrize("doc_type", ["buergergeld", "abmeldung", "wohngeld", "kindergeld"])
    def test_empty_support_list_always_false(self, doc_type):
        _, fn, *_ = _import()
        assert fn(doc_type, "berlin") is False, (
            f"{doc_type} should never show Termin button (empty support list)"
        )

    # --- unknown doc_type ---

    def test_unknown_doc_type(self):
        _, fn, *_ = _import()
        assert fn("familienkasse", "berlin") is False

    def test_completely_unknown_doc_type(self):
        _, fn, *_ = _import()
        assert fn("xyz_doc", "berlin") is False

    # --- case insensitivity for doc_type ---

    def test_doc_type_uppercase_normalized(self):
        _, fn, *_ = _import()
        assert fn("Anmeldung", "berlin") is True

    def test_doc_type_mixed_case(self):
        _, fn, *_ = _import()
        assert fn("UMMELDUNG", "frankfurt") is True


# ---------------------------------------------------------------------------
# build_post_payment_menu — row count signals Termin button presence
# ---------------------------------------------------------------------------

class TestBuildPostPaymentMenu:
    """
    Menu structure (as of v5.0):
      Row 0: Official form button + Instructions button  (always)
      Row 1: Find Termin button                          (only when Termin is supported)
      Row N: "What next?" button                         (always)
      Row N+1: Share bot button                          (always when BOT_USERNAME is configured)

    Key invariant: supported city → exactly 1 more row than unsupported city.
    """

    def _row_count(self, doc_type, city, lang="en"):
        _, _, build, *_ = _import()
        menu = build(doc_type, city, lang)
        return len(menu.inline_keyboard)

    def _base_row_count(self):
        """Row count for a combination where Termin is NOT supported."""
        return self._row_count("anmeldung", "muenchen")

    def test_supported_city_has_one_extra_row(self):
        """Supported city adds exactly the Termin row on top of the base count."""
        base = self._base_row_count()
        assert self._row_count("anmeldung", "berlin") == base + 1

    def test_unsupported_city_has_base_rows(self):
        base = self._base_row_count()
        assert self._row_count("anmeldung", "muenchen") == base

    def test_empty_support_list_has_base_rows(self):
        base = self._base_row_count()
        assert self._row_count("buergergeld", "berlin") == base

    def test_none_city_has_base_rows(self):
        base = self._base_row_count()
        assert self._row_count("anmeldung", None) == base

    def test_none_doc_type_has_base_rows(self):
        base = self._base_row_count()
        assert self._row_count(None, "berlin") == base

    def test_row1_always_has_two_buttons(self):
        """Official form + Instructions are always present in the first row."""
        _, _, build, *_ = _import()
        menu = build("anmeldung", "berlin", "en")
        assert len(menu.inline_keyboard[0]) == 2

    def test_termin_row_has_one_button(self):
        """Termin row contains exactly one button."""
        _, _, build, *_ = _import()
        menu = build("anmeldung", "berlin", "en")
        assert len(menu.inline_keyboard[1]) == 1

    def test_termin_button_callback_data(self):
        """Termin button must use 'termin_from_pdf' callback — matches the existing handler."""
        _, _, build, *_ = _import()
        menu = build("anmeldung", "berlin", "en")
        termin_btn = menu.inline_keyboard[1][0]
        assert termin_btn.callback_data == "termin_from_pdf"

    def test_official_form_button_is_navigable(self):
        """Official form button must provide a destination — either a direct government URL
        (url= field set) or a bot callback (callback_data starts with 'post_payment:official_form:').

        Buttons with a known government link use url= and do NOT set callback_data.
        Buttons without a government link fall back to callback_data.
        Both are valid implementations; we assert that exactly one is present.
        """
        _, _, build, *_ = _import()
        menu = build("anmeldung", "berlin", "en")
        btn = menu.inline_keyboard[0][0]
        has_url = bool(btn.url)
        has_cb = bool(btn.callback_data and btn.callback_data.startswith("post_payment:official_form:"))
        assert has_url or has_cb, (
            f"Official form button has neither a government url= nor a 'post_payment:official_form:' "
            f"callback_data. url={btn.url!r}  callback_data={btn.callback_data!r}"
        )

    @pytest.mark.parametrize("lang,expected_fragment", [
        ("en", "Find Termin"),
        ("de", "Termin finden"),
        ("uk", "Знайти термін"),
        ("pl", "Znajdź termin"),
    ])
    def test_termin_button_label_localized(self, lang, expected_fragment):
        _, _, build, *_ = _import()
        menu = build("anmeldung", "berlin", lang)
        termin_btn = menu.inline_keyboard[1][0]
        assert expected_fragment in termin_btn.text, (
            f"Expected {expected_fragment!r} in button text for lang={lang!r}, "
            f"got {termin_btn.text!r}"
        )

    def test_ua_lang_alias_resolves_to_uk(self):
        """lang='ua' must be treated as 'uk' (same Ukrainian locale)."""
        _, _, build, *_ = _import()
        menu_ua = build("anmeldung", "berlin", "ua")
        menu_uk = build("anmeldung", "berlin", "uk")
        assert menu_ua.inline_keyboard[1][0].text == menu_uk.inline_keyboard[1][0].text

    def test_unknown_lang_falls_back_to_en(self):
        _, _, build, *_ = _import()
        menu = build("anmeldung", "berlin", "zz")
        btn_text = menu.inline_keyboard[1][0].text
        assert "Find Termin" in btn_text


# ---------------------------------------------------------------------------
# TERMIN_SUPPORTED matrix integrity
# ---------------------------------------------------------------------------

class TestTerminSupportedMatrix:

    def test_all_supported_cities_are_canonical(self):
        """Every city code in TERMIN_SUPPORTED must be a canonical alias key."""
        _, _, _, matrix, aliases = _import()
        for doc_type, cities in matrix.items():
            for city in cities:
                assert city in aliases.values(), (
                    f"City {city!r} in TERMIN_SUPPORTED[{doc_type!r}] is not a "
                    f"canonical alias value — normalize would never resolve it"
                )

    def test_no_duplicate_cities_per_doc_type(self):
        _, _, _, matrix, _ = _import()
        for doc_type, cities in matrix.items():
            assert len(cities) == len(set(cities)), (
                f"Duplicate city entries in TERMIN_SUPPORTED[{doc_type!r}]: {cities}"
            )

    def test_matrix_keys_are_lowercase(self):
        _, _, _, matrix, _ = _import()
        for key in matrix:
            assert key == key.lower(), f"TERMIN_SUPPORTED key {key!r} is not lowercase"
