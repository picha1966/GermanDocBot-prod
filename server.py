# -*- coding: utf-8 -*-
"""
server.py — Production ASGI entrypoint.

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8000

This is a thin re-export of the FastAPI app defined in webapp_server.py.
All routes, middleware and configuration live in webapp_server.py.
"""

from webapp_server import app  # noqa: F401

__all__ = ["app"]
