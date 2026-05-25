# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v4.5 - Error Reporter & Silent Crash Prevention
Централізована система обробки та звітування про помилки

ФУНКЦІОНАЛ:
- Відправка детальних звітів про помилки адміну в Telegram
- Включає User ID та крок на якому зупинився користувач
- Логування в файл для аналізу
- Cooldown щоб не спамити повідомленнями
"""

import os
import sys
import traceback
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List
from functools import wraps
from dataclasses import dataclass, field
import logging
import json

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ErrorContext:
    """Контекст помилки з детальною інформацією про користувача"""
    user_id: Optional[int] = None
    username: Optional[str] = None
    current_step: Optional[str] = None
    doc_type: Optional[str] = None
    field_name: Optional[str] = None
    user_input: Optional[str] = None
    state_data: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorReport:
    """Структура звіту про помилку"""
    error_id: str
    timestamp: str
    error_type: str
    error_message: str
    module: str
    function: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    current_step: Optional[str] = None
    doc_type: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    traceback_str: str = ""
    severity: str = "error"  # info, warning, error, critical
    
    def to_telegram_message(self) -> str:
        """
        Форматувати для Telegram повідомлення
        КРИТИЧНО: Включає User ID та крок для швидкої допомоги клієнту!
        """
        severity_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '❌',
            'critical': '🚨'
        }
        
        emoji = severity_emoji.get(self.severity, '❌')
        
        # Формуємо заголовок
        header = f"{emoji} <b>{'🚨 КРИТИЧНА ' if self.severity == 'critical' else ''}ПОМИЛКА #{self.error_id}</b>"
        
        message = f"""
{header}
{'═' * 32}

📅 <b>Час:</b> {self.timestamp}
🔴 <b>Тип:</b> <code>{self.error_type}</code>
📍 <b>Модуль:</b> {self.module}
🔧 <b>Функція:</b> {self.function}
"""
        
        # ⚠️ КРИТИЧНА ІНФОРМАЦІЯ ДЛЯ ДОПОМОГИ КЛІЄНТУ
        if self.user_id:
            message += f"\n👤 <b>USER ID:</b> <code>{self.user_id}</code>"
            if self.username:
                message += f" (@{self.username})"
        
        # КРОК НА ЯКОМУ ЗУПИНИВСЯ КОРИСТУВАЧ
        if self.current_step:
            message += f"\n📌 <b>КРОК:</b> <code>{self.current_step}</code>"
        
        if self.doc_type:
            message += f"\n📄 <b>Документ:</b> {self.doc_type}"
        
        # Повідомлення про помилку
        error_msg = self.error_message[:400] if len(self.error_message) > 400 else self.error_message
        message += f"""\n
💬 <b>Помилка:</b>
<code>{error_msg}</code>
"""
        
        # Контекст (скорочено)
        if self.context:
            # Фільтруємо важливу інформацію
            important_keys = ['step', 'field_name', 'user_input', 'action', 'callback_data']
            filtered_context = {k: v for k, v in self.context.items() if k in important_keys and v}
            
            if filtered_context:
                context_str = json.dumps(filtered_context, ensure_ascii=False, indent=2)[:250]
                message += f"""\n📋 <b>Контекст:</b>
<code>{context_str}</code>
"""
        
        # Traceback для серйозних помилок
        if self.traceback_str and self.severity in ['error', 'critical']:
            # Показуємо останні рядки traceback
            tb_lines = self.traceback_str.strip().split('\n')
            tb_short = '\n'.join(tb_lines[-6:]) if len(tb_lines) > 6 else self.traceback_str
            tb_short = tb_short[:400] if len(tb_short) > 400 else tb_short
            message += f"""\n🔍 <b>Traceback:</b>
<code>{tb_short}</code>
"""
        
        message += f"\n{'═' * 32}"
        
        # Додаємо підказку для швидкої дії
        if self.user_id:
            message += f"\n\n💡 <i>Щоб допомогти: надішліть /user {self.user_id}</i>"
        
        return message
    
    def to_log_entry(self) -> str:
        """Форматувати для лог-файлу (JSON)"""
        return json.dumps({
            'error_id': self.error_id,
            'timestamp': self.timestamp,
            'severity': self.severity,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'module': self.module,
            'function': self.function,
            'user_id': self.user_id,
            'username': self.username,
            'current_step': self.current_step,
            'doc_type': self.doc_type,
            'context': self.context,
            'traceback': self.traceback_str
        }, ensure_ascii=False)


class ErrorReporter:
    """
    Централізований репортер помилок
    
    Використання:
        from error_reporter import error_reporter
        
        # Ініціалізація (один раз при старті бота)
        error_reporter.initialize(bot, admin_ids=[907156976])
        
        # Звіт про помилку з контекстом користувача
        await error_reporter.report(
            exception,
            user_id=123,
            current_step='entering_birth_date',
            doc_type='kindergeld',
            context={'field_name': 'birth_date', 'user_input': 'abc'}
        )
        
        # Як декоратор
        @error_reporter.catch_errors(user_id_param='user_id')
        async def my_handler(user_id: int):
            ...
    """
    
    def __init__(self):
        self._bot = None
        self._admin_ids: List[int] = []
        self._error_count = 0
        self._last_notification_time: Dict[str, datetime] = {}
        self._cooldown_seconds = 30  # Зменшено для критичних помилок
        self._log_file = None
        self._is_initialized = False
        
    def initialize(
        self,
        bot,
        admin_ids: List[int],
        log_file: str = "logs/bot_errors.log",
        cooldown_seconds: int = 30
    ):
        """
        Ініціалізувати репортер
        
        Args:
            bot: Екземпляр aiogram Bot
            admin_ids: Список ID адміністраторів для сповіщень
            log_file: Шлях до файлу логів
            cooldown_seconds: Мінімальний інтервал між сповіщеннями
        """
        self._bot = bot
        self._admin_ids = admin_ids
        self._cooldown_seconds = cooldown_seconds
        self._log_file = log_file
        
        # Створюємо директорію для логів
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        self._is_initialized = True
        logger.info(f"ErrorReporter initialized. Admins: {admin_ids}, Log: {log_file}")
    
    def _generate_error_id(self) -> str:
        """Генерувати унікальний ID помилки"""
        self._error_count += 1
        timestamp = datetime.now().strftime('%m%d%H%M')
        return f"E{timestamp}{self._error_count:03d}"
    
    def _should_notify(self, error_key: str, severity: str) -> bool:
        """
        Перевірити чи можна надіслати сповіщення (cooldown)
        Критичні помилки завжди надсилаються!
        """
        if severity == 'critical':
            return True
        
        now = datetime.now()
        last_time = self._last_notification_time.get(error_key)
        
        if last_time is None:
            return True
        
        if (now - last_time).total_seconds() >= self._cooldown_seconds:
            return True
        
        return False
    
    def _log_to_file(self, report: ErrorReport):
        """Записати помилку в лог-файл"""
        if not self._log_file:
            return
        
        try:
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(report.to_log_entry() + '\n')
        except Exception as e:
            logger.error(f"Failed to write to log file: {e}")
    
    async def report(
        self,
        exception: Exception,
        user_id: int = None,
        username: str = None,
        current_step: str = None,
        doc_type: str = None,
        module: str = None,
        function: str = None,
        context: Dict[str, Any] = None,
        severity: str = "error",
        notify_admin: bool = True
    ) -> ErrorReport:
        """
        Звітувати про помилку
        
        Args:
            exception: Об'єкт винятку
            user_id: ID користувача (КРИТИЧНО!)
            username: Username користувача
            current_step: Крок на якому зупинився користувач (КРИТИЧНО!)
            doc_type: Тип документа
            module: Назва модуля
            function: Назва функції
            context: Додатковий контекст
            severity: Рівень серйозності (info, warning, error, critical)
            notify_admin: Чи надсилати сповіщення адміну
            
        Returns:
            ErrorReport об'єкт
        """
        # Отримуємо інформацію про виклик
        frame = sys._getframe(1)
        if not module:
            module = frame.f_globals.get('__name__', 'unknown')
        if not function:
            function = frame.f_code.co_name
        
        # Створюємо звіт
        report = ErrorReport(
            error_id=self._generate_error_id(),
            timestamp=datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            error_type=type(exception).__name__,
            error_message=str(exception),
            module=module,
            function=function,
            user_id=user_id,
            username=username,
            current_step=current_step,
            doc_type=doc_type,
            context=context or {},
            traceback_str=traceback.format_exc(),
            severity=severity
        )
        
        # Логуємо локально
        log_msg = f"[{report.error_id}] User:{user_id} Step:{current_step} - {report.error_type}: {report.error_message}"
        if severity == 'critical':
            logger.critical(log_msg)
        elif severity == 'error':
            logger.error(log_msg)
        else:
            logger.warning(log_msg)
        
        # Записуємо в файл
        self._log_to_file(report)
        
        # Надсилаємо адміну
        error_key = f"{report.error_type}:{module}:{function}"
        if notify_admin and self._is_initialized and self._should_notify(error_key, severity):
            await self._notify_admins(report)
            self._last_notification_time[error_key] = datetime.now()
        
        return report
    
    async def _notify_admins(self, report: ErrorReport):
        """Надіслати сповіщення адміністраторам"""
        if not self._bot or not self._admin_ids:
            logger.warning("Cannot notify admins: bot or admin_ids not set")
            return
        
        message = report.to_telegram_message()
        
        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(
                    admin_id,
                    message,
                    parse_mode="HTML"
                )
                logger.info(f"Error report sent to admin {admin_id}")
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    async def report_user_action_error(
        self,
        user_id: int,
        current_step: str,
        action: str,
        error_message: str,
        username: str = None,
        doc_type: str = None,
        user_input: str = None,
        context: Dict[str, Any] = None
    ):
        """
        Спрощений метод для звітування про помилки дій користувача
        
        ВИКОРИСТОВУЙТЕ ЦЕЙ МЕТОД для помилок під час заповнення форм!
        
        Args:
            user_id: ID користувача
            current_step: Крок де сталася помилка (напр. 'entering_birth_date')
            action: Дія (document_fill, payment, validation, etc.)
            error_message: Повідомлення про помилку
            username: Username користувача
            doc_type: Тип документа
            user_input: Що ввів користувач
            context: Додатковий контекст
        """
        full_context = {
            'step': current_step,
            'action': action,
            **(context or {})
        }
        if user_input:
            full_context['user_input'] = user_input[:100]  # Обмежуємо довжину
        
        report = ErrorReport(
            error_id=self._generate_error_id(),
            timestamp=datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            error_type="UserActionError",
            error_message=error_message,
            module="user_flow",
            function=action,
            user_id=user_id,
            username=username,
            current_step=current_step,
            doc_type=doc_type,
            context=full_context,
            severity="warning"
        )
        
        self._log_to_file(report)
        
        error_key = f"UserAction:{action}:{current_step}"
        if self._should_notify(error_key, "warning"):
            await self._notify_admins(report)
            self._last_notification_time[error_key] = datetime.now()
        
        return report
    
    def catch_errors(
        self,
        user_id_param: str = None,
        step_param: str = None,
        doc_type_param: str = None,
        severity: str = "error",
        reraise: bool = False,
        default_step: str = None
    ):
        """
        Декоратор для автоматичного перехоплення помилок
        
        Args:
            user_id_param: Назва параметра з user_id
            step_param: Назва параметра з поточним кроком
            doc_type_param: Назва параметра з типом документа
            severity: Рівень серйозності
            reraise: Чи піднімати виняток далі
            default_step: Дефолтний крок якщо не вдалося визначити
            
        Приклад:
            @error_reporter.catch_errors(
                user_id_param='user_id',
                step_param='current_step',
                default_step='unknown'
            )
            async def process_form(user_id: int, current_step: str):
                ...
        """
        def decorator(func: Callable):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Витягуємо параметри
                    uid = self._extract_param(func, args, kwargs, user_id_param)
                    step = self._extract_param(func, args, kwargs, step_param) or default_step
                    doc = self._extract_param(func, args, kwargs, doc_type_param)
                    
                    await self.report(
                        exception=e,
                        user_id=uid,
                        current_step=step,
                        doc_type=doc,
                        module=func.__module__,
                        function=func.__name__,
                        severity=severity
                    )
                    
                    if reraise:
                        raise
                    return None
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    uid = self._extract_param(func, args, kwargs, user_id_param)
                    step = self._extract_param(func, args, kwargs, step_param) or default_step
                    
                    # Для синхронних функцій
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.report(
                            exception=e,
                            user_id=uid,
                            current_step=step,
                            module=func.__module__,
                            function=func.__name__,
                            severity=severity
                        ))
                    
                    if reraise:
                        raise
                    return None
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    def _extract_param(self, func, args, kwargs, param_name):
        """Витягнути параметр з args/kwargs"""
        if not param_name:
            return None
        
        # Спробуємо з kwargs
        if param_name in kwargs:
            return kwargs[param_name]
        
        # Спробуємо з позиційних args
        try:
            import inspect
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if param_name in params:
                idx = params.index(param_name)
                if idx < len(args):
                    return args[idx]
        except:
            pass
        
        return None


# Глобальний екземпляр
error_reporter = ErrorReporter()


# ============================================================================
# HELPER DECORATORS
# ============================================================================

def safe_handler(default_step: str = 'handler'):
    """
    Декоратор для безпечних обробників повідомлень aiogram
    Автоматично витягує user_id з message.from_user
    
    Приклад:
        @dp.message_handler(commands=['start'])
        @safe_handler('cmd_start')
        async def cmd_start(message: types.Message):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Спробуємо отримати user_id та username з message
                user_id = None
                username = None
                for arg in args:
                    if hasattr(arg, 'from_user') and hasattr(arg.from_user, 'id'):
                        user_id = arg.from_user.id
                        username = getattr(arg.from_user, 'username', None)
                        break
                
                await error_reporter.report(
                    exception=e,
                    user_id=user_id,
                    username=username,
                    current_step=default_step,
                    module=func.__module__,
                    function=func.__name__,
                    severity="error"
                )
                
                # Намагаємось відповісти користувачу
                for arg in args:
                    if hasattr(arg, 'answer'):
                        try:
                            await arg.answer(
                                "❌ Виникла помилка. Наша команда вже працює над її вирішенням.",
                                parse_mode="HTML"
                            )
                        except:
                            pass
                        break
                
                return None
        
        return wrapper
    return decorator


def safe_callback(default_step: str = 'callback'):
    """
    Декоратор для безпечних callback handlers
    Включає callback_data в контекст
    
    Приклад:
        @dp.callback_query_handler(lambda c: c.data.startswith('doc_'))
        @safe_callback('doc_selection')
        async def process_doc_choice(callback_query: types.CallbackQuery):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(callback_query, *args, **kwargs):
            try:
                return await func(callback_query, *args, **kwargs)
            except Exception as e:
                user_id = callback_query.from_user.id if callback_query.from_user else None
                username = getattr(callback_query.from_user, 'username', None) if callback_query.from_user else None
                
                await error_reporter.report(
                    exception=e,
                    user_id=user_id,
                    username=username,
                    current_step=default_step,
                    context={'callback_data': callback_query.data},
                    module=func.__module__,
                    function=func.__name__,
                    severity="error"
                )
                
                try:
                    await callback_query.answer(
                        "❌ Помилка. Спробуйте ще раз.",
                        show_alert=True
                    )
                except:
                    pass
                
                return None
        
        return wrapper
    return decorator


def safe_state_handler(step_key: str = 'current_step'):
    """
    Декоратор для обробників з FSM State
    Витягує поточний крок зі state
    
    Приклад:
        @dp.message_handler(state=Form.waiting_for_field)
        @safe_state_handler()
        async def process_field(message: types.Message, state: FSMContext):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                user_id = None
                username = None
                current_step = None
                doc_type = None
                
                # Знаходимо message та state
                for arg in args:
                    if hasattr(arg, 'from_user'):
                        user_id = arg.from_user.id
                        username = getattr(arg.from_user, 'username', None)
                    
                    # FSMContext
                    if hasattr(arg, 'get_data'):
                        try:
                            data = await arg.get_data()
                            current_step = data.get(step_key, data.get('current_field_idx'))
                            doc_type = data.get('doc_type')
                        except:
                            pass
                
                await error_reporter.report(
                    exception=e,
                    user_id=user_id,
                    username=username,
                    current_step=str(current_step) if current_step else 'state_handler',
                    doc_type=doc_type,
                    module=func.__module__,
                    function=func.__name__,
                    severity="error"
                )
                
                # Відповідаємо користувачу
                for arg in args:
                    if hasattr(arg, 'answer'):
                        try:
                            await arg.answer(
                                "❌ Виникла помилка. Спробуйте ще раз або почніть з /start",
                                parse_mode="HTML"
                            )
                        except:
                            pass
                        break
                
                return None
        
        return wrapper
    return decorator
