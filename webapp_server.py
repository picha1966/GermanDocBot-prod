# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - WebApp Server (OPTIONAL — NOT FOR STRIPE!)

╔══════════════════════════════════════════════════════════════════════════════╗
║                           ⚠️  WARNING  ⚠️                                    ║
║                                                                              ║
║   THIS SERVER DOES NOT HANDLE STRIPE WEBHOOKS!                               ║
║   THIS SERVER DOES NOT DELIVER PDFs!                                         ║
║                                                                              ║
║   For Stripe payments to work, you MUST run:                                 ║
║       python bot.py                                                          ║
║                                                                              ║
║   Production: https://termin-assist.de                                     ║
║                                                                              ║
║   This webapp_server.py is ONLY for serving static WebApp files.             ║
║   It is OPTIONAL and usually NOT NEEDED.                                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Run with uvicorn:
    uvicorn webapp_server:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import sys
import logging

# ---------------------------------------------------------------------------
# FastAPI ASGI app — MUST be defined before any risky imports
# ---------------------------------------------------------------------------
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

app = FastAPI(
    title="GERMAN_DOC_BOT WebApp Server",
    description="Static WebApp file server. Does NOT handle Stripe webhooks.",
    version="5.0.0",
)

# ---------------------------------------------------------------------------
# Optional: httpx for proxying requests to bot (graceful if missing)
# Install: pip install httpx
# ---------------------------------------------------------------------------
try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    httpx = None  # type: ignore
    _HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Config (safe import — config.py sets ROOT_DIR etc.)
# ---------------------------------------------------------------------------
try:
    import config
    if config.ROOT_DIR not in sys.path:
        sys.path.insert(0, config.ROOT_DIR)
    WEBAPP_DIR = os.path.join(config.ROOT_DIR, 'webapp')
except Exception:
    WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webapp')

logger = logging.getLogger(__name__)

# URL бота для переадресації /webapp-submit (бот слухає на 4243)
BOT_WEBAPP_SUBMIT_URL = os.environ.get("BOT_WEBAPP_SUBMIT_URL", "http://127.0.0.1:4243/webapp-submit")


# ==================== Routes ====================

@app.get("/", response_class=HTMLResponse)
@app.get("/form", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
@app.get("/webapp/index.html", response_class=HTMLResponse)
@app.get("/webapp/form.html", response_class=HTMLResponse)
async def serve_webapp():
    """Serve WebApp HTML — пріоритет index.html"""
    for filename in ['index.html', 'form.html']:
        file_path = os.path.join(WEBAPP_DIR, filename)
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return HTMLResponse(content=content, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
    return HTMLResponse(content="Not Found", status_code=404)


@app.get("/webapp/{filename}")
async def serve_static(filename: str):
    """Serve static files"""
    file_path = os.path.join(WEBAPP_DIR, filename)

    if os.path.exists(file_path) and os.path.isfile(file_path):
        if filename.endswith('.css'):
            content_type = 'text/css'
        elif filename.endswith('.js'):
            content_type = 'application/javascript'
        elif filename.endswith('.html'):
            content_type = 'text/html'
        else:
            content_type = 'application/octet-stream'

        with open(file_path, 'rb') as f:
            content = f.read()
        return Response(content=content, media_type=content_type)

    return Response(content="Not Found", status_code=404)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "webapp", "stripe_handler": False}


@app.get("/api/form-schema")
async def api_form_schema(doc_type: str = "anmeldung", doc: str = "", lang: str = "de", v: str = ""):
    """GET /api/form-schema?doc_type=wohngeld&lang=de — returns form schema for doc_type."""
    from fastapi.responses import JSONResponse
    dtype = (doc_type or doc or "").strip() or "anmeldung"
    no_cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    try:
        from backend.forms import has_dynamic_form
        if has_dynamic_form(dtype):
            from backend.forms.frontend_adapter import build_frontend_schema
            return JSONResponse(content=build_frontend_schema(dtype, req_lang=lang or "de"), headers=no_cache_headers)

        from backend.document_config import get_document_form_schema
        schema = get_document_form_schema(dtype)
        return JSONResponse(content=schema if schema is not None else [], headers=no_cache_headers)
    except Exception:
        return JSONResponse(content=[], headers=no_cache_headers)


@app.post("/webapp-submit")
async def webapp_submit_proxy(request: Request):
    """POST /webapp-submit: переадресація на бота для відправки пост-форми меню.
    Для успішної відправки бот (python bot.py) має бути запущений на порту 4243."""
    if not _HAS_HTTPX:
        return JSONResponse(
            {"ok": False, "error": "httpx not installed. Run: pip install httpx"},
            status_code=500,
        )
    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                BOT_WEBAPP_SUBMIT_URL,
                content=body,
                headers={"Content-Type": "application/json"},
            )
            return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
    except Exception as e:
        err_msg = str(e)
        if "Connection refused" in err_msg or "Cannot connect" in err_msg:
            err_msg = "Bot unavailable. Start the bot: python bot.py (port 4243)"
        return JSONResponse({"ok": False, "error": err_msg}, status_code=502)


@app.post("/stripe-webhook")
async def stripe_webhook_guard():
    """
    GUARD: Block any Stripe webhooks that accidentally hit this server.
    Returns explicit error telling Stripe (and developers) to use the correct endpoint.
    """
    print()
    print("=" * 70)
    print("ERROR: Stripe webhook received on WRONG SERVER!")
    print("=" * 70)
    print("   This is webapp_server.py — it does NOT handle Stripe webhooks!")
    print()
    print("   CORRECT CONFIGURATION:")
    print("   1. Run: python bot.py (port 4243)")
    print("   2. Stripe Dashboard: https://termin-assist.de/stripe-webhook")
    print()
    print("   PDFs will NOT be delivered until you fix this!")
    print("=" * 70)
    print()

    return JSONResponse(
        {
            "error": "WRONG_SERVER",
            "message": "This is webapp_server.py - it does NOT handle Stripe webhooks!",
            "correct_server": "bot.py on port 4243",
            "action_required": "Update your Stripe webhook URL to point to bot.py (port 4243)",
        },
        status_code=421,
    )


# ==================== Stripe payment result pages ====================

@app.get("/form/payment-success", response_class=HTMLResponse)
async def payment_success(request: Request, order_id: str = "", lang: str = "en"):
    """After Stripe payment succeeds, send result to Telegram WebApp and close."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>
document.addEventListener("DOMContentLoaded", function() {{
    if (window.Telegram && Telegram.WebApp) {{
        Telegram.WebApp.sendData(JSON.stringify({{
            type: "payment_success",
            order_id: "{order_id}",
            lang: "{lang}"
        }}));
        setTimeout(function() {{ Telegram.WebApp.close(); }}, 500);
    }}
}});
</script>
</head><body>
<h3>&#10004; Payment successful</h3>
<p>You can close this window.</p>
</body></html>""")


@app.get("/form/payment-cancel", response_class=HTMLResponse)
async def payment_cancel(request: Request, order_id: str = "", lang: str = "en"):
    """After Stripe payment is cancelled, notify Telegram WebApp and close."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script>
document.addEventListener("DOMContentLoaded", function() {{
    if (window.Telegram && Telegram.WebApp) {{
        Telegram.WebApp.sendData(JSON.stringify({{
            type: "payment_cancel",
            order_id: "{order_id}",
            lang: "{lang}"
        }}));
        setTimeout(function() {{ Telegram.WebApp.close(); }}, 500);
    }}
}});
</script>
</head><body>
<h3>Payment cancelled</h3>
<p>You can close this window and try again.</p>
</body></html>""")


# ==================== Startup log ====================

@app.on_event("startup")
async def on_startup():
    logger.info("WebApp server started (static files only, no Stripe)")
    if not _HAS_HTTPX:
        logger.warning("httpx is NOT installed — /webapp-submit proxy will not work. Run: pip install httpx")


# ==================== Standalone run (fallback) ====================

if __name__ == '__main__':
    import uvicorn

    port = int(os.environ.get('WEBAPP_PORT', 8000))

    print()
    print("=" * 70)
    print("WebApp Server Starting")
    print("=" * 70)
    print()
    print("  WARNING: This server does NOT handle Stripe webhooks!")
    print("  WARNING: This server does NOT deliver PDFs!")
    print()
    print("  For Stripe payments to work, you MUST ALSO run:")
    print("    python bot.py   (Stripe webhook handler, port 4243)")
    print("  Stripe webhook: https://termin-assist.de/stripe-webhook")
    print()
    print(f"  This WebApp server: port {port} (static files only)")
    if not _HAS_HTTPX:
        print()
        print("  httpx not installed -- /webapp-submit proxy disabled")
        print("  Fix: pip install httpx")
    print()
    print("=" * 70)
    print()

    uvicorn.run("webapp_server:app", host="0.0.0.0", port=port, reload=True)
