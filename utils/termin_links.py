# -*- coding: utf-8 -*-
"""
utils/termin_links.py — Single helper for building deep booking links.

Returns {"primary": ..., "fallback": ...} so Telegram and Email always use
the same URLs without duplicating city logic.

Priority model for primary URL:
  A  slot["direct_url"]   — TeVIS select2?md=N, set by tevis_scraper
  B  city+uid deep link   — Köln calendar direct (when uid present in slot)
  C  city+serviceId       — München direct appointment page with service pre-selected
  D  slot["url"]          — generic URL set by each city checker
  E  authority deep link  — _AUTHORITY_DEEP_LINKS[city][service] — lands on correct service page
  F  city portal root     — known portal per city
  G  generic gov fallback — last resort

Fallback URL is always the city portal root (or G if city unknown).
"""
from __future__ import annotations
import logging as _logging

_logger = _logging.getLogger(__name__)

_CITY_PORTALS: dict[str, str] = {
    "berlin":      "https://service.berlin.de/terminvereinbarung/",
    "frankfurt":   "https://tevis.ekom21.de/fra/",
    "duesseldorf": "https://termine.duesseldorf.de/",
    "dusseldorf":  "https://termine.duesseldorf.de/",
    "düsseldorf":  "https://termine.duesseldorf.de/",
    "koeln":       "https://tevis.krzn.de/tevisweb190/",
    "cologne":     "https://tevis.krzn.de/tevisweb190/",
    "krefeld":     "https://tevis.krzn.de/tevisweb350/",
    "muenchen":    "https://www48.muenchen.de/buergeransicht/",
    "munich":      "https://www48.muenchen.de/buergeransicht/",
    "münchen":     "https://www48.muenchen.de/buergeransicht/",
    "dortmund":    "https://dortmund.termine-reservieren.de/",
    "hamburg":     "https://serviceportal.hamburg.de/HamburgGateway/Service/Entry/DigiTermin",
}

# Authority-specific deep links — skip the homepage and land on the correct
# service page directly. Keyed by (city, authority_type).
# Used as the primary URL when the scraper slot has no direct_url / uid / serviceId.
_AUTHORITY_DEEP_LINKS: dict[str, dict[str, str]] = {
    "berlin": {
        "buergeramt":              "https://service.berlin.de/terminvereinbarung/termin/all/120686/?termin=1",
        "anmeldung":               "https://service.berlin.de/terminvereinbarung/termin/all/120686/?termin=1",
        "auslaenderbehoerde":      "https://otv.verwalt-berlin.de/ams/TerminBuchen",
        "aufenthaltstitel":        "https://otv.verwalt-berlin.de/ams/TerminBuchen",
        "niederlassungserlaubnis": "https://otv.verwalt-berlin.de/ams/TerminBuchen",
        "fuehrerschein":           "https://service.berlin.de/terminvereinbarung/termin/all/325326/?termin=1",
        "personalausweis":         "https://service.berlin.de/terminvereinbarung/termin/all/121151/?termin=1",
        "reisepass":               "https://service.berlin.de/terminvereinbarung/termin/all/121921/?termin=1",
    },
    "frankfurt": {
        "buergeramt":              "https://tevis.ekom21.de/fra/select2?md=13",
        "anmeldung":               "https://tevis.ekom21.de/fra/select2?md=13",
        "personalausweis":         "https://tevis.ekom21.de/fra/select2?md=13",
        "reisepass":               "https://tevis.ekom21.de/fra/select2?md=13",
        "auslaenderbehoerde":      "https://tevis.ekom21.de/fra/select2?md=5",
        "aufenthaltstitel":        "https://tevis.ekom21.de/fra/select2?md=5",
        "niederlassungserlaubnis": "https://tevis.ekom21.de/fra/select2?md=5",
        "fuehrerschein":           "https://tevis.ekom21.de/fra/select2?md=6",
    },
    "duesseldorf": {
        "buergeramt":              "https://termine.duesseldorf.de/select2?md=4",
        "anmeldung":               "https://termine.duesseldorf.de/select2?md=4",
        "personalausweis":         "https://termine.duesseldorf.de/select2?md=4",
        "reisepass":               "https://termine.duesseldorf.de/select2?md=4",
        "auslaenderbehoerde":      "https://termine.duesseldorf.de/select2?md=1",
        "aufenthaltstitel":        "https://termine.duesseldorf.de/select2?md=1",
        "niederlassungserlaubnis": "https://termine.duesseldorf.de/select2?md=1",
        "fuehrerschein":           "https://termine.duesseldorf.de/select2?md=3",
    },
    "muenchen": {
        "personalausweis":         "https://www48.muenchen.de/buergeransicht/?serviceId=1063441",
        "reisepass":               "https://www48.muenchen.de/buergeransicht/?serviceId=1063453",
        "buergeramt":              "https://www48.muenchen.de/buergeransicht/?serviceId=1063475",
        "anmeldung":               "https://www48.muenchen.de/buergeransicht/?serviceId=1063475",
        "auslaenderbehoerde":      "https://www48.muenchen.de/buergeransicht/?serviceId=1063475",
        "aufenthaltstitel":        "https://www48.muenchen.de/buergeransicht/?serviceId=1063475",
        "niederlassungserlaubnis": "https://www48.muenchen.de/buergeransicht/?serviceId=1063475",
    },
    "dortmund": {
        "buergeramt":              "https://dortmund.termine-reservieren.de/select2?md=3",
        "auslaenderbehoerde":      "https://dortmund.termine-reservieren.de/select2?md=3",
        "aufenthaltstitel":        "https://dortmund.termine-reservieren.de/select2?md=3",
        "niederlassungserlaubnis": "https://dortmund.termine-reservieren.de/select2?md=3",
        "personalausweis":         "https://dortmund.termine-reservieren.de/select2?md=3",
    },
    "koeln": {
        "buergeramt":              "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "anmeldung":               "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "ummeldung":               "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "abmeldung":               "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "personalausweis":         "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "reisepass":               "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "auslaenderbehoerde":      "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "aufenthaltstitel":        "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "niederlassungserlaubnis": "https://tevis.krzn.de/tevisweb190/select2?md=1",
        "fuehrerschein":           "https://tevis.krzn.de/tevisweb190/select2?md=1",
    },
    "krefeld": {
        "buergeramt":              "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "anmeldung":               "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "ummeldung":               "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "abmeldung":               "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "personalausweis":         "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "reisepass":               "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "auslaenderbehoerde":      "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "aufenthaltstitel":        "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "niederlassungserlaubnis": "https://tevis.krzn.de/tevisweb350/select2?md=10",
        "fuehrerschein":           "https://tevis.krzn.de/tevisweb350/select2?md=10",
    },
}
_GENERIC_FALLBACK = (
    "https://www.germany.info/us-de/service/termine/termin-vereinbarung/2530996"
)


def build_booking_links(city: str, service: str, slot: dict) -> dict:
    """Return {"primary": <deepest link>, "fallback": <portal root>}.

    Never raises — all failures silently return the generic fallback.

    Args:
        city:    Normalised city code (e.g. "frankfurt", "koeln").
        service: Authority / service string (informational, used for logging).
        slot:    Slot dict produced by the city checker (may carry url,
                 direct_url, uid, serviceId, etc.).

    Returns:
        dict with keys "primary" and "fallback" (both non-empty strings).
    """
    city_key = (city or "").lower().strip()

    # ── A: TeVIS select2 direct link (Frankfurt, Düsseldorf, Krefeld …) ──────
    primary = (slot.get("direct_url") or "").strip()

    # ── B: Köln calendar deep link (uid field present) ────────────────────────
    if not primary and city_key in ("koeln", "cologne"):
        uid = slot.get("uid", "")
        if uid:
            primary = f"https://termine.stadt-koeln.de/calendar?uid={uid}"

    # ── C: München direct appointment page with service pre-selected ─────────
    if not primary and city_key in ("muenchen", "munich", "münchen"):
        sid = slot.get("serviceId", "")
        if sid:
            primary = f"https://www48.muenchen.de/buergeransicht/?serviceId={sid}"
            _logger.info("BOOKING_URL_FIXED | city=%s url=%s", city_key, primary)

    # ── D: generic slot url field ─────────────────────────────────────────────
    if not primary:
        primary = (slot.get("url") or "").strip()

    # ── E: authority-specific deep link (service page, not homepage) ──────────
    service_key = (service or "").lower().strip()
    if not primary and service_key:
        _auth_map = _AUTHORITY_DEEP_LINKS.get(city_key, {})
        _deep = _auth_map.get(service_key, "")
        if _deep:
            primary = _deep
            _logger.info("BOOKING_URL_AUTHORITY | city=%s service=%s url=%s", city_key, service_key, primary)

    # ── F: city portal root as fallback ───────────────────────────────────────
    fallback = _CITY_PORTALS.get(city_key) or (slot.get("url") or "").strip()
    if not fallback:
        fallback = _GENERIC_FALLBACK

    # If we still have no primary, use the fallback
    if not primary:
        primary = fallback

    return {"primary": primary, "fallback": fallback}
