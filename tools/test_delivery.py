#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test PDF Delivery — CLI tool to test delivery without Stripe webhook

Usage:
    python -m tools.test_delivery <order_id>
    
Example:
    python -m tools.test_delivery 43

This tool:
1. Loads the bot instance
2. Fetches order from database
3. Calls deliver_document_after_payment()
4. Shows detailed logs

Use this to verify delivery works BEFORE testing with real Stripe payments.
"""

import os
import sys
import asyncio
import logging

# Setup path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def test_delivery(order_id: int):
    """Test PDF delivery for a specific order."""
    from dotenv import load_dotenv
    load_dotenv()
    
    print()
    print("=" * 60)
    print(f"TEST DELIVERY: order_id={order_id}")
    print("=" * 60)
    print()
    
    # 1. Load bot
    from aiogram import Bot
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set in .env")
        return False
    
    bot = Bot(token=bot_token, parse_mode="HTML")
    print(f"✅ Bot loaded")
    
    # 2. Load database and check order
    from utils.helpers import get_db
    db = get_db()
    
    order = db.get_order(order_id)
    if not order:
        print(f"❌ ERROR: Order {order_id} not found in database")
        await bot.session.close()
        return False
    
    print(f"✅ Order found:")
    print(f"   order_id: {order.get('id')}")
    print(f"   user_id: {order.get('user_id')}")
    print(f"   doc_type: {order.get('doc_type')}")
    print(f"   status: {order.get('status')}")
    print(f"   user_data length: {len(str(order.get('user_data', '')))}")
    print()
    
    user_id = order.get("user_id")
    if not user_id:
        print(f"❌ ERROR: Order {order_id} has no user_id")
        await bot.session.close()
        return False
    
    # 3. Set bot instance for stripe_handler
    from handlers.stripe_handler import set_bot
    set_bot(bot)
    
    # 4. Call delivery function
    print("Calling deliver_document_after_payment()...")
    print()
    
    from handlers.stripe_handler import deliver_document_after_payment
    
    try:
        result = await deliver_document_after_payment(bot, order_id)
        print()
        if result:
            print("=" * 60)
            print(f"✅ DELIVERY SUCCESS: order_id={order_id}")
            print("=" * 60)
        else:
            print("=" * 60)
            print(f"❌ DELIVERY FAILED: order_id={order_id} (returned False)")
            print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ DELIVERY EXCEPTION: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        result = False
    
    # Cleanup
    await bot.session.close()
    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("ERROR: Please provide order_id as argument")
        print("Example: python -m tools.test_delivery 43")
        sys.exit(1)
    
    try:
        order_id = int(sys.argv[1])
    except ValueError:
        print(f"ERROR: Invalid order_id: {sys.argv[1]}")
        sys.exit(1)
    
    result = asyncio.run(test_delivery(order_id))
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
