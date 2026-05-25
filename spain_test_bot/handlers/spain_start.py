"""
Spain Test Bot — /start flow, language selection, main menu.

Mirrors the main German bot's architecture exactly:
  /start
    └─▶ show_language_selection()       [always forced, no shortcuts]
          └─▶ handle_language_selection()
                ├─ save lang
                ├─ confirmation flash (0.8 s)
                └─▶ show_main_menu()

Main menu callbacks:
  check_slots      → triggers Spain checker inline
  how_it_works     → shows explanation screen
  support_contact  → shows support info
  language_change  → shows language picker again
  back_to_main_menu → back navigation
"""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.lang_store import get_lang, set_lang, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)


# ── FSM ───────────────────────────────────────────────────────────────────────

class SpainBotState(StatesGroup):
    selecting_language = State()
    main_menu          = State()


# ── Language picker data (mirrors LANGUAGE_BUTTONS from main bot) ─────────────
# callback_data format: lang_<code>   (same pattern as main bot)
LANGUAGE_BUTTONS = [
    ("🇪🇸 Español",    "lang_es"),   # row 1 left
    ("🇬🇧 English",    "lang_en"),   # row 1 right
    ("🇺🇦 Українська", "lang_uk"),   # row 2 left
    ("🇵🇱 Polski",     "lang_pl"),   # row 2 right
    ("🇷🇴 Română",     "lang_ro"),   # row 3 left
    ("🇦🇪 العربية",    "lang_ar"),   # row 3 right
]

# Shown briefly after the user taps a language — replaces the button grid
LANGUAGE_CONFIRMATIONS: dict[str, str] = {
    "es": "✅ Idioma seleccionado: Español",
    "en": "✅ Language selected: English",
    "uk": "✅ Мову вибрано: Українська",
    "pl": "✅ Język wybrany: Polski",
    "ro": "✅ Limbă selectată: Română",
    "ar": "✅ تم اختيار اللغة: العربية",
}

# ── Welcome / intro hook shown right after language is picked ─────────────────
_HOOK_TEXTS: dict[str, str] = {
    "es": (
        "🇪🇸 <b>Spain Citas Bot</b>\n\n"
        "Ayudamos a encontrar citas disponibles para trámites en España.\n\n"
        "⚡ Las citas aparecen de repente y desaparecen en minutos\n"
        "🤖 El bot las comprueba automáticamente y avisa al instante\n\n"
        "Elige lo que quieres hacer:"
    ),
    "en": (
        "🇪🇸 <b>Spain Citas Bot</b>\n\n"
        "We help you find available appointments (citas) for documents in Spain.\n\n"
        "⚡ Appointments appear randomly and disappear fast\n"
        "🤖 Bot monitors them automatically and notifies instantly\n\n"
        "Choose what you want to do:"
    ),
    "uk": (
        "🇪🇸 <b>Spain Citas Bot</b>\n\n"
        "Ми допомагаємо знайти citas для документів в Іспанії 🇪🇸\n\n"
        "⚡ Вільні записи з'являються раптово і швидко зникають\n"
        "🤖 Бот перевіряє їх автоматично і повідомляє одразу\n\n"
        "Обери, що хочеш зробити:"
    ),
    "pl": (
        "🇪🇸 <b>Spain Citas Bot</b>\n\n"
        "Pomagamy znaleźć dostępne wizyty (citas) na dokumenty w Hiszpanii.\n\n"
        "⚡ Wizyty pojawiają się losowo i szybko znikają\n"
        "🤖 Bot monitoruje je automatycznie i powiadamia natychmiast\n\n"
        "Wybierz, co chcesz zrobić:"
    ),
    "ro": (
        "🇪🇸 <b>Spain Citas Bot</b>\n\n"
        "Vă ajutăm să găsiți programări (citas) disponibile pentru acte în Spania.\n\n"
        "⚡ Programările apar aleatoriu și dispar rapid\n"
        "🤖 Botul le monitorizează automat și anunță imediat\n\n"
        "Alege ce vrei să faci:"
    ),
    "ar": (
        "🇪🇸 <b>Spain Citas Bot</b>\n\n"
        "نساعدك في العثور على المواعيد (citas) المتاحة للوثائق في إسبانيا.\n\n"
        "⚡ تظهر المواعيد بشكل مفاجئ وتختفي بسرعة\n"
        "🤖 يراقبها البوت تلقائياً ويُخطرك فوراً\n\n"
        "اختر ما تريد فعله:"
    ),
}

# ── Main menu texts ───────────────────────────────────────────────────────────
_MENU_TEXTS: dict[str, str] = {
    "es": "🇪🇸 <b>Spain Citas Bot</b>\n\nElige una opción del menú:",
    "en": "🇪🇸 <b>Spain Citas Bot</b>\n\nChoose a menu option:",
    "uk": "🇪🇸 <b>Spain Citas Bot</b>\n\nОберіть пункт меню:",
    "pl": "🇪🇸 <b>Spain Citas Bot</b>\n\nWybierz opcję z menu:",
    "ro": "🇪🇸 <b>Spain Citas Bot</b>\n\nAlege o opțiune din meniu:",
    "ar": "🇪🇸 <b>Spain Citas Bot</b>\n\nاختر خياراً من القائمة:",
}

# ── Button labels ─────────────────────────────────────────────────────────────
_BTN_CHECK: dict[str, str] = {
    "es": "🔍 Buscar citas",
    "en": "🔍 Find appointments (citas)",
    "uk": "🔍 Знайти записи (citas)",
    "pl": "🔍 Znajdź wizyty (citas)",
    "ro": "🔍 Găsește programări (citas)",
    "ar": "🔍 ابحث عن مواعيد (citas)",
}
_BTN_HOW: dict[str, str] = {
    "es": "ℹ️ Cómo funciona",
    "en": "ℹ️ How it works",
    "uk": "ℹ️ Як це працює",
    "pl": "ℹ️ Jak to działa",
    "ro": "ℹ️ Cum funcționează",
    "ar": "ℹ️ كيف يعمل",
}
_BTN_SUPPORT: dict[str, str] = {
    "es": "💬 ¿Tienes dudas?",
    "en": "💬 Have questions?",
    "uk": "💬 Є питання?",
    "pl": "💬 Masz pytania?",
    "ro": "💬 Ai întrebări?",
    "ar": "💬 لديك أسئلة؟",
}
_BTN_LANGUAGE: dict[str, str] = {
    "es": "🌐 Idioma",
    "en": "🌐 Language",
    "uk": "🌐 Мова",
    "pl": "🌐 Język",
    "ro": "🌐 Limbă",
    "ar": "🌐 اللغة",
}

# ── "How it works" screen ─────────────────────────────────────────────────────
_HOW_TEXTS: dict[str, str] = {
    "es": (
        "ℹ️ <b>Cómo funciona</b>\n\n"
        "1. Seleccionas ciudad y tipo de trámite (NIE, TIE, Residencia…)\n"
        "2. El bot revisa el portal oficial cada pocos segundos\n"
        "3. En cuanto aparece una cita libre, te enviamos el enlace directo\n"
        "4. Haces clic y reservas en ~1 minuto\n\n"
        "Las citas desaparecen rápido — actúa de inmediato."
    ),
    "en": (
        "ℹ️ <b>How it works</b>\n\n"
        "1. You choose a city and service type (NIE, TIE, Residencia…)\n"
        "2. The bot checks the official portal every few seconds\n"
        "3. The moment a free appointment (cita) appears, we send you the direct link\n"
        "4. You click and book in ~1 minute\n\n"
        "Citas disappear fast — act immediately."
    ),
    "uk": (
        "ℹ️ <b>Як це працює</b>\n\n"
        "1. Обираєш місто та тип послуги (NIE, TIE, Residencia…)\n"
        "2. Бот перевіряє офіційний портал кожні кілька секунд\n"
        "3. Як тільки з'являється вільний запис (cita) — надсилаємо пряме посилання\n"
        "4. Ти клікаєш і бронюєш за ~1 хвилину\n\n"
        "Citas зникають швидко — дій одразу."
    ),
    "pl": (
        "ℹ️ <b>Jak to działa</b>\n\n"
        "1. Wybierasz miasto i typ usługi (NIE, TIE, Residencia…)\n"
        "2. Bot sprawdza oficjalny portal co kilka sekund\n"
        "3. Gdy pojawi się wolny termin, wysyłamy Ci bezpośredni link\n"
        "4. Klikasz i rezerwujesz w ~1 minutę\n\n"
        "Terminy znikają szybko — działaj od razu."
    ),
    "ro": (
        "ℹ️ <b>Cum funcționează</b>\n\n"
        "1. Alegi orașul și tipul de serviciu (NIE, TIE, Residencia…)\n"
        "2. Botul verifică portalul oficial la câteva secunde\n"
        "3. De îndată ce apare o programare (cita) liberă, îți trimitem link-ul direct\n"
        "4. Apeși și rezervi în ~1 minut\n\n"
        "Citas dispar repede — acționează imediat."
    ),
    "ar": (
        "ℹ️ <b>كيف يعمل</b>\n\n"
        "1. تختار المدينة ونوع الخدمة (NIE أو TIE أو Residencia…)\n"
        "2. يفحص البوت البوابة الرسمية كل بضع ثوانٍ\n"
        "3. بمجرد ظهور موعد متاح، نرسل لك الرابط المباشر\n"
        "4. تنقر وتحجز في ~دقيقة واحدة\n\n"
        "المواعيد تختفي بسرعة — تصرف فوراً."
    ),
}

# ── Support screen ────────────────────────────────────────────────────────────
_SUPPORT_TEXTS: dict[str, str] = {
    "es": (
        "💬 <b>Soporte</b>\n\n"
        "¿Tienes preguntas o problemas?\n\n"
        "💬 Contáctanos: @SpainCitasSupport"
    ),
    "en": (
        "💬 <b>Support</b>\n\n"
        "Questions or issues?\n\n"
        "💬 Contact support: @SpainCitasSupport"
    ),
    "uk": (
        "💬 <b>Підтримка</b>\n\n"
        "Маєш питання або проблеми?\n\n"
        "💬 Напишіть нам: @SpainCitasSupport"
    ),
    "pl": (
        "💬 <b>Wsparcie</b>\n\n"
        "Masz pytania lub problemy?\n\n"
        "💬 Napisz do nas: @SpainCitasSupport"
    ),
    "ro": (
        "💬 <b>Suport</b>\n\n"
        "Ai întrebări sau probleme?\n\n"
        "💬 Contactează-ne: @SpainCitasSupport"
    ),
    "ar": (
        "💬 <b>الدعم</b>\n\n"
        "هل لديك أسئلة أو مشاكل؟\n\n"
        "💬 تواصل مع الدعم: @SpainCitasSupport"
    ),
}

# Shared "back to menu" button label
_BTN_BACK: dict[str, str] = {
    "es": "◀️ Volver al menú",
    "en": "◀️ Back to menu",
    "uk": "◀️ Назад до меню",
    "pl": "◀️ Wróć do menu",
    "ro": "◀️ Înapoi la meniu",
    "ar": "◀️ العودة للقائمة",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lang(user_id: int) -> str:
    return get_lang(user_id)


def _t(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


def _back_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_BACK, lang), callback_data="back_to_main_menu"))
    return kb


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(message: types.Message, state: FSMContext) -> None:
    """
    Handle /start [param].

    Deeplinks:
      /start paid_monitor  — webhook already activated → show monitoring status
      /start cancel        — user cancelled payment → show main menu with message
    All other cases → force language selection.
    """
    param = ""
    if message.text and len(message.text.split()) > 1:
        param = message.text.split(maxsplit=1)[1].strip()

    logger.info("CMD_START | user=%s param=%s", message.from_user.id, param or "(none)")

    # ── Deeplink: payment completed ───────────────────────────────────────────
    if param == "paid_monitor":
        lang = get_lang(message.from_user.id)

        # Shared button labels for this screen
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
        _BTN_MENU: dict[str, str] = {
            "es": "🏠 Menú principal",
            "en": "🏠 Main menu",
            "uk": "🏠 Головне меню",
            "pl": "🏠 Menu główne",
            "ro": "🏠 Meniu principal",
            "ar": "🏠 القائمة الرئيسية",
        }

        # Full activation screen shown when webhook already fired
        _ACTIVE_SCREEN: dict[str, str] = {
            "es": (
                "✅ <b>¡Pago exitoso! Búsqueda activada</b>\n\n"
                "📍 {city} — {service}\n\n"
                "🎯 Citas restantes: <b>{attempts}</b>\n\n"
                "🔄 Ya estamos buscando citas para ti\n"
                "⏱ Última verificación: {last_check}\n"
                "⏭ Próxima verificación: {next_check}\n\n"
                "📲 En cuanto aparezca una cita — te avisamos al instante\n"
                "👉 Puedes cerrar el bot — te notificaremos de todas formas"
            ),
            "en": (
                "✅ <b>Payment successful! Search activated</b>\n\n"
                "📍 {city} — {service}\n\n"
                "🎯 Appointments remaining: <b>{attempts}</b>\n\n"
                "🔄 We are already searching for citas for you\n"
                "⏱ Last check: {last_check}\n"
                "⏭ Next check: {next_check}\n\n"
                "📲 You will be notified instantly as soon as an appointment appears\n"
                "👉 You can close the bot — we will notify you anyway"
            ),
            "uk": (
                "✅ <b>Оплата успішна! Пошук активовано</b>\n\n"
                "📍 {city} — {service}\n\n"
                "🎯 Залишилось спроб: <b>{attempts}</b>\n\n"
                "🔄 Ми вже шукаємо citas для тебе\n"
                "⏱ Остання перевірка: {last_check}\n"
                "⏭ Наступна перевірка: {next_check}\n\n"
                "📲 Як тільки з'явиться запис — ти одразу отримаєш повідомлення\n"
                "👉 Можеш закрити бот — ми все одно повідомимо"
            ),
            "pl": (
                "✅ <b>Płatność udana! Wyszukiwanie aktywowane</b>\n\n"
                "📍 {city} — {service}\n\n"
                "🎯 Pozostałe terminy: <b>{attempts}</b>\n\n"
                "🔄 Już szukamy dla Ciebie terminów citas\n"
                "⏱ Ostatnie sprawdzenie: {last_check}\n"
                "⏭ Następne sprawdzenie: {next_check}\n\n"
                "📲 Gdy tylko pojawi się termin — natychmiast dostaniesz powiadomienie\n"
                "👉 Możesz zamknąć bota — i tak Cię powiadomimy"
            ),
            "ro": (
                "✅ <b>Plată reușită! Căutare activată</b>\n\n"
                "📍 {city} — {service}\n\n"
                "🎯 Programări rămase: <b>{attempts}</b>\n\n"
                "🔄 Căutăm deja programări (citas) pentru tine\n"
                "⏱ Ultima verificare: {last_check}\n"
                "⏭ Următoarea verificare: {next_check}\n\n"
                "📲 Imediat ce apare o programare — primești notificare\n"
                "👉 Poți închide botul — te vom notifica oricum"
            ),
            "ar": (
                "✅ <b>تم الدفع بنجاح! تم تفعيل البحث</b>\n\n"
                "📍 {city} — {service}\n\n"
                "🎯 المواعيد المتبقية: <b>{attempts}</b>\n\n"
                "🔄 نحن نبحث بالفعل عن citas لك\n"
                "⏱ آخر فحص: {last_check}\n"
                "⏭ الفحص التالي: {next_check}\n\n"
                "📲 بمجرد ظهور موعد — سيتم إخطارك فوراً\n"
                "👉 يمكنك إغلاق البوت — سنخطرك على أي حال"
            ),
        }

        # Brief screen while webhook is still in transit (rare race condition)
        _ACTIVATING_SCREEN: dict[str, str] = {
            "es": (
                "🚀 <b>Activando monitoreo…</b>\n\n"
                "Tu pago fue recibido. El monitoreo se activará en unos segundos.\n\n"
                "📲 Recibirás un mensaje de confirmación automáticamente."
            ),
            "en": (
                "🚀 <b>Activating monitoring…</b>\n\n"
                "Your payment was received. Monitoring will activate in a few seconds.\n\n"
                "📲 You will receive a confirmation message automatically."
            ),
            "uk": (
                "🚀 <b>Активуємо моніторинг…</b>\n\n"
                "Оплату отримано. Моніторинг активується за кілька секунд.\n\n"
                "📲 Ти автоматично отримаєш повідомлення про підтвердження."
            ),
            "pl": (
                "🚀 <b>Aktywowanie monitoringu…</b>\n\n"
                "Twoja płatność została odebrana. Monitoring aktywuje się za kilka sekund.\n\n"
                "📲 Automatycznie otrzymasz wiadomość potwierdzającą."
            ),
            "ro": (
                "🚀 <b>Se activează monitorizarea…</b>\n\n"
                "Plata a fost primită. Monitorizarea se va activa în câteva secunde.\n\n"
                "📲 Vei primi automat un mesaj de confirmare."
            ),
            "ar": (
                "🚀 <b>جارٍ تفعيل المراقبة…</b>\n\n"
                "تم استلام دفعتك. ستُفعَّل المراقبة خلال ثوانٍ.\n\n"
                "📲 ستتلقى رسالة تأكيد تلقائيًا."
            ),
        }

        def _monitor_kb_full() -> InlineKeyboardMarkup:
            kb = InlineKeyboardMarkup(row_width=1)
            kb.add(InlineKeyboardButton(_t(_BTN_STATUS, lang), callback_data="monitor_status"))
            kb.add(InlineKeyboardButton(_t(_BTN_STOP,   lang), callback_data="stop_monitor"))
            kb.add(InlineKeyboardButton(_t(_BTN_MENU,   lang), callback_data="back_to_main_menu"))
            return kb

        try:
            from utils.payments import is_paid, get_record, get_pending, get_attempts_left
            from utils.monitoring import is_monitoring, start_monitoring

            if is_paid(message.from_user.id):
                # Webhook already fired — restore FSM and show full monitoring screen
                uid    = message.from_user.id
                record = get_record(uid)
                city_display = record["city"]    if record else "—"
                svc_display  = record["service"] if record else "—"
                city_key     = record["city"]    if record else ""
                svc_key      = record["service"] if record else ""
                authority    = svc_key

                if record:
                    await state.update_data(city=city_key, svc=svc_key)
                    # Resolve localised display names
                    try:
                        from handlers.city_select import CITIES
                        from handlers.service_select import SERVICES
                        def _td(d): return d.get(lang) or d.get("en") or next(iter(d.values()))
                        city_display = _td(CITIES.get(city_key, {"en": city_key.title()}))
                        svc_info     = SERVICES.get(svc_key, {})
                        svc_display  = _td(svc_info.get("labels", {"en": svc_key}))
                        authority    = svc_info.get("authority", svc_key)
                    except Exception:
                        pass

                # ── BUG FIX: start monitoring if not already running ───────────
                if not is_monitoring(uid) and city_key and svc_key:
                    try:
                        await start_monitoring(
                            bot=message.bot,
                            user_id=uid,
                            city=city_key,
                            svc=svc_key,
                            authority=authority,
                            city_display=city_display,
                            svc_display=svc_display,
                            lang=lang,
                        )
                        logger.info("PAID_MONITOR_STARTED | user=%s city=%s svc=%s", uid, city_key, svc_key)
                    except Exception as _start_exc:
                        logger.warning("PAID_MONITOR_START_FAILED | user=%s err=%s", uid, _start_exc)

                attempts = get_attempts_left(uid)

                # Get live timing from monitoring session (just started or already running)
                try:
                    from utils.monitoring import get_session, human_last, human_next
                    _sess = get_session(uid)
                    last_check = human_last(_sess["last_check_ts"] if _sess else None, lang)
                    next_check = human_next(_sess["next_check_ts"] if _sess else None, lang)
                except Exception:
                    last_check = "—"
                    next_check = "~30–60 сек" if lang == "uk" else "~30–60 sec"

                text = _t(_ACTIVE_SCREEN, lang).format(
                    city=city_display,
                    service=svc_display,
                    attempts=attempts,
                    last_check=last_check,
                    next_check=next_check,
                )
                await message.answer(text, parse_mode="HTML", reply_markup=_monitor_kb_full())
                return

            # Webhook not yet fired — restore FSM from pending store
            pending = get_pending(message.from_user.id)
            if pending:
                await state.update_data(
                    city=pending["city"],
                    svc=pending["svc"],
                )
        except ImportError:
            pass

        # Webhook not yet received — try verifying payment directly via Stripe API
        _auto_activated = False
        try:
            from utils.payments import get_pending as _get_pending, activate as _activate, get_attempts_left as _gal2
            _pending2 = _get_pending(message.from_user.id)
            if _pending2:
                _session_id = _pending2.get("stripe_session_id", "")
                if _session_id:
                    import stripe as _stripe
                    _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
                    _stripe_sess = _stripe.checkout.Session.retrieve(_session_id)
                    if getattr(_stripe_sess, "payment_status", "") == "paid":
                        logger.info(
                            "DEEPLINK_STRIPE_VERIFY_PAID | user=%s session=%s — auto-activating",
                            message.from_user.id, _session_id,
                        )
                        _activate(message.from_user.id, _pending2["city"], _pending2["svc"], _pending2["plan"])
                        # Resolve display names
                        _uid2  = message.from_user.id
                        _ck2   = _pending2["city"]
                        _sk2   = _pending2["svc"]
                        _cd2   = _ck2.title()
                        _sd2   = _sk2
                        _auth2 = _sk2
                        try:
                            from handlers.city_select import CITIES
                            from handlers.service_select import SERVICES
                            def _td2(d): return d.get(lang) or d.get("en") or next(iter(d.values()))
                            _cd2   = _td2(CITIES.get(_ck2, {"en": _ck2.title()}))
                            _si2   = SERVICES.get(_sk2, {})
                            _sd2   = _td2(_si2.get("labels", {"en": _sk2}))
                            _auth2 = _si2.get("authority", _sk2)
                        except Exception:
                            pass
                        await state.update_data(city=_ck2, svc=_sk2)
                        from utils.monitoring import is_monitoring as _im2, start_monitoring as _sm2, get_session as _gs2, human_last as _hl2, human_next as _hn2
                        if not _im2(_uid2):
                            try:
                                await _sm2(bot=message.bot, user_id=_uid2, city=_ck2, svc=_sk2, authority=_auth2, city_display=_cd2, svc_display=_sd2, lang=lang)
                                logger.info("DEEPLINK_MONITORING_STARTED | user=%s city=%s svc=%s", _uid2, _ck2, _sk2)
                            except Exception as _se2:
                                logger.warning("DEEPLINK_MONITORING_START_FAILED | user=%s err=%s", _uid2, _se2)
                        _attempts2 = _gal2(_uid2)
                        _sess2     = _gs2(_uid2)
                        _lc2       = _hl2(_sess2["last_check_ts"] if _sess2 else None, lang)
                        _nc2       = _hn2(_sess2["next_check_ts"] if _sess2 else None, lang)
                        _text2     = _t(_ACTIVE_SCREEN, lang).format(city=_cd2, service=_sd2, attempts=_attempts2, last_check=_lc2, next_check=_nc2)
                        await message.answer(_text2, parse_mode="HTML", reply_markup=_monitor_kb_full())
                        _auto_activated = True
        except Exception as _verify_exc:
            logger.warning("DEEPLINK_STRIPE_VERIFY_FAILED | user=%s err=%s", message.from_user.id, _verify_exc)

        if _auto_activated:
            return

        # Webhook still in transit — show activating screen, no main menu redirect
        kb_wait = InlineKeyboardMarkup(row_width=1)
        kb_wait.add(InlineKeyboardButton(_t(_BTN_STATUS, lang), callback_data="monitor_status"))
        await message.answer(
            _t(_ACTIVATING_SCREEN, lang),
            parse_mode="HTML",
            reply_markup=kb_wait,
        )
        return

    # ── Deeplink: payment cancelled ───────────────────────────────────────────
    if param == "cancel":
        lang = get_lang(message.from_user.id)
        _CANCEL: dict[str, str] = {
            "es": "ℹ️ Pago cancelado. Puedes elegir un plan en cualquier momento.",
            "en": "ℹ️ Payment cancelled. You can choose a plan at any time.",
            "uk": "ℹ️ Оплату скасовано. Можеш обрати тариф будь-коли.",
            "pl": "ℹ️ Płatność anulowana. Możesz wybrać plan w dowolnym momencie.",
            "ro": "ℹ️ Plată anulată. Poți alege un plan oricând.",
            "ar": "ℹ️ تم إلغاء الدفع. يمكنك اختيار خطة في أي وقت.",
        }
        # DO NOT call state.finish() — preserve selected city/service for retry
        await message.answer(_CANCEL.get(lang, _CANCEL["en"]), parse_mode="HTML")
        await show_main_menu(message, lang)
        return

    # ── Default: force language selection ────────────────────────────────────
    await state.finish()
    await show_language_selection(message)


# ── Language picker ───────────────────────────────────────────────────────────

async def show_language_selection(message: types.Message) -> None:
    """2-column grid of language buttons (3 rows × 2), identical layout to main bot."""
    kb = InlineKeyboardMarkup()
    for i in range(0, len(LANGUAGE_BUTTONS), 2):
        row = [InlineKeyboardButton(LANGUAGE_BUTTONS[i][0], callback_data=LANGUAGE_BUTTONS[i][1])]
        if i + 1 < len(LANGUAGE_BUTTONS):
            row.append(InlineKeyboardButton(LANGUAGE_BUTTONS[i + 1][0], callback_data=LANGUAGE_BUTTONS[i + 1][1]))
        kb.row(*row)

    await message.answer("🌐 Choose language / Elige idioma / Оберіть мову", reply_markup=kb)


async def handle_language_selection(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Save language → flash confirmation → show main menu.
    Mirrors main bot's handle_language_selection exactly."""
    await callback.answer()

    lang_code = callback.data.split("_", 1)[1]   # lang_es → es
    if lang_code not in SUPPORTED_LANGUAGES:
        lang_code = DEFAULT_LANGUAGE

    user_id = callback.from_user.id
    set_lang(user_id, lang_code)
    await state.update_data(lang=lang_code, country="es")

    logger.info("LANGUAGE_SELECTED | user=%s lang=%s", user_id, lang_code)

    # Brief confirmation flash (edit inline buttons away)
    confirm = LANGUAGE_CONFIRMATIONS.get(lang_code, LANGUAGE_CONFIRMATIONS["en"])
    try:
        await callback.message.edit_text(f"<b>{confirm}</b>", parse_mode="HTML")
    except Exception:
        pass

    await asyncio.sleep(0.8)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await show_main_menu(callback.message, lang_code)


# ── Main menu ─────────────────────────────────────────────────────────────────

async def show_main_menu(
    message: types.Message,
    lang: str,
    greeting: str = "",
) -> None:
    """Main menu — same layout as German bot.
    Row 1: [🔍 Find appointments]     ← full width
    Row 2: [ℹ️ How it works]          ← full width
    Row 3: [💬 Support]               ← full width
    Row 4: [🌐 Language]              ← utility
    """
    text = (_t(_HOOK_TEXTS, lang))
    if greeting:
        text = greeting + "\n" + text

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_CHECK,    lang), callback_data="check_slots"))
    kb.add(InlineKeyboardButton(_t(_BTN_HOW,      lang), callback_data="how_it_works"))
    kb.add(InlineKeyboardButton(_t(_BTN_SUPPORT,  lang), callback_data="support_contact"))
    kb.add(InlineKeyboardButton(_t(_BTN_LANGUAGE, lang), callback_data="language_change"))

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ── Main menu callbacks ───────────────────────────────────────────────────────

async def handle_back_to_main_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = _lang(callback.from_user.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_main_menu(callback.message, lang)


async def handle_language_change(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Re-show language picker from the main menu."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_language_selection(callback.message)


async def handle_how_it_works(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = _lang(callback.from_user.id)
    await callback.message.edit_text(
        _t(_HOW_TEXTS, lang),
        parse_mode="HTML",
        reply_markup=_back_kb(lang),
    )


async def handle_support_contact(callback: types.CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = _lang(callback.from_user.id)
    await callback.message.edit_text(
        _t(_SUPPORT_TEXTS, lang),
        parse_mode="HTML",
        reply_markup=_back_kb(lang),
    )


async def handle_check_slots(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Redirect 'Check slots' to city selection — full 5-city / 5-service flow."""
    await callback.answer()
    lang = _lang(callback.from_user.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    from handlers.city_select import show_city_selection
    await show_city_selection(callback.message, lang)


# ── Registration (mirrors register_start_handlers in main bot) ────────────────

def register(dp: Dispatcher) -> None:
    # /start command
    dp.register_message_handler(cmd_start, commands=["start"], state="*")

    # Language selection buttons: lang_es, lang_en, lang_uk, lang_pl, lang_ro, lang_ar
    dp.register_callback_query_handler(
        handle_language_selection,
        lambda c: c.data and c.data.startswith("lang_"),
        state="*",
    )

    # Main menu actions
    dp.register_callback_query_handler(handle_check_slots,        lambda c: c.data == "check_slots",       state="*")
    dp.register_callback_query_handler(handle_how_it_works,       lambda c: c.data == "how_it_works",      state="*")
    dp.register_callback_query_handler(handle_support_contact,    lambda c: c.data == "support_contact",   state="*")
    dp.register_callback_query_handler(handle_language_change,    lambda c: c.data == "language_change",   state="*")
    dp.register_callback_query_handler(handle_back_to_main_menu,  lambda c: c.data == "back_to_main_menu", state="*")
