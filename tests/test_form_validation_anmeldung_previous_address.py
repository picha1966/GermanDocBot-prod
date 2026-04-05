# -*- coding: utf-8 -*-
"""
Regression tests for Anmeldung previous-address validation.

Ensures backend accepts split previous_* fields when combined previous_address
is missing, including localized yes-value "Так".
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.form_validation import validate_anmeldung_form


def _base_payload():
    return {
        "last_name": "Ivanov",
        "first_name": "Ivan",
        "birth_date": "01.01.1990",
        "birth_place": "Vinnytsia, Ukraine",
        "postal_code": "10115",
        "city": "Berlin",
        "street": "Maxstrasse",
        "house_number": "12",
        "move_in_date": "01.01.2020",
        "landlord_name": "Max Mustermann",
        "landlord_street": "Karlstrasse",
        "landlord_house_number": "1",
        "landlord_plz": "10117",
        "landlord_city": "Berlin",
        "dokumentenart": "PA",
        "ausstellungsbehoerde": "Buergeramt Berlin",
        "seriennummer": "L01X00T47",
        "ausstellungsdatum": "01.01.2020",
        "gueltig_bis": "01.01.2030",
        "signature_date": "01.01.2024",
        "weitere_wohnungen": "Nein",
        # split previous-address fields (no combined previous_address on purpose)
        "previous_plz": "10117",
        "previous_ort": "Berlin",
        "previous_strasse": "Maxstrase",
        "previous_hausnummer": "56",
    }


def test_previous_address_required_satisfied_by_split_fields_for_ja():
    data = _base_payload()
    data["has_bisherige_wohnung"] = "Ja"

    ok, errors, _warnings = validate_anmeldung_form(data, "uk")
    err_keys = [e.get("message_key") for e in errors]

    assert ok is True, f"Expected valid payload, got errors: {errors}"
    assert "previous_address_required" not in err_keys


def test_previous_address_required_satisfied_by_split_fields_for_ukrainian_yes():
    data = _base_payload()
    data["has_bisherige_wohnung"] = "Так"

    ok, errors, _warnings = validate_anmeldung_form(data, "uk")
    err_keys = [e.get("message_key") for e in errors]

    assert ok is True, f"Expected valid payload for 'Так', got errors: {errors}"
    assert "previous_address_required" not in err_keys
