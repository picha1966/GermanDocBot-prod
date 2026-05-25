# -*- coding: utf-8 -*-
"""
Drafts Manager - збереження та відновлення незавершених заповнень
Fault Tolerance: зберігає стан після кожного кроку
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from contextlib import contextmanager


class DraftsManager:
    """
    Менеджер чернеток для відновлення сесій
    Зберігає стан заповнення після кожного кроку
    """
    
    # Час життя чернетки (години)
    DRAFT_EXPIRY_HOURS = 72
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_drafts_table()
    
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
    
    def _init_drafts_table(self):
        """Створення таблиці чернеток"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    doc_type TEXT NOT NULL,
                    current_field_idx INTEGER DEFAULT 0,
                    total_fields INTEGER DEFAULT 0,
                    answers TEXT DEFAULT '{}',
                    lang TEXT DEFAULT 'ua',
                    is_completed INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    expires_at TEXT
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_drafts_active ON drafts(user_id, is_completed)')
    
    def save_draft(
        self,
        user_id: int,
        doc_type: str,
        current_field_idx: int,
        total_fields: int,
        answers: dict,
        lang: str = 'ua'
    ) -> int:
        """
        Зберегти чернетку після кожного кроку
        
        Args:
            user_id: ID користувача
            doc_type: Тип документа
            current_field_idx: Поточний індекс поля
            total_fields: Загальна кількість полів
            answers: Словник з відповідями
            lang: Мова користувача
            
        Returns:
            ID чернетки
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            expires = now + timedelta(hours=self.DRAFT_EXPIRY_HOURS)
            
            # Перевіряємо чи є активна чернетка
            cursor.execute(
                '''SELECT id FROM drafts 
                   WHERE user_id = ? AND doc_type = ? AND is_completed = 0
                   ORDER BY updated_at DESC LIMIT 1''',
                (user_id, doc_type)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Оновлюємо існуючу
                cursor.execute(
                    '''UPDATE drafts SET 
                       current_field_idx = ?, total_fields = ?, answers = ?,
                       lang = ?, updated_at = ?, expires_at = ?
                       WHERE id = ?''',
                    (current_field_idx, total_fields, json.dumps(answers, ensure_ascii=False),
                     lang, now.isoformat(), expires.isoformat(), existing['id'])
                )
                return existing['id']
            else:
                # Створюємо нову
                cursor.execute(
                    '''INSERT INTO drafts 
                       (user_id, doc_type, current_field_idx, total_fields, answers, lang, created_at, updated_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (user_id, doc_type, current_field_idx, total_fields,
                     json.dumps(answers, ensure_ascii=False), lang,
                     now.isoformat(), now.isoformat(), expires.isoformat())
                )
                return cursor.lastrowid
    
    def get_active_draft(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Отримати активну незавершену чернетку
        
        Args:
            user_id: ID користувача
            
        Returns:
            Словник з даними чернетки або None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute(
                '''SELECT * FROM drafts 
                   WHERE user_id = ? AND is_completed = 0 AND expires_at > ?
                   ORDER BY updated_at DESC LIMIT 1''',
                (user_id, now)
            )
            result = cursor.fetchone()
            
            if result:
                draft = dict(result)
                draft['answers'] = json.loads(draft['answers'] or '{}')
                return draft
            return None
    
    def get_draft_by_id(self, draft_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Отримати чернетку за ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT * FROM drafts WHERE id = ? AND user_id = ?',
                (draft_id, user_id)
            )
            result = cursor.fetchone()
            
            if result:
                draft = dict(result)
                draft['answers'] = json.loads(draft['answers'] or '{}')
                return draft
            return None
    
    def complete_draft(self, user_id: int, doc_type: str = None):
        """
        Позначити чернетку як завершену
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if doc_type:
                cursor.execute(
                    '''UPDATE drafts SET is_completed = 1, updated_at = ?
                       WHERE user_id = ? AND doc_type = ? AND is_completed = 0''',
                    (datetime.now().isoformat(), user_id, doc_type)
                )
            else:
                cursor.execute(
                    '''UPDATE drafts SET is_completed = 1, updated_at = ?
                       WHERE user_id = ? AND is_completed = 0''',
                    (datetime.now().isoformat(), user_id)
                )
    
    def delete_draft(self, draft_id: int, user_id: int) -> bool:
        """Видалити чернетку"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM drafts WHERE id = ? AND user_id = ?',
                (draft_id, user_id)
            )
            return cursor.rowcount > 0
    
    def delete_user_drafts(self, user_id: int):
        """Видалити всі чернетки користувача"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM drafts WHERE user_id = ?', (user_id,))
    
    def cleanup_expired(self):
        """Очистити застарілі чернетки"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            cursor.execute('DELETE FROM drafts WHERE expires_at < ?', (now,))
            return cursor.rowcount
    
    def get_draft_progress(self, draft: dict) -> dict:
        """
        Отримати інформацію про прогрес чернетки
        
        Returns:
            dict з progress_percent, filled_fields, remaining_fields
        """
        total = draft.get('total_fields', 1)
        current = draft.get('current_field_idx', 0)
        
        return {
            'progress_percent': int((current / total) * 100) if total > 0 else 0,
            'filled_fields': current,
            'remaining_fields': total - current,
            'total_fields': total
        }
    
    def format_resume_message(self, draft: dict, lang: str = 'ua') -> str:
        """
        Форматувати повідомлення про відновлення
        """
        progress = self.get_draft_progress(draft)
        doc_type = draft['doc_type'].capitalize()
        filled = progress['filled_fields']
        total = progress['total_fields']

        if lang == 'de':
            return (
                f"📋 <b>Unvollständiger Antrag gefunden!</b>\n\n"
                f"📄 Dokument: {doc_type}\n"
                f"✔ Ausgefüllt: {filled} von {total} Feldern\n"
                f"⏰ Letzte Bearbeitung: {draft['updated_at'][:16]}\n\n"
                f"Möchten Sie fortfahren?"
            )
        elif lang == 'en':
            return (
                f"📋 <b>Incomplete application found!</b>\n\n"
                f"📄 Document: {doc_type}\n"
                f"✔ Filled: {filled} of {total} fields\n"
                f"⏰ Last edited: {draft['updated_at'][:16]}\n\n"
                f"Would you like to continue?"
            )
        elif lang == 'pl':
            return (
                f"📋 <b>Znaleziono niezakończone wypełnienie!</b>\n\n"
                f"📄 Dokument: {doc_type}\n"
                f"✔ Wypełniono: {filled} z {total} pól\n"
                f"⏰ Ostatnia edycja: {draft['updated_at'][:16]}\n\n"
                f"Chcesz kontynuować?"
            )
        elif lang == 'tr':
            return (
                f"📋 <b>Tamamlanmamış başvuru bulundu!</b>\n\n"
                f"📄 Belge: {doc_type}\n"
                f"✔ Dolduruldu: {filled} / {total} alan\n"
                f"⏰ Son düzenleme: {draft['updated_at'][:16]}\n\n"
                f"Devam etmek ister misiniz?"
            )
        elif lang == 'ar':
            return (
                f"📋 <b>تم العثور على طلب غير مكتمل!</b>\n\n"
                f"📄 المستند: {doc_type}\n"
                f"✔ تم ملء: {filled} من {total} حقل\n"
                f"⏰ آخر تعديل: {draft['updated_at'][:16]}\n\n"
                f"هل تريد المتابعة؟"
            )
        elif lang == 'ru':
            return (
                f"📋 <b>Найдено незавершённое заполнение!</b>\n\n"
                f"📄 Документ: {doc_type}\n"
                f"✔ Заполнено: {filled} из {total} полей\n"
                f"⏰ Последнее редактирование: {draft['updated_at'][:16]}\n\n"
                f"Хотите продолжить?"
            )
        else:
            return (
                f"📋 <b>Знайдено незавершене заповнення!</b>\n\n"
                f"📄 Документ: {doc_type}\n"
                f"✔ Заповнено: {filled} з {total} полів\n"
                f"⏰ Останнє редагування: {draft['updated_at'][:16]}\n\n"
                f"Бажаєте продовжити?"
            )
