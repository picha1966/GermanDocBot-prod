"""
backend/forms/kinderzuschlag_form.py
──────────────────────────────────────────────────────────────────────────────
Dynamic form configuration for Kinderzuschlag (KIZ) applications.

Field keys align with KINDERZUSCHLAG_ACROFORM_MAPPING / get_value_for_pdf_field
in document_config.py.

Partner block visibility: married or registered civil partnership (matches PDF).

Backward compatibility (PDF layer):
  child_last_name / child_first_name / child_birth_date  → Kind Zeile 1
  child2_* / child3_* strings                             → Zeile 2–3
  kiz_partner_birth_date / kiz_partner_nationality        → still read by PDF layer

ISOLATION CONTRACT
  ❌ Do NOT import from document_config.py, pdf_generator.py, form_builder.py.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.forms.form_engine import (
    _eval_condition,
    get_required_keys as _required_keys,
    get_visible_sections as _visible,
    resolve_form as _resolve,
)

_TRANSLATIONS_PATH = Path(__file__).parent.parent / "i18n" / "kinderzuschlag_translations.json"

_YES_NO = [
    {"value": "ja", "label_key": "opt_ja"},
    {"value": "nein", "label_key": "opt_nein"},
]

_GENDER = [
    {"value": "w", "label_key": "gender_f"},
    {"value": "m", "label_key": "gender_m"},
    {"value": "d", "label_key": "gender_d"},
]

_FAMILIENSTAND = [
    {"value": "ledig", "label_key": "fs_ledig"},
    {"value": "verheiratet", "label_key": "fs_verheiratet"},
    {
        "value": "eingetragene lebenspartnerschaft",
        "label_key": "fs_lebenspartnerschaft",
    },
    {"value": "geschieden", "label_key": "fs_geschieden"},
    {"value": "getrennt lebend", "label_key": "fs_getrennt"},
    {"value": "verwitwet", "label_key": "fs_verwitwet"},
]

_PARTNER_GATE = (
    "familienstand == verheiratet or "
    "familienstand == eingetragene lebenspartnerschaft"
)

KINDERZUSCHLAG_FORM: List[Dict[str, Any]] = [

    # ── 1. Persönliche Angaben ────────────────────────────────────────────────
    {
        "id": "personal",
        "title_key": "sec_personal",
        "hint_key": "sec_personal_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "last_name", "type": "text", "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "first_name", "type": "text", "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "birth_date", "type": "date", "required": True},
            {"key": "gender", "type": "select", "required": True,
             "options": _GENDER},
            {"key": "nationality", "type": "text", "required": True,
             "placeholder_key": "ph_nationality"},
            {"key": "phone", "type": "text", "required": True,
             "placeholder_key": "ph_phone"},
            {"key": "familienstand", "type": "select", "required": True,
             "options": _FAMILIENSTAND},
            {"key": "kiz_fam_stand_seit", "type": "date", "required": False},
            {"key": "kiz_title", "type": "text", "required": False,
             "placeholder_key": "ph_title"},
            {"key": "kiz_birth_name_other", "type": "text", "required": False,
             "placeholder_key": "ph_birth_name_other"},
            {"key": "kiz_kg_nr", "type": "text", "required": False,
             "placeholder_key": "ph_kg_nr"},
        ],
    },

    # ── 2. Aktuelle Adresse ───────────────────────────────────────────────────
    {
        "id": "address",
        "title_key": "sec_address",
        "hint_key": "sec_address_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "street", "type": "text", "required": True,
             "placeholder_key": "ph_street"},
            {"key": "house_number", "type": "text", "required": True,
             "placeholder_key": "ph_house_number"},
            {"key": "postal_code", "type": "text", "required": True,
             "placeholder_key": "ph_postal_code"},
            {"key": "city", "type": "text", "required": True,
             "placeholder_key": "ph_city"},
        ],
    },

    # ── 3. Partner (Frage 2) — sichtbar bei Ehe / Lebenspartnerschaft ─────────
    {
        "id": "partner",
        "title_key": "sec_partner",
        "hint_key": "sec_partner_hint",
        "collapsible": True,
        "optional": False,
        "visible_if": _PARTNER_GATE,
        "fields": [
            {"key": "partner_last_name", "type": "text", "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "partner_first_name", "type": "text", "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "partner_birth_date", "type": "date", "required": True},
            {"key": "partner_nationality", "type": "text", "required": True,
             "placeholder_key": "ph_nationality"},
        ],
    },

    # ── 4. Kinder für Kinderzuschlag (Frage 4, Zeile 1–3) ─────────────────────
    {
        "id": "children",
        "title_key": "sec_children",
        "hint_key": "sec_children_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "child1_last_name", "type": "text", "required": True,
             "placeholder_key": "ph_last_name"},
            {"key": "child1_first_name", "type": "text", "required": True,
             "placeholder_key": "ph_first_name"},
            {"key": "child1_birth_date", "type": "date", "required": True},
            {"key": "child2_last_name", "type": "text", "required": False,
             "placeholder_key": "ph_last_name"},
            {"key": "child2_first_name", "type": "text", "required": False,
             "placeholder_key": "ph_first_name"},
            {"key": "child2_birth_date", "type": "date", "required": False},
            {"key": "child3_last_name", "type": "text", "required": False,
             "placeholder_key": "ph_last_name"},
            {"key": "child3_first_name", "type": "text", "required": False,
             "placeholder_key": "ph_first_name"},
            {"key": "child3_birth_date", "type": "date", "required": False},
        ],
    },

    # ── 5. Bankverbindung (Frage 3) ───────────────────────────────────────────
    {
        "id": "bank",
        "title_key": "sec_bank",
        "hint_key": "sec_bank_hint",
        "collapsible": True,
        "optional": False,
        "fields": [
            {"key": "iban", "type": "text", "required": True,
             "placeholder_key": "ph_iban"},
            {"key": "bic", "type": "text", "required": False,
             "placeholder_key": "ph_bic"},
            {"key": "account_holder", "type": "text", "required": False,
             "placeholder_key": "ph_account_holder"},
        ],
    },

    # ── 6. Frage 5 — Kind(er) nicht ständig im Haushalt (optional) ────────────
    {
        "id": "frage5",
        "title_key": "sec_frage5",
        "hint_key": "sec_frage5_hint",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "kiz_f5_r1_firstname", "type": "text", "required": False,
             "placeholder_key": "ph_first_name"},
            {"key": "kiz_f5_r1_absence", "type": "text", "required": False,
             "placeholder_key": "ph_reason_duration"},
            {"key": "kiz_f5_r2_firstname", "type": "text", "required": False,
             "placeholder_key": "ph_first_name"},
            {"key": "kiz_f5_r2_kiz_child_name", "type": "text", "required": False,
             "placeholder_key": "ph_child_full_name"},
            {"key": "kiz_f5_r3_firstname", "type": "text", "required": False,
             "placeholder_key": "ph_first_name"},
            {"key": "kiz_f5_r3_absence", "type": "text", "required": False,
             "placeholder_key": "ph_reason_duration"},
        ],
    },

    # ── 7. Frage 6 — Kind(er) zeitweise im Haushalt, kein Kindergeld (optional)
    {
        "id": "frage6",
        "title_key": "sec_frage6",
        "hint_key": "sec_frage6_hint",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "kiz_f6_r1_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f6_r1_birth_date", "type": "date", "required": False},
            {"key": "kiz_f6_r1_absence", "type": "text", "required": False,
             "placeholder_key": "ph_reason_duration"},
            {"key": "kiz_f6_r2_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f6_r2_birth_date", "type": "date", "required": False},
            {"key": "kiz_f6_r2_absence", "type": "text", "required": False,
             "placeholder_key": "ph_reason_duration"},
            {"key": "kiz_f6_r3_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f6_r3_birth_date", "type": "date", "required": False},
            {"key": "kiz_f6_r3_absence", "type": "text", "required": False,
             "placeholder_key": "ph_reason_duration"},
        ],
    },

    # ── 8. Frage 7 — weitere Haushaltsmitglieder (optional) ───────────────────
    {
        "id": "frage7",
        "title_key": "sec_frage7",
        "hint_key": "sec_frage7_hint",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "kiz_f7_r1_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f7_r1_birth_date", "type": "date", "required": False},
            {"key": "kiz_f7_r1_rel_me", "type": "text", "required": False,
             "placeholder_key": "ph_relationship"},
            {"key": "kiz_f7_r1_rel_partner", "type": "text", "required": False,
             "placeholder_key": "ph_relationship_partner"},
            {"key": "kiz_f7_r2_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f7_r2_birth_date", "type": "date", "required": False},
            {"key": "kiz_f7_r2_rel_me", "type": "text", "required": False,
             "placeholder_key": "ph_relationship"},
            {"key": "kiz_f7_r2_rel_partner", "type": "text", "required": False,
             "placeholder_key": "ph_relationship_partner"},
            {"key": "kiz_f7_r3_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f7_r3_birth_date", "type": "date", "required": False},
            {"key": "kiz_f7_r3_rel_me", "type": "text", "required": False,
             "placeholder_key": "ph_relationship"},
            {"key": "kiz_f7_r3_rel_partner", "type": "text", "required": False,
             "placeholder_key": "ph_relationship_partner"},
            {"key": "kiz_f7_r4_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f7_r4_birth_date", "type": "date", "required": False},
            {"key": "kiz_f7_r4_rel_me", "type": "text", "required": False,
             "placeholder_key": "ph_relationship"},
            {"key": "kiz_f7_r4_rel_partner", "type": "text", "required": False,
             "placeholder_key": "ph_relationship_partner"},
            {"key": "kiz_f7_r5_name", "type": "text", "required": False,
             "placeholder_key": "ph_full_name"},
            {"key": "kiz_f7_r5_birth_date", "type": "date", "required": False},
            {"key": "kiz_f7_r5_rel_me", "type": "text", "required": False,
             "placeholder_key": "ph_relationship"},
            {"key": "kiz_f7_r5_rel_partner", "type": "text", "required": False,
             "placeholder_key": "ph_relationship_partner"},
        ],
    },

    # ── 9. Unterschrift (optional) ────────────────────────────────────────────
    {
        "id": "signature",
        "title_key": "sec_signature",
        "hint_key": "sec_signature_hint",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "signature_date", "type": "date", "required": False},
        ],
    },

    # ── 10. Bestätigung vor Absenden (kein PDF-Feld) ──────────────────────────
    {
        "id": "confirmation",
        "title_key": "sec_confirmation",
        "hint_key": "sec_confirmation_hint",
        "collapsible": False,
        "optional": False,
        "fields": [
            {"key": "kiz_confirm_truth", "type": "boolean", "required": True,
             "options": _YES_NO, "default": "nein"},
            {"key": "kiz_ack_processing", "type": "boolean", "required": True,
             "options": _YES_NO, "default": "nein"},
        ],
    },
]


def resolve_form(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _resolve(KINDERZUSCHLAG_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_visible_sections(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    return _visible(KINDERZUSCHLAG_FORM, _TRANSLATIONS_PATH, form_data,
                    force_show_all=force_show_all, lang=lang)


def get_required_keys(
    force_show_all: bool = False,
    form_data: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Required keys for live *form_data* (partner block only when gate matches)."""
    return _required_keys(
        KINDERZUSCHLAG_FORM,
        force_show_all=force_show_all,
        form_data=form_data,
    )


def partner_section_visible(form_data: Optional[Dict[str, Any]]) -> bool:
    """Utility for tests / API: True when Frage-2 partner PDF rows should be filled."""
    return _eval_condition(_PARTNER_GATE, form_data or {})
