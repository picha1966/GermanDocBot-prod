
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
import asyncio
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
dp = Dispatcher(bot, storage=MemoryStorage())
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
from handlers.stripe_handler import register_stripe_handlers, set_bot
from handlers.admin import register_admin_handlers
from handlers.termin import register_termin_handlers
from handlers.termin_activation import send_termin_activation_message as _send_termin_activation_message
from handlers.support_ai import register_support_handlers
from handlers.health import register_health_handlers

# === WEBAPP HTTP SERVER ===
_http_runner = None
WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")


async def _serve_webapp_html(request):
    path = os.path.join(WEBAPP_DIR, "index.html")
    if not os.path.isfile(path):
        return web.Response(text="Not Found", status=404)
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

        # ── SERVER-SIDE VALIDATION before preview/menu ──
        # Block submission if form data has hard errors (date format, required fields, etc.)
        if (doc_type or "").strip().lower() == "anmeldung":
            try:
                from backend.form_validation import validate_anmeldung_form, get_validation_errors_localized
                _marriage_val = str((answers or {}).get("eheschliessung_ort_datum", "")).strip()
                logger.info("WEBAPP_SUBMIT_DEBUG VALUE: eheschliessung_ort_datum=%r", _marriage_val)
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


async def _handle_stripe_webhook(request):
    """
    Stripe webhook handler for checkout.session.completed.
    Single flow: receive → verify → mark PAID → deliver PDF.
    """
    import stripe as stripe_lib

    # FUNNEL POINT 7: Stripe webhook arrived
    logger.info("FUNNEL | step=webhook_received remote=%s", request.remote)

    raw_body = await request.read()
    sig = request.headers.get("Stripe-Signature") or ""
    
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

    logger.info("WEBHOOK_SECRET_LOADED: %s (len=%s)", bool(webhook_secret), len(webhook_secret))

    # Verify signature and parse event
    if webhook_secret:
        try:
            event = stripe_lib.Webhook.construct_event(raw_body, sig, webhook_secret)
            event_type = event.type
            event_data = event.data
            logger.info("WEBHOOK_SIGNATURE_VERIFIED: OK")
        except stripe_lib.error.SignatureVerificationError as e:
            logger.info("WEBHOOK_SIGNATURE_FAILED: %s", e)
            logger.error("WEBHOOK_SIGNATURE_FAILED: %s", e)
            return web.Response(status=400, text="Invalid signature")
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

    # Only process checkout.session.completed
    if event_type != "checkout.session.completed":
        return web.Response(status=200, text="ok")

    # Parse session
    session = event_data.get("object") if hasattr(event_data, "get") else event_data.object
    session_id = session.get("id") if isinstance(session, dict) else getattr(session, "id", None)
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

    # Get order_id from metadata or client_reference_id
    order_id_str = metadata.get("order_id")
    if not order_id_str:
        order_id_str = session.get("client_reference_id") if isinstance(session, dict) else getattr(session, "client_reference_id", None)

    # Extract customer email for PDF email delivery (after order_id_str is known for logging)
    _customer_email = None
    try:
        _customer_details = (
            session.get("customer_details") if isinstance(session, dict)
            else getattr(session, "customer_details", None)
        )
        if _customer_details:
            _customer_email = (
                _customer_details.get("email") if isinstance(_customer_details, dict)
                else getattr(_customer_details, "email", None)
            )
        # Fallback: top-level customer_email field (older Stripe versions)
        if not _customer_email:
            _customer_email = (
                session.get("customer_email") if isinstance(session, dict)
                else getattr(session, "customer_email", None)
            )
        if _customer_email:
            logger.info("WEBHOOK_CUSTOMER_EMAIL: order_id=%s email=%s", order_id_str, _customer_email)
    except Exception as _email_parse_err:
        logger.debug("WEBHOOK_EMAIL_PARSE_ERROR: %s", _email_parse_err)

    # Validate order_id exists
    if not order_id_str or not str(order_id_str).strip().isdigit():
        logger.info("WEBHOOK_ERROR: NO_ORDER_ID metadata=%s", metadata)
        return web.Response(status=200, text="ok")

    order_id = int(order_id_str)

    # Persist customer email to DB immediately so it survives across webhook retries
    if _customer_email:
        try:
            db.save_customer_email(order_id, _customer_email)
        except Exception:
            pass
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
    
    # Idempotency: if already sent/downloaded, skip
    if old_status in (OrderStatus.SENT.value, OrderStatus.DOWNLOADED.value):
        logger.debug("WEBHOOK_SKIP: already delivered order_id=%s status=%s", order_id, old_status)
        return web.Response(status=200, text="ok")

    # Mark as PAID
    db.update_order_status(order_id, OrderStatus.PAID, stripe_session_id=session_id)
    
    # Verify update
    order = db.get_order(order_id)
    new_status = (order.get("status") or "").strip().lower()
    
    logger.info("WEBHOOK_MARKED_PAID: order_id=%s %s -> %s", order_id, old_status, new_status)
    logger.info("FUNNEL | step=order_marked_paid order_id=%s user_id=%s", order_id, order.get("user_id"))

    if new_status != OrderStatus.PAID.value:
        logger.info("WEBHOOK_ERROR: STATUS_UPDATE_FAILED order_id=%s", order_id)
        return web.Response(status=500, text="status update failed")

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
            _upsert_ent(
                str(_tid),
                plan="single",
                slots_total=1,
                stripe_session_id=session_id or f"bundle_{order_id}",
                paid_until=None,
            )
            # Activate reminder so _resume_termin_monitoring() picks this user up on restart
            _t_user_row = _get_termin_user(_tid)
            _t_city = (_t_user_row or {}).get("city") or "berlin"
            _t_auth = (_t_user_row or {}).get("authority") or "anmeldung"
            _create_termin_reminder(_tid, _t_city, _t_auth, 6)
            logger.info("BUNDLE_TERMIN_ACTIVATED: order_id=%s user_id=%s city=%s auth=%s", order_id, _tid, _t_city, _t_auth)

            # Auto-start polling immediately if city/authority are known (not defaults)
            _bundle_city_known = bool((_t_user_row or {}).get("city"))
            _bundle_auth_known = bool((_t_user_row or {}).get("authority"))
            if _bundle_city_known and _bundle_auth_known:
                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp_b, is_polling as _isp_b
                    from utils.helpers import get_user_lang as _gul_b
                    from backend.termin_db import is_termin_entitled as _ite_b
                    _b_bot = request.app["bot"]
                    _b_lang = (_gul_b(int(_tid)) or "uk").strip().lower()
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
                            on_found_fn=make_termin_found_fn(_b_bot),
                        )
                        logger.debug("BUNDLE_POLLING_STARTED: user=%s city=%s auth=%s", _tid, _t_city, _t_auth)
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
                # Set paid_until = now + 24h so countdown display works correctly.
                from datetime import datetime as _dt24, timedelta as _td24
                _paid_until_24 = (_dt24.utcnow() + _td24(hours=24)).isoformat()
                _upsert_ent(
                    str(_termin_uid),
                    plan="single",
                    slots_total=1,
                    stripe_session_id=session_id or f"termin_{order_id}",
                    paid_until=_paid_until_24,
                )
                # Start monitoring immediately: create reminder using saved city+authority
                _t_user_row = _get_termin_user(str(_termin_uid))
                _t_city = (_t_user_row or {}).get("city") or "berlin"
                _t_auth = (_t_user_row or {}).get("authority") or "anmeldung"
                _create_termin_reminder(str(_termin_uid), _t_city, _t_auth, 6)
                logger.info("TERMIN_ONLY_PAID_ACTIVATED: order_id=%s user_id=%s city=%s auth=%s", order_id, _termin_uid, _t_city, _t_auth)
                logger.info("TERMIN_PAYMENT_SUCCESS | user=%s city=%s auth=%s order=%s", _termin_uid, _t_city, _t_auth, order_id)
                # Start real-time polling engine immediately after entitlement activation.
                # This ensures monitoring is running before the success message is sent.
                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp, is_polling as _isp
                    from utils.helpers import get_user_lang as _gul_poll
                    _p_bot = request.app["bot"]
                    _p_lang = (_gul_poll(int(_termin_uid)) or "uk").strip().lower()
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
                            on_found_fn=make_termin_found_fn(_p_bot),
                        )
                        logger.debug("TERMIN_ONLY_POLLING_STARTED: user=%s city=%s auth=%s", _termin_uid, _t_city, _t_auth)
                        logger.info("TERMIN_MONITORING_STARTED | user=%s city=%s auth=%s", _termin_uid, _t_city, _t_auth)
                    else:
                        logger.debug("TERMIN_ONLY_POLLING_ALREADY_RUNNING: user=%s", _termin_uid)
                except Exception as _pe:
                    logger.error("TERMIN_ONLY_POLLING_START_ERROR: user=%s err=%s", _termin_uid, _pe)
            except Exception as _tpe:
                logger.info("TERMIN_ONLY_PAID_ACTIVATION_ERROR: order_id=%s error=%s", order_id, _tpe)

        # Success UI is shown by the deeplink handler (paid_<order_id>) when the
        # user returns from Stripe. Webhook only activates entitlement + polling.
        # DO NOT call set_success_screen_shown(True) here — the barrier must stay
        # active until the deeplink handler confirms the success screen was delivered.
        # Unblocking here caused immediate SLOT_SENT before the user saw any screen.
        if _termin_uid:
            logger.info("TERMIN_MONITOR_ACTIVATED_SILENT | user=%s — barrier kept until deeplink", _termin_uid)

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
                # Stripe metadata is the ONLY source of truth for city/authority.
                # Never read from DB — DB may contain stale values from a previous payment.
                _city = metadata.get("city") or "berlin"
                _t_auth = metadata.get("authority") or "buergeramt"
                logger.info(
                    "WEBHOOK_METADATA | user=%s city=%s authority=%s order=%s",
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
                from datetime import datetime as _dt24h, timedelta as _td24h
                _paid_until_24h = (_dt24h.utcnow() + _td24h(hours=24)).isoformat()
                _upsert_ent(
                    str(_termin_uid),
                    plan="single",
                    slots_total=1,
                    stripe_session_id=session_id or f"termin_{order_id}",
                    paid_until=_paid_until_24h,
                )
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

                # Start real-time polling engine immediately after entitlement activation
                try:
                    from handlers.termin import (
                        make_termin_send_fn,
                        make_termin_on_reserved_fn,
                        make_termin_found_fn,
                    )
                    from utils.termin_checker import start_polling as _stp, is_polling as _isp
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
                            on_found_fn=make_termin_found_fn(_bot_inst),
                        )
                        logger.debug("TERMIN_MONITOR_24H_POLLING_STARTED: user=%s city=%s auth=%s", _termin_uid, _city, _t_auth)
                        logger.info("TERMIN_MONITORING_STARTED | user=%s city=%s auth=%s", _termin_uid, _city, _t_auth)
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
                await _send_termin_activation_message(_bot_inst, int(_termin_uid), _city, _t_auth, _m_lang, plan="24h")
                # Mark as delivered immediately after sending the activation UI so that
                # the deeplink (fired by Stripe redirect) sees is_order_delivered=True
                # and shows only a compact ACK instead of a duplicate legacy screen.
                try:
                    db.mark_order_delivered(order_id)
                except Exception as _md_24h:
                    logger.warning("MARK_ORDER_DELIVERED_FAILED 24h | order=%s err=%s", order_id, _md_24h)
                # Lift the barrier AFTER the activation message is delivered to the user.
                # Moving this before the await caused SLOT_SENT before success screen arrived.
                try:
                    from utils.termin_checker import set_success_screen_shown as _sss_m
                    _sss_m(int(_termin_uid), True)
                except Exception:
                    pass
            except Exception as _me:
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
                    create_reminder as _create_7d_reminder,
                )
                from datetime import datetime as _dt7, timedelta as _td7
                _7d_lang = (get_user_lang(_termin_uid) or "en").strip().lower()
                _7d_city = metadata.get("city") or "berlin"
                _7d_auth = metadata.get("authority") or "buergeramt"
                _paid_until_7d = (_dt7.utcnow() + _td7(days=7)).isoformat()

                _crt_7d(str(_termin_uid))
                _upd_7d(str(_termin_uid), has_paid_termin=1, city=_7d_city, authority=_7d_auth)
                _upsert_7d(
                    str(_termin_uid),
                    plan="7day",
                    slots_total=1,
                    stripe_session_id=session_id or f"7day_{order_id}",
                    paid_until=_paid_until_7d,
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
                    from utils.termin_checker import start_polling as _stp_7d, is_polling as _isp_7d
                    _bot_inst_7d = request.app["bot"]
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
                            on_found_fn=make_termin_found_fn(_bot_inst_7d),
                        )
                        logger.info("TERMIN_7DAY_POLLING_STARTED | user=%s city=%s auth=%s", _termin_uid, _7d_city, _7d_auth)
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
                await _send_termin_activation_message(_bot_inst, int(_termin_uid), _7d_city, _7d_auth, _7d_lang, plan="7day")
                # Mark as delivered immediately after sending the activation UI so that
                # the deeplink (fired by Stripe redirect) sees is_order_delivered=True
                # and shows only a compact ACK instead of a duplicate legacy screen.
                try:
                    db.mark_order_delivered(order_id)
                except Exception as _md_7d:
                    logger.warning("MARK_ORDER_DELIVERED_FAILED 7day | order=%s err=%s", order_id, _md_7d)
                # Lift the barrier AFTER the activation message is delivered to the user.
                # Moving this before the await caused SLOT_SENT before success screen arrived.
                try:
                    from utils.termin_checker import set_success_screen_shown as _sss_7d
                    _sss_7d(int(_termin_uid), True)
                except Exception:
                    pass
            except Exception as _7de:
                logger.error("TERMIN_7DAY_ACTIVATION_FAILED | order=%s error=%s", order_id, _7de)
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
    _wh_lang_raw = (_wh_get_lang(int(user_id)) or "en").strip().lower()
    _wh_lang = "uk" if _wh_lang_raw == "ua" else _wh_lang_raw
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
            _email_lang = _wh_lang_raw
            _email_ok = False

            logger.info("EMAIL_FLOW_START order=%s", order_id)

            # Fallback 1: email saved to orders.customer_email column
            if not _customer_email:
                _customer_email = (_refreshed_order or {}).get("customer_email") or None
                if _customer_email:
                    logger.info("EMAIL_FOUND: source=db_customer_email order=%s email=%s", order_id, _customer_email)

            # Fallback 2: email field inside user_data JSON (submitted via WebApp form)
            if not _customer_email:
                try:
                    import json as _json_mod
                    _raw_ud = (_refreshed_order or {}).get("user_data") or ""
                    _ud_parsed = _json_mod.loads(_raw_ud) if _raw_ud else {}
                    _customer_email = (_ud_parsed.get("email") or "").strip() or None
                    if _customer_email:
                        logger.info("EMAIL_FOUND: source=user_data_json order=%s email=%s", order_id, _customer_email)
                        db.save_customer_email(order_id, _customer_email)
                except Exception as _ud_email_err:
                    logger.debug("EMAIL_FALLBACK_PARSE_ERROR: %s", _ud_email_err)

            if _customer_email:
                logger.info("USER_EMAIL_RESOLVED=%s order=%s", _customer_email, order_id)
            else:
                logger.error("NO_EMAIL_ABORT: no email found in Stripe session, DB, or user_data order=%s", order_id)

            if _customer_email:
                try:
                    from utils.email_sender import send_pdf_by_email
                    from backend.settings import settings as _settings

                    if not _settings.email.ENABLED:
                        logger.warning("EMAIL_KILL_SWITCH_OFF: order=%s — EMAIL_ENABLED=0", order_id)
                    elif not db.claim_email_send(order_id):
                        logger.info("EMAIL_ALREADY_CLAIMED: order=%s — skipping duplicate", order_id)
                    else:
                        _pdf_path = _delivered_pdf_path or (_refreshed_order or {}).get("file_path")
                        _pdf_exists = bool(_pdf_path and os.path.exists(_pdf_path))
                        _pdf_size   = os.path.getsize(_pdf_path) if _pdf_exists else 0
                        logger.info(
                            "ATTACHMENT_PATH=%s exists=%s size=%d",
                            _pdf_path, _pdf_exists, _pdf_size,
                        )
                        if _pdf_exists and _pdf_size > 0:
                            logger.info("EMAIL_SEND_START order=%s email=%s", order_id, _customer_email)
                            try:
                                _email_ok = await asyncio.wait_for(
                                    send_pdf_by_email(
                                        to_email=_customer_email,
                                        pdf_path=_pdf_path,
                                        doc_type=_doc_type_for_msg,
                                        lang=_email_lang,
                                    ),
                                    timeout=20.0,
                                )
                            except asyncio.TimeoutError:
                                logger.error("EMAIL_FAILED order=%s error=%s", order_id, "timeout after 20s")
                                _email_ok = False
                            except Exception as _send_err:
                                logger.error("EMAIL_FAILED order=%s error=%s", order_id, repr(_send_err))
                                _email_ok = False
                            if _email_ok:
                                logger.info("EMAIL_SEND_SUCCESS order=%s", order_id)
                            else:
                                logger.error(
                                    "EMAIL_FAILED order=%s error=%s",
                                    order_id, "send_pdf_by_email returned False",
                                )
                        elif not _pdf_exists:
                            logger.error(
                                "PDF_MISSING order=%s path=%r — email aborted",
                                order_id, _pdf_path,
                            )
                        else:
                            logger.error(
                                "PDF_MISSING order=%s path=%r size=0 — email aborted",
                                order_id, _pdf_path,
                            )
                except asyncio.TimeoutError:
                    logger.error("EMAIL_FAILED order=%s error=timeout_after_20s", order_id)
                except Exception as _email_err:
                    logger.error("EMAIL_FAILED order=%s error=%s", order_id, repr(_email_err))
            else:
                logger.error("NO_EMAIL_ABORT order=%s — no customer email found", order_id)

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

            def _build_receipt(lang: str) -> str:
                _l = lang if lang in _RECEIPT_CONFIRMED else "en"
                lines = [
                    _RECEIPT_CONFIRMED.get(_l, _RECEIPT_CONFIRMED["en"]),
                    _RECEIPT_PDF_READY.get(_l, _RECEIPT_PDF_READY["en"]),
                ]
                if _customer_email and _email_ok:
                    lines.append(_RECEIPT_EMAIL_OK.get(_l, _RECEIPT_EMAIL_OK["en"]))
                elif _customer_email and not _email_ok:
                    lines.append(_RECEIPT_EMAIL_FAIL.get(_l, _RECEIPT_EMAIL_FAIL["en"]))
                return "\n".join(lines)

            # Build post-payment keyboard via the canonical builder (Official Form,
            # Instructions, Termin CTA, What Next) — fully localised for all 6 languages.
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

            # === SINGLE TELEGRAM MESSAGE: PDF file + receipt caption ===
            # This is the ONLY message the user receives for this payment.
            try:
                await _wh_bot.send_chat_action(chat_id=int(user_id), action="upload_document")
            except Exception:
                pass
            _pdf_for_send = _delivered_pdf_path
            if _pdf_for_send and os.path.exists(_pdf_for_send):
                try:
                    with open(_pdf_for_send, "rb") as _pf:
                        await _wh_bot.send_document(
                            chat_id=int(user_id),
                            document=_pf,
                            caption=_build_receipt(_wh_lang),
                            parse_mode="HTML",
                            reply_markup=_receipt_kb,
                        )
                    logger.info("SINGLE_MESSAGE_SENT: order=%s user=%s email_ok=%s", order_id, user_id, _email_ok)
                except Exception as _send_err:
                    logger.error("SINGLE_MESSAGE_FAILED: order=%s err=%s", order_id, _send_err)
                    # Fallback: send receipt as text so user is at least notified
                    try:
                        await _wh_bot.send_message(
                            chat_id=int(user_id),
                            text=_build_receipt(_wh_lang),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
            else:
                # PDF path unavailable (ummeldung multiple-file case or path lost) —
                # fall back to text-only receipt so user is always notified.
                logger.warning("PDF_PATH_UNAVAILABLE: order=%s — sending text receipt", order_id)
                try:
                    await _wh_bot.send_message(
                        chat_id=int(user_id),
                        text=_build_receipt(_wh_lang),
                        parse_mode="HTML",
                        reply_markup=_receipt_kb,
                    )
                    logger.info("TEXT_RECEIPT_SENT: order=%s user=%s", order_id, user_id)
                except Exception as _fallback_err:
                    logger.warning("TEXT_RECEIPT_FAILED: order=%s err=%s", order_id, _fallback_err)

            # === PDF CLEANUP — only when email delivery succeeded (keep file on disk if email failed) ===
            if _email_ok and _delivered_pdf_path:
                try:
                    from backend.utils.pdf_cleanup import delete_pdf_after_delivery
                    delete_pdf_after_delivery(_delivered_pdf_path)
                except Exception as _cleanup_err:
                    logger.debug("WEBHOOK_PDF_CLEANUP_FAILED: order=%s err=%s", order_id, _cleanup_err)
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
            get_users_with_active_monitoring,
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
        candidates = get_users_with_active_monitoring()
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
        _DEV_TEST_USERS = {402229082}
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
            on_found_fn=make_termin_found_fn(bot_instance),
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
                        "🔄 <b>Моніторинг відновлено</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Перевірки тривають автоматично."
                    ),
                    "ua": (
                        "🔄 <b>Моніторинг відновлено</b>\n\n"
                        "📍 {city}\n"
                        "📄 {authority}\n\n"
                        "Перевірки тривають автоматично."
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

    # === EMAIL SMTP PROBE (detects bad credentials before first payment) ===
    try:
        from utils.email_sender import send_test_email as _smtp_probe
        _test_to = os.getenv("EMAIL_SMTP_USER", "")
        if _test_to:
            import threading as _thr
            _thr.Thread(
                target=_smtp_probe,
                args=(_test_to,),
                daemon=True,
                name="smtp-probe",
            ).start()
    except Exception as _probe_err:
        logger.warning("⚠️ SMTP probe failed to launch (non-critical): %s", _probe_err)

    # === CLEANUP OLD GENERATED PDFs (GDPR — remove stale PII files) ===
    try:
        from backend.utils.pdf_cleanup import cleanup_old_pdfs
        cleanup_old_pdfs(max_age_hours=2)
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

    # === RESUME TERMIN MONITORING ===
    # Runs as a background task so dp.start_polling() is not delayed.
    async def _resume_termin_monitoring_bg():
        try:
            await _resume_termin_monitoring(bot)
        except Exception as e:
            logger.error("❌ Termin monitoring resume failed: %s", e)
    asyncio.create_task(_resume_termin_monitoring_bg())

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
    app.router.add_get("/", _serve_webapp_html)
    app.router.add_get("/form", _serve_webapp_html)
    app.router.add_get("/index.html", _serve_webapp_html)
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

    # === RATING HANDLER ===
    # Catch-all: must be the very last registration.
    # Returns True so LoggingMiddleware logs "Handled" instead of "Unhandled".
    async def _catch_all_callback(callback: types.CallbackQuery):
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

