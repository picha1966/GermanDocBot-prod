"""
Spain Test Bot — city selection handler.

Shown after user taps "🔍 Check slots" in the main menu.
5 cities, 1-column layout, + Back button.

callback_data: city_barcelona / city_madrid / city_valencia / city_sevilla / city_malaga
"""

from __future__ import annotations

import logging

from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.lang_store import get_lang

logger = logging.getLogger(__name__)


# ── City display names (key → {lang: display}) ────────────────────────────────
CITIES: dict[str, dict[str, str]] = {
    "barcelona": {
        "es": "🏙 Barcelona",
        "en": "🏙 Barcelona",
        "uk": "🏙 Барселона",
        "pl": "🏙 Barcelona",
        "ro": "🏙 Barcelona",
        "ar": "🏙 برشلونة",
    },
    "madrid": {
        "es": "🏛 Madrid",
        "en": "🏛 Madrid",
        "uk": "🏛 Мадрид",
        "pl": "🏛 Madryt",
        "ro": "🏛 Madrid",
        "ar": "🏛 مدريد",
    },
    "valencia": {
        "es": "🌊 Valencia",
        "en": "🌊 Valencia",
        "uk": "🌊 Валенсія",
        "pl": "🌊 Walencja",
        "ro": "🌊 Valencia",
        "ar": "🌊 بلنسية",
    },
    "sevilla": {
        "es": "🌸 Sevilla",
        "en": "🌸 Seville",
        "uk": "🌸 Севілья",
        "pl": "🌸 Sewilla",
        "ro": "🌸 Sevilla",
        "ar": "🌸 إشبيلية",
    },
    "malaga": {
        "es": "☀️ Málaga",
        "en": "☀️ Málaga",
        "uk": "☀️ Малага",
        "pl": "☀️ Malaga",
        "ro": "☀️ Málaga",
        "ar": "☀️ مالقة",
    },
}

# ── Screen header ─────────────────────────────────────────────────────────────
_HEADER: dict[str, str] = {
    "es": "📍 <b>Selecciona la ciudad</b>\n\nElige la ciudad donde necesitas la cita:",
    "en": "📍 <b>Select city</b>\n\nChoose the city where you need the appointment:",
    "uk": "📍 <b>Оберіть місто</b>\n\nВибери місто, де потрібен запис:",
    "pl": "📍 <b>Wybierz miasto</b>\n\nWybierz miasto, w którym potrzebujesz wizyty:",
    "ro": "📍 <b>Selectează orașul</b>\n\nAlege orașul unde ai nevoie de programare:",
    "ar": "📍 <b>اختر المدينة</b>\n\nاختر المدينة التي تحتاج فيها إلى موعد:",
}

_BTN_BACK: dict[str, str] = {
    "es": "◀️ Volver al menú",
    "en": "◀️ Back to menu",
    "uk": "◀️ Назад до меню",
    "pl": "◀️ Wróć do menu",
    "ro": "◀️ Înapoi la meniu",
    "ar": "◀️ العودة للقائمة",
}


def _t(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


# ── City selection screen ─────────────────────────────────────────────────────

async def show_city_selection(message: types.Message, lang: str) -> None:
    """Show 5 city buttons in a single column + Back."""
    kb = InlineKeyboardMarkup(row_width=1)
    for city_key, names in CITIES.items():
        kb.add(InlineKeyboardButton(_t(names, lang), callback_data=f"city_{city_key}"))
    kb.add(InlineKeyboardButton(_t(_BTN_BACK, lang), callback_data="back_to_main_menu"))

    await message.answer(_t(_HEADER, lang), parse_mode="HTML", reply_markup=kb)


# ── Callbacks ─────────────────────────────────────────────────────────────────

async def handle_city_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User tapped a city button → save city, show service selection."""
    await callback.answer()

    city_key = callback.data.replace("city_", "")   # city_barcelona → barcelona
    if city_key not in CITIES:
        logger.warning("CITY_UNKNOWN | city=%s", city_key)
        return

    lang = get_lang(callback.from_user.id)
    await state.update_data(city=city_key, lang=lang)

    logger.info("CITY_SELECTED | user=%s city=%s lang=%s", callback.from_user.id, city_key, lang)

    # Delegate immediately to service selection
    from handlers.service_select import show_services
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_services(callback.message, lang, city_key, show_all=False)


# ── Registration ──────────────────────────────────────────────────────────────

def register(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(
        handle_city_selected,
        lambda c: c.data and c.data.startswith("city_") and c.data[5:] in CITIES,
        state="*",
    )
