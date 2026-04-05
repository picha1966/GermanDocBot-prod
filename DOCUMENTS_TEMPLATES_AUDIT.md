# Аудит: документи в боті vs шаблони PDF

**Джерело document_key:** `handlers/start.py` → `category_doc_types`  
**Папка шаблонів:** `templates/` (корінь проєкту)

---

## Зведена таблиця: шаблон є / не вистачає

| document_key | Категорія | Є PDF-шаблон? | Файл | Статус |
|--------------|-----------|----------------|------|--------|
| anmeldung | residence | ✅ так | anmeldung.pdf | OK |
| abmeldung | residence | ❌ ні | — | **немає** |
| ummeldung | residence | ❌ ні | — | **немає** |
| wohnungsgeberbestaetigung | residence | ❌ ні | — | **немає** |
| meldebescheinigung | residence | ❌ ні | — | **немає** |
| anmeldung_familie | residence | ❌ ні | — | **немає** |
| kindergeld | family | ✅ так | kindergeld.pdf | OK |
| elterngeld | family | ❌ ні | — | **немає** |
| kinderzuschlag | family | ⚠️ є інший файл | kiz_main.pdf, kiz_short_en.pdf | кандидат |
| unterhaltsvorschuss | family | ❌ ні | — | **немає** |
| anlage_kind | family | ❌ ні | — | **немає** |
| steuer_id_kind | family | ❌ ні | — | **немає** |
| buergergeld | finance | ❌ ні | — | **немає** |
| wohngeld | finance | ⚠️ є інший файл | wohngeld_main.pdf | кандидат |
| arbeitslosengeld_1 | finance | ❌ ні | — | **немає** |
| arbeitslosengeld_2 | finance | ❌ ні | — | **немає** |
| krankenversicherung_anmeldung | finance | ❌ ні | — | **немає** |
| sozialversicherungsnummer | finance | ❌ ні | — | **немає** |
| arbeitserlaubnis | employment | ❌ ні | — | **немає** |
| steuererklaerung | employment | ❌ ні | — | **немає** |
| gewerbeanmeldung | employment | ❌ ні | — | **немає** |
| kuendigung | employment | ❌ ні | — | **немає** |
| arbeitslosmeldung | employment | ❌ ні | — | **немає** |
| sozialversicherungsnummer | employment | ❌ ні | — | **немає** |

**Підсумок:** є шаблон — **2** (anmeldung, kindergeld); кандидат (інше ім’я файлу) — **2**; **немає шаблону — 20**.

---

## Детальна таблиця (повний аудит)

| document_key | Категорія | Файл у templates/ | Статус |
|--------------|-----------|-------------------|--------|
| **anmeldung** | residence | anmeldung.pdf | ✅ OK |
| abmeldung | residence | — | ❌ missing |
| ummeldung | residence | — | ❌ missing |
| wohnungsgeberbestaetigung | residence | — | ❌ missing |
| meldebescheinigung | residence | — | ❌ missing |
| anmeldung_familie | residence | — | ❌ missing |
| **kindergeld** | family | kindergeld.pdf | ✅ OK |
| elterngeld | family | — | ❌ missing |
| kinderzuschlag | family | kiz_main.pdf, kiz_short_en.pdf * | ⚠️ candidate |
| unterhaltsvorschuss | family | — | ❌ missing |
| anlage_kind | family | — | ❌ missing |
| steuer_id_kind | family | — | ❌ missing |
| buergergeld | finance | — | ❌ missing |
| **wohngeld** | finance | wohngeld_main.pdf * | ⚠️ candidate |
| arbeitslosengeld_1 | finance | — | ❌ missing |
| arbeitslosengeld_2 | finance | — | ❌ missing |
| krankenversicherung_anmeldung | finance | — | ❌ missing |
| sozialversicherungsnummer | finance | — | ❌ missing |
| arbeitserlaubnis | employment | — | ❌ missing |
| steuererklaerung | employment | — | ❌ missing |
| gewerbeanmeldung | employment | — | ❌ missing |
| kuendigung | employment | — | ❌ missing |
| arbeitslosmeldung | employment | — | ❌ missing |
| sozialversicherungsnummer | employment | — | ❌ missing |

\* **candidate** — файл є, але ім’я не збігається з document_key; потрібна явна прив’язка в `PDF_TEMPLATES` (наприклад `"wohngeld": "wohngeld_main.pdf"`).

---

## Підсумок

| Статус | Кількість |
|--------|-----------|
| ✅ OK | 2 (anmeldung, kindergeld) |
| ⚠️ candidate | 2 (kinderzuschlag→kiz_*, wohngeld→wohngeld_main) |
| ❌ missing | 20 |

**Унікальних document_key у боті:** 24 (sozialversicherungsnummer в двох категоріях рахується один раз).

---

## Файли в templates/ без document_key в меню

(Можуть бути для майбутніх документів або інших потоків.)

| Файл |
|------|
| citizenship_extra_info.pdf |
| housing_confirm.pdf |
| jobcenter_kdu.pdf |
| jobcenter_main_2025.pdf |
| kindergeld_child.pdf |
| kiz_main.pdf |
| kiz_short_en.pdf |
| residence_permit_en_fr_it.pdf |
| school_change.pdf |
| tax_reduction.pdf |
| traffic_fine_reply.pdf |
| ukraine_housing.pdf |
| wbs_main.pdf |
| wbs_partner_statement.pdf |
| Wohngeldantrag_Mietzuschuss.pdf |

---

## Що далі (за твоїм планом)

1. **КРОК 1** — цей аудит ✅ зроблено.
2. **КРОК 2** — довести **anmeldung** до ідеалу (поля, координати, aliases, вигляд PDF).
3. **КРОК 3** — додавати документи по одному: PDF у `templates/` + запис у `document_config.py` (PDF_TEMPLATES, DOCUMENT_FIELDS, PDF_FIELD_MAPPING). `pdf_generator.py` не чіпати.
