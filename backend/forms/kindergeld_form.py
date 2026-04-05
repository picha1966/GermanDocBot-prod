"""
backend/forms/kindergeld_form.py
──────────────────────────────────────────────────────────────────────────────
Dynamic form configuration for Kindergeld (KG1) applications.

All field keys align 1:1 with KINDERGELD_ACROFORM_MAPPING / get_value_for_pdf_field
in document_config.py.  Do NOT rename keys here.

ISOLATION CONTRACT
  ❌ Do NOT import from document_config.py, pdf_generator.py, form_builder.py,
     or pdf_renderers.py.
  ✔  Only backend/forms/__init__.py and API handlers import from here.
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

_TRANSLATIONS_PATH = Path(__file__).parent.parent / "i18n" / "kindergeld_translations.json"

# ── Yes/No boolean options ────────────────────────────────────────────────────
_YES_NO = [
    {"value": "ja",   "label_key": "opt_ja"},
    {"value": "nein", "label_key": "opt_nein"},
]

# ── Gender options ────────────────────────────────────────────────────────────
_GENDER = [
    {"value": "w", "label_key": "gender_f"},
    {"value": "m", "label_key": "gender_m"},
    {"value": "d", "label_key": "gender_d"},
]

# ── Marital status options ────────────────────────────────────────────────────
_FAMILIENSTAND = [
    {"value": "ledig",                            "label_key": "fs_ledig"},
    {"value": "verheiratet",                      "label_key": "fs_verheiratet"},
    {"value": "eingetragene Lebenspartnerschaft", "label_key": "fs_eingetragen"},
    {"value": "geschieden",                       "label_key": "fs_geschieden"},
    {"value": "getrennt lebend",                  "label_key": "fs_getrennt"},
    {"value": "verwitwet",                        "label_key": "fs_verwitwet"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Form definition
# ─────────────────────────────────────────────────────────────────────────────

KINDERGELD_FORM: List[Dict[str, Any]] = [

    # ── 1. Persönliche Daten (always open) ───────────────────────────────────
    {
        "id": "personal",
        "title_key": "sec_personal",
        "hint_key": "sec_personal_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "last_name",      "type": "text",   "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "first_name",     "type": "text",   "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "birth_name",     "type": "text",   "required": False,
             "placeholder_key": "ph_birth_name"},
            {"key": "birth_date",     "type": "date",   "required": True},
            {"key": "birth_place",    "type": "text",   "required": True,
             "placeholder_key": "ph_birth_place"},
            {"key": "nationality",    "type": "text",   "required": False,
             "placeholder_key": "ph_nationality"},
            {"key": "gender",         "type": "select", "required": False,
             "options": _GENDER},
            {"key": "familienstand",  "type": "select", "required": True,
             "options": _FAMILIENSTAND},
            {"key": "familienstand_seit", "type": "date",   "required": False},
            {"key": "tax_id",             "type": "text",   "required": False,
             "placeholder_key": "ph_tax_id"},
            {"key": "steuer_id_applicant", "type": "text",   "required": False,
             "placeholder_key": "ph_tax_id"},
        ],
    },

    # ── 2. Aktuelle Adresse (always open) ────────────────────────────────────
    {
        "id": "address",
        "title_key": "sec_address",
        "hint_key": "sec_address_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
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

    # ── 3. Familienkonstellation (always open — drives partner visibility) ───
    {
        "id": "control",
        "title_key": "sec_control",
        "hint_key": "sec_control_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "has_partner", "type": "boolean", "required": False,
             "options": _YES_NO},
        ],
    },

    # ── 4. Angaben zum Ehe-/Lebenspartner (conditional) ──────────────────────
    {
        "id": "partner",
        "title_key": "sec_partner",
        "hint_key": "sec_partner_hint",
        "collapsible": True,
        "optional": True,
        "visible_if": "has_partner == true",
        "fields": [
            {"key": "partner_last_name",  "type": "text", "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "partner_first_name", "type": "text", "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "partner_birth_date", "type": "date", "required": True},
            {"key": "partner_nationality","type": "text", "required": False,
             "placeholder_key": "ph_nationality"},
            {"key": "partner_gender",     "type": "select", "required": False,
             "options": _GENDER},
            {"key": "partner_birth_name", "type": "text", "required": False,
             "placeholder_key": "ph_birth_name"},
            {"key": "partner_steuer_id",  "type": "text", "required": False,
             "placeholder_key": "ph_tax_id"},
        ],
    },

    # ── 5. Angaben zum Kind (always open) ────────────────────────────────────
    {
        "id": "child",
        "title_key": "sec_child",
        "hint_key": "sec_child_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "child_last_name",    "type": "text", "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "child_first_name",   "type": "text", "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "child_birth_date",   "type": "date", "required": True},
            {"key": "child_birth_place",  "type": "text", "required": False,
             "placeholder_key": "ph_birth_place"},
            {"key": "child_nationality",  "type": "text", "required": False,
             "placeholder_key": "ph_nationality"},
            {"key": "child_gender",       "type": "select", "required": False,
             "options": _GENDER},
            {"key": "steuer_id_child",    "type": "text", "required": False,
             "placeholder_key": "ph_tax_id"},
        ],
    },

    # ── 6. Bankverbindung (collapsible; IBAN is required) ────────────────────
    {
        "id": "bank",
        "title_key": "sec_bank",
        "hint_key": "sec_bank_hint",
        "collapsible": True,
        "optional": False,
        "fields": [
            {"key": "iban",           "type": "text", "required": True,
             "placeholder_key": "ph_iban"},
            {"key": "bic",            "type": "text", "required": False,
             "placeholder_key": "ph_bic"},
            {"key": "bank_name",      "type": "text", "required": False,
             "placeholder_key": "ph_bank_name"},
            {"key": "account_holder", "type": "text", "required": False,
             "placeholder_key": "ph_account_holder"},
        ],
    },

    # ── 7. Unterschrift (collapsible, optional) ───────────────────────────────
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


# ── Public API ────────────────────────────────────────────────────────────────


def resolve_form(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _resolve(KINDERGELD_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_visible_sections(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _visible(KINDERGELD_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_required_keys(force_show_all: bool = False) -> List[str]:
    return _required_keys(KINDERGELD_FORM, force_show_all=force_show_all)
