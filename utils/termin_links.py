# -*- coding: utf-8 -*-
"""
utils/termin_links.py — Single helper for building deep booking links.

Returns {"primary": ..., "fallback": ...} so Telegram and Email always use
the same URLs without duplicating city logic.

Priority model for primary URL:
  A  slot["direct_url"]   — TeVIS select2?md=N, set by tevis_scraper
  B  city+uid deep link   — Köln calendar direct (when uid present in slot)
  C  city+serviceId       — München service-specific API page
  D  slot["url"]          — generic URL set by each city checker
  E  city portal root     — known portal per city
  F  generic gov fallback — last resort

Fallback URL is always the city portal root (or F if city unknown).
"""
from __future__ import annotations

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

    # ── C: München service API link (serviceId field present) ─────────────────
    if not primary and city_key in ("muenchen", "munich", "münchen"):
        sid = slot.get("serviceId", "")
        if sid:
            primary = (
                f"https://www48.muenchen.de/buergeransicht/api/citizen/"
                f"offices-and-services/?serviceId={sid}"
            )

    # ── D: generic slot url field ─────────────────────────────────────────────
    if not primary:
        primary = (slot.get("url") or "").strip()

    # ── E/F: city portal root as fallback ─────────────────────────────────────
    fallback = _CITY_PORTALS.get(city_key) or (slot.get("url") or "").strip()
    if not fallback:
        fallback = _GENERIC_FALLBACK

    # If we still have no primary, use the fallback
    if not primary:
        primary = fallback

    return {"primary": primary, "fallback": fallback}
