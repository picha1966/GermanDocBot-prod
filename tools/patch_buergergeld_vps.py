#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bürgergeld surgical patch — VPS deployment.

Adds 10 new fields to BUERGERGELD_SCHEMA and 10 entries to JOBCENTER_ACROFORM_MAPPING.
Designed for the compact single-line schema format used on the VPS (git HEAD, ~3400 lines).

Safe:
  - creates a timestamped backup before any change
  - idempotent: exits 0 without touching the file if already patched
  - validates every anchor before writing
  - verifies all 10 fields + 10 mapping keys after writing via live import
  - auto-restores backup and exits non-zero on any failure

Usage (on VPS):
    python3 /tmp/patch_buergergeld_vps.py /opt/civicassistbot/backend/document_config.py
"""
import re
import sys
import shutil
from datetime import datetime

TARGET = sys.argv[1] if len(sys.argv) > 1 else "/opt/civicassistbot/backend/document_config.py"
BACKUP = TARGET + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")

print(f"[patch] Target : {TARGET}")

# ── Read ──────────────────────────────────────────────────────────────────────
with open(TARGET, encoding="utf-8") as fh:
    content = fh.read()

# ── Idempotency guard ─────────────────────────────────────────────────────────
already = (
    '"leistungsart"' in content
    and '"krankenkasse_name"' in content
    and '"versicherungsnummer"' in content
    and '"txtfPersonLeistungsart"' in content
)
if already:
    print("[patch] Already patched — nothing to do. Exiting 0.")
    sys.exit(0)

# ── Backup ────────────────────────────────────────────────────────────────────
shutil.copy2(TARGET, BACKUP)
print(f"[patch] Backup : {BACKUP}")

# =============================================================================
# PATCH 1
# Insert 8 Leistungsträger fields into BUERGERGELD_SCHEMA einkommen section,
# after "has_andere_leistungen" field, before "receives_benefits".
#
# Anchor (12-space indent, appears exactly once):
#   "            # specific benefit checkboxes (chbxPersonLeistung*)"
# =============================================================================

ANCHOR1 = "            # specific benefit checkboxes (chbxPersonLeistung*)"

# 12-space indent matches VPS compact schema style
FIELDS_1 = (
    '            {"name": "leistungsart",'
    ' "label_de": "Art der Leistung",'
    ' "label_uk": "\u0412\u0438\u0434 \u0432\u0438\u043f\u043b\u0430\u0442\u0438",'
    ' "label_en": "Type of benefit",'
    ' "label_pl": "Rodzaj \u015bwiadczenia",'
    ' "label_tr": "Yard\u0131m t\u00fcr\u00fc",'
    ' "label_ar": "\u0646\u0648\u0639 \u0627\u0644\u0645\u0633\u0627\u0639\u062f\u0629",'
    ' "type": "text", "required": False},\n'

    '            {"name": "leistungstraeger_name",'
    ' "label_de": "Name des Leistungstr\u00e4gers",'
    ' "label_uk": "\u041d\u0430\u0437\u0432\u0430 \u043e\u0440\u0433\u0430\u043d\u0443 \u0432\u0438\u043f\u043b\u0430\u0442",'
    ' "label_en": "Name of paying authority",'
    ' "label_pl": "Nazwa instytucji wyp\u0142acaj\u0105cej",'
    ' "label_tr": "\u00d6deme kurumu ad\u0131",'
    ' "label_ar": "\u0627\u0633\u0645 \u0627\u0644\u062c\u0647\u0629 \u0627\u0644\u062f\u0627\u0641\u0639\u0629",'
    ' "type": "text", "required": False},\n'

    '            {"name": "leistungstraeger_street",'
    ' "label_de": "Stra\u00dfe",'
    ' "label_uk": "\u0412\u0443\u043b\u0438\u0446\u044f",'
    ' "label_en": "Street",'
    ' "label_pl": "Ulica",'
    ' "label_tr": "Sokak",'
    ' "label_ar": "\u0627\u0644\u0634\u0627\u0631\u0639",'
    ' "type": "text", "required": False},\n'

    '            {"name": "leistungstraeger_house_number",'
    ' "label_de": "Hausnummer",'
    ' "label_uk": "\u041d\u043e\u043c\u0435\u0440 \u0431\u0443\u0434\u0438\u043d\u043a\u0443",'
    ' "label_en": "House number",'
    ' "label_pl": "Numer domu",'
    ' "label_tr": "Bina numaras\u0131",'
    ' "label_ar": "\u0631\u0642\u0645 \u0627\u0644\u0645\u0646\u0632\u0644",'
    ' "type": "text", "required": False},\n'

    '            {"name": "leistungstraeger_plz",'
    ' "label_de": "PLZ",'
    ' "label_uk": "\u041f\u043e\u0448\u0442\u043e\u0432\u0438\u0439 \u0456\u043d\u0434\u0435\u043a\u0441",'
    ' "label_en": "Postal code",'
    ' "label_pl": "Kod pocztowy",'
    ' "label_tr": "Posta kodu",'
    ' "label_ar": "\u0627\u0644\u0631\u0645\u0632 \u0627\u0644\u0628\u0631\u064a\u062f\u064a",'
    ' "type": "text", "required": False},\n'

    '            {"name": "leistungstraeger_city",'
    ' "label_de": "Ort",'
    ' "label_uk": "\u041c\u0456\u0441\u0442\u043e",'
    ' "label_en": "City",'
    ' "label_pl": "Miasto",'
    ' "label_tr": "\u015eehir",'
    ' "label_ar": "\u0627\u0644\u0645\u062f\u064a\u0646\u0629",'
    ' "type": "text", "required": False},\n'

    '            {"name": "leistungstraeger_von",'
    ' "label_de": "Von",'
    ' "label_uk": "\u0417",'
    ' "label_en": "From",'
    ' "label_pl": "Od",'
    ' "label_tr": "Ba\u015flang\u0131\u00e7",'
    ' "label_ar": "\u0645\u0646",'
    ' "type": "date", "required": False},\n'

    '            {"name": "leistungstraeger_bis",'
    ' "label_de": "Bis",'
    ' "label_uk": "\u0414\u043e",'
    ' "label_en": "To",'
    ' "label_pl": "Do",'
    ' "label_tr": "Biti\u015f",'
    ' "label_ar": "\u0625\u043b\u044f",'
    ' "type": "date", "required": False},\n'
)

if ANCHOR1 not in content:
    print("[ERROR] ANCHOR1 not found. Patch aborted.")
    sys.exit(1)
if content.count(ANCHOR1) > 1:
    print(f"[ERROR] ANCHOR1 appears {content.count(ANCHOR1)} times. Patch aborted.")
    sys.exit(1)

content = content.replace(ANCHOR1, FIELDS_1 + ANCHOR1, 1)
print("[patch] PATCH 1 applied (8 Leistungstraeger fields)")

# =============================================================================
# PATCH 2
# Insert krankenkasse_name + versicherungsnummer into BUERGERGELD_SCHEMA
# krankenversicherung section, after "has_health_insurance" field,
# before the section's closing "]},".
#
# Strategy: match the end of has_health_insurance options line
# ("Nein / Nicht versichert" ... }]},\n) then the section-close line (\s+]},\n).
# Insert new fields between the two.
# =============================================================================

ANCHOR2_RE = re.compile(
    r'("Nein / Nicht versichert"[^\n]*\}\]\},\n)'   # has_health_insurance last option + close
    r'(\s+\]\},\n)',                                  # krankenversicherung section close
    re.UNICODE,
)

FIELDS_2 = (
    '            {"name": "krankenkasse_name",'
    ' "label_de": "Name der Krankenkasse",'
    ' "label_uk": "\u041d\u0430\u0437\u0432\u0430 \u0441\u0442\u0440\u0430\u0445\u043e\u0432\u043e\u0457 \u043a\u0430\u0441\u0438",'
    ' "label_en": "Health insurance provider",'
    ' "label_pl": "Nazwa ubezpieczyciela",'
    ' "label_tr": "Sigorta kurumu",'
    ' "label_ar": "\u0634\u0631\u043a\u0435\u0020\u0430\u043b-\u0422\u0430\u02be\u043c\u0456\u043d",'
    ' "type": "text", "required": False},\n'

    '            {"name": "versicherungsnummer",'
    ' "label_de": "Versicherungsnummer",'
    ' "label_uk": "\u041d\u043e\u043c\u0435\u0440 \u0441\u0442\u0440\u0430\u0445\u043e\u0432\u043a\u0438",'
    ' "label_en": "Insurance number",'
    ' "label_pl": "Numer ubezpieczenia",'
    ' "label_tr": "Sigorta numaras\u0131",'
    ' "label_ar": "\u0631\u0642\u0645 \u0627\u0644\u062a\u0623\u0645\u064a\u0646",'
    ' "type": "text", "required": False},\n'
)

m2 = ANCHOR2_RE.search(content)
if not m2:
    print("[ERROR] ANCHOR2 pattern not found. Patch aborted.")
    sys.exit(1)

# Insert new fields after group 1 (has_health_insurance end), before group 2 (section close)
insert_pos2 = m2.end(1)
content = content[:insert_pos2] + FIELDS_2 + content[insert_pos2:]
print("[patch] PATCH 2 applied (krankenkasse_name + versicherungsnummer)")

# =============================================================================
# PATCH 3
# Append 10 entries to JOBCENTER_ACROFORM_MAPPING before its closing '}'.
#
# Anchor: the last real entry in the mapping followed by '}'.
# Exact text (verified from git HEAD):
#   '    "signature_date":         "dateUnterschriftPerson",\n}'
# =============================================================================

ANCHOR3_RE = re.compile(
    r'("signature_date"\s*:\s*"dateUnterschriftPerson",\s*\n)'
    r'(\})',
    re.UNICODE,
)

MAPPING_BLOCK = (
    '    # -- Andere Leistungen text fields (p03-p04, verified via fitz) ------\n'
    '    "leistungsart":              "txtfPersonLeistungsart",\n'
    '    "leistungstraeger_name":     "txtfLeistungstraegerName",\n'
    '    "leistungstraeger_street":   "txtfLeistungstraegerStr",\n'
    '    "leistungstraeger_house_number": "txtfLeistungstraegerHausnr",\n'
    '    "leistungstraeger_plz":      "txtfLeistungstraegerPlz",\n'
    '    "leistungstraeger_city":     "txtfLeistungstraegerOrt",\n'
    '    "leistungstraeger_von":      "datePersonZeitraumLeistungVon",\n'
    '    "leistungstraeger_bis":      "datePersonZeitraumLeistungBis",\n'
    '    # -- Krankenversicherung text fields (p06, verified via fitz) ---------\n'
    '    "krankenkasse_name":         "txtfKVName",\n'
    '    "versicherungsnummer":       "txtfKVNr",\n'
)

m3 = ANCHOR3_RE.search(content)
if not m3:
    print("[ERROR] ANCHOR3 pattern not found. Patch aborted.")
    sys.exit(1)

# Insert MAPPING_BLOCK between signature_date line (group 1) and closing } (group 2)
insert_pos3 = m3.end(1)
content = content[:insert_pos3] + MAPPING_BLOCK + content[insert_pos3:]
print("[patch] PATCH 3 applied (10 entries to JOBCENTER_ACROFORM_MAPPING)")

# =============================================================================
# Write
# =============================================================================
with open(TARGET, "w", encoding="utf-8") as fh:
    fh.write(content)
print(f"[patch] Written  : {TARGET}")

# =============================================================================
# Validate via live import
# =============================================================================
print("[patch] Validating runtime import...")
import importlib.util

spec = importlib.util.spec_from_file_location("_dc_patch_check", TARGET)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as exc:
    print(f"[FAIL] Import error: {exc}")
    shutil.copy2(BACKUP, TARGET)
    print(f"[patch] Restored from backup: {BACKUP}")
    sys.exit(1)

schema = mod.BUERGERGELD_SCHEMA
all_field_names = [
    f["name"]
    for sec in schema["sections"]
    for f in sec.get("fields", [])
]
mapping = mod.JOBCENTER_ACROFORM_MAPPING

EXPECTED_SCHEMA = [
    "leistungsart", "leistungstraeger_name", "leistungstraeger_street",
    "leistungstraeger_house_number", "leistungstraeger_plz", "leistungstraeger_city",
    "leistungstraeger_von", "leistungstraeger_bis",
    "krankenkasse_name", "versicherungsnummer",
]
EXPECTED_MAPPING = {
    "leistungsart":              "txtfPersonLeistungsart",
    "leistungstraeger_name":     "txtfLeistungstraegerName",
    "leistungstraeger_street":   "txtfLeistungstraegerStr",
    "leistungstraeger_house_number": "txtfLeistungstraegerHausnr",
    "leistungstraeger_plz":      "txtfLeistungstraegerPlz",
    "leistungstraeger_city":     "txtfLeistungstraegerOrt",
    "leistungstraeger_von":      "datePersonZeitraumLeistungVon",
    "leistungstraeger_bis":      "datePersonZeitraumLeistungBis",
    "krankenkasse_name":         "txtfKVName",
    "versicherungsnummer":       "txtfKVNr",
}

ok = True
print()
print("  Schema fields:")
for k in EXPECTED_SCHEMA:
    present = k in all_field_names
    if not present:
        ok = False
    print(f"    {'OK  ' if present else 'FAIL'} {k}")

print()
print("  Mapping entries:")
for k, expected_v in EXPECTED_MAPPING.items():
    actual_v = mapping.get(k)
    match = actual_v == expected_v
    if not match:
        ok = False
    print(f"    {'OK  ' if match else 'FAIL'} {k!r:40s} -> {actual_v!r}")

print()
if ok:
    print("[patch] ALL 20 CHECKS PASSED — patch successful.")
    print(f"[patch] Backup kept at : {BACKUP}")
    print("[patch] Next step      : supervisorctl restart civicassistbot")
else:
    print("[patch] CHECKS FAILED — restoring backup automatically.")
    shutil.copy2(BACKUP, TARGET)
    print(f"[patch] Restored from  : {BACKUP}")
    sys.exit(1)
