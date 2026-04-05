"""
backend/forms/beschaeftigungserklaerung_form.py
──────────────────────────────────────────────────────────────────────────────
Dynamic form configuration for Erklärung zum Beschäftigungsverhältnis
(employment declaration for residence permit applications).

Field keys align with BESCHAEFTIGUNGSERKLAERUNG_ACROFORM_MAPPING and handlers
in document_config.py.  Do NOT rename keys.

Key mappings:
  first_name, last_name, birth_date, nationality → direct
  street + house_number + postal_code + city → be_wohnsitz (composite)
  be_firma, be_strasse, be_hausnummer, be_plz, be_ort → direct (employer addr)
  be_kontaktperson, phone, email → direct
  be_betriebsnummer, be_beschaeftigung → direct
  be_berufsbezeichnung, be_studiengang → direct
  be_arbeitsstunden, be_gehalt_monat → direct
  signature_place, signature_date → direct

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

_TRANSLATIONS_PATH = (
    Path(__file__).parent.parent / "i18n" / "beschaeftigungserklaerung_translations.json"
)

_YES_NO = [
    {"value": "ja",   "label_key": "opt_ja"},
    {"value": "nein", "label_key": "opt_nein"},
]

BESCHAEFTIGUNGSERKLAERUNG_FORM: List[Dict[str, Any]] = [

    # ── 1. Angaben zur Person (Arbeitnehmer) — always open ────────────────────
    {
        "id": "employee",
        "title_key": "sec_employee",
        "hint_key": "sec_employee_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "last_name",   "type": "text", "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "first_name",  "type": "text", "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "birth_date",  "type": "date", "required": True},
            {"key": "nationality", "type": "text", "required": False,
             "placeholder_key": "ph_nationality"},
        ],
    },

    # ── 2. Wohnanschrift (Arbeitnehmer) — always open ─────────────────────────
    {
        "id": "address",
        "title_key": "sec_address",
        "hint_key": "sec_address_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            # Composite → be_wohnsitz in PDF
            {"key": "street",       "type": "text", "required": True,
             "placeholder_key": "ph_street"},
            {"key": "house_number", "type": "text", "required": True,
             "placeholder_key": "ph_house_number"},
            {"key": "postal_code",  "type": "text", "required": True,
             "placeholder_key": "ph_postal_code"},
            {"key": "city",         "type": "text", "required": True,
             "placeholder_key": "ph_city"},
        ],
    },

    # ── 3. Angaben zum Arbeitgeber (collapsible) ──────────────────────────────
    {
        "id": "employer",
        "title_key": "sec_employer",
        "hint_key": "sec_employer_hint",
        "collapsible": True,
        "optional": False,
        "fields": [
            {"key": "be_firma",          "type": "text", "required": True,
             "placeholder_key": "ph_company"},
            # Employer address (direct PDF fields)
            {"key": "be_strasse",        "type": "text", "required": False,
             "placeholder_key": "ph_street"},
            {"key": "be_hausnummer",     "type": "text", "required": False,
             "placeholder_key": "ph_house_number"},
            {"key": "be_plz",            "type": "text", "required": False,
             "placeholder_key": "ph_postal_code"},
            {"key": "be_ort",            "type": "text", "required": False,
             "placeholder_key": "ph_city"},
            {"key": "be_kontaktperson",  "type": "text", "required": False,
             "placeholder_key": "ph_contact_person"},
            {"key": "phone",             "type": "text", "required": False,
             "placeholder_key": "ph_phone"},
            {"key": "email",             "type": "email", "required": False,
             "placeholder_key": "ph_email"},
            {"key": "be_betriebsnummer", "type": "text", "required": False,
             "placeholder_key": "ph_betriebsnummer"},
        ],
    },

    # ── 4. Beschäftigung (collapsible) ────────────────────────────────────────
    {
        "id": "job",
        "title_key": "sec_job",
        "hint_key": "sec_job_hint",
        "collapsible": True,
        "optional": True,
        "fields": [
            # be_beschaeftigung: free text describing the employment type/status
            {"key": "be_beschaeftigung",    "type": "text",   "required": False,
             "placeholder_key": "ph_employment_type"},
            {"key": "be_berufsbezeichnung", "type": "text",   "required": False,
             "placeholder_key": "ph_job_title"},
            {"key": "be_studiengang",       "type": "text",   "required": False,
             "placeholder_key": "ph_degree"},
            {"key": "be_arbeitsstunden",    "type": "number", "required": False,
             "placeholder_key": "ph_hours"},
            {"key": "be_gehalt_monat",      "type": "number", "required": False,
             "placeholder_key": "ph_salary"},
        ],
    },

    # ── 5. Unterschrift (collapsible, optional) ───────────────────────────────
    {
        "id": "signature",
        "title_key": "sec_signature",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "signature_place", "type": "text", "required": False,
             "placeholder_key": "ph_city"},
            {"key": "signature_date",  "type": "date", "required": False},
        ],
    },
]


def resolve_form(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _resolve(BESCHAEFTIGUNGSERKLAERUNG_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_visible_sections(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _visible(BESCHAEFTIGUNGSERKLAERUNG_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_required_keys(force_show_all: bool = False) -> List[str]:
    return _required_keys(BESCHAEFTIGUNGSERKLAERUNG_FORM, force_show_all=force_show_all)
