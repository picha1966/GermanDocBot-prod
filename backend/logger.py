# -*- coding: utf-8 -*-
"""
Професійна система логування для GERMAN_DOC_BOT
Логування помилок у файл та консоль
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional
import traceback
import json

# Визначаємо шляхи
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_CURRENT_DIR)
_LOGS_DIR = os.path.join(_PARENT_DIR, 'logs')

# Створюємо папку для логів
os.makedirs(_LOGS_DIR, exist_ok=True)

# Шляхи до файлів логів
ERROR_LOG_FILE = os.path.join(_LOGS_DIR, 'bot_errors.log')
ACTIVITY_LOG_FILE = os.path.join(_LOGS_DIR, 'bot_activity.log')
DEBUG_LOG_FILE = os.path.join(_LOGS_DIR, 'bot_debug.log')


class BotLogger:
    """
    Централізована система логування для бота
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern - один екземпляр логера"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._setup_loggers()
    
    def _setup_loggers(self):
        """Налаштування всіх логерів"""
        
        # Формат для файлів
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Формат для консолі (кольоровий)
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # === ERROR LOGGER ===
        self.error_logger = logging.getLogger('bot.errors')
        self.error_logger.setLevel(logging.ERROR)
        self.error_logger.handlers = []  # Очищаємо старі хендлери
        
        # Ротація логів помилок: макс 5MB, зберігаємо 10 файлів
        error_handler = RotatingFileHandler(
            ERROR_LOG_FILE,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=10,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        self.error_logger.addHandler(error_handler)
        
        # === ACTIVITY LOGGER ===
        self.activity_logger = logging.getLogger('bot.activity')
        self.activity_logger.setLevel(logging.INFO)
        self.activity_logger.handlers = []
        
        # Ротація по дням, зберігаємо 30 днів
        activity_handler = TimedRotatingFileHandler(
            ACTIVITY_LOG_FILE,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        activity_handler.setLevel(logging.INFO)
        activity_handler.setFormatter(file_formatter)
        self.activity_logger.addHandler(activity_handler)
        
        # === DEBUG LOGGER ===
        self.debug_logger = logging.getLogger('bot.debug')
        self.debug_logger.setLevel(logging.DEBUG)
        self.debug_logger.handlers = []
        
        debug_handler = RotatingFileHandler(
            DEBUG_LOG_FILE,
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(file_formatter)
        self.debug_logger.addHandler(debug_handler)
        
        # === CONSOLE HANDLER ===
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        
        # Додаємо консоль до activity логера
        self.activity_logger.addHandler(console_handler)
    
    def log_error(
        self,
        error: Exception,
        user_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        context: Optional[dict] = None,
        include_traceback: bool = True
    ):
        """
        Логування помилки з повним контекстом
        
        Args:
            error: Об'єкт помилки
            user_id: ID користувача Telegram
            doc_type: Тип документа
            context: Додатковий контекст
            include_traceback: Включати повний traceback
        """
        error_data = {
            'timestamp': datetime.now().isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'user_id': user_id,
            'doc_type': doc_type,
            'context': context or {}
        }
        
        if include_traceback:
            error_data['traceback'] = traceback.format_exc()
        
        # Форматуємо повідомлення
        log_message = (
            f"\n{'='*60}\n"
            f"❌ ERROR OCCURRED\n"
            f"{'='*60}\n"
            f"User ID: {user_id}\n"
            f"Document Type: {doc_type}\n"
            f"Error Type: {type(error).__name__}\n"
            f"Error Message: {str(error)}\n"
        )
        
        if context:
            log_message += f"Context: {json.dumps(context, ensure_ascii=False, indent=2)}\n"
        
        if include_traceback:
            log_message += f"\nTraceback:\n{traceback.format_exc()}\n"
        
        log_message += f"{'='*60}\n"
        
        self.error_logger.error(log_message)
        
        # Також виводимо в консоль скорочену версію
        print(f"❌ ERROR: {type(error).__name__}: {str(error)} (User: {user_id})")
    
    def log_activity(
        self,
        action: str,
        user_id: Optional[int] = None,
        details: Optional[dict] = None
    ):
        """
        Логування активності користувача
        
        Args:
            action: Тип дії
            user_id: ID користувача
            details: Деталі дії
        """
        details_str = json.dumps(details, ensure_ascii=False) if details else ''
        message = f"ACTION: {action} | User: {user_id} | {details_str}"
        self.activity_logger.info(message)
    
    def log_document_generation(
        self,
        user_id: int,
        doc_type: str,
        success: bool,
        file_path: Optional[str] = None,
        error: Optional[str] = None,
        generation_time: Optional[float] = None
    ):
        """
        Логування генерації документа
        """
        status = "SUCCESS" if success else "FAILED"
        message = (
            f"DOCUMENT GENERATION | Status: {status} | "
            f"User: {user_id} | Type: {doc_type}"
        )
        
        if generation_time:
            message += f" | Time: {generation_time:.2f}s"
        
        if file_path:
            message += f" | File: {file_path}"
        
        if error:
            message += f" | Error: {error}"
        
        if success:
            self.activity_logger.info(message)
        else:
            self.error_logger.error(message)
    
    def log_payment(
        self,
        user_id: int,
        doc_id: int,
        amount: float,
        status: str,
        payment_id: Optional[str] = None
    ):
        """
        Логування платежу
        """
        message = (
            f"PAYMENT | User: {user_id} | Doc: {doc_id} | "
            f"Amount: {amount:.2f}€ | Status: {status}"
        )
        if payment_id:
            message += f" | Payment ID: {payment_id}"
        
        self.activity_logger.info(message)
    
    def log_validation_warning(
        self,
        user_id: int,
        field_name: str,
        original_value: str,
        suggestion: Optional[str] = None
    ):
        """
        Логування попередження валідації (кирилиця замість латиниці)
        """
        message = (
            f"VALIDATION WARNING | User: {user_id} | "
            f"Field: {field_name} | Original: '{original_value}'"
        )
        if suggestion:
            message += f" | Suggestion: '{suggestion}'"
        
        self.activity_logger.warning(message)
    
    def log_debug(self, message: str, data: Optional[dict] = None):
        """
        Debug логування
        """
        if data:
            message += f" | Data: {json.dumps(data, ensure_ascii=False)}"
        self.debug_logger.debug(message)


# Глобальний екземпляр логера
bot_logger = BotLogger()


# Зручні функції для швидкого доступу
def log_error(error: Exception, **kwargs):
    """Швидке логування помилки"""
    bot_logger.log_error(error, **kwargs)


def log_activity(action: str, **kwargs):
    """Швидке логування активності"""
    bot_logger.log_activity(action, **kwargs)


def log_document(user_id: int, doc_type: str, success: bool, **kwargs):
    """Швидке логування генерації документа"""
    bot_logger.log_document_generation(user_id, doc_type, success, **kwargs)
