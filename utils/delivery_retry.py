# -*- coding: utf-8 -*-
"""
PDF Delivery Retry Queue

Simple, safe retry logic for failed PDF deliveries.
No external queue — uses SQLite orders table and an in-process asyncio loop.

Rules:
  - Only retries orders with status = FAILED (never SENT/DOWNLOADED)
  - Idempotency: deliver_document_after_payment has claim_delivery guard
  - MAX_RETRIES attempts with exponential-ish backoff (1m → 5m → 15m)
  - After final failure: logs CRITICAL + alerts admins
  - Zero new DB tables — uses existing orders.status column
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3
DELAYS: list = [60, 300, 900]   # seconds: 1m, 5m, 15m

# In-memory tracking: order_id → attempt count
# Resets on restart (intentional — fresh start after crash = clean slate)
_retry_state: Dict[int, int] = {}

# Product types that are NOT PDF documents.
# These orders are fulfilled by their own activation paths (Termin webhooks, etc.)
# and must NEVER enter the PDF delivery retry pipeline.
_NON_PDF_DOC_TYPES: frozenset = frozenset({
    "termin_monitor_24h",
    "termin_monitor_7day",
    "termin_monitor_30day",
    "termin_monitor_family",
    "termin_notifications",
    "termin_reservation",
    "termin_priority_boost",
    "termin_extend_24h",
})


async def _attempt_delivery(bot, order_id: int, attempt: int) -> bool:
    """Try once. Returns True on success, False on failure."""
    from handlers.stripe_handler import deliver_document_after_payment
    try:
        result = await deliver_document_after_payment(bot, order_id, force=True)
        if result:
            # Email block lives in bot.py webhook handler which is bypassed here —
            # attempt email inline so the user always receives an email on retry.
            await _attempt_email_after_delivery(order_id)
        return bool(result)
    except Exception as exc:
        logger.warning(
            "DELIVERY_RETRY_FAIL | order=%s attempt=%d/%d err=%s",
            order_id, attempt, MAX_RETRIES, str(exc)[:120],
        )
        return False


async def _attempt_email_after_delivery(order_id: int) -> None:
    """Best-effort email send for paths that bypass bot.py's email block (retry / deeplink)."""
    import os
    _claim_won = False
    _db = None
    logger.warning("EMAIL_FLOW_ENTERED order=%s", order_id)
    try:
        from utils.helpers import get_db
        from utils.user_email import resolve_email_for_order
        from utils.email_sender import send_pdf_by_email
        _db = get_db()
        order = _db.get_order(order_id)
        if not order:
            logger.error("EMAIL_FLOW_NO_ORDER order=%s", order_id)
            return
        user_id = order.get("user_id")
        pdf_path = order.get("file_path")
        logger.warning("EMAIL_FLOW_DEBUG order=%s pdf_path=%r user_id=%s", order_id, pdf_path, user_id)
        if not pdf_path or not os.path.exists(pdf_path):
            logger.error("PDF_MISSING_FOR_EMAIL order=%s path=%r", order_id, pdf_path)
            return
        email = resolve_email_for_order(int(user_id), order_id, db=_db)
        logger.warning("EMAIL_FLOW_RESOLVED order=%s email=%s", order_id, bool(email))
        if not email:
            logger.error("NO_EMAIL_ABORT order=%s — no email in DB or user_data", order_id)
            # Show the "Enter email" prompt so the user can still receive the PDF.
            try:
                from utils.runtime_bot import get_runtime_bot as _get_rbot
                from handlers.stripe_handler import send_email_capture_offer as _cap_offer
                _rbot = _get_rbot()
                if _rbot and user_id:
                    _lang = (order.get("lang") or "en")
                    if _lang == "ua":
                        _lang = "uk"
                    asyncio.create_task(_cap_offer(_rbot, int(user_id), order_id, _lang))
                    logger.info("EMAIL_CAPTURE_OFFER_SCHEDULED order=%s user=%s", order_id, user_id)
            except Exception as _cap_err:
                logger.warning("EMAIL_CAPTURE_OFFER_FAIL order=%s err=%s", order_id, _cap_err)
            return
        if not _db.claim_email_send(order_id):
            logger.info("RETRY_EMAIL_ALREADY_CLAIMED order=%s", order_id)
            return
        _claim_won = True
        lang = (order.get("lang") or "en")
        if lang == "ua":
            lang = "uk"
        ok = await send_pdf_by_email(
            to_email=email,
            pdf_path=pdf_path,
            doc_type=order.get("doc_type", "document"),
            lang=lang,
        )
        if ok:
            logger.warning("EMAIL_SENT_CONFIRMED order=%s email_present=True", order_id)
            if _claim_won:  # guard: only confirm when this call actually owned the claim
                _db.confirm_email_sent(order_id)
            _claim_won = False  # claim fully resolved — no release needed in except
        else:
            logger.error("RETRY_EMAIL_FAILED order=%s — releasing claim", order_id)
            _db.release_email_claim(order_id)
            _claim_won = False
    except Exception as exc:
        logger.error("RETRY_EMAIL_ERROR order=%s err=%s", order_id, exc)
        # Release email_sending=0 so the next attempt can retry
        if _claim_won and _db is not None:
            try:
                _db.release_email_claim(order_id)
            except Exception:
                pass


async def schedule_retry(bot, order_id: int) -> None:
    """
    Schedule up to MAX_RETRIES delivery attempts for order_id with backoff delays.
    Each call is fire-and-forget via asyncio.create_task — never blocks the caller.
    """
    asyncio.create_task(_retry_loop(bot, order_id))


async def _retry_loop(bot, order_id: int) -> None:
    """Internal: run the full retry sequence for one order."""
    from utils.helpers import get_db
    from backend.database import OrderStatus

    # Pre-flight: skip non-PDF orders entirely — they are fulfilled by their own
    # activation paths (Termin webhooks) and must never enter the PDF retry pipeline.
    try:
        _pre_db = get_db()
        _pre_order = _pre_db.get_order(order_id)
        if _pre_order:
            _pre_doc = (_pre_order.get("doc_type") or "").strip().lower()
            _pre_uid = _pre_order.get("user_id", "?")
            if _pre_doc in _NON_PDF_DOC_TYPES:
                logger.info(
                    "DELIVERY_SKIP_NON_PDF_ORDER | order_id=%s product_type=termin "
                    "doc_type=%s user_id=%s — skipping PDF retry entirely",
                    order_id, _pre_doc, _pre_uid,
                )
                return
    except Exception as _pre_err:
        logger.warning(
            "DELIVERY_RETRY_PREFLIGHT_ERR | order=%s err=%s — proceeding",
            order_id, _pre_err,
        )

    for attempt in range(1, MAX_RETRIES + 1):
        delay = DELAYS[attempt - 1]
        logger.info(
            "DELIVERY_RETRY_SCHEDULED | order=%s attempt=%d/%d delay=%ds",
            order_id, attempt, MAX_RETRIES, delay,
        )
        await asyncio.sleep(delay)

        # Re-check status — webhook may have delivered between attempts
        try:
            db = get_db()
            order = db.get_order(order_id)
            if not order:
                logger.info("DELIVERY_RETRY_ABORT | order=%s not found", order_id)
                return
            # Double-check product type on every attempt
            _doc = (order.get("doc_type") or "").strip().lower()
            if _doc in _NON_PDF_DOC_TYPES:
                logger.info(
                    "DELIVERY_SKIP_NON_PDF_ORDER | order_id=%s product_type=termin "
                    "doc_type=%s user_id=%s — aborting retry loop",
                    order_id, _doc, order.get("user_id", "?"),
                )
                return
            status = (order.get("status") or "").strip().lower()
            if status in (
                OrderStatus.PROCESSING.value,
                OrderStatus.SENT.value,
                OrderStatus.DOWNLOADED.value,
            ):
                logger.info(
                    "DELIVERY_RETRY_SKIP | order=%s already claimed or delivered (status=%s)",
                    order_id, status,
                )
                return
        except Exception as _db_err:
            logger.warning("DELIVERY_RETRY_DB_CHECK_FAIL | order=%s err=%s", order_id, _db_err)

        success = await _attempt_delivery(bot, order_id, attempt)
        if success:
            logger.info(
                "DELIVERY_RETRY_SUCCESS | order=%s attempt=%d/%d",
                order_id, attempt, MAX_RETRIES,
            )
            return

    # All attempts exhausted — alert admins
    logger.critical(
        "DELIVERY_RETRY_EXHAUSTED | order=%s all %d attempts failed — manual intervention required",
        order_id, MAX_RETRIES,
    )
    await _alert_admins_delivery_failed(bot, order_id)


async def _alert_admins_delivery_failed(bot, order_id: int) -> None:
    """Send a Telegram alert to all ADMIN_IDS when delivery permanently fails.

    Never fires for Termin / non-PDF orders — those are fulfilled by their own
    activation paths and must not generate spurious PDF-failure alerts.
    """
    import os
    try:
        from utils.helpers import get_db
        db = get_db()
        order = db.get_order(order_id) or {}
        user_id  = order.get("user_id", "?")
        doc_type_raw = (order.get("doc_type") or "").strip().lower()
        doc_type_display = (order.get("doc_type") or "?").replace("_", " ").title()
        amount   = order.get("price") or order.get("amount") or "?"

        # Guard: never alert for non-PDF/Termin orders
        if doc_type_raw in _NON_PDF_DOC_TYPES:
            logger.info(
                "DELIVERY_SKIP_NON_PDF_ORDER | order_id=%s product_type=termin "
                "doc_type=%s user_id=%s — suppressing PDF failure alert",
                order_id, doc_type_raw, user_id,
            )
            return

        _admin_ids = [
            int(x.strip())
            for x in os.getenv("ADMIN_IDS", "").split(",")
            if x.strip().isdigit()
        ]
        if not _admin_ids:
            logger.warning("DELIVERY_RETRY_ALERT: no ADMIN_IDS configured")
            return
        msg = (
            f"🚨 <b>PDF Delivery Failed — Manual Action Required</b>\n\n"
            f"🔑 Order: <code>{order_id}</code>\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"📄 Doc: {doc_type_display}\n"
            f"💶 Amount: €{amount}\n"
            f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n\n"
            f"All {MAX_RETRIES} retry attempts failed.\n"
            f"Check logs for DELIVERY_RETRY_FAIL entries."
        )
        for admin_id in _admin_ids:
            try:
                await bot.send_message(admin_id, msg, parse_mode="HTML")
            except Exception as _send_err:
                logger.error("DELIVERY_ALERT_SEND_FAIL | admin=%s err=%s", admin_id, _send_err)
    except Exception as exc:
        logger.error("DELIVERY_RETRY_ALERT_ERROR: %s", exc)
