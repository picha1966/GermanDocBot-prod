# -*- coding: utf-8 -*-
"""
tools/test_pipeline.py — End-to-end pipeline test via create_final_pdf()
Tests mietbescheinigung, unterhaltsvorschuss, kindergeld_anlage through the
actual bot pipeline (same code path as Telegram bot).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
from backend.pdf_generator import create_final_pdf

OUTPUT_DIR = Path("outputs/smoke")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TESTS = [
    {
        "doc_type": "mietbescheinigung",
        "output": OUTPUT_DIR / "pipeline_mietbescheinigung.pdf",
        "user_data": {
            "city": "Berlin",
            "signature_date": "2026-03-21",
            # landlord — single field used by validation + handler
            "landlord_name": "Klaus Müller",
            "landlord_street": "Hauptstraße",
            "landlord_house_number": "5",
            "landlord_plz": "10115",
            "landlord_city": "Berlin",
            # tenant
            "first_name": "Anna",
            "last_name": "Schmidt",
            "street": "Bergstraße",
            "house_number": "12",
            "plz": "10117",
            # property
            "property_street": "Bergstraße",
            "property_house_number": "12",
            "property_plz": "10117",
            "property_city": "Berlin",
            "num_persons": "3",
            "rental_start_date": "2024-01-01",
            "floor_area": "75",
            "num_rooms": "3",
            "num_bathrooms": "1",
            "total_rent": "1200",
            "rent_payment_start": "2024-01-01",
            "cold_rent": "900",
            "nebenkosten": "200",
            "electricity": "50",
            "heating": "100",
        },
    },
    {
        "doc_type": "unterhaltsvorschuss",
        "output": OUTPUT_DIR / "pipeline_unterhaltsvorschuss.pdf",
        "user_data": {
            "first_name": "Maria",
            "last_name": "Weber",
            "birth_date": "1985-06-15",
            "street": "Lindenstraße",
            "house_number": "8",
            "plz": "10243",
            "city": "Berlin",
            "bundesland": "Berlin",   # needed to resolve berlin.pdf template
            "bank_name": "Sparkasse Berlin",
            "iban": "DE89370400440532013000",
            "child_first_name": "Lukas",
            "child_last_name": "Weber",
            "child_birth_date": "2018-03-20",
            "other_parent_first_name": "Thomas",
            "other_parent_last_name": "Fischer",
            "signature_date": "2026-03-21",
        },
    },
    {
        "doc_type": "kindergeld_anlage",
        "output": OUTPUT_DIR / "pipeline_kindergeld_anlage.pdf",
        "user_data": {
            "first_name": "Laura",
            "last_name": "Hoffmann",
            "child_first_name": "Emma",
            "child_last_name": "Hoffmann",
            "child_birth_date": "2020-07-14",
            "child_birth_place": "Hamburg",
            "child_nationality": "deutsch",
            "city": "Hamburg",
            "signature_date": "2026-03-21",
        },
    },
]

passed = 0
failed = 0

for t in TESTS:
    doc_type = t["doc_type"]
    out = t["output"]
    user_data = t["user_data"]

    print(f"\n{'='*60}")
    print(f"Testing: {doc_type}")
    print(f"{'='*60}")

    try:
        result = create_final_pdf(
            user_id=99999,
            doc_type=doc_type,
            user_data=user_data,
            user_lang="de",
        )
        if isinstance(result, dict):
            print(f"  FAIL — validation blocked: {result}")
            failed += 1
        elif result and Path(result).exists():
            size = Path(result).stat().st_size
            print(f"  PASS — {Path(result).name} ({size:,} bytes)")
            passed += 1
        else:
            print(f"  FAIL — create_final_pdf returned: {result!r}")
            failed += 1
    except Exception as e:
        print(f"  ERROR — {e}")
        import traceback
        traceback.print_exc()
        failed += 1

print(f"\n{'='*60}")
print(f"Results: {passed} passed, {failed} failed")
print(f"{'='*60}")
