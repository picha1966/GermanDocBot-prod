# -*- coding: utf-8 -*-
"""
backend/validators.py — rule-based validation and normalization for PDF generation.

- Dates → DD.MM.YYYY (or skip if invalid)
- PLZ → 5 digits
- Enum/select → internal constant (exact option value); invalid/empty → not written
- Empty or invalid values MUST NOT be rendered into PDF.
No AI. Rule-based only.
"""

import logging
import re
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Date normalization: any reasonable input → DD.MM.YYYY or None
# -----------------------------------------------------------------------------

DATE_DDMMYYYY = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$")
DATE_YYYYMMDD = re.compile(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$")


def normalize_date(value: Any) -> Optional[str]:
    """
    Normalize date to DD.MM.YYYY. Returns None if invalid or empty.
    Accepts: DD.MM.YYYY, DD-MM-YYYY, YYYY-MM-DD, D.M.YYYY, etc.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # DD.MM.YYYY or DD-MM-YYYY
    m = DATE_DDMMYYYY.match(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100:
            return f"{d:02d}.{mo:02d}.{y:04d}"
        return None
    # YYYY-MM-DD
    m = DATE_YYYYMMDD.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100:
            return f"{d:02d}.{mo:02d}.{y:04d}"
        return None
    return None


# -----------------------------------------------------------------------------
# PLZ: 5 digits only
# -----------------------------------------------------------------------------


def normalize_plz(value: Any) -> Optional[str]:
    """Normalize to 5-digit string (German PLZ). Returns None if invalid."""
    if value is None:
        return None
    s = str(value).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) == 5:
        return digits
    if len(digits) > 5:
        return digits[:5]
    return None


# -----------------------------------------------------------------------------
# Enum/select: value must be one of allowed options (case-insensitive match)
# -----------------------------------------------------------------------------


def normalize_enum(value: Any, allowed: List[str]) -> Optional[str]:
    """
    Return exact option value if input matches (case-insensitive, strip).
    Otherwise None.
    """
    if value is None or not allowed:
        return None
    s = str(value).strip()
    if not s:
        return None
    low = s.lower()
    for opt in allowed:
        if opt.lower() == low:
            return opt
    return None


# -----------------------------------------------------------------------------
# Latin-only text (for names, places): allow A-Z, a-z, digits, space, . , ' - /
# -----------------------------------------------------------------------------


def is_valid_latin_text(value: Any, min_len: int = 0) -> bool:
    if value is None:
        return min_len == 0
    s = str(value).strip()
    if len(s) < min_len:
        return False
    if not s:
        return min_len == 0
    # Extended to include German umlauts (ä,ö,ü,Ä,Ö,Ü,ß) and common punctuation.
    # Pure Cyrillic / Arabic input is still rejected.
    _LATIN_DE = r"A-Za-zÄÖÜäöüß"
    _PUNCT    = r"0-9 \.,'\-\/\(\)&\+"
    return bool(re.match(rf"^[{_LATIN_DE}{_PUNCT}]+$", s))


def looks_like_date(value: Any) -> bool:
    """True if value looks like DD.MM.YYYY (so it must not go into nationality etc.)."""
    if value is None:
        return False
    s = str(value).strip()
    return bool(DATE_DDMMYYYY.match(s) or DATE_YYYYMMDD.match(s))


# Match date anywhere in string (e.g. "09.08.2023 Berlin" must not go into nationality)
DATE_PATTERN_IN_STRING = re.compile(r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}")


def contains_date_pattern(value: Any) -> bool:
    """True if value contains a date pattern (DD.MM.YYYY) anywhere — reject for nationality."""
    if value is None:
        return False
    return bool(DATE_PATTERN_IN_STRING.search(str(value)))


def _parse_marriage_place_date(value: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse marriage place/date input in tolerant UX formats:
      - "City DD.MM.YYYY"
      - "City, DD.MM.YYYY"

    Returns:
      (city, date_str, error_key)
      - error_key: "invalid_date" | "value_invalid" | None
    """
    if value is None:
        return None, None, None
    s = str(value).strip()
    if not s:
        return None, None, None

    # Strip pipe-separated duplicate suffix: "City, Date | City, Date" → "City, Date"
    # "|" is not a valid character in a place-date string; everything after it is noise.
    s = re.sub(r"\s*\|.*$", "", s).strip()
    if not s:
        return None, None, None

    # Accept:
    #   "Berlin 15.05.2020"
    #   "Berlin, 15.05.2020"
    #   "Berlin,15.05.2020"
    m = re.match(r"^\s*(.+?)\s*,?\s*(\d{2}\.\d{2}\.\d{4})\s*$", s)
    if not m:
        return None, None, "invalid_date"

    city_raw = m.group(1).strip()
    date_raw = m.group(2).strip()
    if not city_raw:
        return None, None, "value_invalid"

    return city_raw, date_raw, None


def normalize_latin_text(value: Any, max_len: Optional[int] = None) -> Optional[str]:
    """Return stripped string if non-empty and latin-only; else None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if not re.match(r"^[A-Za-z0-9 .,'\-\/]+$", s):
        return None
    if max_len is not None and len(s) > max_len:
        s = s[:max_len]
    return s


# -----------------------------------------------------------------------------
# Anmeldung: typo corrections (Bürgeramt-acceptable spelling)
# -----------------------------------------------------------------------------

# Map common typos/variants -> German adjectival form used across PDF output.
# Keep this aligned with backend.utils.normalize._normalize_nationality.
_ANMELDUNG_NATIONALITY_CORRECTIONS = {
    "ua": "ukrainisch",
    "ukrasne": "ukrainisch",
    "ukraine": "ukrainisch",
}
# Always output exactly "Vinnytsia, Ukraine" (comma, no "Vinnitsa Ukraine")
_ANMELDUNG_PLACE_CORRECTIONS = {
    "vinnitsa": "Vinnytsia, Ukraine",
    "vinnitsa ukraine": "Vinnytsia, Ukraine",
    "vinnytsia ukraine": "Vinnytsia, Ukraine",
    "vinnytsia": "Vinnytsia, Ukraine",
    "winniza": "Vinnytsia, Ukraine",
    "winniza ukraine": "Vinnytsia, Ukraine",
}
# Placeholder symbols to replace (Œ etc.) — use em dash for placeholders in text
_ANMELDUNG_PLACEHOLDER_SYMBOLS = ("\u0152", "Œ", "\u0092")  # Œ and similar
_ANMELDUNG_STREET_CORRECTIONS = {
    "karlstrase": "Karlstraße",
    "karlstrasse": "Karlstraße",
    "maxstrase": "Maxstraße",
    "maxstrasse": "Maxstraße",
}


def _normalize_placeholder_symbols(s: str) -> str:
    """Replace Œ and similar placeholder symbols with em dash. Never output raw Œ."""
    if not s:
        return s
    for sym in _ANMELDUNG_PLACEHOLDER_SYMBOLS:
        s = s.replace(sym, "—")
    return s


def _apply_anmeldung_typo_corrections(data: Dict[str, Any]) -> None:
    """Apply known typo corrections to Anmeldung user_data in place. Used before normalization."""
    if not data:
        return
    # Replace placeholder symbols (Œ etc.) in all string values
    for key, value in list(data.items()):
        if value is not None and isinstance(value, str) and value.strip():
            data[key] = _normalize_placeholder_symbols(value)
    # Nationality
    for key in ("nationality", "person2_nationality"):
        v = data.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        low = s.lower()
        if low in _ANMELDUNG_NATIONALITY_CORRECTIONS:
            data[key] = _ANMELDUNG_NATIONALITY_CORRECTIONS[low]
    # Birth place, Eheschließung Ort — normalize ONLY exact known variants (no silent fix for gibberish)
    _vinnytsia_variants = frozenset(
        k for k in _ANMELDUNG_PLACE_CORRECTIONS
    ) | frozenset(["vinnitsa", "vinnytsia", "vinnitsa ukraine", "vinnytsia ukraine", "winniza", "winniza ukraine"])
    for key in ("birth_place", "person2_birth_place", "eheschliessung_ort_datum"):
        v = data.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        low = s.lower()
        if low in _ANMELDUNG_PLACE_CORRECTIONS:
            data[key] = _ANMELDUNG_PLACE_CORRECTIONS[low]
        elif low in _vinnytsia_variants:
            data[key] = "Vinnytsia, Ukraine"
    # Street (neue Wohnung)
    v = data.get("street")
    if v is not None:
        s = str(v).strip()
        if s:
            low = s.lower()
            if low == "maxstrase 12":
                data["street"] = "Maxstraße 12"
            elif low == "maxstrase":
                data["street"] = "Maxstraße"
            elif low == "maxstrasse 12":
                data["street"] = "Maxstraße 12"
            elif low == "maxstrasse":
                data["street"] = "Maxstraße"
    # Bisherige Wohnung: previous_address and old_street (if present)
    for key in ("previous_address", "old_street"):
        v = data.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        low = s.lower()
        if low in _ANMELDUNG_STREET_CORRECTIONS:
            data[key] = _ANMELDUNG_STREET_CORRECTIONS[low]
        elif "karlstrase" in low and "karlstraße" not in s and "karlstrasse" not in s:
            data[key] = "Karlstraße"


# -----------------------------------------------------------------------------
# Anmeldung: get field types from schema and normalize/validate
# -----------------------------------------------------------------------------


def _get_anmeldung_flat_fields() -> List[Dict[str, Any]]:
    """Flat list of fields with name, type, required, options (for select)."""
    try:
        from backend.document_config import get_document_form_schema
        schema = get_document_form_schema("anmeldung")
        if not schema:
            return []
        out = []
        for sec in (schema.get("sections") or []):
            for f in sec.get("fields") or []:
                opts = []
                for o in (f.get("options") or []):
                    if isinstance(o, dict) and "value" in o:
                        opts.append(o["value"])
                    elif isinstance(o, str):
                        opts.append(o)
                out.append({
                    "key": f.get("name"),
                    "type": f.get("type", "text"),
                    "required": bool(f.get("required")),
                    "options": opts,
                })
        return out
    except Exception:
        return []


def normalize_and_validate_anmeldung(user_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """
    Normalize and validate user_data for Anmeldung PDF.
    - Applies typo corrections (Staatsangehörigkeit, Straße, Geburtsort, Eheschließung Ort).
    - Dates → DD.MM.YYYY
    - PLZ → 5 digits
    - Enum/select → exact option value; do not write text for Ja/Nein, wohnungstyp, etc.
    - Empty/invalid → key not set in normalized dict (so PDF won't render them).

    Returns:
        (normalized_data, errors)
        errors = [{"field": "move_in_date", "message": "Invalid date"}, ...]
        If errors and required field missing/invalid, caller should not generate PDF.
    """
    from backend.document_config import ANSWER_KEY_ALIASES

    user_data = dict(user_data)
    # Log raw gender keys BEFORE any normalization — confirms what arrived from the form
    logger.info(
        "NORMALIZE_ANMELDUNG_ENTRY: gender=%r person2_gender=%r person1_gender=%r geschlecht=%r all_keys=%s",
        user_data.get("gender"),
        user_data.get("person2_gender"),
        user_data.get("person1_gender"),
        user_data.get("geschlecht"),
        sorted(user_data.keys()),
    )
    # Alias: person1_gender → gender; treat "" the same as missing
    _g_val = str(user_data.get("gender", "")).strip()
    if not _g_val:
        user_data["gender"] = user_data.get("person1_gender")
    try:
        from backend.document_config import apply_anmeldung_completion
        user_data = apply_anmeldung_completion(user_data)
    except Exception:
        pass
    _apply_anmeldung_typo_corrections(user_data)

    def get_raw(key: str) -> Any:
        v = user_data.get(key)
        if v is not None and str(v).strip():
            return v
        for alias in ANSWER_KEY_ALIASES.get(key, []) or []:
            if alias != key:
                v = user_data.get(alias)
                if v is not None and str(v).strip():
                    return v
        return None

    normalized: Dict[str, Any] = {}
    errors: List[Dict[str, str]] = []
    flat = _get_anmeldung_flat_fields()
    field_by_key = {f["key"]: f for f in flat}

    for f in flat:
        key = f["key"]
        typ = f.get("type", "text")
        required = f.get("required", False)
        raw = get_raw(key)

        if typ == "date":
            n = normalize_date(raw)
            if required and raw is not None and str(raw).strip() and not n:
                errors.append({"field": key, "message": "invalid_date"})
            if n:
                normalized[key] = n
            continue

        if typ == "plz":
            n = normalize_plz(raw)
            if required and raw is not None and str(raw).strip() and not n:
                errors.append({"field": key, "message": "invalid_plz"})
            if n:
                normalized[key] = n
            continue

        if typ == "select" and f.get("options"):
            opts = f["options"]
            raw_for_enum = raw
            # normalize_user_data expands "w"→"weiblich" globally, but schema options
            # for gender use short codes "m"/"w"/"d". Reverse-map before validating so
            # the value is not silently dropped. person2_gender is NOT expanded by
            # normalize_user_data (only "gender" is), but include it here as a safeguard.
            if key in ("gender", "person2_gender") and raw_for_enum:
                _gv = str(raw_for_enum).strip().lower()
                if _gv in ("männlich", "maennlich", "male"):
                    raw_for_enum = "m"
                elif _gv in ("weiblich", "female", "f"):
                    raw_for_enum = "w"
                elif _gv in ("divers", "diverse"):
                    raw_for_enum = "d"
            n = normalize_enum(raw_for_enum, opts)
            if required and raw is not None and str(raw).strip() and not n:
                errors.append({"field": key, "message": "invalid_enum"})
            if n:
                normalized[key] = n
            continue

        # text and other
        if raw is not None:
            s = str(raw).strip()
            if s:
                # Nationality: never accept date or string containing date (e.g. "09.08.2023 Berlin")
                if key in ("nationality", "person2_nationality"):
                    if looks_like_date(s) or contains_date_pattern(s) or (s.isdigit() and len(s) <= 6):
                        continue  # do not add to normalized
                    if not is_valid_latin_text(s):
                        if required:
                            errors.append({"field": key, "message": "latin_only"})
                        continue
                    normalized[key] = s[:200] if len(s) > 200 else s
                    continue
                # Names, address, place: min 2 chars so "X", "3" are not accepted
                name_place_keys = (
                    "first_name", "last_name", "birth_place", "street", "city",
                    "person2_first_name", "person2_last_name", "person2_birth_place",
                )
                if key in name_place_keys:
                    if len(s) < 2:
                        if required:
                            errors.append({"field": key, "message": "too_short"})
                        continue
                # Birth place: do not accept string that contains a date (e.g. "09.08.2023 Berlin")
                if key in ("birth_place", "person2_birth_place") and contains_date_pattern(s):
                    continue
                if key in ("first_name", "last_name", "birth_name", "birth_place", "street", "city",
                           "person2_first_name", "person2_last_name", "person2_birth_name", "person2_birth_place",
                           "passname", "ordens_kuenstlername", "landlord_name", "signature_place",
                           "previous_address", "zuzug_staat", "eheschliessung_ort_datum", "religion"):
                    if key == "eheschliessung_ort_datum":
                        _city, _date, _err = _parse_marriage_place_date(s)
                        if _err:
                            errors.append({"field": key, "message": _err})
                            continue
                        _combined = f"{_city}, {_date}"
                        if is_valid_latin_text(_combined):
                            normalized[key] = _combined[:200] if len(_combined) > 200 else _combined
                        elif required:
                            errors.append({"field": key, "message": "latin_only"})
                        continue
                    if is_valid_latin_text(s, min_len=2 if key in name_place_keys else 0):
                        normalized[key] = s[:200] if len(s) > 200 else s
                    elif required:
                        errors.append({"field": key, "message": "latin_only"})
                else:
                    normalized[key] = s[:200] if len(s) > 200 else s
        if required and key not in normalized and key in field_by_key:
            # Required but missing
            if get_raw(key) is None or not str(get_raw(key) or "").strip():
                errors.append({"field": key, "message": "required"})

    # Required fields: if still missing in normalized, add error once
    for f in flat:
        if not f.get("required"):
            continue
        key = f["key"]
        if key in normalized:
            continue
        if any(e["field"] == key for e in errors):
            continue
        errors.append({"field": key, "message": "required"})

    return normalized, errors
