# -*- coding: utf-8 -*-
"""
main.py — deprecated alias. Canonical entry point: bot.py

Run: python bot.py
This file exits with an error to avoid accidental use; it does not start the bot.
"""

import sys
import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.error("=" * 80)
    logger.error("❌ ПОМИЛКА: Цей файл застарів і не використовується!")
    logger.error("=" * 80)
    logger.error("Використовуйте bot.py як точку входу: python bot.py")
    logger.error("=" * 80)
    print("\n" + "❌" * 40)
    print("  ЦЕЙ ФАЙЛ ЗАСТАРІВ І НЕ ВИКОРИСТОВУЄТЬСЯ!")
    print("  Використовуйте: python bot.py")
    print("❌" * 40 + "\n")
    sys.exit(1)

# Original code preserved below for reference (commented out)
"""
import sys
import logging
import traceback
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# 1. Завантаження конфігурації
try:
    import config
except ImportError:
    print("❌ Помилка: Файл config.py не знайдено!")
    sys.exit(1)

# Налаштування логування
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# 2. Ініціалізація Бота
bot = Bot(token=config.API_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# 3. Функція реєстрації всіх обробників
def register_all_handlers():
    sys.path.insert(0, config.ROOT_DIR)
    try:
        from handlers.documents import register_webapp_handler
        from handlers.start import register_handlers as reg_start
        from handlers.menu import register_handlers as reg_menu

        # Послідовне підключення модулів
        register_webapp_handler(dp)
        reg_start(dp)
        reg_menu(dp)

        logger.info("✅ УСІ СИСТЕМИ (МЕНЮ + WEBAPP) ПІДКЛЮЧЕНО УСПІШНО!")
    except Exception as e:
        logger.error(f"❌ Помилка підключення модулів: {e}")
        traceback.print_exc()

# 4. Точка входу
if __name__ == "__main__":
    print("\n" + "⭐" * 60)
    print("      GERMAN DOC BOT — ЗАПУСК СИСТЕМИ")
    print("⭐" * 60 + "\n")

    register_all_handlers()

    logger.info("📡 Бот вийшов на зв'язок...")
    executor.start_polling(dp, skip_updates=True)
"""
