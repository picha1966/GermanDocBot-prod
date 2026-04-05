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


async def _attempt_delivery(bot, order_id: int, attempt: int) -> bool:
    """Try once. Returns True on success, False on failure."""
    from handlers.stripe_handler import deliver_document_after_payment
    try:
        result = await deliver_document_after_payment(bot, order_id, force=True)
        return bool(result)
    except Exception as exc:
        logger.warning(
            "DELIVERY_RETRY_FAIL | order=%s attempt=%d/%d err=%s",
            order_id, attempt, MAX_RETRIES, str(exc)[:120],
        )
        return False


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
            status = (order.get("status") or "").strip().lower()
            if status in (OrderStatus.SENT.value, OrderStatus.DOWNLOADED.value):
                logger.info(
                    "DELIVERY_RETRY_SKIP | order=%s already delivered (status=%s)",
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
    """Send a Telegram alert to all ADMIN_IDS when delivery permanently fails."""
    import os
    try:
        _admin_ids = [
            int(x.strip())
            for x in os.getenv("ADMIN_IDS", "").split(",")
            if x.strip().isdigit()
        ]
        if not _admin_ids:
            logger.warning("DELIVERY_RETRY_ALERT: no ADMIN_IDS configured")
            return
        from utils.helpers import get_db
        db = get_db()
        order = db.get_order(order_id) or {}
        user_id  = order.get("user_id", "?")
        doc_type = (order.get("doc_type") or "?").replace("_", " ").title()
        amount   = order.get("price") or order.get("amount") or "?"
        msg = (
            f"🚨 <b>PDF Delivery Failed — Manual Action Required</b>\n\n"
            f"🔑 Order: <code>{order_id}</code>\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"📄 Doc: {doc_type}\n"
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
