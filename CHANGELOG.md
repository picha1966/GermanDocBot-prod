# Changelog

All notable changes to CivicAssistBot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [5.0.0] — 2026-03-29

### Added
- **Analytics persistence** — `analytics_events` SQLite table; `log_analytics_event()` now writes real rows; `get_funnel_stats()` returns live counts per event type.
- **GitHub Actions CI** — automated test + lint pipeline on push/PR (`pytest` + `ruff`).
- **Process supervisor docs** — `supervisor/README.md` with full `systemd` and `supervisord` instructions, Nginx reverse-proxy config, health-check commands.
- **`get_funnel_stats(days)`** on `Database` — returns `{total_events, unique_users, by_event_type}`.

### Fixed
- **`user_id` NameError** in Stripe webhook admin alert (`bot.py` line ~594) — variable referenced before assignment in edge case; replaced with `order.get("user_id") or "unknown"`.
- **`test_backend.py`** — completely rewritten; was testing 8 non-existent modules; now 47 tests covering real `Database` and `StripePaymentHandler` APIs, all green.
- **`test_termin_support_matrix.py`** — 6 pre-existing failures fixed; `TestBuildPostPaymentMenu` row-count assertions updated to reflect menu expansion (added "What next" and "Share bot" rows).
- **Admin IDs hardcode** — removed `[907156976]` from `backend/settings.py`; `BotConfig.ADMIN_IDS` now reads exclusively from `ADMIN_IDS` env variable.

### Changed
- **Referral system** — logic disabled (commented out after payment delivery); DB schema and all methods preserved for future activation.
- **`supervisor/webapp.conf`** — updated for v5.0: single `bot.py` process, correct port 4243 (was 8080), removed stale webapp-only config.
- **`README.md`** — rewritten to match actual codebase: real file structure, correct DB tables, accurate feature list, removed stale Stripe key placeholder.
- **`.env.example`** — added `OPENAI_API_KEY`, `THROTTLE_MSG_RATE`, `THROTTLE_CB_RATE` sections.
- **`requirements.txt`** — added `sendgrid>=6.11.0`, `pytest>=7.4.0`, `pytest-asyncio>=0.23.0`; documented optional `resend`.
- **`.gitignore`** — added `temp_pdf/`.

---

## [4.6.x] — 2026-02 / 2026-03

### Added
- Termin bundle subscriptions: 24h, 7-day, family bundle, priority boost, reservation finalization.
- `claim_email_send()` idempotency guard — prevents duplicate email sends on webhook replay.
- `is_order_delivered()` + `mark_order_delivered()` — idempotent delivery tracking.
- Support AI handler (`handlers/support_ai.py`) with OpenAI backend.
- `what_to_do` post-payment flow (`handlers/what_to_do.py`, `backend/what_to_do_config.py`).
- RTL Arabic PDF support (`backend/rtl_fix.py`, `backend/rtl_support.py`, NotoSansArabic font).
- Multi-language email templates (DE / EN / UK / PL / TR / AR).
- `termin_activation.py` handler — decoupled from main bot flow.

### Fixed
- Duplicate PDF delivery race condition — `claim_delivery()` atomic PAID→PROCESSING transition.
- Arabic/Hebrew text rendering in PDF overlays.

---

## [4.0.0] — 2024-12

### Added
- Stripe Checkout integration with `checkout.session.completed` webhook.
- WebApp (Telegram Mini App) form with dynamic JSON schemas.
- AcroForm + overlay + builder PDF pipeline.
- GDPR consent flow at `/start`.
- `bot_config/menu_structure.py` as single source of truth for document menu.
- `bot_config/pricing.py` — `PDF_PRICES` as single source of truth for prices.
- WAL mode on SQLite.
- `DEPLOY.md` — production ops guide (email/DNS setup, Stripe webhook, health check).

---

## [3.x] and earlier

Legacy aiogram 1.x codebase. Entry point was `main.py` (now deprecated — exits with error).
