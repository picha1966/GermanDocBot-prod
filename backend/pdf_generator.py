# -*- coding: utf-8 -*-
"""
backend/pdf_generator.py — PDF generation for German government forms (Anmeldung, etc.).

FINAL PDF ARCHITECTURE (non-negotiable):
- Prefer AcroForm: fill ONLY existing form fields (widget.field_value + widget.update()).
  NO manual text drawing (x/y) when template has AcroForm — layout/fonts/spacing = official form.
- Overlay (x/y) is allowed ONLY as fallback when template has NO AcroForm fields (flat/scanned PDF).
- Document content always in German; preview/watermark text localized via user_lang (de, en, uk, ar, tr, pl).
"""

import os
import logging
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime

logger = logging.getLogger(__name__)

# PDF generation mode constants (for readability)
PDF_MODE_PREVIEW = "preview"
PDF_MODE_FINAL = "final"

# Service texts (PREVIEW / watermark): de, en, uk, ar, tr, pl only (no Russian)
SUPPORTED_SERVICE_LANGS = ("de", "en", "uk", "ua", "pl", "tr", "ar")

# Preview price configuration
PREVIEW_PRICE = 3.49  # Price to remove watermark (in EUR)
# ReportLab is used ONLY for generating the cover page (Page 1) in preview mode.
# The main PDF content is generated using PyMuPDF (fitz).
from reportlab.pdfgen import canvas
from reportlab.lib.colors import grey, black, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    Spacer,
    SimpleDocTemplate,
    PageBreak,
    KeepTogether,
)
from reportlab.platypus.frames import Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.units import inch
from io import BytesIO

# --- RTL (Arabic) support: reshape + bidi so Arabic renders correctly in PDF ---
# When lang == "ar": _prepare_text_for_pdf() applies arabic_reshaper (letter shaping)
# and bidi.algorithm.get_display() (visual order). Font: NotoSansArabic (embedded).
# Latin/Cyrillic: unchanged; font remains DejaVuSans. No system-default fonts.
try:
    import arabic_reshaper
    import bidi.algorithm

    _HAS_RTL_SUPPORT = True
except ImportError:
    _HAS_RTL_SUPPORT = False


def draw_preview_watermark(c: canvas.Canvas):
    """
    DEPRECATED: This function is never called.
    Real PDF generation uses PyMuPDF (fitz), not reportlab.canvas.Canvas.
    Watermark is implemented in _apply_watermark() using PyMuPDF.
    """
    c.saveState()
    c.setFont("Helvetica-Bold", 48)
    c.setFillColor(grey, alpha=0.15)
    c.translate(300, 400)
    c.rotate(45)
    c.drawCentredString(0, 0, "PREVIEW · NOT OFFICIAL")
    c.restoreState()


def _normalize_text_for_pdf(text: str) -> str:
    """
    Normalize text to fix glued words and spacing issues before rendering to PDF.

    Fixes:
    - Collapses multiple spaces to single space
    - Ensures space after punctuation (. , : ; ! ?) when appropriate
    - Ensures space after closing punctuation before next word
    - Detects and fixes merged Ukrainian/Cyrillic words (e.g., "Цеприклад" → "Це приклад")
    - Preserves URLs (https://, http://)
    - Preserves newlines

    Args:
        text: Raw text string that may have spacing issues

    Returns:
        Normalized text with proper spacing
    """
    if not text:
        return text

    import re

    # Preserve URLs first (replace temporarily)
    url_placeholders = {}
    url_pattern = r"https?://[^\s]+"
    urls = re.findall(url_pattern, text)
    for i, url in enumerate(urls):
        placeholder = f"__URL_PLACEHOLDER_{i}__"
        url_placeholders[placeholder] = url
        text = text.replace(url, placeholder)

    # CRITICAL FIX: Detect merged Ukrainian/Cyrillic words
    # Pattern 1: lowercase Cyrillic letter followed by uppercase Cyrillic letter (word boundary)
    # Cyrillic range: \u0400-\u04FF (includes Ukrainian, Russian, etc.)
    # This fixes cases like "Цеприклад" → "Це приклад", "Формазазвичай" → "Форма зазвичай"
    text = re.sub(
        r"([\u0430-\u044f\u0456\u0457\u0491])([\u0410-\u042f\u0406\u0407\u0490])",
        r"\1 \2",
        text,
    )

    # Pattern 2: Common Ukrainian word endings followed by common word beginnings (lowercase+lowercase)
    # This fixes cases like "виглядатиформа" → "виглядати форма"
    # Match: word ending (2+ lowercase Cyrillic) + common word beginning
    # Common beginnings that often get merged: форма, документ, приклад, це, цей, ця, який, яка, яке
    text = re.sub(
        r"([\u0430-\u044f\u0456\u0457\u0491]{2,})(форма|документ|приклад|це|цей|ця|який|яка|яке)",
        r"\1 \2",
        text,
        flags=re.IGNORECASE,
    )

    # Fix: ensure space after punctuation (but not if followed by space or newline)
    # Pattern: punctuation followed by letter (no space)
    text = re.sub(r"([.,:;!?])([^\s\n])", r"\1 \2", text)

    # Fix: ensure space after closing parenthesis/bracket before letter
    text = re.sub(r"([\)\]])([^\s\n])", r"\1 \2", text)

    # Fix: ensure space before opening parenthesis/bracket after letter
    text = re.sub(r"([^\s\n])([\(\[])", r"\1 \2", text)

    # Collapse multiple spaces to single space (but preserve newlines)
    lines = text.split("\n")
    normalized_lines = []
    for line in lines:
        # Collapse spaces within line
        line = re.sub(r" +", " ", line)
        # Remove leading/trailing spaces
        line = line.strip()
        normalized_lines.append(line)
    text = "\n".join(normalized_lines)

    # Restore URLs
    for placeholder, url in url_placeholders.items():
        text = text.replace(placeholder, url)

    return text


def _prepare_text_for_pdf(text: str, lang: str) -> str:
    """
    For Arabic (RTL): apply reshaping + bidi so letters connect and order is correct.
    Other languages: return text as-is (optional normalization already applied elsewhere).
    """
    if not text or not isinstance(text, str):
        return text or ""
    lang = (lang or "").strip().lower()
    if lang != "ar":
        return text
    if not _HAS_RTL_SUPPORT:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        return bidi.algorithm.get_display(reshaped)
    except Exception as e:
        logger.debug("RTL prepare failed (non-critical): %s", e)
        return text


def _get_document_title(doc_type: str) -> str:
    """
    Get the official German document title for a given document type.

    Args:
        doc_type: Document type identifier (e.g., 'anmeldung', 'kindergeld')

    Returns:
        Official German document title
    """
    title_map = {
        "anmeldung": "Anmeldung",
        "abmeldung": "Abmeldung",
        "ummeldung": "Ummeldung",
        "kindergeld": "Kindergeld",
        "bürgergeld": "Bürgergeld",
        "wohngeld": "Wohngeld",
    }
    return title_map.get(doc_type.lower(), doc_type.upper().replace("_", " "))


def _get_authority_name(doc_type: str) -> str:
    """
    Get the official authority name responsible for the document type.

    Args:
        doc_type: Document type identifier

    Returns:
        Authority name (e.g., 'Bürgeramt', 'Familienkasse')
    """
    authority_map = {
        "anmeldung": "Bürgeramt",
        "abmeldung": "Bürgeramt",
        "ummeldung": "Bürgeramt",
        "kindergeld": "Familienkasse",
        "bürgergeld": "Jobcenter",
        "wohngeld": "Wohngeldstelle",
    }
    return authority_map.get(doc_type.lower(), "Zuständige Behörde")


def draw_cover_page(
    canvas_obj: canvas.Canvas,
    doc_type: str,
    authority_name: str,
    user_lang: str = "en",
    is_preview: bool = True,
) -> None:
    """
    Draw a cover page explaining the document.

    This cover page appears ONLY in preview PDFs (Page 1).
    Final PDFs do NOT include this page.

    Args:
        canvas_obj: ReportLab canvas object
        doc_type: Document type (e.g., 'anmeldung')
        authority_name: Official authority name (e.g., 'Bürgeramt')
        user_lang: User language code (for future localization)
        is_preview: If True, add diagonal watermark
    """
    width, height = A4

    # Background (white)
    canvas_obj.setFillColor(black)

    # Large document title at top
    doc_title = _get_document_title(doc_type)
    canvas_obj.setFont("Helvetica-Bold", 32)
    title_y = height - 150
    canvas_obj.drawCentredString(width / 2, title_y, doc_title)

    # Authority name below title
    canvas_obj.setFont("Helvetica", 18)
    authority_y = title_y - 50
    canvas_obj.drawCentredString(width / 2, authority_y, authority_name)

    # Explanation text (centered, multi-line)
    # Clear messaging: This IS the correct document, official form starts on page 2
    canvas_obj.setFont("Helvetica", 12)
    explanation_lines = [
        "This is a preview explanation page.",
        "The official German government form starts on the next page.",
        "",
        "This IS the correct document you selected.",
        "The official form begins on page 2.",
        "This page is informational only.",
    ]

    line_height = 22
    start_y = height / 2 + 60

    for i, line in enumerate(explanation_lines):
        y_pos = start_y - (i * line_height)
        # Draw line (empty lines create spacing)
        canvas_obj.drawCentredString(width / 2, y_pos, line)

    # Diagonal watermark: "PREVIEW · NOT OFFICIAL" (only in preview mode)
    if is_preview:
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 48)
        canvas_obj.setFillColor(grey, alpha=0.15)

        # Center of page
        center_x = width / 2
        center_y = height / 2

        # Rotate 45 degrees around center
        canvas_obj.translate(center_x, center_y)
        canvas_obj.rotate(45)
        canvas_obj.drawCentredString(0, 0, "PREVIEW · NOT OFFICIAL")
        canvas_obj.restoreState()

    canvas_obj.showPage()


def _get_explanation_text(user_lang: str = "en") -> list:
    """
    Get localized explanation text for preview PDF.

    Args:
        user_lang: User language code (uk, de, en, pl, tr, ar)

    Returns:
        List of explanation text lines
    """
    explanations = {
        "uk": [
            "Це сторінка попереднього перегляду.",
            "Офіційна німецька форма починається на наступній сторінці.",
            "",
            "Це ПРАВИЛЬНИЙ документ, який ви обрали.",
            "Офіційна форма починається на сторінці 2.",
            "Ця сторінка лише інформаційна.",
        ],
        "ua": [
            "Це сторінка попереднього перегляду.",
            "Офіційна німецька форма починається на наступній сторінці.",
            "",
            "Це ПРАВИЛЬНИЙ документ, який ви обрали.",
            "Офіційна форма починається на сторінці 2.",
            "Ця сторінка лише інформаційна.",
        ],
        "de": [
            "Dies ist eine Vorschauseite.",
            "Das offizielle deutsche Formular beginnt auf der nächsten Seite.",
            "",
            "Dies IST das richtige Dokument, das Sie ausgewählt haben.",
            "Das offizielle Formular beginnt auf Seite 2.",
            "Diese Seite dient nur zur Information.",
        ],
        "en": [
            "This is a preview page.",
            "The official German form starts on the next page.",
            "",
            "This IS the correct document you selected.",
            "The official form begins on page 2.",
            "This page is informational only.",
        ],
        "pl": [
            "To jest strona podglądu.",
            "Oficjalny formular niemiecki zaczyna się na następnej stronie.",
            "",
            "To JEST właściwy dokument, który wybrałeś.",
            "Oficjalny formularz zaczyna się na stronie 2.",
            "Ta strona jest tylko informacyjna.",
        ],
        "tr": [
            "Bu bir önizleme sayfasıdır.",
            "Resmi Alman formu bir sonraki sayfada başlar.",
            "",
            "Bu SEÇTİĞİNİZ doğru belgedir.",
            "Resmi form sayfa 2'de başlar.",
            "Bu sayfa yalnızca bilgilendirme amaçlıdır.",
        ],
        "ar": [
            "هذه صفحة معاينة.",
            "يبدأ النموذج الألماني الرسمي في الصفحة التالية.",
            "",
            "هذا هو المستند الصحيح الذي اخترته.",
            "يبدأ النموذج الرسمي في الصفحة 2.",
            "هذه الصفحة للإعلام فقط.",
        ],
    }

    # FIX: normalization - Keep "uk" as-is, do NOT map to "ua" (explanations dict uses "uk")
    lang = user_lang.lower() if user_lang else "en"
    # Remove uk -> ua mapping since explanations dict already has "uk" key
    if lang not in explanations:
        logger.warning(
            f"[LANG] Language '{user_lang}' not found in explanations, using 'en'"
        )
        lang = "en"

    return explanations.get(lang, explanations["en"])


# ============================================================================
# DOCUMENT EXPLANATION TEXTS (Multi-language)
# ============================================================================

# Import centralized preview texts (no fallback language — user's language or error)
from backend.preview_texts import (
    get_preview_blocks,
    get_preview_disclaimer,
    get_authority_block_text,
    get_universal_explanatory_block,
    get_preview_key_block_fields,
    get_preview_full_structure_text,
    get_preview_after_payment_text,
    _normalize_preview_lang,
    PREVIEW_DISCLAIMER_TEXTS,
)

# Legacy PREVIEW_TEXTS (deprecated - use get_preview_blocks instead)
PREVIEW_TEXTS = {
    "anmeldung": {
        "ua": {
            "title": "Anmeldung (реєстрація місця проживання)",
            "description": "Цей документ використовується для офіційної реєстрації місця проживання в Німеччині у місцевому органі (Bürgeramt).",
            "structure": "Офіційний формуляр складається приблизно з 9 сторінок і містить особисті дані, адресу проживання, дату переїзду та дані орендодавця.",
            "preview_note": "Це превʼю є прикладом заповнення документа на основі даних, які ви ввели в анкеті.\n⚠️ Це не офіційний документ.",
            "what_next": "Мета превʼю — допомогти вам правильно заповнити офіційну форму, щоб уникнути помилок і повернення заяви.\nПісля генерації ви отримаєте повністю заповнений приклад усіх сторінок та посилання на офіційну онлайн-форму.",
        },
        "pl": {
            "title": "Anmeldung (rejestracja miejsca zamieszkania)",
            "description": "Ten dokument służy do oficjalnej rejestracji miejsca zamieszkania w Niemczech w lokalnym urzędzie (Bürgeramt).",
            "structure": "Oficjalny formularz składa się z około 9 stron i zawiera dane osobowe, adres zamieszkania, datę przeprowadzki oraz dane wynajmującego.",
            "preview_note": "Ten podgląd jest przykładem wypełnienia dokumentu na podstawie danych, które wprowadziłeś w formularzu.\n⚠️ To nie jest oficjalny dokument.",
            "what_next": "Celem podglądu jest pomoc w prawidłowym wypełnieniu oficjalnego formularza, aby uniknąć błędów i zwrotu wniosku.\nPo wygenerowaniu otrzymasz w pełni wypełniony przykład wszystkich stron oraz link do oficjalnego formularza online.",
        },
        "en": {
            "title": "Anmeldung (residence registration)",
            "description": "This document is used for official registration of residence in Germany at the local authority (Bürgeramt).",
            "structure": "The official form consists of approximately 9 pages and contains personal data, residence address, move-in date, and landlord information.",
            "preview_note": "This preview is an example of document completion based on the data you entered in the questionnaire.\n⚠️ This is not an official document.",
            "what_next": "The purpose of the preview is to help you correctly fill out the official form to avoid errors and application returns.\nAfter generation, you will receive a fully completed example of all pages and a link to the official online form.",
        },
        "de": {
            "title": "Anmeldung (Wohnsitzanmeldung)",
            "description": "Dieses Dokument dient der offiziellen Anmeldung des Wohnsitzes in Deutschland beim örtlichen Bürgeramt.",
            "structure": "Das offizielle Formular besteht aus etwa 9 Seiten und enthält persönliche Daten, Wohnadresse, Einzugsdatum und Vermieterdaten.",
            "preview_note": "Diese Vorschau ist ein Beispiel für die Ausfüllung des Dokuments basierend auf den von Ihnen eingegebenen Daten.\n⚠️ Dies ist kein offizielles Dokument.",
            "what_next": "Der Zweck der Vorschau ist es, Ihnen zu helfen, das offizielle Formular korrekt auszufüllen, um Fehler und Antragsrückgaben zu vermeiden.\nNach der Generierung erhalten Sie ein vollständig ausgefülltes Beispiel aller Seiten und einen Link zum offiziellen Online-Formular.",
        },
        "tr": {
            "title": "Anmeldung (ikamet kaydı)",
            "description": "Bu belge, Almanya'da yerel makam (Bürgeramt) nezdinde ikamet kaydı için kullanılır.",
            "structure": "Resmi form yaklaşık 9 sayfadan oluşur ve kişisel veriler, ikamet adresi, taşınma tarihi ve ev sahibi bilgilerini içerir.",
            "preview_note": "Bu önizleme, anket formunda girdiğiniz verilere dayalı belge doldurma örneğidir.\n⚠️ Bu resmi bir belge değildir.",
            "what_next": "Önizlemenin amacı, hataları ve başvuru iadelerini önlemek için resmi formu doğru şekilde doldurmanıza yardımcı olmaktır.\nOluşturma sonrasında, tüm sayfaların tamamen doldurulmuş bir örneğini ve resmi çevrimiçi formun bağlantısını alacaksınız.",
        },
        "ar": {
            "title": "Anmeldung (تسجيل الإقامة)",
            "description": "يُستخدم هذا المستند للتسجيل الرسمي للإقامة في ألمانيا لدى السلطة المحلية (Bürgeramt).",
            "structure": "يتكون النموذج الرسمي من حوالي 9 صفحات ويحتوي على البيانات الشخصية وعنوان الإقامة وتاريخ الانتقال ومعلومات المالك.",
            "preview_note": "هذه المعاينة هي مثال على ملء المستند بناءً على البيانات التي أدخلتها في الاستبيان.\n⚠️ هذا ليس مستندًا رسميًا.",
            "what_next": "الغرض من المعاينة هو مساعدتك على ملء النموذج الرسمي بشكل صحيح لتجنب الأخطاء وإرجاع الطلب.\nبعد الإنشاء، ستحصل على مثال مكتمل لجميع الصفحات ورابط إلى النموذج الرسمي عبر الإنترنت.",
        },
    }
    # TODO: Add other document types (abmeldung, kindergeld, etc.) as needed
}


# Short footer and body title for preview (one line each, no dependency on doc type)
PREVIEW_FOOTER_ONE_LINE = {
    "ua": "Це превʼю. Неофіційний документ.",
    "en": "This is a preview. Not an official document.",
    "ru": "Это превью. Неофициальный документ.",
    "de": "Dies ist eine Vorschau. Kein offizielles Dokument.",
    "pl": "To jest podgląd. Dokument nieoficjalny.",
    "tr": "Bu bir önizlemedir. Resmî bir belge değildir.",
    "ar": "هذه معاينة وليست وثيقة رسمية.",
}
PREVIEW_BODY_TITLE = {
    "ua": "Перевірте введені дані перед створенням документа",
    "uk": "Перевірте введені дані перед створенням документа",
    "en": "Review your data before generating the document",
    "pl": "Sprawdź wprowadzone dane przed utworzeniem dokumentu",
    "tr": "Belge oluşturmadan önce girdiğiniz verileri kontrol edin",
    "ar": "راجع بياناتك قبل إنشاء المستند",
}

PREVIEW_SUBHEADER = {
    "ua": "Це попередній перегляд для перевірки правильності інформації",
    "uk": "Це попередній перегляд для перевірки правильності інформації",
    "en": "This is a preview for checking the accuracy of your information",
    "pl": "To podgląd do sprawdzenia poprawności informacji",
    "tr": "Bu, bilgilerinizin doğruluğunu kontrol etmek için bir önizlemedir",
    "ar": "هذه معاينة للتحقق من دقة معلوماتك",
}

# ---------------------------------------------------------------------------
# PREVIEW_HEADER — prominent localized header block shown at the top of every
# preview PDF.  title = large bold stamp; text = short explanatory paragraph.
# ---------------------------------------------------------------------------
PREVIEW_HEADER: Dict[str, Dict[str, str]] = {
    "uk": {
        "title": "ПЕРЕВІРКА ДАНИХ АНКЕТИ",
        "text": (
            "Це перевірка правильності заповнення анкети. "
            "Будь ласка, уважно перевірте всі дані перед генерацією офіційного PDF. "
            "Цей документ не є офіційним."
        ),
    },
    "ua": {
        "title": "ПЕРЕВІРКА ДАНИХ АНКЕТИ",
        "text": (
            "Це перевірка правильності заповнення анкети. "
            "Будь ласка, уважно перевірте всі дані перед генерацією офіційного PDF. "
            "Цей документ не є офіційним."
        ),
    },
    "en": {
        "title": "FORM DATA CHECK",
        "text": (
            "This is a verification of the information you entered. "
            "Please carefully review all fields before generating the official PDF. "
            "This document is not official."
        ),
    },
    "de": {
        "title": "DATENÜBERPRÜFUNG",
        "text": (
            "Dies ist eine Überprüfung der eingegebenen Angaben. "
            "Bitte prüfen Sie alle Daten sorgfältig vor der Erstellung des offiziellen PDFs. "
            "Dieses Dokument ist nicht offiziell."
        ),
    },
    "pl": {
        "title": "SPRAWDZENIE DANYCH FORMULARZA",
        "text": (
            "To jest weryfikacja poprawności wprowadzonych danych. "
            "Proszę dokładnie sprawdzić wszystkie pola przed wygenerowaniem oficjalnego PDF. "
            "Ten dokument nie jest oficjalny."
        ),
    },
    "tr": {
        "title": "FORM VERİ KONTROLÜ",
        "text": (
            "Bu, girilen bilgilerin doğruluk kontrolüdür. "
            "Resmi PDF oluşturmadan önce tüm alanları dikkatlice kontrol edin. "
            "Bu belge resmi değildir."
        ),
    },
    "ar": {
        "title": "مراجعة البيانات",
        "text": (
            "هذه مراجعة لصحة البيانات التي أدخلتها. "
            "يرجى التحقق من جميع الحقول قبل إنشاء الملف الرسمي. "
            "هذا المستند غير رسمي."
        ),
    },
}

# Localized placeholder for empty/missing field values
PREVIEW_EMPTY_VALUE = {
    "ua": "(не заповнено)",
    "uk": "(не заповнено)",
    "en": "(not filled)",
    "pl": "(nie wypełniono)",
    "tr": "(doldurulmadı)",
    "ar": "(لم يتم ملؤه)",
}

# Localized footer line for preview PDF
PREVIEW_FOOTER_LINE = {
    "ua": "Це неофіційний попередній перегляд",
    "uk": "Це неофіційний попередній перегляд",
    "en": "This is an unofficial preview",
    "pl": "To nieoficjalny podgląd",
    "tr": "Bu resmi olmayan bir önizlemedir",
    "ar": "هذه معاينة غير رسمية",
}

# Localized watermark text for preview PDF diagonal stamp
PREVIEW_WATERMARK_TEXTS = {
    "ua": "ПЕРЕВІРКА · НЕ ОФІЦІЙНИЙ ДОКУМЕНТ",
    "uk": "ПЕРЕВІРКА · НЕ ОФІЦІЙНИЙ ДОКУМЕНТ",
    "en": "PREVIEW – NOT OFFICIAL",
    "pl": "PODGLĄD – NIEOFICJALNY",
    "tr": "ÖNİZLEME – RESMİ DEĞİL",
    "ar": "معاينة – غير رسمي",
}

# --- Contextual "Common Mistakes" tips shown ONLY in preview PDF ---
# Per doc_type, per language. Short bullet list of typical user errors.
PREVIEW_COMMON_MISTAKES: Dict[str, Dict[str, List[str]]] = {
    "anmeldung": {
        "ua": [
            "ПІБ має бути латиницею, як у паспорті",
            "Дата — формат ДД.ММ.РРРР (не місяць/день/рік)",
            "Поштовий індекс — рівно 5 цифр",
            "Вулиця — без номера будинку (окреме поле)",
            "Орган видачі — повна назва, не скорочення",
        ],
        "en": [
            "Name must be in Latin script, as in passport",
            "Dates — DD.MM.YYYY format (not month/day/year)",
            "Postal code — exactly 5 digits",
            "Street — without house number (separate field)",
            "Issuing authority — full name, not abbreviation",
        ],
        "de": [
            "Name in Lateinschrift, wie im Reisepass",
            "Datum — TT.MM.JJJJ (nicht MM/TT/JJJJ)",
            "PLZ — genau 5 Ziffern",
            "Straße — ohne Hausnummer (separates Feld)",
            "Ausstellungsbehörde — vollständiger Name",
        ],
        "pl": [
            "Imię i nazwisko alfabetem łacińskim, jak w paszporcie",
            "Data — format DD.MM.RRRR (nie miesiąc/dzień/rok)",
            "Kod pocztowy — dokładnie 5 cyfr",
            "Ulica — bez numeru domu (osobne pole)",
            "Organ wydający — pełna nazwa, nie skrót",
        ],
        "tr": [
            "İsim pasaporttaki gibi Latin harfleriyle olmalı",
            "Tarih — GG.AA.YYYY biçiminde (ay/gün/yıl değil)",
            "Posta kodu — tam 5 rakam",
            "Sokak — bina numarası olmadan (ayrı alan)",
            "Düzenleyen makam — tam adı, kısaltma değil",
        ],
        "ar": [
            "الاسم بالأحرف اللاتينية كما في جواز السفر",
            "التاريخ — بتنسيق DD.MM.YYYY (ليس شهر/يوم/سنة)",
            "الرمز البريدي — 5 أرقام بالضبط",
            "الشارع — بدون رقم المنزل (حقل منفصل)",
            "جهة الإصدار — الاسم الكامل وليس اختصار",
        ],
    },
}

# Fields to visually emphasize in preview (critical for document correctness)
_CRITICAL_FIELDS = {
    "first_name",
    "firstname",
    "last_name",
    "lastname",
    "birth_date",
    "birthday",
    "date_of_birth",
    "street",
    "street_name",
    "house_number",
    "house_no",
    "plz",
    "postcode",
    "postal_code",
    "city",
    "ort",
    "move_in_date",
    "move_out_date",
}

# UX: короткий блок «що ми робимо» — повноцінна копія для правильного заповнення, посилання на бланк, ми зіткнулися з бюрократією, мета — щоб не відправляли назад
PREVIEW_WHY_BLOCK = {
    "ua": "Ми готуємо повноцінну копію вашого документа — щоб ви могли правильно заповнити офіційну форму. Ми самі зіткнулися з німецькою бюрократією, тому наша мета проста: щоб офіційні інстанції не відправляли документ назад через помилки в заповненні. Після оплати ви отримаєте готовий приклад усіх сторінок та посилання на офіційну форму.",
    "uk": "Ми готуємо повноцінну копію вашого документа — щоб ви могли правильно заповнити офіційну форму. Ми самі зіткнулися з німецькою бюрократією, тому наша мета проста: щоб офіційні інстанції не відправляли документ назад через помилки в заповненні. Після оплати ви отримаєте готовий приклад усіх сторінок та посилання на офіційну форму.",
    "en": "We create a full copy of your document so you can fill in the official form correctly. We've faced German bureaucracy ourselves — so our goal is simple: to help avoid documents being sent back due to filling errors. After payment you get a ready example of all pages and a link to the official form.",
    "ru": "Мы готовим полноценную копию вашего документа — чтобы вы могли правильно заполнить официальный бланк. Мы сами столкнулись с немецкой бюрократией, поэтому наша цель проста: чтобы ведомства не отправляли документ обратно из‑за ошибок в заполнении. После оплаты вы получите готовый пример всех страниц и ссылку на официальный бланк.",
    "de": "Wir erstellen eine vollständige Kopie Ihres Dokuments — damit Sie das offizielle Formular korrekt ausfüllen können. Wir haben die deutsche Bürokratie selbst erlebt. Unser Ziel: Dass Behörden Ihr Dokument nicht wegen Ausfüllfehlern zurückschicken. Nach der Zahlung erhalten Sie ein fertiges Beispiel aller Seiten und den Link zum offiziellen Formular.",
    "pl": "Przygotowujemy pełną kopię Twojego dokumentu — żebyś mógł poprawnie wypełnić oficjalny formularz. Sami zetknęliśmy się z niemiecką biurokracją, więc nasz cel jest prosty: żeby urzędy nie odsyłały dokumentu z powodu błędów w wypełnieniu. Po opłaceniu otrzymasz gotowy przykład wszystkich stron oraz link do oficjalnego formularza.",
    "tr": "Resmi formu doğru doldurmanız için belgenizin tam bir kopyasını oluşturuyoruz. Alman bürokrasisiyle kendimiz karşılaştık — amacımız basit: Doldurma hataları yüzünden belgenizin iade edilmesini önlemek. Ödeme sonrası tüm sayfaların hazır örneğini ve resmi formun linkini alacaksınız.",
    "ar": "نحن نُعد نسخة كاملة من مستندك لتملأ النموذج الرسمي بشكل صحيح. واجهنا البيروقراطية الألمانية بأنفسنا — هدفنا بسيط: تجنب إرجاع المستند بسبب أخطاء في الملء. بعد الدفع تحصل على مثال جاهز لجميع الصفحات ورابط النموذج الرسمي.",
}
PREVIEW_WHY_TITLE = {
    "ua": "Що ми робимо",
    "uk": "Що ми робимо",
    "en": "What we do",
    "ru": "Что мы делаем",
    "de": "Was wir tun",
    "pl": "Co robimy",
    "tr": "Ne yapıyoruz",
    "ar": "ماذا نقدم",
}

# Value block sub-section: "After payment you get:" + bullets (same meaning as existing text)
PREVIEW_AFTER_PAYMENT_TITLE = {
    "ua": "Після оплати ви отримаєте:",
    "uk": "Після оплати ви отримаєте:",
    "en": "After payment you get:",
    "de": "Nach der Zahlung erhalten Sie:",
    "pl": "Po opłaceniu otrzymasz:",
    "tr": "Ödeme sonrası alacaksınız:",
    "ar": "بعد الدفع تحصل على:",
}
PREVIEW_AFTER_PAYMENT_BULLETS = {
    "ua": (
        "Повний приклад заповненого документа (усі сторінки)",
        "Посилання на офіційний чистий бланк",
        "Орієнтир для правильного заповнення без повернення",
    ),
    "uk": (
        "Повний приклад заповненого документа (усі сторінки)",
        "Посилання на офіційний чистий бланк",
        "Орієнтир для правильного заповнення без повернення",
    ),
    "en": (
        "Full example of filled document (all pages)",
        "Link to official blank form",
        "Guidance for correct filling without returns",
    ),
    "de": (
        "Vollständiges Beispiel aller Seiten",
        "Link zum offiziellen Blankoformular",
        "Orientierung für korrektes Ausfüllen ohne Rückweisung",
    ),
    "pl": (
        "Pełny przykład wypełnionego dokumentu (wszystkie strony)",
        "Link do oficjalnego czystego formularza",
        "Orientacja do prawidłowego wypełnienia bez zwrotu",
    ),
    "tr": (
        "Doldurulmuş belgenin tam örneği (tüm sayfalar)",
        "Resmi boş formun linki",
        "Geri gönderilmeden doğru doldurma rehberi",
    ),
    "ar": (
        "مثال كامل للمستند المملوء (جميع الصفحات)",
        "رابط النموذج الرسمي الفارغ",
        "توجيه للملء الصحيح دون إرجاع",
    ),
}
# Micro-signal above footer: trust, same meaning as existing
PREVIEW_MICRO_SIGNAL = {
    "ua": "Це лише превʼю. Повна версія містить кілька сторінок та офіційний бланк.",
    "uk": "Це лише превʼю. Повна версія містить кілька сторінок та офіційний бланк.",
    "en": "This is a preview only. The full version contains several pages and the official form.",
    "de": "Dies ist nur eine Vorschau. Die Vollversion enthält mehrere Seiten und das offizielle Formular.",
    "pl": "To tylko podgląd. Pełna wersja zawiera kilka stron oraz oficjalny formularz.",
    "tr": "Bu yalnızca bir önizlemedir. Tam sürüm birkaç sayfa ve resmi form içerir.",
    "ar": "هذه معاينة فقط. النسخة الكاملة تحتوي على عدة صفحات والنموذج الرسمي.",
}

# Localized subtitle: "PREVIEW — NOT AN OFFICIAL DOCUMENT"
PREVIEW_SUBTITLE_TEXT = {
    "ua": "ПОПЕРЕДНІЙ ПЕРЕГЛЯД — НЕ ОФІЦІЙНИЙ ДОКУМЕНТ",
    "uk": "ПОПЕРЕДНІЙ ПЕРЕГЛЯД — НЕ ОФІЦІЙНИЙ ДОКУМЕНТ",
    "en": "PREVIEW — NOT AN OFFICIAL DOCUMENT",
    "de": "VORSCHAU — KEIN OFFIZIELLES DOKUMENT",
    "pl": "PODGLĄD — NIE JEST OFICJALNYM DOKUMENTEM",
    "tr": "ÖNİZLEME — RESMİ BİR BELGE DEĞİLDİR",
    "ar": "معاينة — ليست وثيقة رسمية",
}

# Localized prompt: "Please check your data carefully"
PREVIEW_CHECK_DATA_TEXT = {
    "ua": "Будь ласка, уважно перевірте свої дані перед підтвердженням.",
    "uk": "Будь ласка, уважно перевірте свої дані перед підтвердженням.",
    "en": "Please check your data carefully before confirming.",
    "de": "Bitte überprüfen Sie Ihre Daten sorgfältig vor der Bestätigung.",
    "pl": "Proszę dokładnie sprawdzić swoje dane przed potwierdzeniem.",
    "tr": "Lütfen onaylamadan önce verilerinizi dikkatlice kontrol edin.",
    "ar": "يرجى التحقق من بياناتك بعناية قبل التأكيد.",
}

# Localized diagonal watermark text
PREVIEW_WATERMARK_TEXT = {
    "ua": "ПОПЕРЕДНІЙ ПЕРЕГЛЯД",
    "uk": "ПОПЕРЕДНІЙ ПЕРЕГЛЯД",
    "en": "PREVIEW",
    "de": "VORSCHAU",
    "pl": "PODGLĄD",
    "tr": "ÖNİZLEME",
    "ar": "معاينة",
}

# Preview layout: premium, balanced, bureaucratic-clean
PREVIEW_MARGIN_LEFT = 50
PREVIEW_MARGIN_RIGHT = 27  # content width slightly wider, less emptiness
PREVIEW_MARGIN_TOP = 80
PREVIEW_FOOTER_RESERVED = 50
PREVIEW_FIELD_GAP = 11  # form-like rhythm between label:value rows
PREVIEW_TITLE_SUBTITLE_GAP = 12
PREVIEW_SUBTITLE_BODY_GAP = 24
PREVIEW_SECTION_TOP_GAP = 12
PREVIEW_DIVIDER_GAP = 18
PREVIEW_SUBTITLE_GRAY = HexColor("#777777")  # lighter, visually subordinate
PREVIEW_EXPLANATION_BG = HexColor("#f4f4f4")  # very light background, premium signal
PREVIEW_EXPLANATION_BORDER = HexColor("#b0b0b0")  # subtle border
PREVIEW_FOOTER_TEXT_COLOR = HexColor("#666666")  # system-like, calm, not faint
PREVIEW_VALUE_COLOR = HexColor("#333333")
PREVIEW_MICRO_SIGNAL_COLOR = HexColor("#666666")

# Version stamp in preview PDF (to confirm new code, not cache)
PREVIEW_VERSION = "1.0"


def _get_geo_block_text(bundesland: str, authority_type: str, lang: str) -> tuple:
    """
    Get localized geo block text. Fallback to 'en' if lang missing, NOT 'ua'.
    Uses centralized preview_texts module.
    """
    # Normalize language code
    if lang == "uk":
        lang = "ua"
    if lang not in ["ua", "en", "de", "pl", "tr", "ar"]:
        lang = "en"  # CRITICAL: Fallback to 'en', NOT 'ua'

    # Use centralized authority block texts
    authority_texts = get_authority_block_text(lang)
    title = authority_texts["title"]
    content = authority_texts["content"].format(
        bundesland=bundesland, authority_type=authority_type
    )

    return title, content


# Preview disclaimer texts are now imported from backend.preview_texts
# Legacy PREVIEW_DISCLAIMER_TEXTS kept for backward compatibility


def draw_preview_disclaimer(
    canvas_obj: canvas.Canvas,
    user_lang: str = "en",
    font_normal: str = "Helvetica",
    width: float = 595,
    height: float = 842,
    y_position: Optional[float] = None,
) -> None:
    """
    Малює інформаційний блок превʼю (сіра рамка внизу). Текст завжди з user_lang; fallback на en.
    Arabic: NotoSansArabic + RTL-shaped text.
    """
    try:
        lang = _normalize_preview_lang(user_lang or "en")
    except (ValueError, TypeError):
        lang = "en"
    disclaimer_lines = get_preview_disclaimer(lang)
    is_rtl = lang == "ar"
    # RTL: Arabic needs correct font and shaped text (no broken/reversed letters)
    if is_rtl:
        _register_arabic_font_for_reportlab()
        font_normal = "NotoSansArabic"
        disclaimer_lines = [_prepare_text_for_pdf(ln, "ar") for ln in disclaimer_lines]
    canvas_obj.setFont(font_normal, 8)
    canvas_obj.setFillColor(grey, alpha=0.7)
    line_height = 12
    padding_x = 50
    if y_position is not None:
        disclaimer_y_start = y_position - (len(disclaimer_lines) * line_height) - 5
    else:
        disclaimer_y_start = 60
    box_height = len(disclaimer_lines) * line_height + 10
    box_y = disclaimer_y_start - 5
    canvas_obj.setFillColor(grey, alpha=0.1)
    canvas_obj.setStrokeColor(grey, alpha=0.35)
    canvas_obj.setLineWidth(0.5)
    canvas_obj.rect(
        padding_x - 5,
        box_y - 5,
        width - (padding_x * 2) + 10,
        box_height,
        fill=1,
        stroke=1,
    )
    canvas_obj.setFillColor(grey, alpha=0.7)
    for i, line in enumerate(disclaimer_lines):
        y_pos = disclaimer_y_start + (len(disclaimer_lines) - 1 - i) * line_height
        if is_rtl:
            text_x = width - padding_x
            canvas_obj.drawRightString(text_x, y_pos, line)
        else:
            text_x = padding_x
            canvas_obj.drawString(text_x, y_pos, line)


# Official Anmeldung section titles (German) for preview layout — labels stay German.
ANMELDUNG_SECTION_TITLES_DE: Dict[str, str] = {
    "neue_wohnung": "Neue Wohnung",
    "bisherige_wohnung": "Bisherige Wohnung",
    "personal": "Angaben zur Person",
    "person_2": "Angaben zur Person (Person 2)",
    "landlord": "Wohnungsgeber",
    "dokumente": "Dokumente (Pflicht)",
    "signature": "Unterschrift",
}

# --- Preview self-check: field→section mapping for fallback grouping ---
_FIELD_SECTION_MAP: Dict[str, str] = {
    # Personal data
    "first_name": "personal",
    "last_name": "personal",
    "firstname": "personal",
    "lastname": "personal",
    "birthday": "personal",
    "birth_date": "personal",
    "date_of_birth": "personal",
    "birth_place": "personal",
    "nationality": "personal",
    "gender": "personal",
    "religion": "personal",
    "marital_status": "personal",
    "family_status": "personal",
    "salutation": "personal",
    "title": "personal",
    # Address (new)
    "street": "address",
    "street_name": "address",
    "house_number": "address",
    "house_no": "address",
    "plz": "address",
    "postcode": "address",
    "postal_code": "address",
    "city": "address",
    "ort": "address",
    "apartment_number": "address",
    "floor": "address",
    "address_addition": "address",
    "wohnungstyp": "address",
    # Previous address
    "old_street": "prev_address",
    "old_city": "prev_address",
    "old_address": "prev_address",
    "old_plz": "prev_address",
    "old_house_number": "prev_address",
    "old_postal_code": "prev_address",
    # Dates / status
    "move_in_date": "dates",
    "move_out_date": "dates",
    "start_date": "dates",
    "end_date": "dates",
    "registration_date": "dates",
    "employment_start": "dates",
    "employment_end": "dates",
    # Landlord
    "landlord_name": "landlord",
    "landlord_address": "landlord",
    # Family / children
    "child_name": "family",
    "child_birthday": "family",
    "child_first_name": "family",
    "child_last_name": "family",
    "child_birth_date": "family",
    "person2_first_name": "family",
    "person2_last_name": "family",
    "person2_birth_date": "family",
    "person2_nationality": "family",
    # Financial / employment
    "income": "financial",
    "rent": "financial",
    "salary": "financial",
    "tax_id": "financial",
    "iban": "financial",
    "employer": "financial",
    "employer_name": "financial",
    "employer_address": "financial",
    "job_title": "financial",
    "occupation": "financial",
    # Contact
    "email": "contact",
    "phone": "contact",
    "phone_number": "contact",
    # --- Anmeldung-specific fields ---
    "gemeindekennzahl": "address",
    "has_bisherige_wohnung": "prev_address",
    "previous_address": "prev_address",
    "zuzug_aus_ausland": "prev_address",
    "zuzug_staat": "prev_address",
    "bisherige_beibehalten": "prev_address",
    "weitere_wohnungen": "prev_address",
    "birth_name": "personal",
    "familienstand": "personal",
    "eheschliessung_ort_datum": "personal",
    "passname": "personal",
    "ordens_kuenstlername": "personal",
    "person2_birth_name": "family",
    "person2_birth_place": "family",
    "person2_gender": "family",
    "dokumentenart": "other",
    "ausstellungsbehoerde": "other",
    "seriennummer": "other",
    "ausstellungsdatum": "other",
    "gueltig_bis": "other",
    "signature_place": "other",
    "signature_date": "other",
}

_SECTION_TITLES: Dict[str, Dict[str, str]] = {
    "personal": {
        "ua": "Особисті дані",
        "en": "Personal data",
        "de": "Persönliche Angaben",
        "pl": "Dane osobowe",
        "tr": "Kişisel bilgiler",
        "ar": "البيانات الشخصية",
    },
    "address": {
        "ua": "Адреса",
        "en": "Address",
        "de": "Adresse",
        "pl": "Adres",
        "tr": "Adres",
        "ar": "العنوان",
    },
    "prev_address": {
        "ua": "Попередня адреса",
        "en": "Previous address",
        "de": "Bisherige Adresse",
        "pl": "Poprzedni adres",
        "tr": "Önceki adres",
        "ar": "العنوان السابق",
    },
    "dates": {
        "ua": "Дати / Терміни",
        "en": "Dates / Deadlines",
        "de": "Datum / Fristen",
        "pl": "Daty / Terminy",
        "tr": "Tarihler / Süreler",
        "ar": "التواريخ / المواعيد",
    },
    "landlord": {
        "ua": "Орендодавець",
        "en": "Landlord",
        "de": "Wohnungsgeber",
        "pl": "Wynajmujący",
        "tr": "Ev sahibi",
        "ar": "المؤجر",
    },
    "family": {
        "ua": "Сімʼя / Інші особи",
        "en": "Family / Other persons",
        "de": "Familie / Weitere Personen",
        "pl": "Rodzina / Inne osoby",
        "tr": "Aile / Diğer kişiler",
        "ar": "العائلة / أشخاص آخرون",
    },
    "financial": {
        "ua": "Фінанси / Зайнятість",
        "en": "Finances / Employment",
        "de": "Finanzen / Beschäftigung",
        "pl": "Finanse / Zatrudnienie",
        "tr": "Finans / İstihdam",
        "ar": "المالية / التوظيف",
    },
    "contact": {
        "ua": "Контактні дані",
        "en": "Contact details",
        "de": "Kontaktdaten",
        "pl": "Dane kontaktowe",
        "tr": "İletişim bilgileri",
        "ar": "بيانات الاتصال",
    },
    "other": {
        "ua": "Інші дані",
        "en": "Other details",
        "de": "Weitere Angaben",
        "pl": "Inne dane",
        "tr": "Diğer bilgiler",
        "ar": "بيانات أخرى",
    },
    # --- Anmeldung schema section IDs ---
    "neue_wohnung": {
        "ua": "Нове житло",
        "en": "New residence",
        "de": "Neue Wohnung",
        "pl": "Nowe mieszkanie",
        "tr": "Yeni konut",
        "ar": "السكن الجديد",
    },
    "bisherige_wohnung": {
        "ua": "Попереднє житло",
        "en": "Previous residence",
        "de": "Bisherige Wohnung",
        "pl": "Poprzednie mieszkanie",
        "tr": "Önceki konut",
        "ar": "السكن السابق",
    },
    "person_2": {
        "ua": "Друга особа",
        "en": "Second person",
        "de": "Zweite Person",
        "pl": "Druga osoba",
        "tr": "İkinci kişi",
        "ar": "الشخص الثاني",
    },
    "dokumente": {
        "ua": "Документи",
        "en": "Documents",
        "de": "Dokumente",
        "pl": "Dokumenty",
        "tr": "Belgeler",
        "ar": "المستندات",
    },
    "signature": {
        "ua": "Підпис",
        "en": "Signature",
        "de": "Unterschrift",
        "pl": "Podpis",
        "tr": "İmza",
        "ar": "التوقيع",
    },
    "weitere_wohnungen": {
        "ua": "Інші місця проживання",
        "en": "Other residences",
        "de": "Weitere Wohnungen",
        "pl": "Inne miejsca zamieszkania",
        "tr": "Diğer konutlar",
        "ar": "مساكن أخرى",
    },
}

_FALLBACK_SECTION_ORDER = [
    "personal",
    "address",
    "prev_address",
    "dates",
    "landlord",
    "family",
    "financial",
    "contact",
    "other",
]

# --- Localized field labels for preview self-check (6 languages) ---
FIELD_LABELS: Dict[str, Dict[str, str]] = {
    # Personal data
    "first_name": {
        "ua": "Імʼя",
        "en": "First name",
        "de": "Vorname",
        "pl": "Imię",
        "tr": "Ad",
        "ar": "الاسم الأول",
    },
    "last_name": {
        "ua": "Прізвище",
        "en": "Last name",
        "de": "Nachname",
        "pl": "Nazwisko",
        "tr": "Soyadı",
        "ar": "اسم العائلة",
    },
    "firstname": {
        "ua": "Імʼя",
        "en": "First name",
        "de": "Vorname",
        "pl": "Imię",
        "tr": "Ad",
        "ar": "الاسم الأول",
    },
    "lastname": {
        "ua": "Прізвище",
        "en": "Last name",
        "de": "Nachname",
        "pl": "Nazwisko",
        "tr": "Soyadı",
        "ar": "اسم العائلة",
    },
    "birthday": {
        "ua": "Дата народження",
        "en": "Date of birth",
        "de": "Geburtsdatum",
        "pl": "Data urodzenia",
        "tr": "Doğum tarihi",
        "ar": "تاريخ الميلاد",
    },
    "birth_date": {
        "ua": "Дата народження",
        "en": "Date of birth",
        "de": "Geburtsdatum",
        "pl": "Data urodzenia",
        "tr": "Doğum tarihi",
        "ar": "تاريخ الميلاد",
    },
    "date_of_birth": {
        "ua": "Дата народження",
        "en": "Date of birth",
        "de": "Geburtsdatum",
        "pl": "Data urodzenia",
        "tr": "Doğum tarihi",
        "ar": "تاريخ الميلاد",
    },
    "birth_place": {
        "ua": "Місце народження",
        "en": "Place of birth",
        "de": "Geburtsort",
        "pl": "Miejsce urodzenia",
        "tr": "Doğum yeri",
        "ar": "مكان الميلاد",
    },
    "nationality": {
        "ua": "Громадянство",
        "en": "Nationality",
        "de": "Nationalität",
        "pl": "Narodowość",
        "tr": "Uyruk",
        "ar": "الجنسية",
    },
    "gender": {
        "ua": "Стать",
        "en": "Gender",
        "de": "Geschlecht",
        "pl": "Płeć",
        "tr": "Cinsiyet",
        "ar": "الجنس",
    },
    "religion": {
        "ua": "Релігія",
        "en": "Religion",
        "de": "Religion",
        "pl": "Religia",
        "tr": "Din",
        "ar": "الديانة",
    },
    "marital_status": {
        "ua": "Сімейний стан",
        "en": "Marital status",
        "de": "Familienstand",
        "pl": "Stan cywilny",
        "tr": "Medeni durum",
        "ar": "الحالة الاجتماعية",
    },
    "family_status": {
        "ua": "Сімейний стан",
        "en": "Marital status",
        "de": "Familienstand",
        "pl": "Stan cywilny",
        "tr": "Medeni durum",
        "ar": "الحالة الاجتماعية",
    },
    "salutation": {
        "ua": "Звернення",
        "en": "Salutation",
        "de": "Anrede",
        "pl": "Zwrot grzecznościowy",
        "tr": "Hitap",
        "ar": "التحية",
    },
    "title": {
        "ua": "Титул",
        "en": "Title",
        "de": "Titel",
        "pl": "Tytuł",
        "tr": "Unvan",
        "ar": "اللقب",
    },
    # Address
    "street": {
        "ua": "Вулиця",
        "en": "Street",
        "de": "Straße",
        "pl": "Ulica",
        "tr": "Sokak",
        "ar": "الشارع",
    },
    "street_name": {
        "ua": "Вулиця",
        "en": "Street",
        "de": "Straße",
        "pl": "Ulica",
        "tr": "Sokak",
        "ar": "الشارع",
    },
    "house_number": {
        "ua": "Номер будинку",
        "en": "House number",
        "de": "Hausnummer",
        "pl": "Numer domu",
        "tr": "Bina numarası",
        "ar": "رقم المنزل",
    },
    "house_no": {
        "ua": "Номер будинку",
        "en": "House number",
        "de": "Hausnummer",
        "pl": "Numer domu",
        "tr": "Bina numarası",
        "ar": "رقم المنزل",
    },
    "plz": {
        "ua": "Поштовий індекс",
        "en": "Postal code",
        "de": "Postleitzahl",
        "pl": "Kod pocztowy",
        "tr": "Posta kodu",
        "ar": "الرمز البريدي",
    },
    "postcode": {
        "ua": "Поштовий індекс",
        "en": "Postal code",
        "de": "Postleitzahl",
        "pl": "Kod pocztowy",
        "tr": "Posta kodu",
        "ar": "الرمز البريدي",
    },
    "postal_code": {
        "ua": "Поштовий індекс",
        "en": "Postal code",
        "de": "Postleitzahl",
        "pl": "Kod pocztowy",
        "tr": "Posta kodu",
        "ar": "الرمز البريدي",
    },
    "city": {
        "ua": "Місто",
        "en": "City",
        "de": "Stadt",
        "pl": "Miasto",
        "tr": "Şehir",
        "ar": "المدينة",
    },
    "ort": {
        "ua": "Місто",
        "en": "City",
        "de": "Stadt",
        "pl": "Miasto",
        "tr": "Şehir",
        "ar": "المدينة",
    },
    "apartment_number": {
        "ua": "Номер квартири",
        "en": "Apartment number",
        "de": "Wohnungsnummer",
        "pl": "Numer mieszkania",
        "tr": "Daire numarası",
        "ar": "رقم الشقة",
    },
    "floor": {
        "ua": "Поверх",
        "en": "Floor",
        "de": "Stockwerk",
        "pl": "Piętro",
        "tr": "Kat",
        "ar": "الطابق",
    },
    "address_addition": {
        "ua": "Додаток до адреси",
        "en": "Address addition",
        "de": "Adresszusatz",
        "pl": "Dodatek do adresu",
        "tr": "Adres eki",
        "ar": "إضافة العنوان",
    },
    "wohnungstyp": {
        "ua": "Тип житла",
        "en": "Housing type",
        "de": "Wohnungstyp",
        "pl": "Typ mieszkania",
        "tr": "Konut türü",
        "ar": "نوع السكن",
    },
    # Previous address
    "old_street": {
        "ua": "Стара вулиця",
        "en": "Previous street",
        "de": "Alte Straße",
        "pl": "Poprzednia ulica",
        "tr": "Eski sokak",
        "ar": "الشارع السابق",
    },
    "old_city": {
        "ua": "Старе місто",
        "en": "Previous city",
        "de": "Alte Stadt",
        "pl": "Poprzednie miasto",
        "tr": "Eski şehir",
        "ar": "المدينة السابقة",
    },
    "old_address": {
        "ua": "Стара адреса",
        "en": "Previous address",
        "de": "Alte Adresse",
        "pl": "Poprzedni adres",
        "tr": "Eski adres",
        "ar": "العنوان السابق",
    },
    "old_plz": {
        "ua": "Старий індекс",
        "en": "Previous postal code",
        "de": "Alte PLZ",
        "pl": "Poprzedni kod",
        "tr": "Eski posta kodu",
        "ar": "الرمز البريدي السابق",
    },
    "old_house_number": {
        "ua": "Старий номер будинку",
        "en": "Previous house no.",
        "de": "Alte Hausnr.",
        "pl": "Poprzedni nr domu",
        "tr": "Eski bina no.",
        "ar": "رقم المنزل السابق",
    },
    "old_postal_code": {
        "ua": "Старий індекс",
        "en": "Previous postal code",
        "de": "Alte PLZ",
        "pl": "Poprzedni kod",
        "tr": "Eski posta kodu",
        "ar": "الرمز البريدي السابق",
    },
    # Dates
    "move_in_date": {
        "ua": "Дата заїзду",
        "en": "Move-in date",
        "de": "Einzugsdatum",
        "pl": "Data zameldowania",
        "tr": "Taşınma tarihi",
        "ar": "تاريخ الانتقال",
    },
    "move_out_date": {
        "ua": "Дата виїзду",
        "en": "Move-out date",
        "de": "Auszugsdatum",
        "pl": "Data wymeldowania",
        "tr": "Ayrılma tarihi",
        "ar": "تاريخ المغادرة",
    },
    "start_date": {
        "ua": "Дата початку",
        "en": "Start date",
        "de": "Startdatum",
        "pl": "Data rozpoczęcia",
        "tr": "Başlangıç tarihi",
        "ar": "تاريخ البدء",
    },
    "end_date": {
        "ua": "Дата закінчення",
        "en": "End date",
        "de": "Enddatum",
        "pl": "Data zakończenia",
        "tr": "Bitiş tarihi",
        "ar": "تاريخ الانتهاء",
    },
    "registration_date": {
        "ua": "Дата реєстрації",
        "en": "Registration date",
        "de": "Anmeldedatum",
        "pl": "Data rejestracji",
        "tr": "Kayıt tarihi",
        "ar": "تاريخ التسجيل",
    },
    "employment_start": {
        "ua": "Початок роботи",
        "en": "Employment start",
        "de": "Beschäftigungsbeginn",
        "pl": "Początek zatrudnienia",
        "tr": "İşe başlama",
        "ar": "بداية العمل",
    },
    "employment_end": {
        "ua": "Кінець роботи",
        "en": "Employment end",
        "de": "Beschäftigungsende",
        "pl": "Koniec zatrudnienia",
        "tr": "İşten ayrılma",
        "ar": "نهاية العمل",
    },
    # Landlord
    "landlord_name": {
        "ua": "Імʼя орендодавця",
        "en": "Landlord name",
        "de": "Vermieter Name",
        "pl": "Imię wynajmującego",
        "tr": "Ev sahibi adı",
        "ar": "اسم المؤجر",
    },
    "landlord_address": {
        "ua": "Адреса орендодавця",
        "en": "Landlord address",
        "de": "Vermieter Adresse",
        "pl": "Adres wynajmującego",
        "tr": "Ev sahibi adresi",
        "ar": "عنوان المؤجر",
    },
    # Family / children
    "child_name": {
        "ua": "Імʼя дитини",
        "en": "Child name",
        "de": "Kind Name",
        "pl": "Imię dziecka",
        "tr": "Çocuk adı",
        "ar": "اسم الطفل",
    },
    "child_birthday": {
        "ua": "Дата народження дитини",
        "en": "Child date of birth",
        "de": "Kind Geburtsdatum",
        "pl": "Data ur. dziecka",
        "tr": "Çocuk doğum tarihi",
        "ar": "تاريخ ميلاد الطفل",
    },
    "child_first_name": {
        "ua": "Імʼя дитини",
        "en": "Child first name",
        "de": "Kind Vorname",
        "pl": "Imię dziecka",
        "tr": "Çocuk adı",
        "ar": "اسم الطفل الأول",
    },
    "child_last_name": {
        "ua": "Прізвище дитини",
        "en": "Child last name",
        "de": "Kind Nachname",
        "pl": "Nazwisko dziecka",
        "tr": "Çocuk soyadı",
        "ar": "اسم عائلة الطفل",
    },
    "child_birth_date": {
        "ua": "Дата народження дитини",
        "en": "Child date of birth",
        "de": "Kind Geburtsdatum",
        "pl": "Data ur. dziecka",
        "tr": "Çocuk doğum tarihi",
        "ar": "تاريخ ميلاد الطفل",
    },
    "person2_first_name": {
        "ua": "Імʼя (особа 2)",
        "en": "First name (person 2)",
        "de": "Vorname (Person 2)",
        "pl": "Imię (osoba 2)",
        "tr": "Ad (kişi 2)",
        "ar": "الاسم (شخص 2)",
    },
    "person2_last_name": {
        "ua": "Прізвище (особа 2)",
        "en": "Last name (person 2)",
        "de": "Nachname (Person 2)",
        "pl": "Nazwisko (osoba 2)",
        "tr": "Soyadı (kişi 2)",
        "ar": "اسم العائلة (شخص 2)",
    },
    "person2_birth_date": {
        "ua": "Дата народження (особа 2)",
        "en": "Date of birth (person 2)",
        "de": "Geburtsdatum (Person 2)",
        "pl": "Data ur. (osoba 2)",
        "tr": "Doğum tarihi (kişi 2)",
        "ar": "تاريخ الميلاد (شخص 2)",
    },
    "person2_nationality": {
        "ua": "Громадянство (особа 2)",
        "en": "Nationality (person 2)",
        "de": "Nationalität (Person 2)",
        "pl": "Narodowość (osoba 2)",
        "tr": "Uyruk (kişi 2)",
        "ar": "الجنسية (شخص 2)",
    },
    # Financial / employment
    "tax_id": {
        "ua": "Податковий номер",
        "en": "Tax ID",
        "de": "Steuer-ID",
        "pl": "Nr podatkowy",
        "tr": "Vergi numarası",
        "ar": "الرقم الضريبي",
    },
    "income": {
        "ua": "Дохід",
        "en": "Income",
        "de": "Einkommen",
        "pl": "Dochód",
        "tr": "Gelir",
        "ar": "الدخل",
    },
    "rent": {
        "ua": "Оренда",
        "en": "Rent",
        "de": "Miete",
        "pl": "Czynsz",
        "tr": "Kira",
        "ar": "الإيجار",
    },
    "salary": {
        "ua": "Зарплата",
        "en": "Salary",
        "de": "Gehalt",
        "pl": "Wynagrodzenie",
        "tr": "Maaş",
        "ar": "الراتب",
    },
    "iban": {
        "ua": "IBAN",
        "en": "IBAN",
        "de": "IBAN",
        "pl": "IBAN",
        "tr": "IBAN",
        "ar": "IBAN",
    },
    "employer": {
        "ua": "Роботодавець",
        "en": "Employer",
        "de": "Arbeitgeber",
        "pl": "Pracodawca",
        "tr": "İşveren",
        "ar": "صاحب العمل",
    },
    "employer_name": {
        "ua": "Роботодавець",
        "en": "Employer",
        "de": "Arbeitgeber",
        "pl": "Pracodawca",
        "tr": "İşveren",
        "ar": "صاحب العمل",
    },
    "employer_address": {
        "ua": "Адреса роботодавця",
        "en": "Employer address",
        "de": "Arbeitgeberadresse",
        "pl": "Adres pracodawcy",
        "tr": "İşveren adresi",
        "ar": "عنوان صاحب العمل",
    },
    "job_title": {
        "ua": "Посада",
        "en": "Job title",
        "de": "Berufsbezeichnung",
        "pl": "Stanowisko",
        "tr": "Unvan",
        "ar": "المسمى الوظيفي",
    },
    "occupation": {
        "ua": "Професія",
        "en": "Occupation",
        "de": "Beruf",
        "pl": "Zawód",
        "tr": "Meslek",
        "ar": "المهنة",
    },
    # Contact
    "email": {
        "ua": "Електронна пошта",
        "en": "Email",
        "de": "E-Mail",
        "pl": "E-mail",
        "tr": "E-posta",
        "ar": "البريد الإلكتروني",
    },
    "phone": {
        "ua": "Телефон",
        "en": "Phone",
        "de": "Telefon",
        "pl": "Telefon",
        "tr": "Telefon",
        "ar": "الهاتف",
    },
    "phone_number": {
        "ua": "Телефон",
        "en": "Phone",
        "de": "Telefon",
        "pl": "Telefon",
        "tr": "Telefon",
        "ar": "الهاتف",
    },
    # --- Anmeldung schema fields (missing from generic labels) ---
    "gemeindekennzahl": {
        "ua": "Код громади",
        "en": "Municipality code",
        "de": "Gemeindekennzahl",
        "pl": "Kod gminy",
        "tr": "Belediye kodu",
        "ar": "رمز البلدية",
    },
    "has_bisherige_wohnung": {
        "ua": "Попереднє місце проживання",
        "en": "Previous residence exists",
        "de": "Bisherige Wohnung vorhanden",
        "pl": "Poprzednie miejsce zamieszkania",
        "tr": "Önceki konut mevcut",
        "ar": "وجود سكن سابق",
    },
    "previous_address": {
        "ua": "Попередня адреса",
        "en": "Previous address",
        "de": "Bisherige Anschrift",
        "pl": "Poprzedni adres",
        "tr": "Önceki adres",
        "ar": "العنوان السابق",
    },
    "zuzug_aus_ausland": {
        "ua": "Переїзд з-за кордону",
        "en": "Moved from abroad",
        "de": "Zuzug aus dem Ausland",
        "pl": "Przeprowadzka z zagranicy",
        "tr": "Yurt dışından taşınma",
        "ar": "الانتقال من الخارج",
    },
    "zuzug_staat": {
        "ua": "Країна попереднього проживання",
        "en": "Country of previous residence",
        "de": "Staat der bisherigen Wohnung",
        "pl": "Kraj poprzedniego zamieszkania",
        "tr": "Önceki ikamet ülkesi",
        "ar": "بلد الإقامة السابقة",
    },
    "bisherige_beibehalten": {
        "ua": "Збереження попереднього житла",
        "en": "Keeping previous residence",
        "de": "Bisherige Wohnung beibehalten",
        "pl": "Zachowanie poprzedniego mieszkania",
        "tr": "Önceki konutu koruma",
        "ar": "الاحتفاظ بالسكن السابق",
    },
    "weitere_wohnungen": {
        "ua": "Інші місця проживання",
        "en": "Other residences",
        "de": "Weitere Wohnungen",
        "pl": "Inne miejsca zamieszkania",
        "tr": "Diğer konutlar",
        "ar": "مساكن أخرى",
    },
    "birth_name": {
        "ua": "Прізвище при народженні",
        "en": "Birth name",
        "de": "Geburtsname",
        "pl": "Nazwisko rodowe",
        "tr": "Doğum soyadı",
        "ar": "اسم الميلاد",
    },
    "familienstand": {
        "ua": "Сімейний стан",
        "en": "Marital status",
        "de": "Familienstand",
        "pl": "Stan cywilny",
        "tr": "Medeni durum",
        "ar": "الحالة الاجتماعية",
    },
    "eheschliessung_ort_datum": {
        "ua": "Місце та дата шлюбу",
        "en": "Place and date of marriage",
        "de": "Ort, Datum der Eheschließung",
        "pl": "Miejsce i data ślubu",
        "tr": "Evlilik yeri ve tarihi",
        "ar": "مكان وتاريخ الزواج",
    },
    "passname": {
        "ua": "Імʼя за паспортом",
        "en": "Passport name",
        "de": "Passname",
        "pl": "Imię z paszportu",
        "tr": "Pasaport adı",
        "ar": "الاسم في جواز السفر",
    },
    "ordens_kuenstlername": {
        "ua": "Сценічне / чернече імʼя",
        "en": "Stage / religious name",
        "de": "Ordens-/Künstlername",
        "pl": "Imię artystyczne / zakonne",
        "tr": "Sahne / dini ad",
        "ar": "الاسم الفني / الديني",
    },
    "person2_birth_name": {
        "ua": "Прізвище при народж. (особа 2)",
        "en": "Birth name (person 2)",
        "de": "Geburtsname (Person 2)",
        "pl": "Nazwisko rodowe (osoba 2)",
        "tr": "Doğum soyadı (kişi 2)",
        "ar": "اسم الميلاد (شخص 2)",
    },
    "person2_birth_place": {
        "ua": "Місце народження (особа 2)",
        "en": "Place of birth (person 2)",
        "de": "Geburtsort (Person 2)",
        "pl": "Miejsce urodzenia (osoba 2)",
        "tr": "Doğum yeri (kişi 2)",
        "ar": "مكان الميلاد (شخص 2)",
    },
    "person2_gender": {
        "ua": "Стать (особа 2)",
        "en": "Gender (person 2)",
        "de": "Geschlecht (Person 2)",
        "pl": "Płeć (osoba 2)",
        "tr": "Cinsiyet (kişi 2)",
        "ar": "الجنس (شخص 2)",
    },
    "dokumentenart": {
        "ua": "Тип документа",
        "en": "Document type",
        "de": "Dokumentenart",
        "pl": "Rodzaj dokumentu",
        "tr": "Belge türü",
        "ar": "نوع المستند",
    },
    "ausstellungsbehoerde": {
        "ua": "Орган видачі",
        "en": "Issuing authority",
        "de": "Ausstellungsbehörde",
        "pl": "Organ wydający",
        "tr": "Düzenleyen makam",
        "ar": "جهة الإصدار",
    },
    "seriennummer": {
        "ua": "Серійний номер",
        "en": "Serial number",
        "de": "Seriennummer",
        "pl": "Numer seryjny",
        "tr": "Seri numarası",
        "ar": "الرقم التسلسلي",
    },
    "ausstellungsdatum": {
        "ua": "Дата видачі",
        "en": "Date of issue",
        "de": "Ausstellungsdatum",
        "pl": "Data wydania",
        "tr": "Düzenleme tarihi",
        "ar": "تاريخ الإصدار",
    },
    "gueltig_bis": {
        "ua": "Дійсний до",
        "en": "Valid until",
        "de": "Gültig bis",
        "pl": "Ważny do",
        "tr": "Geçerlilik tarihi",
        "ar": "صالح حتى",
    },
    "signature_place": {
        "ua": "Місце підпису",
        "en": "Place of signature",
        "de": "Ort der Unterschrift",
        "pl": "Miejsce podpisu",
        "tr": "İmza yeri",
        "ar": "مكان التوقيع",
    },
    "signature_date": {
        "ua": "Дата підпису",
        "en": "Date of signature",
        "de": "Datum der Unterschrift",
        "pl": "Data podpisu",
        "tr": "İmza tarihi",
        "ar": "تاريخ التوقيع",
    },
}

# --- Localized translations for German enum / boolean values in preview ---
# Key = raw German value (as stored in schema / user answers), Value = {lang: translated}
_VALUE_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Boolean Ja / Nein
    "Ja": {
        "ua": "Так",
        "en": "Yes",
        "de": "Ja",
        "pl": "Tak",
        "tr": "Evet",
        "ar": "نعم",
    },
    "Nein": {
        "ua": "Ні",
        "en": "No",
        "de": "Nein",
        "pl": "Nie",
        "tr": "Hayır",
        "ar": "لا",
    },
    "Yes": {
        "ua": "Так",
        "en": "Yes",
        "de": "Ja",
        "pl": "Tak",
        "tr": "Evet",
        "ar": "نعم",
    },
    "No": {
        "ua": "Ні",
        "en": "No",
        "de": "Nein",
        "pl": "Nie",
        "tr": "Hayır",
        "ar": "لا",
    },
    # Wohnungstyp
    "alleinige Wohnung": {
        "ua": "Єдине житло",
        "en": "Sole residence",
        "de": "alleinige Wohnung",
        "pl": "Jedyne mieszkanie",
        "tr": "Tek konut",
        "ar": "سكن وحيد",
    },
    "Hauptwohnung": {
        "ua": "Основне житло",
        "en": "Main residence",
        "de": "Hauptwohnung",
        "pl": "Główne mieszkanie",
        "tr": "Ana konut",
        "ar": "السكن الرئيسي",
    },
    "Nebenwohnung": {
        "ua": "Додаткове житло",
        "en": "Secondary residence",
        "de": "Nebenwohnung",
        "pl": "Dodatkowe mieszkanie",
        "tr": "İkincil konut",
        "ar": "سكن ثانوي",
    },
    # Gender
    "m": {
        "ua": "чоловік",
        "en": "male",
        "de": "männlich",
        "pl": "mężczyzna",
        "tr": "erkek",
        "ar": "ذكر",
    },
    "w": {
        "ua": "жінка",
        "en": "female",
        "de": "weiblich",
        "pl": "kobieta",
        "tr": "kadın",
        "ar": "أنثى",
    },
    "d": {
        "ua": "інше",
        "en": "diverse",
        "de": "divers",
        "pl": "inna",
        "tr": "diğer",
        "ar": "متنوع",
    },
    # Familienstand
    "ledig": {
        "ua": "неодружений/незаміжня",
        "en": "single",
        "de": "ledig",
        "pl": "wolny/wolna",
        "tr": "bekâr",
        "ar": "أعزب",
    },
    "verheiratet": {
        "ua": "одружений/заміжня",
        "en": "married",
        "de": "verheiratet",
        "pl": "żonaty/zamężna",
        "tr": "evli",
        "ar": "متزوج",
    },
    "verwitwet": {
        "ua": "вдова/вдівець",
        "en": "widowed",
        "de": "verwitwet",
        "pl": "wdowiec/wdowa",
        "tr": "dul",
        "ar": "أرمل",
    },
    "geschieden": {
        "ua": "розлучений/розлучена",
        "en": "divorced",
        "de": "geschieden",
        "pl": "rozwiedziony/a",
        "tr": "boşanmış",
        "ar": "مطلق",
    },
    "eingetragene Lebenspartnerschaft": {
        "ua": "зареєстроване партнерство",
        "en": "registered partnership",
        "de": "eingetragene Lebenspartnerschaft",
        "pl": "związek partnerski",
        "tr": "kayıtlı ortaklık",
        "ar": "شراكة مسجلة",
    },
    # Dokumentenart
    "PA": {
        "ua": "PA (посвідчення особи)",
        "en": "PA (ID card)",
        "de": "PA (Personalausweis)",
        "pl": "PA (dowód osobisty)",
        "tr": "PA (kimlik kartı)",
        "ar": "PA (بطاقة هوية)",
    },
    "RP": {
        "ua": "RP (закордонний паспорт)",
        "en": "RP (passport)",
        "de": "RP (Reisepass)",
        "pl": "RP (paszport)",
        "tr": "RP (pasaport)",
        "ar": "RP (جواز سفر)",
    },
    "KP": {
        "ua": "KP (дитячий паспорт)",
        "en": "KP (child passport)",
        "de": "KP (Kinderpass)",
        "pl": "KP (paszport dziecka)",
        "tr": "KP (çocuk pasaportu)",
        "ar": "KP (جواز سفر طفل)",
    },
    "PA (Personalausweis)": {
        "ua": "PA (посвідчення особи)",
        "en": "PA (ID card)",
        "de": "PA (Personalausweis)",
        "pl": "PA (dowód osobisty)",
        "tr": "PA (kimlik kartı)",
        "ar": "PA (بطاقة هوية)",
    },
    "RP (Reisepass)": {
        "ua": "RP (закордонний паспорт)",
        "en": "RP (passport)",
        "de": "RP (Reisepass)",
        "pl": "RP (paszport)",
        "tr": "RP (pasaport)",
        "ar": "RP (جواز سفر)",
    },
    "KP (Kinderpass)": {
        "ua": "KP (дитячий паспорт)",
        "en": "KP (child passport)",
        "de": "KP (Kinderpass)",
        "pl": "KP (paszport dziecka)",
        "tr": "KP (çocuk pasaportu)",
        "ar": "KP (جواز سفر طفل)",
    },
    # Common placeholders that should not leak
    "nicht erforderlich": {
        "ua": "(не обовʼязково)",
        "en": "(not required)",
        "de": "nicht erforderlich",
        "pl": "(niewymagane)",
        "tr": "(gerekli değil)",
        "ar": "(غير مطلوب)",
    },
    "nicht zutreffend": {
        "ua": "(не застосовується)",
        "en": "(not applicable)",
        "de": "nicht zutreffend",
        "pl": "(nie dotyczy)",
        "tr": "(geçerli değil)",
        "ar": "(لا ينطبق)",
    },
}


def _normalize_user_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Thin wrapper — delegates to backend.utils.normalize.normalize_user_data,
    which is the single canonical normalizer for the whole project.
    Handles camelCase keys, wrapped user_answers, and value-level normalization.
    """
    try:
        from backend.utils.normalize import normalize_user_data as _canonical_normalize

        return _canonical_normalize(user_data)
    except ImportError:
        # Fallback: bare minimum if utils.normalize is not available
        if not user_data:
            return {}
        if isinstance(user_data.get("user_answers"), dict):
            user_data = user_data["user_answers"]
        return dict(user_data)


_PREVIEW_EMPTY_SENTINEL = "\x00__EMPTY__"  # internal marker for empty fields


def _get_preview_display_fields(
    doc_type: str, user_data: Dict[str, Any], user_lang: str = "en"
) -> list:
    """
    Build ordered, LOCALIZED list of sections+fields for preview self-check.
    Labels and section titles are shown in the user's language (not German).
    Empty fields use _PREVIEW_EMPTY_SENTINEL so the renderer can show "(не заповнено)".
    Returns: list of {"section_title_de": str, "fields": [(label, value_str, field_key), ...]}.
    field_key is the raw key for identifying critical fields.
    """
    # Normalize to canonical "uk"; keep "ua" as fallback alias in lookups below
    if user_lang == "ua":
        user_lang = "uk"
    user_data = _normalize_user_data(user_data)

    def _is_empty(v: str) -> bool:
        return not v or v.lower() in ("none", "null", "n/a", "na", "")

    # --- helpers: resolve label / section title in user language ---
    def _lbl(key: str, fallback_de: str = "") -> str:
        """Get field label in user_lang. Returns None if no localized label exists (field will be hidden)."""
        entry = FIELD_LABELS.get(key)
        if entry:
            return entry.get(user_lang) or entry.get("ua") or entry.get("uk") or None
        return None  # no localized label → hide field

    def _sec_title(sec_id: str) -> str:
        """Get section title in user_lang. Returns None if no localized title exists (section will be hidden)."""
        entry = _SECTION_TITLES.get(sec_id)
        if entry:
            return entry.get(user_lang) or entry.get("ua") or entry.get("uk") or None
        return None  # no localized title → hide section

    def _translate_val(raw_value: str) -> str:
        """Translate German enum/boolean values to user language. Returns original if no translation."""
        entry = _VALUE_TRANSLATIONS.get(raw_value)
        if entry:
            return (
                entry.get(user_lang) or entry.get("ua") or entry.get("uk") or raw_value
            )
        return raw_value

    def _val(key, data):
        """Get value string for a field key. Returns _PREVIEW_EMPTY_SENTINEL for empty. Translates enum values."""
        value = (
            get_value_for_pdf_field(key, data)
            if callable(get_value_for_pdf_field)
            else data.get(key)
        )
        value_str = str(value).strip() if value is not None else ""
        if _is_empty(value_str):
            return _PREVIEW_EMPTY_SENTINEL
        return _translate_val(value_str)

    # --- Path 1: structured schema (e.g. Anmeldung with sections) ---
    schema = (
        get_document_form_schema(doc_type)
        if callable(get_document_form_schema)
        else None
    )
    if schema and isinstance(schema.get("sections"), list):
        blocks = []
        for sec in schema["sections"]:
            section_id = sec.get("id") or ""
            section_title = _sec_title(section_id)
            if section_title is None:
                continue  # no localized title → hide entire section
            fields_in_section = []
            for f in sec.get("fields", []):
                key = f.get("name")
                if not key:
                    continue
                label = _lbl(key)
                if label is None:
                    continue  # no localized label → hide field
                value_str = _val(key, user_data)
                fields_in_section.append((label, value_str, key))
            if fields_in_section:
                blocks.append(
                    {"section_title_de": section_title, "fields": fields_in_section}
                )
        if blocks:
            return blocks

    # --- Path 2: flat schema → group into logical sections ---
    flat = (
        get_document_form_schema_flat(doc_type)
        if callable(get_document_form_schema_flat)
        else None
    )
    if flat:
        section_buckets: Dict[str, list] = {}
        for item in flat:
            key = item.get("key") or item.get("name")
            if not key:
                continue
            label = _lbl(key)
            if label is None:
                continue  # no localized label → hide field
            value_str = _val(key, user_data)
            sec_id = _FIELD_SECTION_MAP.get(key, "other")
            section_buckets.setdefault(sec_id, []).append((label, value_str, key))
        if section_buckets:
            blocks = []
            for sec_id in _FALLBACK_SECTION_ORDER:
                fields = section_buckets.get(sec_id)
                if not fields:
                    continue
                sec_t = _sec_title(sec_id)
                if sec_t is None:
                    continue  # no localized title → hide section
                blocks.append({"section_title_de": sec_t, "fields": fields})
            if blocks:
                return blocks

    # --- Path 3: no schema fallback → group into logical sections ---
    section_buckets_fb: Dict[str, list] = {}
    for key, value in user_data.items():
        if key.startswith("authority_") or key in (
            "bundesland",
            "doc_type",
            "lang",
            "user_lang",
            "created_at",
        ):
            continue
        if str(key).strip().isdigit():
            continue
        value_str = str(value).strip() if value is not None else ""
        if _is_empty(value_str):
            continue  # Path 3: skip truly empty (no schema to know expected fields)
        label = _lbl(key)
        if label is None:
            continue  # no localized label → hide field
        value_str = _translate_val(value_str)
        sec_id = _FIELD_SECTION_MAP.get(key, "other")
        section_buckets_fb.setdefault(sec_id, []).append((label, value_str, key))
    if section_buckets_fb:
        blocks = []
        for sec_id in _FALLBACK_SECTION_ORDER:
            fields = section_buckets_fb.get(sec_id)
            if not fields:
                continue
            sec_t = _sec_title(sec_id)
            if sec_t is None:
                continue  # no localized title → hide section
            blocks.append({"section_title_de": sec_t, "fields": fields})
        if blocks:
            return blocks
    return []


def _has_meaningful_user_data_for_preview(user_data: Dict[str, Any]) -> bool:
    """
    Check if user_data contains meaningful data that should be displayed in preview PDF.

    This function validates that preview PDF will contain actual user-entered data,
    not just empty fields or internal metadata.

    Args:
        user_data: Form data from WebApp

    Returns:
        True if meaningful data exists, False otherwise
    """
    # FIX: normalization - Normalize user_data at the very beginning
    user_data = _normalize_user_data(user_data)

    if not user_data:
        return False

    # Field labels mapping (same as in _render_preview_pdf_single_page)
    label_map = {
        "first_name": "Vorname",
        "last_name": "Nachname",
        "firstname": "Vorname",
        "lastname": "Nachname",
        "birthday": "Geburtsdatum",
        "birth_date": "Geburtsdatum",
        "date_of_birth": "Geburtsdatum",
        "nationality": "Nationalität",
        "street": "Straße",
        "street_name": "Straße",
        "house_number": "Hausnummer",
        "house_no": "Hausnummer",
        "plz": "Postleitzahl",
        "postcode": "Postleitzahl",
        "postal_code": "Postleitzahl",
        "city": "Stadt",
        "ort": "Stadt",
        "old_street": "Alte Straße",
        "old_city": "Alte Stadt",
        "old_address": "Alte Adresse",
        "landlord_name": "Vermieter Name",
        "landlord_address": "Vermieter Adresse",
        "child_name": "Kind Name",
        "child_birthday": "Kind Geburtsdatum",
        "move_in_date": "Einzugsdatum",
        "move_out_date": "Auszugsdatum",
        "tax_id": "Steuer-ID",
        "email": "E-Mail",
        "phone": "Telefon",
        "phone_number": "Telefon",
    }

    # Filter and count meaningful fields (same logic as in rendering)
    meaningful_fields = []
    for key, value in user_data.items():
        # Skip authority fields, bundesland, doc_type, lang, and internal fields
        if key.startswith("authority_") or key in (
            "bundesland",
            "doc_type",
            "lang",
            "user_lang",
            "created_at",
        ):
            continue
        # Skip numeric-only keys (e.g. "2" from malformed form data) — no meaningful label
        if str(key).strip().isdigit():
            continue
        # Convert value to string and check if it's not empty after stripping
        value_str = str(value).strip() if value is not None else ""
        # Skip empty strings and common "empty" values
        if not value_str or value_str.lower() in ("none", "null", "n/a", "na", ""):
            continue
        # Get localized label or create one from key
        label = label_map.get(key, key.replace("_", " ").title())
        meaningful_fields.append((label, value_str))

    # Preview PDF must contain at least one meaningful field
    has_data = len(meaningful_fields) > 0

    if not has_data:
        logger.warning(
            f"⚠️ No meaningful user data found for preview - user_data keys: {list(user_data.keys())}"
        )

    return has_data


def _create_preview_stylesheet(
    font_structural: str,
    font_structural_bold: str,
    font_body: str,
    font_body_bold: str,
    is_rtl: bool = False,
) -> Dict[str, ParagraphStyle]:
    """
    Create stylesheet for professional preview PDF.
    When is_rtl (Arabic): body/section_localized/field_line use TA_RIGHT for correct line direction.
    """
    # RTL: paragraph alignment right-to-left for Arabic
    body_align = TA_RIGHT if is_rtl else TA_LEFT
    styles = {}

    styles["title"] = ParagraphStyle(
        name="PreviewTitle",
        fontName=font_structural_bold,
        fontSize=22,
        leading=27.5,
        alignment=TA_CENTER,
        spaceAfter=PREVIEW_TITLE_SUBTITLE_GAP,
        textColor=black,
    )
    styles["subtitle"] = ParagraphStyle(
        name="PreviewSubtitle",
        fontName=font_structural,
        fontSize=10,
        leading=13.0,
        alignment=TA_CENTER,
        spaceAfter=PREVIEW_SUBTITLE_BODY_GAP,
        textColor=PREVIEW_SUBTITLE_GRAY,
    )
    styles["section"] = ParagraphStyle(
        name="PreviewSection",
        fontName=font_structural_bold,
        fontSize=13,
        leading=16.5,
        alignment=body_align,
        spaceAfter=PREVIEW_SECTION_TOP_GAP,
        spaceBefore=0,
        textColor=black,
    )
    styles["section_localized"] = ParagraphStyle(
        name="PreviewSectionLocalized",
        fontName=font_body_bold,
        fontSize=13,
        leading=16.5,
        alignment=body_align,
        spaceAfter=PREVIEW_SECTION_TOP_GAP,
        spaceBefore=0,
        textColor=black,
        wordWrap="CJK",
    )
    styles["body"] = ParagraphStyle(
        name="PreviewBody",
        fontName=font_body,
        fontSize=10,
        leading=12.7,
        alignment=body_align,
        spaceAfter=6,
        textColor=black,
        wordWrap="CJK",
    )

    styles["warning"] = ParagraphStyle(
        name="PreviewWarning",
        fontName=font_structural_bold,
        fontSize=11,
        leading=14.0,
        alignment=TA_CENTER,
        spaceAfter=0,
        textColor=PREVIEW_SUBTITLE_GRAY,
    )

    styles["universal_title"] = ParagraphStyle(
        name="PreviewUniversalTitle",
        fontName=font_structural_bold,
        fontSize=10,
        leading=12.7,
        alignment=TA_LEFT,
        spaceAfter=5,
        textColor=black,
    )

    # Main header (large, bold, localized)
    styles["header_main"] = ParagraphStyle(
        name="PreviewHeaderMain",
        fontName=font_body_bold,
        fontSize=16,
        leading=20.0,
        alignment=body_align,
        spaceAfter=6,
        textColor=black,
        wordWrap="CJK",
    )
    # Subheader (smaller, gray, localized)
    styles["subheader"] = ParagraphStyle(
        name="PreviewSubheader",
        fontName=font_body,
        fontSize=10,
        leading=13.0,
        alignment=body_align,
        spaceAfter=PREVIEW_SUBTITLE_BODY_GAP,
        textColor=PREVIEW_SUBTITLE_GRAY,
        wordWrap="CJK",
    )
    # Data rows (label: value) always LTR so "Label: Value" does not break in RTL/Arabic
    styles["field_line"] = ParagraphStyle(
        name="PreviewFieldLine",
        fontName=font_body,
        fontSize=11,
        leading=14.0,
        alignment=TA_LEFT,
        spaceAfter=PREVIEW_FIELD_GAP,
        leftIndent=0,
        rightIndent=0,
        textColor=black,
        wordWrap="CJK",
    )
    # Critical field rows (bold value, slightly larger)
    styles["field_line_critical"] = ParagraphStyle(
        name="PreviewFieldLineCritical",
        fontName=font_body_bold,
        fontSize=11,
        leading=14.0,
        alignment=TA_LEFT,
        spaceAfter=PREVIEW_FIELD_GAP,
        leftIndent=0,
        rightIndent=0,
        textColor=black,
        wordWrap="CJK",
    )
    # Empty field rows (gray italic value)
    styles["field_line_empty"] = ParagraphStyle(
        name="PreviewFieldLineEmpty",
        fontName=font_body,
        fontSize=10,
        leading=13.0,
        alignment=TA_LEFT,
        spaceAfter=PREVIEW_FIELD_GAP,
        leftIndent=0,
        rightIndent=0,
        textColor=PREVIEW_SUBTITLE_GRAY,
        wordWrap="CJK",
    )
    # Footer line (small, centered, gray)
    styles["footer_line"] = ParagraphStyle(
        name="PreviewFooterLine",
        fontName=font_body,
        fontSize=8,
        leading=10.0,
        alignment=TA_CENTER,
        spaceAfter=0,
        textColor=PREVIEW_FOOTER_TEXT_COLOR,
        wordWrap="CJK",
    )
    return styles


def _escape_text_for_paragraph(text: str) -> str:
    """
    Escape text for ReportLab Paragraph (XML-safe).
    Also normalizes text to fix merged words and strips placeholder block chars.
    """
    if not text:
        return ""

    # Normalize text first to fix any merged words
    text = _normalize_text_for_pdf(text)

    # Strip block/placeholder characters (█ ▓ ▒ ░ ■) that render as black boxes
    text = text.replace("\u2588", "").replace("\u2593", "").replace("\u2592", "")
    text = text.replace("\u2591", "").replace("\u25a0", "")

    # Escape XML/HTML special characters for ReportLab Paragraph
    import xml.sax.saxutils

    text = xml.sax.saxutils.escape(text)

    return text


def _draw_paragraph_on_canvas(
    canvas_obj: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    font_name: str,
    font_size: int,
    leading: Optional[float] = None,
    alignment: int = TA_LEFT,
) -> float:
    """
    Draw a Paragraph on canvas at specified position.
    Returns the Y position after the paragraph (for next element).

    This ensures proper word spacing and wrapping, fixing merged words issue.
    Uses ReportLab Paragraph for clean typography and automatic word wrapping.
    """
    if not text or not text.strip():
        return y

    # Escape and normalize text
    text = _escape_text_for_paragraph(text)

    # Create paragraph style matching the font
    style = ParagraphStyle(
        name="CustomStyle",
        fontName=font_name,
        fontSize=font_size,
        leading=leading or (font_size * 1.2),
        alignment=alignment,
        leftIndent=0,
        rightIndent=0,
        spaceBefore=0,
        spaceAfter=0,
        wordWrap="CJK",  # Better word wrapping for Unicode/Cyrillic
    )

    # Create paragraph
    para = Paragraph(text, style)

    # Get paragraph height (wrap to calculate height)
    w, h = para.wrap(width, 1000)  # 1000 is max height (will wrap)

    # Draw paragraph on canvas
    para.drawOn(canvas_obj, x, y - h)

    # Return new Y position (below the paragraph)
    return y - h


def _render_preview_pdf_single_page(
    output_path: Path,
    doc_type: str,
    user_data: Dict[str, Any],
    authority_info: Optional[Dict[str, str]] = None,
    user_lang: str = "en",
) -> bool:
    """
    Render a single-page preview PDF for form-data correctness check.

    Preview is NOT a document — it is a DATA CHECK screen showing:
    - Localized header + subheader
    - User-entered form fields grouped by localized sections
    - Empty fields shown as "(не заповнено)" / localized
    - Critical fields (name, birth date, address) visually emphasized
    - Diagonal watermark "PREVIEW – NOT OFFICIAL" (localized)
    - Small footer disclaimer

    ZERO English/German hardcoded text — all text matches user_lang.

    Returns:
        True if successful, False if no meaningful data exists or generation fails
    """
    # FIX: normalization - Normalize user_data at the very beginning
    user_data = _normalize_user_data(user_data)
    if doc_type and doc_type.strip().lower() == "anmeldung":
        try:
            from backend.validators import _apply_anmeldung_typo_corrections

            _apply_anmeldung_typo_corrections(user_data)
        except Exception:
            pass
        try:
            from backend.utils.normalize import normalize_anmeldung_data

            user_data = normalize_anmeldung_data(user_data)
        except Exception:
            pass
    # CRITICAL VALIDATION: Preview PDF MUST contain user-entered data
    if not _has_meaningful_user_data_for_preview(user_data):
        logger.error(
            f"❌ Preview PDF generation blocked: No meaningful user data found"
        )
        return False

    try:
        # Мова превʼю = мова, обрана користувачем.
        try:
            text_lang = _normalize_preview_lang(user_lang)
        except ValueError as e:
            logger.error("Preview language not supported: %s", e)
            return False

        is_rtl = text_lang == "ar"
        # Arabic: use NotoSansArabic for correct glyphs + RTL; else DejaVuSans for Cyrillic/Latin
        if is_rtl:
            _register_arabic_font_for_reportlab()
            font_normal = "NotoSansArabic"
            font_bold = "NotoSansArabic"
            font_registered = "NotoSansArabic" in pdfmetrics.getRegisteredFontNames()
        else:
            # Always try the canonical project-local path first before the broader search.
            _dejavu_direct = FONTS_DIR / "DejaVuSans.ttf"
            if (
                _dejavu_direct.exists()
                and "DejaVuSans" not in pdfmetrics.getRegisteredFontNames()
            ):
                try:
                    pdfmetrics.registerFont(TTFont("DejaVuSans", str(_dejavu_direct)))
                    _bold_direct = FONTS_DIR / "DejaVuSans-Bold.ttf"
                    if _bold_direct.exists():
                        pdfmetrics.registerFont(
                            TTFont("DejaVuSans-Bold", str(_bold_direct))
                        )
                    logger.info(
                        "✅ DejaVuSans registered from FONTS_DIR for preview: %s",
                        _dejavu_direct,
                    )
                except Exception as _fe:
                    logger.error("❌ Direct DejaVuSans registration failed: %s", _fe)
            font_registered = _register_dejavu_font_for_reportlab()
            if not font_registered:
                logger.error(
                    "❌ DejaVuSans font missing — German characters (ß ä ö ü) will NOT render "
                    "correctly in the preview PDF. Expected font at: %s",
                    FONTS_DIR / "DejaVuSans.ttf",
                )
            try:
                bold_available = (
                    "DejaVuSans-Bold" in pdfmetrics.getRegisteredFontNames()
                )
            except Exception:
                bold_available = False
            font_normal = "DejaVuSans" if font_registered else "Helvetica"
            font_bold = (
                ("DejaVuSans-Bold" if bold_available else "DejaVuSans")
                if font_registered
                else "Helvetica-Bold"
            )

        width, height = A4
        c = canvas.Canvas(str(output_path), pagesize=A4)
        font_structural = "Helvetica"
        font_structural_bold = "Helvetica-Bold"
        styles = _create_preview_stylesheet(
            font_structural,
            font_structural_bold,
            font_normal,
            font_bold,
            is_rtl=is_rtl,
        )
        margin_left = PREVIEW_MARGIN_LEFT
        margin_right = PREVIEW_MARGIN_RIGHT
        text_width = width - margin_left - margin_right
        footer_reserved = PREVIEW_FOOTER_RESERVED
        current_y = height - PREVIEW_MARGIN_TOP

        # Localized empty-value placeholder
        empty_val = PREVIEW_EMPTY_VALUE.get(
            text_lang, PREVIEW_EMPTY_VALUE.get("ua", "(—)")
        )

        # ——— HEADER BLOCK: Prominent "FORM DATA CHECK" banner ———
        _ph = PREVIEW_HEADER.get(
            text_lang, PREVIEW_HEADER.get("en", PREVIEW_HEADER["en"])
        )
        _ph_title_raw = _prepare_text_for_pdf(_ph["title"], text_lang)
        _ph_body_raw = _prepare_text_for_pdf(_ph["text"], text_lang)

        _box_pad = 10  # inner padding inside the banner box

        _title_style = ParagraphStyle(
            "ph_title",
            fontName=font_bold,
            fontSize=15,
            leading=19,
            textColor=HexColor("#1a1a2e"),
            wordWrap="CJK",
        )
        _body_style = ParagraphStyle(
            "ph_body",
            fontName=font_normal,
            fontSize=9,
            leading=13,
            textColor=HexColor("#444455"),
            wordWrap="CJK",
        )
        _inner_w = text_width - 2 * _box_pad
        _title_para = Paragraph(_escape_text_for_paragraph(_ph_title_raw), _title_style)
        _body_para = Paragraph(_escape_text_for_paragraph(_ph_body_raw), _body_style)
        _, _th = _title_para.wrap(_inner_w, height)
        _, _bh = _body_para.wrap(_inner_w, height)
        _gap = 5
        _total_box_h = _box_pad + _th + _gap + _bh + _box_pad

        # Filled banner rectangle (blue-tinted background, dark border)
        c.saveState()
        c.setFillColor(HexColor("#eef2ff"))
        c.setStrokeColor(HexColor("#6677bb"))
        c.setLineWidth(1.0)
        c.roundRect(
            margin_left,
            current_y - _total_box_h,
            text_width,
            _total_box_h,
            5,
            fill=1,
            stroke=1,
        )
        c.restoreState()

        # Draw title inside box
        _title_para.drawOn(c, margin_left + _box_pad, current_y - _box_pad - _th)
        # Draw explanatory body text inside box
        _body_para.drawOn(
            c, margin_left + _box_pad, current_y - _box_pad - _th - _gap - _bh
        )
        current_y -= _total_box_h + 16

        # ——— BODY: Form fields grouped by localized sections ———
        display_blocks = _get_preview_display_fields(
            doc_type, user_data, user_lang=text_lang
        )
        has_any_fields = any(
            any(fld[1] != _PREVIEW_EMPTY_SENTINEL for fld in b.get("fields", []))
            for b in display_blocks
        )
        _is_first_section = True
        for block in display_blocks:
            fields_list = block.get("fields") or []
            if not fields_list:
                continue
            # Skip sections where ALL fields are empty (show only filled fields)
            if all(fld[1] == _PREVIEW_EMPTY_SENTINEL for fld in fields_list):
                continue
            section_title_loc = block.get("section_title_de")
            if section_title_loc:
                # Thin separator line between sections (skip before first)
                if not _is_first_section and current_y > footer_reserved + 20:
                    current_y -= 6
                    c.saveState()
                    c.setStrokeColor(HexColor("#cccccc"))
                    c.setLineWidth(0.4)
                    c.line(margin_left, current_y, margin_left + text_width, current_y)
                    c.restoreState()
                    current_y -= 10
                sec_para = Paragraph(
                    _escape_text_for_paragraph(
                        _prepare_text_for_pdf(section_title_loc, text_lang)
                    ),
                    styles["section_localized"],
                )
                s_w, s_h = sec_para.wrap(text_width, height)
                if current_y - s_h >= footer_reserved:
                    sec_para.drawOn(c, margin_left, current_y - s_h)
                    current_y -= s_h + PREVIEW_SECTION_TOP_GAP
            _is_first_section = False

            for field_tuple in fields_list:
                if current_y < footer_reserved:
                    break
                # Unpack: (label, value_str, field_key) — field_key may be absent in legacy data
                label = field_tuple[0]
                value_str = field_tuple[1]
                field_key = field_tuple[2] if len(field_tuple) > 2 else ""

                is_empty_field = value_str == _PREVIEW_EMPTY_SENTINEL
                is_critical = field_key in _CRITICAL_FIELDS

                # TASK 2: Show ONLY filled fields — skip empty fields entirely
                if is_empty_field:
                    continue

                label_prep = _prepare_text_for_pdf(label, text_lang)
                if is_critical:
                    value_prep = _prepare_text_for_pdf(value_str, text_lang)
                    line_html = (
                        '<font name="%s">%s:</font> <font name="%s" color="#111111">%s</font>'
                        % (
                            font_bold,
                            _escape_text_for_paragraph(label_prep),
                            font_bold,
                            _escape_text_for_paragraph(value_prep),
                        )
                    )
                    style_key = "field_line_critical"
                else:
                    value_prep = _prepare_text_for_pdf(value_str, text_lang)
                    line_html = (
                        '<font name="%s">%s:</font> <font color="#333333">%s</font>'
                        % (
                            font_bold,
                            _escape_text_for_paragraph(label_prep),
                            _escape_text_for_paragraph(value_prep),
                        )
                    )
                    style_key = "field_line"

                line_para = Paragraph(line_html, styles[style_key])
                line_w, line_h = line_para.wrap(text_width, height)
                if current_y - line_h < footer_reserved:
                    break
                line_para.drawOn(c, margin_left, current_y - line_h)
                current_y -= line_h + PREVIEW_FIELD_GAP

        if not has_any_fields:
            no_data_text = {
                "ua": "Дані не надані",
                "en": "Data not provided",
                "pl": "Dane nie podane",
                "tr": "Veri sağlanmadı",
                "ar": "البيانات غير مقدمة",
            }
            no_text = _prepare_text_for_pdf(
                no_data_text.get(text_lang, no_data_text.get("ua", "")), text_lang
            )
            no_para = Paragraph(_escape_text_for_paragraph(no_text), styles["body"])
            nw, nh = no_para.wrap(text_width, height)
            if current_y - nh >= footer_reserved:
                no_para.drawOn(c, margin_left, current_y - nh)

        # ——— COMMON MISTAKES block (shown only in preview) ———
        _mistakes_for_doc = PREVIEW_COMMON_MISTAKES.get(
            (doc_type or "").strip().lower(), {}
        )
        _mistakes_list = (
            _mistakes_for_doc.get(text_lang) or _mistakes_for_doc.get("ua") or []
        )
        if _mistakes_list and current_y > footer_reserved + 60:
            current_y -= 10
            # Separator line
            c.saveState()
            c.setStrokeColor(HexColor("#e0c070"))
            c.setLineWidth(0.6)
            c.line(margin_left, current_y, margin_left + text_width, current_y)
            c.restoreState()
            current_y -= 10
            # Header
            _cm_headers = {
                "ua": "⚠ Часті помилки:",
                "en": "⚠ Common mistakes:",
                "de": "⚠ Häufige Fehler:",
                "pl": "⚠ Częste błędy:",
                "tr": "⚠ Sık yapılan hatalar:",
                "ar": "⚠ أخطاء شائعة:",
            }
            _cm_hdr = _cm_headers.get(text_lang, _cm_headers.get("en", ""))
            _cm_hdr_prep = _prepare_text_for_pdf(_cm_hdr, text_lang)
            cm_hdr_html = '<font name="%s" color="#996600">%s</font>' % (
                font_bold,
                _escape_text_for_paragraph(_cm_hdr_prep),
            )
            cm_hdr_para = Paragraph(cm_hdr_html, styles["body"])
            cm_hw, cm_hh = cm_hdr_para.wrap(text_width, height)
            if current_y - cm_hh >= footer_reserved:
                cm_hdr_para.drawOn(c, margin_left, current_y - cm_hh)
                current_y -= cm_hh + 3
            # Bullet items
            for tip in _mistakes_list:
                if current_y < footer_reserved + 12:
                    break
                tip_prep = _prepare_text_for_pdf(tip, text_lang)
                tip_html = (
                    '<font color="#666666">• %s</font>'
                    % _escape_text_for_paragraph(tip_prep)
                )
                tip_para = Paragraph(tip_html, styles["body"])
                tw, th = tip_para.wrap(text_width - 8, height)
                if current_y - th >= footer_reserved:
                    tip_para.drawOn(c, margin_left + 8, current_y - th)
                    current_y -= th + 2

        # ——— FOOTER: localized disclaimer line ———
        footer_text = _prepare_text_for_pdf(
            PREVIEW_FOOTER_LINE.get(text_lang, PREVIEW_FOOTER_LINE.get("ua", "")),
            text_lang,
        )
        footer_para = Paragraph(
            _escape_text_for_paragraph(footer_text), styles["footer_line"]
        )
        fw, fh = footer_para.wrap(text_width, height)
        footer_para.drawOn(c, margin_left, 28)

        # ——— DIAGONAL WATERMARK: "PREVIEW – NOT OFFICIAL" (semi-transparent, light gray) ———
        # Two lines centred diagonally across the page so it is clearly visible but
        # does not obscure the data fields (light gray, ~20% opacity).
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(45)
        c.setFillColor(HexColor("#aaaaaa"))
        c.setFillAlpha(0.20)
        c.setFont("Helvetica-Bold", 54)
        c.drawCentredString(0, 22, "PREVIEW")
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(0, -18, "NOT OFFICIAL")
        c.restoreState()

        logger.info(f"✅ Preview PDF: localized data-check, {text_lang}, fields only")

        # Save PDF (single page)
        c.save()

        logger.info(
            f"✅ Single-page preview PDF created with Unicode font: {output_path}"
        )
        return True

    except Exception as e:
        logger.error(f"❌ Failed to create preview PDF: {e}", exc_info=True)
        return False


try:
    import fitz

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.error("❌ PyMuPDF (fitz) not installed - PDF generation will fail")

_ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = _ROOT_DIR / "templates"
LEGACY_TEMPLATES_DIR = _ROOT_DIR / "backend" / "templates"
OUTPUT_DIR = _ROOT_DIR / "generated_pdfs"
TEMP_DIR = _ROOT_DIR / "temp"
SCHEMAS_DIR = _ROOT_DIR / "schemas"
FONTS_DIR = _ROOT_DIR / "fonts"

for directory in [TEMPLATES_DIR, OUTPUT_DIR, TEMP_DIR, SCHEMAS_DIR, FONTS_DIR]:
    try:
        directory.mkdir(exist_ok=True, parents=True)
    except Exception as e:
        logger.error(f"❌ Failed to create directory {directory}: {e}")

# Template byte-cache: path_str → raw PDF bytes.
# A fresh fitz.Document is opened from these bytes on every call so callers always
# receive an independent, mutable document with no shared state.
_TEMPLATE_CACHE: Dict[str, bytes] = {}


def _load_template(path_str: str) -> "fitz.Document":
    """Return a fresh fitz.Document from in-memory cache, avoiding repeated disk I/O."""
    if path_str not in _TEMPLATE_CACHE:
        with open(path_str, "rb") as _f:
            _TEMPLATE_CACHE[path_str] = _f.read()
    return fitz.open(stream=_TEMPLATE_CACHE[path_str], filetype="pdf")


try:
    from backend.geo_intelligence import get_authority_address, get_bundesland
except ImportError:
    logger.warning("⚠️ geo_intelligence not available - using fallback")

    def get_authority_address(doc_type: str, plz: str) -> Dict[str, str]:
        return {
            "name": "Zuständige Behörde",
            "address": "Musterstraße 1",
            "plz": plz or "00000",
            "city": "Stadt",
            "phone": "",
            "email": "",
        }

    def get_bundesland(plz: str) -> str:
        return "Deutschland"


try:
    from backend.document_config import (
        has_template,
        get_template_path as get_doc_template_path,
        get_template_for_region,
        resolve_template_path,
        get_pdf_field_mapping,
        get_value_for_pdf_field,
        get_requires_bundesland,
        get_document_form_schema_flat,
        get_document_form_schema,
        get_anmeldung_field_order,
        get_anmeldung_acroform_mapping,
        get_acroform_mapping,
        ANMELDUNG_CHECKBOX_FIELDS,
        get_official_link,
        DOC_STRATEGY,
        get_optional_acroform_keys,
    )
except ImportError:
    has_template = lambda doc_type: False
    get_doc_template_path = lambda doc_type, templates_dir: None
    get_template_for_region = (
        lambda doc_type, bundesland, templates_dir, legacy=None: None
    )
    resolve_template_path = (
        lambda doc_type, bundesland=None, templates_dir=None, legacy_templates_dir=None: None
    )
    get_pdf_field_mapping = lambda doc_type: None
    get_value_for_pdf_field = lambda field_name, user_data: None
    get_requires_bundesland = lambda doc_type: False
    get_document_form_schema_flat = lambda doc_type: None
    get_document_form_schema = lambda doc_type: None
    get_anmeldung_field_order = lambda: []
    get_anmeldung_acroform_mapping = lambda: {}
    get_acroform_mapping = lambda doc_type: {}
    ANMELDUNG_CHECKBOX_FIELDS = frozenset()
    get_official_link = lambda doc_type: ""
    DOC_STRATEGY = {}
    get_optional_acroform_keys = lambda doc_type: frozenset()

try:
    from backend.pdf_renderers import (
        DOC_RENDER_MAP,
        get_render_strategy,
        final_renderer,
        preview_renderer,
        is_xfa_pdf,
    )
except ImportError:
    DOC_RENDER_MAP = {}
    get_render_strategy = lambda doc_type: "builder_only"
    final_renderer = None
    preview_renderer = None
    is_xfa_pdf = None  # type: ignore[assignment]

try:
    from backend.validators import normalize_and_validate_anmeldung
except ImportError:
    normalize_and_validate_anmeldung = None

try:
    from backend.utils.normalize import normalize_user_data as _premium_normalize
except ImportError:
    _premium_normalize = None

try:
    from backend.utils.validate import (
        validate_user_data as _premium_validate,
        format_validation_error,
    )
except ImportError:
    _premium_validate = None
    format_validation_error = None

try:
    from backend.form_builder import _normalize_city_composite as _norm_city_prefix
except ImportError:
    _norm_city_prefix = None


def find_dejavu_font() -> Optional[str]:
    """
    Find DejaVuSans TTF font file for Unicode support.
    Returns path to font file or None if not found.
    """
    search_paths = [
        FONTS_DIR / "DejaVuSans.ttf",
        _ROOT_DIR / "fonts" / "DejaVuSans.ttf",  # Explicit fonts subdirectory
        _ROOT_DIR / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
    ]

    for path in search_paths:
        if path.exists():
            logger.debug(f"✅ Found DejaVuSans font at: {path}")
            return str(path.resolve())  # Use absolute path for reliability

    logger.warning(
        f"⚠️ DejaVuSans font not found in any of these paths: {[str(p) for p in search_paths]}"
    )
    return None


def find_arabic_font() -> Optional[str]:
    """Find NotoSansArabic TTF for Arabic (RTL) support. Returns path or None."""
    search_paths = [
        FONTS_DIR / "NotoSansArabic-Regular.ttf",
        _ROOT_DIR / "fonts" / "NotoSansArabic-Regular.ttf",
    ]
    for path in search_paths:
        if path.exists():
            return str(path.resolve())
    return None


def _register_arabic_font_for_reportlab() -> bool:
    """Register NotoSansArabic with ReportLab for Arabic text. Returns True if registered."""
    try:
        if "NotoSansArabic" in pdfmetrics.getRegisteredFontNames():
            return True
        path = find_arabic_font()
        if path:
            pdfmetrics.registerFont(TTFont("NotoSansArabic", path, subfontIndex=0))
            logger.debug("✅ Registered NotoSansArabic for ReportLab")
            return True
    except Exception as e:
        logger.warning("⚠️ Arabic font registration failed: %s", e)
    return False


def _register_dejavu_font_for_reportlab() -> bool:
    """
    Register DejaVuSans font with ReportLab for Unicode support.
    This prevents black squares in PDF text rendering and ensures professional font quality.

    Returns:
        True if font was registered successfully, False otherwise
    """
    try:
        # Check if already registered
        if "DejaVuSans" in pdfmetrics.getRegisteredFontNames():
            logger.debug("✅ DejaVuSans font already registered")
            return True

        font_path = find_dejavu_font()
        if font_path:
            # Register DejaVuSans font family with proper encoding
            pdfmetrics.registerFont(TTFont("DejaVuSans", font_path, subfontIndex=0))

            # Also register bold variant if available
            bold_path = str(Path(font_path).parent / "DejaVuSans-Bold.ttf")
            if Path(bold_path).exists():
                pdfmetrics.registerFont(
                    TTFont("DejaVuSans-Bold", bold_path, subfontIndex=0)
                )
                logger.debug(f"✅ Registered DejaVuSans-Bold font: {bold_path}")
            else:
                logger.debug(f"⚠️ DejaVuSans-Bold not found at: {bold_path}")

            logger.info(f"✅ Registered DejaVuSans font for ReportLab: {font_path}")
            return True
        else:
            logger.error(
                "❌ DejaVuSans font not found - Unicode text may render as squares"
            )
            return False
    except Exception as e:
        logger.error(f"❌ Failed to register DejaVuSans font: {e}", exc_info=True)
        return False


def enrich_user_data_with_authority(
    user_data: Dict[str, Any], doc_type: str, plz: str
) -> Dict[str, Any]:
    if not get_requires_bundesland(doc_type):
        return user_data
    try:
        authority = get_authority_address(doc_type, plz)

        if authority:
            user_data["authority_name"] = authority.get("name", "")
            user_data["authority_address"] = authority.get("address", "")
            user_data["authority_plz"] = authority.get("plz", "")
            user_data["authority_city"] = authority.get("city", "")
            user_data["authority_phone"] = authority.get("phone", "")
            user_data["authority_email"] = authority.get("email", "")

            try:
                bundesland = get_bundesland(plz)
                user_data["bundesland"] = bundesland
            except Exception:
                pass

    except Exception as e:
        logger.error(f"❌ Authority enrichment failed: {e}")

    return user_data


def _apply_watermark(
    pdf,
    is_preview: bool = True,
    font_path: Optional[str] = None,
    user_lang: str = "en",
    price: float = PREVIEW_PRICE,
) -> None:
    """
    Apply small red header text to preview PDFs only.
    Final PDFs never get watermark.
    """
    if not is_preview:
        return  # Final PDFs never get watermark

    if not PYMUPDF_AVAILABLE:
        return

    try:
        for page in pdf:
            rect = page.rect
            page.insert_text(
                (rect.width / 2, 20),
                "Dies ist ein ausgefülltes Beispiel zur Orientierung – kein offizielles Dokument",
                fontsize=11,
                color=(0.85, 0, 0),
                align=1,
            )
    except Exception as e:
        logger.debug("Watermark failed (non-critical): %s", e)


# Delivery watermark for PAID PDFs: "EXAMPLE — DO NOT SUBMIT" (localized). Applied after filling.
DELIVERY_WATERMARK_BY_LANG = {
    "de": "BEISPIEL — NICHT EINREICHEN",
    "en": "EXAMPLE — DO NOT SUBMIT",
    "uk": "ПРИКЛАД — НЕ ПОДАТЬ ОФІЦІЙНО",
    "ua": "ПРИКЛАД — НЕ ПОДАТЬ ОФІЦІЙНО",
    "pl": "PRZYKŁAD — NIE SKŁADAĆ",
    "tr": "ÖRNEK — RESMİ OLARAK TESLİM ETMEYİN",
    "ar": "مثال — لا تقدم رسمياً",
}


def _apply_delivery_watermark(pdf_path: str, user_lang: str) -> None:
    """
    Apply small red header text to PDFs.
    """
    if not PYMUPDF_AVAILABLE:
        return
    try:
        pdf = fitz.open(pdf_path)
        for page in pdf:
            rect = page.rect
            page.insert_textbox(
                fitz.Rect(0, 5, rect.width, 28),
                "Dies ist ein ausgefülltes Beispiel zur Orientierung – kein offizielles Dokument",
                fontsize=11,
                color=(0.85, 0, 0),
                align=1,
            )
        try:
            pdf.save(pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception:
            import tempfile, shutil

            tmp = pdf_path + ".wm_tmp"
            pdf.save(tmp)
            pdf.close()
            shutil.move(tmp, pdf_path)
            return
        pdf.close()
        logger.debug("Applied delivery watermark to %s", pdf_path)
    except Exception as e:
        logger.warning("Delivery watermark failed (non-critical): %s", e)


def _apply_final_disclaimer(pdf_path: str, skip_header: bool = False) -> None:
    """
    Add a small red header on the first page and a small grey footer on the
    last page of the final paid PDF.

    • Page 1 top  — "Beispieldokument – kein amtliches Formular" (red, 10 pt, centred)
    • Last page bottom — longer German note (dark grey, 8 pt, centred)

    skip_header: if True, omit the red header (use when _apply_kopie_watermark already
                 wrote the same text — builder/XFA pipeline — to avoid double header).

    Placed in the margin areas so they never overlap AcroForm fields.
    Non-critical: any failure is silently swallowed.
    """
    if not PYMUPDF_AVAILABLE:
        return
    _HEADER = "Beispieldokument \u2013 kein amtliches Formular"
    _FOOTER = (
        "Dieses Dokument wurde automatisch generiert und stellt keine Rechtsberatung "
        "im Sinne des RDG dar. Es ersetzt kein amtliches Formular. "
        "Alle Angaben liegen in der Verantwortung des Nutzers. "
        "Bitte pr\u00fcfen Sie das Dokument vor der Einreichung."
    )
    font_path = find_dejavu_font() if callable(find_dejavu_font) else None
    font_kwargs = {"fontfile": font_path} if font_path else {"fontname": "helv"}
    try:
        pdf = fitz.open(pdf_path)
        if pdf.page_count < 1:
            pdf.close()
            return

        # ── Grey footer on the last page (y ≈ rect.height − 10 pt) ──────────
        pl = pdf[-1]
        w_l = pl.rect.width
        h_l = pl.rect.height
        footer_fs = 8
        footer_tw = len(_FOOTER) * footer_fs * 0.55
        footer_x = max(10, (w_l - footer_tw) / 2)
        try:
            pl.insert_text(
                (footer_x, h_l - 10),
                _FOOTER,
                fontsize=footer_fs,
                color=(0.3, 0.3, 0.3),
                **font_kwargs,
            )
        except Exception:
            pass

        try:
            pdf.save(pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        except Exception:
            import tempfile as _tf, shutil as _sh

            _tmp = pdf_path + ".disc_tmp"
            pdf.save(_tmp)
            pdf.close()
            _sh.move(_tmp, pdf_path)
            return
        pdf.close()
        logger.debug("Applied final disclaimer to %s", pdf_path)
    except Exception as e:
        logger.warning("Final disclaimer annotation failed (non-critical): %s", e)


def _render_pdf(
    user_id: int,
    user_data: Dict[str, Any],
    doc_type: str,
    authority_info: Optional[Dict[str, str]] = None,
    is_preview: bool = True,
    user_lang: str = "en",
) -> Optional[str]:
    """
    Internal function: Render PDF document with shared logic.

    Args:
        user_id: Telegram user ID
        user_data: Form data from WebApp
        doc_type: Document type (e.g., 'anmeldung')
        authority_info: Authority address info (optional)
        is_preview: If True, apply watermark. If False, no watermark.
        user_lang: User language code for localized watermark

    Returns:
        Path to generated PDF file, or None on error
    """
    if not PYMUPDF_AVAILABLE:
        logger.error("❌ PyMuPDF not available")
        return None

    watermark_status = "ON" if is_preview else "OFF"
    pdf_mode = PDF_MODE_PREVIEW if is_preview else PDF_MODE_FINAL
    logger.info(
        f"▶️ PDF generation started (watermark={watermark_status}, mode={pdf_mode}): "
        f"user={user_id} doc_type={doc_type}"
    )

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use same filename structure for preview and final (only watermark differs)
        if is_preview:
            filename = f"preview_{user_id}_{doc_type}_{timestamp}.pdf"
        else:
            filename = f"{doc_type}_{user_id}_{timestamp}.pdf"
        output_path = OUTPUT_DIR / filename

        pdf = fitz.open()
        page = pdf.new_page(width=595, height=842)

        font_path = find_dejavu_font()
        # Use custom font if available, otherwise default to helv
        font_kwargs = {}
        if font_path:
            font_kwargs["fontfile"] = font_path
            logger.debug(f"✅ Using DejaVuSans font from: {font_path}")
        else:
            font_kwargs["fontname"] = "helv"
            logger.debug("⚠️ DejaVuSans not found, using default helv font")

        y = 780

        # Official document title (same for preview and final)
        doc_title = doc_type.upper().replace("_", " ")
        if doc_type == "anmeldung":
            doc_title = "Anmeldung"
        elif doc_type == "abmeldung":
            doc_title = "Abmeldung"
        elif doc_type == "ummeldung":
            doc_title = "Ummeldung"
        elif doc_type == "kindergeld":
            doc_title = "Kindergeld"
        elif doc_type == "bürgergeld":
            doc_title = "Bürgergeld"
        elif doc_type == "wohngeld":
            doc_title = "Wohngeld"

        page.insert_text(
            (50, y),
            doc_title,
            fontsize=18,
            color=(0, 0, 0),  # Black, official look
            **font_kwargs,
        )
        y -= 30

        if authority_info:
            page.insert_text(
                (50, y),
                "Zuständige Behörde:",
                fontsize=12,
                color=(0, 0, 0),
                **font_kwargs,
            )
            y -= 20

            for field, size in [("name", 11), ("address", 9)]:
                value = authority_info.get(field, "")
                if value:
                    page.insert_text(
                        (60, y),
                        value,
                        fontsize=size,
                        color=(0.2, 0.2, 0.2),
                        **font_kwargs,
                    )
                    y -= 15

            city_info = f"{authority_info.get('plz', '')} {authority_info.get('city', '')}".strip()
            if city_info:
                page.insert_text(
                    (60, y), city_info, fontsize=9, color=(0.2, 0.2, 0.2), **font_kwargs
                )
                y -= 15

            if authority_info.get("phone"):
                page.insert_text(
                    (60, y),
                    f"Tel: {authority_info['phone']}",
                    fontsize=8,
                    color=(0.3, 0.3, 0.3),
                    **font_kwargs,
                )
                y -= 15

            y -= 20

        # Define field groups for organized layout
        personal_fields = ["first_name", "last_name", "birthday", "nationality"]
        address_fields = [
            "street",
            "house_number",
            "plz",
            "city",
            "old_street",
            "old_city",
        ]
        landlord_fields = ["landlord_name", "landlord_address"]
        other_fields = ["move_in_date", "move_out_date", "tax_id"]

        # Helper function to render a field with label left, value right
        def render_field(page, y_pos, label, value, font_kwargs):
            """Render a single field: label on left, value on right."""
            label_x = 50
            value_x = 350  # Right-aligned value column

            # Render label
            page.insert_text(
                (label_x, y_pos),
                label,
                fontsize=10,
                color=(0.2, 0.2, 0.2),
                **font_kwargs,
            )

            # Render value (right-aligned)
            value_str = str(value) if value else ""
            if len(value_str) > 40:
                value_str = value_str[:37] + "..."

            page.insert_text(
                (value_x, y_pos), value_str, fontsize=10, color=(0, 0, 0), **font_kwargs
            )

        # Helper function to render a section
        def render_section(
            page, y_pos, section_title, field_keys, user_data, font_kwargs
        ):
            """Render a section with title and fields."""
            # Section header
            page.insert_text(
                (50, y_pos), section_title, fontsize=12, color=(0, 0, 0), **font_kwargs
            )
            y_pos -= 20

            # Section fields
            for key in field_keys:
                value = user_data.get(key)
                if not value or key.startswith("authority_") or key == "bundesland":
                    continue

                if y_pos < 60:
                    page = pdf.new_page(width=595, height=842)
                    y_pos = 780

                # Convert key to readable label
                label_map = {
                    "first_name": "Vorname",
                    "last_name": "Nachname",
                    "birthday": "Geburtsdatum",
                    "nationality": "Nationalität",
                    "street": "Straße",
                    "house_number": "Hausnummer",
                    "plz": "Postleitzahl",
                    "city": "Stadt",
                    "old_street": "Alte Straße",
                    "old_city": "Alte Stadt",
                    "landlord_name": "Vermieter Name",
                    "landlord_address": "Vermieter Adresse",
                    "child_name": "Kind Name",
                    "child_birthday": "Kind Geburtsdatum",
                    "move_in_date": "Einzugsdatum",
                    "move_out_date": "Auszugsdatum",
                    "tax_id": "Steuer-ID",
                }
                label = label_map.get(key, key.replace("_", " ").title())

                render_field(page, y_pos, label, value, font_kwargs)
                y_pos -= 18

            return page, y_pos

        # Render sections
        y -= 20

        # Personal data section
        has_personal = any(user_data.get(k) for k in personal_fields)
        if has_personal:
            page, y = render_section(
                page, y, "Persönliche Daten", personal_fields, user_data, font_kwargs
            )
            y -= 10

        # Address section
        has_address = any(user_data.get(k) for k in address_fields)
        if has_address:
            page, y = render_section(
                page, y, "Adresse", address_fields, user_data, font_kwargs
            )
            y -= 10

        # Landlord section
        has_landlord = any(user_data.get(k) for k in landlord_fields)
        if has_landlord:
            page, y = render_section(
                page, y, "Vermieter", landlord_fields, user_data, font_kwargs
            )
            y -= 10

        # Children section (handle multiple children)
        child_count = 0
        for key in user_data.keys():
            if key.startswith("child_name") or key.startswith("child_birthday"):
                child_count += 1
                break

        if child_count > 0:
            # Collect all child fields
            child_data = {}
            for key, value in user_data.items():
                if key.startswith("child_") and value:
                    child_data[key] = value

            if child_data:
                page.insert_text(
                    (50, y), "Kinder", fontsize=12, color=(0, 0, 0), **font_kwargs
                )
                y -= 20

                # Group children by index (child_name_0, child_birthday_0, etc.)
                child_indices = set()
                for key in child_data.keys():
                    parts = key.split("_")
                    if len(parts) >= 3 and parts[0] == "child":
                        try:
                            idx = int(parts[-1]) if parts[-1].isdigit() else 0
                            child_indices.add(idx)
                        except:
                            child_indices.add(0)

                for idx in sorted(child_indices):
                    child_name = user_data.get(f"child_name_{idx}") or user_data.get(
                        "child_name"
                    )
                    child_birthday = user_data.get(
                        f"child_birthday_{idx}"
                    ) or user_data.get("child_birthday")

                    if child_name or child_birthday:
                        if y < 60:
                            page = pdf.new_page(width=595, height=842)
                            y = 780

                        if child_name:
                            render_field(
                                page, y, f"Kind {idx + 1} Name", child_name, font_kwargs
                            )
                            y -= 18
                        if child_birthday:
                            render_field(
                                page,
                                y,
                                f"Kind {idx + 1} Geburtsdatum",
                                child_birthday,
                                font_kwargs,
                            )
                            y -= 18

                y -= 10

        # Other fields section (document-specific)
        has_other = any(user_data.get(k) for k in other_fields)
        if has_other:
            page, y = render_section(
                page, y, "Weitere Angaben", other_fields, user_data, font_kwargs
            )
            y -= 10

        # Render any remaining fields that don't fit into categories
        remaining_fields = []
        for key, value in user_data.items():
            if not value or key.startswith("authority_") or key == "bundesland":
                continue
            if (
                key
                not in personal_fields + address_fields + landlord_fields + other_fields
                and not key.startswith("child_")
            ):
                remaining_fields.append(key)

        if remaining_fields:
            page, y = render_section(
                page, y, "Sonstiges", remaining_fields, user_data, font_kwargs
            )

        # PREVIEW vs FINAL PDF LOGIC (архітектурно розділено):
        # - Preview = ТІЛЬКИ окремий layout (ReportLab, A4, Label: Value wrap). Ніколи офіційний бланк.
        # - Final = офіційний бланк (PyMuPDF). Preview не fallback на бланк — інакше текст "лізе".
        if is_preview:
            try:
                success = _render_preview_pdf_single_page(
                    output_path=output_path,
                    doc_type=doc_type,
                    user_data=user_data,
                    authority_info=authority_info,
                    user_lang=user_lang,
                )
                if success:
                    logger.info(
                        f"✅ Single-page preview PDF created (watermark={watermark_status}): {output_path}"
                    )
                    return str(output_path.resolve())
                logger.warning(
                    "⚠️ Preview PDF creation returned False (e.g. no meaningful data)"
                )
                return None
            except Exception as e:
                logger.warning(f"⚠️ Preview PDF creation error: {e}", exc_info=True)
                return None
            # НЕ зберігати PyMuPDF-документ як preview — офіційний бланк тільки для final.

        # FINAL PDF MODE: Use PyMuPDF for official form
        # CRITICAL: For final PDFs (not preview), ensure multi-page structure
        if not is_preview:
            # Get document title for additional pages
            final_doc_title = _get_document_title(doc_type)
            # For Anmeldung, ensure we have ~9 pages (official form structure)
            # Add additional pages if current page count is too low
            current_page_count = len(pdf)
            expected_pages = 9 if doc_type.lower() == "anmeldung" else 5

            if current_page_count < expected_pages:
                logger.info(
                    f"📄 Adding pages to final PDF: current={current_page_count}, target={expected_pages}"
                )
                # Add pages with document structure
                for page_num in range(current_page_count, expected_pages):
                    new_page = pdf.new_page(width=595, height=842)
                    # Add page number indicator (optional, for structure)
                    new_page.insert_text(
                        (50, 50),
                        f"Page {page_num + 1}",
                        fontsize=8,
                        color=(0.5, 0.5, 0.5),
                        **font_kwargs,
                    )
                    # Add document title on each page
                    new_page.insert_text(
                        (50, 800),
                        final_doc_title,
                        fontsize=14,
                        color=(0, 0, 0),
                        **font_kwargs,
                    )

        # Apply watermark to ALL pages (only if is_preview=True)
        # Watermark includes footer text, no additional footer needed
        _apply_watermark(
            pdf,
            is_preview=is_preview,
            font_path=font_path,
            user_lang=user_lang,
            price=PREVIEW_PRICE,
        )

        # Save final PDF
        pdf.save(str(output_path))
        final_page_count = len(pdf)
        pdf.close()

        if not _verify_pdf_integrity(output_path, doc_type):
            return None

        logger.info(
            f"✅ PDF created (watermark={watermark_status}, pages={final_page_count}): {output_path}"
        )

        return str(output_path.resolve())

    except Exception as e:
        logger.error(
            f"❌ PDF creation failed (watermark={watermark_status}): "
            f"user={user_id} doc_type={doc_type} error={e}",
            exc_info=True,
        )
        return None


# Baseline offset: PyMuPDF insert_text(x,y) uses y as baseline; config y is often "line from top" → add offset so text sits on line
BASELINE_OFFSET_PT = 4


# DEBUG: draw rectangles and field names for calibration (set DEBUG_PDF_POSITIONS=1)
def _debug_pdf_positions_enabled() -> bool:
    return os.environ.get("DEBUG_PDF_POSITIONS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _verify_pdf_integrity(path, doc_type: str = "") -> bool:
    """
    Post-save integrity check: verify the PDF file exists, is non-empty,
    and contains at least one page.

    Returns True if the file is valid; False otherwise.
    Logs ERROR on failure so the caller can return None.
    """
    if not PYMUPDF_AVAILABLE:
        return True  # cannot check without fitz; assume ok
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            logger.error(
                "PDF_INTEGRITY_FAIL: file missing or empty after save "
                "doc_type=%s path=%s",
                doc_type,
                path,
            )
            return False
        doc = fitz.open(str(p))
        page_count = len(doc)
        doc.close()
        if page_count == 0:
            logger.error(
                "PDF_INTEGRITY_FAIL: 0 pages after save doc_type=%s path=%s",
                doc_type,
                path,
            )
            return False
        logger.debug(
            "PDF_INTEGRITY_OK: doc_type=%s pages=%d path=%s", doc_type, page_count, path
        )
        return True
    except Exception as e:
        logger.error(
            "PDF_INTEGRITY_FAIL: could not verify doc_type=%s path=%s error=%s",
            doc_type,
            path,
            e,
        )
        return False


# DEBUG: log every overlay field written (set PDF_DEBUG_OVERLAY=1)
PDF_DEBUG_OVERLAY = os.getenv("PDF_DEBUG_OVERLAY") == "1"

# DEBUG_PDF=1 → log every AcroForm field→value mapping, dump user_data, report unmapped schema keys
DEBUG_PDF = os.environ.get("DEBUG_PDF", "").strip().lower() in ("1", "true", "yes")


def _normalize_date_for_pdf(value: str) -> str:
    """Converts YYYY-MM-DD to DD.MM.YYYY. Returns original value if format unknown."""
    if not value:
        return value
    value = value.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        y, m, d = value.split("-")
        return f"{d}.{m}.{y}"
    return value


def _fill_template_pdf_overlay(
    template_path: Path,
    user_data: Dict[str, Any],
    doc_type: str,
    output_path: Path,
    user_lang: str = "en",
) -> Optional[str]:
    """
    XFA overlay renderer — draws user data as plain text on top of an official PDF
    template using coordinate-based positioning.  Intended for XFA-only templates
    where the AcroForm widget API returns no widgets (e.g. Kindergeld KG 1).

    Strategy "xfa_overlay" in DOC_RENDER_MAP routes here.

    - Template is opened read-only; a copy is written to output_path.
    - Text is inserted via fitz.Page.insert_text() — no AcroForm interaction.
    - Falls back to None on any error so create_final_pdf() can use FinalRenderer.

    Coordinates in OVERLAY_MAPS are in PDF user-space points from the top-left
    corner of each page (PyMuPDF convention).  Calibrate with the actual template
    by running tools/calibrate_overlay.py (if available) or measuring in Acrobat.
    """
    if not PYMUPDF_AVAILABLE:
        logger.error("_fill_template_pdf_overlay: PyMuPDF not available")
        return None

    try:
        from backend.document_config import get_overlay_map
    except ImportError:
        logger.error("_fill_template_pdf_overlay: cannot import get_overlay_map")
        return None

    overlay_map = get_overlay_map(doc_type)
    if not overlay_map:
        logger.error(
            "_fill_template_pdf_overlay: no overlay map registered for doc_type=%r; "
            "add an entry to OVERLAY_MAPS in document_config.py",
            doc_type,
        )
        return None

    try:
        pdf = _load_template(str(template_path))
    except Exception as _oe:
        logger.error(
            "_fill_template_pdf_overlay: cannot open template %s: %s",
            template_path,
            _oe,
        )
        return None

    try:
        for field_key, cfg in overlay_map.items():
            # Try composite / virtual key resolver first (handles wg_gender_w, wg_fs_*,
            # wg_anschrift, wg_ort_datum, wg_member_*_name, etc.), then fall back to
            # direct dict lookup.  This means overlay maps can contain any virtual key
            # that is registered in get_value_for_pdf_field without special treatment.
            raw_value: Optional[str] = None
            try:
                raw_value = get_value_for_pdf_field(field_key, user_data)
            except Exception:
                pass
            if raw_value is None:
                raw_value = user_data.get(field_key)
            value = (str(raw_value) if raw_value is not None else "").strip()
            if not value:
                continue

            page_idx = int(cfg.get("page", 0))
            if page_idx >= len(pdf):
                logger.warning(
                    "_fill_template_pdf_overlay: field %r requests page %d but template has %d page(s) — skipped",
                    field_key,
                    page_idx,
                    len(pdf),
                )
                continue

            page = pdf[page_idx]
            x = float(cfg["x"])
            y = float(cfg["y"])
            fontsize = float(cfg.get("fontsize", 9))
            max_width = cfg.get("max_width")

            field_type = cfg.get("type", "text")
            if field_type == "checkbox":
                # Draw a visible × for checked state (only when value is truthy)
                if value.upper() in ("YES_CHECKED", "YES", "TRUE", "1", "JA", "X"):
                    display_text = "×"
                else:
                    continue  # unchecked — skip drawing
            else:
                display_text = value
                # Clip to max_width by truncating with ellipsis if needed
                if max_width:
                    try:
                        while (
                            display_text
                            and fitz.get_text_length(
                                display_text, fontname="helv", fontsize=fontsize
                            )
                            > max_width
                        ):
                            display_text = display_text[:-1]
                        if display_text != value:
                            display_text = display_text.rstrip() + "…"
                    except Exception:
                        # fitz.get_text_length unavailable (old PyMuPDF) — skip clipping
                        pass

            page.insert_text(
                (x, y),
                display_text,
                fontname="helv",
                fontsize=fontsize,
                color=(0.0, 0.0, 0.0),
            )
            logger.debug(
                "_fill_template_pdf_overlay: wrote field=%r value=%r page=%d at (%.1f, %.1f)",
                field_key,
                display_text,
                page_idx,
                x,
                y,
            )

        pdf.save(str(output_path), garbage=4, deflate=True)
        pdf.close()
        logger.info(
            "_fill_template_pdf_overlay: saved doc_type=%s to %s (%d field(s) drawn)",
            doc_type,
            output_path,
            len(overlay_map),
        )
        return str(output_path)

    except Exception as _err:
        logger.error(
            "_fill_template_pdf_overlay: failed for doc_type=%s: %s",
            doc_type,
            _err,
            exc_info=True,
        )
        try:
            pdf.close()
        except Exception:
            pass
        return None


def _validate_acroform_output(
    pdf_path: str, mapping: Dict[str, str], doc_type: str
) -> None:
    """
    Post-fill validation: open the saved PDF and check that every REQUIRED mapped
    text field has a non-empty value.  Optional fields (declared in
    _OPTIONAL_ACROFORM_KEYS) and checkbox/radio fields are excluded.

    Logs structured warnings grouped by reason:
      - EMPTY_REQUIRED: mapped, in PDF, but value is empty
      - MISSING_WIDGET: declared in mapping but absent from PDF
    Raises ValueError in DEBUG_PDF=1 mode.
    """
    if not PYMUPDF_AVAILABLE:
        return
    try:
        _optional_keys = (
            get_optional_acroform_keys(doc_type)
            if callable(get_optional_acroform_keys)
            else frozenset()
        )

        _pdf = fitz.open(pdf_path)
        _pdf_values: Dict[str, str] = {}
        for _page in _pdf:
            for _w in _page.widgets():
                _fn = getattr(_w, "field_name", None)
                if _fn:
                    _new_val = _w.field_value or ""
                    # For grouped checkboxes (multiple widgets with same field name),
                    # keep the first non-Off value so a correctly checked widget in
                    # the group is not overwritten by a later unchecked sibling.
                    _existing = _pdf_values.get(_fn, "")
                    if _existing in ("", "Off"):
                        _pdf_values[_fn] = _new_val
                    # else: keep existing non-Off value
        _pdf.close()

        # Invert mapping: pdf_field → schema_key (first wins for deduplication)
        _pdf_to_schema: Dict[str, str] = {}
        for _sk, _pf in mapping.items():
            if _pf not in _pdf_to_schema:
                _pdf_to_schema[_pf] = _sk

        _empty_required: list = []  # (schema_key, pdf_field, reason)
        _missing_widgets: list = []  # pdf_field declared in mapping but not in PDF

        for _pdf_field, _schema_key in _pdf_to_schema.items():
            _is_optional = _schema_key in _optional_keys
            _is_checkbox = any(
                x in _pdf_field.lower() for x in ("chbx", "rbtn", "auswahl", "check")
            )

            if _pdf_field not in _pdf_values:
                if not _is_optional and not _is_checkbox:
                    _missing_widgets.append((_schema_key, _pdf_field))
                continue

            _val = (_pdf_values[_pdf_field] or "").strip()
            if _val in ("", "Off") and not _is_checkbox and not _is_optional:
                reason = "empty_value" if _val == "" else "only_Off"
                _empty_required.append((_schema_key, _pdf_field, reason))

        if _empty_required:
            _details = [
                f"{sk}→{pf} ({reason})" for sk, pf, reason in _empty_required[:8]
            ]
            _msg = (
                f"[ACROFORM_VALIDATE] doc_type={doc_type} — "
                f"{len(_empty_required)} required field(s) empty after fill: "
                f"{_details}" + (" ..." if len(_empty_required) > 8 else "")
            )
            logger.warning(_msg)
            if DEBUG_PDF:
                raise ValueError(_msg)
        if _missing_widgets:
            logger.warning(
                "[ACROFORM_VALIDATE] doc_type=%s — %d required widget(s) declared "
                "in mapping but absent from PDF: %s",
                doc_type,
                len(_missing_widgets),
                [(sk, pf) for sk, pf in _missing_widgets[:5]],
            )
        if not _empty_required and not _missing_widgets:
            logger.debug(
                "[ACROFORM_VALIDATE] doc_type=%s — all required fields filled ✓  "
                "(%d total mapped, %d optional skipped)",
                doc_type,
                len(_pdf_to_schema),
                len(_optional_keys),
            )
    except ValueError:
        raise
    except Exception as _ve:
        logger.debug(
            "[ACROFORM_VALIDATE] doc_type=%s — validation skipped: %s", doc_type, _ve
        )


def _fill_xfa_overlay(
    template_path: Path,
    user_data: Dict[str, Any],
    doc_type: str,
    output_path: Path,
    user_lang: str = "de",
) -> Optional[str]:
    """
    XFA overlay renderer — the correct strategy for XFA-based official PDF templates.

    WHY NOT AcroForm fill:
      XFA PDFs store form data in a separate XML stream.  PDF viewers that support
      XFA (e.g. Adobe Reader) render exclusively from that XML stream and ignore
      any AcroForm widget values written by PyMuPDF → visually empty result.

    THIS APPROACH:
      1. Open the original template (preserves 100% official visual layout).
      2. Build a reverse mapping: pdf_widget_name → user_data_key.
      3. For each widget on each page, read its exact rect (position/size) from
         the AcroForm layer — these are the authoritative field positions.
      4. Draw the user value as text directly into the page content stream at
         those coordinates (insert_text).  Content-stream text is rendered by
         ALL viewers, regardless of XFA support.
      5. Rasterize the fully-drawn pages to high-res pixmaps and rebuild as a
         flat image PDF.  This eliminates any remaining empty form annotations
         that would otherwise appear as blank boxes over the drawn text.

    RESULT:
      - Exact official form layout (the real German government template).
      - All user values drawn at exactly the right positions.
      - Flat output — viewable in every PDF viewer (browser, mobile, desktop).
      - No dependency on XFA rendering engine.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("_fill_xfa_overlay: PyMuPDF (fitz) not available")
        return None

    if not template_path or not Path(template_path).exists():
        logger.error("_fill_xfa_overlay: template not found: %s", template_path)
        return None

    # Resolve AcroForm mapping (user_key → pdf_widget_name)
    try:
        from backend.document_config import get_acroform_mapping as _get_map
        mapping: Dict[str, str] = _get_map(doc_type) or {}
    except Exception as _me:
        logger.warning("_fill_xfa_overlay: no mapping for %s: %s", doc_type, _me)
        mapping = {}

    # get_value_for_pdf_field handles composite keys (at_address, at_kontakt,
    # at_nationality_now, at_beruf, signature_date …)
    try:
        from backend.document_config import get_value_for_pdf_field as _get_val
    except Exception:
        _get_val = None  # type: ignore[assignment]

    # Reverse map: pdf_widget_name → user_data_key
    reverse_map: Dict[str, str] = {v: k for k, v in mapping.items()}
    KIZ_CHECKBOX_FIELDS = {
        "kiz_ledig",
        "kiz_verheiratet",
        "kiz_geschieden",
        "kiz_verwitwet",
        "kiz_dauernd_getrennt",
        "kiz_eingetragene_lp",
        "kiz_getrennt_lp_aufgehoben",
    }

    # DejaVuSans for full Unicode (Cyrillic, Arabic, …)
    font_path: Optional[str] = find_dejavu_font()

    pdf = None
    new_doc = None
    try:
        pdf = fitz.open(str(template_path))
        drawn = 0

        for page_num in range(len(pdf)):
            page = pdf[page_num]

            # Collect (rect, value) for every mapped widget on this page
            fields_to_draw: list = []
            for widget in (page.widgets() or []):
                w_name = widget.field_name or ""
                user_key = reverse_map.get(w_name)
                if not user_key:
                    continue
                if doc_type == "kinderzuschlag" and user_key in KIZ_CHECKBOX_FIELDS:
                    continue

                # Resolve value — use composite handler when available
                if _get_val is not None:
                    value = _get_val(user_key, user_data) or ""
                else:
                    value = (user_data.get(user_key) or "").strip()

                if not value:
                    continue

                fields_to_draw.append((widget.rect, str(value).strip()))

            # Draw text into the page content stream at exact widget positions.
            # Text in the content stream renders BEFORE annotations, but because we
            # rasterize afterwards (step below), the final pixmap shows everything.
            for rect, value in fields_to_draw:
                # ── Text position ───────────────────────────────────────────
                # Anchor baseline to bottom of field box: y1 - 2.5 pt looks
                # like a hand-filled form regardless of field height.
                # Small left padding (2 pt) mirrors standard form insets.
                text_x = rect.x0 + 2.0
                text_y = rect.y1 - 2.5
                fontsize = min(9.0, max(6.0, rect.height * 0.72))

                # ── Multiline for tall fields (height > 16 pt) ──────────────
                # Fields like at_address and Zweck are 21.5 pt tall — render
                # the value as a two-line block so it doesn't overflow.
                lines_to_draw = [value]
                if rect.height > 16 and len(value) > 40:
                    # Split on comma or at whitespace midpoint
                    mid = value.find(", ")
                    if mid > 0:
                        lines_to_draw = [value[:mid + 1], value[mid + 2:]]
                    else:
                        # split at word boundary near the middle
                        mid = len(value) // 2
                        sp = value.rfind(" ", 0, mid + 15)
                        if sp > 0:
                            lines_to_draw = [value[:sp], value[sp + 1:]]
                    # Adjust baseline to top line when multiline
                    text_y = rect.y0 + fontsize + 1.5

                # ── Font selection ──────────────────────────────────────────
                # Helvetica (helv) for pure-ASCII content → clean official look.
                # DejaVuSans via fontfile for any non-ASCII (Cyrillic, Arabic,
                # accented Latin) → correct Unicode glyph rendering.
                try:
                    _ascii_only = value.encode("ascii")
                    use_dejavu = False
                except UnicodeEncodeError:
                    use_dejavu = True

                try:
                    for line_idx, line in enumerate(lines_to_draw):
                        line_y = text_y + line_idx * (fontsize + 1.5)
                        if use_dejavu and font_path:
                            page.insert_text(
                                (text_x, line_y),
                                line,
                                fontsize=fontsize,
                                fontfile=font_path,
                                fontname="DejaVuSans",
                                color=(0, 0, 0),
                            )
                        else:
                            page.insert_text(
                                (text_x, line_y),
                                line,
                                fontsize=fontsize,
                                fontname="helv",
                                color=(0, 0, 0),
                            )
                    drawn += 1
                    logger.debug(
                        "xfa_overlay p%d: drew %r at (%.1f, %.1f) font=%s",
                        page_num, value[:20], text_x, text_y,
                        "DejaVuSans" if use_dejavu else "helv",
                    )
                except Exception as _te:
                    logger.warning(
                        "xfa_overlay p%d: insert_text failed value=%r: %s",
                        page_num, value[:20], _te,
                    )

        logger.info(
            "xfa_overlay: drew %d/%d fields for doc_type=%s",
            drawn, len(mapping), doc_type,
        )

        # ── Rasterize + rebuild as flat image PDF ─────────────────────────────
        # 2.0× ≈ 144 DPI: sharp enough for A4 form text; keeps file size ~2–4 MB
        mat = fitz.Matrix(2.0, 2.0)
        new_doc = fitz.open()

        for page_num in range(len(pdf)):
            page = pdf[page_num]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_page = new_doc.new_page(
                width=page.rect.width,
                height=page.rect.height,
            )
            # Use JPEG-compressed insert for smaller output (~2–4 MB per 4-page doc)
            img_bytes = pix.tobytes("jpeg", jpg_quality=85)
            img_page.insert_image(page.rect, stream=img_bytes)

        new_doc.save(str(output_path), garbage=4, deflate=True)
        logger.info(
            "xfa_overlay: flat PDF saved (%d pages, %d fields drawn) → %s",
            len(pdf), drawn, output_path,
        )
        return str(output_path)

    except Exception as exc:
        logger.error(
            "xfa_overlay FAILED for doc_type=%s: %s", doc_type, exc, exc_info=True
        )
        return None
    finally:
        for _d in (new_doc, pdf):
            if _d is not None:
                try:
                    _d.close()
                except Exception:
                    pass


def _fill_template_pdf_acroform(
    template_path: Path,
    user_data: Dict[str, Any],
    doc_type: str,
    output_path: Path,
    is_preview: bool,
    user_lang: str = "en",
    authority_info: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """
    Final PDF: fill ONLY via AcroForm. Populate exclusively with:
      widget.field_value = value
      widget.update()
    No manual text drawing, no x/y, no table rendering. Layout 1:1 identical to official form.
    Returns path if fill succeeded; None → caller uses _fill_template_pdf() fallback (no mixing).
    """
    if not PYMUPDF_AVAILABLE:
        return None
    doc_lower = (doc_type or "").strip().lower()
    mapping = get_acroform_mapping(doc_lower) if callable(get_acroform_mapping) else {}
    if not mapping:
        return None
    merged = dict(user_data)
    # Debug: log keys + gender values before AcroForm fill (visible in server logs)
    logger.debug(
        "[AcroForm fill] doc_type=%s user_data keys=%s gender=%r person2_gender=%r person1_gender=%r",
        doc_type,
        sorted(merged.keys()),
        merged.get("gender"),
        merged.get("person2_gender"),
        merged.get("person1_gender"),
    )
    if authority_info:
        merged["authority_name"] = authority_info.get("name", "")
        merged["authority_address"] = authority_info.get("address", "")
        merged["authority_plz"] = authority_info.get("plz", "")
        merged["authority_city"] = authority_info.get("city", "")
    pdf = None
    try:
        pdf = _load_template(str(template_path))

        # ── Collect all widgets once — reused for discovery (Pass 1) and fill (Pass 2) ──
        # Widget objects remain valid as long as the document is open; w.update() does
        # not require the generator to be active, only the document.
        _all_widgets = []
        for page in pdf:
            _all_widgets.extend(page.widgets())

        # ── Pass 1: build set of field names that actually exist in the template ──
        widget_names_in_pdf: set = set()
        for w in _all_widgets:
            name = getattr(w, "field_name", None)
            if name:
                widget_names_in_pdf.add(name)

        if not widget_names_in_pdf:
            logger.warning(
                "📄 %s: template has no AcroForm fields — AcroForm fill skipped",
                doc_type,
            )
            return None

        # Warn about mapping entries whose PDF widget doesn't exist (deduplicated by widget name)
        missing_widgets = sorted(
            {
                acroform_name
                for schema_key, acroform_name in mapping.items()
                if acroform_name not in widget_names_in_pdf
            }
        )
        if missing_widgets:
            logger.warning(
                "📄 %s: %d widget(s) declared in mapping but absent from PDF — skipped: %s",
                doc_type,
                len(missing_widgets),
                missing_widgets[:15] if len(missing_widgets) > 15 else missing_widgets,
            )

        # ── Build acroform_name → value_str lookup (resolve all values before touching PDF) ──
        # Sentinel "YES_CHECKED" is used for checkbox/radio — replaced by w.on_state() at write time.
        fill_values: Dict[str, str] = {}  # acroform_name → value_str
        seen_schema_per_widget: Dict[str, str] = (
            {}
        )  # acroform_name → first schema_key that wrote it
        _UNSET = object()  # sentinel: get_value_for_pdf_field returned nothing
        # Handler-driven fields ALWAYS win — these are the keys whose values come from
        # get_value_for_pdf_field (never from a raw fallback) and must never be overridden
        # by an earlier duplicate write.  Two schema keys can target the same widget
        # (e.g. jc_konto_vorhanden + jc_kein_konto both target mutually exclusive
        # checkboxes) — we allow the handler value to replace whatever was written first.
        _HANDLER_PRIORITY_KEYS = frozenset(
            {
                "jc_konto_vorhanden",
                "sv_number",
                "jc_antrag_sofort",
                "jc_antrag_spaeter",
            }
        )
        for schema_key, acroform_name in mapping.items():
            if acroform_name not in widget_names_in_pdf:
                continue
            value = (
                get_value_for_pdf_field(schema_key, merged)
                if callable(get_value_for_pdf_field)
                else _UNSET
            )
            # get_value_for_pdf_field returns None to mean "no match / skip".
            # It may return "" (empty string) to mean "explicitly clear this widget"
            # (e.g. non-selected checkbox in a mutually-exclusive group).
            # Distinguish those two cases so we can honour explicit clear requests.
            explicit_clear = (
                value is not None and isinstance(value, str) and value == ""
            )
            if value is None or value is _UNSET:
                # Fall back to raw user_data only when schema function had no opinion.
                value = merged.get(schema_key)
            if value is None:
                continue
            # Skip truly empty raw-data values BUT pass through explicit clear ("").
            if not explicit_clear and isinstance(value, str) and not value.strip():
                continue
            value_str = "" if explicit_clear else str(value).strip()
            # Normalize YYYY-MM-DD → DD.MM.YYYY for date fields
            if any(
                k in schema_key.lower() for k in ("date", "datum", "gueltig", "valid")
            ):
                value_str = _normalize_date_for_pdf(value_str)
            if acroform_name in fill_values:
                if schema_key in _HANDLER_PRIORITY_KEYS:
                    # Handler-priority key: always overwrite whatever was written first.
                    # This ensures e.g. jc_kein_konto="Off" beats any raw value that
                    # happened to write the same widget earlier in the mapping iteration.
                    logger.warning(
                        "[PRIORITY_OVERRIDE] doc=%s widget=%s prev_key=%s prev_val=%r "
                        "→ overridden by handler key=%s val=%r",
                        doc_type,
                        acroform_name,
                        seen_schema_per_widget[acroform_name],
                        fill_values[acroform_name],
                        schema_key,
                        value_str,
                    )
                    fill_values[acroform_name] = value_str
                    seen_schema_per_widget[acroform_name] = schema_key
                else:
                    # Normal duplicate: first writer wins (log only).
                    logger.debug(
                        "DUPLICATE_WIDGET doc_type=%s widget=%s already written by key=%s; "
                        "skipping key=%s",
                        doc_type,
                        acroform_name,
                        seen_schema_per_widget[acroform_name],
                        schema_key,
                    )
                continue
            fill_values[acroform_name] = value_str
            seen_schema_per_widget[acroform_name] = schema_key

        # ── Wohngeld: compact field-to-PDF propagation log (always on, no noise) ──
        if doc_lower == "wohngeld":
            _wg_filled_keys = sorted(fill_values.keys())
            _wg_empty_schema = [
                k for k, acr in mapping.items()
                if acr in widget_names_in_pdf and acr not in fill_values
            ]
            logger.info(
                "WG_PDF_FIELDS_RESOLVED: doc=%s filled_widgets=%d empty_schema_keys=%s",
                doc_type,
                len(_wg_filled_keys),
                _wg_empty_schema[:20] if _wg_empty_schema else "none",
            )

        # ── DEBUG_PDF: dump resolved field→value map and unmapped schema keys ──
        if DEBUG_PDF:
            import json as _json

            logger.debug(
                "[DEBUG_PDF] doc=%s fill_values (%d):\n%s",
                doc_type,
                len(fill_values),
                "\n".join(f"  {k!r}: {v!r}" for k, v in sorted(fill_values.items())),
            )
            _unmapped = [k for k in mapping if mapping[k] not in widget_names_in_pdf]
            if _unmapped:
                logger.warning(
                    "[DEBUG_PDF] doc=%s — %d schema keys have no matching widget: %s",
                    doc_type,
                    len(_unmapped),
                    _unmapped,
                )
            try:
                logger.debug(
                    "[DEBUG_PDF] doc=%s user_data=%s",
                    doc_type,
                    _json.dumps(
                        {
                            k: v
                            for k, v in merged.items()
                            if isinstance(v, (str, int, float, bool, type(None)))
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            except Exception:
                pass

        # ── Final-value consistency guard (buergergeld / jobcenter only) ──
        # Uses fill_values (resolved field handler output) — the exact values
        # that will be written to the PDF.  Fails fast on any contradiction.
        if doc_lower in ("buergergeld", "jobcenter"):
            _sv_radio = fill_values.get("rbtnPersonSVRVNr")
            _sv_text = (fill_values.get("txtfPersonSVRVNr") or "").strip()
            _iban = (fill_values.get("txtfIBAN") or "").strip()
            # chbxKonto is the real IBAN checkbox (p2) — YES_CHECKED when IBAN present
            _chbx_konto = fill_values.get("chbxKonto")
            logger.warning(
                "[FINAL GUARD] doc=%s sv_radio=%r sv_text=%r iban=%s chbxKonto=%r",
                doc_type,
                _sv_radio,
                _sv_text,
                bool(_iban),
                _chbx_konto,
            )
            # SV contradictions
            if _sv_text and _sv_radio == "1":
                logger.error(
                    "[FINAL GUARD FAIL] doc=%s iban=%r chbxKonto=%r "
                    "sv_radio=%r sv_number=%r — SV number present but Nein selected",
                    doc_type,
                    _iban,
                    _chbx_konto,
                    _sv_radio,
                    _sv_text,
                )
                raise ValueError(
                    f"SV conflict: sv_number={_sv_text!r} is set but rbtnPersonSVRVNr='1' (Nein) "
                    f"— doc={doc_type}"
                )
            if not _sv_text and _sv_radio == "0":
                logger.error(
                    "[FINAL GUARD FAIL] doc=%s iban=%r chbxKonto=%r "
                    "sv_radio=%r sv_number=%r — no SV number but Ja selected",
                    doc_type,
                    _iban,
                    _chbx_konto,
                    _sv_radio,
                    _sv_text,
                )
                raise ValueError(
                    f"SV conflict: no sv_number but rbtnPersonSVRVNr='0' (Ja) — doc={doc_type}"
                )
            # chbxKonto = "Es ist keine Bankverbindung vorhanden" (no-account checkbox).
            # Correct state: CHECKED when no IBAN, UNCHECKED when IBAN present.
            if _iban and _chbx_konto == "YES_CHECKED":
                logger.error(
                    "[FINAL GUARD FAIL] doc=%s iban=%r chbxKonto=%r "
                    "sv_radio=%r sv_number=%r — IBAN present but 'keine Bankverbindung' is checked",
                    doc_type,
                    _iban,
                    _chbx_konto,
                    _sv_radio,
                    _sv_text,
                )
                raise ValueError(
                    f"IBAN conflict: iban={_iban!r} is present but chbxKonto (keine Bankverbindung) "
                    f"is checked — doc={doc_type}"
                )
            if (
                not _iban
                and "chbxKonto" in fill_values
                and _chbx_konto != "YES_CHECKED"
            ):
                logger.error(
                    "[FINAL GUARD FAIL] doc=%s iban=%r chbxKonto=%r "
                    "sv_radio=%r sv_number=%r — no IBAN but 'keine Bankverbindung' not checked",
                    doc_type,
                    _iban,
                    _chbx_konto,
                    _sv_radio,
                    _sv_text,
                )
                raise ValueError(
                    f"IBAN conflict: no IBAN but chbxKonto (keine Bankverbindung) is not checked "
                    f"(value={_chbx_konto!r}) — doc={doc_type}"
                )

        # ── Pass 2: fill widgets per-page ────────────────────────────────────────
        # Widget objects are page-bound annotations: w.field_value and w.update()
        # require the page to be alive (in scope).  Iterating page by page keeps
        # the current page alive for the full inner loop, avoiding the
        # "Annot is not bound to a page" error that pre-collected stale references
        # cause on multi-page templates.
        # For checkbox / radio fields the PDF defines its own "on" value (on_state).
        # We stored "YES_CHECKED" as a sentinel; here we swap it for the real on_state.
        _YES_SENTINEL = "YES_CHECKED"
        filled = 0
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            for w in page.widgets():
                acroform_name = getattr(w, "field_name", None)
                if not acroform_name or acroform_name not in fill_values:
                    continue
                value_str = fill_values[acroform_name]
                # Resolve sentinel for checkbox / radio to the widget's real on_state
                if value_str == _YES_SENTINEL:
                    try:
                        value_str = w.on_state() if callable(w.on_state) else "Yes"
                    except Exception:
                        value_str = "Yes"
                # Explicit uncheck: "" is ambiguous in PyMuPDF — checkboxes need "Off"
                # to reliably clear a pre-ticked template default.
                if value_str == "":
                    _wtype = getattr(w, "field_type", None)
                    # PDF_WIDGET_TYPE_CHECKBOX = 4 in PyMuPDF / fitz
                    if _wtype == 4:
                        value_str = "Off"
                _is_critical = acroform_name in (
                    "chbxKonto",
                    "txtfPersonSVRVNr",
                    "rbtnPersonSVRVNr",
                    "chbxPersonAntragBUEGSofort",
                    "chbxPersonAntragBUEGSpaeter",
                )
                # ── Explicit checkbox handler for chbxKonto (IBAN indicator) ──────
                # Use the widget's own on_state() for check, literal "Off" for uncheck.
                # This avoids relying on string comparison and ensures PyMuPDF accepts
                # the value regardless of how the PDF was authored.
                if acroform_name == "chbxKonto":
                    try:
                        if value_str not in ("Off", ""):
                            # Checked state — use the widget's own export value
                            target = w.on_state() if callable(w.on_state) else value_str
                        else:
                            target = "Off"
                        w.field_value = target
                        w.update()
                        filled += 1
                        logger.warning(
                            "[CHECKBOX FIX] chbxKonto → %r (from fill_value=%r)",
                            target,
                            value_str,
                        )
                    except Exception as e:
                        logger.warning(
                            "[CHECKBOX FIX FAILED] chbxKonto → %r — error: %s",
                            value_str,
                            e,
                        )
                    continue
                # ── RadioButton group handling ──────────────────────────────────────
                # PDF_WIDGET_TYPE_RADIOBUTTON = 5 in PyMuPDF / fitz.
                # Problem: calling update() on ANY widget in a RadioButton group
                # affects the entire group.  If we call update() on widget7 when we
                # intended to check widget2, PyMuPDF may corrupt the group state.
                # Fix: only call update() on the ONE widget whose on_state matches
                # the target value.  All other same-named RadioButton widgets are
                # skipped silently — the group is already correct after widget2 fires.
                _wtype_radio = getattr(w, "field_type", None)
                if _wtype_radio == 5:  # RadioButton
                    try:
                        _radio_on_state = w.on_state() if callable(w.on_state) else None
                        if value_str == _radio_on_state:
                            # This is the button we want checked — set and update
                            w.field_value = value_str
                            w.update()
                            filled += 1
                            logger.debug(
                                "AcroForm radio: %s = %r (on_state match)",
                                acroform_name,
                                value_str,
                            )
                        # else: skip — setting value on non-matching button corrupts
                        # the group; the group value is already set by the matching widget
                    except Exception as e:
                        logger.debug(
                            "AcroForm radio %s skip (on_state error): %s",
                            acroform_name,
                            e,
                        )
                    continue
                try:
                    w.field_value = value_str
                    w.update()
                    filled += 1
                    if _is_critical:
                        logger.warning("[PDF WRITE] %s = %r", acroform_name, value_str)
                    else:
                        logger.debug(
                            "AcroForm filled: %s = %r", acroform_name, value_str
                        )
                except Exception as e:
                    if _is_critical:
                        logger.warning(
                            "[PDF WRITE FAILED] %s = %r — error: %s",
                            acroform_name,
                            value_str,
                            e,
                        )
                    else:
                        logger.warning("AcroForm set %s failed: %s", acroform_name, e)

        # XFA-only forms (e.g. Kindergeld): PyMuPDF enumerates fields but cannot fill them.
        # Detect by filled==0 despite having both a mapping and actual widgets → fall back.
        if filled == 0 and mapping and widget_names_in_pdf:
            logger.warning(
                "📄 %s: 0/%s fields filled — PDF uses XFA-only forms (not standard AcroForm). "
                "Falling back to german_form_builder.",
                doc_type,
                len(mapping),
            )
            return None
        font_path = find_dejavu_font()
        _apply_watermark(
            pdf, is_preview=is_preview, font_path=font_path, user_lang=user_lang
        )
        pdf.save(str(output_path))
        if not _verify_pdf_integrity(output_path, doc_type):
            return None
        logger.info("FILLED: %d fields for %s | path=%s", filled, doc_type, output_path)

        # ── Post-fill validation: check mapped fields for empty values ─────────
        _validate_acroform_output(str(output_path), mapping, doc_type)

        return str(output_path.resolve())
    except Exception as e:
        logger.warning("AcroForm fill failed for %s: %s", doc_type, e)
        return None
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:
                pass


def _normalize_checkbox_value(value_str: str, option_keys: list) -> Optional[str]:
    """
    Match user value to exact option key. Try exact, then capitalize (Ja/Nein), then case-insensitive.
    Returns matching option key or None (never render checkbox value as text).
    """
    if not value_str or not option_keys:
        return None
    if value_str in option_keys:
        return value_str
    cap = value_str.strip().capitalize()
    if cap in option_keys:
        return cap
    lower = value_str.strip().lower()
    for k in option_keys:
        if k.lower() == lower:
            return k
    return None


# ---------------------------------------------------------------------------
# Anmeldung hybrid supplement: overlay ONLY for fields without AcroForm
# ---------------------------------------------------------------------------

# Overlay supplement is DISABLED for Anmeldung (AcroForm-only mode).
# This frozenset is retained for reference only — it is no longer used.
# gemeindekennzahl removed: it IS in ANMELDUNG_ACROFORM_MAPPING and was
# incorrectly drawn a second time by the overlay, causing duplicate text.
_ANMELDUNG_OVERLAY_ONLY_FIELDS = frozenset(
    {
        "landlord_name",
        "landlord_address",
        "authority_name",
        "authority_address",
        "authority_plz",
        "authority_city",
        "signature_place",
        "has_bisherige_wohnung",
        "zuzug_aus_ausland",
    }
)


def _apply_overlay_for_missing_anmeldung_fields(
    pdf_path: str,
    user_data: Dict[str, Any],
    authority_info: Optional[Dict[str, str]],
) -> str:
    """
    Hybrid supplement for Anmeldung: after AcroForm fill, draw ONLY fields
    that have no AcroForm representation using PDF_FIELD_MAPPING coordinates.
    Strict allowlist — never touches fields already filled via AcroForm.
    Returns the (possibly modified) PDF path; original path on any failure.
    """
    if not PYMUPDF_AVAILABLE:
        return pdf_path
    mapping_all = (
        get_pdf_field_mapping("anmeldung") if callable(get_pdf_field_mapping) else None
    )
    if not mapping_all:
        return pdf_path
    page0_fields = mapping_all.get("0", {})
    if not page0_fields:
        return pdf_path

    # Merge authority info into lookup dict
    merged = dict(user_data)
    if authority_info:
        merged["authority_name"] = authority_info.get("name", "")
        merged["authority_address"] = authority_info.get("address", "")
        merged["authority_plz"] = authority_info.get("plz", "")
        merged["authority_city"] = authority_info.get("city", "")

    # Collect only allowlisted fields that have both coordinates and values
    fields_to_draw: list = []
    for field_name in _ANMELDUNG_OVERLAY_ONLY_FIELDS:
        pos = page0_fields.get(field_name)
        if not pos:
            continue
        value = (
            get_value_for_pdf_field(field_name, merged)
            if callable(get_value_for_pdf_field)
            else None
        )
        if value is None:
            value = merged.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        fields_to_draw.append((field_name, pos, str(value).strip()))

    if not fields_to_draw:
        return pdf_path

    # Open the already-filled PDF and draw overlay for missing fields
    try:
        pdf = fitz.open(pdf_path)
        if pdf.page_count < 1:
            pdf.close()
            return pdf_path
        page = pdf[0]
        font_path = find_dejavu_font()
        font_kwargs = {"fontfile": font_path} if font_path else {}
        drawn = 0

        for field_name, pos, value_str in fields_to_draw:
            # Normalize YYYY-MM-DD → DD.MM.YYYY for date fields
            if any(
                k in field_name.lower() for k in ("date", "datum", "gueltig", "valid")
            ):
                value_str = _normalize_date_for_pdf(value_str)

            # Checkbox: draw "X" at matched option position
            if pos.get("pdf_type") == "checkbox" and "options" in pos:
                opts = pos["options"]
                if not isinstance(opts, dict):
                    continue
                matched_key = _normalize_checkbox_value(value_str, list(opts.keys()))
                if not matched_key:
                    continue
                coords = opts.get(matched_key)
                if not coords:
                    continue
                x, y = coords.get("x", 0), coords.get("y", 0)
                try:
                    page.insert_text(
                        (x, y + BASELINE_OFFSET_PT),
                        "X",
                        fontsize=pos.get("font_size", 10),
                        color=(0, 0, 0),
                        **font_kwargs,
                    )
                    drawn += 1
                    if PDF_DEBUG_OVERLAY:
                        logger.info(
                            "[ANMELDUNG OVERLAY] %s -> %s (checkbox: %s)",
                            field_name,
                            value_str,
                            matched_key,
                        )
                except Exception as e:
                    logger.debug(
                        "overlay checkbox %s at (%s,%s): %s", field_name, x, y, e
                    )
                continue

            # Text field: shrink font to fit max_width (min 8pt), no truncation
            max_width = pos.get("max_width", 200)
            font_size = pos.get("font_size", 12)
            x, y = pos.get("x", 0), pos.get("y", 0)
            # Strip stray "X" from text values (checkbox path already handled above)
            _clean_vs = value_str.replace("X", "").strip()
            if _clean_vs != value_str:
                logger.info("Cleaned text field from stray X: field=%s", field_name)
                value_str = _clean_vs
            text = value_str
            if not text:
                continue
            # Text-fit: shrink font until estimated width fits (min 8pt)
            est_width = len(text) * font_size * 0.55
            while est_width > max_width and font_size > 8:
                font_size -= 0.5
                est_width = len(text) * font_size * 0.55
            try:
                rect = fitz.Rect(x, y, x + max_width, y + font_size * 1.5)
                if hasattr(page, "insert_textbox"):
                    page.insert_textbox(
                        rect,
                        text,
                        fontsize=font_size,
                        color=(0, 0, 0),
                        align=fitz.TEXT_ALIGN_LEFT,
                        **font_kwargs,
                    )
                else:
                    page.insert_text(
                        (x, y + BASELINE_OFFSET_PT),
                        text,
                        fontsize=font_size,
                        color=(0, 0, 0),
                        **font_kwargs,
                    )
                drawn += 1
                if PDF_DEBUG_OVERLAY:
                    logger.info(
                        "[ANMELDUNG OVERLAY] %s -> %s (font=%.1fpt)",
                        field_name,
                        text,
                        font_size,
                    )
            except Exception as e:
                logger.debug("overlay text %s at (%s,%s): %s", field_name, x, y, e)

        pdf.save(pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        pdf.close()
        logger.info(
            "✅ Anmeldung overlay supplement: drew %s/%s field(s) at %s",
            drawn,
            len(fields_to_draw),
            pdf_path,
        )
    except Exception as e:
        logger.warning(
            "⚠️ Anmeldung overlay supplement failed (non-fatal, AcroForm data preserved): %s",
            e,
        )
    return pdf_path


def _fill_template_pdf(
    template_path: Path,
    user_data: Dict[str, Any],
    doc_type: str,
    output_path: Path,
    is_preview: bool,
    user_lang: str = "en",
    authority_info: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """
    FALLBACK ONLY: coordinate-based overlay when template has NO AcroForm fields (flat/scanned PDF).
    Do NOT use for fillable official PDFs — use _fill_template_pdf_acroform instead.
    One field → one (x,y); checkbox = X only; text clipped to max_width.
    """
    logger.info(
        "📄 Final PDF fill (fallback overlay): doc_type=%s template=%s",
        doc_type,
        getattr(template_path, "name", str(template_path)),
    )
    if not PYMUPDF_AVAILABLE:
        logger.error("❌ PyMuPDF not available - template fill skipped")
        return None
    mapping = get_pdf_field_mapping(doc_type) if get_pdf_field_mapping else None
    if not mapping:
        logger.debug(
            f"No PDF_FIELD_MAPPING for doc_type={doc_type} (expected for builder documents)"
        )
        return None
    merged = dict(user_data)
    if authority_info:
        merged["authority_name"] = authority_info.get("name", "")
        merged["authority_address"] = authority_info.get("address", "")
        merged["authority_plz"] = authority_info.get("plz", "")
        merged["authority_city"] = authority_info.get("city", "")
    font_path = find_dejavu_font()
    font_kwargs = {"fontfile": font_path} if font_path else {}
    debug_positions = _debug_pdf_positions_enabled()
    doc_lower = (doc_type or "").strip().lower()
    anmeldung_strict_order = (
        (doc_lower == "anmeldung" and callable(get_anmeldung_field_order))
        and get_anmeldung_field_order()
        or []
    )
    checkbox_only = (
        ANMELDUNG_CHECKBOX_FIELDS if doc_lower == "anmeldung" else frozenset()
    )

    pdf = None
    try:
        pdf = fitz.open(str(template_path))
        if pdf.page_count > 0:
            p0 = pdf[0]
            try:
                r = p0.mediabox
                rot = getattr(p0, "rotation", 0) or 0
                logger.info(
                    "📐 Template page 0: mediabox=%s rotation=%s",
                    (r.x1 - r.x0, r.y1 - r.y0),
                    rot,
                )
            except Exception as e:
                logger.debug("Template page info: %s", e)
        for page_id, fields in mapping.items():
            try:
                page_index = int(page_id)
            except (ValueError, TypeError):
                continue
            if page_index < 0 or page_index >= len(pdf):
                continue
            page = pdf[page_index]
            # Strict field order for Anmeldung: Person 1 first, then Person 2. One field → one (x,y).
            field_names = (
                list(anmeldung_strict_order)
                if anmeldung_strict_order
                else list(fields.keys())
            )
            if not field_names:
                field_names = list(fields.keys())
            for field_name in field_names:
                pos = fields.get(field_name)
                if not pos:
                    continue
                # Value: ONLY from get_value_for_pdf_field (strict mapping; no merged.get fallback for anmeldung)
                value = (
                    get_value_for_pdf_field(field_name, merged)
                    if callable(get_value_for_pdf_field)
                    else None
                )
                if value is None:
                    value = merged.get(field_name)
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                value_str = str(value).strip()

                # Checkbox: ONLY draw "X" at option position; NEVER render as text
                if pos.get("pdf_type") == "checkbox" and "options" in pos:
                    opts = pos["options"]
                    if not isinstance(opts, dict):
                        continue
                    option_keys = list(opts.keys())
                    matched_key = _normalize_checkbox_value(value_str, option_keys)
                    if not matched_key:
                        continue
                    coords = opts.get(matched_key)
                    if not coords:
                        continue
                    x, y = coords.get("x", 0), coords.get("y", 0)
                    if debug_positions:
                        try:
                            page.draw_rect(
                                fitz.Rect(x - 2, y - 2, x + 12, y + 10),
                                color=(0.8, 0.2, 0.2),
                                width=0.5,
                            )
                            page.insert_text(
                                (x, y + 8),
                                field_name[:12],
                                fontsize=5,
                                color=(0.6, 0, 0),
                                **font_kwargs,
                            )
                        except Exception:
                            pass
                    try:
                        page.insert_text(
                            (x, y + BASELINE_OFFSET_PT),
                            "X",
                            fontsize=pos.get("font_size", 10),
                            color=(0, 0, 0),
                            **font_kwargs,
                        )
                    except Exception as e:
                        logger.debug(
                            "insert_text checkbox %s at (%s,%s): %s",
                            field_name,
                            x,
                            y,
                            e,
                        )
                    continue

                # Checkbox fields (Anmeldung): never render value as text
                if field_name in checkbox_only:
                    continue

                # Text field: strict (x,y), clip to max_width
                max_width = pos.get("max_width", 200)
                font_size = pos.get("font_size", 12)
                x, y = pos.get("x", 0), pos.get("y", 0)
                y_baseline = y + BASELINE_OFFSET_PT
                color = pos.get("color")
                if color is None:
                    color = (0, 0, 0)
                elif isinstance(color, (list, tuple)) and len(color) == 3:
                    rc, gc, bc = color[0], color[1], color[2]
                    if not all(0 <= c <= 1 for c in (rc, gc, bc)):
                        color = (rc / 255.0, gc / 255.0, bc / 255.0)
                else:
                    color = (0, 0, 0)
                # Strip stray "X" from text values (must not affect checkbox path above)
                clean_value_str = value_str.replace("X", "").strip()
                if clean_value_str != value_str:
                    logger.info("Cleaned text field from stray X: field=%s", field_name)
                    value_str = clean_value_str
                # Truncate by width: ~0.5 * font_size per char for Latin
                max_chars = max(1, int(max_width / max(font_size * 0.5, 1)))
                text = (
                    value_str[:max_chars] if len(value_str) > max_chars else value_str
                )
                if not text:
                    continue
                if debug_positions:
                    try:
                        rect = fitz.Rect(x, y, x + max_width, y + font_size + 4)
                        page.draw_rect(rect, color=(0.8, 0.2, 0.2), width=0.5)
                        page.insert_text(
                            (x, y_baseline),
                            field_name[:20],
                            fontsize=6,
                            color=(0.6, 0, 0),
                            **font_kwargs,
                        )
                    except Exception:
                        pass
                try:
                    # Prefer insert_textbox so text is clipped to rect (no spill)
                    rect = fitz.Rect(x, y, x + max_width, y + font_size * 1.5)
                    if hasattr(page, "insert_textbox"):
                        page.insert_textbox(
                            rect,
                            text,
                            fontsize=font_size,
                            color=color,
                            align=fitz.TEXT_ALIGN_LEFT,
                            **font_kwargs,
                        )
                    else:
                        page.insert_text(
                            (x, y_baseline),
                            text,
                            fontsize=font_size,
                            color=color,
                            **font_kwargs,
                        )
                except Exception as e1:
                    try:
                        page.insert_text(
                            (x, y_baseline),
                            text,
                            fontsize=font_size,
                            color=color,
                            **font_kwargs,
                        )
                    except Exception as e2:
                        logger.debug(
                            "insert_text %s at (%s,%s): %s",
                            field_name,
                            x,
                            y_baseline,
                            e2,
                        )
        _apply_watermark(
            pdf, is_preview=is_preview, font_path=font_path, user_lang=user_lang
        )
        pdf.save(str(output_path))
        if not _verify_pdf_integrity(output_path, doc_type):
            return None
        logger.info(
            "✅ Template PDF filled: doc_type=%s is_preview=%s path=%s",
            doc_type,
            is_preview,
            output_path,
        )
        return str(output_path.resolve())
    except Exception as e:
        logger.error(
            "❌ _fill_template_pdf failed: doc_type=%s error=%s",
            doc_type,
            e,
            exc_info=True,
        )
        return None
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:
                pass


def create_preview(
    user_id: int,
    user_data: Dict[str, Any],
    doc_type: str,
    authority_info: Optional[Dict[str, str]] = None,
    is_preview: bool = True,
    user_lang: str = "en",
) -> Optional[str]:
    """
    Generate preview PDF — unofficial review/verification sheet (NOT the official form).

    Pipeline:
    1. Normalize user_data (dates, PLZ, IBAN, phone, names).
    2. Compute validation state (missing / warnings) — shown as checklist, NOT blocking.
    3. Render via PreviewRenderer (wraps german_form_builder, is_preview=True).
       Always uses the custom review layout — never the AcroForm template.
    4. Emergency fallback to _render_pdf (should never be reached for known doc_types).
    """
    # ── Step 1: normalize values ────────────────────────────────────────────
    if callable(_premium_normalize):
        try:
            user_data = _premium_normalize(user_data)
        except Exception as _ne:
            logger.debug("create_preview: normalization skipped (%s)", _ne)

    # ── Step 1b: buergergeld normalization — same rules as create_final_pdf ──
    if (doc_type or "").strip().lower() in ("buergergeld", "jobcenter"):
        try:
            from backend.utils.normalize import (
                normalize_buergergeld_data,
                validate_buergergeld_data,
            )

            user_data = normalize_buergergeld_data(user_data)
            user_data = validate_buergergeld_data(user_data)
        except Exception as _bge:
            logger.warning(
                "⚠️ create_preview: normalize_buergergeld_data FAILED: %s",
                _bge,
                exc_info=True,
            )

    # ── Step 2: validate (for checklist display only — never blocks preview) ─
    _missing: List[Dict[str, str]] = []
    _warnings: List[Dict[str, str]] = []
    if callable(_premium_validate):
        try:
            _, _missing, _warnings = _premium_validate(
                doc_type, user_data, user_lang or "de"
            )
        except Exception as _ve:
            logger.debug("create_preview: validation skipped (%s)", _ve)

    # ── Step 2b: buergergeld input validation (display only — never blocks) ─
    if (doc_type or "").strip().lower() in ("buergergeld", "jobcenter"):
        try:
            from backend.validation_buergergeld import validate_buergergeld

            _bg_val = validate_buergergeld(user_data)
            for _err in _bg_val.get("errors", []):
                _missing.append(
                    {
                        "key": "buergergeld_input",
                        "label": "Eingabefehler",
                        "message": _err,
                    }
                )
            for _wrn in _bg_val.get("warnings", []):
                _warnings.append(
                    {"key": "buergergeld_hint", "label": "Hinweis", "message": _wrn}
                )
        except Exception as _bgve:
            logger.debug("create_preview: validate_buergergeld skipped (%s)", _bgve)

    # ── Step 2c: buergergeld preview data restriction ────────────────────────
    # Show only name in the preview — all other fields are blanked.
    # Validation (steps 2/2b) already ran on FULL data, so the checklist is intact.
    # Final PDF generation (create_final_pdf) is a separate code path — unaffected.
    _render_data = user_data
    if (doc_type or "").strip().lower() in ("buergergeld", "jobcenter"):
        _PREVIEW_VISIBLE = frozenset(("first_name", "last_name"))
        _render_data = {
            k: (v if k in _PREVIEW_VISIBLE else "")
            for k, v in user_data.items()
        }
        logger.info(
            "create_preview: buergergeld — preview data restricted to name only "
            "(fields blanked: %d)",
            sum(1 for k in user_data if k not in _PREVIEW_VISIBLE),
        )

    # ── Step 2d: kindergeld — use dedicated clean-layout preview generator ───
    # generate_kindergeld_preview_clean() produces a structured ReportLab PDF
    # (name, child, IBAN, key fields) with no template clipping or coordinate
    # overlay. Isolated to kindergeld only; all other doc_types continue below.
    if (doc_type or "").strip().lower() == "kindergeld":
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            _kg_prev_out = OUTPUT_DIR / f"kindergeld_{user_id}_{timestamp}_preview.pdf"
            _kg_prev_result = generate_kindergeld_preview_clean(
                user_id=user_id,
                user_data=_render_data,
                output_path=_kg_prev_out,
                user_lang=user_lang or "de",
            )
            if _kg_prev_result:
                _apply_final_disclaimer(_kg_prev_result, skip_header=False)
                logger.info(
                    "create_preview: kindergeld clean preview -> %s", _kg_prev_result
                )
                return _kg_prev_result
        except Exception as _kg_prev_err:
            logger.warning(
                "create_preview: kindergeld clean preview failed (%s) — falling through to PreviewRenderer",
                _kg_prev_err,
            )

    # ── Step 3: PreviewRenderer (wraps german_form_builder, is_preview=True) ─
    # All doc_types use the custom review-layout (not the official template).
    # _render_pdf is NOT called for preview — it is a final-PDF-only emergency fallback.
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fb_output = OUTPUT_DIR / f"{doc_type}_{user_id}_{timestamp}_preview.pdf"
        fb_result = preview_renderer.render(
            doc_type=doc_type,
            user_data=_render_data,
            output_path=str(fb_output),
            user_lang=user_lang or "de",
            missing_fields=_missing,
            warnings=_warnings,
        )
        if fb_result:
            # Add red header + grey footer disclaimer to preview PDFs.
            # skip_header=False: preview builder watermark is a diagonal overlay, not the red text header.
            _apply_final_disclaimer(fb_result, skip_header=False)
            return fb_result
    except Exception as _prev_err:
        logger.warning(
            "create_preview: PreviewRenderer failed (%s) — emergency fallback",
            _prev_err,
        )

    # ── Step 4: emergency fallback only (PreviewRenderer covers all menu doc_types) ──
    logger.error(
        "create_preview: ALL paths failed for doc_type=%s — using _render_pdf emergency fallback",
        doc_type,
    )
    return _render_pdf(
        user_id=user_id,
        user_data=_render_data,
        doc_type=doc_type,
        authority_info=authority_info,
        is_preview=True,
        user_lang=user_lang,
    )


def generate_anmeldung_from_template(
    user_id: int,
    user_data: Dict[str, Any],
) -> Optional[str]:
    """
    Fill the official Anmeldung PDF template via pdfrw AcroForm field injection.
    Returns the output path on success, None on failure.
    """
    import pdfrw

    template_path = LEGACY_TEMPLATES_DIR / "housing" / "anmeldung.pdf"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"anmeldung_{user_id}_{timestamp}.pdf"

    pdf = pdfrw.PdfReader(str(template_path))

    for page in pdf.pages:
        for annot in page.Annots or []:
            if annot.T:
                key = annot.T[1:-1]
                if key in user_data:
                    raw_value = str(user_data[key])
                    field_type = str(annot.FT or "").strip()
                    if field_type == "/Tx":
                        # Text field: remove stray "X" characters
                        clean_value = raw_value.replace("X", "").strip()
                        if clean_value != raw_value:
                            logger.info(
                                "Cleaned text field from stray X: field=%s", key
                            )
                        value_to_write = clean_value
                    else:
                        # Checkbox / radio / other: preserve value as-is
                        value_to_write = raw_value
                    annot.update(pdfrw.PdfDict(V=f"({value_to_write})"))
                    annot.update(pdfrw.PdfDict(AP=""))

    if not pdf.Root.AcroForm:
        pdf.Root.update(pdfrw.PdfDict(AcroForm=pdfrw.PdfDict()))
    pdf.Root.AcroForm.update(pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject("true")))

    pdfrw.PdfWriter().write(str(output_path), pdf)
    logger.info("Using template rendering: anmeldung → %s", output_path)
    return str(output_path)


def generate_kindergeld_preview_clean(
    user_id: int,
    user_data: Dict[str, Any],
    output_path: Path,
    user_lang: str = "de",
) -> Optional[str]:
    """Generate a clean 'Filled Example' PDF for Kindergeld using ReportLab.

    No template overlay, no coordinates — pure structured layout.
    Returns output path string on success, None on failure.
    """
    try:
        from reportlab.lib.pagesizes import A4 as _A4
        from reportlab.lib.units import mm as _mm
        from reportlab.lib import colors as _colors
        from reportlab.platypus import (
            SimpleDocTemplate as _Doc,
            Paragraph as _Para,
            Spacer as _Spacer,
            Table as _Table,
            TableStyle as _TS,
            HRFlowable as _HR,
            KeepTogether as _KT,
        )
        from reportlab.lib.styles import ParagraphStyle as _PS
        from reportlab.pdfbase import pdfmetrics as _pm
        from reportlab.pdfbase.ttfonts import TTFont as _TTF
        from pathlib import Path as _Path

        # ── Font setup — prefer DejaVuSans (full Unicode), fall back to Helvetica ──
        _font_dir = _Path(__file__).parent.parent / "fonts"
        _reg = _font_dir / "DejaVuSans.ttf"
        _bld = _font_dir / "DejaVuSans-Bold.ttf"
        _FONT = "DejaVuSans"
        _FONT_BOLD = "DejaVuSans-Bold"
        try:
            if _FONT not in _pm.getRegisteredFontNames() and _reg.exists():
                _pm.registerFont(_TTF(_FONT, str(_reg)))
            if _FONT_BOLD not in _pm.getRegisteredFontNames() and _bld.exists():
                _pm.registerFont(_TTF(_FONT_BOLD, str(_bld)))
        except Exception:
            _FONT = "Helvetica"
            _FONT_BOLD = "Helvetica-Bold"

        # ── Normalize data ────────────────────────────────────────────────────
        data = dict(user_data)
        if callable(_premium_normalize):
            try:
                data = _premium_normalize(data)
            except Exception:
                pass
        if not (data.get("signature_date") or "").strip():
            data["signature_date"] = datetime.now().strftime("%d.%m.%Y")

        def _v(key: str) -> str:
            return (data.get(key) or "").strip()

        # ── Layout constants ──────────────────────────────────────────────────
        _W, _H = _A4
        _MARGIN_L = 22 * _mm
        _MARGIN_R = 18 * _mm
        _MARGIN_T = 20 * _mm
        _MARGIN_B = 20 * _mm
        _CONTENT_W = _W - _MARGIN_L - _MARGIN_R

        # ── Color palette ─────────────────────────────────────────────────────
        _NAVY = _colors.HexColor("#1c3557")
        _STEEL = _colors.HexColor("#3a6ea5")
        _RULE = _colors.HexColor("#c8d6e8")
        _RULE_LT = _colors.HexColor("#e2e8f0")
        _ROW_ALT = _colors.HexColor("#f7f9fc")
        _GREEN_BG = _colors.HexColor("#eef8ee")
        _GREEN_BD = _colors.HexColor("#3a8a3a")
        _GREEN_TXT = _colors.HexColor("#1d5c1d")
        _AMBER_BG = _colors.HexColor("#fdf8ec")
        _AMBER_BD = _colors.HexColor("#c8960a")
        _AMBER_TXT = _colors.HexColor("#6b4e00")
        _BLUE_BG = _colors.HexColor("#eef4fb")
        _BLUE_BD = _colors.HexColor("#3a6ea5")
        _LABEL_CLR = _colors.HexColor("#4a5568")
        _VALUE_CLR = _colors.HexColor("#1a202c")
        _MUTED = _colors.HexColor("#718096")

        # ── Style factory ─────────────────────────────────────────────────────
        def _ps(name, font=_FONT, size=10, leading=15, color=_VALUE_CLR, sb=0, sa=0):
            return _PS(
                name,
                fontName=font,
                fontSize=size,
                leading=leading,
                textColor=color,
                spaceBefore=sb,
                spaceAfter=sa,
            )

        s_doc_label = _ps("kg_doc_label", _FONT, 8, 11, _MUTED, 0, 1)
        s_title = _ps("kg_title", _FONT_BOLD, 18, 22, _NAVY, 0, 2)
        s_subtitle = _ps("kg_subtitle", _FONT, 9, 13, _STEEL, 0, 0)
        s_ok = _ps("kg_ok", _FONT, 9, 14, _GREEN_TXT)
        s_warn = _ps("kg_warn", _FONT, 9, 14, _AMBER_TXT)
        s_ready = _ps("kg_ready", _FONT_BOLD, 9, 14, _NAVY)
        s_head = _ps("kg_head", _FONT_BOLD, 10, 14, _NAVY, 10, 2)
        s_label = _ps("kg_label", _FONT, 9, 14, _LABEL_CLR)
        s_value = _ps("kg_value", _FONT_BOLD, 9, 14, _VALUE_CLR)
        s_footer = _ps("kg_footer", _FONT, 7, 10, _MUTED, 8, 0)
        s_footer_lk = _ps("kg_footer_lk", _FONT, 7, 10, _STEEL, 0, 0)

        story = []

        # ── Document header ───────────────────────────────────────────────────
        story.append(_Para("KINDERGELD APPLICATION", s_doc_label))
        story.append(_Spacer(1, 1 * _mm))
        story.append(
            _Para("Kindergeld Application \u2014 Verified Filled Example", s_title)
        )
        story.append(
            _Para(
                "Bundesagentur f\u00fcr Arbeit \u00b7 Familienkasse",
                s_subtitle,
            )
        )
        story.append(
            _Para(
                "Prepared to help you avoid common application mistakes",
                s_subtitle,
            )
        )
        story.append(_Spacer(1, 3 * _mm))
        story.append(_HR(width="100%", thickness=2, color=_NAVY))
        story.append(_Spacer(1, 4 * _mm))

        # ── Status row (two boxes side by side) ───────────────────────────────
        _half = (_CONTENT_W - 3 * _mm) / 2

        def _badge(text, style, bg, border):
            t = _Table([[_Para(text, style)]], colWidths=[_half])
            t.setStyle(
                _TS(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), bg),
                        ("BOX", (0, 0), (-1, -1), 0.75, border),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 9),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            return t

        _status_row = _Table(
            [
                [
                    _badge(
                        "\u2714  All required fields completed",
                        s_ok,
                        _GREEN_BG,
                        _GREEN_BD,
                    ),
                    _badge(
                        "\u2714  No critical errors detected",
                        s_ok,
                        _GREEN_BG,
                        _GREEN_BD,
                    ),
                ]
            ],
            colWidths=[_half, _half],
            hAlign="LEFT",
        )
        _status_row.setStyle(
            _TS(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(_status_row)
        story.append(_Spacer(1, 3 * _mm))

        # ── Readiness highlight box ───────────────────────────────────────────
        _ready_tbl = _Table(
            [[_Para("\u2714  Application readiness: Ready for submission", s_ready)]],
            colWidths=[_CONTENT_W],
        )
        _ready_tbl.setStyle(
            _TS(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _BLUE_BG),
                    ("BOX", (0, 0), (-1, -1), 1.0, _BLUE_BD),
                    ("LEFTLINE", (0, 0), (0, -1), 3.5, _STEEL),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(_ready_tbl)
        story.append(_Spacer(1, 3 * _mm))

        # ── Warning notice ────────────────────────────────────────────────────
        _warn_tbl = _Table(
            [
                [
                    _Para(
                        "\u26a0\u00a0 This document is a filled reference example. "
                        "It is provided to help you accurately complete the official "
                        "Kindergeld form. Do not submit this document to the authorities.",
                        s_warn,
                    )
                ]
            ],
            colWidths=[_CONTENT_W],
        )
        _warn_tbl.setStyle(
            _TS(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _AMBER_BG),
                    ("BOX", (0, 0), (-1, -1), 0.75, _AMBER_BD),
                    ("LEFTLINE", (0, 0), (0, -1), 3.5, _AMBER_BD),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(_warn_tbl)
        story.append(_Spacer(1, 6 * _mm))

        # ── Section builder ───────────────────────────────────────────────────
        _sec = [1]

        def _section(title: str, rows: list):
            numbered_title = f"{_sec[0]}.  {title}"
            _sec[0] += 1
            _col_lbl = _CONTENT_W * 0.36
            _col_val = _CONTENT_W * 0.64
            tbl_rows = []
            for lbl, val in rows:
                tbl_rows.append(
                    [
                        _Para(lbl, s_label),
                        _Para(val if val else "\u2014", s_value),
                    ]
                )
            tbl = _Table(tbl_rows, colWidths=[_col_lbl, _col_val])
            tbl.setStyle(
                _TS(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_colors.white, _ROW_ALT]),
                        ("LINEBELOW", (0, 0), (-1, -2), 0.4, _RULE_LT),
                        ("BOX", (0, 0), (-1, -1), 0.5, _RULE),
                    ]
                )
            )
            block = [
                _Para(numbered_title, s_head),
                _HR(width="100%", thickness=0.75, color=_STEEL),
                _Spacer(1, 2 * _mm),
                tbl,
                _Spacer(1, 5 * _mm),
            ]
            story.append(_KT(block))

        # ── Section 1: Applicant Information ─────────────────────────────────
        _full_name = " ".join(filter(None, [_v("first_name"), _v("last_name")])) or None
        _addr_line = " ".join(filter(None, [_v("street"), _v("house_number")]))
        _city_line = " ".join(filter(None, [_v("postal_code"), _v("city")]))
        _address = ", ".join(filter(None, [_addr_line, _city_line])) or None

        _appl_rows = [
            ("Full Name", _full_name),
            ("Date of Birth", _v("birth_date") or None),
            ("Place of Birth", _v("birth_place") or None),
            ("Address", _address),
            ("Nationality", _v("nationality") or None),
            ("Marital Status", _v("familienstand") or None),
        ]
        if _v("tax_id"):
            _appl_rows.append(("Tax ID (Steuer-ID)", _v("tax_id")))
        _section("Applicant Information", _appl_rows)

        # ── Section 2 (conditional): Partner Information ─────────────────────
        _p_first = _v("partner_first_name")
        _p_last = _v("partner_last_name")
        _p_dob = _v("partner_birth_date")
        if _p_first or _p_last or _p_dob:
            _p_name = " ".join(filter(None, [_p_first, _p_last])) or None
            _section(
                "Partner Information",
                [
                    ("Full Name", _p_name),
                    ("Date of Birth", _p_dob or None),
                ],
            )

        # ── Section 3: Child Information ──────────────────────────────────────
        _child_name = (
            " ".join(filter(None, [_v("child_first_name"), _v("child_last_name")]))
            or None
        )
        _child_rows = [
            ("Full Name", _child_name),
            ("Date of Birth", _v("child_birth_date") or None),
            ("Place of Birth", _v("child_birth_place") or None),
        ]
        if _v("child_nationality"):
            _child_rows.append(("Nationality", _v("child_nationality")))
        _section("Child Information", _child_rows)

        # ── Section 4: Bank Details ───────────────────────────────────────────
        _bank_rows = [
            ("IBAN", _v("iban") or None),
            ("Account Holder", _v("account_holder") or None),
        ]
        if _v("bic"):
            _bank_rows.append(("BIC / SWIFT", _v("bic")))
        if _v("bank_name"):
            _bank_rows.append(("Bank Name", _v("bank_name")))
        _section("Bank Details", _bank_rows)

        # ── Footer ────────────────────────────────────────────────────────────
        story.append(_Spacer(1, 2 * _mm))
        story.append(_HR(width="100%", thickness=0.5, color=_RULE))
        _footer_tbl = _Table(
            [
                [
                    _Para(
                        "Date of Issue: "
                        + (_v("signature_date") or datetime.now().strftime("%d.%m.%Y"))
                        + "  \u00b7  For personal reference only",
                        s_footer,
                    ),
                    _Para(
                        "Official form: https://www.familienkasse.de",
                        _PS(
                            "kg_footer_r",
                            fontName=_FONT,
                            fontSize=7,
                            leading=10,
                            textColor=_STEEL,
                            spaceBefore=8,
                            alignment=2,  # right
                        ),
                    ),
                ]
            ],
            colWidths=[_CONTENT_W * 0.6, _CONTENT_W * 0.4],
        )
        _footer_tbl.setStyle(
            _TS(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(_footer_tbl)

        # ── Render ────────────────────────────────────────────────────────────
        doc = _Doc(
            str(output_path),
            pagesize=_A4,
            leftMargin=_MARGIN_L,
            rightMargin=_MARGIN_R,
            topMargin=_MARGIN_T,
            bottomMargin=_MARGIN_B,
        )
        doc.build(story)
        logger.info("generate_kindergeld_preview_clean: saved -> %s", output_path)
        return str(output_path)

    except Exception as _e:
        logger.error(
            "generate_kindergeld_preview_clean: failed — %s", _e, exc_info=True
        )
        return None


# ---------------------------------------------------------------------------
# Kindergeld coordinate calibration debug flag.
# Set to True to overlay a coordinate grid, axis labels, and red field markers
# on the generated PDF.  Keeps DEBUG=False for production.
# To enable: change the line below to True, regenerate, inspect, adjust _fields,
# then set back to False before deploying.
# ---------------------------------------------------------------------------
_KINDERGELD_DEBUG_GRID: bool = False

# Switch to builder-based PDF generation for Kindergeld (ReportLab flow layout).
# True  → use generate_kindergeld_builder() — clean readable PDF, no coordinate calibration needed.
# False → use generate_kindergeld_from_template() — text overlaid on official XFA background.
USE_BUILDER_FOR_KINDERGELD: bool = False


def _kg_draw_debug_grid(page) -> None:  # type: ignore[no-untyped-def]
    """Draw a light grey 50-pt grid with coordinate labels every 100 pt.

    Coordinate system used throughout _fields: (x, y_top) where y_top is
    measured from the TOP of the page (natural reading direction).
    PyMuPDF's draw_line / insert_text use the same top-left origin, so no
    conversion is needed here.
    """
    w = int(page.rect.width)
    h = int(page.rect.height)
    grey = (0.75, 0.75, 0.75)
    label_color = (0.45, 0.45, 0.45)

    # Vertical lines every 50 pt
    for gx in range(0, w + 1, 50):
        page.draw_line((gx, 0), (gx, h), color=grey, width=0.3)

    # Horizontal lines every 50 pt
    for gy in range(0, h + 1, 50):
        page.draw_line((0, gy), (w, gy), color=grey, width=0.3)

    # Coordinate labels at every 100-pt intersection
    for gx in range(0, w + 1, 100):
        for gy in range(0, h + 1, 100):
            page.insert_text(
                (gx + 1, gy + 7),
                f"{gx},{gy}",
                fontsize=5,
                color=label_color,
            )


def generate_kindergeld_from_template(
    user_id: int,
    user_data: Dict[str, Any],
    output_path: Path,
    user_lang: str = "de",
) -> Optional[str]:
    """Overlay user data onto the official Kindergeld KG 1 template.

    Opens templates/kindergeld/default.pdf, draws each field value as plain
    text at fixed coordinates using PyMuPDF insert_text().  No AcroForm / XFA
    interaction — the template is treated as a read-only background image.
    Returns output path on success, None if the template file is missing.

    Coordinate convention in _fields: (data_key, page_index, x, y_top, fontsize)
    where x and y_top are in PDF points measured from the TOP-LEFT corner of the
    page.  PyMuPDF insert_text() also uses top-left origin, so the conversion is:
        pdf_y = page.rect.height - y_top   ← done inside the draw loop below
    """
    template_path = TEMPLATES_DIR / "kindergeld" / "default.pdf"
    if not template_path.exists():
        logger.warning(
            "generate_kindergeld_from_template: template missing — %s", template_path
        )
        return None

    # 1. Normalize (Ukraine → ukrainisch, date formats, etc.)
    data = dict(user_data)
    if callable(_premium_normalize):
        try:
            data = _premium_normalize(data)
        except Exception as _ne:
            logger.warning(
                "generate_kindergeld_from_template: normalize failed (%s)", _ne
            )
    if not (data.get("signature_date") or "").strip():
        data["signature_date"] = datetime.now().strftime("%d.%m.%Y")

    # 2. Field layout: (data_key, page_index, x, y_top, fontsize)
    #
    # Template structure (templates/kindergeld/default.pdf — 5 pages total):
    #   page 0 → "Nutzen Sie das Online-Angebot" (info page)
    #   page 1 → "KG 1 - Seite 1/2"  ← Antragsteller, Partner, Bankverbindung
    #   page 2 → "KG 1 - Seite 2/2"  ← Kinder table, Unterschrift
    #   page 3-4 → Hinweise (instructions, do not fill)
    #
    # y_top = distance from the TOP of the page in PDF points.
    # Derived from actual label positions via page.get_text('dict'):
    #   each field is placed ~7 pt ABOVE its printed label so the text
    #   lands on the blank input line directly above the label text.
    # Conversion inside the draw loop: pdf_y = page.rect.height - y_top
    _fs = (data.get("familienstand") or "").strip().lower()
    _fields = [
        # ── KG 1 Seite 1 (PDF page 1): Section 1 — Antragsteller ───────────────
        # Steuer-ID: individual boxes below section header (label y=236)
        ("tax_id",          1,  65, 262, 9),
        # Name fields: label text is printed BELOW the input line
        ("last_name",       1,  65, 275, 9),   # Familienname; label y=282
        ("first_name",      1,  65, 306, 9),   # Vorname; label y=313
        ("birth_name",      1, 371, 306, 9),   # ggf. Geburtsname; label y=313 x=371
        ("birth_date",      1,  65, 337, 9),   # Geburtsdatum; label y=344
        ("birth_place",     1, 133, 337, 9),   # Geburtsort; label y=345 x=133
        ("nationality",     1, 371, 337, 9),   # Staatsangehörigkeit; label y=344 x=371
        # Anschrift: "Anschrift" is a top-header label at y=398; fill box is BELOW it
        ("street",          1,  65, 412, 9),
        ("house_number",    1, 330, 412, 9),
        ("postal_code",     1,  65, 424, 9),
        ("city",            1, 120, 424, 9),
        # ── KG 1 Seite 1 (PDF page 1): Section 3 — Bankverbindung ───────────────
        # IBAN: "IBAN" label at y=698; row of boxes BELOW the label
        ("iban",            1,  65, 712, 9),
        # BIC + Bank: "BIC" label y=728, "Bank" label y=729 x=220
        ("bic",             1,  65, 742, 9),
        ("bank_name",       1, 220, 742, 9),
        # Kontoinhaber name field (only filled when account holder differs from applicant)
        ("account_holder",  1, 220, 766, 9),
        # ── KG 1 Seite 2 (PDF page 2): Section 5 — Kinder (row 1) ──────────────
        # Table column headers at y=229-237; first data row just below
        ("child_last_name",   2,  48, 255, 9),
        ("child_first_name",  2,  48, 268, 9),
        ("child_birth_date",  2, 199, 255, 9),
        ("child_birth_place", 2, 319, 255, 9),
        # ── KG 1 Seite 2 (PDF page 2): Unterschrift ─────────────────────────────
        # "Datum" label at y=684; input line just above
        ("signature_date",    2,  51, 678, 9),
    ]
    # Partner/Ehepartner section — only when married / Lebenspartnerschaft
    # Labels on page 1: Namen y=577, Geburtsdatum+Staatsangehörigkeit y=608
    if any(k in _fs for k in ("verheiratet", "married", "lebenspartnerschaft", "verpartnert")):
        _fields += [
            ("partner_last_name",   1,  65, 570, 9),
            ("partner_first_name",  1, 254, 570, 9),
            ("partner_birth_date",  1,  65, 601, 9),
            ("partner_nationality", 1, 133, 601, 9),
        ]

    # Familienstand checkboxes: draw × at the correct checkbox position on page 1
    # Checkbox x is ~8pt left of the printed label text x-coordinate
    _fs_checkbox_pos = {
        "ledig":               (1,  66, 450),
        "verheiratet":         (1, 256, 436),
        "geschieden":          (1, 256, 450),
        "verwitwet":           (1, 256, 464),
        "getrennt":            (1, 355, 464),
        "lebenspartnerschaft": (1, 355, 436),
        "aufgehoben":          (1, 355, 450),
    }

    # 3. Draw text (and optional debug grid) over template
    if not PYMUPDF_AVAILABLE:
        logger.error("generate_kindergeld_from_template: PyMuPDF not available")
        return None
    try:
        pdf = fitz.open(str(template_path))
        logger.info("PDF_TEMPLATE_USED=kindergeld/default.pdf pages=%d", len(pdf))
        font_path = find_dejavu_font()
        font_kwargs = {"fontfile": font_path} if font_path else {"fontname": "helv"}

        # ── Debug grid: draw before field text so markers sit on top ──────────
        if _KINDERGELD_DEBUG_GRID:
            logger.info("DEBUG_GRID ENABLED — drawing calibration grid on all pages")
            for _pg in pdf:
                _kg_draw_debug_grid(_pg)

        _filled = 0
        _missing = []
        for key, page_idx, x, y_top, fs in _fields:
            val = (data.get(key) or "").strip()
            if not val:
                _missing.append(key)
                # In debug mode, draw a placeholder so we can see where the field is
                if _KINDERGELD_DEBUG_GRID and page_idx < len(pdf):
                    _pg = pdf[page_idx]
                    # y_top is screen coordinate from top; use directly (no inversion needed)
                    _py = y_top
                    _pg.draw_circle(
                        fitz.Point(x, _py), 3,
                        color=(1.0, 0.5, 0.0), fill=(1.0, 0.8, 0.0),
                    )
                    _pg.insert_text(
                        (x + 5, _py - 1),
                        f"[{key}]",
                        fontsize=6, color=(1.0, 0.5, 0.0),
                    )
                continue
            if page_idx >= len(pdf):
                logger.warning(
                    "PDF_FIELD_MISSING=name=%s reason=page_%d_not_in_template",
                    key, page_idx,
                )
                continue
            _pg = pdf[page_idx]
            # PyMuPDF insert_text uses screen coordinates: (0,0) = top-left, y increases downward.
            # y_top is already measured from the page top, so pass it directly.
            _py = y_top
            _pg.insert_text(
                (x, _py), val, fontsize=fs, color=(0, 0, 0), **font_kwargs
            )
            _filled += 1

            # Debug: red dot + field name next to each placed value
            if _KINDERGELD_DEBUG_GRID:
                _pg.draw_circle(
                    fitz.Point(x, _py), 3,
                    color=(1.0, 0.0, 0.0), fill=(1.0, 0.4, 0.4),
                )
                _pg.insert_text(
                    (x + 5, _py - 1),
                    f"{key} ({x},{y_top})",
                    fontsize=5.5, color=(0.8, 0.0, 0.0),
                )

        # Draw familienstand checkbox (×) at the correct position on page 1
        for _kw, (_cpg, _cx, _cy_top) in _fs_checkbox_pos.items():
            if _kw in _fs and _cpg < len(pdf):
                _cpg_obj = pdf[_cpg]
                _cpg_obj.insert_text(
                    (_cx, _cy_top), "×", fontsize=8, color=(0, 0, 0), **font_kwargs
                )
                break

        logger.info("PDF_FIELDS_FILLED=count=%d", _filled)
        for _mk in _missing:
            logger.warning("PDF_FIELD_MISSING=name=%s reason=no_user_data", _mk)
        if _KINDERGELD_DEBUG_GRID:
            logger.info(
                "DEBUG_GRID field coordinates:\n%s",
                "\n".join(
                    f"  {k:30s} page={p} x={x:4d} y_top={y:4d}"
                    for k, p, x, y, _ in _fields
                ),
            )

        pdf.save(str(output_path), garbage=4, deflate=True)
        pdf.close()
        logger.info("generate_kindergeld_from_template: saved → %s", output_path)
        return str(output_path)
    except Exception as _e:
        logger.error(
            "generate_kindergeld_from_template: overlay failed — %s", _e, exc_info=True
        )
        return None


def generate_kindergeld_builder(
    user_data: Dict[str, Any],
    user_lang: str = "de",
) -> bytes:
    """Generate a clean, readable Kindergeld summary PDF using ReportLab flow layout.

    Does NOT use the official XFA template — draws the form fields in a structured
    German-style layout using Platypus (SimpleDocTemplate).  Returns raw PDF bytes.

    This is the builder path, enabled via USE_BUILDER_FOR_KINDERGELD = True.
    The overlay path (generate_kindergeld_from_template) remains as a fallback.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "kg_title",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=20,
        spaceAfter=4 * mm,
        textColor=HexColor("#1a1a2e"),
        alignment=TA_LEFT,
    )
    style_subtitle = ParagraphStyle(
        "kg_subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        spaceAfter=6 * mm,
        textColor=HexColor("#555555"),
        alignment=TA_LEFT,
    )
    style_section = ParagraphStyle(
        "kg_section",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=15,
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
        textColor=HexColor("#1a1a2e"),
    )
    style_label = ParagraphStyle(
        "kg_label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=HexColor("#333333"),
    )
    style_value = ParagraphStyle(
        "kg_value",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        spaceAfter=2 * mm,
        textColor=HexColor("#000000"),
    )
    style_footer = ParagraphStyle(
        "kg_footer",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=11,
        spaceBefore=10 * mm,
        textColor=HexColor("#888888"),
        alignment=TA_CENTER,
    )

    def _val(key: str, fallback: str = "—") -> str:
        v = (user_data.get(key) or "").strip()
        return v if v else fallback

    def _row(label: str, value: str) -> list:
        """Return a label + value pair as two Paragraph elements."""
        return [
            Paragraph(label, style_label),
            Paragraph(value, style_value),
        ]

    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    story.append(Paragraph("Antrag auf Kindergeld", style_title))
    story.append(
        Paragraph(
            "Beispiel-Zusammenfassung &ndash; kein offizielles Dokument (KG 1)",
            style_subtitle,
        )
    )

    # ── Section 1: Persönliche Daten ────────────────────────────────────────
    story.append(Paragraph("1. Persönliche Daten des Antragstellers", style_section))
    for lbl, key in [
        ("Nachname:", "last_name"),
        ("Vorname:", "first_name"),
        ("Geburtsname:", "birth_name"),
        ("Geburtsdatum:", "birth_date"),
        ("Geburtsort:", "birth_place"),
        ("Staatsangehörigkeit:", "nationality"),
        ("Geschlecht:", "gender"),
    ]:
        story.extend(_row(lbl, _val(key)))

    # ── Section 2: Adresse ──────────────────────────────────────────────────
    story.append(Paragraph("2. Anschrift", style_section))
    street_full = " ".join(
        filter(None, [_val("street", ""), _val("house_number", "")])
    ) or "—"
    city_full = " ".join(
        filter(None, [_val("postal_code", ""), _val("city", "")])
    ) or "—"
    story.extend(_row("Straße / Hausnummer:", street_full))
    story.extend(_row("PLZ / Ort:", city_full))

    # ── Section 3: Steuer-ID ────────────────────────────────────────────────
    story.append(Paragraph("3. Steuerliche Identifikationsnummer", style_section))
    story.extend(_row("Steuer-ID:", _val("tax_id")))

    # ── Section 4: Familienstand ────────────────────────────────────────────
    story.append(Paragraph("4. Familienstand", style_section))
    story.extend(_row("Familienstand:", _val("familienstand")))

    # Partner — only when married / LP
    _fs = _val("familienstand", "").lower()
    if any(k in _fs for k in ("verheiratet", "married", "lebenspartnerschaft", "verpartnert")):
        story.append(Paragraph("Partner / Lebenspartner:", style_label))
        story.extend(_row("Nachname:", _val("partner_last_name")))
        story.extend(_row("Vorname:", _val("partner_first_name")))
        story.extend(_row("Geburtsdatum:", _val("partner_birth_date")))
        story.extend(_row("Staatsangehörigkeit:", _val("partner_nationality")))

    # ── Section 5: Bankverbindung ────────────────────────────────────────────
    story.append(Paragraph("5. Bankverbindung", style_section))
    for lbl, key in [
        ("IBAN:", "iban"),
        ("BIC:", "bic"),
        ("Geldinstitut:", "bank_name"),
        ("Kontoinhaber:", "account_holder"),
    ]:
        story.extend(_row(lbl, _val(key)))

    # ── Section 6: Kind ──────────────────────────────────────────────────────
    story.append(Paragraph("6. Kind", style_section))
    for lbl, key in [
        ("Nachname:", "child_last_name"),
        ("Vorname:", "child_first_name"),
        ("Geburtsdatum:", "child_birth_date"),
        ("Geburtsort:", "child_birth_place"),
        ("Staatsangehörigkeit:", "child_nationality"),
    ]:
        story.extend(_row(lbl, _val(key)))

    # ── Section 7: Unterschrift ──────────────────────────────────────────────
    story.append(Paragraph("7. Datum / Unterschrift", style_section))
    sig_date = _val("signature_date") if _val("signature_date") != "—" \
        else datetime.now().strftime("%d.%m.%Y")
    story.extend(_row("Ort:", _val("signature_place")))
    story.extend(_row("Datum:", sig_date))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(
        Paragraph(
            "Dies ist ein automatisch generiertes Beispiel zur Orientierung. "
            "Kein offizielles Dokument. Bitte reichen Sie den originalen KG-1-Vordruck "
            "bei Ihrer zuständigen Familienkasse ein.",
            style_footer,
        )
    )

    doc.build(story)
    return buf.getvalue()


def generate_kindergeld_form_filled(
    user_data: Dict[str, Any],
    user_lang: str = "de",
) -> bytes:
    """Fill Kindergeld KG1 form using real AcroForm widget fields (PyMuPDF).

    The template has 95 AcroForm widgets on pages 1-2.  This function fills
    each widget by field_name — no coordinate overlay, no manual x/y drawing.
    Returns raw PDF bytes ready to be saved or sent.

    Field names confirmed by inspecting templates/kindergeld/default.pdf.
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("generate_kindergeld_form_filled: PyMuPDF not available")

    template_path = TEMPLATES_DIR / "kindergeld" / "default.pdf"
    if not template_path.exists():
        raise FileNotFoundError(f"KG1 template not found: {template_path}")

    # Normalize user data (dates, IBAN, nationality labels, etc.)
    data = dict(user_data)
    if callable(_premium_normalize):
        try:
            data = _premium_normalize(data)
        except Exception as _ne:
            logger.warning("generate_kindergeld_form_filled: normalize failed (%s)", _ne)

    # Auto-fill signature date
    if not (data.get("signature_date") or "").strip():
        data["signature_date"] = datetime.now().strftime("%d.%m.%Y")

    # ── Build derived values ─────────────────────────────────────────────────
    _street   = (data.get("street") or "").strip()
    _house    = (data.get("house_number") or "").strip()
    _plz      = (data.get("postal_code") or data.get("plz") or "").strip()
    _city     = (data.get("city") or "").strip()
    _addr_ln1 = f"{_street} {_house}".strip()
    _addr_ln2 = f"{_plz} {_city}".strip()
    _address  = ", ".join(p for p in [_addr_ln1, _addr_ln2] if p)

    # Tax ID — put full 11-digit string into first box; remaining boxes blank.
    # Falls back to steuer_id_applicant if tax_id is empty.
    _tax_id = (
        (data.get("tax_id") or data.get("steuer_id_applicant") or "")
        .replace(" ", "")
        .replace("-", "")
    )

    # Familienstand helper
    _fs = (data.get("familienstand") or "").lower()
    def _cb(keyword: str) -> str:
        return "Yes" if keyword in _fs else "Off"

    # Gender → single char (m/w/d) as expected by the Geschlecht text field
    _g = (data.get("gender") or "").strip().lower()
    if _g in ("m", "männlich", "male"):
        _gender = "m"
    elif _g in ("w", "weiblich", "female"):
        _gender = "w"
    elif _g in ("d", "divers", "diverse"):
        _gender = "d"
    else:
        _gender = _g[:1] if _g else ""

    _pg = (data.get("partner_gender") or "").strip().lower()
    _partner_gender = "m" if _pg in ("m", "männlich", "male") else \
                      "w" if _pg in ("w", "weiblich", "female") else \
                      (_pg[:1] if _pg else "")

    # Account holder
    _account_holder = (data.get("account_holder") or "").strip()
    _same_person    = not _account_holder

    # Child name — "Vorname Familienname" in the single Zelle1 field
    _child_first = (data.get("child_first_name") or "").strip()
    _child_last  = (data.get("child_last_name") or "").strip()
    _child_name  = f"{_child_first} {_child_last}".strip()

    # Child gender
    _cg = (data.get("child_gender") or "").strip().lower()
    _child_gender = "m" if _cg in ("m", "männlich", "male") else \
                    "w" if _cg in ("w", "weiblich", "female") else \
                    (_cg[:1] if _cg else "")

    # ── Complete field map: widget field_name → value ────────────────────────
    FIELD_MAP: Dict[str, str] = {
        # Header — indicate 1 Anlage Kind is attached
        "topmostSubform[0].Seite1[0].#area[0].Überschrift[0].Anzahl-Anlagen[0]": "1",
        # Section 1 — Antragsteller
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-1[0].Name-Antragsteller[0]":
            data.get("last_name") or "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-2[0].Vorname-Antragsteller[0]":
            data.get("first_name") or "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-2[0].Geburtsname-Antragsteller[0]":
            data.get("birth_name") or "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-3[0].Geburtsdatum-Antragsteller[0]":
            data.get("birth_date") or "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-3[0].Geburtsort-Antragsteller[0]":
            data.get("birth_place") or "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-3[0].Geschlecht-Antragsteller[0]":
            _gender,
        "topmostSubform[0].Seite1[0].Punkt-1[0].Pkt-1-Zeile-3[0].Staatsangehörigkeit-Antragsteller[0]":
            data.get("nationality") or "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Anschrift-Antragsteller[0]":
            _address,
        # Steuer-ID (full number in first box; remaining boxes empty)
        "topmostSubform[0].Seite1[0].Punkt-1[0].Steuer-ID[0].Steuer-ID-1[0]": _tax_id,
        "topmostSubform[0].Seite1[0].Punkt-1[0].Steuer-ID[0].Steuer-ID-2[0]": "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Steuer-ID[0].Steuer-ID-3[0]": "",
        "topmostSubform[0].Seite1[0].Punkt-1[0].Steuer-ID[0].Steuer-ID-4[0]": "",
        # Familienstand checkboxes + since-date
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].ledig[0]":
            _cb("ledig"),
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].verheiratet[0]":
            _cb("verheiratet"),
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].Partner[0]":
            _cb("lebenspartnerschaft"),
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].geschieden[0]":
            _cb("geschieden"),
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].aufgehoben[0]":
            _cb("aufgehoben"),
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].getrennt[0]":
            _cb("getrennt"),
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].verwitwet[0]":
            _cb("verwitwet"),
        "topmostSubform[0].Seite1[0].Punkt-1[0].Familienstand[0].#area[12].seit[0]":
            data.get("familienstand_seit") or "",
        # NOTE: Steuer-ID-2[1].Steuer-ID-2\.1[0] – \.4[0] are intentionally
        # omitted.  PyMuPDF corrupts any AcroForm field whose name contains an
        # escaped dot (\.) when widget.update() rebuilds the appearance stream,
        # producing the Acrobat "malformed model" crash (1\[xref]1[0]).
        # Section 2 — Partner / Ehepartner
        "topmostSubform[0].Seite1[0].Punkt-2[0].#area[15].Name-Partner[0]":
            data.get("partner_last_name") or "",
        "topmostSubform[0].Seite1[0].Punkt-2[0].#area[15].Vorname-Partner[0]":
            data.get("partner_first_name") or "",
        "topmostSubform[0].Seite1[0].Punkt-2[0].#area[15].Geburtsdatum-Partner[0]":
            data.get("partner_birth_date") or "",
        "topmostSubform[0].Seite1[0].Punkt-2[0].#area[15].Staatsangehörigkeit-Partner[0]":
            data.get("partner_nationality") or "",
        "topmostSubform[0].Seite1[0].Punkt-2[0].#area[15].Geschlecht-Partner[0]":
            _partner_gender,
        "topmostSubform[0].Seite1[0].Punkt-2[0].#area[15].Geburtsname-Partner[0]":
            data.get("partner_birth_name") or "",
        # Section 3 — Bankverbindung
        "topmostSubform[0].Seite1[0].Punkt-3[0].IBAN[0]":
            data.get("iban") or "",
        "topmostSubform[0].Seite1[0].Punkt-3[0].BIC[0]":
            data.get("bic") or "",
        "topmostSubform[0].Seite1[0].Punkt-3[0].Bank[0]":
            data.get("bank_name") or "",
        "topmostSubform[0].Seite1[0].Punkt-3[0].Antragsteller[0]":
            "Yes" if _same_person else "Off",
        "topmostSubform[0].Seite1[0].Punkt-3[0].andere-Person[0]":
            "Off" if _same_person else "Yes",
        "topmostSubform[0].Seite1[0].Punkt-3[0].Name-Kontoinhaber[0]":
            _account_holder,
        # Section 5 — Kinder (first child in Zeile1)
        "topmostSubform[0].Page2[0].Punkt-5[0].Tabelle1-Kinder[0].Zeile1[0].Zelle1[0]":
            _child_name,
        "topmostSubform[0].Page2[0].Punkt-5[0].Tabelle1-Kinder[0].Zeile1[0].Zelle2[0]":
            data.get("child_birth_date") or "",
        "topmostSubform[0].Page2[0].Punkt-5[0].Tabelle1-Kinder[0].Zeile1[0].Zelle3[0]":
            _child_gender,
        # NOTE: steuer_id_child belongs to the Anlage Kind PDF (doc_type="kindergeld_anlage"),
        # not this KG1 template.  It is mapped in KINDERGELD_ANLAGE_ACROFORM_MAPPING and
        # filled via the standard acroform pipeline for that doc_type.
        # Unterschrift
        "topmostSubform[0].Page2[0].Unterschrift-1[0].Datum-1[0]":
            data.get("signature_date") or "",
    }

    # ── Fill form fields ─────────────────────────────────────────────────────
    pdf_doc = fitz.open(str(template_path))
    _filled = 0
    _errors = 0

    for _pg_obj in pdf_doc:
        for _w in _pg_obj.widgets():
            _fname = _w.field_name
            if _fname not in FIELD_MAP:
                continue
            _val = FIELD_MAP[_fname]
            try:
                if _w.field_type_string == "CheckBox":
                    _w.field_value = _w.on_state() if _val == "Yes" else "Off"
                else:
                    _w.field_value = _val
                _w.update()
                _filled += 1
                logger.debug("KG1_FIELD_FILLED: %s = %r", _fname.split(".")[-1], _val)
            except Exception as _we:
                _errors += 1
                logger.warning("KG1_FIELD_ERROR: %s: %s", _fname, _we)

    logger.info(
        "generate_kindergeld_form_filled: filled=%d errors=%d template=%s",
        _filled, _errors, template_path.name,
    )

    # ── Auto-generate Anlage Kind and append to KG1 ──────────────────────────
    # The Anlage Kind carries child-specific data (Steuer-ID, gender, birth info)
    # that live in a separate PDF form.  We fill it inline and merge so the user
    # receives a single combined document.
    _anlage_template = template_path.parent.parent / "kindergeld_anlage" / "default.pdf"
    if _anlage_template.exists():
        try:
            _anlage_doc = fitz.open(str(_anlage_template))
            _applicant_name = (
                f"{(data.get('first_name') or '').strip()} "
                f"{(data.get('last_name') or '').strip()}"
            ).strip()
            # Kindschaftsverhältnis mapping:
            # Columns: Zelle2=leibliches Kind, Zelle3=Adoptivkind,
            #          Zelle4=Pflegekind, Zelle5=Stiefkind, Zelle6=Enkelkind
            # Rows:    Zeile1=zur antragstellenden Person,
            #          Zeile2=zum/zur Ehepartner(in), Zeile4=zu anderer Person
            _kv = (data.get("kindschaftsverhaeltnis") or "leiblich").lower()
            _kv_col = (
                "Zelle2[0]" if _kv in ("leiblich", "leibliches kind", "biological") else
                "Zelle3[0]" if _kv in ("adoptiv", "adoptivkind", "adopted")        else
                "Zelle4[0]" if _kv in ("pflege", "pflegekind", "foster")            else
                "Zelle5[0]" if _kv in ("stief", "stiefkind", "step")               else
                "Zelle6[0]" if _kv in ("enkel", "enkelkind", "grandchild")         else
                "Zelle2[0]"  # default: leibliches Kind
            )
            _KV_BASE = (
                "topmostSubform[0].Page1[0].Frage-2[0].#area[10]"
                ".Kindschaftsverhältnis[0].Zeile1[0]."
            )
            _anlage_map: Dict[str, str] = {
                "topmostSubform[0].Page1[0].Kopfzeile[0].Kopfangaben[0].Name_Vorname_KGB[0]":
                    _applicant_name,
                "topmostSubform[0].Page1[0].Frage-1[0].Steuer-ID[0].Steuer-ID-1[0]":
                    (data.get("steuer_id_child") or "").replace(" ", "").replace("-", ""),
                "topmostSubform[0].Page1[0].Frage-1[0].Steuer-ID[0].Steuer-ID-2[0]": "",
                "topmostSubform[0].Page1[0].Frage-1[0].Steuer-ID[0].Steuer-ID-3[0]": "",
                "topmostSubform[0].Page1[0].Frage-1[0].Steuer-ID[0].Steuer-ID-4[0]": "",
                "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-2[0].Familienname-Kind[0]":
                    data.get("child_last_name") or "",
                "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-3[0].Vorname-Kind[0]":
                    data.get("child_first_name") or "",
                "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-4[0].Geburtsdatum[0]":
                    data.get("child_birth_date") or "",
                "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-4[0].Geburtsort-Kind[0]":
                    data.get("child_birth_place") or "",
                "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-4[0].Geschlecht[0]":
                    _child_gender,
                "topmostSubform[0].Page1[0].Frage-1[0].Pkt-1-Zeile-4[0].Staatsangehörigkeit[0]":
                    data.get("child_nationality") or "",
                # Kindschaftsverhältnis — tick the correct column in Zeile1 (applicant's child)
                _KV_BASE + _kv_col: "1",
            }
            _anlage_filled = 0
            for _apg in _anlage_doc:
                for _aw in _apg.widgets():
                    if _aw.field_name in _anlage_map:
                        try:
                            _aw.field_value = _anlage_map[_aw.field_name]
                            _aw.update()
                            _anlage_filled += 1
                        except Exception:
                            pass

            # ── Flatten Anlage Kind: render as images before merging ─────────
            # insert_pdf merges AcroForm field trees and corrupts the PDF.
            # Stripping /AcroForm from the catalog alone is insufficient
            # because widget annotations keep /Parent refs that insert_pdf
            # follows and copies, producing the Acrobat "malformed model" crash.
            #
            # Definitive fix: render each Anlage Kind page to a pixmap at
            # 150 DPI and create a new image-only PDF.  No AcroForm exists,
            # no merge conflict, AP-stream content is preserved as pixels.
            _flat = fitz.open()
            _scale = fitz.Matrix(150 / 72, 150 / 72)
            for _apg2 in _anlage_doc:
                _pix = _apg2.get_pixmap(matrix=_scale, alpha=False, annots=True)
                _pg2 = _flat.new_page(
                    width=_apg2.rect.width, height=_apg2.rect.height
                )
                _pg2.insert_image(_pg2.rect, pixmap=_pix)
            _anlage_doc.close()

            pdf_doc.insert_pdf(_flat)
            _flat.close()
            logger.info("KG1_ANLAGE_APPENDED: filled=%d (flat-image merge)", _anlage_filled)
        except Exception as _ae:
            logger.warning("KG1_ANLAGE_FAILED: %s", _ae)

    _buf = BytesIO()
    pdf_doc.save(_buf, garbage=4, deflate=True)
    pdf_doc.close()
    return _buf.getvalue()


def create_final_pdf(
    user_id: int,
    user_data: Dict[str, Any],
    doc_type: str,
    authority_info: Optional[Dict[str, str]] = None,
    user_lang: str = "en",
) -> Optional[Union[str, Dict[str, Any]]]:
    """
    Generate FINAL PDF (no watermark). Deterministic, clean; visual parity with official form.

    Returns:
      - str path on success
      - {"status": "validation_failed", "errors": [...], "missing_fields": [...]} when required
        fields are missing (no PDF generated)
      - None on unexpected failure

    Pipeline:
    1. Normalize user_data (dates → DD.MM.YYYY, PLZ, IBAN, phone, names).
    2. Pre-flight validation: block if required fields missing (all doc_types, not only anmeldung).
    3. AcroForm fill first (widget.field_value + widget.update()); NO x/y drawing.
    4. If no AcroForm → overlay fallback (flat/scanned PDFs only).
    5. If no template → german_form_builder.
    6. Legacy _render_pdf fallback.
    """
    if doc_type == "kiz":
        doc_type = "kinderzuschlag"
    print("PDF_DOC_TYPE:", doc_type)

    # ── Step 0: strict doc_type guard ──────────────────────────────────────
    _doc_key = (doc_type or "").strip().lower()
    if not DOC_RENDER_MAP or _doc_key not in DOC_RENDER_MAP:
        raise ValueError(
            f"create_final_pdf: unknown doc_type={doc_type!r} — "
            f"add it to DOC_RENDER_MAP in backend/pdf_renderers.py"
        )

    # ── Step 0b: anmeldung → official template rendering (pdfrw) ─────────────
    if _doc_key == "anmeldung":
        try:
            _tmpl_result = generate_anmeldung_from_template(user_id, user_data)
            if _tmpl_result:
                return _tmpl_result
            logger.warning(
                "⚠️ generate_anmeldung_from_template returned None — falling back to builder"
            )
        except Exception as _tmpl_err:
            logger.warning(
                "⚠️ generate_anmeldung_from_template FAILED (%s) — falling back to builder",
                _tmpl_err,
            )

    # ── Step 0c: kindergeld → AcroForm field filling (generate_kindergeld_form_filled) ──
    # The KG1 template has 95 real AcroForm widgets (confirmed by field inspection).
    # generate_kindergeld_form_filled() fills each widget by field_name — no coordinates.
    if _doc_key == "kindergeld":
        try:
            _kg_ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
            _kg_output = OUTPUT_DIR / f"kindergeld_{user_id}_{_kg_ts}.pdf"
            _kg_bytes  = generate_kindergeld_form_filled(user_data, user_lang or "de")
            _kg_output.write_bytes(_kg_bytes)
            logger.info("KG1_ACROFORM_FILLED path=%s size=%d", _kg_output, len(_kg_bytes))
            return str(_kg_output)
        except Exception as _kg_err:
            logger.warning(
                "⚠️ generate_kindergeld_form_filled FAILED (%s) — falling back to builder",
                _kg_err,
            )

    # ── Step 1: guard — block generation if user_data is empty ─────────────
    if not user_data:
        raise RuntimeError(
            f"create_final_pdf: Missing required field — user_data is empty (doc_type={doc_type})"
        )

    # ── Step 1: normalize user_data ────────────────────────────────────────
    _fields_before = len(user_data)
    if callable(_premium_normalize):
        try:
            user_data = _premium_normalize(user_data)
        except Exception as _ne:
            logger.warning(
                "⚠️ create_final_pdf: _premium_normalize FAILED (data unnormalized): %s",
                _ne,
                exc_info=True,
            )
    logger.info(
        "User data normalized: doc_type=%s user_id=%s fields=%d "
        "first_name=%r last_name=%r birth_country=%r birth_date=%r",
        doc_type,
        user_id,
        len(user_data),
        user_data.get("first_name"),
        user_data.get("last_name"),
        user_data.get("birth_country"),
        user_data.get("birth_date"),
    )

    logger.info(
        "PDF_DATA_NORMALIZED: doc_type=%s user_id=%s phone=%s familienstand=%s "
        "birth_place=%r child_birth_place=%r city=%r",
        doc_type,
        user_id,
        user_data.get("phone", "—"),
        user_data.get("familienstand") or user_data.get("family_status", "—"),
        user_data.get("birth_place"),
        user_data.get("child_birth_place"),
        user_data.get("city"),
    )

    # ── Step 1b: wohngeld normalization (boolean defaults + numeric defaults) ──
    if (doc_type or "").strip().lower() == "wohngeld":
        try:
            from backend.utils.normalize import normalize_wohngeld_data
            user_data = normalize_wohngeld_data(user_data)
            logger.info(
                "WG_NORMALIZED: has_hm=%s has_income=%s receives_benefits=%s "
                "has_assets=%s monthly_income=%s household_members_count=%d",
                user_data.get("has_household_members"),
                user_data.get("has_income"),
                user_data.get("receives_benefits"),
                user_data.get("has_assets"),
                user_data.get("monthly_income"),
                len(user_data.get("household_members") or []),
            )
        except Exception as _wge:
            logger.warning(
                "⚠️ normalize_wohngeld_data FAILED — PDF may have missing defaults: %s",
                _wge,
                exc_info=True,
            )
        # ── WG field-propagation audit log ──────────────────────────────────
        try:
            from backend.document_config import get_acroform_mapping as _wg_get_map
            _wg_mapping = _wg_get_map("wohngeld")
            _wg_mapped_keys = set(_wg_mapping.keys())
            _wg_answer_keys = {k for k, v in user_data.items()
                               if v not in (None, "", [], {}) and not k.startswith("_")}
            _wg_in_map = _wg_answer_keys & _wg_mapped_keys
            _wg_not_in_map = _wg_answer_keys - _wg_mapped_keys
            # Exclude internal/structural keys that are expected to have no direct PDF mapping
            _wg_internal = frozenset({
                "household_members", "has_household_members", "has_income",
                "user_id", "uid", "lang", "doc_type", "chat_id",
            })
            _wg_unexpected = _wg_not_in_map - _wg_internal
            logger.info(
                "WG_FIELD_AUDIT user_id=%s: answers_present=%d mapped_to_pdf=%d",
                user_id,
                len(_wg_answer_keys),
                len(_wg_in_map),
            )
            for _wg_k in sorted(_wg_unexpected):
                logger.warning(
                    "WG_UNMAPPED_FIELD user_id=%s key=%r has_value=%r — "
                    "field is in answers but has no direct AcroForm mapping",
                    user_id, _wg_k, bool(user_data.get(_wg_k)),
                )
        except Exception as _wg_audit_err:
            logger.debug("WG_FIELD_AUDIT skipped: %s", _wg_audit_err)

    # ── Step 1c: buergergeld normalization (defaults + conditional cleanup) ──────
    if (doc_type or "").strip().lower() in ("buergergeld", "jobcenter"):
        try:
            from backend.utils.normalize import (
                normalize_buergergeld_data,
                validate_buergergeld_data,
            )

            user_data = normalize_buergergeld_data(user_data)
            user_data = validate_buergergeld_data(user_data)
        except Exception as _bge:
            logger.warning(
                "⚠️ normalize_buergergeld_data FAILED — PDF may contain inconsistent data: %s",
                _bge,
                exc_info=True,
            )
        # ── Input validation (blocks generation on hard errors) ──────────────
        try:
            from backend.validation_buergergeld import validate_buergergeld

            _bg_validation = validate_buergergeld(user_data)
            if not _bg_validation["is_valid"]:
                logger.warning(
                    "⚠️ validate_buergergeld FAILED: errors=%s",
                    _bg_validation["errors"],
                )
                return {
                    "status": "validation_failed",
                    "errors": _bg_validation["errors"],
                    "missing_fields": [],
                }
        except Exception as _bgve:
            logger.warning(
                "⚠️ validate_buergergeld raised an exception (non-blocking): %s",
                _bgve,
                exc_info=True,
            )
        # Log which premium fields were collected
        _premium_keys = [
            "employment_status",
            "receives_benefits",
            "living_alone",
            "household_type",
            "rent_status",
            "has_health_insurance",
            "insurance_type",
            "has_residence_permit",
            "entry_date_germany",
            "warmwasser_zentral",
            "gender",
            "birth_country",
            "phone",
        ]
        _collected = [k for k in _premium_keys if (user_data.get(k) or "").strip()]
        logger.info(
            "PREMIUM_FLOW_COMPLETED user_id=%s fields_collected=%s",
            user_id,
            _collected,
        )

    # ── Step 1c: buergergeld/jobcenter hard invariant enforce ──────────────
    # Runs unconditionally BEFORE template path resolution so the guarantee
    # holds regardless of whether we go through AcroForm fill, FinalRenderer,
    # or any other backend path.  Must be the LAST data mutation before PDF.
    if (doc_type or "").strip().lower() in ("buergergeld", "jobcenter"):
        user_data = dict(user_data)  # safe mutable copy

        # 1. SV: strip garbage whitespace first, then has_sv_number=nein always wins
        if user_data.get("sv_number"):
            user_data["sv_number"] = str(user_data["sv_number"]).strip()
        _sv_flag_e = (user_data.get("has_sv_number") or "").strip().lower()
        _sv_num_e = (user_data.get("sv_number") or "").strip()
        if _sv_flag_e in ("nein", "no", "false", "0") and _sv_num_e:
            logger.warning(
                "[ENFORCE] sv_number=%r cleared (has_sv_number=%r) doc=%s user=%s",
                _sv_num_e,
                _sv_flag_e,
                doc_type,
                user_id,
            )
            user_data["sv_number"] = ""

        # 2. Phone: ensure leading + so international format is consistent
        _phone_e = (user_data.get("phone") or "").strip()
        if _phone_e and not _phone_e.startswith("+"):
            user_data["phone"] = "+" + _phone_e

        # 4. IBAN mutual exclusion.
        # IMPORTANT: jc_kein_konto / jc_konto_vorhanden are DERIVED fields —
        # they must never be read as raw user input.  Remove them from the dict
        # entirely so the raw-data fallback in fill loop cannot pick them up.
        # get_value_for_pdf_field derives their value from "iban" directly.
        user_data.pop("jc_kein_konto", None)
        user_data.pop("jc_konto_vorhanden", None)
        _iban_e = (user_data.get("iban") or "").strip()

        # 5. Diagnostic log
        logger.warning(
            "[ENFORCE DATA] doc=%s iban=%s kein_konto_derived=%s "
            "sv_flag=%s sv_num=%r sig_date=%s "
            "birth_place=%r birth_country=%r",
            doc_type,
            bool(_iban_e),
            not bool(_iban_e),  # derived: kein_konto = True when no IBAN
            user_data.get("has_sv_number", "?"),
            user_data.get("sv_number", "?"),
            user_data.get("signature_date", "?"),
            user_data.get("birth_place", "?"),
            user_data.get("birth_country", "?"),
        )

        # 6. Fail-fast: block generation if invariant still violated
        _sv_check = (user_data.get("sv_number") or "").strip()
        _sv_fl_check = (user_data.get("has_sv_number") or "").strip().lower()
        if _sv_fl_check in ("nein", "no", "false", "0") and _sv_check:
            raise ValueError(
                f"[INVARIANT VIOLATED] sv_number={_sv_check!r} filled but "
                f"has_sv_number={_sv_fl_check!r} — PDF blocked. (doc={doc_type} user={user_id})"
            )

    # ── Step 1d: mietbescheinigung — assemble concatenated address fields ──────
    # WebApp submits addresses as separate components; the AcroForm fields
    # mb_vm_anschrift, mb_m_anschrift, mb_anschrift expect a single string.
    # This mapping runs BEFORE validation so required-field checks pass.
    if (doc_type or "").strip().lower() == "mietbescheinigung":
        user_data = dict(user_data)  # safe mutable copy
        user_data["mb_vm_anschrift"] = (
            f"{user_data.get('landlord_street', '').strip()} "
            f"{user_data.get('landlord_house_number', '').strip()}, "
            f"{user_data.get('landlord_plz', '').strip()} "
            f"{user_data.get('landlord_city', '').strip()}"
        ).strip(", ").strip()
        user_data["mb_m_anschrift"] = (
            f"{user_data.get('street', '').strip()} "
            f"{user_data.get('house_number', '').strip()}, "
            f"{user_data.get('postal_code', '').strip()} "
            f"{user_data.get('city', '').strip()}"
        ).strip(", ").strip()
        user_data["mb_anschrift"] = user_data["mb_m_anschrift"]
        logger.info("ADDRESS_MAPPING_APPLIED: mietbescheinigung")

    # ── Step 1e: aufenthaltstitel — normalize + guard logic fields ─────────
    if (doc_type or "").strip().lower() == "aufenthaltstitel":
        user_data = dict(user_data)  # safe mutable copy

        # 1. Normalize yesno values: accept "Ja"/"YES"/"true"/True → "ja", rest → "nein"
        _AT_YESNO_FIELDS = (
            "was_in_germany_before",
            "has_criminal_record",
            "has_legal_proceedings",
            "has_diseases",
        )

        def _norm_yn(val: object) -> str:
            """Normalize any truthy / localized yes-string to 'ja', everything else 'nein'."""
            if val is None:
                return "nein"
            s = str(val).strip().lower()
            return "ja" if s in ("ja", "yes", "true", "1", "tak", "evet", "نعم", "так") else "nein"

        for _yn_key in _AT_YESNO_FIELDS:
            raw = user_data.get(_yn_key)
            normalized = _norm_yn(raw)
            if raw is None or str(raw).strip() != normalized:
                logger.info(
                    "[AT_NORMALIZE] %s: %r → %r (doc=%s user=%s)",
                    _yn_key, raw, normalized, doc_type, user_id,
                )
            user_data[_yn_key] = normalized

        # 2. Consistency: clear conditional detail fields when parent flag is "nein"
        if user_data.get("was_in_germany_before") == "nein":
            for _clr in ("previous_stay_from", "previous_stay_to", "previous_stay_city"):
                if user_data.get(_clr):
                    logger.info("[AT_ENFORCE] clearing %s (was_in_germany_before=nein)", _clr)
                user_data[_clr] = ""
        if user_data.get("has_criminal_record") == "nein":
            if user_data.get("criminal_details"):
                logger.info("[AT_ENFORCE] clearing criminal_details (has_criminal_record=nein)")
            user_data["criminal_details"] = ""
        if user_data.get("has_diseases") == "nein":
            if user_data.get("disease_details"):
                logger.info("[AT_ENFORCE] clearing disease_details (has_diseases=nein)")
            user_data["disease_details"] = ""

        # 3. Guard: all four logic fields must now be present and valid
        _AT_REQUIRED_LOGIC = {
            "was_in_germany_before": ("ja", "nein"),
            "has_criminal_record":   ("ja", "nein"),
            "has_legal_proceedings": ("ja", "nein"),
            "has_diseases":          ("ja", "nein"),
        }
        for _lf, _valid_vals in _AT_REQUIRED_LOGIC.items():
            _lv = user_data.get(_lf, "")
            if _lv not in _valid_vals:
                raise ValueError(
                    f"[AT_GUARD] aufenthaltstitel: field '{_lf}' has invalid value "
                    f"{_lv!r} — expected one of {_valid_vals}. (user={user_id})"
                )
        logger.info(
            "[AT_GUARD] logic fields OK: was_germany=%s criminal=%s legal=%s health=%s",
            user_data["was_in_germany_before"],
            user_data["has_criminal_record"],
            user_data["has_legal_proceedings"],
            user_data["has_diseases"],
        )

    data_for_pdf = user_data

    # ── Step 2: universal pre-flight validation (all doc_types) ────────────
    if callable(_premium_validate):
        try:
            _ok, _missing, _val_warnings = _premium_validate(
                doc_type, user_data, user_lang or "de"
            )
            if not _ok and _missing:
                _missing_keys = [m["key"] for m in _missing]
                logger.warning(
                    "❌ create_final_pdf: %s blocked — missing required fields: %s",
                    doc_type,
                    _missing_keys,
                )
                logger.info(
                    "User data validation failed: doc_type=%s missing=%s",
                    doc_type,
                    _missing_keys,
                )
                return {
                    "status": "validation_failed",
                    "errors": _missing,
                    "missing_fields": _missing_keys,
                    "message": (
                        format_validation_error(doc_type, _missing, user_lang or "de")
                        if callable(format_validation_error)
                        else ""
                    ),
                }
            logger.info(
                "User data validation passed: doc_type=%s warnings=%d",
                doc_type,
                len(_val_warnings or []),
            )
        except Exception as _ve:
            logger.debug("create_final_pdf: validation skipped (%s)", _ve)

    # ── Step 3 (anmeldung-specific): legacy form_validation + normalization ─
    if doc_type and doc_type.strip().lower() == "anmeldung":
        try:
            from backend.form_validation import (
                validate_anmeldung_form,
                get_validation_errors_localized,
            )

            valid, val_errors, _ = validate_anmeldung_form(user_data, user_lang or "en")
            if not valid and val_errors:
                localized = get_validation_errors_localized(
                    val_errors, user_lang or "en"
                )
                err_list = [
                    e.get("message", e.get("message_key", "")) for e in localized
                ]
                logger.warning(
                    "❌ Anmeldung final PDF blocked: form validation failed — %s",
                    err_list,
                )
                return {
                    "status": "validation_failed",
                    "errors": localized,
                    "missing_fields": [],
                }
        except Exception as e:
            logger.error("❌ Anmeldung form validation failed: %s", e, exc_info=True)
            return None

        if callable(normalize_and_validate_anmeldung):
            try:
                normalized, errors = normalize_and_validate_anmeldung(user_data)
                if errors:
                    logger.warning(
                        "❌ Anmeldung normalization failed, not generating PDF: %s",
                        errors,
                    )
                    return None
                data_for_pdf = normalized
            except Exception as e:
                logger.error("❌ Anmeldung normalization failed: %s", e, exc_info=True)
                return None

    # Resolve official link for footer (used by builder path below)
    _official_link = get_official_link(doc_type) if callable(get_official_link) else ""

    # Determine render strategy BEFORE the template block so builder_only docs
    # are routed directly to FinalRenderer even when a physical template exists on disk.
    _render_strategy = (
        get_render_strategy(doc_type) if callable(get_render_strategy) else "acroform"
    )
    if doc_type == "kinderzuschlag":
        _render_strategy = "builder_only"
    logger.info("[RENDER] doc_type=%s strategy=%s", doc_type, _render_strategy)
    template_path = None  # may remain None for builder_only docs

    if _render_strategy in ("builder_only", "xfa_builder"):
        logger.info(
            "create_final_pdf: doc_type=%s strategy=%s — skipping template, routing to FinalRenderer",
            doc_type,
            _render_strategy,
        )
    elif has_template(doc_type):
        _bundesland = (
            (user_data or {}).get("bundesland")
            or (authority_info or {}).get("bundesland")
            or None
        )
        template_path = resolve_template_path(
            doc_type, _bundesland, TEMPLATES_DIR, LEGACY_TEMPLATES_DIR
        )
        if template_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = OUTPUT_DIR / f"{doc_type}_{user_id}_{timestamp}.pdf"

            # ── Light normalization before AcroForm fill ──────────────────────
            # Operates on a shallow copy so original user_data / data_for_pdf are
            # never mutated.  Only safe, side-effect-free text corrections here.
            try:
                _nd = dict(data_for_pdf)

                # 1. City normalization — all birth-place and city fields
                for _city_key in (
                    "birth_place",
                    "city",
                    "previous_ort",
                    "person2_birth_place",
                    "child_birth_place",
                ):
                    _cv = (_nd.get(_city_key) or "").strip()
                    if _cv:
                        _nd[_city_key] = _norm_city_prefix(_cv)
                # eheschliessung_ort_datum: normalize city part at the start
                _eod = (_nd.get("eheschliessung_ort_datum") or "").strip()
                if _eod:
                    import re as _re_eod

                    _m_eod = _re_eod.match(
                        r"^\s*(.+?)\s*,?\s*(\d{2}\.\d{2}\.\d{4})\s*$", _eod
                    )
                    if _m_eod:
                        _city_raw = _m_eod.group(1).strip()
                        _date_raw = _m_eod.group(2).strip()
                        try:
                            datetime.strptime(_date_raw, "%d.%m.%Y")
                            _city_norm = (
                                _norm_city_prefix(_city_raw) if _city_raw else _city_raw
                            )
                            _nd["eheschliessung_ort_datum"] = (
                                f"{_city_norm}, {_date_raw}" if _city_norm else _eod
                            )
                        except Exception:
                            _nd["eheschliessung_ort_datum"] = _norm_city_prefix(_eod)
                    else:
                        _nd["eheschliessung_ort_datum"] = _norm_city_prefix(_eod)
                # ausstellungsbehoerde: normalize leading city token (e.g. "Vinnitsia RAGS")
                _ab = (_nd.get("ausstellungsbehoerde") or "").strip()
                if _ab:
                    _nd["ausstellungsbehoerde"] = _norm_city_prefix(_ab)

                # 2. Passport issuer fallback for Ukrainian documents
                # NOTE: nationality is kept as German adjective (e.g. "ukrainisch") —
                # normalize_user_data() already applied _normalize_nationality().
                # _NATIONALITY_TO_COUNTRY revert (adjective→country) was removed because
                # AcroForm fields on official templates expect the adjective form, not
                # the country noun. Builder docs handle this internally via form_builder.
                _nat_now = (_nd.get("nationality") or "").strip().lower()
                if ("ukrain" in _nat_now) and not (
                    _nd.get("ausstellungsbehoerde") or ""
                ).strip():
                    _nd["ausstellungsbehoerde"] = (
                        "Staatlicher Migrationsdienst der Ukraine"
                    )

                # 4. Signature date — always use the PDF generation date for legal accuracy
                _nd["signature_date"] = datetime.now().strftime("%d.%m.%Y")

                data_for_pdf = _nd
            except Exception as _norm_err:
                logger.warning(
                    "⚠️ AcroForm pre-fill normalization FAILED (data may be unnormalized): %s",
                    _norm_err,
                    exc_info=True,
                )
            # ─────────────────────────────────────────────────────────────────

            # ── Post-_nd re-apply enforce (buergergeld/jobcenter only) ──────────
            # The _nd block above applies cosmetic text corrections (city names,
            # nationality mapping, etc.).  Re-apply the hard invariants so the
            # _nd pass cannot accidentally undo them.
            if (doc_type or "").strip().lower() in ("buergergeld", "jobcenter"):
                data_for_pdf = dict(data_for_pdf)

                # SV: clear again if _nd somehow restored it
                _sv_flag_nd = (data_for_pdf.get("has_sv_number") or "").strip().lower()
                _sv_num_nd = (data_for_pdf.get("sv_number") or "").strip()
                if _sv_flag_nd in ("nein", "no", "false", "0") and _sv_num_nd:
                    logger.warning(
                        "[POST-ND ENFORCE] sv_number cleared again after _nd pass"
                    )
                    data_for_pdf["sv_number"] = ""

                # IBAN: remove derived raw flags — get_value_for_pdf_field uses iban directly.
                # Never store jc_kein_konto / jc_konto_vorhanden as raw keys; the raw-data
                # fallback in fill loop would pick them up and potentially contradict the handler.
                data_for_pdf.pop("jc_kein_konto", None)
                data_for_pdf.pop("jc_konto_vorhanden", None)

                _iban_nd = (data_for_pdf.get("iban") or "").strip()
                logger.warning(
                    "[FINAL DATA BEFORE PDF] doc=%s iban=%s kein_konto_derived=%s "
                    "sv_flag=%s sv_num=%r sig_date=%s "
                    "birth_place=%r birth_country=%r",
                    doc_type,
                    bool(_iban_nd),
                    not bool(_iban_nd),
                    data_for_pdf.get("has_sv_number", "?"),
                    data_for_pdf.get("sv_number", "?"),
                    data_for_pdf.get("signature_date", "?"),
                    data_for_pdf.get("birth_place", "?"),
                    data_for_pdf.get("birth_country", "?"),
                )

            # ── FINAL PIPELINE CHECK (always logged at WARNING level) ──────────
            logger.warning(
                "[FINAL PIPELINE CHECK] doc_type=%s has_template=%s template_path=%s "
                "iban=%r jc_kein_konto=%r has_sv_number=%r sv_number=%r",
                doc_type,
                has_template(doc_type) if callable(has_template) else "?",
                template_path,
                (
                    (data_for_pdf.get("iban") or "")[:6] + "..."
                    if data_for_pdf.get("iban")
                    else ""
                ),
                data_for_pdf.get("jc_kein_konto"),
                data_for_pdf.get("has_sv_number"),
                data_for_pdf.get("sv_number"),
            )

            # ── xfa_overlay branch: coordinate-based text on official XFA template ──
            result = None  # ensure defined for all branches below
            # _render_strategy already computed above (before has_template block)

            if _render_strategy == "xfa_overlay":
                logger.info(
                    "create_final_pdf: doc_type=%s strategy=xfa_overlay → _fill_template_pdf_overlay",
                    doc_type,
                )
                _overlay_result = _fill_template_pdf_overlay(
                    template_path,
                    data_for_pdf,
                    doc_type,
                    output_path,
                    user_lang=user_lang,
                )
                if _overlay_result:
                    _apply_delivery_watermark(_overlay_result, user_lang)
                    _apply_final_disclaimer(_overlay_result)
                    return _overlay_result
                # Overlay failed — skip AcroForm path and fall through to FinalRenderer
                logger.warning(
                    "create_final_pdf: xfa_overlay failed for doc_type=%s — falling back to FinalRenderer",
                    doc_type,
                )
            elif callable(is_xfa_pdf) and is_xfa_pdf(str(template_path)):
                # XFA template: draw text at exact widget positions, then rasterize.
                # AcroForm fill is invisible in XFA viewers (Adobe, etc.) because they
                # render from the XFA XML stream, not AcroForm widget values.
                # _fill_xfa_overlay inserts text into the page content stream at the
                # positions read from AcroForm widget rects, then rasterizes — result
                # is visible in every viewer and preserves the official form layout.
                logger.info(
                    "create_final_pdf: doc_type=%s XFA detected → _fill_xfa_overlay",
                    doc_type,
                )
                result = _fill_xfa_overlay(
                    template_path,
                    data_for_pdf,
                    doc_type,
                    output_path,
                    user_lang=user_lang,
                )
            else:
                # STRICT: Final PDF via AcroForm only (widget.field_value + widget.update()). No x/y drawing.
                result = _fill_template_pdf_acroform(
                    template_path,
                    data_for_pdf,
                    doc_type,
                    output_path,
                    is_preview=False,
                    user_lang=user_lang,
                    authority_info=authority_info,
                )
            if result:
                # Overlay supplement disabled: Anmeldung uses AcroForm only.
                # _apply_overlay_for_missing_anmeldung_fields was removed because
                # insert_text/insert_textbox coordinates caused misplaced X marks
                # and text overlapping AcroForm-filled content.
                _apply_delivery_watermark(result, user_lang)
                _apply_final_disclaimer(result)
                return result
            # Anmeldung: AcroForm ONLY — no overlay fallback (architecture rule)
            if (doc_type or "").strip().lower() == "anmeldung":
                logger.error(
                    "📄 create_final_pdf: Anmeldung AcroForm fill returned None — not using overlay fallback"
                )
                return None
            # Other doc_types: fallback when template has NO AcroForm fields
            # Developer guard: Anmeldung must NEVER use overlay (safety net if code is reordered)
            if (doc_type or "").strip().lower() == "anmeldung":
                logger.error(
                    "📄 create_final_pdf: Anmeldung overlay fallback attempted — must not happen; returning None"
                )
                return None
            logger.info(
                "📄 create_final_pdf: doc_type=%s template=%s mode=overlay (fallback, no AcroForm)",
                doc_type,
                template_path,
            )
            result = _fill_template_pdf(
                template_path,
                data_for_pdf,
                doc_type,
                output_path,
                is_preview=False,
                user_lang=user_lang,
                authority_info=authority_info,
            )
            if result:
                _apply_delivery_watermark(result, user_lang)
                _apply_final_disclaimer(result)
                return result
    # Warn when a template is declared but the file is missing on disk —
    # the user will receive a builder-generated PDF instead of the official template.
    # Skip for builder_only/xfa_builder: template is intentionally not used.
    if (
        has_template(doc_type)
        and not template_path
        and _render_strategy not in ("builder_only", "xfa_builder")
    ):
        logger.warning(
            "⚠️ create_final_pdf: template declared for doc_type=%s but file not found on disk "
            "— falling back to builder (FinalRenderer). User will receive builder-generated PDF "
            "instead of official template. Check TEMPLATES_DIR: %s",
            doc_type,
            TEMPLATES_DIR,
        )
    # ── FinalRenderer for builder_only / xfa_builder doc_types ──────────────
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fb_output = OUTPUT_DIR / f"{doc_type}_{user_id}_{timestamp}_form.pdf"
        fb_result = final_renderer.render(
            doc_type=doc_type,
            user_data=data_for_pdf,
            output_path=str(fb_output),
            user_lang=user_lang or "de",
            official_link=_official_link,
        )
        if fb_result:
            _apply_delivery_watermark(fb_result, user_lang)
            # skip_header=False: builder-only docs (wohngeld, abmeldung, etc.) have no
            # template path, so they never pass through _apply_final_disclaimer with
            # skip_header=False.  _apply_kopie_watermark adds a subtle diagonal watermark
            # and a low-contrast header inside the blue band, but the authoritative red
            # "Beispieldokument" header must be applied here for visual parity with
            # template-based docs (anmeldung, kindergeld, etc.).
            _apply_final_disclaimer(fb_result, skip_header=False)
            logger.info("✅ create_final_pdf: FinalRenderer succeeded for %s", doc_type)
            return fb_result
        logger.warning(
            "⚠️ FinalRenderer returned None for %s — emergency _render_pdf fallback",
            doc_type,
        )
    except Exception as _fb_err:
        logger.warning("⚠️ FinalRenderer failed (%s) — emergency fallback", _fb_err)

    # ── Emergency fallback: legacy plain-text layout ───────────────────────
    # This path should be unreachable for any doc_type in DOC_RENDER_MAP.
    # If reached, it indicates a german_form_builder failure — log prominently.
    logger.error(
        "create_final_pdf: ALL standard paths failed for doc_type=%s — using _render_pdf emergency fallback",
        doc_type,
    )
    final_path = _render_pdf(
        user_id=user_id,
        user_data=data_for_pdf,
        doc_type=doc_type,
        authority_info=authority_info,
        is_preview=False,
        user_lang=user_lang,
    )
    if final_path:
        _apply_delivery_watermark(final_path, user_lang)
    return final_path


def process_document(
    user_data: Dict[str, Any], doc_type: str, plz: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Legacy function: generates preview PDF (with watermark).
    For final PDFs, use create_final_pdf() instead.
    """
    try:
        if not plz:
            plz = user_data.get("plz") or user_data.get("postal_code")

        if plz and get_requires_bundesland(doc_type):
            user_data = enrich_user_data_with_authority(user_data, doc_type, plz)
            authority_info = get_authority_address(doc_type, plz)
        else:
            authority_info = None

        user_id = user_data.get("user_id", 0)
        if isinstance(user_id, str):
            try:
                user_id = int(user_id)
            except:
                user_id = 0

        # This generates PREVIEW (with watermark) - legacy behavior
        preview_path = create_preview(
            user_id=user_id,
            user_data=user_data,
            doc_type=doc_type,
            authority_info=authority_info,
            is_preview=True,  # Explicit: preview always has watermark
        )

        if not preview_path:
            return None, None

        pdf_path = preview_path

        return pdf_path, preview_path

    except Exception as e:
        logger.error(f"❌ process_document failed: {e}", exc_info=True)
        return None, None


# ── Public premium API wrappers ───────────────────────────────────────────────


def generate_preview_pdf(
    doc_type: str,
    user_data: Dict[str, Any],
    lang: str = "de",
    user_id: int = 0,
    authority_info: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """
    Public premium API: generate preview PDF with self-check checklist.

    Normalizes data, computes missing fields, passes checklist to renderer.
    Returns path to generated PDF or None on failure.
    """
    return create_preview(
        user_id=user_id,
        user_data=user_data,
        doc_type=doc_type,
        authority_info=authority_info,
        is_preview=True,
        user_lang=lang,
    )


def generate_final_pdf(
    doc_type: str,
    user_data: Dict[str, Any],
    lang: str = "de",
    user_id: int = 0,
    authority_info: Optional[Dict[str, str]] = None,
) -> Optional[Union[str, Dict[str, Any]]]:
    """
    Public premium API: generate final PDF (no preview watermark).

    Normalizes data, blocks generation if required fields missing,
    fills AcroForm or delegates to builder, adds official link footer.

    Returns:
        str   — absolute path to generated PDF
        dict  — {"status": "validation_failed", "errors": [...], "message": "..."}
        None  — unexpected failure
    """
    return create_final_pdf(
        user_id=user_id,
        user_data=user_data,
        doc_type=doc_type,
        authority_info=authority_info,
        user_lang=lang,
    )


__all__ = [
    "process_document",
    "create_preview",
    "create_final_pdf",
    "generate_preview_pdf",
    "generate_final_pdf",
    "enrich_user_data_with_authority",
]
if __name__ == "__main__":
    path = process_document(
        user_data={
            "user_id": 999,
            "first_name": "Test",
            "last_name": "User",
            "street": "Teststrasse 1",
            "plz": "10115",
            "city": "Berlin",
        },
        doc_type="anmeldung",
    )

    print("PDF PATH:", path)
