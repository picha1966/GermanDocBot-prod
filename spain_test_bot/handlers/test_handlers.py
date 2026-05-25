"""
Test handlers for the Spain Test Bot.
Commands:
    /start  — greeting
    /test   — run Spain checker against barcelona/extranjeria
    /check <city> <authority> — run checker with custom params
"""

from __future__ import annotations

import logging

from aiogram import types
from aiogram.dispatcher import Dispatcher

from utils.spain_checker import check_spain_termin

logger = logging.getLogger(__name__)


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(msg: types.Message) -> None:
    await msg.answer(
        "🇪🇸 <b>Spain Test Bot — ready</b>\n\n"
        "Commands:\n"
        "/test — check Barcelona (extranjería / NIE-TIE)\n"
        "/check &lt;city&gt; &lt;authority&gt; — custom check\n\n"
        "Supported cities: barcelona, madrid, valencia, malaga\n"
        "Supported authorities: nie, tie, extranjeria, consulado, sede",
        parse_mode="HTML",
    )


# ── /test ──────────────────────────────────────────────────────────────────────

async def cmd_test(msg: types.Message) -> None:
    city, authority = "barcelona", "extranjeria"
    await msg.answer(f"🔍 Checking Spain slots…\n📍 {city.title()} / {authority}")

    try:
        result = await check_spain_termin(city, authority)
    except Exception as exc:
        logger.error("CMD_TEST_ERROR | err=%s", exc)
        await msg.answer(f"❌ Checker raised an exception:\n<code>{exc}</code>", parse_mode="HTML")
        return

    if not result:
        await msg.answer(
            "❌ <b>No slots found</b>\n\n"
            "Portal may be fully booked or the selector strategy needs updating.\n"
            "Check logs for SPAIN_* entries.",
            parse_mode="HTML",
        )
        return

    lines = [f"✅ <b>Found {len(result)} slot(s):</b>"]
    for i, slot in enumerate(result[:5], 1):
        date = slot.get("date") or "—"
        time = slot.get("time") or "—"
        location = slot.get("location") or "—"
        url = slot.get("url") or "—"
        lines.append(
            f"\n<b>#{i}</b>\n"
            f"📅 {date}  ⏰ {time}\n"
            f"📍 {location}\n"
            f"🔗 {url}"
        )

    await msg.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


# ── /check <city> <authority> ──────────────────────────────────────────────────

async def cmd_check(msg: types.Message) -> None:
    args = (msg.get_args() or "").strip().split()
    if len(args) < 2:
        await msg.answer(
            "Usage: /check <city> <authority>\n"
            "Example: /check madrid nie"
        )
        return

    city, authority = args[0].lower(), args[1].lower()
    await msg.answer(f"🔍 Checking: {city.title()} / {authority}…")

    try:
        result = await check_spain_termin(city, authority)
    except Exception as exc:
        await msg.answer(f"❌ Error: <code>{exc}</code>", parse_mode="HTML")
        return

    if not result:
        await msg.answer(f"❌ No slots found for {city.title()} / {authority}.")
        return

    slot = result[0]
    await msg.answer(
        f"✅ <b>FOUND</b>\n"
        f"📅 {slot.get('date', '—')}  ⏰ {slot.get('time', '—')}\n"
        f"📍 {slot.get('location', '—')}\n"
        f"🔗 {slot.get('url', '—')}\n\n"
        f"Total slots: {len(result)}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ── Registration ───────────────────────────────────────────────────────────────

def register(dp: Dispatcher) -> None:
    dp.register_message_handler(cmd_start, commands=["start"])
    dp.register_message_handler(cmd_test,  commands=["test"])
    dp.register_message_handler(cmd_check, commands=["check"])
