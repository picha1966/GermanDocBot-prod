"""
Spain Test Bot — Stripe payment handling.

Provides:
  PLANS                    — plan definitions (price, attempts, labels)
  paid_users               — in-memory active subscriptions
  is_paid(user_id)         — True if user has attempts remaining
  get_record(user_id)      — full record or None
  activate(...)            — mark user as paid (stores attempts_left)
  get_attempts_left(uid)   — remaining attempts count
  decrement_attempts(uid)  — use one attempt, returns new count
  create_checkout_session(...) — returns Stripe checkout URL
  send_payment_success(...)    — sends activation message via bot
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ── Plan definitions ──────────────────────────────────────────────────────────
# Attempt-based model: each plan gives N cita notifications.
# expires_at is set to 90 days as a safety cleanup TTL — not used for access control.

PLANS: dict[str, dict] = {
    "monitor_1cita": {
        "price_cents": 699,
        "currency":    "eur",
        "attempts":    1,
        "duration_h":  2160,   # 90 days safety TTL
    },
    "monitor_3citas": {
        "price_cents": 1499,
        "currency":    "eur",
        "attempts":    3,
        "duration_h":  2160,
    },
    "monitor_5citas": {
        "price_cents": 2499,
        "currency":    "eur",
        "attempts":    5,
        "duration_h":  2160,
    },
}

# ── Plan display names (6 languages) ─────────────────────────────────────────

_PLAN_DISPLAY: dict[str, dict[str, str]] = {
    "monitor_1cita": {
        "es": "1 cita",
        "en": "1 appointment",
        "uk": "1 запис",
        "pl": "1 termin",
        "ro": "1 programare",
        "ar": "موعد واحد",
    },
    "monitor_3citas": {
        "es": "3 citas",
        "en": "3 appointments",
        "uk": "3 записи",
        "pl": "3 terminy",
        "ro": "3 programări",
        "ar": "3 مواعيد",
    },
    "monitor_5citas": {
        "es": "5 citas",
        "en": "5 appointments",
        "uk": "5 записів",
        "pl": "5 terminów",
        "ro": "5 programări",
        "ar": "5 مواعيد",
    },
}

# ── Payment success message (6 languages) ────────────────────────────────────

_SUCCESS_TEXT: dict[str, str] = {
    "es": (
        "✅ <b>¡Pago exitoso!</b>\n"
        "🚀 <b>Búsqueda activada</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n"
        "🎯 Plan: <b>{plan}</b>\n\n"
        "⚠️ Las citas aparecen de forma aleatoria y desaparecen en 1–3 minutos\n\n"
        "🔄 Ya estamos buscando citas para ti\n"
        "⏱ Última verificación: {last_check}\n"
        "⏭ Próxima verificación: {next_check}\n\n"
        "📲 Te avisaremos al instante cuando aparezca una cita\n"
        "👉 Puedes cerrar el bot — te notificaremos de todas formas\n\n"
        "ℹ️ No garantizamos una cita — aumentamos tus probabilidades"
    ),
    "en": (
        "✅ <b>Payment successful!</b>\n"
        "🚀 <b>Search activated</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n"
        "🎯 Plan: <b>{plan}</b>\n\n"
        "⚠️ Appointments appear randomly and disappear within 1–3 minutes\n\n"
        "🔄 We are already searching for citas for you\n"
        "⏱ Last check: {last_check}\n"
        "⏭ Next check: {next_check}\n\n"
        "📲 You will be notified instantly when an appointment appears\n"
        "👉 You can close the bot — we will notify you anyway\n\n"
        "ℹ️ We do not guarantee a booking — we increase your chances"
    ),
    "uk": (
        "✅ <b>Оплата успішна!</b>\n"
        "🚀 <b>Пошук активовано</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n"
        "🎯 Тариф: <b>{plan}</b>\n\n"
        "⚠️ Записи з'являються випадково і зникають за 1–3 хвилини\n\n"
        "🔄 Ми вже шукаємо citas для тебе\n"
        "⏱ Остання перевірка: {last_check}\n"
        "⏭ Наступна перевірка: {next_check}\n\n"
        "📲 Як тільки з'явиться запис — ти одразу отримаєш повідомлення\n"
        "👉 Можеш закрити бот — ми все одно повідомимо\n\n"
        "ℹ️ Ми не гарантуємо запис — ми збільшуємо твої шанси"
    ),
    "pl": (
        "✅ <b>Płatność potwierdzona!</b>\n"
        "🚀 <b>Wyszukiwanie aktywowane</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n"
        "🎯 Plan: <b>{plan}</b>\n\n"
        "⚠️ Terminy pojawiają się losowo i znikają w ciągu 1–3 minut\n\n"
        "🔄 Już szukamy dla Ciebie terminów citas\n"
        "⏱ Ostatnie sprawdzenie: {last_check}\n"
        "⏭ Następne sprawdzenie: {next_check}\n\n"
        "📲 Gdy tylko pojawi się termin — natychmiast dostaniesz powiadomienie\n"
        "👉 Możesz zamknąć bota — i tak Cię powiadomimy\n\n"
        "ℹ️ Nie gwarantujemy wizyty — zwiększamy Twoje szanse"
    ),
    "ro": (
        "✅ <b>Plată confirmată!</b>\n"
        "🚀 <b>Căutare activată</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n"
        "🎯 Plan: <b>{plan}</b>\n\n"
        "⚠️ Programările apar aleatoriu și dispar în 1–3 minute\n\n"
        "🔄 Căutăm deja programări (citas) pentru tine\n"
        "⏱ Ultima verificare: {last_check}\n"
        "⏭ Următoarea verificare: {next_check}\n\n"
        "📲 Imediat ce apare o programare — primești notificare\n"
        "👉 Poți închide botul — te vom notifica oricum\n\n"
        "ℹ️ Nu garantăm o programare — îți creștem șansele"
    ),
    "ar": (
        "✅ <b>تم الدفع بنجاح!</b>\n"
        "🚀 <b>تم تفعيل البحث</b>\n\n"
        "📍 {city}\n"
        "📄 {service}\n"
        "🎯 الخطة: <b>{plan}</b>\n\n"
        "⚠️ المواعيد تظهر بشكل عشوائي وتختفي خلال 1–3 دقائق\n\n"
        "🔄 نحن نبحث بالفعل عن citas لك\n"
        "⏱ آخر فحص: {last_check}\n"
        "⏭ الفحص التالي: {next_check}\n\n"
        "📲 بمجرد ظهور موعد — سيتم إخطارك فوراً\n"
        "👉 يمكنك إغلاق البوت — سنخطرك على أي حال\n\n"
        "ℹ️ نحن لا نضمن الموعد — بل نزيد فرصك"
    ),
}

# ── Post-payment keyboard buttons (6 languages) ──────────────────────────────

_BTN_STATUS: dict[str, str] = {
    "es": "📊 Ver estado",
    "en": "📊 Check status",
    "uk": "📊 Статус моніторингу",
    "pl": "📊 Status monitoringu",
    "ro": "📊 Status monitorizare",
    "ar": "📊 حالة المراقبة",
}

_BTN_STOP: dict[str, str] = {
    "es": "⛔ Detener monitoreo",
    "en": "⛔ Stop monitoring",
    "uk": "⛔ Зупинити моніторинг",
    "pl": "⛔ Zatrzymaj monitoring",
    "ro": "⛔ Oprește monitorizarea",
    "ar": "⛔ إيقاف المراقبة",
}

_BTN_MAIN_MENU: dict[str, str] = {
    "es": "🏠 Menú principal",
    "en": "🏠 Main menu",
    "uk": "🏠 Головне меню",
    "pl": "🏠 Menu główne",
    "ro": "🏠 Meniu principal",
    "ar": "🏠 القائمة الرئيسية",
}

# ── Attempts exhausted message (6 languages) ─────────────────────────────────

_EXPIRED_TEXT: dict[str, str] = {
    "es": (
        "⛔ <b>Todas las oportunidades utilizadas</b>\n\n"
        "Has usado todas tus citas de este plan.\n"
        "¿Quieres seguir buscando?"
    ),
    "en": (
        "⛔ <b>All attempts used</b>\n\n"
        "You have used all appointments from this plan.\n"
        "Want to keep searching?"
    ),
    "uk": (
        "⛔ <b>Усі спроби використано</b>\n\n"
        "Ти використав усі записи з цього тарифу.\n"
        "Хочеш продовжити пошук?"
    ),
    "pl": (
        "⛔ <b>Wszystkie próby wykorzystane</b>\n\n"
        "Wykorzystałeś wszystkie terminy z tego planu.\n"
        "Chcesz kontynuować wyszukiwanie?"
    ),
    "ro": (
        "⛔ <b>Toate încercările utilizate</b>\n\n"
        "Ai folosit toate programările din acest plan.\n"
        "Vrei să continui căutarea?"
    ),
    "ar": (
        "⛔ <b>تم استخدام جميع المحاولات</b>\n\n"
        "لقد استخدمت جميع المواعيد من هذه الخطة.\n"
        "هل تريد الاستمرار في البحث؟"
    ),
}

# ── Attempts remaining notification (6 languages) ────────────────────────────

_ATTEMPTS_LEFT_TEXT: dict[str, str] = {
    "es": "🔄 Te quedan <b>{n}</b> citas en tu plan",
    "en": "🔄 You have <b>{n}</b> appointments left in your plan",
    "uk": "🔄 У тебе залишилось <b>{n}</b> спроб у тарифі",
    "pl": "🔄 Zostało Ci <b>{n}</b> terminów w planie",
    "ro": "🔄 Îți mai rămân <b>{n}</b> programări în plan",
    "ar": "🔄 تبقّى لديك <b>{n}</b> مواعيد في خطتك",
}


def _t(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


# ── Persistent + in-memory paid users store ───────────────────────────────────
# In-memory dict is the hot cache; SQLite is the durable backing store.
# On module import we warm the cache from SQLite so restarts are transparent.

from utils.payments_store import (
    db_save,
    db_load_all_active,
    db_save_pending,
    db_get_pending,
    db_clear_pending,
    db_update_attempts_left,
)

paid_users: dict[int, dict] = db_load_all_active()   # warm cache on startup


def is_paid(user_id: int) -> bool:
    """True if user has attempts remaining (attempt-based model)."""
    rec = paid_users.get(user_id)
    if rec and rec.get("attempts_left", 0) > 0:
        return True
    # Cache miss → check DB
    from utils.payments_store import db_load_record
    db_rec = db_load_record(user_id)
    if db_rec and db_rec.get("attempts_left", 0) > 0:
        paid_users[user_id] = db_rec
        return True
    return False


def get_record(user_id: int) -> dict | None:
    """Return the paid record if still active (attempts > 0), else None."""
    if is_paid(user_id):
        return paid_users.get(user_id)
    return None


def get_attempts_left(user_id: int) -> int:
    """Return remaining attempt count for a user (0 if none)."""
    rec = paid_users.get(user_id)
    if rec:
        return rec.get("attempts_left", 0)
    from utils.payments_store import db_load_record
    db_rec = db_load_record(user_id)
    if db_rec:
        paid_users[user_id] = db_rec
        return db_rec.get("attempts_left", 0)
    return 0


def decrement_attempts(user_id: int) -> int:
    """Use one attempt. Returns the new attempts_left count."""
    rec = paid_users.get(user_id)
    if not rec:
        return 0
    current = rec.get("attempts_left", 0)
    new_val = max(0, current - 1)
    rec["attempts_left"] = new_val
    try:
        db_update_attempts_left(user_id, new_val)
    except Exception as exc:
        logger.warning("DECREMENT_ATTEMPTS_FAILED | user=%s err=%s", user_id, exc)
    logger.info("ATTEMPTS_DECREMENTED | user=%s remaining=%d", user_id, new_val)
    return new_val


def attempts_left_text(user_id: int, lang: str) -> str:
    """Localised 'X attempts left' line."""
    n = get_attempts_left(user_id)
    return _t(_ATTEMPTS_LEFT_TEXT, lang).format(n=n)


# Legacy plan name aliases (old time-based → new attempt-based equivalents)
_PLAN_ALIASES: dict[str, str] = {
    "monitor_24h": "monitor_1cita",
    "monitor_7d":  "monitor_3citas",
}


def activate(user_id: int, city: str, service: str, plan: str) -> None:
    """Create or overwrite an active subscription for this user."""
    plan = _PLAN_ALIASES.get(plan, plan)
    if plan not in PLANS:
        logger.warning("ACTIVATE_UNKNOWN_PLAN | plan=%s user=%s — using monitor_1cita fallback", plan, user_id)
        plan = "monitor_1cita"
    now           = datetime.utcnow()
    expires_at    = now + timedelta(hours=PLANS[plan]["duration_h"])
    attempts      = PLANS[plan]["attempts"]

    record = {
        "city":          city,
        "service":       service,
        "plan":          plan,
        "expires_at":    expires_at,
        "activated_at":  now,
        "attempts_left": attempts,
    }
    paid_users[user_id] = record
    db_save(user_id, city, service, plan, expires_at, now, attempts_left=attempts)
    try:
        db_clear_pending(user_id)
    except Exception:
        pass

    logger.info(
        "PAYMENT_ACTIVATED | user=%s city=%s svc=%s plan=%s attempts=%d",
        user_id, city, service, plan, attempts,
    )


def plan_display(plan: str, lang: str) -> str:
    """Localised plan duration name."""
    d = _PLAN_DISPLAY.get(plan, {})
    return _t(d, lang) if d else plan


def time_remaining(user_id: int, lang: str) -> str:
    """Human-readable remaining attempts count for a paid plan."""
    n = get_attempts_left(user_id)
    if n <= 0:
        return ""
    _FMT: dict[str, str] = {
        "es": f"{n} cita{'s' if n != 1 else ''}",
        "en": f"{n} appointment{'s' if n != 1 else ''}",
        "uk": f"{n} {'запис' if n == 1 else 'записи' if n in (2, 3, 4) else 'записів'}",
        "pl": f"{n} {'termin' if n == 1 else 'terminy' if n in (2, 3, 4) else 'terminów'}",
        "ro": f"{n} programar{'e' if n == 1 else 'i'}",
        "ar": f"{n} {'موعد' if n == 1 else 'مواعيد'}",
    }
    return _t(_FMT, lang)


def expired_text(lang: str) -> str:
    return _t(_EXPIRED_TEXT, lang)


def save_pending(
    user_id: int,
    city: str,
    svc: str,
    plan: str,
    stripe_session_id: str = "",
) -> None:
    """Persist city/service/plan (+ Stripe session ID) before Stripe opens."""
    try:
        db_save_pending(user_id, city, svc, plan, stripe_session_id=stripe_session_id)
    except Exception as exc:
        logger.warning("PENDING_SAVE_FAILED | user=%s err=%s", user_id, exc)


def get_pending(user_id: int) -> dict | None:
    """Return pre-payment state saved before Stripe opened (or None)."""
    try:
        return db_get_pending(user_id)
    except Exception as exc:
        logger.warning("PENDING_GET_FAILED | user=%s err=%s", user_id, exc)
        return None


# ── Stripe checkout session ───────────────────────────────────────────────────

async def create_checkout_session(
    user_id: int,
    city:    str,
    service: str,
    plan:    str,
    lang:    str = "en",
) -> tuple[str, str]:
    """Create a Stripe Checkout session. Returns (checkout_url, session_id)."""
    secret_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not secret_key or secret_key.startswith("PUT_"):
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    if plan not in PLANS:
        raise ValueError(f"Unknown plan: {plan}")

    # ── Metadata guard — all 4 fields are required for webhook to work ────────
    if not user_id:
        raise ValueError("user_id is required for Stripe metadata")
    if not city:
        raise ValueError("city is required for Stripe metadata")
    if not service:
        raise ValueError("service is required for Stripe metadata")

    logger.info(
        "STRIPE_SESSION_CREATING | user=%s city=%s svc=%s plan=%s lang=%s",
        user_id, city, service, plan, lang,
    )

    import stripe  # lazy import so the module loads even without stripe installed
    stripe.api_key = secret_key

    bot_username = os.getenv("BOT_USERNAME", "spaintest_citas_bot")
    plan_data    = PLANS[plan]
    plan_label   = _t(_PLAN_DISPLAY.get(plan, {"en": plan}), "en")  # always EN for Stripe

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[{
            "price_data": {
                "currency":    plan_data["currency"],
                "unit_amount": plan_data["price_cents"],
                "product_data": {
                    "name": f"Spain Citas Monitor — {plan_label}",
                },
            },
            "quantity": 1,
        }],
        metadata={
            "user_id": str(user_id),
            "city":    city,
            "service": service,
            "plan":    plan,
            "lang":    lang,
        },
        success_url=f"https://t.me/{bot_username}?start=paid_monitor",
        cancel_url=f"https://t.me/{bot_username}?start=cancel",
    )

    logger.info(
        "STRIPE_SESSION_CREATED | user=%s city=%s svc=%s plan=%s session_id=%s",
        user_id, city, service, plan, session.id,
    )
    return session.url, session.id


# ── Post-payment bot message ──────────────────────────────────────────────────

async def send_payment_success(
    bot,
    user_id:       int,
    city_display:  str,
    svc_display:   str,
    plan:          str,
    lang:          str,
    next_check:    str = "",
    last_check:    str = "",
) -> None:
    """Send activation confirmation message to user after webhook fires."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    plan_str = plan_display(plan, lang)

    # Resolve timing labels if not provided
    if not next_check:
        _next_defaults = {"es": "~30–60 seg", "en": "~30–60 sec", "uk": "~30–60 сек",
                          "pl": "~30–60 sek", "ro": "~30–60 sec", "ar": "~30–60 ث"}
        next_check = _next_defaults.get(lang, "~30–60 sec")
    if not last_check:
        _just_now = {"es": "ahora mismo", "en": "just now", "uk": "щойно",
                     "pl": "przed chwilą", "ro": "chiar acum", "ar": "للتو"}
        last_check = _just_now.get(lang, "just now")

    text = _t(_SUCCESS_TEXT, lang).format(
        city=city_display,
        service=svc_display,
        plan=plan_str,
        next_check=next_check,
        last_check=last_check,
    )

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_STATUS,    lang), callback_data="monitor_status"))
    kb.add(InlineKeyboardButton(_t(_BTN_STOP,      lang), callback_data="stop_monitor"))
    kb.add(InlineKeyboardButton(_t(_BTN_MAIN_MENU, lang), callback_data="back_to_main_menu"))

    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
        logger.info("PAYMENT_SUCCESS_SENT | user=%s plan=%s", user_id, plan)
    except Exception as exc:
        logger.error("PAYMENT_SUCCESS_SEND_FAILED | user=%s err=%s", user_id, exc)
