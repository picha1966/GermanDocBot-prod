# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT — backend/rtl_support.py

⚠️  DEPRECATED — NOT USED BY THE PDF PIPELINE.

The canonical RTL engine is in backend/pdf_generator.py:
    _prepare_text_for_pdf(text, lang="ar")
      → arabic_reshaper.reshape(text)
      → bidi.algorithm.get_display(reshaped)
    Font: NotoSansArabic (registered via _register_arabic_font_for_reportlab)

This file contains a manual Arabic letter-shaping implementation (PDFRTLHelper)
that predates the arabic_reshaper / python-bidi library integration.
It is NOT imported by pdf_generator.py or german_form_builder.py.

DO NOT use reshape_arabic_text() or PDFRTLHelper from this file in new code.
Use _prepare_text_for_pdf() from pdf_generator instead.

This file is kept for historical reference only.
"""

import re
from typing import Tuple, Optional
from enum import Enum


# ============================================================================
# ARABIC CHARACTER MAPS
# ============================================================================

# Арабські літери та їх форми (isolated, initial, medial, final)
ARABIC_LETTERS = {
    # Letter: (isolated, initial, medial, final)
    'ا': ('ا', 'ا', 'ـا', 'ـا'),  # Alef
    'ب': ('ب', 'بـ', 'ـبـ', 'ـب'),  # Ba
    'ت': ('ت', 'تـ', 'ـتـ', 'ـت'),  # Ta
    'ث': ('ث', 'ثـ', 'ـثـ', 'ـث'),  # Tha
    'ج': ('ج', 'جـ', 'ـجـ', 'ـج'),  # Jim
    'ح': ('ح', 'حـ', 'ـحـ', 'ـح'),  # Ha
    'خ': ('خ', 'خـ', 'ـخـ', 'ـخ'),  # Kha
    'د': ('د', 'د', 'ـد', 'ـد'),   # Dal
    'ذ': ('ذ', 'ذ', 'ـذ', 'ـذ'),   # Dhal
    'ر': ('ر', 'ر', 'ـر', 'ـر'),   # Ra
    'ز': ('ز', 'ز', 'ـز', 'ـز'),   # Zay
    'س': ('س', 'سـ', 'ـسـ', 'ـس'),  # Sin
    'ش': ('ش', 'شـ', 'ـشـ', 'ـش'),  # Shin
    'ص': ('ص', 'صـ', 'ـصـ', 'ـص'),  # Sad
    'ض': ('ض', 'ضـ', 'ـضـ', 'ـض'),  # Dad
    'ط': ('ط', 'طـ', 'ـطـ', 'ـط'),  # Ta
    'ظ': ('ظ', 'ظـ', 'ـظـ', 'ـظ'),  # Za
    'ع': ('ع', 'عـ', 'ـعـ', 'ـع'),  # Ain
    'غ': ('غ', 'غـ', 'ـغـ', 'ـغ'),  # Ghain
    'ف': ('ف', 'فـ', 'ـفـ', 'ـف'),  # Fa
    'ق': ('ق', 'قـ', 'ـقـ', 'ـق'),  # Qaf
    'ك': ('ك', 'كـ', 'ـكـ', 'ـك'),  # Kaf
    'ل': ('ل', 'لـ', 'ـلـ', 'ـل'),  # Lam
    'م': ('م', 'مـ', 'ـمـ', 'ـم'),  # Mim
    'ن': ('ن', 'نـ', 'ـنـ', 'ـن'),  # Nun
    'ه': ('ه', 'هـ', 'ـهـ', 'ـه'),  # Ha
    'و': ('و', 'و', 'ـو', 'ـو'),   # Waw
    'ي': ('ي', 'يـ', 'ـيـ', 'ـي'),  # Ya
    'ى': ('ى', 'ى', 'ـى', 'ـى'),   # Alef Maksura
    'ة': ('ة', 'ة', 'ـة', 'ـة'),   # Ta Marbuta
    'ء': ('ء', 'ء', 'ء', 'ء'),     # Hamza
    'أ': ('أ', 'أ', 'ـأ', 'ـأ'),   # Alef with Hamza Above
    'إ': ('إ', 'إ', 'ـإ', 'ـإ'),   # Alef with Hamza Below
    'آ': ('آ', 'آ', 'ـآ', 'ـآ'),   # Alef with Madda
    'ؤ': ('ؤ', 'ؤ', 'ـؤ', 'ـؤ'),   # Waw with Hamza
    'ئ': ('ئ', 'ئـ', 'ـئـ', 'ـئ'),  # Ya with Hamza
}

# Літери, що не з'єднуються з наступною
NON_JOINING_LETTERS = {'ا', 'أ', 'إ', 'آ', 'د', 'ذ', 'ر', 'ز', 'و', 'ؤ'}

# Арабські цифри
ARABIC_DIGITS = {
    '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
    '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
}


class TextDirection(Enum):
    """Напрямок тексту"""
    LTR = "ltr"  # Left to Right
    RTL = "rtl"  # Right to Left
    AUTO = "auto"


# ============================================================================
# RTL UTILITY FUNCTIONS
# ============================================================================

def is_arabic_char(char: str) -> bool:
    """Перевірити чи символ арабський"""
    if not char:
        return False
    code = ord(char)
    return (
        0x0600 <= code <= 0x06FF or  # Arabic
        0x0750 <= code <= 0x077F or  # Arabic Supplement
        0x08A0 <= code <= 0x08FF or  # Arabic Extended-A
        0xFB50 <= code <= 0xFDFF or  # Arabic Presentation Forms-A
        0xFE70 <= code <= 0xFEFF     # Arabic Presentation Forms-B
    )


def is_rtl_text(text: str) -> bool:
    """Перевірити чи текст RTL (арабський/іврит)"""
    if not text:
        return False
    
    for char in text:
        if is_arabic_char(char):
            return True
        # Іврит
        if 0x0590 <= ord(char) <= 0x05FF:
            return True
    
    return False


def detect_text_direction(text: str) -> TextDirection:
    """Визначити напрямок тексту"""
    if not text:
        return TextDirection.LTR
    
    # Підраховуємо RTL та LTR символи
    rtl_count = 0
    ltr_count = 0
    
    for char in text:
        code = ord(char)
        if is_arabic_char(char) or (0x0590 <= code <= 0x05FF):
            rtl_count += 1
        elif char.isalpha():
            ltr_count += 1
    
    if rtl_count > ltr_count:
        return TextDirection.RTL
    elif ltr_count > rtl_count:
        return TextDirection.LTR
    else:
        return TextDirection.AUTO


def reverse_string(text: str) -> str:
    """Перевернути рядок (для RTL відображення)"""
    return text[::-1]


def mirror_text_for_pdf(text: str) -> str:
    """
    Підготувати текст для PDF (mirror для RTL)
    
    Для арабського тексту в PDF потрібно:
    1. Перевернути порядок символів
    2. Зберегти числа та латиницю в правильному порядку
    """
    if not text or not is_rtl_text(text):
        return text
    
    result = []
    current_segment = []
    current_is_rtl = None
    
    for char in text:
        char_is_rtl = is_arabic_char(char)
        
        if current_is_rtl is None:
            current_is_rtl = char_is_rtl
        
        if char_is_rtl == current_is_rtl or char in ' \t\n':
            current_segment.append(char)
        else:
            # Зберігаємо сегмент
            segment_text = ''.join(current_segment)
            if current_is_rtl:
                segment_text = reverse_string(segment_text)
            result.append(segment_text)
            
            current_segment = [char]
            current_is_rtl = char_is_rtl
    
    # Останній сегмент
    if current_segment:
        segment_text = ''.join(current_segment)
        if current_is_rtl:
            segment_text = reverse_string(segment_text)
        result.append(segment_text)
    
    # Для RTL тексту перевертаємо весь результат
    return ''.join(reversed(result))


def reshape_arabic_text(text: str) -> str:
    """
    Reshape арабського тексту (з'єднання літер)
    
    Арабські літери мають різні форми залежно від позиції в слові:
    - Isolated (окремо)
    - Initial (на початку)
    - Medial (посередині)
    - Final (в кінці)
    """
    if not text:
        return text
    
    result = []
    i = 0
    
    while i < len(text):
        char = text[i]
        
        if char not in ARABIC_LETTERS:
            result.append(char)
            i += 1
            continue
        
        # Визначаємо позицію літери
        prev_char = text[i-1] if i > 0 else None
        next_char = text[i+1] if i < len(text) - 1 else None
        
        prev_joins = prev_char and prev_char in ARABIC_LETTERS and prev_char not in NON_JOINING_LETTERS
        next_joins = next_char and next_char in ARABIC_LETTERS
        
        forms = ARABIC_LETTERS.get(char, (char, char, char, char))
        
        if not prev_joins and not next_joins:
            # Isolated
            result.append(forms[0])
        elif not prev_joins and next_joins:
            # Initial
            result.append(forms[1])
        elif prev_joins and next_joins:
            # Medial
            result.append(forms[2])
        else:
            # Final
            result.append(forms[3])
        
        i += 1
    
    return ''.join(result)


def convert_to_arabic_digits(text: str) -> str:
    """Конвертувати західні цифри в арабські"""
    result = []
    for char in text:
        result.append(ARABIC_DIGITS.get(char, char))
    return ''.join(result)


def convert_from_arabic_digits(text: str) -> str:
    """Конвертувати арабські цифри в західні"""
    reverse_map = {v: k for k, v in ARABIC_DIGITS.items()}
    result = []
    for char in text:
        result.append(reverse_map.get(char, char))
    return ''.join(result)


# ============================================================================
# PDF RTL HELPERS
# ============================================================================

class PDFRTLHelper:
    """
    Хелпер для RTL тексту в PDF
    
    Використання:
        rtl = PDFRTLHelper()
        
        # Підготувати текст для PDF
        text = rtl.prepare_text("مرحبا")
        
        # Отримати вирівнювання
        align = rtl.get_alignment("مرحبا", default="left")
        
        # Отримати позицію X для RTL
        x = rtl.get_x_position("مرحبا", page_width=595, margin=50)
    """
    
    def __init__(self, use_reshaping: bool = True, mirror_text: bool = True):
        """
        Args:
            use_reshaping: Чи використовувати reshaping арабських літер
            mirror_text: Чи перевертати текст для PDF
        """
        self.use_reshaping = use_reshaping
        self.mirror_text = mirror_text
    
    def prepare_text(self, text: str, lang: str = None) -> str:
        """
        Підготувати текст для PDF
        
        Args:
            text: Вхідний текст
            lang: Код мови (опціонально)
            
        Returns:
            Підготовлений текст
        """
        if not text:
            return text
        
        # Перевіряємо чи потрібна RTL обробка
        if lang == 'ar' or is_rtl_text(text):
            # Reshaping
            if self.use_reshaping:
                text = reshape_arabic_text(text)
            
            # Mirror для PDF
            if self.mirror_text:
                text = mirror_text_for_pdf(text)
        
        return text
    
    def get_alignment(self, text: str, default: str = "left") -> str:
        """
        Отримати вирівнювання для тексту
        
        Args:
            text: Текст
            default: Вирівнювання за замовчуванням
            
        Returns:
            "left", "right", або "center"
        """
        if is_rtl_text(text):
            return "right"
        return default
    
    def get_x_position(
        self,
        text: str,
        page_width: float,
        margin: float,
        text_width: float = None,
        alignment: str = "auto"
    ) -> float:
        """
        Обчислити X позицію для тексту
        
        Args:
            text: Текст
            page_width: Ширина сторінки
            margin: Відступ
            text_width: Ширина тексту (якщо відома)
            alignment: Вирівнювання ("auto", "left", "right", "center")
            
        Returns:
            X координата
        """
        if alignment == "auto":
            alignment = self.get_alignment(text)
        
        usable_width = page_width - 2 * margin
        
        if alignment == "right":
            if text_width:
                return page_width - margin - text_width
            return page_width - margin
        elif alignment == "center":
            if text_width:
                return margin + (usable_width - text_width) / 2
            return page_width / 2
        else:  # left
            return margin
    
    def adjust_padding(
        self,
        text: str,
        left_padding: float,
        right_padding: float
    ) -> Tuple[float, float]:
        """
        Адаптувати padding для RTL тексту
        
        Args:
            text: Текст
            left_padding: Лівий відступ
            right_padding: Правий відступ
            
        Returns:
            Tuple[adjusted_left, adjusted_right]
        """
        if is_rtl_text(text):
            # Міняємо місцями для RTL
            return right_padding, left_padding
        return left_padding, right_padding
    
    def wrap_with_rtl_markers(self, text: str) -> str:
        """
        Обгорнути текст RTL маркерами Unicode
        
        Args:
            text: Текст
            
        Returns:
            Текст з RTL маркерами
        """
        if is_rtl_text(text):
            # RLM (Right-to-Left Mark) та LRM (Left-to-Right Mark)
            RLM = '\u200F'
            return f"{RLM}{text}{RLM}"
        return text
    
    def prepare_mixed_text(self, text: str) -> str:
        """
        Підготувати змішаний текст (арабський + латиниця)
        
        Args:
            text: Змішаний текст
            
        Returns:
            Підготовлений текст з правильним порядком
        """
        if not text:
            return text
        
        # Розбиваємо на сегменти
        segments = []
        current = []
        current_rtl = None
        
        for char in text:
            char_rtl = is_arabic_char(char)
            
            if char in ' \t\n':
                current.append(char)
            elif current_rtl is None or char_rtl == current_rtl:
                current.append(char)
                current_rtl = char_rtl
            else:
                if current:
                    segments.append((''.join(current), current_rtl))
                current = [char]
                current_rtl = char_rtl
        
        if current:
            segments.append((''.join(current), current_rtl))
        
        # Обробляємо кожен сегмент
        result = []
        for segment, is_rtl in segments:
            if is_rtl and self.use_reshaping:
                segment = reshape_arabic_text(segment)
            result.append(segment)
        
        # Визначаємо загальний напрямок
        overall_rtl = any(is_rtl for _, is_rtl in segments)
        
        if overall_rtl:
            result = reversed(result)
        
        return ''.join(result)


# Глобальний екземпляр
rtl_helper = PDFRTLHelper()


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def prepare_arabic_for_pdf(text: str) -> str:
    """Швидка функція для підготовки арабського тексту"""
    return rtl_helper.prepare_text(text, lang='ar')


def get_text_alignment(text: str) -> str:
    """Отримати вирівнювання для тексту"""
    return rtl_helper.get_alignment(text)


def is_rtl(text: str) -> bool:
    """Швидка перевірка RTL"""
    return is_rtl_text(text)
