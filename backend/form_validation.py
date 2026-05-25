# -*- coding: utf-8 -*-
"""
backend/form_validation.py — strict, reusable form validation for WebApp and server.

- All validations return (valid, errors, warnings).
- errors = hard block (no submit, no payment, no PDF).
- warnings = soft (show message, allow submit; or block depending on rule).
- Message keys are used for i18n (DE/UA/EN) on client and server.
"""

import re
from datetime import date as date_type
from typing import Dict, Any, List, Tuple, Optional

# -----------------------------------------------------------------------------
# Validation message keys → localized text (DE / UA / EN) for server-side use
# Client (WebApp) has same keys in TRANSLATIONS.err_* / warn_*
# -----------------------------------------------------------------------------
VALIDATION_MESSAGES: Dict[str, Dict[str, str]] = {
    "required": {
        "de": "Dieses Feld ist erforderlich.",
        "uk": "Це поле є обовʼязковим.",
        "en": "This field is required.",
    },
    "plz_format": {
        "de": "Die Postleitzahl muss aus 5 Ziffern bestehen.",
        "uk": "Поштовий індекс має містити 5 цифр.",
        "en": "Postal code must contain 5 digits.",
    },
    "plz_berlin": {
        "de": "Diese Postleitzahl gehört nicht zu Berlin.",
        "uk": "Цей поштовий індекс не відповідає місту Берлін.",
        "en": "This postal code does not belong to Berlin.",
    },
    "document_number": {
        "de": "Die Dokumentnummer hat ein ungültiges Format.",
        "uk": "Номер документа має неправильний формат.",
        "en": "Document number format is invalid.",
    },
    "authority_empty": {
        "de": "Bitte geben Sie die Ausstellungsbehörde an.",
        "uk": "Вкажіть, будь ласка, орган, який видав документ.",
        "en": "Please enter the issuing authority.",
    },
    "authority_suspicious": {
        "de": "Bitte überprüfen Sie den Namen der Behörde. Einige Ämter erheben eigene Bearbeitungsgebühren — das hat nichts mit dem Bot zu tun.",
        "uk": "Переконайтесь, що назва установи правильна. Деякі відомства можуть стягувати власний збір за обробку документів — це не пов'язано з оплатою у боті.",
        "en": "Please make sure the authority name is correct. Some offices may charge their own processing fee — this is unrelated to the bot.",
    },
    "date_logic": {
        "de": "Das Datum ist logisch nicht korrekt.",
        "uk": "Дата введена некоректно.",
        "en": "The date is not logically valid.",
    },
    "value_invalid": {
        "de": "Diese Angabe scheint ungültig zu sein.",
        "uk": "Це значення виглядає некоректним.",
        "en": "This value appears to be invalid.",
    },
    "placeholder_not_allowed": {
        "de": "Bitte tragen Sie einen gültigen Wert ein (kein Platzhalter).",
        "uk": "Введіть дійсне значення (не заповнювач).",
        "en": "Please enter a valid value (no placeholder).",
    },
    "name_letters_only": {
        "de": "Nur Buchstaben (keine Ziffern oder Sonderzeichen).",
        "uk": "Тільки літери (без цифр і спецсимволів).",
        "en": "Letters only (no digits or special characters).",
    },
    "street_no_digits": {
        "de": "Straßenname ohne Ziffern (Hausnummer getrennt eintragen).",
        "uk": "Назва вулиці без цифр (номер будинку окремо).",
        "en": "Street name without digits (enter house number separately).",
    },
    "plz_germany_only": {
        "de": "Nur deutsche Postleitzahlen (5 Ziffern, 01000–99999).",
        "uk": "Тільки німецькі індекси (5 цифр, 01000–99999).",
        "en": "German postal codes only (5 digits, 01000–99999).",
    },
    "plz_city_mismatch": {
        "de": "Die Postleitzahl {plz} gehört nicht zu „{city}.",
        "uk": "Індекс {plz} не відповідає місту „{city}.",
        "en": "Postal code {plz} does not belong to „{city}.",
    },
    "date_future": {
        "de": "Das Datum darf nicht in der Zukunft liegen.",
        "uk": "Дата не може бути в майбутньому.",
        "en": "The date cannot be in the future.",
    },
    "date_format": {
        "de": "Bitte im Format TT.MM.JJJJ eingeben (z. B. 15.03.2024).",
        "uk": "Введіть у форматі ДД.ММ.РРРР (наприклад 15.03.2024).",
        "en": "Please use format DD.MM.YYYY (e.g. 15.03.2024).",
        "pl": "Użyj formatu DD.MM.RRRR (np. 15.03.2024).",
        "tr": "Lütfen GG.AA.YYYY biçimini kullanın (ör. 15.03.2024).",
        "ar": "يرجى استخدام التنسيق DD.MM.YYYY (مثال: 15.03.2024).",
    },
    "marriage_date_required": {
        "de": "Bei Familienstand 'verheiratet' ist Ort/Datum der Eheschliessung erforderlich.",
        "uk": "При сімейному стані 'одружений' необхідно вказати місце та дату шлюбу.",
        "en": "Marital status 'married' requires place and date of marriage.",
        "pl": "Stan cywilny 'zonaty/zamezna' wymaga podania miejsca i daty slubu.",
        "tr": "Medeni durum 'evli' olarak secildiyse evlilik yeri ve tarihi gereklidir.",
        "ar": "الحالة الاجتماعية 'متزوج' تتطلب مكان وتاريخ الزواج.",
    },
    "previous_address_required": {
        "de": "Bitte geben Sie Ihre bisherige Anschrift an.",
        "uk": "Вкажіть вашу попередню адресу.",
        "en": "Please enter your previous address.",
        "pl": "Proszę podać poprzedni adres.",
        "tr": "Lütfen önceki adresinizi girin.",
        "ar": "يرجى إدخال عنوانك السابق.",
    },
    "nebenwohnung_needs_previous": {
        "de": "Bei Nebenwohnung muss eine bisherige Wohnung angegeben werden.",
        "uk": "Для додаткового житла необхідно вказати попередню адресу.",
        "en": "Secondary residence requires a previous address.",
        "pl": "Mieszkanie dodatkowe wymaga podania poprzedniego adresu.",
        "tr": "İkincil konut için önceki adres gereklidir.",
        "ar": "السكن الثانوي يتطلب عنوانًا سابقًا.",
    },
}


def get_validation_message(message_key: str, lang: str, params: Optional[Dict[str, str]] = None) -> str:
    """Return localized validation message. lang: de, uk, en (ua → uk). params for interpolation e.g. {plz}, {city}."""
    lang = (lang or "en").strip().lower()
    if lang == "ua":
        lang = "uk"
    d = VALIDATION_MESSAGES.get(message_key, {})
    msg = d.get(lang) or d.get("en") or d.get("de") or message_key
    if params:
        for k, v in params.items():
            msg = msg.replace("{" + k + "}", str(v))
    return msg


# -----------------------------------------------------------------------------
# Placeholders that must NEVER pass validation (required or optional)
# -----------------------------------------------------------------------------
FORBIDDEN_PLACEHOLDERS: Tuple[str, ...] = (
    "REQUIRED_FROM_USER",
    "OE",
    "Œ",
    "–",
    "nicht erforderlich",
    "nicht zutreffend",
)
# Normalize for comparison (strip, case-insensitive for these)
def _is_forbidden_placeholder(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    su = s.upper()
    for p in FORBIDDEN_PLACEHOLDERS:
        if p.upper() == su or p == s:
            return True
    if s == "–" or s == "—":
        return True
    return False


# German PLZ: 5 digits, range 01000–99999 (Germany only)
def _is_german_plz(plz: Any) -> bool:
    if plz is None:
        return False
    s = re.sub(r"\D", "", str(plz).strip())
    if len(s) != 5:
        return False
    try:
        n = int(s)
        return 1000 <= n <= 99999
    except ValueError:
        return False


# Names: letters only (allow space, hyphen, apostrophe for compound names)
_NAME_RE = re.compile(r"^[A-Za-z\u00C0-\u024F\u1E00-\u1EFF\s\-']+$")
def _valid_name(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    if len(s) < 2:
        return False
    return bool(_NAME_RE.match(s))


# Street: letters, ß, space, hyphen, no digits (house number is separate field)
_STREET_RE = re.compile(r"^[A-Za-z\u00DF\u00C0-\u024F\u1E00-\u1EFF\s\-\.']+$")
def _valid_street(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    if len(s) < 2:
        return False
    if re.search(r"\d", s):
        return False
    return bool(_STREET_RE.match(s))


# City: letters, space, hyphen (min 2 chars); no digits
_CITY_RE = re.compile(r"^[A-Za-z\u00C0-\u024F\u1E00-\u1EFF\s\-']+$")
def _valid_city(value: Any) -> bool:
    if value is None:
        return False
    s = str(value).strip()
    if len(s) < 2:
        return False
    if re.search(r"\d", s):
        return False
    return bool(_CITY_RE.match(s))


# -----------------------------------------------------------------------------
# Berlin postal codes: valid ranges (inclusive). PLZ is 5 digits.
# https://de.wikipedia.org/wiki/Postleitzahl_(Deutschland)#Berlin
# -----------------------------------------------------------------------------
_BERLIN_PLZ_RANGES: List[Tuple[int, int]] = [
    (10115, 10999),
    (12043, 12359),
    (12435, 12689),
    (13051, 13189),
    (13347, 13629),
    (14050, 14199),
]


def is_berlin_plz(plz: Any) -> bool:
    """True if plz is a 5-digit string in a Berlin PLZ range."""
    if plz is None:
        return False
    s = re.sub(r"\D", "", str(plz).strip())
    if len(s) != 5:
        return False
    try:
        n = int(s)
    except ValueError:
        return False
    return any(r[0] <= n <= r[1] for r in _BERLIN_PLZ_RANGES)


def _city_looks_berlin(city: Any) -> bool:
    """True if city value indicates Berlin (case-insensitive, stripped)."""
    if city is None:
        return False
    s = str(city).strip()
    if not s:
        return False
    low = s.lower()
    return low == "berlin" or low.startswith("berlin ") or low.endswith(" berlin")


# -----------------------------------------------------------------------------
# Document number validation by type (Reisepass RP, Personalausweis PA, Kinderreisepass KP)
# RP: alphanumeric 6–9 chars; PA: exactly 9 chars; KP: alphanumeric min 6
# -----------------------------------------------------------------------------
def _validate_document_number(doc_type: str, number: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate serial/document number by document type.
    Returns (is_valid, error_message_key or None).
    """
    if number is None:
        return False, "document_number"
    s = str(number).strip().replace(" ", "").replace("-", "")
    if not s:
        return False, "document_number"

    doc = (doc_type or "").strip().upper()

    if doc == "RP":
        # Reisepass: alphanumeric, 6–9 characters
        if not (6 <= len(s) <= 9 and re.match(r"^[A-Za-z0-9]+$", s)):
            return False, "document_number"
        return True, None

    if doc == "PA":
        # Personalausweis: exactly 9 characters (e.g. L01X00T47)
        if len(s) != 9 or not re.match(r"^[A-Za-z0-9]{9}$", s):
            return False, "document_number"
        return True, None

    if doc == "KP":
        # Kinderreisepass: alphanumeric, min 6 characters
        if len(s) < 6 or not re.match(r"^[A-Za-z0-9]+$", s):
            return False, "document_number"
        return True, None

    # Unknown type: accept non-empty, 5–12 alphanumeric
    if len(s) < 5 or len(s) > 12:
        return False, "document_number"
    if not re.match(r"^[A-Za-z0-9]+$", s):
        return False, "document_number"
    return True, None


def _looks_suspicious_authority(value: Any) -> bool:
    """True if Ausstellungsbehörde looks random/non-institutional (soft warning)."""
    if value is None:
        return False
    s = str(value).strip()
    if len(s) < 4:
        return True
    # Very short or no space and no typical words
    typical = ("standesamt", "amt", "behörde", "ausländer", "einwohner", "melde", "berlin", "stadt")
    low = s.lower()
    if " " not in s and len(s) < 10:
        return True
    if any(t in low for t in typical):
        return False
    # All lowercase single word or no common pattern
    if len(s) < 8:
        return True
    return False


def _parse_ddmmyyyy(value: Any) -> Optional[Tuple[int, int, int]]:
    """Parse DD.MM.YYYY to (day, month, year) or None."""
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$", s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100:
        return (d, mo, y)
    return None


def _parse_marriage_place_date(value: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse tolerant marriage place/date input:
      - "City DD.MM.YYYY"
      - "City, DD.MM.YYYY"
    Returns (city, date_str, error_key) where error_key is:
      - "date_format" when trailing date token is invalid/missing
      - "value_invalid" when city part is empty
      - None on success
    """
    if value is None:
        return None, None, None
    s = str(value).strip()
    if not s:
        return None, None, None

    # Accept:
    #   "Berlin 15.05.2020"
    #   "Berlin, 15.05.2020"
    #   "Berlin,15.05.2020"
    m = re.match(r"^\s*(.+?)\s*,?\s*(\d{2}\.\d{2}\.\d{4})\s*$", s)
    if not m:
        return None, None, "date_format"

    city = m.group(1).strip()
    date_str = m.group(2).strip()
    if not city:
        return None, None, "value_invalid"
    return city, date_str, None


def _compose_previous_address(a: Dict[str, Any]) -> str:
    """
    Build previous_address from split previous_* fields when combined field is absent.
    """
    plz = str(a.get("previous_plz") or a.get("previous_address_plz") or "").strip()
    ort = str(a.get("previous_ort") or a.get("previous_address_city") or "").strip()
    street = str(a.get("previous_strasse") or a.get("previous_address_street") or "").strip()
    hnr = str(a.get("previous_hausnummer") or a.get("previous_address_house_number") or "").strip()

    parts: List[str] = []
    if street:
        parts.append(street + (f" {hnr}" if hnr else ""))
    if plz or ort:
        parts.append(" ".join(p for p in [plz, ort] if p))

    return ", ".join(parts).strip()


def _date_compare(date1: Optional[Tuple[int, int, int]], date2: Optional[Tuple[int, int, int]]) -> int:
    """Compare (d,m,y) tuples. Return -1 if date1 < date2, 0 if equal, 1 if date1 > date2."""
    if not date1 or not date2:
        return 0
    y1, m1, d1 = date1[2], date1[1], date1[0]
    y2, m2, d2 = date2[2], date2[1], date2[0]
    if y1 != y2:
        return -1 if y1 < y2 else 1
    if m1 != m2:
        return -1 if m1 < m2 else 1
    if d1 != d2:
        return -1 if d1 < d2 else 1
    return 0


def _tuple_to_date(t: Tuple[int, int, int]) -> date_type:
    """(d, m, y) → date for comparison with today."""
    return date_type(t[2], t[1], t[0])


# -----------------------------------------------------------------------------
# Pre-validation normalization: unify field names and values from any frontend.
# -----------------------------------------------------------------------------
def normalize_answers(a: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize raw answers dict before validation.

    Handles:
    - Frontend field key aliases (previous_address_city → previous_ort, etc.)
    - Date format conversion (YYYY-MM-DD → DD.MM.YYYY)
    - Gender, country code normalization
    - Phone/email cleanup
    - String trimming
    """
    a = dict(a)  # shallow copy — do not mutate caller's dict

    # ---- A. Address key aliases (previous address) ----
    if not a.get("previous_plz"):
        a["previous_plz"] = a.get("previous_address_plz") or ""
    if not a.get("previous_ort"):
        a["previous_ort"] = a.get("previous_address_city") or ""
    if not a.get("previous_strasse"):
        a["previous_strasse"] = a.get("previous_address_street") or ""
    if not a.get("previous_hausnummer"):
        a["previous_hausnummer"] = a.get("previous_address_house_number") or ""

    # ---- A2. Address key aliases (current address) ----
    if not a.get("plz"):
        a["plz"] = a.get("address_plz") or ""
    if not a.get("ort"):
        a["ort"] = a.get("address_city") or ""
    if not a.get("strasse"):
        a["strasse"] = a.get("address_street") or ""
    if not a.get("hausnummer"):
        a["hausnummer"] = a.get("address_house_number") or ""

    # ---- B. Date format: YYYY-MM-DD → DD.MM.YYYY ----
    def _norm_date(v: Any) -> str:
        s = str(v or "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            y, m, d = s.split("-")
            return f"{d}.{m}.{y}"
        return s

    for _date_field in ("birth_date", "move_in_date", "move_out_date",
                        "signature_date", "child_birth_date",
                        "ausstellungsdatum", "gueltig_bis", "person2_birth_date"):
        if a.get(_date_field):
            a[_date_field] = _norm_date(a[_date_field])

    # ---- C. Gender normalization → canonical short form ----
    _GENDER_MAP: Dict[str, str] = {
        "male": "m", "männlich": "m", "herr": "m",
        "female": "w", "weiblich": "w", "frau": "w",
        "f": "w",
    }
    if a.get("gender"):
        a["gender"] = _GENDER_MAP.get(str(a["gender"]).strip().lower(), a["gender"])

    # ---- D. Country code normalization ----
    _COUNTRY_MAP: Dict[str, str] = {
        "germany": "DE", "deutschland": "DE", "de": "DE",
        "ukraine": "UA", "україна": "UA", "ua": "UA",
        "poland": "PL", "polska": "PL", "pl": "PL",
    }
    if a.get("country"):
        _c = str(a["country"]).strip().lower()
        a["country"] = _COUNTRY_MAP.get(_c, a["country"])

    # ---- E. Phone: keep only digits and preserve leading + ----
    if a.get("phone"):
        _ph = str(a["phone"]).strip()
        _digits = re.sub(r"\D", "", _ph)
        a["phone"] = ("+" + _digits) if _ph.startswith("+") else _digits

    # ---- F. Email: strip + lowercase ----
    if a.get("email"):
        a["email"] = str(a["email"]).strip().lower()

    # ---- G. Trim all string values ----
    a = {k: (str(v).strip() if isinstance(v, str) else v) for k, v in a.items()}

    return a


# -----------------------------------------------------------------------------
# Main: validate Anmeldung form (strict). Reusable for other doc types later.
# -----------------------------------------------------------------------------
def validate_anmeldung_form(
    answers: Dict[str, Any],
    lang: str = "en",
) -> Tuple[bool, List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Run all strict validations on Anmeldung form data.

    Returns:
        (is_valid, errors, warnings)
        - errors: list of {"field": "...", "message_key": "..."} — hard block
        - warnings: list of {"field": "...", "message_key": "..."} — soft

    Used by:
        - WebApp (client can mirror these rules and message_keys)
        - docs_new.py before showing payment / creating order
        - stripe_handler before create_final_pdf
    """
    answers = normalize_answers(answers)
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    def get(key: str) -> Optional[str]:
        v = answers.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
        return None

    # 1) Required fields — already enforced by schema; we only add if missing for critical ones
    required_critical = [
        "last_name", "first_name", "birth_date", "birth_place",
        "postal_code", "city", "street", "house_number", "move_in_date",
        "landlord_name",
        "landlord_street", "landlord_house_number", "landlord_plz", "landlord_city",
        "dokumentenart",
        "signature_date", "weitere_wohnungen",
    ]
    # Document-section fields (ausstellungsbehoerde, seriennummer, ausstellungsdatum, gueltig_bis)
    # are ONLY required when dokumentenart was submitted — i.e. the dokumente section was visible
    # and the user actually filled it. If dokumentenart is absent the section was hidden, so we
    # must not block submission for these fields.
    _doc_section_fields = ["ausstellungsbehoerde", "seriennummer", "ausstellungsdatum", "gueltig_bis"]

    plz_val = get("postal_code") or get("plz")
    city = get("city")

    # 0) Forbidden placeholders: no REQUIRED_FROM_USER, OE, –, etc. in any required/key field
    for key in required_critical:
        val = get(key)
        if key == "postal_code" and not val:
            val = plz_val
        if val and _is_forbidden_placeholder(val):
            errors.append({"field": key, "message_key": "placeholder_not_allowed"})

    for key in required_critical:
        val = get(key)
        if key == "postal_code" and not val:
            val = plz_val
        if not val:
            errors.append({"field": key, "message_key": "required"})

    # Conditional: only enforce doc-section fields when dokumentenart was actually submitted
    _dokart = get("dokumentenart")
    if _dokart:
        for key in _doc_section_fields:
            val = get(key)
            if val and _is_forbidden_placeholder(val):
                errors.append({"field": key, "message_key": "placeholder_not_allowed"})
            elif not val:
                errors.append({"field": key, "message_key": "required"})

    # 1b) Date format: all date fields must be DD.MM.YYYY
    _date_fields = [
        "birth_date", "move_in_date", "move_out_date",
        "ausstellungsdatum", "gueltig_bis", "signature_date",
        "person2_birth_date",
    ]
    _date_re = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    for df in _date_fields:
        dval = get(df)
        if dval and not _date_re.match(dval):
            errors.append({"field": df, "message_key": "date_format"})

    # 1c) Conditional: Familienstand = verheiratet/Lebenspartnerschaft → marriage date required
    _fam = (get("familienstand") or "").strip().lower()
    if _fam in ("verheiratet", "eingetragene lebenspartnerschaft"):
        if not get("eheschliessung_ort_datum"):
            errors.append({"field": "eheschliessung_ort_datum", "message_key": "marriage_date_required"})

    # 1c.1) marriage place/date format validation (tolerant input; strict date token)
    _marriage_raw = get("eheschliessung_ort_datum")
    if _marriage_raw:
        _city_part, _date_part, _marriage_err = _parse_marriage_place_date(_marriage_raw)
        if _marriage_err:
            errors.append({"field": "eheschliessung_ort_datum", "message_key": _marriage_err})

    # 1d) Conditional: has_bisherige_wohnung = Ja → previous_address required
    _has_prev = (get("has_bisherige_wohnung") or "").strip().lower()
    if _has_prev in {"ja", "так", "yes"}:
        _prev_addr = get("previous_address") or _compose_previous_address(answers)
        if not _prev_addr:
            errors.append({"field": "previous_address", "message_key": "previous_address_required"})

    # 1e) Conditional: wohnungstyp = Nebenwohnung → must have bisherige Wohnung
    _wtyp = (get("wohnungstyp") or "").strip()
    if _wtyp == "Nebenwohnung" and _has_prev not in {"ja", "так", "yes"}:
        errors.append({"field": "has_bisherige_wohnung", "message_key": "nebenwohnung_needs_previous"})

    # 2) PLZ format: exactly 5 digits, Germany only (01000–99999)
    if plz_val:
        digits = re.sub(r"\D", "", plz_val)
        if len(digits) != 5:
            errors.append({"field": "postal_code", "message_key": "plz_format"})
        elif not _is_german_plz(plz_val):
            errors.append({"field": "postal_code", "message_key": "plz_germany_only"})

    # 2b) Name format: letters only (first_name, last_name)
    for key in ("first_name", "last_name"):
        val = get(key)
        if val and not _valid_name(val):
            errors.append({"field": key, "message_key": "name_letters_only"})

    # 2c) Street: no digits
    street_val = get("street")
    if street_val and not _valid_street(street_val):
        errors.append({"field": "street", "message_key": "street_no_digits"})

    # 2d) City: letters only, no digits
    if city and not _valid_city(city):
        errors.append({"field": "city", "message_key": "value_invalid"})

    # 2e) Landlord sub-fields validation (new structured address)
    _landlord_street = get("landlord_street")
    _landlord_hn     = get("landlord_house_number")
    _landlord_plz    = get("landlord_plz")
    _landlord_city   = get("landlord_city")

    if _landlord_street and not _valid_street(_landlord_street):
        errors.append({"field": "landlord_street", "message_key": "street_no_digits"})

    if _landlord_hn:
        _hn_re = re.compile(r"^\d+[A-Za-z]?$")
        if not _hn_re.match(_landlord_hn.strip()):
            errors.append({"field": "landlord_house_number", "message_key": "value_invalid"})

    if _landlord_plz and not _is_german_plz(_landlord_plz):
        digits = re.sub(r"\D", "", _landlord_plz)
        if len(digits) != 5:
            errors.append({"field": "landlord_plz", "message_key": "plz_format"})
        else:
            errors.append({"field": "landlord_plz", "message_key": "plz_germany_only"})

    if _landlord_city and not _valid_city(_landlord_city):
        errors.append({"field": "landlord_city", "message_key": "value_invalid"})

    # 3) City ↔ PLZ consistency
    if city and _city_looks_berlin(city) and plz_val:
        digits = re.sub(r"\D", "", plz_val)
        if len(digits) == 5 and not is_berlin_plz(plz_val):
            errors.append({"field": "postal_code", "message_key": "plz_berlin"})
    # If PLZ is Berlin but city is not Berlin → mismatch
    if plz_val and len(re.sub(r"\D", "", plz_val)) == 5 and is_berlin_plz(plz_val) and city and not _city_looks_berlin(city):
        errors.append({"field": "city", "message_key": "plz_city_mismatch", "params": {"plz": plz_val, "city": city}})

    # 4) Document number by type
    doc_art = get("dokumentenart")
    serien = get("seriennummer")
    if doc_art and serien:
        ok, msg_key = _validate_document_number(doc_art, serien)
        if not ok:
            errors.append({"field": "seriennummer", "message_key": msg_key or "document_number"})

    # 5) Ausstellungsbehörde: only validate when dokumentenart was submitted (section visible)
    auth = get("ausstellungsbehoerde")
    if get("dokumentenart"):
        if not auth:
            errors.append({"field": "ausstellungsbehoerde", "message_key": "authority_empty"})
        elif _looks_suspicious_authority(auth):
            warnings.append({"field": "ausstellungsbehoerde", "message_key": "authority_suspicious"})
    elif auth and _looks_suspicious_authority(auth):
        warnings.append({"field": "ausstellungsbehoerde", "message_key": "authority_suspicious"})

    # 6) Date logic: gültig bis ≥ Ausstellungsdatum; Ausstellungsdatum ≤ today; birth_date < Ausstellungsdatum; no future dates
    today = date_type.today()
    issue_str = get("ausstellungsdatum")
    expiry_str = get("gueltig_bis")
    birth_str = get("birth_date")
    move_in_str = get("move_in_date")
    issue_d = _parse_ddmmyyyy(issue_str) if issue_str else None
    expiry_d = _parse_ddmmyyyy(expiry_str) if expiry_str else None
    birth_d = _parse_ddmmyyyy(birth_str) if birth_str else None
    move_in_d = _parse_ddmmyyyy(move_in_str) if move_in_str else None

    if move_in_d and _tuple_to_date(move_in_d) > today:
        errors.append({"field": "move_in_date", "message_key": "date_future"})
    if birth_d and _tuple_to_date(birth_d) > today:
        errors.append({"field": "birth_date", "message_key": "date_future"})
    if issue_d:
        if _tuple_to_date(issue_d) > today:
            errors.append({"field": "ausstellungsdatum", "message_key": "date_future"})
    if issue_d and expiry_d:
        if _date_compare(expiry_d, issue_d) < 0:
            errors.append({"field": "gueltig_bis", "message_key": "date_logic"})
    if issue_d and birth_d:
        if _date_compare(birth_d, issue_d) >= 0:
            errors.append({"field": "birth_date", "message_key": "date_logic"})
    if move_in_d and birth_d:
        if _date_compare(birth_d, move_in_d) >= 0:
            errors.append({"field": "birth_date", "message_key": "date_logic"})

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def get_validation_errors_localized(
    errors: List[Dict[str, Any]],
    lang: str,
) -> List[Dict[str, str]]:
    """Return errors with localized message text: [{field, message_key, message}]."""
    out = []
    for e in errors:
        key = e.get("message_key") or "value_invalid"
        params = e.get("params")
        out.append({
            "field": e.get("field", ""),
            "message_key": key,
            "message": get_validation_message(key, lang, params=params),
        })
    return out
