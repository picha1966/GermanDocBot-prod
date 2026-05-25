# -*- coding: utf-8 -*-
"""
GDPR Compliance Module
Управління згодою користувачів та правовими документами
"""

from datetime import datetime
from typing import Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class GDPRManager:
    """
    Менеджер GDPR згоди та правових документів
    """
    
    # Тексти згоди
    CONSENT_TEXTS = {
        'ua': {
            'title': '📋 Політика конфіденційності',
            'intro': (
                'Перш ніж продовжити, будь ласка, ознайомтесь з нашими правовими документами:\n\n'
                '🔒 <b>Політика конфіденційності:</b>\n'
                'Ми збираємо та обробляємо ваші персональні дані (ім\'я, дата народження, адреса) '
                'виключно для створення документів.\n\n'
                '📜 <b>Умови використання:</b>\n'
                'Використовуючи цей бот, ви погоджуєтесь з нашими умовами надання послуг.\n\n'
                '🇪🇺 <b>Ваші права згідно GDPR:</b>\n'
                '• Право на доступ до своїх даних\n'
                '• Право на видалення даних\n'
                '• Право на виправлення даних\n'
                '• Право відкликати згоду\n\n'
                'Натискаючи "Погоджуюсь", ви підтверджуєте, що прочитали та погоджуєтесь '
                'з нашою Політикою конфіденційності та Умовами використання.'
            ),
            'accept_button': '✅ Погоджуюсь',
            'decline_button': '❌ Не погоджуюсь',
            'privacy_button': '📄 Політика конфіденційності',
            'terms_button': '📜 Умови використання',
            'decline_message': (
                '❌ На жаль, без вашої згоди ми не можемо надати послуги.\n\n'
                'Якщо ви передумаєте, натисніть /start щоб спробувати знову.'
            ),
            'accept_message': '✅ Дякуємо! Ваша згода збережена.',
        },
        'de': {
            'title': '📋 Datenschutzerklärung',
            'intro': (
                'Bevor Sie fortfahren, lesen Sie bitte unsere rechtlichen Dokumente:\n\n'
                '🔒 <b>Datenschutzerklärung:</b>\n'
                'Wir erheben und verarbeiten Ihre personenbezogenen Daten (Name, Geburtsdatum, Adresse) '
                'ausschließlich zur Dokumentenerstellung.\n\n'
                '📜 <b>Nutzungsbedingungen:</b>\n'
                'Mit der Nutzung dieses Bots stimmen Sie unseren Nutzungsbedingungen zu.\n\n'
                '🇪🇺 <b>Ihre Rechte nach DSGVO:</b>\n'
                '• Recht auf Auskunft\n'
                '• Recht auf Löschung\n'
                '• Recht auf Berichtigung\n'
                '• Recht auf Widerruf\n\n'
                'Mit Klick auf "Zustimmen" bestätigen Sie, dass Sie unsere Datenschutzerklärung '
                'und Nutzungsbedingungen gelesen haben und ihnen zustimmen.'
            ),
            'accept_button': '✅ Zustimmen',
            'decline_button': '❌ Ablehnen',
            'privacy_button': '📄 Datenschutzerklärung',
            'terms_button': '📜 Nutzungsbedingungen',
            'decline_message': (
                '❌ Leider können wir ohne Ihre Zustimmung keine Dienstleistungen erbringen.\n\n'
                'Wenn Sie Ihre Meinung ändern, drücken Sie /start um es erneut zu versuchen.'
            ),
            'accept_message': '✅ Vielen Dank! Ihre Zustimmung wurde gespeichert.',
        },
        'en': {
            'title': '📋 Privacy Policy',
            'intro': (
                'Before proceeding, please review our legal documents:\n\n'
                '🔒 <b>Privacy Policy:</b>\n'
                'We collect and process your personal data (name, date of birth, address) '
                'solely for document creation purposes.\n\n'
                '📜 <b>Terms of Service:</b>\n'
                'By using this bot, you agree to our terms of service.\n\n'
                '🇪🇺 <b>Your GDPR Rights:</b>\n'
                '• Right to access your data\n'
                '• Right to erasure\n'
                '• Right to rectification\n'
                '• Right to withdraw consent\n\n'
                'By clicking "I Agree", you confirm that you have read and agree to '
                'our Privacy Policy and Terms of Service.'
            ),
            'accept_button': '✅ I Agree',
            'decline_button': '❌ Decline',
            'privacy_button': '📄 Privacy Policy',
            'terms_button': '📜 Terms of Service',
            'decline_message': (
                '❌ Unfortunately, we cannot provide services without your consent.\n\n'
                'If you change your mind, press /start to try again.'
            ),
            'accept_message': '✅ Thank you! Your consent has been saved.',
        },
        'pl': {
            'title': '📋 Polityka Prywatności',
            'intro': (
                'Przed kontynuacją zapoznaj się z naszymi dokumentami prawnymi:\n\n'
                '🔒 <b>Polityka Prywatności:</b>\n'
                'Zbieramy i przetwarzamy Twoje dane osobowe (imię, data urodzenia, adres) '
                'wyłącznie w celu tworzenia dokumentów.\n\n'
                '📜 <b>Warunki Użytkowania:</b>\n'
                'Korzystając z tego bota, akceptujesz nasze warunki świadczenia usług.\n\n'
                '🇪🇺 <b>Twoje prawa RODO:</b>\n'
                '• Prawo dostępu do danych\n'
                '• Prawo do usunięcia danych\n'
                '• Prawo do sprostowania danych\n'
                '• Prawo do wycofania zgody\n\n'
                'Klikając "Zgadzam się", potwierdzasz, że przeczytałeś i akceptujesz '
                'naszą Politykę Prywatności oraz Warunki Użytkowania.'
            ),
            'accept_button': '✅ Zgadzam się',
            'decline_button': '❌ Nie zgadzam się',
            'privacy_button': '📄 Polityka Prywatności',
            'terms_button': '📜 Warunki Użytkowania',
            'decline_message': (
                '❌ Niestety, bez Twojej zgody nie możemy świadczyć usług.\n\n'
                'Jeśli zmienisz zdanie, naciśnij /start aby spróbować ponownie.'
            ),
            'accept_message': '✅ Dziękujemy! Twoja zgoda została zapisana.',
        },
        'tr': {
            'title': '📋 Gizlilik Politikası',
            'intro': (
                'Devam etmeden önce lütfen yasal belgelerimizi inceleyin:\n\n'
                '🔒 <b>Gizlilik Politikası:</b>\n'
                'Kişisel verilerinizi (isim, doğum tarihi, adres) yalnızca belge oluşturma '
                'amacıyla topluyoruz ve işliyoruz.\n\n'
                '📜 <b>Kullanım Koşulları:</b>\n'
                'Bu botu kullanarak hizmet şartlarımızı kabul etmiş olursunuz.\n\n'
                '🇪🇺 <b>GDPR Haklarınız:</b>\n'
                '• Verilerinize erişim hakkı\n'
                '• Silme hakkı\n'
                '• Düzeltme hakkı\n'
                '• Onayı geri çekme hakkı\n\n'
                '"Kabul Ediyorum" butonuna tıklayarak Gizlilik Politikamızı '
                've Kullanım Koşullarımızı okuduğunuzu ve kabul ettiğinizi onaylarsınız.'
            ),
            'accept_button': '✅ Kabul Ediyorum',
            'decline_button': '❌ Kabul Etmiyorum',
            'privacy_button': '📄 Gizlilik Politikası',
            'terms_button': '📜 Kullanım Koşulları',
            'decline_message': (
                '❌ Maalesef onayınız olmadan hizmet veremiyoruz.\n\n'
                'Fikrinizi değiştirirseniz, tekrar denemek için /start tuşuna basın.'
            ),
            'accept_message': '✅ Teşekkürler! Onayınız kaydedildi.',
        },
        'ar': {
            'title': '📋 سياسة الخصوصية',
            'intro': (
                'قبل المتابعة، يرجى مراجعة وثائقنا القانونية:\n\n'
                '🔒 <b>سياسة الخصوصية:</b>\n'
                'نقوم بجمع ومعالجة بياناتك الشخصية (الاسم، تاريخ الميلاد، العنوان) '
                'فقط لأغراض إنشاء المستندات.\n\n'
                '📜 <b>شروط الاستخدام:</b>\n'
                'باستخدام هذا البوت، فإنك توافق على شروط الخدمة الخاصة بنا.\n\n'
                '🇪🇺 <b>حقوقك بموجب GDPR:</b>\n'
                '• الحق في الوصول إلى بياناتك\n'
                '• الحق في المحو\n'
                '• الحق في التصحيح\n'
                '• الحق في سحب الموافقة\n\n'
                'بالنقر على "أوافق"، تؤكد أنك قرأت وتوافق على '
                'سياسة الخصوصية وشروط الاستخدام الخاصة بنا.'
            ),
            'accept_button': '✅ أوافق',
            'decline_button': '❌ لا أوافق',
            'privacy_button': '📄 سياسة الخصوصية',
            'terms_button': '📜 شروط الاستخدام',
            'decline_message': (
                '❌ للأسف، لا يمكننا تقديم الخدمات بدون موافقتك.\n\n'
                'إذا غيرت رأيك، اضغط /start للمحاولة مرة أخرى.'
            ),
            'accept_message': '✅ شكراً لك! تم حفظ موافقتك.',
        }
    }
    
    # Повний текст політики конфіденційності
    PRIVACY_POLICY = {
        'ua': """
📄 <b>ПОЛІТИКА КОНФІДЕНЦІЙНОСТІ</b>

<b>1. Збір даних</b>
Ми збираємо наступні персональні дані:
• Ім'я та прізвище
• Дата народження
• Адреса проживання
• Контактна інформація
• Банківські реквізити (IBAN, BIC)

<b>2. Мета обробки</b>
Ваші дані використовуються виключно для:
• Створення офіційних документів
• Комунікації з вами
• Виконання платіжних операцій

<b>3. Зберігання даних</b>
• Дані зберігаються на захищених серверах
• Термін зберігання: 3 роки або до видалення за вашим запитом
• Резервні копії видаляються протягом 30 днів

<b>4. Ваші права</b>
Ви маєте право:
• Отримати копію своїх даних
• Вимагати виправлення неточних даних
• Вимагати видалення даних
• Відкликати згоду на обробку

<b>5. Контакти</b>
Для питань щодо конфіденційності: /support

Останнє оновлення: {date}
""",
        'de': """
📄 <b>DATENSCHUTZERKLÄRUNG</b>

<b>1. Datenerhebung</b>
Wir erheben folgende personenbezogene Daten:
• Vor- und Nachname
• Geburtsdatum
• Wohnadresse
• Kontaktinformationen
• Bankverbindung (IBAN, BIC)

<b>2. Verarbeitungszwecke</b>
Ihre Daten werden ausschließlich verwendet für:
• Erstellung offizieller Dokumente
• Kommunikation mit Ihnen
• Zahlungsabwicklung

<b>3. Datenspeicherung</b>
• Daten werden auf sicheren Servern gespeichert
• Aufbewahrungsfrist: 3 Jahre oder bis zur Löschung auf Anfrage
• Backups werden innerhalb von 30 Tagen gelöscht

<b>4. Ihre Rechte</b>
Sie haben das Recht:
• Eine Kopie Ihrer Daten zu erhalten
• Berichtigung unrichtiger Daten zu verlangen
• Löschung Ihrer Daten zu verlangen
• Ihre Einwilligung zu widerrufen

<b>5. Kontakt</b>
Bei Datenschutzfragen: /support

Letzte Aktualisierung: {date}
""",
        'en': """
📄 <b>PRIVACY POLICY</b>

<b>1. Data Collection</b>
We collect the following personal data:
• First and last name
• Date of birth
• Residential address
• Contact information
• Bank details (IBAN, BIC)

<b>2. Processing Purpose</b>
Your data is used exclusively for:
• Creating official documents
• Communication with you
• Processing payments

<b>3. Data Storage</b>
• Data is stored on secure servers
• Retention period: 3 years or until deletion upon request
• Backups are deleted within 30 days

<b>4. Your Rights</b>
You have the right to:
• Obtain a copy of your data
• Request correction of inaccurate data
• Request deletion of data
• Withdraw consent for processing

<b>5. Contact</b>
For privacy questions: /support

Last updated: {date}
""",
        'pl': """
📄 <b>POLITYKA PRYWATNOŚCI</b>

<b>1. Zbieranie danych</b>
Zbieramy następujące dane osobowe:
• Imię i nazwisko
• Data urodzenia
• Adres zamieszkania
• Informacje kontaktowe
• Dane bankowe (IBAN, BIC)

<b>2. Cel przetwarzania</b>
Twoje dane są wykorzystywane wyłącznie do:
• Tworzenia oficjalnych dokumentów
• Komunikacji z Tobą
• Realizacji płatności

<b>3. Przechowywanie danych</b>
• Dane są przechowywane na zabezpieczonych serwerach
• Okres przechowywania: 3 lata lub do usunięcia na żądanie
• Kopie zapasowe są usuwane w ciągu 30 dni

<b>4. Twoje prawa</b>
Masz prawo do:
• Uzyskania kopii swoich danych
• Żądania poprawienia nieprawidłowych danych
• Żądania usunięcia danych
• Wycofania zgody na przetwarzanie

<b>5. Kontakt</b>
W sprawach prywatności: /support

Ostatnia aktualizacja: {date}
""",
        'tr': """
📄 <b>GİZLİLİK POLİTİKASI</b>

<b>1. Veri Toplama</b>
Aşağıdaki kişisel verileri topluyoruz:
• Ad ve soyad
• Doğum tarihi
• İkamet adresi
• İletişim bilgileri
• Banka bilgileri (IBAN, BIC)

<b>2. İşleme Amacı</b>
Verileriniz yalnızca şunlar için kullanılır:
• Resmi belge oluşturma
• Sizinle iletişim
• Ödeme işlemleri

<b>3. Veri Saklama</b>
• Veriler güvenli sunucularda saklanır
• Saklama süresi: 3 yıl veya talep üzerine silinene kadar
• Yedekler 30 gün içinde silinir

<b>4. Haklarınız</b>
Aşağıdaki haklara sahipsiniz:
• Verilerinizin kopyasını almak
• Yanlış verilerin düzeltilmesini talep etmek
• Verilerin silinmesini talep etmek
• İşleme onayını geri çekmek

<b>5. İletişim</b>
Gizlilik soruları için: /support

Son güncelleme: {date}
""",
        'ar': """
📄 <b>سياسة الخصوصية</b>

<b>1. جمع البيانات</b>
نقوم بجمع البيانات الشخصية التالية:
• الاسم الأول والأخير
• تاريخ الميلاد
• عنوان السكن
• معلومات الاتصال
• التفاصيل المصرفية (IBAN، BIC)

<b>2. غرض المعالجة</b>
تُستخدم بياناتك حصرياً من أجل:
• إنشاء المستندات الرسمية
• التواصل معك
• معالجة المدفوعات

<b>3. تخزين البيانات</b>
• يتم تخزين البيانات على خوادم آمنة
• فترة الاحتفاظ: 3 سنوات أو حتى الحذف عند الطلب
• يتم حذف النسخ الاحتياطية خلال 30 يوماً

<b>4. حقوقك</b>
لديك الحق في:
• الحصول على نسخة من بياناتك
• طلب تصحيح البيانات غير الدقيقة
• طلب حذف البيانات
• سحب الموافقة على المعالجة

<b>5. الاتصال</b>
لأسئلة الخصوصية: /support

آخر تحديث: {date}
"""
    }
    
    # Умови використання
    TERMS_OF_SERVICE = {
        'ua': """
📜 <b>УМОВИ ВИКОРИСТАННЯ</b>

<b>1. Загальні положення</b>
Цей бот надає послуги з підготовки документів для німецьких державних органів.

<b>2. Послуги</b>
• Заповнення форм документів
• Генерація PDF файлів
• Консультаційна підтримка

<b>3. Оплата</b>
• Оплата здійснюється через Stripe
• Ціни вказані в євро (EUR)
• Повернення коштів можливе протягом 14 днів

<b>4. Відповідальність</b>
• Ви несете відповідальність за правильність наданих даних
• Ми не несемо відповідальності за рішення державних органів
• Документи надаються "як є"

<b>5. Інтелектуальна власність</b>
• Всі матеріали захищені авторським правом
• Заборонено копіювання та розповсюдження

<b>6. Зміни умов</b>
Ми залишаємо за собою право змінювати ці умови.

Останнє оновлення: {date}
""",
        'de': """
📜 <b>NUTZUNGSBEDINGUNGEN</b>

<b>1. Allgemeines</b>
Dieser Bot bietet Dienstleistungen zur Dokumentenvorbereitung für deutsche Behörden.

<b>2. Dienstleistungen</b>
• Ausfüllen von Dokumentenformularen
• PDF-Generierung
• Beratungsunterstützung

<b>3. Zahlung</b>
• Zahlung erfolgt über Stripe
• Preise in Euro (EUR)
• Rückerstattung innerhalb von 14 Tagen möglich

<b>4. Haftung</b>
• Sie sind für die Richtigkeit der angegebenen Daten verantwortlich
• Wir haften nicht für Entscheidungen der Behörden
• Dokumente werden "wie besehen" bereitgestellt

<b>5. Geistiges Eigentum</b>
• Alle Materialien sind urheberrechtlich geschützt
• Kopieren und Verbreiten ist untersagt

<b>6. Änderungen</b>
Wir behalten uns das Recht vor, diese Bedingungen zu ändern.

Letzte Aktualisierung: {date}
""",
        'en': """
📜 <b>TERMS OF SERVICE</b>

<b>1. General</b>
This bot provides document preparation services for German authorities.

<b>2. Services</b>
• Document form completion
• PDF generation
• Consultation support

<b>3. Payment</b>
• Payment is processed through Stripe
• Prices are in Euro (EUR)
• Refunds possible within 14 days

<b>4. Liability</b>
• You are responsible for the accuracy of provided data
• We are not liable for decisions by authorities
• Documents are provided "as is"

<b>5. Intellectual Property</b>
• All materials are protected by copyright
• Copying and distribution is prohibited

<b>6. Changes</b>
We reserve the right to change these terms.

Last updated: {date}
""",
        'pl': """
📜 <b>WARUNKI UŻYTKOWANIA</b>

<b>1. Ogólne</b>
Ten bot świadczy usługi przygotowania dokumentów dla niemieckich urzędów.

<b>2. Usługi</b>
• Wypełnianie formularzy dokumentów
• Generowanie PDF
• Wsparcie konsultacyjne

<b>3. Płatność</b>
• Płatność jest przetwarzana przez Stripe
• Ceny w Euro (EUR)
• Zwrot możliwy w ciągu 14 dni

<b>4. Odpowiedzialność</b>
• Jesteś odpowiedzialny za dokładność podanych danych
• Nie ponosimy odpowiedzialności za decyzje urzędów
• Dokumenty są dostarczane "jak są"

<b>5. Własność Intelektualna</b>
• Wszystkie materiały są chronione prawem autorskim
• Kopiowanie i dystrybucja jest zabroniona

<b>6. Zmiany</b>
Zastrzegamy sobie prawo do zmiany tych warunków.

Ostatnia aktualizacja: {date}
""",
        'tr': """
📜 <b>KULLANIM KOŞULLARI</b>

<b>1. Genel</b>
Bu bot Alman makamları için belge hazırlama hizmetleri sunar.

<b>2. Hizmetler</b>
• Belge formu doldurma
• PDF oluşturma
• Danışmanlık desteği

<b>3. Ödeme</b>
• Ödeme Stripe üzerinden işlenir
• Fiyatlar Euro (EUR) cinsindendir
• 14 gün içinde iade mümkündür

<b>4. Sorumluluk</b>
• Sağlanan verilerin doğruluğundan siz sorumlusunuz
• Makamların kararlarından sorumlu değiliz
• Belgeler "olduğu gibi" sağlanır

<b>5. Fikri Mülkiyet</b>
• Tüm materyaller telif hakkı ile korunmaktadır
• Kopyalama ve dağıtım yasaktır

<b>6. Değişiklikler</b>
Bu şartları değiştirme hakkını saklı tutarız.

Son güncelleme: {date}
""",
        'ar': """
📜 <b>شروط الاستخدام</b>

<b>1. عام</b>
يقدم هذا البوت خدمات إعداد المستندات للسلطات الألمانية.

<b>2. الخدمات</b>
• إكمال نماذج المستندات
• إنشاء PDF
• دعم الاستشارة

<b>3. الدفع</b>
• يتم معالجة الدفع من خلال Stripe
• الأسعار باليورو (EUR)
• الاسترداد ممكن خلال 14 يوماً

<b>4. المسؤولية</b>
• أنت مسؤول عن دقة البيانات المقدمة
• نحن غير مسؤولين عن قرارات السلطات
• يتم توفير المستندات "كما هي"

<b>5. الملكية الفكرية</b>
• جميع المواد محمية بحقوق الطبع والنشر
• النسخ والتوزيع محظور

<b>6. التغييرات</b>
نحتفظ بالحق في تغيير هذه الشروط.

آخر تحديث: {date}
"""
    }
    
    def __init__(self, lang: str = 'ua'):
        self.lang = lang
    
    def get_consent_message(self, lang: str = None) -> str:
        """Отримати повідомлення про згоду"""
        lang = lang or self.lang
        texts = self.CONSENT_TEXTS.get(lang, self.CONSENT_TEXTS['ua'])
        return f"<b>{texts['title']}</b>\n\n{texts['intro']}"
    
    def get_consent_keyboard(self, lang: str = None) -> InlineKeyboardMarkup:
        """Отримати клавіатуру для згоди"""
        lang = lang or self.lang
        texts = self.CONSENT_TEXTS.get(lang, self.CONSENT_TEXTS['ua'])
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton(
                text=texts['accept_button'],
                callback_data='gdpr_accept'
            ),
            InlineKeyboardButton(
                text=texts['decline_button'],
                callback_data='gdpr_decline'
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text=texts['privacy_button'],
                callback_data='gdpr_privacy'
            ),
            InlineKeyboardButton(
                text=texts['terms_button'],
                callback_data='gdpr_terms'
            )
        )
        return keyboard
    
    def get_privacy_policy(self, lang: str = None) -> str:
        """Отримати політику конфіденційності"""
        lang = lang or self.lang
        policy = self.PRIVACY_POLICY.get(lang, self.PRIVACY_POLICY['ua'])
        return policy.format(date=datetime.now().strftime('%d.%m.%Y'))
    
    def get_terms_of_service(self, lang: str = None) -> str:
        """Отримати умови використання"""
        lang = lang or self.lang
        terms = self.TERMS_OF_SERVICE.get(lang, self.TERMS_OF_SERVICE['ua'])
        return terms.format(date=datetime.now().strftime('%d.%m.%Y'))
    
    def get_decline_message(self, lang: str = None) -> str:
        """Отримати повідомлення про відмову"""
        lang = lang or self.lang
        texts = self.CONSENT_TEXTS.get(lang, self.CONSENT_TEXTS['ua'])
        return texts['decline_message']
    
    def get_accept_message(self, lang: str = None) -> str:
        """Отримати повідомлення про прийняття"""
        lang = lang or self.lang
        texts = self.CONSENT_TEXTS.get(lang, self.CONSENT_TEXTS['ua'])
        return texts['accept_message']
    
    def get_back_keyboard(self, lang: str = None) -> InlineKeyboardMarkup:
        """Клавіатура для повернення"""
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton(
                text='◀️ Назад' if (lang or self.lang) == 'ua' else 'Zurück',
                callback_data='gdpr_back'
            )
        )
        return keyboard


# Глобальний екземпляр
gdpr_manager = GDPRManager()
