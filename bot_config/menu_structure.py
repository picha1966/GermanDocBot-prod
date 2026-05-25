# -*- coding: utf-8 -*-
"""
config/menu_structure.py — Single source of truth for bot menu hierarchy.

Defines categories, which doc_types belong to each category,
localized labels, and helper utilities.
"""
from __future__ import annotations
from typing import Dict, List, Set

# ---------------------------------------------------------------------------
# Core Launch Pack — documents that have a WebApp form schema and are
# fully supported end-to-end (questionnaire → PDF → payment).
# Only these are shown in the Telegram menu.
# ---------------------------------------------------------------------------
CORE_LAUNCH_DOCS: List[str] = [
    # Registration & Housing
    "anmeldung",
    "wohnungsgeberbestaetigung",
    "mietbescheinigung",
    # Benefits & Family
    "buergergeld",
    "kindergeld",
    "wohngeld",
    # Residence & Migration
    "aufenthaltstitel",
]

# ---------------------------------------------------------------------------
# Documents grouped by category.
# ONLY documents present in DOCUMENT_FORM_SCHEMAS (backend/document_config.py)
# are listed here — they have a complete WebApp questionnaire.
# All other doc_types remain in the codebase but are not shown in the menu.
# ---------------------------------------------------------------------------
CATEGORY_DOCS: Dict[str, List[str]] = {
    "residence": [
        "anmeldung",
        "wohnungsgeberbestaetigung",
        "mietbescheinigung",
        "aufenthaltstitel",
    ],
    "benefits": [
        "buergergeld",
        "kindergeld",
        "wohngeld",
    ],
    # Telegram UI category — 3 financial benefit docs shown under 💰 menu
    "financial": [
        "kindergeld",
        "wohngeld",
        "buergergeld",
    ],
}

# Termin-only order types (payment for monitoring; no PDF document delivery)
TERMIN_DOC_TYPES: Set[str] = {
    "termin_notifications",
    "termin_monitor_24h",
    "termin_extend_24h",
    "termin_priority_boost",
}

# ---------------------------------------------------------------------------
# Reverse map: doc_type → category
# ---------------------------------------------------------------------------
DOC_CATEGORY: Dict[str, str] = {}
for _cat, _docs in CATEGORY_DOCS.items():
    for _doc in _docs:
        DOC_CATEGORY[_doc] = _cat

# ---------------------------------------------------------------------------
# Localized category labels used in menus
# ---------------------------------------------------------------------------
CATEGORY_LABELS: Dict[str, Dict[str, str]] = {
    "residence": {
        "uk": "🏠 Реєстрація та проживання",
        "ua": "🏠 Реєстрація та проживання",
        "en": "🏠 Registration & Housing",
        "de": "🏠 Anmeldung & Wohnen",
        "pl": "🏠 Rejestracja i zamieszkanie",
        "tr": "🏠 Kayıt ve Konut",
        "ar": "🏠 التسجيل والسكن",
    },
    "financial": {
        "uk": "💰 Фінансові документи",
        "ua": "💰 Фінансові документи",
        "en": "💰 Financial Documents",
        "de": "💰 Finanzielle Dokumente",
        "pl": "💰 Dokumenty finansowe",
        "tr": "💰 Finansal Belgeler",
        "ar": "💰 الوثائق المالية",
    },
    "benefits": {
        "uk": "💰 Виплати та підтримка",
        "ua": "💰 Виплати та підтримка",
        "en": "💰 Benefits & Support",
        "de": "💰 Leistungen & Unterstützung",
        "pl": "💰 Świadczenia i wsparcie",
        "tr": "💰 Yardımlar ve Destek",
        "ar": "💰 المزايا والدعم",
    },
    "termin": {
        "uk": "📅 Знайти Termin",
        "ua": "📅 Знайти Termin",
        "en": "📅 Find Appointment",
        "de": "📅 Termin finden",
        "pl": "📅 Znajdź wizytę",
        "tr": "📅 Randevu Bul",
        "ar": "📅 إيجاد موعد",
    },
}

# Localized "My Documents" section titles per category
MY_DOCS_CATEGORY_TITLES: Dict[str, Dict[str, str]] = {
    "residence": {
        "uk": "🏠 Реєстрація та проживання",
        "ua": "🏠 Реєстрація та проживання",
        "en": "🏠 Registration & Housing",
        "de": "🏠 Anmeldung & Wohnen",
        "pl": "🏠 Rejestracja i zamieszkanie",
        "tr": "🏠 Kayıt ve Konut",
        "ar": "🏠 التسجيل والسكن",
    },
    "benefits": {
        "uk": "💰 Виплати та підтримка",
        "ua": "💰 Виплати та підтримка",
        "en": "💰 Benefits & Support",
        "de": "💰 Leistungen",
        "pl": "💰 Świadczenia",
        "tr": "💰 Yardımlar",
        "ar": "💰 المزايا",
    },
    "termin": {
        "uk": "📅 Termin (платні послуги)",
        "ua": "📅 Termin (платні послуги)",
        "en": "📅 Appointments (paid)",
        "de": "📅 Termin (kostenpflichtig)",
        "pl": "📅 Wizyty (płatne)",
        "tr": "📅 Randevular (ücretli)",
        "ar": "📅 المواعيد (مدفوعة)",
    },
    "other": {
        "uk": "📄 Інші документи",
        "ua": "📄 Інші документи",
        "en": "📄 Other documents",
        "de": "📄 Sonstige Dokumente",
        "pl": "📄 Inne dokumenty",
        "tr": "📄 Diğer belgeler",
        "ar": "📄 وثائق أخرى",
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_doc_category(doc_type: str) -> str:
    """Return category name for a doc_type, or 'other' if unknown."""
    if doc_type in TERMIN_DOC_TYPES:
        return "termin"
    return DOC_CATEGORY.get(doc_type, "other")


def get_category_label(category: str, lang: str) -> str:
    """Return localized display label for a category button."""
    _lang = lang if lang != "uk" else "uk"
    labels = CATEGORY_LABELS.get(category, {})
    return labels.get(_lang, labels.get("en", category))


def get_category_docs(category: str) -> List[str]:
    """Return list of doc_types for a given category."""
    return CATEGORY_DOCS.get(category, [])


def is_core_doc(doc_type: str) -> bool:
    """Return True if doc_type is part of the Core Launch Pack."""
    return doc_type in CORE_LAUNCH_DOCS


def get_core_docs_for_category(category: str) -> List[str]:
    """Return only the core docs that belong to a given category."""
    return [d for d in CATEGORY_DOCS.get(category, []) if d in CORE_LAUNCH_DOCS]
