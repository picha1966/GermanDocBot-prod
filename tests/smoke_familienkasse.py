#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke test — familienkasse PDF builder.

Runs the full pipeline:
  validate_user_data → build_german_form (preview + final)

Output:
  outputs/smoke/familienkasse_preview.pdf
  outputs/smoke/familienkasse_final.pdf

Usage:
  python tests/smoke_familienkasse.py
"""

import sys
import os
from pathlib import Path

# ── Project root on sys.path ─────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "outputs" / "smoke"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PREVIEW_PATH = str(OUTPUT_DIR / "familienkasse_preview.pdf")
FINAL_PATH   = str(OUTPUT_DIR / "familienkasse_final.pdf")

# ── Minimal required payload ─────────────────────────────────────────────────
PAYLOAD = {
    "first_name":       "Max",
    "last_name":        "Mustermann",
    "birth_date":       "1990-05-12",
    "street":           "Musterstraße",
    "house_number":     "12",
    "plz":              "10115",
    "city":             "Berlin",
    "child_name":       "Anna Mustermann",
    "child_birth_date": "2022-08-01",
    "iban":             "DE44500105175407324931",
    # optional but realistic
    "phone":            "+4930123456",
    "tax_id":           "12345678901",
    "child_birth_place": "Berlin",
    "child_nationality": "Deutsch",
    "bank_name":        "Sparkasse Berlin",
    "signature_place":  "Berlin",
    "signature_date":   "10.03.2026",
}

LANG = "de"
DOC_TYPE = "familienkasse"

# ── Expected sections (used for content check) ────────────────────────────────
EXPECTED_SECTIONS = [
    "Angaben zum Antragsteller",
    "Kind",
    "Bankverbindung",
    "Unterschrift",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"  OK  {msg}")

def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")

def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Step 1: validate_user_data ────────────────────────────────────────────────

def step_validate() -> bool:
    _section("STEP 1 — validate_user_data")
    try:
        from backend.utils.validate import validate_user_data
        _ok("validate_user_data imported")
    except ImportError as e:
        _fail(f"Import failed: {e}")
        return False

    try:
        ok, missing, warnings = validate_user_data(DOC_TYPE, PAYLOAD, LANG)
    except Exception as e:
        _fail(f"validate_user_data raised: {e}")
        return False

    if ok:
        _ok(f"Validation passed  (missing={missing}, warnings={[w['key'] for w in warnings]})")
    else:
        missing_keys = [m["key"] for m in missing]
        _fail(f"Validation failed — missing required fields: {missing_keys}")
        return False

    if warnings:
        for w in warnings:
            print(f"       WARN  {w['key']}: {w.get('message', '')}")

    return True


# ── Step 2: build_german_form — preview mode ──────────────────────────────────

def step_preview() -> bool:
    _section("STEP 2 — build_german_form (preview)")
    try:
        from backend.form_builder import build_german_form, supported_doc_types
        _ok("build_german_form imported")
    except ImportError as e:
        _fail(f"Import failed: {e}")
        return False

    if DOC_TYPE not in supported_doc_types():
        _fail(f"'{DOC_TYPE}' not in supported_doc_types() — missing from _DOC_META")
        return False
    _ok(f"'{DOC_TYPE}' is in supported_doc_types()")

    try:
        result = build_german_form(
            doc_type=DOC_TYPE,
            user_data=PAYLOAD,
            output_path=PREVIEW_PATH,
            is_preview=True,
            user_lang=LANG,
        )
    except Exception as e:
        _fail(f"build_german_form raised: {e}")
        import traceback
        traceback.print_exc()
        return False

    if not result:
        _fail("build_german_form returned None")
        return False

    pdf_path = Path(result)
    if not pdf_path.exists():
        _fail(f"Output file not created: {result}")
        return False

    size_kb = pdf_path.stat().st_size / 1024
    _ok(f"Preview PDF created: {result}  ({size_kb:.1f} KB)")

    if size_kb < 5:
        _fail(f"PDF is suspiciously small ({size_kb:.1f} KB) — may be empty")
        return False

    return True


# ── Step 3: build_german_form — final mode ────────────────────────────────────

def step_final() -> bool:
    _section("STEP 3 — build_german_form (final)")
    try:
        from backend.form_builder import build_german_form
    except ImportError as e:
        _fail(f"Import failed: {e}")
        return False

    try:
        result = build_german_form(
            doc_type=DOC_TYPE,
            user_data=PAYLOAD,
            output_path=FINAL_PATH,
            is_preview=False,
            user_lang=LANG,
            official_link="https://www.arbeitsagentur.de/familie-und-kinder/kindergeld",
        )
    except Exception as e:
        _fail(f"build_german_form (final) raised: {e}")
        import traceback
        traceback.print_exc()
        return False

    if not result:
        _fail("build_german_form (final) returned None")
        return False

    pdf_path = Path(result)
    if not pdf_path.exists():
        _fail(f"Output file not created: {result}")
        return False

    size_kb = pdf_path.stat().st_size / 1024
    _ok(f"Final PDF created: {result}  ({size_kb:.1f} KB)")

    if size_kb < 5:
        _fail(f"PDF is suspiciously small ({size_kb:.1f} KB) — may be empty")
        return False

    return True


# ── Step 4: content verification via PyMuPDF ─────────────────────────────────

def step_content_check() -> bool:
    _section("STEP 4 — content check (PyMuPDF text extraction)")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("       SKIP  PyMuPDF not installed — skipping text extraction check")
        return True

    preview_path = Path(PREVIEW_PATH)
    if not preview_path.exists():
        _fail(f"Preview PDF not found at {PREVIEW_PATH} — run step 2 first")
        return False

    try:
        doc = fitz.open(str(preview_path))
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()
    except Exception as e:
        _fail(f"PyMuPDF failed to open PDF: {e}")
        return False

    all_ok = True

    # Check key user data appears in the PDF
    checks = {
        "first_name":  "Max",
        "last_name":   "Mustermann",
        "plz":         "10115",
        "city":        "Berlin",
        "child_name":  "Anna",
        "iban":        "DE44",
    }
    for field, expected in checks.items():
        if expected in full_text:
            _ok(f"Field '{field}' value '{expected}' found in PDF")
        else:
            _fail(f"Field '{field}' value '{expected}' NOT found in PDF text")
            all_ok = False

    # Check section titles
    for section in EXPECTED_SECTIONS:
        if section in full_text:
            _ok(f"Section '{section}' found in PDF")
        else:
            _fail(f"Section '{section}' NOT found in PDF text")
            all_ok = False

    return all_ok


# ── Step 5: _DOC_SECTIONS field coverage cross-check ─────────────────────────

def step_field_coverage() -> bool:
    _section("STEP 5 — field coverage cross-check")
    try:
        from backend.form_builder import _DOC_SECTIONS
        from backend.utils.validate import _REQUIRED_FIELDS, _WARNING_FIELDS
    except ImportError as e:
        _fail(f"Import failed: {e}")
        return False

    sections = _DOC_SECTIONS.get(DOC_TYPE)
    if not sections:
        _fail(f"_DOC_SECTIONS['{DOC_TYPE}'] is empty or missing")
        return False

    section_fields = set()
    for _title, fields in sections:
        for field_key, _label in fields:
            section_fields.add(field_key)

    required = set(_REQUIRED_FIELDS.get(DOC_TYPE, []))
    warnings = set(_WARNING_FIELDS.get(DOC_TYPE, []))
    validated = required | warnings

    # Every required/warning field should appear in sections
    missing_in_sections = validated - section_fields
    if missing_in_sections:
        _fail(f"Fields in validate but NOT in _DOC_SECTIONS: {missing_in_sections}")
        return False
    _ok(f"All {len(validated)} validated fields present in _DOC_SECTIONS")

    # Optional: fields in sections but not validated (informational only)
    extra_in_sections = section_fields - validated
    if extra_in_sections:
        print(f"       INFO  Optional fields (in sections, not validated): {extra_in_sections}")

    _ok(f"Section fields total: {len(section_fields)}, required: {len(required)}, warnings: {len(warnings)}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("\n" + "#" * 60)
    print("  SMOKE TEST — familienkasse PDF builder")
    print("#" * 60)
    print(f"  doc_type : {DOC_TYPE}")
    print(f"  lang     : {LANG}")
    print(f"  output   : {OUTPUT_DIR}")
    print("#" * 60)

    steps = [
        ("Validate",        step_validate),
        ("Preview PDF",     step_preview),
        ("Final PDF",       step_final),
        ("Content check",   step_content_check),
        ("Field coverage",  step_field_coverage),
    ]

    results = {}
    for name, fn in steps:
        try:
            results[name] = fn()
        except Exception as e:
            _fail(f"Unexpected exception in step '{name}': {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    all_passed = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        marker = "OK" if passed else "!!"
        print(f"  [{marker}] {status:<8}  {name}")
        if not passed:
            all_passed = False

    print(f"\n  {'ALL STEPS PASSED' if all_passed else 'SOME STEPS FAILED'}")

    if all_passed:
        print(f"\n  Preview : {PREVIEW_PATH}")
        print(f"  Final   : {FINAL_PATH}")

    print("=" * 60 + "\n")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
