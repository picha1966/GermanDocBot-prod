#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bürgergeld visible_if + label fix — PATCH 3 for VPS.

Changes (BUERGERGELD_SCHEMA only):
  FIX 1: Add visible_if has_andere_leistungen=ja to 8 leistungsart/* fields
  FIX 2: Add visible_if has_health_insurance=ja to krankenkasse_name + versicherungsnummer
  FIX 3: Add TODO comment before arbeitgeber section
  FIX 4: Change label_uk "З" → "З (від)" on leistungstraeger_von

Safe: idempotent, creates backup, validates via import + runtime schema check.

Usage (on VPS):
    python3 /tmp/patch_buergergeld_visible_if.py /opt/civicassistbot/backend/document_config.py
"""
import re
import sys
import shutil
from datetime import datetime

TARGET = sys.argv[1] if len(sys.argv) > 1 else "/opt/civicassistbot/backend/document_config.py"
BACKUP = TARGET + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")

print(f"[patch] Target : {TARGET}")

with open(TARGET, encoding="utf-8") as fh:
    content = fh.read()

# ── Idempotency ───────────────────────────────────────────────────────────────
# Check if leistungsart already has visible_if
for line in content.splitlines():
    if '"name": "leistungsart"' in line and '"visible_if"' in line:
        print("[patch] Already patched — nothing to do. Exiting 0.")
        sys.exit(0)

# ── Backup ────────────────────────────────────────────────────────────────────
shutil.copy2(TARGET, BACKUP)
print(f"[patch] Backup : {BACKUP}")

# ── Field lists ───────────────────────────────────────────────────────────────
LEISTUNG_FIELDS = [
    "leistungsart",
    "leistungstraeger_name",
    "leistungstraeger_street",
    "leistungstraeger_house_number",
    "leistungstraeger_plz",
    "leistungstraeger_city",
    "leistungstraeger_von",
    "leistungstraeger_bis",
]
KV_FIELDS = ["krankenkasse_name", "versicherungsnummer"]

VIF_LEISTUNG = '"visible_if": {"field": "has_andere_leistungen", "value": "ja"}'
VIF_KV       = '"visible_if": {"field": "has_health_insurance",  "value": "ja"}'

changes = []

# ── FIX 1 & 2: add visible_if via line-level replacement ─────────────────────
# Each new field is on ONE compact line ending with: , "required": False},
# Strategy: find the line by unique field name, inject visible_if before closing },
lines = content.splitlines(keepends=True)
new_lines = []

for line in lines:
    # FIX 1 — leistungsart / leistungstraeger_* (8 fields)
    matched = False
    for fname in LEISTUNG_FIELDS:
        if (f'"name": "{fname}"' in line
                and '"required": False},' in line
                and '"visible_if"' not in line):
            line = line.replace(
                '"required": False},',
                f'"required": False, {VIF_LEISTUNG}}},',
            )
            changes.append(f"visible_if → has_andere_leistungen=ja  [{fname}]")
            matched = True
            break

    # FIX 2 — krankenkasse_name / versicherungsnummer
    if not matched:
        for fname in KV_FIELDS:
            if (f'"name": "{fname}"' in line
                    and '"required": False},' in line
                    and '"visible_if"' not in line):
                line = line.replace(
                    '"required": False},',
                    f'"required": False, {VIF_KV}}},',
                )
                changes.append(f"visible_if → has_health_insurance=ja  [{fname}]")
                break

    # FIX 4 — label_uk "З" → "З (від)" on leistungstraeger_von only
    if '"name": "leistungstraeger_von"' in line and '"label_uk": "З",' in line:
        line = line.replace('"label_uk": "З",', '"label_uk": "З (від)",')
        changes.append('label_uk "З" → "З (від)"  [leistungstraeger_von]')

    new_lines.append(line)

content = ''.join(new_lines)

# ── FIX 3 — arbeitgeber section_visible_if ───────────────────────────────────
# VPS compact format: section is one line, inject section_visible_if after title_key
ARBT_ANCHOR = '{"id": "arbeitgeber", "title_key": "arbeitgeber",'
ARBT_VIF    = ' "section_visible_if": {"field": "employment_status", "value": "besch\\u00e4ftigt"},'
if ARBT_ANCHOR in content and '"section_visible_if"' not in content.split(ARBT_ANCHOR, 1)[1][:200]:
    content = content.replace(ARBT_ANCHOR, ARBT_ANCHOR + ARBT_VIF, 1)
    changes.append("arbeitgeber section_visible_if added")

# ── Write ─────────────────────────────────────────────────────────────────────
if not changes:
    print("[patch] No changes needed.")
    sys.exit(0)

with open(TARGET, "w", encoding="utf-8") as fh:
    fh.write(content)
print(f"[patch] Written  : {TARGET}")
for c in changes:
    print(f"  [OK]  {c}")

# ── Validate ──────────────────────────────────────────────────────────────────
print("[patch] Validating runtime import...")
import importlib.util

spec = importlib.util.spec_from_file_location("_dc_p3", TARGET)
mod  = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as exc:
    print(f"[FAIL] Import error: {exc}")
    shutil.copy2(BACKUP, TARGET)
    print(f"[patch] Restored from: {BACKUP}")
    sys.exit(1)

schema = mod.BUERGERGELD_SCHEMA
all_fields = {
    f["name"]: f
    for sec in schema["sections"]
    for f in sec.get("fields", [])
}

ok = True
print()
print("  FIX 1 — leistungsart/* visible_if:")
for fname in LEISTUNG_FIELDS:
    f = all_fields.get(fname)
    vif = f.get("visible_if") if f else None
    expected = {"field": "has_andere_leistungen", "value": "ja"}
    status = "OK  " if vif == expected else "FAIL"
    if status == "FAIL":
        ok = False
    print(f"    {status}  {fname}  visible_if={vif!r}")

print()
print("  FIX 2 — krankenkasse / versicherung visible_if:")
for fname in KV_FIELDS:
    f = all_fields.get(fname)
    vif = f.get("visible_if") if f else None
    expected = {"field": "has_health_insurance", "value": "ja"}
    status = "OK  " if vif == expected else "FAIL"
    if status == "FAIL":
        ok = False
    print(f"    {status}  {fname}  visible_if={vif!r}")

print()
print("  FIX 4 — leistungstraeger_von label_uk:")
f_von = all_fields.get("leistungstraeger_von")
lbl = f_von.get("label_uk") if f_von else None
if lbl == "З (від)":
    print(f"    OK    label_uk={lbl!r}")
else:
    print(f"    FAIL  label_uk={lbl!r}  (expected 'З (від)')")
    ok = False

print()
if ok:
    print(f"[patch] ALL {len(changes)} CHECKS PASSED.")
    print(f"[patch] Backup kept at : {BACKUP}")
    print("[patch] Next step      : supervisorctl restart civicassistbot")
else:
    print("[patch] CHECKS FAILED — restoring backup.")
    shutil.copy2(BACKUP, TARGET)
    print(f"[patch] Restored from  : {BACKUP}")
    sys.exit(1)
