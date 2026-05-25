# -*- coding: utf-8 -*-
"""
backend/utils/font_check.py

Startup font integrity check for the PDF generation pipeline.

Called once at bot startup to ensure required TrueType fonts are present
on the deployment server. Missing fonts cause Cyrillic/Arabic user data
to render as boxes or question marks in generated PDFs — a silent P0 defect.

Usage:
    from backend.utils.font_check import check_required_fonts
    check_required_fonts()   # raises RuntimeError if any font is missing
"""

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Resolved relative to this file: backend/utils/ → ../../fonts/
_FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"

_REQUIRED_FONTS: List[str] = [
    "DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf",
]


def check_required_fonts() -> None:
    """
    Verify that all required PDF fonts are present on disk.

    Raises:
        RuntimeError: if any required font file is missing, listing all
                      missing paths so the deployment issue is immediately clear.

    Call this once during bot startup (e.g. in on_startup()) so the problem
    is caught before any user PDF request is processed.
    """
    missing: List[str] = []
    for font_filename in _REQUIRED_FONTS:
        font_path = _FONTS_DIR / font_filename
        if not font_path.exists():
            missing.append(str(font_path))

    if missing:
        missing_list = "\n  - ".join(missing)
        raise RuntimeError(
            f"Required PDF fonts missing. The following font files were not found:\n"
            f"  - {missing_list}\n\n"
            f"Ensure DejaVuSans.ttf and DejaVuSans-Bold.ttf are deployed to: {_FONTS_DIR}\n"
            f"Without these fonts, Cyrillic and Arabic user data will render incorrectly in PDFs."
        )

    logger.info(
        "✅ PDF font check passed — %d required font(s) found in %s",
        len(_REQUIRED_FONTS),
        _FONTS_DIR,
    )
