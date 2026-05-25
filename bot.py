
# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT — MAIN ENTRYPOINT
Stable production bot.py (aiogram 2.x)
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import re
import asyncio

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
from datetime import datetime
import logging
from dotenv import load_dotenv

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.utils.exceptions import Throttled
from aiogram.dispatcher.handler import CancelHandler

# === LOAD ENV ===
load_dotenv()

from utils.stripe_env import enforce_prod_no_unverified_stripe_webhook
from utils.funnel_log import funnel_city_from_mapping, funnel_city_from_order, log_funnel

enforce_prod_no_unverified_stripe_webhook()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ TELEGRAM_BOT_TOKEN not set")

# === LOGGING ===
# In production (ENV=production) emit structured JSON lines for log aggregators
# (e.g. Loki, CloudWatch, Datadog). In dev, use the human-readable format.

class _JsonFormatter(logging.Formatter):
    """One JSON object per line — compatible with most log aggregators."""
    import json as _json_mod

    def format(self, record: logging.LogRecord) -> str:
        import json as _j
        payload = {
            "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return _j.dumps(payload, ensure_ascii=False)


_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_IS_PROD_LOG = os.getenv("ENV", os.getenv("APP_ENV", "")).lower() == "production"

_handler = logging.StreamHandler()
if _IS_PROD_LOG:
    _handler.setFormatter(_JsonFormatter())
else:
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    handlers=[_handler],
)
logger = logging.getLogger(__name__)

# === RATE LIMITING MIDDLEWARE ===
class ThrottlingMiddleware(BaseMiddleware):
    """Simple per-user rate limiter.

    Default limits (configurable via env):
      - Messages : 1 request / 0.7 s  (prevents spam-clicking buttons)
      - Callbacks: 1 request / 0.4 s  (inline buttons can fire very fast)

    Silently drops requests that exceed the limit — no error message to user,
    no exception propagated. Uses aiogram's built-in dp.throttle() which
    relies on MemoryStorage TTL keys, so no Redis required.
    """
    _MSG_LIMIT = float(os.environ.get("THROTTLE_MSG_RATE", "0.7"))
    _CB_LIMIT = float(os.environ.get("THROTTLE_CB_RATE", "0.4"))

    async def on_process_message(self, message: types.Message, _data: dict):
        try:
            await dp.throttle("msg", rate=self._MSG_LIMIT, user_id=message.from_user.id)
        except Throttled:
            raise CancelHandler()

    async def on_process_callback_query(self, callback: types.CallbackQuery, _data: dict):
        try:
            await dp.throttle("cb", rate=self._CB_LIMIT, user_id=callback.from_user.id)
        except Throttled:
            await callback.answer()  # dismiss the loading spinner silently
            raise CancelHandler()


# === BOT / DISPATCHER ===
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
from utils.runtime_bot import set_runtime_bot

set_runtime_bot(bot)
_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_DEV_MODE = os.getenv("DEV_MODE", "").strip() == "1"
if _REDIS_URL:
    try:
        import urllib.parse as _urlparse
        import socket as _socket
        from aiogram.contrib.fsm_storage.redis import RedisStorage2
        _parsed = _urlparse.urlparse(_REDIS_URL)
        _redis_host = _parsed.hostname or "127.0.0.1"
        _redis_port = _parsed.port or 6379
        with _socket.create_connection((_redis_host, _redis_port), timeout=2):
            pass
        _storage = RedisStorage2(
            host=_redis_host,
            port=_redis_port,
            db=int((_parsed.path or "/0").lstrip("/") or 0),
            password=_parsed.password,
        )
        logger.info("REDIS_ENABLED=True FSM_STORAGE=RedisStorage2 url=%s", _REDIS_URL.split("@")[-1])
    except Exception as _redis_init_err:
        logger.critical(
            "FSM_STORAGE_REDIS_REQUIRED | REDIS_URL is set but Redis FSM init failed: %s",
            _redis_init_err,
        )
        raise RuntimeError("FSM_STORAGE_REDIS_REQUIRED: Redis FSM init failed") from _redis_init_err
else:
    if not _DEV_MODE:
        logger.critical(
            "FSM_STORAGE_REDIS_REQUIRED | REDIS_URL is not set; MemoryStorage is allowed only with DEV_MODE=1"
        )
        raise RuntimeError("FSM_STORAGE_REDIS_REQUIRED: set REDIS_URL or DEV_MODE=1")
    _storage = MemoryStorage()
    logger.warning("FSM_STORAGE_MEMORY_DEV_ONLY | REDIS_ENABLED=False FSM_STORAGE=MemoryStorage")
dp = Dispatcher(bot, storage=_storage)
dp.middleware.setup(LoggingMiddleware())
dp.middleware.setup(ThrottlingMiddleware())
# LoggingMiddleware logs "Unhandled callback query" at INFO when a handler returns
# None (the default for async def).  This is cosmetic noise — handlers work correctly.
# Silence it by raising the middleware's logger to WARNING.
logging.getLogger("aiogram.contrib.middlewares.logging").setLevel(logging.WARNING)

# === IMPORT HANDLERS (ВАЖЛИВО: ПІСЛЯ dp) ===
from handlers.start import register_start_handlers
from handlers.docs_new import (
    register_docs_handlers,
    handle_webapp_data,
    send_post_form_menu_via_http,
)
from handlers.stripe_handler import delayed_ltv_post_pdf_followup, register_stripe_handlers, set_bot
from utils.retention import schedule_retention_messages
from handlers.admin import register_admin_handlers
from handlers.termin import register_termin_handlers
from handlers.termin_activation import send_termin_activation_message as _send_termin_activation_message
from handlers.support_ai import register_support_handlers
from handlers.health import register_health_handlers
from handlers.admin_termin import register_admin_termin_handlers

# === WEBAPP HTTP SERVER ===
_http_runner = None
WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
SEO_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seo-site")


async def _serve_seo_html(filename: str):
    """Return a web.Response with the given seo-site HTML file."""
    path = os.path.join(SEO_DIR, filename)
    real = os.path.realpath(path)
    # Guard against directory traversal
    if not real.startswith(os.path.realpath(SEO_DIR)):
        return web.Response(text="Forbidden", status=403)
    if not os.path.isfile(real):
        return web.Response(text="Not Found", status=404)
    with open(real, "r", encoding="utf-8") as f:
        return web.Response(
            text=f.read(),
            content_type="text/html",
            headers={"Cache-Control": "public, max-age=3600"},
        )


async def _serve_landing(request):
    """Serve seo-site/index.html at /"""
    return await _serve_seo_html("index.html")


async def _serve_seo_page(request):
    """Serve any named seo-site HTML page, e.g. /about → seo-site/about.html"""
    page = request.path.strip("/")
    if page.endswith(".html"):
        page = page[:-5]
    if not page:
        page = "index"
    return await _serve_seo_html(f"{page}.html")


async def _serve_webapp_html(request):
    path = os.path.join(WEBAPP_DIR, "index.html")
    if not os.path.isfile(path):
        return web.Response(text="Not Found", status=404)
    doc_type_q = (request.query.get("doc_type") or request.query.get("doc") or "").strip()
    lang_q = (request.query.get("lang") or "").strip()
    chat_q = (request.query.get("chat_id") or "").strip()
    if doc_type_q and chat_q.isdigit():
        try:
            log_funnel(
                "VIEW_FORM",
                int(chat_q),
                doc_type=doc_type_q,
                lang=lang_q or None,
            )
        except (TypeError, ValueError):
            pass
    with open(path, "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html",
                            headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


async def _api_form_schema(request):
    doc_type = (request.query.get("doc_type") or request.query.get("doc") or "").strip() or "anmeldung"
    lang     = (request.query.get("lang") or "de").strip() or "de"
    no_cache = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    try:
        from backend.forms import has_dynamic_form
        if has_dynamic_form(doc_type):
            from backend.forms.frontend_adapter import build_frontend_schema
            return web.json_response(build_frontend_schema(doc_type, req_lang=lang), headers=no_cache)

        from backend.document_config import get_document_form_schema
        schema = get_document_form_schema(doc_type)
        return web.json_response(schema if schema is not None else [], headers=no_cache)
    except Exception as e:
        logger.warning("_api_form_schema failed doc_type=%s: %s", doc_type, e)
        return web.json_response([], status=200, headers=no_cache)


async def _handle_webapp_submit_http(request):
    try:
        body = await request.json()
        chat_id = int(body.get("chat_id", 0))
        doc_type = (body.get("doc_type") or "anmeldung").strip()
        user_lang = (body.get("lang") or "uk").strip()
        answers = body.get("user_answers") or body.get("answers") or {}

        if not chat_id:
            return web.json_response({"ok": False, "error": "chat_id required"}, status=400)

        _ans = answers if isinstance(answers, dict) else {}
        log_funnel(
            "FORM_SUBMIT",
            chat_id,
            doc_type=doc_type,
            lang=user_lang,
            city=funnel_city_from_mapping(_ans),
        )

        # ── SERVER-SIDE VALIDATION before preview/menu ──
        # Block submission if form data has hard errors (date format, required fields, etc.)
        if (doc_type or "").strip().lower() == "anmeldung":
            try:
                from backend.form_validation import validate_anmeldung_form, get_validation_errors_localized
                _marriage_val = str((answers or {}).get("eheschliessung_ort_datum", "")).strip()
                logger.info("WEBAPP_SUBMIT_DEBUG VALUE: eheschliessung_ort_datum=%r", _marriage_val)
                # Log doc-section fields so we can confirm "" vs absent
                _doc_keys = ["dokumentenart", "ausstellungsbehoerde", "seriennummer", "ausstellungsdatum", "gueltig_bis"]
                logger.info(
                    "FINAL ANSWERS doc_fields: %s",
                    {k: (answers or {}).get(k) for k in _doc_keys},
                )
                is_valid, val_errors, val_warnings = validate_anmeldung_form(answers, user_lang)
                logger.info(
                    "WEBAPP_SUBMIT_DEBUG VALID: is_valid=%s val_errors=%s",
                    is_valid, len(val_errors or [])
                )
                if not is_valid and val_errors:
                    localized = get_validation_errors_localized(val_errors, user_lang)
                    error_messages = [e.get("message", "") for e in localized if e.get("message")]
                    field_errors = {}
                    for e in localized:
                        f = e.get("field", "")
                        if f:
                            field_errors[f] = e.get("message", "")
                    for _e in localized:
                        logger.info(
                            "WEBAPP_SUBMIT_DEBUG BLOCK REASON: field=%s message=%s",
                            _e.get("field", ""),
                            _e.get("message", "") or _e.get("message_key", ""),
                        )
                    logger.info("WEBAPP_SUBMIT_VALIDATION_FAILED chat_id=%s errors=%s", chat_id, len(val_errors))
                    return web.json_response({
                        "ok": False,
                        "validation": True,
                        "errors": error_messages,
                        "field_errors": field_errors,
                    })
            except Exception as ve:
                logger.warning("Form validation check failed (non-blocking): %s", ve)
                # Non-blocking: if validation module fails, allow submission to proceed

        bot_instance = request.app["bot"]
        ok = await send_post_form_menu_via_http(bot_instance, chat_id, doc_type, user_lang, answers)
        if ok:
            return web.json_response({
                "ok": True,
                "message": "PDF ready. Proceed to payment",
            })
        return web.json_response({"ok": False, "error": "Failed to prepare payment flow"}, status=500)
    except Exception as e:
        logger.exception("webapp-submit HTTP error: %s", e)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def _handle_payment_success(request):
    """
    Landing page after Stripe Checkout completes.
    This page allows Stripe to finalize the payment before redirecting to Telegram.
    Localized via ?lang= query param.
    """
    order_id = request.query.get("order_id", "")
    lang = request.query.get("lang", "uk")
    if lang == "ua":
        lang = "uk"
    bot_username = os.getenv("BOT_USERNAME", "DE_PDF_Assistant_bot")

    logger.info("PAYMENT_SUCCESS_PAGE order_id=%s lang=%s", order_id, lang)

    if not order_id:
        return web.Response(text="<html><body><h2>Missing order_id</h2></body></html>",
                            content_type="text/html", status=400)

    _titles = {"uk": "Оплату успішно завершено!", "ua": "Оплату успішно завершено!", "en": "Payment successful!",
               "de": "Zahlung erfolgreich!", "pl": "Płatność zakończona!",
               "tr": "Ödeme başarılı!", "ar": "تمت عملية الدفع بنجاح!"}
    _descs = {"uk": "Дякуємо за оплату. Ваш документ буде доставлено автоматично в Telegram протягом кількох секунд.",
              "ua": "Дякуємо за оплату. Ваш документ буде доставлено автоматично в Telegram протягом кількох секунд.",
              "en": "Thank you for your payment. Your document will be delivered automatically in Telegram within seconds.",
              "de": "Vielen Dank für Ihre Zahlung. Ihr Dokument wird in wenigen Sekunden automatisch in Telegram zugestellt.",
              "pl": "Dziękujemy za płatność. Twój dokument zostanie dostarczony automatycznie w Telegramie w ciągu kilku sekund.",
              "tr": "Ödemeniz için teşekkürler. Belgeniz birkaç saniye içinde Telegram'da otomatik olarak teslim edilecektir.",
              "ar": "شكراً لك على الدفع. سيتم تسليم المستند تلقائياً في تيليجرام خلال ثوانٍ."}
    _returning = {
        "uk": "Повернення в Telegram…", "ua": "Повернення в Telegram…",
        "en": "Returning to Telegram…", "de": "Weiterleitung zu Telegram…",
        "pl": "Powrót do Telegrama…", "tr": "Telegram'a dönülüyor…",
        "ar": "جارٍ العودة إلى تيليجرام…",
    }
    _please_wait = {
        "uk": "Зачекайте, будь ласка.", "ua": "Зачекайте, будь ласка.",
        "en": "Please wait a moment.", "de": "Bitte einen Moment warten.",
        "pl": "Proszę chwilę poczekać.", "tr": "Lütfen bir dakika bekleyin.",
        "ar": "يرجى الانتظار لحظة.",
    }

    title = _titles.get(lang, _titles["en"])
    returning = _returning.get(lang, _returning["en"])
    please_wait = _please_wait.get(lang, _please_wait["en"])
    html_dir = "rtl" if lang == "ar" else "ltr"

    tg_native = f"tg://resolve?domain={bot_username}&start=paid_{order_id}"
    tg_web    = f"https://t.me/{bot_username}?start=paid_{order_id}"

    html = f"""<!DOCTYPE html>
<html lang="{lang}" dir="{html_dir}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Successful</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            text-align: center;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        .icon {{ font-size: 64px; margin-bottom: 20px; }}
        h1 {{ color: #22c55e; margin-bottom: 28px; font-size: 24px; }}
        .tg-btn {{
            display: inline-block;
            background: #0088cc;
            color: white;
            text-decoration: none;
            font-size: 16px;
            font-weight: 600;
            padding: 14px 28px;
            border-radius: 12px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h1>{title}</h1>
        <a class="tg-btn" href="{tg_native}">{returning}</a>
    </div>
</body>
</html>"""
    
    return web.Response(text=html, content_type="text/html")


async def _handle_webhook_test(request):
    """
    Test endpoint to verify webhook URL is accessible.
    GET /stripe-webhook-test → shows diagnostic info
    """
    webapp_url = os.getenv("WEBAPP_URL", "NOT_SET")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    
    html = f"""<!DOCTYPE html>
<html>
<head><title>Webhook Test</title></head>
<body style="font-family: monospace; padding: 20px;">
<h1>Stripe Webhook Endpoint Test</h1>
<p><strong>Status:</strong> ✅ Server is running</p>
<p><strong>Webhook URL:</strong> {webapp_url}/stripe-webhook</p>
<p><strong>Webhook Secret:</strong> {"✅ Configured (ends with ..." + webhook_secret[-4:] + ")" if webhook_secret else "❌ NOT SET"}</p>
<hr>
<h2>Setup Instructions:</h2>
<ol>
<li>Go to <a href="https://dashboard.stripe.com/test/webhooks" target="_blank">Stripe Dashboard → Webhooks</a></li>
<li>Click "Add endpoint"</li>
<li>URL: <code>{webapp_url}/stripe-webhook</code></li>
<li>Select event: <code>checkout.session.completed</code></li>
<li>Copy "Signing secret" to .env as STRIPE_WEBHOOK_SECRET</li>
</ol>
<hr>
<p>If webhook still doesn't work, click "Send test webhook" in Stripe Dashboard and check bot console.</p>
</body>
</html>"""
    
    logger.debug("WEBHOOK_TEST_PAGE_ACCESSED")
    return web.Response(text=html, content_type="text/html")


async def _handle_payment_cancel(request):
    """
    Landing page when user cancels Stripe Checkout.
    Localized via ?lang= query param.
    """
    order_id = request.query.get("order_id", "")
    lang = request.query.get("lang", "uk")
    if lang == "ua":
        lang = "uk"
    bot_username = os.getenv("BOT_USERNAME", "DE_PDF_Assistant_bot")
    
    logger.debug("PAYMENT_CANCEL_PAGE: order_id=%s lang=%s", order_id, lang)

    _titles = {"uk": "Оплату скасовано", "ua": "Оплату скасовано", "en": "Payment cancelled",
               "de": "Zahlung abgebrochen", "pl": "Płatność anulowana",
               "tr": "Ödeme iptal edildi", "ar": "تم إلغاء الدفع"}
    _descs = {"uk": "Ви можете повернутися в бот і спробувати ще раз.",
              "ua": "Ви можете повернутися в бот і спробувати ще раз.",
              "en": "You can return to the bot and try again.",
              "de": "Sie können zum Bot zurückkehren und es erneut versuchen.",
              "pl": "Możesz wrócić do bota i spróbować ponownie.",
              "tr": "Bota geri dönüp tekrar deneyebilirsiniz.",
              "ar": "يمكنك العودة إلى البوت والمحاولة مرة أخرى."}
    _btns = {"uk": "📱 Повернутися в Telegram", "ua": "📱 Повернутися в Telegram", "en": "📱 Return to Telegram",
             "de": "📱 Zurück zu Telegram", "pl": "📱 Wróć do Telegrama",
             "tr": "📱 Telegram'a dön", "ar": "📱 العودة إلى تيليجرام"}

    title = _titles.get(lang, _titles["en"])
    desc = _descs.get(lang, _descs["en"])
    btn = _btns.get(lang, _btns["en"])
    html_dir = "rtl" if lang == "ar" else "ltr"

    html = f"""<!DOCTYPE html>
<html lang="{lang}" dir="{html_dir}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Cancelled</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            text-align: center;
            max-width: 400px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        .icon {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #f59e0b;
            margin-bottom: 10px;
            font-size: 24px;
        }}
        p {{
            color: #666;
            margin-bottom: 30px;
            line-height: 1.6;
        }}
        .btn {{
            display: inline-block;
            background: #0088cc;
            color: white;
            padding: 15px 40px;
            border-radius: 30px;
            text-decoration: none;
            font-weight: 600;
            font-size: 16px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0,136,204,0.4);
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">↩️</div>
        <h1>{title}</h1>
        <p>{desc}</p>
        <a href="https://t.me/{bot_username}?start=cancel_{order_id}" class="btn">
            {btn}
        </a>
    </div>
</body>
</html>"""
    
    return web.Response(text=html, content_type="text/html")


async def _http_health(_request):
    """Lightweight liveness for load balancers (no DB, no Telegram)."""
    return web.json_response({"status": "ok", "service": "german-doc-bot"})


def _stripe_checkout_resolved_email(session, metadata):
    """
    Canonical email from Checkout session (dict or object).

    Priority:
      1. customer_details.email  — populated after expand=["customer_details"]
      2. customer_email          — pre-filled field on the session
      3. receipt_email           — Stripe receipt address (often set for wallets)
      4. metadata.email          — passed by us at session creation

    Safe when customer_details is missing/None or session is dict vs Stripe object.
    """
    meta = metadata or {}

    def _norm(e):
        if not e:
            return None
        s = str(e).strip()
        return s if _EMAIL_RE.match(s) else None

    try:
        em = None
        if isinstance(session, dict):
            cd = session.get("customer_details")
            if cd is not None:
                em = cd.get("email") if isinstance(cd, dict) else getattr(cd, "email", None)
            if not em:
                em = session.get("customer_email")
            if not em:
                em = session.get("receipt_email")
        else:
            cd = getattr(session, "customer_details", None)
            if cd is not None:
                em = cd.get("email") if isinstance(cd, dict) else getattr(cd, "email", None)
            if not em:
                em = getattr(session, "customer_email", None)
            if not em:
                em = getattr(session, "receipt_email", None)
        if not em:
            em = meta.get("email")
        return _norm(em)
    except Exception:
        return _norm(meta.get("email"))


async def _handle_stripe_webhook(request):
    """
    Stripe webhook handler for checkout.session.completed.
    Single flow: receive → verify → mark PAID → deliver PDF.
    """
    import stripe as stripe_lib

    # Diagnostic: always print to stdout so this is visible even if logger level is filtered
    print("WEBHOOK HIT", flush=True)
    print(f"WEBHOOK HIT remote={request.remote} method={request.method}", flush=True)

    # FUNNEL POINT 7: Stripe webhook arrived
    logger.info("FUNNEL | step=webhook_received remote=%s", request.remote)

    raw_body = await request.read()
    sig = request.headers.get("Stripe-Signature") or ""
    print(f"SIG HEADER: {'present' if sig else 'MISSING'} body_len={len(raw_body)}", flush=True)

    logger.info("WEBHOOK_SIGNATURE_PRESENT: %s", bool(sig))
    logger.debug("WEBHOOK_BODY_LENGTH: %s", len(raw_body))

    # Load webhook secret
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not webhook_secret:
        try:
            from backend.settings import settings
            webhook_secret = getattr(settings.stripe, "STRIPE_WEBHOOK_SECRET", "")
        except Exception:
            pass

    print(f"SECRET LOADED: {'YES len=' + str(len(webhook_secret)) if webhook_secret else 'NO — STRIPE_WEBHOOK_SECRET missing'}", flush=True)
    logger.info("WEBHOOK_SECRET_LOADED: %s (len=%s)", bool(webhook_secret), len(webhook_secret))

    # Verify signature and parse event
    if webhook_secret:
        try:
            event = stripe_lib.Webhook.construct_event(raw_body, sig, webhook_secret)
            event_type = event.type
            event_data = event.data
            logger.info("WEBHOOK_SIGNATURE_VERIFIED: OK")
        except stripe_lib.error.SignatureVerificationError as e:
            print(f"WEBHOOK SIGNATURE ERROR: {e}", flush=True)
            logger.info("WEBHOOK_SIGNATURE_FAILED: %s", e)
            logger.error("WEBHOOK_SIGNATURE_FAILED: %s", e)
            return web.Response(status=400, text="Invalid signature")
        except Exception as e:
            print(f"WEBHOOK CONSTRUCT_EVENT ERROR: {e}", flush=True)
            logger.error("WEBHOOK_CONSTRUCT_EVENT_FAILED: %s", e)
            return web.Response(status=400, text="Parse error")
    else:
        _allow_unverified = os.getenv("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not _allow_unverified:
            logger.error("Stripe webhook blocked: no signing secret configured")
            logger.error(
                "WEBHOOK_REJECTED: STRIPE_WEBHOOK_SECRET missing — "
                "configure signing secret, or STRIPE_ALLOW_UNVERIFIED_WEBHOOKS=true for local testing only"
            )
            # 400: Stripe will not retry indefinitely (unlike many 5xx responses).
            return web.Response(status=400, text="Webhook not configured")
        logger.warning(
            "WEBHOOK_UNVERIFIED_MODE: parsing without signature verification (dev only — never in production)"
        )
        payload = __import__("json").loads(raw_body.decode("utf-8"))
        event_type = payload.get("type")
        event_data = payload.get("data")

    logger.info("WEBHOOK_EVENT_TYPE: %s", event_type)
    print(f"EVENT TYPE: {event_type}", flush=True)

    # Only process checkout.session.completed
    if event_type != "checkout.session.completed":
        return web.Response(status=200, text="ok")

    # Parse session
    session = event_data.get("object") if hasattr(event_data, "get") else event_data.object
    session_id = session.get("id") if isinstance(session, dict) else getattr(session, "id", None)

    logger.info("STRIPE_WEBHOOK_RECEIVED | event_type=%s session_id=%s", event_type, session_id)

    # Re-fetch session from Stripe API with expanded fields so customer_details and customer
    # are always populated — the webhook payload often omits them (Apple Pay, Google Pay, Link).
    if session_id:
        try:
            session = stripe_lib.checkout.Session.retrieve(
                session_id,
                expand=["customer_details", "customer"],
            )
            logger.info("WEBHOOK_SESSION_REFETCHED: session_id=%s", session_id)
        except Exception as _refetch_err:
            logger.warning("WEBHOOK_SESSION_REFETCH_FAILED: session_id=%s err=%s", session_id, _refetch_err)

    status_val = session.get("status") if isinstance(session, dict) else getattr(session, "status", None)
    payment_status_val = session.get("payment_status") if isinstance(session, dict) else getattr(session, "payment_status", None)
    metadata_obj = (
        session.get("metadata") if isinstance(session, dict) else getattr(session, "metadata", None)
    ) or {}
    logger.info("STRIPE_METADATA_RAW type=%s value=%s", type(metadata_obj).__name__, metadata_obj)
    if hasattr(metadata_obj, "to_dict"):
        metadata = metadata_obj.to_dict()
    elif isinstance(metadata_obj, dict):
        metadata = metadata_obj
    else:
        try:
            metadata = dict(metadata_obj.items())
        except Exception:
            metadata = {}
    metadata = {str(k): v for k, v in metadata.items()}
    logger.info("STRIPE_METADATA_PARSED type=%s value=%s", type(metadata).__name__, metadata)

    # Resolve email: customer_details → customer_email → receipt_email → metadata.email
    _customer_email = _stripe_checkout_resolved_email(session, metadata)

    # Fallback: retrieve Customer object (highest reliability — covers Apple Pay / Google Pay)
    if not _customer_email:
        _customer_id = (
            session.get("customer") if isinstance(session, dict) else getattr(session, "customer", None)
        )
        if _customer_id and isinstance(_customer_id, str):
            try:
                _cust_obj = stripe_lib.Customer.retrieve(_customer_id)
                _cust_email = (
                    _cust_obj.get("email") if isinstance(_cust_obj, dict) else getattr(_cust_obj, "email", None)
                )
                if _cust_email and _EMAIL_RE.match(str(_cust_email).strip()):
                    _customer_email = str(_cust_email).strip()
                    logger.info("WEBHOOK_EMAIL_FROM_CUSTOMER: session_id=%s email=%s", session_id, _customer_email)
            except Exception as _cust_err:
                logger.warning("WEBHOOK_CUSTOMER_FETCH_FAILED: customer_id=%s err=%s", _customer_id, _cust_err)

    if _customer_email:
        logger.info(
            "WEBHOOK_EMAIL_RESOLVED: order_id=%s email=%s",
            metadata.get("order_id"),
            _customer_email,
        )
    else:
        logger.warning(
            "WEBHOOK_NO_EMAIL_YET: order_id=%s (Checkout may collect; or use metadata.email)",
            metadata.get("order_id"),
        )

    # Get order_id from metadata or client_reference_id
    order_id_str = metadata.get("order_id")
    if not order_id_str:
        order_id_str = session.get("client_reference_id") if isinstance(session, dict) else getattr(session, "client_reference_id", None)

    # Validate order_id exists
    if not order_id_str or not str(order_id_str).strip().isdigit():
        logger.info("WEBHOOK_ERROR: NO_ORDER_ID metadata=%s", metadata)
        return web.Response(status=200, text="ok")

    order_id = int(order_id_str)

    logger.info("WEBHOOK_ORDER_ID: order_id=%s session_id=%s", order_id, session_id)

    # Validate payment completed
    if status_val != "complete" or payment_status_val != "paid":
        logger.debug("WEBHOOK_SKIP: payment not complete (status=%s payment_status=%s)", status_val, payment_status_val)
        return web.Response(status=200, text="ok")

    # === LOAD ORDER AND MARK PAID ===
    from utils.helpers import get_db
    from backend.database import OrderStatus
    from handlers.stripe_handler import deliver_document_after_payment

    db = get_db()
    order = db.get_order(order_id)
    
    if not order:
        logger.info("WEBHOOK_ERROR: ORDER_NOT_FOUND order_id=%s", order_id)
        return web.Response(status=200, text="ok")

    old_status = (order.get("status") or "").strip().lower()

    # Session guard: reject if the order is already bound to a different Stripe session.
    # Protects against a second checkout for the same order_id "hijacking" delivery.
    _stored_session = (order.get("stripe_session_id") or "").strip()
    if _stored_session and session_id and _stored_session != session_id:
        logger.warning(
            "WEBHOOK_SESSION_MISMATCH: order_id=%s stored=%s incoming=%s — skipping",
            order_id, _stored_session, session_id,
        )
        return web.Response(status=200, text="ok")

    # Idempotency: skip if already claimed or delivered to prevent double-activation
    # on Stripe webhook re-delivery. PROCESSING is included: claim_delivery already
    # won for this order — overwriting back to PAID would allow a second claim and
    # a duplicate PDF send.
    _skip_claim_paid = False  # set True in Termin recovery path (already PAID)
    if old_status in (
        OrderStatus.PAID.value,
        OrderStatus.PROCESSING.value,
        OrderStatus.SENT.value,
        OrderStatus.DOWNLOADED.value,
    ):
        # Recovery path: PAID Termin order whose activation message was never delivered.
        # This happens when: claim_paid succeeded, entitlement activated, but the Telegram
        # message send failed (returned False) so mark_order_delivered was NOT called.
        # Stripe retried and we now allow re-activation to deliver the message.
        if old_status == OrderStatus.PAID.value:
            _doc_type_idem = (order.get("doc_type") or "").strip()
            if _doc_type_idem.startswith("termin_"):
                try:
                    _already_delivered = db.is_order_delivered(order_id)
                except Exception:
                    _already_delivered = True  # safe default: assume delivered on error
                if not _already_delivered:
                    logger.warning(
                        "TERMIN_WEBHOOK_RECOVERY | order=%s status=paid delivered=False "
                        "doc_type=%s — activation message was never delivered; re-running activation",
                        order_id, _doc_type_idem,
                    )
                    print(
                        f"TERMIN_WEBHOOK_RECOVERY order_id={order_id} — re-running activation",
                        flush=True,
                    )
                    _skip_claim_paid = True
                    order = db.get_order(order_id)  # re-read for fresh state
                    # Fall through to activation code below
                else:
                    logger.info("WEBHOOK_IDEMPOTENT_SKIP: order_id=%s status=%s delivered=True", order_id, old_status)
                    return web.Response(status=200, text="ok")
            else:
                logger.info("WEBHOOK_IDEMPOTENT_SKIP: order_id=%s status=%s", order_id, old_status)
                print(f"WEBHOOK_IDEMPOTENT_SKIP order_id={order_id} status={old_status}", flush=True)
                return web.Response(status=200, text="ok")
        else:
            logger.info("WEBHOOK_IDEMPOTENT_SKIP: order_id=%s status=%s", order_id, old_status)
            print(f"WEBHOOK_IDEMPOTENT_SKIP order_id={order_id} status={old_status}", flush=True)
            return web.Response(status=200, text="ok")

    # FAILED orders are handled exclusively by the in-process retry system
    # (delivery_retry.py) and admin intervention — not by webhook replay.
    # Re-activating via webhook would bypass force=True delivery logic.
    if old_status == OrderStatus.FAILED.value:
        logger.info("WEBHOOK_SKIP_FAILED: order_id=%s — retry system owns failed orders", order_id)
        return web.Response(status=200, text="ok")

    # Mark as PAID — atomic conditional: only succeeds when status is still PENDING.
    # Skip when in recovery mode (order already PAID — claim_paid would fail the CAS).
    if _skip_claim_paid:
        logger.info(
            "WEBHOOK_CLAIM_PAID_SKIPPED | order=%s — recovery mode, order already PAID",
            order_id,
        )
    elif not db.claim_paid(order_id, stripe_session_id=session_id):
        logger.info("WEBHOOK_CLAIM_PAID_LOST: order_id=%s — status changed since read, skipping", order_id)
        return web.Response(status=200, text="ok")

    # Verify update
    order = db.get_order(order_id)
    new_status = (order.get("status") or "").strip().lower()

    logger.info("WEBHOOK_MARKED_PAID: order_id=%s %s -> %s", order_id, old_status, new_status)
    logger.info("FUNNEL | step=order_marked_paid order_id=%s user_id=%s", order_id, order.get("user_id"))
    print(f"PAYMENT CONFIRMED order_id={order_id} user_id={order.get('user_id')}", flush=True)

    if new_status != OrderStatus.PAID.value:
        logger.info("WEBHOOK_ERROR: STATUS_UPDATE_FAILED order_id=%s", order_id)
        return web.Response(status=500, text="status update failed")

    if old_status != OrderStatus.PAID.value:
        _pay_uid = int(order.get("user_id") or 0)
        if _pay_uid:
            _amt_eur = None
            try:
                _atotal = (
                    session.get("amount_total")
                    if isinstance(session, dict)
                    else getattr(session, "amount_total", None)
                )
                if _atotal is not None:
                    _amt_eur = round(float(_atotal) / 100.0, 2)
            except Exception:
                pass
            if _amt_eur is None:
                try:
                    _amt_eur = round(float(order.get("price") or order.get("amount") or 0), 2)
                except Exception:
                    _amt_eur = 0.0
            _o_lang = (order.get("lang") or "").strip() or None
            log_funnel(
                "PAYMENT_SUCCESS",
                _pay_uid,
                doc_type=order.get("doc_type"),
                lang=_o_lang,
                city=funnel_city_from_order(order),
                order_id=order_id,
                amount=_amt_eur,
            )

    # === EMAIL (order: extract → persist → optional hydrate) BEFORE PDF / outbound email ===
    # Session extract is above (_customer_email). Delivery runs much later via
    # deliver_document_after_payment — these steps must finish first so users row
    # and downstream bundle/termin branches see the final address.
    logger.info("EMAIL_AFTER_PAYMENT: %s", _customer_email or None)
    if _customer_email and order.get("user_id"):
        try:
            from utils.user_email import merge_stripe_email_into_user

            _merged = merge_stripe_email_into_user(
                int(order.get("user_id")),
                order_id,
                _customer_email,
                db=db,
            )
            if _merged is not None:
                _customer_email = _merged
            else:
                from utils.user_email import get_user_email as _get_canonical_email

                _g = _get_canonical_email(int(order.get("user_id")))
                _customer_email = _g or None
        except Exception as _sync_e:
            logger.warning(
                "CHECKOUT_EMAIL_PERSIST_FAILED: order_id=%s err=%s",
                order_id,
                _sync_e,
            )

    # Stripe may omit email (e.g. some wallet flows); copy from WebApp form before PDF gen.
    if not (_customer_email and str(_customer_email).strip()) and order.get("user_id"):
        from utils.user_email import hydrate_email_from_order_user_data

        _hydr = hydrate_email_from_order_user_data(
            order_id,
            int(order.get("user_id")),
            db=db,
        )
        if _hydr:
            _customer_email = _hydr

    logger.info(
        "CHECKOUT_EMAIL_PERSIST_DONE before_delivery order=%s has_email=%s",
        order_id,
        bool(_customer_email and str(_customer_email).strip()),
    )

    # === ADMIN ALERT: notify on every confirmed payment ===
    try:
        _adm_raw = os.getenv("ADMIN_IDS", "")
        _adm_ids = [int(x.strip()) for x in _adm_raw.split(",") if x.strip().isdigit()]
        if _adm_ids:
            _adm_bot = request.app.get("bot")
            _adm_amount = order.get("amount") or order.get("price") or 0
            _adm_doc    = (order.get("doc_type") or "?").replace("_", " ").title()
            _adm_uid    = order.get("user_id") or "unknown"
            _adm_email  = _customer_email or "—"
            _adm_msg = (
                f"💰 <b>New payment received</b>\n\n"
                f"📄 Doc: <b>{_adm_doc}</b>\n"
                f"💶 Amount: <b>€{float(_adm_amount):.2f}</b>\n"
                f"👤 User: <code>{_adm_uid}</code>\n"
                f"📧 Email: {_adm_email}\n"
                f"🔑 Order: <code>{order_id}</code>\n"
                f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
            )
            for _aid in _adm_ids:
                try:
                    await _adm_bot.send_message(_aid, _adm_msg, parse_mode="HTML")
                except Exception:
                    pass
    except Exception as _adm_err:
        logger.warning("ADMIN_ALERT_FAILED: %s", _adm_err)

    # === BUNDLE: activate Termin if purchased as bundle ===
    if metadata.get("bundle") == "true":
        try:
            from backend.termin_db import (
                update_user as _upd_termin, create_user as _crt_termin,
                upsert_entitlement as _upsert_ent,
                get_user as _get_termin_user,
                create_reminder as _create_termin_reminder,
            )
            _tid = str(order.get("user_id"))
            _crt_termin(_tid)
            _upd_termin(_tid, has_paid_termin=1)
            # Store Stripe customer email for slot-found email notifications
            if _customer_email:
                _upd_termin(_tid, customer_email=_customer_email, termin_email_notified=0)
                logger.info(
                    "TERMIN_EMAIL_STORED: order_id=%s user_id=%s email=%s (bundle)",
                    order_id, _tid, _customer_email,
                )
                logger.info("EMAIL_SAVED | user=%s email=%s", _tid, _customer_email)
            else:
                logger.error(
                    "EMAIL_MISSING_IN_SESSION | user=%s order=%s — "
                    "Stripe session had no email; slot-found email will be skipped",
                    _tid, order_id,
                )
            # Read city/authority BEFORE upsert so they are stored in entitlement.
            # Priority: Stripe metadata (set at checkout time) → users table → log ERROR.
            _t_user_row = _get_termin_user(_tid)
            _meta_city = metadata.get("city") or ""
            _meta_auth = metadata.get("authority") or ""
            _db_city = (_t_user_row or {}).get("city") or ""
            _db_auth = (_t_user_row or {}).get("authority") or ""
            logger.info("CITY_FROM_STRIPE | user=%s meta_city=%s meta_auth=%s order=%s",
                        _tid, _meta_city, _meta_auth, order_id)
            if _meta_city:
                _t_city = _meta_city
                _t_auth = _meta_auth or _db_auth
                _city_source = "metadata"
            elif _db_city:
                _t_city = _db_city
                _t_auth = _db_auth
                _city_source = "users_fallback"
                logger.error(
                    "CITY_MISSING_IN_METADATA | user=%s order=%s falling_back_to=%s — "
                    "city was not passed to Stripe session metadata",
                    _tid, order_id, _db_city,
                )
            else:
                _t_city = ""
                _t_auth = ""
                _city_source = "unknown"
                logger.error(
                    "CITY_UNKNOWN | user=%s order=%s — city missing from both metadata and DB. "
                    "Monitoring cannot start until user selects a city.",
                    _tid, order_id,
                )
            logger.warning(
                "ENTITLEMENT_CITY_SOURCE | user=%s city=%s source=%s order=%s",
                _tid, _t_city, _city_source, order_id,
            )
            logger.info(
                "STRIPE_METADATA_SAVED | user=%s city=%s authority=%s order=%s",
                _tid, _t_city, _t_auth, order_id,
            )
            _upsert_ent(
                str(_tid),
                plan="single",
                slots_total=1,
                stripe_session_id=session_id or f"bundle_{order_id}",
                paid_until=None,
                city=_t_city,
                authority=_t_auth,
            )
            # Activate reminder so _resume_termin_monitoring() picks this user up on restart
            _create_termin_reminder(_tid, _t_city, _t_auth, 6)
            logger.info("BUNDLE_TERMIN_ACTIVATED: order_id=%s user_id=%s city=%s auth=%s", order_id, _tid, _t_city, _t_auth)

            # Auto-start polling immediately if city/authority are resolved
            logger.info("CITY_IN_ENTITLEMENT | user=%s city=%s authority=%s order=%s",
                        _tid, _t_city, _t_auth, order_id)
            if _t_city and _t_auth:
                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp_b, is_polling as _isp_b, get_session as _get_sess_b, stop_polling as _stop_b
                    from utils.helpers import get_user_lang as _gul_b
                    from backend.termin_db import is_termin_entitled as _ite_b
                    _b_bot = request.app["bot"]
                    _b_lang = (_gul_b(int(_tid)) or "uk").strip().lower()
                    # Hard protection: stop any existing session before starting a new one
                    _existing_b = _get_sess_b(int(_tid))
                    if _existing_b:
                        logger.error(
                            "TERMIN_DOUBLE_SESSION_BLOCKED | user=%s old_city=%s new_city=%s order=%s plan=bundle",
                            _tid, _existing_b.city, _t_city, order_id,
                        )
                        _stop_b(int(_tid), reason="new_payment_bundle")
                    if _ite_b(str(_tid)) and not _isp_b(int(_tid)):
                        _stp_b(
                            user_id=int(_tid),
                            chat_id=int(_tid),
                            city=_t_city,
                            authority=_t_auth,
                            lang=_b_lang,
                            send_fn=make_termin_send_fn(_b_bot, int(_tid), _t_city, _b_lang),
                            on_reserved_fn=make_termin_on_reserved_fn(
                                _b_bot, int(_tid), _t_city, _t_auth, _b_lang, state=None
                            ),
                            on_found_fn=make_termin_found_fn(_b_bot, authority=_t_auth),
                        )
                        logger.debug("BUNDLE_POLLING_STARTED: user=%s city=%s auth=%s", _tid, _t_city, _t_auth)
                        logger.info("CITY_MONITOR_ACTIVATED | user=%s city=%s authority=%s source=%s order=%s",
                                    _tid, _t_city, _t_auth, _city_source, order_id)
                    else:
                        logger.debug("BUNDLE_POLLING_SKIP: user=%s (not entitled or already polling)", _tid)
                except Exception as _bpe:
                    logger.debug("BUNDLE_POLLING_START_ERROR: user=%s err=%s", _tid, _bpe)
            else:
                # City/authority not yet selected — monitoring will start when user selects them
                logger.debug("BUNDLE_POLLING_DEFERRED: user=%s (city/authority not yet selected)", _tid)
                try:
                    from utils.helpers import get_user_lang as _gul_b2
                    _b_bot2 = request.app["bot"]
                    _b_lang2 = (_gul_b2(int(_tid)) or "uk").strip().lower()
                    _SELECT_CITY_MSG = {
                        "uk": "✅ <b>Оплата отримана!</b>\n\nЩоб розпочати моніторинг термінів, оберіть місто та орган в меню Терміну.",
                        "en": "✅ <b>Payment received!</b>\n\nTo start appointment monitoring, please select a city and authority in the Termin menu.",
                        "de": "✅ <b>Zahlung eingegangen!</b>\n\nUm die Terminüberwachung zu starten, wählen Sie bitte Stadt und Behörde im Termin-Menü.",
                        "pl": "✅ <b>Płatność otrzymana!</b>\n\nAby rozpocząć monitorowanie terminów, wybierz miasto i urząd w menu Termin.",
                        "tr": "✅ <b>Ödeme alındı!</b>\n\nRandevu takibini başlatmak için lütfen Termin menüsünden şehir ve kurum seçin.",
                        "ar": "✅ <b>تم استلام الدفع!</b>\n\nلبدء مراقبة المواعيد، يرجى اختيار المدينة والجهة من قائمة Termin.",
                    }
                    _l2 = "uk" if _b_lang2 == "ua" else _b_lang2
                    await _b_bot2.send_message(
                        chat_id=int(_tid),
                        text=_SELECT_CITY_MSG.get(_l2, _SELECT_CITY_MSG["en"]),
                        parse_mode="HTML",
                    )
                except Exception as _bmsg_e:
                    logger.debug("BUNDLE_DEFERRED_MSG_ERROR: user=%s err=%s", _tid, _bmsg_e)
        except Exception as _be:
            print(f"CRITICAL ERROR BUNDLE_ACTIVATION: order_id={order_id} error={_be}", flush=True)
            logger.info("BUNDLE_TERMIN_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _be)

    # === TERMIN-ONLY: skip PDF delivery, payment is for notifications only ===
    if metadata.get("termin_only") == "true":
        logger.info("TERMIN_ONLY_COMPLETED: order_id=%s — no PDF delivery needed", order_id)
        # Mark PAID only — NOT SENT. Delivery (success screen) is done by the deeplink
        # handler when the user returns from Stripe. Setting SENT here would cause
        # is_order_delivered() to return True (via its status fallback) and skip delivery.
        db.update_order_status(order_id, OrderStatus.PAID)

        # CRITICAL: activate has_paid_termin + entitlement until first found Termin
        _termin_uid = order.get("user_id")
        if _termin_uid:
            try:
                from backend.termin_db import (
                    update_user as _upd_termin, create_user as _crt_termin,
                    upsert_entitlement as _upsert_ent,
                    get_user as _get_termin_user,
                    create_reminder as _create_termin_reminder,
                )
                _crt_termin(str(_termin_uid))
                _upd_termin(str(_termin_uid), has_paid_termin=1)
                # Store Stripe customer email for slot-found email notifications
                if _customer_email:
                    _upd_termin(
                        str(_termin_uid),
                        customer_email=_customer_email,
                        termin_email_notified=0,  # reset so first slot sends email
                    )
                    logger.info(
                        "TERMIN_EMAIL_STORED: order_id=%s user_id=%s email=%s",
                        order_id, _termin_uid, _customer_email,
                    )
                    logger.info("EMAIL_SAVED | user=%s email=%s", _termin_uid, _customer_email)
                else:
                    logger.error(
                        "EMAIL_MISSING_IN_SESSION | user=%s order=%s — "
                        "Stripe session had no email; slot-found email will be skipped",
                        _termin_uid, order_id,
                    )
                # Read city/authority BEFORE upsert so they are stored in entitlement.
                # Priority: Stripe metadata (set at checkout time) → users table → log ERROR.
                _t_user_row = _get_termin_user(str(_termin_uid))
                _meta_city_to = metadata.get("city") or ""
                _meta_auth_to = metadata.get("authority") or ""
                _db_city_to = (_t_user_row or {}).get("city") or ""
                _db_auth_to = (_t_user_row or {}).get("authority") or ""
                logger.info("CITY_FROM_STRIPE | user=%s meta_city=%s meta_auth=%s order=%s",
                            _termin_uid, _meta_city_to, _meta_auth_to, order_id)
                if _meta_city_to:
                    _t_city = _meta_city_to
                    _t_auth = _meta_auth_to or _db_auth_to
                    _tonly_city_source = "metadata"
                elif _db_city_to:
                    _t_city = _db_city_to
                    _t_auth = _db_auth_to
                    _tonly_city_source = "users_fallback"
                    logger.error(
                        "CITY_MISSING_IN_METADATA | user=%s order=%s falling_back_to=%s — "
                        "city was not passed to Stripe session metadata",
                        _termin_uid, order_id, _db_city_to,
                    )
                else:
                    _t_city = ""
                    _t_auth = ""
                    _tonly_city_source = "unknown"
                    logger.error(
                        "CITY_UNKNOWN | user=%s order=%s — city missing from both metadata and DB. "
                        "Monitoring cannot start until user selects a city.",
                        _termin_uid, order_id,
                    )
                logger.warning(
                    "ENTITLEMENT_CITY_SOURCE | user=%s city=%s source=%s order=%s",
                    _termin_uid, _t_city, _tonly_city_source, order_id,
                )
                logger.info("CITY_IN_ENTITLEMENT | user=%s city=%s authority=%s order=%s",
                            _termin_uid, _t_city, _t_auth, order_id)
                logger.info(
                    "STRIPE_METADATA_SAVED | user=%s city=%s authority=%s order=%s",
                    _termin_uid, _t_city, _t_auth, order_id,
                )
                # Set paid_until = now + 24h so countdown display works correctly.
                from datetime import datetime as _dt24, timedelta as _td24
                _paid_until_24 = (_dt24.utcnow() + _td24(hours=24)).isoformat()
                _upsert_ent(
                    str(_termin_uid),
                    plan="single",
                    slots_total=1,
                    stripe_session_id=session_id or f"termin_{order_id}",
                    paid_until=_paid_until_24,
                    city=_t_city,
                    authority=_t_auth,
                )
                # Start monitoring immediately: create reminder using saved city+authority
                _create_termin_reminder(str(_termin_uid), _t_city, _t_auth, 6)
                logger.info("TERMIN_ONLY_PAID_ACTIVATED: order_id=%s user_id=%s city=%s auth=%s", order_id, _termin_uid, _t_city, _t_auth)
                logger.info("TERMIN_PAYMENT_SUCCESS | user=%s city=%s auth=%s order=%s", _termin_uid, _t_city, _t_auth, order_id)
                log_funnel("TERMIN_PURCHASE", int(_termin_uid), plan="termin_only")
                # Start real-time polling engine immediately after entitlement activation.
                # This ensures monitoring is running before the success message is sent.
                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp, is_polling as _isp, get_session as _get_sess_to, stop_polling as _stop_to, _cooldowns as _cd_to
                    from utils.helpers import get_user_lang as _gul_poll
                    _p_bot = request.app["bot"]
                    _p_lang = (_gul_poll(int(_termin_uid)) or "uk").strip().lower()
                    # Hard protection: stop any existing session before starting a new one
                    _existing_to = _get_sess_to(int(_termin_uid))
                    if _existing_to:
                        logger.error(
                            "TERMIN_DOUBLE_SESSION_BLOCKED | user=%s old_city=%s new_city=%s order=%s plan=termin_only",
                            _termin_uid, _existing_to.city, _t_city, order_id,
                        )
                        _stop_to(int(_termin_uid), reason="new_payment_termin_only")
                        _cd_to.pop(int(_termin_uid), None)
                    if not _isp(int(_termin_uid)):
                        _stp(
                            user_id=int(_termin_uid),
                            chat_id=int(_termin_uid),
                            city=_t_city,
                            authority=_t_auth,
                            lang=_p_lang,
                            send_fn=make_termin_send_fn(_p_bot, int(_termin_uid), _t_city, _p_lang),
                            on_reserved_fn=make_termin_on_reserved_fn(
                                _p_bot, int(_termin_uid), _t_city, _t_auth, _p_lang, state=None
                            ),
                            on_found_fn=make_termin_found_fn(_p_bot, authority=_t_auth),
                        )
                        logger.debug("TERMIN_ONLY_POLLING_STARTED: user=%s city=%s auth=%s", _termin_uid, _t_city, _t_auth)
                        logger.info("TERMIN_NEW_SESSION_STARTED | user=%s city=%s auth=%s plan=termin_only order=%s", _termin_uid, _t_city, _t_auth, order_id)
                        logger.info("TERMIN_MONITORING_STARTED | user=%s city=%s auth=%s", _termin_uid, _t_city, _t_auth)
                        logger.info("CITY_MONITOR_ACTIVATED | user=%s city=%s authority=%s source=%s order=%s",
                                    _termin_uid, _t_city, _t_auth, _tonly_city_source, order_id)
                    else:
                        logger.debug("TERMIN_ONLY_POLLING_ALREADY_RUNNING: user=%s", _termin_uid)
                except Exception as _pe:
                    logger.error("TERMIN_ONLY_POLLING_START_ERROR: user=%s err=%s", _termin_uid, _pe)
            except Exception as _tpe:
                logger.info("TERMIN_ONLY_PAID_ACTIVATION_ERROR: order_id=%s error=%s", order_id, _tpe)

        # ── Send activation message directly from webhook ─────────────────────
        # Critical UX fix: the user gets Telegram feedback immediately after
        # payment, even if they closed the Stripe/Apple Pay browser window and
        # never returned via the success_url deeplink.
        if _termin_uid and _t_city:
            try:
                from utils.helpers import get_user_lang as _gul_to_wh
                _to_wh_lang = (_gul_to_wh(int(_termin_uid)) or "uk").strip().lower()
                _act_sent_to = await _send_termin_activation_message(
                    request.app["bot"],
                    int(_termin_uid),
                    _t_city,
                    _t_auth,
                    _to_wh_lang,
                    plan="24h",
                )
                if _act_sent_to:
                    logger.info(
                        "TERMIN_ACTIVATION_MESSAGE_SENT | user=%s order=%s plan=24h city=%s auth=%s",
                        _termin_uid, order_id, _t_city, _t_auth,
                    )
                    logger.info(
                        "TERMIN_ONLY_ACTIVATION_SENT | user=%s city=%s auth=%s",
                        _termin_uid, _t_city, _t_auth,
                    )
                    db.mark_order_delivered(order_id)
                    try:
                        from utils.termin_checker import set_success_screen_shown as _sss_to
                        _sss_to(int(_termin_uid), True)
                    except Exception:
                        pass
                    try:
                        from utils.termin_redis import rset as _rset_wh_to
                        _rset_wh_to(f"termin:webhook_success_sent:{_termin_uid}", "1", ttl=300)
                    except Exception:
                        pass
                else:
                    logger.error(
                        "TERMIN_ACTIVATION_MESSAGE_FAILED | user=%s order=%s plan=24h (termin_only) "
                        "— entitlement activated but message NOT sent; returning 500 for Stripe retry",
                        _termin_uid, order_id,
                    )
                    return web.Response(status=500, text="activation_message_failed")
            except Exception as _wh_msg_e:
                logger.error(
                    "TERMIN_ONLY_ACTIVATION_SEND_FAILED | user=%s err=%s",
                    _termin_uid, _wh_msg_e,
                )
        elif _termin_uid:
            logger.warning(
                "TERMIN_ONLY_ACTIVATION_SKIPPED_NO_CITY | user=%s — city empty, cannot send message",
                _termin_uid,
            )

        # Clear FSM state leftover from Termin payment flow (e.g. TerminStates.paying_for_reminders)
        if _termin_uid:
            try:
                _fsm = dp.current_state(chat=int(_termin_uid), user=int(_termin_uid))
                await _fsm.finish()
            except Exception:
                pass

        return web.Response(status=200, text="ok")

    # === TERMIN RESERVATION / MONITOR: finalize booking or activate monitor ===
    if metadata.get("flow") == "termin":
        _termin_uid_str = metadata.get("user_id") or metadata.get("telegram_user_id")
        _monitor_type = metadata.get("monitor", "")
        _bot_inst = request.app["bot"]

        if not _termin_uid_str:
            logger.info("TERMIN_WEBHOOK_NO_USER_ID: order_id=%s", order_id)
            logger.warning("TERMIN_WEBHOOK_NO_USER_ID: order_id=%s metadata_keys=%s", order_id, list(metadata.keys()))
            db.update_order_status(order_id, OrderStatus.PAID)
            return web.Response(status=200, text="ok")

        _termin_uid = int(_termin_uid_str)

        # ── UNIVERSAL email save — runs for ALL monitor types ──────────────
        # Must execute before any branch-specific logic so that when the
        # slot-found callback fires get_customer_email() always returns a value.
        try:
            from backend.termin_db import (
                create_user as _crt_u_email,
                update_user as _upd_u_email,
            )
            _crt_u_email(str(_termin_uid))  # INSERT OR IGNORE — safe to call early
            if _customer_email and "@" in _customer_email:
                _upd_u_email(
                    str(_termin_uid),
                    customer_email=_customer_email,
                    termin_email_notified=0,
                )
                logger.info(
                    "EMAIL_SAVED | user=%s email=%s order=%s monitor=%s",
                    _termin_uid, _customer_email, order_id, _monitor_type or "reservation",
                )
            else:
                logger.error(
                    "EMAIL_MISSING_IN_SESSION | user=%s order=%s monitor=%s email=%r — "
                    "Stripe session carried no valid email; slot-found email will be skipped",
                    _termin_uid, order_id, _monitor_type or "reservation", _customer_email,
                )
        except Exception as _email_save_err:
            logger.error(
                "EMAIL_SAVE_FAILED | user=%s order=%s err=%s",
                _termin_uid, order_id, _email_save_err,
            )

        # ── Termin Monitor 24h ──
        if _monitor_type == "24h":
            try:
                from utils.helpers import get_user_lang
                from backend.termin_db import (
                    update_user as _upd_termin, create_user as _crt_termin,
                    upsert_entitlement as _upsert_ent,
                    get_user as _get_termin_user,
                    create_reminder as _create_termin_reminder,
                )
                _m_lang = (get_user_lang(_termin_uid) or "en").strip().lower()
                # Stripe metadata is the primary source of truth for city/authority.
                # If absent, fall back to DB and log ERROR — never silently use a hardcoded city.
                _meta_city_24h = metadata.get("city") or ""
                _meta_auth_24h = metadata.get("authority") or ""
                logger.info(
                    "CITY_IN_METADATA | user=%s city=%r authority=%r order=%s monitor=24h",
                    _termin_uid, _meta_city_24h, _meta_auth_24h, order_id,
                )
                if _meta_city_24h:
                    _city = _meta_city_24h
                    _t_auth = _meta_auth_24h or "buergeramt"
                    _city_src_24h = "metadata"
                else:
                    _db24_row = _get_termin_user(str(_termin_uid)) or {}
                    _city = _db24_row.get("city") or ""
                    _t_auth = _db24_row.get("authority") or "buergeramt"
                    _city_src_24h = "users_fallback" if _city else "unknown"
                    logger.error(
                        "CITY_MISSING_IN_METADATA | user=%s order=%s monitor=24h "
                        "falling_back_to=%r — city was absent from Stripe session metadata",
                        _termin_uid, order_id, _city,
                    )
                logger.info(
                    "CITY_FROM_STRIPE | user=%s city=%r authority=%r source=%s order=%s monitor=24h",
                    _termin_uid, _city, _t_auth, _city_src_24h, order_id,
                )
                logger.info(
                    "STRIPE_METADATA_SAVED | user=%s city=%s authority=%s order=%s monitor=24h",
                    _termin_uid, _city, _t_auth, order_id,
                )

                # Activate has_paid_termin + entitlement (same logic as termin_only branch)
                _crt_termin(str(_termin_uid))
                _upd_termin(str(_termin_uid), has_paid_termin=1, city=_city, authority=_t_auth)
                # Store Stripe customer email for slot-found email notifications
                if _customer_email:
                    _upd_termin(
                        str(_termin_uid),
                        customer_email=_customer_email,
                        termin_email_notified=0,  # reset for fresh monitoring period
                    )
                    logger.info(
                        "TERMIN_EMAIL_STORED: order_id=%s user_id=%s email=%s",
                        order_id, _termin_uid, _customer_email,
                    )
                    logger.info("EMAIL_SAVED | user=%s email=%s", _termin_uid, _customer_email)
                else:
                    logger.error(
                        "EMAIL_MISSING_IN_SESSION | user=%s order=%s — "
                        "Stripe session had no email; slot-found email will be skipped",
                        _termin_uid, order_id,
                    )
                from datetime import datetime as _dt24h, timedelta as _td24h
                _paid_until_24h = (_dt24h.utcnow() + _td24h(hours=24)).isoformat()
                _upsert_ent(
                    str(_termin_uid),
                    plan="single",
                    slots_total=1,
                    stripe_session_id=session_id or f"termin_{order_id}",
                    paid_until=_paid_until_24h,
                    city=_city,
                    authority=_t_auth,
                )
                logger.info(
                    "CITY_IN_ENTITLEMENT | user=%s city=%r authority=%r source=%s order=%s monitor=24h",
                    _termin_uid, _city, _t_auth, _city_src_24h, order_id,
                )
                print("DB WRITE:", {
                    "user_id": _termin_uid,
                    "city": _city,
                    "authority": _t_auth,
                    "plan": "single",
                    "paid_until": _paid_until_24h,
                }, flush=True)
                _create_termin_reminder(str(_termin_uid), _city, _t_auth, 6)
                logger.info(
                    "ACTIVATING_MONITOR | user=%s city=%s authority=%s order=%s",
                    _termin_uid, _city, _t_auth, order_id,
                )
                logger.info("TERMIN_PAYMENT_SUCCESS | user=%s city=%s auth=%s order=%s", _termin_uid, _city, _t_auth, order_id)
                logger.info(
                    "TERMIN_ANALYTICS | event=payment_completed plan=24h city=%s authority=%s order_id=%s user_id=%s",
                    _city, _t_auth, order_id, _termin_uid,
                )
                logger.info(
                    "TERMIN_PAYMENT_ACTIVATED | order_id=%s user_id=%s plan=24h city=%s authority=%s",
                    order_id, _termin_uid, _city, _t_auth,
                )
                log_funnel(
                    "TERMIN_PURCHASE",
                    int(_termin_uid),
                    doc_type=order.get("doc_type"),
                    lang=_m_lang,
                    city=str(_city).strip() if _city else None,
                    plan="24h",
                    order_id=order_id,
                )

                # Start real-time polling engine immediately after entitlement activation
                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp, is_polling as _isp, get_session as _get_sess_24h, stop_polling as _stop_24h, _cooldowns as _cd_24h
                    # Hard protection: stop any existing session before starting a new one
                    _existing_24h = _get_sess_24h(int(_termin_uid))
                    if _existing_24h:
                        logger.error(
                            "TERMIN_DOUBLE_SESSION_BLOCKED | user=%s old_city=%s new_city=%s order=%s plan=24h",
                            _termin_uid, _existing_24h.city, _city, order_id,
                        )
                        _stop_24h(int(_termin_uid), reason="new_payment_24h")
                        _cd_24h.pop(int(_termin_uid), None)
                    if not _isp(int(_termin_uid)):
                        _stp(
                            user_id=int(_termin_uid),
                            chat_id=int(_termin_uid),
                            city=_city,
                            authority=_t_auth,
                            lang=_m_lang,
                            send_fn=make_termin_send_fn(_bot_inst, int(_termin_uid), _city, _m_lang),
                            on_reserved_fn=make_termin_on_reserved_fn(
                                _bot_inst, int(_termin_uid), _city, _t_auth, _m_lang, state=None
                            ),
                            on_found_fn=make_termin_found_fn(_bot_inst, authority=_t_auth),
                        )
                        logger.debug("TERMIN_MONITOR_24H_POLLING_STARTED: user=%s city=%s auth=%s", _termin_uid, _city, _t_auth)
                        logger.info("TERMIN_NEW_SESSION_STARTED | user=%s city=%s auth=%s plan=24h order=%s", _termin_uid, _city, _t_auth, order_id)
                        logger.info("TERMIN_MONITORING_STARTED | user=%s city=%s auth=%s", _termin_uid, _city, _t_auth)
                        logger.info(
                            "CITY_MONITOR_ACTIVATED | user=%s city=%r authority=%r source=%s order=%s monitor=24h",
                            _termin_uid, _city, _t_auth, _city_src_24h, order_id,
                        )
                        _paid_city_24h = metadata.get("city") or ""
                        if _paid_city_24h and _city != _paid_city_24h:
                            logger.critical(
                                "CITY_MISMATCH | user=%s activated=%r paid_for=%r order=%s monitor=24h "
                                "— selected city does not match paid city",
                                _termin_uid, _city, _paid_city_24h, order_id,
                            )
                        logger.info(
                            "TERMIN_ANALYTICS | event=monitoring_started plan=24h city=%s authority=%s order_id=%s user_id=%s",
                            _city, _t_auth, order_id, _termin_uid,
                        )
                        # Clear any pre-payment cached result so the first poll
                        # makes a fresh HTTP request instead of reusing a stale cache entry.
                        try:
                            from utils.termin_checker import _city_result_cache as _crc_24h
                            _crc_24h.pop(f"{_city}:{_t_auth}", None)
                        except Exception:
                            pass
                    else:
                        logger.debug("TERMIN_MONITOR_24H_POLLING_ALREADY_RUNNING: user=%s", _termin_uid)
                except Exception as _pe:
                    logger.error("TERMIN_MONITOR_24H_POLLING_START_ERROR: user=%s err=%s", _termin_uid, _pe)

                db.update_order_status(order_id, OrderStatus.PAID)
                _act_sent_24h = await _send_termin_activation_message(_bot_inst, int(_termin_uid), _city, _t_auth, _m_lang, plan="24h")
                if _act_sent_24h:
                    logger.info(
                        "TERMIN_ACTIVATION_MESSAGE_SENT | user=%s order=%s plan=24h city=%s authority=%s",
                        _termin_uid, order_id, _city, _t_auth,
                    )
                    # Mark as delivered only after confirmed send, so Stripe retries
                    # can re-attempt activation if the message failed.
                    try:
                        db.mark_order_delivered(order_id)
                    except Exception as _md_24h:
                        logger.warning("MARK_ORDER_DELIVERED_FAILED 24h | order=%s err=%s", order_id, _md_24h)
                    # Lift the barrier AFTER the activation message is delivered to the user.
                    try:
                        from utils.termin_checker import set_success_screen_shown as _sss_m
                        _sss_m(int(_termin_uid), True)
                    except Exception:
                        pass
                else:
                    logger.error(
                        "TERMIN_ACTIVATION_MESSAGE_FAILED | user=%s order=%s plan=24h "
                        "— entitlement activated but message NOT sent; returning 500 for Stripe retry",
                        _termin_uid, order_id,
                    )
                    return web.Response(status=500, text="activation_message_failed")
            except Exception as _me:
                print(f"CRITICAL ERROR TERMIN_MONITOR_ACTIVATION: order_id={order_id} error={_me}", flush=True)
                logger.info("TERMIN_MONITOR_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _me)
                logger.error("TERMIN_MONITOR_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _me)
            return web.Response(status=200, text="ok")

        # ── Termin Monitor 7-day ──
        if _monitor_type == "7day":
            try:
                from utils.helpers import get_user_lang
                from backend.termin_db import (
                    update_user as _upd_7d, create_user as _crt_7d,
                    upsert_entitlement as _upsert_7d,
                    get_user as _get_7d_user,
                    create_reminder as _create_7d_reminder,
                )
                from datetime import datetime as _dt7, timedelta as _td7
                _7d_lang = (get_user_lang(_termin_uid) or "en").strip().lower()
                # Stripe metadata is the primary source of truth for city/authority.
                # If absent, fall back to DB and log ERROR — never silently use a hardcoded city.
                _meta_city_7d = metadata.get("city") or ""
                _meta_auth_7d = metadata.get("authority") or ""
                logger.info(
                    "CITY_IN_METADATA | user=%s city=%r authority=%r order=%s monitor=7day",
                    _termin_uid, _meta_city_7d, _meta_auth_7d, order_id,
                )
                if _meta_city_7d:
                    _7d_city = _meta_city_7d
                    _7d_auth = _meta_auth_7d or "buergeramt"
                    _city_src_7d = "metadata"
                else:
                    _db7d_row = _get_7d_user(str(_termin_uid)) or {}
                    _7d_city = _db7d_row.get("city") or ""
                    _7d_auth = _db7d_row.get("authority") or "buergeramt"
                    _city_src_7d = "users_fallback" if _7d_city else "unknown"
                    logger.error(
                        "CITY_MISSING_IN_METADATA | user=%s order=%s monitor=7day "
                        "falling_back_to=%r — city was absent from Stripe session metadata",
                        _termin_uid, order_id, _7d_city,
                    )
                logger.info(
                    "CITY_FROM_STRIPE | user=%s city=%r authority=%r source=%s order=%s monitor=7day",
                    _termin_uid, _7d_city, _7d_auth, _city_src_7d, order_id,
                )
                _paid_until_7d = (_dt7.utcnow() + _td7(days=7)).isoformat()

                _crt_7d(str(_termin_uid))
                _upd_7d(str(_termin_uid), has_paid_termin=1, city=_7d_city, authority=_7d_auth)
                _upsert_7d(
                    str(_termin_uid),
                    plan="7day",
                    slots_total=1,
                    stripe_session_id=session_id or f"7day_{order_id}",
                    paid_until=_paid_until_7d,
                    city=_7d_city,
                    authority=_7d_auth,
                )
                logger.info(
                    "CITY_IN_ENTITLEMENT | user=%s city=%r authority=%r source=%s order=%s monitor=7day",
                    _termin_uid, _7d_city, _7d_auth, _city_src_7d, order_id,
                )
                _create_7d_reminder(str(_termin_uid), _7d_city, _7d_auth, 6)
                logger.info(
                    "TERMIN_7DAY_ACTIVATED | user=%s city=%s auth=%s order=%s until=%s",
                    _termin_uid, _7d_city, _7d_auth, order_id, _paid_until_7d,
                )

                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp_7d, is_polling as _isp_7d, get_session as _get_sess_7d, stop_polling as _stop_7d, _cooldowns as _cd_7d
                    _bot_inst_7d = request.app["bot"]
                    # Hard protection: stop any existing session before starting a new one
                    _existing_7d = _get_sess_7d(int(_termin_uid))
                    if _existing_7d:
                        logger.error(
                            "TERMIN_DOUBLE_SESSION_BLOCKED | user=%s old_city=%s new_city=%s order=%s plan=7day",
                            _termin_uid, _existing_7d.city, _7d_city, order_id,
                        )
                        _stop_7d(int(_termin_uid), reason="new_payment_7day")
                        _cd_7d.pop(int(_termin_uid), None)
                    if not _isp_7d(int(_termin_uid)):
                        _stp_7d(
                            user_id=int(_termin_uid),
                            chat_id=int(_termin_uid),
                            city=_7d_city,
                            authority=_7d_auth,
                            lang=_7d_lang,
                            send_fn=make_termin_send_fn(_bot_inst_7d, int(_termin_uid), _7d_city, _7d_lang),
                            on_reserved_fn=make_termin_on_reserved_fn(
                                _bot_inst_7d, int(_termin_uid), _7d_city, _7d_auth, _7d_lang, state=None
                            ),
                            on_found_fn=make_termin_found_fn(_bot_inst_7d, authority=_7d_auth),
                        )
                        logger.info("TERMIN_NEW_SESSION_STARTED | user=%s city=%s auth=%s plan=7day order=%s", _termin_uid, _7d_city, _7d_auth, order_id)
                        logger.info("TERMIN_7DAY_POLLING_STARTED | user=%s city=%s auth=%s", _termin_uid, _7d_city, _7d_auth)
                        logger.info(
                            "CITY_MONITOR_ACTIVATED | user=%s city=%r authority=%r source=%s order=%s monitor=7day",
                            _termin_uid, _7d_city, _7d_auth, _city_src_7d, order_id,
                        )
                        _paid_city_7d = metadata.get("city") or ""
                        if _paid_city_7d and _7d_city != _paid_city_7d:
                            logger.critical(
                                "CITY_MISMATCH | user=%s activated=%r paid_for=%r order=%s monitor=7day "
                                "— selected city does not match paid city",
                                _termin_uid, _7d_city, _paid_city_7d, order_id,
                            )
                        logger.info(
                            "TERMIN_ANALYTICS | event=monitoring_started plan=7day city=%s authority=%s order_id=%s user_id=%s",
                            _7d_city, _7d_auth, order_id, _termin_uid,
                        )
                        # Clear any pre-payment cached result so the first poll
                        # makes a fresh HTTP request instead of reusing a stale cache entry.
                        try:
                            from utils.termin_checker import _city_result_cache as _crc_7d
                            _crc_7d.pop(f"{_7d_city}:{_7d_auth}", None)
                        except Exception:
                            pass
                    else:
                        logger.debug("TERMIN_7DAY_POLLING_ALREADY_RUNNING: user=%s", _termin_uid)
                except Exception as _7d_pe:
                    logger.error("TERMIN_7DAY_POLLING_START_ERROR: user=%s err=%s", _termin_uid, _7d_pe)

                db.update_order_status(order_id, OrderStatus.PAID)
                logger.info(
                    "TERMIN_ANALYTICS | event=payment_completed plan=7day city=%s authority=%s order_id=%s user_id=%s",
                    _7d_city, _7d_auth, order_id, _termin_uid,
                )
                log_funnel(
                    "TERMIN_PURCHASE",
                    int(_termin_uid),
                    doc_type=order.get("doc_type"),
                    lang=_7d_lang,
                    city=str(_7d_city).strip() if _7d_city else None,
                    plan="7day",
                    order_id=order_id,
                )
                try:
                    from handlers.post_payment_ux import get_termin_activating_message
                    await _bot_inst.send_message(
                        int(_termin_uid),
                        get_termin_activating_message(_7d_lang),
                        parse_mode="HTML",
                    )
                except Exception as _ta7:
                    logger.debug("TERMIN_ACTIVATING_MSG_7D_FAIL user=%s err=%s", _termin_uid, _ta7)
                _act_sent_7d = await _send_termin_activation_message(_bot_inst, int(_termin_uid), _7d_city, _7d_auth, _7d_lang, plan="7day")
                if _act_sent_7d:
                    logger.info(
                        "TERMIN_ACTIVATION_MESSAGE_SENT | user=%s order=%s plan=7day city=%s authority=%s",
                        _termin_uid, order_id, _7d_city, _7d_auth,
                    )
                    try:
                        db.mark_order_delivered(order_id)
                    except Exception as _md_7d:
                        logger.warning("MARK_ORDER_DELIVERED_FAILED 7day | order=%s err=%s", order_id, _md_7d)
                    try:
                        from utils.termin_checker import set_success_screen_shown as _sss_7d
                        _sss_7d(int(_termin_uid), True)
                    except Exception:
                        pass
                else:
                    logger.error(
                        "TERMIN_ACTIVATION_MESSAGE_FAILED | user=%s order=%s plan=7day "
                        "— entitlement activated but message NOT sent; returning 500 for Stripe retry",
                        _termin_uid, order_id,
                    )
                    return web.Response(status=500, text="activation_message_failed")
            except Exception as _7de:
                logger.error("TERMIN_7DAY_ACTIVATION_FAILED | order=%s error=%s", order_id, _7de)
            return web.Response(status=200, text="ok")

        # ── Termin Monitor 30-day ──
        if _monitor_type == "30day":
            try:
                from utils.helpers import get_user_lang
                from backend.termin_db import (
                    update_user as _upd_30d, create_user as _crt_30d,
                    upsert_entitlement as _upsert_30d,
                    get_user as _get_30d_user,
                    create_reminder as _create_30d_reminder,
                )
                from datetime import datetime as _dt30, timedelta as _td30
                _30d_lang = (get_user_lang(_termin_uid) or "en").strip().lower()
                _meta_city_30d = metadata.get("city") or ""
                _meta_auth_30d = metadata.get("authority") or ""
                logger.info(
                    "CITY_IN_METADATA | user=%s city=%r authority=%r order=%s monitor=30day",
                    _termin_uid, _meta_city_30d, _meta_auth_30d, order_id,
                )
                if _meta_city_30d:
                    _30d_city = _meta_city_30d
                    _30d_auth = _meta_auth_30d or "buergeramt"
                    _city_src_30d = "metadata"
                else:
                    _db30d_row = _get_30d_user(str(_termin_uid)) or {}
                    _30d_city = _db30d_row.get("city") or ""
                    _30d_auth = _db30d_row.get("authority") or "buergeramt"
                    _city_src_30d = "users_fallback" if _30d_city else "unknown"
                    logger.error(
                        "CITY_MISSING_IN_METADATA | user=%s order=%s monitor=30day "
                        "falling_back_to=%r — city was absent from Stripe session metadata",
                        _termin_uid, order_id, _30d_city,
                    )
                logger.info(
                    "CITY_FROM_STRIPE | user=%s city=%r authority=%r source=%s order=%s monitor=30day",
                    _termin_uid, _30d_city, _30d_auth, _city_src_30d, order_id,
                )
                _paid_until_30d = (_dt30.utcnow() + _td30(days=30)).isoformat()

                _crt_30d(str(_termin_uid))
                _upd_30d(str(_termin_uid), has_paid_termin=1, city=_30d_city, authority=_30d_auth)
                _upsert_30d(
                    str(_termin_uid),
                    plan="30day",
                    slots_total=1,
                    stripe_session_id=session_id or f"30day_{order_id}",
                    paid_until=_paid_until_30d,
                    city=_30d_city,
                    authority=_30d_auth,
                )
                logger.info(
                    "CITY_IN_ENTITLEMENT | user=%s city=%r authority=%r source=%s order=%s monitor=30day",
                    _termin_uid, _30d_city, _30d_auth, _city_src_30d, order_id,
                )
                _create_30d_reminder(str(_termin_uid), _30d_city, _30d_auth, 6)
                logger.info(
                    "TERMIN_30DAY_ACTIVATED | user=%s city=%s auth=%s order=%s until=%s",
                    _termin_uid, _30d_city, _30d_auth, order_id, _paid_until_30d,
                )

                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp_30d, is_polling as _isp_30d, get_session as _get_sess_30d, stop_polling as _stop_30d, _cooldowns as _cd_30d
                    _bot_inst_30d = request.app["bot"]
                    _existing_30d = _get_sess_30d(int(_termin_uid))
                    if _existing_30d:
                        logger.error(
                            "TERMIN_DOUBLE_SESSION_BLOCKED | user=%s old_city=%s new_city=%s order=%s plan=30day",
                            _termin_uid, _existing_30d.city, _30d_city, order_id,
                        )
                        _stop_30d(int(_termin_uid), reason="new_payment_30day")
                        _cd_30d.pop(int(_termin_uid), None)
                    if not _isp_30d(int(_termin_uid)):
                        _stp_30d(
                            user_id=int(_termin_uid),
                            chat_id=int(_termin_uid),
                            city=_30d_city,
                            authority=_30d_auth,
                            lang=_30d_lang,
                            send_fn=make_termin_send_fn(_bot_inst_30d, int(_termin_uid), _30d_city, _30d_lang),
                            on_reserved_fn=make_termin_on_reserved_fn(
                                _bot_inst_30d, int(_termin_uid), _30d_city, _30d_auth, _30d_lang, state=None
                            ),
                            on_found_fn=make_termin_found_fn(_bot_inst_30d, authority=_30d_auth),
                        )
                        logger.info("TERMIN_NEW_SESSION_STARTED | user=%s city=%s auth=%s plan=30day order=%s", _termin_uid, _30d_city, _30d_auth, order_id)
                        logger.info(
                            "TERMIN_ANALYTICS | event=monitoring_started plan=30day city=%s authority=%s order_id=%s user_id=%s",
                            _30d_city, _30d_auth, order_id, _termin_uid,
                        )
                        try:
                            from utils.termin_checker import _city_result_cache as _crc_30d
                            _crc_30d.pop(f"{_30d_city}:{_30d_auth}", None)
                        except Exception:
                            pass
                    else:
                        logger.debug("TERMIN_30DAY_POLLING_ALREADY_RUNNING: user=%s", _termin_uid)
                except Exception as _30d_pe:
                    logger.error("TERMIN_30DAY_POLLING_START_ERROR: user=%s err=%s", _termin_uid, _30d_pe)

                db.update_order_status(order_id, OrderStatus.PAID)
                logger.info(
                    "TERMIN_ANALYTICS | event=payment_completed plan=30day city=%s authority=%s order_id=%s user_id=%s",
                    _30d_city, _30d_auth, order_id, _termin_uid,
                )
                log_funnel(
                    "TERMIN_PURCHASE",
                    int(_termin_uid),
                    doc_type=order.get("doc_type"),
                    lang=_30d_lang,
                    city=str(_30d_city).strip() if _30d_city else None,
                    plan="30day",
                    order_id=order_id,
                )
                try:
                    from handlers.post_payment_ux import get_termin_activating_message
                    await _bot_inst.send_message(
                        int(_termin_uid),
                        get_termin_activating_message(_30d_lang),
                        parse_mode="HTML",
                    )
                except Exception as _ta30:
                    logger.debug("TERMIN_ACTIVATING_MSG_30D_FAIL user=%s err=%s", _termin_uid, _ta30)
                _act_sent_30d = await _send_termin_activation_message(_bot_inst, int(_termin_uid), _30d_city, _30d_auth, _30d_lang, plan="30day")
                if _act_sent_30d:
                    logger.info(
                        "TERMIN_ACTIVATION_MESSAGE_SENT | user=%s order=%s plan=30day city=%s authority=%s",
                        _termin_uid, order_id, _30d_city, _30d_auth,
                    )
                    try:
                        db.mark_order_delivered(order_id)
                    except Exception as _md_30d:
                        logger.warning("MARK_ORDER_DELIVERED_FAILED 30day | order=%s err=%s", order_id, _md_30d)
                    try:
                        from utils.termin_checker import set_success_screen_shown as _sss_30d
                        _sss_30d(int(_termin_uid), True)
                    except Exception:
                        pass
                else:
                    logger.error(
                        "TERMIN_ACTIVATION_MESSAGE_FAILED | user=%s order=%s plan=30day "
                        "— entitlement activated but message NOT sent; returning 500 for Stripe retry",
                        _termin_uid, order_id,
                    )
                    return web.Response(status=500, text="activation_message_failed")
            except Exception as _30de:
                logger.error("TERMIN_30DAY_ACTIVATION_FAILED | order=%s error=%s", order_id, _30de)
            return web.Response(status=200, text="ok")

        # ── Termin Extend 24h ──
        if _monitor_type == "extend_24h":
            try:
                from handlers.payments import _activate_termin_extend
                from utils.helpers import get_user_lang
                _e_lang = (get_user_lang(_termin_uid) or "en").strip().lower()
                db.update_order_status(order_id, OrderStatus.PAID)
                await _activate_termin_extend(_bot_inst, _termin_uid, _e_lang)
                logger.info("TERMIN_EXTEND_ACTIVATED: order_id=%s user_id=%s", order_id, _termin_uid)
                logger.info("TERMIN_EXTEND_ACTIVATED: order_id=%s user_id=%s", order_id, _termin_uid)
            except Exception as _ee:
                logger.info("TERMIN_EXTEND_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _ee)
                logger.error("TERMIN_EXTEND_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _ee)
            return web.Response(status=200, text="ok")

        # ── Termin Family Bundle (V1 DB-backed, idempotent) ──
        if _monitor_type == "family":
            try:
                from handlers.termin import _activate_termin_family
                from utils.helpers import get_user_lang
                _f_lang = (get_user_lang(_termin_uid) or "en").strip().lower()
                # Prefer session_id already parsed above; fall back to order column
                _f_session = session_id or (order.get("stripe_session_id") or "")
                db.update_order_status(order_id, OrderStatus.PAID)
                await _activate_termin_family(
                    _bot_inst, _termin_uid, _f_lang,
                    stripe_session_id=_f_session,
                )
                logger.info("TERMIN_FAMILY_ACTIVATED: order_id=%s user_id=%s", order_id, _termin_uid)
            except Exception as _fe:
                logger.info("TERMIN_FAMILY_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _fe)
                logger.error("TERMIN_FAMILY_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _fe)
            return web.Response(status=200, text="ok")

        # ── Termin Priority Boost ──
        if _monitor_type == "priority_boost":
            try:
                from handlers.payments import _activate_termin_priority
                from utils.helpers import get_user_lang
                _p_lang = (get_user_lang(_termin_uid) or "en").strip().lower()
                db.update_order_status(order_id, OrderStatus.PAID)
                await _activate_termin_priority(_bot_inst, _termin_uid, _p_lang)
                logger.info("TERMIN_PRIORITY_ACTIVATED: order_id=%s user_id=%s", order_id, _termin_uid)
                logger.info("TERMIN_PRIORITY_ACTIVATED: order_id=%s user_id=%s", order_id, _termin_uid)
            except Exception as _pe:
                logger.info("TERMIN_PRIORITY_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _pe)
                logger.error("TERMIN_PRIORITY_ACTIVATION_FAILED: order_id=%s error=%s", order_id, _pe)
            return web.Response(status=200, text="ok")

        # ── Termin Reservation (existing Stage 17 flow) ──
        try:
            from handlers.termin import finalize_termin_webhook_payment
            _fin_ok = await finalize_termin_webhook_payment(
                _bot_inst, _termin_uid, dict(metadata),
            )
            if _fin_ok:
                logger.info("TERMIN_RESERVATION_PAID: order_id=%s user_id=%s", order_id, _termin_uid_str)
                try:
                    _fsm = dp.current_state(chat=_termin_uid, user=_termin_uid)
                    await _fsm.finish()
                except Exception:
                    pass
            else:
                logger.debug("TERMIN_WEBHOOK_FINALIZE_SKIPPED: order_id=%s user_id=%s", order_id, _termin_uid_str)
        except Exception as _te:
            print(f"CRITICAL ERROR TERMIN_WEBHOOK: order_id={order_id} error={_te}", flush=True)
            logger.info("TERMIN_WEBHOOK_ERROR: order_id=%s error=%s", order_id, _te)
            logger.error("TERMIN_WEBHOOK_ERROR: order_id=%s error=%s", order_id, _te)

        db.update_order_status(order_id, OrderStatus.PAID)
        return web.Response(status=200, text="ok")

    # === DELIVER PDF ===
    user_id = order.get("user_id")
    if not user_id:
        logger.info("WEBHOOK_ERROR: NO_USER_ID order_id=%s", order_id)
        return web.Response(status=200, text="ok")

    # === DELIVER PDF FROM WEBHOOK (single source of truth) ===
    # Webhook is now responsible for all PDF delivery. The deep-link handler
    # is UX-status-only and never calls deliver_document_after_payment.
    # claim_delivery() inside deliver_document_after_payment provides the
    # atomic guard against any concurrent duplicate calls.
    from utils.helpers import get_user_lang as _wh_get_lang
    _wh_bot = request.app["bot"]
    _db_lang = (_wh_get_lang(int(user_id)) or "").strip().lower()
    if _db_lang == "ua":
        _db_lang = "uk"
    _order_lang = (order.get("lang") or "").strip().lower()
    if _order_lang == "ua":
        _order_lang = "uk"
    _meta_lang = (metadata.get("user_lang") or "").strip().lower()
    if _meta_lang == "ua":
        _meta_lang = "uk"
    _wh_lang_raw = _db_lang or _order_lang or _meta_lang or "uk"
    if _wh_lang_raw not in ("uk", "en", "de", "pl", "tr", "ar"):
        _wh_lang_raw = "uk"
    _wh_lang = _wh_lang_raw
    _WEBHOOK_LANG_KEYS = frozenset({"uk", "en", "de", "pl", "tr", "ar"})
    if _wh_lang not in _WEBHOOK_LANG_KEYS:
        _wh_lang = "uk"
    logger.info(
        "WEBHOOK_LANG_RESOLVED order=%s db=%s order_col=%s meta=%s effective=%s",
        order_id,
        _db_lang,
        _order_lang,
        _meta_lang,
        _wh_lang,
    )
    logger.info("WEBHOOK_DELIVERY_TRIGGERED | order=%s user=%s", order_id, user_id)
    try:
        # deliver_document_after_payment returns the PDF file path (str) on success,
        # True when delivered but path unavailable, or False/None on failure.
        # skip_pdf_send=True: PDF is NOT sent inside the function; we send it here
        # AFTER email so caption can include the email-status line — ONE message total.
        _delivery_result = await deliver_document_after_payment(
            _wh_bot, order_id, skip_pdf_send=True
        )
        _delivery_ok = bool(_delivery_result)
        _delivered_pdf_path = _delivery_result if isinstance(_delivery_result, str) else None

        if _delivery_ok:
            logger.info("WEBHOOK_DELIVERY_SUCCESS | order=%s user=%s", order_id, user_id)
            logger.info("FUNNEL | step=pdf_sent_webhook order_id=%s user_id=%s", order_id, user_id)
            try:
                db.mark_order_delivered(order_id)
            except Exception as _md_err:
                logger.warning("WEBHOOK_MARK_DELIVERED_FAILED: order_id=%s err=%s", order_id, _md_err)

            # REFERRAL SYSTEM DISABLED — DB schema is preserved, logic is off.
            # To re-enable: remove this comment block and uncomment the code below.
            # try:
            #     _ref_code_used = db.get_referral_code_used(int(user_id))
            #     if _ref_code_used:
            #         _awarded = db.register_referral(_ref_code_used, int(user_id))
            #         if _awarded:
            #             logger.info("REFERRAL_AWARDED | referee=%s code=%s", user_id, _ref_code_used)
            # except Exception as _ref_err:
            #     logger.debug("REFERRAL_AWARD_ERROR: order=%s err=%s", order_id, _ref_err)

            # Promo usage was already recorded at application time (process_promo_code).
            # No post-payment action needed — discounted price was passed to Stripe directly.

            # =================================================================
            # EMAIL DELIVERY — must happen BEFORE pdf_cleanup (file still on disk)
            # After this block we send ONE consolidated receipt message.
            # =================================================================
            _refreshed_order = db.get_order(order_id)
            _doc_type_for_msg = (_refreshed_order or {}).get("doc_type", "document")
            _email_lang = _wh_lang
            _email_ok = False
            _email_kill_switch = False

            logger.info("EMAIL_FLOW_START order=%s", order_id)

            from utils.user_email import (
                resolve_email_for_order,
                persist_resolved_email_if_missing_on_user,
            )

            _stripe_email_now = _stripe_checkout_resolved_email(session, metadata)
            _customer_email = resolve_email_for_order(
                int(user_id),
                order_id,
                stripe_hint=_stripe_email_now or _customer_email,
                db=db,
            )
            _email_final = _stripe_checkout_resolved_email(session, metadata) or _customer_email
            if _email_final:
                persist_resolved_email_if_missing_on_user(
                    int(user_id), order_id, _email_final, db=db
                )

            if _email_final:
                logger.info("USER_EMAIL_RESOLVED=%s order=%s", _email_final, order_id)
            else:
                logger.error(
                    "NO_EMAIL_ABORT: order=%s stripe_session=%s stripe_hint=%s db_resolved=%s"
                    " — no email found in Stripe session, DB, or user_data",
                    order_id,
                    bool(_stripe_email_now),
                    bool(_stripe_email_now or _customer_email),
                    bool(_customer_email),
                )

            if not _email_final or not str(_email_final).strip():
                logger.error("EMAIL_MISSING_SKIP_SEND order=%s", order_id)
            else:
                try:
                    from utils.email_sender import send_pdf_by_email
                    from backend.settings import settings as _settings

                    logger.info(
                        "EMAIL_DEBUG | order=%s email=%s enabled=%s",
                        order_id, _email_final, _settings.email.ENABLED,
                    )

                    if not _settings.email.ENABLED:
                        _email_kill_switch = True
                        logger.warning(
                            "EMAIL_KILL_SWITCH_OFF: order=%s — EMAIL_ENABLED=0 "
                            "(PDF is delivered via Telegram in this message)",
                            order_id,
                        )
                    else:
                        _claim_won = db.claim_email_send(order_id)
                        logger.info(
                            "EMAIL_DEBUG | order=%s claim_won=%s",
                            order_id, _claim_won,
                        )
                        if not _claim_won:
                            logger.info("EMAIL_ALREADY_CLAIMED: order=%s — skipping duplicate", order_id)
                        else:
                            _pdf_path = _delivered_pdf_path or (_refreshed_order or {}).get("file_path")
                            _pdf_exists = bool(_pdf_path and os.path.exists(_pdf_path))
                            _pdf_size   = os.path.getsize(_pdf_path) if _pdf_exists else 0
                            logger.info(
                                "EMAIL_DEBUG | order=%s pdf_path=%s exists=%s size=%d",
                                order_id, _pdf_path, _pdf_exists, _pdf_size,
                            )
                            logger.info(
                                "ATTACHMENT_PATH=%s exists=%s size=%d",
                                _pdf_path, _pdf_exists, _pdf_size,
                            )
                            if _pdf_exists and _pdf_size > 0:
                                logger.info(
                                    "EMAIL_SEND_START order=%s email=%s",
                                    order_id,
                                    _email_final,
                                )
                                logger.info(
                                    "EMAIL_DEBUG | sending PDF order=%s path=%s to=%s",
                                    order_id, _pdf_path, _email_final,
                                )
                                _UMMELDUNG_NOTE = {
                                    "uk": "Це частина 1. Інші частини документа доступні у Telegram.",
                                    "en": "This is part 1. Other parts of the document are available in Telegram.",
                                    "de": "Dies ist Teil 1. Die anderen Teile des Dokuments sind in Telegram verfügbar.",
                                    "pl": "To jest część 1. Pozostałe części dokumentu są dostępne w Telegramie.",
                                    "tr": "Bu 1. kısımdır. Belgenin diğer kısımları Telegram'da mevcuttur.",
                                    "ar": "هذا هو الجزء 1. الأجزاء الأخرى من المستند متاحة في Telegram.",
                                }
                                _ummeldung_note = (
                                    _UMMELDUNG_NOTE.get(_email_lang, _UMMELDUNG_NOTE["en"])
                                    if (_doc_type_for_msg or "").lower() == "ummeldung"
                                    else ""
                                )
                                try:
                                    _email_ok = await asyncio.wait_for(
                                        send_pdf_by_email(
                                            to_email=_email_final,
                                            pdf_path=_pdf_path,
                                            doc_type=_doc_type_for_msg,
                                            lang=_email_lang,
                                            extra_note=_ummeldung_note,
                                        ),
                                        timeout=20.0,
                                    )
                                except asyncio.TimeoutError:
                                    logger.error("EMAIL_FAILED order=%s error=%s", order_id, "timeout after 20s")
                                    _email_ok = False
                                except Exception as _send_err:
                                    logger.error(
                                        "EMAIL_FAILED order=%s error=%s",
                                        order_id,
                                        repr(_send_err),
                                    )
                                    _email_ok = False
                                if _email_ok:
                                    logger.info("EMAIL_SEND_SUCCESS order=%s", order_id)
                                    if _claim_won:  # guard: only confirm when this call owned the claim
                                        db.confirm_email_sent(order_id)
                                else:
                                    logger.error(
                                        "EMAIL_FAILED order=%s error=%s",
                                        order_id, "send_pdf_by_email returned False",
                                    )
                                    # Release the claim so the next Stripe replay or retry
                                    # attempt can re-send the email (claim is already 1→0).
                                    try:
                                        db.release_email_claim(order_id)
                                    except Exception as _rel_err:
                                        logger.error(
                                            "EMAIL_CLAIM_RELEASE_FAILED order=%s err=%s",
                                            order_id, _rel_err,
                                        )
                            elif not _pdf_exists:
                                logger.error(
                                    "PDF_MISSING order=%s path=%r — email aborted",
                                    order_id, _pdf_path,
                                )
                                try:
                                    db.release_email_claim(order_id)
                                except Exception as _rel_pm:
                                    logger.error("EMAIL_CLAIM_RELEASE_FAILED order=%s err=%s", order_id, _rel_pm)
                            else:
                                logger.error(
                                    "PDF_MISSING order=%s path=%r size=0 — email aborted",
                                    order_id, _pdf_path,
                                )
                                try:
                                    db.release_email_claim(order_id)
                                except Exception as _rel_ps:
                                    logger.error("EMAIL_CLAIM_RELEASE_FAILED order=%s err=%s", order_id, _rel_ps)
                except asyncio.TimeoutError:
                    logger.error("EMAIL_FAILED order=%s error=timeout_after_20s", order_id)
                except Exception as _email_err:
                    logger.error("EMAIL_FAILED order=%s error=%s", order_id, repr(_email_err))

            # =================================================================
            # ONE RECEIPT MESSAGE — the only Telegram notification after payment.
            # Exactly 3 lines: payment confirmed · PDF generated · email status.
            # =================================================================
            _RECEIPT_CONFIRMED = {
                "uk": "✅ Оплата підтверджена",
                "ua": "✅ Оплата підтверджена",
                "en": "✅ Payment confirmed",
                "de": "✅ Zahlung bestätigt",
                "pl": "✅ Płatność potwierdzona",
                "tr": "✅ Ödeme onaylandı",
                "ar": "✅ تم تأكيد الدفع",
            }
            _RECEIPT_PDF_READY = {
                "uk": "📄 PDF-документ згенерований",
                "ua": "📄 PDF-документ згенерований",
                "en": "📄 PDF document generated",
                "de": "📄 PDF-Dokument erstellt",
                "pl": "📄 Dokument PDF wygenerowany",
                "tr": "📄 PDF belgesi oluşturuldu",
                "ar": "📄 تم إنشاء مستند PDF",
            }
            _RECEIPT_EMAIL_OK = {
                "uk": "📧 Документ надіслано на e-mail",
                "ua": "📧 Документ надіслано на e-mail",
                "en": "📧 Document sent to email",
                "de": "📧 Dokument per E-Mail gesendet",
                "pl": "📧 Dokument wysłany na e-mail",
                "tr": "📧 Belge e-posta ile gönderildi",
                "ar": "📧 تم إرسال المستند إلى البريد الإلكتروني",
            }
            _RECEIPT_EMAIL_FAIL = {
                "uk": "⚠️ E-mail не вдалося надіслати",
                "ua": "⚠️ E-mail не вдалося надіслати",
                "en": "⚠️ Failed to send email",
                "de": "⚠️ E-Mail konnte nicht gesendet werden",
                "pl": "⚠️ Nie udało się wysłać e-mail",
                "tr": "⚠️ E-posta gönderilemedi",
                "ar": "⚠️ فشل إرسال البريد الإلكتروني",
            }
            _RECEIPT_EMAIL_KILL_SWITCH = {
                "uk": "📧 Надсилання на e-mail вимкнено — PDF у цьому повідомленні",
                "ua": "📧 Надсилання на e-mail вимкнено — PDF у цьому повідомленні",
                "en": "📧 Email delivery is off — your PDF is attached above",
                "de": "📧 E-Mail-Versand ist aus — Ihr PDF finden Sie oben",
                "pl": "📧 Wysyłka e-mail wyłączona — PDF jest w załączniku",
                "tr": "📧 E-posta kapalı — PDF bu mesajda",
                "ar": "📧 إرسال البريد معطّل — ملف PDF مرفق أعلاه",
            }

            from handlers.post_payment_ux import (
                get_doc_ready_title_html,
                get_post_delivery_support_html,
                get_termin_ask_line_html,
            )
            from handlers.stripe_handler import is_termin_supported as _ppm_termin_ok

            def _build_receipt(lang: str) -> str:
                _l = lang if lang in _RECEIPT_CONFIRMED else "uk"
                lines = [
                    get_doc_ready_title_html(_l),
                    _RECEIPT_CONFIRMED.get(_l, _RECEIPT_CONFIRMED["uk"]),
                ]
                if _email_kill_switch and _email_final:
                    lines.append(
                        _RECEIPT_EMAIL_KILL_SWITCH.get(_l, _RECEIPT_EMAIL_KILL_SWITCH["uk"])
                    )
                elif _email_final and _email_ok:
                    lines.append(_RECEIPT_EMAIL_OK.get(_l, _RECEIPT_EMAIL_OK["uk"]))
                elif _email_final and not _email_ok:
                    lines.append(_RECEIPT_EMAIL_FAIL.get(_l, _RECEIPT_EMAIL_FAIL["uk"]))
                return "\n".join(lines)

            # Build post-payment keyboard via the canonical builder (Official Form,
            # Instructions, Termin CTA, What Next) — fully localised for all 6 languages.
            _wh_city_kb = ""
            _receipt_kb = None
            try:
                from handlers.stripe_handler import build_post_payment_menu as _build_ppm
                import json as _json_kb
                _wh_order_kb = db.get_order(order_id)
                _wh_ud_raw_kb = (_wh_order_kb or {}).get("user_data") or ""
                _wh_ud_kb = (
                    _json_kb.loads(_wh_ud_raw_kb)
                    if isinstance(_wh_ud_raw_kb, str) and _wh_ud_raw_kb
                    else (_wh_ud_raw_kb if isinstance(_wh_ud_raw_kb, dict) else {})
                )
                _wh_city_kb = (
                    _wh_ud_kb.get("city") or _wh_ud_kb.get("ort") or _wh_ud_kb.get("stadt") or ""
                )
                _receipt_kb = _build_ppm(_doc_type_for_msg, _wh_city_kb, _wh_lang)
            except Exception as _kb_err:
                logger.warning("WEBHOOK_POST_KB_FAILED order=%s err=%s", order_id, _kb_err)

            _receipt_caption = _build_receipt(_wh_lang)
            if _ppm_termin_ok(_doc_type_for_msg, _wh_city_kb):
                _receipt_caption += "\n\n" + get_termin_ask_line_html(_wh_lang)
            _receipt_caption += "\n\n" + get_post_delivery_support_html(_wh_lang)

            # === SINGLE TELEGRAM MESSAGE: PDF file + receipt caption ===
            # This is the ONLY message the user receives for this payment.
            try:
                await _wh_bot.send_chat_action(chat_id=int(user_id), action="upload_document")
            except Exception:
                pass
            _pdf_for_send = _delivered_pdf_path
            _receipt_reached_user = False
            if _pdf_for_send and os.path.exists(_pdf_for_send):
                try:
                    with open(_pdf_for_send, "rb") as _pf:
                        await _wh_bot.send_document(
                            chat_id=int(user_id),
                            document=_pf,
                            caption=_receipt_caption,
                            parse_mode="HTML",
                            reply_markup=_receipt_kb,
                        )
                    log_funnel(
                        "PDF_DELIVERED",
                        int(user_id),
                        doc_type=_doc_type_for_msg,
                        lang=_wh_lang,
                        city=funnel_city_from_order(_refreshed_order),
                        order_id=order_id,
                    )
                    _ltv_city = (_wh_city_kb or "").strip() or None
                    asyncio.create_task(
                        delayed_ltv_post_pdf_followup(
                            _wh_bot,
                            int(user_id),
                            _doc_type_for_msg,
                            _ltv_city,
                            _wh_lang,
                        )
                    )
                    if db.try_claim_retention_schedule(int(order_id)):
                        asyncio.create_task(
                            schedule_retention_messages(
                                _wh_bot,
                                int(user_id),
                                _doc_type_for_msg,
                                _wh_lang,
                                _ltv_city,
                                anchor_order_id=int(order_id),
                            )
                        )
                    else:
                        logger.debug(
                            "RETENTION_SCHEDULE_SKIP order=%s (already scheduled)",
                            order_id,
                        )
                    logger.info("SINGLE_MESSAGE_SENT: order=%s user=%s email_ok=%s", order_id, user_id, _email_ok)
                    _receipt_reached_user = True
                    # Offer email capture when Apple Pay (or any path) has no email
                    if not _email_final:
                        try:
                            from handlers.stripe_handler import send_email_capture_offer as _email_cap_offer
                            asyncio.create_task(
                                _email_cap_offer(_wh_bot, int(user_id), order_id, _wh_lang)
                            )
                        except Exception as _ece:
                            logger.warning("EMAIL_CAPTURE_SCHEDULE_FAIL order=%s err=%s", order_id, _ece)
                except Exception as _send_err:
                    _send_err_s = str(_send_err).lower()
                    _is_tg_blocked = any(
                        k in _send_err_s
                        for k in ("blocked", "chat not found", "deactivated", "user is deactivated")
                    )
                    logger.error(
                        "SINGLE_MESSAGE_FAILED: order=%s blocked=%s err=%s",
                        order_id, _is_tg_blocked, _send_err,
                    )
                    if not _is_tg_blocked:
                        # Transient error (network, Telegram 500, etc.) — order is already
                        # SENT in DB but PDF never reached user. Reset to FAILED so the
                        # retry system can re-deliver.
                        try:
                            db.update_order_status(order_id, OrderStatus.FAILED)
                            logger.warning(
                                "ORDER_RESET_TO_FAILED: order=%s — transient send error, retry scheduled",
                                order_id,
                            )
                        except Exception as _rst_err:
                            logger.error("ORDER_RESET_FAILED: order=%s err=%s", order_id, _rst_err)
                        try:
                            from utils.delivery_retry import schedule_retry as _schedule_retry_send
                            await _schedule_retry_send(_wh_bot, order_id)
                        except Exception as _retry_send_err:
                            logger.error(
                                "DELIVERY_RETRY_SCHEDULE_FAIL order=%s err=%s",
                                order_id, _retry_send_err,
                            )
                    # Always try text fallback so user gets at least a payment confirmation
                    try:
                        await _wh_bot.send_message(
                            chat_id=int(user_id),
                            text=_receipt_caption,
                            parse_mode="HTML",
                        )
                        _receipt_reached_user = True
                    except Exception:
                        pass
            else:
                # PDF path unavailable (ummeldung multiple-file case or path lost) —
                # fall back to text-only receipt so user is always notified.
                logger.warning("PDF_PATH_UNAVAILABLE: order=%s — sending text receipt", order_id)
                try:
                    await _wh_bot.send_message(
                        chat_id=int(user_id),
                        text=_receipt_caption,
                        parse_mode="HTML",
                        reply_markup=_receipt_kb,
                    )
                    logger.info("TEXT_RECEIPT_SENT: order=%s user=%s", order_id, user_id)
                    _receipt_reached_user = True
                except Exception as _fallback_err:
                    logger.warning("TEXT_RECEIPT_FAILED: order=%s err=%s", order_id, _fallback_err)

            if _receipt_reached_user:
                try:
                    from handlers.post_payment_ux import schedule_pdf_fallback_nudge

                    asyncio.create_task(
                        schedule_pdf_fallback_nudge(
                            _wh_bot, int(user_id), order_id, _wh_lang
                        )
                    )
                except Exception as _nudge_sched_err:
                    logger.debug(
                        "PDF_FALLBACK_SCHEDULE_FAIL order=%s err=%s",
                        order_id,
                        _nudge_sched_err,
                    )

            # === PDF CLEANUP — delayed so redownload_pdf still finds the file for a few seconds ===
            if _email_ok and _delivered_pdf_path:
                _cleanup_path = _delivered_pdf_path

                async def _delayed_pdf_cleanup():
                    await asyncio.sleep(4.5)
                    try:
                        from backend.utils.pdf_cleanup import delete_pdf_after_delivery

                        delete_pdf_after_delivery(_cleanup_path)
                    except Exception as _cleanup_err:
                        logger.debug(
                            "WEBHOOK_PDF_CLEANUP_FAILED: order=%s err=%s",
                            order_id,
                            _cleanup_err,
                        )

                asyncio.create_task(_delayed_pdf_cleanup())
            elif _delivered_pdf_path and not _email_ok:
                logger.info("PDF_KEPT: email failed — file preserved for retry order=%s path=%s", order_id, _delivered_pdf_path)
        else:
            logger.warning(
                "WEBHOOK_DELIVERY_RETURNED_FALSE | order=%s — scheduling retry", order_id
            )
            try:
                from utils.delivery_retry import schedule_retry as _schedule_retry
                await _schedule_retry(_wh_bot, order_id)
            except Exception as _retry_sched_err:
                logger.error("DELIVERY_RETRY_SCHEDULE_FAIL | order=%s err=%s", order_id, _retry_sched_err)

    except Exception as _del_err:
        logger.error("WEBHOOK_DELIVERY_ERROR | order=%s user=%s err=%s", order_id, user_id, _del_err)
        # Delivery failure must not crash the webhook — Stripe expects 200 always.
        # Schedule retry so the user eventually receives their PDF.
        try:
            from utils.delivery_retry import schedule_retry as _schedule_retry
            await _schedule_retry(_wh_bot, order_id)
        except Exception as _retry_sched_err2:
            logger.error("DELIVERY_RETRY_SCHEDULE_FAIL | order=%s err=%s", order_id, _retry_sched_err2)

    return web.Response(status=200, text="ok")


# === STARTUP / SHUTDOWN ===
async def _resume_termin_monitoring(bot_instance) -> None:
    """Silently restart Termin polling for all users who had monitoring active
    before the bot was stopped. Called once from on_startup()."""
    try:
        from backend.termin_db import (
            get_entitled_users_for_watchdog,
            is_termin_entitled,
            update_user,
        )
        from utils.termin_checker import start_polling
        from handlers.termin import (
            make_termin_send_fn,
            make_termin_on_reserved_fn,
            make_termin_found_fn,
        )
    except Exception as exc:
        logger.error("TERMIN_RESUME_IMPORT_FAIL err=%s", exc)
        return

    try:
        # Use entitlement table as source of truth (not reminder_active flag).
        # The new polling system never sets reminder_active=1, so the old query
        # returned 0 candidates on every restart. get_entitled_users_for_watchdog()
        # queries termin_entitlements directly and correctly finds all active users.
        candidates = get_entitled_users_for_watchdog()
    except Exception as exc:
        logger.error("TERMIN_RESUME_QUERY_FAIL err=%s", exc)
        return

    resumed = skipped = 0

    for user in candidates:
        uid = str(user.get("telegram_id", "")).strip()
        city = (user.get("city") or "").strip()
        authority = (user.get("authority") or "").strip()
        lang = (user.get("language") or "en").strip()

        # Skip incomplete rows
        if not uid or not city or not authority:
            if uid:
                update_user(uid, reminder_active=0)
            skipped += 1
            continue

        # ── DEV GUARD — skip monitoring resume for test users ────────────────
        # These users must always enter as new customers; auto-resuming their
        # session would bypass the payment gate in handle_termin_from_pdf.
        _DEV_TEST_USERS = set()
        if int(uid) in _DEV_TEST_USERS:
            logger.info("DEV_MONITOR_SKIP user=%s — monitoring resume suppressed for test user", uid)
            skipped += 1
            continue
        # ────────────────────────────────────────────────────────────────────

        # ── STRICT PAYMENT GATE ──────────────────────────────────────────────
        # Stripe entitlement is the ONLY source of truth.
        # A user may have reminder_active=1 in the DB from a previous session
        # without a currently valid entitlement (e.g. payment never completed,
        # entitlement was consumed but reminder_active was not cleaned up, or
        # bot was restarted between payment and entitlement activation).
        # We re-check the live entitlement table here — not has_paid_termin.
        if not is_termin_entitled(uid):
            # Clean up both flags so the UI shows the pre-payment state.
            update_user(uid, reminder_active=0, has_paid_termin=0)
            logger.warning(
                "TERMIN_RESUME_BLOCKED_NO_ENTITLEMENT | user=%s city=%s — "
                "reminder_active was 1 but no valid entitlement found; "
                "polling NOT started, flags reset",
                uid, city,
            )
            skipped += 1
            continue
        # ────────────────────────────────────────────────────────────────────

        # Use the same callback factories as the normal flow.
        # state=None is safe — make_termin_on_reserved_fn guards it internally
        # (skips the optional cross-sell button, everything else is identical).
        uid_int = int(uid)

        # Belt-and-suspenders: re-read entitlement immediately before start_polling
        # to guard against a race where entitlement was consumed between the check
        # above and the actual poll start (e.g. concurrent webhook delivery).
        if not is_termin_entitled(uid):
            update_user(uid, reminder_active=0, has_paid_termin=0)
            logger.warning(
                "TERMIN_RESUME_BLOCKED_NO_ENTITLEMENT | user=%s city=%s — "
                "entitlement expired between gate check and poll start",
                uid, city,
            )
            skipped += 1
            continue

        # Stagger session startup to prevent an HTTP burst against city portals
        # when many users resume simultaneously after a bot restart.
        # Each session is delayed by a random 0.1–1.5 s, spreading the first
        # poll-loop iterations across ~1.5 s × N users instead of firing all
        # at once before the shared result cache has a chance to warm up.
        import random as _random
        await asyncio.sleep(_random.uniform(0.1, 1.5))

        logger.info(
            "TERMIN_STARTUP_RECOVERY_SCHEDULED | user=%s city=%s authority=%s",
            uid, city, authority,
        )
        started = start_polling(
            user_id=uid_int,
            chat_id=uid_int,
            city=city,
            authority=authority,
            lang=lang,
            send_fn=make_termin_send_fn(bot_instance, uid_int, city, lang),
            on_reserved_fn=make_termin_on_reserved_fn(
                bot_instance, uid_int, city, authority, lang, state=None
            ),
            on_found_fn=make_termin_found_fn(bot_instance, authority=authority),
        )

        if started:
            resumed += 1
            logger.info(
                "TERMIN_RESUMED | user=%s city=%s authority=%s (entitlement verified)",
                uid, city, authority,
            )
            # User already knows monitoring is running (bot restart) — unblock notifications.
            try:
                from utils.termin_checker import set_success_screen_shown as _sss_r
                _sss_r(uid_int, True)
            except Exception:
                pass
            try:
                _RESUME_MSG = {
                    "en": (
                        "🔄 <b>Monitoring resumed</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Checking continues automatically."
                    ),
                    "de": (
                        "🔄 <b>Überwachung fortgesetzt</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Prüfung läuft automatisch weiter."
                    ),
                    "uk": (
                        "🔄 <b>Моніторинг відновлено після технічного перезапуску.</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Ми продовжуємо пошук."
                    ),
                    "ua": (
                        "🔄 <b>Моніторинг відновлено після технічного перезапуску.</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Ми продовжуємо пошук."
                    ),
                    "pl": (
                        "🔄 <b>Monitoring wznowiony</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Sprawdzanie trwa automatycznie."
                    ),
                    "tr": (
                        "🔄 <b>İzleme devam ediyor</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Kontroller otomatik olarak devam ediyor."
                    ),
                    "ar": (
                        "🔄 <b>استُؤنف المراقبة</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "تستمر الفحوصات تلقائيًا."
                    ),
                }
                _r_lang = lang if lang in _RESUME_MSG else "en"
                _resume_text = _RESUME_MSG[_r_lang].format(
                    city=city.replace("_", " ").title(),
                    authority=authority.replace("_", " ").title(),
                )
                await bot_instance.send_message(
                    uid_int,
                    _resume_text,
                    parse_mode="HTML",
                )
            except Exception as _msg_exc:
                logger.warning(
                    "TERMIN_RESUME_NOTIFY_FAIL user=%s err=%s", uid, _msg_exc
                )
        else:
            skipped += 1
            logger.info(
                "TERMIN_RESUME_BLOCKED | user=%s city=%s authority=%s "
                "(start_polling blocked — cooldown or duplicate session)",
                uid, city, authority,
            )

    logger.info(
        "TERMIN_RESUME_DONE | resumed=%d blocked=%d total=%d",
        resumed, skipped, len(candidates),
    )


async def on_startup(_):
    logger.info("=" * 60)
    logger.info("🟢 Bot started")
    logger.info("=" * 60)

    # === FONT INTEGRITY CHECK (P0 — missing fonts cause silent PDF defects) ===
    try:
        from backend.utils.font_check import check_required_fonts
        check_required_fonts()
    except RuntimeError as _fe:
        logger.critical("🔴 FONT_CHECK_FAILED: %s", _fe)
        raise  # hard stop — bot must not run without fonts
    except Exception as _fe:
        logger.warning("⚠️ Font check encountered unexpected error (non-critical): %s", _fe)

    # === PRODUCTION ENVIRONMENT VALIDATION ===
    _is_prod = os.getenv("ENV", os.getenv("APP_ENV", "")).lower() == "production"
    if _is_prod:
        _prod_errors = []
        if not os.getenv("STRIPE_SECRET_KEY") and not os.getenv("STRIPE_API_KEY"):
            _prod_errors.append("STRIPE_SECRET_KEY (or STRIPE_API_KEY) not set")
        if not os.getenv("STRIPE_WEBHOOK_SECRET"):
            _prod_errors.append("STRIPE_WEBHOOK_SECRET not set")
        if not os.getenv("WEBAPP_URL") or "localhost" in os.getenv("WEBAPP_URL", ""):
            _prod_errors.append("WEBAPP_URL not set or points to localhost")
        if _prod_errors:
            for _err in _prod_errors:
                logger.critical("🔴 PRODUCTION_CONFIG_MISSING: %s", _err)
            raise RuntimeError(
                "Production startup blocked — missing required env vars: "
                + "; ".join(_prod_errors)
            )
        logger.info("✅ Production env validation passed")

    # === ADMIN IDS CHECK ===
    _admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    if not _admin_ids_raw:
        logger.warning(
            "⚠️  ADMIN_IDS not set — payment alerts and /admin panel will be "
            "silently skipped. Set ADMIN_IDS=<your_telegram_id> in .env."
        )
    else:
        _admin_count = len([x for x in _admin_ids_raw.split(",") if x.strip().isdigit()])
        logger.info("✅ ADMIN_IDS: %d admin(s) configured", _admin_count)

    # === EMAIL SMTP PROBE — dev-only, disabled in production ===
    # To re-enable: set EMAIL_SMTP_PROBE=1 in .env
    # if os.getenv("EMAIL_SMTP_PROBE") == "1":
    #     try:
    #         from utils.email_sender import send_test_email as _smtp_probe
    #         _test_to = os.getenv("EMAIL_SMTP_USER", "")
    #         if _test_to:
    #             import threading as _thr
    #             _thr.Thread(target=_smtp_probe, args=(_test_to,), daemon=True, name="smtp-probe").start()
    #     except Exception as _probe_err:
    #         logger.warning("⚠️ SMTP probe failed to launch (non-critical): %s", _probe_err)

    # === CLEANUP OLD GENERATED PDFs (GDPR — remove stale PII files) ===
    try:
        from backend.utils.pdf_cleanup import cleanup_old_pdfs
        from utils.helpers import get_db as _get_db_cleanup
        # Collect file_paths for orders where email has not been sent yet so
        # cleanup does not delete PDFs that are still needed for email delivery
        # (e.g. Apple Pay users who haven't entered their email address yet).
        _email_pending_paths: set = set()
        try:
            _db_cleanup = _get_db_cleanup()
            _ep_cursor = _db_cleanup.conn.cursor()
            _ep_cursor.execute(
                "SELECT file_path FROM orders"
                " WHERE (email_sent IS NULL OR email_sent = 0)"
                "   AND file_path IS NOT NULL"
            )
            for _ep_row in _ep_cursor.fetchall():
                if _ep_row["file_path"]:
                    _email_pending_paths.add(_ep_row["file_path"])
        except Exception as _ep_err:
            logger.warning("⚠️ Could not load email-pending paths for cleanup guard: %s", _ep_err)
        cleanup_old_pdfs(max_age_hours=2, skip_paths=_email_pending_paths)
    except Exception as _e:
        logger.warning("⚠️ PDF cleanup on startup failed (non-critical): %s", _e)

    # === STALE ORDERS RECOVERY ===
    # Orders stuck in PROCESSING > 30 min after a crash are marked FAILED
    # so Stripe webhook re-delivery can trigger a fresh delivery attempt.
    try:
        from utils.helpers import get_db as _get_db_startup
        from backend.database import OrderStatus as _OS
        _db_startup = _get_db_startup()
        _cutoff_min = 30
        _cursor = _db_startup.conn.cursor()
        _cursor.execute(
            """
            SELECT id, user_id, doc_type FROM orders
            WHERE status = 'processing'
              AND created_at < datetime('now', ?)
            """,
            (f"-{_cutoff_min} minutes",),
        )
        _stale = _cursor.fetchall()
        if _stale:
            for _row in _stale:
                _db_startup.update_order_status(_row["id"], _OS.FAILED)
                logger.warning(
                    "STALE_ORDER_RECOVERED: order_id=%s user_id=%s doc=%s → FAILED",
                    _row["id"], _row["user_id"], _row["doc_type"],
                )
            logger.info("STALE_ORDERS_CLEANUP: %d order(s) recovered", len(_stale))
        else:
            logger.info("✅ No stale PROCESSING orders found")
    except Exception as _stale_err:
        logger.warning("⚠️ Stale orders cleanup failed (non-critical): %s", _stale_err)

    # === FAILED ORDER RETRY ON RESTART ===
    # Orders stuck at FAILED after a crash are never re-attempted by Stripe (we
    # already returned 200) — auto-retry the last 24 h of FAILED orders so users
    # always receive their PDFs even after a bot crash mid-delivery.
    # Termin / non-PDF orders are explicitly excluded — they have their own
    # activation paths and must never enter the PDF retry pipeline.
    try:
        from utils.delivery_retry import schedule_retry as _startup_retry, _NON_PDF_DOC_TYPES as _skip_types_fail
        _db_startup2 = _get_db_startup()
        _fr_cursor = _db_startup2.conn.cursor()
        _skip_placeholders_fail = ",".join("?" * len(_skip_types_fail))
        _fr_cursor.execute(
            f"SELECT id, doc_type FROM orders WHERE status = 'failed'"
            f" AND created_at > datetime('now', '-24 hours')"
            f" AND (doc_type IS NULL OR doc_type NOT IN ({_skip_placeholders_fail}))",
            tuple(_skip_types_fail),
        )
        _failed_rows = _fr_cursor.fetchall()
        if _failed_rows:
            for _fr in _failed_rows:
                logger.info("STARTUP_RETRY_SCHEDULED | order=%s doc_type=%s", _fr["id"], _fr["doc_type"])
                asyncio.create_task(_startup_retry(bot, _fr["id"]))
            logger.info("STARTUP_RETRY: scheduled %d failed order(s)", len(_failed_rows))
        else:
            logger.info("✅ No FAILED orders need startup retry")
    except Exception as _startup_retry_err:
        logger.warning("⚠️ STARTUP_RETRY_FAILED (non-critical): %s", _startup_retry_err)

    # === PAID ORDERS STUCK BEFORE DELIVERY ===
    # Covers: bot crashed after claim_paid() but before deliver_document_after_payment().
    # Webhook retries skip PAID status (idempotency guard), so without this sweep the
    # order stays in PAID permanently when the user returns without the paid_ deeplink.
    # Termin / non-PDF orders are excluded — they are activated by their own webhook
    # branches (flow=termin / termin_only) and do not need PDF delivery.
    try:
        from utils.delivery_retry import schedule_retry as _startup_paid_retry, _NON_PDF_DOC_TYPES as _skip_types_paid
        _db_paid = _get_db_startup()
        _paid_cursor = _db_paid.conn.cursor()
        _skip_placeholders_paid = ",".join("?" * len(_skip_types_paid))
        _paid_cursor.execute(
            f"SELECT id, doc_type FROM orders WHERE status = 'paid'"
            f" AND created_at > datetime('now', '-24 hours')"
            f" AND (doc_type IS NULL OR doc_type NOT IN ({_skip_placeholders_paid}))",
            tuple(_skip_types_paid),
        )
        _paid_rows = _paid_cursor.fetchall()
        if _paid_rows:
            for _pr in _paid_rows:
                logger.info("STARTUP_PAID_RETRY_SCHEDULED | order=%s doc_type=%s", _pr["id"], _pr["doc_type"])
                asyncio.create_task(_startup_paid_retry(bot, _pr["id"]))
            logger.info("STARTUP_PAID_RETRY: scheduled %d paid order(s) for delivery", len(_paid_rows))
        else:
            logger.info("✅ No PAID orders stuck before delivery")
    except Exception as _paid_retry_err:
        logger.warning("⚠️ STARTUP_PAID_RETRY_FAILED (non-critical): %s", _paid_retry_err)

    # === EMAIL RETRY ON RESTART ===
    # Two cases handled:
    #   A) email_sending=1, email_sent=0 — process was killed between claim and send.
    #      Reset email_sending=0 so claim_email_send can win again, then retry.
    #   B) email_sending=0, email_sent=0, customer_email set — send failed normally
    #      (provider error / timeout), claim was released; retry on restart.
    try:
        _db_email_retry = _get_db_startup()
        _er_cursor = _db_email_retry.conn.cursor()

        # Case A: reset stuck email_sending=1 (crashed mid-send)
        _er_cursor.execute(
            "UPDATE orders SET email_sending = 0"
            " WHERE (email_sending = 1)"
            "   AND (email_sent IS NULL OR email_sent = 0)"
            "   AND created_at > datetime('now', '-24 hours')",
        )
        _db_email_retry.conn.commit()
        _stuck_reset_count = _er_cursor.rowcount
        if _stuck_reset_count:
            logger.warning(
                "STARTUP_EMAIL_SENDING_RESET: %d order(s) had email_sending=1 — reset for retry",
                _stuck_reset_count,
            )

        # Case A + B: retry all orders with email not confirmed and email known
        _er_cursor.execute(
            "SELECT id, customer_email FROM orders"
            " WHERE status = 'sent'"
            "   AND (email_sent IS NULL OR email_sent = 0)"
            "   AND (email_sending IS NULL OR email_sending = 0)"
            "   AND customer_email IS NOT NULL"
            "   AND created_at > datetime('now', '-24 hours')",
        )
        _email_retry_rows = _er_cursor.fetchall()
        if _email_retry_rows:
            from utils.delivery_retry import _attempt_email_after_delivery as _startup_email_retry

            async def _staggered_email_retry(order_id, delay):
                await asyncio.sleep(delay)
                await _startup_email_retry(order_id)

            _valid_retry_count = 0
            for _er in _email_retry_rows:
                _er_email = (_er["customer_email"] if "customer_email" in _er.keys() else None) or ""
                if not _er_email or "@" not in _er_email:
                    logger.warning(
                        "STARTUP_EMAIL_RETRY_SKIP | order=%s — invalid email %r",
                        _er["id"], _er_email,
                    )
                    continue
                logger.info("STARTUP_EMAIL_RETRY_SCHEDULED | order=%s delay=%ds",
                            _er["id"], _valid_retry_count * 2)
                asyncio.create_task(_staggered_email_retry(_er["id"], _valid_retry_count * 2))
                _valid_retry_count += 1
            logger.info(
                "STARTUP_EMAIL_RETRY: scheduled %d order(s) for email re-send (staggered 2s apart)",
                _valid_retry_count,
            )
        else:
            logger.info("✅ No SENT orders with missing email found")
    except Exception as _er_err:
        logger.warning("⚠️ STARTUP_EMAIL_RETRY failed (non-critical): %s", _er_err)

    # === CACHE BOT USERNAME for Stripe deep-links ===
    try:
        from handlers.termin import set_bot_username as _set_bot_username
        _me = await bot.get_me()
        if _me and _me.username:
            _set_bot_username(_me.username)
            logger.info("✅ BOT_USERNAME resolved via get_me(): @%s", _me.username)
        else:
            logger.warning("⚠️ bot.get_me() returned no username — falling back to env/config")
    except Exception as _e:
        logger.warning("⚠️ BOT_USERNAME cache failed (%s) — falling back to env/config", _e)

    # === SET BOT COMMANDS (shown in Telegram's "/" menu) ===
    try:
        from aiogram.types import BotCommand
        # Only /start exposed — navigation is button-driven.
        # /help handler still works if typed manually, just not shown in the menu.
        _commands = [
            BotCommand("start", "🏠 Main menu"),
        ]
        await bot.set_my_commands(_commands)
        logger.info("✅ Bot commands registered (%d commands)", len(_commands))
    except Exception as _cmd_err:
        logger.warning("⚠️ set_my_commands failed (non-critical): %s", _cmd_err)

    # === DB BACKUP on startup + periodic 6h task ===
    async def _db_backup_loop():
        from utils.db_backup import run_backup as _run_backup
        while True:
            try:
                _run_backup()
            except Exception as _bup_e:
                logger.warning("DB_BACKUP_FAILED (periodic): %s", _bup_e)
            await asyncio.sleep(6 * 3600)  # every 6 hours

    try:
        from utils.db_backup import run_backup as _run_backup_startup
        _run_backup_startup()
        logger.info("✅ DB backup on startup completed")
    except Exception as _bup_e:
        logger.warning("⚠️ DB backup on startup failed (non-critical): %s", _bup_e)

    asyncio.create_task(_db_backup_loop())

    # === INIT TERMIN DB ===
    try:
        from backend.termin_db import init_database as init_termin_db, seed_all_cities
        init_termin_db()
        seed_all_cities()
        logger.info("✅ Termin DB initialized and seeded")
    except Exception as e:
        logger.error("❌ Termin DB init failed: %s", e)

    # === EMAIL SENDER SANITY CHECK ===
    _email_from = os.getenv("EMAIL_FROM", "")
    if not _email_from or "resend.dev" in _email_from or "example.com" in _email_from:
        logger.warning(
            "⚠️  SANDBOX_EMAIL_SENDER | EMAIL_FROM=%r — "
            "emails to real users will NOT be delivered. "
            "Set EMAIL_FROM to a verified custom domain before release (e.g. noreply@termin-assist.de).",
            _email_from,
        )
    else:
        logger.info("✅ Email sender configured: %s", _email_from)

    # === RESTORE TERMIN REGISTRIES FROM DB (once, before monitoring resumes) ===
    try:
        from handlers.termin import restore_active_termin_sessions as _rats
        _rats()
        logger.info("✅ Termin in-memory registries restored from DB")
    except Exception as _rats_err:
        logger.warning("⚠️ Termin registry restore failed (non-critical): %s", _rats_err)

    # === RESUME TERMIN MONITORING ===
    # Runs as a background task so dp.start_polling() is not delayed.
    async def _resume_termin_monitoring_bg():
        try:
            await _resume_termin_monitoring(bot)
        except Exception as e:
            logger.error("❌ Termin monitoring resume failed: %s", e)
    asyncio.create_task(_resume_termin_monitoring_bg())

    # === TERMIN SESSION WATCHDOG ===
    # Periodically (every 5 min) finds users with a valid entitlement but no
    # running poll session (e.g. after an unhandled exception killed the loop)
    # and restarts their monitoring automatically.
    async def _termin_watchdog_loop(bot_instance):
        # Wait for the startup resume to finish before first check
        await asyncio.sleep(90)
        while True:
            try:
                from backend.termin_db import (
                    get_entitled_users_for_watchdog as _gwam,
                    is_termin_entitled as _ite_wd,
                )
                from utils.termin_checker import (
                    is_polling as _isp_wd,
                    get_session as _gs_wd,
                    start_polling as _stp_wd,
                    set_success_screen_shown as _sss_wd,
                )
                from handlers.termin import (
                    make_termin_send_fn as _mtsf_wd,
                    make_termin_on_reserved_fn as _mtor_wd,
                    make_termin_found_fn as _mtff_wd,
                )
                from utils.helpers import get_user_lang as _gul_wd

                # Query by entitlement (not reminder_active) so the watchdog
                # works correctly even if reminder_active was reset prematurely
                # (e.g. via handle_pause_reminders / deactivate_reminder).
                candidates = _gwam()

                # ── ACTIVE_SESSIONS heartbeat ────────────────────────────────
                from utils.termin_checker import _sessions as _all_sessions
                _active_count = sum(
                    1 for _s in _all_sessions.values()
                    if _s.task and not _s.task.done()
                )
                logger.info(
                    "TERMIN_ACTIVE_SESSIONS | count=%d entitled_in_db=%d",
                    _active_count, len(candidates),
                )
                # ────────────────────────────────────────────────────────────

                for _wu in candidates:
                    _uid_str = str(_wu.get("telegram_id", "")).strip()
                    _wcity   = (_wu.get("city") or "").strip()
                    _wauth   = (_wu.get("authority") or "").strip()

                    if not _uid_str or not _wcity or not _wauth:
                        continue

                    _uid_int = int(_uid_str)

                    # Skip users that already have an active session
                    if _isp_wd(_uid_int) or _gs_wd(_uid_int) is not None:
                        continue

                    # No active session — restart only if still entitled
                    if not _ite_wd(_uid_str):
                        continue

                    _wlang = (_gul_wd(_uid_str) or _wu.get("language") or "en").strip().lower()
                    logger.warning(
                        "TERMIN_WATCHDOG_RESTART | user=%s city=%s auth=%s — "
                        "entitled but no active session, restarting monitoring",
                        _uid_int, _wcity, _wauth,
                    )
                    try:
                        _started_wd = _stp_wd(
                            user_id=_uid_int,
                            chat_id=_uid_int,
                            city=_wcity,
                            authority=_wauth,
                            lang=_wlang,
                            send_fn=_mtsf_wd(bot_instance, _uid_int, _wcity, _wlang),
                            on_reserved_fn=_mtor_wd(
                                bot_instance, _uid_int, _wcity, _wauth, _wlang, state=None
                            ),
                            on_found_fn=_mtff_wd(bot_instance, authority=_wauth),
                        )
                        if _started_wd:
                            _sss_wd(_uid_int, True)
                            logger.warning(
                                "TERMIN_WATCHDOG_STARTED | user=%s city=%s auth=%s",
                                _uid_int, _wcity, _wauth,
                            )
                    except Exception as _ws_exc:
                        logger.error(
                            "TERMIN_WATCHDOG_START_FAILED | user=%s err=%s",
                            _uid_int, _ws_exc,
                        )
            except Exception as _wd_exc:
                logger.error("TERMIN_WATCHDOG_ERROR | err=%s", _wd_exc)

            await asyncio.sleep(300)  # check every 5 minutes

    try:
        asyncio.create_task(_termin_watchdog_loop(bot))
        logger.info("✅ Termin session watchdog started (interval=5min)")
    except Exception as _wd_start_err:
        logger.warning("Termin watchdog failed to start (non-critical): %s", _wd_start_err)

    # === PROGRESSIVE TERMIN UPSELL (72h no-slot nudge) ===
    async def _safe_upsell_loop():
        from utils.termin_upsell import upsell_loop as _upsell_loop_inner
        while True:
            try:
                await _upsell_loop_inner(bot)
            except Exception as _ue:
                logger.error("UPSELL_LOOP_CRASHED: %s — restarting in 60s", _ue)
            await asyncio.sleep(60)  # short pause before restart after crash

    try:
        asyncio.create_task(_safe_upsell_loop())
        logger.info("Progressive Termin upsell loop started (72h threshold)")
    except Exception as _upsell_err:
        logger.warning("Termin upsell loop failed to start (non-critical): %s", _upsell_err)

    # === START TERMIN MONITOR (Premium health checker) ===
    try:
        from utils.termin_monitor import start_termin_monitor
        start_termin_monitor(bot)
        logger.info("✅ Termin Monitor v1.0 scheduled")
    except Exception as e:
        logger.error("❌ Termin Monitor failed to start: %s", e)

    # === START TERMIN AUDITOR (24h deep verification) ===
    try:
        from utils.termin_auditor import start_termin_auditor
        start_termin_auditor(bot)
        logger.info("✅ Termin Auditor v1.0 scheduled")
    except Exception as e:
        logger.error("❌ Termin Auditor failed to start: %s", e)
    
    # === STRIPE SECURITY CHECKS (hard fail — must run before HTTP server starts) ===
    from utils.stripe_env import (
        enforce_stripe_webhook_secret,
        validate_stripe_api_key,
        allow_unverified_stripe_webhook,
    )
    # 1. Webhook secret — hard fail unless dev bypass is explicitly set
    try:
        enforce_stripe_webhook_secret()
        _wh_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        if _wh_secret:
            logger.info(
                "✅ STRIPE_WEBHOOK_SECRET loaded (len=%d, ends ...%s)",
                len(_wh_secret), _wh_secret[-4:] if len(_wh_secret) > 4 else "???",
            )
        else:
            logger.warning(
                "⚠️ STRIPE_WEBHOOK_SECRET missing — UNVERIFIED dev mode "
                "(STRIPE_ALLOW_UNVERIFIED_WEBHOOKS=true). Never use in production."
            )
    except RuntimeError as _wh_err:
        logger.critical("🔴 STRIPE_WEBHOOK_SECRET: %s", _wh_err)
        raise

    # 2. API key connectivity — catches wrong/revoked keys before first real payment
    try:
        await validate_stripe_api_key()
        logger.info("✅ Stripe API key validated (Account.retrieve OK)")
    except RuntimeError as _sk_err:
        logger.critical("🔴 STRIPE_API_KEY: %s", _sk_err)
        raise
    
    global _http_runner

    app = web.Application()
    from handlers.webhook import attach_to_app as _attach_to_app
    _attach_to_app(app, bot, dp)  # registers bot + dp for webhook FSM access
    # ── Landing (SEO site) ──────────────────────────────────────────────────
    app.router.add_get("/", _serve_landing)
    # Static assets for seo-site (css/, js/)
    app.router.add_static("/css", os.path.join(SEO_DIR, "css"), show_index=False)
    app.router.add_static("/js",  os.path.join(SEO_DIR, "js"),  show_index=False)
    # SEO sub-pages
    for _seo_page in (
        "about", "anmeldung", "aufenthaltstitel", "buergergeld",
        "datenschutz", "familienkasse", "faq", "impressum",
        "kindergeld", "termin-berlin", "ummeldung", "wohngeld",
    ):
        app.router.add_get(f"/{_seo_page}", _serve_seo_page)
        app.router.add_get(f"/{_seo_page}.html", _serve_seo_page)
    # robots.txt and sitemap.xml
    async def _serve_robots(req):
        p = os.path.join(SEO_DIR, "robots.txt")
        return web.Response(text=open(p).read(), content_type="text/plain") if os.path.isfile(p) else web.Response(status=404)
    async def _serve_sitemap(req):
        p = os.path.join(SEO_DIR, "sitemap.xml")
        return web.Response(text=open(p).read(), content_type="application/xml") if os.path.isfile(p) else web.Response(status=404)
    app.router.add_get("/robots.txt", _serve_robots)
    app.router.add_get("/sitemap.xml", _serve_sitemap)
    # ── WebApp form (Telegram Mini App) ────────────────────────────────────
    app.router.add_get("/form", _serve_webapp_html)
    app.router.add_get("/index.html", _serve_webapp_html)
    # ── API & infrastructure ────────────────────────────────────────────────
    app.router.add_get("/health", _http_health)
    app.router.add_get("/api/form-schema", _api_form_schema)
    app.router.add_post("/webapp-submit", _handle_webapp_submit_http)
    app.router.add_post("/stripe-webhook", _handle_stripe_webhook)
    app.router.add_get("/stripe-webhook-test", _handle_webhook_test)
    # Payment landing pages (required for Stripe to finalize payment)
    app.router.add_get("/payment-success", _handle_payment_success)
    app.router.add_get("/payment-cancel", _handle_payment_cancel)

    _http_runner = web.AppRunner(app)
    await _http_runner.setup()
    site = web.TCPSite(_http_runner, "0.0.0.0", 4243)
    await site.start()
    
    # Log all registered routes
    logger.info("=" * 60)
    logger.info("✅ HTTP server listening on port 4243")
    logger.info("=" * 60)
    logger.info("REGISTERED ROUTES:")
    for route in app.router.routes():
        logger.info("  %s %s", route.method, route.resource.canonical)
    logger.info("=" * 60)
    logger.info("✅ Stripe webhook endpoint: POST /stripe-webhook")
    logger.info("   Stripe Dashboard must send webhooks to:")
    logger.info("   https://termin-assist.de/stripe-webhook")
    logger.info("=" * 60)
    
    # Print to console for visibility
    logger.info("")
    logger.info("=" * 60)
    logger.info("HTTP SERVER READY")
    logger.info("=" * 60)
    logger.info("  Port: 4243")
    logger.info("  Stripe webhook: POST /stripe-webhook")
    logger.info("")
    logger.info("  Stripe webhook URL:")
    logger.info("  https://termin-assist.de/stripe-webhook")
    logger.info("=" * 60)
    logger.info("")


async def on_shutdown(_):
    logger.info("🔴 Bot shutting down")
    if _http_runner:
        await _http_runner.cleanup()
    # Close bot's internal aiohttp session gracefully
    try:
        session = await bot.get_session()
        await session.close()
    except Exception as _se:
        logger.warning("on_shutdown: session close error: %s", _se)
    # Close shared httpx client in termin_checker (if initialised)
    try:
        from utils.termin_checker import close_shared_httpx_client
        await close_shared_httpx_client()
    except Exception as _hxe:
        logger.warning("on_shutdown: httpx client close error: %s", _hxe)


# === MAIN ===
def main():
    # Print clear startup banner
    logger.info("")
    logger.info("=" * 70)
    logger.info("")
    logger.info("  ╔════════════════════════════════════════════════════════════════╗")
    logger.info("  ║                                                                ║")
    logger.info("  ║   GERMAN_DOC_BOT — MAIN SERVER (STRIPE WEBHOOK HANDLER)       ║")
    logger.info("  ║                                                                ║")
    logger.info("  ╚════════════════════════════════════════════════════════════════╝")
    logger.info("")
    logger.info("  ✅ This is the CORRECT server for Stripe webhooks")
    logger.info("  ✅ Listening on port 4243")
    logger.info("  ✅ Webhook endpoint: /stripe-webhook")
    logger.info("")
    logger.info("  SETUP CHECKLIST:")
    logger.info("  1. Stripe Dashboard → Webhooks → https://termin-assist.de/stripe-webhook")
    logger.info("  2. Copy signing secret to .env as STRIPE_WEBHOOK_SECRET")
    logger.info("")
    logger.info("  ⚠️  DO NOT run stripe_webhook.py (deprecated)")
    logger.info("  ⚠️  DO NOT run webapp_server.py for Stripe (wrong server)")
    logger.info("")
    logger.info("=" * 70)
    logger.info("")
    
    logger.info("🚀 Starting GERMAN_DOC_BOT")
    set_bot(bot)


    # WEB_APP_DATA handler: receives form data via Telegram WebApp API (sendData)
    dp.register_message_handler(
        handle_webapp_data,
        content_types=types.ContentType.WEB_APP_DATA,
        state="*",
    )

    register_start_handlers(dp)
    register_docs_handlers(dp)
    register_termin_handlers(dp)
    register_stripe_handlers(dp)
    register_admin_handlers(dp)
    register_support_handlers(dp)
    register_health_handlers(dp)
    register_admin_termin_handlers(dp)

    # === RATING HANDLER ===
    # Catch-all: must be the very last registration.
    # Returns True so LoggingMiddleware logs "Handled" instead of "Unhandled".
    async def _catch_all_callback(callback: types.CallbackQuery):
        logger.warning("UNHANDLED_CALLBACK | data=%s user=%s", callback.data, callback.from_user.id)
        await callback.answer()
        return True

    dp.register_callback_query_handler(_catch_all_callback, lambda c: True, state="*")

    logger.warning("ACTIVE_DISPATCHER_ID=%s", id(dp))

    async def cmd_testtermin(message: types.Message):
        from utils.termin_checker import check_termin_availability
        tests = [
            ("berlin", "anmeldung"),
            ("frankfurt", "anmeldung"),
            ("duesseldorf", "anmeldung"),
            ("koeln", "anmeldung"),
        ]
        lines = []
        for city, service in tests:
            try:
                status, data = await check_termin_availability(city, service)
                lines.append(f"{city}: {status.name}")
            except Exception:
                lines.append(f"{city}: ERROR")
        await message.answer("Termin test:\n\n" + "\n".join(lines))

    dp.register_message_handler(cmd_testtermin, commands=["testtermin"])

    import time as _time
    while True:
        try:
            executor.start_polling(
                dp,
                skip_updates=True,
                on_startup=on_startup,
                on_shutdown=on_shutdown,
            )
            break  # clean exit (KeyboardInterrupt handled inside executor)
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as _poll_err:
            logger.error("POLLING_CRASHED: %s — restarting in 3s", _poll_err, exc_info=True)
            _time.sleep(3)


if __name__ == "__main__":
    main()

