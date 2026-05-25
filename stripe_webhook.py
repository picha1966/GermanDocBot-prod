#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stripe_webhook.py — DEPRECATED AND DISABLED

╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██████╗ ███████╗██████╗ ██████╗ ███████╗ ██████╗ █████╗ ████████╗███████╗  ║
║   ██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝██╔══██╗╚══██╔══╝██╔════╝  ║
║   ██║  ██║█████╗  ██████╔╝██████╔╝█████╗  ██║     ███████║   ██║   █████╗    ║
║   ██║  ██║██╔══╝  ██╔═══╝ ██╔══██╗██╔══╝  ██║     ██╔══██║   ██║   ██╔══╝    ║
║   ██████╔╝███████╗██║     ██║  ██║███████╗╚██████╗██║  ██║   ██║   ███████╗  ║
║   ╚═════╝ ╚══════╝╚═╝     ╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝  ║
║                                                                              ║
║   THIS FILE IS PERMANENTLY DISABLED AND CANNOT BE RUN                        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

WHY THIS FILE EXISTS:
    This file was the original Stripe webhook handler but it does NOT deliver PDFs.
    It is kept for historical reference only.

CORRECT USAGE:
    1. Run: python bot.py
    2. Set Stripe webhook URL: https://termin-assist.de/stripe-webhook

THE ONLY VALID STRIPE WEBHOOK HANDLER IS IN: bot.py (port 4243)

Importing this module is safe (no exit). Running as __main__ still aborts with instructions.
"""

import sys

# ============================================================================
# HARD FAIL — THIS FILE CANNOT BE RUN
# ============================================================================

def _fatal_error():
    """Print fatal error and exit immediately."""
    print()
    print("=" * 78)
    print()
    print("  ❌❌❌  FATAL ERROR: stripe_webhook.py IS PERMANENTLY DISABLED  ❌❌❌")
    print()
    print("=" * 78)
    print()
    print("  This file CANNOT be run. It was deprecated because:")
    print("  - It does NOT deliver PDFs after payment")
    print("  - It conflicts with the correct webhook handler in bot.py")
    print("  - Running it causes payments to succeed but documents to NOT be sent")
    print()
    print("  ╔════════════════════════════════════════════════════════════════╗")
    print("  ║                                                                ║")
    print("  ║   CORRECT COMMAND:   python bot.py                             ║")
    print("  ║   CORRECT PORT:      4243                                      ║")
    print("  ║   PRODUCTION URL:    https://termin-assist.de                ║")
    print("  ║                                                                ║")
    print("  ╚════════════════════════════════════════════════════════════════╝")
    print()
    print("  The Stripe webhook handler is INSIDE bot.py at /stripe-webhook")
    print()
    print("=" * 78)
    print()
    sys.exit(1)


# Fail only when executed as a script — safe to import (e.g. tests, tooling).
if __name__ == "__main__":
    _fatal_error()