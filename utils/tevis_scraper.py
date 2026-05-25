# -*- coding: utf-8 -*-
"""
utils/tevis_scraper.py -- Real TeVIS slot scraping via Playwright.

Stateless HTTP GET of select2?md=N only reaches step 2 of the 6-step wizard.
The availability calendar (suggestion_form entries with date/start hidden inputs)
lives on step 4 (/suggest) and requires a live browser session to navigate there.

This module provides:
    get_tevis_slots(base_url, md, label) -> list[SlotInfo]

Concurrency safety:
    _BROWSER_SEMAPHORE limits simultaneous Chromium processes to MAX_CONCURRENT_BROWSERS.
    Each call acquires the semaphore before launching and releases it in finally.
    This prevents RAM exhaustion on low-memory VPS (4 GB) when many users monitor
    Playwright cities simultaneously.

Usage (standalone test):
    python -m utils.tevis_scraper
"""

import asyncio
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Concurrency limiter — prevents RAM exhaustion on 4 GB VPS
# ---------------------------------------------------------------------------

# Maximum number of Chromium browser processes allowed at any one moment.
# One headless Chromium uses ~150-200 MB RAM.
# Default: 2 for production safety on a 4 GB VPS (peak ~400 MB).
# Override via env: PLAYWRIGHT_MAX_CONCURRENCY=3
MAX_CONCURRENT_BROWSERS: int = int(os.getenv("PLAYWRIGHT_MAX_CONCURRENCY", "2"))
_BROWSER_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)

# Hard timeout for the entire browser session (all 4 TeVIS steps combined).
# Prevents a hung TeVIS portal from occupying a semaphore slot indefinitely.
# Individual page.goto() calls have _DEFAULT_TIMEOUT_MS (20 s) per step,
# so 4 steps × 20 s + buffer = 90 s is a safe outer bound.
_SESSION_TIMEOUT_SEC: int = int(os.getenv("PLAYWRIGHT_SESSION_TIMEOUT_SEC", "90"))


@dataclass
class SlotInfo:
    date: str           # "2026-03-15"
    time: str           # "09:30" or "" if not extracted
    location: str       # office / Büro name
    url: str            # booking URL to show the user (portal root or direct service page)
    raw_text: str = ""  # raw slot label from the page
    direct_url: str = ""  # direct service-step URL ({base}select2?md=N), skips homepage


def build_tevis_service_url(base_url: str, md: int) -> str:
    """Return the direct service-step URL for a TeVIS service.

    select2?md=N lands the user on the correct service page, bypassing the
    portal homepage. Works in a clean browser session (no prior session needed).
    """
    if md:
        return f"{base_url.rstrip('/')}/select2?md={md}"
    return base_url.rstrip("/") + "/"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT_MS = 20_000   # 20 s per page-load / navigation step
_CALENDAR_TIMEOUT_MS = 25_000  # calendar step can be slower


def _parse_date(raw: str) -> str:
    """Normalise dd.mm.yyyy or yyyy-mm-dd → yyyy-mm-dd."""
    raw = raw.strip()
    if re.match(r"\d{2}\.\d{2}\.\d{4}", raw):
        d, m, y = raw.split(".")
        return f"{y}-{m}-{d}"
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return raw


async def _dismiss_cookie_banner(page) -> None:
    """Click 'Akzeptieren' / 'Zustimmen' / 'OK' if a cookie banner appears."""
    for selector in (
        "button#cookie_msg_btn_yes",
        "button:has-text('Akzeptieren')",
        "button:has-text('Zustimmen')",
        "button:has-text('OK')",
        "input[value='OK']",
        "input[value='Akzeptieren']",
    ):
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=1_500):
                await btn.click()
                logger.debug("Cookie banner dismissed via %s", selector)
                return
        except Exception:
            continue


async def _get_step2_params(page) -> tuple[str, str, str]:
    """
    Extract the cnc-N input name, its ID, and the mdt hidden value from step 2.
    Returns (cnc_name, cnc_id, mdt)  e.g. ("cnc-5748", "5748", "312")

    Tries multiple selectors in order to handle TeVIS instance variations:
      1. input[type='number'][name^='cnc-']  — original EKOM21 format
      2. input[name^='cnc-']                 — any type (some instances use hidden)
      3. Regex scan of raw HTML for name="cnc-N" patterns
    """
    cnc_name, cnc_id, mdt = "", "", ""
    try:
        # Strategy 1: number inputs (original)
        cnc_inputs = await page.locator("input[type='number'][name^='cnc-']").all()
        if not cnc_inputs:
            # Strategy 2: any input type with cnc- name
            cnc_inputs = await page.locator("input[name^='cnc-']").all()
        if cnc_inputs:
            cnc_name = await cnc_inputs[0].get_attribute("name") or ""
            cnc_id = cnc_name.replace("cnc-", "")

        if not cnc_id:
            # Strategy 3: regex scan of raw HTML
            html2 = await page.content()
            _m = re.search(r'name="(cnc-(\d+))"', html2)
            if _m:
                cnc_name = _m.group(1)
                cnc_id = _m.group(2)
                logger.info("cnc_id resolved via HTML regex | cnc=%s", cnc_id)
            else:
                # Log a 500-char snippet to aid debugging future selector changes
                logger.warning(
                    "TEVIS_CNI_ID_NOT_FOUND | url=%s html_snippet=%r",
                    page.url,
                    html2[:500],
                )

        mdt_el = page.locator("input[name='mdt']").first
        if await mdt_el.count():
            mdt = await mdt_el.get_attribute("value") or ""
    except Exception as _e:
        logger.debug("TEVIS_STEP2_PARAMS_ERROR | url=%s err=%s", page.url, _e)
    return cnc_name, cnc_id, mdt


async def _navigate_to_location_page(page, base_url: str, md: int) -> bool:
    """
    Navigate directly to the location-selection page (step 3) using a GET
    request with the cnc service parameter extracted from step 2.

    TeVIS step 3 URL pattern:
        {base}location?cnc-{cnc_id}=1&mdt={mdt}&select_cnc=1

    This works stateless (no server-side session needed) because the GET
    parameters carry all necessary state.

    Returns True if step 3 loaded successfully.
    """
    try:
        _, cnc_id, mdt = await _get_step2_params(page)
        if not cnc_id:
            logger.warning(
                "TEVIS_STEP3_SKIP | city=%s — cnc_id not found on step 2, "
                "returning empty slots (no crash)",
                base_url,
            )
            return False

        location_url = (
            f"{base_url.rstrip('/')}/location"
            f"?cnc-{cnc_id}=1&mdt={mdt or '312'}&select_cnc=1"
        )
        logger.info("Navigating to step 3 location page: %s", location_url)
        await page.goto(location_url, wait_until="networkidle", timeout=_DEFAULT_TIMEOUT_MS)

        html3 = await page.content()
        if "Schritt 3" in html3 or "select_location" in html3:
            logger.info("Step 3 (location) loaded OK")
            return True
        logger.warning(
            "TEVIS_STEP3_UNEXPECTED | url=%s html_snippet=%r",
            page.url, html3[:300],
        )
        return False
    except Exception as e:
        logger.debug("Navigation to step 3 failed: %s", e)
        return False


async def _select_first_location(page) -> bool:
    """
    On step 3 (location selection), click the first 'Weiter mit N' submit
    button to advance to the calendar (step 4).

    TeVIS step 3 has separate <form> per office location, each with:
        <input type="hidden" name="loc" value="139">
        <input type="submit" name="select_location" value="Weiter mit 1">
    Clicking any "Weiter mit N" POSTs that form and loads step 4.
    """
    try:
        # Find first "Weiter mit N" submit button
        weiter_mit = page.locator("input[name='select_location'][value^='Weiter']").first
        if await weiter_mit.count():
            val = await weiter_mit.get_attribute("value") or ""
            logger.info("Clicking location button: %r", val)
            await weiter_mit.click(timeout=5_000)
            await page.wait_for_load_state("networkidle", timeout=_CALENDAR_TIMEOUT_MS)
            logger.debug("Clicked '%s' on step 3", val)
            return True

        # Fallback: old-style radio + Weiter
        radio = page.locator("input[type='radio'][name='ort']").first
        if await radio.is_visible(timeout=2_000):
            await radio.check()
            weiter = page.locator("input[type='submit'][value='Weiter']").first
            await weiter.click()
            await page.wait_for_load_state("networkidle", timeout=_CALENDAR_TIMEOUT_MS)
            return True

        logger.warning("No location selection button found on step 3")
        return False
    except Exception as e:
        logger.debug("Location selection failed: %s", e)
        return False


async def _extract_slots_from_calendar(page, booking_url: str, direct_url: str = "") -> list:
    """
    Parse the TeVIS suggest page (step 4 — "Terminvorschläge / Auswahl der Zeit").

    The suggest page contains one <form class="suggestion_form"> per available
    appointment slot.  Each form has:
        <input name="date"  value="YYYYMMDD">   — appointment date
        <input name="start" value="N">          — start time in minutes from midnight
        <input name="end"   value="N">          — end time in minutes from midnight

    The visible time label (e.g. "09:35 Uhr") is rendered from `start` value.

    Fallback: if suggestion_form is not present (older TeVIS variant), the code
    falls back to buchbar-class <td> parsing.
    """
    slots: list[SlotInfo] = []

    try:
        html = await page.content()
    except Exception:
        return slots

    step_m = re.search(r"Schritt (\d+) von", html)
    logger.info("Page step: %s  len=%d", step_m.group(0) if step_m else "?", len(html))

    # --- Strategy 1 (primary): suggestion_form entries ---
    # Each <form class="suggestion_form"> is one bookable slot.
    suggestion_forms = re.findall(
        r'<form[^>]+class="suggestion_form"[^>]*>(.*?)</form>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    logger.info("suggestion_form entries found: %d", len(suggestion_forms))

    for form_html in suggestion_forms:
        try:
            # Date: YYYYMMDD → yyyy-mm-dd
            date_m = re.search(r'name=["\']date["\'][^>]+value=["\'](\d{8})["\']', form_html)
            if not date_m:
                continue
            raw_date = date_m.group(1)
            date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

            # Time from "start" field (minutes since midnight)
            start_m = re.search(r'name=["\']start["\'][^>]+value=["\'](\d+)["\']', form_html)
            time_str = ""
            if start_m:
                mins = int(start_m.group(1))
                h_part, m_part = divmod(mins, 60)
                time_str = f"{h_part:02d}:{m_part:02d}"

            # Visible time text as raw_text
            time_text_m = re.search(r'(\d{2}:\d{2})\s*(?:Uhr)?', form_html)
            raw_text = time_text_m.group(0).strip() if time_text_m else time_str

            slots.append(SlotInfo(
                date=date,
                time=time_str,
                location="",
                url=direct_url or booking_url,
                raw_text=raw_text,
                direct_url=direct_url,
            ))
        except Exception as e:
            logger.debug("suggestion_form parse error: %s", e)
            continue

    # --- Strategy 2 (fallback): buchbar td cells ---
    if not slots:
        logger.info("No suggestion_forms — trying buchbar td fallback")
        buchbar_cells = await page.locator("td.buchbar, td[class*='buchbar']").all()
        logger.info("buchbar td cells found: %d", len(buchbar_cells))

        for cell in buchbar_cells:
            try:
                link = cell.locator("a").first
                date_raw = await link.get_attribute("data-date") or ""
                title = await link.get_attribute("title") or await link.inner_text() or ""
                date = _parse_date(date_raw) if date_raw else ""
                if not date:
                    dm = re.search(r"(\d{2}\.\d{2}\.\d{4})", title)
                    if dm:
                        date = _parse_date(dm.group(1))
                slots.append(SlotInfo(
                    date=date, time="", location="", url=direct_url or booking_url,
                    raw_text=title.strip(), direct_url=direct_url,
                ))
            except Exception:
                continue

    # --- Strategy 3 (fallback): data-count ---
    if not slots:
        data_count_cells = await page.locator("td[data-count]").all()
        for cell in data_count_cells:
            try:
                count = await cell.get_attribute("data-count") or "0"
                if int(count) > 0:
                    title = await cell.inner_text() or ""
                    dm = re.search(r"(\d{2}\.\d{2}\.\d{4})", title)
                    date = _parse_date(dm.group(1)) if dm else ""
                    slots.append(SlotInfo(
                        date=date, time="", location="", url=direct_url or booking_url,
                        raw_text=f"count={count} {title.strip()}", direct_url=direct_url,
                    ))
            except Exception:
                continue

    # --- Extract office/location name from infobox ---
    location_str = ""
    try:
        for sel in ("#infobox_content", ".infobox", "h1", "h2"):
            el = page.locator(sel).first
            if await el.count() and await el.is_visible(timeout=400):
                raw = (await el.inner_text(timeout=400)).strip()[:100]
                if raw and len(raw) > 3:
                    location_str = raw
                    break
    except Exception:
        pass

    for s in slots:
        if not s.location:
            s.location = location_str

    return slots


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_tevis_slots(
    base_url: str,
    md: int,
    *,
    label: str = "",
    headless: bool = True,
    slow_mo: int = 0,
) -> list:
    """
    Navigate the TeVIS EKOM21 or compatible wizard and return available slots.

    Parameters
    ----------
    base_url : str
        Root URL of the TeVIS instance, e.g.
        "https://tevis.ekom21.de/fra/" or "https://termine.duesseldorf.de/"
    md : int
        Service category ID passed to select2?md=N  (e.g. 13 for Frankfurt Bürgeramt)
    label : str
        Human-readable city label used in log messages (e.g. "frankfurt").
    headless : bool
        Run Chromium in headless mode (default True).
    slow_mo : int
        Milliseconds to slow down Playwright actions — useful for debugging.

    Returns
    -------
    list[SlotInfo]
        Available slots found on the calendar page.
        Empty list = no slots available or navigation failed.

    Concurrency
    -----------
    Acquires _BROWSER_SEMAPHORE before launching Chromium.
    At most MAX_CONCURRENT_BROWSERS (3) processes run simultaneously.
    Excess callers queue until a slot is free — never dropped.
    """
    from playwright.async_api import async_playwright

    city_label = label or base_url.split("/")[2]  # fallback: hostname
    booking_url = base_url.rstrip("/") + "/"
    step2_url = f"{booking_url}select2?md={md}"

    slots: list[SlotInfo] = []

    def _install_playwright_chromium() -> bool:
        """Run `playwright install chromium` and return True on success."""
        try:
            logger.info("PLAYWRIGHT_BROWSER_INSTALL_TRIGGERED | city=%s", city_label)
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                logger.info("PLAYWRIGHT_BROWSER_INSTALL_SUCCESS | city=%s", city_label)
                return True
            logger.error(
                "PLAYWRIGHT_BROWSER_INSTALL_FAILED | city=%s rc=%d stderr=%s",
                city_label, result.returncode, result.stderr[:500],
            )
            return False
        except Exception as _ie:
            logger.error("PLAYWRIGHT_BROWSER_INSTALL_FAILED | city=%s err=%s", city_label, _ie)
            return False

    async def _launch_browser(pw):
        """Launch Chromium, auto-installing it if the executable is missing."""
        try:
            return await pw.chromium.launch(headless=headless, slow_mo=slow_mo)
        except Exception as _le:
            if "Executable doesn't exist" in str(_le) or "executable doesn't exist" in str(_le):
                installed = await asyncio.get_event_loop().run_in_executor(
                    None, _install_playwright_chromium
                )
                if installed:
                    return await pw.chromium.launch(headless=headless, slow_mo=slow_mo)
            raise

    # Build the direct service-step URL (Priority B deep link for TeVIS)
    # This lands the user on the correct service page, bypassing the portal homepage.
    _direct_service_url = build_tevis_service_url(booking_url, md)

    async def _run_browser() -> list:
        """Inner coroutine — wrapped in wait_for() for hard timeout."""
        _slots: list[SlotInfo] = []
        async with async_playwright() as pw:
            browser = await _launch_browser(pw)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                locale="de-DE",
                extra_http_headers={"Accept-Language": "de-DE,de;q=0.9"},
            )
            page = await context.new_page()

            try:
                # ── Step 0: load root to initialise session ───────────────────
                logger.debug("PLAYWRIGHT_STEP0 | city=%s loading root", city_label)
                await page.goto(booking_url, wait_until="networkidle", timeout=_DEFAULT_TIMEOUT_MS)
                await _dismiss_cookie_banner(page)

                # ── Step 2: service selection page ────────────────────────────
                logger.debug("PLAYWRIGHT_STEP2 | city=%s md=%d", city_label, md)
                await page.goto(step2_url, wait_until="networkidle", timeout=_DEFAULT_TIMEOUT_MS)
                await _dismiss_cookie_banner(page)

                html2 = await page.content()
                step_m = re.search(r"Schritt (\d+) von", html2)
                logger.debug(
                    "PLAYWRIGHT_STEP2_OK | city=%s step=%s",
                    city_label, step_m.group(0) if step_m else "?",
                )

                # ── Step 2 → 3: navigate to location page via GET ─────────────
                advanced = await _navigate_to_location_page(page, booking_url, md)
                if not advanced:
                    logger.warning(
                        "PLAYWRIGHT_STEP3_FAIL | city=%s — could not load location page",
                        city_label,
                    )
                    return []

                # ── Step 3 → 4: click first location → calendar ───────────────
                advanced2 = await _select_first_location(page)
                if not advanced2:
                    logger.warning(
                        "PLAYWRIGHT_STEP4_FAIL | city=%s — could not advance to calendar",
                        city_label,
                    )
                    return []

                logger.debug(
                    "PLAYWRIGHT_STEP4_OK | city=%s url=%s", city_label, page.url,
                )

                # ── Step 4: extract available slots ───────────────────────────
                # Pass direct_url so each SlotInfo carries the service-step deep link.
                _slots = await _extract_slots_from_calendar(
                    page, booking_url, direct_url=_direct_service_url
                )
                logger.info(
                    "PLAYWRIGHT_DONE | city=%s found=%d slots direct_url=%s",
                    city_label, len(_slots), _direct_service_url,
                )

            except Exception as exc:
                logger.exception("PLAYWRIGHT_ERROR | city=%s error=%s", city_label, exc)
            finally:
                await context.close()
                await browser.close()
                logger.info("PLAYWRIGHT_CLOSE | city=%s", city_label)

        return _slots

    # ── Acquire concurrency slot ──────────────────────────────────────────────
    # Semaphore wraps the ENTIRE browser session (launch → scrape → close).
    # wait_for() enforces a hard 90 s outer timeout — prevents a hung TeVIS
    # portal from occupying a semaphore slot indefinitely.
    async with _BROWSER_SEMAPHORE:
        logger.info(
            "PLAYWRIGHT_START | city=%s md=%d concurrency=%d/%d",
            city_label, md,
            MAX_CONCURRENT_BROWSERS - _BROWSER_SEMAPHORE._value,  # type: ignore[attr-defined]
            MAX_CONCURRENT_BROWSERS,
        )
        try:
            slots = await asyncio.wait_for(_run_browser(), timeout=_SESSION_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            logger.error(
                "PLAYWRIGHT_TIMEOUT | city=%s — session exceeded %ds hard limit",
                city_label, _SESSION_TIMEOUT_SEC,
            )
            slots = []

    return slots


# ---------------------------------------------------------------------------
# Standalone test runner
# ---------------------------------------------------------------------------

async def _run_tests() -> None:
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    test_cases = [
        {
            "label": "Frankfurt -- Buergeramt (md=13)",
            "base_url": "https://tevis.ekom21.de/fra/",
            "md": 13,
        },
        {
            "label": "Duesseldorf -- Buergeramt (md=4)",
            "base_url": "https://termine.duesseldorf.de/",
            "md": 4,
        },
    ]

    for tc in test_cases:
        label = tc["label"]
        print("\n" + "="*60)
        print("TEST: " + label)
        print("      " + tc["base_url"] + "select2?md=" + str(tc["md"]))
        print("="*60)

        slots = await get_tevis_slots(
            tc["base_url"],
            tc["md"],
            headless=True,
        )

        if slots:
            print("\nOK  %d slot(s) found:\n" % len(slots))
            for i, s in enumerate(slots[:10], 1):
                print(
                    "  [%d] date=%s  time=%s  location=%s  raw=%s"
                    % (i, s.date or "?", s.time or "?",
                       (s.location[:40] if s.location else "?"),
                       s.raw_text[:50])
                )
        else:
            print("\nNO SLOTS found (calendar empty or navigation failed)")
            print("     -> This city can only be monitored as a liveness probe.")


if __name__ == "__main__":
    asyncio.run(_run_tests())
