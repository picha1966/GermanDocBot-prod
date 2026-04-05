#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for backend/database.py and backend/stripe_handler.py.

Covers the actual public API — no references to modules that do not exist.
Run with:  pytest tests/test_backend.py -v
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database, OrderStatus
from backend.stripe_handler import format_price, calculate_discount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> Database:
    """Return a fresh in-memory-like Database backed by a temp file."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    return Database(tmp.name), tmp.name


# ---------------------------------------------------------------------------
# Database — Users
# ---------------------------------------------------------------------------

class TestDatabaseUsers(unittest.TestCase):

    def setUp(self):
        self.db, self.db_path = _make_db()

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_create_and_get_profile(self):
        self.db.create_user(user_id=111, username="alice", first_name="Alice", last_name="Muster")
        profile = self.db.get_profile(111)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["user_id"], 111)
        self.assertEqual(profile["username"], "alice")
        self.assertEqual(profile["first_name"], "Alice")

    def test_create_user_idempotent(self):
        """INSERT OR IGNORE — second call must not raise."""
        self.db.create_user(user_id=222)
        self.db.create_user(user_id=222)
        self.assertIsNotNone(self.db.get_profile(222))

    def test_get_or_create_user_new(self):
        user = self.db.get_or_create_user(user_id=333, username="bob")
        self.assertIsNotNone(user)
        self.assertEqual(user["user_id"], 333)

    def test_get_or_create_user_existing(self):
        self.db.create_user(user_id=444, username="carol")
        user = self.db.get_or_create_user(user_id=444, username="carol_updated")
        # Should return existing row, not overwrite username
        self.assertEqual(user["user_id"], 444)

    def test_language_default(self):
        self.db.create_user(user_id=555)
        lang = self.db.get_user_lang(555)
        self.assertEqual(lang, "uk")

    def test_set_and_get_language(self):
        self.db.create_user(user_id=666)
        self.db.set_user_lang(666, "de")
        self.assertEqual(self.db.get_user_lang(666), "de")

    def test_update_user_language_alias(self):
        self.db.create_user(user_id=777)
        self.db.update_user_language(777, "en")
        self.assertEqual(self.db.get_user_lang(777), "en")


# ---------------------------------------------------------------------------
# Database — GDPR
# ---------------------------------------------------------------------------

class TestDatabaseGDPR(unittest.TestCase):

    def setUp(self):
        self.db, self.db_path = _make_db()

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_gdpr_default_false(self):
        self.db.create_user(user_id=10)
        self.assertFalse(self.db.get_gdpr_status(10))

    def test_set_gdpr_accepted(self):
        self.db.create_user(user_id=11)
        self.db.set_gdpr_consent(11, True)
        self.assertTrue(self.db.get_gdpr_status(11))

    def test_revoke_gdpr(self):
        self.db.create_user(user_id=12)
        self.db.mark_gdpr_accepted(12)
        self.assertTrue(self.db.get_gdpr_status(12))
        self.db.set_gdpr_consent(12, False)
        self.assertFalse(self.db.get_gdpr_status(12))

    def test_mark_gdpr_accepted_alias(self):
        self.db.create_user(user_id=13)
        self.db.mark_gdpr_accepted(13)
        self.assertTrue(self.db.get_gdpr_status(13))


# ---------------------------------------------------------------------------
# Database — Orders
# ---------------------------------------------------------------------------

class TestDatabaseOrders(unittest.TestCase):

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.db.create_user(user_id=1000)

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_create_order_returns_int(self):
        oid = self.db.create_order(user_id=1000, doc_type="kindergeld", amount=9.99)
        self.assertIsInstance(oid, int)
        self.assertGreater(oid, 0)

    def test_get_order_roundtrip(self):
        oid = self.db.create_order(user_id=1000, doc_type="anmeldung", amount=7.50)
        order = self.db.get_order(oid)
        self.assertIsNotNone(order)
        self.assertEqual(order["user_id"], 1000)
        self.assertEqual(order["doc_type"], "anmeldung")
        self.assertAlmostEqual(order["amount"], 7.50)
        self.assertEqual(order["status"], OrderStatus.PENDING.value)

    def test_get_order_aliases(self):
        oid = self.db.create_order(user_id=1000, doc_type="buergergeld", amount=6.00)
        order = self.db.get_order(oid)
        # price is an alias for amount
        self.assertAlmostEqual(order["price"], order["amount"])
        # order_id is an alias for id
        self.assertEqual(order["order_id"], order["id"])

    def test_update_order_status_to_paid(self):
        oid = self.db.create_order(user_id=1000, doc_type="wohngeld", amount=8.00)
        ok = self.db.update_order_status(oid, OrderStatus.PAID)
        self.assertTrue(ok)
        order = self.db.get_order(oid)
        self.assertEqual(order["status"], OrderStatus.PAID.value)
        self.assertIsNotNone(order["paid_at"])

    def test_get_order_by_session(self):
        session_id = "cs_test_abc123"
        oid = self.db.create_order(
            user_id=1000, doc_type="kindergeld", amount=9.99,
            stripe_session_id=session_id
        )
        order = self.db.get_order_by_session(session_id)
        self.assertIsNotNone(order)
        self.assertEqual(order["id"], oid)

    def test_user_has_paid_false_initially(self):
        self.assertFalse(self.db.user_has_paid(1000, "kindergeld"))

    def test_user_has_paid_true_after_marking(self):
        sid = "cs_test_xyz"
        self.db.create_order(user_id=1000, doc_type="kindergeld", amount=9.99, stripe_session_id=sid)
        self.db.mark_order_paid(sid)
        self.assertTrue(self.db.user_has_paid(1000, "kindergeld"))

    def test_get_user_orders(self):
        self.db.create_order(user_id=1000, doc_type="kindergeld", amount=9.99)
        self.db.create_order(user_id=1000, doc_type="anmeldung", amount=7.50)
        orders = self.db.get_user_orders(1000)
        self.assertGreaterEqual(len(orders), 2)

    def test_update_order_user_data(self):
        oid = self.db.create_order(user_id=1000, doc_type="kindergeld", amount=9.99)
        ok = self.db.update_order_user_data(oid, '{"name":"Max"}')
        self.assertTrue(ok)
        order = self.db.get_order(oid)
        self.assertEqual(order["user_data"], '{"name":"Max"}')


# ---------------------------------------------------------------------------
# Database — Delivery idempotency
# ---------------------------------------------------------------------------

class TestDatabaseDelivery(unittest.TestCase):

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.db.create_user(user_id=2000)

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_claim_delivery_wins_first_call(self):
        oid = self.db.create_order(user_id=2000, doc_type="kindergeld", amount=9.99)
        self.db.update_order_status(oid, OrderStatus.PAID)
        self.assertTrue(self.db.claim_delivery(oid))

    def test_claim_delivery_loses_second_call(self):
        oid = self.db.create_order(user_id=2000, doc_type="kindergeld", amount=9.99)
        self.db.update_order_status(oid, OrderStatus.PAID)
        self.db.claim_delivery(oid)
        self.assertFalse(self.db.claim_delivery(oid))

    def test_is_order_delivered_false_initially(self):
        oid = self.db.create_order(user_id=2000, doc_type="kindergeld", amount=9.99)
        self.assertFalse(self.db.is_order_delivered(oid))

    def test_mark_and_check_delivered(self):
        oid = self.db.create_order(user_id=2000, doc_type="kindergeld", amount=9.99)
        self.db.mark_order_delivered(oid)
        self.assertTrue(self.db.is_order_delivered(oid))

    def test_mark_delivered_idempotent(self):
        oid = self.db.create_order(user_id=2000, doc_type="kindergeld", amount=9.99)
        self.db.mark_order_delivered(oid)
        self.db.mark_order_delivered(oid)
        self.assertTrue(self.db.is_order_delivered(oid))

    def test_claim_email_send_wins_first_call(self):
        oid = self.db.create_order(user_id=2000, doc_type="kindergeld", amount=9.99)
        self.assertTrue(self.db.claim_email_send(oid))

    def test_claim_email_send_loses_second_call(self):
        oid = self.db.create_order(user_id=2000, doc_type="kindergeld", amount=9.99)
        self.db.claim_email_send(oid)
        self.assertFalse(self.db.claim_email_send(oid))


# ---------------------------------------------------------------------------
# Database — Referral system
# ---------------------------------------------------------------------------

class TestDatabaseReferral(unittest.TestCase):

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.db.create_user(user_id=3000)
        self.db.create_user(user_id=3001)

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_get_or_create_referral_code(self):
        code = self.db.get_or_create_referral_code(3000)
        self.assertIsNotNone(code)
        self.assertTrue(code.startswith("REF"))
        self.assertEqual(len(code), 11)  # "REF" + 8 hex chars

    def test_referral_code_stable(self):
        code1 = self.db.get_or_create_referral_code(3000)
        code2 = self.db.get_or_create_referral_code(3000)
        self.assertEqual(code1, code2)

    def test_register_referral(self):
        code = self.db.get_or_create_referral_code(3000)
        result = self.db.register_referral(code, 3001)
        self.assertTrue(result)
        stats = self.db.get_referral_stats(3000)
        self.assertEqual(stats["count"], 1)

    def test_cannot_refer_self(self):
        code = self.db.get_or_create_referral_code(3000)
        result = self.db.register_referral(code, 3000)
        self.assertFalse(result)

    def test_referral_credit_awarded_every_two(self):
        code = self.db.get_or_create_referral_code(3000)
        self.db.create_user(user_id=3002)
        self.db.register_referral(code, 3001)
        self.db.register_referral(code, 3002)
        stats = self.db.get_referral_stats(3000)
        self.assertEqual(stats["credits"], 1)

    def test_peek_free_doc_credit(self):
        self.assertFalse(self.db.peek_free_doc_credit(3000))

    def test_set_and_get_referral_code_used(self):
        self.db.set_referral_code_used(3001, "REF12345678")
        code = self.db.get_referral_code_used(3001)
        self.assertEqual(code, "REF12345678")

    def test_use_free_doc_credit(self):
        code = self.db.get_or_create_referral_code(3000)
        self.db.create_user(user_id=3003)
        self.db.create_user(user_id=3004)
        self.db.register_referral(code, 3003)
        self.db.register_referral(code, 3004)
        self.assertTrue(self.db.use_free_doc_credit(3000))
        self.assertFalse(self.db.peek_free_doc_credit(3000))


# ---------------------------------------------------------------------------
# Database — Analytics
# ---------------------------------------------------------------------------

class TestDatabaseAnalytics(unittest.TestCase):

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.db.create_user(user_id=5000)

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_log_event_does_not_raise(self):
        self.db.log_analytics_event("test_event", user_id=5000, doc_type="kindergeld")

    def test_log_event_persisted(self):
        self.db.log_analytics_event("doc_started", user_id=5000, doc_type="anmeldung", step_name="intro")
        stats = self.db.get_funnel_stats(days=7)
        self.assertIn("doc_started", stats["by_event_type"])
        self.assertGreaterEqual(stats["total_events"], 1)

    def test_multiple_events_counted(self):
        for _ in range(3):
            self.db.log_analytics_event("page_view", user_id=5000)
        stats = self.db.get_funnel_stats(days=1)
        self.assertGreaterEqual(stats["by_event_type"].get("page_view", {}).get("count", 0), 3)

    def test_log_event_with_data_dict(self):
        self.db.log_analytics_event("payment_started", user_id=5000, event_data={"amount": 9.99})

    def test_get_funnel_stats_empty(self):
        stats = self.db.get_funnel_stats(days=1)
        self.assertIn("total_events", stats)
        self.assertIn("unique_users", stats)
        self.assertIn("by_event_type", stats)


# ---------------------------------------------------------------------------
# Database — reset_user_orders
# ---------------------------------------------------------------------------

class TestDatabaseReset(unittest.TestCase):

    def setUp(self):
        self.db, self.db_path = _make_db()
        self.db.create_user(user_id=4000)

    def tearDown(self):
        self.db.close()
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_reset_user_orders(self):
        oid = self.db.create_order(user_id=4000, doc_type="kindergeld", amount=9.99)
        updated = self.db.reset_user_orders(4000)
        self.assertGreaterEqual(updated, 1)
        order = self.db.get_order(oid)
        self.assertEqual(order["status"], OrderStatus.FAILED.value)


# ---------------------------------------------------------------------------
# stripe_handler — utility functions
# ---------------------------------------------------------------------------

class TestStripeUtilityFunctions(unittest.TestCase):

    def test_format_price_eur(self):
        self.assertEqual(format_price(9.99, "EUR"), "9.99€")

    def test_format_price_usd(self):
        self.assertEqual(format_price(15.50, "USD"), "15.50$")

    def test_format_price_uah(self):
        self.assertEqual(format_price(100.00, "UAH"), "100.00₴")

    def test_format_price_unknown_currency(self):
        result = format_price(7.50, "GBP")
        self.assertIn("7.50", result)
        self.assertIn("GBP", result)

    def test_calculate_discount_percent(self):
        self.assertAlmostEqual(calculate_discount(100.0, "percent", 10.0), 10.0)

    def test_calculate_discount_fixed(self):
        self.assertAlmostEqual(calculate_discount(100.0, "fixed", 15.0), 15.0)

    def test_calculate_discount_fixed_capped_at_price(self):
        self.assertAlmostEqual(calculate_discount(10.0, "fixed", 20.0), 10.0)

    def test_calculate_discount_zero_percent(self):
        self.assertAlmostEqual(calculate_discount(50.0, "percent", 0.0), 0.0)


# ---------------------------------------------------------------------------
# StripePaymentHandler — get_price
# ---------------------------------------------------------------------------

class TestStripePaymentHandlerGetPrice(unittest.TestCase):

    def _make_handler(self):
        from backend.stripe_handler import StripePaymentHandler
        mock_settings = MagicMock()
        mock_settings.stripe.STRIPE_API_KEY = "sk_test_dummy"
        return StripePaymentHandler(mock_settings)

    def test_db_price_takes_priority(self):
        handler = self._make_handler()
        self.assertAlmostEqual(handler.get_price("kindergeld", db_price=12.99), 12.99)

    def test_fallback_to_pdf_prices(self):
        from bot_config.pricing import PDF_PRICES
        handler = self._make_handler()
        expected = PDF_PRICES["kindergeld"]
        self.assertAlmostEqual(handler.get_price("kindergeld"), expected)

    def test_unknown_doc_type_raises(self):
        handler = self._make_handler()
        with self.assertRaises(ValueError):
            handler.get_price("nonexistent_doc_type_xyz")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
