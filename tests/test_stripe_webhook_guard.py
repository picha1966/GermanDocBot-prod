# -*- coding: utf-8 -*-
"""
E1 — Stripe webhook policy smoke tests.

Run: pytest tests/test_stripe_webhook_guard.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_stripe_env_prod_plus_unverified_raises():
    import utils.stripe_env as stripe_env

    old_env = os.environ.get("ENV")
    old_uv = os.environ.get("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS")
    try:
        os.environ["ENV"] = "production"
        os.environ["STRIPE_ALLOW_UNVERIFIED_WEBHOOKS"] = "true"
        with pytest.raises(RuntimeError, match="STRIPE_ALLOW_UNVERIFIED"):
            stripe_env.enforce_prod_no_unverified_stripe_webhook()
    finally:
        if old_env is None:
            os.environ.pop("ENV", None)
        else:
            os.environ["ENV"] = old_env
        if old_uv is None:
            os.environ.pop("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS", None)
        else:
            os.environ["STRIPE_ALLOW_UNVERIFIED_WEBHOOKS"] = old_uv


def test_stripe_env_prod_without_unverified_ok():
    import utils.stripe_env as stripe_env

    old_env = os.environ.get("ENV")
    old_uv = os.environ.get("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS")
    try:
        os.environ["ENV"] = "production"
        os.environ.pop("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS", None)
        stripe_env.enforce_prod_no_unverified_stripe_webhook()
    finally:
        if old_env is None:
            os.environ.pop("ENV", None)
        else:
            os.environ["ENV"] = old_env
        if old_uv is None:
            os.environ.pop("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS", None)
        else:
            os.environ["STRIPE_ALLOW_UNVERIFIED_WEBHOOKS"] = old_uv


def test_bot_import_fails_when_prod_and_unverified_set():
    """Fresh interpreter: importing bot must raise RuntimeError."""
    code = f"""
import os, sys
os.environ["TELEGRAM_BOT_TOKEN"] = "1:test_token"
os.environ["ENV"] = "production"
os.environ["STRIPE_ALLOW_UNVERIFIED_WEBHOOKS"] = "true"
sys.path.insert(0, {str(ROOT)!r})
try:
    import bot  # noqa: F401
except RuntimeError as e:
    if "STRIPE_ALLOW_UNVERIFIED" in str(e):
        sys.exit(0)
    raise
sys.exit(2)
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_webhook_no_secret_returns_400(tmp_path):
    """No secret + no dev flag → 400 (logs fact; body not echoed)."""
    p = tmp_path / "run400.py"
    p.write_text(
        f'''import os, sys, asyncio
os.environ["TELEGRAM_BOT_TOKEN"] = "1:test_token"
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
os.environ.pop("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS", None)
os.environ.pop("ENV", None)
os.environ.pop("APP_ENV", None)
sys.path.insert(0, {str(ROOT)!r})
import bot

class _Req:
    remote = "127.0.0.1"
    headers = {{}}

    async def read(self):
        return b"{{}}"

async def main():
    resp = await bot._handle_stripe_webhook(_Req())
    if resp.status != 400:
        raise SystemExit(resp.status)
asyncio.run(main())
''',
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(p)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_webhook_with_secret_non_checkout_returns_200(tmp_path):
    """Verified signature path, ignored event type → 200."""
    p = tmp_path / "run200.py"
    p.write_text(
        f'''import os, sys, asyncio
from unittest.mock import MagicMock, patch
os.environ["TELEGRAM_BOT_TOKEN"] = "1:test_token"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
os.environ.pop("STRIPE_ALLOW_UNVERIFIED_WEBHOOKS", None)
sys.path.insert(0, {str(ROOT)!r})
import bot

class _Req:
    remote = "127.0.0.1"
    headers = {{"Stripe-Signature": "t=0,v1=ab"}}

    async def read(self):
        return b"{{}}"

async def main():
    evt = MagicMock()
    evt.type = "customer.updated"
    evt.data = MagicMock()
    with patch("stripe.Webhook.construct_event", return_value=evt):
        resp = await bot._handle_stripe_webhook(_Req())
    if resp.status != 200:
        raise SystemExit(resp.status)
asyncio.run(main())
''',
        encoding="utf-8",
    )
    r = subprocess.run(
        [sys.executable, str(p)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
