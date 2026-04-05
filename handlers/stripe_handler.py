# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - Payment Handler (Stripe)
Single payment flow: Fill → Generate → Pay → Deliver
"""

import os
import json
import asyncio
import logging
from typing import Dict, Optional

from aiogram import types, Dispatcher, Bot
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config

# ---------------------------------------------------------------------------
# Contextual upsell after PDF delivery.
# Only doc_types that require a physical appointment get a Termin CTA button.
# Doc_types not listed here → no upsell message.
# ---------------------------------------------------------------------------
UPSELL_AFTER_DELIVERY: Dict[str, Dict[str, str]] = {
    "anmeldung": {"type": "termin", "authority": "buergeramt"},
    "ummeldung": {"type": "termin", "authority": "buergeramt"},
    "aufenthaltstitel": {"type": "termin", "authority": "auslaenderbehoerde"},
    "buergergeld": {"type": "termin", "authority": "jobcenter"},
}

_AUTHORITY_DISPLAY: Dict[str, str] = {
    "buergeramt": "Bürgeramt / Einwohnermeldeamt",
    "burgeramt": "Bürgeramt / Einwohnermeldeamt",  # legacy alias
    "auslaenderbehoerde": "Ausländerbehörde",
    "auslanderbehorde": "Ausländerbehörde",  # legacy alias
    "jobcenter": "Jobcenter",
}

# ---------------------------------------------------------------------------
# Post-payment menu: Termin button visibility matrix.
# Key   = doc_type (lowercase).
# Value = set of canonical city codes where the Termin scanner is active.
# Empty set  → button never shown for that doc type.
# Doc type absent → button never shown.
# ---------------------------------------------------------------------------
TERMIN_SUPPORTED: Dict[str, list] = {
    "anmeldung": ["berlin", "frankfurt", "koeln", "duesseldorf", "krefeld"],
    "ummeldung": ["berlin", "frankfurt", "koeln", "duesseldorf", "krefeld"],
    "aufenthaltstitel": ["berlin"],
    # buergergeld, abmeldung, wohngeld, kindergeld: Termin scan not yet active for these.
    # Entries with empty city lists removed — is_termin_supported() returns False automatically.
}

# ---------------------------------------------------------------------------
# Canonical aliases: any raw city string → canonical code used in TERMIN_SUPPORTED.
# Mirrors _resolve_city_code() from handlers/termin.py without the DB lookup.
# ---------------------------------------------------------------------------
_CITY_ALIASES: Dict[str, str] = {
    "berlin": "berlin",
    "frankfurt": "frankfurt",
    "frankfurt am main": "frankfurt",
    "frankfurt/main": "frankfurt",
    "köln": "koeln",
    "koeln": "koeln",
    "cologne": "koeln",
    "düsseldorf": "duesseldorf",
    "dusseldorf": "duesseldorf",
    "duesseldorf": "duesseldorf",
    "münchen": "muenchen",
    "munchen": "muenchen",
    "muenchen": "muenchen",
    "munich": "muenchen",
    "krefeld": "krefeld",
    "hamburg": "hamburg",
    "dortmund": "dortmund",
}


def _normalize_city(city: Optional[str]) -> str:
    """Return canonical city code (e.g. 'koeln') from any raw city string."""
    if not city:
        return ""
    return _CITY_ALIASES.get(city.strip().lower(), city.strip().lower())


def is_termin_supported(doc_type: Optional[str], city: Optional[str]) -> bool:
    """Return True iff the Termin scanner is active for this doc_type × city pair."""
    if not doc_type or not city:
        return False
    canonical_city = _normalize_city(city)
    if not canonical_city:
        return False
    supported_cities = TERMIN_SUPPORTED.get(doc_type.strip().lower(), [])
    return canonical_city in supported_cities


# Post-payment "what next?" header — localized with actionable steps
_WHAT_NEXT_TEXT: Dict[str, str] = {
    "uk": (
        "📋 <b>Що далі?</b>\n\n"
        "1. Натисніть <b>«Офіційна сторінка»</b> — перейдіть на урядовий сайт\n"
        "2. Роздрукуйте заповнений приклад (отримали вище)\n"
        "3. Запишіться в Bürgeramt та здайте документи\n\n"
        "⏱ Займе ~10–15 хвилин"
    ),
    "ua": (
        "📋 <b>Що далі?</b>\n\n"
        "1. Натисніть <b>«Офіційна сторінка»</b> — перейдіть на урядовий сайт\n"
        "2. Роздрукуйте заповнений приклад (отримали вище)\n"
        "3. Запишіться в Bürgeramt та здайте документи\n\n"
        "⏱ Займе ~10–15 хвилин"
    ),
    "en": (
        "📋 <b>What's next?</b>\n\n"
        "1. Tap <b>«Official page»</b> — visit the government website\n"
        "2. Print the filled example (received above)\n"
        "3. Book a Bürgeramt appointment and submit your documents\n\n"
        "⏱ Takes ~10–15 minutes"
    ),
    "de": (
        "📋 <b>Was kommt als nächstes?</b>\n\n"
        "1. Tippe auf <b>«Offizielle Seite»</b> — besuche die Regierungswebsite\n"
        "2. Drucke das ausgefüllte Beispiel aus (oben erhalten)\n"
        "3. Buche einen Bürgeramt-Termin und reiche die Unterlagen ein\n\n"
        "⏱ Dauert ca. 10–15 Minuten"
    ),
    "pl": (
        "📋 <b>Co dalej?</b>\n\n"
        "1. Naciśnij <b>«Oficjalna strona»</b> — przejdź na stronę rządową\n"
        "2. Wydrukuj wypełniony przykład (otrzymany powyżej)\n"
        "3. Umów wizytę w Bürgeramt i złóż dokumenty\n\n"
        "⏱ Zajmie ok. 10–15 minut"
    ),
    "tr": (
        "📋 <b>Sırada ne var?</b>\n\n"
        "1. <b>«Resmi sayfa»</b> butonuna dokun — resmi siteyi ziyaret et\n"
        "2. Yukarıda aldığın dolu örneği yazdır\n"
        "3. Bürgeramt randevusu al ve belgeleri teslim et\n\n"
        "⏱ Yaklaşık 10–15 dakika sürer"
    ),
    "ar": (
        "📋 <b>ما التالي؟</b>\n\n"
        "1. اضغط على <b>«الصفحة الرسمية»</b> — زُر الموقع الحكومي\n"
        "2. اطبع المثال المعبأ (الذي استلمته أعلاه)\n"
        "3. احجز موعداً في Bürgeramt وقدّم الوثائق\n\n"
        "⏱ يستغرق حوالي 10–15 دقيقة"
    ),
}

# Button labels — localized
_BTN_OFFICIAL_FORM: Dict[str, str] = {
    "uk": "📄 Офіційна сторінка",
    "ua": "📄 Офіційна сторінка",
    "en": "📄 Official page",
    "de": "📄 Offizielle Seite",
    "pl": "📄 Oficjalna strona",
    "tr": "📄 Resmi sayfa",
    "ar": "📄 الصفحة الرسمية",
}
_BTN_INSTRUCTIONS: Dict[str, str] = {
    "uk": "📘 Інструкція з подачі",
    "ua": "📘 Інструкція з подачі",
    "en": "📘 Submission instructions",
    "de": "📘 Einreichungsanleitung",
    "pl": "📘 Instrukcja składania",
    "tr": "📘 Başvuru talimatları",
    "ar": "📘 تعليمات التقديم",
}
_BTN_FIND_TERMIN: Dict[str, str] = {
    "uk": "🔎 Знайти запис",
    "ua": "🔎 Знайти запис",
    "en": "🔎 Find appointment",
    "de": "🔎 Termin finden",
    "pl": "🔎 Znajdź termin",
    "tr": "🔎 Randevu bul",
    "ar": "🔎 ابحث عن موعد",
}
_BTN_SHARE: Dict[str, str] = {
    "uk": "🔗 Поділитися",
    "ua": "🔗 Поділитися",
    "en": "🔗 Share",
    "de": "🔗 Teilen",
    "pl": "🔗 Udostępnij",
    "tr": "🔗 Paylaş",
    "ar": "🔗 مشاركة",
}
_BTN_DETAILS: Dict[str, str] = {
    "uk": "🌐 Як це працює",
    "ua": "🌐 Як це працює",
    "en": "🌐 How it works",
    "de": "🌐 Wie es funktioniert",
    "pl": "🌐 Jak to działa",
    "tr": "🌐 Nasıl çalışır",
    "ar": "🌐 كيف يعمل",
}
_BTN_MAIN_MENU: Dict[str, str] = {
    "uk": "🏠 Головне меню",
    "ua": "🏠 Головне меню",
    "en": "🏠 Main menu",
    "de": "🏠 Hauptmenü",
    "pl": "🏠 Menu główne",
    "tr": "🏠 Ana menü",
    "ar": "🏠 القائمة الرئيسية",
}
# Inline query text pre-filled when user taps "Share" — social proof framing drives more forwards
_SHARE_INLINE_QUERY: Dict[str, str] = {
    "uk": "Я використав цього бота для документів у Німеччині — зручно і без помилок 🇩🇪",
    "ua": "Я використав цього бота для документів у Німеччині — зручно і без помилок 🇩🇪",
    "en": "This bot fills German documents correctly so they get accepted the first time 🇩🇪",
    "de": "Dieser Bot hilft, deutsche Dokumente korrekt auszufüllen — beim ersten Versuch angenommen 🇩🇪",
    "pl": "Ten bot pomaga poprawnie wypełnić dokumenty do Niemiec — przyjęte za pierwszym razem 🇩🇪",
    "tr": "Bu bot Almanya belgelerini doğru doldurmana yardımcı oluyor — ilk seferde kabul edildi 🇩🇪",
    "ar": "هذا البوت يساعد على ملء وثائق ألمانيا بشكل صحيح — مقبولة من أول مرة 🇩🇪",
}
_BTN_SAMPLE_PDF: Dict[str, str] = {
    "uk": "👁 Подивись що саме ти отримаєш",
    "ua": "👁 Подивись що саме ти отримаєш",
    "en": "👁 See exactly what you'll get",
    "de": "👁 Sieh genau, was du bekommst",
    "pl": "👁 Zobacz dokładnie co otrzymasz",
    "tr": "👁 Ne alacağını tam olarak gör",
    "ar": "👁 اعرف بالضبط ما ستحصل عليه",
}
_BTN_WEBSITE: Dict[str, str] = {
    "uk": "🌐 Офіційний сайт",
    "ua": "🌐 Офіційний сайт",
    "en": "🌐 Official website",
    "de": "🌐 Offizielle Website",
    "pl": "🌐 Oficjalna strona",
    "tr": "🌐 Resmi site",
    "ar": "🌐 الموقع الرسمي",
}

# Shown when doc_type supports Termin but NOT for user's city → book manually
_TERMIN_CITY_NOT_SUPPORTED: Dict[str, str] = {
    "uk": "ℹ️ У вашому місті пошук недоступний\n👉 Запишіться на сайті Bürgeramt",
    "ua": "ℹ️ У вашому місті пошук недоступний\n👉 Запишіться на сайті Bürgeramt",
    "en": "ℹ️ Search not available in your city\n👉 Book on your Bürgeramt website",
    "de": "ℹ️ Suche in Ihrer Stadt nicht verfügbar\n👉 Buchen Sie auf der Website Ihres Bürgeramts",
    "pl": "ℹ️ Wyszukiwanie niedostępne w Twoim mieście\n👉 Zarezerwuj na stronie Bürgeramt",
    "tr": "ℹ️ Şehrinizde arama mevcut değil\n👉 Bürgeramt web sitesinden rezervasyon yapın",
    "ar": "ℹ️ البحث غير متاح في مدينتك\n👉 احجز على موقع Bürgeramt",
}

# Shown when doc_type does NOT need a Bürgeramt appointment at all
_TERMIN_NOT_NEEDED: Dict[str, str] = {
    "kindergeld": {
        "uk": "ℹ️ Подайте до Familienkasse (пошта або онлайн)\nЗапис не потрібен",
        "ua": "ℹ️ Подайте до Familienkasse (пошта або онлайн)\nЗапис не потрібен",
        "en": "ℹ️ Submit to Familienkasse (post or online)\nNo appointment needed",
        "de": "ℹ️ Einreichen bei der Familienkasse (Post oder online)\nKein Termin erforderlich",
        "pl": "ℹ️ Złóż w Familienkasse (poczta lub online)\nWizyta nie jest wymagana",
        "tr": "ℹ️ Familienkasse'ye gönderin (posta veya online)\nRandevu gerekmez",
        "ar": "ℹ️ قدّمه إلى Familienkasse (بريد أو إنترنت)\nلا حاجة لموعد",
    },
    "wohnungsgeberbestaetigung": {
        "uk": "ℹ️ Заповнює орендодавець\nВізьміть на Anmeldung",
        "ua": "ℹ️ Заповнює орендодавець\nВізьміть на Anmeldung",
        "en": "ℹ️ Filled out by your landlord\nBring it to your Anmeldung appointment",
        "de": "ℹ️ Vom Vermieter ausgefüllt\nZur Anmeldung mitbringen",
        "pl": "ℹ️ Wypełnia wynajmujący\nZabrać na Anmeldung",
        "tr": "ℹ️ Ev sahibi tarafından doldurulur\nAnmeldung randevusuna getirin",
        "ar": "ℹ️ يملأها صاحب العقار\nأحضرها إلى موعد Anmeldung",
    },
    "buergergeld": {
        "uk": "ℹ️ Подайте до Jobcenter\n👉 Через сайт або особисто",
        "ua": "ℹ️ Подайте до Jobcenter\n👉 Через сайт або особисто",
        "en": "ℹ️ Submit to Jobcenter\n👉 Online or in person",
        "de": "ℹ️ Beim Jobcenter einreichen\n👉 Online oder persönlich",
        "pl": "ℹ️ Złóż w Jobcenter\n👉 Online lub osobiście",
        "tr": "ℹ️ Jobcenter'a gönderin\n👉 Online veya şahsen",
        "ar": "ℹ️ قدّمه إلى Jobcenter\n👉 عبر الإنترنت أو شخصياً",
    },
    "abmeldung": {
        "uk": "ℹ️ Подайте до Bürgeramt (пошта або особисто)\nЗапис не потрібен",
        "ua": "ℹ️ Подайте до Bürgeramt (пошта або особисто)\nЗапис не потрібен",
        "en": "ℹ️ Submit to Bürgeramt (post or in person)\nNo prior appointment needed",
        "de": "ℹ️ Beim Bürgeramt einreichen (Post oder persönlich)\nKein Termin erforderlich",
        "pl": "ℹ️ Złóż w Bürgeramt (poczta lub osobiście)\nBez wcześniejszego zapisu",
        "tr": "ℹ️ Bürgeramt'a verin (posta veya şahsen)\nÖnceden randevu gerekmez",
        "ar": "ℹ️ قدّمه إلى Bürgeramt (بريد أو شخصياً)\nلا حاجة لموعد مسبق",
    },
    "wohngeld": {
        "uk": "ℹ️ Подайте до Wohngeldbehörde\nЗапишіться через сайт вашого міста",
        "ua": "ℹ️ Подайте до Wohngeldbehörde\nЗапишіться через сайт вашого міста",
        "en": "ℹ️ Submit to Wohngeldbehörde\nBook via your city's website",
        "de": "ℹ️ Bei der Wohngeldbehörde einreichen\nTermin über die Website Ihrer Stadt",
        "pl": "ℹ️ Złóż w Wohngeldbehörde\nUmów przez stronę swojego miasta",
        "tr": "ℹ️ Wohngeldbehörde'ye gönderin\nŞehrin sitesinden randevu alın",
        "ar": "ℹ️ قدّمه إلى Wohngeldbehörde\nاحجز عبر موقع مدينتك",
    },
}

# Generic fallback when doc_type has no specific explanation
_TERMIN_NOT_NEEDED_GENERIC: Dict[str, str] = {
    "uk": "ℹ️ Для цього документа запис не потрібен",
    "ua": "ℹ️ Для цього документа запис не потрібен",
    "en": "ℹ️ No appointment needed for this document",
    "de": "ℹ️ Kein Termin für dieses Dokument erforderlich",
    "pl": "ℹ️ Dla tego dokumentu wizyta nie jest wymagana",
    "tr": "ℹ️ Bu belge için randevu gerekmez",
    "ar": "ℹ️ لا حاجة لموعد لهذه الوثيقة",
}


def get_termin_hint(doc_type: Optional[str], city: Optional[str], lang: str) -> str:
    """Return a localized hint explaining why there is no Termin button.

    Three cases:
    1. is_termin_supported → no hint needed (button is shown)
    2. doc_type is in TERMIN_SUPPORTED (has cities list, even if empty) but city not covered
       → book manually on Bürgeramt site
    3. doc_type not in TERMIN_SUPPORTED at all → doc-specific explanation
    """
    if is_termin_supported(doc_type, city):
        return ""  # button is shown — no hint needed

    _l = "uk" if lang == "ua" else lang
    if _l not in _TERMIN_CITY_NOT_SUPPORTED:
        _l = "en"

    _dt = (doc_type or "").strip().lower()

    # Case 2: doc_type has a city list but this city is not in it
    if _dt in TERMIN_SUPPORTED and TERMIN_SUPPORTED[_dt]:
        return _TERMIN_CITY_NOT_SUPPORTED.get(_l, _TERMIN_CITY_NOT_SUPPORTED["en"])

    # Case 3: doc_type has no termin support (empty list or unknown)
    _specific = _TERMIN_NOT_NEEDED.get(_dt)
    if _specific:
        return _specific.get(_l, _specific.get("en", ""))

    return _TERMIN_NOT_NEEDED_GENERIC.get(_l, _TERMIN_NOT_NEEDED_GENERIC["en"])


def build_post_payment_menu(
    doc_type: Optional[str],
    city: Optional[str],
    lang: str,
) -> InlineKeyboardMarkup:
    """Build the post-payment inline menu.

    Always contains: Official form | Instructions
    Conditionally:   Find Termin  (only when is_termin_supported returns True)

    "Official form" opens the government URL directly (url= button) when a link
    exists for this doc_type — no extra tap required. Falls back to a callback
    that sends the link as a message when no direct URL is available.
    """
    _lang = "uk" if lang == "ua" else lang
    if _lang not in _BTN_OFFICIAL_FORM:
        _lang = "en"

    # Resolve official URL once — used to decide button type
    _official_url = ""
    try:
        from backend.document_config import get_official_link as _get_link

        _official_url = _get_link(doc_type or "") or ""
    except Exception:
        pass

    rows = []

    # Row 1: document-specific action buttons
    _official_btn_label = _BTN_OFFICIAL_FORM.get(_lang, _BTN_OFFICIAL_FORM["en"])
    if _official_url:
        # Direct URL — one tap opens government site immediately
        _official_btn = InlineKeyboardButton(_official_btn_label, url=_official_url)
    else:
        # Fallback: callback sends link as text message
        _official_btn = InlineKeyboardButton(
            _official_btn_label,
            callback_data=f"post_payment:official_form:{doc_type or 'unknown'}",
        )

    rows.append(
        [
            _official_btn,
            InlineKeyboardButton(
                _BTN_INSTRUCTIONS.get(_lang, _BTN_INSTRUCTIONS["en"]),
                callback_data=f"submission_guide:{doc_type or 'generic'}",
            ),
        ]
    )

    # Row 2 (conditional): Termin CTA
    if is_termin_supported(doc_type, city):
        rows.append(
            [
                InlineKeyboardButton(
                    _BTN_FIND_TERMIN.get(_lang, _BTN_FIND_TERMIN["en"]),
                    callback_data="termin_from_pdf",
                )
            ]
        )

    # Row 3: "What next?" — per-document FAQ (always shown)
    from backend.translations import ui as _ui_sth
    rows.append([
        InlineKeyboardButton(
            _ui_sth("what_next", _lang),
            callback_data=f"post_payment:what_next:{doc_type or 'unknown'}",
        )
    ])

    # Row 4: Share + Details buttons
    _SITE_URL = "https://termin-assist.de/"
    _share_url = ""
    try:
        from config import BOT_USERNAME as _bu
        _share_url = f"https://t.me/{_bu}"
    except Exception:
        pass

    _share_row = []
    if _share_url:
        _inline_query = _SHARE_INLINE_QUERY.get(_lang, _SHARE_INLINE_QUERY["en"])
        _share_row.append(
            InlineKeyboardButton(
                _BTN_SHARE.get(_lang, _BTN_SHARE["en"]),
                switch_inline_query=_inline_query,
            )
        )
    logger.info("BUTTON_URL=%s", _SITE_URL)
    logger.info("BUTTON_URL_CLICK=https://termin-assist.de/")
    _share_row.append(
        InlineKeyboardButton(
            _BTN_DETAILS.get(_lang, _BTN_DETAILS["en"]),
            url="https://termin-assist.de/",
        )
    )
    rows.append(_share_row)

    # Last row: Main menu — always shown so user is never left at a dead end
    rows.append([
        InlineKeyboardButton(
            _BTN_MAIN_MENU.get(_lang, _BTN_MAIN_MENU["en"]),
            callback_data="start",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


from states import DocumentState
from utils.helpers import get_user_lang, get_db, format_price

logger = logging.getLogger(__name__)

# ============================================================================
# FINAL DELIVERY CAPTION — single source of truth for ALL delivery paths
# ============================================================================
# Used by _deliver_document_inner (webhook) and deliver_document (resend).
# Contains: ready notice + data-check + email confirmation + 4 action steps.
# Telegram caption limit is 1024 chars — all entries are well within it.
FINAL_CAPTION_TEXTS: Dict[str, str] = {
    "uk": (
        "✅ <b>Ваш документ готовий</b>\n\n"
        "Наступний крок: роздрукуйте та здайте.\n\n"
        "✔️ Поля перевірені\n"
        "✔️ Формати коректні (дати, IBAN, адреса)\n"
        "✔️ Типові помилки усунені\n\n"
        "👉 Далі: запис на прийом"
    ),
    "ua": (
        "✅ <b>Ваш документ готовий</b>\n\n"
        "Наступний крок: роздрукуйте та здайте.\n\n"
        "✔️ Поля перевірені\n"
        "✔️ Формати коректні (дати, IBAN, адреса)\n"
        "✔️ Типові помилки усунені\n\n"
        "👉 Далі: запис на прийом"
    ),
    "en": (
        "✅ <b>Your document is ready</b>\n\n"
        "Next step: print it and submit.\n\n"
        "✔️ Fields verified\n"
        "✔️ Correct formats (dates, IBAN, address)\n"
        "✔️ Common mistakes removed\n\n"
        "👉 Next: book an appointment"
    ),
    "de": (
        "✅ <b>Ihr Dokument ist fertig</b>\n\n"
        "Nächster Schritt: ausdrucken und einreichen.\n\n"
        "✔️ Felder geprüft\n"
        "✔️ Korrekte Formate (Datum, IBAN, Adresse)\n"
        "✔️ Häufige Fehler beseitigt\n\n"
        "👉 Weiter: Termin buchen"
    ),
    "pl": (
        "✅ <b>Twój dokument jest gotowy</b>\n\n"
        "Następny krok: wydrukuj i złóż.\n\n"
        "✔️ Pola zweryfikowane\n"
        "✔️ Poprawne formaty (daty, IBAN, adres)\n"
        "✔️ Typowe błędy usunięte\n\n"
        "👉 Dalej: umów termin"
    ),
    "tr": (
        "✅ <b>Belgeniz hazır</b>\n\n"
        "Sonraki adım: yazdırın ve teslim edin.\n\n"
        "✔️ Alanlar doğrulandı\n"
        "✔️ Doğru formatlar (tarihler, IBAN, adres)\n"
        "✔️ Yaygın hatalar giderildi\n\n"
        "👉 Sonraki adım: randevu al"
    ),
    "ar": (
        "✅ <b>مستندك جاهز</b>\n\n"
        "الخطوة التالية: اطبعه وقدّمه.\n\n"
        "✔️ الحقول تم التحقق منها\n"
        "✔️ تنسيقات صحيحة (التواريخ، IBAN، العنوان)\n"
        "✔️ الأخطاء الشائعة أُزيلت\n\n"
        "👉 التالي: احجز موعدًا"
    ),
}

# Shown ONLY when is_termin_supported(doc_type, city) is True — prepended to caption.
# Guides user to the next concrete action (book an appointment) right after PDF delivery.
_NEXT_STEP_TERMIN: Dict[str, str] = {
    "uk": "📍 <b>Наступний крок: записатися на подачу</b>",
    "en": "📍 <b>Next step: book your appointment</b>",
    "de": "📍 <b>Nächster Schritt: Termin buchen</b>",
    "pl": "📍 <b>Następny krok: umów wizytę</b>",
    "tr": "📍 <b>Sonraki adım: randevu al</b>",
    "ar": "📍 <b>الخطوة التالية: احجز موعدك</b>",
}

# Bürgergeld-specific caption — merges the standard final caption with
# sign-reminder (page 8) and the ⚠️ unsigned-rejection warning so that
# ALL content is delivered in the single PDF message.
_BUERGERGELD_CAPTION_TEXTS: Dict[str, str] = {
    "uk": (
        "📄 Ваш документ готовий\n\n"
        "⚠️ <b>Важливо:</b>\n"
        "Це заповнений приклад — підпишіть на стор. 8 перед подачею.\n\n"
        "✔️ <b>Ми перевірили:</b>\n"
        "• Обов'язкові поля\n"
        "• Формати (дати, IBAN, адреса)\n"
        "• Типові помилки, через які відхиляють\n\n"
        "💡 <b>Результат:</b>\n"
        "Ви уникаєте затримок і повторних подач.\n\n"
        "⚠️ Без підпису заявку не приймуть."
    ),
    "ua": (
        "📄 Ваш документ готовий\n\n"
        "⚠️ <b>Важливо:</b>\n"
        "Це заповнений приклад — підпишіть на стор. 8 перед подачею.\n\n"
        "✔️ <b>Ми перевірили:</b>\n"
        "• Обов'язкові поля\n"
        "• Формати (дати, IBAN, адреса)\n"
        "• Типові помилки, через які відхиляють\n\n"
        "💡 <b>Результат:</b>\n"
        "Ви уникаєте затримок і повторних подач.\n\n"
        "⚠️ Без підпису заявку не приймуть."
    ),
    "en": (
        "📄 Your document is ready\n\n"
        "⚠️ <b>Important:</b>\n"
        "This is a filled example — sign on page 8 before submitting.\n\n"
        "✔️ <b>We checked:</b>\n"
        "• Required fields\n"
        "• Correct format (dates, IBAN, address)\n"
        "• Common mistakes that lead to rejection\n\n"
        "💡 <b>Result:</b>\n"
        "You avoid delays and repeated submissions.\n\n"
        "⚠️ Unsigned forms are automatically rejected."
    ),
    "de": (
        "📄 Ihr Dokument ist fertig\n\n"
        "⚠️ <b>Wichtig:</b>\n"
        "Dies ist ein ausgefülltes Beispiel — unterschreiben Sie auf Seite 8 vor der Einreichung.\n\n"
        "✔️ <b>Wir haben geprüft:</b>\n"
        "• Pflichtfelder\n"
        "• Format (Datum, IBAN, Adresse)\n"
        "• Häufige Fehler, die zur Ablehnung führen\n\n"
        "💡 <b>Ergebnis:</b>\n"
        "Sie vermeiden Verzögerungen und erneute Einreichungen.\n\n"
        "⚠️ Nicht unterschriebene Anträge werden automatisch abgelehnt."
    ),
    "pl": (
        "📄 Twój dokument jest gotowy\n\n"
        "⚠️ <b>Ważne:</b>\n"
        "To wypełniony przykład — podpisz na str. 8 przed złożeniem.\n\n"
        "✔️ <b>Sprawdziliśmy:</b>\n"
        "• Wymagane pola\n"
        "• Formaty (daty, IBAN, adres)\n"
        "• Typowe błędy prowadzące do odrzucenia\n\n"
        "💡 <b>Wynik:</b>\n"
        "Unikasz opóźnień i ponownych złożeń.\n\n"
        "⚠️ Niepodpisane wnioski są automatycznie odrzucane."
    ),
    "tr": (
        "📄 Belgeniz hazır\n\n"
        "⚠️ <b>Önemli:</b>\n"
        "Bu doldurulmuş bir örnek — göndermeden önce sayfa 8'i imzalayın.\n\n"
        "✔️ <b>Kontrol ettiklerimiz:</b>\n"
        "• Zorunlu alanlar\n"
        "• Formatlar (tarihler, IBAN, adres)\n"
        "• Reddedilmeye yol açan yaygın hatalar\n\n"
        "💡 <b>Sonuç:</b>\n"
        "Gecikmeleri ve tekrar başvuruları önlersiniz.\n\n"
        "⚠️ İmzasız başvurular otomatik olarak reddedilir."
    ),
    "ar": (
        "📄 مستندك جاهز\n\n"
        "⚠️ <b>مهم:</b>\n"
        "هذا مثال مملوء — وقّع في الصفحة 8 قبل التقديم.\n\n"
        "✔️ <b>ما تحققنا منه:</b>\n"
        "• الحقول المطلوبة\n"
        "• التنسيقات (التواريخ، IBAN، العنوان)\n"
        "• الأخطاء الشائعة التي تؤدي إلى الرفض\n\n"
        "💡 <b>النتيجة:</b>\n"
        "تتجنب التأخير وإعادة التقديم.\n\n"
        "⚠️ الطلبات غير الموقعة تُرفض تلقائيًا."
    ),
}
# ============================================================================
# BOT INSTANCE
# ============================================================================

_bot: Optional[Bot] = None


def set_bot(bot: Bot):
    global _bot
    _bot = bot


def get_bot() -> Bot:
    if _bot is None:
        raise RuntimeError("Bot instance not initialized")
    return _bot


# ============================================================================
# SAFE IMPORTS
# ============================================================================


def get_stripe_handler():
    try:
        from backend.stripe_handler import stripe_handler
    except ImportError:
        from stripe_handler import stripe_handler
    return stripe_handler


def get_analytics():
    try:
        from backend.analytics import AnalyticsTracker
    except ImportError:
        from analytics import AnalyticsTracker
    return AnalyticsTracker(get_db())


def get_document_config(doc_type: str):
    try:
        from backend.document_handlers import get_document_config
    except ImportError:
        from document_handlers import get_document_config
    return get_document_config(doc_type)


# ============================================================================
# IDEMPOTENCY & MESSAGE DEDUPLICATION (same order never processed twice / same message once)
# ============================================================================
import time

_payment_verification_locked = (
    {}
)  # order_id -> timestamp; guard so one order verified at a time
_last_payment_message = (
    {}
)  # order_id -> (message_key, timestamp); avoid duplicate "processing" spam
_PAYMENT_LOCK_SECONDS = 30
_MESSAGE_DEDUPE_SECONDS = 60


def _should_show_payment_message(order_id: int, message_key: str) -> bool:
    """Return True if we may send this message (not sent for this order in last N seconds)."""
    now = time.time()
    if order_id in _last_payment_message:
        key, ts = _last_payment_message[order_id]
        if key == message_key and (now - ts) < _MESSAGE_DEDUPE_SECONDS:
            return False
    _last_payment_message[order_id] = (message_key, now)
    return True


# ============================================================================
# PAYMENT — unified paywall: one button → Stripe Checkout
# ============================================================================

# Short trust block (2–3 lines) before the single pay button — localized; one term: "Filled Example"
PAYWALL_SHORT_BODY = {
    "uk": (
        "📄 <b>Не отримайте відмову через помилку в документі</b>\n\n"
        "Часта причина повернення — неправильний формат або пропущені поля.\n\n"
        "❌ <b>Без цього:</b>\n"
        "• Гадаєш, що і куди вписувати\n"
        "• Пропущені поля або невірний формат\n"
        "• Форма повертається — ще один похід в Amt\n\n"
        "✅ <b>З цим:</b>\n"
        "• Заповнений зразок — точно знаєш, що вписати\n"
        "• Правильний формат дат, адреси, IBAN\n"
        "• Подаєш впевнено з першого разу\n\n"
        "⏱ Займе ~4 хвилини"
    ),
    "ua": (
        "📄 <b>Не отримайте відмову через помилку в документі</b>\n\n"
        "Часта причина повернення — неправильний формат або пропущені поля.\n\n"
        "❌ <b>Без цього:</b>\n"
        "• Гадаєш, що і куди вписувати\n"
        "• Пропущені поля або невірний формат\n"
        "• Форма повертається — ще один похід в Amt\n\n"
        "✅ <b>З цим:</b>\n"
        "• Заповнений зразок — точно знаєш, що вписати\n"
        "• Правильний формат дат, адреси, IBAN\n"
        "• Подаєш впевнено з першого разу\n\n"
        "⏱ Займе ~4 хвилини"
    ),
    "en": (
        "📄 <b>Don't get rejected over a simple mistake</b>\n\n"
        "A common reason applications are returned: wrong format or missing fields.\n\n"
        "❌ <b>Without this:</b>\n"
        "• Guessing what to write in each field\n"
        "• Missing fields or wrong format\n"
        "• Form returned — another trip to the Amt\n\n"
        "✅ <b>With this:</b>\n"
        "• Filled reference — you know exactly what to write\n"
        "• Correct format for dates, address, IBAN\n"
        "• Submit confidently on the first try\n\n"
        "⏱ Takes ~4 minutes"
    ),
    "de": (
        "📄 <b>Kein Zurückweisen wegen Formfehler</b>\n\n"
        "Häufiger Grund für zurückgesandte Anträge: falsches Format oder fehlende Felder.\n\n"
        "❌ <b>Ohne das:</b>\n"
        "• Raten, was in welche Felder gehört\n"
        "• Fehlende Felder oder falsches Format\n"
        "• Formular zurück — nochmal ins Amt\n\n"
        "✅ <b>Damit:</b>\n"
        "• Ausgefülltes Muster — Sie wissen genau, was Sie eintragen\n"
        "• Korrektes Format für Datum, Adresse, IBAN\n"
        "• Beim ersten Mal sicher einreichen\n\n"
        "⏱ Dauert ~4 Minuten"
    ),
    "pl": (
        "📄 <b>Nie daj się odrzucić przez błąd w dokumentach</b>\n\n"
        "Częsty powód zwrotu wniosków: niepoprawny format lub brakujące pola.\n\n"
        "❌ <b>Bez tego:</b>\n"
        "• Zgadujesz, co wpisać w każde pole\n"
        "• Brakujące pola lub zły format\n"
        "• Wniosek zwrócony — kolejna wizyta w urzędzie\n\n"
        "✅ <b>Z tym:</b>\n"
        "• Wypełniony wzór — wiesz dokładnie, co wpisać\n"
        "• Poprawny format dat, adresu, IBAN\n"
        "• Składasz pewnie za pierwszym razem\n\n"
        "⏱ Zajmie ~4 minuty"
    ),
    "tr": (
        "📄 <b>Basit bir hata yüzünden reddedilmeyin</b>\n\n"
        "Başvuruların iade edilmesinin yaygın nedeni: yanlış format veya eksik alanlar.\n\n"
        "❌ <b>Bunu olmadan:</b>\n"
        "• Her alana ne yazacağını tahmin edersin\n"
        "• Eksik alanlar veya yanlış format\n"
        "• Form geri döner — kuruma tekrar gidilir\n\n"
        "✅ <b>Bununla:</b>\n"
        "• Doldurulmuş örnek — neyi nereye yazacağını tam bilirsin\n"
        "• Tarih, adres, IBAN için doğru format\n"
        "• İlk seferde güvenle teslim edersin\n\n"
        "⏱ ~4 dakika sürer"
    ),
    "ar": (
        "📄 <b>لا تتعرض للرفض بسبب خطأ بسيط في المستند</b>\n\n"
        "سبب شائع لإعادة الطلبات: تنسيق خاطئ أو حقول مفقودة.\n\n"
        "❌ <b>بدون هذا:</b>\n"
        "• تخمّن ما يجب كتابته في كل خانة\n"
        "• حقول مفقودة أو تنسيق خاطئ\n"
        "• الطلب يُعاد — رحلة أخرى للدائرة\n\n"
        "✅ <b>مع هذا:</b>\n"
        "• نموذج مرجعي مملوء — تعرف بالضبط ما تكتبه\n"
        "• تنسيق صحيح للتواريخ والعنوان وIBAN\n"
        "• تقدّم بثقة من المرة الأولى\n\n"
        "⏱ يستغرق ~4 دقائق"
    ),
}

# Pay button label with price placeholder — use .format(price=order["price"])
PAY_BUTTON_LABEL = {
    "uk": "✅ Отримати без помилок → €{price:.2f}",
    "ua": "✅ Отримати без помилок → €{price:.2f}",
    "en": "✅ Get it error-free → €{price:.2f}",
    "de": "✅ Fehlerfrei erhalten → €{price:.2f}",
    "pl": "✅ Pobierz bez błędów → €{price:.2f}",
    "tr": "✅ Hatasız al → €{price:.2f}",
    "ar": "✅ احصل عليه بلا أخطاء → €{price:.2f}",
}

# ============================================================================
# BUNDLE CHOICE (PDF only vs PDF + Termin)
# ============================================================================
BUNDLE_CHOICE_TEXT = {
    "uk": "💡 <b>Рекомендовано:</b> документ + моніторинг Termin",
    "ua": "💡 <b>Рекомендовано:</b> документ + моніторинг Termin",
    "en": "💡 <b>Recommended:</b> document + Termin monitoring",
    "de": "💡 <b>Empfohlen:</b> Dokument + Terminüberwachung",
    "pl": "💡 <b>Zalecane:</b> dokument + monitoring terminów",
    "tr": "💡 <b>Önerilen:</b> belge + Termin takibi",
    "ar": "💡 <b>موصى به:</b> المستند + مراقبة Termin",
}
BUNDLE_BTN_PDF_ONLY = {
    "uk": "📄 Тільки документ — €{price:.2f}",
    "ua": "📄 Тільки документ — €{price:.2f}",
    "en": "📄 Document only — €{price:.2f}",
    "de": "📄 Nur Dokument — €{price:.2f}",
    "pl": "📄 Tylko dokument — €{price:.2f}",
    "tr": "📄 Yalnızca belge — €{price:.2f}",
    "ar": "📄 المستند فقط — €{price:.2f}",
}
BUNDLE_BTN_WITH_TERMIN = {
    "uk": "🔥 Документ + Termin (найкраще) — €{price:.2f}",
    "ua": "🔥 Документ + Termin (найкраще) — €{price:.2f}",
    "en": "🔥 Document + Termin (best value) — €{price:.2f}",
    "de": "🔥 Dokument + Termin (bestes Angebot) — €{price:.2f}",
    "pl": "🔥 Dokument + Termin (najlepsza wartość) — €{price:.2f}",
    "tr": "🔥 Belge + Termin (en iyi değer) — €{price:.2f}",
    "ar": "🔥 المستند + Termin (أفضل قيمة) — €{price:.2f}",
}

# ============================================================================
# DISCLAIMER SCREEN — shown between bundle choice and Stripe checkout
# ============================================================================

DISCLAIMER_TEXT = {
    "uk": (
        "✅ <b>Що саме ви отримаєте</b>\n\n"
        "Заповнений зразок документа на основі ваших відповідей — "
        "готовий для самостійного подання до Bürgeramt.\n\n"
        "ℹ️ <b>Прозорість:</b> ми — незалежний сервіс, не державний орган. "
        "Зразок допомагає заповнити офіційну форму правильно з першого разу.\n\n"
        "✅ Підтвердіть, щоб продовжити."
    ),
    "en": (
        "✅ <b>What you will receive</b>\n\n"
        "A filled example of your document based on your answers — "
        "ready for you to submit to the Bürgeramt yourself.\n\n"
        "ℹ️ <b>Transparency:</b> we are an independent service, not a government authority. "
        "The example helps you fill the official form correctly the first time.\n\n"
        "✅ Confirm to continue."
    ),
    "de": (
        "✅ <b>Was Sie erhalten</b>\n\n"
        "Ein ausgefülltes Beispiel Ihres Dokuments auf Basis Ihrer Angaben — "
        "bereit zur Einreichung beim Bürgeramt.\n\n"
        "ℹ️ <b>Transparenz:</b> wir sind ein unabhängiger Dienst, keine Behörde. "
        "Das Beispiel hilft Ihnen, das offizielle Formular beim ersten Versuch richtig auszufüllen.\n\n"
        "✅ Bestätigen, um fortzufahren."
    ),
    "pl": (
        "✅ <b>Co otrzymasz</b>\n\n"
        "Wypełniony wzór dokumentu na podstawie Twoich odpowiedzi — "
        "gotowy do złożenia w urzędzie.\n\n"
        "ℹ️ <b>Przejrzystość:</b> jesteśmy niezależnym serwisem, nie organem państwowym. "
        "Wzór pomaga prawidłowo wypełnić oficjalny formularz za pierwszym razem.\n\n"
        "✅ Potwierdź, aby kontynuować."
    ),
    "tr": (
        "✅ <b>Ne alacaksınız</b>\n\n"
        "Cevaplarınıza göre doldurulmuş bir belge örneği — "
        "Bürgeramt'a kendiniz teslim etmeye hazır.\n\n"
        "ℹ️ <b>Şeffaflık:</b> biz bağımsız bir hizmetiz, resmi bir kurum değiliz. "
        "Örnek, resmi formu ilk seferinde doğru doldurmanıza yardımcı olur.\n\n"
        "✅ Devam etmek için onaylayın."
    ),
    "ar": (
        "✅ <b>ما ستحصل عليه</b>\n\n"
        "مثال مملوء للمستند بناءً على إجاباتك — "
        "جاهز لتقديمه بنفسك إلى Bürgeramt.\n\n"
        "ℹ️ <b>الشفافية:</b> نحن خدمة مستقلة، لسنا جهة حكومية. "
        "المثال يساعدك على ملء النموذج الرسمي بشكل صحيح من المرة الأولى.\n\n"
        "✅ أكّد للمتابعة."
    ),
}

DISCLAIMER_BTN_CONFIRM = {
    "uk": "✅ Я розумію — продовжити",
    "en": "✅ I understand — continue",
    "de": "✅ Ich verstehe — weiter",
    "pl": "✅ Rozumiem — kontynuuj",
    "tr": "✅ Anlıyorum — devam et",
    "ar": "✅ أفهم — المتابعة",
}

DISCLAIMER_BTN_CANCEL = {
    "uk": "← Назад",
    "en": "← Back",
    "de": "← Zurück",
    "pl": "← Wstecz",
    "tr": "← Geri",
    "ar": "← رجوع",
}


def _paywall_lang(order: dict, user_id: int) -> str:
    lang = (order or {}).get("lang") or get_user_lang(user_id)
    return (lang or "en").strip().lower()


# ============================================================================
# PROMO CODE — waiting state (user_id → order_id, timestamp)
# ============================================================================
import time as _time

_PROMO_WAITING: Dict[int, Dict] = {}  # {user_id: {order_id, ts, lang}}

_BTN_PROMO: Dict[str, str] = {
    "uk": "🏷 Ввести промокод",
    "ua": "🏷 Ввести промокод",
    "en": "🏷 Have a promo code?",
    "de": "🏷 Gutscheincode eingeben",
    "pl": "🏷 Mam kod promocyjny",
    "tr": "🏷 Promosyon kodum var",
    "ar": "🏷 لديّ رمز ترويجي",
}

_PROMO_ASK: Dict[str, str] = {
    "uk": "✏️ Введіть ваш промокод:",
    "ua": "✏️ Введіть ваш промокод:",
    "en": "✏️ Please type your promo code:",
    "de": "✏️ Bitte geben Sie Ihren Gutscheincode ein:",
    "pl": "✏️ Wpisz swój kod promocyjny:",
    "tr": "✏️ Promosyon kodunuzu girin:",
    "ar": "✏️ أدخل الرمز الترويجي:",
}

_PROMO_VALID: Dict[str, str] = {
    "uk": "✅ Промокод застосовано!\n\n🏷 <b>{code}</b> — знижка {discount}€\n💶 Нова ціна: <b>{new_price}€</b>",
    "ua": "✅ Промокод застосовано!\n\n🏷 <b>{code}</b> — знижка {discount}€\n💶 Нова ціна: <b>{new_price}€</b>",
    "en": "✅ Promo code applied!\n\n🏷 <b>{code}</b> — discount {discount}€\n💶 New price: <b>{new_price}€</b>",
    "de": "✅ Gutscheincode angewendet!\n\n🏷 <b>{code}</b> — Rabatt {discount}€\n💶 Neuer Preis: <b>{new_price}€</b>",
    "pl": "✅ Kod promocyjny zastosowany!\n\n🏷 <b>{code}</b> — zniżka {discount}€\n💶 Nowa cena: <b>{new_price}€</b>",
    "tr": "✅ Promosyon kodu uygulandı!\n\n🏷 <b>{code}</b> — indirim {discount}€\n💶 Yeni fiyat: <b>{new_price}€</b>",
    "ar": "✅ تم تطبيق رمز الترويج!\n\n🏷 <b>{code}</b> — خصم {discount}€\n💶 السعر الجديد: <b>{new_price}€</b>",
}

_PROMO_INVALID: Dict[str, str] = {
    "uk": "❌ {reason}\n\nВведіть інший код або продовжіть без знижки.",
    "ua": "❌ {reason}\n\nВведіть інший код або продовжіть без знижки.",
    "en": "❌ {reason}\n\nEnter another code or continue without discount.",
    "de": "❌ {reason}\n\nGeben Sie einen anderen Code ein oder fahren Sie ohne Rabatt fort.",
    "pl": "❌ {reason}\n\nWprowadź inny kod lub kontynuuj bez zniżki.",
    "tr": "❌ {reason}\n\nBaşka bir kod girin veya indirimsiz devam edin.",
    "ar": "❌ {reason}\n\nأدخل رمزاً آخر أو تابع بدون خصم.",
}


async def handle_promo_input(callback_query: types.CallbackQuery, state: FSMContext):
    """User tapped '🏷 Promo code' — set FSM state and ask for the code."""
    await callback_query.answer()
    data = callback_query.data or ""
    # callback: promo_input_{order_id}
    try:
        order_id = int(data.split("_")[-1])
    except (ValueError, IndexError):
        return

    user_id = callback_query.from_user.id
    db = get_db()
    order = db.get_order(order_id)
    if not order or order["user_id"] != user_id:
        return

    lang = _paywall_lang(order, user_id)
    _PROMO_WAITING[user_id] = {"order_id": order_id, "ts": _time.monotonic(), "lang": lang}
    await state.set_state(DocumentState.waiting_promo)

    from aiogram.types import ForceReply
    await callback_query.message.answer(
        _PROMO_ASK.get(lang, _PROMO_ASK["en"]),
        reply_markup=ForceReply(selective=True),
    )


async def process_promo_code(message: types.Message, state: FSMContext):
    """User typed a promo code while in waiting_promo state."""
    user_id = message.from_user.id
    ctx = _PROMO_WAITING.pop(user_id, None)
    await state.finish()

    if not ctx:
        return

    # Expire waiting context after 10 min
    if _time.monotonic() - ctx.get("ts", 0) > 600:
        return

    order_id = ctx["order_id"]
    lang = ctx.get("lang", "en")
    code = (message.text or "").strip().upper()

    db = get_db()
    order = db.get_order(order_id)
    if not order or order["user_id"] != user_id:
        return

    try:
        from backend.pricing import PricingManager
        import os as _os
        _pm = PricingManager(db_path=_os.getenv("DB_PATH", "users.db"))
        result = _pm.validate_promo_code(
            code=code,
            user_id=user_id,
            doc_type=order.get("doc_type"),
            order_amount=float(order.get("price", 0)),
        )
    except Exception as _pe:
        logger.warning("process_promo_code: validation error user=%s code=%s err=%s", user_id, code, _pe)
        await message.answer(_PROMO_INVALID.get(lang, _PROMO_INVALID["en"]).format(reason="Validation error"))
        return

    if not result.get("valid"):
        reason = result.get("message", "Invalid promo code")
        await message.answer(
            _PROMO_INVALID.get(lang, _PROMO_INVALID["en"]).format(reason=reason),
            parse_mode="HTML",
        )
        return

    discount = round(float(result.get("discount", 0)), 2)
    promo_id = result.get("promo_id")
    old_price = float(order.get("price", 0))
    new_price = max(0.50, round(old_price - discount, 2))  # minimum 0.50 EUR

    # Step 1: Update order price in DB — this is the price Stripe will charge
    try:
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE orders SET discount = ?, promo_code = ?, price = ? WHERE id = ?",
            (discount, code, new_price, order_id),
        )
        db.conn.commit()
    except Exception as _dbe:
        logger.error("process_promo_code: DB update failed user=%s err=%s", user_id, _dbe)
        await message.answer(_PROMO_INVALID.get(lang, _PROMO_INVALID["en"]).format(reason="DB error"))
        return

    # Step 2: Record usage immediately — prevents the same code being reused
    # before payment completes (Stripe session is created with already-discounted price).
    if promo_id:
        try:
            from backend.pricing import PricingManager
            import os as _os
            _pm = PricingManager(db_path=_os.getenv("DB_PATH", "users.db"))
            _pm.apply_promo_code(
                promo_id=promo_id,
                user_id=user_id,
                order_id=order_id,
                discount_amount=discount,
            )
            logger.info(
                "PROMO_USAGE_RECORDED: user=%s order=%s code=%s discount=%.2f new_price=%.2f",
                user_id, order_id, code, discount, new_price,
            )
        except Exception as _ue:
            # Non-fatal — price is already updated; usage tracking failure should not block payment
            logger.warning("process_promo_code: usage record failed user=%s err=%s", user_id, _ue)

    # Confirm to user — then show updated pay button
    bundle_addon = float(os.environ.get("TERMIN_BUNDLE_ADDON_EUR", "3.00"))
    bundle_price = new_price + bundle_addon

    btn_pdf = BUNDLE_BTN_PDF_ONLY.get(lang, BUNDLE_BTN_PDF_ONLY["en"]).format(price=new_price)
    btn_bnd = BUNDLE_BTN_WITH_TERMIN.get(lang, BUNDLE_BTN_WITH_TERMIN["en"]).format(price=bundle_price)

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(btn_pdf, callback_data=f"paypdf_{order_id}"),
        types.InlineKeyboardButton(btn_bnd, callback_data=f"paybundle_{order_id}"),
    )

    await message.answer(
        _PROMO_VALID.get(lang, _PROMO_VALID["en"]).format(
            code=code, discount=discount, new_price=new_price
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def initiate_payment(callback_query: types.CallbackQuery):
    """
    Unified payment handler for 7 callback prefixes:
      pay_{id}                 → show bundle choice (2 buttons)
      paydisclaim_pdf_{id}     → show disclaimer screen (PDF)
      paydisclaim_bundle_{id}  → show disclaimer screen (bundle)
      paypdf_{id}              → Stripe checkout, PDF only
      paybundle_{id}           → Stripe checkout, PDF + Termin bundle
      payconfirm_pdf_{id}      → Stripe checkout after user confirmed warnings (PDF only)
      payconfirm_bundle_{id}   → Stripe checkout after user confirmed warnings (bundle)
    """
    await callback_query.answer()
    from backend.database import OrderStatus

    data = callback_query.data or ""

    # FUNNEL POINT 3: pay button tapped
    logger.info(
        "FUNNEL | step=pay_tapped user_id=%s callback=%s",
        callback_query.from_user.id,
        data[:30],
    )

    # --- Detect guard skip (user confirmed despite warnings) ---
    skip_warnings = data.startswith("payconfirm_")

    # --- Determine mode from callback prefix ---
    is_bundle = None  # None = show choice screen
    if data.startswith("paybundle_") or data.startswith("payconfirm_bundle_"):
        is_bundle = True
    elif data.startswith("paypdf_") or data.startswith("payconfirm_pdf_"):
        is_bundle = False
    elif data.startswith("paydisclaim_"):
        is_bundle = "disclaim"  # special marker — handled in STEP 1b
    # else: pay_{id} → choice screen

    # Use last segment: works for pay_123, paypdf_123, and payconfirm_pdf_123
    order_id = int(data.split("_")[-1])
    user_id = callback_query.from_user.id

    db = get_db()
    order = db.get_order(order_id)

    if not order or order["user_id"] != user_id:
        _fb_lang = get_user_lang(user_id) or "en"
        _order_not_found = {
            "uk": "❌ Замовлення не знайдено.\n\nПочніть нове замовлення через головне меню.",
            "en": "❌ Order not found.\n\nPlease start a new order from the main menu.",
            "de": "❌ Bestellung nicht gefunden.\n\nBitte starten Sie eine neue Bestellung.",
            "pl": "❌ Zamówienie nie znalezione.\n\nRozpocznij nowe zamówienie z menu głównego.",
            "tr": "❌ Sipariş bulunamadı.\n\nLütfen ana menüden yeni bir sipariş başlatın.",
            "ar": "❌ الطلب غير موجود.\n\nيرجى بدء طلب جديد من القائمة الرئيسية.",
        }
        await callback_query.message.answer(
            _order_not_found.get(_fb_lang, _order_not_found["en"])
        )
        return

    # Idempotency: same order must never create new checkout if already paid or in progress
    if order.get("status") in (
        OrderStatus.PAID.value,
        OrderStatus.SENT.value,
        OrderStatus.DOWNLOADED.value,
    ):
        try:
            await deliver_document(callback_query.message, order_id, user_id)
        except Exception as _del_err:
            logger.exception(
                "REDELIVER_FAILED order_id=%s user_id=%s: %s",
                order_id,
                user_id,
                _del_err,
            )
            _fb_lang = _paywall_lang(order, user_id)
            _redeliver_err = {
                "uk": "❌ Не вдалося надіслати PDF. Спробуйте ще раз — натисніть кнопку нижче.",
                "en": "❌ Failed to send your PDF. Please tap the button again.",
                "de": "❌ PDF konnte nicht gesendet werden. Bitte erneut versuchen.",
                "pl": "❌ Nie udało się wysłać PDF. Spróbuj ponownie.",
                "tr": "❌ PDF gönderilemedi. Lütfen tekrar deneyin.",
                "ar": "❌ فشل إرسال ملف PDF. يرجى المحاولة مرة أخرى.",
            }
            await callback_query.message.answer(
                _redeliver_err.get(_fb_lang, _redeliver_err["en"])
            )
        return
    if order.get("status") == OrderStatus.PROCESSING.value:
        return

    lang = _paywall_lang(order, user_id)
    pdf_price = order.get("price", 0)
    bundle_addon = float(os.environ.get("TERMIN_BUNDLE_ADDON_EUR", "3.00"))
    bundle_price = pdf_price + bundle_addon

    # ===================== STEP 1: BUNDLE CHOICE SCREEN =====================
    if is_bundle is None:  # pay_{id}
        body = PAYWALL_SHORT_BODY.get(lang, PAYWALL_SHORT_BODY.get("en", ""))
        choice = BUNDLE_CHOICE_TEXT.get(lang, BUNDLE_CHOICE_TEXT.get("en", ""))

        btn_pdf = BUNDLE_BTN_PDF_ONLY.get(lang, BUNDLE_BTN_PDF_ONLY["en"]).format(
            price=pdf_price
        )
        btn_bnd = BUNDLE_BTN_WITH_TERMIN.get(lang, BUNDLE_BTN_WITH_TERMIN["en"]).format(
            price=bundle_price
        )

        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton(btn_pdf, callback_data=f"paypdf_{order_id}"),
            types.InlineKeyboardButton(btn_bnd, callback_data=f"paybundle_{order_id}"),
        )
        # Sample PDF preview — "try before you buy" moment
        _doc_type_for_preview = order.get("doc_type") or "unknown"
        keyboard.add(
            types.InlineKeyboardButton(
                _BTN_SAMPLE_PDF.get(lang, _BTN_SAMPLE_PDF["en"]),
                callback_data=f"sample_preview:{_doc_type_for_preview}",
            )
        )
        # Show promo button only if no promo already applied
        if not order.get("promo_code"):
            keyboard.add(
                types.InlineKeyboardButton(
                    _BTN_PROMO.get(lang, _BTN_PROMO["en"]),
                    callback_data=f"promo_input_{order_id}",
                )
            )

        await callback_query.message.edit_text(
            f"{body}\n\n{choice}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    # ===================== STEP 1b: DISCLAIMER SCREEN =====================
    # Triggered by paydisclaim_pdf_ or paydisclaim_bundle_ callbacks.
    # Shows legal disclaimer + confirm checkbox before proceeding to Stripe.
    if is_bundle == "disclaim":
        _disclaim_is_bundle = data.startswith("paydisclaim_bundle_")
        _next_cb = (
            f"paybundle_{order_id}" if _disclaim_is_bundle else f"paypdf_{order_id}"
        )

        _disc_text = DISCLAIMER_TEXT.get(lang, DISCLAIMER_TEXT["en"])
        _btn_confirm = DISCLAIMER_BTN_CONFIRM.get(lang, DISCLAIMER_BTN_CONFIRM["en"])
        _btn_back = DISCLAIMER_BTN_CANCEL.get(lang, DISCLAIMER_BTN_CANCEL["en"])

        _disc_kb = types.InlineKeyboardMarkup(row_width=1)
        _disc_kb.add(
            types.InlineKeyboardButton(_btn_confirm, callback_data=_next_cb),
            types.InlineKeyboardButton(_btn_back, callback_data=f"pay_{order_id}"),
        )
        await callback_query.message.edit_text(
            _disc_text,
            parse_mode="HTML",
            reply_markup=_disc_kb,
        )
        return

    # ===================== GUARD — Server-side validation before Stripe =====================
    # Runs in STEP 2 only (is_bundle is not None).
    # Critical errors always block. Warnings block unless user already confirmed (skip_warnings).
    try:
        from backend.utils.normalize import normalize_user_data as _normalize
        from backend.utils.validate import (
            validate_user_data as _validate,
            format_validation_error as _fmt_err,
        )

        _doc_type = (order.get("doc_type") or "").strip().lower()
        _raw = order.get("user_data")
        if isinstance(_raw, dict):
            _guard_data = _raw
        else:
            try:
                _guard_data = json.loads(_raw or "{}")
            except Exception:
                _guard_data = {}

        _norm_data = _normalize(_guard_data)
        _ok, _missing, _warnings = _validate(_doc_type, _norm_data, lang)

        # --- CRITICAL block (always enforced, even after payconfirm_) ---
        if not _ok:
            _err_text = _fmt_err(_doc_type, _missing, lang)
            _edit_btn = {
                "uk": "🔧 Виправити анкету",
                "en": "🔧 Edit answers",
                "de": "🔧 Antworten bearbeiten",
                "pl": "🔧 Popraw ankietę",
                "tr": "🔧 Formu düzenle",
                "ar": "🔧 تعديل الإجابات",
            }
            _menu_btn = {
                "uk": "🏠 Головне меню",
                "en": "🏠 Main menu",
                "de": "🏠 Hauptmenü",
                "pl": "🏠 Menu główne",
                "tr": "🏠 Ana menü",
                "ar": "🏠 القائمة الرئيسية",
            }
            _kb = InlineKeyboardMarkup(row_width=1)
            _kb.add(
                InlineKeyboardButton(
                    _edit_btn.get(lang, _edit_btn["en"]), callback_data="edit_answers"
                ),
                InlineKeyboardButton(
                    _menu_btn.get(lang, _menu_btn["en"]),
                    callback_data="main_menu",
                ),
            )
            await callback_query.message.answer(
                _err_text, parse_mode="HTML", reply_markup=_kb
            )
            logger.warning(
                "GUARD_BLOCKED | user_id=%s order_id=%s doc=%s missing=%s",
                user_id,
                order_id,
                _doc_type,
                [m["key"] for m in _missing],
            )
            return

        # --- WARNING screen (only if user has not yet confirmed) ---
        if _warnings and not skip_warnings:
            _warn_intro = {
                "uk": "⚠️ Деякі рекомендовані поля відсутні:",
                "en": "⚠️ Some recommended fields are missing:",
                "de": "⚠️ Einige empfohlene Felder fehlen:",
                "pl": "⚠️ Brakuje kilku zalecanych pól:",
                "tr": "⚠️ Bazı önerilen alanlar eksik:",
                "ar": "⚠️ بعض الحقول الموصى بها مفقودة:",
            }
            _warn_lines = "\n".join(f"• {w['label']}" for w in _warnings)
            _warn_text = f"{_warn_intro.get(lang, _warn_intro['en'])}\n{_warn_lines}"
            _confirm_prefix = "payconfirm_bundle_" if is_bundle else "payconfirm_pdf_"
            _continue_btn = {
                "uk": "✅ Продовжити до оплати",
                "en": "✅ Continue to payment",
                "de": "✅ Weiter zur Zahlung",
                "pl": "✅ Przejdź do płatności",
                "tr": "✅ Ödemeye devam et",
                "ar": "✅ المتابعة إلى الدفع",
            }
            _edit_btn = {
                "uk": "🔧 Виправити анкету",
                "en": "🔧 Edit answers",
                "de": "🔧 Antworten bearbeiten",
                "pl": "🔧 Popraw ankietę",
                "tr": "🔧 Formu düzenle",
                "ar": "🔧 تعديل الإجابات",
            }
            _menu_btn = {
                "uk": "🏠 Головне меню",
                "en": "🏠 Main menu",
                "de": "🏠 Hauptmenü",
                "pl": "🏠 Menu główne",
                "tr": "🏠 Ana menü",
                "ar": "🏠 القائمة الرئيسية",
            }
            _kb = InlineKeyboardMarkup(row_width=1)
            _kb.add(
                InlineKeyboardButton(
                    _continue_btn.get(lang, _continue_btn["en"]),
                    callback_data=f"{_confirm_prefix}{order_id}",
                ),
                InlineKeyboardButton(
                    _edit_btn.get(lang, _edit_btn["en"]), callback_data="edit_answers"
                ),
                InlineKeyboardButton(
                    _menu_btn.get(lang, _menu_btn["en"]),
                    callback_data="main_menu",
                ),
            )
            await callback_query.message.answer(
                _warn_text, parse_mode="HTML", reply_markup=_kb
            )
            logger.info(
                "GUARD_WARNING | user_id=%s order_id=%s doc=%s warnings=%s",
                user_id,
                order_id,
                _doc_type,
                [w["key"] for w in _warnings],
            )
            return

        # --- Layer 3: Anmeldung strict validation (mirrors create_final_pdf logic) ---
        if _doc_type == "anmeldung":
            try:
                from backend.validators import (
                    normalize_and_validate_anmeldung as _anm_validate,
                )

                _anm_norm, _anm_errors = _anm_validate(_norm_data)

                if _anm_errors:
                    logger.warning(
                        "GUARD_L3_BLOCKED | user_id=%s order_id=%s anmeldung_errors=%s",
                        user_id,
                        order_id,
                        _anm_errors,
                    )
                    _anm_field_labels = {
                        "street": {
                            "uk": "Вулиця",
                            "en": "Street",
                            "de": "Straße",
                            "pl": "Ulica",
                            "tr": "Sokak",
                            "ar": "الشارع",
                        },
                        "plz": {
                            "uk": "Поштовий індекс",
                            "en": "Postal code",
                            "de": "Postleitzahl",
                            "pl": "Kod pocztowy",
                            "tr": "Posta kodu",
                            "ar": "الرمز البريدي",
                        },
                        "move_in_date": {
                            "uk": "Дата в'їзду",
                            "en": "Move-in date",
                            "de": "Einzugsdatum",
                            "pl": "Data wprowadzenia",
                            "tr": "Taşınma tarihi",
                            "ar": "تاريخ الانتقال",
                        },
                        "birth_date": {
                            "uk": "Дата народження",
                            "en": "Date of birth",
                            "de": "Geburtsdatum",
                            "pl": "Data urodzenia",
                            "tr": "Doğum tarihi",
                            "ar": "تاريخ الميلاد",
                        },
                    }
                    _anm_msg_hint = {
                        "latin_only": {
                            "uk": "лише латинські символи або German умляути",
                            "en": "Latin characters and German umlauts only",
                            "de": "Nur lateinische Zeichen und Umlaute",
                            "pl": "Tylko znaki łacińskie i niemieckie umlauts",
                            "tr": "Yalnızca Latin karakterler ve Alman ünlüler",
                            "ar": "أحرف لاتينية وحروف ألمانية فقط",
                        },
                    }
                    _error_intro = {
                        "uk": "❌ Будь ласка, виправте наступні поля перед оплатою:",
                        "en": "❌ Please correct the following fields before payment:",
                        "de": "❌ Bitte korrigieren Sie folgende Felder vor der Zahlung:",
                        "pl": "❌ Przed płatnością popraw następujące pola:",
                        "tr": "❌ Ödeme yapmadan önce şu alanları düzeltin:",
                        "ar": "❌ يرجى تصحيح الحقول التالية قبل الدفع:",
                    }
                    _lines = []
                    for _ae in _anm_errors:
                        _fkey = _ae.get("field", "")
                        _fmsg = _ae.get("message", "")
                        _flabel = (
                            _anm_field_labels.get(_fkey, {}).get(lang)
                            or _anm_field_labels.get(_fkey, {}).get("en")
                            or _fkey
                        )
                        _fhint = (
                            _anm_msg_hint.get(_fmsg, {}).get(lang)
                            or _anm_msg_hint.get(_fmsg, {}).get("en")
                            or _fmsg
                        )
                        _lines.append(f"• {_flabel}: {_fhint}")
                    _anm_err_text = (
                        _error_intro.get(lang, _error_intro["en"])
                        + "\n"
                        + "\n".join(_lines)
                    )

                    _l3_edit_btn = {
                        "uk": "🔧 Виправити анкету",
                        "en": "🔧 Edit answers",
                        "de": "🔧 Antworten bearbeiten",
                        "pl": "🔧 Popraw ankietę",
                        "tr": "🔧 Formu düzenle",
                        "ar": "🔧 تعديل الإجابات",
                    }
                    _l3_menu_btn = {
                        "uk": "🏠 Головне меню",
                        "en": "🏠 Main menu",
                        "de": "🏠 Hauptmenü",
                        "pl": "🏠 Menu główne",
                        "tr": "🏠 Ana menü",
                        "ar": "🏠 القائمة الرئيسية",
                    }
                    _l3_kb = InlineKeyboardMarkup(row_width=1)
                    _l3_kb.add(
                        InlineKeyboardButton(
                            _l3_edit_btn.get(lang, _l3_edit_btn["en"]),
                            callback_data="edit_answers",
                        ),
                        InlineKeyboardButton(
                            _l3_menu_btn.get(lang, _l3_menu_btn["en"]),
                            callback_data="main_menu",
                        ),
                    )
                    await callback_query.message.answer(
                        _anm_err_text, parse_mode="HTML", reply_markup=_l3_kb
                    )
                    return

            except Exception as _l3_err:
                # Layer 3 guard failure must never block a legitimate payment
                logger.warning(
                    "GUARD_L3_ERROR | user_id=%s order_id=%s error=%s — proceeding",
                    user_id,
                    order_id,
                    _l3_err,
                )

        logger.info(
            "GUARD_PASS | user_id=%s order_id=%s doc=%s skip_warn=%s",
            user_id,
            order_id,
            _doc_type,
            skip_warnings,
        )
    except Exception as _guard_err:
        # Guard failure must never block a legitimate payment — log and proceed
        logger.warning(
            "GUARD_ERROR | user_id=%s order_id=%s error=%s — proceeding to Stripe",
            user_id,
            order_id,
            _guard_err,
        )

    # ===================== STEP 2: CREATE STRIPE SESSION =====================
    final_price = bundle_price if is_bundle else pdf_price

    if is_bundle:
        logger.info(
            "BUNDLE_SELECTED | user_id=%s order_id=%s pdf=%.2f bundle=%.2f",
            user_id,
            order_id,
            pdf_price,
            final_price,
        )

    stripe = get_stripe_handler()
    analytics = get_analytics()

    webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
    _bot_username = os.getenv("BOT_USERNAME", "DE_PDF_Assistant_bot")
    # Success page shows "✓ Payment successful" and auto-redirects via tg:// (native app,
    # no "Open Telegram?" dialog) with fallback to https://t.me after 1.5s.
    success_url = f"{webapp_url}/payment-success?order_id={order_id}&lang={lang}"
    cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id}&lang={lang}"
    logger.info(
        "STRIPE_SESSION_CREATED | order_id=%s success_url=%s", order_id, success_url
    )

    result = await stripe.create_checkout_session(
        order_id=order_id,
        user_id=user_id,
        doc_type=order["doc_type"],
        price=final_price,
        success_url=success_url,
        cancel_url=cancel_url,
        discount=order.get("discount", 0),
        promo_code=order.get("promo_code"),
        extra_metadata={"bundle": "true" if is_bundle else "false"},
    )

    if not result.success:
        logger.warning(
            "FUNNEL | step=stripe_error user_id=%s order_id=%s", user_id, order_id
        )
        await callback_query.message.answer("❌ Stripe error. Please try again.")
        return

    # FUNNEL POINT 5: Stripe session created — user is being redirected to checkout
    logger.info(
        "FUNNEL | step=stripe_session_created user_id=%s order_id=%s doc=%s price=%.2f",
        user_id,
        order_id,
        order.get("doc_type"),
        final_price,
    )

    db.update_order_status(
        order_id, OrderStatus.PENDING, stripe_session_id=result.session_id
    )
    db.create_payment(order_id, user_id, final_price, result.session_id)

    analytics.track_payment(user_id, order["doc_type"], "initiated", final_price)

    body = PAYWALL_SHORT_BODY.get(lang, PAYWALL_SHORT_BODY.get("en", ""))
    try:
        btn_label = PAY_BUTTON_LABEL.get(
            lang, PAY_BUTTON_LABEL.get("en", "Get filled example (€{price:.2f})")
        ).format(price=final_price)
    except (KeyError, ValueError):
        btn_label = f"Get filled example (€{final_price:.2f})"
    try:
        price_str = (
            format_price(final_price)
            if callable(format_price)
            else f"€{final_price:.2f}"
        )
    except Exception:
        price_str = f"€{final_price:.2f}"

    # === SUMMARY: show 2-3 key user fields before Stripe redirect ===
    # Reduces payment anxiety and chargebacks by letting user confirm their data.
    _summary_lines = []
    try:
        _raw_ud = order.get("user_data") or {}
        _ud = _raw_ud if isinstance(_raw_ud, dict) else json.loads(_raw_ud)
        _first = (_ud.get("first_name") or _ud.get("vorname") or "").strip()
        _last = (
            _ud.get("last_name") or _ud.get("nachname") or _ud.get("name") or ""
        ).strip()
        _city = (
            _ud.get("city")
            or _ud.get("ort")
            or _ud.get("stadt")
            or _ud.get("new_city")
            or _ud.get("zuzugsort")
            or ""
        ).strip()
        _doc_display = (order.get("doc_type") or "").replace("_", " ").title()
        _SUMMARY_HEADER = {
            "uk": "📋 <b>Перевірте перед оплатою:</b>",
            "en": "📋 <b>Please confirm before paying:</b>",
            "de": "📋 <b>Bitte vor der Zahlung prüfen:</b>",
            "pl": "📋 <b>Sprawdź przed płatnością:</b>",
            "tr": "📋 <b>Ödeme öncesi kontrol edin:</b>",
            "ar": "📋 <b>يرجى التحقق قبل الدفع:</b>",
        }
        # Only add non-empty meaningful values — never show "None" or blank labels
        _name = (_first + " " + _last).strip()
        if _name:
            _summary_lines.append(f"👤 {_name}")
        if _city:
            _summary_lines.append(f"📍 {_city}")
        if _doc_display and _doc_display.strip():
            _summary_lines.append(f"📄 {_doc_display}")
    except Exception:
        pass

    _summary_block = ""
    if len(_summary_lines) >= 2:
        # Show summary only if at least 2 fields are present — 1 field alone is not informative
        _hdr = _SUMMARY_HEADER.get(lang, _SUMMARY_HEADER["en"])
        _summary_block = _hdr + "\n" + "\n".join(_summary_lines) + "\n\n"

    _SECURE_BADGE = {
        "uk": "🔒 Безпечна оплата через Stripe",
        "ua": "🔒 Безпечна оплата через Stripe",
        "en": "🔒 Secure checkout via Stripe",
        "de": "🔒 Sichere Zahlung über Stripe",
        "pl": "🔒 Bezpieczna płatność przez Stripe",
        "tr": "🔒 Stripe ile güvenli ödeme",
        "ar": "🔒 دفع آمن عبر Stripe",
    }
    _badge = _SECURE_BADGE.get(lang, _SECURE_BADGE["en"])
    message_text = f"{_summary_block}{body}"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(btn_label, url=result.checkout_url))
    # Trust badge as a disabled info button — visible text, no action
    keyboard.add(types.InlineKeyboardButton(_badge, callback_data="noop_secure_badge"))

    await callback_query.message.edit_text(
        message_text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# Legacy handler: "Check payment" removed. If user has old message with check_payment_ button,
# just deliver if already PAID/SENT/DOWNLOADED; otherwise show "processing" (NOT confirmation).
async def check_payment_status(callback_query: types.CallbackQuery):
    await callback_query.answer()
    from backend.database import OrderStatus

    parts = callback_query.data.split("_")
    if len(parts) < 3:
        return
    order_id = int(parts[2])
    user_id = callback_query.from_user.id
    db = get_db()
    order = db.get_order(order_id)
    if not order or order["user_id"] != user_id:
        return
    status = (order.get("status") or "").strip().lower()
    if status in (
        OrderStatus.PAID.value,
        OrderStatus.SENT.value,
        OrderStatus.DOWNLOADED.value,
    ):
        await deliver_document(callback_query.message, order_id, user_id)
        return
    # Not yet paid/delivered — silent return. Webhook will handle delivery.
    # No "processing" chat message to avoid interrupting Stripe flow.
    logger.debug(
        "CHECK_PAYMENT_NOT_YET_PAID: order_id=%s (silent, awaiting webhook)", order_id
    )


# ============================================================================
# DELIVERY
# ============================================================================
#
# DOCUMENT CONTRACT (architectural rules — do not change without explicit decision):
# - Paid PDF is ALWAYS a filled example (from user answers, with watermark "EXAMPLE – NOT OFFICIAL").
# - Official blank is NEVER sent as a file; it is provided only as a link in the follow-up message.
# - Anmeldung uses AcroForm-only generation; there is NO overlay/coordinate-based fallback for Anmeldung.
# - These rules are intentional and ensure consistent delivery and PDF quality.
#
# ============================================================================


async def _send_user_text(
    message: Optional[types.Message], bot_instance, user_id: int, text: str, **kwargs
):
    """Send text to user: via message.answer if message provided, else bot.send_message (e.g. from webhook)."""
    if message:
        await message.answer(text, **kwargs)
    elif bot_instance and user_id:
        await bot_instance.send_message(user_id, text, **kwargs)


async def _notify_pdf_generation_failed(bot: Bot, user_id: int, order_id: int) -> None:
    """Notify the user that PDF generation failed and alert admins.

    Called when create_final_pdf returns no path or the file is missing.
    The user is charged — they must receive a human response, not silence.
    """
    import os as _os
    _support = _os.getenv("SUPPORT_USERNAME", "@support")
    _msg = (
        "⚠️ <b>Виникла технічна проблема</b>\n\n"
        "Ваш документ тимчасово не вдалося сформувати.\n"
        f"Ваше замовлення <code>#{order_id}</code> збережено.\n\n"
        f"Будь ласка, напишіть {_support} — ми надішлемо документ вручну."
    )
    try:
        await bot.send_message(user_id, _msg, parse_mode="HTML")
    except Exception as _ue:
        logger.error("_notify_pdf_generation_failed: cannot message user %s: %s", user_id, _ue)

    # Admin alert
    try:
        _admin_raw = _os.getenv("ADMIN_IDS", "")
        _admin_ids = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]
        _alert = (
            f"🚨 <b>PDF GENERATION FAILED</b>\n\n"
            f"order_id: <code>{order_id}</code>\n"
            f"user_id: <code>{user_id}</code>\n"
            f"create_final_pdf returned no file — manual resend required."
        )
        for _aid in _admin_ids:
            try:
                await bot.send_message(_aid, _alert, parse_mode="HTML")
            except Exception:
                pass
    except Exception as _ae:
        logger.error("_notify_pdf_generation_failed: admin alert error: %s", _ae)


async def send_final_pdf(bot: Bot, user_id: int, order_id: int) -> None:
    """
    Webhook-only delivery: generate final PDF, send via bot.send_document, set order SENT.
    Delivery depends ONLY on order.status == PAID and idempotency (SENT/DOWNLOADED). stripe_session_id is NOT required.
    """
    import asyncio
    from backend.database import OrderStatus
    from backend.pdf_generator import create_final_pdf

    logger.info("send_final_pdf: ENTER order_id=%s user_id=%s", order_id, user_id)
    db = get_db()
    order = db.get_order(order_id)
    if not order:
        logger.error("send_final_pdf: STOP — order not found order_id=%s", order_id)
        return
    status = (order.get("status") or "").strip().lower()
    if status in (OrderStatus.SENT.value, OrderStatus.DOWNLOADED.value):
        logger.info(
            "send_final_pdf: STOP — idempotent (status=%s) order_id=%s",
            status,
            order_id,
        )
        return
    # Race condition fix: if status is PENDING, wait briefly and re-check (webhook may have called before DB commit)
    if status != OrderStatus.PAID.value:
        if status == OrderStatus.PENDING.value:
            logger.info(
                "send_final_pdf: status=pending, waiting for DB commit order_id=%s",
                order_id,
            )
            await asyncio.sleep(0.5)
            order = db.get_order(order_id)
            if order:
                status = (order.get("status") or "").strip().lower()
                # Re-check idempotency after reload
                if status in (OrderStatus.SENT.value, OrderStatus.DOWNLOADED.value):
                    logger.info(
                        "send_final_pdf: STOP — idempotent after reload (status=%s) order_id=%s",
                        status,
                        order_id,
                    )
                    return
        if status != OrderStatus.PAID.value:
            logger.info(
                "send_final_pdf: STOP — order not PAID (status=%s) order_id=%s",
                status,
                order_id,
            )
            return
    user_data_raw = order.get("user_data")
    if user_data_raw is None:
        user_data_raw = "{}"
    if isinstance(user_data_raw, dict):
        user_data = user_data_raw
    else:
        try:
            user_data = json.loads(user_data_raw)
        except (json.JSONDecodeError, TypeError):
            user_data = {}
    if not user_data or len(user_data) == 0:
        logger.error("send_final_pdf: STOP — no user_data order_id=%s", order_id)
        return
    doc_type = (order.get("doc_type") or "").strip().lower()
    if not doc_type:
        logger.error(f"[PDF] Missing doc_type for order {order_id}")
        return
    lang = (order.get("lang") or "en").strip().lower() or "en"
    logger.info(
        f"[PDF] Generating final PDF for order={order_id}, user={user_id}, doc_type={doc_type}"
    )
    result = create_final_pdf(
        user_id=user_id,
        user_data=user_data,
        doc_type=doc_type,
        authority_info=None,
        user_lang=lang,
    )
    if not result or not isinstance(result, str):
        logger.error(
            "send_final_pdf: STOP — create_final_pdf returned no path order_id=%s result=%s",
            order_id,
            type(result).__name__,
        )
        await _notify_pdf_generation_failed(bot, user_id, order_id)
        return
    if not os.path.exists(result):
        logger.error(
            "send_final_pdf: STOP — file not found path=%s order_id=%s",
            result,
            order_id,
        )
        await _notify_pdf_generation_failed(bot, user_id, order_id)
        return
    logger.info("PDF_GENERATED order_id=%s path=%s", order_id, result)

    # ── Retry × 3 with exponential back-off ─────────────────────────────────
    _max_attempts = 3
    _sent = False
    for _attempt in range(1, _max_attempts + 1):
        try:
            with open(result, "rb") as f:
                await bot.send_document(user_id, f)
            _sent = True
            break
        except Exception as _e:
            logger.warning(
                "send_final_pdf: attempt %s/%s FAILED order_id=%s: %s",
                _attempt,
                _max_attempts,
                order_id,
                _e,
            )
            if _attempt < _max_attempts:
                import asyncio as _asyncio

                await _asyncio.sleep(2**_attempt)  # 2s, 4s

    if _sent:
        try:
            from backend.utils.pdf_cleanup import delete_pdf_after_delivery

            delete_pdf_after_delivery(result)
        except Exception as _ce:
            logger.warning(
                "send_final_pdf: pdf cleanup failed order_id=%s: %s", order_id, _ce
            )

    if not _sent:
        logger.error(
            "send_final_pdf: ALL ATTEMPTS FAILED order_id=%s user_id=%s",
            order_id,
            user_id,
        )
        # ── Admin alert ──────────────────────────────────────────────────────
        try:
            import os as _os

            _admin_raw = _os.getenv("ADMIN_IDS", "")
            _admin_ids = [int(x.strip()) for x in _admin_raw.split(",") if x.strip()]
            _alert = (
                f"🚨 <b>PDF delivery FAILED</b>\n\n"
                f"order_id: <code>{order_id}</code>\n"
                f"user_id: <code>{user_id}</code>\n"
                f"All {_max_attempts} attempts failed.\n"
                f"Check logs and resend manually."
            )
            for _aid in _admin_ids:
                try:
                    await bot.send_message(_aid, _alert, parse_mode="HTML")
                except Exception:
                    pass
        except Exception as _ae:
            logger.error("send_final_pdf: admin_alert failed: %s", _ae)
        return

    logger.info("PDF_SENT order_id=%s user_id=%s", order_id, user_id)
    # FUNNEL POINT 6: PDF delivered — conversion complete
    logger.info("FUNNEL | step=pdf_delivered user_id=%s order_id=%s", user_id, order_id)
    db.update_order_status(order_id, OrderStatus.SENT)


# ============================================================================
# CROSS-SELL: recommend related documents after PDF delivery
# ============================================================================

CROSS_SELL_MAP = {
    "anmeldung": ["wohnungsgeberbestaetigung", "meldebescheinigung"],
    "ummeldung": ["meldebescheinigung", "wohnungsgeberbestaetigung"],
    "abmeldung": ["meldebescheinigung", "kuendigung"],
    "wohnungsgeberbestaetigung": ["anmeldung", "ummeldung"],
    "meldebescheinigung": ["anmeldung", "wohngeld"],
    "buergergeld": ["wohngeld", "kindergeld"],
    "wohngeld": ["buergergeld", "kindergeld"],
    "kindergeld": ["kinderzuschlag", "elterngeld"],
    "kinderzuschlag": ["kindergeld", "elterngeld"],
    "elterngeld": ["kindergeld", "kinderzuschlag"],
    "unterhaltsvorschuss": ["kindergeld", "buergergeld"],
    "kuendigung": ["arbeitslosengeld_1", "buergergeld"],
    "arbeitslosengeld_1": ["buergergeld", "wohngeld"],
    "gewerbeanmeldung": ["anmeldung", "meldebescheinigung"],
}

CROSS_SELL_HEADER = {
    "uk": "📎 <b>Вам також може знадобитися:</b>",
    "ua": "📎 <b>Вам також може знадобитися:</b>",
    "en": "📎 <b>You might also need:</b>",
    "de": "📎 <b>Das könnte Sie auch interessieren:</b>",
    "pl": "📎 <b>Może Ci się również przydać:</b>",
    "tr": "📎 <b>Bunlara da ihtiyacınız olabilir:</b>",
    "ar": "📎 <b>قد تحتاج أيضًا إلى:</b>",
}

CROSS_SELL_DOC_NAMES = {
    "anmeldung": {
        "uk": "Anmeldung (реєстрація)",
        "ua": "Anmeldung (реєстрація)",
        "en": "Anmeldung (registration)",
        "de": "Anmeldung",
        "pl": "Anmeldung (zameldowanie)",
        "tr": "Anmeldung (kayıt)",
        "ar": "Anmeldung (تسجيل)",
    },
    "ummeldung": {
        "uk": "Ummeldung (перереєстрація)",
        "ua": "Ummeldung (перереєстрація)",
        "en": "Ummeldung (re-registration)",
        "de": "Ummeldung",
        "pl": "Ummeldung (przerejestrowanie)",
        "tr": "Ummeldung (adres değişikliği)",
        "ar": "Ummeldung (إعادة تسجيل)",
    },
    "abmeldung": {
        "uk": "Abmeldung (зняття з обліку)",
        "ua": "Abmeldung (зняття з обліку)",
        "en": "Abmeldung (deregistration)",
        "de": "Abmeldung",
        "pl": "Abmeldung (wymeldowanie)",
        "tr": "Abmeldung (kayıt silme)",
        "ar": "Abmeldung (إلغاء تسجيل)",
    },
    "wohnungsgeberbestaetigung": {
        "uk": "Wohnungsgeberbestätigung",
        "ua": "Wohnungsgeberbestätigung",
        "en": "Wohnungsgeberbestätigung",
        "de": "Wohnungsgeberbestätigung",
        "pl": "Wohnungsgeberbestätigung",
        "tr": "Wohnungsgeberbestätigung",
        "ar": "Wohnungsgeberbestätigung",
    },
    "meldebescheinigung": {
        "uk": "Meldebescheinigung",
        "ua": "Meldebescheinigung",
        "en": "Meldebescheinigung",
        "de": "Meldebescheinigung",
        "pl": "Meldebescheinigung",
        "tr": "Meldebescheinigung",
        "ar": "Meldebescheinigung",
    },
    "buergergeld": {
        "uk": "Bürgergeld",
        "ua": "Bürgergeld",
        "en": "Bürgergeld",
        "de": "Bürgergeld",
        "pl": "Bürgergeld",
        "tr": "Bürgergeld",
        "ar": "Bürgergeld",
    },
    "wohngeld": {
        "uk": "Wohngeld (допомога на житло)",
        "ua": "Wohngeld (допомога на житло)",
        "en": "Wohngeld (housing benefit)",
        "de": "Wohngeld",
        "pl": "Wohngeld (dodatek mieszkaniowy)",
        "tr": "Wohngeld (konut yardımı)",
        "ar": "Wohngeld (بدل سكن)",
    },
    "kindergeld": {
        "uk": "Kindergeld (допомога на дітей)",
        "ua": "Kindergeld (допомога на дітей)",
        "en": "Kindergeld (child benefit)",
        "de": "Kindergeld",
        "pl": "Kindergeld (zasiłek na dzieci)",
        "tr": "Kindergeld (çocuk yardımı)",
        "ar": "Kindergeld (علاوة أطفال)",
    },
    "kinderzuschlag": {
        "uk": "Kinderzuschlag (доплата на дітей)",
        "ua": "Kinderzuschlag (доплата на дітей)",
        "en": "Kinderzuschlag (child supplement)",
        "de": "Kinderzuschlag",
        "pl": "Kinderzuschlag (dopłata na dzieci)",
        "tr": "Kinderzuschlag (çocuk ek ödeneği)",
        "ar": "Kinderzuschlag (ملحق أطفال)",
    },
    "elterngeld": {
        "uk": "Elterngeld (батьківські)",
        "ua": "Elterngeld (батьківські)",
        "en": "Elterngeld (parental allowance)",
        "de": "Elterngeld",
        "pl": "Elterngeld (zasiłek rodzicielski)",
        "tr": "Elterngeld (ebeveyn ödeneği)",
        "ar": "Elterngeld (بدل والدي)",
    },
    "unterhaltsvorschuss": {
        "uk": "Unterhaltsvorschuss (аліменти)",
        "ua": "Unterhaltsvorschuss (аліменти)",
        "en": "Unterhaltsvorschuss (child maintenance advance)",
        "de": "Unterhaltsvorschuss",
        "pl": "Unterhaltsvorschuss (zaliczka alimentacyjna)",
        "tr": "Unterhaltsvorschuss (nafaka avansı)",
        "ar": "Unterhaltsvorschuss (سلفة نفقة)",
    },
    "kuendigung": {
        "uk": "Kündigung (звільнення)",
        "ua": "Kündigung (звільнення)",
        "en": "Kündigung (termination)",
        "de": "Kündigung",
        "pl": "Kündigung (wypowiedzenie)",
        "tr": "Kündigung (fesih)",
        "ar": "Kündigung (إنهاء عقد)",
    },
    "arbeitslosengeld_1": {
        "uk": "Arbeitslosengeld I",
        "ua": "Arbeitslosengeld I",
        "en": "Arbeitslosengeld I",
        "de": "Arbeitslosengeld I",
        "pl": "Arbeitslosengeld I",
        "tr": "Arbeitslosengeld I",
        "ar": "Arbeitslosengeld I",
    },
    "gewerbeanmeldung": {
        "uk": "Gewerbeanmeldung (реєстрація бізнесу)",
        "ua": "Gewerbeanmeldung (реєстрація бізнесу)",
        "en": "Gewerbeanmeldung (business registration)",
        "de": "Gewerbeanmeldung",
        "pl": "Gewerbeanmeldung (rejestracja działalności)",
        "tr": "Gewerbeanmeldung (işletme kaydı)",
        "ar": "Gewerbeanmeldung (تسجيل تجاري)",
    },
}


async def send_cross_sell(bot_instance: Bot, user_id: int, doc_type: str, lang: str, delay: float = 15.0):
    """
    Send a cross-sell suggestion for related documents after a delivery.
    Fires `delay` seconds after delivery to not compete with the receipt.
    Safe — never raises; all errors are logged and swallowed.
    """
    import asyncio as _aio
    await _aio.sleep(delay)
    try:
        from backend.translations import ui as _ui_cs
        _related = CROSS_SELL_MAP.get(doc_type or "", [])
        if not _related:
            return
        _l = "ua" if lang in ("ua", "uk") else (lang if lang in ("de", "en", "pl", "tr", "ar") else "ua")
        header = _ui_cs("cross_sell_title", _l)

        from aiogram.types import InlineKeyboardMarkup as _IKM, InlineKeyboardButton as _IKB
        kb = _IKM(row_width=1)
        lines = [header, ""]
        for _dt in _related[:2]:
            _name_map = CROSS_SELL_DOC_NAMES.get(_dt, {})
            _name = _name_map.get(_l) or _name_map.get("en") or _dt.replace("_", " ").title()
            lines.append(f"• {_name}")
            kb.add(_IKB(f"📄 {_name}", callback_data=f"doc_{_dt}"))

        await bot_instance.send_message(
            chat_id=int(user_id),
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=kb,
        )
        logger.info("CROSS_SELL_SENT: user=%s doc=%s related=%s", user_id, doc_type, _related[:2])
    except Exception as _cs_err:
        logger.debug("CROSS_SELL_FAILED: user=%s doc=%s err=%s", user_id, doc_type, _cs_err)


async def deliver_document_after_payment(
    bot_instance: Bot, order_id: int, force: bool = False,
    skip_pdf_send: bool = False,
) -> bool:
    """
    Called from Stripe webhook. Single delivery flow: load order → generate PDF → send → mark sent.
    Returns True if PDF was generated and sent, False otherwise.
    force=True: skip claim_delivery guard (used by deeplink recovery for FAILED orders).
    skip_pdf_send=True: skip Telegram send_document (caller sends the PDF itself after email).
    """
    from backend.database import OrderStatus
    from backend.pdf_generator import create_final_pdf

    logger.info("DELIVERY_STARTED: order_id=%s", order_id)

    db = get_db()
    order = db.get_order(order_id)

    if not order:
        raise RuntimeError(f"DELIVERY_FAILED: order_id={order_id} ORDER_NOT_FOUND")

    user_id = order.get("user_id")
    if not user_id:
        raise RuntimeError(f"DELIVERY_FAILED: order_id={order_id} NO_USER_ID")

    status = (order.get("status") or "").strip().lower()
    if status in (OrderStatus.DOWNLOADED.value, OrderStatus.SENT.value):
        logger.info(
            "DELIVERY_SKIPPED_IDEMPOTENT: order_id=%s status=%s", order_id, status
        )
        return True
    if status == OrderStatus.PROCESSING.value and not force:
        logger.info(
            "DELIVERY_SKIPPED_IN_PROGRESS: order_id=%s already PROCESSING", order_id
        )
        return True

    # Atomic claim: UPDATE … WHERE status='paid' — only the first concurrent
    # caller gets rowcount=1; the second sees rowcount=0 and exits here.
    # This closes the race window between the Stripe webhook and the deep-link.
    if force:
        logger.info("DELIVERY_FORCE: order_id=%s — bypassing claim_delivery", order_id)
        db.update_order_status(order_id, OrderStatus.PROCESSING)
    elif not db.claim_delivery(order_id):
        logger.info(
            "DELIVERY_CLAIM_LOST: order_id=%s — another call already claimed delivery",
            order_id,
        )
        return True  # treat as already-handled; PDF will be sent by the winner
    logger.info("DELIVERY_CLAIMED: order_id=%s PAID→PROCESSING (atomic)", order_id)
    logger.info("PDF_SEND_EXECUTED: order_id=%s", order_id)

    try:
        return await _deliver_document_inner(
            bot_instance=bot_instance,
            order_id=order_id,
            order=order,
            db=db,
            skip_pdf_send=skip_pdf_send,
        )
    except Exception as _delivery_exc:
        try:
            db.update_order_status(order_id, OrderStatus.FAILED)
            logger.warning(
                "DELIVERY_MARKED_FAILED: order_id=%s reason=%s",
                order_id,
                _delivery_exc,
            )
        except Exception as _mark_err:
            logger.error(
                "DELIVERY_FAILED_MARK_ERROR: order_id=%s err=%s", order_id, _mark_err
            )
        raise


async def _deliver_document_inner(
    bot_instance: Bot,
    order_id: int,
    order: dict,
    db,
    skip_pdf_send: bool = False,
) -> bool:
    """Inner implementation of deliver_document_after_payment (called after PROCESSING is claimed).
    skip_pdf_send=True: generate PDF and mark SENT but do NOT send it via Telegram.
    The caller is then responsible for sending the PDF (e.g. as a single message with caption).
    """
    from backend.database import OrderStatus
    from backend.pdf_generator import create_final_pdf

    user_id = order.get("user_id")
    # Parse user_data
    user_data_raw = order.get("user_data")
    if not user_data_raw:
        raise RuntimeError(f"DELIVERY_FAILED: order_id={order_id} NO_USER_DATA")

    if isinstance(user_data_raw, dict):
        user_data = user_data_raw
    else:
        try:
            user_data = json.loads(user_data_raw)
        except Exception:
            user_data = {}
    # Handle double-encoded JSON (json.loads of a JSON string returns another string)
    if isinstance(user_data, str):
        try:
            user_data = json.loads(user_data)
        except Exception:
            user_data = {}
    if not isinstance(user_data, dict):
        user_data = {}

    logger.info("USER_DATA_TYPE: %s order_id=%s", type(user_data).__name__, order_id)
    logger.info("USER_DATA_CONTENT: %s order_id=%s", user_data, order_id)

    if not user_data or len(user_data) == 0:
        raise RuntimeError(f"DELIVERY_FAILED: order_id={order_id} EMPTY_USER_DATA")

    doc_type = order.get("doc_type")
    if not doc_type:
        raise RuntimeError(f"DELIVERY_FAILED: order_id={order_id} NO_DOC_TYPE")

    lang = order.get("lang") or "en"

    logger.info("DELIVERY_ORDER_LOADED: order_id=%s user_id=%s doc_type=%s", order_id, user_id, doc_type)

    # === PDF GENERATION ===
    logger.info("PDF_GENERATOR_ENTERED: order_id=%s doc_type=%s", order_id, doc_type)

    _cap_lang = "uk" if lang == "ua" else lang
    if (doc_type or "").strip().lower() == "buergergeld":
        caption = _BUERGERGELD_CAPTION_TEXTS.get(
            _cap_lang, _BUERGERGELD_CAPTION_TEXTS["en"]
        )
    else:
        caption = FINAL_CAPTION_TEXTS.get(_cap_lang, FINAL_CAPTION_TEXTS["en"])

    # Compute menu city early — needed for both ummeldung loop and post-payment menu
    _menu_city = (
        (user_data.get("city") or user_data.get("ort") or user_data.get("stadt") or "")
        if user_data
        else ""
    )
    try:
        _post_payment_kb = build_post_payment_menu(doc_type, _menu_city, lang)
    except Exception as _kb_err:
        logger.warning(
            "build_post_payment_menu failed doc_type=%s err=%s", doc_type, _kb_err
        )
        _post_payment_kb = None

    # Prepend "Next step" line only when Termin booking is actually available
    # for this doc_type × city — avoids misleading users where Termin is unsupported.
    if is_termin_supported(doc_type, _menu_city):
        _next_step = _NEXT_STEP_TERMIN.get(_cap_lang, _NEXT_STEP_TERMIN["en"])
        caption = _next_step + "\n\n" + caption

    # canonical_file_path is set by whichever branch runs; used for db.update_order_file_path.
    canonical_file_path: Optional[str] = None

    # ── Ummeldung: chunk persons into groups of 2 → one PDF per chunk ────────
    if doc_type.lower() == "ummeldung":
        from backend.form_builder import build_ummeldung_pdfs
        from backend.pdf_generator import OUTPUT_DIR

        _base = f"ummeldung_{user_id}_{order_id}"
        _ummeldung_loop = asyncio.get_event_loop()
        pdf_paths = await _ummeldung_loop.run_in_executor(
            None,
            lambda: build_ummeldung_pdfs(
                user_data=user_data,
                output_dir=str(OUTPUT_DIR),
                base_filename=_base,
                is_preview=False,
                user_lang=lang,
            ),
        )
        if not pdf_paths:
            raise RuntimeError(
                f"DELIVERY_FAILED: order_id={order_id} UMMELDUNG_NO_PDFS_GENERATED"
            )
        logger.info("UMMELDUNG_PDFS_GENERATED: count=%s order_id=%s", len(pdf_paths), order_id)
        canonical_file_path = pdf_paths[0]
        # Send each PDF; caption shows part number when > 1; last part gets the post-payment keyboard
        for _idx, _fp in enumerate(pdf_paths, start=1):
            if not os.path.exists(_fp):
                logger.error(
                    "deliver_document_after_payment: ummeldung part %d not found path=%s",
                    _idx,
                    _fp,
                )
                continue
            _part_caption = (
                f"{caption} ({_idx}/{len(pdf_paths)})"
                if len(pdf_paths) > 1
                else caption
            )
            _is_last = _idx == len(pdf_paths)
            if _is_last:
                logger.info(
                    "FINAL_SINGLE_MESSAGE_SEND order_id=%s doc_type=%s part=%d/%d",
                    order_id,
                    doc_type,
                    _idx,
                    len(pdf_paths),
                )
            with open(_fp, "rb") as _f:
                await bot_instance.send_document(
                    user_id,
                    _f,
                    caption=_part_caption,
                    reply_markup=_post_payment_kb if _is_last else None,
                )
            logger.info("UMMELDUNG_PDF_SENT: part=%s/%s order_id=%s", _idx, len(pdf_paths), order_id)
            try:
                from backend.utils.pdf_cleanup import delete_pdf_after_delivery

                # Skip cleanup for canonical_file_path (pdf_paths[0]) — bot.py handles
                # it AFTER email delivery so the file still exists when emailed.
                if _fp != canonical_file_path:
                    delete_pdf_after_delivery(_fp)
            except Exception as _ce:
                logger.warning(
                    "deliver_document_after_payment: ummeldung cleanup failed: %s", _ce
                )
    else:
        # ── Standard single-PDF path ──────────────────────────────────────────
        if (doc_type or "").strip().lower() in (
            "buergergeld",
            "jobcenter",
        ) and not user_data.get("plz"):
            logger.warning("PLZ missing — continuing without it order_id=%s", order_id)
        try:
            _pdf_loop = asyncio.get_event_loop()
            file_path = await _pdf_loop.run_in_executor(
                None,
                lambda: create_final_pdf(
                    user_id=user_id, user_data=user_data, doc_type=doc_type, user_lang=lang
                ),
            )
        except Exception as _pdf_exc:
            logger.error(
                "PDF_GENERATION_FAILED: order_id=%s err=%s", order_id, _pdf_exc
            )
            try:
                await bot_instance.send_message(
                    chat_id=user_id,
                    text="❌ Error generating document. Please contact support.",
                )
            except Exception:
                pass
            db.update_order_status(order_id, OrderStatus.FAILED)
            return False

        # create_final_pdf returns a dict when validation fails (not a file path).
        if isinstance(file_path, dict):
            _status = file_path.get("status", "")
            _missing = file_path.get("missing_fields") or [
                m.get("key", "") for m in (file_path.get("errors") or [])
            ]
            logger.warning(
                "DELIVERY_FAILED_VALIDATION: order_id=%s status=%s missing_fields=%s",
                order_id,
                _status,
                _missing,
            )
            try:
                await bot_instance.send_message(
                    chat_id=user_id,
                    text="❌ Error generating document. Please contact support.",
                )
            except Exception:
                pass
            db.update_order_status(order_id, OrderStatus.FAILED)
            return False

        if not file_path or not isinstance(file_path, str):
            raise RuntimeError(
                f"DELIVERY_FAILED: order_id={order_id} PDF_NOT_GENERATED result_type={type(file_path).__name__}"
            )

        if not os.path.exists(file_path):
            raise RuntimeError(
                f"DELIVERY_FAILED: order_id={order_id} PDF_FILE_NOT_EXISTS path={file_path}"
            )

        canonical_file_path = file_path
        logger.info("PDF_GENERATED_PATH: order_id=%s path=%s", order_id, file_path)

    # === WRITE TERMIN FSM CONTEXT (silent — no user message) ===
    try:
        from aiogram import Dispatcher as _Dp

        _form_city = (
            (
                user_data.get("city")
                or user_data.get("ort")
                or user_data.get("stadt")
                or ""
            )
            if user_data
            else ""
        )
        _form_plz = (
            (user_data.get("plz") or user_data.get("postleitzahl") or "")
            if user_data
            else ""
        )
        _cur_dp = _Dp.get_current()
        if _cur_dp:
            _fsm = _cur_dp.current_state(chat=user_id, user=user_id)
            await _fsm.update_data(
                termin_city=_form_city,
                termin_plz=_form_plz,
                source_doc=doc_type,
            )
            logger.debug(
                "TERMIN_FSM_WRITTEN: user_id=%s city=%s plz=%s doc=%s",
                user_id,
                _form_city,
                _form_plz,
                doc_type,
            )
    except Exception as _fsm_err:
        logger.warning(
            "deliver_document_after_payment: FSM write failed order_id=%s: %s",
            order_id,
            _fsm_err,
        )

    # === MARK SENT before send_document so status is terminal even if Telegram errors ===
    db.update_order_status(order_id, OrderStatus.SENT)
    if canonical_file_path:
        db.update_order_file_path(order_id, canonical_file_path)
    logger.info("ORDER_MARKED_SENT: order_id=%s", order_id)

    # DISABLED: buergergeld sign-reminder and steps were sent as two extra messages before
    # the PDF. All relevant content (page-8 note, ⚠️ warning, Jobcenter steps) is now
    # included in _BUERGERGELD_CAPTION_TEXTS and delivered as part of the single PDF message.

    # === SEND PDF — ONE message: document + caption + inline keyboard ===
    # Ummeldung PDFs were already sent in the loop above (last part carries the keyboard).
    # All other doc types: send the single PDF here unless skip_pdf_send=True, in which
    # case the caller (bot.py webhook) will send the PDF itself after email delivery so
    # it can include email-status text in the caption — producing exactly ONE message.
    if doc_type.lower() != "ummeldung" and not skip_pdf_send:
        logger.info(
            "FINAL_SINGLE_MESSAGE_SEND order_id=%s doc_type=%s", order_id, doc_type
        )
        try:
            await bot_instance.send_chat_action(user_id, action="upload_document")
        except Exception:
            pass
        try:
            with open(canonical_file_path, "rb") as f:
                await bot_instance.send_document(
                    user_id, f, caption=caption, reply_markup=_post_payment_kb
                )
            logger.info("PDF_SENT: order_id=%s", order_id)
        except Exception as _send_err:
            _e = str(_send_err).lower()
            if any(
                k in _e
                for k in (
                    "blocked",
                    "chat not found",
                    "deactivated",
                    "user is deactivated",
                )
            ):
                # User blocked the bot or deleted account — can't deliver. Status stays SENT.
                logger.error(
                    "PDF_SEND_BLOCKED: order_id=%s user_id=%s err=%s",
                    order_id,
                    user_id,
                    _send_err,
                )
            else:
                # Transient error (network, Telegram overload) — re-raise so outer handler
                # rolls status back to PAID and Stripe can retry delivery.
                logger.error(
                    "PDF_SEND_FAILED: order_id=%s user_id=%s err=%s",
                    order_id,
                    user_id,
                    _send_err,
                )
                raise
        # NOTE: cleanup happens in bot.py AFTER email delivery so the file still
        # exists when send_pdf_by_email() reads it. Do NOT cleanup here.
    elif skip_pdf_send and doc_type.lower() != "ummeldung":
        logger.info(
            "PDF_SEND_DEFERRED: order_id=%s doc_type=%s — caller will send with receipt caption",
            order_id, doc_type,
        )

    # Uncomment the block below to re-enable post-payment referral prompt.
    # try:
    #     ... (referral share prompt code preserved here for future re-activation)
    # except Exception as _share_err:
    #     logger.debug("SHARE_PROMPT_FAILED: order=%s err=%s", order_id, _share_err)

    # Return the PDF path so the caller (webhook handler) can send it via email
    # before triggering cleanup. Returns True (truthy) when path is unavailable.
    return canonical_file_path or True


async def deliver_document(
    message: Optional[types.Message],
    order_id: int,
    user_id: int,
    bot_instance: Optional[Bot] = None,
    force_resend: bool = False,
) -> bool:
    """
    Deliver PDF for already-paid order (legacy/UI calls).
    For webhook flow, use deliver_document_after_payment instead.
    """
    from backend.database import OrderStatus
    from backend.pdf_generator import create_final_pdf

    logger.info("deliver_document: ENTER order_id=%s user_id=%s", order_id, user_id)

    db = get_db()
    bot = bot_instance or get_bot()
    order = db.get_order(order_id)

    if not order:
        raise RuntimeError(f"deliver_document: ORDER_NOT_FOUND order_id={order_id}")

    current_status = (order.get("status") or "").strip().lower()
    if not force_resend and current_status in (
        OrderStatus.DOWNLOADED.value,
        OrderStatus.SENT.value,
    ):
        logger.info(
            "deliver_document: SKIPPED_IDEMPOTENT order_id=%s status=%s",
            order_id,
            current_status,
        )
        return True
    if not force_resend and current_status == OrderStatus.PROCESSING.value:
        logger.info(
            "deliver_document: SKIPPED_IN_PROGRESS order_id=%s already PROCESSING",
            order_id,
        )
        return True
    # For PAID orders: use atomic claim so deliver_document and deliver_document_after_payment
    # cannot both win when called concurrently for the same order.
    if not force_resend and current_status == OrderStatus.PAID.value:
        if not db.claim_delivery(order_id):
            logger.info(
                "deliver_document: CLAIM_LOST order_id=%s — another call already claimed delivery",
                order_id,
            )
            return True
        logger.info(
            "deliver_document: CLAIMED order_id=%s PAID→PROCESSING (atomic)", order_id
        )

    user_data_raw = order.get("user_data")
    if not user_data_raw:
        logger.error(f"deliver_document: NO_USER_DATA order_id={order_id}")
        if message:
            await message.answer(
                "❗ Дані для цього документа не знайдені.\n\n"
                "Можливо, замовлення було створене без збережених відповідей.\n"
                "Будь ласка, заповніть анкету повторно."
            )
        return False

    if isinstance(user_data_raw, dict):
        user_data = user_data_raw
    else:
        user_data = json.loads(user_data_raw)

    if not user_data or len(user_data) == 0:
        raise RuntimeError(f"deliver_document: EMPTY_USER_DATA order_id={order_id}")

    doc_type = order.get("doc_type")
    if not doc_type:
        raise RuntimeError(f"deliver_document: NO_DOC_TYPE order_id={order_id}")

    lang = order.get("lang") or get_user_lang(user_id)

    logger.info("PDF_GENERATOR_ENTERED: order_id=%s doc_type=%s", order_id, doc_type)

    _dl_cap_lang = "uk" if lang == "ua" else lang
    caption = FINAL_CAPTION_TEXTS.get(_dl_cap_lang, FINAL_CAPTION_TEXTS["en"])
    _dl_city = (
        (user_data.get("city") or user_data.get("ort") or user_data.get("stadt") or "")
        if user_data
        else ""
    )
    try:
        _dl_post_kb = build_post_payment_menu(doc_type, _dl_city, lang)
    except Exception as _kb_err:
        logger.warning(
            "build_post_payment_menu failed doc_type=%s err=%s", doc_type, _kb_err
        )
        _dl_post_kb = None

    # ── Ummeldung: chunk persons into groups of 2 → one PDF per chunk ────────
    if doc_type.lower() == "ummeldung":
        from backend.form_builder import build_ummeldung_pdfs
        from backend.pdf_generator import OUTPUT_DIR

        _base = f"ummeldung_{user_id}_{order_id}"
        pdf_paths = build_ummeldung_pdfs(
            user_data=user_data,
            output_dir=str(OUTPUT_DIR),
            base_filename=_base,
            is_preview=False,
            user_lang=lang,
        )
        if not pdf_paths:
            raise RuntimeError(
                f"deliver_document: UMMELDUNG_NO_PDFS_GENERATED order_id={order_id}"
            )
        logger.info("UMMELDUNG_PDFS_GENERATED: count=%s order_id=%s", len(pdf_paths), order_id)
        # Store first path in order for reference
        db.update_order_file_path(order_id, pdf_paths[0])
        for _idx, _fp in enumerate(pdf_paths, start=1):
            if not os.path.exists(_fp):
                logger.error(
                    "deliver_document: ummeldung part %d not found path=%s", _idx, _fp
                )
                continue
            _part_caption = (
                f"{caption} ({_idx}/{len(pdf_paths)})"
                if len(pdf_paths) > 1
                else caption
            )
            _is_last_dl = _idx == len(pdf_paths)
            if _is_last_dl:
                logger.info(
                    "FINAL_SINGLE_MESSAGE_SEND order_id=%s doc_type=%s part=%d/%d",
                    order_id,
                    doc_type,
                    _idx,
                    len(pdf_paths),
                )
            with open(_fp, "rb") as _f:
                await bot.send_document(
                    user_id,
                    _f,
                    caption=_part_caption,
                    reply_markup=_dl_post_kb if _is_last_dl else None,
                )
            logger.info("UMMELDUNG_PDF_SENT: part=%s/%s order_id=%s", _idx, len(pdf_paths), order_id)
            try:
                from backend.utils.pdf_cleanup import delete_pdf_after_delivery

                delete_pdf_after_delivery(_fp)
            except Exception as _ce:
                logger.warning("deliver_document: ummeldung cleanup failed: %s", _ce)
    else:
        # ── Standard single-PDF path ──────────────────────────────────────────
        file_path = create_final_pdf(
            user_id=user_id, user_data=user_data, doc_type=doc_type, user_lang=lang
        )

        if not file_path or not isinstance(file_path, str):
            raise RuntimeError(
                f"deliver_document: PDF_NOT_GENERATED order_id={order_id} result_type={type(file_path).__name__}"
            )

        if not os.path.exists(file_path):
            raise RuntimeError(
                f"deliver_document: PDF_FILE_NOT_EXISTS order_id={order_id} path={file_path}"
            )

        logger.info("PDF_GENERATED_PATH: order_id=%s path=%s", order_id, file_path)

        db.update_order_file_path(order_id, file_path)

        logger.info(
            "FINAL_SINGLE_MESSAGE_SEND order_id=%s doc_type=%s", order_id, doc_type
        )

        # ONE message: document + caption + post-payment keyboard
        with open(file_path, "rb") as f:
            await bot.send_document(
                user_id, f, caption=caption, reply_markup=_dl_post_kb
            )

        logger.info("PDF_SENT: order_id=%s", order_id)
        try:
            from backend.utils.pdf_cleanup import delete_pdf_after_delivery

            delete_pdf_after_delivery(file_path)
        except Exception as _ce:
            logger.warning(
                "deliver_document: pdf cleanup failed order_id=%s: %s", order_id, _ce
            )

    # DISABLED: upsell send_message suppressed — avoid extra message after PDF

    db.update_order_status(order_id, OrderStatus.SENT)
    logger.info("ORDER_MARKED_SENT: order_id=%s", order_id)

    return True


# ============================================================================
# POST-PAYMENT ACTIONS — Official form, Instructions, Re-download, My docs
# ============================================================================

# Localized doc-type display names for the history view
_DOC_TYPE_LABELS: Dict[str, Dict[str, str]] = {
    "anmeldung": {
        "uk": "Анмельдунг",
        "en": "Anmeldung",
        "de": "Anmeldung",
        "pl": "Anmeldung",
        "tr": "Anmeldung",
        "ar": "Anmeldung",
    },
    "ummeldung": {
        "uk": "Уммельдунг",
        "en": "Ummeldung",
        "de": "Ummeldung",
        "pl": "Ummeldung",
        "tr": "Ummeldung",
        "ar": "Ummeldung",
    },
    "abmeldung": {
        "uk": "Абмельдунг",
        "en": "Abmeldung",
        "de": "Abmeldung",
        "pl": "Abmeldung",
        "tr": "Abmeldung",
        "ar": "Abmeldung",
    },
    "wohngeld": {
        "uk": "Вонгельд",
        "en": "Wohngeld",
        "de": "Wohngeld",
        "pl": "Wohngeld",
        "tr": "Wohngeld",
        "ar": "Wohngeld",
    },
    "kindergeld": {
        "uk": "Кіндергельд",
        "en": "Kindergeld",
        "de": "Kindergeld",
        "pl": "Kindergeld",
        "tr": "Kindergeld",
        "ar": "Kindergeld",
    },
    "buergergeld": {
        "uk": "Бюргергельд",
        "en": "Bürgergeld",
        "de": "Bürgergeld",
        "pl": "Bürgergeld",
        "tr": "Bürgergeld",
        "ar": "Bürgergeld",
    },
    "aufenthaltstitel": {
        "uk": "Дозвіл на перебування",
        "en": "Aufenthaltstitel",
        "de": "Aufenthaltstitel",
        "pl": "Aufenthaltstitel",
        "tr": "Aufenthaltstitel",
        "ar": "Aufenthaltstitel",
    },
    "verlaengerung_aufenthaltstitel": {
        "uk": "Продовження дозволу",
        "en": "Permit extension",
        "de": "Verlängerung Aufenthaltstitel",
        "pl": "Przedłużenie zezwolenia",
        "tr": "İzin uzatma",
        "ar": "تمديد التصريح",
    },
    "familienkasse": {
        "uk": "Сімейна каса",
        "en": "Familienkasse",
        "de": "Familienkasse",
        "pl": "Familienkasse",
        "tr": "Familienkasse",
        "ar": "Familienkasse",
    },
}

_HISTORY_HEADER: Dict[str, str] = {
    "uk": "📂 <b>Мої документи</b>\n\nОстанні замовлення:",
    "ua": "📂 <b>Мої документи</b>\n\nОстанні замовлення:",
    "en": "📂 <b>My Documents</b>\n\nRecent orders:",
    "de": "📂 <b>Meine Dokumente</b>\n\nLetzte Bestellungen:",
    "pl": "📂 <b>Moje dokumenty</b>\n\nOstatnie zamówienia:",
    "tr": "📂 <b>Belgelerim</b>\n\nSon siparişler:",
    "ar": "📂 <b>مستنداتي</b>\n\nالطلبات الأخيرة:",
}
_HISTORY_EMPTY: Dict[str, str] = {
    "uk": "📂 У вас ще немає замовлень.",
    "ua": "📂 У вас ще немає замовлень.",
    "en": "📂 You have no orders yet.",
    "de": "📂 Sie haben noch keine Bestellungen.",
    "pl": "📂 Nie masz jeszcze żadnych zamówień.",
    "tr": "📂 Henüz hiç siparişiniz yok.",
    "ar": "📂 ليس لديك أي طلبات بعد.",
}
_HISTORY_STATUS: Dict[str, Dict[str, str]] = {
    "paid": {
        "uk": "оплачено",
        "en": "paid",
        "de": "bezahlt",
        "pl": "opłacone",
        "tr": "ödendi",
        "ar": "مدفوع",
    },
    "sent": {
        "uk": "✅ надіслано",
        "en": "✅ sent",
        "de": "✅ gesendet",
        "pl": "✅ wysłano",
        "tr": "✅ gönderildi",
        "ar": "✅ مُرسَل",
    },
    "downloaded": {
        "uk": "✅ надіслано",
        "en": "✅ sent",
        "de": "✅ gesendet",
        "pl": "✅ wysłano",
        "tr": "✅ gönderildi",
        "ar": "✅ مُرسَل",
    },
    "pending": {
        "uk": "очікує",
        "en": "pending",
        "de": "ausstehend",
        "pl": "oczekujące",
        "tr": "bekliyor",
        "ar": "معلق",
    },
    "processing": {
        "uk": "обробка",
        "en": "processing",
        "de": "verarbeitung",
        "pl": "przetwarzanie",
        "tr": "işleniyor",
        "ar": "قيد المعالجة",
    },
}
_REDOWNLOAD_BTN: Dict[str, str] = {
    "uk": "📥 Отримати PDF знову",
    "ua": "📥 Отримати PDF знову",
    "en": "📥 Re-download PDF",
    "de": "📥 PDF erneut senden",
    "pl": "📥 Pobierz PDF ponownie",
    "tr": "📥 PDF'yi tekrar al",
    "ar": "📥 إعادة تنزيل PDF",
}
_OFFICIAL_FORM_HEADER: Dict[str, str] = {
    "uk": "🔗 <b>Офіційна сторінка</b>\n\nПосилання на урядовий сайт:",
    "ua": "🔗 <b>Офіційна сторінка</b>\n\nПосилання на урядовий сайт:",
    "en": "🔗 <b>Official Page</b>\n\nLink to the official government page:",
    "de": "🔗 <b>Offizielle Seite</b>\n\nLink zur offiziellen Regierungsseite:",
    "pl": "🔗 <b>Oficjalna strona</b>\n\nLink do oficjalnej strony rządowej:",
    "tr": "🔗 <b>Resmi Sayfa</b>\n\nResmi hükümet sayfasına bağlantı:",
    "ar": "🔗 <b>الصفحة الرسمية</b>\n\nرابط الصفحة الحكومية الرسمية:",
}
_OFFICIAL_FORM_NOTFOUND: Dict[str, str] = {
    "uk": "На жаль, посилання для цього документа недоступне.",
    "ua": "На жаль, посилання для цього документа недоступне.",
    "en": "Sorry, the link for this document is not available.",
    "de": "Leider ist der Link für dieses Dokument nicht verfügbar.",
    "pl": "Niestety link do tego dokumentu jest niedostępny.",
    "tr": "Üzgünüz, bu belge için bağlantı mevcut değil.",
    "ar": "عذرًا، الرابط لهذه الوثيقة غير متاح.",
}
_INSTRUCTIONS_HEADER: Dict[str, str] = {
    "uk": "📘 <b>Інструкція з подачі</b>",
    "ua": "📘 <b>Інструкція з подачі</b>",
    "en": "📘 <b>Submission Instructions</b>",
    "de": "📘 <b>Einreichungsanleitung</b>",
    "pl": "📘 <b>Instrukcja składania</b>",
    "tr": "📘 <b>Başvuru Talimatları</b>",
    "ar": "📘 <b>تعليمات التقديم</b>",
}
# One-liner shown under the header — directly sells value of following instructions
_INSTRUCTIONS_INTRO: Dict[str, str] = {
    "uk": "<i>💡 Дотримуйтесь цих кроків, щоб вашу заявку прийняли з першого разу.</i>",
    "ua": "<i>💡 Дотримуйтесь цих кроків, щоб вашу заявку прийняли з першого разу.</i>",
    "en": "<i>💡 Follow these steps so your application is accepted the first time.</i>",
    "de": "<i>💡 Folgen Sie diesen Schritten, damit Ihr Antrag beim ersten Mal angenommen wird.</i>",
    "pl": "<i>💡 Wykonaj te kroki, aby Twój wniosek został przyjęty za pierwszym razem.</i>",
    "tr": "<i>💡 Bu adımları takip et — başvurun ilk seferinde kabul edilsin.</i>",
    "ar": "<i>💡 اتّبع هذه الخطوات حتى يُقبل طلبك من أول مرة.</i>",
}
# Back button label after instructions
_INSTRUCTIONS_CONTINUE: Dict[str, str] = {
    "uk": "⬅️ Назад",
    "ua": "⬅️ Назад",
    "en": "⬅️ Back",
    "de": "⬅️ Zurück",
    "pl": "⬅️ Wróć",
    "tr": "⬅️ Geri",
    "ar": "⬅️ رجوع",
}
# Concise per-doc submission instructions (localized subset — EN/UK; others fall back to EN)
_SUBMISSION_INSTRUCTIONS: Dict[str, Dict[str, str]] = {
    "anmeldung": {
        "uk": (
            "1️⃣ Роздрукуйте заповнений PDF\n"
            "2️⃣ Підпишіть на сторінці підпису\n"
            "3️⃣ Візьміть документ, що засвідчує особу та підтвердження квартири від орендодавця\n"
            "4️⃣ Запишіться на Termin у Bürgeramt або прийдіть без запису (Warteticket)\n"
            "5️⃣ Здайте форму на місці — реєстрація займає 5–10 хвилин"
        ),
        "ua": (
            "1️⃣ Роздрукуйте заповнений PDF\n"
            "2️⃣ Підпишіть на сторінці підпису\n"
            "3️⃣ Візьміть документ, що засвідчує особу та підтвердження квартири від орендодавця\n"
            "4️⃣ Запишіться на Termin у Bürgeramt або прийдіть без запису (Warteticket)\n"
            "5️⃣ Здайте форму на місці — реєстрація займає 5–10 хвилин"
        ),
        "en": (
            "1️⃣ Print the filled PDF\n"
            "2️⃣ Sign on the signature page\n"
            "3️⃣ Bring your ID and the landlord confirmation (Wohnungsgeberbestätigung)\n"
            "4️⃣ Book a Termin at the Bürgeramt or take a walk-in queue ticket\n"
            "5️⃣ Submit in person — registration takes 5–10 minutes"
        ),
        "de": (
            "1️⃣ Ausgefülltes PDF ausdrucken\n"
            "2️⃣ Unterschreiben Sie auf der Unterschriftseite\n"
            "3️⃣ Personalausweis und Wohnungsgeberbestätigung mitbringen\n"
            "4️⃣ Termin beim Bürgeramt buchen oder Warteticket nehmen\n"
            "5️⃣ Vor Ort einreichen — Anmeldung dauert 5–10 Minuten"
        ),
        "pl": (
            "1️⃣ Wydrukuj wypełniony PDF\n"
            "2️⃣ Podpisz na stronie podpisu\n"
            "3️⃣ Zabierz dokument tożsamości i potwierdzenie od wynajmującego\n"
            "4️⃣ Umów wizytę w Bürgeramt lub weź bilet do kolejki\n"
            "5️⃣ Złóż osobiście — rejestracja zajmuje 5–10 minut"
        ),
        "tr": (
            "1️⃣ Doldurulmuş PDF'i yazdır\n"
            "2️⃣ İmza sayfasını imzala\n"
            "3️⃣ Kimlik ve ev sahibi onayını (Wohnungsgeberbestätigung) getir\n"
            "4️⃣ Bürgeramt'ta randevu al veya sıra numarası al\n"
            "5️⃣ Şahsen teslim et — kayıt 5–10 dakika sürer"
        ),
        "ar": (
            "1️⃣ اطبع الملف المعبأ\n"
            "2️⃣ وقّع في صفحة التوقيع\n"
            "3️⃣ أحضر الهوية وتأكيد صاحب العقار (Wohnungsgeberbestätigung)\n"
            "4️⃣ احجز موعداً في Bürgeramt أو خذ رقم الانتظار\n"
            "5️⃣ قدّمه شخصياً — التسجيل يستغرق 5–10 دقائق"
        ),
    },
    "ummeldung": {
        "uk": (
            "1️⃣ Роздрукуйте та підпишіть PDF\n"
            "2️⃣ Підготуйте підтвердження від орендодавця нової квартири\n"
            "3️⃣ Запишіться або прийдіть без запису до Bürgeramt\n"
            "4️⃣ Подайте форму особисто"
        ),
        "ua": (
            "1️⃣ Роздрукуйте та підпишіть PDF\n"
            "2️⃣ Підготуйте підтвердження від орендодавця нової квартири\n"
            "3️⃣ Запишіться або прийдіть без запису до Bürgeramt\n"
            "4️⃣ Подайте форму особисто"
        ),
        "en": (
            "1️⃣ Print and sign the PDF\n"
            "2️⃣ Get the landlord confirmation for your new address\n"
            "3️⃣ Book or walk in to your Bürgeramt\n"
            "4️⃣ Submit the form in person"
        ),
        "de": (
            "1️⃣ PDF ausdrucken und unterschreiben\n"
            "2️⃣ Wohnungsgeberbestätigung der neuen Wohnung besorgen\n"
            "3️⃣ Termin beim Bürgeramt buchen oder vor Ort erscheinen\n"
            "4️⃣ Formular persönlich einreichen"
        ),
        "pl": (
            "1️⃣ Wydrukuj i podpisz PDF\n"
            "2️⃣ Zdobądź potwierdzenie od wynajmującego nowego mieszkania\n"
            "3️⃣ Umów wizytę lub przyjdź do Bürgeramt bez zapisu\n"
            "4️⃣ Złóż formularz osobiście"
        ),
        "tr": (
            "1️⃣ PDF'i yazdır ve imzala\n"
            "2️⃣ Yeni adres için ev sahibi onayını al\n"
            "3️⃣ Bürgeramt'ta randevu al veya sırasız gel\n"
            "4️⃣ Formu şahsen teslim et"
        ),
        "ar": (
            "1️⃣ اطبع الملف ووقّع عليه\n"
            "2️⃣ احصل على تأكيد صاحب العقار الجديد\n"
            "3️⃣ احجز موعداً أو تفضّل بدون حجز إلى Bürgeramt\n"
            "4️⃣ قدّم النموذج شخصياً"
        ),
    },
    "abmeldung": {
        "en": (
            "1️⃣ Print and sign the PDF\n"
            "2️⃣ Submit at the Bürgeramt in person OR send by post\n"
            "3️⃣ No appointment needed in most cities\n"
            "4️⃣ Keep the confirmation (Abmeldebestätigung) you receive"
        ),
        "uk": (
            "1️⃣ Роздрукуйте та підпишіть PDF\n"
            "2️⃣ Подайте особисто у Bürgeramt АБО надішліть поштою\n"
            "3️⃣ Запис зазвичай не потрібен\n"
            "4️⃣ Збережіть підтвердження (Abmeldebestätigung)"
        ),
        "ua": (
            "1️⃣ Роздрукуйте та підпишіть PDF\n"
            "2️⃣ Подайте особисто у Bürgeramt АБО надішліть поштою\n"
            "3️⃣ Запис зазвичай не потрібен\n"
            "4️⃣ Збережіть підтвердження (Abmeldebestätigung)"
        ),
        "de": (
            "1️⃣ PDF ausdrucken und unterschreiben\n"
            "2️⃣ Beim Bürgeramt persönlich abgeben ODER per Post senden\n"
            "3️⃣ In den meisten Städten kein Termin nötig\n"
            "4️⃣ Abmeldebestätigung aufbewahren"
        ),
        "pl": (
            "1️⃣ Wydrukuj i podpisz PDF\n"
            "2️⃣ Złóż osobiście w Bürgeramt LUB wyślij pocztą\n"
            "3️⃣ W większości miast wizyta nie jest wymagana\n"
            "4️⃣ Zachowaj potwierdzenie (Abmeldebestätigung)"
        ),
        "tr": (
            "1️⃣ PDF'i yazdır ve imzala\n"
            "2️⃣ Bürgeramt'a şahsen teslim et VEYA posta ile gönder\n"
            "3️⃣ Çoğu şehirde randevu gerekmez\n"
            "4️⃣ Aldığın onayı (Abmeldebestätigung) sakla"
        ),
        "ar": (
            "1️⃣ اطبع الملف ووقّع عليه\n"
            "2️⃣ قدّمه شخصياً في Bürgeramt أو أرسله بالبريد\n"
            "3️⃣ لا حاجة لموعد في معظم المدن\n"
            "4️⃣ احتفظ بالتأكيد (Abmeldebestätigung)"
        ),
    },
    "wohngeld": {
        "en": (
            "1️⃣ Print the filled PDF\n"
            "2️⃣ Attach income documents (payslips, tax notice, etc.)\n"
            "3️⃣ Submit at the Wohngeldstelle of your city/district\n"
            "4️⃣ Processing takes 2–6 weeks"
        ),
        "uk": (
            "1️⃣ Роздрукуйте PDF\n"
            "2️⃣ Додайте документи про доходи (розрахунки, повідомлення про податки тощо)\n"
            "3️⃣ Подайте у Wohngeldstelle вашого міста/району\n"
            "4️⃣ Розгляд займає 2–6 тижнів"
        ),
        "de": (
            "1️⃣ Ausgefülltes PDF ausdrucken\n"
            "2️⃣ Einkommensnachweise beifügen (Gehaltsabrechnungen, Steuerbescheid usw.)\n"
            "3️⃣ Bei der Wohngeldstelle Ihrer Stadt einreichen\n"
            "4️⃣ Bearbeitung dauert 2–6 Wochen"
        ),
    },
    "kindergeld": {
        "en": (
            "1️⃣ Print the filled PDF\n"
            "2️⃣ Attach birth certificate(s) of the child(ren)\n"
            "3️⃣ Send by post to the Familienkasse in your region OR submit online\n"
            "4️⃣ Processing takes 4–8 weeks"
        ),
        "uk": (
            "1️⃣ Роздрукуйте PDF\n"
            "2️⃣ Додайте свідоцтво(-а) про народження дитини(-ей)\n"
            "3️⃣ Надішліть поштою до Familienkasse вашого регіону АБО подайте онлайн\n"
            "4️⃣ Розгляд займає 4–8 тижнів"
        ),
        "de": (
            "1️⃣ PDF ausdrucken\n"
            "2️⃣ Geburtsurkunde(n) des Kindes / der Kinder beifügen\n"
            "3️⃣ Per Post an die Familienkasse senden ODER online einreichen\n"
            "4️⃣ Bearbeitung dauert 4–8 Wochen"
        ),
    },
    "buergergeld": {
        "en": (
            "1️⃣ Print the filled PDF and sign on the last page\n"
            "2️⃣ Attach bank statements (3 months), rental contract, and ID copy\n"
            "3️⃣ Submit at your local Jobcenter in person or by post\n"
            "4️⃣ Processing takes 2–4 weeks\n"
            "⚠️ Unsigned forms are automatically rejected"
        ),
        "uk": (
            "1️⃣ Роздрукуйте та підпишіть PDF на останній сторінці\n"
            "2️⃣ Додайте виписки з банку (3 місяці), договір оренди та копію ID\n"
            "3️⃣ Подайте особисто або поштою до вашого Jobcenter\n"
            "4️⃣ Розгляд займає 2–4 тижні\n"
            "⚠️ Форми без підпису відхиляються автоматично"
        ),
        "ua": (
            "1️⃣ Роздрукуйте та підпишіть PDF на останній сторінці\n"
            "2️⃣ Додайте виписки з банку (3 місяці), договір оренди та копію ID\n"
            "3️⃣ Подайте особисто або поштою до вашого Jobcenter\n"
            "4️⃣ Розгляд займає 2–4 тижні\n"
            "⚠️ Форми без підпису відхиляються автоматично"
        ),
        "de": (
            "1️⃣ PDF ausdrucken und auf der letzten Seite unterschreiben\n"
            "2️⃣ Kontoauszüge (3 Monate), Mietvertrag und Ausweis-Kopie beifügen\n"
            "3️⃣ Beim Jobcenter persönlich oder per Post einreichen\n"
            "4️⃣ Bearbeitung dauert 2–4 Wochen\n"
            "⚠️ Nicht unterschriebene Anträge werden automatisch abgelehnt"
        ),
        "pl": (
            "1️⃣ Wydrukuj wypełniony PDF i podpisz na ostatniej stronie\n"
            "2️⃣ Dołącz wyciągi bankowe (3 miesiące), umowę najmu i kopię dowodu\n"
            "3️⃣ Złóż osobiście lub pocztą w swoim Jobcenter\n"
            "4️⃣ Rozpatrzenie trwa 2–4 tygodnie\n"
            "⚠️ Formularze bez podpisu są automatycznie odrzucane"
        ),
        "tr": (
            "1️⃣ Doldurulmuş PDF'i yazdır ve son sayfayı imzala\n"
            "2️⃣ Banka ekstrelerini (3 ay), kira sözleşmesini ve kimlik kopyasını ekle\n"
            "3️⃣ Jobcenter'a şahsen veya posta ile gönder\n"
            "4️⃣ İşlem 2–4 hafta sürer\n"
            "⚠️ İmzasız formlar otomatik reddedilir"
        ),
        "ar": (
            "1️⃣ اطبع الملف المعبأ ووقّع في الصفحة الأخيرة\n"
            "2️⃣ أرفق كشوف الحساب (3 أشهر) وعقد الإيجار ونسخة الهوية\n"
            "3️⃣ قدّمه شخصياً أو بالبريد إلى Jobcenter\n"
            "4️⃣ المعالجة تستغرق 2–4 أسابيع\n"
            "⚠️ النماذج غير الموقّعة تُرفض تلقائياً"
        ),
    },
    "aufenthaltstitel": {
        "en": (
            "1️⃣ Book a Termin at the Ausländerbehörde (mandatory — no walk-ins)\n"
            "2️⃣ Bring printed PDF, passport, biometric photo, and all supporting documents\n"
            "3️⃣ Pay the fee at the office (€100–€200 depending on permit type)\n"
            "4️⃣ Processing may take several weeks after the appointment"
        ),
        "uk": (
            "1️⃣ Запишіться до Ausländerbehörde (обов'язково — без запису не приймають)\n"
            "2️⃣ Візьміть PDF, паспорт, біометричне фото та всі підтвердні документи\n"
            "3️⃣ Оплатіть збір на місці (€100–€200 залежно від типу дозволу)\n"
            "4️⃣ Обробка може зайняти кілька тижнів після запису"
        ),
        "de": (
            "1️⃣ Termin bei der Ausländerbehörde buchen (Pflicht — keine Laufkundschaft)\n"
            "2️⃣ PDF ausdrucken, Reisepass, biometrisches Foto und alle Unterlagen mitbringen\n"
            "3️⃣ Gebühr vor Ort bezahlen (€100–€200 je nach Erlaubnisart)\n"
            "4️⃣ Bearbeitung kann nach dem Termin mehrere Wochen dauern"
        ),
    },
    "verlaengerung_aufenthaltstitel": {
        "en": (
            "1️⃣ Book a Termin at the Ausländerbehörde before your current permit expires\n"
            "2️⃣ Bring current permit, passport, printed PDF, and supporting documents\n"
            "3️⃣ Apply at least 6–8 weeks before expiry to avoid gaps"
        ),
        "uk": (
            "1️⃣ Запишіться до Ausländerbehörde до закінчення чинного дозволу\n"
            "2️⃣ Візьміть поточний дозвіл, паспорт, PDF та підтвердні документи\n"
            "3️⃣ Подавайте щонайменше за 6–8 тижнів до закінчення терміну"
        ),
        "de": (
            "1️⃣ Termin bei der Ausländerbehörde vor Ablauf des aktuellen Titels buchen\n"
            "2️⃣ Aktuellen Aufenthaltstitel, Reisepass, PDF und Unterlagen mitbringen\n"
            "3️⃣ Mindestens 6–8 Wochen vor Ablauf beantragen"
        ),
    },
}

_SUBMISSION_GUIDE_GENERIC: Dict[str, str] = {
    "uk": (
        "1️⃣ Роздрукуйте PDF\n"
        "2️⃣ Підпишіть документ\n"
        "3️⃣ Додайте необхідні документи\n"
        "4️⃣ Подайте у Bürgeramt або онлайн\n\n"
        "💡 Візьміть із собою паспорт"
    ),
    "ua": (
        "1️⃣ Роздрукуйте PDF\n"
        "2️⃣ Підпишіть документ\n"
        "3️⃣ Додайте необхідні документи\n"
        "4️⃣ Подайте у Bürgeramt або онлайн\n\n"
        "💡 Візьміть із собою паспорт"
    ),
    "en": (
        "1️⃣ Print the PDF\n"
        "2️⃣ Sign the document\n"
        "3️⃣ Attach required documents\n"
        "4️⃣ Submit to Bürgeramt or online\n\n"
        "💡 Bring your passport"
    ),
    "de": (
        "1️⃣ PDF ausdrucken\n"
        "2️⃣ Unterschreiben\n"
        "3️⃣ Unterlagen beifügen\n"
        "4️⃣ Beim Bürgeramt oder online einreichen\n\n"
        "💡 Reisepass mitnehmen"
    ),
    "pl": (
        "1️⃣ Wydrukuj PDF\n"
        "2️⃣ Podpisz dokument\n"
        "3️⃣ Dołącz wymagane dokumenty\n"
        "4️⃣ Złóż w urzędzie lub online\n\n"
        "💡 Zabierz paszport"
    ),
    "tr": (
        "1️⃣ PDF'i yazdır\n"
        "2️⃣ İmzala\n"
        "3️⃣ Gerekli belgeleri ekle\n"
        "4️⃣ Kuruma veya online gönder\n\n"
        "💡 Pasaportunu getir"
    ),
    "ar": (
        "1️⃣ اطبع الملف\n"
        "2️⃣ وقّع عليه\n"
        "3️⃣ أرفق المستندات المطلوبة\n"
        "4️⃣ قدّمه في الدائرة أو عبر الإنترنت\n\n"
        "💡 أحضر جواز السفر"
    ),
}

_REDOWNLOAD_NO_PDF: Dict[str, str] = {
    "uk": "😔 PDF для цього замовлення не збережено. Зверніться до підтримки.",
    "ua": "😔 PDF для цього замовлення не збережено. Зверніться до підтримки.",
    "en": "😔 No PDF found for this order. Please contact support.",
    "de": "😔 Für diese Bestellung wurde kein PDF gespeichert. Bitte wenden Sie sich an den Support.",
    "pl": "😔 Nie znaleziono PDF dla tego zamówienia. Skontaktuj się z pomocą.",
    "tr": "😔 Bu sipariş için PDF bulunamadı. Lütfen destek ile iletişime geçin.",
    "ar": "😔 لم يُعثر على ملف PDF لهذا الطلب. يرجى التواصل مع الدعم.",
}
_REDOWNLOAD_SENDING: Dict[str, str] = {
    "uk": "📤 Надсилаю ваш PDF...",
    "ua": "📤 Надсилаю ваш PDF...",
    "en": "📤 Sending your PDF...",
    "de": "📤 Ich sende Ihr PDF...",
    "pl": "📤 Wysyłam Twój PDF...",
    "tr": "📤 PDF'niz gönderiliyor...",
    "ar": "📤 جارٍ إرسال ملف PDF...",
}


async def handle_post_payment_actions(callback: types.CallbackQuery):
    """
    Handle post_payment:official_form:{doc_type} and post_payment:instructions:{doc_type}
    callbacks from the post-payment inline menu.
    """
    await callback.answer()

    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    _lang = "uk" if lang == "ua" else lang
    if _lang not in ("uk", "en", "de", "pl", "tr", "ar"):
        _lang = "en"

    # Parse: "post_payment:official_form:anmeldung" / "post_payment:instructions:anmeldung"
    #         / "post_payment:what_next:anmeldung"
    parts = (callback.data or "").split(":", 2)
    if len(parts) < 3:
        return
    action = parts[1]  # "official_form" | "instructions" | "what_next"
    doc_type = parts[2]  # e.g. "anmeldung"

    if action == "official_form":
        try:
            from backend.document_config import get_official_link

            url = get_official_link(doc_type)
        except Exception:
            url = ""

        if url:
            header = _OFFICIAL_FORM_HEADER.get(_lang, _OFFICIAL_FORM_HEADER["en"])
            _open_btn_labels = {
                "uk": "🌐 Відкрити", "ua": "🌐 Відкрити",
                "en": "🌐 Open", "de": "🌐 Öffnen",
                "pl": "🌐 Otwórz", "tr": "🌐 Aç", "ar": "🌐 فتح",
            }
            _open_label = _open_btn_labels.get(_lang, _open_btn_labels["en"])
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton(_open_label, url=url))
            await callback.message.answer(header, parse_mode="HTML", reply_markup=kb)
        else:
            await callback.message.answer(
                _OFFICIAL_FORM_NOTFOUND.get(_lang, _OFFICIAL_FORM_NOTFOUND["en"])
            )

    elif action == "instructions":
        doc_instructions = _SUBMISSION_INSTRUCTIONS.get(doc_type, {})
        text = doc_instructions.get(_lang) or doc_instructions.get("en")
        if not text:
            text = _SUBMISSION_GUIDE_GENERIC.get(_lang, _SUBMISSION_GUIDE_GENERIC["en"])
        header = _INSTRUCTIONS_HEADER.get(_lang, _INSTRUCTIONS_HEADER["en"])
        intro = _INSTRUCTIONS_INTRO.get(_lang, _INSTRUCTIONS_INTRO["en"])
        _continue_label = _INSTRUCTIONS_CONTINUE.get(_lang, _INSTRUCTIONS_CONTINUE["en"])
        _termin_label = _BTN_FIND_TERMIN.get(_lang, _BTN_FIND_TERMIN["en"])
        from handlers.nav import nav_home_text as _nav_home
        back_kb = InlineKeyboardMarkup(row_width=2)
        back_kb.add(
            InlineKeyboardButton(_continue_label, callback_data="back_to_main_menu"),
            InlineKeyboardButton(_termin_label, callback_data="find_termin"),
        )
        back_kb.add(InlineKeyboardButton(_nav_home(_lang), callback_data="main_menu"))
        await callback.message.answer(
            f"{header}\n\n{intro}\n\n{text}",
            parse_mode="HTML",
            reply_markup=back_kb,
        )

    elif action == "what_next":
        # Per-document "What next?" FAQ — tells user the 3 practical steps after they received the doc
        _WHAT_NEXT_TEXTS = {
            "anmeldung": {
                "uk": (
                    "📋 <b>Що далі після Anmeldung?</b>\n\n"
                    "1️⃣ Роздрукуйте заповнений зразок та офіційний бланк\n"
                    "2️⃣ Запишіться на прийом у <b>Bürgeramt</b> вашого міста\n"
                    "3️⃣ Прийдіть із документами: паспорт + бланк\n"
                    "4️⃣ Отримайте <i>Meldebescheinigung</i> на місці\n\n"
                    "⏱ Процедура займає ~10 хв."
                ),
                "en": (
                    "📋 <b>What next after Anmeldung?</b>\n\n"
                    "1️⃣ Print your filled sample and the official form\n"
                    "2️⃣ Book an appointment at your local <b>Bürgeramt</b>\n"
                    "3️⃣ Bring: passport + form\n"
                    "4️⃣ Receive <i>Meldebescheinigung</i> on the spot\n\n"
                    "⏱ Takes ~10 minutes."
                ),
                "de": (
                    "📋 <b>Was kommt nach der Anmeldung?</b>\n\n"
                    "1️⃣ Drucken Sie das ausgefüllte Muster und das offizielle Formular\n"
                    "2️⃣ Termin beim <b>Bürgeramt</b> vereinbaren\n"
                    "3️⃣ Mitbringen: Reisepass + Formular\n"
                    "4️⃣ <i>Meldebescheinigung</i> vor Ort erhalten\n\n"
                    "⏱ Dauer ca. 10 Minuten."
                ),
            },
            "abmeldung": {
                "uk": (
                    "📋 <b>Що далі після Abmeldung?</b>\n\n"
                    "1️⃣ Роздрукуйте заповнений зразок\n"
                    "2️⃣ Подайте у Bürgeramt особисто або поштою\n"
                    "3️⃣ Отримайте <i>Abmeldebestätigung</i>\n\n"
                    "ℹ️ Abmeldung можна зробити до виїзду або протягом 2 тижнів після."
                ),
                "en": (
                    "📋 <b>What next after Abmeldung?</b>\n\n"
                    "1️⃣ Print the filled sample\n"
                    "2️⃣ Submit at Bürgeramt in person or by mail\n"
                    "3️⃣ Receive <i>Abmeldebestätigung</i>\n\n"
                    "ℹ️ Can be done before moving out or within 2 weeks after."
                ),
                "de": (
                    "📋 <b>Was kommt nach der Abmeldung?</b>\n\n"
                    "1️⃣ Ausgefülltes Muster ausdrucken\n"
                    "2️⃣ Im Bürgeramt persönlich abgeben oder per Post schicken\n"
                    "3️⃣ <i>Abmeldebestätigung</i> erhalten\n\n"
                    "ℹ️ Möglich vor dem Auszug oder innerhalb von 2 Wochen danach."
                ),
            },
        }

        _WHAT_NEXT_GENERIC = {
            "uk": (
                "📋 <b>Що далі?</b>\n\n"
                "1️⃣ Роздрукуйте отриманий заповнений зразок\n"
                "2️⃣ Перенесіть дані у офіційний бланк\n"
                "3️⃣ Подайте у відповідний орган\n\n"
                "Офіційний бланк доступний за кнопкою «{official_form}» вище."
            ),
            "en": (
                "📋 <b>What next?</b>\n\n"
                "1️⃣ Print your filled sample\n"
                "2️⃣ Transfer the data to the official form\n"
                "3️⃣ Submit to the relevant authority\n\n"
                "The official form is available via the «{official_form}» button above."
            ),
            "de": (
                "📋 <b>Was nun?</b>\n\n"
                "1️⃣ Ausgefülltes Muster ausdrucken\n"
                "2️⃣ Daten in offizielle Formular übertragen\n"
                "3️⃣ Bei der zuständigen Behörde einreichen\n\n"
                "Das offizielle Formular finden Sie über die Schaltfläche «{official_form}» oben."
            ),
            "pl": (
                "📋 <b>Co dalej?</b>\n\n"
                "1️⃣ Wydrukuj wypełniony wzór\n"
                "2️⃣ Przepisz dane do oficjalnego formularza\n"
                "3️⃣ Złóż w odpowiednim urzędzie\n\n"
                "Oficjalny formularz jest dostępny przez przycisk «{official_form}» powyżej."
            ),
            "tr": (
                "📋 <b>Sırada ne var?</b>\n\n"
                "1️⃣ Doldurulmuş örneği yazdırın\n"
                "2️⃣ Verileri resmi forma aktarın\n"
                "3️⃣ İlgili kuruma teslim edin\n\n"
                "Resmi form, yukarıdaki «{official_form}» düğmesiyle erişilebilir."
            ),
            "ar": (
                "📋 <b>ماذا بعد؟</b>\n\n"
                "1️⃣ اطبع النموذج المعبأ\n"
                "2️⃣ انقل البيانات إلى النموذج الرسمي\n"
                "3️⃣ قدّمه إلى الجهة المختصة\n\n"
                "النموذج الرسمي متاح عبر زر «{official_form}» أعلاه."
            ),
        }

        _doc_texts = _WHAT_NEXT_TEXTS.get(doc_type, {})
        text = _doc_texts.get(_lang) or _doc_texts.get("en")
        if not text:
            _off_btn_label = _BTN_OFFICIAL_FORM.get(_lang, _BTN_OFFICIAL_FORM["en"])
            text = _WHAT_NEXT_GENERIC.get(_lang, _WHAT_NEXT_GENERIC["en"]).format(
                official_form=_off_btn_label
            )
        await callback.message.answer(text, parse_mode="HTML")

    logger.info(
        "POST_PAYMENT_ACTION: user=%s doc_type=%s action=%s",
        user_id,
        doc_type,
        action,
    )


async def handle_redownload_pdf(callback: types.CallbackQuery):
    """
    Handle redownload_pdf:{order_id} callback.
    Re-sends the stored PDF for a completed order, or regenerates it if needed.
    """
    await callback.answer()

    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    _lang = "uk" if lang == "ua" else lang
    if _lang not in ("uk", "en", "de", "pl", "tr", "ar"):
        _lang = "en"

    parts = (callback.data or "").split(":", 1)
    order_id_str = parts[1] if len(parts) == 2 else ""

    db = get_db()
    order = None
    if order_id_str.isdigit():
        try:
            order = db.get_order(int(order_id_str))
        except Exception:
            pass

    if not order:
        await callback.message.answer(
            _REDOWNLOAD_NO_PDF.get(_lang, _REDOWNLOAD_NO_PDF["en"])
        )
        return

    file_path = order.get("file_path") or ""

    import os as _os

    if file_path and _os.path.exists(file_path):
        await callback.message.answer(
            _REDOWNLOAD_SENDING.get(_lang, _REDOWNLOAD_SENDING["en"])
        )
        try:
            with open(file_path, "rb") as f:
                await callback.message.answer_document(f)
            logger.info(
                "REDOWNLOAD_PDF_SENT: user=%s order=%s path=%s",
                user_id,
                order_id_str,
                file_path,
            )
        except Exception as _e:
            logger.warning(
                "REDOWNLOAD_PDF_FAILED: user=%s order=%s err=%s",
                user_id,
                order_id_str,
                _e,
            )
            await callback.message.answer(
                _REDOWNLOAD_NO_PDF.get(_lang, _REDOWNLOAD_NO_PDF["en"])
            )
    else:
        # File deleted from disk — try to regenerate
        doc_type = order.get("doc_type", "")
        delivered = order.get("delivered", False) or order.get("status") in (
            "sent",
            "downloaded",
        )
        if delivered and doc_type:
            await callback.message.answer(
                _REDOWNLOAD_SENDING.get(_lang, _REDOWNLOAD_SENDING["en"])
            )
            try:
                bot_instance = callback.bot
                await deliver_document_after_payment(bot_instance, int(order_id_str))
                logger.info(
                    "REDOWNLOAD_REGENERATED: user=%s order=%s", user_id, order_id_str
                )
            except Exception as _re:
                logger.warning(
                    "REDOWNLOAD_REGEN_FAILED: user=%s order=%s err=%s",
                    user_id,
                    order_id_str,
                    _re,
                )
                await callback.message.answer(
                    _REDOWNLOAD_NO_PDF.get(_lang, _REDOWNLOAD_NO_PDF["en"])
                )
        else:
            await callback.message.answer(
                _REDOWNLOAD_NO_PDF.get(_lang, _REDOWNLOAD_NO_PDF["en"])
            )


async def handle_submission_guide(callback: types.CallbackQuery):
    """
    Show localized step-by-step submission instructions.
    Callback data: "submission_guide:{doc_type}" or just "submission_guide".
    Priority: doc-specific lang → doc-specific EN → generic guide.
    Includes conversion intro line and back-to-menu nudge to prevent dead-end UX.
    """
    await callback.answer()

    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    _lang = "uk" if lang == "ua" else lang
    if _lang not in ("uk", "en", "de", "pl", "tr", "ar"):
        _lang = "en"

    parts = (callback.data or "").split(":", 1)
    doc_type = parts[1] if len(parts) == 2 else "generic"

    doc_instructions = _SUBMISSION_INSTRUCTIONS.get(doc_type, {})
    body = (
        doc_instructions.get(_lang)
        or doc_instructions.get("en")
        or _SUBMISSION_GUIDE_GENERIC.get(_lang, _SUBMISSION_GUIDE_GENERIC["en"])
    )

    header = _INSTRUCTIONS_HEADER.get(_lang, _INSTRUCTIONS_HEADER["en"])
    intro = _INSTRUCTIONS_INTRO.get(_lang, _INSTRUCTIONS_INTRO["en"])
    full_text = f"{header}\n\n{intro}\n\n{body}"

    # Row 1: ⬅️ Back | 📍 Find Termin (upsell — leads to second product)
    _continue_label = _INSTRUCTIONS_CONTINUE.get(_lang, _INSTRUCTIONS_CONTINUE["en"])
    _termin_label = _BTN_FIND_TERMIN.get(_lang, _BTN_FIND_TERMIN["en"])
    from handlers.nav import nav_home_text as _nav_home
    back_kb = InlineKeyboardMarkup(row_width=2)
    back_kb.add(
        InlineKeyboardButton(_continue_label, callback_data="back_to_main_menu"),
        InlineKeyboardButton(_termin_label, callback_data="find_termin"),
    )
    back_kb.add(InlineKeyboardButton(_nav_home(_lang), callback_data="main_menu"))

    await callback.message.answer(full_text, parse_mode="HTML", reply_markup=back_kb)


async def handle_sample_preview(callback: types.CallbackQuery):
    """
    Show a watermarked preview of the requested document type BEFORE payment.
    Uses create_template_snippet_image with anonymous sample data.
    Falls back to a localized text description if image generation fails.
    callback_data: "sample_preview:{doc_type}"
    """
    await callback.answer()

    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    _lang = "uk" if lang == "ua" else lang
    if _lang not in ("uk", "en", "de", "pl", "tr", "ar"):
        _lang = "en"

    parts = (callback.data or "").split(":", 1)
    doc_type = parts[1] if len(parts) == 2 else "unknown"

    _PREVIEW_INTRO: Dict[str, str] = {
        "uk": "📄 <b>Приклад заповненого документа</b>\n\n⚠️ Це демо-зразок з тестовими даними. Ваш документ буде заповнений вашими даними.",
        "ua": "📄 <b>Приклад заповненого документа</b>\n\n⚠️ Це демо-зразок з тестовими даними. Ваш документ буде заповнений вашими даними.",
        "en": "📄 <b>Example filled document</b>\n\n⚠️ This is a demo sample with test data. Your document will be filled with your actual information.",
        "de": "📄 <b>Beispiel ausgefülltes Dokument</b>\n\n⚠️ Dies ist eine Demo mit Testdaten. Ihr Dokument wird mit Ihren echten Daten ausgefüllt.",
        "pl": "📄 <b>Przykładowy wypełniony dokument</b>\n\n⚠️ To jest próbka demo z danymi testowymi. Twój dokument zostanie wypełniony Twoimi danymi.",
        "tr": "📄 <b>Doldurulmuş belge örneği</b>\n\n⚠️ Bu, test verileriyle hazırlanmış bir demo örneğidir. Belgeniz gerçek bilgilerinizle doldurulacak.",
        "ar": "📄 <b>مثال على مستند مملوء</b>\n\n⚠️ هذا نموذج تجريبي ببيانات اختبارية. مستندك سيُملأ ببياناتك الحقيقية.",
    }
    _PREVIEW_FALLBACK: Dict[str, str] = {
        "uk": "✅ Ви отримаєте:\n• Офіційний бланк, заповнений вашими даними\n• Перевірені формати (дати, адреси, IBAN)\n• Готовий до подачі PDF без помилок",
        "ua": "✅ Ви отримаєте:\n• Офіційний бланк, заповнений вашими даними\n• Перевірені формати (дати, адреси, IBAN)\n• Готовий до подачі PDF без помилок",
        "en": "✅ You will receive:\n• Official form filled with your data\n• Verified formats (dates, addresses, IBAN)\n• Error-free PDF ready to submit",
        "de": "✅ Sie erhalten:\n• Offizielles Formular mit Ihren Daten\n• Geprüfte Formate (Daten, Adressen, IBAN)\n• Fehlerfreies PDF zur Einreichung",
        "pl": "✅ Otrzymasz:\n• Oficjalny formularz wypełniony Twoimi danymi\n• Zweryfikowane formaty (daty, adresy, IBAN)\n• PDF gotowy do złożenia bez błędów",
        "tr": "✅ Alacaklarınız:\n• Verilerinizle doldurulmuş resmi form\n• Doğrulanmış formatlar (tarihler, adresler, IBAN)\n• Hatasız, teslime hazır PDF",
        "ar": "✅ ستحصل على:\n• نموذج رسمي مملوء ببياناتك\n• تنسيقات محققة (تواريخ، عناوين، IBAN)\n• ملف PDF خالٍ من الأخطاء، جاهز للتقديم",
    }

    intro = _PREVIEW_INTRO.get(_lang, _PREVIEW_INTRO["en"])

    # Try to generate a real watermarked snippet image
    _img_bytes = None
    try:
        import asyncio as _aio
        from backend.pdf_preview import create_template_snippet_image
        _sample_data = {
            "first_name": "Max", "last_name": "Mustermann",
            "birth_date": "01.01.1990", "street": "Musterstraße 1",
            "city": "Berlin", "zip": "10115",
        }
        _img_bytes = await _aio.get_event_loop().run_in_executor(
            None,
            lambda: create_template_snippet_image(doc_type, _sample_data, lang=_lang),
        )
    except Exception as _prev_err:
        logger.debug("SAMPLE_PREVIEW_IMG_FAIL: doc=%s err=%s", doc_type, _prev_err)

    if _img_bytes:
        from aiogram.types import InputFile as _IF
        import io as _io
        await callback.message.answer_photo(
            photo=_IF(_io.BytesIO(_img_bytes), filename="sample.png"),
            caption=intro,
            parse_mode="HTML",
        )
    else:
        # Image not available — send text description (always works)
        fallback = _PREVIEW_FALLBACK.get(_lang, _PREVIEW_FALLBACK["en"])
        await callback.message.answer(
            f"{intro}\n\n{fallback}",
            parse_mode="HTML",
        )


async def handle_my_docs(message: types.Message):
    """
    /mydocs command — shows the user's last 5 paid orders with status and re-download button.
    """
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    _lang = "uk" if lang == "ua" else lang
    if _lang not in ("uk", "en", "de", "pl", "tr", "ar"):
        _lang = "en"

    db = get_db()
    try:
        orders = db.get_user_orders(user_id, limit=5)
    except Exception:
        orders = []

    # Filter: only paid/sent/downloaded orders worth showing
    paid_orders = [
        o
        for o in orders
        if o.get("status") in ("paid", "sent", "downloaded", "processing")
    ]

    if not paid_orders:
        await message.answer(
            _HISTORY_EMPTY.get(_lang, _HISTORY_EMPTY["en"]),
            parse_mode="HTML",
        )
        return

    await message.answer(
        _HISTORY_HEADER.get(_lang, _HISTORY_HEADER["en"]),
        parse_mode="HTML",
    )

    for order in paid_orders:
        order_id = order.get("id") or order.get("order_id")
        doc_type = (order.get("doc_type") or "").lower()
        status = order.get("status", "")
        created_at = (order.get("created_at") or "")[:10]  # YYYY-MM-DD
        amount = order.get("amount") or order.get("price") or 0

        doc_label_map = _DOC_TYPE_LABELS.get(doc_type, {})
        doc_label = doc_label_map.get(_lang) or doc_label_map.get("en") or doc_type

        status_map = _HISTORY_STATUS.get(status, {})
        status_label = status_map.get(_lang) or status_map.get("en") or status

        try:
            price_str = f"€{float(amount):.2f}"
        except Exception:
            price_str = ""

        line = f"📄 <b>{doc_label}</b>"
        if created_at:
            line += f" — {created_at}"
        if price_str:
            line += f" ({price_str})"
        line += f"\n{status_label}"

        kb = InlineKeyboardMarkup()
        if status in ("sent", "downloaded") and order_id:
            kb.add(
                InlineKeyboardButton(
                    _REDOWNLOAD_BTN.get(_lang, _REDOWNLOAD_BTN["en"]),
                    callback_data=f"redownload_pdf:{order_id}",
                )
            )

        await message.answer(
            line, parse_mode="HTML", reply_markup=kb if kb.inline_keyboard else None
        )

    logger.info("MY_DOCS_SHOWN: user=%s count=%s", user_id, len(paid_orders))


# ============================================================================
# REGISTER (PUBLIC API)
# ============================================================================


def register_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(
        initiate_payment, lambda c: c.data.startswith("pay_")
    )
    dp.register_callback_query_handler(
        initiate_payment, lambda c: c.data and c.data.startswith("paypdf_")
    )
    dp.register_callback_query_handler(
        initiate_payment, lambda c: c.data and c.data.startswith("paybundle_")
    )
    dp.register_callback_query_handler(
        initiate_payment, lambda c: c.data and c.data.startswith("payconfirm_")
    )
    dp.register_callback_query_handler(
        initiate_payment, lambda c: c.data and c.data.startswith("paydisclaim_")
    )
    dp.register_callback_query_handler(
        check_payment_status, lambda c: c.data.startswith("check_payment_")
    )
    # post-payment menu actions (Official form / What next?)
    dp.register_callback_query_handler(
        handle_post_payment_actions,
        lambda c: c.data and c.data.startswith("post_payment:"),
    )
    # submission guide: instruction button on post-payment keyboard
    dp.register_callback_query_handler(
        handle_submission_guide,
        lambda c: c.data and c.data.startswith("submission_guide"),
    )
    # sample PDF preview — shown before payment in bundle choice screen
    dp.register_callback_query_handler(
        handle_sample_preview,
        lambda c: c.data and c.data.startswith("sample_preview:"),
    )
    # re-download PDF from order history
    dp.register_callback_query_handler(
        handle_redownload_pdf,
        lambda c: c.data and c.data.startswith("redownload_pdf:"),
    )
    # /mydocs command — order history
    dp.register_message_handler(handle_my_docs, commands=["mydocs"])
    # Promo code: tap button → set state → type code
    dp.register_callback_query_handler(
        handle_promo_input,
        lambda c: c.data and c.data.startswith("promo_input_"),
    )
    dp.register_message_handler(process_promo_code, state=DocumentState.waiting_promo)
    # Trust badge: silent answer — no popup, no action
    dp.register_callback_query_handler(
        lambda c: c.answer(),
        lambda c: c.data == "noop_secure_badge",
    )


def register_stripe_handlers(dp: Dispatcher):
    """
    🔒 PUBLIC CONTRACT
    Bot MUST import only this function
    """
    register_handlers(dp)
