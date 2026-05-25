"""
Spain Test Bot — monitoring UX handlers.

Callbacks:
  start_monitor   → start background monitoring, show confirmation
  stop_monitor    → stop monitoring, show stopped message
  monitor_status  → show current status screen
  i_booked        → user booked after alert — stop + celebrate
"""

from __future__ import annotations

import logging

from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.lang_store import get_lang
from utils import monitoring as mon

logger = logging.getLogger(__name__)


def _t(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


# ── Shared city / service display helpers ─────────────────────────────────────
# (importing display dicts here avoids duplication)

def _city_name(city_key: str, lang: str) -> str:
    from handlers.city_select import CITIES, _t as _ct
    return _ct(CITIES.get(city_key, {"en": city_key.title()}), lang)


def _svc_name(svc_key: str, lang: str) -> str:
    from handlers.service_select import SERVICES, _t as _st
    svc = SERVICES.get(svc_key, {})
    return _st(svc.get("labels", {"en": svc_key}), lang)


# ── Confirmation screen texts ─────────────────────────────────────────────────

_CONFIRM: dict[str, str] = {
    "es": (
        "🚀 <b>¡Monitoreo iniciado!</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🔄 Ya estamos comprobando el sitio ahora mismo\n"
        "⚡ Te avisaremos al instante cuando aparezca una cita\n"
        "⏱ Próxima verificación en ~30–60 segundos\n\n"
        "👉 Puedes cerrar el bot — te notificaremos de todas formas"
    ),
    "en": (
        "🚀 <b>Monitoring started!</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🔄 We are already checking the site right now\n"
        "⚡ You will be notified instantly when an appointment (cita) appears\n"
        "⏱ Next check in ~30–60 seconds\n\n"
        "👉 You can close the bot — we will notify you anyway"
    ),
    "uk": (
        "🚀 <b>Моніторинг запущено!</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🔄 Ми вже перевіряємо сайт прямо зараз\n"
        "⚡ Повідомимо миттєво, щойно з'явиться вільний запис (cita)\n"
        "⏱ Наступна перевірка через ~30–60 секунд\n\n"
        "👉 Можеш закрити бот — ми все одно повідомимо"
    ),
    "pl": (
        "🚀 <b>Monitoring uruchomiony!</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🔄 Już sprawdzamy stronę właśnie teraz\n"
        "⚡ Powiadomimy Cię natychmiast, gdy pojawi się termin (cita)\n"
        "⏱ Następne sprawdzenie za ~30–60 sekund\n\n"
        "👉 Możesz zamknąć bota — i tak Cię powiadomimy"
    ),
    "ro": (
        "🚀 <b>Monitorizare pornită!</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🔄 Verificăm deja site-ul chiar acum\n"
        "⚡ Vei fi notificat imediat când apare o programare (cita)\n"
        "⏱ Următoarea verificare în ~30–60 secunde\n\n"
        "👉 Poți închide botul — te vom notifica oricum"
    ),
    "ar": (
        "🚀 <b>بدأت المراقبة!</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🔄 نحن نفحص الموقع الآن مباشرة\n"
        "⚡ ستُخطر فوراً عند ظهور موعد (cita)\n"
        "⏱ الفحص التالي خلال ~30–60 ثانية\n\n"
        "👉 يمكنك إغلاق البوت — سنخطرك على أي حال"
    ),
}

# ── Status screen texts ───────────────────────────────────────────────────────

_STATUS_ACTIVE: dict[str, str] = {
    "es": (
        "📊 <b>Estado de la búsqueda</b>\n\n"
        "🟢 Activo\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🎯 Citas restantes: <b>{time_left}</b> (1 cita = 1 notificación)\n"
        "🔄 Última verificación: {last}\n"
        "⏭ Próxima verificación: {next}\n\n"
        "🔄 Revisamos el sitio cada 30–60 segundos\n"
        "📲 En cuanto aparezca una cita — recibirás una notificación\n"
        "⚠️ Las citas pueden desaparecer en 1–2 minutos\n\n"
        "👉 Puedes cerrar el bot — te avisaremos igual"
    ),
    "en": (
        "📊 <b>Search status</b>\n\n"
        "🟢 Active\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🎯 Appointments remaining: <b>{time_left}</b> (1 find = 1 notification)\n"
        "🔄 Last check: {last}\n"
        "⏭ Next check: {next}\n\n"
        "🔄 We check the site every 30–60 seconds\n"
        "📲 As soon as an appointment appears — you'll be notified instantly\n"
        "⚠️ Appointments can disappear within 1–2 minutes\n\n"
        "👉 You can close the bot — we'll notify you anyway"
    ),
    "uk": (
        "📊 <b>Статус пошуку</b>\n\n"
        "🟢 Активний\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🎯 Залишилось спроб: <b>{time_left}</b> (1 спроба = 1 знайдений запис)\n"
        "🔄 Остання перевірка: {last}\n"
        "⏭ Наступна перевірка: {next}\n\n"
        "🔄 Ми перевіряємо сайт кожні 30–60 секунд\n"
        "📲 Як тільки з'явиться запис — ти одразу отримаєш повідомлення\n"
        "⚠️ Записи можуть зникнути за 1–2 хвилини\n\n"
        "👉 Можеш закрити бот — ми все одно повідомимо"
    ),
    "pl": (
        "📊 <b>Status wyszukiwania</b>\n\n"
        "🟢 Aktywny\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🎯 Pozostałe terminy: <b>{time_left}</b> (1 próba = 1 znaleziony termin)\n"
        "🔄 Ostatnie sprawdzenie: {last}\n"
        "⏭ Następne sprawdzenie: {next}\n\n"
        "🔄 Sprawdzamy stronę co 30–60 sekund\n"
        "📲 Gdy tylko pojawi się termin — otrzymasz powiadomienie\n"
        "⚠️ Terminy mogą zniknąć w ciągu 1–2 minut\n\n"
        "👉 Możesz zamknąć bota — i tak Cię powiadomimy"
    ),
    "ro": (
        "📊 <b>Status căutare</b>\n\n"
        "🟢 Activ\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🎯 Programări rămase: <b>{time_left}</b> (1 încercare = 1 programare găsită)\n"
        "🔄 Ultima verificare: {last}\n"
        "⏭ Următoarea verificare: {next}\n\n"
        "🔄 Verificăm site-ul la fiecare 30–60 secunde\n"
        "📲 Imediat ce apare o programare — vei fi notificat\n"
        "⚠️ Programările pot dispărea în 1–2 minute\n\n"
        "👉 Poți închide botul — te vom anunța oricum"
    ),
    "ar": (
        "📊 <b>حالة البحث</b>\n\n"
        "🟢 نشطة\n"
        "📍 {city}\n"
        "📄 {service}\n\n"
        "🎯 المواعيد المتبقية: <b>{time_left}</b> (محاولة واحدة = موعد واحد مُوجَد)\n"
        "🔄 آخر فحص: {last}\n"
        "⏭ الفحص التالي: {next}\n\n"
        "🔄 نقوم بفحص الموقع كل 30–60 ثانية\n"
        "📲 بمجرد ظهور موعد — سيتم إشعارك فورًا\n"
        "⚠️ قد تختفي المواعيد خلال 1–2 دقيقة\n\n"
        "👉 يمكنك إغلاق البوت — سنقوم بإعلامك على أي حال"
    ),
}

_STATUS_NONE: dict[str, str] = {
    "es": "📊 No hay monitoreo activo.\n\nVuelve al menú para iniciar una búsqueda.",
    "en": "📊 No active monitoring.\n\nReturn to menu to start a search.",
    "uk": "📊 Моніторинг не запущено.\n\nПовернись до меню, щоб почати пошук.",
    "pl": "📊 Brak aktywnego monitoringu.\n\nWróć do menu, aby rozpocząć wyszukiwanie.",
    "ro": "📊 Nu există monitorizare activă.\n\nRevino la meniu pentru a începe o căutare.",
    "ar": "📊 لا توجد مراقبة نشطة.\n\nعُد إلى القائمة لبدء البحث.",
}

# ── Stop screen ───────────────────────────────────────────────────────────────

_STOPPED: dict[str, str] = {
    "es": (
        "⛔ <b>Monitoreo detenido</b>\n\n"
        "Puedes iniciar una nueva búsqueda en cualquier momento."
    ),
    "en": (
        "⛔ <b>Monitoring stopped</b>\n\n"
        "You can start a new search at any time."
    ),
    "uk": (
        "⛔ <b>Моніторинг зупинено</b>\n\n"
        "Можеш розпочати новий пошук будь-коли."
    ),
    "pl": (
        "⛔ <b>Monitoring zatrzymany</b>\n\n"
        "Możesz rozpocząć nowe wyszukiwanie w dowolnym momencie."
    ),
    "ro": (
        "⛔ <b>Monitorizare oprită</b>\n\n"
        "Poți începe o nouă căutare oricând."
    ),
    "ar": (
        "⛔ <b>توقفت المراقبة</b>\n\n"
        "يمكنك بدء بحث جديد في أي وقت."
    ),
}

# ── Booked celebration ────────────────────────────────────────────────────────

_BOOKED: dict[str, str] = {
    "es": "🎉 <b>¡Felicidades!</b>\n\nMonitoreo detenido. ¡Buena suerte con tu cita! 🍀",
    "en": "🎉 <b>Congratulations!</b>\n\nMonitoring stopped. Good luck with your appointment! 🍀",
    "uk": "🎉 <b>Вітаємо!</b>\n\nМоніторинг зупинено. Успіхів на записі! 🍀",
    "pl": "🎉 <b>Gratulacje!</b>\n\nMonitoring zatrzymany. Powodzenia! 🍀",
    "ro": "🎉 <b>Felicitări!</b>\n\nMonitorizare oprită. Mult succes la programare! 🍀",
    "ar": "🎉 <b>تهانينا!</b>\n\nتوقفت المراقبة. حظاً موفقاً في موعدك! 🍀",
}

# ── Button labels ─────────────────────────────────────────────────────────────

_BTN_STATUS: dict[str, str] = {
    "es": "📊 Estado",
    "en": "📊 Status",
    "uk": "📊 Статус",
    "pl": "📊 Status",
    "ro": "📊 Status",
    "ar": "📊 الحالة",
}

_BTN_STOP: dict[str, str] = {
    "es": "⛔ Detener monitoreo",
    "en": "⛔ Stop monitoring",
    "uk": "⛔ Зупинити моніторинг",
    "pl": "⛔ Zatrzymaj monitoring",
    "ro": "⛔ Oprește monitorizarea",
    "ar": "⛔ إيقاف المراقبة",
}

_BTN_MENU: dict[str, str] = {
    "es": "🏠 Menú principal",
    "en": "🏠 Main menu",
    "uk": "🏠 Головне меню",
    "pl": "🏠 Menu główne",
    "ro": "🏠 Meniu principal",
    "ar": "🏠 القائمة الرئيسية",
}

_BTN_RESTART: dict[str, str] = {
    "es": "🔄 Buscar de nuevo",
    "en": "🔄 Search again",
    "uk": "🔄 Шукати знову",
    "pl": "🔄 Szukaj ponownie",
    "ro": "🔄 Caută din nou",
    "ar": "🔄 ابحث مجدداً",
}

_BTN_BACK_MENU: dict[str, str] = {
    "es": "◀️ Volver al menú",
    "en": "◀️ Back to menu",
    "uk": "◀️ Назад до меню",
    "pl": "◀️ Wróć do menu",
    "ro": "◀️ Înapoi la meniu",
    "ar": "◀️ العودة للقائمة",
}


def _monitor_kb(lang: str) -> InlineKeyboardMarkup:
    """Active monitoring controls: Status / Stop / Main menu."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_STATUS, lang), callback_data="monitor_status"))
    kb.add(InlineKeyboardButton(_t(_BTN_STOP,   lang), callback_data="stop_monitor"))
    kb.add(InlineKeyboardButton(_t(_BTN_MENU,   lang), callback_data="back_to_main_menu"))
    return kb


def _stopped_kb(lang: str) -> InlineKeyboardMarkup:
    """Post-stop controls: Search again / Main menu."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_RESTART, lang), callback_data="check_slots"))
    kb.add(InlineKeyboardButton(_t(_BTN_MENU,    lang), callback_data="back_to_main_menu"))
    return kb


def _back_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_BACK_MENU, lang), callback_data="back_to_main_menu"))
    return kb


# ── Handlers ─────────────────────────────────────────────────────────────────

async def handle_start_monitor(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start background monitoring — only if user has an active paid plan."""
    await callback.answer()
    lang = get_lang(callback.from_user.id)

    # ── Payment gate ──────────────────────────────────────────────────────────
    try:
        from utils.payments import is_paid
        if not is_paid(callback.from_user.id):
            try:
                await callback.message.delete()
            except Exception:
                pass
            from handlers.payment_handlers import show_pricing_screen
            await show_pricing_screen(callback.message, lang)
            return
    except ImportError:
        pass   # payments module not available in dev — allow free access

    data = await state.get_data()

    city    = data.get("city")
    svc_key = data.get("svc")

    if not city or not svc_key:
        logger.warning("START_MONITOR_NO_STATE | user=%s data=%s", callback.from_user.id, data)
        await callback.message.answer(
            _t(_STATUS_NONE, lang),
            parse_mode="HTML",
            reply_markup=_back_kb(lang),
        )
        return

    from handlers.service_select import SERVICES
    authority    = SERVICES[svc_key]["authority"]
    city_display = _city_name(city, lang)
    svc_display  = _svc_name(svc_key, lang)

    await mon.start_monitoring(
        bot=callback.message.bot,
        user_id=callback.from_user.id,
        city=city,
        svc=svc_key,
        authority=authority,
        city_display=city_display,
        svc_display=svc_display,
        lang=lang,
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    text = _t(_CONFIRM, lang).format(city=city_display, service=svc_display)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=_monitor_kb(lang))
    logger.info("START_MONITOR | user=%s city=%s svc=%s", callback.from_user.id, city, svc_key)


async def handle_stop_monitor(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Stop active monitoring session."""
    await callback.answer()
    lang = get_lang(callback.from_user.id)
    mon.stop_monitoring(callback.from_user.id)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        _t(_STOPPED, lang),
        parse_mode="HTML",
        reply_markup=_stopped_kb(lang),
    )
    logger.info("STOP_MONITOR | user=%s", callback.from_user.id)


async def handle_monitor_status(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show live status of the current monitoring session."""
    await callback.answer()
    uid  = callback.from_user.id
    lang = get_lang(uid)

    # ── BUG FIX: if paid but session was lost (bot restart etc.) → restart ────
    if not mon.is_monitoring(uid):
        try:
            from utils.payments import is_paid, get_record
            if is_paid(uid):
                record = get_record(uid)
                if record and record.get("city") and record.get("service"):
                    city_key = record["city"]
                    svc_key  = record["service"]
                    city_display = city_key.title()
                    svc_display  = svc_key
                    authority    = svc_key

                    try:
                        city_display = _city_name(city_key, lang)
                        svc_display  = _svc_name(svc_key, lang)
                        from handlers.service_select import SERVICES
                        authority = SERVICES.get(svc_key, {}).get("authority", svc_key)
                    except Exception:
                        pass

                    await state.update_data(city=city_key, svc=svc_key)
                    try:
                        await mon.start_monitoring(
                            bot=callback.bot,
                            user_id=uid,
                            city=city_key,
                            svc=svc_key,
                            authority=authority,
                            city_display=city_display,
                            svc_display=svc_display,
                            lang=lang,
                        )
                        logger.info("STATUS_MONITOR_RESTARTED | user=%s city=%s svc=%s", uid, city_key, svc_key)
                    except Exception as _exc:
                        logger.warning("STATUS_MONITOR_RESTART_FAILED | user=%s err=%s", uid, _exc)
        except Exception as _outer_exc:
            logger.warning("STATUS_PAID_CHECK_FAILED | user=%s err=%s", uid, _outer_exc)

    session = mon.get_session(uid)

    if not session:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            _t(_STATUS_NONE, lang),
            parse_mode="HTML",
            reply_markup=_back_kb(lang),
        )
        return

    city_display = session["city_display"]
    svc_display  = session["svc_display"]
    last_str     = mon.human_last(session["last_check_ts"], lang)
    next_str     = mon.human_next(session["next_check_ts"], lang)

    # Resolve remaining attempts count (inline in template)
    time_left_str = "—"
    try:
        from utils.payments import time_remaining
        remaining = time_remaining(uid, lang)
        if remaining:
            time_left_str = remaining
    except Exception:
        pass

    text = _t(_STATUS_ACTIVE, lang).format(
        city=city_display,
        service=svc_display,
        last=last_str,
        next=next_str,
        time_left=time_left_str,
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(text, parse_mode="HTML", reply_markup=_monitor_kb(lang))


async def handle_i_booked(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User confirmed they booked after receiving an alert — celebrate + stop."""
    await callback.answer()
    lang = get_lang(callback.from_user.id)
    mon.stop_monitoring(callback.from_user.id)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(
        _t(_BOOKED, lang),
        parse_mode="HTML",
        reply_markup=_back_kb(lang),
    )
    logger.info("I_BOOKED | user=%s", callback.from_user.id)


async def handle_missed_appointment(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User missed the appointment — show remaining attempts, monitoring continues."""
    await callback.answer()
    uid  = callback.from_user.id
    lang = get_lang(uid)

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    from utils.payments import get_attempts_left
    n = get_attempts_left(uid)

    _s_map = {
        "es": "s" if n != 1 else "",
        "en": "s" if n != 1 else "",
        "uk": "и" if n in (2, 3, 4) else "",
        "pl": "y" if n in (2, 3, 4) else "",
        "ro": "i" if n != 1 else "e",
        "ar": "",
    }
    s = _s_map.get(lang, "")

    from utils.monitoring import _MISSED_REPLY, _BTN_BUY_MORE

    if n > 0:
        text = _t(_MISSED_REPLY, lang).format(n=n, s=s)
        kb   = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(_t(_BTN_STATUS, lang), callback_data="monitor_status"))
        kb.add(InlineKeyboardButton(_t(_BTN_MENU,   lang), callback_data="back_to_main_menu"))
    else:
        from utils.payments import expired_text as _exp_text
        text = _exp_text(lang)
        kb   = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(_t(_BTN_BUY_MORE, lang), callback_data="check_slots"))
        kb.add(InlineKeyboardButton(_t(_BTN_MENU,     lang), callback_data="back_to_main_menu"))

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    logger.info("MISSED_APPOINTMENT | user=%s attempts_left=%d", uid, n)


# ── Registration ──────────────────────────────────────────────────────────────

def register(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(
        handle_start_monitor,
        lambda c: c.data == "start_monitor",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_stop_monitor,
        lambda c: c.data == "stop_monitor",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_monitor_status,
        lambda c: c.data == "monitor_status",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_i_booked,
        lambda c: c.data == "i_booked",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_missed_appointment,
        lambda c: c.data == "missed_appointment",
        state="*",
    )
