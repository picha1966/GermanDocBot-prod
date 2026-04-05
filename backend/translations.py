# -*- coding: utf-8 -*-
"""
GERMAN_DOC_BOT v4.6 - Глобальний багатомовний словник
Підтримка 6 мов: UA, DE, EN, PL, TR, AR (з RTL)
40+ типів документів з професійною німецькою термінологією

Refactored version with:
- TEXTS as primary dictionary (TRANSLATIONS as alias)
- FIELD_PROMPTS extracted from TEXTS['fields']
- Auto-generated DOCUMENT_NAMES from doc_ keys
- All compatibility bridges for bot.py and webapp_server.py
"""

# ============================================================================
# SUPPORTED LANGUAGES
# ============================================================================

SUPPORTED_LANGUAGES = ['ua', 'de', 'en', 'pl', 'tr', 'ar']
RTL_LANGUAGES = ['ar']  # Мови з написанням справа наліво

LANGUAGE_NAMES = {
    'ua': {'ua': '🇺🇦 Українська', 'de': 'Ukrainisch', 'en': 'Ukrainian', 
           'pl': 'Ukraiński', 'tr': 'Ukraynaca', 'ar': 'الأوكرانية'},
    'de': {'ua': '🇩🇪 Німецька', 'de': 'Deutsch', 'en': 'German', 
           'pl': 'Niemiecki', 'tr': 'Almanca', 'ar': 'الألمانية'},
    'en': {'ua': '🇬🇧 Англійська', 'de': 'Englisch', 'en': 'English', 
           'pl': 'Angielski', 'tr': 'İngilizce', 'ar': 'الإنجليزية'},
    'pl': {'ua': '🇵🇱 Польська', 'de': 'Polnisch', 'en': 'Polish', 
           'pl': 'Polski', 'tr': 'Lehçe', 'ar': 'البولندية'},
    'tr': {'ua': '🇹🇷 Турецька', 'de': 'Türkisch', 'en': 'Turkish', 
           'pl': 'Turecki', 'tr': 'Türkçe', 'ar': 'التركية'},
    'ar': {'ua': '🇸🇦 Арабська', 'de': 'Arabisch', 'en': 'Arabic', 
           'pl': 'Arabski', 'tr': 'Arapça', 'ar': 'العربية'},
}


# ============================================================================
# TEXTS - PRIMARY UI TRANSLATIONS DICTIONARY
# ============================================================================

TEXTS = {
    # ========================================================================
    # WELCOME MESSAGES
    # ========================================================================
    
    # Main welcome (primary key)
    'welcome': {
        'ua': '🇩🇪 <b>Вітаємо у German Doc Bot Premium!</b>\n\n'
              'Я допоможу вам заповнити документи для Німеччини швидко та правильно.\n\n'
              '📋 Оберіть тип документа нижче:',
        'de': '🇩🇪 <b>Willkommen beim German Doc Bot Premium!</b>\n\n'
              'Ich helfe Ihnen beim schnellen und korrekten Ausfüllen von Dokumenten für Deutschland.\n\n'
              '📋 Wählen Sie unten den Dokumenttyp:',
        'en': '🇩🇪 <b>Welcome to German Doc Bot Premium!</b>\n\n'
              'I will help you fill out documents for Germany quickly and correctly.\n\n'
              '📋 Choose document type below:',
        'pl': '🇩🇪 <b>Witamy w German Doc Bot Premium!</b>\n\n'
              'Pomogę Ci szybko i poprawnie wypełnić dokumenty dla Niemiec.\n\n'
              '📋 Wybierz typ dokumentu poniżej:',
        'tr': '🇩🇪 <b>German Doc Bot Premium\'a Hoş Geldiniz!</b>\n\n'
              'Almanya için belgeleri hızlı ve doğru bir şekilde doldurmanıza yardımcı olacağım.\n\n'
              '📋 Aşağıdan belge türünü seçin:',
        'ar': '🇩🇪 <b>مرحباً بك في German Doc Bot Premium!</b>\n\n'
              'سأساعدك في ملء المستندات لألمانيا بسرعة وبشكل صحيح.\n\n'
              '📋 اختر نوع المستند أدناه:',
    },
    
    # Welcome message (alias - copy of 'welcome')
    'welcome_msg': {
        'ua': '🇩🇪 <b>Вітаємо у German Doc Bot Premium!</b>\n\n'
              'Я допоможу вам заповнити документи для Німеччини швидко та правильно.\n\n'
              '📋 Оберіть тип документа нижче:',
        'de': '🇩🇪 <b>Willkommen beim German Doc Bot Premium!</b>\n\n'
              'Ich helfe Ihnen beim schnellen und korrekten Ausfüllen von Dokumenten für Deutschland.\n\n'
              '📋 Wählen Sie unten den Dokumenttyp:',
        'en': '🇩🇪 <b>Welcome to German Doc Bot Premium!</b>\n\n'
              'I will help you fill out documents for Germany quickly and correctly.\n\n'
              '📋 Choose document type below:',
        'pl': '🇩🇪 <b>Witamy w German Doc Bot Premium!</b>\n\n'
              'Pomogę Ci szybko i poprawnie wypełnić dokumenty dla Niemiec.\n\n'
              '📋 Wybierz typ dokumentu poniżej:',
        'tr': '🇩🇪 <b>German Doc Bot Premium\'a Hoş Geldiniz!</b>\n\n'
              'Almanya için belgeleri hızlı ve doğru bir şekilde doldurmanıza yardımcı olacağım.\n\n'
              '📋 Aşağıdan belge türünü seçin:',
        'ar': '🇩🇪 <b>مرحباً بك في German Doc Bot Premium!</b>\n\n'
              'سأساعدك في ملء المستندات لألمانيا بسرعة وبشكل صحيح.\n\n'
              '📋 اختر نوع المستند أدناه:',
    },
    
    # ========================================================================
    # LANGUAGE SELECTION
    # ========================================================================
    
    'select_language': {
        'ua': '🌍 Оберіть мову:',
        'de': '🌍 Sprache wählen:',
        'en': '🌍 Select language:',
        'pl': '🌍 Wybierz język:',
        'tr': '🌍 Dil seçin:',
        'ar': '🌍 اختر اللغة:',
    },
    
    # ========================================================================
    # PAYMENT SCREEN
    # ========================================================================
    
    'payment_screen_title': {
        'ua': '📄 <b>Ваш документ готовий!</b>\n\n'
              'Після оплати ви отримаєте:\n'
              '✓ PDF-файл без водяних знаків\n'
              '✓ Адресу органу для відправки\n'
              '✓ Супровідний лист (Anschreiben)',
        'de': '📄 <b>Ihr Dokument ist fertig!</b>\n\n'
              'Nach der Zahlung erhalten Sie:\n'
              '✓ PDF-Datei ohne Wasserzeichen\n'
              '✓ Behördenadresse für den Versand\n'
              '✓ Anschreiben',
        'en': '📄 <b>Your document is ready!</b>\n\n'
              'After payment you will receive:\n'
              '✓ PDF file without watermarks\n'
              '✓ Authority address for mailing\n'
              '✓ Cover letter (Anschreiben)',
        'pl': '📄 <b>Twój dokument jest gotowy!</b>\n\n'
              'Po płatności otrzymasz:\n'
              '✓ Plik PDF bez znaków wodnych\n'
              '✓ Adres urzędu do wysyłki\n'
              '✓ List przewodni (Anschreiben)',
        'tr': '📄 <b>Belgeniz hazır!</b>\n\n'
              'Ödemeden sonra alacaksınız:\n'
              '✓ Filigransız PDF dosyası\n'
              '✓ Gönderi için kurum adresi\n'
              '✓ Kapak mektubu (Anschreiben)',
        'ar': '📄 <b>مستندك جاهز!</b>\n\n'
              'بعد الدفع ستحصل على:\n'
              '✓ ملف PDF بدون علامة مائية\n'
              '✓ عنوان الجهة للإرسال\n'
              '✓ خطاب تغطية (Anschreiben)',
    },
    
    # ========================================================================
    # AUTO-FILL & DRAFTS
    # ========================================================================
    
    'autofill_prompt': {
        'ua': '💡 <b>Знайдено збережені дані!</b>\n\nБажаєте автоматично заповнити спільні поля?',
        'de': '💡 <b>Gespeicherte Daten gefunden!</b>\n\nMöchten Sie gemeinsame Felder automatisch ausfüllen?',
        'en': '💡 <b>Saved data found!</b>\n\nWould you like to auto-fill common fields?',
        'pl': '💡 <b>Znaleziono zapisane dane!</b>\n\nCzy chcesz automatycznie wypełnić wspólne pola?',
        'tr': '💡 <b>Kayıtlı veriler bulundu!</b>\n\nOrtak alanları otomatik doldurmak ister misiniz?',
        'ar': '💡 <b>تم العثور على بيانات محفوظة!</b>\n\nهل تريد الملء التلقائي للحقول المشتركة؟',
    },
    
    'draft_found': {
        'ua': '📝 <b>Знайдено незавершений документ!</b>\n\nБажаєте продовжити з місця зупинки?',
        'de': '📝 <b>Unvollständiges Dokument gefunden!</b>\n\nMöchten Sie dort weitermachen, wo Sie aufgehört haben?',
        'en': '📝 <b>Incomplete document found!</b>\n\nWould you like to continue where you left off?',
        'pl': '📝 <b>Znaleziono niekompletny dokument!</b>\n\nCzy chcesz kontynuować od miejsca, w którym skończyłeś?',
        'tr': '📝 <b>Tamamlanmamış belge bulundu!</b>\n\nKaldığınız yerden devam etmek ister misiniz?',
        'ar': '📝 <b>تم العثور على مستند غير مكتمل!</b>\n\nهل تريد المتابعة من حيث توقفت؟',
    },
    
    # ========================================================================
    # BUTTONS
    # ========================================================================
    
    'btn_yes': {
        'ua': '✅ Так', 'de': '✅ Ja', 'en': '✅ Yes',
        'pl': '✅ Tak', 'tr': '✅ Evet', 'ar': '✅ نعم'
    },
    'btn_no': {
        'ua': '❌ Ні', 'de': '❌ Nein', 'en': '❌ No',
        'pl': '❌ Nie', 'tr': '❌ Hayır', 'ar': '❌ لا'
    },
    'btn_cancel': {
        'ua': '❌ Скасувати', 'de': '❌ Abbrechen', 'en': '❌ Cancel',
        'pl': '❌ Anuluj', 'tr': '❌ İptal', 'ar': '❌ إلغاء'
    },
    'btn_back': {
        'ua': '◀️ Назад', 'de': '◀️ Zurück', 'en': '◀️ Back',
        'pl': '◀️ Wstecz', 'tr': '◀️ Geri', 'ar': '◀️ رجوع'
    },
    'btn_pay': {
        'ua': '💳 Сплатити', 'de': '💳 Bezahlen', 'en': '💳 Pay',
        'pl': '💳 Zapłać', 'tr': '💳 Öde', 'ar': '💳 دفع'
    },
    'btn_download': {
        'ua': '📥 Завантажити', 'de': '📥 Herunterladen', 'en': '📥 Download',
        'pl': '📥 Pobierz', 'tr': '📥 İndir', 'ar': '📥 تحميل'
    },
    
    # ========================================================================
    # STATUS MESSAGES
    # ========================================================================
    
 'processing': {
    'ua': '⏳ Обробляємо...',
    'de': '⏳ Verarbeitung...',
    'en': '⏳ Processing...',
    'pl': '⏳ Przetwarzanie...',
    'tr': '⏳ İşleniyor...',
    'ar': '⏳ جاري المعالجة...'
},

'success': {
    'ua': '✅ Успішно!',
    'de': '✅ Erfolgreich!',
    'en': '✅ Success!',
    'pl': '✅ Sukces!',
    'tr': '✅ Başarılı!',
    'ar': '✅ نجاح!'
},

'error': {
    'ua': '❌ Помилка',
    'de': '❌ Fehler',
    'en': '❌ Error',
    'pl': '❌ Błąd',
    'tr': '❌ Hata',
    'ar': '❌ خطأ'
},

'generating_pdf': {
    'ua': '⏳ Генерую ваш PDF, зачекайте кілька секунд...',
    'de': '⏳ Ihr PDF wird erstellt, bitte warten...'
},

'error_pdf': {
    'ua': '❌ Помилка при створенні PDF. Будь ласка, перевірте дані в анкеті.',
    'de': '❌ Fehler bei der PDF-Erstellung. Bitte prüfen Sie Ihre Eingaben.'
},

    
    # ========================================================================
    # FIELD PROMPTS - All 50+ fields
    # ========================================================================
    
    'fields': {
        # === PERSONAL DATA (Persönliche Daten) ===
        'first_name': {
            'ua': 'Введіть ваше ім\'я (латиницею)',
            'de': 'Geben Sie Ihren Vornamen ein',
            'en': 'Enter your first name',
            'pl': 'Wpisz swoje imię (łacińskimi literami)',
            'tr': 'Adınızı girin (Latin harfleri)',
            'ar': 'أدخل اسمك الأول (بالأحرف اللاتينية)'
        },
        'last_name': {
            'ua': 'Введіть ваше прізвище (латиницею)',
            'de': 'Geben Sie Ihren Nachnamen ein',
            'en': 'Enter your last name',
            'pl': 'Wpisz swoje nazwisko (łacińskimi literami)',
            'tr': 'Soyadınızı girin (Latin harfleri)',
            'ar': 'أدخل اسم عائلتك (بالأحرف اللاتينية)'
        },
        'birth_name': {
            'ua': 'Введіть дівоче прізвище (якщо змінювали)',
            'de': 'Geben Sie Ihren Geburtsnamen ein (falls abweichend)',
            'en': 'Enter your birth name (if changed)',
            'pl': 'Wpisz nazwisko panieńskie (jeśli zmienione)',
            'tr': 'Kızlık soyadınızı girin (değiştiyse)',
            'ar': 'أدخل اسم العائلة عند الولادة (إذا تغير)'
        },
        'birth_date': {
            'ua': 'Введіть дату народження (ДД.ММ.РРРР)',
            'de': 'Geben Sie Ihr Geburtsdatum ein (TT.MM.JJJJ)',
            'en': 'Enter your date of birth (DD.MM.YYYY)',
            'pl': 'Wpisz datę urodzenia (DD.MM.RRRR)',
            'tr': 'Doğum tarihinizi girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ ميلادك (يوم.شهر.سنة)'
        },
        'birth_place': {
            'ua': 'Введіть місце народження',
            'de': 'Geben Sie Ihren Geburtsort ein',
            'en': 'Enter your place of birth',
            'pl': 'Wpisz miejsce urodzenia',
            'tr': 'Doğum yerinizi girin',
            'ar': 'أدخل مكان الولادة'
        },
        'birth_country': {
            'ua': 'Введіть країну народження',
            'de': 'Geben Sie Ihr Geburtsland ein',
            'en': 'Enter your country of birth',
            'pl': 'Wpisz kraj urodzenia',
            'tr': 'Doğduğunuz ülkeyi girin',
            'ar': 'أدخل بلد الولادة'
        },
        'nationality': {
            'ua': 'Введіть громадянство',
            'de': 'Geben Sie Ihre Staatsangehörigkeit ein',
            'en': 'Enter your nationality',
            'pl': 'Wpisz obywatelstwo',
            'tr': 'Vatandaşlığınızı girin',
            'ar': 'أدخل جنسيتك'
        },
        'gender': {
            'ua': 'Оберіть стать (M - чоловіча / W - жіноча / D - різне)',
            'de': 'Wählen Sie das Geschlecht (M - männlich / W - weiblich / D - divers)',
            'en': 'Select gender (M - male / W - female / D - diverse)',
            'pl': 'Wybierz płeć (M - mężczyzna / W - kobieta / D - inna)',
            'tr': 'Cinsiyet seçin (M - erkek / W - kadın / D - diğer)',
            'ar': 'اختر الجنس (M - ذكر / W - أنثى / D - آخر)'
        },
        'marital_status': {
            'ua': 'Оберіть сімейний стан (ledig/verheiratet/geschieden/verwitwet)',
            'de': 'Wählen Sie den Familienstand (ledig/verheiratet/geschieden/verwitwet)',
            'en': 'Select marital status (single/married/divorced/widowed)',
            'pl': 'Wybierz stan cywilny (kawaler-panna/żonaty-zamężna/rozwiedziony/wdowiec)',
            'tr': 'Medeni durumu seçin (bekar/evli/boşanmış/dul)',
            'ar': 'اختر الحالة الاجتماعية (أعزب/متزوج/مطلق/أرمل)'
        },
        'religion': {
            'ua': 'Введіть релігійну приналежність (або "keine" якщо немає)',
            'de': 'Geben Sie Ihre Religionszugehörigkeit ein (oder "keine")',
            'en': 'Enter your religious affiliation (or "keine" if none)',
            'pl': 'Wpisz wyznanie (lub "keine" jeśli brak)',
            'tr': 'Din bilgisini girin (veya yoksa "keine")',
            'ar': 'أدخل الانتماء الديني (أو "keine" إذا لا يوجد)'
        },
        
        # === ADDRESS (Anschrift) ===
        'street': {
            'ua': 'Введіть назву вулиці',
            'de': 'Geben Sie den Straßennamen ein',
            'en': 'Enter street name',
            'pl': 'Wpisz nazwę ulicy',
            'tr': 'Sokak adını girin',
            'ar': 'أدخل اسم الشارع'
        },
        'house_number': {
            'ua': 'Введіть номер будинку',
            'de': 'Geben Sie die Hausnummer ein',
            'en': 'Enter house number',
            'pl': 'Wpisz numer domu',
            'tr': 'Ev numarasını girin',
            'ar': 'أدخل رقم المنزل'
        },
        'address': {
            'ua': 'Введіть повну адресу (вулиця, номер будинку)',
            'de': 'Geben Sie die vollständige Adresse ein (Straße, Hausnummer)',
            'en': 'Enter full address (street, house number)',
            'pl': 'Wpisz pełny adres (ulica, numer domu)',
            'tr': 'Tam adresi girin (sokak, ev numarası)',
            'ar': 'أدخل العنوان الكامل (الشارع، رقم المنزل)'
        },
        'address_addition': {
            'ua': 'Додаток до адреси (квартира, поверх) - опціонально',
            'de': 'Adresszusatz (Wohnung, Etage) - optional',
            'en': 'Address addition (apartment, floor) - optional',
            'pl': 'Dodatek do adresu (mieszkanie, piętro) - opcjonalnie',
            'tr': 'Adres eki (daire, kat) - isteğe bağlı',
            'ar': 'إضافة للعنوان (شقة، طابق) - اختياري'
        },
        'postal_code': {
            'ua': 'Введіть поштовий індекс (5 цифр)',
            'de': 'Geben Sie die Postleitzahl ein (5 Ziffern)',
            'en': 'Enter postal code (5 digits)',
            'pl': 'Wpisz kod pocztowy (5 cyfr)',
            'tr': 'Posta kodunu girin (5 rakam)',
            'ar': 'أدخل الرمز البريدي (5 أرقام)'
        },
        'city': {
            'ua': 'Введіть назву міста',
            'de': 'Geben Sie den Ort ein',
            'en': 'Enter city name',
            'pl': 'Wpisz nazwę miasta',
            'tr': 'Şehir adını girin',
            'ar': 'أدخل اسم المدينة'
        },
        'country': {
            'ua': 'Введіть країну',
            'de': 'Geben Sie das Land ein',
            'en': 'Enter country',
            'pl': 'Wpisz kraj',
            'tr': 'Ülkeyi girin',
            'ar': 'أدخل البلد'
        },
        
        # === CONTACT (Kontaktdaten) ===
        'phone': {
            'ua': 'Введіть номер телефону (з кодом країни)',
            'de': 'Geben Sie Ihre Telefonnummer ein (mit Landesvorwahl)',
            'en': 'Enter phone number (with country code)',
            'pl': 'Wpisz numer telefonu (z numerem kierunkowym)',
            'tr': 'Telefon numaranızı girin (ülke kodu ile)',
            'ar': 'أدخل رقم الهاتف (مع رمز البلد)'
        },
        'mobile': {
            'ua': 'Введіть номер мобільного телефону',
            'de': 'Geben Sie Ihre Handynummer ein',
            'en': 'Enter mobile phone number',
            'pl': 'Wpisz numer telefonu komórkowego',
            'tr': 'Cep telefonu numaranızı girin',
            'ar': 'أدخل رقم الجوال'
        },
        'email': {
            'ua': 'Введіть email адресу',
            'de': 'Geben Sie Ihre E-Mail-Adresse ein',
            'en': 'Enter email address',
            'pl': 'Wpisz adres e-mail',
            'tr': 'E-posta adresinizi girin',
            'ar': 'أدخل عنوان البريد الإلكتروني'
        },
        
        # === IDENTIFICATION (Identifikation) ===
        'id_number': {
            'ua': 'Введіть номер посвідчення особи',
            'de': 'Geben Sie Ihre Personalausweisnummer ein',
            'en': 'Enter ID card number',
            'pl': 'Wpisz numer dowodu osobistego',
            'tr': 'Kimlik numaranızı girin',
            'ar': 'أدخل رقم بطاقة الهوية'
        },
        'passport_number': {
            'ua': 'Введіть номер закордонного паспорта',
            'de': 'Geben Sie Ihre Reisepassnummer ein',
            'en': 'Enter passport number',
            'pl': 'Wpisz numer paszportu',
            'tr': 'Pasaport numaranızı girin',
            'ar': 'أدخل رقم جواز السفر'
        },
        'tax_id': {
            'ua': 'Введіть податковий номер IdNr (11 цифр)',
            'de': 'Geben Sie Ihre Steuer-Identifikationsnummer ein (11 Ziffern)',
            'en': 'Enter Tax ID number (11 digits)',
            'pl': 'Wpisz numer identyfikacji podatkowej (11 cyfr)',
            'tr': 'Vergi kimlik numaranızı girin (11 rakam)',
            'ar': 'أدخل رقم التعريف الضريبي (11 رقماً)'
        },
        'social_security_number': {
            'ua': 'Введіть номер соціального страхування (Sozialversicherungsnummer)',
            'de': 'Geben Sie Ihre Sozialversicherungsnummer ein',
            'en': 'Enter social security number',
            'pl': 'Wpisz numer ubezpieczenia społecznego',
            'tr': 'Sosyal güvenlik numaranızı girin',
            'ar': 'أدخل رقم الضمان الاجتماعي'
        },
        'aufenthaltstitel': {
            'ua': 'Введіть тип дозволу на перебування (Aufenthaltstitel)',
            'de': 'Geben Sie die Art des Aufenthaltstitels ein',
            'en': 'Enter residence permit type',
            'pl': 'Wpisz rodzaj zezwolenia na pobyt',
            'tr': 'Oturma izni türünü girin',
            'ar': 'أدخل نوع تصريح الإقامة'
        },
        'aufenthaltstitel_valid_until': {
            'ua': 'Введіть термін дії дозволу на перебування (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Gültigkeitsdatum des Aufenthaltstitels ein (TT.MM.JJJJ)',
            'en': 'Enter residence permit validity date (DD.MM.YYYY)',
            'pl': 'Wpisz datę ważności zezwolenia na pobyt (DD.MM.RRRR)',
            'tr': 'Oturma izni geçerlilik tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ انتهاء صلاحية تصريح الإقامة'
        },
        
        # === BANK DETAILS (Bankverbindung) ===
        'iban': {
            'ua': 'Введіть IBAN банківського рахунку',
            'de': 'Geben Sie die IBAN des Bankkontos ein',
            'en': 'Enter bank account IBAN',
            'pl': 'Wpisz numer IBAN konta bankowego',
            'tr': 'Banka hesabı IBAN\'ını girin',
            'ar': 'أدخل رقم IBAN للحساب البنكي'
        },
        'bic': {
            'ua': 'Введіть BIC/SWIFT код банку',
            'de': 'Geben Sie den BIC/SWIFT-Code der Bank ein',
            'en': 'Enter bank BIC/SWIFT code',
            'pl': 'Wpisz kod BIC/SWIFT banku',
            'tr': 'Banka BIC/SWIFT kodunu girin',
            'ar': 'أدخل رمز BIC/SWIFT للبنك'
        },
        'bank_name': {
            'ua': 'Введіть назву банку',
            'de': 'Geben Sie den Namen der Bank ein',
            'en': 'Enter bank name',
            'pl': 'Wpisz nazwę banku',
            'tr': 'Banka adını girin',
            'ar': 'أدخل اسم البنك'
        },
        'account_holder': {
            'ua': 'Введіть ім\'я власника рахунку',
            'de': 'Geben Sie den Namen des Kontoinhabers ein',
            'en': 'Enter account holder name',
            'pl': 'Wpisz nazwę właściciela konta',
            'tr': 'Hesap sahibinin adını girin',
            'ar': 'أدخل اسم صاحب الحساب'
        },
        
        # === CHILD DATA (Angaben zum Kind) ===
        'child_first_name': {
            'ua': 'Введіть ім\'я дитини',
            'de': 'Geben Sie den Vornamen des Kindes ein',
            'en': 'Enter child\'s first name',
            'pl': 'Wpisz imię dziecka',
            'tr': 'Çocuğun adını girin',
            'ar': 'أدخل الاسم الأول للطفل'
        },
        'child_last_name': {
            'ua': 'Введіть прізвище дитини',
            'de': 'Geben Sie den Nachnamen des Kindes ein',
            'en': 'Enter child\'s last name',
            'pl': 'Wpisz nazwisko dziecka',
            'tr': 'Çocuğun soyadını girin',
            'ar': 'أدخل اسم عائلة الطفل'
        },
        'child_name': {
            'ua': 'Введіть повне ім\'я дитини',
            'de': 'Geben Sie den vollständigen Namen des Kindes ein',
            'en': 'Enter child\'s full name',
            'pl': 'Wpisz pełne imię i nazwisko dziecka',
            'tr': 'Çocuğun tam adını girin',
            'ar': 'أدخل الاسم الكامل للطفل'
        },
        'child_birth_date': {
            'ua': 'Введіть дату народження дитини (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Geburtsdatum des Kindes ein (TT.MM.JJJJ)',
            'en': 'Enter child\'s date of birth (DD.MM.YYYY)',
            'pl': 'Wpisz datę urodzenia dziecka (DD.MM.RRRR)',
            'tr': 'Çocuğun doğum tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ ميلاد الطفل'
        },
        'child_birth_place': {
            'ua': 'Введіть місце народження дитини',
            'de': 'Geben Sie den Geburtsort des Kindes ein',
            'en': 'Enter child\'s place of birth',
            'pl': 'Wpisz miejsce urodzenia dziecka',
            'tr': 'Çocuğun doğum yerini girin',
            'ar': 'أدخل مكان ولادة الطفل'
        },
        'child_nationality': {
            'ua': 'Введіть громадянство дитини',
            'de': 'Geben Sie die Staatsangehörigkeit des Kindes ein',
            'en': 'Enter child\'s nationality',
            'pl': 'Wpisz obywatelstwo dziecka',
            'tr': 'Çocuğun vatandaşlığını girin',
            'ar': 'أدخل جنسية الطفل'
        },
        'child_gender': {
            'ua': 'Оберіть стать дитини (M/W/D)',
            'de': 'Wählen Sie das Geschlecht des Kindes (M/W/D)',
            'en': 'Select child\'s gender (M/W/D)',
            'pl': 'Wybierz płeć dziecka (M/W/D)',
            'tr': 'Çocuğun cinsiyetini seçin (M/W/D)',
            'ar': 'اختر جنس الطفل (M/W/D)'
        },
        'relationship_to_child': {
            'ua': 'Вкажіть ваше відношення до дитини (мати/батько/опікун)',
            'de': 'Geben Sie Ihr Verhältnis zum Kind an (Mutter/Vater/Vormund)',
            'en': 'Specify your relationship to the child (mother/father/guardian)',
            'pl': 'Podaj swój stosunek do dziecka (matka/ojciec/opiekun)',
            'tr': 'Çocukla ilişkinizi belirtin (anne/baba/vasi)',
            'ar': 'حدد علاقتك بالطفل (أم/أب/وصي)'
        },
        'child_lives_in_household': {
            'ua': 'Чи проживає дитина у вашому домогосподарстві? (Ja/Nein)',
            'de': 'Lebt das Kind in Ihrem Haushalt? (Ja/Nein)',
            'en': 'Does the child live in your household? (Ja/Nein)',
            'pl': 'Czy dziecko mieszka w twoim gospodarstwie domowym? (Ja/Nein)',
            'tr': 'Çocuk sizin hanenizde mi yaşıyor? (Ja/Nein)',
            'ar': 'هل يعيش الطفل في منزلك؟ (Ja/Nein)'
        },
        
        # === SPOUSE/PARTNER (Ehepartner/Lebenspartner) ===
        'spouse_first_name': {
            'ua': 'Введіть ім\'я партнера/дружини/чоловіка',
            'de': 'Geben Sie den Vornamen des Ehepartners/Lebenspartners ein',
            'en': 'Enter spouse/partner\'s first name',
            'pl': 'Wpisz imię małżonka/partnera',
            'tr': 'Eşinizin/partnerinizin adını girin',
            'ar': 'أدخل الاسم الأول للزوج/الشريك'
        },
        'spouse_last_name': {
            'ua': 'Введіть прізвище партнера/дружини/чоловіка',
            'de': 'Geben Sie den Nachnamen des Ehepartners/Lebenspartners ein',
            'en': 'Enter spouse/partner\'s last name',
            'pl': 'Wpisz nazwisko małżonka/partnera',
            'tr': 'Eşinizin/partnerinizin soyadını girin',
            'ar': 'أدخل اسم عائلة الزوج/الشريك'
        },
        'spouse_birth_date': {
            'ua': 'Введіть дату народження партнера (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Geburtsdatum des Ehepartners ein (TT.MM.JJJJ)',
            'en': 'Enter spouse\'s date of birth (DD.MM.YYYY)',
            'pl': 'Wpisz datę urodzenia małżonka (DD.MM.RRRR)',
            'tr': 'Eşinizin doğum tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ ميلاد الزوج/الشريك'
        },
        'spouse_tax_id': {
            'ua': 'Введіть податковий номер партнера (IdNr)',
            'de': 'Geben Sie die Steuer-ID des Ehepartners ein (IdNr)',
            'en': 'Enter spouse\'s tax ID (IdNr)',
            'pl': 'Wpisz numer podatkowy małżonka (IdNr)',
            'tr': 'Eşinizin vergi kimlik numarasını girin (IdNr)',
            'ar': 'أدخل الرقم الضريبي للزوج/الشريك'
        },
        'marriage_date': {
            'ua': 'Введіть дату одруження (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Heiratsdatum ein (TT.MM.JJJJ)',
            'en': 'Enter marriage date (DD.MM.YYYY)',
            'pl': 'Wpisz datę ślubu (DD.MM.RRRR)',
            'tr': 'Evlilik tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ الزواج'
        },
        
        # === HOUSING (Wohnung) ===
        'move_in_date': {
            'ua': 'Введіть дату заселення (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Einzugsdatum ein (TT.MM.JJJJ)',
            'en': 'Enter move-in date (DD.MM.YYYY)',
            'pl': 'Wpisz datę wprowadzenia się (DD.MM.RRRR)',
            'tr': 'Taşınma tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ الانتقال'
        },
        'move_out_date': {
            'ua': 'Введіть дату виселення (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Auszugsdatum ein (TT.MM.JJJJ)',
            'en': 'Enter move-out date (DD.MM.YYYY)',
            'pl': 'Wpisz datę wyprowadzki (DD.MM.RRRR)',
            'tr': 'Taşınma (çıkış) tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ المغادرة'
        },
        'previous_address': {
            'ua': 'Введіть попередню адресу',
            'de': 'Geben Sie die vorherige Adresse ein',
            'en': 'Enter previous address',
            'pl': 'Wpisz poprzedni adres',
            'tr': 'Önceki adresinizi girin',
            'ar': 'أدخل العنوان السابق'
        },
        'landlord_name': {
            'ua': 'Введіть ім\'я власника житла / орендодавця',
            'de': 'Geben Sie den Namen des Vermieters ein',
            'en': 'Enter landlord\'s name',
            'pl': 'Wpisz nazwę wynajmującego',
            'tr': 'Ev sahibinin adını girin',
            'ar': 'أدخل اسم المالك/المؤجر'
        },
        'landlord_address': {
            'ua': 'Введіть адресу власника житла',
            'de': 'Geben Sie die Adresse des Vermieters ein',
            'en': 'Enter landlord\'s address',
            'pl': 'Wpisz adres wynajmującego',
            'tr': 'Ev sahibinin adresini girin',
            'ar': 'أدخل عنوان المالك'
        },
        'wgb_is_not_eigentuemer': {
            'ua': 'Оберіть, якщо орендодавець не є власником квартири',
            'de': 'Wählen Sie, wenn der Wohnungsgeber nicht der Eigentümer ist',
            'en': 'Select if the landlord is not the property owner',
            'pl': 'Wybierz, jeśli wynajmujący nie jest właścicielem',
            'tr': 'Kiraya veren mülk sahibi değilse seçin',
            'ar': 'اختر إذا كان المؤجر ليس مالك العقار'
        },
        'wgb_owner_name': {
            'ua': 'Повне ім\'я та прізвище власника квартири',
            'de': 'Vollständiger Name des Eigentümers der Wohnung',
            'en': 'Full name of the property owner',
            'pl': 'Pełne imię i nazwisko właściciela nieruchomości',
            'tr': 'Mülk sahibinin tam adı',
            'ar': 'الاسم الكامل لمالك العقار'
        },
        'wgb_owner_address': {
            'ua': 'Адреса власника: вулиця, номер, індекс, місто',
            'de': 'Anschrift des Eigentümers: Straße, Hausnummer, PLZ, Ort',
            'en': 'Owner\'s address: street, house number, postal code, city',
            'pl': 'Adres właściciela: ulica, numer, kod pocztowy, miasto',
            'tr': 'Mülk sahibinin adresi: sokak, numara, posta kodu, şehir',
            'ar': 'عنوان المالك: الشارع، الرقم، الرمز البريدي، المدينة'
        },
        'rent_amount': {
            'ua': 'Введіть суму оренди (EUR на місяць)',
            'de': 'Geben Sie die Miethöhe ein (EUR pro Monat)',
            'en': 'Enter rent amount (EUR per month)',
            'pl': 'Wpisz wysokość czynszu (EUR miesięcznie)',
            'tr': 'Kira tutarını girin (aylık EUR)',
            'ar': 'أدخل مبلغ الإيجار (يورو شهرياً)'
        },
        'living_space': {
            'ua': 'Введіть площу житла (м²)',
            'de': 'Geben Sie die Wohnfläche ein (m²)',
            'en': 'Enter living space (m²)',
            'pl': 'Wpisz powierzchnię mieszkalną (m²)',
            'tr': 'Yaşam alanını girin (m²)',
            'ar': 'أدخل مساحة المعيشة (م²)'
        },
        'number_of_rooms': {
            'ua': 'Введіть кількість кімнат',
            'de': 'Geben Sie die Anzahl der Zimmer ein',
            'en': 'Enter number of rooms',
            'pl': 'Wpisz liczbę pokoi',
            'tr': 'Oda sayısını girin',
            'ar': 'أدخل عدد الغرف'
        },
        'household_members': {
            'ua': 'Введіть кількість членів домогосподарства',
            'de': 'Geben Sie die Anzahl der Haushaltsmitglieder ein',
            'en': 'Enter number of household members',
            'pl': 'Wpisz liczbę członków gospodarstwa domowego',
            'tr': 'Hane halkı sayısını girin',
            'ar': 'أدخل عدد أفراد الأسرة'
        },
        
        # === EMPLOYMENT (Beschäftigung) ===
        'employer_name': {
            'ua': 'Введіть назву роботодавця',
            'de': 'Geben Sie den Namen des Arbeitgebers ein',
            'en': 'Enter employer\'s name',
            'pl': 'Wpisz nazwę pracodawcy',
            'tr': 'İşveren adını girin',
            'ar': 'أدخل اسم صاحب العمل'
        },
        'employer_address': {
            'ua': 'Введіть адресу роботодавця',
            'de': 'Geben Sie die Adresse des Arbeitgebers ein',
            'en': 'Enter employer\'s address',
            'pl': 'Wpisz adres pracodawcy',
            'tr': 'İşveren adresini girin',
            'ar': 'أدخل عنوان صاحب العمل'
        },
        'employment_start_date': {
            'ua': 'Введіть дату початку роботи (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Datum des Arbeitsbeginns ein (TT.MM.JJJJ)',
            'en': 'Enter employment start date (DD.MM.YYYY)',
            'pl': 'Wpisz datę rozpoczęcia pracy (DD.MM.RRRR)',
            'tr': 'İşe başlama tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ بدء العمل'
        },
        'occupation': {
            'ua': 'Введіть вашу професію',
            'de': 'Geben Sie Ihren Beruf ein',
            'en': 'Enter your occupation',
            'pl': 'Wpisz swój zawód',
            'tr': 'Mesleğinizi girin',
            'ar': 'أدخل مهنتك'
        },
        'monthly_income': {
            'ua': 'Введіть місячний дохід брутто (EUR)',
            'de': 'Geben Sie das monatliche Bruttoeinkommen ein (EUR)',
            'en': 'Enter monthly gross income (EUR)',
            'pl': 'Wpisz miesięczny dochód brutto (EUR)',
            'tr': 'Aylık brüt geliri girin (EUR)',
            'ar': 'أدخل الدخل الشهري الإجمالي (يورو)'
        },
        
        # === DATES (Verschiedene Daten) ===
        'application_date': {
            'ua': 'Введіть дату подання заяви (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Antragsdatum ein (TT.MM.JJJJ)',
            'en': 'Enter application date (DD.MM.YYYY)',
            'pl': 'Wpisz datę złożenia wniosku (DD.MM.RRRR)',
            'tr': 'Başvuru tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ تقديم الطلب'
        },
        'start_date': {
            'ua': 'Введіть дату початку (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Startdatum ein (TT.MM.JJJJ)',
            'en': 'Enter start date (DD.MM.YYYY)',
            'pl': 'Wpisz datę rozpoczęcia (DD.MM.RRRR)',
            'tr': 'Başlangıç tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ البدء'
        },
        'end_date': {
            'ua': 'Введіть дату закінчення (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Enddatum ein (TT.MM.JJJJ)',
            'en': 'Enter end date (DD.MM.YYYY)',
            'pl': 'Wpisz datę zakończenia (DD.MM.RRRR)',
            'tr': 'Bitiş tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ الانتهاء'
        },
        
        # === SIGNATURE (Unterschrift) ===
        'signature_place': {
            'ua': 'Введіть місце підпису (місто)',
            'de': 'Geben Sie den Ort der Unterschrift ein (Stadt)',
            'en': 'Enter signature place (city)',
            'pl': 'Wpisz miejsce podpisu (miasto)',
            'tr': 'İmza yerini girin (şehir)',
            'ar': 'أدخل مكان التوقيع (المدينة)'
        },
        'signature_date': {
            'ua': 'Введіть дату підпису (ДД.ММ.РРРР)',
            'de': 'Geben Sie das Datum der Unterschrift ein (TT.MM.JJJJ)',
            'en': 'Enter signature date (DD.MM.YYYY)',
            'pl': 'Wpisz datę podpisu (DD.MM.RRRR)',
            'tr': 'İmza tarihini girin (GG.AA.YYYY)',
            'ar': 'أدخل تاريخ التوقيع'
        },
        
        # === OTHER (Sonstiges) ===
        'notes': {
            'ua': 'Додаткові примітки (опціонально)',
            'de': 'Zusätzliche Anmerkungen (optional)',
            'en': 'Additional notes (optional)',
            'pl': 'Dodatkowe uwagi (opcjonalnie)',
            'tr': 'Ek notlar (isteğe bağlı)',
            'ar': 'ملاحظات إضافية (اختياري)'
        },
        'reason': {
            'ua': 'Вкажіть причину / підставу',
            'de': 'Geben Sie den Grund an',
            'en': 'Specify the reason',
            'pl': 'Podaj powód',
            'tr': 'Nedeni belirtin',
            'ar': 'حدد السبب'
        },
    },
    
    # ========================================================================
    # VALIDATION MESSAGES
    # ========================================================================
    
    'validation': {
        'empty_field': {
            'ua': '❌ Поле не може бути порожнім',
            'de': '❌ Das Feld darf nicht leer sein',
            'en': '❌ Field cannot be empty',
            'pl': '❌ Pole nie może być puste',
            'tr': '❌ Alan boş olamaz',
            'ar': '❌ لا يمكن أن يكون الحقل فارغاً'
        },
        'invalid_iban': {
            'ua': '❌ Невірний формат IBAN. Приклад: DE89 3704 0044 0532 0130 00',
            'de': '❌ Ungültiges IBAN-Format. Beispiel: DE89 3704 0044 0532 0130 00',
            'en': '❌ Invalid IBAN format. Example: DE89 3704 0044 0532 0130 00',
            'pl': '❌ Nieprawidłowy format IBAN. Przykład: DE89 3704 0044 0532 0130 00',
            'tr': '❌ Geçersiz IBAN formatı. Örnek: DE89 3704 0044 0532 0130 00',
            'ar': '❌ تنسيق IBAN غير صالح. مثال: DE89 3704 0044 0532 0130 00'
        },
        'invalid_tax_id': {
            'ua': '❌ Невірний формат ідентифікаційного номера (IdNr). Має містити 11 цифр.',
            'de': '❌ Ungültiges Format der Steuer-ID (IdNr). Muss 11 Ziffern enthalten.',
            'en': '❌ Invalid Tax ID (IdNr) format. Must contain 11 digits.',
            'pl': '❌ Nieprawidłowy format numeru podatkowego (IdNr). Musi zawierać 11 cyfr.',
            'tr': '❌ Geçersiz Vergi Kimlik Numarası (IdNr) formatı. 11 rakam içermelidir.',
            'ar': '❌ تنسيق رقم التعريف الضريبي (IdNr) غير صالح. يجب أن يحتوي على 11 رقماً.'
        },
        'invalid_date': {
            'ua': '❌ Невірний формат дати. Використовуйте: ДД.ММ.РРРР (наприклад: 15.03.1990)',
            'de': '❌ Ungültiges Datumsformat. Verwenden Sie: TT.MM.JJJJ (Beispiel: 15.03.1990)',
            'en': '❌ Invalid date format. Use: DD.MM.YYYY (example: 15.03.1990)',
            'pl': '❌ Nieprawidłowy format daty. Użyj: DD.MM.RRRR (przykład: 15.03.1990)',
            'tr': '❌ Geçersiz tarih formatı. Kullanın: GG.AA.YYYY (örnek: 15.03.1990)',
            'ar': '❌ تنسيق التاريخ غير صالح. استخدم: يوم.شهر.سنة (مثال: 15.03.1990)'
        },
        'invalid_plz': {
            'ua': '❌ Невірний німецький поштовий індекс. Має містити 5 цифр.',
            'de': '❌ Ungültige deutsche Postleitzahl. Muss 5 Ziffern enthalten.',
            'en': '❌ Invalid German postal code. Must contain 5 digits.',
            'pl': '❌ Nieprawidłowy niemiecki kod pocztowy. Musi zawierać 5 cyfr.',
            'tr': '❌ Geçersiz Alman posta kodu. 5 rakam içermelidir.',
            'ar': '❌ الرمز البريدي الألماني غير صالح. يجب أن يحتوي على 5 أرقام.'
        },
        'invalid_phone': {
            'ua': '❌ Невірний формат телефону. Приклад: +49 30 12345678',
            'de': '❌ Ungültiges Telefonformat. Beispiel: +49 30 12345678',
            'en': '❌ Invalid phone format. Example: +49 30 12345678',
            'pl': '❌ Nieprawidłowy format telefonu. Przykład: +49 30 12345678',
            'tr': '❌ Geçersiz telefon formatı. Örnek: +49 30 12345678',
            'ar': '❌ تنسيق الهاتف غير صالح. مثال: +49 30 12345678'
        },
        'invalid_email': {
            'ua': '❌ Невірний формат email. Приклад: name@example.com',
            'de': '❌ Ungültiges E-Mail-Format. Beispiel: name@example.com',
            'en': '❌ Invalid email format. Example: name@example.com',
            'pl': '❌ Nieprawidłowy format e-mail. Przykład: name@example.com',
            'tr': '❌ Geçersiz e-posta formatı. Örnek: name@example.com',
            'ar': '❌ تنسيق البريد الإلكتروني غير صالح. مثال: name@example.com'
        },
        'use_latin': {
            'ua': '⚠️ <b>Увага!</b> Німецькі документи заповнюються латиницею.\n\nНадішліть латиницею або напишіть <b>OK</b> для автоматичної транслітерації.',
            'de': '⚠️ <b>Achtung!</b> Deutsche Dokumente werden in Lateinschrift ausgefüllt.\n\nSenden Sie in Lateinschrift oder schreiben Sie <b>OK</b> für automatische Transliteration.',
            'en': '⚠️ <b>Warning!</b> German documents are filled in Latin script.\n\nSend in Latin or type <b>OK</b> for automatic transliteration.',
            'pl': '⚠️ <b>Uwaga!</b> Dokumenty niemieckie wypełnia się alfabetem łacińskim.\n\nWyślij łaciński lub wpisz <b>OK</b> dla automatycznej transliteracji.',
            'tr': '⚠️ <b>Dikkat!</b> Alman belgeleri Latin alfabesiyle doldurulur.\n\nLatin alfabesiyle gönderin veya otomatik transliterasyon için <b>OK</b> yazın.',
            'ar': '⚠️ <b>تحذير!</b> تُملأ المستندات الألمانية بالحروف اللاتينية.\n\nأرسل باللاتينية أو اكتب <b>OK</b> للتحويل التلقائي.'
        },
        'future_date_not_allowed': {
            'ua': '❌ Дата не може бути в майбутньому для цього поля',
            'de': '❌ Das Datum darf für dieses Feld nicht in der Zukunft liegen',
            'en': '❌ Date cannot be in the future for this field',
            'pl': '❌ Data nie może być w przyszłości dla tego pola',
            'tr': '❌ Bu alan için tarih gelecekte olamaz',
            'ar': '❌ لا يمكن أن يكون التاريخ في المستقبل لهذا الحقل'
        },
        'age_too_young': {
            'ua': '❌ Вік занадто малий. Перевірте дату народження.',
            'de': '❌ Alter zu jung. Bitte überprüfen Sie das Geburtsdatum.',
            'en': '❌ Age too young. Please check the birth date.',
            'pl': '❌ Zbyt młody wiek. Sprawdź datę urodzenia.',
            'tr': '❌ Yaş çok küçük. Lütfen doğum tarihini kontrol edin.',
            'ar': '❌ العمر صغير جداً. يرجى التحقق من تاريخ الميلاد.'
        },
        'valid': {
            'ua': '✅ Дані прийнято',
            'de': '✅ Daten akzeptiert',
            'en': '✅ Data accepted',
            'pl': '✅ Dane zaakceptowane',
            'tr': '✅ Veriler kabul edildi',
            'ar': '✅ تم قبول البيانات'
        },
    },
    
    # ========================================================================
    # COVER LETTER TEMPLATES
    # ========================================================================
    
    'cover_letter': {
        'header': {
            'ua': 'Супровідний лист (Anschreiben)',
            'de': 'Anschreiben',
            'en': 'Cover Letter',
            'pl': 'List przewodni',
            'tr': 'Kapak Mektubu',
            'ar': 'خطاب التغطية'
        },
        'subject_kindergeld': {
            'de': 'Antrag auf Kindergeld',
            'ua': 'Заява на отримання Kindergeld',
            'en': 'Application for Child Benefit',
        },
        'subject_anmeldung': {
            'de': 'Anmeldung einer Wohnung',
            'ua': 'Реєстрація за місцем проживання',
            'en': 'Registration of Residence',
        },
        'subject_wohngeld': {
            'de': 'Antrag auf Wohngeld',
            'ua': 'Заява на житлову допомогу',
            'en': 'Application for Housing Benefit',
        },
        'greeting': {
            'de': 'Sehr geehrte Damen und Herren,',
            'ua': 'Шановні пані та панове,',
            'en': 'Dear Sir or Madam,',
            'pl': 'Szanowni Państwo,',
            'tr': 'Sayın Yetkili,',
            'ar': 'السادة المحترمون،'
        },
        'closing': {
            'de': 'Mit freundlichen Grüßen',
            'ua': 'З повагою',
            'en': 'Yours faithfully',
            'pl': 'Z poważaniem',
            'tr': 'Saygılarımla',
            'ar': 'مع فائق الاحترام'
        },
        'attachments': {
            'de': 'Anlagen',
            'ua': 'Додатки',
            'en': 'Attachments',
            'pl': 'Załączniki',
            'tr': 'Ekler',
            'ar': 'المرفقات'
        },
    },
    
    # ========================================================================
    # DOCUMENT TYPE NAMES (doc_ prefixed for auto-generation)
    # ========================================================================
    
    # Family Benefits
    'doc_kindergeld': {
        'ua': '👶 Kindergeld (Дитяча допомога)',
        'de': '👶 Kindergeld',
        'en': '👶 Child Benefit (Kindergeld)',
        'pl': '👶 Kindergeld (Zasiłek na dzieci)',
        'tr': '👶 Kindergeld (Çocuk Parası)',
        'ar': '👶 إعانة الأطفال (Kindergeld)'
    },
    'doc_kinderzuschlag': {
        'ua': '💰 Kinderzuschlag (Дитяча надбавка)',
        'de': '💰 Kinderzuschlag',
        'en': '💰 Child Supplement',
        'pl': '💰 Kinderzuschlag (Dodatek na dzieci)',
        'tr': '💰 Kinderzuschlag (Çocuk Ek Parası)',
        'ar': '💰 علاوة الأطفال (Kinderzuschlag)'
    },
    'doc_elterngeld': {
        'ua': '👨‍👩‍👧 Elterngeld (Батьківська допомога)',
        'de': '👨‍👩‍👧 Elterngeld',
        'en': '👨‍👩‍👧 Parental Allowance',
        'pl': '👨‍👩‍👧 Elterngeld (Zasiłek rodzicielski)',
        'tr': '👨‍👩‍👧 Elterngeld (Ebeveyn Parası)',
        'ar': '👨‍👩‍👧 بدل الوالدين (Elterngeld)'
    },
    'doc_unterhaltsvorschuss': {
        'ua': '💳 Unterhaltsvorschuss (Аванс на утримання)',
        'de': '💳 Unterhaltsvorschuss',
        'en': '💳 Maintenance Advance',
        'pl': '💳 Unterhaltsvorschuss (Zaliczka alimentacyjna)',
        'tr': '💳 Unterhaltsvorschuss (Nafaka Avansı)',
        'ar': '💳 سلفة النفقة (Unterhaltsvorschuss)'
    },
    
    # Housing & Registration
    'doc_anmeldung': {
        'ua': '🏠 Anmeldung (Реєстрація)',
        'de': '🏠 Anmeldung',
        'en': '🏠 Registration',
        'pl': '🏠 Anmeldung (Zameldowanie)',
        'tr': '🏠 Anmeldung (Kayıt)',
        'ar': '🏠 تسجيل الإقامة (Anmeldung)'
    },
    'doc_ummeldung': {
        'ua': '🔄 Ummeldung (Перереєстрація)',
        'de': '🔄 Ummeldung',
        'en': '🔄 Re-registration',
        'pl': '🔄 Ummeldung (Przemeldowanie)',
        'tr': '🔄 Ummeldung (Yeniden Kayıt)',
        'ar': '🔄 إعادة التسجيل (Ummeldung)'
    },
    'doc_abmeldung': {
        'ua': '📤 Abmeldung (Зняття з реєстрації)',
        'de': '📤 Abmeldung',
        'en': '📤 Deregistration',
        'pl': '📤 Abmeldung (Wymeldowanie)',
        'tr': '📤 Abmeldung (Kayıt Silme)',
        'ar': '📤 إلغاء التسجيل (Abmeldung)'
    },
    'doc_wohnungsgeberbestaetigung': {
        'ua': '📋 Wohnungsgeberbestätigung (Підтвердження від орендодавця)',
        'de': '📋 Wohnungsgeberbestätigung',
        'en': '📋 Landlord Confirmation',
        'pl': '📋 Wohnungsgeberbestätigung (Potwierdzenie od wynajmującego)',
        'tr': '📋 Wohnungsgeberbestätigung (Ev Sahibi Onayı)',
        'ar': '📋 تأكيد المالك (Wohnungsgeberbestätigung)'
    },
    'doc_wohngeld': {
        'ua': '🏘️ Wohngeld (Житлова допомога)',
        'de': '🏘️ Wohngeld',
        'en': '🏘️ Housing Benefit',
        'pl': '🏘️ Wohngeld (Dodatek mieszkaniowy)',
        'tr': '🏘️ Wohngeld (Konut Yardımı)',
        'ar': '🏘️ بدل السكن (Wohngeld)'
    },
    
    # Tax & Finance
    'doc_steuererklaerung': {
        'ua': '📊 Steuererklärung (Податкова декларація)',
        'de': '📊 Steuererklärung',
        'en': '📊 Tax Return',
        'pl': '📊 Steuererklärung (Zeznanie podatkowe)',
        'tr': '📊 Steuererklärung (Vergi Beyannamesi)',
        'ar': '📊 الإقرار الضريبي (Steuererklärung)'
    },
    'doc_steuerklassenwechsel': {
        'ua': '🔢 Steuerklassenwechsel (Зміна податкового класу)',
        'de': '🔢 Steuerklassenwechsel',
        'en': '🔢 Tax Class Change',
        'pl': '🔢 Steuerklassenwechsel (Zmiana klasy podatkowej)',
        'tr': '🔢 Steuerklassenwechsel (Vergi Sınıfı Değişikliği)',
        'ar': '🔢 تغيير الفئة الضريبية'
    },
    
    # Social Benefits
    'doc_buergergeld': {
        'ua': '💶 Bürgergeld (Громадянський дохід)',
        'de': '💶 Bürgergeld',
        'en': '💶 Citizen\'s Benefit',
        'pl': '💶 Bürgergeld (Dochód obywatelski)',
        'tr': '💶 Bürgergeld (Vatandaş Geliri)',
        'ar': '💶 دخل المواطن (Bürgergeld)'
    },
    'doc_arbeitslosengeld': {
        'ua': '📉 Arbeitslosengeld (Допомога по безробіттю)',
        'de': '📉 Arbeitslosengeld',
        'en': '📉 Unemployment Benefit',
        'pl': '📉 Arbeitslosengeld (Zasiłek dla bezrobotnych)',
        'tr': '📉 Arbeitslosengeld (İşsizlik Maaşı)',
        'ar': '📉 إعانة البطالة (Arbeitslosengeld)'
    },
    'doc_bildungspaket': {
        'ua': '📚 Bildungspaket (Освітній пакет)',
        'de': '📚 Bildungs- und Teilhabepaket',
        'en': '📚 Education Package',
        'pl': '📚 Bildungspaket (Pakiet edukacyjny)',
        'tr': '📚 Bildungspaket (Eğitim Paketi)',
        'ar': '📚 حزمة التعليم (Bildungspaket)'
    },
    
    # Documents & IDs
    'doc_fuehrerschein': {
        'ua': '🚗 Führerschein (Посвідчення водія)',
        'de': '🚗 Führerschein',
        'en': '🚗 Driving License',
        'pl': '🚗 Führerschein (Prawo jazdy)',
        'tr': '🚗 Führerschein (Ehliyet)',
        'ar': '🚗 رخصة القيادة (Führerschein)'
    },
    'doc_personalausweis': {
        'ua': '🪪 Personalausweis (Посвідчення особи)',
        'de': '🪪 Personalausweis',
        'en': '🪪 ID Card',
        'pl': '🪪 Personalausweis (Dowód osobisty)',
        'tr': '🪪 Personalausweis (Kimlik Kartı)',
        'ar': '🪪 بطاقة الهوية (Personalausweis)'
    },
    'doc_reisepass': {
        'ua': '🛂 Reisepass (Закордонний паспорт)',
        'de': '🛂 Reisepass',
        'en': '🛂 Passport',
        'pl': '🛂 Reisepass (Paszport)',
        'tr': '🛂 Reisepass (Pasaport)',
        'ar': '🛂 جواز السفر (Reisepass)'
    },
    
    # Health & Insurance
    'doc_krankenversicherung': {
        'ua': '🏥 Krankenversicherung (Медичне страхування)',
        'de': '🏥 Krankenversicherung',
        'en': '🏥 Health Insurance',
        'pl': '🏥 Krankenversicherung (Ubezpieczenie zdrowotne)',
        'tr': '🏥 Krankenversicherung (Sağlık Sigortası)',
        'ar': '🏥 التأمين الصحي (Krankenversicherung)'
    },
    'doc_pflegegeld': {
        'ua': '🩺 Pflegegeld (Допомога по догляду)',
        'de': '🩺 Pflegegeld',
        'en': '🩺 Care Allowance',
        'pl': '🩺 Pflegegeld (Zasiłek opiekuńczy)',
        'tr': '🩺 Pflegegeld (Bakım Parası)',
        'ar': '🩺 بدل الرعاية (Pflegegeld)'
    },
    
    # Work & Business
    'doc_gewerbeanmeldung': {
        'ua': '🏢 Gewerbeanmeldung (Реєстрація бізнесу)',
        'de': '🏢 Gewerbeanmeldung',
        'en': '🏢 Business Registration',
        'pl': '🏢 Gewerbeanmeldung (Rejestracja działalności)',
        'tr': '🏢 Gewerbeanmeldung (İşletme Kaydı)',
        'ar': '🏢 تسجيل الأعمال (Gewerbeanmeldung)'
    },
    'doc_arbeitserlaubnis': {
        'ua': '💼 Arbeitserlaubnis (Дозвіл на роботу)',
        'de': '💼 Arbeitserlaubnis',
        'en': '💼 Work Permit',
        'pl': '💼 Arbeitserlaubnis (Pozwolenie na pracę)',
        'tr': '💼 Arbeitserlaubnis (Çalışma İzni)',
        'ar': '💼 تصريح العمل (Arbeitserlaubnis)'
    },
    
    # Other
    'doc_vollmacht': {
        'ua': '📜 Vollmacht (Довіреність)',
        'de': '📜 Vollmacht',
        'en': '📜 Power of Attorney',
        'pl': '📜 Vollmacht (Pełnomocnictwo)',
        'tr': '📜 Vollmacht (Vekaletname)',
        'ar': '📜 التوكيل (Vollmacht)'
    },
    'doc_kuendigung': {
        'ua': '✉️ Kündigung (Розірвання договору)',
        'de': '✉️ Kündigung',
        'en': '✉️ Termination Notice',
        'pl': '✉️ Kündigung (Wypowiedzenie)',
        'tr': '✉️ Kündigung (Fesih)',
        'ar': '✉️ إشعار الإنهاء (Kündigung)'
    },
    'doc_einbuergerung': {
        'ua': '🇩🇪 Einbürgerung (Натуралізація)',
        'de': '🇩🇪 Einbürgerung',
        'en': '🇩🇪 Naturalization',
        'pl': '🇩🇪 Einbürgerung (Naturalizacja)',
        'tr': '🇩🇪 Einbürgerung (Vatandaşlık)',
        'ar': '🇩🇪 التجنس (Einbürgerung)'
    },
    'doc_rundfunkbeitrag': {
        'ua': '📺 Rundfunkbeitrag (Радіовнесок)',
        'de': '📺 Rundfunkbeitrag',
        'en': '📺 Broadcasting Fee',
        'pl': '📺 Rundfunkbeitrag (Abonament radiowo-telewizyjny)',
        'tr': '📺 Rundfunkbeitrag (Yayın Ücreti)',
        'ar': '📺 رسوم البث (Rundfunkbeitrag)'
    },

    # ========================================================================
    # POST-PAYMENT / RECEIPT
    # ========================================================================

    'payment_confirmed': {
        'ua': '✅ <b>Оплата підтверджена</b>',
        'de': '✅ <b>Zahlung bestätigt</b>',
        'en': '✅ <b>Payment confirmed</b>',
        'pl': '✅ <b>Płatność potwierdzona</b>',
        'tr': '✅ <b>Ödeme onaylandı</b>',
        'ar': '✅ <b>تم تأكيد الدفع</b>',
    },

    'document_ready': {
        'ua': '✅ Ваш документ готовий',
        'de': '✅ Ihr Dokument ist fertig',
        'en': '✅ Your document is ready',
        'pl': '✅ Twój dokument jest gotowy',
        'tr': '✅ Belgeniz hazır',
        'ar': '✅ مستندك جاهز',
    },

    'email_sent': {
        'ua': '📧 Надіслано на {email}',
        'de': '📧 Gesendet an {email}',
        'en': '📧 Sent to {email}',
        'pl': '📧 Wysłano na {email}',
        'tr': '📧 {email} adresine gönderildi',
        'ar': '📧 أُرسل إلى {email}',
    },

    'email_failed': {
        'ua': '📧 Email: не вдалося надіслати',
        'de': '📧 E-Mail: Versand fehlgeschlagen',
        'en': '📧 Email: delivery failed',
        'pl': '📧 Email: wysyłka nie powiodła się',
        'tr': '📧 E-posta: gönderilemedi',
        'ar': '📧 البريد: فشل التسليم',
    },

    'no_email_provided': {
        'ua': (
            '⚠️ Не вдалося надіслати документ на email — адреса не була вказана під час оплати.\n'
            'Ви можете завантажити документ прямо тут.'
        ),
        'de': (
            '⚠️ Das Dokument konnte nicht per E-Mail gesendet werden — beim Bezahlen wurde keine E-Mail-Adresse angegeben.\n'
            'Sie können das Dokument hier herunterladen.'
        ),
        'en': (
            '⚠️ We couldn\'t send the document by email — no email was provided during payment.\n'
            'You can download the document directly here.'
        ),
        'pl': (
            '⚠️ Nie udało się wysłać dokumentu na email — nie podano adresu podczas płatności.\n'
            'Możesz pobrać dokument bezpośrednio tutaj.'
        ),
        'tr': (
            '⚠️ Belge e-posta ile gönderilemedi — ödeme sırasında e-posta adresi girilmedi.\n'
            'Belgeyi doğrudan buradan indirebilirsiniz.'
        ),
        'ar': (
            '⚠️ تعذّر إرسال المستند عبر البريد — لم يُقدَّم عنوان بريد إلكتروني أثناء الدفع.\n'
            'يمكنك تنزيل المستند مباشرة من هنا.'
        ),
    },

    # ========================================================================
    # PDF DELIVERY FAILURE
    # ========================================================================

    'delivery_failed': {
        'ua': (
            '⚠️ <b>Виникла проблема з доставкою документа.</b>\n\n'
            'Ваш платіж прийнято. Спробуйте отримати документ через /my_docs\n'
            'Якщо проблема залишається — напишіть у підтримку.'
        ),
        'de': (
            '⚠️ <b>Es gab ein Problem bei der Dokumentenzustellung.</b>\n\n'
            'Ihre Zahlung wurde empfangen. Verwenden Sie /my_docs um Ihr Dokument abzurufen.\n'
            'Wenn das Problem weiterhin besteht, kontaktieren Sie den Support.'
        ),
        'en': (
            '⚠️ <b>There was a problem delivering your document.</b>\n\n'
            'Your payment was received. Use /my_docs to retrieve your document.\n'
            'If the issue persists, please contact support.'
        ),
        'pl': (
            '⚠️ <b>Wystąpił problem z dostarczeniem dokumentu.</b>\n\n'
            'Twoja płatność została przyjęta. Użyj /my_docs aby pobrać dokument.\n'
            'Jeśli problem nadal występuje, skontaktuj się z pomocą.'
        ),
        'tr': (
            '⚠️ <b>Belge tesliminde bir sorun oluştu.</b>\n\n'
            'Ödemeniz alındı. Belgenizi almak için /my_docs kullanın.\n'
            'Sorun devam ederse lütfen destek ile iletişime geçin.'
        ),
        'ar': (
            '⚠️ <b>حدثت مشكلة في تسليم المستند.</b>\n\n'
            'تم استلام دفعتك. استخدم /my_docs لاسترداد مستندك.\n'
            'إذا استمرت المشكلة، يرجى التواصل مع الدعم.'
        ),
    },

    # ========================================================================
    # FORM & PREVIEW
    # ========================================================================

    'form_submitted': {
        'ua': '✅ <b>Форму відправлено!</b>\n\n⏳ Генеруємо попередній перегляд з вашими даними…',
        'de': '✅ <b>Formular abgeschickt!</b>\n\n⏳ Vorschau wird mit Ihren Daten erstellt…',
        'en': '✅ <b>Form submitted!</b>\n\n⏳ Generating your preview with your data…',
        'pl': '✅ <b>Formularz wysłany!</b>\n\n⏳ Generujemy podgląd z Twoimi danymi…',
        'tr': '✅ <b>Form gönderildi!</b>\n\n⏳ Verilerinizle önizleme oluşturuluyor…',
        'ar': '✅ <b>تم إرسال النموذج!</b>\n\n⏳ جارٍ إنشاء المعاينة ببياناتك…',
    },

    'generating_preview': {
        'ua': '⏳ Генеруємо попередній перегляд…',
        'de': '⏳ Vorschau wird erstellt…',
        'en': '⏳ Generating preview…',
        'pl': '⏳ Generowanie podglądu…',
        'tr': '⏳ Önizleme oluşturuluyor…',
        'ar': '⏳ جارٍ إنشاء المعاينة…',
    },

    'generating_document': {
        'ua': '⏳ Генеруємо ваш документ…',
        'de': '⏳ Ihr Dokument wird erstellt…',
        'en': '⏳ Generating your document…',
        'pl': '⏳ Generowanie dokumentu…',
        'tr': '⏳ Belgeniz oluşturuluyor…',
        'ar': '⏳ جارٍ إنشاء مستندك…',
    },

    # ========================================================================
    # /my_docs SCREEN
    # ========================================================================

    'my_documents_header': {
        'ua': '📂 <b>Ваші документи</b>',
        'de': '📂 <b>Ihre Dokumente</b>',
        'en': '📂 <b>Your documents</b>',
        'pl': '📂 <b>Twoje dokumenty</b>',
        'tr': '📂 <b>Belgeleriniz</b>',
        'ar': '📂 <b>مستنداتك</b>',
    },

    'no_documents': {
        'ua': 'У вас ще немає оплачених документів.\n\nНатисніть /start щоб замовити перший.',
        'de': 'Sie haben noch keine bezahlten Dokumente.\n\nTippen Sie /start um das erste zu bestellen.',
        'en': 'You have no paid documents yet.\n\nTap /start to order your first one.',
        'pl': 'Nie masz jeszcze opłaconych dokumentów.\n\nNaciśnij /start aby zamówić pierwszy.',
        'tr': 'Henüz ödenen belgeniz yok.\n\nİlkini sipariş etmek için /start\'a dokunun.',
        'ar': 'ليس لديك مستندات مدفوعة حتى الآن.\n\nاضغط /start لطلب أول مستند.',
    },

    'send_again': {
        'ua': '📄 Отримати знову',
        'de': '📄 Erneut senden',
        'en': '📄 Send again',
        'pl': '📄 Wyślij ponownie',
        'tr': '📄 Tekrar gönder',
        'ar': '📄 أعد الإرسال',
    },

    'main_menu_btn': {
        'ua': '🏠 Головне меню',
        'de': '🏠 Hauptmenü',
        'en': '🏠 Main menu',
        'pl': '🏠 Menu główne',
        'tr': '🏠 Ana menü',
        'ar': '🏠 القائمة الرئيسية',
    },

    # ========================================================================
    # PAYMENT SCREEN BUTTONS
    # ========================================================================

    'refresh_payment': {
        'ua': '🔄 Оновити посилання для оплати',
        'de': '🔄 Zahlungslink erneuern',
        'en': '🔄 Refresh payment link',
        'pl': '🔄 Odśwież link płatności',
        'tr': '🔄 Ödeme bağlantısını yenile',
        'ar': '🔄 تحديث رابط الدفع',
    },

    'try_again': {
        'ua': '🔁 Спробувати ще раз',
        'de': '🔁 Erneut versuchen',
        'en': '🔁 Try again',
        'pl': '🔁 Spróbuj ponownie',
        'tr': '🔁 Tekrar dene',
        'ar': '🔁 حاول مرة أخرى',
    },

    'payment_session_failed': {
        'ua': '⚠️ Не вдалося створити платіжну сесію. Спробуйте ще раз.',
        'de': '⚠️ Zahlungssitzung konnte nicht erstellt werden. Bitte versuchen Sie es erneut.',
        'en': '⚠️ Could not create a payment session. Please try again.',
        'pl': '⚠️ Nie udało się utworzyć sesji płatności. Spróbuj ponownie.',
        'tr': '⚠️ Ödeme oturumu oluşturulamadı. Lütfen tekrar deneyin.',
        'ar': '⚠️ تعذّر إنشاء جلسة الدفع. يرجى المحاولة مرة أخرى.',
    },

    # ========================================================================
    # RATING
    # ========================================================================

    'rating_prompt': {
        'ua': '⭐ Як вам сервіс? Оцініть, будь ласка:',
        'de': '⭐ Wie war Ihr Erlebnis? Bitte bewerten Sie uns:',
        'en': '⭐ How was your experience? Please rate us:',
        'pl': '⭐ Jak oceniasz nasz serwis?',
        'tr': '⭐ Deneyiminizi değerlendirir misiniz?',
        'ar': '⭐ كيف كانت تجربتك؟ يرجى تقييمنا:',
    },

    'rating_thanks_high': {
        'ua': '🙏 Дякуємо! {stars}\n\nРаді, що сервіс вам сподобався!',
        'de': '🙏 Vielen Dank! {stars}\n\nSchön, dass Sie zufrieden sind!',
        'en': '🙏 Thank you! {stars}\n\nWe\'re glad you had a great experience!',
        'pl': '🙏 Dziękujemy! {stars}\n\nCieszymy się, że jesteś zadowolony!',
        'tr': '🙏 Teşekkürler! {stars}\n\nMemnun olduğunuza sevindik!',
        'ar': '🙏 شكراً! {stars}\n\nيسعدنا أنك راضٍ عن خدمتنا!',
    },

    'rating_thanks_low': {
        'ua': '{stars} Дякуємо за чесний відгук.\n\nЩо можемо покращити? Напишіть нам.',
        'de': '{stars} Danke für Ihr ehrliches Feedback.\n\nWas können wir verbessern? Schreiben Sie uns.',
        'en': '{stars} Thank you for the honest feedback.\n\nWhat can we improve? Feel free to write to us.',
        'pl': '{stars} Dziękujemy za szczerą opinię.\n\nCo możemy poprawić? Napisz do nas.',
        'tr': '{stars} Dürüst geri bildiriminiz için teşekkürler.\n\nNeyi iyileştirebiliriz? Bize yazın.',
        'ar': '{stars} شكراً على ملاحظاتك الصادقة.\n\nما الذي يمكننا تحسينه؟ اكتب لنا.',
    },

    # ========================================================================
    # CROSS-SELL
    # ========================================================================

    'cross_sell_title': {
        'ua': '📎 Також може знадобитися:',
        'de': '📎 Das könnte Sie auch interessieren:',
        'en': '📎 You might also need:',
        'pl': '📎 Może Ci się również przydać:',
        'tr': '📎 Bunlara da ihtiyacınız olabilir:',
        'ar': '📎 قد تحتاج أيضًا إلى:',
    },

    # ========================================================================
    # WHAT NEXT? BUTTON
    # ========================================================================

    'what_next': {
        'ua': '📋 Що далі?',
        'de': '📋 Was nun?',
        'en': '📋 What next?',
        'pl': '📋 Co dalej?',
        'tr': '📋 Sırada ne var?',
        'ar': '📋 ماذا بعد؟',
    },

    # ========================================================================
    # SUPPORT / ERRORS
    # ========================================================================

    'support_error': {
        'ua': '❌ Виникла помилка. Спробуйте ще раз або зверніться в підтримку.',
        'de': '❌ Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut oder kontaktieren Sie den Support.',
        'en': '❌ An error occurred. Please try again or contact support.',
        'pl': '❌ Wystąpił błąd. Spróbuj ponownie lub skontaktuj się z pomocą.',
        'tr': '❌ Bir hata oluştu. Lütfen tekrar deneyin veya destek ile iletişime geçin.',
        'ar': '❌ حدث خطأ. يرجى المحاولة مرة أخرى أو التواصل مع الدعم.',
    },

    'back_btn': {
        'ua': '⬅️ Назад',
        'de': '⬅️ Zurück',
        'en': '⬅️ Back',
        'pl': '⬅️ Wstecz',
        'tr': '⬅️ Geri',
        'ar': '⬅️ رجوع',
    },
}


# ============================================================================
# COMPATIBILITY ALIASES
# ============================================================================

# Primary alias: TRANSLATIONS = TEXTS (for backward compatibility)
TRANSLATIONS = TEXTS

# Extract FIELD_PROMPTS from TEXTS['fields']
FIELD_PROMPTS = TEXTS.get('fields', {})


# ============================================================================
# AUTO-GENERATE DOCUMENT_NAMES FROM doc_ KEYS
# ============================================================================

def _generate_document_names() -> dict:
    """
    Автоматично генерує словник DOCUMENT_NAMES на основі ключів doc_ у TEXTS.
    Ключ doc_kindergeld -> kindergeld
    """
    doc_names = {}
    for key, value in TEXTS.items():
        if key.startswith('doc_') and isinstance(value, dict):
            # Remove 'doc_' prefix to get document type
            doc_type = key[4:]  # 'doc_kindergeld' -> 'kindergeld'
            doc_names[doc_type] = value
    return doc_names

# Auto-generated document names
DOCUMENT_NAMES = _generate_document_names()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_text(key: str, lang: str = 'ua', **kwargs) -> str:
    """
    Отримати переклад за ключем з підтримкою форматування.
    
    Args:
        key: Основний ключ (наприклад, 'welcome_msg', 'fields.first_name')
        lang: Код мови (ua, de, en, pl, tr, ar)
        **kwargs: Додаткові аргументи для форматування тексту
    
    Returns:
        Перекладений текст для вказаної мови
    
    Examples:
        get_text('welcome', 'de')
        get_text('fields.first_name', 'ua')
        get_text('btn_yes', 'en')
    """
    if lang not in SUPPORTED_LANGUAGES:
        lang = 'ua'
    
    # Handle nested keys like 'fields.first_name' or 'validation.invalid_iban'
    if '.' in key:
        parts = key.split('.', 1)
        data = TEXTS.get(parts[0], {})
        if isinstance(data, dict) and parts[1] in data:
            data = data[parts[1]]
        else:
            return key
    else:
        data = TEXTS.get(key, {})
    
    # Get translation for language
    if isinstance(data, dict):
        text = data.get(lang, data.get('ua', str(key)))
    else:
        text = str(data)
    
    # Apply formatting if kwargs provided
    if kwargs and isinstance(text, str):
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    
    return text


import logging as _i18n_log
_i18n_logger = _i18n_log.getLogger(__name__)


def ui(key: str, lang: str = 'ua', **kwargs) -> str:
    """
    Compact i18n helper for UI strings.  Normalises 'uk' → 'ua', falls back to
    English then the raw key, and logs a warning for any missing key so nothing
    is ever silently swallowed.

    Usage:
        ui('payment_confirmed', lang)
        ui('email_sent', lang, email='user@example.com')
    """
    # Normalise uk → ua (both codes circulate in the codebase)
    _lang = 'ua' if lang in ('uk', 'ua') else lang
    if _lang not in SUPPORTED_LANGUAGES:
        _lang = 'ua'

    data = TEXTS.get(key)
    if data is None:
        _i18n_logger.warning("i18n_missing_key: %s (lang=%s)", key, lang)
        return key

    if isinstance(data, dict):
        text = data.get(_lang) or data.get('ua') or data.get('en') or key
    else:
        text = str(data)

    if kwargs and isinstance(text, str):
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return text


def get_field_text(field_name: str, lang: str = 'ua') -> str:
    """
    Отримати текст підказки для поля форми.
    
    Args:
        field_name: Назва поля (наприклад, 'first_name', 'birth_date')
        lang: Код мови
    
    Returns:
        Текст підказки для поля
    """
    fields = TEXTS.get('fields', {})
    field_data = fields.get(field_name, {})
    
    if isinstance(field_data, dict):
        return field_data.get(lang, field_data.get('ua', field_name))
    
    return field_name


def get_validation_message(validation_type: str, lang: str = 'ua') -> str:
    """
    Отримати повідомлення валідації.
    
    Args:
        validation_type: Тип валідації (empty_field, invalid_iban, etc.)
        lang: Код мови
    
    Returns:
        Повідомлення про помилку валідації
    """
    validation = TEXTS.get('validation', {})
    msg_data = validation.get(validation_type, {})
    
    if isinstance(msg_data, dict):
        return msg_data.get(lang, msg_data.get('ua', validation_type))
    
    return validation_type


def get_document_name(doc_id: str, lang: str = 'ua') -> str:
    """
    Отримати локалізовану назву документа.
    
    Args:
        doc_id: Ідентифікатор документа (kindergeld, anmeldung, etc.)
        lang: Код мови
    
    Returns:
        Локалізована назва документа з емодзі
    """
    doc_data = DOCUMENT_NAMES.get(doc_id, {})
    
    if isinstance(doc_data, dict):
        return doc_data.get(lang, doc_data.get('de', doc_id))
    
    return doc_id


def is_rtl_language(lang: str) -> bool:
    """
    Перевірити чи мова з написанням справа наліво (RTL).
    
    Args:
        lang: Код мови
    
    Returns:
        True якщо мова RTL (арабська), False інакше
    """
    return lang in RTL_LANGUAGES


def get_rtl_marker(lang: str) -> str:
    """
    Отримати RTL маркер для тексту.
    
    Args:
        lang: Код мови
    
    Returns:
        Unicode RTL маркер для RTL мов, порожній рядок інакше
    """
    return '\u200F' if is_rtl_language(lang) else ''


def format_rtl_text(text: str, lang: str) -> str:
    """
    Форматувати текст для RTL мов.
    
    Args:
        text: Текст для форматування
        lang: Код мови
    
    Returns:
        Текст з RTL маркерами для RTL мов
    """
    if is_rtl_language(lang):
        return f'\u200F{text}\u200F'
    return text


def get_all_document_types() -> list:
    """
    Отримати список усіх доступних типів документів.
    
    Returns:
        Список ідентифікаторів документів
    """
    return list(DOCUMENT_NAMES.keys())


def get_supported_languages() -> list:
    """
    Отримати список підтримуваних мов.
    
    Returns:
        Список кодів мов
    """
    return SUPPORTED_LANGUAGES.copy()


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Main dictionaries
    'TEXTS',
    'TRANSLATIONS',  # Alias for TEXTS
    'FIELD_PROMPTS',  # Alias for TEXTS['fields']
    'DOCUMENT_NAMES',  # Auto-generated from doc_ keys
    
    # Language config
    'SUPPORTED_LANGUAGES',
    'RTL_LANGUAGES',
    'LANGUAGE_NAMES',
    
    # Helper functions
    'get_text',
    'get_field_text',
    'get_validation_message',
    'get_document_name',
    'is_rtl_language',
    'get_rtl_marker',
    'format_rtl_text',
    'get_all_document_types',
    'get_supported_languages',
]
