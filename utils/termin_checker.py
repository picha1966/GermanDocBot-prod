# -*- coding: utf-8 -*-
"""
utils/termin_checker.py — Termin availability polling + soft-lock reservation.

- Real API check via TERMIN_API_URL (falls back to stub if unset)
- In-memory per-user session state
- asyncio background loop (15s interval)
- Soft-lock reservation window (45s default)
- Safe cancellation via stop_polling() / cancel_reservation()
"""
import asyncio
import json
import logging
import os
import re
import time
from enum import Enum
from typing import Dict, Optional, Callable, Awaitable, Tuple

try:
    import httpx as _httpx_mod
    _HTTPX_LIMITS = _httpx_mod.Limits(max_connections=20, max_keepalive_connections=10)
    _HTTPX_TIMEOUT = _httpx_mod.Timeout(30.0, connect=10.0)
except ImportError:
    _HTTPX_LIMITS = None
    _HTTPX_TIMEOUT = None

# Limits concurrent outbound HTTP calls to prevent WinError 121 / semaphore exhaustion
_HTTP_SEMAPHORE = asyncio.Semaphore(10)

# Shared httpx client for simple single-GET city checks (connection reuse / lower latency).
# HTTP/2 fallback checks (Berlin, generic) still create per-request clients.
_SHARED_HTTPX_CLIENT = None


def _get_shared_client():
    """Lazily initialise and return a shared httpx.AsyncClient."""
    global _SHARED_HTTPX_CLIENT
    try:
        import httpx
        if _SHARED_HTTPX_CLIENT is None or _SHARED_HTTPX_CLIENT.is_closed:
            _SHARED_HTTPX_CLIENT = httpx.AsyncClient(
                limits=_HTTPX_LIMITS,
                timeout=_HTTPX_TIMEOUT,
                follow_redirects=True,
            )
    except Exception:
        pass
    return _SHARED_HTTPX_CLIENT


async def close_shared_httpx_client():
    """Close the shared client on bot shutdown to release connections."""
    global _SHARED_HTTPX_CLIENT
    if _SHARED_HTTPX_CLIENT is not None and not _SHARED_HTTPX_CLIENT.is_closed:
        await _SHARED_HTTPX_CLIENT.aclose()
        _SHARED_HTTPX_CLIENT = None


logger = logging.getLogger(__name__)


# ==================== Status Enum ====================
class TerminStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    RESERVED = "RESERVED"
    FINALIZED = "FINALIZED"
    PAUSED_AFTER_FOUND = "PAUSED_AFTER_FOUND"  # slot notified, waiting for user to resume


# ==================== Demand & Pricing Model ====================

class DemandLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# City code → demand level (static heuristic)
_CITY_DEMAND_MAP: Dict[str, DemandLevel] = {
    "berlin": DemandLevel.HIGH,
    "muenchen": DemandLevel.HIGH,
    "munich": DemandLevel.HIGH,
    "münchen": DemandLevel.HIGH,
    # Hamburg removed from Premium cities
    "koeln": DemandLevel.MEDIUM,
    "cologne": DemandLevel.MEDIUM,
    "frankfurt": DemandLevel.MEDIUM,
    "duesseldorf": DemandLevel.MEDIUM,
    "dusseldorf": DemandLevel.MEDIUM,
    "düsseldorf": DemandLevel.MEDIUM,
    "dortmund": DemandLevel.MEDIUM,
    "stuttgart": DemandLevel.MEDIUM,
}

# Base price per demand level (EUR) — demand-based pricing
_BASE_PRICES: Dict[DemandLevel, float] = {
    DemandLevel.LOW: 3.99,
    DemandLevel.MEDIUM: 5.99,
    DemandLevel.HIGH: 7.99,
}


def get_demand_level(city: str) -> DemandLevel:
    """Resolve demand level for a city code. Unknown cities default to LOW."""
    return _CITY_DEMAND_MAP.get(city.lower().strip(), DemandLevel.LOW)


def get_termin_price(city: str, authority: str = "") -> float:
    """
    Calculate Termin price based on city demand.
    Authority param accepted for future per-service pricing; currently unused.
    Returns price in EUR as float.
    """
    level = get_demand_level(city)
    return _BASE_PRICES[level]


# ==================== Berlin Real Scraper ====================

# Maps authority codes used in the bot to Berlin service portal URLs.
# Each value is the direct availability-check URL for that service.
_BERLIN_SERVICE_URLS: Dict[str, str] = {
    # Ausländerbehörde — all services (Aufenthaltstitel, Niederlassungserlaubnis, etc.)
    "auslaenderbehoerde":   "https://service.berlin.de/terminvereinbarung/termin/all/324/",
    "aufenthaltstitel":     "https://service.berlin.de/terminvereinbarung/termin/all/324/",
    "niederlassungserlaubnis": "https://service.berlin.de/terminvereinbarung/termin/all/324/",
    # Bürgeramt — Anmeldung / Ummeldung
    "anmeldung":            "https://service.berlin.de/terminvereinbarung/termin/all/120686/?termin=1",
    "buergeramt":           "https://service.berlin.de/terminvereinbarung/termin/all/120686/?termin=1",
    "ummeldung":            "https://service.berlin.de/terminvereinbarung/termin/all/120686/?termin=1",
    "abmeldung":            "https://service.berlin.de/terminvereinbarung/termin/all/121598/?termin=1",
    # Documents
    "personalausweis":      "https://service.berlin.de/terminvereinbarung/termin/all/121151/?termin=1",
    "reisepass":            "https://service.berlin.de/terminvereinbarung/termin/all/121921/?termin=1",
    "fuehrerschein":        "https://service.berlin.de/terminvereinbarung/termin/all/121598/?termin=1",
    # Kindergeld / Jobcenter — Familienkasse (not Berlin portal)
    "kindergeld":           "https://service.berlin.de/terminvereinbarung/termin/all/324462/?termin=1",
    "buergergeld":          "https://service.berlin.de/terminvereinbarung/termin/all/324462/?termin=1",
}

_BERLIN_BASE_URL = "https://service.berlin.de/terminvereinbarung/"

# Frankfurt (TeVIS)
# md=13 = Bürgerbüro (Anmeldung, Ummeldung, Personalausweis, Reisepass — confirmed live 2026-02-18)
# md=5  = Ausländerbehörde (residence permits — confirmed)
# md=6  = Fahrerlaubnisbehörde (Führerschein — confirmed live 2026-02-18)
_FRANKFURT_SERVICE_URLS: Dict[str, str] = {
    # Bürgeramt / Anmeldung / ID documents — all handled by Bürgerbüro (md=13)
    "anmeldung":             "https://tevis.ekom21.de/fra/",
    "buergeramt":            "https://tevis.ekom21.de/fra/",
    "ummeldung":             "https://tevis.ekom21.de/fra/",
    "abmeldung":             "https://tevis.ekom21.de/fra/",
    "personalausweis":       "https://tevis.ekom21.de/fra/",
    "reisepass":             "https://tevis.ekom21.de/fra/",
    # Ausländerbehörde / residence permits
    "auslaenderbehoerde":    "https://tevis.ekom21.de/fra/",
    "aufenthaltstitel":      "https://tevis.ekom21.de/fra/",
    "niederlassungserlaubnis": "https://tevis.ekom21.de/fra/",
    # Fahrerlaubnisbehörde (Führerschein)
    "fuehrerschein":         "https://tevis.ekom21.de/fra/",
}

# Köln — termine.stadt-koeln.de (Timify-based REST calendar system)
#
# Architecture (confirmed 2026-03-01 via live probe of stadt-koeln.de):
#   www.stadt-koeln.de/service/kontakt/terminvereinbarung-online
#     → embeds an iframe: koelngis.stadt-koeln.de/koelngis/portale/terminvergabe/index.html
#     → links to REST calendars at termine.stadt-koeln.de/m/<office>/extern/calendar/?uid=<UID>
#   The booking system is Timify (SaaS calendar platform), NOT TeVIS.
#   NOTE: tevis.krzn.de/tevisweb190 is the KRZN Kreis-Wesel instance (Xanten, Sonsbeck, etc.)
#         — it serves municipalities in Kreis Wesel (NRW), NOT Köln city.
#
# DEPLOYMENT NOTE — geo-firewall:
#   termine.stadt-koeln.de (194.8.223.109) and koelngis.stadt-koeln.de are geo-firewalled:
#   TCP connections are refused/time out from non-German IP space (confirmed 2026-03-01).
#   The bot MUST run on a DE server for Köln monitoring to function.
#   KOELN_GEO_BLOCKED warning log makes this immediately visible to operators.
#
# Calendar UIDs (confirmed from terminvereinbarung-online page, 2026-03-01):
#   Kundenzentren (Bürgeramt / Anmeldung / Personalausweis / Reisepass):
#     uid=b5a5a394-ec33-4130-9af3-490f99517071
#     uid=6cfd65c8-3caf-43a4-9efd-b4c5100eaab6
#     uid=e21cb479-b362-4475-8aad-0e2a9b5ebd9c
#   Ausländeramt (Aufenthaltstitel / Niederlassungserlaubnis):
#     uid=f3737466-3187-492f-8d7e-6082d47aeb84
#     uid=a1b62fe2-4455-4fc8-bc5b-8ec5d13588ca
#     uid=9699e2a7-d410-45c6-90e0-f3b32b022fd9
#
# Checker strategy:
#   1. DNS pre-check — fast 5s connect timeout to detect geo-block before HTTP.
#   2. GET termine.stadt-koeln.de/m/<office>/extern/calendar/?uid=<UID>
#      The Timify calendar page shows available time slots in its HTML when they exist,
#      and renders a "Keine Termine verfügbar" message when fully booked.
#   3. Confirm presence of Timify calendar UID links for the relevant office type.

# Globally-reachable Köln appointment portal — embedded Timify UID links confirm
# the booking system is operational. No geo-blocking (www.stadt-koeln.de, not
# the Timify subdomain termine.stadt-koeln.de which is TCP-firewalled outside DE).
_KOELN_PORTAL_URL = "https://www.stadt-koeln.de/service/kontakt/terminvereinbarung-online"

# Canonical booking page shown to users when a slot is detected.
_KOELN_BOOKING_URL = _KOELN_PORTAL_URL

# Office path substrings embedded in Timify UID links on the portal page.
# Used to confirm that the relevant office section is present and has UID links.
_KOELN_OFFICE_PATHS: Dict[str, str] = {
    "buergeramt":              "kundenzentren",
    "anmeldung":               "kundenzentren",
    "ummeldung":               "kundenzentren",
    "abmeldung":               "kundenzentren",
    "personalausweis":         "kundenzentren",
    "reisepass":               "kundenzentren",
    "auslaenderbehoerde":      "auslaenderamt",
    "aufenthaltstitel":        "auslaenderamt",
    "niederlassungserlaubnis": "auslaenderamt",
}

# Backwards-compat alias used by check_city_slots routing (kept for safety)
_KOELN_SERVICE_URLS: Dict[str, str] = {}

# Köln — KRZN TeVIS (tevis.krzn.de/tevisweb190) — CONFIRMED 2026-03-03
#
# Architecture (confirmed via Playwright probe 2026-03-03):
#   tevis.krzn.de/tevisweb190 is a standard TeVIS EKOM21 instance serving
#   Köln Bürgerservice. It follows the identical 6-step wizard as Frankfurt
#   and Düsseldorf (select2?md=N → /location → /suggest).
#   296 real slots found (Bürgerservice md=1) — dates from 09.03.2026 onward.
#   No geo-blocking observed (globally reachable).
#
# Note: The old liveness probe (check_koeln_slots) used www.stadt-koeln.de
# (Timify-based, city official page). That endpoint is kept as fallback code
# but routing now goes through this Playwright-based checker for real slots.
_KOELN_KRZN_PLAYWRIGHT_BASE = "https://tevis.krzn.de/tevisweb190/"
_KOELN_KRZN_BOOKING_URL = "https://tevis.krzn.de/tevisweb190/"
_KOELN_KRZN_MD_MAP: Dict[str, int] = {
    "buergeramt":              1,
    "anmeldung":               1,
    "ummeldung":               1,
    "abmeldung":               1,
    "personalausweis":         1,
    "reisepass":               1,
    # Ausländerbehörde — md=2..5 returned no cnc form in probe; defaulting to md=1
    # which covers general Bürgerservice including residence-related matters.
    "auslaenderbehoerde":      1,
    "aufenthaltstitel":        1,
    "niederlassungserlaubnis": 1,
    "fuehrerschein":           1,
}

# Krefeld — KRZN TeVIS (tevis.krzn.de/tevisweb350) — CONFIRMED 2026-03-03
#
# Architecture: standard KRZN TeVIS instance (same provider as Köln tevisweb190).
# 32 real slots found (Bürgerservice md=10) — dates from 04.03.2026 onward.
# md=10 = Bürgerservice (confirmed: cnc form loads, suggest page returns slots).
# md=1  = no cnc form (empty service group for this instance).
# No geo-blocking, no CAPTCHA, globally reachable.
# City: Krefeld, NRW, population ~220K (4th largest city in NRW).
_KREFELD_PLAYWRIGHT_BASE = "https://tevis.krzn.de/tevisweb350/"
_KREFELD_BOOKING_URL = "https://tevis.krzn.de/tevisweb350/"
_KREFELD_MD_MAP: Dict[str, int] = {
    "buergeramt":              10,
    "anmeldung":               10,
    "ummeldung":               10,
    "abmeldung":               10,
    "personalausweis":         10,
    "reisepass":               10,
    "auslaenderbehoerde":      10,
    "aufenthaltstitel":        10,
    "niederlassungserlaubnis": 10,
    "fuehrerschein":           10,
}

# Düsseldorf (TeVIS — termine.duesseldorf.de) — CONFIRMED 2026-02-26
# md=4 = Einwohnerangelegenheiten (Bürgeramt / Anmeldung / Ummeldung / Personalausweis / Reisepass)
#   Verified live: md=4 page shows "Personalausweis - Antrag" and "Reisepass" services.
# md=1 = Ausländerbehörde (residence permits)
# md=3 = Fahrerlaubnisbehörde (Führerschein) — confirmed 2026-02-18
_DUESSELDORF_SERVICE_URLS: Dict[str, str] = {
    # Bürgeramt / Einwohnerangelegenheiten — includes Personalausweis & Reisepass
    "anmeldung":               "https://termine.duesseldorf.de/",
    "buergeramt":              "https://termine.duesseldorf.de/",
    "ummeldung":               "https://termine.duesseldorf.de/",
    "abmeldung":               "https://termine.duesseldorf.de/",
    "personalausweis":         "https://termine.duesseldorf.de/",
    "reisepass":               "https://termine.duesseldorf.de/",
    # Ausländerbehörde / residence permits — CONFIRMED 2026-02-26
    "auslaenderbehoerde":      "https://termine.duesseldorf.de/",
    "aufenthaltstitel":        "https://termine.duesseldorf.de/",
    "niederlassungserlaubnis": "https://termine.duesseldorf.de/",
    # Fahrerlaubnisbehörde (Führerschein) — CONFIRMED 2026-02-18
    "fuehrerschein":           "https://termine.duesseldorf.de/",
}

# Dortmund — dortmund.termine-reservieren.de (TeVIS variant, confirmed 2026-03-03)
#
# Architecture (probed 2026-03-03 via live probe of dortmund.de):
#   www.dortmund.de/services/online-terminreservierung.html
#     links to dortmund.termine-reservieren.de (TeVIS-based booking system)
#
# Available md= values (confirmed live 2026-03-03):
#   md=3  — Einwohnermelde- und Kraftfahrzeugangelegenheiten
#           Covers: Anmeldung, Ummeldung, Abmeldung, Personalausweis, Reisepass,
#                   Aufenthaltstitel (eAT), KFZ-Angelegenheiten.
#           NOTE: Ausländerbehörde is NOT a separate office — Aufenthaltstitel
#                 is handled by the same Einwohnermeldewesen unit (md=3).
#   md=2  — Standesamt (civil registry: marriages, births, certificates)
#   md=9  — MigraDo (migration counselling — NOT an Ausländerbehörde)
#
# CHECKER STRATEGY — liveness probe:
#   The select2?md=3 page is a service-selection form (step 2 of 6).
#   Availability indicators (buchbar class, data-count, etc.) appear only at
#   step 4 (calendar). Navigating there requires form state (cookies + POST).
#   A stateless GET of select2?md=3 returning HTTP 200 is a reliable liveness
#   signal: the booking system is up and accepting appointment requests.
#   This is equivalent to the strategy used for Köln (www.stadt-koeln.de).
#
# Booking portal (shown to users):
_DORTMUND_PORTAL_URL = "https://dortmund.termine-reservieren.de/select2?md=3"
_DORTMUND_BOOKING_URL = "https://dortmund.termine-reservieren.de/"

# Service URLs used for the liveness GET request (all point to md=3 which
# handles all citizen-office services including Aufenthaltstitel).
_DORTMUND_SERVICE_URLS: Dict[str, str] = {
    "anmeldung":               _DORTMUND_PORTAL_URL,
    "buergeramt":              _DORTMUND_PORTAL_URL,
    "ummeldung":               _DORTMUND_PORTAL_URL,
    "abmeldung":               _DORTMUND_PORTAL_URL,
    "personalausweis":         _DORTMUND_PORTAL_URL,
    "reisepass":               _DORTMUND_PORTAL_URL,
    # Aufenthaltstitel is served by the same Einwohnermeldewesen unit (md=3)
    "auslaenderbehoerde":      _DORTMUND_PORTAL_URL,
    "aufenthaltstitel":        _DORTMUND_PORTAL_URL,
    "niederlassungserlaubnis": _DORTMUND_PORTAL_URL,
}


async def check_dortmund_slots(service_key: str) -> dict:
    """Dortmund liveness checker via dortmund.termine-reservieren.de.

    Uses a stateless GET of the select2?md=3 page (Einwohnermelde- und
    Kraftfahrzeugangelegenheiten — step 2 of 6).  HTTP 200 with the
    expected page title confirms the booking portal is operational.

    Returns available=True when the portal is reachable and returning a
    valid service-selection page.  liveness_only=True is set in the result
    to indicate that no exact slot date/time is extracted.
    """
    import httpx

    svc = (service_key or "buergeramt").lower().strip()
    url = _DORTMUND_SERVICE_URLS.get(svc)
    if not url:
        logger.debug("DORTMUND_CHECK_UNKNOWN_SERVICE | service=%s", svc)
        return {"available": False, "city": "dortmund"}

    logger.info("DORTMUND_CHECK_START | service=%s", svc)

    headers = {
        **_HEADERS,
        "Referer": "https://www.dortmund.de/",
    }
    try:
        import httpx
        client = _get_shared_client()
        async with _HTTP_SEMAPHORE:
            resp = await client.get(url, headers=headers)

        logger.info(
            "CITY_CHECK_EXECUTED | city=dortmund service=%s status=%s url=%s",
            svc, resp.status_code, url,
        )

        if resp.status_code != 200:
            logger.warning(
                "DORTMUND_HTTP_ERROR | service=%s status=%s",
                svc, resp.status_code,
            )
            return {"available": False, "city": "dortmund"}

        # Confirm it's the real TeVIS page, not an error or redirect
        page_ok = (
            "dortmund.termine-reservieren.de" in str(resp.url)
            and "Stadt Dortmund" in resp.text
        )

        if page_ok:
            logger.info(
                "DORTMUND_PORTAL_UP | service=%s — booking portal is operational",
                svc,
            )
            return {
                "available":     True,
                "city":          "dortmund",
                "location":      "Dortmund Stadtbüro",
                "date":          "",
                "time":          "",
                "url":           _DORTMUND_BOOKING_URL,
                "liveness_only": True,  # portal is UP; user must book manually
            }

        logger.info("DORTMUND_NOT_AVAILABLE | service=%s (portal page check failed)", svc)
        return {"available": False, "city": "dortmund"}

    except httpx.TimeoutException as exc:
        logger.warning("DORTMUND_TIMEOUT | service=%s error=%s", svc, exc)
        return {"available": False, "city": "dortmund"}
    except httpx.ConnectError as exc:
        logger.warning("DORTMUND_CONNECT_ERROR | service=%s error=%s", svc, exc)
        return {"available": False, "city": "dortmund"}
    except Exception as exc:
        logger.warning("DORTMUND_ERROR | service=%s error=%s", svc, exc)
        return {"available": False, "city": "dortmund"}


# Frankfurt TeVIS md= values by authority/service key.
# Used by the Playwright-based checker to navigate directly to the correct
# service-selection page without a stateful form POST.
_FRANKFURT_PLAYWRIGHT_BASE = "https://tevis.ekom21.de/fra/"
_FRANKFURT_BOOKING_URL = "https://tevis.ekom21.de/fra/"
_FRANKFURT_MD_MAP: Dict[str, int] = {
    "buergeramt":              13,
    "anmeldung":               13,
    "ummeldung":               13,
    "abmeldung":               13,
    "personalausweis":         13,
    "reisepass":               13,
    "auslaenderbehoerde":      5,
    "aufenthaltstitel":        5,
    "niederlassungserlaubnis": 5,
    "fuehrerschein":           6,
}

# Düsseldorf TeVIS md= values by authority/service key.
_DUESSELDORF_PLAYWRIGHT_BASE = "https://termine.duesseldorf.de/"
_DUESSELDORF_BOOKING_URL = "https://termine.duesseldorf.de/"
_DUESSELDORF_MD_MAP: Dict[str, int] = {
    "buergeramt":              4,
    "anmeldung":               4,
    "ummeldung":               4,
    "abmeldung":               4,
    "personalausweis":         4,
    "reisepass":               4,
    "auslaenderbehoerde":      1,
    "aufenthaltstitel":        1,
    "niederlassungserlaubnis": 1,
    "fuehrerschein":           3,
}

_CITY_SERVICE_URLS: Dict[str, Dict[str, str]] = {
    "berlin":      _BERLIN_SERVICE_URLS,
    # Frankfurt and Düsseldorf are routed to Playwright checkers in
    # check_termin_availability() BEFORE this lookup.
    # The entries below are kept only as a fallback liveness reference.
    "frankfurt":   _FRANKFURT_SERVICE_URLS,
    # Köln is NOT here — it uses check_koeln_slots() (Timify REST, termine.stadt-koeln.de).
    # Dortmund is NOT here — it uses check_dortmund_slots() (liveness probe).
    # Both are routed before this lookup in check_termin_availability().
    "duesseldorf": _DUESSELDORF_SERVICE_URLS,
    "dusseldorf":  _DUESSELDORF_SERVICE_URLS,
}
_SCRAPE_TIMEOUT = _HTTPX_TIMEOUT  # 30s total / 10s connect — DE gov sites can be slow

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Patterns in HTML that reliably indicate available slots.
#
# The Berlin portal sets class="buchbar" on calendar cells AND on legend/tooltip
# elements — so a bare buchbar match is not sufficient. A real bookable slot has
# a <td class="buchbar"> that contains an <a href="/terminvereinbarung/termin/time/...">
# child link leading to the time-selection page.
#
# Strategy: require BOTH signals within a short HTML window:
#   1. A <td> or <a> element with class containing "buchbar"
#   2. A href pointing to /termin/time/ or /termin/day/ with a booking token
#      (the portal adds ?termin=N or /date/ segments only for real slots)
#
# Removed (false-positive sources):
#   - terminvereinbarung/termin/day  — appears in nav/calendar even when fully booked
#   - "appointment"                  — JSON-LD / JS vars on all pages
#   - data-count="[1-9]"             — service count, not slot count
#   - <td class="buchbar"> alone     — also used for legend rows and disabled-but-styled cells
_AVAILABLE_PATTERNS = [
    # A <td class="buchbar ..."> that contains a booking link to /termin/time/ or /termin/tag/.
    # Window limited to 600 chars so DOTALL cannot bridge across the full document.
    # 600 chars is enough for <td>...<div>...<span>...<a href="...">...</td> nesting
    # but prevents the pattern from connecting a buchbar legend cell to a remote link.
    re.compile(
        r'<td\b[^>]*class=["\'][^"\']*\bbuchbar\b[^"\']*["\'][^>]*>.{0,600}?'
        r'href=["\'][^"\']*terminvereinbarung/termin/(?:time|tag)/[^"\']*["\']',
        re.IGNORECASE | re.DOTALL,
    ),
    # Fallback: an <a> tag that is itself buchbar and links to /termin/time/
    re.compile(
        r'<a\b[^>]*class=["\'][^"\']*\bbuchbar\b[^"\']*["\'][^>]*'
        r'href=["\'][^"\']*terminvereinbarung/termin/(?:time|tag)/[^"\']*["\']',
        re.IGNORECASE,
    ),
]

# Patterns that explicitly signal no slots are available.
# If any of these match, the page is treated as unavailable regardless of _AVAILABLE_PATTERNS.
_UNAVAILABLE_PATTERNS = [
    re.compile(r'keine\s+Termine?\s+(verf[uü]gbar|frei)', re.IGNORECASE),
    re.compile(r'aktuell\s+keine\s+Termine?', re.IGNORECASE),
    re.compile(r'derzeit\s+keine\s+Termine?\s+frei', re.IGNORECASE),
    re.compile(r'Es\s+sind\s+keine\s+freien\s+Termine?', re.IGNORECASE),
    re.compile(r'Leider\s+sind.*keine\s+Termine?', re.IGNORECASE),
]

# Patterns to extract date from response (dd.mm.yyyy or yyyy-mm-dd)
_DATE_PATTERN = re.compile(r'(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})')
# Time pattern hh:mm
_TIME_PATTERN = re.compile(r'\b(\d{1,2}:\d{2})\b')
# Location line near "Bürgeramt" or "Ausländerbehörde"
_LOCATION_PATTERN = re.compile(
    r'(B(?:ü|ue)rgeramt[^<]{0,60}|Ausländerbehörde[^<]{0,60})', re.IGNORECASE
)


async def check_berlin_slots(service: str) -> dict:
    """
    Real Berlin slot checker using httpx.

    Scrapes service.berlin.de for the given service type and detects
    whether bookable slots exist.

    Args:
        service: authority code (e.g. "anmeldung", "auslaenderbehoerde")

    Returns:
        {
            "available": True,
            "location": "Bürgeramt Mitte",
            "date": "2026-03-14",
            "time": "10:15",
            "url": "https://service.berlin.de/terminvereinbarung/"
        }
        or:
        {
            "available": False
        }
    """
    service_key = service.lower().strip()
    url = _BERLIN_SERVICE_URLS.get(service_key)

    if not url:
        # No URL mapping → cannot check → treat as not available
        logger.debug("Berlin check: no URL mapping for service=%s", service_key)
        return {"available": False}

    try:
        import httpx
        # Try HTTP/2 first — Berlin's Cloudflare CDN more often accepts H2 requests
        resp = None
        for http2 in (True, False):
            try:
                async with httpx.AsyncClient(
                    headers=_HEADERS,
                    timeout=_SCRAPE_TIMEOUT,
                    limits=_HTTPX_LIMITS,
                    follow_redirects=True,
                    http2=http2,
                ) as client:
                    async with _HTTP_SEMAPHORE:
                        resp = await client.get(url)
                if resp.status_code not in (403, 429):
                    break
            except Exception:
                if not http2:
                    raise

        logger.info(
            "Berlin check executed | service=%s status=%s url=%s",
            service_key, resp.status_code, url,
        )

        if resp.status_code != 200:
            logger.warning(
                "BERLIN_SCRAPE_HTTP_ERROR | service=%s status=%s",
                service_key, resp.status_code,
            )
            return {"available": False}

        html = resp.text

        # Explicit "no slots" text takes priority over any positive signal
        if any(pat.search(html) for pat in _UNAVAILABLE_PATTERNS):
            available = False
        else:
            _match = next((pat.search(html) for pat in _AVAILABLE_PATTERNS if pat.search(html)), None)
            # Guard: data-url="/dienstleistung//" marks today's highlight cell, not a real slot
            if _match and 'data-url="/dienstleistung//' in _match.group(0):
                _match = None
            available = _match is not None
            logger.info(
                "BERLIN_SLOT_SIGNAL | service=%s buchbar=%s time_link=%s",
                service_key, available, available,
            )
            if available:
                logger.info(
                    "BERLIN_BUCHBAR_MATCH | service=%s matched=%r",
                    service_key, _match.group(0)[:120],
                )

        if not available:
            return {"available": False}

        # --- Try to extract slot details from the HTML ---
        location = "Berlin"
        loc_match = _LOCATION_PATTERN.search(html)
        if loc_match:
            location = loc_match.group(1).strip().rstrip(",").strip()

        date = ""
        date_match = _DATE_PATTERN.search(html)
        if date_match:
            raw = date_match.group(1)
            # Normalise dd.mm.yyyy → yyyy-mm-dd
            if "." in raw:
                parts = raw.split(".")
                if len(parts) == 3:
                    date = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                date = raw

        time_str = ""
        time_match = _TIME_PATTERN.search(html)
        if time_match:
            time_str = time_match.group(1)

        # Return the service-specific entry URL so the notification button lands
        # directly on the correct service page instead of the generic portal root.
        service_url = _BERLIN_SERVICE_URLS.get(service_key, _BERLIN_BASE_URL)
        return {
            "available": True,
            "location": location,
            "date": date,
            "time": time_str,
            "url": service_url,
        }

    except Exception as exc:
        logger.warning("BERLIN_SCRAPE_ERROR | service=%s error=%s", service_key, exc)
        return {"available": False}


# München Bürgeransicht REST API — globally reachable (confirmed 2026-03-02)
#
# Architecture (probed 2026-03-02):
#   www56.muenchen.de / www46.muenchen.de — old KVR POST API.
#     Geo-TCP blocked outside Germany (ConnectTimeout). Removed.
#   www48.muenchen.de/buergeransicht/ — new SPA (Vue.js) backed by REST API.
#     /api/citizen/offices-and-services/ — captcha-free, 200 globally.
#       Returns list of offices with scope/availability metadata.
#     /api/citizen/available-days-by-office/ — requires captcha token
#       (400 captchaMissing). Not usable for automated monitoring.
#
# CHECKER STRATEGY — liveness probe via /offices-and-services/:
#   GET /offices-and-services/?serviceId=SERVICE_ID (captcha-free, globally reachable)
#   If ≥1 Bürgerbüro office returned → portal is UP and operational.
#   available=True signals portal is live; available=False signals portal is down.
#   Note: actual slot count is not visible without captcha.  The checker confirms
#   the booking system is reachable and functional, which is the correct signal
#   for health monitoring.
#
# SERVICE IDs (confirmed from /api/citizen/services, 2026-03-02):
#   1063475  Wohnsitzanmeldung
#   10224132 Wohnsitzanmeldung – Familie
#   1063453  Reisepass
#   1063441  Personalausweis
#   1063576  Meldebescheinigung

_MUENCHEN_API_BASE = "https://www48.muenchen.de/buergeransicht/api/citizen"
_MUENCHEN_BOOKING_URL = "https://www48.muenchen.de/buergeransicht/"

_MUENCHEN_SERVICE_IDS: Dict[str, int] = {
    "buergeramt":              1063475,
    "anmeldung":               1063475,
    "ummeldung":               1063475,
    "abmeldung":               1063475,
    "meldebescheinigung":      1063576,
    "personalausweis":         1063441,
    "reisepass":               1063453,
    "auslaenderbehoerde":      1063475,
    "aufenthaltstitel":        1063475,
    "niederlassungserlaubnis": 1063475,
}

_MUENCHEN_API_HEADERS = {
    **_HEADERS,
    "Accept":   "application/json, */*",
    "Origin":   "https://www48.muenchen.de",
    "Referer":  "https://www48.muenchen.de/buergeransicht/",
}


async def check_muenchen_slots(service: str) -> dict:
    """München liveness checker via Bürgeransicht REST API (www48.muenchen.de).

    Uses the captcha-free /offices-and-services/ endpoint which is globally
    reachable (no geo-blocking).  Returns available=True when the booking
    portal is operational (≥1 office returned for the service).

    Steps:
      1. Resolve service key to a München service ID.
      2. GET /api/citizen/offices-and-services/?serviceId=<id>
      3. Parse JSON — if offices list is non-empty → available=True (portal up).
      4. If request fails or list is empty → available=False.
    """
    import httpx

    service_key = (service or "buergeramt").lower().strip()
    service_id  = _MUENCHEN_SERVICE_IDS.get(service_key, 1063475)

    logger.info("MUENCHEN_CHECK_START | service=%s serviceId=%s", service_key, service_id)

    url = f"{_MUENCHEN_API_BASE}/offices-and-services/"
    params = {"serviceId": service_id}

    try:
        client = _get_shared_client()
        async with _HTTP_SEMAPHORE:
            resp = await client.get(url, params=params, headers=_MUENCHEN_API_HEADERS)

        logger.info(
            "CITY_CHECK_EXECUTED | city=muenchen status=%s url=%s",
            resp.status_code, url,
        )

        if resp.status_code != 200:
            logger.warning(
                "MUENCHEN_HTTP_ERROR | service=%s status=%s",
                service_key, resp.status_code,
            )
            return {"available": False, "city": "muenchen"}

        data = resp.json()
        offices = data.get("offices", [])

        # Bürgerbüro offices for this service
        buerger = [o for o in offices if "bürgerbüro" in o.get("name", "").lower()]

        if buerger:
            office_name = buerger[0].get("name", "München Bürgerbüro")
            logger.info(
                "MUENCHEN_PORTAL_UP | service=%s offices=%d first=%r",
                service_key, len(buerger), office_name,
            )
            return {
                "available":    True,
                "city":         "muenchen",
                "location":     office_name,
                "url":          _MUENCHEN_BOOKING_URL,
                "liveness_only": True,  # no exact slot — portal is UP, user must book manually
            }

        if offices:
            # Non-Bürgerbüro offices present (ABH etc.)
            logger.info(
                "MUENCHEN_PORTAL_UP | service=%s offices=%d (non-buergerbuero)",
                service_key, len(offices),
            )
            return {
                "available":    True,
                "city":         "muenchen",
                "location":     offices[0].get("name", "München"),
                "url":          _MUENCHEN_BOOKING_URL,
                "liveness_only": True,
            }

        logger.info("MUENCHEN_NO_OFFICES | service=%s (portal may be unavailable)", service_key)
        return {"available": False, "city": "muenchen"}

    except httpx.TimeoutException as exc:
        logger.warning("MUENCHEN_TIMEOUT | service=%s error=%s", service_key, exc)
        return {"available": False, "city": "muenchen"}
    except Exception as exc:
        logger.warning("MUENCHEN_ERROR | service=%s error=%s", service_key, exc)
        return {"available": False, "city": "muenchen"}


async def check_city_slots(city: str, service: str) -> dict:
    """Real checker for configured cities using official booking endpoints.

    Uses the same HTTP + pattern-detection architecture as Berlin.
    Returns the same dict format as check_berlin_slots().
    """
    city_key = (city or "").lower().strip()
    service_key = (service or "").lower().strip()
    city_map = _CITY_SERVICE_URLS.get(city_key, {})
    url = city_map.get(service_key)

    if not url:
        logger.debug(
            "CITY_CHECK_NO_URL | city=%s service=%s",
            city_key, service_key,
        )
        return {"available": False}

    try:
        import httpx
        resp = None
        for http2 in (True, False):
            try:
                async with httpx.AsyncClient(
                    headers=_HEADERS,
                    timeout=_SCRAPE_TIMEOUT,
                    limits=_HTTPX_LIMITS,
                    follow_redirects=True,
                    http2=http2,
                ) as client:
                    async with _HTTP_SEMAPHORE:
                        resp = await client.get(url)
                if resp.status_code not in (403, 429):
                    break
            except Exception:
                if not http2:
                    raise

        logger.info(
            "CITY_CHECK_EXECUTED | city=%s service=%s status=%s url=%s",
            city_key, service_key, resp.status_code, url,
        )

        if resp.status_code != 200:
            logger.warning(
                "CITY_SCRAPE_HTTP_ERROR | city=%s service=%s status=%s",
                city_key, service_key, resp.status_code,
            )
            return {"available": False}

        html = resp.text
        # Explicit "no slots" text takes priority over any positive signal
        if any(pat.search(html) for pat in _UNAVAILABLE_PATTERNS):
            available = False
        else:
            _match = next((pat.search(html) for pat in _AVAILABLE_PATTERNS if pat.search(html)), None)
            # Guard: data-url="/dienstleistung//" marks today's highlight cell, not a real slot
            if _match and 'data-url="/dienstleistung//' in _match.group(0):
                _match = None
            available = _match is not None
            logger.info(
                "BERLIN_SLOT_SIGNAL | city=%s service=%s buchbar=%s time_link=%s",
                city_key, service_key, available, available,
            )
            if available:
                logger.info(
                    "BERLIN_BUCHBAR_MATCH | city=%s service=%s matched=%r",
                    city_key, service_key, _match.group(0)[:120],
                )
        if not available:
            return {"available": False}

        location = city_key.title()
        loc_match = _LOCATION_PATTERN.search(html)
        if loc_match:
            location = loc_match.group(1).strip().rstrip(",").strip()

        date = ""
        date_match = _DATE_PATTERN.search(html)
        if date_match:
            raw = date_match.group(1)
            if "." in raw:
                parts = raw.split(".")
                if len(parts) == 3:
                    date = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                date = raw

        time_str = ""
        time_match = _TIME_PATTERN.search(html)
        if time_match:
            time_str = time_match.group(1)

        return {
            "available": True,
            "location": location,
            "date": date,
            "time": time_str,
            "url": url,
        }
    except Exception as exc:
        logger.warning(
            "CITY_SCRAPE_ERROR | city=%s service=%s error=%s",
            city_key, service_key, exc,
        )
        return {"available": False}


async def check_tevis_playwright_slots(
    base_url: str,
    md: int,
    booking_url: str,
    city_label: str = "",
) -> dict:
    """Real slot checker via Playwright for TeVIS cities (Frankfurt, Düsseldorf).

    Navigates the 4-step TeVIS wizard:
        root → select2?md=N (service) → /location (office) → /suggest (slots)

    The /suggest page contains one <form class="suggestion_form"> per available
    appointment slot with hidden inputs name="date" (YYYYMMDD) and name="start"
    (minutes since midnight).

    Falls back to {"available": False} if playwright is not installed,
    the browser launch fails, or the page is unreachable.

    Returns the same dict format as check_city_slots() / check_berlin_slots().
    """
    try:
        from utils.tevis_scraper import get_tevis_slots  # lazy import — optional dep
    except ImportError:
        logger.debug("TEVIS_PLAYWRIGHT_UNAVAILABLE | tevis_scraper not installed")
        return {"available": False}

    try:
        slots = await get_tevis_slots(base_url, md, label=city_label or "tevis", headless=True)
    except Exception as exc:
        logger.warning(
            "TEVIS_PLAYWRIGHT_ERROR | base=%s md=%d error=%s",
            base_url, md, exc,
        )
        return {"available": False}

    if not slots:
        logger.info(
            "TEVIS_PLAYWRIGHT_NO_SLOTS | city=%s base=%s md=%d",
            city_label or base_url, base_url, md,
        )
        return {"available": False}

    first = slots[0]
    # Use portal URL from SlotInfo; direct_url (select2?md=N) is internal only.
    resolved_url = first.url or booking_url
    _BAD_PATTERNS = ("select2", "ajax", "api")
    if resolved_url and any(x in resolved_url for x in _BAD_PATTERNS):
        resolved_url = booking_url
    logger.info(
        "TEVIS_PLAYWRIGHT_FOUND | city=%s date=%s time=%s location=%s total_slots=%d url=%s",
        city_label or base_url,
        first.date,
        first.time,
        (first.location or "")[:50],
        len(slots),
        resolved_url,
    )
    return {
        "available": True,
        "location": first.location or city_label,
        "date": first.date,
        "time": first.time,
        "url": resolved_url,
    }


async def check_frankfurt_playwright(service_key: str) -> dict:
    """Frankfurt Bürgeramt / Ausländerbehörde / Führerschein — Playwright scraper."""
    svc = (service_key or "buergeramt").lower().strip()
    md = _FRANKFURT_MD_MAP.get(svc, 13)
    logger.debug("FRANKFURT_PLAYWRIGHT_CHECK | service=%s md=%d", svc, md)
    return await check_tevis_playwright_slots(
        _FRANKFURT_PLAYWRIGHT_BASE,
        md,
        _FRANKFURT_BOOKING_URL,
        "Frankfurt",
    )


async def check_duesseldorf_playwright(service_key: str) -> dict:
    """Düsseldorf Bürgeramt / Ausländerbehörde / Führerschein — Playwright scraper."""
    svc = (service_key or "buergeramt").lower().strip()
    md = _DUESSELDORF_MD_MAP.get(svc, 4)
    logger.debug("DUESSELDORF_PLAYWRIGHT_CHECK | service=%s md=%d", svc, md)
    return await check_tevis_playwright_slots(
        _DUESSELDORF_PLAYWRIGHT_BASE,
        md,
        _DUESSELDORF_BOOKING_URL,
        "Duesseldorf",
    )


# Hamburg DTMS (Digitales Terminmanagement System) — driveport.de
#
# Architecture (confirmed 2026-03-01 via live probe):
#   serviceportal.hamburg.de/HamburgGateway/Service/Entry/DigiTermin
#     → HTTP 302 → https://driveport.de/termine/
#     → Blazor WebAssembly SPA (DTMSAzureWeb.wasm + DTMSTerminCommon.wasm)
#     → Backend uses Microsoft SignalR for real-time slot updates.
#     → SignalR hub: POST /terminHub/negotiate  (returns 200 + connection token)
#     → Hub streams slot availability events — no plain REST GET for slots.
#
# Probe strategy (zero browser automation required):
#   1. POST to the SignalR negotiate endpoint.  A 200 response means the hub is
#      reachable and the DTMS backend is live.  A non-200 means backend down.
#   2. GET the DTMS entry page and look for known availability text signals
#      ("Termin verfügbar", "freier Termin", "Buchung möglich") injected by the
#      server-side rendering layer on high-demand days.
#   3. If SignalR negotiation returns a connectionToken AND the entry HTML contains
#      any availability signal, report AVAILABLE.  Otherwise NOT_AVAILABLE.
#
# Limitation: without subscribing to the SignalR hub (which requires WebSocket +
# an ongoing async connection beyond a single HTTP request), we cannot get the
# actual slot count.  The negotiate check is a reliable liveness signal only.
# When the negotiate endpoint returns 200 AND text signals are present, it is
# safe to surface the official booking link so the user can check manually;
# this is better than permanently blocking Hamburg users from any notification.
#
# Service keys mapping to driveport.de (all districts share the same hub):
_HAMBURG_SERVICE_MAP: Dict[str, str] = {
    # Bürgeramt / Einwohnermeldeamt
    "anmeldung":               "anmeldung",
    "buergeramt":              "anmeldung",
    "ummeldung":               "anmeldung",
    "abmeldung":               "anmeldung",
    "personalausweis":         "personalausweis",
    "reisepass":               "reisepass",
    "fuehrerschein":           "fuehrerschein",
    "meldebescheinigung":      "anmeldung",
    # Ausländerbehörde
    "auslaenderbehoerde":      "auslaenderbehoerde",
    "aufenthaltstitel":        "auslaenderbehoerde",
    "niederlassungserlaubnis": "auslaenderbehoerde",
}

# DTMS entry point (confirmed 2026-03-01)
_HAMBURG_DTMS_BASE = "https://driveport.de/termine"
_HAMBURG_PORTAL_ENTRY = (
    "https://serviceportal.hamburg.de/HamburgGateway/Service/Entry/DigiTermin"
)
_HAMBURG_BOOKING_URL = "https://driveport.de/termine/"

# Availability text patterns in the DTMS SPA shell / server hints
_HAMBURG_AVAILABLE_TEXTS = [
    "termin verfügbar",
    "freier termin",
    "buchung möglich",
    "termine vorhanden",
    "jetzt buchen",
    "slot available",
    "available",          # English variant in API responses
    '"available":true',   # JSON fragment if SSR injects state
    '"hasSlots":true',
    '"slotsAvailable":true',
]

# SignalR negotiate endpoint — POST here; 200 + JSON with connectionToken = hub alive
_HAMBURG_SIGNALR_HUB = f"{_HAMBURG_DTMS_BASE}/terminHub"


async def check_hamburg_slots(service_key: str) -> dict:
    """Real Hamburg availability checker via DTMS (driveport.de).

    Uses a two-signal approach:
      1. POST to SignalR negotiate — confirms the DTMS backend is live.
      2. GET the DTMS SPA entry page — looks for server-injected availability text.

    Returns the same dict format as other city checkers:
        {"available": True,  "location": "Hamburg", "url": ...}  — slot detected
        {"available": False}                                       — no slot / backend down
    """
    svc = (service_key or "anmeldung").lower().strip()
    if svc not in _HAMBURG_SERVICE_MAP:
        logger.debug("HAMBURG_CHECK_UNKNOWN_SERVICE | service=%s", svc)
        return {"available": False}

    logger.info("HAMBURG_CHECK_START | service=%s", svc)

    try:
        import httpx

        headers_html = {
            **_HEADERS,
            "Referer": "https://serviceportal.hamburg.de/",
        }
        headers_signalr = {
            "User-Agent": _HEADERS["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "text/plain;charset=UTF-8",
            "Referer": _HAMBURG_DTMS_BASE + "/",
            "Origin": "https://driveport.de",
        }

        hub_alive = False
        page_signal = False
        connection_token = ""

        async with httpx.AsyncClient(
            timeout=_HTTPX_TIMEOUT,
            limits=_HTTPX_LIMITS,
            follow_redirects=True,
        ) as client:

            # ── Signal 1: SignalR negotiate ──────────────────────────────────
            # A successful negotiate means the DTMS backend is running and
            # accepting connections for this appointment type.
            try:
                neg_url = f"{_HAMBURG_SIGNALR_HUB}/negotiate?negotiateVersion=1"
                async with _HTTP_SEMAPHORE:
                    neg_resp = await client.post(neg_url, headers=headers_signalr, content=b"")
                logger.info(
                    "HAMBURG_SIGNALR_NEGOTIATE | service=%s status=%s",
                    svc, neg_resp.status_code,
                )
                if neg_resp.status_code == 200:
                    hub_alive = True
                    try:
                        neg_data = neg_resp.json()
                        connection_token = neg_data.get("connectionToken", "")
                    except Exception:
                        pass
                elif neg_resp.status_code in (401, 403):
                    # Auth required — hub exists but protected; count as alive
                    hub_alive = True
                    logger.info("HAMBURG_SIGNALR_NEGOTIATE_AUTH | service=%s status=%s", svc, neg_resp.status_code)
            except Exception as neg_exc:
                logger.warning("HAMBURG_SIGNALR_NEGOTIATE_ERROR | service=%s error=%s", svc, neg_exc)

            # ── Signal 2: Entry page text scan ───────────────────────────────
            try:
                async with _HTTP_SEMAPHORE:
                    entry_resp = await client.get(
                        _HAMBURG_PORTAL_ENTRY,
                        headers=headers_html,
                    )
                logger.info(
                    "HAMBURG_ENTRY_PAGE | service=%s status=%s len=%s",
                    svc, entry_resp.status_code, len(entry_resp.text),
                )
                if entry_resp.status_code == 200:
                    html_lower = entry_resp.text.lower()
                    for signal in _HAMBURG_AVAILABLE_TEXTS:
                        if signal.lower() in html_lower:
                            page_signal = True
                            logger.info(
                                "HAMBURG_PAGE_SIGNAL_FOUND | service=%s signal=%r",
                                svc, signal,
                            )
                            break
            except Exception as page_exc:
                logger.warning("HAMBURG_ENTRY_PAGE_ERROR | service=%s error=%s", svc, page_exc)

        # ── Decision logic ────────────────────────────────────────────────────
        # Report AVAILABLE only when BOTH signals confirm:
        #   - hub_alive: DTMS backend is running (not down/maintenance)
        #   - page_signal: server-injected text confirms slots exist
        #
        # hub_alive alone is insufficient — it just means the system is online.
        # page_signal alone could be a false positive from static HTML.
        # Both together is a strong positive signal.
        if hub_alive and page_signal:
            logger.info(
                "HAMBURG_AVAILABLE | service=%s hub_alive=%s page_signal=%s",
                svc, hub_alive, page_signal,
            )
            return {
                "available": True,
                "location": "Hamburg",
                "date": "",
                "time": "",
                "url": _HAMBURG_BOOKING_URL,
            }

        logger.info(
            "HAMBURG_NOT_AVAILABLE | service=%s hub_alive=%s page_signal=%s",
            svc, hub_alive, page_signal,
        )
        return {"available": False}

    except Exception as exc:
        logger.warning("HAMBURG_CHECK_ERROR | service=%s error=%s", svc, exc)
        return {"available": False}


async def check_koeln_slots(service_key: str) -> dict:
    """Slot checker for Köln — liveness probe via www.stadt-koeln.de (globally reachable).

    Architecture (updated 2026-03-02):
      termine.stadt-koeln.de is TCP-firewalled outside Germany and unusable as a
      direct endpoint.  Instead we probe the city's main appointment portal at
      www.stadt-koeln.de, which is served from a global CDN and returns HTTP 200
      worldwide in under 1 second.

      The portal page embeds Timify calendar UID links for every office type.
      Presence of UID links for the relevant office path confirms:
        (a) the portal is operational, and
        (b) the booking system is configured and active for that service.

    Steps:
      1. GET https://www.stadt-koeln.de/service/kontakt/terminvereinbarung-online
      2. Confirm HTTP 200.
      3. Check that at least one Timify UID link for the relevant office path
         (e.g. "kundenzentren" for buergeramt, "auslaenderamt" for
         auslaenderbehoerde) is present in the HTML.
      4. Return available=True if portal is up and office links are present.
    """
    import httpx
    import re

    svc = (service_key or "buergeramt").lower().strip()
    logger.info("KOELN_CHECK_STARTED | service=%s", svc)

    office_path = _KOELN_OFFICE_PATHS.get(svc)
    if not office_path:
        logger.debug("KOELN_CHECK_UNKNOWN_SERVICE | service=%s", svc)
        return {"available": False, "city": "koeln"}

    headers = {
        **_HEADERS,
        "Referer": "https://www.stadt-koeln.de/",
    }
    timeout = httpx.Timeout(5.0)

    try:
        client = _get_shared_client()
        async with _HTTP_SEMAPHORE:
            resp = await client.get(_KOELN_PORTAL_URL, headers=headers)

        logger.info(
            "CITY_CHECK_EXECUTED | city=koeln service=%s status=%s",
            svc, resp.status_code,
        )

        if resp.status_code != 200:
            logger.warning(
                "KOELN_HTTP_ERROR | service=%s status=%s",
                svc, resp.status_code,
            )
            return {"available": False, "city": "koeln"}

        # Confirm booking system is active: Timify UID links for this office must exist.
        uid_pattern = re.compile(
            r'https://termine\.stadt-koeln\.de/m/' + re.escape(office_path) +
            r'/extern/calendar/\?uid=([a-f0-9\-]+)',
            re.IGNORECASE,
        )
        uid_matches = uid_pattern.findall(resp.text)

        if uid_matches:
            logger.info(
                "KOELN_PORTAL_UP | service=%s office=%s uid_links=%d",
                svc, office_path, len(uid_matches),
            )
            location_label = (
                "Köln Ausländeramt" if office_path == "auslaenderamt"
                else "Köln Kundenzentrum"
            )
            return {
                "available":    True,
                "city":         "koeln",
                "location":     location_label,
                "date":         "",
                "time":         "",
                "url":          _KOELN_BOOKING_URL,
                "liveness_only": True,  # no exact slot — portal is UP, user must book manually
            }

        logger.info(
            "KOELN_NOT_AVAILABLE | service=%s office=%s (no UID links found in portal)",
            svc, office_path,
        )
        return {"available": False, "city": "koeln"}

    except httpx.TimeoutException as exc:
        logger.warning("KOELN_TIMEOUT | service=%s error=%s", svc, exc)
        return {"available": False, "city": "koeln"}
    except httpx.ConnectError as exc:
        logger.warning("KOELN_CONNECT_ERROR | service=%s error=%s", svc, exc)
        return {"available": False, "city": "koeln"}
    except Exception as exc:
        logger.warning("KOELN_ERROR | service=%s error=%s", svc, exc)
        return {"available": False, "city": "koeln"}


async def check_koeln_playwright(service_key: str) -> dict:
    """Köln Bürgerservice — Playwright-based real slot checker via KRZN TeVIS.

    Uses tevis.krzn.de/tevisweb190/ — a standard TeVIS EKOM21 instance that
    follows the same 6-step wizard as Frankfurt and Düsseldorf.
    Confirmed 2026-03-03: 296 real slots found for md=1 (Bürgerservice).
    No geo-blocking (globally reachable, unlike termine.stadt-koeln.de).
    """
    svc = (service_key or "buergeramt").lower().strip()
    md = _KOELN_KRZN_MD_MAP.get(svc, 1)
    logger.debug("KOELN_PLAYWRIGHT_CHECK | service=%s md=%d", svc, md)
    return await check_tevis_playwright_slots(
        _KOELN_KRZN_PLAYWRIGHT_BASE,
        md,
        _KOELN_KRZN_BOOKING_URL,
        "Koeln",
    )


async def check_krefeld_playwright(service_key: str) -> dict:
    """Krefeld Bürgerservice — Playwright-based real slot checker via KRZN TeVIS.

    Uses tevis.krzn.de/tevisweb350/ — KRZN TeVIS instance for Krefeld.
    Confirmed 2026-03-03: 32 real slots found for md=10 (Bürgerservice).
    md=10 is the correct service group; md=1 returns no cnc form for this instance.
    No geo-blocking, no CAPTCHA, globally reachable.
    """
    svc = (service_key or "buergeramt").lower().strip()
    md = _KREFELD_MD_MAP.get(svc, 10)
    logger.debug("KREFELD_PLAYWRIGHT_CHECK | service=%s md=%d", svc, md)
    return await check_tevis_playwright_slots(
        _KREFELD_PLAYWRIGHT_BASE,
        md,
        _KREFELD_BOOKING_URL,
        "Krefeld",
    )


# ==================== Supported Authorities ====================

# Only these authority codes have real working checkers.
# Any other authority_type will be rejected before hitting the scraper.
# Expand this set only when a new checker is implemented and verified.
SUPPORTED_AUTHORITIES: frozenset = frozenset({
    "buergeramt",
    "auslaenderbehoerde",
    # aliases that resolve to the same checker endpoint:
    "anmeldung",
    "ummeldung",
    "abmeldung",
    "aufenthaltstitel",
    "niederlassungserlaubnis",
    # Document services (Berlin / Frankfurt / Düsseldorf):
    "personalausweis",
    "reisepass",
    "fuehrerschein",
    "kindergeld",
    "buergergeld",
})


# ==================== Availability Checker ====================

_TERMIN_API_URL: str = os.getenv("TERMIN_API_URL", "")

# Dedup flag: log API warning once per error streak, reset on success.
_api_fail_logged: bool = False

# ---------------------------------------------------------------------------
# City-level result cache — prevents N duplicate HTTP/Playwright checks when
# N users monitor the same city simultaneously.
#
# Key   : "{city_key}:{auth_key}"  (e.g. "berlin:anmeldung")
# Value : {"result": TerminStatus, "slot_details": dict, "ts": float}
#
# asyncio is single-threaded — plain dict access is safe without locks.
# ---------------------------------------------------------------------------
CACHE_TTL_SEC: int = int(os.getenv("TERMIN_CACHE_TTL_SEC", "4"))
# Playwright cities are slower (60 s poll interval) — use a longer TTL so
# the browser is not re-launched by a second user arriving 1 s later.
CACHE_TTL_PLAYWRIGHT_SEC: int = int(os.getenv("TERMIN_CACHE_TTL_PLAYWRIGHT_SEC", "55"))

_PLAYWRIGHT_CITIES = frozenset({
    "frankfurt", "duesseldorf", "dusseldorf", "koeln", "cologne", "krefeld",
})

_city_result_cache: Dict[str, Dict] = {}


async def check_termin_availability(
    city: str = "", authority: str = ""
) -> Tuple[TerminStatus, dict]:
    """
    Check slot availability.

    Returns: (TerminStatus, slot_details_dict)

    slot_details_dict is populated when AVAILABLE:
        {
            "available": True,
            "location": "Bürgeramt Mitte",   # may be empty string
            "date":     "2026-03-14",          # may be empty string
            "time":     "10:15",               # may be empty string
            "url":      "https://..."
        }
    When NOT_AVAILABLE: slot_details_dict is {}

    Priority:
    1. Unsupported authority → fast-return NOT_AVAILABLE (no HTTP request made)
    2. München → check_muenchen_slots() (KVR POST API, www56/www46.muenchen.de)
    3. Köln → check_koeln_slots() (Timify REST, termine.stadt-koeln.de)
    4. Berlin / Frankfurt / Düsseldorf → check_city_slots() (TeVIS/HTML GET)
    5. Hamburg → DISABLED (removed from Premium cities; checker code kept but unreachable)
    6. TERMIN_API_URL set → custom REST API
    7. Other cities without scraper → NOT_AVAILABLE (no fake random)

    Never raises — always returns a TerminStatus.
    """
    global _api_fail_logged

    city_key = city.lower().strip()
    auth_key = (authority or "").lower().strip()
    _no_details: dict = {}

    # --- Guard: reject unsupported authority types immediately ---
    # Fast-path: no cache lookup — no real check is performed anyway.
    if auth_key and auth_key not in SUPPORTED_AUTHORITIES:
        logger.debug(
            "TERMIN_UNSUPPORTED_AUTHORITY | city=%s authority=%s → NOT_AVAILABLE",
            city_key, auth_key,
        )
        return TerminStatus.NOT_AVAILABLE, _no_details

    # --- City-level result cache ---
    # All user poll loops for the same city+authority share one real HTTP/Playwright
    # check per TTL window. asyncio single-thread guarantees no race conditions.
    _cache_key = f"{city_key}:{auth_key}"
    _now = time.time()
    _cached = _city_result_cache.get(_cache_key)
    if _cached is not None:
        _ttl = (
            CACHE_TTL_PLAYWRIGHT_SEC
            if city_key in _PLAYWRIGHT_CITIES
            else CACHE_TTL_SEC
        )
        if (_now - _cached["ts"]) < _ttl:
            logger.debug(
                "TERMIN_CACHE_HIT | key=%s age=%.1fs ttl=%ds",
                _cache_key, _now - _cached["ts"], _ttl,
            )
            return _cached["result"], _cached["slot_details"]

    # --- Dispatch: run the real checker and cache the result ---
    # All city-specific checkers are called inside _do_check() so the cache
    # write happens in exactly one place, keeping the logic DRY.
    async def _do_check() -> Tuple[TerminStatus, dict]:
        global _api_fail_logged

        # --- München: POST-based KVR API ---
        if city_key in ("muenchen", "munich", "münchen"):
            slot = await check_muenchen_slots(authority)
            if slot.get("available"):
                _api_fail_logged = False
                return TerminStatus.AVAILABLE, slot
            return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Köln: Playwright-based real slot checker (KRZN TeVIS) ---
        if city_key in ("koeln", "cologne"):
            slot = await check_koeln_playwright(auth_key)
            if slot.get("available"):
                _api_fail_logged = False
                return TerminStatus.AVAILABLE, slot
            return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Krefeld: Playwright-based real slot checker (KRZN TeVIS tevisweb350) ---
        if city_key == "krefeld":
            slot = await check_krefeld_playwright(auth_key)
            if slot.get("available"):
                _api_fail_logged = False
                return TerminStatus.AVAILABLE, slot
            return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Dortmund: liveness probe (dortmund.termine-reservieren.de) ---
        if city_key == "dortmund":
            slot = await check_dortmund_slots(auth_key)
            if slot.get("available"):
                _api_fail_logged = False
                return TerminStatus.AVAILABLE, slot
            return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Frankfurt: Playwright-based real slot checker ---
        if city_key == "frankfurt":
            slot = await check_frankfurt_playwright(auth_key)
            if slot.get("available"):
                _api_fail_logged = False
                return TerminStatus.AVAILABLE, slot
            return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Düsseldorf: Playwright-based real slot checker ---
        if city_key in ("duesseldorf", "dusseldorf"):
            slot = await check_duesseldorf_playwright(auth_key)
            if slot.get("available"):
                _api_fail_logged = False
                return TerminStatus.AVAILABLE, slot
            return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Berlin: original HTTP-based checker (real slot API, no browser needed) ---
        if city_key in _CITY_SERVICE_URLS:
            slot = await check_city_slots(city_key, authority)
            if slot.get("available"):
                _api_fail_logged = False
                return TerminStatus.AVAILABLE, slot
            return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Custom REST API (any city) ---
        if _TERMIN_API_URL:
            try:
                import httpx
                client = _get_shared_client()
                async with _HTTP_SEMAPHORE:
                    resp = await client.get(
                        _TERMIN_API_URL,
                        params={"city": city, "authority": authority},
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    _api_fail_logged = False
                    if data.get("available", False):
                        return TerminStatus.AVAILABLE, data
                    return TerminStatus.NOT_AVAILABLE, _no_details

                if not _api_fail_logged:
                    logger.warning(
                        "TERMIN_API_HTTP_ERROR | status=%s url=%s",
                        resp.status_code, _TERMIN_API_URL,
                    )
                    _api_fail_logged = True
                return TerminStatus.NOT_AVAILABLE, _no_details

            except Exception as exc:
                if not _api_fail_logged:
                    logger.warning("TERMIN_API_FAIL | city=%s error=%s", city, exc)
                _api_fail_logged = True
                return TerminStatus.NOT_AVAILABLE, _no_details

        # --- Hamburg: REMOVED from Premium cities ---
        # check_hamburg_slots() is kept in the codebase but routing is intentionally disabled.
        # Hamburg is no longer offered to users. Premium cities: Berlin, Frankfurt,
        # Düsseldorf, München, Köln.
        # if city_key in ("hamburg",):
        #     slot = await check_hamburg_slots(auth_key)
        #     if slot.get("available"):
        #         _api_fail_logged = False
        #         return TerminStatus.AVAILABLE, slot
        #     return TerminStatus.NOT_AVAILABLE, _no_details

        # --- No real checker available for this city yet ---
        logger.debug("TERMIN_NO_CHECKER | city=%s authority=%s → NOT_AVAILABLE", city, authority)
        return TerminStatus.NOT_AVAILABLE, _no_details

    _result, _slot_details = await _do_check()

    # Write result to cache (both AVAILABLE and NOT_AVAILABLE are cached so
    # NOT_AVAILABLE floods also don't hammer the server with duplicate requests).
    _city_result_cache[_cache_key] = {
        "result":       _result,
        "slot_details": _slot_details,
        "ts":           time.time(),
    }
    logger.debug(
        "TERMIN_CACHE_WRITE | key=%s result=%s",
        _cache_key, _result,
    )
    return _result, _slot_details


# ==================== Localized Status Messages ====================
_MSG_CHECKING: Dict[str, str] = {
    "ua": "🔍 Перевіряємо наявність вільних місць…",
    "en": "🔍 Checking availability…",
    "de": "🔍 Verfügbarkeit wird geprüft…",
    "pl": "🔍 Sprawdzamy dostępność…",
    "tr": "🔍 Uygunluk kontrol ediliyor…",
    "ar": "🔍 جارٍ التحقق من التوفر…",
}
_MSG_NOT_AVAILABLE: Dict[str, str] = {
    "ua": "⏳ Вільних місць немає. Повторна перевірка через 15 сек…",
    "en": "⏳ No slots available, retrying in 15 sec…",
    "de": "⏳ Keine Termine verfügbar, erneuter Versuch in 15 Sek…",
    "pl": "⏳ Brak wolnych miejsc, ponowna próba za 15 sek…",
    "tr": "⏳ Uygun yer yok, 15 sn sonra tekrar denenecek…",
    "ar": "⏳ لا توجد مواعيد متاحة، إعادة المحاولة خلال 15 ثانية…",
}
_MSG_FOUND: Dict[str, str] = {
    "ua": "🎯 Знайдено запис!",
    "uk": "🎯 Знайдено запис!",
    "en": "🎯 Appointment found!",
    "de": "🎯 Termin gefunden!",
    "pl": "🎯 Znaleziono termin!",
    "tr": "🎯 Randevu bulundu!",
    "ar": "🎯 تم العثور على موعد!",
}

# Urgency warning shown after slot details — reminds user to act immediately.
_MSG_FOUND_URGENCY: Dict[str, str] = {
    "ua": "⚡ Слоти можуть зникнути за секунди — натисніть кнопку нижче",
    "uk": "⚡ Слоти можуть зникнути за секунди — натисніть кнопку нижче",
    "en": "⚡ Slots can disappear in seconds — use the button below",
    "de": "⚡ Termine können in Sekunden verschwinden — nutzen Sie die Schaltfläche unten",
    "pl": "⚡ Terminy mogą zniknąć w kilka sekund — użyj przycisku poniżej",
    "tr": "⚡ Randevular saniyeler içinde kaybolabilir — aşağıdaki butonu kullanın",
    "ar": "⚡ قد تختفي المواعيد خلال ثوانٍ — استخدم الزر أدناه",
}

# Localized labels for the rich found-message detail lines
_FOUND_LABEL_LOCATION: Dict[str, str] = {
    "ua": "📍 Місце",
    "en": "📍 Location",
    "de": "📍 Ort",
    "pl": "📍 Lokalizacja",
    "tr": "📍 Konum",
    "ar": "📍 الموقع",
}
_FOUND_LABEL_DATE: Dict[str, str] = {
    "ua": "📅 Дата",
    "en": "📅 Date",
    "de": "📅 Datum",
    "pl": "📅 Data",
    "tr": "📅 Tarih",
    "ar": "📅 التاريخ",
}
_FOUND_LABEL_TIME: Dict[str, str] = {
    "ua": "⏰ Час",
    "en": "⏰ Time",
    "de": "⏰ Uhrzeit",
    "pl": "⏰ Godzina",
    "tr": "⏰ Saat",
    "ar": "⏰ الوقت",
}
_FOUND_LABEL_BOOK: Dict[str, str] = {
    "ua": "📅 Перейти до бронювання",
    "en": "📅 Open booking page",
    "de": "📅 Buchungsseite öffnen",
    "pl": "📅 Otwórz stronę rezerwacji",
    "tr": "📅 Rezervasyon sayfasını aç",
    "ar": "📅 فتح صفحة الحجز",
}
_FOUND_FALLBACK_LOCATION = "Bürgeramt"

# Localized "check portal" fallback shown when the checker cannot extract an
# exact date/time (München liveness probe, Köln portal probe, geo-blocked 403).
# Never shows hardcoded EN "Available" / "Soon" to non-EN users.
_FOUND_FALLBACK_DATE: Dict[str, str] = {
    "ua": "Перевірте портал",
    "en": "Check portal",
    "de": "Portal prüfen",
    "pl": "Sprawdź portal",
    "tr": "Portalı kontrol edin",
    "ar": "تحقق من البوابة",
}
_FOUND_FALLBACK_TIME: Dict[str, str] = {
    "ua": "Якнайшвидше",
    "en": "As soon as possible",
    "de": "So schnell wie möglich",
    "pl": "Jak najszybciej",
    "tr": "En kısa sürede",
    "ar": "في أقرب وقت",
}
# City-specific portal fallback URLs.
# Used when the slot dict carries no URL and get_authority_info() returns nothing.
# Each city gets its own portal root — never the wrong city's URL.
_CITY_PORTAL_FALLBACKS: Dict[str, str] = {
    "berlin":       "https://service.berlin.de/terminvereinbarung/",
    "frankfurt":    "https://tevis.ekom21.de/fra/",
    "duesseldorf":  "https://termine.duesseldorf.de/",
    "dusseldorf":   "https://termine.duesseldorf.de/",
    "düsseldorf":   "https://termine.duesseldorf.de/",
    "koeln":        "https://tevis.krzn.de/tevisweb190/",
    "cologne":      "https://tevis.krzn.de/tevisweb190/",
    "krefeld":      "https://tevis.krzn.de/tevisweb350/",
    "muenchen":     "https://www48.muenchen.de/buergeransicht/",
    "munich":       "https://www48.muenchen.de/buergeransicht/",
    "münchen":      "https://www48.muenchen.de/buergeransicht/",
    "dortmund":     "https://dortmund.termine-reservieren.de/",
    "hamburg":      "https://serviceportal.hamburg.de/HamburgGateway/Service/Entry/DigiTermin",
}
# Generic fallback for unknown cities — a neutral German gov info page.
_FOUND_FALLBACK_URL = "https://www.germany.info/us-de/service/termine/termin-vereinbarung/2530996"


def build_best_booking_link(slot: dict, city: str = "") -> str:
    """Return the most specific bookable URL available for a found slot.

    Priority model:
      A — slot-level deep link (``direct_url`` field, currently TeVIS select2?md=N)
      B — service/calendar page (``url`` field when it is more specific than a root)
      C — city-specific portal root from ``_CITY_PORTAL_FALLBACKS``
      D — generic German gov page (last resort)

    The function never returns a wrong-city URL (old bug: Berlin fallback for München).
    """
    # Priority A/B: slot dict url (already set to direct_url by tevis_scraper or
    # service-specific URL by Berlin checker)
    url = slot.get("url") or ""
    if url:
        return url

    # Priority C: city-specific portal root
    city_key = (city or "").lower().strip()
    if city_key in _CITY_PORTAL_FALLBACKS:
        return _CITY_PORTAL_FALLBACKS[city_key]

    # Priority D: generic fallback
    return _FOUND_FALLBACK_URL


# Liveness-probe header: used instead of "Slot found!" for München/Köln where
# we confirm the portal is UP but cannot extract exact date/time without captcha.
_MSG_FOUND_LIVENESS: Dict[str, str] = {
    "ua": "🔔 Портал відкритий — перевірте доступні місця!",
    "en": "🔔 Portal is open — check for available slots now!",
    "de": "🔔 Portal ist offen — Termine jetzt prüfen!",
    "pl": "🔔 Portal otwarty — sprawdź dostępne terminy!",
    "tr": "🔔 Portal açık — mevcut randevuları şimdi kontrol edin!",
    "ar": "🔔 البوابة مفتوحة — تحقق من المواعيد المتاحة الآن!",
}


def build_found_message(lang: str, slot: dict) -> str:
    """Build a rich slot-found message from checker details.

    Public API — importable by handlers so they can compose the text themselves
    and attach any desired keyboard without text-pattern detection.

    For cities where only liveness is confirmed (München, Köln — slot["liveness_only"] = True),
    shows a softer "portal is open, check now" header instead of "Slot found!" to avoid
    misleading the user when exact date/time cannot be extracted.

    All fallback strings are fully localized — no hardcoded EN.
    """
    is_liveness = slot.get("liveness_only", False)
    header = (
        _MSG_FOUND_LIVENESS.get(lang, _MSG_FOUND_LIVENESS["en"])
        if is_liveness
        else _MSG_FOUND.get(lang, _MSG_FOUND["en"])
    )
    location = slot.get("location") or _FOUND_FALLBACK_LOCATION

    # Use localized fallback when date/time are empty (liveness-probe cities)
    _fb_date = _FOUND_FALLBACK_DATE.get(lang, _FOUND_FALLBACK_DATE["en"])
    _fb_time = _FOUND_FALLBACK_TIME.get(lang, _FOUND_FALLBACK_TIME["en"])
    date = slot.get("date") or _fb_date
    time_val = slot.get("time") or _fb_time

    # Use build_best_booking_link to ensure the most specific URL is used.
    # The city is not passed here since build_found_message is called without city context;
    # the slot["url"] set by each city checker already carries the correct URL.
    url = build_best_booking_link(slot)

    loc_lbl = _FOUND_LABEL_LOCATION.get(lang, _FOUND_LABEL_LOCATION["en"])
    date_lbl = _FOUND_LABEL_DATE.get(lang, _FOUND_LABEL_DATE["en"])
    time_lbl = _FOUND_LABEL_TIME.get(lang, _FOUND_LABEL_TIME["en"])
    book_lbl = _FOUND_LABEL_BOOK.get(lang, _FOUND_LABEL_BOOK["en"])

    urgency = _MSG_FOUND_URGENCY.get(lang, _MSG_FOUND_URGENCY["en"])

    if is_liveness:
        # Compact format for liveness-probe: skip date/time rows (empty anyway),
        # show only location, urgency warning, and booking link
        return (
            f"🎯 {header}\n\n"
            f"{loc_lbl}: {location}\n\n"
            f"{urgency}\n\n"
            f"{book_lbl}:\n{url}"
        )

    return (
        f"🎯 {header}\n\n"
        f"{loc_lbl}: {location}\n"
        f"{date_lbl}: {date}\n"
        f"{time_lbl}: {time_val}\n\n"
        f"{urgency}\n\n"
        f"{book_lbl}:\n{url}"
    )


_MSG_STOPPED: Dict[str, str] = {
    "ua": "⏹ Перевірку зупинено.",
    "uk": "⏹ Перевірку зупинено.",
    "en": "⏹ Polling stopped.",
    "de": "⏹ Prüfung gestoppt.",
    "pl": "⏹ Sprawdzanie zatrzymane.",
    "tr": "⏹ Kontrol durduruldu.",
    "ar": "⏹ تم إيقاف الفحص.",
}
_MSG_RESERVATION_EXPIRED: Dict[str, str] = {
    "ua": "⏳ Схоже, цей слот вже зайнятий або час резервування минув.\nМи продовжуємо пошук нових Termin для вас.",
    "uk": "⏳ Схоже, цей слот вже зайнятий або час резервування минув.\nМи продовжуємо пошук нових Termin для вас.",
    "en": "⏳ This appointment may already be taken or the reservation window expired.\nWe continue searching for new appointments for you.",
    "de": "⏳ Dieser Termin ist möglicherweise bereits vergeben oder die Reservierungszeit ist abgelaufen.\nWir suchen weiter nach neuen Terminen für Sie.",
    "pl": "⏳ Ten termin może być już zajęty lub czas rezerwacji minął.\nKontynuujemy wyszukiwanie nowych terminów.",
    "tr": "⏳ Bu randevu alınmış olabilir veya rezervasyon süresi dolmuş olabilir.\nYeni randevular aramaya devam ediyoruz.",
    "ar": "⏳ قد يكون هذا الموعد قد تم حجزه أو انتهت مدة الحجز.\nسنواصل البحث عن مواعيد جديدة لك.",
}

POLL_INTERVAL_SEC = 5
# Playwright-based cities (Frankfurt, Düsseldorf) need more time per check:
# browser launch + 3-step TeVIS navigation + suggestion-form parsing ≈ 10-30 s.
# 60 s keeps server load reasonable while still providing timely notifications.
PLAYWRIGHT_POLL_INTERVAL_SEC = 60
RESERVATION_TIMEOUT_SEC = 180
COOLDOWN_SEC = 45

# Adaptive backoff — applied only on the NOT_AVAILABLE path.
# Each consecutive miss multiplies the current interval by BACKOFF_FACTOR until
# MAX_INTERVAL_SEC is reached.  The interval resets immediately on AVAILABLE.
# Playwright cities start from PLAYWRIGHT_POLL_INTERVAL_SEC as their base.
_BACKOFF_FACTOR = float(os.getenv("TERMIN_BACKOFF_FACTOR", "1.5"))
_MAX_INTERVAL_SEC = int(os.getenv("TERMIN_MAX_INTERVAL_SEC", "60"))
_PLAYWRIGHT_MAX_INTERVAL_SEC = int(os.getenv("TERMIN_PLAYWRIGHT_MAX_INTERVAL_SEC", "300"))
# Minimum gap between two "Slot Found" notifications for the same user/city.
# Prevents the Slot Found → Expired → Slot Found spam loop when a checker
# returns available=True on every poll (e.g. München liveness-probe strategy).
SLOT_NOTIFY_COOLDOWN_SEC = 600  # 10 minutes


# ==================== Type Aliases ====================
SendFunc = Callable[[int, str], Awaitable[None]]
"""Type alias: async function(chat_id, text) that sends a Telegram message."""

OnReservedFunc = Callable[[int, str], Awaitable[None]]
"""Type alias: async function(chat_id, lang) called when slot found — handler sends reservation UI."""

OnFoundFunc = Callable[[int, str, dict], Awaitable[None]]
"""Type alias: async function(chat_id, lang, slot_details) called when a slot is found without
reservation. The handler is responsible for building and sending the found-message with any
desired keyboard. slot_details contains location/date/time/url from the scraper."""


from utils.termin_redis import RedisBackedDict, rset, rget


# ==================== Per-User Session Store ====================
class _PollingSession:
    __slots__ = ("user_id", "chat_id", "city", "authority", "lang",
                 "status", "task", "reservation_task",
                 "started_at", "checks_count", "last_check_ts",
                 "send_fn", "on_reserved_fn", "on_found_fn",
                 "payment_pending", "locked_price",
                 "slot_details", "last_notified_ts",
                 "success_screen_shown",
                 "status_message_id", "_last_status_text")

    def __init__(self, user_id: int, chat_id: int, city: str,
                 authority: str, lang: str,
                 send_fn: SendFunc,
                 on_reserved_fn: Optional[OnReservedFunc] = None,
                 on_found_fn: Optional[OnFoundFunc] = None):
        self.user_id = user_id
        self.chat_id = chat_id
        self.city = city
        self.authority = authority
        self.lang = lang
        self.status: TerminStatus = TerminStatus.NOT_AVAILABLE
        self.task: Optional[asyncio.Task] = None
        self.reservation_task: Optional[asyncio.Task] = None
        self.started_at: float = time.time()
        self.checks_count: int = 0
        self.last_check_ts: float = 0.0  # unix timestamp of last poll attempt
        self.send_fn: SendFunc = send_fn
        self.on_reserved_fn: Optional[OnReservedFunc] = on_reserved_fn
        self.on_found_fn: Optional[OnFoundFunc] = on_found_fn
        self.payment_pending: bool = False
        self.locked_price: Optional[float] = None
        self.slot_details: dict = {}  # filled when slot found: location/date/time/url
        self.last_notified_ts: float = 0.0  # unix timestamp of last Slot Found notification sent
        # Post-payment success screen barrier: notifications are suppressed until the
        # "✅ Monitoring Activated" screen has been delivered to the user.
        # Set to True by set_success_screen_shown() after the success message is sent.
        # For sessions started from bot restart (_resume_termin_monitoring) this is
        # pre-set to True because the user is already aware monitoring is running.
        self.success_screen_shown: bool = False
        # Live status dashboard: if the user has the "📊 Status" message open,
        # its message_id is stored here so the poll loop can edit it in-place.
        # None means no status message is currently tracked.
        self.status_message_id: Optional[int] = None
        self._last_status_text: str = ""  # dedup guard: skip edit if text unchanged


# Active sessions: user_id → _PollingSession.
# Kept purely in-memory — _PollingSession contains asyncio.Task and callback
# references that cannot be serialized. Active polls/reservations are lost on
# restart (by design). Payment-critical guards (_payment_completed, locked_price)
# are persisted separately via Redis.
_sessions: Dict[int, _PollingSession] = {}

# Anti-spam cooldown: user_id → timestamp when cooldown started.
# Redis-backed (Stage 15): survives restart when REDIS_URL is set; falls back to in-memory.
_cooldowns = RedisBackedDict("termin:cd", ttl=COOLDOWN_SEC)


def _set_cooldown(user_id: int) -> None:
    """Record cooldown start for a user (called on cancel/fail/stop)."""
    _cooldowns[user_id] = time.time()


def _is_in_cooldown(user_id: int) -> bool:
    """Check if user is within cooldown window. Lazily cleans expired entries."""
    ts = _cooldowns.get(user_id)
    if ts is None:
        return False
    if time.time() - ts < COOLDOWN_SEC:
        return True
    # Expired — clean up
    _cooldowns.pop(user_id, None)
    return False


# ==================== Internal: Resume Polling ====================
def _resume_polling(session: _PollingSession) -> None:
    """Restart the poll loop for an existing session (after reservation release)."""
    session.status = TerminStatus.NOT_AVAILABLE
    session.reservation_task = None
    session.checks_count = 0
    # When resuming after a reservation expiry the user already saw the success screen
    # previously — no need to block notifications again.
    session.success_screen_shown = True
    task = asyncio.ensure_future(_poll_loop(session))
    session.task = task
    logger.info("TERMIN_POLL_RESUMED | user=%s", session.user_id)


# ==================== Internal: Reservation Timer ====================
async def _reservation_timer(session: _PollingSession) -> None:
    """Background timer: expires reservation after RESERVATION_TIMEOUT_SEC.

    After expiry the session transitions to PAUSED_AFTER_FOUND instead of
    automatically resuming polling.  The user must explicitly tap
    '🔄 Continue search' to restart — this prevents spam for liveness-probe
    cities (München/Köln) where the checker always returns available=True.
    """
    try:
        await asyncio.sleep(RESERVATION_TIMEOUT_SEC)
        lang = session.lang
        # Signal the send_fn hook that the reservation window expired.
        # The hook (make_termin_send_fn) will send one consolidated "slot taken"
        # message instead of the raw expired text, eliminating chat spam.
        try:
            await session.send_fn(
                session.chat_id,
                _MSG_RESERVATION_EXPIRED.get(lang, _MSG_RESERVATION_EXPIRED["en"]),
            )
        except Exception:
            pass
        logger.info("TERMIN_RESERVATION_EXPIRED | user=%s", session.user_id)
        # Transition to PAUSED — do NOT auto-resume to avoid notification spam.
        # The send_fn hook in make_termin_send_fn will show the "Continue search" button.
        session.status = TerminStatus.PAUSED_AFTER_FOUND
        session.reservation_task = None
        logger.info(
            "TERMIN_RESERVATION_PAUSED_AFTER_EXPIRY | user=%s city=%s"
            " — session kept, user must tap Continue to resume",
            session.user_id, session.city,
        )
    except asyncio.CancelledError:
        # Timer cancelled by confirm_reservation / cancel_reservation — handled there
        pass
    except Exception as exc:
        logger.error(
            "TERMIN_RESERVATION_TIMER_ERROR | user=%s error=%s",
            session.user_id, exc,
        )
        _sessions.pop(session.user_id, None)


# ==================== Slot Reminder Task ====================

_SLOT_REMINDER_TEXT: Dict[str, str] = {
    "ua": "⚠️ Нагадування: Цей слот може швидко зникнути.\nВідкрийте сторінку бронювання зараз.",
    "uk": "⚠️ Нагадування: Цей слот може швидко зникнути.\nВідкрийте сторінку бронювання зараз.",
    "en": "⚠️ Reminder: Your appointment slot may disappear quickly.\nOpen the booking page now to confirm it.",
    "de": "⚠️ Erinnerung: Dieser Termin kann schnell vergeben werden.\nÖffnen Sie jetzt die Buchungsseite.",
    "pl": "⚠️ Przypomnienie: Ten termin może szybko zniknąć.\nOtwórz stronę rezerwacji teraz.",
    "tr": "⚠️ Hatırlatma: Bu randevu hızlı kaybolabilir.\nŞimdi rezervasyon sayfasını açın.",
    "ar": "⚠️ تذكير: قد يختفي هذا الموعد بسرعة.\nافتح صفحة الحجز الآن.",
}


async def _slot_reminder_task(session: _PollingSession, delay: int = 10) -> None:
    """Send a single urgency reminder ~10 s after a slot is found.

    Only fires if the session is still alive AND the user has not yet
    finalized the booking (status == RESERVED).  Both guards are mandatory:
    the session may be cleaned up by stop_polling / cancel_reservation before
    the delay elapses, and the user may tap "I booked" in the meantime.
    """
    await asyncio.sleep(delay)

    # Guard 1 — session may have been removed from _sessions
    live = _sessions.get(session.user_id)
    if not live:
        return

    # Guard 2 — user finalized booking (FINALIZED) or reservation expired (PAUSED_AFTER_FOUND)
    if live.status != TerminStatus.RESERVED:
        return

    lang = live.lang
    text = _SLOT_REMINDER_TEXT.get(lang, _SLOT_REMINDER_TEXT["en"])
    try:
        await live.send_fn(live.chat_id, text)
        logger.info(
            "TERMIN_SLOT_REMINDER_SENT | user=%s city=%s",
            live.user_id, live.city,
        )
    except Exception as _re:
        logger.debug("TERMIN_SLOT_REMINDER_ERROR | user=%s err=%s", session.user_id, _re)


# ==================== Core Poll Loop ====================
async def _poll_loop(session: _PollingSession) -> None:
    """Background coroutine: poll every POLL_INTERVAL_SEC until found or cancelled."""
    lang = session.lang
    _transitioned_to_reserved = False

    # Adaptive backoff state — tracks the current NOT_AVAILABLE sleep duration.
    # AVAILABLE resets it to _base_interval; each consecutive miss multiplies by
    # _BACKOFF_FACTOR up to the per-city maximum.
    _is_playwright = session.city in (
        "frankfurt", "duesseldorf", "dusseldorf", "koeln", "cologne", "krefeld"
    )
    _base_interval: float = PLAYWRIGHT_POLL_INTERVAL_SEC if _is_playwright else POLL_INTERVAL_SEC
    _max_interval: float = _PLAYWRIGHT_MAX_INTERVAL_SEC if _is_playwright else _MAX_INTERVAL_SEC
    _interval: float = _base_interval

    try:
        # Short initial delay so the "✅ Monitoring Activated" message reaches the user
        # before the first slot check fires. Prevents the UX impression that a slot was
        # found instantly at payment time. Does not affect ongoing poll cadence.
        if session.checks_count == 0:
            await asyncio.sleep(3)

        while True:
            if session.checks_count > 0 and session.checks_count % 10 == 0:
                try:
                    from backend.termin_db import is_termin_entitled as _ite_guard
                    if not _ite_guard(str(session.user_id)):
                        logger.info(
                            "TERMIN_POLL_ENTITLEMENT_EXPIRED | user=%s city=%s — stopping",
                            session.user_id, session.city,
                        )
                        raise asyncio.CancelledError
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
            session.checks_count += 1
            session.last_check_ts = time.time()
            result, slot_details = await check_termin_availability(session.city, session.authority)

            if result == TerminStatus.AVAILABLE:
                # Slot found — reset backoff immediately so the next cycle after
                # any barrier/cooldown wait fires at the base rate.
                _interval = _base_interval

                # Persist slot details in session (accessible via get_slot_details)
                session.slot_details = slot_details

                # ── Post-payment Success Screen Barrier ──────────────────────────
                # Never send a slot notification before the user has seen the
                # "✅ Monitoring Activated" success screen.  The webhook starts
                # polling and then sends the success message; on a fast check the
                # first AVAILABLE result can arrive before that message is delivered.
                # We suppress the notification and retry on the next poll cycle.
                if not session.success_screen_shown:
                    logger.info(
                        "TERMIN_NOTIFY_BLOCKED_WAITING_SUCCESS | user=%s city=%s",
                        session.user_id, session.city,
                    )
                    await asyncio.sleep(_base_interval)
                    continue
                else:
                    logger.info(
                        "TERMIN_NOTIFY_ALLOWED | user=%s city=%s",
                        session.user_id, session.city,
                    )
                # ────────────────────────────────────────────────────────────────

                # ── Early-poll Guard ─────────────────────────────────────────────
                # Do not fire a reservation notification on the very first checks.
                # The Berlin portal sometimes returns a transient AVAILABLE on the
                # first poll right after activation (race between session init and
                # the first real HTTP response). Requiring at least 3 checks before
                # allowing SLOT_SENT type=reserved filters out these false positives
                # without delaying genuine slot alerts on subsequent polls.
                if session.on_reserved_fn and session.checks_count < 3:
                    logger.info(
                        "TERMIN_EARLY_POLL_GUARD | user=%s city=%s checks=%s — "
                        "skipping reserved notification until check 3",
                        session.user_id, session.city, session.checks_count,
                    )
                    await asyncio.sleep(_base_interval)
                    continue
                # ────────────────────────────────────────────────────────────────

                # ── Slot Notify Cooldown ─────────────────────────────────────────
                # Guard against the Slot Found → Expired → Slot Found spam loop.
                # If the checker returns available=True on every poll (e.g. München
                # liveness-probe), resuming after an expiry would immediately fire
                # another notification. We enforce a per-session minimum gap.
                _now = time.time()
                _since_last = _now - session.last_notified_ts
                if session.last_notified_ts > 0 and _since_last < SLOT_NOTIFY_COOLDOWN_SEC:
                    logger.info(
                        "SLOT_COOLDOWN_ACTIVE | city=%s user=%s seconds_remaining=%.0f",
                        session.city, session.user_id,
                        SLOT_NOTIFY_COOLDOWN_SEC - _since_last,
                    )
                    await asyncio.sleep(_base_interval)
                    continue
                # ────────────────────────────────────────────────────────────────

                if session.on_reserved_fn:
                    # --- Soft-lock: transition to RESERVED ---
                    # Lock price at reservation time (guard: price immutable after this)
                    session.locked_price = get_termin_price(session.city, session.authority)
                    # Shadow-write locked price to Redis (survives restart)
                    try:
                        rset(f"termin:locked_price:{session.user_id}",
                             str(session.locked_price), 1800)
                    except Exception:
                        pass
                    session.status = TerminStatus.RESERVED
                    session.last_notified_ts = time.time()
                    logger.info(
                        "SLOT_SENT | city=%s user=%s type=reserved",
                        session.city, session.user_id,
                    )
                    await session.on_reserved_fn(session.chat_id, session.lang)
                    session.reservation_task = asyncio.ensure_future(
                        _reservation_timer(session)
                    )
                    asyncio.create_task(_slot_reminder_task(session))
                    _transitioned_to_reserved = True
                    logger.info(
                        "TERMIN_SLOT_RESERVED | user=%s city=%s auth=%s checks=%s",
                        session.user_id, session.city, session.authority,
                        session.checks_count,
                    )
                    return  # Exit loop; session stays alive for reservation
                else:
                    # No reservation callback — notify user and PAUSE polling.
                    # The session stays alive in _sessions so the user can resume
                    # via the "🔄 Continue search" button without re-paying.
                    # Poll loop exits here (return); finally block skips cleanup
                    # because _transitioned_to_reserved is reused as the guard flag.
                    session.status = TerminStatus.PAUSED_AFTER_FOUND
                    session.last_notified_ts = time.time()
                    logger.info(
                        "SLOT_SENT | city=%s user=%s type=found",
                        session.city, session.user_id,
                    )
                    if session.on_found_fn:
                        await session.on_found_fn(session.chat_id, lang, slot_details)
                    else:
                        found_msg = build_found_message(lang, slot_details)
                        await session.send_fn(session.chat_id, found_msg)
                    logger.info(
                        "TERMIN_SLOT_FOUND_PAUSED | user=%s city=%s auth=%s checks=%s"
                        " — polling paused, session kept for resume",
                        session.user_id, session.city, session.authority,
                        session.checks_count,
                    )
                    # Keep session alive — do NOT close entitlement yet.
                    # Entitlement is closed only after user explicitly stops or
                    # a new slot is found after resume.
                    _transitioned_to_reserved = True  # reuse flag: skip finally cleanup
                    return

            # Not available yet — wait silently (no user message).
            # Apply adaptive backoff: each consecutive miss increases the sleep
            # duration by _BACKOFF_FACTOR up to _max_interval.
            session.status = result
            logger.debug(
                "TERMIN_NOT_AVAILABLE | user=%s city=%s auth=%s check=%s interval=%.1fs",
                session.user_id, session.city, session.authority,
                session.checks_count, _interval,
            )
            # Push live update to the status dashboard if user has it open.
            await update_monitor_status(session)
            await asyncio.sleep(_interval)
            _interval = min(_max_interval, _interval * _BACKOFF_FACTOR)

    except asyncio.CancelledError:
        # Graceful cancellation
        try:
            await session.send_fn(
                session.chat_id,
                _MSG_STOPPED.get(lang, _MSG_STOPPED["en"]),
            )
        except Exception:
            pass
        logger.info("TERMIN_POLL_CANCELLED | user=%s", session.user_id)
    except Exception as exc:
        logger.error("TERMIN_POLL_ERROR | user=%s error=%s", session.user_id, exc)
    finally:
        # Don't clean up if we transitioned to RESERVED (reservation timer owns the session)
        if not _transitioned_to_reserved:
            _sessions.pop(session.user_id, None)


# ==================== Public API ====================

def start_polling(
    user_id: int,
    chat_id: int,
    city: str,
    authority: str,
    lang: str,
    send_fn: SendFunc,
    on_reserved_fn: Optional[OnReservedFunc] = None,
    on_found_fn: Optional[OnFoundFunc] = None,
) -> bool:
    """
    Start a background availability poll for a user.

    Returns True if started, False if blocked.
    Blocked when:
      - user already has an active session (polling / reserved / payment)
      - user is in post-cancel/fail cooldown window

    If on_reserved_fn is provided, AVAILABLE triggers a soft-lock reservation
    instead of a simple notification. The handler should send the reservation
    UI (confirm/cancel buttons) inside on_reserved_fn.

    If on_found_fn is provided (and on_reserved_fn is NOT), it is called as
    on_found_fn(chat_id, lang, slot_details) when a slot is found. The handler
    is fully responsible for sending the found-message and any keyboards. This
    avoids any text-pattern detection on the checker side.
    """
    allowed, reason = can_start_polling(user_id)
    if not allowed:
        logger.info(
            "TERMIN_POLL_BLOCKED | user=%s reason=%s", user_id, reason,
        )
        return False

    # Clean up any stale session entry
    _sessions.pop(user_id, None)

    session = _PollingSession(
        user_id, chat_id, city, authority, lang,
        send_fn=send_fn, on_reserved_fn=on_reserved_fn,
        on_found_fn=on_found_fn,
    )
    task = asyncio.ensure_future(_poll_loop(session))
    session.task = task
    _sessions[user_id] = session
    logger.info(
        "TERMIN_POLL_START | user=%s city=%s auth=%s lang=%s reservation=%s",
        user_id, city, authority, lang, bool(on_reserved_fn),
    )
    return True


def set_success_screen_shown(user_id: int, shown: bool = True) -> None:
    """
    Mark that the post-payment '✅ Monitoring Activated' screen has been delivered.

    Call this immediately after successfully sending the success message to the user.
    Until this is called, _poll_loop suppresses all slot-found / reserved notifications
    to guarantee the user sees the success screen before any slot alert.

    Safe to call even when no active session exists (no-op in that case).
    """
    session = _sessions.get(user_id)
    if session is None:
        return
    session.success_screen_shown = shown
    if shown:
        logger.info(
            "TERMIN_SUCCESS_SCREEN_CONFIRMED | user=%s city=%s auth=%s",
            user_id, session.city, session.authority,
        )


def resume_after_found(user_id: int) -> bool:
    """
    Resume polling for a user whose session was paused after a slot notification.

    Allowed only when session.status == PAUSED_AFTER_FOUND.
    Returns True if polling was restarted, False otherwise.
    """
    session = _sessions.get(user_id)
    if not session:
        return False
    if session.status != TerminStatus.PAUSED_AFTER_FOUND:
        logger.info(
            "TERMIN_RESUME_AFTER_FOUND_BLOCKED | user=%s status=%s",
            user_id, session.status,
        )
        return False
    # Reset state and restart the poll loop
    session.status = TerminStatus.NOT_AVAILABLE
    session.checks_count = 0
    session.success_screen_shown = True  # no need to re-show success screen
    task = asyncio.ensure_future(_poll_loop(session))
    session.task = task
    logger.info(
        "TERMIN_RESUME_AFTER_FOUND | user=%s city=%s auth=%s",
        user_id, session.city, session.authority,
    )
    return True


def stop_polling(user_id: int) -> bool:
    """
    Cancel all polling + reservation activity for a user.

    Triggers cooldown. Returns True if something was cancelled, False if no active session.
    """
    session = _sessions.get(user_id)
    if not session:
        return False

    cancelled = False
    if session.task and not session.task.done():
        session.task.cancel()
        cancelled = True
    if session.reservation_task and not session.reservation_task.done():
        session.reservation_task.cancel()
        cancelled = True

    _sessions.pop(user_id, None)
    if cancelled:
        _set_cooldown(user_id)
        logger.info("TERMIN_POLL_STOP | user=%s cooldown=%ss", user_id, COOLDOWN_SEC)
        return True
    return False


def confirm_reservation(user_id: int) -> bool:
    """
    Confirm the soft-lock reservation for a user.

    Cancels the reservation timer and cleans up the session.
    Returns True if confirmed, False if no active reservation.
    """
    session = _sessions.get(user_id)
    if not session or session.status != TerminStatus.RESERVED:
        return False

    if session.reservation_task and not session.reservation_task.done():
        session.reservation_task.cancel()
    session.reservation_task = None
    _sessions.pop(user_id, None)
    logger.info("TERMIN_RESERVATION_CONFIRMED | user=%s", user_id)
    return True


def cancel_reservation(user_id: int) -> bool:
    """
    Cancel the soft-lock reservation and resume polling.

    Triggers cooldown. Returns True if cancelled + polling resumed, False if no active reservation.
    """
    session = _sessions.get(user_id)
    if not session or session.status != TerminStatus.RESERVED:
        return False

    if session.reservation_task and not session.reservation_task.done():
        session.reservation_task.cancel()
    session.reservation_task = None
    session.payment_pending = False

    _set_cooldown(user_id)

    # Resume polling automatically
    _resume_polling(session)
    logger.info("TERMIN_RESERVATION_CANCELLED_RESUMED | user=%s cooldown=%ss", user_id, COOLDOWN_SEC)
    return True


# ==================== Payment Gate API ====================

def proceed_to_payment(user_id: int) -> bool:
    """
    Pause reservation timer and mark session as payment-in-progress.

    Allowed ONLY from RESERVED state.
    The reservation timer is cancelled so it does NOT expire during payment.
    Returns True if paused, False if not in RESERVED state.
    """
    session = _sessions.get(user_id)
    if not session or session.status != TerminStatus.RESERVED:
        return False
    if session.payment_pending:
        return True  # Already in payment flow — idempotent

    # Cancel reservation timer (don't resume polling, don't clean up session)
    if session.reservation_task and not session.reservation_task.done():
        session.reservation_task.cancel()
    session.reservation_task = None
    session.payment_pending = True

    logger.info("TERMIN_PAYMENT_STARTED | user=%s", user_id)
    return True


def finalize_reservation(user_id: int) -> bool:
    """
    Finalize reservation after successful payment.

    Sets status to FINALIZED, cleans up session entirely.
    Polling does NOT restart. Cooldown is cleared (payment success is never penalized).
    Returns True if finalized, False if no active reservation.
    """
    session = _sessions.get(user_id)
    if not session or session.status != TerminStatus.RESERVED:
        return False

    # Cancel any lingering tasks
    if session.reservation_task and not session.reservation_task.done():
        session.reservation_task.cancel()
    if session.task and not session.task.done():
        session.task.cancel()

    session.status = TerminStatus.FINALIZED
    _sessions.pop(user_id, None)
    # FINALIZED bypasses cooldown — clear any existing cooldown
    _cooldowns.pop(user_id, None)
    # Clean up Redis locked_price shadow
    try:
        from utils.termin_redis import rdel as _rdel
        _rdel(f"termin:locked_price:{user_id}")
    except Exception:
        pass

    logger.info("TERMIN_RESERVATION_FINALIZED | user=%s", user_id)
    return True


def fail_payment(user_id: int) -> bool:
    """
    Handle payment failure / cancellation.

    Triggers cooldown. Releases reservation and auto-resumes polling.
    Returns True if released + polling resumed, False if no active session.
    """
    session = _sessions.get(user_id)
    if not session or session.status != TerminStatus.RESERVED:
        return False

    session.payment_pending = False
    _set_cooldown(user_id)

    # Resume polling automatically
    _resume_polling(session)

    logger.info("TERMIN_PAYMENT_FAILED_RESUMED | user=%s cooldown=%ss", user_id, COOLDOWN_SEC)
    return True


# ==================== Status Queries ====================

def can_start_polling(user_id: int) -> Tuple[bool, str]:
    """
    Check whether a user is allowed to start a new polling session.

    Returns:
        (True,  "ok")              — user may start polling
        (False, "active_session")  — polling / reserved / payment already active
        (False, "cooldown")        — in post-cancel/fail cooldown window
    """
    session = _sessions.get(user_id)
    if session:
        # Active poll loop
        if session.task and not session.task.done():
            return (False, "active_session")
        # Active reservation timer
        if session.reservation_task and not session.reservation_task.done():
            return (False, "active_session")
        # Payment in progress (timer paused, session alive)
        if session.payment_pending:
            return (False, "active_session")

    # Cooldown check (only matters when no active session blocks)
    if _is_in_cooldown(user_id):
        return (False, "cooldown")

    return (True, "ok")


def get_status(user_id: int) -> Optional[TerminStatus]:
    """Return current cached status for a user, or None if no session."""
    session = _sessions.get(user_id)
    if session:
        return session.status
    return None


def is_polling(user_id: int) -> bool:
    """True if a polling loop is active for this user."""
    session = _sessions.get(user_id)
    if not session:
        return False
    if session.task and not session.task.done():
        return True
    return False


def is_reserved(user_id: int) -> bool:
    """True if the user has an active soft-lock reservation (including payment-in-progress)."""
    session = _sessions.get(user_id)
    if not session or session.status != TerminStatus.RESERVED:
        return False
    # Reserved with active timer OR payment in progress
    if session.payment_pending:
        return True
    return bool(session.reservation_task and not session.reservation_task.done())


def get_locked_price(user_id: int) -> Optional[float]:
    """Return the price locked at reservation time, or None if no active reservation."""
    session = _sessions.get(user_id)
    if session and session.status == TerminStatus.RESERVED and session.locked_price is not None:
        return session.locked_price
    # Redis fallback: locked price may survive restart even if session is gone
    try:
        raw = rget(f"termin:locked_price:{user_id}")
        if raw is not None:
            return float(raw)
    except Exception:
        pass
    return None


def get_slot_details(user_id: int) -> dict:
    """Return the last slot details dict for user (populated when slot found).

    Returns {} when no session or slot not yet found.
    Keys: available, location, date, time, url.
    """
    session = _sessions.get(user_id)
    if session:
        return dict(session.slot_details)
    return {}


def get_session(user_id: int):
    """Return the live _PollingSession for user_id, or None if not currently polling."""
    return _sessions.get(user_id)


def get_monitoring_stats(user_id: int) -> dict:
    """Return real-time monitoring statistics for the user's active session.

    Returns:
        {
            "checks":         int  — total poll attempts since session started,
            "last_check_sec": int|None — seconds since last poll (None if not started yet)
        }

    Always safe — returns zeroed dict when no session exists.
    """
    session = _sessions.get(user_id)
    if not session:
        return {"checks": 0, "last_check_sec": None}

    last_sec: Optional[int] = None
    if session.last_check_ts:
        last_sec = int(time.time() - session.last_check_ts)

    return {
        "checks": session.checks_count,
        "last_check_sec": last_sec,
    }


def set_status_message_id(user_id: int, message_id: int) -> None:
    """Store the message_id of the '📊 Status' message the user has open.

    Called by handle_termin_status after sending/editing the status screen.
    The poll loop uses this to push live updates via edit_message_text.
    """
    session = _sessions.get(user_id)
    if session:
        session.status_message_id = message_id
        session._last_status_text = ""  # force first edit


def clear_status_message_id(user_id: int) -> None:
    """Clear the tracked status message_id (e.g. user navigated away)."""
    session = _sessions.get(user_id)
    if session:
        session.status_message_id = None
        session._last_status_text = ""


def build_status_text(session: "_PollingSession", lang: str,
                      countdown_line: str = "",
                      found_count_str: str = "",
                      status_label_override: "Optional[str]" = None) -> str:
    """Build the live monitoring status message text.

    Single source of truth used by:
      - handle_termin_status  (handlers/termin.py)  — all three render paths
      - update_monitor_status (utils/termin_checker.py) — live poll-driven edits

    Args:
        session:               Active _PollingSession or SimpleNamespace stub.
        lang:                  User language code.
        countdown_line:        Pre-built countdown string (empty = no block).
        found_count_str:       Pre-formatted social-proof counter (fetched lazily).
        status_label_override: When set, replaces the default "🟢 Active" label.
                               Use for paused state ("⏸ Pausiert") or custom text.

    Returns empty string on import failure so callers can detect and fall back.
    """
    import time as _t
    import datetime as _dt

    # Deferred import avoids circular dependency:
    # handlers.termin imports utils.termin_checker at module level;
    # we import handlers.termin here at call time only.
    try:
        from handlers.termin import (
            _lang_text, _CITY_DISPLAY_MAP, normalize_authority_name,
            _ALL_AUTHORITIES_LABEL,
            _STATUS_TITLE, _SSTAT_ACTIVE_LBL,
            _SSTAT_CITY_LBL, _SSTAT_DOC_LBL,
            _SSTAT_ELAPSED_LBL, _SSTAT_LASTCHK_LBL,
            _SSTAT_LASTCHK_SEC_AGO, _SSTAT_LASTCHK_STARTING, _SSTAT_CHECKS_LBL,
            _SSTAT_SCAN_PHRASES, _SSTAT_NOTIFY_HDR, _SSTAT_NOTIFY_BODY,
            _SSTAT_UPTIME_LBL, _SSTAT_UPTIME_MIN, _SSTAT_LAST_SLOT_LBL,
            _SSTAT_INTERVAL_NOTE, _SSTAT_EXPECTATION, _SSTAT_SOCIAL_PROOF,
            _SSTAT_LIVE_HDR, _SSTAT_LIVE_SCAN_NOW, _SSTAT_NEXT_CHECK,
        )
    except ImportError as _imp_err:
        logger.warning("build_status_text: import failed — %s", _imp_err)
        return ""

    city = session.city or "berlin"
    auth = session.authority or ""
    city_display = _CITY_DISPLAY_MAP.get(city, city.replace("_", " ").title())
    auth_display = (normalize_authority_name(auth) if auth
                    else _lang_text(_ALL_AUTHORITIES_LABEL, lang))

    checks = session.checks_count
    checks_display = f"🔵 {checks}" if checks > 0 else "—"

    if session.last_check_ts:
        last_sec = int(_t.time() - session.last_check_ts)
        last_display = f"🟡 {last_sec} {_lang_text(_SSTAT_LASTCHK_SEC_AGO, lang)}"
    else:
        last_display = _lang_text(_SSTAT_LASTCHK_STARTING, lang)

    # Elapsed time + uptime in minutes
    if getattr(session, "started_at", None):
        elapsed_sec = int(_t.time() - session.started_at)
        e_h, e_rem = divmod(elapsed_sec, 3600)
        e_m, _ = divmod(e_rem, 60)
        elapsed_str = f"{e_h}h {e_m}m" if e_h else f"{e_m}m"
        uptime_minutes = elapsed_sec // 60
    else:
        elapsed_str = "—"
        uptime_minutes = 0

    # Progress bar: fills 1 block every 2 checks, cycles every 20 checks.
    # Slower cycle looks more natural than checks % 10.
    bar_filled = min((checks // 2) % 10, 10)
    bar = "🟩" * bar_filled + "⬜" * (10 - bar_filled)

    # Live activity block — all state derived from wall-clock, zero storage.
    # pulse: 🟢/🟡 toggles every second  (timestamp % 2)
    # dot:   …/.../. cycles every second  (timestamp % 3)
    _ts = int(_t.time())
    pulse = "🟢" if _ts % 2 == 0 else "🟡"
    dot = ("…", "..", ".")[_ts % 3]
    live_block = (
        f"{pulse} <b>{_lang_text(_SSTAT_LIVE_HDR, lang)}</b>\n"
        f"{_lang_text(_SSTAT_LIVE_SCAN_NOW, lang)}{dot}\n"
        f"{_lang_text(_SSTAT_NEXT_CHECK, lang)}"
    )

    # Uptime line: "⏱ Працюємо вже: 17 хв"
    uptime_lbl = _lang_text(_SSTAT_UPTIME_LBL, lang)
    uptime_unit = _lang_text(_SSTAT_UPTIME_MIN, lang)
    uptime_line = f"{uptime_lbl}: {uptime_minutes} {uptime_unit}\n"

    # Last slot found — only shown after at least one slot was surfaced
    last_slot_line = ""
    if getattr(session, "last_notified_ts", 0) and session.last_notified_ts > 0:
        slot_dt = _dt.datetime.fromtimestamp(session.last_notified_ts)
        slot_str = slot_dt.strftime("%H:%M")
        last_slot_line = f"{_lang_text(_SSTAT_LAST_SLOT_LBL, lang)}: {slot_str}\n"

    # Social proof counter (fetched lazily when not provided by caller)
    if not found_count_str:
        try:
            from utils.stats import get_termin_found as _gtf
            found_count_str = f"{_gtf():,}".replace(",", " ")
        except Exception:
            found_count_str = "2 000+"

    cd_block = f"\n{countdown_line}\n" if countdown_line else "\n"
    sep = "<code>━━━━━━━━━━━━━━━</code>"
    active_lbl = (status_label_override
                  if status_label_override is not None
                  else _lang_text(_SSTAT_ACTIVE_LBL, lang))

    return (
        f"{_lang_text(_STATUS_TITLE, lang)}\n"
        f"{sep}\n\n"
        f"{active_lbl}"
        f"{cd_block}\n"
        f"{_lang_text(_SSTAT_CITY_LBL, lang)}:\n"
        f"<b>{city_display}</b>\n\n"
        f"{_lang_text(_SSTAT_DOC_LBL, lang)}:\n"
        f"<b>{auth_display}</b>\n\n"
        f"{sep}\n\n"
        f"{live_block}\n\n"
        f"{_lang_text(_SSTAT_LASTCHK_LBL, lang)}: {last_display}\n\n"
        f"{_lang_text(_SSTAT_NOTIFY_HDR, lang)}\n"
        f"{_lang_text(_SSTAT_NOTIFY_BODY, lang)}\n\n"
        f"{last_slot_line}"
        f"{_lang_text(_SSTAT_EXPECTATION, lang)}\n"
        f"{_lang_text(_SSTAT_SOCIAL_PROOF, lang).format(count=found_count_str)}"
    )


async def update_monitor_status(session: "_PollingSession") -> None:
    """Edit the open '📊 Status' message in-place with fresh stats.

    Called after each poll cycle in _poll_loop.
    Only fires when:
      - session.status_message_id is set (user has the status screen open)
      - the generated text differs from the last sent text (dedup guard)

    Never raises — all errors are silently swallowed so the poll loop
    is never interrupted by a Telegram API hiccup.
    """
    if not session.status_message_id:
        return

    try:
        import time as _t
        from utils.time_utils import get_countdown_line as _get_cd
        from utils.runtime_bot import get_runtime_bot

        _bot = get_runtime_bot()
        if _bot is None:
            return

        lang = session.lang

        # ── Countdown line (may be empty for single/unlimited plans) ──────────
        cd_line = ""
        try:
            from backend.termin_db import get_entitlement as _ge
            _ent = _ge(str(session.user_id))
            _paid_until = (_ent or {}).get("paid_until")
            cd_line = _get_cd(_paid_until, lang)
        except Exception:
            pass

        # ── Build status text via shared helper ───────────────────────────────
        new_text = build_status_text(session, lang, countdown_line=cd_line)
        if not new_text:
            return  # import failed inside build_status_text — skip silently

        # Dedup: skip edit if text hasn't changed (avoids Telegram "not modified" error)
        if new_text == session._last_status_text:
            return

        # Rebuild the status keyboard so it is never lost on live updates.
        # Falls back to hardcoded labels if any import fails — user keeps navigation.
        _kb = None
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            from handlers.termin import _lang_text as _lt2
            from handlers.termin import _BTN_CHANGE_CITY, _BTN_CHANGE_DOC, _PAUSE_BTN, _FILTERS_BTN
            from backend.termin_texts import get_text as _get_text
            _s_city_kb = session.city or "berlin"
            _kb = InlineKeyboardMarkup(row_width=2)
            _kb.row(
                InlineKeyboardButton(_lt2(_BTN_CHANGE_CITY, lang), callback_data="termin_cities"),
                InlineKeyboardButton(_lt2(_BTN_CHANGE_DOC, lang), callback_data=f"termin_city_{_s_city_kb}"),
            )
            _kb.row(
                InlineKeyboardButton(_lt2(_PAUSE_BTN, lang), callback_data="termin_pause"),
                InlineKeyboardButton(_lt2(_FILTERS_BTN, lang), callback_data="termin_filters"),
            )
            _kb.add(InlineKeyboardButton(_get_text("btn_back", lang), callback_data="termin_menu"))
        except Exception as _kb_exc:
            logger.error(
                "TERMIN_STATUS_KEYBOARD_BUILD_FAILED | user=%s err=%s — using hardcoded fallback",
                session.user_id, _kb_exc,
            )
            # Hardcoded fallback: user never loses navigation even if imports break
            try:
                from aiogram.types import InlineKeyboardMarkup as _IKM, InlineKeyboardButton as _IKB
                _s_city_fb = session.city or "berlin"
                _kb = _IKM(row_width=2)
                _kb.row(
                    _IKB("🏙 City", callback_data="termin_cities"),
                    _IKB("📄 Service", callback_data=f"termin_city_{_s_city_fb}"),
                )
                _kb.row(
                    _IKB("⏸ Pause", callback_data="termin_pause"),
                    _IKB("🔧 Filters", callback_data="termin_filters"),
                )
                _kb.add(_IKB("← Back", callback_data="termin_menu"))
            except Exception as _fb_exc:
                logger.error("TERMIN_STATUS_KEYBOARD_FALLBACK_FAILED | user=%s err=%s", session.user_id, _fb_exc)

        await _bot.edit_message_text(
            chat_id=session.chat_id,
            message_id=session.status_message_id,
            text=new_text,
            parse_mode="HTML",
            reply_markup=_kb,
        )
        session._last_status_text = new_text

    except Exception as _upd_exc:
        _exc_str = str(_upd_exc)
        # Telegram returns this when user navigated away / deleted the message
        if "message is not modified" in _exc_str.lower():
            return
        if "message to edit not found" in _exc_str.lower():
            session.status_message_id = None  # stale — stop trying
            return
        if "message can't be edited" in _exc_str.lower():
            session.status_message_id = None
            return
        # Any other error: log at debug level only (non-critical)
        logger.debug("update_monitor_status failed | user=%s err=%s", session.user_id, _upd_exc)
