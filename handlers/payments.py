# -*- coding: utf-8 -*-
"""
handlers/payments.py
Post-payment deep link handling for Telegram bot.

Flow:
1. User completes Stripe payment → landing page
2. User clicks "Return to Telegram" → t.me/bot?start=paid_<order_id>
3. This handler delivers the PDF if order is paid (or shows Termin success for termin orders)

IMPORTANT: Webhook (checkout.session.completed) marks order as PAID.
This handler delivers PDF for paid orders when user returns.
"""

import asyncio
import logging
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

# Messages for different states
MESSAGES = {
    "processing": {
        "uk": "⏳ Обробка платежу. Зачекайте, будь ласка...\n\nЯкщо документ не надійде протягом хвилини, зверніться до підтримки.",
        "en": "⏳ Processing payment. Please wait...\n\nIf you don't receive the document within a minute, contact support.",
        "de": "⏳ Zahlung wird bearbeitet. Bitte warten...\n\nWenn Sie das Dokument nicht innerhalb einer Minute erhalten, wenden Sie sich an den Support.",
        "pl": "⏳ Przetwarzanie płatności. Proszę czekać...\n\nJeśli nie otrzymasz dokumentu w ciągu minuty, skontaktuj się z pomocą techniczną.",
        "tr": "⏳ Ödeme işleniyor. Lütfen bekleyin...\n\nBelgeyi bir dakika içinde almazsanız, destek ile iletişime geçin.",
        "ar": "⏳ جارٍ معالجة الدفع. يرجى الانتظار...\n\nإذا لم تستلم المستند خلال دقيقة، يرجى التواصل مع الدعم.",
    },
    "already_sent": {
        "uk": "✅ <b>Дякуємо за оплату!</b>\n\nВаш документ вже надіслано — знайдіть його у повідомленнях вище.",
        "en": "✅ <b>Thank you for your payment!</b>\n\nYour document has already been sent — find it in the messages above.",
        "de": "✅ <b>Vielen Dank für Ihre Zahlung!</b>\n\nIhr Dokument wurde bereits gesendet — suchen Sie es in den Nachrichten oben.",
        "pl": "✅ <b>Dziękujemy za płatność!</b>\n\nTwój dokument został już wysłany — znajdź go w wiadomościach powyżej.",
        "tr": "✅ <b>Ödemeniz için teşekkürler!</b>\n\nBelgeniz zaten gönderildi — yukarıdaki mesajlarda bulabilirsiniz.",
        "ar": "✅ <b>شكراً على دفعتك!</b>\n\nتم إرسال مستندك بالفعل — ابحث عنه في الرسائل أعلاه.",
    },
    "not_found": {
        "uk": "❌ Замовлення не знайдено.\n\nЗверніться до підтримки.",
        "en": "❌ Order not found.\n\nPlease contact support.",
        "de": "❌ Bestellung nicht gefunden.\n\nBitte kontaktieren Sie den Support.",
        "pl": "❌ Zamówienie nie znalezione.\n\nProszę skontaktować się z pomocą techniczną.",
        "tr": "❌ Sipariş bulunamadı.\n\nLütfen destek ile iletişime geçin.",
        "ar": "❌ لم يتم العثور على الطلب.\n\nيرجى التواصل مع الدعم.",
    },
    "delivery_success": {
        "uk": "✅ Ваш документ готовий! Перевірте повідомлення вище.",
        "en": "✅ Your document is ready! Check the message above.",
        "de": "✅ Ihr Dokument ist fertig! Überprüfen Sie die Nachricht oben.",
        "pl": "✅ Twój dokument jest gotowy! Sprawdź wiadomość powyżej.",
        "tr": "✅ Belgeniz hazır! Yukarıdaki mesajı kontrol edin.",
        "ar": "✅ مستندك جاهز! تحقق من الرسالة أعلاه.",
    },
    "delivery_failed": {
        "uk": "❌ Помилка при доставці документа. Зверніться до підтримки.",
        "en": "❌ Document delivery failed. Please contact support.",
        "de": "❌ Dokumentenlieferung fehlgeschlagen. Bitte kontaktieren Sie den Support.",
        "pl": "❌ Dostarczenie dokumentu nie powiodło się. Skontaktuj się z pomocą techniczną.",
        "tr": "❌ Belge teslimi başarısız oldu. Lütfen destek ile iletişime geçin.",
        "ar": "❌ فشل تسليم المستند. يرجى التواصل مع الدعم.",
    },
}

# Alias
PROCESSING_MSG = MESSAGES["processing"]

# --- Termin-only success screen ---

# FALLBACK: shown ONLY when user has NOT pre-selected city+document before paying
TERMIN_SUCCESS_TEXT_FALLBACK = {
    "uk": (
        "✅ <b>Оплата пройшла успішно!</b>\n\n"
        "Тепер оберіть місто та установу,\n"
        "для яких ми будемо відстежувати вільні місця.\n\n"
        "Запис ви робите самостійно через офіційний сайт."
    ),
    "en": (
        "✅ <b>Payment successful!</b>\n\n"
        "Now select the city and authority\n"
        "we should monitor for available slots.\n\n"
        "You book the appointment yourself via the official website."
    ),
    "de": (
        "✅ <b>Zahlung erfolgreich!</b>\n\n"
        "Wählen Sie jetzt die Stadt und Behörde,\n"
        "für die wir freie Termine überwachen sollen.\n\n"
        "Sie buchen den Termin selbst über die offizielle Website."
    ),
    "pl": (
        "✅ <b>Płatność zakończona!</b>\n\n"
        "Teraz wybierz miasto i urząd,\n"
        "dla których będziemy monitorować wolne miejsca.\n\n"
        "Wizytę rezerwujesz samodzielnie na oficjalnej stronie."
    ),
    "tr": (
        "✅ <b>Ödeme başarılı!</b>\n\n"
        "Şimdi takip etmemiz gereken\n"
        "şehri ve kurumu seçin.\n\n"
        "Randevunuzu resmi web sitesinden kendiniz alırsınız."
    ),
    "ar": (
        "✅ <b>تمت عملية الدفع بنجاح!</b>\n\n"
        "الآن اختر المدينة والجهة\n"
        "التي نراقب فيها المواعيد المتاحة.\n\n"
        "أنت تحجز بنفسك عبر الموقع الرسمي."
    ),
}

# PRIMARY: shown when user already selected city+document before paying.
# Supports optional {city} and {authority} placeholders — filled at render time.
TERMIN_SUCCESS_TEXT_ACTIVE = {
    "uk": (
        "✅ <b>Моніторинг активовано</b>\n\n"
        "📍 Місто: <b>{city}</b>\n"
        "🏢 Установа: <b>{authority}</b>\n\n"
        "🔎 Автоматичні перевірки запущено.\n\n"
        "🎯 Моніторинг триває до першого знайденого Termin.\n\n"
        "Запис ви робите самостійно через офіційний сайт."
    ),
    "en": (
        "✅ <b>Monitoring Activated</b>\n\n"
        "📍 City: <b>{city}</b>\n"
        "🏢 Office: <b>{authority}</b>\n\n"
        "🔎 Automatic checks are running.\n\n"
        "🎯 Monitoring continues until a Termin is found.\n\n"
        "You book the appointment yourself via the official website."
    ),
    "de": (
        "✅ <b>Überwachung aktiviert</b>\n\n"
        "📍 Stadt: <b>{city}</b>\n"
        "🏢 Behörde: <b>{authority}</b>\n\n"
        "🔎 Automatische Prüfungen laufen.\n\n"
        "🎯 Überwachung läuft bis zum ersten gefundenen Termin.\n\n"
        "Sie buchen den Termin selbst über die offizielle Website."
    ),
    "pl": (
        "✅ <b>Monitoring aktywowany</b>\n\n"
        "📍 Miasto: <b>{city}</b>\n"
        "🏢 Urząd: <b>{authority}</b>\n\n"
        "🔎 Automatyczne sprawdzenia uruchomione.\n\n"
        "🎯 Monitoring trwa do pierwszego znalezionego Termin.\n\n"
        "Wizytę rezerwujesz samodzielnie na oficjalnej stronie."
    ),
    "tr": (
        "✅ <b>İzleme Etkinleştirildi</b>\n\n"
        "📍 Şehir: <b>{city}</b>\n"
        "🏢 Kurum: <b>{authority}</b>\n\n"
        "🔎 Otomatik kontroller çalışıyor.\n\n"
        "🎯 İlk randevu bulunana kadar izleme devam eder.\n\n"
        "Randevunuzu resmi web sitesinden kendiniz alırsınız."
    ),
    "ar": (
        "✅ <b>تم تفعيل المراقبة</b>\n\n"
        "📍 المدينة: <b>{city}</b>\n"
        "🏢 الجهة: <b>{authority}</b>\n\n"
        "🔎 الفحوصات التلقائية تعمل.\n\n"
        "🎯 المراقبة مستمرة حتى العثور على أول موعد.\n\n"
        "أنت تحجز بنفسك عبر الموقع الرسمي."
    ),
}

TERMIN_SUCCESS_TEXT_7DAY = {
    "uk": "✅ <b>Моніторинг активовано на 7 днів.</b>\n\n📍 Місто: {city}\n🏛 Служба: {authority}\n\nМи автоматично перевіряємо нові слоти і повідомимо вас одразу після появи.",
    "en": "✅ <b>Monitoring active for 7 days.</b>\n\n📍 City: {city}\n🏛 Authority: {authority}\n\nWe automatically check for new slots and will notify you immediately.",
    "de": "✅ <b>Überwachung für 7 Tage aktiv.</b>\n\n📍 Stadt: {city}\n🏛 Behörde: {authority}\n\nWir prüfen automatisch neue Termine und benachrichtigen Sie sofort.",
    "pl": "✅ <b>Monitoring aktywny przez 7 dni.</b>\n\n📍 Miasto: {city}\n🏛 Urząd: {authority}\n\nAutomatycznie sprawdzamy nowe terminy i powiadomimy Cię natychmiast.",
    "tr": "✅ <b>İzleme 7 gün boyunca aktif.</b>\n\n📍 Şehir: {city}\n🏛 Kurum: {authority}\n\nYeni randevuları otomatik olarak kontrol ediyoruz ve hemen bildirim göndereceğiz.",
    "ar": "✅ <b>المراقبة نشطة لمدة 7 أيام.</b>\n\n📍 المدينة: {city}\n🏛 الجهة: {authority}\n\nنتحقق تلقائيًا من المواعيد الجديدة وسنبلغك فورًا.",
}

TERMIN_BTN_SELECT = {
    "uk": "📍 Обрати місто та установу",
    "en": "📍 Select city & authority",
    "de": "📍 Stadt & Behörde wählen",
    "pl": "📍 Wybierz miasto i urząd",
    "tr": "📍 Şehir ve kurum seçin",
    "ar": "📍 اختر المدينة والجهة",
}

TERMIN_BTN_MENU = {
    "uk": "⬅️ Назад до меню",
    "en": "⬅️ Back to menu",
    "de": "⬅️ Zurück zum Menü",
    "pl": "⬅️ Powrót do menu",
    "tr": "⬅️ Menüye dön",
    "ar": "⬅️ العودة إلى القائمة",
}

# Post-payment active-screen buttons
_ACTIVE_BTN_STATUS = {
    "uk": "📊 Статус",
    "ua": "📊 Статус",
    "en": "📊 Status",
    "de": "📊 Status",
    "pl": "📊 Status",
    "tr": "📊 Durum",
    "ar": "📊 الحالة",
}
_ACTIVE_BTN_STOP = {
    "uk": "🔕 Зупинити моніторинг",
    "ua": "🔕 Зупинити моніторинг",
    "en": "🔕 Stop monitoring",
    "de": "🔕 Überwachung stoppen",
    "pl": "🔕 Zatrzymaj monitoring",
    "tr": "🔕 İzlemeyi durdur",
    "ar": "🔕 إيقاف المراقبة",
}
_ACTIVE_BTN_SETTINGS = {
    "uk": "⚙ Налаштування",
    "en": "⚙ Settings",
    "de": "⚙ Einstellungen",
    "pl": "⚙ Ustawienia",
    "tr": "⚙ Ayarlar",
    "ar": "⚙ الإعدادات",
}
_ACTIVE_BTN_MENU = {
    "uk": "🏠 Головне меню",
    "ua": "🏠 Головне меню",
    "en": "🏠 Main menu",
    "de": "🏠 Hauptmenü",
    "pl": "🏠 Menu główne",
    "tr": "🏠 Ana menü",
    "ar": "🏠 القائمة الرئيسية",
}


_PAYMENT_PENDING_TEXTS = {
    "uk": (
        "⏳ <b>Перевіряємо оплату…</b>\n\n"
        "Якщо ви щойно оплатили — зачекайте 10–15 секунд і натисніть знову.\n"
        "Ми підтвердимо автоматично."
    ),
    "ua": (
        "⏳ <b>Перевіряємо оплату…</b>\n\n"
        "Якщо ви щойно оплатили — зачекайте 10–15 секунд і натисніть знову.\n"
        "Ми підтвердимо автоматично."
    ),
    "en": (
        "⏳ <b>Checking your payment…</b>\n\n"
        "If you just paid — wait 10–15 seconds and tap again.\n"
        "We'll confirm it automatically."
    ),
    "de": (
        "⏳ <b>Zahlung wird geprüft…</b>\n\n"
        "Wenn Sie gerade bezahlt haben — warten Sie 10–15 Sekunden und tippen Sie erneut.\n"
        "Wir bestätigen automatisch."
    ),
    "pl": (
        "⏳ <b>Sprawdzamy płatność…</b>\n\n"
        "Jeśli właśnie zapłaciłeś — poczekaj 10–15 sekund i kliknij ponownie.\n"
        "Potwierdzimy automatycznie."
    ),
    "tr": (
        "⏳ <b>Ödeme kontrol ediliyor…</b>\n\n"
        "Az önce ödediyseniz — 10–15 saniye bekleyin ve tekrar dokunun.\n"
        "Otomatik olarak onaylayacağız."
    ),
    "ar": (
        "⏳ <b>جارٍ التحقق من الدفع…</b>\n\n"
        "إذا كنت قد دفعت للتو — انتظر 10–15 ثانية ثم اضغط مجدداً.\n"
        "سنؤكد ذلك تلقائياً."
    ),
}

_PAY_NOW_BTN = {
    "uk": "💳 Оплатити зараз",
    "ua": "💳 Оплатити зараз",
    "en": "💳 Pay now",
    "de": "💳 Jetzt bezahlen",
    "pl": "💳 Zapłać teraz",
    "tr": "💳 Şimdi öde",
    "ar": "💳 ادفع الآن",
}


def _build_pending_payment_kb(
    lang: str, checkout_url: str | None
) -> InlineKeyboardMarkup | None:
    """Return an inline keyboard with a 'Pay now' URL button if checkout_url is available."""
    if not checkout_url:
        return None
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            text=_PAY_NOW_BTN.get(lang, _PAY_NOW_BTN["en"]),
            url=checkout_url,
        )
    )
    return kb


def _get_msg(key: str, lang: str) -> str:
    """Get localized message with fallback to Ukrainian."""
    msgs = MESSAGES.get(key, {})
    if lang == "ua":
        lang = "uk"
    return msgs.get(lang, msgs.get("uk", msgs.get("en", "")))


def _resolve_termin_user(user_id) -> dict:
    """Load termin DB user by user_id. Returns dict or empty dict."""
    try:
        from backend.termin_db import get_user

        return get_user(str(user_id)) or {}
    except Exception:
        return {}


def _resolve_city_authority_display(user_id, lang: str):
    """Return (city_display, authority_display) for the given user.

    Priority: live polling session → DB row.
    A PAUSED_AFTER_FOUND session is intentionally skipped: it belongs to a
    previously notified city and must not bleed into the success screen of a
    newly activated payment (e.g. München session still in memory when Berlin
    payment completes).
    Returns ("—", "—") if nothing is available — never raises.
    """
    try:
        from utils.termin_checker import get_session as _get_sess, TerminStatus as _TS

        _sess = _get_sess(int(user_id))
        if (
            _sess
            and _sess.city
            and _sess.authority
            and _sess.status != _TS.PAUSED_AFTER_FOUND
        ):
            from handlers.termin import _CITY_DISPLAY_MAP, normalize_authority_name

            _c = _CITY_DISPLAY_MAP.get(_sess.city, _sess.city.replace("_", " ").title())
            _a = normalize_authority_name(_sess.authority)
            return _c, _a
    except Exception:
        pass
    try:
        tu = _resolve_termin_user(user_id)
        if tu.get("city") and tu.get("authority"):
            from handlers.termin import _CITY_DISPLAY_MAP, normalize_authority_name

            _c = _CITY_DISPLAY_MAP.get(tu["city"], tu["city"].replace("_", " ").title())
            _a = normalize_authority_name(tu["authority"])
            return _c, _a
    except Exception:
        pass
    return "—", "—"


def _get_termin_success_text(
    lang: str,
    user_id=None,
    city: str = None,
    authority: str = None,
    plan: str = "single",
) -> str:
    """Get localized termin success text — state-aware, with dynamic city/authority.

    City/authority resolution order:
      1. Explicit city/authority args
      2. Live polling session
      3. DB row
      4. Fallback (no selection yet → prompt to choose city)
    """
    if lang == "ua":
        lang = "uk"

    if plan == "7day":
        _c7 = city
        _a7 = authority
        if user_id and (not _c7 or not _a7):
            _c7_r, _a7_r = _resolve_city_authority_display(user_id, lang)
            if not _c7:
                _c7 = _c7_r
            if not _a7:
                _a7 = _a7_r
        tpl7 = TERMIN_SUCCESS_TEXT_7DAY.get(lang, TERMIN_SUCCESS_TEXT_7DAY["uk"])
        return tpl7.format(city=_c7 or "—", authority=_a7 or "—")

    _city = city
    _auth = authority

    if user_id and (not _city or not _auth):
        _db_city, _db_auth = _resolve_city_authority_display(user_id, lang)
        if not _city:
            _city = _db_city
        if not _auth:
            _auth = _db_auth

    has_selection = bool(_city and _city != "—" and _auth and _auth != "—")

    if has_selection:
        # München: portal assistant mode — replace "automatic checks running" text.
        _raw_city = ""
        try:
            from backend.termin_db import get_user as _get_tu
            _tu = _get_tu(str(user_id)) or {}
            _raw_city = (_tu.get("city") or "").lower().strip()
        except Exception:
            pass
        _is_muenchen = _raw_city in ("muenchen", "münchen", "munich")

        if _is_muenchen:
            logger.info(
                "MUENCHEN_MANUAL_ONLY_MODE | user=%s city=%s auth=%s action=success_screen",
                user_id, _city, _auth,
            )
            _portal_url = "https://www48.muenchen.de/buergeransicht/"
            _muenchen_success = {
                "uk": (
                    "✅ <b>Портал-асистент активовано</b>\n\n"
                    f"📍 Місто: <b>{_city}</b>\n"
                    f"🏢 Служба: <b>{_auth}</b>\n\n"
                    "🗺 Бот надає офіційне посилання та інструкцію.\n"
                    f"🔗 {_portal_url}\n\n"
                    "⚠️ Автоматичне виявлення слотів недоступне.\n"
                    "Перевіряйте та записуйтесь вручну на офіційному порталі."
                ),
                "en": (
                    "✅ <b>Portal Assistant Activated</b>\n\n"
                    f"📍 City: <b>{_city}</b>\n"
                    f"🏢 Office: <b>{_auth}</b>\n\n"
                    "🗺 The bot provides the official link and instructions.\n"
                    f"🔗 {_portal_url}\n\n"
                    "⚠️ Automatic slot detection is not available.\n"
                    "Check for slots and book manually on the official portal."
                ),
                "de": (
                    "✅ <b>Portal-Assistent aktiviert</b>\n\n"
                    f"📍 Stadt: <b>{_city}</b>\n"
                    f"🏢 Behörde: <b>{_auth}</b>\n\n"
                    "🗺 Der Bot stellt den offiziellen Link und Anleitung bereit.\n"
                    f"🔗 {_portal_url}\n\n"
                    "⚠️ Automatische Terminsuche nicht verfügbar.\n"
                    "Freie Termine manuell prüfen und buchen."
                ),
                "pl": (
                    "✅ <b>Asystent portalu aktywowany</b>\n\n"
                    f"📍 Miasto: <b>{_city}</b>\n"
                    f"🏢 Urząd: <b>{_auth}</b>\n\n"
                    "🗺 Bot dostarcza oficjalny link i instrukcję.\n"
                    f"🔗 {_portal_url}\n\n"
                    "⚠️ Automatyczne wykrywanie slotów niedostępne.\n"
                    "Sprawdzaj i rezerwuj ręcznie na oficjalnym portalu."
                ),
                "tr": (
                    "✅ <b>Portal Asistanı Etkinleştirildi</b>\n\n"
                    f"📍 Şehir: <b>{_city}</b>\n"
                    f"🏢 Kurum: <b>{_auth}</b>\n\n"
                    "🗺 Bot resmi bağlantıyı ve talimatları sağlar.\n"
                    f"🔗 {_portal_url}\n\n"
                    "⚠️ Otomatik randevu tespiti mevcut değil.\n"
                    "Randevuları manuel kontrol edin ve rezervasyon yapın."
                ),
                "ar": (
                    "✅ <b>تم تفعيل مساعد البوابة</b>\n\n"
                    f"📍 المدينة: <b>{_city}</b>\n"
                    f"🏢 الجهة: <b>{_auth}</b>\n\n"
                    "🗺 يوفر البوت الرابط الرسمي والتعليمات.\n"
                    f"🔗 {_portal_url}\n\n"
                    "⚠️ الكشف التلقائي عن المواعيد غير متاح.\n"
                    "تحقق من المواعيد واحجز يدويًا عبر البوابة الرسمية."
                ),
            }
            return _muenchen_success.get(lang, _muenchen_success["en"])

        tpl = TERMIN_SUCCESS_TEXT_ACTIVE.get(lang, TERMIN_SUCCESS_TEXT_ACTIVE["uk"])
        logger.info(
            "TERMIN_SUCCESS_SCREEN_SHOWN | user=%s city=%s auth=%s lang=%s",
            user_id,
            _city,
            _auth,
            lang,
        )
        return tpl.format(city=_city, authority=_auth)

    return TERMIN_SUCCESS_TEXT_FALLBACK.get(lang, TERMIN_SUCCESS_TEXT_FALLBACK["uk"])


def _build_termin_success_keyboard(
    lang: str, user_id=None, plan: str = "single"
) -> InlineKeyboardMarkup:
    """Build keyboard for termin success screen — state-aware Premium layout.

    Active (city+authority known):
      Row 1:  📊 Status
      Row 2:  🔕 Stop monitoring  |  ⚙ Settings
      Row 3:  ⬅ Back to menu

    Fallback (no city selected yet):
      Row 1:  📍 Select city
      Row 2:  ⬅ Back to menu
    """
    if lang == "ua":
        lang = "uk"
    kb = InlineKeyboardMarkup(row_width=1)

    has_selection = False
    if user_id:
        try:
            tu = _resolve_termin_user(user_id)
            if tu.get("city") and tu.get("authority"):
                has_selection = True
        except Exception:
            pass

    if has_selection:
        kb.add(
            InlineKeyboardButton(
                _ACTIVE_BTN_STATUS.get(lang, "📊 Status"),
                callback_data="termin_status",
            )
        )
        kb.row(
            InlineKeyboardButton(
                _ACTIVE_BTN_STOP.get(lang, "🔕 Stop monitoring"),
                callback_data="termin_pause",
            ),
            InlineKeyboardButton(
                _ACTIVE_BTN_SETTINGS.get(lang, "⚙ Settings"),
                callback_data="termin_filters",
            ),
        )
    else:
        kb.add(
            InlineKeyboardButton(
                TERMIN_BTN_SELECT.get(lang, TERMIN_BTN_SELECT["uk"]),
                callback_data="termin_cities",
            )
        )

    kb.add(
        InlineKeyboardButton(
            TERMIN_BTN_MENU.get(lang, TERMIN_BTN_MENU["uk"]),
            callback_data="back_to_main_menu",
        )
    )
    return kb


# ======================================================================
# TERMIN MONITOR 24h — post-payment status + heartbeat
# ======================================================================

_MONITOR_STATUS = {
    "uk": (
        "✅ <b>Моніторинг активовано</b>\n\n"
        "🏙 Місто: <b>{city}</b>\n"
        "🏛 Установи: <b>{n_auth}</b>\n"
        "🔄 Перевірок/год: <b>~30</b>\n"
        "🕐 Старт: <b>{started}</b>\n\n"
        "<b>Що далі:</b>\n"
        "1️⃣ Перший звіт через ~15 хв\n"
        "2️⃣ Безперервний пошук запущено\n"
        "3️⃣ Якщо знайдемо — одразу повідомимо\n"
        "4️⃣ Ви можете змінити фільтри\n\n"
        "Натисніть <b>Статус</b> щоб перевірити."
    ),
    "en": (
        "✅ <b>Monitoring activated</b>\n\n"
        "🏙 City: <b>{city}</b>\n"
        "🏛 Authorities: <b>{n_auth}</b>\n"
        "🔄 Checks/hour: <b>~30</b>\n"
        "🕐 Started: <b>{started}</b>\n\n"
        "<b>Next steps:</b>\n"
        "1️⃣ First report in ~15 min\n"
        "2️⃣ Continuous search started\n"
        "3️⃣ Instant alert if found\n"
        "4️⃣ Filters can be changed\n\n"
        "Tap <b>Status</b> to check."
    ),
    "de": (
        "✅ <b>Überwachung aktiviert</b>\n\n"
        "🏙 Stadt: <b>{city}</b>\n"
        "🏛 Behörden: <b>{n_auth}</b>\n"
        "🔄 Prüfungen/Std: <b>~30</b>\n"
        "🕐 Gestartet: <b>{started}</b>\n\n"
        "<b>Nächste Schritte:</b>\n"
        "1️⃣ Erster Bericht in ~15 Min.\n"
        "2️⃣ Dauersuche gestartet\n"
        "3️⃣ Sofortige Benachrichtigung bei Fund\n"
        "4️⃣ Filter können geändert werden\n\n"
        "Tippen Sie auf <b>Status</b> zum Prüfen."
    ),
    "pl": (
        "✅ <b>Monitoring aktywowany</b>\n\n"
        "🏙 Miasto: <b>{city}</b>\n"
        "🏛 Urzędy: <b>{n_auth}</b>\n"
        "🔄 Sprawdzeń/godz: <b>~30</b>\n"
        "🕐 Start: <b>{started}</b>\n\n"
        "<b>Co dalej:</b>\n"
        "1️⃣ Pierwszy raport za ~15 min\n"
        "2️⃣ Ciągłe wyszukiwanie uruchomione\n"
        "3️⃣ Natychmiastowy alert przy znalezieniu\n"
        "4️⃣ Filtry można zmienić\n\n"
        "Kliknij <b>Status</b> aby sprawdzić."
    ),
    "tr": (
        "✅ <b>İzleme etkinleştirildi</b>\n\n"
        "🏙 Şehir: <b>{city}</b>\n"
        "🏛 Kurumlar: <b>{n_auth}</b>\n"
        "🔄 Kontrol/saat: <b>~30</b>\n"
        "🕐 Başlangıç: <b>{started}</b>\n\n"
        "<b>Sonraki adımlar:</b>\n"
        "1️⃣ İlk rapor ~15 dk içinde\n"
        "2️⃣ Sürekli arama başladı\n"
        "3️⃣ Bulunursa anında bildirim\n"
        "4️⃣ Filtreler değiştirilebilir\n\n"
        "<b>Durum</b>'a dokunarak kontrol edin."
    ),
    "ar": (
        "✅ <b>تم تفعيل المراقبة</b>\n\n"
        "🏙 المدينة: <b>{city}</b>\n"
        "🏛 الجهات: <b>{n_auth}</b>\n"
        "🔄 فحوصات/ساعة: <b>~30</b>\n"
        "🕐 البدء: <b>{started}</b>\n\n"
        "<b>:الخطوات التالية</b>\n"
        "1️⃣ أول تقرير خلال ~15 دقيقة\n"
        "2️⃣ بدأ البحث المستمر\n"
        "3️⃣ إشعار فوري عند العثور\n"
        "4️⃣ يمكن تغيير الفلاتر\n\n"
        "اضغط <b>الحالة</b> للتحقق."
    ),
}

_HEARTBEAT_MSG = {
    "uk": (
        "📊 <b>Оновлення:</b>\n\n"
        "Ми перевірили <b>300+</b> слотів.\n"
        "Поки що вільних термінів не знайдено.\n\n"
        "🔄 Пошук триває…"
    ),
    "en": (
        "📊 <b>Update:</b>\n\n"
        "We checked <b>300+</b> slots.\n"
        "No free appointments found yet.\n\n"
        "🔄 Search continues…"
    ),
    "de": (
        "📊 <b>Aktualisierung:</b>\n\n"
        "Wir haben <b>300+</b> Termine geprüft.\n"
        "Noch keine freien Termine gefunden.\n\n"
        "🔄 Suche läuft weiter…"
    ),
    "pl": (
        "📊 <b>Aktualizacja:</b>\n\n"
        "Sprawdziliśmy <b>300+</b> terminów.\n"
        "Nie znaleziono wolnych terminów.\n\n"
        "🔄 Wyszukiwanie trwa…"
    ),
    "tr": (
        "📊 <b>Güncelleme:</b>\n\n"
        "<b>300+</b> randevu kontrol edildi.\n"
        "Henüz boş randevu bulunamadı.\n\n"
        "🔄 Arama devam ediyor…"
    ),
    "ar": (
        "📊 <b>:تحديث</b>\n\n"
        "تم فحص <b>300+</b> موعد.\n"
        "لم يتم العثور على مواعيد متاحة بعد.\n\n"
        "🔄 البحث مستمر…"
    ),
}


async def _send_termin_heartbeat(bot, dispatcher, user_id, lang: str):
    """Send a neutral heartbeat ~15 min after monitor activation confirming search is ongoing."""
    await asyncio.sleep(900)
    _l = lang if lang not in ("ua",) else "uk"
    text = _HEARTBEAT_MSG.get(_l, _HEARTBEAT_MSG["en"])
    try:
        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
        logger.info("MONITOR_HEARTBEAT_SENT: user_id=%s", user_id)
    except Exception as e:
        logger.error("MONITOR_HEARTBEAT_FAILED: user_id=%s error=%s", user_id, e)


_DAILY_SUMMARY = {
    "uk": (
        "📅 <b>Звіт моніторингу</b>\n\n"
        "🔄 Пошук активний — перевіряємо доступність термінів.\n"
        "Ви отримаєте повідомлення, щойно з'явиться вільне місце."
    ),
    "en": (
        "📅 <b>Monitoring Update</b>\n\n"
        "🔄 Search is active — checking appointment availability.\n"
        "You will be notified as soon as a slot opens."
    ),
    "de": (
        "📅 <b>Überwachungs-Update</b>\n\n"
        "🔄 Suche aktiv — Terminverfügbarkeit wird geprüft.\n"
        "Sie werden benachrichtigt, sobald ein Termin frei wird."
    ),
    "pl": (
        "📅 <b>Aktualizacja monitoringu</b>\n\n"
        "🔄 Wyszukiwanie aktywne — sprawdzamy dostępność terminów.\n"
        "Zostaniesz powiadomiony/a, gdy pojawi się wolne miejsce."
    ),
    "tr": (
        "📅 <b>İzleme Güncellemesi</b>\n\n"
        "🔄 Arama aktif — randevu müsaitliği kontrol ediliyor.\n"
        "Yer açıldığında bildirim alacaksınız."
    ),
    "ar": (
        "📅 <b>تحديث المراقبة</b>\n\n"
        "🔄 البحث نشط — يتم التحقق من توفر المواعيد.\n"
        "ستتلقى إشعاراً فور ظهور موعد متاح."
    ),
}


async def _send_daily_summary(bot, dispatcher, user_id, lang: str):
    """Send a monitoring progress summary ~4h after activation.

    Skipped if the user is no longer entitled or no longer polling.
    """
    await asyncio.sleep(14400)
    _l = lang if lang not in ("ua",) else "uk"

    # Safety: do not send if entitlement is gone or polling has stopped.
    try:
        from backend.termin_db import is_termin_entitled as _is_ent
        from utils.termin_checker import is_polling as _is_pol

        if not _is_ent(str(user_id)) and not _is_pol(int(user_id)):
            logger.info(
                "MONITOR_DAILY_SUMMARY_SKIPPED: user_id=%s (not entitled/not polling)",
                user_id,
            )
            return
    except Exception:
        pass

    text = _DAILY_SUMMARY.get(_l, _DAILY_SUMMARY["en"])

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            _ACTIVE_BTN_STATUS.get(_l, "📊 Status"),
            callback_data="termin_status",
        )
    )
    kb.add(
        InlineKeyboardButton(
            _ACTIVE_BTN_MENU.get(_l, _ACTIVE_BTN_MENU["en"]),
            callback_data="main_menu",
        )
    )
    try:
        await bot.send_message(
            chat_id=user_id, text=text, parse_mode="HTML", reply_markup=kb
        )
        logger.info("MONITOR_DAILY_SUMMARY_SENT: user_id=%s", user_id)
    except Exception as e:
        logger.error("MONITOR_DAILY_SUMMARY_FAILED: user_id=%s error=%s", user_id, e)


async def _extract_city_from_order(order: dict, db=None) -> str:
    """Extract city_code from Stripe session metadata.

    Returns empty string if city cannot be resolved — callers must handle
    this case explicitly and MUST NOT silently substitute a hardcoded city.
    Uses asyncio.to_thread so the synchronous Stripe SDK call does not block
    the event loop.
    """
    import logging as _ecfo_log
    _ecfo_logger = _ecfo_log.getLogger(__name__)
    sid = order.get("stripe_session_id")
    if sid:
        try:
            import asyncio
            import stripe as _stripe_lib
            import os

            _stripe_lib.api_key = os.getenv("STRIPE_SECRET_KEY", "")
            sess = await asyncio.to_thread(_stripe_lib.checkout.Session.retrieve, sid)
            meta = getattr(sess, "metadata", None) or {}
            city = meta.get("city") if hasattr(meta, "get") else None
            if city:
                return city
            _ecfo_logger.error(
                "CITY_MISSING_IN_METADATA | session=%s — city key absent from Stripe metadata",
                sid,
            )
        except Exception as _ecfo_exc:
            _ecfo_logger.error(
                "CITY_EXTRACT_STRIPE_ERROR | session=%s error=%s — cannot resolve city",
                sid, _ecfo_exc,
            )
    else:
        _ecfo_logger.error(
            "CITY_EXTRACT_NO_SESSION | order=%s — no stripe_session_id, cannot resolve city",
            order.get("id") or order.get("order_id") or "?",
        )
    return ""


_EXTEND_ACTIVATED = {
    "uk": (
        "✅ <b>Моніторинг продовжено на 24 години.</b>\n\n"
        "Пошук продовжується без перерви.\n"
        "Ви отримаєте сповіщення одразу при появі вільного терміну."
    ),
    "en": (
        "✅ <b>Monitoring extended for another 24 hours.</b>\n\n"
        "Search continues without interruption.\n"
        "You'll be notified instantly when a slot appears."
    ),
    "de": (
        "✅ <b>Überwachung um weitere 24 Stunden verlängert.</b>\n\n"
        "Die Suche läuft ohne Unterbrechung weiter.\n"
        "Sie werden sofort benachrichtigt, wenn ein Termin verfügbar ist."
    ),
    "pl": (
        "✅ <b>Monitoring przedłużony o kolejne 24 godziny.</b>\n\n"
        "Wyszukiwanie trwa bez przerwy.\n"
        "Powiadomienie pojawi się natychmiast po znalezieniu terminu."
    ),
    "tr": (
        "✅ <b>İzleme 24 saat daha uzatıldı.</b>\n\n"
        "Arama kesintisiz devam eder.\n"
        "Randevu çıktığında anında bildirim alırsınız."
    ),
    "ar": (
        "✅ <b>تم تمديد المراقبة لمدة 24 ساعة إضافية.</b>\n\n"
        "يستمر البحث دون انقطاع.\n"
        "ستُبلَّغ فورًا عند ظهور موعد."
    ),
}

_PRIORITY_ACTIVATED = {
    "uk": (
        "🔔 <b>Priority Boost активовано.</b>\n\n"
        "Шанс знайти слот збільшено до 60%.\n"
        "Ви отримаєте сповіщення першими при появі вільного терміну."
    ),
    "en": (
        "🔔 <b>Priority Boost activated.</b>\n\n"
        "Your slot chance increased to 60%.\n"
        "You'll receive alerts first when a slot appears."
    ),
    "de": (
        "🔔 <b>Priority Boost aktiviert.</b>\n\n"
        "Ihre Slot-Chance steigt auf 60%.\n"
        "Sie erhalten als Erste eine Benachrichtigung, wenn ein Termin verfügbar ist."
    ),
    "pl": (
        "🔔 <b>Priority Boost aktywowany.</b>\n\n"
        "Szansa na slot wzrosła do 60%.\n"
        "Będziesz pierwszy powiadamiany o wolnym terminie."
    ),
    "tr": (
        "🔔 <b>Priority Boost etkinleştirildi.</b>\n\n"
        "Slot şansınız %60'a yükseldi.\n"
        "Randevu açıldığında ilk siz bildirim alacaksınız."
    ),
    "ar": (
        "🔔 <b>تم تفعيل Priority Boost.</b>\n\n"
        "ارتفعت فرصتك في الحصول على موعد إلى 60%.\n"
        "ستكون أول من يتلقى تنبيهًا عند ظهور موعد."
    ),
}


async def _activate_termin_extend(bot, user_id, lang: str):
    """Extend monitoring timer in FSM by +24h (additive, not reset) and notify user."""
    from datetime import datetime as _dt, timedelta as _td

    _l = lang if lang not in ("ua",) else "uk"

    try:
        from aiogram import Dispatcher as _Dp

        _dp = _Dp.get_current()
        if _dp:
            _fsm = _dp.current_state(chat=int(user_id), user=int(user_id))
            _data = await _fsm.get_data()
            _expires = _data.get("monitor_expires_at")
            _now = _dt.utcnow()
            if _expires:
                try:
                    _exp_dt = _dt.fromisoformat(_expires)
                    _exp_dt = (
                        (_exp_dt + _td(hours=24))
                        if _exp_dt > _now
                        else (_now + _td(hours=24))
                    )
                except Exception:
                    _exp_dt = _now + _td(hours=24)
            else:
                _exp_dt = _now + _td(hours=24)
            await _fsm.update_data(monitor_expires_at=_exp_dt.isoformat())
    except Exception:
        pass

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            _ACTIVE_BTN_STATUS.get(_l, "📊 Status"),
            callback_data="termin_status",
        )
    )
    kb.add(
        InlineKeyboardButton(
            _ACTIVE_BTN_MENU.get(_l, _ACTIVE_BTN_MENU["en"]),
            callback_data="main_menu",
        )
    )
    text = _EXTEND_ACTIVATED.get(_l, _EXTEND_ACTIVATED["en"])
    try:
        await bot.send_message(
            chat_id=user_id, text=text, parse_mode="HTML", reply_markup=kb
        )
        logger.info("EXTEND_ACTIVATED: user_id=%s", user_id)
    except Exception as e:
        logger.error("EXTEND_ACTIVATION_FAILED: user_id=%s error=%s", user_id, e)


async def _activate_termin_priority(bot, user_id, lang: str):
    """Enable priority_alerts in FSM and notify user after payment."""
    _l = lang if lang not in ("ua",) else "uk"

    try:
        from aiogram import Dispatcher as _Dp

        _dp = _Dp.get_current()
        if _dp:
            _fsm = _dp.current_state(chat=int(user_id), user=int(user_id))
            await _fsm.update_data(priority_alerts=True)
    except Exception:
        pass

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            _ACTIVE_BTN_STATUS.get(_l, "📊 Status"),
            callback_data="termin_status",
        )
    )
    kb.add(
        InlineKeyboardButton(
            _ACTIVE_BTN_MENU.get(_l, _ACTIVE_BTN_MENU["en"]),
            callback_data="main_menu",
        )
    )
    text = _PRIORITY_ACTIVATED.get(_l, _PRIORITY_ACTIVATED["en"])
    try:
        await bot.send_message(
            chat_id=user_id, text=text, parse_mode="HTML", reply_markup=kb
        )
        logger.info("PRIORITY_ACTIVATED: user_id=%s", user_id)
    except Exception as e:
        logger.error("PRIORITY_ACTIVATION_FAILED: user_id=%s error=%s", user_id, e)


async def send_monitor_activation(bot, user_id, city_code: str, lang: str):
    """Send detailed monitor-24h activation status and schedule heartbeat."""
    from datetime import datetime as _dt

    _l = lang if lang not in ("ua",) else "uk"
    now = _dt.utcnow()
    started_at = now.strftime("%H:%M")

    try:
        from aiogram import Dispatcher

        _dp = Dispatcher.get_current()
        if _dp:
            _fsm = _dp.current_state(chat=int(user_id), user=int(user_id))
            await _fsm.update_data(monitor_started_at=now.isoformat())
    except Exception:
        pass

    try:
        from backend.termin_db import get_authorities

        auth_rows = get_authorities(city_code)
    except Exception:
        auth_rows = []
    n_auth = len(auth_rows) if auth_rows else 5

    city_display = city_code.replace("_", " ").title()

    # Attempt to use rich contextual success message from termin module
    _rich_text = None
    try:
        from handlers.termin import _PAYMENT_SUCCESS_RICH
        from backend.termin_db import get_user

        _user_row = get_user(str(user_id)) or {}
        _auth_key = _user_row.get("authority", "")
        _AUTH_DISPLAY = {
            "buergeramt": "Bürgeramt",
            "burgeramt": "Bürgeramt",  # legacy alias
            "auslaenderbehoerde": "Ausländerbehörde",
            "auslanderbehorde": "Ausländerbehörde",  # legacy alias
            "jobcenter": "Jobcenter",
            "standesamt": "Standesamt",
        }
        _auth_display = _AUTH_DISPLAY.get(_auth_key, "Bürgeramt")
        _rich_tmpl = _PAYMENT_SUCCESS_RICH.get(_l, _PAYMENT_SUCCESS_RICH.get("en", ""))
        if _rich_tmpl:
            _rich_text = _rich_tmpl.format(
                city=city_display,
                authority=_auth_display,
                started_at=started_at,
            )
    except Exception as _re:
        logger.warning(
            "send_monitor_activation: rich text failed (%s), using fallback", _re
        )

    if _rich_text:
        text = _rich_text
    else:
        text = _MONITOR_STATUS.get(_l, _MONITOR_STATUS["en"]).format(
            city=city_display,
            n_auth=n_auth,
            started=started_at,
        )
    _STATUS_BTN = {
        "uk": "📊 Статус",
        "en": "📊 Status",
        "de": "📊 Status",
        "pl": "📊 Status",
        "tr": "📊 Durum",
        "ar": "📊 الحالة",
    }
    _MENU_BTN = {
        "uk": "🏠 Головне меню",
        "en": "🏠 Main menu",
        "de": "🏠 Hauptmenü",
        "pl": "🏠 Menu główne",
        "tr": "🏠 Ana menü",
        "ar": "🏠 القائمة الرئيسية",
    }
    _FAMILY_UPSELL_BTN = {
        "uk": "👨‍👩‍👧 Додати члена родини (+€2.99)",
        "en": "👨‍👩‍👧 Add a family member (+€2.99)",
        "de": "👨‍👩‍👧 Familienmitglied hinzufügen (+€2,99)",
        "pl": "👨‍👩‍👧 Dodaj członka rodziny (+€2,99)",
        "tr": "👨‍👩‍👧 Aile üyesi ekle (+€2,99)",
        "ar": "👨‍👩‍👧 أضف فرداً من العائلة (+€2.99)",
    }
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(
            _STATUS_BTN.get(_l, "📊 Status"),
            callback_data="termin_status",
        )
    )
    # Family upsell: show only if user is NOT on a family plan (single-slot users = best upsell moment)
    try:
        from backend.termin_db import get_entitlement as _get_ent
        _ent = _get_ent(str(user_id)) or {}
        _is_family = _ent.get("plan") == "family" or _ent.get("slots_total", 1) > 1
    except Exception:
        _is_family = False
    if not _is_family:
        kb.add(
            InlineKeyboardButton(
                _FAMILY_UPSELL_BTN.get(_l, _FAMILY_UPSELL_BTN["en"]),
                callback_data="termin_family_upsell",
            )
        )
    kb.add(
        InlineKeyboardButton(
            _MENU_BTN.get(_l, "🏠 Main menu"),
            callback_data="main_menu",
        )
    )
    try:
        await bot.send_message(
            chat_id=user_id, text=text, parse_mode="HTML", reply_markup=kb
        )
        logger.info("MONITOR_ACTIVATION_SENT: user_id=%s city=%s", user_id, city_code)
    except Exception as e:
        logger.error("MONITOR_ACTIVATION_SEND_FAILED: user_id=%s error=%s", user_id, e)

    from aiogram import Dispatcher as _Dp

    _dispatcher = _Dp.get_current()
    asyncio.create_task(_send_termin_heartbeat(bot, _dispatcher, user_id, _l))
    asyncio.create_task(_send_daily_summary(bot, _dispatcher, user_id, _l))


async def handle_payment_return(message: types.Message, order_id_str: str):
    """
    Return handler after Stripe success_url redirect (payment_ prefix).

    IMPORTANT: This does NOT confirm payment!
    User can reach this URL without completing payment.

    Silent return — webhook handles all post-payment messages.
    No "processing" message to avoid interrupting Stripe flow.
    """
    logger.info("PAYMENT_RETURN: order_id=%s (silent return, webhook handles delivery)", order_id_str)
    # No message sent — webhook sends success/delivery when payment completes


async def handle_paid_deeplink(message: types.Message, order_id_str: str):
    """
    Handle deep link after payment: t.me/bot?start=paid_<order_id>

    This is called when user clicks "Return to Telegram" on payment success page.
    At this point, webhook should have already marked order as PAID.

    Flow:
    1. Load order from DB
    2. Check status:
       - SENT/DOWNLOADED → already delivered, show message
       - PAID → deliver PDF now
       - PENDING/PROCESSING → payment not confirmed yet, show processing
    3. Deliver PDF if PAID
    4. Mark as SENT
    5. Idempotent: never duplicate delivery
    """
    logger.info("PAID_DEEPLINK: order_id=%s", order_id_str)

    user_id = message.from_user.id if message.from_user else None

    from utils.helpers import get_user_lang, get_db

    _lang = (get_user_lang(user_id) or "en").strip().lower() if user_id else "en"
    if _lang == "ua":
        _lang = "uk"

    # Validate order_id
    try:
        order_id = int(order_id_str) if order_id_str else None
    except (ValueError, TypeError):
        order_id = None

    if not order_id:
        logger.info("PAID_DEEPLINK_ERROR: invalid order_id=%s", order_id_str)
        await message.answer(_get_msg("not_found", _lang))
        return

    # Load order from DB
    db = get_db()
    try:
        order = db.get_order(order_id)
    except Exception as e:
        logger.error("PAID_DEEPLINK_DB_ERROR: order_id=%s error=%s", order_id, e)
        order = None

    if not order:
        logger.info("PAID_DEEPLINK_NOT_FOUND: order_id=%s", order_id)
        await message.answer(_get_msg("not_found", _lang))
        return

    # Get order status and doc_type
    status = (order.get("status") or "").strip().lower()
    doc_type = (order.get("doc_type") or "").strip()
    is_termin_only = doc_type in (
        "termin_notifications",
        "termin_monitor_24h",
        "termin_extend_24h",
        "termin_priority_boost",
        "termin_monitor_7day",
        "termin_monitor_30day",
    )
    logger.debug(
        "PAID_DEEPLINK_STATUS: order_id=%s status=%s doc_type=%s",
        order_id,
        status,
        doc_type,
    )

    # ======================================================================
    # IDEMPOTENCY GUARD — termin orders only
    # Prevents the success screen being sent more than once regardless of
    # how many times the deep link fires (Stripe redirect, user taps "back",
    # Telegram re-delivers the start link, etc.).
    # ======================================================================
    if is_termin_only:
        logger.info("DELIVERY_STARTED: order_id=%s user_id=%s", order_id, user_id)
        try:
            if db.is_order_delivered(order_id):
                logger.info(
                    "DELIVERY_SKIPPED_IDEMPOTENT: order_id=%s user_id=%s",
                    order_id,
                    user_id,
                )
                logger.info(
                    "TERMIN_IDEMPOTENT_DEEPLINK | user=%s order=%s doc_type=%s",
                    user_id,
                    order_id,
                    doc_type,
                )
                # Webhook already sent the activation screen and marked order delivered.
                # Deeplink shows a concise "already active" confirmation so the user
                # knows their payment worked — avoids panic after closing Stripe.
                _ALREADY_ACTIVE_TEXT = {
                    "uk": "✅ <b>Оплата успішна</b>\n\n🔄 Моніторинг вже працює.\n📊 Перевірте статус нижче.",
                    "en": "✅ <b>Payment successful</b>\n\n🔄 Monitoring is already running.\n📊 Check the status below.",
                    "de": "✅ <b>Zahlung erfolgreich</b>\n\n🔄 Überwachung läuft bereits.\n📊 Status unten prüfen.",
                    "pl": "✅ <b>Płatność zakończona</b>\n\n🔄 Monitoring już działa.\n📊 Sprawdź status poniżej.",
                    "tr": "✅ <b>Ödeme başarılı</b>\n\n🔄 İzleme zaten çalışıyor.\n📊 Aşağıdan durumu kontrol edin.",
                    "ar": "✅ <b>تم الدفع بنجاح</b>\n\n🔄 المراقبة تعمل بالفعل.\n📊 تحقق من الحالة أدناه.",
                }
                _ALREADY_ACTIVE_BTN = {
                    "uk": "📊 Перевірити статус",
                    "en": "📊 Check status",
                    "de": "📊 Status prüfen",
                    "pl": "📊 Sprawdź status",
                    "tr": "📊 Durumu kontrol et",
                    "ar": "📊 التحقق من الحالة",
                }
                try:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton as _IKB_idp
                    _kb_idp = InlineKeyboardMarkup(row_width=1)
                    _kb_idp.add(_IKB_idp(
                        _ALREADY_ACTIVE_BTN.get(_lang, _ALREADY_ACTIVE_BTN["en"]),
                        callback_data="termin_status",
                    ))
                    await message.answer(
                        _ALREADY_ACTIVE_TEXT.get(_lang, _ALREADY_ACTIVE_TEXT["en"]),
                        parse_mode="HTML",
                        reply_markup=_kb_idp,
                    )
                except Exception as _idp_msg_e:
                    logger.warning("TERMIN_IDEMPOTENT_MSG_FAIL | user=%s err=%s", user_id, _idp_msg_e)
                try:
                    from utils.termin_checker import (
                        set_success_screen_shown as _sss_idp,
                    )
                    _sss_idp(int(user_id), True)
                except Exception:
                    pass
                return
        except Exception as _idp_exc:
            logger.warning(
                "DELIVERY_IDEMPOTENCY_CHECK_FAILED: order_id=%s err=%s — proceeding",
                order_id,
                _idp_exc,
            )

    # ======================================================================
    # TERMIN-ONLY ORDERS: webhook sends success message; deeplink is silent
    # ======================================================================
    if is_termin_only:
        logger.debug(
            "PAID_DEEPLINK_TERMIN_ONLY: order_id=%s status=%s", order_id, status
        )

        # Webhook already processed this order and sent the success message, but
        # the user is now returning from Stripe via the deeplink — they may be
        # staring at the old "Slot found → Pay" screen.
        if status in ("sent", "downloaded"):
            # Webhook already activated entitlement and started polling.
            _tuid = str(order.get("user_id") or user_id)
            logger.info(
                "TERMIN_POST_PAYMENT_RETURN | user=%s order=%s",
                user_id,
                order_id,
            )

            # Duplicate-screen guard: if webhook already sent a success message
            # (within the last 5 min), deeplink sends only a compact confirmation
            # instead of a full duplicate screen.
            _webhook_already_sent = False
            try:
                from utils.termin_redis import rget as _rget_ws

                _webhook_already_sent = bool(
                    _rget_ws(f"termin:webhook_success_sent:{user_id}")
                )
            except Exception:
                pass

            try:
                if _webhook_already_sent:
                    # Webhook screen was delivered moments ago — compact deeplink ack only
                    _COMPACT_ACK = {
                        "uk": "✅ <b>Моніторинг активовано.</b> Ми повідомимо вас одразу.",
                        "ua": "✅ <b>Моніторинг активовано.</b> Ми повідомимо вас одразу.",
                        "en": "✅ <b>Monitoring is active.</b> You'll be notified instantly.",
                        "de": "✅ <b>Überwachung aktiv.</b> Sie werden sofort benachrichtigt.",
                        "pl": "✅ <b>Monitoring aktywny.</b> Powiadomimy Cię natychmiast.",
                        "tr": "✅ <b>İzleme aktif.</b> Anında bildirim alacaksınız.",
                        "ar": "✅ <b>المراقبة نشطة.</b> ستُبلَّغ فورًا.",
                    }
                    await message.answer(
                        _COMPACT_ACK.get(_lang, _COMPACT_ACK["en"]),
                        parse_mode="HTML",
                    )
                    logger.info(
                        "TERMIN_DEEPLINK_COMPACT_ACK | user=%s (webhook screen already sent)",
                        user_id,
                    )
                else:
                    # Webhook screen not yet confirmed — use the canonical activation message
                    # (same as the one the webhook sends) instead of the legacy success text.
                    _dl_uid = str(order.get("user_id") or user_id)
                    try:
                        from backend.termin_db import get_user as _get_termin_user_dl
                    except Exception:
                        _get_termin_user_dl = lambda _: {}
                    _dl_user_row = _get_termin_user_dl(_dl_uid) or {}
                    _dl_city = _dl_user_row.get("city") or ""
                    _dl_auth = _dl_user_row.get("authority") or "buergeramt"
                    if not _dl_city:
                        logger.error(
                            "CITY_MISSING_IN_DB | user=%s order=%s deeplink — "
                            "city absent from termin users table; activation message may be incomplete",
                            _dl_uid, order_id,
                        )
                    if doc_type == "termin_monitor_7day":
                        _dl_plan = "7day"
                    elif doc_type == "termin_monitor_30day":
                        _dl_plan = "30day"
                    else:
                        _dl_plan = "24h"
                    try:
                        from handlers.termin_activation import send_termin_activation_message as _stam_dl

                        await _stam_dl(
                            message.bot,
                            int(_dl_uid),
                            _dl_city,
                            _dl_auth,
                            _lang,
                            plan=_dl_plan,
                        )
                    except Exception as _stam_exc:
                        logger.warning(
                            "TERMIN_DEEPLINK_ACTIVATION_MSG_FAILED | user=%s err=%s",
                            user_id,
                            _stam_exc,
                        )
                    logger.info(
                        "TERMIN_DEEPLINK_FULL_SCREEN | user=%s (no prior webhook screen)",
                        user_id,
                    )
                # Mark order as delivered so subsequent deep link triggers are skipped.
                try:
                    db.mark_order_delivered(order_id)
                except Exception as _md_exc:
                    logger.warning(
                        "MARK_ORDER_DELIVERED_FAILED: order_id=%s err=%s",
                        order_id,
                        _md_exc,
                    )
                # Success screen confirmed delivered — unblock slot notifications.
                try:
                    from utils.termin_checker import set_success_screen_shown as _sss_dl

                    _sss_dl(int(user_id), True)
                except Exception:
                    pass
            except Exception as _e:
                logger.warning(
                    "TERMIN_POST_PAYMENT_RETURN_SEND_ERR | user=%s err=%s", user_id, _e
                )
                # Unblock even on send failure so monitoring isn't silently suppressed.
                try:
                    from utils.termin_checker import (
                        set_success_screen_shown as _sss_dl_fb,
                    )

                    _sss_dl_fb(int(user_id), True)
                except Exception:
                    pass
            return

        # PAID but not yet moved to SENT — backend safety net
        if status == "paid":
            from backend.database import OrderStatus

            db.update_order_status(order_id, OrderStatus.SENT)

            # Webhook already activated everything (upsert_entitlement, create_reminder,
            # start_polling) and marked the order PAID.  The deeplink arriving here is a
            # race condition where the delivered flag wasn't written yet.
            # Show the canonical new activation UI and mark delivered.
            if doc_type in (
                "termin_notifications",
                "termin_monitor_7day",
                "termin_monitor_24h",
                "termin_monitor_30day",
            ):
                _tuid = str(order.get("user_id") or user_id)
                try:
                    from backend.termin_db import get_user as _get_termin_user_paid
                except Exception:
                    _get_termin_user_paid = lambda _: {}
                _paid_user_row = _get_termin_user_paid(_tuid) or {}
                _paid_city = _paid_user_row.get("city") or ""
                _paid_auth = _paid_user_row.get("authority") or "buergeramt"
                if not _paid_city:
                    logger.error(
                        "CITY_MISSING_IN_DB | user=%s order=%s paid-deeplink — "
                        "city absent from termin users table; activation message may be incomplete",
                        _tuid, order_id,
                    )
                if doc_type == "termin_monitor_7day":
                    _paid_plan = "7day"
                elif doc_type == "termin_monitor_30day":
                    _paid_plan = "30day"
                else:
                    _paid_plan = "24h"
                try:
                    from handlers.termin_activation import send_termin_activation_message as _stam_paid

                    await _stam_paid(
                        message.bot,
                        int(_tuid),
                        _paid_city,
                        _paid_auth,
                        _lang,
                        plan=_paid_plan,
                    )
                    logger.info(
                        "TERMIN_PAID_DEEPLINK_UI_ONLY | user=%s order=%s"
                        " (webhook already activated; showing new activation screen only)",
                        user_id,
                        order_id,
                    )
                except Exception as _ui_exc:
                    logger.warning(
                        "TERMIN_PAID_DEEPLINK_UI_FAILED: order_id=%s err=%s",
                        order_id,
                        _ui_exc,
                    )
                try:
                    db.mark_order_delivered(order_id)
                except Exception as _md_exc:
                    logger.warning(
                        "MARK_ORDER_DELIVERED_FAILED: order_id=%s err=%s",
                        order_id,
                        _md_exc,
                    )
                try:
                    from utils.termin_checker import (
                        set_success_screen_shown as _sss_paid,
                    )

                    _sss_paid(int(user_id), True)
                except Exception:
                    pass
                return
            # ─────────────────────────────────────────────────────────────────

            _dl_city = ""
            _dl_auth = "buergeramt"
            _tid = str(order.get("user_id") or user_id)
            try:
                from backend.termin_db import (
                    update_user as _upd_termin,
                    create_user as _crt_termin,
                    upsert_entitlement as _upsert_ent,
                    get_user as _get_termin_user,
                    create_reminder as _crt_reminder,
                )
                from datetime import datetime as _dt_dl, timedelta as _td_dl

                _crt_termin(_tid)
                _upd_termin(_tid, has_paid_termin=1)
                _dl_session = order.get("stripe_session_id") or f"deeplink_{order_id}"

                # ── Resolve city/authority BEFORE upsert so entitlement is complete ──
                _dl_user_row = _get_termin_user(_tid) or {}
                _dl_city = _dl_user_row.get("city") or ""
                _dl_auth = _dl_user_row.get("authority") or "buergeramt"
                # Fallback: pull city from Stripe metadata if missing in user row
                if not _dl_city:
                    _dl_city = await _extract_city_from_order(order, db)
                if not _dl_city:
                    logger.error(
                        "CITY_MISSING | user=%s order=%s deeplink — "
                        "cannot resolve city; entitlement stored without city",
                        _tid, order_id,
                    )
                # ──────────────────────────────────────────────────────────────

                if doc_type == "termin_monitor_7day":
                    _dl_plan = "7day"
                    _dl_hours = 168  # 7 days
                elif doc_type == "termin_monitor_30day":
                    _dl_plan = "30day"
                    _dl_hours = 720  # 30 days
                else:
                    _dl_plan = "single"
                    _dl_hours = 24
                _paid_until_dl = (_dt_dl.utcnow() + _td_dl(hours=_dl_hours)).isoformat()
                _upsert_ent(
                    user_id=str(_tid),
                    plan=_dl_plan,
                    slots_total=1,
                    stripe_session_id=_dl_session,
                    paid_until=_paid_until_dl,
                    city=_dl_city or None,
                    authority=_dl_auth or None,
                )
                logger.info(
                    "DEEPLINK_TERMIN_FALLBACK_ENTITLEMENT | user=%s doc_type=%s plan=%s "
                    "paid_until=%s city=%s auth=%s session=%s",
                    _tid, doc_type, _dl_plan, _paid_until_dl, _dl_city, _dl_auth, _dl_session,
                )
                _crt_reminder(_tid, _dl_city, _dl_auth, 6)
                logger.info(
                    "PAID_DEEPLINK_TERMIN_ACTIVATED: order_id=%s user_id=%s city=%s auth=%s",
                    order_id, _tid, _dl_city, _dl_auth,
                )

                # ── Start polling immediately — do NOT wait for watchdog ────
                if _dl_city and _dl_auth:
                    try:
                        from utils.termin_checker import (
                            start_polling as _stp_dl,
                            is_polling as _isp_dl,
                            get_session as _gs_dl,
                            stop_polling as _stop_dl_imm,
                            _cooldowns as _cd_dl,
                        )
                        from handlers.termin import (
                            make_termin_send_fn,
                            make_termin_on_reserved_fn,
                            make_termin_found_fn,
                        )
                        from utils.helpers import get_user_lang as _gul_dl
                        _dl_uid_int = int(_tid)
                        _dl_poll_lang = (
                            _gul_dl(_dl_uid_int) or _lang or "en"
                        ).strip().lower()
                        _existing_dl = _gs_dl(_dl_uid_int)
                        if _existing_dl:
                            _stop_dl_imm(_dl_uid_int, reason="deeplink_restart")
                            _cd_dl.pop(_dl_uid_int, None)
                        if not _isp_dl(_dl_uid_int):
                            _stp_dl(
                                user_id=_dl_uid_int,
                                chat_id=_dl_uid_int,
                                city=_dl_city,
                                authority=_dl_auth,
                                lang=_dl_poll_lang,
                                send_fn=make_termin_send_fn(
                                    message.bot, _dl_uid_int, _dl_city, _dl_poll_lang
                                ),
                                on_reserved_fn=make_termin_on_reserved_fn(
                                    message.bot, _dl_uid_int, _dl_city,
                                    _dl_auth, _dl_poll_lang, state=None,
                                ),
                                on_found_fn=make_termin_found_fn(
                                    message.bot, authority=_dl_auth
                                ),
                            )
                            logger.info(
                                "TERMIN_DEEPLINK_POLLING_STARTED | user=%s city=%s auth=%s",
                                _dl_uid_int, _dl_city, _dl_auth,
                            )
                    except Exception as _poll_exc:
                        logger.error(
                            "TERMIN_DEEPLINK_POLLING_START_ERROR | user=%s err=%s",
                            _tid, _poll_exc,
                        )
                # ──────────────────────────────────────────────────────────────
            except Exception as _te:
                logger.error("PAID_DEEPLINK_TERMIN_ACTIVATION_ERROR: %s", _te)

            # ── Send activation UX message + lift success-screen barrier ─────
            if doc_type in ("termin_monitor_24h", "termin_notifications", "termin_monitor_30day"):
                try:
                    from handlers.termin_activation import (
                        send_termin_activation_message as _stam_sa,
                    )
                    await _stam_sa(
                        message.bot, user_id, _dl_city, _dl_auth, _lang, plan=_dl_plan
                    )
                except Exception as _sa_exc:
                    logger.warning(
                        "TERMIN_DEEPLINK_ACTIVATION_MSG_FAILED | user=%s err=%s",
                        user_id, _sa_exc,
                    )
                try:
                    from utils.termin_checker import (
                        set_success_screen_shown as _sss_dl_imm,
                    )
                    _sss_dl_imm(int(user_id), True)
                except Exception:
                    pass
            elif doc_type == "termin_extend_24h":
                await _activate_termin_extend(message.bot, user_id, _lang)
            elif doc_type == "termin_priority_boost":
                await _activate_termin_priority(message.bot, user_id, _lang)
            # ──────────────────────────────────────────────────────────────────
            return

        # PENDING — Stripe API backup (webhook might not have arrived yet)
        if status in ("pending", "processing"):
            stripe_session_id = order.get("stripe_session_id")
            if stripe_session_id:
                try:
                    import asyncio
                    import stripe
                    import os

                    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
                    # Use asyncio.to_thread to avoid blocking the event loop with
                    # the synchronous Stripe SDK HTTP call.
                    session = await asyncio.to_thread(
                        stripe.checkout.Session.retrieve, stripe_session_id
                    )
                    s_status = getattr(session, "status", None)
                    s_pay = getattr(session, "payment_status", None)
                    logger.debug(
                        "PAID_DEEPLINK_TERMIN_STRIPE: status=%s payment=%s",
                        s_status,
                        s_pay,
                    )

                    if s_status == "complete" and s_pay == "paid":
                        from backend.database import OrderStatus

                        db.update_order_status(order_id, OrderStatus.SENT)
                        # ── Extract city/auth from Stripe metadata FIRST ─────────
                        _sp_meta = getattr(session, "metadata", None) or {}
                        _sp_city = (
                            _sp_meta.get("city") if hasattr(_sp_meta, "get") else None
                        ) or ""
                        _sp_auth = (
                            _sp_meta.get("authority") if hasattr(_sp_meta, "get") else None
                        ) or ""
                        _sp_uid = str(order.get("user_id") or user_id)
                        if not _sp_city or not _sp_auth:
                            try:
                                from backend.termin_db import get_user as _get_sp_u
                                _sp_user_row = _get_sp_u(_sp_uid) or {}
                                _sp_city = _sp_city or _sp_user_row.get("city") or ""
                                _sp_auth = _sp_auth or _sp_user_row.get("authority") or "buergeramt"
                            except Exception:
                                pass
                        if not _sp_city:
                            logger.error(
                                "CITY_MISSING | user=%s order=%s stripe-pending — "
                                "cannot resolve city; entitlement stored without city",
                                _sp_uid, order_id,
                            )
                        # ─────────────────────────────────────────────────────────

                        if doc_type == "termin_monitor_7day":
                            _sp_plan = "7day"
                            _sp_hours = 168  # 7 days
                        elif doc_type == "termin_monitor_30day":
                            _sp_plan = "30day"
                            _sp_hours = 720  # 30 days
                        else:
                            _sp_plan = "single"
                            _sp_hours = 24
                        try:
                            from backend.termin_db import (
                                update_user as _upd_termin,
                                create_user as _crt_termin,
                                upsert_entitlement as _upsert_ent,
                                get_user as _get_termin_user,
                                create_reminder as _crt_reminder,
                            )
                            from datetime import datetime as _dt_sp, timedelta as _td_sp

                            _tid = _sp_uid
                            _crt_termin(_tid)
                            _upd_termin(_tid, has_paid_termin=1)
                            _dl_session = stripe_session_id or f"deeplink_{order_id}"
                            _paid_until_sp = (
                                _dt_sp.utcnow() + _td_sp(hours=_sp_hours)
                            ).isoformat()
                            _upsert_ent(
                                user_id=str(_tid),
                                plan=_sp_plan,
                                slots_total=1,
                                stripe_session_id=_dl_session,
                                paid_until=_paid_until_sp,
                                city=_sp_city or None,
                                authority=_sp_auth or None,
                            )
                            _crt_reminder(_tid, _sp_city, _sp_auth, 6)
                            logger.info(
                                "DEEPLINK_TERMIN_FALLBACK_ENTITLEMENT | user=%s doc_type=%s plan=%s "
                                "paid_until=%s city=%s auth=%s session=%s",
                                _tid, doc_type, _sp_plan, _paid_until_sp, _sp_city, _sp_auth, _dl_session,
                            )
                            logger.info(
                                "PAID_DEEPLINK_TERMIN_ACTIVATED: order_id=%s user_id=%s",
                                order_id, _tid,
                            )

                            # ── Start polling immediately ────────────────────────
                            if _sp_city and _sp_auth:
                                try:
                                    from utils.termin_checker import (
                                        start_polling as _stp_sp,
                                        is_polling as _isp_sp,
                                        get_session as _gs_sp,
                                        stop_polling as _stop_sp,
                                        _cooldowns as _cd_sp,
                                    )
                                    from handlers.termin import (
                                        make_termin_send_fn,
                                        make_termin_on_reserved_fn,
                                        make_termin_found_fn,
                                    )
                                    from utils.helpers import get_user_lang as _gul_sp
                                    _sp_uid_int = int(_tid)
                                    _sp_lang = (
                                        _gul_sp(_sp_uid_int) or _lang or "en"
                                    ).strip().lower()
                                    if _gs_sp(_sp_uid_int):
                                        _stop_sp(_sp_uid_int, reason="stripe_pending_restart")
                                        _cd_sp.pop(_sp_uid_int, None)
                                    if not _isp_sp(_sp_uid_int):
                                        _stp_sp(
                                            user_id=_sp_uid_int,
                                            chat_id=_sp_uid_int,
                                            city=_sp_city,
                                            authority=_sp_auth,
                                            lang=_sp_lang,
                                            send_fn=make_termin_send_fn(
                                                message.bot, _sp_uid_int,
                                                _sp_city, _sp_lang,
                                            ),
                                            on_reserved_fn=make_termin_on_reserved_fn(
                                                message.bot, _sp_uid_int, _sp_city,
                                                _sp_auth, _sp_lang, state=None,
                                            ),
                                            on_found_fn=make_termin_found_fn(
                                                message.bot, authority=_sp_auth
                                            ),
                                        )
                                        logger.info(
                                            "TERMIN_DEEPLINK_POLLING_STARTED | "
                                            "user=%s city=%s auth=%s",
                                            _sp_uid_int, _sp_city, _sp_auth,
                                        )
                                except Exception as _poll_sp_exc:
                                    logger.error(
                                        "TERMIN_DEEPLINK_POLLING_START_ERROR | "
                                        "user=%s err=%s", _tid, _poll_sp_exc,
                                    )
                            # ────────────────────────────────────────────────────
                        except Exception as _te:
                            logger.error(
                                "PAID_DEEPLINK_TERMIN_ACTIVATION_ERROR: %s", _te
                            )
                        if doc_type in (
                            "termin_monitor_24h", "termin_monitor_7day",
                            "termin_notifications", "termin_monitor_30day",
                        ):
                            try:
                                from handlers.termin_activation import (
                                    send_termin_activation_message as _stam_sp,
                                )
                                await _stam_sp(
                                    message.bot, int(_sp_uid), _sp_city,
                                    _sp_auth, _lang, plan=_sp_plan,
                                )
                            except Exception as _sp_exc:
                                logger.warning(
                                    "TERMIN_STRIPE_PENDING_ACTIVATION_MSG_FAILED | "
                                    "user=%s err=%s", user_id, _sp_exc,
                                )
                            try:
                                from utils.termin_checker import (
                                    set_success_screen_shown as _sss_sp,
                                )
                                _sss_sp(int(_sp_uid), True)
                            except Exception:
                                pass
                        elif doc_type == "termin_extend_24h":
                            await _activate_termin_extend(message.bot, user_id, _lang)
                        elif doc_type == "termin_priority_boost":
                            await _activate_termin_priority(message.bot, user_id, _lang)
                        return
                except Exception as e:
                    logger.error("PAID_DEEPLINK_TERMIN_STRIPE_ERROR: %s", e)

            # Stripe not confirmed yet — silent (no "processing" message)
            logger.debug(
                "PAID_DEEPLINK_TERMIN_WAITING: order_id=%s (silent, awaiting webhook)",
                order_id,
            )
            return

        # Unknown status — silent
        logger.debug(
            "PAID_DEEPLINK_TERMIN_UNKNOWN: order_id=%s status=%s (silent)",
            order_id,
            status,
        )
        return

    # ======================================================================
    # DOCUMENT ORDERS (PDF delivery logic)
    # ======================================================================

    # Idempotency guard — prevent duplicate PDF + menu when deep link fires
    # more than once (Telegram re-delivery, user taps "Back", etc.).
    try:
        if db.is_order_delivered(order_id):
            logger.info(
                "PAID_DEEPLINK_ALREADY_DELIVERED_SILENT | order=%s user=%s",
                order_id,
                user_id,
            )
            return
    except Exception as _idp_pdf_exc:
        logger.warning(
            "PDF_DELIVERY_IDEMPOTENCY_CHECK_FAILED: order_id=%s err=%s — proceeding",
            order_id,
            _idp_pdf_exc,
        )

    _is_delivered = status in ("sent", "downloaded")
    _is_paid = status == "paid"
    logger.info(
        "ORDER_DELIVERY_DECISION: order_id=%s paid=%s delivered=%s resend_request=False status=%s",
        order_id,
        _is_paid or _is_delivered,
        _is_delivered,
        status,
    )

    # Termin orders have no user_data — PDF delivery does not apply to them.
    # They are fully handled by the termin-specific block above; reaching here
    # means the order slipped through (e.g. unknown status). Skip PDF delivery.
    _doc_type = (order.get("doc_type") or "").strip()
    if _doc_type.startswith("termin_"):
        logger.info(
            "SKIP_PDF_DELIVERY_FOR_TERMIN: order_id=%s doc_type=%s status=%s",
            order_id,
            _doc_type,
            status,
        )
        return

    # Order was already delivered (webhook beat the deeplink) — do not re-deliver.
    if _is_delivered:
        logger.info(
            "PAID_DEEPLINK_STATUS_DELIVERED_SILENT | order=%s status=%s user=%s",
            order_id,
            status,
            user_id,
        )
        return

    # PROCESSING means claim_delivery already won — PDF generation is in flight.
    # Rolling back to PAID and re-entering deliver_document_after_payment would
    # send the PDF a second time. Tell the user to wait; the in-flight delivery
    # will mark the order SENT and notify the user when done.
    if status == "processing":
        logger.info(
            "PAID_DEEPLINK_PROCESSING_WAIT | order=%s user=%s",
            order_id,
            user_id,
        )
        from handlers.stripe_handler import _should_show_payment_message as _spm

        if _spm(order_id, "processing"):
            _processing_msg = PROCESSING_MSG.get(
                _lang,
                PROCESSING_MSG.get(
                    "en", "⏳ Payment is being processed. Please wait a few seconds..."
                ),
            )
            await message.answer(_processing_msg)
        return

    # If not yet paid (webhook not processed), check Stripe API as backup
    if status == "pending":
        logger.debug(
            "PAID_DEEPLINK_NOT_YET_PAID: order_id=%s status=%s", order_id, status
        )

        # BACKUP: Check Stripe API if webhook didn't arrive
        stripe_session_id = order.get("stripe_session_id")
        if stripe_session_id:
            logger.debug(
                "PAID_DEEPLINK_CHECKING_STRIPE: order_id=%s session_id=%s",
                order_id,
                stripe_session_id,
            )

            try:
                import stripe
                import os

                stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

                session = stripe.checkout.Session.retrieve(stripe_session_id)
                stripe_status = getattr(session, "status", None)
                stripe_payment_status = getattr(session, "payment_status", None)

                logger.debug(
                    "PAID_DEEPLINK_STRIPE_STATUS: session_status=%s payment_status=%s",
                    stripe_status,
                    stripe_payment_status,
                )

                if stripe_status == "complete" and stripe_payment_status == "paid":
                    logger.info(
                        "PAID_DEEPLINK_STRIPE_CONFIRMS_PAID: order_id=%s", order_id
                    )

                    # Re-read order before writing: webhook may have already
                    # set PROCESSING/SENT between our Stripe check and now.
                    from backend.database import OrderStatus

                    _fresh = db.get_order(order_id)
                    _fresh_status = (
                        (_fresh.get("status") or "").strip().lower() if _fresh else ""
                    )
                    if _fresh_status in ("processing", "sent", "downloaded"):
                        logger.info(
                            "PAID_DEEPLINK_STRIPE_BACKUP_SKIP: order_id=%s — status moved to %s while we were checking Stripe",
                            order_id,
                            _fresh_status,
                        )
                        _processing_msg = PROCESSING_MSG.get(
                            _lang,
                            PROCESSING_MSG.get(
                                "en",
                                "⏳ Payment is being processed. Please wait a few seconds...",
                            ),
                        )
                        await message.answer(_processing_msg)
                        return

                    # Safe to mark as PAID — status is still pending
                    db.update_order_status(order_id, OrderStatus.PAID)
                    logger.info("PAID_DEEPLINK_MARKED_PAID: order_id=%s", order_id)

                    # Webhook may never arrive for this session — deliver as safety net.
                    # claim_delivery() inside deliver_document_after_payment prevents duplicates
                    # if the webhook races us and also tries to deliver.
                    logger.info(
                        "DEEPLINK_STRIPE_BACKUP_DELIVERY | order=%s user=%s",
                        order_id,
                        user_id,
                    )
                    _processing_msg = PROCESSING_MSG.get(
                        _lang,
                        PROCESSING_MSG.get(
                            "en",
                            "⏳ Payment is being processed. Please wait a few seconds...",
                        ),
                    )
                    await message.answer(_processing_msg)
                    try:
                        from handlers.stripe_handler import (
                            deliver_document_after_payment as _ddap,
                        )

                        _backup_bot = message.bot
                        _backup_ok = await _ddap(_backup_bot, order_id)
                        if _backup_ok:
                            logger.info(
                                "DEEPLINK_STRIPE_BACKUP_DELIVERY_SUCCESS | order=%s",
                                order_id,
                            )
                            try:
                                db.mark_order_delivered(order_id)
                            except Exception as _md_b:
                                logger.warning(
                                    "DEEPLINK_STRIPE_BACKUP_MARK_FAILED: order_id=%s err=%s",
                                    order_id,
                                    _md_b,
                                )
                            # Webhook буде пропущений (SENT → idempotent skip) — email тут
                            try:
                                from utils.delivery_retry import _attempt_email_after_delivery as _aead_b
                                logger.warning("EMAIL_AFTER_DEEPLINK_CALLED order=%s", order_id)
                                await _aead_b(order_id)
                            except Exception as _em_b:
                                logger.error("EMAIL_AFTER_DEEPLINK_FAILED order=%s err=%s", order_id, _em_b)
                        else:
                            logger.warning(
                                "DEEPLINK_STRIPE_BACKUP_DELIVERY_FALSE | order=%s",
                                order_id,
                            )
                    except Exception as _bde:
                        logger.error(
                            "DEEPLINK_STRIPE_BACKUP_DELIVERY_ERROR | order=%s err=%s",
                            order_id,
                            _bde,
                        )
                    return
                else:
                    logger.debug(
                        "PAID_DEEPLINK_STRIPE_NOT_PAID: order_id=%s — showing pending UX",
                        order_id,
                    )
                    _pending_text = _PAYMENT_PENDING_TEXTS.get(
                        _lang, _PAYMENT_PENDING_TEXTS["en"]
                    )
                    # Retrieve checkout URL from Stripe session to offer a retry button
                    _checkout_url = getattr(session, "url", None)
                    _pending_kb = _build_pending_payment_kb(_lang, _checkout_url)
                    await message.answer(
                        _pending_text, parse_mode="HTML", reply_markup=_pending_kb
                    )
                    return

            except Exception as e:
                logger.debug(
                    "PAID_DEEPLINK_STRIPE_CHECK_ERROR: order_id=%s error=%s",
                    order_id,
                    e,
                )
                logger.exception(
                    "PAID_DEEPLINK_STRIPE_CHECK_ERROR: order_id=%s", order_id
                )
                _pending_text = _PAYMENT_PENDING_TEXTS.get(
                    _lang, _PAYMENT_PENDING_TEXTS["en"]
                )
                await message.answer(_pending_text, parse_mode="HTML")
                return
        else:
            logger.debug(
                "PAID_DEEPLINK_NO_SESSION_ID: order_id=%s — showing pending UX",
                order_id,
            )
            _pending_text = _PAYMENT_PENDING_TEXTS.get(
                _lang, _PAYMENT_PENDING_TEXTS["en"]
            )
            await message.answer(_pending_text, parse_mode="HTML")
            return

    # Status is PAID or FAILED — trigger delivery directly as fallback.
    # PAID: webhook may not have fired yet. FAILED: prior attempt crashed, retry with force.
    if status in ("paid", "failed"):
        logger.info("DEEPLINK_FALLBACK_DELIVERY | order=%s status=%s", order_id, status)
        _processing_msg = PROCESSING_MSG.get(
            _lang,
            PROCESSING_MSG.get(
                "en", "⏳ Payment is being processed. Please wait a few seconds..."
            ),
        )
        await message.answer(_processing_msg)
        try:
            from handlers.stripe_handler import deliver_document_after_payment as _ddap

            _force = status == "failed"
            _ok = await _ddap(message.bot, order_id, force=_force)
            if _ok:
                logger.info("DEEPLINK_FALLBACK_DELIVERY_SUCCESS | order=%s", order_id)
                # Email block lives in bot.py webhook handler which may never fire
                # (webhook arrives and sees SENT → idempotent skip). Send email here.
                try:
                    from utils.delivery_retry import _attempt_email_after_delivery as _aead
                    await _aead(order_id)
                except Exception as _em_err:
                    logger.warning("DEEPLINK_EMAIL_ERROR | order=%s err=%s", order_id, _em_err)
            else:
                logger.warning("DEEPLINK_FALLBACK_DELIVERY_FALSE | order=%s", order_id)
        except Exception as _dde:
            logger.error(
                "DEEPLINK_FALLBACK_DELIVERY_ERROR | order=%s err=%s", order_id, _dde
            )
        return

    # Unknown status — silent return (no "processing" spam)
    logger.debug(
        "PAID_DEEPLINK_UNKNOWN_STATUS: order_id=%s status=%s (silent)", order_id, status
    )
