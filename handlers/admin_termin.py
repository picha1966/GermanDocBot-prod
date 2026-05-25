# -*- coding: utf-8 -*-
"""
handlers/admin_termin.py — Admin-only Termin observability commands.

Provides /termin_status command:
  - Shows all active in-memory polling sessions.
  - Enriches each session with plan/paid_until from DB (readonly GET).
  - Accessible only to ADMIN_IDS. Silently ignored for anyone else.

Does NOT modify any checker, entitlement, Stripe, or PDF logic.
"""

import logging
from datetime import datetime

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

from config import ADMIN_IDS
from utils.termin_checker import get_active_sessions_snapshot
from backend.termin_db import get_entitlement

logger = logging.getLogger(__name__)


async def cmd_termin_status(message: types.Message, state: FSMContext):
    """Admin-only: show a snapshot of all active Termin polling sessions."""
    if message.from_user.id not in ADMIN_IDS:
        return  # silently ignore non-admins

    sessions = get_active_sessions_snapshot()

    if not sessions:
        await message.answer(
            "📊 <b>Termin Monitor Status</b>\n\n"
            "No active polling sessions.",
            parse_mode="HTML",
        )
        return

    lines = [
        f"📊 <b>Termin Monitor Status</b>",
        f"Active sessions: <b>{len(sessions)}</b>",
        "",
    ]

    for idx, s in enumerate(sessions, start=1):
        ent = get_entitlement(str(s["user_id"])) or {}
        plan = ent.get("plan") or "?"
        paid_until_raw = ent.get("paid_until") or "?"

        # Format paid_until to a human-readable timestamp if parseable
        try:
            paid_until = datetime.fromisoformat(paid_until_raw).strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            paid_until = paid_until_raw

        lines.append(
            f"{'─' * 28}\n"
            f"<b>#{idx}</b> user=<code>{s['user_id']}</code>\n"
            f"   city=<b>{s['city']}</b>  auth=<b>{s['authority']}</b>\n"
            f"   status=<code>{s['status']}</code>\n"
            f"   plan=<b>{plan}</b>  paid_until=<code>{paid_until}</code>\n"
            f"   checks=<b>{s['checks_count']}</b>  last=<code>{s['last_check'] or '—'}</code>\n"
            f"   started=<code>{s['started_at']}</code>"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")
    logger.info(
        "ADMIN_TERMIN_STATUS | admin=%s sessions=%s",
        message.from_user.id, len(sessions),
    )


def register_admin_termin_handlers(dp: Dispatcher):
    dp.register_message_handler(
        cmd_termin_status,
        commands=["termin_status"],
        state="*",
    )
