# -*- coding: utf-8 -*-
"""
DB Backup utility — safe SQLite online backup using sqlite3.Connection.backup().

Usage (one-off):
    python utils/db_backup.py

Usage (from Python):
    from utils.db_backup import run_backup
    run_backup()

Systemd timer setup: see supervisor/README.md for the .timer unit file.
"""

import os
import sqlite3
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — override via environment variables
# ---------------------------------------------------------------------------
_DB_PATH       = os.getenv("DB_PATH", "users.db")
_BACKUP_DIR    = os.getenv("DB_BACKUP_DIR", "backups/db")
_KEEP_DAYS     = int(os.getenv("DB_BACKUP_KEEP_DAYS", "14"))   # purge older than this
_BACKUP_PREFIX = "users_backup"


def run_backup(db_path: str = _DB_PATH, backup_dir: str = _BACKUP_DIR, keep_days: int = _KEEP_DAYS) -> str:
    """
    Create a hot backup of the SQLite database using the sqlite3 online backup API.
    This is safe to run while the database is being written — no locking required.

    Returns the path to the new backup file.
    """
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest_dir = Path(backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / f"{_BACKUP_PREFIX}_{ts}.db"

    src_conn = sqlite3.connect(db_path)
    try:
        dst_conn = sqlite3.connect(str(dest_path))
        try:
            src_conn.backup(dst_conn, pages=100)
            dst_conn.close()
        except Exception:
            dst_conn.close()
            if dest_path.exists():
                dest_path.unlink()
            raise
    finally:
        src_conn.close()

    logger.info("DB_BACKUP_OK: %s (%.1f KB)", dest_path, dest_path.stat().st_size / 1024)

    # ── Purge old backups ──────────────────────────────────────────────────
    _purge_old_backups(dest_dir, keep_days)

    return str(dest_path)


def _purge_old_backups(backup_dir: Path, keep_days: int) -> None:
    """Delete backup files older than `keep_days` days."""
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    purged = 0
    for f in backup_dir.glob(f"{_BACKUP_PREFIX}_*.db"):
        try:
            mtime = datetime.utcfromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                purged += 1
        except Exception as _e:
            logger.warning("DB_BACKUP_PURGE_ERROR: %s %s", f, _e)
    if purged:
        logger.info("DB_BACKUP_PURGED: %d file(s) older than %d days", purged, keep_days)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        path = run_backup()
        print(f"Backup created: {path}")
    except Exception as exc:
        print(f"Backup FAILED: {exc}")
        raise SystemExit(1)
