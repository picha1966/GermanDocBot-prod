# -*- coding: utf-8 -*-
"""
Smart Family Profiles - ВИПРАВЛЕНА ВЕРСІЯ
Синхронізовано з database.py - БЕЗ зайвих колонок та індексів
"""

import json
import re
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class FamilyMemberType:
    """Типи членів сім'ї"""
    CHILD = "child"
    PARTNER = "partner"
    APPLICANT = "applicant"


class DataNormalizer:
    """Нормалізація даних перед збереженням"""
    
    @staticmethod
    def normalize_iban(iban: str) -> str:
        """Видаляє пробіли з IBAN"""
        if not iban:
            return ""
        return re.sub(r'\s+', '', iban.upper().strip())
    
    @staticmethod
    def normalize_date(date_str: str, output_format: str = "iso") -> str:
        """Конвертує дату між форматами DD.MM.YYYY <-> YYYY-MM-DD"""
        if not date_str:
            return ""
        
        date_str = date_str.strip()
        
        if '.' in date_str:  # DD.MM.YYYY
            parts = date_str.split('.')
            if len(parts) == 3:
                day, month, year = parts
                iso_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        elif '-' in date_str:  # YYYY-MM-DD
            parts = date_str.split('-')
            if len(parts) == 3:
                year, month, day = parts
                iso_date = date_str
        else:
            return date_str
        
        if output_format == "iso":
            return iso_date
        elif output_format == "display":
            return f"{day.zfill(2)}.{month.zfill(2)}.{year}"
        
        return date_str
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """Очищає ім'я від зайвих пробілів"""
        if not name:
            return ""
        return ' '.join(name.strip().split())
    
    @staticmethod
    def normalize_postal_code(postal_code: str) -> str:
        """Нормалізує поштовий індекс (тільки цифри)"""
        if not postal_code:
            return ""
        return re.sub(r'\D', '', postal_code.strip())


class FamilyProfilesManager:
    """
    Менеджер профілів сім'ї - ВИПРАВЛЕНА ВЕРСІЯ
    БЕЗ зайвих колонок usage_count, is_active, display_name
    """
    
    def __init__(self, db):
        """
        Ініціалізація з об'єктом Database
        
        Args:
            db: Екземпляр класу Database з database.py
        """
        # Дістаємо шлях до БД з об'єкта Database
        self.db_path = db.db_name if hasattr(db, 'db_name') else db.db_path
        self.normalizer = DataNormalizer()
        self._init_family_tables()

    @contextmanager
    def _get_connection(self):
        """Пряме підключення до SQLite"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_family_tables(self):
        """
        Створення таблиць БЕЗ зайвих колонок
        ТІЛЬКИ необхідні поля для роботи
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # ============================================================
            # ТАБЛИЦЯ ЧЛЕНІВ СІМ'Ї (мінімалістична)
            # ============================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS family_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    member_type TEXT NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    birth_date TEXT,
                    relation TEXT,
                    tax_id TEXT,
                    additional_data TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            
            # ============================================================
            # ТАБЛИЦЯ АДРЕС
            # ============================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_addresses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    address_name TEXT DEFAULT 'Домашня',
                    street TEXT,
                    house_number TEXT,
                    city TEXT,
                    postal_code TEXT,
                    is_primary INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            
            # ============================================================
            # ТАБЛИЦЯ БАНКІВСЬКИХ РЕКВІЗИТІВ
            # ============================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_bank_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    account_name TEXT DEFAULT 'Основний',
                    iban TEXT,
                    bic TEXT,
                    bank_name TEXT,
                    account_holder TEXT,
                    is_primary INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(user_id, iban)
                )
            """)
            
            # ============================================================
            # ІНДЕКСИ (тільки безпечні, БЕЗ usage_count та is_active)
            # ============================================================
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_fm_user ON family_members(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sa_user ON saved_addresses(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_user ON saved_bank_details(user_id)")
            
            conn.commit()

    # ================================================================
    # ЧЛЕНИ СІМ'Ї
    # ================================================================

    def add_or_update_family_member(
        self,
        user_id: int,
        member_type: str,
        first_name: str,
        last_name: str = None,
        birth_date: str = None,
        relation: str = None,
        tax_id: str = None,
        additional_data: dict = None
    ) -> int:
        """Додати або оновити члена сім'ї (UPSERT)"""
        first_name = self.normalizer.normalize_name(first_name)
        last_name = self.normalizer.normalize_name(last_name) if last_name else None
        birth_date_iso = self.normalizer.normalize_date(birth_date, "iso") if birth_date else None
        
        if not first_name:
            raise ValueError("First name cannot be empty")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Перевірка на існування
            cursor.execute("""
                SELECT id FROM family_members 
                WHERE user_id = ? AND first_name = ? AND 
                      COALESCE(last_name, '') = COALESCE(?, '') AND 
                      COALESCE(birth_date, '') = COALESCE(?, '') AND
                      member_type = ?
            """, (user_id, first_name, last_name or '', birth_date_iso or '', member_type))
            
            existing = cursor.fetchone()
            
            if existing:
                # Оновлюємо існуючий
                member_id = existing['id']
                
                # Об'єднуємо додаткові дані
                cursor.execute("SELECT additional_data FROM family_members WHERE id = ?", (member_id,))
                current_data = json.loads(cursor.fetchone()['additional_data'] or '{}')
                merged_data = {**current_data, **(additional_data or {})}
                
                cursor.execute("""
                    UPDATE family_members 
                    SET relation = ?, tax_id = COALESCE(?, tax_id),
                        additional_data = ?, updated_at = ?
                    WHERE id = ?
                """, (relation, tax_id, json.dumps(merged_data, ensure_ascii=False), now, member_id))
            else:
                # Створюємо новий
                cursor.execute("""
                    INSERT INTO family_members 
                    (user_id, member_type, first_name, last_name, birth_date, 
                     relation, tax_id, additional_data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, member_type, first_name, last_name, birth_date_iso,
                      relation, tax_id, json.dumps(additional_data or {}, ensure_ascii=False), now, now))
                member_id = cursor.lastrowid
            
            return member_id

    def get_family_members(
        self,
        user_id: int,
        member_type: str = None
    ) -> List[Dict[str, Any]]:
        """Отримати членів сім'ї"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if member_type:
                cursor.execute("""
                    SELECT * FROM family_members 
                    WHERE user_id = ? AND member_type = ?
                    ORDER BY created_at DESC
                """, (user_id, member_type))
            else:
                cursor.execute("""
                    SELECT * FROM family_members 
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                """, (user_id,))
            
            members = []
            for row in cursor.fetchall():
                member = dict(row)
                
                # Парсимо JSON
                if member.get('additional_data'):
                    try:
                        member['additional_data'] = json.loads(member['additional_data'])
                    except json.JSONDecodeError:
                        member['additional_data'] = {}
                
                # Додаємо display_name на льоту
                member['display_name'] = f"{member['first_name']} {member['last_name']}".strip() if member.get('last_name') else member['first_name']
                
                # Конвертуємо дату для відображення
                if member.get('birth_date'):
                    member['birth_date_display'] = self.normalizer.normalize_date(
                        member['birth_date'], "display"
                    )
                
                members.append(member)
            
            return members

    def get_children(self, user_id: int) -> List[Dict[str, Any]]:
        """Отримати список дітей"""
        return self.get_family_members(user_id, FamilyMemberType.CHILD)

    def get_partners(self, user_id: int) -> List[Dict[str, Any]]:
        """Отримати партнерів"""
        return self.get_family_members(user_id, FamilyMemberType.PARTNER)

    def delete_family_member(self, member_id: int, user_id: int) -> bool:
        """Видалити члена сім'ї"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM family_members 
                WHERE id = ? AND user_id = ?
            """, (member_id, user_id))
            return cursor.rowcount > 0

    # ================================================================
    # АДРЕСИ
    # ================================================================

    def save_or_update_address(
        self,
        user_id: int,
        street: str,
        city: str,
        postal_code: str,
        house_number: str = None,
        address_name: str = "Домашня",
        is_primary: bool = False
    ) -> int:
        """Зберегти або оновити адресу"""
        street = self.normalizer.normalize_name(street)
        city = self.normalizer.normalize_name(city)
        postal_code = self.normalizer.normalize_postal_code(postal_code)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Перевірка на існування
            cursor.execute("""
                SELECT id FROM saved_addresses 
                WHERE user_id = ? AND street = ? AND city = ? AND postal_code = ?
            """, (user_id, street, city, postal_code))
            
            existing = cursor.fetchone()
            
            if is_primary:
                cursor.execute("UPDATE saved_addresses SET is_primary = 0 WHERE user_id = ?", (user_id,))
            
            if existing:
                address_id = existing['id']
                cursor.execute("""
                    UPDATE saved_addresses 
                    SET address_name = ?, house_number = ?, is_primary = ?, updated_at = ?
                    WHERE id = ?
                """, (address_name, house_number, 1 if is_primary else 0, now, address_id))
            else:
                cursor.execute("""
                    INSERT INTO saved_addresses 
                    (user_id, address_name, street, house_number, city, postal_code, is_primary, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, address_name, street, house_number, city, postal_code, 
                      1 if is_primary else 0, now, now))
                address_id = cursor.lastrowid
            
            return address_id

    def get_addresses(self, user_id: int) -> List[Dict[str, Any]]:
        """Отримати збережені адреси"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM saved_addresses 
                WHERE user_id = ? 
                ORDER BY is_primary DESC, created_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_primary_address(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Отримати основну адресу"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM saved_addresses 
                WHERE user_id = ? AND is_primary = 1 LIMIT 1
            """, (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    # ================================================================
    # БАНКІВСЬКІ РЕКВІЗИТИ
    # ================================================================

    def save_or_update_bank_details(
        self,
        user_id: int,
        iban: str,
        bic: str = None,
        bank_name: str = None,
        account_holder: str = None,
        account_name: str = "Основний",
        is_primary: bool = False
    ) -> int:
        """Зберегти або оновити банківські реквізити"""
        iban = self.normalizer.normalize_iban(iban)
        
        if not iban:
            raise ValueError("IBAN cannot be empty")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute("""
                SELECT id FROM saved_bank_details 
                WHERE user_id = ? AND iban = ?
            """, (user_id, iban))
            
            existing = cursor.fetchone()
            
            if is_primary:
                cursor.execute("UPDATE saved_bank_details SET is_primary = 0 WHERE user_id = ?", (user_id,))
            
            if existing:
                bank_id = existing['id']
                cursor.execute("""
                    UPDATE saved_bank_details 
                    SET account_name = ?, bic = ?, bank_name = ?, 
                        account_holder = ?, is_primary = ?, updated_at = ?
                    WHERE id = ?
                """, (account_name, bic, bank_name, account_holder,
                      1 if is_primary else 0, now, bank_id))
            else:
                cursor.execute("""
                    INSERT INTO saved_bank_details 
                    (user_id, account_name, iban, bic, bank_name, account_holder, is_primary, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, account_name, iban, bic, bank_name, account_holder,
                      1 if is_primary else 0, now, now))
                bank_id = cursor.lastrowid
            
            return bank_id

    def get_bank_details(self, user_id: int) -> List[Dict[str, Any]]:
        """Отримати збережені банківські реквізити"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM saved_bank_details 
                WHERE user_id = ? 
                ORDER BY is_primary DESC, created_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_primary_bank(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Отримати основні банківські реквізити"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM saved_bank_details 
                WHERE user_id = ? AND is_primary = 1 LIMIT 1
            """, (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    # ================================================================
    # СТАТИСТИКА
    # ================================================================

    def get_user_stats(self, user_id: int) -> Dict[str, int]:
        """Отримати статистику збережених даних"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM family_members 
                WHERE user_id = ? AND member_type = ?
            """, (user_id, FamilyMemberType.CHILD))
            stats['children_count'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM saved_addresses WHERE user_id = ?", (user_id,))
            stats['addresses_count'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM saved_bank_details WHERE user_id = ?", (user_id,))
            stats['bank_accounts_count'] = cursor.fetchone()['count']
            
            return stats