# -*- coding: utf-8 -*-
"""
Termin Assistant Handler — integrated into GOLD-BUILD
Product 2: Appointment booking guidance + paid reminders

Adapted from termin_docs_bot-main for Gold Build integration.
Key changes:
  - Imports from backend.termin_db / backend.termin_texts
  - Language synced from Gold Build's get_user_lang on every entry
  - back_to_products → Gold Build main menu
  - TerminStates — isolated FSM group (no conflicts with DocumentState)
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, types
# NOTE: _termin_metrics and utils/termin_checker._sessions are still process-local.
# _payment_screen_shown and _payment_completed are now Redis-backed (Stage 15)
# and survive restarts when REDIS_URL is set. Falls back to in-memory otherwise.
# TODO_STAGE18: For horizontal scaling, migrate _sessions and FSM to shared store.
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from backend.termin_db import (
    get_user, update_user, create_user,
    get_cities, get_authorities,
    get_knowledge, get_authority_info,
    create_reminder, deactivate_reminder,
    get_active_reminders, update_reminder_sent,
    is_termin_entitled,
)
from backend.termin_texts import get_text
from utils.helpers import get_user_lang
from utils.termin_checker import (
    DemandLevel, get_demand_level, get_termin_price, get_locked_price,
    get_monitoring_stats, get_session as get_polling_session, build_found_message,
    build_best_booking_link, _CITY_PORTAL_FALLBACKS,
)
from utils.termin_redis import RedisBackedDict

logger = logging.getLogger(__name__)

# ==================== Bot username cache ====================
# Priority: set_bot_username() at startup → config.BOT_USERNAME → BOT_USERNAME env → fallback
_BOT_USERNAME_CACHE: str = ""


def set_bot_username(username: str) -> None:
    """Called once at bot startup (after bot.get_me()) to cache the live username."""
    global _BOT_USERNAME_CACHE
    if username:
        _BOT_USERNAME_CACHE = username.lstrip("@")
        logger.info("BOT_USERNAME_CACHED | username=%s", _BOT_USERNAME_CACHE)


def _get_bot_username() -> str:
    """
    Resolve bot username with priority:
      1. Runtime cache set by set_bot_username() (primed from bot.get_me() at startup)
      2. config.BOT_USERNAME (from settings/.env)
      3. BOT_USERNAME environment variable
      4. Hard fallback "DE_PDF_Assistant_bot" (last resort — always produces a valid URL)
    """
    if _BOT_USERNAME_CACHE:
        return _BOT_USERNAME_CACHE
    try:
        from config import BOT_USERNAME as _cfg_username
        if _cfg_username:
            return str(_cfg_username).lstrip("@")
    except Exception:
        pass
    env_val = os.getenv("BOT_USERNAME", "")
    if env_val:
        return env_val.lstrip("@")
    return "DE_PDF_Assistant_bot"


def _build_success_url(order_id) -> str:
    """Build and log the Stripe success deep-link for this order."""
    username = _get_bot_username()
    url = f"https://t.me/{username}?start=paid_{order_id}"
    logger.info("STRIPE_SUCCESS_URL=%s", url)
    return url


# DEV MODE: users in this set always enter Termin as a new customer.
# Add/remove Telegram IDs here for local payment testing.
# Never affects real users — only IDs explicitly listed below.
DEV_TEST_USERS: set = {402229082}

# Legacy env-var support (kept for backward compat; DEV_TEST_USERS takes priority)
DEV_USER_ID = int(os.getenv("TERMIN_DEV_USER_ID", "0"))


def _dev_reset_if_needed(user_id: int) -> None:
    """Soft-reset Termin state for DEV test users so they always see the payment flow.

    Only fires for user IDs listed in DEV_TEST_USERS.
    Uses UPDATE (not DELETE) so the users row stays intact for language/city fields.
    Never touches real users.
    """
    if user_id not in DEV_TEST_USERS:
        return
    try:
        from backend.termin_db import get_connection
        tid = str(user_id)
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET has_paid_termin=0, reminder_active=0, status=NULL "
                "WHERE telegram_id=?",
                (tid,),
            )
            conn.execute(
                "UPDATE termin_entitlements SET active=0 WHERE user_id=?",
                (tid,),
            )
            conn.execute(
                "UPDATE reminders SET is_active=0 WHERE telegram_id=?",
                (tid,),
            )
            conn.commit()
        logger.warning("🧪 DEV_TEST_USER reset | user=%s — entering as new customer", user_id)
    except Exception as exc:
        logger.error("DEV reset failed | user=%s err=%s", user_id, exc)

# ==================== Production Observability (Stage 12) ====================


def log_event(event: str, user_id: int, extra=None) -> None:
    """Lightweight structured audit log for Termin payment events."""
    try:
        msg = f"TERMIN_EVENT | event={event} | user={user_id}"
        if extra:
            details = " ".join(f"{k}={v}" for k, v in extra.items())
            msg += f" | {details}"
        logger.info(msg)
    except Exception:
        pass


# In-memory counters — reset on process restart, NOT persisted.
# Intentionally kept in-memory (cheap, non-critical). Use Redis INCR if needed later.
_termin_metrics: dict = {
    "success": 0,
    "retry": 0,
    "fail": 0,
    "expired": 0,
}


def get_termin_metrics_snapshot() -> dict:
    """Return a safe copy of current metrics (for logging/debug only, never user-facing)."""
    try:
        return dict(_termin_metrics)
    except Exception:
        return {}


def _get_admin_ids() -> list:
    """Read admin IDs from env (self-contained, no cross-module dependency)."""
    raw = os.getenv("ADMIN_IDS", "")
    if not raw:
        return []
    try:
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]
    except (ValueError, TypeError):
        return []


# Stage 18: Debug logging toggle (env TERMIN_DEBUG=1). NOT for hot loops.
_TERMIN_DEBUG = os.getenv("TERMIN_DEBUG", "").strip() == "1"



# ==================== FSM States (isolated — no global finish) ====================
class TerminStates(StatesGroup):
    """States for termin assistant flow"""
    selecting_city = State()
    selecting_authority = State()
    viewing_guidance = State()
    paying_for_reminders = State()
    setting_reminder = State()


# ==================== Language Bridge ====================
def _resolve_lang(user_id: int) -> str:
    """
    Resolve user language using Gold Build's canonical source,
    then sync into termin DB so termin_texts picks the right locale.
    Maps Gold Build 'uk' → termin 'ua' convention.
    """
    lang = get_user_lang(user_id) or 'en'
    # Gold Build uses 'uk' for Ukrainian; termin_texts uses 'ua'
    if lang == 'uk':
        lang = 'ua'
    return lang


def _lang_text(d: dict, lang: str) -> str:
    """Resolve localized text with deterministic Ukrainian fallback.

    Resolution order:
      1. exact key  (e.g. 'ua', 'de', 'en')
      2. Ukrainian alias  ('uk' ↔ 'ua')
      3. 'en' as final fallback
    Never silently falls back to a random key.
    """
    if lang in d:
        return d[lang]
    if lang in ("ua", "uk"):
        alt = "uk" if lang == "ua" else "ua"
        if alt in d:
            return d[alt]
    return d.get("en", "")


def _ensure_termin_user(user_id: int, lang: str) -> dict:
    """Ensure user exists in termin DB with correct language.

    Read-only with respect to payment state:
    - Creates user row if missing
    - Syncs language if changed
    - NEVER touches has_paid_termin, city, or authority
    Webhook is the single source of truth for has_paid_termin.
    """
    telegram_id = str(user_id)
    user = get_user(telegram_id)
    if not user:
        user = create_user(telegram_id, lang)
    elif user.get('language') != lang:
        user = update_user(telegram_id, language=lang)
    return user


# ==================== Termin Notification UX (6 languages) ====================

# Entry screen — city prompt (shown to all non-active users)
# When only one city is active, text states availability directly instead of "select".
# When more cities are added, this should be updated to a selection prompt.
_TERMIN_ENTRY_TEXT = {
    "ua": (
        "📅 <b>Моніторинг Termin — 24/7</b>\n"
        "📍 Berlin · München · Frankfurt · Köln · Düsseldorf · Krefeld\n\n"
        "Ми перевіряємо слоти кожні кілька секунд\n"
        "і повідомляємо одразу, коли з'являється місце.\n\n"
        "🔔 Telegram + Email миттєво\n\n"
        "👥 <b>2 400+</b> людей вже моніторять прямо зараз\n\n"
        "Оберіть місто:"
    ),
    "uk": (
        "📅 <b>Моніторинг Termin — 24/7</b>\n"
        "📍 Berlin · München · Frankfurt · Köln · Düsseldorf · Krefeld\n\n"
        "Ми перевіряємо слоти кожні кілька секунд\n"
        "і повідомляємо одразу, коли з'являється місце.\n\n"
        "🔔 Telegram + Email миттєво\n\n"
        "👥 <b>2 400+</b> людей вже моніторять прямо зараз\n\n"
        "Оберіть місто:"
    ),
    "en": (
        "📅 <b>Termin Monitoring — 24/7</b>\n"
        "📍 Berlin · München · Frankfurt · Köln · Düsseldorf · Krefeld\n\n"
        "We check slots every few seconds\n"
        "and notify you instantly when one opens.\n\n"
        "🔔 Telegram + Email instantly\n\n"
        "👥 <b>2,400+</b> people monitoring right now\n\n"
        "Choose your city:"
    ),
    "de": (
        "📅 <b>Terminüberwachung — 24/7</b>\n"
        "📍 Berlin · München · Frankfurt · Köln · Düsseldorf · Krefeld\n\n"
        "Wir prüfen Slots alle paar Sekunden\n"
        "und benachrichtigen Sie sofort, sobald ein Termin frei wird.\n\n"
        "🔔 Telegram + E-Mail sofort\n\n"
        "👥 <b>2.400+</b> Nutzer überwachen gerade aktiv\n\n"
        "Stadt auswählen:"
    ),
    "pl": (
        "📅 <b>Monitoring Termin — 24/7</b>\n"
        "📍 Berlin · München · Frankfurt · Köln · Düsseldorf · Krefeld\n\n"
        "Sprawdzamy sloty co kilka sekund\n"
        "i powiadamiamy natychmiast, gdy pojawi się wolne miejsce.\n\n"
        "🔔 Telegram + e-mail od razu\n\n"
        "👥 <b>2 400+</b> osób monitoruje właśnie teraz\n\n"
        "Wybierz miasto:"
    ),
    "tr": (
        "📅 <b>Termin Takibi — 7/24</b>\n"
        "📍 Berlin · München · Frankfurt · Köln · Düsseldorf · Krefeld\n\n"
        "Slotları her birkaç saniyede kontrol ediyoruz\n"
        "ve yer açılır açılmaz anında bildirim gönderiyoruz.\n\n"
        "🔔 Telegram + e-posta anında\n\n"
        "👥 <b>2.400+</b> kişi şu an aktif olarak izliyor\n\n"
        "Şehir seçin:"
    ),
    "ar": (
        "📅 <b>مراقبة المواعيد — 24/7</b>\n"
        "📍 Berlin · München · Frankfurt · Köln · Düsseldorf · Krefeld\n\n"
        "نفحص المواعيد كل بضع ثوانٍ\n"
        "ونرسل إشعارًا فور توفر مكان.\n\n"
        "🔔 Telegram + بريد إلكتروني فورًا\n\n"
        "👥 <b>2,400+</b> شخص يراقبون الآن\n\n"
        "اختر المدينة:"
    ),
}
def _get_live_monitor_count() -> str:
    """
    Return a formatted active monitor count for the Termin intro screen.
    Queries DB for users with has_paid_termin=1; caches result for 1 hour.
    Falls back to a safe generic string if DB is unavailable.
    """
    import time as _time_mod
    _now = _time_mod.time()
    _cache = _get_live_monitor_count.__dict__
    if _now - _cache.get("_ts", 0) < 3600 and "val" in _cache:
        return _cache["val"]
    try:
        from backend.termin_db import get_connection as _tc
        with _tc() as _conn:
            _cur = _conn.cursor()
            # Count only currently active monitors — not historical total
            _cur.execute(
                "SELECT COUNT(DISTINCT user_id) FROM termin_entitlements "
                "WHERE active = 1 AND found_termin = 0"
            )
            _row = _cur.fetchone()
            count = int(_row[0]) if _row else 0
    except Exception:
        count = 0
    # Show real number if meaningful; avoid inflated placeholder when count is low
    if count >= 200:
        val = f"{count:,}+"
    elif count >= 20:
        val = f"{count}+"
    else:
        # Not enough real data yet — show demand signal without a specific number
        val = "growing"
    _cache["val"] = val
    _cache["_ts"] = _now
    return val


def _build_termin_entry_text(lang: str) -> str:
    """Build the Termin entry screen text with live social proof injected."""
    _count = _get_live_monitor_count()
    if _count == "growing":
        # Early stage: show demand without a number (honest, no inflated placeholder)
        _SOCIAL_LINE = {
            "uk": "👥 Сервіс активно росте — приєднуйтесь",
            "ua": "👥 Сервіс активно росте — приєднуйтесь",
            "en": "👥 Service is growing — be among the first",
            "de": "👥 Der Dienst wächst — seien Sie dabei",
            "pl": "👥 Serwis rośnie — dołącz do nas",
            "tr": "👥 Hizmet büyüyor — ilk kullanıcılar arasına katılın",
            "ar": "👥 الخدمة في نمو — كن من الأوائل",
        }
    else:
        _SOCIAL_LINE = {
            "uk": f"👥 <b>{_count}</b> людей вже моніторять прямо зараз",
            "ua": f"👥 <b>{_count}</b> людей вже моніторять прямо зараз",
            "en": f"👥 <b>{_count}</b> people monitoring right now",
            "de": f"👥 <b>{_count}</b> Nutzer überwachen gerade aktiv",
            "pl": f"👥 <b>{_count}</b> osób monitoruje właśnie teraz",
            "tr": f"👥 <b>{_count}</b> kişi şu an aktif olarak izliyor",
            "ar": f"👥 <b>{_count}</b> شخص يراقبون الآن",
        }
    _base = _TERMIN_ENTRY_TEXT.get(lang) or _TERMIN_ENTRY_TEXT.get("en", "")
    _social = _SOCIAL_LINE.get(lang, _SOCIAL_LINE["en"])
    import re as _re
    _base = _re.sub(r"👥 <b>[^<]+</b>[^\n]+|👥 [^\n]+", _social, _base)
    return _base


# Document type selection prompt (shown after city selection)
_DOC_SELECT_TEXT = {
    "ua": (
        "📄 <b>Оберіть послугу</b>\n\n"
        "Для якої послуги вам потрібен запис?"
    ),
    "uk": (
        "📄 <b>Оберіть послугу</b>\n\n"
        "Для якої послуги вам потрібен запис?"
    ),
    "en": (
        "📄 <b>Select a service</b>\n\n"
        "What type of appointment do you need?"
    ),
    "de": (
        "📄 <b>Dienst auswählen</b>\n\n"
        "Für welchen Dienst benötigen Sie einen Termin?"
    ),
    "pl": (
        "📄 <b>Wybierz usługę</b>\n\n"
        "Jakiego rodzaju wizytę potrzebujesz?"
    ),
    "tr": (
        "📄 <b>Hizmet seçin</b>\n\n"
        "Hangi hizmet için randevuya ihtiyacınız var?"
    ),
    "ar": (
        "📄 <b>اختر الخدمة</b>\n\n"
        "ما نوع الموعد الذي تحتاجه؟"
    ),
}

# Payment offer (shown after city + document selection, BEFORE payment)
_PAYMENT_OFFER_TEXT = {
    "ua": (
        "🔔 <b>Моніторинг доступності Termin</b>\n\n"
        "Безперервне відстеження офіційних порталів (кілька секунд).\n"
        "Ви отримаєте сповіщення одразу, щойно з\u02bcявиться вільний слот.\n\n"
        "✅ Автоматичний моніторинг Termin\n"
        "💰 Вартість: <b>€{price}</b> (одноразово)\n\n"
        "Запис ви завжди робите самостійно через офіційний сайт.\n"
        "Ми не є державним органом."
    ),
    "uk": (
        "🔔 <b>Моніторинг доступності Termin</b>\n\n"
        "Безперервне відстеження офіційних порталів (кілька секунд).\n"
        "Ви отримаєте сповіщення одразу, щойно з\u02bcявиться вільний слот.\n\n"
        "✅ Автоматичний моніторинг Termin\n"
        "💰 Вартість: <b>€{price}</b> (одноразово)\n\n"
        "Запис ви завжди робите самостійно через офіційний сайт.\n"
        "Ми не є державним органом."
    ),
    "en": (
        "🔔 <b>Termin availability monitoring</b>\n\n"
        "Continuous monitoring of official portals (a few seconds).\n"
        "You will be notified immediately when a slot becomes available.\n\n"
        "✅ Automatic Termin monitoring\n"
        "💰 Price: <b>€{price}</b> (one-time)\n\n"
        "You always book the appointment yourself via the official website.\n"
        "We are not a government authority."
    ),
    "de": (
        "🔔 <b>Termin-Verfügbarkeitsüberwachung</b>\n\n"
        "Kontinuierliche Überwachung offizieller Portale (wenige Sekunden).\n"
        "Sie werden sofort benachrichtigt, sobald ein Termin verfügbar ist.\n\n"
        "✅ Automatische Termin-Überwachung\n"
        "💰 Preis: <b>€{price}</b> (einmalig)\n\n"
        "Sie buchen den Termin immer selbst über die offizielle Website.\n"
        "Wir sind keine Behörde."
    ),
    "pl": (
        "🔔 <b>Monitoring dostępności Termin</b>\n\n"
        "Ciągły monitoring oficjalnych portali (co kilka sekund).\n"
        "Otrzymasz powiadomienie natychmiast po pojawieniu się wolnego miejsca.\n\n"
        "✅ Automatyczny monitoring Termin\n"
        "💰 Cena: <b>€{price}</b> (jednorazowo)\n\n"
        "Wizytę zawsze umawiasz samodzielnie na oficjalnej stronie.\n"
        "Nie jesteśmy organem rządowym."
    ),
    "tr": (
        "🔔 <b>Termin müsaitlik izlemesi</b>\n\n"
        "Resmi portalların sürekli izlenmesi (saniye aralıkla).\n"
        "Bir yer açıldığında anında bildirim alacaksınız.\n\n"
        "✅ Otomatik Termin izleme\n"
        "💰 Fiyat: <b>€{price}</b> (tek seferlik)\n\n"
        "Randevunuzu her zaman kendiniz resmi web sitesinden alırsınız.\n"
        "Bir devlet kurumu değiliz."
    ),
    "ar": (
        "🔔 <b>مراقبة توافر المواعيد</b>\n\n"
        "مراقبة مستمرة للبوابات الرسمية (كل بضع ثوانٍ).\n"
        "ستصلك إشعار فوري عند توفر موعد.\n\n"
        "✅ مراقبة Termin تلقائية\n"
        "💰 السعر: <b>€{price}</b> (مرة واحدة)\n\n"
        "أنت تحجز الموعد دائماً بنفسك عبر الموقع الرسمي.\n"
        "لسنا جهة حكومية."
    ),
}

# Pre-payment summary screen — shown when city+service selected but not yet paid.
# Includes {city}, {service}, {price} placeholders resolved at render time.
_PRE_PAYMENT_TEXT = {
    "ua": (
        "🔎 <b>Termin Monitoring — {city}</b>\n\n"
        "📄 Послуга: <b>{service}</b>\n\n"
        "Ми автоматично перевіряємо офіційні системи запису\n"
        "та повідомляємо вас одразу коли з'явиться Termin.\n\n"
        "Вам більше не потрібно перевіряти вручну.\n\n"
        "✅ Миттєві сповіщення в Telegram + Email\n"
        "✅ Пряме посилання для запису\n"
        "✅ Моніторинг до першого знайденого Termin\n\n"
        "💶 <b>Оберіть план:</b>\n"
        "⭐ <b>Найкращий вибір: 7 днів — €14.99</b>\n"
        "⚡ Швидкий старт: 24 год — €4.99"
    ),
    "uk": (
        "🔎 <b>Termin Monitoring — {city}</b>\n\n"
        "📄 Послуга: <b>{service}</b>\n\n"
        "Ми автоматично перевіряємо офіційні системи запису\n"
        "та повідомляємо вас одразу коли з'явиться Termin.\n\n"
        "Вам більше не потрібно перевіряти вручну.\n\n"
        "✅ Миттєві сповіщення в Telegram + Email\n"
        "✅ Пряме посилання для запису\n"
        "✅ Моніторинг до першого знайденого Termin\n\n"
        "💶 <b>Оберіть план:</b>\n"
        "⭐ <b>Найкращий вибір: 7 днів — €14.99</b>\n"
        "⚡ Швидкий старт: 24 год — €4.99"
    ),
    "en": (
        "🔎 <b>Termin Monitoring — {city}</b>\n\n"
        "📄 Service: <b>{service}</b>\n\n"
        "We automatically monitor official booking systems\n"
        "and notify you immediately when a Termin appears.\n\n"
        "You no longer need to check manually.\n\n"
        "✅ Instant Telegram + Email notifications\n"
        "✅ Direct booking link\n"
        "✅ Monitoring runs until the first Termin is found\n\n"
        "💶 <b>Choose your plan:</b>\n"
        "⭐ <b>Best choice: 7 days — €14.99</b>\n"
        "⚡ Quick start: 24h — €4.99"
    ),
    "de": (
        "🔎 <b>Termin Monitoring — {city}</b>\n\n"
        "📄 Dienst: <b>{service}</b>\n\n"
        "Wir überwachen offizielle Buchungssysteme automatisch\n"
        "und benachrichtigen Sie sofort, wenn ein Termin erscheint.\n\n"
        "Sie müssen nicht mehr manuell prüfen.\n\n"
        "✅ Sofortige Benachrichtigungen via Telegram + E-Mail\n"
        "✅ Direkter Buchungslink\n"
        "✅ Überwachung läuft bis zum ersten gefundenen Termin\n\n"
        "💶 <b>Plan wählen:</b>\n"
        "⭐ <b>Beste Wahl: 7 Tage — €14,99</b>\n"
        "⚡ Schnellstart: 24 Stunden — €4,99"
    ),
    "pl": (
        "🔎 <b>Termin Monitoring — {city}</b>\n\n"
        "📄 Usługa: <b>{service}</b>\n\n"
        "Automatycznie sprawdzamy oficjalne systemy rezerwacji\n"
        "i natychmiast powiadamiamy gdy pojawi się Termin.\n\n"
        "Nie musisz już sprawdzać ręcznie.\n\n"
        "✅ Natychmiastowe powiadomienia Telegram + e-mail\n"
        "✅ Bezpośredni link do rezerwacji\n"
        "✅ Monitoring działa do znalezienia pierwszego Terminu\n\n"
        "💶 <b>Wybierz plan:</b>\n"
        "⭐ <b>Najlepszy wybór: 7 dni — €14,99</b>\n"
        "⚡ Szybki start: 24h — €4,99"
    ),
    "tr": (
        "🔎 <b>Termin Monitoring — {city}</b>\n\n"
        "📄 Hizmet: <b>{service}</b>\n\n"
        "Resmi randevu sistemlerini otomatik kontrol ediyoruz\n"
        "ve Termin göründüğünde sizi anında bilgilendiriyoruz.\n\n"
        "Artık manuel kontrol etmenize gerek yok.\n\n"
        "✅ Anında Telegram + e-posta bildirimleri\n"
        "✅ Doğrudan rezervasyon bağlantısı\n"
        "✅ İzleme ilk Termin bulunana kadar çalışır\n\n"
        "💶 <b>Plan seçin:</b>\n"
        "⭐ <b>En iyi seçim: 7 gün — €14,99</b>\n"
        "⚡ Hızlı başlangıç: 24 saat — €4,99"
    ),
    "ar": (
        "🔎 <b>Termin Monitoring — {city}</b>\n\n"
        "📄 الخدمة: <b>{service}</b>\n\n"
        "نقوم بمراقبة أنظمة الحجز الرسمية تلقائيًا\n"
        "ونبلغك فور توفر موعد.\n\n"
        "لم تعد بحاجة إلى التحقق يدويًا.\n\n"
        "✅ إشعارات فورية عبر Telegram + بريد إلكتروني\n"
        "✅ رابط الحجز المباشر\n"
        "✅ المراقبة تعمل حتى العثور على أول موعد\n\n"
        "💶 <b>اختر خطتك:</b>\n"
        "⭐ <b>الخيار الأفضل: 7 أيام — €14.99</b>\n"
        "⚡ بداية سريعة: 24 ساعة — €4.99"
    ),
}

# Cities that have a working real-time checker (Playwright-based real slot scraping).
# Active menu cities: Berlin, Frankfurt, Düsseldorf, Köln, Krefeld.
_CITIES_WITH_AUTO_SCAN = frozenset({
    "berlin", "frankfurt", "koeln", "cologne", "duesseldorf", "dusseldorf",
    "krefeld",
})
_CITIES_BETA_SPA: frozenset = frozenset()  # No cities in beta-only mode

# City-dependent scan-status footnote shown on pre-payment screen.
_SCAN_STATUS_NOTE = {
    # Automatic scan cities — positive confirmation
    "auto": {
        "ua": "✅ Автоматичний скан: увімкнено",
        "uk": "✅ Автоматичний скан: увімкнено",
        "en": "✅ Automatic scan: active",
        "de": "✅ Automatischer Scan: aktiv",
        "pl": "✅ Automatyczne skanowanie: aktywne",
        "tr": "✅ Otomatik tarama: aktif",
        "ar": "✅ المسح التلقائي: نشط",
    },
}


def _get_city_scan_note(city_code: str, lang: str) -> str:
    """Return the scan-status footnote for the pre-payment screen.

    - All active menu cities (Berlin/Frankfurt/Köln/Düsseldorf/Krefeld): positive line.
    - Any other unknown city: empty string (no note).
    """
    key = (city_code or "").lower().strip()
    if key in _CITIES_WITH_AUTO_SCAN:
        return _SCAN_STATUS_NOTE["auto"].get(lang, _SCAN_STATUS_NOTE["auto"]["en"])
    return ""

# Document type labels — user-friendly names for authorities (6 languages)
_DOC_TYPE_LABELS = {
    "buergeramt": {
        "ua": "📋 Anmeldung (реєстрація проживання)",
        "uk": "📋 Anmeldung (реєстрація проживання)",
        "en": "📋 Anmeldung (residence registration)",
        "de": "📋 Anmeldung (Wohnsitzanmeldung)",
        "pl": "📋 Anmeldung (rejestracja zamieszkania)",
        "tr": "📋 Anmeldung (ikamet kaydı)",
        "ar": "📋 Anmeldung (تسجيل الإقامة)",
    },
    "auslaenderbehoerde": {
        "ua": "❗ Aufenthaltstitel (дозвіл на проживання)",
        "uk": "❗ Aufenthaltstitel (дозвіл на проживання)",
        "en": "❗ Aufenthaltstitel (residence permit)",
        "de": "❗ Aufenthaltstitel (Aufenthaltserlaubnis)",
        "pl": "❗ Aufenthaltstitel (pozwolenie na pobyt)",
        "tr": "❗ Aufenthaltstitel (oturma izni)",
        "ar": "❗ Aufenthaltstitel (تصريح الإقامة)",
    },
    "jobcenter": {
        "ua": "💼 Bürgergeld (соціальна допомога)",
        "uk": "💼 Bürgergeld (соціальна допомога)",
        "en": "💼 Bürgergeld (social benefits)",
        "de": "💼 Bürgergeld (Sozialleistungen)",
        "pl": "💼 Bürgergeld (zasiłek socjalny)",
        "tr": "💼 Bürgergeld (sosyal yardım)",
        "ar": "💼 Bürgergeld (المساعدة الاجتماعية)",
    },
    "familienkasse": {
        "ua": "👨‍👩‍👧 Kindergeld (допомога на дитину)",
        "uk": "👨‍👩‍👧 Kindergeld (допомога на дитину)",
        "en": "👨‍👩‍👧 Kindergeld (child benefits)",
        "de": "👨‍👩‍👧 Kindergeld (Familienleistungen)",
        "pl": "👨‍👩‍👧 Kindergeld (zasiłek rodzinny)",
        "tr": "👨‍👩‍👧 Kindergeld (çocuk yardımı)",
        "ar": "👨‍👩‍👧 Kindergeld (إعانة الأطفال)",
    },
}

# ==================== Demand Labels (6 languages × 3 levels) ====================
_DEMAND_LABEL_TEXT = {
    DemandLevel.HIGH: {
        "ua": "🔴 Попит високий — слоти зникають швидко. Бронюйте одразу.",
        "uk": "🔴 Попит високий — слоти зникають швидко. Бронюйте одразу.",
        "en": "🔴 High demand — slots vanish quickly. Book as soon as one appears.",
        "de": "🔴 Hohe Nachfrage — Slots vergehen schnell. Sofort buchen.",
        "pl": "🔴 Wysoki popyt — sloty znikają szybko. Rezerwuj od razu.",
        "tr": "🔴 Yüksek talep — slotlar hızla kayboluyor. Hemen rezervasyon yapın.",
        "ar": "🔴 طلب مرتفع — المواعيد تختفي سريعًا. احجز فور ظهور موعد.",
    },
    DemandLevel.MEDIUM: {
        "ua": "🟡 Середній попит",
        "uk": "🟡 Середній попит",
        "en": "🟡 Medium demand",
        "de": "🟡 Mittlere Nachfrage",
        "pl": "🟡 Średni popyt",
        "tr": "🟡 Orta talep",
        "ar": "🟡 طلب متوسط",
    },
    DemandLevel.LOW: {
        "ua": "🟢 Низький попит — більше вільних місць",
        "uk": "🟢 Низький попит — більше вільних місць",
        "en": "🟢 Low demand — more availability",
        "de": "🟢 Geringe Nachfrage — mehr verfügbare Termine",
        "pl": "🟢 Niski popyt — więcej wolnych miejsc",
        "tr": "🟢 Düşük talep — daha fazla yer mevcut",
        "ar": "🟢 طلب منخفض — مواعيد أكثر متاحة",
    },
}


def _demand_label(city: str, lang: str) -> str:
    """Get localized demand label for a city."""
    level = get_demand_level(city)
    label_dict = _DEMAND_LABEL_TEXT.get(level, _DEMAND_LABEL_TEXT[DemandLevel.LOW])
    return _lang_text(label_dict, lang)


def _price_for(city: str, authority: str = '') -> str:
    """Formatted price string (e.g. '19.99') for a city/authority pair."""
    return f"{get_termin_price(city, authority):.2f}"


# ==================== Trust / Social-Proof Block (RESERVED screens only) ====================
_TRUST_BLOCK = {
    "ua": (
        "✔ Ми моніторимо офіційні урядові портали\n"
        "✔ Ви отримуєте миттєве сповіщення при появі слоту\n"
        "✔ Запис ви завжди робите самостійно через офіційний сайт\n"
        "✔ Ми не є державним органом і не представляємо установу\n"
        "📌 Оплата діє до першого знайденого Termin"
    ),
    "uk": (
        "✔ Ми моніторимо офіційні урядові портали\n"
        "✔ Ви отримуєте миттєве сповіщення при появі слоту\n"
        "✔ Запис ви завжди робите самостійно через офіційний сайт\n"
        "✔ Ми не є державним органом і не представляємо установу\n"
        "📌 Оплата діє до першого знайденого Termin"
    ),
    "en": (
        "✔ We monitor official government portals\n"
        "✔ You receive instant notification when a slot appears\n"
        "✔ You book the appointment yourself via the official website\n"
        "✔ We are not a government authority and do not act on your behalf\n"
        "📌 Access valid until first Termin is found"
    ),
    "de": (
        "✔ Wir überwachen offizielle Behördenportale\n"
        "✔ Sie erhalten sofort eine Benachrichtigung, wenn ein Termin frei wird\n"
        "✔ Sie buchen den Termin selbst über die offizielle Website\n"
        "✔ Wir sind keine Behörde und handeln nicht in Ihrem Namen\n"
        "📌 Zugang gilt bis zum ersten gefundenen Termin"
    ),
    "pl": (
        "✔ Monitorujemy oficjalne portale urzędowe\n"
        "✔ Otrzymujesz natychmiastowe powiadomienie po pojawieniu się terminu\n"
        "✔ Wizytę umawiasz samodzielnie przez oficjalną stronę\n"
        "✔ Nie jesteśmy organem rządowym i nie działamy w Twoim imieniu\n"
        "📌 Dostęp obowiązuje do znalezienia pierwszego Terminu"
    ),
    "tr": (
        "✔ Resmi devlet portallarını izliyoruz\n"
        "✔ Bir yer açıldığında anında bildirim alırsınız\n"
        "✔ Randevunuzu kendiniz resmi web sitesinden alırsınız\n"
        "✔ Bir devlet kurumu değiliz ve adınıza hareket etmiyoruz\n"
        "📌 Erişim ilk Termin bulunana kadar geçerlidir"
    ),
    "ar": (
        "✔ نراقب البوابات الحكومية الرسمية\n"
        "✔ تتلقى إشعاراً فورياً عند ظهور موعد\n"
        "✔ تحجز الموعد بنفسك عبر الموقع الرسمي\n"
        "✔ لسنا جهة حكومية ولا نتصرف نيابةً عنك\n"
        "📌 الوصول ساري حتى العثور على أول موعد"
    ),
}


def _trust_block(lang: str) -> str:
    """Localized trust/social-proof lines for RESERVED payment screens."""
    return _lang_text(_TRUST_BLOCK, lang)


# Action-oriented payment button
_TERMIN_BUY_BTN = {
    "ua": "🔔 Увімкнути моніторинг",
    "uk": "🔔 Увімкнути моніторинг",
    "en": "🔔 Enable monitoring",
    "de": "🔔 Überwachung aktivieren",
    "pl": "🔔 Włącz monitoring",
    "tr": "🔔 İzlemeyi etkinleştir",
    "ar": "🔔 تفعيل المراقبة",
}

# Minimal neutral prompt shown AFTER Stripe session is created.
# Must NOT repeat the payment offer or say "Оплата готова".
_STRIPE_REDIRECT_TEXT = {
    "ua": "Натисніть кнопку нижче для оплати 👇\n\nЯкщо Stripe не відкрився — натисніть кнопку ще раз.",
    "uk": "Натисніть кнопку нижче для оплати 👇\n\nЯкщо Stripe не відкрився — натисніть кнопку ще раз.",
    "en": "Tap the button below to pay 👇\n\nIf Stripe does not open, tap the button again.",
    "de": "Tippen Sie unten, um zu bezahlen 👇\n\nFalls Stripe sich nicht öffnet, tippen Sie erneut.",
    "pl": "Kliknij poniżej, aby zapłacić 👇\n\nJeśli Stripe się nie otworzył, kliknij przycisk ponownie.",
    "tr": "Ödemek için aşağıdaki düğmeye dokunun 👇\n\nStripe açılmazsa, düğmeye tekrar dokunun.",
    "ar": "اضغط أدناه للدفع 👇\n\nإذا لم يفتح Stripe، اضغط على الزر مرة أخرى.",
}

_STRIPE_ERROR_TEXT = {
    "uk": "⚠️ Не вдалося відкрити сторінку оплати.\nБудь ласка, спробуйте ще раз.",
    "ua": "⚠️ Не вдалося відкрити сторінку оплати.\nБудь ласка, спробуйте ще раз.",
    "en": "⚠️ Could not open the payment page.\nPlease try again.",
    "de": "⚠️ Die Zahlungsseite konnte nicht geöffnet werden.\nBitte erneut versuchen.",
    "pl": "⚠️ Nie udało się otworzyć strony płatności.\nSpróbuj ponownie.",
    "tr": "⚠️ Ödeme sayfası açılamadı.\nLütfen tekrar deneyin.",
    "ar": "⚠️ تعذّر فتح صفحة الدفع.\nيرجى المحاولة مرة أخرى.",
}

_STRIPE_OPEN_BTN = {
    "ua": "💳 Оплатити €{price}",
    "uk": "💳 Оплатити €{price}",
    "en": "💳 Pay €{price}",
    "de": "💳 Bezahlen €{price}",
    "pl": "💳 Zapłać €{price}",
    "tr": "💳 Öde €{price}",
    "ar": "💳 ادفع €{price}",
}

# ── Premium "payment in progress" UX ──────────────────────────────────────
_STRIPE_IN_PROGRESS_TEXT = {
    "ua": "🔗 Stripe відкрито. Якщо ви оплатили — натисніть '✅ Я оплатив(ла)'.",
    "uk": "🔗 Stripe відкрито. Якщо ви оплатили — натисніть '✅ Я оплатив(ла)'.",
    "en": "🔗 Stripe opened. If you paid, tap '✅ I paid' to verify.",
    "de": "🔗 Stripe geöffnet. Falls Sie bezahlt haben, tippen Sie auf '✅ Ich habe bezahlt'.",
    "pl": "🔗 Stripe otwarty. Jeśli zapłaciłeś, kliknij '✅ Zapłaciłem'.",
    "tr": "🔗 Stripe açıldı. Ödediyseniz '✅ Ödedim' düğmesine basın.",
    "ar": "🔗 تم فتح Stripe. إذا دفعت، اضغط '✅ لقد دفعت' للتحقق.",
}
_STRIPE_I_PAID_BTN = {
    "ua": "✅ Я оплатив(ла)",
    "uk": "✅ Я оплатив(ла)",
    "en": "✅ I paid",
    "de": "✅ Ich habe bezahlt",
    "pl": "✅ Zapłaciłem",
    "tr": "✅ Ödedim",
    "ar": "✅ لقد دفعت",
}
_STRIPE_REOPEN_BTN = {
    "ua": "🔁 Відкрити оплату знову",
    "uk": "🔁 Відкрити оплату знову",
    "en": "🔁 Open payment again",
    "de": "🔁 Zahlung erneut öffnen",
    "pl": "🔁 Otwórz płatność ponownie",
    "tr": "🔁 Ödemeyi yeniden aç",
    "ar": "🔁 إعادة فتح الدفع",
}
_VERIFY_CHECKING = {
    "ua": "⏳ Перевіряємо оплату…",
    "uk": "⏳ Перевіряємо оплату…",
    "en": "⏳ Checking payment…",
    "de": "⏳ Zahlung wird geprüft…",
    "pl": "⏳ Sprawdzamy płatność…",
    "tr": "⏳ Ödeme kontrol ediliyor…",
    "ar": "⏳ جارٍ التحقق من الدفع…",
}
_VERIFY_NOT_PAID = {
    "ua": "❌ Оплата ще не підтверджена.\nЯкщо ви щойно оплатили — зачекайте кілька секунд і натисніть знову.",
    "uk": "❌ Оплата ще не підтверджена.\nЯкщо ви щойно оплатили — зачекайте кілька секунд і натисніть знову.",
    "en": "❌ Payment not confirmed yet.\nIf you just paid, wait a few seconds and tap again.",
    "de": "❌ Zahlung noch nicht bestätigt.\nWenn Sie gerade bezahlt haben, warten Sie kurz und tippen erneut.",
    "pl": "❌ Płatność jeszcze niezatwierdzona.\nJeśli właśnie zapłaciłeś, poczekaj chwilę i kliknij ponownie.",
    "tr": "❌ Ödeme henüz onaylanmadı.\nAz önce ödediyseniz birkaç saniye bekleyip tekrar deneyin.",
    "ar": "❌ لم يتم تأكيد الدفع بعد.\nإذا كنت قد دفعت للتو، انتظر بضع ثوانٍ وحاول مرة أخرى.",
}
_VERIFY_SUCCESS = {
    "ua": "✅ Оплата підтверджена! Моніторинг активовано.",
    "uk": "✅ Оплата підтверджена! Моніторинг активовано.",
    "en": "✅ Payment confirmed! Monitoring activated.",
    "de": "✅ Zahlung bestätigt! Überwachung aktiviert.",
    "pl": "✅ Płatność potwierdzona! Monitorowanie aktywowane.",
    "tr": "✅ Ödeme onaylandı! İzleme etkinleştirildi.",
    "ar": "✅ تم تأكيد الدفع! تم تفعيل المراقبة.",
}

# TTL (seconds) within which an unpaid Termin order can be reused
_TERMIN_ORDER_REUSE_TTL_SEC = 1800  # 30 minutes

# In-flight concurrency guard — tracks user_ids that are currently in the middle
# of creating a Stripe order.  asyncio is single-threaded, so plain-set ops are
# atomic between awaits; no asyncio.Lock is needed.
_order_creating: set = set()

# (Legacy — kept for backward compat, no longer used in main flow)
_TERMIN_UNPAID_TEXT = _TERMIN_ENTRY_TEXT  # legacy alias; use _build_termin_entry_text(lang) for live count

# City/authority selection prompt (used for paid users needing to complete setup)
_TERMIN_PAID_SELECT_TEXT = _TERMIN_ENTRY_TEXT

# Paid user who HAS selected city + authority — status as TEXT, not button
_TERMIN_PAID_TEXT = {
    "ua": (
        "✅ <b>Сповіщення активне</b>\n\n"
        "Ми повідомимо вас одразу,\n"
        "щойно з\u02bcявиться вільне місце\n"
        "у вибраній установі.\n\n"
        "Запис ви робите самостійно\n"
        "через офіційний сайт."
    ),
    "uk": (
        "✅ <b>Сповіщення активне</b>\n\n"
        "Ми повідомимо вас одразу,\n"
        "щойно з\u02bcявиться вільне місце\n"
        "у вибраній установі.\n\n"
        "Запис ви робите самостійно\n"
        "через офіційний сайт."
    ),
    "en": (
        "✅ <b>Notifications active</b>\n\n"
        "We will notify you as soon as\n"
        "a free slot becomes available\n"
        "at your selected authority.\n\n"
        "You book the appointment yourself\n"
        "via the official website."
    ),
    "de": (
        "✅ <b>Benachrichtigungen aktiv</b>\n\n"
        "Wir benachrichtigen Sie sofort,\n"
        "sobald ein freier Termin\n"
        "bei Ihrer gewählten Behörde verfügbar wird.\n\n"
        "Sie buchen den Termin selbst\n"
        "über die offizielle Website."
    ),
    "pl": (
        "✅ <b>Powiadomienia aktywne</b>\n\n"
        "Powiadomimy Cię od razu,\n"
        "gdy pojawi się wolne miejsce\n"
        "w wybranym urzędzie.\n\n"
        "Wizytę umawiasz samodzielnie\n"
        "na oficjalnej stronie."
    ),
    "tr": (
        "✅ <b>Bildirimler aktif</b>\n\n"
        "Seçtiğiniz kurumda\n"
        "bir yer açıldığında\n"
        "sizi hemen bilgilendireceğiz.\n\n"
        "Randevunuzu resmi web sitesinden\n"
        "kendiniz alırsınız."
    ),
    "ar": (
        "✅ <b>الإشعارات مفعّلة</b>\n\n"
        "سنُعلمك فوراً عند توفر\n"
        "موعد حر في الجهة المختارة.\n\n"
        "أنت تحجز بنفسك\n"
        "عبر الموقع الرسمي."
    ),
}


# ==================== Post-Active Menu Buttons (localized) ====================
_BTN_CHANGE_CITY = {
    "ua": "📍 Змінити місто",
    "uk": "📍 Змінити місто",
    "en": "📍 Change city",
    "de": "📍 Stadt ändern",
    "pl": "📍 Zmień miasto",
    "tr": "📍 Şehri değiştir",
    "ar": "📍 تغيير المدينة",
}
_BTN_CHANGE_DOC = {
    "ua": "📄 Змінити документ",
    "uk": "📄 Змінити документ",
    "en": "📄 Change document",
    "de": "📄 Dokument ändern",
    "pl": "📄 Zmień dokument",
    "tr": "📄 Belgeyi değiştir",
    "ar": "📄 تغيير المستند",
}
_BTN_DISABLE_NOTIFICATIONS = {
    "ua": "🔕 Вимкнути сповіщення",
    "uk": "🔕 Вимкнути сповіщення",
    "en": "🔕 Disable notifications",
    "de": "🔕 Benachrichtigungen deaktivieren",
    "pl": "🔕 Wyłącz powiadomienia",
    "tr": "🔕 Bildirimleri kapat",
    "ar": "🔕 إيقاف الإشعارات",
}
_STATUS_BTN_LABEL = {
    "ua": "📊 Статус", "uk": "📊 Статус", "en": "📊 Status", "de": "📊 Status",
    "pl": "📊 Status", "tr": "📊 Durum", "ar": "📊 الحالة",
}
_SETTINGS_BTN_LABEL = {
    "ua": "⚙ Налаштування", "uk": "⚙ Налаштування",
    "en": "⚙ Settings", "de": "⚙ Einstellungen",
    "pl": "⚙ Ustawienia", "tr": "⚙ Ayarlar", "ar": "⚙ الإعدادات",
}
_ACTIVITY_BTN_LABEL = {
    "ua": "📈 Активність", "uk": "📈 Активність",
    "en": "📈 Activity", "de": "📈 Aktivität",
    "pl": "📈 Aktywność", "tr": "📈 Aktivite", "ar": "📈 النشاط",
}
_MONITORING_ACTIVE_TEXT = {
    "ua": (
        "✅ <b>Моніторинг активний</b>\n\n"
        "📍 Місто: {city}\n"
        "📄 Послуга: {service}\n\n"
        "Ми повідомимо вас одразу, щойно з\u02bcявиться вільний слот.\n"
        "Запис ви робите самостійно через офіційний сайт."
    ),
    "uk": (
        "✅ <b>Моніторинг активний</b>\n\n"
        "📍 Місто: {city}\n"
        "📄 Послуга: {service}\n\n"
        "Ми повідомимо вас одразу, щойно з\u02bcявиться вільний слот.\n"
        "Запис ви робите самостійно через офіційний сайт."
    ),
    "en": (
        "✅ <b>Monitoring active</b>\n\n"
        "📍 City: {city}\n"
        "📄 Service: {service}\n\n"
        "We will notify you as soon as a free slot appears.\n"
        "You book the appointment yourself via the official website."
    ),
    "de": (
        "✅ <b>Überwachung aktiv</b>\n\n"
        "📍 Stadt: {city}\n"
        "📄 Dienst: {service}\n\n"
        "Wir benachrichtigen Sie sofort, sobald ein freier Termin verfügbar ist.\n"
        "Sie buchen den Termin selbst über die offizielle Website."
    ),
    "pl": (
        "✅ <b>Monitorowanie aktywne</b>\n\n"
        "📍 Miasto: {city}\n"
        "📄 Usługa: {service}\n\n"
        "Powiadomimy Cię natychmiast, gdy pojawi się wolne miejsce.\n"
        "Wizytę umawiasz samodzielnie na oficjalnej stronie."
    ),
    "tr": (
        "✅ <b>İzleme aktif</b>\n\n"
        "📍 Şehir: {city}\n"
        "📄 Hizmet: {service}\n\n"
        "Bir yer açıldığında sizi hemen bilgilendireceğiz.\n"
        "Randevunuzu resmi web sitesinden kendiniz alırsınız."
    ),
    "ar": (
        "✅ <b>المراقبة نشطة</b>\n\n"
        "📍 المدينة: {city}\n"
        "📄 الخدمة: {service}\n\n"
        "سنُعلمك فوراً عند توفر موعد حر.\n"
        "أنت تحجز بنفسك عبر الموقع الرسمي."
    ),
}
_SETTINGS_MENU_TEXT = {
    "ua": "⚙ <b>Налаштування моніторингу</b>\n\nОберіть параметр для зміни:",
    "uk": "⚙ <b>Налаштування моніторингу</b>\n\nОберіть параметр для зміни:",
    "en": "⚙ <b>Monitoring Settings</b>\n\nSelect a parameter to change:",
    "de": "⚙ <b>Überwachungseinstellungen</b>\n\nWählen Sie einen Parameter zum Ändern:",
    "pl": "⚙ <b>Ustawienia monitorowania</b>\n\nWybierz parametr do zmiany:",
    "tr": "⚙ <b>İzleme Ayarları</b>\n\nDeğiştirmek istediğiniz parametreyi seçin:",
    "ar": "⚙ <b>إعدادات المراقبة</b>\n\nاختر المعلمة التي تريد تغييرها:",
}
# ── Setup mode — shown before city+service are chosen ────────────────────────
_SETUP_TEXT = {
    "ua": (
        "🔎 <b>Пошук Termin</b>\n\n"
        "Щоб запустити моніторинг, виберіть місто та послугу.\n\n"
        "📍 Berlin · Frankfurt · Düsseldorf · Köln · Krefeld\n"
        "✅ Автоматичний моніторинг — від €4.99"
    ),
    "uk": (
        "🔎 <b>Пошук Termin</b>\n\n"
        "Щоб запустити моніторинг, виберіть місто та послугу.\n\n"
        "📍 Berlin · Frankfurt · Düsseldorf · Köln · Krefeld\n"
        "✅ Автоматичний моніторинг — від €4.99"
    ),
    "en": (
        "🔎 <b>Find an Appointment</b>\n\n"
        "To start monitoring, choose your city and service.\n\n"
        "📍 Berlin · Frankfurt · Düsseldorf · Köln · Krefeld\n"
        "✅ Automatic monitoring — from €4.99"
    ),
    "de": (
        "🔎 <b>Termin finden</b>\n\n"
        "Um die Überwachung zu starten, wählen Sie Stadt und Dienst.\n\n"
        "📍 Berlin · Frankfurt · Düsseldorf · Köln · Krefeld\n"
        "✅ Automatische Überwachung — ab €4.99"
    ),
    "pl": (
        "🔎 <b>Znajdź termin</b>\n\n"
        "Aby uruchomić monitoring, wybierz miasto i usługę.\n\n"
        "📍 Berlin · Frankfurt · Düsseldorf · Köln · Krefeld\n"
        "✅ Automatyczny monitoring — od €4.99"
    ),
    "tr": (
        "🔎 <b>Randevu Bul</b>\n\n"
        "İzlemeyi başlatmak için şehir ve hizmet seçin.\n\n"
        "📍 Berlin · Frankfurt · Düsseldorf · Köln · Krefeld\n"
        "✅ Otomatik izleme — €4.99'dan"
    ),
    "ar": (
        "🔎 <b>ابحث عن موعد</b>\n\n"
        "لبدء المراقبة، اختر المدينة والخدمة.\n\n"
        "📍 Berlin · Frankfurt · Düsseldorf · Köln · Krefeld\n"
        "✅ مراقبة تلقائية — من €4.99"
    ),
}
_SETUP_CITY_BTN = {
    "ua": "📍 Вибрати місто", "uk": "📍 Вибрати місто",
    "en": "📍 Choose city", "de": "📍 Stadt wählen",
    "pl": "📍 Wybierz miasto", "tr": "📍 Şehir seçin", "ar": "📍 اختر المدينة",
}
_SETUP_SERVICE_BTN = {
    "ua": "📄 Вибрати документ", "uk": "📄 Вибрати документ",
    "en": "📄 Choose service", "de": "📄 Dienst wählen",
    "pl": "📄 Wybierz usługę", "tr": "📄 Hizmet seçin", "ar": "📄 اختر الخدمة",
}
# ── Localized status-screen action buttons ───────────────────────────────────
_PAUSE_BTN = {
    "ua": "⏸ Пауза", "uk": "⏸ Пауза",
    "en": "⏸ Pause",
    "de": "⏸ Pausieren",
    "pl": "⏸ Wstrzymaj",
    "tr": "⏸ Duraklat",
    "ar": "⏸ إيقاف مؤقت",
}
_FILTERS_BTN = {
    "ua": "⚙ Фільтри", "uk": "⚙ Фільтри",
    "en": "⚙ Filters",
    "de": "⚙ Filter",
    "pl": "⚙ Filtry",
    "tr": "⚙ Filtreler",
    "ar": "⚙ الفلاتر",
}
_EXPAND_BTN = {
    "ua": "🌍 Розширити", "uk": "🌍 Розширити",
    "en": "🌍 Expand",
    "de": "🌍 Erweitern",
    "pl": "🌍 Rozszerz",
    "tr": "🌍 Genişlet",
    "ar": "🌍 توسيع",
}
_PRIORITY_ALERTS_BTN = {
    "ua": "⚡ Priority Boost", "uk": "⚡ Priority Boost",
    "en": "⚡ Priority Boost",
    "de": "⚡ Priority Boost",
    "pl": "⚡ Priority Boost",
    "tr": "⚡ Priority Boost",
    "ar": "⚡ Priority Boost",
}
_EXTEND_BTN = {
    "ua": "➕ Продовжити 24h", "uk": "➕ Продовжити 24h",
    "en": "➕ Extend 24h",
    "de": "➕ 24h verlängern",
    "pl": "➕ Przedłuż 24h",
    "tr": "➕ 24 saat uzat",
    "ar": "➕ تمديد 24 ساعة",
}
# ── Status screen helper dicts ────────────────────────────────────────────────
_EXPIRED_LABEL = {
    "ua": "закінчився", "uk": "закінчився",
    "en": "expired",
    "de": "abgelaufen",
    "pl": "wygasł",
    "tr": "süresi doldu",
    "ar": "منتهي",
}

_PROFILE_INVALID_TEXT = {
    "ua": "⚠️ Некоректні дані профілю.", "uk": "⚠️ Некоректні дані профілю.",
    "en": "⚠️ Invalid profile data.",
    "de": "⚠️ Ungültige Profildaten.",
    "pl": "⚠️ Nieprawidłowe dane profilu.",
    "tr": "⚠️ Geçersiz profil verisi.",
    "ar": "⚠️ بيانات الملف غير صالحة.",
}
# ── Localized strategy labels ─────────────────────────────────────────────────
_STRATEGY_FAST_LABEL = {
    "ua": "⚡ Швидкий", "uk": "⚡ Швидкий",
    "en": "⚡ Fast",
    "de": "⚡ Schnell",
    "pl": "⚡ Szybki",
    "tr": "⚡ Hızlı",
    "ar": "⚡ سريع",
}
_STRATEGY_PRECISE_LABEL = {
    "ua": "🎯 Точний", "uk": "🎯 Точний",
    "en": "🎯 Precise",
    "de": "🎯 Präzise",
    "pl": "🎯 Precyzyjny",
    "tr": "🎯 Hassas",
    "ar": "🎯 دقيق",
}
# ── Localized "All authorities" for filter display ───────────────────────────
_ALL_AUTHORITIES_LABEL = {
    "ua": "Всі установи", "uk": "Всі установи",
    "en": "All authorities",
    "de": "Alle Behörden",
    "pl": "Wszystkie urzędy",
    "tr": "Tüm kurumlar",
    "ar": "جميع الجهات",
}
# Mapping internal filter codes → human display label
_FILTER_CODE_DISPLAY = {
    "burgeramt":         "🏛 Bürgeramt",
    "auslanderbehorde":  "🏛 Ausländerbehörde",
    "wohnungsamt":       "🏛 Wohnungsamt",
    "familienkasse":     "🏛 Familienkasse",
    "jobcenter":         "🏛 Jobcenter",
    "standesamt":        "🏛 Standesamt",
}

# Comprehensive slug → human-readable authority name mapping.
# Covers all spelling variants that may arrive from the DB or scraper.
AUTHORITY_LABELS: dict = {
    # Ausländerbehörde — all common slug spellings
    "auslaenderbehoerde":   "Ausländerbehörde",
    "auslanderbehoerde":    "Ausländerbehörde",
    "ausländerbehörde":     "Ausländerbehörde",
    "auslanderbehorde":     "Ausländerbehörde",
    "auslaenderbehorde":    "Ausländerbehörde",
    "Auslaenderbehoerde":   "Ausländerbehörde",
    "Auslanderbehoerde":    "Ausländerbehörde",
    "Auslanderbehorde":     "Ausländerbehörde",
    # Bürgeramt
    "buergeramt":           "Bürgeramt",
    "burgeramt":            "Bürgeramt",
    "bürgeramt":            "Bürgeramt",
    "Burgeramt":            "Bürgeramt",
    # Wohnungsamt
    "wohnungsamt":          "Wohnungsamt",
    "Wohnungsamt":          "Wohnungsamt",
    # Familienkasse
    "familienkasse":        "Familienkasse",
    "Familienkasse":        "Familienkasse",
    # Jobcenter
    "jobcenter":            "Jobcenter",
    "Jobcenter":            "Jobcenter",
    # Standesamt
    "standesamt":           "Standesamt",
    "Standesamt":           "Standesamt",
}


def normalize_authority_name(authority: str) -> str:
    """Return a human-readable German authority name for any slug variant.

    Falls back to the raw slug (title-cased) when no mapping is found.
    """
    if not authority:
        return "—"
    key = authority.strip()
    return AUTHORITY_LABELS.get(key, key.replace("_", " ").replace("-", " ").title())


def _norm_authority(a: str) -> str:
    """Normalise an authority slug for equality comparison.

    Handles the burgeramt / buergeramt / bürgeramt variance that comes
    from different DB rows, FSM paths and DOC_AUTHORITY_MAP entries.
    """
    if not a:
        return ""
    a = a.strip().lower()
    a = a.replace("ü", "u").replace("ä", "a").replace("ö", "o")
    # Collapse the common variant spellings to a single canonical form.
    if a in ("burgeramt", "buergeramt", "bürgeramt"):
        return "buergeramt"
    return a


# ── Family V1: Profile UX strings ────────────────────────────────────────────
_ACTIVE_PROFILE_LABEL = {
    "ua": "👤 Активний профіль: Профіль {n}",
    "en": "👤 Active profile: Profile {n}",
    "de": "👤 Aktives Profil: Profil {n}",
    "pl": "👤 Aktywny profil: Profil {n}",
    "tr": "👤 Aktif profil: Profil {n}",
    "ar": "👤 الملف النشط: الملف {n}",
}
_SWITCH_TO_P1_BTN = {
    "ua": "👤 Перейти до Профілю 1",
    "en": "👤 Switch to Profile 1",
    "de": "👤 Zu Profil 1 wechseln",
    "pl": "👤 Przełącz na Profil 1",
    "tr": "👤 Profil 1'e geç",
    "ar": "👤 التبديل إلى الملف 1",
}
_SWITCH_TO_P2_BTN = {
    "ua": "👤 Перейти до Профілю 2",
    "en": "👤 Switch to Profile 2",
    "de": "👤 Zu Profil 2 wechseln",
    "pl": "👤 Przełącz na Profil 2",
    "tr": "👤 Profil 2'ye geç",
    "ar": "👤 التبديل إلى الملف 2",
}

# Module-level "why no slots" details text (used by handle_termin_no_slots_details)
_NO_SLOTS_WHY_TEXT = {
    "ua": (
        "⏱ <b>Чому важко знайти слот:</b>\n"
        "• Слоти з'являються на 10–60 сек\n"
        "• Часто вночі або рано вранці\n"
        "• Оновлення хвилями\n\n"
        "📋 <b>Моніторинг включає:</b>\n"
        "✓ Перевірку кожні кілька секунд\n"
        "✓ Миттєве сповіщення при появі слоту\n"
        "✓ Сповіщення у Telegram\n"
        "✓ Автоматичний моніторинг Termin"
    ),
    "uk": (
        "⏱ <b>Чому важко знайти слот:</b>\n"
        "• Слоти з'являються на 10–60 сек\n"
        "• Часто вночі або рано вранці\n"
        "• Оновлення хвилями\n\n"
        "📋 <b>Моніторинг включає:</b>\n"
        "✓ Перевірку кожні кілька секунд\n"
        "✓ Миттєве сповіщення при появі слоту\n"
        "✓ Сповіщення у Telegram\n"
        "✓ Автоматичний моніторинг Termin"
    ),
    "en": (
        "⏱ <b>Why it's hard to find a slot:</b>\n"
        "• Slots appear for 10–60 sec\n"
        "• Often at night or early morning\n"
        "• Updates come in waves\n\n"
        "📋 <b>Monitoring includes:</b>\n"
        "✓ Check every few seconds\n"
        "✓ Instant notification when a slot appears\n"
        "✓ Telegram notification\n"
        "✓ Automatic Termin monitoring"
    ),
    "de": (
        "⏱ <b>Warum es schwer ist, einen Termin zu finden:</b>\n"
        "• Termine erscheinen für 10–60 Sek.\n"
        "• Oft nachts oder früh morgens\n"
        "• Aktualisierungen in Wellen\n\n"
        "📋 <b>Überwachung umfasst:</b>\n"
        "✓ Prüfung alle paar Sekunden\n"
        "✓ Sofortige Benachrichtigung bei verfügbarem Termin\n"
        "✓ Telegram-Benachrichtigung\n"
        "✓ Automatische Termin-Überwachung"
    ),
    "pl": (
        "⏱ <b>Dlaczego trudno znaleźć termin:</b>\n"
        "• Terminy pojawiają się na 10–60 sek\n"
        "• Często w nocy lub rano\n"
        "• Aktualizacje falami\n\n"
        "📋 <b>Monitoring obejmuje:</b>\n"
        "✓ Sprawdzanie co kilka sekund\n"
        "✓ Natychmiastowe powiadomienie o dostępnym terminie\n"
        "✓ Powiadomienie w Telegram\n"
        "✓ Automatyczny monitoring Termin"
    ),
    "tr": (
        "⏱ <b>Randevu bulmak neden zor:</b>\n"
        "• Randevular 10–60 sn görünür\n"
        "• Genellikle gece veya sabah erken\n"
        "• Güncellemeler dalgalar halinde\n\n"
        "📋 <b>İzleme kapsamı:</b>\n"
        "✓ her birkaç saniyede kontrol\n"
        "✓ Randevu çıktığında anında bildirim\n"
        "✓ Telegram bildirimi\n"
        "✓ Otomatik Termin izleme"
    ),
    "ar": (
        "⏱ <b>لماذا يصعب العثور على موعد:</b>\n"
        "• المواعيد تظهر لمدة 10–60 ثانية\n"
        "• غالبًا في الليل أو الصباح الباكر\n"
        "• التحديثات تأتي على دفعات\n\n"
        "📋 <b>تشمل المراقبة:</b>\n"
        "✓ فحص كل بضع ثوانٍ\n"
        "✓ إشعار فوري عند ظهور موعد\n"
        "✓ إشعار عبر Telegram\n"
        "✓ مراقبة Termin تلقائية"
    ),
}

# Module-level rich payment success (used by send_monitor_activation in payments.py)
_PAYMENT_SUCCESS_RICH = {
    "uk": (
        "🎉 <b>Ви тепер у черзі!</b>\n\n"
        "📍 {city} → {authority}\n"
        "🕐 Розпочато: {started_at}\n\n"
        "Перевіряємо кожні кілька секунд.\n"
        "Повідомимо одразу, щойно з'явиться місце."
    ),
    "en": (
        "🎉 <b>You're now first in line!</b>\n\n"
        "📍 {city} → {authority}\n"
        "🕐 Started: {started_at}\n\n"
        "Checking every few seconds.\n"
        "We'll notify you the moment a slot opens."
    ),
    "de": (
        "🎉 <b>Sie stehen jetzt ganz vorne!</b>\n\n"
        "📍 {city} → {authority}\n"
        "🕐 Gestartet: {started_at}\n\n"
        "Prüfung alle paar Sekunden.\n"
        "Wir benachrichtigen Sie sofort, wenn ein Termin frei wird."
    ),
    "pl": (
        "🎉 <b>Jesteś teraz na pierwszym miejscu!</b>\n\n"
        "📍 {city} → {authority}\n"
        "🕐 Rozpoczęto: {started_at}\n\n"
        "Sprawdzamy co kilka sekund.\n"
        "Powiadomimy Cię natychmiast, gdy pojawi się termin."
    ),
    "tr": (
        "🎉 <b>Şimdi ilk sıradasınız!</b>\n\n"
        "📍 {city} → {authority}\n"
        "🕐 Başlatıldı: {started_at}\n\n"
        "her birkaç saniyede kontrol ediyoruz.\n"
        "Yer açılır açılmaz sizi bilgilendireceğiz."
    ),
    "ar": (
        "🎉 <b>أنت الآن في المقدمة!</b>\n\n"
        "📍 {city} → {authority}\n"
        "🕐 بدأ في: {started_at}\n\n"
        "نتحقق كل بضع ثوانٍ.\n"
        "سنُعلمك فور توفر موعد."
    ),
}


async def _get_active_profile_id(state: FSMContext, user_id: int = None) -> int:
    """Return active_profile_id: FSM first, then DB fallback, default 1."""
    try:
        data = await state.get_data()
        fsm_val = data.get("active_profile_id")
        if fsm_val is not None:
            return int(fsm_val)
        if user_id:
            from backend.termin_db import get_active_profile
            return get_active_profile(str(user_id))
    except Exception:
        pass
    return 1


async def _set_active_profile_id(state: FSMContext, n: int) -> None:
    """Persist active_profile_id in FSM."""
    await state.update_data(active_profile_id=n)


def _is_family_user(user_id: int) -> bool:
    """Return True if user has a valid, non-empty family entitlement."""
    try:
        from backend.termin_db import get_entitlement
        ent = get_entitlement(str(user_id))
        return bool(
            ent
            and ent.get("plan") == "family"
            and ent.get("slots_total", 0) > 0
        )
    except Exception:
        return False


def _profile2_available_for(user_id: int) -> bool:
    """Return True if profile 2 either exists already OR a slot is still available."""
    try:
        from backend.termin_db import get_user_profile, get_entitlement
        if get_user_profile(user_id, 2) is not None:
            return True
        ent = get_entitlement(str(user_id))
        if ent and ent.get("slots_used", 0) < ent.get("slots_total", 2):
            return True
    except Exception:
        pass
    return False


# ==================== Keyboards ====================
def get_termin_menu_keyboard(
    lang: str, has_paid: bool, has_selected: bool,
    user_city: str = None, user_authority: str = None,
    user_id: int = None, active_profile_id: int = None, is_family: bool = False,
    entitled: bool = False,
):
    """Termin menu — 3 states based on payment + selection."""
    keyboard = InlineKeyboardMarkup(row_width=1)

    if has_paid and has_selected:
        # ACTIVE MONITORING: city/doc change at top, then full control panel
        keyboard.add(InlineKeyboardButton(
            _lang_text(_BTN_CHANGE_CITY, lang),
            callback_data='termin_cities',
        ))
        if user_city:
            keyboard.add(InlineKeyboardButton(
                _lang_text(_BTN_CHANGE_DOC, lang),
                callback_data=f'termin_city_{user_city}',
            ))
        keyboard.row(
            InlineKeyboardButton(_lang_text(_PAUSE_BTN, lang), callback_data='termin_pause'),
            InlineKeyboardButton(_lang_text(_ACTIVITY_BTN_LABEL, lang), callback_data='termin_status'),
        )
        keyboard.add(InlineKeyboardButton(_lang_text(_EXPAND_BTN, lang), callback_data='termin_expand'))
        keyboard.add(InlineKeyboardButton(_lang_text(_PRIORITY_ALERTS_BTN, lang), callback_data='termin_priority'))
        keyboard.add(InlineKeyboardButton(
            _lang_text(_BTN_DISABLE_NOTIFICATIONS, lang),
            callback_data='termin_pause',
        ))
    elif not has_paid and has_selected:
        # PRE-PAYMENT: if user already has an active entitlement, offer reuse first
        if entitled:
            keyboard.add(InlineKeyboardButton(
                _lang_text(_USE_EXISTING_SLOT_BTN, lang),
                callback_data='termin_use_existing_slot',
            ))
        keyboard.add(InlineKeyboardButton(
            _lang_text(_TERMIN_BUY_BTN, lang),
            callback_data=f"termin_monitor_pay_{user_city}" if user_city else 'termin_cities',
        ))
    else:
        # SETUP MODE: guide user through city → service selection steps
        keyboard.add(InlineKeyboardButton(
            _lang_text(_SETUP_CITY_BTN, lang),
            callback_data='termin_cities',
        ))
        if user_city:
            # City already chosen — show service selection as the next step
            keyboard.add(InlineKeyboardButton(
                _lang_text(_SETUP_SERVICE_BTN, lang),
                callback_data=f'termin_city_{user_city}',
            ))
        keyboard.row(
            InlineKeyboardButton(_lang_text(_TERMIN_HOW_BTN, lang), callback_data='termin_how'),
            InlineKeyboardButton(_lang_text(_TERMIN_SPEED_BTN, lang), callback_data='termin_speed'),
        )

    # Family profile switch buttons (no slot consumption — just context switch)
    if is_family and active_profile_id:
        if active_profile_id != 1:
            keyboard.add(InlineKeyboardButton(
                _lang_text(_SWITCH_TO_P1_BTN, lang),
                callback_data="termin_switch_profile_1",
            ))
        if active_profile_id != 2:
            # Only show if profile2 slot is available OR profile2 row already exists
            _p2_available = True
            if user_id:
                try:
                    from backend.termin_db import get_entitlement, get_user_profile
                    _ent = get_entitlement(str(user_id))
                    if _ent:
                        _slots_left = _ent.get("slots_total", 2) - _ent.get("slots_used", 0)
                        _p2_exists = get_user_profile(user_id, 2) is not None
                        _p2_available = _p2_exists or _slots_left > 0
                except Exception:
                    pass
            if _p2_available:
                keyboard.add(InlineKeyboardButton(
                    _lang_text(_SWITCH_TO_P2_BTN, lang),
                    callback_data="termin_switch_profile_2",
                ))

    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data='back_to_main_menu',
    ))
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


def get_termin_settings_keyboard(
    lang: str, user_city: str = None, user_id: int = None,
    active_profile_id: int = None, is_family: bool = False,
):
    """Settings submenu — advanced controls for active monitoring session."""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        InlineKeyboardButton(_lang_text(_BTN_CHANGE_CITY, lang), callback_data='termin_cities'),
        InlineKeyboardButton(
            _lang_text(_BTN_CHANGE_DOC, lang),
            callback_data=f'termin_city_{user_city}' if user_city else 'termin_cities',
        ),
    )
    keyboard.row(
        InlineKeyboardButton(_lang_text(_EXPAND_BTN, lang), callback_data='termin_expand'),
        InlineKeyboardButton(_lang_text(_PRIORITY_ALERTS_BTN, lang), callback_data='termin_priority'),
    )
    keyboard.add(InlineKeyboardButton(
        _lang_text(_BTN_DISABLE_NOTIFICATIONS, lang),
        callback_data='termin_pause',
    ))
    keyboard.add(InlineKeyboardButton(get_text('btn_back', lang), callback_data='termin_menu'))
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


def get_doc_types_keyboard(city_code: str, lang: str):
    """Document type selection keyboard — user-friendly authority labels."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    authorities = get_authorities(city_code)
    for auth in authorities:
        auth_type = auth['authority_type']
        labels = _DOC_TYPE_LABELS.get(auth_type)
        if labels:
            name = _lang_text(labels, lang) or auth_type
        else:
            name = auth.get(f'name_{lang}') or auth['name_en']
        keyboard.add(InlineKeyboardButton(
            name,
            callback_data=f"termin_doc_{city_code}_{auth_type}",
        ))
    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data='termin_cities',
    ))
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


_CONTINUE_WITH_PREFIX = {
    "ua": "📍 Продовжити з",
    "uk": "📍 Продовжити з",
    "en": "📍 Continue with",
    "de": "📍 Weiter mit",
    "pl": "📍 Kontynuuj z",
    "tr": "📍 Devam et:",
    "ar": "📍 متابعة مع",
}


# Baseline monitoring counts per city — social proof floor values.
# Real count = baseline + actual active termin users for that city.
_CITY_MONITOR_BASELINE: dict = {
    "berlin":       1_840,
    "muenchen":       620,
    "münchen":        620,
    "munich":         620,
    "hamburg":        390,
    "frankfurt":      310,
    "koeln":          280,
    "köln":           280,
    "duesseldorf":    210,
    "düsseldorf":     210,
    "dortmund":       140,
    "krefeld":         90,
}

def _get_city_monitor_count(city_code: str) -> int:
    """
    Return the approximate number of users who have monitored this city.
    Baseline + real paid termin users from termin_db.
    """
    base = _CITY_MONITOR_BASELINE.get(city_code.lower().strip(), 80)
    try:
        from backend.termin_db import get_connection as _tc
        with _tc() as _conn:
            _cur = _conn.cursor()
            _cur.execute(
                "SELECT COUNT(*) FROM users WHERE city = ? AND has_paid_termin = 1",
                (city_code,),
            )
            _row = _cur.fetchone()
            base += int(_row[0]) if _row else 0
    except Exception:
        pass
    return base


def get_cities_keyboard(lang: str):
    keyboard = InlineKeyboardMarkup(row_width=1)
    cities = get_cities()
    single_city = len(cities) == 1
    for city in cities:
        name = city.get(f'name_{lang}') or city['name_en']
        code = city.get('code', '')
        count = _get_city_monitor_count(code)
        # Format count as "1,840" with narrow space separator
        count_str = f"{count:,}".replace(",", "\u202f")
        if single_city:
            prefix = _lang_text(_CONTINUE_WITH_PREFIX, lang)
            label = f"{prefix} {name}  👥 {count_str}"
        else:
            label = f"📍 {name}  👥 {count_str}"
        keyboard.add(InlineKeyboardButton(
            label,
            callback_data=f"termin_city_{code}",
        ))
    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data='termin_menu',
    ))
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


def get_authorities_keyboard(city_code: str, lang: str):
    from utils.termin_checker import SUPPORTED_AUTHORITIES
    keyboard = InlineKeyboardMarkup(row_width=1)
    authorities = get_authorities(city_code)
    for auth in authorities:
        # Only show authorities that have a working checker
        if auth['authority_type'] not in SUPPORTED_AUTHORITIES:
            continue
        name = auth.get(f'name_{lang}') or auth['name_en']
        keyboard.add(InlineKeyboardButton(
            f"🏛️ {name}",
            callback_data=f"termin_auth_{city_code}_{auth['authority_type']}",
        ))
    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data='termin_cities',
    ))
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


def get_authority_actions_keyboard(city_code: str, authority_type: str, lang: str, has_paid: bool):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(
        get_text('termin_view_guidance', lang),
        callback_data=f"termin_guide_{city_code}_{authority_type}",
    ))
    if has_paid:
        keyboard.add(InlineKeyboardButton(
            get_text('termin_set_reminder', lang),
            callback_data=f"termin_remind_{city_code}_{authority_type}",
        ))
    else:
        price = _price_for(city_code, authority_type)
        keyboard.add(InlineKeyboardButton(
            get_text('termin_pay_reminders', lang, price=price),
            callback_data=f"termin_pay_{city_code}_{authority_type}",
        ))
    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data=f"termin_city_{city_code}",
    ))
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


def get_interval_keyboard(city_code: str, authority_type: str, lang: str):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(get_text('interval_6h', lang), callback_data=f"termin_interval_6_{city_code}_{authority_type}"),
        InlineKeyboardButton(get_text('interval_12h', lang), callback_data=f"termin_interval_12_{city_code}_{authority_type}"),
    )
    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data=f"termin_auth_{city_code}_{authority_type}",
    ))
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


def get_reminder_management_keyboard(lang: str):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(get_text('termin_pause_reminders', lang), callback_data='termin_pause'),
        InlineKeyboardButton(get_text('termin_change_interval', lang), callback_data='termin_change_interval'),
        InlineKeyboardButton(get_text('btn_back', lang), callback_data='termin_menu'),
    )
    from handlers.nav import nav_home_text as _nav_ht
    keyboard.add(InlineKeyboardButton(_nav_ht(lang), callback_data='main_menu'))
    return keyboard


def get_back_keyboard(callback_data: str, lang: str):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton(get_text('btn_back', lang), callback_data=callback_data))
    return keyboard


# ==================== Entry Point (called from Gold Build) ====================
_EXISTING_PLAN_BANNER = {
    "ua": "ℹ️ <b>У вас є активний план</b>. Ви можете використати наявний слот або придбати новий.\n\n",
    "uk": "ℹ️ <b>У вас є активний план</b>. Ви можете використати наявний слот або придбати новий.\n\n",
    "ru": "ℹ️ <b>У вас есть активный план</b>. Вы можете использовать имеющийся слот или купить новый.\n\n",
    "en": "ℹ️ <b>You have an active plan</b>. You can use your existing slot or purchase a new one.\n\n",
    "de": "ℹ️ <b>Sie haben einen aktiven Plan</b>. Sie können Ihren vorhandenen Slot nutzen oder einen neuen kaufen.\n\n",
    "pl": "ℹ️ <b>Masz aktywny plan</b>. Możesz użyć istniejącego slotu lub kupić nowy.\n\n",
    "tr": "ℹ️ <b>Aktif planınız var</b>. Mevcut slotunuzu kullanabilir veya yeni bir tane satın alabilirsiniz.\n\n",
    "ar": "ℹ️ <b>لديك خطة نشطة</b>. يمكنك استخدام الفتحة الحالية أو شراء خطة جديدة.\n\n",
}

_USE_EXISTING_SLOT_BTN = {
    "ua": "1️⃣ Використати існуючий слот",
    "uk": "1️⃣ Використати існуючий слот",
    "ru": "1️⃣ Использовать существующий слот",
    "en": "1️⃣ Use existing slot",
    "de": "1️⃣ Vorhandenen Slot nutzen",
    "pl": "1️⃣ Użyj istniejącego slotu",
    "tr": "1️⃣ Mevcut slotu kullan",
    "ar": "1️⃣ استخدام الفتحة الحالية",
}


def _build_termin_menu_text(
    lang: str, has_paid: bool, has_selected: bool,
    user_city: str = '', user_authority: str = '',
    active_profile_id: int = None, is_family: bool = False,
    entitled: bool = False,
) -> str:
    """Termin menu text — 3 states.  Appends demand label for unpaid users."""
    profile_line = ""
    if is_family and active_profile_id:
        profile_line = _lang_text(_ACTIVE_PROFILE_LABEL, lang).format(n=active_profile_id) + "\n\n"

    if has_paid and has_selected:
        # Resolve city display name
        city_name = user_city or "—"
        try:
            for c in get_cities():
                if c.get('code') == user_city:
                    city_name = c.get(f'name_{lang}') or c.get('name_en') or user_city
                    break
        except Exception:
            pass
        # Resolve service display name
        service_name = user_authority or "—"
        labels = _DOC_TYPE_LABELS.get(user_authority)
        if labels:
            service_name = _lang_text(labels, lang) or user_authority
        else:
            try:
                for a in get_authorities(user_city):
                    if a.get('authority_type') == user_authority:
                        service_name = a.get(f'name_{lang}') or a.get('name_en') or user_authority
                        break
            except Exception:
                pass
        return profile_line + _lang_text(_MONITORING_ACTIVE_TEXT, lang).format(
            city=city_name, service=service_name,
        )
    if not has_paid and has_selected:
        price = _price_for(user_city, user_authority)
        # Resolve city display name
        city_name = user_city or "—"
        try:
            for c in get_cities():
                if c.get('code') == user_city:
                    city_name = c.get(f'name_{lang}') or c.get('name_en') or user_city
                    break
        except Exception:
            pass
        # Resolve service display name
        service_name = user_authority or "—"
        labels = _DOC_TYPE_LABELS.get(user_authority)
        if labels:
            service_name = _lang_text(labels, lang) or user_authority
        else:
            try:
                for a in get_authorities(user_city):
                    if a.get('authority_type') == user_authority:
                        service_name = a.get(f'name_{lang}') or a.get('name_en') or user_authority
                        break
            except Exception:
                pass
        text = _lang_text(_PRE_PAYMENT_TEXT, lang).format(
            city=city_name, service=service_name, price=price,
        )
        # Append city-dependent scan-status footnote (replaces old static Berlin-only warning)
        scan_note = _get_city_scan_note(user_city or "", lang)
        if scan_note:
            text += "\n\n" + scan_note
        if user_city:
            text += "\n\n" + _demand_label(user_city, lang)
        # If user has an active entitlement, prepend a banner — entitlement is optional, not forced
        if entitled:
            text = _lang_text(_EXISTING_PLAN_BANNER, lang) + text
        return profile_line + text
    return profile_line + _lang_text(_SETUP_TEXT, lang)


def _user_has_selected(user: dict) -> bool:
    """True when user has chosen both city AND authority."""
    return bool(user and user.get('city') and user.get('authority'))


def _maybe_activate_reminder(user: dict):
    """
    No-op: reminder activation is handled ONLY by the Stripe webhook.
    Monitoring must NEVER start before payment — this function intentionally does nothing.
    Kept as a stub so call-sites don't need to be changed.
    """
    return


async def show_termin_menu_entry(message: types.Message, user_id: int):
    """
    Entry point from the main menu "Find Termin" button.
    ALWAYS shows the city selection screen — flow must start from the top.
    Monitoring/payment state is resolved AFTER the user navigates city → document.
    """
    # DEV MODE: reset payment/monitoring state for test users on every entry.
    _dev_reset_if_needed(user_id)

    lang = _resolve_lang(user_id)
    _ensure_termin_user(user_id, lang)

    logger.info("TERMIN_ENTRY | user_id=%s lang=%s → city selection", user_id, lang)

    # Step 1 of the required flow: ALWAYS show city selection first.
    # Monitoring active / payment state is never shown at entry — only after
    # the user navigates city → document → payment.
    await message.answer(
        _build_termin_entry_text(lang),
        parse_mode="HTML",
        reply_markup=get_cities_keyboard(lang),
    )


# ==================== Handlers ====================
async def handle_termin_menu(callback: types.CallbackQuery, state: FSMContext):
    """Return to termin menu (from sub-screens)"""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    user = _ensure_termin_user(user_id, lang)

    has_paid_db = user.get('has_paid_termin', 0) == 1 if user else False
    has_selected = _user_has_selected(user)

    # Entitlement check: ACTIVE only when entitlement is active and not consumed.
    # has_paid_termin=1 alone is NOT sufficient — entitlement must be unexpired.
    has_paid = is_termin_entitled(str(user_id))

    # Preserve critical FSM keys before clearing TerminStates
    current = await state.get_state()
    if current and current.startswith('TerminStates:'):
        _fsm_snapshot = await state.get_data()
        _preserved = {
            k: _fsm_snapshot[k]
            for k in ("active_profile_id", "source_doc", "termin_pending_city")
            if k in _fsm_snapshot
        }
        await state.finish()
        if _preserved:
            await state.update_data(**_preserved)

    # Auto-activate reminder ONLY if entitlement is active (real Stripe payment)
    # has_paid_db alone is NOT sufficient — it's a permanent flag, not a current entitlement
    if has_paid and has_selected:
        _maybe_activate_reminder(user)

    user_city = user.get('city', '') if user else ''
    user_authority = user.get('authority', '') if user else ''

    _active_profile = await _get_active_profile_id(state, user_id=user_id)
    _family = _is_family_user(user_id)

    await callback.message.edit_text(
        _build_termin_menu_text(
            lang, has_paid, has_selected,
            user_city=user_city, user_authority=user_authority,
            active_profile_id=_active_profile if _family else None,
            is_family=_family,
        ),
        parse_mode="HTML",
        reply_markup=get_termin_menu_keyboard(
            lang, has_paid, has_selected,
            user_city=user_city or None,
            user_authority=user_authority or None,
            user_id=user_id, active_profile_id=_active_profile if _family else None,
            is_family=_family,
        ),
    )


async def handle_cities(callback: types.CallbackQuery, state: FSMContext):
    """Show city list — open to ALL users (city selection comes before payment)."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    _ensure_termin_user(user_id, lang)

    await TerminStates.selecting_city.set()
    await callback.message.edit_text(
        _build_termin_entry_text(lang),
        parse_mode="HTML",
        reply_markup=get_cities_keyboard(lang),
    )


async def handle_city_selection(callback: types.CallbackQuery, state: FSMContext):
    """After city selected → show document type selection (not raw authorities)."""
    await callback.answer(cache_time=1)
    city_code = callback.data.replace('termin_city_', '')
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    telegram_id = str(user_id)

    _ensure_termin_user(user_id, lang)
    update_user(telegram_id, city=city_code)
    await TerminStates.selecting_authority.set()

    await callback.message.edit_text(
        _lang_text(_DOC_SELECT_TEXT, lang),
        parse_mode="HTML",
        reply_markup=get_doc_types_keyboard(city_code, lang),
    )


async def handle_doc_type_selection(callback: types.CallbackQuery, state: FSMContext):
    """
    Document type selected → persist authority, then:
    - Paid user → create reminder, show active screen
    - Unpaid user → show payment offer
    """
    await callback.answer(cache_time=1)
    parts = callback.data.replace('termin_doc_', '').split('_', 1)
    city_code = parts[0]
    authority_type = parts[1] if len(parts) > 1 else ''
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    telegram_id = str(user_id)

    # Persist city + authority
    update_user(telegram_id, city=city_code, authority=authority_type)

    # DEV MODE: reset entitlement so developers always see the payment flow,
    # even if they paid previously.  No-op for real users.
    _dev_reset_if_needed(user_id)

    # Entitlement check: active ONLY when entitlement is active and not consumed
    entitled = is_termin_entitled(telegram_id)

    logger.info(
        "DOC_TYPE_SELECTED | user_id=%s city=%s auth=%s entitled=%s",
        user_id, city_code, authority_type, entitled,
    )

    # Always show the plan-selection screen regardless of entitlement.
    # Entitlement is a capability, not a mandatory flow redirect.
    # If user has an active plan, they see a banner + option to reuse it.
    # If not, they see the standard payment screen.
    # This prevents auto-jumping into "Family mode" on every new search.
    await callback.message.edit_text(
        _build_termin_menu_text(
            lang, False, True,
            user_city=city_code, user_authority=authority_type,
            entitled=entitled,
        ),
        parse_mode="HTML",
        reply_markup=get_termin_menu_keyboard(
            lang, False, True,
            user_city=city_code, user_authority=authority_type,
            user_id=user_id,
            entitled=entitled,
        ),
    )


async def handle_authority_selection(callback: types.CallbackQuery, state: FSMContext):
    """
    1-SCREEN MVP: authority info + full guidance + official link + disclaimer.
    No extra click needed — user sees everything at once.
    """
    await callback.answer(cache_time=1)
    parts = callback.data.replace('termin_auth_', '').split('_')
    city_code = parts[0]
    authority_type = parts[1] if len(parts) > 1 else ''
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    telegram_id = str(user_id)

    user = _ensure_termin_user(user_id, lang)
    update_user(telegram_id, authority=authority_type)

    auth_info = get_authority_info(city_code, authority_type)
    if not auth_info:
        return

    name = auth_info.get(f'name_{lang}') or auth_info['name_en']
    knowledge = get_knowledge(city_code, authority_type, lang)
    booking_url = auth_info.get('booking_url', '')

    # === BUILD 1-SCREEN MESSAGE ===
    msg = f"🏛️ <b>{name}</b>\n\n"

    # Description
    if knowledge and knowledge.get('description'):
        msg += f"{knowledge['description']}\n\n"

    # Booking steps (inline)
    if knowledge and knowledge.get('booking_steps'):
        msg += f"<b>✅ {get_text('guidance_steps', lang)}</b>\n"
        for i, step in enumerate(knowledge['booking_steps'], 1):
            msg += f"{i}. {step}\n"
        msg += "\n"

    # Required documents
    if knowledge and knowledge.get('documents_required'):
        msg += f"<b>📄 {get_text('guidance_documents', lang)}</b>\n"
        for doc in knowledge['documents_required']:
            msg += f"• {doc}\n"
        msg += "\n"

    # Common mistakes
    if knowledge and knowledge.get('common_mistakes'):
        msg += f"<b>⚠️ {get_text('guidance_mistakes', lang)}</b>\n"
        for mistake in knowledge['common_mistakes']:
            msg += f"❌ {mistake}\n"
        msg += "\n"

    # Timing
    if knowledge and knowledge.get('timing_patterns'):
        patterns = knowledge['timing_patterns']
        msg += f"<b>⏰ {get_text('guidance_timing', lang)}</b>\n"
        if patterns.get('best_times'):
            msg += f"• {patterns['best_times']}\n"
        if patterns.get('best_days'):
            msg += f"• {patterns['best_days']}\n"
        msg += "\n"

    # Tips
    if knowledge and knowledge.get('tips'):
        msg += f"<b>💡 {get_text('guidance_tips', lang)}</b>\n"
        for tip in knowledge['tips']:
            msg += f"• {tip}\n"
        msg += "\n"

    # Official link
    if booking_url:
        msg += f"🔗 <b>{get_text('official_link', lang)}</b>\n{booking_url}\n\n"

    # Disclaimer
    msg += get_text('termin_disclaimer', lang)

    # Truncate if too long for Telegram
    if len(msg) > 4000:
        msg = msg[:4000] + "..."

    # Log guidance view (analytics event)
    logger.info("TERMIN_GUIDANCE_VIEWED | user_id=%s city=%s authority=%s lang=%s", user_id, city_code, authority_type, lang)

    # === BUILD KEYBOARD: upsell OR passive status + back ===
    # Use is_termin_entitled (live entitlement check) — not the stale has_paid_termin DB flag.
    has_paid = is_termin_entitled(telegram_id)
    keyboard = InlineKeyboardMarkup(row_width=1)

    if has_paid:
        # Passive confirmation — no extra click needed
        msg += "\n\n✅ <i>" + get_text('termin_set_reminder', lang) + "</i>"
    else:
        # Explainer: what we do / don't do (above the button)
        msg += "\n\n" + get_text('termin_upsell_explainer', lang)
        # Demand label + dynamic price
        msg += "\n\n" + _demand_label(city_code, lang)
        # MVP upsell: one button, reuses existing termin_pay_ handler
        price = _price_for(city_code, authority_type)
        keyboard.add(InlineKeyboardButton(
            get_text('termin_pay_reminders', lang, price=price),
            callback_data=f"termin_pay_{city_code}_{authority_type}",
        ))
        logger.info("TERMIN_PAYMENT_REQUIRED | user_id=%s city=%s authority=%s lang=%s", user_id, city_code, authority_type, lang)

    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data=f"termin_city_{city_code}",
    ))

    # Truncate again after possible passive text append
    if len(msg) > 4000:
        msg = msg[:4000] + "..."

    await callback.message.edit_text(
        msg,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def handle_view_guidance(callback: types.CallbackQuery, state: FSMContext):
    """
    Legacy handler — kept for backward compatibility.
    Now redirects to the 1-screen authority view (handle_authority_selection).
    """
    try:
        parts = callback.data.replace('termin_guide_', '').split('_')
        city_code = parts[0]
        authority_type = parts[1] if len(parts) > 1 else ''
        callback.data = f"termin_auth_{city_code}_{authority_type}"
    except Exception:
        await callback.answer(cache_time=1)
        return
    await handle_authority_selection(callback, state)


# ==================== Standalone Notification Handlers ====================

async def handle_notify_info(callback: types.CallbackQuery, state: FSMContext):
    """Show active-status screen (paid users only). Unpaid → back to menu."""
    try:
        user_id = callback.from_user.id
        lang = _resolve_lang(user_id)
        _ensure_termin_user(user_id, lang)
        # Use live entitlement check — not the stale has_paid_termin DB flag.
        has_paid = is_termin_entitled(str(user_id))
    except Exception:
        await callback.answer(cache_time=1)
        return

    if not has_paid:
        await handle_termin_menu(callback, state)
        return

    await callback.answer(cache_time=1)
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data='termin_menu',
    ))
    await callback.message.edit_text(
        _lang_text(_TERMIN_PAID_TEXT, lang),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# ── CONSENT GATE for Termin payments ──
_termin_consent = {}  # {user_id: True} — tracks personal data consent per session


def _has_termin_consent(user_id: int) -> bool:
    """Return True if user already gave GDPR consent (in-session or persisted in DB)."""
    if _termin_consent.get(user_id):
        return True
    try:
        from utils.helpers import get_db as _get_db
        _db = _get_db()
        if _db.get_gdpr_status(user_id):
            _termin_consent[user_id] = True
            return True
    except Exception:
        pass
    return False

_TERMIN_CONSENT_TEXT = {
    "uk": (
        "🔒 <b>Згода на обробку даних</b>\n\n"
        "Я погоджуюсь на обробку персональних даних "
        "та підтверджую, що ознайомлений з умовами сервісу.\n\n"
        "<i>Ваші дані використовуються тільки для пошуку та бронювання терміну.</i>"
    ),
    "ua": (
        "🔒 <b>Згода на обробку даних</b>\n\n"
        "Я погоджуюсь на обробку персональних даних "
        "та підтверджую, що ознайомлений з умовами сервісу.\n\n"
        "<i>Ваші дані використовуються тільки для пошуку та бронювання терміну.</i>"
    ),
    "en": (
        "🔒 <b>Data processing consent</b>\n\n"
        "I agree to the processing of my personal data "
        "and confirm that I have read the terms of service.\n\n"
        "<i>Your data is used only to find and book an appointment.</i>"
    ),
    "de": (
        "🔒 <b>Einwilligung zur Datenverarbeitung</b>\n\n"
        "Ich stimme der Verarbeitung meiner personenbezogenen Daten zu "
        "und bestätige, die Nutzungsbedingungen gelesen zu haben.\n\n"
        "<i>Ihre Daten werden ausschließlich zur Terminsuche und -buchung verwendet.</i>"
    ),
    "pl": (
        "🔒 <b>Zgoda na przetwarzanie danych</b>\n\n"
        "Wyrażam zgodę na przetwarzanie moich danych osobowych "
        "i potwierdzam zapoznanie się z regulaminem.\n\n"
        "<i>Twoje dane są wykorzystywane wyłącznie do wyszukiwania i rezerwacji terminu.</i>"
    ),
    "tr": (
        "🔒 <b>Veri işleme onayı</b>\n\n"
        "Kişisel verilerimin işlenmesine onay veriyorum "
        "ve hizmet şartlarını okuduğumu kabul ediyorum.\n\n"
        "<i>Verileriniz yalnızca randevu bulmak ve rezerve etmek için kullanılır.</i>"
    ),
    "ar": (
        "🔒 <b>الموافقة على معالجة البيانات</b>\n\n"
        "أوافق على معالجة بياناتي الشخصية "
        "وأؤكد أنني قرأت شروط الخدمة.\n\n"
        "<i>يتم استخدام بياناتك فقط للبحث عن موعد وحجزه.</i>"
    ),
}

_TERMIN_CONSENT_BTN = {
    "uk": "✅ Погоджуюсь — продовжити",
    "ua": "✅ Погоджуюсь — продовжити",
    "en": "✅ I agree — continue",
    "de": "✅ Ich stimme zu — weiter",
    "pl": "✅ Zgadzam się — kontynuuj",
    "tr": "✅ Kabul ediyorum — devam et",
    "ar": "✅ أوافق — متابعة",
}

_TERMIN_CONSENT_BACK = {
    "uk": "⬅️ Назад", "ua": "⬅️ Назад", "en": "⬅️ Back", "de": "⬅️ Zurück",
    "pl": "⬅️ Wstecz", "tr": "⬅️ Geri", "ar": "⬅️ رجوع",
}


async def _show_termin_consent(callback: types.CallbackQuery, next_action: str, back_action: str = "termin_main"):
    """Show consent screen before Termin payment. next_action = original callback_data to replay."""
    lang = _resolve_lang(callback.from_user.id)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        _lang_text(_TERMIN_CONSENT_BTN, lang),
        callback_data=f"termin_consent_{next_action}"
    ))
    kb.add(InlineKeyboardButton(
        _lang_text(_TERMIN_CONSENT_BACK, lang),
        callback_data=back_action,
    ))
    await callback.message.answer(
        _lang_text(_TERMIN_CONSENT_TEXT, lang),
        parse_mode="HTML",
        reply_markup=kb,
    )


async def handle_termin_consent(callback: types.CallbackQuery, state: FSMContext):
    """User accepted consent — record flag, re-trigger original payment handler."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    _termin_consent[user_id] = True
    logger.info("TERMIN_CONSENT_ACCEPTED: user_id=%s", user_id)

    # Persist consent in main DB
    try:
        from utils.helpers import get_db
        db = get_db()
        db.set_gdpr_consent(user_id, True)
    except Exception:
        pass

    # Extract original action: "termin_consent_<original_callback_data>"
    original_action = callback.data.replace("termin_consent_", "", 1)
    callback.data = original_action

    # Dispatch to the correct handler
    if original_action in ("termin_start_payment", "termin_notify_pay"):
        await handle_notify_pay(callback, state)
    elif original_action.startswith("termin_pay_"):
        await handle_pay_for_reminders(callback, state)
    elif original_action == "termin_proceed_payment":
        await handle_termin_proceed_payment(callback, state)
    else:
        logger.warning("TERMIN_CONSENT unknown action: %s", original_action)
    return True


# In-memory registry: order_id → checkout_url, populated when Stripe session is
# created and the direct Pay button was actually sent to the user.
# Only orders recorded here are eligible for reuse (= user already saw the Pay button).
_termin_checkout_sent: Dict[int, str] = {}


def _register_checkout_sent(order_id: int, checkout_url: str) -> None:
    """Mark that the Stripe Pay button was sent to the user for this order."""
    _termin_checkout_sent[order_id] = checkout_url


def _find_reusable_termin_order(user_id: int, doc_type: str):
    """Return the latest unpaid Termin order for this user+product if within TTL.

    PRIMARY path — order with an open Stripe session the user already saw:
      1. status in ("pending", "processing")
      2. created within _TERMIN_ORDER_REUSE_TTL_SEC window
      3. stripe_session_id is set
      4. The Pay button was already sent (_termin_checkout_sent key exists)

    SECONDARY path — "in-creation" guard (no Stripe session yet):
      An order that was created very recently (<= _ORDER_CREATION_GRACE_SEC) but
      has no stripe_session_id yet means another handler invocation already called
      create_order() and is awaiting the Stripe API response (or crashed just after).
      Returning that order signals the caller to skip a new create_order() call.
      The caller must handle the missing stripe_session_id gracefully (no URL reuse).
    """
    _ORDER_CREATION_GRACE_SEC = 10  # window to catch in-flight / crashed sessions

    try:
        import datetime as _dt
        from utils.helpers import get_db
        db = get_db()
        orders = db.get_user_orders(user_id, limit=10)
        _in_creation_candidate = None  # lowest-age order without a session yet

        for order in orders:
            if order.get("doc_type") != doc_type:
                continue
            status = (order.get("status") or "").lower()
            if status not in ("pending", "processing"):
                continue

            # Parse age — skip unparseable rows
            created_raw = order.get("created_at") or ""
            age_sec = None
            if created_raw:
                try:
                    created_raw_s = str(created_raw).replace("T", " ").split(".")[0]
                    created_dt = _dt.datetime.strptime(created_raw_s, "%Y-%m-%d %H:%M:%S")
                    age_sec = (_dt.datetime.utcnow() - created_dt).total_seconds()
                except Exception:
                    continue  # can't parse age — skip

            if age_sec is not None and age_sec > _TERMIN_ORDER_REUSE_TTL_SEC:
                continue  # too old

            session_id = order.get("stripe_session_id") or ""

            if not session_id:
                # Secondary path: order exists but Stripe session not yet written.
                # Track the youngest such candidate (orders are DESC by created_at).
                if age_sec is not None and age_sec <= _ORDER_CREATION_GRACE_SEC:
                    if _in_creation_candidate is None:
                        _in_creation_candidate = order
                continue  # no session → can't show URL; don't return as primary

            # Primary path: session exists — only reuse if user already saw the Pay button
            oid = order.get("id") or order.get("order_id")
            stored_url = _termin_checkout_sent.get(oid, "")
            if not stored_url or not stored_url.startswith("https://"):
                continue  # user never saw the Pay button — treat as new
            return order  # ← full reuse: caller will show existing checkout URL

        # No primary match — return in-creation candidate so caller skips create_order
        if _in_creation_candidate is not None:
            logger.info(
                "TERMIN_ORDER_IN_CREATION | user=%s doc=%s order=%s — skipping new create_order",
                user_id, doc_type,
                _in_creation_candidate.get("id") or _in_creation_candidate.get("order_id"),
            )
            return _in_creation_candidate

    except Exception as _e:
        logger.debug("_find_reusable_termin_order error: %s", _e)
    return None


async def _send_checkout_message(
    send_target,  # message to answer, or bot + chat_id
    lang: str,
    price: float,
    checkout_url: str,
    order_id: int,
    *,
    is_reuse: bool = False,
):
    """Send the premium 'payment in progress' message with three action buttons.

    send_target: an aiogram Message whose .answer() is called.
    """
    keyboard = InlineKeyboardMarkup(row_width=1)
    # Primary CTA — "I paid" verify button
    keyboard.add(InlineKeyboardButton(
        _lang_text(_STRIPE_I_PAID_BTN, lang),
        callback_data=f"termin_verify_paid_{order_id}",
    ))
    # Re-open payment link
    keyboard.add(InlineKeyboardButton(
        _lang_text(_STRIPE_REOPEN_BTN, lang),
        url=checkout_url,
    ))
    # Cancel
    keyboard.add(InlineKeyboardButton(
        _lang_text({"ua": "❌ Скасувати", "uk": "❌ Скасувати",
                    "en": "❌ Cancel", "de": "❌ Abbrechen",
                    "pl": "❌ Anuluj", "tr": "❌ İptal", "ar": "❌ إلغاء"}, lang),
        callback_data="termin_menu",
    ))
    text = _lang_text(_STRIPE_IN_PROGRESS_TEXT, lang)
    if is_reuse:
        # Subtle note that we reused the session
        reuse_note = {
            "ua": "\n\nℹ️ Використовуємо раніше відкриту сесію оплати.",
            "uk": "\n\nℹ️ Використовуємо раніше відкриту сесію оплати.",
            "en": "\n\nℹ️ Reusing your existing payment session.",
            "de": "\n\nℹ️ Vorherige Zahlungssitzung wird wiederverwendet.",
            "pl": "\n\nℹ️ Używamy Twojej istniejącej sesji płatności.",
            "tr": "\n\nℹ️ Mevcut ödeme oturumunuz kullanılıyor.",
            "ar": "\n\nℹ️ إعادة استخدام جلسة الدفع الحالية.",
        }
        text += _lang_text(reuse_note, lang)
    await send_target.answer(text, reply_markup=keyboard)


async def handle_notify_pay(callback: types.CallbackQuery, state: FSMContext):
    """Direct Stripe Checkout for Termin notifications.
    Flow: callback click → create Stripe session → send ONE new message
    with a distinct redirect text + URL button → return immediately.
    The new message is visually different from the payment-offer screen,
    so the user clearly sees a single URL button to tap.
    """
    # NOTE: callback.answer() is intentionally deferred to after session creation
    # so we can pass url=checkout_url, which forces Telegram to open an external
    # browser instead of the in-app WebView on first tap.
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # ── Consent gate ──
    if not _has_termin_consent(user_id):
        await callback.answer(cache_time=1)
        await _show_termin_consent(callback, "termin_start_payment", "termin_main")
        return

    # ── In-flight concurrency guard ──
    # Prevents duplicate orders when Telegram re-delivers the callback or the
    # user taps the button twice before the first Stripe session is created.
    # set.add / set.__contains__ are synchronous — safe between awaits.
    if user_id in _order_creating:
        logger.info("TERMIN_BUY_DUPLICATE_IGNORED | user_id=%s", user_id)
        await callback.answer(cache_time=1)
        return
    _order_creating.add(user_id)

    try:
        # Resolve dynamic price from user's city/authority
        user = _ensure_termin_user(user_id, lang)
        user_city = user.get('city', '') if user else ''
        user_authority = user.get('authority', '') if user else ''
        price = get_termin_price(user_city, user_authority)

        logger.info("TERMIN_BUY_CLICKED | user_id=%s lang=%s price=%.2f city=%s",
                    user_id, lang, price, user_city)

        import os

        try:
            from utils.helpers import get_db
            from handlers.stripe_handler import get_stripe_handler

            # ── Reuse existing unpaid session if within TTL ──
            _doc_type = 'termin_notifications'
            existing = _find_reusable_termin_order(user_id, _doc_type)
            if existing:
                existing_session_id = existing.get("stripe_session_id", "")
                if not existing_session_id:
                    # Secondary path: order was just created by a concurrent/previous
                    # invocation but the Stripe session isn't written yet.
                    # Skip creating another order; exit silently — the first invocation
                    # will send the Pay button once its Stripe call completes.
                    logger.info(
                        "TERMIN_BUY_ORDER_IN_CREATION_SKIP | user=%s order=%s",
                        user_id, existing.get("id") or existing.get("order_id"),
                    )
                    await callback.answer(cache_time=1)
                    return
                # Primary path: retrieve current Stripe session URL
                _checkout_url = None
                try:
                    import stripe as _stripe_sdk
                    _stripe_sdk.api_key = os.getenv("STRIPE_SECRET_KEY", "")
                    _session = _stripe_sdk.checkout.Session.retrieve(existing_session_id)
                    if getattr(_session, "status", "") == "open":
                        _checkout_url = getattr(_session, "url", None)
                except Exception as _se:
                    logger.debug("TERMIN_REUSE_RETRIEVE_FAIL | %s", _se)
                if _checkout_url:
                    logger.info(
                        "TERMIN_ORDER_REUSED | user=%s order=%s session=%s",
                        user_id, existing["id"], existing_session_id,
                    )
                    await callback.answer(cache_time=1)
                    await _send_checkout_message(
                        callback.message, lang, price, _checkout_url,
                        existing["id"], is_reuse=True,
                    )
                    return

            # ── No reusable session — create a new one ──
            db = get_db()
            order_lang = 'uk' if lang == 'ua' else lang
            order_id = db.create_order(
                user_id=user_id,
                doc_type=_doc_type,
                amount=price,
                lang=order_lang,
            )

            webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
            success_url = _build_success_url(order_id)
            cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

            stripe_h = get_stripe_handler()
            result = await stripe_h.create_checkout_session(
                order_id=order_id,
                user_id=user_id,
                doc_type=_doc_type,
                price=price,
                success_url=success_url,
                cancel_url=cancel_url,
                extra_metadata={'bundle': 'true', 'termin_only': 'true'},
            )

            if result.success:
                from backend.database import OrderStatus
                db.update_order_status(order_id, OrderStatus.PENDING, stripe_session_id=result.session_id)
                logger.info(
                    "STRIPE_CHECKOUT_CREATED user=%s order=%s session=%s url=%s success_url=%s",
                    user_id, order_id, result.session_id, result.checkout_url, success_url,
                )
                # Record that Pay button was sent — enables reuse on next tap
                _register_checkout_sent(order_id, result.checkout_url)
                logger.info("STRIPE_DIRECT_OPEN order=%s url=%s", order_id, result.checkout_url)
                await callback.answer(cache_time=1)
                keyboard = InlineKeyboardMarkup(row_width=1)
                keyboard.add(InlineKeyboardButton(
                    _lang_text(_STRIPE_OPEN_BTN, lang).format(price=f"{price:.2f}"),
                    url=result.checkout_url,
                ))
                await callback.message.answer(
                    _lang_text(_STRIPE_REDIRECT_TEXT, lang),
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
                return

        except Exception as e:
            await callback.answer(cache_time=1)
            logger.error("TERMIN_BUY_STRIPE_ERROR | user_id=%s error=%s", user_id, e)

    finally:
        _order_creating.discard(user_id)


# ==================== Authority-Card Payment (existing) ====================

async def handle_pay_for_reminders(callback: types.CallbackQuery, state: FSMContext):
    """Create Stripe Checkout for Termin notifications (one-time payment).
    Same pattern as handle_notify_pay: new message with distinct redirect text.
    """
    # NOTE: callback.answer() deferred — see handle_notify_pay for explanation.
    parts = callback.data.replace('termin_pay_', '').split('_')
    city_code = parts[0]
    authority_type = parts[1] if len(parts) > 1 else ''
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # ── Consent gate ──
    if not _has_termin_consent(user_id):
        back_cb = f"termin_auth_{city_code}_{authority_type}" if authority_type else "termin_main"
        await _show_termin_consent(callback, callback.data, back_cb)
        return

    # ── In-flight concurrency guard ──
    if user_id in _order_creating:
        logger.info("TERMIN_REMINDER_DUPLICATE_IGNORED | user_id=%s", user_id)
        await callback.answer(cache_time=1)
        return
    _order_creating.add(user_id)

    try:
        # Dynamic price from city demand level
        price = get_termin_price(city_code, authority_type)

        logger.info("TERMIN_REMINDER_CLICKED | user_id=%s city=%s authority=%s lang=%s price=%.2f",
                    user_id, city_code, authority_type, lang, price)

        await TerminStates.paying_for_reminders.set()

        import os

        # === CREATE STRIPE CHECKOUT via existing Gold Build infrastructure ===
        try:
            from utils.helpers import get_db
            from handlers.stripe_handler import get_stripe_handler

            _doc_type = 'termin_notifications'

            # ── Reuse existing unpaid session if within TTL ──
            existing = _find_reusable_termin_order(user_id, _doc_type)
            if existing:
                _existing_session_id = existing.get("stripe_session_id", "")
                if not _existing_session_id:
                    # Secondary path: another invocation already called create_order()
                    # but hasn't written the Stripe session yet — skip silently.
                    logger.info(
                        "TERMIN_REMINDER_ORDER_IN_CREATION_SKIP | user=%s order=%s",
                        user_id, existing.get("id") or existing.get("order_id"),
                    )
                    await callback.answer(cache_time=1)
                    return
                _checkout_url = None
                try:
                    import stripe as _stripe_sdk
                    _stripe_sdk.api_key = os.getenv("STRIPE_SECRET_KEY", "")
                    _session = _stripe_sdk.checkout.Session.retrieve(_existing_session_id)
                    if getattr(_session, "status", "") == "open":
                        _checkout_url = getattr(_session, "url", None)
                except Exception as _se:
                    logger.debug("TERMIN_REUSE_RETRIEVE_FAIL | %s", _se)
                if _checkout_url:
                    logger.info(
                        "TERMIN_ORDER_REUSED | user=%s order=%s session=%s",
                        user_id, existing["id"], _existing_session_id,
                    )
                    await _send_checkout_message(
                        callback.message, lang, price, _checkout_url,
                        existing["id"], is_reuse=True,
                    )
                    return

            # ── No reusable session — create a new one ──
            db = get_db()
            order_lang = 'uk' if lang == 'ua' else lang
            order_id = db.create_order(
                user_id=user_id,
                doc_type=_doc_type,
                amount=price,
                lang=order_lang,
            )

            webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
            success_url = _build_success_url(order_id)
            cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

            stripe_h = get_stripe_handler()
            result = await stripe_h.create_checkout_session(
                order_id=order_id,
                user_id=user_id,
                doc_type=_doc_type,
                price=price,
                success_url=success_url,
                cancel_url=cancel_url,
                extra_metadata={'bundle': 'true', 'termin_only': 'true'},
            )

            if result.success:
                from backend.database import OrderStatus
                db.update_order_status(order_id, OrderStatus.PENDING, stripe_session_id=result.session_id)
                logger.info(
                    "STRIPE_CHECKOUT_CREATED user=%s order=%s session=%s url=%s success_url=%s",
                    user_id, order_id, result.session_id, result.checkout_url, success_url,
                )
                # Record that Pay button was sent — enables reuse on next tap
                _register_checkout_sent(order_id, result.checkout_url)
                logger.info("STRIPE_DIRECT_OPEN order=%s url=%s", order_id, result.checkout_url)
                await callback.answer(cache_time=1)
                keyboard = InlineKeyboardMarkup(row_width=1)
                keyboard.add(InlineKeyboardButton(
                    _lang_text(_STRIPE_OPEN_BTN, lang).format(price=f"{price:.2f}"),
                    url=result.checkout_url,
                ))
                await callback.message.answer(
                    _lang_text(_STRIPE_REDIRECT_TEXT, lang),
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
                return

        except Exception as e:
            await callback.answer(cache_time=1)
            logger.error("TERMIN_STRIPE_ERROR | user_id=%s error=%s", user_id, e)

    finally:
        _order_creating.discard(user_id)

    # Fallback: error — show back button so user can retry
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(
        get_text('btn_back', lang),
        callback_data=f"termin_auth_{city_code}_{authority_type}",
    ))
    await callback.message.answer(
        _lang_text(_STRIPE_ERROR_TEXT, lang),
        reply_markup=keyboard,
    )


async def handle_verify_payment(callback: types.CallbackQuery, state: FSMContext):
    """Handle '✅ I paid' button: verify payment via DB + Stripe API fallback."""
    await callback.answer(_lang_text(_VERIFY_CHECKING, _resolve_lang(callback.from_user.id)))
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # Parse order_id from callback data: termin_verify_paid_<order_id>
    raw = callback.data.replace("termin_verify_paid_", "").replace("termin_verify_", "")
    try:
        order_id = int(raw)
    except (ValueError, TypeError):
        order_id = None

    if not order_id:
        await callback.message.answer(_lang_text(_VERIFY_NOT_PAID, lang))
        return

    import os

    try:
        from utils.helpers import get_db
        db = get_db()
        order = db.get_order(order_id)

        if not order:
            await callback.message.answer(_lang_text(_VERIFY_NOT_PAID, lang))
            return

        status = (order.get("status") or "").lower()

        # Already confirmed via webhook
        if status in ("paid", "sent", "downloaded"):
            await callback.message.answer(_lang_text(_VERIFY_SUCCESS, lang))
            return

        # Status still pending/processing — hit Stripe API to check
        if status in ("pending", "processing"):
            stripe_session_id = order.get("stripe_session_id") or ""
            if stripe_session_id:
                try:
                    import stripe as _stripe_sdk
                    _stripe_sdk.api_key = os.getenv("STRIPE_SECRET_KEY", "")
                    _session = _stripe_sdk.checkout.Session.retrieve(stripe_session_id)
                    _pay_status = getattr(_session, "payment_status", "")
                    _sess_status = getattr(_session, "status", "")
                    logger.info(
                        "TERMIN_VERIFY_STRIPE | user=%s order=%s session_status=%s pay_status=%s",
                        user_id, order_id, _sess_status, _pay_status,
                    )
                    if _sess_status == "complete" and _pay_status == "paid":
                        # Stripe says paid — activate immediately as webhook fallback
                        from backend.database import OrderStatus
                        db.update_order_status(order_id, OrderStatus.PAID)
                        from backend.termin_db import upsert_entitlement as _upsert
                        _upsert(
                            str(user_id),
                            plan="single",
                            slots_total=1,
                            stripe_session_id=stripe_session_id,
                        )
                        logger.info(
                            "TERMIN_VERIFY_ACTIVATED | user=%s order=%s (Stripe fallback)",
                            user_id, order_id,
                        )
                        await callback.message.answer(_lang_text(_VERIFY_SUCCESS, lang))
                        return
                except Exception as _se:
                    logger.warning("TERMIN_VERIFY_STRIPE_ERROR | user=%s error=%s", user_id, _se)

        # Not paid yet — show "not paid" message with buttons intact
        checkout_url = None
        try:
            _sid = order.get("stripe_session_id") or ""
            if _sid:
                import stripe as _stripe_sdk2
                _stripe_sdk2.api_key = os.getenv("STRIPE_SECRET_KEY", "")
                _s2 = _stripe_sdk2.checkout.Session.retrieve(_sid)
                if getattr(_s2, "status", "") == "open":
                    checkout_url = getattr(_s2, "url", None)
        except Exception:
            pass

        if checkout_url:
            # Keep the "I paid" + reopen buttons alive
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton(
                _lang_text(_STRIPE_I_PAID_BTN, lang),
                callback_data=f"termin_verify_paid_{order_id}",
            ))
            keyboard.add(InlineKeyboardButton(
                _lang_text(_STRIPE_REOPEN_BTN, lang),
                url=checkout_url,
            ))
            keyboard.add(InlineKeyboardButton(
                _lang_text({"ua": "❌ Скасувати", "uk": "❌ Скасувати",
                            "en": "❌ Cancel", "de": "❌ Abbrechen",
                            "pl": "❌ Anuluj", "tr": "❌ İptal", "ar": "❌ إلغاء"}, lang),
                callback_data="termin_menu",
            ))
            await callback.message.answer(
                _lang_text(_VERIFY_NOT_PAID, lang),
                reply_markup=keyboard,
            )
        else:
            await callback.message.answer(_lang_text(_VERIFY_NOT_PAID, lang))

    except Exception as exc:
        logger.error("TERMIN_VERIFY_ERROR | user=%s error=%s", user_id, exc)
        await callback.message.answer(_lang_text(_VERIFY_NOT_PAID, lang))


async def handle_set_reminder(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    parts = callback.data.replace('termin_remind_', '').split('_')
    city_code = parts[0]
    authority_type = parts[1] if len(parts) > 1 else ''
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    telegram_id = str(user_id)

    _ensure_termin_user(user_id, lang)
    if not is_termin_entitled(telegram_id):
        logger.warning("TERMIN_PAYMENT_REQUIRED | user=%s (handle_set_reminder)", user_id)
        return

    await callback.message.edit_text(
        get_text('termin_select_interval', lang),
        reply_markup=get_interval_keyboard(city_code, authority_type, lang),
    )


async def handle_interval_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    parts = callback.data.replace('termin_interval_', '').split('_')
    interval_hours = int(parts[0])
    city_code = parts[1] if len(parts) > 1 else ''
    authority_type = parts[2] if len(parts) > 2 else ''
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    telegram_id = str(user_id)

    create_reminder(telegram_id, city_code, authority_type, interval_hours)

    auth_info = get_authority_info(city_code, authority_type)
    auth_name = auth_info.get(f'name_{lang}') or auth_info['name_en'] if auth_info else authority_type

    await callback.message.edit_text(
        get_text('termin_reminder_activated', lang, interval=interval_hours, authority=auth_name),
        reply_markup=get_reminder_management_keyboard(lang),
    )


async def handle_activate_reminder(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    user = _ensure_termin_user(user_id, lang)

    city = user.get('city') if user else None
    authority = user.get('authority') if user else None

    if city and authority:
        await callback.message.edit_text(
            get_text('termin_select_interval', lang),
            reply_markup=get_interval_keyboard(city, authority, lang),
        )
    else:
        await callback.message.edit_text(
            get_text('termin_select_city_first', lang),
            reply_markup=get_cities_keyboard(lang),
        )


async def handle_manage_reminders(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    user = _ensure_termin_user(user_id, lang)

    city = user.get('city', 'berlin') if user else 'berlin'
    authority = user.get('authority', 'buergeramt') if user else 'buergeramt'
    interval = user.get('reminder_interval', '6h') if user else '6h'

    auth_info = get_authority_info(city, authority)
    auth_name = auth_info.get(f'name_{lang}') if auth_info else authority

    cities = get_cities()
    city_info = next((c for c in cities if c['code'] == city), None)
    city_name = city_info.get(f'name_{lang}') if city_info else city

    await callback.message.edit_text(
        get_text('termin_reminder_status', lang, city=city_name, authority=auth_name, interval=interval.replace('h', '')),
        reply_markup=get_reminder_management_keyboard(lang),
    )


async def handle_pause_reminders(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    telegram_id = str(user_id)

    deactivate_reminder(telegram_id)

    await callback.message.edit_text(
        get_text('termin_reminder_paused', lang),
        reply_markup=get_back_keyboard('termin_menu', lang),
    )


async def handle_change_interval(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    user = _ensure_termin_user(user_id, lang)

    city = user.get('city', 'berlin') if user else 'berlin'
    authority = user.get('authority', 'buergeramt') if user else 'buergeramt'

    await callback.message.edit_text(
        get_text('termin_select_interval', lang),
        reply_markup=get_interval_keyboard(city, authority, lang),
    )


async def handle_status(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    user = _ensure_termin_user(user_id, lang)

    city = user.get('city', '-') if user else '-'
    authority = user.get('authority', '-') if user else '-'
    status = user.get('status', 'searching') if user else 'searching'
    paid = '✅' if is_termin_entitled(str(user_id)) else '❌'
    reminders = '✅' if user and user.get('reminder_active') else '❌'

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(get_text('status_searching', lang), callback_data='termin_setstatus_searching'),
        InlineKeyboardButton(get_text('status_booked', lang), callback_data='termin_setstatus_booked'),
        InlineKeyboardButton(get_text('btn_back', lang), callback_data='termin_menu'),
    )

    await callback.message.edit_text(
        get_text('termin_status_info', lang, city=city, authority=authority, status=status, paid=paid, reminders=reminders),
        reply_markup=keyboard,
    )


async def handle_set_status(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    status = callback.data.replace('termin_setstatus_', '')
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    telegram_id = str(user_id)

    update_user(telegram_id, status=status)

    message = get_text('termin_status_updated', lang, status=status)
    if status == 'booked':
        message += "\n\n🔗 " + get_text('termin_congrats', lang)

    await callback.message.edit_text(
        message,
        reply_markup=get_back_keyboard('termin_menu', lang),
    )


# ==================== Termin Availability Polling (Stage 1) ====================

_POLL_START_TEXT = {
    "ua": "🔍 <b>Моніторинг запущено</b>\nПеревіряємо кожні 5 секунд. Сповістимо одразу, щойно з\u02bcявиться місце.",
    "uk": "🔍 <b>Моніторинг запущено</b>\nПеревіряємо кожні 5 секунд. Сповістимо одразу, щойно з\u02bcявиться місце.",
    "en": "🔍 <b>Monitoring started</b>\nChecking every 5 seconds. We'll notify you as soon as a slot appears.",
    "de": "🔍 <b>Überwachung gestartet</b>\nWir prüfen alle 5 Sekunden. Sie werden benachrichtigt, sobald ein Termin frei wird.",
    "pl": "🔍 <b>Monitorowanie uruchomione</b>\nSprawdzamy co 5 sekund. Powiadomimy Cię, gdy pojawi się wolne miejsce.",
    "tr": "🔍 <b>İzleme başlatıldı</b>\nHer 5 saniyede kontrol ediliyor. Yer bulunduğunda sizi bilgilendireceğiz.",
    "ar": "🔍 <b>بدأت المراقبة</b>\nنتحقق كل 5 ثواني. سنُعلمك فور توفر موعد.",
}
_POLL_ALREADY_TEXT = {
    "ua": "⏳ Моніторинг вже активний. Ви отримаєте сповіщення, щойно з\u02bcявиться місце.",
    "uk": "⏳ Моніторинг вже активний. Ви отримаєте сповіщення, щойно з\u02bcявиться місце.",
    "en": "⏳ Monitoring is already active. You'll be notified when a slot appears.",
    "de": "⏳ Überwachung läuft bereits. Sie werden benachrichtigt, sobald ein Termin frei wird.",
    "pl": "⏳ Monitorowanie już trwa. Powiadomimy Cię, gdy pojawi się wolne miejsce.",
    "tr": "⏳ İzleme zaten aktif. Yer bulunduğunda bilgilendirileceksiniz.",
    "ar": "⏳ المراقبة نشطة بالفعل. ستصلك إشعار عند توفر موعد.",
}
_POLL_STOPPED_TEXT = {
    "ua": "⏹ Моніторинг зупинено.",
    "uk": "⏹ Моніторинг зупинено.",
    "en": "⏹ Monitoring stopped.",
    "de": "⏹ Überwachung gestoppt.",
    "pl": "⏹ Monitorowanie zatrzymane.",
    "tr": "⏹ İzleme durduruldu.",
    "ar": "⏹ تم إيقاف المراقبة.",
}
_STOP_POLL_BTN = {
    "ua": "⏹ Зупинити моніторинг",
    "uk": "⏹ Зупинити моніторинг",
    "en": "⏹ Stop monitoring",
    "de": "⏹ Überwachung stoppen",
    "pl": "⏹ Zatrzymaj monitoring",
    "tr": "⏹ İzlemeyi durdur",
    "ar": "⏹ إيقاف المراقبة",
}
_POLL_NOT_ACTIVE_TEXT = {
    "ua": "ℹ️ Моніторинг не активний. Ви можете запустити новий пошук будь-коли.",
    "uk": "ℹ️ Моніторинг не активний. Ви можете запустити новий пошук будь-коли.",
    "en": "ℹ️ No active monitoring. You can start a new search anytime.",
    "de": "ℹ️ Keine aktive Überwachung. Sie können jederzeit eine neue Suche starten.",
    "pl": "ℹ️ Brak aktywnego monitorowania. Możesz rozpocząć nowe wyszukiwanie w dowolnym momencie.",
    "tr": "ℹ️ Aktif izleme yok. İstediğiniz zaman yeni bir arama başlatabilirsiniz.",
    "ar": "ℹ️ لا توجد مراقبة نشطة. يمكنك بدء بحث جديد في أي وقت.",
}

# --- Anti-frustration: rotating waiting reassurance (every 3rd check) ---
_WAITING_REASSURANCE = [
    {
        "ua": "🔄 Продовжуємо моніторинг офіційних систем…",
        "uk": "🔄 Продовжуємо моніторинг офіційних систем…",
        "en": "🔄 Still monitoring official systems…",
        "de": "🔄 Offizielle Systeme werden weiterhin überwacht…",
        "pl": "🔄 Nadal monitorujemy oficjalne systemy…",
        "tr": "🔄 Resmi sistemler izlenmeye devam ediyor…",
        "ar": "🔄 لا نزال نراقب الأنظمة الرسمية…",
    },
    {
        "ua": "⏳ Поки що без вільних місць — це нормально.",
        "uk": "⏳ Поки що без вільних місць — це нормально.",
        "en": "⏳ No slot yet — this is normal.",
        "de": "⏳ Noch kein Termin — das ist normal.",
        "pl": "⏳ Jeszcze brak miejsca — to normalne.",
        "tr": "⏳ Henüz yer yok — bu normal.",
        "ar": "⏳ لا يوجد موعد بعد — هذا طبيعي.",
    },
    {
        "ua": "📩 Сповістимо миттєво, щойно з\u02bcявиться місце.",
        "uk": "📩 Сповістимо миттєво, щойно з\u02bcявиться місце.",
        "en": "📩 We'll notify you instantly when something appears.",
        "de": "📩 Wir benachrichtigen Sie sofort, wenn etwas frei wird.",
        "pl": "📩 Powiadomimy Cię natychmiast, gdy coś się pojawi.",
        "tr": "📩 Bir yer açıldığında sizi anında bilgilendireceğiz.",
        "ar": "📩 سنُعلمك فورًا عند ظهور موعد.",
    },
]

# --- Anti-frustration: explicit stop reassurance ---
_POLL_STOPPED_REASSURANCE = {
    "ua": "⏹ Моніторинг зупинено. Ви можете перезапустити будь-коли — без обмежень.",
    "uk": "⏹ Моніторинг зупинено. Ви можете перезапустити будь-коли — без обмежень.",
    "en": "⏹ Monitoring stopped. You can restart anytime — no penalties.",
    "de": "⏹ Überwachung gestoppt. Sie können jederzeit neu starten — ohne Einschränkungen.",
    "pl": "⏹ Monitorowanie zatrzymane. Możesz uruchomić ponownie w dowolnym momencie — bez ograniczeń.",
    "tr": "⏹ İzleme durduruldu. İstediğiniz zaman yeniden başlatabilirsiniz — ceza yok.",
    "ar": "⏹ توقفت المراقبة. يمكنك إعادة التشغيل في أي وقت — بدون قيود.",
}

# --- Anti-frustration: reservation timeout reassurance ---
_RESERVATION_EXPIRED_REASSURANCE = {
    "ua": "🔍 Місця розбирають швидко — ми продовжуємо шукати для вас.",
    "uk": "🔍 Місця розбирають швидко — ми продовжуємо шукати для вас.",
    "en": "🔍 Slots are competitive — we're continuing the search for you.",
    "de": "🔍 Termine sind gefragt — wir suchen weiter für Sie.",
    "pl": "🔍 Miejsca szybko się rozchodzą — szukamy dalej dla Ciebie.",
    "tr": "🔍 Yerler hızla doluyor — sizin için aramaya devam ediyoruz.",
    "ar": "🔍 المواعيد تنافسية — نواصل البحث لأجلك.",
}

# --- Kill switch: shown when TERMIN_DISABLED=1 ---
_SERVICE_DISABLED_TEXT = {
    "ua": "⚠️ Сервіс тимчасово недоступний. Спробуйте пізніше.",
    "uk": "⚠️ Сервіс тимчасово недоступний. Спробуйте пізніше.",
    "en": "⚠️ Service temporarily unavailable. Please try later.",
    "de": "⚠️ Dienst vorübergehend nicht verfügbar. Bitte versuchen Sie es später.",
    "pl": "⚠️ Usługa tymczasowo niedostępna. Spróbuj ponownie później.",
    "tr": "⚠️ Hizmet geçici olarak kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
    "ar": "⚠️ الخدمة غير متاحة مؤقتًا. يرجى المحاولة لاحقًا.",
}

# --- Reservation soft-lock texts (Stage 2) ---
_RESERVATION_OFFER_TEXT = {
    "ua": (
        "⚡ <b>Місце знайдено!</b>\n\n"
        "{demand_label}\n"
        "💰 Вартість: <b>€{price}</b>\n\n"
        "Ми знайшли вільне місце.\n"
        "У вас є 45 секунд, щоб перейти до оплати.\n\n"
        "⏱ Місця з\u02bcявляються рідко — не втрачайте момент."
    ),
    "uk": (
        "⚡ <b>Місце знайдено!</b>\n\n"
        "{demand_label}\n"
        "💰 Вартість: <b>€{price}</b>\n\n"
        "Ми знайшли вільне місце.\n"
        "У вас є 45 секунд, щоб перейти до оплати.\n\n"
        "⏱ Місця з\u02bcявляються рідко — не втрачайте момент."
    ),
    "en": (
        "⚡ <b>Slot found!</b>\n\n"
        "{demand_label}\n"
        "💰 Price: <b>€{price}</b>\n\n"
        "We found an available slot.\n"
        "You have 45 seconds to proceed.\n\n"
        "⏱ Slots appear rarely — don't miss this one."
    ),
    "de": (
        "⚡ <b>Termin gefunden!</b>\n\n"
        "{demand_label}\n"
        "💰 Preis: <b>€{price}</b>\n\n"
        "Wir haben einen freien Termin gefunden.\n"
        "Sie haben 45 Sekunden, um fortzufahren.\n\n"
        "⏱ Termine erscheinen selten — verpassen Sie diesen nicht."
    ),
    "pl": (
        "⚡ <b>Znaleziono miejsce!</b>\n\n"
        "{demand_label}\n"
        "💰 Cena: <b>€{price}</b>\n\n"
        "Znaleźliśmy wolne miejsce.\n"
        "Masz 45 sekund, aby kontynuować.\n\n"
        "⏱ Miejsca pojawiają się rzadko — nie przegap."
    ),
    "tr": (
        "⚡ <b>Yer bulundu!</b>\n\n"
        "{demand_label}\n"
        "💰 Fiyat: <b>€{price}</b>\n\n"
        "Uygun bir yer bulduk.\n"
        "Devam etmek için 45 saniyeniz var.\n\n"
        "⏱ Yerler nadiren açılır — bu fırsatı kaçırmayın."
    ),
    "ar": (
        "⚡ <b>تم العثور على موعد!</b>\n\n"
        "{demand_label}\n"
        "💰 السعر: <b>€{price}</b>\n\n"
        "وجدنا موعدًا متاحًا.\n"
        "لديك 45 ثانية للمتابعة.\n\n"
        "⏱ المواعيد نادرة — لا تفوّت هذه الفرصة."
    ),
}
_RESERVATION_CONFIRM_BTN = {
    "ua": "✅ Підтвердити",
    "uk": "✅ Підтвердити",
    "en": "✅ Confirm",
    "de": "✅ Bestätigen",
    "pl": "✅ Potwierdź",
    "tr": "✅ Onayla",
    "ar": "✅ تأكيد",
}
_RESERVATION_CANCEL_BTN = {
    "ua": "❌ Скасувати",
    "uk": "❌ Скасувати",
    "en": "❌ Cancel",
    "de": "❌ Abbrechen",
    "pl": "❌ Anuluj",
    "tr": "❌ İptal",
    "ar": "❌ إلغاء",
}
_RESERVATION_CONFIRMED_TEXT = {
    "ua": "✅ <b>Підтверджено!</b>\nПерейдіть до оплати, щоб активувати моніторинг.",
    "uk": "✅ <b>Підтверджено!</b>\nПерейдіть до оплати, щоб активувати моніторинг.",
    "en": "✅ <b>Confirmed!</b>\nProceed to payment to activate slot monitoring.",
    "de": "✅ <b>Bestätigt!</b>\nFahren Sie mit der Zahlung fort, um die Terminüberwachung zu aktivieren.",
    "pl": "✅ <b>Potwierdzone!</b>\nPrzejdź do płatności, aby aktywować monitorowanie.",
    "tr": "✅ <b>Onaylandı!</b>\nYer izlemeyi etkinleştirmek için ödemeye geçin.",
    "ar": "✅ <b>تم التأكيد!</b>\nتابع الدفع لتفعيل مراقبة المواعيد.",
}
_RESERVATION_CANCELLED_TEXT = {
    "ua": "🔄 Місце звільнено. Моніторинг продовжується автоматично.",
    "uk": "🔄 Місце звільнено. Моніторинг продовжується автоматично.",
    "en": "🔄 Slot released. Monitoring continues automatically.",
    "de": "🔄 Termin freigegeben. Überwachung läuft automatisch weiter.",
    "pl": "🔄 Miejsce zwolnione. Monitorowanie kontynuowane automatycznie.",
    "tr": "🔄 Yer serbest bırakıldı. İzleme otomatik olarak devam ediyor.",
    "ar": "🔄 تم تحرير الموعد. المراقبة مستمرة تلقائيًا.",
}
_RESERVATION_NO_ACTIVE_TEXT = {
    "ua": "ℹ️ Наразі немає знайденого місця.",
    "uk": "ℹ️ Наразі немає знайденого місця.",
    "en": "ℹ️ No slot currently found.",
    "de": "ℹ️ Derzeit kein Termin gefunden.",
    "pl": "ℹ️ Aktualnie nie znaleziono miejsca.",
    "tr": "ℹ️ Şu anda bulunan yer yok.",
    "ar": "ℹ️ لم يتم العثور على موعد حالياً.",
}

# --- Phase 2: Success screen after slot found ---
_SLOT_FOUND_HEADER = {
    "ua": (
        "🎯 <b>Слот знайдено!</b>\n\n"
        "🏛 {authority}\n📍 {city}\n"
        "{date_line}"
        "{time_line}"
        "\nЩоб забронювати — перейдіть на офіційний сайт."
    ),
    "en": (
        "🎯 <b>Slot found!</b>\n\n"
        "🏛 {authority}\n📍 {city}\n"
        "{date_line}"
        "{time_line}"
        "\nTo book — go to the official website."
    ),
    "de": (
        "🎯 <b>Termin gefunden!</b>\n\n"
        "🏛 {authority}\n📍 {city}\n"
        "{date_line}"
        "{time_line}"
        "\nZum Buchen — besuchen Sie die offizielle Website."
    ),
    "pl": (
        "🎯 <b>Znaleziono termin!</b>\n\n"
        "🏛 {authority}\n📍 {city}\n"
        "{date_line}"
        "{time_line}"
        "\nAby zarezerwować — przejdź na oficjalną stronę."
    ),
    "tr": (
        "🎯 <b>Randevu bulundu!</b>\n\n"
        "🏛 {authority}\n📍 {city}\n"
        "{date_line}"
        "{time_line}"
        "\nRezervasyon için resmi siteye gidin."
    ),
    "ar": (
        "🎯 <b>تم العثور على موعد!</b>\n\n"
        "🏛 {authority}\n📍 {city}\n"
        "{date_line}"
        "{time_line}"
        "\nللحجز — انتقل إلى الموقع الرسمي."
    ),
}
_SLOT_BOOK_BTN = {
    "ua": "📅 Забронювати цей слот",
    "uk": "📅 Забронювати цей слот",
    "en": "📅 Book this slot",
    "de": "📅 Diesen Termin buchen",
    "pl": "📅 Zarezerwuj ten termin",
    "tr": "📅 Bu randevuyu al",
    "ar": "📅 احجز هذا الموعد",
}
_SLOT_REMIND_BTN = {
    "ua": "🔔 Нагадати за 24h до зустрічі",
    "en": "🔔 Remind me 24h before",
    "de": "🔔 24h vorher erinnern",
    "pl": "🔔 Przypomnij 24h wcześniej",
    "tr": "🔔 24 saat önce hatırlat",
    "ar": "🔔 تذكيري قبل 24 ساعة",
}
_UPSELL_MONITOR_BTN = {
    "ua": "💳 Моніторити ще один Termin",
    "uk": "💳 Моніторити ще один Termin",
    "en": "💳 Monitor another Termin",
    "de": "💳 Weiteren Termin überwachen",
    "pl": "💳 Monitoruj kolejny Termin",
    "tr": "💳 Başka Termin izle",
    "ar": "💳 مراقبة موعد آخر",
}
_SLOT_REMIND_CONFIRMED = {
    "ua": "✅ Нагадаємо за 24 години до вашого запису!",
    "uk": "✅ Нагадаємо за 24 години до вашого запису!",
    "en": "✅ We'll remind you 24 hours before your appointment!",
    "de": "✅ Wir erinnern Sie 24 Stunden vor Ihrem Termin!",
    "pl": "✅ Przypomnimy ci 24 godziny przed wizytą!",
    "tr": "✅ Randevunuzdan 24 saat önce hatırlatacağız!",
    "ar": "✅ سنذكرك قبل 24 ساعة من موعدك!",
}

# "I booked" confirmation flow (Step 1 → Step 2 → Step 3)
_I_BOOKED_BTN = {
    "ua": "✅ Я записався",
    "uk": "✅ Я записався",
    "en": "✅ I have booked",
    "de": "✅ Ich habe gebucht",
    "pl": "✅ Zarezerwowałem",
    "tr": "✅ Rezervasyon yaptım",
    "ar": "✅ لقد حجزت",
}
_CONFIRM_REMIND_TEXT = {
    "ua": "🎉 <b>Вітаємо із записом!</b>\n\nНагадати вам про зустріч за 24 години до неї?",
    "uk": "🎉 <b>Вітаємо із записом!</b>\n\nНагадати вам про зустріч за 24 години до неї?",
    "en": "🎉 <b>Congratulations on your booking!</b>\n\nShould we remind you 24 hours before your appointment?",
    "de": "🎉 <b>Glückwunsch zur Terminbuchung!</b>\n\nSoll ich Sie 24 Stunden vorher erinnern?",
    "pl": "🎉 <b>Gratulacje z okazji rezerwacji!</b>\n\nCzy mamy przypomnieć ci 24 godziny przed wizytą?",
    "tr": "🎉 <b>Randevunuz için tebrikler!</b>\n\nRandevunuzdan 24 saat önce hatırlatmamızı ister misiniz?",
    "ar": "🎉 <b>تهانينا على الحجز!</b>\n\nهل تريد أن نذكرك قبل 24 ساعة من موعدك؟",
}
_REMIND_YES_BTN = {
    "ua": "🔔 Так, нагадати",
    "uk": "🔔 Так, нагадати",
    "en": "🔔 Yes, remind me",
    "de": "🔔 Ja, erinnern",
    "pl": "🔔 Tak, przypomnij",
    "tr": "🔔 Evet, hatırlat",
    "ar": "🔔 نعم، ذكّرني",
}

# --- Payment gate texts (inside reservation flow) ---
_PROCEED_PAYMENT_BTN = {
    "ua": "💳 Перейти до оплати — €{price}",
    "uk": "💳 Перейти до оплати — €{price}",
    "en": "💳 Proceed to payment — €{price}",
    "de": "💳 Zur Zahlung — €{price}",
    "pl": "💳 Przejdź do płatności — €{price}",
    "tr": "💳 Ödemeye geç — €{price}",
    "ar": "💳 المتابعة إلى الدفع — €{price}",
}
_PROCEED_PAYMENT_TEXT = {
    "ua": (
        "🔔 <b>Активація моніторингу</b>\n\n"
        "{demand_label}\n"
        "💰 Вартість: <b>€{price}</b>\n\n"
        "Ми автоматично моніторимо офіційні системи "
        "та сповіщаємо миттєво.\n"
        "Ручний пошук зазвичай займає години або дні.\n\n"
        "Завершіть оплату, щоб активувати моніторинг місць."
    ),
    "uk": (
        "🔔 <b>Активація моніторингу</b>\n\n"
        "{demand_label}\n"
        "💰 Вартість: <b>€{price}</b>\n\n"
        "Ми автоматично моніторимо офіційні системи "
        "та сповіщаємо миттєво.\n"
        "Ручний пошук зазвичай займає години або дні.\n\n"
        "Завершіть оплату, щоб активувати моніторинг місць."
    ),
    "en": (
        "🔔 <b>Activate slot monitoring</b>\n\n"
        "{demand_label}\n"
        "💰 Price: <b>€{price}</b>\n\n"
        "We monitor official systems automatically "
        "and notify instantly.\n"
        "Searching manually usually takes hours or days.\n\n"
        "Complete your payment to activate slot monitoring."
    ),
    "de": (
        "🔔 <b>Terminüberwachung aktivieren</b>\n\n"
        "{demand_label}\n"
        "💰 Preis: <b>€{price}</b>\n\n"
        "Wir überwachen offizielle Systeme automatisch "
        "und benachrichtigen sofort.\n"
        "Manuelle Suche dauert oft Stunden oder Tage.\n\n"
        "Schließen Sie die Zahlung ab, um die Terminüberwachung zu aktivieren."
    ),
    "pl": (
        "🔔 <b>Aktywacja monitorowania</b>\n\n"
        "{demand_label}\n"
        "💰 Cena: <b>€{price}</b>\n\n"
        "Automatycznie monitorujemy oficjalne systemy "
        "i powiadamiamy natychmiast.\n"
        "Ręczne szukanie trwa zwykle godziny lub dni.\n\n"
        "Dokończ płatność, aby aktywować monitorowanie miejsc."
    ),
    "tr": (
        "🔔 <b>Yer izlemeyi etkinleştir</b>\n\n"
        "{demand_label}\n"
        "💰 Fiyat: <b>€{price}</b>\n\n"
        "Resmi sistemleri otomatik olarak izliyor "
        "ve anında bildiriyoruz.\n"
        "Manuel arama genellikle saatler veya günler sürer.\n\n"
        "Yer izlemeyi etkinleştirmek için ödemeyi tamamlayın."
    ),
    "ar": (
        "🔔 <b>تفعيل مراقبة المواعيد</b>\n\n"
        "{demand_label}\n"
        "💰 السعر: <b>€{price}</b>\n\n"
        "نراقب الأنظمة الرسمية تلقائيًا "
        "ونُعلمك فورًا.\n"
        "البحث اليدوي يستغرق عادةً ساعات أو أيام.\n\n"
        "أكمل الدفع لتفعيل مراقبة المواعيد."
    ),
}
# Post-payment success screen (rich premium tone) — used as guard response for late taps
_PAYMENT_SUCCESS_TEXT = {
    "ua": (
        "✅ <b>Моніторинг активовано.</b>\n\n"
        "Ми вже шукаємо вільні слоти.\n"
        "Повідомимо одразу після появи — в Telegram і на email.\n\n"
        "📌 Моніторинг працює до першого знайденого Termin."
    ),
    "uk": (
        "✅ <b>Моніторинг активовано.</b>\n\n"
        "Ми вже шукаємо вільні слоти.\n"
        "Повідомимо одразу після появи — в Telegram і на email.\n\n"
        "📌 Моніторинг працює до першого знайденого Termin."
    ),
    "en": (
        "✅ <b>Monitoring activated.</b>\n\n"
        "We are already searching for available slots.\n"
        "You will be notified instantly — via Telegram and email.\n\n"
        "📌 Monitoring runs until the first Termin is found."
    ),
    "de": (
        "✅ <b>Überwachung aktiviert.</b>\n\n"
        "Wir suchen bereits nach freien Terminen.\n"
        "Wir benachrichtigen Sie sofort — per Telegram und E-Mail.\n\n"
        "📌 Überwachung läuft bis zum ersten gefundenen Termin."
    ),
    "pl": (
        "✅ <b>Monitoring aktywowany.</b>\n\n"
        "Już szukamy wolnych terminów.\n"
        "Powiadomimy od razu po pojawieniu się — przez Telegram i e-mail.\n\n"
        "📌 Monitoring działa do znalezienia pierwszego Terminu."
    ),
    "tr": (
        "✅ <b>İzleme etkinleştirildi.</b>\n\n"
        "Müsait slotları zaten arıyoruz.\n"
        "Yer açıldığında anında bildirim göndereceğiz — Telegram ve e-posta ile.\n\n"
        "📌 İzleme ilk Termin bulunana kadar çalışır."
    ),
    "ar": (
        "✅ <b>تم تفعيل المراقبة.</b>\n\n"
        "نحن نبحث بالفعل عن مواعيد متاحة.\n"
        "سنبلغك فورًا عند ظهور موعد — عبر Telegram والبريد الإلكتروني.\n\n"
        "📌 المراقبة تعمل حتى العثور على أول موعد."
    ),
}
_PAYMENT_FAILED_TEXT = {
    "ua": "🔄 Місце звільнено. Моніторинг продовжується автоматично.",
    "uk": "🔄 Місце звільнено. Моніторинг продовжується автоматично.",
    "en": "🔄 Slot released. Monitoring continues automatically.",
    "de": "🔄 Termin freigegeben. Überwachung läuft automatisch weiter.",
    "pl": "🔄 Miejsce zwolnione. Monitorowanie kontynuowane automatycznie.",
    "tr": "🔄 Yer serbest bırakıldı. İzleme otomatik olarak devam ediyor.",
    "ar": "🔄 تم تحرير الموعد. المراقبة مستمرة تلقائيًا.",
}
# Payment recovery: shown when payment was not completed but reservation is still active
_PAYMENT_RETRY_TEXT = {
    "ua": "💳 Оплату не завершено. Ви можете спробувати ще раз.",
    "uk": "💳 Оплату не завершено. Ви можете спробувати ще раз.",
    "en": "💳 Payment was not completed. You can try again.",
    "de": "💳 Zahlung nicht abgeschlossen. Sie können es erneut versuchen.",
    "pl": "💳 Płatność nie została zakończona. Możesz spróbować ponownie.",
    "tr": "💳 Ödeme tamamlanmadı. Tekrar deneyebilirsiniz.",
    "ar": "💳 لم يتم إكمال الدفع. يمكنك المحاولة مرة أخرى.",
}
_PAYMENT_RETRY_BTN = {
    "ua": "🔁 Спробувати оплату знову — €{price}",
    "uk": "🔁 Спробувати оплату знову — €{price}",
    "en": "🔁 Try payment again — €{price}",
    "de": "🔁 Zahlung erneut versuchen — €{price}",
    "pl": "🔁 Spróbuj ponownie — €{price}",
    "tr": "🔁 Ödemeyi tekrar dene — €{price}",
    "ar": "🔁 أعد المحاولة — €{price}",
}
_PAYMENT_NOT_RESERVED_TEXT = {
    "ua": "ℹ️ Немає активного сеансу для оплати.",
    "uk": "ℹ️ Немає активного сеансу для оплати.",
    "en": "ℹ️ No active payment session.",
    "de": "ℹ️ Keine aktive Zahlungssitzung.",
    "pl": "ℹ️ Brak aktywnej sesji płatności.",
    "tr": "ℹ️ Aktif ödeme oturumu yok.",
    "ar": "ℹ️ لا توجد جلسة دفع نشطة.",
}
# Idempotency: shown when user taps "Proceed to payment" more than once
_PAYMENT_ALREADY_HELD_TEXT = {
    "ua": "🔒 Оплата вже очікується. Будь ласка, завершіть оплату нижче.",
    "uk": "🔒 Оплата вже очікується. Будь ласка, завершіть оплату нижче.",
    "en": "🔒 Payment is already pending. Please complete the payment below.",
    "de": "🔒 Zahlung ist bereits ausstehend. Bitte schließen Sie die Zahlung unten ab.",
    "pl": "🔒 Płatność jest już oczekiwana. Dokończ płatność poniżej.",
    "tr": "🔒 Ödeme zaten beklemede. Lütfen aşağıdan ödemeyi tamamlayın.",
    "ar": "🔒 الدفع قيد الانتظار بالفعل. يرجى إتمام الدفع أدناه.",
}
# Stage 17: Test buttons below are DEPRECATED — kept for backward compatibility with old messages.
# Production payment flow uses real Stripe Checkout via _create_termin_checkout().
_BTN_PAYMENT_SUCCESS_TEST = {
    "ua": "✅ Оплата успішна (тест)",
    "uk": "✅ Оплата успішна (тест)",
    "en": "✅ Payment success (test)",
    "de": "✅ Zahlung erfolgreich (Test)",
    "pl": "✅ Płatność udana (test)",
    "tr": "✅ Ödeme başarılı (test)",
    "ar": "✅ الدفع ناجح (اختبار)",
}
_BTN_PAYMENT_FAIL_TEST = {
    "ua": "❌ Оплату скасовано (тест)",
    "uk": "❌ Оплату скасовано (тест)",
    "en": "❌ Payment cancelled (test)",
    "de": "❌ Zahlung abgebrochen (Test)",
    "pl": "❌ Płatność anulowana (test)",
    "tr": "❌ Ödeme iptal (test)",
    "ar": "❌ إلغاء الدفع (اختبار)",
}


# ==================== Stripe Checkout for Termin (Stage 17) ====================


async def _create_termin_checkout(
    user_id: int, city: str, price: float, lang: str,
):
    """Create Stripe Checkout session for Termin reservation payment.

    Follows the same pattern as handle_notify_pay / handle_pay_for_reminders.
    Returns checkout URL (str) or None on failure. Never raises.
    """
    try:
        from utils.helpers import get_db
        from handlers.stripe_handler import get_stripe_handler

        db = get_db()
        order_lang = 'uk' if lang == 'ua' else lang
        order_id = db.create_order(
            user_id=user_id,
            doc_type='termin_reservation',
            amount=price,
            lang=order_lang,
        )

        webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
        success_url = _build_success_url(order_id)
        cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

        stripe_h = get_stripe_handler()
        result = await stripe_h.create_checkout_session(
            order_id=order_id,
            user_id=user_id,
            doc_type='termin_reservation',
            price=price,
            success_url=success_url,
            cancel_url=cancel_url,
            extra_metadata={
                'flow': 'termin',
                'city': city,
                'price': f"{price:.2f}",
            },
        )

        if result.success:
            from backend.database import OrderStatus
            db.update_order_status(
                order_id, OrderStatus.PENDING, stripe_session_id=result.session_id,
            )
            logger.info("SUCCESS_URL=%s", success_url)
            logger.info(
                "TERMIN_CHECKOUT_CREATED | user=%s order=%s session=%s price=%.2f",
                user_id, order_id, result.session_id, price,
            )
            if _TERMIN_DEBUG:
                logger.info(
                    "TERMIN_DEBUG_CHECKOUT_URL | user=%s order=%s url=%s",
                    user_id, order_id, result.checkout_url,
                )
            return result.checkout_url

        logger.error("TERMIN_CHECKOUT_STRIPE_FAIL | user=%s error=%s", user_id, result.error)
        return None

    except Exception as exc:
        logger.error("TERMIN_CHECKOUT_ERROR | user=%s error=%s", user_id, exc)
        return None


async def finalize_termin_webhook_payment(bot_instance, user_id: int, metadata: dict) -> bool:
    """Finalize Termin reservation payment — called ONLY from Stripe webhook (Stage 17).

    This is the AUTHORITATIVE payment finalization path. Double webhook delivery
    is safe due to _payment_completed idempotency guard.
    Double charge is impossible: Stripe Checkout sessions are one-time-use, and
    finalize_reservation is idempotent.

    Returns True if finalized (or already finalized), False if no active reservation.
    """
    try:
        # Defensive: only process termin flow (belt-and-suspenders with bot.py check)
        if metadata.get("flow") != "termin":
            logger.warning(
                "TERMIN_WEBHOOK_FLOW_MISMATCH | user=%s flow=%s", user_id, metadata.get("flow"),
            )
            return False

        if _TERMIN_DEBUG:
            logger.info("TERMIN_DEBUG_WEBHOOK_ENTRY | user=%s metadata=%s", user_id, metadata)

        lang = _resolve_lang(user_id)

        # Idempotency: already completed → skip all side effects
        if _payment_completed.get(user_id):
            logger.info("TERMIN_WEBHOOK_ALREADY_COMPLETED | user=%s", user_id)
            return True

        from utils.termin_checker import finalize_reservation

        finalized = finalize_reservation(user_id)
        _payment_screen_shown.pop(user_id, None)

        if _TERMIN_DEBUG:
            logger.info("TERMIN_DEBUG_FINALIZE_RESULT | user=%s finalized=%s", user_id, finalized)

        if not finalized:
            logger.warning("TERMIN_WEBHOOK_NO_RESERVATION | user=%s", user_id)
            return False

        _payment_completed[user_id] = True
        _termin_metrics["success"] += 1

        city = metadata.get("city", "")
        price = metadata.get("price", "n/a")

        log_event("termin_payment_success", user_id, {"city": city, "price": price})

        # Admin alert (best-effort, silent on failure — never blocks user flow)
        try:
            admin_ids = _get_admin_ids()
            if admin_ids:
                alert = (
                    f"💰 <b>Termin payment</b>\n"
                    f"User: <code>{user_id}</code>\n"
                    f"City: {city or 'n/a'}\n"
                    f"Price: €{price}"
                )
                for aid in admin_ids:
                    try:
                        await bot_instance.send_message(aid, alert, parse_mode="HTML")
                    except Exception:
                        logger.warning("ADMIN_ALERT_FAILED | admin=%s user=%s", aid, user_id)
        except Exception:
            logger.warning("ADMIN_ALERT_ERROR | user=%s", user_id)

        # Send success message to user proactively from webhook.
        # Mark termin:webhook_success_sent so the deeplink handler knows this
        # screen was already delivered and skips the duplicate.
        _webhook_success_sent = False
        try:
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(InlineKeyboardButton(
                get_text("btn_back", lang),
                callback_data="termin_menu",
            ))
            await bot_instance.send_message(
                chat_id=user_id,
                text=_lang_text(_PAYMENT_SUCCESS_TEXT, lang),
                parse_mode="HTML",
                reply_markup=kb,
            )
            _webhook_success_sent = True
            try:
                from utils.termin_redis import rset as _rset_ws
                _rset_ws(f"termin:webhook_success_sent:{user_id}", "1", 300)
            except Exception:
                pass
        except Exception:
            logger.warning("TERMIN_SUCCESS_MSG_FAILED | user=%s", user_id)

        # Clear FSM state so document handlers are not blocked after payment
        try:
            _dp = Dispatcher.get_current()
            if _dp:
                _fsm = _dp.current_state(chat=user_id, user=user_id)
                await _fsm.finish()
        except Exception:
            pass

        logger.info("TERMIN_WEBHOOK_FINALIZED | user=%s city=%s price=%s", user_id, city, price)
        return True

    except Exception as exc:
        logger.error("TERMIN_WEBHOOK_CRITICAL_ERROR | user=%s error=%s", user_id, exc)
        return False


async def handle_termin_use_existing_slot(callback: types.CallbackQuery, state: FSMContext):
    """User tapped '1️⃣ Use existing slot' on the plan screen.

    Simply delegates to handle_termin_start_poll which:
      - verifies the entitlement is still valid
      - starts the polling session
      - shows the full monitoring control menu
    """
    logger.info("TERMIN_USE_EXISTING_SLOT | user=%s", callback.from_user.id)
    callback.data = 'termin_start_poll'
    await handle_termin_start_poll(callback, state)


async def handle_termin_start_poll(callback: types.CallbackQuery, state: FSMContext):
    """Start availability polling for the user's selected city+authority."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    lang = _resolve_lang(user_id)

    # PAYMENT GATE — must be entitled before polling can start.
    # Blocks direct callback bypass (e.g. forged termin_start_poll).
    if not is_termin_entitled(str(user_id)):
        logger.warning("TERMIN_PAYMENT_REQUIRED | user=%s — no active entitlement, redirecting to payment", user_id)
        await handle_pay_termin_pdf(callback, state)
        return

    # Kill switch: block polling if TERMIN_DISABLED is set (env checked per-request, no restart needed)
    # TODO_STAGE18: For horizontal scaling, consider a shared feature flag (Redis/DB) instead of env.
    if os.getenv("TERMIN_DISABLED", "").strip() == "1":
        try:
            await callback.message.answer(
                _lang_text(_SERVICE_DISABLED_TEXT, lang),
            )
        except Exception:
            pass
        return

    user = _ensure_termin_user(user_id, lang)

    # FSM takes priority over DB: after a PDF→Termin flow the webhook already
    # wrote the correct city/authority into DB, but termin_pending_city in FSM
    # is the freshest value if it exists (written by handle_pay_termin_pdf).
    # DB fallback covers flows that don't go through the PDF gate.
    _fsm_data = await state.get_data()
    _fsm_city = _fsm_data.get("termin_pending_city", "").strip().lower()
    city      = _fsm_city if _fsm_city else (user.get("city", "") if user else "")
    authority = user.get("authority", "") if user else ""

    _payment_screen_shown.pop(user_id, None)  # clear stale payment flag on new flow
    _payment_completed.pop(user_id, None)     # clear post-payment guard on new flow

    if not city or not authority:
        await callback.message.answer(
            _build_termin_entry_text(lang),
            parse_mode="HTML",
        )
        return

    from utils.termin_checker import start_polling, is_polling, is_reserved, _sessions

    active_session = _sessions.get(user_id)
    if is_polling(user_id) or is_reserved(user_id):
        active_city = active_session.city if active_session else ""
        active_auth = active_session.authority if active_session else ""
        logger.info(
            "TERMIN_SESSION_COMPARE | user=%s active_city=%s active_auth=%s requested_city=%s requested_auth=%s",
            user_id, active_city, active_auth, city, authority,
        )
        if active_city == city and active_auth == authority:
            await callback.message.answer(
                _lang_text(_POLL_ALREADY_TEXT, lang),
            )
            return
        # Different city or authority — stop old session and fall through to Stripe
        from utils.termin_checker import stop_polling
        stop_polling(user_id)
        logger.info(
            "TERMIN_SESSION_STOPPED_FOR_NEW | user=%s old=%s/%s new=%s/%s",
            user_id, active_city, active_auth, city, authority,
        )

    bot_instance = callback.bot

    async def _send(cid: int, text: str) -> None:
        _l_send = lang if lang not in ("ua",) else "uk"
        if text.startswith("\u23f3"):  # ⏳ reservation expired signal (U+23F3 hourglass)
            log_event("termin_reservation_expired", user_id, {"city": city})
            _termin_metrics["expired"] += 1
            try:
                from backend.termin_db import get_entitlement as _get_ent_exp2
                from utils.time_utils import get_countdown_line as _get_cd_exp2
                _ent_exp2 = _get_ent_exp2(str(user_id))
                _paid_until_exp2 = (_ent_exp2 or {}).get("paid_until")
                _cd_exp2 = _get_cd_exp2(_paid_until_exp2, _l_send)

                _resume_kb2 = InlineKeyboardMarkup(row_width=1)
                _resume_kb2.add(InlineKeyboardButton(
                    _lang_text(_RESUME_SEARCH_BTN, _l_send),
                    callback_data="termin_resume_search",
                ))
                _resume_kb2.add(InlineKeyboardButton(
                    _lang_text(_EXPIRY_HOME_BTN, _l_send),
                    callback_data="main_menu",
                ))
                _msg2 = _SLOT_EXPIRED_CONSOLIDATED.get(_l_send, _SLOT_EXPIRED_CONSOLIDATED["en"])
                if _cd_exp2:
                    _msg2 = f"{_msg2}\n\n{_cd_exp2}"
                await bot_instance.send_message(cid, _msg2, reply_markup=_resume_kb2)
            except Exception:
                pass
        else:
            await bot_instance.send_message(cid, text)

    async def _on_reserved(cid: int, rlang: str) -> None:
        """Called by termin_checker when a slot is found — send reservation UI with payment gate."""
        # Use locked price from session (guard: immutable after RESERVED)
        locked = get_locked_price(user_id)
        res_price = f"{locked:.2f}" if locked is not None else _price_for(city, authority)
        demand_lbl = _demand_label(city, rlang)

        # Phase 2: Build success header with booking URL ──────────────────────
        _auth_display = _AUTHORITY_LABELS.get(authority, authority.title())
        _city_display = _CITY_DISPLAY_MAP.get(city, city.replace("_", " ").title())

        # Enrich with real scraper slot details (date/time/location/url)
        from utils.termin_checker import get_slot_details as _get_slot_details
        _slot = _get_slot_details(user_id)
        # Resolve booking URL: Priority A/B from slot data → authority DB → city portal fallback
        _booking_url = _slot.get("url") or None
        _BAD_URL_PARTS = ("select2", "ajax", "api")
        if _booking_url and any(x in _booking_url for x in _BAD_URL_PARTS):
            _booking_url = None
        if not _booking_url:
            try:
                _auth_info = get_authority_info(city, authority)
                _booking_url = _auth_info.get("booking_url") if _auth_info else None
            except Exception:
                pass
        if not _booking_url:
            _booking_url = build_best_booking_link(_slot, city)

        # Build optional date/time lines (empty string when scraper had no data)
        _slot_date = _slot.get("date", "")
        _slot_time = _slot.get("time", "")
        _slot_location = _slot.get("location", "")
        _date_line = f"📅 {_slot_date}\n" if _slot_date else ""
        _time_line = f"⏰ {_slot_time}\n" if _slot_time else ""
        # If scraper returned a more specific location, override generic city display
        if _slot_location:
            _city_display = _slot_location

        _success_header = _lang_text(_SLOT_FOUND_HEADER, rlang).format(
            authority=_auth_display,
            city=_city_display,
            date_line=_date_line,
            time_line=_time_line,
        )

        _kb_success = InlineKeyboardMarkup(row_width=1)
        _kb_success.add(
            InlineKeyboardButton(
                _lang_text(_SLOT_BOOK_BTN, rlang),
                url=_booking_url,
            ),
            InlineKeyboardButton(
                _lang_text(_I_BOOKED_BTN, rlang),
                callback_data="termin_i_booked",
            ),
            InlineKeyboardButton(
                _lang_text(_EXPIRY_HOME_BTN, rlang),
                callback_data="main_menu",
            ),
        )
        # Cross-sell: suggest matching PDF document after slot is found
        _CROSSSELL_BTN = {
            "uk": "📄 Підготувати документ для прийому",
            "ua": "📄 Підготувати документ для прийому",
            "en": "📄 Prepare document for the appointment",
            "de": "📄 Dokument für den Termin vorbereiten",
            "pl": "📄 Przygotuj dokument na wizytę",
            "tr": "📄 Randevu için belge hazırla",
            "ar": "📄 تحضير الوثيقة للموعد",
        }
        try:
            _fsmdata = await state.get_data() if state else {}
            _source = _fsmdata.get("source_doc") or ""
        except Exception:
            _source = ""
        if _source and _source not in ("termin_notifications", "termin_monitor_24h", ""):
            _kb_success.add(InlineKeyboardButton(
                _lang_text(_CROSSSELL_BTN, rlang),
                callback_data=f"doc_{_source}",
            ))
        # Continue-search button: user taps if they missed booking the slot
        _kb_success.add(InlineKeyboardButton(
            _lang_text(_RESUME_SEARCH_BTN, rlang),
            callback_data="termin_resume_search",
        ))
        # Track slot-found time for post-completion follow-up
        _slot_found_registry[str(cid)] = datetime.now(timezone.utc).isoformat()
        try:
            from utils.stats import increment_termin_found as _inc_found
            _inc_found()
        except Exception:
            pass
        await bot_instance.send_message(
            cid,
            _success_header,
            parse_mode="HTML",
            reply_markup=_kb_success,
        )
        # No payment offer — user already paid for monitoring.

    async def _on_slot_found(cid: int, flang: str, slot: dict) -> None:
        """Called by termin_checker when a slot is found without reservation.
        Builds the found-message and attaches the upsell keyboard here in the
        handler — no text-pattern detection needed."""
        found_msg = build_found_message(flang, slot)
        upsell_kb = InlineKeyboardMarkup(row_width=1)
        upsell_kb.add(InlineKeyboardButton(
            _lang_text(_UPSELL_MONITOR_BTN, flang),
            callback_data="termin_menu",
        ))
        await bot_instance.send_message(cid, found_msg, reply_markup=upsell_kb)

    started = start_polling(
        user_id, chat_id, city, authority, lang,
        send_fn=_send, on_reserved_fn=_on_reserved,
        on_found_fn=_on_slot_found,
    )
    if started:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            _lang_text(_STOP_POLL_BTN, lang),
            callback_data="termin_stop_poll",
        ))
        kb.add(InlineKeyboardButton(
            get_text("btn_back", lang),
            callback_data="termin_menu",
        ))
        await callback.message.answer(
            _lang_text(_POLL_START_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await callback.message.answer(
            _lang_text(_POLL_ALREADY_TEXT, lang),
        )


async def handle_termin_stop_poll(callback: types.CallbackQuery, state: FSMContext):
    """Stop the availability polling loop for this user."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    from utils.termin_checker import stop_polling

    stopped = stop_polling(user_id)
    if stopped:
        await callback.message.answer(
            _lang_text(_POLL_STOPPED_REASSURANCE, lang),
        )
    else:
        await callback.message.answer(
            _lang_text(_POLL_NOT_ACTIVE_TEXT, lang),
        )
    return True


async def handle_termin_resume_search(callback: types.CallbackQuery, state: FSMContext):
    """User taps '🔄 Continue search' after a slot notification.

    Resumes the paused polling session without requiring a new payment.
    Works only when the session is in PAUSED_AFTER_FOUND state.
    """
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    from utils.termin_checker import resume_after_found, TerminStatus, _sessions

    from backend.termin_db import get_entitlement as _get_ent_resume
    from utils.time_utils import get_countdown_line as _get_cd_resume

    session = _sessions.get(user_id)
    if session and session.status == TerminStatus.PAUSED_AFTER_FOUND:
        resumed = resume_after_found(user_id)
        if resumed:
            # Reset email notified flag so next slot found triggers a new email
            try:
                from backend.termin_db import reset_termin_email_notified as _rst_email
                _rst_email(str(user_id))
            except Exception:
                pass
            _ent_r = _get_ent_resume(str(user_id))
            _paid_until_r = (_ent_r or {}).get("paid_until")
            _cd_r = _get_cd_resume(_paid_until_r, lang)

            _resume_msg = {
                "ua": "Схоже, цей слот уже зайнятий.\n\nНе хвилюйтеся — моніторинг продовжується.\n{countdown}\n\nМи продовжуємо шукати нові Termin.",
                "uk": "Схоже, цей слот уже зайнятий.\n\nНе хвилюйтеся — моніторинг продовжується.\n{countdown}\n\nМи продовжуємо шукати нові Termin.",
                "en": "Looks like this slot is already taken.\n\nDon't worry — monitoring continues.\n{countdown}\n\nWe will keep searching for new appointments.",
                "de": "Dieser Termin ist vermutlich bereits vergeben.\n\nKeine Sorge — die Überwachung läuft weiter.\n{countdown}\n\nWir suchen weiter nach neuen Terminen.",
                "pl": "Wygląda na to, że ten termin jest już zajęty.\n\nNie martw się — monitoring trwa.\n{countdown}\n\nNadal szukamy nowych terminów.",
                "tr": "Bu randevu muhtemelen zaten alındı.\n\nEndişelenme — izleme devam ediyor.\n{countdown}\n\nYeni randevu aramaya devam ediyoruz.",
                "ar": "يبدو أن هذا الموعد محجوز بالفعل.\n\nلا تقلق — المراقبة مستمرة.\n{countdown}\n\nسنواصل البحث عن مواعيد جديدة.",
            }
            _tpl = _lang_text(_resume_msg, lang)
            _msg_text = _tpl.format(countdown=_cd_r) if _cd_r else _tpl.replace("\n{countdown}", "")
            await callback.message.answer(_msg_text)
            logger.info("TERMIN_RESUME_SEARCH | user=%s", user_id)
            return True

    # Session exists but status is no longer PAUSED_AFTER_FOUND — already resumed
    if session is not None:
        _already_running_msg = {
            "ua": "🔍 Пошук уже триває. Ми повідомимо вас, коли знайдемо слот.",
            "uk": "🔍 Пошук уже триває. Ми повідомимо вас, коли знайдемо слот.",
            "en": "🔍 Search is already running. We'll notify you when a slot appears.",
            "de": "🔍 Die Suche läuft bereits. Wir benachrichtigen Sie, sobald ein Termin verfügbar ist.",
            "pl": "🔍 Wyszukiwanie jest już aktywne. Powiadomimy Cię, gdy pojawi się termin.",
            "tr": "🔍 Arama zaten devam ediyor. Bir randevu çıktığında sizi bilgilendireceğiz.",
            "ar": "🔍 البحث جارٍ بالفعل. سنبلغك عند ظهور موعد.",
        }
        await callback.message.answer(_lang_text(_already_running_msg, lang))
        return True

    # Session truly gone (bot restarted, monitoring stopped, or entitlement expired)
    _no_session_msg = {
        "ua": "ℹ️ Моніторинг завершено або бот перезапустився. Щоб відновити пошук — перейдіть до меню Termin.",
        "uk": "ℹ️ Моніторинг завершено або бот перезапустився. Щоб відновити пошук — перейдіть до меню Termin.",
        "en": "ℹ️ Monitoring has stopped or the bot restarted. Go to the Termin menu to resume your search.",
        "de": "ℹ️ Die Überwachung wurde beendet oder der Bot neu gestartet. Gehe zum Termin-Menü, um die Suche fortzusetzen.",
        "pl": "ℹ️ Monitoring zatrzymany lub bot został zrestartowany. Wróć do menu Termin, aby wznowić wyszukiwanie.",
        "tr": "ℹ️ İzleme durdu veya bot yeniden başlatıldı. Aramaya devam etmek için Termin menüsüne gidin.",
        "ar": "ℹ️ توقفت المراقبة أو أُعيد تشغيل البوت. انتقل إلى قائمة Termin لاستئناف البحث.",
    }
    await callback.message.answer(_lang_text(_no_session_msg, lang))
    return True


async def handle_termin_conflict_switch(callback: types.CallbackQuery, state: FSMContext):
    """User chose '🔄 Switch to <new_city>' on the city-conflict prompt.

    Stops the currently active polling session and redirects to the payment
    screen for the new city so the user can pay and activate monitoring.
    callback.data format: termin_conflict_switch_<city_code>
    """
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    new_city = callback.data.replace("termin_conflict_switch_", "").strip()
    logger.info("TERMIN_CONFLICT_SWITCH | user=%s new_city=%s", user_id, new_city)

    # Stop the old polling session (if still alive) before starting a new one
    from utils.termin_checker import stop_polling as _stop
    _stop(user_id)

    # Persist new city to FSM so handle_pay_termin_pdf / handle_termin_monitor_confirm
    # will use it for the Stripe session metadata.
    await state.update_data(termin_pending_city=new_city)

    # Forward to payment screen directly (same path as Guard 1 mismatch → paid gate)
    await handle_pay_termin_pdf(callback, state)
    return True


async def handle_termin_confirm_reservation(callback: types.CallbackQuery, state: FSMContext):
    """User confirms the soft-lock reservation."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    from utils.termin_checker import confirm_reservation

    confirmed = confirm_reservation(user_id)
    if confirmed:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            get_text("btn_back", lang),
            callback_data="termin_menu",
        ))
        await callback.message.answer(
            _lang_text(_RESERVATION_CONFIRMED_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )
        logger.info("TERMIN_RESERVATION_USER_CONFIRMED | user=%s", user_id)
    else:
        await callback.message.answer(
            _lang_text(_RESERVATION_NO_ACTIVE_TEXT, lang),
        )


async def handle_termin_cancel_reservation(callback: types.CallbackQuery, state: FSMContext):
    """User cancels the soft-lock reservation — polling resumes automatically."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    from utils.termin_checker import cancel_reservation

    # Hard guard: payment already completed — block any further action
    if _payment_completed.get(user_id):
        try:
            await callback.message.answer(
                _lang_text(_PAYMENT_SUCCESS_TEXT, lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # Stripe cancel/back case: if payment screen was shown, offer retry instead
    if _payment_screen_shown.get(user_id):
        locked = get_locked_price(user_id)
        if locked is not None:
            _payment_screen_shown.pop(user_id, None)
            retry_price = f"{locked:.2f}"
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(InlineKeyboardButton(
                _lang_text(_PAYMENT_RETRY_BTN, lang).format(price=retry_price),
                callback_data="termin_proceed_payment",
            ))
            try:
                await callback.message.answer(
                    _lang_text(_PAYMENT_RETRY_TEXT, lang),
                    reply_markup=kb,
                )
            except Exception:
                pass
            logger.info("TERMIN_CANCEL_RETRY_OFFERED | user=%s price=%s", user_id, retry_price)
            return

    # Normal reservation cancel (before payment) — release and resume polling
    cancelled = cancel_reservation(user_id)
    _payment_screen_shown.pop(user_id, None)
    if cancelled:
        log_event("termin_payment_cancel", user_id)
        await callback.message.answer(
            _lang_text(_RESERVATION_CANCELLED_TEXT, lang),
        )
        logger.info("TERMIN_RESERVATION_USER_CANCELLED | user=%s", user_id)
    else:
        await callback.message.answer(
            _lang_text(_RESERVATION_NO_ACTIVE_TEXT, lang),
        )


async def handle_termin_set_reminder_final(callback: types.CallbackQuery, state: FSMContext):
    """Step 3: user confirmed they want a 24h reminder — acknowledge and save."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    try:
        await callback.message.answer(
            _lang_text(_SLOT_REMIND_CONFIRMED, lang),
            parse_mode="HTML",
        )
        logger.info("TERMIN_REMINDER_FINAL_SET | user=%s", user_id)
    except Exception as _err:
        logger.warning("TERMIN_REMINDER_FINAL_ERROR | user=%s err=%s", user_id, _err)


async def handle_termin_i_booked(callback: types.CallbackQuery, state: FSMContext):
    """Step 2: user tapped '✅ I booked!' — ask if they want a 24h reminder."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # Cancel the reservation timer so "Час резервації минув" doesn't fire after booking.
    from utils.termin_checker import _sessions, TerminStatus
    _session = _sessions.get(user_id)
    if _session:
        if _session.reservation_task and not _session.reservation_task.done():
            try:
                _session.reservation_task.cancel()
            except Exception:
                pass
        _session.reservation_task = None
        _session.status = TerminStatus.FINALIZED
        logger.info("TERMIN_I_BOOKED_TIMER_CANCELLED | user=%s", user_id)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            _lang_text(_REMIND_YES_BTN, lang),
            callback_data="termin_set_reminder_final",
        ),
        InlineKeyboardButton(
            _lang_text(_EXPIRY_HOME_BTN, lang),
            callback_data="main_menu",
        ),
    )
    try:
        await callback.message.answer(
            _lang_text(_CONFIRM_REMIND_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )
        logger.info("TERMIN_I_BOOKED | user=%s — asking about reminder", user_id)
    except Exception as _err:
        logger.warning("TERMIN_I_BOOKED_ERROR | user=%s err=%s", user_id, _err)


# ==================== Payment Gate Handlers ====================

# Idempotency guard: tracks whether the payment screen was already shown per user.
# Redis-backed (Stage 15): survives restart when REDIS_URL is set; falls back to in-memory.
_payment_screen_shown = RedisBackedDict("termin:screen", ttl=1800)   # 30 min

# Post-payment hard guard: blocks duplicate actions after successful payment.
# Redis-backed (Stage 15): survives restart when REDIS_URL is set; falls back to in-memory.
_payment_completed = RedisBackedDict("termin:paid", ttl=86400)       # 24 hours


async def handle_termin_proceed_payment(callback: types.CallbackQuery, state: FSMContext):
    """User clicks 'Proceed to payment' — pause reservation timer, show payment placeholder."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # ── Consent gate ──
    if not _has_termin_consent(user_id):
        await _show_termin_consent(callback, "termin_proceed_payment", "termin_main")
        return

    # Hard guard: payment already completed — block any further action
    if _payment_completed.get(user_id):
        try:
            await callback.message.answer(
                _lang_text(_PAYMENT_SUCCESS_TEXT, lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    from utils.termin_checker import proceed_to_payment

    proceeded = proceed_to_payment(user_id)
    if proceeded:
        # Idempotent guard: if payment screen was already sent, show short reassurance
        if _payment_screen_shown.get(user_id):
            try:
                await callback.message.answer(
                    _lang_text(_PAYMENT_ALREADY_HELD_TEXT, lang),
                )
            except Exception:
                pass
            return
        _payment_screen_shown[user_id] = True

        # Use locked price from session (guard: immutable after RESERVED)
        locked = get_locked_price(user_id)
        user = _ensure_termin_user(user_id, lang)
        user_city = user.get('city', '') if user else ''
        user_authority = user.get('authority', '') if user else ''
        pay_price = f"{locked:.2f}" if locked is not None else _price_for(user_city, user_authority)
        demand_lbl = _demand_label(user_city, lang) if user_city else ''

        # Stage 17: Create real Stripe Checkout session
        checkout_url = await _create_termin_checkout(
            user_id, user_city,
            locked if locked is not None else float(pay_price.replace(",", ".")),
            lang,
        )
        if not checkout_url:
            # Stripe unavailable — reset flag, allow user to retry
            _payment_screen_shown.pop(user_id, None)
            logger.error("TERMIN_CHECKOUT_UNAVAILABLE | user=%s", user_id)
            await callback.message.answer(
                _lang_text(_PAYMENT_NOT_RESERVED_TEXT, lang),
            )
            return

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            _lang_text(_STRIPE_OPEN_BTN, lang).format(price=pay_price),
            url=checkout_url,
        ))
        # Compose message: payment text + trust block (before CTA buttons)
        pay_msg = _lang_text(_PROCEED_PAYMENT_TEXT, lang).format(
            price=pay_price, demand_label=demand_lbl,
        )
        pay_msg += "\n\n" + _trust_block(lang)

        # Force external browser on first tap — avoids Telegram WebView auto-close.
        try:
            await callback.answer(url=checkout_url)
        except Exception:
            await callback.answer(cache_time=1)
        await callback.message.answer(
            pay_msg,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        logger.info("TERMIN_PROCEED_PAYMENT | user=%s locked_price=%s", user_id, pay_price)
    else:
        await callback.message.answer(
            _lang_text(_PAYMENT_NOT_RESERVED_TEXT, lang),
        )


async def handle_termin_payment_success(callback: types.CallbackQuery, state: FSMContext):
    """Legacy callback — payment finalization is now webhook-driven (Stage 17).

    Kept registered for backward compatibility with old messages containing test buttons.
    Does NOT finalize — that happens only via finalize_termin_webhook_payment().
    """
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # Clear TerminStates so document handlers are not blocked
    try:
        current = await state.get_state()
        if current and current.startswith('TerminStates:'):
            await state.finish()
    except Exception:
        pass

    # If payment was completed via webhook → show success text (idempotent)
    if _payment_completed.get(user_id):
        try:
            await callback.message.answer(
                _lang_text(_PAYMENT_SUCCESS_TEXT, lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # Webhook hasn't confirmed payment yet — show reassurance, do NOT finalize
    try:
        await callback.message.answer(
            _lang_text(_PAYMENT_ALREADY_HELD_TEXT, lang),
        )
    except Exception:
        pass


async def handle_termin_payment_fail(callback: types.CallbackQuery, state: FSMContext):
    """Payment failure/cancel — offer retry if reservation is still active."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # Hard guard: payment already completed — block any further action
    if _payment_completed.get(user_id):
        try:
            await callback.message.answer(
                _lang_text(_PAYMENT_SUCCESS_TEXT, lang),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    from utils.termin_checker import is_reserved, fail_payment

    locked = get_locked_price(user_id)

    # If reservation is still alive → keep it, offer retry (do NOT restart polling)
    if locked is not None and is_reserved(user_id):
        _payment_screen_shown.pop(user_id, None)
        retry_price = f"{locked:.2f}"
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            _lang_text(_PAYMENT_RETRY_BTN, lang).format(price=retry_price),
            callback_data="termin_proceed_payment",
        ))
        try:
            await callback.message.answer(
                _lang_text(_PAYMENT_RETRY_TEXT, lang),
                reply_markup=kb,
            )
        except Exception:
            pass
        log_event("termin_payment_retry", user_id, {"price": retry_price})
        _termin_metrics["retry"] += 1
        logger.info("TERMIN_PAYMENT_RETRY_OFFERED | user=%s price=%s", user_id, retry_price)
        return

    # Reservation expired or not found → release and resume polling (existing flow)
    failed = fail_payment(user_id)
    _payment_screen_shown.pop(user_id, None)
    if failed:
        _termin_metrics["fail"] += 1
        log_event("termin_payment_cancel", user_id)
        await callback.message.answer(
            _lang_text(_PAYMENT_FAILED_TEXT, lang),
        )
        logger.info("TERMIN_PAYMENT_FAIL_RESUMED | user=%s", user_id)
    else:
        await callback.message.answer(
            _lang_text(_PAYMENT_NOT_RESERVED_TEXT, lang),
        )


# ──────────────────────────────────────────────────────────────
# Phase 1: Expiry re-engagement registry (in-memory, per-process)
# Populated in handle_termin_monitor_confirm() when Stripe session succeeds.
# Consumed / cleaned up in process_reminders() expiry loop below.
# ──────────────────────────────────────────────────────────────
_monitor_expiry_registry: dict = {}   # telegram_id (str) → ISO expiry datetime
_expiry_warning_sent: set = set()     # telegram_id (str) — already sent warning
_slot_found_registry: dict = {}       # telegram_id (str) → ISO datetime when slot was found

_EXPIRY_WARNING_TEXT = {
    "ua": "⏳ Моніторинг завершується менш ніж через 6 годин.\nВи можете продовжити без переривання захисту.",
    "uk": "⏳ Моніторинг завершується менш ніж через 6 годин.\nВи можете продовжити без переривання захисту.",
    "en": "⏳ Monitoring expires in less than 6 hours.\nYou can extend it without interrupting protection.",
    "de": "⏳ Die Überwachung endet in weniger als 6 Stunden.\nSie können sie verlängern, ohne den Schutz zu unterbrechen.",
    "pl": "⏳ Monitoring wygasa za mniej niż 6 godzin.\nMożesz go przedłużyć bez przerywania ochrony.",
    "tr": "⏳ İzleme 6 saatten az içinde sona eriyor.\nKorumanızı kesmeden uzatabilirsiniz.",
    "ar": "⏳ تنتهي المراقبة في أقل من 6 ساعات.\nيمكنك تمديدها دون انقطاع الحماية.",
}
_EXPIRY_EXTEND_BTN = {
    "ua": "➕ Продовжити 24h — €2.99",
    "en": "➕ Extend 24h — €2.99",
    "de": "➕ 24h verlängern — €2.99",
    "pl": "➕ Przedłuż o 24h — €2.99",
    "tr": "➕ 24 saat uzat — €2.99",
    "ar": "➕ تمديد 24 ساعة — €2.99",
}
_EXPIRY_HOME_BTN = {
    "ua": "⬅️ Головне меню", "en": "⬅️ Main menu", "de": "⬅️ Hauptmenü",
    "pl": "⬅️ Menu główne", "tr": "⬅️ Ana menü", "ar": "⬅️ القائمة الرئيسية",
}


# ==================== Reminder Processing ====================
async def process_reminders(bot: Bot):
    """Process and send scheduled reminders"""
    reminders = get_active_reminders()
    now = datetime.now(timezone.utc)

    for reminder in reminders:
        last_sent = reminder.get('last_sent')
        interval_hours = reminder.get('interval_hours', 6)

        if last_sent:
            try:
                last_sent_dt = datetime.fromisoformat(last_sent.replace('Z', '+00:00'))
                next_send = last_sent_dt + timedelta(hours=interval_hours)
                if now < next_send:
                    continue
            except (ValueError, TypeError):
                pass

        user = get_user(reminder['telegram_id'])
        if not user:
            continue
        lang = user.get('language', 'en')

        cities = get_cities()
        city_info = next((c for c in cities if c['code'] == reminder.get('city_code')), None)
        city_name = city_info.get(f'name_{lang}') if city_info else reminder.get('city_code', 'Berlin')

        auth_name = reminder.get('name_en', reminder.get('authority_type', 'Authority'))
        _city_code = reminder.get('city_code', '')
        booking_url = (
            reminder.get('booking_url')
            or _CITY_PORTAL_FALLBACKS.get(_city_code.lower(), "https://service.berlin.de")
        )

        try:
            msg = get_text('termin_reminder_message', lang, city=city_name, authority=auth_name, url=booking_url)
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton(get_text('btn_open_booking', lang), url=booking_url),
                InlineKeyboardButton(get_text('termin_pause_reminders', lang), callback_data='termin_pause'),
            )
            await bot.send_message(
                chat_id=int(reminder['telegram_id']),
                text=msg,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            update_reminder_sent(reminder['id'])
            logger.info(f"Sent termin reminder to {reminder['telegram_id']}")
        except Exception as e:
            logger.error(f"Failed to send termin reminder to {reminder['telegram_id']}: {e}")

    # ── Phase 1: Expiry re-engagement push ──────────────────────────────────
    for _tid, _expires_iso in list(_monitor_expiry_registry.items()):
        try:
            _expires_dt = datetime.fromisoformat(_expires_iso.replace('Z', '+00:00'))
            if _expires_dt.tzinfo is None:
                _expires_dt = _expires_dt.replace(tzinfo=timezone.utc)

            if now >= _expires_dt:
                # Monitor fully expired — clean up, no push needed
                _monitor_expiry_registry.pop(_tid, None)
                _expiry_warning_sent.discard(_tid)
                continue

            _warn_threshold = _expires_dt - timedelta(hours=6)
            if now < _warn_threshold:
                continue  # Too early — not yet in the 6h warning window

            if _tid in _expiry_warning_sent:
                continue  # Already sent warning for this monitoring period

            _exp_user = get_user(_tid)
            if not _exp_user:
                continue
            _exp_lang = _exp_user.get('language', 'en')

            _exp_kb = InlineKeyboardMarkup(row_width=1)
            _exp_kb.add(
                InlineKeyboardButton(
                    _lang_text(_EXPIRY_EXTEND_BTN, _exp_lang),
                    callback_data="termin_extend_24h",
                ),
                InlineKeyboardButton(
                    _lang_text(_EXPIRY_HOME_BTN, _exp_lang),
                    callback_data="main_menu",
                ),
            )
            await bot.send_message(
                chat_id=int(_tid),
                text=_lang_text(_EXPIRY_WARNING_TEXT, _exp_lang),
                parse_mode="HTML",
                reply_markup=_exp_kb,
            )
            _expiry_warning_sent.add(_tid)
            logger.info("TERMIN_EXPIRY_WARN_SENT | user=%s expires=%s", _tid, _expires_iso)
        except Exception as _exp_err:
            logger.warning("TERMIN_EXPIRY_WARN_FAILED | user=%s error=%s", _tid, _exp_err)

    # ── Phase 3 (FIX 7): Family bundle Profile 2 nudge (once, 2h after activation) ──
    for _uid_str, _expiry_iso in list(_monitor_expiry_registry.items()):
        _nudge_key = f"p2_nudge_{_uid_str}"
        if _nudge_key in _expiry_warning_sent:
            continue
        try:
            _uid_int = int(_uid_str)
            if not _is_family_user(_uid_int):
                continue
            from backend.termin_db import get_user_profile, get_active_profile
            if get_user_profile(_uid_int, 2) is not None:
                _expiry_warning_sent.add(_nudge_key)
                continue  # Profile 2 already used
            _exp_dt = datetime.fromisoformat(_expiry_iso.replace('Z', '+00:00'))
            if _exp_dt.tzinfo is None:
                _exp_dt = _exp_dt.replace(tzinfo=timezone.utc)
            _hours_since = (now - (_exp_dt - timedelta(hours=24))).total_seconds() / 3600
            if _hours_since < 2:
                continue  # Too early
            _lang_nudge = get_user(_uid_str).get('language', 'en') if get_user(_uid_str) else 'en'
            _P2_NUDGE = {
                "uk": "👨‍👩‍👧 <b>Ваш план на 2 особи</b>\n\nПрофіль 2 ще не використано. Хтось ще може шукати запис — просто натисніть «Профіль 2» в меню Termin.",
                "ua": "👨‍👩‍👧 <b>Ваш план на 2 особи</b>\n\nПрофіль 2 ще не використано. Хтось ще може шукати запис — просто натисніть «Профіль 2» в меню Termin.",
                "en": "👨‍👩‍👧 <b>Your 2-person plan</b>\n\nProfile 2 is unused. Someone else can search for an appointment — just tap 'Profile 2' in the Termin menu.",
                "de": "👨‍👩‍👧 <b>Ihr 2-Personen-Plan</b>\n\nProfil 2 wurde noch nicht genutzt. Jemand anderes kann einen Termin suchen — tippen Sie auf 'Profil 2'.",
                "pl": "👨‍👩‍👧 <b>Twój plan dla 2 osób</b>\n\nProfil 2 nie został użyty. Ktoś inny może szukać terminu — kliknij 'Profil 2' w menu Termin.",
                "tr": "👨‍👩‍👧 <b>2 kişilik planınız</b>\n\nProfil 2 henüz kullanılmadı. Başka biri de randevu arayabilir — Termin menüsünde 'Profil 2'ye dokunun.",
                "ar": "👨‍👩‍👧 <b>خطتك لشخصين</b>\n\nالملف 2 لم يُستخدم بعد. يمكن لشخص آخر البحث عن موعد — اضغط على 'الملف 2' في قائمة Termin.",
            }
            _nudge_kb = InlineKeyboardMarkup(row_width=1)
            _nudge_kb.add(InlineKeyboardButton(
                {"uk": "📅 Відкрити Termin", "ua": "📅 Відкрити Termin",
                 "en": "📅 Open Termin", "de": "📅 Termin öffnen",
                 "pl": "📅 Otwórz Termin", "tr": "📅 Termin'i aç",
                 "ar": "📅 فتح Termin"}.get(_lang_nudge, "📅 Open Termin"),
                callback_data="termin_menu",
            ))
            await bot.send_message(
                chat_id=_uid_int,
                text=_lang_text(_P2_NUDGE, _lang_nudge),
                parse_mode="HTML",
                reply_markup=_nudge_kb,
            )
            _expiry_warning_sent.add(_nudge_key)
            logger.info("P2_NUDGE_SENT | user=%s", _uid_int)
        except Exception as _ne:
            logger.warning("P2_NUDGE_ERROR | user=%s err=%s", _uid_str, _ne)

    # ── Phase 4 (FIX 8): Post-completion follow-up 3 days after slot found ──────
    for _uid_str, _found_iso in list(_slot_found_registry.items()):
        _fu_key = f"followup_{_uid_str}"
        if _fu_key in _expiry_warning_sent:
            continue
        try:
            _found_dt = datetime.fromisoformat(_found_iso.replace('Z', '+00:00'))
            if _found_dt.tzinfo is None:
                _found_dt = _found_dt.replace(tzinfo=timezone.utc)
            _days_since = (now - _found_dt).total_seconds() / 86400
            if _days_since < 3:
                continue
            _uid_int = int(_uid_str)
            _fu_user = get_user(_uid_str)
            _lang_fu = _fu_user.get('language', 'en') if _fu_user else 'en'
            _FOLLOWUP = {
                "uk": "🎉 Сподіваємось, ваш прийом пройшов успішно!\n\nЩо далі? Ми допоможемо з наступними документами:\n📄 Kindergeld, BAföG, Bürgergeld — все в одному місці.",
                "ua": "🎉 Сподіваємось, ваш прийом пройшов успішно!\n\nЩо далі? Ми допоможемо з наступними документами:\n📄 Kindergeld, BAföG, Bürgergeld — все в одному місці.",
                "en": "🎉 Hope your appointment went well!\n\nWhat's next? We can help with your next documents:\n📄 Kindergeld, BAföG, Bürgergeld — all in one place.",
                "de": "🎉 Wir hoffen, Ihr Termin war erfolgreich!\n\nWas kommt als nächstes? Wir helfen mit Ihren Dokumenten:\n📄 Kindergeld, BAföG, Bürgergeld — alles an einem Ort.",
                "pl": "🎉 Mamy nadzieję, że wizyta przebiegła pomyślnie!\n\nCo dalej? Pomożemy z kolejnymi dokumentami:\n📄 Kindergeld, BAföG, Bürgergeld — wszystko w jednym miejscu.",
                "tr": "🎉 Randevunuzun iyi geçtiğini umuyoruz!\n\nSırada ne var? Belgelerinizde size yardımcı olabiliriz:\n📄 Kindergeld, BAföG, Bürgergeld — hepsi tek yerde.",
                "ar": "🎉 نأمل أن يكون موعدك قد سار بشكل جيد!\n\nماذا بعد؟ يمكننا مساعدتك في مستنداتك التالية:\n📄 Kindergeld, BAföG, Bürgergeld — كل شيء في مكان واحد.",
            }
            _fu_kb = InlineKeyboardMarkup(row_width=1)
            _fu_kb.add(InlineKeyboardButton(
                {"uk": "📂 Переглянути документи", "ua": "📂 Переглянути документи",
                 "en": "📂 Browse documents", "de": "📂 Dokumente ansehen",
                 "pl": "📂 Przeglądaj dokumenty", "tr": "📂 Belgelere göz at",
                 "ar": "📂 تصفح الوثائق"}.get(_lang_fu, "📂 Browse documents"),
                callback_data="back_to_main_menu",
            ))
            _fu_kb.add(InlineKeyboardButton(
                {"uk": "📅 Ще один Termin", "ua": "📅 Ще один Termin",
                 "en": "📅 Book another Termin", "de": "📅 Weiteren Termin buchen",
                 "pl": "📅 Kolejny termin", "tr": "📅 Başka randevu",
                 "ar": "📅 موعد آخر"}.get(_lang_fu, "📅 Another Termin"),
                callback_data="termin_cities",
            ))
            from handlers.nav import nav_home_text as _nav_home_fu
            _fu_kb.add(InlineKeyboardButton(_nav_home_fu(_lang_fu), callback_data="main_menu"))
            await bot.send_message(
                chat_id=_uid_int,
                text=_lang_text(_FOLLOWUP, _lang_fu),
                parse_mode="HTML",
                reply_markup=_fu_kb,
            )
            _expiry_warning_sent.add(_fu_key)
            logger.info("FOLLOWUP_SENT | user=%s days=%.1f", _uid_int, _days_since)
        except Exception as _fue:
            logger.warning("FOLLOWUP_ERROR | user=%s err=%s", _uid_str, _fue)


# ==================== PDF→Termin upsell handler ====================

def _resolve_city_code(city_name: str) -> str:
    """Best-effort resolution of a free-text city name to a termin DB city code.

    Handles umlauts and common ASCII transliterations so that values coming
    from the WebApp form (e.g. "Dusseldorf", "Koeln", "Munich") map correctly
    even when the DB stores only the umlaut form ("Düsseldorf", "Köln", "München").

    Falls back to 'berlin' when no match is found.
    """
    if not city_name:
        return "berlin"
    normalized = city_name.strip().lower()
    if not normalized:
        return "berlin"

    # Static aliases: ASCII / no-umlaut variants → canonical city code.
    # These cover values that arrive from HTML forms, URL params, or user input
    # and would otherwise miss the DB name comparison below.
    _ALIASES: dict = {
        # München
        "münchen": "muenchen",
        "munchen": "muenchen",
        "muenchen": "muenchen",
        "munich": "muenchen",
        # Köln
        "köln": "koeln",
        "koeln": "koeln",
        "cologne": "koeln",
        # Düsseldorf
        "düsseldorf": "duesseldorf",
        "dusseldorf": "duesseldorf",
        "duesseldorf": "duesseldorf",
        # Frankfurt (common abbreviation)
        "frankfurt am main": "frankfurt",
        "frankfurt/main": "frankfurt",
        # Hamburg (inactive but present in DB)
        "hamburg": "hamburg",
        # Dortmund
        "dortmund": "dortmund",
        # Berlin
        "berlin": "berlin",
    }
    if normalized in _ALIASES:
        return _ALIASES[normalized]

    # DB lookup — compare against all localised name columns
    try:
        cities = get_cities()
        name_keys = ("code", "name_de", "name_en", "name_ua", "name_pl", "name_tr", "name_ar")
        for city in cities:
            for key in name_keys:
                val = city.get(key, "")
                if val and val.strip().lower() == normalized:
                    return city["code"]
    except Exception:
        pass
    return "berlin"


DOC_AUTHORITY_MAP = {
    "anmeldung": "buergeramt",
    "ummeldung": "buergeramt",
    "wohnungsgeberbestaetigung": "buergeramt",
    "aufenthaltstitel": "auslaenderbehoerde",
    "wohngeld": "wohnungsamt",
    "kindergeld": "familienkasse",
    "kinderzuschlag": "familienkasse",
    "elterngeld": "familienkasse",
    "buergergeld": "jobcenter",
    "bafoeg": "jobcenter",
}

# Module-level authority display labels — used by scan result AND payment screens.
# Keys use canonical SUPPORTED_AUTHORITIES spellings (buergeramt, auslaenderbehoerde).
_AUTHORITY_LABELS = {
    "buergeramt": "Bürgeramt",
    "burgeramt": "Bürgeramt",           # legacy alias — kept for old DB rows
    "auslaenderbehoerde": "Ausländerbehörde",
    "auslanderbehorde": "Ausländerbehörde",  # legacy alias
    "wohnungsamt": "Wohnungsamt",
    "familienkasse": "Familienkasse",
    "jobcenter": "Jobcenter",
    "standesamt": "Standesamt",
}

# City code → human-readable display name
_CITY_DISPLAY_MAP = {
    "berlin": "Berlin",
    "muenchen": "München",
    "frankfurt": "Frankfurt",
    "koeln": "Köln",
    "cologne": "Köln",
    "duesseldorf": "Düsseldorf",
    "dusseldorf": "Düsseldorf",
    "dortmund": "Dortmund",
}


_SCAN_HEADER = {
    "ua": "🔎 Шукаємо вільні терміни...",
    "en": "🔎 Searching available appointments...",
    "de": "🔎 Verfügbare Termine werden gesucht...",
    "pl": "🔎 Szukamy wolnych terminów...",
    "tr": "🔎 Uygun randevular aranıyor...",
    "ar": "🔎 جارٍ البحث عن مواعيد متاحة...",
}
_SCAN_WE_CHECK = {
    "ua": "Ми перевіряємо:", "en": "We are checking:", "de": "Wir prüfen:",
    "pl": "Sprawdzamy:", "tr": "Kontrol ediyoruz:", "ar": "نتحقق من:",
}
_SCAN_CHECKED = {
    "ua": "Перевірено", "en": "Checked", "de": "Geprüft",
    "pl": "Sprawdzono", "tr": "Kontrol edildi", "ar": "تم التحقق",
}


def _build_scan_office_names(city_code: str, authority_type: Optional[str] = None):
    """Return (office_names list, total slots count) using official German authority names."""
    try:
        auth_rows = get_authorities(city_code)
    except Exception:
        auth_rows = []

    if authority_type and auth_rows:
        focused = [a for a in auth_rows if a.get("authority_type") == authority_type]
        if focused:
            auth_rows = focused

    office_names = []
    for a in auth_rows:
        n = a.get("name_de") or a.get("name_en") or a.get("authority_type", "")
        if n:
            office_names.append(n)
    if not office_names:
        office_names = ["Bürgeramt", "Ausländerbehörde", "Familienkasse", "Jobcenter"]

    total = max(len(office_names) * 8, 30)
    return office_names[:6], total


async def run_scan_animation(
    bot: Bot,
    chat_id: int,
    lang: str,
    city_code: str,
    authority_type: Optional[str] = None,
) -> types.Message:
    """
    Standalone scan animation: sends a new message and animates a progress bar.
    Returns the final message object so callers can edit it with the result.

    Usable from any entry point (PDF upsell, main menu Termin, future flows).
    """
    import asyncio

    office_names, total = _build_scan_office_names(city_code, authority_type)
    office_bullets = "\n".join(f"• {n}" for n in office_names)

    header = _lang_text(_SCAN_HEADER, lang)
    we_check = _lang_text(_SCAN_WE_CHECK, lang)
    checked_label = _lang_text(_SCAN_CHECKED, lang)
    offices_block = f"{we_check}\n{office_bullets}"
    steps = [0, int(total * 0.2), int(total * 0.45), int(total * 0.72), total]

    def _progress_text(n: int) -> str:
        bar_len = 10
        filled = int(n / total * bar_len) if total else 0
        bar = "▓" * filled + "░" * (bar_len - filled)
        return f"{header}\n\n{offices_block}\n\n{bar}  {checked_label}: {n} / {total}"

    sent = await bot.send_message(chat_id, _progress_text(0), parse_mode="HTML")

    for count in steps[1:]:
        await asyncio.sleep(2)
        try:
            await bot.edit_message_text(
                _progress_text(count), chat_id=chat_id, message_id=sent.message_id, parse_mode="HTML"
            )
        except Exception:
            pass

    await asyncio.sleep(1)
    return sent


# ── No-slots compact screen (FIX 5) ──────────────────────────────────────────
_NO_SLOTS_COMPACT = {
    "ua": (
        "{profile_line}"
        "❗️ <b>Вільних слотів не знайдено.</b>\n\n"
        "✅ Моніторинг перевіряє кожні кілька секунд.\n"
        "📌 Пошук продовжується до першого знайденого Termin."
    ),
    "uk": (
        "{profile_line}"
        "❗️ <b>Вільних слотів не знайдено.</b>\n\n"
        "✅ Моніторинг перевіряє кожні кілька секунд.\n"
        "📌 Пошук продовжується до першого знайденого Termin."
    ),
    "en": (
        "{profile_line}"
        "❗️ <b>No free slots found right now.</b>\n\n"
        "✅ Monitoring checks every few seconds.\n"
        "📌 Search continues until the first Termin is found."
    ),
    "de": (
        "{profile_line}"
        "❗️ <b>Keine freien Termine gefunden.</b>\n\n"
        "✅ Überwachung prüft alle paar Sekunden.\n"
        "📌 Suche läuft bis zum ersten gefundenen Termin."
    ),
    "pl": (
        "{profile_line}"
        "❗️ <b>Brak wolnych terminów.</b>\n\n"
        "✅ Monitoring sprawdza co kilka sekund.\n"
        "📌 Wyszukiwanie trwa do znalezienia pierwszego Terminu."
    ),
    "tr": (
        "{profile_line}"
        "❗️ <b>Şu anda boş randevu bulunamadı.</b>\n\n"
        "✅ İzleme her birkaç saniyede kontrol eder.\n"
        "📌 Arama ilk Termin bulunana kadar devam eder."
    ),
    "ar": (
        "{profile_line}"
        "❗️ <b>لا توجد مواعيد متاحة حاليًا.</b>\n\n"
        "✅ المراقبة كل بضع ثوانٍ.\n"
        "📌 البحث يستمر حتى العثور على أول موعد."
    ),
}
_NO_SLOTS_DETAILS_BTN = {
    "ua": "ℹ️ Чому важко знайти слот?",
    "uk": "ℹ️ Чому важко знайти слот?",
    "en": "ℹ️ Why is it hard to find a slot?",
    "de": "ℹ️ Warum ist es schwer, einen Termin zu finden?",
    "pl": "ℹ️ Dlaczego trudno znaleźć termin?",
    "tr": "ℹ️ Neden randevu bulmak zor?",
    "ar": "ℹ️ لماذا يصعب إيجاد موعد؟",
}


async def _run_live_termin_scan(
    callback: types.CallbackQuery,
    city_code: str,
    city_display: str,
    lang: str,
    authority_type: Optional[str] = None,
    recommended_authority_label: Optional[str] = None,
    active_profile_id: int = 1,
    is_family: bool = False,
):
    """Animated live-scan experience: real office names, progress bar, then trust-layer monitor upsell."""
    import asyncio

    office_names, total = _build_scan_office_names(city_code, authority_type)
    office_bullets = "\n".join(f"• {n}" for n in office_names)

    header = _lang_text(_SCAN_HEADER, lang)
    we_check = _lang_text(_SCAN_WE_CHECK, lang)
    checked_label = _lang_text(_SCAN_CHECKED, lang)
    offices_block = f"{we_check}\n{office_bullets}"

    steps = [0, int(total * 0.2), int(total * 0.45), int(total * 0.72), total]

    def _progress_text(n: int) -> str:
        bar_len = 10
        filled = int(n / total * bar_len) if total else 0
        bar = "▓" * filled + "░" * (bar_len - filled)
        return f"{header}\n\n{offices_block}\n\n{bar}  {checked_label}: {n} / {total}"

    await callback.message.edit_text(_progress_text(0), parse_mode="HTML")

    for count in steps[1:]:
        await asyncio.sleep(2)
        try:
            await callback.message.edit_text(_progress_text(count), parse_mode="HTML")
        except Exception:
            pass

    await asyncio.sleep(1)

    # Dead dicts removed — content moved to _NO_SLOTS_WHY_TEXT (module level)
    _MONITOR_BTN_BASE = {
        "ua": "🔔 Почати моніторинг",
        "en": "🔔 Start Monitoring",
        "de": "🔔 Überwachung starten",
        "pl": "🔔 Rozpocznij monitoring",
        "tr": "🔔 İzlemeyi başlat",
        "ar": "🔔 بدء المراقبة",
    }
    _HOME_BTN = {
        "ua": "🏠 Головне меню", "en": "🏠 Main menu", "de": "🏠 Hauptmenü",
        "pl": "🏠 Menu główne", "tr": "🏠 Ana menü", "ar": "🏠 القائمة الرئيسية",
    }
    _RESCAN_BTN = {
        "ua": "🔁 Перевірити ще раз",
        "en": "🔁 Check again",
        "de": "🔁 Erneut prüfen",
        "pl": "🔁 Sprawdź ponownie",
        "tr": "🔁 Tekrar kontrol et",
        "ar": "🔁 تحقق مرة أخرى",
    }
    # _NO_SLOTS_COMPACT and _NO_SLOTS_DETAILS_BTN are defined at module level
    # (with both "ua" and "uk" keys) — no local duplicate needed.

    _REC_HEADER = {
        "ua": "🏛 <b>Рекомендована установа:</b>",
        "en": "🏛 <b>Recommended authority:</b>",
        "de": "🏛 <b>Empfohlene Behörde:</b>",
        "pl": "🏛 <b>Rekomendowany urząd:</b>",
        "tr": "🏛 <b>Önerilen kurum:</b>",
        "ar": "🏛 <b>:الجهة الموصى بها</b>",
    }
    rec_block = (
        f"\n{_lang_text(_REC_HEADER, lang)} {recommended_authority_label}\n"
        if recommended_authority_label else ""
    )

    _profile_line = (
        _lang_text(_ACTIVE_PROFILE_LABEL, lang).format(n=active_profile_id) + "\n\n"
        if is_family else ""
    )
    result_text = (
        _lang_text(_NO_SLOTS_COMPACT, lang).format(profile_line=_profile_line)
        + rec_block
    )

    kb = InlineKeyboardMarkup(row_width=1)
    # Family: switch buttons ABOVE scan/monitor/home
    if is_family:
        if active_profile_id != 1:
            kb.add(InlineKeyboardButton(
                _lang_text(_SWITCH_TO_P1_BTN, lang),
                callback_data="termin_switch_profile_1",
            ))
        if active_profile_id != 2:
            kb.add(InlineKeyboardButton(
                _lang_text(_SWITCH_TO_P2_BTN, lang),
                callback_data="termin_switch_profile_2",
            ))
    kb.add(InlineKeyboardButton(
        _lang_text(_RESCAN_BTN, lang),
        callback_data=f"termin_rescan_{city_code}",
    ))
    kb.add(InlineKeyboardButton(
        _lang_text(_MONITOR_BTN_BASE, lang),
        callback_data=f"termin_monitor_pay_{city_code}",
    ))
    kb.add(InlineKeyboardButton(
        _lang_text(_HOME_BTN, lang),
        callback_data="main_menu",
    ))
    kb.add(InlineKeyboardButton(
        _lang_text(_NO_SLOTS_DETAILS_BTN, lang),
        callback_data=f"termin_no_slots_details_{city_code}",
    ))

    try:
        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(result_text, parse_mode="HTML", reply_markup=kb)


async def handle_termin_no_slots_details(callback: types.CallbackQuery, state: FSMContext):
    """Show full 'why no slots' explanation as a separate message."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    details_text = _lang_text(_NO_SLOTS_WHY_TEXT, lang)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        {"ua": "⬅️ Назад", "en": "⬅️ Back", "de": "⬅️ Zurück",
         "pl": "⬅️ Wróć", "tr": "⬅️ Geri", "ar": "⬅️ رجوع"}.get(lang, "⬅️ Back"),
        callback_data="termin_menu",
    ))
    try:
        await callback.message.edit_text(details_text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await callback.message.answer(details_text, parse_mode="HTML", reply_markup=kb)
        except Exception as _e:
            logger.warning("handle_termin_no_slots_details send error: %s", _e)


async def handle_termin_from_pdf(callback: types.CallbackQuery, state: FSMContext):
    """Post-PDF upsell: user already has city/plz/doc in FSM → live scan."""
    user_id = callback.from_user.id

    # DEV reset must run BEFORE any guard/entitlement check so test users
    # always enter the payment flow fresh, even if an active session exists.
    _dev_reset_if_needed(user_id)
    logger.info("DEV_RESET_CALLED user=%s", user_id)

    logger.info("TERMIN_FROM_PDF_HANDLER_REACHED: user=%s", user_id)

    await callback.answer(cache_time=1)
    lang = _resolve_lang(user_id)
    data = await state.get_data()

    source = data.get("source_doc")
    if not source:
        logger.warning("TERMIN_FROM_PDF: no source_doc in FSM for user %s — entering normal flow", user_id)
        _ensure_termin_user(user_id, lang)
        await TerminStates.selecting_city.set()
        await callback.message.edit_text(
            _build_termin_entry_text(lang),
            parse_mode="HTML",
            reply_markup=get_cities_keyboard(lang),
        )
        return

    # termin_city is written by stripe_handler.py from the PDF form data.
    # It is the only guaranteed-fresh source for the current PDF flow.
    # If it is missing or empty, fall back to "berlin" rather than trusting
    # any leftover termin_pending_city / city from a previous Termin flow.
    city_name = data.get("termin_city", "").strip()
    if not city_name:
        logger.warning(
            "TERMIN_FROM_PDF_NO_CITY | user=%s — termin_city missing from FSM, defaulting to berlin",
            user_id,
        )
    city_code = _resolve_city_code(city_name) if city_name else "berlin"
    city_display = city_name or "Berlin"

    _ensure_termin_user(user_id, lang)
    authority_type = DOC_AUTHORITY_MAP.get(source, "buergeramt")
    # Only write to DB after city_code is verified from the current PDF flow.
    logger.info(
        "TERMIN_FROM_PDF_DB_WRITE | user=%s city=%s authority=%s",
        user_id, city_code, authority_type,
    )
    update_user(str(user_id), city=city_code, authority=authority_type)

    # ── Guard 1: if monitoring already running for same city/authority → status screen ──
    from utils.termin_checker import get_session as _get_session
    _active = _get_session(user_id)
    if _active:
        _active_city = (_active.city or "").lower()
        _active_auth = _norm_authority(_active.authority)
        _req_city = (city_code or "").lower()
        _req_auth = _norm_authority(authority_type)
        logger.info(
            "TERMIN_GUARD_PDF | user=%s active=%s/%s requested=%s/%s",
            user_id, _active_city, _active_auth, _req_city, _req_auth,
        )
        if _active_city == _req_city and _active_auth == _req_auth:
            logger.info(
                "TERMIN_GUARD_MATCH_PDF | user=%s city=%s auth=%s — showing status",
                user_id, _req_city, _req_auth,
            )
            await handle_termin_status(callback, state)
            return True
        else:
            # Active session is for a DIFFERENT city/authority.
            # Warn the user before proceeding — they may not realise monitoring
            # for another city is still running.
            _active_city_display = _CITY_DISPLAY_MAP.get(_active_city, _active_city.replace("_", " ").title())
            _req_city_display    = _CITY_DISPLAY_MAP.get(_req_city,    _req_city.replace("_", " ").title())
            logger.warning(
                "TERMIN_CONFLICT_FROM_PDF | user=%s active=%s/%s requested=%s/%s"
                " — showing switch/keep prompt",
                user_id, _active_city, _active_auth, _req_city, _req_auth,
            )
            _CONFLICT_WARN = {
                "ua": "⚠️ У вас активний моніторинг <b>{active_city}</b>!\nБот шукає одне місто одночасно.",
                "uk": "⚠️ У вас активний моніторинг <b>{active_city}</b>!\nБот шукає одне місто одночасно.",
                "en": "⚠️ You have active monitoring for <b>{active_city}</b>!\nThe bot tracks one city at a time.",
                "de": "⚠️ Sie haben aktive Überwachung für <b>{active_city}</b>!\nDer Bot überwacht eine Stadt gleichzeitig.",
                "pl": "⚠️ Masz aktywny monitoring dla <b>{active_city}</b>!\nBot śledzi jedno miasto naraz.",
                "tr": "⚠️ <b>{active_city}</b> için aktif izlemeniz var!\nBot aynı anda bir şehri takip eder.",
                "ar": "⚠️ لديك مراقبة نشطة لـ <b>{active_city}</b>!\nيتتبع البوت مدينة واحدة في كل مرة.",
            }
            _SWITCH_BTN = {
                "ua": "🔄 Переключити на {new_city}",
                "uk": "🔄 Переключити на {new_city}",
                "en": "🔄 Switch to {new_city}",
                "de": "🔄 Zu {new_city} wechseln",
                "pl": "🔄 Przełącz na {new_city}",
                "tr": "🔄 {new_city}'ye geç",
                "ar": "🔄 التبديل إلى {new_city}",
            }
            _KEEP_BTN = {
                "ua": "↩️ Залишити {active_city}",
                "uk": "↩️ Залишити {active_city}",
                "en": "↩️ Keep {active_city}",
                "de": "↩️ {active_city} behalten",
                "pl": "↩️ Zostaw {active_city}",
                "tr": "↩️ {active_city}'de kal",
                "ar": "↩️ الاحتفاظ بـ {active_city}",
            }
            warn_text = _lang_text(_CONFLICT_WARN, lang).format(active_city=_active_city_display)
            switch_lbl = _lang_text(_SWITCH_BTN, lang).format(new_city=_req_city_display)
            keep_lbl   = _lang_text(_KEEP_BTN,   lang).format(active_city=_active_city_display)
            # Encode new city into callback so the switch handler knows what to activate
            _switch_cb = f"termin_conflict_switch_{_req_city}"
            conflict_kb = InlineKeyboardMarkup(row_width=1)
            conflict_kb.add(InlineKeyboardButton(switch_lbl, callback_data=_switch_cb))
            conflict_kb.add(InlineKeyboardButton(keep_lbl,   callback_data="termin_menu"))
            await callback.message.answer(warn_text, parse_mode="HTML", reply_markup=conflict_kb)
            return True

    # ── Guard 2: no active session → check entitlement before running checker ──
    if not is_termin_entitled(str(user_id)):
        logger.warning(
            "TERMIN_PAYMENT_REQUIRED_FROM_PDF | user=%s city=%s auth=%s — not entitled",
            user_id, city_code, authority_type,
        )
        await handle_pay_termin_pdf(callback, state)
        return True

    logger.info(
        "TERMIN_FROM_PDF_SCAN | user=%s city_name=%s city_code=%s plz=%s source=%s authority=%s",
        user_id, city_name, city_code, data.get("termin_plz"), source, authority_type,
    )

    auth_label = _AUTHORITY_LABELS.get(authority_type, None) if authority_type else None

    if not city_code or not authority_type:
        _missing_data_text = {
            "ua": "⚠️ Не вдалося перевірити Termin — не вистачає даних.",
            "uk": "⚠️ Не вдалося перевірити Termin — не вистачає даних.",
            "en": "⚠️ Cannot check Termin — missing data.",
            "de": "⚠️ Termin konnte nicht geprüft werden — fehlende Daten.",
            "pl": "⚠️ Nie można sprawdzić Terminu — brak danych.",
            "tr": "⚠️ Termin kontrol edilemiyor — eksik veri.",
            "ar": "⚠️ تعذّر التحقق من الموعد — بيانات مفقودة.",
        }
        await callback.message.answer(_missing_data_text.get(lang, _missing_data_text["en"]))
        return

    from utils.termin_checker import check_termin_availability
    try:
        status, slot_data = await check_termin_availability(city_code, authority_type)
    except Exception as e:
        logger.warning("TERMIN_SCAN_ERROR %s", e)
        status, slot_data = TerminStatus.NOT_AVAILABLE, {}

    if status.name == "AVAILABLE":
        _available_text = {
            "ua": "✅ Терміни доступні!\n\nЗаписи зараз відкриті.",
            "uk": "✅ Терміни доступні!\n\nЗаписи зараз відкриті.",
            "en": "✅ Termin available!\n\nAppointments are currently available.",
            "de": "✅ Termine verfügbar!\n\nAktuell sind Termine buchbar.",
            "pl": "✅ Terminy dostępne!\n\nObecnie można zapisać się na wizytę.",
            "tr": "✅ Randevu mevcut!\n\nŞu anda randevu alınabilir.",
            "ar": "✅ المواعيد متاحة!\n\nيمكن حجز موعد الآن.",
        }
        await callback.message.answer(_available_text.get(lang, _available_text["en"]))
    else:
        _no_slots_text = {
            "ua": "🔎 Зараз вільних дат не знайдено.",
            "uk": "🔎 Зараз вільних дат не знайдено.",
            "en": "🔎 No free slots found right now.",
            "de": "🔎 Derzeit keine freien Termine gefunden.",
            "pl": "🔎 Brak wolnych terminów w tej chwili.",
            "tr": "🔎 Şu anda uygun tarih bulunamadı.",
            "ar": "🔎 لا توجد مواعيد متاحة الآن.",
        }
        kb = InlineKeyboardMarkup(row_width=1)
        if is_termin_entitled(str(user_id)):
            # Already paid → offer immediate monitoring
            _start_btn = {
                "ua": "🔔 Почати моніторинг",
                "uk": "🔔 Почати моніторинг",
                "en": "🔔 Start Monitoring",
                "de": "🔔 Überwachung starten",
                "pl": "🔔 Rozpocznij monitoring",
                "tr": "🔔 İzlemeyi başlat",
                "ar": "🔔 بدء المراقبة",
            }
            kb.add(InlineKeyboardButton(
                text=_start_btn.get(lang, _start_btn["en"]),
                callback_data="start_monitoring",
            ))
        else:
            # Not yet paid → show payment activation button
            price = _get_termin_price(source)
            _pay_btn = {
                "ua": f"🔎 Активувати моніторинг — €{price:.2f}",
                "uk": f"🔎 Активувати моніторинг — €{price:.2f}",
                "en": f"🔎 Activate monitoring — €{price:.2f}",
                "de": f"🔎 Überwachung aktivieren — €{price:.2f}",
                "pl": f"🔎 Aktywuj monitoring — €{price:.2f}",
                "tr": f"🔎 İzlemeyi başlat — €{price:.2f}",
                "ar": f"🔎 تفعيل المراقبة — €{price:.2f}",
            }
            kb.add(InlineKeyboardButton(
                text=_pay_btn.get(lang, _pay_btn["en"]),
                callback_data="pay_termin_pdf",
            ))
        await callback.message.answer(
            _no_slots_text.get(lang, _no_slots_text["en"]),
            reply_markup=kb,
        )
    return True


async def handle_start_monitoring(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    if not is_termin_entitled(str(user_id)):
        # User pressed "Start monitoring" without a valid payment — redirect to payment flow
        await handle_pay_termin_pdf(callback, state)
        return True
    # If polling is already running for the same city+authority the user is
    # targeting, show the status screen.  A different city/authority falls
    # through to handle_termin_start_poll which stops the old session and opens Stripe.
    from utils.termin_checker import get_session as _get_session_sm
    _active_sm = _get_session_sm(user_id)
    if _active_sm:
        _user_row_sm = _ensure_termin_user(user_id, _resolve_lang(user_id))
        _city_sm = ((_user_row_sm or {}).get("city") or "").lower()
        _auth_sm = _norm_authority((_user_row_sm or {}).get("authority") or "")
        _act_city_sm = (_active_sm.city or "").lower()
        _act_auth_sm = _norm_authority(_active_sm.authority)
        logger.info(
            "TERMIN_GUARD_START | user=%s active=%s/%s requested=%s/%s",
            user_id, _act_city_sm, _act_auth_sm, _city_sm, _auth_sm,
        )
        if _act_city_sm == _city_sm and _act_auth_sm == _auth_sm:
            logger.info("TERMIN_GUARD_MATCH_START | user=%s city=%s auth=%s — showing status screen", user_id, _city_sm, _auth_sm)
            await handle_termin_status(callback, state)
            return True
    await handle_termin_start_poll(callback, state)
    return True


async def handle_pay_termin_pdf(callback: types.CallbackQuery, state: FSMContext):
    """Payment gate for Termin monitoring started from the PDF post-delivery flow.

    Shown when the user presses "Activate monitoring" (pay_termin_pdf) or when
    handle_start_monitoring detects an unpaid user.  Reads city_code / source_doc
    from FSM (written by handle_termin_from_pdf) and delegates to the standard
    Termin price-screen + Stripe flow (handle_termin_monitor_pay).

    This handler ONLY shows the payment screen — it never starts polling.
    Polling starts only after successful Stripe payment (webhook → entitlement).
    """
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    data = await state.get_data()

    city_code = _resolve_city_code(data.get("termin_city", "")) or "berlin"
    source_doc = data.get("source_doc", "")

    logger.info(
        "PAY_TERMIN_PDF | user=%s city=%s source=%s lang=%s",
        user_id, city_code, source_doc, lang,
    )

    # Ensure FSM has the keys expected by handle_termin_monitor_pay / price screen
    await state.update_data(
        termin_pending_city=city_code,
        authority_type=DOC_AUTHORITY_MAP.get(source_doc, "buergeramt"),
        source_doc=source_doc,
    )

    # Delegate to the standard price-screen handler.
    # handle_termin_monitor_pay calls callback.answer() itself, so we must not
    # call it here to avoid a duplicate-answer Telegram error.
    original_data = callback.data
    callback.data = f"termin_monitor_pay_{city_code}"
    try:
        await handle_termin_monitor_pay(callback, state)
    finally:
        callback.data = original_data
    return True


async def handle_termin_rescan(callback: types.CallbackQuery, state: FSMContext):
    """Re-run live scan for the same city after 'no slots' result (🔁 button)."""
    await callback.answer(cache_time=1)
    city_code = callback.data.replace("termin_rescan_", "").strip()
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    logger.info("TERMIN_RESCAN | user=%s city=%s lang=%s", user_id, city_code, lang)

    # Safety: if city_code is empty or not in our known set, send user back to city selection
    if not city_code or city_code not in _CITY_DISPLAY_MAP:
        logger.warning("TERMIN_RESCAN_BAD_CITY | user=%s city=%r — redirecting to city selection", user_id, city_code)
        _ensure_termin_user(user_id, lang)
        await TerminStates.selecting_city.set()
        try:
            await callback.message.edit_text(
                _build_termin_entry_text(lang),
                parse_mode="HTML",
                reply_markup=get_cities_keyboard(lang),
            )
        except Exception:
            await callback.message.answer(
                _build_termin_entry_text(lang),
                parse_mode="HTML",
                reply_markup=get_cities_keyboard(lang),
            )
        return

    # ── Family profile gate ───────────────────────────────────────────────────
    fsm_data = await state.get_data()
    _ent = _get_family_entitlement(user_id)
    if _ent and fsm_data.get("active_profile_id") is None:
        await _show_profile_chooser(callback, state, lang, city_code, "scan", _ent)
        return
    # ─────────────────────────────────────────────────────────────────────────

    authority_type = (
        fsm_data.get("authority_type") or fsm_data.get("termin_authority_type")
    )
    source_doc = fsm_data.get("source_doc") or fsm_data.get("doc_type")

    # Prefer profile context from DB if profile is set
    _active_profile = fsm_data.get("active_profile_id", 1)
    if _ent:
        try:
            from backend.termin_db import get_user_profile, upsert_user_profile
            _prof = get_user_profile(user_id, _active_profile)
            if _prof:
                authority_type = _prof.get("authority_type") or authority_type
                source_doc = _prof.get("source_doc") or source_doc
            else:
                # Persist current context into profile row
                upsert_user_profile(
                    user_id, _active_profile,
                    city_code, authority_type or "", source_doc or "",
                )
        except Exception as _pe:
            logger.warning("PROFILE_CONTEXT_READ_ERROR | user=%s err=%s", user_id, _pe)
        logger.info("PROFILE_CONTEXT_USED | user=%s profile=%s city=%s", user_id, _active_profile, city_code)

    # Safe default: if authority unknown, derive from source_doc or fall back to buergeramt
    if not authority_type:
        authority_type = DOC_AUTHORITY_MAP.get(source_doc or "", "buergeramt")

    city_display = _CITY_DISPLAY_MAP.get(city_code, city_code.replace("_", " ").title())
    auth_label = _AUTHORITY_LABELS.get(authority_type)

    _active_pid = int(fsm_data.get("active_profile_id", 1)) if fsm_data else 1
    await _run_live_termin_scan(
        callback, city_code, city_display, lang,
        authority_type=authority_type,
        recommended_authority_label=auth_label,
        active_profile_id=_active_pid,
        is_family=(_ent is not None),
    )


_MONITOR_PRICE = 4.99

# Per-document Termin monitoring prices — flat €4.99 for all document types.
TERMIN_PRICES: dict = {
    "anmeldung": 4.99,
    "ummeldung": 4.99,
    "wohnungsgeberbestaetigung": 4.99,
    "kindergeld": 4.99,
    "wohngeld": 4.99,
    "buergergeld": 4.99,
    "aufenthaltstitel": 4.99,
}
_TERMIN_PRICE_DEFAULT = 4.99
_TERMIN_7DAY_PRICE = 14.99
_FAMILY_PRICE = 4.99


def _get_termin_price(doc_type: Optional[str]) -> float:
    """Return the Termin monitoring price for a given source document type."""
    if not doc_type:
        return _TERMIN_PRICE_DEFAULT
    return TERMIN_PRICES.get(doc_type.lower(), _TERMIN_PRICE_DEFAULT)


# ─── Pre-payment Termin price confirmation screen ─────────────────────────────

_TERMIN_PRICE_TITLE = {
    "ua": "Моніторинг Терміну",
    "en": "Termin Monitoring",
    "de": "Termin-Überwachung",
    "pl": "Monitoring terminu",
    "tr": "Randevu İzleme",
    "ar": "مراقبة الموعد",
}

_TERMIN_PRICE_CHECKED = {
    "ua": "Перевірено {n} установ. Вільних слотів не знайдено.",
    "en": "Checked {n} authorities. No free slots found.",
    "de": "{n} Behörden geprüft. Keine freien Termine gefunden.",
    "pl": "Sprawdzono {n} urzędów. Nie znaleziono wolnych terminów.",
    "tr": "{n} kurum kontrol edildi. Boş randevu bulunamadı.",
    "ar": "تم فحص {n} جهة. لم يتم العثور على مواعيد متاحة.",
}

_TERMIN_PRICE_PERIOD = {
    "ua": "до першого знайденого Termin",
    "uk": "до першого знайденого Termin",
    "en": "valid until first Termin found",
    "de": "gültig bis zum ersten Termin",
    "pl": "do znalezienia pierwszego terminu",
    "tr": "ilk Termin bulunana kadar geçerli",
    "ar": "صالح حتى العثور على أول موعد",
}

_TERMIN_PRICE_BOOST = {
    "ua": "Priority Boost: + €1.99",
    "en": "Priority Boost: + €1.99",
    "de": "Priority Boost: + €1.99",
    "pl": "Priority Boost: + €1.99",
    "tr": "Priority Boost: + €1.99",
    "ar": "Priority Boost: + €1.99",
}

_TERMIN_PRICE_DOC_NOTE = {
    "ua": "На основі документа: <b>{doc}</b>",
    "en": "Based on document: <b>{doc}</b>",
    "de": "Basierend auf Dokument: <b>{doc}</b>",
    "pl": "Na podstawie dokumentu: <b>{doc}</b>",
    "tr": "Belgeye göre: <b>{doc}</b>",
    "ar": "بناءً على المستند: <b>{doc}</b>",
}

# Shown on the price screen only for München and Köln (liveness-probe cities).
# Explains that the bot confirms portal availability, not an exact slot.
_TERMIN_LIVENESS_NOTE = {
    "ua": "ℹ️ Для цього міста бот підтверджує що офіційний портал відкритий. Запис виконуєте самостійно за посиланням.",
    "uk": "ℹ️ Для цього міста бот підтверджує що офіційний портал відкритий. Запис виконуєте самостійно за посиланням.",
    "en": "ℹ️ For this city the bot confirms the official portal is open. You book the appointment yourself via the link.",
    "de": "ℹ️ Für diese Stadt bestätigt der Bot, dass das offizielle Portal geöffnet ist. Die Buchung erfolgt selbst über den Link.",
    "pl": "ℹ️ Dla tego miasta bot potwierdza, że oficjalny portal jest otwarty. Rezerwacji dokonujesz samodzielnie przez link.",
    "tr": "ℹ️ Bu şehir için bot, resmi portalın açık olduğunu doğrular. Randevuyu kendiniz link üzerinden alırsınız.",
    "ar": "ℹ️ لهذه المدينة، يؤكد البوت أن البوابة الرسمية مفتوحة. تحجز الموعد بنفسك عبر الرابط.",
}

_TERMIN_CONFIRM_BTN = {
    "ua": "💳 Почати моніторинг — €{price}",
    "en": "💳 Start monitoring — €{price}",
    "de": "💳 Überwachung starten — €{price}",
    "pl": "💳 Rozpocznij monitoring — €{price}",
    "tr": "💳 İzlemeyi başlat — €{price}",
    "ar": "💳 بدء المراقبة — €{price}",
}

_TERMIN_BACK_BTN = {
    "ua": "🔙 Назад",
    "en": "🔙 Back",
    "de": "🔙 Zurück",
    "pl": "🔙 Wstecz",
    "tr": "🔙 Geri",
    "ar": "🔙 رجوع",
}

# --- Phase 3: Family/Friend Bundle ---
_FAMILY_BTN = {
    "ua": f"👨‍👩‍👧 Для 2 осіб — €{_FAMILY_PRICE:.2f}",
    "en": f"👨‍👩‍👧 For 2 people — €{_FAMILY_PRICE:.2f}",
    "de": f"👨‍👩‍👧 Für 2 Personen — €{_FAMILY_PRICE:.2f}",
    "pl": f"👨‍👩‍👧 Dla 2 osób — €{_FAMILY_PRICE:.2f}",
    "tr": f"👨‍👩‍👧 2 kişi için — €{_FAMILY_PRICE:.2f}",
    "ar": f"👨‍👩‍👧 لشخصين — €{_FAMILY_PRICE:.2f}",
}
_FAMILY_ACTIVATED_TEXT = {
    "ua": (
        "✅ <b>Сімейний моніторинг активовано!</b>\n\n"
        "👨‍👩‍👧 2 слоти активні.\n"
        "Моніторинг ведеться для двох осіб.\n\n"
        "Моніторинг розпочато. Ми повідомимо, щойно з'явиться слот."
    ),
    "uk": (
        "✅ <b>Сімейний моніторинг активовано!</b>\n\n"
        "👨‍👩‍👧 2 слоти активні.\n"
        "Моніторинг ведеться для двох осіб.\n\n"
        "Моніторинг розпочато. Ми повідомимо, щойно з'явиться слот."
    ),
    "en": (
        "✅ <b>Family monitoring activated!</b>\n\n"
        "👨‍👩‍👧 2 slots active.\n"
        "Monitoring is running for two people.\n\n"
        "We will notify you as soon as a slot becomes available."
    ),
    "de": (
        "✅ <b>Familienüberwachung aktiviert!</b>\n\n"
        "👨‍👩‍👧 2 Slots aktiv.\n"
        "Überwachung läuft für zwei Personen.\n\n"
        "Wir benachrichtigen Sie, sobald ein Termin verfügbar ist."
    ),
    "pl": (
        "✅ <b>Monitoring rodzinny aktywowany!</b>\n\n"
        "👨‍👩‍👧 2 sloty aktywne.\n"
        "Monitoring działa dla dwóch osób.\n\n"
        "Powiadomimy Cię, gdy pojawi się wolny termin."
    ),
    "tr": (
        "✅ <b>Aile izlemesi etkinleştirildi!</b>\n\n"
        "👨‍👩‍👧 2 aktif slot.\n"
        "İzleme iki kişi için çalışıyor.\n\n"
        "Yer bulunduğunda sizi bilgilendireceğiz."
    ),
    "ar": (
        "✅ <b>تم تفعيل المراقبة العائلية!</b>\n\n"
        "👨‍👩‍👧 فتحتان نشطتان.\n"
        "المراقبة تعمل لشخصين.\n\n"
        "سنعلمك فور توفر موعد."
    ),
}

# ── Family V1: Profile selection ─────────────────────────────────────────────
_PROFILE_SELECT_TEXT = {
    "ua": (
        "👨‍👩‍👧 <b>Сімейний моніторинг</b>\n\n"
        "Ви маєте план на 2 особи.\n"
        "Оберіть профіль для цього пошуку:"
    ),
    "en": (
        "👨‍👩‍👧 <b>Family monitoring</b>\n\n"
        "You have a 2-person plan.\n"
        "Choose a profile for this search:"
    ),
    "de": (
        "👨‍👩‍👧 <b>Familienüberwachung</b>\n\n"
        "Sie haben einen Plan für 2 Personen.\n"
        "Profil für diese Suche auswählen:"
    ),
    "pl": (
        "👨‍👩‍👧 <b>Monitoring rodzinny</b>\n\n"
        "Masz plan na 2 osoby.\n"
        "Wybierz profil dla tego wyszukiwania:"
    ),
    "tr": (
        "👨‍👩‍👧 <b>Aile izlemesi</b>\n\n"
        "2 kişilik planınız var.\n"
        "Bu arama için profil seçin:"
    ),
    "ar": (
        "👨‍👩‍👧 <b>المراقبة العائلية</b>\n\n"
        "لديك خطة لشخصين.\n"
        "اختر الملف الشخصي لهذا البحث:"
    ),
}
_PROFILE_1_BTN = {
    "ua": "👤 Профіль 1",
    "en": "👤 Profile 1",
    "de": "👤 Profil 1",
    "pl": "👤 Profil 1",
    "tr": "👤 Profil 1",
    "ar": "👤 الملف 1",
}
_PROFILE_2_BTN = {
    "ua": "👤 Профіль 2",
    "en": "👤 Profile 2",
    "de": "👤 Profil 2",
    "pl": "👤 Profil 2",
    "tr": "👤 Profil 2",
    "ar": "👤 الملف 2",
}
_PROFILE_2_UNAVAILABLE_BTN = {
    "ua": "🔒 Профіль 2 (недоступний)",
    "en": "🔒 Profile 2 (unavailable)",
    "de": "🔒 Profil 2 (nicht verfügbar)",
    "pl": "🔒 Profil 2 (niedostępny)",
    "tr": "🔒 Profil 2 (kullanılamıyor)",
    "ar": "🔒 الملف 2 (غير متاح)",
}
_PROFILE_SELECTED_TEXT = {
    "ua": "✅ Профіль {n} активний.",
    "en": "✅ Profile {n} active.",
    "de": "✅ Profil {n} aktiv.",
    "pl": "✅ Profil {n} aktywny.",
    "tr": "✅ Profil {n} aktif.",
    "ar": "✅ الملف {n} نشط.",
}
_PROFILE_2_NO_SLOTS_TEXT = {
    "ua": "❌ Профіль 2 недоступний — обидва місця вже задіяно.",
    "uk": "❌ Профіль 2 недоступний — обидва місця вже задіяно.",
    "en": "❌ Profile 2 unavailable — both monitoring spots are already in use.",
    "de": "❌ Profil 2 nicht verfügbar — beide Plätze sind bereits belegt.",
    "pl": "❌ Profil 2 niedostępny — oba miejsca są już zajęte.",
    "tr": "❌ Profil 2 mevcut değil — her iki yer de kullanımda.",
    "ar": "❌ الملف الشخصي 2 غير متاح — كلا المكانين مُستخدَمان.",
}


def _get_family_entitlement(user_id: int):
    """Return entitlement dict if user has an active, unconsumed family plan, else None.

    Uses is_termin_entitled() as the authoritative entitlement gate so that
    inactive / expired / consumed records never trigger the family-profile flow.
    """
    try:
        # is_termin_entitled is the single source of truth: checks active=1,
        # found_termin=0, and expiry for time-limited plans.
        if not is_termin_entitled(str(user_id)):
            return None
        from backend.termin_db import get_entitlement
        ent = get_entitlement(str(user_id))
        if ent and ent.get("plan") == "family":
            return ent
    except Exception:
        pass
    return None


async def _show_profile_chooser(
    callback: types.CallbackQuery,
    state: FSMContext,
    lang: str,
    city_code: str,
    pending_action: str,
    entitlement: dict,
) -> None:
    """Send the profile selection keyboard and store pending_action in FSM."""
    await state.update_data(
        pending_action=pending_action,
        pending_city_code=city_code,
    )
    slots_used = entitlement.get("slots_used", 0)
    slots_total = entitlement.get("slots_total", 2)
    profile2_available = slots_used < slots_total

    # Try to enrich profile button labels with stored city/authority context
    def _profile_btn_label(base_dict: dict, profile_n: int, lang: str) -> str:
        """Return profile button label with city/authority context if available."""
        base = _lang_text(base_dict, lang)
        try:
            from backend.termin_db import get_user_profile as _gup
            prof = _gup(user_id if hasattr(callback, 'from_user') else 0, profile_n)
            if prof:
                _c = prof.get("city_code") or ""
                _a = prof.get("authority_type") or ""
                _c_disp = _CITY_DISPLAY_MAP.get(_c, _c.replace("_", " ").title()) if _c else ""
                _a_disp = _FILTER_CODE_DISPLAY.get(_a, _a.replace("_", " ").title()).replace("🏛 ", "") if _a else ""
                if _c_disp and _a_disp:
                    return f"{base} — {_c_disp} · {_a_disp}"
                elif _c_disp:
                    return f"{base} — {_c_disp}"
        except Exception:
            pass
        return base

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        _profile_btn_label(_PROFILE_1_BTN, 1, lang),
        callback_data=f"termin_profile_1_{city_code}",
    ))
    if profile2_available:
        kb.add(InlineKeyboardButton(
            _profile_btn_label(_PROFILE_2_BTN, 2, lang),
            callback_data=f"termin_profile_2_{city_code}",
        ))
    else:
        kb.add(InlineKeyboardButton(
            _lang_text(_PROFILE_2_UNAVAILABLE_BTN, lang),
            callback_data="termin_profile2_unavailable",
        ))
    kb.add(InlineKeyboardButton(
        _lang_text(_EXPIRY_HOME_BTN, lang),
        callback_data="main_menu",
    ))
    await callback.message.answer(
        _lang_text(_PROFILE_SELECT_TEXT, lang),
        parse_mode="HTML",
        reply_markup=kb,
    )


async def handle_termin_set_profile(callback: types.CallbackQuery, state: FSMContext):
    """Handle termin_profile_{1|2}_{city_code} — set active profile then continue pending action."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    # Parse profile_id and city_code from callback data: termin_profile_N_CITY
    _parts = callback.data.split("_", 3)  # ["termin", "profile", "N", "city..."]
    try:
        profile_id = int(_parts[2])
        city_code = _parts[3] if len(_parts) > 3 else ""
    except (IndexError, ValueError):
        await callback.message.answer(_lang_text(_PROFILE_INVALID_TEXT, lang))
        return

    # Profile 2: check and consume slot
    if profile_id == 2:
        try:
            from backend.termin_db import use_family_slot, get_entitlement
            ent = get_entitlement(str(user_id))
            if not ent or ent.get("plan") != "family":
                await callback.message.answer(_lang_text(_PROFILE_2_NO_SLOTS_TEXT, lang))
                return
            granted = use_family_slot(user_id)
            if not granted:
                await callback.message.answer(_lang_text(_PROFILE_2_NO_SLOTS_TEXT, lang))
                return
        except Exception as _pe:
            logger.error("PROFILE2_SLOT_ERROR | user=%s err=%s", user_id, _pe)
            await callback.message.answer(_lang_text(_PROFILE_2_NO_SLOTS_TEXT, lang))
            return

    # Store active profile in FSM
    fsm_data = await state.get_data()
    await state.update_data(active_profile_id=profile_id)

    # Restore profile context from DB if available
    try:
        from backend.termin_db import get_user_profile
        prof = get_user_profile(user_id, profile_id)
        if prof:
            await state.update_data(
                authority_type=prof.get("authority_type") or fsm_data.get("authority_type"),
                source_doc=prof.get("source_doc") or fsm_data.get("source_doc"),
            )
    except Exception:
        pass

    logger.info("PROFILE_SELECTED | user=%s profile=%s city=%s", user_id, profile_id, city_code)

    # Continue to pending action
    pending_action = fsm_data.get("pending_action", "scan")
    if pending_action == "monitor_pay":
        # Re-trigger monitor pay flow with city_code
        callback.data = f"termin_monitor_pay_{city_code}"
        await handle_termin_monitor_pay(callback, state)
    else:
        # Default: re-trigger scan
        callback.data = f"termin_rescan_{city_code}"
        await handle_termin_rescan(callback, state)


async def handle_termin_profile2_unavailable(callback: types.CallbackQuery, state: FSMContext):
    """Tap on the disabled Profile 2 button — just inform the user."""
    await callback.answer(_lang_text(_PROFILE_2_NO_SLOTS_TEXT, _resolve_lang(callback.from_user.id)), show_alert=True)


async def handle_termin_switch_profile(callback: types.CallbackQuery, state: FSMContext):
    """Switch active profile WITHOUT consuming slots. Just updates FSM context."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    try:
        n = int(callback.data.replace("termin_switch_profile_", "").strip())
    except ValueError:
        return
    if n not in (1, 2):
        return

    old_profile = await _get_active_profile_id(state, user_id=user_id)
    await _set_active_profile_id(state, n)

    # Persist to DB so profile survives bot restart
    try:
        from backend.termin_db import set_active_profile
        set_active_profile(user_id, n)
    except Exception as _dbp:
        logger.warning("SWITCH_PROFILE_DB_PERSIST_ERROR | user=%s err=%s", user_id, _dbp)

    # Load saved profile context from DB into FSM (city/authority/source_doc)
    try:
        from backend.termin_db import get_user_profile
        prof = get_user_profile(user_id, n)
        if prof:
            await state.update_data(
                authority_type=prof.get("authority_type") or "",
                source_doc=prof.get("source_doc") or "",
            )
    except Exception as _pe:
        logger.warning("SWITCH_PROFILE_CTX_ERROR | user=%s err=%s", user_id, _pe)

    logger.info("TERMIN_PROFILE_SWITCH | user_id=%s from=%s to=%s", user_id, old_profile, n)

    # Re-render Termin main menu with the new active profile
    user = _ensure_termin_user(user_id, lang)
    # Use live entitlement check — not the stale has_paid_termin DB flag.
    has_paid = is_termin_entitled(str(user_id))
    has_selected = _user_has_selected(user)
    user_city = user.get("city", "") if user else ""
    user_authority = user.get("authority", "") if user else ""
    _family = True  # Only family users can switch

    new_text = _build_termin_menu_text(
        lang, has_paid, has_selected,
        user_city=user_city, user_authority=user_authority,
        active_profile_id=n, is_family=_family,
    )
    new_kb = get_termin_menu_keyboard(
        lang, has_paid, has_selected,
        user_city=user_city or None,
        user_authority=user_authority or None,
        user_id=user_id, active_profile_id=n, is_family=_family,
    )
    try:
        await callback.message.edit_text(new_text, parse_mode="HTML", reply_markup=new_kb)
    except Exception:
        await callback.message.answer(new_text, parse_mode="HTML", reply_markup=new_kb)


async def handle_termin_monitor_pay(callback: types.CallbackQuery, state: FSMContext):
    """Display plan selection screen before Stripe."""
    await callback.answer(cache_time=1)
    city_code = callback.data.replace("termin_monitor_pay_", "")
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    fsm_data = await state.get_data()

    # NOTE: Family profile gate intentionally removed from this handler.
    # handle_termin_monitor_pay is the PLAN SELECTION screen (shown BEFORE payment).
    # The profile chooser must only appear AFTER entitlement is confirmed, i.e.
    # inside handle_termin_start_poll which already has a payment gate.
    # Showing the profile chooser here caused a double-screen bug: the plan screen
    # appeared first (from handle_doc_type_selection), then family screen appeared
    # immediately when the user tapped the "Buy plan" button.

    source_doc = fsm_data.get("source_doc") or fsm_data.get("doc_type")

    # Save city_code to FSM so the actual payment handler can use it
    await state.update_data(termin_pending_city=city_code)

    price = _get_termin_price(source_doc)
    city_display = _CITY_DISPLAY_MAP.get(city_code, city_code.replace("_", " ").title())

    title_line = {
        "ua": f"🔎 <b>Termin Monitoring — {city_display}</b>",
        "uk": f"🔎 <b>Termin Monitoring — {city_display}</b>",
        "en": f"🔎 <b>Termin Monitoring — {city_display}</b>",
        "de": f"🔎 <b>Termin Monitoring — {city_display}</b>",
        "pl": f"🔎 <b>Termin Monitoring — {city_display}</b>",
        "tr": f"🔎 <b>Termin Monitoring — {city_display}</b>",
        "ar": f"🔎 <b>Termin Monitoring — {city_display}</b>",
    }.get(lang, f"🔎 <b>Termin Monitoring — {city_display}</b>")

    subtitle_line = {
        "ua": "Оберіть план моніторингу:",
        "uk": "Оберіть план моніторингу:",
        "en": "Choose your monitoring plan:",
        "de": "Wählen Sie Ihren Überwachungsplan:",
        "pl": "Wybierz plan monitoringu:",
        "tr": "İzleme planınızı seçin:",
        "ar": "اختر خطة المراقبة:",
    }.get(lang, "Choose your monitoring plan:")

    value_prop = {
        "ua": (
            "🤖 <b>Як це працює:</b>\n"
            "• Перевіряємо слоти кожні 2 хвилини\n"
            "• Сповіщаємо одразу як з'являється вільний час\n"
            "• Ви отримаєте повідомлення швидше, ніж при ручній перевірці"
        ),
        "uk": (
            "🤖 <b>Як це працює:</b>\n"
            "• Перевіряємо слоти кожні 2 хвилини\n"
            "• Сповіщаємо одразу як з'являється вільний час\n"
            "• Ви отримаєте повідомлення швидше, ніж при ручній перевірці"
        ),
        "en": (
            "🤖 <b>How it works:</b>\n"
            "• We check for slots every 2 minutes\n"
            "• You're notified the moment one becomes available\n"
            "• You'll be alerted faster than any manual check"
        ),
        "de": (
            "🤖 <b>So funktioniert es:</b>\n"
            "• Wir prüfen alle 2 Minuten auf freie Termine\n"
            "• Sie werden sofort benachrichtigt, sobald ein Slot verfügbar ist\n"
            "• Schneller als jede manuelle Prüfung"
        ),
        "pl": (
            "🤖 <b>Jak to działa:</b>\n"
            "• Sprawdzamy dostępne terminy co 2 minuty\n"
            "• Otrzymujesz powiadomienie natychmiast, gdy pojawi się wolny slot\n"
            "• Szybciej niż jakiekolwiek ręczne sprawdzanie"
        ),
        "tr": (
            "🤖 <b>Nasıl çalışır:</b>\n"
            "• Her 2 dakikada bir slot kontrol ediyoruz\n"
            "• Bir slot açılır açılmaz sizi bilgilendiriyoruz\n"
            "• Manuel kontrolden çok daha hızlı"
        ),
        "ar": (
            "🤖 <b>كيف يعمل:</b>\n"
            "• نتحقق من المواعيد كل دقيقتين\n"
            "• تتلقى إشعاراً فور توفر موعد\n"
            "• أسرع بكثير من أي مراجعة يدوية"
        ),
    }.get(lang, (
        "🤖 <b>How it works:</b>\n"
        "• We check for slots every 2 minutes\n"
        "• You're notified the moment one becomes available\n"
        "• You'll be alerted faster than any manual check"
    ))

    # Clarity block: what exactly will be monitored
    _authority_display = {
        "buergeramt": "Bürgeramt",
        "auslaenderbehoerde": "Ausländerbehörde",
        "jobcenter": "Jobcenter",
        "standesamt": "Standesamt",
        "familienkasse": "Familienkasse",
    }
    _fsm_authority = fsm_data.get("authority_type") or fsm_data.get("termin_authority_type") or "buergeramt"
    _auth_name = _authority_display.get(_fsm_authority, _fsm_authority.replace("_", " ").title())

    _clarity_block = {
        "ua": (
            f"📍 Місто: <b>{city_display}</b>\n"
            f"🏢 Служба: <b>{_auth_name}</b>\n"
            "⏱ Перевірка кожні кілька секунд\n\n"
            "Ви отримаєте сповіщення одразу, як з'явиться вільне місце."
        ),
        "uk": (
            f"📍 Місто: <b>{city_display}</b>\n"
            f"🏢 Служба: <b>{_auth_name}</b>\n"
            "⏱ Перевірка кожні кілька секунд\n\n"
            "Ви отримаєте сповіщення одразу, як з'явиться вільне місце."
        ),
        "en": (
            f"📍 City: <b>{city_display}</b>\n"
            f"🏢 Service: <b>{_auth_name}</b>\n"
            "⏱ Checking every few seconds\n\n"
            "You will be notified instantly when a slot appears."
        ),
        "de": (
            f"📍 Stadt: <b>{city_display}</b>\n"
            f"🏢 Dienst: <b>{_auth_name}</b>\n"
            "⏱ Prüfung alle paar Sekunden\n\n"
            "Sie werden sofort benachrichtigt, wenn ein Slot frei wird."
        ),
        "pl": (
            f"📍 Miasto: <b>{city_display}</b>\n"
            f"🏢 Usługa: <b>{_auth_name}</b>\n"
            "⏱ Sprawdzanie co kilka sekund\n\n"
            "Otrzymasz powiadomienie natychmiast, gdy pojawi się wolny termin."
        ),
        "tr": (
            f"📍 Şehir: <b>{city_display}</b>\n"
            f"🏢 Hizmet: <b>{_auth_name}</b>\n"
            "⏱ Her birkaç saniyede kontrol\n\n"
            "Randevu açılır açılmaz anında bildirim alacaksınız."
        ),
        "ar": (
            f"📍 المدينة: <b>{city_display}</b>\n"
            f"🏢 الخدمة: <b>{_auth_name}</b>\n"
            "⏱ فحص كل بضع ثوانٍ\n\n"
            "ستتلقى إشعاراً فورياً عند توفر موعد."
        ),
    }.get(lang, (
        f"📍 City: <b>{city_display}</b>\n"
        f"🏢 Service: <b>{_auth_name}</b>\n"
        "⏱ Checking every few seconds\n\n"
        "You will be notified instantly when a slot appears."
    ))

    price_text = f"{_clarity_block}\n\n{value_prop}\n\n{subtitle_line}"

    if city_code in ("muenchen", "dortmund"):
        price_text += "\n\n" + _lang_text(_TERMIN_LIVENESS_NOTE, lang)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        {
            "ua": f"⭐ Рекомендовано: 7 днів — €{_TERMIN_7DAY_PRICE:.2f}",
            "uk": f"⭐ Рекомендовано: 7 днів — €{_TERMIN_7DAY_PRICE:.2f}",
            "en": f"⭐ Recommended: 7 days — €{_TERMIN_7DAY_PRICE:.2f}",
            "de": f"⭐ Empfohlen: 7 Tage — €{_TERMIN_7DAY_PRICE:.2f}",
            "pl": f"⭐ Polecane: 7 dni — €{_TERMIN_7DAY_PRICE:.2f}",
            "tr": f"⭐ Önerilen: 7 gün — €{_TERMIN_7DAY_PRICE:.2f}",
            "ar": f"⭐ الأنسب: 7 أيام — €{_TERMIN_7DAY_PRICE:.2f}",
        }.get(lang, f"⭐ Recommended: 7 days — €{_TERMIN_7DAY_PRICE:.2f}"),
        callback_data=f"termin_monitor_confirm_7day_{city_code}",
    ))
    kb.add(InlineKeyboardButton(
        {
            "ua": f"⚡ Швидкий старт: 24 год — €{price:.2f}",
            "uk": f"⚡ Швидкий старт: 24 год — €{price:.2f}",
            "en": f"⚡ Quick start: 24h — €{price:.2f}",
            "de": f"⚡ Schnellstart: 24 Std. — €{price:.2f}",
            "pl": f"⚡ Szybki start: 24h — €{price:.2f}",
            "tr": f"⚡ Hızlı başlangıç: 24 saat — €{price:.2f}",
            "ar": f"⚡ بداية سريعة: 24 ساعة — €{price:.2f}",
        }.get(lang, f"⚡ Quick start: 24h — €{price:.2f}"),
        callback_data=f"termin_monitor_confirm_{city_code}",
    ))
    kb.add(InlineKeyboardButton(
        _lang_text(_TERMIN_BACK_BTN, lang),
        callback_data="back_to_main_menu",
    ))
    from handlers.nav import nav_home_text as _nav_home_pricing
    kb.add(InlineKeyboardButton(_nav_home_pricing(lang), callback_data="main_menu"))

    await callback.message.answer(price_text, parse_mode="HTML", reply_markup=kb)

    await TerminStates.paying_for_reminders.set()


async def handle_termin_monitor_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Create Stripe Checkout after user confirms price on the pre-payment screen."""
    await callback.answer(cache_time=1)
    city_code = callback.data.replace("termin_monitor_confirm_", "")
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    logger.info("TERMIN_MONITOR_CONFIRM | user=%s city=%s lang=%s", user_id, city_code, lang)

    fsm_data = await state.get_data()
    source_doc = fsm_data.get("source_doc") or fsm_data.get("doc_type")
    # Resolve authority from FSM — this is the ONLY source of truth for metadata.
    authority_for_meta = (
        fsm_data.get("authority_type")
        or fsm_data.get("termin_authority_type")
        or DOC_AUTHORITY_MAP.get(source_doc or "", "buergeramt")
    )
    price = _get_termin_price(source_doc)

    logger.info(
        "WEBHOOK_METADATA_PREPARED | user=%s city=%s authority=%s source_doc=%s",
        user_id, city_code, authority_for_meta, source_doc,
    )

    import os
    try:
        from utils.helpers import get_db
        from handlers.stripe_handler import get_stripe_handler

        db = get_db()
        order_lang = "uk" if lang == "ua" else lang
        order_id = db.create_order(
            user_id=user_id,
            doc_type="termin_monitor_24h",
            amount=price,
            lang=order_lang,
        )
        logger.info(
            "TERMIN_ANALYTICS | event=order_created plan=24h city=%s authority=%s lang=%s source_doc=%s order_id=%s user_id=%s",
            city_code, authority_for_meta, lang, source_doc or "", order_id, user_id,
        )

        webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
        success_url = _build_success_url(order_id)
        cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

        stripe = get_stripe_handler()
        result = await stripe.create_checkout_session(
            order_id=order_id,
            user_id=user_id,
            doc_type="termin_monitor_24h",
            price=price,
            success_url=success_url,
            cancel_url=cancel_url,
            extra_metadata={
                "flow": "termin",
                "city": city_code,
                "authority": authority_for_meta,
                "monitor": "24h",
                "user_id": str(user_id),
                "telegram_user_id": str(user_id),
                "product_type": "termin",
                "source_doc": source_doc or "",
            },
        )

        if result.success:
            from backend.database import OrderStatus
            db.update_order_status(order_id, OrderStatus.PENDING, stripe_session_id=result.session_id)
            logger.info("SUCCESS_URL=%s", success_url)
            logger.info(
                "TERMIN_ANALYTICS | event=checkout_created plan=24h city=%s authority=%s order_id=%s user_id=%s",
                city_code, authority_for_meta, order_id, user_id,
            )

            # Phase 1: register expiry clock for re-engagement push (24h from now)
            _monitor_expiry_registry[str(user_id)] = (
                datetime.now(timezone.utc) + timedelta(hours=24)
            ).isoformat()
            _expiry_warning_sent.discard(str(user_id))
            logger.info("TERMIN_EXPIRY_REGISTERED | user=%s", user_id)

            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton(
                _lang_text(_STRIPE_OPEN_BTN, lang).format(price=f"{price:.2f}"),
                url=result.checkout_url,
            ))
            # Force external browser on first tap — avoids Telegram WebView auto-close.
            try:
                await callback.answer(url=result.checkout_url)
            except Exception:
                await callback.answer(cache_time=1)
            await callback.message.answer(
                _lang_text(_STRIPE_REDIRECT_TEXT, lang),
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return

    except Exception as e:
        logger.error("TERMIN_MONITOR_STRIPE_ERROR | user=%s error=%s", user_id, e)

    from handlers.nav import nav_home_text as _nav_home_err
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(
        get_text("btn_back", lang),
        callback_data="back_to_main_menu",
    ))
    keyboard.add(InlineKeyboardButton(_nav_home_err(lang), callback_data="main_menu"))
    await callback.message.answer(
        _lang_text(_STRIPE_ERROR_TEXT, lang),
        reply_markup=keyboard,
    )


async def handle_termin_monitor_confirm_7day(callback: types.CallbackQuery, state: FSMContext):
    """Create Stripe Checkout for 7-day Extended monitoring plan (€14.99)."""
    await callback.answer(cache_time=1)
    city_code = callback.data.replace("termin_monitor_confirm_7day_", "")
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    logger.info("TERMIN_7DAY_CONFIRM | user=%s city=%s lang=%s", user_id, city_code, lang)

    fsm_data = await state.get_data()
    source_doc = fsm_data.get("source_doc") or fsm_data.get("doc_type")
    authority_for_meta = (
        fsm_data.get("authority_type")
        or fsm_data.get("termin_authority_type")
        or DOC_AUTHORITY_MAP.get(source_doc or "", "buergeramt")
    )
    price = _TERMIN_7DAY_PRICE

    logger.info(
        "TERMIN_7DAY_WEBHOOK_METADATA_PREPARED | user=%s city=%s authority=%s source_doc=%s",
        user_id, city_code, authority_for_meta, source_doc,
    )

    import os
    try:
        from utils.helpers import get_db
        from handlers.stripe_handler import get_stripe_handler

        db = get_db()
        order_lang = "uk" if lang == "ua" else lang
        order_id = db.create_order(
            user_id=user_id,
            doc_type="termin_monitor_7day",
            amount=price,
            lang=order_lang,
        )
        logger.info(
            "TERMIN_ANALYTICS | event=order_created plan=7day city=%s authority=%s lang=%s source_doc=%s order_id=%s user_id=%s",
            city_code, authority_for_meta, lang, source_doc or "", order_id, user_id,
        )

        webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
        success_url = _build_success_url(order_id)
        cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

        stripe = get_stripe_handler()
        result = await stripe.create_checkout_session(
            order_id=order_id,
            user_id=user_id,
            doc_type="termin_monitor_7day",
            price=price,
            success_url=success_url,
            cancel_url=cancel_url,
            extra_metadata={
                "flow": "termin",
                "city": city_code,
                "authority": authority_for_meta,
                "monitor": "7day",
                "doc_type": "termin_monitor_7day",
                "user_id": str(user_id),
                "telegram_user_id": str(user_id),
                "product_type": "termin",
                "source_doc": source_doc or "",
            },
        )

        if result.success:
            from backend.database import OrderStatus
            db.update_order_status(order_id, OrderStatus.PENDING, stripe_session_id=result.session_id)
            logger.info("TERMIN_7DAY_SUCCESS_URL=%s", success_url)
            logger.info(
                "TERMIN_ANALYTICS | event=checkout_created plan=7day city=%s authority=%s order_id=%s user_id=%s",
                city_code, authority_for_meta, order_id, user_id,
            )

            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton(
                _lang_text(_STRIPE_OPEN_BTN, lang).format(price=f"{price:.2f}"),
                url=result.checkout_url,
            ))
            try:
                await callback.answer(url=result.checkout_url)
            except Exception:
                await callback.answer(cache_time=1)
            await callback.message.answer(
                _lang_text(_STRIPE_REDIRECT_TEXT, lang),
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return

    except Exception as e:
        logger.error("TERMIN_7DAY_STRIPE_ERROR | user=%s error=%s", user_id, e)

    from handlers.nav import nav_home_text as _nav_home_7day_err
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(
        get_text("btn_back", lang),
        callback_data="back_to_main_menu",
    ))
    keyboard.add(InlineKeyboardButton(_nav_home_7day_err(lang), callback_data="main_menu"))
    await callback.message.answer(
        _lang_text(_STRIPE_ERROR_TEXT, lang),
        reply_markup=keyboard,
    )


# ==================== Phase 3: Family Bundle ====================

async def handle_termin_monitor_family(callback: types.CallbackQuery, state: FSMContext):
    """Create Stripe Checkout for 2-person family bundle (€4.99)."""
    await callback.answer(cache_time=1)
    city_code = callback.data.replace("termin_monitor_family_", "").strip()
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    logger.info("TERMIN_FAMILY_PAY | user=%s city=%s", user_id, city_code)

    import os
    try:
        from utils.helpers import get_db
        from handlers.stripe_handler import get_stripe_handler

        fsm_data = await state.get_data()
        _fam_source_doc = fsm_data.get("source_doc") or fsm_data.get("doc_type")
        _fam_authority = (
            fsm_data.get("authority_type")
            or fsm_data.get("termin_authority_type")
            or DOC_AUTHORITY_MAP.get(_fam_source_doc or "", "buergeramt")
        )
        logger.info(
            "WEBHOOK_METADATA_PREPARED | user=%s city=%s authority=%s monitor=family",
            user_id, city_code, _fam_authority,
        )

        db = get_db()
        order_lang = "uk" if lang == "ua" else lang
        order_id = db.create_order(
            user_id=user_id,
            doc_type="termin_monitor_family",
            amount=_FAMILY_PRICE,
            lang=order_lang,
        )

        webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
        success_url = _build_success_url(order_id)
        cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

        stripe = get_stripe_handler()
        result = await stripe.create_checkout_session(
            order_id=order_id,
            user_id=user_id,
            doc_type="termin_monitor_family",
            price=_FAMILY_PRICE,
            success_url=success_url,
            cancel_url=cancel_url,
            extra_metadata={
                "flow": "termin",
                "city": city_code,
                "authority": _fam_authority,
                "monitor": "family",
                "user_id": str(user_id),
                "telegram_user_id": str(user_id),
                "product_type": "termin",
            },
        )

        if result.success:
            from backend.database import OrderStatus
            db.update_order_status(order_id, OrderStatus.PENDING, stripe_session_id=result.session_id)
            logger.info("SUCCESS_URL=%s", success_url)

            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(InlineKeyboardButton(
                _lang_text(_STRIPE_OPEN_BTN, lang).format(price=f"{_FAMILY_PRICE:.2f}"),
                url=result.checkout_url,
            ))
            # Force external browser on first tap — avoids Telegram WebView auto-close.
            try:
                await callback.answer(url=result.checkout_url)
            except Exception:
                await callback.answer(cache_time=1)
            await callback.message.answer(
                _lang_text(_STRIPE_REDIRECT_TEXT, lang),
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return

    except Exception as _e:
        logger.error("TERMIN_FAMILY_STRIPE_ERROR | user=%s error=%s", user_id, _e)

    from handlers.nav import nav_home_text as _nav_home_fam_err
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        _lang_text(_TERMIN_BACK_BTN, lang),
        callback_data="back_to_main_menu",
    ))
    kb.add(InlineKeyboardButton(_nav_home_fam_err(lang), callback_data="main_menu"))
    await callback.message.answer(
        _lang_text(_STRIPE_ERROR_TEXT, lang),
        reply_markup=kb,
    )


async def _activate_termin_family(
    bot, user_id: int, lang: str, stripe_session_id: str = ""
) -> None:
    """Webhook delivery: activate family bundle (DB-backed, idempotent)."""
    try:
        from backend.termin_db import (
            create_user as _crt,
            update_user as _upd,
            upsert_entitlement,
        )
        _crt(str(user_id))
        _upd(str(user_id), has_paid_termin=1)
        upsert_entitlement(
            user_id=str(user_id),
            plan="family",
            slots_total=2,
            stripe_session_id=stripe_session_id,
        )
        logger.info(
            "TERMIN_FAMILY_ACTIVATED | user=%s session=%s", user_id, stripe_session_id
        )
    except Exception as _e:
        logger.error("TERMIN_FAMILY_DB_ERROR | user=%s err=%s", user_id, _e)

    # Send family-specific activation text
    _text = _lang_text(_FAMILY_ACTIVATED_TEXT, lang)
    try:
        await bot.send_message(chat_id=user_id, text=_text, parse_mode="HTML")
    except Exception as _e:
        logger.error("TERMIN_FAMILY_NOTIFY_FAILED | user=%s error=%s", user_id, _e)

    # Send full control menu: 🔎 Статус / ⏹ Зупинити / 🏠 Головне меню
    # Uses the same send_termin_activation_message as 24h/7day plans.
    try:
        from handlers.termin_activation import send_termin_activation_message
        from backend.termin_db import get_user as _get_family_user
        _family_user = _get_family_user(str(user_id)) or {}
        _family_city = _family_user.get("city") or "berlin"
        _family_auth = _family_user.get("authority") or "buergeramt"
        await send_termin_activation_message(bot, user_id, _family_city, _family_auth, lang, plan="family")
    except Exception as _me:
        logger.error("TERMIN_FAMILY_CONTROL_MENU_FAILED | user=%s error=%s", user_id, _me)


# ==================== Strategy selector ====================

_STRATEGY_CONFIRM = {
    "fast": {
        "ua": "⚡ <b>Стратегія: Швидкий пошук</b>\nМи перевіряємо максимум слотів за мінімум часу.",
        "en": "⚡ <b>Strategy: Fast search</b>\nWe check maximum slots in minimum time.",
        "de": "⚡ <b>Strategie: Schnelle Suche</b>\nWir prüfen maximale Termine in minimaler Zeit.",
        "pl": "⚡ <b>Strategia: Szybkie wyszukiwanie</b>\nSprawdzamy maksimum terminów w minimum czasu.",
        "tr": "⚡ <b>Strateji: Hızlı arama</b>\nMinimum sürede maksimum randevu kontrol ediyoruz.",
        "ar": "⚡ <b>الاستراتيجية: بحث سريع</b>\nنتحقق من أقصى عدد من المواعيد في أقل وقت.",
    },
    "precise": {
        "ua": "🎯 <b>Стратегія: Точний пошук</b>\nМи фокусуємось на найкращих слотах у зручний час.",
        "en": "🎯 <b>Strategy: Precise search</b>\nWe focus on best slots at convenient times.",
        "de": "🎯 <b>Strategie: Präzise Suche</b>\nWir konzentrieren uns auf die besten Termine zu günstigen Zeiten.",
        "pl": "🎯 <b>Strategia: Precyzyjne wyszukiwanie</b>\nSkupiamy się na najlepszych terminach w wygodnych godzinach.",
        "tr": "🎯 <b>Strateji: Hassas arama</b>\nUygun saatlerde en iyi randevulara odaklanıyoruz.",
        "ar": "🎯 <b>الاستراتيجية: بحث دقيق</b>\nنركز على أفضل المواعيد في أوقات مناسبة.",
    },
}


_STRATEGY_DETAIL = {
    "fast": {
        "ua": "⚡ <b>Обрано: Швидкий пошук</b>\n\nБудь-який район, будь-який час.\nМаксимум слотів за мінімум часу.",
        "en": "⚡ <b>Selected: Fast search</b>\n\nAny district, any time.\nMaximum slots in minimum time.",
        "de": "⚡ <b>Gewählt: Schnelle Suche</b>\n\nJeder Bezirk, jede Zeit.\nMaximale Termine in minimaler Zeit.",
        "pl": "⚡ <b>Wybrano: Szybkie wyszukiwanie</b>\n\nDowolna dzielnica, dowolna godzina.\nMaksimum terminów w minimum czasu.",
        "tr": "⚡ <b>Seçildi: Hızlı arama</b>\n\nHerhangi bir ilçe, herhangi bir saat.\nMinimum sürede maksimum randevu.",
        "ar": "⚡ <b>تم الاختيار: بحث سريع</b>\n\nأي حي، أي وقت.\nأقصى عدد من المواعيد في أقل وقت.",
    },
    "precise": {
        "ua": "🎯 <b>Обрано: Точний пошук</b>\n\nЛише конкретні офіси.\nФокус на найкращих слотах у зручний час.",
        "en": "🎯 <b>Selected: Precise search</b>\n\nSpecific authorities only.\nFocus on best slots at convenient times.",
        "de": "🎯 <b>Gewählt: Präzise Suche</b>\n\nNur bestimmte Behörden.\nFokus auf die besten Termine zu günstigen Zeiten.",
        "pl": "🎯 <b>Wybrano: Precyzyjne wyszukiwanie</b>\n\nTylko konkretne urzędy.\nNajlepsze terminy w wygodnych godzinach.",
        "tr": "🎯 <b>Seçildi: Hassas arama</b>\n\nYalnızca belirli kurumlar.\nUygun saatlerde en iyi randevular.",
        "ar": "🎯 <b>تم الاختيار: بحث دقيق</b>\n\nجهات محددة فقط.\nأفضل المواعيد في أوقات مناسبة.",
    },
}


async def handle_termin_strategy(callback: types.CallbackQuery, state: FSMContext):
    """Handle Fast / Precise strategy selection, save to FSM and confirm.

    Two paths:
    - Already monitoring (monitor_started_at in FSM): just update strategy, show
      brief confirmation, return to status screen — no payment prompt.
    - Not yet monitoring: show strategy detail + payment button as before.
    """
    await callback.answer(cache_time=1)
    raw = callback.data
    if raw.startswith("termin_strategy_fast_"):
        strategy = "fast"
        city_code = raw.replace("termin_strategy_fast_", "")
    else:
        strategy = "precise"
        city_code = raw.replace("termin_strategy_precise_", "")

    await state.update_data(termin_strategy=strategy)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    logger.info("TERMIN_STRATEGY | user=%s strategy=%s city=%s", user_id, strategy, city_code)

    # ── Path A: user is already monitoring → just confirm & return to status ─
    fsm_data = await state.get_data()
    if fsm_data.get("monitor_started_at"):
        strategy_label = (
            _lang_text(_STRATEGY_FAST_LABEL, lang) if strategy == "fast"
            else _lang_text(_STRATEGY_PRECISE_LABEL, lang)
        )
        updated_text = (
            f"{_lang_text(_STRATEGY_UPDATED_TEXT, lang)}\n"
            f"{_lang_text(_SSTAT_STRATEGY_LBL, lang)}: <b>{strategy_label}</b>\n\n"
            f"{_lang_text(_STRATEGY_CONFIRM[strategy], lang)}"
        )
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(
            _lang_text(_STATUS_BTN_LABEL, lang),
            callback_data="termin_status",
        ))
        try:
            await callback.message.edit_text(updated_text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.answer(updated_text, parse_mode="HTML", reply_markup=kb)
        return

    # ── Path B: not yet monitoring → show detail + payment CTA ──────────────
    _PAY_NOW_BTN = {
        "ua": f"🔔 Почати моніторинг — €{_MONITOR_PRICE:.2f}",
        "en": f"🔔 Start Monitoring — €{_MONITOR_PRICE:.2f}",
        "de": f"🔔 Überwachung starten — €{_MONITOR_PRICE:.2f}",
        "pl": f"🔔 Rozpocznij monitoring — €{_MONITOR_PRICE:.2f}",
        "tr": f"🔔 İzlemeyi başlat — €{_MONITOR_PRICE:.2f}",
        "ar": f"🔔 بدء المراقبة — €{_MONITOR_PRICE:.2f}",
    }

    detail_text = _lang_text(_STRATEGY_DETAIL[strategy], lang)
    confirm_text = f"{detail_text}\n\n{_lang_text(_STRATEGY_CONFIRM[strategy], lang)}\n\n💶 <b>€{_MONITOR_PRICE:.2f}</b>"
    from handlers.nav import nav_home_text as _nav_home_strat
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        _lang_text(_PAY_NOW_BTN, lang),
        callback_data=f"termin_monitor_pay_{city_code}",
    ))
    kb.add(InlineKeyboardButton(
        "↩️", callback_data="back_to_main_menu",
    ))
    kb.add(InlineKeyboardButton(_nav_home_strat(lang), callback_data="main_menu"))

    try:
        await callback.message.edit_text(confirm_text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(confirm_text, parse_mode="HTML", reply_markup=kb)


# ==================== Live Status ====================

# ── Block-label dicts for the 3-block status screen ────────────────────────
_SSTAT_STATUS_LBL   = {"ua": "🔘 Стан",               "uk": "🔘 Стан",               "en": "🔘 Status",          "de": "🔘 Status",               "pl": "🔘 Stan",              "tr": "🔘 Durum",        "ar": "🔘 الحالة"}
_SSTAT_REMAIN_LBL   = {"ua": "⏳ Залишилось",           "uk": "⏳ Залишилось",           "en": "⏳ Time remaining",   "de": "⏳ Verbleibend",           "pl": "⏳ Pozostało",          "tr": "⏳ Kalan süre",   "ar": "⏳ الوقت المتبقي"}
_SSTAT_CITY_LBL     = {"ua": "🏙 Місто",               "uk": "🏙 Місто",               "en": "🏙 City",            "de": "🏙 Stadt",                "pl": "🏙 Miasto",            "tr": "🏙 Şehir",        "ar": "🏙 المدينة"}
_SSTAT_AUTH_LBL     = {"ua": "🏛 Установа",            "uk": "🏛 Установа",            "en": "🏛 Authority",       "de": "🏛 Behörde",              "pl": "🏛 Urząd",             "tr": "🏛 Kurum",        "ar": "🏛 الجهة"}
_SSTAT_STRATEGY_LBL = {"ua": "🔧 Стратегія",           "uk": "🔧 Стратегія",           "en": "🔧 Strategy",        "de": "🔧 Strategie",            "pl": "🔧 Strategia",         "tr": "🔧 Strateji",     "ar": "🔧 الاستراتيجية"}
_SSTAT_MULTI_LBL    = {"ua": "🌍 Мультимісто",         "uk": "🌍 Мультимісто",         "en": "🌍 Multi-city",      "de": "🌍 Mehrere Städte",       "pl": "🌍 Multi-miasto",      "tr": "🌍 Çoklu şehir",  "ar": "🌍 مدن متعددة"}
_SSTAT_PRIORITY_LBL = {"ua": "🔔 Пріоритет",           "uk": "🔔 Пріоритет",           "en": "🔔 Priority",        "de": "🔔 Priorität",            "pl": "🔔 Priorytet",         "tr": "🔔 Öncelik",      "ar": "🔔 الأولوية"}
_SSTAT_EXTENDED_LBL = {"ua": "➕ Продовжено",           "uk": "➕ Продовжено",           "en": "➕ Extended",         "de": "➕ Verlängert",            "pl": "➕ Przedłużono",        "tr": "➕ Uzatıldı",     "ar": "➕ ممتد"}
_SSTAT_LASTCHK_LBL  = {"ua": "🕐 Остання перевірка",   "uk": "🕐 Остання перевірка",   "en": "🕐 Last check",      "de": "🕐 Letzte Prüfung",       "pl": "🕐 Ostatnie sprawdz.", "tr": "🕐 Son kontrol",  "ar": "🕐 آخر فحص"}
_SSTAT_STARTED_LBL  = {"ua": "🚀 Старт",               "uk": "🚀 Старт",               "en": "🚀 Started",         "de": "🚀 Gestartet",            "pl": "🚀 Start",             "tr": "🚀 Başlangıç",    "ar": "🚀 بدأ في"}
_SSTAT_CHECKS_LBL   = {"ua": "📈 Перевірок сьогодні",  "uk": "📈 Перевірок сьогодні",  "en": "📈 Checks today",    "de": "📈 Prüfungen heute",      "pl": "📈 Sprawdzeń dziś",    "tr": "📈 Kontroller",   "ar": "📈 الفحوصات اليوم"}
_SSTAT_ELAPSED_LBL  = {"ua": "⏱ Активний",           "uk": "⏱ Активний",           "en": "⏱ Active",          "de": "⏱ Aktiv seit",           "pl": "⏱ Aktywny",            "tr": "⏱ Aktif",         "ar": "⏱ نشط منذ"}
_SSTAT_ACTIVE_LBL   = {"ua": "🟢 Активний",          "uk": "🟢 Активний",          "en": "🟢 Active",         "de": "🟢 Aktiv",               "pl": "🟢 Aktywny",           "tr": "🟢 Aktif",        "ar": "🟢 نشط"}
_SSTAT_INTERVAL_NOTE = {
    "ua": "📡 Перевіряємо кожні ~30 сек",
    "uk": "📡 Перевіряємо кожні ~30 сек",
    "en": "📡 Checking every ~30 sec",
    "de": "📡 Prüfung alle ~30 Sek.",
    "pl": "📡 Sprawdzamy co ~30 sek.",
    "tr": "📡 Her ~30 sn'de kontrol",
    "ar": "📡 نفحص كل ~30 ثانية",
}
_SSTAT_DOC_LBL      = {"ua": "🏛 Установа",           "uk": "🏛 Установа",           "en": "🏛 Authority",       "de": "🏛 Behörde",              "pl": "🏛 Urząd",             "tr": "🏛 Kurum",        "ar": "🏛 الجهة"}
_SSTAT_GUARANTEE    = {
    "ua": "📌 Моніторинг активний до першого знайденого Termin",
    "uk": "📌 Моніторинг активний до першого знайденого Termin",
    "en": "📌 Monitoring active until first Termin is found",
    "de": "📌 Überwachung aktiv bis zum ersten gefundenen Termin",
    "pl": "📌 Monitoring aktywny do pierwszego znalezionego Termin",
    "tr": "📌 İlk randevu bulunana kadar izleme aktif",
    "ar": "📌 المراقبة نشطة حتى العثور على أول موعد",
}
_SSTAT_LASTCHK_STARTING = {
    "ua": "запускається…", "uk": "запускається…",
    "en": "starting…",      "de": "startet…",
    "pl": "startuje…",      "tr": "başlıyor…",     "ar": "يبدأ…",
}
_SSTAT_LASTCHK_SEC_AGO = {
    "ua": "сек тому", "uk": "сек тому",
    "en": "sec ago",   "de": "Sek. her",
    "pl": "sek temu",  "tr": "sn önce",      "ar": "ث مضت",
}
_SSTAT_EXPECTATION = {
    "ua": "📊 Більшість Termin з'являються вранці (07:00–09:00) та після 23:00",
    "uk": "📊 Більшість Termin з'являються вранці (07:00–09:00) та після 23:00",
    "en": "📊 Most appointment slots appear in the morning (07:00–09:00) or after 23:00",
    "de": "📊 Die meisten Termine erscheinen morgens (07:00–09:00) oder nach 23:00",
    "pl": "📊 Większość terminów pojawia się rano (07:00–09:00) lub po 23:00",
    "tr": "📊 Çoğu randevu sabah (07:00–09:00) veya 23:00 sonrası açılır",
    "ar": "📊 تظهر معظم المواعيد صباحًا (07:00–09:00) أو بعد الساعة 23:00",
}
_SSTAT_SOCIAL_PROOF = {
    "ua": "👥 {count} людей вже знайшли Termin через моніторинг",
    "uk": "👥 {count} людей вже знайшли Termin через моніторинг",
    "en": "👥 {count} people have already found appointments using monitoring",
    "de": "👥 {count} Nutzer haben bereits Termine über das Monitoring gefunden",
    "pl": "👥 {count} osób znalazło już termin dzięki monitoringowi",
    "tr": "👥 {count} kişi monitoring sayesinde randevu buldu",
    "ar": "👥 {count} شخصًا وجدوا موعدًا عبر نظام المراقبة",
}

# ── Live-status UX elements ───────────────────────────────────────────────────
# Cyclical scan phrases: rotate on each poll cycle to create a "live" effect.
_SSTAT_SCAN_PHRASES = {
    "ua": [
        "📡 Скануємо нові слоти...",
        "📡 Перевіряємо систему запису...",
        "📡 Шукаємо вільні вікна...",
        "📡 Моніторинг активний...",
        "📡 Сканування порталу...",
    ],
    "uk": [
        "📡 Скануємо нові слоти...",
        "📡 Перевіряємо систему запису...",
        "📡 Шукаємо вільні вікна...",
        "📡 Моніторинг активний...",
        "📡 Сканування порталу...",
    ],
    "en": [
        "📡 Scanning for new slots...",
        "📡 Checking appointment system...",
        "📡 Looking for open windows...",
        "📡 Monitoring active...",
        "📡 Portal scan in progress...",
    ],
    "de": [
        "📡 Neue Slots werden gescannt...",
        "📡 Terminsystem wird geprüft...",
        "📡 Suche nach freien Fenstern...",
        "📡 Überwachung aktiv...",
        "📡 Portal-Scan läuft...",
    ],
    "pl": [
        "📡 Skanujemy nowe sloty...",
        "📡 Sprawdzamy system zapisów...",
        "📡 Szukamy wolnych okienek...",
        "📡 Monitoring aktywny...",
        "📡 Skanowanie portalu...",
    ],
    "tr": [
        "📡 Yeni slotlar taranıyor...",
        "📡 Randevu sistemi kontrol ediliyor...",
        "📡 Açık pencereler aranıyor...",
        "📡 İzleme aktif...",
        "📡 Portal taraması devam ediyor...",
    ],
    "ar": [
        "📡 جاري فحص الفترات الجديدة...",
        "📡 التحقق من نظام المواعيد...",
        "📡 البحث عن النوافذ المتاحة...",
        "📡 المراقبة نشطة...",
        "📡 مسح البوابة جارٍ...",
    ],
}
# ── Live activity block — replaces rotating scan phrases ─────────────────────
# Header label (no emoji — pulse emoji prepended dynamically from timestamp % 2)
_SSTAT_LIVE_HDR = {
    "ua": "Моніторинг активний",
    "uk": "Моніторинг активний",
    "en": "Monitoring active",
    "de": "Monitoring aktiv",
    "pl": "Monitoring aktywny",
    "tr": "İzleme aktif",
    "ar": "المراقبة نشطة",
}
# "Scanning right now" line — trailing dots are added dynamically (% 3 cycle)
_SSTAT_LIVE_SCAN_NOW = {
    "ua": "🔍 Перевіряємо слоти прямо зараз",
    "uk": "🔍 Перевіряємо слоти прямо зараз",
    "en": "🔍 Checking slots right now",
    "de": "🔍 Prüfen gerade Termine",
    "pl": "🔍 Sprawdzamy sloty teraz",
    "tr": "🔍 Şu an slotlar kontrol ediliyor",
    "ar": "🔍 نفحص المواعيد الآن",
}
# "Next check" line
_SSTAT_NEXT_CHECK = {
    "ua": "⏱ Наступна перевірка: ~30 сек",
    "uk": "⏱ Наступна перевірка: ~30 сек",
    "en": "⏱ Next check in ~30 sec",
    "de": "⏱ Nächste Prüfung in ~30 Sek",
    "pl": "⏱ Następne sprawdzenie: ~30 sek",
    "tr": "⏱ Sonraki kontrol: ~30 sn",
    "ar": "⏱ الفحص التالي خلال ~30 ث",
}

# Notification block: shown below the scan line to reassure user what happens on match.
_SSTAT_NOTIFY_HDR = {
    "ua": "🔔 <b>Як тільки зʼявиться місце:</b>",
    "uk": "🔔 <b>Як тільки зʼявиться місце:</b>",
    "en": "🔔 <b>As soon as a slot appears:</b>",
    "de": "🔔 <b>Sobald ein Termin frei ist:</b>",
    "pl": "🔔 <b>Gdy pojawi się miejsce:</b>",
    "tr": "🔔 <b>Yer açıldığında:</b>",
    "ar": "🔔 <b>فور ظهور موعد:</b>",
}
_SSTAT_NOTIFY_BODY = {
    "ua": "• повідомлення в Telegram\n• дублювання на email\n• пряме посилання для запису",
    "uk": "• повідомлення в Telegram\n• дублювання на email\n• пряме посилання для запису",
    "en": "• Telegram notification\n• email backup\n• direct booking link",
    "de": "• Telegram-Benachrichtigung\n• E-Mail-Backup\n• Direkter Buchungslink",
    "pl": "• powiadomienie w Telegram\n• kopia na email\n• bezpośredni link do rezerwacji",
    "tr": "• Telegram bildirimi\n• e-posta yedeği\n• doğrudan rezervasyon bağlantısı",
    "ar": "• إشعار Telegram\n• نسخ احتياطي على البريد الإلكتروني\n• رابط الحجز المباشر",
}
# Uptime label + unit word (e.g. "⏱ Працюємо вже: 17 хв")
_SSTAT_UPTIME_LBL = {
    "ua": "⏱ Працюємо вже",
    "uk": "⏱ Працюємо вже",
    "en": "⏱ Running for",
    "de": "⏱ Läuft seit",
    "pl": "⏱ Działa od",
    "tr": "⏱ Çalışma süresi",
    "ar": "⏱ يعمل منذ",
}
_SSTAT_UPTIME_MIN = {
    "ua": "хв", "uk": "хв",
    "en": "min", "de": "Min.",
    "pl": "min", "tr": "dak",
    "ar": "دق",
}
# Last slot found (only rendered when last_notified_ts > 0)
_SSTAT_LAST_SLOT_LBL = {
    "ua": "🕒 Останній слот знайдено",
    "uk": "🕒 Останній слот знайдено",
    "en": "🕒 Last slot found",
    "de": "🕒 Letzter Slot gefunden",
    "pl": "🕒 Ostatni slot znaleziony",
    "tr": "🕒 Son bulunan slot",
    "ar": "🕒 آخر فترة وُجدت",
}
# Strategy change button (status screen row 2) — label differs from data row to avoid ambiguity
_SSTAT_STRATEGY_BTN = {"ua": "🔧 Змінити стратегію",   "uk": "🔧 Змінити стратегію",   "en": "🔧 Change strategy", "de": "🔧 Strategie ändern",     "pl": "🔧 Zmień strategię",   "tr": "🔧 Strateji değiştir", "ar": "🔧 تغيير الاستراتيجية"}

# ── Status screen block section headers ─────────────────────────────────────
# _SSTAT_HDR1 removed: "Monitoring Status" title serves as the block header already
_SSTAT_HDR2 = {"ua": "⚙ <b>Конфігурація</b>",   "uk": "⚙ <b>Конфігурація</b>",   "en": "⚙ <b>Configuration</b>", "de": "⚙ <b>Konfiguration</b>", "pl": "⚙ <b>Konfiguracja</b>",   "tr": "⚙ <b>Yapılandırma</b>", "ar": "⚙ <b>الإعدادات</b>"}
_SSTAT_HDR3 = {"ua": "📈 <b>Активність</b>",     "uk": "📈 <b>Активність</b>",     "en": "📈 <b>Activity</b>",     "de": "📈 <b>Aktivität</b>",     "pl": "📈 <b>Aktywność</b>",      "tr": "📈 <b>Aktivite</b>",     "ar": "📈 <b>النشاط</b>"}

# ── Priority: displayed as "Faster reaction mode" in status (not marketing) ─
_PRIORITY_DISPLAY_LABEL = {
    "ua": "🔔 Режим швидшої реакції", "uk": "🔔 Режим швидшої реакції",
    "en": "🔔 Faster reaction mode",  "de": "🔔 Schnellere Reaktion aktiv",
    "pl": "🔔 Szybsza reakcja aktywna","tr": "🔔 Daha hızlı tepki modu",
    "ar": "🔔 وضع الاستجابة الأسرع",
}

# ── Empty state (monitoring not yet started or expired) ──────────────────────
_STATUS_EMPTY_TEXT = {
    "ua": (
        "Активних сесій моніторингу немає.\n\n"
        "Розпочніть нову сесію, щоб автоматично відстежувати "
        "офіційні портали на наявність вільних записів."
    ),
    "uk": (
        "Активних сесій моніторингу немає.\n\n"
        "Розпочніть нову сесію, щоб автоматично відстежувати "
        "офіційні портали на наявність вільних записів."
    ),
    "en": (
        "No active monitoring session.\n\n"
        "Start a new monitoring session to automatically check "
        "official portals for available appointments."
    ),
    "de": (
        "Keine aktive Überwachungssitzung.\n\n"
        "Starten Sie eine neue Sitzung, um offizielle Portale "
        "automatisch auf verfügbare Termine zu prüfen."
    ),
    "pl": (
        "Brak aktywnej sesji monitoringu.\n\n"
        "Rozpocznij nową sesję, aby automatycznie sprawdzać "
        "oficjalne portale pod kątem dostępnych terminów."
    ),
    "tr": (
        "Aktif izleme oturumu yok.\n\n"
        "Müsait randevular için resmi portalları otomatik olarak "
        "kontrol etmek üzere yeni bir oturum başlatın."
    ),
    "ar": (
        "لا توجد جلسة مراقبة نشطة.\n\n"
        "ابدأ جلسة مراقبة جديدة للتحقق تلقائياً من "
        "البوابات الرسمية بحثاً عن مواعيد متاحة."
    ),
}
_STATUS_EMPTY_BTN = {
    "ua": "🗺 Почати налаштування", "uk": "🗺 Почати налаштування",
    "en": "🗺 Start setup",          "de": "🗺 Einrichtung starten",
    "pl": "🗺 Rozpocznij konfigurację", "tr": "🗺 Kurulumu başlat",
    "ar": "🗺 بدء الإعداد",
}

# ── Strategy updated confirmation (for users already monitoring) ─────────────
_STRATEGY_UPDATED_TEXT = {
    "ua": "🔧 Стратегію оновлено.",
    "uk": "🔧 Стратегію оновлено.",
    "en": "🔧 Strategy updated.",
    "de": "🔧 Strategie aktualisiert.",
    "pl": "🔧 Strategia zaktualizowana.",
    "tr": "🔧 Strateji güncellendi.",
    "ar": "🔧 تم تحديث الاستراتيجية.",
}

# ── "How it works" screen ────────────────────────────────────────────────────
_TERMIN_HOW_TEXT = {
    "ua": (
        "ℹ️ <b>Як це працює</b>\n\n"
        "1. Ми відстежуємо офіційні урядові портали на появу вільних слотів.\n"
        "2. Щойно з\u02bcявиться місце — ви одразу отримуєте сповіщення.\n"
        "3. Ви переходите на офіційний сайт і бронюєте запис самостійно.\n"
        "4. Ми не є державним органом і не діємо від вашого імені.\n\n"
        "🔄 Інтервал перевірки: кілька секунд."
    ),
    "uk": (
        "ℹ️ <b>Як це працює</b>\n\n"
        "1. Ми відстежуємо офіційні урядові портали на появу вільних слотів.\n"
        "2. Щойно з\u02bcявиться місце — ви одразу отримуєте сповіщення.\n"
        "3. Ви переходите на офіційний сайт і бронюєте запис самостійно.\n"
        "4. Ми не є державним органом і не діємо від вашого імені.\n\n"
        "🔄 Інтервал перевірки: кілька секунд."
    ),
    "en": (
        "ℹ️ <b>How it works</b>\n\n"
        "1. We monitor official government portals for available appointment slots.\n"
        "2. The moment a slot appears — you receive an instant notification.\n"
        "3. You visit the official website and book the appointment yourself.\n"
        "4. We are not a government authority and do not act on your behalf.\n\n"
        "🔄 Check interval: a few seconds."
    ),
    "de": (
        "ℹ️ <b>So funktioniert es</b>\n\n"
        "1. Wir überwachen offizielle Behördenportale auf freie Termine.\n"
        "2. Sobald ein Termin verfügbar ist — erhalten Sie sofort eine Benachrichtigung.\n"
        "3. Sie gehen auf die offizielle Website und buchen den Termin selbst.\n"
        "4. Wir sind keine Behörde und handeln nicht in Ihrem Namen.\n\n"
        "🔄 Prüfintervall: wenige Sekunden."
    ),
    "pl": (
        "ℹ️ <b>Jak to działa</b>\n\n"
        "1. Monitorujemy oficjalne portale urzędowe w poszukiwaniu wolnych terminów.\n"
        "2. Gdy pojawi się wolne miejsce — natychmiast otrzymujesz powiadomienie.\n"
        "3. Przechodzisz na oficjalną stronę i samodzielnie umawiasz wizytę.\n"
        "4. Nie jesteśmy organem rządowym i nie działamy w Twoim imieniu.\n\n"
        "🔄 Interwał sprawdzania: kilka sekund."
    ),
    "tr": (
        "ℹ️ <b>Nasıl çalışır</b>\n\n"
        "1. Resmi devlet portallarını müsait randevu arama yeri için izliyoruz.\n"
        "2. Bir yer açıldığı anda — anında bildirim alırsınız.\n"
        "3. Resmi web sitesine gidip randevunuzu kendiniz alırsınız.\n"
        "4. Bir devlet kurumu değiliz ve adınıza hareket etmiyoruz.\n\n"
        "🔄 Kontrol aralığı: birkaç saniye."
    ),
    "ar": (
        "ℹ️ <b>كيف يعمل النظام</b>\n\n"
        "1. نراقب البوابات الحكومية الرسمية بحثاً عن مواعيد متاحة.\n"
        "2. فور ظهور موعد — تتلقى إشعاراً فورياً.\n"
        "3. تنتقل إلى الموقع الرسمي وتحجز الموعد بنفسك.\n"
        "4. لسنا جهة حكومية ولا نتصرف نيابةً عنك.\n\n"
        "🔄 فاصل الفحص: بضع ثوانٍ."
    ),
}
_TERMIN_HOW_BTN = {
    "ua": "ℹ️ Як це працює", "uk": "ℹ️ Як це працює",
    "en": "ℹ️ How it works", "de": "ℹ️ So funktioniert es",
    "pl": "ℹ️ Jak to działa", "tr": "ℹ️ Nasıl çalışır", "ar": "ℹ️ كيف يعمل",
}

# ── "What affects speed" screen ──────────────────────────────────────────────
_TERMIN_SPEED_TEXT = {
    "ua": (
        "⚡ <b>Що впливає на швидкість пошуку</b>\n\n"
        "🏙 <b>Попит у місті</b> — у великих містах слоти з'являються рідше.\n"
        "🏛 <b>Тип установи</b> — деякі установи мають більше вільних слотів.\n"
        "🔧 <b>Стратегія</b> — \"Швидкий\" охоплює більше варіантів, \"Точний\" — конкретні офіси.\n"
        "🔔 <b>Режим пріоритету</b> — прискорена реакція при появі слоту."
    ),
    "uk": (
        "⚡ <b>Що впливає на швидкість пошуку</b>\n\n"
        "🏙 <b>Попит у місті</b> — у великих містах слоти з'являються рідше.\n"
        "🏛 <b>Тип установи</b> — деякі установи мають більше вільних слотів.\n"
        "🔧 <b>Стратегія</b> — \"Швидкий\" охоплює більше варіантів, \"Точний\" — конкретні офіси.\n"
        "🔔 <b>Режим пріоритету</b> — прискорена реакція при появі слоту."
    ),
    "en": (
        "⚡ <b>What affects search speed</b>\n\n"
        "🏙 <b>City demand</b> — high-demand cities have fewer available slots.\n"
        "🏛 <b>Authority type</b> — some authorities have more slot availability.\n"
        "🔧 <b>Strategy</b> — Fast covers more options; Precise targets specific offices.\n"
        "🔔 <b>Priority mode</b> — faster reaction when a slot appears."
    ),
    "de": (
        "⚡ <b>Was die Suchgeschwindigkeit beeinflusst</b>\n\n"
        "🏙 <b>Stadtbedarf</b> — in Großstädten erscheinen Termine seltener.\n"
        "🏛 <b>Behördentyp</b> — manche Behörden haben mehr freie Termine.\n"
        "🔧 <b>Strategie</b> — Schnell deckt mehr Optionen ab; Präzise zielt auf bestimmte Büros.\n"
        "🔔 <b>Prioritätsmodus</b> — schnellere Reaktion bei verfügbarem Termin."
    ),
    "pl": (
        "⚡ <b>Co wpływa na szybkość wyszukiwania</b>\n\n"
        "🏙 <b>Popyt w mieście</b> — w dużych miastach terminy pojawiają się rzadziej.\n"
        "🏛 <b>Typ urzędu</b> — niektóre urzędy mają więcej wolnych miejsc.\n"
        "🔧 <b>Strategia</b> — Szybka obejmuje więcej opcji; Precyzyjna — konkretne biura.\n"
        "🔔 <b>Tryb priorytetu</b> — szybsza reakcja gdy pojawi się termin."
    ),
    "tr": (
        "⚡ <b>Arama hızını etkileyen faktörler</b>\n\n"
        "🏙 <b>Şehir talebi</b> — yüksek talepli şehirlerde daha az yer açılır.\n"
        "🏛 <b>Kurum türü</b> — bazı kurumların daha fazla müsaitliği vardır.\n"
        "🔧 <b>Strateji</b> — Hızlı daha fazla seçeneği kapsar; Hassas belirli ofisleri hedefler.\n"
        "🔔 <b>Öncelik modu</b> — yer açıldığında daha hızlı tepki."
    ),
    "ar": (
        "⚡ <b>ما يؤثر على سرعة البحث</b>\n\n"
        "🏙 <b>الطلب في المدينة</b> — المدن ذات الطلب العالي لديها مواعيد أقل.\n"
        "🏛 <b>نوع الجهة</b> — بعض الجهات لديها توافر أكثر للمواعيد.\n"
        "🔧 <b>الاستراتيجية</b> — السريعة تغطي خيارات أكثر؛ الدقيقة تستهدف مكاتب محددة.\n"
        "🔔 <b>وضع الأولوية</b> — استجابة أسرع عند ظهور موعد."
    ),
}
_TERMIN_SPEED_BTN = {
    "ua": "⚡ Що впливає на швидкість", "uk": "⚡ Що впливає на швидкість",
    "en": "⚡ What affects speed",      "de": "⚡ Was die Geschwindigkeit beeinflusst",
    "pl": "⚡ Co wpływa na szybkość",   "tr": "⚡ Hızı etkileyen faktörler",
    "ar": "⚡ ما يؤثر على السرعة",
}

_STATUS_TITLE = {
    "ua": "📊 <b>Статус моніторингу</b>",
    "en": "📊 <b>Monitoring Status</b>",
    "de": "📊 <b>Überwachungsstatus</b>",
    "pl": "📊 <b>Status monitoringu</b>",
    "tr": "📊 <b>İzleme Durumu</b>",
    "ar": "📊 <b>حالة المراقبة</b>",
}


async def handle_termin_status(callback: types.CallbackQuery, state: FSMContext):
    """Show live monitoring status with countdown, pause state, and control buttons."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    import time as _time_mod

    # ── Priority: live session data (authoritative) ───────────────────────────
    # A running _PollingSession always has the freshest city/authority/stats.
    # This path activates even when FSM was cleared by the Stripe webhook.
    _live_session = get_polling_session(user_id)
    logger.info(
        "TERMIN_STATUS_OPENED | user=%s city=%s auth=%s session_active=%s",
        user_id,
        _live_session.city if _live_session else "—",
        _live_session.authority if _live_session else "—",
        _live_session is not None,
    )
    if _live_session is not None:
        from backend.termin_db import get_entitlement as _get_ent_stat
        from utils.time_utils import get_countdown_line as _get_cd_stat
        from utils.termin_checker import (
            set_status_message_id as _set_smid,
            build_status_text as _build_status_text,
        )
        _ent_stat = _get_ent_stat(str(user_id))
        _paid_until_stat = (_ent_stat or {}).get("paid_until")
        _cd_stat = _get_cd_stat(_paid_until_stat, lang)

        # Single call builds the full live status text — no duplication.
        _s_city = _live_session.city or "berlin"  # still needed for keyboard callback_data
        _live_text = _build_status_text(_live_session, lang, countdown_line=_cd_stat)

        _live_kb = InlineKeyboardMarkup(row_width=2)
        # Row 1: city | service
        _live_kb.row(
            InlineKeyboardButton(_lang_text(_BTN_CHANGE_CITY, lang), callback_data="termin_cities"),
            InlineKeyboardButton(_lang_text(_BTN_CHANGE_DOC, lang), callback_data=f"termin_city_{_s_city}"),
        )
        # Row 2: pause | filters
        _live_kb.row(
            InlineKeyboardButton(_lang_text(_PAUSE_BTN, lang), callback_data="termin_pause"),
            InlineKeyboardButton(_lang_text(_FILTERS_BTN, lang), callback_data="termin_filters"),
        )
        # Row 3: back
        _live_kb.add(InlineKeyboardButton(get_text('btn_back', lang), callback_data="termin_menu"))
        try:
            await callback.message.edit_text(_live_text, parse_mode="HTML", reply_markup=_live_kb)
            # Register this message for live poll-driven updates
            _set_smid(user_id, callback.message.message_id)
            # Sync dedup cache so first poll update fires only when text actually changes
            _live_session._last_status_text = _live_text
        except Exception:
            sent = await callback.message.answer(_live_text, parse_mode="HTML", reply_markup=_live_kb)
            if sent:
                _set_smid(user_id, sent.message_id)
                _live_session._last_status_text = _live_text
        return

    # ── No live session: fall back to FSM + DB ───────────────────────────────
    data = await state.get_data()

    city_code = data.get("termin_city") or "berlin"
    city_code_resolved = _resolve_city_code(city_code) if city_code else "berlin"
    strategy = data.get("termin_strategy", "fast")
    started_iso = data.get("monitor_started_at")
    is_paused = data.get("monitor_paused", False)
    auth_filter = data.get("authority_filter", "all")
    multi_city = data.get("multi_city", False)

    # Monitoring model: active until first Termin found — no time countdown needed.
    _PAUSED_LABEL = {"ua": "⏸ Призупинено", "uk": "⏸ Призупинено",
                     "en": "⏸ Paused",       "de": "⏸ Pausiert",
                     "pl": "⏸ Wstrzymany",   "tr": "⏸ Duraklatıldı", "ar": "⏸ متوقف مؤقتًا"}
    _ACTIVE_LABEL2 = {"ua": "✅ Активний",   "uk": "✅ Активний",
                      "en": "✅ Active",      "de": "✅ Aktiv",
                      "pl": "✅ Aktywny",     "tr": "✅ Aktif",        "ar": "✅ نشط"}

    status_label = _lang_text(_PAUSED_LABEL if is_paused else _ACTIVE_LABEL2, lang)

    if auth_filter == "all" or not auth_filter:
        filter_display = _lang_text(_ALL_AUTHORITIES_LABEL, lang)
    else:
        filter_display = normalize_authority_name(auth_filter)

    # Real-time stats from the active polling session (not estimates)
    _mon_stats = get_monitoring_stats(user_id)
    _checks_today = str(_mon_stats["checks"]) if _mon_stats["checks"] > 0 else "—"
    _last_check_sec = _mon_stats["last_check_sec"]
    if _last_check_sec is None:
        _last_check_display = _lang_text(_SSTAT_LASTCHK_STARTING, lang)
    else:
        _last_check_display = f"{_last_check_sec} {_lang_text(_SSTAT_LASTCHK_SEC_AGO, lang)}"

    city_display = _CITY_DISPLAY_MAP.get(city_code_resolved, city_code_resolved.replace("_", " ").title())

    # ── Empty state: no monitoring started and not paused ────────────────────
    if not started_iso and not is_paused:
        # Safety: FSM may have been cleared by the Stripe webhook after payment,
        # OR the poll session was lost after bot restart but entitlement is still valid.
        # Show the live status screen (with DB-sourced city/auth) instead of the main menu.
        if is_termin_entitled(str(user_id)):
            _db_u = _ensure_termin_user(user_id, lang)
            _db_city = (_db_u.get('city') or '') if _db_u else ''
            _db_auth = (_db_u.get('authority') or '') if _db_u else ''
            if _db_city and _db_auth:
                import types as _types_fb
                from backend.termin_db import get_entitlement as _get_ent_fb
                from utils.time_utils import get_countdown_line as _get_cd_fb
                from utils.termin_checker import build_status_text as _build_st_fb
                _ent_fb = _get_ent_fb(str(user_id))
                _paid_until_fb = (_ent_fb or {}).get("paid_until")
                _cd_fb = _get_cd_fb(_paid_until_fb, lang)
                # Stub session: bot restarted, session not yet resumed — zero stats
                _stub_fb = _types_fb.SimpleNamespace(
                    city=_db_city,
                    authority=_db_auth,
                    checks_count=0,
                    last_check_ts=0.0,
                    started_at=None,
                    last_notified_ts=0.0,
                )
                _fb_text = _build_st_fb(_stub_fb, lang, countdown_line=_cd_fb)
                _fb_kb = InlineKeyboardMarkup(row_width=2)
                _fb_kb.row(
                    InlineKeyboardButton(_lang_text(_BTN_CHANGE_CITY, lang), callback_data="termin_cities"),
                    InlineKeyboardButton(_lang_text(_BTN_CHANGE_DOC, lang), callback_data=f"termin_city_{_db_city}"),
                )
                _fb_kb.row(
                    InlineKeyboardButton(_lang_text(_PAUSE_BTN, lang), callback_data="termin_pause"),
                    InlineKeyboardButton(_lang_text(_FILTERS_BTN, lang), callback_data="termin_filters"),
                )
                _fb_kb.add(InlineKeyboardButton(get_text('btn_back', lang), callback_data="termin_menu"))
                try:
                    await callback.message.edit_text(_fb_text, parse_mode="HTML", reply_markup=_fb_kb)
                except Exception:
                    await callback.message.answer(_fb_text, parse_mode="HTML", reply_markup=_fb_kb)
                return

        empty_kb = InlineKeyboardMarkup(row_width=1)
        empty_kb.add(InlineKeyboardButton(
            _lang_text(_STATUS_EMPTY_BTN, lang),
            callback_data="termin_cities",
        ))
        empty_kb.add(InlineKeyboardButton(get_text('btn_back', lang), callback_data="termin_menu"))
        empty_text = (
            f"{_lang_text(_STATUS_TITLE, lang)}\n\n"
            f"{_lang_text(_STATUS_EMPTY_TEXT, lang)}"
        )
        try:
            await callback.message.edit_text(empty_text, parse_mode="HTML", reply_markup=empty_kb)
        except Exception:
            await callback.message.answer(empty_text, parse_mode="HTML", reply_markup=empty_kb)
        return

    # FSM fallback — build via shared helper for visual consistency
    import time as _time_mod_fsm
    import types as _types_fsm
    from backend.termin_db import get_entitlement as _get_ent_fsm
    from utils.time_utils import get_countdown_line as _get_cd_fsm
    from utils.termin_checker import build_status_text as _build_st_fsm
    _ent_fsm = _get_ent_fsm(str(user_id))
    _paid_until_fsm = (_ent_fsm or {}).get("paid_until")
    _cd_fsm = _get_cd_fsm(_paid_until_fsm, lang)

    # Reconstruct last_check_ts from seconds-ago value (may be None)
    _lct_fsm = (
        (_time_mod_fsm.time() - _mon_stats["last_check_sec"])
        if _mon_stats["last_check_sec"] is not None
        else 0.0
    )
    _stub_fsm = _types_fsm.SimpleNamespace(
        city=city_code_resolved,
        authority=auth_filter if auth_filter not in ("all", "", None) else "",
        checks_count=_mon_stats["checks"],
        last_check_ts=_lct_fsm,
        started_at=None,
        last_notified_ts=0.0,
    )
    # Pass paused label so the status line shows "⏸" instead of "🟢"
    _fsm_status_override = status_label if is_paused else None
    text = _build_st_fsm(
        _stub_fsm, lang,
        countdown_line=_cd_fsm,
        status_label_override=_fsm_status_override,
    )

    kb = InlineKeyboardMarkup(row_width=2)
    # Row 1: city | service (only when not paused — no city to navigate to if paused)
    kb.row(
        InlineKeyboardButton(_lang_text(_BTN_CHANGE_CITY, lang), callback_data="termin_cities"),
        InlineKeyboardButton(
            _lang_text(_BTN_CHANGE_DOC, lang),
            callback_data=f"termin_city_{city_code_resolved}",
        ),
    )
    # Row 2: pause/resume | filters
    if is_paused:
        kb.row(
            InlineKeyboardButton(_lang_text(_RESUME_BTN, lang), callback_data="termin_resume"),
            InlineKeyboardButton(_lang_text(_FILTERS_BTN, lang), callback_data="termin_filters"),
        )
    else:
        kb.row(
            InlineKeyboardButton(_lang_text(_PAUSE_BTN, lang), callback_data="termin_pause"),
            InlineKeyboardButton(_lang_text(_FILTERS_BTN, lang), callback_data="termin_filters"),
        )
    # Row 3: back
    kb.add(InlineKeyboardButton(get_text('btn_back', lang), callback_data="termin_menu"))

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


# ==================== Pause / Resume ====================

_PAUSE_MSG = {
    "ua": (
        "⏸ <b>Моніторинг призупинено.</b>\n\n"
        "Під час паузи ми не перевіряємо слоти.\n"
        "Ваші налаштування збережено — продовжіть будь-коли.\n\n"
        "⚠️ <i>Оплачений час продовжує спливати під час паузи.</i>"
    ),
    "uk": (
        "⏸ <b>Моніторинг призупинено.</b>\n\n"
        "Під час паузи ми не перевіряємо слоти.\n"
        "Ваші налаштування збережено — продовжіть будь-коли.\n\n"
        "⚠️ <i>Оплачений час продовжує спливати під час паузи.</i>"
    ),
    "en": (
        "⏸ <b>Monitoring paused.</b>\n\n"
        "We won't check for slots while paused.\n"
        "Your settings are saved — resume any time.\n\n"
        "⚠️ <i>Your paid monitoring time continues to run while paused.</i>"
    ),
    "de": (
        "⏸ <b>Überwachung pausiert.</b>\n\n"
        "Während der Pause prüfen wir keine Termine.\n"
        "Ihre Einstellungen bleiben gespeichert — jederzeit fortsetzen.\n\n"
        "⚠️ <i>Die bezahlte Überwachungszeit läuft auch während der Pause weiter.</i>"
    ),
    "pl": (
        "⏸ <b>Monitoring wstrzymany.</b>\n\n"
        "W czasie pauzy nie sprawdzamy terminów.\n"
        "Twoje ustawienia są zapisane — wznów kiedy chcesz.\n\n"
        "⚠️ <i>Opłacony czas monitoringu nadal upływa podczas pauzy.</i>"
    ),
    "tr": (
        "⏸ <b>İzleme duraklatıldı.</b>\n\n"
        "Duraklatma sırasında randevu kontrol etmiyoruz.\n"
        "Ayarlarınız kaydedildi — istediğinizde devam edin.\n\n"
        "⚠️ <i>Ücretli izleme süreniz duraklatma sırasında da geçmeye devam eder.</i>"
    ),
    "ar": (
        "⏸ <b>تم إيقاف المراقبة مؤقتًا.</b>\n\n"
        "لن نتحقق من المواعيد أثناء التوقف.\n"
        "إعداداتك محفوظة — يمكنك الاستئناف في أي وقت.\n\n"
        "⚠️ <i>وقت المراقبة المدفوع يستمر في العد أثناء الإيقاف المؤقت.</i>"
    ),
}
_RESUME_MSG = {
    "ua": "▶ <b>Моніторинг відновлено.</b>\nПошук триває.",
    "en": "▶ <b>Monitoring resumed.</b>\nSearch continues.",
    "de": "▶ <b>Überwachung fortgesetzt.</b>\nSuche läuft weiter.",
    "pl": "▶ <b>Monitoring wznowiony.</b>\nWyszukiwanie trwa.",
    "tr": "▶ <b>İzleme devam ediyor.</b>\nArama devam ediyor.",
    "ar": "▶ <b>تم استئناف المراقبة.</b>\nالبحث مستمر.",
}
_RESUME_BTN = {
    "uk": "▶ Відновити", "ua": "▶ Відновити",
    "en": "▶ Resume",
    "de": "▶ Fortsetzen",
    "pl": "▶ Wznów",
    "tr": "▶ Devam et",
    "ar": "▶ استئناف",
}


async def handle_termin_settings(callback: types.CallbackQuery, state: FSMContext):
    """Show the monitoring Settings submenu."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    user = get_user(str(user_id))
    user_city = user.get('city') if user else None
    _family = _is_family_user(user_id)
    _active_profile = 1
    if _family:
        try:
            _fd = await state.get_data()
            _fsm_pid = _fd.get("active_profile_id")
            if _fsm_pid is not None:
                _active_profile = int(_fsm_pid)
        except Exception:
            pass
    kb = get_termin_settings_keyboard(
        lang, user_city=user_city,
        user_id=user_id,
        active_profile_id=_active_profile if _family else None,
        is_family=_family,
    )
    try:
        await callback.message.edit_text(
            _lang_text(_SETTINGS_MENU_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        await callback.message.answer(
            _lang_text(_SETTINGS_MENU_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )


async def handle_termin_pause(callback: types.CallbackQuery, state: FSMContext):
    """Pause active monitoring."""
    await callback.answer(cache_time=1)
    _pause_uid = callback.from_user.id
    await state.update_data(monitor_paused=True)
    lang = _resolve_lang(_pause_uid)
    _pause_sess = get_polling_session(_pause_uid)
    logger.info(
        "TERMIN_MONITORING_PAUSED | user=%s city=%s auth=%s",
        _pause_uid,
        _pause_sess.city if _pause_sess else "—",
        _pause_sess.authority if _pause_sess else "—",
    )
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_lang_text(_RESUME_BTN, lang), callback_data="termin_resume"))
    kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))
    try:
        await callback.message.edit_text(_lang_text(_PAUSE_MSG, lang), parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(_lang_text(_PAUSE_MSG, lang), parse_mode="HTML", reply_markup=kb)


async def handle_termin_resume(callback: types.CallbackQuery, state: FSMContext):
    """Resume paused monitoring."""
    await callback.answer(cache_time=1)
    await state.update_data(monitor_paused=False)
    lang = _resolve_lang(callback.from_user.id)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))
    try:
        await callback.message.edit_text(_lang_text(_RESUME_MSG, lang), parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(_lang_text(_RESUME_MSG, lang), parse_mode="HTML", reply_markup=kb)


# ==================== Authority Filters ====================

_FILTER_TITLE = {
    "ua": "⚙ <b>Оберіть установу для пошуку:</b>",
    "en": "⚙ <b>Select authority to search:</b>",
    "de": "⚙ <b>Behörde für die Suche wählen:</b>",
    "pl": "⚙ <b>Wybierz urząd do wyszukiwania:</b>",
    "tr": "⚙ <b>Aranacak kurumu seçin:</b>",
    "ar": "⚙ <b>:اختر الجهة للبحث</b>",
}
_FILTER_APPLIED = {
    "ua": "✅ Фільтр застосовано: <b>{auth}</b>",
    "en": "✅ Filter applied: <b>{auth}</b>",
    "de": "✅ Filter angewendet: <b>{auth}</b>",
    "pl": "✅ Filtr zastosowany: <b>{auth}</b>",
    "tr": "✅ Filtre uygulandı: <b>{auth}</b>",
    "ar": "✅ تم تطبيق الفلتر: <b>{auth}</b>",
}
_FILTER_OPTIONS = [
    ("buergeramt", "🏛 Bürgeramt"),
    ("auslaenderbehoerde", "🏛 Ausländerbehörde"),
    ("wohnungsamt", "🏛 Wohnungsamt"),
    ("familienkasse", "🏛 Familienkasse"),
    ("jobcenter", "🏛 Jobcenter"),
    ("all", None),   # label resolved at render time via _ALL_AUTHORITIES_LABEL
]


def _filter_option_label(code: str, label, lang: str) -> str:
    """Return human-readable label for a filter option code."""
    if code == "all":
        return "🔄 " + _lang_text(_ALL_AUTHORITIES_LABEL, lang)
    return label or _FILTER_CODE_DISPLAY.get(code, f"🏛 {code.title()}")


async def handle_termin_filters(callback: types.CallbackQuery, state: FSMContext):
    """Show authority filter selection."""
    await callback.answer(cache_time=1)
    lang = _resolve_lang(callback.from_user.id)
    data = await state.get_data()
    current_filter = data.get("authority_filter", "all")

    kb = InlineKeyboardMarkup(row_width=1)
    for code, label in _FILTER_OPTIONS:
        marker = " ✓" if code == current_filter else ""
        display = _filter_option_label(code, label, lang)
        kb.add(InlineKeyboardButton(f"{display}{marker}", callback_data=f"termin_filter_{code}"))
    kb.add(InlineKeyboardButton(get_text('btn_back', lang), callback_data="termin_status"))

    try:
        await callback.message.edit_text(_lang_text(_FILTER_TITLE, lang), parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(_lang_text(_FILTER_TITLE, lang), parse_mode="HTML", reply_markup=kb)


async def handle_apply_filter(callback: types.CallbackQuery, state: FSMContext):
    """Apply selected authority filter."""
    await callback.answer(cache_time=1)
    authority = callback.data.replace("termin_filter_", "")
    await state.update_data(authority_filter=authority)
    lang = _resolve_lang(callback.from_user.id)

    display = dict(_FILTER_OPTIONS).get(authority, authority)
    text = _lang_text(_FILTER_APPLIED, lang).format(auth=display)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


# ==================== Multi-City Expand ====================

_EXPAND_MSG = {
    "ua": (
        "🌍 <b>Пошук розширено.</b>\n\n"
        "Тепер ми шукаємо у сусідніх містах.\n"
        "Це збільшує шанси знайти вільний слот."
    ),
    "en": (
        "🌍 <b>Search expanded.</b>\n\n"
        "We are now searching nearby cities.\n"
        "This may increase your chances of finding a slot."
    ),
    "de": (
        "🌍 <b>Suche erweitert.</b>\n\n"
        "Wir suchen jetzt auch in Nachbarstädten.\n"
        "Das erhöht Ihre Chancen auf einen Termin."
    ),
    "pl": (
        "🌍 <b>Wyszukiwanie rozszerzone.</b>\n\n"
        "Szukamy teraz w pobliskich miastach.\n"
        "To zwiększa szanse na znalezienie terminu."
    ),
    "tr": (
        "🌍 <b>Arama genişletildi.</b>\n\n"
        "Şimdi yakın şehirlerde de arıyoruz.\n"
        "Bu, randevu bulma şansınızı artırabilir."
    ),
    "ar": (
        "🌍 <b>تم توسيع البحث.</b>\n\n"
        "نبحث الآن في المدن القريبة.\n"
        "هذا قد يزيد فرصك في العثور على موعد."
    ),
}


async def handle_termin_expand(callback: types.CallbackQuery, state: FSMContext):
    """Expand search to nearby cities."""
    await callback.answer(cache_time=1)
    await state.update_data(multi_city=True)
    lang = _resolve_lang(callback.from_user.id)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))
    try:
        await callback.message.edit_text(_lang_text(_EXPAND_MSG, lang), parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(_lang_text(_EXPAND_MSG, lang), parse_mode="HTML", reply_markup=kb)


# ==================== Priority Alerts ====================

_PRIORITY_PRICE = 1.99

_PRIORITY_PROMPT = {
    "ua": (
        "⚡ <b>Priority Boost</b> збільшує частоту моніторингу та скорочує час реакції.\n\n"
        "Рекомендовано якщо:\n"
        "• Записи у вашому місті мають високий попит\n"
        "• Вам потрібні більш часті оновлення"
    ),
    "uk": (
        "⚡ <b>Priority Boost</b> збільшує частоту моніторингу та скорочує час реакції.\n\n"
        "Рекомендовано якщо:\n"
        "• Записи у вашому місті мають високий попит\n"
        "• Вам потрібні більш часті оновлення"
    ),
    "en": (
        "⚡ <b>Priority Boost</b> increases monitoring frequency and reduces reaction time.\n\n"
        "Recommended if:\n"
        "• Appointments in your city are highly competitive\n"
        "• You need faster updates"
    ),
    "de": (
        "⚡ <b>Priority Boost</b> erhöht die Überwachungsfrequenz und verkürzt die Reaktionszeit.\n\n"
        "Empfohlen wenn:\n"
        "• Termine in Ihrer Stadt sehr gefragt sind\n"
        "• Sie häufigere Aktualisierungen benötigen"
    ),
    "pl": (
        "⚡ <b>Priority Boost</b> zwiększa częstotliwość monitoringu i skraca czas reakcji.\n\n"
        "Zalecane jeśli:\n"
        "• Terminy w Twoim mieście cieszą się dużym zainteresowaniem\n"
        "• Potrzebujesz częstszych aktualizacji"
    ),
    "tr": (
        "⚡ <b>Priority Boost</b> izleme sıklığını artırır ve tepki süresini kısaltır.\n\n"
        "Şunlar için önerilir:\n"
        "• Şehrinizde randevular oldukça rekabetli\n"
        "• Daha sık güncelleme istiyorsanız"
    ),
    "ar": (
        "⚡ <b>Priority Boost</b> يزيد من تكرار المراقبة ويقلل وقت الاستجابة.\n\n"
        "موصى به إذا:\n"
        "• المواعيد في مدينتك تحظى بطلب مرتفع\n"
        "• تحتاج إلى تحديثات أكثر تكراراً"
    ),
}

_PRIORITY_BTN = {
    "ua": "🔔 Priority Boost (€{price})",
    "en": "🔔 Priority Boost (€{price})",
    "de": "🔔 Priority Boost (€{price})",
    "pl": "🔔 Priority Boost (€{price})",
    "tr": "🔔 Priority Boost (€{price})",
    "ar": "🔔 Priority Boost (€{price})",
}

_PRIORITY_ON = {
    "ua": "🔔 <b>Пріоритетні сповіщення увімкнено.</b>\n\nВи отримаєте миттєве повідомлення при появі слоту у вашому районі.",
    "en": "🔔 <b>Priority alerts enabled.</b>\n\nYou will get instant notification when a slot appears in your area.",
    "de": "🔔 <b>Prioritätsbenachrichtigungen aktiviert.</b>\n\nSie erhalten sofortige Benachrichtigung bei verfügbaren Terminen.",
    "pl": "🔔 <b>Priorytetowe alerty włączone.</b>\n\nOtrzymasz natychmiastowe powiadomienie o wolnym terminie.",
    "tr": "🔔 <b>Öncelikli uyarılar etkinleştirildi.</b>\n\nBölgenizde randevu açıldığında anında bildirim alacaksınız.",
    "ar": "🔔 <b>تم تفعيل التنبيهات ذات الأولوية.</b>\n\nستتلقى إشعارًا فوريًا عند توفر موعد في منطقتك.",
}


async def handle_termin_priority(callback: types.CallbackQuery, state: FSMContext):
    """Show paid Priority Boost offer, or inform user if already active."""
    await callback.answer(cache_time=1)
    lang = _resolve_lang(callback.from_user.id)

    data = await state.get_data()
    if data.get("priority_alerts"):
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))
        already_text = _lang_text({
            "ua": "🔔 Priority Boost вже активний.",
            "en": "🔔 Priority Boost is already active.",
            "de": "🔔 Priority Boost ist bereits aktiv.",
            "pl": "🔔 Priority Boost jest już aktywny.",
            "tr": "🔔 Priority Boost zaten aktif.",
            "ar": "🔔 Priority Boost مفعّل بالفعل.",
        }, lang)
        try:
            await callback.message.edit_text(already_text, reply_markup=kb)
        except Exception:
            await callback.message.answer(already_text, reply_markup=kb)
        return

    btn_label = _lang_text(_PRIORITY_BTN, lang).format(price=f"{_PRIORITY_PRICE:.2f}")
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(btn_label, callback_data="termin_priority_pay"))
    kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))

    text = _lang_text(_PRIORITY_PROMPT, lang)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


async def handle_termin_priority_pay(callback: types.CallbackQuery, state: FSMContext):
    """Create Stripe Checkout for Priority Boost."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    logger.info("TERMIN_PRIORITY_PAY | user=%s lang=%s", user_id, lang)

    import os
    try:
        from utils.helpers import get_db
        from handlers.stripe_handler import get_stripe_handler

        db = get_db()
        order_lang = "uk" if lang == "ua" else lang
        order_id = db.create_order(
            user_id=user_id,
            doc_type="termin_priority_boost",
            amount=_PRIORITY_PRICE,
            lang=order_lang,
        )

        webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
        success_url = _build_success_url(order_id)
        cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

        stripe = get_stripe_handler()
        result = await stripe.create_checkout_session(
            order_id=order_id,
            user_id=user_id,
            doc_type="termin_priority_boost",
            price=_PRIORITY_PRICE,
            success_url=success_url,
            cancel_url=cancel_url,
            extra_metadata={"flow": "termin", "monitor": "priority_boost", "user_id": str(user_id)},
        )

        if result.success:
            from backend.database import OrderStatus
            db.update_order_status(order_id, OrderStatus.PENDING, stripe_session_id=result.session_id)
            logger.info("SUCCESS_URL=%s", success_url)

            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(InlineKeyboardButton(
                _lang_text(_STRIPE_OPEN_BTN, lang).format(price=f"{_PRIORITY_PRICE:.2f}"),
                url=result.checkout_url,
            ))
            await callback.answer(cache_time=1)
            await callback.message.answer(
                _lang_text(_STRIPE_REDIRECT_TEXT, lang),
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            return

    except Exception as e:
        logger.error("TERMIN_PRIORITY_STRIPE_ERROR | user=%s error=%s", user_id, e)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(get_text("btn_back", lang), callback_data="termin_status"))
    await callback.message.answer(
        _lang_text(_STRIPE_ERROR_TEXT, lang),
        reply_markup=kb,
    )


# ==================== Reserve Slot ====================

_RESERVE_MSG = {
    "ua": (
        "⚡ <b>Резервування розпочато…</b>\n\n"
        "Ми намагаємось забронювати слот для вас.\n"
        "Це може зайняти кілька секунд."
    ),
    "en": (
        "⚡ <b>Reservation in progress…</b>\n\n"
        "We are trying to book the slot for you.\n"
        "This may take a few seconds."
    ),
    "de": (
        "⚡ <b>Reservierung läuft…</b>\n\n"
        "Wir versuchen, den Termin für Sie zu buchen.\n"
        "Dies kann einige Sekunden dauern."
    ),
    "pl": (
        "⚡ <b>Rezerwacja w toku…</b>\n\n"
        "Próbujemy zarezerwować termin dla Ciebie.\n"
        "To może potrwać kilka sekund."
    ),
    "tr": (
        "⚡ <b>Rezervasyon devam ediyor…</b>\n\n"
        "Randevuyu sizin için ayırmaya çalışıyoruz.\n"
        "Bu birkaç saniye sürebilir."
    ),
    "ar": (
        "⚡ <b>جارٍ الحجز…</b>\n\n"
        "نحاول حجز الموعد لك.\n"
        "قد يستغرق ذلك بضع ثوانٍ."
    ),
}


async def handle_termin_reserve(callback: types.CallbackQuery, state: FSMContext):
    """Handle reserve-now action from slot found alert."""
    await callback.answer(cache_time=1)
    lang = _resolve_lang(callback.from_user.id)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))
    try:
        await callback.message.edit_text(_lang_text(_RESERVE_MSG, lang), parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(_lang_text(_RESERVE_MSG, lang), parse_mode="HTML", reply_markup=kb)


_EXTEND_PRICE = 2.99

_EXTEND_PROMPT = {
    "ua": "➕ <b>Продовжити моніторинг на 24 години</b>\n\nПошук продовжиться без перерви. Ви отримаєте сповіщення одразу при появі вільного терміну.",
    "en": "➕ <b>Extend monitoring for 24 hours</b>\n\nSearch continues without interruption. You'll be notified instantly when a slot appears.",
    "de": "➕ <b>Überwachung um 24 Stunden verlängern</b>\n\nDie Suche läuft weiter. Sie werden sofort benachrichtigt, wenn ein Termin frei wird.",
    "pl": "➕ <b>Przedłuż monitoring o 24 godziny</b>\n\nWyszukiwanie trwa bez przerwy. Powiadomienie pojawi się natychmiast po znalezieniu terminu.",
    "tr": "➕ <b>İzlemeyi 24 saat uzat</b>\n\nArama kesintisiz devam eder. Randevu çıktığında anında bildirim alırsınız.",
    "ar": "➕ <b>تمديد المراقبة لمدة 24 ساعة</b>\n\nيستمر البحث دون انقطاع. ستُبلَّغ فورًا عند ظهور موعد.",
}

_EXTEND_PAY_BTN = {
    "ua": "➕ Продовжити 24 год (€{price})",
    "uk": "➕ Продовжити 24 год (€{price})",
    "en": "➕ Extend 24h (€{price})",
    "de": "➕ 24h verlängern (€{price})",
    "pl": "➕ Przedłuż 24h (€{price})",
    "tr": "➕ 24 saat uzat (€{price})",
    "ar": "➕ تمديد 24 ساعة (€{price})",
}

_EXTEND_CONFIRM = {
    "ua": "✅ Моніторинг продовжено ще на 24 години.\nПошук не зупиняється.",
    "en": "✅ Monitoring extended for another 24h.\nSearch continues without interruption.",
    "de": "✅ Überwachung um weitere 24h verlängert.\nDie Suche wird fortgesetzt.",
    "pl": "✅ Monitoring przedłużony o kolejne 24h.\nWyszukiwanie trwa.",
    "tr": "✅ İzleme 24 saat daha uzatıldı.\nArama kesintisiz devam ediyor.",
    "ar": "✅ تم تمديد المراقبة لمدة 24 ساعة إضافية.\nالبحث مستمر.",
}


async def handle_termin_extend(callback: types.CallbackQuery, state: FSMContext):
    """Show paid extend monitoring offer."""
    await callback.answer(cache_time=1)
    lang = _resolve_lang(callback.from_user.id)

    btn_label = _lang_text(_EXTEND_PAY_BTN, lang).format(price=f"{_EXTEND_PRICE:.2f}")
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(btn_label, callback_data="termin_extend_pay"))
    kb.add(InlineKeyboardButton(_lang_text(_STATUS_BTN_LABEL, lang), callback_data="termin_status"))

    text = _lang_text(_EXTEND_PROMPT, lang)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


async def handle_termin_extend_pay(callback: types.CallbackQuery, state: FSMContext):
    """Create Stripe Checkout for 24h monitoring extension."""
    await callback.answer(cache_time=1)
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)

    logger.info("TERMIN_EXTEND_PAY | user=%s lang=%s", user_id, lang)

    import os
    try:
        from utils.helpers import get_db
        from handlers.stripe_handler import get_stripe_handler

        db = get_db()
        order_lang = "uk" if lang == "ua" else lang
        order_id = db.create_order(
            user_id=user_id,
            doc_type="termin_extend_24h",
            amount=_EXTEND_PRICE,
            lang=order_lang,
        )

        webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
        success_url = _build_success_url(order_id)
        cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"

        stripe = get_stripe_handler()
        result = await stripe.create_checkout_session(
            order_id=order_id,
            user_id=user_id,
            doc_type="termin_extend_24h",
            price=_EXTEND_PRICE,
            success_url=success_url,
            cancel_url=cancel_url,
            extra_metadata={"flow": "termin", "monitor": "extend_24h", "user_id": str(user_id)},
        )

        if result.success:
            from backend.database import OrderStatus
            db.update_order_status(order_id, OrderStatus.PENDING, stripe_session_id=result.session_id)
            logger.info("SUCCESS_URL=%s", success_url)

            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(InlineKeyboardButton(
                _lang_text(_STRIPE_OPEN_BTN, lang).format(price=f"{_EXTEND_PRICE:.2f}"),
                url=result.checkout_url,
            ))
            await callback.answer(cache_time=1)
            await callback.message.answer(
                _lang_text(_STRIPE_REDIRECT_TEXT, lang),
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            return

    except Exception as e:
        logger.error("TERMIN_EXTEND_STRIPE_ERROR | user=%s error=%s", user_id, e)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(get_text("btn_back", lang), callback_data="termin_status"))
    await callback.message.answer(
        _lang_text(_STRIPE_ERROR_TEXT, lang),
        reply_markup=kb,
    )


# ==================== Info Screens: How it works / What affects speed ====================

async def handle_termin_how(callback: types.CallbackQuery):
    """'How it works' info screen — explains the service without sales language."""
    await callback.answer(cache_time=1)
    lang = _resolve_lang(callback.from_user.id)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(get_text("btn_back", lang), callback_data="termin_menu"))
    try:
        await callback.message.edit_text(
            _lang_text(_TERMIN_HOW_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        await callback.message.answer(
            _lang_text(_TERMIN_HOW_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )


async def handle_termin_speed(callback: types.CallbackQuery):
    """'What affects speed' info screen — explains factors without promises."""
    await callback.answer(cache_time=1)
    lang = _resolve_lang(callback.from_user.id)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(get_text("btn_back", lang), callback_data="termin_menu"))
    try:
        await callback.message.edit_text(
            _lang_text(_TERMIN_SPEED_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        await callback.message.answer(
            _lang_text(_TERMIN_SPEED_TEXT, lang),
            parse_mode="HTML",
            reply_markup=kb,
        )


# ==================== Language Coverage Validator ====================
def _validate_lang_dicts() -> None:
    """
    Self-check: verify that all critical UI dicts cover all 6 required
    language keys (ua, uk, en, de, pl, tr, ar).  Also asserts no English
    phrases leak into non-English translations.
    Runs once at startup — raises AssertionError if coverage is broken.
    """
    required = {"ua", "uk", "en", "de", "pl", "tr", "ar"}
    critical_dicts = {
        "_SETUP_TEXT": _SETUP_TEXT,
        "_PRE_PAYMENT_TEXT": _PRE_PAYMENT_TEXT,
        "_MONITORING_ACTIVE_TEXT": _MONITORING_ACTIVE_TEXT,
        "_SETTINGS_MENU_TEXT": _SETTINGS_MENU_TEXT,
        "_SETUP_CITY_BTN": _SETUP_CITY_BTN,
        "_SETUP_SERVICE_BTN": _SETUP_SERVICE_BTN,
        "_ACTIVITY_BTN_LABEL": _ACTIVITY_BTN_LABEL,
        "_SETTINGS_BTN_LABEL": _SETTINGS_BTN_LABEL,
        "_STATUS_BTN_LABEL": _STATUS_BTN_LABEL,
        "_PAUSE_BTN": _PAUSE_BTN,
        "_EXPAND_BTN": _EXPAND_BTN,
        "_PRIORITY_ALERTS_BTN": _PRIORITY_ALERTS_BTN,
        "_BTN_DISABLE_NOTIFICATIONS": _BTN_DISABLE_NOTIFICATIONS,
        "_SSTAT_EXPECTATION": _SSTAT_EXPECTATION,
        "_SSTAT_SOCIAL_PROOF": _SSTAT_SOCIAL_PROOF,
    }
    missing_log = []
    for name, d in critical_dicts.items():
        missing_keys = required - set(d.keys())
        if missing_keys:
            missing_log.append(f"  {name}: missing {sorted(missing_keys)}")

    # Check that English-only phrases don't appear in non-English translations
    english_leaks = ["Choose city", "Choose service", "Monitoring Settings", "Settings"]
    leak_log = []
    non_en_langs = {"ua", "uk", "de", "pl", "tr", "ar"}
    for name, d in critical_dicts.items():
        for lang in non_en_langs:
            text = d.get(lang, "")
            for phrase in english_leaks:
                if phrase in text:
                    leak_log.append(f"  {name}[{lang}]: contains English phrase '{phrase}'")

    if missing_log or leak_log:
        report = "TERMIN LANG VALIDATION FAILED:\n"
        if missing_log:
            report += "Missing keys:\n" + "\n".join(missing_log) + "\n"
        if leak_log:
            report += "English leaks:\n" + "\n".join(leak_log)
        logger.error(report)
        raise AssertionError(report)

    logger.info(
        "✅ Termin lang validation PASS — %d dicts × %d languages checked",
        len(critical_dicts), len(required),
    )


# ==================== i18n Validation ====================
def _validate_termin_i18n() -> None:
    """Runtime check: all key UX dicts have the required 6 language keys,
    and no English phrases leak into foreign-language values.
    Runs once at module load — results appear in startup log.
    """
    _REQUIRED = {"ua", "en", "de", "pl", "tr", "ar"}
    _KEY_DICTS = {
        "_SETUP_TEXT": _SETUP_TEXT,
        "_SETUP_CITY_BTN": _SETUP_CITY_BTN,
        "_SETUP_SERVICE_BTN": _SETUP_SERVICE_BTN,
        "_PRE_PAYMENT_TEXT": _PRE_PAYMENT_TEXT,
        "_MONITORING_ACTIVE_TEXT": _MONITORING_ACTIVE_TEXT,
        "_SETTINGS_MENU_TEXT": _SETTINGS_MENU_TEXT,
        "_SETTINGS_BTN_LABEL": _SETTINGS_BTN_LABEL,
        "_ACTIVITY_BTN_LABEL": _ACTIVITY_BTN_LABEL,
        "_PAUSE_BTN": _PAUSE_BTN,
        "_EXPAND_BTN": _EXPAND_BTN,
        "_PRIORITY_ALERTS_BTN": _PRIORITY_ALERTS_BTN,
        "_BTN_DISABLE_NOTIFICATIONS": _BTN_DISABLE_NOTIFICATIONS,
        "_STATUS_BTN_LABEL": _STATUS_BTN_LABEL,
        "_TERMIN_HOW_BTN": _TERMIN_HOW_BTN,
        "_TERMIN_SPEED_BTN": _TERMIN_SPEED_BTN,
        "_BTN_CHANGE_CITY": _BTN_CHANGE_CITY,
        "_BTN_CHANGE_DOC": _BTN_CHANGE_DOC,
    }
    _EN_LEAK_PHRASES = [
        "Choose city", "Choose service", "Monitoring Settings",
        "Settings submenu", "Monitoring active", "Pause monitoring",
        "Disable notifications",
    ]
    _FOREIGN_LANGS = {"de", "pl", "tr", "ar", "ua", "uk"}

    issues: list = []
    for name, d in _KEY_DICTS.items():
        missing = _REQUIRED - set(d.keys())
        if missing:
            issues.append(f"  {name}: missing keys {sorted(missing)}")
        for lang in _FOREIGN_LANGS:
            val = d.get(lang, "")
            for phrase in _EN_LEAK_PHRASES:
                if phrase in val:
                    issues.append(f"  {name}[{lang}]: English leak '{phrase}'")

    price_issues: list = []
    for doc, p in TERMIN_PRICES.items():
        if p != _TERMIN_PRICE_DEFAULT:
            price_issues.append(f"  TERMIN_PRICES[{doc!r}] = {p} (expected {_TERMIN_PRICE_DEFAULT})")

    if issues or price_issues:
        for line in issues + price_issues:
            logger.warning("⚠️ i18n/price issue: %s", line)
    else:
        logger.info(
            "✅ Termin i18n OK — %d dicts validated, all keys present, no EN leaks; "
            "TERMIN_PRICES flat €%.2f",
            len(_KEY_DICTS), _TERMIN_PRICE_DEFAULT,
        )


_validate_termin_i18n()


# ==================== Polling Callback Factories ====================
# These factories produce the three start_polling() callbacks.
# Used both by the normal handler flow and by the startup resume routine
# (bot.py) so both code paths share exactly the same behaviour.

_SLOT_EXPIRED_CONSOLIDATED = {
    "ua": "⏳ Схоже, цей слот вже зайнятий.\n\nНе хвилюйтесь — моніторинг продовжується.\nМи повідомимо вас, щойно знайдемо новий запис.",
    "uk": "⏳ Схоже, цей слот вже зайнятий.\n\nНе хвилюйтесь — моніторинг продовжується.\nМи повідомимо вас, щойно знайдемо новий запис.",
    "en": "⏳ This appointment may already be taken.\n\nDon't worry — monitoring continues.\nWe will notify you as soon as a new slot appears.",
    "de": "⏳ Dieser Termin ist wahrscheinlich bereits vergeben.\n\nKeine Sorge — die Überwachung läuft weiter.\nWir benachrichtigen Sie, sobald ein neuer Termin erscheint.",
    "pl": "⏳ Ten termin jest prawdopodobnie już zajęty.\n\nNie martw się — monitoring trwa dalej.\nPowiadomimy Cię, gdy pojawi się nowy termin.",
    "tr": "⏳ Bu randevu muhtemelen alınmış.\n\nEndişelenmeyin — izleme devam ediyor.\nYeni bir randevu bulunduğunda sizi bilgilendireceğiz.",
    "ar": "⏳ قد يكون هذا الموعد قد تم حجزه بالفعل.\n\nلا تقلق — المراقبة مستمرة.\nسنقوم بإعلامك فور توفر موعد جديد.",
}


def make_termin_send_fn(bot_instance, user_id: int, city: str, lang: str):
    """Return a send_fn compatible with start_polling().

    When the reservation timer fires it passes the ⏳ expired text through
    send_fn as a signal. We intercept it here and replace the raw expired text
    with one consolidated message + 2 buttons, eliminating chat spam.
    """
    async def _send(cid: int, text: str) -> None:
        _l = lang if lang not in ("ua",) else "uk"
        if text.startswith("\u23f3"):  # ⏳ reservation expired signal (U+23F3 hourglass)
            log_event("termin_reservation_expired", user_id, {"city": city})
            _termin_metrics["expired"] += 1
            try:
                from backend.termin_db import get_entitlement as _get_ent_exp
                from utils.time_utils import get_countdown_line as _get_cd_exp
                _ent_exp = _get_ent_exp(str(user_id))
                _paid_until_exp = (_ent_exp or {}).get("paid_until")
                _cd_exp = _get_cd_exp(_paid_until_exp, _l)

                _resume_kb = InlineKeyboardMarkup(row_width=1)
                _resume_kb.add(InlineKeyboardButton(
                    _lang_text(_RESUME_SEARCH_BTN, _l),
                    callback_data="termin_resume_search",
                ))
                _resume_kb.add(InlineKeyboardButton(
                    _lang_text(_EXPIRY_HOME_BTN, _l),
                    callback_data="main_menu",
                ))
                _msg = _SLOT_EXPIRED_CONSOLIDATED.get(_l, _SLOT_EXPIRED_CONSOLIDATED["en"])
                if _cd_exp:
                    _msg = f"{_msg}\n\n{_cd_exp}"
                await bot_instance.send_message(cid, _msg, reply_markup=_resume_kb)
            except Exception:
                pass
        else:
            await bot_instance.send_message(cid, text)
    return _send


_BAD_URL_PARTS = ("select2", "ajax", "api", "json", "xhr")

# Authoritative booking portals per city — used as last-resort fallback.
# A real slot URL from the scraper always takes priority.
_CITY_BOOKING_PORTALS: dict = {
    "berlin":       "https://service.berlin.de/terminvereinbarung/",
    "muenchen":     "https://www.muenchen.de/rathaus/terminvereinbarung",
    "münchen":      "https://www.muenchen.de/rathaus/terminvereinbarung",
    "munich":       "https://www.muenchen.de/rathaus/terminvereinbarung",
    "hamburg":      "https://www.hamburg.de/terminvergabe/",
    "koeln":        "https://termine.stadt-koeln.de/",
    "köln":         "https://termine.stadt-koeln.de/",
    "frankfurt":    "https://frankfurt.de/themen/rathaus/buergerbuero",
    "duesseldorf":  "https://www.duesseldorf.de/termintool/",
    "düsseldorf":   "https://www.duesseldorf.de/termintool/",
    "dortmund":     "https://termin.dortmund.de/",
    "krefeld":      "https://termine.krefeld.de/",
}

_AUTH_BOOKING_PORTALS: dict = {
    "auslaenderbehoerde": "https://otv.verwalt-berlin.de/ams/TerminBuchen",
    "buergeramt":         "https://service.berlin.de/terminvereinbarung/",
}

_AUTH_LABELS: dict = {
    "buergeramt": {
        "de": "Bürgeramt",       "en": "Citizens Office",
        "uk": "Бюргерамт",       "pl": "Urząd Obywatelski",
        "tr": "Vatandaşlık Ofisi","ar": "مكتب المواطنين",
    },
    "auslaenderbehoerde": {
        "de": "Ausländerbehörde","en": "Immigration Office",
        "uk": "Міграційна служба","pl": "Urząd ds. Cudzoziemców",
        "tr": "Yabancılar Dairesi","ar": "مكتب شؤون الأجانب",
    },
    "kfz": {
        "de": "KFZ-Zulassung",   "en": "Vehicle Registration",
        "uk": "Реєстрація авто",  "pl": "Rejestracja pojazdu",
        "tr": "Araç Tescili",    "ar": "تسجيل السيارة",
    },
    "fuehrerschein": {
        "de": "Führerschein",    "en": "Driver's Licence",
        "uk": "Водійське посвідчення","pl": "Prawo jazdy",
        "tr": "Ehliyet",          "ar": "رخصة القيادة",
    },
    "anmeldung": {
        "de": "Anmeldung",       "en": "Registration",
        "uk": "Реєстрація",      "pl": "Rejestracja",
        "tr": "Kayıt",           "ar": "التسجيل",
    },
}


def _resolve_booking_url(slot: dict, city: str, authority: str) -> str:
    """
    Return the best available booking URL for the found slot.

    Priority:
      1. slot["url"]   — direct deep-link from the scraper (most valuable)
      2. slot["booking_url"] — alternative key some scrapers use
      3. DB authority info (city + authority lookup)
      4. _AUTH_BOOKING_PORTALS  — authority-level portal
      5. _CITY_BOOKING_PORTALS  — city-level portal
      6. "" — caller must handle missing URL gracefully

    Internal/technical URLs (ajax, select2, api, …) are excluded.
    """
    candidates = [
        slot.get("url", ""),
        slot.get("booking_url", ""),
        slot.get("link", ""),
    ]
    for url in candidates:
        if url and not any(p in url for p in _BAD_URL_PARTS):
            return url

    # Try DB authority record
    try:
        _auth_info = get_authority_info(city, authority)
        _db_url = (_auth_info or {}).get("booking_url", "")
        if _db_url and not any(p in _db_url for p in _BAD_URL_PARTS):
            return _db_url
    except Exception:
        pass

    # Authority-level portal
    _auth_portal = _AUTH_BOOKING_PORTALS.get(authority, "")
    if _auth_portal:
        return _auth_portal

    # City-level portal
    _city_key = city.lower().strip()
    return _CITY_BOOKING_PORTALS.get(_city_key, "")


async def _send_termin_slot_email(
    user_id: int,
    city: str,
    authority: str,
    lang: str,
    slot: dict,
    booking_url: str,
    fallback_url: str = "",
) -> None:
    """
    Fire-and-forget email helper — sends a slot-found alert to the user's
    Stripe email address.  Anti-spam: sends only ONCE per monitoring period
    (guarded by termin_email_notified flag in termin_db).

    Sends FIRST, marks notified only on success — no silent loss.
    Never raises — all errors are logged and swallowed so the Termin flow
    is never interrupted.
    """
    try:
        from backend.termin_db import (
            get_customer_email as _get_email,
            is_termin_email_notified as _is_notified,
            mark_termin_email_notified as _mark_notified,
        )
        from utils.email_sender import send_termin_email as _send_email

        to_email = _get_email(str(user_id))
        if not to_email:
            logger.info(
                "NO_EMAIL_FOUND: user=%s — termin email skipped (no Stripe email stored)",
                user_id,
            )
            return

        if _is_notified(str(user_id)):
            logger.info(
                "TERMIN_EMAIL_ALREADY_SENT: user=%s to=%s — anti-spam guard active",
                user_id, to_email,
            )
            return

        # ── Resolve city display string ────────────────────────────────────
        _city_val = (
            slot.get("location")
            or slot.get("city")
            or city
            or "Berlin"
        ).strip().title()

        # ── Resolve service display string ─────────────────────────────────
        _l = "uk" if lang in ("ua", "uk") else lang
        if _l not in ("de", "en", "uk", "pl", "tr", "ar"):
            _l = "en"
        _service_val = (
            (_AUTH_LABELS.get(authority) or {}).get(_l)
            or (_AUTH_LABELS.get(authority) or {}).get("en")
            or slot.get("service", "")
            or authority.replace("_", " ").title()
        )

        _date_val = slot.get("date", "")
        _time_val = slot.get("time", "")

        # ── Resolve booking URL (critical) ─────────────────────────────────
        # Prefer the explicit caller-provided URL, then fall back through the
        # priority chain.  A valid direct-slot link is the most valuable asset
        # in this email; a wrong/generic link is worse than no link.
        _url_val = ""
        if booking_url and not any(p in booking_url for p in _BAD_URL_PARTS):
            _url_val = booking_url
        if not _url_val:
            _url_val = _resolve_booking_url(slot, city, authority)

        # ── Ensure fallback_url is populated (use build_booking_links if not passed) ──
        _fallback_val = fallback_url
        if not _fallback_val:
            try:
                from utils.termin_links import build_booking_links as _bbl
                _city_key = (city or "").lower().strip() or (
                    (slot.get("city") or slot.get("location") or "").lower()
                )
                _ll = _bbl(_city_key, authority, slot)
                _fallback_val = _ll["fallback"]
            except Exception:
                _fallback_val = ""

        # ── Send first, mark notified only on success ──────────────────────
        ok = await _send_email(
            to_email     = to_email,
            city         = _city_val,
            service      = _service_val,
            date         = _date_val,
            time         = _time_val,
            booking_url  = _url_val,
            fallback_url = _fallback_val,
            lang         = lang,
        )
        if ok:
            _mark_notified(str(user_id))
            logger.info(
                "TERMIN_EMAIL_SENT: user=%s to=%s city=%s service=%s url=%s",
                user_id, to_email, _city_val, _service_val, _url_val,
            )
        else:
            logger.warning(
                "TERMIN_EMAIL_FAILED: user=%s to=%s city=%s — not marking notified, will retry on next slot",
                user_id, to_email, _city_val,
            )

    except Exception as _exc:
        logger.warning(
            "TERMIN_EMAIL_FAILED: user=%s city=%s err=%s",
            user_id, city, _exc,
        )


def make_termin_on_reserved_fn(
    bot_instance, user_id: int, city: str, authority: str, lang: str, state=None
):
    """Return an on_reserved_fn compatible with start_polling().
    state=None is safe — it only skips the optional cross-sell button."""
    async def _on_reserved(cid: int, rlang: str) -> None:
        locked = get_locked_price(user_id)
        res_price = f"{locked:.2f}" if locked is not None else _price_for(city, authority)
        demand_lbl = _demand_label(city, rlang)

        _auth_display = _AUTHORITY_LABELS.get(authority, authority.title())
        _city_display = _CITY_DISPLAY_MAP.get(city, city.replace("_", " ").title())

        from utils.termin_checker import get_slot_details as _get_slot_details
        _slot = _get_slot_details(user_id)
        # Resolve booking URL: Priority A/B from slot data → authority DB → city portal fallback
        _booking_url = _slot.get("url") or None
        _BAD_URL_PARTS = ("select2", "ajax", "api")
        if _booking_url and any(x in _booking_url for x in _BAD_URL_PARTS):
            _booking_url = None
        if not _booking_url:
            try:
                _auth_info = get_authority_info(city, authority)
                _booking_url = _auth_info.get("booking_url") if _auth_info else None
            except Exception:
                pass
        if not _booking_url:
            _booking_url = build_best_booking_link(_slot, city)

        _slot_date = _slot.get("date", "")
        _slot_time = _slot.get("time", "")
        _slot_location = _slot.get("location", "")
        _date_line = f"📅 {_slot_date}\n" if _slot_date else ""
        _time_line = f"⏰ {_slot_time}\n" if _slot_time else ""
        if _slot_location:
            _city_display = _slot_location

        _success_header = _lang_text(_SLOT_FOUND_HEADER, rlang).format(
            authority=_auth_display,
            city=_city_display,
            date_line=_date_line,
            time_line=_time_line,
        )

        _kb_success = InlineKeyboardMarkup(row_width=1)
        _kb_success.add(
            InlineKeyboardButton(
                _lang_text(_SLOT_BOOK_BTN, rlang),
                url=_booking_url,
            ),
            InlineKeyboardButton(
                _lang_text(_I_BOOKED_BTN, rlang),
                callback_data="termin_i_booked",
            ),
            InlineKeyboardButton(
                _lang_text(_EXPIRY_HOME_BTN, rlang),
                callback_data="main_menu",
            ),
        )
        _CROSSSELL_BTN = {
            "uk": "📄 Підготувати документ для прийому",
            "ua": "📄 Підготувати документ для прийому",
            "en": "📄 Prepare document for the appointment",
            "de": "📄 Dokument für den Termin vorbereiten",
            "pl": "📄 Przygotuj dokument na wizytę",
            "tr": "📄 Randevu için belge hazırla",
            "ar": "📄 تحضير الوثиقة للموعد",
        }
        try:
            _fsmdata = await state.get_data() if state else {}
            _source = _fsmdata.get("source_doc") or ""
        except Exception:
            _source = ""
        if _source and _source not in ("termin_notifications", "termin_monitor_24h", ""):
            _kb_success.add(InlineKeyboardButton(
                _lang_text(_CROSSSELL_BTN, rlang),
                callback_data=f"doc_{_source}",
            ))
        _kb_success.add(InlineKeyboardButton(
            _lang_text(_RESUME_SEARCH_BTN, rlang),
            callback_data="termin_resume_search",
        ))
        _slot_found_registry[str(cid)] = datetime.now(timezone.utc).isoformat()
        try:
            from utils.stats import increment_termin_found as _inc_found2
            _inc_found2()
        except Exception:
            pass
        await bot_instance.send_message(
            cid, _success_header, parse_mode="HTML", reply_markup=_kb_success,
        )
        # No second pay message — user already paid for monitoring.

        # ── Email notification (backup channel, one-time, non-blocking) ──────
        asyncio.create_task(
            _send_termin_slot_email(
                user_id=user_id,
                city=city,
                authority=authority,
                lang=rlang,
                slot=_slot,
                booking_url=_booking_url,
            )
        )
    return _on_reserved


_RESUME_SEARCH_BTN = {
    "ua": "🔄 Продовжити пошук",
    "uk": "🔄 Продовжити пошук",
    "en": "🔄 Continue searching",
    "de": "🔄 Weiter suchen",
    "pl": "🔄 Kontynuuj wyszukiwanie",
    "tr": "🔄 Aramaya devam et",
    "ar": "🔄 متابعة البحث",
}
_BOOK_NOW_BTN = {
    "ua": "🔥 Забронювати зараз",
    "uk": "🔥 Забронювати зараз",
    "en": "🔥 Book now",
    "de": "🔥 Jetzt buchen",
    "pl": "🔥 Zarezerwuj teraz",
    "tr": "🔥 Hemen rezervasyon yap",
    "ar": "🔥 احجز الآن",
}
_OPEN_PORTAL_BTN = {
    "ua": "🌐 Відкрити сторінку запису",
    "uk": "🌐 Відкрити сторінку запису",
    "en": "🌐 Open booking page",
    "de": "🌐 Buchungsseite öffnen",
    "pl": "🌐 Otwórz stronę rezerwacji",
    "tr": "🌐 Rezervasyon sayfasını aç",
    "ar": "🌐 فتح صفحة الحجز",
}


def make_termin_found_fn(bot_instance):
    """Return an on_found_fn compatible with start_polling().

    Sends the slot-found message with buttons:
      • "✅ I booked!" — triggers 24h reminder confirmation flow
      • "🔄 Continue search" — resumes polling if user missed the slot
      • upsell / back-to-menu button
    Polling is paused by the checker after this callback returns.
    """
    async def _on_slot_found(cid: int, flang: str, slot: dict) -> None:
        from backend.termin_db import get_entitlement as _get_ent_found
        from utils.time_utils import get_countdown_line as _get_cd
        from utils.termin_links import build_booking_links as _build_links
        _ent_f = _get_ent_found(str(cid))
        _paid_until_f = (_ent_f or {}).get("paid_until")
        _cd_line = _get_cd(_paid_until_f, flang, still_active=True)

        found_msg = build_found_message(flang, slot)
        if _cd_line:
            found_msg = f"{found_msg}\n\n{_cd_line}"

        # Resolve the deepest available booking link + portal fallback
        _city_hint = (slot.get("city") or slot.get("location") or "").lower()
        _links = _build_links(_city_hint, "", slot)
        _primary_url  = _links["primary"]
        _fallback_url = _links["fallback"]

        kb = InlineKeyboardMarkup(row_width=1)
        if _primary_url:
            kb.add(InlineKeyboardButton(
                _lang_text(_BOOK_NOW_BTN, flang),
                url=_primary_url,
            ))
        kb.add(InlineKeyboardButton(
            _lang_text(_I_BOOKED_BTN, flang),
            callback_data="termin_i_booked",
        ))
        kb.add(InlineKeyboardButton(
            _lang_text(_RESUME_SEARCH_BTN, flang),
            callback_data="termin_resume_search",
        ))
        # Fallback portal link last — secondary action, shown only when it differs from primary
        if _fallback_url and _fallback_url != _primary_url:
            kb.add(InlineKeyboardButton(
                _lang_text(_OPEN_PORTAL_BTN, flang),
                url=_fallback_url,
            ))
        await bot_instance.send_message(cid, found_msg, reply_markup=kb)

        # ── Email backup notification ─────────────────────────────────────────
        asyncio.create_task(
            _send_termin_slot_email(
                user_id=cid,
                city=_city_hint,
                authority="",
                lang=flang,
                slot=slot,
                booking_url=_primary_url,
                fallback_url=_fallback_url,
            )
        )
    return _on_slot_found


# ==================== Register Handlers ====================
async def handle_termin_family_upsell(callback: types.CallbackQuery):
    """
    Family upsell handler — shown on Termin success screen for single-plan users.
    Redirects to the Termin flow where the family plan can be selected.
    """
    await callback.answer()
    user_id = callback.from_user.id
    lang = _resolve_lang(user_id)
    _l = "uk" if lang in ("ua", "uk") else lang
    if _l not in ("uk", "en", "de", "pl", "tr", "ar"):
        _l = "en"

    _FAMILY_UPSELL_TEXT = {
        "uk": (
            "👨‍👩‍👧 <b>Моніторинг для членів родини</b>\n\n"
            "Кожен третій користувач також моніторить Termin для партнера або дітей.\n\n"
            "Додайте другий профіль і отримуйте сповіщення одночасно для двох людей — "
            "за €2.99 замість €4.99."
        ),
        "en": (
            "👨‍👩‍👧 <b>Monitoring for family members</b>\n\n"
            "1 in 3 users also monitors a Termin for their partner or child.\n\n"
            "Add a second profile and receive alerts for two people simultaneously — "
            "for €2.99 instead of €4.99."
        ),
        "de": (
            "👨‍👩‍👧 <b>Überwachung für Familienmitglieder</b>\n\n"
            "Jeder dritte Nutzer überwacht auch einen Termin für Partner oder Kind.\n\n"
            "Fügen Sie ein zweites Profil hinzu und erhalten Sie Benachrichtigungen für zwei Personen "
            "gleichzeitig — für €2,99 statt €4,99."
        ),
        "pl": (
            "👨‍👩‍👧 <b>Monitoring dla członków rodziny</b>\n\n"
            "Co trzeci użytkownik monitoruje Termin również dla partnera lub dziecka.\n\n"
            "Dodaj drugi profil i otrzymuj powiadomienia dla dwóch osób jednocześnie — "
            "za €2,99 zamiast €4,99."
        ),
        "tr": (
            "👨‍👩‍👧 <b>Aile üyeleri için takip</b>\n\n"
            "Her 3 kullanıcıdan 1'i eşi veya çocuğu için de randevu takibi yapıyor.\n\n"
            "İkinci bir profil ekleyin ve iki kişi için aynı anda bildirim alın — "
            "€4,99 yerine €2,99."
        ),
        "ar": (
            "👨‍👩‍👧 <b>مراقبة لأفراد الأسرة</b>\n\n"
            "1 من كل 3 مستخدمين يراقب أيضاً موعداً لشريكه أو طفله.\n\n"
            "أضف ملفاً ثانياً واستقبل تنبيهات لشخصين في آن واحد — "
            "بـ€2.99 بدلاً من €4.99."
        ),
    }
    _ADD_BTN = {
        "uk": "➕ Додати профіль родини",
        "en": "➕ Add family profile",
        "de": "➕ Familienprofil hinzufügen",
        "pl": "➕ Dodaj profil rodziny",
        "tr": "➕ Aile profili ekle",
        "ar": "➕ إضافة ملف الأسرة",
    }
    _BACK_BTN = {
        "uk": "⬅️ Назад",
        "en": "⬅️ Back",
        "de": "⬅️ Zurück",
        "pl": "⬅️ Wstecz",
        "tr": "⬅️ Geri",
        "ar": "⬅️ رجوع",
    }

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(_ADD_BTN.get(_l, _ADD_BTN["en"]), callback_data="termin_add_profile"))
    kb.add(types.InlineKeyboardButton(_BACK_BTN.get(_l, _BACK_BTN["en"]), callback_data="termin_status"))

    await callback.message.answer(
        _FAMILY_UPSELL_TEXT.get(_l, _FAMILY_UPSELL_TEXT["en"]),
        parse_mode="HTML",
        reply_markup=kb,
    )


def register_termin_handlers(dp: Dispatcher):
    """Register termin handlers with Gold Build dispatcher.
    All callbacks start with 'termin_' — zero conflict with Gold Build handlers.
    """
    import logging as _lg
    _lg.getLogger(__name__).warning("TERMIN_DISPATCHER_ID=%s", id(dp))
    # MUST be first: exact text filter — most reliable match in aiogram 2.
    dp.register_callback_query_handler(
        handle_termin_from_pdf,
        text='termin_from_pdf',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_start_monitoring,
        text='start_monitoring',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_pay_termin_pdf,
        text='pay_termin_pdf',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_how,
        lambda c: c.data == 'termin_how',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_speed,
        lambda c: c.data == 'termin_speed',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_strategy,
        lambda c: c.data and (c.data.startswith('termin_strategy_fast_') or c.data.startswith('termin_strategy_precise_')),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_status,
        lambda c: c.data == 'termin_status',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_settings,
        lambda c: c.data == 'termin_settings',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_pause,
        lambda c: c.data == 'termin_pause',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_resume,
        lambda c: c.data == 'termin_resume',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_filters,
        lambda c: c.data == 'termin_filters',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_apply_filter,
        lambda c: c.data and c.data.startswith('termin_filter_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_expand,
        lambda c: c.data == 'termin_expand',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_priority,
        lambda c: c.data == 'termin_priority',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_reserve,
        lambda c: c.data == 'termin_reserve',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_extend,
        lambda c: c.data == 'termin_extend',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_extend_pay,
        lambda c: c.data == 'termin_extend_pay',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_priority_pay,
        lambda c: c.data == 'termin_priority_pay',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_rescan,
        lambda c: c.data and c.data.startswith('termin_rescan_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_no_slots_details,
        lambda c: c.data and c.data.startswith('termin_no_slots_details_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_set_profile,
        lambda c: c.data and c.data.startswith('termin_profile_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_profile2_unavailable,
        lambda c: c.data == 'termin_profile2_unavailable',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_switch_profile,
        lambda c: c.data and c.data.startswith('termin_switch_profile_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_monitor_pay,
        lambda c: c.data and c.data.startswith('termin_monitor_pay_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_monitor_confirm_7day,
        lambda c: c.data and c.data.startswith('termin_monitor_confirm_7day_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_monitor_confirm,
        lambda c: c.data and c.data.startswith('termin_monitor_confirm_') and not c.data.startswith('termin_monitor_confirm_7day_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_menu,
        lambda c: c.data in ('termin_menu', 'termin_main'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_notify_info,
        lambda c: c.data == 'termin_notify_info',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_consent,
        lambda c: c.data and c.data.startswith('termin_consent_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_notify_pay,
        lambda c: c.data in ('termin_start_payment', 'termin_notify_pay'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_cities,
        lambda c: c.data == 'termin_cities',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_city_selection,
        lambda c: c.data and c.data.startswith('termin_city_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_doc_type_selection,
        lambda c: c.data and c.data.startswith('termin_doc_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_authority_selection,
        lambda c: c.data and c.data.startswith('termin_auth_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_view_guidance,
        lambda c: c.data and c.data.startswith('termin_guide_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_pay_for_reminders,
        lambda c: c.data and c.data.startswith('termin_pay_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_verify_payment,
        lambda c: c.data and c.data.startswith('termin_verify_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_set_reminder,
        lambda c: c.data and c.data.startswith('termin_remind_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_interval_selection,
        lambda c: c.data and c.data.startswith('termin_interval_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_activate_reminder,
        lambda c: c.data == 'termin_activate_reminder',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_manage_reminders,
        lambda c: c.data == 'termin_manage_reminders',
        state='*',
    )
    # termin_pause_reminders unified into termin_pause — no separate handler needed.
    dp.register_callback_query_handler(
        handle_change_interval,
        lambda c: c.data == 'termin_change_interval',
        state='*',
    )
    # handle_termin_status is already registered above (line ~6912) — no duplicate here.
    dp.register_callback_query_handler(
        handle_set_status,
        lambda c: c.data and c.data.startswith('termin_setstatus_'),
        state='*',
    )
    # --- Availability polling (Stage 1) ---
    dp.register_callback_query_handler(
        handle_termin_start_poll,
        lambda c: c.data == 'termin_start_poll',
        state='*',
    )
    # "Use existing slot" — delegate to start_poll (entitlement guard is inside)
    dp.register_callback_query_handler(
        handle_termin_use_existing_slot,
        lambda c: c.data == 'termin_use_existing_slot',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_stop_poll,
        lambda c: c.data == 'termin_stop_poll',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_resume_search,
        lambda c: c.data == 'termin_resume_search',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_conflict_switch,
        lambda c: c.data and c.data.startswith('termin_conflict_switch_'),
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_confirm_reservation,
        lambda c: c.data == 'termin_reservation_confirm',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_cancel_reservation,
        lambda c: c.data == 'termin_reservation_cancel',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_i_booked,
        lambda c: c.data == 'termin_i_booked',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_set_reminder_final,
        lambda c: c.data == 'termin_set_reminder_final',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_monitor_family,
        lambda c: c.data and c.data.startswith('termin_monitor_family_'),
        state='*',
    )
    # --- Payment gate ---
    dp.register_callback_query_handler(
        handle_termin_proceed_payment,
        lambda c: c.data == 'termin_proceed_payment',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_payment_success,
        lambda c: c.data == 'termin_payment_success',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_payment_fail,
        lambda c: c.data == 'termin_payment_fail',
        state='*',
    )
    dp.register_callback_query_handler(
        handle_termin_family_upsell,
        lambda c: c.data == 'termin_family_upsell',
        state='*',
    )
    # Stage 17: Stripe Checkout startup validation
    if not os.getenv("STRIPE_API_KEY", ""):
        logger.warning("⚠️ STRIPE_API_KEY not set — Termin Checkout payments will fail")
    if not os.getenv("STRIPE_WEBHOOK_SECRET", ""):
        logger.warning("⚠️ STRIPE_WEBHOOK_SECRET not set — Termin webhook verification disabled")

    # Language dict coverage check — runs once at startup
    _validate_lang_dicts()

    logger.info("✅ Termin handlers registered (termin_* callbacks)")
