#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/acroform_map_wizard.py — AcroForm field inspector + mapping skeleton generator.

Usage:
    python tools/acroform_map_wizard.py --doc anmeldung
    python tools/acroform_map_wizard.py --doc jobcenter --json
    python tools/acroform_map_wizard.py --doc bafoeg --json --out layouts/bafoeg_mapping.json

Outputs:
  1. Human-readable field report: field name, type, current mapping status, sample fill value.
  2. Mapping skeleton JSON: { "user_data_key_or_literal": "pdf_field_name" } for unmapped fields.
  3. Fill report: filled / left-empty counts with reasons.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as script
_PROJ_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJ_ROOT))

# ── sample fixture used to show "what value would fill this field" ────────────
_SAMPLE_USER_DATA = {
    "first_name":           "Maria",
    "last_name":            "Musterfrau",
    "birth_date":           "15.05.1990",
    "birth_name":           "Mustermädchen",
    "birth_place":          "Kyiv",
    "nationality":          "Ukrainisch",
    "gender":               "weiblich",
    "family_status":        "ledig",
    "street":               "Musterstraße",
    "house_number":         "12A",
    "plz":                  "10115",
    "city":                 "Berlin",
    "phone":                "+4930123456",
    "email":                "maria@example.de",
    "iban":                 "DE89370400440532013000",
    "tax_id":               "12345678901",
    "employer_name":        "Muster GmbH",
    "employer_street":      "Gewerbestr.",
    "employer_house_number": "7",
    "employer_plz":         "10117",
    "employer_city":        "Berlin",
    "signature_date":       "18.02.2026",
    "signature_place":      "Berlin",
    "landlord_name":        "Hans Vermieter",
    "landlord_address":     "Berliner Str. 5, 10115 Berlin",
    "move_in_date":         "01.01.2024",
    "child_birth_date":     "10.03.2020",
    "child_first_name":     "Leo",
    "child_last_name":      "Musterfrau",
    "bafoeg_schule":        "Freie Universität Berlin",
    "bafoeg_fachrichtung":  "Informatik",
    "bafoeg_abschluss":     "Bachelor",
}


def _detect_pdf_type(fitz_doc) -> str:
    """Return 'acroform', 'xfa', 'flat', or 'unknown'."""
    try:
        import fitz as _fitz  # noqa: F401 (just to confirm available)
        fields = []
        for page in fitz_doc:
            for w in page.widgets():
                fields.append(w)
        if not fields:
            return "flat"
        # Attempt XFA detection via raw trailer bytes
        trailer_str = str(fitz_doc.pdf_trailer())
        if "XFA" in trailer_str:
            return "xfa"
        return "acroform"
    except Exception:
        return "unknown"


def _normalize_date(val: str) -> str:
    """YYYY-MM-DD → DD.MM.YYYY for date fields."""
    import re
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", val.strip())
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return val


def run_wizard(
    doc_type: str,
    output_json: bool = False,
    out_file: Path | None = None,
    verbose: bool = True,
) -> int:
    """
    Main wizard logic. Returns exit code (0 = success, 1 = error).
    Prints a fill report and optionally writes a mapping skeleton JSON.
    """
    try:
        import fitz
    except ImportError:
        print("[ERROR] PyMuPDF (fitz) not installed. Run: pip install pymupdf", file=sys.stderr)
        return 1

    try:
        from backend.document_config import (
            resolve_template_path,
            get_acroform_mapping,
            get_value_for_pdf_field,
        )
    except ImportError as e:
        print(f"[ERROR] Cannot import backend modules: {e}", file=sys.stderr)
        return 1

    TMPL = _PROJ_ROOT / "templates"
    LEGACY = _PROJ_ROOT / "backend" / "templates"

    template_path = resolve_template_path(doc_type, None, TMPL, LEGACY)
    if not template_path:
        print(f"[ERROR] No template found for doc_type={doc_type!r}", file=sys.stderr)
        return 1

    doc = fitz.open(str(template_path))
    pdf_type = _detect_pdf_type(doc)

    # Collect all AcroForm widgets (first occurrence of each name)
    widget_by_name: dict[str, tuple] = {}   # name → (field_type, page_num)
    for page_num in range(len(doc)):
        for w in doc[page_num].widgets():
            name = getattr(w, "field_name", None)
            ftype = getattr(w, "field_type_string", "?")
            if name and name not in widget_by_name:
                widget_by_name[name] = (ftype, page_num + 1)
    doc.close()

    existing_mapping = get_acroform_mapping(doc_type)
    # Invert: pdf_field_name → schema_key (for quick lookup)
    pdf_to_schema: dict[str, str] = {v: k for k, v in existing_mapping.items()}

    # ── Print header ─────────────────────────────────────────────────────────
    source_tag = "NEW" if str(template_path).startswith(str(TMPL)) else "LEGACY"
    if verbose:
        print(f"\n{'=' * 70}")
        print(f"  AcroForm Map Wizard  —  {doc_type.upper()}")
        print(f"{'=' * 70}")
        print(f"  Template : [{source_tag}] {template_path.name}")
        print(f"  PDF type : {pdf_type}")
        print(f"  Total fields : {len(widget_by_name)}")
        print(f"  Already mapped : {len(existing_mapping)} schema keys → "
              f"{len(set(existing_mapping.values()))} PDF fields")
        print(f"{'=' * 70}\n")
        print(f"  {'PDF field name':<50} {'Type':<12} {'Schema key / status'}")
        print(f"  {'-' * 50} {'-' * 12} {'-' * 30}")

    filled_count = 0
    empty_count = 0
    skeleton: dict[str, str] = {}   # suggested_schema_key → pdf_field_name

    for pdf_field, (ftype, page) in sorted(widget_by_name.items(), key=lambda x: (x[1][1], x[0])):
        schema_key = pdf_to_schema.get(pdf_field)
        if schema_key:
            # Already mapped — resolve sample value
            sample_val = get_value_for_pdf_field(schema_key, _SAMPLE_USER_DATA)
            if sample_val is None:
                sample_val = _SAMPLE_USER_DATA.get(schema_key)
            if "date" in schema_key.lower() or "datum" in schema_key.lower():
                if sample_val:
                    sample_val = _normalize_date(str(sample_val))
            status = f"✔ mapped → {schema_key!r}"
            if sample_val:
                status += f"  (sample: {str(sample_val)[:30]!r})"
                filled_count += 1
            else:
                status += "  (no sample value)"
                empty_count += 1
        else:
            # Not yet mapped
            status = "— unmapped"
            skeleton[f"<schema_key>"] = pdf_field    # placeholder key for JSON skeleton
            empty_count += 1

        if verbose:
            print(f"  p{page:<2} {pdf_field:<50} {ftype:<12} {status}")

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"  FILL REPORT")
        print(f"  Total AcroForm fields : {len(widget_by_name)}")
        print(f"  Mapped in get_acroform_mapping : {len(existing_mapping)} schema keys")
        print(f"  Would fill with sample data   : {filled_count}")
        print(f"  Left empty (no sample value)  : {empty_count}")
        unmapped_count = sum(1 for pdf_f in widget_by_name if pdf_f not in pdf_to_schema)
        print(f"  Unmapped fields               : {unmapped_count}")
        print(f"{'=' * 70}\n")

    # ── Mapping skeleton for unmapped fields ─────────────────────────────────
    skeleton_full: dict[str, str] = {}
    for pdf_field in sorted(widget_by_name):
        if pdf_field not in pdf_to_schema:
            suggested_key = (
                pdf_field.lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace(".", "_")
                .replace("/", "_")
                .replace("(", "")
                .replace(")", "")
                .replace(",", "")
                .replace("ä", "ae")
                .replace("ö", "oe")
                .replace("ü", "ue")
                .replace("ß", "ss")
                [:60]
            )
            skeleton_full[suggested_key] = pdf_field

    if output_json:
        skeleton_json = json.dumps(
            {"_doc_type": doc_type, "_note": "skeleton for unmapped fields — rename keys to real schema keys",
             "unmapped": skeleton_full, "existing_mapping": existing_mapping},
            ensure_ascii=False,
            indent=2,
        )
        if out_file:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(skeleton_json, encoding="utf-8")
            if verbose:
                print(f"  Skeleton JSON written to: {out_file}")
        else:
            print("\n--- MAPPING SKELETON JSON (unmapped fields) ---")
            print(skeleton_json)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AcroForm Map Wizard — inspect PDF fields and generate mapping skeletons.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--doc", required=True, metavar="DOC_TYPE",
                        help="Document type (e.g. anmeldung, jobcenter, bafoeg)")
    parser.add_argument("--json", action="store_true", dest="output_json",
                        help="Also output mapping skeleton JSON")
    parser.add_argument("--out", type=Path, metavar="PATH",
                        help="Write JSON skeleton to this file instead of stdout")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress field-by-field output (useful with --json)")
    args = parser.parse_args()

    return run_wizard(
        doc_type=args.doc,
        output_json=args.output_json,
        out_file=args.out,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
