# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v5.0 - Global Settings Configuration
Централізований конфіг для всіх налаштувань бота
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
import logging
import os

from bot_config.pricing import PDF_PRICES

logger = logging.getLogger(__name__)


# ============================================================================
# BOT CONFIGURATION
# ============================================================================

@dataclass
class BotConfig:
    """Основні налаштування бота"""
    
    # Telegram Bot: BOT_TOKEN або TELEGRAM_BOT_TOKEN, BOT_USERNAME з .env
    API_TOKEN: str = os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_TOKEN_HERE')
    BOT_USERNAME: str = os.environ.get('BOT_USERNAME', 'german_doc_bot')
    BOT_NAME: str = "German Doc Bot Premium"
    BOT_VERSION: str = "5.0.0"
    
    # Admin IDs — читаються з ADMIN_IDS env (одне число або кілька через кому).
    # Приклад: ADMIN_IDS=123456789,987654321
    # Якщо змінна не задана — адмін-панель недоступна нікому.
    ADMIN_IDS: List[int] = field(default_factory=lambda: [
        int(x.strip())
        for x in os.environ.get("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ])
    
    # Support Links
    SUPPORT_GROUP: str = "@german_doc_support"
    NEWS_CHANNEL: str = "@german_doc_news"
    SUPPORT_EMAIL: str = "support@germandocbot.com"
    
    # WebApp URL з .env або за замовчуванням
    WEBAPP_URL: str = os.environ.get('WEBAPP_URL', 'https://termin-assist.de/form')
  
    # Default Language
    DEFAULT_LANGUAGE: str = "ua"
    SUPPORTED_LANGUAGES: List[str] = field(default_factory=lambda: ['ua', 'de', 'en', 'pl', 'tr', 'ar'])


@dataclass
class PricingConfig:
    """Налаштування цін (EUR) — all documents.

    Prices come from bot_config.pricing.PDF_PRICES (single source of truth).
    Do NOT hardcode prices here.
    """

    # Delegate to single source of truth.
    CUSTOM_PRICES: Dict[str, float] = field(default_factory=lambda: dict(PDF_PRICES))

    CURRENCY: str = "EUR"
    CURRENCY_SYMBOL: str = "€"

    def get_price(self, doc_type: str) -> float:
        """Return price for *doc_type*.

        Raises ValueError on unknown doc_type — never returns 0.0.
        """
        price = self.CUSTOM_PRICES.get(doc_type)
        if price is None:
            logger.error("PRICE_MISSING_CRITICAL: doc_type=%r not found in CUSTOM_PRICES", doc_type)
            raise ValueError(f"Price not found for doc_type={doc_type!r}. Add it to bot_config/pricing.py → PDF_PRICES.")
        return price


@dataclass
class PaymentConfig:
    """Налаштування платежів"""
    # Stripe: STRIPE_API_KEY або STRIPE_SECRET_KEY (обидва варіанти підтримуються)
    STRIPE_API_KEY: str = os.environ.get('STRIPE_API_KEY') or os.environ.get('STRIPE_SECRET_KEY', 'sk_test_placeholder')
    STRIPE_WEBHOOK_SECRET: str = os.environ.get('STRIPE_WEBHOOK_SECRET', '')


@dataclass
class EmailConfig:
    """Email доставка PDF після оплати.

    Підтримує три бекенди (автовизначення за env-змінними, пріоритет зверху вниз):
      1. SendGrid  — SENDGRID_API_KEY
      2. Resend    — RESEND_API_KEY
      3. SMTP      — EMAIL_SMTP_HOST + EMAIL_SMTP_PORT + EMAIL_SMTP_USER + EMAIL_SMTP_PASS

    EMAIL_FROM      — адреса відправника (default: noreply@germandocbot.com)
    EMAIL_ENABLED   — "0" щоб повністю вимкнути email доставку
    """
    SENDGRID_API_KEY: str = os.environ.get('SENDGRID_API_KEY', '')
    RESEND_API_KEY: str = os.environ.get('RESEND_API_KEY', '')
    SMTP_HOST: str = os.environ.get('EMAIL_SMTP_HOST', '')
    SMTP_PORT: int = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
    SMTP_USER: str = os.environ.get('EMAIL_SMTP_USER', '')
    SMTP_PASS: str = os.environ.get('EMAIL_SMTP_PASS', '')
    FROM_ADDRESS: str = os.environ.get('EMAIL_FROM', 'noreply@germandocbot.com')
    ENABLED: bool = os.environ.get('EMAIL_ENABLED', '1').strip() not in ('0', 'false', 'no')

    def is_configured(self) -> bool:
        """True якщо хоча б один email бекенд налаштований."""
        return bool(self.SENDGRID_API_KEY or self.RESEND_API_KEY or self.SMTP_HOST)


@dataclass
class PDFConfig:
    """Налаштування PDF та Шляхів"""
    DOCS_DIR: str = "docs"
    PREVIEWS_DIR: str = "previews"
    TEMPLATES_DIR: str = "templates"
    FONTS_DIR: str = "fonts"
    
    # Ватермарка для прев'ю
    WATERMARK: str = "PREVIEW COPY"


@dataclass
class FeatureFlags:
    """Увімкнення/Вимкнення модулів"""
    ENABLE_GDPR: bool = True
    ENABLE_PROMO: bool = True
    ENABLE_DRAFTS: bool = True
    ENABLE_FAMILY: bool = True


# ============================================================================
# ГОЛОВНИЙ КЛАС SETTINGS (SINGLETON)
# ============================================================================

class Settings:
    def __init__(self):
        self.bot = BotConfig()
        self.pricing = PricingConfig()
        self.payment = PaymentConfig()
        self.stripe = self.payment  # аліас для backend.stripe_handler (STRIPE_API_KEY, STRIPE_WEBHOOK_SECRET)
        self.pdf = PDFConfig()
        self.features = FeatureFlags()
        self.email = EmailConfig()
        self.db_name = "bot_database.db"

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.bot.ADMIN_IDS

    def format_price(self, price: float) -> str:
        return f"{price:.2f}{self.pricing.CURRENCY_SYMBOL}"


# Створюємо один екземпляр для всього проекту
settings = Settings()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_admin_ids() -> List[int]:
    """
    Get list of admin user IDs.
    Canonical source for admin IDs across the entire application.
    """
    return settings.bot.ADMIN_IDS