"""
backend/forms
─────────────
Isolated, dynamic form configurations keyed by document type.

Usage
─────
    from backend.forms import get_form_config

    # Default: German, visibility resolved from empty form_data
    config = get_form_config("wohngeld")

    # With partial user answers and English labels
    config = get_form_config("wohngeld", form_data=answers, lang="en")

    # Admin / power-user mode: show all sections regardless of conditions
    config = get_form_config("wohngeld", force_show_all=True, lang="de")

Registered document types
─────────────────────────
  wohngeld                  → wohngeld_form.py   (own inline engine)
  kindergeld                → kindergeld_form.py
  kinderzuschlag            → kinderzuschlag_form.py
  mietbescheinigung         → mietbescheinigung_form.py
  beschaeftigungserklaerung → beschaeftigungserklaerung_form.py

ISOLATION CONTRACT
──────────────────
Only this package (and bot/WebApp handlers that consume form configs) should
import from here.  PDF generation, form_builder.py, and pdf_renderers.py must
NOT depend on this package.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any, Dict, List, Optional

# Registered document types that have a dynamic form module.
# Add new entries here as new form modules are created.
_REGISTERED: Dict[str, str] = {
    "wohngeld":                  "backend.forms.wohngeld_form",
    "kindergeld":                "backend.forms.kindergeld_form",
    "kinderzuschlag":            "backend.forms.kinderzuschlag_form",
    "mietbescheinigung":         "backend.forms.mietbescheinigung_form",
    "beschaeftigungserklaerung": "backend.forms.beschaeftigungserklaerung_form",
}


def _get_module(document_type: str):
    """Lazy-import (or hot-reload) the form module for *document_type*.

    On every call: if the module is already in sys.modules it is reloaded from
    disk so that changes to form files take effect without a server restart.
    """
    module_path = _REGISTERED.get(document_type)
    if not module_path:
        raise NotImplementedError(
            f"No form configuration registered for document_type={document_type!r}. "
            "Add a new module under backend/forms/ and register it in "
            "backend/forms/__init__.py → _REGISTERED."
        )
    if module_path in sys.modules:
        # Clear the translation cache so the reloaded module picks up any
        # changes made to the JSON translation file while the server was running.
        try:
            from backend.forms import form_engine as _fe
            _fe._TRANSLATION_CACHE.clear()
        except Exception:
            pass
        mod = importlib.reload(sys.modules[module_path])
    else:
        mod = importlib.import_module(module_path)
    return mod


def get_form_config(
    document_type: str,
    *,
    form_data: Optional[Dict[str, Any]] = None,
    force_show_all: bool = False,
    lang: str = "de",
    visible_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    Return the dynamic form configuration for *document_type*.

    Parameters
    ----------
    document_type : slug identifying the document (e.g. "wohngeld")
    form_data     : current answers collected so far; used to resolve
                    ``visible_if`` conditions (pass ``{}`` or omit for a
                    clean slate)
    force_show_all: if True, all ``visible_if`` conditions are bypassed —
                    every section and field is returned regardless of answers
    lang          : ISO 639-1 language code used for inline labels/hints
                    (de | en | tr | ar); falls back to "de" if not found
    visible_only  : if True, returns only sections whose ``visible`` flag
                    resolved to True

    Returns
    -------
    List of resolved section dicts.

    Raises
    ------
    NotImplementedError
        When *document_type* has no registered form configuration.
    """
    mod = _get_module(document_type)
    if visible_only:
        return mod.get_visible_sections(form_data, force_show_all=force_show_all, lang=lang)
    return mod.resolve_form(form_data, force_show_all=force_show_all, lang=lang)


def get_required_keys(
    document_type: str,
    *,
    force_show_all: bool = False,
) -> List[str]:
    """Return all required field keys for *document_type*."""
    mod = _get_module(document_type)
    return mod.get_required_keys(force_show_all=force_show_all)


def has_dynamic_form(document_type: str) -> bool:
    """Return True if *document_type* has a registered dynamic form module."""
    return document_type in _REGISTERED
