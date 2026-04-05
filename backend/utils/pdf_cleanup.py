# -*- coding: utf-8 -*-
"""
backend/utils/pdf_cleanup.py — GDPR-safe PDF lifecycle management.

Provides:
  cleanup_old_pdfs(max_age_hours)  — remove stale generated PDFs on startup
  delete_pdf_after_delivery(path)  — remove a specific PDF after it was sent

All generated PDFs in generated_pdfs/ contain PII (name, address, IBAN).
They must not accumulate on disk indefinitely.
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolved at import time; falls back gracefully if pdf_generator is not importable.
try:
    from backend.pdf_generator import OUTPUT_DIR as _OUTPUT_DIR
except Exception:
    _OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "generated_pdfs"

_OUTPUT_DIR = Path(_OUTPUT_DIR)


def cleanup_old_pdfs(max_age_hours: int = 2) -> int:
    """
    Delete PDF files in the generated_pdfs/ directory that are older than
    max_age_hours. Non-PDF files are never touched.

    Returns the number of files deleted.
    Called once at bot startup to clear stale files from previous runs.
    """
    if not _OUTPUT_DIR.exists():
        logger.debug("pdf_cleanup: output dir does not exist yet — nothing to clean")
        return 0

    cutoff_seconds = max_age_hours * 3600
    now = time.time()
    deleted = 0
    errors = 0

    for pdf_file in _OUTPUT_DIR.iterdir():
        if not pdf_file.is_file():
            continue
        if pdf_file.suffix.lower() != ".pdf":
            continue
        try:
            age_seconds = now - pdf_file.stat().st_mtime
            if age_seconds >= cutoff_seconds:
                pdf_file.unlink()
                deleted += 1
                logger.debug(
                    "pdf_cleanup: deleted stale file %s (age=%.0f min)",
                    pdf_file.name,
                    age_seconds / 60,
                )
        except Exception as e:
            errors += 1
            logger.warning("pdf_cleanup: could not delete %s: %s", pdf_file.name, e)

    if deleted or errors:
        logger.info(
            "pdf_cleanup: startup cleanup complete — deleted=%d errors=%d (max_age=%dh)",
            deleted,
            errors,
            max_age_hours,
        )
    else:
        logger.debug("pdf_cleanup: no stale PDFs found (max_age=%dh)", max_age_hours)

    return deleted


def delete_pdf_after_delivery(pdf_path: Optional[str]) -> bool:
    """
    Safely delete a specific PDF file after it has been sent to the user.

    Should be called immediately after a successful bot.send_document() call
    to remove PII from disk.

    Returns True if the file was deleted, False otherwise.
    """
    if not pdf_path:
        return False

    path = Path(pdf_path)
    if not path.exists():
        logger.debug("pdf_cleanup: file already gone: %s", path.name)
        return True

    try:
        path.unlink()
        logger.info("pdf_cleanup: deleted after delivery: %s", path.name)
        return True
    except Exception as e:
        logger.warning("pdf_cleanup: failed to delete %s after delivery: %s", path.name, e)
        return False
