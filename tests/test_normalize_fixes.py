# -*- coding: utf-8 -*-
"""Tests for birth_place, birth_country and street auto-split normalizations."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.normalize import normalize_user_data, _normalize_birth_place


def test_birth_place():
    cases = [
        ("Vinnytsia Ukraine",                "Vinnytsia, Ukraine"),
        ("vinnitsia ukraine",                "Vinnitsia, Ukraine"),
        ("Vinnytsia, ukraine",               "Vinnytsia, Ukraine"),
        ("Vinnytsia, Ukraine",               "Vinnytsia, Ukraine"),
        ("Frankfurt am Main Deutschland",    "Frankfurt Am Main, Deutschland"),
        ("Berlin",                           "Berlin"),
        ("kyiv",                             "Kyiv"),
        ("kyiv ukraine",                     "Kyiv, Ukraine"),
        ("Kyiv,",                            "Kyiv"),
        ("vinnitsia,",                       "Vinnitsia"),
    ]
    for inp, expected in cases:
        got = _normalize_birth_place(inp)
        assert got == expected, f"birth_place({inp!r}): got {got!r}, expected {expected!r}"
    print("birth_place: ALL OK")


def test_birth_country():
    cases = [
        ("ukraine",      "Ukraine"),
        ("Ukraine",      "Ukraine"),
        ("south korea",  "South Korea"),
        ("DEUTSCHLAND",  "Deutschland"),
        ("deutschland",  "Deutschland"),
        ("türkei",       "Türkei"),
        ("turkey",       "Turkey"),
        ("polska",       "Polska"),
    ]
    for inp, expected in cases:
        d = normalize_user_data({"birth_country": inp})
        got = d.get("birth_country", "")
        assert got == expected, f"birth_country({inp!r}): got {got!r}, expected {expected!r}"
    print("birth_country: ALL OK")


def test_street_split():
    cases = [
        # (street_in, hn_in, expected_street, expected_hn)
        # _normalize_street converts "strasse" → "straße" and title-cases
        ("Musterstrasse 12",          "",  "Musterstraße",          "12"),
        ("Musterstrasse 12a",         "",  "Musterstraße",          "12a"),
        ("Frankfurter Allee 120-122", "",  "Frankfurter Allee",     "120-122"),
        ("Hauptstrasse 5/2",          "",  "Hauptstraße",           "5/2"),
        ("Am Bahnhof 7",              "",  "Am Bahnhof",            "7"),
        # no number → no split
        ("Am Bahnhof",                "",  "Am Bahnhof",            ""),
        ("Musterstrasse",             "",  "Musterstraße",          ""),
        # house_number already provided → split NOT applied, street still normalized
        ("Musterstrasse",             "5", "Musterstraße",          "5"),
        # Streets already using ß
        ("Hauptstraße 5",             "",  "Hauptstraße",           "5"),
        ("Königsallee 30",            "",  "Königsallee",           "30"),
    ]
    for s_in, hn_in, exp_s, exp_hn in cases:
        data = {"street": s_in}
        if hn_in:
            data["house_number"] = hn_in
        d = normalize_user_data(data)
        got_s  = d.get("street", "")
        got_hn = d.get("house_number", "")
        assert got_s  == exp_s,  f"street({s_in!r}, hn={hn_in!r}): street got {got_s!r}, expected {exp_s!r}"
        assert got_hn == exp_hn, f"street({s_in!r}, hn={hn_in!r}): hn got {got_hn!r}, expected {exp_hn!r}"
    print("street_split: ALL OK")


if __name__ == "__main__":
    test_birth_place()
    test_birth_country()
    test_street_split()
    print("\nALL TESTS PASSED")
