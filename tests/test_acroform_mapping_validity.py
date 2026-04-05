# -*- coding: utf-8 -*-
"""
tests/test_acroform_mapping_validity.py

Verifies that every key in an AcroForm mapping actually corresponds to a real
widget field inside the PDF template file.

Only documents whose template file EXISTS on disk are checked.  Documents that
are declared in PDF_TEMPLATES but have a missing file are reported as a warning
(separate test), not a failure, because the template may not be committed to
the repository.

Uses PyMuPDF (fitz) to extract widget names from the PDF.

Usage:
  pytest tests/test_acroform_mapping_validity.py -v
"""
import sys
import os
import pytest
from pathlib import Path
from typing import Dict, Set

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import fitz  # type: ignore
    _FITZ_AVAILABLE = True
except ImportError:
    _FITZ_AVAILABLE = False

from backend.document_config import (
    PDF_TEMPLATES,
    DOC_STRATEGY,
    _ACROFORM_MAPPINGS,
)

# Root directory of the project (one level above /tests)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _REPO_ROOT / "templates"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _widget_names_from_pdf(pdf_path: Path) -> Set[str]:
    """Return the set of all AcroForm widget field names found in a PDF."""
    doc = fitz.open(str(pdf_path))
    names: Set[str] = set()
    for page in doc:
        for widget in page.widgets():
            if widget.field_name:
                names.add(widget.field_name)
    doc.close()
    return names


def _template_path(doc_type: str) -> Path | None:
    """Return the resolved template Path if declared and present on disk."""
    rel = PDF_TEMPLATES.get(doc_type)
    if rel is None:
        return None
    p = _TEMPLATES_DIR / rel
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Collect test cases: only docs with an AcroForm mapping AND an existing template
# ---------------------------------------------------------------------------

_ACROFORM_CASES = []
for _doc in sorted(_ACROFORM_MAPPINGS.keys()):
    _tpl = _template_path(_doc)
    if _tpl is not None:
        _ACROFORM_CASES.append(
            pytest.param(_doc, _tpl, _ACROFORM_MAPPINGS[_doc], id=_doc)
        )


# ---------------------------------------------------------------------------
# RULE 1 — Every mapping value must be a widget field in the PDF
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _FITZ_AVAILABLE, reason="PyMuPDF (fitz) not installed")
@pytest.mark.parametrize("doc_type,tpl_path,mapping", _ACROFORM_CASES)
def test_mapping_keys_exist_in_pdf(doc_type, tpl_path, mapping):
    """
    For each doc_type that has both an AcroForm mapping and an existing PDF
    template, verify that every PDF field name referenced in the mapping
    (the dict *values*) actually exists as a widget in the template.

    Failure means the field will be silently skipped during PDF filling.
    """
    widget_names = _widget_names_from_pdf(tpl_path)

    if not widget_names:
        pytest.skip(
            f"No AcroForm widgets found in '{tpl_path.name}' "
            f"(may be a flat/XFA PDF) — skipping field coverage check."
        )

    bad_targets: list = []
    for schema_key, pdf_field in mapping.items():
        if pdf_field not in widget_names:
            bad_targets.append((schema_key, pdf_field))

    assert not bad_targets, (
        f"[BROKEN MAPPING] '{doc_type}': these mapping entries reference "
        f"PDF widget names that do NOT exist in '{tpl_path.name}':\n"
        + "\n".join(f"  schema_key='{sk}' → pdf_field='{pf}'"
                    for sk, pf in sorted(bad_targets))
        + f"\n\nExisting widget names in template ({len(widget_names)}):\n  "
        + ", ".join(sorted(widget_names)[:30])
        + (" ..." if len(widget_names) > 30 else "")
    )


# ---------------------------------------------------------------------------
# RULE 2 — Template integrity: warn about declared-but-missing templates
# ---------------------------------------------------------------------------

def _make_template_param(doc: str, rel: str) -> pytest.param:
    strategy = DOC_STRATEGY.get(doc, "builder")
    full = _TEMPLATES_DIR / rel
    # Builder-only docs must NOT have a stale PDF_TEMPLATES entry: hard fail.
    # AcroForm/flat/xfa docs whose template file is absent from the repo are
    # marked xfail (template binary may not be committed) but still reported.
    if strategy == "builder" or full.exists():
        return pytest.param(doc, rel, id=doc)
    return pytest.param(
        doc, rel,
        marks=pytest.mark.xfail(
            reason=(
                f"Template '{rel}' declared but missing from disk "
                f"(strategy={strategy}). "
                f"Add the PDF file to templates/ to fix this warning."
            ),
            strict=False,
        ),
        id=doc,
    )


_DECLARED_DOCS = [
    _make_template_param(doc, PDF_TEMPLATES[doc])
    for doc in sorted(PDF_TEMPLATES.keys())
]


@pytest.mark.parametrize("doc_type,rel_path", _DECLARED_DOCS)
def test_declared_templates_exist_on_disk(doc_type, rel_path):
    """
    Every template declared in PDF_TEMPLATES must physically exist on disk.

    Builder-strategy docs: HARD FAIL — builder docs need no template; a stale
    PDF_TEMPLATES entry is dead config and should be removed.

    AcroForm/flat/xfa docs: XFAIL when the file is missing — the template
    binary may not be committed to the repository, but the absence is still
    reported so it can be tracked.
    """
    full_path = _TEMPLATES_DIR / rel_path
    assert full_path.exists(), (
        f"[MISSING TEMPLATE] '{doc_type}': template declared as "
        f"'{rel_path}' but file not found at:\n  {full_path}\n"
        f"Either add the file or remove the entry from PDF_TEMPLATES."
    )
