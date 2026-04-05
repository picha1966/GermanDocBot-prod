# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - GDPR Data Shredder
========================================
Безпечне видалення персональних даних користувача.

Відповідність GDPR:
- Art. 17: Right to erasure ('right to be forgotten')
- Повне видалення даних з БД
- Видалення всіх згенерованих файлів
- Логування операцій видалення

Використання:
    from gdpr_shredder import shred_user_data
    result = await shred_user_data(user_id, bot)
"""

import os
import shutil
import logging
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

_CURRENT_FILE = os.path.abspath(__file__)
_BACKEND_DIR = os.path.dirname(_CURRENT_FILE)
_BASE_DIR = os.path.dirname(_BACKEND_DIR)

OUTPUT_DIR = os.path.join(_BASE_DIR, 'output')
LOGS_DIR = os.path.join(_BASE_DIR, 'logs')

# Директорії з даними користувачів
USER_DATA_DIRS = [
    OUTPUT_DIR,           # /output/{user_id}/
]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ShredResult:
    """Результат операції видалення"""
    success: bool
    user_id: int
    files_deleted: int
    db_records_deleted: int
    errors: List[str]
    timestamp: str
    
    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'user_id': self.user_id,
            'files_deleted': self.files_deleted,
            'db_records_deleted': self.db_records_deleted,
            'errors': self.errors,
            'timestamp': self.timestamp,
        }
    
    def format_message(self, lang: str = 'ua') -> str:
        """Форматоване повідомлення для користувача"""
        if self.success:
            messages = {
                'ua': (
                    "✅ <b>Ваші дані успішно видалено!</b>\n\n"
                    f"📁 Видалено файлів: {self.files_deleted}\n"
                    f"🗄 Видалено записів з БД: {self.db_records_deleted}\n"
                    f"🕐 Час: {self.timestamp}\n\n"
                    "<i>Відповідно до GDPR (Art. 17), всі ваші персональні дані "
                    "були безповоротно видалені з наших серверів.</i>"
                ),
                'de': (
                    "✅ <b>Ihre Daten wurden erfolgreich gelöscht!</b>\n\n"
                    f"📁 Gelöschte Dateien: {self.files_deleted}\n"
                    f"🗄 Gelöschte DB-Einträge: {self.db_records_deleted}\n"
                    f"🕐 Zeit: {self.timestamp}\n\n"
                    "<i>Gemäß DSGVO (Art. 17) wurden alle Ihre personenbezogenen Daten "
                    "unwiderruflich von unseren Servern gelöscht.</i>"
                ),
                'en': (
                    "✅ <b>Your data has been successfully deleted!</b>\n\n"
                    f"📁 Files deleted: {self.files_deleted}\n"
                    f"🗄 DB records deleted: {self.db_records_deleted}\n"
                    f"🕐 Time: {self.timestamp}\n\n"
                    "<i>In accordance with GDPR (Art. 17), all your personal data "
                    "has been permanently removed from our servers.</i>"
                ),
            }
            return messages.get(lang, messages['ua'])
        else:
            error_text = "\n".join(self.errors) if self.errors else "Unknown error"
            messages = {
                'ua': f"❌ <b>Помилка видалення даних</b>\n\n{error_text}",
                'de': f"❌ <b>Fehler beim Löschen der Daten</b>\n\n{error_text}",
                'en': f"❌ <b>Error deleting data</b>\n\n{error_text}",
            }
            return messages.get(lang, messages['ua'])


# ============================================================================
# FILE OPERATIONS
# ============================================================================

def get_user_files(user_id: int) -> List[str]:
    """
    Отримати список всіх файлів користувача.
    
    Returns:
        Список шляхів до файлів
    """
    files = []
    
    for base_dir in USER_DATA_DIRS:
        user_dir = os.path.join(base_dir, str(user_id))
        
        if os.path.exists(user_dir):
            for root, dirs, filenames in os.walk(user_dir):
                for filename in filenames:
                    files.append(os.path.join(root, filename))
    
    return files


def delete_user_files(user_id: int) -> Tuple[int, List[str]]:
    """
    Видалити всі файли користувача.
    
    Returns:
        Tuple[кількість видалених, список помилок]
    """
    deleted_count = 0
    errors = []
    
    for base_dir in USER_DATA_DIRS:
        user_dir = os.path.join(base_dir, str(user_id))
        
        if os.path.exists(user_dir):
            try:
                # Рахуємо файли перед видаленням
                for root, dirs, files in os.walk(user_dir):
                    deleted_count += len(files)
                
                # Видаляємо всю директорію
                shutil.rmtree(user_dir)
                logger.info(f"Deleted user directory: {user_dir}")
                
            except Exception as e:
                error_msg = f"Error deleting {user_dir}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
    
    return deleted_count, errors


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def delete_user_from_db(user_id: int, db) -> Tuple[int, List[str]]:
    """
    Видалити всі записи користувача з бази даних.
    
    Args:
        user_id: ID користувача
        db: Об'єкт бази даних
    
    Returns:
        Tuple[кількість видалених записів, список помилок]
    """
    deleted_count = 0
    errors = []
    
    # Таблиці для очищення
    tables = [
        ('profiles', 'user_id'),
        ('orders', 'user_id'),
        ('drafts', 'user_id'),
        ('family_members', 'user_id'),
        ('user_preferences', 'user_id'),
        ('analytics_events', 'user_id'),
    ]
    
    try:
        conn = db.get_connection() if hasattr(db, 'get_connection') else db.conn
        cursor = conn.cursor()
        
        for table_name, id_column in tables:
            try:
                # Перевіряємо чи таблиця існує
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if cursor.fetchone():
                    # Рахуємо записи
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {id_column} = ?", (user_id,))
                    count = cursor.fetchone()[0]
                    
                    # Видаляємо
                    cursor.execute(f"DELETE FROM {table_name} WHERE {id_column} = ?", (user_id,))
                    deleted_count += count
                    
                    logger.info(f"Deleted {count} records from {table_name} for user {user_id}")
                    
            except Exception as e:
                error_msg = f"Error deleting from {table_name}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Видаляємо з головної таблиці users
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if cursor.fetchone():
                cursor.execute("DELETE FROM users WHERE user_id = ? OR id = ?", (user_id, user_id))
                if cursor.rowcount > 0:
                    deleted_count += cursor.rowcount
                    logger.info(f"Deleted user {user_id} from users table")
        except Exception as e:
            error_msg = f"Error deleting from users: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
        
        conn.commit()
        
    except Exception as e:
        error_msg = f"Database error: {e}"
        logger.error(error_msg, exc_info=True)
        errors.append(error_msg)
    
    return deleted_count, errors


# ============================================================================
# MAIN SHREDDER FUNCTION
# ============================================================================

async def shred_user_data(
    user_id: int,
    db=None,
    notify_admin: bool = True,
    admin_ids: List[int] = None,
    bot=None
) -> ShredResult:
    """
    Повне видалення всіх персональних даних користувача.
    
    GDPR Art. 17 - Right to erasure:
    1. Видалення всіх файлів (PDF, JPEG, etc.)
    2. Видалення з бази даних
    3. Логування операції
    4. Сповіщення адміна (опційно)
    
    Args:
        user_id: ID користувача Telegram
        db: Об'єкт бази даних
        notify_admin: Сповістити адмінів
        admin_ids: Список ID адмінів
        bot: Об'єкт бота для сповіщень
    
    Returns:
        ShredResult з деталями операції
    """
    logger.info(f"=" * 60)
    logger.info(f"GDPR DATA SHREDDER: Starting for user {user_id}")
    logger.info(f"=" * 60)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    errors = []
    
    # 1. Видаляємо файли
    logger.info("Step 1: Deleting user files...")
    files_deleted, file_errors = delete_user_files(user_id)
    errors.extend(file_errors)
    logger.info(f"Files deleted: {files_deleted}")
    
    # 2. Видаляємо з БД
    db_records_deleted = 0
    if db:
        logger.info("Step 2: Deleting database records...")
        db_records_deleted, db_errors = delete_user_from_db(user_id, db)
        errors.extend(db_errors)
        logger.info(f"DB records deleted: {db_records_deleted}")
    else:
        logger.warning("Step 2: Skipped (no database connection)")
    
    # 3. Логуємо операцію
    success = len(errors) == 0
    
    log_entry = {
        'timestamp': timestamp,
        'user_id': user_id,
        'files_deleted': files_deleted,
        'db_records_deleted': db_records_deleted,
        'success': success,
        'errors': errors,
    }
    
    logger.info(f"GDPR Shredder Result: {log_entry}")
    
    # Зберігаємо в файл логу
    gdpr_log_path = os.path.join(LOGS_DIR, 'gdpr_deletions.log')
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    try:
        with open(gdpr_log_path, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp} | User {user_id} | Files: {files_deleted} | DB: {db_records_deleted} | Success: {success}\n")
    except Exception as e:
        logger.error(f"Could not write to GDPR log: {e}")
    
    # 4. Сповіщення адмінів
    if notify_admin and admin_ids and bot:
        admin_message = (
            f"🗑 <b>GDPR Data Deletion</b>\n\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Files deleted: {files_deleted}\n"
            f"DB records deleted: {db_records_deleted}\n"
            f"Status: {'✅ Success' if success else '❌ Errors'}\n"
            f"Time: {timestamp}"
        )
        
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, admin_message, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Could not notify admin {admin_id}: {e}")
    
    logger.info(f"=" * 60)
    logger.info(f"GDPR DATA SHREDDER: Completed for user {user_id}")
    logger.info(f"=" * 60)
    
    return ShredResult(
        success=success,
        user_id=user_id,
        files_deleted=files_deleted,
        db_records_deleted=db_records_deleted,
        errors=errors,
        timestamp=timestamp
    )


# ============================================================================
# INLINE KEYBOARD FOR TELEGRAM
# ============================================================================

def get_gdpr_delete_keyboard(lang: str = 'ua'):
    """
    Створити InlineKeyboard для видалення даних.
    Повертає дані для конструктора.
    """
    texts = {
        'ua': {
            'delete': "⚠️ Видалити мої персональні дані",
            'cancel': "❌ Скасувати",
            'confirm': "✅ Так, видалити назавжди",
        },
        'de': {
            'delete': "⚠️ Meine Daten löschen",
            'cancel': "❌ Abbrechen",
            'confirm': "✅ Ja, endgültig löschen",
        },
        'en': {
            'delete': "⚠️ Delete my personal data",
            'cancel': "❌ Cancel",
            'confirm': "✅ Yes, delete permanently",
        },
    }
    return texts.get(lang, texts['ua'])


def get_gdpr_confirmation_text(lang: str = 'ua') -> str:
    """Текст підтвердження видалення"""
    texts = {
        'ua': (
            "⚠️ <b>УВАГА: Видалення даних</b>\n\n"
            "Ви збираєтесь <b>назавжди видалити</b> всі ваші персональні дані:\n\n"
            "• Профіль та анкети\n"
            "• Історію замовлень\n"
            "• Всі згенеровані документи (PDF)\n"
            "• Превью файли\n\n"
            "❗ <b>Ця дія незворотня!</b>\n\n"
            "Ви впевнені?"
        ),
        'de': (
            "⚠️ <b>ACHTUNG: Datenlöschung</b>\n\n"
            "Sie sind dabei, alle Ihre personenbezogenen Daten <b>dauerhaft zu löschen</b>:\n\n"
            "• Profil und Formulare\n"
            "• Bestellhistorie\n"
            "• Alle erstellten Dokumente (PDF)\n"
            "• Vorschau-Dateien\n\n"
            "❗ <b>Diese Aktion kann nicht rückgängig gemacht werden!</b>\n\n"
            "Sind Sie sicher?"
        ),
        'en': (
            "⚠️ <b>WARNING: Data Deletion</b>\n\n"
            "You are about to <b>permanently delete</b> all your personal data:\n\n"
            "• Profile and forms\n"
            "• Order history\n"
            "• All generated documents (PDF)\n"
            "• Preview files\n\n"
            "❗ <b>This action cannot be undone!</b>\n\n"
            "Are you sure?"
        ),
    }
    return texts.get(lang, texts['ua'])


# ============================================================================
# TEST
# ============================================================================

if __name__ == '__main__':
    import asyncio
    
    print("=" * 60)
    print("GDPR Data Shredder Test")
    print("=" * 60)
    
    # Create test user directory
    test_user_id = 999999
    test_dir = os.path.join(OUTPUT_DIR, str(test_user_id))
    os.makedirs(test_dir, exist_ok=True)
    
    # Create test files
    test_file = os.path.join(test_dir, 'test_document.pdf')
    with open(test_file, 'w') as f:
        f.write('Test content')
    
    print(f"\n1. Created test directory: {test_dir}")
    print(f"   Test file: {test_file}")
    print(f"   Exists: {os.path.exists(test_file)}")
    
    # Test shredder
    async def test():
        result = await shred_user_data(test_user_id, db=None, notify_admin=False)
        return result
    
    result = asyncio.run(test())
    
    print(f"\n2. Shredder Result:")
    print(f"   Success: {result.success}")
    print(f"   Files deleted: {result.files_deleted}")
    print(f"   Directory exists: {os.path.exists(test_dir)}")
    
    print("\n" + "=" * 60)
