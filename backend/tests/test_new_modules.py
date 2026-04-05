#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Suite for GERMAN_DOC_BOT v4.5 New Modules
Tests settings.py, error_reporter.py, and rtl_fix.py modules
"""

import sys
import os
import unittest
import tempfile
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime

# Add the GERMAN_DOC_BOT directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'backend'))

# Import modules to test
from backend.settings import (
    Settings, BotConfig, PricingConfig, get_price, is_admin, 
    get_admin_ids, settings
)
from backend.error_reporter import (
    ErrorReporter, ErrorReport, ErrorContext, error_reporter,
    safe_handler, safe_callback, safe_state_handler
)
from backend.rtl_fix import (
    is_rtl_char, is_rtl_text, is_rtl_language, prepare_rtl_text,
    format_for_pdf, RTLTextProcessor, check_rtl_support
)


class TestSettings(unittest.TestCase):
    """Test Settings module functionality"""
    
    def setUp(self):
        """Set up test settings"""
        self.settings = Settings()
    
    def test_admin_id_configuration(self):
        """Test that admin ID 907156976 is configured"""
        admin_ids = self.settings.bot.ADMIN_IDS
        self.assertIn(907156976, admin_ids)
        self.assertTrue(self.settings.is_admin(907156976))
        self.assertTrue(is_admin(907156976))
    
    def test_price_categories(self):
        """Test price categories are correctly configured"""
        # Test premium price
        self.assertEqual(self.settings.pricing.PREMIUM_PRICE, 14.99)
        
        # Test standard price
        self.assertEqual(self.settings.pricing.STANDARD_PRICE, 9.99)
        
        # Test basic price
        self.assertEqual(self.settings.pricing.BASIC_PRICE, 4.99)
    
    def test_custom_prices(self):
        """Test custom prices for specific documents"""
        custom_prices = self.settings.pricing.CUSTOM_PRICES
        
        # Test wohnungsgeberbestaetigung price
        self.assertEqual(custom_prices['wohnungsgeberbestaetigung'], 3.99)
        
        # Test wohngeld price
        self.assertEqual(custom_prices['wohngeld'], 7.99)
    
    def test_get_price_function(self):
        """Test get_price() function returns correct prices"""
        # Test custom price
        self.assertEqual(get_price('wohnungsgeberbestaetigung'), 3.99)
        self.assertEqual(get_price('wohngeld'), 7.99)
        
        # Test complex documents
        self.assertEqual(get_price('buergergeld'), 7.99)
        self.assertEqual(get_price('aufenthaltstitel'), 7.99)

        # Test core documents
        self.assertEqual(get_price('kindergeld'), 6.99)
        self.assertEqual(get_price('elterngeld'), 5.99)
        self.assertEqual(get_price('anmeldung'), 5.99)
        self.assertEqual(get_price('kinderzuschlag'), 4.99)

        # Test simple documents
        self.assertEqual(get_price('wohnungsgeberbestaetigung'), 3.99)
        self.assertEqual(get_price('abmeldung'), 2.99)

        # Unknown document must raise — never silently return wrong price
        with self.assertRaises(ValueError):
            get_price('unknown_document')
    
    def test_support_links(self):
        """Test support links configuration"""
        self.assertEqual(self.settings.bot.SUPPORT_GROUP, "@german_doc_support")
        self.assertEqual(self.settings.bot.NEWS_CHANNEL, "@german_doc_news")
    
    def test_is_admin_function(self):
        """Test is_admin() function works correctly"""
        # Test configured admin
        self.assertTrue(is_admin(907156976))
        
        # Test non-admin
        self.assertFalse(is_admin(123456789))
    
    def test_get_admin_ids_function(self):
        """Test get_admin_ids() function"""
        admin_ids = get_admin_ids()
        self.assertIsInstance(admin_ids, list)
        self.assertIn(907156976, admin_ids)
    
    def test_pricing_config_get_price_method(self):
        """Test PricingConfig.get_price() returns correct prices from PDF_PRICES."""
        pricing = self.settings.pricing

        # All prices sourced from bot_config.pricing.PDF_PRICES
        self.assertEqual(pricing.get_price('wohnungsgeberbestaetigung'), 3.99)
        self.assertEqual(pricing.get_price('elterngeld'), 5.99)
        self.assertEqual(pricing.get_price('kindergeld'), 6.99)
        self.assertEqual(pricing.get_price('anmeldung'), 5.99)
        self.assertEqual(pricing.get_price('buergergeld'), 7.99)
        self.assertEqual(pricing.get_price('aufenthaltstitel'), 7.99)

    def test_pricing_missing_doc_raises(self):
        """Unknown doc_type must raise ValueError — never silently charge wrong amount."""
        pricing = self.settings.pricing
        with self.assertRaises(ValueError):
            pricing.get_price('unknown_document_xyz')

    def test_pdf_prices_module_raises_on_missing(self):
        """bot_config.pricing.get_price() must raise ValueError for unknown doc_type."""
        from bot_config.pricing import get_price
        with self.assertRaises(ValueError):
            get_price('totally_unknown_doc')

    def test_all_pdf_prices_are_positive(self):
        """Every price in PDF_PRICES must be > 0 to avoid free Stripe charges."""
        from bot_config.pricing import PDF_PRICES
        for doc_type, price in PDF_PRICES.items():
            self.assertGreater(price, 0, f"Price for {doc_type!r} must be > 0")

    def test_no_price_above_fifteen(self):
        """Sanity check: no PDF price should exceed €15 (catches fat-finger typos)."""
        from bot_config.pricing import PDF_PRICES
        for doc_type, price in PDF_PRICES.items():
            self.assertLessEqual(price, 15.0, f"Price for {doc_type!r} looks suspiciously high: {price}")

    def test_stripe_price_missing_raises(self):
        """StripePaymentHandler.get_price() must raise ValueError for unknown doc_type."""
        from backend.stripe_handler import StripePaymentHandler
        handler = StripePaymentHandler.__new__(StripePaymentHandler)
        handler.DOCUMENT_PRICES = StripePaymentHandler.DOCUMENT_PRICES
        with self.assertRaises(ValueError):
            handler.get_price('nonexistent_doc_type')


class TestErrorReporter(unittest.TestCase):
    """Test ErrorReporter module functionality"""
    
    def setUp(self):
        """Set up test error reporter"""
        self.error_reporter = ErrorReporter()
        self.mock_bot = AsyncMock()
        self.admin_ids = [907156976, 123456789]
        
        # Create temporary log file
        self.temp_log = tempfile.NamedTemporaryFile(mode='w', delete=False)
        self.temp_log.close()
        
        self.error_reporter.initialize(
            bot=self.mock_bot,
            admin_ids=self.admin_ids,
            log_file=self.temp_log.name,
            cooldown_seconds=1
        )
    
    def tearDown(self):
        """Clean up test files"""
        if os.path.exists(self.temp_log.name):
            os.unlink(self.temp_log.name)
    
    def test_error_report_to_telegram_message(self):
        """Test ErrorReport.to_telegram_message() includes USER ID and CURRENT STEP"""
        report = ErrorReport(
            error_id="E001",
            timestamp="01.01.2024 12:00:00",
            error_type="ValueError",
            error_message="Test error message",
            module="test_module",
            function="test_function",
            user_id=907156976,
            username="testuser",
            current_step="entering_birth_date",
            doc_type="kindergeld",
            context={"field_name": "birth_date", "user_input": "invalid_date"},
            traceback_str="Traceback test",
            severity="error"
        )
        
        message = report.to_telegram_message()
        
        # Check critical requirements
        self.assertIn("USER ID", message)
        self.assertIn("907156976", message)
        self.assertIn("КРОК", message)
        self.assertIn("entering_birth_date", message)
        self.assertIn("testuser", message)
        self.assertIn("kindergeld", message)
        self.assertIn("Test error message", message)
    
    def test_error_report_without_user_context(self):
        """Test ErrorReport without user context"""
        report = ErrorReport(
            error_id="E002",
            timestamp="01.01.2024 12:00:00",
            error_type="RuntimeError",
            error_message="System error",
            module="system",
            function="startup",
            severity="critical"
        )
        
        message = report.to_telegram_message()
        self.assertIn("🚨 КРИТИЧНА", message)
        self.assertIn("RuntimeError", message)
        self.assertIn("System error", message)
    
    async def test_error_reporter_report_method(self):
        """Test error_reporter.report() creates valid reports"""
        exception = ValueError("Test exception")
        
        report = await self.error_reporter.report(
            exception=exception,
            user_id=907156976,
            username="testuser",
            current_step="document_selection",
            doc_type="kindergeld",
            context={"action": "select_document"},
            severity="error"
        )
        
        # Verify report structure
        self.assertIsInstance(report, ErrorReport)
        self.assertEqual(report.user_id, 907156976)
        self.assertEqual(report.username, "testuser")
        self.assertEqual(report.current_step, "document_selection")
        self.assertEqual(report.doc_type, "kindergeld")
        self.assertEqual(report.error_type, "ValueError")
        self.assertEqual(report.error_message, "Test exception")
        self.assertEqual(report.severity, "error")
    
    def test_safe_handler_decorator(self):
        """Test safe_handler decorator catches exceptions"""
        @safe_handler('test_handler')
        async def test_handler(message):
            raise ValueError("Handler error")
        
        # Mock message object
        mock_message = Mock()
        mock_message.from_user = Mock()
        mock_message.from_user.id = 907156976
        mock_message.from_user.username = "testuser"
        mock_message.answer = AsyncMock()
        
        # Test that decorator catches exception
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(test_handler(mock_message))
            self.assertIsNone(result)  # Should return None when exception caught
        finally:
            loop.close()
    
    def test_safe_callback_decorator(self):
        """Test safe_callback decorator catches callback exceptions"""
        @safe_callback('test_callback')
        async def test_callback(callback_query):
            raise RuntimeError("Callback error")
        
        # Mock callback query object
        mock_callback = Mock()
        mock_callback.from_user = Mock()
        mock_callback.from_user.id = 907156976
        mock_callback.from_user.username = "testuser"
        mock_callback.data = "test_callback_data"
        mock_callback.answer = AsyncMock()
        
        # Test that decorator catches exception
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(test_callback(mock_callback))
            self.assertIsNone(result)  # Should return None when exception caught
        finally:
            loop.close()
    
    def test_log_file_writing(self):
        """Test that error reports are written to log file"""
        report = ErrorReport(
            error_id="E003",
            timestamp="01.01.2024 12:00:00",
            error_type="TestError",
            error_message="Log test",
            module="test",
            function="test_log",
            user_id=907156976,
            current_step="test_step"
        )
        
        self.error_reporter._log_to_file(report)
        
        # Check if log file contains the report
        with open(self.temp_log.name, 'r', encoding='utf-8') as f:
            log_content = f.read()
            self.assertIn("E003", log_content)
            self.assertIn("TestError", log_content)
            self.assertIn("Log test", log_content)
            self.assertIn("907156976", log_content)


class TestRTLFix(unittest.TestCase):
    """Test RTL Fix module functionality"""
    
    def test_is_rtl_char(self):
        """Test is_rtl_char() detects Arabic characters"""
        # Test Arabic characters
        self.assertTrue(is_rtl_char('م'))  # Arabic letter Meem
        self.assertTrue(is_rtl_char('ر'))  # Arabic letter Reh
        self.assertTrue(is_rtl_char('ح'))  # Arabic letter Hah
        self.assertTrue(is_rtl_char('ب'))  # Arabic letter Beh
        self.assertTrue(is_rtl_char('ا'))  # Arabic letter Alef
        
        # Test non-RTL characters
        self.assertFalse(is_rtl_char('a'))
        self.assertFalse(is_rtl_char('1'))
        self.assertFalse(is_rtl_char(' '))
        self.assertFalse(is_rtl_char('ü'))
    
    def test_is_rtl_text(self):
        """Test is_rtl_text() detects Arabic text"""
        # Test Arabic text
        self.assertTrue(is_rtl_text("مرحبا بالعالم"))  # "Hello World" in Arabic
        self.assertTrue(is_rtl_text("السلام عليكم"))   # "Peace be upon you" in Arabic
        self.assertTrue(is_rtl_text("مرحبا"))          # "Hello" in Arabic
        
        # Test mixed text (should still return True if contains RTL)
        self.assertTrue(is_rtl_text("Hello مرحبا"))
        self.assertTrue(is_rtl_text("123 مرحبا"))
        
        # Test non-RTL text
        self.assertFalse(is_rtl_text("Hello World"))
        self.assertFalse(is_rtl_text("Guten Tag"))
        self.assertFalse(is_rtl_text("123456"))
        self.assertFalse(is_rtl_text(""))
    
    def test_is_rtl_language(self):
        """Test is_rtl_language() function"""
        # Test RTL languages
        self.assertTrue(is_rtl_language('ar'))  # Arabic
        self.assertTrue(is_rtl_language('he'))  # Hebrew
        self.assertTrue(is_rtl_language('fa'))  # Persian
        self.assertTrue(is_rtl_language('ur'))  # Urdu
        
        # Test case insensitive
        self.assertTrue(is_rtl_language('AR'))
        self.assertTrue(is_rtl_language('He'))
        
        # Test non-RTL languages
        self.assertFalse(is_rtl_language('de'))  # German
        self.assertFalse(is_rtl_language('en'))  # English
        self.assertFalse(is_rtl_language('ua'))  # Ukrainian
        self.assertFalse(is_rtl_language('pl'))  # Polish
        self.assertFalse(is_rtl_language('tr'))  # Turkish
    
    def test_prepare_rtl_text(self):
        """Test prepare_rtl_text() processes Arabic text for PDF"""
        # Test Arabic text processing
        arabic_text = "مرحبا بالعالم"
        processed = prepare_rtl_text(arabic_text)
        
        # Should return processed text (different from input for RTL)
        self.assertIsInstance(processed, str)
        self.assertNotEqual(processed, "")
        
        # Test non-RTL text (should remain unchanged)
        english_text = "Hello World"
        processed_english = prepare_rtl_text(english_text)
        self.assertEqual(processed_english, english_text)
        
        # Test empty text
        self.assertEqual(prepare_rtl_text(""), "")
        self.assertEqual(prepare_rtl_text(None), None)
    
    def test_format_for_pdf_with_language(self):
        """Test format_for_pdf() with lang='ar' applies RTL"""
        text = "مرحبا بالعالم"
        
        # Test Arabic language
        arabic_formatted = format_for_pdf(text, 'ar')
        self.assertIsInstance(arabic_formatted, str)
        
        # Test German language (should not process as RTL)
        german_formatted = format_for_pdf("Hallo Welt", 'de')
        self.assertEqual(german_formatted, "Hallo Welt")
        
        # Test Ukrainian language
        ukrainian_formatted = format_for_pdf("Привіт світ", 'ua')
        self.assertEqual(ukrainian_formatted, "Привіт світ")
    
    def test_rtl_text_processor(self):
        """Test RTLTextProcessor class"""
        processor = RTLTextProcessor()
        
        # Test Arabic text processing
        arabic_text = "مرحبا بالعالم"
        processed = processor.process(arabic_text)
        self.assertIsInstance(processed, str)
        
        # Test non-RTL text
        english_text = "Hello World"
        processed_english = processor.process(english_text)
        self.assertEqual(processed_english, english_text)
        
        # Test multiline processing
        multiline_text = "مرحبا\nبالعالم"
        processed_multiline = processor.process_multiline(multiline_text)
        self.assertIn('\n', processed_multiline)
    
    def test_check_rtl_support(self):
        """Test check_rtl_support() function"""
        support_info = check_rtl_support()
        
        # Should return dictionary with required keys
        self.assertIsInstance(support_info, dict)
        self.assertIn('arabic_reshaper', support_info)
        self.assertIn('python_bidi', support_info)
        self.assertIn('full_support', support_info)
        self.assertIn('recommendation', support_info)
        
        # Values should be boolean or string
        self.assertIsInstance(support_info['arabic_reshaper'], bool)
        self.assertIsInstance(support_info['python_bidi'], bool)
        self.assertIsInstance(support_info['full_support'], bool)


class TestIntegration(unittest.TestCase):
    """Test integration between modules"""
    
    def test_import_settings_from_bot_path(self):
        """Test importing settings from bot.py path"""
        try:
            # This should work from bot.py context
            from backend.settings import settings, get_price, is_admin
            self.assertIsNotNone(settings)
            self.assertTrue(callable(get_price))
            self.assertTrue(callable(is_admin))
        except ImportError as e:
            self.fail(f"Failed to import settings: {e}")
    
    def test_import_error_reporter_from_bot_path(self):
        """Test importing error_reporter from bot.py path"""
        try:
            from backend.error_reporter import error_reporter, ErrorReport
            self.assertIsNotNone(error_reporter)
            self.assertTrue(callable(ErrorReport))
        except ImportError as e:
            self.fail(f"Failed to import error_reporter: {e}")
    
    def test_import_rtl_fix_from_bot_path(self):
        """Test importing rtl_fix from bot.py path"""
        try:
            from backend.rtl_fix import prepare_rtl_text, is_rtl_language
            self.assertTrue(callable(prepare_rtl_text))
            self.assertTrue(callable(is_rtl_language))
        except ImportError as e:
            self.fail(f"Failed to import rtl_fix: {e}")
    
    def test_settings_prices_match_document_handlers(self):
        """Test that all prices are consistent with PDF_PRICES."""
        self.assertEqual(get_price('kindergeld'), 6.99)
        self.assertEqual(get_price('elterngeld'), 5.99)
        self.assertEqual(get_price('anmeldung'), 5.99)
        self.assertEqual(get_price('wohnungsgeberbestaetigung'), 3.99)
        self.assertEqual(get_price('wohngeld'), 5.99)
    
    def test_error_reporter_initialization(self):
        """Test error reporter initializes correctly"""
        reporter = ErrorReporter()
        mock_bot = Mock()
        admin_ids = [907156976]
        
        reporter.initialize(
            bot=mock_bot,
            admin_ids=admin_ids,
            log_file="test.log"
        )
        
        self.assertTrue(reporter._is_initialized)
        self.assertEqual(reporter._admin_ids, admin_ids)
        self.assertEqual(reporter._bot, mock_bot)


if __name__ == '__main__':
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestSettings,
        TestErrorReporter, 
        TestRTLFix,
        TestIntegration
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print(f"\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print(f"\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    # Exit with appropriate code
    exit_code = 0 if result.wasSuccessful() else 1
    sys.exit(exit_code)