# CivicAssistBot v5.0

Telegram-бот для генерації заповнених PDF-документів для українців у Німеччині.
Підтримує WebApp-форму, оплату через Stripe, email-доставку та Termin-моніторинг.

---

## Функції

### Документи

| Тип документа | Шаблон |
|---|---|
| Anmeldung (реєстрація) | AcroForm + overlay |
| Abmeldung (виписка) | AcroForm |
| Bürgergeld (соціальна допомога) | Builder |
| Kindergeld (дитяча допомога) | AcroForm |
| Kinderzuschlag (надбавка) | Builder |
| Wohngeld (субсидія на житло) | Builder |
| Aufenthaltstitel (посвідка) | Builder |
| Mietbescheinigung (довідка про оренду) | Builder |
| Wohnungsgeberbestätigung | AcroForm |
| Beschäftigungserklärung | Builder |
| та інші (16+ шаблонів) | |

### Оплата (Stripe)

- Stripe Checkout (Card, Apple Pay, Google Pay, SEPA, Klarna — dynamic methods)
- Webhook `checkout.session.completed` → PDF генерується і доставляється одразу
- Idempotent delivery через `claim_delivery()` (захист від дублювання при одночасних запитах)
- Email-доставка PDF після оплати (SendGrid / Resend / SMTP)

### Termin-моніторинг

- Перевірка наявності записів у Bürgeramt
- Підписки: 24h, 7-day, сімейний пакет, пріоритетний буст
- Відновлення моніторингу після рестарту бота

### Реферальна система

- Схема БД та всі методи збережені (`referral_code`, `referral_count`, `free_doc_credits`)
- **Логіка нарахування вимкнена** (нема `register_referral` після оплати)
- Щоб увімкнути — розкоментуйте блок `REFERRAL SYSTEM DISABLED` у `bot.py`

### Інше

- Багатомовність: UK / DE / EN / PL / TR / AR
- GDPR consent при першому старті
- WebApp (форма в Telegram Mini App)
- Адмін-панель: `/admin`, статистика, управління цінами
- Реферальна аналітика у логах (`REFERRAL_AWARDED`)

---

## Структура проєкту

```
.
├── bot.py                    # Головний entrypoint: polling + HTTP 4243 + Stripe webhook
├── app.py                    # Шим: from bot import main
├── main.py                   # DEPRECATED: виводить помилку і виходить
├── requirements.txt
├── .env.example
├── DEPLOY.md                 # Деплой, email, DNS (SPF/DKIM/DMARC)
├── supervisor/               # Конфіги supervisord + systemd + Nginx
├── backend/
│   ├── database.py           # SQLite: users, orders, referrals (WAL mode)
│   ├── stripe_handler.py     # Stripe Checkout Session
│   ├── pdf_generator.py      # PDF генерація (AcroForm + overlay + builder)
│   ├── pdf_renderers.py      # Рендерери для кожного типу документа
│   ├── form_builder.py       # Динамічна побудова форм
│   ├── document_config.py    # Конфігурація документів
│   ├── translations.py       # Переклади
│   ├── settings.py           # Конфіг з .env
│   ├── termin_db.py          # Termin-підписки
│   ├── family_profiles.py    # Smart Family Profiles
│   ├── progress_bar.py       # Progress bar UI
│   ├── calendar_widget.py    # Inline calendar
│   ├── advisor.py            # Eligibility advisor
│   ├── gdpr.py               # GDPR тексти і клавіатури
│   ├── export.py             # Експорт CSV
│   ├── analytics.py          # Аналітика воронки
│   ├── pricing.py            # Динамічні ціни (DB override)
│   ├── forms/                # Динамічні JSON-схеми форм
│   ├── i18n/                 # Переклади форм (JSON)
│   └── utils/                # normalize, validate, font_check, pdf_cleanup
├── bot_config/
│   ├── menu_structure.py     # Меню і список документів (source of truth)
│   └── pricing.py            # PDF_PRICES (base prices)
├── handlers/
│   ├── docs_new.py           # WebApp flow: форма → preview → оплата → PDF
│   ├── payments.py           # Post-payment UX і deep-link обробка
│   ├── start.py              # /start, мова, GDPR, головне меню
│   ├── termin.py             # Termin flow
│   ├── termin_activation.py  # Активація після оплати
│   ├── stripe_handler.py     # Checkout ініціація
│   ├── admin.py              # Адмін-панель
│   ├── support_ai.py         # AI-підтримка
│   ├── health.py             # /health команда
│   └── what_to_do.py         # "Що робити далі" після документа
├── utils/
│   ├── email_sender.py       # SendGrid / Resend / SMTP
│   ├── termin_checker.py     # Scraper для Termin
│   ├── termin_monitor.py     # Background polling loop
│   └── stripe_env.py         # Env-guard (не пускає prod без webhook secret)
├── templates/                # PDF-шаблони (офіційні форми, 16+ типів)
├── webapp/                   # WebApp HTML (Telegram Mini App)
├── tests/                    # pytest тести
└── tools/                    # Утиліти: e2e тести, PDF аудит, реєстрація документів
```

---

## Швидкий старт

### Крок 1. Налаштуйте `.env`

```bash
cp .env.example .env
# Відредагуйте .env своїм редактором
```

Мінімально необхідні змінні:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
BOT_USERNAME=your_bot_username
WEBAPP_URL=https://your-domain.com/form
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

### Крок 2. Встановіть залежності

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# або
source venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
```

### Крок 3. Запустіть бота

```bash
python bot.py
```

Успішний запуск:
```
✅ Database initialized (WAL mode)
🟢 Bot started and polling
✅ HTTP /webapp-submit listening on 0.0.0.0:4243
```

### Крок 4. Перевірте в Telegram

1. Відкрийте бота в Telegram
2. Натисніть `/start`
3. Пройдіть GDPR consent
4. Оберіть документ → «Заповнити анкету»
5. Заповніть WebApp-форму

---

## Production деплой

Детальна інструкція з Stripe, email, DNS (SPF/DKIM/DMARC) та Nginx — у **[DEPLOY.md](DEPLOY.md)**.

Process supervisor (systemd або supervisord) — у **[supervisor/README.md](supervisor/README.md)**.

Health check: `GET http://127.0.0.1:4243/health`

---

## Адмін команди

| Команда | Опис |
|---------|------|
| `/admin` | Відкрити адмін-панель |
| `/health` | Стан Termin-моніторингу |

---

## База даних (SQLite, WAL mode)

| Таблиця | Призначення |
|---------|------------|
| `users` | Користувачі: мова, GDPR, referral_code, credits |
| `orders` | Замовлення: статус, stripe_session_id, delivered |
| `referrals` | Підтверджені реферали (referrer → referee) |

Схема розширюється автоматично через `ALTER TABLE IF NOT EXISTS` — безпечно для наявних БД.

---

## Тести

```bash
pytest tests/ -v
```

Ключові тест-файли:
- `tests/test_backend.py` — Database API + Stripe utils
- `tests/test_normalize_validate.py` — нормалізація і валідація даних
- `tests/test_stripe_webhook_guard.py` — безпека webhook
- `tests/test_smoke_regression.py` — smoke імпорти
- `tests/test_termin_support_matrix.py` — Termin UX матриця

---

## Реферальна система

**Статус: вимкнена (DB-схема збережена).**

DB-шар повністю реалізований: `get_or_create_referral_code`, `register_referral`,
`use_free_doc_credit` тощо. Логіка нарахування після оплати закоментована в `bot.py`
(блок `# REFERRAL SYSTEM DISABLED`).

Щоб увімкнути — розкоментуйте цей блок у `bot.py` після функції `_delivery_ok`.

---

## Версія

**v5.0** (березень 2026)

- Stripe Checkout з idempotent PDF delivery
- Termin-моніторинг з bundle-підписками
- Реферальна система (активна)
- 16+ типів документів
- WebApp (Telegram Mini App) + AcroForm + Builder pipeline
- Email-доставка (SendGrid / Resend / SMTP)
- GDPR consent flow
- Multilingual: UK / DE / EN / PL / TR / AR

---

Розроблено для українців у Німеччині.
