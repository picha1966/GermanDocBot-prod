# -*- coding: utf-8 -*-
"""Англійська мова - backend/texts/en.py"""

# ============================================================================
# PROJECT INTRODUCTION TEXT
# ============================================================================

INTRO_TEXT = """Hello! 👋

We help you fill out German documents so they're accepted
the first time — without returns or extra trips to the office.

How it works:
You answer questions in a form, and we show you a ready example
of a completed document. This way you see exactly how the form should look
and can transfer the data to the official form without mistakes.

We work with documents like:
– residence registration (Anmeldung)
– social and family applications
– financial and administrative forms

Important:
We don't submit documents for you and we're not a government agency.
We simply help you prepare documents correctly
so they won't be returned for corrections.

Select a document category to get started."""

# ============================================================================
# GDPR / ЮРИДИЧНИЙ ТЕКСТ
# ============================================================================

GDPR_TEXT = """📜 <b>User Agreement</b>

By using this bot, you agree to the following terms:

<b>1. Personal Data Processing</b>
The bot collects and processes your personal data (name, contact details, documents) exclusively to provide document preparation services.

<b>2. Data Storage</b>
• Your data is stored in a secure database
• Data is used only for document generation
• Data is NOT shared with third parties without your consent

<b>3. Your Rights</b>
• Right to access your data
• Right to delete data (command /delete_data)
• Right to correct data

<b>4. Security</b>
We use encryption and other measures to protect your data.

<b>5. Liability</b>
The user is responsible for the accuracy of the provided data. The bot is a tool for creating documents and does not provide legal advice.

By clicking "Confirm", you agree to these terms."""

# ============================================================================
# TЕКСТИ МЕНЮ ТА КНОПОК
# ============================================================================

MENU_TEXTS = {
    # Вибір мови
    'language_selection': '🌍 Choose language:',
    'btn_confirm': '✅ Confirm',
    
    # Головне меню
    'main_menu': '📋 Main Menu',
    'welcome': '👋 Welcome!',
    'select_action': 'Select an action:',
    
    # Кнопки головного меню
    'btn_documents': '📄 Documents',
    'btn_my_data': '👤 My Data',
    'btn_orders': '📦 My Orders',
    'btn_support': '💬 Support',
    'btn_settings': '⚙️ Settings',
    
    # Документи
    'documents_menu': '📄 Select document type:',
    'doc_anmeldung': '🏠 Anmeldung (Registration)',
    'doc_kindergeld': '👶 Kindergeld (Child Benefit)',
    'doc_abmeldung': '📤 Abmeldung (Deregistration)',
    
    # Навігація
    'btn_back': '◀️ Back',
    'btn_cancel': '❌ Cancel',
    
    # Замовлення
    'orders_menu': '📦 Your orders:',
    'no_orders': 'You have no orders yet',
    'order_status_pending': '⏳ Processing',
    'order_status_ready': '✅ Ready',
    'order_status_paid': '💳 Paid',
    
    # Налаштування
    'settings_menu': '⚙️ Settings:',
    'change_language': '🌍 Change Language',
    'delete_data': '🗑️ Delete My Data',
}

# ============================================================================
# СИСТЕМНІ ПОВІДОМЛЕННЯ
# ============================================================================

MESSAGE_TEXTS = {
    # Успішні операції
    'success_saved': '✅ Data saved successfully',
    'success_deleted': '✅ Data deleted successfully',
    'success_updated': '✅ Data updated successfully',
    
    # Помилки
    'error_general': '❌ An error occurred. Please try again later.',
    'error_invalid_data': '❌ Invalid data. Please check entered values.',
    'error_not_found': '❌ Data not found',
    
    # Попередження
    'warning_empty_field': '⚠️ This field cannot be empty',
    'warning_invalid_format': '⚠️ Invalid data format',
    
    # Підтвердження
    'confirm_delete': '⚠️ Are you sure? This action is irreversible.',
    'confirm_cancel': '⚠️ Are you sure you want to cancel?',
    
    # Очікування
    'wait_processing': '⏳ Processing your request...',
    'wait_generating': '⏳ Generating document...',
    
    # Інше
    'feature_unavailable': '⚠️ This feature is temporarily unavailable',
}

# ============================================================================
# ТЕКСТИ ДЛЯ ДОКУМЕНТІВ
# ============================================================================

DOCUMENT_TEXTS = {
    'anmeldung_name': 'Anmeldung (Address Registration)',
    'anmeldung_desc': 'Form for registering a new address in Germany',
    'anmeldung_price': '9.99 EUR',
    
    'kindergeld_name': 'Kindergeld (Child Benefit Application)',
    'kindergeld_desc': 'Form for receiving financial support for children',
    'kindergeld_price': '14.99 EUR',
    
    'fill_form': '📝 Fill Form',
    'fields_required': 'Required fields are marked with an asterisk (*)',
    
    'order_created': '✅ Order created',
    'order_number': '🆔 Order number',
    'preview_ready': '✅ Preview ready',
    'payment_required': '💳 Payment required to receive the document',
    'after_payment': 'After payment you will receive the completed PDF document',
    # My documents library
    'my_documents_btn': '📄 My documents',
    'my_documents_title': '📄 <b>My documents</b>\n\nRe-download your paid documents here.',
    'my_documents_empty': 'You have no paid documents yet.\n\nThey will appear here after payment.',
    'btn_download_again': '📥 Download',
    'back_to_menu': '◀️ Back to menu',
}

WHAT_TO_DO_TEXTS = {
    'what_to_do_btn': '🧭 What do I need to do?',
    'what_to_do_intro': 'Answer a few questions — I\'ll suggest what to do based on your situation. No complicated bureaucracy, just a clear plan.',
    'step_of': 'Step %s of %s',
    'exit_flow': 'Exit',
    'q_arrived': 'Did you just arrive in Germany?',
    'q_new_address': 'Did you move to a new address within Germany?',
    'q_alone_family': 'Do you live alone or with family?',
    'q_permanent_address': 'Do you already have a permanent address?',
    'q_housing_type': 'What type of housing do you live in?',
    'q_wohnungsgeber': 'Do you have a landlord confirmation (Wohnungsgeberbestätigung)?',
    'q_where_before': 'Where did you live before?',
    'q_when_moved': 'When did you move in?',
    'q_registered': 'Have you already registered at the Bürgeramt?',
    'q_status': 'What is your current status?',
    'opt_yes': 'Yes',
    'opt_no': 'No',
    'opt_alone': 'Alone',
    'opt_family': 'With family',
    'opt_rent': 'Renting',
    'opt_own': 'Own',
    'opt_other': 'Other',
    'opt_abroad': 'Abroad',
    'opt_germany': 'In Germany',
    'opt_nowhere': 'Nowhere / first time',
    'opt_recent': 'Recently (within 14 days)',
    'opt_long_ago': 'A while ago',
    'opt_work': 'Work',
    'opt_study': 'Study',
    'result_must_title': '🔴 You should do this',
    'result_should_title': '🟡 We recommend doing this',
    'result_not_needed_title': '⚪ You do not need to do this',
    'result_notes_title': '⚠️ Good to know',
    'result_must_register': 'Register your address (Anmeldung) at the Bürgeramt within 14 days.',
    'result_must_wohnungsgeber': 'Get a landlord confirmation (Wohnungsgeberbestätigung) — you need it for registration.',
    'result_should_health': 'Get health insurance if you don\'t have it yet.',
    'result_should_bank': 'Open a bank account for salary and payments.',
    'result_should_tax_id': 'Get your tax identification number (Steuer-ID).',
    'result_not_reg_again': 'You don\'t need to register again — you\'re already registered.',
    'result_note_deadline': 'Address registration: try to do it within 14 days of moving in.',
    'result_note_wohnungsgeber': 'Without landlord confirmation, registration may be refused — ask your landlord to fill the form.',
    'recommendation_text': 'Based on your answers, we recommend preparing: Anmeldung.',
    'recommendation_btn': 'View recommended document',
}

SITUATION_CHECKER_TEXTS = {
    'situation_checker_btn': '🔍 My situation',
    'sc_intro': 'Answer a few Yes/No questions — I\'ll tell you which documents you need (Anmeldung, Abmeldung, etc.).',
    'sc_step_of': 'Question %s of %s',
    'sc_exit': 'Exit',
    'sc_q1': 'Did you just arrive in Germany?',
    'sc_q2': 'Did you move to a new address within Germany?',
    'sc_q3': 'Have you already registered at the Bürgeramt for your current address?',
    'sc_q4': 'Are you moving out of your current address (deregistering)?',
    'sc_q5': 'Do you have a landlord confirmation (Wohnungsgeberbestätigung)?',
    'sc_q6': 'Do you live with family in the same household?',
    'sc_yes': 'Yes',
    'sc_no': 'No',
    'result_title': '📋 Based on your answers:',
    'result_anmeldung_yes': '✔ You need Anmeldung',
    'result_anmeldung_no': '✖ You do not need Anmeldung',
    'result_abmeldung_yes': '✔ You need Abmeldung',
    'result_abmeldung_no': '✖ You do not need Abmeldung',
    'result_deadline_note': '⚠ You have 14 days after moving in to register',
    'cta_to_documents': '👉 Go to documents',
    'sc_result_intro': '✅ Based on your situation you need:',
    'sc_section_residence': '📂 Living & Registration',
    'sc_section_employment': '📂 Work & Employment',
    'sc_section_benefits': '📂 Benefits & Support',
    'sc_doc_anmeldung': '• Anmeldung — address registration',
    'sc_doc_abmeldung': '• Abmeldung — address deregistration',
    'sc_doc_steuer_id': '• Steuer-ID — tax identification number',
    'sc_how_to_continue': 'ℹ️ How to continue:',
    'sc_step1': '1️⃣ Open the section «Living & Registration» (or another as needed)',
    'sc_step2': '2️⃣ Choose the document (e.g. Anmeldung)',
    'sc_step3': '3️⃣ Fill in the form',
    'sc_what_next': '👇 What would you like to do?',
    'sc_cta_documents': '📂 Go to documents',
    'sc_back_menu': '⬅️ Back',
    'sc_back_to_category': '⬅️ Back',
    'sc_work_intro': 'Answer a few questions — I\'ll suggest which documents from «Work & Employment» you need.',
    'sc_work_q1': 'Are you planning to resign or terminate your employment contract?',
    'sc_work_q2': 'Do you need help registering a business (Gewerbeanmeldung)?',
    'sc_work_q3': 'Are you job-seeking or need to register as unemployed?',
    'sc_work_result_docs': '• Kündigung — letter template to terminate contract\n• Gewerbeanmeldung — business registration\n• Arbeitslosmeldung / Arbeitslosengeld — unemployment',
    'sc_benefits_intro': 'Answer a few questions — I\'ll suggest which documents from «Benefits & Support» you need.',
    'sc_benefits_q1': 'Do you have children living with you?',
    'sc_benefits_q2': 'Is your income below the minimum (need support)?',
    'sc_benefits_q3': 'Do you need help with rent (Wohngeld)?',
    'sc_benefits_result_docs': '• Kindergeld / Elterngeld / Kinderzuschlag — child benefits\n• Bürgergeld — basic support\n• Wohngeld — housing benefit',
    'menu_documents_btn': '📂 Documents',
    'menu_language_btn': '🌐 Language',
    'documents_menu_title': '📂 Choose document category:',
}

LIFE_CHECKLIST_TEXTS = {
    'life_checklist_btn': '✅ What to do next',
    'life_checklist_title': '✅ <b>What to do next</b>\n\nKey steps (short):',
    'lc_anmeldung': '📝 <b>Anmeldung</b> — register your address at the Bürgeramt.',
    'lc_steuer_id': '🆔 <b>Steuer-ID</b> — tax identification number.',
    'lc_krankenkasse': '🏥 <b>Krankenkasse</b> — health insurance.',
    'lc_rundfunkbeitrag': '📻 <b>Rundfunkbeitrag</b> — broadcasting contribution.',
    'lc_schule_kita': '🏫 <b>School / Kita</b> — if you have children.',
    'fill_document_btn': 'Fill in document',
    'back_to_menu': '◀️ Back to menu',
}

DEADLINES_TEXTS = {
    'deadlines_btn': '⏰ Important deadlines',
    'deadlines_title': '⏰ <b>Important deadlines</b>\n\nTrusted information (no reminders):',
    'd_anmeldung': '📝 <b>Anmeldung</b> — within 14 days of moving in.',
    'd_ummeldung': '🔄 <b>Ummeldung</b> — when changing address, ideally right away.',
    'd_kindergeld': '👶 <b>Kindergeld</b> — application can be backdated up to 6 months.',
    'back_to_menu': '◀️ Back to menu',
}

DOCUMENT_NEXT_STEPS = {
    'anmeldung': (
        '📌 <b>What to do next</b>\n\n'
        '📍 <b>Where to submit:</b> Local registration office (Bürgeramt / Einwohnermeldeamt) at your place of residence.\n\n'
        '⏰ <b>Deadline:</b> You must register within <b>14 days</b> of moving in.\n\n'
        '📎 <b>What to bring:</b> ID or passport, landlord confirmation (Wohnungsgeberbestätigung), completed Anmeldung form.'
    ),
    'kindergeld': (
        '📌 <b>What to do next</b>\n\n'
        '📍 <b>Where to submit:</b> Familienkasse (family fund) of the Federal Employment Agency, or submit online.\n\n'
        '📎 <b>What to bring:</b> Completed application, ID, children\'s birth certificates, income details if required.'
    ),
    'abmeldung': (
        '📌 <b>What to do next</b>\n\n'
        '📍 <b>Where to submit:</b> Registration office (Bürgeramt) of your last registered address.\n\n'
        '⏰ <b>Deadline:</b> Ideally before or shortly after moving out.\n\n'
        '📎 <b>What to bring:</b> ID or passport, completed Abmeldung form.'
    ),
}