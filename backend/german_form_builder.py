# -*- coding: utf-8 -*-
"""
backend/german_form_builder.py — backward-compatibility shim.

Renamed to form_builder.py. This file re-exports everything so that any
existing code that imports from german_form_builder continues to work.
"""
from backend.form_builder import *  # noqa: F401,F403
from backend.form_builder import build_german_form, supported_doc_types  # noqa: F401
