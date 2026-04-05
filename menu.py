# -*- coding: utf-8 -*-
"""
menu.py - DEPRECATED: Old menu handler (NOT USED)

⚠️ WARNING: This file is DEPRECATED and should NOT be used.
The active menu handler is: backend/menu_handler.py

This file is kept for reference only. The register_handlers() function
will not register any handlers to avoid conflicts.
"""
from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)
logger.warning("⚠️ menu.py is DEPRECATED. Use backend/menu_handler.py instead.")

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

MENU_TEXTS = {
    'ua': {
        'family': '👨‍👩‍👧‍👦 Сім\'я',
        'housing': '🏠 Житло',
        'work': '💼 Робота',
        'profile': '👤 Профіль',
        'help': '🆘 Допомога',
        'language': '🌍 Мова',
    },
    'uk': {
        'family': '👨‍👩‍👧‍👦 Сім\'я',
        'housing': '🏠 Житло',
        'work': '💼 Робота',
        'profile': '👤 Профіль',
        'help': '🆘 Допомога',
        'language': '🌍 Мова',
    },
    'de': {
        'family': '👨‍👩‍👧‍👦 Familie',
        'housing': '🏠 Wohnung',
        'work': '💼 Arbeit',
        'profile': '👤 Profil',
        'help': '🆘 Hilfe',
        'language': '🌍 Sprache',
    },
    'en': {
        'family': '👨‍👩‍👧‍👦 Family',
        'housing': '🏠 Housing',
        'work': '💼 Work',
        'profile': '👤 Profile',
        'help': '🆘 Help',
        'language': '🌍 Language',
    },
    'pl': {
        'family': '👨‍👩‍👧‍👦 Rodzina',
        'housing': '🏠 Mieszkanie',
        'work': '💼 Praca',
        'profile': '👤 Profil',
        'help': '🆘 Pomoc',
        'language': '🌍 Język',
    },
    'tr': {
        'family': '👨‍👩‍👧‍👦 Aile',
        'housing': '🏠 Konut',
        'work': '💼 İş',
        'profile': '👤 Profil',
        'help': '🆘 Yardım',
        'language': '🌍 Dil',
    },
    'ar': {
        'family': '👨‍👩‍👧‍👦 العائلة',
        'housing': '🏠 السكن',
        'work': '💼 العمل',
        'profile': '👤 الملف الشخصي',
        'help': '🆘 المساعدة',
        'language': '🌍 اللغة',
    }
}

DOCUMENT_EXPLANATIONS = {
    'anmeldung': {
        'ua': 'Реєстрація місця проживання в Німеччині',
        'uk': 'Реєстрація місця проживання в Німеччині',
        'de': 'Anmeldung des Wohnsitzes in Deutschland',
        'en': 'Registration of residence in Germany',
        'pl': 'Rejestracja miejsca zamieszkania w Niemczech',
        'tr': 'Almanya\'da ikamet kaydı',
        'ar': 'تسجيل مكان الإقامة في ألمانيا'
    },
    'ummeldung': {
        'ua': 'Перереєстрація при переїзді',
        'uk': 'Перереєстрація при переїзді',
        'de': 'Ummeldung bei Umzug',
        'en': 'Re-registration when moving',
        'pl': 'Przerejestracja przy przeprowadzce',
        'tr': 'Taşınırken yeniden kayıt',
        'ar': 'إعادة التسجيل عند الانتقال'
    },
    'abmeldung': {
        'ua': 'Зняття з реєстрації при виїзді',
        'uk': 'Зняття з реєстрації при виїзді',
        'de': 'Abmeldung beim Auszug',
        'en': 'Deregistration when moving out',
        'pl': 'Wyrejestrowanie przy wyprowadzce',
        'tr': 'Taşınırken kayıt silme',
        'ar': 'إلغاء التسجيل عند المغادرة'
    },
    'wohngeld': {
        'ua': 'Допомога на оплату оренди житла',
        'uk': 'Допомога на оплату оренди житла',
        'de': 'Wohngeld für Mietunterstützung',
        'en': 'Housing allowance for rent support',
        'pl': 'Dodatek mieszkaniowy na wsparcie czynszu',
        'tr': 'Kira desteği için konut yardımı',
        'ar': 'بدل السكن لدعم الإيجار'
    },
    'wohnungsgeberbestaetigung': {
        'ua': 'Підтвердження від орендодавця про проживання',
        'uk': 'Підтвердження від орендодавця про проживання',
        'de': 'Bestätigung des Vermieters über den Wohnsitz',
        'en': 'Landlord confirmation of residence',
        'pl': 'Potwierdzenie od wynajmującego o zamieszkaniu',
        'tr': 'Kiralayanın ikamet onayı',
        'ar': 'تأكيد المالك على الإقامة'
    },
    'kindergeld': {
        'ua': 'Допомога на дітей від держави',
        'uk': 'Допомога на дітей від держави',
        'de': 'Kindergeld vom Staat',
        'en': 'Child benefit from the state',
        'pl': 'Zasiłek na dzieci od państwa',
        'tr': 'Devletten çocuk parası',
        'ar': 'إعانة الأطفال من الدولة'
    },
    'elterngeld': {
        'ua': 'Допомога батькам після народження дитини',
        'uk': 'Допомога батькам після народження дитини',
        'de': 'Elterngeld nach der Geburt',
        'en': 'Parental allowance after birth',
        'pl': 'Zasiłek rodzicielski po urodzeniu',
        'tr': 'Doğum sonrası ebeveyn yardımı',
        'ar': 'إعانة الوالدين بعد الولادة'
    },
    'kinderzuschlag': {
        'ua': 'Додаткова допомога для сімей з дітьми',
        'uk': 'Додаткова допомога для сімей з дітьми',
        'de': 'Zusätzliche Unterstützung für Familien mit Kindern',
        'en': 'Additional support for families with children',
        'pl': 'Dodatkowe wsparcie dla rodzin z dziećmi',
        'tr': 'Çocuklu aileler için ek destek',
        'ar': 'دعم إضافي للأسر التي لديها أطفال'
    },
    'unterhaltsvorschuss': {
        'ua': 'Авансова виплата аліментів від держави',
        'uk': 'Авансова виплата аліментів від держави',
        'de': 'Vorschuss auf Unterhaltszahlungen vom Staat',
        'en': 'Advance payment of child support from the state',
        'pl': 'Zaliczka na alimenty od państwa',
        'tr': 'Devletten nafaka avans ödemesi',
        'ar': 'دفعة مقدمة من النفقة من الدولة'
    },
    'arbeitslosengeld': {
        'ua': 'Пособія з безробіття',
        'uk': 'Пособія з безробіття',
        'de': 'Arbeitslosengeld',
        'en': 'Unemployment benefits',
        'pl': 'Zasiłek dla bezrobotnych',
        'tr': 'İşsizlik maaşı',
        'ar': 'إعانة البطالة'
    },
    'kurzarbeitergeld': {
        'ua': 'Допомога при скороченні робочих годин',
        'uk': 'Допомога при скороченні робочих годин',
        'de': 'Kurzarbeitergeld bei reduzierten Arbeitsstunden',
        'en': 'Short-time work allowance',
        'pl': 'Zasiłek przy skróconym czasie pracy',
        'tr': 'Kısaltılmış çalışma saatleri için yardım',
        'ar': 'بدل العمل بدوام جزئي'
    },
    'berufsausbildungsbeihilfe': {
        'ua': 'Допомога під час професійного навчання',
        'uk': 'Допомога під час професійного навчання',
        'de': 'Unterstützung während der Berufsausbildung',
        'en': 'Support during vocational training',
        'pl': 'Wsparcie podczas szkolenia zawodowego',
        'tr': 'Mesleki eğitim sırasında destek',
        'ar': 'الدعم أثناء التدريب المهني'
    }
}

HOUSING_DOCS = [
    ('anmeldung', 'anmeldung'),
    ('ummeldung', 'ummeldung'),
    ('wohnungsgeberbestaetigung', 'wohnungsgeberbestaetigung'),
    ('wohngeld', 'wohngeld'),
]

BENEFITS_DOCS = [
    ('kindergeld', 'kindergeld'),
    ('buergergeld', 'buergergeld'),
]

WORK_DOCS = [
    ('aufenthaltstitel', 'aufenthaltstitel'),
]

# Legacy alias
FAMILY_DOCS = BENEFITS_DOCS

DOCS_BY_COUNTRY = {
    "de": {
        "housing": HOUSING_DOCS,
        "benefits": BENEFITS_DOCS,
        "work": WORK_DOCS,
        "family": FAMILY_DOCS,
    },
}


def get_docs_for_country(country_code: str, category: str) -> list:
    """Return document list for a given country and category.

    Falls back to 'de' when the requested country is not configured yet.
    """
    country = DOCS_BY_COUNTRY.get(country_code, DOCS_BY_COUNTRY["de"])
    return country.get(category, [])

def get_main_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    lang = _norm_lang(lang)
    texts = _strict_get_text(MENU_TEXTS, lang)
    
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton(texts['housing']),
        KeyboardButton(texts['family']),
        KeyboardButton(texts['work']),
        KeyboardButton(texts['profile']),
        KeyboardButton(texts['help']),
        KeyboardButton(texts['language'])
    )
    return keyboard

def create_docs_keyboard(docs_list: list, lang: str = "uk") -> InlineKeyboardMarkup:
    """
    Creates Inline keyboard from document list.
    Resolves document names dynamically via document_handlers.get_document_config().
    Uses user language to render document titles with explanations.
    """
    try:
        from backend.document_handlers import get_document_config
    except ImportError:
        try:
            from document_handlers import get_document_config
        except ImportError:
            logger.error("Cannot import get_document_config")
            get_document_config = None
    
    lang = _norm_lang(lang)
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for doc_id, _ in docs_list:
        doc_config = get_document_config(doc_id) if get_document_config else None
        
        if doc_config:
            try:
                german_name = doc_config.get_name("de")
            except KeyError:
                german_name = doc_id.capitalize()
        else:
            german_name = doc_id.capitalize()
        
        explanation = _strict_get_text(DOCUMENT_EXPLANATIONS, doc_id)[lang]
        
        button_text = f"{german_name}\n{explanation}"
        
        keyboard.add(InlineKeyboardButton(
            text=button_text,
            callback_data=f"doc_{doc_id}"
        ))
    
    back_texts = {
        'ua': "◀️ Назад до меню",
        'uk': "◀️ Назад до меню",
        'de': "◀️ Zurück zum Menü",
        'en': "◀️ Back to menu",
        'pl': "◀️ Powrót do menu",
        'tr': "◀️ Menüye dön",
        'ar': "◀️ العودة إلى القائمة",
    }
    back_text = _strict_get_text(back_texts, lang)
    
    keyboard.add(InlineKeyboardButton(
        text=back_text,
        callback_data="back_to_menu"
    ))
    return keyboard

async def show_main_menu(message: types.Message, lang: str = "uk"):
    lang = _norm_lang(lang)
    
    texts = {
        'ua': "🇩🇪 <b>Головне меню</b>\n\nОберіть категорію документів:",
        'uk': "🇩🇪 <b>Головне меню</b>\n\nОберіть категорію документів:",
        'de': "🇩🇪 <b>Hauptmenü</b>\n\nWählen Sie eine Dokumentenkategorie:",
        'en': "🇩🇪 <b>Main Menu</b>\n\nSelect a document category:",
        'pl': "🇩🇪 <b>Menu główne</b>\n\nWybierz kategorię dokumentów:",
        'tr': "🇩🇪 <b>Ana Menü</b>\n\nBir belge kategorisi seçin:",
        'ar': "🇩🇪 <b>القائمة الرئيسية</b>\n\nاختر فئة المستندات:"
    }
    
    info_button_texts = {
        'ua': "ℹ️ Про сервіс",
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
    
    await message.answer(
        _strict_get_text(texts, lang),
        reply_markup=get_main_keyboard(lang),
        parse_mode="HTML"
    )
    
    await message.answer(
        "ℹ️",
        reply_markup=inline_kb
    )

async def show_housing_menu(message: types.Message, lang: str = "uk", country_code: str = "de"):
    lang = _norm_lang(lang)
    
    texts = {
        'ua': "🏠 <b>Житлові документи</b>\n\nОберіть тип документа:",
        'uk': "🏠 <b>Житлові документи</b>\n\nОберіть тип документа:",
        'de': "🏠 <b>Wohnungsdokumente</b>\n\nWählen Sie einen Dokumenttyp:",
        'en': "🏠 <b>Housing Documents</b>\n\nSelect a document type:",
        'pl': "🏠 <b>Dokumenty mieszkaniowe</b>\n\nWybierz typ dokumentu:",
        'tr': "🏠 <b>Konut Belgeleri</b>\n\nBir belge türü seçin:",
        'ar': "🏠 <b>مستندات السكن</b>\n\nاختر نوع المستند:"
    }
    
    docs = get_docs_for_country(country_code, "housing")
    await message.answer(
        _strict_get_text(texts, lang),
        reply_markup=create_docs_keyboard(docs, lang),
        parse_mode="HTML"
    )

async def show_family_menu(message: types.Message, lang: str = "uk", country_code: str = "de"):
    lang = _norm_lang(lang)
    
    texts = {
        'ua': "👨‍👩‍👧‍👦 <b>Сімейні документи</b>\n\nОберіть тип документа:",
        'uk': "👨‍👩‍👧‍👦 <b>Сімейні документи</b>\n\nОберіть тип документа:",
        'de': "👨‍👩‍👧‍👦 <b>Familiendokumente</b>\n\nWählen Sie einen Dokumenttyp:",
        'en': "👨‍👩‍👧‍👦 <b>Family Documents</b>\n\nSelect a document type:",
        'pl': "👨‍👩‍👧‍👦 <b>Dokumenty rodzinne</b>\n\nWybierz typ dokumentu:",
        'tr': "👨‍👩‍👧‍👦 <b>Aile Belgeleri</b>\n\nBir belge türü seçin:",
        'ar': "👨‍👩‍👧‍👦 <b>مستندات العائلة</b>\n\nاختر نوع المستند:"
    }
    
    docs = get_docs_for_country(country_code, "family")
    await message.answer(
        _strict_get_text(texts, lang),
        reply_markup=create_docs_keyboard(docs, lang),
        parse_mode="HTML"
    )

async def show_work_menu(message: types.Message, lang: str = "uk", country_code: str = "de"):
    lang = _norm_lang(lang)
    
    texts = {
        'ua': "💼 <b>Робочі документи</b>\n\nОберіть тип документа:",
        'uk': "💼 <b>Робочі документи</b>\n\nОберіть тип документа:",
        'de': "💼 <b>Arbeitsdokumente</b>\n\nWählen Sie einen Dokumenttyp:",
        'en': "💼 <b>Work Documents</b>\n\nSelect a document type:",
        'pl': "💼 <b>Dokumenty pracy</b>\n\nWybierz typ dokumentu:",
        'tr': "💼 <b>İş Belgeleri</b>\n\nBir belge türü seçin:",
        'ar': "💼 <b>مستندات العمل</b>\n\nاختر نوع المستند:"
    }
    
    docs = get_docs_for_country(country_code, "work")
    await message.answer(
        _strict_get_text(texts, lang),
        reply_markup=create_docs_keyboard(docs, lang),
        parse_mode="HTML"
    )

async def show_profile_menu(message: types.Message, lang: str = "uk"):
    lang = _norm_lang(lang)
    
    texts = {
        'ua': "👤 <b>Ваш профіль</b>\n\nТут ви можете переглянути свої дані та замовлення.",
        'uk': "👤 <b>Ваш профіль</b>\n\nТут ви можете переглянути свої дані та замовлення.",
        'de': "👤 <b>Ihr Profil</b>\n\nHier können Sie Ihre Daten und Bestellungen einsehen.",
        'en': "👤 <b>Your Profile</b>\n\nHere you can view your data and orders.",
        'pl': "👤 <b>Twój profil</b>\n\nTutaj możesz przeglądać swoje dane i zamówienia.",
        'tr': "👤 <b>Profiliniz</b>\n\nBurada verilerinizi ve siparişlerinizi görüntüleyebilirsiniz.",
        'ar': "👤 <b>ملفك الشخصي</b>\n\nهنا يمكنك عرض بياناتك وطلباتك."
    }
    
    button_texts = {
        'ua': {
            'orders': "📋 Мої замовлення",
            'family': "👨‍👩‍👧 Сім'я",
            'back': "◀️ Назад"
        },
        'uk': {
            'orders': "📋 Мої замовлення",
            'family': "👨‍👩‍👧 Сім'я",
            'back': "◀️ Назад"
        },
        'de': {
            'orders': "📋 Meine Bestellungen",
            'family': "👨‍👩‍👧 Familie",
            'back': "◀️ Zurück"
        },
        'en': {
            'orders': "📋 My Orders",
            'family': "👨‍👩‍👧 Family",
            'back': "◀️ Back"
        },
        'pl': {
            'orders': "📋 Moje zamówienia",
            'family': "👨‍👩‍👧 Rodzina",
            'back': "◀️ Wstecz"
        },
        'tr': {
            'orders': "📋 Siparişlerim",
            'family': "👨‍👩‍👧 Aile",
            'back': "◀️ Geri"
        },
        'ar': {
            'orders': "📋 طلباتي",
            'family': "👨‍👩‍👧 العائلة",
            'back': "◀️ رجوع"
        }
    }
    
    buttons = _strict_get_text(button_texts, lang)
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(buttons['orders'], callback_data="my_orders"),
        InlineKeyboardButton(buttons['family'], callback_data="family_menu"),
        InlineKeyboardButton(buttons['back'], callback_data="back_to_menu")
    )
    
    await message.answer(
        _strict_get_text(texts, lang),
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def show_help_menu(message: types.Message, lang: str = "uk"):
    lang = _norm_lang(lang)
    
    texts = {
        'ua': (
            "🆘 <b>Допомога</b>\n\n"
            "Якщо у вас виникли питання:\n"
            "• Напишіть /start щоб почати спочатку\n"
            "• Зверніться до підтримки: @support\n"
            "• FAQ: /faq"
        ),
        'uk': (
            "🆘 <b>Допомога</b>\n\n"
            "Якщо у вас виникли питання:\n"
            "• Напишіть /start щоб почати спочатку\n"
            "• Зверніться до підтримки: @support\n"
            "• FAQ: /faq"
        ),
        'de': (
            "🆘 <b>Hilfe</b>\n\n"
            "Wenn Sie Fragen haben:\n"
            "• Schreiben Sie /start um neu zu beginnen\n"
            "• Kontaktieren Sie den Support: @support\n"
            "• FAQ: /faq"
        ),
        'en': (
            "🆘 <b>Help</b>\n\n"
            "If you have questions:\n"
            "• Write /start to start over\n"
            "• Contact support: @support\n"
            "• FAQ: /faq"
        ),
        'pl': (
            "🆘 <b>Pomoc</b>\n\n"
            "Jeśli masz pytania:\n"
            "• Napisz /start, aby zacząć od nowa\n"
            "• Skontaktuj się z pomocą: @support\n"
            "• FAQ: /faq"
        ),
        'tr': (
            "🆘 <b>Yardım</b>\n\n"
            "Sorularınız varsa:\n"
            "• Yeniden başlamak için /start yazın\n"
            "• Destek ile iletişime geçin: @support\n"
            "• SSS: /faq"
        ),
        'ar': (
            "🆘 <b>المساعدة</b>\n\n"
            "إذا كان لديك أسئلة:\n"
            "• اكتب /start للبدء من جديد\n"
            "• اتصل بالدعم: @support\n"
            "• الأسئلة الشائعة: /faq"
        )
    }
    
    await message.answer(
        _strict_get_text(texts, lang),
        parse_mode="HTML"
    )

def match_menu_button(text: str) -> str:
    """
    Розпізнає яку кнопку меню натиснув користувач
    Повертає тип кнопки або None
    """
    for lang, buttons in MENU_TEXTS.items():
        for button_type, button_text in buttons.items():
            if button_text in text:
                return button_type
    
    return None

INFO_TEXTS = {
    "ua": {
        "title": "ℹ️ Про сервіс Deutschland PDF Assistant",
        "text": (
            "<b>Що це за сервіс?</b>\n"
            "Deutschland PDF Assistant допомагає швидко створити офіційні німецькі документи "
            "без знання німецької мови та без помилок.\n\n"
            "<b>Що ми робимо:</b>\n"
            "• Формуємо PDF-документи для державних установ Німеччини\n"
            "• Показуємо попередній перегляд (Preview)\n"
            "• Після підтвердження ви отримуєте фінальний PDF без водяних знаків\n\n"
            "<b>Типи документів:</b>\n"
            "• Anmeldung / Ummeldung\n"
            "• Kindergeld\n"
            "• Bürgergeld\n"
            "• Wohngeld\n"
            "• Інші офіційні заяви\n\n"
            "<b>Безпека:</b>\n"
            "• Файли не зберігаються\n"
            "• Preview та final PDF автоматично видаляються\n\n"
            "<b>Ви платите лише за готовий фінальний документ.</b>"
        )
    },
    "uk": {
        "title": "ℹ️ Про сервіс Deutschland PDF Assistant",
        "text": (
            "<b>Що це за сервіс?</b>\n"
            "Deutschland PDF Assistant допомагає швидко створити офіційні німецькі документи "
            "без знання німецької мови та без помилок.\n\n"
            "<b>Що ми робимо:</b>\n"
            "• Формуємо PDF-документи для державних установ Німеччини\n"
            "• Показуємо попередній перегляд (Preview)\n"
            "• Після підтвердження ви отримуєте фінальний PDF без водяних знаків\n\n"
            "<b>Типи документів:</b>\n"
            "• Anmeldung / Ummeldung\n"
            "• Kindergeld\n"
            "• Bürgergeld\n"
            "• Wohngeld\n"
            "• Інші офіційні заяви\n\n"
            "<b>Безпека:</b>\n"
            "• Файли не зберігаються\n"
            "• Preview та final PDF автоматично видаляються\n\n"
            "<b>Ви платите лише за готовий фінальний документ.</b>"
        )
    },
    "de": {
        "title": "ℹ️ Über den Deutschland PDF Assistant",
        "text": (
            "<b>Was ist dieser Service?</b>\n"
            "Deutschland PDF Assistant hilft Ihnen, offizielle deutsche Dokumente "
            "schnell und korrekt zu erstellen – auch ohne Deutschkenntnisse.\n\n"
            "<b>Was wir tun:</b>\n"
            "• Erstellung offizieller PDF-Dokumente für deutsche Behörden\n"
            "• Vorschau-Dokument (Preview)\n"
            "• Nach Bestätigung: offizielles PDF ohne Wasserzeichen\n\n"
            "<b>Dokumenttypen:</b>\n"
            "• Anmeldung / Ummeldung\n"
            "• Kindergeld\n"
            "• Bürgergeld\n"
            "• Wohngeld\n"
            "• Weitere Anträge\n\n"
            "<b>Sicherheit:</b>\n"
            "• Keine langfristige Speicherung\n"
            "• Vorschau- und Final-PDFs werden automatisch gelöscht\n\n"
            "<b>Bezahlung nur für das finale Dokument.</b>"
        )
    },
    "pl": {
        "title": "ℹ️ Informacje o Deutschland PDF Assistant",
        "text": (
            "<b>Czym jest ten serwis?</b>\n"
            "Deutschland PDF Assistant pomaga szybko i poprawnie przygotować "
            "oficjalne dokumenty w Niemczech.\n\n"
            "<b>Co robimy:</b>\n"
            "• Tworzymy oficjalne dokumenty PDF\n"
            "• Udostępniamy podgląd dokumentu\n"
            "• Po zatwierdzeniu otrzymujesz finalny PDF bez znaków wodnych\n\n"
            "<b>Rodzaje dokumentów:</b>\n"
            "• Anmeldung / Ummeldung\n"
            "• Kindergeld\n"
            "• Bürgergeld\n"
            "• Wohngeld\n\n"
            "<b>Bezpieczeństwo:</b>\n"
            "• Brak długoterminowego przechowywania\n"
            "• Pliki są automatycznie usuwane\n\n"
            "<b>Płacisz tylko za gotowy dokument.</b>"
        )
    },
    "tr": {
        "title": "ℹ️ Deutschland PDF Assistant Hakkında",
        "text": (
            "<b>Bu servis nedir?</b>\n"
            "Deutschland PDF Assistant, Almanya'daki resmi belgeleri "
            "hızlı ve doğru şekilde oluşturmanıza yardımcı olur.\n\n"
            "<b>Ne yapıyoruz:</b>\n"
            "• Resmi PDF belgeleri oluşturuyoruz\n"
            "• Önizleme (Preview) sunuyoruz\n"
            "• Onaydan sonra filigransız final PDF veriyoruz\n\n"
            "<b>Belge türleri:</b>\n"
            "• Anmeldung / Ummeldung\n"
            "• Kindergeld\n"
            "• Bürgergeld\n"
            "• Wohngeld\n\n"
            "<b>Güvenlik:</b>\n"
            "• Dosyalar saklanmaz\n"
            "• Tüm PDF'ler otomatik silinir\n\n"
            "<b>Sadece final belge için ödeme yaparsınız.</b>"
        )
    },
    "ar": {
        "title": "ℹ️ حول Deutschland PDF Assistant",
        "text": (
            "<b>ما هو هذا النظام؟</b>\n"
            "Deutschland PDF Assistant يساعدك على إنشاء مستندات رسمية في ألمانيا "
            "بسهولة وبدون أخطاء.\n\n"
            "<b>ماذا نقدم:</b>\n"
            "• إنشاء مستندات PDF رسمية\n"
            "• عرض نسخة معاينة\n"
            "• بعد التأكيد تحصل على PDF نهائي بدون علامة مائية\n\n"
            "<b>أنواع المستندات:</b>\n"
            "• Anmeldung / Ummeldung\n"
            "• Kindergeld\n"
            "• Bürgergeld\n"
            "• Wohngeld\n\n"
            "<b>الأمان:</b>\n"
            "• لا يتم تخزين الملفات\n"
            "• يتم حذف جميع الملفات تلقائيًا\n\n"
            "<b>الدفع فقط مقابل المستند النهائي.</b>"
        )
    },
    "en": {
        "title": "ℹ️ About Deutschland PDF Assistant",
        "text": (
            "<b>What is this service?</b>\n"
            "Deutschland PDF Assistant helps you generate official German documents "
            "quickly and correctly.\n\n"
            "<b>What we do:</b>\n"
            "• Generate official PDF documents\n"
            "• Provide a preview version\n"
            "• After confirmation you receive a final PDF without watermark\n\n"
            "<b>Document types:</b>\n"
            "• Anmeldung / Ummeldung\n"
            "• Kindergeld\n"
            "• Bürgergeld\n"
            "• Wohngeld\n\n"
            "<b>Security:</b>\n"
            "• No long-term storage\n"
            "• Files are deleted automatically\n\n"
            "<b>You pay only for the final document.</b>"
        )
    }
}

async def handle_info_about_project(callback_query: types.CallbackQuery):
    """Handle info_about_project callback - show localized info text"""
    try:
        from utils.helpers import get_user_lang
    except ImportError:
        def get_user_lang(user_id: int) -> str:
            return "en"
    
    user_id = callback_query.from_user.id
    
    try:
        user_lang = get_user_lang(user_id)
    except Exception:
        user_lang = "en"
    
    user_lang = _norm_lang(user_lang)
    
    info_data = _strict_get_text(INFO_TEXTS, user_lang)
    title = info_data["title"]
    text = info_data["text"]
    
    back_texts = {
        'ua': "⬅️ Назад до меню",
        'uk': "⬅️ Назад до меню",
        'de': "⬅️ Zurück zum Menü",
        'en': "⬅️ Back to menu",
        'pl': "⬅️ Powrót do menu",
        'tr': "⬅️ Menüye dön",
        'ar': "⬅️ العودة إلى القائمة",
    }
    back_text = _strict_get_text(back_texts, user_lang)
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(text=back_text, callback_data="back_to_main"))
    
    await callback_query.answer()
    await callback_query.message.answer(
        f"{title}\n\n{text}",
        parse_mode="HTML",
        reply_markup=kb
    )

def register_handlers(dp: Dispatcher):
    """
    DEPRECATED: This function does NOTHING to avoid conflicts.
    
    ⚠️ WARNING: This file is deprecated. Do NOT use this function.
    The active menu handler is: backend/menu_handler.py
    
    This function is kept for backward compatibility but will not register any handlers.
    """
    logger.warning("⚠️ menu.py.register_handlers() is DEPRECATED and does nothing.")
    logger.warning("⚠️ Use backend/menu_handler.py instead.")
    # Intentionally empty - do not register handlers to avoid conflicts
    pass
