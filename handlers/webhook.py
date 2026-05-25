# -*- coding: utf-8 -*-
"""
handlers/webhook.py — Stripe webhook infrastructure.

Architecture note:
    The full _handle_stripe_webhook implementation currently lives in bot.py
    for stability reasons (900 lines, critical payment path, no dedicated
    integration tests yet). This module provides:

    1. attach_to_app(app, bot, dp) — registers bot+dp in aiohttp app context
       so the webhook handler can access dp for FSM state management without
       a circular import.

    2. A future home for the extracted function once webhook integration tests
       are in place. Target structure:

        async def handle_stripe_webhook(request) -> web.Response:
            ...full implementation moved from bot.py...

    Migration checklist (when ready to extract):
    - [ ] Add tests/test_stripe_webhook_integration.py covering all metadata paths
    - [ ] Replace _handle_stripe_webhook in bot.py with:
          from handlers.webhook import handle_stripe_webhook as _handle_stripe_webhook
    - [ ] Remove attach_to_app import from bot.py (no longer needed separately)
"""

from aiohttp import web


def attach_to_app(app: web.Application, bot, dp) -> None:
    """
    Register bot and Dispatcher in the aiohttp application context.

    Called from on_startup() in bot.py. Makes both objects available to
    the webhook handler via `request.app["bot"]` and `request.app["dp"]`
    without circular imports.
    """
    app["bot"] = bot
    app["dp"] = dp
