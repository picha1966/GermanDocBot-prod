# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v4.5 - RTL (Right-to-Left) Fix for Arabic PDF

Утиліта для коректного відображення арабського тексту в PDF документах.
Автоматично "дзеркалить" текст перед вставкою в PDF.

ВИКОРИСТАННЯ:
    from rtl_fix import prepare_rtl_text, is_rtl_language, RTLTextProcessor
    
    # Простий спосіб
    text = prepare_rtl_text("مرحبا بالعالم")  # Готовий для PDF
    
    # Або через клас
    processor = RTLTextProcessor()
    pdf_text = processor.process("مرحبا بالعالم")
"""

import re
from typing import Optional, List, Tuple


# ============================================================================
# RTL CHARACTER DETECTION
# ============================================================================

# Діапазони Unicode для RTL мов
RTL_RANGES = [
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
    (0x0590, 0x05FF),  # Hebrew
    (0xFB1D, 0xFB4F),  # Hebrew Presentation Forms
]

# RTL мови (код мови -> назва)
RTL_LANGUAGES = {
    'ar': 'Arabic',
    'he': 'Hebrew',
    'fa': 'Persian',
    'ur': 'Urdu',
}


def is_rtl_char(char: str) -> bool:
    """
    Перевірити чи символ є RTL
    
    Args:
        char: Один символ
        
    Returns:
        True якщо символ RTL
    """
    if not char:
        return False
    
    code = ord(char)
    for start, end in RTL_RANGES:
        if start <= code <= end:
            return True
    return False


def is_rtl_text(text: str) -> bool:
    """
    Перевірити чи текст містить RTL символи
    
    Args:
        text: Текст для перевірки
        
    Returns:
        True якщо текст містить RTL символи
    """
    if not text:
        return False
    
    for char in text:
        if is_rtl_char(char):
            return True
    return False


def is_rtl_language(lang_code: str) -> bool:
    """
    Перевірити чи мова є RTL
    
    Args:
        lang_code: Код мови (ar, he, fa, ur)
        
    Returns:
        True якщо мова RTL
    """
    return lang_code.lower() in RTL_LANGUAGES


# ============================================================================
# RTL TEXT PROCESSOR
# ============================================================================

class RTLTextProcessor:
    """
    Процесор для підготовки RTL тексту до вставки в PDF
    
    ReportLab та інші PDF бібліотеки не підтримують RTL "з коробки".
    Цей клас виконує необхідні трансформації:
    1. Реверс порядку символів (дзеркалення)
    2. Корекція зв'язаних форм арабських літер
    3. Обробка змішаного тексту (RTL + LTR)
    """
    
    def __init__(self, use_reshaping: bool = True):
        """
        Args:
            use_reshaping: Використовувати reshaping для арабського тексту
                          (потребує бібліотеку arabic-reshaper)
        """
        self.use_reshaping = use_reshaping
        self._reshaper = None
        self._bidi = None
        
        # Спробуємо імпортувати бібліотеки
        self._init_libraries()
    
    def _init_libraries(self):
        """Ініціалізація зовнішніх бібліотек (якщо доступні)"""
        try:
            import arabic_reshaper
            self._reshaper = arabic_reshaper
        except ImportError:
            self._reshaper = None
        
        try:
            from bidi.algorithm import get_display
            self._bidi = get_display
        except ImportError:
            self._bidi = None
    
    def process(self, text: str, force_rtl: bool = False) -> str:
        """
        Обробити текст для PDF
        
        Args:
            text: Вхідний текст
            force_rtl: Примусово обробити як RTL
            
        Returns:
            Текст готовий для вставки в PDF
        """
        if not text:
            return text
        
        # Якщо текст не RTL і не примусово - повертаємо як є
        if not force_rtl and not is_rtl_text(text):
            return text
        
        # Спочатку спробуємо використати бібліотеки
        if self._reshaper and self._bidi:
            return self._process_with_libraries(text)
        
        # Fallback: просте дзеркалення
        return self._simple_mirror(text)
    
    def _process_with_libraries(self, text: str) -> str:
        """
        Обробка з використанням arabic-reshaper та python-bidi
        Найкращий результат для арабського тексту
        """
        try:
            # Reshape - з'єднує літери правильно
            reshaped = self._reshaper.reshape(text)
            # Bidi - коректний порядок для відображення
            display = self._bidi(reshaped)
            return display
        except Exception:
            return self._simple_mirror(text)
    
    def _simple_mirror(self, text: str) -> str:
        """
        Просте дзеркалення тексту (fallback)
        
        Обробляє рядок по частинах:
        - RTL частини - дзеркаляться
        - LTR частини (числа, латиниця) - залишаються
        """
        if not text:
            return text
        
        # Розбиваємо на сегменти RTL та LTR
        segments = self._split_by_direction(text)
        
        # Обробляємо кожен сегмент
        processed = []
        for segment, is_rtl in segments:
            if is_rtl:
                # Дзеркалимо RTL сегмент
                processed.append(segment[::-1])
            else:
                # LTR залишаємо
                processed.append(segment)
        
        # Для RTL тексту - реверсуємо порядок сегментів
        if segments and segments[0][1]:  # Якщо перший сегмент RTL
            processed.reverse()
        
        return ''.join(processed)
    
    def _split_by_direction(self, text: str) -> List[Tuple[str, bool]]:
        """
        Розбити текст на сегменти за напрямком
        
        Returns:
            Список кортежів (сегмент, is_rtl)
        """
        if not text:
            return []
        
        segments = []
        current_segment = ""
        current_is_rtl = None
        
        for char in text:
            char_is_rtl = is_rtl_char(char)
            
            # Пробіли та пунктуація - нейтральні, додаємо до поточного
            if char.isspace() or char in '.,;:!?()-':
                current_segment += char
                continue
            
            if current_is_rtl is None:
                current_is_rtl = char_is_rtl
            
            if char_is_rtl == current_is_rtl:
                current_segment += char
            else:
                # Зберігаємо поточний сегмент
                if current_segment:
                    segments.append((current_segment, current_is_rtl))
                # Починаємо новий
                current_segment = char
                current_is_rtl = char_is_rtl
        
        # Додаємо останній сегмент
        if current_segment:
            segments.append((current_segment, current_is_rtl or False))
        
        return segments
    
    def process_multiline(self, text: str) -> str:
        """
        Обробити багаторядковий текст
        
        Args:
            text: Текст з переносами рядків
            
        Returns:
            Оброблений текст
        """
        if not text:
            return text
        
        lines = text.split('\n')
        processed_lines = [self.process(line) for line in lines]
        return '\n'.join(processed_lines)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

# Глобальний екземпляр процесора
_default_processor = RTLTextProcessor()


def prepare_rtl_text(text: str, force: bool = False) -> str:
    """
    Підготувати RTL текст для вставки в PDF
    
    Це головна функція яку слід використовувати!
    
    Args:
        text: Вхідний текст (може бути арабською, івритом тощо)
        force: Примусово обробити як RTL
        
    Returns:
        Текст готовий для PDF
        
    Приклад:
        >>> text = prepare_rtl_text("مرحبا بالعالم")
        >>> canvas.drawString(100, 700, text)
    """
    return _default_processor.process(text, force_rtl=force)


def prepare_rtl_multiline(text: str) -> str:
    """
    Підготувати багаторядковий RTL текст
    
    Args:
        text: Текст з переносами рядків
        
    Returns:
        Оброблений текст
    """
    return _default_processor.process_multiline(text)


def format_for_pdf(text: str, lang: str) -> str:
    """
    Форматувати текст для PDF з урахуванням мови
    
    Args:
        text: Вхідний текст
        lang: Код мови ('ar', 'de', 'ua', etc.)
        
    Returns:
        Текст готовий для PDF
    """
    if is_rtl_language(lang):
        return prepare_rtl_text(text, force=True)
    return text


# ============================================================================
# PDF HELPER FUNCTIONS
# ============================================================================

def draw_rtl_string(canvas, x: float, y: float, text: str, lang: str = 'ar'):
    """
    Намалювати RTL текст на canvas
    
    Автоматично обробляє текст та малює справа наліво
    
    Args:
        canvas: ReportLab canvas об'єкт
        x: X координата (права межа тексту)
        y: Y координата
        text: Текст для відображення
        lang: Код мови
    """
    processed = format_for_pdf(text, lang)
    
    if is_rtl_language(lang):
        # Для RTL - x це права межа, малюємо справа
        canvas.drawRightString(x, y, processed)
    else:
        canvas.drawString(x, y, processed)


def get_rtl_text_width(canvas, text: str, font_name: str, font_size: int) -> float:
    """
    Отримати ширину RTL тексту
    
    Args:
        canvas: ReportLab canvas
        text: Текст
        font_name: Назва шрифту
        font_size: Розмір шрифту
        
    Returns:
        Ширина тексту в points
    """
    processed = prepare_rtl_text(text)
    return canvas.stringWidth(processed, font_name, font_size)


# ============================================================================
# ARABIC SPECIFIC HELPERS
# ============================================================================

# Арабські цифри
ARABIC_NUMERALS = {
    '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
    '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
}

WESTERN_NUMERALS = {v: k for k, v in ARABIC_NUMERALS.items()}


def convert_to_arabic_numerals(text: str) -> str:
    """
    Конвертувати західні цифри в арабські
    
    Args:
        text: Текст з цифрами
        
    Returns:
        Текст з арабськими цифрами
    """
    for western, arabic in ARABIC_NUMERALS.items():
        text = text.replace(western, arabic)
    return text


def convert_to_western_numerals(text: str) -> str:
    """
    Конвертувати арабські цифри в західні
    
    Args:
        text: Текст з арабськими цифрами
        
    Returns:
        Текст з західними цифрами
    """
    for arabic, western in WESTERN_NUMERALS.items():
        text = text.replace(arabic, western)
    return text


def format_arabic_date(day: int, month: int, year: int) -> str:
    """
    Форматувати дату арабською
    
    Args:
        day: День
        month: Місяць
        year: Рік
        
    Returns:
        Форматована дата
    """
    date_str = f"{day:02d}.{month:02d}.{year}"
    return convert_to_arabic_numerals(date_str)


# ============================================================================
# INSTALLATION HELPER
# ============================================================================

def check_rtl_support() -> dict:
    """
    Перевірити підтримку RTL бібліотек
    
    Returns:
        Словник з інформацією про доступні бібліотеки
    """
    result = {
        'arabic_reshaper': False,
        'python_bidi': False,
        'full_support': False,
        'recommendation': None
    }
    
    try:
        import arabic_reshaper
        result['arabic_reshaper'] = True
    except ImportError:
        pass
    
    try:
        from bidi.algorithm import get_display
        result['python_bidi'] = True
    except ImportError:
        pass
    
    result['full_support'] = result['arabic_reshaper'] and result['python_bidi']
    
    if not result['full_support']:
        missing = []
        if not result['arabic_reshaper']:
            missing.append('arabic-reshaper')
        if not result['python_bidi']:
            missing.append('python-bidi')
        
        result['recommendation'] = f"pip install {' '.join(missing)}"
    
    return result


if __name__ == '__main__':
    # Тест
    print("RTL Support Check:")
    support = check_rtl_support()
    for key, value in support.items():
        print(f"  {key}: {value}")
    
    print("\nTest RTL processing:")
    test_text = "مرحبا بالعالم"
    print(f"  Input: {test_text}")
    print(f"  Is RTL: {is_rtl_text(test_text)}")
    print(f"  Processed: {prepare_rtl_text(test_text)}")
