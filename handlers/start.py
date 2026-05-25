# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - Start & Language & GDPR Handlers
Обробка /start, вибору мови та GDPR згоди.
"""

import asyncio
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import logging
from states import DocumentState
from utils.helpers import get_user_lang, get_db
from utils.funnel_log import log_funnel
from utils.retention import RETENTION_MAIN_MENU_CB
# Note: get_intro_text/get_trust_disclaimer no longer used - using SIMPLE_INTRO_TEXTS inline

logger = logging.getLogger(__name__)

logger.debug("START.PY LOADED FROM: %s", __file__)

# ============================================================================
# PREMIUM HOOK TEXTS — shown once after language selection
# Goal: immediate value clarity + social proof + 2 direct CTAs
# NO "Open Menu" step — user chooses action directly
# ============================================================================

# Seed baseline — set to 0 so the displayed counter reflects only real paid orders.
# Increase this value only after accumulating verified real orders.
_DOC_COUNTER_SEED = 0

def _get_doc_counter() -> int:
    """
    Return total of prepared documents (paid orders) from DB.
    Falls back to seed value on any DB error.
    """
    try:
        from utils.helpers import get_db
        db = get_db()
        cur = db.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM orders WHERE status IN ('paid','sent','downloaded','processing')"
        )
        row = cur.fetchone()
        db_count = int(row[0]) if row else 0
        return _DOC_COUNTER_SEED + db_count
    except Exception:
        return _DOC_COUNTER_SEED


def _fmt_counter(n: int) -> str:
    """Format counter as '14,200+' with thousand separator."""
    return f"{n:,}+".replace(",", "\u202f")  # narrow no-break space


# Premium hook body — clear value proposition, popular docs, counter + 2 CTAs
# {counter} is replaced dynamically at render time
_HOOK_TEXTS = {
    "uk": (
        "<b>🇩🇪 Знайдемо Termin без постійної перевірки сайтів</b>\n\n"
        "🔔 <b>Як тільки зʼявиться слот:</b>\n"
        "• сповіщення в Telegram і на email — одразу після появи\n"
        "• пряме посилання для запису\n\n"
        "⚡ Не пропустиш вільний слот\n\n"
        "📄 <b>Допоможемо з документами</b>\n"
        "— щоб їх прийняли з першого разу\n\n"
        "📎 Приклад заповненого PDF\n"
        "+ офіційний бланк для подачі\n\n"
        "📩 Копія документа також надійде на email\n\n"
        "⏱ 3–5 хвилин · <b>{counter} вже скористались</b>"
    ),
    "en": (
        "<b>🇩🇪 We find your Termin — no manual site-checking</b>\n\n"
        "🔔 <b>As soon as a slot opens:</b>\n"
        "• Telegram + Email alert — the moment a slot appears\n"
        "• direct booking link\n\n"
        "⚡ You won't miss a free slot\n\n"
        "📄 <b>We help with your documents</b>\n"
        "— so they are accepted first time\n\n"
        "📎 Filled-in PDF example\n"
        "+ official blank form included\n\n"
        "📩 Document copy also sent to your email\n\n"
        "⏱ 3–5 minutes · <b>{counter} already used this</b>"
    ),
    "de": (
        "<b>🇩🇪 Wir finden Ihren Termin — ohne ständiges Prüfen</b>\n\n"
        "🔔 <b>Sobald ein Slot frei ist:</b>\n"
        "• Telegram + E-Mail — sofort nach Verfügbarkeit\n"
        "• direkter Buchungslink\n\n"
        "⚡ Keinen freien Slot verpassen\n\n"
        "📄 <b>Wir helfen mit Ihren Dokumenten</b>\n"
        "— damit sie beim ersten Mal akzeptiert werden\n\n"
        "📎 Ausgefülltes PDF-Beispiel\n"
        "+ offizielles Leerformular\n\n"
        "📩 Dokumentkopie auch per E-Mail\n\n"
        "⏱ 3–5 Minuten · <b>{counter} haben es bereits genutzt</b>"
    ),
    "pl": (
        "<b>🇩🇪 Znajdziemy Termin bez ciągłego sprawdzania stron</b>\n\n"
        "🔔 <b>Gdy tylko pojawi się slot:</b>\n"
        "• Telegram + Email — natychmiast po pojawieniu się\n"
        "• bezpośredni link do zapisu\n\n"
        "⚡ Nie przegapisz wolnego slotu\n\n"
        "📄 <b>Pomożemy z dokumentami</b>\n"
        "— żeby zostały przyjęte za pierwszym razem\n\n"
        "📎 Przykład wypełnionego PDF\n"
        "+ oficjalny pusty formularz\n\n"
        "📩 Kopia dokumentu trafi też na Twój email\n\n"
        "⏱ 3–5 minut · <b>{counter} już skorzystało</b>"
    ),
    "tr": (
        "<b>🇩🇪 Sürekli site kontrol etmeden Termin buluruz</b>\n\n"
        "🔔 <b>Randevu slotu açılır açılmaz:</b>\n"
        "• Telegram + E-posta — slot çıkar çıkmaz anında\n"
        "• doğrudan rezervasyon linki\n\n"
        "⚡ Boş slotu kaçırmazsın\n\n"
        "📄 <b>Belgelerinde yardım ederiz</b>\n"
        "— ilk seferde kabul edilsin diye\n\n"
        "📎 Doldurulmuş PDF örneği\n"
        "+ resmi boş form dahil\n\n"
        "📩 Belge kopyası e-postana da gelir\n\n"
        "⏱ 3–5 dakika · <b>{counter} kişi kullandı</b>"
    ),
    "ar": (
        "<b>🇩🇪 نجد لك Termin بدون مراجعة المواقع باستمرار</b>\n\n"
        "🔔 <b>بمجرد توفر slot:</b>\n"
        "• Telegram + البريد الإلكتروني — فور ظهور الموعد\n"
        "• رابط مباشر للحجز\n\n"
        "⚡ لن تفوّت أي slot متاح\n\n"
        "📄 <b>نساعدك في المستندات</b>\n"
        "— حتى تُقبل من المرة الأولى\n\n"
        "📎 مثال على PDF مملوء\n"
        "+ النموذج الرسمي الفارغ\n\n"
        "📩 نسخة المستند تصلك أيضاً على البريد\n\n"
        "⏱ 3–5 دقائق · <b>{counter} استخدموه بالفعل</b>"
    ),
}

# CTA button labels for the hook screen
_HOOK_DOC_BTN = {
    "uk": "📄 Заповнити документ",
    "ua": "📄 Заповнити документ",
    "en": "📄 Fill a document",
    "de": "📄 Dokument ausfüllen",
    "pl": "📄 Wypełnij dokument",
    "tr": "📄 Belge doldur",
    "ar": "📄 ملء المستند",
}
_HOOK_TERMIN_BTN = {
    "uk": "📅 Знайти Termin — 24/7",
    "ua": "📅 Знайти Termin — 24/7",
    "en": "📅 Find Termin — 24/7",
    "de": "📅 Termin finden — 24/7",
    "pl": "📅 Znajdź Termin — 24/7",
    "tr": "📅 Termin bul — 24/7",
    "ar": "📅 إيجاد Termin — 24/7",
}

# ── Returning-user "welcome back" screen ──────────────────────────────────────
_RETURNING_HOOK_TEXTS = {
    "uk": "👋 <b>З поверненням!</b>\n\nПродовжіть з того, де зупинились, або оберіть нову дію.",
    "en": "👋 <b>Welcome back!</b>\n\nContinue where you left off, or choose a new action.",
    "de": "👋 <b>Willkommen zurück!</b>\n\nMachen Sie weiter, wo Sie aufgehört haben, oder wählen Sie eine neue Aktion.",
    "pl": "👋 <b>Witamy z powrotem!</b>\n\nKontynuuj od miejsca, w którym skończyłeś, lub wybierz nową akcję.",
    "tr": "👋 <b>Tekrar hoş geldiniz!</b>\n\nKaldığınız yerden devam edin veya yeni bir işlem seçin.",
    "ar": "👋 <b>مرحباً بعودتك!</b>\n\nاستمر من حيث توقفت أو اختر إجراءً جديداً.",
}
_RETURNING_MENU_BTN = {
    "uk": "📋 Відкрити меню",
    "ua": "📋 Відкрити меню",
    "en": "📋 Open menu",
    "de": "📋 Menü öffnen",
    "pl": "📋 Otwórz menu",
    "tr": "📋 Menüyü aç",
    "ar": "📋 فتح القائمة",
}

# Legacy alias — some older code still references SIMPLE_INTRO_TEXTS / GO_TO_MENU_TEXTS
SIMPLE_INTRO_TEXTS = _HOOK_TEXTS
GO_TO_MENU_TEXTS = _RETURNING_MENU_BTN
# Legacy: Keep for backward compatibility (GDPR flow uses this)
WELCOME_BEFORE_GDPR_TEXTS = _HOOK_TEXTS.copy()


async def show_welcome_before_gdpr(message: types.Message, user_id: int, lang: str):
    """Legacy entry-point kept for compatibility — delegates to premium hook screen."""
    await show_intro_text(message, lang)


async def handle_start_documents(callback_query: types.CallbackQuery):
    """User chose Documents -> set GDPR consent, go directly to flat document list."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)

    db = get_db()
    db.set_gdpr_consent(user_id, True)

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    await _show_flat_doc_list(callback_query.message, lang)
    return True


async def handle_start_termin(callback_query: types.CallbackQuery):
    """User chose Find Appointment -> set GDPR consent, delegate to existing termin flow."""
    await callback_query.answer()
    user_id = callback_query.from_user.id

    db = get_db()
    db.set_gdpr_consent(user_id, True)

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    from handlers.termin import show_termin_menu_entry
    await show_termin_menu_entry(callback_query.message, user_id)
    return True


async def handle_welcome_continue(callback_query: types.CallbackQuery):
    """Legacy: old cached keyboards may still send welcome_continue -> treat as start_documents."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)

    db = get_db()
    db.set_gdpr_consent(user_id, True)

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    await _show_main_menu(callback_query.message, lang)
    return True


# ============================================================================
# LANGUAGE SELECTION
# ============================================================================

_bot_logger = None
_analytics = None
_gdpr_manager = None


def _get_bot_logger():
    global _bot_logger
    if _bot_logger is None:
        try:
            from logger import bot_logger
        except ImportError:
            from backend.logger import bot_logger
        _bot_logger = bot_logger
    return _bot_logger


def _get_analytics():
    global _analytics
    if _analytics is None:
        try:
            from analytics import AnalyticsTracker
        except ImportError:
            from backend.analytics import AnalyticsTracker
        db = get_db()
        _analytics = AnalyticsTracker(db)
    return _analytics


def _get_gdpr_manager():
    global _gdpr_manager
    if _gdpr_manager is None:
        try:
            from gdpr import gdpr_manager
        except ImportError:
            try:
                from backend.gdpr import gdpr_manager
            except ImportError:
                # Fallback: return None if GDPR module doesn't exist
                _gdpr_manager = None
                return None
        _gdpr_manager = gdpr_manager
    return _gdpr_manager


# ============================================================================
# LANGUAGE SELECTION
# ============================================================================

# 3 rows × 2 columns — order matches the desired grid layout
LANGUAGE_BUTTONS = [
    ('🇬🇧 English',    'lang_en'),   # row 1 left
    ('🇩🇪 Deutsch',    'lang_de'),   # row 1 right
    ('🇺🇦 Українська', 'lang_ua'),   # row 2 left
    ('🇵🇱 Polski',     'lang_pl'),   # row 2 right
    ('🇹🇷 Türkçe',     'lang_tr'),   # row 3 left
    ('🇸🇦 العربية',    'lang_ar'),   # row 3 right
]

LANGUAGE_CONFIRMATIONS = {
    'ua': '✅ Мову встановлено: Українська',
    'de': '✅ Sprache eingestellt: Deutsch',
    'en': '✅ Language set: English',
    'pl': '✅ Język ustawiony: Polski',
    'tr': '✅ Dil ayarlandı: Türkçe',
    'ar': '✅ تم تعيين اللغة: العربية'
}


async def show_language_selection(message: types.Message):
    """Language picker — 2-column grid (3 rows × 2 buttons)."""
    keyboard = types.InlineKeyboardMarkup()
    for i in range(0, len(LANGUAGE_BUTTONS), 2):
        row = [types.InlineKeyboardButton(text=LANGUAGE_BUTTONS[i][0],
                                          callback_data=LANGUAGE_BUTTONS[i][1])]
        if i + 1 < len(LANGUAGE_BUTTONS):
            row.append(types.InlineKeyboardButton(text=LANGUAGE_BUTTONS[i + 1][0],
                                                  callback_data=LANGUAGE_BUTTONS[i + 1][1]))
        keyboard.row(*row)

    await message.answer("🌐 Choose language", reply_markup=keyboard)


async def show_gdpr_consent(message: types.Message, user_id: int, lang: str = None):
    """Показати GDPR згоду на обраній мові"""
    if lang is None:
        lang = get_user_lang(user_id)
    
    gdpr = _get_gdpr_manager()
    if gdpr is None:
        # GDPR module missing - treat as accepted, go directly to main menu
        await _show_main_menu(message, lang)
        return
    
    text = gdpr.get_consent_message(lang)
    keyboard = gdpr.get_consent_keyboard(lang)
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ============================================================================
# HANDLERS
# ============================================================================

async def cmd_start(message: types.Message, state: FSMContext):
    """
    Обробник /start
    ПРИМУСОВИЙ ПОТІК: /start → Вибір мови → GDPR → Головне меню
    """
    # Імпортуємо тут щоб уникнути циклічних залежностей
    from handlers.payments import handle_payment_return, handle_paid_deeplink
    
    user = message.from_user
    db = get_db()
    analytics = _get_analytics()
    bot_logger = _get_bot_logger()
    
    # Перевіряємо аргументи ПЕРШ ніж reset state
    args = message.get_args()

    # AI doc-support deep link: /start ai_{doc_type}
    # Opened from email "Support" button — must be handled BEFORE state reset.
    if args and args.startswith('ai_'):
        doc_type = args[3:].strip().lower()  # strip "ai_" prefix
        logger.info("START_AI_DEEPLINK: user_id=%s doc_type=%r", user.id, doc_type)
        from handlers.support_ai import open_ai_doc_support
        # Ensure user exists in DB (needed for lang lookup)
        db.get_or_create_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        await open_ai_doc_support(message, state, doc_type)
        return

    # CRITICAL: Handle paid_ deep link (post-payment PDF delivery)
    # This MUST be checked BEFORE resetting state and BEFORE language selection
    # Format: /start paid_<order_id>
    if args and args.startswith('paid_'):
        order_id = args.replace('paid_', '').strip()
        logger.info("START_PAID_DEEPLINK: order_id=%s", order_id)
        await handle_paid_deeplink(message, order_id)
        return  # CRITICAL: Do NOT show language selection after payment
    
    # Deep link від оплати (payment_123 або payment_success_123) - legacy
    # This is used by old success_url format (not recommended)
    if args and args.startswith('payment_'):
        parts = args.split('_')
        order_id = parts[-1] if len(parts) >= 2 else None
        await handle_payment_return(message, order_id)
        return
    
    # Cancel link - just show main menu, don't reset
    if args and args.startswith('cancel_'):
        logger.debug("START_CANCEL_LINK: args=%s", args)
        # Just continue to normal /start flow
    
    # CRITICAL FIX: Only reset FSM state, NOT in-memory questionnaire data
    # FSM state is separate from _PENDING_PREVIEWS (in-memory dict)
    # WebApp data is stored in _PENDING_PREVIEWS, not FSM, so resetting FSM is safe
    # However, we should preserve _PENDING_PREVIEWS unless user explicitly starts over
    await state.finish()  # Reset FSM state only
    
    # CRITICAL: Do NOT clear _PENDING_PREVIEWS here - user might have unfinished questionnaire
    # Only clear if user explicitly wants to start over (not implemented yet)
    
    referral_code = None
    
    # Реферальний код
    if args and not args.startswith('payment_') and not args.startswith('paid_') and not args.startswith('cancel_') and not args.startswith('ai_'):
        referral_code = args
    
    # Створюємо/оновлюємо користувача (база створиться, якщо її нема)
    db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        referral_code_used=referral_code
    )
    # if referral_code and referral_code.startswith("REF"):
    #     try:
    #         db.set_referral_code_used(user.id, referral_code)
    #     except Exception:
    #         pass
    
    # ── TERMIN ACTIVE MONITORING GATE ───────────────────────────────────────────
    # Any user who has active Termin monitoring and a saved language sees the
    # monitoring status screen immediately on /start — no deeplinks, no admins.
    # This prevents the "dead state" where monitoring runs but /start shows the
    # generic menu with no indication.
    # Also catches recently-expired entitlements so user sees "ended" instead of
    # silently landing on the generic menu.
    if not args:
        try:
            _tgate_lang = db.get_user_lang(user.id) if hasattr(db, "get_user_lang") else None
            _tgate_admin = user.id in (getattr(config, "ADMIN_IDS", []) or [])
            if _tgate_lang and not _tgate_admin:
                from backend.termin_db import (
                    is_termin_entitled as _ite_gate,
                    get_entitlement as _ge_gate,
                )
                _ent_gate = _ge_gate(str(user.id))
                _tgl = "uk" if _tgate_lang in ("ua", "uk") else _tgate_lang
                if _ent_gate and _ent_gate.get("active") == 1:
                    _is_entitled = _ite_gate(str(user.id))
                    # Expired: active=1 but is_termin_entitled() returns False
                    # (paid_until exceeded or found_termin=1).  Show "ended" card
                    # only when entitlement was created in the last 30 days so we
                    # don't surface ancient stale rows to long-inactive users.
                    _is_expired = not _is_entitled
                    if _is_expired:
                        try:
                            from datetime import datetime as _dtg
                            _created = _ent_gate.get("created_at") or ""
                            _age_days = 999
                            if _created:
                                _age_days = (_dtg.utcnow() - _dtg.fromisoformat(_created)).days
                        except Exception:
                            _age_days = 999
                        _is_expired = _age_days <= 30
                    if _is_entitled or _is_expired:
                        logger.info(
                            "TERMIN_ACTIVE_GATE | user=%s city=%s auth=%s expired=%s",
                            user.id,
                            _ent_gate.get("city"),
                            _ent_gate.get("authority"),
                            _is_expired,
                        )
                        await _show_termin_active_screen(
                            message, user.id, _tgl, _ent_gate, expired=_is_expired
                        )
                        return
        except Exception as _tgate_err:
            logger.exception("TERMIN_ACTIVE_GATE_ERROR | user=%s", user.id)

    # ── NEW vs RETURNING USER ────────────────────────────────────────────────────
    # A returning user (has at least one completed order) gets a fast "Welcome back"
    # screen that goes straight to the menu — skipping language selection entirely.
    _is_returning = False
    try:
        _saved_lang = db.get_user_lang(user.id) if hasattr(db, "get_user_lang") else None
        _past_orders = db.get_user_orders(user.id, limit=3) or []
        _completed_statuses = {"paid", "sent", "downloaded"}
        _has_completed = any(
            (o.get("status") or "").strip().lower() in _completed_statuses
            for o in _past_orders
        )
        _is_admin = user.id in (getattr(config, "ADMIN_IDS", []) or [])
        if _has_completed and _saved_lang and not args and not _is_admin:
            # Known user with at least one paid order — show unified main menu with welcome header
            # Admins always get the full new-user flow so they can test the onboarding.
            _is_returning = True
            _ret_lang = "uk" if _saved_lang in ("ua", "uk") else _saved_lang
            if _ret_lang not in _HOOK_TEXTS:
                _ret_lang = "en"
            _ret_headers = {
                "uk": "👋 <b>З поверненням! Продовжимо</b>\n\n",
                "en": "👋 <b>Welcome back! Let's continue</b>\n\n",
                "de": "👋 <b>Willkommen zurück! Weiter geht's</b>\n\n",
                "pl": "👋 <b>Witamy z powrotem! Kontynuujemy</b>\n\n",
                "tr": "👋 <b>Tekrar hoş geldiniz! Devam edelim</b>\n\n",
                "ar": "👋 <b>مرحباً بعودتك! لنكمل</b>\n\n",
            }
            analytics.track_user_start(user.id, is_new=False, referral_code=referral_code)
            bot_logger.log_activity(
                action="USER_RETURNING",
                user_id=user.id,
                details={"username": user.username, "lang": _ret_lang},
            )
            await _show_main_menu(message, _ret_lang, greeting=_ret_headers.get(_ret_lang, ""))
            return
    except Exception as _ret_err:
        logger.debug("RETURNING_USER_CHECK_FAILED: %s", _ret_err)

    # Аналітика та логування
    analytics.track_user_start(user.id, is_new=True, referral_code=referral_code)
    bot_logger.log_activity(
        action="USER_START_FORCED",
        user_id=user.id,
        details={'username': user.username}
    )

    # ── ORDER RECOVERY: resume pending order if user returns without paying ──────
    try:
        _recovery_orders = db.get_user_orders(user.id, limit=5)
        from backend.database import OrderStatus as _OS
        # "pending" = user hasn't paid yet → show "continue to payment".
        # "paid"    = user paid but PDF not delivered (webhook lag / bot was down) → show "get PDF".
        # "processing" = PDF generation in flight — do NOT interrupt.
        # "failed", "sent", "downloaded", "cancelled" are terminal — never show.
        _pending_statuses = (_OS.PENDING.value, _OS.PAID.value)
        _lang_now = (db.get_user_lang(user.id) if hasattr(db, "get_user_lang") else None) or "en"
        _lang_now = "uk" if _lang_now == "ua" else _lang_now

        _recovery = [
            o for o in _recovery_orders
            if (o.get("status") or "").strip().lower() in _pending_statuses
            and o.get("doc_type") and o.get("user_data")
        ]
        if _recovery:
            _o = _recovery[0]
            _doc = (_o.get("doc_type") or "").lower()
            _oid = _o.get("id") or _o.get("order_id")
            _price = _o.get("price") or _o.get("amount") or 0

            # German official name for the document
            _DOC_NAMES_RECOVERY = {
                "anmeldung": "Anmeldung", "ummeldung": "Ummeldung",
                "abmeldung": "Abmeldung", "wohnungsgeberbestaetigung": "Wohnungsgeberbestätigung",
                "kindergeld": "Kindergeld", "buergergeld": "Bürgergeld",
                "wohngeld": "Wohngeld", "aufenthaltstitel": "Aufenthaltstitel",
                "bafoeg": "BAföG", "elterngeld": "Elterngeld",
                "kinderzuschlag": "Kinderzuschlag", "unterhaltsvorschuss": "Unterhaltsvorschuss",
                "wbs": "Wohnberechtigungsschein", "ebk": "Erklärung zur Bekämpfung der Kinderarmut",
                "verpflichtungserklaerung": "Verpflichtungserklärung",
                "beschaeftigungserklaerung": "Beschäftigungserklärung",
            }
            _doc_display = _DOC_NAMES_RECOVERY.get(_doc, _doc.replace("_", " ").title())
            _is_paid = ((_o.get("status") or "").strip().lower() == _OS.PAID.value)

            if _is_paid:
                # User already paid — PDF delivery failed or was delayed. Offer immediate re-delivery.
                _recovery_text = {
                    "uk": (
                        f"✅ <b>Оплату отримано!</b>\n\n"
                        f"📄 {_doc_display}\n\n"
                        "Документ ще не надійшов? Натисніть кнопку — надішлемо зараз."
                    ),
                    "en": (
                        f"✅ <b>Payment received!</b>\n\n"
                        f"📄 {_doc_display}\n\n"
                        "Document not received yet? Tap the button to get it now."
                    ),
                    "de": (
                        f"✅ <b>Zahlung erhalten!</b>\n\n"
                        f"📄 {_doc_display}\n\n"
                        "Dokument noch nicht erhalten? Tippen Sie auf die Schaltfläche."
                    ),
                    "pl": (
                        f"✅ <b>Płatność otrzymana!</b>\n\n"
                        f"📄 {_doc_display}\n\n"
                        "Dokument nie dotarł? Naciśnij przycisk, aby otrzymać go teraz."
                    ),
                    "tr": (
                        f"✅ <b>Ödeme alındı!</b>\n\n"
                        f"📄 {_doc_display}\n\n"
                        "Belge henüz gelmedi mi? Şimdi almak için düğmeye basın."
                    ),
                    "ar": (
                        f"✅ <b>تم استلام الدفع!</b>\n\n"
                        f"📄 {_doc_display}\n\n"
                        "لم يصل المستند بعد؟ اضغط على الزر للحصول عليه الآن."
                    ),
                }
                _continue_btn = {
                    "uk": "📥 Отримати PDF", "en": "📥 Get PDF",
                    "de": "📥 PDF erhalten", "pl": "📥 Pobierz PDF",
                    "tr": "📥 PDF al", "ar": "📥 احصل على PDF",
                }
            else:
                _recovery_text = {
                    "uk": (
                        f"📋 <b>У вас є незавершене замовлення:</b>\n\n"
                        f"📄 {_doc_display}\n"
                        f"💰 €{_price:.2f}\n\n"
                        "Хочете продовжити до оплати?"
                    ),
                    "en": (
                        f"📋 <b>You have an unfinished order:</b>\n\n"
                        f"📄 {_doc_display}\n"
                        f"💰 €{_price:.2f}\n\n"
                        "Would you like to continue to payment?"
                    ),
                    "de": (
                        f"📋 <b>Sie haben eine unfertige Bestellung:</b>\n\n"
                        f"📄 {_doc_display}\n"
                        f"💰 €{_price:.2f}\n\n"
                        "Möchten Sie zur Zahlung fortfahren?"
                    ),
                    "pl": (
                        f"📋 <b>Masz niedokończone zamówienie:</b>\n\n"
                        f"📄 {_doc_display}\n"
                        f"💰 €{_price:.2f}\n\n"
                        "Czy chcesz przejść do płatności?"
                    ),
                    "tr": (
                        f"📋 <b>Tamamlanmamış bir siparişiniz var:</b>\n\n"
                        f"📄 {_doc_display}\n"
                        f"💰 €{_price:.2f}\n\n"
                        "Ödemeye devam etmek ister misiniz?"
                    ),
                    "ar": (
                        f"📋 <b>لديك طلب غير مكتمل:</b>\n\n"
                        f"📄 {_doc_display}\n"
                        f"💰 €{_price:.2f}\n\n"
                        "هل تريد الاستمرار إلى الدفع؟"
                    ),
                }
                _continue_btn = {
                    "uk": "✅ Продовжити оплату", "en": "✅ Continue to payment",
                    "de": "✅ Zur Zahlung", "pl": "✅ Przejdź do płatności",
                    "tr": "✅ Ödemeye devam", "ar": "✅ المتابعة للدفع",
                }
            _cancel_btn = {
                "uk": "❌ Почати заново", "en": "❌ Start over",
                "de": "❌ Neu beginnen", "pl": "❌ Zacznij od nowa",
                "tr": "❌ Yeniden başla", "ar": "❌ ابدأ من جديد",
            }
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            _kb = InlineKeyboardMarkup(row_width=1)
            _kb.add(
                InlineKeyboardButton(
                    _continue_btn.get(_lang_now, _continue_btn["en"]),
                    callback_data=f"pay_{_oid}",
                ),
                InlineKeyboardButton(
                    _cancel_btn.get(_lang_now, _cancel_btn["en"]),
                    callback_data="back_to_main_menu",
                ),
            )
            await message.answer(
                _recovery_text.get(_lang_now, _recovery_text["en"]),
                parse_mode="HTML",
                reply_markup=_kb,
            )
            logger.info("ORDER_RECOVERY_SHOWN | user_id=%s order_id=%s doc=%s", user.id, _oid, _doc)
            return
    except Exception as _rec_err:
        logger.warning("ORDER_RECOVERY_FAILED | user_id=%s error=%s", user.id, _rec_err)

    # ── DRAFT RECOVERY: resume incomplete form if user stopped mid-filling ────
    # Only shown when no paid/processing/pending order exists (order recovery takes priority).
    # Uses DraftsManager which tracks form progress step-by-step.
    try:
        from backend.drafts import DraftsManager as _DraftsManager
        import config as _cfg
        from backend.database import OrderStatus as _OS2
        _drafts_db_path = getattr(_cfg, "DB_PATH", "bot_database.db")
        _drafts_mgr = _DraftsManager(_drafts_db_path)

        # Skip draft recovery entirely if there is any active/recent order
        # (paid, processing, pending) — those flows take priority.
        _active_statuses = {
            _OS2.PAID.value, _OS2.PROCESSING.value, _OS2.PENDING.value,
        }
        _has_active_order = any(
            (o.get("status") or "").strip().lower() in _active_statuses
            for o in (db.get_user_orders(user.id, limit=5) or [])
        )

        _active_draft = None if _has_active_order else _drafts_mgr.get_active_draft(user.id)
        if _active_draft:
            _dlang = (db.get_user_lang(user.id) if hasattr(db, "get_user_lang") else None) or "en"
            _dlang = "uk" if _dlang == "ua" else _dlang
            _draft_text = _drafts_mgr.format_resume_message(_active_draft, lang=_dlang)
            _continue_draft_btn = {
                "uk": "▶️ Продовжити заповнення",
                "en": "▶️ Continue filling",
                "de": "▶️ Ausfüllen fortsetzen",
                "pl": "▶️ Kontynuuj wypełnianie",
                "tr": "▶️ Doldurmaya devam et",
                "ar": "▶️ متابعة التعبئة",
            }
            _discard_draft_btn = {
                "uk": "🗑 Почати заново",
                "en": "🗑 Start over",
                "de": "🗑 Neu beginnen",
                "pl": "🗑 Zacznij od nowa",
                "tr": "🗑 Yeniden başla",
                "ar": "🗑 ابدأ من جديد",
            }
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            _draft_kb = InlineKeyboardMarkup(row_width=1)
            _draft_kb.add(
                InlineKeyboardButton(
                    _continue_draft_btn.get(_dlang, _continue_draft_btn["en"]),
                    callback_data=f"resume_draft_{_active_draft['id']}",
                ),
                InlineKeyboardButton(
                    _discard_draft_btn.get(_dlang, _discard_draft_btn["en"]),
                    callback_data="discard_draft",
                ),
            )
            await message.answer(_draft_text, parse_mode="HTML", reply_markup=_draft_kb)
            logger.info(
                "DRAFT_RECOVERY_SHOWN | user_id=%s draft_id=%s doc=%s",
                user.id, _active_draft["id"], _active_draft.get("doc_type"),
            )
            return
    except Exception as _draft_err:
        logger.warning("DRAFT_RECOVERY_FAILED | user_id=%s error=%s", user.id, _draft_err)

    # ПРИМУСОВИЙ ВИБІР МОВИ (ігноруємо наявність згоди в базі)
    await show_language_selection(message)


async def handle_language_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обробка вибору мови - зберігає мову та ПРИМУСОВО показує GDPR"""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    db = get_db()
    bot_logger = _get_bot_logger()
    
    # CRITICAL FIX: Preserve existing questionnaire data when changing language
    # Import here to avoid circular dependency
    try:
        from handlers.docs_new import _PENDING_PREVIEWS
        import logging
        logger = logging.getLogger(__name__)
        lang_code_new = callback_query.data.split('_')[1]
        # Update language in ALL pending entries for this user (keyed by (user_id, doc_type))
        updated = 0
        for key, entry in _PENDING_PREVIEWS.items():
            if key[0] == user_id:
                entry["lang"] = lang_code_new
                entry["user_lang"] = lang_code_new
                updated += 1
        if updated:
            logger.info(f"📋 Preserved questionnaire data for user {user_id} during language change ({updated} slots)")
    except ImportError:
        pass  # If module not available, skip
    
    # Витягуємо код мови (lang_ua -> ua)
    lang_code = callback_query.data.split('_')[1]
    
    if lang_code not in config.SUPPORTED_LANGUAGES:
        lang_code = config.DEFAULT_LANGUAGE
    
    # Зберігаємо мову в базу
    db.set_user_lang(user_id, lang_code)
    await state.update_data(country_code="de")
    
    bot_logger.log_activity(
        action="LANGUAGE_SELECTED",
        user_id=user_id,
        details={'lang': lang_code}
    )
    
    # Підтвердження вибору мови — edit inline buttons away, show confirmation briefly
    confirm_text = LANGUAGE_CONFIRMATIONS.get(lang_code, LANGUAGE_CONFIRMATIONS['ua'])
    try:
        await callback_query.message.edit_text(f"<b>{confirm_text}</b>", parse_mode="HTML")
    except Exception:
        pass

    await asyncio.sleep(0.8)  # Коротка пауза для ефекту

    # Delete the language selection message to clean up chat
    try:
        await callback_query.message.delete()
    except Exception:
        pass

    # Show welcome explanation screen; user presses "Open Menu" to proceed
    logger.info("LANGUAGE_SELECTED_SHOW_WELCOME | lang_code=%s user_id=%s", lang_code, user_id)
    await show_intro_text(callback_query.message, lang_code)
    return True

async def handle_set_language_from_menu(callback_query: types.CallbackQuery, state: FSMContext):
    """Обробка зміни мови з меню (set_lang_ua)"""
    try:
        from handlers.menu import show_main_menu
    except ImportError:
        _err = {"uk": "Меню тимчасово недоступне", "en": "Main menu is temporarily unavailable",
                "de": "Hauptmenü vorübergehend nicht verfügbar", "pl": "Menu tymczasowo niedostępne",
                "tr": "Ana menü geçici olarak kullanılamıyor", "ar": "القائمة الرئيسية غير متاحة مؤقتاً"}
        await callback_query.answer(_err.get(get_user_lang(callback_query.from_user.id), _err["en"]))
        return
    
    await callback_query.answer()
    user_id = callback_query.from_user.id
    db = get_db()
    bot_logger = _get_bot_logger()
    
    # CRITICAL FIX: Preserve existing questionnaire data when changing language
    # Import here to avoid circular dependency
    try:
        from handlers.docs_new import _PENDING_PREVIEWS
        import logging
        logger = logging.getLogger(__name__)
        lang_code_new = callback_query.data.replace('set_lang_', '')
        # Update language in ALL pending entries for this user (keyed by (user_id, doc_type))
        updated = 0
        for key, entry in _PENDING_PREVIEWS.items():
            if key[0] == user_id:
                entry["lang"] = lang_code_new
                entry["user_lang"] = lang_code_new
                updated += 1
        if updated:
            logger.info(f"📋 Preserved questionnaire data for user {user_id} during language change from menu ({updated} slots)")
    except ImportError:
        pass  # If module not available, skip
    
    # set_lang_ua -> ua
    lang_code = callback_query.data.replace('set_lang_', '')
    
    if lang_code not in config.SUPPORTED_LANGUAGES:
        lang_code = config.DEFAULT_LANGUAGE
    
    db.set_user_lang(user_id, lang_code)
    
    bot_logger.log_activity(
        action="LANGUAGE_CHANGED",
        user_id=user_id,
        details={'lang': lang_code, 'source': 'menu'}
    )
    
    try:
        await callback_query.message.delete()
    except:
        pass
    
    await _show_main_menu(callback_query.message, lang_code)

async def _show_termin_active_screen(
    message: types.Message,
    user_id: int,
    lang: str,
    entitlement: dict,
    *,
    expired: bool = False,
) -> None:
    """Show Termin monitoring status card when user returns via /start or /my.

    expired=False (default): active monitoring — shows status/stop/menu buttons.
    expired=True: entitlement has expired — shows restart/menu buttons only.
    """
    city_raw = (entitlement or {}).get("city") or "—"
    authority_key = (entitlement or {}).get("authority") or ""
    paid_until = (entitlement or {}).get("paid_until")

    _l = lang if lang in ("uk", "en", "de", "pl", "tr", "ar") else "en"

    _AUTH_NAMES = {
        "buergeramt": {
            "uk": "Бюргерамт", "en": "Citizens Office", "de": "Bürgeramt",
            "pl": "Urząd Obywatelski", "tr": "Vatandaşlık Ofisi", "ar": "مكتب المواطنين",
        },
        "auslaenderbehoerde": {
            "uk": "Міграційна служба", "en": "Immigration Office", "de": "Ausländerbehörde",
            "pl": "Urząd ds. Cudzoziemców", "tr": "Yabancılar Dairesi", "ar": "مكتب شؤون الأجانب",
        },
        "kfz": {
            "uk": "Реєстрація авто", "en": "Vehicle Registration", "de": "KFZ-Zulassung",
            "pl": "Rejestracja pojazdu", "tr": "Araç Tescili", "ar": "تسجيل السيارة",
        },
        "fuehrerschein": {
            "uk": "Водійське посвідчення", "en": "Driver's Licence", "de": "Führerschein",
            "pl": "Prawo jazdy", "tr": "Ehliyet", "ar": "رخصة القيادة",
        },
        "anmeldung": {
            "uk": "Реєстрація (Anmeldung)", "en": "Registration (Anmeldung)", "de": "Anmeldung",
            "pl": "Rejestracja (Anmeldung)", "tr": "Kayıt (Anmeldung)", "ar": "التسجيل (Anmeldung)",
        },
    }
    auth_display = (
        (_AUTH_NAMES.get(authority_key) or {}).get(_l)
        or authority_key.replace("_", " ").title()
        or "—"
    )
    city_display = city_raw.title() if city_raw != "—" else "—"

    _expires_str = ""
    if paid_until:
        try:
            from datetime import datetime as _dt
            _expires_str = _dt.fromisoformat(paid_until).strftime("%d.%m.%Y")
        except Exception:
            pass

    _exp_line = {
        "uk": f"⏳ Дійсний до: {_expires_str}\n" if _expires_str else "",
        "en": f"⏳ Valid until: {_expires_str}\n" if _expires_str else "",
        "de": f"⏳ Gültig bis: {_expires_str}\n" if _expires_str else "",
        "pl": f"⏳ Ważny do: {_expires_str}\n" if _expires_str else "",
        "tr": f"⏳ Geçerlilik: {_expires_str}\n" if _expires_str else "",
        "ar": f"⏳ صالح حتى: {_expires_str}\n" if _expires_str else "",
    }

    # ── EXPIRED STATE ────────────────────────────────────────────────────────
    if expired:
        _EXP_TEXTS = {
            "uk": (
                "⏰ <b>Моніторинг Termin завершився</b>\n\n"
                f"📍 Місто: <b>{city_display}</b>\n"
                f"📄 Послуга: <b>{auth_display}</b>\n"
                f"{_exp_line['uk']}"
                "\n🔴 <b>Статус:</b> завершено\n\n"
                "Запис не було знайдено або термін дії закінчився.\n"
                "Запустіть новий пошук, щоб продовжити."
            ),
            "en": (
                "⏰ <b>Termin monitoring ended</b>\n\n"
                f"📍 City: <b>{city_display}</b>\n"
                f"📄 Service: <b>{auth_display}</b>\n"
                f"{_exp_line['en']}"
                "\n🔴 <b>Status:</b> ended\n\n"
                "No slot was found or the subscription expired.\n"
                "Start a new search to continue."
            ),
            "de": (
                "⏰ <b>Terminüberwachung beendet</b>\n\n"
                f"📍 Stadt: <b>{city_display}</b>\n"
                f"📄 Dienst: <b>{auth_display}</b>\n"
                f"{_exp_line['de']}"
                "\n🔴 <b>Status:</b> beendet\n\n"
                "Kein Termin gefunden oder Abo abgelaufen.\n"
                "Starten Sie eine neue Suche."
            ),
            "pl": (
                "⏰ <b>Monitoring Termin zakończony</b>\n\n"
                f"📍 Miasto: <b>{city_display}</b>\n"
                f"📄 Usługa: <b>{auth_display}</b>\n"
                f"{_exp_line['pl']}"
                "\n🔴 <b>Status:</b> zakończony\n\n"
                "Nie znaleziono terminu lub subskrypcja wygasła.\n"
                "Uruchom nowe wyszukiwanie."
            ),
            "tr": (
                "⏰ <b>Termin takibi sona erdi</b>\n\n"
                f"📍 Şehir: <b>{city_display}</b>\n"
                f"📄 Hizmet: <b>{auth_display}</b>\n"
                f"{_exp_line['tr']}"
                "\n🔴 <b>Durum:</b> sona erdi\n\n"
                "Randevu bulunamadı veya abonelik süresi doldu.\n"
                "Aramaya devam etmek için yeniden başlatın."
            ),
            "ar": (
                "⏰ <b>انتهت مراقبة Termin</b>\n\n"
                f"📍 المدينة: <b>{city_display}</b>\n"
                f"📄 الخدمة: <b>{auth_display}</b>\n"
                f"{_exp_line['ar']}"
                "\n🔴 <b>الحالة:</b> منتهية\n\n"
                "لم يُعثر على موعد أو انتهت صلاحية الاشتراك.\n"
                "ابدأ بحثاً جديداً للمتابعة."
            ),
        }
        _NEW_SEARCH_BTN = {
            "uk": "🔍 Новий пошук", "en": "🔍 New search", "de": "🔍 Neue Suche",
            "pl": "🔍 Nowe wyszukiwanie", "tr": "🔍 Yeni arama", "ar": "🔍 بحث جديد",
        }
        _MENU_BTN_EXP = {
            "uk": "🏠 Головне меню", "en": "🏠 Main menu", "de": "🏠 Hauptmenü",
            "pl": "🏠 Menu główne", "tr": "🏠 Ana menü", "ar": "🏠 القائمة الرئيسية",
        }
        kb_exp = InlineKeyboardMarkup(row_width=2)
        kb_exp.row(
            InlineKeyboardButton(_NEW_SEARCH_BTN.get(_l, "🔍 New search"), callback_data="find_termin"),
            InlineKeyboardButton(_MENU_BTN_EXP.get(_l, "🏠 Main menu"), callback_data="back_to_main_menu"),
        )
        await message.answer(_EXP_TEXTS.get(_l, _EXP_TEXTS["en"]), parse_mode="HTML", reply_markup=kb_exp)
        return

    # ── ACTIVE STATE ─────────────────────────────────────────────────────────
    _TEXTS = {
        "uk": (
            "🔄 <b>Активний моніторинг Termin</b>\n\n"
            f"📍 Місто: <b>{city_display}</b>\n"
            f"📄 Послуга: <b>{auth_display}</b>\n"
            f"{_exp_line['uk']}"
            "🟢 <b>Статус:</b> активний — бот шукає запис\n\n"
            "🤖 Перевірка слотів 24/7. Як тільки з'явиться запис — ти отримаєш повідомлення.\n"
            "Можеш закрити бот — ми все одно надішлемо."
        ),
        "en": (
            "🔄 <b>Active Termin monitoring</b>\n\n"
            f"📍 City: <b>{city_display}</b>\n"
            f"📄 Service: <b>{auth_display}</b>\n"
            f"{_exp_line['en']}"
            "🟢 <b>Status:</b> active — bot is searching\n\n"
            "🤖 Slot checks 24/7. As soon as one appears — you'll get a notification.\n"
            "You can close the bot — we'll notify you anyway."
        ),
        "de": (
            "🔄 <b>Aktive Terminüberwachung</b>\n\n"
            f"📍 Stadt: <b>{city_display}</b>\n"
            f"📄 Dienst: <b>{auth_display}</b>\n"
            f"{_exp_line['de']}"
            "🟢 <b>Status:</b> aktiv — Bot sucht\n\n"
            "🤖 Slot-Prüfung 24/7. Sobald einer frei ist — erhalten Sie eine Benachrichtigung.\n"
            "Sie können den Bot schließen — wir benachrichtigen Sie trotzdem."
        ),
        "pl": (
            "🔄 <b>Aktywne monitorowanie Termin</b>\n\n"
            f"📍 Miasto: <b>{city_display}</b>\n"
            f"📄 Usługa: <b>{auth_display}</b>\n"
            f"{_exp_line['pl']}"
            "🟢 <b>Status:</b> aktywny — bot szuka\n\n"
            "🤖 Sprawdzanie slotów 24/7. Jak tylko pojawi się termin — dostaniesz powiadomienie.\n"
            "Możesz zamknąć bota — i tak Cię powiadomimy."
        ),
        "tr": (
            "🔄 <b>Aktif Termin takibi</b>\n\n"
            f"📍 Şehir: <b>{city_display}</b>\n"
            f"📄 Hizmet: <b>{auth_display}</b>\n"
            f"{_exp_line['tr']}"
            "🟢 <b>Durum:</b> aktif — bot arıyor\n\n"
            "🤖 7/24 slot kontrolü. Yer açıldığında bildirim alırsınız.\n"
            "Botu kapatabilirsiniz — yine de bilgilendiririz."
        ),
        "ar": (
            "🔄 <b>مراقبة Termin نشطة</b>\n\n"
            f"📍 المدينة: <b>{city_display}</b>\n"
            f"📄 الخدمة: <b>{auth_display}</b>\n"
            f"{_exp_line['ar']}"
            "🟢 <b>الحالة:</b> نشطة — البوت يبحث\n\n"
            "🤖 فحص المواعيد 24/7. فور ظهور موعد — ستتلقى إشعاراً.\n"
            "يمكنك إغلاق البوت — سنبلغك على أي حال."
        ),
    }

    _STATUS_BTN = {
        "uk": "📊 Статус", "en": "📊 Status", "de": "📊 Status",
        "pl": "📊 Status", "tr": "📊 Durum", "ar": "📊 الحالة",
    }
    _STOP_BTN = {
        "uk": "❌ Зупинити", "en": "❌ Stop", "de": "❌ Stoppen",
        "pl": "❌ Zatrzymaj", "tr": "❌ Durdur", "ar": "❌ إيقاف",
    }
    _MENU_BTN = {
        "uk": "🏠 Головне меню", "en": "🏠 Main menu", "de": "🏠 Hauptmenü",
        "pl": "🏠 Menu główne", "tr": "🏠 Ana menü", "ar": "🏠 القائمة الرئيسية",
    }

    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton(_STATUS_BTN.get(_l, "📊 Status"), callback_data="termin_status"),
        InlineKeyboardButton(_STOP_BTN.get(_l, "❌ Stop"), callback_data="termin_stop_poll"),
    )
    kb.add(InlineKeyboardButton(_MENU_BTN.get(_l, "🏠 Main menu"), callback_data="back_to_main_menu"))
    await message.answer(_TEXTS.get(_l, _TEXTS["en"]), parse_mode="HTML", reply_markup=kb)


async def _show_main_menu(message: types.Message, lang: str, greeting: str = ""):
    """Main menu — Termin is the headline product, documents second."""
    # Menu header — mentions both products explicitly
    menu_texts = {
        "uk": (
            "🇩🇪 <b>CivicAssistBot</b>\n\n"
            "📅 <b>Моніторинг Termin</b> — знайдемо запис, поки ви спите\n"
            "📄 <b>Документи</b> — будь-який формуляр за 4 хвилини\n\n"
            "Що вам потрібно?"
        ),
        "ua": (
            "🇩🇪 <b>CivicAssistBot</b>\n\n"
            "📅 <b>Моніторинг Termin</b> — знайдемо запис, поки ви спите\n"
            "📄 <b>Документи</b> — будь-який формуляр за 4 хвилини\n\n"
            "Що вам потрібно?"
        ),
        "en": (
            "🇩🇪 <b>CivicAssistBot</b>\n\n"
            "📅 <b>Termin monitoring</b> — we find your slot while you sleep\n"
            "📄 <b>Documents</b> — any German form in 4 minutes\n\n"
            "What do you need?"
        ),
        "de": (
            "🇩🇪 <b>CivicAssistBot</b>\n\n"
            "📅 <b>Terminüberwachung</b> — wir finden Ihren Termin, während Sie schlafen\n"
            "📄 <b>Dokumente</b> — jedes Formular in 4 Minuten\n\n"
            "Was brauchen Sie?"
        ),
        "pl": (
            "🇩🇪 <b>CivicAssistBot</b>\n\n"
            "📅 <b>Monitoring Termin</b> — znajdziemy termin, gdy śpisz\n"
            "📄 <b>Dokumenty</b> — każdy formularz w 4 minuty\n\n"
            "Czego potrzebujesz?"
        ),
        "tr": (
            "🇩🇪 <b>CivicAssistBot</b>\n\n"
            "📅 <b>Termin takibi</b> — siz uyurken randevunuzu buluruz\n"
            "📄 <b>Belgeler</b> — her form 4 dakikada\n\n"
            "Neye ihtiyacınız var?"
        ),
        "ar": (
            "🇩🇪 <b>CivicAssistBot</b>\n\n"
            "📅 <b>مراقبة المواعيد</b> — نجد موعدك وأنت نائم\n"
            "📄 <b>المستندات</b> — أي نموذج في 4 دقائق\n\n"
            "ماذا تحتاج؟"
        ),
    }

    # Termin — headline button (full width, prominent)
    _termin_label = {
        "uk": "📅 Знайти Termin (запис) — 24/7",
        "ua": "📅 Знайти Termin (запис) — 24/7",
        "en": "📅 Find Termin (appointment) — 24/7",
        "de": "📅 Termin finden — 24/7",
        "pl": "📅 Znajdź Termin (wizytę) — 24/7",
        "tr": "📅 Termin bul (randevu) — 24/7",
        "ar": "📅 إيجاد Termin (موعد) — 24/7",
    }
    _residence_label = {
        "uk": "📄 Обрати та заповнити документ",
        "ua": "📄 Обрати та заповнити документ",
        "en": "📄 Choose & fill document",
        "de": "📄 Dokument auswählen & ausfüllen",
        "pl": "📄 Wybierz i wypełnij dokument",
        "tr": "📄 Belge seç ve doldur",
        "ar": "📄 اختر المستند واملأه",
    }
    _my_docs_label = {
        "uk": "📁 Мої документи", "ua": "📁 Мої документи",
        "en": "📁 My Documents",  "de": "📁 Meine Dokumente",
        "pl": "📁 Moje dokumenty","tr": "📁 Belgelerim",
        "ar": "📁 مستنداتي",
    }
    _lang_btn_label = {
        "uk": "🌐 Мова", "ua": "🌐 Мова", "en": "🌐 Language",
        "de": "🌐 Sprache", "pl": "🌐 Język", "tr": "🌐 Dil", "ar": "🌐 اللغة",
    }
    _settings_btn_label = {
        "uk": "⚙️ Налаштування", "ua": "⚙️ Налаштування", "en": "⚙️ Settings",
        "de": "⚙️ Einstellungen", "pl": "⚙️ Ustawienia", "tr": "⚙️ Ayarlar",
        "ar": "⚙️ الإعدادات",
    }
    _support_btn_label = {
        "uk": "💬 Підтримка", "ua": "💬 Підтримка", "en": "💬 Support",
        "de": "💬 Support", "pl": "💬 Wsparcie", "tr": "💬 Destek",
        "ar": "💬 الدعم",
    }

    _l = lang if lang in _termin_label else "en"
    text = menu_texts.get(_l, menu_texts["en"])
    if greeting:
        text = greeting + text

    # Layout (priority order):
    # Row 1: [📅 Find Termin — 24/7]            ← #1 product, full width
    # Row 2: [📄 Choose & fill document]         ← #2 product, full width
    # Row 3: [🆘 Support]  [⚙️ Settings]         ← Support as direct quick-access button
    # Row 4: [📁 My docs]  [🌐 Language]         ← utility, compact
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton(
        _termin_label.get(_l, _termin_label["en"]),
        callback_data="find_termin",
    ))
    kb.add(InlineKeyboardButton(
        _residence_label.get(_l, _residence_label["en"]),
        callback_data="create_doc",
    ))
    kb.row(
        InlineKeyboardButton(_support_btn_label.get(_l, _support_btn_label["en"]), callback_data="ai_support"),
        InlineKeyboardButton(_settings_btn_label.get(_l, _settings_btn_label["en"]), callback_data="settings_menu"),
    )
    kb.row(
        InlineKeyboardButton(_my_docs_label.get(_l, _my_docs_label["en"]), callback_data="my_docs"),
        InlineKeyboardButton(_lang_btn_label.get(_l, _lang_btn_label["en"]), callback_data="language"),
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def show_intro_text(message: types.Message, lang: str):
    """
    Premium hook screen shown after language selection.

    New users see: strong headline + 3 outcome bullets + live document counter
    + two direct CTAs (Document / Termin).  No intermediate "Open Menu" step.
    """
    _l = lang if lang in _HOOK_TEXTS else ("uk" if lang in ("ua",) else "en")

    counter_str = _fmt_counter(_get_doc_counter())
    hook_text = _HOOK_TEXTS[_l].format(counter=counter_str)

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            _HOOK_TERMIN_BTN.get(_l, _HOOK_TERMIN_BTN["en"]),
            callback_data="start_termin",
        ),
        InlineKeyboardButton(
            _HOOK_DOC_BTN.get(_l, _HOOK_DOC_BTN["en"]),
            callback_data="start_documents",
        ),
    )

    # Typing indicator — makes the first impression feel alive, not instant-machine
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
        import asyncio as _asyncio
        await _asyncio.sleep(0.7)
    except Exception:
        pass

    await message.answer(hook_text, parse_mode="HTML", reply_markup=kb)


async def handle_intro_continue(callback_query: types.CallbackQuery):
    """Handle 'Open Menu' button after welcome screen (callback_data: open_menu or intro_continue).
    Shows country selection first so the user picks their country before entering the menu."""
    await callback_query.answer()

    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)

    logger.debug("handle_intro_continue | user=%s", user_id)
    try:
        await callback_query.message.delete()
    except Exception:
        pass

    db = get_db()
    existing_country = db.get_user_country(user_id)
    if existing_country and existing_country != "DE":
        # Country already set (non-default) — go straight to menu
        await _show_main_menu(callback_query.message, lang)
    else:
        # Show country selection (Germany is default but let user confirm)
        await show_country_selection(callback_query.message, lang)


def _get_situation_checker_button_label(lang: str) -> str:
    """Localized label for Situation Checker menu button."""
    _fallback = {"uk": "🔍 Моя ситуація", "en": "🔍 My Situation", "de": "🔍 Meine Situation",
                 "pl": "🔍 Moja sytuacja", "tr": "🔍 Durumum", "ar": "🔍 وضعي"}
    try:
        from backend.texts import get_text
        l = "uk" if lang in ("ua", "uk") else lang
        return get_text("situation_checker", "situation_checker_btn", l) or _fallback.get(l, _fallback["en"])
    except Exception:
        return _fallback.get(lang, _fallback.get("uk", "🔍 My Situation"))


def _get_document_label(doc_type: str, lang: str, description_only: bool = False) -> str:
    """
    Get document label for inline button (short German name) or description text.
    description_only=True → returns localized description string (for message text).
    description_only=False (default) → returns 'emoji GermanName' for button label.
    """
    # Document emojis
    doc_emojis = {
        "anmeldung": "📝",
        "abmeldung": "📝",
        "wohnungsgeberbestaetigung": "📋",
        "anmeldung_familie": "👨‍👩‍👧",
        "kindergeld": "👶",
        "elterngeld": "👨‍👩‍👧",
        "kinderzuschlag": "💰",
        "unterhaltsvorschuss": "💳",
        "anlage_kind": "📋",
        "steuer_id_kind": "🆔",
        "buergergeld": "💶",
        "wohngeld": "🏠",
        "arbeitslosengeld_1": "💼",
        "arbeitslosengeld_2": "💼",
        "krankenversicherung_anmeldung": "🏥",
        "sozialversicherungsnummer": "🆔",
        "arbeitserlaubnis": "💼",
        "steuererklaerung": "📊",
        "gewerbeanmeldung": "🏢",
        "kuendigung": "✉️",
        "arbeitslosmeldung": "📋",
        "aufenthaltstitel": "🛂",
        "bafoeg": "🎓",
        "wbs": "🏡",
        "ebk": "👶",
        "verpflichtungserklaerung": "📜",
        "beschaeftigungserklaerung": "💼",
        "mietbescheinigung": "📋",
        "jobcenter": "💶",
    }
    
    # Document descriptions (localized)
    # CRITICAL: Use "ua" not "uk" to match normalization logic
    doc_descriptions = {
        "anmeldung": {
            "ua": "Реєстрація місця проживання в Німеччині",
            "en": "Register your address in Germany",
            "de": "Anmeldung",
            "pl": "Rejestracja",
            "tr": "Kayıt",
            "ar": "التسجيل",
        },
        "abmeldung": {
            "ua": "Зняття з реєстрації при виїзді",
            "en": "Deregister your address",
            "de": "Abmeldung",
            "pl": "Wyrejestrowanie",
            "tr": "Kayıt silme",
            "ar": "إلغاء التسجيل",
        },
        "wohnungsgeberbestaetigung": {
            "ua": "Підтвердження від орендодавця для реєстрації",
            "en": "Landlord confirmation for registration",
            "de": "Wohnungsgeberbestätigung",
            "pl": "Potwierdzenie właściciela",
            "tr": "Ev sahibi onayı",
            "ar": "تأكيد المالك",
        },
        "anmeldung_familie": {
            "ua": "Реєстрація сім'ї",
            "en": "Family registration",
            "de": "Familienanmeldung",
            "pl": "Rejestracja rodziny",
            "tr": "Aile kaydı",
            "ar": "تسجيل العائلة",
        },
        "kindergeld": {
            "ua": "Державна допомога на дитину",
            "en": "Child benefit application",
            "de": "Kindergeld",
            "pl": "Zasiłek na dziecko",
            "tr": "Çocuk yardımı",
            "ar": "إعانة الطفل",
        },
        "elterngeld": {
            "ua": "Державна допомога батькам після народження дитини",
            "uk": "Державна допомога батькам після народження дитини",
            "en": "Parental allowance after the birth of a child",
            "de": "Elterngeld",
            "pl": "Zasiłek rodzicielski po urodzeniu dziecka",
            "tr": "Doğum sonrası ebeveyn yardımı",
            "ar": "إعانة الوالدين بعد الولادة",
        },
        "kinderzuschlag": {
            "ua": "Додаткова допомога сім'ям з дітьми",
            "en": "Extra benefit for families with children",
            "de": "Kinderzuschlag",
            "pl": "Dodatek na dziecko",
            "tr": "Çocuk ek ödeneği",
            "ar": "مكمل الطفل",
        },
        "unterhaltsvorschuss": {
            "ua": "Аванс по аліментах від держави",
            "en": "State advance child support",
            "de": "Unterhaltsvorschuss",
            "pl": "Zaliczka alimentacyjna",
            "tr": "Nafaka avansı",
            "ar": "سلفة النفقة",
        },
        "anlage_kind": {
            "ua": "Дані дитини для оформлення Kindergeld",
            "en": "Child details for Kindergeld",
            "de": "Anlage Kind",
            "pl": "Załącznik dla dziecka",
            "tr": "Çocuk eki",
            "ar": "مرفق الطفل",
        },
        "steuer_id_kind": {
            "ua": "Податковий ID дитини",
            "en": "Child tax ID",
            "de": "Steuer-ID Kind",
            "pl": "ID podatkowe dziecka",
            "tr": "Çocuk vergi kimliği",
            "ar": "هوية الطفل الضريبية",
        },
        "buergergeld": {
            "ua": "Заява до Jobcenter на фінансову допомогу",
            "en": "Jobcenter application for financial support",
            "de": "Bürgergeld",
            "pl": "Zasiłek obywatelski",
            "tr": "Vatandaş yardımı",
            "ar": "إعانة المواطن",
        },
        "wohngeld": {
            "ua": "Житлова допомога для зменшення витрат на оренду",
            "en": "Housing benefit to reduce rent costs",
            "de": "Wohngeld",
            "pl": "Dodatek mieszkaniowy",
            "tr": "Konut yardımı",
            "ar": "بدل السكن",
        },
        "arbeitslosengeld_1": {
            "ua": "Допомога по безробіттю після роботи",
            "en": "Unemployment benefit after employment",
            "de": "Arbeitslosengeld I",
            "pl": "Zasiłek dla bezrobotnych I",
            "tr": "İşsizlik yardımı I",
            "ar": "إعانة البطالة I",
        },
        "arbeitslosengeld_2": {
            "ua": "Допомога по безробіттю II",
            "en": "Unemployment benefit II",
            "de": "Arbeitslosengeld II",
            "pl": "Zasiłek dla bezrobotnych II",
            "tr": "İşsizlik yardımı II",
            "ar": "إعانة البطالة II",
        },
        "krankenversicherung_anmeldung": {
            "ua": "Реєстрація страхування",
            "en": "Health insurance registration",
            "de": "Krankenversicherung Anmeldung",
            "pl": "Rejestracja ubezpieczenia",
            "tr": "Sağlık sigortası kaydı",
            "ar": "تسجيل التأمين الصحي",
        },
        "sozialversicherungsnummer": {
            "ua": "Номер соцстрахування",
            "en": "Social security number",
            "de": "Sozialversicherungsnummer",
            "pl": "Numer ubezpieczenia społecznego",
            "tr": "Sosyal güvenlik numarası",
            "ar": "رقم الضمان الاجتماعي",
        },
        "arbeitserlaubnis": {
            "ua": "Дозвіл на роботу",
            "en": "Work permit",
            "de": "Arbeitserlaubnis",
            "pl": "Pozwolenie na pracę",
            "tr": "Çalışma izni",
            "ar": "تصريح العمل",
        },
        "steuererklaerung": {
            "ua": "Податкова декларація",
            "en": "Tax return",
            "de": "Steuererklärung",
            "pl": "Rozliczenie podatkowe",
            "tr": "Vergi beyannamesi",
            "ar": "الإقرار الضريبي",
        },
        "gewerbeanmeldung": {
            "ua": "Реєстрація власної діяльності (бізнесу)",
            "en": "Register a business activity",
            "de": "Gewerbeanmeldung",
            "pl": "Rejestracja działalności",
            "tr": "İş kaydı",
            "ar": "تسجيل الأعمال",
        },
        "kuendigung": {
            "ua": "Шаблон листа для розірвання трудового договору",
            "en": "Letter template to terminate employment",
            "de": "Kündigung",
            "pl": "Wypowiedzenie",
            "tr": "Fesih",
            "ar": "الإنهاء",
        },
        "arbeitslosmeldung": {
            "ua": "Реєстрація безробіття",
            "en": "Unemployment registration",
            "de": "Arbeitslosmeldung",
            "pl": "Rejestracja bezrobocia",
            "tr": "İşsizlik kaydı",
            "ar": "تسجيل البطالة",
        },
        "aufenthaltstitel": {
            "ua": "Отримання або подовження дозволу на перебування",
            "uk": "Отримання або подовження дозволу на перебування",
            "en": "Apply for or extend your residence permit",
            "de": "Erteilung oder Verlängerung des Aufenthaltstitels",
            "pl": "Uzyskanie lub przedłużenie tytułu pobytowego",
            "tr": "Oturma izni almak veya uzatmak",
            "ar": "الحصول على تصريح الإقامة أو تمديده",
        },
        "bafoeg": {
            "uk": "Федеральна допомога студентам на навчання",
            "ua": "Федеральна допомога студентам на навчання",
            "en": "Federal student financial aid for education",
            "de": "Bundesausbildungsförderungsgesetz (BAföG)",
            "pl": "Federalne wsparcie finansowe dla studentów",
            "tr": "Federal öğrenci eğitim desteği",
            "ar": "المساعدة المالية الفيدرالية للطلاب",
        },
        "wbs": {
            "uk": "Свідоцтво на право соціального житла",
            "en": "Certificate for social housing eligibility",
            "de": "Berechtigungsnachweis für Sozialwohnung",
            "pl": "Zaświadczenie o prawie do mieszkania socjalnego",
            "tr": "Sosyal konut hak belgesi",
            "ar": "شهادة الأحقية في السكن الاجتماعي",
        },
        "ebk": {
            "uk": "Заява для підтримки сімей з дітьми в Jobcenter",
            "en": "Application for child poverty support at Jobcenter",
            "de": "Erklärung zur Bekämpfung der Kinderarmut (Jobcenter)",
            "pl": "Wniosek o wsparcie dla rodzin z dziećmi w Jobcenter",
            "tr": "Jobcenter'da çocuk yoksulluğuyla mücadele beyanı",
            "ar": "طلب دعم مكافحة فقر الأطفال في مركز التوظيف",
        },
        "verpflichtungserklaerung": {
            "uk": "Фінансове зобов'язання для запрошення іноземця",
            "en": "Financial guarantee for inviting a foreigner to Germany",
            "de": "Verpflichtungserklärung für die Einladung von Ausländern",
            "pl": "Zobowiązanie finansowe dla zaproszenia cudzoziemca",
            "tr": "Yabancı davet etmek için mali taahhüt belgesi",
            "ar": "تعهد مالي لدعوة أجنبي إلى ألمانيا",
        },
        "beschaeftigungserklaerung": {
            "uk": "Підтвердження зайнятості від роботодавця",
            "en": "Employment declaration from employer",
            "de": "Beschäftigungserklärung des Arbeitgebers",
            "pl": "Oświadczenie o zatrudnieniu od pracodawcy",
            "tr": "İşverenden istihdam beyanı",
            "ar": "إقرار التوظيف من صاحب العمل",
        },
        "mietbescheinigung": {
            "uk": "Довідка від орендодавця про умови проживання",
            "en": "Landlord certificate confirming tenancy conditions",
            "de": "Bescheinigung des Vermieters über die Wohnverhältnisse",
            "pl": "Zaświadczenie wynajmującego o warunkach najmu",
            "tr": "Kiralama koşullarını belgeleyen ev sahibi sertifikası",
            "ar": "شهادة المالك تؤكد شروط الإيجار",
        },
    }

    # Normalize language code: canonical is "uk" for Ukrainian
    if lang == "ua":
        lang = "uk"
    if lang not in ["uk", "en", "de", "pl", "tr", "ar"]:
        lang = "en"

    # Get German document name (always in German)
    doc_name_german = {
        "anmeldung": "Anmeldung",
        "abmeldung": "Abmeldung",
        "wohnungsgeberbestaetigung": "Wohnungsgeberbestätigung",
        "anmeldung_familie": "Anmeldung Familie",
        "kindergeld": "Kindergeld",
        "elterngeld": "Elterngeld",
        "kinderzuschlag": "Kinderzuschlag",
        "unterhaltsvorschuss": "Unterhaltsvorschuss",
        "anlage_kind": "Anlage Kind",
        "steuer_id_kind": "Steuer-ID Kind",
        "buergergeld": "Bürgergeld",
        "wohngeld": "Wohngeld",
        "arbeitslosengeld_1": "Arbeitslosengeld I",
        "arbeitslosengeld_2": "Arbeitslosengeld II",
        "krankenversicherung_anmeldung": "Krankenversicherung Anmeldung",
        "sozialversicherungsnummer": "Sozialversicherungsnummer",
        "arbeitserlaubnis": "Arbeitserlaubnis",
        "steuererklaerung": "Steuererklärung",
        "gewerbeanmeldung": "Gewerbeanmeldung",
        "kuendigung": "Kündigung",
        "arbeitslosmeldung": "Arbeitslosmeldung",
        "aufenthaltstitel": "Aufenthaltstitel",
        "bafoeg": "BAföG",
        "wbs": "Wohnberechtigungsschein",
        "ebk": "Erklärung zur Bekämpfung der Kinderarmut",
        "verpflichtungserklaerung": "Verpflichtungserklärung",
        "beschaeftigungserklaerung": "Beschäftigungserklärung",
        "mietbescheinigung": "Mietbescheinigung",
        "jobcenter": "Jobcenter-Antrag",
    }

    emoji = doc_emojis.get(doc_type, "📄")
    german_name = doc_name_german.get(doc_type, doc_type)
    description_dict = doc_descriptions.get(doc_type, {})
    # Fallback chain: uk → ua (for older dicts) → en
    description = (
        description_dict.get(lang)
        or description_dict.get("ua")
        or description_dict.get("en", "")
    )

    if description_only:
        return description or ""

    # Button label: always short German name (fits mobile width)
    return f"{emoji} {german_name}"


CATEGORY_TIPS = {
    "residence": {
        "uk": "⚠️ Anmeldung потрібно зробити протягом <b>14 днів</b> після переїзду.",
        "en": "⚠️ Anmeldung must be done within <b>14 days</b> of moving.",
        "de": "⚠️ Anmeldung muss innerhalb von <b>14 Tagen</b> nach dem Umzug erfolgen.",
        "pl": "⚠️ Anmeldung należy złożyć w ciągu <b>14 dni</b> od przeprowadzki.",
        "tr": "⚠️ Anmeldung, taşınmadan sonra <b>14 gün</b> içinde yapılmalıdır.",
        "ar": "⚠️ يجب تقديم Anmeldung خلال <b>14 يومًا</b> من الانتقال.",
    },
    "benefits": {
        "uk": "💡 Більшість виплат не діють заднім числом — подавайте якнайшвидше.",
        "en": "💡 Most benefits are not retroactive — apply as soon as possible.",
        "de": "💡 Die meisten Leistungen gelten nicht rückwirkend — beantragen Sie schnell.",
        "pl": "💡 Większość świadczeń nie działa wstecz — złóż wniosek jak najszybciej.",
        "tr": "💡 Yardımlar genellikle geriye dönük geçerli değildir — hemen başvurun.",
        "ar": "💡 معظم المساعدات لا تُطبَّق بأثر رجعي — تقدم في أسرع وقت.",
    },
    "employment": {
        "uk": "💡 Подайте заяву на подовження мінімум за 8 тижнів до закінчення дозволу.",
        "en": "💡 Apply for extension at least 8 weeks before your permit expires.",
        "de": "💡 Beantragen Sie die Verlängerung mindestens 8 Wochen vor Ablauf.",
        "pl": "💡 Złóż wniosek o przedłużenie co najmniej 8 tygodni przed wygaśnięciem.",
        "tr": "💡 İzniniz sona ermeden en az 8 hafta önce uzatma başvurusu yapın.",
        "ar": "💡 تقدم بطلب التمديد قبل 8 أسابيع على الأقل من انتهاء التصريح.",
    },
    "financial": {
        "uk": "💡 Більшість виплат не діють заднім числом — подавайте якнайшвидше.",
        "en": "💡 Most benefits are not retroactive — apply as soon as possible.",
        "de": "💡 Die meisten Leistungen gelten nicht rückwirkend — beantragen Sie schnell.",
        "pl": "💡 Większość świadczeń nie działa wstecz — złóż wniosek jak najszybciej.",
        "tr": "💡 Yardımlar genellikle geriye dönük geçerli değildir — hemen başvurun.",
        "ar": "💡 معظم المساعدات لا تُطبَّق بأثر رجعي — تقدم في أسرع وقت.",
    },
}


async def _show_flat_doc_list(message: types.Message, lang: str):
    """Show all available documents in a flat list with group labels in the message text.
    Replaces the 2-level category → document selection flow.
    """
    _l = "uk" if lang in ("ua", "uk") else lang
    if _l not in ("uk", "en", "de", "pl", "tr", "ar"):
        _l = "en"

    _headers = {
        "uk": "📄 <b>Оберіть потрібний документ</b>",
        "en": "📄 <b>Choose the document you need</b>",
        "de": "📄 <b>Wählen Sie das benötigte Dokument</b>",
        "pl": "📄 <b>Wybierz potrzebny dokument</b>",
        "tr": "📄 <b>İhtiyacınız olan belgeyi seçin</b>",
        "ar": "📄 <b>اختر المستند الذي تحتاجه</b>",
    }
    _benefits_labels = {
        "uk": "💰 <b>Виплати та підтримка</b>",
        "en": "💰 <b>Benefits & Support</b>",
        "de": "💰 <b>Leistungen & Unterstützung</b>",
        "pl": "💰 <b>Świadczenia i wsparcie</b>",
        "tr": "💰 <b>Yardımlar ve destek</b>",
        "ar": "💰 <b>المدفوعات والدعم</b>",
    }

    # Documents in display order
    residence_docs = ["anmeldung", "wohnungsgeberbestaetigung", "mietbescheinigung", "aufenthaltstitel"]
    benefits_docs  = ["buergergeld", "kindergeld", "wohngeld"]

    try:
        from handlers.docs_new import _get_doc_prices
        _prices = _get_doc_prices()
    except Exception:
        _prices = {}

    # Section divider labels (plain text — no HTML, used as disabled separator buttons)
    _divider_labels = {
        "uk": "──── 💰 Виплати та підтримка ────",
        "en": "──── 💰 Benefits & Support ────",
        "de": "──── 💰 Leistungen & Unterstützung ────",
        "pl": "──── 💰 Świadczenia i wsparcie ────",
        "tr": "──── 💰 Yardımlar ve destek ────",
        "ar": "──── 💰 المساعدات والدعم ────",
    }

    header_text = _headers.get(_l, _headers["en"])

    kb = InlineKeyboardMarkup(row_width=1)
    for i, doc_type in enumerate(residence_docs):
        doc_label = _get_document_label(doc_type, _l)
        price = _prices.get(doc_type)
        label = f"{doc_label} — €{price:.2f}" if price else doc_label
        if i == 0:
            label = "❗ " + label
        kb.add(InlineKeyboardButton(label, callback_data=f"doc_{doc_type}"))

    # Visual separator between the two groups
    kb.add(InlineKeyboardButton(
        _divider_labels.get(_l, _divider_labels["en"]),
        callback_data="noop",
    ))

    for doc_type in benefits_docs:
        doc_label = _get_document_label(doc_type, _l)
        price = _prices.get(doc_type)
        label = f"{doc_label} — €{price:.2f}" if price else doc_label
        kb.add(InlineKeyboardButton(label, callback_data=f"doc_{doc_type}"))

    kb.add(InlineKeyboardButton(_nav_back_text(_l), callback_data="back_to_main_menu"))
    await message.answer(header_text, parse_mode="HTML", reply_markup=kb)


async def _show_doc_type_categories(message: types.Message, lang: str):
    """Show top-level document category selection: Housing and Financial."""
    _l = "uk" if lang in ("ua", "uk") else lang
    if _l not in ("uk", "en", "de", "pl", "tr", "ar"):
        _l = "en"

    _titles = {
        "uk": "📄 <b>Оберіть категорію документів</b>",
        "en": "📄 <b>Choose document category</b>",
        "de": "📄 <b>Dokumentkategorie auswählen</b>",
        "pl": "📄 <b>Wybierz kategorię dokumentów</b>",
        "tr": "📄 <b>Belge kategorisi seçin</b>",
        "ar": "📄 <b>اختر فئة المستند</b>",
    }
    _housing = {
        "uk": "🏠 Проживання та реєстрація",
        "en": "🏠 Housing & Registration",
        "de": "🏠 Wohnen & Anmeldung",
        "pl": "🏠 Mieszkanie i rejestracja",
        "tr": "🏠 İkamet ve kayıt",
        "ar": "🏠 الإقامة والتسجيل",
    }
    _financial = {
        "uk": "💰 Фінансові документи",
        "en": "💰 Financial Documents",
        "de": "💰 Finanzielle Dokumente",
        "pl": "💰 Dokumenty finansowe",
        "tr": "💰 Finansal Belgeler",
        "ar": "💰 الوثائق المالية",
    }

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_housing.get(_l, _housing["en"]), callback_data="docs_housing"),
        InlineKeyboardButton(_financial.get(_l, _financial["en"]), callback_data="docs_financial"),
        InlineKeyboardButton(_nav_back_text(lang), callback_data="back_to_main_menu"),
    )
    await message.answer(_titles.get(_l, _titles["en"]), parse_mode="HTML", reply_markup=kb)


async def _show_category_documents(message: types.Message, category: str, lang: str):
    """Show documents for a specific category.
    Residence: Anmeldung, Ummeldung, Wohnungsgeberbestätigung, Abmeldung
    Benefits:  Wohngeld, Kindergeld, Bürgergeld, …
    Employment: Aufenthaltstitel, Verpflichtungserklärung, EBK, …
    """
    try:
        from bot_config.menu_structure import CATEGORY_DOCS as _CDOCS
        category_doc_types = dict(_CDOCS)
        # Backward-compat aliases
        category_doc_types["finance"] = _CDOCS.get("benefits", [])
        category_doc_types["family"] = _CDOCS.get("benefits", [])
    except Exception:
        residence_docs = ["anmeldung", "mietbescheinigung", "wohnungsgeberbestaetigung"]
        benefits_docs = ["wohngeld", "kindergeld", "buergergeld"]
        employment_docs = ["aufenthaltstitel"]
        category_doc_types = {
            "residence": residence_docs,
            "benefits": benefits_docs,
            "employment": employment_docs,
            "finance": benefits_docs,
            "family": benefits_docs,
        }
    
    # Category titles localized (user language)
    category_titles = {
        "uk": {
            "residence": "🏠 <b>Проживання та реєстрація</b>\n\nОберіть документ:",
            "financial": "💰 <b>Фінансові документи</b>\n\nОберіть документ:",
            "benefits": "💰 <b>Виплати та підтримка</b>\n\nОберіть документ:",
            "employment": "💼 <b>Робота та зайнятість</b>\n\nОберіть документ:",
            "finance": "💰 <b>Виплати та підтримка</b>\n\nОберіть документ:",
            "family": "💰 <b>Виплати та підтримка</b>\n\nОберіть документ:",
        },
        "ua": {
            "residence": "🏠 <b>Проживання та реєстрація</b>\n\nОберіть документ:",
            "financial": "💰 <b>Фінансові документи</b>\n\nОберіть документ:",
            "benefits": "💰 <b>Виплати та підтримка</b>\n\nОберіть документ:",
            "employment": "💼 <b>Робота та зайнятість</b>\n\nОберіть документ:",
            "finance": "💰 <b>Виплати та підтримка</b>\n\nОберіть документ:",
            "family": "💰 <b>Виплати та підтримка</b>\n\nОберіть документ:",
        },
        "en": {
            "residence": "🏠 <b>Housing & Registration</b>\n\nSelect document:",
            "financial": "💰 <b>Financial Documents</b>\n\nSelect document:",
            "benefits": "💰 <b>Benefits & Support</b>\n\nSelect document:",
            "employment": "💼 <b>Work & Employment</b>\n\nSelect document:",
            "finance": "💰 <b>Benefits & Support</b>\n\nSelect document:",
            "family": "💰 <b>Benefits & Support</b>\n\nSelect document:",
        },
        "de": {
            "residence": "🏠 <b>Wohnen & Anmeldung</b>\n\nDokument auswählen:",
            "financial": "💰 <b>Finanzielle Dokumente</b>\n\nDokument auswählen:",
            "benefits": "💰 <b>Leistungen & Unterstützung</b>\n\nDokument auswählen:",
            "employment": "💼 <b>Arbeit & Beschäftigung</b>\n\nDokument auswählen:",
            "finance": "💰 <b>Leistungen & Unterstützung</b>\n\nDokument auswählen:",
            "family": "💰 <b>Leistungen & Unterstützung</b>\n\nDokument auswählen:",
        },
        "pl": {
            "residence": "🏠 <b>Mieszkanie i rejestracja</b>\n\nWybierz dokument:",
            "financial": "💰 <b>Dokumenty finansowe</b>\n\nWybierz dokument:",
            "benefits": "💰 <b>Świadczenia i wsparcie</b>\n\nWybierz dokument:",
            "employment": "💼 <b>Praca i zatrudnienie</b>\n\nWybierz dokument:",
            "finance": "💰 <b>Świadczenia i wsparcie</b>\n\nWybierz dokument:",
            "family": "💰 <b>Świadczenia i wsparcie</b>\n\nWybierz dokument:",
        },
        "tr": {
            "residence": "🏠 <b>İkamet ve kayıt</b>\n\nBelge seçin:",
            "financial": "💰 <b>Finansal Belgeler</b>\n\nBelge seçin:",
            "benefits": "💰 <b>Yardımlar ve destek</b>\n\nBelge seçin:",
            "employment": "💼 <b>İş ve istihdam</b>\n\nBelge seçin:",
            "finance": "💰 <b>Yardımlar ve destek</b>\n\nBelge seçin:",
            "family": "💰 <b>Yardımlar ve destek</b>\n\nBelge seçin:",
        },
        "ar": {
            "residence": "🏠 <b>الإقامة والتسجيل</b>\n\nاختر المستند:",
            "financial": "💰 <b>الوثائق المالية</b>\n\nاختر المستند:",
            "benefits": "💰 <b>المدفوعات والدعم</b>\n\nاختر المستند:",
            "employment": "💼 <b>العمل والتوظيف</b>\n\nاختر المستند:",
            "finance": "💰 <b>المدفوعات والدعم</b>\n\nاختر المستند:",
            "family": "💰 <b>المدفوعات والدعم</b>\n\nاختر المستند:",
        },
    }
    
    # Normalize language code: canonical is "uk" for Ukrainian
    if lang == "ua":
        lang = "uk"
    if lang not in ["uk", "ua", "en", "de", "pl", "tr", "ar"]:
        lang = "en"

    # Get document types for this category
    doc_types = category_doc_types.get(category, [])

    # Get category title (fallback to 'en' if language missing)
    title = category_titles.get(lang, category_titles.get("en", {})).get(category, "")

    _tip = CATEGORY_TIPS.get(category, {}).get(lang, "")
    if _tip:
        title = title + "\n\n" + _tip

    # Fetch live prices so buttons match what users see everywhere else
    try:
        from handlers.docs_new import _get_doc_prices
        _prices = _get_doc_prices()
    except Exception:
        _prices = {}

    # Build keyboard: documents first, then situation helper, then Back
    kb = InlineKeyboardMarkup(row_width=1)
    for i, doc_type in enumerate(doc_types):
        doc_label = _get_document_label(doc_type, lang)
        price = _prices.get(doc_type)
        label_with_price = f"{doc_label} — €{price:.2f}" if price else doc_label
        # Highlight the first (most important) doc in the residence category
        if category == "residence" and i == 0:
            label_with_price = "❗ " + label_with_price
        kb.add(InlineKeyboardButton(label_with_price, callback_data=f"doc_{doc_type}"))

    # Back to category selection for the two new top-level categories;
    # legacy categories fall back to main menu as before.
    _back_cb = (
        "back_to_doc_categories"
        if category in ("residence", "financial")
        else "back_to_main_menu"
    )
    kb.add(InlineKeyboardButton(_nav_back_text(lang), callback_data=_back_cb))

    await message.answer(title, parse_mode="HTML", reply_markup=kb)


async def handle_category_selection(callback_query: types.CallbackQuery):
    """Handle category selection (category_family, category_residence, category_termin, etc.)"""
    # CRITICAL: Answer callback immediately to prevent "Unhandled callback query" spam
    await callback_query.answer()
    
    user_id = callback_query.from_user.id
    category = callback_query.data.replace("category_", "")
    lang = get_user_lang(user_id)

    # Defensive: clear any lingering Termin FSM state so document flow is not blocked
    try:
        _dp = Dispatcher.get_current()
        if _dp:
            _fsm = _dp.current_state(
                chat=callback_query.message.chat.id,
                user=callback_query.from_user.id,
            )
            _cur = await _fsm.get_state()
            if _cur and _cur.startswith('TerminStates:'):
                await _fsm.finish()
    except Exception:
        pass
    
    logger.debug("handle_category_selection user=%s category=%s", user_id, category)
    
    # CRITICAL FIX: Preserve existing questionnaire data during navigation
    # Do NOT clear _PENDING_PREVIEWS when selecting category - user might return to form
    # Import here to avoid circular dependency
    try:
        from handlers.docs_new import _cleanup_old_previews
        _cleanup_old_previews()  # Only removes expired entries (>20 min old)
    except ImportError:
        pass  # If module not available, skip cleanup
    
    # Special handling for Termin category — delegate to termin flow
    if category == "termin":
        from handlers.termin import show_termin_menu_entry
        return await show_termin_menu_entry(callback_query.message, callback_query.from_user.id)

    await _show_category_documents(callback_query.message, category, lang)



# ============================================================================
# TERMIN PAGE - Appointment preparation feature
# ============================================================================

TERMIN_PAGE_TEXTS = {
    "uk": (
        "🗓 <b>Запис на прийом (Termin)</b>\n\n"
        "Підготуйте документи заздалегідь — і запишіться\n"
        "на сайті Bürgeramt вашого міста."
    ),
    "ua": (
        "🗓 <b>Запис на прийом (Termin)</b>\n\n"
        "Підготуйте документи заздалегідь — і запишіться\n"
        "на сайті Bürgeramt вашого міста."
    ),
    "en": (
        "🗓 <b>Appointment (Termin)</b>\n\n"
        "Prepare your documents in advance — and book\n"
        "on your city's Bürgeramt website."
    ),
    "de": (
        "🗓 <b>Termin</b>\n\n"
        "Bereiten Sie Ihre Unterlagen vor — und buchen Sie\n"
        "auf der Website Ihres Bürgeramts."
    ),
    "pl": (
        "🗓 <b>Wizyta w urzędzie (Termin)</b>\n\n"
        "Przygotuj dokumenty wcześniej — i umów się\n"
        "na stronie Bürgeramt Twojego miasta."
    ),
    "tr": (
        "🗓 <b>Randevu (Termin)</b>\n\n"
        "Belgelerinizi önceden hazırlayın — ve şehrinizin\n"
        "Bürgeramt web sitesinden randevu alın."
    ),
    "ar": (
        "🗓 <b>الموعد (Termin)</b>\n\n"
        "جهّز مستنداتك مسبقاً — واحجز موعدًا\n"
        "على موقع Bürgeramt لمدينتك."
    ),
}


async def _show_termin_page(message: types.Message, lang: str):
    """Show Termin (appointment preparation) page."""
    # Normalize language
    text_lang = lang
    if text_lang == "ua":
        text_lang = "uk"
    if text_lang not in TERMIN_PAGE_TEXTS:
        text_lang = "en"
    
    text = TERMIN_PAGE_TEXTS.get(text_lang, TERMIN_PAGE_TEXTS["en"])
    
    # Navigation buttons
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_nav_back_text(lang), callback_data="back_to_main_menu"))

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# Two navigation buttons (⬅️ Назад, 🏠 Головне меню) — used in category and all subsequent screens
NAV_BACK_TEXTS = {
    "uk": "⬅️ Назад", "ua": "⬅️ Назад", "en": "⬅️ Back", "de": "⬅️ Zurück",
    "pl": "⬅️ Wstecz", "tr": "⬅️ Geri", "ar": "⬅️ رجوع",
}
NAV_HOME_TEXTS = {
    "uk": "🏠 Головне меню", "ua": "🏠 Головне меню", "en": "🏠 Main Menu", "de": "🏠 Hauptmenü",
    "pl": "🏠 Menu główne", "tr": "🏠 Ana Menü", "ar": "🏠 القائمة الرئيسية",
}


def _nav_back_text(lang: str) -> str:
    return NAV_BACK_TEXTS.get(lang, NAV_BACK_TEXTS.get("ua", NAV_BACK_TEXTS.get("en", "⬅️ Back")))


def _nav_home_text(lang: str) -> str:
    return NAV_HOME_TEXTS.get(lang, NAV_HOME_TEXTS.get("ua", NAV_HOME_TEXTS.get("en", "🏠 Main Menu")))


async def handle_go_home(callback_query: types.CallbackQuery, state: FSMContext):
    """Go to main menu from anywhere. Clears FSM state. Always shows the 3-category main menu."""
    await callback_query.answer()
    try:
        await state.finish()
    except Exception:
        pass
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    try:
        from handlers.docs_new import _cleanup_old_previews
        _cleanup_old_previews()
    except ImportError:
        pass
    await _show_main_menu(callback_query.message, lang)


async def handle_how_to_submit_doc(callback_query: types.CallbackQuery):
    """Secondary screen: show submission instructions (moved out of post-PDF to reduce cognitive load)."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = (get_user_lang(user_id) or "uk").strip().lower()
    if lang == "ua":
        lang = "uk"
    if lang not in ("uk", "en", "de", "pl", "tr", "ar"):
        lang = "en"

    _guide_text = {
        "uk": (
            "📍 <b>Як подати документ</b>\n\n"
            "Подати документ потрібно особисто у <b>Bürgeramt</b>.\n\n"
            "Візьміть із собою:\n"
            "• Паспорт або ID-картку\n"
            "• Договір оренди (Mietvertrag)\n"
            "• Підтвердження від орендодавця (Wohnungsgeberbestätigung)\n\n"
            "Офіційний запис на прийом:\nhttps://service.berlin.de/terminvereinbarung/"
        ),
        "en": (
            "📍 <b>How to submit your document</b>\n\n"
            "You need to submit the document in person at <b>Bürgeramt</b>.\n\n"
            "Bring with you:\n"
            "• Passport or ID card\n"
            "• Rental contract (Mietvertrag)\n"
            "• Landlord confirmation (Wohnungsgeberbestätigung)\n\n"
            "Official appointment booking:\nhttps://service.berlin.de/terminvereinbarung/"
        ),
        "de": (
            "📍 <b>So reichen Sie Ihr Dokument ein</b>\n\n"
            "Das Dokument muss persönlich beim <b>Bürgeramt</b> eingereicht werden.\n\n"
            "Bringen Sie mit:\n"
            "• Reisepass oder Personalausweis\n"
            "• Mietvertrag\n"
            "• Wohnungsgeberbestätigung\n\n"
            "Offizielle Terminbuchung:\nhttps://service.berlin.de/terminvereinbarung/"
        ),
        "pl": (
            "📍 <b>Jak złożyć dokument</b>\n\n"
            "Dokument należy złożyć osobiście w <b>Bürgeramt</b>.\n\n"
            "Weź ze sobą:\n"
            "• Paszport lub dowód osobisty\n"
            "• Umowę najmu (Mietvertrag)\n"
            "• Potwierdzenie od wynajmującego (Wohnungsgeberbestätigung)\n\n"
            "Oficjalna rezerwacja terminu:\nhttps://service.berlin.de/terminvereinbarung/"
        ),
        "tr": (
            "📍 <b>Belgenizi nasıl sunarsınız</b>\n\n"
            "Belgeyi <b>Bürgeramt</b>'a şahsen teslim etmeniz gerekir.\n\n"
            "Yanınıza alın:\n"
            "• Pasaport veya kimlik kartı\n"
            "• Kira sözleşmesi (Mietvertrag)\n"
            "• Ev sahibi onayı (Wohnungsgeberbestätigung)\n\n"
            "Resmi randevu:\nhttps://service.berlin.de/terminvereinbarung/"
        ),
        "ar": (
            "📍 <b>كيفية تقديم المستند</b>\n\n"
            "يجب تقديم المستند شخصيًا في <b>Bürgeramt</b>.\n\n"
            "أحضر معك:\n"
            "• جواز السفر أو بطاقة الهوية\n"
            "• عقد الإيجار (Mietvertrag)\n"
            "• تأكيد المالك (Wohnungsgeberbestätigung)\n\n"
            "الحجز الرسمي:\nhttps://service.berlin.de/terminvereinbarung/"
        ),
    }
    from handlers.nav import make_nav_kb
    kb = make_nav_kb(lang, back_cb="back_to_main_menu")
    await callback_query.message.answer(
        _guide_text.get(lang, _guide_text["en"]),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb,
    )


async def handle_back_to_main_menu(callback_query: types.CallbackQuery, state: FSMContext = None):
    """Handle back to main menu button — clears FSM state and shows category main menu."""
    await callback_query.answer()
    if state:
        try:
            await state.finish()
        except Exception:
            pass
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    try:
        from handlers.docs_new import _cleanup_old_previews
        _cleanup_old_previews()
    except ImportError:
        pass
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await _show_main_menu(callback_query.message, lang)


async def handle_retention_main_menu(callback_query: types.CallbackQuery, state: FSMContext = None):
    log_funnel(
        "RETENTION_CLICK",
        callback_query.from_user.id,
        **{"type": "return"},
    )
    await handle_back_to_main_menu(callback_query, state)


async def handle_my_orders(callback_query: types.CallbackQuery):
    """Handle my_orders callback - show user's orders"""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    db = get_db()
    
    try:
        orders = db.get_user_orders(user_id, limit=10)
    except Exception as e:
        logger.error(f"❌ Failed to get orders for user {user_id}: {e}")
        orders = []
    
    _back_btn_texts = {
        "uk": "◀️ Назад",
        "en": "◀️ Back",
        "de": "◀️ Zurück",
        "pl": "◀️ Wstecz",
        "tr": "◀️ Geri",
        "ar": "◀️ رجوع",
    }
    _back_label = _back_btn_texts.get(lang, _back_btn_texts["en"])

    if not orders:
        no_orders_texts = {
            "uk": "📋 У вас поки немає замовлень.",
            "en": "📋 You don't have any orders yet.",
            "de": "📋 Sie haben noch keine Bestellungen.",
            "pl": "📋 Nie masz jeszcze zamówień.",
            "tr": "📋 Henüz siparişiniz yok.",
            "ar": "📋 ليس لديك طلبات بعد.",
        }
        text = no_orders_texts.get(lang, no_orders_texts["en"])
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(_back_label, callback_data="back_to_main_menu"))
        await callback_query.message.edit_text(text, reply_markup=kb)
        return
    
    _header_texts = {
        "uk": "📋 <b>Мої замовлення:</b>\n\n",
        "en": "📋 <b>My Orders:</b>\n\n",
        "de": "📋 <b>Meine Bestellungen:</b>\n\n",
        "pl": "📋 <b>Moje zamówienia:</b>\n\n",
        "tr": "📋 <b>Siparişlerim:</b>\n\n",
        "ar": "📋 <b>طلباتي:</b>\n\n",
    }
    text = _header_texts.get(lang, _header_texts["en"])
    kb = InlineKeyboardMarkup(row_width=1)
    
    for order in orders[:10]:
        status_emoji = {"paid": "✅", "pending": "⏳", "failed": "❌"}.get(order.get("status", "pending"), "❓")
        order_text = f"{status_emoji} #{order.get('id', 'N/A')} | {order.get('doc_type', 'N/A')}"
        text += order_text + "\n"
    
    kb.add(InlineKeyboardButton(_back_label, callback_data="back_to_main_menu"))
    await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


def _format_order_date(created_at) -> str:
    """Format order created_at to DD.MM.YYYY for display."""
    if not created_at:
        return ""
    try:
        from datetime import datetime as _dt
        if isinstance(created_at, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return _dt.strptime(created_at[:19], fmt).strftime("%d.%m.%Y")
                except ValueError:
                    continue
        return str(created_at)[:10]
    except Exception:
        return str(created_at)[:10]


def _format_order_status(status: str, lang: str) -> str:
    """Return a short localized status label for display in My Documents list."""
    _STATUS = {
        "paid": {"uk": "Оплачено", "en": "Paid", "de": "Bezahlt", "pl": "Opłacono", "tr": "Ödendi", "ar": "مدفوع"},
        "sent": {"uk": "Надіслано", "en": "Sent", "de": "Gesendet", "pl": "Wysłano", "tr": "Gönderildi", "ar": "أُرسل"},
        "downloaded": {"uk": "Завантажено", "en": "Downloaded", "de": "Heruntergeladen", "pl": "Pobrano", "tr": "İndirildi", "ar": "تم التنزيل"},
        "preview": {"uk": "Preview", "en": "Preview", "de": "Vorschau", "pl": "Podgląd", "tr": "Önizleme", "ar": "معاينة"},
    }
    _l = lang if lang in ("uk", "en", "de", "pl", "tr", "ar") else "en"
    return _STATUS.get(status.lower(), {}).get(_l, status.capitalize())


async def handle_my_documents(callback_query: types.CallbackQuery):
    """
    Level 1 of My Documents: show categories that have paid orders, with counts.
    Example:
      🏠 Реєстрація (3)
      💰 Виплати (1)
      📅 Termin (2)
    """
    await callback_query.answer()

    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    if lang == "ua":
        lang = "uk"
    db = get_db()

    _TITLES = {
        "uk": "📂 <b>Мої документи</b>\n\nОберіть категорію:",
        "en": "📂 <b>My Documents</b>\n\nSelect category:",
        "de": "📂 <b>Meine Dokumente</b>\n\nKategorie wählen:",
        "pl": "📂 <b>Moje dokumenty</b>\n\nWybierz kategorię:",
        "tr": "📂 <b>Belgelerim</b>\n\nKategori seçin:",
        "ar": "📂 <b>مستنداتي</b>\n\nاختر الفئة:",
    }
    _EMPTY = {
        "uk": "📭 У вас поки немає оплачених документів.",
        "en": "📭 You don't have any paid documents yet.",
        "de": "📭 Sie haben noch keine bezahlten Dokumente.",
        "pl": "📭 Nie masz jeszcze żadnych opłaconych dokumentów.",
        "tr": "📭 Henüz ödenen belgeniz yok.",
        "ar": "📭 ليس لديك مستندات مدفوعة بعد.",
    }
    _BACK = {
        "uk": "◀️ Головне меню", "en": "◀️ Main Menu", "de": "◀️ Hauptmenü",
        "pl": "◀️ Menu główne", "tr": "◀️ Ana Menü", "ar": "◀️ القائمة الرئيسية",
    }

    try:
        orders = db.get_user_orders(user_id, limit=100)
    except Exception as e:
        logger.error("handle_my_documents: get_user_orders failed user=%s: %s", user_id, e)
        orders = []

    paid_statuses = {"paid", "sent", "downloaded"}
    paid_orders = [o for o in orders if (o.get("status") or "").lower() in paid_statuses]

    _l = lang if lang in _TITLES else "en"
    kb = InlineKeyboardMarkup(row_width=1)

    if not paid_orders:
        kb.add(InlineKeyboardButton(_BACK.get(_l, _BACK["en"]), callback_data="back_to_main_menu"))
        try:
            await callback_query.message.edit_text(_EMPTY.get(_l, _EMPTY["en"]), parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback_query.message.answer(_EMPTY.get(_l, _EMPTY["en"]), parse_mode="HTML", reply_markup=kb)
        return

    # Group by category, counting orders per category (exclude termin in the count label)
    try:
        from bot_config.menu_structure import get_doc_category, MY_DOCS_CATEGORY_TITLES, TERMIN_DOC_TYPES as _TERMIN
    except Exception:
        def get_doc_category(dt):
            return "other"
        MY_DOCS_CATEGORY_TITLES = {}
        _TERMIN = set()

    _cat_counts: dict = {}
    for o in paid_orders:
        _cat = get_doc_category(o.get("doc_type", ""))
        _cat_counts[_cat] = _cat_counts.get(_cat, 0) + 1

    # Show categories in fixed order; skip empty ones
    _cat_order = ["residence", "benefits", "employment", "termin", "other"]
    for cat in _cat_order:
        count = _cat_counts.get(cat, 0)
        if count == 0:
            continue
        _cat_labels = MY_DOCS_CATEGORY_TITLES.get(cat, {})
        _cat_label = _cat_labels.get(_l, _cat_labels.get("en", cat))
        kb.add(InlineKeyboardButton(f"{_cat_label} ({count})", callback_data=f"mydocs_cat_{cat}"))

    kb.add(InlineKeyboardButton(_BACK.get(_l, _BACK["en"]), callback_data="back_to_main_menu"))

    try:
        await callback_query.message.edit_text(_TITLES.get(_l, _TITLES["en"]), parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback_query.message.answer(_TITLES.get(_l, _TITLES["en"]), parse_mode="HTML", reply_markup=kb)


async def handle_my_docs_category(callback_query: types.CallbackQuery):
    """
    Level 2 of My Documents: show all paid orders in a specific category.
    Each row: DocName — DD.MM.YYYY — Status   [📥 re-download button]
    """
    await callback_query.answer()

    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    if lang == "ua":
        lang = "uk"
    db = get_db()

    category = callback_query.data.replace("mydocs_cat_", "").strip()

    _BACK_CAT = {
        "uk": "◀️ Мої документи", "en": "◀️ My Documents", "de": "◀️ Meine Dokumente",
        "pl": "◀️ Moje dokumenty", "tr": "◀️ Belgelerim", "ar": "◀️ مستنداتي",
    }
    _BACK_MENU = {
        "uk": "🏠 Головне меню", "en": "🏠 Main Menu", "de": "🏠 Hauptmenü",
        "pl": "🏠 Menu główne", "tr": "🏠 Ana Menü", "ar": "🏠 القائمة الرئيسية",
    }
    _DL_LABEL = {
        "uk": "📥 Завантажити", "en": "📥 Download", "de": "📥 Herunterladen",
        "pl": "📥 Pobierz", "tr": "📥 İndir", "ar": "📥 تنزيل",
    }

    _l = lang if lang in _BACK_CAT else "en"

    try:
        from bot_config.menu_structure import get_doc_category, MY_DOCS_CATEGORY_TITLES
    except Exception:
        def get_doc_category(dt):
            return "other"
        MY_DOCS_CATEGORY_TITLES = {}

    try:
        orders = db.get_user_orders(user_id, limit=100)
    except Exception as e:
        logger.error("handle_my_docs_category: get_user_orders failed user=%s: %s", user_id, e)
        orders = []

    paid_statuses = {"paid", "sent", "downloaded"}
    cat_orders = [
        o for o in orders
        if (o.get("status") or "").lower() in paid_statuses
        and get_doc_category(o.get("doc_type", "")) == category
    ]

    # Category heading
    _cat_labels = MY_DOCS_CATEGORY_TITLES.get(category, {})
    _cat_title = _cat_labels.get(_l, _cat_labels.get("en", category))

    _HEADING = {
        "uk": f"<b>{_cat_title}</b>\n\nОберіть документ для повторного завантаження:",
        "en": f"<b>{_cat_title}</b>\n\nSelect a document to re-download:",
        "de": f"<b>{_cat_title}</b>\n\nDokument zum erneuten Herunterladen auswählen:",
        "pl": f"<b>{_cat_title}</b>\n\nWybierz dokument do ponownego pobrania:",
        "tr": f"<b>{_cat_title}</b>\n\nYeniden indirmek için belge seçin:",
        "ar": f"<b>{_cat_title}</b>\n\nاختر مستندًا لإعادة التنزيل:",
    }
    heading = _HEADING.get(_l, _HEADING["en"])

    kb = InlineKeyboardMarkup(row_width=1)
    doc_lang = "ua" if lang == "uk" else lang

    for order in cat_orders[:25]:
        oid = order.get("order_id") or order.get("id")
        dtype = order.get("doc_type", "")
        doc_name = _get_document_label(dtype, doc_lang)
        date_str = _format_order_date(order.get("created_at"))
        status_str = _format_order_status(order.get("status", ""), lang)
        row_label = f"{doc_name}"
        if date_str:
            row_label += f" — {date_str}"
        row_label += f" — {status_str}"
        dl_btn = _DL_LABEL.get(_l, _DL_LABEL["en"])
        kb.add(InlineKeyboardButton(f"{dl_btn}  {row_label}", callback_data=f"resend_doc_{oid}"))

    kb.add(InlineKeyboardButton(_BACK_CAT.get(_l, _BACK_CAT["en"]), callback_data="my_documents"))
    kb.add(InlineKeyboardButton(_BACK_MENU.get(_l, _BACK_MENU["en"]), callback_data="back_to_main_menu"))

    try:
        await callback_query.message.edit_text(heading, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback_query.message.answer(heading, parse_mode="HTML", reply_markup=kb)


async def handle_change_language(callback_query: types.CallbackQuery):
    """Language picker from main menu — same clean layout, adds back button."""
    await callback_query.answer()
    lang = get_user_lang(callback_query.from_user.id)
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for label, cb in LANGUAGE_BUTTONS:
        # Use set_lang_* so the handler returns to main menu instead of re-running welcome
        keyboard.add(types.InlineKeyboardButton(text=label, callback_data=cb.replace("lang_", "set_lang_")))
    keyboard.add(types.InlineKeyboardButton(_nav_back_text(lang), callback_data="back_to_main_menu"))
    await callback_query.message.answer("🌍", reply_markup=keyboard)


async def handle_gdpr_confirmed(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle gdpr_confirmed callback - treat as GDPR accept, go directly to main menu"""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    db = get_db()
    
    db.set_gdpr_consent(user_id, True)
    try:
        await callback_query.message.delete()
    except:
        pass
    
    await _show_main_menu(callback_query.message, lang)


async def handle_gdpr_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Simplified GDPR callback handler.
    Only handles: gdpr_privacy, gdpr_terms, gdpr_back.
    Privacy/Terms → show text + "⬅️ Назад" → back edits message to welcome screen.
    gdpr_accept/decline are legacy — accept goes to menu, decline shows short message.
    """
    await callback_query.answer()
    user_id = callback_query.from_user.id
    action = callback_query.data.split('_')[1]
    lang = get_user_lang(user_id)

    gdpr = _get_gdpr_manager()

    if action == 'privacy' or action == 'terms':
        # Show privacy policy or terms text + single "⬅️ Назад" button
        if gdpr:
            content = gdpr.get_privacy_policy(lang) if action == 'privacy' else gdpr.get_terms_of_service(lang)
        else:
            content = "Privacy policy / Terms not available."
        _back_label = {
            "uk": "⬅️ Назад", "ua": "⬅️ Назад", "en": "⬅️ Back", "de": "⬅️ Zurück",
            "pl": "⬅️ Wstecz", "tr": "⬅️ Geri", "ar": "⬅️ رجوع",
        }
        _lk = "uk" if lang in ("ua", "uk") else lang
        back_kb = InlineKeyboardMarkup(row_width=1)
        back_kb.add(InlineKeyboardButton(
            _back_label.get(_lk, _back_label.get("en", "⬅️ Back")),
            callback_data="gdpr_back"
        ))
        try:
            await callback_query.message.edit_text(content, parse_mode="HTML", reply_markup=back_kb)
        except Exception:
            # Message too long or edit failed — send as new message
            await callback_query.message.answer(content, parse_mode="HTML", reply_markup=back_kb)
        return True

    elif action == 'back':
        # Return to welcome screen by re-rendering it in place (edit_text)
        lookup_lang = "uk" if lang in ("ua", "uk") else lang
        if lookup_lang not in SIMPLE_INTRO_TEXTS:
            lookup_lang = "uk"
        welcome_text = SIMPLE_INTRO_TEXTS.get(lookup_lang, SIMPLE_INTRO_TEXTS["uk"])
        kb = InlineKeyboardMarkup(row_width=2)
        _dl = {"uk": "📄 Документи", "en": "📄 Documents", "de": "📄 Dokumente", "pl": "📄 Dokumenty", "tr": "📄 Belgeler", "ar": "📄 المستندات"}.get(lookup_lang, "📄 Документи")
        _tl_btn = {"uk": "📅 Знайти термін", "en": "📅 Find appointment", "de": "📅 Termin finden", "pl": "📅 Znajdź termin", "tr": "📅 Randevu bul", "ar": "📅 حجز موعد"}.get(lookup_lang, "📅 Знайти термін")
        kb.row(InlineKeyboardButton(_dl, callback_data="start_documents"), InlineKeyboardButton(_tl_btn, callback_data="start_termin"))
        try:
            await callback_query.message.edit_text(welcome_text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass  # edit_text may fail if message hasn't changed — safe to ignore
        return True

    elif action == 'accept':
        # Legacy: old cached GDPR screen might still send this — treat as consent + go to menu
        db = get_db()
        db.set_gdpr_consent(user_id, True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await _show_main_menu(callback_query.message, lang)
        return True

    elif action == 'decline':
        # Legacy: show short decline message (no nested navigation)
        _decline = {
            "uk": "Для використання бота необхідна згода на обробку даних. Натисніть /start щоб почати знову.",
            "en": "Consent is required to use the bot. Press /start to start again.",
            "de": "Zur Nutzung des Bots ist eine Einwilligung erforderlich. Drücken Sie /start, um neu zu beginnen.",
            "pl": "Do korzystania z bota wymagana jest zgoda. Naciśnij /start, aby zacząć od nowa.",
            "tr": "Botu kullanmak için onay gereklidir. Yeniden başlamak için /start basın.",
            "ar": "مطلوب الموافقة لاستخدام البوت. اضغط /start للبدء من جديد.",
        }
        _lk = "uk" if lang in ("ua", "uk") else lang
        await callback_query.message.edit_text(
            _decline.get(_lk, _decline.get("en", _decline["uk"])),
            parse_mode="HTML"
        )
        return True


# ============================================================================
# COUNTRY SELECTION
# ============================================================================

_COUNTRY_SELECT_TEXTS = {
    "uk": "🌍 <b>Оберіть країну</b>\n\nДля якої країни вам потрібна допомога?",
    "ua": "🌍 <b>Оберіть країну</b>\n\nДля якої країни вам потрібна допомога?",
    "en": "🌍 <b>Select country</b>\n\nFor which country do you need help?",
    "de": "🌍 <b>Land auswählen</b>\n\nFür welches Land benötigen Sie Hilfe?",
    "pl": "🌍 <b>Wybierz kraj</b>\n\nDla jakiego kraju potrzebujesz pomocy?",
    "tr": "🌍 <b>Ülke seçin</b>\n\nHangi ülke için yardıma ihtiyacınız var?",
    "ar": "🌍 <b>اختر الدولة</b>\n\nلأي دولة تحتاج إلى مساعدة؟",
}

_COMING_SOON_TEXTS = {
    "uk": "Незабаром",
    "ua": "Незабаром",
    "en": "Coming soon",
    "de": "Demnächst",
    "pl": "Wkrótce",
    "tr": "Yakında",
    "ar": "قريباً",
}


async def show_country_selection(message: types.Message, lang: str):
    """Show country selection screen (Germany active, others coming soon)."""
    text = _COUNTRY_SELECT_TEXTS.get(lang, _COUNTRY_SELECT_TEXTS["en"])
    soon = _COMING_SOON_TEXTS.get(lang, _COMING_SOON_TEXTS["en"])

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🇩🇪 Deutschland / Germany", callback_data="select_country_DE"),
        InlineKeyboardButton(f"🇪🇸 España / Spain — {soon}", callback_data="country_soon"),
        InlineKeyboardButton(f"🇫🇷 France — {soon}", callback_data="country_soon"),
        InlineKeyboardButton(f"🇳🇱 Nederland — {soon}", callback_data="country_soon"),
        InlineKeyboardButton(_nav_back_text(lang), callback_data="back_to_main_menu"),
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def handle_country_selection(callback_query: types.CallbackQuery):
    """Handle country button press."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)

    country_code = callback_query.data.replace("select_country_", "")  # e.g. "DE"
    db = get_db()
    db.set_user_country(user_id, country_code)

    logger.info("COUNTRY_SELECTED | user=%s country=%s", user_id, country_code)

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    await _show_main_menu(callback_query.message, lang)


async def handle_country_soon(callback_query: types.CallbackQuery):
    """Notify user that this country is not yet available."""
    lang = get_user_lang(callback_query.from_user.id)
    _msgs = {
        "uk": "Цей розділ ще в розробці. Незабаром!",
        "ua": "Цей розділ ще в розробці. Незабаром!",
        "en": "This country is not available yet. Coming soon!",
        "de": "Dieser Bereich ist noch in Entwicklung. Demnächst!",
        "pl": "Ta sekcja jest jeszcze w trakcie budowy. Wkrótce!",
        "tr": "Bu bölüm henüz geliştirme aşamasında. Yakında!",
        "ar": "هذا القسم لا يزال قيد التطوير. قريباً!",
    }
    await callback_query.answer(_msgs.get(lang, _msgs["en"]), show_alert=True)


# ============================================================================
# /reset — developer / testing utility
# ============================================================================

async def cmd_reset(message: types.Message):
    """Mark all pending/processing/paid orders for this user as FAILED.
    Useful for testing so that /start no longer shows 'unfinished order' prompts.
    Does NOT affect other users or orders already in terminal states.
    """
    from backend.database import get_db
    user = message.from_user
    lang = get_user_lang(user.id) if callable(get_user_lang) else "en"
    if lang == "ua":
        lang = "uk"

    db = get_db()
    updated = db.reset_user_orders(user.id)

    _msgs = {
        "uk": f"✅ Ваші замовлення очищено ({updated} шт.). Можете почати заново.",
        "en": f"✅ Your orders have been reset ({updated}). You can start again.",
        "de": f"✅ Ihre Bestellungen wurden zurückgesetzt ({updated}).",
        "pl": f"✅ Twoje zamówienia zostały zresetowane ({updated}). Możesz zacząć od nowa.",
        "tr": f"✅ Siparişleriniz sıfırlandı ({updated}). Yeniden başlayabilirsiniz.",
        "ar": f"✅ تم إعادة تعيين طلباتك ({updated}). يمكنك البدء من جديد.",
    }
    await message.answer(_msgs.get(lang, _msgs["en"]))


async def cmd_dev_new(message: types.Message, state: FSMContext):
    """
    /dev_new — admin-only command.
    Simulates a brand-new user session for the caller only.
    Clears FSM state, in-memory questionnaire data, drafts, pending orders,
    and saved language, then immediately shows the language-selection screen.
    Does NOT touch paid orders, Termin entitlements, or other users.
    """
    user_id = message.from_user.id
    _admin_ids = getattr(config, "ADMIN_IDS", []) or []
    if user_id not in _admin_ids:
        return  # silently ignore non-admins

    # 1. Clear FSM state
    await state.finish()

    # 2. Clear in-memory questionnaire data (_PENDING_PREVIEWS) for this user
    try:
        from handlers.docs_new import _PENDING_PREVIEWS
        _keys_to_drop = [k for k in _PENDING_PREVIEWS if k[0] == user_id]
        for _k in _keys_to_drop:
            del _PENDING_PREVIEWS[_k]
    except Exception as _e:
        logger.warning("cmd_dev_new: _PENDING_PREVIEWS clear failed: %s", _e)

    # 3. Reset pending/processing/paid orders to 'failed' (cancels recovery screens)
    try:
        get_db().reset_user_orders(user_id)
    except Exception as _e:
        logger.warning("cmd_dev_new: reset_user_orders failed: %s", _e)

    # 4. Delete all active drafts for this user
    try:
        from backend.drafts import DraftsManager as _DraftsManager
        _dm = _DraftsManager(config.DB_PATH)
        _dm.delete_user_drafts(user_id)
    except Exception as _e:
        logger.warning("cmd_dev_new: delete_user_drafts failed: %s", _e)

    # 5. Clear saved language so language-selection is shown as first screen
    try:
        _db2 = get_db()
        _db2.set_user_lang(user_id, "")
    except Exception as _e:
        logger.warning("cmd_dev_new: set_user_lang clear failed: %s", _e)

    # 6. Suppress admin system alerts while in client-test mode
    config.enter_dev_client_mode(user_id)

    logger.info("DEV_NEW_DONE | user_id=%s | dev_client_mode=ON", user_id)

    # 7. Show the same screen a brand-new user sees on first launch
    await show_language_selection(message)


async def cmd_dev_admin(message: types.Message):
    """
    /dev_admin — admin-only command.
    Exits dev-client mode: restores normal admin alerts for this user_id.
    Safe to call even if not in dev-client mode.
    """
    user_id = message.from_user.id
    _admin_ids = getattr(config, "ADMIN_IDS", []) or []
    if user_id not in _admin_ids:
        return
    config.exit_dev_client_mode(user_id)
    logger.info("DEV_ADMIN_MODE_RESTORED | user_id=%s", user_id)
    await message.answer("✅ Admin mode restored. System alerts are active again.")


# ============================================================================
# REGISTER HANDLERS
# ============================================================================

def register_handlers(dp: Dispatcher):
    """DEPRECATED — not called anywhere. Use register_start_handlers() instead."""
    dp.register_message_handler(cmd_start, commands=['start'], state='*')
    dp.register_message_handler(cmd_reset, commands=['reset'], state='*')
    dp.register_callback_query_handler(
        handle_language_selection, 
        lambda c: c.data.startswith('lang_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_set_language_from_menu,
        lambda c: c.data.startswith('set_lang_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_gdpr_callback,
        lambda c: c.data.startswith('gdpr_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_country_selection,
        lambda c: c.data and c.data.startswith('select_country_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_country_soon,
        lambda c: c.data and c.data == 'country_soon',
        state='*'
    )


async def handle_resume_draft(callback_query: types.CallbackQuery, state: FSMContext):
    """Resume an incomplete form from a saved draft."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    try:
        import config as _cfg
        from backend.drafts import DraftsManager as _DraftsManager
        _drafts_mgr = _DraftsManager(getattr(_cfg, "DB_PATH", "bot_database.db"))
        draft_id = int(callback_query.data.split("_")[-1])
        draft = _drafts_mgr.get_draft_by_id(draft_id, user_id)
        if not draft:
            await callback_query.message.answer("⚠️ Draft not found. Please start over.")
            await show_language_selection(callback_query.message)
            return
        # Re-open the WebApp form with pre-filled data from draft
        doc_type = draft.get("doc_type", "")
        lang = (draft.get("lang") or "en").strip().lower()
        from handlers.docs_new import process_doc_choice_internal
        await process_doc_choice_internal(callback_query.message, doc_type, lang, prefill=draft.get("answers", {}))
        logger.info("DRAFT_RESUMED | user_id=%s draft_id=%s doc=%s", user_id, draft_id, doc_type)
    except Exception as _e:
        logger.warning("DRAFT_RESUME_FAILED | user_id=%s error=%s", user_id, _e)
        await show_language_selection(callback_query.message)


async def handle_discard_draft(callback_query: types.CallbackQuery, state: FSMContext):
    """Discard the saved draft and show main menu."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    try:
        import config as _cfg
        from backend.drafts import DraftsManager as _DraftsManager
        _drafts_mgr = _DraftsManager(getattr(_cfg, "DB_PATH", "bot_database.db"))
        _drafts_mgr.delete_user_drafts(user_id)
        logger.info("DRAFT_DISCARDED | user_id=%s", user_id)
    except Exception as _e:
        logger.warning("DRAFT_DISCARD_FAILED | user_id=%s error=%s", user_id, _e)
    await show_language_selection(callback_query.message)


async def cmd_refer(message: types.Message):
    """
    /refer — show the user's personal referral link and progress.
    Every 2 friends who pay → 1 free document.
    """
    user_id = message.from_user.id
    db = get_db()
    lang = get_user_lang(user_id)
    _l = lang if lang in ("uk", "ua", "en", "de", "pl", "tr", "ar") else "en"
    if _l == "ua":
        _l = "uk"

    try:
        import config as _cfg
        _bot_username = getattr(_cfg, "BOT_USERNAME", None) or "DE_PDF_Assistant_bot"
    except Exception:
        _bot_username = "DE_PDF_Assistant_bot"

    referral_code = db.get_or_create_referral_code(user_id)
    stats = db.get_referral_stats(user_id)
    count   = stats["count"]
    credits = stats["credits"]
    link    = f"https://t.me/{_bot_username}?start={referral_code}"

    # Progress bar: 0–2 filled circles
    _FILLED   = "🟢"
    _EMPTY    = "⚪"
    progress_in_cycle = count % 2
    bar = _FILLED * progress_in_cycle + _EMPTY * (2 - progress_in_cycle)

    _texts = {
        "uk": (
            f"🎁 <b>Запроси друзів — отримай документ безкоштовно</b>\n\n"
            f"Твоє посилання:\n<code>{link}</code>\n\n"
            f"{bar}  {progress_in_cycle}/2 до наступного безкоштовного документа\n"
            f"👥 Всього запрошено: <b>{count}</b>\n"
            f"🎫 Безкоштовних документів: <b>{credits}</b>\n\n"
            f"Поділись з другом — і обоє виграєте.\n"
            f"Після 2 оплачених реєстрацій ти отримуєш 1 безкоштовний документ."
        ),
        "en": (
            f"🎁 <b>Invite friends — get a free document</b>\n\n"
            f"Your link:\n<code>{link}</code>\n\n"
            f"{bar}  {progress_in_cycle}/2 to your next free document\n"
            f"👥 Total invited: <b>{count}</b>\n"
            f"🎫 Free document credits: <b>{credits}</b>\n\n"
            f"Share with a friend — you both benefit.\n"
            f"After 2 friends pay → you get 1 free document."
        ),
        "de": (
            f"🎁 <b>Freunde einladen — kostenloses Dokument erhalten</b>\n\n"
            f"Dein Link:\n<code>{link}</code>\n\n"
            f"{bar}  {progress_in_cycle}/2 bis zum nächsten kostenlosen Dokument\n"
            f"👥 Insgesamt eingeladen: <b>{count}</b>\n"
            f"🎫 Kostenlose Dokumente: <b>{credits}</b>\n\n"
            f"Teile mit einem Freund — beide profitieren.\n"
            f"Nach 2 bezahlten Registrierungen → 1 kostenloses Dokument."
        ),
        "pl": (
            f"🎁 <b>Zaproś znajomych — dostań dokument za darmo</b>\n\n"
            f"Twój link:\n<code>{link}</code>\n\n"
            f"{bar}  {progress_in_cycle}/2 do następnego darmowego dokumentu\n"
            f"👥 Łącznie zaproszonych: <b>{count}</b>\n"
            f"🎫 Darmowe dokumenty: <b>{credits}</b>\n\n"
            f"Podziel się ze znajomym — oboje zyskacie.\n"
            f"Po 2 opłaconych rejestracjach → 1 darmowy dokument."
        ),
        "tr": (
            f"🎁 <b>Arkadaşlarını davet et — ücretsiz belge kazan</b>\n\n"
            f"Bağlantın:\n<code>{link}</code>\n\n"
            f"{bar}  {progress_in_cycle}/2 sonraki ücretsiz belgeye\n"
            f"👥 Toplam davet edilen: <b>{count}</b>\n"
            f"🎫 Ücretsiz belgeler: <b>{credits}</b>\n\n"
            f"Arkadaşınla paylaş — ikiniz de kazanırsınız.\n"
            f"2 ücretli kayıt sonrası → 1 ücretsiz belge."
        ),
        "ar": (
            f"🎁 <b>ادعُ أصدقاءك — احصل على مستند مجاني</b>\n\n"
            f"رابطك:\n<code>{link}</code>\n\n"
            f"{bar}  {progress_in_cycle}/2 للوصول إلى المستند المجاني التالي\n"
            f"👥 إجمالي المدعوين: <b>{count}</b>\n"
            f"🎫 مستندات مجانية: <b>{credits}</b>\n\n"
            f"شارك مع صديق — كلاكما يستفيد.\n"
            f"بعد تسجيل 2 صديق مدفوع → مستند مجاني واحد."
        ),
    }

    _share_btn = {
        "uk": "📤 Поділитись посиланням",
        "en": "📤 Share my link",
        "de": "📤 Link teilen",
        "pl": "📤 Udostępnij link",
        "tr": "📤 Bağlantıyı paylaş",
        "ar": "📤 مشاركة الرابط",
    }

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        _share_btn.get(_l, _share_btn["en"]),
        switch_inline_query=link,
    ))

    await message.answer(
        _texts.get(_l, _texts["en"]),
        parse_mode="HTML",
        reply_markup=kb,
    )
    logger.info("REFER_CMD | user=%s code=%s count=%s credits=%s", user_id, referral_code, count, credits)


async def cmd_my_docs(message: types.Message):
    """
    /my_docs — show the user's last paid orders with a "Send again" button each.
    Allows users to recover documents without contacting support.
    """
    user_id = message.from_user.id
    db = get_db()
    lang = get_user_lang(user_id)
    _l = lang if lang in ("uk", "ua", "en", "de", "pl", "tr", "ar") else "en"
    if _l == "ua":
        _l = "uk"

    from backend.translations import ui as _ui
    await message.bot.send_chat_action(message.chat.id, "typing")

    _STATUS_LABELS = {
        "sent":       {"ua": "✅ доставлено",    "en": "✅ delivered",   "de": "✅ geliefert",   "pl": "✅ dostarczono",  "tr": "✅ teslim edildi", "ar": "✅ تم التسليم"},
        "downloaded": {"ua": "✅ отримано",       "en": "✅ received",    "de": "✅ erhalten",     "pl": "✅ odebrano",     "tr": "✅ alındı",        "ar": "✅ مُستلَم"},
        "paid":       {"ua": "💳 оплачено",       "en": "💳 paid",        "de": "💳 bezahlt",      "pl": "💳 opłacono",     "tr": "💳 ödendi",        "ar": "💳 مدفوع"},
        "processing": {"ua": "⏳ обробляється",   "en": "⏳ processing",  "de": "⏳ verarbeitung", "pl": "⏳ przetwarzanie","tr": "⏳ işleniyor",      "ar": "⏳ قيد المعالجة"},
        "failed":     {"ua": "❌ помилка",        "en": "❌ failed",      "de": "❌ fehler",       "pl": "❌ błąd",         "tr": "❌ hata",           "ar": "❌ فشل"},
    }

    # Load last 7 orders regardless of status — filter to paid+
    _PAID_STATUSES = {"sent", "downloaded", "paid", "processing"}
    all_orders = db.get_user_orders(int(user_id), limit=20)
    orders = [o for o in all_orders if (o.get("status") or "").lower() in _PAID_STATUSES][:7]

    # Normalise lang for translation lookup (SUPPORTED_LANGUAGES uses 'ua' not 'uk')
    _tl = "ua" if _l in ("uk", "ua") else _l

    if not orders:
        await message.answer(_ui("no_documents", _tl))
        return

    lines = [_ui("my_documents_header", _tl), ""]
    kb = InlineKeyboardMarkup(row_width=1)

    for o in orders:
        _otype     = (o.get("doc_type") or "document").replace("_", " ").title()
        _amount    = o.get("amount") or o.get("price")
        _price_str = f"€{float(_amount):.2f}" if _amount else ""
        _dt_raw    = o.get("paid_at") or o.get("created_at") or ""
        _dt_str    = str(_dt_raw)[:10] if _dt_raw else "—"
        _st        = (o.get("status") or "").lower()
        _st_label  = _STATUS_LABELS.get(_st, {}).get(_tl, _st)
        _oid       = o.get("id") or o.get("order_id")

        line = f"• <b>{_otype}</b>  {_price_str}  <i>{_dt_str}</i>  {_st_label}"
        lines.append(line)

        if _oid and _st in {"sent", "downloaded", "paid"}:
            kb.add(InlineKeyboardButton(
                f"{_ui('send_again', _tl)} — {_otype}",
                callback_data=f"resend_doc_{_oid}",
            ))

    kb.add(InlineKeyboardButton(
        _ui("main_menu_btn", _tl),
        callback_data="back_to_main_menu",
    ))

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb,
    )
    logger.info("MY_DOCS | user=%s orders=%s", user_id, len(orders))


# ============================================================================
# /my — active monitoring status shortcut
# ============================================================================

async def cmd_my(message: types.Message):
    """/my — instantly show active Termin monitoring or main menu if none."""
    user_id = message.from_user.id
    db = get_db()
    lang = get_user_lang(user_id)
    _l = "uk" if lang in ("ua", "uk") else (lang if lang in ("en", "de", "pl", "tr", "ar") else "en")

    try:
        from backend.termin_db import (
            is_termin_entitled as _ite_my,
            get_entitlement as _ge_my,
        )
        _ent = _ge_my(str(user_id))
        if _ent and _ent.get("active") == 1:
            _entitled = _ite_my(str(user_id))
            await _show_termin_active_screen(message, user_id, _l, _ent, expired=not _entitled)
            return
    except Exception as _my_err:
        logger.exception("CMD_MY_TERMIN_ERROR | user=%s", user_id)

    # No active monitoring — show a helpful "nothing active" message with main menu button
    _NO_ACTIVE = {
        "uk": "ℹ️ Активного моніторингу немає.\n\nЗапустіть пошук Termin через головне меню.",
        "en": "ℹ️ No active monitoring.\n\nStart a Termin search from the main menu.",
        "de": "ℹ️ Keine aktive Überwachung.\n\nStarten Sie eine Terminsuche über das Hauptmenü.",
        "pl": "ℹ️ Brak aktywnego monitorowania.\n\nUruchom wyszukiwanie Termin z menu głównego.",
        "tr": "ℹ️ Aktif takip yok.\n\nAna menüden Termin araması başlatın.",
        "ar": "ℹ️ لا توجد مراقبة نشطة.\n\nابدأ البحث عن Termin من القائمة الرئيسية.",
    }
    _FIND_BTN = {
        "uk": "📅 Знайти Termin", "en": "📅 Find Termin", "de": "📅 Termin suchen",
        "pl": "📅 Szukaj Termin", "tr": "📅 Termin bul", "ar": "📅 ابحث عن Termin",
    }
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(_FIND_BTN.get(_l, "📅 Find Termin"), callback_data="find_termin"))
    await message.answer(_NO_ACTIVE.get(_l, _NO_ACTIVE["en"]), parse_mode="HTML", reply_markup=kb)


# ============================================================================
# GDPR — /delete_my_data
# ============================================================================

_GDPR_CONFIRM_TEXT = {
    "uk": (
        "⚠️ <b>Видалення даних (GDPR Art. 17)</b>\n\n"
        "Буде безповоротно видалено:\n"
        "• Всі ваші персональні дані з бази\n"
        "• Згенеровані PDF-файли\n"
        "• Ваш профіль та замовлення\n\n"
        "<b>Це дію не можна скасувати.</b>\n\nПродовжити?"
    ),
    "en": (
        "⚠️ <b>Data Deletion (GDPR Art. 17)</b>\n\n"
        "The following will be permanently deleted:\n"
        "• All your personal data from the database\n"
        "• Generated PDF files\n"
        "• Your profile and orders\n\n"
        "<b>This action cannot be undone.</b>\n\nContinue?"
    ),
    "de": (
        "⚠️ <b>Datenlöschung (DSGVO Art. 17)</b>\n\n"
        "Folgendes wird dauerhaft gelöscht:\n"
        "• Alle Ihre persönlichen Daten aus der Datenbank\n"
        "• Generierte PDF-Dateien\n"
        "• Ihr Profil und Bestellungen\n\n"
        "<b>Diese Aktion kann nicht rückgängig gemacht werden.</b>\n\nFortfahren?"
    ),
    "pl": (
        "⚠️ <b>Usunięcie danych (RODO Art. 17)</b>\n\n"
        "Zostanie trwale usunięte:\n"
        "• Wszystkie Twoje dane osobowe z bazy danych\n"
        "• Wygenerowane pliki PDF\n"
        "• Twój profil i zamówienia\n\n"
        "<b>Tej czynności nie można cofnąć.</b>\n\nKontynuować?"
    ),
    "tr": (
        "⚠️ <b>Veri Silme (GDPR Md. 17)</b>\n\n"
        "Kalıcı olarak silinecekler:\n"
        "• Veritabanındaki tüm kişisel verileriniz\n"
        "• Oluşturulan PDF dosyaları\n"
        "• Profiliniz ve siparişleriniz\n\n"
        "<b>Bu işlem geri alınamaz.</b>\n\nDevam edilsin mi?"
    ),
    "ar": (
        "⚠️ <b>حذف البيانات (المادة 17 من GDPR)</b>\n\n"
        "سيتم حذف ما يلي بشكل دائم:\n"
        "• جميع بياناتك الشخصية من قاعدة البيانات\n"
        "• ملفات PDF المُنشأة\n"
        "• ملفك الشخصي والطلبات\n\n"
        "<b>لا يمكن التراجع عن هذا الإجراء.</b>\n\nمتابعة؟"
    ),
}

_GDPR_BTN_CONFIRM = {"uk": "🗑 Так, видалити все", "en": "🗑 Yes, delete everything", "de": "🗑 Ja, alles löschen", "pl": "🗑 Tak, usuń wszystko", "tr": "🗑 Evet, her şeyi sil", "ar": "🗑 نعم، احذف كل شيء"}
_GDPR_BTN_CANCEL  = {"uk": "← Скасувати", "en": "← Cancel", "de": "← Abbrechen", "pl": "← Anuluj", "tr": "← İptal", "ar": "← إلغاء"}


async def cmd_delete_my_data(message: types.Message):
    """Step 1 — show confirmation screen."""
    user_id = message.from_user.id
    lang = (get_user_lang(user_id) or "en").strip().lower()
    _l = "uk" if lang in ("uk", "ua") else (lang if lang in ("en", "de", "pl", "tr", "ar") else "en")

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_GDPR_BTN_CONFIRM.get(_l, _GDPR_BTN_CONFIRM["en"]), callback_data="gdpr_delete_confirm"),
        InlineKeyboardButton(_GDPR_BTN_CANCEL.get(_l, _GDPR_BTN_CANCEL["en"]),   callback_data="back_to_main_menu"),
    )
    await message.answer(_GDPR_CONFIRM_TEXT.get(_l, _GDPR_CONFIRM_TEXT["en"]), parse_mode="HTML", reply_markup=kb)


async def handle_gdpr_delete_confirm(callback_query: types.CallbackQuery):
    """Step 2 — execute shredder and report result."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = (get_user_lang(user_id) or "en").strip().lower()
    _l = "uk" if lang in ("uk", "ua") else (lang if lang in ("en", "de", "pl", "tr", "ar") else "en")

    try:
        from backend.gdpr_shredder import shred_user_data
        import os as _os
        _admin_ids = [int(x.strip()) for x in _os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
        _bot = callback_query.bot
        _db = get_db()
        result = await shred_user_data(
            user_id=user_id,
            db=_db,
            notify_admin=bool(_admin_ids),
            admin_ids=_admin_ids,
            bot=_bot,
        )
        await callback_query.message.answer(result.format_message(_l), parse_mode="HTML")
    except Exception as _e:
        logger.error("GDPR_SHREDDER_ERROR: user=%s err=%s", user_id, _e)
        _err_text = {"uk": "❌ Помилка видалення. Зверніться до підтримки.", "en": "❌ Deletion error. Please contact support.", "de": "❌ Fehler beim Löschen. Bitte wenden Sie sich an den Support."}
        await callback_query.message.answer(_err_text.get(_l, _err_text["en"]))


# ============================================================================
# /help command
# ============================================================================

_HELP_TEXT = {
    "uk": (
        "📖 <b>Довідка</b>\n\n"
        "🤖 Бот допомагає заповнити офіційні документи для Німеччини.\n\n"
        "<b>Команди:</b>\n"
        "/start — головне меню\n"
        "/my_docs — мої замовлення\n"
        "/delete_my_data — видалити мої дані (GDPR)\n"
        "/help — ця довідка\n\n"
        "<b>Як це працює:</b>\n"
        "1. Оберіть документ\n"
        "2. Заповніть форму\n"
        "3. Оплатіть та отримайте PDF\n\n"
        "❓ Питання? Напишіть нам через головне меню."
    ),
    "en": (
        "📖 <b>Help</b>\n\n"
        "🤖 This bot helps you fill out official German documents.\n\n"
        "<b>Commands:</b>\n"
        "/start — main menu\n"
        "/my_docs — my orders\n"
        "/delete_my_data — delete my data (GDPR)\n"
        "/help — this help\n\n"
        "<b>How it works:</b>\n"
        "1. Choose a document\n"
        "2. Fill out the form\n"
        "3. Pay and receive your PDF\n\n"
        "❓ Questions? Write to us via the main menu."
    ),
    "de": (
        "📖 <b>Hilfe</b>\n\n"
        "🤖 Dieser Bot hilft Ihnen, offizielle deutsche Dokumente auszufüllen.\n\n"
        "<b>Befehle:</b>\n"
        "/start — Hauptmenü\n"
        "/my_docs — Meine Bestellungen\n"
        "/delete_my_data — Meine Daten löschen (DSGVO)\n"
        "/help — Diese Hilfe\n\n"
        "<b>So funktioniert es:</b>\n"
        "1. Dokument auswählen\n"
        "2. Formular ausfüllen\n"
        "3. Bezahlen und PDF erhalten\n\n"
        "❓ Fragen? Schreiben Sie uns über das Hauptmenü."
    ),
    "pl": (
        "📖 <b>Pomoc</b>\n\n"
        "🤖 Ten bot pomaga wypełniać oficjalne dokumenty niemieckie.\n\n"
        "<b>Komendy:</b>\n"
        "/start — menu główne\n"
        "/my_docs — moje zamówienia\n"
        "/delete_my_data — usuń moje dane (RODO)\n"
        "/help — ta pomoc\n\n"
        "<b>Jak to działa:</b>\n"
        "1. Wybierz dokument\n"
        "2. Wypełnij formularz\n"
        "3. Zapłać i odbierz PDF\n\n"
        "❓ Pytania? Napisz do nas przez menu główne."
    ),
    "tr": (
        "📖 <b>Yardım</b>\n\n"
        "🤖 Bu bot, Alman resmi belgelerini doldurmanıza yardımcı olur.\n\n"
        "<b>Komutlar:</b>\n"
        "/start — ana menü\n"
        "/my_docs — siparişlerim\n"
        "/delete_my_data — verilerimi sil (GDPR)\n"
        "/help — bu yardım\n\n"
        "<b>Nasıl çalışır:</b>\n"
        "1. Belge seçin\n"
        "2. Formu doldurun\n"
        "3. Ödeme yapın ve PDF'i alın\n\n"
        "❓ Sorularınız mı var? Ana menüden bize yazın."
    ),
    "ar": (
        "📖 <b>المساعدة</b>\n\n"
        "🤖 يساعدك هذا البوت في ملء الوثائق الرسمية الألمانية.\n\n"
        "<b>الأوامر:</b>\n"
        "/start — القائمة الرئيسية\n"
        "/my_docs — طلباتي\n"
        "/delete_my_data — حذف بياناتي (GDPR)\n"
        "/help — هذه المساعدة\n\n"
        "<b>كيف يعمل:</b>\n"
        "1. اختر وثيقة\n"
        "2. املأ النموذج\n"
        "3. ادفع واستلم ملف PDF\n\n"
        "❓ أسئلة؟ راسلنا عبر القائمة الرئيسية."
    ),
}


async def cmd_help(message: types.Message):
    """Show help — button-driven, no command list in body."""
    user_id = message.from_user.id
    lang = (get_user_lang(user_id) or "en").strip().lower()
    _l = "uk" if lang in ("uk", "ua") else (lang if lang in ("en", "de", "pl", "tr", "ar") else "en")
    await _send_help_screen(message, _l, edit=False)


async def _send_help_screen(target, lang: str, edit: bool = False):
    """Reusable help screen used by /help command and Settings → Help button."""
    _HELP_BODY = {
        "uk": (
            "📖 <b>Як працює бот</b>\n\n"
            "1. Оберіть документ\n"
            "2. Заповніть форму (WebApp)\n"
            "3. Оплатіть — отримайте готовий PDF\n\n"
            "Або запустіть моніторинг Termin — бот знайде запис і сповістить миттєво."
        ),
        "en": (
            "📖 <b>How the bot works</b>\n\n"
            "1. Choose a document\n"
            "2. Fill the form (WebApp)\n"
            "3. Pay — receive a ready PDF\n\n"
            "Or start Termin monitoring — the bot finds a slot and notifies you instantly."
        ),
        "de": (
            "📖 <b>So funktioniert der Bot</b>\n\n"
            "1. Dokument auswählen\n"
            "2. Formular ausfüllen (WebApp)\n"
            "3. Bezahlen — fertiges PDF erhalten\n\n"
            "Oder starten Sie die Terminüberwachung — der Bot findet einen Termin und benachrichtigt Sie sofort."
        ),
        "pl": (
            "📖 <b>Jak działa bot</b>\n\n"
            "1. Wybierz dokument\n"
            "2. Wypełnij formularz (WebApp)\n"
            "3. Zapłać — otrzymaj gotowy PDF\n\n"
            "Lub uruchom monitoring Termin — bot znajdzie termin i powiadomi cię natychmiast."
        ),
        "tr": (
            "📖 <b>Bot nasıl çalışır</b>\n\n"
            "1. Belge seçin\n"
            "2. Formu doldurun (WebApp)\n"
            "3. Ödeme yapın — hazır PDF alın\n\n"
            "Ya da Termin takibini başlatın — bot randevu bulup anında bildirir."
        ),
        "ar": (
            "📖 <b>كيف يعمل البوت</b>\n\n"
            "1. اختر وثيقة\n"
            "2. املأ النموذج (WebApp)\n"
            "3. ادفع — استلم ملف PDF جاهزاً\n\n"
            "أو ابدأ مراقبة المواعيد — يجد البوت موعداً ويُعلمك فوراً."
        ),
    }
    _BTN_DOC   = {"uk": "📄 Підготувати документ", "en": "📄 Create document", "de": "📄 Dokument erstellen", "pl": "📄 Utwórz dokument", "tr": "📄 Belge oluştur", "ar": "📄 إنشاء وثيقة"}
    _BTN_TERM  = {"uk": "📅 Знайти Termin",         "en": "📅 Find Termin",     "de": "📅 Termin finden",    "pl": "📅 Znajdź Termin",  "tr": "📅 Termin Bul",   "ar": "📅 إيجاد موعد"}
    _BTN_BACK  = {"uk": "← Головне меню",            "en": "← Main menu",       "de": "← Hauptmenü",         "pl": "← Menu główne",     "tr": "← Ana menü",      "ar": "← القائمة الرئيسية"}

    _l = lang if lang in _HELP_BODY else "en"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_BTN_DOC.get(_l, _BTN_DOC["en"]),  callback_data="create_doc"),
        InlineKeyboardButton(_BTN_TERM.get(_l, _BTN_TERM["en"]), callback_data="find_termin"),
        InlineKeyboardButton(_BTN_BACK.get(_l, _BTN_BACK["en"]), callback_data="back_to_main_menu"),
    )
    text = _HELP_BODY.get(_l, _HELP_BODY["en"])
    if edit and hasattr(target, "edit_text"):
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        msg = target.message if hasattr(target, "message") else target
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


# ============================================================================
# SETTINGS menu — GDPR + Help, accessible from main menu ⚙️
# ============================================================================

_SETTINGS_TEXT = {
    "uk": "⚙️ <b>Налаштування</b>",
    "en": "⚙️ <b>Settings</b>",
    "de": "⚙️ <b>Einstellungen</b>",
    "pl": "⚙️ <b>Ustawienia</b>",
    "tr": "⚙️ <b>Ayarlar</b>",
    "ar": "⚙️ <b>الإعدادات</b>",
}
_BTN_HELP_INLINE  = {"uk": "📖 Як користуватися", "en": "📖 How to use",     "de": "📖 Anleitung",          "pl": "📖 Jak używać",     "tr": "📖 Nasıl kullanılır", "ar": "📖 كيفية الاستخدام"}
_BTN_DELETE_DATA  = {"uk": "🗑 Видалити мої дані", "en": "🗑 Delete my data", "de": "🗑 Meine Daten löschen", "pl": "🗑 Usuń moje dane", "tr": "🗑 Verilerimi sil",    "ar": "🗑 حذف بياناتي"}
_BTN_BACK_MENU    = {"uk": "← Назад",              "en": "← Back",            "de": "← Zurück",              "pl": "← Wstecz",          "tr": "← Geri",              "ar": "← رجوع"}


_BTN_SUPPORT_SETTINGS = {
    "uk": "💬 Підтримка",
    "en": "💬 Support",
    "de": "💬 Support",
    "pl": "💬 Wsparcie",
    "tr": "💬 Destek",
    "ar": "💬 الدعم",
}


async def handle_settings(callback_query: types.CallbackQuery):
    """Show Settings submenu — Help + Support + GDPR Delete."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = (get_user_lang(user_id) or "en").strip().lower()
    _l = "uk" if lang in ("uk", "ua") else (lang if lang in ("en", "de", "pl", "tr", "ar") else "en")

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_BTN_SUPPORT_SETTINGS.get(_l, _BTN_SUPPORT_SETTINGS["en"]), callback_data="ai_support"),
        InlineKeyboardButton(_BTN_HELP_INLINE.get(_l, _BTN_HELP_INLINE["en"]),  callback_data="settings_help"),
        InlineKeyboardButton(_BTN_DELETE_DATA.get(_l, _BTN_DELETE_DATA["en"]),  callback_data="gdpr_delete_confirm_prompt"),
        InlineKeyboardButton(_BTN_BACK_MENU.get(_l, _BTN_BACK_MENU["en"]),      callback_data="back_to_main_menu"),
    )
    try:
        await callback_query.message.edit_text(
            _SETTINGS_TEXT.get(_l, _SETTINGS_TEXT["en"]), parse_mode="HTML", reply_markup=kb
        )
    except Exception:
        await callback_query.message.answer(
            _SETTINGS_TEXT.get(_l, _SETTINGS_TEXT["en"]), parse_mode="HTML", reply_markup=kb
        )


async def handle_settings_help(callback_query: types.CallbackQuery):
    """Show help from Settings menu."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = (get_user_lang(user_id) or "en").strip().lower()
    _l = "uk" if lang in ("uk", "ua") else (lang if lang in ("en", "de", "pl", "tr", "ar") else "en")
    await _send_help_screen(callback_query, _l, edit=True)


async def handle_gdpr_delete_confirm_prompt(callback_query: types.CallbackQuery):
    """Show GDPR delete confirmation screen (from Settings)."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = (get_user_lang(user_id) or "en").strip().lower()
    _l = "uk" if lang in ("uk", "ua") else (lang if lang in ("en", "de", "pl", "tr", "ar") else "en")

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(_GDPR_BTN_CONFIRM.get(_l, _GDPR_BTN_CONFIRM["en"]), callback_data="gdpr_delete_confirm"),
        InlineKeyboardButton(_BTN_BACK_MENU.get(_l, _BTN_BACK_MENU["en"]),        callback_data="settings_menu"),
    )
    try:
        await callback_query.message.edit_text(
            _GDPR_CONFIRM_TEXT.get(_l, _GDPR_CONFIRM_TEXT["en"]), parse_mode="HTML", reply_markup=kb
        )
    except Exception:
        await callback_query.message.answer(
            _GDPR_CONFIRM_TEXT.get(_l, _GDPR_CONFIRM_TEXT["en"]), parse_mode="HTML", reply_markup=kb
        )


async def _handle_language_btn(callback_query: types.CallbackQuery):
    """Open the language selection grid when user taps '🌐 Мова' in the main menu."""
    await callback_query.answer()
    await show_language_selection(callback_query.message)


async def _handle_noop(callback_query: types.CallbackQuery):
    """Silent no-op handler for divider/separator buttons in inline keyboards."""
    await callback_query.answer()


# ── Callback aliases for the new menu button names ───────────────────────────
# These map the new clean callback_data (create_doc, find_termin, my_docs, language)
# to the existing handler functions — zero business logic changes.

async def _alias_create_doc(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await _show_flat_doc_list(callback_query.message, lang)


async def handle_back_to_doc_categories(callback_query: types.CallbackQuery):
    """Back button from a category document list — returns to flat document list."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    await _show_flat_doc_list(callback_query.message, lang)


async def handle_docs_housing(callback_query: types.CallbackQuery):
    """User selected Housing & Registration category."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    await _show_category_documents(callback_query.message, "residence", lang)


async def handle_docs_financial(callback_query: types.CallbackQuery):
    """User selected Financial Documents category."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = get_user_lang(user_id)
    await _show_category_documents(callback_query.message, "financial", lang)


async def _alias_find_termin(callback_query: types.CallbackQuery):
    callback_query.data = "category_termin"
    await handle_category_selection(callback_query)


async def _alias_my_docs(callback_query: types.CallbackQuery):
    await handle_my_documents(callback_query)


def register_start_handlers(dp: Dispatcher):
    """Minimal registration for bot.py compatibility"""
    dp.register_message_handler(cmd_start,   commands=["start"],   state="*")
    dp.register_message_handler(cmd_my_docs, commands=["my_docs"], state="*")
    dp.register_message_handler(cmd_my,      commands=["my"],      state="*")
    # dp.register_message_handler(cmd_refer,  commands=["refer"], state="*")
    dp.register_message_handler(cmd_reset,   commands=["reset"],   state="*")
    dp.register_message_handler(cmd_help,    commands=["help"],    state="*")
    dp.register_message_handler(cmd_delete_my_data, commands=["delete_my_data"], state="*")
    dp.register_message_handler(cmd_dev_new,         commands=["dev_new"],        state="*")
    dp.register_message_handler(cmd_dev_admin,       commands=["dev_admin"],      state="*")
    dp.register_callback_query_handler(
        handle_language_selection,
        lambda c: c.data and c.data.startswith('lang_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_set_language_from_menu,
        lambda c: c.data and c.data.startswith('set_lang_'),
        state='*'
    )
    # Exact-match handlers MUST come before the startswith('gdpr_') catch-all
    # so aiogram v2 picks them up first.
    dp.register_callback_query_handler(
        handle_gdpr_confirmed,
        lambda c: c.data and c.data == 'gdpr_confirmed',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_gdpr_callback,
        lambda c: c.data and c.data.startswith('gdpr_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_start_documents,
        lambda c: c.data and c.data == 'start_documents',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_start_termin,
        lambda c: c.data and c.data == 'start_termin',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_welcome_continue,
        lambda c: c.data and c.data == 'welcome_continue',
        state='*'
    )
    # Register category selection handler - handles category_residence, category_family, etc.
    # CRITICAL: Use text filter for exact matches where possible, startswith for patterns
    dp.register_callback_query_handler(
        handle_category_selection,
        lambda c: c.data and c.data.startswith('category_'),
        state='*'
    )
    logger.info("✅ Registered handler for category_* callbacks")
    dp.register_callback_query_handler(
        handle_back_to_main_menu,
        lambda c: c.data and c.data == 'back_to_main_menu',
        state='*'
    )
    # Retention 3d follow-up — must be before generic main_menu
    dp.register_callback_query_handler(
        handle_retention_main_menu,
        lambda c: c.data and c.data == RETENTION_MAIN_MENU_CB,
        state="*",
    )
    # Canonical main_menu callback — used by handlers/nav.py with_navigation()
    dp.register_callback_query_handler(
        handle_back_to_main_menu,
        lambda c: c.data and c.data == 'main_menu',
        state='*'
    )
    # Backward-compat: old cached Telegram messages may still send go_home
    dp.register_callback_query_handler(
        handle_back_to_main_menu,
        lambda c: c.data and c.data == 'go_home',
        state='*'
    )
    # "🏠 Main menu" button in post-payment keyboard uses callback_data="start"
    dp.register_callback_query_handler(
        handle_back_to_main_menu,
        lambda c: c.data and c.data == 'start',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_how_to_submit_doc,
        lambda c: c.data and c.data == 'how_to_submit_doc',
        state='*'
    )
    # Register welcome "Open Menu" handler (open_menu) + legacy intro_continue
    dp.register_callback_query_handler(
        handle_intro_continue,
        lambda c: c.data in ("open_menu", "intro_continue"),
        state='*'
    )
    logger.info("✅ Registered handler for intro_continue / open_menu")
    dp.register_callback_query_handler(
        handle_my_documents,
        lambda c: c.data and c.data == 'my_documents',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_my_docs_category,
        lambda c: c.data and c.data.startswith('mydocs_cat_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_change_language,
        lambda c: c.data and c.data == 'change_language',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_country_selection,
        lambda c: c.data and c.data.startswith('select_country_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_country_soon,
        lambda c: c.data and c.data == 'country_soon',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_resume_draft,
        lambda c: c.data and c.data.startswith('resume_draft_'),
        state='*'
    )
    dp.register_callback_query_handler(
        handle_discard_draft,
        lambda c: c.data and c.data == 'discard_draft',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_gdpr_delete_confirm,
        lambda c: c.data and c.data == 'gdpr_delete_confirm',
        state='*'
    )
    # ── Settings menu ──────────────────────────────────────────────────────
    dp.register_callback_query_handler(
        handle_settings,
        lambda c: c.data and c.data == 'settings_menu',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_settings_help,
        lambda c: c.data and c.data == 'settings_help',
        state='*'
    )
    dp.register_callback_query_handler(
        handle_gdpr_delete_confirm_prompt,
        lambda c: c.data and c.data == 'gdpr_delete_confirm_prompt',
        state='*'
    )
    # ── Clean callback aliases (new menu button names) ─────────────────────
    dp.register_callback_query_handler(
        _alias_create_doc,  lambda c: c.data == 'create_doc',   state='*'
    )
    dp.register_callback_query_handler(
        handle_docs_housing,   lambda c: c.data == 'docs_housing',   state='*'
    )
    dp.register_callback_query_handler(
        handle_docs_financial, lambda c: c.data == 'docs_financial', state='*'
    )
    dp.register_callback_query_handler(
        handle_back_to_doc_categories,
        lambda c: c.data == 'back_to_doc_categories',
        state='*'
    )
    dp.register_callback_query_handler(
        _alias_find_termin, lambda c: c.data == 'find_termin',  state='*'
    )
    dp.register_callback_query_handler(
        _alias_my_docs,     lambda c: c.data == 'my_docs',      state='*'
    )
    dp.register_callback_query_handler(
        _handle_language_btn, lambda c: c.data == 'language', state='*'
    )
    dp.register_callback_query_handler(
        _handle_noop, lambda c: c.data == 'noop', state='*'
    )
