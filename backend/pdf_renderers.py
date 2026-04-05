# -*- coding: utf-8 -*-
"""
backend/pdf_renderers.py — Centralized renderer registry and thin wrapper classes.

ARCHITECTURE RULE:
  Every doc_type from bot_config/menu_structure.py must appear in DOC_RENDER_MAP.
  The map is the single source of truth for "which engine handles which doc_type".

Render strategies:
  "acroform"      — fill existing AcroForm PDF template via PyMuPDF widget API
  "xfa_builder"   — XFA-only template (cannot be filled); german_form_builder is used instead
  "xfa_overlay"   — XFA-only template used as visual background; user data drawn via coordinate map
  "flat_overlay"  — flat/scanned PDF; overlay via coordinate map or german_form_builder
  "builder_only"  — no physical template; pure german_form_builder output

For PREVIEW:
  All doc_types go through german_form_builder (is_preview=True) — verification-letter layout.
  As of this refactor all 16 menu doc_types are now covered by german_form_builder.

For FINAL:
  Routed by strategy:
    acroform     → _fill_template_pdf_acroform() in pdf_generator
    xfa_builder  → german_form_builder (is_preview=False)
    xfa_overlay  → _fill_template_pdf_overlay() in pdf_generator (official template + coordinate text)
    flat_overlay → _fill_template_pdf() overlay OR german_form_builder
    builder_only → german_form_builder (is_preview=False)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DOC_RENDER_MAP — authoritative doc_type → render strategy
# Source of truth: bot_config/menu_structure.py CATEGORY_DOCS
# ---------------------------------------------------------------------------
DOC_RENDER_MAP: Dict[str, str] = {
    # ── residence ──────────────────────────────────────────────────────────
    "anmeldung":                    "acroform",
    "ummeldung":                    "acroform",
    "wohnungsgeberbestaetigung":    "acroform",
    "abmeldung":                    "acroform",   # 58-field AcroForm (templates/abmeldung/berlin.pdf)
    # ── benefits ───────────────────────────────────────────────────────────
    "wohngeld":                     "acroform",      # 387-field AcroForm (official Bayern Wohngeld Mietzuschuss)
    "kindergeld":                   "builder_only",  # builder path: full 28-field coverage via _DOC_SECTIONS
    "buergergeld":                  "acroform",
    "elterngeld":                   "acroform",
    "unterhaltsvorschuss":          "acroform",
    "kinderzuschlag":               "acroform",
    "bafoeg":                       "acroform",
    "wbs":                          "builder_only",  # 119 AcroForm fields but 0 mapping — builder output until mapped
    # ── housing docs ────────────────────────────────────────────────────────
    "mietbescheinigung":            "acroform",    # 78-field AcroForm (templates/mietbescheinigung/default.pdf)
    # ── family benefits ─────────────────────────────────────────────────────
    "jobcenter":                    "acroform",    # alias of buergergeld (shares JOBCENTER_ACROFORM_MAPPING)
    "kindergeld_anlage":            "acroform",    # 127-field AcroForm (Anlage Kind supplement)
    # ── employment ─────────────────────────────────────────────────────────
    "aufenthaltstitel":             "acroform",       # XFA PDF: AcroForm fill + page rasterization (xfa_flatten path)
    "verpflichtungserklaerung":     "acroform",
    "beschaeftigungserklaerung":    "acroform",
    "ebk":                          "acroform",
    # ── builder-only / flat (no fillable AcroForm fields) ───────────────────
    "verlaengerung_aufenthaltstitel": "builder_only",   # no physical template
    "schulbescheinigung":           "builder_only",     # XFA-only, not fillable
    "aufenthaltserlaubnis_antrag":  "builder_only",     # flat scan, 0 AcroForm fields
    "niederlassungserlaubnis":      "builder_only",     # flat scan, 0 AcroForm fields
}

# ---------------------------------------------------------------------------
# BUILDER_DOCS — authoritative set of doc_types rendered exclusively by
# german_form_builder (form_builder.py).  No template loading, no AcroForm
# fill, no xfa_overlay for any doc in this set.
# ---------------------------------------------------------------------------
BUILDER_DOCS: frozenset = frozenset(
    dt for dt, strategy in DOC_RENDER_MAP.items()
    if strategy in ("builder_only", "xfa_builder")
)


def get_render_strategy(doc_type: str) -> str:
    """Return the render strategy for a doc_type. Falls back to 'builder_only'."""
    return DOC_RENDER_MAP.get((doc_type or "").strip().lower(), "builder_only")


def is_xfa_pdf(path: str) -> bool:
    """
    Return True if the PDF at *path* uses XFA form technology.

    XFA forms have a /XFA key inside the /AcroForm dictionary of the PDF catalog.
    PyMuPDF can fill their underlying AcroForm widgets, but XFA-capable viewers
    (e.g. Adobe Reader) render from the XFA XML stream and ignore those values.
    Use _fill_xfa_overlay() for XFA PDFs to produce a viewer-independent result.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        try:
            # Primary method: navigate catalog → AcroForm → check for /XFA
            # This is O(1) and works regardless of object numbering order.
            cat_xref = doc.pdf_catalog()
            if cat_xref:
                cat_str = doc.xref_object(cat_xref, compressed=False)
                # Extract AcroForm xref from catalog
                import re as _re
                _m = _re.search(r"/AcroForm\s+(\d+)\s+0\s+R", cat_str)
                if _m:
                    acroform_xref = int(_m.group(1))
                    acroform_str = doc.xref_object(acroform_xref, compressed=False)
                    if "/XFA" in acroform_str:
                        logger.info(
                            "is_xfa_pdf: XFA detected via AcroForm xref=%d path=%s",
                            acroform_xref, path,
                        )
                        return True

            # Fallback: scan all objects (covers inline AcroForm dicts)
            for xref in range(1, doc.xref_length()):
                try:
                    obj_str = doc.xref_object(xref, compressed=False)
                    if "/XFA" in obj_str:
                        logger.info(
                            "is_xfa_pdf: XFA detected via full scan xref=%d path=%s",
                            xref, path,
                        )
                        return True
                except Exception:
                    continue
        finally:
            doc.close()
    except Exception as _e:
        logger.debug("is_xfa_pdf check failed for %s: %s", path, _e)
    return False


def is_acroform_doc(doc_type: str) -> bool:
    return get_render_strategy(doc_type) == "acroform"


def is_builder_doc(doc_type: str) -> bool:
    return get_render_strategy(doc_type) in ("builder_only", "xfa_builder")


def is_xfa_overlay_doc(doc_type: str) -> bool:
    return get_render_strategy(doc_type) == "xfa_overlay"


# ---------------------------------------------------------------------------
# Thin renderer wrapper classes
# These classes wrap the existing functions — no logic is duplicated.
# ---------------------------------------------------------------------------

class PreviewRenderer:
    """
    Preview renderer — wraps german_form_builder with is_preview=True.
    Produces verification-letter layout for ALL doc_types.
    Do NOT call create_final_pdf from here.
    """

    def render(
        self,
        doc_type: str,
        user_data: Dict[str, Any],
        output_path: str,
        user_lang: str = "en",
        missing_fields: Optional[list] = None,
        warnings: Optional[list] = None,
    ) -> Optional[str]:
        try:
            from backend.form_builder import build_german_form, supported_doc_types
            if doc_type not in supported_doc_types():
                logger.warning(
                    "PreviewRenderer: doc_type=%s not in german_form_builder; "
                    "check that it was added to _DOC_META", doc_type
                )
                return None
            return build_german_form(
                doc_type=doc_type,
                user_data=user_data,
                output_path=output_path,
                is_preview=True,
                user_lang=user_lang or "de",
                missing_fields=missing_fields or [],
                warnings=warnings or [],
            )
        except Exception as exc:
            logger.error("PreviewRenderer.render failed: doc_type=%s error=%s", doc_type, exc, exc_info=True)
            return None


class FinalRenderer:
    """
    Final renderer for builder_only / xfa_builder doc_types.
    Wraps german_form_builder with is_preview=False.
    Never applies a preview watermark.
    """

    def render(
        self,
        doc_type: str,
        user_data: Dict[str, Any],
        output_path: str,
        user_lang: str = "en",
        official_link: str = "",
    ) -> Optional[str]:
        try:
            from backend.form_builder import build_german_form, supported_doc_types
            if doc_type not in supported_doc_types():
                logger.warning(
                    "FinalRenderer: doc_type=%s not in german_form_builder", doc_type
                )
                return None
            return build_german_form(
                doc_type=doc_type,
                user_data=user_data,
                output_path=output_path,
                is_preview=False,
                user_lang=user_lang or "de",
                official_link=official_link,
            )
        except Exception as exc:
            logger.error("FinalRenderer.render failed: doc_type=%s error=%s", doc_type, exc, exc_info=True)
            return None


class AcroFormRenderer:
    """
    Final renderer for AcroForm / flat_overlay doc_types.
    Wraps the existing _fill_template_pdf_acroform / _fill_template_pdf pipeline in pdf_generator.
    Does NOT use german_form_builder (that is handled by FinalRenderer above).
    """

    def render(
        self,
        doc_type: str,
        user_data: Dict[str, Any],
        output_path: str,
        template_path,
        user_lang: str = "en",
        authority_info: Optional[Dict[str, Any]] = None,
        is_preview: bool = False,
    ) -> Optional[str]:
        try:
            from backend.pdf_generator import (
                _fill_template_pdf_acroform,
                _fill_template_pdf,
            )
            from pathlib import Path
            result = _fill_template_pdf_acroform(
                Path(template_path),
                user_data,
                doc_type,
                Path(output_path),
                is_preview=is_preview,
                user_lang=user_lang,
                authority_info=authority_info,
            )
            if result:
                return result
            # Flat/overlay fallback for non-AcroForm templates
            logger.info(
                "AcroFormRenderer: AcroForm returned None for %s — trying overlay", doc_type
            )
            return _fill_template_pdf(
                Path(template_path),
                user_data,
                doc_type,
                Path(output_path),
                is_preview=is_preview,
                user_lang=user_lang,
                authority_info=authority_info,
            )
        except Exception as exc:
            logger.error("AcroFormRenderer.render failed: doc_type=%s error=%s", doc_type, exc, exc_info=True)
            return None


# ---------------------------------------------------------------------------
# Module-level singleton instances for convenience
# ---------------------------------------------------------------------------
preview_renderer = PreviewRenderer()
final_renderer = FinalRenderer()
acroform_renderer = AcroFormRenderer()
