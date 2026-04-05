"""Persistent counters for UX social proof display.

Counter is stored in termin_stats.json next to the bot root so it
survives restarts. Falls back to the baseline offset on first run.
Write operations are protected by a threading.Lock to prevent race
conditions when multiple slot-found callbacks fire concurrently.
"""

import json
import logging
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

_STATS_FILE = Path(__file__).parent.parent / "termin_stats.json"
_BASELINE = 2400  # pre-launch offset shown to first users
_stats_lock = Lock()


def get_termin_found() -> int:
    try:
        if _STATS_FILE.exists():
            return int(json.loads(_STATS_FILE.read_text(encoding="utf-8")).get("total", _BASELINE))
    except Exception as e:
        logger.debug("stats.get_termin_found read error: %s", e)
    return _BASELINE


def increment_termin_found() -> None:
    with _stats_lock:
        try:
            total = get_termin_found() + 1
            _STATS_FILE.write_text(json.dumps({"total": total}), encoding="utf-8")
        except Exception as e:
            logger.warning("stats.increment_termin_found write error: %s", e)
