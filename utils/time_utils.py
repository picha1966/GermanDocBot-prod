# -*- coding: utf-8 -*-
"""
utils/time_utils.py — Termin Monitoring countdown helpers.
"""

from datetime import datetime, timezone
from typing import Optional


def format_remaining_time(paid_until: Optional[str], now: Optional[datetime] = None) -> str:
    """
    Return a short human-readable string of time remaining until paid_until.

    Returns "expired" if paid_until is None, unparseable, or already past.

    Examples:
        "6 d 18 h"
        "3 h 42 m"
        "17 m"
        "expired"
    """
    if not paid_until:
        return "expired"

    if now is None:
        now = datetime.utcnow()

    try:
        expires = datetime.fromisoformat(paid_until)
    except (ValueError, TypeError):
        return "expired"

    remaining = expires - now
    total_seconds = int(remaining.total_seconds())

    if total_seconds <= 0:
        return "expired"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    if days >= 1:
        return f"{days} d {hours} h"
    elif hours >= 1:
        return f"{hours} h {minutes} m"
    else:
        return f"{minutes} m"


# Localized countdown label templates — {time} is replaced at render time.
COUNTDOWN_LABEL = {
    "ua": "⏳ Залишилось часу: {time}",
    "uk": "⏳ Залишилось часу: {time}",
    "en": "⏳ Time remaining: {time}",
    "de": "⏳ Verbleibende Zeit: {time}",
    "pl": "⏳ Pozostały czas: {time}",
    "tr": "⏳ Kalan süre: {time}",
    "ar": "⏳ الوقت المتبقي: {time}",
}

# Localized "still active" label — shown inside slot-found notification.
COUNTDOWN_STILL_ACTIVE = {
    "ua": "⏳ Моніторинг ще активний: {time}",
    "uk": "⏳ Моніторинг ще активний: {time}",
    "en": "⏳ Monitoring still active: {time}",
    "de": "⏳ Überwachung weiterhin aktiv: {time}",
    "pl": "⏳ Monitoring nadal aktywny: {time}",
    "tr": "⏳ İzleme hâlâ aktif: {time}",
    "ar": "⏳ المراقبة ما تزال نشطة: {time}",
}


def get_countdown_line(paid_until: Optional[str], lang: str, still_active: bool = False) -> str:
    """
    Return a fully-formatted localized countdown line.

    Args:
        paid_until: ISO datetime string from entitlement record.
        lang: user language code.
        still_active: if True uses "Monitoring still active" phrasing.

    Returns empty string if paid_until is None (graceful fallback).
    """
    if not paid_until:
        return ""

    time_str = format_remaining_time(paid_until)
    if time_str == "expired":
        return ""

    _lang = lang if lang in COUNTDOWN_LABEL else "en"
    templates = COUNTDOWN_STILL_ACTIVE if still_active else COUNTDOWN_LABEL
    return templates.get(_lang, templates["en"]).format(time=time_str)
