# -*- coding: utf-8 -*-
"""
UX helpers: Situation Checker, Life Checklist, Deadlines.
Additive only — no PDF logic, no changes to existing document flow.
All texts via get_text(situation_checker|life_checklist|deadlines, key, lang).
"""

import logging
from typing import Dict, Any, Optional

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from states import DocumentState
from utils.helpers import get_user_lang
from backend.texts import get_text

logger = logging.getLogger(__name__)

SC_RESIDENCE_KEYS = ["sc_q1", "sc_q2", "sc_q3", "sc_q4", "sc_q5", "sc_q6"]
SC_WORK_KEYS = ["sc_work_q1", "sc_work_q2", "sc_work_q3"]
SC_BENEFITS_KEYS = ["sc_benefits_q1", "sc_benefits_q2", "sc_benefits_q3"]

def _get_question_keys(category: str):
    if category == "residence":
        return SC_RESIDENCE_KEYS
    if category == "work":
        return SC_WORK_KEYS
    if category == "benefits":
        return SC_BENEFITS_KEYS
    return SC_RESIDENCE_KEYS


def _category_to_callback(category: str) -> str:
    """Return callback_data to return to this category (documents list)."""
    return {"residence": "category_residence", "work": "category_employment", "benefits": "category_benefits"}.get(category, "category_residence")


def _situation_to_display_category(category: str) -> str:
    """Map situation_category (residence/work/benefits) to start.py category key (residence/employment/benefits)."""
    return {"residence": "residence", "work": "employment", "benefits": "benefits"}.get(category, "residence")


def _norm_lang(lang: Optional[str]) -> str:
    if not lang:
        return "uk"
    lang = (lang or "").strip().lower()
    if lang == "ua":
        return "uk"
    return lang if lang in ("uk", "en", "de", "pl", "tr", "ar") else "uk"


def _sc_get(key: str, lang: str) -> str:
    t = get_text("situation_checker", key, lang)
    return t or get_text("situation_checker", key, "uk") or key


# --- Feature 1: Situation Checker (per-category: residence / work / benefits) ---


async def handle_situation_start(callback_query: types.CallbackQuery, state: FSMContext):
    """Entry from category: situation_residence | situation_work | situation_benefits. Store category, show intro + first question."""
    await callback_query.answer()
    raw = (callback_query.data or "").strip()
    category = "residence"
    if raw == "situation_work":
        category = "work"
    elif raw == "situation_benefits":
        category = "benefits"
    user_id = callback_query.from_user.id
    lang = _norm_lang(get_user_lang(user_id))
    await state.set_state(DocumentState.situation_checker_flow)
    await state.update_data(step=0, answers={}, situation_category=category)
    intro_key = "sc_intro" if category == "residence" else ("sc_work_intro" if category == "work" else "sc_benefits_intro")
    intro = _sc_get(intro_key, lang)
    try:
        await callback_query.message.edit_text(intro, parse_mode="HTML")
    except Exception:
        await callback_query.message.answer(intro, parse_mode="HTML")
    await _sc_send_question(callback_query.message, 0, lang, state, category, use_edit=False)


async def _sc_send_question(
    message: types.Message, step_index: int, lang: str, state: FSMContext, category: str, use_edit: bool = True
):
    """Show one question for the given category (step_index 0..N-1)."""
    keys = _get_question_keys(category)
    total = len(keys)
    if step_index >= total:
        return
    q_key = keys[step_index]
    step_label = _sc_get("sc_step_of", lang)
    try:
        step_label = step_label % (step_index + 1, total)
    except (TypeError, ValueError):
        step_label = f"{step_index + 1} / {total}"
    text = f"<b>{step_label}</b>\n\n" + _sc_get(q_key, lang)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_sc_get("sc_yes", lang), callback_data=f"sc_{step_index}_yes"))
    kb.add(InlineKeyboardButton(_sc_get("sc_no", lang), callback_data=f"sc_{step_index}_no"))
    from handlers.start import _nav_back_text, _nav_home_text
    kb.add(InlineKeyboardButton(_nav_back_text(lang), callback_data="situation_checker_exit"))
    kb.add(InlineKeyboardButton(_nav_home_text(lang), callback_data="back_to_main_menu"))
    if use_edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await state.update_data(step=step_index)


def _sc_evaluate(answers: Dict[str, str]) -> Dict[str, bool]:
    """Rule-based: need_anmeldung, need_abmeldung, show_deadline_note."""
    q1 = (answers.get("q1") or "").strip().lower() == "yes"
    q2 = (answers.get("q2") or "").strip().lower() == "yes"
    q3 = (answers.get("q3") or "").strip().lower() == "yes"
    q4 = (answers.get("q4") or "").strip().lower() == "yes"
    need_anmeldung = (q1 or q2) and not q3
    need_abmeldung = q4
    show_deadline = need_anmeldung
    return {"need_anmeldung": need_anmeldung, "need_abmeldung": need_abmeldung, "show_deadline": show_deadline}


async def _sc_show_result(message: types.Message, answers: Dict[str, str], lang: str, state: FSMContext, category: str):
    """Result screen: «За вашою ситуацією вам потрібно» + docs for this category + how to continue. Buttons return to SAME category."""
    back_cb = _category_to_callback(category)
    parts = [_sc_get("sc_result_intro", lang)]
    if category == "residence":
        ev = _sc_evaluate(answers)
        if ev["need_anmeldung"] or ev["need_abmeldung"]:
            parts.append(_sc_get("sc_section_residence", lang))
            if ev["need_anmeldung"]:
                parts.append(_sc_get("sc_doc_anmeldung", lang))
            if ev["need_abmeldung"]:
                parts.append(_sc_get("sc_doc_abmeldung", lang))
            parts.append("")
        else:
            parts.append(_sc_get("result_anmeldung_no", lang))
            parts.append(_sc_get("result_abmeldung_no", lang))
            parts.append("")
        if ev["show_deadline"]:
            parts.append(_sc_get("result_deadline_note", lang))
            parts.append("")
    elif category == "work":
        parts.append(_sc_get("sc_section_employment", lang))
        parts.append(_sc_get("sc_work_result_docs", lang))
        parts.append("")
    else:
        parts.append(_sc_get("sc_section_benefits", lang))
        parts.append(_sc_get("sc_benefits_result_docs", lang))
        parts.append("")
    parts.append(_sc_get("sc_how_to_continue", lang))
    parts.append(_sc_get("sc_step1", lang))
    parts.append(_sc_get("sc_step2", lang))
    parts.append(_sc_get("sc_step3", lang))
    parts.append("")
    parts.append(_sc_get("sc_what_next", lang))
    text = "\n".join(parts)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_sc_get("sc_cta_documents", lang), callback_data=back_cb))
    from handlers.start import _nav_back_text, _nav_home_text
    kb.add(InlineKeyboardButton(_nav_back_text(lang), callback_data=back_cb))
    kb.add(InlineKeyboardButton(_nav_home_text(lang), callback_data="back_to_main_menu"))
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    await state.finish()


async def handle_situation_checker_answer(callback_query: types.CallbackQuery, state: FSMContext):
    """Process answer: store, then next question or (if last) show result. Category from state."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = _norm_lang(get_user_lang(user_id))
    data = await state.get_data()
    step = data.get("step", 0)
    answers = data.get("answers") or {}
    category = data.get("situation_category") or "residence"
    question_keys = _get_question_keys(category)
    raw = (callback_query.data or "").strip()
    # Exit is handled by handle_situation_checker_exit (registered with same state, before this handler)
    if not raw.startswith("sc_"):
        await state.finish()
        from handlers.start import _show_main_menu
        await _show_main_menu(callback_query.message, lang)
        return
    parts = raw.split("_")
    if len(parts) < 3:
        await state.finish()
        return
    try:
        step_parsed = int(parts[1])
    except ValueError:
        await state.finish()
        return
    value = parts[2].lower()
    if step_parsed != step or value not in ("yes", "no"):
        return
    answers[f"q{step + 1}"] = value
    await state.update_data(answers=answers)

    if step >= len(question_keys) - 1:
        await _sc_show_result(callback_query.message, answers, lang, state, category)
        return

    next_step = step + 1
    await _sc_send_question(callback_query.message, next_step, lang, state, category, use_edit=True)


async def handle_situation_checker_exit(callback_query: types.CallbackQuery, state: FSMContext):
    """Exit flow: always works at any step. Clears FSM and returns to the category from which user started."""
    await callback_query.answer()
    try:
        data = await state.get_data()
        category = data.get("situation_category") or "residence"
        display_cat = _situation_to_display_category(category)
    except Exception:
        display_cat = "residence"
    await state.finish()
    lang = _norm_lang(get_user_lang(callback_query.from_user.id))
    from handlers.start import _show_category_documents
    await _show_category_documents(callback_query.message, display_cat, lang)


# --- Feature 2: Life Checklist (static + doc buttons) ---


def _lc_get(key: str, lang: str) -> str:
    t = get_text("life_checklist", key, lang)
    return t or get_text("life_checklist", key, "uk") or key


async def handle_life_checklist(callback_query: types.CallbackQuery):
    """Show static checklist; items that have a document get 'Fill document' button."""
    await callback_query.answer()
    user_id = callback_query.from_user.id
    lang = _norm_lang(get_user_lang(user_id))
    title = _lc_get("life_checklist_title", lang)
    lines = [
        _lc_get("lc_anmeldung", lang),
        _lc_get("lc_steuer_id", lang),
        _lc_get("lc_krankenkasse", lang),
        _lc_get("lc_rundfunkbeitrag", lang),
        _lc_get("lc_schule_kita", lang),
    ]
    text = title + "\n\n" + "\n".join(lines)
    kb = InlineKeyboardMarkup(row_width=1)
    fill_btn = _lc_get("fill_document_btn", lang)
    kb.add(InlineKeyboardButton(fill_btn, callback_data="doc_anmeldung"))
    kb.add(InlineKeyboardButton(_lc_get("back_to_menu", lang), callback_data="back_to_main_menu"))
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback_query.message.answer(text, parse_mode="HTML", reply_markup=kb)


# --- Feature 3: Deadlines (static list, no reminders) ---


def _dl_get(key: str, lang: str) -> str:
    t = get_text("deadlines", key, lang)
    return t or get_text("deadlines", key, "uk") or key


async def handle_deadlines(callback_query: types.CallbackQuery):
    """Show static deadlines list. No reminders, no scheduling."""
    await callback_query.answer()
    lang = _norm_lang(get_user_lang(callback_query.from_user.id))
    title = _dl_get("deadlines_title", lang)
    lines = [_dl_get("d_anmeldung", lang), _dl_get("d_ummeldung", lang), _dl_get("d_kindergeld", lang)]
    text = title + "\n\n" + "\n".join(lines)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_dl_get("back_to_menu", lang), callback_data="back_to_main_menu"))
    try:
        await callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback_query.message.answer(text, parse_mode="HTML", reply_markup=kb)


# --- Registration ---


def register_ux_helpers(dp):
    """Register Situation Checker: entry from each category (situation_residence / situation_work / situation_benefits)."""
    dp.register_callback_query_handler(
        handle_situation_start,
        lambda c: c.data and c.data in ("situation_residence", "situation_work", "situation_benefits"),
    )
    # CRITICAL: Exit must be registered WITH state=situation_checker_flow and BEFORE answer handler,
    # so "Вийти" is handled at any step and clears FSM, then returns to category.
    dp.register_callback_query_handler(
        handle_situation_checker_exit,
        lambda c: c.data and c.data == "situation_checker_exit",
        state=DocumentState.situation_checker_flow,
    )
    dp.register_callback_query_handler(
        handle_situation_checker_answer,
        lambda c: c.data and c.data.startswith("sc_"),
        state=DocumentState.situation_checker_flow,
    )
    logger.info("✅ UX helpers registered (situation_residence / situation_work / situation_benefits)")
