# Посилання на офіційні бланки документів (для типів у боті)

Довідник зібрано за допомогою пошуку офіційних джерел. Використовуйте для додавання шаблонів у `backend/document_config.py` (PDF_TEMPLATES) або для посилань у боті.

---

## Проживання (Residence)

### Anmeldung (реєстрація місця проживання)
- **Офіційний бланк:** ANM / Anmeldung einer Wohnung
- **Посилання:** https://allaboutberlin.com/documents/anmeldung-original.pdf  
- **Портал:** https://wohnsitzanmeldung.gov.de/ (електронна реєстрація), https://service.berlin.de/dienstleistung/120686/
- **Примітка:** Бланк стандартизований (BMG). Потрібна також Wohnungsgeberbestätigung.

### Abmeldung (зняття з реєстрації)
- **Офіційний бланк:** Abmeldung bei der Meldebehörde
- **Приклади PDF:**  
  - Thüringen: https://thformular.thueringen.de/.../BMG-006-DE-FL  
  - Mannheim: https://www.mannheim.de/sites/default/files/page/73797/abmeldung.pdf  
  - Geldern: https://www.geldern.de/.../bmg_abmeldung.pdf
- **Примітка:** Форма може трохи відрізнятися за землею. Бланк подається протягом 2 тижнів після виїзду.

### Ummeldung (перереєстрація)
- Зазвичай використовується той самий бланк, що й для Anmeldung (нова адреса + стара адреса). Деталі: портал землі або міста (Bürgeramt).

### Wohnungsgeberbestätigung (підтвердження орендодавця)
- **Приклади PDF:**  
  - Dresden: https://www.dresden.de/media/pdf/einwohner/WGBest__Formular.pdf  
  - Geratal: https://www.geratal.de/.../Wohnungsgeberbestaetigung.pdf  
  - Aichhalden: https://www.aichhalden.de/.../Wohnungsgeberbestätigung.pdf
- **Примітка:** За BMG §19. Заповнює орендодавець; потрібна для Anmeldung.

### Meldebescheinigung
- Це не заява, а **свідоцтво**, яке видає Meldebehörde після реєстрації. Офіційного «бланка заяви» немає — звертаються до Bürgeramt.

### Anmeldung Familie (сімейна реєстрація)
- Електронна реєстрація: https://wohnsitzanmeldung.gov.de/ (опція сімейної реєстрації). Бланки за землею можуть мати окремий аркуш для додаткових осіб.

---

## Сім'я (Family)

### Kindergeld (допомога на дітей)
- **Офіційні форми (Bundesagentur für Arbeit):**  
  - Сторінка форм: https://www.arbeitsagentur.de/familie-und-kinder/downloads-familie-und-kinder/formulare-kindergeld  
  - **KG1** (головний бланк): https://www.arbeitsagentur.de/datei/kg1-antrag-kindergeld_ba036550.pdf  
  - **KG1-AnK** (додаток на кожну дитину): https://www.arbeitsagentur.de/datei/kg1-anlagekind_ba033765.pdf  
- **Українською:** KG1-ua, KG1-uaAK на тій самій сторінці (розділ «Заява про отримання допомоги на дитину»).

### Elterngeld (батьківська допомога)
- Форми залежать від землі та дати народження.  
- **Приклади:** Niedersachsen, NRW, BMF — на сайтах Elterngeldstelle землі.  
- **Інфо:** https://www.familienportal.de, https://www.bundesamtsozialesicherung.de/de/mutterschaftsgeld/antrag-stellen/

### Kinderzuschlag (дитяча доплата)
- **Офіційні форми (Bundesagentur):**  
  - Сторінка: https://www.arbeitsagentur.de/familie-und-kinder/downloads-familie-und-kinder/formulare-kinderzuschlag  
  - **KiZ 1** (головний): https://www.arbeitsagentur.de/datei/kiz1-antrag_ba036540.pdf  
  - **KiZ 1-AnK** (додаток дитина): https://www.arbeitsagentur.de/datei/kiz1-ank_ba035005.pdf  

### Unterhaltsvorschuss (аліменти / допомога на утримання)
- **Офіційна назва:** Antrag auf Leistungen nach dem Unterhaltsvorschussgesetz (UVG).  
- Форми видають Jugendämter; приклад (Berlin): https://www.berlin.de/sen/jugend/.../antrag-uvg-anlage-2.pdf  
- **Онлайн:** service.berlin.de (Berlin), аналогічно — портали інших земель.

### Anlage Kind / Steuer-ID Kind
- Для Kindergeld використовується **KG1-AnK** (посилання вище).  
- Окремий бланк на отримання Steuer-ID для дитини — через BZSt / Finanzamt (форма за запитом).

---

## Фінанси (Finance)

### Bürgergeld
- Форми та онлайн-анкета: **Bundesagentur für Arbeit** / Jobcenter.  
- **Сторінка:** https://www.arbeitsagentur.de/arbeitslos-arbeit-finden/buergergeld  
- **Інфо форми:** https://www.buergergeld.org/formulare/  
- Рекомендовано подавати через jobcenter.digital (онлайн).

### Wohngeld (допомога на житло)
- **Залежить від землі.** Приклади:  
  - Bayern: https://www.stmb.bayern.de/.../35_mz_antrag_bildschirm.pdf  
  - Mecklenburg-Vorpommern: https://www.regierung-mv.de/.../wohngeldformulare/  
  - NRW: https://bauportal.nrw/antraege/antrag-auf-wohngeld  
- Шукати: «Wohngeld Antrag [назва землі]» або офіційний портал землі.

### Arbeitslosengeld I / II
- **ALG I:** Форми на сайті Bundesagentur (Arbeitslosmeldung, Antrag ALG I).  
- **ALG II** замінено на **Bürgergeld** (див. вище).

### Krankenversicherung Anmeldung
- Це заява до страхової каси (Krankenkasse), не єдиний державний бланк. Форма залежить від каси (AOK, TK, Barmer тощо).

### Sozialversicherungsnummer
- Отримується через Antrag bei der Deutschen Rentenversicherung або при першій роботі. Один із варіантів: форма «Antrag auf Zuteilung einer Versicherungsnummer» (Rentenversicherung).

---

## Робота (Employment)

### Arbeitserlaubnis
- Це дозвіл (від Ausländerbehörde / Agentur für Arbeit), не один уніфікований бланк. Форми за землею/відомством.

### Steuererklärung (податкова декларація)
- **Офіційні форми BZSt / Finanzamt:** звірити по https://www.bzst.de або Elster (електронна подача). Форми (Mantelbogen, Anlagen) за рік.

### Gewerbeanmeldung
- Реєстрація бізнесу в Gewerbeamt / Ordnungsamt. Бланк за комуною; приклад: https://www.gewerbe-anmelden.de (інфо) або офіційний портал міста.

### Kündigung (розірвання договору)
- Це лист/заява до роботодавця, не єдиний державний PDF. Існують зразки (Muster) від правових порталів, але офіційного «бланка» немає.

### Arbeitslosmeldung (реєстрація безробіття)
- **Bundesagentur für Arbeit:** реєстрація онлайн або особисто. Форми на https://www.arbeitsagentur.de (Arbeitslosmeldung, Antrag auf Arbeitslosengeld).

---

## Як додати шаблон у бот

1. Завантажити офіційний PDF у папку `templates/` (наприклад `kindergeld.pdf`).
2. У `backend/document_config.py` додати запис у `PDF_TEMPLATES`, наприклад:
   - `"kindergeld": "kindergeld.pdf"`
3. Додати (за потреби) поля в `DOCUMENT_FIELDS`, `DOCUMENT_FORM_SCHEMA`, `PDF_FIELD_MAPPING` для цього типу документа.

**Увага:** Багато бланків відрізняються за федеральними землями (Bundesland). Для уніфікованих форм (наприклад Kindergeld KG1, KiZ 1, Anmeldung) посилання вище ведуть на офіційні PDF.
