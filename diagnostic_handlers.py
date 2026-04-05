# ============================================================================
# КРИТИЧНА ДІАГНОСТИКА: ПЕРЕХОПЛЕННЯ ВСІХ ПОВІДОМЛЕНЬ
# ============================================================================
# Помістіть цей код на САМИЙ ПОЧАТОК bot.py або main.py
# ПЕРЕД усіма іншими handlers!

from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
import json
from datetime import datetime

# ============================================================================
# MIDDLEWARE ДЛЯ ЛОГУВАННЯ ВСІХ ПОВІДОМЛЕНЬ
# ============================================================================

class DebugLoggingMiddleware(BaseMiddleware):
    """
    Middleware що логує ВСІ повідомлення ДО обробки handlers.
    Помістіть це middleware ПЕРШИМ, щоб бачити що взагалі приходить.
    """
    
    async def on_pre_process_message(self, message: types.Message, data: dict):
        """Викликається ДО обробки повідомлення"""
        print("\n" + "=" * 80)
        print("🔍 MIDDLEWARE: PRE-PROCESS MESSAGE")
        print("=" * 80)
        print(f"📥 Time: {datetime.now().strftime('%H:%M:%S.%f')}")
        print(f"📥 User ID: {message.from_user.id}")
        print(f"📥 Chat ID: {message.chat.id}")
        print(f"📥 Content Type: {message.content_type}")
        print(f"📥 Message ID: {message.message_id}")
        
        # КРИТИЧНО ВАЖЛИВО: Перевірка web_app_data
        if hasattr(message, 'web_app_data') and message.web_app_data:
            print("🔥🔥🔥 WEB_APP_DATA DETECTED! 🔥🔥🔥")
            print(f"📦 web_app_data exists: True")
            print(f"📦 web_app_data.data length: {len(message.web_app_data.data)}")
            print(f"📦 web_app_data.data preview:")
            print(message.web_app_data.data[:500])
            print(f"📦 web_app_data.button_text: {getattr(message.web_app_data, 'button_text', 'N/A')}")
        else:
            print(f"⚠️ web_app_data: None")
        
        # Додаткова інформація
        print(f"📥 Text: {message.text if message.text else 'None'}")
        print(f"📥 Caption: {message.caption if message.caption else 'None'}")
        
        # Всі атрибути повідомлення
        print(f"\n📋 ALL MESSAGE ATTRIBUTES:")
        for attr in dir(message):
            if not attr.startswith('_') and not callable(getattr(message, attr)):
                try:
                    value = getattr(message, attr)
                    if value is not None:
                        print(f"   {attr}: {str(value)[:100]}")
                except:
                    pass
        
        print("=" * 80 + "\n")
    
    async def on_post_process_message(self, message: types.Message, results, data: dict):
        """Викликається ПІСЛЯ обробки повідомлення"""
        print("\n" + "=" * 80)
        print("✅ MIDDLEWARE: POST-PROCESS MESSAGE")
        print("=" * 80)
        print(f"📤 User ID: {message.from_user.id}")
        print(f"📤 Content Type: {message.content_type}")
        print(f"📤 Results: {results}")
        print("=" * 80 + "\n")


# ============================================================================
# УНІВЕРСАЛЬНИЙ HANDLER ДЛЯ ВСІХ ТИПІВ ПОВІДОМЛЕНЬ
# ============================================================================

async def catch_all_messages(message: types.Message):
    """
    Цей handler ловить ВСІ повідомлення що не були оброблені раніше.
    Якщо ви бачите тут web_app_data - значить спеціальний handler НЕ спрацював!
    """
    print("\n" + "🚨" * 40)
    print("🚨 CATCH-ALL HANDLER CALLED!")
    print("🚨" * 40)
    print(f"⚠️ This message was NOT processed by any specific handler!")
    print(f"📥 User: {message.from_user.id}")
    print(f"📥 Content Type: {message.content_type}")
    
    if hasattr(message, 'web_app_data') and message.web_app_data:
        print("\n" + "🔥" * 40)
        print("🔥 WEB_APP_DATA FOUND IN CATCH-ALL!")
        print("🔥 THIS MEANS YOUR SPECIFIC HANDLER DID NOT WORK!")
        print("🔥" * 40)
        print(f"Data: {message.web_app_data.data[:300]}")
        
        await message.answer(
            "⚠️ ДІАГНОСТИКА: Отримано web_app_data, але спеціальний handler НЕ спрацював!\n\n"
            f"Content type: {message.content_type}\n"
            f"Data length: {len(message.web_app_data.data)}"
        )
    else:
        print(f"Text: {message.text if message.text else 'None'}")
        await message.answer(
            f"⚠️ ДІАГНОСТИКА: Отримано повідомлення типу {message.content_type}\n"
            f"Спеціальний handler не знайдено."
        )
    
    print("🚨" * 40 + "\n")


# ============================================================================
# СПЕЦІАЛЬНИЙ ТЕСТОВИЙ HANDLER ДЛЯ web_app_data
# ============================================================================

async def test_webapp_handler(message: types.Message):
    """
    Тестовий handler для web_app_data.
    Якщо ВИ БАЧИТЕ ЦЕЙ ЛОГ - значить dispatcher отримує web_app_data!
    """
    print("\n" + "🎉" * 40)
    print("🎉🎉🎉 TEST WEBAPP HANDLER CALLED! 🎉🎉🎉")
    print("🎉" * 40)
    print(f"✅ web_app_data SUCCESSFULLY RECEIVED!")
    print(f"📥 User: {message.from_user.id}")
    print(f"📥 Data length: {len(message.web_app_data.data)}")
    print(f"📥 Data preview:")
    print(message.web_app_data.data[:500])
    print("🎉" * 40 + "\n")
    
    try:
        data = json.loads(message.web_app_data.data)
        print(f"✅ JSON parsed successfully:")
        print(f"   doc_type: {data.get('doc_type')}")
        print(f"   status: {data.get('status')}")
        print(f"   user_answers: {len(data.get('user_answers', {}))} fields")
        
        await message.answer(
            f"✅ ДІАГНОСТИКА: web_app_data отримано!\n\n"
            f"Doc type: {data.get('doc_type')}\n"
            f"Fields: {len(data.get('user_answers', {}))}\n"
            f"Status: {data.get('status')}\n\n"
            f"🎉 Handler спрацював правильно!"
        )
    except Exception as e:
        print(f"❌ Error parsing JSON: {e}")
        await message.answer(f"⚠️ Помилка парсингу JSON: {e}")


# ============================================================================
# РЕЄСТРАЦІЯ В bot.py
# ============================================================================

"""
ПОМІСТІТЬ ЦЕЙ КОД У ВАШ bot.py АБО main.py:

# 1. ІМПОРТ
from diagnostic_handlers import (
    DebugLoggingMiddleware,
    test_webapp_handler,
    catch_all_messages
)

# 2. ПІСЛЯ СТВОРЕННЯ dp (Dispatcher):
dp = Dispatcher(bot, storage=storage)

# 🔥 КРИТИЧНО: Middleware ПЕРШИМ!
dp.middleware.setup(DebugLoggingMiddleware())
print("✅ Debug middleware activated")

# 3. ЗАРЕЄСТРУЙТЕ ТЕСТОВИЙ HANDLER ПЕРШИМ (ДО ВСІХ ІНШИХ!):
dp.register_message_handler(
    test_webapp_handler,
    content_types=['web_app_data']
)
print("✅ Test WebApp handler registered (content_types=['web_app_data'])")

# 4. ПОТІМ реєструйте ваші звичайні handlers:
from handlers import register_all_handlers
register_all_handlers(dp)

# 5. CATCH-ALL HANDLER В САМОМУ КІНЦІ:
dp.register_message_handler(
    catch_all_messages,
    content_types=types.ContentTypes.ANY,
    state='*'
)
print("✅ Catch-all handler registered (last)")

# 6. ЗАПУСК БОТА
executor.start_polling(dp, skip_updates=True)
"""


# ============================================================================
# АЛЬТЕРНАТИВА: ПРЯМИЙ ПАТЧ dp.process_update
# ============================================================================

def patch_dispatcher_for_debugging(dp):
    """
    Патчить dispatcher для логування ВСІХ updates.
    Використовуйте якщо middleware не допомагає.
    """
    original_process = dp.process_update
    
    async def debug_process_update(update):
        print("\n" + "🔍" * 40)
        print("🔍 DISPATCHER: PROCESSING UPDATE")
        print("🔍" * 40)
        print(f"⏰ Time: {datetime.now().strftime('%H:%M:%S.%f')}")
        print(f"📦 Update ID: {update.update_id}")
        
        # Перевірка типу update
        if update.message:
            msg = update.message
            print(f"📥 Type: MESSAGE")
            print(f"📥 User: {msg.from_user.id}")
            print(f"📥 Content: {msg.content_type}")
            
            if hasattr(msg, 'web_app_data') and msg.web_app_data:
                print("\n🔥🔥🔥 WEB_APP_DATA IN UPDATE! 🔥🔥🔥")
                print(f"📦 Data length: {len(msg.web_app_data.data)}")
                print(f"📦 Data: {msg.web_app_data.data[:300]}")
        
        elif update.callback_query:
            print(f"📥 Type: CALLBACK_QUERY")
            print(f"📥 Data: {update.callback_query.data}")
        
        else:
            print(f"📥 Type: OTHER")
            print(f"📥 Update: {update}")
        
        print("🔍" * 40 + "\n")
        
        # Викликаємо оригінальний метод
        return await original_process(update)
    
    dp.process_update = debug_process_update
    print("✅ Dispatcher patched for debugging")


# ============================================================================
# ВИКОРИСТАННЯ ПАТЧУ
# ============================================================================

"""
ДОДАЙТЕ ДО bot.py ПІСЛЯ СТВОРЕННЯ dp:

from diagnostic_handlers import patch_dispatcher_for_debugging

dp = Dispatcher(bot, storage=storage)

# Патч для глибокої діагностики
patch_dispatcher_for_debugging(dp)

# Потім реєстрація handlers...
"""