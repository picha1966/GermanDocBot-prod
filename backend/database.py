# -*- coding: utf-8 -*-
"""
backend/database.py
Оновлена версія — виправлення помилок логів, мова та GDPR у users
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status enum for payment tracking. Lifecycle: CREATED -> PENDING -> PROCESSING -> PAID -> DELIVERED."""
    PENDING = "pending"
    PROCESSING = "processing"  # Payment check in progress; idempotency guard
    PAID = "paid"
    SENT = "sent"
    DOWNLOADED = "downloaded"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL mode: allows concurrent reads + one writer without blocking.
        # Critical for webhook + deep-link arriving simultaneously.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()
        logger.info("✅ Database initialized (WAL mode)")

    # ======================================================================
    # TABLES
    # ======================================================================

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()

        # USERS (основна таблиця)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                lang TEXT DEFAULT 'uk',
                gdpr_accepted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ORDERS table for payment tracking
        # Used by: handlers/stripe_handler.py, handlers/docs_new.py
        # Minimal schema with required fields for payment flow
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                doc_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                stripe_session_id TEXT,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'EUR',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Add optional columns if they don't exist (for backward compatibility)
        # These are needed by handlers but added via ALTER TABLE to avoid breaking existing DBs
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN price REAL")
            logger.debug("✅ Added price column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN user_data TEXT")
            logger.debug("✅ Added user_data column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN lang TEXT DEFAULT 'uk'")
            logger.debug("✅ Added lang column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN file_path TEXT")
            logger.debug("✅ Added file_path column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN paid_at TIMESTAMP")
            logger.debug("✅ Added paid_at column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN delivered INTEGER DEFAULT 0")
            logger.debug("✅ Added delivered column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN email_sent INTEGER DEFAULT 0")
            logger.debug("✅ Added email_sent column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN customer_email TEXT DEFAULT NULL")
            logger.debug("✅ Added customer_email column to orders table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN country TEXT DEFAULT 'DE'")
            logger.debug("✅ Added country column to users table")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # ── Referral system migrations ─────────────────────────────────────────
        # referral_code  — unique shareable code for this user
        # referral_count — how many friends have paid via this user's link
        # free_doc_credits — earned free document slots (1 per 2 referrals)
        for _col, _def in [
            ("referral_code",      "TEXT DEFAULT NULL"),
            ("referral_code_used", "TEXT DEFAULT NULL"),
            ("referral_count",     "INTEGER DEFAULT 0"),
            ("free_doc_credits",   "INTEGER DEFAULT 0"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {_col} {_def}")
                logger.debug("✅ Added %s column to users table", _col)
            except sqlite3.OperationalError:
                pass

        # referrals table — one row per successful paid referral
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referee_id  INTEGER NOT NULL UNIQUE,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referee_id)  REFERENCES users(user_id)
            )
        """)

        # analytics_events — funnel & UX event log (append-only)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                event_type TEXT NOT NULL,
                doc_type   TEXT,
                step_name  TEXT,
                event_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()
        logger.info("✅ Tables checked/created")

    # ======================================================================
    # USERS
    # ======================================================================

    def create_user(
        self,
        user_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None
    ) -> None:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (
                    user_id, username, first_name, last_name
                )
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, last_name))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ create_user: {e}")

    def update_last_active(self, user_id: int) -> None:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE users
                SET last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ update_last_active: {e}")

    def get_profile(self, user_id: int) -> Optional[dict]:
        """Get user profile as dictionary"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM users WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"❌ get_profile: {e}")
            return None

    def get_or_create_user(
        self,
        user_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        referral_code_used: str = None
    ) -> Optional[dict]:
        """Get user if exists, otherwise create and return profile"""
        try:
            # Check if user exists
            profile = self.get_profile(user_id)
            if profile:
                # User exists, return profile
                return profile
            
            # User does not exist, create it
            self.create_user(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            
            # Return the newly created profile
            return self.get_profile(user_id)
        except Exception as e:
            logger.error(f"❌ get_or_create_user: {e}")
            return None

    # ======================================================================
    # LANGUAGE
    # ======================================================================

    def set_user_lang(self, user_id: int, lang: str) -> None:
        try:
            self.create_user(user_id)
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE users
                SET lang = ?
                WHERE user_id = ?
            """, (lang, user_id))
            self.conn.commit()
            logger.info(f"✅ Language set: {user_id} -> {lang}")
        except Exception as e:
            logger.error(f"❌ set_user_lang: {e}")

    def update_user_language(self, user_id: int, lang: str) -> None:
        """Alias для сумісності"""
        self.set_user_lang(user_id, lang)

    def get_user_lang(self, user_id: int) -> str:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT lang FROM users WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            return row["lang"] if row and row["lang"] else "uk"
        except Exception as e:
            logger.error(f"❌ get_user_lang: {e}")
            return "uk"

    # ======================================================================
    # COUNTRY
    # ======================================================================

    def set_user_country(self, user_id: int, country: str) -> None:
        try:
            self.create_user(user_id)
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE users
                SET country = ?
                WHERE user_id = ?
            """, (country.upper(), user_id))
            self.conn.commit()
            logger.info(f"✅ Country set: {user_id} -> {country.upper()}")
        except Exception as e:
            logger.error(f"❌ set_user_country: {e}")

    def get_user_country(self, user_id: int) -> str:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT country FROM users WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            return row["country"] if row and row["country"] else "DE"
        except Exception as e:
            logger.error(f"❌ get_user_country: {e}")
            return "DE"

    # ======================================================================
    # GDPR
    # ======================================================================

    def set_gdpr_consent(self, user_id: int, accepted: bool) -> None:
        try:
            self.create_user(user_id)
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE users
                SET gdpr_accepted = ?
                WHERE user_id = ?
            """, (1 if accepted else 0, user_id))
            self.conn.commit()
            logger.info(f"✅ GDPR consent set: {user_id} -> {accepted}")
        except Exception as e:
            logger.error(f"❌ set_gdpr_consent: {e}")

    def mark_gdpr_accepted(self, user_id: int) -> None:
        self.set_gdpr_consent(user_id, True)

    def get_gdpr_status(self, user_id: int) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT gdpr_accepted FROM users WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            return bool(row["gdpr_accepted"]) if row else False
        except Exception as e:
            logger.error(f"❌ get_gdpr_status: {e}")
            return False

    # ======================================================================
    # REFERRAL SYSTEM
    # ======================================================================

    def get_or_create_referral_code(self, user_id: int) -> str:
        """
        Return this user's unique referral code, creating one if needed.
        Code format: REF + 8 random hex chars (uppercase), e.g. REF3A7F2B9C.
        Cryptographically random — avoids user_id enumeration.
        """
        import secrets as _secrets
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            existing = row["referral_code"] if row else None
            if existing:
                return existing
            code = "REF" + _secrets.token_hex(4).upper()
            cursor.execute(
                "UPDATE users SET referral_code = ? WHERE user_id = ?",
                (code, user_id),
            )
            self.conn.commit()
            return code
        except Exception as e:
            logger.error("get_or_create_referral_code: %s", e)
            return "REF" + _secrets.token_hex(4).upper()

    def set_referral_code_used(self, user_id: int, code: str) -> None:
        """Store which referral code this user joined via (pending — not counted yet)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET referral_code_used = ? WHERE user_id = ? AND referral_code_used IS NULL",
                (code, user_id),
            )
            self.conn.commit()
        except Exception as e:
            logger.error("set_referral_code_used: %s", e)

    def get_referral_code_used(self, user_id: int) -> Optional[str]:
        """Return the referral code this user joined via, or None."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT referral_code_used FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return row["referral_code_used"] if row else None
        except Exception as e:
            logger.error("get_referral_code_used: %s", e)
            return None

    def peek_free_doc_credit(self, user_id: int) -> bool:
        """Check if user has at least 1 free document credit WITHOUT consuming it."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT free_doc_credits FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return int(row["free_doc_credits"] or 0) > 0 if row else False
        except Exception as e:
            logger.error("peek_free_doc_credit: %s", e)
            return False

    def get_referral_stats(self, user_id: int) -> dict:
        """Return {'count': int, 'credits': int} for a user's referral activity."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT referral_count, free_doc_credits FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                return {"count": int(row["referral_count"] or 0), "credits": int(row["free_doc_credits"] or 0)}
        except Exception as e:
            logger.error("get_referral_stats: %s", e)
        return {"count": 0, "credits": 0}

    def register_referral(self, referral_code: str, referee_id: int) -> bool:
        """
        Record that *referee_id* joined via *referral_code*.
        Increments the referrer's counter; awards a free doc credit every 2 referrals.
        Returns True if recorded, False if code unknown or already registered.
        """
        try:
            cursor = self.conn.cursor()
            # Resolve referrer
            cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
            row = cursor.fetchone()
            if not row:
                return False
            referrer_id = row["user_id"]
            if referrer_id == referee_id:
                return False  # Cannot refer yourself
            # Insert referral (UNIQUE constraint on referee_id prevents duplicates)
            try:
                cursor.execute(
                    "INSERT INTO referrals (referrer_id, referee_id) VALUES (?, ?)",
                    (referrer_id, referee_id),
                )
            except Exception:
                return False  # Already registered
            # Increment counter
            cursor.execute(
                "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?",
                (referrer_id,),
            )
            # Award free credit every 2 completed referrals
            cursor.execute(
                "SELECT referral_count FROM users WHERE user_id = ?", (referrer_id,)
            )
            count_row = cursor.fetchone()
            new_count = int((count_row["referral_count"] or 0)) if count_row else 0
            if new_count > 0 and new_count % 2 == 0:
                cursor.execute(
                    "UPDATE users SET free_doc_credits = free_doc_credits + 1 WHERE user_id = ?",
                    (referrer_id,),
                )
                logger.info("REFERRAL_CREDIT_AWARDED: referrer=%s count=%s", referrer_id, new_count)
            self.conn.commit()
            logger.info("REFERRAL_REGISTERED: referrer=%s referee=%s", referrer_id, referee_id)
            return True
        except Exception as e:
            logger.error("register_referral: %s", e)
            return False

    def use_free_doc_credit(self, user_id: int) -> bool:
        """
        Consume one free document credit.  Returns True if a credit was available.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT free_doc_credits FROM users WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            credits = int(row["free_doc_credits"] or 0) if row else 0
            if credits <= 0:
                return False
            cursor.execute(
                "UPDATE users SET free_doc_credits = free_doc_credits - 1 WHERE user_id = ?",
                (user_id,),
            )
            self.conn.commit()
            logger.info("FREE_DOC_CREDIT_USED: user=%s remaining=%s", user_id, credits - 1)
            return True
        except Exception as e:
            logger.error("use_free_doc_credit: %s", e)
            return False

    # ======================================================================
    # ORDERS (Payment tracking)
    # ======================================================================
    # Used by: handlers/stripe_handler.py (initiate_payment, check_payment_status, deliver_document)
    #          handlers/docs_new.py (_check_payment_status, handle_final_pdf)

    def create_order(
        self,
        user_id: int,
        doc_type: str,
        amount: float,
        currency: str = "EUR",
        stripe_session_id: Optional[str] = None,
        user_data: Optional[str] = None,
        lang: Optional[str] = None
    ) -> int:
        """
        Create a new order.
        
        Used by: handlers/docs_new.py (handle_final_pdf) when user requests full PDF
        Returns: order_id
        """
        try:
            cursor = self.conn.cursor()
            status = OrderStatus.PENDING.value
            # Use amount as price (for compatibility with handlers that expect 'price')
            price = amount
            cursor.execute("""
                INSERT INTO orders (user_id, doc_type, status, amount, price, currency, stripe_session_id, user_data, lang)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, doc_type, status, amount, price, currency, stripe_session_id, user_data, lang))
            self.conn.commit()
            order_id = cursor.lastrowid
            logger.info(f"✅ Order created: id={order_id} user_id={user_id} doc_type={doc_type} amount={amount}")
            return order_id
        except Exception as e:
            logger.error(f"❌ create_order failed: {e}")
            raise

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """
        Get order by order_id.
        
        Used by: handlers/stripe_handler.py (initiate_payment, check_payment_status, deliver_document)
        Returns dict with compatibility aliases: 'order_id' for 'id', 'price' for 'amount'
        """
        try:
            cursor = self.conn.cursor()
            # Use aliases for compatibility: id -> order_id, amount -> price
            cursor.execute("""
                SELECT 
                    id,
                    id as order_id,
                    user_id,
                    doc_type,
                    status,
                    stripe_session_id,
                    amount,
                    amount as price,
                    currency,
                    created_at,
                    user_data,
                    lang,
                    file_path,
                    paid_at,
                    customer_email
                FROM orders WHERE id = ?
            """, (order_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"❌ get_order failed: {e}")
            return None

    def get_order_by_session(self, stripe_session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order by Stripe session ID.
        
        Used by: Webhook handlers (when Stripe sends checkout.session.completed event)
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    id as order_id,
                    user_id,
                    doc_type,
                    status,
                    stripe_session_id,
                    amount,
                    amount as price,
                    currency,
                    created_at,
                    user_data,
                    lang,
                    file_path,
                    paid_at
                FROM orders WHERE stripe_session_id = ?
            """, (stripe_session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"❌ get_order_by_session failed: {e}")
            return None

    def mark_order_paid(self, stripe_session_id: str) -> bool:
        """
        Mark order as PAID by Stripe session ID.
        Accepts both PENDING and PROCESSING so webhook can complete when check is in progress.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE orders 
                SET status = ?, paid_at = CURRENT_TIMESTAMP
                WHERE stripe_session_id = ? AND status IN (?, ?)
            """, (OrderStatus.PAID.value, stripe_session_id, OrderStatus.PENDING.value, OrderStatus.PROCESSING.value))
            self.conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"✅ Order marked as paid: stripe_session_id={stripe_session_id}")
                return True
            else:
                logger.warning(f"⚠️ No order found or already paid: stripe_session_id={stripe_session_id}")
                return False
        except Exception as e:
            logger.error(f"❌ mark_order_paid failed: {e}")
            return False

    def user_has_paid(self, user_id: int, doc_type: str) -> bool:
        """
        Check if user has a paid order for this document type.
        
        Used by: handlers/docs_new.py (_check_payment_status)
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM orders 
                WHERE user_id = ? AND doc_type = ? AND status = ?
            """, (user_id, doc_type, OrderStatus.PAID.value))
            row = cursor.fetchone()
            return row["count"] > 0 if row else False
        except Exception as e:
            logger.error(f"❌ user_has_paid failed: {e}")
            return False

    def get_user_orders(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent orders for a user.
        
        Used by: handlers/docs_new.py (_check_payment_status)
        Returns list of dicts with compatibility aliases: 'order_id' for 'id'
        """
        try:
            cursor = self.conn.cursor()
            # Use alias for compatibility: id -> order_id
            cursor.execute("""
                SELECT 
                    id,
                    id as order_id,
                    user_id,
                    doc_type,
                    status,
                    stripe_session_id,
                    amount,
                    amount as price,
                    currency,
                    created_at,
                    user_data,
                    lang,
                    file_path,
                    paid_at
                FROM orders 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ get_user_orders failed: {e}")
            return []

    def claim_delivery(self, order_id: int) -> bool:
        """Atomically transition order from PAID → PROCESSING.

        Returns True only if this call was the one that changed the row
        (i.e. it won the race).  Returns False if the row was already
        PROCESSING / SENT / DOWNLOADED — meaning another concurrent caller
        already claimed it.

        SQLite serialises writers, so only one concurrent call can observe
        rowcount > 0, guaranteeing at-most-once PDF delivery even when the
        Stripe webhook and the Telegram deep-link arrive simultaneously.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE orders SET status = ? WHERE id = ? AND status = ?",
                (OrderStatus.PROCESSING.value, order_id, OrderStatus.PAID.value),
            )
            self.conn.commit()
            won = cursor.rowcount > 0
            if won:
                logger.info("claim_delivery WON: order_id=%s PAID→PROCESSING", order_id)
            else:
                logger.info("claim_delivery LOST: order_id=%s (already claimed or not PAID)", order_id)
            return won
        except Exception as exc:
            logger.error("claim_delivery failed: order_id=%s err=%s", order_id, exc)
            return False

    def update_order_status(
        self,
        order_id: int,
        new_status: OrderStatus,
        stripe_session_id: Optional[str] = None
    ) -> bool:
        """
        Update order status.
        
        Used by: handlers/stripe_handler.py (initiate_payment, check_payment_status, deliver_document)
        """
        try:
            cursor = self.conn.cursor()
            if stripe_session_id:
                cursor.execute("""
                    UPDATE orders 
                    SET status = ?, stripe_session_id = ?, paid_at = CASE WHEN ? = 'paid' THEN CURRENT_TIMESTAMP ELSE paid_at END
                    WHERE id = ?
                """, (new_status.value, stripe_session_id, new_status.value, order_id))
            else:
                cursor.execute("""
                    UPDATE orders 
                    SET status = ?, paid_at = CASE WHEN ? = 'paid' THEN CURRENT_TIMESTAMP ELSE paid_at END
                    WHERE id = ?
                """, (new_status.value, new_status.value, order_id))
            self.conn.commit()
            logger.info(f"✅ Order status updated: id={order_id} status={new_status.value}")
            return True
        except Exception as e:
            logger.error(f"❌ update_order_status failed: {e}")
            return False

    def reset_user_orders(self, user_id: int) -> int:
        """Mark all non-terminal orders for a user as FAILED.
        Only affects orders with status IN ('pending', 'processing', 'paid').
        Terminal statuses (sent, downloaded, cancelled, failed) are left untouched.
        Returns the number of rows updated.
        Used by: /reset command (developer/testing utility).
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE orders
                SET status = ?
                WHERE user_id = ?
                  AND status IN ('pending', 'processing', 'paid')
                """,
                (OrderStatus.FAILED.value, user_id),
            )
            self.conn.commit()
            updated = cursor.rowcount
            logger.info("reset_user_orders: user_id=%s rows_updated=%s", user_id, updated)
            return updated
        except Exception as e:
            logger.error("reset_user_orders failed: user_id=%s error=%s", user_id, e)
            return 0

    def is_order_delivered(self, order_id: int) -> bool:
        """Return True if the order's success screen has already been delivered.

        Used as an idempotency guard in handle_paid_deeplink to prevent
        duplicate success screens when the deep link fires multiple times.

        For termin-only orders the webhook sets status=PAID (not SENT), so the
        status-based fallback must NOT fire for them — only the explicit
        delivered=1 flag counts.  For document orders the fallback on
        status IN ('sent','downloaded') remains for backward compatibility with
        rows created before the delivered column was added.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT delivered, status, doc_type FROM orders WHERE id = ?",
                (order_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            # Primary signal: explicit delivered flag (set by mark_order_delivered)
            if row["delivered"]:
                return True
            # Fallback for legacy document orders only.
            # Termin-only orders must NOT use this fallback: their webhook correctly
            # sets status=PAID and delivery is done exclusively by the deeplink handler.
            _is_termin = (row["doc_type"] or "").startswith("termin_")
            if _is_termin:
                return False
            return (row["status"] or "").lower() in ("sent", "downloaded")
        except Exception as exc:
            logger.error("❌ is_order_delivered failed: order_id=%s err=%s", order_id, exc)
            return False

    def mark_order_delivered(self, order_id: int) -> bool:
        """Set delivered=1 on an order after the success screen is sent.

        Idempotent — safe to call multiple times; subsequent calls are no-ops
        because the UPDATE only touches rows where delivered=0.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE orders SET delivered = 1 WHERE id = ? AND (delivered IS NULL OR delivered = 0)",
                (order_id,),
            )
            self.conn.commit()
            if cursor.rowcount > 0:
                logger.info("✅ Order marked delivered: id=%s", order_id)
            return True
        except Exception as exc:
            logger.error("❌ mark_order_delivered failed: order_id=%s err=%s", order_id, exc)
            return False

    def claim_email_send(self, order_id: int) -> bool:
        """Atomically reserve the right to send the email for this order.

        Returns True only if THIS call flipped email_sent 0→1 (i.e. this caller
        won the race).  Returns False if another concurrent call already sent it.

        Pattern mirrors claim_delivery() — single UPDATE with WHERE guard so
        SQLite serialises writers and only one concurrent caller observes rowcount > 0.
        This prevents duplicate emails even when Stripe replays the webhook while
        a previous send is still in-flight (within the 15s timeout window).
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE orders SET email_sent = 1 WHERE id = ? AND (email_sent IS NULL OR email_sent = 0)",
                (order_id,),
            )
            self.conn.commit()
            won = cursor.rowcount > 0
            if won:
                logger.info("claim_email_send WON: order_id=%s", order_id)
            else:
                logger.info("claim_email_send LOST: order_id=%s — email already sent/claimed", order_id)
            return won
        except Exception as exc:
            logger.error("claim_email_send failed: order_id=%s err=%s", order_id, exc)
            return False

    def save_customer_email(self, order_id: int, email: str) -> None:
        """Persist customer email on the order row (best-effort, never raises)."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE orders SET customer_email = ? WHERE id = ? AND (customer_email IS NULL OR customer_email = '')",
                (email, order_id),
            )
            self.conn.commit()
        except Exception as exc:
            logger.warning("save_customer_email failed: order_id=%s err=%s", order_id, exc)

    def invalidate_order_session(self, order_id: int) -> bool:
        """
        Clear stripe_session_id for an order (e.g. when session expired).
        Used so user can create a new checkout session.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE orders SET stripe_session_id = NULL WHERE id = ?
            """, (order_id,))
            self.conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"✅ Order session invalidated: order_id={order_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ invalidate_order_session failed: {e}")
            return False

    def update_order_user_data(self, order_id: int, user_data: str) -> bool:
        """
        Persist form data to order so payment/delivery never rely only on in-memory data.
        Key for form data persistence: order_id.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE orders SET user_data = ? WHERE id = ?
            """, (user_data, order_id))
            self.conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"✅ Order user_data updated: order_id={order_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ update_order_user_data failed: {e}")
            return False

    def update_order_file_path(self, order_id: int, file_path: str) -> bool:
        """
        Update order file_path (for storing generated PDF path).
        
        Used by: handlers/stripe_handler.py (deliver_document)
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE orders SET file_path = ? WHERE id = ?
            """, (file_path, order_id))
            self.conn.commit()
            return True
        except Exception as e:
            # Silently fail if column doesn't exist (backward compatibility)
            logger.debug(f"⚠️ update_order_file_path: {e} (column may not exist)")
            return False

    def get_document_price(self, doc_type: str) -> Optional[float]:
        """Return the custom price for doc_type from the DB, or None if not set.

        Falls back to None so callers can chain to settings.get_document_price().
        Used by utils/helpers.py → get_document_price().
        """
        try:
            # Try the pricing DB (backend/pricing.py manages a separate prices table)
            from backend.pricing import PricingDatabase
            pricing_db = PricingDatabase()
            price = pricing_db.get_price(doc_type)
            if price is not None:
                return float(price)
        except Exception as _pe:
            logger.debug("get_document_price pricing_db fallback: %s", _pe)

        # Fallback: check if price is stored on the most recent order for this doc_type
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT price FROM orders WHERE doc_type = ? AND price IS NOT NULL ORDER BY id DESC LIMIT 1",
                (doc_type,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return float(row[0])
        except Exception as _e:
            logger.debug("get_document_price orders fallback: %s", _e)

        return None

    def create_payment(
        self,
        order_id: int,
        user_id: int,
        amount: float,
        stripe_session_id: str
    ) -> int:
        """
        Create payment record (for payment history).
        
        Used by: handlers/stripe_handler.py (initiate_payment)
        Returns: payment_id (stub implementation)
        """
        try:
            # Note: payments table not in minimal schema, but method kept for compatibility
            # This is a stub that logs but doesn't fail
            logger.debug(f"✅ Payment record (stub): order_id={order_id} amount={amount} session={stripe_session_id}")
            return 0  # Return stub ID
        except Exception as e:
            logger.error(f"❌ create_payment failed: {e}")
            return 0

    # ======================================================================
    # ANALYTICS
    # ======================================================================

    def log_analytics_event(
        self,
        event_type: str = "",
        user_id: int = None,
        doc_type: str = None,
        step_name: str = None,
        event_data: dict = None,
        **_kwargs,
    ) -> None:
        """Persist an analytics event to the analytics_events table.

        Accepts both positional (legacy: event_type, user_id, data) and keyword
        arguments so existing call sites continue to work without changes.
        Silently swallows errors — analytics must never crash the bot.
        """
        import json as _json
        try:
            _payload = None
            if event_data is not None:
                try:
                    _payload = _json.dumps(event_data, ensure_ascii=False)
                except Exception:
                    _payload = str(event_data)
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO analytics_events (user_id, event_type, doc_type, step_name, event_data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, event_type or "unknown", doc_type, step_name, _payload),
            )
            self.conn.commit()
        except Exception as _e:
            logger.debug("log_analytics_event failed (non-fatal): %s", _e)

    def get_funnel_stats(self, days: int = 7) -> dict:
        """Return basic funnel counts for the last *days* days.

        Returns a dict with keys: total_events, unique_users, by_event_type.
        """
        import json as _json
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT event_type, COUNT(*) as cnt, COUNT(DISTINCT user_id) as users
                FROM analytics_events
                WHERE created_at >= datetime('now', ?)
                GROUP BY event_type
                ORDER BY cnt DESC
                """,
                (f"-{days} days",),
            )
            rows = cursor.fetchall()
            by_type = {r["event_type"]: {"count": r["cnt"], "users": r["users"]} for r in rows}
            total = sum(v["count"] for v in by_type.values())
            unique = sum(1 for _ in {r["user_id"] for r in cursor.execute(
                "SELECT DISTINCT user_id FROM analytics_events WHERE created_at >= datetime('now', ?)",
                (f"-{days} days",),
            )})
            return {"total_events": total, "unique_users": unique, "by_event_type": by_type}
        except Exception as _e:
            logger.debug("get_funnel_stats failed: %s", _e)
            return {"total_events": 0, "unique_users": 0, "by_event_type": {}}

    # ======================================================================
    # CLOSE
    # ======================================================================

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            logger.info("✅ Database connection closed")

    def __del__(self):
        self.close()


__all__ = ["Database", "OrderStatus"]

_db: Optional[Database] = None


def init_db(db_path: str = None) -> None:
    global _db
    if _db is None:
        if db_path is not None:
            _db = Database(db_path)


def get_db() -> Database:
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


def close_db() -> None:
    global _db
    if _db is not None:
        _db.close()
        _db = None
