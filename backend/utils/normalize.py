# -*- coding: utf-8 -*-
"""
backend/utils/normalize.py — Idempotent value-level normalization for user_data.

Called BEFORE validation and PDF generation. Normalizes:
  - dates       → DD.MM.YYYY
  - PLZ         → 5-digit string
  - IBAN        → uppercase, no spaces / dashes
  - phone       → digits only (+ prefix preserved)
  - names       → trim + collapse internal spaces
  - street/addr → trim + collapse internal spaces

Keys are preserved as-is. Idempotent: calling twice returns the same result.
"""
import re
from typing import Any, Dict

# ── Field buckets ──────────────────────────────────────────────────────────────

_DATE_FIELDS = frozenset({
    "birth_date", "date_of_birth", "birthdate", "geburtsdatum", "dob",
    "move_in_date", "move_out_date", "einzugsdatum", "auszugsdatum",
    "issue_date", "ausstellungsdatum", "gueltig_bis", "valid_until",
    "datum", "date", "child_birth_date", "kind_geburtsdatum",
    "ankunftsdatum", "einreisedatum",
})
_DATE_SUFFIXES = ("_date", "_datum", "_bis", "_von", "_seit", "_ab", "_ende")

# Fields that end in a date suffix but contain city+date combos — must NOT be
# passed through _normalize_date (which expects a bare date string).
_SKIP_DATE_NORMALIZATION = frozenset({
    "eheschliessung_ort_datum",  # "Berlin, 12.05.2020" — city + date in one field
})

_PLZ_FIELDS = frozenset({
    "plz", "postal_code", "postleitzahl", "zip", "new_plz", "neue_plz",
})

_IBAN_FIELDS = frozenset({"iban", "bankverbindung"})

_PHONE_FIELDS = frozenset({
    "phone", "phone_number", "telefon", "telephone", "mobil", "handy", "telefonnummer",
})
_PHONE_SUFFIXES = ("_phone", "_telefon", "_mobil")

_NAME_FIELDS = frozenset({
    "first_name", "last_name", "name", "vorname", "nachname",
    "birth_name", "geburtsname", "middle_name",
    "landlord_name", "employer_name", "vermieter_name", "arbeitgeber_name",
    "company_name", "firma", "child_name", "child_first_name",
    "kind_name", "kind_vorname",
})
_NAME_SUFFIXES = ("_name",)

_STREET_FIELDS = frozenset({
    "street", "strasse", "street_name", "strassenname",
    "new_street", "neue_strasse",
    "landlord_address", "address", "adresse",
})
_STREET_SUFFIXES = ("_street", "_strasse", "_address", "_adresse")

_BIRTH_PLACE_FIELDS = frozenset({
    "birth_place", "geburtsort", "birthplace",
    "person2_birth_place", "person3_birth_place", "person4_birth_place", "person5_birth_place",
    "child_birth_place", "kind_geburtsort",
})

_BIRTH_COUNTRY_FIELDS = frozenset({
    "birth_country", "geburtsland",
})

# ---------------------------------------------------------------------------
# COUNTRY_MAP — public constant (importable by other modules for reference).
# Maps free-text country input (any script / language / abbreviation) to the
# canonical country name used in German official documents.
# Keys are lowercase; the normalizer applies .lower().strip() before lookup.
# ---------------------------------------------------------------------------
COUNTRY_MAP: Dict[str, str] = {
    # Ukrainian variants
    "ukraine":          "Ukraine",
    "ukraina":          "Ukraine",
    "ukrayna":          "Ukraine",
    "україна":          "Ukraine",
    "украина":          "Ukraine",
    "ua":               "Ukraine",
    "ukr":              "Ukraine",
    # German variants
    "germany":          "Deutschland",
    "deutschland":      "Deutschland",
    "allemagne":        "Deutschland",
    "german":           "Deutschland",
    "de":               "Deutschland",
    # Poland
    "poland":           "Polen",
    "polska":           "Polen",
    "польща":           "Polen",
    "польша":           "Polen",
    "pl":               "Polen",
    # Russia
    "russia":           "Russland",
    "russland":         "Russland",
    "росія":            "Russland",
    "россия":           "Russland",
    "ru":               "Russland",
    # Turkey
    "turkey":           "Türkei",
    "türkei":           "Türkei",
    "turkei":           "Türkei",
    "türkiye":          "Türkei",
    "turkiye":          "Türkei",
    "tr":               "Türkei",
    # Belarus
    "belarus":          "Belarus",
    "weissrussland":    "Belarus",
    "weißrussland":     "Belarus",
    "беларусь":         "Belarus",
    "by":               "Belarus",
    # Syria
    "syria":            "Syrien",
    "syrien":           "Syrien",
    "سوريا":            "Syrien",
    # Afghanistan
    "afghanistan":      "Afghanistan",
    # Iraq
    "iraq":             "Irak",
    "irak":             "Irak",
    "العراق":           "Irak",
    # Iran
    "iran":             "Iran",
    # Georgia
    "georgia":          "Georgien",
    "georgien":         "Georgien",
    "საქართველო":       "Georgien",
    "ge":               "Georgien",
    # Moldova
    "moldova":          "Moldau",
    "moldau":           "Moldau",
    "молдова":          "Moldau",
    # Azerbaijan
    "azerbaijan":       "Aserbaidschan",
    "aserbaidschan":    "Aserbaidschan",
    "az":               "Aserbaidschan",
    # Kazakhstan
    "kazakhstan":       "Kasachstan",
    "kasachstan":       "Kasachstan",
    "kz":               "Kasachstan",
    # Uzbekistan
    "uzbekistan":       "Usbekistan",
    "usbekistan":       "Usbekistan",
    # Romania
    "romania":          "Rumänien",
    "rumänien":         "Rumänien",
    "rumaenien":        "Rumänien",
    "ro":               "Rumänien",
    # Bulgaria
    "bulgaria":         "Bulgarien",
    "bulgarien":        "Bulgarien",
    "bg":               "Bulgarien",
    # Vietnam
    "vietnam":          "Vietnam",
    "vn":               "Vietnam",
    # China
    "china":            "China",
    "vr china":         "China",
    "cn":               "China",
    # Egypt
    "egypt":            "Ägypten",
    "ägypten":          "Ägypten",
    "aegypten":         "Ägypten",
    "مصر":              "Ägypten",
    # Serbia
    "serbia":           "Serbien",
    "serbien":          "Serbien",
    # North Macedonia
    "north macedonia":  "Nordmazedonien",
    "nordmazedonien":   "Nordmazedonien",
    # Kosovo
    "kosovo":           "Kosovo",
    # Croatia
    "croatia":          "Kroatien",
    "kroatien":         "Kroatien",
    "hr":               "Kroatien",
    # Bosnia
    "bosnia":                   "Bosnien und Herzegowina",
    "bosnien":                  "Bosnien und Herzegowina",
    "bosnien und herzegowina":  "Bosnien und Herzegowina",
    "ba":                       "Bosnien und Herzegowina",
    # Albania
    "albania":          "Albanien",
    "albanien":         "Albanien",
    "al":               "Albanien",
}


def _normalize_country(v: str) -> str:
    """Map raw country input to standard canonical form.

    Lookup is case-insensitive. Falls back to `.title()` so at minimum the
    country name is capitalized correctly even if not in the map.

    Examples:
        "ukraine"    → "Ukraine"
        "GERMANY"    → "Deutschland"
        "deutschland"→ "Deutschland"
        "Polska"     → "Polen"
        "XYZ"        → "Xyz"   (unknown, fallback to title)
    """
    key = v.strip().lower()
    mapped = COUNTRY_MAP.get(key)
    if mapped:
        return mapped
    return v.strip().title()


# ── Normalizer functions ───────────────────────────────────────────────────────

def _normalize_date(v: str) -> str:
    """Normalize date to DD.MM.YYYY. Returns original string if not recognized."""
    v = v.strip()
    # DD.MM.YYYY (possibly single-digit)
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', v)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{m.group(3)}"
    # ISO YYYY-MM-DD
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', v)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    # DD/MM/YYYY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', v)
    if m:
        return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{m.group(3)}"
    # YYYY/MM/DD
    m = re.match(r'^(\d{4})/(\d{2})/(\d{2})$', v)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    # DDMMYYYY — 8 consecutive digits, no separators (e.g. 09082024 → 09.08.2024)
    m = re.match(r'^(\d{2})(\d{2})(\d{4})$', v)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return v


def _normalize_plz(v: str) -> str:
    """Strip non-digits; return 5-digit PLZ or the original trimmed string."""
    digits = re.sub(r'\D', '', v.strip())
    return digits if len(digits) == 5 else v.strip()


def _normalize_iban(v: str) -> str:
    """Remove spaces/dashes and uppercase."""
    return re.sub(r'[\s\-]', '', v.strip()).upper()


def _normalize_phone(v: str) -> str:
    """Normalize phone to digit-only German format.

    Rules (applied in order):
    1. Strip whitespace and common separators (spaces, dashes, parentheses).
    2. Remove leading '+' (international prefix marker).
    3. Strip all remaining non-digit characters.
    4. If the result starts with '0' (German local format like 030…), replace
       the leading '0' with '49' to produce a valid international format.

    Examples:
        '+49 30 12345678'  → '4930 12345678' → '493012345678'
        '0 30/123-456'     → '030123456'     → '4930123456'
        '4930 1234567'     → '4930 1234567'  → '49301234567'
        '+493012345678'    → '493012345678'
    """
    v = v.strip()
    # Remove leading + (international prefix)
    if v.startswith('+'):
        v = v[1:]
    # Strip all non-digit characters (spaces, dashes, slashes, parentheses)
    v = re.sub(r'[^\d]', '', v)
    # Convert German local format (0xx…) → international (49xx…)
    if v.startswith('0'):
        v = '49' + v[1:]
    return v


def _normalize_turkish_chars(v: str) -> str:
    """Replace Turkish-specific characters that AcroForm PDF fields cannot render.

    Turkish dotted/dotless I variants and other chars that break Latin-only PDF fields:
      İ (U+0130) → I   (Turkish capital I with dot above)
      ı (U+0131) → i   (Turkish small dotless i)
      Ğ / ğ     → G/g  (soft g)
      Ş / ş     → S/s  (s with cedilla)
      Ç / ç     → C/c  (c with cedilla) — already handled by most fonts, but normalize anyway
      Ö / ö     → Oe/oe — NOT replaced (Ö is valid in German PDF fields)
      Ü / ü     → NOT replaced (valid German umlauts)

    Only the chars that cause rendering failures in standard AcroForm fields are replaced.
    German umlauts (ä/ö/ü/ß) are kept as-is — German PDF templates expect them.
    """
    _TR_MAP = str.maketrans({
        "\u0130": "I",   # İ → I
        "\u0131": "i",   # ı → i
        "\u011e": "G",   # Ğ → G
        "\u011f": "g",   # ğ → g
        "\u015e": "S",   # Ş → S
        "\u015f": "s",   # ş → s
    })
    return v.translate(_TR_MAP)


# Fields where non-Latin scripts (Arabic, Hebrew, Cyrillic, CJK) must be stripped
# because German AcroForm PDF templates use Latin-only fonts and cannot render them.
# "note", "comment", "anmerkung" are excluded — free-text fields may accept anything.
_LATIN_ONLY_PDF_FIELDS = frozenset({
    "nationality", "person2_nationality", "child_nationality",
    "birth_place", "birth_country", "geburtsort", "geburtsland",
    "city", "street", "landlord_name", "landlord_city",
    "first_name", "last_name", "birth_name", "person2_first_name",
    "person2_last_name", "person2_birth_place", "person2_birth_country",
    "signature_place", "ausstellungsbehoerde",
})

# Arabic Unicode block: U+0600–U+06FF (covers Arabic script letters, diacritics, digits)
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+")

# Minimal Arabic → Latin transliteration map for common country/nationality terms.
# Purpose: preserve meaning when user enters Arabic text in a Latin-only PDF field.
_ARABIC_TRANSLITERATE: Dict[str, str] = {
    "أوكرانيا":   "Ukraine",
    "أوكراني":    "ukrainisch",
    "أوكرانية":   "ukrainisch",
    "ألمانيا":    "Deutschland",
    "ألماني":     "deutsch",
    "ألمانية":    "deutsch",
    "بولندا":     "Polen",
    "بولندي":     "polnisch",
    "تركيا":      "Türkei",
    "تركي":       "türkisch",
    "روسيا":      "Russland",
    "روسي":       "russisch",
    "بيلاروسيا":  "Belarus",
    "مصر":        "Ägypten",
    "سوريا":      "Syrien",
    "العراق":     "Irak",
    "برلين":      "Berlin",
    "هامبورغ":    "Hamburg",
    "ميونخ":      "München",
}


def _sanitize_arabic_for_pdf(v: str) -> str:
    """Remove or transliterate Arabic script from a value destined for a Latin-only PDF field.

    Strategy:
    1. If the entire value matches a known Arabic term → return the German/Latin equivalent.
    2. Otherwise strip Arabic characters and collapse whitespace.
       This prevents broken glyph sequences in AcroForm fields whose embedded font
       does not include Arabic shaping tables.
    """
    v_stripped = v.strip()
    # Full-value lookup first (most common case: user types just the country/nationality)
    exact = _ARABIC_TRANSLITERATE.get(v_stripped)
    if exact:
        return exact
    # Partial: replace Arabic substrings with their transliteration where known, else remove
    def _replace_arabic(m: re.Match) -> str:
        return _ARABIC_TRANSLITERATE.get(m.group(0), "")
    result = _ARABIC_RE.sub(_replace_arabic, v_stripped)
    return " ".join(result.split())  # collapse extra spaces


def _normalize_name(v: str) -> str:
    """Trim, collapse internal whitespace, and capitalize each word.

    Handles compound names with hyphens (e.g. "anna-maria" → "Anna-Maria")
    and multi-word names ("van den berg" → "Van Den Berg").

    Examples:
        "ivan"          → "Ivan"
        "petrenko"      → "Petrenko"
        "anna-maria"    → "Anna-Maria"
        "  JOHN  doe "  → "John Doe"
    """
    # Collapse whitespace first
    v = ' '.join(v.split())
    # Capitalize each hyphen-separated segment independently
    parts = v.split('-')
    return '-'.join(seg.title() for seg in parts)


def _normalize_street(v: str) -> str:
    """Trim, collapse spaces, capitalize each word, replace strasse/strase suffix → 'straße'."""
    import re as _re
    v = ' '.join(v.split())
    # Capitalize first letter of each word
    v = v.title()
    # Replace ...strasse / ...strase (single-s typo) → ...straße (case-insensitive).
    # Order matters: longer pattern first so "strasse" is caught before "strase".
    v = _re.sub(r'(?i)strasse\b', 'straße', v)
    v = _re.sub(r'(?i)strase\b',  'straße', v)
    return v


_AUTHORITY_TYPOS = {
    # common OCR/user typos for German authority names
    r'(?i)\bsytandesamt\b':      'Standesamt',
    r'(?i)\bstandessamt\b':      'Standesamt',
    r'(?i)\bstandessammt\b':     'Standesamt',
    r'(?i)\bbuergeramt\b':       'Bürgeramt',
    r'(?i)\bbürgeramt\b':        'Bürgeramt',
    r'(?i)\bauslenderbehörde\b': 'Ausländerbehörde',
    r'(?i)\bauslanderbehörde\b': 'Ausländerbehörde',
    r'(?i)\bausländerbehorde\b': 'Ausländerbehörde',
    r'(?i)\bauslanderbehorde\b': 'Ausländerbehörde',
}

_NATIONALITY_MAP: Dict[str, str] = {
    # Ukrainian variants
    "ua":               "ukrainisch",
    "україна":          "ukrainisch",
    "украина":          "ukrainisch",
    "ukraine":          "ukrainisch",
    "ukraina":          "ukrainisch",
    "ukrainian":        "ukrainisch",
    "ukrainerin":       "ukrainisch",
    "ukrain":           "ukrainisch",
    "ukranian":         "ukrainisch",
    # Russian variants
    "россия":           "russisch",
    "россiя":           "russisch",
    "russia":           "russisch",
    "russian":          "russisch",
    "russland":         "russisch",
    # German
    "deutschland":      "deutsch",
    "german":           "deutsch",
    "germany":          "deutsch",
    "germany (de)":     "deutsch",
    # Polish
    "polska":           "polnisch",
    "poland":           "polnisch",
    "polish":           "polnisch",
    "polnisch":         "polnisch",
    # Turkish
    "türkiye":          "türkisch",
    "turkiye":          "türkisch",
    "turkey":           "türkisch",
    "turkish":          "türkisch",
    # Syrian
    "سوريا":            "syrisch",
    "syria":            "syrisch",
    "syrian":           "syrisch",
    # Afghan
    "afghanistan":      "afghanisch",
    "afghan":           "afghanisch",
    # Romanian
    "românia":          "rumänisch",
    "romania":          "rumänisch",
    "romanian":         "rumänisch",
    # Bulgarian
    "българия":         "bulgarisch",
    "bulgaria":         "bulgarisch",
    "bulgarian":        "bulgarisch",
    # Serbian
    "srbija":           "serbisch",
    "serbia":           "serbisch",
    "serbian":          "serbisch",
    # Croatian
    "hrvatska":         "kroatisch",
    "croatia":          "kroatisch",
    "croatian":         "kroatisch",
    # Vietnamese
    "việt nam":         "vietnamesisch",
    "vietnam":          "vietnamesisch",
    "vietnamese":       "vietnamesisch",
    # Chinese
    "中国":             "chinesisch",
    "china":            "chinesisch",
    "chinese":          "chinesisch",
    # Iraqi
    "العراق":           "irakisch",
    "iraq":             "irakisch",
    "iraqi":            "irakisch",
    # Iranian
    "ايران":            "iranisch",
    "iran":             "iranisch",
    "iranian":          "iranisch",
}

_NATIONALITY_FIELDS = frozenset({
    "nationality", "staatsangehoerigkeiten", "staatsangehörigkeit",
    "staatsangehoerigkei", "staatsangehoerigkeit",   # single-person alias
    "citizenship", "staatsbuergerschaft",            # English / alternate aliases
    "person2_nationality",
    "child_nationality",                             # Kindergeld / Familienkasse child field
})


def _normalize_nationality(v: str) -> str:
    """Map common country names / adjectives in any language to German adjectival form."""
    key = v.strip().lower()
    return _NATIONALITY_MAP.get(key, v)


def _normalize_authority(v: str) -> str:
    """Trim, collapse spaces, fix common typos in German authority names."""
    v = ' '.join(v.split())
    for pattern, replacement in _AUTHORITY_TYPOS.items():
        v = re.sub(pattern, replacement, v)
    return v


# Country typo / misspelling map — shared by _normalize_birth_place and
# normalize_buergergeld_data to keep corrections consistent.
# Each entry: (lowercase_substring, canonical_spelling)
_COUNTRY_TYPO_MAP: list = [
    ("ukrain",   "Ukraine"),
    ("ukraina",  "Ukraine"),
    ("deutschl", "Deutschland"),
    ("russland", "Russland"),
    ("russlan",  "Russland"),
    ("weissruss","Weißrussland"),
    ("weißruss", "Weißrussland"),
    ("belarus",  "Belarus"),
    ("moldau",   "Moldova"),
    ("moldov",   "Moldova"),
    ("georgien", "Georgien"),
    ("armenien", "Armenien"),
    ("aserbaid", "Aserbaidschan"),
    ("kasachst", "Kasachstan"),
    ("uzbekist", "Usbekistan"),
    ("kirgisi",  "Kirgisistan"),
    ("tadschik", "Tadschikistan"),
    ("turkmen",  "Turkmenistan"),
]


def _normalize_country_token(token: str) -> str:
    """Apply _COUNTRY_TYPO_MAP to a single country token.

    Returns the canonical spelling if a known substring matches,
    otherwise returns the token title-cased.
    """
    tok_low = token.strip().lower()
    for sub, canon in _COUNTRY_TYPO_MAP:
        if sub in tok_low:
            return canon
    return token.strip().title()


def _normalize_city_token(city: str) -> str:
    """Apply form_builder._CITY_CORRECTIONS to a city token inside birth_place.

    Imported lazily to avoid circular imports (form_builder imports from normalize).
    Falls back to title-case if the import or lookup fails.
    """
    try:
        from backend.form_builder import _normalize_city_name as _fb_city
        return _fb_city(city)
    except Exception:
        return city.strip().title()


def _normalize_birth_place(v: str) -> str:
    """Ensure 'City, Country' format: insert a comma + title-case each part.

    Also normalises the country token through _COUNTRY_TYPO_MAP so that
    variants like "Ukraina", "Ukrane", "ukraine" all become "Ukraine".
    City token is additionally corrected through _CITY_CORRECTIONS in form_builder
    so that transliteration variants like "Vinnitsia" → "Vinnytsia" are fixed here.

    Rules:
    1. Collapse extra spaces.
    2. If already has a comma → normalize city (CITY_CORRECTIONS + title), normalize country.
    3. Single token → normalize city, done.
    4. Two or more tokens → last token = country candidate, rest = city.
       Always insert comma regardless of capitalisation (covers lowercase input).

    Examples:
        'Vinnytsia Ukraine'           → 'Vinnytsia, Ukraine'
        'Vinnytsia Ukraina'           → 'Vinnytsia, Ukraine'
        'vinnitsia ukraine'           → 'Vinnytsia, Ukraine'   ← FIXED (was Vinnitsia)
        'Vinnitsia, Ukraine'          → 'Vinnytsia, Ukraine'   ← FIXED
        'Vinnytsia, ukraine'          → 'Vinnytsia, Ukraine'
        'Vinnytsia, Ukraine'          → 'Vinnytsia, Ukraine'   (unchanged)
        'Frankfurt am Main Deutschland' → 'Frankfurt Am Main, Deutschland'
        'Berlin'                      → 'Berlin'
        'kyiv'                        → 'Kyiv'
    """
    v = ' '.join(v.split())
    if not v:
        return v
    if ',' in v:
        # Already has comma — clean up both sides
        parts = v.split(',', 1)
        city_part = _normalize_city_token(parts[0])
        country_part = _normalize_country_token(parts[1])
        if country_part:
            return f"{city_part}, {country_part}"
        return city_part
    tokens = v.split(' ')
    if len(tokens) == 1:
        return _normalize_city_token(tokens[0])
    country = _normalize_country_token(tokens[-1])
    city = _normalize_city_token(' '.join(tokens[:-1]))
    return f"{city}, {country}"


def _key_matches(k: str, exact_set: frozenset, suffixes: tuple = ()) -> bool:
    if k in exact_set:
        return True
    for suf in suffixes:
        if k.endswith(suf):
            return True
    return False


# ── camelCase → snake_case key map (WebApp form fields) ───────────────────────
# Mirrors the map that was previously only in pdf_generator._normalize_user_data.

_CAMEL_TO_SNAKE: Dict[str, str] = {
    "firstName":      "first_name",
    "lastName":       "last_name",
    "birthDate":      "birth_date",
    "dateOfBirth":    "date_of_birth",
    "postalCode":     "postal_code",
    "zip":            "plz",
    "houseNo":        "house_number",
    "houseNumber":    "house_number",
    "streetName":     "street",
    "phoneNumber":    "phone_number",
    "moveInDate":     "move_in_date",
    "moveOutDate":    "move_out_date",
    "taxId":          "tax_id",
    # Additional WebApp camelCase keys not previously covered
    "childFirstName": "child_first_name",
    "childLastName":  "child_last_name",
    "childBirthDate": "child_birth_date",
    "childName":      "child_name",
    "birthPlace":     "birth_place",
    "birthName":      "birth_name",
    "bankName":       "bank_name",
    "landlordName":   "landlord_name",
    "employerName":   "employer_name",
    "monthlyIncome":  "monthly_income",
    "emailAddress":   "email",
    "cityName":       "city",
    "incomeSource":   "income_source",
    "household":      "household_members",
}


# ── Public API ─────────────────────────────────────────────────────────────────

def normalize_user_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a new dict with all string values normalized.
    Keys are mapped from camelCase to snake_case where applicable.
    Idempotent: calling twice returns the same result.
    """
    if not user_data:
        return {}

    # Unwrap nested user_answers if present
    if isinstance(user_data.get("user_answers"), dict):
        user_data = user_data["user_answers"]

    result: Dict[str, Any] = {}
    for key, raw in user_data.items():
        canonical_key = _CAMEL_TO_SNAKE.get(key, key)
        k_low = canonical_key.lower().replace("-", "_")
        v = raw
        if isinstance(v, str) and v.strip():
            v = v.strip()
            # Normalize Turkish-specific chars that AcroForm PDFs cannot render
            v = _normalize_turkish_chars(v)
            # Strip / transliterate Arabic script for fields that go into Latin-only PDF AcroForms.
            # German PDF templates (Anmeldung, Kindergeld, etc.) use fonts without Arabic shaping —
            # Arabic text renders as disconnected broken glyphs. Transliterate known terms;
            # silently drop unrecognized Arabic characters rather than corrupt the PDF field.
            if k_low in _LATIN_ONLY_PDF_FIELDS and _ARABIC_RE.search(v):
                v = _sanitize_arabic_for_pdf(v)
            if k_low in _SKIP_DATE_NORMALIZATION:
                pass  # city+date combo — leave for normalize_anmeldung_data to handle
            elif _key_matches(k_low, _DATE_FIELDS, _DATE_SUFFIXES):
                v = _normalize_date(v)
            elif _key_matches(k_low, _PLZ_FIELDS):
                v = _normalize_plz(v)
            elif _key_matches(k_low, _IBAN_FIELDS):
                v = _normalize_iban(v)
            elif _key_matches(k_low, _PHONE_FIELDS, _PHONE_SUFFIXES):
                v = _normalize_phone(v)
            elif _key_matches(k_low, _NAME_FIELDS, _NAME_SUFFIXES):
                v = _normalize_name(v)
            elif _key_matches(k_low, _BIRTH_PLACE_FIELDS):
                v = _normalize_birth_place(v)
            elif k_low in _BIRTH_COUNTRY_FIELDS:
                v = _normalize_country(v)
            elif _key_matches(k_low, _STREET_FIELDS, _STREET_SUFFIXES):
                v = _normalize_street(v)
            elif k_low in ("ausstellungsbehoerde", "authority", "behoerde"):
                v = _normalize_authority(v)
            elif k_low in _NATIONALITY_FIELDS:
                v = _normalize_nationality(v)
            elif k_low == "gender":
                # Expand short codes to full German gender string expected by AcroForm text fields.
                # Radio-button documents (Bürgergeld) use "m"/"w"/"d" directly via checkbox handlers;
                # text-field documents (Kindergeld, Anmeldung) need the full German label.
                _g = v.lower()
                if _g in ("m", "male", "männlich", "maennlich"):
                    v = "männlich"
                elif _g in ("w", "f", "female", "weiblich"):
                    v = "weiblich"
                elif _g in ("d", "divers", "diverse"):
                    v = "divers"
        result[canonical_key] = v

    # Alias: person1_gender → gender before applying fallback default.
    if not str(result.get("gender", "")).strip():
        _p1g = str(result.get("person1_gender", "")).strip()
        if _p1g:
            _g = _p1g.lower()
            if _g in ("m", "male", "männlich", "maennlich"):
                result["gender"] = "männlich"
            elif _g in ("w", "f", "female", "weiblich"):
                result["gender"] = "weiblich"
            elif _g in ("d", "divers", "diverse"):
                result["gender"] = "divers"
            else:
                result["gender"] = _p1g
    # gender fallback — if not provided at all, default to "männlich" (safe neutral default
    # for German official forms; user can always correct before submission).
    if not str(result.get("gender", "")).strip():
        result["gender"] = "männlich"

    # apartment_number — strip "Whg.", "Wohnung", "Apt." prefixes globally.
    # normalize_anmeldung_data does this too, but applying here ensures ALL doc
    # types get clean apartment numbers before reaching any PDF builder.
    _apt = str(result.get("apartment_number", "")).strip()
    if _apt:
        import re as _re_apt
        _apt_clean = _re_apt.sub(r"(?i)^(whg\.?\s*|wohnung\s*|apt\.?\s*|wohng\.?\s*)", "", _apt).strip()
        if _apt_clean != _apt:
            result["apartment_number"] = _apt_clean

    # nationality post-loop guarantee — re-apply _normalize_nationality() so that
    # any value which slipped through (e.g. set by apply_anmeldung_completion or
    # other callers before normalize_user_data) is always converted to adjective form.
    # This is the single authoritative enforcement point; no later code should revert it
    # for AcroForm documents (builder docs handle their own display via _get_display_value).
    for _nat_key in _NATIONALITY_FIELDS:
        _nat_raw = str(result.get(_nat_key, "")).strip()
        if _nat_raw:
            _nat_normalized = _normalize_nationality(_nat_raw)
            result[_nat_key] = _nat_normalized

    # Strict assertion: country names must NOT appear in nationality fields after normalization.
    # If they do, it means _NATIONALITY_MAP is missing an entry — fail loudly so it is fixed.
    _COUNTRY_NAMES_FORBIDDEN = frozenset({
        "ukraine", "poland", "germany", "turkey", "russia", "syria", "iran",
        "iraq", "afghanistan", "china", "vietnam", "romania", "bulgaria",
        "deutschland", "polska", "türkei", "türkiye",
    })
    import logging as _log_assert
    _assert_log = _log_assert.getLogger(__name__)
    for _nat_key in _NATIONALITY_FIELDS:
        _nat_final = str(result.get(_nat_key, "")).strip().lower()
        if _nat_final in _COUNTRY_NAMES_FORBIDDEN:
            _assert_log.error(
                "NORMALIZE_ASSERT_FAIL: nationality field '%s' still contains country name '%s' "
                "after normalization — add entry to _NATIONALITY_MAP",
                _nat_key, result.get(_nat_key),
            )

    # Synthesize child_name from child_first_name + child_last_name if not already set.
    # This ensures validator's child_name alias check passes when WebApp sends split fields.
    if "child_name" not in result or not str(result["child_name"]).strip():
        fn = str(result.get("child_first_name", "")).strip()
        ln = str(result.get("child_last_name", "")).strip()
        if fn or ln:
            result["child_name"] = " ".join(p for p in [fn, ln] if p)

    # Auto-split street + house_number when user typed them combined.
    # Rules:
    #   - Only fires when house_number is absent/empty.
    #   - Matches the trailing house-number token: digits optionally followed by
    #     a letter suffix (12a, 5b) OR a range (120-122) OR a slash variant (5/2).
    #   - Street name part must be non-empty (≥1 char before the number).
    #   - Does NOT fire if the street itself has no trailing number pattern
    #     (e.g. pure street names like "Am Bahnhof" without a number stay as-is).
    # Examples that split:
    #   "Musterstraße 12"     → street="Musterstraße",  house_number="12"
    #   "Musterstraße 12a"    → street="Musterstraße",  house_number="12a"
    #   "Frankfurter Allee 120-122" → street="Frankfurter Allee", house_number="120-122"
    #   "Hauptstraße 5/2"     → street="Hauptstraße",   house_number="5/2"
    #   "Am Bahnhof 7"        → street="Am Bahnhof",    house_number="7"
    # Examples that do NOT split (no trailing number):
    #   "Am Bahnhof"          → unchanged
    #   "Musterstraße"        → unchanged
    _st = str(result.get("street", "")).strip()
    _hn = str(result.get("house_number", "")).strip()
    if _st and not _hn:
        _m = re.match(r'^(.+?)\s+(\d+(?:[a-zA-Z]|[-/]\d+)?)$', _st)
        if _m:
            result["street"] = _normalize_street(_m.group(1).strip())
            # Lowercase the letter suffix so "12A" → "12a" (German standard)
            _raw_hn = _m.group(2).strip()
            result["house_number"] = re.sub(r'(\d+)([A-Z])$', lambda x: x.group(1) + x.group(2).lower(), _raw_hn)

    # ── Assemble household_members list from flat member_* fields (Wohngeld/Bürgergeld) ──
    # The WebApp form stores individual member data as flat keys (member_name,
    # member_birth_date, etc.) but the PDF builder and validator expect a list of
    # member dicts under the key "household_members".  Build it here so every
    # downstream consumer (validate.py, document_config.py) gets a consistent value.
    if not result.get("household_members"):
        _has_hm = str(result.get("has_household_members", "")).strip().lower()
        if _has_hm in ("ja", "yes", "true", "1"):
            _member: Dict[str, Any] = {}
            for _flat_key, _dict_key in (
                ("member_name",          "name"),
                ("member_birth_date",    "birth_date"),
                ("member_birth_place",   "birth_place"),
                ("member_relation",      "relation"),
                ("member_gender",        "gender"),
                ("member_nationality",   "nationality"),
                ("member_family_status", "family_status"),
                ("member_occupation",    "occupation"),
            ):
                _val = str(result.get(_flat_key, "")).strip()
                if _val:
                    _member[_dict_key] = _val
            result["household_members"] = [_member] if _member else []
        else:
            # User lives alone — set to empty list so validation passes and the
            # PDF builder renders no member rows (applicant is always row 0).
            result["household_members"] = []

    return result


# ── Anmeldung-specific post-normalization ──────────────────────────────────────

def normalize_anmeldung_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply Anmeldung-specific business rules on top of the generic normalization.
    Must be called AFTER normalize_user_data().

    Rules:
    1. weitere_wohnungen auto-set to "Nein" when wohnungstyp == "alleinige Wohnung"
    2. apartment_number appended to street line: "Straße HNr, Whg. N"
       The raw apartment_number key is kept for reference but the combined field
       is written to street_with_apt for the PDF builder to consume.
    3. signature_place auto-filled from city when empty.
    4. gemeindekennzahl empty → kept empty (no warning injection here).
    5. Date fields already normalized by normalize_user_data(); marriage date
       (eheschliessung_ort_datum) is date-formatted where possible.
    """
    data = dict(user_data)

    # Alias: person1_gender → gender; treat "" the same as missing
    _g_val = str(data.get("gender", "")).strip()
    if not _g_val:
        data["gender"] = data.get("person1_gender")

    # 1. weitere_wohnungen logic
    wohnungstyp = (data.get("wohnungstyp") or "").strip().lower()
    if wohnungstyp in ("alleinige wohnung", "alleinige"):
        data["weitere_wohnungen"] = "Nein"
    elif not (data.get("weitere_wohnungen") or "").strip():
        data["weitere_wohnungen"] = "Nein"

    # 2. Compose address line with apartment number
    street = (data.get("street") or "").strip()
    house_no = (data.get("house_number") or "").strip()
    apt = (data.get("apartment_number") or "").strip()
    # Strip "Whg." / "Wohnung" prefix if user entered it (e.g. "Whg. 12" → "12")
    if apt:
        import re as _re
        apt = _re.sub(r"(?i)^(whg\.?\s*|wohnung\s*)", "", apt).strip()
        data["apartment_number"] = apt
    if street and house_no and apt:
        data["street_display"] = f"{street} {house_no}, Whg. {apt}"
    elif street and house_no:
        data["street_display"] = f"{street} {house_no}"
    else:
        data["street_display"] = street

    # 3. signature_place: auto-fill from city if empty
    if not (data.get("signature_place") or "").strip():
        city = (data.get("city") or "").strip()
        if city:
            data["signature_place"] = city

    # 5. Religion default: Bürgeramt expects a value; "ohne" avoids rejection
    if not (data.get("religion") or "").strip():
        data["religion"] = "ohne"

    # 6. signature_date fallback — if user left it empty, use today (same as Bürgergeld)
    from datetime import date as _date
    if not (data.get("signature_date") or "").strip():
        data["signature_date"] = _date.today().strftime("%d.%m.%Y")

    # 4. Normalize marriage/civil-status date (eheschliessung_ort_datum may be
    #    a freetext "Berlin, 12.07.1999" — keep as-is; if it's a raw date string
    #    like "1207 1999" or "12071999" try to parse it.
    #    Also insert comma between city and date when missing: "Berlin 12.07.1999"
    _ehd = (data.get("eheschliessung_ort_datum") or "").strip()
    if _ehd:
        import re as _re
        # Strip pipe-separated duplicate suffix: "City, Date | City, Date" → "City, Date"
        _ehd = _re.sub(r"\s*\|.*$", "", _ehd).strip()
        data["eheschliessung_ort_datum"] = _ehd
        # Pattern: 8 consecutive digits DDMMYYYY → DD.MM.YYYY
        _ehd_stripped = _ehd.replace(' ', '').replace('.', '')
        m = _re.match(r'^(\d{2})(\d{2})(\d{4})$', _ehd_stripped)
        if m:
            data["eheschliessung_ort_datum"] = f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
        elif _re.search(r',+\s*\d{2}\.\d{2}\.\d{4}', _ehd):
            # Already contains "City, Date" format — only collapse multiple commas
            # and normalize spacing.  Do NOT add another comma (would cause ",," duplication).
            data["eheschliessung_ort_datum"] = _re.sub(
                r',+\s*(\d{2}\.\d{2}\.\d{4})',
                r', \1',
                _ehd,
            ).strip()
        else:
            # Insert comma if "City DD.MM.YYYY" is missing the comma entirely
            _ehd2 = _re.sub(
                r'^([\w\s\.\-]+?)\s+(\d{2}\.\d{2}\.\d{4})$',
                r'\1, \2',
                _ehd,
            )
            data["eheschliessung_ort_datum"] = _ehd2

    return data


def normalize_buergergeld_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply Bürgergeld/Jobcenter-specific business rules before PDF generation.
    Must be called AFTER normalize_user_data().

    Rules:
    1. All Yes/No radio fields default to "nein" if not provided.
    2. is_erwerbsfaehig defaults to "ja" (legal implication of "nein").
    3. Conditional field clearing: if parent == "nein", clear dependent fields.
    4. SV bidirectional: has_sv_number=nein → clear sv_number;
       sv_number filled → force has_sv_number=ja.
    5. Country typo normalization (e.g. "Ukrainme" → "Ukraine").
    6. IBAN present → no "kein Konto" conflict (handled at PDF-mapping level).
    7. signature_date auto-filled from today if empty.
    """
    import logging as _logging
    from datetime import date as _date

    _log = _logging.getLogger(__name__)
    data = dict(user_data)

    # ── 1. Yes/No defaults (safe = "nein", except is_erwerbsfaehig) ────────────
    _nein_defaults = {
        "has_residence_permit":  "nein",
        "has_sv_number":         "nein",
        "has_betreuer":          "nein",
        "has_verpflichtung":     "nein",
        "had_buergergeld_before":"nein",
        "is_schueler":           "nein",
        "is_asylbewerber":       "nein",
        "has_andere_leistungen": "nein",
        "is_alleinerziehend":    "nein",
        "has_health_insurance":  "ja",    # safer default: insured
        "warmwasser_zentral":    "ja",
        "rent_status":           "ja",
        "living_alone":          "nein",
        "employment_status":     "arbeitslos",
    }
    for key, default in _nein_defaults.items():
        if not (data.get(key) or "").strip():
            data[key] = default

    # is_erwerbsfaehig: default "ja" — "nein" has serious legal consequences
    if not (data.get("is_erwerbsfaehig") or "").strip():
        data["is_erwerbsfaehig"] = "ja"

    # ── 2. Conditional field clearing ───────────────────────────────────────────
    def _is_nein(key: str) -> bool:
        return (data.get(key) or "").strip().lower() in ("nein", "no", "false", "0")

    def _is_ja(key: str) -> bool:
        return (data.get(key) or "").strip().lower() in ("ja", "yes", "true", "1")

    # SV consistency — has_sv_number flag has FULL priority over sv_number value.
    #
    # Rule 1: has_sv_number=nein → always clear sv_number (user explicitly said "no")
    # Rule 2: sv_number filled but has_sv_number is empty/unset → infer "ja"
    #         (but NEVER override an explicit "nein" — that would contradict user choice)
    _sv_num   = (data.get("sv_number") or "").strip()
    _sv_flag  = (data.get("has_sv_number") or "").strip().lower()
    if _is_nein("has_sv_number"):
        # Explicit nein wins — clear any orphan sv_number
        data["sv_number"] = ""
    elif _sv_num and not _sv_flag:
        # sv_number present but flag not set → infer ja
        data["has_sv_number"] = "ja"

    _log.debug("[PDF DEBUG] SV has_sv_number=%s has_sv_number_value=%s",
               data.get("has_sv_number"), bool(data.get("sv_number")))

    # betreuer / verpflichtung: clear if has_sondersituation == nein (gate field)
    # Only override if user did NOT explicitly provide a value for the sub-field.
    if _is_nein("has_sondersituation"):
        if not (user_data.get("has_betreuer") or "").strip():
            data["has_betreuer"] = "nein"
        if not (user_data.get("has_verpflichtung") or "").strip():
            data["has_verpflichtung"] = "nein"

    # receives_benefits + benefit type: clear if has_andere_leistungen == nein
    if _is_nein("has_andere_leistungen"):
        data["receives_benefits"] = ""

    # is_schueler / is_asylbewerber: gate field has full priority
    if _is_nein("has_sonderstatus"):
        data["is_schueler"] = "nein"
        data["is_asylbewerber"] = "nein"

    # entry_date_germany: clear if has_residence_permit == nein
    if _is_nein("has_residence_permit"):
        data["entry_date_germany"] = ""

    # household_type: clear if living_alone == ja
    if _is_ja("living_alone"):
        data["household_type"] = ""

    # employer fields: clear when not employed (prevents orphan data in PDF)
    _emp_status = (data.get("employment_status") or "").strip().lower()
    if _emp_status not in ("angestellt", "beschäftigt", "selbständig", "selbstaendig"):
        for _emp_key in ("employer_name", "employer_street", "employer_house_number",
                         "employer_plz", "employer_city"):
            data[_emp_key] = ""

    _log.debug("[PDF DEBUG] employment_status=%r employer_name=%r",
               data.get("employment_status"), data.get("employer_name"))

    # ── 3. Country / nationality typo normalization ──────────────────────────────
    # Reuse the module-level _COUNTRY_TYPO_MAP (defined above _normalize_birth_place).
    # Fixes fields that contain only a country name ("birth_country", "geburtsland").
    # NOTE: "nationality" is intentionally excluded here — it is already normalized
    # to German adjectival form (e.g. "ukrainisch") by normalize_user_data() via
    # _NATIONALITY_FIELDS + _normalize_nationality(). Applying _COUNTRY_TYPO_MAP here
    # would overwrite "ukrainisch" back to "Ukraine" because "ukrain" is a substring.
    for _field in ("birth_country", "geburtsland"):
        _raw_c = (data.get(_field) or "").strip()
        if not _raw_c:
            continue
        # Skip if already a valid German adjectival form (already processed by normalize_user_data)
        if _raw_c.lower() in _NATIONALITY_MAP:
            continue
        _raw_low = _raw_c.lower()
        for _sub, _canon in _COUNTRY_TYPO_MAP:
            if _sub in _raw_low and _raw_c != _canon:
                _log.debug("[PDF DEBUG] country typo fix: %r → %r (field=%s)", _raw_c, _canon, _field)
                data[_field] = _canon
                break

    # Also fix the country-token embedded inside "birth_place" / "geburtsort"
    # e.g. "Vinnytsia, Ukraina" → "Vinnytsia, Ukraine"
    for _bp_field in ("birth_place", "geburtsort"):
        _bp = (data.get(_bp_field) or "").strip()
        if not _bp:
            continue
        _fixed_bp = _normalize_birth_place(_bp)
        if _fixed_bp != _bp:
            _log.debug("[PDF DEBUG] birth_place typo fix: %r → %r (field=%s)", _bp, _fixed_bp, _bp_field)
            data[_bp_field] = _fixed_bp

    # ── 4. IBAN debug log ────────────────────────────────────────────────────────
    _iban = (data.get("iban") or "").strip()
    _log.debug("[PDF DEBUG] IBAN present=%s → kein_konto=%s", bool(_iban), not bool(_iban))

    # ── 5. signature_date fallback ───────────────────────────────────────────────
    if not (data.get("signature_date") or "").strip():
        data["signature_date"] = _date.today().strftime("%d.%m.%Y")

    return data


# ── Wohngeld-specific post-normalization ──────────────────────────────────────

def normalize_wohngeld_data(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply Wohngeld-specific business rules on top of generic normalize_user_data().
    Must be called AFTER normalize_user_data().

    Rules:
    1. Boolean/YES-NO gate fields default to "nein" if absent or empty.
       Exception: has_income defaults to "ja" (safest — most applicants have income).
    2. Numeric cost/income fields default to "0" when empty so the PDF never
       receives an empty string for a numeric AcroForm text field.
    3. signature_date and signature_place auto-filled when absent.
    4. Assemble household_members from flat member_* keys (idempotent — the
       generic normalize_user_data() already does this, but we repeat the guard
       here so it also fires when normalize_wohngeld_data is called standalone).
    """
    import logging as _logging
    from datetime import date as _date

    _log = _logging.getLogger(__name__)
    data = dict(user_data)

    # ── 1. Boolean gate defaults ─────────────────────────────────────────────
    # All YES/NO fields that drive section visibility must always have a value
    # so that:
    #   a) The PDF AcroForm checkbox/radio is filled correctly.
    #   b) The conditional validation in validate.py works predictably.
    _bool_defaults: Dict[str, str] = {
        # Core control fields
        "has_household_members": "nein",
        "receives_benefits":     "nein",
        "has_assets":            "nein",
        # has_income defaults to "ja" — most applicants have income
        "has_income":            "ja",
        # §1 Erhöhungsantrag reasons
        "wg_reason_person_increase": "nein",
        "wg_reason_income_decrease": "nein",
        "wg_reason_rent_increase":   "nein",
        # §2 Previous Wohngeld
        "wg_had_previous_wohngeld": "nein",
        # §3 Moving / Zweitwohnsitz
        "wg_planning_move":            "nein",
        "wg_has_second_residence":     "nein",
        "wg_main_residence_elsewhere": "nein",
        # §5 Household changes
        "wg_hh_size_changing": "nein",
        # §6 Betreuer
        "wg_has_betreuer": "nein",
        # §7 Absent member
        "wg_has_absent_member": "nein",
        "wg_absent_returning":  "nein",
        # §8 Shared custody in household
        "wg_shared_custody_hh": "nein",
        # §9 Shared custody outside
        "wg_shared_custody_ext": "nein",
        # §10 Member left / new member
        "wg_member_left":             "nein",
        "wg_new_member_expected":     "nein",
        "wg_new_member_moved_in":     "nein",
        "wg_new_member_has_benefits": "nein",
        # §11 Transfer payment timing
        "wg_benefits_last_12m": "nein",
        "wg_benefits_next_12m": "nein",
        # §11 Transfer payment type checkboxes
        "wg_benefit_unterkunft_zuschuss": "nein",
        "wg_benefit_unterkunft_kosten":   "nein",
        "wg_benefit_verletztengeld11":    "nein",
        "wg_benefit_vorschuss":           "nein",
        "wg_benefit_grundsicherung":      "nein",
        "wg_benefit_lebensunterhalt":     "nein",
        "wg_benefit_ergaenzende":         "nein",
        "wg_benefit_jugendhilfe8":        "nein",
        "wg_benefit_asylbewerber":        "nein",
        # §12 Other payments
        "wg_has_other_payments":        "nein",
        "wg_pay_rente":                 "nein",
        "wg_pay_unterhaltsvorschuss12": "nein",
        "wg_pay_kinderzuschlag":        "nein",
        "wg_pay_wohngeld_prev":         "nein",
        "wg_pay_bab":                   "nein",
        "wg_pay_ausbildungsfoerderung": "nein",
        "wg_pay_ausbildungsgeld":       "nein",
        "wg_pay_mobiproeu":             "nein",
        "wg_pay_uebergangsgeld":        "nein",
        "wg_pay_verletztengeld12":      "nein",
        "wg_pay_jugendhilfe12":         "nein",
        # §14 One-time payments
        "wg_has_onetime_payment": "nein",
        "wg_onetime_expected":    "nein",
        # §15 Expected income changes
        "wg_income_change_expected": "nein",
        # §18 Unterhalt claims
        "wg_has_unterhalt_claim": "nein",
        # §20 Kindergeld elsewhere
        "wg_kindergeld_elsewhere": "nein",
        # §21 Unterhalt payments
        "wg_has_unterhalt":  "nein",
        "wg_unterhalt_extra": "nein",
        # §22 Housing type
        "wg_is_untermieter":      "nein",
        "wg_is_heimbewohner":     "nein",
        "wg_is_mehrfamilienhaus": "nein",
        "wg_is_sonstiger_nutzer": "nein",
        # §23 Employer subsidy
        "wg_employer_subsidy": "nein",
        # §26 Rent reduction
        "wg_rent_reduction": "nein",
        # §27 Partial use
        "wg_commercial_use":   "nein",
        "wg_sublet_to_others": "nein",
        "wg_shared_by_others": "nein",
        "wg_subletting_heating": "nein",
        "wg_subletting_energy":  "nein",
        "wg_subletting_garage":  "nein",
        # §28 Business use
        "wg_has_business_use": "nein",
        # §29 Wohnrecht
        "wg_has_wohnrecht": "nein",
        # §30 Abroad
        "wg_abroad": "nein",
        # §31 Third party pays
        "wg_third_party_pays": "nein",
        # §19 NS victim
        "wg_disabled1_ns_victim": "nein",
        "wg_disabled2_ns_victim": "nein",
    }
    for _key, _default in _bool_defaults.items():
        _raw = str(data.get(_key, "")).strip().lower()
        if _raw not in ("ja", "nein", "yes", "no", "true", "false", "1", "0"):
            _log.debug("[WG_NORM] boolean default: %s → %r", _key, _default)
            data[_key] = _default

    # ── 2. Numeric field defaults ─────────────────────────────────────────────
    # monthly_income defaults to "0" only when has_income == "ja" and the field is empty,
    # to avoid a blank required income field.  heating_costs and additional_costs are
    # intentionally left empty when not filled — their PDF checkboxes (wg_heizkosten_chk /
    # wg_sonstige_chk) must NOT tick when the user entered nothing.
    _inc_raw = str(data.get("monthly_income", "")).strip()
    if not _inc_raw:
        _log.debug("[WG_NORM] numeric default: monthly_income → '0'")
        data["monthly_income"] = "0"

    # ── 3. Signature date / place fallbacks ───────────────────────────────────
    if not str(data.get("signature_date", "")).strip():
        data["signature_date"] = _date.today().strftime("%d.%m.%Y")
    if not str(data.get("signature_place", "")).strip():
        _city = str(data.get("city", "")).strip()
        if _city:
            data["signature_place"] = _city

    # ── 4. Assemble household_members (idempotent guard) ─────────────────────
    if not data.get("household_members"):
        _has_hm = str(data.get("has_household_members", "")).strip().lower()
        if _has_hm in ("ja", "yes", "true", "1"):
            _member: Dict[str, Any] = {}
            for _flat_key, _dict_key in (
                ("member_name",          "name"),
                ("member_birth_date",    "birth_date"),
                ("member_birth_place",   "birth_place"),
                ("member_relation",      "relation"),
                ("member_gender",        "gender"),
                ("member_nationality",   "nationality"),
                ("member_family_status", "family_status"),
                ("member_occupation",    "occupation"),
            ):
                _val = str(data.get(_flat_key, "")).strip()
                if _val:
                    _member[_dict_key] = _val
            data["household_members"] = [_member] if _member else []
        else:
            data["household_members"] = []

    return data


# ── Country canonical lookup (shared) ─────────────────────────────────────────
_COUNTRY_CANONICAL: Dict[str, str] = {
    "ukraine":        "Ukraine",
    "deutschland":    "Deutschland",
    "germany":        "Deutschland",
    "russland":       "Russland",
    "russia":         "Russland",
    "belarus":        "Belarus",
    "weissrussland":  "Weißrussland",
    "weißrussland":   "Weißrussland",
    "moldova":        "Moldova",
    "moldau":         "Moldau",
    "georgien":       "Georgien",
    "georgia":        "Georgien",
    "armenien":       "Armenien",
    "armenia":        "Armenien",
    "aserbaidschan":  "Aserbaidschan",
    "azerbaijan":     "Aserbaidschan",
    "kasachstan":     "Kasachstan",
    "kazakhstan":     "Kasachstan",
    "usbekistan":     "Usbekistan",
    "uzbekistan":     "Usbekistan",
    "kirgisistan":    "Kirgisistan",
    "kyrgyzstan":     "Kirgisistan",
    "tadschikistan":  "Tadschikistan",
    "tajikistan":     "Tadschikistan",
    "turkmenistan":   "Turkmenistan",
    "turkmenien":     "Turkmenistan",
    "österreich":     "Österreich",
    "austria":        "Österreich",
    "schweiz":        "Schweiz",
    "switzerland":    "Schweiz",
    "frankreich":     "Frankreich",
    "france":         "Frankreich",
    "italien":        "Italien",
    "italy":          "Italien",
    "spanien":        "Spanien",
    "spain":          "Spanien",
    "polen":          "Polen",
    "poland":         "Polen",
    "türkei":         "Türkei",
    "turkey":         "Türkei",
    "tschechien":     "Tschechien",
    "czech":          "Tschechien",
    "rumänien":       "Rumänien",
    "romania":        "Rumänien",
    "bulgarien":      "Bulgarien",
    "bulgaria":       "Bulgarien",
    "ungarn":         "Ungarn",
    "hungary":        "Ungarn",
    "kroatien":       "Kroatien",
    "croatia":        "Kroatien",
    "serbien":        "Serbien",
    "serbia":         "Serbien",
}


def validate_buergergeld_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final sanity check for Bürgergeld/Jobcenter data AFTER normalize_buergergeld_data().

    Auto-fixes logical conflicts — data consistency always wins over raw input.
    Logs every fix at DEBUG level with prefix [PDF VALIDATE].

    Rules enforced:
    A. IBAN ↔ kein_konto: IBAN present → kein_konto marker must not exist;
       if IBAN absent and kein_konto marker present → clear IBAN (already empty).
    B. SV consistency: has_sv_number=nein + sv_number filled → clear sv_number.
    C. Country canonical form: exact-match lookup for common country names.
    D. Employment: employment_status not "employed" → employer fields cleared.
    E. Sonderstatus gate: has_sonderstatus=nein → is_schueler=nein, is_asylbewerber=nein.
    F. Sondersituation gate: has_sondersituation=nein → has_betreuer=nein,
       has_verpflichtung=nein (unless user explicitly provided them).
    G. Benefits gate: has_andere_leistungen=nein → receives_benefits cleared.
    H. Residence gate: has_residence_permit=nein → entry_date_germany cleared.
    I. Household gate: living_alone=ja → household_type cleared.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    result = dict(data)

    def _v(key: str) -> str:
        return (result.get(key) or "").strip()

    def _is_nein(key: str) -> bool:
        return _v(key).lower() in ("nein", "no", "false", "0")

    def _is_ja(key: str) -> bool:
        return _v(key).lower() in ("ja", "yes", "true", "1")

    # Fields that are considered "user-visible" input — overriding them is notable.
    _USER_INPUT_KEYS = frozenset({
        "has_sv_number", "sv_number", "has_residence_permit", "entry_date_germany",
        "is_schueler", "is_asylbewerber", "has_betreuer", "has_verpflichtung",
        "receives_benefits", "household_type", "employer_name", "employer_street",
        "employer_house_number", "employer_plz", "employer_city",
    })

    def _fix(key: str, value: str, reason: str) -> None:
        old = result.get(key)
        if old == value:
            return
        if key in _USER_INPUT_KEYS and old not in (None, "", "nein", "no"):
            _log.warning(
                "[PDF VALIDATE WARNING] user input overridden: field=%s old=%r → new=%r  (%s)",
                key, old, value, reason,
            )
        else:
            _log.debug("[PDF VALIDATE] fix %s: %r → %r  (%s)", key, old, value, reason)
        result[key] = value

    # A. SV consistency — has_sv_number flag has FULL priority.
    # Rule: nein → clear sv_number (flag wins over filled value).
    # Inverse: sv_number present + flag unset → infer "ja" (but NEVER override explicit "nein").
    _sv_num = _v("sv_number")
    if _is_nein("has_sv_number") and _sv_num:
        _fix("sv_number", "", "has_sv_number=nein → clear orphan sv_number")
    elif _sv_num and not _v("has_sv_number"):
        _fix("has_sv_number", "ja", "sv_number filled + flag unset → infer ja")

    # B. IBAN consistency
    _iban = _v("iban")
    # Nothing to clear on the data side — the PDF mapping layer handles the
    # checkbox. But if "kein_konto" marker exists as a data key, clear it.
    if _iban and result.get("kein_konto"):
        _fix("kein_konto", "", "IBAN present → kein_konto marker must be cleared")
    _log.debug("[PDF VALIDATE] IBAN present=%s", bool(_iban))

    # C. Country canonical form (exact match after lower-strip)
    for _cfield in ("birth_country", "geburtsland"):
        _raw = _v(_cfield)
        if _raw:
            _canon = _COUNTRY_CANONICAL.get(_raw.lower())
            if _canon and _raw != _canon:
                _fix(_cfield, _canon, f"country canonical: {_raw!r} → {_canon!r}")

    # D. Employment fields (redundant safety net — normalize already did this)
    _emp = _v("employment_status").lower()
    if _emp not in ("angestellt", "beschäftigt", "selbständig", "selbstaendig"):
        for _ef in ("employer_name", "employer_street", "employer_house_number",
                    "employer_plz", "employer_city"):
            if _v(_ef):
                _fix(_ef, "", f"employment_status={_emp!r} → clear {_ef}")

    # E. Sonderstatus gate
    if _is_nein("has_sonderstatus"):
        if not _is_nein("is_schueler"):
            _fix("is_schueler", "nein", "has_sonderstatus=nein gate")
        if not _is_nein("is_asylbewerber"):
            _fix("is_asylbewerber", "nein", "has_sonderstatus=nein gate")

    # F. Sondersituation gate (only clear sub-fields if user didn't fill them)
    if _is_nein("has_sondersituation"):
        if not _is_ja("has_betreuer"):
            pass  # already nein — no-op
        if _v("has_betreuer") not in ("ja", "nein"):
            _fix("has_betreuer", "nein", "has_sondersituation=nein gate, betreuer unknown")
        if _v("has_verpflichtung") not in ("ja", "nein"):
            _fix("has_verpflichtung", "nein", "has_sondersituation=nein gate, verpflichtung unknown")

    # G. Benefits gate
    if _is_nein("has_andere_leistungen") and _v("receives_benefits"):
        _fix("receives_benefits", "", "has_andere_leistungen=nein gate")

    # H. Residence gate
    if _is_nein("has_residence_permit") and _v("entry_date_germany"):
        _fix("entry_date_germany", "", "has_residence_permit=nein gate")

    # I. Household gate
    if _is_ja("living_alone") and _v("household_type"):
        _fix("household_type", "", "living_alone=ja gate")

    _log.debug(
        "[PDF VALIDATE] done — employment=%r iban=%s sv=%r",
        result.get("employment_status"), bool(_iban), result.get("has_sv_number"),
    )
    return result
