# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT – Authority Manager (Production-grade)
====================================================
Визначає адресу установи (Bürgeramt, Familienkasse, Wohngeldstelle) на основі PLZ.
"""

import os
import logging
from typing import Optional, Dict, Any

# Налаштування логування
logger = logging.getLogger(__name__)

# ============================================================================
# БЕЗПЕЧНИЙ ІМПОРТ БАЗИ ДАНИХ З data_processor.py
# ============================================================================
AUTHORITIES_BY_PLZ = {}
WOHNGELD_ADDRESSES = {}

try:
    # Пріоритет 1: data_processor.py (той файл, який ви знайшли)
    from backend.data_processor import AUTHORITIES_BY_PLZ as a_plz, WOHNGELD_ADDRESSES as w_addr
    AUTHORITIES_BY_PLZ, WOHNGELD_ADDRESSES = a_plz, w_addr
    logger.info("✅ База адрес завантажена з backend.data_processor.py")
except ImportError:
    try:
        # Пріоритет 2: властиво authorities.py (як запасний варіант)
        from backend.authorities import AUTHORITIES_BY_PLZ as a_plz, WOHNGELD_ADDRESSES as w_addr
        AUTHORITIES_BY_PLZ, WOHNGELD_ADDRESSES = a_plz, w_addr
        logger.info("✅ База адрес завантажена з backend.authorities")
    except ImportError:
        logger.error("❌ НЕ ЗНАЙДЕНО ФАЙЛ БАЗИ ДАНИХ (data_processor.py або authorities.py)")

# ============================================================================
# PLZ normalisation
# ============================================================================

def _clean_plz(plz: Any) -> Optional[str]:
    try:
        if plz is None:
            return None
        s = str(plz).strip().replace(" ", "")
        if len(s) != 5 or not s.isdigit():
            return None
        return s
    except Exception:
        return None

# ============================================================================
# Bundesland detection (Всі 16 земель Німеччини)
# ============================================================================

def get_bundesland(plz: Any) -> Optional[str]:
    """Визначає федеральну землю за першими цифрами індексу."""
    plz = _clean_plz(plz)
    if not plz:
        return None

    try:
        p = int(plz[:2])
        # Офіційні діапазони Deutsche Post для всіх 16 земель
        if 10 <= p <= 13: return "Berlin"
        if 14 <= p <= 16: return "Brandenburg"
        if 17 <= p <= 19: return "Mecklenburg-Vorpommern"
        if 20 <= p <= 22: return "Hamburg"
        if 23 <= p <= 25: return "Schleswig-Holstein"
        if 26 <= p <= 31: return "Niedersachsen"
        if p == 27 or p == 28: return "Bremen"
        if 32 <= p <= 53: return "Nordrhein-Westfalen"
        if 54 <= p <= 56: return "Rheinland-Pfalz"
        if 60 <= p <= 65: return "Hessen"
        if p == 66: return "Saarland"
        if 68 <= p <= 79: return "Baden-Württemberg"
        if 80 <= p <= 97: return "Bayern"
        if p == 39: return "Sachsen-Anhalt"
        if 1 <= p <= 9: return "Sachsen"
        if 98 <= p <= 99: return "Thüringen"
    except Exception:
        logger.error(f"Помилка визначення землі для PLZ {plz}")

    return None

# ============================================================================
# Address formatter
# ============================================================================

def _record_to_address(record: Any) -> Optional[str]:
    """Перетворює запис із бази у форматований текст для PDF."""
    if not record:
        return None
    if isinstance(record, str):
        return record.strip()
    if isinstance(record, dict):
        if "address" in record:
            return record["address"].strip()
        
        parts = []
        # Збираємо адресу по частинах
        name = record.get("name") or record.get("title")
        if name: parts.append(str(name))
        
        dept = record.get("department")
        if dept: parts.append(str(dept))
        
        street = record.get("street") or record.get("street_address")
        if street: parts.append(str(street))

        z = record.get("postal_code") or record.get("zip") or ""
        c = record.get("city") or ""
        if z or c:
            parts.append(f"{z} {c}".strip())
        
        return "\n".join(p for p in parts if p)
    return str(record)

# ============================================================================
# Main resolver
# ============================================================================

def get_authority_address(doc_type: str, plz: Any) -> Optional[str]:
    """Знаходить адресу установи для PDF генератора."""
    try:
        if not doc_type: return None
        
        doc_type = doc_type.strip().lower()
        plz_clean = _clean_plz(plz)
        if not plz_clean: return None

        # 1. Логіка для Wohngeld
        if doc_type == "wohngeld":
            record = WOHNGELD_ADDRESSES.get(plz_clean)
            if not record:
                land = get_bundesland(plz_clean)
                record = WOHNGELD_ADDRESSES.get(land)
            if not record:
                record = WOHNGELD_ADDRESSES.get("DEFAULT")
            return _record_to_address(record)

        # 2. Логіка для Anmeldung, Kindergeld тощо
        record = AUTHORITIES_BY_PLZ.get(plz_clean)
        if record:
            logger.info(f"✅ Знайдено відомство для {plz_clean}")
            return _record_to_address(record)

        logger.warning(f"⚠️ Адресу не знайдено для PLZ {plz_clean} ({doc_type})")
        return None

    except Exception as e:
        logger.error(f"Критична помилка пошуку адреси: {e}")
        return None