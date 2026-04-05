# -*- coding: utf-8 -*-
"""
backend/gdpr.py
Stub GDPR manager for compatibility
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def _gdpr_lang(lang: str) -> str:
    """Normalize language for GDPR: ua → uk so Ukrainian selection gets Ukrainian strings."""
    if not lang:
        return "uk"
    lang = (lang or "").strip().lower()
    if lang == "ua":
        return "uk"
    return lang if lang in ("uk", "en", "de", "pl", "tr", "ar") else "en"


class GDPRManager:
    """Stub GDPR manager"""

    def get_consent_message(self, lang: str = "uk") -> str:
        """Get GDPR consent message (localized)."""
        lang = _gdpr_lang(lang)
        texts = {
            "uk": "📋 <b>Згода на обробку персональних даних</b>\n\nБез вашої згоди бот не може працювати.",
            "en": "📋 <b>GDPR Consent</b>\n\nWithout consent the bot cannot work.",
            "de": "📋 <b>DSGVO Zustimmung</b>\n\nOhne Zustimmung kann der Bot nicht arbeiten.",
            "pl": "📋 <b>Zgoda RODO</b>\n\nBez zgody bot nie może działać.",
            "tr": "📋 <b>KVKK Onayı</b>\n\nOnay olmadan bot çalışamaz.",
            "ar": "📋 <b>الموافقة على معالجة البيانات الشخصية</b>\n\nبدون الموافقة لا يمكن للبوت العمل.",
        }
        return texts.get(lang, texts["en"])

    def get_consent_keyboard(self, lang: str = "uk") -> InlineKeyboardMarkup:
        """Get GDPR consent keyboard (localized)."""
        lang = _gdpr_lang(lang)
        texts = {
            "uk": ("✅ Прийняти", "❌ Відхилити"),
            "en": ("✅ Accept", "❌ Decline"),
            "de": ("✅ Akzeptieren", "❌ Ablehnen"),
            "pl": ("✅ Akceptuję", "❌ Odrzucam"),
            "tr": ("✅ Kabul ediyorum", "❌ Reddet"),
            "ar": ("✅ أوافق", "❌ أرفض"),
        }
        accept, decline = texts.get(lang, texts["en"])
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(accept, callback_data="gdpr_accept"),
            InlineKeyboardButton(decline, callback_data="gdpr_decline")
        )
        return kb
    
    def get_decline_message(self, lang: str = "uk") -> str:
        """Get GDPR decline message (localized)."""
        lang = _gdpr_lang(lang)
        texts = {
            "uk": "❌ Без вашої згоди бот не може працювати.\n\nНатисніть /start, якщо передумаєте.",
            "en": "❌ Without consent the bot cannot work.\n\nPress /start if you change your mind.",
            "de": "❌ Ohne Zustimmung kann der Bot nicht arbeiten.\n\nDrücken Sie /start, wenn Sie es sich anders überlegen.",
            "pl": "❌ Bez zgody bot nie może działać.\n\nNaciśnij /start, jeśli zmienisz zdanie.",
            "tr": "❌ Onay olmadan bot çalışamaz.\n\nFikrinizi değiştirirseniz /start yazın.",
            "ar": "❌ بدون الموافقة لا يمكن للبوت العمل.\n\nاضغط /start إذا غيّرت رأيك.",
        }
        return texts.get(lang, texts["en"])
    
    def get_privacy_policy(self, lang: str = "uk") -> str:
        """Get privacy policy text"""
        return self.get_consent_message(lang)
    
    def get_terms_of_service(self, lang: str = "uk") -> str:
        """Get terms of service text"""
        return self.get_consent_message(lang)
    
    def get_back_keyboard(self, lang: str = "uk") -> InlineKeyboardMarkup:
        """Get back button keyboard (localized)."""
        lang = _gdpr_lang(lang)
        texts = {
            "uk": "← Назад",
            "en": "← Back",
            "de": "← Zurück",
            "pl": "← Wstecz",
            "tr": "← Geri",
            "ar": "← رجوع",
        }
        back_text = texts.get(lang, texts["en"])
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(back_text, callback_data="gdpr_back"))
        return kb


gdpr_manager = GDPRManager()
