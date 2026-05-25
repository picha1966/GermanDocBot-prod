# -*- coding: utf-8 -*-
"""
Configurable "What do I need to do in Germany?" flow.
Questions and result rules — no hardcoded user-facing text (all via i18n keys).
"""

from typing import Dict, Any, List, Optional

# Question order and option values. All display text comes from WHAT_TO_DO_TEXTS[lang].
QUESTIONS: List[Dict[str, Any]] = [
    {"id": "q1", "key": "q_arrived", "options": [{"value": "yes", "key": "opt_yes"}, {"value": "no", "key": "opt_no"}]},
    {"id": "q2", "key": "q_new_address", "options": [{"value": "yes", "key": "opt_yes"}, {"value": "no", "key": "opt_no"}]},
    {"id": "q3", "key": "q_alone_family", "options": [{"value": "alone", "key": "opt_alone"}, {"value": "family", "key": "opt_family"}]},
    {"id": "q4", "key": "q_permanent_address", "options": [{"value": "yes", "key": "opt_yes"}, {"value": "no", "key": "opt_no"}]},
    {"id": "q5", "key": "q_housing_type", "options": [{"value": "rent", "key": "opt_rent"}, {"value": "own", "key": "opt_own"}, {"value": "other", "key": "opt_other"}]},
    {"id": "q6", "key": "q_wohnungsgeber", "options": [{"value": "yes", "key": "opt_yes"}, {"value": "no", "key": "opt_no"}]},
    {"id": "q7", "key": "q_where_before", "options": [{"value": "abroad", "key": "opt_abroad"}, {"value": "germany", "key": "opt_germany"}, {"value": "nowhere", "key": "opt_nowhere"}]},
    {"id": "q8", "key": "q_when_moved", "options": [{"value": "recent", "key": "opt_recent"}, {"value": "long_ago", "key": "opt_long_ago"}]},
    {"id": "q9", "key": "q_registered", "options": [{"value": "yes", "key": "opt_yes"}, {"value": "no", "key": "opt_no"}]},
    {"id": "q10", "key": "q_status", "options": [{"value": "work", "key": "opt_work"}, {"value": "study", "key": "opt_study"}, {"value": "other", "key": "opt_other"}]},
]

# Result item ids per section. Condition = which answers show this item (rule-based).
# Section: must, should, not_needed, notes.
# Each item has: "id" (i18n key suffix), "condition" = lambda answers: bool.
def _result_condition_must_register(answers: Dict[str, str]) -> bool:
    arrived = answers.get("q_arrived") == "yes"
    new_addr = answers.get("q_new_address") == "yes"
    registered = answers.get("q_registered") == "yes"
    return (arrived or new_addr) and not registered

def _result_condition_wohnungsgeber(answers: Dict[str, str]) -> bool:
    return answers.get("q_wohnungsgeber") == "no" and answers.get("q_housing_type") == "rent"

def _result_condition_health_insurance(answers: Dict[str, str]) -> bool:
    return answers.get("q_arrived") == "yes" or answers.get("q_status") in ("work", "study")

def _result_condition_bank(answers: Dict[str, str]) -> bool:
    return answers.get("q_status") == "work"

def _result_condition_tax_id(answers: Dict[str, str]) -> bool:
    return answers.get("q_status") == "work"

def _result_condition_not_needed_reg(answers: Dict[str, str]) -> bool:
    return answers.get("q_registered") == "yes" and answers.get("q_new_address") != "yes"

def _result_condition_note_deadline(answers: Dict[str, str]) -> bool:
    return answers.get("q_arrived") == "yes" or answers.get("q_new_address") == "yes"

def _result_condition_note_wohnungsgeber(answers: Dict[str, str]) -> bool:
    return answers.get("q_housing_type") == "rent"

RESULT_RULES: List[Dict[str, Any]] = [
    {"id": "must_register", "section": "must", "condition": _result_condition_must_register},
    {"id": "must_wohnungsgeber", "section": "must", "condition": _result_condition_wohnungsgeber},
    {"id": "should_health", "section": "should", "condition": _result_condition_health_insurance},
    {"id": "should_bank", "section": "should", "condition": _result_condition_bank},
    {"id": "should_tax_id", "section": "should", "condition": _result_condition_tax_id},
    {"id": "not_reg_again", "section": "not_needed", "condition": _result_condition_not_needed_reg},
    {"id": "note_deadline", "section": "notes", "condition": _result_condition_note_deadline},
    {"id": "note_wohnungsgeber", "section": "notes", "condition": _result_condition_note_wohnungsgeber},
]

def get_result_items(answers: Dict[str, str]) -> Dict[str, List[str]]:
    """Returns {"must": [id, ...], "should": [...], "not_needed": [...], "notes": [...]}."""
    out: Dict[str, List[str]] = {"must": [], "should": [], "not_needed": [], "notes": []}
    for rule in RESULT_RULES:
        if rule["condition"](answers):
            out[rule["section"]].append(rule["id"])
    return out

def get_recommended_document(answers: Dict[str, str]) -> Optional[str]:
    """If we should suggest a document (e.g. Anmeldung), return its doc_type; else None."""
    if answers.get("q_registered") == "yes":
        return None
    if answers.get("q_arrived") == "yes" or answers.get("q_new_address") == "yes":
        return "anmeldung"
    return None
