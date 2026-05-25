# -*- coding: utf-8 -*-
"""Stripe webhook environment policy (importable without loading bot.py)."""

from __future__ import annotations

import os

_UNVERIFIED_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_production_env() -> bool:
    return (os.getenv("ENV") or os.getenv("APP_ENV") or "").strip().lower() == "production"


def allow_unverified_stripe_webhook() -> bool:
    return os.getenv("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS", "").strip().lower() in _UNVERIFIED_TRUTHY


def enforce_prod_no_unverified_stripe_webhook() -> None:
    """Fail fast if production is misconfigured with unverified webhook bypass."""
    if is_production_env() and allow_unverified_stripe_webhook():
        raise RuntimeError(
            "STRIPE_ALLOW_UNVERIFIED_WEBHOOKS is not allowed when ENV=production (or APP_ENV=production)"
        )


def enforce_stripe_webhook_secret() -> None:
    """
    Hard fail if STRIPE_WEBHOOK_SECRET is missing AND we are not in explicit dev-bypass mode.
    Called once at bot startup — prevents silent webhook forgery in production.
    """
    if not os.getenv("STRIPE_WEBHOOK_SECRET", "").strip():
        if not allow_unverified_stripe_webhook():
            raise RuntimeError(
                "STRIPE_WEBHOOK_SECRET is required. "
                "Set it in .env, or for local testing only: STRIPE_ALLOW_UNVERIFIED_WEBHOOKS=true"
            )


async def validate_stripe_api_key() -> None:
    """
    Verify the Stripe API key is valid by calling stripe.Account.retrieve().
    This is a free read-only call — no charge. Logs CRITICAL and raises on failure.
    Called once at bot startup so a misconfigured key is caught before first real payment.
    """
    import stripe as _stripe
    api_key = (
        os.getenv("STRIPE_API_KEY")
        or os.getenv("STRIPE_SECRET_KEY")
        or ""
    ).strip()
    if not api_key or api_key == "sk_test_placeholder":
        raise RuntimeError(
            "STRIPE_API_KEY (or STRIPE_SECRET_KEY) is not set or is a placeholder."
        )
    _stripe.api_key = api_key
    try:
        _stripe.Account.retrieve()
    except _stripe.error.AuthenticationError as exc:
        raise RuntimeError(f"Stripe API key is invalid: {exc}") from exc
    except Exception as exc:
        # Network errors etc. — warn but don't block startup
        import logging as _log
        _log.getLogger(__name__).warning(
            "STRIPE_KEY_CHECK: could not verify (network?): %s — continuing", exc
        )
