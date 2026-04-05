# -*- coding: utf-8 -*-
"""
Shim entrypoint — canonical run command: python bot.py

Keeps `python app.py` working for older deploy scripts while ensuring a single
Bot/Dispatcher implementation lives in bot.py (avoids duplicate HTTP/Stripe setup).
"""

from bot import main

if __name__ == "__main__":
    main()
