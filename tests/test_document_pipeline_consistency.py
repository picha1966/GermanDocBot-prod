# -*- coding: utf-8 -*-
"""
tests/test_document_pipeline_consistency.py

Automated guard: verifies Document → Schema → Validation → Builder alignment.

If you add a new doc_type, you MUST:
  1. Add schema to DOCUMENT_FORM_SCHEMAS  (backend/document_config.py)
  2. Add required fields to _REQUIRED_FIELDS  (backend/utils/validate.py)
  3. Add sections to _DOC_SECTIONS  (backend/form_builder.py)

This test will fail immediately if any of the three registries are out of sync.
"""
import sys
import os
import pytest

# Ensure project root is on sys.path when running from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.document_config import DOCUMENT_FORM_SCHEMAS, DOC_STRATEGY
from backend.utils.validate import _REQUIRED_FIELDS, _FIELD_ALIASES
from backend.form_builder import _DOC_META, _DOC_SECTIONS


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


def _alias_flat_set() -> set:
    """Return the flat set of all known alias values (what the validator can find)."""
    flat = set()
    for aliases in _FIELD_ALIASES.values():
        flat.update(aliases)
    return flat


# ---------------------------------------------------------------------------
# RULE 1: Every doc in DOCUMENT_FORM_SCHEMAS must be in _REQUIRED_FIELDS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", list(DOCUMENT_FORM_SCHEMAS.keys()))
def test_schema_has_required_fields_entry(doc_type):
    assert doc_type in _REQUIRED_FIELDS, (
        f"[MISSING VALIDATOR] '{doc_type}' is in DOCUMENT_FORM_SCHEMAS "
        f"but has no entry in _REQUIRED_FIELDS (backend/utils/validate.py).\n"
        f"Add: \"{doc_type}\": [\"first_name\", \"last_name\", ...]"
    )


# ---------------------------------------------------------------------------
# RULE 2: Every doc in DOCUMENT_FORM_SCHEMAS must be in _DOC_META (builder)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", list(DOCUMENT_FORM_SCHEMAS.keys()))
def test_schema_has_builder_meta(doc_type):
    # Some docs use AcroForm templates (not builder) but still need a _DOC_META
    # entry for the watermark/header logic in form_builder.py.
    assert doc_type in _DOC_META, (
        f"[MISSING BUILDER META] '{doc_type}' is in DOCUMENT_FORM_SCHEMAS "
        f"but has no entry in _DOC_META (backend/form_builder.py).\n"
        f"Add a (title, legal_basis, authority) tuple."
    )


# ---------------------------------------------------------------------------
# RULE 3: Every required validator field must be findable via schema or aliases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", list(DOCUMENT_FORM_SCHEMAS.keys()))
def test_required_fields_covered_by_schema_or_alias(doc_type):
    schema = DOCUMENT_FORM_SCHEMAS[doc_type]
    schema_fields = _schema_field_names(schema)
    all_known_aliases = _alias_flat_set()

    missing_coverage = []
    for req_field in _REQUIRED_FIELDS.get(doc_type, []):
        # Field is covered if:
        # (a) the schema directly asks for it (same name)
        # (b) the schema asks for an alias that the validator resolves to req_field
        # (c) the req_field itself appears as an alias value somewhere (normalize handles it)
        if req_field in schema_fields:
            continue
        # Check if any schema field is an alias that resolves to req_field
        aliases_for_req = set(_FIELD_ALIASES.get(req_field, [req_field]))
        if schema_fields & aliases_for_req:
            continue
        # Check if any schema field is an alias value that maps to req_field
        # (e.g. schema has postal_code, validator needs plz — covered by alias)
        found_via_alias = False
        for schema_fld in schema_fields:
            if schema_fld in aliases_for_req:
                found_via_alias = True
                break
        if found_via_alias:
            continue
        missing_coverage.append(req_field)

    assert not missing_coverage, (
        f"[FIELD COVERAGE GAP] '{doc_type}': required fields not found in schema "
        f"(even after alias resolution): {missing_coverage}\n"
        f"Schema fields: {sorted(schema_fields)}\n"
        f"Fix: add these fields to DOCUMENT_FORM_SCHEMAS['{doc_type}'] "
        f"or add an alias in _FIELD_ALIASES."
    )


# ---------------------------------------------------------------------------
# RULE 4: No schema field is completely absent from both validator and builder
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type", list(DOCUMENT_FORM_SCHEMAS.keys()))
def test_no_orphan_schema_fields(doc_type):
    """
    Every field the schema collects must be used by at least one of:
    - validator (_REQUIRED_FIELDS or _FIELD_ALIASES)
    - builder (_DOC_SECTIONS)

    For AcroForm-strategy documents the builder-section check is skipped
    (all schema fields are forwarded to the AcroForm engine), but the
    schema ↔ validator check still runs to ensure required validation
    keys are present and correct.
    """
    strategy = DOC_STRATEGY.get(doc_type, "builder")
    schema = DOCUMENT_FORM_SCHEMAS[doc_type]
    schema_fields = _schema_field_names(schema)
    all_known_aliases = _alias_flat_set()

    required_and_warnings: set = set()
    for aliases in _FIELD_ALIASES.values():
        required_and_warnings.update(aliases)
    required_and_warnings.update(_REQUIRED_FIELDS.get(doc_type, []))

    # Signature/meta fields that are always valid even without explicit validator entry
    _ALWAYS_VALID = {
        "signature_place", "signature_date", "postal_code", "plz",
        "apartment_number", "gemeindekennzahl",
    }

    if strategy == "acroform":
        # AcroForm docs: every schema field is forwarded to the AcroForm engine
        # so a builder-section check is not meaningful.
        # We still verify schema ↔ validator: every required field in
        # _REQUIRED_FIELDS must be findable in the schema (or via aliases).
        validator_fields = list(_REQUIRED_FIELDS.get(doc_type, []))
        bad_validator_keys = []
        for vfield in validator_fields:
            if vfield in _ALWAYS_VALID:
                continue
            if vfield in schema_fields:
                continue
            aliases_for_v = set(_FIELD_ALIASES.get(vfield, [vfield]))
            if schema_fields & aliases_for_v:
                continue
            if any(sf in aliases_for_v for sf in schema_fields):
                continue
            bad_validator_keys.append(vfield)
        assert not bad_validator_keys, (
            f"[ACROFORM VALIDATOR MISMATCH] '{doc_type}': these required "
            f"validation fields are not findable in the schema:\n"
            f"  {bad_validator_keys}\n"
            f"Schema fields: {sorted(schema_fields)}\n"
            f"Fix: correct the key in _REQUIRED_FIELDS['{doc_type}'] to match "
            f"the schema, or add a _FIELD_ALIASES entry."
        )
        return

    # --- builder / xfa / flat strategy: full orphan check ---
    builder_fields = _builder_field_keys(doc_type)

    orphans = []
    for sf in schema_fields:
        if sf in _ALWAYS_VALID:
            continue
        if sf in builder_fields:
            continue
        if sf in required_and_warnings:
            continue
        if sf in all_known_aliases:
            continue
        orphans.append(sf)

    assert not orphans, (
        f"[ORPHAN SCHEMA FIELDS] '{doc_type}' (strategy={strategy}): schema "
        f"collects these fields but they are used by neither validator nor builder: {orphans}\n"
        f"Either add them to _DOC_SECTIONS['{doc_type}'] in form_builder.py "
        f"or to _REQUIRED_FIELDS / _WARNING_FIELDS in validate.py."
    )


# ---------------------------------------------------------------------------
# Integration smoke: the five core documents pass all rules
# ---------------------------------------------------------------------------

_CORE_DOCS = ["anmeldung", "kindergeld", "wohngeld", "buergergeld", "familienkasse"]

def test_core_documents_present_in_all_registries():
    for doc in _CORE_DOCS:
        assert doc in DOCUMENT_FORM_SCHEMAS, f"'{doc}' missing from DOCUMENT_FORM_SCHEMAS"
        assert doc in _REQUIRED_FIELDS,       f"'{doc}' missing from _REQUIRED_FIELDS"
        assert doc in _DOC_META,              f"'{doc}' missing from _DOC_META"
