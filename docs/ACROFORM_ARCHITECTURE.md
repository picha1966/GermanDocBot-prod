# AcroForm Architecture — Final PDF Generation

## Why AcroForm (Technical)

- **No layout drift**: Filling existing form fields uses the PDF’s own widget positions and appearance. No manual (x, y), no font size or max_width guesswork, no overlapping or shifted text.
- **1:1 with official form**: The output looks exactly like the official German form; only field values change. No “rebuilt” layout or custom tables.
- **Scalable**: New documents = new template PDF + mapping. No coordinate calibration per form.
- **Accessibility**: Form fields keep structure (names, order); assistive tech and “Save as” keep working.

Manual drawing (insert_text at x/y) is disabled when the template has AcroForm fields; it remains only as fallback for flat (scanned) PDFs.

---

## Field Mapping: schema_key → AcroForm field name

| schema_key | AcroForm field name (official PDF) |
|------------|-----------------------------------|
| authority_name | Behoerde_Name |
| authority_address | Behoerde_Adresse |
| authority_plz | Behoerde_PLZ |
| authority_city | Behoerde_Ort |
| wohnungstyp | Wohnungstyp |
| move_in_date | Einzugsdatum |
| plz / postal_code | PLZ |
| city | Ort |
| street | Strasse |
| house_number | Hausnummer |
| apartment_number | Wohnungsnummer |
| has_bisherige_wohnung | Bisherige_Wohnung |
| move_out_date | Auszugsdatum |
| previous_address | Bisherige_Anschrift |
| zuzug_aus_ausland | Zuzug_Ausland |
| zuzug_staat | Zuzug_Staat |
| bisherige_beibehalten | Bisherige_beibehalten |
| weitere_wohnungen | Weitere_Wohnungen |
| last_name | Familienname |
| first_name | Vorname |
| birth_name | Geburtsname |
| birth_date | Geburtsdatum |
| birth_place | Geburtsort |
| nationality | Staatsangehoerigkeit |
| gender | Geschlecht |
| religion | Religionsgesellschaft |
| familienstand | Familienstand |
| eheschliessung_ort_datum | Eheschliessung_Ort_Datum |
| passname | Passname |
| ordens_kuenstlername | Ordensname |
| landlord_name | Wohnungsgeber |
| person2_last_name | Familienname_2 |
| person2_first_name | Vorname_2 |
| person2_birth_name | Geburtsname_2 |
| person2_birth_date | Geburtsdatum_2 |
| person2_birth_place | Geburtsort_2 |
| person2_nationality | Staatsangehoerigkeit_2 |
| person2_gender | Geschlecht_2 |
| signature_place | Ort_Unterschrift |
| signature_date | Datum_Unterschrift |

**Note:** If your official PDF uses different AcroForm names, run:

```bash
python tools/extract_acroform_fields.py
```

Then update `ANMELDUNG_ACROFORM_MAPPING` in `backend/document_config.py` so each `schema_key` points to the actual field name in the template.

---

## Multi-language (Service Text Only — No Russian)

- **Form labels and structure**: Always German (official form).
- **Localized**: Watermark / footer / disclaimer text only, from `get_user_lang(user_id)` or `order["lang"]`.
- **Supported**: `de`, `en`, `uk`/`ua`, `ar`, `tr`, `pl` only.

Example PREVIEW label by language:

| Lang | Text |
|------|------|
| de | VORSCHAU — KEIN OFFIZIELLES DOKUMENT |
| en | PREVIEW — NOT OFFICIAL DOCUMENT |
| uk/ua | ПРЕВʼЮ — НЕОФІЦІЙНИЙ ДОКУМЕНТ |
| ar | معاينة — مستند غير رسمي |
| tr | ÖN İZLEME — RESMİ BELGE DEĞİLDİR |
| pl | PODGLĄD — DOKUMENT NIEOFICJALNY |

---

## Flow

1. **create_final_pdf** calls **\_fill_template_pdf_acroform** first.
2. If the template has widgets: fill exclusively via `widget.field_value = value` and `widget.update()`; save; return path. No x/y drawing.
3. If the template has no AcroForm fields: return `None`; **create_final_pdf** falls back to **\_fill_template_pdf** (overlay). AcroForm and overlay are never used in the same document.
4. Watermark (preview only) uses the localized label; it does not move or overlap form fields.
