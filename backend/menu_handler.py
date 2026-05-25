# -*- coding: utf-8 -*-
"""backend/menu_handler.py - Menu Handler v9.0 (ReplyKeyboard Edition)"""

import logging
from typing import Optional, Dict, Any, Tuple
from aiogram import Bot, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logger = logging.getLogger(__name__)

def _norm_lang(lang: str) -> str:
    """Normalize language code to consistent format."""
    lang = (lang or "").strip().lower()
    if lang == "ua":
        lang = "uk"
    if lang in ("uk", "en", "de", "pl", "tr", "ar"):
        return lang
    return "uk"

def _strict_get_text(texts_dict: Dict[str, Any], lang: str) -> Any:
    """
    STRICT language access - NO FALLBACKS ALLOWED.
    Raises KeyError if translation is missing for the requested language.
    """
    lang = _norm_lang(lang)
    if lang not in texts_dict:
        raise KeyError(f"Missing language '{lang}' in texts dictionary. Available: {list(texts_dict.keys())}")
    return texts_dict[lang]

def _extract_german_name(title_with_emoji: str) -> str:
    """Extract German document name without emoji."""
    parts = title_with_emoji.split(' ', 1)
    if len(parts) > 1:
        return parts[1]
    return title_with_emoji

MENU_BUTTONS = {
    'family': {
        'uk': '👨‍👩‍👧 Сім\'я',
        'de': '👨‍👩‍👧 Familie',
        'en': '👨‍👩‍👧 Family',
        'pl': '👨‍👩‍👧 Rodzina',
        'tr': '👨‍👩‍👧 Aile',
        'ar': '👨‍👩‍👧 العائلة'
    },
    'work': {
        'uk': '💼 Робота',
        'de': '💼 Arbeit',
        'en': '💼 Work',
        'pl': '💼 Praca',
        'tr': '💼 İş',
        'ar': '💼 العمل'
    },
    'housing': {
        'uk': '🏠 Житло',
        'de': '🏠 Wohnung',
        'en': '🏠 Housing',
        'pl': '🏠 Mieszkanie',
        'tr': '🏠 Konut',
        'ar': '🏠 السكن'
    },
    'support': {
        'uk': '🤝 Допомога',
        'de': '🤝 Unterstützung',
        'en': '🤝 Support',
        'pl': '🤝 Wsparcie',
        'tr': '🤝 Destek',
        'ar': '🤝 الدعم'
    },
    'profile': {
        'uk': '👤 Профіль',
        'de': '👤 Profil',
        'en': '👤 Profile',
        'pl': '👤 Profil',
        'tr': '👤 Profil',
        'ar': '👤 الملف'
    },
    'language': {
        'uk': '🌍 Мова',
        'de': '🌍 Sprache',
        'en': '🌍 Language',
        'pl': '🌍 Język',
        'tr': '🌍 Dil',
        'ar': '🌍 اللغة'
    }
}

MENU_TEXTS = {
    'welcome': {
        'uk': '🇩🇪 <b>Ласкаво просимо до German Doc Bot!</b>\n\nОберіть категорію документів:',
        'de': '🇩🇪 <b>Willkommen beim German Doc Bot!</b>\n\nWählen Sie eine Dokumentenkategorie:',
        'en': '🇩🇪 <b>Welcome to German Doc Bot!</b>\n\nSelect a document category:',
        'pl': '🇩🇪 <b>Witamy w German Doc Bot!</b>\n\nWybierz kategorię dokumentów:',
        'tr': '🇩🇪 <b>German Doc Bot\'a Hoş Geldiniz!</b>\n\nBir belge kategorisi seçin:',
        'ar': '🇩🇪 <b>مرحباً بك في German Doc Bot!</b>\n\nاختر فئة المستندات:'
    },
    'family_title': {
        'uk': '👨‍👩‍👧 <b>Сімейні документи</b>\n\nОберіть тип документа:',
        'de': '👨‍👩‍👧 <b>Familiendokumente</b>\n\nWählen Sie den Dokumenttyp:',
        'en': '👨‍👩‍👧 <b>Family Documents</b>\n\nSelect document type:',
        'pl': '👨‍👩‍👧 <b>Dokumenty rodzinne</b>\n\nWybierz typ dokumentu:',
        'tr': '👨‍👩‍👧 <b>Aile Belgeleri</b>\n\nBelge türünü seçin:',
        'ar': '👨‍👩‍👧 <b>مستندات العائلة</b>\n\nاختر نوع المستند:'
    },
    'work_title': {
        'uk': '💼 <b>Робочі документи</b>\n\nОберіть тип документа:',
        'de': '💼 <b>Arbeitsdokumente</b>\n\nWählen Sie den Dokumenttyp:',
        'en': '💼 <b>Work Documents</b>\n\nSelect document type:',
        'pl': '💼 <b>Dokumenty robocze</b>\n\nWybierz typ dokumentu:',
        'tr': '💼 <b>İş Belgeleri</b>\n\nBelge türünü seçin:',
        'ar': '💼 <b>مستندات العمل</b>\n\nاختر نوع المستند:'
    },
    'housing_title': {
        'uk': '🏠 <b>Житлові документи</b>\n\nОберіть тип документа:',
        'de': '🏠 <b>Wohnungsdokumente</b>\n\nWählen Sie den Dokumenttyp:',
        'en': '🏠 <b>Housing Documents</b>\n\nSelect document type:',
        'pl': '🏠 <b>Dokumenty mieszkaniowe</b>\n\nWybierz typ dokumentu:',
        'tr': '🏠 <b>Konut Belgeleri</b>\n\nBelge türünü seçin:',
        'ar': '🏠 <b>مستندات السكن</b>\n\nاختر نوع المستند:'
    },
    'support_title': {
        'uk': '🤝 <b>Соціальна допомога</b>\n\nОберіть тип документа:',
        'de': '🤝 <b>Soziale Unterstützung</b>\n\nWählen Sie den Dokumenttyp:',
        'en': '🤝 <b>Social Support</b>\n\nSelect document type:',
        'pl': '🤝 <b>Wsparcie socjalne</b>\n\nWybierz typ dokumentu:',
        'tr': '🤝 <b>Sosyal Destek</b>\n\nBelge türünü seçin:',
        'ar': '🤝 <b>الدعم الاجتماعي</b>\n\nاختر نوع المستند:'
    },
    'profile_title': {
        'uk': '👤 <b>Мій профіль</b>',
        'de': '👤 <b>Mein Profil</b>',
        'en': '👤 <b>My Profile</b>',
        'pl': '👤 <b>Mój profil</b>',
        'tr': '👤 <b>Profilim</b>',
        'ar': '👤 <b>ملفي الشخصي</b>'
    },
    'gdpr': {
        'uk': '📜 <b>Угода користувача</b>\n\nВикористовуючи цього бота, ви погоджуєтесь з обробкою персональних даних.',
        'de': '📜 <b>Nutzervereinbarung</b>\n\nMit der Nutzung dieses Bots stimmen Sie der Verarbeitung personenbezogener Daten zu.',
        'en': '📜 <b>User Agreement</b>\n\nBy using this bot, you agree to the processing of personal data.',
        'pl': '📜 <b>Umowa użytkownika</b>\n\nKorzystając z tego bota, zgadzasz się na przetwarzanie danych osobowych.',
        'tr': '📜 <b>Kullanıcı Sözleşmesi</b>\n\nBu botu kullanarak kişisel verilerin işlenmesini kabul ediyorsunuz.',
        'ar': '📜 <b>اتفاقية المستخدم</b>\n\nباستخدام هذا البوت، فإنك توافق على معالجة البيانات الشخصية.'
    },
    'language_select': {
        'uk': '🌍 <b>Оберіть мову:</b>',
        'de': '🌍 <b>Sprache wählen:</b>',
        'en': '🌍 <b>Select language:</b>',
        'pl': '🌍 <b>Wybierz język:</b>',
        'tr': '🌍 <b>Dil seçin:</b>',
        'ar': '🌍 <b>اختر اللغة:</b>'
    },
    'back': {
        'uk': '◀️ Назад',
        'de': '◀️ Zurück',
        'en': '◀️ Back',
        'pl': '◀️ Wstecz',
        'tr': '◀️ Geri',
        'ar': '◀️ رجوع'
    },
    'confirm': {
        'uk': '✅ Підтвердити',
        'de': '✅ Bestätigen',
        'en': '✅ Confirm',
        'pl': '✅ Potwierdź',
        'tr': '✅ Onayla',
        'ar': '✅ تأكيد'
    }
}

DOCUMENT_EXPLANATIONS = {
    'anmeldung': {
        'uk': 'Реєстрація місця проживання в Німеччині',
        'de': 'Anmeldung des Wohnsitzes in Deutschland',
        'en': 'Registration of residence in Germany',
        'pl': 'Rejestracja miejsca zamieszkania w Niemczech',
        'tr': 'Almanya\'da ikamet kaydı',
        'ar': 'تسجيل مكان الإقامة في ألمانيا'
    },
    'abmeldung': {
        'uk': 'Зняття з реєстрації при виїзді',
        'de': 'Abmeldung beim Auszug',
        'en': 'Deregistration when moving out',
        'pl': 'Wyrejestrowanie przy wyprowadzce',
        'tr': 'Taşınırken kayıt silme',
        'ar': 'إلغاء التسجيل عند المغادرة'
    },
    'wohngeld': {
        'uk': 'Допомога на оплату оренди житла',
        'de': 'Wohngeld für Mietunterstützung',
        'en': 'Housing allowance for rent support',
        'pl': 'Dodatek mieszkaniowy na wsparcie czynszu',
        'tr': 'Kira desteği için konut yardımı',
        'ar': 'بدل السكن لدعم الإيجار'
    },
    'kindergeld': {
        'uk': 'Допомога на дітей від держави',
        'de': 'Staatliche Unterstützung für Kinder',
        'en': 'Child benefit from the state',
        'pl': 'Zasiłek na dzieci od państwa',
        'tr': 'Devletten çocuk parası',
        'ar': 'إعانة الأطفال من الدولة'
    },
    'elterngeld': {
        'uk': 'Допомога батькам після народження дитини',
        'de': 'Unterstützung für Eltern nach der Geburt',
        'en': 'Parental allowance after birth',
        'pl': 'Zasiłek rodzicielski po urodzeniu',
        'tr': 'Doğum sonrası ebeveyn yardımı',
        'ar': 'إعانة الوالدين بعد الولادة'
    },
    'kinderzuschlag': {
        'uk': 'Додаткова допомога для сімей з дітьми',
        'de': 'Zusätzliche Unterstützung für Familien mit Kindern',
        'en': 'Additional support for families with children',
        'pl': 'Dodatkowe wsparcie dla rodzin z dziećmi',
        'tr': 'Çocuklu aileler için ek destek',
        'ar': 'دعم إضافي للأسر التي لديها أطفال'
    },
    'kinderfreibetrag': {
        'uk': 'Податкова пільга на дітей',
        'de': 'Steuerfreibetrag für Kinder',
        'en': 'Tax allowance for children',
        'pl': 'Ulga podatkowa na dzieci',
        'tr': 'Çocuklar için vergi muafiyeti',
        'ar': 'إعفاء ضريبي للأطفال'
    },
    'steuerklasse': {
        'uk': 'Податковий клас для прибуткового податку',
        'de': 'Steuerklasse für Lohnsteuer',
        'en': 'Tax class for income tax',
        'pl': 'Klasa podatkowa dla podatku dochodowego',
        'tr': 'Gelir vergisi için vergi sınıfı',
        'ar': 'فئة الضرائب لضريبة الدخل'
    },
    'buergergeld': {
        'uk': 'Базова підтримка для тих, хто шукає роботу',
        'de': 'Grundsicherung für Arbeitsuchende',
        'en': 'Basic income support for jobseekers',
        'pl': 'Podstawowe wsparcie dla osób poszukujących pracy',
        'tr': 'İş arayanlar için temel gelir desteği',
        'ar': 'دعم الدخل الأساسي للباحثين عن عمل'
    },
    'erstausstattung': {
        'uk': 'Початкове облаштування квартири',
        'de': 'Erstausstattung für die Wohnung',
        'en': 'Initial equipment for the apartment',
        'pl': 'Wyposażenie początkowe do mieszkania',
        'tr': 'Daire için ilk ekipman',
        'ar': 'المعدات الأولية للشقة'
    }
}

WEBAPP_BUTTON_TEXTS = {
    'uk': '📝 Відкрити форму',
    'de': '📝 Formular öffnen',
    'en': '📝 Open form',
    'pl': '📝 Otwórz formularz',
    'tr': '📝 Formu aç',
    'ar': '📝 افتح النموذج'
}

HOUSING_DOCUMENTS = [
    ('anmeldung', '📝 Anmeldung'),
    ('mietbescheinigung', '📋 Mietbescheinigung'),
    ('wohnungsgeberbestaetigung', '📋 Wohnungsgeberbestätigung'),
    ('wohngeld', '🏠 Wohngeld'),
]

BENEFITS_DOCUMENTS = [
    ('kindergeld', '👶 Kindergeld'),
    ('buergergeld', '💶 Bürgergeld'),
]

WORK_DOCUMENTS = [
    ('aufenthaltstitel', '🛂 Aufenthaltstitel'),
]

# Legacy aliases
FAMILY_DOCUMENTS = BENEFITS_DOCUMENTS
SUPPORT_DOCUMENTS = BENEFITS_DOCUMENTS

DOCUMENTS_BY_COUNTRY = {
    "de": {
        "housing": HOUSING_DOCUMENTS,
        "benefits": BENEFITS_DOCUMENTS,
        "work": WORK_DOCUMENTS,
        # legacy keys
        "family": FAMILY_DOCUMENTS,
        "support": SUPPORT_DOCUMENTS,
    },
}


def get_country_documents(country_code: str, category: str) -> list:
    """Return document list for a given country and category.

    Falls back to 'de' when the requested country is not configured yet.
    """
    country = DOCUMENTS_BY_COUNTRY.get(country_code, DOCUMENTS_BY_COUNTRY["de"])
    return country.get(category, [])

class MenuHandler:
    """Обробник меню бота з ReplyKeyboard"""
    
    def __init__(self, bot: Bot, db=None):
        """
        Ініціалізація MenuHandler.
        
        Args:
            bot: Екземпляр Bot
            db: Екземпляр Database (опційно)
        """
        self.bot = bot
        self.db = db
        logger.info("✅ MenuHandler ініціалізовано (ReplyKeyboard Edition)")
    
    def create_main_keyboard(self, lang: str = 'uk') -> ReplyKeyboardMarkup:
        """Створити ReplyKeyboard головного меню"""
        lang = _norm_lang(lang)
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        
        keyboard.row(
            KeyboardButton(_strict_get_text(MENU_BUTTONS['family'], lang)),
            KeyboardButton(_strict_get_text(MENU_BUTTONS['work'], lang))
        )
        
        keyboard.row(
            KeyboardButton(_strict_get_text(MENU_BUTTONS['housing'], lang)),
            KeyboardButton(_strict_get_text(MENU_BUTTONS['support'], lang))
        )
        
        keyboard.row(
            KeyboardButton(_strict_get_text(MENU_BUTTONS['profile'], lang)),
            KeyboardButton(_strict_get_text(MENU_BUTTONS['language'], lang))
        )
        
        return keyboard
    
    def create_documents_keyboard(
        self,
        documents: list,
        lang: str = "uk"
    ) -> InlineKeyboardMarkup:
        keyboard = InlineKeyboardMarkup(row_width=1)

        for doc_item in documents:
            if isinstance(doc_item, (list, tuple)) and len(doc_item) == 2:
                doc_type, doc_name_with_emoji = doc_item
                german_name = _extract_german_name(doc_name_with_emoji)
            else:
                doc_type = doc_item[0]
                german_name = doc_type.capitalize()

            explanation = _strict_get_text(DOCUMENT_EXPLANATIONS.get(doc_type, {}), lang)
            button_text = f"{german_name}\n{explanation}" if explanation else german_name

            if doc_type == "termin":
                callback_data = "termin_entry"
            else:
                callback_data = f"doc_{doc_type}"

            keyboard.add(
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=callback_data
                )
            )

        return keyboard
    
    def get_webapp_url(self, base_url: str, doc_type: str = None, lang: str = 'uk') -> str:
        """
        Отримати WebApp URL з правильним lang параметром.
        
        Args:
            base_url: Базовий URL WebApp
            doc_type: Тип документа (опціонально)
            lang: Мова користувача (нормалізується автоматично)
        
        Returns:
            URL з lang параметром
        """
        lang = _norm_lang(lang)
        
        if '?' in base_url:
            url = f"{base_url}&lang={lang}"
        else:
            url = f"{base_url}?lang={lang}"
        
        if doc_type:
            if '&' in url:
                url = f"{url}&doc_type={doc_type}"
            else:
                url = f"{url}&doc_type={doc_type}"
        
        return url
    
    def create_language_keyboard(self) -> InlineKeyboardMarkup:
        """Створити InlineKeyboard вибору мови"""
        keyboard = InlineKeyboardMarkup(row_width=2)
        
        languages = [
            ('🇺🇦 Українська', 'set_lang_uk'),
            ('🇩🇪 Deutsch', 'set_lang_de'),
            ('🇵🇱 Polski', 'set_lang_pl'),
            ('🇬🇧 English', 'set_lang_en'),
            ('🇹🇷 Türkçe', 'set_lang_tr'),
            ('🇸🇦 العربية', 'set_lang_ar'),
        ]
        
        for i in range(0, len(languages), 2):
            row = [InlineKeyboardButton(text=languages[i][0], callback_data=languages[i][1])]
            if i + 1 < len(languages):
                row.append(InlineKeyboardButton(text=languages[i + 1][0], callback_data=languages[i + 1][1]))
            keyboard.row(*row)
        
        return keyboard
    
    async def show_language_selection(self, message: types.Message) -> None:
        """Показує вибір мови"""
        try:
            keyboard = self.create_language_keyboard()
            
            text = (
                "🌍 Оберіть мову / Choose language / Sprache wählen\n"
                "Wybierz język / Dil seçin / اختر اللغة"
            )
            
            await message.answer(text, reply_markup=keyboard)
            logger.info(f"✅ Вибір мови показано {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ show_language_selection: {e}")
    
    async def show_gdpr_notice(self, message: types.Message, lang: str = 'uk') -> None:
        """Показує GDPR повідомлення"""
        try:
            lang = _norm_lang(lang)
            gdpr_text = _strict_get_text(MENU_TEXTS['gdpr'], lang)
            confirm_text = _strict_get_text(MENU_TEXTS['confirm'], lang)
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(confirm_text, callback_data="gdpr_confirmed"))
            
            await message.answer(gdpr_text, reply_markup=keyboard, parse_mode='HTML')
            logger.info(f"✅ GDPR показано {message.from_user.id} ({lang})")
            
        except Exception as e:
            logger.error(f"❌ show_gdpr_notice: {e}")
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("✅ Підтвердити", callback_data="gdpr_confirmed"))
            await message.answer("📜 Підтвердіть умови", reply_markup=keyboard)
    
    async def show_main_menu(self, message: types.Message, lang: str = 'uk') -> None:
        """Показує головне меню з ReplyKeyboard та inline кнопкою About"""
        try:
            lang = _norm_lang(lang)
            text = _strict_get_text(MENU_TEXTS['welcome'], lang)
            keyboard = self.create_main_keyboard(lang)
            
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            
            info_button_texts = {
                'uk': "ℹ️ Про сервіс",
                'de': "ℹ️ Über den Service",
                'en': "ℹ️ About the service",
                'pl': "ℹ️ O serwisie",
                'tr': "ℹ️ Servis hakkında",
                'ar': "ℹ️ حول الخدمة",
            }
            info_button_text = _strict_get_text(info_button_texts, lang)
            
            inline_kb = InlineKeyboardMarkup(row_width=1)
            inline_kb.add(InlineKeyboardButton(
                text=info_button_text,
                callback_data="info_about_project"
            ))
            
            await message.answer("ℹ️", reply_markup=inline_kb)
            
            logger.info(f"✅ Головне меню показано {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ show_main_menu: {e}")
    
    async def show_family_menu(self, message: types.Message, lang: str = 'uk', country_code: str = 'de') -> None:
        """Меню сімейних документів"""
        try:
            lang = _norm_lang(lang)
            text = _strict_get_text(MENU_TEXTS['family_title'], lang)
            docs = get_country_documents(country_code, "family")
            keyboard = self.create_documents_keyboard(docs, lang)
            
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            logger.info(f"✅ Меню Сім'я показано {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ show_family_menu: {e}")
    
    async def show_work_menu(self, message: types.Message, lang: str = 'uk', country_code: str = 'de') -> None:
        """Меню робочих документів"""
        try:
            lang = _norm_lang(lang)
            text = _strict_get_text(MENU_TEXTS['work_title'], lang)
            docs = get_country_documents(country_code, "work")
            keyboard = self.create_documents_keyboard(docs, lang)
            
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            logger.info(f"✅ Меню Робота показано {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ show_work_menu: {e}")
    
    async def show_housing_menu(self, message: types.Message, lang: str = 'uk', country_code: str = 'de') -> None:
        """Меню житлових документів"""
        try:
            lang = _norm_lang(lang)
            text = _strict_get_text(MENU_TEXTS['housing_title'], lang)
            docs = get_country_documents(country_code, "housing")
            keyboard = self.create_documents_keyboard(docs, lang)
            
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            logger.info(f"✅ Меню Житло показано {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ show_housing_menu: {e}")
    
    async def show_support_menu(self, message: types.Message, lang: str = 'uk', country_code: str = 'de') -> None:
        """Меню соціальної допомоги"""
        try:
            lang = _norm_lang(lang)
            text = _strict_get_text(MENU_TEXTS['support_title'], lang)
            docs = get_country_documents(country_code, "support")
            keyboard = self.create_documents_keyboard(docs, lang)
            
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            logger.info(f"✅ Меню Допомога показано {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ show_support_menu: {e}")
    
    async def show_profile_menu(self, message: types.Message, lang: str = 'uk') -> None:
        """Меню профілю користувача"""
        try:
            lang = _norm_lang(lang)
            user_id = message.from_user.id if hasattr(message, 'from_user') else message.chat.id
            
            text = _strict_get_text(MENU_TEXTS['profile_title'], lang)
            
            _profile_created = {"uk": "📋 Профіль створено", "en": "📋 Profile created", "de": "📋 Profil erstellt",
                                "pl": "📋 Profil utworzony", "tr": "📋 Profil oluşturuldu", "ar": "📋 تم إنشاء الملف"}
            _orders_count = {"uk": "📄 Замовлень: {n}", "en": "📄 Orders: {n}", "de": "📄 Bestellungen: {n}",
                             "pl": "📄 Zamówień: {n}", "tr": "📄 Sipariş: {n}", "ar": "📄 الطلبات: {n}"}
            _my_orders_btn = {"uk": "📋 Мої замовлення", "en": "📋 My Orders", "de": "📋 Meine Bestellungen",
                              "pl": "📋 Moje zamówienia", "tr": "📋 Siparişlerim", "ar": "📋 طلباتي"}
            _change_lang_btn = {"uk": "🌍 Змінити мову", "en": "🌍 Change language", "de": "🌍 Sprache ändern",
                                "pl": "🌍 Zmień język", "tr": "🌍 Dili değiştir", "ar": "🌍 تغيير اللغة"}
            if self.db:
                try:
                    profile = self.db.get_profile(user_id)
                    orders = self.db.get_user_orders(user_id, limit=5)
                    
                    if profile:
                        text += f"\n\n{_profile_created.get(lang, _profile_created['en'])}"
                    
                    if orders:
                        text += f"\n{_orders_count.get(lang, _orders_count['en']).format(n=len(orders))}"
                except Exception as e:
                    logger.error(f"❌ Error fetching profile: {e}")
            
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton(_my_orders_btn.get(lang, _my_orders_btn["en"]), callback_data="my_orders"),
                InlineKeyboardButton(_change_lang_btn.get(lang, _change_lang_btn["en"]), callback_data="change_language"),
                InlineKeyboardButton(_strict_get_text(MENU_TEXTS['back'], lang), callback_data="back_to_main")
            )
            
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
            logger.info(f"✅ Профіль показано {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ show_profile_menu: {e}")
    
    def match_menu_button(self, text: str) -> Optional[str]:
        """
        Визначає яка кнопка меню натиснута.
        
        Args:
            text: Текст кнопки
        
        Returns:
            Категорія ('family', 'work', 'housing', 'support', 'profile', 'language') або None
        """
        if not text:
            return None
        
        for button_type, translations in MENU_BUTTONS.items():
            for lang, button_text in translations.items():
                if text == button_text:
                    return button_type
        
        return None

__all__ = ['MenuHandler']
