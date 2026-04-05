# -*- coding: utf-8 -*-
"""
utils/lang.py — Single normalization point for user language codes.

The project has two legacy conventions for Ukrainian:
  "ua" → used in backend/translations.py (TEXTS, SUPPORTED_LANGUAGES)
  "uk" → used in email_sender.py (_HTML_L10N, _TERMIN_L10N) and most handler dicts

normalize_lang() resolves both to "uk" so all email/handler paths get
a consistent canonical value.  Code that must call backend.translations.ui()
should convert back:  ui_lang = "ua" if lang == "uk" else lang
"""

_ALLOWED = frozenset(("uk", "en", "de", "pl", "tr", "ar"))


def normalize_lang(lang: str | None) -> str:
    """Return a canonical language code safe for handler dicts and email L10N.

    "ua" and "uk" both map to "uk".
    Any unknown code falls back to "en".
    Never raises.
    """
    if not lang:
        return "en"
    lang = lang.strip().lower()
    if lang in ("ua", "uk"):
        return "uk"
    if lang in _ALLOWED:
        return lang
    return "en"
