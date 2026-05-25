# -*- coding: utf-8 -*-
"""
Багатомовна система текстів - backend/texts/__init__.py

Підтримувані мови: uk, de, pl, en, tr, ar
"""

from typing import Dict, Any, Optional

# Імпорт всіх мовних модулів
try:
    from . import uk, de, pl, en, tr, ar
except ImportError as e:
    # Якщо якась мова не завантажилась - не критично
    import logging
    logging.warning(f"Деякі мовні модулі не завантажено: {e}")
    uk = de = pl = en = tr = ar = None

# Мапа мовних модулів
LANG_MODULES = {
    'uk': uk,
    'de': de,
    'pl': pl,
    'en': en,
    'tr': tr,
    'ar': ar
}

# Дефолтна мова
DEFAULT_LANG = 'uk'

# Один чіткий дисклеймер довіри (показати один раз, напр. на інтро)
TRUST_DISCLAIMER = {
    'uk': "⚠️ Ми не є державним органом. Ми допомагаємо заповнити документи за зразком.",
    'en': "⚠️ We are not a government authority. We help fill out documents by sample.",
    'de': "⚠️ Wir sind keine Behörde. Wir helfen, Dokumente nach Vorlage auszufüllen.",
    'pl': "⚠️ Nie jesteśmy organem państwowym. Pomagamy wypełniać dokumenty według wzoru.",
    'tr': "⚠️ Devlet kurumu değiliz. Belgeleri örnekteki gibi doldurmanıza yardımcı oluyoruz.",
    'ar': "⚠️ نحن لسنا جهة حكومية. نساعد في ملء المستندات حسب النموذج.",
}


def get_trust_disclaimer(lang: str = 'uk') -> str:
    """Один чіткий дисклеймер довіри для всіх мов. Без fallback — повертає uk якщо мови немає."""
    if lang == "ua":
        lang = "uk"
    return TRUST_DISCLAIMER.get(lang, TRUST_DISCLAIMER[DEFAULT_LANG])


def get_text(category: str, key: str, lang: str = 'uk') -> str:
    """
    Отримує текст за категорією та ключем.
    
    Args:
        category: Категорія ('gdpr', 'menu', 'message', 'document')
        key: Ключ тексту
        lang: Код мови (uk, de, pl, en, tr, ar)
    
    Returns:
        Текст або '' якщо не знайдено
    
    Example:
        >>> get_text('menu', 'main_menu', 'uk')
        '📋 Головне меню'
    """
    # Якщо мова не підтримується - використовуємо uk
    if lang not in LANG_MODULES or LANG_MODULES[lang] is None:
        lang = DEFAULT_LANG
    
    module = LANG_MODULES[lang]
    
    # Мапа категорій до атрибутів модуля
    category_map = {
        'gdpr': 'GDPR_TEXT',
        'menu': 'MENU_TEXTS',
        'message': 'MESSAGE_TEXTS',
        'document': 'DOCUMENT_TEXTS',
        'what_to_do': 'WHAT_TO_DO_TEXTS',
        'situation_checker': 'SITUATION_CHECKER_TEXTS',
        'life_checklist': 'LIFE_CHECKLIST_TEXTS',
        'deadlines': 'DEADLINES_TEXTS',
    }
    
    attr_name = category_map.get(category)
    if not attr_name or not hasattr(module, attr_name):
        return ''
    
    texts = getattr(module, attr_name)
    
    # Для GDPR_TEXT - це просто рядок
    if category == 'gdpr':
        return texts if isinstance(texts, str) else ''
    
    # Для інших - словник
    return texts.get(key, '') if isinstance(texts, dict) else ''


def get_gdpr(lang: str = 'uk') -> str:
    """Отримує GDPR текст для мови"""
    return get_text('gdpr', '', lang) or get_text('gdpr', '', DEFAULT_LANG)


def get_intro_text(lang: str = 'uk') -> str:
    """
    Отримує вступний текст проєкту для мови.
    
    Args:
        lang: Код мови (uk, de, pl, en, tr, ar)
    
    Returns:
        Вступний текст або текст за замовчуванням (uk) якщо мова не знайдена
    """
    # Normalize language code (ua -> uk for compatibility)
    if lang == "ua":
        lang = "uk"
    
    if lang not in LANG_MODULES or LANG_MODULES[lang] is None:
        lang = DEFAULT_LANG
    
    module = LANG_MODULES[lang]
    intro_text = getattr(module, 'INTRO_TEXT', '')
    
    # Fallback to default language if empty
    if not intro_text and lang != DEFAULT_LANG:
        default_module = LANG_MODULES[DEFAULT_LANG]
        intro_text = getattr(default_module, 'INTRO_TEXT', '')
    
    return intro_text


def get_all_texts(lang: str = 'uk') -> Dict[str, Any]:
    """
    Отримує всі тексти для мови.
    
    Returns:
        {'gdpr': str, 'menu': dict, 'message': dict, 'document': dict}
    """
    if lang not in LANG_MODULES or LANG_MODULES[lang] is None:
        lang = DEFAULT_LANG
    
    module = LANG_MODULES[lang]
    
    return {
        'gdpr': getattr(module, 'GDPR_TEXT', ''),
        'menu': getattr(module, 'MENU_TEXTS', {}),
        'message': getattr(module, 'MESSAGE_TEXTS', {}),
        'document': getattr(module, 'DOCUMENT_TEXTS', {})
    }


def get_document_next_steps(doc_type: str, lang: str = 'uk') -> Optional[str]:
    """
    Returns localized "what to do next" block for a document type (e.g. anmeldung).
    Used after PDF preview and after final delivery. Returns None if no steps defined.
    Uses backend.next_steps (localized, available in multiple languages).
    """
    try:
        from backend.next_steps import get_next_steps
        return get_next_steps(doc_type, lang)
    except Exception:
        return None


def get_document_delivery_message(doc_type: str, lang: str = 'uk') -> Optional[str]:
    """
    Returns message for paid delivery: official blank link + step-by-step instructions.
    Used by deliver_document after sending the filled PDF.
    """
    try:
        from backend.next_steps import get_delivery_message
        return get_delivery_message(doc_type, lang)
    except Exception:
        return get_document_next_steps(doc_type, lang)


def get_anmeldung_unfilled_fields_message(lang: str = 'uk') -> Optional[str]:
    """
    Returns short localized explanation that some Anmeldung fields are intentionally not filled.
    Only for doc_type=anmeldung; used after PDF + delivery message.
    """
    try:
        from backend.next_steps import get_anmeldung_unfilled_fields_message as _get
        return _get(lang)
    except Exception:
        return None


def get_anmeldung_required_fields_missing_message(lang: str = 'uk') -> str:
    """
    Returns localized message when Anmeldung required fields are missing at delivery.
    Used only for doc_type=anmeldung; do not call create_final_pdf when this applies.
    """
    try:
        from backend.next_steps import get_anmeldung_required_fields_missing_message as _get
        return _get(lang)
    except Exception:
        return "Please reopen the form, fill in all required fields, and try again."


# Експорт для зворотної сумісності
GDPR_TEXTS = {lang: get_gdpr(lang) for lang in LANG_MODULES.keys()}
MENU_TEXTS = {lang: get_all_texts(lang)['menu'] for lang in LANG_MODULES.keys()}
MESSAGE_TEXTS = {lang: get_all_texts(lang)['message'] for lang in LANG_MODULES.keys()}
DOCUMENT_TEXTS = {lang: get_all_texts(lang)['document'] for lang in LANG_MODULES.keys()}
INTRO_TEXTS = {lang: get_intro_text(lang) for lang in LANG_MODULES.keys()}

__all__ = [
    'get_text',
    'get_gdpr',
    'get_trust_disclaimer',
    'get_intro_text',
    'get_all_texts',
    'get_document_next_steps',
    'get_document_delivery_message',
    'get_anmeldung_unfilled_fields_message',
    'get_anmeldung_required_fields_missing_message',
    'GDPR_TEXTS',
    'MENU_TEXTS',
    'MESSAGE_TEXTS',
    'DOCUMENT_TEXTS',
    'INTRO_TEXTS',
    'DEFAULT_LANG'
]