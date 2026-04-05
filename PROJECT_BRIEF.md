# PROJECT BRIEF — Deutschland PDF Assistant (Telegram Bot)

## 1. Загальна ідея

Deutschland PDF Assistant — Telegram-бот, який допомагає підготувати **приклад** правильно заповнених німецьких документів, щоб їх прийняли з першого разу.

**Бот НЕ створює офіційні документи.** Він генерує неофіційні PDF-приклади / шаблони на основі відповідей користувача.

PDF використовується як:
- візуальна інструкція
- приклад заповнення
- орієнтир для ручного заповнення офіційної форми

---

## 2. Архітектура (ключова логіка)

### 2.1 Документи в боті

У боті є перелік документів: **menu → category → document**. Кожен документ має унікальний **document_key**.

Приклад:
- `anmeldung`
- `abmeldung`
- `ummeldung`
- `wohnungsgeberbestaetigung`
- `meldebescheinigung`
- `anmeldung_familie`

**document_key — єдине джерело правди для всієї логіки.**

### 2.2 PDF-шаблони

У папці `templates/` зберігаються PDF-шаблони.

Правила:
- 1 документ = 1 PDF-шаблон
- назва файлу логічно відповідає document_key
- жодних універсальних шаблонів «на все»

Приклад:
```
templates/
├─ anmeldung_template.pdf
├─ abmeldung_template.pdf
├─ ummeldung_template.pdf
```

### 2.3 Привʼязка документ → шаблон

Привʼязка реалізується **одним словником**, без `if`/`elif`:

```python
PDF_TEMPLATES = {
    "anmeldung": "templates/anmeldung_template.pdf",
    "abmeldung": "templates/abmeldung_template.pdf",
    "ummeldung": "templates/ummeldung_template.pdf",
}
```

Якщо **document_key** немає в словнику:
- PDF не генерується
- бот показує «coming soon» або інформативне повідомлення

---

## 3. Анкета (WebApp) і дані

### 3.1 Принцип анкети

- Кожен документ має **свою** анкету
- Анкета збирає тільки релевантні поля
- Дані відправляються в бот через `tg.sendData()`

### 3.2 Формат даних у бота

Стандартна структура (приклад):

```json
{
  "document_key": "anmeldung",
  "answers": {
    "first_name": "Max",
    "last_name": "Mustermann",
    "birth_date": "01.01.1990",
    "street": "Musterstraße 1",
    "postal_code": "10115",
    "city": "Berlin",
    "move_in_date": "01.02.2026",
    "landlord_name": "Hans Müller"
  }
}
```

---

## 4. Поля (Fields) — критично важливо

### 4.1 Принцип полів

- Поля анкети ≠ поля PDF напряму
- Потрібен чіткий мапінг:

```
answers (user data) → template_fields (PDF positions) → rendered PDF
```

### 4.2 Опис полів для кожного документа

Для **кожного** документа має бути опис:

```python
DOCUMENT_FIELDS = {
  "anmeldung": {
    "required": [
      "first_name", "last_name", "birth_date",
      "street", "postal_code", "city",
      "move_in_date"
    ],
    "optional": [
      "landlord_name", "apartment_number"
    ]
  }
}
```

### 4.3 Мапінг полів у PDF

Кожен шаблон має власний mapping:

```python
PDF_FIELD_MAPPING = {
  "anmeldung": {
    "first_name": {"x": 120, "y": 640},
    "last_name": {"x": 300, "y": 640},
    "birth_date": {"x": 120, "y": 610},
    "street": {"x": 120, "y": 580},
    "city": {"x": 300, "y": 580},
    "move_in_date": {"x": 120, "y": 550}
  }
}
```

Координати — приклад, не фіксовані.

---

## 5. Генерація PDF

### 5.1 Що має містити PDF

Кожен згенерований PDF:
- Заповнені дані користувача
- Водяний знак: **PREVIEW – NOT OFFICIAL DOCUMENT**
- Пояснювальний текст (1 сторінка або footer):  
  *This is an example of a filled document. Use it as a reference for the official form.*

### 5.2 Preview vs Final

На поточному етапі:
- PDF = preview / example
- Paywall підключається пізніше

---

## 5.3 Правила превʼю PDF (мова та оформлення)

**Важливе уточнення.**

Усі PDF-превʼю мають бути тією мовою, яку безпосередньо обрав клієнт (UA / DE / EN / тощо).  
**Без винятків і без fallback'ів на "дефолтну" мову.**

Також превʼю повинно бути:
- візуально охайним і якісно оформленим (шрифти, відступи, структура),
- виглядати як професійний документ, а не технічна заглушка,
- зберігати стиль і тон майбутнього повного PDF.

Ідея: превʼю має викликати думку  
*"Так, це мій документ, моєю мовою, все виглядає серйозно — можна платити"*,  
а не просто "перевірку даних".

Це критично для довіри та конверсії.

---

## 6. Поведінка при відсутності даних

- Немає шаблону → не генерувати PDF
- Немає обовʼязкового поля → показати помилку користувачу
- Порожні answers → не створювати PDF

---

## 7. Правила розробки (must-follow)

1. Ніякої магії
2. Ніяких hardcoded if/else
3. Усе через словники
4. Один документ = одна логіка = один шаблон
5. Максимальна прозорість

---

## 8. Цінність продукту

Ми не автоматизуємо німецьку бюрократію.  
Ми допомагаємо людям заповнити документи так, щоб їх не повернули назад.
Project: CivicAssistBot

Telegram bot that helps immigrants prepare German documents and find appointments (Termin).

Architecture:
Telegram Bot
→ WebApp form
→ Preview PDF
→ Stripe payment
→ Final PDF
→ Termin monitoring

Main principle:
Bot generates example-filled PDFs explaining how to correctly complete official forms so applications are accepted the first time.

Languages supported:
DE, EN, UA, PL, TR, AR
