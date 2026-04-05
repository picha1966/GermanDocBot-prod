"""
backend/forms/mietbescheinigung_form.py
──────────────────────────────────────────────────────────────────────────────
Dynamic form configuration for Mietbescheinigung (Vermieterbescheinigung).

This form covers ALL 47 fillable fields of the official PDF template
(templates/mietbescheinigung/default.pdf), including:
  - Document type and tenant role (intro)
  - Landlord details (landlord)
  - Tenant name (tenant)
  - Property address and building data, sections 1.0–2.7 (property)
  - Rent breakdown, sections 3.0–3.2 (rent)
  - Utility/running costs, sections 4.0–4.3 (nebenkosten)
  - Heating and energy data, sections 5.0–5.7 (heating)
  - Garage/parking, sections 6.0–6.1 (garage)
  - Security deposit, sections 7.0–7.3 (deposit)
  - Rent arrears, sections 8.0–8.1 (arrears)
  - Landlord IBAN, section 9.0 (bank)
  - Data protection confirmation + signature (signature)

Key composite mappings (assembled by pdf_generator, NOT stored as single fields):
  last_name + first_name               → mb_m_anschrift  (txt_M_Anschrift)
  landlord_name + landlord_street + …  → mb_vm_anschrift (txt_VM_Anschrift)
  street + house_number + … + city     → mb_anschrift    (txt_Anschrift)

All other keys map 1:1 via MIETBESCHEINIGUNG_ACROFORM_MAPPING in document_config.py.

ISOLATION CONTRACT
  ❌ Do NOT import from document_config.py, pdf_generator.py, form_builder.py.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.forms.form_engine import (
    resolve_form as _resolve,
    get_visible_sections as _visible,
    get_required_keys as _required_keys,
)

_TRANSLATIONS_PATH = Path(__file__).parent.parent / "i18n" / "mietbescheinigung_translations.json"

# ── Shared yes/no ─────────────────────────────────────────────────────────────
_JANEIN = [
    {"value": "ja",   "label_key": "opt_ja"},
    {"value": "nein", "label_key": "opt_nein"},
]

# ── Document type ─────────────────────────────────────────────────────────────
_MIETANGEBOT = [
    {"value": "mietbescheinigung", "label_key": "opt_mietbescheinigung"},
    {"value": "mietangebot",       "label_key": "opt_mietangebot"},
]

# ── Tenant role in the tenancy ────────────────────────────────────────────────
_MIETERTYP = [
    {"value": "hauptmieter",  "label_key": "opt_hauptmieter"},
    {"value": "untermieter",  "label_key": "opt_untermieter"},
]

# ── Apartment type (§ 2.7) ────────────────────────────────────────────────────
_WOHNUNGSTYP = [
    {"value": "abgeschlossen",       "label_key": "opt_abgeschlossen"},
    {"value": "nicht_abgeschlossen", "label_key": "opt_nicht_abgeschlossen"},
]

# ── Energy class (§ 5.1, Energiepass) ────────────────────────────────────────
_ENERGIEPASS = [
    {"value": "a_plus", "label_key": "opt_ep_a_plus"},
    {"value": "a",      "label_key": "opt_ep_a"},
    {"value": "b",      "label_key": "opt_ep_b"},
    {"value": "c",      "label_key": "opt_ep_c"},
    {"value": "d",      "label_key": "opt_ep_d"},
    {"value": "e",      "label_key": "opt_ep_e"},
    {"value": "f",      "label_key": "opt_ep_f"},
    {"value": "g",      "label_key": "opt_ep_g"},
    {"value": "h",      "label_key": "opt_ep_h"},
    {"value": "unbekannt", "label_key": "opt_ep_unbekannt"},
]

# ── Energy source / Energieträger (§ 5.2) ────────────────────────────────────
_ENERGIEART = [
    {"value": "erdgas",      "label_key": "opt_erdgas"},
    {"value": "erdoel",      "label_key": "opt_erdoel"},
    {"value": "fernwaerme",  "label_key": "opt_fernwaerme"},
    {"value": "strom",       "label_key": "opt_strom_heizung"},
    {"value": "holzpellets", "label_key": "opt_holzpellets"},
    {"value": "holz",        "label_key": "opt_holz"},
    {"value": "kohle",       "label_key": "opt_kohle"},
]

# ── Water heating type (§ 5.3) ────────────────────────────────────────────────
_WASSERAUFBEREITUNG = [
    {"value": "dezentral",       "label_key": "opt_wasser_dezentral"},
    {"value": "heizungsanlage",  "label_key": "opt_wasser_heizungsanlage"},
]


MIETBESCHEINIGUNG_FORM: List[Dict[str, Any]] = [

    # ── Intro: document type + tenant role ────────────────────────────────────
    # Always required — determines whether this is a Mietbescheinigung
    # (for existing tenancy) or a Mietangebot (for prospective tenant).
    {
        "id": "intro",
        "title_key": "sec_intro",
        "hint_key": "sec_intro_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "mb_doc_type",    "type": "select", "required": True,
             "options": _MIETANGEBOT},
            {"key": "mb_tenant_type", "type": "select", "required": True,
             "options": _MIETERTYP},
        ],
    },

    # ── 1. Landlord ───────────────────────────────────────────────────────────
    # Name and address of the landlord or property owner.
    # Assembled into txt_VM_Anschrift composite by pdf_generator.
    {
        "id": "landlord",
        "title_key": "sec_landlord",
        "hint_key": "sec_landlord_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "landlord_name",        "type": "text", "required": True,
             "placeholder_key": "ph_landlord_name"},
            {"key": "landlord_street",       "type": "text", "required": True,
             "placeholder_key": "ph_street"},
            {"key": "landlord_house_number", "type": "text", "required": True,
             "placeholder_key": "ph_house_number"},
            {"key": "landlord_plz",          "type": "text", "required": True,
             "placeholder_key": "ph_postal_code"},
            {"key": "landlord_city",         "type": "text", "required": True,
             "placeholder_key": "ph_city"},
        ],
    },

    # ── 2. Tenant ─────────────────────────────────────────────────────────────
    # Name of the tenant. Assembled into txt_M_Anschrift by pdf_generator.
    {
        "id": "tenant",
        "title_key": "sec_tenant",
        "hint_key": "sec_tenant_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "last_name",  "type": "text", "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "first_name", "type": "text", "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "email", "type": "email", "required": True,
             "placeholder_key": "ph_email"},
        ],
    },

    # ── 3. Property — 1.0–2.7 ────────────────────────────────────────────────
    # Full address + building and apartment data.
    # Street/number/plz/city assembled into txt_Anschrift by pdf_generator.
    {
        "id": "property",
        "title_key": "sec_property",
        "hint_key": "sec_property_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            # 1.0 Anschrift
            {"key": "street",                     "type": "text",   "required": True,
             "placeholder_key": "ph_street"},
            {"key": "house_number",               "type": "text",   "required": True,
             "placeholder_key": "ph_house_number"},
            {"key": "apartment_number",           "type": "text",   "required": False,
             "placeholder_key": "ph_apartment_number"},
            {"key": "postal_code",                "type": "text",   "required": True,
             "placeholder_key": "ph_postal_code"},
            {"key": "city",                       "type": "text",   "required": True,
             "placeholder_key": "ph_city"},
            # 1.1 Personen
            {"key": "mb_anzahl_personen",         "type": "number", "required": True,
             "placeholder_key": "ph_count"},
            # 2.0 Mietbeginn
            {"key": "mb_mietbeginn",              "type": "date",   "required": True},
            # 2.1–2.4 Flächen
            {"key": "mb_gebaeudflaeche",          "type": "number", "required": False,
             "placeholder_key": "ph_sqm"},
            {"key": "mb_wohnungsflaeche",         "type": "number", "required": True,
             "placeholder_key": "ph_sqm"},
            {"key": "mb_untervermietete_flaeche", "type": "number", "required": False,
             "placeholder_key": "ph_sqm"},
            {"key": "mb_gewerblich",              "type": "number", "required": False,
             "placeholder_key": "ph_sqm"},
            # 2.5 Baujahr
            {"key": "mb_bezugsfertig",            "type": "number", "required": False,
             "placeholder_key": "ph_year"},
            # 2.6 Zimmer / Bäder / Küchen
            {"key": "mb_zimmer",                  "type": "number", "required": True,
             "placeholder_key": "ph_count"},
            {"key": "mb_bäder",                   "type": "number", "required": True,
             "placeholder_key": "ph_count"},
            {"key": "mb_kuechen",                 "type": "number", "required": True,
             "placeholder_key": "ph_count"},
            # 2.7 Wohnungstyp
            {"key": "mb_wohnungstyp",             "type": "select", "required": True,
             "options": _WOHNUNGSTYP},
        ],
    },

    # ── 4. Rent — 3.0–3.2 ────────────────────────────────────────────────────
    {
        "id": "rent",
        "title_key": "sec_rent",
        "hint_key": "sec_rent_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "mb_gesamtmiete",    "type": "number", "required": True,
             "placeholder_key": "ph_euro"},
            {"key": "mb_beginn_zahlung", "type": "date",   "required": True},
            {"key": "mb_kaltmiete",      "type": "number", "required": True,
             "placeholder_key": "ph_euro"},
        ],
    },

    # ── 5. Nebenkosten — 4.0–4.3 ─────────────────────────────────────────────
    # Running costs without heating.
    {
        "id": "nebenkosten",
        "title_key": "sec_nebenkosten",
        "hint_key": "sec_nebenkosten_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            # 4.0
            {"key": "mb_nebenkosten",    "type": "number", "required": True,
             "placeholder_key": "ph_euro"},
            # 4.1 Pauschale
            {"key": "mb_nk_pauschale",   "type": "select", "required": True,
             "options": _JANEIN},
            # 4.2 Haushaltsstrom
            {"key": "mb_haushaltsstrom", "type": "select", "required": True,
             "options": _JANEIN},
            {"key": "mb_stromkosten",    "type": "number", "required": False,
             "placeholder_key": "ph_euro",
             "visible_if": "mb_haushaltsstrom == ja"},
            # 4.3 NK direkt an Versorger
            {"key": "mb_nk_vu",          "type": "text",   "required": False,
             "placeholder_key": "ph_nk_vu"},
        ],
    },

    # ── 6. Heating — 5.0–5.7 ─────────────────────────────────────────────────
    # Legally required for Wohngeld / Bürgergeld calculations.
    {
        "id": "heating",
        "title_key": "sec_heating",
        "hint_key": "sec_heating_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            # 5.1 Energiepass
            {"key": "mb_energiepass",         "type": "select", "required": True,
             "options": _ENERGIEPASS},
            # 5.2 Energieträger
            {"key": "mb_energieart",          "type": "select", "required": True,
             "options": _ENERGIEART},
            {"key": "mb_gastherme",           "type": "select", "required": False,
             "options": _JANEIN,
             "visible_if": "mb_energieart == erdgas"},
            # 5.3 Wasseraufbereitung
            {"key": "mb_wasseraufbereitung",  "type": "select", "required": True,
             "options": _WASSERAUFBEREITUNG},
            {"key": "mb_heizung_notiz",       "type": "text",   "required": False,
             "placeholder_key": "ph_notes"},
            # 5.4 Kosten + Jahresverbrauch
            {"key": "mb_heizkosten",          "type": "number", "required": True,
             "placeholder_key": "ph_euro"},
            {"key": "mb_jahresverbrauch",     "type": "number", "required": False,
             "placeholder_key": "ph_kwh"},
            # 5.5 Pauschale
            {"key": "mb_heizpauschale",       "type": "select", "required": True,
             "options": _JANEIN},
            # 5.6 Mieter zahlt direkt an VU
            {"key": "mb_hk_vu",              "type": "select", "required": True,
             "options": _JANEIN},
            # 5.7 Brennstoffbesorgung durch Mieter
            {"key": "mb_brennstoffbesorgung", "type": "select", "required": True,
             "options": _JANEIN},
        ],
    },

    # ── 7. Garage — 6.0–6.1 ──────────────────────────────────────────────────
    {
        "id": "garage",
        "title_key": "sec_garage",
        "hint_key": "sec_garage_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "mb_garage",          "type": "select", "required": True,
             "options": _JANEIN},
            {"key": "mb_garage_kosten",   "type": "number", "required": False,
             "placeholder_key": "ph_euro",
             "visible_if": "mb_garage == ja"},
            {"key": "mb_garage_zwingend", "type": "select", "required": False,
             "options": _JANEIN,
             "visible_if": "mb_garage == ja"},
        ],
    },

    # ── 8. Deposit — 7.0–7.3 ─────────────────────────────────────────────────
    {
        "id": "deposit",
        "title_key": "sec_deposit",
        "hint_key": "sec_deposit_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "mb_mietkaution",     "type": "select", "required": True,
             "options": _JANEIN},
            {"key": "mb_kaution_betrag",  "type": "number", "required": False,
             "placeholder_key": "ph_euro",
             "visible_if": "mb_mietkaution == ja"},
            {"key": "mb_kaution_gezahlt", "type": "select", "required": False,
             "options": _JANEIN,
             "visible_if": "mb_mietkaution == ja"},
            {"key": "mb_buergschaft",     "type": "select", "required": False,
             "options": _JANEIN,
             "visible_if": "mb_mietkaution == ja"},
        ],
    },

    # ── 9. Arrears — 8.0–8.1 ─────────────────────────────────────────────────
    {
        "id": "arrears",
        "title_key": "sec_arrears",
        "hint_key": "sec_arrears_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "mb_mietrueckstaende", "type": "select", "required": True,
             "options": _JANEIN},
            {"key": "mb_rueckstands_info", "type": "text",   "required": False,
             "placeholder_key": "ph_rueckstands_info",
             "visible_if": "mb_mietrueckstaende == ja"},
        ],
    },

    # ── 10. Bank — 9.0 (freiwillig) ──────────────────────────────────────────
    # Optional IBAN. Allows the Leistungsträger to pay rent directly to the
    # landlord when the tenant consents (§ 22 Abs. 7 SGB II).
    {
        "id": "bank",
        "title_key": "sec_bank",
        "hint_key": "sec_bank_hint",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "mb_iban", "type": "text", "required": False,
             "placeholder_key": "ph_iban"},
        ],
    },

    # ── 11. Signature ─────────────────────────────────────────────────────────
    # Landlord confirms data protection notice and signs.
    {
        "id": "signature",
        "title_key": "sec_signature",
        "hint_key": "sec_signature_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "mb_datenschutz",  "type": "checkbox", "required": True},
            {"key": "signature_place", "type": "text",     "required": True,
             "placeholder_key": "ph_city"},
            {"key": "signature_date",  "type": "date",     "required": True},
        ],
    },
]


def resolve_form(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _resolve(MIETBESCHEINIGUNG_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_visible_sections(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _visible(MIETBESCHEINIGUNG_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_required_keys(force_show_all: bool = False) -> List[str]:
    return _required_keys(MIETBESCHEINIGUNG_FORM, force_show_all=force_show_all)
