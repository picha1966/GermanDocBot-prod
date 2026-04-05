# -*- coding: utf-8 -*-
"""
tests/test_builder_schema_alignment.py

Consistency guard: every field key used in _DOC_SECTIONS (form_builder.py)
must exist as a named field in the corresponding DOCUMENT_FORM_SCHEMAS entry.

This prevents silent builder ↔ schema mismatches such as:

  builder uses:  "plz"
  schema has:    "postal_code"

  → builder renders an empty row; user data is silently lost in the PDF.

Usage:
  pytest tests/test_builder_schema_alignment.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.document_config import DOCUMENT_FORM_SCHEMAS, DOC_STRATEGY
from backend.form_builder import _DOC_SECTIONS
from backend.utils.validate import _FIELD_ALIASES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _schema_field_names(schema: dict) -> set:
    """Collect all field 'name' values from a DOCUMENT_FORM_SCHEMAS entry."""
    names = set()
    for section in schema.get("sections", []):
        for field in section.get("fields", []):
            n = field.get("name")
            if n:
                names.add(n)
    return names


def _builder_field_keys(doc_type: str) -> set:
    """Collect all field keys from _DOC_SECTIONS for a doc_type."""
    keys = set()
    for _section_title, fields in _DOC_SECTIONS.get(doc_type, []):
        for field_key, _label in fields:
            keys.add(field_key)
    return keys


def _alias_canonical_keys() -> set:
    """Return the set of all canonical alias *keys* (left side of _FIELD_ALIASES)."""
    return set(_FIELD_ALIASES.keys())


def _alias_values_flat() -> set:
    """Return the flat set of all known alias *values* (right side of _FIELD_ALIASES)."""
    flat = set()
    for aliases in _FIELD_ALIASES.values():
        flat.update(aliases)
    return flat


# Builder-only synthetic keys: derived/composite values that are assembled
# by _preprocess_user_data() before rendering and are not schema fields.
# They are valid builder keys even if absent from the schema.
_BUILDER_SYNTHETIC_KEYS = {
    "street_display",      # anmeldung: composed from street + house_number
    "previous_address",    # legacy composite kept in some builder sections
}


# ---------------------------------------------------------------------------
# RULE A: every builder field key must exist in schema (or be a known alias/synthetic)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", [
    dt for dt in DOCUMENT_FORM_SCHEMAS
    if DOC_STRATEGY.get(dt, "builder") not in ("acroform",)
       and dt in _DOC_SECTIONS
])
def test_builder_fields_exist_in_schema(doc_type):
    """
    Every key listed in _DOC_SECTIONS[doc_type] must appear as a 'name' in
    DOCUMENT_FORM_SCHEMAS[doc_type], OR be a known alias value, OR be a
    declared synthetic key.

    Failure means the builder will silently render an empty row for that field.
    """
    schema = DOCUMENT_FORM_SCHEMAS[doc_type]
    schema_fields = _schema_field_names(schema)
    builder_fields = _builder_field_keys(doc_type)
    all_alias_values = _alias_values_flat()

    ghost_fields = []
    for bkey in builder_fields:
        if bkey in _BUILDER_SYNTHETIC_KEYS:
            continue
        if bkey in schema_fields:
            continue
        if bkey in all_alias_values:
            # Key is a known alias value — the schema may use a different name
            # that resolves to the same field (e.g. schema has "postal_code",
            # builder has "plz" — both are in _FIELD_ALIASES["plz"]).
            continue
        ghost_fields.append(bkey)

    assert not ghost_fields, (
        f"[GHOST BUILDER FIELDS] '{doc_type}': builder references fields that "
        f"do not exist in the schema (user data for these will be empty in PDF):\n"
        f"  ghost keys: {sorted(ghost_fields)}\n"
        f"  schema fields: {sorted(schema_fields)}\n"
        f"Fix: either add these fields to DOCUMENT_FORM_SCHEMAS['{doc_type}'] "
        f"or correct the key name in _DOC_SECTIONS['{doc_type}']."
    )


# ---------------------------------------------------------------------------
# RULE B: every builder section must have at least one field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", [
    dt for dt in DOCUMENT_FORM_SCHEMAS
    if dt in _DOC_SECTIONS
])
def test_builder_sections_not_empty(doc_type):
    """No section in _DOC_SECTIONS should be declared with zero fields."""
    for section_title, fields in _DOC_SECTIONS[doc_type]:
        assert fields, (
            f"[EMPTY BUILDER SECTION] '{doc_type}': section '{section_title}' "
            f"has no fields. Remove the section or add fields to it."
        )


# ---------------------------------------------------------------------------
# RULE C: documents with builder strategy must have a _DOC_SECTIONS entry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", [
    dt for dt in DOCUMENT_FORM_SCHEMAS
    if DOC_STRATEGY.get(dt, "builder") == "builder"
])
def test_builder_strategy_has_sections(doc_type):
    """
    Every document with strategy='builder' must have an entry in _DOC_SECTIONS,
    otherwise pdf_generator falls through to the emergency plain-text renderer.
    """
    assert doc_type in _DOC_SECTIONS, (
        f"[MISSING BUILDER SECTIONS] '{doc_type}' has strategy='builder' but "
        f"no entry in _DOC_SECTIONS (backend/form_builder.py).\n"
        f"The PDF generator will fall back to emergency plain-text output.\n"
        f"Add a sections layout to _DOC_SECTIONS['{doc_type}']."
    )
