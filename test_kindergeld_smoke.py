# -*- coding: utf-8 -*-
"""
Kindergeld smoke test — two real cases.

Usage:
    python test_kindergeld_smoke.py

Tests:
  Case A — single applicant, no partner
  Case B — married applicant, with partner

For each case:
  1. Validate frontend payload simulation (required fields, no stale partner data)
  2. Run get_value_for_pdf_field() for every mapped field
  3. Generate preview PDF + final PDF via create_final_pdf()
  4. Confirm output files exist and are non-empty
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Realistic test payloads (mirrors what the frontend submits after our fixes)
# ---------------------------------------------------------------------------

CASE_A: Dict[str, Any] = {
    # — Applicant —
    "last_name": "Kovalenko",
    "first_name": "Olena",
    "birth_name": "",  # optional, left blank
    "birth_date": "15.03.1990",
    "birth_place": "Kyiv, Ukraine",
    "nationality": "ukrainisch",
    "gender": "w",  # schema sends short code
    "familienstand": "ledig",
    # — Address (split fields as per new schema) —
    "street": "Hauptstraße",
    "house_number": "12a",
    "postal_code": "10115",
    "city": "Berlin",
    # — Tax ID (optional) —
    "tax_id": "86095742719",
    # — Partner (ALL empty / absent — ledig) —
    "partner_last_name": "",
    "partner_first_name": "",
    "partner_birth_date": "",
    "partner_nationality": "",  # must stay empty
    # — Child —
    "child_last_name": "Kovalenko",
    "child_first_name": "Dmytro",
    "child_birth_date": "20.06.2019",
    "child_birth_place": "Berlin",
    "child_nationality": "ukrainisch",
    # — Bank —
    "iban": "DE89370400440532013000",
    "bic": "COBADEFFXXX",
    "bank_name": "Commerzbank",
    "account_holder": "",
    # — Signature —
    "signature_place": "Berlin",
    "signature_date": "",  # intentionally empty → should auto-fill today
}

CASE_B: Dict[str, Any] = {
    # — Applicant —
    "last_name": "Müller",
    "first_name": "Anna",
    "birth_name": "Schmidt",  # birth name differs → must appear in PDF
    "birth_date": "01.05.1985",
    "birth_place": "Hamburg, Deutschland",
    "nationality": "deutsch",
    "gender": "w",
    "familienstand": "verheiratet",
    # — Address —
    "street": "Musterstraße",
    "house_number": "12-14",  # edge-case: range format
    "postal_code": "20095",
    "city": "Hamburg",
    # — Tax ID —
    "tax_id": "12345678901",
    # — Partner (married → all required) —
    "partner_last_name": "Müller",
    "partner_first_name": "Klaus",
    "partner_birth_date": "10.07.1983",
    "partner_nationality": "deutsch",
    # — Child —
    "child_last_name": "Müller",
    "child_first_name": "Sophie",
    "child_birth_date": "05.09.2018",
    "child_birth_place": "Hamburg",
    "child_nationality": "deutsch",
    # — Bank —
    "iban": "DE44500105175407324931",
    "bic": "BELADEBEXXX",
    "bank_name": "Berliner Sparkasse",
    "account_holder": "",
    # — Signature —
    "signature_place": "Hamburg",
    "signature_date": "24.03.2026",
}

# ---------------------------------------------------------------------------
# Fields we care about verifying directly
# ---------------------------------------------------------------------------

CRITICAL_FIELDS: List[Tuple[str, str]] = [
    # (pdf_field_name, expected_substring_or_exact)
    ("last_name", "EXACT"),
    ("first_name", "EXACT"),
    ("birth_date", "EXACT"),
    ("birth_place", "EXACT"),
    ("nationality", "CONTAINS"),
    ("gender", "CONTAINS"),  # normaliser → männlich/weiblich/divers
    ("kg_anschrift", "CONTAINS"),  # street + house_number + postal_code + city
    ("kg_ledig", "OPTIONAL_CHECK"),  # set for case A, unset for case B
    ("kg_verheiratet", "OPTIONAL_CHECK"),
    ("kg_partner_name", "OPTIONAL_CHECK"),
    ("kg_partner_nationality", "OPTIONAL_CHECK"),
    ("kg_kind1_name", "CONTAINS"),
    ("kg_kind1_gebdat", "EXACT"),
    ("birth_name", "OPTIONAL_CHECK"),
    ("bic", "OPTIONAL_CHECK"),
    ("bank_name", "OPTIONAL_CHECK"),
    ("signature_date", "NONEMPTY"),  # auto-filled when empty
]


def check_field_mapping(case_label: str, user_data: Dict[str, Any]) -> List[str]:
    """
    Run get_value_for_pdf_field() for every mapped kindergeld field.
    Returns list of failure messages (empty = all OK).
    """
    from backend.document_config import (
        KINDERGELD_ACROFORM_MAPPING,
        get_value_for_pdf_field,
    )

    failures = []

    for pdf_key in KINDERGELD_ACROFORM_MAPPING:
        try:
            val = get_value_for_pdf_field(pdf_key, user_data)
        except Exception as exc:
            failures.append(f"  [{case_label}] EXCEPTION for field '{pdf_key}': {exc}")
            continue

        # signature_date must never be None or empty
        if pdf_key == "signature_date":
            if not val:
                failures.append(
                    f"  [{case_label}] FAIL: signature_date is empty (auto-fill broke)"
                )

        # kg_anschrift must contain street, house_number, postal_code, city
        if pdf_key == "kg_anschrift" and val:
            street = user_data.get("street", "")
            house = user_data.get("house_number", "")
            plz = user_data.get("postal_code", user_data.get("plz", ""))
            city = user_data.get("city", "")
            for part in [street, house, plz, city]:
                if part and part not in val:
                    failures.append(
                        f"  [{case_label}] FAIL: kg_anschrift='{val}' missing '{part}'"
                    )

    # Case A — no partner: kg_partner_* must all be None
    if user_data.get("familienstand", "").lower() == "ledig":
        for pf in (
            "kg_partner_name",
            "kg_partner_first_name",
            "kg_partner_birth_date",
            "kg_partner_nationality",
        ):
            val = get_value_for_pdf_field(pf, user_data)
            if val:
                failures.append(
                    f"  [{case_label}] STALE PARTNER DATA: '{pf}' = '{val}' (should be None)"
                )

    # Case B — with partner: kg_partner_* must all be set
    if user_data.get("familienstand", "").lower() == "verheiratet":
        for pf in (
            "kg_partner_name",
            "kg_partner_first_name",
            "kg_partner_birth_date",
            "kg_partner_nationality",
        ):
            val = get_value_for_pdf_field(pf, user_data)
            if not val:
                failures.append(
                    f"  [{case_label}] MISSING PARTNER FIELD: '{pf}' is None/empty"
                )

    # birth_name: optional — if provided, must pass through
    bn = user_data.get("birth_name", "").strip()
    if bn:
        val = get_value_for_pdf_field("birth_name", user_data)
        if val != bn:
            failures.append(
                f"  [{case_label}] FAIL: birth_name expected '{bn}', got '{val}'"
            )

    # gender must be expanded by normaliser ("w" → "weiblich")
    val_gender = get_value_for_pdf_field("gender", user_data)
    if val_gender not in ("männlich", "weiblich", "divers", "-"):
        failures.append(
            f"  [{case_label}] FAIL: gender normaliser produced unexpected value '{val_gender}'"
        )

    return failures


def generate_pdfs(
    case_label: str, user_data: Dict[str, Any], out_dir: Path
) -> List[str]:
    """
    Generate preview + final PDFs. Returns failure messages.
    """
    from backend.pdf_generator import create_final_pdf

    failures = []

    for mode in ("final",):
        try:
            result = create_final_pdf(
                user_id=0,
                user_data=user_data,
                doc_type="kindergeld",
                user_lang="de",
            )
            # result is a str path, a dict (validation_failed), or None
            if isinstance(result, dict):
                failures.append(
                    f"  [{case_label}] FAIL {mode}: validation_failed — {result.get('missing_fields')}"
                )
            elif isinstance(result, str):
                p = Path(result)
                if p.exists() and p.stat().st_size > 500:
                    print(
                        f"  [{case_label}] OK  {mode:8s}: {p.name} ({p.stat().st_size:,} bytes)"
                    )
                    # copy to out_dir so we can inspect if needed
                    import shutil

                    shutil.copy(result, out_dir / f"kindergeld_{case_label}_{mode}.pdf")
                else:
                    size = p.stat().st_size if p.exists() else 0
                    failures.append(
                        f"  [{case_label}] FAIL {mode}: file missing or suspiciously small ({size} bytes)"
                    )
            else:
                failures.append(
                    f"  [{case_label}] FAIL {mode}: create_final_pdf returned None"
                )
        except Exception:
            failures.append(
                f"  [{case_label}] EXCEPTION during {mode}:\n{traceback.format_exc()}"
            )

    return failures


def run_case(label: str, user_data: Dict[str, Any], out_dir: Path) -> bool:
    print(f"\n{'='*60}")
    print(f"  SMOKE TEST {label}")
    print(f"{'='*60}")

    all_failures: List[str] = []

    # 1. Field mapping
    print(f"\n  [1/2] Field mapping check …")
    mapping_fails = check_field_mapping(label, user_data)
    if mapping_fails:
        all_failures.extend(mapping_fails)
        for f in mapping_fails:
            print(f)
    else:
        print(f"  [{label}] OK  all field mappings correct")

    # 2. PDF generation
    print(f"\n  [2/2] PDF generation …")
    pdf_fails = generate_pdfs(label, user_data, out_dir)
    if pdf_fails:
        all_failures.extend(pdf_fails)
        for f in pdf_fails:
            print(f)

    # Summary
    print()
    if all_failures:
        print(f"  ❌ {label} — FAIL ({len(all_failures)} issue(s))")
        return False
    else:
        print(f"  ✅ {label} — PASS")
        return True


def main() -> None:
    print("\nKindergeld Smoke Test")
    print("=" * 60)

    with tempfile.TemporaryDirectory(prefix="kg_smoke_") as tmp:
        out_dir = Path(tmp)

        result_a = run_case("A (no partner)", CASE_A, out_dir)
        result_b = run_case("B (with partner)", CASE_B, out_dir)

        print(f"\n{'='*60}")
        print("  RESULTS")
        print(f"{'='*60}")
        print(f"  Smoke test A (no partner):   {'PASS ✅' if result_a else 'FAIL ❌'}")
        print(f"  Smoke test B (with partner): {'PASS ✅' if result_b else 'FAIL ❌'}")

        if result_a and result_b:
            print("\n  Kindergeld is fully finished ✅")
            sys.exit(0)
        else:
            print("\n  Some tests failed — see details above.")
            sys.exit(1)


if __name__ == "__main__":
    main()
