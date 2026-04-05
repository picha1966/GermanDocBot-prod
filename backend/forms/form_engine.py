"""
backend/forms/form_engine.py
──────────────────────────────────────────────────────────────────────────────
Shared dynamic form engine used by all document form modules (kindergeld,
kinderzuschlag, mietbescheinigung, beschaeftigungserklaerung, …).

wohngeld_form.py has its own inline engine — it is NOT modified.
This module is used ONLY by new form modules created after Task 26.

ISOLATION CONTRACT
  ❌ Do NOT import from pdf_generator.py, form_builder.py, pdf_renderers.py,
     or document_config.py.
  ✔  Only backend/forms/<doc>_form.py modules import from here.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Boolean token sets ────────────────────────────────────────────────────────
_BOOL_TRUE  = {"true", "1", "yes", "ja", "so", "نعم", "evet"}
_BOOL_FALSE = {"false", "0", "no", "nein", "hayır", "لا"}

# ── Translation cache: path → dict ───────────────────────────────────────────
_TRANSLATION_CACHE: Dict[str, Dict[str, Any]] = {}


def _load_translations(path: Path) -> Dict[str, Any]:
    """
    Load a translations JSON file and cache by absolute path string.

    Expected file structure:
        {
          "ui":     { "de": { "sec_personal": "...", … }, "en": {…}, … },
          "fields": { "field_key": { "de": {"label": …, "hint": …}, … }, … }
        }

    Returns a flat dict:
        result["de"]        → dict of UI/section strings
        result["en"]        → …
        result["tr"]        → …
        result["ar"]        → …
        result["fields"]    → { field_key: { lang: { label, hint } } }
    """
    key = str(path.resolve())
    if key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[key]

    raw: Dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

    result: Dict[str, Any] = {"fields": raw.get("fields", {})}
    for lang, strings in raw.get("ui", {}).items():
        result[lang] = strings

    _TRANSLATION_CACHE[key] = result
    return result


def reload_translations(path: Path) -> None:
    """Force-reload a specific translations file (dev hot-swap)."""
    key = str(path.resolve())
    _TRANSLATION_CACHE.pop(key, None)
    _load_translations(path)


def _eval_single_condition(condition: str, form_data: Dict[str, Any]) -> bool:
    """Single comparison: key == value or key != value."""
    m = re.match(
        r'^(?P<key>\w+)\s*(?P<op>==|!=)\s*(?P<val>.+)$',
        condition,
        re.IGNORECASE,
    )
    if not m:
        return True

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
            return raw_str in _BOOL_TRUE if val_lower == "true" else raw_str in _BOOL_FALSE
        return raw_str == val_lower
    # !=
    if val_lower in ("true", "false"):
        return raw_str not in _BOOL_TRUE if val_lower == "true" else raw_str not in _BOOL_FALSE
    return raw_str != val_lower


def _eval_condition(condition: str, form_data: Dict[str, Any]) -> bool:
    """
    Evaluate a simple visible_if expression.

    Supported syntax:
        key == true | false | "string_value"
        key != true | false | "string_value"
        disjunction:  cond1 or cond2   (each side is a single comparison)

    Returns True (visible) when condition is empty / None / unparseable.
    """
    if not condition:
        return True
    condition = condition.strip()

    # OR of simple clauses (same use-case: familienstand == a or familienstand == b)
    if re.search(r"\s+or\s+", condition, flags=re.IGNORECASE):
        parts = re.split(r"\s+or\s+", condition, flags=re.IGNORECASE)
        return any(_eval_single_condition(p.strip(), form_data) for p in parts if p.strip())

    return _eval_single_condition(condition, form_data)


def resolve_form(
    form_definition: List[Dict[str, Any]],
    translations_path: Path,
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    """
    Resolve a form definition against current form_data.

    Parameters
    ----------
    form_definition   : list of section dicts (the FORM constant in each module)
    translations_path : Path to the <doc>_translations.json file
    form_data         : current answers (empty dict or None = clean slate)
    force_show_all    : bypass all visible_if conditions (admin / power-user mode)
    lang              : language code for inline labels (de | en | tr | ar)

    Returns
    -------
    List of resolved section dicts, each containing:
      • visible, collapsible, optional, section_title, section_hint (optional)
      • fields — list of resolved field dicts with label, hint, placeholder,
                  visible, optional, optional_label, options
    """
    data = form_data or {}
    t_all = _load_translations(translations_path)
    t = t_all.get(lang) or t_all.get("en") or t_all.get("de") or {}
    optional_label = t.get("optional", "Optional")

    resolved: List[Dict[str, Any]] = []
    for raw_sec in form_definition:
        sec = deepcopy(raw_sec)
        cond = sec.get("visible_if", "")
        sec["visible"]       = True if force_show_all else _eval_condition(cond, data)
        sec["collapsible"]   = sec.get("collapsible", True)
        sec["optional"]      = sec.get("optional", False)
        sec["section_title"] = t.get(sec.get("title_key", ""), sec.get("title_key", ""))
        if sec.get("hint_key"):
            sec["section_hint"] = t.get(sec["hint_key"], "")

        for field in sec.get("fields", []):
            fkey    = field["key"]
            f_langs = t_all.get("fields", {}).get(fkey, {})
            f_t     = f_langs.get(lang) or f_langs.get("en") or f_langs.get("de") or {}
            field["label"] = f_t.get("label", fkey)
            field["hint"]  = f_t.get("hint", "")
            if field.get("placeholder_key"):
                field["placeholder"] = t.get(field["placeholder_key"], "")

            fcond = field.get("visible_if", "")
            field["visible"] = True if force_show_all else _eval_condition(fcond, data)

            is_required = bool(field.get("required", False))
            field["optional"] = not is_required
            if not is_required:
                field["optional_label"] = optional_label

            for opt in field.get("options", []):
                opt["label"] = t.get(opt.get("label_key", ""), opt.get("label_key", ""))

        resolved.append(sec)
    return resolved


def get_visible_sections(
    form_definition: List[Dict[str, Any]],
    translations_path: Path,
    form_data: Optional[Dict[str, Any]] = None,
    *,
    force_show_all: bool = False,
    lang: str = "de",
) -> List[Dict[str, Any]]:
    """Return only currently-visible sections."""
    return [
        s for s in resolve_form(
            form_definition, translations_path, form_data,
            force_show_all=force_show_all, lang=lang,
        )
        if s["visible"]
    ]


def get_required_keys(
    form_definition: List[Dict[str, Any]],
    *,
    force_show_all: bool = False,
    form_data: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Return all required field keys.

    When *form_data* is provided and *force_show_all* is False, section- and
    field-level ``visible_if`` expressions are evaluated so hidden blocks do
    not contribute required keys.  When *form_data* is None, behaviour matches
    the legacy rule: any section that defines ``visible_if`` is skipped entirely
    (conservative default for callers without live answers).
    """
    keys: List[str] = []
    data = form_data if form_data is not None else None
    for sec in form_definition:
        cond = sec.get("visible_if", "")
        if not force_show_all and cond:
            if data is None:
                continue
            if not _eval_condition(cond, data):
                continue
        for field in sec.get("fields", []):
            fcond = field.get("visible_if", "")
            if (
                not force_show_all
                and fcond
                and data is not None
                and not _eval_condition(fcond, data)
            ):
                continue
            if field.get("required"):
                keys.append(field["key"])
    return keys
