# -*- coding: utf-8 -*-
"""
backend/pdf_preview.py
──────────────────────────────────────────────────────────────────────────────
Generates a PNG "snippet" preview from the REAL official PDF template.

The snippet is cropped around first_name / last_name / birth_date fields —
the user sees their actual data on the government form before paying.

Unlike create_preview() which produces an unofficial review sheet,
this function renders a piece of the real Behörde form with the
user's own name/surname/date already filled in.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import fitz  # PyMuPDF

    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False
    logger.warning(
        "pdf_preview: PyMuPDF (fitz) not available — template snippet preview disabled"
    )

# ── Rendering config ──────────────────────────────────────────────────────────
_PREVIEW_DPI = 150          # higher → better quality but larger file
_FIELD_PADDING_PT = 65      # extra space around the identity fields (PDF points)
_FALLBACK_TOP_FRACTION = 0.42  # fraction of page height used when no widgets found

# ── Watermark strip ───────────────────────────────────────────────────────────
_WATERMARK_TEXTS: Dict[str, str] = {
    "de": "🔒 Vorschau — vollständiges Dokument nach der Zahlung verfügbar",
    "en": "🔒 Preview — full document available after payment",
    "uk": "🔒 Перегляд — повний документ доступний після оплати",
    "pl": "🔒 Podgląd — pełny dokument dostępny po płatności",
    "tr": "🔒 Önizleme — ödeme sonrası tam belge mevcut",
    "ar": "🔒 معاينة — المستند الكامل متاح بعد الدفع",
}
_STRIP_HEIGHT_PT = 22   # height of the watermark strip in PDF points
_STRIP_COLOR = (0.08, 0.22, 0.48)   # dark blue
_STRIP_TEXT_COLOR = (1.0, 1.0, 1.0)  # white
_STRIP_FONTSIZE = 8.5

# ── Identity field keys used to locate the crop region ───────────────────────
# These user-data keys map to the PDF widget names we look for.
_IDENTITY_USER_KEYS = (
    "first_name",
    "last_name",
    "birth_date",
    "birth_date_place",
)


def _get_identity_pdf_names(doc_type: str) -> List[str]:
    """
    Return the list of PDF AcroForm field names that correspond to
    first_name / last_name / birth_date for the given doc_type.
    """
    try:
        from backend.document_config import get_acroform_mapping

        mapping = get_acroform_mapping(doc_type) or {}
    except Exception:
        return []

    names: List[str] = []
    for key in _IDENTITY_USER_KEYS:
        pdf_name = mapping.get(key)
        if pdf_name and pdf_name not in names:
            names.append(str(pdf_name))
    return names


def _fill_widgets(
    doc: "fitz.Document",
    doc_type: str,
    user_data: Dict[str, Any],
) -> None:
    """Fill all AcroForm widgets in *doc* using the doc_type mapping."""
    try:
        from backend.document_config import get_acroform_mapping, get_value_for_pdf_field

        mapping = get_acroform_mapping(doc_type) or {}
    except Exception:
        return

    field_values: Dict[str, str] = {}
    for user_key, pdf_name in mapping.items():
        try:
            val = get_value_for_pdf_field(user_key, user_data)
            if val:
                field_values[str(pdf_name)] = str(val)
        except Exception:
            pass

    if not field_values:
        return

    for page in doc:
        page_changed = False
        for widget in page.widgets():
            fname = widget.field_name or ""
            if fname in field_values:
                try:
                    widget.field_value = field_values[fname]
                    widget.update()
                    page_changed = True
                except Exception:
                    pass
        # Flush page content so get_pixmap() renders updated field values
        if page_changed:
            try:
                page.clean_contents()
            except Exception:
                pass


def _find_clip(
    doc: "fitz.Document",
    identity_pdf_names: List[str],
) -> Tuple["fitz.Page", "fitz.Rect"]:
    """
    Locate the page and bounding rect that best shows the filled fields.

    Priority:
      1. Page that contains identity fields (name / birth_date)
      2. First page that contains ANY AcroForm widgets (skips instruction pages)
      3. Top fraction of first page with widgets by widget count (last resort)
    """
    # ── Priority 1: page with identity fields ─────────────────────────────────
    if identity_pdf_names and doc.page_count:
        for page in doc:
            boxes: List["fitz.Rect"] = []
            for widget in page.widgets():
                if widget.field_name in identity_pdf_names:
                    boxes.append(fitz.Rect(widget.rect))

            if boxes:
                union: "fitz.Rect" = boxes[0]
                for r in boxes[1:]:
                    union = union | r

                pr = page.rect
                clip = fitz.Rect(
                    max(0.0, union.x0 - _FIELD_PADDING_PT),
                    max(0.0, union.y0 - _FIELD_PADDING_PT),
                    min(pr.width, union.x1 + _FIELD_PADDING_PT),
                    min(pr.height, union.y1 + _FIELD_PADDING_PT),
                )
                logger.debug(
                    "pdf_preview: identity fields found on page %d clip=%s",
                    page.number, tuple(round(v) for v in clip),
                )
                return page, clip

    # ── Priority 2: first page that has ANY widgets (skips instruction pages) ─
    best_page = None
    best_count = 0
    for page in doc:
        widgets = list(page.widgets())
        if not widgets:
            continue
        if best_page is None:
            # First page with widgets — use it directly
            pr = page.rect
            all_boxes = [fitz.Rect(w.rect) for w in widgets]
            union = all_boxes[0]
            for r in all_boxes[1:]:
                union = union | r
            clip = fitz.Rect(
                0,
                max(0.0, union.y0 - _FIELD_PADDING_PT),
                pr.width,
                min(pr.height, union.y1 + _FIELD_PADDING_PT),
            )
            logger.debug(
                "pdf_preview: no identity fields — using first widget page %d "
                "(%d widgets) clip=%s",
                page.number, len(widgets), tuple(round(v) for v in clip),
            )
            return page, clip
        if len(widgets) > best_count:
            best_page = page
            best_count = len(widgets)

    # ── Priority 3: absolute fallback — top portion of first page ─────────────
    logger.debug("pdf_preview: no widgets found anywhere — using top of page 0")
    page = doc[0]
    pr = page.rect
    return page, fitz.Rect(0, 0, pr.width, pr.height * _FALLBACK_TOP_FRACTION)


def _draw_watermark(
    page: "fitz.Page",
    clip: "fitz.Rect",
    lang: str,
) -> None:
    """
    Draw a filled watermark bar at the bottom of *clip* directly on the page
    (in memory, before rendering — the doc is never saved to disk).
    """
    text = _WATERMARK_TEXTS.get(lang) or _WATERMARK_TEXTS["en"]
    strip = fitz.Rect(
        clip.x0,
        clip.y1 - _STRIP_HEIGHT_PT,
        clip.x1,
        clip.y1,
    )
    page.draw_rect(strip, color=_STRIP_COLOR, fill=_STRIP_COLOR, overlay=True)
    page.insert_text(
        fitz.Point(clip.x0 + 6, clip.y1 - 7),
        text,
        fontsize=_STRIP_FONTSIZE,
        color=_STRIP_TEXT_COLOR,
        overlay=True,
    )


def _choose_kiz_preview_page(
    doc: "fitz.Document",
    user_data: Dict[str, Any],
) -> Tuple["fitz.Page", "fitz.Rect"]:
    """Pick the first KIZ builder/final page that actually contains user-visible values."""
    search_terms: List[str] = []
    for key in (
        "first_name",
        "last_name",
        "street",
        "house_number",
        "postal_code",
        "city",
        "iban",
        "child1_first_name",
        "child1_last_name",
        "partner_first_name",
        "partner_last_name",
    ):
        raw = str(user_data.get(key) or "").strip()
        if raw and len(raw) >= 2:
            search_terms.append(raw.lower())

    best_page_index = 0
    best_score = -1
    for page_index in range(doc.page_count):
        page = doc[page_index]
        try:
            page_text = (page.get_text("text") or "").lower()
        except Exception:
            page_text = ""
        score = sum(1 for term in search_terms if term in page_text)
        if score > best_score:
            best_score = score
            best_page_index = page_index

    if best_score <= 0 and doc.page_count > 1:
        best_page_index = 1

    page = doc[best_page_index]
    logger.info(
        "pdf_preview: KIZ final-page selected page=%d score=%d",
        best_page_index,
        best_score,
    )
    return page, fitz.Rect(0, 0, page.rect.width, page.rect.height)


def create_template_snippet_image(
    doc_type: str,
    user_data: Dict[str, Any],
    lang: str = "de",
    bundesland: Optional[str] = None,
) -> Optional[bytes]:
    """
    Render a PNG snippet of the REAL official PDF template filled with
    *user_data* (first_name / last_name / birth_date area).

    Returns raw PNG bytes on success, **None** on any failure so the caller
    can safely fall back to the existing unofficial preview sheet.

    The returned image is never saved to disk — all operations are in-memory.
    """
    if not _FITZ_AVAILABLE:
        return None

    internal_doc_type = "kinderzuschlag" if doc_type == "kiz" else doc_type

    if internal_doc_type == "kinderzuschlag":
        _kiz_pdf_path: Optional[str] = None
        _kiz_doc = None
        try:
            from backend.pdf_generator import create_final_pdf

            _kiz_user_id = int(user_data.get("user_id") or user_data.get("uid") or 0)
            _kiz_result = create_final_pdf(
                user_id=_kiz_user_id,
                user_data=dict(user_data),
                doc_type=doc_type,
                authority_info=None,
                user_lang=lang or "de",
            )
            if not isinstance(_kiz_result, str) or not Path(_kiz_result).exists():
                logger.warning(
                    "pdf_preview: KIZ final PDF generation failed for snippet (result=%r)",
                    _kiz_result,
                )
                return None
            _kiz_pdf_path = _kiz_result
            _kiz_doc = fitz.open(_kiz_pdf_path)
            try:
                target_page, clip_rect = _choose_kiz_preview_page(_kiz_doc, user_data)
                _draw_watermark(target_page, clip_rect, lang)
                matrix = fitz.Matrix(_PREVIEW_DPI / 72.0, _PREVIEW_DPI / 72.0)
                pix = target_page.get_pixmap(matrix=matrix, clip=clip_rect)
            except Exception as _kiz_page_exc:
                logger.warning(
                    "pdf_preview: KIZ preview-page heuristic failed, using full page fallback (%s)",
                    _kiz_page_exc,
                )
                _fallback_index = 1 if _kiz_doc.page_count > 1 else 0
                target_page = _kiz_doc[_fallback_index]
                clip_rect = fitz.Rect(0, 0, target_page.rect.width, target_page.rect.height)
                _draw_watermark(target_page, clip_rect, lang)
                matrix = fitz.Matrix(_PREVIEW_DPI / 72.0, _PREVIEW_DPI / 72.0)
                pix = target_page.get_pixmap(matrix=matrix, clip=clip_rect)

            png_bytes: bytes = pix.tobytes("png")
            logger.info(
                "pdf_preview: KIZ final PDF snippet OK page=%d size=%d B",
                target_page.number,
                len(png_bytes),
            )
            return png_bytes
        except Exception as _kiz_exc:
            logger.warning(
                "pdf_preview: KIZ final PDF snippet failed (%s)",
                _kiz_exc,
                exc_info=True,
            )
            return None
        finally:
            if _kiz_doc is not None:
                try:
                    _kiz_doc.close()
                except Exception:
                    pass
            if _kiz_pdf_path:
                try:
                    Path(_kiz_pdf_path).unlink(missing_ok=True)
                except Exception:
                    pass

    try:
        from backend.document_config import has_template, resolve_template_path
    except Exception as exc:
        logger.debug("pdf_preview: import error: %s", exc)
        return None

    if not has_template(internal_doc_type):
        logger.debug(
            "pdf_preview: doc_type=%r has no template (builder-only) — skipped",
            doc_type,
        )
        return None

    # Resolve the templates directory the same way pdf_generator.py does
    _root = Path(__file__).resolve().parent.parent
    _templates_dir = _root / "templates"
    _legacy_dir = _root / "backend" / "templates"

    template_path = resolve_template_path(internal_doc_type, bundesland, _templates_dir, _legacy_dir)
    if not template_path or not Path(template_path).exists():
        logger.debug(
            "pdf_preview: template not found doc_type=%r bundesland=%r",
            doc_type,
            bundesland,
        )
        return None

    # Normalize user_data (clean names, dates, etc.)
    normalized = dict(user_data)
    try:
        from backend.utils.normalize import normalize_user_data

        normalized = normalize_user_data(normalized)
    except Exception:
        pass

    try:
        doc = fitz.open(str(template_path))
    except Exception as exc:
        logger.warning("pdf_preview: cannot open template %r: %s", template_path, exc)
        return None

    try:
        # 1. Fill all widgets with user data
        _fill_widgets(doc, internal_doc_type, normalized)

        # 2. Find the crop area around identity fields
        identity_names = _get_identity_pdf_names(internal_doc_type)

        # kinderzuschlag: the applicant's name is assembled as a composite field
        # (kiz_header_name) so _find_clip can't locate individual identity widgets.
        # The result is a random mid-form crop.  Override with a fixed top slice of
        # page 0 where the header (name / Familienkasse / address) always lives.
        if doc_type == "kiz":
            target_page = doc[0]
            page_rect = target_page.rect
            clip_rect = fitz.Rect(0, 0, page_rect.width, page_rect.height * 0.55)
        elif internal_doc_type == "kinderzuschlag":
            # The KIZ template is XFA — _fill_widgets() does nothing and the
            # rendered page never contains user data.  Instead, use the same
            # builder that create_preview() uses: it produces a verification
            # sheet with user data already embedded.  Render page 0 of that
            # builder PDF as the snippet PNG and return immediately.
            import os as _os
            import tempfile as _tempfile
            try:
                from backend.form_builder import build_german_form, supported_doc_types
                if "kinderzuschlag" not in supported_doc_types():
                    logger.warning("pdf_preview: kinderzuschlag not in form_builder — skipping snippet")
                    return None
                with _tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as _tf:
                    _tmp = _tf.name
                try:
                    _built_path = build_german_form(
                        doc_type="kinderzuschlag",
                        user_data=normalized,
                        output_path=_tmp,
                        is_preview=True,
                        user_lang=lang or "de",
                        missing_fields=[],
                        warnings=[],
                    )
                    if not _built_path or not Path(_built_path).exists():
                        logger.warning("pdf_preview: kinderzuschlag builder returned no PDF")
                        return None
                    _bdoc = fitz.open(_built_path)
                    try:
                        _bpage = _bdoc[0]
                        _bpr = _bpage.rect
                        # Show top half — builder layout always places name/fields there
                        _bclip = fitz.Rect(0, 0, _bpr.width, _bpr.height * 0.55)
                        _draw_watermark(_bpage, _bclip, lang)
                        _bmatrix = fitz.Matrix(_PREVIEW_DPI / 72.0, _PREVIEW_DPI / 72.0)
                        _bpix = _bpage.get_pixmap(matrix=_bmatrix, clip=_bclip)
                        _bpng: bytes = _bpix.tobytes("png")
                        logger.info(
                            "pdf_preview: kinderzuschlag builder snippet OK size=%d B", len(_bpng)
                        )
                        return _bpng
                    finally:
                        _bdoc.close()
                finally:
                    try:
                        _os.unlink(_tmp)
                    except Exception:
                        pass
            except Exception as _kiz_exc:
                logger.warning(
                    "pdf_preview: kinderzuschlag builder snippet failed (%s) — returning None",
                    _kiz_exc,
                )
                return None
        elif internal_doc_type == "wohnungsgeberbestaetigung":
            target_page = doc[0]
            clip_rect = fitz.Rect(
                0,
                0,
                target_page.rect.width,
                target_page.rect.height * 0.55,
            )
        else:
            target_page, clip_rect = _find_clip(doc, identity_names)

        # 3. Draw watermark strip (in-memory mutation, never saved)
        _draw_watermark(target_page, clip_rect, lang)

        # 4. Render clip to PNG
        matrix = fitz.Matrix(_PREVIEW_DPI / 72.0, _PREVIEW_DPI / 72.0)
        pix = target_page.get_pixmap(matrix=matrix, clip=clip_rect)
        png_bytes: bytes = pix.tobytes("png")

        logger.info(
            "pdf_preview: OK doc_type=%r page=%d clip=%s size=%d B",
            doc_type,
            target_page.number,
            tuple(round(v) for v in clip_rect),
            len(png_bytes),
        )
        return png_bytes

    except Exception as exc:
        logger.warning(
            "pdf_preview: error rendering snippet doc_type=%r: %s",
            doc_type,
            exc,
            exc_info=True,
        )
        return None

    finally:
        try:
            doc.close()
        except Exception:
            pass
