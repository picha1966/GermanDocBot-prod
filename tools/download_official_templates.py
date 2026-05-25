#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/download_official_templates.py

Downloads official German government AcroForm PDF templates into templates/.
Run once before first deployment, then re-run to update templates.

Usage:
    python tools/download_official_templates.py
    python tools/download_official_templates.py --doc anmeldung
    python tools/download_official_templates.py --check     # only verify existing files
"""

import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Known official PDF sources
# Source validity checked: Bundesdruckerei / Bundesagentur / Gemeinden
# ---------------------------------------------------------------------------
OFFICIAL_SOURCES = {
    # ── Existing forms (now with Bundesland-aware paths) ─────────────────────
    "anmeldung": {
        "filename": "anmeldung/default.pdf",
        "url": "https://allaboutberlin.com/documents/anmeldung-original.pdf",
        "description": "Anmeldung einer Wohnung (Bundesmeldegesetz §17 — standardized BMG form)",
        "authority": "Bürgeramt",
        "pages": 1,
        "has_acroform": True,
    },
    "kindergeld": {
        "filename": "kindergeld/default.pdf",
        "url": "https://www.arbeitsagentur.de/datei/kg1-antrag-kindergeld_ba036550.pdf",
        "description": "KG 1 — Antrag auf Kindergeld (Bundesagentur für Arbeit)",
        "authority": "Familienkasse",
        "pages": 4,
        "has_acroform": True,
    },
    "kindergeld_anlage": {
        "filename": "kindergeld_anlage/default.pdf",
        "url": "https://www.arbeitsagentur.de/datei/kg1-anlagekind_ba033765.pdf",
        "description": "KG 1-AnK — Anlage Kind (Bundesagentur für Arbeit)",
        "authority": "Familienkasse",
        "pages": 2,
        "has_acroform": True,
    },
    "wohnungsgeberbestaetigung": {
        "filename": "wohnungsgeberbestaetigung/default.pdf",
        "url": "https://www.dresden.de/media/pdf/einwohner/WGBest__Formular.pdf",
        "description": "Wohnungsgeberbestätigung gemäß §19 BMG (Dresden template — standardized)",
        "authority": "Wohnungsgeber",
        "pages": 1,
        "has_acroform": True,   # 21 AcroForm fields
    },
    "verpflichtungserklaerung": {
        "filename": "verpflichtungserklaerung/default.pdf",
        "url": "https://www.zollernalbkreis.de/site/LRA-ZAK-2017/get/documents_E-1725436053/lra_zak/LRA-ZAK-2018-Objekte/Amt/Zuwanderung%20und%20Integration/Formulare/SG%20421/Antrag%20Verpflichtungserkl%C3%A4rung%20%C2%A7%2068%20AufenthG.pdf",
        "description": "Verpflichtungserklärung gemäß §68 AufenthG (Zollernalbkreis — bundesweit anerkanntes Muster)",
        "authority": "Ausländerbehörde",
        "pages": 2,
        "has_acroform": True,   # 49 AcroForm fields
    },
    "beschaeftigungserklaerung": {
        "filename": "beschaeftigungserklaerung/berlin.pdf",
        "url": "https://www.berlin.de/einwanderung/_assets/stellenbeschreibung.pdf",
        "description": "Erklärung zum Beschäftigungsverhältnis / Stellenbeschreibung (Landesamt für Einwanderung Berlin)",
        "authority": "Landesamt für Einwanderung (LEA) Berlin",
        "pages": 5,
        "has_acroform": True,   # 69 AcroForm fields
    },
    "aufenthaltserlaubnis_antrag": {
        "filename": "aufenthaltserlaubnis_antrag/berlin.pdf",
        "url": "https://www.berlin.de/einwanderung/_assets/antrag-aufenthaltstitel-deutsch-engl-frz-ital.pdf",
        "description": "Antrag auf einen befristeten Aufenthaltstitel — Deutsch/Englisch/Französisch/Italienisch (LEA Berlin)",
        "authority": "Landesamt für Einwanderung (LEA) Berlin",
        "pages": 3,
        "has_acroform": False,  # flat PDF — german_form_builder used
    },
    "schulbescheinigung": {
        "filename": "schulbescheinigung/default.pdf",
        "url": "https://www.arbeitsagentur.de/datei/kg5a_ba031890.pdf",
        "description": "Schulbescheinigung für Kindergeld (KG 5a) — Bundesagentur für Arbeit / Familienkasse",
        "authority": "Familienkasse",
        "pages": 1,
        "has_acroform": True,   # XFA fields (not fillable via standard AcroForm API) → builder
    },
    "mietbescheinigung": {
        "filename": "mietbescheinigung/default.pdf",
        "url": "https://www.jobcenter-rhein-berg.de/fileadmin/Dokumente/Antr%C3%A4ge-Vordrucke/Geldleistungen/250320-mietbescheinigung-2025.pdf",
        "description": "Mietbescheinigung 2025 für Wohngeld / Bürgergeld (Jobcenter Rhein-Berg — bundesweit verwendetes Muster)",
        "authority": "Jobcenter / Wohngeldbehörde",
        "pages": 4,
        "has_acroform": True,   # 48 AcroForm fields
    },
    # ── New 8 forms added 2026-02 ────────────────────────────────────────────
    "abmeldung": {
        "filename": "abmeldung/berlin.pdf",
        "url": "https://www.berlin.de/formularverzeichnis/?formular=/labo/zentrale-einwohnerangelegenheiten/_assets/mdb-f402609-20151120_abmeldung.pdf",
        "description": "Abmeldung bei der Meldebehörde (Berlin, Bundesmeldegesetz §24)",
        "authority": "Bürgeramt Berlin",
        "pages": 1,
        "has_acroform": True,   # 58 AcroForm fields
    },
    "wbs": {
        "filename": "wbs/berlin.pdf",
        "url": "https://www.berlin.de/sen/sbw/_assets/service/formular-center/bereich-wohnen/bauwohn502.pdf",
        "description": "Antrag auf Wohnberechtigungsschein WBS §5 WoBindG / §27 WoFG (SenSBW Berlin, Stand 01.2026)",
        "authority": "Senatsverwaltung für Stadtentwicklung und Wohnen Berlin",
        "pages": 4,
        "has_acroform": True,   # 119 AcroForm fields
    },
    "elterngeld": {
        "filename": "elterngeld/berlin.pdf",
        "url": "https://www.berlin.de/jugendamt-pankow/dienste-und-leistungen/kindschaftsrecht/bundeselterngeld/230102-einheitlicher-elterngeldantrag-barrierefrei-aenderungsantrag-230427-formular-dsb.pdf",
        "description": "Einheitlicher Elterngeldantrag Berlin (Jugendamt Pankow, barrier-free)",
        "authority": "Jugendamt Berlin",
        "pages": 10,
        "has_acroform": True,   # 201 AcroForm fields
    },
    "kinderzuschlag": {
        "filename": "kinderzuschlag/default.pdf",
        "url": "https://www.arbeitsagentur.de/datei/kiz1-antrag_ba036540.pdf",
        "description": "KiZ 1 — Antrag auf Kinderzuschlag (Bundesagentur für Arbeit)",
        "authority": "Familienkasse / Bundesagentur für Arbeit",
        "pages": 6,
        "has_acroform": False,  # XFA form (74 fields) → german_form_builder fallback
    },
    "unterhaltsvorschuss": {
        "filename": "unterhaltsvorschuss/berlin.pdf",
        "url": "https://www.berlin.de/sen/jugend/familie-und-kinder/finanzielle-leistungen/unterhaltsvorschuss/antrag-uvg-anlage-2.pdf",
        "description": "Antrag auf Leistungen nach dem UVG (Unterhaltsvorschuss) — Berlin Senatsverwaltung",
        "authority": "Jugendamt Berlin",
        "pages": 11,
        "has_acroform": True,   # 293 AcroForm fields
    },
    "bafoeg": {
        "filename": "bafoeg/default.pdf",
        "url": "https://www.studentenwerk-potsdam.de/fileadmin/user_upload/Dateien/BAfoeG_und_Finanzen/Formulare/Formblatt_1_01.pdf",
        "description": "BAföG Formblatt 1 — Antrag auf Ausbildungsförderung (Stand 2025, bundesweit)",
        "authority": "Studentenwerk / BAföG-Ämter",
        "pages": 10,
        "has_acroform": True,   # 237 AcroForm fields
    },
    "verlaengerung_aufenthaltstitel": {
        "filename": "verlaengerung_aufenthaltstitel/berlin.pdf",
        "url": "https://www.berlin.de/einwanderung/_assets/antrag-aufenthaltstitel-deutsch-engl-frz-ital.pdf",
        "description": "Antrag auf Verlängerung des Aufenthaltstitels — LEA Berlin",
        "authority": "Landesamt für Einwanderung (LEA) Berlin",
        "pages": 3,
        "has_acroform": False,  # flat PDF → german_form_builder fallback
    },
    "niederlassungserlaubnis": {
        "filename": "niederlassungserlaubnis/berlin.pdf",
        "url": "https://www.berlin.de/einwanderung/_assets/antrag-aufenthaltstitel-deutsch-engl-frz-ital.pdf",
        "description": "Antrag auf Niederlassungserlaubnis (uses Aufenthaltstitel form) — LEA Berlin",
        "authority": "Landesamt für Einwanderung (LEA) Berlin",
        "pages": 3,
        "has_acroform": False,  # flat PDF → german_form_builder fallback
    },
}

# Docs without fillable AcroForm — generated by german_form_builder.py
GENERATED_DOCS = {
    "ummeldung":                    "Same form as Anmeldung — reuses anmeldung/default.pdf",
    "wohngeld":                     "Varies by Bundesland — generated by german_form_builder",
    "buergergeld":                  "Submitted via jobcenter.digital — generated by german_form_builder",
    "aufenthaltstitel":             "Varies by Ausländerbehörde — generated by german_form_builder",
    "aufenthaltserlaubnis_antrag":  "Flat PDF (no AcroForm) — generated by german_form_builder",
    "schulbescheinigung":           "XFA-only PDF — generated by german_form_builder",
    "kinderzuschlag":               "XFA-only PDF (74 fields, not fillable) — generated by german_form_builder",
    "verlaengerung_aufenthaltstitel": "Flat PDF (no AcroForm) — generated by german_form_builder",
    "niederlassungserlaubnis":      "Flat PDF (no AcroForm) — generated by german_form_builder",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, timeout: int = 30) -> bool:
    """Download url → dest. Returns True on success."""
    print(f"  ↓ {url}")
    try:
        headers = {"User-Agent": "GermanDocBot/1.0 (template downloader)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 1024:
            print(f"  ✗ Downloaded file too small ({len(data)} bytes) — may be error page")
            return False
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  ✓ Saved: {dest.name} ({len(data) // 1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def _check_acroform(path: Path):
    """Check if PDF has fillable AcroForm fields. Returns (has_form, field_count)."""
    try:
        import fitz
        doc = fitz.open(str(path))
        field_count = sum(
            1 for page in doc for w in (page.widgets() or [])
            if getattr(w, "field_name", None)
        )
        doc.close()
        return field_count > 0, field_count
    except Exception:
        return False, 0


def cmd_download(doc_filter: str = None):
    """Download all (or a specific) official template."""
    success = 0
    skipped = 0
    failed = 0

    for doc_key, info in OFFICIAL_SOURCES.items():
        if doc_filter and doc_key != doc_filter:
            continue
        dest = TEMPLATES_DIR / info["filename"]
        print(f"\n[{doc_key}] {info['description']}")

        if dest.exists():
            size_kb = dest.stat().st_size // 1024
            print(f"  ℹ  Already exists: {dest.name} ({size_kb} KB) — skipping")
            skipped += 1
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        ok = _download(info["url"], dest)
        if ok:
            success += 1
            # Report AcroForm status
            try:
                has_form, nfields = _check_acroform(dest)
                if has_form:
                    print(f"  ✓ AcroForm: {nfields} fillable field(s) found")
                else:
                    print("  ℹ  No AcroForm fields — overlay mode will be used")
            except Exception:
                pass
        else:
            failed += 1

    print(f"\n{'─'*50}")
    print(f"Downloaded: {success}  Skipped: {skipped}  Failed: {failed}")

    if failed:
        print("\n⚠️  Some downloads failed. Check URLs or download manually.")
        print("   Docs without templates will use german_form_builder (auto-generated).")

    print("\nDocs without official templates (auto-generated):")
    for dk, reason in GENERATED_DOCS.items():
        print(f"  • {dk}: {reason}")


LEGACY_TEMPLATES_DIR = ROOT / "backend" / "templates"

# Mirrors _LEGACY_CATEGORY_MAP in document_config.py (kept in sync manually)
_LEGACY_CATEGORY_MAP = {
    "anmeldung":         ("housing", ["anmeldung"]),
    "ummeldung":         ("housing", ["anmeldung"]),
    "abmeldung":         ("housing", ["abmeldung"]),
    "kindergeld":        ("family",  ["kg1-antrag-kindergeld_ba036550", "kg1-antrag-kindergeld", "kindergeld"]),
    "kindergeld_anlage": ("family",  ["kg1-anlagekind_ba033765", "kg1-anlagekind", "kindergeld_anlage"]),
    "kinderzuschlag":    ("family",  ["kiz_main", "kiz", "kinderzuschlag"]),
    "wohngeld":          ("finance", ["wohngeld_main", "wohngeld"]),
    "buergergeld":       ("finance", ["jobcenter_main_2025", "jobcenter_main", "jobcenter"]),
    "jobcenter":         ("finance", ["jobcenter_main_2025", "jobcenter_main", "jobcenter"]),
    "ebk":               ("work",    ["Antrag_EBK", "antrag_ebk", "ebk"]),
}


def _resolve_legacy_path(doc_key: str) -> Path | None:
    """Resolve a doc_key to a file under backend/templates/{category}/."""
    entry = _LEGACY_CATEGORY_MAP.get(doc_key)
    if not entry:
        return None
    category, stems = entry
    cat_dir = LEGACY_TEMPLATES_DIR / category
    if not cat_dir.is_dir():
        return None
    for stem in stems:
        exact = cat_dir / f"{stem}.pdf"
        if exact.exists():
            return exact
    cat_lower = {p.stem.lower(): p for p in cat_dir.glob("*.pdf")}
    for stem in stems:
        hit = cat_lower.get(stem.lower())
        if hit:
            return hit
    return None


def cmd_check():
    """Verify which templates exist — checks both new doc_type and legacy category structures."""
    all_doc_keys = sorted(set(list(OFFICIAL_SOURCES.keys()) + list(_LEGACY_CATEGORY_MAP.keys())))

    print(f"Primary   templates: {TEMPLATES_DIR}")
    print(f"Legacy    templates: {LEGACY_TEMPLATES_DIR}")
    print()

    # ── Section 1: new doc_type structure ────────────────────────────────
    print("┌─ New structure: templates/{doc_type}/{bundesland|default}.pdf")
    new_found = 0
    for doc_key, info in OFFICIAL_SOURCES.items():
        dest = TEMPLATES_DIR / info["filename"]
        if dest.exists():
            size_kb = dest.stat().st_size // 1024
            try:
                has_form, nfields = _check_acroform(dest)
                acro = f"AcroForm: {nfields} fields" if has_form else "no AcroForm"
            except Exception:
                acro = "fitz not available"
            print(f"│  ✓  {doc_key:<32} {size_kb:>5} KB  {acro}")
            new_found += 1
        else:
            # Check if ANY file exists in the subdirectory
            subdir = TEMPLATES_DIR / doc_key
            variants = list(subdir.glob("*.pdf")) if subdir.is_dir() else []
            if variants:
                label = ", ".join(v.name for v in sorted(variants)[:3])
                print(f"│  ✓  {doc_key:<32} (variants: {label})")
                new_found += 1
            else:
                print(f"│  ✗  {doc_key:<32} MISSING — run without --check to download")
    print(f"└─ {new_found}/{len(OFFICIAL_SOURCES)} present\n")

    # ── Section 2: legacy category structure ────────────────────────────
    print("┌─ Legacy structure: backend/templates/{category}/{stem}.pdf")
    legacy_total = 0
    legacy_found = 0
    for doc_key in sorted(_LEGACY_CATEGORY_MAP):
        legacy_total += 1
        path = _resolve_legacy_path(doc_key)
        if path:
            legacy_found += 1
            size_kb = path.stat().st_size // 1024
            try:
                has_form, nfields = _check_acroform(path)
                acro = f"AcroForm: {nfields} fields" if has_form else "no AcroForm (flat)"
            except Exception:
                acro = "fitz not available"
            rel = path.relative_to(ROOT)
            print(f"│  ✓  {doc_key:<32} {size_kb:>5} KB  {acro:<30}  ← {rel}")
        else:
            entry = _LEGACY_CATEGORY_MAP[doc_key]
            print(f"│  ✗  {doc_key:<32} NOT FOUND in backend/templates/{entry[0]}/")
    print(f"└─ {legacy_found}/{legacy_total} present\n")

    # ── Section 3: resolution summary ───────────────────────────────────
    print("┌─ Effective resolution (new → legacy → builder)")
    resolved_new = resolved_legacy = resolved_builder = 0
    for doc_key in sorted(set(list(OFFICIAL_SOURCES.keys()) + list(_LEGACY_CATEGORY_MAP.keys()) + list(GENERATED_DOCS.keys()))):
        # Try new structure first
        subdir = TEMPLATES_DIR / doc_key
        new_hits = list(subdir.glob("*.pdf")) if subdir.is_dir() else []
        if new_hits:
            best = sorted(new_hits, key=lambda p: p.name)[0]
            print(f"│  {doc_key:<32} [new]     templates/{doc_key}/{best.name}")
            resolved_new += 1
            continue
        leg = _resolve_legacy_path(doc_key)
        if leg:
            print(f"│  {doc_key:<32} [legacy]  {leg.relative_to(ROOT)}".replace("\\", "/"))
            resolved_legacy += 1
            continue
        print(f"│  {doc_key:<32} [builder] german_form_builder")
        resolved_builder += 1

    # Discovered PDFs count
    all_pdfs_new = list(TEMPLATES_DIR.rglob("*.pdf")) if TEMPLATES_DIR.exists() else []
    all_pdfs_leg = list(LEGACY_TEMPLATES_DIR.rglob("*.pdf")) if LEGACY_TEMPLATES_DIR.exists() else []
    print(f"└─ new={resolved_new}  legacy={resolved_legacy}  builder={resolved_builder}")
    print(f"\nDiscovered PDFs: {len(all_pdfs_new)} in templates/  +  {len(all_pdfs_leg)} in backend/templates/  =  {len(all_pdfs_new)+len(all_pdfs_leg)} total")

    print("\nAuto-generated docs (intentionally no template):")
    for dk, reason in GENERATED_DOCS.items():
        print(f"  {dk:<32} {reason}")


def cmd_extract_fields(doc_key: str):
    """Print AcroForm field names for a downloaded template."""
    info = OFFICIAL_SOURCES.get(doc_key)
    if not info:
        print(f"Unknown doc_key: {doc_key}")
        return
    dest = TEMPLATES_DIR / info["filename"]
    if not dest.exists():
        print(f"Template not found: {dest}  (run --download first)")
        return
    try:
        import fitz
        doc = fitz.open(str(dest))
        seen = set()
        print(f"\nAcroForm fields in {dest.name}:")
        print("-" * 60)
        for page_no, page in enumerate(doc):
            for w in (page.widgets() or []):
                name = getattr(w, "field_name", None)
                if not name or name in seen:
                    continue
                seen.add(name)
                wtype = {1: "button", 2: "checkbox", 3: "radio",
                         4: "text", 5: "listbox", 6: "combo"}.get(
                    getattr(w, "field_type", 0), "?")
                print(f"  p{page_no+1}  {name!r:<40} ({wtype})")
        doc.close()
        print(f"\nTotal: {len(seen)} unique fields")
    except ImportError:
        print("PyMuPDF (fitz) required: pip install pymupdf")


def main():
    parser = argparse.ArgumentParser(description="Download/verify official German PDF templates")
    parser.add_argument("--download", action="store_true", help="Download missing templates")
    parser.add_argument("--check",    action="store_true", help="Check template status")
    parser.add_argument("--fields",   metavar="DOC",       help="Extract AcroForm fields from template")
    parser.add_argument("--doc",      metavar="DOC",       help="Limit to specific doc type")
    args = parser.parse_args()

    if args.fields:
        cmd_extract_fields(args.fields)
    elif args.check:
        cmd_check()
    else:
        # Default: download
        cmd_download(doc_filter=args.doc)
        print("\nTip: run with --check to verify status after download")
        print("Tip: run with --fields <doc_key> to inspect AcroForm field names")


if __name__ == "__main__":
    # Fix Windows console encoding
    import io
    if getattr(sys.stdout, "buffer", None):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
