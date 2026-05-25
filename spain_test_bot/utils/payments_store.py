"""
Spain Test Bot — persistent SQLite store for paid subscriptions.

Survives bot restarts. All writes go to both:
  - in-memory dict (fast reads, zero latency)
  - SQLite file     (persistence across restarts)

DB location: spain_test_bot/data/payments.db

Schema:
  paid_subscriptions(
      user_id      INTEGER PRIMARY KEY,
      city         TEXT,
      service      TEXT,
      plan         TEXT,
      expires_at   TEXT,   -- ISO 8601 UTC
      activated_at TEXT    -- ISO 8601 UTC
  )
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "payments.db"

_CREATE_PAID_SQL = """
CREATE TABLE IF NOT EXISTS paid_subscriptions (
    user_id        INTEGER PRIMARY KEY,
    city           TEXT    NOT NULL,
    service        TEXT    NOT NULL,
    plan           TEXT    NOT NULL,
    expires_at     TEXT    NOT NULL,
    activated_at   TEXT    NOT NULL,
    attempts_left  INTEGER NOT NULL DEFAULT 0
)
"""

_MIGRATE_ATTEMPTS_SQL = """
ALTER TABLE paid_subscriptions ADD COLUMN attempts_left INTEGER NOT NULL DEFAULT 0
"""

_CREATE_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS processed_events (
    event_id     TEXT    PRIMARY KEY,
    processed_at TEXT    NOT NULL
)
"""

_CREATE_PENDING_SQL = """
CREATE TABLE IF NOT EXISTS pending_payments (
    user_id           INTEGER PRIMARY KEY,
    city              TEXT    NOT NULL,
    service           TEXT    NOT NULL,
    plan              TEXT    NOT NULL,
    saved_at          TEXT    NOT NULL,
    stripe_session_id TEXT    NOT NULL DEFAULT ''
)
"""

_MIGRATE_SESSION_ID_SQL = """
ALTER TABLE pending_payments ADD COLUMN stripe_session_id TEXT NOT NULL DEFAULT ''
"""


# ── Connection helper ─────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(_CREATE_PAID_SQL)
    c.execute(_CREATE_EVENTS_SQL)
    c.execute(_CREATE_PENDING_SQL)
    # Non-breaking migrations: add columns if they don't exist yet
    try:
        c.execute(_MIGRATE_ATTEMPTS_SQL)
    except Exception:
        pass  # column already exists — ignore
    try:
        c.execute(_MIGRATE_SESSION_ID_SQL)
    except Exception:
        pass  # column already exists — ignore
    c.commit()
    return c


# ── Write ─────────────────────────────────────────────────────────────────────

def db_save(
    user_id:       int,
    city:          str,
    service:       str,
    plan:          str,
    expires_at:    datetime,
    activated_at:  datetime,
    attempts_left: int = 0,
) -> None:
    """Insert or replace a paid subscription record."""
    try:
        with _conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO paid_subscriptions
                    (user_id, city, service, plan, expires_at, activated_at, attempts_left)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    city,
                    service,
                    plan,
                    expires_at.isoformat(),
                    activated_at.isoformat(),
                    attempts_left,
                ),
            )
        logger.debug("DB_SAVE | user=%s plan=%s attempts=%d", user_id, plan, attempts_left)
    except Exception as exc:
        logger.error("DB_SAVE_FAILED | user=%s err=%s", user_id, exc)


def db_update_attempts_left(user_id: int, attempts_left: int) -> None:
    """Update remaining attempts for an active subscription."""
    try:
        with _conn() as c:
            c.execute(
                "UPDATE paid_subscriptions SET attempts_left = ? WHERE user_id = ?",
                (attempts_left, user_id),
            )
        logger.debug("DB_ATTEMPTS_UPDATE | user=%s attempts_left=%d", user_id, attempts_left)
    except Exception as exc:
        logger.error("DB_ATTEMPTS_UPDATE_FAILED | user=%s err=%s", user_id, exc)


# ── Read ──────────────────────────────────────────────────────────────────────

def db_load_record(user_id: int) -> dict | None:
    """Load a single record by user_id (None if not found)."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT city, service, plan, expires_at, activated_at, attempts_left "
                "FROM paid_subscriptions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "city":          row[0],
            "service":       row[1],
            "plan":          row[2],
            "expires_at":    datetime.fromisoformat(row[3]),
            "activated_at":  datetime.fromisoformat(row[4]),
            "attempts_left": row[5] if row[5] is not None else 0,
        }
    except Exception as exc:
        logger.error("DB_LOAD_FAILED | user=%s err=%s", user_id, exc)
        return None


def db_load_all_active() -> dict[int, dict]:
    """
    Load all subscriptions with attempts remaining.
    Called once at startup to warm the in-memory cache.
    """
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT user_id, city, service, plan, expires_at, activated_at, attempts_left "
                "FROM paid_subscriptions WHERE attempts_left > 0"
            ).fetchall()
        result = {}
        for row in rows:
            result[row[0]] = {
                "city":          row[1],
                "service":       row[2],
                "plan":          row[3],
                "expires_at":    datetime.fromisoformat(row[4]),
                "activated_at":  datetime.fromisoformat(row[5]),
                "attempts_left": row[6] if row[6] is not None else 0,
            }
        logger.info("DB_LOADED | active_subscriptions=%d", len(result))
        return result
    except Exception as exc:
        logger.error("DB_LOAD_ALL_FAILED | err=%s", exc)
        return {}


# ── Idempotency: processed Stripe events ──────────────────────────────────────

def is_event_processed(event_id: str) -> bool:
    """Return True if this Stripe event_id has already been handled."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT 1 FROM processed_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return row is not None
    except Exception as exc:
        logger.error("DB_EVENT_CHECK_FAILED | event_id=%s err=%s", event_id, exc)
        return False


def mark_event_processed(event_id: str) -> None:
    """Record that a Stripe event has been handled (idempotency guard)."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO processed_events (event_id, processed_at) VALUES (?, ?)",
                (event_id, datetime.utcnow().isoformat()),
            )
        logger.debug("DB_EVENT_MARKED | event_id=%s", event_id)
    except Exception as exc:
        logger.error("DB_EVENT_MARK_FAILED | event_id=%s err=%s", event_id, exc)


# ── Pending payments: preserve city/service/plan before Stripe opens ──────────

def db_save_pending(
    user_id: int,
    city: str,
    service: str,
    plan: str,
    stripe_session_id: str = "",
) -> None:
    """Save pre-payment state so it survives if user closes app before deeplink."""
    try:
        with _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO pending_payments "
                "(user_id, city, service, plan, saved_at, stripe_session_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, city, service, plan, datetime.utcnow().isoformat(), stripe_session_id),
            )
        logger.debug(
            "DB_PENDING_SAVE | user=%s city=%s svc=%s plan=%s session_id=%s",
            user_id, city, service, plan, stripe_session_id or "(none)",
        )
    except Exception as exc:
        logger.error("DB_PENDING_SAVE_FAILED | user=%s err=%s", user_id, exc)


def db_get_pending(user_id: int) -> dict | None:
    """Return the saved pre-payment state for a user (None if not found)."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT city, service, plan, stripe_session_id FROM pending_payments WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "city":              row[0],
            "svc":               row[1],
            "plan":              row[2],
            "stripe_session_id": row[3] or "",
        }
    except Exception as exc:
        logger.error("DB_PENDING_GET_FAILED | user=%s err=%s", user_id, exc)
        return None


def db_clear_pending(user_id: int) -> None:
    """Remove pending payment record after activation (cleanup)."""
    try:
        with _conn() as c:
            c.execute("DELETE FROM pending_payments WHERE user_id = ?", (user_id,))
    except Exception as exc:
        logger.error("DB_PENDING_CLEAR_FAILED | user=%s err=%s", user_id, exc)
