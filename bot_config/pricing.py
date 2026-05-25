# -*- coding: utf-8 -*-
"""
bot_config/pricing.py — Single source of truth for all PDF document prices.

ALL pricing for PDF documents must be defined here and only here.
backend/pricing.py, backend/settings.py, and backend/stripe_handler.py
all import from this file — never the other way around.

Termin pricing lives in handlers/termin.py and utils/termin_checker.py.
Do NOT mix them here.
"""
from __future__ import annotations
from typing import Dict

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical PDF price table — THE single source of truth.
# Tier comments are informational only; pricing is intentionally flat-friendly
# to maximise conversion with a price-sensitive audience.
# ---------------------------------------------------------------------------
PDF_PRICES: Dict[str, float] = {
    # Simple (€2.99–€3.99) — straightforward filler forms, no conditions
    "abmeldung":                    2.99,
    "wohnungsgeberbestaetigung":    3.99,
    "wbs":                          3.99,
    "mietbescheinigung":            3.99,

    # Standard tier 1 (€4.99) — multi-section forms, no complex logic
    "ummeldung":                    4.99,
    "unterhaltsvorschuss":          4.99,
    "kinderzuschlag":               4.99,
    "ebk":                          5.99,

    # Standard tier 2 (€5.99–€6.99) — core high-frequency documents
    "anmeldung":                    5.99,
    "wohngeld":                     5.99,
    "elterngeld":                   5.99,
    "kindergeld":                   6.99,
    "bafoeg":                       6.99,

    # Complex (€7.99) — multi-section, conditional logic, legal documents
    "buergergeld":                  7.99,
    "verpflichtungserklaerung":     7.99,
    "aufenthaltstitel":             7.99,

    # Additional documents — standard tier
    "beschaeftigungserklaerung":    5.99,
}

# Backward-compatibility alias — existing imports of DEFAULT_PRICES keep working.
DEFAULT_PRICES: Dict[str, float] = PDF_PRICES


def get_prices() -> Dict[str, float]:
    """Return {doc_type: price_float} for all registered documents.

    Primary source: live PricingManager (DB).
    Fallback: PDF_PRICES (this file).
    """
    try:
        from handlers.docs_new import _get_doc_prices
        result = _get_doc_prices()
        if result:
            # Merge — DB values win, but every key in PDF_PRICES is always present.
            merged = dict(PDF_PRICES)
            merged.update(result)
            return merged
    except Exception:
        pass
    return dict(PDF_PRICES)


def get_price(doc_type: str) -> float:
    """Return the price for *doc_type*.

    Raises ValueError if the document type is unknown so the caller is
    forced to handle the error explicitly.  Never returns 0.0 — that would
    allow free Stripe charges to slip through silently.
    """
    price = PDF_PRICES.get(doc_type)
    if price is None:
        logger.error("PRICE_MISSING_CRITICAL: doc_type=%r not in PDF_PRICES", doc_type)
        raise ValueError(f"Price not found for doc_type={doc_type!r}. Add it to bot_config/pricing.py → PDF_PRICES.")
    return price
