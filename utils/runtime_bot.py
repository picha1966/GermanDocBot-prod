# -*- coding: utf-8 -*-
"""Single process-wide Telegram Bot instance (set from bot.py at startup).

Avoids `from bot import bot` in utils/handlers — that pattern duplicated Bot
state when multiple entry modules existed and complicates tests.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

_rbot: Optional["Bot"] = None


def set_runtime_bot(bot: "Bot") -> None:
    global _rbot
    _rbot = bot


def get_runtime_bot() -> Optional["Bot"]:
    return _rbot
