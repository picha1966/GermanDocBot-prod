"""
Spain appointment checker — pure async logic, no Telegram/Stripe/DB.

Supported portals:
  • consulado-es  — https://www.exteriores.gob.es/Consulados (Spanish consulates)
  • sede          — https://sede.administracionespublicas.gob.es (NIE / TIE)

Returns a list of slot dicts (same contract as the German checker):
    [{"date": "2025-04-20", "time": "10:30", "url": "https://...", "location": "..."}]
Returns [] if no slots found or on any error.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Portal entry-points ────────────────────────────────────────────────────────
# consulado: citaconsular.es is the current (post-2024) national booking system
#            for all Spanish consulates — city/office selection happens on-site.
# sede:      icp.administracionelectronica.gob.es — NIE/TIE/Residencia via
#            Extranjería; blocks simple HTTP (anti-bot) but loads with Playwright.
_CONSULADO_URL = "https://www.citaconsular.es/"
_SEDE_URL      = "https://icp.administracionelectronica.gob.es/icpplus/index.html"

_PORTAL_URLS: dict[str, dict[str, str]] = {
    "barcelona": {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "madrid":    {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "valencia":  {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "malaga":    {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "sevilla":   {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "alicante":  {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "murcia":    {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "zaragoza":  {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "bilbao":    {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
    "granada":   {"consulado": _CONSULADO_URL, "sede": _SEDE_URL},
}

# Authority aliases → portal key
_AUTHORITY_MAP: dict[str, str] = {
    "consulado":        "consulado",
    "extranjeria":      "sede",
    "nie":              "sede",
    "tie":              "sede",
    "nie_tie":          "sede",
    "residencia":       "sede",
    "buergeramt":       "sede",   # common alias from German side
    "sede":             "sede",
}


# ── Public API ─────────────────────────────────────────────────────────────────

async def check_spain_termin(
    city: str,
    authority: str,
) -> list[dict[str, Any]]:
    """Check Spain booking portals for available appointment slots.

    Args:
        city:      Normalised city name (barcelona / madrid / valencia / malaga).
        authority: Service type (consulado / nie / tie / extranjeria / sede …).

    Returns:
        List of slot dicts: [{"date", "time", "url", "location"}]
        Returns [] on any error — never raises.
    """
    city_key = city.lower().strip()
    auth_key = _AUTHORITY_MAP.get(authority.lower().strip(), "sede")

    urls = _PORTAL_URLS.get(city_key)
    if not urls:
        logger.warning("SPAIN_CHECK_UNKNOWN_CITY | city=%s", city_key)
        return []

    target_url = urls.get(auth_key, urls.get("sede", ""))
    if not target_url:
        logger.warning("SPAIN_CHECK_UNKNOWN_AUTHORITY | city=%s auth=%s", city_key, auth_key)
        return []

    logger.info("SPAIN_CHECK_START | city=%s authority=%s url=%s", city_key, auth_key, target_url)

    try:
        slots = await _scrape_with_playwright(target_url, city_key, auth_key)
    except Exception as exc:
        logger.error("SPAIN_ERROR | city=%s auth=%s err=%s", city_key, auth_key, exc)
        return []

    if slots:
        logger.info("SPAIN_FOUND | city=%s auth=%s count=%d first=%s", city_key, auth_key, len(slots), slots[0])
    else:
        logger.info("SPAIN_NO_SLOTS | city=%s auth=%s", city_key, auth_key)

    return slots


# ── Playwright scraper ─────────────────────────────────────────────────────────
# headless=False when DEBUG=True so you can watch the browser live during testing

_HEADLESS = os.getenv("DEBUG", "false").lower() not in ("1", "true", "yes")


async def _scrape_with_playwright(
    url: str,
    city: str,
    authority: str,
) -> list[dict[str, Any]]:
    """Open the booking portal with Playwright and extract available slots.

    Uses explicit start()/stop() instead of async-with to guarantee cleanup
    even when the parent asyncio Task is cancelled (avoids GeneratorExit errors).

    Steps:
      1. Open page — navigate to portal URL.
      2. Select city — dismiss cookies, wait for interactive state.
      3. Select service — wait for page to stabilise after interaction.
      4. Check slots — run extraction strategies.
    """
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout

    logger.info("STEP 0: START SCRAPER | city=%s auth=%s url=%s", city, authority, url)

    slots: list[dict[str, Any]] = []
    playwright = None
    browser    = None
    context    = None

    try:
        # ── Launch (explicit start/stop prevents GeneratorExit on cancellation) ──
        playwright = await async_playwright().start()
        logger.info("STEP 1: PLAYWRIGHT STARTED")

        _proxy_url = os.getenv("PROXY_URL", "").strip()
        _proxy = {"server": _proxy_url} if _proxy_url else None
        if _proxy:
            logger.info("USING PROXY: %s", _proxy_url)
        else:
            logger.info("NO PROXY — direct connection")

        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=_proxy,
        )
        logger.info("STEP 2: BROWSER LAUNCHED")

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-ES",
        )
        logger.info("STEP 3: CONTEXT CREATED")

        page = await context.new_page()
        logger.info("STEP 4: PAGE CREATED")

        # ── STEP 5/6: Open page ──────────────────────────────────────────────
        logger.info("STEP 5: BEFORE GOTO | url=%s", url)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            logger.info("STEP 6: AFTER GOTO | title=%s | url=%s", await page.title(), page.url)
            await page.screenshot(path=f"debug_{city}_{authority}.png")
            logger.info("STEP 7: SCREENSHOT DONE | debug_%s_%s.png", city, authority)
        except PWTimeout:
            logger.warning("STEP 5/6: Page load timeout | city=%s url=%s", city, url)
            return []

        # ── STEP 2: Select city — dismiss cookie banner, wait for page ──────
        logger.debug("STEP 2: Select city — dismissing cookie banner if present")
        for selector in [
            "button:has-text('Aceptar')",
            "button:has-text('Aceptar todo')",
            "button:has-text('Acepto')",
            "#aceptar",
            ".aceptar-cookies",
            "button:has-text('Aceptar todas')",
            "button:has-text('OK')",
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2_000):
                    await btn.click()
                    logger.debug("STEP 2: Cookie banner dismissed | selector=%s", selector)
                    break
            except PWTimeout:
                pass
            except Exception:
                pass

        await page.wait_for_timeout(1_500)
        logger.debug("STEP 2: Done — page is interactive | url=%s", page.url)

        # ── STEP 3: Select service — let dynamic content settle ───────────────
        logger.debug("STEP 3: Select service — waiting for dynamic content | city=%s", city)
        try:
            # Wait for any loading spinners / network activity to finish
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except PWTimeout:
            # networkidle can be flaky on SPA portals — continue anyway
            logger.debug("STEP 3: networkidle timeout (continuing) | city=%s", city)
        logger.debug("STEP 3: Done — dynamic content settled")

        # ── STEP 4: Check slots ───────────────────────────────────────────────
        logger.debug("STEP 4: Check slots | city=%s auth=%s", city, authority)
        slots = await _extract_slots(page, url, city, authority)
        logger.debug("STEP 4: Done | slots_found=%d", len(slots))

    except PWTimeout:
        logger.warning("SPAIN_TIMEOUT | city=%s auth=%s url=%s", city, authority, url)
    except Exception as exc:
        logger.error("CRITICAL SCRAPER ERROR: %s", exc, exc_info=True)
    finally:
        # Always clean up — order matters: context → browser → playwright
        if context:
            try:
                await context.close()
            except Exception as _e:
                logger.debug("SPAIN_CTX_CLOSE_ERR | %s", _e)
        if browser:
            try:
                await browser.close()
            except Exception as _e:
                logger.debug("SPAIN_BROWSER_CLOSE_ERR | %s", _e)
        if playwright:
            try:
                await playwright.stop()
            except Exception as _e:
                logger.debug("SPAIN_PW_STOP_ERR | %s", _e)

    return slots


async def _extract_slots(page: Any, url: str, city: str, authority: str) -> list[dict[str, Any]]:
    """Try multiple selector strategies to extract slot data from the page."""
    from playwright.async_api import TimeoutError as PWTimeout

    slots: list[dict[str, Any]] = []

    # ── Strategy A: calendar day cells with available class ──────────────────
    # Common pattern on sede.administracionelectronica.gob.es
    available_selectors = [
        "td.cita-disponible",
        "td.disponible",
        "td[class*='disponible']",
        "td[class*='available']",
        "div[class*='slot-available']",
        "a.diaCita",
        "td:not(.nodisponible):not(.festivo) > a",
    ]
    for sel in available_selectors:
        try:
            cells = await page.locator(sel).all()
            if not cells:
                continue
            for cell in cells[:5]:
                text = (await cell.inner_text()).strip()
                date_match = re.search(r"\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}", text)
                date_str = date_match.group(0) if date_match else text[:10]
                href = ""
                try:
                    href = (await cell.get_attribute("href")) or url
                except Exception:
                    href = url
                if date_str:
                    slots.append({
                        "date": date_str,
                        "time": "",
                        "url": href if href.startswith("http") else url,
                        "location": city.title(),
                    })
            if slots:
                logger.debug("SPAIN_SLOTS_VIA_CALENDAR | count=%d selector=%s", len(slots), sel)
                return slots
        except Exception:
            continue

    # ── Strategy B: time-slot dropdown / select ───────────────────────────────
    for sel in ["select[name*='hora']", "select[id*='hora']", "select[name*='time']"]:
        try:
            dropdown = page.locator(sel).first
            if not await dropdown.is_visible(timeout=1_500):
                continue
            options = await dropdown.locator("option").all()
            for opt in options[1:6]:  # skip first (placeholder)
                val = (await opt.get_attribute("value") or "").strip()
                txt = (await opt.inner_text()).strip()
                if val and val not in ("0", "-1", ""):
                    slots.append({
                        "date": "",
                        "time": txt or val,
                        "url": url,
                        "location": city.title(),
                    })
            if slots:
                logger.debug("SPAIN_SLOTS_VIA_DROPDOWN | count=%d", len(slots))
                return slots
        except Exception:
            continue

    # ── Strategy C: text scan for date/time patterns ─────────────────────────
    try:
        body_text = await page.inner_text("body")
        date_times = re.findall(
            r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\s+(\d{1,2}:\d{2})?",
            body_text,
        )
        for date_str, time_str in date_times[:3]:
            slots.append({
                "date": date_str,
                "time": time_str or "",
                "url": url,
                "location": city.title(),
            })
        if slots:
            logger.debug("SPAIN_SLOTS_VIA_TEXT_SCAN | count=%d", len(slots))
            return slots
    except Exception:
        pass

    # ── Strategy D: look for "no hay citas" / "no disponible" ────────────────
    # Positive proof that the portal explicitly says "no slots" — log and return [].
    try:
        body_lower = (await page.inner_text("body")).lower()
        no_slot_phrases = [
            "no hay citas disponibles",
            "no existen citas",
            "no disponible",
            "no hay plazas",
            "sin citas",
        ]
        if any(ph in body_lower for ph in no_slot_phrases):
            logger.info("SPAIN_CONFIRMED_NO_SLOTS | city=%s", city)
    except Exception:
        pass

    return []
