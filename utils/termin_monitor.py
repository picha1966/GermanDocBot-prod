# -*- coding: utf-8 -*-
"""
Termin Monitor v1.0 — Premium Monitoring System

Runs an independent background loop that checks all 5 Premium cities every
MONITOR_INTERVAL_MIN minutes, logs results to logs/termin_monitor.log, and
sends a Telegram alert to the admin when a checker fails TERMIN_ALERT_THRESHOLD
times in a row. Sends a recovery message when it comes back up.

This module NEVER modifies termin_checker.py or any handler. It only CALLS
check_termin_availability() and reacts to the outcome.

Cities monitored:
    Berlin, Frankfurt, Düsseldorf, München, Köln
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Monitoring targets — city → representative authority used for health-check
# ---------------------------------------------------------------------------
_MONITOR_TARGETS: Dict[str, str] = {
    "berlin":      "anmeldung",
    "frankfurt":   "buergeramt",
    "duesseldorf": "buergeramt",
    "muenchen":    "buergeramt",
    "koeln":       "buergeramt",
}

# ---------------------------------------------------------------------------
# Runtime state (per-city counters + alert flags)
# ---------------------------------------------------------------------------
_fail_counts:  Dict[str, int]  = {city: 0 for city in _MONITOR_TARGETS}
_alert_active: Dict[str, bool] = {city: False for city in _MONITOR_TARGETS}
_last_results: Dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Log file
# ---------------------------------------------------------------------------
_LOG_PATH: Optional[str] = None   # resolved lazily at first write


def _resolve_log_path() -> str:
    """Return absolute path to logs/termin_monitor.log, creating the dir."""
    global _LOG_PATH
    if _LOG_PATH is None:
        # Walk up from this file to the project root
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logs_dir = os.path.join(root, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        _LOG_PATH = os.path.join(logs_dir, "termin_monitor.log")
    return _LOG_PATH


def _log_monitor(city: str, status: str, elapsed: Optional[float]) -> None:
    """Append one line to logs/termin_monitor.log."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elapsed_str = f"{elapsed:.2f}s" if elapsed is not None else "-"
    line = f"{ts} | {city:<12} | {status:<16} | {elapsed_str}\n"
    try:
        with open(_resolve_log_path(), "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:
        logger.error("MONITOR_LOG_WRITE_FAIL | %s", exc)


# ---------------------------------------------------------------------------
# Alert helpers
# ---------------------------------------------------------------------------
async def _send_alert(bot, city: str, authority: str, fail_count: int,
                      error_detail: str) -> None:
    """Send failure alert to all admins."""
    from config import ADMIN_IDS
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        "⚠️ <b>Termin Checker Problem</b>\n\n"
        f"City: <b>{city.capitalize()}</b>\n"
        f"Authority: <b>{authority}</b>\n\n"
        f"Failed checks: <b>{fail_count}</b>\n"
        f"Error: <code>{error_detail}</code>\n\n"
        f"Time: {ts}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as exc:
            logger.error("MONITOR_ALERT_FAIL | admin=%s err=%s", admin_id, exc)


async def _send_recovery(bot, city: str, authority: str) -> None:
    """Send recovery notification to all admins."""
    from config import ADMIN_IDS
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = (
        "✅ <b>Termin Checker Recovered</b>\n\n"
        f"City: <b>{city.capitalize()}</b>\n"
        f"Authority: <b>{authority}</b>\n\n"
        f"System working again.\n"
        f"Time: {ts}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as exc:
            logger.error("MONITOR_RECOVERY_FAIL | admin=%s err=%s", admin_id, exc)


# ---------------------------------------------------------------------------
# Single-city check
# ---------------------------------------------------------------------------
async def _check_city(bot, city: str, authority: str) -> None:
    """Run one availability check for a city and handle the result."""
    from config import TERMIN_ALERT_THRESHOLD
    from utils.termin_checker import check_termin_availability

    status = "UNKNOWN"
    elapsed: Optional[float] = None
    error_detail = ""

    t0 = time.monotonic()
    try:
        _status_enum, _details = await check_termin_availability(city, authority)
        elapsed = time.monotonic() - t0
        status = "OK"

        _last_results[city] = {
            "status": status,
            "details": _details,
            "elapsed": elapsed,
            "time": datetime.now(),
        }

        # --- Success path: reset counter and send recovery if needed ---
        was_failing = _alert_active[city]
        _fail_counts[city] = 0
        if was_failing:
            _alert_active[city] = False
            logger.info("MONITOR_RECOVERED | city=%s", city)
            try:
                await _send_recovery(bot, city, authority)
            except Exception as exc:
                logger.error("MONITOR_RECOVERY_SEND_FAIL | city=%s exc=%s", city, exc)

        logger.info(
            "MONITOR_OK | city=%-12s authority=%-14s elapsed=%.2fs",
            city, authority, elapsed,
        )

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        status = "TIMEOUT"
        error_detail = f"timeout after {elapsed:.1f}s"
        _handle_failure(city, status, error_detail, elapsed)

    except Exception as exc:
        elapsed = time.monotonic() - t0
        status = "ERROR"
        error_detail = str(exc)[:120]
        _handle_failure(city, status, error_detail, elapsed)

    finally:
        _log_monitor(city, status, elapsed)

    # --- Send alert if threshold crossed (only once per incident) ---
    if (
        status != "OK"
        and _fail_counts[city] >= TERMIN_ALERT_THRESHOLD
        and not _alert_active[city]
    ):
        _alert_active[city] = True
        logger.warning(
            "MONITOR_ALERT | city=%s failed=%d times", city, _fail_counts[city]
        )
        try:
            await _send_alert(bot, city, authority, _fail_counts[city], error_detail)
        except Exception as exc:
            logger.error("MONITOR_ALERT_SEND_FAIL | city=%s exc=%s", city, exc)


def _handle_failure(city: str, status: str, error_detail: str,
                    elapsed: float) -> None:
    """Increment fail counter and log warning."""
    _fail_counts[city] += 1
    _last_results[city] = {
        "status": status,
        "details": {"error": error_detail},
        "elapsed": elapsed,
        "time": datetime.now(),
    }
    logger.warning(
        "MONITOR_FAIL | city=%-12s status=%-10s elapsed=%.2fs detail=%s fail_count=%d",
        city, status, elapsed, error_detail, _fail_counts[city],
    )


# ---------------------------------------------------------------------------
# Monitor cycle — one pass over all cities
# ---------------------------------------------------------------------------
async def run_monitor_cycle(bot) -> None:
    """Check all 5 Premium cities sequentially. Never raises."""
    logger.info("MONITOR_CYCLE_START | cities=%s", list(_MONITOR_TARGETS))
    for city, authority in _MONITOR_TARGETS.items():
        try:
            await _check_city(bot, city, authority)
        except Exception as exc:
            # Belt-and-suspenders: _check_city already catches everything,
            # but guard here too so one city cannot abort the whole cycle.
            logger.error(
                "MONITOR_CYCLE_UNHANDLED | city=%s exc=%s", city, exc
            )
            _log_monitor(city, "UNHANDLED_ERROR", None)
    logger.info("MONITOR_CYCLE_DONE")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
async def termin_monitor_loop(bot) -> None:
    """Forever loop: run a monitor cycle, then sleep MONITOR_INTERVAL_MIN minutes."""
    from config import MONITOR_INTERVAL_MIN

    logger.info(
        "MONITOR_LOOP_START | interval=%d min | targets=%s",
        MONITOR_INTERVAL_MIN, list(_MONITOR_TARGETS),
    )
    while True:
        try:
            await run_monitor_cycle(bot)
        except Exception as exc:
            logger.error("MONITOR_LOOP_CYCLE_CRASH | %s", exc)
        await asyncio.sleep(MONITOR_INTERVAL_MIN * 60)


# ---------------------------------------------------------------------------
# Public entry point — call from bot.py on_startup()
# ---------------------------------------------------------------------------
def start_termin_monitor(bot) -> None:
    """Schedule the monitor loop as a background asyncio task.

    Must be called from an already-running event loop (e.g. inside on_startup).
    """
    asyncio.create_task(termin_monitor_loop(bot))
    logger.info("MONITOR_SCHEDULED | Termin Monitor v1.0 active")


# ---------------------------------------------------------------------------
# Read-only snapshot — used by /health command
# ---------------------------------------------------------------------------
def get_monitor_snapshot() -> Dict[str, dict]:
    """Return a copy of the latest results for all monitored cities."""
    return dict(_last_results)
