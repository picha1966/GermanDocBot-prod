# -*- coding: utf-8 -*-
"""
Stripe Payment Integration для Telegram Bot v5.0
Використовує Checkout Session для оплати документів
"""

import asyncio
import logging
import stripe
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bot_config.pricing import PDF_PRICES

logger = logging.getLogger(__name__)


@dataclass
class CheckoutResult:
    """Результат створення Checkout Session"""
    success: bool
    session_id: Optional[str] = None
    checkout_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class PaymentStatus:
    """Статус платежу"""
    status: str
    payment_status: str
    amount_total: int
    currency: str
    metadata: Dict
    customer_email: Optional[str] = None


class StripePaymentHandler:
    """
    Обробник платежів через Stripe Checkout
    Оптимізований для Telegram Bot v5.0
    """
    
    # All document prices come from bot_config.pricing.PDF_PRICES — single source of truth.
    DOCUMENT_PRICES = PDF_PRICES

    def __init__(self, settings):
        """
        Ініціалізація обробника
        
        Args:
            settings: Settings об'єкт з конфігурацією
        """
        self.settings = settings
        stripe.api_key = settings.stripe.STRIPE_API_KEY
    
    def _round_price(self, value: float) -> Decimal:
        """
        Округлення ціни через Decimal для точності
        
        Args:
            value: Ціна для округлення
            
        Returns:
            Округлена ціна як Decimal
        """
        return Decimal(str(value)).quantize(Decimal('0.01'))
    
    def get_price(self, doc_type: str, db_price: float = None) -> float:
        """Return price for *doc_type*.

        DB price takes priority (admin override).  Falls back to PDF_PRICES.
        Raises ValueError on unknown doc_type — NEVER proceeds to Stripe with 0.
        """
        if db_price is not None:
            return db_price
        price = self.DOCUMENT_PRICES.get(doc_type)
        if price is None:
            logger.error("STRIPE_PRICE_MISSING_CRITICAL: doc_type=%r not in DOCUMENT_PRICES", doc_type)
            raise ValueError(
                f"Stripe price not found for doc_type={doc_type!r}. "
                "Add it to bot_config/pricing.py → PDF_PRICES."
            )
        return price
    
    async def create_checkout_session(
        self,
        order_id: int,
        user_id: int,
        doc_type: str,
        price: float,
        customer_email: str = None,
        discount: float = 0.0,
        promo_code: str = None,
        user_lang: str = 'uk',
        success_url: str = None,
        cancel_url: str = None,
        extra_metadata: dict = None,
    ) -> CheckoutResult:
        """
        Створити Stripe Checkout Session
        
        Args:
            order_id: ID замовлення в нашій БД
            user_id: Telegram user ID
            doc_type: Тип документа
            price: Ціна в EUR
            customer_email: Email клієнта (опціонально)
            discount: Знижка в EUR
            promo_code: Промокод (для metadata)
            user_lang: Мова користувача
            
        Returns:
            CheckoutResult з URL для оплати
        """
        try:
            # Обчислюємо фінальну ціну з точним округленням
            final_price = self._round_price(max(price - discount, 0.01))
            
            # Конвертуємо в центи через Decimal для точності
            amount_cents = int(final_price * 100)
            
            # success_url is always a direct Telegram deep-link (same pattern as Termin module).
            # Stripe redirects straight to t.me — no intermediate success page.
            if not success_url or not cancel_url:
                import os
                _bot_username_fb = os.getenv("BOT_USERNAME", "DE_PDF_Assistant_bot")
                webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
                success_url = success_url or f"https://t.me/{_bot_username_fb}?start=paid_{order_id}"
                cancel_url = cancel_url or f"{webapp_url}/payment-cancel?order_id={order_id}&lang={user_lang}"
            
            # Формуємо metadata для ідентифікації (критично для Webhook)
            metadata = {
                'order_id': str(order_id),
                'user_id': str(user_id),
                'doc_type': doc_type,
                'user_lang': user_lang,
                'original_price': str(price),
                'discount': str(discount),
                'source': 'telegram_bot'
            }
            
            if promo_code:
                metadata['promo_code'] = promo_code
            
            if extra_metadata:
                metadata.update(extra_metadata)
            
            # ── Product names ─────────────────────────────────────────────────
            _PRODUCT_NAMES = {
                'termin_monitor_24h':    ('24h Termin Monitoring',     '24-hour appointment slot monitoring'),
                'termin_extend_24h':     ('Termin Extend +24h',        'Extend monitoring by another 24 hours'),
                'termin_priority_boost': ('Termin Priority Boost',     'Priority slot alerts — 60 % higher chance'),
                'termin_reservation':    ('Appointment Slot Booking',  'Appointment slot monitoring service'),
            }
            _pname, _pdesc = _PRODUCT_NAMES.get(
                doc_type,
                (
                    f'CivicAssistBot — {doc_type.replace("_", " ").title()}',
                    f'Filled document template · Order #{order_id}',
                ),
            )

            # ── Session params ────────────────────────────────────────────────
            # payment_method_types=["card"] enables Card + Apple Pay + Google Pay
            # and disables Stripe Link ("Confirm it's you" phone screen).
            session_params = {
                'mode': 'payment',
                'payment_method_types': ['card'],
                'customer_creation': 'if_required',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'metadata': metadata,
                'client_reference_id': str(order_id),
                'allow_promotion_codes': False,
                # Capture billing details (needed for Apple Pay / Google Pay name + email)
                'billing_address_collection': 'auto',
                'payment_intent_data': {
                    'metadata': metadata,
                    # Statement descriptor shown on bank / card statement (22 chars max)
                    'statement_descriptor_suffix': 'CivicAssistBot',
                },
                'line_items': [{
                    'price_data': {
                        'currency': 'eur',
                        'unit_amount': amount_cents,
                        'product_data': {
                            'name': _pname,
                            'description': _pdesc,
                        },
                    },
                    'quantity': 1,
                }],
            }

            # ── Non-blocking Stripe call ──────────────────────────────────────
            # stripe-python is a synchronous library.  Running it directly in an
            # async handler would block the entire event loop for ~200–500 ms.
            # run_in_executor offloads the blocking HTTP call to a thread.
            _loop = asyncio.get_event_loop()
            session = await _loop.run_in_executor(
                None,
                lambda: stripe.checkout.Session.create(**session_params),
            )

            return CheckoutResult(
                success=True,
                session_id=session.id,
                checkout_url=session.url,
            )

        except stripe.error.StripeError as e:
            return CheckoutResult(success=False, error=f"Stripe error: {e}")
        except Exception as e:
            return CheckoutResult(success=False, error=f"Error: {e}")
    
    async def get_session_status(self, session_id: str) -> Optional[PaymentStatus]:
        """
        Отримати статус Checkout Session
        
        Args:
            session_id: Stripe session ID
            
        Returns:
            PaymentStatus або None
        """
        try:
            _loop = asyncio.get_event_loop()
            session = await _loop.run_in_executor(
                None,
                lambda: stripe.checkout.Session.retrieve(session_id),
            )

            return PaymentStatus(
                status=session.status,
                payment_status=session.payment_status,
                amount_total=session.amount_total,
                currency=session.currency,
                metadata=dict(session.metadata or {}) if hasattr(session, "metadata") else {},
                customer_email=session.customer_details.email if session.customer_details else None,
            )
            
        except stripe.error.StripeError:
            return None
        except Exception:
            return None
    
    async def verify_payment(self, session_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Verify payment. Webhook is source of truth; this is for redirect/UI only.
        - PAID: only if Stripe returns payment_status == "paid" (and session complete).
        - PROCESSING: status in ["open", "processing"] or payment_status "unpaid" — never treat as error.
        - EXPIRED: session.status == "expired".
        - FAILED: only if Stripe explicitly returns payment_status == "failed".
        """
        if not session_id or not str(session_id).strip():
            return False, {'session_status': 'missing'}
        status = await self.get_session_status(session_id)
        if not status:
            return False, {'session_status': 'processing', 'session_id': session_id}
        payment_data = {
            'session_id': session_id,
            'status': status.status,
            'payment_status': status.payment_status,
            'amount': status.amount_total / 100 if status.amount_total else 0,
            'currency': (status.currency or '').upper(),
            'metadata': dict(status.metadata or {}) if hasattr(status, "metadata") else {},
            'verified_at': datetime.now().isoformat(),
        }
        if status.status == 'expired':
            payment_data['session_status'] = 'expired'
            return False, payment_data
        if status.payment_status == 'failed':
            payment_data['session_status'] = 'failed'
            return False, payment_data
        if status.status == 'complete' and status.payment_status == 'paid':
            return True, payment_data
        # open / processing / unpaid — processing; NEVER error
        payment_data['session_status'] = 'processing'
        return False, payment_data
    
    def generate_payment_link(
        self,
        order_id: int,
        doc_type: str
    ) -> str:
        """
        Генерувати deep link для повернення в бот після оплати
        
        Args:
            order_id: ID замовлення
            doc_type: Тип документа
            
        Returns:
            Deep link URL
        """
        bot_username = self.settings.bot.BOT_USERNAME
        return f"https://t.me/{bot_username}?start=payment_{order_id}"


# ==================== UTILITY FUNCTIONS ====================

def format_price(price: float, currency: str = 'EUR') -> str:
    """Форматувати ціну для відображення"""
    symbols = {'EUR': '€', 'USD': '$', 'UAH': '₴'}
    symbol = symbols.get(currency.upper(), currency)
    return f"{price:.2f}{symbol}"


def calculate_discount(original_price: float, discount_type: str, discount_value: float) -> float:
    """
    Розрахувати знижку
    
    Args:
        original_price: Оригінальна ціна
        discount_type: 'percent' або 'fixed'
        discount_value: Значення знижки
        
    Returns:
        Сума знижки в EUR
    """
    if discount_type == 'percent':
        return original_price * (discount_value / 100)
    else:  # fixed
        return min(discount_value, original_price)


# Екземпляр для handlers (get_stripe_handler())
try:
    from backend.settings import settings
except ImportError:
    from settings import settings
stripe_handler = StripePaymentHandler(settings)