"""
Simple in-memory language store for the Spain Test Bot.
No DB required — test bot only.  Thread-safe for asyncio (single event-loop).
"""

from __future__ import annotations

_store: dict[int, str] = {}

SUPPORTED_LANGUAGES = ("es", "en", "uk", "pl", "ro", "ar")
DEFAULT_LANGUAGE    = "es"


def set_lang(user_id: int, lang: str) -> None:
    _store[user_id] = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def get_lang(user_id: int) -> str:
    return _store.get(user_id, DEFAULT_LANGUAGE)
