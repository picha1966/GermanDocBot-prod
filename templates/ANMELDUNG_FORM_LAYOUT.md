# Розмітка офіційного бланка Anmeldung (для PDF_FIELD_MAPPING)

Щоб анкетні дані **співпадали з рядками** превʼю і **відповідали назвам рядків** на бланку:

1. **Один ключ маппінгу = один рядок на бланку** — значення пишеться саме в рядок з цим підписом.
2. **Координати (x, y)** виміряти по вашому `templates/anmeldung.pdf` — інакше текст ляже не в той рядок.
3. **Текст заповнення** рендериться **чорним** (не тусклим) — це вже зроблено в коді.

## Структура бланка (зверху вниз)

1. **Заголовок:** «Anmeldung»
2. **Neue Wohnung (ліва колонка):**
   - Gemeindekennzahl
   - «Die neue Wohnung ist» (alleinige / Haupt- / Nebenwohnung)
   - **Tag des Einzugs** → `move_in_date`
   - **Postleitzahl, Gemeinde, Ortsteil** → `plz`, `city`
   - **Straße, Hausnummer, Zusätze** → `street`, `house_number`
3. **Bisherige Wohnung (права колонка):**
   - Tag des Auszugs, Postleitzahl, Gemeinde/Kreis/Land, Straße…
   - «Bei Zuzug aus dem Ausland Staat»
   - «Wird die bisherige Wohnung beibehalten?»
   - «Haben die unten aufgeführten Personen noch weitere Wohnungen?»
   - Попередня адреса (одним рядком або кількома) → `previous_address`
4. **Person 1 (і 2):**
   - **Familienname** → `last_name`
   - Passname
   - **Vornamen** → `first_name`
   - Geburtsname, Geschlecht
   - **Tag, Ort, Land der Geburt** → `birth_date`, `birth_place` (країну можна додати окремим полем)
   - Religionsgesellschaft
   - **Staatsangehörigkeiten** → `nationality`
   - Ordens-/Künstlername, Familienstand, Eheschließung/Lebenspartnerschaft
5. **Dokumente:** таблиця (Art, Ausstellungsbehörde, Seriennummer, Datum, gültig bis)
6. **Unterschrift** (внизу) → `signature_place`, `signature_date`

## Як виміряти координати у вашому PDF

1. Відкрийте **ваш** `templates/anmeldung.pdf` (той самий, що використовується для превʼю).
2. У PyMuPDF (fitz): **початок (0,0)** — лівий верхній кут сторінки, **y зростає вниз**.
3. Для **кожного рядка** з таблиці вище: знайдіть на PDF рядок з цією **назвою** (наприклад «Familienname»), визначте **y** (базова лінія рядка) і **x** (початок поля для вписування).
4. У `backend/document_config.py` у `PDF_FIELD_MAPPING["anmeldung"]["0"]` підставте ці **x** та **y** для відповідного ключа.
5. Збережіть і згенеруйте превʼю — кожна відповідь має лягти в рядок з правильною назвою і бути чорною (не тусклою).

## Відповідність ключів анкети та бланка

| Назва рядка на бланку | Ключ у маппінгу | Примітка |
|-----------------------|-----------------|----------|
| **Tag des Einzugs** | move_in_date | Neue Wohnung |
| **Postleitzahl, Gemeinde, Ortsteil** | plz, city | той самий рядок, різні x |
| **Straße, Hausnummer** | street, house_number | один рядок, різні x |
| Bisherige Wohnung (адреса) | previous_address | права колонка |
| **Familienname** | last_name | Person 1/2 |
| **Vornamen** | first_name | Person 1/2 |
| **Tag, Ort, Land der Geburt** | birth_date, birth_place | один рядок, різні x |
| **Staatsangehörigkeiten** | nationality | Person 1/2 |
| **Unterschrift Ort / Datum** | signature_place, signature_date | внизу сторінки |

Після вимірювання (x, y) по вашому PDF і підстановки в `PDF_FIELD_MAPPING` анкетні дані будуть співпадати з рядками і назвами рядків; текст буде чорним (не тусклим).
