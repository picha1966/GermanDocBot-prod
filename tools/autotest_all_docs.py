# -*- coding: utf-8 -*-
"""
tools/autotest_all_docs.py — Auto-test all 23 doc_types through create_final_pdf().
Generates synthetic user_data for each doc_type, measures time and memory,
validates output PDF fields, and prints a summary.

Usage:
    python tools/autotest_all_docs.py
    DEBUG_PDF=1 python tools/autotest_all_docs.py
"""
import sys, os, time, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
from typing import Dict, Any, Optional

import fitz

from backend.document_config import DOC_STRATEGY, _ACROFORM_MAPPINGS
from backend.pdf_renderers import DOC_RENDER_MAP
from backend.pdf_generator import create_final_pdf

# ── Synthetic user_data — covers all common schema keys ─────────────────────
BASE_USER_DATA: Dict[str, Any] = {
    # Personal
    "first_name": "Test", "last_name": "Nutzer",
    "birth_date": "1990-05-15", "birth_place": "Berlin",
    "nationality": "deutsch", "gender": "männlich",
    "familienstand": "ledig",
    # Address
    "street": "Teststraße", "house_number": "42", "plz": "10115", "city": "Berlin",
    "bundesland": "Berlin",
    # Previous address
    "previous_street": "Altstraße", "previous_house_number": "1",
    "previous_plz": "10117", "previous_city": "Berlin",
    # Contact
    "phone": "+4915112345678", "email": "test@example.de",
    # Document
    "passport_number": "T123456789", "passport_issuer": "Bürgeramt Berlin",
    "passport_valid_until": "2030-01-01",
    # Signature
    "signature_date": "2026-03-21", "signature_place": "Berlin",
    # Landlord
    "landlord_name": "Klaus Vermieter", "landlord_first_name": "Klaus",
    "landlord_last_name": "Vermieter",
    "landlord_street": "Vermieterstraße", "landlord_house_number": "1",
    "landlord_plz": "10115", "landlord_city": "Berlin",
    # Property
    "property_street": "Teststraße", "property_house_number": "42",
    "property_plz": "10115", "property_city": "Berlin",
    "num_persons": "2", "rental_start_date": "2024-01-01",
    "floor_area": "65", "num_rooms": "2", "num_bathrooms": "1",
    "total_rent": "1100", "rent_payment_start": "2024-01-01",
    "cold_rent": "850", "nebenkosten": "150", "electricity": "60", "heating": "90",
    # Child
    "child_first_name": "Max", "child_last_name": "Nutzer",
    "child_birth_date": "2018-06-01", "child_birth_place": "Berlin",
    "child_nationality": "deutsch",
    # Other parent
    "other_parent_first_name": "Eva", "other_parent_last_name": "Mueller",
    # Bank
    "bank_name": "Testbank AG", "iban": "DE89370400440532013000",
    # Education
    "university": "Technische Universität Berlin", "degree_program": "Informatik",
    "enrollment_date": "2022-10-01", "semester": "5",
    # Buergergeld / jobcenter specific
    "employment_status": "unemployed", "receives_benefits": "nein",
    "living_alone": "ja", "household_type": "single",
    "rent_status": "mieter", "has_health_insurance": "ja",
    "insurance_type": "gesetzlich", "has_residence_permit": "ja",
    "entry_date_germany": "2015-01-01", "warmwasser_zentral": "ja",
    "birth_country": "Deutschland",
    "has_sv_number": "ja", "sv_number": "T123456789",
    # Elterngeld
    "eg_child_vorname": "Max", "eg_child_nachname": "Nutzer",
    "eg_child_birth_date": "2018-06-01", "eg_ort_datum": "Berlin, 21.03.2026",
    # Unterhaltsvorschuss
    "uv_applicant_name": "Nutzer, Test", "uv_birth_date": "1990-05-15",
    "uv_address": "Teststraße 42, 10115 Berlin", "uv_bank_name": "Testbank AG",
    "uv_child_name": "Max Nutzer", "uv_child_birth_date": "2018-06-01",
    "uv_other_parent_name": "Mueller, Eva",
    # Aufenthaltstitel
    "residence_permit_type": "Niederlassungserlaubnis",
    "residence_permit_valid_until": "2030-01-01",
    # Wohnungsgeber
    "wgb_landlord_name": "Klaus Vermieter",
    "wgb_property_address": "Teststraße 42, 10115 Berlin",
    "wgb_move_in_date": "2024-01-01",
    # Verpflichtungserklaerung
    "vp_visitor_name": "Ivan Gast",
    "vp_visitor_birth_date": "1985-03-10",
    "vp_visitor_nationality": "ukrainisch",
    # EBK
    "ebk_employer_name": "Test GmbH",
    "ebk_employment_start": "2023-01-01",
    # KGA
    "kga_applicant_name": "Nutzer, Test",
    "kga_child_last_name": "Nutzer", "kga_child_first_name": "Max",
    "kga_child_birth_date": "2018-06-01", "kga_child_birth_place": "Berlin",
    "kga_child_nationality": "deutsch",
    # Anmeldung / Ummeldung / Abmeldung
    "move_in_date": "2024-01-01", "move_out_date": "2026-03-01",
    "previous_ort": "Hamburg",
    "postal_code": "10115",          # some schemas use postal_code vs plz
    # Employer (beschaeftigungserklaerung / ebk / buergergeld)
    "employer_name": "Test GmbH",
    "employment_start_date": "2023-01-01",
    # Household (buergergeld / wohngeld / kindergeld)
    "household_members": "2", "monthly_rent": "1100",
    "living_space_sqm": "65", "monthly_income": "2500",
    # Aufenthaltstitel / Niederlassungserlaubnis
    "dokumentenart": "Aufenthaltstitel", "seriennummer": "L01A123456",
    "ausstellungsbehoerde": "Ausländerbehörde Berlin",
    "ausstellungsdatum": "2022-01-15", "gueltig_bis": "2027-01-14",
    "residence_purpose": "Arbeit",
    # WBS
    "income": "2500",
    # Partner data (kinderzuschlag, etc.)
    "partner_first_name": "Eva", "partner_last_name": "Mueller",
    "partner_birth_date": "1988-04-20", "partner_nationality": "deutsch",
    # Employer data (beschaeftigungserklaerung, ebk)
    "employer_street": "Firmenstraße", "employer_house_number": "10",
    "employer_plz": "10117", "employer_city": "Berlin",
    "contact_person": "HR Team",
    "betriebsnummer": "12345678",
    "employment_type": "Vollzeit", "job_title": "Softwareentwickler",
    "degree_type": "Bachelor",
    "hours_per_week": "40", "hourly_rate": "25.00",
    # Verpflichtungserklaerung visitor
    "vp_besucher_name": "Ivan Gast",
    "vp_besucher_gebdatum": "1985-03-10",
    "vp_besucher_staatsangeh": "ukrainisch",
    "vp_einreisedatum": "2026-04-01",
    "vp_aufenthaltsdauer": "30 Tage",
    "vp_reisezweck": "Tourismus",
    # Mietbescheinigung schema-specific keys
    "mb_anzahl_personen": "2",
    "mb_mietbeginn": "2024-01-01",
    "mb_wohnungsflaeche": "65",
    "mb_zimmer": "2",
    "mb_bäder": "1",
    "mb_gesamtmiete": "1100",
    "mb_beginn_zahlung": "2024-01-01",
    "mb_kaltmiete": "850",
    "mb_nebenkosten": "150",
    "mb_stromkosten": "60",
    "mb_heizkosten": "90",
}

# Per-doc overrides for required fields that differ from BASE
DOC_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "mietbescheinigung": {
        "landlord_name": "Klaus Vermieter",
        "property_street": "Teststraße", "property_house_number": "42",
        "property_plz": "10115", "property_city": "Berlin",
    },
    "unterhaltsvorschuss": {"bundesland": "Berlin"},
    "buergergeld":  {"has_sv_number": "ja", "sv_number": "T123456789", "iban": "DE89370400440532013000"},
    "jobcenter":    {"has_sv_number": "ja", "sv_number": "T123456789", "iban": "DE89370400440532013000"},
    "bafoeg":       {"bundesland": "Berlin"},
}


def make_user_data(doc_type: str) -> Dict[str, Any]:
    data = dict(BASE_USER_DATA)
    data.update(DOC_OVERRIDES.get(doc_type, {}))
    return data


def count_filled_fields(pdf_path: str, mapping: Dict[str, str]) -> tuple:
    """Returns (filled_count, empty_text_fields) for the given PDF."""
    try:
        _pdf = fitz.open(pdf_path)
        _vals: Dict[str, str] = {}
        for _page in _pdf:
            for _w in _page.widgets():
                _fn = getattr(_w, "field_name", None)
                if _fn:
                    _vals[_fn] = _w.field_value or ""
        _pdf.close()
    except Exception:
        return 0, []

    filled = 0
    empty_text = []
    seen_pdf_fields = set()
    for _sk, _pf in mapping.items():
        if _pf in seen_pdf_fields:
            continue
        seen_pdf_fields.add(_pf)
        if _pf not in _vals:
            continue
        val = (_vals[_pf] or "").strip()
        is_checkbox = any(x in _pf.lower() for x in ("chbx", "rbtn", "auswahl", "check"))
        if val and val != "Off":
            filled += 1
        elif not is_checkbox and not val:
            empty_text.append(_pf)

    return filled, empty_text


# ── Main test loop ───────────────────────────────────────────────────────────
ALL_DOCS = sorted(set(DOC_STRATEGY.keys()) | set(DOC_RENDER_MAP.keys()))

results = []
SLOW_THRESHOLD_S = 3.0  # warn if generation takes longer

# Warmup: pre-import all lazy modules so first real test isn't penalized
# by Python module import time (~1-2s cold start).
print("  Warming up (pre-importing modules)...", end="", flush=True)
try:
    _wu_data = {**BASE_USER_DATA, **DOC_OVERRIDES.get("aufenthaltserlaubnis_antrag", {})}
    create_final_pdf(user_id=0, doc_type="aufenthaltserlaubnis_antrag", user_data=_wu_data, user_lang="de")
except Exception:
    pass
print(" done\n")

print(f"\n{'='*70}")
print(f"  Auto-test: {len(ALL_DOCS)} doc_types")
print(f"{'='*70}")

for dt in ALL_DOCS:
    strategy = DOC_RENDER_MAP.get(dt, "MISSING")
    mapping = _ACROFORM_MAPPINGS.get(dt, {})
    user_data = make_user_data(dt)

    t0 = time.perf_counter()
    mem_before = 0
    try:
        import tracemalloc
        tracemalloc.start()
        mem_before = tracemalloc.get_traced_memory()[0]
    except Exception:
        pass

    result = None
    error = None
    status = "PASS"
    filled_count = 0
    empty_fields = []

    try:
        result = create_final_pdf(user_id=88888, doc_type=dt, user_data=user_data, user_lang="de")
    except Exception as e:
        error = str(e)
        status = "ERROR"

    elapsed = time.perf_counter() - t0

    mem_used_kb = 0
    try:
        _, mem_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        mem_used_kb = mem_peak // 1024
    except Exception:
        pass

    if status != "ERROR":
        if isinstance(result, dict):
            status = "BLOCKED"
            error = f"validation: {result.get('missing_fields', [])}"
        elif result and Path(result).exists():
            size = Path(result).stat().st_size
            if mapping:
                filled_count, empty_fields = count_filled_fields(result, mapping)
            status = "PASS"
        else:
            status = "FAIL"
            error = f"returned {result!r}"

    flag = "✓" if status == "PASS" else ("⚠" if status == "BLOCKED" else "✗")
    timing_warn = f" [SLOW {elapsed:.1f}s]" if elapsed > SLOW_THRESHOLD_S else f" ({elapsed:.2f}s)"
    mapping_info = f" {filled_count}/{len(mapping)} fields" if mapping else " (builder)"
    empty_warn = f" ⚠ empty: {empty_fields[:3]}" if empty_fields else ""

    print(f"  {flag}  {dt:<35s} {strategy:<14s}{timing_warn}{mapping_info}{empty_warn}")
    if error:
        print(f"       → {error}")

    results.append({
        "doc_type": dt, "status": status, "strategy": strategy,
        "elapsed_s": elapsed, "mem_kb": mem_used_kb,
        "filled": filled_count, "mapping_total": len(mapping),
        "empty_fields": empty_fields, "error": error,
    })

# ── Summary ──────────────────────────────────────────────────────────────────
passed  = [r for r in results if r["status"] == "PASS"]
failed  = [r for r in results if r["status"] in ("FAIL", "ERROR")]
blocked = [r for r in results if r["status"] == "BLOCKED"]
slow    = [r for r in results if r["elapsed_s"] > SLOW_THRESHOLD_S]
missing_maps = [r for r in results if r["strategy"] == "acroform" and r["mapping_total"] == 0]

print(f"\n{'='*70}")
print(f"  Summary")
print(f"{'='*70}")
print(f"  Total doc_types : {len(results)}")
print(f"  Passed          : {len(passed)}")
print(f"  Blocked (valid) : {len(blocked)}")
print(f"  Failed/Error    : {len(failed)}")
print(f"  Slow (>{SLOW_THRESHOLD_S}s)    : {len(slow)}")
print(f"  Missing mappings: {len(missing_maps)}")

if slow:
    print(f"\n  Slow doc_types:")
    for r in sorted(slow, key=lambda x: -x["elapsed_s"]):
        print(f"    {r['doc_type']}: {r['elapsed_s']:.2f}s  ({r['mem_kb']} KB peak)")

if failed:
    print(f"\n  Failures:")
    for r in failed:
        print(f"    {r['doc_type']}: {r['error']}")

if missing_maps:
    print(f"\n  Acroform docs without mapping:")
    for r in missing_maps:
        print(f"    {r['doc_type']}")

avg_time = sum(r["elapsed_s"] for r in results) / max(len(results), 1)
print(f"\n  Avg time/doc    : {avg_time:.2f}s")
print(f"  Total time      : {sum(r['elapsed_s'] for r in results):.2f}s")
print()
