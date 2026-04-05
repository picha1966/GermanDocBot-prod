# Anmeldung — еталонний документ

Один документ = ідеал. Шаблон для всіх інших (kindergeld, wohngeld, …).

**Специфікація анкети 1:1:** `docs/ANMELDUNG_QUESTIONNAIRE_SPEC.md`

---

## 1. Повний список полів

**Джерело:** `backend/document_config.py` → `DOCUMENT_FIELDS["anmeldung"]`

### Required (обовʼязкові)

| Поле (PDF / анкета) | Німецька форма |
|---------------------|----------------|
| wohnungstyp | Die neue Wohnung ist |
| move_in_date | Einzugsdatum |
| postal_code / plz | Postleitzahl |
| city | Gemeinde, Ortsteil |
| street | Straße |
| house_number | Hausnummer |
| has_bisherige_wohnung | Bisherige Wohnung vorhanden? |
| last_name | Familienname |
| first_name | Vornamen |
| birth_date | Tag der Geburt |
| birth_place | Ort, Land der Geburt |

### Optional (необовʼязкові)

| Поле | Німецька форма |
|------|-----------------|
| apartment_number | Wohnungsnummer |
| move_out_date | Tag des Auszugs |
| previous_address | Bisherige Anschrift |
| zuzug_aus_ausland | Zuzug aus dem Ausland? |
| zuzug_staat | Staat (bei Zuzug aus dem Ausland) |
| bisherige_beibehalten | Bisherige Wohnung beibehalten? |
| weitere_wohnungen | Weitere Wohnungen? |
| birth_name | Geburtsname |
| nationality | Staatsangehörigkeiten |
| gender | Geschlecht |
| religion | Religionsgesellschaft |
| familienstand | Familienstand |
| eheschliessung_ort_datum | Ort, Datum der Eheschließung/Lebenspartnerschaft |
| passname | Passname |
| ordens_kuenstlername | Ordens-/Künstlername |
| landlord_name | Wohnungsgeber |
| signature_place | Ort (Unterschrift) |
| signature_date | Datum (Unterschrift) |
| plz | (alias для postal_code у ANSWER_KEY_ALIASES) |

---

## 2. PDF_FIELD_MAPPING (сторінка "0")

Координати 1:1 з офіційною сторінкою.  
Структура: `{ "0": { field_name: { x, y, font_size, max_width } } }`.

- **Behörde:** authority_name, authority_address, authority_plz, authority_city (заповнюються з `authority_info`).
- **Person:** first_name, last_name, birth_date, birth_place, nationality.
- **Anschrift:** street, house_number, plz, city, move_in_date, previous_address.
- **Unterschrift:** signature_place, signature_date.

Точні значення — у `document_config.py` → `PDF_FIELD_MAPPING["anmeldung"]`.

---

## 3. ANSWER_KEY_ALIASES

Анкета (WebApp) може слати інші ключі; тут — варіанти для підстановки в PDF.

| PDF поле | Можливі ключі з анкети |
|----------|------------------------|
| plz | plz, postal_code |
| city | city, city_name, ort |
| house_number | house_number, house_no, hausnummer |
| move_in_date | move_in_date, move_in, einzugsdatum |
| street | street, street_name, straße, strasse |
| birth_date | birth_date, birthdate, geburtsdatum |
| birth_place | birth_place, birthplace, geburtsort |
| first_name | first_name, vorname, given_name |
| last_name | last_name, nachname, family_name, surname |
| previous_address | previous_address, bisherige_anschrift, old_address |
| landlord_name | landlord_name, wohnungsgeber, landlord |

---

## 4. Візуальний контроль

| Режим | Водяний знак | Де в коді |
|-------|----------------|-----------|
| **Preview** | Так — "PREVIEW · NOT OFFICIAL" | `pdf_generator._fill_template_pdf(..., is_preview=True)` → `_apply_watermark(pdf, is_preview=True)` |
| **Final** | Ні | `_fill_template_pdf(..., is_preview=False)` → `_apply_watermark(pdf, is_preview=False)` (нічого не малює) |

Перевірка: згенерувати preview → має бути watermark; оплатити/скачати final → без watermark.

---

## 5. Шаблон PDF

- Файл: `templates/anmeldung.pdf`
- Привʼязка: `PDF_TEMPLATES["anmeldung"] = "anmeldung.pdf"`

Інші документи не чіпати до завершення еталону anmeldung.

---

## 6. DOCUMENT_FORM_SCHEMA (анкета для WebApp)

**Правило:** DOCUMENT_FIELDS = логіка (required/optional). DOCUMENT_FORM_SCHEMA = анкета (UI).

WebApp має:
1. Отримувати `doc_type`
2. Завантажувати `get_document_form_schema(doc_type)` → список полів з `key`, `label`, `type` (text|date|select), `required`, `placeholder`
3. Динамічно будувати анкету за цим порядком
4. Валідувати required
5. Надсилати `{ doc_type, answers }`

Схема anmeldung — у `document_config.py` → `DOCUMENT_FORM_SCHEMA["anmeldung"]`.
