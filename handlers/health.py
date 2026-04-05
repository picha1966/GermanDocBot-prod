# -*- coding: utf-8 -*-
"""
handlers/health.py — Termin System Health Command

/health shows the real-time status of all 5 Premium cities by reading
the last snapshot stored by utils/termin_monitor.py.

This handler is READ-ONLY:
  - No HTTP requests
  - No checker calls
  - No background tasks
  - No monitor logic
  - Only reads get_monitor_snapshot()
"""

import logging
from datetime import datetime

from aiogram import types, Dispatcher

logger = logging.getLogger(__name__)


async def cmd_health(message: types.Message) -> None:
    """Reply with the current Termin Monitor snapshot."""
    try:
        from utils.termin_monitor import get_monitor_snapshot
        snapshot = get_monitor_snapshot()
    except Exception as exc:
        logger.error("HEALTH_SNAPSHOT_ERROR | %s", exc)
        await message.answer("⚠️ Termin Monitor not available.")
        return

    if not snapshot:
        await message.answer(
            "⚠️ Termin Monitor not started yet.\n"
            "The first check runs 1 minute after bot startup."
        )
        return

    lines = ["🩺 <b>Termin System Health</b>\n"]

    for city, data in snapshot.items():
        status  = data.get("status", "UNKNOWN")
        elapsed = data.get("elapsed")
        checked = data.get("time")

        icon         = "🟢" if status == "OK" else "🔴"
        elapsed_str  = f"{elapsed:.2f}s" if isinstance(elapsed, (int, float)) else "—"
        city_label   = city.title().replace("Duesseldorf", "Düsseldorf") \
                                   .replace("Muenchen", "München") \
                                   .replace("Koeln", "Köln")

        lines.append(f"{icon} <code>{city_label:<12}</code> | {status:<10} | {elapsed_str}")

    # Last check timestamp from the most recent entry
    last_time = max(
        (d["time"] for d in snapshot.values() if isinstance(d.get("time"), datetime)),
        default=None,
    )
    if last_time:
        lines.append(f"\n🕐 Last check: {last_time.strftime('%Y-%m-%d %H:%M')}")

    try:
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as exc:
        logger.error("HEALTH_SEND_ERROR | %s", exc)


def register_health_handlers(dp: Dispatcher) -> None:
    dp.register_message_handler(cmd_health, commands=["health"], state="*")
