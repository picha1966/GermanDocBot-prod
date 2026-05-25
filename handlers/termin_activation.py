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
) -> bool:
    """Send confirmation + control keyboard after Termin monitoring is activated.

    Returns True if the Telegram message was delivered successfully, False otherwise.
    Callers must only call mark_order_delivered() when this returns True.
    """
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from handlers.termin import _CITY_DISPLAY_MAP, _AUTHORITY_LABELS
        from backend.termin_db import get_entitlement as _get_ent
        from utils.time_utils import get_countdown_line

        city_display = _CITY_DISPLAY_MAP.get(city, city.replace("_", " ").title())
        auth_display = _AUTHORITY_LABELS.get(authority, authority.replace("_", " ").title())

        _lang = lang if lang in ("uk", "ua", "en", "de", "pl", "tr", "ar") else "en"
        if _lang == "ua":
            _lang = "uk"

        _ent = _get_ent(str(user_id))
        _paid_until = (_ent or {}).get("paid_until")
        _countdown = get_countdown_line(_paid_until, _lang)
        _countdown_block = f"\n{_countdown}" if _countdown else ""

        _is_muenchen = (city or "").lower().strip() in ("muenchen", "münchen", "munich")

        if _is_muenchen:
            logger.info(
                "MUENCHEN_MANUAL_ONLY_MODE | user=%s city=%s authority=%s action=activation_message",
                user_id, city, authority,
            )
            # München: portal assistant mode — do NOT claim automatic slot detection.
            _portal_url = "https://www48.muenchen.de/buergeransicht/"
            text = {
                "uk": (
                    f"✅ <b>Готово! Портал-асистент активний.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🗺 Бот надає офіційне посилання та інструкцію для ручного запису.\n"
                    f"🔗 Офіційний портал: {_portal_url}\n\n"
                    f"ℹ️ Перевіряйте наявність слотів вручну: Пн–Пт 7–8 та 9–11 ранку."
                ),
                "en": (
                    f"✅ <b>All set! Portal assistant active.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🗺 The bot provides the official link and step-by-step booking instructions.\n"
                    f"🔗 Official portal: {_portal_url}\n\n"
                    f"ℹ️ Check for slots manually: Mon–Fri 7–8 AM and 9–11 AM."
                ),
                "de": (
                    f"✅ <b>Fertig! Portal-Assistent aktiv.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🗺 Der Bot stellt den offiziellen Link und Anleitung zur Verfügung.\n"
                    f"🔗 Offizielles Portal: {_portal_url}\n\n"
                    f"ℹ️ Freie Termine manuell prüfen: Mo–Fr 7–8 und 9–11 Uhr."
                ),
                "pl": (
                    f"✅ <b>Gotowe! Asystent portalu aktywny.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🗺 Bot dostarcza oficjalny link i instrukcję rezerwacji krok po kroku.\n"
                    f"🔗 Oficjalny portal: {_portal_url}\n\n"
                    f"ℹ️ Sprawdzaj sloty ręcznie: Pn–Pt 7–8 i 9–11 rano."
                ),
                "tr": (
                    f"✅ <b>Hazır! Portal asistanı aktif.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🗺 Bot, resmi bağlantıyı ve adım adım rezervasyon talimatlarını sağlar.\n"
                    f"🔗 Resmi portal: {_portal_url}\n\n"
                    f"ℹ️ Slotları manuel kontrol edin: Pzt–Cum 7–8 ve 9–11."
                ),
                "ar": (
                    f"✅ <b>جاهز! مساعد البوابة نشط.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🗺 يوفر البوت الرابط الرسمي وتعليمات الحجز خطوة بخطوة.\n"
                    f"🔗 البوابة الرسمية: {_portal_url}\n\n"
                    f"ℹ️ تحقق من المواعيد يدويًا: الاثنين–الجمعة 7–8 و9–11 صباحًا."
                ),
            }.get(_lang, (
                f"✅ <b>All set! Portal assistant active.</b>\n\n"
                f"📍 {city_display}\n"
                f"🏛 {auth_display}"
                f"{_countdown_block}\n\n"
                f"🗺 The bot provides the official link and step-by-step booking instructions.\n"
                f"🔗 Official portal: {_portal_url}\n\n"
                f"ℹ️ Check for slots manually: Mon–Fri 7–8 AM and 9–11 AM."
            ))
        else:
            _social_proof = {
                "uk": "👥 2 400+ людей вже знайшли Termin через наш сервіс",
                "en": "👥 2,400+ people have already found their Termin",
                "de": "👥 Über 2.400 Personen haben bereits ihren Termin gefunden",
                "pl": "👥 Ponad 2 400 osób już znalazło swój Termin",
                "tr": "👥 2.400+ kişi zaten randevusunu buldu",
                "ar": "👥 أكثر من 2,400 شخص وجدوا موعدهم بالفعل",
            }.get(_lang, "👥 2,400+ people have already found their Termin")

            text = {
                "uk": (
                    f"🚀 <b>Все готово! Моніторинг запущено.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🔄 Ми вже перевіряємо слоти\n"
                    f"⏳ Перші результати — протягом 1–2 хвилин\n\n"
                    f"{_social_proof}"
                ),
                "en": (
                    f"🚀 <b>All set! Monitoring is running.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🔄 Already checking slots\n"
                    f"⏳ First results may appear within 1–2 minutes\n\n"
                    f"{_social_proof}"
                ),
                "de": (
                    f"🚀 <b>Alles bereit! Monitoring läuft.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🔄 Wir prüfen bereits Termine\n"
                    f"⏳ Erste Ergebnisse in 1–2 Minuten\n\n"
                    f"{_social_proof}"
                ),
                "pl": (
                    f"🚀 <b>Gotowe! Monitoring uruchomiony.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🔄 Już sprawdzamy terminy\n"
                    f"⏳ Pierwsze wyniki mogą pojawić się w ciągu 1–2 minut\n\n"
                    f"{_social_proof}"
                ),
                "tr": (
                    f"🚀 <b>Hazır! İzleme başlatıldı.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🔄 Randevular zaten kontrol ediliyor\n"
                    f"⏳ İlk sonuçlar 1–2 dakika içinde gelebilir\n\n"
                    f"{_social_proof}"
                ),
                "ar": (
                    f"🚀 <b>جاهز! بدأت المراقبة.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🔄 نفحص المواعيد بالفعل\n"
                    f"⏳ قد تظهر النتائج الأولى خلال 1–2 دقيقة\n\n"
                    f"{_social_proof}"
                ),
            }.get(
                _lang,
                (
                    f"🚀 <b>All set! Monitoring is running.</b>\n\n"
                    f"📍 {city_display}\n"
                    f"🏛 {auth_display}"
                    f"{_countdown_block}\n\n"
                    f"🔄 Already checking slots\n"
                    f"⏳ First results may appear within 1–2 minutes\n\n"
                    f"{_social_proof}"
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
        return True
    except Exception as _msg_err:
        logger.error(
            "TERMIN_ACTIVATION_MSG_FAILED | user=%s city=%s auth=%s plan=%s err=%s "
            "— activation message NOT delivered; mark_order_delivered must NOT be called",
            user_id, city, authority, plan, _msg_err,
        )
        return False
