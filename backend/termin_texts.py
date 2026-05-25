"""
Localization texts for Termin Assistant Bot
Languages: DE, EN, UA, PL, TR, AR (NO Russian, NO Romanian)
"""

LANGUAGES = {
    'de': {'name': 'German', 'native': 'Deutsch', 'flag': '🇩🇪'},
    'en': {'name': 'English', 'native': 'English', 'flag': '🇬🇧'},
    'ua': {'name': 'Ukrainian', 'native': 'Українська', 'flag': '🇺🇦'},
    'pl': {'name': 'Polish', 'native': 'Polski', 'flag': '🇵🇱'},
    'tr': {'name': 'Turkish', 'native': 'Türkçe', 'flag': '🇹🇷'},
    'ar': {'name': 'Arabic', 'native': 'العربية', 'flag': '🇸🇦'},
}

TEXTS = {
    'en': {
        # Welcome & Global
        'welcome': '''👋 <b>Welcome!</b>

This bot offers two services:
• 📄 German Document Generator
• 📅 Termin Assistant

Please select your language:''',
        
        'select_language': '🌍 Select your language:',
        'language_changed': '✅ Language changed!',
        
        # Main Menu
        'main_menu': '''📋 <b>Main Menu</b>

Choose a service to get started:''',
        
        'menu_document': '📄 Document Generator',
        'menu_termin': '📅 Termin Assistant',
        
        # Product Selection
        'select_product': '''📋 <b>Choose a Service</b>

What would you like to do?''',
        
        'product_document': '📄 Generate German Document',
        'product_termin': '📅 Termin Assistant',
        
        # Buttons
        'btn_back': '← Back',
        'btn_back_products': '← Back to Services',
        'btn_main_menu': '🏠 Main Menu',
        'btn_help': '❓ Help',
        'btn_change_language': '🌍 Change Language',
        'btn_pay_now': '💳 Pay Now',
        'btn_verify_payment': '✅ Verify Payment',
        'btn_open_booking': '🔗 Open Appointment Page',
        'switch_to_termin_btn': '📅 Switch to Termin Assistant',
        'switch_to_document_btn': '📄 Switch to Document Generator',
        
        # Errors
        'error': '❌ An error occurred. Please try /start again.',
        'payment_pending': '⏳ Payment not confirmed yet. Please complete payment.',
        
        # Help
        'help': '''❓ <b>Help</b>

<b>Available Services:</b>

📄 <b>Document Generator</b>
Generate German documents (Kündigung, Vollmacht, etc.)

📅 <b>Termin Assistant</b>
Get help with appointments at German authorities.

<b>Commands:</b>
/start - Start the bot
/menu - Main menu
/help - This help

<b>Disclaimer:</b>
We do NOT book appointments or bypass any systems. We only provide guidance and official links.''',

        # ==================== DOCUMENT TEXTS ====================
        'doc_menu': '''📄 <b>Document Generator</b>

Generate German documents quickly and easily.''',
        
        'doc_new_document': '📝 New Document',
        'doc_my_documents': '📁 My Documents',
        'doc_select_type': '''📄 <b>Select Document Type</b>

Choose the type of document you need:''',
        
        'doc_type_selected': '''📄 <b>{name}</b>

Required fields:
{fields}

Ready to create your document?''',
        
        'doc_start_form': '✏️ Start Form',
        'doc_form_placeholder': '''✏️ <b>Form</b>

[Form implementation placeholder]

In the full version, you would fill out each field step by step.

Click Preview to continue.''',
        
        'doc_preview': '👁️ Preview',
        'doc_preview_text': '''👁️ <b>Document Preview</b>

[Preview placeholder]

To generate the final PDF, a one-time payment of €{price} is required.''',
        
        'doc_pay_generate': '💳 Pay €{price} & Generate',
        'doc_payment_link': '''💳 <b>Payment</b>

Click the button below to pay €{price}.

After payment, click "Verify Payment".''',
        
        'doc_payment_success': '''✅ <b>Payment Successful!</b>

Your document is being generated. You will receive it shortly.''',

        'doc_payment_success_detailed': '''✅ <b>Payment Successful!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>What you paid for:</b>
📄 {document_name} - Document Generation

<b>What is now activated:</b>
✓ Your document is being generated
✓ You will receive the PDF file shortly

<b>What happens next:</b>
1. We generate your document (1-2 minutes)
2. You receive the PDF directly in this chat
3. Download and use your document

<b>Note:</b>
This is a one-time purchase for this document.
━━━━━━━━━━━━━━━━━━━━━━

Need another document? Use the menu below.''',
        
        'doc_no_documents': '📁 You have no documents yet. Create a new one!',

        # ==================== TERMIN TEXTS ====================
        'termin_menu': '''📅 <b>Appointment Assistant</b>

ℹ️ <b>Important:</b>
We do NOT book appointments for you.
We help you find available slots and notify you when they appear.

🔔 When a slot becomes available — you receive a notification.
🔗 You always book the appointment yourself via the official website.''',
        
        'termin_select_city': '📍 Select City & Authority',
        'termin_manage_reminders': '🔔 Manage Notifications',
        'termin_activate_reminders': '🔔 Activate Notifications',
        
        'termin_select_city_prompt': '''📍 <b>Select City</b>

Choose your city:''',
        
        'termin_select_authority_prompt': '''🏛️ <b>Select Authority</b>

What type of appointment do you need?''',
        
        'termin_authority_info': '''🏛️ <b>{name}</b>

{description}

🔗 <b>Official Appointment Link:</b>
{url}''',
        
        'termin_disclaimer': '''⚠️ <b>Disclaimer:</b>
We do NOT book appointments or bypass anti-bot systems.
You must book manually on the official website.''',

        'termin_upsell_explainer': '''💡 <b>How can we help?</b>
Available slots appear and disappear quickly.
We will notify you when new slots are available so you don't miss them.
You always book the appointment yourself via the official website.
We provide you with the direct official appointment link.''',
        'termin_pay_cta': '💳 Enable notifications (€{price})',
        
        'termin_view_guidance': '📚 View Full Guidance (Free)',
        'termin_set_reminder': '🔔 Notifications active',
        'termin_pay_reminders': '🔔 Notify me when slots appear (€{price})',
        
        # Guidance labels
        'guidance_steps': 'How to Book',
        'guidance_documents': 'Required Documents',
        'guidance_mistakes': 'Common Mistakes',
        'guidance_timing': 'When to Check',
        'guidance_tips': 'Tips',
        'official_link': 'Official Link',
        
        # Reminders
        'termin_select_interval': '''⏰ <b>Select Reminder Interval</b>

How often should I remind you?''',
        
        'interval_6h': 'Every 6 hours',
        'interval_12h': 'Every 12 hours',
        
        'termin_reminder_activated': '''✅ <b>Reminders Activated!</b>

I will remind you every {interval} hours to check for appointments at {authority}.

Each reminder includes the official appointment link.''',
        
        'termin_reminder_message': '''🔔 <b>Time to check for appointments!</b>

📍 {city} → {authority}

Click below to open the official appointment page.

🔗 {url}

<i>This is a reminder only. We do NOT check slots.</i>''',
        
        'termin_pause_reminders': '⏸️ Pause Reminders',
        'termin_change_interval': '⏱️ Change Interval',
        'termin_reminder_paused': '⏸️ Reminders paused. You can reactivate anytime.',
        
        'termin_reminder_status': '''🔔 <b>Your Reminders</b>

📍 City: {city}
🏛️ Authority: {authority}
⏰ Interval: Every {interval} hours
✅ Status: Active''',
        
        'termin_select_city_first': 'Please select a city and authority first.',
        'termin_need_pay': 'Notifications require a one-time payment of €{price}.',
        
        'termin_payment_link': '''🔔 <b>Slot Notifications</b>

One-time payment: <b>€{price}</b>

We will notify you when new appointment slots appear.
You always book the appointment yourself via the official website.

This is a one-time purchase — notifications stay active permanently.''',
        
        'termin_payment_success': '''✅ <b>Notifications Activated!</b>

You will now receive alerts when new slots appear.''',

        'termin_payment_success_detailed': '''✅ <b>Payment Successful!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>What you paid for:</b>
🔔 Termin Reminder Service (one-time €4.99)

<b>What is now activated:</b>
✓ Unlimited reminders for appointment checking
✓ Choose your preferred reminder interval (6h or 12h)
✓ Pause/resume anytime

<b>What happens next:</b>
1. Select your reminder interval below
2. You'll receive regular reminders to check for slots
3. Each reminder includes the official appointment link

<b>⚠️ Important - What reminders do:</b>
• Send you a notification at your chosen interval
• Include the official appointment link
• Remind you to check manually

<b>⚠️ What reminders DON'T do:</b>
• We do NOT check for available slots
• We do NOT book appointments for you
• We do NOT bypass any website systems

<b>How to stop reminders:</b>
Go to "Manage Reminders" → "Pause Reminders"
━━━━━━━━━━━━━━━━━━━━━━

Select your reminder interval:''',
        
        # Status
        'termin_status_info': '''📊 <b>Your Status</b>

📍 City: {city}
🏛️ Authority: {authority}
🔍 Status: {status}
💳 Paid: {paid}
🔔 Notifications: {reminders}''',
        
        'status_searching': '⏳ Waiting for available slots',
        'status_booked': '✅ Slots found — check official link',
        'termin_status_updated': '✅ Status updated: {status}',
        'termin_congrats': 'Free slots were found! Book your appointment via the official link.',
        # Change city warning
        'change_city_warning_title': '⚠️ You already have an active monitoring',
        'change_city_warning_body': (
            '📍 {city}\n\n'
            'If you change the city:\n'
            '• your current monitoring will be stopped\n'
            '• a new monitoring requires a separate payment'
        ),
        'change_city_confirm': '🔁 Change city',
        'change_city_cancel': '❌ Cancel',
        'old_monitoring_stopped': '🛑 Previous monitoring stopped',
        'booking_instruction': (
            "✅ You are already on the correct page\n\n"
            "What to do:\n"
            "• choose a location\n"
            "• choose a date and time\n\n"
            "⏱ Takes less than 1 minute\n"
            "⚠️ Slots disappear quickly\n\n"
            "👇 Tap the button below"
        ),
    },
    
    'de': {
        'welcome': '''👋 <b>Willkommen!</b>

Dieser Bot bietet zwei Dienste:
• 📄 Deutscher Dokument-Generator
• 📅 Termin Assistent

Bitte wählen Sie Ihre Sprache:''',
        
        'select_language': '🌍 Sprache wählen:',
        'language_changed': '✅ Sprache geändert!',
        
        # Main Menu
        'main_menu': '''📋 <b>Hauptmenü</b>

Wählen Sie einen Dienst:''',
        
        'menu_document': '📄 Dokument-Generator',
        'menu_termin': '📅 Termin Assistent',
        
        'select_product': '''📋 <b>Dienst wählen</b>

Was möchten Sie tun?''',
        
        'product_document': '📄 Deutsches Dokument erstellen',
        'product_termin': '📅 Termin Assistent',
        
        'btn_back': '← Zurück',
        'btn_back_products': '← Zurück zu Diensten',
        'btn_main_menu': '🏠 Hauptmenü',
        'btn_help': '❓ Hilfe',
        'btn_change_language': '🌍 Sprache ändern',
        'btn_pay_now': '💳 Jetzt zahlen',
        'btn_verify_payment': '✅ Zahlung prüfen',
        'btn_open_booking': '🔗 Terminseite öffnen',
        'switch_to_termin_btn': '📅 Zu Termin Assistent wechseln',
        'switch_to_document_btn': '📄 Zu Dokument-Generator wechseln',
        
        'error': '❌ Ein Fehler ist aufgetreten. Bitte /start erneut versuchen.',
        'payment_pending': '⏳ Zahlung noch nicht bestätigt.',
        
        'doc_menu': '''📄 <b>Dokument-Generator</b>

Deutsche Dokumente schnell und einfach erstellen.''',
        
        'doc_new_document': '📝 Neues Dokument',
        'doc_my_documents': '📁 Meine Dokumente',
        
        'doc_payment_success_detailed': '''✅ <b>Zahlung erfolgreich!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Was Sie bezahlt haben:</b>
📄 {document_name} - Dokumentenerstellung

<b>Was jetzt aktiviert ist:</b>
✓ Ihr Dokument wird erstellt
✓ Sie erhalten die PDF-Datei in Kürze

<b>Was als nächstes passiert:</b>
1. Wir erstellen Ihr Dokument (1-2 Minuten)
2. Sie erhalten die PDF direkt in diesem Chat
3. Herunterladen und verwenden

<b>Hinweis:</b>
Dies ist ein einmaliger Kauf für dieses Dokument.
━━━━━━━━━━━━━━━━━━━━━━

Brauchen Sie ein weiteres Dokument? Nutzen Sie das Menü unten.''',
        
        'termin_menu': '''📅 <b>Termin-Assistent</b>

ℹ️ <b>Wichtig:</b>
Wir buchen KEINE Termine für Sie.
Wir helfen Ihnen, verfügbare Termine zu finden und benachrichtigen Sie, wenn welche frei werden.

🔔 Wenn ein Termin frei wird — erhalten Sie eine Benachrichtigung.
🔗 Den Termin buchen Sie immer selbst über die offizielle Website.''',
        
        'termin_select_city': '📍 Stadt & Behörde wählen',
        'termin_manage_reminders': '🔔 Benachrichtigungen verwalten',
        'termin_activate_reminders': '🔔 Benachrichtigungen aktivieren',
        
        'termin_disclaimer': '''⚠️ <b>Hinweis:</b>
Wir buchen keine Termine und umgehen keine Systeme.
Sie müssen selbst auf der offiziellen Website buchen.''',

        'termin_upsell_explainer': '''💡 <b>Wie können wir helfen?</b>
Verfügbare Termine erscheinen und verschwinden schnell.
Wir benachrichtigen Sie, wenn neue Termine frei werden.
Sie buchen immer selbst über die offizielle Website.
Wir stellen Ihnen den direkten offiziellen Terminlink bereit.''',
        'termin_pay_cta': '💳 Benachrichtigungen aktivieren (€{price})',
        
        'termin_view_guidance': '📚 Anleitung ansehen (Kostenlos)',
        'termin_set_reminder': '🔔 Benachrichtigungen aktiv',
        'termin_pay_reminders': '🔔 Benachrichtigen, wenn Termine frei werden (€{price})',
        
        'termin_need_pay': 'Benachrichtigungen erfordern eine einmalige Zahlung von €{price}.',
        
        'termin_payment_link': '''🔔 <b>Slot-Benachrichtigungen</b>

Einmalige Zahlung: <b>€{price}</b>

Wir benachrichtigen Sie, wenn neue Termine verfügbar werden.
Den Termin buchen Sie immer selbst über die offizielle Website.

Dies ist ein einmaliger Kauf — Benachrichtigungen bleiben dauerhaft aktiv.''',
        
        'termin_payment_success': '''✅ <b>Benachrichtigungen aktiviert!</b>

Sie werden nun informiert, wenn neue Termine verfügbar sind.''',

        'termin_payment_success_detailed': '''✅ <b>Zahlung erfolgreich!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Was Sie bezahlt haben:</b>
🔔 Termin-Erinnerungsdienst (einmalig €4.99)

<b>Was jetzt aktiviert ist:</b>
✓ Unbegrenzte Erinnerungen zur Terminprüfung
✓ Wählen Sie Ihr Intervall (6h oder 12h)
✓ Jederzeit pausieren/fortsetzen

<b>Was als nächstes passiert:</b>
1. Wählen Sie unten Ihr Erinnerungsintervall
2. Sie erhalten regelmäßige Erinnerungen
3. Jede Erinnerung enthält den offiziellen Terminlink

<b>⚠️ Was Erinnerungen tun:</b>
• Senden Ihnen eine Benachrichtigung
• Enthalten den offiziellen Terminlink
• Erinnern Sie daran, manuell zu prüfen

<b>⚠️ Was Erinnerungen NICHT tun:</b>
• Wir prüfen KEINE verfügbaren Termine
• Wir buchen KEINE Termine für Sie
• Wir umgehen KEINE Website-Systeme

<b>So stoppen Sie Erinnerungen:</b>
"Erinnerungen verwalten" → "Erinnerungen pausieren"
━━━━━━━━━━━━━━━━━━━━━━

Wählen Sie Ihr Erinnerungsintervall:''',
        
        'guidance_steps': 'So buchen Sie',
        'guidance_documents': 'Erforderliche Dokumente',
        'guidance_mistakes': 'Häufige Fehler',
        'guidance_timing': 'Wann prüfen',
        'guidance_tips': 'Tipps',
        'official_link': 'Offizieller Link',
        
        'interval_6h': 'Alle 6 Stunden',
        'interval_12h': 'Alle 12 Stunden',
        
        # Reminders
        'termin_select_interval': '''⏰ <b>Erinnerungsintervall wählen</b>

Wie oft möchten Sie an die Terminprüfung erinnert werden?''',
        
        'termin_reminder_activated': '''✅ <b>Erinnerungen aktiviert!</b>

Sie erhalten alle {interval} Stunden eine Erinnerung.
Jede Erinnerung enthält den direkten Link zur offiziellen Terminseite.''',
        
        'termin_reminder_message': '''🔔 <b>Zeit, Termine zu prüfen!</b>

Klicken Sie auf den offiziellen Link unten, um freie Termine zu prüfen.
Wenn Sie einen freien Termin finden — buchen Sie sofort.''',
        
        'termin_pause_reminders': '⏸️ Erinnerungen pausieren',
        'termin_change_interval': '⏱️ Intervall ändern',
        'termin_reminder_paused': '⏸️ Erinnerungen pausiert. Sie können sie jederzeit wieder aktivieren.',
        
        'termin_reminder_status': '''🔔 <b>Ihre Erinnerungen</b>

📍 Stadt: {city}
🏛️ Behörde: {authority}
⏱️ Intervall: alle {interval} Stunden
📊 Status: {status}''',
        
        'termin_select_city_first': 'Bitte wählen Sie zuerst eine Stadt und Behörde.',
        
        'status_searching': '⏳ Warten auf verfügbare Termine',
        'status_booked': '✅ Termine gefunden — über offiziellen Link buchen',
        'termin_status_info': '''📊 <b>Ihr Status</b>

📍 Stadt: {city}
🏛️ Behörde: {authority}
🔍 Status: {status}
💳 Bezahlt: {paid}
🔔 Benachrichtigungen: {reminders}''',
        'termin_status_updated': '✅ Status aktualisiert: {status}',
        'termin_congrats': 'Freie Termine gefunden! Buchen Sie über den offiziellen Link.',
        # Change city warning
        'change_city_warning_title': '⚠️ Sie haben bereits ein aktives Monitoring',
        'change_city_warning_body': (
            '📍 {city}\n\n'
            'Wenn Sie die Stadt ändern:\n'
            '• wird das aktuelle Monitoring gestoppt\n'
            '• ein neues Monitoring erfordert eine separate Zahlung'
        ),
        'change_city_confirm': '🔁 Stadt ändern',
        'change_city_cancel': '❌ Abbrechen',
        'old_monitoring_stopped': '🛑 Vorheriges Monitoring gestoppt',
        'booking_instruction': (
            "✅ Sie sind bereits auf der richtigen Seite\n\n"
            "Was zu tun ist:\n"
            "• Standort auswählen\n"
            "• Datum und Uhrzeit wählen\n\n"
            "⏱ Dauert weniger als 1 Minute\n"
            "⚠️ Termine sind schnell weg\n\n"
            "👇 Klicken Sie unten"
        ),
    },
    
    'ua': {
        'welcome': '''👋 <b>Ласкаво просимо!</b>

Цей бот пропонує два сервіси:
• 📄 Генератор німецьких документів
• 📅 Помічник з записів

Оберіть мову:''',
        
        'select_language': '🌍 Оберіть мову:',
        'language_changed': '✅ Мову змінено!',
        
        # Main Menu
        'main_menu': '''📋 <b>Головне меню</b>

Оберіть сервіс:''',
        
        'menu_document': '📄 Генератор документів',
        'menu_termin': '📅 Помічник з записів',
        
        'select_product': '''📋 <b>Оберіть сервіс</b>

Що ви хочете зробити?''',
        
        'product_document': '📄 Створити німецький документ',
        'product_termin': '📅 Помічник з записів',
        
        'btn_back': '← Назад',
        'btn_back_products': '← До сервісів',
        'btn_main_menu': '🏠 Головне меню',
        'btn_help': '❓ Допомога',
        'btn_change_language': '🌍 Змінити мову',
        'btn_pay_now': '💳 Оплатити',
        'btn_verify_payment': '✅ Перевірити оплату',
        'btn_open_booking': '🔗 Відкрити сторінку запису',
        'switch_to_termin_btn': '📅 Перейти до Помічника з записів',
        'switch_to_document_btn': '📄 Перейти до Генератора документів',
        
        'error': '❌ Сталася помилка. Спробуйте /start знову.',
        'payment_pending': '⏳ Оплата ще не підтверджена.',
        
        'doc_menu': '''📄 <b>Генератор документів</b>

Швидке створення німецьких документів.''',
        
        'doc_payment_success_detailed': '''✅ <b>Оплату підтверджено!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Що ви оплатили:</b>
📄 {document_name} - Створення документа

<b>Що активовано:</b>
✓ Ваш документ створюється
✓ Ви отримаєте PDF файл незабаром

<b>Що далі:</b>
1. Ми створюємо ваш документ (1-2 хвилини)
2. Ви отримаєте PDF прямо в цьому чаті
3. Завантажте та використовуйте

<b>Примітка:</b>
Це одноразова покупка для цього документа.
━━━━━━━━━━━━━━━━━━━━━━

Потрібен інший документ? Скористайтеся меню нижче.''',
        
        'termin_menu': '''📅 <b>Помічник із записів до установ</b>

ℹ️ <b>Важливо:</b>
Ми НЕ записуємо вас на прийом.
Ми допомагаємо знайти вільні слоти та повідомляємо, коли вони з'являються.

🔔 Коли з'являється вільний час — ви отримуєте сповіщення.
🔗 Запис ви завжди робите самостійно через офіційний сайт установи.''',
        
        'termin_select_city': '📍 Обрати місто та установу',
        'termin_manage_reminders': '🔔 Керувати сповіщеннями',
        'termin_activate_reminders': '🔔 Активувати сповіщення',
        
        'termin_disclaimer': '''⚠️ <b>Застереження:</b>
Ми не записуємо та не обходимо системи.
Ви маєте записатися самостійно на офіційному сайті.''',

        'termin_upsell_explainer': '''💡 <b>Чим ми можемо допомогти?</b>
Вільні місця з'являються і зникають дуже швидко.
Ми повідомимо вас, коли з'являться нові вільні слоти.
Запис ви завжди робите самостійно через офіційний сайт установи.
Ми надамо вам пряме офіційне посилання для запису.''',
        'termin_pay_cta': '💳 Отримувати сповіщення (€{price})',
        
        'termin_view_guidance': '📚 Переглянути інструкцію (Безкоштовно)',
        'termin_set_reminder': '🔔 Сповіщення активні',
        'termin_pay_reminders': '🔔 Повідомити, коли з\'являться місця (€{price})',
        
        'termin_need_pay': 'Сповіщення потребують одноразової оплати €{price}.',
        
        'termin_payment_link': '''🔔 <b>Сповіщення про вільні слоти</b>

Одноразова оплата: <b>€{price}</b>

Ми повідомимо вас, коли з'являться нові вільні слоти для запису.
Запис ви завжди робите самостійно через офіційний сайт установи.

Це одноразова покупка — сповіщення залишаються активними назавжди.''',
        
        'termin_payment_success': '''✅ <b>Сповіщення активовано!</b>

Ви отримуватимете повідомлення, коли з'являться нові вільні місця.''',

        'termin_payment_success_detailed': '''✅ <b>Оплату підтверджено!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Що ви оплатили:</b>
🔔 Сервіс нагадувань про записи (одноразово €4.99)

<b>Що активовано:</b>
✓ Необмежені нагадування для перевірки записів
✓ Оберіть інтервал (6 або 12 годин)
✓ Призупиніть/відновіть будь-коли

<b>Що далі:</b>
1. Оберіть інтервал нагадувань нижче
2. Ви отримуватимете регулярні нагадування
3. Кожне нагадування містить офіційне посилання

<b>⚠️ Що роблять нагадування:</b>
• Надсилають вам повідомлення
• Містять офіційне посилання для запису
• Нагадують перевірити вручну

<b>⚠️ Чого нагадування НЕ роблять:</b>
• Ми НЕ перевіряємо вільні місця
• Ми НЕ записуємо за вас
• Ми НЕ обходимо системи сайтів

<b>Як зупинити нагадування:</b>
"Керувати нагадуваннями" → "Призупинити"
━━━━━━━━━━━━━━━━━━━━━━

Оберіть інтервал нагадувань:''',
        
        'interval_6h': 'Кожні 6 годин',
        'interval_12h': 'Кожні 12 годин',
        
        # Guidance labels
        'guidance_steps': 'Як записатися',
        'guidance_documents': 'Необхідні документи',
        'guidance_mistakes': 'Поширені помилки',
        'guidance_timing': 'Коли перевіряти',
        'guidance_tips': 'Поради',
        'official_link': 'Офіційне посилання',
        
        # Reminders
        'termin_select_interval': '''⏰ <b>Оберіть інтервал нагадувань</b>

Як часто ви хочете отримувати нагадування про перевірку вільних слотів?''',
        
        'termin_reminder_activated': '''✅ <b>Нагадування активовано!</b>

Ви отримуватимете нагадування кожні {interval} годин.
Кожне нагадування містить пряме посилання на офіційний сайт запису.''',
        
        'termin_reminder_message': '''🔔 <b>Час перевірити записи!</b>

Натисніть на офіційне посилання нижче, щоб перевірити вільні слоти.
Якщо знайдете вільне місце — записуйтесь одразу.''',
        
        'termin_pause_reminders': '⏸️ Призупинити нагадування',
        'termin_reminder_paused': '⏸️ Нагадування призупинено. Ви можете відновити їх у будь-який час.',
        
        'termin_reminder_status': '''🔔 <b>Ваші нагадування</b>

📍 Місто: {city}
🏛️ Установа: {authority}
⏱️ Інтервал: кожні {interval} годин
📊 Статус: {status}''',
        
        'termin_select_city_first': 'Спочатку оберіть місто та установу.',
        
        'status_searching': '⏳ Очікуємо вільні слоти',
        'status_booked': '✅ Вільні слоти знайдено — перейдіть за офіційним посиланням',
        'termin_status_info': '''📊 <b>Ваш статус</b>

📍 Місто: {city}
🏛️ Установа: {authority}
🔍 Статус: {status}
💳 Оплачено: {paid}
🔔 Сповіщення: {reminders}''',
        'termin_status_updated': '✅ Статус оновлено: {status}',
        'termin_congrats': 'Знайдено вільні місця! Запишіться через офіційне посилання.',
        # Change city warning
        'change_city_warning_title': '⚠️ У вас вже є активний моніторинг',
        'change_city_warning_body': (
            '📍 {city}\n\n'
            'Якщо ви зміните місто:\n'
            '• поточний моніторинг буде зупинено\n'
            '• новий моніторинг потребує окремої оплати'
        ),
        'change_city_confirm': '🔁 Змінити місто',
        'change_city_cancel': '❌ Скасувати',
        'old_monitoring_stopped': '🛑 Попередній моніторинг зупинено',
        'booking_instruction': (
            "✅ Ви вже на правильній сторінці\n\n"
            "Що зробити:\n"
            "• оберіть відділення\n"
            "• оберіть дату і час\n\n"
            "⏱ Це займе менше 1 хвилини\n"
            "⚠️ Слоти швидко зникають\n\n"
            "👇 Натисніть кнопку нижче"
        ),
    },
    
    'pl': {
        'welcome': '''👋 <b>Witamy!</b>

Ten bot oferuje dwa serwisy:
• 📄 Generator dokumentów niemieckich
• 📅 Asystent terminów

Wybierz język:''',
        
        'select_language': '🌍 Wybierz język:',
        'language_changed': '✅ Język zmieniony!',
        
        # Main Menu
        'main_menu': '''📋 <b>Menu główne</b>

Wybierz usługę:''',
        
        'menu_document': '📄 Generator dokumentów',
        'menu_termin': '📅 Asystent terminów',
        
        'select_product': '''📋 <b>Wybierz serwis</b>

Co chcesz zrobić?''',
        'product_document': '📄 Utwórz niemiecki dokument',
        'product_termin': '📅 Asystent terminów',
        
        'btn_back': '← Wstecz',
        'btn_back_products': '← Do serwisów',
        'btn_main_menu': '🏠 Menu główne',
        'btn_help': '❓ Pomoc',
        'btn_change_language': '🌍 Zmień język',
        'btn_pay_now': '💳 Zapłać teraz',
        'btn_verify_payment': '✅ Zweryfikuj płatność',
        'btn_open_booking': '🔗 Otwórz stronę wizyt',
        'switch_to_termin_btn': '📅 Przejdź do Asystenta terminów',
        'switch_to_document_btn': '📄 Przejdź do Generatora dokumentów',
        
        'error': '❌ Wystąpił błąd. Spróbuj /start ponownie.',
        'payment_pending': '⏳ Płatność jeszcze nie potwierdzona.',
        
        'help': '''❓ <b>Pomoc</b>

<b>Dostępne usługi:</b>

📄 <b>Generator dokumentów</b>
Twórz niemieckie dokumenty (Kündigung, Vollmacht, itp.)

📅 <b>Asystent terminów</b>
Pomoc z terminami w niemieckich urzędach.

<b>Komendy:</b>
/start - Uruchom bota
/menu - Menu główne
/help - Ta pomoc

<b>Zastrzeżenie:</b>
NIE umawiamy wizyt ani nie omijamy żadnych systemów. Zapewniamy tylko wskazówki i oficjalne linki.''',
        
        'doc_menu': '''📄 <b>Generator dokumentów</b>

Twórz niemieckie dokumenty szybko i łatwo.''',
        
        'doc_new_document': '📝 Nowy dokument',
        'doc_my_documents': '📁 Moje dokumenty',
        
        'doc_payment_success_detailed': '''✅ <b>Płatność zakończona!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Za co zapłaciłeś:</b>
📄 {document_name} - Generowanie dokumentu

<b>Co jest teraz aktywne:</b>
✓ Twój dokument jest generowany
✓ Wkrótce otrzymasz plik PDF

<b>Co się stanie dalej:</b>
1. Generujemy Twój dokument (1-2 minuty)
2. Otrzymasz PDF bezpośrednio na tym czacie
3. Pobierz i używaj

<b>Uwaga:</b>
To jednorazowy zakup tego dokumentu.
━━━━━━━━━━━━━━━━━━━━━━

Potrzebujesz innego dokumentu? Użyj menu poniżej.''',
        
        'termin_menu': '''📅 <b>Asystent wizyt w urzędach</b>

ℹ️ <b>Ważne:</b>
NIE umawiamy wizyt za Ciebie.
Pomagamy znaleźć wolne terminy i powiadamiamy, gdy się pojawią.

🔔 Gdy zwolni się miejsce — otrzymasz powiadomienie.
🔗 Wizytę zawsze umawiasz samodzielnie na oficjalnej stronie urzędu.''',
        
        'termin_select_city': '📍 Wybierz miasto i urząd',
        'termin_manage_reminders': '🔔 Zarządzaj powiadomieniami',
        'termin_activate_reminders': '🔔 Aktywuj powiadomienia',
        
        'termin_disclaimer': '''⚠️ <b>Uwaga:</b>
Nie umawiamy wizyt i nie omijamy systemów.
Wizytę umawiasz samodzielnie na oficjalnej stronie.''',

        'termin_upsell_explainer': '''💡 <b>Jak możemy pomóc?</b>
Wolne terminy pojawiają się i znikają bardzo szybko.
Powiadomimy Cię, gdy pojawią się nowe wolne miejsca.
Wizytę zawsze umawiasz samodzielnie na oficjalnej stronie urzędu.
Udostępniamy bezpośredni oficjalny link do strony wizyt.''',
        'termin_pay_cta': '💳 Włącz powiadomienia (€{price})',
        
        'termin_view_guidance': '📚 Zobacz instrukcję (Bezpłatnie)',
        'termin_set_reminder': '🔔 Powiadomienia aktywne',
        'termin_pay_reminders': '🔔 Powiadom, gdy pojawią się miejsca (€{price})',
        
        'termin_need_pay': 'Powiadomienia wymagają jednorazowej opłaty €{price}.',
        
        'termin_payment_link': '''🔔 <b>Powiadomienia o wolnych terminach</b>

Jednorazowa opłata: <b>€{price}</b>

Powiadomimy Cię, gdy pojawią się nowe wolne terminy.
Wizytę zawsze umawiasz samodzielnie na oficjalnej stronie urzędu.

To jednorazowy zakup — powiadomienia pozostają aktywne na stałe.''',
        
        'termin_payment_success': '''✅ <b>Powiadomienia aktywowane!</b>

Otrzymasz alert, gdy pojawią się nowe wolne terminy.''',

        'termin_payment_success_detailed': '''✅ <b>Płatność zakończona!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Za co zapłaciłeś:</b>
🔔 Usługa przypomnień o terminach (jednorazowo €4.99)

<b>Co jest teraz aktywne:</b>
✓ Nieograniczone przypomnienia o sprawdzaniu terminów
✓ Wybierz preferowany interwał (6h lub 12h)
✓ Wstrzymaj/wznów w dowolnym momencie

<b>Co się stanie dalej:</b>
1. Wybierz interwał przypomnień poniżej
2. Będziesz otrzymywać regularne przypomnienia
3. Każde przypomnienie zawiera oficjalny link do strony wizyt

<b>⚠️ Co robią przypomnienia:</b>
• Wysyłają Ci powiadomienie w wybranym interwale
• Zawierają oficjalny link do strony wizyt
• Przypominają o ręcznym sprawdzeniu

<b>⚠️ Czego przypomnienia NIE robią:</b>
• NIE sprawdzamy dostępnych terminów
• NIE umawiamy wizyt za Ciebie
• NIE omijamy żadnych systemów

<b>Jak zatrzymać przypomnienia:</b>
"Zarządzaj przypomnieniami" → "Wstrzymaj przypomnienia"
━━━━━━━━━━━━━━━━━━━━━━

Wybierz interwał przypomnień:''',
        
        'guidance_steps': 'Jak umówić wizytę',
        'guidance_documents': 'Wymagane dokumenty',
        'guidance_mistakes': 'Częste błędy',
        'guidance_timing': 'Kiedy sprawdzać',
        'guidance_tips': 'Wskazówki',
        'official_link': 'Oficjalny link',
        
        'interval_6h': 'Co 6 godzin',
        'interval_12h': 'Co 12 godzin',
        
        # Reminders
        'termin_select_interval': '''⏰ <b>Wybierz interwał przypomnień</b>

Jak często chcesz otrzymywać przypomnienia o sprawdzaniu wolnych terminów?''',
        
        'termin_reminder_activated': '''✅ <b>Przypomnienia aktywowane!</b>

Będziesz otrzymywać przypomnienia co {interval} godzin.
Każde przypomnienie zawiera bezpośredni link do oficjalnej strony wizyt.''',
        
        'termin_reminder_message': '''🔔 <b>Czas sprawdzić terminy!</b>

Kliknij oficjalny link poniżej, aby sprawdzić wolne terminy.
Jeśli znajdziesz wolne miejsce — umów się od razu.''',
        
        'termin_pause_reminders': '⏸️ Wstrzymaj przypomnienia',
        'termin_change_interval': '⏱️ Zmień interwał',
        'termin_reminder_paused': '⏸️ Przypomnienia wstrzymane. Możesz je wznowić w dowolnym momencie.',
        
        'termin_reminder_status': '''🔔 <b>Twoje przypomnienia</b>

📍 Miasto: {city}
🏛️ Urząd: {authority}
⏱️ Interwał: co {interval} godzin
📊 Status: {status}''',
        
        'termin_select_city_first': 'Najpierw wybierz miasto i urząd.',
        
        'status_searching': '⏳ Oczekiwanie na wolne terminy',
        'status_booked': '✅ Znaleziono wolne terminy — umów się na oficjalnej stronie',
        'termin_status_info': '''📊 <b>Twój status</b>

📍 Miasto: {city}
🏛️ Urząd: {authority}
🔍 Status: {status}
💳 Opłacone: {paid}
🔔 Powiadomienia: {reminders}''',
        'termin_status_updated': '✅ Status zaktualizowany: {status}',
        'termin_congrats': 'Znaleziono wolne terminy! Umów się przez oficjalny link.',
        # Change city warning
        'change_city_warning_title': '⚠️ Masz już aktywne monitorowanie',
        'change_city_warning_body': (
            '📍 {city}\n\n'
            'Jeśli zmienisz miasto:\n'
            '• obecne monitorowanie zostanie zatrzymane\n'
            '• nowe monitorowanie wymaga osobnej płatności'
        ),
        'change_city_confirm': '🔁 Zmień miasto',
        'change_city_cancel': '❌ Anuluj',
        'old_monitoring_stopped': '🛑 Poprzednie monitorowanie zatrzymane',
        'booking_instruction': (
            "✅ Jesteś już na właściwej stronie\n\n"
            "Co zrobić:\n"
            "• wybierz lokalizację\n"
            "• wybierz datę i godzinę\n\n"
            "⏱ Zajmie mniej niż minutę\n"
            "⚠️ Terminy szybko znikają\n\n"
            "👇 Kliknij poniżej"
        ),
    },
    
    'tr': {
        'welcome': '''👋 <b>Hoş Geldiniz!</b>

Bu bot iki hizmet sunuyor:
• 📄 Alman Belge Oluşturucu
• 📅 Randevu Asistanı

Dilinizi seçin:''',
        
        'select_language': '🌍 Dilinizi seçin:',
        'language_changed': '✅ Dil değiştirildi!',
        
        # Main Menu
        'main_menu': '''📋 <b>Ana Menü</b>

Bir hizmet seçin:''',
        
        'menu_document': '📄 Belge Oluşturucu',
        'menu_termin': '📅 Randevu Asistanı',
        
        'select_product': '''📋 <b>Hizmet Seçin</b>

Ne yapmak istersiniz?''',
        'product_document': '📄 Alman belgesi oluştur',
        'product_termin': '📅 Randevu Asistanı',
        
        'btn_back': '← Geri',
        'btn_back_products': '← Hizmetlere dön',
        'btn_main_menu': '🏠 Ana Menü',
        'btn_help': '❓ Yardım',
        'btn_change_language': '🌍 Dili değiştir',
        'btn_pay_now': '💳 Şimdi öde',
        'btn_verify_payment': '✅ Ödemeyi doğrula',
        'btn_open_booking': '🔗 Randevu sayfasını aç',
        'switch_to_termin_btn': '📅 Randevu Asistanına geç',
        'switch_to_document_btn': '📄 Belge Oluşturucuya geç',
        
        'error': '❌ Bir hata oluştu. Lütfen /start tekrar deneyin.',
        'payment_pending': '⏳ Ödeme henüz onaylanmadı.',
        
        'help': '''❓ <b>Yardım</b>

<b>Mevcut Hizmetler:</b>

📄 <b>Belge Oluşturucu</b>
Alman belgeleri oluşturun (Kündigung, Vollmacht, vb.)

📅 <b>Randevu Asistanı</b>
Alman makamlarında randevu almak için yardım.

<b>Komutlar:</b>
/start - Botu başlat
/menu - Ana menü
/help - Bu yardım

<b>Uyarı:</b>
Randevu almıyoruz veya herhangi bir sistemi atlamıyoruz. Sadece rehberlik ve resmi linkler sağlıyoruz.''',
        
        'doc_menu': '''📄 <b>Belge Oluşturucu</b>

Alman belgelerini hızlı ve kolay oluşturun.''',
        
        'doc_new_document': '📝 Yeni Belge',
        'doc_my_documents': '📁 Belgelerim',
        
        'doc_payment_success_detailed': '''✅ <b>Ödeme Başarılı!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Ne için ödeme yaptınız:</b>
📄 {document_name} - Belge Oluşturma

<b>Şimdi aktif olan:</b>
✓ Belgeniz oluşturuluyor
✓ PDF dosyasını kısa süre içinde alacaksınız

<b>Bundan sonra ne olacak:</b>
1. Belgenizi oluşturuyoruz (1-2 dakika)
2. PDF'i doğrudan bu sohbette alacaksınız
3. İndirin ve kullanın

<b>Not:</b>
Bu, bu belge için tek seferlik bir satın almadır.
━━━━━━━━━━━━━━━━━━━━━━

Başka bir belgeye mi ihtiyacınız var? Aşağıdaki menüyü kullanın.''',
        
        'termin_menu': '''📅 <b>Randevu Asistanı</b>

ℹ️ <b>Önemli:</b>
Sizin yerinize randevu ALMIYORUZ.
Müsait randevuları bulmanıza yardımcı oluyor ve açıldığında sizi bilgilendiriyoruz.

🔔 Bir yer açıldığında bildirim alırsınız.
🔗 Randevuyu her zaman resmi web sitesi üzerinden kendiniz alırsınız.''',
        
        'termin_select_city': '📍 Şehir ve makam seçin',
        'termin_manage_reminders': '🔔 Bildirimleri yönet',
        'termin_activate_reminders': '🔔 Bildirimleri etkinleştir',
        
        'termin_disclaimer': '''⚠️ <b>Uyarı:</b>
Randevu almıyoruz ve sistemleri atlamıyoruz.
Resmi web sitesinden kendiniz randevu almalısınız.''',

        'termin_upsell_explainer': '''💡 <b>Nasıl yardımcı olabiliriz?</b>
Müsait randevular çok hızlı gelir ve gider.
Yeni yerler açıldığında sizi bilgilendiririz.
Randevunuzu her zaman resmi web sitesi üzerinden kendiniz alırsınız.
Size doğrudan resmi randevu linkini sağlıyoruz.''',
        'termin_pay_cta': '💳 Bildirimleri etkinleştir (€{price})',
        
        'termin_view_guidance': '📚 Rehberi görüntüle (Ücretsiz)',
        'termin_set_reminder': '🔔 Bildirimler aktif',
        'termin_pay_reminders': '🔔 Yer açılınca bildir (€{price})',
        
        'termin_need_pay': 'Bildirimler için €{price} tutarında tek seferlik ödeme gereklidir.',
        
        'termin_payment_link': '''🔔 <b>Randevu Bildirimleri</b>

Tek seferlik ödeme: <b>€{price}</b>

Yeni randevu slotları açıldığında sizi bilgilendireceğiz.
Randevuyu her zaman resmi web sitesi üzerinden kendiniz alırsınız.

Bu tek seferlik bir satın almadır — bildirimler kalıcı olarak aktif kalır.''',
        
        'termin_payment_success': '''✅ <b>Bildirimler Etkinleştirildi!</b>

Yeni randevu slotları açıldığında bilgilendirileceksiniz.''',

        'termin_payment_success_detailed': '''✅ <b>Ödeme Başarılı!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>Ne için ödeme yaptınız:</b>
🔔 Randevu Hatırlatma Hizmeti (tek seferlik €4.99)

<b>Şimdi aktif olan:</b>
✓ Randevu kontrolü için sınırsız hatırlatıcılar
✓ Tercih ettiğiniz aralığı seçin (6 veya 12 saat)
✓ İstediğiniz zaman duraklatın/devam ettirin

<b>Bundan sonra ne olacak:</b>
1. Aşağıdan hatırlatma aralığınızı seçin
2. Düzenli hatırlatıcılar alacaksınız
3. Her hatırlatıcı resmi randevu linkini içerir

<b>⚠️ Hatırlatıcılar ne yapar:</b>
• Seçtiğiniz aralıkta size bildirim gönderir
• Resmi randevu linkini içerir
• Manuel kontrol etmenizi hatırlatır

<b>⚠️ Hatırlatıcılar ne YAPMAZ:</b>
• Müsait randevuları kontrol ETMİYORUZ
• Sizin için randevu almıyoruz
• Hiçbir web sitesi sistemini atlamıyoruz

<b>Hatırlatıcıları nasıl durdurursunuz:</b>
"Hatırlatıcıları yönet" → "Hatırlatıcıları duraklat"
━━━━━━━━━━━━━━━━━━━━━━

Hatırlatma aralığınızı seçin:''',
        
        'guidance_steps': 'Nasıl randevu alınır',
        'guidance_documents': 'Gerekli belgeler',
        'guidance_mistakes': 'Yaygın hatalar',
        'guidance_timing': 'Ne zaman kontrol edilmeli',
        'guidance_tips': 'İpuçları',
        'official_link': 'Resmi link',
        
        'interval_6h': 'Her 6 saatte',
        'interval_12h': 'Her 12 saatte',
        
        # Reminders
        'termin_select_interval': '''⏰ <b>Hatırlatma aralığını seçin</b>

Müsait randevuları ne sıklıkla kontrol etmek için hatırlatma almak istiyorsunuz?''',
        
        'termin_reminder_activated': '''✅ <b>Hatırlatıcılar etkinleştirildi!</b>

Her {interval} saatte bir hatırlatma alacaksınız.
Her hatırlatıcı resmi randevu sayfasına doğrudan bağlantı içerir.''',
        
        'termin_reminder_message': '''🔔 <b>Randevuları kontrol etme zamanı!</b>

Müsait randevuları kontrol etmek için aşağıdaki resmi bağlantıya tıklayın.
Boş bir yer bulursanız — hemen randevu alın.''',
        
        'termin_pause_reminders': '⏸️ Hatırlatıcıları duraklat',
        'termin_change_interval': '⏱️ Aralığı değiştir',
        'termin_reminder_paused': '⏸️ Hatırlatıcılar duraklatıldı. İstediğiniz zaman yeniden etkinleştirebilirsiniz.',
        
        'termin_reminder_status': '''🔔 <b>Hatırlatıcılarınız</b>

📍 Şehir: {city}
🏛️ Makam: {authority}
⏱️ Aralık: her {interval} saatte
📊 Durum: {status}''',
        
        'termin_select_city_first': 'Lütfen önce bir şehir ve makam seçin.',
        
        'status_searching': '⏳ Müsait randevular bekleniyor',
        'status_booked': '✅ Müsait randevu bulundu — resmi linkten randevu alın',
        'termin_status_info': '''📊 <b>Durumunuz</b>

📍 Şehir: {city}
🏛️ Makam: {authority}
🔍 Durum: {status}
💳 Ödendi: {paid}
🔔 Bildirimler: {reminders}''',
        'termin_status_updated': '✅ Durum güncellendi: {status}',
        'termin_congrats': 'Müsait randevular bulundu! Resmi link üzerinden randevu alın.',
        # Change city warning
        'change_city_warning_title': '⚠️ Zaten aktif bir takip işleminiz var',
        'change_city_warning_body': (
            '📍 {city}\n\n'
            'Şehri değiştirirseniz:\n'
            '• mevcut takip durdurulacak\n'
            '• yeni takip için ayrı ödeme gerekecek'
        ),
        'change_city_confirm': '🔁 Şehri değiştir',
        'change_city_cancel': '❌ İptal',
        'old_monitoring_stopped': '🛑 Önceki takip durduruldu',
        'booking_instruction': (
            "✅ Zaten doğru sayfadasınız\n\n"
            "Ne yapmanız gerekiyor:\n"
            "• konumu seçin\n"
            "• tarih ve saat seçin\n\n"
            "⏱ 1 dakikadan az sürer\n"
            "⚠️ Randevular hızla kaybolur\n\n"
            "👇 Aşağıya tıklayın"
        ),
    },
    
    'ar': {
        'welcome': '''👋 <b>مرحباً!</b>

يقدم هذا البوت خدمتين:
• 📄 منشئ المستندات الألمانية
• 📅 مساعد المواعيد

اختر لغتك:''',
        
        'select_language': '🌍 اختر لغتك:',
        'language_changed': '✅ تم تغيير اللغة!',
        
        # Main Menu
        'main_menu': '''📋 <b>القائمة الرئيسية</b>

اختر خدمة:''',
        
        'menu_document': '📄 منشئ المستندات',
        'menu_termin': '📅 مساعد المواعيد',
        
        'select_product': '''📋 <b>اختر خدمة</b>

ماذا تريد أن تفعل؟''',
        'product_document': '📄 إنشاء مستند ألماني',
        'product_termin': '📅 مساعد المواعيد',
        
        'btn_back': '← رجوع',
        'btn_back_products': '← العودة للخدمات',
        'btn_main_menu': '🏠 القائمة الرئيسية',
        'btn_help': '❓ مساعدة',
        'btn_change_language': '🌍 تغيير اللغة',
        'btn_pay_now': '💳 ادفع الآن',
        'btn_verify_payment': '✅ تحقق من الدفع',
        'btn_open_booking': '🔗 افتح صفحة المواعيد',
        'switch_to_termin_btn': '📅 انتقل إلى مساعد المواعيد',
        'switch_to_document_btn': '📄 انتقل إلى منشئ المستندات',
        
        'error': '❌ حدث خطأ. يرجى المحاولة /start مرة أخرى.',
        'payment_pending': '⏳ لم يتم تأكيد الدفع بعد.',
        
        'help': '''❓ <b>مساعدة</b>

<b>الخدمات المتاحة:</b>

📄 <b>منشئ المستندات</b>
إنشاء مستندات ألمانية (Kündigung, Vollmacht, إلخ)

📅 <b>مساعد المواعيد</b>
المساعدة في المواعيد لدى الجهات الألمانية.

<b>الأوامر:</b>
/start - بدء البوت
/menu - القائمة الرئيسية
/help - هذه المساعدة

<b>إخلاء مسؤولية:</b>
نحن لا نحجز المواعيد ولا نتجاوز أي أنظمة. نقدم فقط الإرشادات والروابط الرسمية.''',
        
        'doc_menu': '''📄 <b>منشئ المستندات</b>

إنشاء المستندات الألمانية بسرعة وسهولة.''',
        
        'doc_new_document': '📝 مستند جديد',
        'doc_my_documents': '📁 مستنداتي',
        
        'doc_payment_success_detailed': '''✅ <b>تم الدفع بنجاح!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>ما دفعت مقابله:</b>
📄 {document_name} - إنشاء المستند

<b>ما تم تفعيله الآن:</b>
✓ يتم إنشاء مستندك
✓ ستستلم ملف PDF قريباً

<b>ما سيحدث بعد ذلك:</b>
1. نقوم بإنشاء مستندك (1-2 دقيقة)
2. ستستلم PDF مباشرة في هذه المحادثة
3. قم بالتحميل والاستخدام

<b>ملاحظة:</b>
هذا شراء لمرة واحدة لهذا المستند.
━━━━━━━━━━━━━━━━━━━━━━

هل تحتاج مستنداً آخر؟ استخدم القائمة أدناه.''',
        
        'termin_menu': '''📅 <b>مساعد المواعيد</b>

ℹ️ <b>مهم:</b>
نحن لا نحجز المواعيد نيابة عنك.
نساعدك في العثور على المواعيد المتاحة ونُعلمك عند ظهورها.

🔔 عندما يتوفر موعد — تتلقى إشعارًا.
🔗 تقوم دائمًا بحجز الموعد بنفسك عبر الموقع الرسمي للجهة.''',
        
        'termin_select_city': '📍 اختر المدينة والجهة',
        'termin_manage_reminders': '🔔 إدارة الإشعارات',
        'termin_activate_reminders': '🔔 تفعيل الإشعارات',
        
        'termin_disclaimer': '''⚠️ <b>تنويه:</b>
لا نحجز المواعيد ولا نتجاوز الأنظمة.
يجب عليك حجز الموعد بنفسك على الموقع الرسمي.''',

        'termin_upsell_explainer': '''💡 <b>كيف يمكننا المساعدة؟</b>
المواعيد المتاحة تظهر وتختفي بسرعة كبيرة.
سنُعلمك عند ظهور أماكن جديدة حتى لا تفوتك.
أنت دائمًا تحجز بنفسك عبر الموقع الرسمي.
نوفر لك رابط المواعيد الرسمي المباشر.''',
        'termin_pay_cta': '💳 تفعيل الإشعارات (€{price})',

        'termin_view_guidance': '📚 عرض الدليل (مجاني)',
        'termin_set_reminder': '🔔 الإشعارات مفعّلة',
        'termin_pay_reminders': '🔔 أعلمني عند ظهور مواعيد (€{price})',
        
        'termin_need_pay': 'الإشعارات تتطلب دفعة واحدة بقيمة €{price}.',
        
        'termin_payment_link': '''🔔 <b>إشعارات المواعيد المتاحة</b>

دفعة واحدة: <b>€{price}</b>

سنُعلمك عند ظهور مواعيد جديدة متاحة.
أنت دائمًا تحجز الموعد بنفسك عبر الموقع الرسمي.

هذا شراء لمرة واحدة — تبقى الإشعارات مفعّلة بشكل دائم.''',
        
        'termin_payment_success': '''✅ <b>تم تفعيل الإشعارات!</b>

ستتلقى تنبيهات عند ظهور مواعيد جديدة.''',

        'termin_payment_success_detailed': '''✅ <b>تم الدفع بنجاح!</b>

━━━━━━━━━━━━━━━━━━━━━━
<b>ما دفعت مقابله:</b>
🔔 خدمة تذكير المواعيد (مرة واحدة €4.99)

<b>ما تم تفعيله الآن:</b>
✓ تذكيرات غير محدودة لفحص المواعيد
✓ اختر الفاصل الزمني المفضل (6 أو 12 ساعة)
✓ إيقاف/استئناف في أي وقت

<b>ما سيحدث بعد ذلك:</b>
1. اختر فاصل التذكير أدناه
2. ستتلقى تذكيرات منتظمة
3. كل تذكير يحتوي على رابط المواعيد الرسمي

<b>⚠️ ما تفعله التذكيرات:</b>
• ترسل لك إشعاراً في الفاصل الذي اخترته
• تحتوي على رابط المواعيد الرسمي
• تذكرك بالفحص يدوياً

<b>⚠️ ما لا تفعله التذكيرات:</b>
• لا نفحص المواعيد المتاحة
• لا نحجز المواعيد لك
• لا نتجاوز أي أنظمة مواقع

<b>كيفية إيقاف التذكيرات:</b>
"إدارة التذكيرات" ← "إيقاف التذكيرات"
━━━━━━━━━━━━━━━━━━━━━━

اختر فاصل التذكير:''',
        
        'guidance_steps': 'كيفية حجز الموعد',
        'guidance_documents': 'المستندات المطلوبة',
        'guidance_mistakes': 'الأخطاء الشائعة',
        'guidance_timing': 'متى تفحص',
        'guidance_tips': 'نصائح',
        'official_link': 'الرابط الرسمي',
        
        'interval_6h': 'كل 6 ساعات',
        'interval_12h': 'كل 12 ساعة',
        
        # Reminders
        'termin_select_interval': '''⏰ <b>اختر فاصل التذكير</b>

كم مرة تريد أن يتم تذكيرك بفحص المواعيد المتاحة؟''',
        
        'termin_reminder_activated': '''✅ <b>تم تفعيل التذكيرات!</b>

ستتلقى تذكيراً كل {interval} ساعات.
كل تذكير يحتوي على رابط مباشر لصفحة المواعيد الرسمية.''',
        
        'termin_reminder_message': '''🔔 <b>حان وقت فحص المواعيد!</b>

اضغط على الرابط الرسمي أدناه لفحص المواعيد المتاحة.
إذا وجدت موعداً متاحاً — احجز فوراً.''',
        
        'termin_pause_reminders': '⏸️ إيقاف التذكيرات',
        'termin_change_interval': '⏱️ تغيير الفاصل',
        'termin_reminder_paused': '⏸️ تم إيقاف التذكيرات. يمكنك إعادة تفعيلها في أي وقت.',
        
        'termin_reminder_status': '''🔔 <b>تذكيراتك</b>

📍 المدينة: {city}
🏛️ الجهة: {authority}
⏱️ الفاصل: كل {interval} ساعات
📊 الحالة: {status}''',
        
        'termin_select_city_first': 'يرجى اختيار مدينة وجهة أولاً.',
        
        'status_searching': '⏳ في انتظار مواعيد متاحة',
        'status_booked': '✅ تم العثور على مواعيد — احجز عبر الرابط الرسمي',
        'termin_status_info': '''📊 <b>حالتك</b>

📍 المدينة: {city}
🏛️ الجهة: {authority}
🔍 الحالة: {status}
💳 مدفوع: {paid}
🔔 الإشعارات: {reminders}''',
        'termin_status_updated': '✅ تم تحديث الحالة: {status}',
        'termin_congrats': 'تم العثور على مواعيد متاحة! احجز عبر الرابط الرسمي.',
        # Change city warning
        'change_city_warning_title': '⚠️ لديك بالفعل مراقبة نشطة',
        'change_city_warning_body': (
            '📍 {city}\n\n'
            'إذا قمت بتغيير المدينة:\n'
            '• سيتم إيقاف المراقبة الحالية\n'
            '• يتطلب بدء مراقبة جديدة دفعًا منفصلًا'
        ),
        'change_city_confirm': '🔁 تغيير المدينة',
        'change_city_cancel': '❌ إلغاء',
        'old_monitoring_stopped': '🛑 تم إيقاف المراقبة السابقة',
        'booking_instruction': (
            "✅ أنت بالفعل في الصفحة الصحيحة\n\n"
            "ما يجب فعله:\n"
            "• اختر الموقع\n"
            "• اختر التاريخ والوقت\n\n"
            "⏱ يستغرق أقل من دقيقة\n"
            "⚠️ المواعيد تختفي بسرعة\n\n"
            "👇 اضغط أدناه"
        ),
    },
}

# Alias: 'uk' → same dict as 'ua' so both codes resolve identically.
TEXTS['uk'] = TEXTS['ua']


def get_text(key: str, language: str = 'en', **kwargs) -> str:
    """Get localized text with optional formatting.

    Normalizes Ukrainian: 'uk' → 'ua' (TEXTS uses 'ua' as canonical key).
    """
    # Normalize Ukrainian before lookup
    if language in ("uk", "ua"):
        language = "ua"
    lang_texts = TEXTS.get(language, TEXTS['en'])
    text = lang_texts.get(key)
    
    # Fallback to English
    if text is None:
        text = TEXTS['en'].get(key, key)
    
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    
    return text
