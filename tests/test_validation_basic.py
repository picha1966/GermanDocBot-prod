# -*- coding: utf-8 -*-
"""
tests/test_validation_basic.py

Basic sanity tests for the validation pipeline.

Verifies that:
  - minimal valid payloads pass validation (ok=True, no critical missing fields)
  - alias resolution works (postal_code accepted for plz, monthly_income for income)
  - child_name synthesis from child_first_name + child_last_name works
  - invalid payloads correctly fail validation

Usage:
  pytest tests/test_validation_basic.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.utils.validate import validate_user_data
from backend.utils.normalize import normalize_user_data


# ---------------------------------------------------------------------------
# SECTION 1: Core doc — anmeldung passes with minimal required fields
# ---------------------------------------------------------------------------

def test_anmeldung_minimal_valid():
    """All required anmeldung fields present → validation passes."""
    data = {
        "first_name":   "Max",
        "last_name":    "Mustermann",
        "birth_date":   "18.07.1990",
        "street":       "Musterstraße",
        "house_number": "12",
        "postal_code":  "10115",   # alias for plz
        "city":         "Berlin",
        "move_in_date": "01.03.2026",
    }
    ok, missing, warnings = validate_user_data("anmeldung", data, "en")
    missing_keys = [m["key"] for m in missing]
    assert ok is True, f"Expected validation to pass but got missing: {missing_keys}"


def test_anmeldung_missing_required_fails():
    """Missing street + city → validation must fail."""
    data = {
        "first_name":   "Max",
        "last_name":    "Mustermann",
        "birth_date":   "18.07.1990",
    }
    ok, missing, _warnings = validate_user_data("anmeldung", data, "en")
    assert ok is False, "Expected validation to fail when required fields are missing"
    missing_keys = [m["key"] for m in missing]
    assert "street" in missing_keys or "plz" in missing_keys or "city" in missing_keys


# ---------------------------------------------------------------------------
# SECTION 2: Alias resolution — postal_code accepted as plz
# ---------------------------------------------------------------------------

def test_plz_alias_postal_code_accepted():
    """postal_code must be accepted as equivalent to plz."""
    data = {
        "first_name":   "Anna",
        "last_name":    "Beispiel",
        "birth_date":   "01.01.1995",
        "street":       "Hauptstraße 1",
        "plz":          "10115",
        "city":         "Berlin",
        "move_in_date": "15.02.2026",
        "house_number": "1",
    }
    data_with_postal_code = dict(data)
    del data_with_postal_code["plz"]
    data_with_postal_code["postal_code"] = "10115"

    ok_plz,     _, _ = validate_user_data("anmeldung", data,                  "en")
    ok_postal,  _, _ = validate_user_data("anmeldung", data_with_postal_code, "en")

    assert ok_plz,    "Baseline with plz should pass"
    assert ok_postal, "postal_code alias must be accepted — same result as plz"


# ---------------------------------------------------------------------------
# SECTION 3: Alias resolution — monthly_income accepted for wohngeld income
# ---------------------------------------------------------------------------

def test_wohngeld_monthly_income_alias():
    """monthly_income must be accepted as income for wohngeld."""
    data = {
        "first_name":    "Maria",
        "last_name":     "Schmidt",
        "street":        "Berliner Allee 10",
        "plz":           "10243",
        "city":          "Berlin",
        "monthly_income": "1200",  # alias for income
    }
    ok, missing, _ = validate_user_data("wohngeld", data, "en")
    missing_keys = [m["key"] for m in missing]
    assert "income" not in missing_keys, (
        f"monthly_income alias not resolved — validator still reports income missing.\n"
        f"All missing: {missing_keys}"
    )


# ---------------------------------------------------------------------------
# SECTION 4: child_name synthesis in normalize_user_data
# ---------------------------------------------------------------------------

def test_child_name_synthesized_from_split_fields():
    """normalize_user_data must combine child_first_name + child_last_name → child_name."""
    data = {
        "child_first_name": "Anna",
        "child_last_name":  "Mustermann",
    }
    result = normalize_user_data(data)
    assert "child_name" in result, "child_name must be synthesized from split fields"
    assert result["child_name"] == "Anna Mustermann", (
        f"Expected 'Anna Mustermann', got '{result.get('child_name')}'"
    )


def test_child_name_not_overwritten_when_already_set():
    """If child_name already exists, normalize must NOT overwrite it."""
    data = {
        "child_name":       "Existing Name",
        "child_first_name": "Anna",
        "child_last_name":  "Mustermann",
    }
    result = normalize_user_data(data)
    assert result["child_name"] == "Existing Name", (
        "Existing child_name must not be overwritten by synthesis"
    )


def test_child_name_alias_passes_validation_for_kindergeld():
    """child_first_name + child_last_name → synthesized child_name → validation passes."""
    raw = {
        "first_name":        "Olena",
        "last_name":         "Kovalenko",
        "birth_date":        "15.07.1990",
        "street":            "Hauptstraße 8",
        "plz":               "10115",
        "city":              "Berlin",
        "child_first_name":  "Maksym",
        "child_last_name":   "Kovalenko",
        "child_birth_date":  "03.04.2019",
        "iban":              "DE44500105175407324931",
    }
    normalized = normalize_user_data(raw)
    ok, missing, _ = validate_user_data("kindergeld", normalized, "en")
    missing_keys = [m["key"] for m in missing]
    assert "child_name" not in missing_keys, (
        f"child_name should be satisfied after normalization synthesis.\n"
        f"All missing: {missing_keys}"
    )


# ---------------------------------------------------------------------------
# SECTION 5: familienkasse minimal valid
# ---------------------------------------------------------------------------

def test_familienkasse_minimal_valid():
    """familienkasse with all required fields passes validation."""
    data = {
        "first_name":       "Max",
        "last_name":        "Mustermann",
        "birth_date":       "12.05.1985",
        "street":           "Musterstraße 12",
        "house_number":     "12",
        "plz":              "10115",
        "city":             "Berlin",
        "child_name":       "Anna Mustermann",
        "child_birth_date": "01.08.2020",
        "iban":             "DE44500105175407324931",
    }
    ok, missing, _ = validate_user_data("familienkasse", data, "en")
    missing_keys = [m["key"] for m in missing]
    assert ok is True, f"familienkasse validation failed — missing: {missing_keys}"


# ---------------------------------------------------------------------------
# SECTION 6: kindergeld minimal valid
# ---------------------------------------------------------------------------

def test_kindergeld_minimal_valid():
    """kindergeld with all required fields (no house_number — combined street field) passes."""
    data = {
        "first_name":       "Olena",
        "last_name":        "Kovalenko",
        "birth_date":       "15.07.1990",
        "street":           "Hauptstraße 8",
        "plz":              "10115",
        "city":             "Berlin",
        "child_name":       "Maksym Kovalenko",
        "child_birth_date": "03.04.2019",
        "iban":             "DE44500105175407324931",
    }
    ok, missing, _ = validate_user_data("kindergeld", data, "en")
    missing_keys = [m["key"] for m in missing]
    assert ok is True, f"kindergeld validation failed — missing: {missing_keys}"


# ---------------------------------------------------------------------------
# SECTION 7: ummeldung uses plain street/city (not new_street/new_city)
# ---------------------------------------------------------------------------

def test_ummeldung_uses_plain_address_fields():
    """ummeldung validator must accept street/city, not require new_street/new_city."""
    data = {
        "first_name": "Hans",
        "last_name":  "Meier",
        "birth_date": "01.01.1980",
        "street":     "Neue Straße 5",
        "plz":        "80331",
        "city":       "München",
    }
    ok, missing, _ = validate_user_data("ummeldung", data, "en")
    missing_keys = [m["key"] for m in missing]
    assert ok is True, (
        f"ummeldung validation failed with plain address fields — missing: {missing_keys}"
    )
    # Confirm old broken field names are NOT required
    assert "new_street" not in missing_keys
    assert "new_plz" not in missing_keys
    assert "new_city" not in missing_keys


# ---------------------------------------------------------------------------
# SECTION 8: aufenthaltstitel has a validator entry
# ---------------------------------------------------------------------------

def test_aufenthaltstitel_validator_entry_exists():
    """aufenthaltstitel must have an entry in _REQUIRED_FIELDS (regression guard)."""
    from backend.utils.validate import _REQUIRED_FIELDS
    assert "aufenthaltstitel" in _REQUIRED_FIELDS, (
        "aufenthaltstitel missing from _REQUIRED_FIELDS — add it to backend/utils/validate.py"
    )
    assert len(_REQUIRED_FIELDS["aufenthaltstitel"]) > 0, (
        "aufenthaltstitel _REQUIRED_FIELDS entry is empty"
    )
