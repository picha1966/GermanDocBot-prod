"""
Spain Test Bot — payment UX handlers.

Callbacks:
  buy_1cita       → create Stripe session for 1-appointment plan
  buy_3citas      → create Stripe session for 3-appointment plan
  buy_5citas      → create Stripe session for 5-appointment plan

Helper:
  show_pricing_screen(message, lang) → display plan selection
"""

from __future__ import annotations

import logging

from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.lang_store import get_lang

logger = logging.getLogger(__name__)


def _t(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


# ── Pricing screen texts (6 languages) ────────────────────────────────────────

_PRICING_HEADER: dict[str, str] = {
    "es": (
        "🎯 <b>Elige cuántas citas quieres encontrar</b>\n\n"
        "⚠️ Las citas aparecen de forma aleatoria y desaparecen en 1–3 minutos\n"
        "🤖 Revisamos cada 30–60 segundos — y te avisamos al instante\n\n"
        "1 cita = 1 notificación cuando encontremos un hueco\n"
        "📲 Puedes cerrar el bot — te avisaremos de todas formas\n\n"
        "ℹ️ No garantizamos una cita — aumentamos tus probabilidades\n\n"
        "Elige tu plan:"
    ),
    "en": (
        "🎯 <b>Choose how many appointments to find</b>\n\n"
        "⚠️ Appointments appear randomly and disappear within 1–3 minutes\n"
        "🤖 We check every 30–60 seconds — and notify you instantly\n\n"
        "1 appointment = 1 notification when we find a slot\n"
        "📲 You can close the bot — we will notify you anyway\n\n"
        "ℹ️ We do not guarantee a booking — we increase your chances\n\n"
        "Choose your plan:"
    ),
    "uk": (
        "🎯 <b>Обери скільки записів шукати</b>\n\n"
        "⚠️ Записи з'являються випадково і зникають за 1–3 хвилини\n"
        "🤖 Перевіряємо кожні 30–60 секунд — і миттєво повідомляємо\n\n"
        "1 запис = 1 повідомлення коли знайдемо вільне місце\n"
        "📲 Можеш закрити бот — ми все одно повідомимо\n\n"
        "ℹ️ Ми не гарантуємо запис — ми збільшуємо твої шанси\n\n"
        "Оберіть тариф:"
    ),
    "pl": (
        "🎯 <b>Wybierz ile terminów szukać</b>\n\n"
        "⚠️ Terminy pojawiają się losowo i znikają w ciągu 1–3 minut\n"
        "🤖 Sprawdzamy co 30–60 sekund — i powiadamiamy natychmiast\n\n"
        "1 termin = 1 powiadomienie gdy znajdziemy wolne miejsce\n"
        "📲 Możesz zamknąć bota — i tak Cię powiadomimy\n\n"
        "ℹ️ Nie gwarantujemy wizyty — zwiększamy Twoje szanse\n\n"
        "Wybierz plan:"
    ),
    "ro": (
        "🎯 <b>Alege câte programări să cauți</b>\n\n"
        "⚠️ Programările apar aleatoriu și dispar în 1–3 minute\n"
        "🤖 Verificăm la fiecare 30–60 secunde — și te notificăm instant\n\n"
        "1 programare = 1 notificare când găsim un loc liber\n"
        "📲 Poți închide botul — te vom notifica oricum\n\n"
        "ℹ️ Nu garantăm o programare — îți creștem șansele\n\n"
        "Alege planul:"
    ),
    "ar": (
        "🎯 <b>اختر كم موعدًا تريد إيجاده</b>\n\n"
        "⚠️ المواعيد تظهر بشكل عشوائي وتختفي خلال 1–3 دقائق\n"
        "🤖 نفحص كل 30–60 ثانية — ونخطرك فوراً\n\n"
        "موعد واحد = إشعار واحد عند إيجاد مكان متاح\n"
        "📲 يمكنك إغلاق البوت — سنخطرك على أي حال\n\n"
        "ℹ️ نحن لا نضمن الموعد — بل نزيد فرصك\n\n"
        "اختر خطتك:"
    ),
}

_BTN_1CITA: dict[str, str] = {
    "es": "🎯 1 cita — €6.99",
    "en": "🎯 1 appointment — €6.99",
    "uk": "🎯 1 запис — €6.99",
    "pl": "🎯 1 termin — €6.99",
    "ro": "🎯 1 programare — €6.99",
    "ar": "🎯 موعد واحد — €6.99",
}

_BTN_3CITAS: dict[str, str] = {
    "es": "🔥 3 citas — €14.99  ✅ Recomendado",
    "en": "🔥 3 appointments — €14.99  ✅ Recommended",
    "uk": "🔥 3 записи — €14.99  ✅ Рекомендується",
    "pl": "🔥 3 terminy — €14.99  ✅ Polecane",
    "ro": "🔥 3 programări — €14.99  ✅ Recomandat",
    "ar": "🔥 3 مواعيد — €14.99  ✅ موصى به",
}

_BTN_5CITAS: dict[str, str] = {
    "es": "🚀 5 citas — €24.99  💎 Máxima probabilidad",
    "en": "🚀 5 appointments — €24.99  💎 Maximum chance",
    "uk": "🚀 5 записів — €24.99  💎 Максимальний шанс",
    "pl": "🚀 5 terminów — €24.99  💎 Maksymalne szanse",
    "ro": "🚀 5 programări — €24.99  💎 Șanse maxime",
    "ar": "🚀 5 مواعيد — €24.99  💎 أقصى فرصة",
}

_BTN_BACK: dict[str, str] = {
    "es": "◀️ Volver",
    "en": "◀️ Back",
    "uk": "◀️ Назад",
    "pl": "◀️ Wróć",
    "ro": "◀️ Înapoi",
    "ar": "◀️ رجوع",
}

_PAYMENT_LINK_TEXT: dict[str, str] = {
    "es": "🔗 Completa tu pago:\n\n{url}\n\n💡 Después del pago, vuelve al bot automáticamente.",
    "en": "🔗 Complete your payment:\n\n{url}\n\n💡 After payment, you'll be returned to the bot automatically.",
    "uk": "🔗 Завершіть оплату:\n\n{url}\n\n💡 Після оплати бот активується автоматично.",
    "pl": "🔗 Dokończ płatność:\n\n{url}\n\n💡 Po płatności bot aktywuje się automatycznie.",
    "ro": "🔗 Finalizează plata:\n\n{url}\n\n💡 După plată, botul se activează automat.",
    "ar": "🔗 أكمل الدفع:\n\n{url}\n\n💡 بعد الدفع، سيُفعّل البوت تلقائياً.",
}

_PAYMENT_BTN: dict[str, str] = {
    "es": "💳 Ir al pago",
    "en": "💳 Go to payment",
    "uk": "💳 Перейти до оплати",
    "pl": "💳 Przejdź do płatności",
    "ro": "💳 Mergi la plată",
    "ar": "💳 الذهاب للدفع",
}

_STRIPE_NOT_CONFIGURED: dict[str, str] = {
    "es": "⚠️ El sistema de pago no está configurado todavía.\n\nContacta con el soporte.",
    "en": "⚠️ Payment system is not configured yet.\n\nPlease contact support.",
    "uk": "⚠️ Система оплати ще не налаштована.\n\nЗверніться до підтримки.",
    "pl": "⚠️ System płatności nie jest jeszcze skonfigurowany.\n\nSkontaktuj się z pomocą techniczną.",
    "ro": "⚠️ Sistemul de plată nu este încă configurat.\n\nContactează suportul.",
    "ar": "⚠️ نظام الدفع غير مهيأ بعد.\n\nتواصل مع الدعم.",
}


# ── Shared helper ─────────────────────────────────────────────────────────────

def pricing_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_1CITA,  lang), callback_data="buy_1cita"))
    kb.add(InlineKeyboardButton(_t(_BTN_3CITAS, lang), callback_data="buy_3citas"))
    kb.add(InlineKeyboardButton(_t(_BTN_5CITAS, lang), callback_data="buy_5citas"))
    kb.add(InlineKeyboardButton(_t(_BTN_BACK,   lang), callback_data="back_to_cities"))
    return kb


async def show_pricing_screen(message: types.Message, lang: str) -> None:
    """Display the plan selection screen."""
    await message.answer(
        _t(_PRICING_HEADER, lang),
        parse_mode="HTML",
        reply_markup=pricing_keyboard(lang),
    )


# ── Shared payment initiator ──────────────────────────────────────────────────

async def _initiate_payment(
    callback: types.CallbackQuery,
    state:    FSMContext,
    plan:     str,
) -> None:
    await callback.answer()
    lang = get_lang(callback.from_user.id)
    data = await state.get_data()

    city    = data.get("city")
    svc_key = data.get("svc")

    if not city or not svc_key:
        logger.warning("BUY_%s_NO_STATE | user=%s", plan, callback.from_user.id)
        await callback.message.answer(
            _t(_STRIPE_NOT_CONFIGURED, lang),
            parse_mode="HTML",
        )
        return

    # Persist city/svc/plan BEFORE opening Stripe so it survives if user closes app
    # (stripe_session_id will be updated below after session creation)
    try:
        from utils.payments import save_pending
        save_pending(callback.from_user.id, city, svc_key, plan)
    except Exception as _exc:
        logger.warning("PENDING_SAVE_SKIP | user=%s err=%s", callback.from_user.id, _exc)

    try:
        from utils.payments import create_checkout_session
        url, stripe_session_id = await create_checkout_session(
            user_id=callback.from_user.id,
            city=city,
            service=svc_key,
            plan=plan,
            lang=lang,
        )
        # Update pending with session_id so deeplink can verify payment via Stripe API
        try:
            from utils.payments import save_pending as _sp
            _sp(callback.from_user.id, city, svc_key, plan, stripe_session_id=stripe_session_id)
        except Exception as _sid_exc:
            logger.warning("PENDING_SESSION_ID_SAVE_SKIP | user=%s err=%s", callback.from_user.id, _sid_exc)
    except RuntimeError:
        # STRIPE_SECRET_KEY not set — dev mode
        logger.warning("STRIPE_NOT_CONFIGURED | user=%s", callback.from_user.id)
        await callback.message.answer(
            _t(_STRIPE_NOT_CONFIGURED, lang),
            parse_mode="HTML",
        )
        return
    except Exception as exc:
        logger.error("STRIPE_SESSION_FAILED | user=%s plan=%s err=%s", callback.from_user.id, plan, exc)
        await callback.message.answer(
            _t(_STRIPE_NOT_CONFIGURED, lang),
            parse_mode="HTML",
        )
        return

    # Send payment link as inline button
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_PAYMENT_BTN, lang), url=url))
    kb.add(InlineKeyboardButton(_t(_BTN_BACK,    lang), callback_data="back_to_cities"))

    msg_text = _t(_PAYMENT_LINK_TEXT, lang).format(url=url)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(msg_text, parse_mode="HTML", reply_markup=kb,
                                   disable_web_page_preview=True)
    logger.info("PAYMENT_LINK_SENT | user=%s plan=%s", callback.from_user.id, plan)


# ── Handlers ─────────────────────────────────────────────────────────────────

async def handle_buy_1cita(callback: types.CallbackQuery, state: FSMContext) -> None:
    await _initiate_payment(callback, state, "monitor_1cita")


async def handle_buy_3citas(callback: types.CallbackQuery, state: FSMContext) -> None:
    await _initiate_payment(callback, state, "monitor_3citas")


async def handle_buy_5citas(callback: types.CallbackQuery, state: FSMContext) -> None:
    await _initiate_payment(callback, state, "monitor_5citas")


# ── Registration ──────────────────────────────────────────────────────────────

def register(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(
        handle_buy_1cita,
        lambda c: c.data == "buy_1cita",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_buy_3citas,
        lambda c: c.data == "buy_3citas",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_buy_5citas,
        lambda c: c.data == "buy_5citas",
        state="*",
    )
