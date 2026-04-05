# -*- coding: utf-8 -*-
"""
tests/test_pdf_smoke_builder_docs.py

Smoke tests for builder-strategy PDF documents.
Only tests documents that do NOT require physical AcroForm template files.

Documents tested:
  familienkasse                  — builder
  wohngeld                       — builder
  kindergeld                     — xfa → falls back to builder
  abmeldung                      — builder
  aufenthaltstitel               — builder
  verlaengerung_aufenthaltstitel — builder
  buergergeld                    — builder
  anmeldung                      — acroform overlay

Usage:
  pytest tests/test_pdf_smoke_builder_docs.py -v
"""
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Fixtures (sample payloads — minimal valid data for each doc_type)
# ---------------------------------------------------------------------------

_FAMILIENKASSE_DATA: Dict[str, Any] = {
    "first_name":        "Max",
    "last_name":         "Mustermann",
    "birth_date":        "12.05.1985",
    "street":            "Musterstraße 12",
    "house_number":      "12",
    "plz":               "10115",
    "city":              "Berlin",
    "child_name":        "Anna Mustermann",
    "child_birth_date":  "01.08.2020",
    "iban":              "DE44500105175407324931",
    "signature_date":    "10.03.2026",
    # optional
    "phone":             "+4930123456",
    "tax_id":            "12345678901",
    "child_birth_place": "Berlin",
    "bank_name":         "Sparkasse Berlin",
    "signature_place":   "Berlin",
}

_WOHNGELD_DATA: Dict[str, Any] = {
    "first_name":         "Maria",
    "last_name":          "Schmidt",
    "birth_date":         "20.03.1978",
    "street":             "Berliner Str. 5",
    "house_number":       "5",
    "plz":                "10243",
    "city":               "Berlin",
    "monthly_income":     "1200",    # resolves via income alias
    "living_space_sqm":   "55",
    "monthly_rent":       "700",
    "household_members":  "2",
    "signature_date":     "10.03.2026",
    # optional
    "nationality":        "ukrainisch",
    "dwelling_type":      "Mietwohnung",
    "signature_place":    "Berlin",
}

_KINDERGELD_DATA: Dict[str, Any] = {
    "first_name":         "Olena",
    "last_name":          "Kovalenko",
    "birth_date":         "15.07.1990",
    "street":             "Hauptstraße 8",
    "plz":                "10115",
    "city":               "Berlin",
    "child_name":         "Maksym Kovalenko",
    "child_birth_date":   "03.04.2019",
    "child_birth_place":  "Kyiv",
    "iban":               "DE44500105175407324931",
    "signature_date":     "10.03.2026",
    # optional
    "tax_id":             "98765432100",
    "bank_name":          "Deutsche Bank",
    "account_holder":     "Olena Kovalenko",
    "signature_place":    "Berlin",
}

_ABMELDUNG_DATA: Dict[str, Any] = {
    "first_name":       "Klaus",
    "last_name":        "Weber",
    "birth_date":       "22.09.1975",
    "street":           "Hauptstraße",
    "house_number":     "5",
    "plz":              "10115",
    "city":             "Berlin",
    "move_out_date":    "01.04.2026",
    "signature_date":   "15.03.2026",
    # optional
    "birth_place":      "Hamburg",
    "nationality":      "deutsch",
    "gender":           "m",
    "new_street":       "Bahnhofstraße",
    "new_house_number": "10",
    "new_plz":          "80331",
    "new_city":         "München",
    "signature_place":  "Berlin",
}

_AUFENTHALTSTITEL_DATA: Dict[str, Any] = {
    "first_name":            "Andriy",
    "last_name":             "Melnyk",
    "birth_date":            "10.06.1988",
    "birth_place":           "Kyiv, Ukraine",
    "nationality":           "ukrainisch",
    "postal_code":           "10117",
    "city":                  "Berlin",
    "street":                "Unter den Linden",
    "house_number":          "77",
    "dokumentenart":         "RP",
    "seriennummer":          "UA123456789",
    "ausstellungsbehoerde":  "Standesamt Kyiv",
    "ausstellungsdatum":     "01.01.2020",
    "gueltig_bis":           "01.01.2030",
    "residence_purpose":     "Arbeit",
    "signature_date":        "15.03.2026",
    # optional
    "gender":                "m",
    "visa_type":             "Aufenthaltserlaubnis",
    "entry_date":            "15.03.2022",
    "employer_name":         "Tech GmbH",
    "occupation":            "Softwareentwickler",
    "signature_place":       "Berlin",
}

_VERLAENGERUNG_DATA: Dict[str, Any] = {
    "first_name":            "Iryna",
    "last_name":             "Bondarenko",
    "birth_date":            "05.03.1992",
    "birth_place":           "Lviv, Ukraine",
    "nationality":           "ukrainisch",
    "postal_code":           "10243",
    "city":                  "Berlin",
    "street":                "Karl-Marx-Allee",
    "house_number":          "12",
    "dokumentenart":         "RP",
    "seriennummer":          "UA987654321",
    "ausstellungsbehoerde":  "Amt Lviv",
    "ausstellungsdatum":     "15.06.2019",
    "gueltig_bis":           "15.06.2029",
    "residence_purpose":     "Studium",
    "signature_date":        "15.03.2026",
    # optional
    "current_permit_type":   "Aufenthaltserlaubnis",
    "permit_expiry_date":    "01.06.2026",
    "visa_type":             "Aufenthaltserlaubnis",
    "signature_place":       "Berlin",
}

_BUERGERGELD_DATA: Dict[str, Any] = {
    "first_name":        "Thomas",
    "last_name":         "Fischer",
    "birth_date":        "18.11.1980",
    "street":            "Ringstraße 3",
    "postal_code":       "13353",
    "city":              "Berlin",
    "household_members": "2",
    "monthly_rent":      "650",
    "iban":              "DE44500105175407324931",
    "signature_date":    "15.03.2026",
    # optional
    "birth_place":       "Dresden",
    "nationality":       "deutsch",
    "family_status":     "ledig",
    "employment_status": "arbeitslos",
    "monthly_income":    "0",
    "heating_costs":     "80",
    "additional_costs":  "120",
    "bank_name":         "Commerzbank",
    "signature_place":   "Berlin",
}

_ANMELDUNG_DATA: Dict[str, Any] = {
    # Neue Wohnung
    "wohnungstyp":           "Hauptwohnung",
    "move_in_date":          "01.03.2026",
    "plz":                   "10965",
    "city":                  "Berlin",
    "street":                "Hauptstraße",
    "house_number":          "7",
    # Bisherige Wohnung
    "has_bisherige_wohnung": "Nein",
    "weitere_wohnungen":     "Nein",
    # Person 1
    "first_name":            "Max",
    "last_name":             "Mustermann",
    "birth_date":            "01.01.1990",
    "birth_place":           "Hamburg",
    "nationality":           "deutsch",
    "gender":                "m",
    # Landlord (required)
    "landlord_name":         "Hans Meier",
    "landlord_street":       "Nebenstraße",
    "landlord_house_number": "3",
    "landlord_plz":          "10965",
    "landlord_city":         "Berlin",
    # Document (required)
    "dokumentenart":         "RP",
    "ausstellungsbehoerde":  "Standesamt Hamburg",
    "seriennummer":          "C1A2B3C4D5",
    "ausstellungsdatum":     "01.01.2015",
    "gueltig_bis":           "01.01.2030",
    "signature_date":        "10.03.2026",
    # optional
    "signature_place":       "Berlin",
}

# ---------------------------------------------------------------------------
# Parametrize: doc_type → (payload, texts_that_must_appear_in_pdf)
# ---------------------------------------------------------------------------

BUILDER_DOC_CASES = [
    pytest.param(
        "familienkasse",
        _FAMILIENKASSE_DATA,
        ["Mustermann", "10115", "Anna", "DE44"],
        id="familienkasse",
    ),
    pytest.param(
        "wohngeld",
        _WOHNGELD_DATA,
        ["Schmidt", "10243", "Berlin"],
        id="wohngeld",
    ),
    pytest.param(
        "kindergeld",
        _KINDERGELD_DATA,
        ["Kovalenko", "10115", "DE44"],
        id="kindergeld",
    ),
    pytest.param(
        "abmeldung",
        _ABMELDUNG_DATA,
        ["Weber", "10115", "Berlin"],
        id="abmeldung",
    ),
    pytest.param(
        "aufenthaltstitel",
        _AUFENTHALTSTITEL_DATA,
        ["Melnyk", "10117", "Berlin"],
        id="aufenthaltstitel",
    ),
    pytest.param(
        "verlaengerung_aufenthaltstitel",
        _VERLAENGERUNG_DATA,
        ["Bondarenko", "10243", "Berlin"],
        id="verlaengerung_aufenthaltstitel",
    ),
    pytest.param(
        "buergergeld",
        _BUERGERGELD_DATA,
        ["Fischer", "13353", "Berlin"],
        id="buergergeld",
    ),
    pytest.param(
        "anmeldung",
        _ANMELDUNG_DATA,
        ["Mustermann", "Hauptstraße", "10965"],
        id="anmeldung",
    ),
]


# ---------------------------------------------------------------------------
# Helper: skip gracefully if builder not available
# ---------------------------------------------------------------------------

def _import_builder():
    try:
        from backend.form_builder import build_german_form, supported_doc_types
        return build_german_form, supported_doc_types
    except ImportError as e:
        pytest.skip(f"form_builder not importable: {e}")


def _import_fitz():
    try:
        import fitz  # PyMuPDF
        return fitz
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type,payload,expected_texts", BUILDER_DOC_CASES)
def test_builder_preview_pdf_generated(doc_type, payload, expected_texts, tmp_path):
    """Preview PDF must be created and be non-trivially sized."""
    build_german_form, supported_doc_types = _import_builder()

    if doc_type not in supported_doc_types():
        pytest.skip(f"'{doc_type}' not in supported_doc_types()")

    output = str(tmp_path / f"{doc_type}_preview.pdf")
    result = build_german_form(
        doc_type=doc_type,
        user_data=payload,
        output_path=output,
        is_preview=True,
        user_lang="de",
    )

    assert result is not None, f"build_german_form returned None for {doc_type}"
    pdf_path = Path(result)
    assert pdf_path.exists(), f"PDF file not created at {result}"
    size_bytes = pdf_path.stat().st_size
    assert size_bytes > 5000, (
        f"Preview PDF for {doc_type} is too small ({size_bytes} bytes) — likely empty"
    )


@pytest.mark.parametrize("doc_type,payload,expected_texts", BUILDER_DOC_CASES)
def test_builder_final_pdf_generated(doc_type, payload, expected_texts, tmp_path):
    """Final (non-preview) PDF must be created and be non-trivially sized."""
    build_german_form, supported_doc_types = _import_builder()

    if doc_type not in supported_doc_types():
        pytest.skip(f"'{doc_type}' not in supported_doc_types()")

    output = str(tmp_path / f"{doc_type}_final.pdf")
    result = build_german_form(
        doc_type=doc_type,
        user_data=payload,
        output_path=output,
        is_preview=False,
        user_lang="de",
    )

    assert result is not None, f"build_german_form (final) returned None for {doc_type}"
    pdf_path = Path(result)
    assert pdf_path.exists(), f"PDF file not created at {result}"
    size_bytes = pdf_path.stat().st_size
    assert size_bytes > 5000, (
        f"Final PDF for {doc_type} is too small ({size_bytes} bytes) — likely empty"
    )


@pytest.mark.parametrize("doc_type,payload,expected_texts", BUILDER_DOC_CASES)
def test_builder_pdf_contains_user_data(doc_type, payload, expected_texts, tmp_path):
    """Preview PDF must contain user-provided values (text extraction via PyMuPDF)."""
    fitz = _import_fitz()
    if fitz is None:
        pytest.skip("PyMuPDF (fitz) not installed — skipping text extraction check")

    build_german_form, supported_doc_types = _import_builder()

    if doc_type not in supported_doc_types():
        pytest.skip(f"'{doc_type}' not in supported_doc_types()")

    output = str(tmp_path / f"{doc_type}_textcheck.pdf")
    result = build_german_form(
        doc_type=doc_type,
        user_data=payload,
        output_path=output,
        is_preview=True,
        user_lang="de",
    )

    assert result is not None, f"build_german_form returned None for {doc_type}"

    doc = fitz.open(result)
    full_text = "".join(page.get_text() for page in doc)
    doc.close()

    missing_in_pdf = [t for t in expected_texts if t not in full_text]
    assert not missing_in_pdf, (
        f"[{doc_type}] Expected values not found in PDF text: {missing_in_pdf}\n"
        f"PDF text excerpt (first 500 chars): {full_text[:500]}"
    )
