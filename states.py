# -*- coding: utf-8 -*-
"""GERMAN_DOC_BOT v5.0 - FSM States"""

from aiogram.dispatcher.filters.state import State, StatesGroup


class DocumentState(StatesGroup):
    """Єдиний клас станів для всього бота"""
    # Мова та GDPR
    selecting_language = State()
    waiting_gdpr = State()
    
    # Анкета (WebApp не потребує FSM, але залишаємо для fallback)
    filling_form = State()
    waiting_field = State()
    
    # Оплата
    waiting_promo = State()
    waiting_payment = State()
    
    # "What do I need to do in Germany?" — free guided flow (answers in state data)
    what_to_do_flow = State()
    
    # Адмінка
    admin_broadcast = State()
    admin_promo_create = State()
    admin_set_price = State()

    # Situation Checker (decision helper) — isolated from document FSM
    situation_checker_flow = State()


class SupportStates(StatesGroup):
    """FSM states for the AI support chat."""
    waiting_for_question = State()
    # Deep-link entry: user arrives via ai_{doc_type} — chat has document context
    waiting_for_doc_question = State()
