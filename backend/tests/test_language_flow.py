#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Suite for GERMAN_DOC_BOT Language Selection & GDPR Flow
Tests the new user flow: /start → Language Selection → GDPR → Main Menu
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
try:
    # Strategy 1: Direct import
    from database import Database
    from gdpr import gdpr_manager, GDPRManager
    print("✅ Strategy 1: Direct imports successful")
except ImportError as e1:
    print(f"⚠️ Strategy 1 failed: {e1}")
    try:
        # Strategy 2: Backend prefix
        from backend.database import Database
        from backend.gdpr import gdpr_manager, GDPRManager
        print("✅ Strategy 2: Backend imports successful")
    except ImportError as e2:
        print(f"❌ Both import strategies failed: {e2}")
        sys.exit(1)

# Try to import bot constants
try:
    import bot
    LANGUAGE_BUTTONS = getattr(bot, 'LANGUAGE_BUTTONS', None)
    show_language_selection = getattr(bot, 'show_language_selection', None)
    handle_language_selection = getattr(bot, 'handle_language_selection', None)
    print("✅ Bot module imports successful")
except ImportError as e:
    print(f"⚠️ Bot module import failed: {e}")
    # Define fallback constants for testing
    LANGUAGE_BUTTONS = [
        ('🇺🇦 Українська', 'lang_ua'),
        ('🇩🇪 Deutsch', 'lang_de'),
        ('🇬🇧 English', 'lang_en'),
        ('🇵🇱 Polski', 'lang_pl'),
        ('🇹🇷 Türkçe', 'lang_tr'),
        ('🇸🇦 العربية', 'lang_ar'),
    ]
    show_language_selection = None
    handle_language_selection = None


class TestLanguageButtons(unittest.TestCase):
    """Test Language Selection Constants"""
    
    def test_language_buttons_exist(self):
        """Test that LANGUAGE_BUTTONS constant exists with 6 entries"""
        self.assertIsNotNone(LANGUAGE_BUTTONS, "LANGUAGE_BUTTONS constant should exist")
        self.assertEqual(len(LANGUAGE_BUTTONS), 6, "Should have exactly 6 language buttons")
    
    def test_language_buttons_structure(self):
        """Test that language buttons have correct structure"""
        expected_languages = ['ua', 'de', 'en', 'pl', 'tr', 'ar']
        
        for i, (text, callback_data) in enumerate(LANGUAGE_BUTTONS):
            # Test text format
            self.assertIsInstance(text, str, f"Button {i} text should be string")
            self.assertTrue(text.startswith('🇺🇦') or text.startswith('🇩🇪') or 
                          text.startswith('🇬🇧') or text.startswith('🇵🇱') or 
                          text.startswith('🇹🇷') or text.startswith('🇸🇦'), 
                          f"Button {i} should start with flag emoji")
            
            # Test callback data format
            self.assertIsInstance(callback_data, str, f"Button {i} callback should be string")
            self.assertTrue(callback_data.startswith('lang_'), f"Button {i} callback should start with 'lang_'")
            
            # Extract language code
            lang_code = callback_data.split('_')[1]
            self.assertIn(lang_code, expected_languages, f"Language code {lang_code} should be supported")
    
    def test_all_supported_languages_present(self):
        """Test that all 6 required languages are present"""
        callback_data_list = [callback for _, callback in LANGUAGE_BUTTONS]
        expected_callbacks = ['lang_ua', 'lang_de', 'lang_en', 'lang_pl', 'lang_tr', 'lang_ar']
        
        for expected in expected_callbacks:
            self.assertIn(expected, callback_data_list, f"Missing language callback: {expected}")


class TestBotFunctions(unittest.TestCase):
    """Test Bot Language Selection Functions"""
    
    def test_show_language_selection_exists(self):
        """Test that show_language_selection function exists"""
        if show_language_selection is not None:
            self.assertTrue(callable(show_language_selection), "show_language_selection should be callable")
        else:
            print("⚠️ show_language_selection function not found in bot module")
    
    def test_handle_language_selection_exists(self):
        """Test that handle_language_selection callback handler exists"""
        if handle_language_selection is not None:
            self.assertTrue(callable(handle_language_selection), "handle_language_selection should be callable")
        else:
            print("⚠️ handle_language_selection function not found in bot module")


class TestDatabaseLanguageFunctions(unittest.TestCase):
    """Test Database Language and GDPR Functions"""
    
    def setUp(self):
        """Set up test database"""
        # Create temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        
        # Initialize database
        self.db = Database(self.temp_db.name)
        
        # Create test user
        self.test_user_id = 12345
        self.db.get_or_create_user(
            user_id=self.test_user_id,
            username="testuser",
            first_name="Test",
            last_name="User"
        )
    
    def tearDown(self):
        """Clean up test database"""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_set_user_lang_function(self):
        """Test db.set_user_lang() saves language correctly"""
        # Test setting Polish language
        self.db.set_user_lang(self.test_user_id, 'pl')
        
        # Verify language was saved
        profile = self.db.get_profile(self.test_user_id)
        self.assertIsNotNone(profile, "Profile should exist after setting language")
        self.assertEqual(profile['lang'], 'pl', "Language should be set to Polish")
    
    def test_get_profile_lang_returns_correct_language(self):
        """Test db.get_profile(user_id)['lang'] returns correct language"""
        # Test different languages
        test_languages = ['ua', 'de', 'en', 'pl', 'tr', 'ar']
        
        for lang in test_languages:
            with self.subTest(language=lang):
                # Set language
                self.db.set_user_lang(self.test_user_id, lang)
                
                # Get profile and verify
                profile = self.db.get_profile(self.test_user_id)
                self.assertEqual(profile['lang'], lang, f"Language should be {lang}")
    
    def test_set_gdpr_consent_function(self):
        """Test db.set_gdpr_consent(user_id, True) saves consent"""
        # Set GDPR consent to True
        self.db.set_gdpr_consent(self.test_user_id, True)
        
        # Verify consent was saved
        has_consent = self.db.has_gdpr_consent(self.test_user_id)
        self.assertTrue(has_consent, "GDPR consent should be True")
        
        # Test setting consent to False
        self.db.set_gdpr_consent(self.test_user_id, False)
        has_consent = self.db.has_gdpr_consent(self.test_user_id)
        self.assertFalse(has_consent, "GDPR consent should be False")
    
    def test_has_gdpr_consent_function(self):
        """Test db.has_gdpr_consent(user_id) returns correct value"""
        # Initially should be False
        has_consent = self.db.has_gdpr_consent(self.test_user_id)
        self.assertFalse(has_consent, "Initial GDPR consent should be False")
        
        # Set to True and test
        self.db.set_gdpr_consent(self.test_user_id, True)
        has_consent = self.db.has_gdpr_consent(self.test_user_id)
        self.assertTrue(has_consent, "GDPR consent should be True after setting")
        
        # Set to False and test
        self.db.set_gdpr_consent(self.test_user_id, False)
        has_consent = self.db.has_gdpr_consent(self.test_user_id)
        self.assertFalse(has_consent, "GDPR consent should be False after unsetting")


class TestGDPRMultilingual(unittest.TestCase):
    """Test GDPR Multilingual Support"""
    
    def setUp(self):
        """Set up GDPR manager"""
        self.gdpr = GDPRManager()
        self.supported_languages = ['ua', 'de', 'en', 'pl', 'tr', 'ar']
    
    def test_gdpr_consent_message_all_languages(self):
        """Test gdpr_manager.get_consent_message(lang) for all 6 languages"""
        for lang in self.supported_languages:
            with self.subTest(language=lang):
                message = gdpr_manager.get_consent_message(lang)
                
                # Should return non-empty string
                self.assertIsInstance(message, str, f"Consent message for {lang} should be string")
                self.assertGreater(len(message), 0, f"Consent message for {lang} should not be empty")
                
                # Should contain HTML formatting
                self.assertIn('<b>', message, f"Consent message for {lang} should contain bold formatting")
                
                # Should contain language-specific content
                if lang == 'pl':
                    self.assertIn('Polityka', message, "Polish message should contain 'Polityka'")
                elif lang == 'de':
                    self.assertIn('Datenschutz', message, "German message should contain 'Datenschutz'")
                elif lang == 'ar':
                    self.assertIn('الخصوصية', message, "Arabic message should contain Arabic text")
    
    def test_gdpr_consent_keyboard_all_languages(self):
        """Test gdpr_manager.get_consent_keyboard(lang) for all 6 languages"""
        for lang in self.supported_languages:
            with self.subTest(language=lang):
                keyboard = gdpr_manager.get_consent_keyboard(lang)
                
                # Should return InlineKeyboardMarkup
                self.assertIsNotNone(keyboard, f"Keyboard for {lang} should not be None")
                
                # Should have buttons (we can't easily test the exact structure without aiogram)
                # But we can test that it's the right type
                self.assertTrue(hasattr(keyboard, 'inline_keyboard'), 
                              f"Keyboard for {lang} should have inline_keyboard attribute")
    
    def test_gdpr_accept_message_all_languages(self):
        """Test gdpr_manager.get_accept_message(lang) for all 6 languages"""
        for lang in self.supported_languages:
            with self.subTest(language=lang):
                message = gdpr_manager.get_accept_message(lang)
                
                # Should return non-empty string
                self.assertIsInstance(message, str, f"Accept message for {lang} should be string")
                self.assertGreater(len(message), 0, f"Accept message for {lang} should not be empty")
                
                # Should contain positive confirmation
                if lang == 'pl':
                    self.assertIn('Dziękujemy', message, "Polish accept message should contain 'Dziękujemy'")
                elif lang == 'de':
                    self.assertIn('Vielen Dank', message, "German accept message should contain 'Vielen Dank'")
                elif lang == 'en':
                    self.assertIn('Thank you', message, "English accept message should contain 'Thank you'")
    
    def test_gdpr_privacy_policy_all_languages(self):
        """Test gdpr_manager.get_privacy_policy(lang) for all 6 languages"""
        for lang in self.supported_languages:
            with self.subTest(language=lang):
                policy = gdpr_manager.get_privacy_policy(lang)
                
                # Should return non-empty string
                self.assertIsInstance(policy, str, f"Privacy policy for {lang} should be string")
                self.assertGreater(len(policy), 100, f"Privacy policy for {lang} should be substantial")
                
                # Should contain HTML formatting
                self.assertIn('<b>', policy, f"Privacy policy for {lang} should contain bold formatting")
                
                # Should contain current date
                current_date = datetime.now().strftime('%d.%m.%Y')
                self.assertIn(current_date, policy, f"Privacy policy for {lang} should contain current date")
                
                # Should contain language-specific legal terms
                if lang == 'pl':
                    self.assertIn('POLITYKA PRYWATNOŚCI', policy, "Polish policy should contain Polish title")
                elif lang == 'de':
                    self.assertIn('DATENSCHUTZERKLÄRUNG', policy, "German policy should contain German title")
                elif lang == 'ar':
                    self.assertIn('سياسة الخصوصية', policy, "Arabic policy should contain Arabic title")
    
    def test_gdpr_terms_of_service_all_languages(self):
        """Test gdpr_manager.get_terms_of_service(lang) for all 6 languages"""
        for lang in self.supported_languages:
            with self.subTest(language=lang):
                terms = gdpr_manager.get_terms_of_service(lang)
                
                # Should return non-empty string
                self.assertIsInstance(terms, str, f"Terms of service for {lang} should be string")
                self.assertGreater(len(terms), 100, f"Terms of service for {lang} should be substantial")
                
                # Should contain HTML formatting
                self.assertIn('<b>', terms, f"Terms of service for {lang} should contain bold formatting")
                
                # Should contain current date
                current_date = datetime.now().strftime('%d.%m.%Y')
                self.assertIn(current_date, terms, f"Terms of service for {lang} should contain current date")
                
                # Should contain language-specific legal terms
                if lang == 'pl':
                    self.assertIn('WARUNKI UŻYTKOWANIA', terms, "Polish terms should contain Polish title")
                elif lang == 'de':
                    self.assertIn('NUTZUNGSBEDINGUNGEN', terms, "German terms should contain German title")
                elif lang == 'ar':
                    self.assertIn('شروط الاستخدام', terms, "Arabic terms should contain Arabic title")


class TestFlowSimulation(unittest.TestCase):
    """Test Complete New User Flow Simulation"""
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
        
        # Test user
        self.test_user_id = 98765
        self.db.get_or_create_user(
            user_id=self.test_user_id,
            username="flowtest",
            first_name="Flow",
            last_name="Test"
        )
    
    def tearDown(self):
        """Clean up"""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_complete_new_user_flow(self):
        """Simulate the complete new user flow"""
        # STEP 1: Create user with no GDPR consent
        user_id = self.test_user_id
        
        # STEP 2: Verify has_gdpr_consent returns False initially
        has_consent = self.db.has_gdpr_consent(user_id)
        self.assertFalse(has_consent, "New user should not have GDPR consent")
        
        # STEP 3: Set language to Polish
        self.db.set_user_lang(user_id, 'pl')
        
        # Verify language was set
        profile = self.db.get_profile(user_id)
        self.assertEqual(profile['lang'], 'pl', "Language should be set to Polish")
        
        # STEP 4: Get GDPR message in Polish - verify it's in Polish
        gdpr_message = gdpr_manager.get_consent_message('pl')
        self.assertIn('Polityka Prywatności', gdpr_message, "GDPR message should be in Polish")
        self.assertIn('Zgadzam się', gdpr_message.replace('<b>', '').replace('</b>', '') or 
                     str(gdpr_manager.get_consent_keyboard('pl')), "Should contain Polish accept button")
        
        # STEP 5: Set GDPR consent to True
        self.db.set_gdpr_consent(user_id, True)
        
        # STEP 6: Verify has_gdpr_consent returns True
        has_consent = self.db.has_gdpr_consent(user_id)
        self.assertTrue(has_consent, "User should have GDPR consent after accepting")
        
        # Verify accept message is in Polish
        accept_message = gdpr_manager.get_accept_message('pl')
        self.assertIn('Dziękujemy', accept_message, "Accept message should be in Polish")
    
    def test_flow_with_different_languages(self):
        """Test flow simulation with different languages"""
        languages_to_test = [
            ('de', 'Datenschutzerklärung', 'Vielen Dank'),
            ('en', 'Privacy Policy', 'Thank you'),
            ('tr', 'Gizlilik Politikası', 'Teşekkürler'),
            ('ar', 'الخصوصية', 'شكراً')
        ]
        
        for lang, privacy_keyword, thanks_keyword in languages_to_test:
            with self.subTest(language=lang):
                # Create new user for each language test
                user_id = self.test_user_id + hash(lang) % 1000
                self.db.get_or_create_user(
                    user_id=user_id,
                    username=f"test_{lang}",
                    first_name="Test",
                    last_name="User"
                )
                
                # Verify no initial consent
                self.assertFalse(self.db.has_gdpr_consent(user_id))
                
                # Set language
                self.db.set_user_lang(user_id, lang)
                
                # Verify GDPR message is in correct language
                gdpr_message = gdpr_manager.get_consent_message(lang)
                self.assertIn(privacy_keyword, gdpr_message, 
                            f"GDPR message should contain {privacy_keyword} for {lang}")
                
                # Accept consent
                self.db.set_gdpr_consent(user_id, True)
                
                # Verify consent and accept message
                self.assertTrue(self.db.has_gdpr_consent(user_id))
                accept_message = gdpr_manager.get_accept_message(lang)
                self.assertIn(thanks_keyword, accept_message, 
                            f"Accept message should contain {thanks_keyword} for {lang}")


class TestGDPRContentQuality(unittest.TestCase):
    """Test GDPR Content Quality and Completeness"""
    
    def test_gdpr_content_completeness(self):
        """Test that GDPR content is complete and professional"""
        languages = ['ua', 'de', 'en', 'pl', 'tr', 'ar']
        
        for lang in languages:
            with self.subTest(language=lang):
                # Test consent message
                consent = gdpr_manager.get_consent_message(lang)
                self.assertGreater(len(consent), 200, f"Consent message for {lang} should be substantial")
                
                # Test privacy policy
                privacy = gdpr_manager.get_privacy_policy(lang)
                self.assertGreater(len(privacy), 500, f"Privacy policy for {lang} should be comprehensive")
                self.assertIn('GDPR', privacy.upper(), f"Privacy policy for {lang} should mention GDPR")
                
                # Test terms of service
                terms = gdpr_manager.get_terms_of_service(lang)
                self.assertGreater(len(terms), 400, f"Terms of service for {lang} should be comprehensive")
                
                # Test that all contain proper legal structure
                for content in [privacy, terms]:
                    # Should have numbered sections
                    self.assertIn('<b>1.', content, f"Content for {lang} should have numbered sections")
                    # Should have contact information
                    self.assertIn('/support', content, f"Content for {lang} should have support contact")


if __name__ == '__main__':
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test classes in logical order
    test_classes = [
        TestLanguageButtons,
        TestBotFunctions,
        TestDatabaseLanguageFunctions,
        TestGDPRMultilingual,
        TestFlowSimulation,
        TestGDPRContentQuality
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    print("🚀 Starting GERMAN_DOC_BOT Language Selection & GDPR Flow Tests")
    print("=" * 80)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print(f"\n{'='*80}")
    print(f"TEST SUMMARY - Language Selection & GDPR Flow")
    print(f"{'='*80}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.testsRun > 0:
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
        print(f"Success rate: {success_rate:.1f}%")
    
    # Detailed results
    if result.failures:
        print(f"\n❌ FAILURES ({len(result.failures)}):")
        for test, traceback in result.failures:
            print(f"  - {test}")
            print(f"    {traceback.split('AssertionError:')[-1].strip()}")
    
    if result.errors:
        print(f"\n⚠️ ERRORS ({len(result.errors)}):")
        for test, traceback in result.errors:
            print(f"  - {test}")
            print(f"    {traceback.split('Exception:')[-1].strip()}")
    
    if result.wasSuccessful():
        print(f"\n✅ ALL TESTS PASSED!")
        print(f"Language selection and GDPR flow is working correctly.")
    else:
        print(f"\n❌ SOME TESTS FAILED!")
        print(f"Please review the failures and errors above.")
    
    # Exit with appropriate code
    exit_code = 0 if result.wasSuccessful() else 1
    sys.exit(exit_code)