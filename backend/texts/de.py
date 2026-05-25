# -*- coding: utf-8 -*-
"""Німецька мова - backend/texts/de.py"""

# ============================================================================
# PROJEKT-EINFÜHRUNGSTEXT
# ============================================================================

INTRO_TEXT = """Hallo! 👋

Wir helfen Ihnen, deutsche Dokumente so auszufüllen,
dass sie beim ersten Mal akzeptiert werden — ohne Rückgaben oder zusätzliche Behördengänge.

So funktioniert's:
Sie beantworten Fragen in einem Formular, und wir zeigen Ihnen ein fertiges Beispiel
eines ausgefüllten Dokuments. So sehen Sie genau, wie das Formular aussehen soll,
und können die Daten fehlerfrei in das offizielle Formular übertragen.

Wir arbeiten mit Dokumenten wie:
– Wohnsitzanmeldung (Anmeldung)
– soziale und familiäre Anträge
– finanzielle und administrative Formulare

Wichtig:
Wir reichen keine Dokumente für Sie ein und sind keine staatliche Behörde.
Wir helfen Ihnen einfach, Dokumente richtig vorzubereiten,
damit sie nicht zur Korrektur zurückgegeben werden.

Wählen Sie eine Dokumentenkategorie, um zu beginnen."""

# ============================================================================
# GDPR / ЮРИДИЧНИЙ ТЕКСТ
# ============================================================================

GDPR_TEXT = """📜 <b>Nutzungsvereinbarung</b>

Durch die Nutzung dieses Bots stimmen Sie den folgenden Bedingungen zu:

<b>1. Verarbeitung personenbezogener Daten</b>
Der Bot sammelt und verarbeitet Ihre personenbezogenen Daten (Name, Kontaktdaten, Dokumente) ausschließlich zur Bereitstellung von Dokumentenerstellungsdiensten.

<b>2. Datenspeicherung</b>
• Ihre Daten werden in einer sicheren Datenbank gespeichert
• Daten werden nur zur Generierung von Dokumenten verwendet
• Daten werden NICHT ohne Ihre Zustimmung an Dritte weitergegeben

<b>3. Ihre Rechte</b>
• Recht auf Zugriff auf Ihre Daten
• Recht auf Löschung von Daten (Befehl /delete_data)
• Recht auf Berichtigung von Daten

<b>4. Sicherheit</b>
Wir verwenden Verschlüsselung und andere Maßnahmen zum Schutz Ihrer Daten.

<b>5. Haftung</b>
Der Benutzer ist für die Richtigkeit der bereitgestellten Daten verantwortlich. Der Bot ist ein Werkzeug zur Erstellung von Dokumenten und bietet keine Rechtsberatung.

Durch Klicken auf "Bestätigen" stimmen Sie diesen Bedingungen zu."""

# ============================================================================
# TЕКСТИ МЕНЮ ТА КНОПОК
# ============================================================================

MENU_TEXTS = {
    # Вибір мови
    'language_selection': '🌍 Sprache wählen:',
    'btn_confirm': '✅ Bestätigen',
    
    # Головне меню
    'main_menu': '📋 Hauptmenü',
    'welcome': '👋 Willkommen!',
    'select_action': 'Wählen Sie eine Aktion:',
    
    # Кнопки головного меню
    'btn_documents': '📄 Dokumente',
    'btn_my_data': '👤 Meine Daten',
    'btn_orders': '📦 Meine Bestellungen',
    'btn_support': '💬 Support',
    'btn_settings': '⚙️ Einstellungen',
    
    # Документи
    'documents_menu': '📄 Dokumenttyp wählen:',
    'doc_anmeldung': '🏠 Anmeldung',
    'doc_kindergeld': '👶 Kindergeld',
    'doc_abmeldung': '📤 Abmeldung',
    
    # Навігація
    'btn_back': '◀️ Zurück',
    'btn_cancel': '❌ Abbrechen',
    
    # Замовлення
    'orders_menu': '📦 Ihre Bestellungen:',
    'no_orders': 'Sie haben noch keine Bestellungen',
    'order_status_pending': '⏳ In Bearbeitung',
    'order_status_ready': '✅ Bereit',
    'order_status_paid': '💳 Bezahlt',
    
    # Налаштування
    'settings_menu': '⚙️ Einstellungen:',
    'change_language': '🌍 Sprache ändern',
    'delete_data': '🗑️ Meine Daten löschen',
}

# ============================================================================
# СИСТЕМНІ ПОВІДОМЛЕННЯ
# ============================================================================

MESSAGE_TEXTS = {
    # Успішні операції
    'success_saved': '✅ Daten erfolgreich gespeichert',
    'success_deleted': '✅ Daten erfolgreich gelöscht',
    'success_updated': '✅ Daten erfolgreich aktualisiert',
    
    # Помилки
    'error_general': '❌ Ein Fehler ist aufgetreten. Bitte versuchen Sie es später erneut.',
    'error_invalid_data': '❌ Ungültige Daten. Bitte überprüfen Sie die eingegebenen Werte.',
    'error_not_found': '❌ Daten nicht gefunden',
    
    # Попередження
    'warning_empty_field': '⚠️ Dieses Feld darf nicht leer sein',
    'warning_invalid_format': '⚠️ Ungültiges Datenformat',
    
    # Підтвердження
    'confirm_delete': '⚠️ Sind Sie sicher? Diese Aktion ist unwiderruflich.',
    'confirm_cancel': '⚠️ Möchten Sie wirklich abbrechen?',
    
    # Очікування
    'wait_processing': '⏳ Ihre Anfrage wird bearbeitet...',
    'wait_generating': '⏳ Dokument wird generiert...',
    
    # Інше
    'feature_unavailable': '⚠️ Diese Funktion ist vorübergehend nicht verfügbar',
}

# ============================================================================
# ТЕКСТИ ДЛЯ ДОКУМЕНТІВ
# ============================================================================

DOCUMENT_TEXTS = {
    'anmeldung_name': 'Anmeldung (Wohnsitzanmeldung)',
    'anmeldung_desc': 'Formular zur Anmeldung einer neuen Adresse in Deutschland',
    'anmeldung_price': '9.99 EUR',
    
    'kindergeld_name': 'Kindergeld (Antrag auf Kindergeld)',
    'kindergeld_desc': 'Formular für die finanzielle Unterstützung für Kinder',
    'kindergeld_price': '14.99 EUR',
    
    'fill_form': '📝 Formular ausfüllen',
    'fields_required': 'Pflichtfelder sind mit einem Sternchen (*) gekennzeichnet',
    
    'order_created': '✅ Bestellung erstellt',
    'order_number': '🆔 Bestellnummer',
    'preview_ready': '✅ Vorschau bereit',
    'payment_required': '💳 Zahlung erforderlich, um das Dokument zu erhalten',
    'after_payment': 'Nach der Zahlung erhalten Sie das fertige PDF-Dokument',
    # My documents library
    'my_documents_btn': '📄 Meine Dokumente',
    'my_documents_title': '📄 <b>Meine Dokumente</b>\n\nHier können Sie bezahlte Dokumente erneut herunterladen.',
    'my_documents_empty': 'Sie haben noch keine bezahlten Dokumente.\n\nSie erscheinen hier nach der Zahlung.',
    'btn_download_again': '📥 Herunterladen',
    'back_to_menu': '◀️ Zurück zum Menü',
}

WHAT_TO_DO_TEXTS = {
    'what_to_do_btn': '🧭 Was muss ich tun?',
    'what_to_do_intro': 'Beantworten Sie ein paar Fragen — ich sage Ihnen, was in Ihrer Situation zu tun ist. Keine komplizierte Bürokratie, nur ein klarer Plan.',
    'step_of': 'Schritt %s von %s',
    'exit_flow': 'Beenden',
    'q_arrived': 'Sind Sie gerade in Deutschland angekommen?',
    'q_new_address': 'Sind Sie innerhalb Deutschlands umgezogen?',
    'q_alone_family': 'Leben Sie allein oder mit Familie?',
    'q_permanent_address': 'Haben Sie bereits eine feste Adresse?',
    'q_housing_type': 'In welcher Wohnform leben Sie?',
    'q_wohnungsgeber': 'Haben Sie eine Wohnungsgeberbestätigung?',
    'q_where_before': 'Wo haben Sie vorher gewohnt?',
    'q_when_moved': 'Wann sind Sie eingezogen?',
    'q_registered': 'Haben Sie sich schon beim Bürgeramt angemeldet?',
    'q_status': 'Was ist Ihr aktueller Status?',
    'opt_yes': 'Ja',
    'opt_no': 'Nein',
    'opt_alone': 'Allein',
    'opt_family': 'Mit Familie',
    'opt_rent': 'Miete',
    'opt_own': 'Eigentum',
    'opt_other': 'Sonstiges',
    'opt_abroad': 'Im Ausland',
    'opt_germany': 'In Deutschland',
    'opt_nowhere': 'Nirgends / erstes Mal',
    'opt_recent': 'Kürzlich (innerhalb 14 Tage)',
    'opt_long_ago': 'Schon länger',
    'opt_work': 'Arbeit',
    'opt_study': 'Studium',
    'result_must_title': '🔴 Das sollten Sie tun',
    'result_should_title': '🟡 Das empfehlen wir',
    'result_not_needed_title': '⚪ Das brauchen Sie nicht',
    'result_notes_title': '⚠️ Wichtig zu wissen',
    'result_must_register': 'Melden Sie sich innerhalb von 14 Tagen beim Bürgeramt an (Anmeldung).',
    'result_must_wohnungsgeber': 'Holen Sie sich eine Wohnungsgeberbestätigung — die brauchen Sie für die Anmeldung.',
    'result_should_health': 'Kümmern Sie sich um eine Krankenversicherung, falls noch nicht geschehen.',
    'result_should_bank': 'Eröffnen Sie ein Konto für Gehalt und Zahlungen.',
    'result_should_tax_id': 'Beantragen Sie Ihre Steuer-Identifikationsnummer (Steuer-ID).',
    'result_not_reg_again': 'Eine erneute Anmeldung ist nicht nötig — Sie sind bereits gemeldet.',
    'result_note_deadline': 'Anmeldung: am besten innerhalb von 14 Tagen nach dem Einzug.',
    'result_note_wohnungsgeber': 'Ohne Wohnungsgeberbestätigung kann die Anmeldung abgelehnt werden — bitten Sie Ihren Vermieter um das Formular.',
    'recommendation_text': 'Nach Ihren Angaben empfehlen wir: Anmeldung.',
    'recommendation_btn': 'Empfohlenes Dokument ansehen',
}

SITUATION_CHECKER_TEXTS = {
    'situation_checker_btn': '🔍 Meine Situation',
    'sc_intro': 'Beantworten Sie ein paar Ja/Nein-Fragen — ich sage Ihnen, welche Dokumente Sie brauchen (Anmeldung, Abmeldung usw.).',
    'sc_step_of': 'Frage %s von %s',
    'sc_exit': 'Beenden',
    'sc_q1': 'Sind Sie gerade in Deutschland angekommen?',
    'sc_q2': 'Sind Sie innerhalb Deutschlands umgezogen?',
    'sc_q3': 'Haben Sie sich schon beim Bürgeramt für Ihre jetzige Adresse gemeldet?',
    'sc_q4': 'Ziehen Sie von Ihrer jetzigen Adresse aus (Abmeldung)?',
    'sc_q5': 'Haben Sie eine Wohnungsgeberbestätigung?',
    'sc_q6': 'Leben Sie mit Familie im selben Haushalt?',
    'sc_yes': 'Ja',
    'sc_no': 'Nein',
    'result_title': '📋 Nach Ihren Angaben:',
    'result_anmeldung_yes': '✔ Sie brauchen eine Anmeldung',
    'result_anmeldung_no': '✖ Sie brauchen keine Anmeldung',
    'result_abmeldung_yes': '✔ Sie brauchen eine Abmeldung',
    'result_abmeldung_no': '✖ Sie brauchen keine Abmeldung',
    'result_deadline_note': '⚠ Sie haben 14 Tage nach dem Einzug zur Anmeldung',
    'cta_to_documents': '👉 Zu den Dokumenten',
    'sc_result_intro': '✅ Nach Ihrer Situation brauchen Sie:',
    'sc_section_residence': '📂 Wohnen & Anmeldung',
    'sc_section_employment': '📂 Arbeit & Beschäftigung',
    'sc_section_benefits': '📂 Leistungen & Unterstützung',
    'sc_doc_anmeldung': '• Anmeldung — Adressmeldung',
    'sc_doc_abmeldung': '• Abmeldung — Abmeldung der Adresse',
    'sc_doc_steuer_id': '• Steuer-ID — Steuer-Identifikationsnummer',
    'sc_how_to_continue': 'ℹ️ So geht es weiter:',
    'sc_step1': '1️⃣ Öffnen Sie den Bereich «Wohnen & Anmeldung» (oder einen anderen)',
    'sc_step2': '2️⃣ Wählen Sie das Dokument (z. B. Anmeldung)',
    'sc_step3': '3️⃣ Füllen Sie das Formular aus',
    'sc_what_next': '👇 Was möchten Sie tun?',
    'sc_cta_documents': '📂 Zu den Dokumenten',
    'sc_back_menu': '⬅️ Zurück',
    'sc_back_to_category': '⬅️ Zurück',
    'sc_work_intro': 'Beantworten Sie ein paar Fragen — ich empfehle passende Dokumente aus «Arbeit & Beschäftigung».',
    'sc_work_q1': 'Planen Sie zu kündigen oder Ihren Arbeitsvertrag zu beenden?',
    'sc_work_q2': 'Brauchen Sie Hilfe zur Gewerbeanmeldung?',
    'sc_work_q3': 'Suchen Sie Arbeit oder müssen Sie sich arbeitslos melden?',
    'sc_work_result_docs': '• Kündigung — Vorlage Kündigungsschreiben\n• Gewerbeanmeldung — Gewerbe anmelden\n• Arbeitslosmeldung / Arbeitslosengeld',
    'sc_benefits_intro': 'Beantworten Sie ein paar Fragen — ich empfehle passende Dokumente aus «Leistungen & Unterstützung».',
    'sc_benefits_q1': 'Haben Sie Kinder, die bei Ihnen leben?',
    'sc_benefits_q2': 'Ist Ihr Einkommen unter dem Existenzminimum?',
    'sc_benefits_q3': 'Brauchen Sie Hilfe zur Miete (Wohngeld)?',
    'sc_benefits_result_docs': '• Kindergeld / Elterngeld / Kinderzuschlag\n• Bürgergeld — Grundsicherung\n• Wohngeld',
    'menu_documents_btn': '📂 Dokumente',
    'menu_language_btn': '🌐 Sprache',
    'documents_menu_title': '📂 Dokumentenkategorie wählen:',
}

LIFE_CHECKLIST_TEXTS = {
    'life_checklist_btn': '✅ Was als Nächstes',
    'life_checklist_title': '✅ <b>Was als Nächstes</b>\n\nWichtige Schritte (kurz):',
    'lc_anmeldung': '📝 <b>Anmeldung</b> — Meldeamt (Bürgeramt).',
    'lc_steuer_id': '🆔 <b>Steuer-ID</b> — Steuer-Identifikationsnummer.',
    'lc_krankenkasse': '🏥 <b>Krankenkasse</b> — Krankenversicherung.',
    'lc_rundfunkbeitrag': '📻 <b>Rundfunkbeitrag</b> — Beitragsservice.',
    'lc_schule_kita': '🏫 <b>Schule / Kita</b> — falls Sie Kinder haben.',
    'fill_document_btn': 'Dokument ausfüllen',
    'back_to_menu': '◀️ Zurück zum Menü',
}

DEADLINES_TEXTS = {
    'deadlines_btn': '⏰ Wichtige Fristen',
    'deadlines_title': '⏰ <b>Wichtige Fristen</b>\n\nVertrauenswürdige Angaben (ohne Erinnerungen):',
    'd_anmeldung': '📝 <b>Anmeldung</b> — innerhalb von 14 Tagen nach dem Einzug.',
    'd_ummeldung': '🔄 <b>Ummeldung</b> — bei Adressänderung, am besten sofort.',
    'd_kindergeld': '👶 <b>Kindergeld</b> — Antrag bis zu 6 Monate rückwirkend möglich.',
    'back_to_menu': '◀️ Zurück zum Menü',
}

DOCUMENT_NEXT_STEPS = {
    'anmeldung': (
        '📌 <b>Was Sie als Nächstes tun sollten</b>\n\n'
        '📍 <b>Wo einreichen:</b> Bürgeramt / Einwohnermeldeamt an Ihrem Wohnort.\n\n'
        '⏰ <b>Frist:</b> Die Anmeldung muss innerhalb von <b>14 Tagen</b> nach dem Einzug erfolgen.\n\n'
        '📎 <b>Mitbringen:</b> Personalausweis oder Reisepass, Wohnungsgeberbestätigung, ausgefülltes Anmeldeformular.'
    ),
    'kindergeld': (
        '📌 <b>Was Sie als Nächstes tun sollten</b>\n\n'
        '📍 <b>Wo einreichen:</b> Familienkasse der Bundesagentur für Arbeit oder online einreichen.\n\n'
        '📎 <b>Mitbringen:</b> Ausgefüllter Antrag, Ausweisdokumente, Geburtsurkunden der Kinder, ggf. Einkommensnachweise.'
    ),
    'abmeldung': (
        '📌 <b>Was Sie als Nächstes tun sollten</b>\n\n'
        '📍 <b>Wo einreichen:</b> Bürgeramt Ihres letzten Wohnsitzes.\n\n'
        '⏰ <b>Frist:</b> Am besten vor oder kurz nach dem Auszug.\n\n'
        '📎 <b>Mitbringen:</b> Personalausweis oder Reisepass, ausgefülltes Abmeldeformular.'
    ),
}