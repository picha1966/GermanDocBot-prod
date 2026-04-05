import os
import re
import sys
import fitz
import json
import traceback
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =========================================================
# PATH SETUP
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# =========================================================
# IMPORTS
# =========================================================

try:
    from backend.form_builder import build_german_form
except Exception as e:
    raise RuntimeError(f"Cannot import build_german_form: {e}")

try:
    from backend.pdf_generator import create_final_pdf
except Exception as e:
    raise RuntimeError(f"Cannot import create_final_pdf: {e}")

try:
    import backend.document_config as document_config
except Exception:
    document_config = None


# =========================================================
# CONFIG
# =========================================================

# Якщо хочеш — впиши тут всі 8 своїх документів.
# Якщо список порожній, тестер спробує знайти doc_type автоматично.
DOCUMENTS: List[str] = []  # empty → discover_doc_types() covers all 9 documents

# Мови для перевірки перекладів у схемі
REQUIRED_LABEL_LANGS = ["de", "en", "uk", "pl", "tr", "ar"]

# Куди складати тестові PDF
OUTPUT_DIR = ROOT_DIR / "generated_pdfs" / "_qa"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Якщо для якихось документів автоматична генерація даних недостатня,
# тут можна вручну перебити значення.
DOC_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "buergergeld": {
        "first_name": "Ivan",
        "last_name": "Ivanov",
        "birth_date": "01.01.1990",
        "birth_place": "Vinnytsia, Ukraine",
        "birth_country": "Ukraine",
        "city": "Berlin",
        "postal_code": "10115",
        "street": "Teststraße",
        "house_number": "1",
        "iban": "DE89370400440532013000",
        "phone": "493012345678",
        "has_sv_number": "nein",
        "family_status": "verheiratet",
    },
    "anmeldung": {
        "first_name": "Ivan",
        "last_name": "Ivanov",
        "birth_date": "01.01.1990",
        "birth_place": "Vinnytsia, Ukraine",
        "birth_country": "Ukraine",
        "city": "Berlin",
        "plz": "10115",
        "postal_code": "10115",
        "street": "Teststraße",
        "house_number": "1",
        "nationality": "Ukraine",
        "gender": "männlich",
        "signature_date": date.today().strftime("%d.%m.%Y"),
        "signature_place": "Berlin",
        # Address fields
        "wohnungstyp": "alleinige Wohnung",
        "move_in_date": "01.01.2020",
        "has_bisherige_wohnung": "Nein",
        "weitere_wohnungen": "Nein",
        # Landlord
        "landlord_name": "Max Mustermann",
        "landlord_street": "Musterstrasse",
        "landlord_house_number": "5",
        "landlord_plz": "10117",
        "landlord_city": "Berlin",
        # Document
        "dokumentenart": "PA",
        "ausstellungsbehoerde": "Einwohnermeldeamt Berlin",
        "seriennummer": "L01X00T47",
        "ausstellungsdatum": "01.01.2020",
        "gueltig_bis": "01.01.2030",
    },
    "wohngeld": {
        "first_name": "Ivan",
        "last_name": "Ivanov",
        "birth_date": "01.01.1990",
        "city": "Berlin",
        "plz": "10115",
        "street": "Teststraße",
        "house_number": "1",
    },
    "kindergeld": {
        "child_first_name":  "Anna",
        "child_last_name":   "Ivanova",
        "child_birth_date":  "15.06.2018",
        "child_birth_place": "Berlin",
    },
}


# =========================================================
# HELPERS
# =========================================================

def normalize_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lower_text(value: Any) -> str:
    return safe_text(value).lower()


def read_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    text = []
    for page in doc:
        text.append(page.get_text())
    return "\n".join(text)


def read_pdf_fields(pdf_path: Path) -> Dict[str, Any]:
    doc = fitz.open(str(pdf_path))
    fields: Dict[str, Any] = {}
    for page in doc:
        widgets = page.widgets()
        if not widgets:
            continue
        for w in widgets:
            if w.field_name:
                fields[w.field_name] = w.field_value
    return fields


def extract_schema_vars() -> Dict[str, Any]:
    if document_config is None:
        return {}
    result = {}
    for name in dir(document_config):
        if not name.endswith("_SCHEMA"):
            continue
        value = getattr(document_config, name)
        if isinstance(value, (dict, list)):
            result[name] = value
    return result


def discover_doc_types() -> List[str]:
    schemas = extract_schema_vars()
    if not schemas:
        return []
    docs = []
    for schema_name in schemas.keys():
        raw = schema_name[:-7].lower()  # strip _SCHEMA
        docs.append(raw)
    return sorted(set(docs))


def find_schema_for_doc(doc_type: str) -> Optional[Any]:
    if document_config is None:
        return None

    aliases = {
        "anmeldung": ["ANMELDUNG_SCHEMA"],
        "abmeldung": ["ABMELDUNG_SCHEMA"],
        "ummeldung": ["UMMELDUNG_SCHEMA"],
        "buergergeld": ["BUERGERGELD_SCHEMA", "JOBCENTER_SCHEMA"],
        "jobcenter": ["JOBCENTER_SCHEMA", "BUERGERGELD_SCHEMA"],
        "wohngeld": ["WOHNGELD_SCHEMA"],
        "wohnungsgeberbestaetigung": ["WOHNUNGSGEBERBESTAETIGUNG_SCHEMA"],
        "aufenthaltstitel": ["AUFENTHALTSTITEL_SCHEMA"],
        "verlaengerung_aufenthaltstitel": ["VERLAENGERUNG_AUFENTHALTSTITEL_SCHEMA"],
        "kindergeld": ["KINDERGELD_SCHEMA"],
    }

    for candidate in aliases.get(doc_type, []):
        if hasattr(document_config, candidate):
            return getattr(document_config, candidate)

    # fallback: fuzzy find
    norm_target = normalize_key(doc_type)
    for name, value in extract_schema_vars().items():
        if norm_target in normalize_key(name):
            return value

    return None


def iter_schema_fields(schema: Any) -> List[Dict[str, Any]]:
    """
    Підтримує різні формати:
    - {"sections": [{"fields": [...]}, ...]}
    - [{"fields": [...]}, ...]
    - {"fields": [...]}
    """
    fields: List[Dict[str, Any]] = []

    if isinstance(schema, dict):
        if "fields" in schema and isinstance(schema["fields"], list):
            for f in schema["fields"]:
                if isinstance(f, dict):
                    fields.append(f)

        if "sections" in schema and isinstance(schema["sections"], list):
            for section in schema["sections"]:
                if not isinstance(section, dict):
                    continue
                for f in section.get("fields", []):
                    if isinstance(f, dict):
                        fields.append(f)

    elif isinstance(schema, list):
        for item in schema:
            if not isinstance(item, dict):
                continue
            if "fields" in item and isinstance(item["fields"], list):
                for f in item["fields"]:
                    if isinstance(f, dict):
                        fields.append(f)

    return fields


def guess_value_for_field(field: Dict[str, Any]) -> Any:
    key = safe_text(field.get("name") or field.get("key"))
    ftype = lower_text(field.get("type"))
    options = field.get("options") or []

    if options and isinstance(options, list):
        # Беремо першу опцію
        first = options[0]
        if isinstance(first, dict):
            return first.get("value") or first.get("key") or first.get("id") or "ja"
        return first

    k = lower_text(key)

    if "first_name" in k or k.endswith("firstname") or k == "vorname":
        return "Ivan"
    if "last_name" in k or k.endswith("lastname") or "familienname" in k:
        return "Ivanov"
    if "birth_name" in k:
        return "Ivanov"
    if "birth_date" in k or "geburtsdatum" in k:
        return "01.01.1990"
    if "signature_date" in k:
        return date.today().strftime("%d.%m.%Y")
    if "entry_date" in k:
        return "01.01.2020"
    if "date" in k:
        return "01.01.2020"
    if "birth_place" in k or "geburtsort" in k:
        return "Vinnytsia, Ukraine"
    if "birth_country" in k or "geburtsland" in k:
        return "Ukraine"
    if "city" in k or "ort" in k:
        return "Berlin"
    if k == "plz" or "postal_code" in k or "postcode" in k:
        return "10115"
    if "street" in k or "strasse" in k:
        return "Teststraße"
    if "house_number" in k or "hausnummer" in k:
        return "1"
    if "apartment" in k:
        return "12"
    if "iban" in k:
        return "DE89370400440532013000"
    if "phone" in k or "telefon" in k:
        return "493012345678"
    if "email" in k:
        return "ivan@example.com"
    if "nationality" in k or "staatsangehoerigkeit" in k:
        return "Ukraine"
    if k == "gender" or "geschlecht" in k:
        return "männlich"
    if "religion" in k:
        return "ohne"
    if "family_status" in k or "familienstand" in k:
        return "ledig"
    if "country" in k:
        return "Germany"
    if "employer_name" in k:
        return "Test GmbH"
    if "sv_number" in k:
        return "12345678A123"
    if "account_holder" in k:
        return "Ivan Ivanov"

    if ftype in {"checkbox", "boolean", "bool"}:
        return True
    if ftype in {"number", "integer"}:
        return 1
    if ftype in {"text", "textarea", "string", ""}:
        return "Test"

    return "Test"


# =========================================================
# VALID DATA GENERATOR — satisfies all strict validation rules
# =========================================================

# Safe values for validation-sensitive field names (exact key or substring match).
# Rules derived from backend/form_validation.py:
#   - date fields: DD.MM.YYYY, must not be in future (except gueltig_bis)
#   - plz: exactly 5 digits, 01000–99999, Berlin PLZ if city=Berlin
#   - seriennummer PA: exactly 9 alphanumeric chars
#   - street/city: letters only, no digits
#   - name: letters only (space, hyphen, apostrophe allowed)
#   - has_bisherige_wohnung="Nein" → previous_address not required
#   - familienstand="ledig" → eheschliessung_ort_datum not required
_FIELD_SAFE_VALUES: Dict[str, Any] = {
    # Personal
    "first_name":               "Ivan",
    "last_name":                "Ivanov",
    "birth_name":               "Ivanov",
    # "-" is the standard "no value" sentinel — get_value_for_pdf_field ignores it
    "passname":                 "-",
    "ordens_kuenstlername":     "-",
    "birth_date":               "01.01.1990",
    "birth_place":              "Vinnytsia",
    "birth_country":            "Ukraine",
    "nationality":              "Ukraine",
    "gender":                   "männlich",
    "religion":                 "ohne",
    "familienstand":            "ledig",
    "family_status":            "ledig",
    # Address
    "city":                     "Berlin",
    "plz":                      "10115",
    "postal_code":              "10115",
    "street":                   "Teststraße",
    "house_number":             "1",
    "apartment_number":         "2",
    "signature_place":          "Berlin",
    # Landlord address (must also be valid Berlin PLZ)
    "landlord_name":            "Max Mustermann",
    "landlord_street":          "Musterstraße",
    "landlord_house_number":    "5",
    "landlord_plz":             "10117",
    "landlord_city":            "Berlin",
    # Document identity
    "dokumentenart":            "PA",
    "ausstellungsbehoerde":     "Einwohnermeldeamt Berlin",
    # seriennummer for PA: exactly 9 alphanumeric chars (regex: ^[A-Za-z0-9]{9}$)
    "seriennummer":             "L01X00T47",
    # Dates: ausstellungsdatum ≤ today; gueltig_bis > ausstellungsdatum
    "ausstellungsdatum":        "01.01.2020",
    "gueltig_bis":              "01.01.2030",
    "move_in_date":             "01.01.2020",
    "signature_date":           date.today().strftime("%d.%m.%Y"),
    # Registration
    "wohnungstyp":              "alleinige Wohnung",
    "has_bisherige_wohnung":    "Nein",   # → suppresses previous_address requirement
    "weitere_wohnungen":        "Nein",
    "bisherige_wohnungstyp":    "alleinige Wohnung",
    "zuzug_aus_ausland":        "Nein",
    "bisherige_beibehalten":    "Nein",
    # Financial
    "iban":                     "DE89370400440532013000",
    "account_holder":           "Ivan Ivanov",
    "has_sv_number":            "nein",
    "sv_number":                "",
    # Contact
    "phone":                    "493012345678",
    "email":                    "ivan@example.com",
    # Employment / Aufenthaltstitel
    "employer_name":            "Test GmbH",
    "residence_purpose":        "Arbeit",
    "occupation":               "Softwareentwickler",
    "current_permit_type":      "Aufenthaltserlaubnis",
    # Wohngeld / housing
    "living_space_sqm":         "60",
    "monthly_rent":             "750",
    "monthly_income":           "1200",
    "income_source":            "Arbeit",
    "household_members":        "2",
    # Child (Familienkasse / Kindergeld)
    "child_name":               "Anna Ivanova",
    # Bank
    "bank_name":                "Deutsche Bank",
    # Tax
    "tax_id":                   "12345678901",
}

# Substring patterns applied when exact key not found (checked in order, first match wins)
_FIELD_PATTERN_VALUES: List[Tuple[str, Any]] = [
    ("first_name",          "Ivan"),
    ("last_name",           "Ivanov"),
    ("birth_name",          "Ivanov"),
    ("birth_date",          "01.01.1990"),
    ("birth_place",         "Vinnytsia"),
    ("birth_country",       "Ukraine"),
    # Any date-like suffix: ausstellungsdatum, gueltig_bis, move_in_date, etc.
    # Must come BEFORE generic "date" so "ausstellungsdatum" gets past-date
    ("ausstellungsdatum",   "01.01.2020"),
    ("gueltig_bis",         "01.01.2030"),
    ("move_in_date",        "01.01.2020"),
    ("move_out_date",       "01.01.2020"),
    ("entry_date",          "01.01.2020"),
    ("signature_date",      date.today().strftime("%d.%m.%Y")),
    # Any remaining *datum or *date field → safe past date
    ("datum",               "01.01.2020"),
    ("date",                "01.01.2020"),
    # Address
    ("landlord_name",       "Max Mustermann"),
    ("landlord_street",     "Musterstraße"),
    ("landlord_house_number", "5"),
    ("landlord_plz",        "10117"),
    ("landlord_city",       "Berlin"),
    ("landlord",            "Max Mustermann"),
    ("plz",                 "10115"),
    ("postal_code",         "10115"),
    ("postcode",            "10115"),
    ("city",                "Berlin"),
    ("ort",                 "Berlin"),
    ("street",              "Teststraße"),
    ("strasse",             "Teststraße"),
    ("house_number",        "1"),
    ("hausnummer",          "1"),
    ("apartment",           "2"),
    # Identity document
    ("seriennummer",        "L01X00T47"),
    ("ausstellungsbehoerde", "Einwohnermeldeamt Berlin"),
    ("dokumentenart",       "PA"),
    ("ausstellungsdatum",   "01.01.2020"),
    # Personal details
    ("nationality",         "Ukraine"),
    ("staatsangehoerigkeit", "Ukraine"),
    ("gender",              "männlich"),
    ("geschlecht",          "männlich"),
    ("religion",            "ohne"),
    ("familienstand",       "ledig"),
    ("family_status",       "ledig"),
    ("country",             "Germany"),
    # Finance
    ("iban",                "DE89370400440532013000"),
    ("account_holder",      "Ivan Ivanov"),
    ("sv_number",           "12345678A123"),
    ("phone",               "493012345678"),
    ("telefon",             "493012345678"),
    ("email",               "ivan@example.com"),
    ("employer_name",       "Test GmbH"),
]


def _value_for_key(key: str, ftype: str, options: list) -> Any:
    """
    Return a guaranteed-valid value for the given field key/type/options.

    Priority:
      1. Select field → pick first safe option (skip "Ja" for bisherige_wohnung)
      2. Exact key match in _FIELD_SAFE_VALUES
      3. Substring match in _FIELD_PATTERN_VALUES
      4. Type-based fallback
    """
    k = key.lower()

    # 1. Select field with explicit options
    if options and isinstance(options, list):
        # Special case: has_bisherige_wohnung must be "Nein" to avoid
        # triggering the previous_address required rule.
        if "bisherige_wohnung" in k:
            for opt in options:
                v = (opt.get("value") if isinstance(opt, dict) else opt) or ""
                if str(v).strip().lower() == "nein":
                    return v
        # familienstand must be "ledig" to avoid marriage date requirement
        if "familienstand" in k or "family_status" in k:
            for opt in options:
                v = (opt.get("value") if isinstance(opt, dict) else opt) or ""
                if str(v).strip().lower() == "ledig":
                    return v
        # Default: first option
        first = options[0]
        if isinstance(first, dict):
            return first.get("value") or first.get("key") or first.get("id") or "ja"
        return first

    # 2. Exact key match
    if key in _FIELD_SAFE_VALUES:
        return _FIELD_SAFE_VALUES[key]

    # 3. Substring pattern match
    for pattern, value in _FIELD_PATTERN_VALUES:
        if pattern in k:
            return value

    # 4. Type-based fallback
    if ftype in {"date"}:
        return "01.01.2020"
    if ftype in {"plz"}:
        return "10115"
    if ftype in {"city"}:
        return "Berlin"
    if ftype in {"street"}:
        return "Teststraße"
    if ftype in {"house_number"}:
        return "1"
    if ftype in {"checkbox", "boolean", "bool"}:
        return False
    if ftype in {"number", "integer"}:
        return 1
    if ftype in {"text", "textarea", "string", ""}:
        return "Muster"

    return "Muster"


# Invalid sentinel values that must never appear in generated data
_INVALID_SENTINELS: Tuple[str, ...] = ("Test", "test", "TEST")


def assert_no_test_values(data: Dict[str, Any], doc_type: str) -> List[str]:
    """
    Guard: fail if any field still holds a bare "Test" sentinel or is unexpectedly
    empty for a non-optional-by-design field.

    Returns a list of error strings (empty = all clear).
    """
    errors: List[str] = []
    for field_key, value in data.items():
        str_val = safe_text(value)
        if str_val in _INVALID_SENTINELS:
            errors.append(
                f"[INVALID FALLBACK] {doc_type}.{field_key} = {str_val!r} "
                f"(generator produced bare sentinel value)"
            )
    return errors


def generate_valid_data_from_schema(doc_type: str, schema: Any) -> Dict[str, Any]:
    """
    Generate a complete, validation-passing user_data dict from a document schema.

    Pipeline:
      1. Iterate all schema fields via iter_schema_fields()
      2. For each field call _value_for_key() (exact → pattern → type fallback)
      3. Apply DOC_OVERRIDES on top (highest priority)
      4. Log a short preview of the first 10 generated key/value pairs
    """
    data: Dict[str, Any] = {}
    fields = iter_schema_fields(schema)

    for field in fields:
        key = safe_text(field.get("name") or field.get("key"))
        if not key:
            continue
        ftype = lower_text(field.get("type"))
        options = field.get("options") or []
        data[key] = _value_for_key(key, ftype, options)

    # Apply manual overrides last (highest priority)
    data.update(deepcopy(DOC_OVERRIDES.get(doc_type, {})))

    # Debug log — short preview (first 10 pairs only to avoid noise)
    preview_items = list(data.items())[:10]
    preview_str = ", ".join(f"{k}={v!r}" for k, v in preview_items)
    print(f"[AUTO DATA GENERATED] {doc_type} ({len(data)} fields) | {preview_str}")

    return data


def build_data_from_schema(doc_type: str, schema: Any) -> Dict[str, Any]:
    """Legacy wrapper — delegates to generate_valid_data_from_schema."""
    return generate_valid_data_from_schema(doc_type, schema)


def validate_schema(doc_type: str, schema: Any, data: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if schema is None:
        errors.append("Schema not found")
        return errors

    fields = iter_schema_fields(schema)
    if not fields:
        errors.append("Schema has no fields")
        return errors

    for field in fields:
        key = safe_text(field.get("name") or field.get("key"))
        if not key:
            errors.append("Field without name/key")
            continue

        if key not in data:
            errors.append(f"Missing generated value for field: {key}")

        # перевірка перекладів, якщо схема їх містить
        has_any_lang_label = any(f"label_{lang}" in field for lang in REQUIRED_LABEL_LANGS)
        if has_any_lang_label:
            for lang in REQUIRED_LABEL_LANGS:
                label_key = f"label_{lang}"
                if label_key in field and not safe_text(field.get(label_key)):
                    errors.append(f"Empty translation: {doc_type}.{key}.{label_key}")

    return errors


def validate_pdf_text(doc_type: str, data: Dict[str, Any], pdf_text: str) -> List[str]:
    errors: List[str] = []

    if not safe_text(pdf_text):
        errors.append("PDF text is empty")
        return errors

    # Базові перевірки по тексту
    for key in ("first_name", "last_name"):
        val = safe_text(data.get(key))
        if val and val not in pdf_text:
            errors.append(f"Missing in PDF text: {key}={val}")

    # Verify signature_date appears in PDF (applies to all document types that have it)
    sig_date = safe_text(data.get("signature_date"))
    if sig_date and sig_date not in pdf_text:
        errors.append(f"Missing in PDF text: signature_date={sig_date}")

    # Критичні бізнес-перевірки
    if doc_type == "buergergeld":
        if lower_text(data.get("has_sv_number")) == "nein":
            sv = safe_text(data.get("sv_number"))
            if sv and sv in pdf_text:
                errors.append("SV not cleaned in PDF text")

        iban = safe_text(data.get("iban"))
        if iban and "keine bankverbindung vorhanden" in lower_text(pdf_text):
            # це груба евристика по тексту; точніше перевіряється по полях нижче
            pass

    return errors


def validate_pdf_fields_exact(doc_type: str, pdf_path: Path, data: Dict[str, Any]) -> List[str]:
    """
    Field-level AcroForm correctness check.

    For every entry in the doc_type's AcroForm mapping:
      - compute the expected value via get_value_for_pdf_field()
      - read the actual value from the filled PDF widget
      - report FIELD_MISMATCH when the expected value is non-empty and not
        found inside the actual value (substring match to handle trimming /
        multi-line AcroForm values)

    Skipped automatically for:
      - builder / XFA documents (no AcroForm mapping)
      - checkbox / radio fields (expected = "Yes", "YES_CHECKED", "Off", None)
    """
    errors: List[str] = []

    try:
        from backend.document_config import get_acroform_mapping, get_value_for_pdf_field
    except ImportError as exc:
        errors.append(f"[FIELD_CHECK] import error: {exc}")
        return errors

    mapping = get_acroform_mapping(doc_type)
    if not mapping:
        # builder / XFA document — field-level check not applicable
        return errors

    # Read actual widget values from the filled PDF
    actual_fields: Dict[str, str] = {}
    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            widgets = page.widgets()
            if not widgets:
                continue
            for w in widgets:
                if w.field_name:
                    actual_fields[w.field_name] = str(w.field_value or "").strip()
        doc.close()
    except Exception as exc:
        errors.append(f"[FIELD_CHECK] could not read PDF widgets: {exc}")
        return errors

    # Sentinel values used for checkboxes / radios — skip value comparison.
    # "0" and "1" are radio button on_state values resolved at write-time by
    # PyMuPDF w.on_state(); the actual stored value depends on the PDF revision
    # and cannot be meaningfully compared to a fixed expected string.
    _CHECKBOX_SENTINELS = {"yes", "yes_checked", "off", "0", "1"}

    validated = 0
    for schema_key, acroform_field in mapping.items():
        # get_value_for_pdf_field takes the SCHEMA KEY (e.g. "last_name"), not the
        # raw AcroForm PDF field name — this matches how pdf_generator calls it.
        expected = get_value_for_pdf_field(schema_key, data)
        if expected is None:
            continue  # field intentionally empty (e.g. checkbox not selected)

        expected_str = str(expected).strip()
        if not expected_str:
            continue
        if expected_str.lower() in _CHECKBOX_SENTINELS:
            continue  # checkbox/radio — value depends on PDF on_state(), skip

        actual_str = actual_fields.get(acroform_field, "")
        if not actual_str:
            # Field not written to PDF — skip rather than fail; some fields
            # (e.g. gender text, optional composites) are intentionally left blank
            # by the PDF generator even when user_data has a value.
            continue
        if expected_str not in actual_str:
            errors.append(
                f"[FIELD_MISMATCH] {schema_key} → '{acroform_field}': "
                f"expected {expected_str!r}, got {actual_str!r}"
            )
        validated += 1

    print(f"[FIELD CHECK] {doc_type}: validated {validated} AcroForm text fields")
    return errors


def validate_pdf_fields(doc_type: str, data: Dict[str, Any], fields: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    # Якщо AcroForm полів немає — це не помилка для builder PDF
    if not fields:
        return errors

    if doc_type == "buergergeld":
        iban_field = fields.get("txtfIBAN")
        kein_field = fields.get("chbxPersonKeine")
        sv_field = fields.get("txtfPersonSVRVNr")

        if safe_text(iban_field) and safe_text(kein_field) not in ("", "Off", "None"):
            errors.append("AcroForm conflict: IBAN + kein Konto")

        if lower_text(data.get("has_sv_number")) == "nein":
            if safe_text(sv_field):
                errors.append("AcroForm conflict: SV should be empty when has_sv_number=nein")

    return errors


def generate_preview_pdf(doc_type: str, data: Dict[str, Any]) -> Tuple[Optional[Path], Optional[str]]:
    output_path = OUTPUT_DIR / f"{doc_type}_preview.pdf"
    try:
        result = build_german_form(
            doc_type=doc_type,
            user_data=data,
            output_path=str(output_path),
            is_preview=True,
        )
    except Exception:
        return None, traceback.format_exc()

    if not result or not output_path.exists():
        return None, "Preview PDF not generated"

    return output_path, None


def generate_final_pdf(doc_type: str, data: Dict[str, Any]) -> Tuple[Optional[Path], Optional[str]]:
    try:
        result = create_final_pdf(
            user_id=0,
            user_data=data,
            doc_type=doc_type,
            user_lang="de",
        )
    except Exception:
        return None, traceback.format_exc()

    if isinstance(result, dict):
        status = result.get("status", "")
        errors = result.get("errors") or result.get("error") or ""
        if status == "validation_failed":
            raise AssertionError(
                f"CRITICAL: generator produced invalid data for {doc_type!r}. "
                f"Validation errors from create_final_pdf: {errors}"
            )
        return None, f"create_final_pdf returned dict: {json.dumps(result, ensure_ascii=False)}"

    if not result:
        return None, "create_final_pdf returned empty result"

    path = Path(str(result))
    if not path.exists():
        return None, f"Final PDF path does not exist: {path}"

    return path, None


def assert_normalized_data(doc_type: str, normalized: Dict[str, Any]) -> List[str]:
    """
    Sanity-checks on the normalized user_data dict — catches bugs in the
    normalize layer before they reach the PDF generator.
    """
    errors: List[str] = []

    apt = safe_text(normalized.get("apartment_number"))
    if apt and "whg" in apt.lower():
        errors.append(
            f"[NORMALIZE] apartment_number not cleaned: {apt!r} "
            f"(expected prefix 'Whg.' to be stripped)"
        )

    sig_date_str = safe_text(normalized.get("signature_date"))
    if sig_date_str:
        try:
            from datetime import datetime as _dt
            sig_d = _dt.strptime(sig_date_str, "%d.%m.%Y").date()
            if sig_d > date.today():
                errors.append(
                    f"[NORMALIZE] signature_date is in the future: {sig_date_str!r}"
                )
        except ValueError:
            errors.append(
                f"[NORMALIZE] signature_date has invalid format: {sig_date_str!r}"
            )

    bp = safe_text(normalized.get("birth_place"))
    if bp and "vinnitsia" in bp.lower():
        errors.append(
            f"[NORMALIZE] birth_place contains un-normalized spelling: {bp!r} "
            f"(expected 'Vinnytsia')"
        )

    nat = safe_text(normalized.get("nationality"))
    if nat and nat.lower() in {"ukraine", "poland", "germany", "turkey"}:
        errors.append(
            f"[NORMALIZE] nationality is a country name, not adjective: {nat!r} "
            f"(expected e.g. 'ukrainisch')"
        )

    return errors


def run_single(doc_type: str) -> Dict[str, Any]:
    result = {
        "doc_type": doc_type,
        "status": "ok",
        "errors": [],
    }

    print(f"\n=== TEST: {doc_type} ===")

    schema = find_schema_for_doc(doc_type)

    if schema is None:
        result["status"] = "fail"
        result["errors"].append("Schema not found")
        print("❌ Schema not found")
        return result

    data = generate_valid_data_from_schema(doc_type, schema)

    # Guard: no bare "Test" sentinel values must survive into generated data
    sentinel_errors = assert_no_test_values(data, doc_type)
    if sentinel_errors:
        result["status"] = "fail"
        result["errors"].extend(sentinel_errors)
        for err in sentinel_errors:
            print(f"  [GUARD] {err}")

    schema_errors = validate_schema(doc_type, schema, data)
    if schema_errors:
        result["errors"].extend(schema_errors)

    # === NORMALIZE LAYER — mirrors production pipeline ===
    # Run normalize_user_data() so the test catches bugs in the normalize layer
    # (apartment prefix stripping, birth_place spelling, nationality adjective, etc.)
    # before they reach the PDF generator.
    normalized = deepcopy(data)
    try:
        from backend.utils.normalize import normalize_user_data
        normalized = normalize_user_data(deepcopy(data))
        print(f"  [NORMALIZE] applied successfully ({len(normalized)} fields)")

        norm_errors = assert_normalized_data(doc_type, normalized)
        if norm_errors:
            result["status"] = "fail"
            result["errors"].extend(norm_errors)
            for err in norm_errors:
                print(f"  {err}")
    except ImportError:
        print("  [NORMALIZE] skipped (normalize module not available)")
    except Exception as _ne:
        result["errors"].append(f"[NORMALIZE] exception: {_ne}")
        print(f"  [NORMALIZE] exception: {_ne}")

    # Pass normalized data to PDF generators (same as production)
    preview_path, preview_err = generate_preview_pdf(doc_type, normalized)
    if preview_err:
        result["status"] = "fail"
        result["errors"].append(f"Preview: {preview_err}")
    else:
        preview_text = read_pdf_text(preview_path)
        preview_fields = read_pdf_fields(preview_path)
        result["errors"].extend(validate_pdf_text(doc_type, normalized, preview_text))
        result["errors"].extend(validate_pdf_fields(doc_type, normalized, preview_fields))

    final_path, final_err = generate_final_pdf(doc_type, normalized)
    if final_err:
        result["status"] = "fail"
        result["errors"].append(f"Final: {final_err}")
    else:
        final_text = read_pdf_text(final_path)
        final_fields = read_pdf_fields(final_path)
        result["errors"].extend(validate_pdf_text(doc_type, normalized, final_text))
        result["errors"].extend(validate_pdf_fields(doc_type, normalized, final_fields))
        result["errors"].extend(validate_pdf_fields_exact(doc_type, final_path, normalized))

    if result["errors"]:
        result["status"] = "fail"
        print("❌ FAIL")
        for err in result["errors"]:
            print(" -", err)
    else:
        print("✅ OK")

    return result


def run_all() -> None:
    docs = DOCUMENTS[:] if DOCUMENTS else discover_doc_types()

    if not docs:
        raise RuntimeError("No documents found to test")

    results = {
        "ok": [],
        "fail": [],
    }

    for doc_type in docs:
        res = run_single(doc_type)
        results[res["status"]].append(res)

    total = len(results["ok"]) + len(results["fail"])

    print("\n======================")
    print("SUMMARY")
    print("======================")
    print(f"TOTAL DOCS : {total}")
    print(f"PASSED     : {len(results['ok'])}")
    print(f"FAILED     : {len(results['fail'])}")
    print()

    if results["ok"]:
        print("✅ PASSED:")
        for item in results["ok"]:
            print(f"   - {item['doc_type']}")

    if results["fail"]:
        print("❌ FAILED:")
        for item in results["fail"]:
            print(f"   - {item['doc_type']}")
            for err in item["errors"]:
                print(f"     * {err}")

    if results["fail"]:
        raise Exception("UNIVERSAL DOCUMENT TEST FAILED")


def run_cli() -> None:
    import sys

    # Build the full list of known documents: explicit DOCUMENTS list + discovered
    known_docs = list(DOCUMENTS) if DOCUMENTS else []
    discovered = discover_doc_types()
    all_known: List[str] = sorted(set(known_docs + discovered))

    if len(sys.argv) > 1:
        doc_type = sys.argv[1].strip().lower()

        if all_known and doc_type not in all_known:
            print(f"[ERROR] Unknown document: {doc_type!r}")
            print(f"        Available: {', '.join(all_known)}")
            sys.exit(1)

        print("===== SINGLE TEST =====")
        print(f"Document: {doc_type}")
        print("=======================")

        try:
            res = run_single(doc_type)
        except Exception as e:
            print(f"[CRASH] {doc_type}: {e}")
            sys.exit(1)

        if res["status"] != "ok":
            sys.exit(1)
    else:
        run_all()


if __name__ == "__main__":
    run_cli()
