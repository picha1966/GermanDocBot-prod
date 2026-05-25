# -*- coding: utf-8 -*-
"""
Progressive Termin Upsell — 72-hour no-slot nudge.

After 72 hours of active monitoring with no slot found, send a one-time
high-intent upsell: "Upgrade to Priority Mode" (family plan or PDF bundle).

Rules:
  - Only fires once per entitlement (tracked via `upsell_sent` flag in memory + DB col).
  - Only for users where active=1, found_termin=0, created_at < 72h ago.
  - Safe: never fires twice for the same user session.
  - Runs as a background asyncio task, called from bot.py startup loop.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

UPSELL_AFTER_HOURS: int = 72
CHECK_INTERVAL_SECONDS: int = 3600  # re-check every hour

_UPSELL_SENT: set = set()  # in-memory cache; primary guard is the DB table below


def _ensure_upsell_table() -> None:
    """Create upsell_log table if it doesn't exist. Runs once on first call."""
    try:
        from backend.termin_db import get_connection
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS upsell_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    upsell_type TEXT NOT NULL DEFAULT 'termin_72h',
                    sent_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(user_id, upsell_type)
                )
                """
            )
            conn.commit()
    except Exception as exc:
        logger.warning("TERMIN_UPSELL: could not create upsell_log table: %s", exc)


def _mark_upsell_sent_db(user_id: str) -> None:
    """Persist that upsell was sent so it survives bot restarts."""
    try:
        from backend.termin_db import get_connection
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO upsell_log (user_id, upsell_type) VALUES (?, 'termin_72h')",
                (user_id,),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("TERMIN_UPSELL: could not persist upsell_sent: %s", exc)


def _is_upsell_sent_db(user_id: str) -> bool:
    """Return True if upsell was already sent (checks DB, not just in-memory)."""
    try:
        from backend.termin_db import get_connection
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT 1 FROM upsell_log WHERE user_id = ? AND upsell_type = 'termin_72h'",
                (user_id,),
            )
            return cur.fetchone() is not None
    except Exception:
        return False  # fail-open: if DB unreachable, let in-memory guard decide

_UPSELL_TEXT = {
    "uk": (
        "⏳ <b>Ви вже {hours} год. у черзі на Termin…</b>\n\n"
        "Деякі міста мають дуже низьку доступність — іноді потрібно чекати тижнями.\n\n"
        "💡 <b>Порада:</b> додайте ще одне місто або послугу до моніторингу — "
        "це збільшує шанси знайти вільний слот вдвічі.\n\n"
        "📄 Поки чекаєте — підготуйте документ заздалегідь, щоб на Termin не поспішати."
    ),
    "ua": (
        "⏳ <b>Ви вже {hours} год. у черзі на Termin…</b>\n\n"
        "Деякі міста мають дуже низьку доступність — іноді потрібно чекати тижнями.\n\n"
        "💡 <b>Порада:</b> додайте ще одне місто або послугу до моніторингу — "
        "це збільшує шанси знайти вільний слот вдвічі.\n\n"
        "📄 Поки чекаєте — підготуйте документ заздалегідь, щоб на Termin не поспішати."
    ),
    "en": (
        "⏳ <b>You've been waiting {hours}h for a Termin slot…</b>\n\n"
        "Some cities have very low availability — it can take weeks.\n\n"
        "💡 <b>Tip:</b> add another city or service to your monitoring — "
        "it doubles your chances of finding an open slot.\n\n"
        "📄 While you wait — prepare your documents now so you're ready the moment a slot opens."
    ),
    "de": (
        "⏳ <b>Sie warten bereits {hours} Std. auf einen Termin…</b>\n\n"
        "Manche Städte haben eine sehr geringe Verfügbarkeit — manchmal dauert es Wochen.\n\n"
        "💡 <b>Tipp:</b> Fügen Sie eine weitere Stadt oder Dienstleistung hinzu — "
        "das verdoppelt Ihre Chancen.\n\n"
        "📄 Nutzen Sie die Wartezeit — bereiten Sie Ihre Unterlagen jetzt vor."
    ),
    "pl": (
        "⏳ <b>Czekasz już {hours} godzin na Termin…</b>\n\n"
        "Niektóre miasta mają bardzo niską dostępność — czekanie tygodniami jest normalne.\n\n"
        "💡 <b>Wskazówka:</b> dodaj kolejne miasto lub usługę — "
        "to podwaja Twoje szanse na znalezienie wolnego terminu.\n\n"
        "📄 Wykorzystaj czas oczekiwania — przygotuj dokumenty już teraz."
    ),
    "tr": (
        "⏳ <b>{hours} saattir Termin bekliyorsunuz…</b>\n\n"
        "Bazı şehirlerde uygunluk çok düşük — haftalar sürebilir.\n\n"
        "💡 <b>İpucu:</b> başka bir şehir veya hizmet ekleyin — "
        "bu şansınızı iki katına çıkarır.\n\n"
        "📄 Beklerken belgelerinizi hazırlayın — randevu açılır açılmaz hazır olursunuz."
    ),
    "ar": (
        "⏳ <b>لقد انتظرت {hours} ساعة للحصول على Termin…</b>\n\n"
        "بعض المدن لديها توفر منخفض جداً — قد يستغرق الأمر أسابيع.\n\n"
        "💡 <b>نصيحة:</b> أضف مدينة أو خدمة أخرى للمراقبة — "
        "هذا يضاعف فرصك في إيجاد موعد.\n\n"
        "📄 استغل وقت الانتظار — جهّز مستنداتك الآن."
    ),
}

_UPSELL_KEYBOARD_LABEL = {
    "uk": ("📄 Підготувати документ", "🔔 Додати моніторинг"),
    "ua": ("📄 Підготувати документ", "🔔 Додати моніторинг"),
    "en": ("📄 Prepare document", "🔔 Add monitoring"),
    "de": ("📄 Dokument vorbereiten", "🔔 Monitoring hinzufügen"),
    "pl": ("📄 Przygotuj dokument", "🔔 Dodaj monitoring"),
    "tr": ("📄 Belge hazırla", "🔔 İzleme ekle"),
    "ar": ("📄 جهّز مستنداً", "🔔 أضف مراقبة"),
}


def _get_stale_users() -> list:
    """Return users with active monitoring started >72h ago, not yet notified."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=UPSELL_AFTER_HOURS)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    try:
        from backend.termin_db import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT e.user_id, u.language
                FROM termin_entitlements e
                LEFT JOIN users u ON u.telegram_id = e.user_id
                WHERE e.active = 1
                  AND e.found_termin = 0
                  AND e.created_at < ?
                """,
                (cutoff_str,),
            )
            return [{"user_id": row[0], "lang": row[1] or "en"} for row in cur.fetchall()]
    except Exception as exc:
        logger.warning("TERMIN_UPSELL: DB query failed: %s", exc)
        return []


async def _send_upsell(bot, user_id: str, lang: str, hours: int) -> bool:
    from aiogram import types

    _lang = lang.strip().lower()
    if _lang == "ua":
        _lang = "uk"
    if _lang not in _UPSELL_TEXT:
        _lang = "en"

    text = _UPSELL_TEXT[_lang].format(hours=hours)
    labels = _UPSELL_KEYBOARD_LABEL.get(_lang, _UPSELL_KEYBOARD_LABEL["en"])

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(labels[0], callback_data="create_doc"))
    kb.add(types.InlineKeyboardButton(labels[1], callback_data="find_termin"))

    try:
        await bot.send_message(
            chat_id=int(user_id),
            text=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
        logger.info("TERMIN_UPSELL_SENT: user=%s hours=%d", user_id, hours)
        return True
    except Exception as exc:
        logger.warning("TERMIN_UPSELL_SEND_FAIL: user=%s err=%s", user_id, exc)
        return False


async def run_upsell_check(bot) -> None:
    """Check for stale users and send upsell. Call periodically."""
    stale = _get_stale_users()
    if not stale:
        return
    for row in stale:
        uid = str(row["user_id"])
        # Two-layer guard: in-memory (fast) + DB (survives restarts)
        if uid in _UPSELL_SENT:
            continue
        if _is_upsell_sent_db(uid):
            _UPSELL_SENT.add(uid)  # warm the in-memory cache
            continue
        sent = await _send_upsell(bot, uid, row["lang"], UPSELL_AFTER_HOURS)
        if sent:
            _UPSELL_SENT.add(uid)
            _mark_upsell_sent_db(uid)
        await asyncio.sleep(0.3)  # throttle: max ~3 per second


async def upsell_loop(bot) -> None:
    """Background task: check for upsell candidates every hour."""
    _ensure_upsell_table()  # idempotent — safe to call on every start
    logger.info("TERMIN_UPSELL_LOOP: started (interval=%ds)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await run_upsell_check(bot)
        except Exception as exc:
            logger.warning("TERMIN_UPSELL_LOOP: error: %s", exc)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
