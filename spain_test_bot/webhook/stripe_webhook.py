"""
Spain Test Bot — Stripe webhook handler.

Handles POST /webhook from Stripe.
On checkout.session.completed:
  1. Verify signature
  2. Extract metadata (user_id, city, service, plan, lang)
  3. Activate paid subscription
  4. Start monitoring background task
  5. Send payment success message to user

Setup:
  - Add STRIPE_WEBHOOK_SECRET to .env
  - Set Stripe webhook URL to: https://<your-domain>/webhook
  - Use ngrok for local testing: ngrok http 8081
"""

from __future__ import annotations

import json
import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)


async def stripe_webhook_handler(request: web.Request) -> web.Response:
    """Main Stripe webhook entry point."""
    payload    = await request.read()
    sig_header = request.headers.get("Stripe-Signature", "")
    secret     = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # ── Verify signature ──────────────────────────────────────────────────────
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        if secret:
            event = stripe.Webhook.construct_event(payload, sig_header, secret)
        else:
            # Dev mode: skip signature verification if no secret is set
            logger.warning("WEBHOOK_NO_SECRET — skipping signature check (dev mode)")
            # ensure_ascii=False so Cyrillic / non-ASCII chars survive round-trip
            raw = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
            event = stripe.Event.construct_from(raw, stripe.api_key)
    except ValueError:
        logger.error("WEBHOOK_INVALID_PAYLOAD")
        return web.Response(status=400, text="Invalid payload")
    except Exception as exc:
        logger.error("WEBHOOK_SIGNATURE_FAILED | err=%s", exc)
        return web.Response(status=400, text="Signature verification failed")

    logger.info("WEBHOOK_EVENT | type=%s id=%s", event["type"], event.get("id", ""))

    # ── Handle checkout completed ─────────────────────────────────────────────
    if event["type"] == "checkout.session.completed":

        # ── Idempotency guard — skip already-processed events ─────────────────
        event_id = event.get("id", "")
        if event_id:
            try:
                from utils.payments_store import is_event_processed, mark_event_processed
                if is_event_processed(event_id):
                    logger.info("WEBHOOK_DUPLICATE_SKIPPED | event_id=%s", event_id)
                    return web.Response(text="OK")
                mark_event_processed(event_id)
            except Exception as _idem_exc:
                logger.warning("WEBHOOK_IDEMPOTENCY_CHECK_FAILED | err=%s", _idem_exc)

        session  = event["data"]["object"]
        metadata = session.get("metadata") or {}

        user_id_str = metadata.get("user_id", "")
        city        = metadata.get("city", "")
        service     = metadata.get("service", "")
        plan        = metadata.get("plan", "")
        lang        = metadata.get("lang", "en")

        if not all([user_id_str, city, service, plan]):
            logger.error(
                "WEBHOOK_MISSING_METADATA | meta=%s", metadata
            )
            return web.Response(text="OK")   # still 200 so Stripe doesn't retry

        user_id = int(user_id_str)

        # ── Activate subscription ─────────────────────────────────────────────
        try:
            from utils.payments import activate, send_payment_success
            activate(user_id, city, service, plan)
        except Exception as exc:
            logger.error("WEBHOOK_ACTIVATE_FAILED | user=%s err=%s", user_id, exc)
            return web.Response(text="OK")

        # ── Resolve display names ─────────────────────────────────────────────
        try:
            from utils.lang_store import get_lang
            from handlers.city_select import CITIES
            from handlers.service_select import SERVICES

            actual_lang  = get_lang(user_id) or lang

            def _t(d, lg): return d.get(lg) or d.get("en") or next(iter(d.values()))

            city_display = _t(CITIES.get(city, {"en": city.title()}), actual_lang)
            svc_info     = SERVICES.get(service, {})
            svc_display  = _t(svc_info.get("labels", {"en": service}), actual_lang)
            authority    = svc_info.get("authority", service)
        except Exception as exc:
            logger.error("WEBHOOK_DISPLAY_NAMES_FAILED | user=%s err=%s", user_id, exc)
            city_display = city
            svc_display  = service
            authority    = service
            actual_lang  = lang

        # ── Resolve bot instance ──────────────────────────────────────────────
        bot = request.app.get("bot")
        if not bot:
            # Last-resort: try to import the global bot instance from bot.py
            try:
                import importlib
                _bot_module = importlib.import_module("bot")
                bot = getattr(_bot_module, "bot", None)
                if bot:
                    logger.warning("WEBHOOK_BOT_FALLBACK — using imported bot instance")
            except Exception as _fb_exc:
                logger.error("WEBHOOK_BOT_FALLBACK_FAILED | err=%s", _fb_exc)

        if not bot:
            logger.error(
                "WEBHOOK_NO_BOT_INSTANCE | user=%s — activation saved to DB but "
                "monitoring NOT started and success message NOT sent",
                user_id,
            )
            return web.Response(text="OK")

        # ── Start monitoring ──────────────────────────────────────────────────
        next_check_str = ""
        last_check_str = ""
        try:
            from utils.monitoring import start_monitoring, get_session, human_last, human_next
            await start_monitoring(
                bot=bot,
                user_id=user_id,
                city=city,
                svc=service,
                authority=authority,
                city_display=city_display,
                svc_display=svc_display,
                lang=actual_lang,
            )
            logger.info(
                "WEBHOOK_MONITORING_STARTED | user=%s city=%s svc=%s plan=%s",
                user_id, city, service, plan,
            )
            # Grab live timing from the freshly created session
            _sess = get_session(user_id)
            if _sess:
                last_check_str = human_last(_sess.get("last_check_ts"), actual_lang)
                next_check_str = human_next(_sess.get("next_check_ts"), actual_lang)
        except Exception as exc:
            logger.error("WEBHOOK_MONITORING_START_FAILED | user=%s err=%s", user_id, exc)
            # Don't return early — still send the success message

        # ── Send activation message ───────────────────────────────────────────
        try:
            await send_payment_success(
                bot=bot,
                user_id=user_id,
                city_display=city_display,
                svc_display=svc_display,
                plan=plan,
                lang=actual_lang,
                next_check=next_check_str,
                last_check=last_check_str,
            )
        except Exception as exc:
            logger.error("WEBHOOK_SUCCESS_MSG_FAILED | user=%s err=%s", user_id, exc)

    return web.Response(text="OK")


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="Spain Test Bot webhook: OK")
