# -*- coding: utf-8 -*-
"""
tools/e2e_test.py
═══════════════════════════════════════════════════════════════════════════════
Full end-to-end pipeline test (no real Stripe / Telegram network calls).

Steps executed:
  1. PREVIEW  — create_template_snippet_image()  →  PNG snippet
  2. PAYMENT  — simulated (order dict built in-memory)
  3. FINAL PDF — create_final_pdf()              →  real filled PDF
  4. TELEGRAM — verify PDF is readable (no bot token needed)
  5. EMAIL    — build full HTML + send via SMTP/provider if configured,
               otherwise write HTML to disk for visual inspection
  6. RESULTS  — summary table with PASS / FAIL per step

Run:
    python tools/e2e_test.py
    python tools/e2e_test.py --doc anmeldung --lang uk
    python tools/e2e_test.py --email you@example.com   (triggers real email send)
"""

import sys
import os
import argparse
import logging
import time
import json
from pathlib import Path

# ── ensure project root is on sys.path ───────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

# ── configure a detailed logger that shows every step ────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("e2e_test")

OUTPUT_DIR = ROOT / "outputs" / "e2e"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ═════════════════════════════════════════════════════════════════════════════
# Sample user data per doc_type
# ═════════════════════════════════════════════════════════════════════════════

_USER_DATA: dict = {
    "anmeldung": {
        # anmeldung strict builder requires Latin-only names + full ID document data
        "first_name": "Ivan",
        "last_name": "Petrenko",
        "birth_date": "1990-05-15",
        "birth_place": "Kyiv",
        "nationality": "ukrainisch",
        "street": "Hauptstrasse",
        "house_number": "12",
        "plz": "10115",
        "city": "Berlin",
        "move_in_date": "2026-01-15",
        "landlord_name": "Klaus Muller",
        "landlord_street": "Hauptstrasse",
        "landlord_house_number": "12",
        "landlord_plz": "10115",
        "landlord_city": "Berlin",
        "dokumentenart": "Reisepass",
        "seriennummer": "AB123456",
        "ausstellungsbehoerde": "Stadtamt Berlin",
        "ausstellungsdatum": "2020-01-01",
        "gueltig_bis": "2030-01-01",
        "weitere_wohnungen": "nein",
        "signature_date": "2026-03-28",
    },
    "abmeldung": {
        "first_name": "Ivan",
        "last_name": "Petrenko",
        "birth_date": "1990-05-15",
        "street": "Hauptstrasse",
        "house_number": "12",
        "plz": "10115",
        "city": "Berlin",
        "move_out_date": "2026-03-28",
        "new_street": "Bahnhofstrasse",
        "new_house_number": "5",
        "new_plz": "20095",
        "new_city": "Hamburg",
        "signature_date": "2026-03-28",
    },
    "wohnungsgeberbestaetigung": {
        "first_name": "Іван",
        "last_name": "Петренко",
        "birth_date": "1990-05-15",
        "street": "Hauptstraße",
        "house_number": "12",
        "plz": "10115",
        "city": "Berlin",
        "landlord_name": "Klaus Müller",
        "einzug_date": "2026-01-01",
        "signature_date": "2026-03-28",
    },
    "mietbescheinigung": {
        # composite address fields required by _REQUIRED_FIELDS
        "mb_vm_anschrift": "Klaus Müller, Hauptstraße 1, 10115 Berlin",
        "mb_m_anschrift": "Ivan Petrenko, Bergstraße 5, 10117 Berlin",
        "mb_anschrift": "Bergstraße 5, 10117 Berlin",
        "mb_mietbeginn": "01.01.2025",
        "first_name": "Ivan",
        "last_name": "Petrenko",
        "street": "Bergstrasse",
        "house_number": "5",
        "plz": "10117",
        "city": "Berlin",
        "signature_date": "2026-03-28",
    },
    "aufenthaltstitel": {
        "first_name": "Іван",
        "last_name": "Петренко",
        "birth_date": "1990-05-15",
        "birth_place": "Kyiv",
        "nationality": "ukrainisch",
        "street": "Hauptstraße",
        "house_number": "12",
        "plz": "10115",
        "city": "Berlin",
    },
    "beschaeftigungserklaerung": {
        "first_name": "Іван",
        "last_name": "Петренко",
        "birth_date": "1990-05-15",
        "nationality": "ukrainisch",
        "street": "Hauptstraße",
        "house_number": "12",
        "postal_code": "10115",
        "city": "Berlin",
        "be_firma": "Musterfirma GmbH",
        "be_strasse": "Industrieweg",
        "be_hausnummer": "99",
        "be_plz": "10179",
        "be_ort": "Berlin",
        "be_beschaeftigung": "Vollzeit",
        "be_berufsbezeichnung": "Softwareentwickler",
        "signature_date": "2026-03-28",
    },
}

# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⏭  SKIP"


def _section(title: str) -> None:
    width = 72
    log.info("")
    log.info("─" * width)
    log.info("  %s", title)
    log.info("─" * width)


def _result(label: str, ok: bool, detail: str = "") -> dict:
    status = PASS if ok else FAIL
    msg = f"{status}  {label}"
    if detail:
        msg += f"  [{detail}]"
    if ok:
        log.info(msg)
    else:
        log.error(msg)
    return {"label": label, "ok": ok, "detail": detail}


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 — Preview (template snippet)
# ═════════════════════════════════════════════════════════════════════════════

def step1_preview(doc_type: str, lang: str, user_data: dict) -> dict:
    _section(f"STEP 1 — Preview snippet  doc={doc_type}  lang={lang}")
    t0 = time.perf_counter()
    try:
        from backend.pdf_preview import create_template_snippet_image
        png_bytes = create_template_snippet_image(
            doc_type=doc_type,
            user_data=user_data,
            lang=lang,
        )
        elapsed = time.perf_counter() - t0
        if png_bytes and len(png_bytes) > 500:
            out = OUTPUT_DIR / f"{doc_type}_preview_snippet.png"
            out.write_bytes(png_bytes)
            return _result(
                "Preview PNG generated",
                True,
                f"{len(png_bytes):,} B  →  {out.name}  [{elapsed:.2f}s]",
            )
        else:
            # Template-based snippet unavailable — acceptable for builder-only docs
            log.warning("snippet=None (builder-only or no template) — fallback applies")
            return _result("Preview PNG", False, "returned None (no template / XFA)")
    except Exception as exc:
        log.exception("step1_preview EXCEPTION: %s", exc)
        return _result("Preview PNG", False, str(exc))


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2 — Simulate Stripe payment
# ═════════════════════════════════════════════════════════════════════════════

def step2_stripe_payment(doc_type: str, lang: str, customer_email: str) -> dict:
    _section("STEP 2 — Stripe payment (simulated)")
    log.info("  In production this step is triggered by Stripe webhook POST /stripe-webhook")
    log.info("  session.customer_details.email → %s", customer_email or "(none — email step will be skipped)")
    log.info("  Payment status: complete / paid  →  order marked PAID  →  delivery triggered")

    # Simulate the order that would be in the DB after payment
    fake_order = {
        "id": 99999,
        "user_id": 123456789,
        "doc_type": doc_type,
        "lang": lang,
        "status": "paid",
        "user_data": json.dumps(
            _USER_DATA.get(doc_type, _USER_DATA["anmeldung"])
        ),
        "stripe_session_id": "cs_test_e2e_simulation",
        "customer_email": customer_email,
    }
    log.info("  Fake order: %s", {k: v for k, v in fake_order.items() if k != "user_data"})
    return _result("Stripe payment simulated", True, f"order_id=99999  email={customer_email or 'none'}")


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3 — Final PDF generation
# ═════════════════════════════════════════════════════════════════════════════

def step3_final_pdf(doc_type: str, lang: str, user_data: dict) -> tuple[dict, str | None]:
    _section(f"STEP 3 — Final PDF generation  doc={doc_type}")
    t0 = time.perf_counter()
    pdf_path = None
    try:
        from backend.pdf_generator import create_final_pdf
        result = create_final_pdf(
            user_id=123456789,
            user_data=user_data,
            doc_type=doc_type,
            authority_info=None,
            user_lang=lang,
        )
        elapsed = time.perf_counter() - t0
        if isinstance(result, str) and os.path.exists(result):
            size = os.path.getsize(result)
            # copy to e2e output dir for inspection
            out = OUTPUT_DIR / f"{doc_type}_final.pdf"
            import shutil
            shutil.copy2(result, out)
            pdf_path = str(result)
            return (
                _result(
                    "Final PDF created",
                    True,
                    f"{size:,} B  →  {out.name}  [{elapsed:.2f}s]",
                ),
                pdf_path,
            )
        elif isinstance(result, dict):
            log.error("  create_final_pdf returned validation error dict: %s", result)
            return _result("Final PDF created", False, f"validation errors: {result}"), None
        else:
            log.error("  create_final_pdf returned unexpected: %s", type(result).__name__)
            return _result("Final PDF created", False, f"unexpected return type: {type(result).__name__}"), None
    except Exception as exc:
        log.exception("step3_final_pdf EXCEPTION: %s", exc)
        return _result("Final PDF created", False, str(exc)), None


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 — Telegram delivery (verify file is readable / sendable)
# ═════════════════════════════════════════════════════════════════════════════

def step4_telegram(doc_type: str, pdf_path: str | None) -> dict:
    _section("STEP 4 — Telegram delivery readiness")
    if not pdf_path:
        return _result("Telegram PDF readable", False, "no PDF path from step 3")
    try:
        size = os.path.getsize(pdf_path)
        with open(pdf_path, "rb") as f:
            header = f.read(5)
        is_pdf = header.startswith(b"%PDF-")
        log.info("  File: %s", pdf_path)
        log.info("  Size: %s B", f"{size:,}")
        log.info("  Header: %s  (valid PDF: %s)", header, is_pdf)
        log.info("  In production: bot.send_document(user_id=%s, file=open(pdf_path,'rb'))", 123456789)
        return _result(
            "Telegram PDF readable",
            is_pdf and size > 1000,
            f"{size:,} B  header={header!r}",
        )
    except Exception as exc:
        log.exception("step4_telegram EXCEPTION: %s", exc)
        return _result("Telegram PDF readable", False, str(exc))


# ═════════════════════════════════════════════════════════════════════════════
# STEP 5 — Email delivery
# ═════════════════════════════════════════════════════════════════════════════

def step5_email(doc_type: str, lang: str, pdf_path: str | None, customer_email: str) -> dict:
    _section("STEP 5 — Email delivery")

    if not pdf_path or not os.path.exists(pdf_path):
        return _result("Email delivery", False, "no PDF file available")

    # Always write the HTML to disk for visual inspection
    try:
        from utils.email_sender import (
            _build_html_email, _build_plain_email,
            _get_doc_label, _get_official_link, _get_support_link, _SUBJECT,
        )
        _lang = "uk" if lang in ("ua", "uk") else lang
        if _lang not in {"de", "en", "uk", "pl", "tr", "ar"}:
            _lang = "en"
        doc_label     = _get_doc_label(doc_type, _lang)
        official_link = _get_official_link(doc_type)
        support_href  = _get_support_link(doc_type)
        subject       = _SUBJECT.get(_lang, _SUBJECT["en"])
        html_body     = _build_html_email(_lang, doc_label, official_link, support_href)
        plain_body    = _build_plain_email(_lang, doc_label, official_link)

        html_out = OUTPUT_DIR / f"{doc_type}_email_{_lang}.html"
        html_out.write_text(html_body, encoding="utf-8")
        log.info("  Subject : %s", subject)
        log.info("  To      : %s", customer_email or "(none — real send skipped)")
        log.info("  Doc     : %s", doc_label)
        log.info("  Official: %s", official_link)
        log.info("  HTML    : %s B  →  %s", len(html_body), html_out.name)
        log.info("  Plain   : %s B", len(plain_body))
        log.info("  PDF     : %s_filled_sample.pdf  (%s B)", doc_type, f"{os.path.getsize(pdf_path):,}")
    except Exception as exc:
        log.exception("step5_email HTML build EXCEPTION: %s", exc)
        return _result("Email HTML build", False, str(exc))

    # Try real send if email provided and provider configured
    _provider = (
        "sendgrid" if os.environ.get("SENDGRID_API_KEY") else
        "resend"   if os.environ.get("RESEND_API_KEY")   else
        "smtp"     if os.environ.get("EMAIL_SMTP_HOST")   else
        None
    )
    log.info("  Provider: %s", _provider or "none — no env vars set")

    if customer_email and _provider:
        log.info("  Attempting REAL email send to %s via %s …", customer_email, _provider)
        try:
            import asyncio
            from utils.email_sender import send_pdf_by_email
            ok = asyncio.run(
                send_pdf_by_email(
                    to_email=customer_email,
                    pdf_path=pdf_path,
                    doc_type=doc_type,
                    lang=lang,
                )
            )
            return _result(
                f"Email sent via {_provider}",
                ok,
                f"to={customer_email}",
            )
        except Exception as exc:
            log.exception("step5 real send EXCEPTION: %s", exc)
            return _result("Email send", False, str(exc))

    if customer_email and not _provider:
        log.warning("  Email provider not configured — real send skipped")
        log.warning("  Set SENDGRID_API_KEY / RESEND_API_KEY / EMAIL_SMTP_HOST to enable")
        return _result(
            "Email HTML built (no provider configured)",
            True,
            f"preview → {html_out.name}",
        )

    return _result(
        "Email HTML built (no address — real send skipped)",
        True,
        f"preview → {html_out.name}",
    )


# ═════════════════════════════════════════════════════════════════════════════
# STEP 6 — Summary
# ═════════════════════════════════════════════════════════════════════════════

def step6_summary(results: list[dict], doc_type: str, lang: str, elapsed_total: float) -> None:
    _section("STEP 6 — Final results")
    passed = sum(1 for r in results if r["ok"])
    failed = sum(1 for r in results if not r["ok"])
    log.info("  doc_type : %s", doc_type)
    log.info("  lang     : %s", lang)
    log.info("  elapsed  : %.2f s", elapsed_total)
    log.info("")
    for r in results:
        status = PASS if r["ok"] else FAIL
        detail = f"  [{r['detail']}]" if r["detail"] else ""
        log.info("  %s  %s%s", status, r["label"], detail)
    log.info("")
    if failed == 0:
        log.info("  ══════════════════════════════")
        log.info("  ✅  ALL %d STEPS PASSED", passed)
        log.info("  ══════════════════════════════")
    else:
        log.info("  ══════════════════════════════")
        log.info("  🔴  %d/%d STEPS FAILED", failed, len(results))
        log.info("  ══════════════════════════════")
    log.info("")
    log.info("  Output files: %s", OUTPUT_DIR)


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="CivicAssistBot — end-to-end pipeline test")
    parser.add_argument("--doc",   default="anmeldung",
                        choices=list(_USER_DATA.keys()), help="Document type to test")
    parser.add_argument("--lang",  default="uk",
                        choices=["de", "en", "uk", "pl", "tr", "ar"], help="Language")
    parser.add_argument("--email", default="",
                        help="Customer email — triggers real email send if provider configured")
    args = parser.parse_args()

    doc_type  = args.doc
    lang      = args.lang
    customer_email = args.email.strip()
    user_data = _USER_DATA.get(doc_type, _USER_DATA["anmeldung"])

    t_start = time.perf_counter()

    log.info("══════════════════════════════════════════════════════════════════════")
    log.info("  CivicAssistBot — END-TO-END TEST")
    log.info("  doc=%s  lang=%s  email=%s", doc_type, lang, customer_email or "(none)")
    log.info("══════════════════════════════════════════════════════════════════════")

    results: list[dict] = []

    r1 = step1_preview(doc_type, lang, user_data)
    results.append(r1)

    r2 = step2_stripe_payment(doc_type, lang, customer_email)
    results.append(r2)

    r3, pdf_path = step3_final_pdf(doc_type, lang, user_data)
    results.append(r3)

    r4 = step4_telegram(doc_type, pdf_path)
    results.append(r4)

    r5 = step5_email(doc_type, lang, pdf_path, customer_email)
    results.append(r5)

    step6_summary(results, doc_type, lang, time.perf_counter() - t_start)


if __name__ == "__main__":
    main()
