# -*- coding: utf-8 -*-
"""
Post-PDF retention nudges (10 min / 24 h / 3 d). Scheduled from webhook after PDF_DELIVERED.

- Scheduling is idempotent per order (`orders.retention_followups_scheduled`) so Stripe
  webhook retries do not enqueue duplicate task chains.
- Timers run in-process (asyncio.sleep): a full process restart cancels pending sends;
  use an external job queue later if hard delivery guarantees are required.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Callbacks dedicated to retention analytics (avoid mixing with LTV / generic main_menu).
RETENTION_TERMIN_CB = "retention_termin_from_pdf"
RETENTION_MAIN_MENU_CB = "retention_main_menu"
# 24h cross-sell only — distinct from LTV upsell_doc_* for clean RETENTION_CLICK metrics
RETENTION_UPSELL_DOC_PREFIX = "retention_upsell_doc_"


def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "en").strip().lower()
    if l == "ua":
        l = "uk"
    if l not in ("uk", "en", "de", "pl", "tr", "ar"):
        l = "en"
    return l


def user_should_skip_retention_followup(
    user_id: int, anchor_order_id: Optional[int]
) -> bool:
    """
    Skip 24h/3d (and 10min after sleep) if user already has Termin entitlement
    or any newer paid / in-flight order than the PDF delivery anchor.
    """
    if not anchor_order_id:
        return False
    try:
        from backend.termin_db import is_termin_entitled

        if is_termin_entitled(str(user_id)):
            return True
    except Exception:
        pass

    try:
        from backend.database import get_db

        db = get_db()
        anchor = db.get_order(int(anchor_order_id))
        if not anchor:
            return False

        paid_like = {"paid", "sent", "processing", "downloaded"}
        orders = db.get_user_orders(user_id, limit=80)
        aid = int(anchor_order_id)
        for o in orders:
            oid = o.get("order_id")
            if oid is None:
                oid = o.get("id")
            if oid is None:
                continue
            try:
                oid_i = int(oid)
            except (TypeError, ValueError):
                continue
            if oid_i <= aid:
                continue
            st = (o.get("status") or "").lower()
            if st in paid_like:
                return True
    except Exception:
        pass
    return False


# 10 min — “new slots” angle (distinct from immediate LTV Termin copy)
_RETENTION_10MIN: dict[str, str] = {
    "uk": (
        "👀 <b>Ми перевірили систему</b> — інколи з’являються нові записи (Termin) "
        "у відповідних органах.\n\n"
        "Якщо ви ще підбираєте слот — натисніть нижче, допоможемо з пошуком."
    ),
    "en": (
        "👀 <b>We checked</b> — new appointment slots (Termin) sometimes open up "
        "at the relevant offices.\n\n"
        "If you’re still looking for a slot — tap below and we’ll help you search."
    ),
    "de": (
        "👀 <b>Wir haben nachgeschaut</b> — bei den Behörden kommen manchmal neue "
        "Termine (Termin) dazu.\n\n"
        "Wenn Sie noch einen Slot suchen — tippen Sie unten, wir helfen bei der Suche."
    ),
    "pl": (
        "👀 <b>Sprawdziliśmy</b> — w urzędach czasem pojawiają się nowe terminy (Termin).\n\n"
        "Jeśli nadal szukasz terminu — kliknij poniżej, pomożemy w wyszukiwaniu."
    ),
    "tr": (
        "👀 <b>Kontrol ettik</b> — ilgili kurumlarda bazen yeni randevu (Termin) "
        "açılıyor.\n\n"
        "Hâlâ slot arıyorsanız — aşağıya dokunun, aramada yardımcı olalım."
    ),
    "ar": (
        "👀 <b>تحققنا</b> — تظهر أحيانًا مواعيد جديدة (Termin) في الجهات المختصة.\n\n"
        "إذا كنت لا تزال تبحث عن موعد — اضغط أدناه وسنساعدك في البحث."
    ),
}

# 24 h — cross-sell related documents (same callbacks as LTV: upsell_doc_*)
_RETENTION_24H_HEADER: dict[str, str] = {
    "uk": "📎 <b>Нагадування:</b> часто після цього документа потрібні ще такі бланки:",
    "en": "📎 <b>Reminder:</b> people often need these forms next after yours:",
    "de": "📎 <b>Erinnerung:</b> oft werden nach diesem Dokument noch diese Formulare benötigt:",
    "pl": "📎 <b>Przypomnienie:</b> często po tym dokumencie potrzebne są jeszcze te formularze:",
    "tr": "📎 <b>Hatırlatma:</b> bu belgeden sonra genelde şu formlar da gerekiyor:",
    "ar": "📎 <b>تذكير:</b> غالبًا يحتاج الناس بعد مستندك إلى هذه النماذج أيضًا:",
}

# 3 d — soft “come back” (no ads; retention main menu only)
_RETENTION_3D: dict[str, str] = {
    "uk": (
        "👋 <b>Повернімось до ваших документів?</b>\n\n"
        "Якщо знадобиться ще один бланк для Німеччини — відкрийте меню нижче."
    ),
    "en": (
        "👋 <b>Back to your German paperwork?</b>\n\n"
        "If you need another form — open the menu below."
    ),
    "de": (
        "👋 <b>Wieder etwas für Ihre Unterlagen?</b>\n\n"
        "Wenn Sie noch ein Formular brauchen — öffnen Sie unten das Menü."
    ),
    "pl": (
        "👋 <b>Wracamy do dokumentów?</b>\n\n"
        "Jeśli potrzebujesz kolejnego formularza — otwórz menu poniżej."
    ),
    "tr": (
        "👋 <b>Tekrar belgelere dönelim mi?</b>\n\n"
        "Başka bir forma gerekirse — aşağıdaki menüyü açın."
    ),
    "ar": (
        "👋 <b>العودة إلى مستنداتك؟</b>\n\n"
        "إذا احتجتَ إلى نموذج آخر — افتح القائمة أدناه."
    ),
}

_RETENTION_MAIN_MENU: dict[str, str] = {
    "uk": "🏠 Головне меню",
    "en": "🏠 Main menu",
    "de": "🏠 Hauptmenü",
    "pl": "🏠 Menu główne",
    "tr": "🏠 Ana menü",
    "ar": "🏠 القائمة الرئيسية",
}


async def send_after_10min(
    bot: Bot,
    user_id: int,
    doc_type: Optional[str],
    lang: str,
    city: Optional[str],
    anchor_order_id: Optional[int],
) -> None:
    try:
        await asyncio.sleep(600)
        from backend.termin_db import is_termin_entitled

        if is_termin_entitled(str(user_id)):
            return
        if user_should_skip_retention_followup(user_id, anchor_order_id):
            return

        _l = _norm_lang(lang)
        from handlers.stripe_handler import _LTV_BTN_FIND_TERMIN

        text = _RETENTION_10MIN.get(_l, _RETENTION_10MIN["en"])
        btn = _LTV_BTN_FIND_TERMIN.get(_l, _LTV_BTN_FIND_TERMIN["en"])
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(btn, callback_data=RETENTION_TERMIN_CB)
        )
        await bot.send_message(
            chat_id=int(user_id),
            text=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
        logger.info(
            "RETENTION_10MIN_SENT user=%s doc=%s lang=%s city=%s anchor_order=%s",
            user_id,
            doc_type,
            _l,
            (city or "").strip() or None,
            anchor_order_id,
        )
    except Exception as e:
        logger.warning(
            "retention send_after_10min failed user=%s doc=%s err=%s",
            user_id,
            doc_type,
            e,
        )


async def send_after_24h(
    bot: Bot,
    user_id: int,
    doc_type: Optional[str],
    lang: str,
    city: Optional[str],
    anchor_order_id: Optional[int],
) -> None:
    try:
        await asyncio.sleep(86400)
        if user_should_skip_retention_followup(user_id, anchor_order_id):
            return

        from handlers.stripe_handler import CROSS_SELL_DOC_NAMES, CROSS_SELL_MAP

        _dt = (doc_type or "").strip().lower()
        _related = CROSS_SELL_MAP.get(_dt, [])[:3]
        if not _related:
            return

        _l = _norm_lang(lang)
        header = _RETENTION_24H_HEADER.get(_l, _RETENTION_24H_HEADER["en"])
        kb = InlineKeyboardMarkup(row_width=1)
        for _rd in _related:
            _name_map = CROSS_SELL_DOC_NAMES.get(_rd, {})
            _name = (
                _name_map.get(_l)
                or _name_map.get("en")
                or _rd.replace("_", " ").title()
            )
            kb.add(
                InlineKeyboardButton(
                    f"📄 {_name}",
                    callback_data=f"{RETENTION_UPSELL_DOC_PREFIX}{_rd}",
                )
            )

        await bot.send_message(
            chat_id=int(user_id),
            text=header,
            parse_mode="HTML",
            reply_markup=kb,
        )
        logger.info(
            "RETENTION_24H_SENT user=%s doc=%s lang=%s city=%s anchor_order=%s",
            user_id,
            doc_type,
            _l,
            (city or "").strip() or None,
            anchor_order_id,
        )
    except Exception as e:
        logger.warning(
            "retention send_after_24h failed user=%s doc=%s err=%s",
            user_id,
            doc_type,
            e,
        )


async def send_after_3days(
    bot: Bot,
    user_id: int,
    doc_type: Optional[str],
    lang: str,
    city: Optional[str],
    anchor_order_id: Optional[int],
) -> None:
    try:
        await asyncio.sleep(259200)
        if user_should_skip_retention_followup(user_id, anchor_order_id):
            return

        _l = _norm_lang(lang)
        text = _RETENTION_3D.get(_l, _RETENTION_3D["en"])
        btn = _RETENTION_MAIN_MENU.get(_l, _RETENTION_MAIN_MENU["en"])
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(btn, callback_data=RETENTION_MAIN_MENU_CB)
        )
        await bot.send_message(
            chat_id=int(user_id),
            text=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
        logger.info(
            "RETENTION_3D_SENT user=%s doc=%s lang=%s city=%s anchor_order=%s",
            user_id,
            doc_type,
            _l,
            (city or "").strip() or None,
            anchor_order_id,
        )
    except Exception as e:
        logger.warning(
            "retention send_after_3days failed user=%s doc=%s err=%s",
            user_id,
            doc_type,
            e,
        )


async def schedule_retention_messages(
    bot: Bot,
    user_id: int,
    doc_type: Optional[str],
    lang: str,
    city: Optional[str],
    anchor_order_id: Optional[int] = None,
) -> None:
    """Schedule 10 min / 24 h / 3 d follow-ups (independent asyncio tasks)."""
    asyncio.create_task(
        send_after_10min(bot, user_id, doc_type, lang, city, anchor_order_id)
    )
    asyncio.create_task(
        send_after_24h(bot, user_id, doc_type, lang, city, anchor_order_id)
    )
    asyncio.create_task(
        send_after_3days(bot, user_id, doc_type, lang, city, anchor_order_id)
    )
