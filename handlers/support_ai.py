# -*- coding: utf-8 -*-
"""
handlers/support_ai.py — AI Support Assistant handler.

Opens a GPT-powered support chat from the main menu.
Does NOT touch Termin, PDF, Stripe, or FSM document states.
"""

import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import SupportStates
from utils.support_ai import ask_support_ai, ask_support_ai_doc
from utils.helpers import get_user_lang

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Localized strings
# ---------------------------------------------------------------------------

_SUPPORT_GREETING = {
    "uk": (
        "💬 <b>Підтримка</b>\n\n"
        "Ми допоможемо з:\n"
        "• заповненням документів та PDF\n"
        "• моніторингом Termin\n"
        "• оплатою та тарифами\n"
        "• тим, як працює сервіс\n\n"
        "Напишіть ваше питання — ми допоможемо розібратися 👇"
    ),
    "en": (
        "💬 <b>Support</b>\n\n"
        "We can help with:\n"
        "• filling out documents and PDF\n"
        "• Termin monitoring\n"
        "• payments and pricing\n"
        "• how the service works\n\n"
        "Write your question — we'll help you figure it out 👇"
    ),
    "de": (
        "💬 <b>Support</b>\n\n"
        "Wir helfen bei:\n"
        "• Ausfüllen von Dokumenten und PDFs\n"
        "• Termin-Überwachung\n"
        "• Zahlung und Preisen\n"
        "• Wie der Service funktioniert\n\n"
        "Schreiben Sie Ihre Frage — wir helfen Ihnen weiter 👇"
    ),
    "pl": (
        "💬 <b>Wsparcie</b>\n\n"
        "Pomożemy z:\n"
        "• wypełnianiem dokumentów i PDF\n"
        "• monitoringiem Termin\n"
        "• płatnościami i cennikiem\n"
        "• jak działa serwis\n\n"
        "Napisz swoje pytanie — pomożemy to wyjaśnić 👇"
    ),
    "tr": (
        "💬 <b>Destek</b>\n\n"
        "Şunlarda yardımcı oluruz:\n"
        "• belge doldurma ve PDF\n"
        "• Termin takibi\n"
        "• ödeme ve fiyatlandırma\n"
        "• servis nasıl çalışır\n\n"
        "Sorunuzu yazın — çözmenize yardımcı olacağız 👇"
    ),
    "ar": (
        "💬 <b>الدعم</b>\n\n"
        "يمكننا المساعدة في:\n"
        "• ملء المستندات وملفات PDF\n"
        "• مراقبة Termin\n"
        "• المدفوعات والأسعار\n"
        "• كيف يعمل الخدمة\n\n"
        "اكتب سؤالك — سنساعدك في الوصول إلى الحل 👇"
    ),
}

_THINKING_TEXT = {
    "uk": "⏳ Обробляю ваше запитання…",
    "en": "⏳ Processing your question…",
    "de": "⏳ Verarbeite Ihre Frage…",
    "pl": "⏳ Przetwarzam Twoje pytanie…",
    "tr": "⏳ Sorunuz işleniyor…",
    "ar": "⏳ جارٍ معالجة سؤالك…",
}

_FOLLOW_UP_BTN = {
    "uk": "💬 Ще запитання",
    "en": "💬 Ask another question",
    "de": "💬 Weitere Frage",
    "pl": "💬 Kolejne pytanie",
    "tr": "💬 Başka soru sor",
    "ar": "💬 سؤال آخر",
}

_MENU_BTN = {
    "uk": "🏠 Головне меню",
    "en": "🏠 Main menu",
    "de": "🏠 Hauptmenü",
    "pl": "🏠 Menu główne",
    "tr": "🏠 Ana menü",
    "ar": "🏠 القائمة الرئيسية",
}

# CTA buttons shown below every AI answer to guide users to actions
_CTA_DOCS_BTN = {
    "uk": "📄 Відкрити документи",
    "en": "📄 Open documents",
    "de": "📄 Dokumente öffnen",
    "pl": "📄 Otwórz dokumenty",
    "tr": "📄 Belgeleri aç",
    "ar": "📄 فتح المستندات",
}
_CTA_TERMIN_BTN = {
    "uk": "🗓 Знайти термін",
    "en": "🗓 Find appointment",
    "de": "🗓 Termin finden",
    "pl": "🗓 Znajdź termin",
    "tr": "🗓 Randevu bul",
    "ar": "🗓 البحث عن موعد",
}


def _l(d: dict, lang: str) -> str:
    if lang == "ua":
        lang = "uk"
    return d.get(lang, d.get("en", ""))


# ---------------------------------------------------------------------------
# doc_type → human-readable label (German official name)
# ---------------------------------------------------------------------------

_DOC_LABELS: dict[str, str] = {
    "anmeldung":                    "Anmeldung",
    "ummeldung":                    "Ummeldung",
    "abmeldung":                    "Abmeldung",
    "wohnungsgeberbestaetigung":    "Wohnungsgeberbestätigung",
    "wohngeld":                     "Wohngeld",
    "kindergeld":                   "Kindergeld",
    "buergergeld":                  "Bürgergeld",
    "aufenthaltstitel":             "Aufenthaltstitel",
    "verlaengerung_aufenthaltstitel": "Verlängerung Aufenthaltstitel",
    "elterngeld":                   "Elterngeld",
    "unterhaltsvorschuss":          "Unterhaltsvorschuss",
    "kinderzuschlag":               "Kinderzuschlag",
    "wbs":                          "Wohnberechtigungsschein (WBS)",
    "bafoeg":                       "BAföG",
    "ebk":                          "Einkommens­bescheinigung (EBK)",
    "verpflichtungserklaerung":     "Verpflichtungserklärung",
    "beschaeftigungserklaerung":    "Beschäftigungserklärung",
    "mietbescheinigung":            "Mietbescheinigung",
}


def _doc_label(doc_type: str) -> str:
    """Return the human-readable German label for *doc_type*."""
    return _DOC_LABELS.get((doc_type or "").lower(), doc_type.capitalize())


# ---------------------------------------------------------------------------
# Localized strings — doc-context deep-link support
# ---------------------------------------------------------------------------

_DOC_GREETING: dict[str, str] = {
    "uk": (
        "💬 <b>Підтримка</b>\n\n"
        "Бачу, вам потрібна допомога з документом:\n"
        "👉 <b>{doc_label}</b>\n\n"
        "Напишіть своє запитання — відповімо покроково."
    ),
    "en": (
        "💬 <b>Support</b>\n\n"
        "I see you need help with:\n"
        "👉 <b>{doc_label}</b>\n\n"
        "Write your question — we'll walk you through it step by step."
    ),
    "de": (
        "💬 <b>Support</b>\n\n"
        "Sie benötigen Hilfe zu folgendem Dokument:\n"
        "👉 <b>{doc_label}</b>\n\n"
        "Stellen Sie Ihre Frage — wir helfen Ihnen Schritt für Schritt."
    ),
    "pl": (
        "💬 <b>Wsparcie</b>\n\n"
        "Widzę, że potrzebujesz pomocy z dokumentem:\n"
        "👉 <b>{doc_label}</b>\n\n"
        "Napisz swoje pytanie — odpowiemy krok po kroku."
    ),
    "tr": (
        "💬 <b>Destek</b>\n\n"
        "Şu belge için yardıma ihtiyacınız var:\n"
        "👉 <b>{doc_label}</b>\n\n"
        "Sorunuzu yazın — adım adım yardımcı olacağız."
    ),
    "ar": (
        "💬 <b>الدعم</b>\n\n"
        "أرى أنك تحتاج إلى مساعدة بشأن المستند:\n"
        "👉 <b>{doc_label}</b>\n\n"
        "اكتب سؤالك — سنرد عليك خطوة بخطوة."
    ),
}

_DOC_FALLBACK_GREETING: dict[str, str] = {
    "uk": "💬 Ми допоможемо вам із документами. Напишіть ваше запитання 👇",
    "en": "💬 We'll help you with German documents. Write your question 👇",
    "de": "💬 Wir helfen Ihnen mit deutschen Dokumenten. Schreiben Sie Ihre Frage 👇",
    "pl": "💬 Pomożemy Ci z dokumentami. Napisz swoje pytanie 👇",
    "tr": "💬 Belgelerle ilgili yardımcı olacağız. Sorunuzu yazın 👇",
    "ar": "💬 سنساعدك في المستندات. اكتب سؤالك 👇",
}

_EXIT_BTN: dict[str, str] = {
    "uk": "⬅️ Вийти з підтримки",
    "en": "⬅️ Exit support",
    "de": "⬅️ Support beenden",
    "pl": "⬅️ Wyjdź ze wsparcia",
    "tr": "⬅️ Desteği kapat",
    "ar": "⬅️ الخروج من الدعم",
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def open_ai_support(callback: types.CallbackQuery, state: FSMContext):
    """Open support chat when user taps the Support button."""
    await callback.answer()
    lang = (get_user_lang(callback.from_user.id) or "en").strip().lower()

    _back_btn = {
        "uk": "← Головне меню", "ua": "← Головне меню", "en": "← Main menu",
        "de": "← Hauptmenü", "pl": "← Menu główne", "tr": "← Ana menü", "ar": "← القائمة الرئيسية",
    }
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        _back_btn.get(lang, _back_btn["en"]),
        callback_data="back_to_main_menu",
    ))

    await callback.message.answer(_l(_SUPPORT_GREETING, lang), parse_mode="HTML", reply_markup=kb)
    await SupportStates.waiting_for_question.set()
    logger.info("SUPPORT_OPENED: user_id=%s", callback.from_user.id)


async def handle_support_question(message: types.Message, state: FSMContext):
    """Receive user question, call GPT, return answer."""
    lang = (get_user_lang(message.from_user.id) or "en").strip().lower()
    question = (message.text or "").strip()

    if not question:
        return

    thinking_msg = await message.answer(_l(_THINKING_TEXT, lang))

    response = await ask_support_ai(question)

    # Delete "thinking" placeholder
    try:
        await thinking_msg.delete()
    except Exception:
        pass

    kb = InlineKeyboardMarkup(row_width=2)
    # Primary CTAs — lead the user directly to product flows
    kb.row(
        InlineKeyboardButton(_l(_CTA_DOCS_BTN, lang), callback_data="start_documents"),
        InlineKeyboardButton(_l(_CTA_TERMIN_BTN, lang), callback_data="category_termin"),
    )
    kb.add(InlineKeyboardButton(_l(_FOLLOW_UP_BTN, lang), callback_data="ai_support"))
    kb.add(InlineKeyboardButton(_l(_MENU_BTN, lang), callback_data="back_to_main_menu"))

    await message.answer(response, reply_markup=kb)
    logger.info("SUPPORT_ANSWERED: user_id=%s question_len=%s", message.from_user.id, len(question))

    # Keep state open so user can ask another question via the button,
    # but clear state here so a follow-up tap on the button re-opens cleanly.
    await state.finish()


# ---------------------------------------------------------------------------
# Deep-link doc-context support (ai_{doc_type})
# ---------------------------------------------------------------------------

async def open_ai_doc_support(message: types.Message, state: FSMContext, doc_type: str):
    """
    Called from cmd_start when the user arrives via /start ai_{doc_type}.
    Sets FSM to waiting_for_doc_question with doc_type stored in state.
    """
    lang = (get_user_lang(message.from_user.id) or "en").strip().lower()
    if lang == "ua":
        lang = "uk"

    doc_label = _doc_label(doc_type)

    if doc_type:
        greeting_tpl = _DOC_GREETING.get(lang, _DOC_GREETING["en"])
        greeting = greeting_tpl.format(doc_label=doc_label)
    else:
        greeting = _DOC_FALLBACK_GREETING.get(lang, _DOC_FALLBACK_GREETING["en"])

    from handlers.nav import nav_home_text
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(
        _l(_EXIT_BTN, lang),
        callback_data="ai_doc_support_exit",
    ))
    kb.add(InlineKeyboardButton(
        nav_home_text(lang),
        callback_data="main_menu",
    ))

    await state.finish()
    await SupportStates.waiting_for_doc_question.set()
    async with state.proxy() as data:
        data["doc_type"] = doc_type or ""

    await message.answer(greeting, parse_mode="HTML", reply_markup=kb)
    logger.info("DOC_AI_OPENED: user_id=%s doc_type=%s", message.from_user.id, doc_type)


async def handle_doc_support_question(message: types.Message, state: FSMContext):
    """Receive user question, inject doc_type context, call GPT, return answer."""
    lang = (get_user_lang(message.from_user.id) or "en").strip().lower()
    if lang == "ua":
        lang = "uk"
    question = (message.text or "").strip()

    if not question:
        return

    async with state.proxy() as data:
        doc_type = data.get("doc_type", "")

    thinking_msg = await message.answer(_l(_THINKING_TEXT, lang))

    if doc_type:
        response = await ask_support_ai_doc(question, doc_type)
    else:
        response = await ask_support_ai(question)

    try:
        await thinking_msg.delete()
    except Exception:
        pass

    from handlers.nav import nav_home_text
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_l(_FOLLOW_UP_BTN, lang), callback_data=f"ai_doc_support_followup_{doc_type}"))
    kb.add(InlineKeyboardButton(_l(_EXIT_BTN, lang), callback_data="ai_doc_support_exit"))
    kb.add(InlineKeyboardButton(nav_home_text(lang), callback_data="main_menu"))

    await message.answer(response, reply_markup=kb)
    logger.info(
        "DOC_AI_ANSWERED: user_id=%s doc_type=%s question_len=%s",
        message.from_user.id, doc_type, len(question),
    )


async def handle_doc_support_exit(callback: types.CallbackQuery, state: FSMContext):
    """Exit doc-context support chat and return to main menu."""
    await callback.answer()
    await state.finish()
    lang = (get_user_lang(callback.from_user.id) or "en").strip().lower()
    from handlers.start import _show_main_menu
    await _show_main_menu(callback.message, lang)


async def handle_doc_support_followup(callback: types.CallbackQuery, state: FSMContext):
    """Re-open doc-context support when user taps 'ask another question'."""
    await callback.answer()
    # Extract doc_type from callback_data: ai_doc_support_followup_{doc_type}
    doc_type = callback.data.replace("ai_doc_support_followup_", "", 1)
    lang = (get_user_lang(callback.from_user.id) or "en").strip().lower()
    if lang == "ua":
        lang = "uk"

    doc_label = _doc_label(doc_type)
    _prompt = {
        "uk": f"Задайте наступне запитання про <b>{doc_label}</b> 👇",
        "en": f"Ask your next question about <b>{doc_label}</b> 👇",
        "de": f"Stellen Sie Ihre nächste Frage zu <b>{doc_label}</b> 👇",
        "pl": f"Zadaj następne pytanie o <b>{doc_label}</b> 👇",
        "tr": f"<b>{doc_label}</b> hakkında sonraki sorunuzu sorun 👇",
        "ar": f"اطرح سؤالك التالي حول <b>{doc_label}</b> 👇",
    }

    from handlers.nav import nav_home_text
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_l(_EXIT_BTN, lang), callback_data="ai_doc_support_exit"))
    kb.add(InlineKeyboardButton(nav_home_text(lang), callback_data="main_menu"))

    await SupportStates.waiting_for_doc_question.set()
    async with state.proxy() as data:
        data["doc_type"] = doc_type

    await callback.message.answer(
        _prompt.get(lang, _prompt["en"]),
        parse_mode="HTML",
        reply_markup=kb,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

async def handle_support_back(callback: types.CallbackQuery, state: FSMContext):
    """Exit support chat and return to main menu, clearing FSM state."""
    await callback.answer()
    await state.finish()
    lang = (get_user_lang(callback.from_user.id) or "en").strip().lower()
    from handlers.start import _show_main_menu
    await _show_main_menu(callback.message, lang)


def register_support_handlers(dp: Dispatcher):
    # ── existing generic support ────────────────────────────────────────────
    dp.register_callback_query_handler(
        open_ai_support,
        lambda c: c.data == "ai_support",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_support_back,
        lambda c: c.data == "back_to_main_menu",
        state=SupportStates.waiting_for_question,
    )
    dp.register_message_handler(
        handle_support_question,
        state=SupportStates.waiting_for_question,
        content_types=types.ContentType.TEXT,
    )

    # ── deep-link doc-context support ───────────────────────────────────────
    dp.register_callback_query_handler(
        handle_doc_support_exit,
        lambda c: c.data == "ai_doc_support_exit",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_doc_support_followup,
        lambda c: (c.data or "").startswith("ai_doc_support_followup_"),
        state="*",
    )
    dp.register_message_handler(
        handle_doc_support_question,
        state=SupportStates.waiting_for_doc_question,
        content_types=types.ContentType.TEXT,
    )
