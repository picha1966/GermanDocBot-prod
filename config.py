# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - Centralized Configuration
Єдине місце для всіх налаштувань бота.

СТРУКТУРА ПАПОК:
/ (корінь)           — main.py, config.py
/handlers/           — documents.py, start.py, menu_handler.py
/backend/            — pdf_generator.py, document_handlers.py
/backend/templates/  — PDF шаблони (anmeldung.pdf, kindergeld.pdf, ...)
/backend/schemas/    — universal_mapping.json
/output/             — готові файли користувачів (/output/{user_id}/)
"""

import os
import sys
import logging

# ============================================================================
# ШЛЯХИ
# ============================================================================

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, 'backend')
HANDLERS_DIR = os.path.join(ROOT_DIR, 'handlers')

# Backend subdirectories
TEMPLATES_DIR = os.path.join(BACKEND_DIR, 'templates')     # PDF шаблони
SCHEMAS_DIR = os.path.join(BACKEND_DIR, 'schemas')         # JSON схеми
SCHEMA_FILE = os.path.join(SCHEMAS_DIR, 'universal_mapping.json')

# Output directory structure: /output/{user_id}/{doc_type}.pdf
OUTPUT_DIR = os.path.join(ROOT_DIR, 'output')

# Other directories
LOGS_DIR = os.path.join(ROOT_DIR, 'logs')
TEMP_PDF_DIR = os.path.join(ROOT_DIR, 'temp_pdf')
FONTS_DIR = os.path.join(ROOT_DIR, 'fonts')
WEBAPP_DIR = os.path.join(ROOT_DIR, 'webapp')

# Legacy paths (for backward compatibility)
DOCS_DIR = OUTPUT_DIR
PREVIEWS_DIR = OUTPUT_DIR

# Створюємо папки автоматично
REQUIRED_DIRS = [
    BACKEND_DIR, HANDLERS_DIR, TEMPLATES_DIR, SCHEMAS_DIR,
    OUTPUT_DIR, LOGS_DIR, TEMP_PDF_DIR, FONTS_DIR, WEBAPP_DIR
]
for folder in REQUIRED_DIRS:
    os.makedirs(folder, exist_ok=True)

# Додаємо шляхи до Python path.
# ROOT_DIR must always have higher priority than BACKEND_DIR so that the
# root-level utils/ package is found before backend/utils/.
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)

# ============================================================================
# ІМПОРТ НАЛАШТУВАНЬ З BACKEND
# ============================================================================

try:
    from settings import settings, get_admin_ids
except ImportError:
    from backend.settings import settings, get_admin_ids

# ============================================================================
# BOT CONFIGURATION
# ============================================================================

API_TOKEN = settings.bot.API_TOKEN
BOT_USERNAME = settings.bot.BOT_USERNAME
# Admin IDs from settings (single source of truth)
ADMIN_IDS = get_admin_ids()
SUPPORT_GROUP = getattr(settings.bot, 'SUPPORT_GROUP', None)
NEWS_CHANNEL = getattr(settings.bot, 'NEWS_CHANNEL', None)

# Нові налаштування сповіщень
NOTIFY_ADMIN_ON_ERROR = True
NOTIFY_ADMIN_ON_ORDER = True
ERROR_NOTIFICATION_COOLDOWN = 300  # 5 хвилин

# ============================================================================
# WEBAPP CONFIGURATION
# ============================================================================

# URL для Telegram WebApp (HTTPS обов'язково!)
# CRITICAL: This MUST point to the NEW multi-language form (webapp/index.html)
# NOT the old Ukrainian-only form. The new form supports 6 languages with radio buttons.
# OLD URL (DISABLED): "https://picha1966.github.io/germany-form"
# Production URL: Load from environment variable WEBAPP_URL
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://termin-assist.de/form")
# ============================================================================
# PRICING
# ============================================================================

REFERRAL_BONUS_PERCENT = getattr(settings.pricing, 'REFERRAL_BONUS_PERCENT', 10)

# ============================================================================
# DATABASE
# ============================================================================

DB_PATH = os.path.join(ROOT_DIR, "bot_database.db")

# ============================================================================
# LOGGING
# ============================================================================

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = logging.INFO

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# ============================================================================
# SUPPORTED LANGUAGES
# ============================================================================

SUPPORTED_LANGUAGES = ['ua', 'de', 'en', 'pl', 'tr', 'ar']
RTL_LANGUAGES = ['ar']
DEFAULT_LANGUAGE = 'ua'

LANGUAGE_FLAGS = {
    'ua': '🇺🇦',
    'de': '🇩🇪',
    'en': '🇬🇧',
    'pl': '🇵🇱',
    'tr': '🇹🇷',
    'ar': '🇸🇦'
}

LANGUAGE_NAMES = {
    'ua': 'Українська',
    'de': 'Deutsch',
    'en': 'English',
    'pl': 'Polski',
    'tr': 'Türkçe',
    'ar': 'العربية'
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# ============================================================================
# TERMIN MONITOR
# ============================================================================

# Primary admin who receives Termin checker alerts.
# Must be a valid Telegram user_id. Set via env var for flexibility.
ADMIN_ID: int = int(os.getenv("ADMIN_ID", "402229082"))

# How often (in minutes) the monitor loop checks all 5 Premium cities.
MONITOR_INTERVAL_MIN: int = int(os.getenv("MONITOR_INTERVAL_MIN", "60"))

# How many consecutive failures before an alert is sent.
TERMIN_ALERT_THRESHOLD: int = int(os.getenv("TERMIN_ALERT_THRESHOLD", "3"))

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_admin(user_id: int) -> bool:
    """Перевірка чи користувач є адміном"""
    return user_id in ADMIN_IDS


# ---------------------------------------------------------------------------
# Dev-client mode: admin tests onboarding flow without receiving system alerts
# ---------------------------------------------------------------------------
_DEV_CLIENT_MODE_USERS: set = set()


def enter_dev_client_mode(user_id: int) -> None:
    """Suppress admin alerts for user_id (called by /dev_new)."""
    _DEV_CLIENT_MODE_USERS.add(user_id)


def exit_dev_client_mode(user_id: int) -> None:
    """Restore admin alerts for user_id (called by /start or /dev_admin)."""
    _DEV_CLIENT_MODE_USERS.discard(user_id)


def is_dev_client_mode(user_id: int) -> bool:
    """Return True if this admin is currently simulating a new-user session."""
    return user_id in _DEV_CLIENT_MODE_USERS


def get_webapp_url() -> str:
    """Отримати URL для WebApp"""
    return WEBAPP_URL


def get_user_output_dir(user_id: int) -> str:
    """
    Отримати директорію для збереження файлів користувача.
    Структура: /output/{user_id}/
    """
    user_dir = os.path.join(OUTPUT_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def get_output_path(user_id: int, doc_type: str, suffix: str = '') -> str:
    """
    Отримати повний шлях для збереження файлу.
    Приклад: /output/123456/kindergeld.pdf або /output/123456/kindergeld_preview.jpg
    """
    user_dir = get_user_output_dir(user_id)
    filename = f"{doc_type}{suffix}"
    return os.path.join(user_dir, filename)
async def notify_admins(bot, message, error_type=None):
    """Сповіщення адміністраторів про події або помилки"""
    from settings import settings
    for admin_id in settings.bot.ADMIN_IDS:
        if is_dev_client_mode(admin_id):
            continue
        try:
            await bot.send_message(admin_id, message, parse_mode="HTML")
        except Exception as e:
            print(f"Не вдалося надіслати сповіщення адміну {admin_id}: {e}")

def format_error_message(error, context, include_traceback=True):
    """Форматування тексту помилки для адміна"""
    import traceback
    msg = f"❌ <b>Критична помилка!</b>\n\n"
    msg += f"<b>Тип:</b> {type(error).__name__}\n"
    msg += f"<b>Опис:</b> {str(error)}\n"
    msg += f"<b>Контекст:</b> {context}\n"
    if include_traceback:
        msg += f"\n<b>Traceback:</b>\n<code>{traceback.format_exc()[-500:]}</code>"
    return msg

def format_order_notification(order_id, user_id, doc_type, price, status):
    """Форматування сповіщення про замовлення"""
    return (f"💰 <b>Нове замовлення #{order_id}</b>\n"
            f"👤 Користувач: {user_id}\n"
            f"📄 Документ: {doc_type}\n"
            f"💶 Ціна: {price} EUR\n"
            f"📊 Статус: {status}")
