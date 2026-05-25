# -*- coding: utf-8 -*-
"""
Single place to resolve a Telegram user's delivery email.

Writes go to `termin_db.users.customer_email` (canonical) and optionally
`orders.customer_email` for compatibility; reads for delivery use this module only.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_user_email(telegram_id: int | str) -> str:
    """Return the stored email for this Telegram user (termin `users` row)."""
    try:
        from backend.termin_db import get_customer_email as _get

        return (_get(str(telegram_id)) or "").strip()
    except Exception as exc:
        logger.warning("get_user_email failed: user=%s err=%s", telegram_id, exc)
        return ""


def merge_stripe_email_into_user(
    telegram_user_id: int,
    order_id: int,
    stripe_email: Optional[str],
    *,
    db: Any = None,
) -> Optional[str]:
    """
    Persist Stripe session email to `users` + `orders`.

    If `users.customer_email` is already set and differs from the Stripe address,
    log EMAIL_CONFLICT and keep the existing value (do not overwrite).

    Returns the canonical email to use for this checkout, or None if stripe_email
    was empty/invalid.
    """
    new = normalize_email_address(stripe_email)
    if not new:
        return None
    if not is_valid_email_basic(new):
        logger.warning(
            "EMAIL_INVALID: order=%s user=%s raw=%r — not saving",
            order_id,
            telegram_user_id,
            stripe_email,
        )
        return None
    if db is None:
        from utils.helpers import get_db

        db = get_db()

    existing = get_user_email(telegram_user_id)
    if not existing:
        try:
            db.save_customer_email(order_id, new, overwrite=True)
        except Exception as exc:
            logger.warning("merge_stripe_email save_order: order=%s err=%s", order_id, exc)
        try:
            from backend.termin_db import create_user as _crt_t, update_user as _upd_t

            _crt_t(str(telegram_user_id))
            _upd_t(str(telegram_user_id), customer_email=new)
        except Exception as exc:
            logger.warning("merge_stripe_email update_user: order=%s err=%s", order_id, exc)
        logger.info(
            "CHECKOUT_EMAIL_SYNCED: order_id=%s user_id=%s",
            order_id,
            telegram_user_id,
        )
        return new

    if existing == new:
        try:
            db.save_customer_email(order_id, new, overwrite=False)
        except Exception as exc:
            logger.warning("merge_stripe_email same_addr save_order: %s", exc)
        return new

    logger.warning(
        "EMAIL_CONFLICT: user=%s order=%s existing=%s stripe_new=%s — keeping existing",
        telegram_user_id,
        order_id,
        existing,
        new,
    )
    try:
        db.save_customer_email(order_id, existing, overwrite=True)
    except Exception as exc:
        logger.warning("merge_stripe_email conflict save_order: order=%s err=%s", order_id, exc)
    return existing


def resolve_email_for_order(
    telegram_user_id: int,
    order_id: int,
    *,
    stripe_hint: Optional[str] = None,
    db: Any = None,
) -> Optional[str]:
    """
    Resolve email for PDF / delivery for this order.

    Priority:
      1) Stripe session hint (webhook, already parsed)
      2) `termin_db.users.customer_email`
      3) `user_data` JSON on the order (form / WebApp)
    """
    if stripe_hint:
        _h = normalize_email_address(stripe_hint)
        if _h:
            if is_valid_email_basic(_h):
                return _h
            logger.warning(
                "EMAIL_INVALID: order=%s stripe_hint=%r — skipping hint",
                order_id,
                stripe_hint,
            )

    u = get_user_email(telegram_user_id)
    if u:
        return u

    if db is None:
        from utils.helpers import get_db

        db = get_db()

    order = db.get_order(order_id)
    if not order:
        return None

    try:
        raw = order.get("user_data") or ""
        ud = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        if not isinstance(ud, dict):
            ud = {}
        em = normalize_email_address(ud.get("email") or "")
        if em:
            if is_valid_email_basic(em):
                logger.info(
                    "EMAIL_FOUND: source=user_data_json order=%s email=%s",
                    order_id,
                    em,
                )
                return em
            logger.warning(
                "EMAIL_INVALID: order=%s user_data email=%r — skipping",
                order_id,
                ud.get("email"),
            )
    except Exception as exc:
        logger.debug("resolve_email_for_order user_data parse: %s", exc)

    return None


def hydrate_email_from_order_user_data(
    order_id: int,
    telegram_user_id: int,
    *,
    db: Any = None,
) -> Optional[str]:
    """
    When the Stripe session has no email, persist address from WebApp `user_data`
    before PDF generation / email sending so `users.customer_email` is populated.
    """
    if db is None:
        from utils.helpers import get_db

        db = get_db()
    order = db.get_order(order_id)
    if not order:
        return None
    try:
        raw = order.get("user_data") or ""
        ud = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        if not isinstance(ud, dict):
            ud = {}
        em = normalize_email_address(ud.get("email") or "")
        if not em or "@" not in em:
            return None

        existing = get_user_email(telegram_user_id)
        if existing:
            if existing != em:
                logger.warning(
                    "EMAIL_CONFLICT: user=%s order=%s existing=%s form_new=%s — keeping existing",
                    telegram_user_id,
                    order_id,
                    existing,
                    em,
                )
            try:
                db.save_customer_email(order_id, existing, overwrite=True)
            except Exception as exc:
                logger.warning("hydrate save_customer_email: order=%s err=%s", order_id, exc)
            return existing

        try:
            db.save_customer_email(order_id, em, overwrite=False)
        except Exception as exc:
            logger.warning("hydrate save_customer_email: order=%s err=%s", order_id, exc)
        try:
            from backend.termin_db import create_user as _crt_t, update_user as _upd_t

            _crt_t(str(telegram_user_id))
            _upd_t(str(telegram_user_id), customer_email=em)
        except Exception as exc:
            logger.warning("hydrate update_user: order=%s err=%s", order_id, exc)
        logger.info(
            "EMAIL_HYDRATED_FROM_USER_DATA: order=%s user=%s",
            order_id,
            telegram_user_id,
        )
        return em
    except Exception as exc:
        logger.warning("hydrate_email_from_order_user_data: %s", exc)
        return None


def persist_resolved_email_if_missing_on_user(
    telegram_user_id: int,
    order_id: int,
    email: str,
    *,
    db: Any = None,
) -> None:
    """
    If termin `users.customer_email` is still empty but we resolved an address
    (e.g. from WebApp `user_data`), backfill users + order row.
    """
    _em = normalize_email_address(email)
    if not _em or not is_valid_email_basic(_em):
        if _em:
            logger.warning(
                "EMAIL_INVALID: order=%s user=%s raw=%r — persist skipped",
                order_id,
                telegram_user_id,
                email,
            )
        return
    if get_user_email(telegram_user_id):
        return
    if db is None:
        from utils.helpers import get_db

        db = get_db()
    try:
        db.save_customer_email(order_id, _em, overwrite=False)
    except Exception as exc:
        logger.warning("persist_resolved_email save_customer_email: %s", exc)
    try:
        from backend.termin_db import create_user as _crt_t, update_user as _upd_t

        _crt_t(str(telegram_user_id))
        _upd_t(str(telegram_user_id), customer_email=_em)
    except Exception as exc:
        logger.warning("persist_resolved_email update_user: %s", exc)
