# -*- coding: utf-8 -*-
"""
utils/termin_redis.py — Optional Redis persistence for Termin flow state.

Activated by setting REDIS_URL env var (e.g. redis://localhost:6379/0).
If REDIS_URL is not set or connection fails, all operations silently
fall back to in-memory-only — zero behavior change.

Used by: handlers/termin.py, utils/termin_checker.py
"""
import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client = None
_init_done = False


def _ensure_client():
    """Lazy-init Redis connection. Returns client or None."""
    global _client, _init_done
    if _init_done:
        return _client
    _init_done = True

    url = os.getenv("REDIS_URL", "")
    if not url:
        logger.info("TERMIN_REDIS | REDIS_URL not set — in-memory only")
        return None

    try:
        import redis as _redis_lib
        _client = _redis_lib.Redis.from_url(
            url, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
        )
        _client.ping()
        logger.info("TERMIN_REDIS | Connected to Redis at %s", url.split("@")[-1])
    except ImportError:
        logger.warning("TERMIN_REDIS | redis package not installed — in-memory fallback")
        _client = None
    except Exception as exc:
        logger.warning("TERMIN_REDIS | Connection failed (%s) — in-memory fallback", exc)
        _client = None
    return _client


# ==================== Low-level ops (all silent on failure) ====================

def rget(key: str) -> Optional[str]:
    """Get a value from Redis. Returns None on miss or any error."""
    try:
        c = _ensure_client()
        return c.get(key) if c else None
    except Exception:
        return None


def rset(key: str, value: str, ttl: int = 0) -> bool:
    """Set a value in Redis with optional TTL (seconds). Returns False on error."""
    try:
        c = _ensure_client()
        if not c:
            return False
        if ttl > 0:
            c.setex(key, ttl, value)
        else:
            c.set(key, value)
        return True
    except Exception:
        return False


def rdel(key: str) -> bool:
    """Delete a key from Redis. Returns False on error."""
    try:
        c = _ensure_client()
        if not c:
            return False
        c.delete(key)
        return True
    except Exception:
        return False


def redis_available() -> bool:
    """Check if Redis is connected (for diagnostics only)."""
    try:
        c = _ensure_client()
        return c is not None
    except Exception:
        return False


# ==================== RedisBackedDict ====================

class RedisBackedDict(dict):
    """Dict with transparent write-through to Redis.

    - On write (__setitem__): stores in memory AND Redis (with optional TTL).
    - On read (get): checks memory first; on miss, hydrates from Redis.
    - On delete (pop/del): removes from memory AND Redis.
    - Any Redis failure is silently ignored — pure in-memory behavior preserved.
    """

    def __init__(self, prefix: str, ttl: int = 0):
        super().__init__()
        self._prefix = prefix
        self._ttl = ttl

    def _rkey(self, k) -> str:
        return f"{self._prefix}:{k}"

    def __setitem__(self, k, v):
        super().__setitem__(k, v)
        try:
            rset(self._rkey(k), json.dumps(v), self._ttl)
        except Exception:
            pass

    def get(self, k, default=None):
        # Fast path: in-memory hit
        v = super().get(k)
        if v is not None:
            return v
        # Slow path: hydrate from Redis on miss (e.g. after restart)
        try:
            raw = rget(self._rkey(k))
            if raw is not None:
                v = json.loads(raw)
                super().__setitem__(k, v)  # hydrate in-memory cache
                return v
        except Exception:
            pass
        return default

    def pop(self, k, *args):
        result = super().pop(k, *args)
        try:
            rdel(self._rkey(k))
        except Exception:
            pass
        return result

    def __delitem__(self, k):
        try:
            super().__delitem__(k)
        except KeyError:
            pass
        try:
            rdel(self._rkey(k))
        except Exception:
            pass

    def __contains__(self, k):
        if super().__contains__(k):
            return True
        try:
            return rget(self._rkey(k)) is not None
        except Exception:
            return False
