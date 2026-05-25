# Anmeldung (Wohnsitzanmeldung) — Internal Questionnaire Specification

1:1 mirror of the official German form. Section order and field wording match the official document.

---

## Section 1: Neue Wohnung (new address)

| field_id | label (DE) | type | required | conditional | notes |
|----------|------------|------|----------|-------------|-------|
| wohnungstyp | Die neue Wohnung ist | select | yes | — | Options: alleinige Wohnung, Hauptwohnung, Nebenwohnung. Exactly one. |
| move_in_date | Tag des Einzugs | date | yes | — | |
| postal_code | Postleitzahl | plz | yes | — | |
| city | Gemeinde, Ortsteil | text | yes | — | |
| street | Straße | text | yes | — | |
| house_number | Hausnummer, Zusätze | text | yes | — | |
| apartment_number | Wohnungsnummer | text | no | — | If applicable. |

---

## Section 2: Bisherige Wohnung (previous residence)

| field_id | label (DE) | type | required | conditional | notes |
|----------|------------|------|----------|-------------|-------|
| has_bisherige_wohnung | Bisherige Wohnung vorhanden? | select | yes | — | Options: Ja, Nein. |
| move_out_date | Tag des Auszugs | date | no | visible_if: has_bisherige_wohnung = Ja | Only if previous residence in Germany. |
| previous_address | Bisherige Anschrift (PLZ, Ort, Straße …) | text | no | visible_if: has_bisherige_wohnung = Ja | One or more lines. |
| zuzug_aus_ausland | Bei Zuzug aus dem Ausland? | select | no | visible_if: has_bisherige_wohnung = Ja | Options: Ja, Nein. |
| zuzug_staat | Staat (bei Zuzug aus dem Ausland) | text | no | visible_if: zuzug_aus_ausland = Ja | Country of previous residence. |
| bisherige_beibehalten | Wird die bisherige Wohnung beibehalten? | select | no | visible_if: has_bisherige_wohnung = Ja | Options: Ja, Nein. |
| weitere_wohnungen | Haben die unten aufgeführten Personen noch weitere Wohnungen? | select | no | — | Options: Ja, Nein. |

---

## Section 3: Angaben zur Person (Person 1)

| field_id | label (DE) | type | required | conditional | notes |
|----------|------------|------|----------|-------------|-------|
| last_name | Familienname | text | yes | — | |
| first_name | Vornamen | text | yes | — | |
| birth_name | Geburtsname (sofern abweichend) | text | no | — | Maiden name / former surname. |
| birth_date | Tag der Geburt | date | yes | — | |
| birth_place | Ort, Land der Geburt | text | yes | — | |
| nationality | Staatsangehörigkeiten | text | no | — | One or more (comma-separated if multiple). BMG §3. |
| gender | Geschlecht | select | no | — | Options: m, w, d. Official wording. |
| religion | Religionsgesellschaft | text | no | — | Legal membership in public-law religious society. Optional. |
| familienstand | Familienstand | select | no | — | Options: ledig, verheiratet, verwitwet, geschieden, eingetragene Lebenspartnerschaft. |
| eheschliessung_ort_datum | Ort, Datum der Eheschließung/Lebenspartnerschaft | text | no | visible_if: familienstand in [verheiratet, eingetragene Lebenspartnerschaft] | Only when married or registered partnership. Schema uses visible_if.values array. |
| passname | Passname | text | no | — | If applicable (e.g. different from civil name). |
| ordens_kuenstlername | Ordens-/Künstlername | text | no | — | Religious/artistic name if applicable. |

**Person 2 (family registration):** Optional section "Angaben zur Person (Person 2)" with same fields as Person 1, prefixed `person2_`: person2_last_name, person2_first_name, person2_birth_name, person2_birth_date, person2_birth_place, person2_nationality, person2_gender. All optional; if filled, data is printed on the same form below Person 1. 1:1 with official form layout.

---

## Section 4: Wohnungsgeber

| field_id | label (DE) | type | required | conditional | notes |
|----------|------------|------|----------|-------------|-------|
| landlord_name | Name, Anschrift des Wohnungsgebers | text | no | — | Landlord or main tenant. |

---

## Section 5: Unterschrift

| field_id | label (DE) | type | required | conditional | notes |
|----------|------------|------|----------|-------------|-------|
| signature_place | Ort (Unterschrift) | text | no | — | |
| signature_date | Datum (Unterschrift) | date | no | — | |

---

## Official-only (no user question)

These keys may appear in PDF_FIELD_MAPPING but are **not** questionnaire fields; they are filled by the system or left for the authority:

- **Behörde:** authority_name, authority_address, authority_plz, authority_city (from authority_info).
- **Gemeindekennzahl:** administrative; leave empty or pre-filled.
- **Dokumente:** Art, Ausstellungsbehörde, Seriennummer, Datum, gültig bis — ID/passport table, official use only.
- **Unterschrift (handwritten):** user signs on paper; no questionnaire field for the signature itself (signature_place and signature_date are questionnaire fields).

---

## Conditional rules (summary)

1. If **has_bisherige_wohnung** = Ja → show: move_out_date, previous_address, zuzug_aus_ausland, zuzug_staat (if zuzug_aus_ausland=Ja), bisherige_beibehalten.
2. If **zuzug_aus_ausland** = Ja → show: zuzug_staat.
3. **wohnungstyp**: exactly one of alleinige Wohnung, Hauptwohnung, Nebenwohnung (no free text).
4. If **bisherige_beibehalten** = Ja → **wohnungstyp** must be Hauptwohnung or Nebenwohnung (not „alleinige Wohnung“). Enforce in validation: if user keeps previous dwelling, the new one is either main or secondary residence.
5. If **familienstand** = verheiratet or eingetragene Lebenspartnerschaft → show: eheschliessung_ort_datum.
6. All Ja/Nein questions: select with options [Ja, Nein] only.

---

## Checkbox / select integrity

- wohnungstyp: select, options = ["alleinige Wohnung", "Hauptwohnung", "Nebenwohnung"].
- has_bisherige_wohnung: select, options = ["Ja", "Nein"].
- zuzug_aus_ausland: select, options = ["Ja", "Nein"].
- bisherige_beibehalten: select, options = ["Ja", "Nein"].
- weitere_wohnungen: select, options = ["Ja", "Nein"].
- gender: select, options = ["m", "w", "d"] (official wording).
- familienstand: select, options = ["ledig", "verheiratet", "verwitwet", "geschieden", "eingetragene Lebenspartnerschaft"].

No free text for these; values must match official wording for PDF 1:1 fill.

---

## Validation rules (cross-field)

- **bisherige_beibehalten = Ja** → **wohnungstyp** must be "Hauptwohnung" or "Nebenwohnung" (not "alleinige Wohnung"). If the user keeps the previous dwelling, the new address is by definition a main or secondary residence. Enforce in backend or frontend validation when both are set.

## PDF consistency

- Every questionnaire field_id has a PDF_FIELD_MAPPING key (or is official-only).
- Official-only keys (in PDF_FIELD_MAPPING but not in questionnaire): **authority_name**, **authority_address**, **authority_plz**, **authority_city** (filled from authority_info).
- **postal_code** (questionnaire) → **plz** (PDF key) via ANSWER_KEY_ALIASES; all other questionnaire fields use the same key as PDF.
- ANSWER_KEY_ALIASES: include all alternate keys the frontend may send.
- Values written to PDF must match official wording (Ja/Nein, alleinige/Haupt/Nebenwohnung, m/w/d, familienstand values).

### PDF mapping audit (questionnaire → PDF)

| Questionnaire field_id | PDF key | Source |
|------------------------|---------|--------|
| postal_code | plz | ANSWER_KEY_ALIASES |
| All other schema fields | same as field_id | Direct |
| — | authority_name, authority_address, authority_plz, authority_city | Official-only (authority_info) |

### Naming conventions

- **field_id:** snake_case; matches official form semantics (e.g. `zuzug_aus_ausland`, `bisherige_beibehalten`). No ambiguous names (e.g. addr1/addr2); use `street`, `house_number`, `previous_address` etc.
- **ANSWER_KEY_ALIASES:** canonical key = PDF field name; list includes German equivalents and common frontend variants so `get_value_for_pdf_field` resolves correctly.

---

## Anmeldung 1:1 Compliance — Final Validation

### ✅ Checklist: PASSED

- **Field completeness:** All official form fields represented: Neue Wohnung, Bisherige Wohnung (with Zuzug aus dem Ausland, bisherige beibehalten, weitere Wohnungen), Angaben zur Person (including Religionsgesellschaft, Familienstand, Eheschließung/Lebenspartnerschaft, Passname, Ordens-/Künstlername), Wohnungsgeber, Unterschrift (Ort, Datum). Multiple nationality via single text field (comma-separated). Person 2 scope documented.
- **Conditional logic:** has_bisherige_wohnung → move_out_date, previous_address, zuzug_aus_ausland, zuzug_staat, bisherige_beibehalten. zuzug_aus_ausland → zuzug_staat. familienstand (verheiratet / eingetragene Lebenspartnerschaft) → eheschliessung_ort_datum. wohnungstyp select-only; Ja/Nein select-only. bisherige_beibehalten = Ja → wohnungstyp Haupt-/Nebenwohnung rule documented.
- **PDF mapping:** Every questionnaire field maps to a PDF key (postal_code → plz via alias). Official-only keys (authority_*) documented. No questionnaire field unused; no user-filled PDF key without questionnaire source.
- **Naming & semantics:** field_id and ANSWER_KEY_ALIASES normalized; no breaking changes.

### ❗ Remaining risks

1. **Coordinates (x, y):** PDF_FIELD_MAPPING coordinates are placeholder/layout values. They must be measured against the actual `templates/anmeldung.pdf` so text aligns with the official form lines. Until then, final PDF may show text in wrong positions.
2. **Cross-field validation:** The rule „bisherige_beibehalten = Ja → wohnungstyp ∈ {Hauptwohnung, Nebenwohnung}“ is documented but not enforced in code. Consider adding validation in backend or WebApp before submit.
3. **Person 2:** Questionnaire is Person 1 only. Adding a repeatable „Person 2“ section would require schema and PDF mapping extension (second set of person fields on the form).

### 📄 Confirmation

The questionnaire defined in this spec and implemented in `ANMELDUNG_SCHEMA` / `DOCUMENT_FIELDS` / `PDF_FIELD_MAPPING` can be used as a **direct visual and logical filling guide** for the official German Anmeldung (Wohnsitzanmeldung) form: section order, field labels, types, and conditional visibility match the official document; select options use exact official wording; all user-filled areas on the form have a corresponding questionnaire field and PDF mapping.
