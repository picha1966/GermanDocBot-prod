# -*- coding: utf-8 -*-
"""
"What do I need to do in Germany?" — free guided flow.
One question per screen, progress indicator, exit anytime.
All text via get_text("what_to_do", key, lang). No PDF, no payment.
"""

import logging
from typing import Dict, Any, Optional

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import DocumentState
from utils.helpers import get_user_lang, get_db
from backend.texts import get_text
from backend.what_to_do_config import QUESTIONS, get_result_items, get_recommended_document

logger = logging.getLogger(__name__)

TOTAL_STEPS = len(QUESTIONS)


def _norm_lang(lang: Optional[str]) -> str:
    if not lang:
        return "uk"
    lang = (lang or "").strip().lower()
    if lang == "ua":
        return "uk"
    return lang if lang in ("uk", "en", "de", "pl", "tr", "ar") else "uk"


def _get_wtd(key: str, lang: str) -> str:
    """Get what_to_do translation; fallback to uk only (never English)."""
    t = get_text("what_to_do", key, lang)
    if t:
        return t
    return get_text("what_to_do", key, "uk") or key


def _build_question_message(step_index: int, lang: str) -> tuple:
    """Return (text, keyboard) for the given step. Used for both send and edit."""
    q = QUESTIONS[step_index]
    step_of = _get_wtd("step_of", lang)
    try:
        step_label = step_of % (step_index + 1, TOTAL_STEPS)
    except (TypeError, ValueError):
        step_label = f"{step_index + 1} / {TOTAL_STEPS}"
    text = f"<b>{step_label}</b>\n\n" + _get_wtd(q["key"], lang)
    from handlers.nav import nav_home_text
    kb = InlineKeyboardMarkup(row_width=1)
    for opt in q["options"]:
        kb.add(InlineKeyboardButton(
            _get_wtd(opt["key"], lang),
            callback_data=f"wtd_{step_index}_{opt['value']}",
        ))
    kb.add(InlineKeyboardButton(_get_wtd("exit_flow", lang), callback_data="what_to_do_exit"))
    kb.add(InlineKeyboardButton(nav_home_text(lang), callback_data="main_menu"))
    return text, kb


async def _send_question(
    message: types.Message,
    step_index: int,
    lang: str,
    state: FSMContext,
    use_edit: bool = True,
) -> None:
    """Show one question (edit existing message or send new)."""
    text, kb = _build_question_message(step_index, lang)
    if use_edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await state.update_data(step=step_index)


async def handle_what_to_do_start(callback_query: types.CallbackQuery, state: FSMContext):
    """Entry: show intro and first question. All text from i18n."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = _norm_lang(get_user_lang(user_id))

    await state.set_state(DocumentState.what_to_do_flow)
    await state.update_data(step=0, answers={})

    intro = _get_wtd("what_to_do_intro", lang)
    try:
        await callback_query.message.edit_text(intro, parse_mode="HTML")
    except Exception:
        await callback_query.message.answer(intro, parse_mode="HTML")
    # First question in a new message so intro stays visible
    await _send_question(callback_query.message, 0, lang, state, use_edit=False)


async def handle_what_to_do_answer(callback_query: types.CallbackQuery, state: FSMContext):
    """Process answer: store, then next question or result screen."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = _norm_lang(get_user_lang(user_id))
    data = await state.get_data()
    step = data.get("step", 0)
    answers = data.get("answers") or {}

    # Parse callback_data: wtd_{step_index}_{value}
    raw = (callback_query.data or "").strip()
    if not raw.startswith("wtd_"):
        await state.finish()
        return
    rest = raw[4:]  # after "wtd_"
    parts = rest.split("_", 1)
    if len(parts) < 2:
        await state.finish()
        return
    try:
        step_parsed = int(parts[0])
    except ValueError:
        await state.finish()
        return
    value = parts[1]
    if step_parsed < 0 or step_parsed >= len(QUESTIONS):
        await state.finish()
        return
    q_key = QUESTIONS[step_parsed]["key"]
    answers[q_key] = value
    next_step = step + 1

    if next_step >= TOTAL_STEPS:
        await _show_result(callback_query.message, answers, lang, state)
        return

    await state.update_data(step=next_step, answers=answers)
    await _send_question(callback_query.message, next_step, lang, state, use_edit=True)


def _build_result_message(answers: Dict[str, str], lang: str) -> str:
    """Build result screen with 4 sections. All text from i18n."""
    items = get_result_items(answers)
    lines = []
    for section in ("must", "should", "not_needed", "notes"):
        ids_list = items.get(section, [])
        if not ids_list:
            continue
        title_key = f"result_{section}_title"
        title = _get_wtd(title_key, lang)
        lines.append(title)
        for item_id in ids_list:
            lines.append("• " + _get_wtd(f"result_{item_id}", lang))
        lines.append("")
    return "\n".join(lines).strip()


async def _show_result(message: types.Message, answers: Dict[str, str], lang: str, state: FSMContext):
    """Show result screen and optional recommendation button."""
    await state.finish()

    body = _build_result_message(answers, lang)
    if not body:
        body = _get_wtd("result_notes_title", lang) + "\n• " + _get_wtd("result_note_deadline", lang)

    kb = InlineKeyboardMarkup(row_width=1)
    doc = get_recommended_document(answers)
    if doc and doc == "anmeldung":
        rec_text = _get_wtd("recommendation_text", lang)
        rec_btn = _get_wtd("recommendation_btn", lang)
        body = body + "\n\n" + rec_text
        kb.add(InlineKeyboardButton(rec_btn, callback_data="doc_anmeldung"))
    back_label = get_text("document", "back_to_menu", lang) or get_text("document", "back_to_menu", "uk") or _get_wtd("exit_flow", lang)
    kb.add(InlineKeyboardButton(back_label, callback_data="back_to_main_menu"))
    from handlers.nav import nav_home_text
    kb.add(InlineKeyboardButton(nav_home_text(lang), callback_data="main_menu"))

    try:
        await message.edit_text(body, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await message.answer(body, parse_mode="HTML", reply_markup=kb)


async def handle_what_to_do_exit(callback_query: types.CallbackQuery, state: FSMContext):
    """Exit flow and return to main menu."""
    await callback_query.answer()
    await state.finish()
    from handlers.start import _show_main_menu
    lang = _norm_lang(get_user_lang(callback_query.from_user.id))
    await _show_main_menu(callback_query.message, lang)


def register_what_to_do_handlers(dp):
    """Register what_to_do flow handlers."""
    dp.register_callback_query_handler(
        handle_what_to_do_start,
        lambda c: c.data and c.data == "what_to_do_start",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_what_to_do_answer,
        lambda c: c.data and c.data.startswith("wtd_"),
        state=DocumentState.what_to_do_flow,
    )
    dp.register_callback_query_handler(
        handle_what_to_do_exit,
        lambda c: c.data and c.data == "what_to_do_exit",
        state=DocumentState.what_to_do_flow,
    )
    logger.info("✅ What-to-do flow handlers registered")
