#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick smoke test for all 7 document types."""
import sys, io, os, logging
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.WARNING)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from backend.pdf_generator import create_final_pdf, create_preview

ANMELDUNG = {
    "user_id": 1, "last_name": "Muster", "first_name": "Max",
    "birth_date": "15.03.1990", "birth_place": "Kiew UA",
    "nationality": "ukrainisch", "gender": "m",
    "wohnungstyp": "Hauptwohnung", "move_in_date": "01.03.2024",
    "postal_code": "10115", "city": "Berlin",
    "street": "Musterstrasse", "house_number": "15",
    "has_bisherige_wohnung": "Nein", "weitere_wohnungen": "Nein",
    "dokumentenart": "RP", "seriennummer": "UA1234567",
    "ausstellungsbehoerde": "DMSU UA", "ausstellungsdatum": "10.01.2020",
    "gueltig_bis": "09.01.2030", "landlord_name": "Hans Schmidt",
    "landlord_address": "Musterstrasse 1, 10115 Berlin",
    "signature_date": "18.02.2024", "familienstand": "ledig",
    "signature_place": "Berlin",
}

TESTS = [
    ("anmeldung",               ANMELDUNG),
    ("ummeldung", {
        "user_id": 2, "last_name": "Kovalenko", "first_name": "Olena",
        "move_in_date": "01.04.2024", "postal_code": "10178", "city": "Berlin",
        "street": "Alexanderstrasse", "house_number": "3",
        "previous_address": "10115 Berlin, Musterstrasse 15",
        "birth_date": "12.07.1995", "signature_date": "18.02.2024",
    }),
    ("wohnungsgeberbestaetigung", {
        "user_id": 3, "landlord_name": "Schmidt GmbH",
        "landlord_address": "Kantstrasse 5, 10623 Berlin",
        "postal_code": "10623", "city": "Berlin", "street": "Kantstrasse",
        "house_number": "5", "last_name": "Ivanenko", "first_name": "Dmytro",
        "birth_date": "22.08.1988", "move_in_date": "01.03.2024",
        "signature_date": "18.02.2024",
    }),
    ("kindergeld", {
        "user_id": 4, "last_name": "Bondar", "first_name": "Natalia",
        "birth_date": "10.01.1988", "postal_code": "80331", "city": "Muenchen",
        "street": "Maximilianstrasse", "house_number": "1",
        "child_last_name": "Bondar", "child_first_name": "Lena",
        "child_birth_date": "15.06.2021", "child_birth_place": "Berlin",
        "iban": "DE89370400440532013000", "signature_date": "18.02.2024",
    }),
    ("wohngeld", {
        "user_id": 5, "last_name": "Petrenko", "first_name": "Ivan",
        "birth_date": "20.05.1985", "postal_code": "10115", "city": "Berlin",
        "street": "Hauptstrasse", "house_number": "5",
        "dwelling_type": "Mietwohnung", "living_space_sqm": "55",
        "monthly_rent": "850", "household_members": "2",
        "monthly_income": "1200", "signature_date": "18.02.2024",
    }),
    ("buergergeld", {
        "user_id": 6, "last_name": "Savchenko", "first_name": "Oksana",
        "birth_date": "05.11.1992", "birth_place": "Odessa UA",
        "postal_code": "10115", "city": "Berlin",
        "street": "Friedrichstrasse", "house_number": "10",
        "household_members": "1", "family_status": "ledig",
        "monthly_rent": "700", "iban": "DE89370400440532013000",
        "signature_date": "18.02.2024",
    }),
    ("aufenthaltstitel", {
        "user_id": 7, "last_name": "Kovalenko", "first_name": "Olena",
        "birth_date": "12.07.1995", "birth_place": "Lemberg UA",
        "nationality": "ukrainisch", "gender": "w",
        "dokumentenart": "RP", "seriennummer": "UA9876543",
        "ausstellungsbehoerde": "DMSU Ukraine",
        "ausstellungsdatum": "01.06.2019", "gueltig_bis": "31.05.2029",
        "postal_code": "10115", "city": "Berlin",
        "street": "Kantstrasse", "house_number": "22",
        "residence_purpose": "Arbeit", "employer_name": "Tech GmbH",
        "occupation": "Software-Entwicklerin",
        "signature_date": "18.02.2024",
    }),
]

ok = 0
fail = 0
for doc_type, data in TESTS:
    r_final = create_final_pdf(user_id=data["user_id"], user_data=data, doc_type=doc_type, user_lang="uk")
    r_preview = create_preview(user_id=data["user_id"], user_data=data, doc_type=doc_type, user_lang="uk")
    final_ok = r_final and isinstance(r_final, str) and os.path.exists(r_final)
    prev_ok  = r_preview and isinstance(r_preview, str) and os.path.exists(r_preview)
    sz_f = os.path.getsize(r_final) // 1024 if final_ok else 0
    sz_p = os.path.getsize(r_preview) // 1024 if prev_ok else 0
    status = "OK" if (final_ok and prev_ok) else "FAIL"
    if status == "OK":
        ok += 1
    else:
        fail += 1
    print(f"  {status}  {doc_type:<32} final={sz_f:>4}KB  preview={sz_p:>4}KB")

print()
print(f"Results: {ok} passed, {fail} failed out of {len(TESTS)} documents")
if fail:
    sys.exit(1)
