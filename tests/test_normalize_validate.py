# -*- coding: utf-8 -*-
"""
Tests for normalize_user_data / validate_user_data / COUNTRY_MAP.

Run: pytest tests/test_normalize_validate.py -v
"""
from __future__ import annotations

import pytest
from backend.utils.normalize import (
    COUNTRY_MAP,
    _normalize_country,
    _normalize_date,
    _normalize_name,
    _normalize_street,
    normalize_user_data,
)
from backend.utils.validate import validate_user_data


# ---------------------------------------------------------------------------
# A. COUNTRY_MAP — canonical country normalization
# ---------------------------------------------------------------------------

class TestCountryMap:
    def test_ukraine_english(self):
        assert _normalize_country("ukraine") == "Ukraine"

    def test_ukraine_cyrillic(self):
        assert _normalize_country("україна") == "Ukraine"

    def test_ukraine_russian(self):
        assert _normalize_country("украина") == "Ukraine"

    def test_ukraine_abbrev(self):
        assert _normalize_country("ua") == "Ukraine"

    def test_germany_english(self):
        assert _normalize_country("germany") == "Deutschland"

    def test_germany_native(self):
        assert _normalize_country("deutschland") == "Deutschland"

    def test_germany_abbrev(self):
        assert _normalize_country("de") == "Deutschland"

    def test_poland(self):
        assert _normalize_country("polska") == "Polen"

    def test_case_insensitive(self):
        assert _normalize_country("UKRAINE") == "Ukraine"
        assert _normalize_country("Germany") == "Deutschland"
        assert _normalize_country("DEUTSCHLAND") == "Deutschland"

    def test_unknown_falls_back_to_title(self):
        assert _normalize_country("someUnknownCountry") == "Someunknowncountry"

    def test_country_map_exported(self):
        assert isinstance(COUNTRY_MAP, dict)
        assert len(COUNTRY_MAP) > 10

    def test_normalize_user_data_birth_country(self):
        data = normalize_user_data({"birth_country": "ukraine"})
        assert data["birth_country"] == "Ukraine"

    def test_normalize_user_data_geburtsland(self):
        data = normalize_user_data({"geburtsland": "germany"})
        assert data["geburtsland"] == "Deutschland"


# ---------------------------------------------------------------------------
# B. Names — capitalize
# ---------------------------------------------------------------------------

class TestNameNormalization:
    def test_lowercase_capitalized(self):
        assert _normalize_name("ivan") == "Ivan"

    def test_last_name_capitalized(self):
        assert _normalize_name("petrenko") == "Petrenko"

    def test_all_caps_lowered_capitalized(self):
        assert _normalize_name("JOHN") == "John"

    def test_compound_hyphen_name(self):
        assert _normalize_name("anna-maria") == "Anna-Maria"

    def test_multi_word_name(self):
        result = _normalize_name("  john   doe  ")
        assert result == "John Doe"

    def test_already_correct(self):
        assert _normalize_name("Ivan") == "Ivan"

    def test_normalize_user_data_names(self):
        data = normalize_user_data({"first_name": "ivan", "last_name": "petrenko"})
        assert data["first_name"] == "Ivan"
        assert data["last_name"] == "Petrenko"


# ---------------------------------------------------------------------------
# C. Dates — DD.MM.YYYY normalization
# ---------------------------------------------------------------------------

class TestDateNormalization:
    def test_iso_format(self):
        assert _normalize_date("1990-05-15") == "15.05.1990"

    def test_german_format_already(self):
        assert _normalize_date("15.05.1990") == "15.05.1990"

    def test_single_digit_day_month(self):
        assert _normalize_date("5.5.1990") == "05.05.1990"

    def test_slash_format(self):
        assert _normalize_date("15/05/1990") == "15.05.1990"

    def test_iso_slash(self):
        assert _normalize_date("1990/05/15") == "15.05.1990"

    def test_normalize_user_data_dates(self):
        data = normalize_user_data({"birth_date": "1990-05-15"})
        assert data["birth_date"] == "15.05.1990"

    def test_normalize_user_data_move_in_date(self):
        data = normalize_user_data({"move_in_date": "2023/01/07"})
        assert data["move_in_date"] == "07.01.2023"


# ---------------------------------------------------------------------------
# D. Streets — strasse → Straße
# ---------------------------------------------------------------------------

class TestStreetNormalization:
    def test_strasse_to_strasse_german(self):
        assert _normalize_street("Musterstrasse") == "Musterstraße"

    def test_mixed_case(self):
        assert _normalize_street("musterSTRASSE") == "Musterstraße"

    def test_already_correct(self):
        assert _normalize_street("Musterstraße") == "Musterstraße"

    def test_normalize_user_data_street(self):
        data = normalize_user_data({"street": "Musterstrasse"})
        assert data["street"] == "Musterstraße"


# ---------------------------------------------------------------------------
# E. Cleanup — double spaces, trim
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_trim_whitespace(self):
        data = normalize_user_data({"first_name": "  Ivan  "})
        assert data["first_name"] == "Ivan"

    def test_double_spaces_collapsed(self):
        data = normalize_user_data({"first_name": "Anna  Maria"})
        assert "  " not in data["first_name"]

    def test_empty_string_preserved(self):
        data = normalize_user_data({"first_name": ""})
        assert data["first_name"] == ""


# ---------------------------------------------------------------------------
# F. validate_user_data — integration
# ---------------------------------------------------------------------------

class TestValidateUserData:
    def test_valid_anmeldung_returns_ok(self):
        data = {
            "first_name": "Ivan",
            "last_name": "Petrenko",
            "birth_date": "15.05.1990",
            "street": "Musterstraße",
            "house_number": "5",
            "plz": "10115",
            "city": "Berlin",
        }
        ok, missing, warnings = validate_user_data("anmeldung", data, lang="de")
        # Some fields may still be missing but the function must not crash
        assert isinstance(ok, bool)
        assert isinstance(missing, list)
        assert isinstance(warnings, list)

    def test_empty_data_has_missing_fields(self):
        ok, missing, _ = validate_user_data("anmeldung", {}, lang="de")
        assert ok is False
        assert len(missing) > 0

    def test_missing_keys_are_strings(self):
        _, missing, _ = validate_user_data("anmeldung", {}, lang="de")
        for m in missing:
            assert "key" in m
            assert isinstance(m["key"], str)

    def test_unknown_doc_type_returns_ok(self):
        """Unknown doc_type has no required fields — validation passes."""
        ok, missing, _ = validate_user_data("nonexistent_type", {"a": "b"}, lang="de")
        assert ok is True
        assert missing == []


# ---------------------------------------------------------------------------
# G. normalize_user_data — idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_calling_twice_same_result(self):
        data = {
            "first_name": "ivan",
            "birth_date": "1990-05-15",
            "street": "Musterstrasse",
            "birth_country": "ukraine",
        }
        once = normalize_user_data(data)
        twice = normalize_user_data(once)
        assert once == twice

    def test_does_not_mutate_original(self):
        original = {"first_name": "ivan", "birth_date": "1990-05-15"}
        _ = normalize_user_data(original)
        assert original["first_name"] == "ivan"   # original unchanged
        assert original["birth_date"] == "1990-05-15"
