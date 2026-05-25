# -*- coding: utf-8 -*-
"""
handlers/nav.py — Centralized navigation helpers for GermanDocBot.

Supported languages: uk, en, de, tr, pl, ar
NO Russian (ru) support — by design.

Usage:
    from handlers.nav import with_navigation, nav_home_text, nav_back_text, make_nav_kb

    # Add Back + Main Menu to any keyboard list:
    kb = with_navigation([
        InlineKeyboardButton("Some action", callback_data="some_cb"),
    ], lang=lang)

    # Minimal two-button nav keyboard:
    kb = make_nav_kb(lang, back_cb="some_back_callback")
"""

from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------------------------------------------------------
# Canonical label dicts — ONLY 6 supported languages
# ---------------------------------------------------------------------------

MAIN_MENU_LABELS: dict = {
    "uk": "🏠 Головне меню",
    "en": "🏠 Main Menu",
    "de": "🏠 Hauptmenü",
    "tr": "🏠 Ana Menü",
    "pl": "🏠 Menu główne",
    "ar": "🏠 القائمة الرئيسية",
}

BACK_LABELS: dict = {
    "uk": "⬅️ Назад",
    "en": "⬅️ Back",
    "de": "⬅️ Zurück",
    "tr": "⬅️ Geri",
    "pl": "⬅️ Wstecz",
    "ar": "⬅️ رجوع",
}

# Canonical callback_data values
CB_MAIN_MENU = "main_menu"
CB_BACK_MENU = "back_to_main_menu"

_SUPPORTED = frozenset(MAIN_MENU_LABELS.keys())


def _norm_lang(lang: Optional[str]) -> str:
    """Normalize a language code to one of the 6 supported languages."""
    if not lang:
        return "uk"
    lang = lang.strip().lower()
    # Map legacy aliases — no Russian
    if lang in ("ua",):
        return "uk"
    return lang if lang in _SUPPORTED else "uk"


def nav_home_text(lang: Optional[str]) -> str:
    """Return the localized 'Main Menu' button label."""
    return MAIN_MENU_LABELS.get(_norm_lang(lang), MAIN_MENU_LABELS["en"])


def nav_back_text(lang: Optional[str]) -> str:
    """Return the localized 'Back' button label."""
    return BACK_LABELS.get(_norm_lang(lang), BACK_LABELS["en"])


def with_navigation(
    buttons: List[InlineKeyboardButton],
    lang: Optional[str],
    back_cb: str = CB_BACK_MENU,
    home_cb: str = CB_MAIN_MENU,
    row_width: int = 1,
) -> InlineKeyboardMarkup:
    """
    Build an InlineKeyboardMarkup from *buttons* and append:
      - ⬅️ Back  →  back_cb
      - 🏠 Main Menu  →  home_cb

    Args:
        buttons: List of InlineKeyboardButton for the content area.
        lang: User language code (uk/en/de/tr/pl/ar).
        back_cb: callback_data for the Back button.
        home_cb: callback_data for the Main Menu button.
        row_width: Row width for the keyboard (default 1).

    Returns:
        InlineKeyboardMarkup with content buttons + nav buttons appended.
    """
    _lang = _norm_lang(lang)
    kb = InlineKeyboardMarkup(row_width=row_width)
    for btn in buttons:
        kb.add(btn)
    kb.add(InlineKeyboardButton(nav_back_text(_lang), callback_data=back_cb))
    kb.add(InlineKeyboardButton(nav_home_text(_lang), callback_data=home_cb))
    return kb


def make_nav_kb(
    lang: Optional[str],
    back_cb: str = CB_BACK_MENU,
    home_cb: str = CB_MAIN_MENU,
) -> InlineKeyboardMarkup:
    """
    Minimal two-button navigation keyboard:
      - ⬅️ Back  →  back_cb
      - 🏠 Main Menu  →  home_cb

    Use this when a screen has no other buttons (error pages, dead-end confirmations).
    """
    _lang = _norm_lang(lang)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(nav_back_text(_lang), callback_data=back_cb))
    kb.add(InlineKeyboardButton(nav_home_text(_lang), callback_data=home_cb))
    return kb


def add_home_button(
    kb: InlineKeyboardMarkup,
    lang: Optional[str],
    home_cb: str = CB_MAIN_MENU,
) -> InlineKeyboardMarkup:
    """
    Append only the 🏠 Main Menu button to an existing keyboard.

    Use when a screen already has a Back button but is missing the Home button.
    """
    kb.add(InlineKeyboardButton(nav_home_text(lang), callback_data=home_cb))
    return kb
