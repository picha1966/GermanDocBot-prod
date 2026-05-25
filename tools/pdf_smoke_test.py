#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/pdf_smoke_test.py — Generate preview + final PDF for all universal doc_types.

Usage:
    python tools/pdf_smoke_test.py
    python tools/pdf_smoke_test.py --lang uk --out outputs/smoke
    python tools/pdf_smoke_test.py --doc anmeldung            (single doc)
    python tools/pdf_smoke_test.py --final-only               (skip preview)

What "universal" means: resolves with bundesland=None (no region required).
Missing-field errors are treated as PASS for the smoke test (validation is working).

Output (per doc_type):
    PASS preview  anmeldung   → outputs/smoke/anmeldung_preview.pdf
    PASS final    anmeldung   → outputs/smoke/anmeldung_final.pdf
    SKIP final    wbs         → validation_failed (missing: first_name, last_name, ...)
    FAIL preview  bafoeg      → exception: ...
"""
import argparse
import os
import sys
import shutil
import traceback
from pathlib import Path
from typing import Optional

_DISCLAIMER_TEXT = "NICHT OFFIZIELLES DOKUMENT - NUR ZUR VORBEREITUNG"


def _pdf_has_disclaimer(pdf_path: str) -> bool:
    """Return True if the PDF contains the mandatory red disclaimer text."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        for page in doc:
            if _DISCLAIMER_TEXT in page.get_text():
                doc.close()
                return True
        doc.close()
    except Exception:
        pass
    return False

_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPT_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Test data ─────────────────────────────────────────────────────────────────
# Comprehensive fixture covering the most common required fields.
_TEST_USER_DATA = {
    "user_id":              99999,
    "first_name":           "Maria",
    "last_name":            "Musterfrau",
    "birth_date":           "1990-05-15",           # will be normalized to 15.05.1990
    "birth_place":          "Kyiv",                 # required by legacy anmeldung validator
    "birth_name":           "Mustermädchen",
    "street":               "Musterstrasse",          # latin only (legacy anmeldung validator)
    "house_number":         "12A",
    "plz":                  "10115",
    "city":                 "Berlin",
    "nationality":          "Ukrainisch",
    "gender":               "weiblich",
    "family_status":        "ledig",
    "move_in_date":         "2024-01-01",
    "landlord_name":        "Hans Vermieter",
    "landlord_address":     "Berliner Str. 5, 10115 Berlin",
    "phone":                "+4930 123456",          # will be normalized
    "email":                "maria@example.de",
    "iban":                 "DE89 3704 0044 0532 0130 00",  # will be normalized
    "tax_id":               "12 345 678 901",
    "income":               "1800",
    "employer_name":        "Muster GmbH",
    "child_name":           "Leo Musterfrau",
    "child_first_name":     "Leo",
    "child_last_name":      "Musterfrau",
    "child_birth_date":     "2020-03-10",
    "new_street":           "Neue Straße",
    "new_house_number":     "7B",
    "new_plz":              "12345",
    "new_city":             "München",
    "bundesland":           None,                    # universal (no region)
    # ── Anmeldung: required by legacy form_validation ────────────────────────
    "dokumentenart":        "RP",                   # enum value: RP=Reisepass, PA=Personalausweis
    "ausstellungsbehoerde": "Botschaft Kyiv",
    "seriennummer":         "XY123456",
    "ausstellungsdatum":    "01.01.2020",
    "gueltig_bis":          "01.01.2030",
    "weitere_wohnungen":    "Nein",
    "wohnungstyp":          "Hauptwohnung",
    "has_bisherige_wohnung": "Nein",
    # ── Jobcenter / Bürgergeld: additional helpful fields ────────────────────
    "signature_date":       "18.02.2026",
    "signature_place":      "Berlin",
    # ── BAföG: training details ───────────────────────────────────────────────
    "bafoeg_schule":        "Freie Universität Berlin",
    "bafoeg_fachrichtung":  "Informatik",
    "bafoeg_abschluss":     "Bachelor of Science",
}

# ── Universal doc_types (resolve without bundesland) ──────────────────────────
_UNIVERSAL_DOCS = [
    "anmeldung",
    "ummeldung",
    "abmeldung",
    "wohnungsgeberbestaetigung",
    "kindergeld",
    "kindergeld_anlage",
    "verpflichtungserklaerung",
    "mietbescheinigung",
    "bafoeg",
    "kinderzuschlag",
    "schulbescheinigung",
    "wohngeld",
    "buergergeld",
    "jobcenter",
    "ebk",
]

# ── Result tracking ───────────────────────────────────────────────────────────
_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"


def run_smoke_test(
    out_dir: Path,
    lang: str,
    doc_filter: Optional[str],
    final_only: bool,
    preview_only: bool,
) -> int:
    """Run smoke tests. Returns exit code (0=all pass, 1=some failed)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Import here so import errors are caught as test failures
    try:
        from backend.pdf_generator import generate_preview_pdf, generate_final_pdf
    except ImportError as e:
        print(f"[FATAL] Cannot import pdf_generator: {e}")
        return 1

    docs = [doc_filter.lower()] if doc_filter else _UNIVERSAL_DOCS
    results = []

    for doc_type in docs:
        user_data = dict(_TEST_USER_DATA)

        # ── Preview ─────────────────────────────────────────────────────────
        if not final_only:
            preview_out = out_dir / f"{doc_type}_preview.pdf"
            try:
                path = generate_preview_pdf(
                    doc_type=doc_type,
                    user_data=user_data,
                    lang=lang,
                    user_id=99999,
                )
                if path and Path(path).exists():
                    shutil.copy2(path, preview_out)
                    sz = Path(path).stat().st_size
                    has_disc = _pdf_has_disclaimer(path)
                    disc_note = "" if has_disc else " ⚠️ DISCLAIMER MISSING"
                    results.append((_PASS if has_disc else _FAIL, "preview", doc_type, str(preview_out), f"{sz} bytes{disc_note}"))
                else:
                    results.append((_FAIL, "preview", doc_type, "", "returned None or missing file"))
            except Exception as exc:
                results.append((_FAIL, "preview", doc_type, "", f"exception: {exc}"))

        # ── Final ────────────────────────────────────────────────────────────
        if not preview_only:
            final_out = out_dir / f"{doc_type}_final.pdf"
            try:
                result = generate_final_pdf(
                    doc_type=doc_type,
                    user_data=user_data,
                    lang=lang,
                    user_id=99999,
                )
                if isinstance(result, str) and Path(result).exists():
                    shutil.copy2(result, final_out)
                    sz = Path(result).stat().st_size
                    has_disc = _pdf_has_disclaimer(result)
                    disc_note = "" if has_disc else " ⚠️ DISCLAIMER MISSING"
                    results.append((_PASS if has_disc else _FAIL, "final", doc_type, str(final_out), f"{sz} bytes{disc_note}"))
                elif isinstance(result, dict) and result.get("status") == "validation_failed":
                    missing = result.get("missing_fields", [])
                    msg = f"validation_failed — missing: {', '.join(missing[:5])}" if missing else "validation_failed"
                    results.append((_SKIP, "final", doc_type, "", msg))
                elif result is None:
                    results.append((_FAIL, "final", doc_type, "", "returned None"))
                else:
                    results.append((_FAIL, "final", doc_type, "", f"unexpected return: {result!r:.80}"))
            except Exception as exc:
                tb_lines = traceback.format_exc().strip().splitlines()
                short_tb = tb_lines[-1] if tb_lines else str(exc)
                results.append((_FAIL, "final", doc_type, "", f"exception: {short_tb}"))

    # ── Print summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 90)
    print("  PDF SMOKE TEST RESULTS")
    print("=" * 90)
    total = len(results)
    n_pass = sum(1 for r in results if r[0] == _PASS)
    n_fail = sum(1 for r in results if r[0] == _FAIL)
    n_skip = sum(1 for r in results if r[0] == _SKIP)

    for status, mode, doc, path, note in results:
        icon = "✅" if status == _PASS else ("⚠️ " if status == _SKIP else "❌")
        path_short = Path(path).name if path else ""
        line = f"  {icon} {status:<4}  {mode:<8}  {doc:<38}  {path_short or note}"
        if status == _PASS and note:
            line += f"  ({note})"
        elif status in (_SKIP, _FAIL):
            line += f"  ← {note}"
        print(line)

    print("-" * 90)
    print(f"  Total: {total}   PASS: {n_pass}   SKIP (validation): {n_skip}   FAIL: {n_fail}")
    print(f"  Output dir: {out_dir}")
    print("=" * 90)
    print()

    # Print example validation error
    for _, mode, doc, _, note in results:
        if mode == "final" and "validation_failed" in note:
            print(f"  Example validation message for '{doc}':")
            try:
                from backend.utils.validate import validate_user_data, format_validation_error
                _, missing, _ = validate_user_data(doc, _TEST_USER_DATA, lang)
                if missing:
                    print(format_validation_error(doc, missing, lang))
                else:
                    print(f"  (no missing fields for test data — validation passed)")
            except Exception as e:
                print(f"  (could not generate example: {e})")
            print()
            break

    return 1 if n_fail > 0 else 0


def main():
    parser = argparse.ArgumentParser(description="PDF smoke test for GermanDocBot")
    parser.add_argument("--lang",         default="de",          help="Lang for generation (default: de)")
    parser.add_argument("--out",          default="outputs/smoke", help="Output directory")
    parser.add_argument("--doc",          default=None,          help="Test a single doc_type")
    parser.add_argument("--final-only",   action="store_true",   help="Skip preview generation")
    parser.add_argument("--preview-only", action="store_true",   help="Skip final generation")
    args = parser.parse_args()

    out_dir = _ROOT / args.out
    rc = run_smoke_test(
        out_dir=out_dir,
        lang=args.lang,
        doc_filter=args.doc,
        final_only=args.final_only,
        preview_only=args.preview_only,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
