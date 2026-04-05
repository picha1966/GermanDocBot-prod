#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract ALL AcroForm field names from the official Anmeldung PDF.
Run: python tools/extract_acroform_fields.py
Output: list of field names and types (text / checkbox / radio).
Use this to build schema_key → acroform_field_name mapping in document_config.
"""
import sys
from pathlib import Path

# Add project root for imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main():
    import io
    if getattr(sys.stdout, "buffer", None) and (not getattr(sys.stdout, "encoding", None) or "utf" not in (sys.stdout.encoding or "").lower()):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    try:
        import fitz
    except ImportError:
        print("PyMuPDF (fitz) required: pip install pymupdf")
        return 1
    template_path = ROOT / "templates" / "anmeldung.pdf"
    if not template_path.exists():
        print(f"Template not found: {template_path}")
        return 1
    doc = fitz.open(str(template_path))
    print(f"PDF: {template_path.name} — pages: {len(doc)}\n")
    print("AcroForm field list (use for ANMELDUNG_ACROFORM_MAPPING):")
    print("-" * 60)
    seen = set()
    for page_no in range(len(doc)):
        page = doc[page_no]
        widgets = page.widgets()
        if not widgets:
            continue
        for w in widgets:
            name = getattr(w, "field_name", None) or getattr(w, "field_name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            # Widget type: 1=pushbutton, 2=checkbox, 3=radiobutton, 4=text, 5=listbox, 6=combobox, 7=signature
            wtype = getattr(w, "field_type", None)
            type_str = {1: "button", 2: "checkbox", 3: "radio", 4: "text", 5: "listbox", 6: "combobox", 7: "signature"}.get(wtype, f"type_{wtype}")
            print(f"  {name!r}  ({type_str})")
    doc.close()
    if not seen:
        print("  (no AcroForm fields found — template may be flat/scanned; use fillable official PDF)")
    print("-" * 60)
    print(f"Total unique fields: {len(seen)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
