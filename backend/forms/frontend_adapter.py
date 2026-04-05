"""
backend/forms/frontend_adapter.py
──────────────────────────────────────────────────────────────────────────────
Converts the dynamic wohngeld form config produced by wohngeld_form.py into
the flat schema format that the existing frontend (webapp/index.html) already
knows how to render via rebuildFromSchema().

Expected output shape (per section):
    {
      "id":          "personal",
      "title_key":   "personal",          ← section-ID fallback for sectionName()
      "title_de":    "1. Antragsteller",  ← used by updated sectionName() in HTML
      "title_en":    "1. Applicant",
      "title_tr":    "1. Başvuru Sahibi",
      "title_ar":    "1. مقدم الطلب",
      "collapsible": False,
      "optional":    False,
      "fields": [
        {
          "name":        "last_name",
          "type":        "text",
          "required":    True,
          "label_de":    "Familienname",
          "label_en":    "Last name",
          "label_tr":    "Soyadı",
          "label_ar":    "اسم العائلة",
          "hint_de":     "Ihr aktueller Familienname",
          "hint_en":     "Your current family name",
          "hint_tr":     "Güncel soyadınız",
          "hint_ar":     "اسم عائلتك الحالي",
          "placeholder": "z. B. Müller",
          "options":     None,
          "visible_if":  None
        },
        ...
      ]
    }

Key transformations:
  • field.key       → field.name  (frontend reads f.name)
  • field.label     → label_de / label_en / label_tr / label_ar
  • field.hint      → hint_de / hint_en / hint_tr / hint_ar
  • type="boolean"  → type="select" with options [{value:"ja"},{value:"nein"}]
  • section visible_if string → per-field visible_if object {field, value}
  • "true"/"false"  in visible_if → "ja"/"nein" (matches ja/nein select values)

ISOLATION CONTRACT
  Only import from this module in API handler functions.  Do NOT import in
  pdf_generator.py, form_builder.py, pdf_renderers.py, or document_config.py.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

# Languages that the backend form engine knows about.
_SUPPORTED_LANGS = ("de", "en", "tr", "ar", "uk", "pl")

# Default yes/no select options (values already in frontend _OPTION_LABELS).
_YES_NO_OPTIONS = [{"value": "ja"}, {"value": "nein"}]


# ---------------------------------------------------------------------------
# Generic public API (works for ANY registered doc type)
# ---------------------------------------------------------------------------

def build_frontend_schema(
    document_type: str,
    req_lang: str = "de",
) -> Dict[str, Any]:
    """
    Return the complete form schema for *document_type* in the format
    understood by the frontend ``rebuildFromSchema()`` function.

    Works for every document type registered in ``backend.forms.__init__``
    (wohngeld, kindergeld, kinderzuschlag, mietbescheinigung,
    beschaeftigungserklaerung, …).

    Parameters
    ----------
    document_type : e.g. "kindergeld"
    req_lang      : hint for the active frontend language (de | en | tr | ar)

    Returns
    -------
    ``{"sections": [...]}`` ready for ``web.json_response()``.
    """
    from backend.forms import get_form_config

    # Resolve the form once per supported language with all sections visible.
    lang_resolved: Dict[str, List[Dict[str, Any]]] = {}
    for lg in _SUPPORTED_LANGS:
        lang_resolved[lg] = get_form_config(
            document_type,
            form_data={},
            force_show_all=True,
            lang=lg,
        )

    return _assemble_frontend_schema(lang_resolved)


def build_wohngeld_frontend_schema(
    req_lang: str = "de",
) -> Dict[str, Any]:
    """Backward-compatible wrapper — delegates to the generic builder."""
    return build_frontend_schema("wohngeld", req_lang=req_lang)


# ---------------------------------------------------------------------------
# Internal assembly helper (shared by all doc types)
# ---------------------------------------------------------------------------

def _assemble_frontend_schema(
    lang_resolved: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Convert a per-language resolved-form dict into the flat schema object
    that ``rebuildFromSchema()`` in the frontend expects.
    """
    base = lang_resolved["de"]
    result_sections: List[Dict[str, Any]] = []

    for sec_idx, base_sec in enumerate(base):
        # Section-level visible_if → frontend visible_if object
        sec_vis_str = base_sec.get("visible_if", "")
        inherited_field_vis = _parse_visible_if(sec_vis_str)

        result_sec: Dict[str, Any] = {
            "id":          base_sec["id"],
            "title_key":   base_sec["id"],  # fallback for sectionName()
            "collapsible": base_sec.get("collapsible", True),
            "optional":    base_sec.get("optional", False),
        }

        # Propagate section-level visible_if so the frontend can hide/show the
        # ENTIRE section card (not just individual fields) based on a gate field.
        # This is used by wohngeld household/benefits sections which must be
        # completely invisible until the relevant toggle is set to "ja".
        if inherited_field_vis:
            result_sec["section_visible_if"] = inherited_field_vis

        # Embed section title in all 6 languages
        for lg in _SUPPORTED_LANGS:
            result_sec[f"title_{lg}"] = (
                lang_resolved[lg][sec_idx].get("section_title", base_sec["id"])
            )

        # Fields
        result_fields: List[Dict[str, Any]] = []
        for f_idx, base_field in enumerate(base_sec.get("fields", [])):
            fkey  = base_field["key"]
            ftype = base_field.get("type", "text")

            result_field: Dict[str, Any] = {
                "name":     fkey,
                "type":     ftype if ftype != "boolean" else "yesno",
                "required": bool(base_field.get("required", False)),
            }

            # Pass through initial default value (used by yesno toggle renderer)
            if base_field.get("default") is not None:
                result_field["default"] = base_field["default"]

            for lg in _SUPPORTED_LANGS:
                lg_field = lang_resolved[lg][sec_idx]["fields"][f_idx]
                result_field[f"label_{lg}"] = lg_field.get("label", fkey)
                result_field[f"hint_{lg}"]  = lg_field.get("hint", "") or ""

            ph = base_field.get("placeholder", "")
            if ph:
                result_field["placeholder"] = ph

            raw_opts = base_field.get("options", [])
            if raw_opts:
                result_field["options"] = _build_options(raw_opts)

            fvis_str = base_field.get("visible_if", "")
            field_vis = _parse_visible_if(fvis_str) if fvis_str else inherited_field_vis
            if field_vis:
                result_field["visible_if"] = field_vis

            result_fields.append(result_field)

        result_sec["fields"] = result_fields
        result_sections.append(result_sec)

    return {"sections": result_sections}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_vis_val(val: str) -> str:
    v_lower = val.lower()
    if v_lower == "true":
        return "ja"
    if v_lower == "false":
        return "nein"
    return val


def _parse_visible_if(condition: str) -> Optional[Dict[str, Union[str, List[str]]]]:
    """
    Convert a form-engine condition string to the frontend object format.

    Input:  "has_household_members == true"
    Output: {"field": "has_household_members", "value": "ja"}

    Input:  "familienstand == verheiratet or familienstand == eingetragene lebenspartnerschaft"
    Output: {"field": "familienstand", "values": ["verheiratet", "eingetragene lebenspartnerschaft"]}

    Input:  ""  (empty) → None
    """
    if not condition:
        return None
    condition = condition.strip()

    # OR of simple equality clauses on the SAME field (section gates)
    if re.search(r"\s+or\s+", condition, flags=re.IGNORECASE):
        parts = re.split(r"\s+or\s+", condition, flags=re.IGNORECASE)
        field_name: Optional[str] = None
        values: List[str] = []
        for part in parts:
            part = part.strip()
            m = re.match(r"^(\w+)\s*==\s*(.+)$", part, re.IGNORECASE)
            if not m:
                return None
            fld = m.group(1)
            val = _norm_vis_val(m.group(2).strip().strip('"').strip("'"))
            if field_name is None:
                field_name = fld
            elif field_name != fld:
                return None
            values.append(val)
        if field_name and values:
            return {"field": field_name, "values": values}
        return None

    m = re.match(r"^(\w+)\s*(?P<op>==|!=)\s*(.+)$", condition, re.IGNORECASE)
    if not m:
        return None

    field = m.group(1)
    op = m.group("op")
    val = _norm_vis_val(m.group(3).strip().strip('"').strip("'"))

    if op == "!=":
        # Frontend visible_if supports only equality; for != we return None so
        # the field is always visible (conservative safe default).
        return None

    return {"field": field, "value": val}


def _build_options(options: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Strip the form-engine-internal label_key and keep only the value."""
    return [{"value": str(opt.get("value", ""))} for opt in options if opt.get("value") is not None]
