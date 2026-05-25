# -*- coding: utf-8 -*-
"""Structured funnel events for log-based analytics (FUNNEL: lines)."""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_EMAIL_LIKE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", re.I)
_REDACT_KEYS = frozenset(
    {
        "email",
        "customer_email",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
    }
)


def _sanitize_funnel_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Strip obvious PII from structured log lines (email-like strings, sensitive keys)."""
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        lk = str(k).lower()
        if lk in _REDACT_KEYS or any(x in lk for x in ("password", "secret", "token", "email")):
            out[k] = "[redacted]"
            continue
        if isinstance(v, dict):
            out[k] = _sanitize_funnel_meta(v)
            continue
        if isinstance(v, str) and _EMAIL_LIKE.match(v.strip()):
            out[k] = "[redacted]"
            continue
        out[k] = v
    return out


def funnel_city_from_mapping(mapping: Optional[dict]) -> Optional[str]:
    """Best-effort city from WebApp answers / user_data dict."""
    if not mapping or not isinstance(mapping, dict):
        return None
    c = (
        mapping.get("city")
        or mapping.get("ort")
        or mapping.get("stadt")
        or mapping.get("new_city")
        or mapping.get("zuzugsort")
        or ""
    )
    s = str(c).strip()
    return s or None


def funnel_city_from_order(order: Optional[dict]) -> Optional[str]:
    """City from order.user_data JSON."""
    if not order:
        return None
    try:
        raw = order.get("user_data") or {}
        ud = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        return funnel_city_from_mapping(ud)
    except Exception:
        return None


def log_funnel(
    event: str,
    user_id: int,
    *,
    doc_type: Optional[str] = None,
    lang: Optional[str] = None,
    city: Optional[str] = None,
    **kwargs: Any,
) -> None:
    meta: dict[str, Any] = {}
    if doc_type is not None:
        meta["doc_type"] = doc_type
    if lang is not None:
        meta["lang"] = lang
    if city is not None and str(city).strip():
        meta["city"] = str(city).strip()
    meta.update(kwargs)
    meta = _sanitize_funnel_meta(meta)
    logger.info(f"FUNNEL: {event} | user={user_id} | {meta}")
