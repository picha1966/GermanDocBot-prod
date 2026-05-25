#!/usr/bin/env python3
"""
tools/extract_pdf_fields.py
===========================
Print all AcroForm widgets in a PDF with their coordinates.

Usage:
    python tools/extract_pdf_fields.py templates/buergergeld/default.pdf
    python tools/extract_pdf_fields.py templates/buergergeld/default.pdf --json
    python tools/extract_pdf_fields.py templates/buergergeld/default.pdf --overlay

Output modes:
    (default)  human-readable table: page | field_name | type | rect
    --json     acroform_map skeleton: {"field_name": "AcroForm Field Name", ...}
    --overlay  overlay_map skeleton: {"field_name": {"page": 0, "x": 0.0, "y": 0.0, ...}}

Use --overlay when the PDF is XFA-only (widgets() is empty but you want coordinate stubs).
Use --json   when the PDF has real AcroForm fields → paste into _ACROFORM_MAPPINGS.
"""
import sys
import io
import json
import argparse
from pathlib import Path

# Force UTF-8 output on Windows (cp1251 cannot encode German umlauts)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def extract_fields(pdf_path: str, mode: str = "table") -> None:
    try:
        import fitz
    except ImportError:
        print("ERROR: PyMuPDF not installed. Run: pip install pymupdf", file=sys.stderr)
        sys.exit(1)

    path = Path(pdf_path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    doc = fitz.open(str(path))
    widgets_found = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        for w in page.widgets():
            if not w.field_name:
                continue
            widgets_found.append({
                "page": page_num,
                "field_name": w.field_name,
                "field_type": w.field_type_string,
                "x": round(w.rect.x0, 1),
                "y": round(w.rect.y1, 1),   # baseline (bottom of rect, PyMuPDF y-down)
                "width": round(w.rect.width, 1),
                "height": round(w.rect.height, 1),
            })

    doc.close()

    if not widgets_found:
        print(f"No AcroForm widgets found in {path.name}.")
        print("The PDF is likely XFA-only. Use --overlay to generate coordinate stubs.")
        return

    if mode == "table":
        _print_table(widgets_found, path.name)
    elif mode == "json":
        _print_acroform_map(widgets_found)
    elif mode == "overlay":
        _print_overlay_map(widgets_found)


def _print_table(widgets, filename: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {filename}  —  {len(widgets)} AcroForm widget(s)")
    print(f"{'='*70}")
    print(f"{'Page':>4}  {'Type':<12}  {'x':>7}  {'y':>7}  {'w':>6}  {'h':>5}  Field name")
    print(f"{'-'*70}")
    for w in widgets:
        print(
            f"{w['page']:>4}  {w['field_type']:<12}  "
            f"{w['x']:>7.1f}  {w['y']:>7.1f}  "
            f"{w['width']:>6.1f}  {w['height']:>5.1f}  "
            f"{w['field_name']}"
        )
    print(f"{'='*70}\n")


def _print_acroform_map(widgets) -> None:
    """Print skeleton for _ACROFORM_MAPPINGS: schema_key → AcroForm field name."""
    mapping = {}
    for w in widgets:
        # Use field_name as both key and value — developer fills in schema_key manually
        snake = w["field_name"].lower().replace(" ", "_").replace("-", "_")
        mapping[snake] = w["field_name"]
    print("# Paste into _ACROFORM_MAPPINGS in document_config.py")
    print("# Replace left-side keys with your schema field names\n")
    print(json.dumps(mapping, ensure_ascii=False, indent=2))


def _print_overlay_map(widgets) -> None:
    """Print skeleton for OVERLAY_MAPS / overlay_map.json."""
    overlay = {}
    for w in widgets:
        snake = w["field_name"].lower().replace(" ", "_").replace("-", "_")
        overlay[snake] = {
            "page": w["page"],
            "x": w["x"],
            "y": w["y"],
            "fontsize": 9,
            "max_width": round(w["width"], 1),
        }
    print("# Paste into OVERLAY_MAPS or save as templates/{doc_type}/overlay_map.json")
    print("# Replace left-side keys with your schema field names\n")
    print(json.dumps(overlay, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract AcroForm fields from a PDF and print coordinates."
    )
    parser.add_argument("pdf", help="Path to the PDF file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json",    action="store_true", help="Output acroform_map skeleton")
    group.add_argument("--overlay", action="store_true", help="Output overlay_map skeleton")
    args = parser.parse_args()

    mode = "json" if args.json else "overlay" if args.overlay else "table"
    extract_fields(args.pdf, mode)


if __name__ == "__main__":
    main()
