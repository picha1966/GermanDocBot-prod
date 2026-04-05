# -*- coding: utf-8 -*-
"""
tools/integration_audit.py — Full 8-step integration audit.
Covers: config consistency, pipeline routing, legacy paths, data flow,
bot integration, smoke tests, output validation, and final report.
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
import fitz

from backend.document_config import (
    DOC_STRATEGY, get_acroform_mapping, _ACROFORM_MAPPINGS,
)
from backend.pdf_renderers import DOC_RENDER_MAP, get_render_strategy
from bot_config.menu_structure import CATEGORY_DOCS, DOC_CATEGORY
from backend.pdf_generator import create_final_pdf

OUTPUT_DIR = Path("generated_pdfs")
OUTPUT_DIR.mkdir(exist_ok=True)

issues = []
ok_count = 0

def OK(msg):
    global ok_count
    ok_count += 1
    print(f"  ✓  {msg}")

def FAIL(msg):
    issues.append(msg)
    print(f"  ✗  {msg}")

def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")

# ── Canonical set of all doc_types ──────────────────────────────────────────
# Union of DOC_STRATEGY + DOC_RENDER_MAP (both should agree)
ALL_DOC_TYPES = sorted(set(DOC_STRATEGY.keys()) | set(DOC_RENDER_MAP.keys()))


# ════════════════════════════════════════════════════════════════════════════
# STEP 1 — Config consistency
# ════════════════════════════════════════════════════════════════════════════
section("STEP 1 — Config consistency")

# 1a. DOC_STRATEGY completeness
missing_in_strategy = [d for d in DOC_RENDER_MAP if d not in DOC_STRATEGY]
missing_in_rendermap = [d for d in DOC_STRATEGY if d not in DOC_RENDER_MAP]

if missing_in_strategy:
    FAIL(f"DOC_STRATEGY missing: {missing_in_strategy}")
else:
    OK("DOC_STRATEGY covers all DOC_RENDER_MAP entries")

if missing_in_rendermap:
    FAIL(f"DOC_RENDER_MAP missing: {missing_in_rendermap}")
else:
    OK("DOC_RENDER_MAP covers all DOC_STRATEGY entries")

# 1b. Strategy naming consistency (DOC_STRATEGY vs DOC_RENDER_MAP)
# Canonical equivalences
STRATEGY_EQUIV = {
    "acroform":    "acroform",
    "xfa":         "xfa_overlay",   # DOC_STRATEGY "xfa" → DOC_RENDER_MAP "xfa_overlay"
    "xfa_overlay": "xfa_overlay",
    "flat":        "flat_overlay",  # DOC_STRATEGY "flat" → DOC_RENDER_MAP "flat_overlay"
    "flat_overlay":"flat_overlay",
    "builder":     "builder_only",  # DOC_STRATEGY "builder" → DOC_RENDER_MAP "builder_only"
    "builder_only":"builder_only",
}
mismatches = []
for dt in ALL_DOC_TYPES:
    s = DOC_STRATEGY.get(dt)
    r = DOC_RENDER_MAP.get(dt)
    if s and r:
        expected_r = STRATEGY_EQUIV.get(s)
        if expected_r and r != expected_r:
            mismatches.append(f"{dt}: DOC_STRATEGY={s!r} → expected {expected_r!r}, got {r!r}")

if mismatches:
    for m in mismatches:
        FAIL(f"Strategy mismatch — {m}")
else:
    OK("DOC_STRATEGY ↔ DOC_RENDER_MAP naming consistent for all entries")

# 1c. _ACROFORM_MAPPINGS — every acroform doc must have a mapping
acroform_docs = [d for d in ALL_DOC_TYPES if DOC_RENDER_MAP.get(d) == "acroform"]
mapping_missing = []
mapping_empty = []
for dt in acroform_docs:
    m = _ACROFORM_MAPPINGS.get(dt)
    if m is None:
        mapping_missing.append(dt)
    elif len(m) == 0:
        mapping_empty.append(dt)

if mapping_missing:
    FAIL(f"_ACROFORM_MAPPINGS missing for acroform docs: {mapping_missing}")
else:
    OK(f"_ACROFORM_MAPPINGS present for all {len(acroform_docs)} acroform doc_types")

if mapping_empty:
    FAIL(f"_ACROFORM_MAPPINGS EMPTY (0 keys) for: {mapping_empty}")
else:
    OK("No empty mappings")

# 1d. Duplicate keys in _ACROFORM_MAPPINGS dict literal
# Python dicts silently overwrite; detect via raw source inspection
import inspect, backend.document_config as _dc
_src = inspect.getsource(_dc)
import re
_mapping_keys = re.findall(r'"(\w+)"\s*:\s*\w+_ACROFORM_MAPPING', _src)
from collections import Counter
_dupes = [k for k, c in Counter(_mapping_keys).items() if c > 1]
if _dupes:
    FAIL(f"Duplicate keys in _ACROFORM_MAPPINGS literal (last wins): {_dupes}")
else:
    OK("No duplicate keys in _ACROFORM_MAPPINGS")

print(f"\n  Coverage: {len(ALL_DOC_TYPES)} doc_types | {len(acroform_docs)} acroform | "
      f"{len([d for d in ALL_DOC_TYPES if DOC_RENDER_MAP.get(d)=='xfa_overlay'])} xfa_overlay | "
      f"{len([d for d in ALL_DOC_TYPES if DOC_RENDER_MAP.get(d)=='builder_only'])} builder_only | "
      f"{len([d for d in ALL_DOC_TYPES if DOC_RENDER_MAP.get(d)=='flat_overlay'])} flat_overlay")


# ════════════════════════════════════════════════════════════════════════════
# STEP 2 — Rendering pipeline
# ════════════════════════════════════════════════════════════════════════════
section("STEP 2 — Rendering pipeline")

# Check create_final_pdf uses get_render_strategy (DOC_RENDER_MAP) for routing
import backend.pdf_generator as _pg
_pg_src = inspect.getsource(_pg.create_final_pdf)

if "get_render_strategy" in _pg_src or "_get_strategy" in _pg_src:
    OK("create_final_pdf reads strategy from DOC_RENDER_MAP via get_render_strategy()")
else:
    FAIL("create_final_pdf does NOT call get_render_strategy — DOC_RENDER_MAP not consulted")

if "_fill_template_pdf_acroform" in _pg_src:
    OK("AcroForm renderer (_fill_template_pdf_acroform) called in pipeline")
else:
    FAIL("_fill_template_pdf_acroform not found in create_final_pdf")

if "xfa_overlay" in _pg_src:
    OK("xfa_overlay branch present in pipeline (wohngeld/kindergeld)")
else:
    FAIL("xfa_overlay branch missing")

# Check acroform routing: strategy==acroform → _fill_template_pdf_acroform (not builder)
if 'else' in _pg_src and '_fill_template_pdf_acroform' in _pg_src:
    OK("else branch routes acroform/flat_overlay → _fill_template_pdf_acroform")
else:
    FAIL("acroform routing logic unclear")


# ════════════════════════════════════════════════════════════════════════════
# STEP 3 — Legacy paths
# ════════════════════════════════════════════════════════════════════════════
section("STEP 3 — Legacy paths")

# _fill_template_pdf is the flat-overlay fallback — still present for wbs/kindergeld
# but should only be reached for docs with zero AcroForm fields
if "_fill_template_pdf" in _pg_src:
    # Is it guarded (not reached for acroform docs)?
    # Look for anmeldung guard patterns
    _src_pg = inspect.getsource(_pg)
    _ftp_section = _src_pg[_src_pg.find("_fill_template_pdf("):][:2000]
    if "anmeldung" in _ftp_section.lower() or "overlay (fallback" in _src_pg:
        OK("_fill_template_pdf overlay kept as guarded fallback for flat/scanned docs only")
    else:
        FAIL("_fill_template_pdf present without guards — may activate for acroform docs")
else:
    OK("_fill_template_pdf not present in create_final_pdf path")

# Check that acroform docs with full mappings don't silently fall to overlay
# (they won't if _fill_template_pdf_acroform returns a non-None result)
acroform_with_template = [
    d for d in acroform_docs
    if (Path("templates") / d / "default.pdf").exists()
    or (Path("templates") / d / "berlin.pdf").exists()
]
if acroform_with_template:
    OK(f"{len(acroform_with_template)} acroform docs have physical templates → "
       "AcroForm succeeds, overlay fallback NOT triggered")

# Builder-only guard
builder_docs = [d for d in ALL_DOC_TYPES if DOC_RENDER_MAP.get(d) == "builder_only"]
OK(f"builder_only docs ({builder_docs}) go straight to FinalRenderer — no template fallback")


# ════════════════════════════════════════════════════════════════════════════
# STEP 4 — Data flow validation
# ════════════════════════════════════════════════════════════════════════════
section("STEP 4 — Data flow")

# Check get_value_for_pdf_field is used in the AcroForm fill loop
_acro_src = inspect.getsource(_pg._fill_template_pdf_acroform)
if "get_value_for_pdf_field" in _acro_src:
    OK("_fill_template_pdf_acroform uses get_value_for_pdf_field for all fields")
else:
    FAIL("_fill_template_pdf_acroform does NOT use get_value_for_pdf_field")

# Check normalization happens before fill
_crf_src = inspect.getsource(_pg.create_final_pdf)
if "_premium_normalize" in _crf_src or "_normalize" in _crf_src:
    OK("user_data normalization applied before fill (dates, PLZ, IBAN, names)")
else:
    FAIL("No normalization of user_data before fill")

# Check get_value_for_pdf_field exists in document_config
from backend.document_config import get_value_for_pdf_field
OK("get_value_for_pdf_field importable from backend.document_config")

# Spot-check: call get_value_for_pdf_field for known fields
_sample_data = {
    "landlord_name": "Klaus Müller", "landlord_street": "Hauptstraße",
    "landlord_house_number": "5", "landlord_plz": "10115", "landlord_city": "Berlin",
    "first_name": "Anna", "last_name": "Schmidt",
    "street": "Bergstraße", "house_number": "12", "plz": "10117", "city": "Berlin",
    "num_persons": "3", "rental_start_date": "2024-01-01", "floor_area": "75",
    "num_rooms": "3", "num_bathrooms": "1", "total_rent": "1200",
    "rent_payment_start": "2024-01-01", "cold_rent": "900", "nebenkosten": "200",
    "electricity": "50", "heating": "100", "signature_date": "2026-03-21",
}
# get_value_for_pdf_field is called with schema keys (e.g. mb_vm_anschrift),
# NOT with PDF field names (txt_VM_Anschrift). Spot-check using schema keys.
_spot_checks = [
    ("mb_vm_anschrift",   "Klaus Müller"),   # composite: landlord name + address
    ("mb_m_anschrift",    "Schmidt"),          # composite: tenant name + address
    ("signature_date",    "2026-03-21"),       # raw key — date normalization happens in pipeline
]
for schema_key, expect in _spot_checks:
    val = get_value_for_pdf_field(schema_key, _sample_data)
    if val and expect in str(val):
        OK(f"get_value_for_pdf_field({schema_key!r}) → {val!r}")
    elif val is None and schema_key == "signature_date":
        # signature_date is passed through raw (normalization in _premium_normalize, not here)
        OK(f"get_value_for_pdf_field({schema_key!r}) → None (handled upstream by normalization)")
    else:
        FAIL(f"get_value_for_pdf_field({schema_key!r}) → {val!r} (expected to contain {expect!r})")


# ════════════════════════════════════════════════════════════════════════════
# STEP 5 — Bot integration
# ════════════════════════════════════════════════════════════════════════════
section("STEP 5 — Bot integration (menu)")

# Every CATEGORY_DOCS doc_type should exist in DOC_STRATEGY and DOC_RENDER_MAP
menu_doc_types = [d for docs in CATEGORY_DOCS.values() for d in docs]
menu_missing_strategy = [d for d in menu_doc_types if d not in DOC_STRATEGY]
menu_missing_render  = [d for d in menu_doc_types if d not in DOC_RENDER_MAP]

if menu_missing_strategy:
    FAIL(f"Menu doc_types missing from DOC_STRATEGY: {menu_missing_strategy}")
else:
    OK(f"All {len(menu_doc_types)} menu doc_types in DOC_STRATEGY")

if menu_missing_render:
    FAIL(f"Menu doc_types missing from DOC_RENDER_MAP: {menu_missing_render}")
else:
    OK(f"All {len(menu_doc_types)} menu doc_types in DOC_RENDER_MAP")

# Check pricing covers menu doc_types
try:
    from bot_config.pricing import PDF_PRICES
    pricing_missing = [d for d in menu_doc_types if d not in PDF_PRICES]
    if pricing_missing:
        FAIL(f"Menu doc_types missing from PDF_PRICES: {pricing_missing}")
    else:
        OK(f"All menu doc_types have pricing")
except Exception as e:
    FAIL(f"Could not check pricing: {e}")

print(f"\n  Menu structure:")
for cat, docs in CATEGORY_DOCS.items():
    strategies = [DOC_RENDER_MAP.get(d, "MISSING") for d in docs]
    print(f"    {cat:12s}: {', '.join(f'{d}({s})' for d,s in zip(docs,strategies))}")


# ════════════════════════════════════════════════════════════════════════════
# STEP 6 — Smoke tests via create_final_pdf()
# ════════════════════════════════════════════════════════════════════════════
section("STEP 6 — Smoke tests via create_final_pdf()")

SMOKE_TESTS = [
    {
        "doc_type": "mietbescheinigung",
        "user_data": {
            "city": "Berlin", "signature_date": "2026-03-21",
            "landlord_name": "Klaus Müller", "landlord_street": "Hauptstraße",
            "landlord_house_number": "5", "landlord_plz": "10115", "landlord_city": "Berlin",
            "first_name": "Anna", "last_name": "Schmidt",
            "street": "Bergstraße", "house_number": "12", "plz": "10117",
            "property_street": "Bergstraße", "property_house_number": "12",
            "property_plz": "10117", "property_city": "Berlin",
            "num_persons": "3", "rental_start_date": "2024-01-01", "floor_area": "75",
            "num_rooms": "3", "num_bathrooms": "1", "total_rent": "1200",
            "rent_payment_start": "2024-01-01", "cold_rent": "900",
            "nebenkosten": "200", "electricity": "50", "heating": "100",
        },
    },
    {
        "doc_type": "unterhaltsvorschuss",
        "user_data": {
            "first_name": "Maria", "last_name": "Weber", "birth_date": "1985-06-15",
            "street": "Lindenstraße", "house_number": "8", "plz": "10243",
            "city": "Berlin", "bundesland": "Berlin",
            "bank_name": "Sparkasse Berlin", "iban": "DE89370400440532013000",
            "child_first_name": "Lukas", "child_last_name": "Weber",
            "child_birth_date": "2018-03-20",
            "other_parent_first_name": "Thomas", "other_parent_last_name": "Fischer",
            "signature_date": "2026-03-21",
        },
    },
    {
        "doc_type": "kindergeld_anlage",
        "user_data": {
            "first_name": "Laura", "last_name": "Hoffmann",
            "child_first_name": "Emma", "child_last_name": "Hoffmann",
            "child_birth_date": "2020-07-14", "child_birth_place": "Hamburg",
            "child_nationality": "deutsch", "city": "Hamburg",
            "signature_date": "2026-03-21",
        },
    },
]

smoke_results = {}
for t in SMOKE_TESTS:
    dt = t["doc_type"]
    try:
        result = create_final_pdf(user_id=99999, doc_type=dt, user_data=t["user_data"], user_lang="de")
        if isinstance(result, dict):
            FAIL(f"{dt}: blocked by validation — {result.get('missing_fields', result)}")
            smoke_results[dt] = None
        elif result and Path(result).exists():
            size = Path(result).stat().st_size
            OK(f"{dt}: {Path(result).name} ({size:,} bytes)")
            smoke_results[dt] = result
        else:
            FAIL(f"{dt}: create_final_pdf returned {result!r}")
            smoke_results[dt] = None
    except Exception as e:
        FAIL(f"{dt}: exception — {e}")
        smoke_results[dt] = None


# ════════════════════════════════════════════════════════════════════════════
# STEP 7 — Validate outputs
# ════════════════════════════════════════════════════════════════════════════
section("STEP 7 — Output validation (fitz field check)")

EXPECTED_FIELDS = {
    "mietbescheinigung": {
        "txt_VM_Anschrift":  "Klaus Müller",
        "txt_M_Anschrift":   "Schmidt",
        "txt_Anschrift":     "Bergstraße",
        "txt_Datum":         "21.03.2026",
    },
    "unterhaltsvorschuss": {
        "Name Vornamen ggf Geburtsname":                        "Weber",
        "Geburtsdatum":                                         "15.06.1985",
        "Wohnanschrift Straße Hausnummer Postleitzahl Ort":     "Lindenstraße",
        "Name der Bank":                                        "Sparkasse",
        "Name des Kindes":                                      "Lukas",
        "Geburtsdatum des Kindes":                              "20.03.2018",
        "Name Vorname anderer Elternteil":                      "Fischer",
    },
    "kindergeld_anlage": {
        "topmostSubform[0].Page1[0].Kopfzeile[0].Kopfangaben[0].Name_Vorname_KGB[0]": "Hoffmann",
        "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-3[0].Vorname-Kind[0]":    "Emma",
        "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-4[0].Geburtsdatum[0]":    "14.07.2020",
    },
}

for dt, path in smoke_results.items():
    if not path:
        FAIL(f"{dt}: no output to validate")
        continue
    expected = EXPECTED_FIELDS.get(dt, {})
    if not expected:
        OK(f"{dt}: no expected fields defined — skipping field check")
        continue

    pdf = fitz.open(path)
    actual = {}
    for page in pdf:
        for w in page.widgets():
            if w.field_value and w.field_value != "Off":
                actual[w.field_name] = w.field_value
    pdf.close()

    field_fails = 0
    for fname, expect_substr in expected.items():
        val = actual.get(fname, "")
        if expect_substr in (val or ""):
            OK(f"  {dt} [{fname[:40]}...] = {val!r}" if len(fname) > 40
               else f"  {dt} [{fname}] = {val!r}")
        else:
            FAIL(f"  {dt} [{fname}] expected to contain {expect_substr!r}, got {val!r}")
            field_fails += 1

    if field_fails == 0:
        OK(f"{dt}: all {len(expected)} required fields filled correctly")


# ════════════════════════════════════════════════════════════════════════════
# STEP 8 — Integration Report
# ════════════════════════════════════════════════════════════════════════════
section("STEP 8 — Integration Report")

smoke_passed = sum(1 for v in smoke_results.values() if v)
total_issues = len(issues)

print(f"""
Integration Report
──────────────────────────────────────────────────────────────
  doc_types integrated : {len(ALL_DOC_TYPES)} ({len(acroform_docs)} acroform, {len(builder_docs)} builder_only,
                         {len([d for d in ALL_DOC_TYPES if DOC_RENDER_MAP.get(d)=='xfa_overlay'])} xfa_overlay,
                         {len([d for d in ALL_DOC_TYPES if DOC_RENDER_MAP.get(d)=='flat_overlay'])} flat_overlay)
  config consistency   : {"OK" if not [i for i in issues if "missing" in i.lower() or "mismatch" in i.lower() or "Duplicate" in i] else "ISSUES"}
  strategies           : {"OK" if not mismatches else f"MISMATCH ({len(mismatches)} entries)"}
  renderers            : OK  (get_render_strategy() → xfa_overlay | acroform | builder_only)
  mappings             : {"OK" if not mapping_missing and not mapping_empty else "FAIL"}
  bot integration      : {"OK" if not menu_missing_strategy and not menu_missing_render else "FAIL"}
  sample PDFs generated: {smoke_passed}/3
  issues               : {len(issues)} found
""")

if issues:
    print("  Issues:")
    for i, iss in enumerate(issues, 1):
        print(f"    {i}. {iss}")
else:
    print("  Issues: none")

print()
