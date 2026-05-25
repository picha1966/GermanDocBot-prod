#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/pdf_audit.py — Audit a single doc_type's PDF configuration and template.

Usage:
    python tools/pdf_audit.py --doc anmeldung
    python tools/pdf_audit.py --doc wohngeld --bundesland none --lang de
    python tools/pdf_audit.py --doc kindergeld --bundesland berlin
    python tools/pdf_audit.py --all                        (audit every registered doc_type)

Output:
    Template source:  NEW / LEGACY / NONE (builder)
    Template type:    AcroForm / XFA / flat / builder
    AcroForm fields:  count + first 10 field names
    Mapping coverage: mapped keys vs actual PDF fields
    Runtime path:     acroform / overlay / builder / unknown
    Official link:    URL or (none)
    Validation rules: required fields list
"""
import argparse
import os
import sys
from pathlib import Path

# Ensure project root is on path
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPT_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Project imports ────────────────────────────────────────────────────────────
try:
    from backend.document_config import (
        PDF_TEMPLATES,
        resolve_template_path,
        get_doc_strategy,
        get_official_link,
        get_acroform_mapping,
        DOC_STRATEGY,
    )
except ImportError as e:
    print(f"[ERROR] Cannot import document_config: {e}")
    sys.exit(1)

try:
    from backend.utils.validate import _REQUIRED_FIELDS, get_label
    _HAS_VALIDATE = True
except ImportError:
    _HAS_VALIDATE = False
    _REQUIRED_FIELDS = {}
    def get_label(k, lang="de"): return k

TEMPLATES_DIR = _ROOT / "templates"
LEGACY_DIR    = _ROOT / "backend" / "templates"

try:
    import fitz as _fitz
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_pdf_type(path: Path) -> tuple:
    """
    Returns (type_str, field_count, all_unique_field_names).
    type_str: "AcroForm" | "XFA" | "flat" | "unknown"
    all_unique_field_names is a list of deduplicated field names (for coverage checks).
    """
    if not _HAS_FITZ:
        return "unknown (fitz not available)", 0, []
    try:
        doc = _fitz.open(str(path))
        widgets_all = []      # all occurrences (for raw count)
        unique_names = []     # deduplicated names (for coverage)
        seen = set()
        is_xfa = False
        for page in doc:
            for w in page.widgets():
                name = getattr(w, "field_name", "?")
                widgets_all.append(name)
                if name not in seen:
                    seen.add(name)
                    unique_names.append(name)
        # Check for XFA stream
        try:
            trailer = doc.pdf_trailer()
            if trailer:
                root = trailer.get("Root", {})
                acro = root.get("AcroForm", {})
                if acro.get("XFA"):
                    is_xfa = True
        except Exception:
            pass
        doc.close()
        if is_xfa:
            return "XFA", len(widgets_all), unique_names
        if widgets_all:
            return "AcroForm", len(widgets_all), unique_names
        return "flat (no fields)", 0, []
    except Exception as e:
        return f"error ({e})", 0, []


def audit_doc(doc_type: str, bundesland: str | None, lang: str) -> dict:
    """Return a dict with all audit data for one doc_type."""
    key = doc_type.strip().lower()
    bl  = bundesland.strip().lower() if bundesland and bundesland.lower() not in ("none", "") else None

    # ── Template resolution ────────────────────────────────────────────────
    template_path = resolve_template_path(key, bl, TEMPLATES_DIR, LEGACY_DIR)
    if template_path:
        p = Path(template_path)
        if str(TEMPLATES_DIR) in str(p):
            source = "NEW"
        elif str(LEGACY_DIR) in str(p):
            source = "LEGACY"
        else:
            source = "OTHER"
    else:
        source = "NONE (builder fallback)"

    # ── Strategy ───────────────────────────────────────────────────────────
    strategy = get_doc_strategy(key)

    # ── PDF type inspection ────────────────────────────────────────────────
    if template_path and Path(template_path).exists():
        pdf_type, field_count, field_names = _detect_pdf_type(Path(template_path))
    else:
        pdf_type, field_count, field_names = "N/A (no template)", 0, []

    # ── AcroForm mapping ───────────────────────────────────────────────────
    mapping = get_acroform_mapping(key)
    mapped_count = len(mapping)

    # Coverage: how many mapped keys actually exist in the PDF as fields
    coverage_note = ""
    if mapping and field_names:
        actual = set(field_names)
        mapped_vals = set(mapping.values())
        found = len(mapped_vals & actual)
        coverage_note = f"{found}/{mapped_count} mapped fields found in PDF"
    elif mapping and not field_count:
        coverage_note = f"{mapped_count} mapped keys but PDF has 0 readable fields"

    # ── Runtime path ───────────────────────────────────────────────────────
    if template_path and pdf_type.startswith("AcroForm") and mapping:
        runtime = "AcroForm fill"
    elif template_path and pdf_type.startswith("AcroForm") and not mapping:
        runtime = "no mapping → builder fallback"
    elif template_path and pdf_type.startswith("XFA"):
        runtime = "XFA → builder fallback"
    elif template_path and pdf_type.startswith("flat"):
        runtime = "overlay or builder fallback"
    elif not template_path:
        runtime = "german_form_builder"
    else:
        runtime = "unknown"

    # ── Official link ──────────────────────────────────────────────────────
    official_link = get_official_link(key) or "(none)"

    # ── Required fields ────────────────────────────────────────────────────
    required = _REQUIRED_FIELDS.get(key, []) if _HAS_VALIDATE else []
    req_labels = [f"{fk} ({get_label(fk, lang)})" for fk in required]

    return {
        "doc_type":     key,
        "bundesland":   bl or "none",
        "source":       source,
        "template":     template_path or "(none)",
        "strategy":     strategy,
        "pdf_type":     pdf_type,
        "field_count":  field_count,
        "field_names":  field_names,
        "mapped_count": mapped_count,
        "coverage":     coverage_note,
        "runtime":      runtime,
        "official_link": official_link,
        "required_fields": req_labels,
    }


def print_audit(r: dict) -> None:
    w = 60
    print("=" * w)
    print(f"  📄 PDF Audit: {r['doc_type'].upper()}"
          + (f" (bundesland={r['bundesland']})" if r['bundesland'] != 'none' else ""))
    print("=" * w)
    print(f"  Template source : {r['source']}")
    print(f"  Template path   : {r['template']}")
    print(f"  Strategy        : {r['strategy']}")
    print(f"  PDF type        : {r['pdf_type']}")
    print(f"  AcroForm fields : {r['field_count']}")
    if r['field_names']:
        preview = ", ".join(r['field_names'][:10])
        print(f"  Field names     : {preview}")
    if r['coverage']:
        print(f"  Mapping coverage: {r['coverage']}")
    print(f"  Runtime path    : {r['runtime']}")
    print(f"  Official link   : {r['official_link']}")
    if r['required_fields']:
        print(f"  Required fields ({len(r['required_fields'])}):")
        for f in r['required_fields']:
            print(f"    • {f}")
    print("=" * w)


def print_all_table(results: list) -> None:
    """Print a compact summary table for --all mode."""
    print()
    print(f"{'DOC_TYPE':<36} {'SOURCE':<8} {'TYPE':<14} {'FIELDS':>6} {'RUNTIME':<24}")
    print("-" * 95)
    for r in results:
        flds = str(r['field_count']) if r['field_count'] else "-"
        print(
            f"{r['doc_type']:<36} {r['source'][:7]:<8} {r['pdf_type'][:13]:<14} "
            f"{flds:>6} {r['runtime'][:23]:<24}"
        )
    print()
    total = len(results)
    acroform = sum(1 for r in results if "AcroForm fill" in r['runtime'])
    builder  = sum(1 for r in results if "builder" in r['runtime'])
    overlay  = sum(1 for r in results if "overlay" in r['runtime'])
    print(f"  Total: {total}  |  AcroForm: {acroform}  |  Builder: {builder}  |  Overlay: {overlay}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PDF Audit tool for GermanDocBot")
    parser.add_argument("--doc",        help="Doc type to audit (e.g. anmeldung)")
    parser.add_argument("--bundesland", default="none", help="Bundesland (default: none)")
    parser.add_argument("--lang",       default="de",   help="Language for labels (default: de)")
    parser.add_argument("--all",        action="store_true", help="Audit all registered doc_types")
    args = parser.parse_args()

    if args.all:
        all_docs = sorted(set(PDF_TEMPLATES.keys()) | set(DOC_STRATEGY.keys()))
        results = []
        for dt in all_docs:
            results.append(audit_doc(dt, args.bundesland, args.lang))
        print_all_table(results)
    elif args.doc:
        r = audit_doc(args.doc, args.bundesland, args.lang)
        print_audit(r)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
