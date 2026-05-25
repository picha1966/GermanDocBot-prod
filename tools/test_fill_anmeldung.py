#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script: generate final PDF Anmeldung with fixed payload.
Usage: from project root, run:
  python tools/test_fill_anmeldung.py
Output: generated_pdfs/anmeldung_999_<timestamp>.pdf and copy to output/anmeldung_test.pdf
Optional: DEBUG_PDF_POSITIONS=1 python tools/test_fill_anmeldung.py  # draw field rectangles
"""

import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Fixed payload for Anmeldung (normalized keys, DD.MM.YYYY dates)
TEST_ANSWERS = {
    "wohnungstyp": "Hauptwohnung",
    "move_in_date": "01.02.2025",
    "postal_code": "10115",
    "city": "Berlin",
    "street": "Musterstraße",
    "house_number": "12",
    "has_bisherige_wohnung": "Nein",
    "last_name": "Mustermann",
    "first_name": "Max",
    "birth_date": "15.03.1990",
    "birth_place": "Berlin",
    "nationality": "deutsch",
    "gender": "m",
    "familienstand": "ledig",
    "landlord_name": "Vermieter GmbH",
    "signature_place": "Berlin",
    "signature_date": "01.02.2025",
}


def main():
    from backend.pdf_generator import create_final_pdf

    user_id = 999
    doc_type = "anmeldung"
    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "anmeldung_test.pdf"

    print("Generating final PDF Anmeldung (mode=overlay)...")
    result = create_final_pdf(
        user_id=user_id,
        user_data=TEST_ANSWERS,
        doc_type=doc_type,
        authority_info=None,
        user_lang="de",
    )
    if isinstance(result, dict) and result.get("status") == "incomplete":
        print("Validation gate: final PDF correctly blocked (REQUIRED_FROM_USER present)")
        for m in result.get("missing_fields") or []:
            print(f"  - {m.get('field')}: {m.get('label')}")
        sys.exit(0)
    if result and Path(result).exists():
        import shutil
        shutil.copy(result, out_file)
        print(f"OK: {result}")
        print(f"Copy: {out_file}")
        sys.exit(0)
    print("FAIL: create_final_pdf returned no file")
    sys.exit(1)


if __name__ == "__main__":
    main()
