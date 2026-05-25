# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - Data Processor
=====================================
Транслітерація, очистка та підготовка даних для німецьких PDF документів.

Функції:
- Транслітерація кирилиці → латиниця (Віталій → Vitalii)
- Очистка даних (strip, capitalize)
- Валідація для німецьких документів
"""

import re
import logging
from typing import Dict, Any, Optional
from unidecode import unidecode

logger = logging.getLogger(__name__)

# ============================================================================
# ТРАНСЛІТЕРАЦІЯ КИРИЛИЦІ → ЛАТИНИЦЯ
# ============================================================================

# Український словник транслітерації (згідно з паспортними правилами)
UA_TRANSLIT_TABLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g',
    'д': 'd', 'е': 'e', 'є': 'ye', 'ж': 'zh', 'з': 'z',
    'и': 'y', 'і': 'i', 'ї': 'yi', 'й': 'i', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p',
    'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f',
    'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ь': '', 'ю': 'yu', 'я': 'ya', "'": '', "\u2019": '', "\u02bc": '',
    # Великі літери
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'H', 'Ґ': 'G',
    'Д': 'D', 'Е': 'E', 'Є': 'Ye', 'Ж': 'Zh', 'З': 'Z',
    'И': 'Y', 'І': 'I', 'Ї': 'Yi', 'Й': 'I', 'К': 'K',
    'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O', 'П': 'P',
    'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F',
    'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
    'Ь': '', 'Ю': 'Yu', 'Я': 'Ya',
}

# Російський словник транслітерації
RU_TRANSLIT_TABLE = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
    'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
    'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
    # Великі літери
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D',
    'Е': 'E', 'Ё': 'Yo', 'Ж': 'Zh', 'З': 'Z', 'И': 'I',
    'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
    'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T',
    'У': 'U', 'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch',
    'Ш': 'Sh', 'Щ': 'Shch', 'Ъ': '', 'Ы': 'Y', 'Ь': '',
    'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya',
}

# Об'єднаний словник
TRANSLIT_TABLE = {**UA_TRANSLIT_TABLE, **RU_TRANSLIT_TABLE}


def has_cyrillic(text: str) -> bool:
    """Перевірка чи текст містить кирилицю"""
    if not text:
        return False
    return bool(re.search('[а-яА-ЯіїєґІЇЄҐёЁ]', text))


def transliterate(text: str, use_unidecode_fallback: bool = True) -> str:
    """
    Транслітерація тексту з кирилиці в латиницю.
    
    Особливості:
    - Використовує український/російський словник транслітерації
    - Fallback на unidecode для інших символів
    - Зберігає німецькі умляути (ä, ö, ü, ß)
    
    Args:
        text: Вхідний текст
        use_unidecode_fallback: Використовувати unidecode для невідомих символів
    
    Returns:
        Транслітерований текст
    
    Examples:
        >>> transliterate("Віталій")
        'Vitalii'
        >>> transliterate("Київ")
        'Kyiv'
        >>> transliterate("München")  # Зберігає умляут
        'München'
    """
    if not text:
        return text
    
    # Якщо немає кирилиці - повертаємо як є
    if not has_cyrillic(text):
        return text
    
    result = []
    for char in text:
        if char in TRANSLIT_TABLE:
            result.append(TRANSLIT_TABLE[char])
        elif use_unidecode_fallback and ord(char) > 127:
            # Перевіряємо чи це не німецький символ
            if char in 'äöüÄÖÜß':
                result.append(char)  # Зберігаємо умляути
            else:
                result.append(unidecode(char))
        else:
            result.append(char)
    
    return ''.join(result)


# ============================================================================
# ОЧИСТКА ДАНИХ (DATA CLEANING)
# ============================================================================

# Поля, які потребують capitalize
NAME_FIELDS = {
    'first_name', 'last_name', 'birth_name', 'birth_place', 'city',
    'child_first_name', 'child_last_name', 'child_name', 'child_birth_place',
    'spouse_first_name', 'spouse_last_name', 'landlord_name', 'employer_name',
    'account_holder', 'signature_place', 'bank_name'
}

# Поля, які потребують UPPERCASE
UPPERCASE_FIELDS = {'iban', 'bic'}

# Поля, які НЕ потребують транслітерації (вже латиниця)
NO_TRANSLIT_FIELDS = {'iban', 'bic', 'email', 'phone', 'tax_id', 'social_security_number'}


def clean_string(value: str) -> str:
    """
    Базова очистка рядка:
    - Видалення зайвих пробілів
    - Видалення переносів рядків
    """
    if not value:
        return value
    
    # Видаляємо зайві пробіли
    value = ' '.join(value.split())
    # Видаляємо пробіли на початку/кінці
    value = value.strip()
    
    return value


def capitalize_name(value: str) -> str:
    """
    Правильна капіталізація імен:
    - Перша літера велика
    - Підтримка подвійних імен (Anna-Maria → Anna-Maria)
    """
    if not value:
        return value
    
    # Розбиваємо по дефісу для подвійних імен
    parts = value.split('-')
    capitalized_parts = [part.strip().capitalize() for part in parts if part.strip()]
    
    return '-'.join(capitalized_parts)


def format_iban(iban: str) -> str:
    """
    Форматування IBAN:
    - Видалення будь-яких зайвих символів (пробіли, крапки, тире)
    - Переведення у верхній регістр (Uppercase)
    - Безпечна обробка порожніх значень
    """
    if not iban or not isinstance(iban, str):
        return ""
    
    # Видаляємо ВСЕ, крім латинських літер та цифр
    iban = re.sub(r'[^A-Z0-9]', '', iban.upper())
    
    return iban


def format_phone(phone: str) -> str:
    """
    Очистка номера телефону:
    - Залишаємо тільки цифри та +
    """
    if not phone:
        return phone
    
    # Залишаємо тільки цифри, +, пробіли
    cleaned = re.sub(r'[^\d\+\s\-]', '', phone)
    # Видаляємо зайві пробіли
    cleaned = ' '.join(cleaned.split())
    
    return cleaned


def format_postal_code(postal_code: str) -> str:
    """
    Форматування поштового індексу:
    - Тільки цифри
    - Доповнення нулями до 5 цифр (для Німеччини)
    """
    if not postal_code:
        return postal_code
    
    # Залишаємо тільки цифри
    digits = re.sub(r'\D', '', postal_code)
    
    # Доповнюємо нулями для німецького формату (5 цифр)
    if len(digits) < 5:
        digits = digits.zfill(5)
    
    return digits


def format_date(date_str: str) -> str:
    """
    Форматування дати у німецький формат DD.MM.YYYY
    """
    if not date_str:
        return date_str
    
    # Якщо вже у правильному форматі
    if re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_str):
        return date_str
    
    # ISO формат (YYYY-MM-DD)
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
    if match:
        year, month, day = match.groups()
        return f"{day}.{month}.{year}"
    
    # Формат з /
    match = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', date_str)
    if match:
        day, month, year = match.groups()
        return f"{day}.{month}.{year}"
    
    return date_str


# ============================================================================
# ГОЛОВНА ФУНКЦІЯ ОБРОБКИ ДАНИХ
# ============================================================================

def process_user_data(
    user_data: Dict[str, Any],
    transliterate_cyrillic: bool = True,
    clean_data: bool = True,
    log_changes: bool = True
) -> Dict[str, Any]:
    """
    Повна обробка даних користувача для PDF генерації.
    
    Етапи:
    1. Очистка (strip, remove extra spaces)
    2. Транслітерація кирилиці → латиниця
    3. Капіталізація імен/міст
    4. Форматування спеціальних полів (IBAN, телефон, індекс, дата)
    
    Args:
        user_data: Словник з даними користувача
        transliterate_cyrillic: Транслітерувати кирилицю
        clean_data: Очищати дані
        log_changes: Логувати всі зміни
    
    Returns:
        Оброблений словник даних
    """
    if not user_data:
        return {}
    
    processed = {}
    changes_log = []
    
    for key, value in user_data.items():
        original_value = value
        
        # Пропускаємо не-строкові значення
        if not isinstance(value, str):
            processed[key] = value
            continue
        
        # 1. Базова очистка
        if clean_data:
            value = clean_string(value)
        
        # 2. Транслітерація (крім спеціальних полів)
        if transliterate_cyrillic and key not in NO_TRANSLIT_FIELDS:
            if has_cyrillic(value):
                value = transliterate(value)
                if log_changes:
                    changes_log.append(f"  Transliterated {key}: '{original_value}' → '{value}'")
        
        # 3. Форматування спеціальних полів
        if key in UPPERCASE_FIELDS:
            value = value.upper()
        elif key in NAME_FIELDS:
            value = capitalize_name(value)
        elif key == 'iban':
            value = format_iban(value)
        elif key == 'phone' or key == 'mobile':
            value = format_phone(value)
        elif key == 'postal_code' or key == 'zip_code':
            value = format_postal_code(value)
        elif 'date' in key.lower():
            value = format_date(value)
        
        # Логуємо зміни
        if log_changes and original_value != value and not has_cyrillic(original_value):
            changes_log.append(f"  Formatted {key}: '{original_value}' → '{value}'")
        
        processed[key] = value
    
    # Виводимо лог змін
    if log_changes and changes_log:
        logger.info(f"Data processing complete. Changes made:\n" + "\n".join(changes_log))
    
    return processed


# ============================================================================
# ВАЛІДАЦІЯ ДЛЯ НІМЕЦЬКИХ ДОКУМЕНТІВ
# ============================================================================

# Довжина IBAN по країнах
IBAN_LENGTHS = {
    'DE': 22, 'AT': 20, 'CH': 21, 'FR': 27, 'IT': 27, 'ES': 24,
    'NL': 18, 'BE': 16, 'PL': 28, 'CZ': 24, 'SK': 24, 'UA': 29,
    'GB': 22, 'IE': 22, 'PT': 25, 'GR': 27, 'HU': 28, 'RO': 24,
    'BG': 22, 'HR': 21, 'SI': 19, 'LT': 20, 'LV': 21, 'EE': 20,
    'LU': 20, 'MT': 31, 'CY': 28, 'DK': 18, 'SE': 24, 'FI': 18,
    'NO': 15, 'LI': 21, 'MC': 27, 'SM': 27, 'AD': 24, 'BA': 20,
    'RS': 22, 'ME': 22, 'MK': 19, 'AL': 28, 'MD': 24, 'GE': 22,
}


def validate_iban(iban: str) -> tuple[bool, str]:
    """
    Повна валідація IBAN за стандартом ISO 13616.
    
    Перевірки:
    1. Формат: 2 літери (країна) + 2 цифри (контрольні) + до 30 алфанумеричних символів
    2. Довжина відповідно до країни
    3. Контрольна сума (MOD-97 алгоритм)
    
    Args:
        iban: IBAN для валідації (з пробілами або без)
    
    Returns:
        Tuple (is_valid: bool, error_message: str)
        Якщо valid - error_message порожній
    
    Examples:
        >>> validate_iban("DE89370400440532013000")
        (True, "")
        >>> validate_iban("DE00370400440532013000")
        (False, "Invalid IBAN checksum")
    """
    if not iban:
        return False, "IBAN is empty"
    
    # Очистка: видаляємо пробіли та переводимо у верхній регістр
    iban_clean = iban.replace(' ', '').replace('-', '').upper()
    
    # 1. Перевірка базового формату
    if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]+$', iban_clean):
        return False, f"Invalid IBAN format: must start with 2 letters + 2 digits"
    
    # 2. Отримуємо код країни
    country_code = iban_clean[:2]
    
    # 3. Перевірка довжини по країні
    if country_code in IBAN_LENGTHS:
        expected_length = IBAN_LENGTHS[country_code]
        if len(iban_clean) != expected_length:
            return False, f"Invalid IBAN length for {country_code}: expected {expected_length}, got {len(iban_clean)}"
    elif len(iban_clean) < 15 or len(iban_clean) > 34:
        return False, f"Invalid IBAN length: {len(iban_clean)} (expected 15-34)"
    
    # 4. Перевірка контрольної суми (MOD-97 алгоритм)
    # Переміщуємо перші 4 символи в кінець
    rearranged = iban_clean[4:] + iban_clean[:4]
    
    # Конвертуємо літери в числа (A=10, B=11, ..., Z=35)
    numeric_string = ''
    for char in rearranged:
        if char.isalpha():
            numeric_string += str(ord(char) - ord('A') + 10)
        else:
            numeric_string += char
    
    # Перевірка MOD 97
    try:
        remainder = int(numeric_string) % 97
        if remainder != 1:
            return False, f"Invalid IBAN checksum (MOD-97 check failed)"
    except ValueError:
        return False, f"Invalid IBAN format: contains non-numeric characters"
    
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    """
    Валідація email адреси за стандартом RFC 5322 (спрощена версія).
    
    Перевірки:
    1. Наявність @ та доменної частини
    2. Коректний формат локальної частини
    3. Коректний формат домену (мінімум 2 символи TLD)
    4. Відсутність недозволених символів
    
    Args:
        email: Email для валідації
    
    Returns:
        Tuple (is_valid: bool, error_message: str)
    
    Examples:
        >>> validate_email("user@example.com")
        (True, "")
        >>> validate_email("invalid-email")
        (False, "Email must contain @")
    """
    if not email:
        return False, "Email is empty"
    
    email_clean = email.strip().lower()
    
    # 1. Перевірка наявності @
    if '@' not in email_clean:
        return False, "Email must contain @"
    
    # 2. Розділяємо на локальну та доменну частини
    parts = email_clean.split('@')
    if len(parts) != 2:
        return False, "Email must contain exactly one @"
    
    local_part, domain_part = parts
    
    # 3. Перевірка локальної частини
    if not local_part:
        return False, "Email local part (before @) is empty"
    
    if len(local_part) > 64:
        return False, "Email local part too long (max 64 characters)"
    
    # Дозволені символи: букви, цифри, крапки, дефіси, підкреслення, плюси
    if not re.match(r'^[a-zA-Z0-9._%+\-]+$', local_part):
        return False, "Email local part contains invalid characters"
    
    # Не може починатись/закінчуватись крапкою
    if local_part.startswith('.') or local_part.endswith('.'):
        return False, "Email local part cannot start or end with a dot"
    
    # Не може містити подвійних крапок
    if '..' in local_part:
        return False, "Email local part cannot contain consecutive dots"
    
    # 4. Перевірка доменної частини
    if not domain_part:
        return False, "Email domain part (after @) is empty"
    
    if len(domain_part) > 253:
        return False, "Email domain too long (max 253 characters)"
    
    # Домен повинен містити крапку
    if '.' not in domain_part:
        return False, "Email domain must contain at least one dot"
    
    # Перевірка формату домену
    domain_regex = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
    if not re.match(domain_regex, domain_part):
        return False, "Invalid email domain format"
    
    # TLD повинен бути мінімум 2 символи
    tld = domain_part.split('.')[-1]
    if len(tld) < 2:
        return False, "Email TLD must be at least 2 characters"
    
    return True, ""


def validate_german_postal_code(postal_code: str) -> tuple[bool, str]:
    """
    Валідація німецького поштового індексу (PLZ).
    
    Правила:
    - Рівно 5 цифр
    - Діапазон 01000-99999
    - Деякі діапазони не використовуються
    
    Args:
        postal_code: Поштовий індекс
    
    Returns:
        Tuple (is_valid: bool, error_message: str)
    """
    if not postal_code:
        return False, "Postal code is empty"
    
    # Очистка
    plz_clean = re.sub(r'\D', '', postal_code)
    
    if len(plz_clean) != 5:
        return False, f"German postal code must have exactly 5 digits, got {len(plz_clean)}"
    
    # Перевірка діапазону
    plz_int = int(plz_clean)
    if plz_int < 1000:  # 01000 - найменший
        return False, f"Invalid postal code: {plz_clean} (too low)"
    
    if plz_int > 99999:
        return False, f"Invalid postal code: {plz_clean} (too high)"
    
    return True, ""


def validate_phone_number(phone: str, country: str = 'DE') -> tuple[bool, str]:
    """
    Валідація номера телефону.
    
    Підтримує формати:
    - Німеччина: +49, 0049, 0...
    - Міжнародний: +XX...
    
    Args:
        phone: Номер телефону
        country: Код країни (DE за замовчуванням)
    
    Returns:
        Tuple (is_valid: bool, error_message: str)
    """
    if not phone:
        return False, "Phone number is empty"
    
    # Очистка - залишаємо тільки цифри та +
    phone_clean = re.sub(r'[^\d+]', '', phone)
    
    # Мінімальна довжина (включаючи код країни)
    if len(phone_clean) < 8:
        return False, f"Phone number too short: {len(phone_clean)} digits"
    
    if len(phone_clean) > 15:
        return False, f"Phone number too long: {len(phone_clean)} digits"
    
    # Перевірка формату
    if phone_clean.startswith('+'):
        # Міжнародний формат
        if not re.match(r'^\+\d{8,14}$', phone_clean):
            return False, "Invalid international phone format"
    elif phone_clean.startswith('00'):
        # Міжнародний формат з 00
        if not re.match(r'^00\d{8,14}$', phone_clean):
            return False, "Invalid international phone format (00...)"
    elif phone_clean.startswith('0'):
        # Національний формат (Німеччина)
        if country == 'DE' and not re.match(r'^0\d{7,14}$', phone_clean):
            return False, "Invalid German phone format"
    else:
        return False, "Phone number must start with + or 0"
    
    return True, ""


def validate_for_german_docs(user_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Комплексна валідація даних для німецьких документів.
    
    Перевірки:
    - IBAN (повна валідація з контрольною сумою)
    - Email (RFC 5322)
    - Поштовий індекс (5 цифр)
    - Телефон (опціонально)
    - Відсутність кирилиці
    
    Returns:
        Словник з помилками {field: error_message}
        Порожній словник = всі дані валідні
    """
    errors = {}
    
    # 1. Перевірка кирилиці у всіх полях
    for key, value in user_data.items():
        if isinstance(value, str) and has_cyrillic(value):
            errors[key] = f"Contains Cyrillic characters (transliteration required): '{value}'"
    
    # 2. Валідація IBAN
    iban = user_data.get('iban', '')
    if iban:
        is_valid, error_msg = validate_iban(iban)
        if not is_valid:
            errors['iban'] = error_msg
    
    # 3. Валідація Email
    email = user_data.get('email', '')
    if email:
        is_valid, error_msg = validate_email(email)
        if not is_valid:
            errors['email'] = error_msg
    
    # 4. Валідація поштового індексу
    postal = user_data.get('postal_code', user_data.get('zip_code', user_data.get('plz', '')))
    if postal:
        is_valid, error_msg = validate_german_postal_code(postal)
        if not is_valid:
            errors['postal_code'] = error_msg
    
    # 5. Валідація телефону (якщо є)
    phone = user_data.get('phone', user_data.get('mobile', user_data.get('telefon', '')))
    if phone:
        is_valid, error_msg = validate_phone_number(phone)
        if not is_valid:
            errors['phone'] = error_msg
    
    return errors


def validate_all_fields(user_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Детальна валідація всіх полів з результатами.
    
    Returns:
        Словник {field: {valid: bool, value: str, error: str|None}}
    """
    results = {}
    
    for key, value in user_data.items():
        if not isinstance(value, str):
            results[key] = {'valid': True, 'value': value, 'error': None}
            continue
        
        result = {'valid': True, 'value': value, 'error': None}
        
        # Спеціальні валідації
        if key == 'iban':
            is_valid, error = validate_iban(value)
            result['valid'] = is_valid
            result['error'] = error if not is_valid else None
        elif key == 'email':
            is_valid, error = validate_email(value)
            result['valid'] = is_valid
            result['error'] = error if not is_valid else None
        elif key in ('postal_code', 'zip_code', 'plz'):
            is_valid, error = validate_german_postal_code(value)
            result['valid'] = is_valid
            result['error'] = error if not is_valid else None
        elif key in ('phone', 'mobile', 'telefon'):
            is_valid, error = validate_phone_number(value)
            result['valid'] = is_valid
            result['error'] = error if not is_valid else None
        elif has_cyrillic(value):
            result['valid'] = False
            result['error'] = "Contains Cyrillic characters"
        
        results[key] = result
    
    return results


# ============================================================================
# ТЕСТУВАННЯ
# ============================================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("DATA PROCESSOR & VALIDATION TEST")
    print("=" * 70)
    
    # ========================================
    # TEST 1: IBAN Validation
    # ========================================
    print("\n" + "=" * 70)
    print("1. IBAN VALIDATION")
    print("=" * 70)
    
    test_ibans = [
        ("DE89370400440532013000", True, "Valid German IBAN"),
        ("DE89 3704 0044 0532 0130 00", True, "Valid German IBAN with spaces"),
        ("AT611904300234573201", True, "Valid Austrian IBAN"),
        ("FR7630006000011234567890189", True, "Valid French IBAN"),
        ("CH9300762011623852957", True, "Valid Swiss IBAN"),
        ("DE00370400440532013000", False, "Invalid checksum"),
        ("DE8937040044053201300", False, "Wrong length for DE"),
        ("XX89370400440532013000", False, "Unknown country code"),
        ("12345678901234567890", False, "No country code"),
        ("", False, "Empty IBAN"),
    ]
    
    for iban, expected_valid, description in test_ibans:
        is_valid, error = validate_iban(iban)
        status = "✅" if is_valid == expected_valid else "❌"
        result = "VALID" if is_valid else f"INVALID: {error}"
        print(f"  {status} {description}")
        print(f"     IBAN: {iban or '(empty)'}")
        print(f"     Result: {result}")
    
    # ========================================
    # TEST 2: Email Validation
    # ========================================
    print("\n" + "=" * 70)
    print("2. EMAIL VALIDATION")
    print("=" * 70)
    
    test_emails = [
        ("user@example.com", True, "Standard email"),
        ("user.name@example.com", True, "Email with dot"),
        ("user+tag@example.com", True, "Email with plus"),
        ("user@subdomain.example.com", True, "Email with subdomain"),
        ("user@example.de", True, "German TLD"),
        ("USER@EXAMPLE.COM", True, "Uppercase email"),
        ("invalid-email", False, "No @ symbol"),
        ("user@", False, "No domain"),
        ("@example.com", False, "No local part"),
        ("user@@example.com", False, "Double @"),
        ("user@example", False, "No TLD"),
        ("user..name@example.com", False, "Double dots"),
        (".user@example.com", False, "Starts with dot"),
        ("user.@example.com", False, "Ends with dot"),
        ("", False, "Empty email"),
    ]
    
    for email, expected_valid, description in test_emails:
        is_valid, error = validate_email(email)
        status = "✅" if is_valid == expected_valid else "❌"
        result = "VALID" if is_valid else f"INVALID: {error}"
        print(f"  {status} {description}")
        print(f"     Email: {email or '(empty)'}")
        print(f"     Result: {result}")
    
    # ========================================
    # TEST 3: Full Data Processing
    # ========================================
    print("\n" + "=" * 70)
    print("3. FULL DATA PROCESSING")
    print("=" * 70)
    
    test_data = {
        'first_name': '  віталій  ',
        'last_name': 'Шевченко',
        'birth_place': 'київ',
        'city': ' münchen ',
        'address': 'вулиця тараса шевченка 15',
        'postal_code': '10115',
        'phone': '+49 30 123456789',
        'email': 'vitalii.shevchenko@example.de',
        'iban': 'DE89 3704 0044 0532 0130 00',
        'bic': 'cobadeffxxx',
        'birth_date': '1990-05-15',
        'child_name': 'марія-анна',
    }
    
    print("\nOriginal data:")
    for k, v in test_data.items():
        print(f"  {k}: '{v}'")
    
    processed = process_user_data(test_data, log_changes=True)
    
    print("\nProcessed data:")
    for k, v in processed.items():
        print(f"  {k}: '{v}'")
    
    # ========================================
    # TEST 4: Validation Results
    # ========================================
    print("\n" + "=" * 70)
    print("4. VALIDATION RESULTS")
    print("=" * 70)
    
    errors = validate_for_german_docs(processed)
    if errors:
        print("\n❌ Validation errors:")
        for field, error in errors.items():
            print(f"  - {field}: {error}")
    else:
        print("\n✅ All fields valid for German documents!")
    
    # Test with invalid data
    print("\nTesting with invalid data:")
    invalid_data = {
        'email': 'invalid-email',
        'iban': 'DE00000000000000000000',
        'postal_code': '123',
        'phone': '123',
        'first_name': 'Іван',  # Cyrillic
    }
    
    errors = validate_for_german_docs(invalid_data)
    for field, error in errors.items():
        print(f"  ❌ {field}: {error}")
    
    print("\n" + "=" * 70)
    print("TESTS COMPLETE")
    print("=" * 70)