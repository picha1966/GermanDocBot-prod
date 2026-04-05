# -*- coding: utf-8 -*-
"""
backend/smoke_test_builder.py — Smoke tests for builder_only doc_types.

Validates that each builder doc can produce a preview PDF and a final PDF
without errors.  Does NOT modify any rendering behavior.

Usage:
    python -m backend.smoke_test_builder
    python backend/smoke_test_builder.py
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Minimal representative user_data per builder doc_type
# ---------------------------------------------------------------------------
_SAMPLE_DATA: Dict[str, Dict[str, Any]] = {
    "kindergeld": {
        "last_name": "Mustermann",
        "first_name": "Maria",
        "birth_date": "01.01.1985",
        "birth_place": "Berlin",
        "street": "Musterstraße 1",
        "postal_code": "10115",
        "city": "Berlin",
        "nationality": "deutsch",
        "gender": "weiblich",
        "familienstand": "verheiratet",
        "tax_id": "12345678901",
        "child_last_name": "Mustermann",
        "child_first_name": "Leon",
        "child_birth_date": "15.03.2020",
        "child_birth_place": "Berlin",
        "child_nationality": "deutsch",
        "iban": "DE89370400440532013000",
        "bank_name": "Deutsche Bank",
        "account_holder": "Maria Mustermann",
        "signature_place": "Berlin",
        "signature_date": "01.01.2024",
    },
    "wbs": {
        "last_name": "Mustermann",
        "first_name": "Max",
        "birth_date": "05.06.1980",
        "street": "Beispielweg 3",
        "postal_code": "10178",
        "city": "Berlin",
        "nationality": "deutsch",
        "signature_place": "Berlin",
        "signature_date": "01.01.2024",
    },
    "aufenthaltstitel": {
        "last_name": "Ivanova",
        "first_name": "Olena",
        "birth_date": "12.07.1990",
        "birth_place": "Kyiv",
        "nationality": "ukrainisch",
        "gender": "weiblich",
        "postal_code": "10115",
        "city": "Berlin",
        "street": "Hauptstraße",
        "house_number": "5",
        "residence_purpose": "Arbeit",
        "signature_place": "Berlin",
        "signature_date": "01.01.2024",
    },
    "verlaengerung_aufenthaltstitel": {
        "last_name": "Ivanova",
        "first_name": "Olena",
        "birth_date": "12.07.1990",
        "birth_place": "Kyiv",
        "nationality": "ukrainisch",
        "postal_code": "10115",
        "city": "Berlin",
        "street": "Hauptstraße",
        "house_number": "5",
        "residence_purpose": "Arbeit",
        "signature_place": "Berlin",
        "signature_date": "01.01.2024",
    },
    "schulbescheinigung": {
        "last_name": "Petrov",
        "first_name": "Ivan",
        "birth_date": "20.09.2008",
        "street": "Schulweg 1",
        "postal_code": "10117",
        "city": "Berlin",
        "nationality": "ukrainisch",
        "signature_place": "Berlin",
        "signature_date": "01.01.2024",
    },
    "aufenthaltserlaubnis_antrag": {
        "last_name": "Kim",
        "first_name": "Jae",
        "birth_date": "03.03.1992",
        "birth_place": "Seoul",
        "nationality": "südkoreanisch",
        "postal_code": "10243",
        "city": "Berlin",
        "street": "Friedrichstraße",
        "house_number": "100",
        "signature_place": "Berlin",
        "signature_date": "01.01.2024",
    },
    "niederlassungserlaubnis": {
        "last_name": "Müller",
        "first_name": "Sergei",
        "birth_date": "11.11.1975",
        "birth_place": "Moskau",
        "nationality": "russisch",
        "postal_code": "10785",
        "city": "Berlin",
        "street": "Potsdamer Str.",
        "house_number": "2",
        "signature_place": "Berlin",
        "signature_date": "01.01.2024",
    },
}


def _run_smoke_test(doc_type: str, user_data: Dict[str, Any], out_dir: Path) -> bool:
    """
    Generate preview + final PDF for one builder doc_type.
    Returns True if both files were created successfully.
    """
    from backend.form_builder import build_german_form, supported_doc_types

    if doc_type not in supported_doc_types():
        logger.error("[SMOKE] SKIP  doc_type=%s — not in supported_doc_types()", doc_type)
        return False

    preview_path = out_dir / f"{doc_type}_smoke_preview.pdf"
    final_path   = out_dir / f"{doc_type}_smoke_final.pdf"

    ok = True

    # Preview
    result = build_german_form(
        doc_type=doc_type,
        user_data=user_data,
        output_path=str(preview_path),
        is_preview=True,
        user_lang="de",
    )
    if result and Path(result).exists():
        logger.info("[SMOKE] OK    doc_type=%-35s mode=preview  path=%s", doc_type, result)
    else:
        logger.error("[SMOKE] FAIL  doc_type=%-35s mode=preview", doc_type)
        ok = False

    # Final
    result = build_german_form(
        doc_type=doc_type,
        user_data=user_data,
        output_path=str(final_path),
        is_preview=False,
        user_lang="de",
    )
    if result and Path(result).exists():
        logger.info("[SMOKE] OK    doc_type=%-35s mode=final    path=%s", doc_type, result)
    else:
        logger.error("[SMOKE] FAIL  doc_type=%-35s mode=final", doc_type)
        ok = False

    return ok


def run_all() -> bool:
    """Run smoke tests for all builder doc_types. Returns True if all pass."""
    from backend.pdf_renderers import BUILDER_DOCS

    with tempfile.TemporaryDirectory(prefix="smoke_builder_") as tmp:
        out_dir = Path(tmp)
        results = {}
        for doc_type in sorted(BUILDER_DOCS):
            data = _SAMPLE_DATA.get(doc_type)
            if data is None:
                logger.warning("[SMOKE] NO SAMPLE DATA for doc_type=%s — skipping", doc_type)
                continue
            results[doc_type] = _run_smoke_test(doc_type, data, out_dir)

    passed = sum(v for v in results.values())
    failed = sum(not v for v in results.values())
    logger.info("[SMOKE] Results: %d passed, %d failed (out of %d tested)", passed, failed, len(results))
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
