# -*- coding: utf-8 -*-
"""
handlers/admin.py - Complete Admin Panel for GERMAN_DOC_BOT v5.0
Full-featured admin interface with statistics, export, pricing, and promo management
"""

import os
import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Optional, Dict, Any
import csv

from aiogram import types, Dispatcher, Bot

logger = logging.getLogger(__name__)

_bot: Optional[Bot] = None

ADMIN_IDS: List[int] = []
_admin_ids_loaded = False

# Localized access denied message (shown to non-admin users)
_ACCESS_DENIED = {
    "uk": "⛔ Доступ заборонено",
    "en": "⛔ Access denied",
    "de": "⛔ Zugriff verweigert",
    "pl": "⛔ Dostęp zabroniony",
    "tr": "⛔ Erişim engellendi",
    "ar": "⛔ تم رفض الوصول",
}


def _get_access_denied(user_id: int) -> str:
    """Get localized access denied text for user."""
    try:
        from utils.helpers import get_user_lang
        lang = get_user_lang(user_id)
        if lang == "ua":
            lang = "uk"
    except Exception:
        lang = "en"
    return _ACCESS_DENIED.get(lang, _ACCESS_DENIED["en"])


def _load_admin_ids():
    """Load admin IDs from environment variable once."""
    global ADMIN_IDS, _admin_ids_loaded
    if not _admin_ids_loaded:
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        if admin_ids_str:
            try:
                ADMIN_IDS = [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()]
                logger.info(f"✅ Loaded {len(ADMIN_IDS)} admin IDs")
            except ValueError as e:
                logger.error(f"❌ Invalid ADMIN_IDS format: {e}")
                ADMIN_IDS = []
        else:
            logger.warning("⚠️ ADMIN_IDS not set in environment")
            ADMIN_IDS = []
        _admin_ids_loaded = True


def set_bot(bot: Bot):
    """Set global bot instance for admin operations."""
    global _bot
    _bot = bot


def get_bot() -> Bot:
    """Get global bot instance."""
    global _bot
    if _bot is None:
        raise RuntimeError("Bot not initialized. Call set_bot(bot) first.")
    return _bot


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    _load_admin_ids()
    return user_id in ADMIN_IDS


def _get_db():
    """Get database instance from helpers."""
    from utils.helpers import get_db
    return get_db()


def _format_price(amount: float) -> str:
    """Format price using helpers."""
    from utils.helpers import format_price
    return format_price(amount)


def _get_document_prices() -> Dict[str, float]:
    """Get document prices from helpers."""
    from utils.helpers import get_document_price
    
    doc_types = [
        'kindergeld', 'anmeldung', 'abmeldung', 'elterngeld',
        'kinderzuschlag', 'wohngeld', 'buergergeld',
        'bildungspaket', 'unterhaltsvorschuss'
    ]
    
    return {doc_type: get_document_price(doc_type) for doc_type in doc_types}


def _calculate_extended_stats() -> Dict[str, Any]:
    """Extended statistics: revenue by period, top documents, Termin stats, funnel."""
    db = _get_db()
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    ago_7d  = now - timedelta(days=7)
    ago_30d = now - timedelta(days=30)

    result: Dict[str, Any] = {
        "revenue_today": 0.0,
        "revenue_7d": 0.0,
        "revenue_30d": 0.0,
        "revenue_total": 0.0,
        "paid_today": 0,
        "paid_7d": 0,
        "paid_30d": 0,
        "new_users_today": 0,
        "new_users_7d": 0,
        "total_users": 0,
        "top_docs": [],        # list of (doc_type, count)
        "termin_active": 0,
        "termin_found": 0,
        "avg_order_value": 0.0,
        "conversion_7d": 0.0,
    }

    try:
        # Users
        result["total_users"] = db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        result["new_users_today"] = db.conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (today_start.isoformat(),)
        ).fetchone()[0]
        result["new_users_7d"] = db.conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (ago_7d.isoformat(),)
        ).fetchone()[0]

        # Revenue periods
        for key, ts in [("today", today_start), ("7d", ago_7d), ("30d", ago_30d)]:
            row = db.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM orders "
                "WHERE created_at >= ? AND status IN ('paid','sent','downloaded')",
                (ts.isoformat(),)
            ).fetchone()
            result[f"paid_{key}"] = row[0] if row else 0
            result[f"revenue_{key}"] = float(row[1]) if row else 0.0

        rev_row = db.conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status IN ('paid','sent','downloaded')"
        ).fetchone()
        result["revenue_total"] = float(rev_row[0]) if rev_row else 0.0

        # Average order value
        if result["paid_30d"] > 0:
            result["avg_order_value"] = result["revenue_30d"] / result["paid_30d"]

        # Top documents by sales (30d)
        top_rows = db.conn.execute("""
            SELECT doc_type, COUNT(*) as cnt
            FROM orders
            WHERE created_at >= ? AND status IN ('paid','sent','downloaded')
              AND (doc_type IS NULL OR doc_type NOT LIKE 'termin_%')
            GROUP BY doc_type
            ORDER BY cnt DESC
            LIMIT 5
        """, (ago_30d.isoformat(),)).fetchall()
        result["top_docs"] = [(r[0] or "unknown", r[1]) for r in top_rows]

        # Conversion 7d: paid / new_users
        if result["new_users_7d"] > 0:
            result["conversion_7d"] = result["paid_7d"] / result["new_users_7d"] * 100

    except Exception as _e:
        logger.warning("_calculate_extended_stats orders error: %s", _e)

    # Termin stats (separate DB)
    try:
        from backend.termin_db import get_connection as _tc
        _tconn = _tc()
        result["termin_active"] = _tconn.execute(
            "SELECT COUNT(*) FROM termin_entitlements WHERE active=1"
        ).fetchone()[0]
        _found_row = _tconn.execute(
            "SELECT COUNT(*) FROM termin_entitlements WHERE found_termin=1"
        ).fetchone()
        result["termin_found"] = _found_row[0] if _found_row else 0
        _tconn.close()
    except Exception:
        pass

    # Persistent termin_found counter from stats.py
    try:
        from utils.stats import get_termin_found
        result["termin_found_total"] = get_termin_found()
    except Exception:
        result["termin_found_total"] = 0

    return result


def _calculate_stats() -> Dict[str, Any]:
    """Calculate comprehensive admin statistics from database."""
    db = _get_db()
    
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    week_ago = now - timedelta(days=7)
    
    total_users = db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    active_users_7d = db.conn.execute(
        "SELECT COUNT(*) FROM users WHERE last_active >= ?",
        (week_ago.isoformat(),)
    ).fetchone()[0]
    
    new_users_today = db.conn.execute(
        "SELECT COUNT(*) FROM users WHERE created_at >= ?",
        (today_start.isoformat(),)
    ).fetchone()[0]
    
    stats = {
        'total_users': total_users,
        'active_users_7d': active_users_7d,
        'new_users_today': new_users_today,
        'referred_users': 0,
        'orders_today': 0,
        'orders_by_status': {},
        'total_revenue': 0.0,
        'promo_discounts': 0.0,
    }
    
    # Use `orders` table (the real payment tracking table).
    # Fall back to `documents` if `orders` does not exist (legacy DBs).
    try:
        orders_today = db.conn.execute(
            "SELECT COUNT(*) FROM orders WHERE created_at >= ?",
            (today_start.isoformat(),)
        ).fetchone()[0]
        stats['orders_today'] = orders_today

        orders_by_status = db.conn.execute("""
            SELECT status, COUNT(*) as count
            FROM orders
            WHERE created_at >= ?
            GROUP BY status
        """, (today_start.isoformat(),)).fetchall()
        stats['orders_by_status'] = {row[0]: row[1] for row in orders_by_status}

        # Total revenue from paid/sent orders
        rev_row = db.conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status IN ('paid','sent','downloaded')"
        ).fetchone()
        stats['total_revenue'] = float(rev_row[0]) if rev_row else 0.0

    except Exception as _e:
        logger.warning("_calculate_stats: orders table query failed (%s), trying documents", _e)
        try:
            orders_today = db.conn.execute(
                "SELECT COUNT(*) FROM documents WHERE created_at >= ?",
                (today_start.isoformat(),)
            ).fetchone()[0]
            stats['orders_today'] = orders_today

            orders_by_status = db.conn.execute("""
                SELECT status, COUNT(*) as count
                FROM documents
                WHERE created_at >= ?
                GROUP BY status
            """, (today_start.isoformat(),)).fetchall()
            stats['orders_by_status'] = {row[0]: row[1] for row in orders_by_status}
        except Exception:
            pass
    
    return stats


def _format_funnel_message(days: int = 7) -> str:
    """Format conversion funnel statistics message."""
    db = _get_db()
    week_ago = datetime.now() - timedelta(days=days)
    
    try:
        total_users = db.conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?",
            (week_ago.isoformat(),)
        ).fetchone()[0]

        gdpr_accepted = db.conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ? AND gdpr_accepted = 1",
            (week_ago.isoformat(),)
        ).fetchone()[0]

        try:
            total_orders = db.conn.execute(
                "SELECT COUNT(*) FROM orders WHERE created_at >= ?",
                (week_ago.isoformat(),)
            ).fetchone()[0]

            completed_orders = db.conn.execute(
                "SELECT COUNT(*) FROM orders WHERE created_at >= ? AND status IN ('paid','sent','downloaded')",
                (week_ago.isoformat(),)
            ).fetchone()[0]
        except Exception:
            try:
                total_orders = db.conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE created_at >= ?",
                    (week_ago.isoformat(),)
                ).fetchone()[0]
                completed_orders = db.conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE created_at >= ? AND status = 'completed'",
                    (week_ago.isoformat(),)
                ).fetchone()[0]
            except Exception:
                total_orders = 0
                completed_orders = 0
        
        text = (
            f"📊 <b>ВОРОНКА ПРОДАЖІВ ({days} днів)</b>\n\n"
            f"👥 Нових користувачів: {total_users}\n"
            f"    ↓ {(gdpr_accepted/total_users*100 if total_users > 0 else 0):.1f}%\n"
            f"✅ Прийняли GDPR: {gdpr_accepted}\n"
        )
        
        if total_orders > 0:
            text += (
                f"    ↓ {(total_orders/gdpr_accepted*100 if gdpr_accepted > 0 else 0):.1f}%\n"
                f"📄 Створили замовлення: {total_orders}\n"
                f"    ↓ {(completed_orders/total_orders*100 if total_orders > 0 else 0):.1f}%\n"
                f"💰 Завершили оплату: {completed_orders}\n"
            )
        
        conversion = (completed_orders / total_users * 100) if total_users > 0 else 0
        text += f"\n<b>Загальна конверсія: {conversion:.2f}%</b>"
        
        return text
        
    except Exception as e:
        logger.error(f"❌ Error formatting funnel: {e}", exc_info=True)
        return "📊 <b>ВОРОНКА ПРОДАЖІВ</b>\n\nПомилка завантаження даних"


def _export_users_csv(days: int = 7) -> Optional[bytes]:
    """Export users to CSV format."""
    db = _get_db()
    week_ago = datetime.now() - timedelta(days=days)
    
    try:
        users = db.conn.execute("""
            SELECT user_id, username, first_name, last_name, lang, 
                   gdpr_accepted, created_at, last_active
            FROM users
            WHERE created_at >= ?
            ORDER BY created_at DESC
        """, (week_ago.isoformat(),)).fetchall()
        
        output = BytesIO()
        writer = csv.writer(output)
        
        writer.writerow([
            'User ID', 'Username', 'First Name', 'Last Name', 
            'Language', 'GDPR Accepted', 'Created At', 'Last Active'
        ])
        
        for user in users:
            writer.writerow(user)
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error exporting users: {e}", exc_info=True)
        return None


def _export_documents_csv(days: int = 7) -> Optional[bytes]:
    """Export documents/orders to CSV format."""
    db = _get_db()
    week_ago = datetime.now() - timedelta(days=days)
    
    try:
        documents = db.conn.execute("""
            SELECT id, user_id, doc_type, status, created_at
            FROM documents
            WHERE created_at >= ?
            ORDER BY created_at DESC
        """, (week_ago.isoformat(),)).fetchall()
        
        output = BytesIO()
        writer = csv.writer(output)
        
        writer.writerow(['Order ID', 'User ID', 'Document Type', 'Status', 'Created At'])
        
        for doc in documents:
            writer.writerow(doc)
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"❌ Error exporting documents: {e}", exc_info=True)
        return None


async def admin_panel(message: types.Message):
    """Display main admin panel with statistics and navigation."""
    if not is_admin(message.from_user.id):
        user_info = f"{message.from_user.id} (@{message.from_user.username or 'no_username'})"
        logger.warning(f"🚫 Unauthorized admin access attempt: {user_info} tried /admin")
        await message.answer(_get_access_denied(message.from_user.id))
        return
    
    try:
        stats = _calculate_stats()
    except Exception as e:
        logger.error(f"❌ Error calculating stats: {e}", exc_info=True)
        await message.answer("❌ Помилка отримання статистики")
        return

    # 24h quick summary
    _24h_paid = 0
    _24h_revenue = 0.0
    _24h_users = 0
    try:
        db = _get_db()
        _24h_ago = (datetime.now() - timedelta(hours=24)).isoformat()
        _r = db.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount),0) FROM orders "
            "WHERE created_at >= ? AND status IN ('paid','sent','downloaded')",
            (_24h_ago,)
        ).fetchone()
        _24h_paid = _r[0] if _r else 0
        _24h_revenue = float(_r[1]) if _r else 0.0
        _u = db.conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (_24h_ago,)
        ).fetchone()
        _24h_users = _u[0] if _u else 0
    except Exception:
        pass

    text = (
        "📊 <b>АДМІН ПАНЕЛЬ</b>\n"
        "═══════════════════════\n\n"
        f"⚡ <b>Останні 24 год:</b>\n"
        f"   • Нових юзерів: {_24h_users}\n"
        f"   • Оплат: {_24h_paid}  |  Дохід: {_format_price(_24h_revenue)}\n\n"
        f"👥 <b>Користувачі:</b>\n"
        f"   • Всього: {stats['total_users']}\n"
        f"   • Активних (7д): {stats['active_users_7d']}\n"
        f"   • Нових сьогодні: {stats['new_users_today']}\n\n"
        f"📄 <b>Замовлення сьогодні:</b>\n"
        f"   • Всього: {stats['orders_today']}\n"
    )

    status_names = {'pending': '⏳', 'paid': '💰', 'sent': '✅', 'downloaded': '📥',
                    'failed': '⚠️', 'completed': '✅'}
    for status, emoji in status_names.items():
        count = stats['orders_by_status'].get(status, 0)
        if count > 0:
            text += f"   • {emoji} {status}: {count}\n"

    text += (
        f"\n💰 <b>Фінанси (весь час):</b>\n"
        f"   • Дохід: {_format_price(stats['total_revenue'])}\n"
        f"\n═══════════════════════"
    )

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🔄 Оновити", callback_data="admin_refresh"),
        types.InlineKeyboardButton("📊 Воронка", callback_data="admin_funnel"),
    )
    keyboard.add(
        types.InlineKeyboardButton("📥 Експорт", callback_data="admin_export"),
        types.InlineKeyboardButton("💰 Ціни", callback_data="admin_prices"),
    )
    keyboard.add(
        types.InlineKeyboardButton("🎁 Промокоди", callback_data="admin_promos"),
    )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


async def admin_refresh(callback_query: types.CallbackQuery):
    """Refresh admin panel statistics."""
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        return
    
    try:
        stats = _calculate_stats()
    except Exception as e:
        logger.error(f"❌ Error calculating stats: {e}", exc_info=True)
        return
    
    text = (
        "📊 <b>АДМІН ПАНЕЛЬ</b>\n"
        "═══════════════════════\n\n"
        f"👥 <b>Користувачі:</b>\n"
        f"   • Всього: {stats['total_users']}\n"
        f"   • Активних (7д): {stats['active_users_7d']}\n"
        f"   • Нових сьогодні: {stats['new_users_today']}\n"
        f"   • Рефералів: {stats['referred_users']}\n\n"
        f"📄 <b>Замовлення:</b>\n"
        f"   • Сьогодні: {stats['orders_today']}\n"
    )
    
    status_names = {'pending': '⏳', 'paid': '✅', 'failed': '⚠️', 'completed': '✅'}
    for status, emoji in status_names.items():
        count = stats['orders_by_status'].get(status, 0)
        if count > 0:
            text += f"   • {emoji} {status}: {count}\n"
    
    text += (
        f"\n💰 <b>Фінанси:</b>\n"
        f"   • Дохід: {_format_price(stats['total_revenue'])}\n"
        f"   • Знижки: {_format_price(stats['promo_discounts'])}\n"
        f"\n═══════════════════════"
    )
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🔄 Оновити", callback_data="admin_refresh"),
        types.InlineKeyboardButton("📊 Воронка", callback_data="admin_funnel"),
    )
    keyboard.add(
        types.InlineKeyboardButton("📥 Експорт", callback_data="admin_export"),
        types.InlineKeyboardButton("💰 Ціни", callback_data="admin_prices"),
    )
    keyboard.add(
        types.InlineKeyboardButton("🎁 Промокоди", callback_data="admin_promos"),
    )
    
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


async def admin_funnel(callback_query: types.CallbackQuery):
    """Display conversion funnel analytics."""
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        return
    
    text = _format_funnel_message(days=7)
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


async def admin_export(callback_query: types.CallbackQuery):
    """Export data menu."""
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        return
    
    text = (
        "📥 <b>ЕКСПОРТ ДАНИХ</b>\n\n"
        "Оберіть що експортувати:"
    )
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("👥 Користувачі (7 днів)", callback_data="export_users_7"),
        types.InlineKeyboardButton("📄 Замовлення (7 днів)", callback_data="export_orders_7"),
        types.InlineKeyboardButton("👥 Користувачі (30 днів)", callback_data="export_users_30"),
        types.InlineKeyboardButton("📄 Замовлення (30 днів)", callback_data="export_orders_30"),
    )
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


async def admin_export_users(callback_query: types.CallbackQuery):
    """Export users data to CSV."""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer(_get_access_denied(callback_query.from_user.id))
        return
    
    days = 7 if "_7" in callback_query.data else 30
    
    await callback_query.answer("🔄 Генерую експорт...")
    
    try:
        bot = get_bot()
        file_bytes = _export_users_csv(days=days)
        
        if file_bytes:
            file_obj = BytesIO(file_bytes)
            file_obj.name = f"users_{datetime.now().strftime('%Y%m%d')}_{days}d.csv"
            
            db = _get_db()
            week_ago = datetime.now() - timedelta(days=days)
            count = db.conn.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?",
                (week_ago.isoformat(),)
            ).fetchone()[0]
            
            await bot.send_document(
                callback_query.from_user.id,
                file_obj,
                caption=f"📥 Експорт користувачів за {days} днів\n{count} записів"
            )
            
    except Exception as e:
        logger.error(f"❌ Export users error: {e}", exc_info=True)


async def admin_export_orders(callback_query: types.CallbackQuery):
    """Export orders/documents data to CSV."""
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        return
    
    days = 7 if "_7" in callback_query.data else 30
    
    try:
        bot = get_bot()
        file_bytes = _export_documents_csv(days=days)
        
        if file_bytes:
            file_obj = BytesIO(file_bytes)
            file_obj.name = f"orders_{datetime.now().strftime('%Y%m%d')}_{days}d.csv"
            
            db = _get_db()
            week_ago = datetime.now() - timedelta(days=days)
            count = db.conn.execute(
                "SELECT COUNT(*) FROM documents WHERE created_at >= ?",
                (week_ago.isoformat(),)
            ).fetchone()[0]
            
            await bot.send_document(
                callback_query.from_user.id,
                file_obj,
                caption=f"📥 Експорт замовлень за {days} днів\n{count} записів"
            )
            
    except Exception as e:
        logger.error(f"❌ Export orders error: {e}", exc_info=True)


async def admin_prices(callback_query: types.CallbackQuery):
    """Display document prices management."""
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        return
    
    prices = _get_document_prices()
    
    text = "💰 <b>ЦІНИ ДОКУМЕНТІВ</b>\n\n"
    
    doc_names = {
        'kindergeld': 'Kindergeld',
        'anmeldung': 'Anmeldung',
        'abmeldung': 'Abmeldung',
        'elterngeld': 'Elterngeld',
        'kinderzuschlag': 'Kinderzuschlag',
        'wohngeld': 'Wohngeld',
        'buergergeld': 'Bürgergeld',
        'bildungspaket': 'Bildungspaket',
        'unterhaltsvorschuss': 'Unterhaltsvorschuss',
    }
    
    for doc_type, price in prices.items():
        name = doc_names.get(doc_type, doc_type.capitalize())
        text += f"• {name}: {_format_price(price)}\n"
    
    text += "\nДля зміни ціни: /setprice <тип> <ціна>"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


async def admin_promos(callback_query: types.CallbackQuery):
    """Display promo codes management."""
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        return
    
    text = (
        "🎁 <b>ПРОМОКОДИ</b>\n\n"
        "Управління промокодами:\n\n"
        "• Створити промокод:\n"
        "  /addpromo <код> <тип> <значення> [макс] [днів]\n\n"
        "<b>Приклади:</b>\n"
        "• /addpromo WELCOME percent 20 100 30\n"
        "  (20% знижка, макс 100 використань, 30 днів)\n\n"
        "• /addpromo NEWYEAR fixed 5.00 50 7\n"
        "  (€5 знижка, макс 50 використань, 7 днів)\n\n"
        "<b>Типи знижок:</b>\n"
        "• percent - відсоткова знижка\n"
        "• fixed - фіксована сума в EUR"
    )
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


async def admin_back(callback_query: types.CallbackQuery):
    """Return to main admin panel."""
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        return
    
    try:
        stats = _calculate_stats()
    except Exception as e:
        logger.error(f"❌ Error calculating stats: {e}", exc_info=True)
        return
    
    text = (
        "📊 <b>АДМІН ПАНЕЛЬ</b>\n"
        "═══════════════════════\n\n"
        f"👥 <b>Користувачі:</b>\n"
        f"   • Всього: {stats['total_users']}\n"
        f"   • Активних (7д): {stats['active_users_7d']}\n"
        f"   • Нових сьогодні: {stats['new_users_today']}\n"
        f"   • Рефералів: {stats['referred_users']}\n\n"
        f"📄 <b>Замовлення:</b>\n"
        f"   • Сьогодні: {stats['orders_today']}\n"
    )
    
    status_names = {'pending': '⏳', 'paid': '✅', 'failed': '⚠️', 'completed': '✅'}
    for status, emoji in status_names.items():
        count = stats['orders_by_status'].get(status, 0)
        if count > 0:
            text += f"   • {emoji} {status}: {count}\n"
    
    text += (
        f"\n💰 <b>Фінанси:</b>\n"
        f"   • Дохід: {_format_price(stats['total_revenue'])}\n"
        f"   • Знижки: {_format_price(stats['promo_discounts'])}\n"
        f"\n═══════════════════════"
    )
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🔄 Оновити", callback_data="admin_refresh"),
        types.InlineKeyboardButton("📊 Воронка", callback_data="admin_funnel"),
    )
    keyboard.add(
        types.InlineKeyboardButton("📥 Експорт", callback_data="admin_export"),
        types.InlineKeyboardButton("💰 Ціни", callback_data="admin_prices"),
    )
    keyboard.add(
        types.InlineKeyboardButton("🎁 Промокоди", callback_data="admin_promos"),
    )
    
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        pass


async def set_price(message: types.Message):
    """Set document price via command."""
    if not is_admin(message.from_user.id):
        user_info = f"{message.from_user.id} (@{message.from_user.username or 'no_username'})"
        logger.warning(f"🚫 Unauthorized admin access attempt: {user_info} tried /setprice")
        await message.answer(_get_access_denied(message.from_user.id))
        return
    
    args = message.text.split()[1:]
    if len(args) != 2:
        await message.answer(
            "❌ <b>Невірний формат</b>\n\n"
            "Використання: /setprice <тип> <ціна>\n\n"
            "<b>Приклад:</b>\n"
            "/setprice kindergeld 12.99",
            parse_mode="HTML"
        )
        return
    
    doc_type, price_str = args
    
    try:
        price = float(price_str)
        if price <= 0:
            raise ValueError("Price must be positive")
    except ValueError:
        await message.answer("❌ Невірний формат ціни. Використовуйте число, наприклад: 12.99")
        return
    
    from bot_config.pricing import PDF_PRICES as _pdf_prices
    valid_doc_types = sorted(_pdf_prices.keys())

    if doc_type not in valid_doc_types:
        await message.answer(
            f"❌ Невідомий тип документа: <code>{doc_type}</code>\n\n"
            f"Доступні типи:\n" + "\n".join(f"• {dt}" for dt in valid_doc_types),
            parse_mode="HTML"
        )
        return

    try:
        from backend.pricing import PricingManager
        _db = _get_db()
        _pricing = PricingManager(_db.db_path)
        _pricing.update_price(doc_type, price, admin_id=message.from_user.id, reason="admin /setprice")
    except Exception as _pe:
        logger.error("set_price: PricingManager failed: %s", _pe, exc_info=True)
        await message.answer("❌ Помилка запису ціни в БД. Ціна НЕ збережена.")
        return

    await message.answer(
        f"✅ <b>Ціну оновлено і збережено</b>\n\n"
        f"Документ: <code>{doc_type}</code>\n"
        f"Нова ціна: <b>{_format_price(price)}</b>\n\n"
        f"<i>Діє для нових замовлень.</i>",
        parse_mode="HTML"
    )
    logger.info("PRICE_UPDATED: doc_type=%s price=%.2f admin=%s", doc_type, price, message.from_user.id)


async def add_promo(message: types.Message):
    """Create promo code via command."""
    if not is_admin(message.from_user.id):
        user_info = f"{message.from_user.id} (@{message.from_user.username or 'no_username'})"
        logger.warning(f"🚫 Unauthorized admin access attempt: {user_info} tried /addpromo")
        await message.answer(_get_access_denied(message.from_user.id))
        return
    
    args = message.text.split()[1:]
    if len(args) < 3:
        await message.answer(
            "❌ <b>Невірний формат</b>\n\n"
            "Використання:\n"
            "/addpromo <код> <тип> <значення> [макс_використань] [днів]\n\n"
            "<b>Типи знижок:</b>\n"
            "• percent - відсоткова знижка (1-100)\n"
            "• fixed - фіксована сума в EUR\n\n"
            "<b>Приклади:</b>\n"
            "• /addpromo WELCOME percent 20 100 30\n"
            "• /addpromo SAVE5 fixed 5.00 50 7",
            parse_mode="HTML"
        )
        return
    
    code = args[0].upper()
    discount_type = args[1].lower()
    
    try:
        discount_value = float(args[2])
    except ValueError:
        await message.answer("❌ Невірне значення знижки. Використовуйте число.")
        return
    
    max_uses = int(args[3]) if len(args) > 3 else 0
    valid_days = int(args[4]) if len(args) > 4 else 30
    
    if discount_type not in ['percent', 'fixed']:
        await message.answer("❌ Тип знижки має бути 'percent' або 'fixed'")
        return
    
    if discount_type == 'percent' and (discount_value <= 0 or discount_value > 100):
        await message.answer("❌ Відсоткова знижка має бути від 1 до 100")
        return
    
    if discount_type == 'fixed' and discount_value <= 0:
        await message.answer("❌ Фіксована знижка має бути більше 0")
        return
    
    try:
        from backend.pricing import PricingManager
        _db = _get_db()
        _pricing = PricingManager(_db.db_path)
        _promo_id = _pricing.create_promo_code(
            code=code,
            discount_type=discount_type,
            discount_value=discount_value,
            max_uses=max_uses if max_uses > 0 else None,
            valid_days=valid_days,
            created_by=message.from_user.id,
        )
        logger.info(
            "PROMO_CREATED: code=%s type=%s value=%s max_uses=%s days=%s id=%s admin=%s",
            code, discount_type, discount_value, max_uses, valid_days, _promo_id, message.from_user.id,
        )
        await message.answer(
            f"✅ <b>Промокод створено і збережено!</b>\n\n"
            f"🎁 Код: <code>{code}</code>\n"
            f"💰 Знижка: {discount_value}{'%' if discount_type == 'percent' else '€'}\n"
            f"📊 Макс. використань: {max_uses if max_uses > 0 else 'безлімітно'}\n"
            f"📅 Дійсний: {valid_days} днів\n"
            f"🆔 ID в БД: <code>{_promo_id}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error("add_promo: failed: %s", e, exc_info=True)
        await message.answer(f"❌ Помилка збереження промокоду: {e}")


async def admin_stats_command(message: types.Message):
    """/stats — rich analytics dashboard for admins."""
    if not is_admin(message.from_user.id):
        await message.answer(_get_access_denied(message.from_user.id))
        return

    try:
        s = _calculate_extended_stats()
    except Exception as e:
        logger.error("admin_stats_command error: %s", e, exc_info=True)
        await message.answer("❌ Помилка отримання статистики")
        return

    # --- Revenue bar (visual progress) ---
    _goal = 500.0  # monthly target €
    _pct = min(int(s["revenue_30d"] / _goal * 10), 10)
    _bar = "█" * _pct + "░" * (10 - _pct)
    _pct_str = f"{s['revenue_30d'] / _goal * 100:.0f}%"

    # --- Top docs ---
    _top_str = ""
    _doc_labels = {
        "anmeldung": "Anmeldung", "ummeldung": "Ummeldung", "abmeldung": "Abmeldung",
        "buergergeld": "Bürgergeld", "kindergeld": "Kindergeld", "wohngeld": "Wohngeld",
        "elterngeld": "Elterngeld", "kinderzuschlag": "Kinderzuschlag",
        "aufenthaltstitel": "Aufenthaltstitel", "gewerbeanmeldung": "Gewerbeanmeldung",
    }
    for doc_type, cnt in s["top_docs"]:
        label = _doc_labels.get(doc_type, doc_type or "?")
        _top_str += f"   • {label}: {cnt}\n"
    if not _top_str:
        _top_str = "   • —\n"

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    text = (
        f"📊 <b>АНАЛІТИКА БОТА</b>\n"
        f"<i>{now_str}</i>\n"
        f"═══════════════════════\n\n"

        f"💰 <b>Дохід:</b>\n"
        f"   • Сьогодні:  {_format_price(s['revenue_today'])} ({s['paid_today']} оплат)\n"
        f"   • За 7 днів: {_format_price(s['revenue_7d'])} ({s['paid_7d']} оплат)\n"
        f"   • За 30 днів: {_format_price(s['revenue_30d'])} ({s['paid_30d']} оплат)\n"
        f"   • Всього: {_format_price(s['revenue_total'])}\n"
        f"   • Сер. чек: {_format_price(s['avg_order_value'])}\n\n"

        f"🎯 <b>Ціль €{_goal:.0f}/місяць:</b>\n"
        f"   [{_bar}] {_pct_str}\n\n"

        f"👥 <b>Користувачі:</b>\n"
        f"   • Всього: {s['total_users']}\n"
        f"   • Нових сьогодні: {s['new_users_today']}\n"
        f"   • Нових за 7д: {s['new_users_7d']}\n"
        f"   • Конверсія 7д: {s['conversion_7d']:.1f}%\n\n"

        f"📄 <b>Топ документів (30д):</b>\n"
        f"{_top_str}\n"

        f"⏰ <b>Termin модуль:</b>\n"
        f"   • Активних планів: {s['termin_active']}\n"
        f"   • Знайдено слотів (всього): {s['termin_found_total']:,}\n\n"

        f"═══════════════════════\n"
        f"🔧 Команди: /admin · /addpromo · /setprice"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔄 Оновити", callback_data="stats_refresh"),
        types.InlineKeyboardButton("📊 Воронка", callback_data="admin_funnel"),
    )
    kb.add(
        types.InlineKeyboardButton("📥 Експорт", callback_data="admin_export"),
        types.InlineKeyboardButton("🏠 Адмін", callback_data="admin_back"),
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


async def stats_refresh(callback_query: types.CallbackQuery):
    """/stats inline refresh button."""
    await callback_query.answer("🔄 Оновлюю...")
    if not is_admin(callback_query.from_user.id):
        return

    try:
        s = _calculate_extended_stats()
    except Exception as e:
        logger.error("stats_refresh error: %s", e)
        return

    _goal = 500.0
    _pct = min(int(s["revenue_30d"] / _goal * 10), 10)
    _bar = "█" * _pct + "░" * (10 - _pct)
    _pct_str = f"{s['revenue_30d'] / _goal * 100:.0f}%"

    _doc_labels = {
        "anmeldung": "Anmeldung", "ummeldung": "Ummeldung", "abmeldung": "Abmeldung",
        "buergergeld": "Bürgergeld", "kindergeld": "Kindergeld", "wohngeld": "Wohngeld",
        "elterngeld": "Elterngeld", "kinderzuschlag": "Kinderzuschlag",
        "aufenthaltstitel": "Aufenthaltstitel", "gewerbeanmeldung": "Gewerbeanmeldung",
    }
    _top_str = ""
    for doc_type, cnt in s["top_docs"]:
        label = _doc_labels.get(doc_type, doc_type or "?")
        _top_str += f"   • {label}: {cnt}\n"
    if not _top_str:
        _top_str = "   • —\n"

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    text = (
        f"📊 <b>АНАЛІТИКА БОТА</b>\n"
        f"<i>{now_str}</i>\n"
        f"═══════════════════════\n\n"
        f"💰 <b>Дохід:</b>\n"
        f"   • Сьогодні:  {_format_price(s['revenue_today'])} ({s['paid_today']} оплат)\n"
        f"   • За 7 днів: {_format_price(s['revenue_7d'])} ({s['paid_7d']} оплат)\n"
        f"   • За 30 днів: {_format_price(s['revenue_30d'])} ({s['paid_30d']} оплат)\n"
        f"   • Всього: {_format_price(s['revenue_total'])}\n"
        f"   • Сер. чек: {_format_price(s['avg_order_value'])}\n\n"
        f"🎯 <b>Ціль €{_goal:.0f}/місяць:</b>\n"
        f"   [{_bar}] {_pct_str}\n\n"
        f"👥 <b>Користувачі:</b>\n"
        f"   • Всього: {s['total_users']}\n"
        f"   • Нових сьогодні: {s['new_users_today']}\n"
        f"   • Нових за 7д: {s['new_users_7d']}\n"
        f"   • Конверсія 7д: {s['conversion_7d']:.1f}%\n\n"
        f"📄 <b>Топ документів (30д):</b>\n"
        f"{_top_str}\n"
        f"⏰ <b>Termin модуль:</b>\n"
        f"   • Активних планів: {s['termin_active']}\n"
        f"   • Знайдено слотів (всього): {s['termin_found_total']:,}\n\n"
        f"═══════════════════════\n"
        f"🔧 Команди: /admin · /addpromo · /setprice"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔄 Оновити", callback_data="stats_refresh"),
        types.InlineKeyboardButton("📊 Воронка", callback_data="admin_funnel"),
    )
    kb.add(
        types.InlineKeyboardButton("📥 Експорт", callback_data="admin_export"),
        types.InlineKeyboardButton("🏠 Адмін", callback_data="admin_back"),
    )

    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass


async def admin_broadcast_command(message: types.Message):
    """Broadcast command placeholder."""
    if not is_admin(message.from_user.id):
        await message.answer(_get_access_denied(message.from_user.id))
        return
    
    await message.answer(
        "📢 <b>Розсилка</b>\n\n"
        "Функція масової розсилки буде додана в наступній версії.\n\n"
        "Для безпеки користувачів, розсилки вимагають:\n"
        "• Окремого модуля з підтвердженням\n"
        "• Контролю частоти відправки\n"
        "• Можливості відписки\n"
        "• Логування всіх розсилок",
        parse_mode="HTML"
    )


# ============================================================================
# DEV/TEST ONLY: Reset stale Termin state for a specific user
# ============================================================================
# WHY: The termin_assistant.db may retain has_paid_termin=1 from previous
#      test payments. Since the webhook is the single source of truth,
#      this flag is never auto-cleared. Use this command to reset a
#      specific user's Termin state during development/testing.
#
# DB FILE: GERMAN_DOC_BOT/termin_assistant.db
# USAGE:   /termin_reset <telegram_id>
# EFFECT:  has_paid_termin=0, city=NULL, authority=NULL for that user only
# ============================================================================
# Pending confirmations: {admin_id: {"target_id": str, "expires": float}}
_termin_reset_pending: dict = {}


async def termin_reset_command(message: types.Message):
    """Admin-only: reset Termin paid state + entitlements for a user (dev/test).
    Usage: /termin_reset <telegram_id>
    Requires two-step confirmation — reply /termin_reset <id> confirm within 60 s.
    """
    import time as _time
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer(
            "Usage: /termin_reset <telegram_id>\n"
            "Then confirm: /termin_reset <telegram_id> confirm\n\n"
            "Resets has_paid_termin, city, authority AND deactivates entitlements."
        )
        return

    target_id = parts[1].strip()
    confirmed = len(parts) >= 3 and parts[2].lower() == "confirm"
    admin_id = message.from_user.id

    if not confirmed:
        # Step 1: require confirmation within 60 s
        from backend.termin_db import get_user
        user = get_user(target_id)
        if not user:
            await message.answer(f"❌ User {target_id} not found in termin DB.")
            return
        _termin_reset_pending[admin_id] = {
            "target_id": target_id,
            "expires": _time.time() + 60,
        }
        await message.answer(
            f"⚠️ <b>Підтвердіть скидання Termin</b>\n\n"
            f"Користувач: <code>{target_id}</code>\n"
            f"has_paid_termin: {user.get('has_paid_termin', 0)} → <b>0</b>\n"
            f"city: {user.get('city') or 'None'} → <b>None</b>\n\n"
            f"Для підтвердження надішліть протягом 60 с:\n"
            f"<code>/termin_reset {target_id} confirm</code>",
            parse_mode="HTML",
        )
        return

    # Step 2: verify pending confirmation
    pending = _termin_reset_pending.get(admin_id)
    if not pending or pending["target_id"] != target_id or _time.time() > pending["expires"]:
        await message.answer("❌ Підтвердження не знайдено або застаріло. Надішліть команду знову.")
        _termin_reset_pending.pop(admin_id, None)
        return

    _termin_reset_pending.pop(admin_id, None)

    try:
        from backend.termin_db import get_user, update_user, get_connection
        user = get_user(target_id)
        if not user:
            await message.answer(f"❌ User {target_id} not found in termin DB.")
            return

        old_paid = user.get('has_paid_termin', 0)
        old_city = user.get('city')
        old_auth = user.get('authority')

        update_user(target_id, has_paid_termin=0, city=None, authority=None, reminder_active=0)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE termin_entitlements SET active=0, found_termin=0 WHERE user_id=?",
            (str(target_id),),
        )
        ent_rows = cur.rowcount
        conn.commit()
        conn.close()

        await message.answer(
            f"✅ Termin reset for user {target_id}:\n"
            f"  has_paid_termin: {old_paid} → 0\n"
            f"  city: {old_city} → None\n"
            f"  authority: {old_auth} → None\n"
            f"  entitlements deactivated: {ent_rows} row(s)"
        )
        logger.info("TERMIN_RESET admin=%s target=%s ent_rows=%s", admin_id, target_id, ent_rows)
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
        logger.error("TERMIN_RESET_ERROR: %s", e)


async def reset_termin_self_command(message: types.Message):
    """Admin-only: /reset_termin — reset YOUR OWN termin entitlement (quick dev shortcut)."""
    if not is_admin(message.from_user.id):
        return

    user_id = str(message.from_user.id)
    try:
        from backend.termin_db import update_user, get_connection
        update_user(user_id, has_paid_termin=0, reminder_active=0)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE termin_entitlements SET active=0, found_termin=0 WHERE user_id=?",
            (user_id,),
        )
        ent_rows = cur.rowcount
        conn.commit()
        conn.close()

        await message.answer(
            f"✅ Your termin entitlement reset.\n"
            f"  Entitlement rows deactivated: {ent_rows}\n\n"
            f"Now /start → city → doc → must show €4.99 payment screen."
        )
        logger.info("RESET_TERMIN_SELF admin=%s ent_rows=%s", user_id, ent_rows)
    except Exception as e:
        await message.answer(f"❌ Error: {e}")
        logger.error("RESET_TERMIN_SELF_ERROR: %s", e)


def register_admin_handlers(dp: Dispatcher):
    """Register all admin handlers with dispatcher."""
    dp.register_message_handler(admin_panel, commands=['admin'])
    dp.register_message_handler(set_price, commands=['setprice'])
    dp.register_message_handler(add_promo, commands=['addpromo'])
    dp.register_message_handler(admin_stats_command, commands=['stats'])
    dp.register_message_handler(admin_broadcast_command, commands=['broadcast'])
    dp.register_message_handler(termin_reset_command, commands=['termin_reset'])
    dp.register_message_handler(reset_termin_self_command, commands=['reset_termin'])
    
    dp.register_callback_query_handler(
        admin_refresh,
        lambda c: c.data == 'admin_refresh'
    )
    dp.register_callback_query_handler(
        admin_funnel,
        lambda c: c.data == 'admin_funnel'
    )
    dp.register_callback_query_handler(
        admin_export,
        lambda c: c.data == 'admin_export'
    )
    dp.register_callback_query_handler(
        admin_export_users,
        lambda c: c.data and c.data.startswith('export_users_')
    )
    dp.register_callback_query_handler(
        admin_export_orders,
        lambda c: c.data and c.data.startswith('export_orders_')
    )
    dp.register_callback_query_handler(
        admin_prices,
        lambda c: c.data == 'admin_prices'
    )
    dp.register_callback_query_handler(
        admin_promos,
        lambda c: c.data == 'admin_promos'
    )
    dp.register_callback_query_handler(
        admin_back,
        lambda c: c.data == 'admin_back'
    )
    dp.register_callback_query_handler(
        stats_refresh,
        lambda c: c.data == 'stats_refresh'
    )

    logger.info("✅ Admin handlers registered (full functionality)")