# -*- coding: utf-8 -*-
"""Post-payment UX copy: processing, receipt lines, Termin hints. Telegram HTML."""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _norm(lang: Optional[str]) -> str:
    l = (lang or "en").strip().lower()
    if l == "ua":
        l = "uk"
    return l if l in ("uk", "en", "de", "pl", "tr", "ar") else "en"


# Shown immediately before PDF generation (webhook + resend paths).
PDF_PROCESSING_MSG = {
    "uk": "⏳ <b>Обробляємо ваш документ...</b>",
    "ua": "⏳ <b>Обробляємо ваш документ...</b>",
    "en": "⏳ <b>Processing your document...</b>",
    "de": "⏳ <b>Ihr Dokument wird verarbeitet...</b>",
    "pl": "⏳ <b>Przetwarzamy Twój dokument...</b>",
    "tr": "⏳ <b>Belgeniz işleniyor...</b>",
    "ar": "⏳ <b>جارٍ معالجة مستندك...</b>",
}


def get_pdf_processing_message(lang: Optional[str]) -> str:
    l = _norm(lang)
    return PDF_PROCESSING_MSG.get(l, PDF_PROCESSING_MSG["en"])


# First line of webhook receipt caption (single PDF message after Stripe).
DOC_READY_TITLE_HTML = {
    "uk": "✅ <b>Ваш документ готовий</b>",
    "ua": "✅ <b>Ваш документ готовий</b>",
    "en": "✅ <b>Your document is ready</b>",
    "de": "✅ <b>Ihr Dokument ist fertig</b>",
    "pl": "✅ <b>Twój dokument jest gotowy</b>",
    "tr": "✅ <b>Belgeniz hazır</b>",
    "ar": "✅ <b>مستندك جاهز</b>",
}


def get_doc_ready_title_html(lang: Optional[str]) -> str:
    l = _norm(lang)
    return DOC_READY_TITLE_HTML.get(l, DOC_READY_TITLE_HTML["en"])


# Appended to webhook PDF caption (trust / support nudge).
POST_DELIVERY_SUPPORT_HTML = {
    "uk": "💬 <b>Якщо щось не так — напишіть нам</b> у підтримку.",
    "ua": "💬 <b>Якщо щось не так — напишіть нам</b> у підтримку.",
    "en": "💬 <b>If something is wrong — message us</b> in support.",
    "de": "💬 <b>Wenn etwas nicht stimmt — schreiben Sie uns</b> im Support.",
    "pl": "💬 <b>Jeśli coś jest nie tak — napisz do nas</b> w pomocy.",
    "tr": "💬 <b>Bir sorun varsa — bize yazın</b> (destek).",
    "ar": "💬 <b>إذا كان هناك خطأ ما — راسلنا</b> في الدعم.",
}


def get_post_delivery_support_html(lang: Optional[str]) -> str:
    l = _norm(lang)
    return POST_DELIVERY_SUPPORT_HTML.get(l, POST_DELIVERY_SUPPORT_HTML["en"])


# Shown under receipt when Termin CTA is available (caption, not a button).
TERMIN_ASK_LINE_HTML = {
    "uk": (
        "⚡ <b>Ми не записуємо вас напряму</b> — автоматично шукаємо вільні слоти.\n"
        "📅 <b>Потрібен запис на Termin?</b> Натисніть кнопку нижче."
    ),
    "ua": (
        "⚡ <b>Ми не записуємо вас напряму</b> — автоматично шукаємо вільні слоти.\n"
        "📅 <b>Потрібен запис на Termin?</b> Натисніть кнопку нижче."
    ),
    "en": (
        "⚡ <b>We don’t book you directly</b> — we automatically find open slots.\n"
        "📅 <b>Need an appointment (Termin)?</b> Use the button below."
    ),
    "de": (
        "⚡ <b>Wir buchen nicht direkt für Sie</b> — wir finden automatisch freie Termine.\n"
        "📅 <b>Brauchen Sie einen Termin?</b> Tippen Sie auf die Schaltfläche unten."
    ),
    "pl": (
        "⚡ <b>Nie rezerwujemy za Ciebie bezpośrednio</b> — automatycznie szukamy wolnych terminów.\n"
        "📅 <b>Potrzebujesz terminu?</b> Użyj przycisku poniżej."
    ),
    "tr": (
        "⚡ <b>Sizin adınıza doğrudan randevu almıyoruz</b> — boş slotları otomatik buluyoruz.\n"
        "📅 <b>Termin gerekiyor mu?</b> Aşağıdaki düğmeyi kullanın."
    ),
    "ar": (
        "⚡ <b>لا نحجز عنك مباشرة</b> — نبحث تلقائيًا عن المواعيد المتاحة.\n"
        "📅 <b>تحتاج موعدًا؟</b> استخدم الزر أدناه."
    ),
}


def get_termin_ask_line_html(lang: Optional[str]) -> str:
    l = _norm(lang)
    return TERMIN_ASK_LINE_HTML.get(l, TERMIN_ASK_LINE_HTML["en"])


# Shown briefly before Termin activation UI (webhook).
TERMIN_ACTIVATING_MSG = {
    "uk": "⏳ <b>Активуємо моніторинг...</b>",
    "ua": "⏳ <b>Активуємо моніторинг...</b>",
    "en": "⏳ <b>Activating monitoring...</b>",
    "de": "⏳ <b>Überwachung wird aktiviert...</b>",
    "pl": "⏳ <b>Aktywujemy monitoring...</b>",
    "tr": "⏳ <b>İzleme etkinleştiriliyor...</b>",
    "ar": "⏳ <b>جارٍ تفعيل المراقبة...</b>",
}


def get_termin_activating_message(lang: Optional[str]) -> str:
    l = _norm(lang)
    return TERMIN_ACTIVATING_MSG.get(l, TERMIN_ACTIVATING_MSG["en"])


# Fallback nudge ~2.5s after PDF delivery (Telegram hiccups).
PDF_FALLBACK_PROMPT_HTML = {
    "uk": (
        "📥 <b>Якщо документ не відкрився</b> — натисніть кнопку нижче.\n"
        "<i>(ми відправимо його ще раз)</i>"
    ),
    "ua": (
        "📥 <b>Якщо документ не відкрився</b> — натисніть кнопку нижче.\n"
        "<i>(ми відправимо його ще раз)</i>"
    ),
    "en": (
        "📥 <b>If the document didn’t open</b> — tap the button below.\n"
        "<i>(we’ll send the PDF again)</i>"
    ),
    "de": (
        "📥 <b>Wenn sich das Dokument nicht öffnet</b> — tippen Sie unten.\n"
        "<i>(Wir senden Ihr PDF erneut.)</i>"
    ),
    "pl": (
        "📥 <b>Jeśli dokument się nie otworzył</b> — użyj przycisku poniżej.\n"
        "<i>(Wyślemy PDF ponownie.)</i>"
    ),
    "tr": (
        "📥 <b>Belge açılmadıysa</b> — aşağıdaki düğmeye dokunun.\n"
        "<i>(PDF’yi tekrar göndeririz.)</i>"
    ),
    "ar": (
        "📥 <b>إذا لم يفتح المستند</b> — اضغط الزر أدناه.\n"
        "<i>(سنرسل ملف PDF مرة أخرى.)</i>"
    ),
}

PDF_RESEND_BTN = {
    "uk": "📥 Отримати PDF ще раз",
    "ua": "📥 Отримати PDF ще раз",
    "en": "📥 Get PDF again",
    "de": "📥 PDF erneut senden",
    "pl": "📥 Wyślij PDF ponownie",
    "tr": "📥 PDF'yi tekrar al",
    "ar": "📥 إرسال PDF مرة أخرى",
}


def get_pdf_fallback_prompt_html(lang: Optional[str]) -> str:
    l = _norm(lang)
    return PDF_FALLBACK_PROMPT_HTML.get(l, PDF_FALLBACK_PROMPT_HTML["en"])


def get_pdf_resend_button_label(lang: Optional[str]) -> str:
    l = _norm(lang)
    return PDF_RESEND_BTN.get(l, PDF_RESEND_BTN["en"])


# Second paragraph in Termin activation message (next step clarity).
TERMIN_ACTIVATION_NEXT_STEP = {
    "uk": "👉 <b>Далі:</b> ми повідомимо вас, щойно з’явиться вільний слот.",
    "ua": "👉 <b>Далі:</b> ми повідомимо вас, щойно з’явиться вільний слот.",
    "en": "👉 <b>Next:</b> we’ll notify you as soon as a slot opens.",
    "de": "👉 <b>Als Nächstes:</b> Wir benachrichtigen Sie, sobald ein Termin frei wird.",
    "pl": "👉 <b>Dalej:</b> powiadomimy Cię, gdy pojawi się wolny termin.",
    "tr": "👉 <b>Sonraki:</b> boş randevu çıkar çıkmaz haber vereceğiz.",
    "ar": "👉 <b>التالي:</b> سنُعلمك فور توفر موعد.",
}


def get_termin_activation_next_step(lang: Optional[str]) -> str:
    l = _norm(lang)
    return TERMIN_ACTIVATION_NEXT_STEP.get(l, TERMIN_ACTIVATION_NEXT_STEP["en"])


async def schedule_pdf_fallback_nudge(bot, user_id: int, order_id: int, lang: Optional[str]) -> None:
    """Send backup message + resend button ~2.5s after delivery (uses redownload_pdf: handler)."""
    await asyncio.sleep(2.6)
    try:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        _l = _norm(lang)
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                get_pdf_resend_button_label(_l),
                callback_data=f"redownload_pdf:{order_id}",
            )
        )
        await bot.send_message(
            chat_id=int(user_id),
            text=get_pdf_fallback_prompt_html(_l),
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception as _e:
        logger.debug("PDF_FALLBACK_NUDGE_FAILED order=%s err=%s", order_id, _e)
