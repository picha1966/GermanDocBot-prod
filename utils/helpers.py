# -*- coding: utf-8 -*-
"""GERMAN_DOC_BOT v5.0 - Helper Functions"""

import config

_db = None
_error_reporter = None


def get_db():
    """Get Database instance"""
    global _db
    if _db is None:
        try:
            from database import Database
        except ImportError:
            from backend.database import Database
        _db = Database(config.DB_PATH)
    return _db


def get_user_lang(user_id: int) -> str:
    """Get user language from DB"""
    db = get_db()
    profile = db.get_profile(user_id)
    return profile.get('lang', config.DEFAULT_LANGUAGE) if profile else config.DEFAULT_LANGUAGE


def set_user_lang(user_id: int, lang: str) -> None:
    """Set user language in DB"""
    db = get_db()
    db.set_user_lang(user_id, lang)


def get_document_price(doc_type: str) -> float:
    """Get document price (DB → settings → default)"""
    db = get_db()
    db_price = db.get_document_price(doc_type)
    if db_price is not None:
        return db_price
    return config.settings.get_document_price(doc_type)


def format_price(amount: float) -> str:
    """Format price in EUR"""
    try:
        from stripe_handler import format_price as fmt
    except ImportError:
        from backend.stripe_handler import format_price as fmt
    return fmt(amount)


async def notify_admin_error(error: Exception, context: dict = None, user_id: int = None, current_step: str = None):
    """Notify admins about error"""
    global _error_reporter
    if _error_reporter is None:
        try:
            from error_reporter import error_reporter
        except ImportError:
            from backend.error_reporter import error_reporter
        _error_reporter = error_reporter
    
    await _error_reporter.report(
        exception=error,
        user_id=user_id,
        current_step=current_step,
        context=context,
        severity='error'
    )
