"""
backend/forms/wohngeld_form.py
──────────────────────────────────────────────────────────────────────────────
Dynamic form configuration for the Wohngeld Mietzuschuss application.

Design goals:
  • Section-based, mirrors the official 8-page Bayern form structure
  • visible_if conditions collapse irrelevant sections until needed
  • repeatable sections for household members and income entries
  • force_show_all=True reveals every section at once (power users / admin)
  • All field keys align 1:1 with WOHNGELD_ACROFORM_MAPPING in document_config.py
  • collapsible / optional UX flags allow progressive-disclosure rendering

Section UX flags
────────────────
  collapsible  – frontend may render the section as an accordion/expandable
                 panel; False means always open (used for the primary section)
  optional     – True when the section contains no required fields and the
                 whole block can be skipped by simple users; a translated
                 "Optional" badge should be shown next to the section title

Field UX flags
──────────────
  required     – True  → frontend shows "*" and blocks submission when empty
  optional     – True  → frontend may show a translated "Optional" chip/label

──────────────────────────────────────────────────────────────────────────────
ISOLATION CONTRACT
  ❌ Do NOT import from this module in document_config.py, pdf_generator.py,
     form_builder.py, or pdf_renderers.py.
  ✔  Only backend/forms/get_form_config() and bot/WebApp handlers may import.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Form definition
# ---------------------------------------------------------------------------

#: Each section is a dict with keys:
#:   id          – unique slug used by the engine and frontend
#:   title_key   – translation key for the section heading
#:   fields      – list of field descriptors (see below)
#:   visible_if  – optional expression evaluated against current FormData
#:   repeatable  – if True, the section can be instantiated 1…N times
#:   hint_key    – optional translation key for an info box below the header
#:
#: Each field descriptor:
#:   key         – matches WOHNGELD_ACROFORM_MAPPING / user_data key
#:   type        – text | date | number | select | boolean | textarea
#:   required    – bool (default False for control/optional fields)
#:   options     – list of {value, label_key} for select fields
#:   placeholder_key – translation key for the input placeholder
#:   visible_if  – field-level visibility condition

WOHNGELD_FORM: List[Dict[str, Any]] = [
    # ── Section 1: Antragsteller (§1 of official form) ─────────────────────
    {
        "id": "personal",
        "title_key": "sec_personal",
        "hint_key": "sec_personal_hint",
        "collapsible": False,  # primary section — always expanded
        "optional": False,  # contains required identity + address fields
        "fields": [
            {
                "key": "last_name",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_last_name",
            },
            {
                "key": "first_name",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_first_name",
            },
            {
                "key": "birth_name",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_birth_name",
            },
            {
                "key": "birth_date",
                "type": "date",
                "required": True,
                "placeholder_key": "ph_birth_date",
            },
            {
                "key": "birth_place",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_birth_place",
            },
            {
                "key": "nationality",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_nationality",
            },
            {
                "key": "gender",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "w", "label_key": "gender_f"},
                    {"value": "m", "label_key": "gender_m"},
                    {"value": "d", "label_key": "gender_d"},
                ],
            },
            {
                "key": "street",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_street",
            },
            {
                "key": "house_number",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_house_number",
            },
            {
                "key": "apartment_number",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_apartment_number",
            },
            {
                "key": "postal_code",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_postal_code",
            },
            {
                "key": "city",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_city",
            },
            {
                "key": "phone",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_phone",
            },
            {
                "key": "email",
                "type": "email",
                "required": False,
                "placeholder_key": "ph_email",
            },
            {
                "key": "family_status",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "ledig", "label_key": "fs_ledig"},
                    {"value": "verheiratet", "label_key": "fs_verheiratet"},
                    {"value": "getrennt lebend", "label_key": "fs_getrennt"},
                    {"value": "geschieden", "label_key": "fs_geschieden"},
                    {"value": "verwitwet", "label_key": "fs_verwitwet"},
                    {
                        "value": "eingetragene Lebenspartnerschaft",
                        "label_key": "fs_eingetragen",
                    },
                    {
                        "value": "nichteheliche Lebensgemeinschaft",
                        "label_key": "fs_nichtehelich",
                    },
                ],
            },
            {
                "key": "occupation",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "Arbeitnehmer/in", "label_key": "occ_arbeitnehmer"},
                    {"value": "Selbständige/r", "label_key": "occ_selbstaendig"},
                    {"value": "Beamter/Beamtin", "label_key": "occ_beamter"},
                    {"value": "Student/in oder Auszubildende/r", "label_key": "occ_student"},
                    {"value": "Rentner/in oder Pensionär/in", "label_key": "occ_rentner"},
                    {"value": "arbeitslos", "label_key": "occ_arbeitslos"},
                    {"value": "aus sonstigen Gründen nicht erwerbstätig", "label_key": "occ_sonstig"},
                ],
            },
        ],
    },
    # ── Section 2: Control questions (drive visibility of §4, §11–13) ──────
    {
        "id": "control",
        "title_key": "sec_control",
        "hint_key": "sec_control_hint",
        "collapsible": False,  # drives conditional visibility — must stay open
        "optional": False,  # has_income is required
        "fields": [
            {"key": "has_household_members", "type": "boolean", "required": False, "default": "nein"},
            {"key": "has_income",            "type": "boolean", "required": True,  "default": "ja"},
            {"key": "receives_benefits",     "type": "boolean", "required": False, "default": "nein"},
            {"key": "has_assets",            "type": "boolean", "required": False, "default": "nein"},
        ],
    },
    # ── Section 2b: §1 Antragtyp / Erhöhungsantrag-Gründe ──────────────────
    {
        "id": "antragtyp",
        "title_key": "sec_antragtyp",
        "collapsible": True,
        "optional": True,
        "fields": [
            {
                "key": "wg_antragtyp",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "erst",          "label_key": "at_erstantrag"},
                    {"value": "weiterleistung","label_key": "at_weiterleistung"},
                    {"value": "erhoehung",     "label_key": "at_erhoehung"},
                ],
            },
            {"key": "wg_reason_person_increase", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_reason_income_decrease",  "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_reason_rent_increase",    "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "wg_wohngeld_number",
                "type": "text",
                "required": False,
                "visible_if": "wg_antragtyp != erst",
                "placeholder_key": "ph_wohngeld_number",
            },
        ],
    },
    # ── Section 2c: §2 Vorheriger Wohngeldbezug ─────────────────────────────
    {
        "id": "previous_wohngeld",
        "title_key": "sec_previous_wohngeld",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_had_previous_wohngeld", "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "wg_previous_new_address",
                "type": "text",
                "required": False,
                "visible_if": "wg_had_previous_wohngeld == true",
                "placeholder_key": "ph_address",
            },
            {
                "key": "wg_previous_since",
                "type": "text",
                "required": False,
                "visible_if": "wg_had_previous_wohngeld == true",
                "placeholder_key": "ph_birth_date",
            },
        ],
    },
    # ── Section 2d: §3 Umzug / Zweitwohnsitz ────────────────────────────────
    {
        "id": "address_situation",
        "title_key": "sec_address_situation",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_planning_move",            "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_has_second_residence",     "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "wg_second_residence_address",
                "type": "text",
                "required": False,
                "visible_if": "wg_has_second_residence == true",
                "placeholder_key": "ph_address",
            },
            {"key": "wg_main_residence_elsewhere", "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "wg_keeps_room_at_address",
                "type": "boolean",
                "required": False,
                "default": "nein",
                "visible_if": "wg_main_residence_elsewhere == true",
            },
            {
                "key": "wg_lebensmittelpunkt",
                "type": "text",
                "required": False,
                "visible_if": "wg_main_residence_elsewhere == true",
                "placeholder_key": "ph_address",
            },
        ],
    },
    # ── Section 3: Weitere Haushaltsmitglieder (§4) — repeatable ───────────
    {
        "id": "household",
        "title_key": "sec_household",
        "hint_key": "sec_household_hint",
        "collapsible": True,
        "optional": True,
        "visible_if": "has_household_members == true",
        "repeatable": True,
        "repeat_label_key": "repeat_add_member",
        "fields": [
            {
                "key": "member_name",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_member_name",
            },
            {
                "key": "member_birth_date",
                "type": "date",
                "required": True,
                "placeholder_key": "ph_member_birth_date",
            },
            {
                "key": "member_birth_place",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_member_birth_place",
            },
            {
                "key": "member_relation",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_member_relation",
            },
            {
                "key": "member_gender",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "w", "label_key": "gender_f"},
                    {"value": "m", "label_key": "gender_m"},
                    {"value": "d", "label_key": "gender_d"},
                ],
            },
            {
                "key": "member_nationality",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_nationality",
            },
            {
                "key": "member_family_status",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "ledig",                          "label_key": "fs_ledig"},
                    {"value": "verheiratet",                    "label_key": "fs_verheiratet"},
                    {"value": "getrennt lebend",                "label_key": "fs_getrennt"},
                    {"value": "geschieden",                     "label_key": "fs_geschieden"},
                    {"value": "verwitwet",                      "label_key": "fs_verwitwet"},
                    {"value": "eingetragene Lebenspartnerschaft","label_key": "fs_eingetragen"},
                    {"value": "nichteheliche Lebensgemeinschaft","label_key": "fs_nichtehelich"},
                ],
            },
            {
                "key": "member_occupation",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_income_source",
            },
        ],
    },
    # ── Section 3b: §5 Änderung der Haushaltsgröße ──────────────────────────
    {
        "id": "hh_changes",
        "title_key": "sec_hh_changes",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_hh_size_changing", "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "wg_hh_change_when",
                "type": "text",
                "required": False,
                "visible_if": "wg_hh_size_changing == true",
                "placeholder_key": "ph_birth_date",
            },
            {
                "key": "wg_hh_change_reason",
                "type": "text",
                "required": False,
                "visible_if": "wg_hh_size_changing == true",
                "placeholder_key": "ph_reason",
            },
        ],
    },
    # ── Section 3c: §6 Betreuer ──────────────────────────────────────────────
    {
        "id": "betreuer",
        "title_key": "sec_betreuer",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_betreuer", "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "wg_betreuer_person",
                "type": "text",
                "required": False,
                "visible_if": "wg_has_betreuer == true",
                "placeholder_key": "ph_member_name",
            },
            {
                "key": "wg_betreuer_details",
                "type": "text",
                "required": False,
                "visible_if": "wg_has_betreuer == true",
                "placeholder_key": "ph_address",
            },
        ],
    },
    # ── Section 3d: §7 Abwesende Haushaltsmitglieder ────────────────────────
    {
        "id": "absent_member",
        "title_key": "sec_absent_member",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_absent_member", "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "wg_absent_who",
                "type": "text",
                "required": False,
                "visible_if": "wg_has_absent_member == true",
                "placeholder_key": "ph_member_name",
            },
            {
                "key": "wg_absent_where",
                "type": "text",
                "required": False,
                "visible_if": "wg_has_absent_member == true",
                "placeholder_key": "ph_address",
            },
            {
                "key": "wg_absent_returning",
                "type": "boolean",
                "required": False,
                "default": "nein",
                "visible_if": "wg_has_absent_member == true",
            },
        ],
    },
    # ── Section 3e: §8 Sorgerecht (innerhalb) ────────────────────────────────
    {
        "id": "shared_custody_hh",
        "title_key": "sec_shared_custody_hh",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_shared_custody_hh", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_custody_hh_child1",     "type": "text", "required": False,
             "visible_if": "wg_shared_custody_hh == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_custody_hh_child1_rel", "type": "text", "required": False,
             "visible_if": "wg_shared_custody_hh == true", "placeholder_key": "ph_member_relation"},
            {"key": "wg_custody_hh_child2",     "type": "text", "required": False,
             "visible_if": "wg_shared_custody_hh == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_custody_hh_child2_rel", "type": "text", "required": False,
             "visible_if": "wg_shared_custody_hh == true", "placeholder_key": "ph_member_relation"},
        ],
    },
    # ── Section 3f: §9 Sorgerecht (außerhalb) ────────────────────────────────
    {
        "id": "shared_custody_ext",
        "title_key": "sec_shared_custody_ext",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_shared_custody_ext", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_custody_ext_child1",  "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_custody_ext_child2",  "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_custody_ext_parent1", "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_address"},
            {"key": "wg_custody_ext_parent2", "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_address"},
            {"key": "wg_custody_ext_share1",  "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_percent"},
            {"key": "wg_custody_ext_other1",  "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_custody_ext_share2",  "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_percent"},
            {"key": "wg_custody_ext_other2",  "type": "text", "required": False,
             "visible_if": "wg_shared_custody_ext == true", "placeholder_key": "ph_member_name"},
        ],
    },
    # ── Section 3g: §10 Haushaltsmitglied ausgezogen / eingezogen ──────────
    {
        "id": "member_changes",
        "title_key": "sec_member_changes",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_member_left", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_member_left_who",  "type": "text", "required": False,
             "visible_if": "wg_member_left == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_member_left_when", "type": "text", "required": False,
             "visible_if": "wg_member_left == true", "placeholder_key": "ph_birth_date"},
            {"key": "wg_new_member_expected", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_new_member_moved_in", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_new_member_who",  "type": "text", "required": False,
             "visible_if": "wg_new_member_moved_in == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_new_member_when", "type": "text", "required": False,
             "visible_if": "wg_new_member_moved_in == true", "placeholder_key": "ph_birth_date"},
            {"key": "wg_new_member_has_benefits", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_new_member_benefit",    "type": "text", "required": False,
             "visible_if": "wg_new_member_has_benefits == true", "placeholder_key": "ph_benefit_type"},
            {"key": "wg_new_member_authority",  "type": "text", "required": False,
             "visible_if": "wg_new_member_has_benefits == true", "placeholder_key": "ph_benefit_issuer"},
        ],
    },
    # ── Section 4: Transferleistungen (§11) — optional ─────────────────────
    {
        "id": "benefits",
        "title_key": "sec_benefits",
        "hint_key": "sec_benefits_hint",
        "collapsible": True,
        "optional": True,
        "visible_if": "receives_benefits == true",
        "fields": [
            {
                "key": "benefit_type",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_benefit_type",
            },
            {
                "key": "benefit_issuer",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_benefit_issuer",
            },
            # §11 transfer type checkboxes
            {"key": "wg_benefit_buergergeld",         "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_unterkunft_zuschuss",  "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_unterkunft_kosten",    "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_verletztengeld11",     "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_vorschuss",            "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_grundsicherung",       "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_lebensunterhalt",      "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_ergaenzende",          "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_jugendhilfe8",         "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefit_asylbewerber",         "type": "boolean", "required": False, "default": "nein"},
            # Who/type rows
            {"key": "wg_benefit_name1", "type": "text", "required": False, "placeholder_key": "ph_member_name"},
            {"key": "wg_benefit_type1", "type": "text", "required": False, "placeholder_key": "ph_benefit_type"},
            {"key": "wg_benefit_name2", "type": "text", "required": False, "placeholder_key": "ph_member_name"},
            {"key": "wg_benefit_type2", "type": "text", "required": False, "placeholder_key": "ph_benefit_type"},
            # Past / future 12 months
            {"key": "wg_benefits_last_12m", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_benefits_next_12m", "type": "boolean", "required": False, "default": "nein"},
        ],
    },
    # ── Section 4b: §12 Sonstige regelmäßige Leistungen ─────────────────────
    {
        "id": "other_payments",
        "title_key": "sec_other_payments",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_other_payments",        "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_pay_rente",                 "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_unterhaltsvorschuss12", "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_kinderzuschlag",        "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_wohngeld_prev",         "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_bab",                   "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_ausbildungsfoerderung", "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_ausbildungsgeld",       "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_mobiproeu",             "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_uebergangsgeld",        "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_verletztengeld12",      "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_pay_jugendhilfe12",         "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_has_other_payments == true"},
            {"key": "wg_other_pay_who1",  "type": "text", "required": False,
             "visible_if": "wg_has_other_payments == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_other_pay_type1", "type": "text", "required": False,
             "visible_if": "wg_has_other_payments == true", "placeholder_key": "ph_benefit_type"},
            {"key": "wg_other_pay_who2",  "type": "text", "required": False,
             "visible_if": "wg_has_other_payments == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_other_pay_type2", "type": "text", "required": False,
             "visible_if": "wg_has_other_payments == true", "placeholder_key": "ph_benefit_type"},
        ],
    },
    # ── Section 5: Einkommen (§13) — repeatable ────────────────────────────
    {
        "id": "income",
        "title_key": "sec_income",
        "hint_key": "sec_income_hint",
        "collapsible": True,
        "optional": False,
        "visible_if": "has_income == true",
        "repeatable": True,
        "repeat_label_key": "repeat_add_income",
        "fields": [
            {
                "key": "income_source",
                "type": "text",
                "required": True,
                "placeholder_key": "ph_income_source",
            },
            {
                "key": "monthly_income",
                "type": "number",
                "required": True,
                "placeholder_key": "ph_monthly_income",
            },
            {"key": "wg_income_applicant_3",       "type": "text",    "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_income_applicant_4",       "type": "text",    "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_income_applicant_regular", "type": "boolean", "required": False, "default": "ja"},
            {"key": "wg_income_applicant_taxable", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_income_applicant_temp",    "type": "boolean", "required": False, "default": "nein"},
        ],
    },
    # ── Section 5b: §14 Einmalige Einnahmen ──────────────────────────────────
    {
        "id": "onetime_payments",
        "title_key": "sec_onetime_payments",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_onetime_payment", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_onetime_who",    "type": "text",   "required": False,
             "visible_if": "wg_has_onetime_payment == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_onetime_type",   "type": "text",   "required": False,
             "visible_if": "wg_has_onetime_payment == true", "placeholder_key": "ph_benefit_type"},
            {"key": "wg_onetime_when",   "type": "text",   "required": False,
             "visible_if": "wg_has_onetime_payment == true", "placeholder_key": "ph_birth_date"},
            {"key": "wg_onetime_amount", "type": "number", "required": False,
             "visible_if": "wg_has_onetime_payment == true", "placeholder_key": "ph_monthly_income"},
            {"key": "wg_onetime_expected", "type": "boolean", "required": False, "default": "nein"},
        ],
    },
    # ── Section 5c: §15 Bevorstehende Einkommensveränderungen ────────────────
    {
        "id": "income_change_expected",
        "title_key": "sec_income_change_expected",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_income_change_expected", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_income15_who",    "type": "text",   "required": False,
             "visible_if": "wg_income_change_expected == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_income15_type",   "type": "text",   "required": False,
             "visible_if": "wg_income_change_expected == true", "placeholder_key": "ph_benefit_type"},
            {"key": "wg_income15_when",   "type": "text",   "required": False,
             "visible_if": "wg_income_change_expected == true", "placeholder_key": "ph_birth_date"},
            {"key": "wg_income15_amount", "type": "number", "required": False,
             "visible_if": "wg_income_change_expected == true", "placeholder_key": "ph_monthly_income"},
        ],
    },
    # ── Section 5d: §16 Einkommensveränderung ────────────────────────────────
    {
        "id": "income_change16",
        "title_key": "sec_income_change16",
        "collapsible": True,
        "optional": True,
        "fields": [
            {
                "key": "wg_income16_change",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "ver", "label_key": "ic16_ver"},
                    {"value": "erh", "label_key": "ic16_erh"},
                    {"value": "n",   "label_key": "ic16_n"},
                ],
            },
            {"key": "wg_income16_who",    "type": "text",   "required": False, "placeholder_key": "ph_member_name"},
            {"key": "wg_income16_from",   "type": "text",   "required": False, "placeholder_key": "ph_birth_date"},
            {"key": "wg_income16_amount", "type": "number", "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_income16_reason", "type": "text",   "required": False, "placeholder_key": "ph_reason"},
        ],
    },
    # ── Section 5e: §18 Unterhaltsansprüche ──────────────────────────────────
    {
        "id": "unterhalt_claim",
        "title_key": "sec_unterhalt_claim",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_unterhalt_claim", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_unterhalt_claim_what",   "type": "text", "required": False,
             "visible_if": "wg_has_unterhalt_claim == true", "placeholder_key": "ph_reason"},
            {"key": "wg_unterhalt_claim_amount", "type": "number", "required": False,
             "visible_if": "wg_has_unterhalt_claim == true", "placeholder_key": "ph_monthly_income"},
        ],
    },
    # ── Section 5f: §19 Schwerbehinderung / Pflegebedürftigkeit ──────────────
    {
        "id": "disability",
        "title_key": "sec_disability",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_disabled1_name",  "type": "text", "required": False, "placeholder_key": "ph_member_name"},
            {"key": "wg_disabled1_grade", "type": "text", "required": False, "placeholder_key": "ph_percent"},
            {
                "key": "wg_disabled1_pflege",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "h", "label_key": "pflege_h"},
                    {"value": "t", "label_key": "pflege_t"},
                    {"value": "k", "label_key": "pflege_k"},
                ],
            },
            {"key": "wg_disabled1_stage",     "type": "text",    "required": False, "placeholder_key": "ph_percent"},
            {"key": "wg_disabled1_ns_victim", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_disabled2_name",  "type": "text", "required": False, "placeholder_key": "ph_member_name"},
            {"key": "wg_disabled2_grade", "type": "text", "required": False, "placeholder_key": "ph_percent"},
            {
                "key": "wg_disabled2_pflege",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "h", "label_key": "pflege_h"},
                    {"value": "t", "label_key": "pflege_t"},
                    {"value": "k", "label_key": "pflege_k"},
                ],
            },
            {"key": "wg_disabled2_stage",     "type": "text",    "required": False, "placeholder_key": "ph_percent"},
            {"key": "wg_disabled2_ns_victim", "type": "boolean", "required": False, "default": "nein"},
        ],
    },
    # ── Section 5g: §20 Kindergeld an Dritte ─────────────────────────────────
    {
        "id": "kindergeld_elsewhere",
        "title_key": "sec_kindergeld_elsewhere",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_kindergeld_elsewhere", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_kg_child1",     "type": "text", "required": False,
             "visible_if": "wg_kindergeld_elsewhere == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_kg_recipient1", "type": "text", "required": False,
             "visible_if": "wg_kindergeld_elsewhere == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_kg_child2",     "type": "text", "required": False,
             "visible_if": "wg_kindergeld_elsewhere == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_kg_recipient2", "type": "text", "required": False,
             "visible_if": "wg_kindergeld_elsewhere == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_kg_child3",     "type": "text", "required": False,
             "visible_if": "wg_kindergeld_elsewhere == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_kg_recipient3", "type": "text", "required": False,
             "visible_if": "wg_kindergeld_elsewhere == true", "placeholder_key": "ph_member_name"},
        ],
    },
    # ── Section 5h: §21 Unterhaltszahlungen ──────────────────────────────────
    {
        "id": "unterhalt_payments",
        "title_key": "sec_unterhalt_payments",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_unterhalt", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_unterhalt_who1",    "type": "text",   "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_unterhalt_to1",     "type": "text",   "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_address"},
            {"key": "wg_unterhalt_rel1",    "type": "text",   "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_member_relation"},
            {"key": "wg_unterhalt_amount1", "type": "number", "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_monthly_income"},
            {"key": "wg_unterhalt_who2",    "type": "text",   "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_unterhalt_to2",     "type": "text",   "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_address"},
            {"key": "wg_unterhalt_rel2",    "type": "text",   "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_member_relation"},
            {"key": "wg_unterhalt_amount2", "type": "number", "required": False,
             "visible_if": "wg_has_unterhalt == true", "placeholder_key": "ph_monthly_income"},
            {"key": "wg_unterhalt_extra",   "type": "boolean", "required": False, "default": "nein"},
        ],
    },
    # ── Section 6: Wohnraum-Details (§22–25 of official form) ───────────────
    {
        "id": "housing",
        "title_key": "sec_housing",
        "hint_key": "sec_housing_hint",
        "collapsible": True,
        "optional": False,
        "fields": [
            # §22 Housing type
            {
                "key": "dwelling_type",
                "type": "select",
                "required": False,
                "options": [
                    {"value": "Mietwohnung",    "label_key": "dt_miete"},
                    {"value": "Eigentumswohnung","label_key": "dt_eigentum"},
                ],
            },
            {"key": "wg_is_untermieter",      "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_is_heimbewohner",     "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_is_mehrfamilienhaus", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_is_sonstiger_nutzer", "type": "boolean", "required": False, "default": "nein"},
            {
                "key": "landlord_name",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_landlord_name",
            },
            # §23 Employer subsidy
            {"key": "wg_employer_subsidy", "type": "boolean", "required": False, "default": "nein"},
            # §24-25 Size and costs
            {
                "key": "living_space_sqm",
                "type": "number",
                "required": True,
                "placeholder_key": "ph_living_space",
            },
            {
                "key": "monthly_rent",
                "type": "number",
                "required": True,
                "placeholder_key": "ph_monthly_rent",
            },
            {
                "key": "heating_costs",
                "type": "number",
                "required": False,
                "placeholder_key": "ph_heating_costs",
            },
            {"key": "wg_commercial_heating_chk",  "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_commercial_heating_cost",  "type": "number",  "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_household_energy_chk",     "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_household_energy_cost",    "type": "number",  "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_garage_chk",               "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_garage_cost",              "type": "number",  "required": False, "placeholder_key": "ph_monthly_income"},
            {
                "key": "additional_costs",
                "type": "number",
                "required": False,
                "placeholder_key": "ph_additional_costs",
            },
            {"key": "wg_sonstige_description", "type": "text", "required": False, "placeholder_key": "ph_reason"},
        ],
    },
    # ── Section 6b: §26 Mietminderung ────────────────────────────────────────
    {
        "id": "rent_reduction",
        "title_key": "sec_rent_reduction",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_rent_reduction", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_rent_reduction_period", "type": "text", "required": False,
             "visible_if": "wg_rent_reduction == true", "placeholder_key": "ph_reason"},
            {"key": "wg_rent_reduction_amount", "type": "number", "required": False,
             "visible_if": "wg_rent_reduction == true", "placeholder_key": "ph_monthly_income"},
        ],
    },
    # ── Section 6c: §27 Teilweise gewerbliche / sonstige Nutzung ─────────────
    {
        "id": "partial_use",
        "title_key": "sec_partial_use",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_commercial_use",    "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_commercial_sqm",    "type": "number",  "required": False, "placeholder_key": "ph_living_space"},
            {"key": "wg_sublet_to_others",  "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_sublet_sqm",        "type": "number",  "required": False, "placeholder_key": "ph_living_space"},
            {"key": "wg_shared_by_others",  "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_shared_sqm",        "type": "number",  "required": False, "placeholder_key": "ph_living_space"},
            {"key": "wg_subletting_income", "type": "number",  "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_subletting_heating",     "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_subletting_heating_amt", "type": "number",  "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_subletting_energy",      "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_subletting_energy_amt",  "type": "number",  "required": False, "placeholder_key": "ph_monthly_income"},
            {"key": "wg_subletting_garage",      "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_subletting_garage_amt",  "type": "number",  "required": False, "placeholder_key": "ph_monthly_income"},
        ],
    },
    # ── Section 6d: §28 Berufliche Nutzung ────────────────────────────────────
    {
        "id": "business_use",
        "title_key": "sec_business_use",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_business_use", "type": "boolean", "required": False, "default": "nein"},
        ],
    },
    # ── Section 6e: §29 Wohnrecht / Nutzungsrecht ────────────────────────────
    {
        "id": "wohnrecht",
        "title_key": "sec_wohnrecht",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_has_wohnrecht", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_wohnrecht_type",      "type": "text",   "required": False,
             "visible_if": "wg_has_wohnrecht == true", "placeholder_key": "ph_reason"},
            {"key": "wg_wohnrecht_from_whom", "type": "text",   "required": False,
             "visible_if": "wg_has_wohnrecht == true", "placeholder_key": "ph_landlord_name"},
            {"key": "wg_wohnrecht_since",     "type": "text",   "required": False,
             "visible_if": "wg_has_wohnrecht == true", "placeholder_key": "ph_birth_date"},
            {"key": "wg_wohnrecht_value",     "type": "number", "required": False,
             "visible_if": "wg_has_wohnrecht == true", "placeholder_key": "ph_monthly_income"},
        ],
    },
    # ── Section 6f: §30 Auslandsaufenthalt ────────────────────────────────────
    {
        "id": "abroad",
        "title_key": "sec_abroad",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_abroad", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_abroad_keeps_room", "type": "boolean", "required": False, "default": "nein",
             "visible_if": "wg_abroad == true"},
            {"key": "wg_abroad_address",    "type": "text",    "required": False,
             "visible_if": "wg_abroad == true", "placeholder_key": "ph_address"},
        ],
    },
    # ── Section 6g: §31 Kostenübernahme durch Dritte ─────────────────────────
    {
        "id": "third_party_pays",
        "title_key": "sec_third_party_pays",
        "collapsible": True,
        "optional": True,
        "fields": [
            {"key": "wg_third_party_pays", "type": "boolean", "required": False, "default": "nein"},
            {"key": "wg_third_party_who",      "type": "text",   "required": False,
             "visible_if": "wg_third_party_pays == true", "placeholder_key": "ph_landlord_name"},
            {"key": "wg_third_party_for_whom", "type": "text",   "required": False,
             "visible_if": "wg_third_party_pays == true", "placeholder_key": "ph_member_name"},
            {"key": "wg_third_party_amount",   "type": "number", "required": False,
             "visible_if": "wg_third_party_pays == true", "placeholder_key": "ph_monthly_income"},
        ],
    },
    # ── Section 6h: §17 Vermögenswerte ──────────────────────────────────────
    {
        "id": "assets",
        "title_key": "sec_assets",
        "collapsible": True,
        "optional": True,
        "visible_if": "has_assets == true",
        "fields": [
            {
                "key": "wg_asset_real_estate",
                "type": "number",
                "required": False,
                "visible_if": "has_assets == true",
                "placeholder_key": "ph_monthly_income",
            },
            {
                "key": "wg_asset_money",
                "type": "number",
                "required": False,
                "visible_if": "has_assets == true",
                "placeholder_key": "ph_monthly_income",
            },
            {
                "key": "wg_asset_goods",
                "type": "number",
                "required": False,
                "visible_if": "has_assets == true",
                "placeholder_key": "ph_monthly_income",
            },
            {
                "key": "wg_asset_other",
                "type": "number",
                "required": False,
                "visible_if": "has_assets == true",
                "placeholder_key": "ph_monthly_income",
            },
        ],
    },
    # ── Section 7: Bankverbindung (§32) — optional ─────────────────────────
    {
        "id": "bank",
        "title_key": "sec_bank",
        "hint_key": "sec_bank_hint",
        "collapsible": True,  # fully optional block; collapsed by default
        "optional": True,  # all bank fields are optional
        "fields": [
            {
                "key": "iban",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_iban",
            },
            {
                "key": "bic",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_bic",
            },
            {
                "key": "bank_name",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_bank_name",
            },
        ],
    },
    # ── Section 8: Unterschrift (Seite 8) ────────────────────────────────────
    {
        "id": "signature",
        "title_key": "sec_signature",
        "collapsible": True,  # placed last; collapsible
        "optional": True,  # place/date are optional (auto-filled by backend)
        "fields": [
            {
                "key": "signature_place",
                "type": "text",
                "required": False,
                "placeholder_key": "ph_city",
            },
            {"key": "signature_date", "type": "date", "required": False},
        ],
    },
]


# ---------------------------------------------------------------------------
# Form engine
# ---------------------------------------------------------------------------

_BOOL_TRUE = {"true", "1", "yes", "ja", "so", "نعم", "evet"}
_BOOL_FALSE = {"false", "0", "no", "nein", "hayır", "لا"}


def _eval_condition(condition: str, form_data: Dict[str, Any]) -> bool:
    """
    Evaluate a simple visible_if expression against current form_data.

    Supported syntax:
        key == true | false | "string"
        key != true | false | "string"

    Returns True (visible) when condition is empty / None.
    """
    if not condition:
        return True
    condition = condition.strip()

    # Parse:  <key>  <op>  <value>
    m = re.match(
        r"^(?P<key>\w+)\s*(?P<op>==|!=)\s*(?P<val>.+)$",
        condition,
        re.IGNORECASE,
    )
    if not m:
        return True  # unparseable → default visible

    key = m.group("key")
    op = m.group("op")
    val = m.group("val").strip().strip('"').strip("'")

    raw = form_data.get(key)
    if raw is None:
        raw_str = ""
    elif isinstance(raw, bool):
        raw_str = "true" if raw else "false"
    else:
        raw_str = str(raw).strip().lower()

    val_lower = val.lower()

    if op == "==":
        if val_lower in ("true", "false"):
            return (
                raw_str in _BOOL_TRUE if val_lower == "true" else raw_str in _BOOL_FALSE
            )
        return raw_str == val_lower
    else:  # !=
        if val_lower in ("true", "false"):
            return (
                raw_str not in _BOOL_TRUE
                if val_lower == "true"
                else raw_str not in _BOOL_FALSE
            )
        return raw_str != val_lower


def resolve_form(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    """
    Return a copy of WOHNGELD_FORM with visibility resolved.

    Parameters
    ----------
    form_data : current answers collected so far (may be partial / empty)
    force_show_all : if True, all visible_if conditions are ignored (every
                     section is returned) — useful for admin previews and
                     full-form completion mode
    lang : language code for attaching translated labels inline (de/en/tr/ar)

    Returns
    -------
    List of section dicts with:
        • ``visible``      – bool: whether the section should be rendered
        • ``collapsible``  – bool: frontend may render as accordion
        • ``optional``     – bool (section): all fields are skippable
        • ``section_title``  – translated section heading string
        • ``section_hint``   – translated info-box string (when present)
        • Per field:
            - ``label``     – translated field label
            - ``hint``      – translated helper text
            - ``placeholder`` – translated input placeholder (when defined)
            - ``visible``   – bool: field-level visibility
            - ``optional``  – bool: inverse of ``required`` (convenience flag)
            - ``optional_label`` – translated "Optional" string for UI badges
    """
    data = form_data or {}
    translations = _load_translations()
    t = translations.get(lang) or translations.get("en") or {}
    optional_label = t.get("optional", "Optional")

    resolved: List[Dict[str, Any]] = []
    for raw_sec in WOHNGELD_FORM:
        sec = deepcopy(raw_sec)
        cond = sec.get("visible_if", "")
        sec["visible"] = True if force_show_all else _eval_condition(cond, data)
        sec["collapsible"] = sec.get("collapsible", True)
        sec["optional"] = sec.get("optional", False)
        sec["section_title"] = t.get(sec["title_key"], sec["title_key"])
        if sec.get("hint_key"):
            sec["section_hint"] = t.get(sec["hint_key"], "")

        for field in sec.get("fields", []):
            fkey = field["key"]
            field_t = translations.get("fields", {}).get(fkey, {}).get(lang, {})
            field["label"] = field_t.get("label", fkey)
            field["hint"] = field_t.get("hint", "")
            if field.get("placeholder_key"):
                field["placeholder"] = t.get(field["placeholder_key"], "")

            # field-level visibility
            fcond = field.get("visible_if", "")
            field["visible"] = True if force_show_all else _eval_condition(fcond, data)

            # UX convenience: explicit "optional" flag + translated badge text
            is_required = bool(field.get("required", False))
            field["optional"] = not is_required
            if not is_required:
                field["optional_label"] = optional_label

            # Translate option labels for select fields
            for opt in field.get("options", []):
                opt["label"] = t.get(opt["label_key"], opt["label_key"])

        resolved.append(sec)
    return resolved


def get_visible_sections(
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    """Return only the sections that should currently be shown."""
    return [
        s
        for s in resolve_form(form_data, force_show_all=force_show_all, lang=lang)
        if s["visible"]
    ]


def get_required_keys(force_show_all: bool = False) -> List[str]:
    """Return all required field keys (respects force_show_all visibility)."""
    keys: List[str] = []
    for sec in WOHNGELD_FORM:
        cond = sec.get("visible_if", "")
        if not force_show_all and cond:
            continue  # skip conditionally-hidden sections
        for field in sec.get("fields", []):
            if field.get("required"):
                keys.append(field["key"])
    return keys


# ---------------------------------------------------------------------------
# Translation loader (lazy, cached)
# ---------------------------------------------------------------------------

_translations_cache: Optional[Dict[str, Any]] = None


def _load_translations() -> Dict[str, Any]:
    """
    Load wohngeld_translations.json once and cache in memory.
    Returns a dict keyed by language code at top level for section strings,
    and by "fields" for per-field translations.
    """
    global _translations_cache
    if _translations_cache is not None:
        return _translations_cache

    i18n_path = Path(__file__).parent.parent / "i18n" / "wohngeld_translations.json"
    if i18n_path.exists():
        with open(i18n_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = {}

    # Flatten per-language section/UI strings for fast lookup: t[lang][key] = str
    result: Dict[str, Any] = {"fields": raw.get("fields", {})}
    for lang, strings in raw.get("ui", {}).items():
        result[lang] = strings

    _translations_cache = result
    return result


def reload_translations() -> None:
    """Force-reload translations from disk (useful after hot-swap in dev)."""
    global _translations_cache
    _translations_cache = None
    _load_translations()
