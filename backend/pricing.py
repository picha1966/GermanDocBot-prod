# -*- coding: utf-8 -*-
"""
Pricing Manager - динамічне управління цінами
Admin Price Control: ціни зберігаються в БД і можуть змінюватися онлайн
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any
from contextlib import contextmanager
from decimal import Decimal

# Single source of truth — never define prices here directly.
from bot_config.pricing import PDF_PRICES


class PricingManager:
    """
    Менеджер цін з підтримкою:
    - Базових цін на документи
    - Промокодів та знижок
    - Реферальної програми
    - Історії змін цін
    """

    # Delegate to bot_config.pricing — single source of truth.
    DEFAULT_PRICES = PDF_PRICES
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_pricing_tables()
    
    @contextmanager
    def _get_connection(self):
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
    
    def _init_pricing_tables(self):
        """Створення таблиць для цін та промокодів"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблиця цін на документи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_type TEXT UNIQUE NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT DEFAULT 'EUR',
                    is_active INTEGER DEFAULT 1,
                    description TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # Історія змін цін
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_type TEXT NOT NULL,
                    old_price REAL,
                    new_price REAL NOT NULL,
                    changed_by INTEGER,
                    reason TEXT,
                    created_at TEXT
                )
            ''')
            
            # Промокоди
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    discount_type TEXT NOT NULL,
                    discount_value REAL NOT NULL,
                    max_uses INTEGER DEFAULT NULL,
                    current_uses INTEGER DEFAULT 0,
                    valid_from TEXT,
                    valid_until TEXT,
                    applicable_docs TEXT DEFAULT '[]',
                    min_order_amount REAL DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_by INTEGER,
                    created_at TEXT
                )
            ''')
            
            # Використання промокодів
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS promo_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    promo_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    order_id INTEGER,
                    discount_amount REAL,
                    used_at TEXT,
                    FOREIGN KEY (promo_id) REFERENCES promo_codes(id)
                )
            ''')
            
            # Реферальна програма
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER NOT NULL UNIQUE,
                    referral_code TEXT,
                    bonus_given INTEGER DEFAULT 0,
                    bonus_amount REAL DEFAULT 0,
                    created_at TEXT
                )
            ''')
            
            # Ініціалізуємо дефолтні ціни
            for doc_type, price in self.DEFAULT_PRICES.items():
                cursor.execute(
                    '''INSERT OR IGNORE INTO prices (doc_type, price, created_at, updated_at)
                       VALUES (?, ?, ?, ?)''',
                    (doc_type, price, datetime.now().isoformat(), datetime.now().isoformat())
                )
    
    # ==================== ЦІНИ ====================
    
    def get_price(self, doc_type: str) -> float:
        """
        Отримати поточну ціну документа
        
        Args:
            doc_type: Тип документа
            
        Returns:
            Ціна або дефолтна ціна
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT price FROM prices WHERE doc_type = ? AND is_active = 1',
                (doc_type,)
            )
            result = cursor.fetchone()
            
            if result:
                return float(result['price'])
            return self.DEFAULT_PRICES.get(doc_type, 0.0)
    
    def get_all_prices(self) -> Dict[str, float]:
        """Отримати всі активні ціни"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT doc_type, price FROM prices WHERE is_active = 1')
            return {row['doc_type']: float(row['price']) for row in cursor.fetchall()}
    
    def update_price(
        self,
        doc_type: str,
        new_price: float,
        admin_id: int = None,
        reason: str = None
    ) -> bool:
        """
        Оновити ціну документа (адмін-функція)
        
        Args:
            doc_type: Тип документа
            new_price: Нова ціна
            admin_id: ID адміна
            reason: Причина зміни
            
        Returns:
            True якщо успішно
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Отримуємо стару ціну
            cursor.execute('SELECT price FROM prices WHERE doc_type = ?', (doc_type,))
            result = cursor.fetchone()
            old_price = result['price'] if result else None
            
            # Оновлюємо або створюємо
            cursor.execute(
                '''INSERT INTO prices (doc_type, price, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(doc_type) DO UPDATE SET 
                   price = excluded.price, updated_at = excluded.updated_at''',
                (doc_type, new_price, now, now)
            )
            
            # Записуємо в історію
            cursor.execute(
                '''INSERT INTO price_history (doc_type, old_price, new_price, changed_by, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (doc_type, old_price, new_price, admin_id, reason, now)
            )
            
            return True
    
    def get_price_history(self, doc_type: str = None, limit: int = 50) -> List[dict]:
        """Отримати історію змін цін"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if doc_type:
                cursor.execute(
                    '''SELECT * FROM price_history 
                       WHERE doc_type = ? ORDER BY created_at DESC LIMIT ?''',
                    (doc_type, limit)
                )
            else:
                cursor.execute(
                    'SELECT * FROM price_history ORDER BY created_at DESC LIMIT ?',
                    (limit,)
                )
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== ПРОМОКОДИ ====================
    
    def create_promo_code(
        self,
        code: str,
        discount_type: str,  # 'percent' або 'fixed'
        discount_value: float,
        max_uses: int = None,
        valid_days: int = 30,
        applicable_docs: List[str] = None,
        min_order_amount: float = 0,
        created_by: int = None
    ) -> int:
        """
        Створити промокод
        
        Args:
            code: Код (наприклад, WELCOME20)
            discount_type: 'percent' або 'fixed'
            discount_value: Значення знижки (20 для 20% або 5 для 5€)
            max_uses: Максимальна кількість використань
            valid_days: Термін дії в днях
            applicable_docs: Список документів для яких діє
            min_order_amount: Мінімальна сума замовлення
            created_by: ID адміна
            
        Returns:
            ID промокоду
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            valid_until = now + timedelta(days=valid_days) if valid_days else None
            
            cursor.execute(
                '''INSERT INTO promo_codes 
                   (code, discount_type, discount_value, max_uses, valid_from, valid_until,
                    applicable_docs, min_order_amount, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (code.upper(), discount_type, discount_value, max_uses,
                 now.isoformat(), valid_until.isoformat() if valid_until else None,
                 json.dumps(applicable_docs or []), min_order_amount, created_by, now.isoformat())
            )
            
            return cursor.lastrowid
    
    def validate_promo_code(
        self,
        code: str,
        user_id: int,
        doc_type: str = None,
        order_amount: float = 0
    ) -> Dict[str, Any]:
        """
        Перевірити промокод
        
        Returns:
            {'valid': bool, 'discount': float, 'message': str, 'promo_id': int}
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute(
                '''SELECT * FROM promo_codes 
                   WHERE code = ? AND is_active = 1''',
                (code.upper(),)
            )
            promo = cursor.fetchone()
            
            if not promo:
                return {'valid': False, 'discount': 0, 'message': 'Промокод не знайдено', 'promo_id': None}
            
            promo = dict(promo)
            
            # Перевірка терміну дії
            if promo['valid_until'] and promo['valid_until'] < now:
                return {'valid': False, 'discount': 0, 'message': 'Промокод прострочений', 'promo_id': None}
            
            if promo['valid_from'] and promo['valid_from'] > now:
                return {'valid': False, 'discount': 0, 'message': 'Промокод ще не активний', 'promo_id': None}
            
            # Перевірка ліміту використань
            if promo['max_uses'] and promo['current_uses'] >= promo['max_uses']:
                return {'valid': False, 'discount': 0, 'message': 'Ліміт використань вичерпано', 'promo_id': None}
            
            # Перевірка чи користувач вже використовував
            cursor.execute(
                'SELECT id FROM promo_usage WHERE promo_id = ? AND user_id = ?',
                (promo['id'], user_id)
            )
            if cursor.fetchone():
                return {'valid': False, 'discount': 0, 'message': 'Ви вже використали цей промокод', 'promo_id': None}
            
            # Перевірка мінімальної суми
            if order_amount < promo['min_order_amount']:
                return {
                    'valid': False, 'discount': 0,
                    'message': f"Мінімальна сума замовлення: {promo['min_order_amount']}€",
                    'promo_id': None
                }
            
            # Перевірка застосовності до документа
            applicable = json.loads(promo['applicable_docs'] or '[]')
            if applicable and doc_type and doc_type not in applicable:
                return {'valid': False, 'discount': 0, 'message': 'Промокод не діє для цього документа', 'promo_id': None}
            
            # Розраховуємо знижку
            if promo['discount_type'] == 'percent':
                discount = order_amount * (promo['discount_value'] / 100)
            else:
                discount = min(promo['discount_value'], order_amount)
            
            return {
                'valid': True,
                'discount': round(discount, 2),
                'message': f"Знижка {promo['discount_value']}{'%' if promo['discount_type'] == 'percent' else '€'}",
                'promo_id': promo['id']
            }
    
    def apply_promo_code(
        self,
        promo_id: int,
        user_id: int,
        order_id: int,
        discount_amount: float
    ):
        """Застосувати промокод (після успішної оплати)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Записуємо використання
            cursor.execute(
                '''INSERT INTO promo_usage (promo_id, user_id, order_id, discount_amount, used_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (promo_id, user_id, order_id, discount_amount, now)
            )
            
            # Збільшуємо лічильник
            cursor.execute(
                'UPDATE promo_codes SET current_uses = current_uses + 1 WHERE id = ?',
                (promo_id,)
            )
    
    # ==================== РЕФЕРАЛЬНА ПРОГРАМА ====================
    
    def create_referral_code(self, user_id: int) -> str:
        """
        Створити реферальний код для користувача
        
        Returns:
            Реферальний код
        """
        import hashlib
        code = f"REF{hashlib.md5(str(user_id).encode()).hexdigest()[:8].upper()}"
        return code
    
    def register_referral(
        self,
        referrer_id: int,
        referred_id: int,
        referral_code: str = None
    ) -> bool:
        """
        Зареєструвати реферала
        
        Args:
            referrer_id: ID того хто запросив
            referred_id: ID запрошеного
            referral_code: Реферальний код
            
        Returns:
            True якщо успішно
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Перевіряємо чи referred_id ще не зареєстрований
            cursor.execute(
                'SELECT id FROM referrals WHERE referred_id = ?',
                (referred_id,)
            )
            if cursor.fetchone():
                return False
            
            # Не можна запросити себе
            if referrer_id == referred_id:
                return False
            
            cursor.execute(
                '''INSERT INTO referrals (referrer_id, referred_id, referral_code, created_at)
                   VALUES (?, ?, ?, ?)''',
                (referrer_id, referred_id, referral_code, datetime.now().isoformat())
            )
            
            return True
    
    def get_referrer(self, user_id: int) -> Optional[int]:
        """Отримати ID того хто запросив користувача"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT referrer_id FROM referrals WHERE referred_id = ?',
                (user_id,)
            )
            result = cursor.fetchone()
            return result['referrer_id'] if result else None
    
    def get_referrals(self, user_id: int) -> List[dict]:
        """Отримати список рефералів користувача"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT r.*, u.username, u.first_name 
                   FROM referrals r
                   LEFT JOIN users u ON r.referred_id = u.user_id
                   WHERE r.referrer_id = ?
                   ORDER BY r.created_at DESC''',
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_referral_stats(self, user_id: int) -> dict:
        """Отримати статистику рефералів"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT COUNT(*) as total FROM referrals WHERE referrer_id = ?',
                (user_id,)
            )
            total = cursor.fetchone()['total']
            
            cursor.execute(
                '''SELECT SUM(bonus_amount) as total_bonus 
                   FROM referrals WHERE referrer_id = ? AND bonus_given = 1''',
                (user_id,)
            )
            total_bonus = cursor.fetchone()['total_bonus'] or 0
            
            return {
                'total_referrals': total,
                'total_bonus': total_bonus,
                'referral_code': self.create_referral_code(user_id)
            }
    
    def give_referral_bonus(
        self,
        referrer_id: int,
        referred_id: int,
        bonus_amount: float = 2.0
    ):
        """Нарахувати бонус за реферала (після першої покупки)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''UPDATE referrals SET bonus_given = 1, bonus_amount = ?
                   WHERE referrer_id = ? AND referred_id = ?''',
                (bonus_amount, referrer_id, referred_id)
            )


# Імпорт timedelta
from datetime import timedelta
