# -*- coding: utf-8 -*-
"""
Termin Auditor v2.0 — Deep System Verification

Runs once every 24 hours. For each Premium city it calls
check_termin_availability() AUDIT_RETRIES times, analyses the results,
and sends a structured alert to all ADMIN_IDS *only when problems are found*.

Improvements over v1.0:
  - Severity levels: WARNING (slow) vs CRITICAL (failing)
  - Alert cooldown: repeated identical problem → suppressed for ALERT_COOLDOWN_MIN
  - Aggregated single message (no per-city spam)
  - All-OK runs stay in logs only — no Telegram noise

Rules:
  - NEVER contacts Telegram users
  - ONLY notifies ADMIN_IDS on problems
  - ONLY calls check_termin_availability()
  - Sequential checks — never overloads servers
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audit targets — must mirror _MONITOR_TARGETS in termin_monitor.py
# ---------------------------------------------------------------------------
_AUDIT_TARGETS: Dict[str, str] = {
    "berlin":      "anmeldung",
    "frankfurt":   "buergeramt",
    "duesseldorf": "buergeramt",
    "muenchen":    "buergeramt",
    "koeln":       "buergeramt",
}

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
AUDIT_INTERVAL_HOURS: int = 24
AUDIT_RETRIES: int        = 3
AUDIT_DELAY_SEC: int      = 5    # pause between retries for the same city

# Severity thresholds
WARN_AVG_SEC: float  = 8.0   # avg response > this → WARNING even if no errors
CRIT_FAIL_MIN: int   = 2     # fail_count >= this → CRITICAL

# Cooldown: minimum gap between any two alerts (hard rate-limit)
ALERT_COOLDOWN_MIN: int = 60

# ---------------------------------------------------------------------------
# In-memory state (resets on restart — acceptable for 24h cycle)
# ---------------------------------------------------------------------------
_last_alert_at: Optional[datetime]        = None
# Maps city → severity at the time of the last sent alert, e.g. {"duesseldorf": "WARNING"}
_last_sent_severities: Dict[str, str]     = {}


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------
def _city_severity(result: Dict) -> str:
    """Return 'CRITICAL', 'WARNING', or 'OK' for a single city result."""
    if result["fail_count"] >= CRIT_FAIL_MIN or (
        len(set(result["statuses"])) == 1 and result["statuses"][0] != "OK"
    ):
        return "CRITICAL"
    if result["avg_time"] > WARN_AVG_SEC and result["success_count"] > 0:
        return "WARNING"
    return "OK"


# ---------------------------------------------------------------------------
# Single city audit
# ---------------------------------------------------------------------------
async def _audit_city(city: str, authority: str) -> Dict:
    """Run AUDIT_RETRIES checks for one city. Returns per-city result dict."""
    from utils.termin_checker import check_termin_availability
    import time

    statuses: List[str] = []
    times: List[float]  = []

    for attempt in range(AUDIT_RETRIES):
        if attempt > 0:
            await asyncio.sleep(AUDIT_DELAY_SEC)

        t0 = time.monotonic()
        try:
            _status_enum, _details = await check_termin_availability(city, authority)
            elapsed = time.monotonic() - t0
            statuses.append("OK")
            times.append(elapsed)
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            statuses.append("TIMEOUT")
            times.append(elapsed)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            statuses.append("ERROR")
            times.append(elapsed)
            logger.warning(
                "AUDITOR_CHECK_FAIL | city=%s attempt=%d exc=%s",
                city, attempt + 1, str(exc)[:80],
            )

    success_count = statuses.count("OK")
    fail_count    = AUDIT_RETRIES - success_count
    avg_time      = sum(times) / len(times) if times else 0.0
    severity      = _city_severity({
        "statuses": statuses, "fail_count": fail_count,
        "success_count": success_count, "avg_time": avg_time,
    })

    return {
        "city":          city,
        "authority":     authority,
        "statuses":      statuses,
        "success_count": success_count,
        "fail_count":    fail_count,
        "avg_time":      avg_time,
        "severity":      severity,
        "is_problem":    severity != "OK",
    }


# ---------------------------------------------------------------------------
# Build aggregated Telegram alert
# ---------------------------------------------------------------------------
_CITY_DISPLAY: Dict[str, str] = {
    "berlin":      "Berlin",
    "frankfurt":   "Frankfurt",
    "duesseldorf": "Düsseldorf",
    "muenchen":    "München",
    "koeln":       "Köln",
}

_SEVERITY_ICON: Dict[str, str] = {
    "CRITICAL": "🚨",
    "WARNING":  "⚠️",
    "OK":       "✅",
}


def _build_alert(results: List[Dict], started_at: datetime) -> str:
    """
    Build a single aggregated alert message.
    Only problem cities are listed in detail; OK cities shown as a count.
    """
    problems  = [r for r in results if r["is_problem"]]
    ok_count  = len(results) - len(problems)

    has_critical = any(r["severity"] == "CRITICAL" for r in problems)
    header = (
        "🚨 <b>Termin Auditor — CRITICAL</b>"
        if has_critical else
        "⚠️ <b>Termin Auditor — WARNING</b>"
    )

    lines = [header, ""]

    for r in problems:
        icon   = _SEVERITY_ICON[r["severity"]]
        name   = _CITY_DISPLAY.get(r["city"], r["city"].title())
        detail = " ".join(r["statuses"])
        lines.append(f"{icon} <b>{name}</b>: {detail}  avg {r['avg_time']:.1f}s")

    lines.append("")
    lines.append(
        f"✅ {ok_count} city/cities OK"
        if ok_count else
        "❌ All cities affected"
    )
    lines.append(f"🕐 {started_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total issues: {len(problems)}/{len(results)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Debounce + cooldown check
# ---------------------------------------------------------------------------
def _should_send_alert(current_severities: Dict[str, str]) -> bool:
    """
    Return True only when the alert carries new information:
      • a city appeared in / disappeared from the problem list, OR
      • an existing city's severity changed (WARNING ↔ CRITICAL).

    Even when there IS a change, the hard cooldown (ALERT_COOLDOWN_MIN) prevents
    sending more than once per hour — protects against flapping.

    _last_sent_severities is updated only when True is returned.
    """
    global _last_alert_at, _last_sent_severities

    now = datetime.now()

    # Hard cooldown — never fire more often than ALERT_COOLDOWN_MIN
    if (
        _last_alert_at is not None
        and (now - _last_alert_at) < timedelta(minutes=ALERT_COOLDOWN_MIN)
    ):
        minutes_ago = int((now - _last_alert_at).total_seconds() // 60)
        logger.info(
            "AUDITOR_COOLDOWN | last alert %d min ago — suppressing | cities=%s",
            minutes_ago, list(current_severities),
        )
        return False

    # State-change check — only alert when something actually changed
    if current_severities == _last_sent_severities:
        logger.info(
            "AUDITOR_DEBOUNCE | same problems/severities as last alert — suppressing | %s",
            current_severities,
        )
        return False

    # Describe what changed for the log
    added    = set(current_severities) - set(_last_sent_severities)
    removed  = set(_last_sent_severities) - set(current_severities)
    changed  = {
        c for c in current_severities
        if c in _last_sent_severities and current_severities[c] != _last_sent_severities[c]
    }
    logger.info(
        "AUDITOR_STATE_CHANGE | new=%s resolved=%s severity_changed=%s",
        sorted(added), sorted(removed), sorted(changed),
    )

    _last_alert_at       = now
    _last_sent_severities = dict(current_severities)
    return True


# ---------------------------------------------------------------------------
# Full audit cycle
# ---------------------------------------------------------------------------
async def run_full_audit(bot) -> None:
    """Audit all Premium cities; alert admins only on problems (with cooldown)."""
    from config import ADMIN_IDS, is_dev_client_mode

    started_at = datetime.now()
    logger.info("AUDITOR_START | %s", started_at.strftime("%Y-%m-%d %H:%M"))

    results: List[Dict] = []
    for city, authority in _AUDIT_TARGETS.items():
        try:
            result = await _audit_city(city, authority)
            results.append(result)
            logger.info(
                "AUDITOR_CITY_DONE | city=%-12s severity=%-8s statuses=%s avg=%.2fs",
                city, result["severity"], result["statuses"], result["avg_time"],
            )
        except Exception as exc:
            logger.error("AUDITOR_CITY_CRASH | city=%s exc=%s", city, exc)
            results.append({
                "city": city, "authority": authority,
                "statuses": ["CRASH"], "success_count": 0,
                "fail_count": AUDIT_RETRIES, "avg_time": 0.0,
                "severity": "CRITICAL", "is_problem": True,
            })

    problem_cities = [r["city"] for r in results if r["is_problem"]]
    # Map of city → severity for all problem cities (used for state-change detection)
    current_severities: Dict[str, str] = {
        r["city"]: r["severity"] for r in results if r["is_problem"]
    }

    if not problem_cities:
        logger.info(
            "AUDITOR_ALL_OK | cities=%d | avg=%.2fs",
            len(results),
            sum(r["avg_time"] for r in results) / len(results) if results else 0,
        )
        # If problems were present before but everything is now OK → notify recovery
        if _last_sent_severities:
            if _should_send_alert(current_severities):
                recovery_text = (
                    "✅ <b>Termin Auditor — All systems recovered</b>\n\n"
                    + f"Previously affected: {', '.join(_last_sent_severities)}\n"
                    + f"🕐 {started_at.strftime('%Y-%m-%d %H:%M')}"
                )
                for admin_id in ADMIN_IDS:
                    if is_dev_client_mode(admin_id):
                        continue
                    try:
                        await bot.send_message(admin_id, recovery_text, parse_mode="HTML")
                    except Exception as exc:
                        logger.error("AUDITOR_SEND_FAIL | admin=%s exc=%s", admin_id, exc)
    else:
        logger.warning("AUDITOR_PROBLEMS | cities=%s", problem_cities)

        if _should_send_alert(current_severities):
            alert_text = _build_alert(results, started_at)
            for admin_id in ADMIN_IDS:
                if is_dev_client_mode(admin_id):
                    continue
                try:
                    await bot.send_message(admin_id, alert_text, parse_mode="HTML")
                except Exception as exc:
                    logger.error("AUDITOR_SEND_FAIL | admin=%s exc=%s", admin_id, exc)

    logger.info(
        "AUDITOR_DONE | elapsed=%.0fs",
        (datetime.now() - started_at).total_seconds(),
    )


# ---------------------------------------------------------------------------
# Forever loop
# ---------------------------------------------------------------------------
_STARTUP_GRACE_SEC: int = 10 * 60  # 10-minute startup grace: admin can /dev_new before first alert


async def termin_audit_loop(bot) -> None:
    """Run a full audit once, then sleep AUDIT_INTERVAL_HOURS hours. Repeat forever.

    A startup grace period of _STARTUP_GRACE_SEC seconds is applied before the
    first audit run.  This gives admins time to issue /dev_new and suppress
    alerts while testing the onboarding flow after a bot restart.
    """
    logger.info(
        "AUDITOR_LOOP_START | interval=%dh | cities=%s | startup_grace=%ds",
        AUDIT_INTERVAL_HOURS, list(_AUDIT_TARGETS), _STARTUP_GRACE_SEC,
    )
    await asyncio.sleep(_STARTUP_GRACE_SEC)
    while True:
        try:
            await run_full_audit(bot)
        except Exception as exc:
            logger.error("AUDITOR_LOOP_CRASH | %s", exc)
        await asyncio.sleep(AUDIT_INTERVAL_HOURS * 3600)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def start_termin_auditor(bot) -> None:
    """Schedule the audit loop as a non-blocking background asyncio task."""
    asyncio.create_task(termin_audit_loop(bot))
    logger.info("AUDITOR_SCHEDULED | Termin Auditor v2.0 active")
