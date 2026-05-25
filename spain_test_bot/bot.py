"""
Spain Test Bot — standalone entry point.

Run:
    cd spain_test_bot
    python bot.py

Required env (.env):
    BOT_TOKEN=<your test bot token>
    ENV=test
    DEBUG=True

Optional env for Stripe payments:
    STRIPE_SECRET_KEY=sk_test_...
    STRIPE_WEBHOOK_SECRET=whsec_...
    BOT_USERNAME=your_bot_username   (without @)
    WEBHOOK_PORT=8081                (port for Stripe webhook server)

Flow:
    /start → language selection → main menu → check slots / how it works / support
    /test  → direct Barcelona slot check (dev shortcut)
    /check <city> <authority> → custom check
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# ── Load .env from the same directory as this file ────────────────────────────
from pathlib import Path

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)
else:
    print(f"[WARN] .env not found at {_env_path} — relying on shell environment", file=sys.stderr)

# ── Logging ────────────────────────────────────────────────────────────────────
_debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
logging.basicConfig(
    level=logging.DEBUG if _debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Token guard ────────────────────────────────────────────────────────────────
_TOKEN = os.getenv("BOT_TOKEN", "")
if not _TOKEN or _TOKEN == "PUT_TEST_BOT_TOKEN_HERE":
    logger.critical(
        "BOT_TOKEN is not set.\n"
        "Edit spain_test_bot/.env and replace PUT_TEST_BOT_TOKEN_HERE with your bot token.\n"
        "Get a token from @BotFather on Telegram."
    )
    sys.exit(1)

# ── aiogram setup ─────────────────────────────────────────────────────────────
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage

bot = Bot(token=_TOKEN, parse_mode="HTML")
dp  = Dispatcher(bot, storage=MemoryStorage())

# ── Add spain_test_bot root to sys.path so local imports resolve ───────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── Register handlers (ORDER MATTERS — most specific first) ───────────────────
#
# 1. spain_start       — /start, language callbacks, main menu callbacks
# 2. city_select       — city_<name> callbacks
# 3. service_select    — svc_<name> + more_services + back_to_cities
# 4. payment_handlers  — buy_24h / buy_7d
# 5. monitoring        — start_monitor / stop_monitor / monitor_status / i_booked
# 6. test_handlers     — /test + /check  (dev shortcuts)
#
from handlers.spain_start       import register as _register_start
from handlers.city_select       import register as _register_cities
from handlers.service_select    import register as _register_services
from handlers.payment_handlers  import register as _register_payments
from handlers.monitoring        import register as _register_monitoring
from handlers.test_handlers     import register as _register_test

_register_start(dp)       # /start + language picker + main menu callbacks
_register_cities(dp)      # city_<name> callbacks
_register_services(dp)    # svc_<name> + more_services + back_to_cities callbacks
_register_payments(dp)    # buy_1cita / buy_3citas / buy_5citas
_register_monitoring(dp)  # start_monitor / stop_monitor / monitor_status / i_booked
if _debug:
    _register_test(dp)    # /test + /check  (dev shortcuts — disabled in production)


# ── Startup / shutdown hooks ───────────────────────────────────────────────────

async def _recover_monitoring() -> None:
    """
    On startup, restore monitoring for all active paid users whose sessions
    were lost in memory due to a bot restart.
    """
    try:
        from utils.payments_store import db_load_all_active
        from utils.monitoring import start_monitoring, is_monitoring
        from utils.lang_store import get_lang
        from handlers.city_select import CITIES
        from handlers.service_select import SERVICES

        def _t(d: dict, lg: str) -> str:
            return d.get(lg) or d.get("en") or next(iter(d.values()))

        active = db_load_all_active()
        if not active:
            logger.info("SPAIN_MONITOR_RECOVER_START | no active paid users to restore")
            return

        logger.info("SPAIN_MONITOR_RECOVER_START | active_paid_users=%d", len(active))

        for user_id, record in active.items():
            if is_monitoring(user_id):
                logger.info("SPAIN_MONITOR_RECOVER_SKIPPED | user=%s reason=already_running", user_id)
                continue

            city    = record.get("city", "")
            svc_key = record.get("service", "")

            if not city or not svc_key:
                logger.warning("SPAIN_MONITOR_RECOVER_SKIPPED | user=%s reason=missing_city_or_svc", user_id)
                continue

            lang          = get_lang(user_id) or "en"
            city_display  = _t(CITIES.get(city, {"en": city.title()}), lang)
            svc_info      = SERVICES.get(svc_key, {})
            svc_display   = _t(svc_info.get("labels", {"en": svc_key}), lang)
            authority     = svc_info.get("authority", svc_key)

            try:
                await start_monitoring(
                    bot=bot,
                    user_id=user_id,
                    city=city,
                    svc=svc_key,
                    authority=authority,
                    city_display=city_display,
                    svc_display=svc_display,
                    lang=lang,
                )
                logger.info(
                    "SPAIN_MONITOR_RECOVERED | user=%s city=%s svc=%s lang=%s",
                    user_id, city, svc_key, lang,
                )
            except Exception as exc:
                logger.error("SPAIN_MONITOR_RECOVER_ERROR | user=%s err=%s", user_id, exc)

    except Exception as exc:
        logger.error("SPAIN_MONITOR_RECOVER_FAILED | err=%s", exc)


async def on_startup() -> None:
    me  = await bot.get_me()
    env = os.getenv("ENV", "test")
    logger.info(
        "🇪🇸 Spain Test Bot started | @%s | env=%s | debug=%s",
        me.username, env, _debug,
    )
    logger.info("Flow: /start → language → main menu → check slots → pricing → payment")

    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    if stripe_key and not stripe_key.startswith("PUT_"):
        logger.info("Stripe: configured ✓  |  webhook port: %s", os.getenv("WEBHOOK_PORT", "8081"))
    else:
        logger.warning("Stripe: NOT configured (STRIPE_SECRET_KEY not set) — payments will show 'not configured' message")

    # Restore monitoring sessions for paid users after restart
    await _recover_monitoring()


async def on_shutdown() -> None:
    logger.info("Spain Test Bot shutting down…")
    await dp.storage.close()
    await dp.storage.wait_closed()


# ── Stripe webhook server (aiohttp) ───────────────────────────────────────────

async def _start_webhook_server() -> None:
    """Run a lightweight aiohttp server alongside the bot for Stripe webhooks."""
    try:
        from aiohttp import web
        from webhook.stripe_webhook import stripe_webhook_handler, health_check

        _app = web.Application()
        _app["bot"] = bot
        _app.router.add_post("/webhook", stripe_webhook_handler)
        _app.router.add_get("/health",   health_check)

        _runner = web.AppRunner(_app)
        await _runner.setup()

        _port = int(os.getenv("WEBHOOK_PORT", "8081"))
        _site = web.TCPSite(_runner, "0.0.0.0", _port)
        await _site.start()

        logger.info("Stripe webhook server started on port %d  (POST /webhook)", _port)
        logger.info("For local testing: ngrok http %d", _port)

        # Keep the server running (will be cancelled on shutdown)
        try:
            await asyncio.Event().wait()
        finally:
            await _runner.cleanup()

    except ImportError:
        logger.warning("aiohttp not installed — Stripe webhook server not started")
    except Exception as exc:
        logger.error("Webhook server failed to start: %s", exc)


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> None:
    await on_startup()

    # aiogram 2.x: skip_updates must be called separately before polling
    await dp.skip_updates()

    # Run bot polling and webhook server concurrently
    await asyncio.gather(
        dp.start_polling(),
        _start_webhook_server(),
        return_exceptions=True,
    )

    await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
