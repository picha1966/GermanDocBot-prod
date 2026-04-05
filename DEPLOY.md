# GermanDocBot — deployment notes

## Environment variables (REQUIRED)

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `STRIPE_SECRET_KEY` or `STRIPE_API_KEY` | Stripe secret API key (Checkout) |
| `STRIPE_WEBHOOK_SECRET` | Signing secret for `POST /stripe-webhook` |

Also set **`WEBAPP_URL`** (public HTTPS URL to the form) for the in-bot WebApp.

Optional: `BOT_USERNAME`, `ADMIN_IDS`, `REDIS_URL`, etc. — see `.env.example`.

**Production safety**

- Set **`ENV=production`** (or **`APP_ENV=production`**) on live servers.
- **`STRIPE_ALLOW_UNVERIFIED_WEBHOOKS`** must **not** be set in production — the process exits on startup if both are true.

## Start

```bash
python bot.py
```

(`python app.py` delegates to the same `main()`.)

## Health check

- **HTTP:** `GET http://127.0.0.1:4243/health` → JSON `{"status":"ok","service":"german-doc-bot"}` (liveness, no DB).
- **Telegram:** command `/health` — Termin monitor snapshot (separate from HTTP).

## Webhook

- **URL:** `POST https://YOUR_DOMAIN/stripe-webhook` (reverse-proxy to port **4243**).
- **Signing:** required in production; without `STRIPE_WEBHOOK_SECRET` the handler returns **400** `Webhook not configured` (unless dev override below).

**Local / Stripe CLI only:** `STRIPE_ALLOW_UNVERIFIED_WEBHOOKS=true` — never with `ENV=production`.

---

## Process

- Do **not** use `main.py` as an entrypoint — it exits with an error by design.

## HTTP (same process as the bot)

- Listens on **`0.0.0.0:4243`**.
- **Stripe:** `POST /stripe-webhook` — endpoint for Stripe Dashboard (PDF/Termin finalization).
- **WebApp:** `GET /`, `/form`, `/api/form-schema`, `POST /webapp-submit`.
- **Checkout return:** `GET /payment-success`, `GET /payment-cancel`.

## Not for Stripe

- **`webapp_server.py`** / **`uvicorn webapp_server:app`** — optional static WebApp only; **do not** point production Stripe webhooks here.

## Environment file

- Copy **`.env.example`** → **`.env`**.

---

## Email Delivery Setup

After a successful Stripe payment the bot:
1. Sends the filled PDF via Telegram.
2. Sends the same PDF as an email attachment to the address from `session.customer_details.email`.
3. Sends a Telegram confirmation message with the recipient email.

### Step 1 — Choose an email provider

Pick **one** of three backends (priority: SendGrid → Resend → SMTP):

| Provider | Env var | Free tier | Best for |
|----------|---------|-----------|----------|
| **SendGrid** | `SENDGRID_API_KEY` | 100 emails/day | Production (best deliverability) |
| **Resend** | `RESEND_API_KEY` | 3 000/month | Modern API, easy setup |
| **SMTP** | `EMAIL_SMTP_HOST` + credentials | Varies | Self-hosted / Gmail |

#### SendGrid
```
SENDGRID_API_KEY=SG.xxxxxxxxxxxxx
EMAIL_FROM=CivicAssistBot <noreply@yourdomain.com>
```

#### Resend
```
RESEND_API_KEY=re_xxxxxxxxxxxxx
EMAIL_FROM=CivicAssistBot <noreply@yourdomain.com>
```
Install: `pip install resend`

#### SMTP (Gmail example)
```
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=noreply@yourdomain.com
EMAIL_SMTP_PASS=your_16_char_app_password
EMAIL_FROM=CivicAssistBot <noreply@yourdomain.com>
```
For Gmail: use an **App Password** (Google Account → Security → App Passwords).

---

### Step 2 — DNS records for trusted delivery

Configure these DNS records for your sending domain (e.g. `yourdomain.com`).
Without them, emails land in spam or are rejected.

#### SPF — authorize your mail server

Add a `TXT` record to `yourdomain.com`:

```
v=spf1 include:sendgrid.net ~all        # SendGrid
v=spf1 include:amazonses.com ~all       # SES
v=spf1 mx ~all                          # Own mail server
```

Replace `include:` with your provider's SPF string.

#### DKIM — cryptographic signature

Each provider generates a DKIM key pair. Add the `CNAME` (or `TXT`) records they give you:

**SendGrid:** Settings → Sender Authentication → Domain Authentication → follow wizard → add 3 CNAME records.

**Resend:** Domains → Add Domain → add the 2–3 DNS records shown.

**Self-hosted:** Generate with `opendkim-genkey -s mail -d yourdomain.com`, add the `TXT` record for `mail._domainkey.yourdomain.com`.

#### DMARC — policy that ties SPF + DKIM together

Add a `TXT` record to `_dmarc.yourdomain.com`:

```
v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com; pct=100
```

| Tag | Meaning |
|-----|---------|
| `p=none` | Monitor only (start here) |
| `p=quarantine` | Move failing mail to spam |
| `p=reject` | Reject failing mail (strictest) |

Start with `p=none` while you verify alignment, then raise to `p=quarantine`.

#### BIMI (optional — logo in Gmail/Apple Mail)

Once DMARC is at `p=quarantine` or `p=reject`:

1. Host the CivicAssistBot logo as a square SVG at `https://yourdomain.com/logo.svg`.
2. Add a `TXT` record to `default._bimi.yourdomain.com`:
   ```
   v=BIMI1; l=https://yourdomain.com/logo.svg;
   ```
3. For Gmail's verified checkmark: obtain a **VMC (Verified Mark Certificate)** from DigiCert or Entrust — requires a registered trademark.

**Note:** BIMI is purely cosmetic (logo in inbox). It has zero effect on deliverability.

---

### Step 3 — Verify

1. Send a test email: set `EMAIL_SMTP_*` and run:
   ```bash
   python -c "
   import asyncio
   from utils.email_sender import send_pdf_by_email
   asyncio.run(send_pdf_by_email('you@example.com', 'outputs/smoke/anmeldung_test.pdf', 'anmeldung', 'en'))
   "
   ```
2. Check [mail-tester.com](https://www.mail-tester.com) — score should be ≥ 9/10.
3. Check [MXToolbox SuperTool](https://mxtoolbox.com/SuperTool.aspx) → SPF / DKIM / DMARC lookups.

---

### Email design

The HTML email uses CivicAssistBot branding:
- Dark navy header (`#0d1f3c → #1b4db5` gradient)
- Amber disclaimer box (legal notice: "NOT an official document")
- Step-by-step instructions
- Official form link button
- Telegram AI support link
- Languages: `de`, `en`, `uk`, `pl`, `tr`, `ar`

PDF filename delivered: `{doc_type}_filled_sample.pdf`
