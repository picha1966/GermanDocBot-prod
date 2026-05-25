# -*- coding: utf-8 -*-
"""Single source of truth: Termin product positioning (monitoring ≠ booking). HTML for Telegram."""

from typing import Optional

# Keys: uk (also used for ua), en, de, pl, tr, ar
TERMIN_POSITIONING_HTML: dict[str, str] = {
    "uk": (
        "⚡ <b>Ми не записуємо вас напряму</b> — автоматично шукаємо вільні слоти.\n\n"
        "📅 <b>Що входить у Termin:</b>\n"
        "• Ми перевіряємо наявність вільних слотів\n"
        "• Даємо пряме посилання на запис\n"
        "• Ви самостійно бронюєте Termin\n\n"
        "❗ <b>Ми НЕ гарантуємо отримання запису</b>"
    ),
    "en": (
        "⚡ <b>We don’t book you directly</b> — we automatically find open slots.\n\n"
        "📅 <b>What you get:</b>\n"
        "• We check available appointment slots\n"
        "• We provide a direct booking link\n"
        "• You book the appointment yourself\n\n"
        "❗ <b>We do NOT guarantee an appointment</b>"
    ),
    "de": (
        "⚡ <b>Wir buchen nicht direkt für Sie</b> — wir finden automatisch freie Termine.\n\n"
        "📅 <b>Was Sie erhalten:</b>\n"
        "• Wir prüfen verfügbare Termine\n"
        "• Wir geben Ihnen einen direkten Buchungslink\n"
        "• Sie buchen den Termin selbst\n\n"
        "❗ <b>Wir garantieren keinen Termin</b>"
    ),
    "pl": (
        "⚡ <b>Nie rezerwujemy za Ciebie bezpośrednio</b> — automatycznie szukamy wolnych terminów.\n\n"
        "📅 <b>Co otrzymasz:</b>\n"
        "• Sprawdzamy dostępne terminy\n"
        "• Dajemy bezpośredni link do rezerwacji\n"
        "• Sam rezerwujesz termin\n\n"
        "❗ <b>Nie gwarantujemy terminu</b>"
    ),
    "tr": (
        "⚡ <b>Sizin adınıza doğrudan randevu almıyoruz</b> — boş slotları otomatik buluyoruz.\n\n"
        "📅 <b>Ne alırsınız:</b>\n"
        "• Uygun randevuları kontrol ederiz\n"
        "• Doğrudan rezervasyon linki veririz\n"
        "• Randevuyu kendiniz alırsınız\n\n"
        "❗ <b>Randevu garantisi yoktur</b>"
    ),
    "ar": (
        "⚡ <b>لا نحجز عنك مباشرة</b> — نبحث تلقائيًا عن المواعيد المتاحة.\n\n"
        "📅 <b>ما ستحصل عليه:</b>\n"
        "• نتحقق من المواعيد المتاحة\n"
        "• نوفر رابط حجز مباشر\n"
        "• تقوم بالحجز بنفسك\n\n"
        "❗ <b>لا نضمن الحصول على موعد</b>"
    ),
}

# Short teaser for bundle-choice screen only (full details before Stripe checkout).
TERMIN_POSITIONING_SHORT_HTML: dict[str, str] = {
    "uk": (
        "⚡ <b>Ми не записуємо вас напряму</b> — автоматично шукаємо вільні слоти.\n"
        "📅 <b>Termin:</b> перевіряємо слоти й даємо посилання на запис — "
        "ви бронюєте самі.\n"
        "❗ <b>Ми не гарантуємо запис</b>"
    ),
    "en": (
        "⚡ <b>We don’t book you directly</b> — we automatically find open slots.\n"
        "📅 <b>Termin:</b> we check slots and give a booking link — you book yourself.\n"
        "❗ <b>We do NOT guarantee an appointment</b>"
    ),
    "de": (
        "⚡ <b>Wir buchen nicht direkt für Sie</b> — wir finden automatisch freie Termine.\n"
        "📅 <b>Termin:</b> Wir prüfen Slots und geben den Buchungslink — Sie buchen selbst.\n"
        "❗ <b>Wir garantieren keinen Termin</b>"
    ),
    "pl": (
        "⚡ <b>Nie rezerwujemy za Ciebie bezpośrednio</b> — automatycznie szukamy wolnych terminów.\n"
        "📅 <b>Termin:</b> sprawdzamy terminy i dajemy link — rezerwujesz sam.\n"
        "❗ <b>Nie gwarantujemy terminu</b>"
    ),
    "tr": (
        "⚡ <b>Sizin adınıza doğrudan randevu almıyoruz</b> — boş slotları otomatik buluyoruz.\n"
        "📅 <b>Termin:</b> slotları kontrol eder, link veririz — randevuyu siz alırsınız.\n"
        "❗ <b>Randevu garantisi yoktur</b>"
    ),
    "ar": (
        "⚡ <b>لا نحجز عنك مباشرة</b> — نبحث تلقائيًا عن المواعيد المتاحة.\n"
        "📅 <b>المواعيد:</b> نتحقق من الأماكن ونعطي رابط الحجز — تحجز بنفسك.\n"
        "❗ <b>لا نضمن موعدًا</b>"
    ),
}


def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "en").strip().lower()
    if l == "ua":
        l = "uk"
    return l


def get_termin_positioning_short_html(lang: Optional[str]) -> str:
    """Bundle-choice screen: one compact line + guarantee (HTML)."""
    l = _norm_lang(lang)
    return TERMIN_POSITIONING_SHORT_HTML.get(l, TERMIN_POSITIONING_SHORT_HTML["en"])


def get_termin_positioning_html(lang: Optional[str]) -> str:
    """Full block — use immediately before Stripe checkout for PDF+Termin bundle."""
    l = _norm_lang(lang)
    return TERMIN_POSITIONING_HTML.get(l, TERMIN_POSITIONING_HTML["en"])
