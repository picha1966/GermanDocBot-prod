# -*- coding: utf-8 -*-
"""
backend/form_builder.py  (renamed from german_form_builder.py)

Generates professional government-style PDF documents using ReportLab.
Supports Germany now; Spain/France/Netherlands to be added via _DOC_META + _DOC_SECTIONS.
Covers all 7 MVP document types.  No external templates needed — pure code.

Pipeline position (in pdf_generator.py):
  create_final_pdf()
      └── has_template(doc_type)?
          ├── YES → AcroForm fill (existing, e.g. anmeldung.pdf)
          └── NO  → build_german_form()   ← THIS MODULE
"""

import logging
import math
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.colors import HexColor, black, grey, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# _normalize_nationality: imported lazily to avoid circular import
# (normalize.py imports _normalize_city_name from this module).
try:
    from backend.utils.normalize import _normalize_nationality as _norm_nationality
except ImportError:
    _norm_nationality = None

# ---------------------------------------------------------------------------
# RTL support — canonical engine: arabic_reshaper + python-bidi
# (rtl_support.py is DEPRECATED — do not import from it)
# ---------------------------------------------------------------------------
try:
    import arabic_reshaper as _arabic_reshaper
    import bidi.algorithm as _bidi_algorithm

    _HAS_RTL = True
except ImportError:
    _arabic_reshaper = None
    _bidi_algorithm = None
    _HAS_RTL = False


def _prepare_rtl_text(text: str, lang: str) -> str:
    """Apply Arabic reshaping + bidi reorder for lang='ar'. Other langs: unchanged."""
    if not text or lang != "ar" or not _HAS_RTL:
        return text
    try:
        return _bidi_algorithm.get_display(_arabic_reshaper.reshape(text))
    except Exception:
        return text


# ---------------------------------------------------------------------------
# Font registration — DejaVuSans for full Unicode (Cyrillic, Latin, German)
# Must run once at module load. ReportLab pdfmetrics is a global singleton.
# ---------------------------------------------------------------------------
def _register_builder_fonts() -> None:
    """Register DejaVuSans (regular + bold) for ReportLab. Safe to call multiple times."""
    try:
        if "DejaVuSans" in pdfmetrics.getRegisteredFontNames():
            return
        _font_dir = Path(__file__).parent.parent / "fonts"
        _regular = _font_dir / "DejaVuSans.ttf"
        _bold = _font_dir / "DejaVuSans-Bold.ttf"
        if _regular.exists():
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(_regular)))
        if _bold.exists():
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(_bold)))
    except Exception as _fe:
        logger.warning(
            "german_form_builder: font registration failed: %s — falling back to Helvetica",
            _fe,
        )


_register_builder_fonts()

# ---------------------------------------------------------------------------
# Constants — German government visual style
# ---------------------------------------------------------------------------
_BLUE_HEADER = HexColor("#003366")  # Bundesrepublik dark blue
_BLUE_LIGHT = HexColor("#e8eef5")  # Section background
_GREY_LINE = HexColor("#aaaaaa")  # Separator lines
_GREY_LABEL = HexColor("#555555")  # Field label text
_BLACK = HexColor("#111111")
_RED_STAMP = HexColor("#cc0000")  # Preview stamp

_PAGE_W, _PAGE_H = A4
_MARGIN = 18 * mm
_SERVICE_DOMAIN = "termin-assist.de"  # single source of truth for footer/branding
_COL_LABEL = 62 * mm  # label column width
_COL_VALUE = _PAGE_W - 2 * _MARGIN - _COL_LABEL
_TEXT_WIDTH = _PAGE_W - 2 * _MARGIN

# Official German authority → form title mapping
_DOC_META: Dict[str, Tuple[str, str, str]] = {
    # key: (form_title, legal_basis, authority)
    "anmeldung": (
        "Anmeldung einer Wohnung",
        "§ 17 Bundesmeldegesetz (BMG)",
        "Bürgeramt / Einwohnermeldeamt",
    ),
    "ummeldung": (
        "Ummeldung / Änderung der Anschrift",
        "§ 17 Bundesmeldegesetz (BMG)",
        "Bürgeramt / Einwohnermeldeamt",
    ),
    "wohnungsgeberbestaetigung": (
        "Wohnungsgeberbestätigung",
        "§ 19 Bundesmeldegesetz (BMG)",
        "Wohnungsgeber",
    ),
    "kindergeld": ("Antrag auf Kindergeld — KG 1", "§ 62 ff. EStG", "Familienkasse"),
    "wohngeld": ("Antrag auf Wohngeld", "§ 22 Wohngeldgesetz (WoGG)", "Wohngeldstelle"),
    "buergergeld": ("Antrag auf Bürgergeld", "§ 37 SGB II", "Jobcenter"),
    "aufenthaltstitel": (
        "Antrag auf Erteilung / Verlängerung\neines Aufenthaltstitels",
        "§ 81 AufenthG",
        "Ausländerbehörde",
    ),
    # ── New doc types (fallback builder for flat/XFA PDFs) ───────────────────
    "verpflichtungserklaerung": (
        "Verpflichtungserklärung gemäß §68 AufenthG",
        "§ 68 AufenthG",
        "Ausländerbehörde",
    ),
    "beschaeftigungserklaerung": (
        "Erklärung zum Beschäftigungsverhältnis\n(Stellenbeschreibung)",
        "§§ 18, 18a, 18b AufenthG",
        "Landesamt für Einwanderung",
    ),
    "aufenthaltserlaubnis_antrag": (
        "Antrag auf Erteilung eines\nbefristeten Aufenthaltstitels",
        "§ 81 AufenthG",
        "Ausländerbehörde",
    ),
    "schulbescheinigung": (
        "Schulbescheinigung für Kindergeld — KG 5a",
        "§ 63 Abs. 1 EStG",
        "Familienkasse",
    ),
    "mietbescheinigung": (
        "Mietbescheinigung",
        "§ 23 Abs. 3 WoGG",
        "Jobcenter / Wohngeldbehörde",
    ),
    # ── 7 doc_types added to cover all menu_structure.py entries ────────────
    "abmeldung": (
        "Abmeldung einer Wohnung",
        "§ 17 Bundesmeldegesetz (BMG)",
        "Bürgeramt / Einwohnermeldeamt",
    ),
    "elterngeld": (
        "Antrag auf Elterngeld",
        "§§ 1, 9 BEEG",
        "Elterngeldstelle / Familienkasse",
    ),
    "unterhaltsvorschuss": (
        "Antrag auf Unterhaltsvorschuss",
        "§§ 1 ff. UhVorschG",
        "Jugendamt",
    ),
    "kinderzuschlag": ("Antrag auf Kinderzuschlag — KiZ", "§ 6a BKGG", "Familienkasse"),
    "bafoeg": (
        "Antrag auf Ausbildungsförderung — BAföG",
        "§§ 1 ff. BAföG",
        "Amt für Ausbildungsförderung (BAföG-Amt)",
    ),
    "wbs": (
        "Antrag auf Wohnberechtigungsschein",
        "§ 5 WoBindG",
        "Wohnungsamt / Bezirksamt",
    ),
    "ebk": (
        "Erklärung zur Bekämpfung von Kinderarmut — EBK",
        "§ 2 UhVorschG",
        "Jobcenter",
    ),
    "verlaengerung_aufenthaltstitel": (
        "Antrag auf Verlängerung eines Aufenthaltstitels",
        "§ 81 AufenthG",
        "Ausländerbehörde",
    ),
}

# Field sections per document type.
# Format: [ (section_title_de, [ (field_key, label_de), ... ]) ]
_DOC_SECTIONS: Dict[str, List[Tuple[str, List[Tuple[str, str]]]]] = {
    "anmeldung": [
        (
            "1. Neue Wohnung",
            [
                ("wohnungstyp", "Die neue Wohnung ist"),
                ("move_in_date", "Tag des Einzugs"),
                ("plz", "Postleitzahl"),
                ("city", "Gemeinde / Ortsteil"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("apartment_number", "Wohnungsnummer"),
                ("gemeindekennzahl", "Gemeindekennzahl"),
                ("weitere_wohnungen", "Weitere Wohnungen in Deutschland"),
            ],
        ),
        (
            "2. Bisherige Wohnung",
            [
                ("has_bisherige_wohnung", "Bisherige Wohnung vorhanden"),
                # The following fields are only shown when has_bisherige_wohnung == "Ja"
                # (filtered at render time — see _get_preview_fields_for_section)
                ("move_out_date", "Tag des Auszugs"),
                ("previous_strasse", "Straße (bisherige Wohnung)"),
                ("previous_hausnummer", "Hausnummer (bisherige Wohnung)"),
                ("previous_plz", "PLZ (bisherige Wohnung)"),
                ("previous_ort", "Ort (bisherige Wohnung)"),
                ("bisherige_beibehalten", "Bisherige Wohnung beibehalten"),
                ("bisherige_wohnungstyp", "Art der bisherigen Wohnung"),
                ("zuzug_aus_ausland", "Zuzug aus dem Ausland"),
                ("zuzug_staat", "Staat (Ausland)"),
            ],
        ),
        (
            "3. Angaben zur Person 1",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vornamen"),
                ("birth_name", "Geburtsname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort / -land"),
                ("nationality", "Staatsangehörigkeit"),
                ("gender", "Geschlecht"),
                ("familienstand", "Familienstand"),
                ("eheschliessung_ort_datum", "Ort, Datum der Eheschließung"),
                ("religion", "Religionsgesellschaft"),
                ("passname", "Passname"),
                ("ordens_kuenstlername", "Ordens-/Künstlername"),
            ],
        ),
        (
            "4. Angaben zur Person 2 (Ehepartner/in)",
            [
                ("person2_last_name", "Familienname"),
                ("person2_first_name", "Vornamen"),
                ("person2_birth_name", "Geburtsname"),
                ("person2_birth_date", "Geburtsdatum"),
                ("person2_birth_place", "Geburtsort / -land"),
                ("person2_nationality", "Staatsangehörigkeit"),
                ("person2_gender", "Geschlecht"),
                ("person2_religion", "Religionsgesellschaft"),
                ("person2_ordens_kuenstlername", "Ordens-/Künstlername"),
            ],
        ),
        (
            "5. Ausweisdokument",
            [
                ("dokumentenart", "Art des Dokuments (PA/RP/KP)"),
                ("seriennummer", "Seriennummer / Dokumentennummer"),
                ("ausstellungsbehoerde", "Ausstellungsbehörde"),
                ("ausstellungsdatum", "Ausstellungsdatum"),
                ("gueltig_bis", "Gültig bis"),
            ],
        ),
        (
            "6. Wohnungsgeber",
            [
                ("landlord_name", "Name des Wohnungsgebers"),
                ("landlord_street", "Straße des Wohnungsgebers"),
                ("landlord_house_number", "Hausnummer des Wohnungsgebers"),
                ("landlord_plz", "PLZ des Wohnungsgebers"),
                ("landlord_city", "Ort des Wohnungsgebers"),
                ("landlord_address", "Anschrift des Wohnungsgebers"),  # legacy fallback
            ],
        ),
        (
            "7. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "ummeldung": [
        (
            "1. Neue Wohnung",
            [
                ("move_in_date", "Tag des Einzugs"),
                ("postal_code", "Postleitzahl"),
                ("city", "Gemeinde / Ortsteil"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("apartment_number", "Wohnungsnummer"),
            ],
        ),
        (
            "2. Bisherige Wohnung",
            [
                ("previous_strasse", "Straße (bisherige Wohnung)"),
                ("previous_hausnummer", "Hausnummer (bisherige Wohnung)"),
                ("previous_plz", "Postleitzahl (bisherige Wohnung)"),
                ("previous_ort", "Ort (bisherige Wohnung)"),
                ("move_out_date", "Tag des Auszugs"),
            ],
        ),
        (
            "3. Person 1",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vornamen"),
                ("birth_date", "Geburtsdatum"),
                ("birth_name", "Geburtsname"),
                ("birth_place", "Geburtsort"),
                ("nationality", "Staatsangehörigkeit"),
            ],
        ),
        (
            "4. Person 2",
            [
                ("person2_last_name", "Familienname"),
                ("person2_first_name", "Vornamen"),
                ("person2_birth_date", "Geburtsdatum"),
                ("person2_birth_name", "Geburtsname"),
                ("person2_birth_place", "Geburtsort"),
                ("person2_nationality", "Staatsangehörigkeit"),
            ],
        ),
        (
            "5. Person 3",
            [
                ("person3_last_name", "Familienname"),
                ("person3_first_name", "Vornamen"),
                ("person3_birth_date", "Geburtsdatum"),
                ("person3_birth_name", "Geburtsname"),
                ("person3_birth_place", "Geburtsort"),
                ("person3_nationality", "Staatsangehörigkeit"),
            ],
        ),
        (
            "6. Person 4",
            [
                ("person4_last_name", "Familienname"),
                ("person4_first_name", "Vornamen"),
                ("person4_birth_date", "Geburtsdatum"),
                ("person4_birth_name", "Geburtsname"),
                ("person4_birth_place", "Geburtsort"),
                ("person4_nationality", "Staatsangehörigkeit"),
            ],
        ),
        (
            "7. Person 5",
            [
                ("person5_last_name", "Familienname"),
                ("person5_first_name", "Vornamen"),
                ("person5_birth_date", "Geburtsdatum"),
                ("person5_birth_name", "Geburtsname"),
                ("person5_birth_place", "Geburtsort"),
                ("person5_nationality", "Staatsangehörigkeit"),
            ],
        ),
        (
            "8. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "wohnungsgeberbestaetigung": [
        (
            "1. Angaben zum Wohnungsgeber",
            [
                ("landlord_name", "Name des Wohnungsgebers"),
                ("landlord_address", "Anschrift des Wohnungsgebers"),
            ],
        ),
        (
            "2. Wohnobjekt",
            [
                ("postal_code", "Postleitzahl"),
                ("city", "Ort"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("apartment_number", "Wohnungsnummer"),
            ],
        ),
        (
            "3. Einziehende Person(en)",
            [
                ("last_name", "Familienname (Person 1)"),
                ("first_name", "Vorname (Person 1)"),
                ("birth_date", "Geburtsdatum (Person 1)"),
                ("wgb_p2_last_name", "Familienname (Person 2)"),
                ("wgb_p2_first_name", "Vorname (Person 2)"),
                ("wgb_p2_birth_date", "Geburtsdatum (Person 2)"),
                ("wgb_p3_last_name", "Familienname (Person 3)"),
                ("wgb_p3_first_name", "Vorname (Person 3)"),
                ("wgb_p3_birth_date", "Geburtsdatum (Person 3)"),
                ("wgb_p4_last_name", "Familienname (Person 4)"),
                ("wgb_p4_first_name", "Vorname (Person 4)"),
                ("wgb_p4_birth_date", "Geburtsdatum (Person 4)"),
                ("wgb_p5_last_name", "Familienname (Person 5)"),
                ("wgb_p5_first_name", "Vorname (Person 5)"),
                ("wgb_p5_birth_date", "Geburtsdatum (Person 5)"),
                ("wgb_p6_last_name", "Familienname (Person 6)"),
                ("wgb_p6_first_name", "Vorname (Person 6)"),
                ("wgb_p6_birth_date", "Geburtsdatum (Person 6)"),
            ],
        ),
        (
            "4. Einzugsdatum",
            [
                ("move_in_date", "Tag des Einzugs"),
            ],
        ),
        (
            "5. Eigentümer der Wohnung",
            [
                ("wgb_is_not_eigentuemer", "Wohnungsgeber ist nicht Eigentümer"),
                ("wgb_owner_name", "Name des Eigentümers"),
                ("wgb_owner_address", "Adresse des Eigentümers"),
            ],
        ),
        (
            "6. Erklärung / Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum der Unterzeichnung"),
            ],
        ),
    ],
    "kindergeld": [
        (
            "1. Antragsteller",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_name", "ggf. Geburtsname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort / -land"),
                ("street", "Straße / Hausnummer"),
                ("postal_code", "PLZ"),
                ("city", "Wohnort"),
                ("nationality", "Staatsangehörigkeit"),
                ("gender", "Geschlecht"),
                ("familienstand", "Familienstand"),
                ("tax_id", "Steueridentifikationsnummer"),
            ],
        ),
        (
            "2. Partner / Ehepartner",
            [
                ("partner_last_name", "Familienname Partner/in"),
                ("partner_first_name", "Vorname Partner/in"),
                ("partner_birth_date", "Geburtsdatum Partner/in"),
                ("partner_nationality", "Staatsangehörigkeit Partner/in"),
            ],
        ),
        (
            "3. Kind",
            [
                ("child_last_name", "Familienname des Kindes"),
                ("child_first_name", "Vorname des Kindes"),
                ("child_birth_date", "Geburtsdatum des Kindes"),
                ("child_birth_place", "Geburtsort des Kindes"),
                ("child_nationality", "Staatsangehörigkeit des Kindes"),
            ],
        ),
        (
            "4. Bankverbindung",
            [
                ("iban", "IBAN"),
                ("bic", "BIC"),
                ("bank_name", "Name der Bank / Kreditinstitut"),
                ("account_holder", "Kontoinhaber"),
            ],
        ),
        (
            "5. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "wohngeld": [
        # ── Abschnitt 1: Wohngeldberechtigte Person ──────────────────────────
        # Official form §1 — Personalien der antragstellenden Person
        (
            "1  Wohngeldberechtigte Person (Antragstellerin / Antragsteller)",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("gender", "Geschlecht"),
                ("birth_name", "ggf. Geburtsname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort"),
                ("nationality", "Staatsangehörigkeit"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("apartment_number", "ggf. Wohnungsnummer"),
                ("postal_code", "Postleitzahl"),
                ("city", "Ort"),
                ("phone", "Telefonnummer (freiwillige Angabe)"),
                ("email", "E-Mail-Adresse (freiwillige Angabe)"),
                ("family_status", "Familienstand"),
                (
                    "occupation",
                    "Derzeit ausgeübte Tätigkeit (z. B. Arbeit, Rente, ALG)",
                ),
            ],
        ),
        # ── Abschnitt 3: Wohnraum ────────────────────────────────────────────
        # Official form §3 — Wohnraum, für den Wohngeld beantragt wird
        (
            "3  Wohnraum, für den Wohngeld beantragt wird",
            [
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("apartment_number", "ggf. Wohnungsnummer"),
                ("postal_code", "Postleitzahl"),
                ("city", "Ort"),
            ],
        ),
        # ── Abschnitt 4: Weitere Haushaltsmitglieder ─────────────────────────
        # Official form §4 — Zusammensetzung des Haushalts
        (
            "4  Weitere Haushaltsmitglieder (Zusammensetzung des Haushalts)",
            [
                (
                    "household_members",
                    "Gesamtzahl der zum Haushalt gehörenden Personen",
                ),
            ],
        ),
        # ── Abschnitt 13: Angaben über das Einkommen ─────────────────────────
        # Official form §13 — Einkünfte (Nettoeinkommen, Rente, ALG, sonstige Einnahmen)
        (
            "13  Angaben über das Einkommen",
            [
                (
                    "income_source",
                    "Art der Einnahmen (z. B. Arbeitsentgelt, Rente, ALG II)",
                ),
                ("monthly_income", "Höhe der Einnahmen monatlich (brutto, €)"),
            ],
        ),
        # ── Abschnitt 22: Nutzungsart des Wohnraums ──────────────────────────
        # Official form §22 — Handelt es sich um Eigentum oder Miete?
        (
            "22  Nutzungsart des Wohnraums",
            [
                ("dwelling_type", "Nutzungsart (Mietwohnung / Eigentum)"),
            ],
        ),
        # ── Abschnitt 24: Gesamtfläche des Wohnraums ─────────────────────────
        # Official form §24 — Wohnfläche in m²
        (
            "24  Gesamtfläche des Wohnraums",
            [
                ("living_space_sqm", "Gesamtfläche (m²)"),
            ],
        ),
        # ── Abschnitt 25: Miete / Nutzungsentgelt ────────────────────────────
        # Official form §25 — Monatliche Kosten für den Wohnraum
        (
            "25  Miete / Nutzungsentgelt (monatlich)",
            [
                ("monthly_rent", "Monatliche Kaltmiete / Grundmiete (€)"),
                ("heating_costs", "davon: Kosten für Heizung und Warmwasser (€)"),
                ("additional_costs", "davon: Betriebskosten / Nebenkosten (€)"),
            ],
        ),
        # ── Abschnitt 32: Auszahlung des Wohngeldes ──────────────────────────
        # Official form §32 — Bankverbindung für die Auszahlung
        (
            "32  Auszahlung des Wohngeldes (Bankverbindung)",
            [
                ("iban", "IBAN"),
                ("bic", "BIC"),
                ("bank_name", "Name des Kreditinstituts"),
            ],
        ),
        # ── Erklärung / Unterschrift ──────────────────────────────────────────
        # Official form — Datenschutz, Vollständigkeit, Unterschrift
        (
            "Erklärung / Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "buergergeld": [
        (
            "1. Antragsteller",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort"),
                ("nationality", "Staatsangehörigkeit"),
                ("street", "Straße / Hausnummer"),
                ("postal_code", "PLZ"),
                ("city", "Ort"),
            ],
        ),
        (
            "2. Haushalt",
            [
                ("household_members", "Anzahl der Haushaltsmitglieder"),
                ("family_status", "Familienstand"),
            ],
        ),
        (
            "3. Wohnkosten",
            [
                ("monthly_rent", "Kaltmiete (€)"),
                ("heating_costs", "Heizkosten (€)"),
                ("additional_costs", "Nebenkosten (€)"),
            ],
        ),
        (
            "4. Einkommen",
            [
                ("employment_status", "Beschäftigungsstatus"),
                ("monthly_income", "Monatliches Nettoeinkommen (€)"),
                ("other_income", "Sonstige Einnahmen (€)"),
            ],
        ),
        (
            "5. Bankverbindung",
            [
                ("iban", "IBAN"),
                ("bank_name", "Bank"),
            ],
        ),
        (
            "6. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "aufenthaltstitel": [
        (
            "1. Personalien",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname(n)"),
                ("birth_name", "Geburtsname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort / -land"),
                ("nationality", "Staatsangehörigkeit"),
                ("gender", "Geschlecht"),
            ],
        ),
        (
            "2. Reisedokument",
            [
                ("dokumentenart", "Dokumentenart"),
                ("seriennummer", "Dokumentennummer"),
                ("ausstellungsbehoerde", "Ausstellungsbehörde / -staat"),
                ("ausstellungsdatum", "Ausstellungsdatum"),
                ("gueltig_bis", "Gültig bis"),
            ],
        ),
        (
            "3. Aktuelle Adresse in Deutschland",
            [
                ("postal_code", "Postleitzahl"),
                ("city", "Ort"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
            ],
        ),
        (
            "4. Aufenthalt / Zweck",
            [
                ("residence_purpose", "Aufenthaltszweck"),
                ("visa_type", "Aktueller Aufenthaltsstatus"),
                ("entry_date", "Einreisedatum"),
            ],
        ),
        (
            "5. Beschäftigung",
            [
                ("employer_name", "Arbeitgeber"),
                ("occupation", "Beruf / Tätigkeit"),
                ("employment_start", "Beschäftigt seit"),
            ],
        ),
        (
            "6. Kontaktdaten",
            [
                ("phone", "Telefonnummer"),
                ("email", "E-Mail-Adresse"),
            ],
        ),
        (
            "7. Familienstand",
            [
                ("familienstand", "Familienstand"),
                ("partner_last_name", "Familienname Ehegatte / Lebenspartner"),
                ("partner_first_name", "Vorname Ehegatte / Lebenspartner"),
                ("partner_birth_date", "Geburtsdatum Ehegatte / Lebenspartner"),
                ("partner_nationality", "Staatsangehörigkeit Ehegatte / Lebenspartner"),
            ],
        ),
        (
            "8. Kinder",
            [
                ("child_last_name", "Familienname Kind"),
                ("child_first_name", "Vorname Kind"),
                ("child_birth_date", "Geburtsdatum Kind"),
                ("child_nationality", "Staatsangehörigkeit Kind"),
            ],
        ),
        (
            "9. Finanzen",
            [
                ("monthly_income", "Monatliches Nettoeinkommen (€)"),
                ("income_source", "Art des Einkommens"),
            ],
        ),
        (
            "10. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "verlaengerung_aufenthaltstitel": [
        (
            "1. Personalien",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname(n)"),
                ("birth_name", "Geburtsname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort / -land"),
                ("nationality", "Staatsangehörigkeit"),
                ("gender", "Geschlecht"),
            ],
        ),
        (
            "2. Reisedokument",
            [
                ("dokumentenart", "Dokumentenart"),
                ("seriennummer", "Dokumentennummer"),
                ("ausstellungsbehoerde", "Ausstellungsbehörde / -staat"),
                ("ausstellungsdatum", "Ausstellungsdatum"),
                ("gueltig_bis", "Gültig bis"),
            ],
        ),
        (
            "3. Aktuelle Adresse in Deutschland",
            [
                ("postal_code", "Postleitzahl"),
                ("city", "Ort"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
            ],
        ),
        (
            "4. Angaben zum aktuellen Aufenthaltstitel",
            [
                ("current_permit_type", "Art des aktuellen Aufenthaltstitels"),
                ("permit_expiry_date", "Ablaufdatum des aktuellen Titels"),
            ],
        ),
        (
            "5. Aufenthalt / Verlängerungsgrund",
            [
                ("residence_purpose", "Aufenthaltszweck / Verlängerungsgrund"),
                ("visa_type", "Aktueller Aufenthaltsstatus"),
                ("entry_date", "Einreisedatum"),
            ],
        ),
        (
            "6. Beschäftigung",
            [
                ("employer_name", "Arbeitgeber"),
                ("occupation", "Beruf / Tätigkeit"),
                ("employment_start", "Beschäftigt seit"),
            ],
        ),
        (
            "7. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    # ── New document types ────────────────────────────────────────────────────
    "verpflichtungserklaerung": [
        (
            "1. Angaben zum Verpflichtungsgeber",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort"),
                ("nationality", "Staatsangehörigkeit"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
                ("phone", "Telefon"),
                ("occupation", "Beruf"),
                ("employer", "Arbeitgeber"),
            ],
        ),
        (
            "2. Angaben zum Eingeladenen (Gast)",
            [
                ("ve_gast_nachname", "Familienname des Gastes"),
                ("ve_gast_vorname", "Vorname des Gastes"),
                ("ve_gast_gebdat", "Geburtsdatum"),
                ("ve_gast_gebort", "Geburtsort"),
                ("ve_gast_staat", "Staatsangehörigkeit"),
                ("ve_gast_reisepass", "Reisepassnummer"),
                ("ve_gast_wohnort", "Wohnanschrift im Ausland"),
                ("ve_beziehung", "Beziehung zum Gast"),
            ],
        ),
        (
            "3. Aufenthalt",
            [
                ("ve_einreise", "Geplantes Einreisedatum"),
                ("ve_dauer", "Voraussichtliche Aufenthaltsdauer"),
                ("ve_zweck", "Aufenthaltszweck"),
                ("ve_adresse2", "Unterkunft in Deutschland"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "beschaeftigungserklaerung": [
        (
            "1. Angaben zum Antragsteller (Arbeitnehmer)",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("nationality", "Staatsangehörigkeit"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
            ],
        ),
        (
            "2. Angaben zum Arbeitgeber",
            [
                ("be_firma", "Firma / Arbeitgeber"),
                ("be_strasse", "Straße"),
                ("be_hausnummer", "Hausnummer"),
                ("be_plz", "Postleitzahl"),
                ("be_ort", "Ort"),
                ("be_kontaktperson", "Ansprechpartner"),
                ("phone", "Telefon"),
                ("email", "E-Mail"),
                ("be_betriebsnummer", "Betriebsnummer"),
            ],
        ),
        (
            "3. Beschäftigungsverhältnis",
            [
                ("be_berufsbezeichnung", "Berufsbezeichnung / Tätigkeit"),
                ("be_beschaeftigung", "Art des Beschäftigungsverhältnisses"),
                ("be_arbeitsstunden", "Arbeitsstunden pro Woche"),
                ("be_gehalt_monat", "Bruttogehalt (monatlich)"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "aufenthaltserlaubnis_antrag": [
        (
            "1. Persönliche Angaben",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname(n)"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort"),
                ("nationality", "Staatsangehörigkeit"),
                ("gender", "Geschlecht"),
                ("id_document_number", "Passnummer"),
                ("gueltig_bis", "Gültig bis"),
            ],
        ),
        (
            "2. Aktuelle Anschrift",
            [
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
                ("phone", "Telefon"),
                ("email", "E-Mail"),
            ],
        ),
        (
            "3. Aufenthaltstitel / Zweck",
            [
                ("visa_type", "Art des Aufenthaltstitels"),
                ("residence_purpose", "Aufenthaltszweck"),
                ("entry_date", "Einreisedatum"),
                ("employer_name", "Arbeitgeber"),
                ("occupation", "Tätigkeit"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "schulbescheinigung": [
        (
            "1. Schüler / Kind",
            [
                ("last_name", "Familienname des Kindes"),
                ("first_name", "Vorname(n)"),
                ("birth_date", "Geburtsdatum"),
                ("school_name", "Name der Schule / Ausbildungsstätte"),
                ("school_address", "Anschrift der Schule"),
                ("class_grade", "Klasse / Jahrgang"),
                ("school_year_start", "Schuljahr von"),
                ("school_year_end", "Schuljahr bis"),
            ],
        ),
        (
            "2. Antragsteller (Elternteil)",
            [
                ("parent_last_name", "Familienname des Antragstellers"),
                ("parent_first_name", "Vorname"),
                ("kg_number", "Kindergeld-Nr."),
            ],
        ),
        (
            "3. Bestätigung der Schule",
            [
                ("school_confirm_date", "Bestätigungsdatum"),
                ("school_official", "Name des Schulleiters / Beauftragten"),
            ],
        ),
    ],
    "mietbescheinigung": [
        (
            "1. Vermieter",
            [
                ("landlord_name", "Name des Vermieters"),
                ("landlord_address", "Anschrift des Vermieters"),
            ],
        ),
        (
            "2. Mieter",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
                ("mb_anzahl_personen", "Anzahl der Personen im Haushalt"),
            ],
        ),
        (
            "3. Mietverhältnis",
            [
                ("mb_mietbeginn", "Mietbeginn"),
                ("mb_wohnungsflaeche", "Wohnfläche (m²)"),
                ("mb_zimmer", "Anzahl Zimmer"),
                ("mb_kaltmiete", "Kaltmiete (€)"),
                ("mb_nebenkosten", "Nebenkosten (€)"),
                ("mb_heizkosten", "Heizkosten (€)"),
                ("mb_gesamtmiete", "Gesamtmiete (€)"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    # ── 7 new entries (mirror required fields from validate.py) ─────────────
    "abmeldung": [
        (
            "1. Angaben zur Person",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("birth_place", "Geburtsort / -land"),
                ("nationality", "Staatsangehörigkeit"),
                ("gender", "Geschlecht"),
            ],
        ),
        (
            "2. Bisherige Wohnung",
            [
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
                ("move_out_date", "Tag des Auszugs"),
            ],
        ),
        (
            "3. Neue Anschrift",
            [
                ("new_street", "Neue Straße"),
                ("new_house_number", "Neue Hausnummer"),
                ("new_plz", "Neue Postleitzahl"),
                ("new_city", "Neuer Ort"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "elterngeld": [
        (
            "1. Angaben zur Person",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("nationality", "Staatsangehörigkeit"),
                ("phone", "Telefon"),
                ("email", "E-Mail"),
            ],
        ),
        (
            "2. Kind",
            [
                ("child_name", "Name des Kindes"),
                ("child_birth_date", "Geburtsdatum des Kindes"),
            ],
        ),
        (
            "3. Bankverbindung",
            [
                ("iban", "IBAN"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "unterhaltsvorschuss": [
        (
            "1. Angaben zum Antragsteller",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
                ("phone", "Telefon"),
            ],
        ),
        (
            "2. Kind",
            [
                ("child_name", "Name des Kindes"),
                ("child_birth_date", "Geburtsdatum des Kindes"),
            ],
        ),
        (
            "3. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "kinderzuschlag": [
        (
            "1. Antragsteller",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("gender", "Geschlecht"),
                ("nationality", "Staatsangehörigkeit"),
                ("phone", "Telefon"),
                ("familienstand", "Familienstand"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("postal_code", "Postleitzahl"),
                ("city", "Ort"),
            ],
        ),
        (
            "2. Partner (bei Ehe / Lebenspartnerschaft)",
            [
                ("partner_last_name", "Partner: Familienname"),
                ("partner_first_name", "Partner: Vorname"),
                ("partner_birth_date", "Partner: Geburtsdatum"),
                ("partner_nationality", "Partner: Staatsangehörigkeit"),
            ],
        ),
        (
            "3. Kinder (Frage 4)",
            [
                ("child1_last_name", "Kind 1: Familienname"),
                ("child1_first_name", "Kind 1: Vorname"),
                ("child1_birth_date", "Kind 1: Geburtsdatum"),
                ("child2_last_name", "Kind 2: Familienname"),
                ("child2_first_name", "Kind 2: Vorname"),
                ("child2_birth_date", "Kind 2: Geburtsdatum"),
                ("child3_last_name", "Kind 3: Familienname"),
                ("child3_first_name", "Kind 3: Vorname"),
                ("child3_birth_date", "Kind 3: Geburtsdatum"),
            ],
        ),
        (
            "4. Bankverbindung",
            [
                ("iban", "IBAN"),
                ("bic", "BIC"),
                ("account_holder", "Kontoinhaber"),
            ],
        ),
        (
            "5. Unterschrift",
            [
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "bafoeg": [
        (
            "1. Angaben zur Person",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("nationality", "Staatsangehörigkeit"),
                ("phone", "Telefon"),
                ("email", "E-Mail"),
            ],
        ),
        (
            "2. Aktuelle Anschrift",
            [
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
            ],
        ),
        (
            "3. Bankverbindung",
            [
                ("iban", "IBAN"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "wbs": [
        (
            "1. Angaben zur Person",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("nationality", "Staatsangehörigkeit"),
                ("phone", "Telefon"),
            ],
        ),
        (
            "2. Aktuelle Anschrift",
            [
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
            ],
        ),
        (
            "3. Haushalt und Einkommen",
            [
                ("income", "Monatliches Einkommen (€)"),
                ("wbs_household_size", "Anzahl Personen im Haushalt"),
            ],
        ),
        (
            "4. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
    "ebk": [
        (
            "1. Angaben zum Antragsteller (Arbeitnehmer)",
            [
                ("last_name", "Familienname"),
                ("first_name", "Vorname"),
                ("birth_date", "Geburtsdatum"),
                ("street", "Straße"),
                ("house_number", "Hausnummer"),
                ("plz", "Postleitzahl"),
                ("city", "Ort"),
                ("phone", "Telefon"),
            ],
        ),
        (
            "2. Angaben zum Arbeitgeber",
            [
                ("employer_name", "Name des Arbeitgebers"),
                ("employer_address", "Anschrift des Arbeitgebers"),
            ],
        ),
        (
            "3. Unterschrift",
            [
                ("signature_place", "Ort"),
                ("signature_date", "Datum"),
            ],
        ),
    ],
}


# ---------------------------------------------------------------------------
# Localized translations for section titles and field labels (preview only)
# Languages: uk (Ukrainian), en (English), de (German), pl (Polish), tr (Turkish), ar (Arabic)
# ---------------------------------------------------------------------------

_SECTION_TITLE_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Anmeldung / Ummeldung
    "1. Neue Wohnung": {
        "uk": "Нова квартира",
        "en": "New apartment",
        "pl": "Nowe mieszkanie",
        "tr": "Yeni daire",
        "ar": "الشقة الجديدة",
    },
    "2. Bisherige Wohnung": {
        "uk": "Попередня квартира",
        "en": "Previous apartment",
        "pl": "Poprzednie mieszkanie",
        "tr": "Önceki daire",
        "ar": "الشقة السابقة",
    },
    "3. Angaben zur Person": {
        "uk": "Особисті дані",
        "en": "Personal data",
        "pl": "Dane osobowe",
        "tr": "Kişisel bilgiler",
        "ar": "البيانات الشخصية",
    },
    "4. Ausweisdokument": {
        "uk": "Документ, що посвідчує особу",
        "en": "Identity document",
        "pl": "Dokument tożsamości",
        "tr": "Kimlik belgesi",
        "ar": "وثيقة الهوية",
    },
    "5. Wohnungsgeber": {
        "uk": "Орендодавець",
        "en": "Landlord",
        "pl": "Wynajmujący",
        "tr": "Ev sahibi",
        "ar": "المؤجر",
    },
    "6. Unterschrift": {
        "uk": "Підпис",
        "en": "Signature",
        "pl": "Podpis",
        "tr": "İmza",
        "ar": "التوقيع",
    },
    "4. Unterschrift": {
        "uk": "Підпис",
        "en": "Signature",
        "pl": "Podpis",
        "tr": "İmza",
        "ar": "التوقيع",
    },
    # Wohnungsgeberbestätigung
    "1. Angaben zum Wohnungsgeber": {
        "uk": "Дані орендодавця",
        "en": "Landlord details",
        "pl": "Dane wynajmującego",
        "tr": "Ev sahibi bilgileri",
        "ar": "بيانات المؤجر",
    },
    "2. Wohnobjekt": {
        "uk": "Об'єкт нерухомості",
        "en": "Property details",
        "pl": "Nieruchomość",
        "tr": "Mülk bilgileri",
        "ar": "تفاصيل العقار",
    },
    "3. Einziehende Person(en)": {
        "uk": "Особа(и), що в'їжджає",
        "en": "Person(s) moving in",
        "pl": "Wprowadzające się osoby",
        "tr": "Taşınan kişi(ler)",
        "ar": "الشخص (الأشخاص) المنتقل",
    },
    "4. Einzugsdatum": {
        "uk": "Дата в'їзду",
        "en": "Move-in date",
        "pl": "Data wprowadzenia",
        "tr": "Taşınma tarihi",
        "ar": "تاريخ الانتقال",
    },
    "5. Erklärung / Unterschrift": {
        "uk": "Заява / Підпис",
        "en": "Declaration / Signature",
        "pl": "Oświadczenie / Podpis",
        "tr": "Beyan / İmza",
        "ar": "الإعلان / التوقيع",
    },
    # Kindergeld
    "1. Antragsteller": {
        "uk": "Заявник",
        "en": "Applicant",
        "pl": "Wnioskodawca",
        "tr": "Başvuran",
        "ar": "مقدم الطلب",
    },
    "2. Kind": {
        "uk": "Дитина",
        "en": "Child",
        "pl": "Dziecko",
        "tr": "Çocuk",
        "ar": "الطفل",
    },
    "3. Bankverbindung": {
        "uk": "Банківські реквізити",
        "en": "Bank details",
        "pl": "Dane bankowe",
        "tr": "Banka bilgileri",
        "ar": "بيانات البنك",
    },
    # Wohngeld
    "2. Wohnung": {
        "uk": "Квартира",
        "en": "Apartment",
        "pl": "Mieszkanie",
        "tr": "Daire",
        "ar": "الشقة",
    },
    "3. Haushaltsmitglieder": {
        "uk": "Члени домогосподарства",
        "en": "Household members",
        "pl": "Członkowie gospodarstwa",
        "tr": "Hane üyeleri",
        "ar": "أفراد الأسرة",
    },
    "4. Einkommen": {
        "uk": "Дохід",
        "en": "Income",
        "pl": "Dochód",
        "tr": "Gelir",
        "ar": "الدخل",
    },
    # Bürgergeld
    "2. Haushalt": {
        "uk": "Домогосподарство",
        "en": "Household",
        "pl": "Gospodarstwo domowe",
        "tr": "Hane",
        "ar": "الأسرة",
    },
    "3. Wohnkosten": {
        "uk": "Витрати на житло",
        "en": "Housing costs",
        "pl": "Koszty mieszkania",
        "tr": "Konut giderleri",
        "ar": "تكاليف السكن",
    },
    "5. Bankverbindung": {
        "uk": "Банківські реквізити",
        "en": "Bank details",
        "pl": "Dane bankowe",
        "tr": "Banka bilgileri",
        "ar": "بيانات البنك",
    },
    # Aufenthaltstitel
    "1. Personalien": {
        "uk": "Особисті дані",
        "en": "Personal details",
        "pl": "Dane osobowe",
        "tr": "Kişisel bilgiler",
        "ar": "البيانات الشخصية",
    },
    "2. Reisedokument": {
        "uk": "Документ для подорожей",
        "en": "Travel document",
        "pl": "Dokument podróży",
        "tr": "Seyahat belgesi",
        "ar": "وثيقة السفر",
    },
    "3. Aktuelle Adresse in Deutschland": {
        "uk": "Поточна адреса в Німеччині",
        "en": "Current address in Germany",
        "pl": "Adres w Niemczech",
        "tr": "Almanya'daki adres",
        "ar": "العنوان الحالي في ألمانيا",
    },
    "4. Aufenthalt / Zweck": {
        "uk": "Вид на проживання / Мета",
        "en": "Residence / Purpose",
        "pl": "Pobyt / Cel",
        "tr": "İkamet / Amaç",
        "ar": "الإقامة / الغرض",
    },
    "5. Beschäftigung": {
        "uk": "Зайнятість",
        "en": "Employment",
        "pl": "Zatrudnienie",
        "tr": "İstihdam",
        "ar": "التوظيف",
    },
    "6. Kontaktdaten": {
        "uk": "Контактні дані",
        "en": "Contact details",
        "pl": "Dane kontaktowe",
        "tr": "İletişim bilgileri",
        "ar": "بيانات الاتصال",
    },
    "7. Familienstand": {
        "uk": "Сімейний стан",
        "en": "Marital status",
        "pl": "Stan cywilny",
        "tr": "Medeni durum",
        "ar": "الحالة الاجتماعية",
    },
    "8. Kinder": {
        "uk": "Діти",
        "en": "Children",
        "pl": "Dzieci",
        "tr": "Çocuklar",
        "ar": "الأطفال",
    },
    "9. Finanzen": {
        "uk": "Фінансовий стан",
        "en": "Financial situation",
        "pl": "Sytuacja finansowa",
        "tr": "Mali durum",
        "ar": "الوضع المالي",
    },
    "10. Unterschrift": {
        "uk": "Підпис",
        "en": "Signature",
        "pl": "Podpis",
        "tr": "İmza",
        "ar": "التوقيع",
    },
    # Verpflichtungserklärung
    "1. Angaben zum Verpflichtungsgeber": {
        "uk": "Дані гаранта (запрошуючого)",
        "en": "Details of guarantor",
        "pl": "Dane poręczyciela",
        "tr": "Kefil bilgileri",
        "ar": "بيانات الضامن",
    },
    "2. Angaben zum Eingeladenen (Gast)": {
        "uk": "Дані запрошеного (гостя)",
        "en": "Details of invited guest",
        "pl": "Dane zaproszonego gościa",
        "tr": "Davetli konuk bilgileri",
        "ar": "بيانات الضيف المدعو",
    },
    "3. Aufenthalt": {
        "uk": "Перебування",
        "en": "Stay",
        "pl": "Pobyt",
        "tr": "Konaklama",
        "ar": "فترة الإقامة",
    },
    # Beschäftigungserklärung
    "1. Angaben zum Antragsteller (Arbeitnehmer)": {
        "uk": "Дані заявника (працівника)",
        "en": "Applicant (employee) data",
        "pl": "Dane pracownika",
        "tr": "Başvuran (çalışan) bilgileri",
        "ar": "بيانات مقدم الطلب (الموظف)",
    },
    "2. Angaben zum Arbeitgeber": {
        "uk": "Дані роботодавця",
        "en": "Employer details",
        "pl": "Dane pracodawcy",
        "tr": "İşveren bilgileri",
        "ar": "بيانات صاحب العمل",
    },
    "3. Beschäftigungsverhältnis": {
        "uk": "Трудові відносини",
        "en": "Employment relationship",
        "pl": "Stosunek zatrudnienia",
        "tr": "İş ilişkisi",
        "ar": "علاقة العمل",
    },
    # Persönliche Angaben variants
    "1. Persönliche Angaben": {
        "uk": "Особисті дані",
        "en": "Personal data",
        "pl": "Dane osobowe",
        "tr": "Kişisel bilgiler",
        "ar": "البيانات الشخصية",
    },
    "2. Aktuelle Anschrift": {
        "uk": "Поточна адреса",
        "en": "Current address",
        "pl": "Aktualny adres",
        "tr": "Mevcut adres",
        "ar": "العنوان الحالي",
    },
    "3. Aufenthaltstitel / Zweck": {
        "uk": "Вид на проживання / Мета",
        "en": "Residence title / Purpose",
        "pl": "Tytuł pobytowy / Cel",
        "tr": "İkamet belgesi / Amaç",
        "ar": "تصريح الإقامة / الغرض",
    },
    # Schulbescheinigung
    "1. Schüler / Kind": {
        "uk": "Учень / Дитина",
        "en": "Student / Child",
        "pl": "Uczeń / Dziecko",
        "tr": "Öğrenci / Çocuk",
        "ar": "الطالب / الطفل",
    },
    "2. Antragsteller (Elternteil)": {
        "uk": "Заявник (батько/мати)",
        "en": "Applicant (parent)",
        "pl": "Wnioskodawca (rodzic)",
        "tr": "Başvuran (ebeveyn)",
        "ar": "مقدم الطلب (الوالد)",
    },
    "3. Bestätigung der Schule": {
        "uk": "Підтвердження школи",
        "en": "School confirmation",
        "pl": "Potwierdzenie szkoły",
        "tr": "Okul onayı",
        "ar": "تأكيد المدرسة",
    },
    # Mietbescheinigung
    "1. Vermieter": {
        "uk": "Орендодавець",
        "en": "Landlord",
        "pl": "Wynajmujący",
        "tr": "Kiraya veren",
        "ar": "المؤجر",
    },
    "2. Mieter": {
        "uk": "Орендар",
        "en": "Tenant",
        "pl": "Najemca",
        "tr": "Kiracı",
        "ar": "المستأجر",
    },
    "3. Mietverhältnis": {
        "uk": "Умови оренди",
        "en": "Tenancy conditions",
        "pl": "Warunki najmu",
        "tr": "Kiralama koşulları",
        "ar": "شروط الإيجار",
    },
    # Generic
    "Angaben zur Person": {
        "uk": "Особисті дані",
        "en": "Personal data",
        "pl": "Dane osobowe",
        "tr": "Kişisel bilgiler",
        "ar": "البيانات الشخصية",
    },
    "Unterschrift": {
        "uk": "Підпис",
        "en": "Signature",
        "pl": "Podpis",
        "tr": "İmza",
        "ar": "التوقيع",
    },
    # ── Anmeldung renamed / new section titles ───────────────────────────────
    "3. Angaben zur Person 1": {
        "uk": "Особисті дані (особа 1)",
        "en": "Personal data (person 1)",
        "pl": "Dane osobowe (osoba 1)",
        "tr": "Kişisel bilgiler (kişi 1)",
        "ar": "البيانات الشخصية (الشخص 1)",
    },
    "4. Angaben zur Person 2 (Ehepartner/in)": {
        "uk": "Особисті дані (чоловік/дружина)",
        "en": "Personal data (spouse)",
        "pl": "Dane osobowe (małżonek)",
        "tr": "Kişisel bilgiler (eş)",
        "ar": "البيانات الشخصية (الزوج/الزوجة)",
    },
    "5. Ausweisdokument": {
        "uk": "Посвідчення особи",
        "en": "Identity document",
        "pl": "Dokument tożsamości",
        "tr": "Kimlik belgesi",
        "ar": "وثيقة الهوية",
    },
    "6. Wohnungsgeber": {
        "uk": "Орендодавець",
        "en": "Landlord",
        "pl": "Wynajmujący",
        "tr": "Ev sahibi",
        "ar": "المؤجر",
    },
    "7. Unterschrift": {
        "uk": "Підпис",
        "en": "Signature",
        "pl": "Podpis",
        "tr": "İmza",
        "ar": "التوقيع",
    },
    # ── New section titles for 7 added doc_types ─────────────────────────────
    "3. Neue Anschrift": {
        "uk": "Нова адреса",
        "en": "New address",
        "pl": "Nowy adres",
        "tr": "Yeni adres",
        "ar": "العنوان الجديد",
    },
    "1. Angaben zum Antragsteller": {
        "uk": "Дані заявника",
        "en": "Applicant details",
        "pl": "Dane wnioskodawcy",
        "tr": "Başvuran bilgileri",
        "ar": "بيانات مقدم الطلب",
    },
    "3. Haushalt und Einkommen": {
        "uk": "Домогосподарство та дохід",
        "en": "Household and income",
        "pl": "Gospodarstwo i dochód",
        "tr": "Hane ve gelir",
        "ar": "الأسرة والدخل",
    },
    "3. Unterschrift": {
        "uk": "Підпис",
        "en": "Signature",
        "pl": "Podpis",
        "tr": "İmza",
        "ar": "التوقيع",
    },
}

_FIELD_LABEL_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Personal
    "last_name": {
        "uk": "Прізвище",
        "en": "Last name",
        "pl": "Nazwisko",
        "tr": "Soyadı",
        "ar": "اسم العائلة",
    },
    "first_name": {
        "uk": "Ім'я",
        "en": "First name",
        "pl": "Imię",
        "tr": "Ad",
        "ar": "الاسم الأول",
    },
    "birth_name": {
        "uk": "Дівоче прізвище",
        "en": "Birth name",
        "pl": "Nazwisko rodowe",
        "tr": "Doğum soyadı",
        "ar": "اسم الميلاد",
    },
    "birth_date": {
        "uk": "Дата народження",
        "en": "Date of birth",
        "pl": "Data urodzenia",
        "tr": "Doğum tarihi",
        "ar": "تاريخ الميلاد",
    },
    "birth_place": {
        "uk": "Місце народження",
        "en": "Place of birth",
        "pl": "Miejsce urodzenia",
        "tr": "Doğum yeri",
        "ar": "مكان الميلاد",
    },
    "nationality": {
        "uk": "Громадянство",
        "en": "Nationality",
        "pl": "Obywatelstwo",
        "tr": "Uyruk",
        "ar": "الجنسية",
    },
    "gender": {
        "uk": "Стать",
        "en": "Gender",
        "pl": "Płeć",
        "tr": "Cinsiyet",
        "ar": "الجنس",
    },
    "familienstand": {
        "uk": "Сімейний стан",
        "en": "Marital status",
        "pl": "Stan cywilny",
        "tr": "Medeni durum",
        "ar": "الحالة الاجتماعية",
    },
    "religion": {
        "uk": "Релігія",
        "en": "Religion",
        "pl": "Religia",
        "tr": "Din",
        "ar": "الديانة",
    },
    "phone": {
        "uk": "Телефон",
        "en": "Phone",
        "pl": "Telefon",
        "tr": "Telefon",
        "ar": "الهاتف",
    },
    "email": {
        "uk": "Електронна пошта",
        "en": "Email",
        "pl": "E-mail",
        "tr": "E-posta",
        "ar": "البريد الإلكتروني",
    },
    "occupation": {
        "uk": "Професія",
        "en": "Occupation",
        "pl": "Zawód",
        "tr": "Meslek",
        "ar": "المهنة",
    },
    "employer": {
        "uk": "Роботодавець",
        "en": "Employer",
        "pl": "Pracodawca",
        "tr": "İşveren",
        "ar": "صاحب العمل",
    },
    # Address
    "street": {
        "uk": "Вулиця",
        "en": "Street",
        "pl": "Ulica",
        "tr": "Sokak",
        "ar": "الشارع",
    },
    "house_number": {
        "uk": "Номер будинку",
        "en": "House number",
        "pl": "Numer domu",
        "tr": "Bina numarası",
        "ar": "رقم المنزل",
    },
    "apartment_number": {
        "uk": "Номер квартири",
        "en": "Apartment number",
        "pl": "Numer mieszkania",
        "tr": "Daire numarası",
        "ar": "رقم الشقة",
    },
    "postal_code": {
        "uk": "Поштовий індекс",
        "en": "Postal code",
        "pl": "Kod pocztowy",
        "tr": "Posta kodu",
        "ar": "الرمز البريدي",
    },
    "city": {
        "uk": "Місто",
        "en": "City",
        "pl": "Miasto",
        "tr": "Şehir",
        "ar": "المدينة",
    },
    "plz": {
        "uk": "Поштовий індекс",
        "en": "Postal code",
        "pl": "Kod pocztowy",
        "tr": "Posta kodu",
        "ar": "الرمز البريدي",
    },
    "previous_address": {
        "uk": "Попередня адреса",
        "en": "Previous address",
        "pl": "Poprzedni adres",
        "tr": "Önceki adres",
        "ar": "العنوان السابق",
    },
    # Dates / move
    "move_in_date": {
        "uk": "Дата в'їзду",
        "en": "Move-in date",
        "pl": "Data wprowadzenia",
        "tr": "Taşınma tarihi",
        "ar": "تاريخ الانتقال",
    },
    "move_out_date": {
        "uk": "Дата виїзду",
        "en": "Move-out date",
        "pl": "Data wyprowadzki",
        "tr": "Çıkış tarihi",
        "ar": "تاريخ المغادرة",
    },
    "entry_date": {
        "uk": "Дата в'їзду до Німеччини",
        "en": "Date of entry",
        "pl": "Data wjazdu do Niemiec",
        "tr": "Almanya'ya giriş tarihi",
        "ar": "تاريخ الدخول إلى ألمانيا",
    },
    "signature_date": {
        "uk": "Дата підпису",
        "en": "Date of signature",
        "pl": "Data podpisu",
        "tr": "İmza tarihi",
        "ar": "تاريخ التوقيع",
    },
    "signature_place": {
        "uk": "Місце підписання",
        "en": "Place of signature",
        "pl": "Miejsce podpisu",
        "tr": "İmza yeri",
        "ar": "مكان التوقيع",
    },
    # Property type
    "wohnungstyp": {
        "uk": "Тип квартири",
        "en": "Apartment type",
        "pl": "Typ mieszkania",
        "tr": "Daire türü",
        "ar": "نوع الشقة",
    },
    "has_bisherige_wohnung": {
        "uk": "Наявність попередньої квартири",
        "en": "Has previous apartment",
        "pl": "Poprzednia nieruchomość",
        "tr": "Önceki daire var mı",
        "ar": "وجود شقة سابقة",
    },
    "zuzug_aus_ausland": {
        "uk": "Приїзд з-за кордону",
        "en": "Moving from abroad",
        "pl": "Przyjazd z zagranicy",
        "tr": "Yurt dışından taşınma",
        "ar": "الانتقال من الخارج",
    },
    "zuzug_staat": {
        "uk": "Країна попереднього проживання",
        "en": "Country of previous residence",
        "pl": "Poprzedni kraj zamieszkania",
        "tr": "Önceki ikamet ülkesi",
        "ar": "بلد الإقامة السابق",
    },
    # Documents
    "dokumentenart": {
        "uk": "Тип документа",
        "en": "Document type",
        "pl": "Rodzaj dokumentu",
        "tr": "Belge türü",
        "ar": "نوع الوثيقة",
    },
    "seriennummer": {
        "uk": "Номер документа",
        "en": "Document number",
        "pl": "Numer dokumentu",
        "tr": "Belge numarası",
        "ar": "رقم الوثيقة",
    },
    "ausstellungsbehoerde": {
        "uk": "Орган, що видав документ",
        "en": "Issuing authority",
        "pl": "Organ wydający",
        "tr": "Düzenleyen makam",
        "ar": "جهة الإصدار",
    },
    "ausstellungsdatum": {
        "uk": "Дата видачі",
        "en": "Date of issue",
        "pl": "Data wydania",
        "tr": "Düzenleme tarihi",
        "ar": "تاريخ الإصدار",
    },
    "gueltig_bis": {
        "uk": "Дійсний до",
        "en": "Valid until",
        "pl": "Ważny do",
        "tr": "Geçerlilik tarihi",
        "ar": "صالح حتى",
    },
    "id_document_number": {
        "uk": "Номер паспорта",
        "en": "Passport number",
        "pl": "Numer paszportu",
        "tr": "Pasaport numarası",
        "ar": "رقم جواز السفر",
    },
    # Landlord
    "landlord_name": {
        "uk": "Ім'я орендодавця",
        "en": "Landlord name",
        "pl": "Imię/nazwisko wynajmującego",
        "tr": "Ev sahibinin adı",
        "ar": "اسم المؤجر",
    },
    "landlord_address": {
        "uk": "Адреса орендодавця",
        "en": "Landlord address",
        "pl": "Adres wynajmującego",
        "tr": "Ev sahibinin adresi",
        "ar": "عنوان المؤجر",
    },
    # Bank
    "iban": {
        "uk": "IBAN (номер рахунку)",
        "en": "IBAN (account number)",
        "pl": "IBAN (numer konta)",
        "tr": "IBAN (hesap numarası)",
        "ar": "رقم الحساب IBAN",
    },
    "bank_name": {
        "uk": "Назва банку",
        "en": "Bank name",
        "pl": "Nazwa banku",
        "tr": "Banka adı",
        "ar": "اسم البنك",
    },
    "account_holder": {
        "uk": "Власник рахунку",
        "en": "Account holder",
        "pl": "Właściciel konta",
        "tr": "Hesap sahibi",
        "ar": "صاحب الحساب",
    },
    "tax_id": {
        "uk": "Ідентифікаційний номер платника податків",
        "en": "Tax ID number",
        "pl": "Numer identyfikacji podatkowej",
        "tr": "Vergi kimlik numarası",
        "ar": "رقم التعريف الضريبي",
    },
    # Children
    "child_last_name": {
        "uk": "Прізвище дитини",
        "en": "Child's last name",
        "pl": "Nazwisko dziecka",
        "tr": "Çocuğun soyadı",
        "ar": "لقب الطفل",
    },
    "child_first_name": {
        "uk": "Ім'я дитини",
        "en": "Child's first name",
        "pl": "Imię dziecka",
        "tr": "Çocuğun adı",
        "ar": "اسم الطفل",
    },
    "child_birth_date": {
        "uk": "Дата народження дитини",
        "en": "Child's date of birth",
        "pl": "Data urodzenia dziecka",
        "tr": "Çocuğun doğum tarihi",
        "ar": "تاريخ ميلاد الطفل",
    },
    "child_birth_place": {
        "uk": "Місце народження дитини",
        "en": "Child's place of birth",
        "pl": "Miejsce urodzenia dziecka",
        "tr": "Çocuğun doğum yeri",
        "ar": "مكان ميلاد الطفل",
    },
    "child_nationality": {
        "uk": "Громадянство дитини",
        "en": "Child's nationality",
        "pl": "Obywatelstwo dziecka",
        "tr": "Çocuğun uyruğu",
        "ar": "جنسية الطفل",
    },
    # Housing / income
    "dwelling_type": {
        "uk": "Тип житла",
        "en": "Dwelling type",
        "pl": "Typ lokalu",
        "tr": "Konut türü",
        "ar": "نوع السكن",
    },
    "living_space_sqm": {
        "uk": "Площа житла (м²)",
        "en": "Living area (m²)",
        "pl": "Powierzchnia mieszkania (m²)",
        "tr": "Yaşam alanı (m²)",
        "ar": "مساحة المسكن (م²)",
    },
    "monthly_rent": {
        "uk": "Щомісячна орендна плата (€)",
        "en": "Monthly rent (€)",
        "pl": "Miesięczny czynsz (€)",
        "tr": "Aylık kira (€)",
        "ar": "الإيجار الشهري (€)",
    },
    "heating_costs": {
        "uk": "Витрати на опалення (€)",
        "en": "Heating costs (€)",
        "pl": "Koszty ogrzewania (€)",
        "tr": "Isıtma giderleri (€)",
        "ar": "تكاليف التدفئة (€)",
    },
    "additional_costs": {
        "uk": "Додаткові витрати (€)",
        "en": "Additional costs (€)",
        "pl": "Koszty dodatkowe (€)",
        "tr": "Ek masraflar (€)",
        "ar": "التكاليف الإضافية (€)",
    },
    "household_members": {
        "uk": "Кількість членів домогосподарства",
        "en": "Number of household members",
        "pl": "Liczba członków gospodarstwa",
        "tr": "Hane üyesi sayısı",
        "ar": "عدد أفراد الأسرة",
    },
    "family_status": {
        "uk": "Сімейний стан",
        "en": "Family status",
        "pl": "Stan rodzinny",
        "tr": "Aile durumu",
        "ar": "الوضع العائلي",
    },
    "monthly_income": {
        "uk": "Щомісячний дохід (€)",
        "en": "Monthly income (€)",
        "pl": "Miesięczny dochód (€)",
        "tr": "Aylık gelir (€)",
        "ar": "الدخل الشهري (€)",
    },
    "income_source": {
        "uk": "Джерело доходу",
        "en": "Income source",
        "pl": "Źródło dochodu",
        "tr": "Gelir kaynağı",
        "ar": "مصدر الدخل",
    },
    "other_income": {
        "uk": "Інший дохід (€)",
        "en": "Other income (€)",
        "pl": "Inny dochód (€)",
        "tr": "Diğer gelir (€)",
        "ar": "دخل آخر (€)",
    },
    "employment_status": {
        "uk": "Статус зайнятості",
        "en": "Employment status",
        "pl": "Status zatrudnienia",
        "tr": "İstihdam durumu",
        "ar": "حالة التوظيف",
    },
    # Aufenthaltstitel extras
    "partner_last_name": {
        "uk": "Прізвище чоловіка / партнера",
        "en": "Spouse / partner last name",
        "pl": "Nazwisko małżonka / partnera",
        "tr": "Eş / partner soyadı",
        "ar": "لقب الزوج / الشريك",
    },
    "partner_first_name": {
        "uk": "Ім'я чоловіка / партнера",
        "en": "Spouse / partner first name",
        "pl": "Imię małżonka / partnera",
        "tr": "Eş / partner adı",
        "ar": "اسم الزوج / الشريك",
    },
    "partner_birth_date": {
        "uk": "Дата народження чоловіка / партнера",
        "en": "Spouse / partner date of birth",
        "pl": "Data urodzenia małżonka / partnera",
        "tr": "Eş / partner doğum tarihi",
        "ar": "تاريخ ميلاد الزوج / الشريك",
    },
    "partner_nationality": {
        "uk": "Громадянство чоловіка / партнера",
        "en": "Spouse / partner nationality",
        "pl": "Obywatelstwo małżonka / partnera",
        "tr": "Eş / partner uyruğu",
        "ar": "جنسية الزوج / الشريك",
    },
    "residence_purpose": {
        "uk": "Мета проживання",
        "en": "Purpose of residence",
        "pl": "Cel pobytu",
        "tr": "İkamet amacı",
        "ar": "الغرض من الإقامة",
    },
    "visa_type": {
        "uk": "Поточний статус перебування",
        "en": "Current residence status",
        "pl": "Aktualny status pobytu",
        "tr": "Mevcut ikamet statüsü",
        "ar": "وضع الإقامة الحالي",
    },
    "employer_name": {
        "uk": "Роботодавець",
        "en": "Employer",
        "pl": "Pracodawca",
        "tr": "İşveren",
        "ar": "صاحب العمل",
    },
    "employment_start": {
        "uk": "Працює з",
        "en": "Employed since",
        "pl": "Zatrudniony od",
        "tr": "İstihdam başlangıcı",
        "ar": "موظف منذ",
    },
    # Verpflichtungserklärung
    "ve_gast_nachname": {
        "uk": "Прізвище гостя",
        "en": "Guest's last name",
        "pl": "Nazwisko gościa",
        "tr": "Konuğun soyadı",
        "ar": "لقب الضيف",
    },
    "ve_gast_vorname": {
        "uk": "Ім'я гостя",
        "en": "Guest's first name",
        "pl": "Imię gościa",
        "tr": "Konuğun adı",
        "ar": "اسم الضيف",
    },
    "ve_gast_gebdat": {
        "uk": "Дата народження гостя",
        "en": "Guest's date of birth",
        "pl": "Data urodzenia gościa",
        "tr": "Konuğun doğum tarihi",
        "ar": "تاريخ ميلاد الضيف",
    },
    "ve_gast_gebort": {
        "uk": "Місце народження гостя",
        "en": "Guest's place of birth",
        "pl": "Miejsce urodzenia gościa",
        "tr": "Konuğun doğum yeri",
        "ar": "مكان ميلاد الضيف",
    },
    "ve_gast_staat": {
        "uk": "Громадянство гостя",
        "en": "Guest's nationality",
        "pl": "Obywatelstwo gościa",
        "tr": "Konuğun uyruğu",
        "ar": "جنسية الضيف",
    },
    "ve_gast_reisepass": {
        "uk": "Номер паспорта гостя",
        "en": "Guest's passport number",
        "pl": "Paszport gościa",
        "tr": "Konuğun pasaport numarası",
        "ar": "رقم جواز سفر الضيف",
    },
    "ve_gast_wohnort": {
        "uk": "Адреса гостя за кордоном",
        "en": "Guest's address abroad",
        "pl": "Adres gościa za granicą",
        "tr": "Konuğun yurt dışı adresi",
        "ar": "عنوان الضيف في الخارج",
    },
    "ve_beziehung": {
        "uk": "Відносини з гостем",
        "en": "Relationship with guest",
        "pl": "Relacja z gościem",
        "tr": "Konukla ilişki",
        "ar": "العلاقة بالضيف",
    },
    "ve_einreise": {
        "uk": "Плановане дата в'їзду",
        "en": "Planned entry date",
        "pl": "Planowana data wjazdu",
        "tr": "Planlanan giriş tarihi",
        "ar": "تاريخ الدخول المخطط",
    },
    "ve_dauer": {
        "uk": "Орієнтовна тривалість перебування",
        "en": "Expected duration of stay",
        "pl": "Przewidywany czas pobytu",
        "tr": "Tahmini konaklama süresi",
        "ar": "مدة الإقامة المتوقعة",
    },
    "ve_zweck": {
        "uk": "Мета перебування",
        "en": "Purpose of stay",
        "pl": "Cel pobytu",
        "tr": "Konaklama amacı",
        "ar": "الغرض من الإقامة",
    },
    "ve_adresse2": {
        "uk": "Адреса проживання в Німеччині",
        "en": "Accommodation address in Germany",
        "pl": "Adres zakwaterowania w Niemczech",
        "tr": "Almanya'daki konaklama adresi",
        "ar": "عنوان الإقامة في ألمانيا",
    },
    # Beschäftigungserklärung employer fields
    "be_firma": {
        "uk": "Компанія / Роботодавець",
        "en": "Company / Employer",
        "pl": "Firma / Pracodawca",
        "tr": "Şirket / İşveren",
        "ar": "الشركة / صاحب العمل",
    },
    "be_strasse": {
        "uk": "Вулиця (роботодавець)",
        "en": "Street (employer)",
        "pl": "Ulica (pracodawca)",
        "tr": "Sokak (işveren)",
        "ar": "شارع صاحب العمل",
    },
    "be_hausnummer": {
        "uk": "Номер будинку (роботодавець)",
        "en": "House number (employer)",
        "pl": "Numer domu (pracodawca)",
        "tr": "Bina numarası (işveren)",
        "ar": "رقم منزل صاحب العمل",
    },
    "be_plz": {
        "uk": "Поштовий індекс (роботодавець)",
        "en": "Postal code (employer)",
        "pl": "Kod pocztowy (pracodawca)",
        "tr": "Posta kodu (işveren)",
        "ar": "الرمز البريدي لصاحب العمل",
    },
    "be_ort": {
        "uk": "Місто (роботодавець)",
        "en": "City (employer)",
        "pl": "Miasto (pracodawca)",
        "tr": "Şehir (işveren)",
        "ar": "مدينة صاحب العمل",
    },
    "be_kontaktperson": {
        "uk": "Контактна особа",
        "en": "Contact person",
        "pl": "Osoba kontaktowa",
        "tr": "İletişim kişisi",
        "ar": "جهة الاتصال",
    },
    "be_betriebsnummer": {
        "uk": "Номер підприємства",
        "en": "Company registration number",
        "pl": "Numer firmy",
        "tr": "İşletme numarası",
        "ar": "رقم المنشأة",
    },
    "be_berufsbezeichnung": {
        "uk": "Посада / Діяльність",
        "en": "Job title / Activity",
        "pl": "Stanowisko / Działalność",
        "tr": "İş unvanı / Faaliyet",
        "ar": "المسمى الوظيفي / النشاط",
    },
    "be_beschaeftigung": {
        "uk": "Вид трудових відносин",
        "en": "Type of employment",
        "pl": "Rodzaj zatrudnienia",
        "tr": "Çalışma şekli",
        "ar": "نوع العمل",
    },
    "be_arbeitsstunden": {
        "uk": "Робочі години на тиждень",
        "en": "Working hours per week",
        "pl": "Godziny pracy tygodniowo",
        "tr": "Haftalık çalışma saatleri",
        "ar": "ساعات العمل الأسبوعية",
    },
    "be_gehalt_monat": {
        "uk": "Брутто-зарплата (щомісяця)",
        "en": "Gross monthly salary",
        "pl": "Wynagrodzenie brutto (miesięcznie)",
        "tr": "Brüt aylık maaş",
        "ar": "الراتب الإجمالي الشهري",
    },
    # School
    "school_name": {
        "uk": "Назва школи",
        "en": "School name",
        "pl": "Nazwa szkoły",
        "tr": "Okul adı",
        "ar": "اسم المدرسة",
    },
    "school_address": {
        "uk": "Адреса школи",
        "en": "School address",
        "pl": "Adres szkoły",
        "tr": "Okul adresi",
        "ar": "عنوان المدرسة",
    },
    "class_grade": {
        "uk": "Клас / Рік навчання",
        "en": "Class / Year",
        "pl": "Klasa / Rok",
        "tr": "Sınıf / Yıl",
        "ar": "الصف / السنة الدراسية",
    },
    "school_year_start": {
        "uk": "Навчальний рік — початок",
        "en": "School year start",
        "pl": "Rok szkolny — początek",
        "tr": "Öğrenim yılı başlangıcı",
        "ar": "بداية العام الدراسي",
    },
    "school_year_end": {
        "uk": "Навчальний рік — кінець",
        "en": "School year end",
        "pl": "Rok szkolny — koniec",
        "tr": "Öğrenim yılı bitişi",
        "ar": "نهاية العام الدراسي",
    },
    "parent_last_name": {
        "uk": "Прізвище батька/матері",
        "en": "Parent's last name",
        "pl": "Nazwisko rodzica",
        "tr": "Ebeveynin soyadı",
        "ar": "لقب الوالد",
    },
    "parent_first_name": {
        "uk": "Ім'я батька/матері",
        "en": "Parent's first name",
        "pl": "Imię rodzica",
        "tr": "Ebeveynin adı",
        "ar": "اسم الوالد",
    },
    "kg_number": {
        "uk": "Номер Kindergeld",
        "en": "Kindergeld number",
        "pl": "Numer Kindergeld",
        "tr": "Kindergeld numarası",
        "ar": "رقم Kindergeld",
    },
    "school_confirm_date": {
        "uk": "Дата підтвердження",
        "en": "Confirmation date",
        "pl": "Data potwierdzenia",
        "tr": "Onay tarihi",
        "ar": "تاريخ التأكيد",
    },
    "school_official": {
        "uk": "Ім'я директора / уповноваженого",
        "en": "Principal / authorized person",
        "pl": "Dyrektor / upoważniona osoba",
        "tr": "Müdür / Yetkili kişi",
        "ar": "المدير / الشخص المفوض",
    },
    # Mietbescheinigung
    "mb_anzahl_personen": {
        "uk": "Кількість осіб у домогосподарстві",
        "en": "Number of persons in household",
        "pl": "Liczba osób w gospodarstwie",
        "tr": "Hane kişi sayısı",
        "ar": "عدد الأشخاص في الأسرة",
    },
    "mb_mietbeginn": {
        "uk": "Початок оренди",
        "en": "Tenancy start date",
        "pl": "Początek najmu",
        "tr": "Kiralama başlangıcı",
        "ar": "بداية الإيجار",
    },
    "mb_wohnungsflaeche": {
        "uk": "Площа квартири (м²)",
        "en": "Apartment area (m²)",
        "pl": "Powierzchnia mieszkania (m²)",
        "tr": "Daire alanı (m²)",
        "ar": "مساحة الشقة (م²)",
    },
    "mb_zimmer": {
        "uk": "Кількість кімнат",
        "en": "Number of rooms",
        "pl": "Liczba pokoi",
        "tr": "Oda sayısı",
        "ar": "عدد الغرف",
    },
    "mb_kaltmiete": {
        "uk": "Базова орендна плата (€)",
        "en": "Base rent (€)",
        "pl": "Czynsz netto (€)",
        "tr": "Temel kira (€)",
        "ar": "الإيجار الأساسي (€)",
    },
    "mb_nebenkosten": {
        "uk": "Комунальні послуги (€)",
        "en": "Utilities (€)",
        "pl": "Koszty dodatkowe (€)",
        "tr": "Ortak giderler (€)",
        "ar": "المرافق (€)",
    },
    "mb_heizkosten": {
        "uk": "Витрати на опалення (€)",
        "en": "Heating costs (€)",
        "pl": "Koszty ogrzewania (€)",
        "tr": "Isıtma maliyetleri (€)",
        "ar": "تكاليف التدفئة (€)",
    },
    "mb_gesamtmiete": {
        "uk": "Загальна орендна плата (€)",
        "en": "Total rent (€)",
        "pl": "Całkowity czynsz (€)",
        "tr": "Toplam kira (€)",
        "ar": "إجمالي الإيجار (€)",
    },
    # ── Fields added for 7 new doc_types ──────────────────────────────────────
    "child_name": {
        "uk": "Ім'я дитини",
        "en": "Child's name",
        "pl": "Imię dziecka",
        "tr": "Çocuğun adı",
        "ar": "اسم الطفل",
    },
    "income": {
        "uk": "Щомісячний дохід (€)",
        "en": "Monthly income (€)",
        "pl": "Miesięczny dochód (€)",
        "tr": "Aylık gelir (€)",
        "ar": "الدخل الشهري (€)",
    },
    "wbs_household_size": {
        "uk": "Кількість осіб у домогосподарстві",
        "en": "Number of persons in household",
        "pl": "Liczba osób w gospodarstwie",
        "tr": "Hane kişi sayısı",
        "ar": "عدد أفراد الأسرة",
    },
    "employer_address": {
        "uk": "Адреса роботодавця",
        "en": "Employer address",
        "pl": "Adres pracodawcy",
        "tr": "İşveren adresi",
        "ar": "عنوان صاحب العمل",
    },
    "new_street": {
        "uk": "Нова вулиця",
        "en": "New street",
        "pl": "Nowa ulica",
        "tr": "Yeni sokak",
        "ar": "الشارع الجديد",
    },
    "new_house_number": {
        "uk": "Новий номер будинку",
        "en": "New house number",
        "pl": "Nowy numer domu",
        "tr": "Yeni bina numarası",
        "ar": "رقم المنزل الجديد",
    },
    "new_plz": {
        "uk": "Новий поштовий індекс",
        "en": "New postal code",
        "pl": "Nowy kod pocztowy",
        "tr": "Yeni posta kodu",
        "ar": "الرمز البريدي الجديد",
    },
    "new_city": {
        "uk": "Нове місто",
        "en": "New city",
        "pl": "Nowe miasto",
        "tr": "Yeni şehir",
        "ar": "المدينة الجديدة",
    },
    # Anmeldung synthesized fields
    "street_display": {
        "uk": "Вулиця / Номер будинку",
        "en": "Street / House number",
        "pl": "Ulica / Numer domu",
        "tr": "Sokak / Bina numarası",
        "ar": "الشارع / رقم المنزل",
    },
    "weitere_wohnungen": {
        "uk": "Інші місця проживання в Німеччині",
        "en": "Other residences in Germany",
        "pl": "Inne miejsca zamieszkania",
        "tr": "Almanya'daki diğer konutlar",
        "ar": "مساكن أخرى في ألمانيا",
    },
    "gemeindekennzahl": {
        "uk": "Код муніципалітету",
        "en": "Municipality code",
        "pl": "Kod gminy",
        "tr": "Belediye kodu",
        "ar": "رمز البلدية",
    },
    # Anmeldung — previous address fields
    "previous_strasse": {
        "uk": "Вулиця (попередня квартира)",
        "en": "Street (previous residence)",
        "pl": "Ulica (poprzednie mieszkanie)",
        "tr": "Sokak (önceki konut)",
        "ar": "الشارع (السكن السابق)",
    },
    "previous_hausnummer": {
        "uk": "Номер будинку (попередня квартира)",
        "en": "House number (previous residence)",
        "pl": "Numer domu (poprzednie mieszkanie)",
        "tr": "Bina numarası (önceki konut)",
        "ar": "رقم المنزل (السكن السابق)",
    },
    "previous_plz": {
        "uk": "Індекс (попередня квартира)",
        "en": "Postal code (previous residence)",
        "pl": "Kod pocztowy (poprzednie m.)",
        "tr": "Posta kodu (önceki konut)",
        "ar": "الرمز البريدي (السكن السابق)",
    },
    "previous_ort": {
        "uk": "Місто (попередня квартира)",
        "en": "City (previous residence)",
        "pl": "Miasto (poprzednie mieszkanie)",
        "tr": "Şehir (önceki konut)",
        "ar": "المدينة (السكن السابق)",
    },
    "bisherige_beibehalten": {
        "uk": "Зберегти попередню квартиру",
        "en": "Keep previous apartment",
        "pl": "Zachować poprzednie mieszkanie",
        "tr": "Önceki daireyi koru",
        "ar": "الاحتفاظ بالشقة السابقة",
    },
    "bisherige_wohnungstyp": {
        "uk": "Тип попередньої квартири",
        "en": "Type of previous apartment",
        "pl": "Typ poprzedniego mieszkania",
        "tr": "Önceki daire türü",
        "ar": "نوع الشقة السابقة",
    },
    # Anmeldung — personal section extras
    "eheschliessung_ort_datum": {
        "uk": "Місце та дата одруження",
        "en": "Place and date of marriage",
        "pl": "Miejsce i data ślubu",
        "tr": "Evlilik yeri ve tarihi",
        "ar": "مكان وتاريخ الزواج",
    },
    "passname": {
        "uk": "Ім'я у паспорті",
        "en": "Name in passport",
        "pl": "Imię w paszporcie",
        "tr": "Pasaport adı",
        "ar": "الاسم في جواز السفر",
    },
    "ordens_kuenstlername": {
        "uk": "Чернече / сценічне ім'я",
        "en": "Religious or stage name",
        "pl": "Imię zakonne / artystyczne",
        "tr": "Dini veya sahne adı",
        "ar": "الاسم الديني أو الفني",
    },
    # Anmeldung — Person 2 fields
    "person2_last_name": {
        "uk": "Прізвище (особа 2)",
        "en": "Last name (person 2)",
        "pl": "Nazwisko (osoba 2)",
        "tr": "Soyadı (kişi 2)",
        "ar": "اسم العائلة (الشخص 2)",
    },
    "person2_first_name": {
        "uk": "Ім'я (особа 2)",
        "en": "First name (person 2)",
        "pl": "Imię (osoba 2)",
        "tr": "Ad (kişi 2)",
        "ar": "الاسم الأول (الشخص 2)",
    },
    "person2_birth_name": {
        "uk": "Дівоче прізвище (особа 2)",
        "en": "Birth name (person 2)",
        "pl": "Nazwisko rodowe (osoba 2)",
        "tr": "Doğum soyadı (kişi 2)",
        "ar": "اسم الميلاد (الشخص 2)",
    },
    "person2_birth_date": {
        "uk": "Дата народження (особа 2)",
        "en": "Date of birth (person 2)",
        "pl": "Data urodzenia (osoba 2)",
        "tr": "Doğum tarihi (kişi 2)",
        "ar": "تاريخ الميلاد (الشخص 2)",
    },
    "person2_birth_place": {
        "uk": "Місце народження (особа 2)",
        "en": "Place of birth (person 2)",
        "pl": "Miejsce urodzenia (osoba 2)",
        "tr": "Doğum yeri (kişi 2)",
        "ar": "مكان الميلاد (الشخص 2)",
    },
    "person2_nationality": {
        "uk": "Громадянство (особа 2)",
        "en": "Nationality (person 2)",
        "pl": "Obywatelstwo (osoba 2)",
        "tr": "Uyruk (kişi 2)",
        "ar": "الجنسية (الشخص 2)",
    },
    "person2_gender": {
        "uk": "Стать (особа 2)",
        "en": "Gender (person 2)",
        "pl": "Płeć (osoba 2)",
        "tr": "Cinsiyet (kişi 2)",
        "ar": "الجنس (الشخص 2)",
    },
    "person2_religion": {
        "uk": "Релігійна громада (особа 2)",
        "en": "Religious community (person 2)",
        "pl": "Wspólnota religijna (osoba 2)",
        "tr": "Dini topluluk (kişi 2)",
        "ar": "الطائفة الدينية (الشخص 2)",
    },
    "person2_ordens_kuenstlername": {
        "uk": "Чернече / сценічне ім'я (особа 2)",
        "en": "Religious or stage name (person 2)",
        "pl": "Imię zakonne / artystyczne (os. 2)",
        "tr": "Dini veya sahne adı (kişi 2)",
        "ar": "الاسم الديني أو الفني (الشخص 2)",
    },
    # Anmeldung — landlord split fields
    "landlord_street": {
        "uk": "Вулиця (орендодавець)",
        "en": "Street (landlord)",
        "pl": "Ulica (wynajmujący)",
        "tr": "Sokak (ev sahibi)",
        "ar": "الشارع (المؤجر)",
    },
    "landlord_house_number": {
        "uk": "Номер будинку (орендодавець)",
        "en": "House number (landlord)",
        "pl": "Numer domu (wynajmujący)",
        "tr": "Bina numarası (ev sahibi)",
        "ar": "رقم المنزل (المؤجر)",
    },
    "landlord_plz": {
        "uk": "Індекс (орендодавець)",
        "en": "Postal code (landlord)",
        "pl": "Kod pocztowy (wynajmujący)",
        "tr": "Posta kodu (ev sahibi)",
        "ar": "الرمز البريدي (المؤجر)",
    },
    "landlord_city": {
        "uk": "Місто (орендодавець)",
        "en": "City (landlord)",
        "pl": "Miasto (wynajmujący)",
        "tr": "Şehir (ev sahibi)",
        "ar": "المدينة (المؤجر)",
    },
}


def _get_field_hint(field_key: str, user_lang: str) -> str:
    """Return localized field label hint for the given language. Empty string if not found."""
    if not user_lang or user_lang in ("de",):
        return ""  # German users: no hint needed (labels already in German)
    lang = user_lang if user_lang != "ua" else "uk"
    entry = _FIELD_LABEL_TRANSLATIONS.get(field_key)
    if entry:
        return entry.get(lang) or entry.get("uk") or ""
    return ""


def _get_section_hint(section_title_de: str, user_lang: str) -> str:
    """Return localized section title for the given language. Empty string if not found."""
    if not user_lang or user_lang in ("de",):
        return ""
    lang = user_lang if user_lang != "ua" else "uk"
    entry = _SECTION_TITLE_TRANSLATIONS.get(section_title_de)
    if entry:
        return entry.get(lang) or entry.get("uk") or ""
    return ""


# Common German form values → localized translations (used in preview letter mode)
_VALUE_TRANS: Dict[str, Dict[str, str]] = {
    "Ja": {"uk": "Так", "en": "Yes", "pl": "Tak", "tr": "Evet", "ar": "نعم"},
    "Nein": {"uk": "Ні", "en": "No", "pl": "Nie", "tr": "Hayır", "ar": "لا"},
    "ja": {"uk": "Так", "en": "Yes", "pl": "Tak", "tr": "Evet", "ar": "نعم"},
    "nein": {"uk": "Ні", "en": "No", "pl": "Nie", "tr": "Hayır", "ar": "لا"},
    "männlich": {
        "de": "männlich",
        "uk": "Чоловіча",
        "en": "Male",
        "pl": "Mężczyzna",
        "tr": "Erkek",
        "ar": "ذكر",
    },
    "weiblich": {
        "de": "weiblich",
        "uk": "Жіноча",
        "en": "Female",
        "pl": "Kobieta",
        "tr": "Kadın",
        "ar": "أنثى",
    },
    "divers": {
        "de": "divers",
        "uk": "Інша",
        "en": "Other",
        "pl": "Inna",
        "tr": "Diğer",
        "ar": "آخر",
    },
    # Single-letter shortcodes from WebApp/DB — expand to full German word
    "m": {
        "de": "männlich",
        "uk": "Чоловіча",
        "en": "Male",
        "pl": "Mężczyzna",
        "tr": "Erkek",
        "ar": "ذكر",
    },
    "w": {
        "de": "weiblich",
        "uk": "Жіноча",
        "en": "Female",
        "pl": "Kobieta",
        "tr": "Kadın",
        "ar": "أنثى",
    },
    "d": {
        "de": "divers",
        "uk": "Інша",
        "en": "Other",
        "pl": "Inna",
        "tr": "Diğer",
        "ar": "آخر",
    },
    "alleinige Wohnung": {
        "uk": "Єдине місце проживання",
        "en": "Sole residence",
        "pl": "Jedyne miejsce zamieszkania",
        "tr": "Tek ikamet",
        "ar": "مكان الإقامة الوحيد",
    },
    "Hauptwohnung": {
        "uk": "Основне місце проживання",
        "en": "Primary residence",
        "pl": "Główne mieszkanie",
        "tr": "Ana ikamet",
        "ar": "مكان الإقامة الرئيسي",
    },
    "Nebenwohnung": {
        "uk": "Додаткове місце проживання",
        "en": "Secondary residence",
        "pl": "Dodatkowe mieszkanie",
        "tr": "İkincil ikamet",
        "ar": "مكان الإقامة الثانوي",
    },
    "PA": {
        "de": "Personalausweis",
        "uk": "Паспорт (PA)",
        "en": "ID card (PA)",
        "pl": "Paszport (PA)",
        "tr": "Pasaport (PA)",
        "ar": "جواز سفر (PA)",
    },
    "RP": {
        "de": "Reisepass",
        "uk": "Посвідка на проживання (RP)",
        "en": "Residence permit (RP)",
        "pl": "Karta pobytu (RP)",
        "tr": "Oturma izni (RP)",
        "ar": "تصريح إقامة (RP)",
    },
    "ledig": {
        "uk": "Неодружений/а",
        "en": "Single",
        "pl": "Kawaler/Panna",
        "tr": "Bekar",
        "ar": "أعزب",
    },
    "verheiratet": {
        "uk": "Одружений/а",
        "en": "Married",
        "pl": "Żonaty/Mężatka",
        "tr": "Evli",
        "ar": "متزوج",
    },
    "geschieden": {
        "uk": "Розлучений/а",
        "en": "Divorced",
        "pl": "Po rozwodzie",
        "tr": "Boşanmış",
        "ar": "مطلق",
    },
    "verwitwet": {
        "uk": "Вдовець/вдова",
        "en": "Widowed",
        "pl": "Wdowiec/Wdowa",
        "tr": "Dul",
        "ar": "أرمل",
    },
}


def _translate_val(value: str, lang: str) -> str:
    """Translate a German form value to user's language (preview letter mode)."""
    # Always expand single-letter gender codes — "m"/"w"/"d" must never appear
    # in any PDF output, regardless of language.
    _GENDER_EXPAND = {"m": "männlich", "w": "weiblich", "d": "divers"}
    if value in _GENDER_EXPAND:
        value = _GENDER_EXPAND[value]
    if not lang or lang == "de":
        return value
    _lang = lang if lang != "ua" else "uk"
    entry = _VALUE_TRANS.get(value)
    if entry:
        return entry.get(_lang) or entry.get("uk") or value
    return value


def _display_val_de(value: str) -> str:
    """Return German display label for a select-field code (e.g. 'RP' → 'Reisepass').
    Used in official/final PDF layout to show human-readable German values."""
    # Explicit gender shortcode expansion — single-letter codes "m"/"w"/"d" must
    # never appear on the final Amt-ready document.
    _GENDER_EXPAND = {"m": "männlich", "w": "weiblich", "d": "divers"}
    if value in _GENDER_EXPAND:
        return _GENDER_EXPAND[value]
    entry = _VALUE_TRANS.get(value)
    if entry and "de" in entry:
        return entry["de"]
    return value


# Localized "not filled" sentinel text for preview letter
_PREVIEW_LETTER_EMPTY: Dict[str, str] = {
    "uk": "⚠ не заповнено",
    "en": "⚠ not filled",
    "de": "⚠ nicht ausgefüllt",
    "pl": "⚠ nie wypełniono",
    "tr": "⚠ doldurulmadı",
    "ar": "⚠ غير مكتمل",
    "ru": "⚠ не заполнено",
}

# Per-field neutral "empty" overrides — shown instead of ⚠ for fields that
# are intentionally left blank or filled by the authority, not the applicant.
_FIELD_EMPTY_OVERRIDE: Dict[str, Dict[str, str]] = {
    "gemeindekennzahl": {
        "uk": "optional – заповнюється Bürgeramt",
        "en": "optional – filled in by Bürgeramt",
        "de": "optional – wird vom Bürgeramt ausgefüllt",
        "pl": "opcjonalne – wypełnia urząd",
        "tr": "isteğe bağlı – Bürgeramt tarafından doldurulur",
        "ar": "اختياري – تملأه الجهة الحكومية",
        "ru": "необязательно – заполняется Bürgeramt",
    },
}

# Preview-only UX reassurance block — tells the user what the system auto-corrects
# when generating the final document. Never shown in final PDFs.
_PREVIEW_REASSURANCE_TEXT: Dict[str, str] = {
    "uk": (
        "\u2139\ufe0f \u0426\u0435 \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u043e\u0447\u043d\u0435 \u043f\u0440\u0435\u0432'\u044e \u0432\u0430\u0448\u0438\u0445 \u0434\u0430\u043d\u0438\u0445.\n\n"
        "\u041f\u0456\u0434 \u0447\u0430\u0441 \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0456\u0457 \u0444\u0456\u043d\u0430\u043b\u044c\u043d\u043e\u0433\u043e PDF \u0441\u0438\u0441\u0442\u0435\u043c\u0430 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u043d\u043e "
        "\u0432\u0456\u0434\u0444\u043e\u0440\u043c\u0430\u0442\u0443\u0454 \u0434\u0430\u0442\u0438, \u0432\u0438\u043f\u0440\u0430\u0432\u043b\u044f\u0454 \u043d\u0430\u043f\u0438\u0441\u0430\u043d\u043d\u044f \u0430\u0434\u0440\u0435\u0441 \u043d\u0456\u043c\u0435\u0446\u044c\u043a\u043e\u044e "
        "\u0442\u0430 \u043d\u043e\u0440\u043c\u0430\u043b\u0456\u0437\u0443\u0454 \u043d\u0430\u0437\u0432\u0438 \u043a\u0440\u0430\u0457\u043d \u0432\u0456\u0434\u043f\u043e\u0432\u0456\u0434\u043d\u043e \u0434\u043e \u0432\u0438\u043c\u043e\u0433 \u0444\u043e\u0440\u043c\u0438.\n\n"
        "\u0411\u0443\u0434\u044c \u043b\u0430\u0441\u043a\u0430, \u043f\u0435\u0440\u0435\u0432\u0456\u0440\u0442\u0435 \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u0456\u0441\u0442\u044c \u0432\u0430\u0448\u0438\u0445 \u0434\u0430\u043d\u0438\u0445 \u043f\u0435\u0440\u0435\u0434 \u0441\u0442\u0432\u043e\u0440\u0435\u043d\u043d\u044f\u043c \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430."
    ),
    "en": (
        "\u2139\ufe0f This is a preview of the data you entered.\n\n"
        "When generating the final PDF, the system automatically formats dates, "
        "corrects German address spelling, and normalizes country names according "
        "to the official form requirements.\n\n"
        "Please review your information before creating the document."
    ),
    "de": (
        "\u2139\ufe0f Dies ist eine Vorschau Ihrer eingegebenen Daten.\n\n"
        "Bei der Erstellung des endg\u00fcltigen PDF-Dokuments werden Datumsformate, "
        "Adressschreibweisen und Staatsangeh\u00f6rigkeiten automatisch an die "
        "Anforderungen des offiziellen Formulars angepasst.\n\n"
        "Bitte \u00fcberpr\u00fcfen Sie Ihre Angaben vor der Dokumenterstellung."
    ),
    "pl": (
        "\u2139\ufe0f To jest podgl\u0105d wprowadzonych danych.\n\n"
        "Podczas generowania ko\u0144cowego dokumentu PDF system automatycznie "
        "sformatuje daty, poprawi pisowni\u0119 adres\u00f3w w j\u0119zyku niemieckim "
        "oraz ujednolici nazwy kraj\u00f3w zgodnie z wymaganiami formularza.\n\n"
        "Przed utworzeniem dokumentu sprawd\u017a poprawno\u015b\u0107 danych."
    ),
    "tr": (
        "\u2139\ufe0f Bu, girdi\u011finiz bilgilerin \u00f6nizlemesidir.\n\n"
        "Nihai PDF olu\u015fturulurken sistem tarihleri otomatik olarak bi\u00e7imlendirir, "
        "Almanca adres yaz\u0131m\u0131n\u0131 d\u00fczeltir ve \u00fclke adlar\u0131n\u0131 "
        "resmi form gereksinimlerine g\u00f6re standart hale getirir.\n\n"
        "L\u00fctfen belgeyi olu\u015fturmadan \u00f6nce bilgilerinizi kontrol edin."
    ),
    "ar": (
        "\u2139\ufe0f \u0647\u0630\u0647 \u0645\u0639\u0627\u064a\u0646\u0629 \u0644\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u062a\u064a \u0623\u062f\u062e\u0644\u062a\u0647\u0627.\n\n"
        "\u0639\u0646\u062f \u0625\u0646\u0634\u0627\u0621 \u0645\u0644\u0641 PDF \u0627\u0644\u0646\u0647\u0627\u0626\u064a\u060c \u064a\u0642\u0648\u0645 \u0627\u0644\u0646\u0638\u0627\u0645 \u062a\u0644\u0642\u0627\u0626\u064a\u064b\u0627 "
        "\u0628\u062a\u0646\u0633\u064a\u0642 \u0627\u0644\u062a\u0648\u0627\u0631\u064a\u062e\u060c \u0648\u062a\u0635\u062d\u064a\u062d \u0643\u062a\u0627\u0628\u0629 \u0627\u0644\u0639\u0646\u0627\u0648\u064a\u0646 \u0628\u0627\u0644\u0623\u0644\u0645\u0627\u0646\u064a\u0629\u060c "
        "\u0648\u062a\u0648\u062d\u064a\u062f \u0623\u0633\u0645\u0627\u0621 \u0627\u0644\u062f\u0648\u0644 \u0648\u0641\u0642\u064b\u0627 \u0644\u0645\u062a\u0637\u0644\u0628\u0627\u062a \u0627\u0644\u0646\u0645\u0648\u0630\u062c \u0627\u0644\u0631\u0633\u0645\u064a.\n\n"
        "\u064a\u0631\u062c\u0649 \u0645\u0631\u0627\u062c\u0639\u0629 \u0628\u064a\u0627\u0646\u0627\u062a\u0643 \u0642\u0628\u0644 \u0625\u0646\u0634\u0627\u0621 \u0627\u0644\u0645\u0633\u062a\u0646\u062f."
    ),
}

# Fields that are optional (not required) — shown with "(optional)" suffix when empty
_OPTIONAL_FIELDS: frozenset = frozenset(
    {
        "apartment_number",
        "gemeindekennzahl",
        "birth_name",
        "religion",
        "phone",
        "email",
        "tax_id",
        "bank_name",
        "bic",
        "account_holder",
        "partner_nationality",
        "partner_last_name",
        "partner_first_name",
        "partner_birth_date",
        "landlord_address",
        "signature_place",
        "signature_date",
        "child_birth_place",
        "child_last_name",
        "child_first_name",
        "child_birth_date",
        "child_nationality",
        "occupation",
        "employer",
        "has_bisherige_wohnung",
        "move_out_date",
        "previous_address",
        "zuzug_aus_ausland",
        "zuzug_staat",
        "bisherige_beibehalten",
        "weitere_wohnungen",
        "passname",
        "ordens_kuenstlername",
        "dwelling_type",
        "living_space_sqm",
        "household_members",
        "monthly_income",
        "income_source",
        "family_status",
        "familienstand",
        "other_income",
        "heating_costs",
        "additional_costs",
        "residence_purpose",
        "visa_type",
        "entry_date",
        "employer_name",
        "employment_start",
    }
)

_OPTIONAL_SUFFIX: Dict[str, str] = {
    "uk": " (необов'язково)",
    "en": " (optional)",
    "de": " (optional)",
    "pl": " (opcjonalne)",
    "tr": " (isteğe bağlı)",
    "ar": " (اختياري)",
    "ru": " (необязательно)",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_value(user_data: Dict[str, Any], *keys: str) -> str:
    """Try multiple key variants; return first non-empty string found."""
    for k in keys:
        v = user_data.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _get_field_value(user_data: Dict[str, Any], field_key: str) -> str:
    """
    Resolve a field value from user_data using ANSWER_KEY_ALIASES if available.

    Always returns a string (empty string on any failure).
    New schema fields not yet in ANSWER_KEY_ALIASES are looked up by their
    exact key — never crash, never raise.
    """
    try:
        from backend.document_config import ANSWER_KEY_ALIASES

        aliases = ANSWER_KEY_ALIASES.get(field_key, [])
        # Try: exact key first, then all alias variants
        return _get_value(user_data, field_key, *aliases)
    except Exception:
        # Defensive: any import or lookup error → fall back to direct key lookup
        try:
            return _get_value(user_data, field_key)
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Display-time normalizations (form_builder only — not persisted to DB)
# ---------------------------------------------------------------------------

_CITY_CORRECTIONS: Dict[str, str] = {
    # Ukraine
    # Vinnytsia — EN/UK/DE variants
    "vinnitsia": "Vinnytsia",
    "vinnytsia": "Vinnytsia",
    "vinnytsya": "Vinnytsia",
    "vinnitsa": "Vinnytsia",
    "vinnitza": "Vinnytsia",
    "winniza": "Vinnytsia",
    "vynnytsia": "Vinnytsia",
    "winnyzja": "Vinnytsia",  # DE
    "winnyzia": "Vinnytsia",  # DE variant
    "vinnytsi": "Vinnytsia",  # truncated input (missing trailing 'a')
    # Kyiv — EN/UK/DE variants
    "kiev": "Kyiv",
    "kyiv": "Kyiv",
    "kiyv": "Kyiv",
    "kyjiv": "Kyiv",
    "kijew": "Kyiv",  # DE
    "kiew": "Kyiv",  # DE short form
    # Lviv — EN/UK/DE variants
    "lvov": "Lviv",
    "lviv": "Lviv",
    "lemberg": "Lviv",  # DE historical
    "lwow": "Lviv",  # DE/PL
    "lwiw": "Lviv",  # DE
    # Kharkiv — EN/UK/DE variants
    "kharkov": "Kharkiv",
    "kharkoiv": "Kharkiv",
    "kharkiv": "Kharkiv",
    "charkow": "Kharkiv",  # DE
    "charkov": "Kharkiv",  # DE variant
    # Odesa — EN/UK/DE variants
    "odessa": "Odesa",
    "odesa": "Odesa",
    # Dnipro — EN/UK/DE variants
    "dnepropetrovsk": "Dnipro",
    "dnipropetrovsk": "Dnipro",
    "dniepropetrovsk": "Dnipro",
    "dnipro": "Dnipro",
    "dnepr": "Dnipro",  # DE/RU short form
    "dnjepr": "Dnipro",  # DE
    "dnipropetrowsk": "Dnipro",  # DE
    # Donetsk
    "donetsk": "Donetsk",
    "donezk": "Donetsk",  # DE
    # Zaporizhzhia — EN/UK/DE variants
    "zaporizhzhia": "Zaporizhzhia",
    "zaporizhia": "Zaporizhzhia",
    "zaporozhe": "Zaporizhzhia",
    "zaporozhye": "Zaporizhzhia",
    "zaporozhie": "Zaporizhzhia",
    "zaporischje": "Zaporizhzhia",  # DE
    "saporischja": "Zaporizhzhia",  # DE variant
    "saporoschje": "Zaporizhzhia",  # DE variant
    # Poltava
    "poltava": "Poltava",
    "poltawa": "Poltava",  # DE
    # Sumy
    "sumy": "Sumy",
    # Cherkasy
    "cherkasy": "Cherkasy",
    "tscherkassy": "Cherkasy",  # DE
    # Chernihiv — EN/UK/DE variants
    "chernihiv": "Chernihiv",
    "tschernihiw": "Chernihiv",  # DE
    "tschernigov": "Chernihiv",  # DE/RU
    # Chernivtsi — EN/UK/DE variants
    "chernivtsi": "Chernivtsi",
    "chernovtsy": "Chernivtsi",
    "chernovtsi": "Chernivtsi",
    "chernowitz": "Chernivtsi",
    "czernowitz": "Chernivtsi",  # DE historical
    "tscherniwzi": "Chernivtsi",  # DE
    # Ternopil — EN/UK/DE variants
    "ternopil": "Ternopil",
    "ternopol": "Ternopil",
    "ternopol'": "Ternopil",
    "ternopilj": "Ternopil",
    "tarnopol": "Ternopil",  # DE historical
    # Zhytomyr — EN/UK/DE variants
    "zhytomyr": "Zhytomyr",
    "shytomyr": "Zhytomyr",
    "schitomir": "Zhytomyr",  # DE
    "schytomyr": "Zhytomyr",  # DE variant
    # Ivano-Frankivsk — EN/UK/DE variants
    "ivanofrankivsk": "Ivano-Frankivsk",
    "ivano-frankivsk": "Ivano-Frankivsk",
    "iwano-frankiwsk": "Ivano-Frankivsk",  # DE
    "stanislau": "Ivano-Frankivsk",  # DE historical
    # Uzhhorod — EN/UK/DE variants
    "uzhhorod": "Uzhhorod",
    "uschhorod": "Uzhhorod",  # DE
    "ungwar": "Uzhhorod",  # DE historical
    # Mykolaiv — EN/UK/DE variants
    "mykolaiv": "Mykolaiv",
    "nikolaev": "Mykolaiv",
    "mykolajiv": "Mykolaiv",
    "mykolaiw": "Mykolaiv",  # DE
    "nikolajew": "Mykolaiv",  # DE
    # Khmelnytskyi — EN/UK/DE variants
    "khmelnytskyi": "Khmelnytskyi",
    "khmelnitsky": "Khmelnytskyi",
    "chmelnyzkyj": "Khmelnytskyi",  # DE
    "khmelnitskyi": "Khmelnytskyi",
    # Kherson — EN/UK/DE variants
    "kherson": "Kherson",
    "cherson": "Kherson",  # DE
    # Rivne — EN/UK/DE variants
    "rivne": "Rivne",
    "rowno": "Rivne",  # DE/PL
    "riwne": "Rivne",  # DE
    # Lutsk
    "lutsk": "Lutsk",
    "luzk": "Lutsk",  # DE
    # Kropyvnytskyi
    "kropyvnytskyi": "Kropyvnytskyi",
    "kirovograd": "Kropyvnytskyi",
    "kirowohrad": "Kropyvnytskyi",  # DE
    # Turkey — common cities (Latin forms after Turkish-char normalization)
    "istanbul": "Istanbul",
    "ankara": "Ankara",
    "izmir": "Izmir",
    "bursa": "Bursa",
    "adana": "Adana",
    "gaziantep": "Gaziantep",
    "konya": "Konya",
    "antalya": "Antalya",
    "kayseri": "Kayseri",
    "mersin": "Mersin",
    "diyarbakir": "Diyarbakir",
    "sanliurfa": "Sanliurfa",
    "sanlurfa": "Sanliurfa",
    "urfa": "Sanliurfa",
    "trabzon": "Trabzon",
    "erzurum": "Erzurum",
    "malatya": "Malatya",
    "samsun": "Samsun",
    "eskisehir": "Eskisehir",
    "hatay": "Hatay",
    # Poland — normalize spelling variants only (no translation to historical German names)
    "warsaw": "Warsaw",
    "warszawa": "Warsaw",
    "krakow": "Krakow",
    "kraków": "Krakow",
    "wroclaw": "Wroclaw",
    "wrocław": "Wroclaw",
    "gdansk": "Gdansk",
    "gdańsk": "Gdansk",
    "gdynia": "Gdynia",
    "poznan": "Poznan",
    "poznań": "Poznan",
    "lodz": "Lodz",
    "łódź": "Lodz",
    "lublin": "Lublin",
    "bialystok": "Bialystok",
    "białystok": "Bialystok",
    "szczecin": "Szczecin",
    "katowice": "Katowice",
    "rzeszow": "Rzeszow",
    "rzeszów": "Rzeszow",
    # Arabic-speaking countries — normalize spelling variants only
    # (keep internationally recognized English spellings, not German translations)
    "cairo": "Cairo",
    "kairo": "Cairo",
    "baghdad": "Baghdad",
    "bagdad": "Baghdad",
    "damascus": "Damascus",
    "damaskus": "Damascus",
    "aleppo": "Aleppo",
    "haleb": "Aleppo",
    "beirut": "Beirut",
    "beyrouth": "Beirut",
    "amman": "Amman",
    "riyadh": "Riyadh",
    "riad": "Riyadh",
    "dubai": "Dubai",
    "abu dhabi": "Abu Dhabi",
    "abudhabi": "Abu Dhabi",
    "tehran": "Tehran",
    "teheran": "Tehran",
    "kabul": "Kabul",
    "tripoli": "Tripoli",
    "tripolis": "Tripoli",
    "tunis": "Tunis",
    "rabat": "Rabat",
    "casablanca": "Casablanca",
    "algiers": "Algiers",
    "algier": "Algiers",
    # Russia / Belarus (common forms)
    "moskva": "Moskau",
    "moscow": "Moskau",
    "moskau": "Moskau",
    "sankt peterburg": "Sankt Petersburg",
    "saint petersburg": "Sankt Petersburg",
    "st. petersburg": "Sankt Petersburg",
    "st petersburg": "Sankt Petersburg",
    "leningrad": "Sankt Petersburg",
    "minsk": "Minsk",
}


def _normalize_city_name(city: str) -> str:
    """Correct common transliteration variants to their preferred English/German spelling."""
    if not city:
        return city
    key = city.strip().lower()
    return _CITY_CORRECTIONS.get(key, city.strip())


# Known country-name suffix variants → canonical English/German spelling.
# Applied to the trailing token of composite place strings (e.g. "Vinnytsia Ukraina").
_COUNTRY_SUFFIX_CORRECTIONS: Dict[str, str] = {
    "ukraina": "Ukraine",  # Polish / Slovak / Czech / Croatian
    "ukrayna": "Ukraine",  # Turkish
    "ukrainie": "Ukraine",  # rare variant
    "ukrainaa": "Ukraine",  # double-letter typo
    "ukrainaq": "Ukraine",  # accidental extra key
    "ukrain": "Ukraine",  # truncated form
}

# Punctuation stripped from suffix tokens before country-suffix matching.
_SUFFIX_STRIP_CHARS = ".,;:!?"


def _normalize_city_composite(value: str) -> str:
    """
    Normalize the leading city token in a composite string.

    Handles both comma-separated and space-separated formats:
      "Vinnitsia"          → "Vinnytsia"
      "Vinnitsia, Ukraine" → "Vinnytsia, Ukraine"
      "Vinnitsia Ukraine"  → "Vinnytsia Ukraine"
      "Vinnitsia RAGS"     → "Vinnytsia RAGS"

    Strategy:
    1. If a comma is present, split there — city is unambiguously the first part.
    2. Otherwise try progressively longer space-separated prefixes (longest first)
       against _CITY_CORRECTIONS.
    3. If a match is found, replace only that prefix and keep the rest unchanged.
    4. If no prefix matches, return the original string unchanged.
    """
    if not value:
        return value
    val = value.strip()

    # Case 1: comma separator
    if "," in val:
        left, right = val.split(",", 1)
        left = _normalize_city_name(left.strip())
        return f"{left}, {right.strip()}"

    # Case 2: space-separated — longest-prefix match
    parts = val.split()
    for i in range(len(parts), 0, -1):
        candidate = " ".join(parts[:i]).lower()
        if candidate in _CITY_CORRECTIONS:
            normalized = _CITY_CORRECTIONS[candidate]
            remainder = " ".join(parts[i:])
            # Normalize known country-suffix variants in the remainder.
            # Strip trailing punctuation before matching to handle "Ukraina." etc.
            remainder_key = remainder.strip().rstrip(_SUFFIX_STRIP_CHARS).lower()
            remainder = _COUNTRY_SUFFIX_CORRECTIONS.get(remainder_key, remainder)
            return f"{normalized} {remainder}".strip()

    # No known city prefix — still normalize a trailing country-suffix if present
    if len(parts) >= 2:
        # Strip trailing punctuation before matching to handle "Ukraina." etc.
        suffix = parts[-1].strip().rstrip(_SUFFIX_STRIP_CHARS).lower()
        if suffix in _COUNTRY_SUFFIX_CORRECTIONS:
            city_part = " ".join(parts[:-1])
            return f"{city_part} {_COUNTRY_SUFFIX_CORRECTIONS[suffix]}".strip()

    return val  # no known city prefix — leave unchanged


# Adjective → country noun mapping for Staatsangehörigkeit display
_NATIONALITY_TO_COUNTRY: Dict[str, str] = {
    "ukrainisch": "Ukraine",
    "ukraina": "Ukraine",  # Polish/Slovak spelling
    "deutsch": "Deutschland",
    "österreichisch": "Österreich",
    "schweizerisch": "Schweiz",
    "polnisch": "Polen",
    "russisch": "Russland",
    "weißrussisch": "Belarus",
    "belarussisch": "Belarus",
    "türkisch": "Türkei",
    "arabisch": "Arabische Länder",
    "syrisch": "Syrien",
    "irakisch": "Irak",
    "iranisch": "Iran",
    "afghanisch": "Afghanistan",
    "pakistanisch": "Pakistan",
    "indisch": "Indien",
    "chinesisch": "China",
    "amerikanisch": "USA",
    "britisch": "Großbritannien",
    "französisch": "Frankreich",
    "italienisch": "Italien",
    "spanisch": "Spanien",
    "portugiesisch": "Portugal",
    "rumänisch": "Rumänien",
    "bulgarisch": "Bulgarien",
    "ungarisch": "Ungarn",
    "tschechisch": "Tschechien",
    "slowakisch": "Slowakei",
    "kroatisch": "Kroatien",
    "serbisch": "Serbien",
    "griechisch": "Griechenland",
    "niederländisch": "Niederlande",
    "belgisch": "Belgien",
    "schwedisch": "Schweden",
    "norwegisch": "Norwegen",
    "dänisch": "Dänemark",
    "finnisch": "Finnland",
    "litauisch": "Litauen",
    "lettisch": "Lettland",
    "estnisch": "Estland",
    "kasachisch": "Kasachstan",
    "georgisch": "Georgien",
    "armenisch": "Armenien",
    "aserbaidschanisch": "Aserbaidschan",
    "moldauisch": "Moldau",
    "albanisch": "Albanien",
    "mazedonisch": "Nordmazedonien",
    "bosnisch": "Bosnien und Herzegowina",
    "montenegrinisch": "Montenegro",
    "kosovarisch": "Kosovo",
    "israelisch": "Israel",
    "libanesisch": "Libanon",
    "jordanisch": "Jordanien",
    "ägyptisch": "Ägypten",
    "marokkanisch": "Marokko",
    "tunesisch": "Tunesien",
    "algerisch": "Algerien",
    "äthiopisch": "Äthiopien",
    "somalisch": "Somalia",
    "eritreisch": "Eritrea",
    "ghanaisch": "Ghana",
    "nigerianisch": "Nigeria",
    "kongolesisch": "DR Kongo",
    "kamerunisch": "Kamerun",
    "kenianisch": "Kenia",
    "brasilianisch": "Brasilien",
    "mexikanisch": "Mexiko",
    "kolumbianisch": "Kolumbien",
    "venezuelanisch": "Venezuela",
    "peruanisch": "Peru",
    "chilenisch": "Chile",
    "argentinisch": "Argentinien",
    "japanisch": "Japan",
    "koreanisch": "Südkorea",
    "vietnamesisch": "Vietnam",
    "philippinisch": "Philippinen",
    "indonesisch": "Indonesien",
    "thailändisch": "Thailand",
}

# These keys contain city names that should be normalized
_CITY_FIELD_KEYS: frozenset = frozenset(
    {
        "birth_place",
        "person2_birth_place",
        "person3_birth_place",
        "person4_birth_place",
        "person5_birth_place",
        "child_birth_place",
        "ve_gast_gebort",
        "eheschliessung_ort_datum",  # city appears at the start — handle partially
        "previous_ort",
    }
)

# In builder PDF display, these fields should show city only (without ", Country")
_BIRTH_PLACE_CITY_ONLY_KEYS: frozenset = frozenset(
    {
        "birth_place",
        "place_of_birth",
    }
)

# These keys contain nationality (adjective) that should be converted to country noun
_NATIONALITY_FIELD_KEYS: frozenset = frozenset(
    {
        "nationality",
        "person2_nationality",
        "person3_nationality",
        "person4_nationality",
        "person5_nationality",
        "child_nationality",
        "partner_nationality",
        "ve_gast_staat",
    }
)

# These keys contain German street names that may need ß normalization
_STREET_FIELD_KEYS: frozenset = frozenset(
    {
        "street",
        "previous_strasse",
        "new_street",
        "landlord_street",
        "be_strasse",
        "person2_street",
        "person3_street",
        "person4_street",
        "person5_street",
    }
)

# Issuing authority for Ukrainian passports / travel documents (German name for official forms)
_UKRAINE_ISSUER = "Staatlicher Migrationsdienst der Ukraine"


def _normalize_street_name(street: str) -> str:
    """Normalize common German street-name misspellings (missing ß) at render time.

    Only affects the display value — database records are not modified.
    """
    if not street:
        return street
    _REPLACEMENTS = (
        ("Strasse", "Straße"),
        ("strasse", "straße"),
        ("Strase", "Straße"),
        ("strase", "straße"),
    )
    for wrong, correct in _REPLACEMENTS:
        street = street.replace(wrong, correct)
    return street


def _format_marriage_place_date_for_pdf(value: str) -> str:
    """
    Builder-display formatter for eheschliessung_ort_datum.
    Accepts:
      - "City DD.MM.YYYY"            → "City, DD.MM.YYYY"
      - "City, DD.MM.YYYY"           → "City, DD.MM.YYYY"  (no change)
      - "City,, DD.MM.YYYY"          → "City, DD.MM.YYYY"  (double-comma collapse)
      - "City, DD.MM.YYYY City, …"   → "City, DD.MM.YYYY"  (deduplication)

    Always returns a canonical "City, DD.MM.YYYY" string.
    """
    if not value:
        return value
    s = str(value).strip()
    import re

    # Strip any pipe-separated duplicate suffix: "City, DD.MM.YYYY | City, DD.MM.YYYY"
    # → "City, DD.MM.YYYY".  The pipe character "|" is not a valid character in a
    # German place-date string, so everything from the first "|" onwards is noise.
    s = re.sub(r"\s*\|.*$", "", s).strip()
    # Primary pattern: non-greedy city-letters + one-or-more commas + date.
    # NOT anchored at $ so any duplicated suffix after the first valid date is ignored.
    # `[^,\d]+?` ensures city part contains no commas and no digits (clean city name).
    m = re.match(r"^\s*([^,\d][^,]*?)\s*,+\s*(\d{2}\.\d{2}\.\d{4})", s)
    if m:
        city = m.group(1).strip().rstrip(",").strip()
        date_str = m.group(2).strip()
        if city:
            try:
                datetime.strptime(date_str, "%d.%m.%Y")
                return f"{city}, {date_str}"
            except Exception:
                pass

    # Fallback: space-separated "City DD.MM.YYYY" (no comma)
    m2 = re.match(r"^\s*(.+?)\s+(\d{2}\.\d{2}\.\d{4})\s*", s)
    if m2:
        city = m2.group(1).strip()
        date_str = m2.group(2).strip()
        if city:
            try:
                datetime.strptime(date_str, "%d.%m.%Y")
                return f"{city}, {date_str}"
            except Exception:
                pass

    return s


def _resolve_field_for_display(
    user_data: Dict[str, Any],
    field_key: str,
) -> str:
    """
    Resolve a field value with display-time normalizations applied:

    • city fields      — correct transliteration via _normalize_city_name()
    • nationality keys — convert German adjective to country noun
    • apartment_number — prefix "Whg. " when non-empty
    • ausstellungsbehoerde — auto-fill "Staatlicher Migrationsdienst der Ukraine"
                             if country is Ukraine and field is empty
    • signature_date   — fall back to today's date if empty
    """
    val = _get_field_value(user_data, field_key)

    # ── apartment_number: prefix Whg. ───────────────────────────────────────
    if field_key == "apartment_number" and val:
        if not val.lower().startswith("whg"):
            val = f"Whg. {val}"
        return val

    # ── signature_date: always use generation date (dynamic, not user-entered) ──
    if field_key == "signature_date":
        _user_date = _get_field_value(user_data, field_key)
        return _user_date if _user_date else datetime.now().strftime("%d.%m.%Y")

    # ── ausstellungsbehoerde: auto-fill / normalize ─────────────────────────
    if field_key == "ausstellungsbehoerde":
        if not val:
            nat = (
                (
                    user_data.get("nationality")
                    or user_data.get("staatsangehoerigkeiten")
                    or ""
                )
                .strip()
                .lower()
            )
            country = (user_data.get("birth_country") or "").strip().lower()
            if (
                "ukrain" in nat
                or "ukraine" in country
                or nat in ("ukrainisch", "ukraine")
            ):
                return _UKRAINE_ISSUER
        else:
            # Normalize Ukrainian civil registry abbreviations (e.g. "Vinnitsia RAGS",
            # "Kyiv ZAGS") to standard German-form value.
            _val_up = val.upper()
            if (
                "RAGS" in _val_up
                or "ZAGS" in _val_up
                or "РАЦС" in val
                or "ДРАЦС" in val
            ):
                return _UKRAINE_ISSUER

    # ── nationality: always use German adjective form ───────────────────────
    # All documents (builder + AcroForm) must be consistent: "ukrainisch", not "Ukraine".
    if field_key in _NATIONALITY_FIELD_KEYS and val:
        if callable(_norm_nationality):
            val = _norm_nationality(val)
        else:
            val = val.capitalize()

    # ── city fields: transliteration fix ────────────────────────────────────
    if field_key in _CITY_FIELD_KEYS and val:
        val = _normalize_city_composite(val)

    # ── marriage place/date: canonical PDF format ───────────────────────────
    if field_key == "eheschliessung_ort_datum" and val:
        val = _format_marriage_place_date_for_pdf(val)

    # ── birth place display: keep only city part (builder PDFs only) ───────
    # Example: "Vinnytsia, Ukraine" -> "Vinnytsia"
    if field_key in _BIRTH_PLACE_CITY_ONLY_KEYS and val and "," in val:
        val = val.split(",", 1)[0].strip()

    # ── street fields: ß normalization ──────────────────────────────────────
    if field_key in _STREET_FIELD_KEYS and val:
        val = _normalize_street_name(val)

    return val


def _make_styles() -> Dict[str, ParagraphStyle]:
    # Use DejaVuSans if registered (supports Cyrillic/Arabic/German), else fall back to Helvetica
    _reg = pdfmetrics.getRegisteredFontNames()
    _f = "DejaVuSans" if "DejaVuSans" in _reg else "Helvetica"
    _fb = "DejaVuSans-Bold" if "DejaVuSans-Bold" in _reg else "Helvetica-Bold"

    styles: Dict[str, ParagraphStyle] = {}
    styles["form_title"] = ParagraphStyle(
        "form_title",
        fontName=_fb,
        fontSize=14,
        leading=17,
        textColor=white,
        alignment=TA_LEFT,
    )
    styles["legal_basis"] = ParagraphStyle(
        "legal_basis",
        fontName=_f,
        fontSize=8,
        leading=10,
        textColor=HexColor("#ccddee"),
        alignment=TA_LEFT,
    )
    styles["section"] = ParagraphStyle(
        "section",
        fontName=_fb,
        fontSize=9,
        leading=11,
        textColor=_BLACK,
        leftIndent=2 * mm,
        spaceAfter=0,
    )
    styles["field_label"] = ParagraphStyle(
        "field_label",
        fontName=_f,
        fontSize=8,
        leading=10,
        textColor=_GREY_LABEL,
    )
    styles["field_value"] = ParagraphStyle(
        "field_value",
        fontName=_fb,
        fontSize=9,
        leading=11,
        textColor=_BLACK,
    )
    styles["footer"] = ParagraphStyle(
        "footer",
        fontName=_f,
        fontSize=7,
        leading=9,
        textColor=HexColor("#888888"),
        alignment=TA_CENTER,
    )
    styles["checklist_title"] = ParagraphStyle(
        "checklist_title",
        fontName=_fb,
        fontSize=9,
        leading=12,
        textColor=HexColor("#003366"),
        spaceAfter=2,
    )
    styles["checklist_ok"] = ParagraphStyle(
        "checklist_ok",
        fontName=_f,
        fontSize=8,
        leading=11,
        textColor=HexColor("#228822"),
        leftIndent=4 * mm,
    )
    styles["checklist_missing"] = ParagraphStyle(
        "checklist_missing",
        fontName=_fb,
        fontSize=8,
        leading=11,
        textColor=HexColor("#cc2200"),
        leftIndent=4 * mm,
    )
    styles["checklist_warn"] = ParagraphStyle(
        "checklist_warn",
        fontName=_f,
        fontSize=8,
        leading=11,
        textColor=HexColor("#996600"),
        leftIndent=4 * mm,
    )
    styles["official_link"] = ParagraphStyle(
        "official_link",
        fontName=_f,
        fontSize=7,
        leading=9,
        textColor=HexColor("#003399"),
        alignment=TA_CENTER,
    )
    styles["field_label_hint"] = ParagraphStyle(
        "field_label_hint",
        fontName=_f,
        fontSize=7,
        leading=9,
        textColor=HexColor("#8899bb"),
        spaceAfter=0,
        spaceBefore=0,
    )
    styles["section_hint"] = ParagraphStyle(
        "section_hint",
        fontName=_f,
        fontSize=7,
        leading=9,
        textColor=HexColor("#6677aa"),
        leftIndent=2 * mm,
    )
    # ── Preview-letter styles (is_preview=True, non-DE language) ──────────────
    styles["pl_label"] = ParagraphStyle(
        "pl_label",
        fontName=_fb,
        fontSize=9,
        leading=11,
        textColor=HexColor("#1a1a3e"),
    )
    styles["pl_label_de"] = ParagraphStyle(
        "pl_label_de",
        fontName=_f,
        fontSize=7,
        leading=9,
        textColor=HexColor("#888899"),
        spaceBefore=0,
    )
    styles["pl_value"] = ParagraphStyle(
        "pl_value",
        fontName=_fb,
        fontSize=9,
        leading=11,
        textColor=HexColor("#111111"),
    )
    styles["pl_empty"] = ParagraphStyle(
        "pl_empty",
        fontName=_f,
        fontSize=8,
        leading=10,
        textColor=HexColor("#cc5500"),
        fontStyle="italic" if False else "normal",  # reportlab uses fontName for italic
    )
    styles["pl_sec_title"] = ParagraphStyle(
        "pl_sec_title",
        fontName=_fb,
        fontSize=10,
        leading=13,
        textColor=HexColor("#003366"),
    )
    styles["pl_sec_de"] = ParagraphStyle(
        "pl_sec_de",
        fontName=_f,
        fontSize=7,
        leading=9,
        textColor=HexColor("#8899aa"),
    )
    return styles


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


class _FormBuilder:
    """Builds a single German government form PDF with ReportLab Platypus."""

    def __init__(
        self,
        doc_type: str,
        user_data: Dict[str, Any],
        output_path: str,
        is_preview: bool = False,
        user_lang: str = "de",
        missing_fields: Optional[List[Dict[str, str]]] = None,
        warnings: Optional[List[Dict[str, str]]] = None,
        official_link: str = "",
    ):
        self.doc_type = doc_type.lower().strip()
        self.user_data = self._preprocess_user_data(doc_type.lower().strip(), user_data)
        self.output_path = str(output_path)
        self.is_preview = is_preview
        self.user_lang = user_lang
        self.missing_fields = missing_fields or []
        self.warnings = warnings or []
        self.official_link = official_link
        self.meta = _DOC_META.get(self.doc_type, ("Formular", "", "Behörde"))
        self.sections = _DOC_SECTIONS.get(self.doc_type, [])
        if self.doc_type == "kindergeld":
            _pkeys = {
                "partner_last_name",
                "partner_first_name",
                "partner_birth_date",
                "partner_nationality",
            }
            _hp = str(self.user_data.get("has_partner", "") or "").strip().lower()
            if _hp != "ja" and not any(
                str(self.user_data.get(k) or "").strip() for k in _pkeys
            ):
                self.sections = [
                    s for s in self.sections if not any(k in _pkeys for k, _ in s[1])
                ]
        self.styles = _make_styles()

    @staticmethod
    def _preprocess_user_data(
        doc_type: str, user_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply doc-type-specific normalization before any rendering."""
        if doc_type == "anmeldung":
            try:
                from backend.utils.normalize import normalize_anmeldung_data

                user_data = normalize_anmeldung_data(user_data)
            except Exception as _e:
                logger.debug("anmeldung preprocess failed (non-fatal): %s", _e)
        return user_data

    # ------------------------------------------------------------------
    # Keys in "Bisherige Wohnung" that must be suppressed when the user
    # answered "Nein" to has_bisherige_wohnung.
    _BISHERIGE_DETAIL_KEYS: frozenset = frozenset(
        {
            "move_out_date",
            "previous_strasse",
            "previous_hausnummer",
            "previous_plz",
            "previous_ort",
            "previous_address",
            "bisherige_beibehalten",
            "bisherige_wohnungstyp",
        }
    )

    def _get_preview_fields_for_section(self, sec_title: str, fields: list) -> list:
        """
        Return the (key, label, value) rows to render for a section in preview mode.

        Rules:
        1. If has_bisherige_wohnung == "Nein" (or is empty/absent), suppress all
           previous-address detail fields — show only the has_bisherige_wohnung row.
        2. Required fields without a value are included (shown as "⚠ not filled").
        3. Optional fields without a value are EXCLUDED entirely — never show
           "— not filled" for optional fields.
        4. Deduplicate by key: the first occurrence wins (prevents postal_code /
           plz double-printing when both keys map to the same value).
        """
        has_bisherige = (
            str(self.user_data.get("has_bisherige_wohnung", "") or "").strip().lower()
        )
        bisherige_is_nein = has_bisherige in ("nein", "no", "ні", "не", "")

        seen_keys: set = set()
        result = []

        for k, lbl in fields:
            # Skip if we already rendered this key (deduplication)
            if k in seen_keys:
                continue

            # Suppress previous-address detail rows when bisherige == Nein
            if bisherige_is_nein and k in self._BISHERIGE_DETAIL_KEYS:
                continue

            val = _resolve_field_for_display(self.user_data, k)
            if self.doc_type == "kindergeld":
                if k == "street":
                    _hn = str(self.user_data.get("house_number") or "").strip()
                    if _hn and val:
                        val = f"{val} {_hn}"
                elif k == "birth_place":
                    val = str(self.user_data.get("birth_place") or val)

            # Skip empty optional fields — never show "not filled" for optional
            if (not val or not str(val).strip()) and k in _OPTIONAL_FIELDS:
                continue

            seen_keys.add(k)
            result.append((k, lbl, val))

        # Drop section entirely if every remaining row is empty AND optional
        # (i.e. all required rows are also empty — section has no signal at all)
        if not result:
            return []
        # Keep section if at least one row has a value OR is a required field
        if not any(val for _, _, val in result):
            # All rows are empty required fields — still show section so user
            # knows they need to fill them
            pass

        return result

    # ------------------------------------------------------------------
    def build(self) -> Optional[str]:
        try:
            buf = BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=A4,
                leftMargin=_MARGIN,
                rightMargin=_MARGIN,
                topMargin=_MARGIN,
                bottomMargin=_MARGIN + 10 * mm,
                title=self.meta[0],
                author="GermanDocBot",
            )
            story = []
            story.extend(self._build_header())
            story.append(Spacer(1, 4 * mm))

            # Preview: cover banner + optional deadline reminder (before fields)
            if self.is_preview:
                story.extend(self._build_preview_cover())
                if self.doc_type == "anmeldung":
                    story.extend(self._build_deadline_reminder())

            # Field sections (all modes)
            for sec_title, fields in self.sections:
                if self.is_preview:
                    section_fields = self._get_preview_fields_for_section(
                        sec_title, fields
                    )
                    if not section_fields:
                        continue
                else:
                    # Official mode: resolve + deduplicate by key (first occurrence wins)
                    _seen_keys: set = set()
                    section_fields = []
                    for k, lbl in fields:
                        if k in _seen_keys:
                            continue
                        _seen_keys.add(k)
                        v = _resolve_field_for_display(self.user_data, k)
                        if self.doc_type == "kindergeld":
                            if k == "street":
                                _hn = str(
                                    self.user_data.get("house_number") or ""
                                ).strip()
                                if _hn and v:
                                    v = f"{v} {_hn}"
                            elif k == "birth_place":
                                v = str(self.user_data.get("birth_place") or v)
                        if v:
                            section_fields.append((k, lbl, v))
                    if not section_fields:
                        continue
                _sec_elems = self._build_section(sec_title, section_fields)
                _sec_elems.append(Spacer(1, 2 * mm))
                story.append(KeepTogether(_sec_elems))

            # Preview: self-check AFTER fields (user sees data first, then assessment)
            if self.is_preview:
                story.append(Spacer(1, 3 * mm))
                story.extend(self._build_selfcheck_block())
                story.extend(self._build_next_steps())
                story.extend(self._build_preview_reassurance())

            story.extend(self._build_footer())

            doc.build(
                story,
                onFirstPage=self._draw_background,
                onLaterPages=self._draw_background,
            )

            pdf_bytes = buf.getvalue()
            if self.is_preview:
                pdf_bytes = self._apply_watermark(pdf_bytes)
            else:
                # Final PDF: stamp a subtle "KOPIE" disclaimer so document
                # cannot be mistaken for an officially submitted original.
                pdf_bytes = self._apply_kopie_watermark(pdf_bytes)

            with open(self.output_path, "wb") as f:
                f.write(pdf_bytes)

            # Post-save integrity check: file must exist, be non-empty, have pages
            if not self._verify_integrity():
                return None

            logger.info(
                "✅ german_form_builder: %s → %s", self.doc_type, self.output_path
            )
            return self.output_path
        except Exception as exc:
            logger.error(
                "❌ german_form_builder failed: %s | %s",
                self.doc_type,
                exc,
                exc_info=True,
            )
            return None

    def _verify_integrity(self) -> bool:
        """Verify the saved PDF is non-empty and has at least one page."""
        from pathlib import Path as _Path

        p = _Path(self.output_path)
        if not p.exists() or p.stat().st_size == 0:
            logger.error(
                "PDF_INTEGRITY_FAIL: builder output missing or empty doc_type=%s path=%s",
                self.doc_type,
                self.output_path,
            )
            return False
        try:
            import fitz as _fitz

            doc = _fitz.open(self.output_path)
            pages = len(doc)
            doc.close()
            if pages == 0:
                logger.error(
                    "PDF_INTEGRITY_FAIL: builder output has 0 pages doc_type=%s path=%s",
                    self.doc_type,
                    self.output_path,
                )
                return False
            logger.debug(
                "PDF_INTEGRITY_OK: builder doc_type=%s pages=%d path=%s",
                self.doc_type,
                pages,
                self.output_path,
            )
            return True
        except ImportError:
            return True  # PyMuPDF not available; skip check
        except Exception as e:
            logger.error(
                "PDF_INTEGRITY_FAIL: builder verification error doc_type=%s path=%s: %s",
                self.doc_type,
                self.output_path,
                e,
            )
            return False

    # ------------------------------------------------------------------
    def _draw_background(self, canv: canvas.Canvas, doc) -> None:
        """Draw the blue header strip on every page."""
        canv.saveState()
        canv.setFillColor(_BLUE_HEADER)
        canv.rect(0, _PAGE_H - 38 * mm, _PAGE_W, 38 * mm, fill=1, stroke=0)
        canv.restoreState()

    # ------------------------------------------------------------------
    def _build_header(self) -> list:
        form_title, legal_basis, authority = self.meta
        title_para = Paragraph(form_title, self.styles["form_title"])
        basis_para = Paragraph(
            f"{legal_basis}  ·  {authority}",
            self.styles["legal_basis"],
        )
        # Spacer to push text into the blue strip (drawn via canvas)
        return [
            Spacer(1, 12 * mm),
            title_para,
            Spacer(1, 2 * mm),
            basis_para,
            Spacer(1, 8 * mm),
        ]

    # ------------------------------------------------------------------
    def _build_section(self, title: str, fields: list) -> list:
        """Build one section: header row + field table.

        Two rendering modes:
        • is_preview=True + non-DE language → "Verification Letter" layout:
            - Section header shows localized title (large) / German title (small, gray)
            - Each row: localized label (bold, primary) / German label (small gray)
              + value (bold) OR "⚠ not filled" (orange) for empty fields
        • is_preview=False OR DE language → official form layout (German labels primary)
        """
        elems = []
        lang = (self.user_lang or "de").lower()
        # aufenthaltstitel is builder-only (no AcroForm template), so even the
        # final PDF should use the letter layout for non-DE users so that field
        # labels appear in the user's language alongside the German reference.
        # Other doc types retain the original behaviour unchanged.
        use_letter_layout = lang not in ("de",) and (
            self.is_preview or self.doc_type == "aufenthaltstitel"
        )

        # ── Section header ────────────────────────────────────────────────────
        if use_letter_layout:
            loc_title = _get_section_hint(title, lang) or title
            cell_content = [
                Paragraph(loc_title, self.styles["pl_sec_title"]),
                Paragraph(title, self.styles["pl_sec_de"]),
            ]
            bg_color = HexColor("#e8f0fb")
            border_color = HexColor("#4466aa")
        else:
            # Official form layout: German section title only — no localized hints
            cell_content = Paragraph(title, self.styles["section"])
            bg_color = _BLUE_LIGHT
            border_color = _BLUE_HEADER

        sec_table = Table([[cell_content]], colWidths=[_TEXT_WIDTH])
        sec_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                    ("TOPPADDING", (0, 0), (-1, -1), 5 if use_letter_layout else 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5 if use_letter_layout else 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6 if use_letter_layout else 4),
                    (
                        "LINEBELOW",
                        (0, -1),
                        (-1, -1),
                        1.0 if use_letter_layout else 0.8,
                        border_color,
                    ),
                ]
            )
        )
        elems.append(sec_table)

        # ── Field rows ────────────────────────────────────────────────────────
        table_data = []
        row_styles_extra = []  # for per-row backgrounds

        for i, (field_key, lbl_de, val) in enumerate(fields):
            is_empty = not val or str(val).strip() == ""

            if use_letter_layout:
                # Primary label: user's language (bold)
                loc_lbl = _get_field_hint(field_key, lang)
                primary_label = loc_lbl if loc_lbl else lbl_de
                de_ref = (
                    lbl_de if loc_lbl else ""
                )  # show German ref only if localized label exists

                label_rows = [[Paragraph(primary_label, self.styles["pl_label"])]]
                if de_ref:
                    label_rows.append([Paragraph(de_ref, self.styles["pl_label_de"])])
                label_cell = Table(
                    label_rows,
                    colWidths=[_COL_LABEL - 6],
                )
                label_cell.setStyle(
                    TableStyle(
                        [
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ]
                    )
                )

                if is_empty:
                    # Per-field override (e.g. gemeindekennzahl → neutral authority note)
                    _override = _FIELD_EMPTY_OVERRIDE.get(field_key)
                    _row_idx = len(
                        table_data
                    )  # index this row will occupy in table_data
                    if _override:
                        empty_text = _override.get(lang, _override.get("en", ""))
                        row_styles_extra.append(
                            (
                                "BACKGROUND",
                                (0, _row_idx),
                                (-1, _row_idx),
                                HexColor("#fafafa"),
                            )
                        )
                    elif field_key in _OPTIONAL_FIELDS:
                        base_empty = _PREVIEW_LETTER_EMPTY.get(
                            lang, _PREVIEW_LETTER_EMPTY["en"]
                        )
                        suffix = _OPTIONAL_SUFFIX.get(lang, _OPTIONAL_SUFFIX["en"])
                        empty_text = base_empty + suffix
                        row_styles_extra.append(
                            (
                                "BACKGROUND",
                                (0, _row_idx),
                                (-1, _row_idx),
                                HexColor("#fafafa"),
                            )
                        )
                    else:
                        base_empty = _PREVIEW_LETTER_EMPTY.get(
                            lang, _PREVIEW_LETTER_EMPTY["en"]
                        )
                        empty_text = base_empty
                        row_styles_extra.append(
                            (
                                "BACKGROUND",
                                (0, _row_idx),
                                (-1, _row_idx),
                                HexColor("#fff8f0"),
                            )
                        )
                    value_cell = Paragraph(empty_text, self.styles["pl_empty"])
                else:
                    display_val = _prepare_rtl_text(
                        _translate_val(str(val).strip(), lang), lang
                    )
                    value_cell = Paragraph(display_val, self.styles["pl_value"])
                    _row_idx = len(
                        table_data
                    )  # index this row will occupy in table_data
                    if i % 2 == 0:
                        row_styles_extra.append(
                            (
                                "BACKGROUND",
                                (0, _row_idx),
                                (-1, _row_idx),
                                HexColor("#f6f9ff"),
                            )
                        )

            else:
                # Official form layout: German labels only — no localized hints
                if is_empty:
                    continue  # skip empty fields in final/official mode
                label_cell = Paragraph(lbl_de, self.styles["field_label"])
                val_de = _display_val_de(str(val).strip())
                value_cell = Paragraph(
                    _prepare_rtl_text(val_de, lang), self.styles["field_value"]
                )
                _row_idx = len(table_data)  # index this row will occupy in table_data
                if i % 2 == 0:
                    row_styles_extra.append(
                        (
                            "BACKGROUND",
                            (0, _row_idx),
                            (-1, _row_idx),
                            HexColor("#f9f9f9"),
                        )
                    )

            table_data.append([label_cell, value_cell])

        if not table_data:
            return elems

        col_label_w = _COL_LABEL + (6 if use_letter_layout else 0)
        col_value_w = _TEXT_WIDTH - col_label_w

        field_table = Table(
            table_data,
            colWidths=[col_label_w, col_value_w],
            repeatRows=0,
        )
        base_styles = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4 if use_letter_layout else 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if use_letter_layout else 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6 if use_letter_layout else 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, _GREY_LINE),
            (
                "LINEBELOW",
                (0, -1),
                (-1, -1),
                0.8 if not use_letter_layout else 0.3,
                _GREY_LINE,
            ),
        ]
        field_table.setStyle(TableStyle(base_styles + row_styles_extra))
        elems.append(field_table)
        return elems

    # ------------------------------------------------------------------
    def _build_selfcheck_block(self) -> list:
        """
        Preview-only: render a self-check section showing:
        - Readiness score (%)
        - Green checkmark rows for filled required fields
        - Red warning rows for missing required fields
        - Orange rows for recommended-but-missing fields
        - Common rejection reasons for this doc_type
        """
        lang = (self.user_lang or "de").lower()

        # Dynamic title: resolved after score is calculated below.
        # Defined here so the structure is clear; actual value set after score block.
        _TITLE_READY = {
            "de": "✅ Dokument ist bereit zur Einreichung",
            "en": "✅ Your document looks ready",
            "uk": "✅ Документ готовий до подачі",
            "ua": "✅ Документ готовий до подачі",
            "ru": "✅ Документ готов к подаче",
            "pl": "✅ Dokument jest gotowy do złożenia",
            "tr": "✅ Belgeniz gönderilmeye hazır görünüyor",
            "ar": "✅ وثيقتك تبدو جاهزة للتقديم",
        }
        _TITLE_ALMOST = {
            "de": "⚠️ Fast fertig — bitte markierte Abschnitte prüfen",
            "en": "⚠️ Almost ready — please review highlighted sections",
            "uk": "⚠️ Майже готово — перевірте виділені розділи",
            "ua": "⚠️ Майже готово — перевірте виділені розділи",
            "ru": "⚠️ Почти готово — проверьте выделенные разделы",
            "pl": "⚠️ Prawie gotowe — sprawdź zaznaczone sekcje",
            "tr": "⚠️ Neredeyse hazır — lütfen işaretli bölümleri gözden geçirin",
            "ar": "⚠️ تقريبًا جاهز — يرجى مراجعة الأقسام المميزة",
        }
        _TITLE_ISSUES = {
            "de": "❌ Wichtige Probleme erkannt — bitte sorgfältig prüfen",
            "en": "❌ Important issues detected — please review carefully",
            "uk": "❌ Виявлено важливі проблеми — перевірте уважно",
            "ua": "❌ Виявлено важливі проблеми — перевірте уважно",
            "ru": "❌ Обнаружены важные проблемы — проверьте внимательно",
            "pl": "❌ Wykryto ważne problemy — sprawdź uważnie",
            "tr": "❌ Önemli sorunlar tespit edildi — lütfen dikkatlice inceleyin",
            "ar": "❌ تم اكتشاف مشكلات مهمة — يرجى المراجعة بعناية",
        }
        # Placeholder; will be overwritten once score is known
        title_text = _TITLE_ALMOST.get(lang, _TITLE_ALMOST["en"])

        elems = []

        # ── Status block (replaces percentage score) ──────────────────────────
        try:
            from backend.utils.validate import (
                calculate_readiness_score,
                _REQUIRED_FIELDS,
                _WARNING_FIELDS,
            )

            _req_fields = _REQUIRED_FIELDS.get(self.doc_type, [])
            _warn_fields = _WARNING_FIELDS.get(self.doc_type, [])
            score = calculate_readiness_score(
                self.missing_fields, self.warnings, _req_fields, _warn_fields
            )

            # Dynamic section header based on score
            if score >= 90:
                title_text = _TITLE_READY.get(lang, _TITLE_READY["en"])
            elif score >= 70:
                title_text = _TITLE_ALMOST.get(lang, _TITLE_ALMOST["en"])
            else:
                title_text = _TITLE_ISSUES.get(lang, _TITLE_ISSUES["en"])

            # Status lines — confidence-based, no percentage
            _STATUS_OK = {
                "de": "✔ Alle wichtigen Daten sind ausgefüllt",
                "en": "✔ Core data is filled",
                "uk": "✔ Основні дані заповнені",
                "ua": "✔ Основні дані заповнені",
                "ru": "✔ Основные данные заполнены",
                "pl": "✔ Podstawowe dane zostały wypełnione",
                "tr": "✔ Temel bilgiler dolduruldu",
                "ar": "✔ تم إدخال البيانات الأساسية",
            }
            _STATUS_READY = {
                "de": "✔ Dokument ist bereit zur Einreichung",
                "en": "✔ Document is ready for submission",
                "uk": "✔ Документ готовий до подачі",
                "ua": "✔ Документ готовий до подачі",
                "ru": "✔ Документ готов к подаче",
                "pl": "✔ Dokument jest gotowy do złożenia",
                "tr": "✔ Belge gönderime hazır",
                "ar": "✔ المستند جاهز للتقديم",
            }

            if score >= 90:
                status_lines = [
                    _STATUS_OK.get(lang, _STATUS_OK["en"]),
                    _STATUS_READY.get(lang, _STATUS_READY["en"]),
                ]
                status_color = HexColor("#1a7a1a")
                bg_color = HexColor("#f0f7f0")
            elif score >= 70:
                status_lines = [_STATUS_OK.get(lang, _STATUS_OK["en"])]
                status_color = HexColor("#b36b00")
                bg_color = HexColor("#fff8e8")
            else:
                status_lines = []
                status_color = HexColor("#cc0000")
                bg_color = HexColor("#fff0f0")

            if status_lines:
                status_style = ParagraphStyle(
                    "status_line",
                    parent=self.styles.get("checklist_title", self.styles["footer"]),
                    textColor=status_color,
                    fontSize=11,
                    spaceAfter=2,
                )
                combined = "<br/>".join(status_lines)
                status_table = Table(
                    [[Paragraph(combined, status_style)]],
                    colWidths=[_TEXT_WIDTH],
                )
                status_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("LINEBELOW", (0, -1), (-1, -1), 1.0, status_color),
                        ]
                    )
                )
                elems.append(status_table)
                elems.append(Spacer(1, 2 * mm))
        except Exception as _score_err:
            logger.debug("status block failed (non-critical): %s", _score_err)

        # Section header
        header_table = Table(
            [[Paragraph(title_text, self.styles["checklist_title"])]],
            colWidths=[_TEXT_WIDTH],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#eef4ff")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, -1), (-1, -1), 1.0, HexColor("#003366")),
                ]
            )
        )
        elems.append(header_table)
        elems.append(Spacer(1, 2 * mm))

        # ── Trust block: why this document is tricky (buergergeld/jobcenter only) ─
        if self.doc_type in ("buergergeld", "jobcenter"):
            try:
                _trust_header = Table(
                    [
                        [
                            Paragraph(
                                "ℹ️ Warum ist dieses Formular anspruchsvoll?",
                                self.styles.get(
                                    "checklist_title", self.styles["footer"]
                                ),
                            )
                        ]
                    ],
                    colWidths=[_TEXT_WIDTH],
                )
                _trust_header.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#eef3fb")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("LINEBELOW", (0, -1), (-1, -1), 0.8, HexColor("#003399")),
                        ]
                    )
                )
                _trust_point_style = self.styles.get(
                    "checklist_warn", self.styles["footer"]
                )
                elems.append(_trust_header)
                elems.append(Spacer(1, 1 * mm))
                for _pt in [
                    "•  Über 80 Angaben auf 8 Seiten — viele Felder sind voneinander abhängig.",
                    "•  SV-Nummer, IBAN und Familienstand müssen exakt übereinstimmen.",
                    "•  Fehler können die Bearbeitungszeit beim Jobcenter verlängern.",
                ]:
                    elems.append(Paragraph(_pt, _trust_point_style))
                elems.append(Spacer(1, 2 * mm))
                elems.append(HRFlowable(width="100%", thickness=0.4, color=_GREY_LINE))
                elems.append(Spacer(1, 2 * mm))
            except Exception as _trust_err:
                logger.debug("trust block failed (non-critical): %s", _trust_err)

        # Missing required fields (blocking)
        if self.missing_fields:
            for item in self.missing_fields:
                text = f"❌  {item['label']} — {item['message']}"
                elems.append(Paragraph(text, self.styles["checklist_missing"]))

        # Warning fields (non-blocking)
        if self.warnings:
            for item in self.warnings:
                text = f"⚠️  {item['label']} — {item['message']}"
                elems.append(Paragraph(text, self.styles["checklist_warn"]))

        # If nothing missing — positive confirmation
        if not self.missing_fields and not self.warnings:
            _ALL_OK = {
                "de": "✔  Alle Pflichtfelder sind ausgefüllt.",
                "en": "✔  All required fields are filled.",
                "uk": "✔  Усі обов'язкові поля заповнені.",
                "ua": "✔  Усі обов'язкові поля заповнені.",
                "ru": "✔  Все обязательные поля заполнены.",
                "pl": "✔  Wszystkie wymagane pola są wypełnione.",
                "tr": "✔  Tüm zorunlu alanlar doldurulmuştur.",
                "ar": "✔  جميع الحقول الإلزامية مكتملة.",
            }
            elems.append(
                Paragraph(_ALL_OK.get(lang, _ALL_OK["en"]), self.styles["checklist_ok"])
            )

        # Parity note: inform user the final version uses the official government form
        _PARITY_NOTE = {
            "de": "ℹ️  Das finale PDF verwendet das offizielle Formular-Layout der Behörde.",
            "en": "ℹ️  The final PDF will use the official government form layout.",
            "uk": "ℹ️  Фінальний PDF використовуватиме офіційний бланк державного органу.",
            "ua": "ℹ️  Фінальний PDF використовуватиме офіційний бланк державного органу.",
            "ru": "ℹ️  Финальный PDF будет использовать официальный бланк государственного органа.",
            "pl": "ℹ️  Finalny PDF będzie korzystał z oficjalnego układu formularza urzędowego.",
            "tr": "ℹ️  Son PDF, resmi devlet formu düzenini kullanacaktır.",
            "ar": "ℹ️  سيستخدم PDF النهائي التخطيط الرسمي لنموذج الجهة الحكومية.",
        }
        parity_text = _PARITY_NOTE.get(lang, _PARITY_NOTE["en"])
        elems.append(Spacer(1, 1 * mm))
        elems.append(
            Paragraph(
                parity_text, self.styles.get("checklist_warn", self.styles["footer"])
            )
        )

        elems.append(HRFlowable(width="100%", thickness=0.4, color=_GREY_LINE))

        # ── Common rejection reasons block ────────────────────────────────────
        try:
            from backend.utils.validate import get_rejection_reasons

            reasons = get_rejection_reasons(self.doc_type, lang)
            if reasons:
                _REASONS_TITLE = {
                    "de": "⚠️ Häufige Ablehnungsgründe — bitte prüfen",
                    "en": "⚠️ Common rejection reasons — please verify",
                    "uk": "⚠️ Типові причини відмови — перевірте",
                    "ua": "⚠️ Типові причини відмови — перевірте",
                    "ru": "⚠️ Типичные причины отказа — проверьте",
                    "pl": "⚠️ Częste przyczyny odrzucenia — sprawdź",
                    "tr": "⚠️ Sık görülen red nedenleri — lütfen kontrol edin",
                    "ar": "⚠️ أسباب الرفض الشائعة — يرجى التحقق",
                }
                reasons_header = Table(
                    [
                        [
                            Paragraph(
                                _REASONS_TITLE.get(lang, _REASONS_TITLE["en"]),
                                self.styles.get(
                                    "checklist_title", self.styles["footer"]
                                ),
                            )
                        ]
                    ],
                    colWidths=[_TEXT_WIDTH],
                )
                reasons_header.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#fff8e8")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("LINEBELOW", (0, -1), (-1, -1), 0.8, HexColor("#b36b00")),
                        ]
                    )
                )
                elems.append(Spacer(1, 3 * mm))
                elems.append(reasons_header)
                elems.append(Spacer(1, 1 * mm))
                _reason_style = self.styles.get("checklist_warn", self.styles["footer"])
                for reason in reasons:
                    elems.append(Paragraph(f"•  {reason}", _reason_style))
                elems.append(Spacer(1, 2 * mm))
                elems.append(HRFlowable(width="100%", thickness=0.4, color=_GREY_LINE))
        except Exception as _rr_err:
            logger.debug("rejection reasons block failed (non-critical): %s", _rr_err)

        # ── Soft upsell: get official PDF (buergergeld/jobcenter only) ──────────
        if self.doc_type in ("buergergeld", "jobcenter"):
            try:
                _upsell_header = Table(
                    [
                        [
                            Paragraph(
                                "📄 Offizielles Bürgergeld-Formular erhalten",
                                self.styles.get(
                                    "checklist_title", self.styles["footer"]
                                ),
                            )
                        ]
                    ],
                    colWidths=[_TEXT_WIDTH],
                )
                _upsell_header.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), HexColor("#f0f7f0")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("LINEBELOW", (0, -1), (-1, -1), 0.8, HexColor("#1a7a1a")),
                        ]
                    )
                )
                _upsell_benefit_style = self.styles.get(
                    "checklist_ok",
                    self.styles.get("checklist_warn", self.styles["footer"]),
                )
                elems.append(Spacer(1, 3 * mm))
                elems.append(_upsell_header)
                elems.append(Spacer(1, 1 * mm))
                for _bn in [
                    "✔  Ausgefülltes offizielles Formular (8 Seiten, druckfertig)",
                    "✔  Alle Felder korrekt ausgefüllt — kein manuelles Nacharbeiten",
                    "✔  Sofort einreichbar beim Jobcenter",
                ]:
                    elems.append(Paragraph(_bn, _upsell_benefit_style))
                elems.append(Spacer(1, 2 * mm))
            except Exception as _upsell_err:
                logger.debug("upsell block failed (non-critical): %s", _upsell_err)

        return elems

    # ------------------------------------------------------------------
    def _build_preview_cover(self) -> list:
        """
        Preview-only: a compact info banner rendered before the self-check block.
        Shows document title, service name, language, and generation date.
        Fully localized; falls back to English for unknown languages.
        """
        lang = (self.user_lang or "de").lower()
        form_title = self.meta[0]
        today = datetime.now().strftime("%d.%m.%Y")

        _COVER_TITLE = {
            "de": "Dokumentenvorbereitung",
            "en": "Document Preparation Guide",
            "uk": "Підготовка документа",
            "ua": "Підготовка документа",
            "ru": "Подготовка документа",
            "pl": "Przygotowanie dokumentu",
            "tr": "Belge Hazırlama Rehberi",
            "ar": "دليل إعداد الوثيقة",
        }
        _COVER_SERVICE = {
            "de": f"Erstellt mit Termin Assist · {_SERVICE_DOMAIN}",
            "en": f"Prepared with Termin Assist · {_SERVICE_DOMAIN}",
            "uk": f"Підготовлено за допомогою Termin Assist · {_SERVICE_DOMAIN}",
            "ua": f"Підготовлено за допомогою Termin Assist · {_SERVICE_DOMAIN}",
            "pl": f"Przygotowano z Termin Assist · {_SERVICE_DOMAIN}",
            "tr": f"Termin Assist ile hazırlandı · {_SERVICE_DOMAIN}",
            "ar": f"أُعدَّ بواسطة Termin Assist · {_SERVICE_DOMAIN}",
            "ru": f"Подготовлено с Termin Assist · {_SERVICE_DOMAIN}",
        }
        _COVER_DATE_LABEL = {
            "de": "Erstellt am",
            "en": "Generated",
            "uk": "Дата",
            "ua": "Дата",
            "ru": "Дата",
            "pl": "Data",
            "tr": "Tarih",
            "ar": "التاريخ",
        }
        _COVER_LANG_LABEL = {
            "de": "Sprache",
            "en": "Language",
            "uk": "Мова",
            "ua": "Мова",
            "ru": "Язык",
            "pl": "Język",
            "tr": "Dil",
            "ar": "اللغة",
        }
        _LANG_NAMES = {
            "de": "Deutsch",
            "en": "English",
            "uk": "Українська",
            "ua": "Українська",
            "pl": "Polski",
            "tr": "Türkçe",
            "ar": "العربية",
        }

        cover_title = _COVER_TITLE.get(lang, _COVER_TITLE["en"])
        service_line = _COVER_SERVICE.get(lang, _COVER_SERVICE["en"])
        date_label = _COVER_DATE_LABEL.get(lang, _COVER_DATE_LABEL["en"])
        lang_label = _COVER_LANG_LABEL.get(lang, _COVER_LANG_LABEL["en"])
        lang_name = _LANG_NAMES.get(lang, lang.upper())

        cover_style = ParagraphStyle(
            "cover_title",
            parent=self.styles.get("form_title", self.styles["footer"]),
            fontSize=10,
            textColor=HexColor("#003399"),
            spaceAfter=1,
        )
        cover_sub_style = ParagraphStyle(
            "cover_sub",
            parent=self.styles.get("legal_basis", self.styles["footer"]),
            fontSize=9,
            textColor=HexColor("#444444"),
            spaceAfter=1,
        )

        meta_text = (
            f"{service_line}  ·  {lang_label}: {lang_name}  ·  {date_label}: {today}"
        )
        # form_title is already shown in the blue header strip above — not repeated here
        cover_table = Table(
            [
                [Paragraph(cover_title, cover_style)],
                [Paragraph(meta_text, cover_sub_style)],
            ],
            colWidths=[_TEXT_WIDTH],
        )
        cover_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#eef3fb")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, -1), (-1, -1), 1.0, HexColor("#003399")),
                ]
            )
        )
        return [cover_table, Spacer(1, 3 * mm)]

    # ------------------------------------------------------------------
    def _build_deadline_reminder(self) -> list:
        """
        Preview-only, Anmeldung only: a highlighted warning about the 14-day
        registration deadline (§17 BMG).  Fully localized; English fallback.
        """
        lang = (self.user_lang or "de").lower()

        _REMINDER_TITLE = {
            "de": "⚠️ Wichtiger Hinweis",
            "en": "⚠️ Important",
            "uk": "⚠️ Важливо",
            "ua": "⚠️ Важливо",
            "ru": "⚠️ Важно",
            "pl": "⚠️ Ważne",
            "tr": "⚠️ Önemli",
            "ar": "⚠️ مهم",
        }
        _REMINDER_BODY = {
            "de": (
                "Die Anmeldung muss <b>innerhalb von 14 Tagen</b> nach dem Einzug erfolgen "
                "(§ 17 BMG). Bei verspäteter Anmeldung droht ein Bußgeld von bis zu <b>1 000 €</b>."
            ),
            "en": (
                "Registration must be completed <b>within 14 days</b> after moving in "
                "(§ 17 BMG). Late registration may result in a fine of up to <b>€1,000</b>."
            ),
            "uk": (
                "Реєстрацію необхідно здійснити <b>протягом 14 днів</b> після в'їзду "
                "(§ 17 BMG). За запізнення може бути накладено штраф до <b>1 000 €</b>."
            ),
            "ua": (
                "Реєстрацію необхідно здійснити <b>протягом 14 днів</b> після в'їзду "
                "(§ 17 BMG). За запізнення може бути накладено штраф до <b>1 000 €</b>."
            ),
            "ru": (
                "Регистрацию необходимо оформить <b>в течение 14 дней</b> после въезда "
                "(§ 17 BMG). За просрочку может быть наложен штраф до <b>1 000 €</b>."
            ),
            "pl": (
                "Rejestracja musi nastąpić <b>w ciągu 14 dni</b> od wprowadzenia się "
                "(§ 17 BMG). Spóźnienie grozi karą do <b>1 000 €</b>."
            ),
            "tr": (
                "Kayıt, taşınmadan sonra <b>14 gün içinde</b> yapılmalıdır "
                "(§ 17 BMG). Geç kayıt durumunda <b>1.000 €</b>'ya kadar para cezası uygulanabilir."
            ),
            "ar": (
                "يجب إتمام التسجيل <b>خلال 14 يومًا</b> من الانتقال إلى المسكن "
                "(§ 17 BMG). قد يُفضي التأخر إلى غرامة تصل إلى <b>1.000 €</b>."
            ),
        }

        title_style = ParagraphStyle(
            "reminder_title",
            parent=self.styles.get("checklist_title", self.styles["footer"]),
            fontSize=9,
            textColor=HexColor("#7a3000"),
            spaceAfter=2,
        )
        body_style = ParagraphStyle(
            "reminder_body",
            parent=self.styles.get("checklist_warn", self.styles["footer"]),
            fontSize=8,
            textColor=HexColor("#5a2000"),
            spaceAfter=0,
        )

        reminder_table = Table(
            [
                [
                    Paragraph(
                        _REMINDER_TITLE.get(lang, _REMINDER_TITLE["en"]), title_style
                    )
                ],
                [Paragraph(_REMINDER_BODY.get(lang, _REMINDER_BODY["en"]), body_style)],
            ],
            colWidths=[_TEXT_WIDTH],
        )
        reminder_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#fff3e0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, -1), (-1, -1), 1.2, HexColor("#b36b00")),
                    ("LINEBEFORE", (0, 0), (0, -1), 3.0, HexColor("#b36b00")),
                ]
            )
        )
        return [reminder_table, Spacer(1, 3 * mm)]

    # ------------------------------------------------------------------
    def _build_next_steps(self) -> list:
        """
        Preview-only: a compact 'Next Steps' block shown after the field sections.
        Guides the user on what to do after reviewing the preview.
        Fully localized; English fallback.
        """
        lang = (self.user_lang or "de").lower()

        _NS_TITLE = {
            "de": "📋 Nächste Schritte",
            "en": "📋 Next Steps",
            "uk": "📋 Наступні кроки",
            "ua": "📋 Наступні кроки",
            "ru": "📋 Следующие шаги",
            "pl": "📋 Kolejne kroki",
            "tr": "📋 Sonraki Adımlar",
            "ar": "📋 الخطوات التالية",
        }
        _NS_STEPS = {
            "de": [
                "Laden Sie das offizielle Formular herunter.",
                "Drucken Sie das Dokument aus.",
                "Bringen Sie einen gültigen Personalausweis oder Reisepass mit.",
                "Reichen Sie das Formular bei der zuständigen Behörde ein.",
            ],
            "en": [
                "Download the official form.",
                "Print the document.",
                "Bring a valid ID or passport.",
                "Submit the form at the responsible authority.",
            ],
            "uk": [
                "Завантажте офіційний бланк.",
                "Роздрукуйте документ.",
                "Візьміть з собою дійсний паспорт або посвідчення особи.",
                "Подайте форму до відповідного органу.",
            ],
            "ua": [
                "Завантажте офіційний бланк.",
                "Роздрукуйте документ.",
                "Візьміть з собою дійсний паспорт або посвідчення особи.",
                "Подайте форму до відповідного органу.",
            ],
            "ru": [
                "Скачайте официальный бланк.",
                "Распечатайте документ.",
                "Возьмите с собой действующий паспорт или удостоверение личности.",
                "Подайте форму в соответствующий орган.",
            ],
            "pl": [
                "Pobierz oficjalny formularz.",
                "Wydrukuj dokument.",
                "Zabierz ważny dowód tożsamości lub paszport.",
                "Złóż formularz w odpowiednim urzędzie.",
            ],
            "tr": [
                "Resmi formu indirin.",
                "Belgeyi yazdırın.",
                "Geçerli bir kimlik veya pasaport getirin.",
                "Formu ilgili makama teslim edin.",
            ],
            "ar": [
                "قم بتنزيل النموذج الرسمي.",
                "اطبع الوثيقة.",
                "أحضر بطاقة هوية سارية أو جواز سفر.",
                "قدّم النموذج إلى الجهة المختصة.",
            ],
        }

        title_style = ParagraphStyle(
            "ns_title",
            parent=self.styles.get("checklist_title", self.styles["footer"]),
            fontSize=9,
            textColor=HexColor("#003399"),
            spaceAfter=2,
        )
        step_style = ParagraphStyle(
            "ns_step",
            parent=self.styles.get("footer", self.styles["footer"]),
            fontSize=8,
            textColor=HexColor("#222222"),
            spaceAfter=1,
        )

        _NS_QUALITY_NOTE = {
            "de": (
                "ℹ️ Diese Vorschau wurde auf Basis offizieller Formularstrukturen erstellt. "
                "Das offizielle Formular wird mit der finalen Version bereitgestellt."
            ),
            "en": (
                "ℹ️ This preview was prepared using official German form structures. "
                "The official blank form is included with the final version."
            ),
            "uk": (
                "ℹ️ Цей попередній перегляд підготовлено на основі офіційних структур форм. "
                "Офіційний бланк буде надано разом із фінальною версією."
            ),
            "ua": (
                "ℹ️ Цей попередній перегляд підготовлено на основі офіційних структур форм. "
                "Офіційний бланк буде надано разом із фінальною версією."
            ),
            "ru": (
                "ℹ️ Этот предварительный просмотр подготовлен на основе официальных структур форм. "
                "Официальный бланк будет предоставлен вместе с финальной версией."
            ),
            "pl": (
                "ℹ️ Ten podgląd został przygotowany na podstawie oficjalnych struktur formularzy. "
                "Oficjalny formularz zostanie dołączony do wersji finalnej."
            ),
            "tr": (
                "ℹ️ Bu önizleme, resmi Alman form yapıları kullanılarak hazırlanmıştır. "
                "Resmi boş form, nihai sürümle birlikte sunulacaktır."
            ),
            "ar": (
                "ℹ️ تم إعداد هذا المعاينة باستخدام هياكل النماذج الرسمية الألمانية. "
                "سيتم تضمين النموذج الرسمي الفارغ مع النسخة النهائية."
            ),
        }

        note_style = ParagraphStyle(
            "ns_quality_note",
            parent=self.styles.get("footer", self.styles["footer"]),
            fontSize=7,
            textColor=HexColor("#555555"),
            spaceAfter=0,
        )

        # Doc-type-specific step overrides (localized; fallback to generic _NS_STEPS)
        _DOC_STEPS_OVERRIDE: Dict[str, Dict[str, list]] = {
            "anmeldung": {
                "de": [
                    "Wohnungsgeberbestätigung vom Vermieter einholen.",
                    "Offizielles Anmeldeformular herunterladen und ausfüllen.",
                    "Personalausweis / Reisepass + Wohnungsgeberbestätigung mitbringen.",
                    "Termin beim Bürgeramt buchen und erscheinen.",
                ],
                "en": [
                    "Obtain the Wohnungsgeberbestätigung (landlord confirmation).",
                    "Download and fill in the official Anmeldung form.",
                    "Bring your ID/passport and the landlord confirmation.",
                    "Book and attend your Bürgeramt appointment.",
                ],
                "uk": [
                    "Отримайте підтвердження від орендодавця (Wohnungsgeberbestätigung).",
                    "Завантажте та заповніть офіційну форму Anmeldung.",
                    "Візьміть паспорт та підтвердження від орендодавця.",
                    "Запишіться та відвідайте Bürgeramt.",
                ],
                "ua": [
                    "Отримайте підтвердження від орендодавця (Wohnungsgeberbestätigung).",
                    "Завантажте та заповніть офіційну форму Anmeldung.",
                    "Візьміть паспорт та підтвердження від орендодавця.",
                    "Запишіться та відвідайте Bürgeramt.",
                ],
                "ru": [
                    "Получите подтверждение от арендодателя (Wohnungsgeberbestätigung).",
                    "Скачайте и заполните официальную форму Anmeldung.",
                    "Возьмите паспорт и подтверждение от арендодателя.",
                    "Запишитесь и посетите Bürgeramt.",
                ],
                "pl": [
                    "Uzyskaj potwierdzenie od wynajmującego (Wohnungsgeberbestätigung).",
                    "Pobierz i wypełnij oficjalny formularz Anmeldung.",
                    "Zabierz dowód tożsamości/paszport i potwierdzenie wynajmującego.",
                    "Umów się i zgłoś do Bürgeramt.",
                ],
                "tr": [
                    "Ev sahibinden Wohnungsgeberbestätigung alın.",
                    "Resmi Anmeldung formunu indirip doldurun.",
                    "Kimliğinizi/pasaportunuzu ve ev sahibi onayını getirin.",
                    "Bürgeramt randevusu alın ve gidin.",
                ],
                "ar": [
                    "احصل على تأكيد المالك (Wohnungsgeberbestätigung).",
                    "نزّل نموذج Anmeldung الرسمي واملأه.",
                    "أحضر جواز سفرك وتأكيد المالك.",
                    "احجز موعدًا في Bürgeramt واحضر إليه.",
                ],
            },
            "kindergeld": {
                "de": [
                    "Kindergeldantrag beim zuständigen Familienkasse-Amt stellen.",
                    "Geburtsurkunde des Kindes und Personalausweis mitbringen.",
                    "IBAN für die Auszahlung angeben.",
                    "Bearbeitungszeit: ca. 4–8 Wochen.",
                ],
                "en": [
                    "Submit the Kindergeld application at the Familienkasse office.",
                    "Bring the child's birth certificate and your ID.",
                    "Provide your IBAN for payment.",
                    "Processing time: approx. 4–8 weeks.",
                ],
                "uk": [
                    "Подайте заяву на Kindergeld до відділення Familienkasse.",
                    "Візьміть свідоцтво про народження дитини та паспорт.",
                    "Вкажіть IBAN для виплат.",
                    "Термін розгляду: приблизно 4–8 тижнів.",
                ],
                "ua": [
                    "Подайте заяву на Kindergeld до відділення Familienkasse.",
                    "Візьміть свідоцтво про народження дитини та паспорт.",
                    "Вкажіть IBAN для виплат.",
                    "Термін розгляду: приблизно 4–8 тижнів.",
                ],
                "ru": [
                    "Подайте заявление на Kindergeld в отделение Familienkasse.",
                    "Возьмите свидетельство о рождении ребёнка и паспорт.",
                    "Укажите IBAN для выплат.",
                    "Срок рассмотрения: около 4–8 недель.",
                ],
                "pl": [
                    "Złóż wniosek o Kindergeld w urzędzie Familienkasse.",
                    "Zabierz akt urodzenia dziecka i dowód tożsamości.",
                    "Podaj IBAN do wypłat.",
                    "Czas rozpatrzenia: ok. 4–8 tygodni.",
                ],
                "tr": [
                    "Familienkasse ofisine Kindergeld başvurusu yapın.",
                    "Çocuğun doğum belgesini ve kimliğinizi getirin.",
                    "Ödeme için IBAN'ınızı belirtin.",
                    "İşlem süresi: yaklaşık 4–8 hafta.",
                ],
                "ar": [
                    "قدّم طلب Kindergeld في مكتب Familienkasse.",
                    "أحضر شهادة ميلاد الطفل وهويتك.",
                    "أدخل رقم IBAN للدفع.",
                    "مدة المعالجة: حوالي 4–8 أسابيع.",
                ],
            },
        }

        # Pick doc-type-specific steps if available, otherwise generic
        _doc_steps_by_lang = _DOC_STEPS_OVERRIDE.get(self.doc_type, _NS_STEPS)
        steps = _doc_steps_by_lang.get(
            lang, _doc_steps_by_lang.get("en", _NS_STEPS["en"])
        )
        rows = [[Paragraph(_NS_TITLE.get(lang, _NS_TITLE["en"]), title_style)]]
        for i, step in enumerate(steps, 1):
            rows.append([Paragraph(f"{i}. {step}", step_style)])
        rows.append(
            [Paragraph(_NS_QUALITY_NOTE.get(lang, _NS_QUALITY_NOTE["en"]), note_style)]
        )

        ns_table = Table(rows, colWidths=[_TEXT_WIDTH])
        ns_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#f5f8ff")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.8, HexColor("#003399")),
                ]
            )
        )
        return [Spacer(1, 3 * mm), ns_table]

    # ------------------------------------------------------------------
    def _build_preview_reassurance(self) -> list:
        """
        Preview-only UX block: reassures the user that the system will
        automatically normalize formatting when the final PDF is generated.
        Rendered with a thin separator line, small font, grey text.
        Never included in final PDFs.
        """
        lang = (self.user_lang or "de").lower()
        if lang == "ua":
            lang = "uk"
        text = _PREVIEW_REASSURANCE_TEXT.get(lang, _PREVIEW_REASSURANCE_TEXT["en"])

        is_rtl = lang == "ar"
        alignment = TA_RIGHT if is_rtl else TA_LEFT

        reassurance_style = ParagraphStyle(
            "preview_reassurance",
            parent=self.styles["footer"],
            fontSize=8,
            leading=11,
            textColor=HexColor("#888888"),
            alignment=alignment,
            spaceAfter=0,
            spaceBefore=0,
            leftIndent=4,
            rightIndent=4,
        )

        # Replace \n\n with paragraph breaks for clean multi-paragraph rendering
        paragraphs = text.split("\n\n")
        elems: list = [
            Spacer(1, 4 * mm),
            HRFlowable(width="100%", thickness=0.4, color=_GREY_LINE),
            Spacer(1, 2 * mm),
        ]
        for i, para in enumerate(paragraphs):
            para_text = para.replace("\n", " ").strip()
            if para_text:
                elems.append(Paragraph(para_text, reassurance_style))
                if i < len(paragraphs) - 1:
                    elems.append(Spacer(1, 1.5 * mm))

        return elems

    # ------------------------------------------------------------------
    def _build_footer(self) -> list:
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        service_tag = f"Erstellt mit GermanDocBot · {_SERVICE_DOMAIN}"
        preview_note = (
            "  ·  Automatisch generiertes Anmeldung-Vorbereitungsdokument"
            if self.is_preview
            else ""
        )

        elems = [
            Spacer(1, 6 * mm),
            HRFlowable(width="100%", thickness=0.5, color=_GREY_LINE),
            Spacer(1, 2 * mm),
            Paragraph(f"{service_tag}  ·  {now}{preview_note}", self.styles["footer"]),
        ]

        # Final PDF: RDG legal disclaimer (Rechtsdienstleistungsgesetz)
        if not self.is_preview:
            elems.append(
                Paragraph(
                    "Dieses Dokument wurde automatisch generiert und stellt keine Rechtsberatung "
                    "im Sinne des RDG dar. Es ersetzt kein amtliches Formular. "
                    "Alle Angaben liegen in der Verantwortung des Nutzers. "
                    "Bitte pr\u00fcfen Sie das Dokument vor der Einreichung.",
                    self.styles["footer"],
                )
            )

        # Final PDF: add official form reference link
        if not self.is_preview and self.official_link:
            _LINK_LABEL = {
                "de": "Offizielles Formular",
                "en": "Official blank form",
                "uk": "Офіційний бланк",
                "ua": "Офіційний бланк",
                "ru": "Официальный бланк",
                "pl": "Oficjalny formularz",
                "tr": "Resmi form",
                "ar": "النموذج الرسمي",
            }
            lang = (self.user_lang or "de").lower()
            label = _LINK_LABEL.get(lang, _LINK_LABEL["en"])
            elems.append(
                Paragraph(
                    f'{label}: <a href="{self.official_link}" color="#003399">{self.official_link}</a>',
                    self.styles["official_link"],
                )
            )

        return elems

    # ------------------------------------------------------------------
    def _apply_watermark(self, pdf_bytes: bytes) -> bytes:
        """Add small red header to preview PDFs only."""
        try:
            import fitz  # type: ignore
        except ImportError:
            return pdf_bytes

        _WM_TEXT = {
            "de": "PREVIEW – NOT OFFICIAL",
            "en": "PREVIEW – NOT OFFICIAL",
            "uk": "PREVIEW – NOT OFFICIAL",
            "ua": "PREVIEW – NOT OFFICIAL",
            "ru": "PREVIEW – NOT OFFICIAL",
            "pl": "PREVIEW – NOT OFFICIAL",
            "tr": "PREVIEW – NOT OFFICIAL",
            "ar": "PREVIEW – NOT OFFICIAL",
        }
        wm_text = _WM_TEXT.get(self.user_lang, _WM_TEXT["en"])
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                rect = page.rect
                page.insert_textbox(
                    fitz.Rect(0, 5, rect.width, 28),
                    "Dies ist ein ausgefülltes Beispiel zur Orientierung – kein offizielles Dokument",
                    fontsize=11,
                    color=(0.85, 0, 0),
                    align=1,
                )
            out = BytesIO()
            doc.save(out)
            doc.close()
            return out.getvalue()
        except Exception as e:
            logger.debug("Watermark failed (non-fatal): %s", e)
            return pdf_bytes

    # ------------------------------------------------------------------
    def _apply_kopie_watermark(self, pdf_bytes: bytes) -> bytes:
        """Final PDF: small red header only."""
        try:
            import fitz  # type: ignore
        except ImportError:
            return pdf_bytes

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in doc:
                rect = page.rect
                page.insert_textbox(
                    fitz.Rect(0, 5, rect.width, 28),
                    "Dies ist ein ausgefülltes Beispiel zur Orientierung – kein offizielles Dokument",
                    fontsize=11,
                    color=(0.85, 0, 0),
                    align=1,
                )
            out = BytesIO()
            doc.save(out)
            doc.close()
            return out.getvalue()
        except Exception as e:
            logger.debug("KOPIE watermark failed (non-fatal): %s", e)
            return pdf_bytes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_german_form(
    doc_type: str,
    user_data: Dict[str, Any],
    output_path: str,
    is_preview: bool = False,
    user_lang: str = "de",
    missing_fields: Optional[List[Dict[str, str]]] = None,
    warnings: Optional[List[Dict[str, str]]] = None,
    official_link: str = "",
) -> Optional[str]:
    """
    Main entry point.  Returns output_path on success, None on failure.

    Called from pdf_generator.create_final_pdf() when no AcroForm template is
    available for the given doc_type.

    Args:
        missing_fields: List of {key, label, message} dicts for missing required fields.
                        When provided in preview mode, renders a self-check checklist.
        warnings:       List of {key, label, message} dicts for recommended-but-missing fields.
        official_link:  Official government URL shown in final PDF footer.
    """
    doc_key = (doc_type or "").strip().lower()
    if doc_key not in _DOC_META:
        logger.warning("german_form_builder: unknown doc_type=%s", doc_type)
        return None
    builder = _FormBuilder(
        doc_key,
        user_data,
        output_path,
        is_preview,
        user_lang,
        missing_fields=missing_fields,
        warnings=warnings,
        official_link=official_link,
    )
    return builder.build()


def supported_doc_types() -> List[str]:
    """Return list of doc types supported by this builder."""
    return list(_DOC_META.keys())


def normalize_for_builder(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pure adapter: derive convenience composite fields from raw user_data.

    Returns a NEW dict — original user_data is never mutated.
    Builder does NOT depend on these keys; they are additive only.
    If source keys are missing the composite field is omitted (no empty strings).

    Composite fields added:
      full_name   — "{first_name} {last_name}"
      address     — "{street} {house_number}"
      full_address — "{street} {house_number}, {plz} {city}"
    """
    out = dict(user_data)
    first = (out.get("first_name") or "").strip()
    last = (out.get("last_name") or "").strip()
    if first or last:
        out["full_name"] = f"{first} {last}".strip()

    street = (out.get("street") or "").strip()
    house = (out.get("house_number") or "").strip()
    plz = (out.get("plz") or out.get("postal_code") or "").strip()
    city = (out.get("city") or "").strip()
    if street or house:
        out["address"] = f"{street} {house}".strip()
    if street or house or plz or city:
        out["full_address"] = f"{street} {house}, {plz} {city}".strip(" ,")

    return out


# ---------------------------------------------------------------------------
# Ummeldung multi-person chunking helper
# ---------------------------------------------------------------------------
_UMMELDUNG_PERSON_FIELDS = (
    "last_name",
    "first_name",
    "birth_date",
    "birth_name",
    "birth_place",
    "nationality",
)
_UMMELDUNG_PERSON_PREFIXES = ("", "person2_", "person3_", "person4_", "person5_")


def _extract_ummeldung_persons(user_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract up to 5 persons from flat ummeldung user_data.

    Person 1 uses bare keys (last_name, first_name, …).
    Persons 2-5 use prefixed keys (person2_last_name, …).

    Returns a list of non-empty person dicts (persons with no data are dropped).
    """
    persons = []
    for prefix in _UMMELDUNG_PERSON_PREFIXES:
        person: Dict[str, str] = {}
        for field in _UMMELDUNG_PERSON_FIELDS:
            key = prefix + field
            val = (user_data.get(key) or "").strip()
            if val:
                person[field] = val
        # Only include if at least a last_name or first_name is present
        if person.get("last_name") or person.get("first_name"):
            persons.append(person)
    return persons


def _build_ummeldung_chunk_data(
    base_data: Dict[str, Any],
    chunk: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Build a flat user_data dict for one ummeldung PDF from a chunk of ≤2 persons.

    Person 1 → bare keys (last_name, …)
    Person 2 → person2_* keys
    """
    data = dict(base_data)
    # Clear all person fields first so stale data from other chunks doesn't bleed through
    for prefix in _UMMELDUNG_PERSON_PREFIXES:
        for field in _UMMELDUNG_PERSON_FIELDS:
            data.pop(prefix + field, None)

    for idx, person in enumerate(chunk[:2]):
        prefix = _UMMELDUNG_PERSON_PREFIXES[idx]
        for field, val in person.items():
            data[prefix + field] = val

    return data


def build_ummeldung_pdfs(
    user_data: Dict[str, Any],
    output_dir: str,
    base_filename: str,
    is_preview: bool = False,
    user_lang: str = "de",
    missing_fields: Optional[List[Dict[str, str]]] = None,
    warnings: Optional[List[Dict[str, str]]] = None,
    official_link: str = "",
) -> List[str]:
    """
    Generate one PDF per pair of persons for an ummeldung form.

    The official Ummeldung PDF has space for exactly 2 persons.
    If the user registered 3-4 persons → 2 PDFs; 5 persons → 3 PDFs.

    Args:
        user_data:      Flat user_data dict from the WebApp (person1/person2/…/person5 keys).
        output_dir:     Directory where PDFs are written.
        base_filename:  Base filename without extension (e.g. "ummeldung_12345").
        is_preview:     Pass True for preview mode.
        user_lang:      ISO language code for localization.
        missing_fields: Forwarded to build_german_form() for self-check block.
        warnings:       Forwarded to build_german_form() for self-check block.
        official_link:  Forwarded to build_german_form() for footer link.

    Returns:
        List of generated PDF file paths (one per chunk).  Empty on total failure.
    """
    import os

    persons = _extract_ummeldung_persons(user_data)
    if not persons:
        # Fallback: generate a single PDF with whatever data is present
        logger.warning(
            "build_ummeldung_pdfs: no persons extracted — falling back to single PDF"
        )
        out_path = os.path.join(output_dir, f"{base_filename}.pdf")
        result = build_german_form(
            "ummeldung",
            user_data,
            out_path,
            is_preview=is_preview,
            user_lang=user_lang,
            missing_fields=missing_fields,
            warnings=warnings,
            official_link=official_link,
        )
        if result and not is_preview:
            try:
                from backend.pdf_generator import _apply_final_disclaimer

                logger.info(
                    "build_ummeldung_pdfs: applying final disclaimer to %s", result
                )
                _apply_final_disclaimer(result, skip_header=False)
            except Exception as _disc_err:
                logger.warning(
                    "build_ummeldung_pdfs: disclaimer failed (fallback): %s", _disc_err
                )
        return [result] if result else []

    # Split into chunks of 2
    chunks = [persons[i : i + 2] for i in range(0, len(persons), 2)]
    paths: List[str] = []
    for chunk_idx, chunk in enumerate(chunks, start=1):
        suffix = f"_part{chunk_idx}" if len(chunks) > 1 else ""
        out_path = os.path.join(output_dir, f"{base_filename}{suffix}.pdf")
        chunk_data = _build_ummeldung_chunk_data(user_data, chunk)
        result = build_german_form(
            "ummeldung",
            chunk_data,
            out_path,
            is_preview=is_preview,
            user_lang=user_lang,
            # Only pass missing_fields/warnings on the first chunk (they relate to Person 1)
            missing_fields=missing_fields if chunk_idx == 1 else None,
            warnings=warnings if chunk_idx == 1 else None,
            official_link=official_link,
        )
        if result:
            if not is_preview:
                try:
                    from backend.pdf_generator import _apply_final_disclaimer

                    logger.info(
                        "build_ummeldung_pdfs: applying final disclaimer to %s", result
                    )
                    _apply_final_disclaimer(result, skip_header=False)
                except Exception as _disc_err:
                    logger.warning(
                        "build_ummeldung_pdfs: disclaimer failed (chunk %d): %s",
                        chunk_idx,
                        _disc_err,
                    )
            paths.append(result)
            logger.info(
                "build_ummeldung_pdfs: chunk %d/%d → %s (persons: %s)",
                chunk_idx,
                len(chunks),
                result,
                ", ".join(p.get("last_name", "?") for p in chunk),
            )
        else:
            logger.error(
                "build_ummeldung_pdfs: chunk %d/%d FAILED — build_german_form returned None",
                chunk_idx,
                len(chunks),
            )
    return paths
