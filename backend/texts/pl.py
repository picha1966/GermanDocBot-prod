# -*- coding: utf-8 -*-
"""Польська мова - backend/texts/pl.py"""

# ============================================================================
# TEKST WPROWADZAJĄCY PROJEKT
# ============================================================================

INTRO_TEXT = """Cześć! 👋

Pomagamy Ci wypełnić niemieckie dokumenty tak,
żeby były przyjmowane za pierwszym razem — bez zwrotów i dodatkowych wizyt w urzędzie.

Jak to działa:
Odpowiadasz na pytania w formularzu, a my pokazujemy Ci gotowy przykład
wypełnionego dokumentu. Dzięki temu widzisz dokładnie, jak powinien wyglądać formularz,
i możesz przenieść dane do oficjalnego formularza bez błędów.

Pracujemy z dokumentami takimi jak:
– rejestracja miejsca zamieszkania (Anmeldung)
– wnioski socjalne i rodzinne
– formularze finansowe i administracyjne

Ważne:
Nie składamy dokumentów w Twoim imieniu i nie jesteśmy urzędem państwowym.
Po prostu pomagamy przygotować dokumenty poprawnie,
żeby nie były zwracane do poprawy.

Wybierz kategorię dokumentów, aby rozpocząć."""

# ============================================================================
# GDPR / ЮРИДИЧНИЙ ТЕКСТ
# ============================================================================

GDPR_TEXT = """📜 <b>Umowa użytkownika</b>

Korzystając z tego bota, zgadzasz się na następujące warunki:

<b>1. Przetwarzanie danych osobowych</b>
Bot zbiera i przetwarza Twoje dane osobowe (imię, dane kontaktowe, dokumenty) wyłącznie w celu świadczenia usług związanych z przygotowaniem dokumentów.

<b>2. Przechowywanie danych</b>
• Twoje dane są przechowywane w bezpiecznej bazie danych
• Dane są wykorzystywane tylko do generowania dokumentów
• Dane NIE są udostępniane stronom trzecim bez Twojej zgody

<b>3. Twoje prawa</b>
• Prawo dostępu do swoich danych
• Prawo do usunięcia danych (polecenie /delete_data)
• Prawo do poprawiania danych

<b>4. Bezpieczeństwo</b>
Stosujemy szyfrowanie i inne środki w celu ochrony Twoich danych.

<b>5. Odpowiedzialność</b>
Użytkownik ponosi odpowiedzialność za poprawność podanych danych. Bot jest narzędziem do tworzenia dokumentów i nie świadczy porad prawnych.

Klikając "Potwierdzić", zgadzasz się na te warunki."""

# ============================================================================
# TЕКСТИ МЕНЮ ТА КНОПОК
# ============================================================================

MENU_TEXTS = {
    # Вибір мови
    'language_selection': '🌍 Wybierz język:',
    'btn_confirm': '✅ Potwierdzić',
    
    # Головне меню
    'main_menu': '📋 Menu główne',
    'welcome': '👋 Witamy!',
    'select_action': 'Wybierz akcję:',
    
    # Кнопки головного меню
    'btn_documents': '📄 Dokumenty',
    'btn_my_data': '👤 Moje dane',
    'btn_orders': '📦 Moje zamówienia',
    'btn_support': '💬 Wsparcie',
    'btn_settings': '⚙️ Ustawienia',
    
    # Документи
    'documents_menu': '📄 Wybierz typ dokumentu:',
    'doc_anmeldung': '🏠 Anmeldung (Rejestracja)',
    'doc_kindergeld': '👶 Kindergeld (Zasiłek na dzieci)',
    'doc_abmeldung': '📤 Abmeldung (Wyrejestrowanie)',
    
    # Навігація
    'btn_back': '◀️ Wstecz',
    'btn_cancel': '❌ Anuluj',
    
    # Замовлення
    'orders_menu': '📦 Twoje zamówienia:',
    'no_orders': 'Nie masz jeszcze zamówień',
    'order_status_pending': '⏳ W trakcie realizacji',
    'order_status_ready': '✅ Gotowe',
    'order_status_paid': '💳 Opłacone',
    
    # Налаштування
    'settings_menu': '⚙️ Ustawienia:',
    'change_language': '🌍 Zmień język',
    'delete_data': '🗑️ Usuń moje dane',
}

# ============================================================================
# СИСТЕМНІ ПОВІДОМЛЕННЯ
# ============================================================================

MESSAGE_TEXTS = {
    # Успішні операції
    'success_saved': '✅ Dane zapisane pomyślnie',
    'success_deleted': '✅ Dane usunięte pomyślnie',
    'success_updated': '✅ Dane zaktualizowane pomyślnie',
    
    # Помилки
    'error_general': '❌ Wystąpił błąd. Spróbuj ponownie później.',
    'error_invalid_data': '❌ Nieprawidłowe dane. Sprawdź wprowadzone wartości.',
    'error_not_found': '❌ Nie znaleziono danych',
    
    # Попередження
    'warning_empty_field': '⚠️ To pole nie może być puste',
    'warning_invalid_format': '⚠️ Nieprawidłowy format danych',
    
    # Підтвердження
    'confirm_delete': '⚠️ Czy jesteś pewien? Ta akcja jest nieodwracalna.',
    'confirm_cancel': '⚠️ Czy na pewno chcesz anulować?',
    
    # Очікування
    'wait_processing': '⏳ Przetwarzanie żądania...',
    'wait_generating': '⏳ Generowanie dokumentu...',
    
    # Інше
    'feature_unavailable': '⚠️ Ta funkcja jest tymczasowo niedostępna',
}

# ============================================================================
# ТЕКСТИ ДЛЯ ДОКУМЕНТІВ
# ============================================================================

DOCUMENT_TEXTS = {
    'anmeldung_name': 'Anmeldung (Rejestracja miejsca zamieszkania)',
    'anmeldung_desc': 'Formularz rejestracji nowego adresu w Niemczech',
    'anmeldung_price': '9.99 EUR',
    
    'kindergeld_name': 'Kindergeld (Wniosek o zasiłek na dzieci)',
    'kindergeld_desc': 'Formularz do otrzymania wsparcia finansowego na dzieci',
    'kindergeld_price': '14.99 EUR',
    
    'fill_form': '📝 Wypełnij formularz',
    'fields_required': 'Pola obowiązkowe są oznaczone gwiazdką (*)',
    
    'order_created': '✅ Zamówienie utworzone',
    'order_number': '🆔 Numer zamówienia',
    'preview_ready': '✅ Podgląd gotowy',
    'payment_required': '💳 Wymagana płatność, aby otrzymać dokument',
    'after_payment': 'Po opłaceniu otrzymasz gotowy dokument PDF',
    # My documents library
    'my_documents_btn': '📄 Moje dokumenty',
    'my_documents_title': '📄 <b>Moje dokumenty</b>\n\nTutaj możesz ponownie pobrać opłacone dokumenty.',
    'my_documents_empty': 'Nie masz jeszcze opłaconych dokumentów.\n\nPojawią się tutaj po opłaceniu.',
    'btn_download_again': '📥 Pobierz',
    'back_to_menu': '◀️ Powrót do menu',
}

WHAT_TO_DO_TEXTS = {
    'what_to_do_btn': '🧭 Co muszę zrobić?',
    'what_to_do_intro': 'Odpowiedz na kilka pytań — podpowiem, co zrobić w Twojej sytuacji. Bez skomplikowanej biurokracji, tylko jasny plan.',
    'step_of': 'Krok %s z %s',
    'exit_flow': 'Wyjdź',
    'q_arrived': 'Czy właśnie przyjechałeś/aś do Niemiec?',
    'q_new_address': 'Czy przeprowadziłeś/aś się na nowy adres w Niemczech?',
    'q_alone_family': 'Czy mieszkasz sam/sama, czy z rodziną?',
    'q_permanent_address': 'Czy masz już stały adres?',
    'q_housing_type': 'W jakim typie mieszkania mieszkasz?',
    'q_wohnungsgeber': 'Czy masz potwierdzenie od wynajmującego (Wohnungsgeberbestätigung)?',
    'q_where_before': 'Gdzie wcześniej mieszkałeś/aś?',
    'q_when_moved': 'Kiedy się wprowadziłeś/aś?',
    'q_registered': 'Czy zarejestrowałeś/aś się już w Bürgeramt?',
    'q_status': 'Jaki jest Twój obecny status?',
    'opt_yes': 'Tak',
    'opt_no': 'Nie',
    'opt_alone': 'Sam/sama',
    'opt_family': 'Z rodziną',
    'opt_rent': 'Wynajem',
    'opt_own': 'Własność',
    'opt_other': 'Inne',
    'opt_abroad': 'Za granicą',
    'opt_germany': 'W Niemczech',
    'opt_nowhere': 'Nigdzie / pierwszy raz',
    'opt_recent': 'Niedawno (w ciągu 14 dni)',
    'opt_long_ago': 'Dawno temu',
    'opt_work': 'Praca',
    'opt_study': 'Nauka',
    'result_must_title': '🔴 To warto zrobić',
    'result_should_title': '🟡 To polecamy',
    'result_not_needed_title': '⚪ Tego nie musisz robić',
    'result_notes_title': '⚠️ Warto wiedzieć',
    'result_must_register': 'Zarejestruj adres (Anmeldung) w Bürgeramt w ciągu 14 dni.',
    'result_must_wohnungsgeber': 'Zdobądź potwierdzenie od wynajmującego (Wohnungsgeberbestätigung) — potrzebne do rejestracji.',
    'result_should_health': 'Załóż ubezpieczenie zdrowotne, jeśli go nie masz.',
    'result_should_bank': 'Otwórz konto bankowe do wypłat i płatności.',
    'result_should_tax_id': 'Uzyskaj numer identyfikacji podatkowej (Steuer-ID).',
    'result_not_reg_again': 'Nie musisz rejestrować się ponownie — jesteś już zarejestrowany/a.',
    'result_note_deadline': 'Rejestracja: najlepiej w ciągu 14 dni od wprowadzki.',
    'result_note_wohnungsgeber': 'Bez potwierdzenia wynajmującego rejestracja może być odrzucona — poproś o wypełnienie formularza.',
    'recommendation_text': 'Na podstawie Twoich odpowiedzi polecamy: Anmeldung.',
    'recommendation_btn': 'Zobacz polecany dokument',
}

SITUATION_CHECKER_TEXTS = {
    'situation_checker_btn': '🔍 Moja sytuacja',
    'sc_intro': 'Odpowiedz na kilka pytań Tak/Nie — podpowiem, jakie dokumenty są Ci potrzebne (Anmeldung, Abmeldung itd.).',
    'sc_step_of': 'Pytanie %s z %s',
    'sc_exit': 'Wyjdź',
    'sc_q1': 'Czy właśnie przyjechałeś/aś do Niemiec?',
    'sc_q2': 'Czy przeprowadziłeś/aś się na nowy adres w Niemczech?',
    'sc_q3': 'Czy zarejestrowałeś/aś się już w Bürgeramt pod obecnym adresem?',
    'sc_q4': 'Czy wyprowadzasz się z obecnego adresu (wyrejestrowanie)?',
    'sc_q5': 'Czy masz potwierdzenie od wynajmującego (Wohnungsgeberbestätigung)?',
    'sc_q6': 'Czy mieszkasz z rodziną w jednym gospodarstwie?',
    'sc_yes': 'Tak',
    'sc_no': 'Nie',
    'result_title': '📋 Na podstawie Twoich odpowiedzi:',
    'result_anmeldung_yes': '✔ Potrzebujesz Anmeldung',
    'result_anmeldung_no': '✖ Nie potrzebujesz Anmeldung',
    'result_abmeldung_yes': '✔ Potrzebujesz Abmeldung',
    'result_abmeldung_no': '✖ Nie potrzebujesz Abmeldung',
    'result_deadline_note': '⚠ Masz 14 dni od wprowadzki na rejestrację',
    'cta_to_documents': '👉 Przejdź do dokumentów',
    'sc_result_intro': '✅ Na podstawie Twojej sytuacji potrzebujesz:',
    'sc_section_residence': '📂 Mieszkanie i rejestracja',
    'sc_section_employment': '📂 Praca i zatrudnienie',
    'sc_section_benefits': '📂 Świadczenia i wsparcie',
    'sc_doc_anmeldung': '• Anmeldung — rejestracja adresu',
    'sc_doc_abmeldung': '• Abmeldung — wyrejestrowanie adresu',
    'sc_doc_steuer_id': '• Steuer-ID — numer identyfikacji podatkowej',
    'sc_how_to_continue': 'ℹ️ Jak kontynuować:',
    'sc_step1': '1️⃣ Otwórz sekcję «Mieszkanie i rejestracja» (lub inną)',
    'sc_step2': '2️⃣ Wybierz dokument (np. Anmeldung)',
    'sc_step3': '3️⃣ Wypełnij formularz',
    'sc_what_next': '👇 Co chcesz zrobić?',
    'sc_cta_documents': '📂 Przejdź do dokumentów',
    'sc_back_menu': '⬅️ Wstecz',
    'sc_back_to_category': '⬅️ Wstecz',
    'sc_work_intro': 'Odpowiedz na kilka pytań — podpowiem, jakie dokumenty z «Praca i zatrudnienie» są dla Ciebie.',
    'sc_work_q1': 'Planujesz rozwiązać umowę o pracę?',
    'sc_work_q2': 'Potrzebujesz pomocy z rejestracją działalności (Gewerbeanmeldung)?',
    'sc_work_q3': 'Szukasz pracy lub rejestracja jako bezrobotny?',
    'sc_work_result_docs': '• Kündigung — wzór wypowiedzenia\n• Gewerbeanmeldung — rejestracja działalności\n• Arbeitslosmeldung / Arbeitslosengeld',
    'sc_benefits_intro': 'Odpowiedz na kilka pytań — podpowiem, jakie dokumenty z «Świadczenia i wsparcie» są dla Ciebie.',
    'sc_benefits_q1': 'Masz dzieci mieszkające z Tobą?',
    'sc_benefits_q2': 'Twój dochód jest poniżej minimum?',
    'sc_benefits_q3': 'Potrzebujesz pomocy z czynszem (Wohngeld)?',
    'sc_benefits_result_docs': '• Kindergeld / Elterngeld / Kinderzuschlag\n• Bürgergeld — podstawowe wsparcie\n• Wohngeld',
    'menu_documents_btn': '📂 Dokumenty',
    'menu_language_btn': '🌐 Język',
    'documents_menu_title': '📂 Wybierz kategorię dokumentów:',
}

LIFE_CHECKLIST_TEXTS = {
    'life_checklist_btn': '✅ Co dalej',
    'life_checklist_title': '✅ <b>Co dalej</b>\n\nKluczowe kroki (krótko):',
    'lc_anmeldung': '📝 <b>Anmeldung</b> — rejestracja adresu w Bürgeramt.',
    'lc_steuer_id': '🆔 <b>Steuer-ID</b> — numer identyfikacji podatkowej.',
    'lc_krankenkasse': '🏥 <b>Krankenkasse</b> — ubezpieczenie zdrowotne.',
    'lc_rundfunkbeitrag': '📻 <b>Rundfunkbeitrag</b> — opłata radiowo-telewizyjna.',
    'lc_schule_kita': '🏫 <b>Szkoła / Kita</b> — jeśli masz dzieci.',
    'fill_document_btn': 'Wypełnij dokument',
    'back_to_menu': '◀️ Powrót do menu',
}

DEADLINES_TEXTS = {
    'deadlines_btn': '⏰ Ważne terminy',
    'deadlines_title': '⏰ <b>Ważne terminy</b>\n\nSprawdzone informacje (bez przypomnień):',
    'd_anmeldung': '📝 <b>Anmeldung</b> — w ciągu 14 dni od zamieszkania.',
    'd_ummeldung': '🔄 <b>Ummeldung</b> — przy zmianie adresu, najlepiej od razu.',
    'd_kindergeld': '👶 <b>Kindergeld</b> — wniosek do 6 miesięcy wstecz.',
    'back_to_menu': '◀️ Powrót do menu',
}

DOCUMENT_NEXT_STEPS = {
    'anmeldung': (
        '📌 <b>Co dalej</b>\n\n'
        '📍 <b>Gdzie złożyć:</b> Urząd meldunkowy (Bürgeramt / Einwohnermeldeamt) w miejscu zamieszkania.\n\n'
        '⏰ <b>Termin:</b> Meldunek należy złożyć w ciągu <b>14 dni</b> od zamieszkania.\n\n'
        '📎 <b>Co zabrać:</b> Dowód osobisty lub paszport, potwierdzenie od wynajmującego (Wohnungsgeberbestätigung), wypełniony formularz Anmeldung.'
    ),
    'kindergeld': (
        '📌 <b>Co dalej</b>\n\n'
        '📍 <b>Gdzie złożyć:</b> Kasa rodzinna (Familienkasse) przy Federalnej Agencji Pracy lub online.\n\n'
        '📎 <b>Co zabrać:</b> Wypełniony wniosek, dowód tożsamości, akty urodzenia dzieci, ewentualnie zaświadczenie o dochodach.'
    ),
    'abmeldung': (
        '📌 <b>Co dalej</b>\n\n'
        '📍 <b>Gdzie złożyć:</b> Urząd meldunkowy ostatniego miejsca zamieszkania.\n\n'
        '⏰ <b>Termin:</b> Najlepiej przed lub wkrótce po wyprowadzce.\n\n'
        '📎 <b>Co zabrać:</b> Dowód osobisty lub paszport, wypełniony formularz Abmeldung.'
    ),
}