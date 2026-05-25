#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bürgergeld date + conditional-clear patch — PATCH 2 for VPS.

Fixes two bugs in the PDF generation pipeline:

  BUG 1 (document_config.py)
    leistungstraeger_von / leistungstraeger_bis are date fields but their
    key names don't contain "date"/"datum" so pdf_generator skips DD.MM.YYYY
    normalization. Dates end up in the PDF as YYYY-MM-DD (ISO from the browser
    date-picker) instead of German DD.MM.YYYY.
    FIX: add explicit handlers in get_value_for_pdf_field.

  BUG 2 (backend/utils/normalize.py)
    When has_andere_leistungen == "nein", only receives_benefits is cleared;
    the new leistungsart / leistungstraeger_* fields are left in user_data and
    would appear in the PDF even when the user said "no other benefits".
    Same problem for krankenkasse_name / versicherungsnummer when
    has_health_insurance == "nein".
    FIX: extend the conditional-clearing block.

Safe: idempotent, creates timestamped backups, validates via import.

Usage (on VPS):
    python3 /tmp/patch_buergergeld_dates.py
"""
import re
import sys
import shutil
from datetime import datetime

DC_PATH  = sys.argv[1] if len(sys.argv) > 1 else "/opt/civicassistbot/backend/document_config.py"
NRM_PATH = sys.argv[2] if len(sys.argv) > 2 else "/opt/civicassistbot/backend/utils/normalize.py"
TS       = datetime.now().strftime("%Y%m%d_%H%M%S")

print(f"[patch] document_config : {DC_PATH}")
print(f"[patch] normalize       : {NRM_PATH}")

# ─── Read ─────────────────────────────────────────────────────────────────────
with open(DC_PATH,  encoding="utf-8") as f: dc_content  = f.read()
with open(NRM_PATH, encoding="utf-8") as f: nrm_content = f.read()

# ─── Idempotency ──────────────────────────────────────────────────────────────
dc_done  = '"leistungstraeger_von", "leistungstraeger_bis"' in dc_content
nrm_done = '"leistungstraeger_name"' in nrm_content  # used as proxy

if dc_done and nrm_done:
    print("[patch] Both patches already applied — nothing to do. Exiting 0.")
    sys.exit(0)

# ─── Backups ──────────────────────────────────────────────────────────────────
if not dc_done:
    dc_bak  = DC_PATH  + ".bak_" + TS
    shutil.copy2(DC_PATH,  dc_bak)
    print(f"[patch] Backup dc  : {dc_bak}")

if not nrm_done:
    nrm_bak = NRM_PATH + ".bak_" + TS
    shutil.copy2(NRM_PATH, nrm_bak)
    print(f"[patch] Backup nrm : {nrm_bak}")

# =============================================================================
# PATCH A — document_config.py
# Insert YYYY-MM-DD → DD.MM.YYYY handlers for leistungstraeger date fields
# just before the general fallback:
#   value = user_data.get(field_name)
# =============================================================================
DATE_FIX = (
    "    # -- Buergergeld date fields: convert YYYY-MM-DD to DD.MM.YYYY --------\n"
    '    if field_name in ("leistungstraeger_von", "leistungstraeger_bis"):\n'
    "        raw = (user_data.get(field_name) or \"\").strip()\n"
    "        if raw and len(raw) == 10 and raw[4:5] == \"-\" and raw[7:8] == \"-\":\n"
    "            return f\"{raw[8:10]}.{raw[5:7]}.{raw[0:4]}\"\n"
    "        return raw or None\n"
    "\n"
)

# Unique anchor: the general-fallback start line (appears exactly once)
DC_ANCHOR = "    value = user_data.get(field_name)\n    if value is not None and str(value).strip():"

if not dc_done:
    if DC_ANCHOR not in dc_content:
        print("[ERROR] Anchor A not found in document_config.py — abort.")
        sys.exit(1)
    if dc_content.count(DC_ANCHOR) > 1:
        print(f"[ERROR] Anchor A appears {dc_content.count(DC_ANCHOR)} times — ambiguous.")
        sys.exit(1)
    dc_content = dc_content.replace(DC_ANCHOR, DATE_FIX + DC_ANCHOR, 1)
    print("[patch] PATCH A applied (date normalization in get_value_for_pdf_field)")

# =============================================================================
# PATCH B — backend/utils/normalize.py
# Extend conditional-clear block:
#   a) Clear leistungsart/leistungstraeger_* when has_andere_leistungen == nein
#   b) Clear krankenkasse_name/versicherungsnummer when has_health_insurance == nein
# =============================================================================

# ── Patch B1: extend has_andere_leistungen block ──────────────────────────────
# Anchor: the two lines that already exist
B1_ANCHOR = (
    '    if _is_nein("has_andere_leistungen"):\n'
    '        data["receives_benefits"] = ""\n'
)
B1_INSERT = (
    '    if _is_nein("has_andere_leistungen"):\n'
    '        data["receives_benefits"] = ""\n'
    '        for _lt_key in ("leistungsart", "leistungstraeger_name",\n'
    '                         "leistungstraeger_street", "leistungstraeger_house_number",\n'
    '                         "leistungstraeger_plz", "leistungstraeger_city",\n'
    '                         "leistungstraeger_von", "leistungstraeger_bis"):\n'
    '            data[_lt_key] = ""\n'
)

# ── Patch B2: add has_health_insurance block ──────────────────────────────────
# Anchor: is_schueler / is_asylbewerber gate (appears right after B1 in the code)
B2_ANCHOR = '    if _is_nein("has_sonderstatus"):\n        data["is_schueler"] = "nein"\n'
B2_INSERT = (
    '    # Clear Krankenversicherung text fields when not insured\n'
    '    if _is_nein("has_health_insurance"):\n'
    '        data["krankenkasse_name"] = ""\n'
    '        data["versicherungsnummer"] = ""\n'
    '\n'
)

if not nrm_done:
    # Apply B1
    if B1_ANCHOR not in nrm_content:
        print("[ERROR] Anchor B1 not found in normalize.py — abort.")
        sys.exit(1)
    if nrm_content.count(B1_ANCHOR) > 1:
        print(f"[ERROR] Anchor B1 appears {nrm_content.count(B1_ANCHOR)} times — ambiguous.")
        sys.exit(1)
    nrm_content = nrm_content.replace(B1_ANCHOR, B1_INSERT, 1)
    print("[patch] PATCH B1 applied (clear leistungsart/* when andere_leistungen=nein)")

    # Apply B2
    if B2_ANCHOR not in nrm_content:
        print("[ERROR] Anchor B2 not found in normalize.py — abort.")
        sys.exit(1)
    nrm_content = nrm_content.replace(B2_ANCHOR, B2_INSERT + B2_ANCHOR, 1)
    print("[patch] PATCH B2 applied (clear krankenkasse/versicherungsnummer when health_insurance=nein)")

# ─── Write ────────────────────────────────────────────────────────────────────
if not dc_done:
    with open(DC_PATH, "w", encoding="utf-8") as f: f.write(dc_content)
    print(f"[patch] Written: {DC_PATH}")

if not nrm_done:
    with open(NRM_PATH, "w", encoding="utf-8") as f: f.write(nrm_content)
    print(f"[patch] Written: {NRM_PATH}")

# ─── Validate ─────────────────────────────────────────────────────────────────
print("[patch] Validating imports...")
import importlib.util

ok = True

# Check document_config
spec = importlib.util.spec_from_file_location("_dc_v2", DC_PATH)
mod  = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    fn = mod.get_value_for_pdf_field
    # Simulate: date field in ISO format
    test_ud = {"leistungstraeger_von": "2024-03-15", "leistungstraeger_bis": "2024-06-30"}
    von_val = fn("leistungstraeger_von", test_ud)
    bis_val = fn("leistungstraeger_bis", test_ud)
    if von_val == "15.03.2024" and bis_val == "30.06.2024":
        print("    OK   date normalization von=15.03.2024  bis=30.06.2024")
    else:
        print(f"    FAIL date normalization von={von_val!r}  bis={bis_val!r}")
        ok = False
except Exception as e:
    print(f"    FAIL import: {e}")
    ok = False

# Check normalize
spec2 = importlib.util.spec_from_file_location("_nrm_v2", NRM_PATH)
mod2  = importlib.util.module_from_spec(spec2)
try:
    spec2.loader.exec_module(mod2)
    fn2 = mod2.normalize_buergergeld_data
    # Test B1: andere_leistungen=nein should clear leistungsart
    r1 = fn2({"has_andere_leistungen": "nein", "leistungsart": "ALG", "leistungstraeger_name": "Jobcenter"})
    if r1.get("leistungsart") == "" and r1.get("leistungstraeger_name") == "":
        print("    OK   clear leistungsart when andere_leistungen=nein")
    else:
        print(f"    FAIL clear leistungsart: {r1.get('leistungsart')!r}")
        ok = False
    # Test B2: health_insurance=nein should clear krankenkasse_name
    r2 = fn2({"has_health_insurance": "nein", "krankenkasse_name": "AOK", "versicherungsnummer": "123"})
    if r2.get("krankenkasse_name") == "" and r2.get("versicherungsnummer") == "":
        print("    OK   clear krankenkasse_name when health_insurance=nein")
    else:
        print(f"    FAIL clear krankenkasse_name: {r2.get('krankenkasse_name')!r}")
        ok = False
except Exception as e:
    print(f"    FAIL import normalize: {e}")
    ok = False

print()
if ok:
    print("[patch] ALL CHECKS PASSED")
    print("[patch] Next: supervisorctl restart civicassistbot")
else:
    print("[patch] CHECKS FAILED — restoring backups.")
    if not dc_done:  shutil.copy2(dc_bak,  DC_PATH)
    if not nrm_done: shutil.copy2(nrm_bak, NRM_PATH)
    sys.exit(1)
