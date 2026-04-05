#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic Tool for Database & Analytics
Run this to verify your installation is correct
"""

import sys
import os

def test_database():
    """Test database initialization and analytics"""
    print("\n" + "="*60)
    print("🧪 DATABASE & ANALYTICS DIAGNOSTIC TEST")
    print("="*60 + "\n")
    
    try:
        # Import database
        print("1️⃣ Testing database import...")
        from backend.database import Database
        print("   ✅ Database imported successfully")
    except ImportError as e:
        print(f"   ❌ Failed to import Database: {e}")
        print("   💡 Make sure database.py is in backend/ folder")
        return False
    
    try:
        # Initialize database
        print("\n2️⃣ Testing database initialization...")
        db = Database('test_bot_database.db')
        print("   ✅ Database initialized successfully")
        print(f"   📁 Path: {db.db_path}")
    except Exception as e:
        print(f"   ❌ Failed to initialize database: {e}")
        return False
    
    try:
        # Test analytics - Format 1
        print("\n3️⃣ Testing analytics - Format 1 (positional args)...")
        db.log_analytics_event('TEST_EVENT_1', 12345, {'test': 'data', 'format': 1})
        print("   ✅ Format 1 works: log_analytics_event('EVENT', user_id, data)")
    except Exception as e:
        print(f"   ❌ Format 1 failed: {e}")
        return False
    
    try:
        # Test analytics - Format 2
        print("\n4️⃣ Testing analytics - Format 2 (keyword args)...")
        db.log_analytics_event(event_type='TEST_EVENT_2', user_id=67890, event_data={'format': 2})
        print("   ✅ Format 2 works: log_analytics_event(event_type='EVENT', user_id=123, ...)")
    except Exception as e:
        print(f"   ❌ Format 2 failed: {e}")
        return False
    
    try:
        # Test analytics - Format 3
        print("\n5️⃣ Testing analytics - Format 3 (mixed args)...")
        db.log_analytics_event(user_id=11111, event_name='TEST_EVENT_3', extra='field')
        print("   ✅ Format 3 works: log_analytics_event(user_id=123, event_name='EVENT', ...)")
    except Exception as e:
        print(f"   ❌ Format 3 failed: {e}")
        return False
    
    try:
        # Retrieve analytics
        print("\n6️⃣ Testing analytics retrieval...")
        events = db.get_analytics_events(limit=10)
        print(f"   ✅ Retrieved {len(events)} analytics events")
        
        if events:
            print("\n   📊 Recent events:")
            for event in events[:3]:
                print(f"      • {event['event_type']} - User {event['user_id']} - {event['created_at']}")
    except Exception as e:
        print(f"   ❌ Failed to retrieve analytics: {e}")
        return False
    
    try:
        # Test GDPR methods
        print("\n7️⃣ Testing GDPR methods...")
        test_user_id = 99999
        
        # Create user
        db.get_or_create_user(test_user_id, 'test_user', 'Test', 'User')
        print("   ✅ User created")
        
        # Set language
        db.set_user_lang(test_user_id, 'ua')
        lang = db.get_user_lang(test_user_id)
        print(f"   ✅ Language set: {lang}")
        
        # Set GDPR consent
        db.set_gdpr_consent(test_user_id, True)
        has_consent = db.has_gdpr_consent(test_user_id)
        print(f"   ✅ GDPR consent: {has_consent}")
    except Exception as e:
        print(f"   ❌ GDPR methods failed: {e}")
        return False
    
    try:
        # Get stats
        print("\n8️⃣ Testing database statistics...")
        stats = db.get_stats()
        print("   ✅ Statistics retrieved:")
        print(f"      • Total users: {stats.get('total_users', 0)}")
        print(f"      • GDPR users: {stats.get('gdpr_users', 0)}")
        print(f"      • Total events: {stats.get('total_events', 0)}")
        print(f"      • Total orders: {stats.get('total_orders', 0)}")
    except Exception as e:
        print(f"   ❌ Failed to get stats: {e}")
        return False
    
    # Cleanup
    try:
        os.remove('test_bot_database.db')
        print("\n9️⃣ Cleanup completed")
    except:
        pass
    
    return True


def test_menu_import():
    """Test if menu module is available"""
    print("\n" + "="*60)
    print("🧪 MENU MODULE TEST")
    print("="*60 + "\n")
    
    try:
        print("1️⃣ Testing menu import...")
        import menu
        print("   ✅ Menu module imported")
    except ImportError as e:
        print(f"   ❌ Failed to import menu: {e}")
        return False
    
    try:
        print("\n2️⃣ Testing show_main_menu function...")
        if hasattr(menu, 'show_main_menu'):
            print("   ✅ show_main_menu() function exists")
        else:
            print("   ❌ show_main_menu() function not found")
            return False
    except Exception as e:
        print(f"   ❌ Error checking menu functions: {e}")
        return False
    
    return True


def test_gdpr_import():
    """Test if GDPR manager is available"""
    print("\n" + "="*60)
    print("🧪 GDPR MANAGER TEST")
    print("="*60 + "\n")
    
    try:
        print("1️⃣ Testing GDPR manager import...")
        from backend.gdpr import gdpr_manager
        print("   ✅ GDPR manager imported")
    except ImportError as e:
        print(f"   ❌ Failed to import gdpr_manager: {e}")
        return False
    
    try:
        print("\n2️⃣ Testing GDPR methods...")
        methods = ['get_consent_message', 'get_accept_message', 'get_decline_message']
        for method in methods:
            if hasattr(gdpr_manager, method):
                print(f"   ✅ {method}() exists")
            else:
                print(f"   ❌ {method}() not found")
                return False
    except Exception as e:
        print(f"   ❌ Error checking GDPR methods: {e}")
        return False
    
    return True


def main():
    """Run all diagnostic tests"""
    print("\n" + "🔧"*30)
    print("   TELEGRAM BOT DIAGNOSTIC TOOL v1.0")
    print("🔧"*30)
    
    results = {
        'database': test_database(),
        'menu': test_menu_import(),
        'gdpr': test_gdpr_import()
    }
    
    print("\n" + "="*60)
    print("📋 SUMMARY")
    print("="*60 + "\n")
    
    all_passed = True
    for component, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{component.upper()}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    
    if all_passed:
        print("✅ ALL TESTS PASSED - Your installation is ready!")
        print("\nYou can now start your bot with:")
        print("   python3 bot.py")
    else:
        print("❌ SOME TESTS FAILED - Please fix the issues above")
        print("\nCommon solutions:")
        print("1. Make sure all files are in the correct folders")
        print("2. Check your imports in bot.py")
        print("3. Verify database.py has the universal log_analytics_event method")
        print("4. Ensure menu.py has show_main_menu() function")
    
    print("="*60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())