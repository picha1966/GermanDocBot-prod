# -*- coding: utf-8 -*-
"""Post-payment Termin monitoring activation message (shared UI, no bot.py import)."""

import logging

logger = logging.getLogger(__name__)


async def send_termin_activation_message(
    bot_inst,
    user_id: int,
    city: str,
    authority: str,
    lang: str,
    plan: str = "24h",
) -> None:
    """Send confirmation + control keyboard after Termin monitoring is activated."""
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from handlers.termin import _CITY_DISPLAY_MAP, _AUTHORITY_LABELS
        from backend.termin_db import get_entitlement as _get_ent
        from utils.time_utils import get_countdown_line

        city_display = _CITY_DISPLAY_MAP.get(city, city.replace("_", " ").title())
        auth_display = _AUTHORITY_LABELS.get(authority, authority.replace("_", " ").title())

        _lang = lang if lang in ("uk", "ua", "en", "de", "pl", "tr", "ar") else "uk"
        if _lang == "ua":
            _lang = "uk"

        _ent = _get_ent(str(user_id))
        _paid_until = (_ent or {}).get("paid_until")
        _countdown = get_countdown_line(_paid_until, _lang)
        _countdown_block = f"\n{_countdown}" if _countdown else ""

        text = {
            "uk": (
                f"✅ <b>Моніторинг активовано</b>\n\n"
                f"📍 Місто: {city_display}\n"
                f"🏛 Послуга: {auth_display}"
                f"{_countdown_block}\n\n"
                f"Бот автоматично перевіряє нові слоти та повідомить вас одразу після появи Termin."
            ),
            "en": (
                f"✅ <b>Monitoring activated</b>\n\n"
                f"📍 City: {city_display}\n"
                f"🏛 Service: {auth_display}"
                f"{_countdown_block}\n\n"
                f"We automatically check new appointment slots and notify you immediately."
            ),
            "de": (
                f"✅ <b>Überwachung aktiviert</b>\n\n"
                f"📍 Stadt: {city_display}\n"
                f"🏛 Dienst: {auth_display}"
                f"{_countdown_block}\n\n"
                f"Der Bot überprüft automatisch neue Termine und benachrichtigt Sie sofort."
            ),
            "pl": (
                f"✅ <b>Monitoring aktywowany</b>\n\n"
                f"📍 Miasto: {city_display}\n"
                f"🏛 Usługa: {auth_display}"
                f"{_countdown_block}\n\n"
                f"Automatycznie sprawdzamy nowe terminy i natychmiast powiadamiamy."
            ),
            "tr": (
                f"✅ <b>İzleme etkinleştirildi</b>\n\n"
                f"📍 Şehir: {city_display}\n"
                f"🏛 Hizmet: {auth_display}"
                f"{_countdown_block}\n\n"
                f"Yeni randevuları otomatik olarak kontrol ediyor ve hemen bildirim gönderiyoruz."
            ),
            "ar": (
                f"✅ <b>تم تفعيل المراقبة</b>\n\n"
                f"📍 المدينة: {city_display}\n"
                f"🏛 الخدمة: {auth_display}"
                f"{_countdown_block}\n\n"
                f"نتحقق تلقائيًا من المواعيد الجديدة وسنبلغك فورًا."
            ),
        }.get(
            _lang,
            (
                f"✅ <b>Monitoring activated</b>\n\n"
                f"📍 City: {city_display}\n"
                f"🏛 Service: {auth_display}"
                f"{_countdown_block}\n\n"
                f"We automatically check new appointment slots and notify you immediately."
            ),
        )

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton(
                {
                    "uk": "🔎 Статус моніторингу",
                    "en": "🔎 Monitoring status",
                    "de": "🔎 Überwachungsstatus",
                    "pl": "🔎 Status monitoringu",
                    "tr": "🔎 İzleme durumu",
                    "ar": "🔎 حالة المراقبة",
                }.get(_lang, "🔎 Monitoring status"),
                callback_data="termin_status",
            )
        )
        kb.add(
            InlineKeyboardButton(
                {
                    "uk": "⏹ Зупинити моніторинг",
                    "en": "⏹ Stop monitoring",
                    "de": "⏹ Überwachung stoppen",
                    "pl": "⏹ Zatrzymaj monitoring",
                    "tr": "⏹ İzlemeyi durdur",
                    "ar": "⏹ إيقاف المراقبة",
                }.get(_lang, "⏹ Stop monitoring"),
                callback_data="termin_pause",
            )
        )
        kb.add(
            InlineKeyboardButton(
                {
                    "uk": "🏠 Головне меню",
                    "en": "🏠 Main menu",
                    "de": "🏠 Hauptmenü",
                    "pl": "🏠 Menu główne",
                    "tr": "🏠 Ana menü",
                    "ar": "🏠 القائمة الرئيسية",
                }.get(_lang, "🏠 Main menu"),
                callback_data="back_to_main_menu",
            )
        )

        await bot_inst.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
        logger.info(
            "TERMIN_MONITOR_ACTIVATED | user=%s city=%s auth=%s plan=%s",
            user_id,
            city,
            authority,
            plan,
        )
    except Exception as _msg_err:
        logger.warning(
            "TERMIN_ACTIVATION_MSG_FAILED | user=%s err=%s", user_id, _msg_err
        )
