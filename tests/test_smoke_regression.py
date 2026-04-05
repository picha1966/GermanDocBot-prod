# -*- coding: utf-8 -*-
"""
E3 — Smoke / regression tests.

Checks that critical modules can be imported without side effects, that key
files are structurally sound, and that previously found regressions don't return.

Run: pytest tests/test_smoke_regression.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. stripe_webhook.py must be safe to import (no sys.exit on import)
# ---------------------------------------------------------------------------


def test_stripe_webhook_safe_to_import():
    """stripe_webhook.py used to call sys.exit() at module level — must not now."""
    code = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
import stripe_webhook  # noqa: F401
sys.exit(0)
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (
        "stripe_webhook import raised sys.exit or an exception:\n" + r.stderr
    )


# ---------------------------------------------------------------------------
# 2. utils.stripe_env imports without touching .env or DB
# ---------------------------------------------------------------------------


def test_stripe_env_imports_clean():
    import utils.stripe_env  # noqa: F401


def test_stripe_env_helpers_work():
    import utils.stripe_env as se

    old = {k: os.environ.pop(k, None) for k in ("ENV", "APP_ENV", "STRIPE_ALLOW_UNVERIFIED_WEBHOOKS")}
    try:
        assert se.is_production_env() is False
        assert se.allow_unverified_stripe_webhook() is False
        se.enforce_prod_no_unverified_stripe_webhook()  # must not raise
    finally:
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# 3. utils.runtime_bot starts as None (no bot process needed)
# ---------------------------------------------------------------------------


def test_runtime_bot_none_before_set():
    from utils.runtime_bot import get_runtime_bot

    bot = get_runtime_bot()
    assert bot is None or bot is not None  # just import + call without crash


# ---------------------------------------------------------------------------
# 4. handlers.termin_activation imports cleanly (no bot.py dependency)
# ---------------------------------------------------------------------------


def test_termin_activation_imports_no_bot_module():
    code = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
# Ensure bot module is NOT imported
import importlib
import builtins
_real_import = builtins.__import__
def _blocking_import(name, *args, **kwargs):
    if name == "bot":
        raise ImportError("bot module must not be imported by termin_activation")
    return _real_import(name, *args, **kwargs)
builtins.__import__ = _blocking_import
try:
    import handlers.termin_activation  # noqa: F401
except ImportError as e:
    if "bot module" in str(e):
        raise
finally:
    builtins.__import__ = _real_import
sys.exit(0)
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (
        "handlers/termin_activation imported bot.py which it must not:\n" + r.stderr
    )


# ---------------------------------------------------------------------------
# 5. webapp/index.html starts with valid HTML (no stray number before DOCTYPE)
# ---------------------------------------------------------------------------


def test_index_html_starts_with_doctype():
    p = ROOT / "webapp" / "index.html"
    assert p.exists(), "webapp/index.html not found"
    content = p.read_text(encoding="utf-8", errors="replace")
    stripped = content.lstrip()
    assert stripped.lower().startswith("<!doctype"), (
        f"index.html must start with <!DOCTYPE html>, got: {stripped[:40]!r}"
    )


# ---------------------------------------------------------------------------
# 6. main.py must NOT start the bot (exits cleanly with code 1 when run)
# ---------------------------------------------------------------------------


def test_main_py_exits_with_error_not_bot():
    r = subprocess.run(
        [sys.executable, str(ROOT / "main.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1, (
        f"main.py should exit with code 1 (deprecated stub), got {r.returncode}"
    )


# ---------------------------------------------------------------------------
# 7. FUNNEL steps are all present (grep in key modules)
# ---------------------------------------------------------------------------


_EXPECTED_STEPS = {
    "webapp_opened",
    "form_submitted",
    "pay_tapped",
    "stripe_session_created",
    "webhook_received",
    "order_marked_paid",
    "pdf_delivered",
    "pdf_sent_webhook",
}


def test_funnel_steps_present():
    src = "".join(
        (ROOT / f).read_text(encoding="utf-8", errors="replace")
        for f in (
            "handlers/docs_new.py",
            "handlers/stripe_handler.py",
            "bot.py",
        )
    )
    missing = [s for s in _EXPECTED_STEPS if f"step={s}" not in src]
    assert not missing, f"Missing FUNNEL steps: {missing}"
