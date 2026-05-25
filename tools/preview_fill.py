# -*- coding: utf-8 -*-
"""
tools/preview_fill.py

Fill official German PDF template with user data and add a red
"PREVIEW – NOT AN OFFICIAL DOCUMENT" watermark on every page.

Strategy:
  1. Open official PDF from /templates/ — no layout changes.
  2. Fill AcroForm fields if present (fallback: coordinate overlay in
     existing blank input zones identified from the real template).
  3. Stamp red semi-transparent watermark on every page.

Usage:
  python tools/preview_fill.py
"""

import math
import sys
from pathlib import Path

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Sample user data
# ---------------------------------------------------------------------------
USER_DATA = {
    "last_name":          "Müller",
    "first_name":         "Hans Peter",
    "birth_name":         "",
    "birth_date":         "01.01.1985",
    "birth_place":        "Wien",
    "birth_country":      "Österreich",
    "gender":             "männlich",        # männlich | weiblich | unbekannt
    "nationality":        "österreichisch",
    "dokument_type":      "Reisepass",
    "dokument_nr":        "XY123456",
    "dokument_issued_on": "15.06.2020",
    "dokument_issued_by": "Magistrat Wien",
    "dokument_valid":     "15.06.2030",
    "entry_date":         "01.03.2022",
    "city":               "Berlin",
    "street":             "Hauptstraße 12",
    "employer":           "Tech GmbH",
    "purpose":            "Arbeit",
    "phone":              "+49 152 123456",
    "signature_place":    "Berlin",
    "signature_date":     "22.03.2026",
}

TEMPLATE = Path(__file__).parent.parent / "templates" / "aufenthaltserlaubnis_antrag" / "berlin.pdf"
OUTPUT   = Path(__file__).parent.parent / "outputs" / "aufenthaltstitel_preview.pdf"


# ---------------------------------------------------------------------------
# Coordinate overlay map
# Positions extracted directly from the official PDF text blocks.
# Each entry: (page, x, y_bottom, field_key)
# y_bottom = baseline of text insertion (placed just above the printed label)
# ---------------------------------------------------------------------------
OVERLAY: list[tuple[int, float, float, str]] = [
    # PAGE 0 — Personal data
    (0,  51.0,  89.0,  "last_name"),
    (0,  51.0, 111.0,  "birth_name"),
    (0,  51.0, 133.0,  "first_name"),
    (0,  51.0, 155.0,  "birth_date"),
    (0,  51.0, 177.0,  "birth_place"),
    (0,  51.0, 199.0,  "birth_country"),
    # nationality (jetzige) — below "a) jetzige" at y=307.8
    (0,  51.0, 304.0,  "nationality"),
    # Travel document
    (0,  51.0, 392.0,  "dokument_type"),
    (0,  51.0, 433.0,  "dokument_nr"),
    (0,  51.0, 455.0,  "dokument_issued_on"),
    (0,  51.0, 477.0,  "dokument_issued_by"),
    (0,  51.0, 499.0,  "dokument_valid"),

    # PAGE 1 — Address & entry
    (1, 150.0, 559.0,  "entry_date"),
    (1, 285.0, 656.0,  "city"),
    (1, 285.0, 685.0,  "street"),
    (1,  51.0, 744.0,  "phone"),

    # PAGE 2 — Purpose & employer
    (2,  51.0,  62.0,  "purpose"),
    (2,  51.0, 116.0,  "employer"),

    # PAGE 3 — Signature
    (3, 134.0, 661.0,  "signature_place"),
    (3, 280.0, 661.0,  "signature_date"),
]

# Gender checkbox positions on page 0, y ≈ 225
GENDER_POS = {
    "männlich":  287.0,
    "weiblich":  363.0,
    "unbekannt": 447.0,
}
GENDER_Y = 218.0   # top of the small checkbox square


def _add_watermark(page: fitz.Page) -> None:
    """Stamp red 'PREVIEW — NOT AN OFFICIAL DOCUMENT' watermark on the page."""
    pw, ph = page.rect.width, page.rect.height
    text  = "PREVIEW — NOT AN OFFICIAL DOCUMENT"

    # Diagonal text via morph (arbitrary rotation) with low fill_opacity
    pivot = fitz.Point(pw * 0.08, ph * 0.58)
    mat   = fitz.Matrix(35)   # 35-degree rotation matrix
    page.insert_text(
        pivot,
        text,
        fontname="helv",
        fontsize=24,
        color=(0.85, 0.0, 0.0),
        fill_opacity=0.22,
        render_mode=0,
        morph=(pivot, mat),
    )

    # Small top-banner: centred, red, every page
    page.insert_textbox(
        fitz.Rect(0, 2, pw, 16),
        "PREVIEW – NOT AN OFFICIAL DOCUMENT",
        fontname="helv",
        fontsize=9,
        color=(0.85, 0.0, 0.0),
        align=1,
    )


def fill(template: Path, user_data: dict, output: Path) -> str:
    doc = fitz.open(str(template))

    # ── Step 1: AcroForm fill (handles templates that DO have form fields) ──
    for page in doc:
        for widget in page.widgets() or []:
            key = widget.field_name or ""
            if key in user_data and user_data[key]:
                widget.field_value = user_data[key]
                widget.update()

    # ── Step 2: Coordinate overlay (for static PDFs without AcroForm fields) ─
    FONT      = "helv"
    FONT_SIZE = 9
    COLOR     = (0.0, 0.0, 0.0)

    for page_idx, x, y_bottom, field_key in OVERLAY:
        value = str(user_data.get(field_key) or "").strip()
        if not value or page_idx >= doc.page_count:
            continue
        page = doc[page_idx]
        page.insert_text(
            fitz.Point(x, y_bottom),
            value,
            fontname=FONT,
            fontsize=FONT_SIZE,
            color=COLOR,
        )

    # ── Step 3: Gender checkbox ───────────────────────────────────────────────
    gender_raw = str(user_data.get("gender", "")).strip().lower()
    gender_key = None
    if "männlich" in gender_raw or gender_raw in ("m", "male"):
        gender_key = "männlich"
    elif "weiblich" in gender_raw or gender_raw in ("w", "female"):
        gender_key = "weiblich"
    elif "unbekannt" in gender_raw or gender_raw == "unknown":
        gender_key = "unbekannt"

    if gender_key and doc.page_count > 0:
        gx = GENDER_POS[gender_key]
        gy = GENDER_Y
        doc[0].draw_rect(
            fitz.Rect(gx, gy, gx + 6, gy + 6),
            color=(0.0, 0.0, 0.0),
            fill=(0.0, 0.0, 0.0),
        )

    # ── Step 4: Watermark every page ─────────────────────────────────────────
    for page in doc:
        _add_watermark(page)

    # ── Step 5: Save ─────────────────────────────────────────────────────────
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output))
    doc.close()
    return str(output)


if __name__ == "__main__":
    result = fill(TEMPLATE, USER_DATA, OUTPUT)
    print(f"Saved: {result}")
