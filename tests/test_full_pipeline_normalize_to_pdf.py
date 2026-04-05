# -*- coding: utf-8 -*-
"""
tests/test_full_pipeline_normalize_to_pdf.py

Full pipeline test: raw WebApp-style input → normalize → validate → build → PDF text check.

This is the only test in the suite that exercises the COMPLETE path a real user request takes:

  raw_input (camelCase / alias keys from WebApp)
      ↓ normalize_user_data()
  normalized (snake_case, PLZ/IBAN/date formatted)
      ↓ validate_user_data()
  ok=True, missing=[]
      ↓ build_german_form()
  PDF file on disk
      ↓ PyMuPDF text extraction
  assert key values survived the full journey

Catches bugs in:
  - camelCase alias mapping (_CAMEL_TO_SNAKE in normalize.py)
  - field alias resolution (ANSWER_KEY_ALIASES in document_config.py)
  - child_name synthesis (normalize.py)
  - income / monthly_income alias chain
  - postal_code / plz alias chain
  - builder silently dropping a section

Distinct from test_pdf_smoke_builder_docs.py which calls build_german_form() directly
with pre-normalized snake_case keys. This test starts from the raw frontend payload.

Usage:
  pytest tests/test_full_pipeline_normalize_to_pdf.py -v
"""
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_pipeline():
    """Import all three pipeline stages; skip test if any is unavailable."""
    try:
        from backend.utils.normalize import normalize_user_data
        from backend.utils.validate import validate_user_data
        from backend.form_builder import build_german_form, supported_doc_types
        return normalize_user_data, validate_user_data, build_german_form, supported_doc_types
    except ImportError as e:
        pytest.skip(f"Pipeline module not importable: {e}")


def _import_fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Raw WebApp payloads — keys as they come from the frontend
#
# Rules for what goes here:
#   - Use camelCase keys that are in _CAMEL_TO_SNAKE (firstName, lastName, etc.)
#   - Use alias keys that normalize/validate accept (postal_code, monthly_income)
#   - Use split child fields (child_first_name + child_last_name) to test synthesis
#   - Do NOT pre-normalize: the test must do that itself
# ---------------------------------------------------------------------------

# familienkasse — mixes camelCase top-level with snake_case child fields
_FAMILIENKASSE_RAW: Dict[str, Any] = {
    # Recognized camelCase keys (mapped by _CAMEL_TO_SNAKE)
    "firstName":   "Max",
    "lastName":    "Mustermann",
    "birthDate":   "01.01.1990",
    "postalCode":  "10115",       # → postal_code → resolved by alias chain
    # Plain snake_case keys (passed through unchanged)
    "street":      "Musterstraße",
    "house_number": "12",
    "city":        "Berlin",
    "iban":        "DE44 5001 0517 5407 3249 31",  # spaces → normalized to DE44500105175407324931
    # Split child fields → synthesized into child_name by normalize
    "child_first_name": "Anna",
    "child_last_name":  "Mustermann",
    "child_birth_date": "2020-01-01",              # ISO date → normalized to 01.01.2020
    # Optional
    "phone":       "+49 30 123456",
    "signature_date": "10.03.2026",
}

# wohngeld — income arrives as monthly_income (WebApp schema key)
_WOHNGELD_RAW: Dict[str, Any] = {
    "firstName":      "Maria",
    "lastName":       "Schmidt",
    "birthDate":      "20.03.1978",
    "postalCode":     "10243",
    "city":           "Berlin",
    "street":         "Berliner Str. 5",
    "house_number":   "5",
    "monthly_income": "1200",      # schema key; validates as income via alias
    "living_space_sqm": "55",
    "monthly_rent":   "700",
    "household_members": "2",
    "signature_date": "10.03.2026",
}

# kindergeld — child name sent as split fields; also camelCase keys
_KINDERGELD_RAW: Dict[str, Any] = {
    "firstName":        "Olena",
    "lastName":         "Kovalenko",
    "birthDate":        "1990-07-15",              # ISO → 15.07.1990
    "postalCode":       "10115",
    "city":             "Berlin",
    "street":           "Hauptstraße 8",
    "child_first_name": "Maksym",
    "child_last_name":  "Kovalenko",
    "child_birth_date": "03.04.2019",
    "iban":             "DE44500105175407324931",
    "signature_date":   "10.03.2026",
}

# ---------------------------------------------------------------------------
# Expected tokens that MUST survive the full pipeline and appear in PDF text.
# Only stable values: surnames, PLZ, city, IBAN prefix.
# Avoid fragile assertions on full sentences or field labels.
# ---------------------------------------------------------------------------

_CASES: List[Tuple[str, Dict[str, Any], List[str]]] = [
    (
        "familienkasse",
        _FAMILIENKASSE_RAW,
        ["Mustermann", "10115", "Berlin", "DE44"],
    ),
    (
        "wohngeld",
        _WOHNGELD_RAW,
        ["Schmidt", "10243", "Berlin"],
    ),
    (
        "kindergeld",
        _KINDERGELD_RAW,
        ["Kovalenko", "10115", "Berlin", "DE44"],
    ),
]

PIPELINE_CASES = [
    pytest.param(doc_type, raw, tokens, id=doc_type)
    for doc_type, raw, tokens in _CASES
]


# ---------------------------------------------------------------------------
# STEP 1 — Normalization produces snake_case output
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type,raw,_tokens", PIPELINE_CASES)
def test_normalize_converts_camelcase_keys(doc_type, raw, _tokens):
    """normalize_user_data() must convert known camelCase keys to snake_case."""
    normalize_user_data = _import_pipeline()[0]
    normalized = normalize_user_data(raw)

    # firstName / lastName must have been translated
    if "firstName" in raw:
        assert "first_name" in normalized, (
            f"[{doc_type}] 'firstName' was not converted to 'first_name'"
        )
    if "lastName" in raw:
        assert "last_name" in normalized, (
            f"[{doc_type}] 'lastName' was not converted to 'last_name'"
        )
    # postalCode must be translated (→ postal_code)
    if "postalCode" in raw:
        assert "postal_code" in normalized, (
            f"[{doc_type}] 'postalCode' was not converted to 'postal_code'"
        )


@pytest.mark.parametrize("doc_type,raw,_tokens", PIPELINE_CASES)
def test_normalize_formats_iban(doc_type, raw, _tokens):
    """normalize_user_data() must strip spaces from IBAN and uppercase it."""
    normalize_user_data = _import_pipeline()[0]

    if "iban" not in raw:
        pytest.skip(f"[{doc_type}] no IBAN in raw payload")

    normalized = normalize_user_data(raw)
    iban = str(normalized.get("iban", ""))
    assert " " not in iban, f"[{doc_type}] IBAN still has spaces after normalize: {iban!r}"
    assert iban == iban.upper(), f"[{doc_type}] IBAN not uppercased: {iban!r}"


@pytest.mark.parametrize("doc_type,raw,_tokens", PIPELINE_CASES)
def test_normalize_formats_iso_date(doc_type, raw, _tokens):
    """ISO dates (YYYY-MM-DD) in raw input must be converted to DD.MM.YYYY."""
    normalize_user_data = _import_pipeline()[0]

    iso_keys = {k: v for k, v in raw.items() if isinstance(v, str) and v[:4].isdigit() and "-" in v}
    if not iso_keys:
        pytest.skip(f"[{doc_type}] no ISO-format dates in raw payload")

    normalized = normalize_user_data(raw)
    for orig_key, iso_val in iso_keys.items():
        # The key may be camelCase in raw → snake_case after normalize
        canonical = orig_key  # if not converted, stays same
        if orig_key == "birthDate":
            canonical = "birth_date"
        norm_val = str(normalized.get(canonical, ""))
        assert re.match(r"\d{2}\.\d{2}\.\d{4}", norm_val), (
            f"[{doc_type}] ISO date '{iso_val}' not converted to DD.MM.YYYY format "
            f"(got '{norm_val}' for key '{canonical}')"
        )


@pytest.mark.parametrize("doc_type,raw,_tokens", [
    pytest.param("familienkasse", _FAMILIENKASSE_RAW, [], id="familienkasse_synthesis"),
    pytest.param("kindergeld",    _KINDERGELD_RAW,    [], id="kindergeld_synthesis"),
])
def test_normalize_synthesizes_child_name(doc_type, raw, _tokens):
    """child_first_name + child_last_name → child_name must be synthesized."""
    normalize_user_data = _import_pipeline()[0]

    if "child_first_name" not in raw and "child_last_name" not in raw:
        pytest.skip(f"[{doc_type}] no split child name fields in raw payload")

    normalized = normalize_user_data(raw)
    assert "child_name" in normalized, (
        f"[{doc_type}] child_name was not synthesized from child_first_name + child_last_name"
    )
    fn = str(raw.get("child_first_name", "")).strip()
    ln = str(raw.get("child_last_name", "")).strip()
    expected = " ".join(p for p in [fn, ln] if p)
    assert normalized["child_name"] == expected, (
        f"[{doc_type}] synthesized child_name is '{normalized['child_name']}', expected '{expected}'"
    )


# ---------------------------------------------------------------------------
# STEP 2 — Validation passes after normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type,raw,_tokens", PIPELINE_CASES)
def test_validate_passes_after_normalize(doc_type, raw, _tokens):
    """After normalization, validate_user_data() must return ok=True."""
    normalize_user_data, validate_user_data, _, __ = _import_pipeline()

    normalized = normalize_user_data(raw)
    ok, missing, warnings = validate_user_data(doc_type, normalized, lang="en")
    missing_keys = [m["key"] for m in missing]
    assert ok is True, (
        f"[{doc_type}] Validation failed after normalization.\n"
        f"Missing required fields: {missing_keys}\n"
        f"Normalized keys available: {sorted(normalized.keys())}"
    )


# ---------------------------------------------------------------------------
# STEP 3 — PDF is generated from normalized data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type,raw,_tokens", PIPELINE_CASES)
def test_pdf_generated_from_normalized_input(doc_type, raw, _tokens, tmp_path):
    """build_german_form() must produce a valid PDF from normalize_user_data() output."""
    normalize_user_data, _validate, build_german_form, supported_doc_types = _import_pipeline()

    if doc_type not in supported_doc_types():
        pytest.skip(f"'{doc_type}' not in supported_doc_types()")

    normalized = normalize_user_data(raw)
    output = str(tmp_path / f"{doc_type}_pipeline.pdf")
    result = build_german_form(
        doc_type=doc_type,
        user_data=normalized,
        output_path=output,
        is_preview=True,
        user_lang="de",
    )

    assert result is not None, (
        f"[{doc_type}] build_german_form returned None after full pipeline.\n"
        f"Normalized keys: {sorted(normalized.keys())}"
    )
    pdf_path = Path(result)
    assert pdf_path.exists(), f"[{doc_type}] PDF file not found at {result}"
    assert pdf_path.stat().st_size > 5000, (
        f"[{doc_type}] PDF is suspiciously small ({pdf_path.stat().st_size} bytes)"
    )


# ---------------------------------------------------------------------------
# STEP 4 — Round-trip: user values survive into PDF text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type,raw,expected_tokens", PIPELINE_CASES)
def test_user_data_survives_full_pipeline_to_pdf_text(doc_type, raw, expected_tokens, tmp_path):
    """
    Core round-trip test: values from raw input must be readable in extracted PDF text.

    This is the only test that exercises the complete path:
      raw frontend input → normalize → build → PDF → text extraction
    """
    fitz = _import_fitz()
    if fitz is None:
        pytest.skip("PyMuPDF (fitz) not installed — skipping round-trip text check")

    normalize_user_data, _validate, build_german_form, supported_doc_types = _import_pipeline()

    if doc_type not in supported_doc_types():
        pytest.skip(f"'{doc_type}' not in supported_doc_types()")

    normalized = normalize_user_data(raw)
    output = str(tmp_path / f"{doc_type}_roundtrip.pdf")
    result = build_german_form(
        doc_type=doc_type,
        user_data=normalized,
        output_path=output,
        is_preview=True,
        user_lang="de",
    )

    assert result is not None, f"[{doc_type}] build_german_form returned None"

    doc = fitz.open(result)
    full_text = "".join(page.get_text() for page in doc)
    doc.close()

    missing = [token for token in expected_tokens if token not in full_text]
    assert not missing, (
        f"[{doc_type}] These values were NOT found in the final PDF after full pipeline:\n"
        f"  Missing: {missing}\n"
        f"  All expected: {expected_tokens}\n"
        f"  PDF text (first 600 chars): {full_text[:600]}"
    )


# ---------------------------------------------------------------------------
# Import needed for ISO date check
# ---------------------------------------------------------------------------
import re
