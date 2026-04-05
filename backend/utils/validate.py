# -*- coding: utf-8 -*-
"""
backend/utils/validate.py — Per-doc-type pre-flight validation.

validate_user_data(doc_type, user_data, lang)
  -> (ok: bool, missing: List[dict], warnings: List[dict])

Each list item: {"key": str, "label": str, "message": str}
"""
import logging
import re
from datetime import datetime, date
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── Localized field labels ─────────────────────────────────────────────────────
# fmt: off
_FIELD_LABELS: Dict[str, Dict[str, str]] = {
    "first_name":       {"de": "Vorname",                   "en": "First name",            "uk": "Ім'я",                  "pl": "Imię",               "tr": "Ad",               "ar": "الاسم الأول"},
    "last_name":        {"de": "Nachname",                  "en": "Last name",             "uk": "Прізвище",              "pl": "Nazwisko",           "tr": "Soyad",            "ar": "اسم العائلة"},
    "birth_date":       {"de": "Geburtsdatum",              "en": "Date of birth",         "uk": "Дата народження",       "pl": "Data urodzenia",     "tr": "Doğum tarihi",     "ar": "تاريخ الميلاد"},
    "street":           {"de": "Straße",                    "en": "Street",                "uk": "Вулиця",                "pl": "Ulica",              "tr": "Sokak",            "ar": "الشارع"},
    "house_number":     {"de": "Hausnummer",                "en": "House number",          "uk": "Номер будинку",         "pl": "Nr domu",            "tr": "Kapı numarası",    "ar": "رقم المنزل"},
    "plz":              {"de": "Postleitzahl (PLZ)",        "en": "Postal code",           "uk": "Поштовий індекс",       "pl": "Kod pocztowy",       "tr": "Posta kodu",       "ar": "الرمز البريدي"},
    "city":             {"de": "Stadt / Ort",               "en": "City",                  "uk": "Місто",                 "pl": "Miasto",             "tr": "Şehir",            "ar": "المدينة"},
    "nationality":      {"de": "Staatsangehörigkeit",       "en": "Nationality",           "uk": "Громадянство",          "pl": "Obywatelstwo",       "tr": "Uyruk",            "ar": "الجنسية"},
    "move_in_date":     {"de": "Einzugsdatum",              "en": "Move-in date",          "uk": "Дата в'їзду",           "pl": "Data przeprowadzki", "tr": "Taşınma tarihi",   "ar": "تاريخ الانتقال"},
    "landlord_name":    {"de": "Name des Wohnungsgebers",   "en": "Landlord / owner name", "uk": "ПІБ орендодавця",       "pl": "Imię wynajmującego", "tr": "Ev sahibi adı",    "ar": "اسم المالك"},
    "iban":             {"de": "IBAN",                      "en": "IBAN",                  "uk": "IBAN",                  "pl": "IBAN",               "tr": "IBAN",             "ar": "IBAN"},
    "tax_id":           {"de": "Steuer-ID / Steuernummer",  "en": "Tax ID",                "uk": "Податковий номер",      "pl": "Numer podatkowy",    "tr": "Vergi kimlik no.", "ar": "الرقم الضريبي"},
    "employer_name":    {"de": "Name des Arbeitgebers",     "en": "Employer name",         "uk": "Назва роботодавця",     "pl": "Nazwa pracodawcy",   "tr": "İşveren adı",      "ar": "اسم صاحب العمل"},
    "income":           {"de": "Monatliches Einkommen",     "en": "Monthly income",        "uk": "Місячний дохід",        "pl": "Dochód miesięczny",  "tr": "Aylık gelir",      "ar": "الدخل الشهري"},
    "child_name":       {"de": "Name des Kindes",           "en": "Child's name",          "uk": "Ім'я дитини",           "pl": "Imię dziecka",       "tr": "Çocuk adı",        "ar": "اسم الطفل"},
    "child_birth_date": {"de": "Geburtsdatum des Kindes",   "en": "Child's date of birth", "uk": "Дата народження дитини","pl": "Data ur. dziecka",   "tr": "Çocuk doğum tar.", "ar": "تاريخ ميلاد الطفل"},
    "new_street":       {"de": "Neue Straße",               "en": "New street",            "uk": "Нова вулиця",           "pl": "Nowa ulica",         "tr": "Yeni sokak",       "ar": "الشارع الجديد"},
    "new_house_number": {"de": "Neue Hausnummer",           "en": "New house number",      "uk": "Новий номер будинку",   "pl": "Nowy nr domu",       "tr": "Yeni kapı no.",    "ar": "رقم المنزل الجديد"},
    "new_plz":          {"de": "Neue PLZ",                  "en": "New postal code",       "uk": "Новий поштовий індекс", "pl": "Nowy kod pocztowy",  "tr": "Yeni posta kodu",  "ar": "الرمز البريدي الجديد"},
    "new_city":         {"de": "Neue Stadt / Ort",          "en": "New city",              "uk": "Нове місто",            "pl": "Nowe miasto",        "tr": "Yeni şehir",       "ar": "المدينة الجديدة"},
    "phone":            {"de": "Telefonnummer",             "en": "Phone number",          "uk": "Телефон",               "pl": "Numer telefonu",     "tr": "Telefon numarası", "ar": "رقم الهاتف"},
    "person2_last_name":  {"de": "Person 2: Familienname",   "en": "Person 2: Last name",   "uk": "Особа 2: Прізвище",     "pl": "Osoba 2: Nazwisko",  "tr": "Kişi 2: Soyad",    "ar": "الشخص 2: اسم العائلة"},
    "person2_first_name": {"de": "Person 2: Vornamen",       "en": "Person 2: First name",  "uk": "Особа 2: Ім'я",         "pl": "Osoba 2: Imię",      "tr": "Kişi 2: Ad",        "ar": "الشخص 2: الاسم الأول"},
    "person2_birth_date": {"de": "Person 2: Geburtsdatum",   "en": "Person 2: Date of birth","uk": "Особа 2: Дата народження","pl": "Osoba 2: Data ur.",  "tr": "Kişi 2: Doğum tar.","ar": "الشخص 2: تاريخ الميلاد"},
    "email":            {"de": "E-Mail-Adresse",            "en": "E-mail address",        "uk": "Електронна пошта",      "pl": "Adres e-mail",       "tr": "E-posta adresi",   "ar": "البريد الإلكتروني"},
    "passport_number":  {"de": "Ausweis- / Passnummer",    "en": "Passport / ID number",  "uk": "Номер паспорта",        "pl": "Nr paszportu/dowodu","tr": "Pasaport / kimlik no.","ar": "رقم جواز السفر"},
    "family_status":    {"de": "Familienstand",             "en": "Marital status",        "uk": "Сімейний стан",         "pl": "Stan cywilny",       "tr": "Medeni durum",     "ar": "الحالة الاجتماعية"},
    "familienstand":    {"de": "Familienstand",             "en": "Marital status",        "uk": "Сімейний стан",         "pl": "Stan cywilny",       "tr": "Medeni durum",     "ar": "الحالة الاجتماعية"},
    "gender":           {"de": "Geschlecht",                "en": "Gender",                "uk": "Стать",                 "pl": "Płeć",               "tr": "Cinsiyet",         "ar": "الجنس"},
    "postal_code":      {"de": "Postleitzahl (PLZ)",        "en": "Postal code",           "uk": "Поштовий індекс",       "pl": "Kod pocztowy",       "tr": "Posta kodu",       "ar": "الرمز البريدي"},
    "partner_birth_date": {"de": "Geburtsdatum Partner",    "en": "Partner date of birth", "uk": "Дата народження партнера", "pl": "Data ur. partnera", "tr": "Partner doğum tarihi", "ar": "تاريخ ميلاد الشريك"},
    "partner_nationality": {"de": "Staatsangehörigkeit Partner", "en": "Partner nationality", "uk": "Громадянство партнера", "pl": "Obywatelstwo partnera", "tr": "Partner uyruğu", "ar": "جنسية الشريك"},
    "child1_last_name": {"de": "Familienname Kind 1",      "en": "Child 1 last name",     "uk": "Прізвище дитини 1",     "pl": "Nazwisko dziecka 1", "tr": "1. çocuk soyadı", "ar": "اسم عائلة الطفل 1"},
    "child1_first_name": {"de": "Vorname Kind 1",           "en": "Child 1 first name",    "uk": "Ім'я дитини 1",         "pl": "Imię dziecka 1",     "tr": "1. çocuk adı",    "ar": "الاسم الأول للطفل 1"},
    "child1_birth_date": {"de": "Geburtsdatum Kind 1",      "en": "Child 1 date of birth", "uk": "Дата народження дитини 1", "pl": "Data ur. dziecka 1", "tr": "1. çocuk doğum tarihi", "ar": "تاريخ ميلاد الطفل 1"},
    "kiz_confirm_truth": {"de": "Wahrheitsbestätigung",     "en": "Truth confirmation",    "uk": "Підтвердження правдивості", "pl": "Potwierdzenie prawdziwości", "tr": "Doğruluk onayı", "ar": "تأكيد صحة البيانات"},
    "kiz_ack_processing": {"de": "Bearbeitungshinweis",    "en": "Processing acknowledgment", "uk": "Підтвердження щодо обробки", "pl": "Potwierdzenie przetwarzania", "tr": "İşlem bildirimi", "ar": "إقرار المعالجة"},
    "birth_place":      {"de": "Geburtsort / -land",        "en": "Place of birth",        "uk": "Місце народження",      "pl": "Miejsce urodzenia",  "tr": "Doğum yeri",       "ar": "مكان الميلاد"},
    "signature_date":   {"de": "Datum der Unterschrift",    "en": "Signature date",        "uk": "Дата підпису",          "pl": "Data podpisu",       "tr": "İmza tarihi",      "ar": "تاريخ التوقيع"},
    "household_members":{"de": "Anzahl Haushaltsmitglieder","en": "Household members",     "uk": "Членів домогосподарства","pl": "Członkowie gosp.",   "tr": "Hane üyeleri",     "ar": "أفراد الأسرة"},
    "monthly_rent":     {"de": "Kaltmiete (€)",             "en": "Monthly rent (€)",      "uk": "Орендна плата (€)",     "pl": "Czynsz miesięczny",  "tr": "Aylık kira (€)",   "ar": "الإيجار الشهري"},
    "dokumentenart":    {"de": "Dokumentenart",             "en": "Document type",         "uk": "Тип документа",         "pl": "Rodzaj dokumentu",   "tr": "Belge türü",       "ar": "نوع الوثيقة"},
    "seriennummer":     {"de": "Dokumentennummer",          "en": "Document number",       "uk": "Номер документа",       "pl": "Numer dokumentu",    "tr": "Belge numarası",   "ar": "رقم الوثيقة"},
    "ausstellungsbehoerde": {"de": "Ausstellungsbehörde",   "en": "Issuing authority",     "uk": "Орган видачі",          "pl": "Organ wydający",     "tr": "Veren kurum",      "ar": "جهة الإصدار"},
    "ausstellungsdatum":{"de": "Ausstellungsdatum",         "en": "Issue date",            "uk": "Дата видачі",           "pl": "Data wydania",       "tr": "Düzenlenme tarihi","ar": "تاريخ الإصدار"},
    "gueltig_bis":      {"de": "Gültig bis",                "en": "Valid until",           "uk": "Дійсний до",            "pl": "Ważny do",           "tr": "Geçerlilik tarihi","ar": "صالح حتى"},
    "residence_purpose":{"de": "Aufenthaltszweck",          "en": "Purpose of residence",  "uk": "Мета перебування",      "pl": "Cel pobytu",         "tr": "İkamet amacı",     "ar": "غرض الإقامة"},
    # Mietbescheinigung composite textarea keys
    "mb_vm_anschrift":  {"de": "Vermieter: Name und Anschrift",  "en": "Landlord name and address",  "uk": "Орендодавець: ім'я та адреса",  "pl": "Wynajmujący: imię i adres",  "tr": "Ev sahibi adı ve adresi",     "ar": "اسم المؤجر وعنوانه"},
    "mb_m_anschrift":   {"de": "Mieter: Name und Anschrift",     "en": "Tenant name and address",    "uk": "Орендар: ім'я та адреса",       "pl": "Najemca: imię i adres",      "tr": "Kiracı adı ve adresi",        "ar": "اسم المستأجر وعنوانه"},
    "mb_anschrift":     {"de": "Anschrift der Wohnung",          "en": "Property address",           "uk": "Адреса квартири",               "pl": "Adres nieruchomości",        "tr": "Mülk adresi",                 "ar": "عنوان العقار"},
    "mb_mietbeginn":    {"de": "Mietbeginn",                     "en": "Rental start date",          "uk": "Дата початку оренди",           "pl": "Data rozpoczęcia najmu",     "tr": "Kira başlangıç tarihi",       "ar": "تاريخ بدء الإيجار"},
    # Beschäftigungserklärung direct keys
    "be_firma":         {"de": "Firma / Arbeitgeber",            "en": "Company / Employer",         "uk": "Компанія / Роботодавець",       "pl": "Firma / Pracodawca",         "tr": "Firma / İşveren",             "ar": "الشركة / صاحب العمل"},
}
# fmt: on


def get_label(field_key: str, lang: str = "de") -> str:
    """Return localized label for a field key. Falls back to title-cased key."""
    lang_norm = (lang or "de").strip().lower()
    if lang_norm == "ua":
        lang_norm = "uk"
    labels = _FIELD_LABELS.get(field_key)
    if not labels:
        return field_key.replace("_", " ").title()
    return (
        labels.get(lang_norm) or labels.get("de") or field_key.replace("_", " ").title()
    )


# ── Required fields per doc_type ──────────────────────────────────────────────
_REQUIRED_FIELDS: Dict[str, List[str]] = {
    "anmeldung": [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "house_number",
        "plz",
        "city",
        "move_in_date",
    ],
    # Person 1 is always required; persons 2-5 are validated dynamically
    # in validate_user_data() based on people_count.
    "ummeldung": [
        "last_name",
        "first_name",
        "birth_date",
        "street",
        "house_number",
        "plz",
        "city",
        "move_in_date",
        "birth_place",
        "gender",
        "previous_ort",
    ],
    "abmeldung": [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "house_number",
        "plz",
        "city",
        "move_out_date",
    ],
    "wohnungsgeberbestaetigung": [
        "first_name",
        "last_name",
        "street",
        "house_number",
        "plz",
        "city",
        "landlord_name",
    ],
    "kindergeld": [
        "first_name",
        "last_name",
        "birth_date",
        "birth_place",
        "street",
        "house_number",
        "postal_code",
        "city",
        "child_last_name",
        "child_first_name",
        "child_birth_date",
        "iban",
    ],
    "kindergeld_anlage": ["child_name", "child_birth_date"],
    "wohngeld": [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "house_number",
        "postal_code",
        "city",
        "living_space_sqm",
        "monthly_rent",
        # household_members is validated conditionally in validate_user_data()
        # based on has_household_members — do not add it here.
        "monthly_income",
        "signature_date",
    ],
    "buergergeld": [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "postal_code",
        "city",
        "household_members",
        "monthly_rent",
        "iban",
        "signature_date",
    ],
    "jobcenter": [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "house_number",
        "plz",
        "city",
    ],
    "verpflichtungserklaerung": [
        "first_name",
        "last_name",
        "street",
        "house_number",
        "plz",
        "city",
    ],
    # be_firma is the direct form/mapping key; employer_name alias does NOT cover be_firma
    "beschaeftigungserklaerung": ["first_name", "last_name", "be_firma"],
    # Mietbescheinigung uses composite textarea keys (mb_*) — validated directly
    "mietbescheinigung": ["mb_vm_anschrift", "mb_m_anschrift", "mb_anschrift", "mb_mietbeginn"],
    "bafoeg": [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "house_number",
        "plz",
        "city",
        "iban",
    ],
    "kinderzuschlag": [
        "first_name",
        "last_name",
        "birth_date",
        "gender",
        "nationality",
        "phone",
        "familienstand",
        "street",
        "house_number",
        "postal_code",
        "city",
        "iban",
        "child1_last_name",
        "child1_first_name",
        "child1_birth_date",
    ],
    "schulbescheinigung": ["child_name", "child_birth_date"],
    "unterhaltsvorschuss": [
        "first_name",
        "last_name",
        "child_name",
        "child_birth_date",
    ],
    "wbs": [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "house_number",
        "plz",
        "city",
        "income",
    ],
    "elterngeld": ["first_name", "last_name", "birth_date", "iban"],
    "aufenthaltserlaubnis_antrag": [
        "first_name",
        "last_name",
        "birth_date",
        "nationality",
        "street",
        "house_number",
        "plz",
        "city",
    ],
    # signature_date is NOT in the aufenthaltstitel AcroForm mapping (XFA PDF — signed by hand)
    "aufenthaltstitel": [
        "first_name",
        "last_name",
        "birth_date",
        "birth_place",
        "nationality",
        "postal_code",
        "city",
        "street",
        "house_number",
        "dokumentenart",
        "seriennummer",
        "ausstellungsbehoerde",
        "ausstellungsdatum",
        "gueltig_bis",
        "residence_purpose",
    ],
    "verlaengerung_aufenthaltstitel": [
        "first_name",
        "last_name",
        "birth_date",
        "birth_place",
        "nationality",
        "postal_code",
        "city",
        "street",
        "house_number",
        "dokumentenart",
        "seriennummer",
        "ausstellungsbehoerde",
        "ausstellungsdatum",
        "gueltig_bis",
        "residence_purpose",
    ],
    "niederlassungserlaubnis": ["first_name", "last_name", "birth_date", "nationality"],
    "ebk": ["first_name", "last_name", "employer_name"],
}

# Non-blocking warnings (recommended but not required)
_WARNING_FIELDS: Dict[str, List[str]] = {
    "anmeldung": ["phone", "nationality"],
    "kindergeld": ["tax_id"],
    "buergergeld": ["phone", "tax_id"],
    "bafoeg": ["tax_id"],
    "elterngeld": ["tax_id"],
    "wbs": ["phone"],
}

# Alternative key names accepted for each logical field
_FIELD_ALIASES: Dict[str, List[str]] = {
    "first_name": ["first_name", "vorname", "firstname"],
    "last_name": ["last_name", "nachname", "lastname", "surname"],
    "birth_date": ["birth_date", "date_of_birth", "birthdate", "geburtsdatum", "dob"],
    "street": ["street", "strasse", "street_name", "strassenname"],
    "house_number": ["house_number", "housenumber", "hausnummer", "house_no"],
    "plz": ["plz", "postal_code", "postleitzahl", "zip"],
    "city": ["city", "ort", "stadt"],
    "nationality": [
        "nationality",
        "staatsangehoerigkeit",
        "citizenship",
        "staatsbuergerschaft",
    ],
    "move_in_date": ["move_in_date", "einzugsdatum", "zuzugsdatum", "moveindate"],
    "landlord_name": [
        "landlord_name",
        "wohnungsgeber_name",
        "vermieter_name",
        "landlord",
    ],
    "iban": ["iban"],
    "tax_id": ["tax_id", "steuer_id", "steuernummer", "tax_number"],
    "employer_name": ["employer_name", "arbeitgeber_name", "company_name", "firma"],
    "income": ["income", "einkommen", "monatliches_einkommen", "monthly_income"],
    "child_name": [
        "child_name",
        "child_first_name",
        "child_last_name",
        "kind_name",
        "kind_vorname",
        "kindname",
    ],
    "child_birth_date": [
        "child_birth_date",
        "child_birthdate",
        "kind_geburtsdatum",
        "child_dob",
    ],
    "new_street": ["new_street", "neue_strasse", "street_new"],
    "new_house_number": ["new_house_number", "neue_hausnummer", "house_number_new"],
    "new_plz": ["new_plz", "neue_plz", "plz_new"],
    "new_city": ["new_city", "neue_stadt", "ort_new"],
    "phone": ["phone", "phone_number", "telefon", "telephone", "mobil"],
    "email": ["email", "e_mail", "mail"],
    "passport_number": ["passport_number", "ausweisnummer", "pass_nummer"],
    "family_status": ["family_status", "familienstand", "marital_status"],
    "familienstand": ["familienstand", "family_status", "marital_status"],
    "postal_code": ["postal_code", "plz", "zip", "postleitzahl"],
    "gender": ["gender", "geschlecht"],
    "child1_last_name": ["child1_last_name", "child_last_name"],
    "child1_first_name": ["child1_first_name", "child_first_name"],
    "child1_birth_date": ["child1_birth_date", "child_birth_date"],
}

_EMPTY_VALUES = frozenset({"", "null", "none", "keine", "-", "n/a"})

# ── Format validators ─────────────────────────────────────────────────────────

_PLZ_RE = re.compile(r"^\d{5}$")

# IBAN: 2 letters + 2 digits + up to 30 alphanumeric (no spaces required here,
# normalize.py already strips spaces and uppercases before we get here).
_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$")

# DE IBAN specifically: DE + 2 check digits + 18 digits
_DE_IBAN_RE = re.compile(r"^DE\d{20}$")

_FORMAT_ERRORS: Dict[str, Dict[str, str]] = {
    "plz_invalid": {
        "de": "PLZ muss genau 5 Ziffern haben (z.B. 10115)",
        "en": "Postal code must be exactly 5 digits (e.g. 10115)",
        "uk": "Поштовий індекс має містити рівно 5 цифр (наприклад 10115)",
        "pl": "Kod pocztowy musi składać się dokładnie z 5 cyfr (np. 10115)",
        "tr": "Posta kodu tam 5 rakamdan oluşmalıdır (ör. 10115)",
        "ar": "يجب أن يتكون الرمز البريدي من 5 أرقام بالضبط (مثل 10115)",
    },
    "iban_invalid": {
        "de": "IBAN hat ein ungültiges Format (erwartet: DE + 20 Ziffern oder gültige EU-IBAN)",
        "en": "IBAN format is invalid (expected: DE + 20 digits or valid EU IBAN)",
        "uk": "Невірний формат IBAN (очікується: DE + 20 цифр або коректний EU IBAN)",
        "pl": "Nieprawidłowy format IBAN (oczekiwany: DE + 20 cyfr lub prawidłowy IBAN UE)",
        "tr": "IBAN formatı geçersiz (beklenen: DE + 20 hane veya geçerli AB IBAN)",
        "ar": "تنسيق IBAN غير صالح (المتوقع: DE + 20 رقمًا أو IBAN أوروبي صالح)",
    },
    "iban_checksum_invalid": {
        "de": "IBAN Prüfsumme ungültig. Bitte prüfen Sie die Kontonummer.",
        "en": "Invalid IBAN checksum. Please double-check the account number.",
        "uk": "Невірна контрольна сума IBAN. Будь ласка, перевірте номер рахунку.",
        "pl": "Nieprawidłowa suma kontrolna IBAN. Sprawdź numer konta.",
        "tr": "IBAN kontrol toplamı geçersiz. Lütfen hesap numarasını kontrol edin.",
        "ar": "رقم التحقق من IBAN غير صالح. يرجى التحقق من رقم الحساب.",
    },
    "date_invalid": {
        "de": "Ungültiges Datum. Erwartet: TT.MM.JJJJ (z.B. 15.03.1990)",
        "en": "Invalid date. Expected format: DD.MM.YYYY (e.g. 15.03.1990)",
        "uk": "Невірна дата. Очікуваний формат: ДД.ММ.РРРР (наприклад 15.03.1990)",
        "pl": "Nieprawidłowa data. Oczekiwany format: DD.MM.RRRR (np. 15.03.1990)",
        "tr": "Geçersiz tarih. Beklenen format: GG.AA.YYYY (ör. 15.03.1990)",
        "ar": "تاريخ غير صالح. الصيغة المتوقعة: يوم.شهر.سنة (مثل 15.03.1990)",
    },
    "date_future": {
        "de": "Datum darf nicht in der Zukunft liegen.",
        "en": "Date must not be in the future.",
        "uk": "Дата не може бути в майбутньому.",
        "pl": "Data nie może być w przyszłości.",
        "tr": "Tarih gelecekte olamaz.",
        "ar": "لا يمكن أن يكون التاريخ في المستقبل.",
    },
    "date_too_old": {
        "de": "Datum vor 1900 ist ungültig.",
        "en": "Date before 1900 is not valid.",
        "uk": "Дата до 1900 року недійсна.",
        "pl": "Data przed 1900 rokiem jest nieprawidłowa.",
        "tr": "1900 öncesi tarih geçerli değil.",
        "ar": "التاريخ قبل عام 1900 غير صالح.",
    },
}

# ── IBAN MOD-97 checksum ───────────────────────────────────────────────────────


def _validate_iban_checksum(iban: str) -> bool:
    """
    Validate IBAN via ISO 7064 MOD-97-10 algorithm.

    Steps:
      1. Remove spaces, uppercase.
      2. Move first 4 chars to the end.
      3. Replace each letter with its numeric value (A=10 … Z=35).
      4. Compute int(numeric_string) % 97; valid if result == 1.
    """
    iban_clean = iban.upper().replace(" ", "").replace("-", "")
    if len(iban_clean) < 5:
        return False
    rearranged = iban_clean[4:] + iban_clean[:4]
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        elif ch.isalpha():
            numeric += str(ord(ch) - ord("A") + 10)
        else:
            return False
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


# ── Date semantic validation ──────────────────────────────────────────────────

_DATE_FMT = "%d.%m.%Y"
_TODAY = None  # resolved lazily so tests can freeze time


def _today() -> date:
    return date.today()


def _parse_date(value: str) -> datetime | None:
    """Try to parse DD.MM.YYYY; return datetime or None."""
    try:
        return datetime.strptime(value.strip(), _DATE_FMT)
    except (ValueError, AttributeError):
        return None


def _validate_date_semantics(
    field_key: str,
    value: str,
    all_data: Dict[str, Any],
    lang_norm: str,
) -> List[Dict[str, str]]:
    """
    Semantic checks on a single date field after format normalization.

    Returns list of {key, label, message} — errors are critical (go into missing),
    warnings are soft (go into warnings at call site).

    Rules per field:
      birth_date        — must parse, not future, not before 1900
      child_birth_date  — must parse, not future; warning if > 25 years old
      move_in_date      — warning only if > 6 months in the past
    """
    issues: List[Dict[str, str]] = []

    dt = _parse_date(value)
    if dt is None:
        issues.append(
            {
                "key": field_key,
                "label": get_label(field_key, lang_norm),
                "message": _FORMAT_ERRORS["date_invalid"].get(
                    lang_norm, _FORMAT_ERRORS["date_invalid"]["en"]
                ),
                "_severity": "error",
            }
        )
        return issues

    today = _today()
    d = dt.date()

    if field_key == "birth_date":
        if d > today:
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _FORMAT_ERRORS["date_future"].get(
                        lang_norm, _FORMAT_ERRORS["date_future"]["en"]
                    ),
                    "_severity": "error",
                }
            )
        elif d.year < 1900:
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _FORMAT_ERRORS["date_too_old"].get(
                        lang_norm, _FORMAT_ERRORS["date_too_old"]["en"]
                    ),
                    "_severity": "error",
                }
            )

    elif field_key in ("child_birth_date", "child1_birth_date"):
        if d > today:
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _FORMAT_ERRORS["date_future"].get(
                        lang_norm, _FORMAT_ERRORS["date_future"]["en"]
                    ),
                    "_severity": "error",
                }
            )
        elif (today - d).days > 25 * 365:
            _WARN_OLD_CHILD = {
                "de": "Geburtsdatum des Kindes ist über 25 Jahre alt — bitte prüfen.",
                "en": "Child's birth date is over 25 years ago — please verify.",
                "uk": "Дата народження дитини понад 25 років тому — перевірте.",
                "pl": "Data urodzenia dziecka jest sprzed ponad 25 lat — sprawdź.",
                "tr": "Çocuğun doğum tarihi 25 yıldan fazla önce — lütfen kontrol edin.",
                "ar": "تاريخ ميلاد الطفل أكثر من 25 عامًا مضت — يرجى التحقق.",
            }
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _WARN_OLD_CHILD.get(lang_norm, _WARN_OLD_CHILD["en"]),
                    "_severity": "warning",
                }
            )

    elif field_key == "partner_birth_date":
        if d > today:
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _FORMAT_ERRORS["date_future"].get(
                        lang_norm, _FORMAT_ERRORS["date_future"]["en"]
                    ),
                    "_severity": "error",
                }
            )
        elif d.year < 1900:
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _FORMAT_ERRORS["date_too_old"].get(
                        lang_norm, _FORMAT_ERRORS["date_too_old"]["en"]
                    ),
                    "_severity": "error",
                }
            )

    elif field_key == "move_in_date":
        days_ago = (today - d).days
        # BMG §17: registration must be completed within 14 days of moving in
        if 0 < days_ago > 14:
            _WARN_DEADLINE = {
                "de": "Anmeldung sollte innerhalb von 14 Tagen nach dem Einzug erfolgen (§17 BMG).",
                "en": "Registration should be completed within 14 days of moving in (§17 BMG).",
                "uk": "Реєстрація має бути здійснена протягом 14 днів після переїзду (§17 BMG).",
                "pl": "Meldunek powinien być dokonany w ciągu 14 dni od daty przeprowadzki (§17 BMG).",
                "tr": "Taşınmadan sonra 14 gün içinde kayıt yaptırılmalıdır (§17 BMG).",
                "ar": "يجب إتمام التسجيل في غضون 14 يومًا من الانتقال (§17 BMG).",
            }
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _WARN_DEADLINE.get(lang_norm, _WARN_DEADLINE["en"]),
                    "_severity": "warning",
                }
            )
        if days_ago > 180:
            _WARN_OLD_MOVE = {
                "de": "Einzugsdatum liegt über 6 Monate zurück — bitte prüfen.",
                "en": "Move-in date is more than 6 months ago — please verify.",
                "uk": "Дата переїзду більше 6 місяців тому — перевірте.",
                "pl": "Data przeprowadzki jest sprzed ponad 6 miesięcy — sprawdź.",
                "tr": "Taşınma tarihi 6 aydan fazla önce — lütfen kontrol edin.",
                "ar": "تاريخ الانتقال أكثر من 6 أشهر مضت — يرجى التحقق.",
            }
            issues.append(
                {
                    "key": field_key,
                    "label": get_label(field_key, lang_norm),
                    "message": _WARN_OLD_MOVE.get(lang_norm, _WARN_OLD_MOVE["en"]),
                    "_severity": "warning",
                }
            )

    return issues


def _get_field_value(user_data: Dict[str, Any], field_key: str) -> str:
    """Return the first non-empty value for field_key (checking aliases), normalized."""
    for k in _FIELD_ALIASES.get(field_key, [field_key]):
        v = user_data.get(k)
        if v is not None:
            s = str(v).strip()
            if s.lower() not in _EMPTY_VALUES:
                return s
    return ""


def _validate_formats(
    user_data: Dict[str, Any],
    lang_norm: str,
) -> List[Dict[str, str]]:
    """
    Run format checks on PLZ and IBAN values present in user_data.
    Returns list of {key, label, message} for each format error (treated as critical).
    Includes IBAN MOD-97 checksum validation after regex check.
    """
    errors: List[Dict[str, str]] = []

    for plz_key in ("plz", "new_plz"):
        val = _get_field_value(user_data, plz_key)
        if val and not _PLZ_RE.match(val.replace(" ", "")):
            errors.append(
                {
                    "key": plz_key,
                    "label": get_label(plz_key, lang_norm),
                    "message": _FORMAT_ERRORS["plz_invalid"].get(
                        lang_norm, _FORMAT_ERRORS["plz_invalid"]["en"]
                    ),
                }
            )

    iban_val = _get_field_value(user_data, "iban")
    if iban_val:
        iban_clean = iban_val.upper().replace(" ", "")
        if not _IBAN_RE.match(iban_clean):
            errors.append(
                {
                    "key": "iban",
                    "label": get_label("iban", lang_norm),
                    "message": _FORMAT_ERRORS["iban_invalid"].get(
                        lang_norm, _FORMAT_ERRORS["iban_invalid"]["en"]
                    ),
                }
            )
        elif not _validate_iban_checksum(iban_clean):
            logger.debug(
                "validate: IBAN checksum failed for value starting %s", iban_clean[:6]
            )
            errors.append(
                {
                    "key": "iban",
                    "label": get_label("iban", lang_norm),
                    "message": _FORMAT_ERRORS["iban_checksum_invalid"].get(
                        lang_norm, _FORMAT_ERRORS["iban_checksum_invalid"]["en"]
                    ),
                }
            )

    return errors


def _has_value(user_data: Dict[str, Any], field_key: str) -> bool:
    """Return True if any alias for field_key has a non-empty value."""
    for k in _FIELD_ALIASES.get(field_key, [field_key]):
        v = user_data.get(k)
        if v is not None and str(v).strip().lower() not in _EMPTY_VALUES:
            return True
    return False


# ── Public API ─────────────────────────────────────────────────────────────────


def validate_user_data(
    doc_type: str,
    user_data: Dict[str, Any],
    lang: str = "de",
) -> Tuple[bool, List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Validate user_data against doc_type's required-field list.

    Returns:
        ok       — True when no required fields are missing
        missing  — list of {key, label, message} for each missing required field
        warnings — list of {key, label, message} for each missing recommended field
    """
    lang_norm = (lang or "de").strip().lower()
    if lang_norm == "ua":
        lang_norm = "uk"

    _MSG = {
        "de": "Pflichtfeld fehlt",
        "en": "Required field missing",
        "uk": "Обов'язкове поле відсутнє",
        "pl": "Brak wymaganego pola",
        "tr": "Zorunlu alan eksik",
        "ar": "الحقل الإلزامي مفقود",
    }
    _WARN_MSG = {
        "de": "Empfohlen, aber kein Pflichtfeld",
        "en": "Recommended but not required",
        "uk": "Рекомендовано, але не обов'язково",
        "pl": "Zalecane, ale niewymagane",
        "tr": "Önerilen ama zorunlu değil",
        "ar": "مستحسن لكن غير مطلوب",
    }

    key = (doc_type or "").strip().lower()
    missing: List[Dict[str, str]] = []
    for fk in _REQUIRED_FIELDS.get(key, []):
        if not _has_value(user_data, fk):
            missing.append(
                {
                    "key": fk,
                    "label": get_label(fk, lang_norm),
                    "message": _MSG.get(lang_norm, _MSG["en"]),
                }
            )

    # ── Ummeldung: validate additional persons (2-5) when people_count > 1 ──
    if key == "ummeldung":
        try:
            count = int(str(user_data.get("people_count", "1")).strip())
        except (ValueError, TypeError):
            count = 1
        _PERSON_REQ = ["last_name", "first_name", "birth_date"]
        _PERSON_LABELS = {
            "last_name": {"de": "Familienname", "en": "Last name", "uk": "Прізвище"},
            "first_name": {"de": "Vornamen", "en": "First name", "uk": "Ім'я"},
            "birth_date": {
                "de": "Geburtsdatum",
                "en": "Date of birth",
                "uk": "Дата народження",
            },
        }
        for p in range(2, min(count + 1, 6)):
            prefix = f"person{p}_"
            for fk in _PERSON_REQ:
                full_key = prefix + fk
                if not _has_value(user_data, full_key):
                    lbl = _PERSON_LABELS.get(fk, {}).get(lang_norm, fk)
                    missing.append(
                        {
                            "key": full_key,
                            "label": f"Person {p}: {lbl}",
                            "message": _MSG.get(lang_norm, _MSG["en"]),
                        }
                    )

    # ── Anmeldung: validate spouse (Person 2) when spouse_registers == "Ja" ──
    if key == "anmeldung":
        _spouse = str(user_data.get("spouse_registers", "")).strip()
        if _spouse == "Ja":
            _SPOUSE_REQ = {
                "person2_last_name": {
                    "de": "Person 2 muss einen Familiennamen haben (Bürgeramt-Pflicht).",
                    "en": "Person 2 must have a last name (required by Bürgeramt).",
                    "uk": "Особа 2 повинна мати прізвище (вимога Bürgeramt).",
                    "pl": "Osoba 2 musi mieć nazwisko (wymóg Bürgeramt).",
                    "tr": "Kişi 2'nin soyadı olmalıdır (Bürgeramt zorunluluğu).",
                    "ar": "يجب أن يكون للشخص 2 اسم عائلة (شرط Bürgeramt).",
                },
                "person2_first_name": {
                    "de": "Person 2 muss einen Vornamen haben (Bürgeramt-Pflicht).",
                    "en": "Person 2 must have a first name (required by Bürgeramt).",
                    "uk": "Особа 2 повинна мати ім'я (вимога Bürgeramt).",
                    "pl": "Osoba 2 musi mieć imię (wymóg Bürgeramt).",
                    "tr": "Kişi 2'nin adı olmalıdır (Bürgeramt zorunluluğu).",
                    "ar": "يجب أن يكون للشخص 2 اسم أول (شرط Bürgeramt).",
                },
                "person2_birth_date": {
                    "de": "Person 2: Geburtsdatum ist für das Anmeldungsformular erforderlich.",
                    "en": "Person 2: Date of birth is required for the registration form.",
                    "uk": "Особа 2: Дата народження обов'язкова для форми реєстрації.",
                    "pl": "Osoba 2: Data urodzenia jest wymagana w formularzu rejestracyjnym.",
                    "tr": "Kişi 2: Doğum tarihi kayıt formu için zorunludur.",
                    "ar": "الشخص 2: تاريخ الميلاد مطلوب لنموذج التسجيل.",
                },
            }
            for _sk, _msgs in _SPOUSE_REQ.items():
                if not _has_value(user_data, _sk):
                    missing.append(
                        {
                            "key": _sk,
                            "label": get_label(_sk, lang_norm),
                            "message": _msgs.get(lang_norm, _msgs["en"]),
                        }
                    )

    # ── Wohngeld: conditional household_members validation ───────────────────
    # household_members is only required when the user declared they have
    # additional household members (has_household_members == "ja").
    # An empty list means the user lives alone — that is valid.
    if key == "wohngeld":
        _hm_flag = str(user_data.get("has_household_members", "")).strip().lower()
        if _hm_flag in ("ja", "yes", "true", "1"):
            _hm_val = user_data.get("household_members")
            _hm_empty = (
                _hm_val is None
                or (isinstance(_hm_val, list) and len(_hm_val) == 0)
                or (isinstance(_hm_val, str) and _hm_val.strip().lower() in (_EMPTY_VALUES | {"[]"}))
            )
            if _hm_empty:
                _WG_HM_MSG: Dict[str, str] = {
                    "de": "Haushaltsmitglieder fehlen (Sie haben 'Ja' für weitere Mitglieder angegeben).",
                    "en": "Household member details are missing (you indicated additional members).",
                    "uk": "Відсутні дані про членів домогосподарства (Ви вказали 'Так').",
                    "pl": "Brak danych członków gospodarstwa (zaznaczono 'Tak' dla dodatkowych osób).",
                    "tr": "Hane üyesi bilgileri eksik (ek üye olduğunu belirttiniz).",
                    "ar": "بيانات أفراد الأسرة مفقودة (أشرت إلى وجود أفراد إضافيين).",
                }
                missing.append({
                    "key": "household_members",
                    "label": get_label("household_members", lang_norm),
                    "message": _WG_HM_MSG.get(lang_norm, _WG_HM_MSG["en"]),
                })

    # ── Kinderzuschlag: confirmations must be "ja"; partner when married / LP ───
    if key == "kinderzuschlag":
        for _ck in ("kiz_confirm_truth", "kiz_ack_processing"):
            _cv = str(user_data.get(_ck, "")).strip().lower()
            if _cv != "ja":
                missing.append(
                    {
                        "key": _ck,
                        "label": get_label(_ck, lang_norm),
                        "message": _MSG.get(lang_norm, _MSG["en"]),
                    }
                )
        _kfs = str(user_data.get("familienstand", "")).strip().lower()
        if _kfs in ("verheiratet", "eingetragene lebenspartnerschaft"):
            for _pk in (
                "partner_last_name",
                "partner_first_name",
                "partner_birth_date",
                "partner_nationality",
            ):
                if not _has_value(user_data, _pk):
                    missing.append(
                        {
                            "key": _pk,
                            "label": get_label(_pk, lang_norm),
                            "message": _MSG.get(lang_norm, _MSG["en"]),
                        }
                    )

    # Format validation: PLZ (5 digits) and IBAN with MOD-97 checksum
    format_errors = _validate_formats(user_data, lang_norm)
    missing.extend(format_errors)

    # Semantic date validation for known date fields present in user_data
    _DATE_FIELDS_TO_CHECK = (
        "birth_date",
        "child_birth_date",
        "child1_birth_date",
        "partner_birth_date",
        "move_in_date",
    )
    for date_fk in _DATE_FIELDS_TO_CHECK:
        date_val = _get_field_value(user_data, date_fk)
        if not date_val:
            continue
        date_issues = _validate_date_semantics(date_fk, date_val, user_data, lang_norm)
        for issue in date_issues:
            severity = issue.pop("_severity", "error")
            if severity == "error":
                missing.append(issue)
            # warnings from date semantics are collected below

    warnings: List[Dict[str, str]] = []
    for fk in _WARNING_FIELDS.get(key, []):
        if not _has_value(user_data, fk):
            warnings.append(
                {
                    "key": fk,
                    "label": get_label(fk, lang_norm),
                    "message": _WARN_MSG.get(lang_norm, _WARN_MSG["en"]),
                }
            )

    # Soft date warnings (move_in_date > 6 months, child > 25 years)
    for date_fk in _DATE_FIELDS_TO_CHECK:
        date_val = _get_field_value(user_data, date_fk)
        if not date_val:
            continue
        date_issues = _validate_date_semantics(date_fk, date_val, user_data, lang_norm)
        for issue in date_issues:
            severity = issue.pop("_severity", "error")
            if severity == "warning":
                warnings.append(issue)

    # ── Buergergeld: document-specific rejection-risk warnings ────────────────
    # These warn about real Jobcenter rejection reasons that are not covered by
    # the generic missing-field check above.  All are non-blocking (warnings only).
    if key == "buergergeld":
        _bg_risk = _get_buergergeld_risk_warnings(user_data, lang_norm)
        warnings.extend(_bg_risk)
        if _bg_risk:
            logger.info(
                "RISK_WARNINGS_ADDED: doc_type=buergergeld warnings=%s",
                [w["key"] for w in _bg_risk],
            )

    # ── Kindergeld: soft format check for Steuer-ID fields ───────────────────
    # Non-blocking: warn if a Steuer-ID value is present but is not 11 digits.
    if key == "kindergeld":
        _steuer_warn_msg: Dict[str, str] = {
            "de": "Steuer-ID muss genau 11 Ziffern enthalten",
            "en": "Tax ID must be exactly 11 digits",
            "uk": "Steuer-ID має містити рівно 11 цифр",
            "pl": "Steuer-ID musi zawierać dokładnie 11 cyfr",
            "tr": "Steuer-ID tam 11 rakamdan oluşmalıdır",
            "ar": "يجب أن يحتوي Steuer-ID على 11 رقماً بالضبط",
        }
        for _sid_key in ("tax_id", "steuer_id_applicant", "steuer_id_child"):
            _sid_val = (user_data.get(_sid_key) or "").replace(" ", "")
            if _sid_val and (not _sid_val.isdigit() or len(_sid_val) != 11):
                warnings.append(
                    {
                        "key": _sid_key,
                        "label": get_label(_sid_key, lang_norm),
                        "message": _steuer_warn_msg.get(
                            lang_norm, _steuer_warn_msg["en"]
                        ),
                    }
                )

    return len(missing) == 0, missing, warnings


def _get_buergergeld_risk_warnings(
    data: Dict[str, Any],
    lang: str = "de",
) -> List[Dict[str, str]]:
    """
    Return a list of non-blocking {key, label, message} dicts for Jobcenter-specific
    rejection risks in a Bürgergeld application.

    Does NOT duplicate checks already enforced as blocking errors:
    - IBAN format / checksum  → already a blocking error via _validate_formats()
    - PLZ 5-digit format      → already a blocking error via _validate_formats()
    """
    _MSGS: Dict[str, Dict[str, str]] = {
        "partner_missing": {
            "de": "⚠️ Verheiratet / Lebenspartnerschaft: Angaben zum Partner fehlen — Jobcenter kann Antrag ablehnen.",
            "en": "⚠️ Married / civil partnership: partner details are missing — Jobcenter may reject the application.",
            "uk": "⚠️ Одружений / партнерство: дані партнера відсутні — Jobcenter може відхилити заяву.",
            "pl": "⚠️ Żonaty/zamężna: brakuje danych partnera — Jobcenter może odrzucić wniosek.",
            "tr": "⚠️ Evli / birliktelik: partner bilgileri eksik — Jobcenter başvuruyu reddedebilir.",
            "ar": "⚠️ متزوج / شراكة: بيانات الشريك مفقودة — قد يرفض Jobcenter الطلب.",
        },
        "signature_date_missing": {
            "de": "⚠️ Unterschriftsdatum fehlt — nicht unterschriebene Anträge werden automatisch abgelehnt.",
            "en": "⚠️ Signature date is missing — unsigned applications are automatically rejected.",
            "uk": "⚠️ Дата підпису відсутня — непідписані заяви автоматично відхиляються.",
            "pl": "⚠️ Brak daty podpisu — niepodpisane wnioski są automatycznie odrzucane.",
            "tr": "⚠️ İmza tarihi eksik — imzasız başvurular otomatik olarak reddedilir.",
            "ar": "⚠️ تاريخ التوقيع مفقود — الطلبات غير الموقعة تُرفض تلقائيًا.",
        },
        "iban_non_german": {
            "de": "⚠️ Nicht-deutsche IBAN: Jobcenter überweist Leistungen bevorzugt auf deutsche Konten (DE...).",
            "en": "⚠️ Non-German IBAN: Jobcenter strongly prefers German bank accounts (DE...) for benefit payments.",
            "uk": "⚠️ Не-німецький IBAN: Jobcenter надає перевагу німецьким рахункам (DE...) для виплат.",
            "pl": "⚠️ Nie-niemiecki IBAN: Jobcenter preferuje niemieckie rachunki bankowe (DE...) do wypłat.",
            "tr": "⚠️ Alman olmayan IBAN: Jobcenter, ödemeler için Alman banka hesabını (DE...) tercih eder.",
            "ar": "⚠️ IBAN غير ألماني: يفضل Jobcenter الحسابات الألمانية (DE...) لصرف الإعانات.",
        },
    }

    result: List[Dict[str, str]] = []

    # 1. Married/civil-partnership but no partner household data
    _fs = (data.get("family_status") or data.get("familienstand") or "").strip().lower()
    _is_married = _fs in (
        "verheiratet",
        "married",
        "eingetragene lebenspartnerschaft",
        "одружений",
        "заміжня",
        "одружений/заміжня",
    )
    if _is_married:
        # Consider partner data present if household_members > 1 or any partner key is filled
        _hm = str(data.get("household_members") or "1").strip()
        _has_partner_data = (
            _has_value(data, "partner_name")
            or _has_value(data, "household_type")
            or (_hm.isdigit() and int(_hm) > 1)
        )
        if not _has_partner_data:
            result.append(
                {
                    "key": "partner_missing",
                    "label": _MSGS["partner_missing"].get("de", "Partner"),
                    "message": _MSGS["partner_missing"].get(
                        lang, _MSGS["partner_missing"]["en"]
                    ),
                }
            )

    # 2. Signature date missing (required field, but also a rejection reason worth highlighting)
    if not _has_value(data, "signature_date"):
        result.append(
            {
                "key": "signature_date_missing",
                "label": _MSGS["signature_date_missing"].get("de", "Unterschrift"),
                "message": _MSGS["signature_date_missing"].get(
                    lang, _MSGS["signature_date_missing"]["en"]
                ),
            }
        )

    # 3. Non-German IBAN (not a format error — just a practical Jobcenter preference)
    # Only fires when IBAN is present and valid but not a DE IBAN.
    _iban = (data.get("iban") or "").strip().upper()
    if (
        _iban
        and len(_iban) >= 4
        and _DE_IBAN_RE.match(_iban) is None
        and _IBAN_RE.match(_iban)
    ):
        result.append(
            {
                "key": "iban_non_german",
                "label": _MSGS["iban_non_german"].get("de", "IBAN"),
                "message": _MSGS["iban_non_german"].get(
                    lang, _MSGS["iban_non_german"]["en"]
                ),
            }
        )

    return result


def format_validation_error(
    doc_type: str,
    missing: List[Dict[str, str]],
    lang: str = "de",
) -> str:
    """
    Build a human-readable localized error message for missing required fields.
    Suitable for bot reply messages and PDF rejection notices.
    """
    lang_norm = (lang or "de").strip().lower()
    if lang_norm == "ua":
        lang_norm = "uk"

    _INTRO = {
        "de": "❌ Das Dokument kann nicht erstellt werden.\nFolgende Pflichtfelder fehlen:",
        "en": "❌ Cannot generate document.\nThe following required fields are missing:",
        "uk": "❌ Не можна згенерувати документ.\nВідсутні обов'язкові поля:",
        "pl": "❌ Nie można wygenerować dokumentu.\nBrakuje wymaganych pól:",
        "tr": "❌ Belge oluşturulamıyor.\nŞu zorunlu alanlar eksik:",
        "ar": "❌ لا يمكن إنشاء المستند.\nالحقول الإلزامية التالية مفقودة:",
    }
    lines = [_INTRO.get(lang_norm, _INTRO["en"])]
    for item in missing:
        lines.append(f"  • {item['label']}")
    return "\n".join(lines)


# ── Readiness score ───────────────────────────────────────────────────────────


def calculate_readiness_score(
    missing: List[Dict[str, str]],
    warnings: List[Dict[str, str]],
    required_fields: List[str],
    warning_fields: List[str],
) -> int:
    """
    Calculate a 0-100 integer readiness score for a document submission.

    Formula:
        required_completion * 80%
      + warning_completion  * 15%
      + format_integrity    *  5%

    required_completion:
        Fraction of required fields that are present (not in `missing`).
        A fully filled document → 1.0.

    warning_completion:
        Fraction of optional/recommended fields (warning_fields) that are
        present. Only keys that appear in warning_fields are counted.
        If no warning_fields are defined for this doc_type → defaults to 1.0
        so it does not penalise documents that have no optional fields.

    format_integrity:
        1.0 if no format-level errors (PLZ, IBAN) in `missing`; else 0.0.
        Format errors are identified by their key — they are separate from
        missing required fields and from date-semantic warnings.
        This component only fires for genuine format violations.

    Weights: required fields dominate (80%). Optional warnings provide a
    small nudge (15%). Format integrity is a light bonus (5%).

    Returns an integer percentage (0-100).
    """
    # ── Required completion ───────────────────────────────────────────────
    n_required = len(required_fields)
    required_field_set = set(required_fields)
    n_missing_required = len([m for m in missing if m.get("key") in required_field_set])
    required_completion = (
        (n_required - n_missing_required) / n_required if n_required else 1.0
    )

    # ── Warning (optional) field completion ───────────────────────────────
    # Only count keys that are actually in warning_fields; ignore date-semantic
    # warnings that share a key with required fields (e.g. move_in_date).
    warning_field_set = set(warning_fields)
    n_warnings = len(warning_fields)
    if n_warnings:
        n_missing_warnings = len(
            [w for w in warnings if w.get("key") in warning_field_set]
        )
        warning_completion = (n_warnings - n_missing_warnings) / n_warnings
    else:
        warning_completion = 1.0  # no optional fields defined → full score

    # ── Format integrity ──────────────────────────────────────────────────
    # A format error key is one that is NOT in required_fields (PLZ/IBAN
    # format checks generate their own entries with key "plz" or "iban").
    # We check for any missing entry whose key is a format-only key.
    _FORMAT_KEYS = frozenset({"plz", "new_plz", "iban"})
    has_format_error = any(m.get("key") in _FORMAT_KEYS for m in missing)
    format_integrity = 0.0 if has_format_error else 1.0

    score = (
        required_completion * 0.90 + warning_completion * 0.07 + format_integrity * 0.03
    )
    # Cap at 98: a perfect score of 100% would feel unrealistic to users.
    # 98% still signals "everything is great" while staying credible.
    return max(0, min(98, round(score * 100)))


# ── Common rejection reasons ──────────────────────────────────────────────────
# Localized per doc_type. Based on typical Behörde rejection patterns.
# Keys: language codes (de, en, uk, pl, tr, ar).

_REJECTION_REASONS: Dict[str, Dict[str, List[str]]] = {
    "anmeldung": {
        "de": [
            "Name stimmt nicht mit dem Ausweis überein",
            "Einzugsdatum ist falsch oder fehlt",
            "Wohnungsgeberbestätigung fehlt",
            "Adresse ist unvollständig",
            "Anmeldung erfolgte nach 14-Tage-Frist (§17 BMG)",
        ],
        "en": [
            "Name does not match passport or ID",
            "Move-in date is incorrect or missing",
            "Landlord confirmation (Wohnungsgeberbestätigung) missing",
            "Address is incomplete",
            "Registration submitted after the 14-day deadline (§17 BMG)",
        ],
        "uk": [
            "Ім'я не відповідає паспорту",
            "Дата в'їзду вказана неправильно або відсутня",
            "Відсутнє підтвердження орендодавця",
            "Адреса вказана неповністю",
            "Реєстрація подана після 14-денного терміну (§17 BMG)",
        ],
        "pl": [
            "Imię/nazwisko nie zgadza się z dowodem tożsamości",
            "Błędna lub brakująca data przeprowadzki",
            "Brak potwierdzenia wynajmującego",
            "Niekompletny adres",
            "Zgłoszenie po upływie 14-dniowego terminu (§17 BMG)",
        ],
        "tr": [
            "Ad/soyad pasaportla eşleşmiyor",
            "Taşınma tarihi hatalı veya eksik",
            "Ev sahibi onayı eksik",
            "Adres eksik",
            "Kayıt 14 günlük süre dolduktan sonra yapıldı (§17 BMG)",
        ],
        "ar": [
            "الاسم لا يطابق جواز السفر",
            "تاريخ الانتقال غير صحيح أو مفقود",
            "تأكيد المالك مفقود",
            "العنوان غير مكتمل",
            "تم التسجيل بعد انتهاء المهلة القانونية (§17 BMG)",
        ],
    },
    "kindergeld": {
        "de": [
            "Geburtsurkunde des Kindes fehlt",
            "IBAN ist falsch oder gehört nicht zum Antragsteller",
            "Familienstand wurde nicht angegeben",
            "Kind lebt nicht im Haushalt des Antragstellers",
            "Steuernummer fehlt",
        ],
        "en": [
            "Child birth certificate missing",
            "IBAN is incorrect or does not belong to the applicant",
            "Family status not provided",
            "Child does not live in applicant's household",
            "Tax ID (Steuernummer) missing",
        ],
        "uk": [
            "Свідоцтво про народження дитини відсутнє",
            "IBAN неправильний або не належить заявнику",
            "Сімейний стан не вказано",
            "Дитина не проживає в домогосподарстві заявника",
            "Відсутній податковий номер",
        ],
        "pl": [
            "Brak aktu urodzenia dziecka",
            "IBAN jest błędny lub nie należy do wnioskodawcy",
            "Nie podano stanu cywilnego",
            "Dziecko nie mieszka w gospodarstwie domowym wnioskodawcy",
            "Brak numeru podatkowego",
        ],
        "tr": [
            "Çocuğun doğum belgesi eksik",
            "IBAN hatalı veya başvurana ait değil",
            "Medeni durum belirtilmemiş",
            "Çocuk başvuranın hanesinde yaşamıyor",
            "Vergi numarası eksik",
        ],
        "ar": [
            "شهادة ميلاد الطفل مفقودة",
            "رقم IBAN غير صحيح أو لا ينتمي لمقدم الطلب",
            "الحالة الاجتماعية غير محددة",
            "الطفل لا يسكن في منزل مقدم الطلب",
            "الرقم الضريبي مفقود",
        ],
    },
    "buergergeld": {
        "de": [
            "IBAN fehlt oder stimmt nicht",
            "Angaben zu Einkommen oder Vermögen unvollständig",
            "Wohnadresse fehlt oder ist falsch",
            "Geburtsdatum fehlt",
        ],
        "en": [
            "IBAN missing or incorrect",
            "Income or assets information incomplete",
            "Residential address missing or incorrect",
            "Date of birth missing",
        ],
        "uk": [
            "IBAN відсутній або неправильний",
            "Інформація про доходи або майно неповна",
            "Адреса проживання відсутня або неправильна",
            "Дата народження відсутня",
        ],
        "pl": [
            "IBAN brakuje lub jest błędny",
            "Informacje o dochodach lub majątku niekompletne",
            "Brak lub błędny adres zamieszkania",
            "Brak daty urodzenia",
        ],
        "tr": [
            "IBAN eksik veya hatalı",
            "Gelir veya mal varlığı bilgisi eksik",
            "İkamet adresi eksik veya hatalı",
            "Doğum tarihi eksik",
        ],
        "ar": [
            "رقم IBAN مفقود أو غير صحيح",
            "معلومات الدخل أو الأصول غير مكتملة",
            "العنوان السكني مفقود أو غير صحيح",
            "تاريخ الميلاد مفقود",
        ],
    },
    "aufenthaltstitel": {
        "de": [
            "Reisepass oder Ausweisdokument fehlt oder ist abgelaufen",
            "Aufenthaltszweck nicht klar angegeben",
            "Nachweis über Krankenversicherung fehlt",
            "Einkommensnachweis oder Finanzierungsnachweis fehlt",
            "Antrag nicht vollständig ausgefüllt",
        ],
        "en": [
            "Passport or ID document missing or expired",
            "Purpose of residence not clearly stated",
            "Proof of health insurance missing",
            "Proof of income or financial means missing",
            "Application form not fully completed",
        ],
        "uk": [
            "Паспорт або документ, що посвідчує особу, відсутній або прострочений",
            "Мета проживання не вказана чітко",
            "Відсутній доказ медичного страхування",
            "Відсутній доказ доходу або фінансового забезпечення",
            "Заява заповнена не повністю",
        ],
        "pl": [
            "Paszport lub dokument tożsamości brakuje lub jest nieważny",
            "Cel pobytu nie jest jasno określony",
            "Brak dowodu ubezpieczenia zdrowotnego",
            "Brak zaświadczenia o dochodach lub środkach finansowych",
            "Formularz wniosku nie jest w pełni wypełniony",
        ],
        "tr": [
            "Pasaport veya kimlik belgesi eksik veya süresi dolmuş",
            "İkamet amacı açıkça belirtilmemiş",
            "Sağlık sigortası belgesi eksik",
            "Gelir veya mali kaynak belgesi eksik",
            "Başvuru formu tam olarak doldurulmamış",
        ],
        "ar": [
            "جواز السفر أو وثيقة الهوية مفقودة أو منتهية الصلاحية",
            "الغرض من الإقامة غير محدد بوضوح",
            "إثبات التأمين الصحي مفقود",
            "إثبات الدخل أو الوسائل المالية مفقود",
            "نموذج الطلب غير مكتمل",
        ],
    },
    "ummeldung": {
        "de": [
            "Einzugsdatum fehlt oder liegt in der Zukunft",
            "Neue Adresse ist unvollständig",
            "Anmeldung erfolgte nach 14-Tage-Frist (§17 BMG)",
            "Wohnungsgeberbestätigung fehlt",
        ],
        "en": [
            "Move-in date missing or in the future",
            "New address is incomplete",
            "Re-registration submitted after the 14-day deadline (§17 BMG)",
            "Landlord confirmation missing",
        ],
        "uk": [
            "Дата в'їзду відсутня або в майбутньому",
            "Нова адреса вказана неповністю",
            "Перереєстрація подана після 14-денного терміну (§17 BMG)",
            "Відсутнє підтвердження орендодавця",
        ],
        "pl": [
            "Brak daty przeprowadzki lub data w przyszłości",
            "Nowy adres jest niekompletny",
            "Ponowna rejestracja po upływie 14-dniowego terminu (§17 BMG)",
            "Brak potwierdzenia wynajmującego",
        ],
        "tr": [
            "Taşınma tarihi eksik veya gelecekte",
            "Yeni adres eksik",
            "Yeniden kayıt 14 günlük süre dolduktan sonra yapıldı (§17 BMG)",
            "Ev sahibi onayı eksik",
        ],
        "ar": [
            "تاريخ الانتقال مفقود أو في المستقبل",
            "العنوان الجديد غير مكتمل",
            "تم إعادة التسجيل بعد انتهاء المهلة القانونية (§17 BMG)",
            "تأكيد المالك مفقود",
        ],
    },
    "wohngeld": {
        "de": [
            "Einkommensnachweis fehlt",
            "Mietvertrag oder Mietnachweis fehlt",
            "Haushaltsgröße nicht korrekt angegeben",
            "Adresse stimmt nicht mit Mietvertrag überein",
        ],
        "en": [
            "Proof of income missing",
            "Rental agreement or rent receipt missing",
            "Household size not correctly stated",
            "Address does not match rental agreement",
        ],
        "uk": [
            "Відсутній доказ доходу",
            "Договір оренди або квитанція про орендну плату відсутні",
            "Розмір домогосподарства вказано неправильно",
            "Адреса не відповідає договору оренди",
        ],
        "pl": [
            "Brak zaświadczenia o dochodach",
            "Brak umowy najmu lub potwierdzenia czynszu",
            "Nieprawidłowa liczba osób w gospodarstwie",
            "Adres niezgodny z umową najmu",
        ],
        "tr": [
            "Gelir belgesi eksik",
            "Kira sözleşmesi veya makbuzu eksik",
            "Hane büyüklüğü doğru belirtilmemiş",
            "Adres kira sözleşmesiyle eşleşmiyor",
        ],
        "ar": [
            "إثبات الدخل مفقود",
            "عقد الإيجار أو إيصال الإيجار مفقود",
            "حجم الأسرة المعيشية غير محدد بشكل صحيح",
            "العنوان لا يتطابق مع عقد الإيجار",
        ],
    },
}


def get_rejection_reasons(doc_type: str, lang: str = "en") -> List[str]:
    """
    Return the list of common rejection reasons for the given doc_type and language.
    Falls back to English if the language is not available.
    Returns an empty list if no reasons are defined for this doc_type.
    """
    lang_norm = (lang or "en").strip().lower()
    if lang_norm == "ua":
        lang_norm = "uk"
    reasons = _REJECTION_REASONS.get((doc_type or "").strip().lower(), {})
    return reasons.get(lang_norm) or reasons.get("en") or []


# ── FormValidator — thin class wrapper (PHASE 4 refactor) ─────────────────────
# Provides an OO interface over the existing validate_user_data() function.
# Does NOT duplicate any validation logic.

from dataclasses import dataclass, field as _dc_field


@dataclass
class ValidationResult:
    """Structured result returned by FormValidator.validate()."""

    ok: bool
    missing: List[Dict[str, str]] = _dc_field(default_factory=list)
    warnings: List[Dict[str, str]] = _dc_field(default_factory=list)
    error_message: str = ""

    def __bool__(self) -> bool:
        return self.ok


class FormValidator:
    """
    Thin class wrapper around validate_user_data().
    Use this for new code; validate_user_data() is preserved for backward compatibility.

    Usage:
        result = FormValidator.validate("anmeldung", user_data, lang="uk")
        if not result:
            return result.error_message
    """

    @staticmethod
    def validate(
        doc_type: str,
        user_data: Dict[str, Any],
        lang: str = "de",
    ) -> ValidationResult:
        """
        Validate user_data for the given doc_type.
        Returns a ValidationResult with ok, missing, warnings, and error_message.
        """
        ok, missing, warnings = validate_user_data(doc_type, user_data, lang)
        error_msg = ""
        if not ok and missing:
            error_msg = format_validation_error(doc_type, missing, lang)
        return ValidationResult(
            ok=ok, missing=missing, warnings=warnings, error_message=error_msg
        )
