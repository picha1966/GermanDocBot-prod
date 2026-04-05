# Process Supervisor — CivicAssistBot v5.0

Бот запускається як **один процес** (`bot.py`): Telegram polling, HTTP-сервер
на порту **4243**, Stripe webhook і Termin-моніторинг — усе в одному.

---

## Варіант 1: systemd (рекомендовано для VPS/Debian/Ubuntu)

### 1. Створіть service-файл

```bash
sudo nano /etc/systemd/system/civicassistbot.service
```

Вставте:

```ini
[Unit]
Description=CivicAssistBot — German Documents Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/civicassistbot
# Завантажує змінні з .env — НАЙБЕЗПЕЧНІШИЙ спосіб зберігання секретів
EnvironmentFile=/opt/civicassistbot/.env
ExecStart=/opt/civicassistbot/venv/bin/python bot.py
Restart=on-failure
RestartSec=10s
# Обмеження ресурсів
LimitNOFILE=65536
# Логи через journald
StandardOutput=journal
StandardError=journal
SyslogIdentifier=civicassistbot

[Install]
WantedBy=multi-user.target
```

### 2. Увімкніть і запустіть

```bash
sudo systemctl daemon-reload
sudo systemctl enable civicassistbot
sudo systemctl start civicassistbot
```

### 3. Корисні команди

```bash
# Статус
sudo systemctl status civicassistbot

# Живі логи
sudo journalctl -u civicassistbot -f

# Перезапуск (після деплою нового коду)
sudo systemctl restart civicassistbot

# Зупинити
sudo systemctl stop civicassistbot
```

---

## Варіант 2: Supervisor

### 1. Встановлення

```bash
apt-get update && apt-get install -y supervisor
```

### 2. Обгортка для завантаження .env

Supervisor не підтримує `EnvironmentFile`, тому створіть обгортку:

```bash
cat > /opt/civicassistbot/start_bot.sh << 'EOF'
#!/bin/bash
set -a
source /opt/civicassistbot/.env
set +a
exec /opt/civicassistbot/venv/bin/python bot.py
EOF
chmod +x /opt/civicassistbot/start_bot.sh
```

### 3. Змінна шляху у конфізі

Відредагуйте `supervisor/webapp.conf`:
- `directory=` → ваш реальний шлях до проєкту
- `command=` → шлях до `start_bot.sh`
- `user=` → системний користувач (не root)

### 4. Скопіюйте конфіг

```bash
sudo mkdir -p /etc/supervisor/conf.d
sudo cp /opt/civicassistbot/supervisor/webapp.conf /etc/supervisor/conf.d/civicassistbot.conf
```

### 5. Увімкніть

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start civicassistbot
```

### Корисні команди

```bash
# Статус
sudo supervisorctl status civicassistbot

# Логи
tail -f /opt/civicassistbot/logs/bot_stdout.log
tail -f /opt/civicassistbot/logs/bot_stderr.log

# Перезапуск
sudo supervisorctl restart civicassistbot
```

---

## Nginx (reverse proxy для Stripe webhook і WebApp)

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Stripe webhook + WebApp form + health check
    location / {
        proxy_pass         http://127.0.0.1:4243;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        # Stripe webhooks можуть мати великий payload
        client_max_body_size 2M;
    }
}

# Редирект HTTP → HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

Отримати SSL-сертифікат:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

---

## Health check

```bash
# HTTP liveness
curl http://127.0.0.1:4243/health

# Очікувана відповідь:
# {"status":"ok","service":"german-doc-bot"}
```

---

## Порти

| Сервіс | Порт | Призначення |
|--------|------|-------------|
| bot.py | 4243 | Stripe webhook, WebApp, health |
| Nginx  | 443  | Public HTTPS → 4243 |

**Не використовуйте `webapp_server.py` для Stripe** — він не приймає вебхуки. Детальніше: `DEPLOY.md`.
