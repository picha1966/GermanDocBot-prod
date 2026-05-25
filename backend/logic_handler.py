# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - Logic Handler
PDF генерація з динамічною маршрутизацією
FIXED: Return values, paths, WebApp data normalization
"""

import os
import asyncio
from datetime import datetime, date
from typing import Tuple, Optional, Dict, Any
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

from PIL import Image, ImageDraw, ImageFont

try:
    from document_handlers import get_document_config, DocumentConfig, AUTOFILL_GROUPS
    from validators import transliterate_ua_to_latin, has_cyrillic, validate_field, LATIN_ONLY_FIELDS
    from geo_helper import GeoHelper, get_bundesland, get_authority_address, format_authority
    from translations import TRANSLATIONS, get_document_name, get_text
    from rtl_fix import prepare_rtl_text, is_rtl_language, format_for_pdf
    from settings import settings
except ImportError:
    from backend.document_handlers import get_document_config, DocumentConfig, AUTOFILL_GROUPS
    from backend.validators import transliterate_ua_to_latin, has_cyrillic, validate_field, LATIN_ONLY_FIELDS
    from backend.geo_helper import GeoHelper, get_bundesland, get_authority_address, format_authority
    from backend.translations import TRANSLATIONS, get_document_name, get_text
    from backend.rtl_fix import prepare_rtl_text, is_rtl_language, format_for_pdf
    from backend.settings import settings


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOCS_DIR = os.path.join(ROOT_DIR, settings.pdf.DOCS_DIR)
PREVIEWS_DIR = os.path.join(ROOT_DIR, settings.pdf.PREVIEWS_DIR)
TEMPLATES_DIR = os.path.join(ROOT_DIR, settings.pdf.TEMPLATES_DIR)
FONTS_DIR = os.path.join(ROOT_DIR, settings.pdf.FONTS_DIR)

for directory in [DOCS_DIR, PREVIEWS_DIR, TEMPLATES_DIR, FONTS_DIR]:
    os.makedirs(directory, exist_ok=True)


def normalize_webapp_data(webapp_data: dict) -> dict:
    """Нормалізувати дані з WebApp перед обробкою"""
    user_data = webapp_data.get('user_answers', {})
    user_data = {k: v for k, v in user_data.items() if v}
    user_data = _auto_transliterate(user_data)
    return user_data


async def process_user_data_to_pdf(
    user_id: int,
    doc_type: str,
    user_data: Dict[str, Any],
    auto_transliterate: bool = True,
    generate_cover_letter: bool = False,
    user_lang: str = 'de'
) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns:
        Tuple[main_pdf_path, preview_path]
    """
    config = get_document_config(doc_type)
    if not config:
        return None, None
    
    if auto_transliterate:
        user_data = _auto_transliterate(user_data)
    
    if is_rtl_language(user_lang):
        user_data = _process_rtl_data(user_data, user_lang)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_filename = f"{doc_type}_{user_id}_{timestamp}"
    
    main_pdf_path = os.path.join(DOCS_DIR, f"{base_filename}.pdf")
    preview_path = os.path.join(PREVIEWS_DIR, f"{base_filename}_preview.png")
    
    plz = user_data.get('postal_code', '')
    template_path = config.get_template_path(plz, TEMPLATES_DIR)
    
    try:
        main_pdf_path = await _generate_document_pdf(
            config, user_data, main_pdf_path, template_path, user_lang
        )
    except Exception as e:
        print(f"Error generating main PDF: {e}")
        main_pdf_path = await _generate_simple_pdf(config, user_data, main_pdf_path, user_lang)
    
    if not main_pdf_path:
        return None, None
    
    preview_path = await _generate_preview(main_pdf_path, preview_path)
    
    return main_pdf_path, preview_path


def _process_rtl_data(user_data: Dict[str, Any], lang: str) -> Dict[str, Any]:
    result = {}
    for key, value in user_data.items():
        if isinstance(value, str):
            result[key] = format_for_pdf(value, lang)
        else:
            result[key] = value
    return result


async def _generate_document_pdf(
    config: DocumentConfig,
    user_data: Dict[str, Any],
    output_path: str,
    template_path: str = None,
    user_lang: str = 'de'
) -> Optional[str]:
    if template_path and os.path.exists(template_path):
        return await _fill_pdf_template(template_path, user_data, output_path)
    return await _generate_simple_pdf(config, user_data, output_path, user_lang)


async def _generate_simple_pdf(
    config: DocumentConfig,
    user_data: Dict[str, Any],
    output_path: str,
    user_lang: str = 'de'
) -> Optional[str]:
    try:
        c = canvas.Canvas(output_path, pagesize=A4)
        page_width, page_height = A4
        margin = 25 * mm
        
        is_rtl = is_rtl_language(user_lang)
        y = page_height - margin
        
        c.setFont("Helvetica-Bold", 16)
        title = config.get_name('de')
        c.drawCentredString(page_width / 2, y, title)
        y -= 30
        
        c.setFont("Helvetica", 10)
        c.drawRightString(page_width - margin, y, f"Datum: {datetime.now().strftime('%d.%m.%Y')}")
        y -= 20
        
        c.setStrokeColor(HexColor('#333333'))
        c.line(margin, y, page_width - margin, y)
        y -= 25
        
        c.setFont("Helvetica", 11)
        
        field_groups = [
            ('Persönliche Daten', ['first_name', 'last_name', 'birth_date', 'birth_place', 'nationality', 'gender']),
            ('Anschrift', ['address', 'street', 'house_number', 'postal_code', 'city']),
            ('Kontakt', ['phone', 'email']),
            ('Bankverbindung', ['iban', 'bic', 'bank_name', 'account_holder']),
            ('Angaben zum Kind', ['child_name', 'child_first_name', 'child_last_name', 'child_birth_date']),
            ('Sonstiges', []),
        ]
        
        printed_fields = set()
        
        for group_name, group_fields in field_groups:
            fields_with_data = []
            for field in group_fields:
                if field in user_data and user_data[field]:
                    fields_with_data.append(field)
                    printed_fields.add(field)
            
            if fields_with_data:
                c.setFont("Helvetica-Bold", 11)
                c.drawString(margin, y, group_name)
                y -= 15
                
                c.setFont("Helvetica", 10)
                for field in fields_with_data:
                    label = _get_field_label(field)
                    value = str(user_data[field])
                    c.drawString(margin + 5*mm, y, f"{label}: {value}")
                    y -= 12
                y -= 10
        
        other_fields = [f for f in user_data.keys() if f not in printed_fields and user_data[f]]
        if other_fields:
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin, y, "Weitere Angaben")
            y -= 15
            
            c.setFont("Helvetica", 10)
            for field in other_fields:
                label = _get_field_label(field)
                value = str(user_data[field])
                c.drawString(margin + 5*mm, y, f"{label}: {value}")
                y -= 12
        
        y -= 30
        c.setFont("Helvetica", 10)
        c.line(margin, y, margin + 60*mm, y)
        y -= 12
        c.drawString(margin, y, "Unterschrift")
        c.drawString(margin + 80*mm, y + 12, f"Datum: {datetime.now().strftime('%d.%m.%Y')}")
        
        c.save()
        return output_path
    except Exception as e:
        print(f"Error generating simple PDF: {e}")
        return None


async def _fill_pdf_template(template_path: str, user_data: Dict[str, Any], output_path: str) -> Optional[str]:
    import shutil
    try:
        if os.path.exists(template_path):
            shutil.copy(template_path, output_path)
            return output_path
    except:
        pass
    return None


async def _generate_preview(pdf_path: str, output_path: str) -> Optional[str]:
    try:
        img_width, img_height = 595, 842
        img = Image.new('RGB', (img_width, img_height), 'white')
        draw = ImageDraw.Draw(img)
        
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        watermark_text = "PREVIEW"
        watermark = Image.new('RGBA', (img_width, img_height), (255, 255, 255, 0))
        watermark_draw = ImageDraw.Draw(watermark)
        
        for i in range(-2, 4):
            for j in range(-2, 4):
                x = img_width // 2 + i * 200
                y = img_height // 2 + j * 150
                watermark_draw.text((x, y), watermark_text, font=font_large, fill=(200, 200, 200, 128), anchor='mm')
        
        watermark = watermark.rotate(45, expand=False, center=(img_width//2, img_height//2))
        img.paste(watermark, (0, 0), watermark)
        draw.rectangle([0, 0, img_width, 50], fill='#ff6b6b')
        
        try:
            draw.text((img_width // 2, 25), "⚠️ PREVIEW COPY - NOT FOR OFFICIAL USE ⚠️", font=font_small, fill='white', anchor='mm')
        except:
            draw.text((100, 15), "PREVIEW COPY - NOT FOR OFFICIAL USE", fill='white')
        
        img.save(output_path, 'PNG', quality=85)
        return output_path
    except Exception as e:
        print(f"Error generating preview: {e}")
        return None


def _auto_transliterate(user_data: Dict[str, Any]) -> Dict[str, Any]:
    result = {}
    for key, value in user_data.items():
        if isinstance(value, str) and key in LATIN_ONLY_FIELDS:
            if has_cyrillic(value):
                result[key] = transliterate_ua_to_latin(value)
            else:
                result[key] = value
        else:
            result[key] = value
    return result


def _get_field_label(field_name: str) -> str:
    labels = {
        'first_name': 'Vorname', 'last_name': 'Nachname', 'birth_name': 'Geburtsname',
        'birth_date': 'Geburtsdatum', 'birth_place': 'Geburtsort', 'birth_country': 'Geburtsland',
        'nationality': 'Staatsangehörigkeit', 'gender': 'Geschlecht', 'marital_status': 'Familienstand',
        'religion': 'Religionszugehörigkeit', 'street': 'Straße', 'house_number': 'Hausnummer',
        'address': 'Adresse', 'address_addition': 'Adresszusatz', 'postal_code': 'Postleitzahl',
        'city': 'Ort', 'country': 'Land', 'phone': 'Telefon', 'mobile': 'Mobil', 'email': 'E-Mail',
        'tax_id': 'Steuer-ID', 'social_security_number': 'Sozialversicherungsnummer',
        'iban': 'IBAN', 'bic': 'BIC', 'bank_name': 'Kreditinstitut', 'account_holder': 'Kontoinhaber',
        'child_name': 'Name des Kindes', 'child_first_name': 'Vorname des Kindes',
        'child_last_name': 'Nachname des Kindes', 'child_birth_date': 'Geburtsdatum des Kindes',
        'child_birth_place': 'Geburtsort des Kindes', 'child_nationality': 'Staatsangehörigkeit des Kindes',
        'child_gender': 'Geschlecht des Kindes', 'relationship_to_child': 'Verhältnis zum Kind',
        'spouse_first_name': 'Vorname des Ehepartners', 'spouse_last_name': 'Nachname des Ehepartners',
        'spouse_birth_date': 'Geburtsdatum des Ehepartners', 'spouse_tax_id': 'Steuer-ID des Ehepartners',
        'marriage_date': 'Heiratsdatum', 'move_in_date': 'Einzugsdatum', 'move_out_date': 'Auszugsdatum',
        'previous_address': 'Frühere Anschrift', 'landlord_name': 'Name des Vermieters',
        'landlord_address': 'Adresse des Vermieters', 'rent_amount': 'Miete (EUR)',
        'living_space': 'Wohnfläche (m²)', 'number_of_rooms': 'Zimmeranzahl',
        'household_members': 'Haushaltsmitglieder', 'employer_name': 'Arbeitgeber',
        'employer_address': 'Adresse des Arbeitgebers', 'employment_start_date': 'Beschäftigungsbeginn',
        'occupation': 'Beruf', 'monthly_income': 'Monatliches Bruttoeinkommen (EUR)',
        'signature_place': 'Ort', 'signature_date': 'Datum', 'reason': 'Grund', 'notes': 'Anmerkungen',
    }
    return labels.get(field_name, field_name.replace('_', ' ').title())


async def validate_user_input(field_name: str, value: str, lang: str = 'ua') -> Tuple[bool, str, Optional[str]]:
    """Валідація введених даних користувача"""
    result = validate_field(field_name, value, lang)
    message = result.get_message(lang)
    return result.is_valid, message, result.suggestion


def get_authority_info_for_document(doc_type: str, plz: str, lang: str = 'de') -> str:
    """Отримання інформації про відомство (адреса, контакти)"""
    return format_authority(doc_type, plz, lang)


async def _fill_pdf_template(template_path: str, user_data: Dict[str, Any], output_path: str) -> Optional[str]:
    """
    ЗАПОВНЕННЯ ФОРМ PDF: Вписує дані користувача безпосередньо в інтерактивні поля шаблону.
    """
    try:
        import pdfrw
        
        template = pdfrw.PdfReader(template_path)
        
        for page in template.pages:
            annotations = page['/Annots']
            if annotations:
                for annotation in annotations:
                    # Перевіряємо, чи це поле для введення тексту (/Widget)
                    if annotation['/Subtype'] == '/Widget' and annotation['/T']:
                        # Отримуємо ім'я поля (наприклад, 'first_name')
                        key = annotation['/T'][1:-1]
                        
                        if key in user_data:
                            val = str(user_data[key])
                            # Оновлюємо значення поля (/V)
                            annotation.update(pdfrw.PdfDict(V=f"({val})"))
                            # Скидаємо зовнішній вигляд для коректного рендерингу
                            annotation.update(pdfrw.PdfDict(AP=""))

        # Дозволяємо системі відображати заповнені дані
        if not template.Root.AcroForm:
            template.Root.update(pdfrw.PdfDict(AcroForm=pdfrw.PdfDict()))
        template.Root.AcroForm.update(pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject('true')))
        
        pdfrw.PdfWriter().write(output_path, template)
        return output_path
        
    except Exception as e:
        print(f"❌ Помилка заповнення шаблону PDF: {e}")
        return None


async def _generate_preview_image(pdf_path: str, output_path: str) -> Optional[str]:
    """
    ГЕНЕРАЦІЯ ПРЕВ'Ю: Створює візуальну копію документа з ватермаркою.
    """
    try:
        from pdf2image import convert_from_path
        
        images = convert_from_path(pdf_path, first_page=1, last_page=1)
        
        if images:
            img = images[0]
            draw = ImageDraw.Draw(img)
            try:
                font_path = os.path.join(FONTS_DIR, "DejaVuSans.ttf")
                font = ImageFont.truetype(font_path, 70) if os.path.exists(font_path) else ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            # Малюємо захисну ватермарку
            draw.text((100, 400), "PREVIEW - NO VALUE", font=font, fill=(200, 200, 200))
            
            img.save(output_path, 'PNG', quality=70)
            return output_path
            
    except Exception as e:
        print(f"⚠️ Помилка створення картинки-прев'ю: {e}")
        return output_path