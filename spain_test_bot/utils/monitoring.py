"""
Spain Test Bot — in-memory monitoring engine.

Each session is stored as:
  _sessions[user_id] = {
      "city":          str,          # "barcelona"
      "svc":           str,          # "nie"
      "authority":     str,          # "extranjeria"
      "city_display":  str,          # localised city name
      "svc_display":   str,          # localised service name
      "lang":          str,          # "es" / "en" / …
      "last_check_ts": float | None, # unix timestamp
      "next_check_ts": float | None, # unix timestamp
      "task":          asyncio.Task,
  }
"""

from __future__ import annotations

import asyncio
import logging
import random
import time

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

_sessions: dict[int, dict] = {}

# ── Interval ─────────────────────────────────────────────────────────────────
_MIN_INTERVAL = 30.0    # seconds
_MAX_INTERVAL = 65.0    # seconds


# ── Session accessors ─────────────────────────────────────────────────────────

def is_monitoring(user_id: int) -> bool:
    return user_id in _sessions


def get_session(user_id: int) -> dict | None:
    return _sessions.get(user_id)


# ── Human-friendly time ───────────────────────────────────────────────────────

_JUST_NOW: dict[str, str] = {
    "es": "ahora mismo",
    "en": "just now",
    "uk": "щойно",
    "pl": "przed chwilą",
    "ro": "chiar acum",
    "ar": "للتو",
}

_MIN_AGO: dict[str, str] = {
    "es": "hace ~{} min",
    "en": "~{} min ago",
    "uk": "~{} хв тому",
    "pl": "~{} min temu",
    "ro": "~{} min în urmă",
    "ar": "منذ ~{} دقيقة",
}

_FEW_MIN_AGO: dict[str, str] = {
    "es": "hace varios minutos",
    "en": "a few min ago",
    "uk": "кілька хв тому",
    "pl": "kilka minut temu",
    "ro": "câteva min în urmă",
    "ar": "منذ بضع دقائق",
}

_IN_SEC: dict[str, str] = {
    "es": "en ~{} seg",
    "en": "in ~{} sec",
    "uk": "через ~{} сек",
    "pl": "za ~{} sek",
    "ro": "în ~{} sec",
    "ar": "خلال ~{} ثا",
}

_IN_MIN: dict[str, str] = {
    "es": "en ~{} min",
    "en": "in ~{} min",
    "uk": "через ~{} хв",
    "pl": "za ~{} min",
    "ro": "în ~{} min",
    "ar": "خلال ~{} دقيقة",
}


def _t(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


def human_last(ts: float | None, lang: str) -> str:
    if ts is None:
        return _t(_JUST_NOW, lang)
    elapsed = time.time() - ts
    if elapsed < 60:
        return _t(_JUST_NOW, lang)
    elif elapsed < 180:
        return _t(_MIN_AGO, lang).format(int(elapsed / 60))
    return _t(_FEW_MIN_AGO, lang)


def human_next(ts: float | None, lang: str) -> str:
    if ts is None:
        return _t(_IN_SEC, lang).format(30)
    remaining = ts - time.time()
    if remaining <= 0:
        # Check is overdue or just started — next cycle will begin shortly
        return _t(_IN_SEC, lang).format(30)
    elif remaining < 60:
        return _t(_IN_SEC, lang).format(int(remaining))
    return _t(_IN_MIN, lang).format(int(remaining / 60))


# ── Alert texts ───────────────────────────────────────────────────────────────

_ALERT_HEADER: dict[str, str] = {
    "es": "🔥 <b>¡Cita disponible!</b>",
    "en": "🔥 <b>Appointment found!</b>",
    "uk": "🔥 <b>Запис знайдено!</b>",
    "pl": "🔥 <b>Znaleziono wizytę!</b>",
    "ro": "🔥 <b>Programare găsită!</b>",
    "ar": "🔥 <b>تم العثور على موعد!</b>",
}

_ALERT_URGENCY: dict[str, str] = {
    "es": "⚡ Actúa rápido — las citas desaparecen en minutos",
    "en": "⚡ Act fast — citas disappear quickly",
    "uk": "⚡ Дій швидко — citas зникають за хвилини",
    "pl": "⚡ Działaj szybko — citas znikają w minutach",
    "ro": "⚡ Acționează rapid — citas dispar în minute",
    "ar": "⚡ تصرف بسرعة — تختفي المواعيد (citas) في دقائق",
}

_ALERT_BOOK_BTN: dict[str, str] = {
    "es": "👉 Reservar ahora — antes de que desaparezca",
    "en": "👉 Book now — before it disappears",
    "uk": "👉 Записатись зараз — поки не зникло",
    "pl": "👉 Zarezerwuj teraz — zanim zniknie",
    "ro": "👉 Rezervă acum — înainte să dispară",
    "ar": "👉 احجز الآن — قبل أن يختفي",
}

_ALERT_BOOKED_BTN: dict[str, str] = {
    "es": "✅ Ya reservé",
    "en": "✅ I booked it",
    "uk": "✅ Я записався",
    "pl": "✅ Zarezerwowałem",
    "ro": "✅ Am rezervat",
    "ar": "✅ لقد حجزت",
}

_ALERT_MISSED_BTN: dict[str, str] = {
    "es": "❌ Ya no estaba disponible",
    "en": "❌ It was already taken",
    "uk": "❌ Запис вже зайнятий",
    "pl": "❌ Termin już zajęty",
    "ro": "❌ Deja ocupat",
    "ar": "❌ الموعد محجوز بالفعل",
}

_ALERT_ATTEMPTS_LEFT: dict[str, str] = {
    "es": "🔄 Te quedan <b>{n}</b> cita{s} en tu plan — seguimos buscando",
    "en": "🔄 You have <b>{n}</b> appointment{s} left — we keep searching",
    "uk": "🔄 Залишилось <b>{n}</b> спроб{s} у тарифі — продовжуємо пошук",
    "pl": "🔄 Pozostało Ci <b>{n}</b> termin{s} w planie — szukamy dalej",
    "ro": "🔄 Îți mai rămân <b>{n}</b> programăr{s} în plan — continuăm căutarea",
    "ar": "🔄 تبقّى لديك <b>{n}</b> موعد{s} في خطتك — نواصل البحث",
}

_ALERT_LAST_ATTEMPT: dict[str, str] = {
    "es": "ℹ️ Era tu última cita del plan",
    "en": "ℹ️ That was your last appointment from the plan",
    "uk": "ℹ️ Це була остання спроба тарифу",
    "pl": "ℹ️ To był Twój ostatni termin z planu",
    "ro": "ℹ️ Aceasta a fost ultima programare din plan",
    "ar": "ℹ️ كان هذا آخر موعد من خطتك",
}

_BTN_BUY_MORE: dict[str, str] = {
    "es": "🔄 Comprar más citas",
    "en": "🔄 Buy more attempts",
    "uk": "🔄 Купити ще",
    "pl": "🔄 Kup więcej",
    "ro": "🔄 Cumpără mai multe",
    "ar": "🔄 شراء المزيد",
}

_MISSED_REPLY: dict[str, str] = {
    "es": (
        "❌ <b>Registro ya no disponible</b>\n\n"
        "Pasa — no siempre se llega a tiempo. Seguimos buscando.\n"
        "🔄 Intentos restantes: <b>{n}</b>"
    ),
    "en": (
        "❌ <b>Appointment already taken</b>\n\n"
        "It happens — not always possible to be first. We keep searching.\n"
        "🔄 You still have: <b>{n}</b> attempt{s}"
    ),
    "uk": (
        "❌ <b>Запис вже зайнятий</b>\n\n"
        "Буває — не завжди вдається встигнути. Продовжуємо пошук.\n"
        "🔄 У тебе залишилось: <b>{n}</b> спроб{s}"
    ),
    "pl": (
        "❌ <b>Termin już zajęty</b>\n\n"
        "Zdarza się — nie zawsze się zdąży. Szukamy dalej.\n"
        "🔄 Zostało Ci: <b>{n}</b> termin{s}"
    ),
    "ro": (
        "❌ <b>Programare deja ocupată</b>\n\n"
        "Se întâmplă — nu se poate ajunge mereu primul. Continuăm căutarea.\n"
        "🔄 Îți mai rămân: <b>{n}</b> programăr{s}"
    ),
    "ar": (
        "❌ <b>الموعد محجوز بالفعل</b>\n\n"
        "يحدث — لا يمكن دائماً أن تكون الأول. نواصل البحث.\n"
        "🔄 تبقّى لديك: <b>{n}</b> موعد{s}"
    ),
}


# ── Background monitor loop ───────────────────────────────────────────────────

async def _monitor_loop(
    bot: Bot,
    user_id: int,
    city: str,
    svc: str,
    authority: str,
    city_display: str,
    svc_display: str,
    lang: str,
) -> None:
    logger.info("MONITOR_START | user=%s city=%s svc=%s", user_id, city, svc)

    try:
        from utils.spain_checker import check_spain_termin
    except ImportError as exc:
        logger.error("MONITOR_IMPORT_ERROR | %s", exc)
        _sessions.pop(user_id, None)   # clean up so is_monitoring() correctly returns False
        return

    while user_id in _sessions:
        interval = random.uniform(_MIN_INTERVAL, _MAX_INTERVAL)
        next_ts  = time.time() + interval

        session = _sessions.get(user_id)
        if session:
            session["next_check_ts"] = next_ts

        # Sleep in small chunks so stop_monitoring is responsive
        slept = 0.0
        while slept < interval:
            await asyncio.sleep(min(5.0, interval - slept))
            slept += 5.0
            if user_id not in _sessions:
                logger.info("MONITOR_STOPPED_DURING_SLEEP | user=%s", user_id)
                return

        if user_id not in _sessions:
            return

        logger.info("MONITOR_CHECK | user=%s city=%s svc=%s", user_id, city, svc)
        check_ts = time.time()

        try:
            result = await check_spain_termin(city, authority)
        except Exception as exc:
            logger.error("MONITOR_CHECK_ERROR | user=%s err=%s", user_id, exc)
            result = []

        session = _sessions.get(user_id)
        if session:
            session["last_check_ts"] = check_ts

        # ── Check attempts remaining before acting on result ──────────────────
        try:
            from utils.payments import is_paid, expired_text as _exp_text, decrement_attempts, get_attempts_left
            if not is_paid(user_id):
                logger.info("MONITOR_NO_ATTEMPTS | user=%s — stopping", user_id)
                stop_monitoring(user_id)
                try:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    kb_exp = InlineKeyboardMarkup(row_width=1)
                    kb_exp.add(InlineKeyboardButton(_t(_BTN_BUY_MORE, lang), callback_data="check_slots"))
                    await bot.send_message(user_id, _exp_text(lang), parse_mode="HTML", reply_markup=kb_exp)
                except Exception:
                    pass
                return
        except ImportError:
            pass   # payments module not available — skip check

        if not result:
            logger.info("MONITOR_NO_SLOTS | user=%s", user_id)
            continue

        # ── Cita found — decrement attempt, send alert ────────────────────────
        logger.info("MONITOR_FOUND | user=%s city=%s svc=%s slots=%d", user_id, city, svc, len(result))
        slot = result[0]
        date      = slot.get("date")     or "—"
        slot_time = slot.get("time")     or "—"
        location  = slot.get("location") or city_display
        url       = slot.get("url")      or ""

        # Decrement attempt immediately on find
        remaining = 0
        try:
            from utils.payments import decrement_attempts as _dec
            remaining = _dec(user_id)
        except Exception as exc:
            logger.warning("MONITOR_DECREMENT_FAILED | user=%s err=%s", user_id, exc)

        try:
            from utils.portal_instructions import get_portal_instructions as _get_instr
            instructions = _get_instr(city, svc, lang)
        except Exception:
            instructions = ""

        # Build attempts-remaining line
        if remaining > 0:
            _s = {"es": "s", "en": "s", "uk": "и" if remaining in (2, 3, 4) else "", "pl": "y" if remaining in (2, 3, 4) else "", "ro": "i", "ar": ""}
            attempts_line = _t(_ALERT_ATTEMPTS_LEFT, lang).format(n=remaining, s=_s.get(lang, ""))
        else:
            attempts_line = _t(_ALERT_LAST_ATTEMPT, lang)

        text = (
            f"{_t(_ALERT_HEADER, lang)}\n\n"
            f"📍 {location}\n"
            f"📄 {svc_display}\n"
            f"📅 {date}  ⏰ {slot_time}\n\n"
            f"{_t(_ALERT_URGENCY, lang)}\n\n"
            f"{attempts_line}"
            + (f"\n\n{instructions}" if instructions else "")
        )

        kb = InlineKeyboardMarkup(row_width=1)
        if url:
            kb.add(InlineKeyboardButton(_t(_ALERT_BOOK_BTN, lang), url=url))
        kb.add(InlineKeyboardButton(_t(_ALERT_BOOKED_BTN, lang), callback_data="i_booked"))
        kb.add(InlineKeyboardButton(_t(_ALERT_MISSED_BTN, lang), callback_data="missed_appointment"))

        try:
            await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
        except Exception as exc:
            logger.error("MONITOR_ALERT_SEND_FAILED | user=%s err=%s", user_id, exc)

        if remaining == 0:
            # All attempts used — stop monitoring
            stop_monitoring(user_id)
            try:
                from utils.payments import expired_text as _exp_text
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                kb_done = InlineKeyboardMarkup(row_width=1)
                kb_done.add(InlineKeyboardButton(_t(_BTN_BUY_MORE, lang), callback_data="check_slots"))
                await bot.send_message(user_id, _exp_text(lang), parse_mode="HTML", reply_markup=kb_done)
            except Exception:
                pass
            return
        # else: attempts remain — continue loop (no stop, no return)

    logger.info("MONITOR_LOOP_EXIT | user=%s", user_id)


# ── Public API ────────────────────────────────────────────────────────────────

async def start_monitoring(
    bot: Bot,
    user_id: int,
    city: str,
    svc: str,
    authority: str,
    city_display: str,
    svc_display: str,
    lang: str,
) -> None:
    """Start a monitoring session. Stops any previous session for this user."""
    if user_id in _sessions:
        stop_monitoring(user_id)

    task = asyncio.create_task(
        _monitor_loop(bot, user_id, city, svc, authority, city_display, svc_display, lang),
        name=f"monitor_{user_id}",
    )

    _sessions[user_id] = {
        "city":          city,
        "svc":           svc,
        "authority":     authority,
        "city_display":  city_display,
        "svc_display":   svc_display,
        "lang":          lang,
        "last_check_ts": None,
        "next_check_ts": None,
        "task":          task,
    }
    logger.info("MONITOR_SESSION_CREATED | user=%s city=%s svc=%s", user_id, city, svc)


def stop_monitoring(user_id: int) -> bool:
    """Cancel a monitoring session. Returns True if one was active."""
    session = _sessions.pop(user_id, None)
    if session is None:
        return False
    task: asyncio.Task = session.get("task")
    if task and not task.done():
        task.cancel()
    logger.info("MONITOR_STOPPED | user=%s", user_id)
    return True
