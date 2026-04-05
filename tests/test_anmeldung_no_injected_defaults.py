# -*- coding: utf-8 -*-
"""
tests/test_anmeldung_no_injected_defaults.py

Regression test: Anmeldung PDF must NEVER contain values that the user
did not provide.

Specifically guards against the class of bug where ANMELDUNG_COMPLETION_DEFAULTS
contained real personal/address data that was injected into every PDF regardless
of user input (e.g. "Hmelnytskoho 12" appeared in bisherige Wohnung even when
the user never entered a previous address).

The test strategy:
  - Feed minimal user_data with NO previous-address fields.
  - Generate a final PDF (not preview, so completion logic runs).
  - Extract PDF text.
  - Assert that none of the historically-injected values appear.
  - Assert that the user's own values DO appear (sanity check).

Usage:
    pytest tests/test_anmeldung_no_injected_defaults.py -v
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_builder():
    try:
        from backend.form_builder import build_german_form, supported_doc_types
        return build_german_form, supported_doc_types
    except ImportError as e:
        pytest.skip(f"form_builder not importable: {e}")


def _import_fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        return None


def _import_completion():
    try:
        from backend.document_config import apply_anmeldung_completion
        return apply_anmeldung_completion
    except ImportError as e:
        pytest.skip(f"document_config not importable: {e}")


# ---------------------------------------------------------------------------
# Minimal Anmeldung payload — no previous address, no bisherige Wohnung.
# Represents the most common case: user arriving from abroad (first registration).
# ---------------------------------------------------------------------------

_MINIMAL_ANMELDUNG: dict = {
    # Neue Wohnung
    "street":        "Hauptstraße",
    "house_number":  "7",
    "plz":           "10965",
    "city":          "Berlin",
    "move_in_date":  "01.03.2026",
    "wohnungstyp":   "Hauptwohnung",
    # Person
    "first_name":    "Olena",
    "last_name":     "Kovalenko",
    "birth_date":    "15.07.1990",
    "birth_place":   "Kyiv, Ukraine",
    "nationality":   "Ukraine",
    "gender":        "f",
    # Landlord (required)
    "landlord_name":         "Hans Meier",
    "landlord_street":       "Nebenstraße",
    "landlord_house_number": "3",
    "landlord_plz":          "10965",
    "landlord_city":         "Berlin",
    # Document
    "dokumentenart":      "RP",
    "ausstellungsbehoerde": "Stadt Kyiv",
    "seriennummer":         "AA123456",
    "ausstellungsdatum":    "01.01.2020",
    "gueltig_bis":          "01.01.2030",
    "signature_date":       "10.03.2026",
}

# Values that were historically injected from ANMELDUNG_COMPLETION_DEFAULTS
# and must NEVER appear in a PDF generated from _MINIMAL_ANMELDUNG.
_FORMERLY_INJECTED = [
    "Hmelnytskoho",   # previous_strasse default
    "Vinnytsia",      # previous_ort + birth_place default
    "Pichkur",        # last_name default
    "Vitalii",        # first_name default (as developer test data)
    "18.07.1966",     # birth_date default
    "21000",          # previous_plz default
    "18.07.2022",     # move_out_date default
]

# Values from _MINIMAL_ANMELDUNG that MUST appear in the PDF (sanity check).
_EXPECTED_IN_PDF = [
    "Kovalenko",
    "Olena",
    "Hauptstraße",
    "10965",
]


# ---------------------------------------------------------------------------
# Unit: apply_anmeldung_completion must not inject previous-address defaults
# ---------------------------------------------------------------------------

def test_completion_does_not_inject_previous_address():
    """
    apply_anmeldung_completion() must not add previous_strasse / previous_hausnummer
    when the user did not provide them.
    """
    apply = _import_completion()
    result = apply(_MINIMAL_ANMELDUNG)

    assert result.get("previous_strasse") is None or result.get("previous_strasse") == "", (
        f"previous_strasse was injected by defaults: {result.get('previous_strasse')!r}"
    )
    assert result.get("previous_hausnummer") is None or result.get("previous_hausnummer") == "", (
        f"previous_hausnummer was injected by defaults: {result.get('previous_hausnummer')!r}"
    )
    assert result.get("previous_ort") is None or result.get("previous_ort") == "", (
        f"previous_ort was injected by defaults: {result.get('previous_ort')!r}"
    )
    assert result.get("previous_plz") is None or result.get("previous_plz") == "", (
        f"previous_plz was injected by defaults: {result.get('previous_plz')!r}"
    )


def test_completion_defaults_has_bisherige_wohnung_nein():
    """
    When user does not specify has_bisherige_wohnung, it must default to 'Nein',
    not 'Ja' (which would trigger the previous-address section in the PDF).
    """
    apply = _import_completion()

    # Feed data without has_bisherige_wohnung
    data_without_flag = {k: v for k, v in _MINIMAL_ANMELDUNG.items()
                         if k != "has_bisherige_wohnung"}
    result = apply(data_without_flag)

    val = result.get("has_bisherige_wohnung", "")
    assert val == "Nein", (
        f"has_bisherige_wohnung defaults to {val!r} — expected 'Nein'. "
        f"A 'Ja' default would cause previous-address fields to be rendered."
    )


def test_completion_preserves_user_last_name():
    """User-provided last_name must not be overwritten by a default."""
    apply = _import_completion()
    result = apply(_MINIMAL_ANMELDUNG)
    assert result.get("last_name") == "Kovalenko", (
        f"last_name was overwritten: {result.get('last_name')!r}"
    )


def test_completion_preserves_user_first_name():
    """User-provided first_name must not be overwritten by a default."""
    apply = _import_completion()
    result = apply(_MINIMAL_ANMELDUNG)
    assert result.get("first_name") == "Olena", (
        f"first_name was overwritten: {result.get('first_name')!r}"
    )


# ---------------------------------------------------------------------------
# Integration: PDF text must not contain formerly-injected values
# ---------------------------------------------------------------------------

def test_anmeldung_pdf_contains_no_injected_defaults(tmp_path):
    """
    Full-pipeline regression: generate a final Anmeldung PDF from minimal user
    input and assert none of the historically-injected default values appear.
    """
    fitz = _import_fitz()
    if fitz is None:
        pytest.skip("PyMuPDF (fitz) not installed — skipping PDF text check")

    build_german_form, supported_doc_types = _import_builder()
    if "anmeldung" not in supported_doc_types():
        pytest.skip("'anmeldung' not in supported_doc_types()")

    output = str(tmp_path / "anmeldung_injection_test.pdf")
    result = build_german_form(
        doc_type="anmeldung",
        user_data=_MINIMAL_ANMELDUNG,
        output_path=output,
        is_preview=False,   # final mode so apply_anmeldung_completion runs
        user_lang="de",
    )
    assert result is not None, "build_german_form returned None"

    doc = fitz.open(result)
    full_text = "".join(page.get_text() for page in doc)
    doc.close()

    injected = [v for v in _FORMERLY_INJECTED if v in full_text]
    assert not injected, (
        f"Formerly-injected default values found in Anmeldung PDF:\n"
        f"  Found: {injected}\n"
        f"  These must never appear when not provided by the user.\n"
        f"  PDF text (first 800 chars): {full_text[:800]}"
    )


def test_anmeldung_pdf_contains_user_values(tmp_path):
    """
    Sanity check: user-provided values must actually appear in the PDF.
    If this fails, the builder dropped the user's data entirely.
    """
    fitz = _import_fitz()
    if fitz is None:
        pytest.skip("PyMuPDF (fitz) not installed — skipping PDF text check")

    build_german_form, supported_doc_types = _import_builder()
    if "anmeldung" not in supported_doc_types():
        pytest.skip("'anmeldung' not in supported_doc_types()")

    output = str(tmp_path / "anmeldung_sanity_test.pdf")
    result = build_german_form(
        doc_type="anmeldung",
        user_data=_MINIMAL_ANMELDUNG,
        output_path=output,
        is_preview=False,
        user_lang="de",
    )
    assert result is not None, "build_german_form returned None"

    doc = fitz.open(result)
    full_text = "".join(page.get_text() for page in doc)
    doc.close()

    missing = [v for v in _EXPECTED_IN_PDF if v not in full_text]
    assert not missing, (
        f"User-provided values missing from Anmeldung PDF:\n"
        f"  Missing: {missing}\n"
        f"  Expected all of: {_EXPECTED_IN_PDF}\n"
        f"  PDF text (first 800 chars): {full_text[:800]}"
    )
