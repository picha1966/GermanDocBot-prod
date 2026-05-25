# -*- coding: utf-8 -*-
"""
Termin Assistant — SQLite Database (adapted for GOLD-BUILD integration)
Separate DB from main bot's database to avoid conflicts.
"""
import sqlite3
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# DB lives next to main bot's DB, inside GERMAN_DOC_BOT/
DATABASE_PATH = Path(__file__).parent.parent / "termin_assistant.db"


def get_connection():
    """Get a database connection with WAL journal mode.

    WAL (Write-Ahead Logging) allows concurrent reads during writes, which is
    critical for the Termin module where the background polling loop, the Stripe
    webhook handler, and the deeplink handler all access the DB simultaneously.
    Without WAL, concurrent writes can cause 'database is locked' errors.
    """
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; faster than FULL
    return conn


def init_database():
    """Initialize the database with all required tables"""
    conn = get_connection()
    cursor = conn.cursor()

    # Users table (termin-specific fields)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE NOT NULL,
            language TEXT DEFAULT 'en',
            mode TEXT,
            city TEXT,
            authority TEXT,
            status TEXT DEFAULT 'searching',
            has_paid_document INTEGER DEFAULT 0,
            has_paid_termin INTEGER DEFAULT 0,
            reminder_interval TEXT,
            reminder_active INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # Payment transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT NOT NULL,
            session_id TEXT UNIQUE NOT NULL,
            payment_id TEXT,
            product_type TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'eur',
            payment_status TEXT DEFAULT 'pending',
            metadata TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        )
    """)

    # Cities table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            country_code TEXT NOT NULL DEFAULT 'de',
            name_de TEXT NOT NULL,
            name_en TEXT NOT NULL,
            name_ua TEXT,
            name_pl TEXT,
            name_tr TEXT,
            name_ar TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    # Authorities table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS authorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_code TEXT NOT NULL,
            authority_type TEXT NOT NULL,
            name_de TEXT NOT NULL,
            name_en TEXT NOT NULL,
            name_ua TEXT,
            name_pl TEXT,
            name_tr TEXT,
            name_ar TEXT,
            booking_url TEXT,
            booking_system TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            UNIQUE(city_code, authority_type),
            FOREIGN KEY (city_code) REFERENCES cities(code)
        )
    """)

    # Knowledge base table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_code TEXT NOT NULL,
            authority_type TEXT NOT NULL,
            language TEXT NOT NULL,
            title TEXT,
            description TEXT,
            booking_steps TEXT,
            documents_required TEXT,
            common_mistakes TEXT,
            timing_patterns TEXT,
            tips TEXT,
            constraints TEXT,
            updated_at TEXT,
            UNIQUE(city_code, authority_type, language)
        )
    """)

    # Reminders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT NOT NULL,
            city_code TEXT,
            authority_type TEXT,
            interval_hours INTEGER DEFAULT 6,
            is_active INTEGER DEFAULT 1,
            last_sent TEXT,
            created_at TEXT,
            FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
        )
    """)

    # Migration: add country_code to existing cities table if missing
    try:
        cursor.execute("PRAGMA table_info(cities)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "country_code" not in columns:
            cursor.execute("ALTER TABLE cities ADD COLUMN country_code TEXT NOT NULL DEFAULT 'de'")
            logger.info("Migrated cities table: added country_code column")
    except Exception as e:
        logger.warning("cities migration check failed: %s", e)

    # Entitlements table (single/family access control)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS termin_entitlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'single',
            slots_total INTEGER NOT NULL DEFAULT 1,
            slots_used INTEGER NOT NULL DEFAULT 0,
            stripe_session_id TEXT UNIQUE,
            active INTEGER NOT NULL DEFAULT 0,
            found_termin INTEGER NOT NULL DEFAULT 0,
            paid_until TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Migration: add active/found_termin entitlement flags if missing + clean stale rows
    try:
        cursor.execute("PRAGMA table_info(termin_entitlements)")
        _e_cols = [row["name"] for row in cursor.fetchall()]
        if "active" not in _e_cols:
            cursor.execute("ALTER TABLE termin_entitlements ADD COLUMN active INTEGER NOT NULL DEFAULT 0")
            logger.info("Migrated termin_entitlements: added active column (default 0)")
        if "found_termin" not in _e_cols:
            cursor.execute("ALTER TABLE termin_entitlements ADD COLUMN found_termin INTEGER NOT NULL DEFAULT 0")
            logger.info("Migrated termin_entitlements: added found_termin column")
        if "city" not in _e_cols:
            cursor.execute("ALTER TABLE termin_entitlements ADD COLUMN city TEXT")
            logger.info("Migrated termin_entitlements: added city column")
        if "authority" not in _e_cols:
            cursor.execute("ALTER TABLE termin_entitlements ADD COLUMN authority TEXT")
            logger.info("Migrated termin_entitlements: added authority column")
        if "checkout_url" not in _e_cols:
            cursor.execute("ALTER TABLE termin_entitlements ADD COLUMN checkout_url TEXT DEFAULT NULL")
            logger.info("Migrated termin_entitlements: added checkout_url column")
    except Exception as e:
        logger.warning("termin_entitlements migration failed: %s", e)

    # Per-profile user settings (Family V1)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS termin_user_profiles (
            user_id INTEGER NOT NULL,
            profile_id INTEGER NOT NULL,
            city_code TEXT,
            authority_type TEXT,
            source_doc TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, profile_id)
        )
    """)

    # Migration: add profile_id to reminders if missing
    try:
        cursor.execute("PRAGMA table_info(reminders)")
        _r_cols = [row["name"] for row in cursor.fetchall()]
        if "profile_id" not in _r_cols:
            cursor.execute("ALTER TABLE reminders ADD COLUMN profile_id INTEGER DEFAULT 1")
            cursor.execute("UPDATE reminders SET profile_id = 1 WHERE profile_id IS NULL")
            logger.info("Migrated reminders table: added profile_id column + backfilled existing rows")
    except Exception as e:
        logger.warning("reminders profile_id migration failed: %s", e)

    # Migration: add active_profile_id to users if missing
    try:
        cursor.execute("PRAGMA table_info(users)")
        _u_cols = [row["name"] for row in cursor.fetchall()]
        if "active_profile_id" not in _u_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN active_profile_id INTEGER DEFAULT 1")
            logger.info("Migrated users table: added active_profile_id column")
    except Exception as e:
        logger.warning("users active_profile_id migration failed: %s", e)

    # Migration: add customer_email + termin_email_notified to users if missing
    try:
        cursor.execute("PRAGMA table_info(users)")
        _u_cols2 = [row["name"] for row in cursor.fetchall()]
        if "customer_email" not in _u_cols2:
            cursor.execute("ALTER TABLE users ADD COLUMN customer_email TEXT DEFAULT NULL")
            logger.info("Migrated users table: added customer_email column")
        if "termin_email_notified" not in _u_cols2:
            cursor.execute("ALTER TABLE users ADD COLUMN termin_email_notified INTEGER DEFAULT 0")
            logger.info("Migrated users table: added termin_email_notified column")
        if "last_slot_found_at" not in _u_cols2:
            cursor.execute("ALTER TABLE users ADD COLUMN last_slot_found_at TEXT DEFAULT NULL")
            logger.info("Migrated users table: added last_slot_found_at column")
    except Exception as e:
        logger.warning("users email columns migration failed: %s", e)

    conn.commit()
    conn.close()
    logger.info("Termin DB initialized at %s", DATABASE_PATH)


def seed_berlin_data():
    """Seed initial data for Berlin"""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute("SELECT COUNT(*) as count FROM cities WHERE code = 'berlin'")
    city_exists = cursor.fetchone()['count'] > 0

    if not city_exists:
        # ── City ──
        cursor.execute("""
            INSERT INTO cities (code, country_code, name_de, name_en, name_ua, name_pl, name_tr, name_ar, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('berlin', 'de', 'Berlin', 'Berlin', 'Берлін', 'Berlin', 'Berlin', 'برلين', now))

    # ── Authorities — INSERT OR IGNORE so re-runs on existing DB are safe ──
    berlin_authorities = [
        ('buergeramt', 'Bürgeramt', 'Citizens Office', 'Бюргерамт', 'Urząd Obywatelski', 'Vatandaşlık Ofisi', 'مكتب المواطنين',
         'https://service.berlin.de/terminvereinbarung/termin/all/120686/?termin=1', 'berlin_service'),
        ('auslaenderbehoerde', 'Ausländerbehörde', 'Immigration Office', 'Міграційна служба', 'Urząd ds. Cudzoziemców', 'Yabancılar Dairesi', 'مكتب شؤون الأجانب',
         'https://otv.verwalt-berlin.de/ams/TerminBuchen', 'berlin_labo'),
        ('niederlassungserlaubnis', 'Niederlassungserlaubnis', 'Permanent Residence Permit', 'Постійний дозвіл на проживання', 'Zezwolenie na pobyt stały', 'Süresiz Oturma İzni', 'تصريح إقامة دائمة',
         'https://otv.verwalt-berlin.de/ams/TerminBuchen', 'berlin_labo'),
        ('fuehrerschein', 'Führerscheinstelle', 'Driver\'s License Office', 'Конвертація водійського посвідчення', 'Urząd ds. Prawa Jazdy', 'Ehliyet Dairesi', 'مكتب رخصة القيادة',
         'https://service.berlin.de/terminvereinbarung/termin/all/121598/?termin=1', 'berlin_service'),
        ('personalausweis', 'Personalausweis (Bürgeramt)', 'German ID Card', 'Посвідчення особи (Personalausweis)', 'Dowód osobisty', 'Kimlik Kartı', 'بطاقة الهوية الألمانية',
         'https://service.berlin.de/terminvereinbarung/termin/all/121151/?termin=1', 'berlin_service'),
        ('reisepass', 'Reisepass (Bürgeramt)', 'German Passport', 'Закордонний паспорт (Reisepass)', 'Paszport (Reisepass)', 'Pasaport (Reisepass)', 'جواز السفر الألماني (Reisepass)',
         'https://service.berlin.de/terminvereinbarung/termin/all/121921/?termin=1', 'berlin_service'),
    ]
    for auth in berlin_authorities:
        cursor.execute("""
            INSERT OR IGNORE INTO authorities
            (city_code, authority_type, name_de, name_en, name_ua, name_pl, name_tr, name_ar, booking_url, booking_system, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('berlin', *auth, now))

    # ── Knowledge base (always upsert — INSERT OR REPLACE is idempotent) ──
    _seed_buergeramt_knowledge(cursor, now)
    _seed_auslaenderbehoerde_knowledge(cursor, now)

    conn.commit()
    conn.close()
    logger.info("Termin DB: Berlin data seeded (city_new=%s)", not city_exists)


# ═══════════════════════════════════════════════════
# Knowledge seeding (all languages)
# ═══════════════════════════════════════════════════

def _seed_buergeramt_knowledge(cursor, now):
    knowledge = {
        'en': {
            'title': 'Booking at Bürgeramt Berlin',
            'description': 'The Bürgeramt handles residence registration (Anmeldung), ID cards, passports, and civil services.',
            'booking_steps': json.dumps([
                'Go to service.berlin.de',
                'Select "Terminvereinbarung"',
                'Choose "Anmeldung einer Wohnung"',
                'Select any available Bürgeramt',
                'Pick a date and time',
                'Enter your email for confirmation',
                'Save your appointment code',
            ]),
            'documents_required': json.dumps([
                'Valid passport or ID',
                'Registration form (Anmeldeformular)',
                'Landlord confirmation (Wohnungsgeberbestätigung)',
                'Previous registration if moving within Berlin',
            ]),
            'common_mistakes': json.dumps([
                'Choosing "Meldebescheinigung" instead of "Anmeldung" - different services!',
                'Forgetting landlord confirmation form',
                'Missing the 14-day registration deadline',
            ]),
            'timing_patterns': json.dumps({
                'best_times': 'Early morning (8:00) or late night (22:00+)',
                'best_days': 'Tuesday and Thursday',
                'note': 'New slots appear throughout the day',
            }),
            'tips': json.dumps([
                'Check multiple Bürgeramt locations',
                'Have all documents ready beforehand',
                'Arrive 10 minutes early',
            ]),
        },
        'de': {
            'title': 'Termin beim Bürgeramt Berlin',
            'description': 'Das Bürgeramt ist zuständig für Anmeldung, Personalausweise, Reisepässe und Bürgerangelegenheiten.',
            'booking_steps': json.dumps(['Gehen Sie zu service.berlin.de', 'Wählen Sie "Terminvereinbarung"', 'Wählen Sie "Anmeldung einer Wohnung"', 'Wählen Sie ein verfügbares Bürgeramt', 'Wählen Sie Datum und Uhrzeit', 'Geben Sie Ihre E-Mail ein', 'Speichern Sie Ihren Termincode']),
            'documents_required': json.dumps(['Gültiger Reisepass oder Personalausweis', 'Anmeldeformular', 'Wohnungsgeberbestätigung', 'Vorherige Meldebescheinigung bei Umzug innerhalb Berlins']),
            'common_mistakes': json.dumps(['"Meldebescheinigung" statt "Anmeldung" wählen - verschiedene Dienste!', 'Wohnungsgeberbestätigung vergessen', '14-Tage-Frist nach Umzug verpassen']),
            'timing_patterns': json.dumps({'best_times': 'Früh morgens (8:00) oder spät abends (22:00+)', 'best_days': 'Dienstag und Donnerstag', 'note': 'Neue Termine erscheinen über den Tag verteilt'}),
            'tips': json.dumps(['Verschiedene Bürgeramt-Standorte prüfen', 'Alle Dokumente vorher bereithalten', '10 Minuten früher ankommen']),
        },
        'ua': {
            'title': 'Запис до Бюргерамту Берлін',
            'description': 'Бюргерамт займається реєстрацією проживання (Anmeldung), посвідченнями, паспортами та цивільними справами.',
            'booking_steps': json.dumps(['Перейдіть на service.berlin.de', 'Виберіть "Terminvereinbarung"', 'Виберіть "Anmeldung einer Wohnung"', 'Виберіть доступний Бюргерамт', 'Оберіть дату та час', 'Введіть email для підтвердження', 'Збережіть код запису']),
            'documents_required': json.dumps(['Дійсний паспорт або посвідчення', 'Форма реєстрації (Anmeldeformular)', 'Підтвердження від орендодавця (Wohnungsgeberbestätigung)', 'Попередня реєстрація при переїзді в межах Берліна']),
            'common_mistakes': json.dumps(['Вибір "Meldebescheinigung" замість "Anmeldung" - це різні послуги!', 'Забути форму від орендодавця', 'Пропустити 14-денний термін реєстрації']),
            'timing_patterns': json.dumps({'best_times': 'Рано вранці (8:00) або пізно ввечері (22:00+)', 'best_days': 'Вівторок та четвер', 'note': "Нові записи з'являються протягом дня"}),
            'tips': json.dumps(['Перевірте кілька локацій Бюргерамту', 'Підготуйте всі документи заздалегідь', 'Прийдіть на 10 хвилин раніше']),
        },
        'pl': {
            'title': 'Rezerwacja w Bürgeramt Berlin',
            'description': 'Bürgeramt zajmuje się rejestracją zamieszkania (Anmeldung), dowodami, paszportami i sprawami obywatelskimi.',
            'booking_steps': json.dumps(['Wejdź na service.berlin.de', 'Wybierz "Terminvereinbarung"', 'Wybierz "Anmeldung einer Wohnung"', 'Wybierz dostępny Bürgeramt', 'Wybierz datę i godzinę', 'Podaj email do potwierdzenia', 'Zapisz kod wizyty']),
            'documents_required': json.dumps(['Ważny paszport lub dowód', 'Formularz rejestracyjny (Anmeldeformular)', 'Potwierdzenie od wynajmującego (Wohnungsgeberbestätigung)', 'Poprzednia rejestracja przy przeprowadzce w Berlinie']),
            'common_mistakes': json.dumps(['Wybór "Meldebescheinigung" zamiast "Anmeldung" - to różne usługi!', 'Zapomnienie formularza od wynajmującego', 'Przekroczenie 14-dniowego terminu']),
            'timing_patterns': json.dumps({'best_times': 'Wcześnie rano (8:00) lub późno wieczorem (22:00+)', 'best_days': 'Wtorek i czwartek', 'note': 'Nowe terminy pojawiają się w ciągu dnia'}),
            'tips': json.dumps(['Sprawdź różne lokalizacje Bürgeramt', 'Przygotuj wszystkie dokumenty wcześniej', 'Przyjdź 10 minut wcześniej']),
        },
        'tr': {
            'title': "Bürgeramt Berlin'de Randevu",
            'description': 'Bürgeramt ikamet kaydı (Anmeldung), kimlik kartları, pasaportlar ve sivil işlerle ilgilenir.',
            'booking_steps': json.dumps(["service.berlin.de'ye gidin", '"Terminvereinbarung" seçin', '"Anmeldung einer Wohnung" seçin', 'Uygun bir Bürgeramt seçin', 'Tarih ve saat seçin', 'Onay için email girin', 'Randevu kodunuzu kaydedin']),
            'documents_required': json.dumps(['Geçerli pasaport veya kimlik', 'Kayıt formu (Anmeldeformular)', 'Ev sahibi onayı (Wohnungsgeberbestätigung)', "Berlin içinde taşınıyorsanız önceki kayıt"]),
            'common_mistakes': json.dumps(['"Anmeldung" yerine "Meldebescheinigung" seçmek - farklı hizmetler!', 'Ev sahibi formunu unutmak', '14 günlük süreyi kaçırmak']),
            'timing_patterns': json.dumps({'best_times': 'Sabah erken (8:00) veya gece geç (22:00+)', 'best_days': 'Salı ve Perşembe', 'note': 'Yeni randevular gün boyunca açılır'}),
            'tips': json.dumps(['Farklı Bürgeramt lokasyonlarını kontrol edin', 'Tüm belgeleri önceden hazırlayın', '10 dakika erken gelin']),
        },
        'ar': {
            'title': 'حجز موعد في مكتب المواطنين برلين',
            'description': 'يتعامل مكتب المواطنين مع تسجيل الإقامة وبطاقات الهوية وجوازات السفر والخدمات المدنية.',
            'booking_steps': json.dumps(['اذهب إلى service.berlin.de', 'اختر "Terminvereinbarung"', 'اختر "Anmeldung einer Wohnung"', 'اختر مكتب مواطنين متاح', 'اختر التاريخ والوقت', 'أدخل بريدك الإلكتروني', 'احفظ رمز الموعد']),
            'documents_required': json.dumps(['جواز سفر أو هوية سارية', 'استمارة التسجيل (Anmeldeformular)', 'تأكيد المالك (Wohnungsgeberbestätigung)', 'التسجيل السابق إذا كنت تنتقل داخل برلين']),
            'common_mistakes': json.dumps(['اختيار "Meldebescheinigung" بدلاً من "Anmeldung" - خدمات مختلفة!', 'نسيان نموذج المالك', 'تفويت موعد 14 يومًا']),
            'timing_patterns': json.dumps({'best_times': 'الصباح الباكر (8:00) أو المساء المتأخر (22:00+)', 'best_days': 'الثلاثاء والخميس', 'note': 'تظهر مواعيد جديدة خلال اليوم'}),
            'tips': json.dumps(['تحقق من مواقع مكتب المواطنين المختلفة', 'جهز جميع المستندات مسبقًا', 'احضر قبل 10 دقائق']),
        },
    }
    for lang, data in knowledge.items():
        cursor.execute("""
            INSERT OR REPLACE INTO knowledge_base
            (city_code, authority_type, language, title, description, booking_steps,
             documents_required, common_mistakes, timing_patterns, tips, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('berlin', 'buergeramt', lang, data['title'], data['description'],
              data['booking_steps'], data['documents_required'], data['common_mistakes'],
              data['timing_patterns'], data['tips'], now))


def _seed_auslaenderbehoerde_knowledge(cursor, now):
    knowledge = {
        'en': {
            'title': 'Booking at Ausländerbehörde Berlin',
            'description': 'The Immigration Office handles visa extensions, residence permits, and immigration matters.',
            'booking_steps': json.dumps(['Go to otv.verwalt-berlin.de', 'Select "Termin Buchen"', 'Choose your visa/permit category', 'Select appointment type', 'Pick available date and time', 'Enter personal details', 'Confirm booking']),
            'documents_required': json.dumps(['Valid passport', 'Current visa/residence permit', 'Biometric photo', 'Proof of health insurance', 'Proof of income/employment', 'Rental contract']),
            'common_mistakes': json.dumps(['Applying too late for visa extension', 'Wrong appointment category', 'Missing health insurance proof']),
            'timing_patterns': json.dumps({'best_times': 'Very early morning or midnight', 'best_days': 'Monday and Wednesday', 'note': 'Slots are very limited - check frequently'}),
            'tips': json.dumps(['Apply 6-8 weeks before visa expires', 'Prepare all documents in advance', 'Check for cancellations regularly']),
        },
        'de': {
            'title': 'Termin bei der Ausländerbehörde Berlin',
            'description': 'Die Ausländerbehörde ist zuständig für Visaverlängerungen, Aufenthaltstitel und Einwanderungsangelegenheiten.',
            'booking_steps': json.dumps(['Gehen Sie zu otv.verwalt-berlin.de', 'Wählen Sie "Termin Buchen"', 'Wählen Sie Ihre Visa-/Aufenthaltskategorie', 'Wählen Sie die Terminart', 'Wählen Sie Datum und Uhrzeit', 'Geben Sie persönliche Daten ein', 'Bestätigen Sie die Buchung']),
            'documents_required': json.dumps(['Gültiger Reisepass', 'Aktuelles Visum/Aufenthaltstitel', 'Biometrisches Foto', 'Krankenversicherungsnachweis', 'Einkommens-/Beschäftigungsnachweis', 'Mietvertrag']),
            'common_mistakes': json.dumps(['Visaverlängerung zu spät beantragen', 'Falsche Terminkategorie wählen', 'Fehlender Krankenversicherungsnachweis']),
            'timing_patterns': json.dumps({'best_times': 'Sehr früh morgens oder um Mitternacht', 'best_days': 'Montag und Mittwoch', 'note': 'Termine sind sehr begrenzt — häufig prüfen'}),
            'tips': json.dumps(['6–8 Wochen vor Visaablauf beantragen', 'Alle Dokumente im Voraus vorbereiten', 'Regelmäßig nach Absagen prüfen']),
        },
        'ua': {
            'title': 'Запис до Міграційної служби Берлін',
            'description': 'Міграційна служба займається продовженням віз, дозволами на проживання та міграційними питаннями.',
            'booking_steps': json.dumps(['Перейдіть на otv.verwalt-berlin.de', 'Виберіть "Termin Buchen"', 'Виберіть категорію візи/дозволу', 'Виберіть тип запису', 'Оберіть дату та час', 'Введіть особисті дані', 'Підтвердіть бронювання']),
            'documents_required': json.dumps(['Дійсний закордонний паспорт', 'Поточна віза/дозвіл на проживання', 'Біометричне фото', 'Підтвердження медичного страхування', 'Підтвердження доходу/роботи', 'Договір оренди житла']),
            'common_mistakes': json.dumps(['Занадто пізня подача на продовження візи', 'Неправильна категорія запису', 'Відсутній документ про страхування']),
            'timing_patterns': json.dumps({'best_times': 'Дуже рано вранці або опівночі', 'best_days': 'Понеділок та середа', 'note': 'Місць дуже мало — перевіряйте часто'}),
            'tips': json.dumps(['Подавайте за 6–8 тижнів до закінчення візи', 'Підготуйте всі документи заздалегідь', 'Регулярно перевіряйте скасовані записи']),
        },
        'pl': {
            'title': 'Rezerwacja w Ausländerbehörde Berlin',
            'description': 'Urząd ds. Cudzoziemców zajmuje się przedłużaniem wiz, pozwoleniami na pobyt i sprawami imigracyjnymi.',
            'booking_steps': json.dumps(['Wejdź na otv.verwalt-berlin.de', 'Wybierz "Termin Buchen"', 'Wybierz kategorię wizy/pozwolenia', 'Wybierz rodzaj wizyty', 'Wybierz datę i godzinę', 'Podaj dane osobowe', 'Potwierdź rezerwację']),
            'documents_required': json.dumps(['Ważny paszport', 'Aktualna wiza/pozwolenie na pobyt', 'Zdjęcie biometryczne', 'Potwierdzenie ubezpieczenia zdrowotnego', 'Potwierdzenie dochodu/zatrudnienia', 'Umowa najmu']),
            'common_mistakes': json.dumps(['Zbyt późne złożenie wniosku o przedłużenie wizy', 'Zła kategoria wizyty', 'Brak potwierdzenia ubezpieczenia']),
            'timing_patterns': json.dumps({'best_times': 'Bardzo wcześnie rano lub o północy', 'best_days': 'Poniedziałek i środa', 'note': 'Terminów jest bardzo mało — sprawdzaj często'}),
            'tips': json.dumps(['Złóż wniosek 6–8 tygodni przed wygaśnięciem wizy', 'Przygotuj wszystkie dokumenty wcześniej', 'Regularnie sprawdzaj odwołane terminy']),
        },
        'tr': {
            'title': "Ausländerbehörde Berlin'de Randevu",
            'description': 'Yabancılar Dairesi vize uzatma, oturma izni ve göç işleriyle ilgilenir.',
            'booking_steps': json.dumps(["otv.verwalt-berlin.de'ye gidin", '"Termin Buchen" seçin', 'Vize/oturma izni kategorinizi seçin', 'Randevu türünü seçin', 'Tarih ve saat seçin', 'Kişisel bilgilerinizi girin', 'Rezervasyonu onaylayın']),
            'documents_required': json.dumps(['Geçerli pasaport', 'Mevcut vize/oturma izni', 'Biyometrik fotoğraf', 'Sağlık sigortası belgesi', 'Gelir/istihdam belgesi', 'Kira sözleşmesi']),
            'common_mistakes': json.dumps(['Vize uzatma başvurusunu çok geç yapmak', 'Yanlış randevu kategorisi seçmek', 'Sağlık sigortası belgesini unutmak']),
            'timing_patterns': json.dumps({'best_times': 'Sabah çok erken veya gece yarısı', 'best_days': 'Pazartesi ve Çarşamba', 'note': 'Randevular çok sınırlı — sık kontrol edin'}),
            'tips': json.dumps(['Vize bitmeden 6–8 hafta önce başvurun', 'Tüm belgeleri önceden hazırlayın', 'İptal edilen randevuları düzenli kontrol edin']),
        },
        'ar': {
            'title': 'حجز موعد في مكتب شؤون الأجانب برلين',
            'description': 'يتعامل مكتب شؤون الأجانب مع تمديد التأشيرات وتصاريح الإقامة وشؤون الهجرة.',
            'booking_steps': json.dumps(['اذهب إلى otv.verwalt-berlin.de', 'اختر "Termin Buchen"', 'اختر فئة التأشيرة/الإقامة', 'اختر نوع الموعد', 'اختر التاريخ والوقت', 'أدخل بياناتك الشخصية', 'أكد الحجز']),
            'documents_required': json.dumps(['جواز سفر ساري', 'التأشيرة/تصريح الإقامة الحالي', 'صورة بيومترية', 'إثبات التأمين الصحي', 'إثبات الدخل/العمل', 'عقد الإيجار']),
            'common_mistakes': json.dumps(['التقديم المتأخر لتمديد التأشيرة', 'اختيار فئة موعد خاطئة', 'نسيان إثبات التأمين الصحي']),
            'timing_patterns': json.dumps({'best_times': 'الصباح الباكر جدًا أو منتصف الليل', 'best_days': 'الاثنين والأربعاء', 'note': 'المواعيد محدودة جدًا — تحقق بشكل متكرر'}),
            'tips': json.dumps(['قدم قبل 6–8 أسابيع من انتهاء التأشيرة', 'جهز جميع المستندات مسبقًا', 'تحقق من المواعيد الملغاة بانتظام']),
        },
    }
    for lang, data in knowledge.items():
        cursor.execute("""
            INSERT OR REPLACE INTO knowledge_base
            (city_code, authority_type, language, title, description, booking_steps,
             documents_required, common_mistakes, timing_patterns, tips, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('berlin', 'auslaenderbehoerde', lang, data['title'], data['description'],
              data['booking_steps'], data['documents_required'], data['common_mistakes'],
              data['timing_patterns'], data['tips'], now))


def _seed_jobcenter_knowledge(cursor, now):
    knowledge = {
        'en': {
            'title': 'Booking at Jobcenter Berlin',
            'description': 'The Jobcenter handles employment services, unemployment benefits, and job placement.',
            'booking_steps': json.dumps(['Contact your local Jobcenter', 'Call the hotline or visit in person', 'Appointments are usually arranged by phone', 'Some services available without appointment']),
            'documents_required': json.dumps(['ID/Passport', 'Registration certificate (Meldebescheinigung)', 'Work permit (if applicable)', 'Previous employment documents']),
            'common_mistakes': json.dumps(['Not registering as job-seeker on time', 'Missing appointment without notice']),
            'timing_patterns': json.dumps({'best_times': 'Morning hours', 'note': 'Contact directly for appointment'}),
            'tips': json.dumps(['Register as job-seeker before unemployment starts', 'Bring all documents to first meeting']),
        },
        'de': {
            'title': 'Termin beim Jobcenter Berlin',
            'description': 'Das Jobcenter ist zuständig für Arbeitsvermittlung, Arbeitslosengeld und Beschäftigungsförderung.',
            'booking_steps': json.dumps(['Kontaktieren Sie Ihr lokales Jobcenter', 'Rufen Sie die Hotline an oder kommen Sie persönlich', 'Termine werden in der Regel telefonisch vereinbart', 'Einige Leistungen sind ohne Termin verfügbar']),
            'documents_required': json.dumps(['Personalausweis/Reisepass', 'Meldebescheinigung', 'Arbeitserlaubnis (falls zutreffend)', 'Unterlagen früherer Beschäftigung']),
            'common_mistakes': json.dumps(['Arbeitssuchend-Meldung zu spät', 'Termin ohne Absage versäumen']),
            'timing_patterns': json.dumps({'best_times': 'Vormittags', 'note': 'Direkt kontaktieren für Terminvereinbarung'}),
            'tips': json.dumps(['Vor Beginn der Arbeitslosigkeit arbeitssuchend melden', 'Alle Unterlagen zum ersten Gespräch mitbringen']),
        },
        'ua': {
            'title': 'Запис до Центру зайнятості Берлін',
            'description': 'Центр зайнятості займається працевлаштуванням, допомогою по безробіттю та пошуком роботи.',
            'booking_steps': json.dumps(['Зверніться до місцевого Центру зайнятості', 'Зателефонуйте на гарячу лінію або прийдіть особисто', 'Записи зазвичай оформлюються по телефону', 'Деякі послуги доступні без запису']),
            'documents_required': json.dumps(['Паспорт або посвідчення особи', 'Довідка про реєстрацію (Meldebescheinigung)', 'Дозвіл на роботу (якщо потрібен)', 'Документи з попереднього місця роботи']),
            'common_mistakes': json.dumps(['Несвоєчасна реєстрація як шукач роботи', 'Пропуск запису без попередження']),
            'timing_patterns': json.dumps({'best_times': 'Ранкові години', 'note': 'Зверніться безпосередньо для запису'}),
            'tips': json.dumps(['Зареєструйтесь як шукач роботи до початку безробіття', 'Візьміть усі документи на першу зустріч']),
        },
        'pl': {
            'title': 'Rezerwacja w Jobcenter Berlin',
            'description': 'Jobcenter zajmuje się pośrednictwem pracy, zasiłkami dla bezrobotnych i pomocą w zatrudnieniu.',
            'booking_steps': json.dumps(['Skontaktuj się z lokalnym Jobcenter', 'Zadzwoń na infolinię lub przyjdź osobiście', 'Wizyty umawiane są zwykle telefonicznie', 'Niektóre usługi dostępne bez wizyty']),
            'documents_required': json.dumps(['Dowód/Paszport', 'Zaświadczenie o zameldowaniu (Meldebescheinigung)', 'Pozwolenie na pracę (jeśli dotyczy)', 'Dokumenty z poprzedniego zatrudnienia']),
            'common_mistakes': json.dumps(['Zbyt późna rejestracja jako poszukujący pracy', 'Niestawienie się na wizytę bez uprzedzenia']),
            'timing_patterns': json.dumps({'best_times': 'Godziny poranne', 'note': 'Skontaktuj się bezpośrednio w sprawie wizyty'}),
            'tips': json.dumps(['Zarejestruj się jako poszukujący pracy przed utratą zatrudnienia', 'Zabierz wszystkie dokumenty na pierwsze spotkanie']),
        },
        'tr': {
            'title': "Jobcenter Berlin'de Randevu",
            'description': 'Jobcenter istihdam hizmetleri, işsizlik yardımları ve iş bulma ile ilgilenir.',
            'booking_steps': json.dumps(['Yerel Jobcenter ile iletişime geçin', 'Hattı arayın veya şahsen gidin', 'Randevular genellikle telefonla ayarlanır', 'Bazı hizmetler randevusuz kullanılabilir']),
            'documents_required': json.dumps(['Kimlik/Pasaport', 'İkamet kaydı belgesi (Meldebescheinigung)', 'Çalışma izni (gerekiyorsa)', 'Önceki iş belgeleri']),
            'common_mistakes': json.dumps(['İş arayan kaydını zamanında yapmamak', 'Haber vermeden randevuyu kaçırmak']),
            'timing_patterns': json.dumps({'best_times': 'Sabah saatleri', 'note': 'Randevu için doğrudan iletişime geçin'}),
            'tips': json.dumps(['İşsizlik başlamadan önce iş arayan olarak kaydolun', 'İlk görüşmeye tüm belgeleri getirin']),
        },
        'ar': {
            'title': 'حجز موعد في مركز التوظيف برلين',
            'description': 'يتعامل مركز التوظيف مع خدمات العمل وإعانات البطالة والمساعدة في إيجاد وظيفة.',
            'booking_steps': json.dumps(['تواصل مع مركز التوظيف المحلي', 'اتصل بالخط الساخن أو قم بزيارة شخصية', 'يتم ترتيب المواعيد عادة عبر الهاتف', 'بعض الخدمات متاحة بدون موعد']),
            'documents_required': json.dumps(['هوية/جواز سفر', 'شهادة تسجيل السكن (Meldebescheinigung)', 'تصريح عمل (إن وجد)', 'مستندات العمل السابق']),
            'common_mistakes': json.dumps(['عدم التسجيل كباحث عن عمل في الوقت المناسب', 'تفويت الموعد دون إشعار']),
            'timing_patterns': json.dumps({'best_times': 'ساعات الصباح', 'note': 'تواصل مباشرة لحجز موعد'}),
            'tips': json.dumps(['سجل كباحث عن عمل قبل بدء البطالة', 'أحضر جميع المستندات في أول لقاء']),
        },
    }
    for lang, data in knowledge.items():
        cursor.execute("""
            INSERT OR REPLACE INTO knowledge_base
            (city_code, authority_type, language, title, description, booking_steps,
             documents_required, common_mistakes, timing_patterns, tips, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('berlin', 'jobcenter', lang, data['title'], data['description'],
              data['booking_steps'], data['documents_required'], data['common_mistakes'],
              data['timing_patterns'], data['tips'], now))


def _seed_familienkasse_knowledge(cursor, now):
    knowledge = {
        'en': {
            'title': 'Booking at Familienkasse Berlin',
            'description': 'The Family Benefits Office handles child benefits (Kindergeld) and family allowances.',
            'booking_steps': json.dumps(['Go to arbeitsagentur.de', 'Select "Familie und Kinder"', 'Choose your service type', 'Book appointment online or by phone']),
            'documents_required': json.dumps(['ID/Passport for all family members', 'Birth certificates', 'Residence registration', 'Work permit/visa (if applicable)']),
            'common_mistakes': json.dumps(['Applying too late after child birth', 'Missing required translations']),
            'timing_patterns': json.dumps({'best_times': 'Morning hours', 'note': 'Online application often faster'}),
            'tips': json.dumps(['Apply within first month after birth', 'Use online form when possible']),
        },
        'de': {
            'title': 'Termin bei der Familienkasse Berlin',
            'description': 'Die Familienkasse ist zuständig für Kindergeld und Familienleistungen.',
            'booking_steps': json.dumps(['Gehen Sie zu arbeitsagentur.de', 'Wählen Sie "Familie und Kinder"', 'Wählen Sie die gewünschte Leistung', 'Termin online oder telefonisch buchen']),
            'documents_required': json.dumps(['Personalausweis/Reisepass aller Familienmitglieder', 'Geburtsurkunden', 'Meldebestätigung', 'Arbeitserlaubnis/Visum (falls zutreffend)']),
            'common_mistakes': json.dumps(['Zu späte Beantragung nach der Geburt', 'Fehlende beglaubigte Übersetzungen']),
            'timing_patterns': json.dumps({'best_times': 'Vormittags', 'note': 'Online-Antrag oft schneller'}),
            'tips': json.dumps(['Innerhalb des ersten Monats nach der Geburt beantragen', 'Online-Formular nutzen wenn möglich']),
        },
        'ua': {
            'title': 'Запис до Сімейної каси Берлін',
            'description': 'Сімейна каса займається дитячими виплатами (Kindergeld) та сімейними допомогами.',
            'booking_steps': json.dumps(['Перейдіть на arbeitsagentur.de', 'Виберіть "Familie und Kinder"', 'Оберіть тип послуги', 'Запишіться онлайн або по телефону']),
            'documents_required': json.dumps(['Паспорт/посвідчення всіх членів сім\'ї', 'Свідоцтва про народження', 'Реєстрація за місцем проживання', 'Дозвіл на роботу/віза (якщо потрібен)']),
            'common_mistakes': json.dumps(['Занадто пізня подача після народження дитини', 'Відсутність перекладів документів']),
            'timing_patterns': json.dumps({'best_times': 'Ранкові години', 'note': 'Онлайн-заява часто швидша'}),
            'tips': json.dumps(['Подайте протягом першого місяця після народження', 'Використовуйте онлайн-форму, коли можливо']),
        },
        'pl': {
            'title': 'Rezerwacja w Familienkasse Berlin',
            'description': 'Kasa Rodzinna zajmuje się zasiłkami na dzieci (Kindergeld) i świadczeniami rodzinnymi.',
            'booking_steps': json.dumps(['Wejdź na arbeitsagentur.de', 'Wybierz "Familie und Kinder"', 'Wybierz rodzaj usługi', 'Umów wizytę online lub telefonicznie']),
            'documents_required': json.dumps(['Dowód/Paszport wszystkich członków rodziny', 'Akty urodzenia', 'Potwierdzenie zameldowania', 'Pozwolenie na pracę/wiza (jeśli dotyczy)']),
            'common_mistakes': json.dumps(['Zbyt późne złożenie wniosku po urodzeniu dziecka', 'Brak wymaganych tłumaczeń']),
            'timing_patterns': json.dumps({'best_times': 'Godziny poranne', 'note': 'Wniosek online często szybszy'}),
            'tips': json.dumps(['Złóż wniosek w ciągu pierwszego miesiąca po urodzeniu', 'Korzystaj z formularza online, jeśli to możliwe']),
        },
        'tr': {
            'title': "Familienkasse Berlin'de Randevu",
            'description': 'Aile Yardımları Ofisi çocuk yardımı (Kindergeld) ve aile ödeneklerini yönetir.',
            'booking_steps': json.dumps(["arbeitsagentur.de'ye gidin", '"Familie und Kinder" seçin', 'Hizmet türünüzü seçin', 'Online veya telefonla randevu alın']),
            'documents_required': json.dumps(['Tüm aile üyelerinin kimlik/pasaportu', 'Doğum belgeleri', 'İkamet kaydı', 'Çalışma izni/vize (gerekiyorsa)']),
            'common_mistakes': json.dumps(['Doğumdan sonra çok geç başvurmak', 'Gerekli tercümelerin eksikliği']),
            'timing_patterns': json.dumps({'best_times': 'Sabah saatleri', 'note': 'Online başvuru genellikle daha hızlı'}),
            'tips': json.dumps(['Doğumdan sonra ilk ay içinde başvurun', 'Mümkünse online formu kullanın']),
        },
        'ar': {
            'title': 'حجز موعد في صندوق الأسرة برلين',
            'description': 'يتعامل صندوق الأسرة مع إعانات الأطفال (Kindergeld) والبدلات العائلية.',
            'booking_steps': json.dumps(['اذهب إلى arbeitsagentur.de', 'اختر "Familie und Kinder"', 'اختر نوع الخدمة', 'احجز موعدًا عبر الإنترنت أو الهاتف']),
            'documents_required': json.dumps(['هوية/جواز سفر جميع أفراد الأسرة', 'شهادات الميلاد', 'تسجيل السكن', 'تصريح عمل/تأشيرة (إن وجد)']),
            'common_mistakes': json.dumps(['التقديم المتأخر بعد ولادة الطفل', 'نقص الترجمات المطلوبة']),
            'timing_patterns': json.dumps({'best_times': 'ساعات الصباح', 'note': 'الطلب عبر الإنترنت غالبًا أسرع'}),
            'tips': json.dumps(['قدم خلال الشهر الأول بعد الولادة', 'استخدم النموذج الإلكتروني عندما يكون ذلك ممكنًا']),
        },
    }
    for lang, data in knowledge.items():
        cursor.execute("""
            INSERT OR REPLACE INTO knowledge_base
            (city_code, authority_type, language, title, description, booking_steps,
             documents_required, common_mistakes, timing_patterns, tips, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('berlin', 'familienkasse', lang, data['title'], data['description'],
              data['booking_steps'], data['documents_required'], data['common_mistakes'],
              data['timing_patterns'], data['tips'], now))


# ═══════════════════════════════════════════════════
# Universal knowledge builders (city-parameterised)
# ═══════════════════════════════════════════════════

def _insert_city_knowledge(cursor, now, city_code, authority_type, knowledge: dict):
    """Idempotent upsert of knowledge_base rows for a city/authority."""
    for lang, data in knowledge.items():
        cursor.execute("""
            INSERT OR REPLACE INTO knowledge_base
            (city_code, authority_type, language, title, description, booking_steps,
             documents_required, common_mistakes, timing_patterns, tips, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (city_code, authority_type, lang,
              data.get('title'), data.get('description'), data.get('booking_steps'),
              data.get('documents_required'), data.get('common_mistakes'),
              data.get('timing_patterns'), data.get('tips'), now))


def _build_buergeramt_knowledge(city_en, city_de, city_ua, city_pl, city_tr, city_ar):
    return {
        'en': {
            'title': f'Booking at Bürgeramt {city_en}',
            'description': 'The Bürgeramt handles residence registration (Anmeldung), ID cards, passports, and civil services.',
            'booking_steps': json.dumps([f'Go to the official {city_en} city appointment portal', 'Select "Anmeldung einer Wohnung"', 'Choose an available location', 'Pick a date and time', 'Enter your email for confirmation', 'Save your appointment code']),
            'documents_required': json.dumps(['Valid passport or ID card', 'Registration form (Anmeldeformular)', 'Landlord confirmation (Wohnungsgeberbestätigung)', 'Deregistration certificate if moving from another city']),
            'common_mistakes': json.dumps(['Confusing "Meldebescheinigung" with "Anmeldung" — different services', 'Forgetting the landlord confirmation form', 'Missing the 14-day registration deadline']),
            'timing_patterns': json.dumps({'best_times': 'Early morning (8:00) or late evening (22:00+)', 'best_days': 'Tuesday and Thursday', 'note': 'New slots appear throughout the day'}),
            'tips': json.dumps([f'Check multiple Bürgeramt locations in {city_en}', 'Prepare all documents beforehand', 'Arrive 10 minutes early']),
        },
        'de': {
            'title': f'Termin beim Bürgeramt {city_de}',
            'description': 'Das Bürgeramt ist zuständig für Anmeldung, Personalausweise, Reisepässe und Bürgerangelegenheiten.',
            'booking_steps': json.dumps([f'Rufen Sie das offizielle Terminportal von {city_de} auf', '"Anmeldung einer Wohnung" auswählen', 'Verfügbaren Standort wählen', 'Datum und Uhrzeit auswählen', 'E-Mail eingeben', 'Termincode speichern']),
            'documents_required': json.dumps(['Gültiger Reisepass oder Personalausweis', 'Anmeldeformular', 'Wohnungsgeberbestätigung', 'Bei Zuzug aus anderer Stadt: Abmeldebestätigung']),
            'common_mistakes': json.dumps(['"Meldebescheinigung" statt "Anmeldung" wählen — verschiedene Leistungen', 'Wohnungsgeberbestätigung vergessen', '14-Tage-Frist nach Einzug verpassen']),
            'timing_patterns': json.dumps({'best_times': 'Früh morgens (8:00) oder spät abends (22:00+)', 'best_days': 'Dienstag und Donnerstag', 'note': 'Neue Termine erscheinen über den Tag verteilt'}),
            'tips': json.dumps([f'Mehrere Bürgeramt-Standorte in {city_de} prüfen', 'Alle Dokumente vorher bereithalten', '10 Minuten früher erscheinen']),
        },
        'ua': {
            'title': f'Запис до Бюргерамту {city_ua}',
            'description': 'Бюргерамт займається реєстрацією проживання (Anmeldung), посвідченнями, паспортами та цивільними справами.',
            'booking_steps': json.dumps([f'Перейдіть на офіційний портал запису {city_ua}', 'Виберіть "Anmeldung einer Wohnung"', 'Оберіть доступний відділ', 'Виберіть дату та час', 'Введіть email для підтвердження', 'Збережіть код запису']),
            'documents_required': json.dumps(['Дійсний паспорт або посвідчення', 'Форма реєстрації (Anmeldeformular)', 'Підтвердження від орендодавця (Wohnungsgeberbestätigung)', 'При переїзді з іншого міста: довідка про виписку']),
            'common_mistakes': json.dumps(['Плутати "Meldebescheinigung" з "Anmeldung" — різні послуги', 'Забути форму від орендодавця', 'Пропустити 14-денний термін реєстрації']),
            'timing_patterns': json.dumps({'best_times': 'Рано вранці (8:00) або пізно ввечері (22:00+)', 'best_days': 'Вівторок та четвер', 'note': "Нові записи з'являються протягом дня"}),
            'tips': json.dumps([f'Перевірте кілька відділень Бюргерамту в {city_ua}', 'Підготуйте всі документи заздалегідь', 'Прийдіть на 10 хвилин раніше']),
        },
        'pl': {
            'title': f'Rezerwacja w Bürgeramt {city_pl}',
            'description': 'Bürgeramt zajmuje się rejestracją zamieszkania (Anmeldung), dowodami, paszportami i sprawami obywatelskimi.',
            'booking_steps': json.dumps([f'Wejdź na oficjalny portal rezerwacji {city_pl}', 'Wybierz "Anmeldung einer Wohnung"', 'Wybierz dostępną lokalizację', 'Wybierz datę i godzinę', 'Podaj email do potwierdzenia', 'Zapisz kod wizyty']),
            'documents_required': json.dumps(['Ważny paszport lub dowód osobisty', 'Formularz rejestracyjny (Anmeldeformular)', 'Potwierdzenie od wynajmującego (Wohnungsgeberbestätigung)', 'Przy przeprowadzce z innego miasta: zaświadczenie o wymeldowaniu']),
            'common_mistakes': json.dumps(['Mylenie "Meldebescheinigung" z "Anmeldung" — to różne usługi', 'Zapomnienie formularza od wynajmującego', 'Przekroczenie 14-dniowego terminu']),
            'timing_patterns': json.dumps({'best_times': 'Wcześnie rano (8:00) lub późno wieczorem (22:00+)', 'best_days': 'Wtorek i czwartek', 'note': 'Nowe terminy pojawiają się w ciągu dnia'}),
            'tips': json.dumps([f'Sprawdź kilka lokalizacji Bürgeramt w {city_pl}', 'Przygotuj wszystkie dokumenty wcześniej', 'Przyjdź 10 minut wcześniej']),
        },
        'tr': {
            'title': f"Bürgeramt {city_tr}'de Randevu",
            'description': 'Bürgeramt ikamet kaydı (Anmeldung), kimlik kartları, pasaportlar ve sivil işlerle ilgilenir.',
            'booking_steps': json.dumps([f'{city_tr} resmi randevu portalına gidin', '"Anmeldung einer Wohnung" seçin', 'Uygun bir konum seçin', 'Tarih ve saat seçin', 'Onay için email girin', 'Randevu kodunuzu kaydedin']),
            'documents_required': json.dumps(['Geçerli pasaport veya kimlik kartı', 'Kayıt formu (Anmeldeformular)', 'Ev sahibi onayı (Wohnungsgeberbestätigung)', 'Başka şehirden taşınıyorsanız: adres silme belgesi']),
            'common_mistakes': json.dumps(['"Meldebescheinigung"ı "Anmeldung" ile karıştırmak — farklı hizmetler', 'Ev sahibi formunu unutmak', '14 günlük süreyi kaçırmak']),
            'timing_patterns': json.dumps({'best_times': 'Sabah erken (8:00) veya gece geç (22:00+)', 'best_days': 'Salı ve Perşembe', 'note': 'Yeni randevular gün boyunca açılır'}),
            'tips': json.dumps([f'{city_tr} şehrinde birden fazla Bürgeramt konumunu kontrol edin', 'Tüm belgeleri önceden hazırlayın', '10 dakika erken gelin']),
        },
        'ar': {
            'title': f'حجز موعد في مكتب المواطنين {city_ar}',
            'description': 'يتعامل مكتب المواطنين مع تسجيل الإقامة وبطاقات الهوية وجوازات السفر والخدمات المدنية.',
            'booking_steps': json.dumps([f'اذهب إلى بوابة الحجز الرسمية في {city_ar}', 'اختر "Anmeldung einer Wohnung"', 'اختر موقعًا متاحًا', 'اختر التاريخ والوقت', 'أدخل بريدك الإلكتروني', 'احفظ رمز الموعد']),
            'documents_required': json.dumps(['جواز سفر أو هوية سارية', 'استمارة التسجيل (Anmeldeformular)', 'تأكيد المالك (Wohnungsgeberbestätigung)', 'عند الانتقال من مدينة أخرى: شهادة إلغاء القيد']),
            'common_mistakes': json.dumps(['الخلط بين "Meldebescheinigung" و"Anmeldung" — خدمات مختلفة', 'نسيان نموذج المالك', 'تفويت مهلة 14 يومًا']),
            'timing_patterns': json.dumps({'best_times': 'الصباح الباكر (8:00) أو المساء المتأخر (22:00+)', 'best_days': 'الثلاثاء والخميس', 'note': 'تظهر مواعيد جديدة خلال اليوم'}),
            'tips': json.dumps([f'تحقق من مواقع Bürgeramt المتعددة في {city_ar}', 'جهز جميع المستندات مسبقًا', 'احضر قبل 10 دقائق']),
        },
    }


def _build_auslaenderbehoerde_knowledge(city_en, city_de, city_ua, city_pl, city_tr, city_ar):
    return {
        'en': {
            'title': f'Booking at Ausländerbehörde {city_en}',
            'description': 'The Immigration Office handles visa extensions, residence permits (Aufenthaltstitel), and all immigration matters.',
            'booking_steps': json.dumps([f'Go to the official {city_en} immigration appointment portal', 'Select your visa or permit category', 'Choose appointment type', 'Pick an available date and time', 'Enter personal details', 'Confirm booking and save reference number']),
            'documents_required': json.dumps(['Valid passport', 'Current visa or residence permit', 'Biometric photo (35×45 mm)', 'Proof of health insurance', 'Proof of income or employment contract', 'Current rental contract']),
            'common_mistakes': json.dumps(['Applying too late — apply 6–8 weeks before expiry', 'Selecting the wrong appointment category', 'Missing health insurance certificate']),
            'timing_patterns': json.dumps({'best_times': 'Very early morning or midnight', 'best_days': 'Monday and Wednesday', 'note': 'Slots are very limited — check frequently'}),
            'tips': json.dumps(['Apply 6–8 weeks before visa expires', 'Prepare complete document set in advance', 'Check for cancellations daily']),
        },
        'de': {
            'title': f'Termin bei der Ausländerbehörde {city_de}',
            'description': 'Die Ausländerbehörde ist zuständig für Visaverlängerungen, Aufenthaltstitel und alle Einwanderungsangelegenheiten.',
            'booking_steps': json.dumps([f'Rufen Sie das offizielle Terminportal der Ausländerbehörde {city_de} auf', 'Wählen Sie Ihre Visa-/Aufenthaltskategorie', 'Terminart auswählen', 'Datum und Uhrzeit auswählen', 'Persönliche Daten eingeben', 'Buchung bestätigen und Referenznummer speichern']),
            'documents_required': json.dumps(['Gültiger Reisepass', 'Aktuelles Visum/Aufenthaltstitel', 'Biometrisches Foto (35×45 mm)', 'Krankenversicherungsnachweis', 'Einkommens-/Beschäftigungsnachweis', 'Aktueller Mietvertrag']),
            'common_mistakes': json.dumps(['Zu späte Beantragung — 6–8 Wochen vor Ablauf stellen', 'Falsche Terminkategorie wählen', 'Fehlender Krankenversicherungsnachweis']),
            'timing_patterns': json.dumps({'best_times': 'Sehr früh morgens oder um Mitternacht', 'best_days': 'Montag und Mittwoch', 'note': 'Termine sehr begrenzt — häufig prüfen'}),
            'tips': json.dumps(['6–8 Wochen vor Visaablauf beantragen', 'Vollständigen Dokumentensatz vorbereiten', 'Täglich auf Absagen prüfen']),
        },
        'ua': {
            'title': f'Запис до Міграційної служби {city_ua}',
            'description': 'Міграційна служба займається продовженням віз, дозволами на проживання та всіма міграційними питаннями.',
            'booking_steps': json.dumps([f'Перейдіть на офіційний портал запису Міграційної служби {city_ua}', 'Виберіть категорію візи або дозволу', 'Оберіть тип запису', 'Виберіть дату та час', 'Введіть особисті дані', 'Підтвердіть бронювання та збережіть номер']),
            'documents_required': json.dumps(['Дійсний закордонний паспорт', 'Поточна віза або дозвіл на проживання', 'Біометричне фото (35×45 мм)', 'Підтвердження медичного страхування', 'Підтвердження доходу або трудовий договір', 'Чинний договір оренди']),
            'common_mistakes': json.dumps(['Занадто пізня подача — подавайте за 6–8 тижнів до закінчення', 'Неправильна категорія запису', 'Відсутній документ про медичне страхування']),
            'timing_patterns': json.dumps({'best_times': 'Дуже рано вранці або опівночі', 'best_days': 'Понеділок та середа', 'note': 'Місць дуже мало — перевіряйте щодня'}),
            'tips': json.dumps(['Подавайте за 6–8 тижнів до закінчення візи', 'Підготуйте повний пакет документів', 'Щодня перевіряйте скасовані записи']),
        },
        'pl': {
            'title': f'Rezerwacja w Ausländerbehörde {city_pl}',
            'description': 'Urząd ds. Cudzoziemców zajmuje się przedłużaniem wiz, pozwoleniami na pobyt i wszystkimi sprawami imigracyjnymi.',
            'booking_steps': json.dumps([f'Wejdź na oficjalny portal rezerwacji Ausländerbehörde {city_pl}', 'Wybierz kategorię wizy lub pozwolenia', 'Wybierz rodzaj wizyty', 'Wybierz datę i godzinę', 'Podaj dane osobowe', 'Potwierdź rezerwację i zapisz numer referencyjny']),
            'documents_required': json.dumps(['Ważny paszport', 'Aktualna wiza/pozwolenie na pobyt', 'Zdjęcie biometryczne (35×45 mm)', 'Potwierdzenie ubezpieczenia zdrowotnego', 'Potwierdzenie dochodu lub umowa o pracę', 'Aktualna umowa najmu']),
            'common_mistakes': json.dumps(['Zbyt późne złożenie wniosku — 6–8 tygodni przed wygaśnięciem', 'Zła kategoria wizyty', 'Brak potwierdzenia ubezpieczenia zdrowotnego']),
            'timing_patterns': json.dumps({'best_times': 'Bardzo wcześnie rano lub o północy', 'best_days': 'Poniedziałek i środa', 'note': 'Terminów jest bardzo mało — sprawdzaj codziennie'}),
            'tips': json.dumps(['Złóż wniosek 6–8 tygodni przed wygaśnięciem wizy', 'Przygotuj kompletny zestaw dokumentów', 'Sprawdzaj codziennie anulowane terminy']),
        },
        'tr': {
            'title': f"Ausländerbehörde {city_tr}'de Randevu",
            'description': 'Yabancılar Dairesi vize uzatma, oturma izni ve tüm göç işleriyle ilgilenir.',
            'booking_steps': json.dumps([f'{city_tr} Yabancılar Dairesi resmi randevu portalına gidin', 'Vize veya izin kategorinizi seçin', 'Randevu türünü seçin', 'Tarih ve saat seçin', 'Kişisel bilgilerinizi girin', 'Rezervasyonu onaylayın ve referans numaranızı kaydedin']),
            'documents_required': json.dumps(['Geçerli pasaport', 'Mevcut vize veya oturma izni', 'Biyometrik fotoğraf (35×45 mm)', 'Sağlık sigortası belgesi', 'Gelir belgesi veya iş sözleşmesi', 'Güncel kira sözleşmesi']),
            'common_mistakes': json.dumps(['Çok geç başvurmak — bitiş tarihinden 6–8 hafta önce başvurun', 'Yanlış randevu kategorisi seçmek', 'Sağlık sigortası belgesini unutmak']),
            'timing_patterns': json.dumps({'best_times': 'Sabah çok erken veya gece yarısı', 'best_days': 'Pazartesi ve Çarşamba', 'note': 'Randevular çok sınırlı — her gün kontrol edin'}),
            'tips': json.dumps(['Vize bitmeden 6–8 hafta önce başvurun', 'Eksiksiz belge seti hazırlayın', 'İptal edilen randevuları her gün kontrol edin']),
        },
        'ar': {
            'title': f'حجز موعد في مكتب شؤون الأجانب {city_ar}',
            'description': 'يتعامل مكتب شؤون الأجانب مع تمديد التأشيرات وتصاريح الإقامة وجميع شؤون الهجرة.',
            'booking_steps': json.dumps([f'اذهب إلى بوابة الحجز الرسمية لمكتب شؤون الأجانب في {city_ar}', 'اختر فئة التأشيرة أو الإقامة', 'اختر نوع الموعد', 'اختر التاريخ والوقت', 'أدخل بياناتك الشخصية', 'أكد الحجز واحفظ الرقم المرجعي']),
            'documents_required': json.dumps(['جواز سفر ساري', 'التأشيرة أو تصريح الإقامة الحالي', 'صورة بيومترية (35×45 مم)', 'إثبات التأمين الصحي', 'إثبات الدخل أو عقد العمل', 'عقد الإيجار الحالي']),
            'common_mistakes': json.dumps(['التقديم المتأخر — قدم قبل 6-8 أسابيع من الانتهاء', 'اختيار فئة موعد خاطئة', 'نسيان إثبات التأمين الصحي']),
            'timing_patterns': json.dumps({'best_times': 'الصباح الباكر جدًا أو منتصف الليل', 'best_days': 'الاثنين والأربعاء', 'note': 'المواعيد محدودة جدًا — تحقق يوميًا'}),
            'tips': json.dumps(['قدم قبل 6–8 أسابيع من انتهاء التأشيرة', 'جهز مجموعة كاملة من الوثائق', 'تحقق من المواعيد الملغاة يوميًا']),
        },
    }


def _build_jobcenter_knowledge(city_en, city_de, city_ua, city_pl, city_tr, city_ar):
    return {
        'en': {
            'title': f'Booking at Jobcenter {city_en}',
            'description': 'The Jobcenter handles Bürgergeld (unemployment benefits), job placement, and employment services.',
            'booking_steps': json.dumps([f'Contact the local Jobcenter {city_en}', 'Call the hotline or visit in person', 'Appointments are usually arranged by phone or via letter', 'Some services are available without appointment']),
            'documents_required': json.dumps(['ID or passport', 'Registration certificate (Meldebescheinigung)', 'Work permit if applicable', 'Documents from previous employment']),
            'common_mistakes': json.dumps(['Not registering as job-seeker on time', 'Missing an appointment without prior notice']),
            'timing_patterns': json.dumps({'best_times': 'Morning hours', 'note': 'Contact directly for appointment scheduling'}),
            'tips': json.dumps(['Register as job-seeker before unemployment starts', 'Bring all documents to the first meeting', 'Keep all correspondence from Jobcenter']),
        },
        'de': {
            'title': f'Termin beim Jobcenter {city_de}',
            'description': 'Das Jobcenter ist zuständig für Bürgergeld, Arbeitsvermittlung und Beschäftigungsförderung.',
            'booking_steps': json.dumps([f'Kontaktieren Sie das Jobcenter {city_de}', 'Hotline anrufen oder persönlich vorbeikommen', 'Termine werden in der Regel telefonisch oder per Brief vereinbart', 'Einige Leistungen ohne Termin verfügbar']),
            'documents_required': json.dumps(['Personalausweis oder Reisepass', 'Meldebescheinigung', 'Arbeitserlaubnis (falls zutreffend)', 'Unterlagen früherer Beschäftigung']),
            'common_mistakes': json.dumps(['Arbeitssuchend-Meldung zu spät', 'Termin ohne Absage versäumen']),
            'timing_patterns': json.dumps({'best_times': 'Vormittags', 'note': 'Direkt kontaktieren für Terminvereinbarung'}),
            'tips': json.dumps(['Vor Beginn der Arbeitslosigkeit arbeitssuchend melden', 'Alle Unterlagen zum ersten Gespräch mitbringen', 'Alle Schreiben vom Jobcenter aufbewahren']),
        },
        'ua': {
            'title': f'Запис до Центру зайнятості {city_ua}',
            'description': 'Центр зайнятості займається виплатами Bürgergeld, допомогою з працевлаштуванням та зайнятістю.',
            'booking_steps': json.dumps([f'Зверніться до Центру зайнятості {city_ua}', 'Зателефонуйте або прийдіть особисто', 'Записи оформлюються по телефону або листом', 'Деякі послуги доступні без запису']),
            'documents_required': json.dumps(['Паспорт або посвідчення особи', 'Довідка про реєстрацію (Meldebescheinigung)', 'Дозвіл на роботу (якщо потрібен)', 'Документи з попереднього місця роботи']),
            'common_mistakes': json.dumps(['Несвоєчасна реєстрація як шукач роботи', 'Пропуск запису без попередження']),
            'timing_patterns': json.dumps({'best_times': 'Ранкові години', 'note': 'Зверніться безпосередньо для запису'}),
            'tips': json.dumps(['Зареєструйтесь до початку безробіття', 'Візьміть усі документи на першу зустріч', 'Зберігайте всю кореспонденцію від Jobcenter']),
        },
        'pl': {
            'title': f'Rezerwacja w Jobcenter {city_pl}',
            'description': 'Jobcenter zajmuje się Bürgergeld, pośrednictwem pracy i pomocą w zatrudnieniu.',
            'booking_steps': json.dumps([f'Skontaktuj się z Jobcenter {city_pl}', 'Zadzwoń lub przyjdź osobiście', 'Wizyty umawiane telefonicznie lub listownie', 'Niektóre usługi bez wizyty']),
            'documents_required': json.dumps(['Dowód lub paszport', 'Zaświadczenie o zameldowaniu (Meldebescheinigung)', 'Pozwolenie na pracę (jeśli dotyczy)', 'Dokumenty z poprzedniego zatrudnienia']),
            'common_mistakes': json.dumps(['Zbyt późna rejestracja jako poszukujący pracy', 'Niestawienie się bez uprzedzenia']),
            'timing_patterns': json.dumps({'best_times': 'Godziny poranne', 'note': 'Skontaktuj się bezpośrednio w sprawie wizyty'}),
            'tips': json.dumps(['Zarejestruj się przed utratą pracy', 'Zabierz wszystkie dokumenty na pierwsze spotkanie', 'Zachowuj całą korespondencję z Jobcenter']),
        },
        'tr': {
            'title': f"Jobcenter {city_tr}'de Randevu",
            'description': 'Jobcenter Bürgergeld, istihdam hizmetleri ve iş bulma ile ilgilenir.',
            'booking_steps': json.dumps([f'{city_tr} Jobcenter ile iletişime geçin', 'Hattı arayın veya şahsen gidin', 'Randevular telefon veya mektupla ayarlanır', 'Bazı hizmetler randevusuz kullanılabilir']),
            'documents_required': json.dumps(['Kimlik veya pasaport', 'İkamet kaydı belgesi (Meldebescheinigung)', 'Çalışma izni (gerekiyorsa)', 'Önceki iş belgeleri']),
            'common_mistakes': json.dumps(['İş arayan kaydını zamanında yapmamak', 'Haber vermeden randevuyu kaçırmak']),
            'timing_patterns': json.dumps({'best_times': 'Sabah saatleri', 'note': 'Randevu için doğrudan iletişime geçin'}),
            'tips': json.dumps(['İşsizlik başlamadan önce kaydolun', 'İlk görüşmeye tüm belgeleri getirin', 'Jobcenter yazışmalarını saklayın']),
        },
        'ar': {
            'title': f'حجز موعد في مركز التوظيف {city_ar}',
            'description': 'يتعامل مركز التوظيف مع Bürgergeld وخدمات التوظيف والمساعدة في إيجاد عمل.',
            'booking_steps': json.dumps([f'تواصل مع مركز التوظيف في {city_ar}', 'اتصل بالخط الساخن أو قم بزيارة شخصية', 'يتم ترتيب المواعيد عبر الهاتف أو الرسائل', 'بعض الخدمات متاحة بدون موعد']),
            'documents_required': json.dumps(['هوية أو جواز سفر', 'شهادة تسجيل السكن (Meldebescheinigung)', 'تصريح عمل (إن وجد)', 'مستندات العمل السابق']),
            'common_mistakes': json.dumps(['عدم التسجيل كباحث عن عمل في الوقت المناسب', 'تفويت الموعد دون إشعار']),
            'timing_patterns': json.dumps({'best_times': 'ساعات الصباح', 'note': 'تواصل مباشرة لحجز موعد'}),
            'tips': json.dumps(['سجل كباحث عن عمل قبل البطالة', 'أحضر جميع المستندات في أول لقاء', 'احتفظ بجميع مراسلات Jobcenter']),
        },
    }


def _build_familienkasse_knowledge(city_en, city_de, city_ua, city_pl, city_tr, city_ar):
    return {
        'en': {
            'title': f'Booking at Familienkasse {city_en}',
            'description': 'The Family Benefits Office handles child benefits (Kindergeld), Kinderzuschlag, and family allowances.',
            'booking_steps': json.dumps(['Go to arbeitsagentur.de', 'Select "Familie und Kinder"', 'Choose your service type (Kindergeld, Kinderzuschlag, etc.)', 'Book appointment online or by phone']),
            'documents_required': json.dumps(['ID or passport for all family members', 'Birth certificates of children', 'Residence registration (Meldebescheinigung)', 'Work permit or visa if applicable', 'Bank account details (IBAN)']),
            'common_mistakes': json.dumps(['Applying too late after child birth — apply within first month', 'Missing required certified translations of foreign documents']),
            'timing_patterns': json.dumps({'best_times': 'Morning hours', 'note': 'Online application often faster than in-person'}),
            'tips': json.dumps(['Apply within the first month after birth', 'Use online form when possible', 'Keep payment receipts and all correspondence']),
        },
        'de': {
            'title': f'Termin bei der Familienkasse {city_de}',
            'description': 'Die Familienkasse ist zuständig für Kindergeld, Kinderzuschlag und Familienleistungen.',
            'booking_steps': json.dumps(['Gehen Sie zu arbeitsagentur.de', '"Familie und Kinder" auswählen', 'Gewünschte Leistung wählen (Kindergeld, Kinderzuschlag usw.)', 'Termin online oder telefonisch buchen']),
            'documents_required': json.dumps(['Personalausweis/Reisepass aller Familienmitglieder', 'Geburtsurkunden der Kinder', 'Meldebescheinigung', 'Arbeitserlaubnis/Visum falls zutreffend', 'IBAN']),
            'common_mistakes': json.dumps(['Zu späte Beantragung nach der Geburt — innerhalb des ersten Monats stellen', 'Fehlende beglaubigte Übersetzungen ausländischer Dokumente']),
            'timing_patterns': json.dumps({'best_times': 'Vormittags', 'note': 'Online-Antrag oft schneller als Besuch vor Ort'}),
            'tips': json.dumps(['Innerhalb des ersten Monats nach Geburt beantragen', 'Online-Formular nutzen wenn möglich', 'Zahlungsnachweise und Schreiben aufbewahren']),
        },
        'ua': {
            'title': f'Запис до Сімейної каси {city_ua}',
            'description': 'Сімейна каса займається дитячими виплатами (Kindergeld), Kinderzuschlag та сімейними допомогами.',
            'booking_steps': json.dumps(['Перейдіть на arbeitsagentur.de', 'Виберіть "Familie und Kinder"', 'Оберіть тип послуги (Kindergeld, Kinderzuschlag тощо)', 'Запишіться онлайн або по телефону']),
            'documents_required': json.dumps(['Паспорт/посвідчення всіх членів сім\'ї', 'Свідоцтва про народження дітей', 'Довідка про реєстрацію (Meldebescheinigung)', 'Дозвіл на роботу/віза (якщо потрібен)', 'Номер рахунку IBAN']),
            'common_mistakes': json.dumps(['Занадто пізня подача — подайте протягом першого місяця після народження', 'Відсутність завірених перекладів іноземних документів']),
            'timing_patterns': json.dumps({'best_times': 'Ранкові години', 'note': 'Онлайн-заява часто швидша за особистий візит'}),
            'tips': json.dumps(['Подайте протягом першого місяця після народження', 'Використовуйте онлайн-форму коли можливо', 'Зберігайте квитанції про оплату та кореспонденцію']),
        },
        'pl': {
            'title': f'Rezerwacja w Familienkasse {city_pl}',
            'description': 'Kasa Rodzinna zajmuje się zasiłkami na dzieci (Kindergeld), Kinderzuschlag i świadczeniami rodzinnymi.',
            'booking_steps': json.dumps(['Wejdź na arbeitsagentur.de', 'Wybierz "Familie und Kinder"', 'Wybierz rodzaj usługi (Kindergeld, Kinderzuschlag itp.)', 'Umów wizytę online lub telefonicznie']),
            'documents_required': json.dumps(['Dowód/paszport wszystkich członków rodziny', 'Akty urodzenia dzieci', 'Zaświadczenie o zameldowaniu (Meldebescheinigung)', 'Pozwolenie na pracę/wiza jeśli dotyczy', 'Numer konta IBAN']),
            'common_mistakes': json.dumps(['Zbyt późne złożenie — złóż w ciągu pierwszego miesiąca po urodzeniu', 'Brak certyfikowanych tłumaczeń zagranicznych dokumentów']),
            'timing_patterns': json.dumps({'best_times': 'Godziny poranne', 'note': 'Wniosek online często szybszy niż wizyta osobista'}),
            'tips': json.dumps(['Złóż wniosek w ciągu pierwszego miesiąca po urodzeniu', 'Korzystaj z formularza online', 'Zachowuj potwierdzenia płatności i całą korespondencję']),
        },
        'tr': {
            'title': f"Familienkasse {city_tr}'de Randevu",
            'description': 'Aile Yardımları Ofisi çocuk yardımı (Kindergeld), Kinderzuschlag ve aile ödeneklerini yönetir.',
            'booking_steps': json.dumps(["arbeitsagentur.de'ye gidin", '"Familie und Kinder" seçin', 'Hizmet türünüzü seçin (Kindergeld, Kinderzuschlag vb.)', 'Online veya telefonla randevu alın']),
            'documents_required': json.dumps(['Tüm aile üyelerinin kimlik/pasaportu', 'Çocukların doğum belgeleri', 'İkamet kaydı (Meldebescheinigung)', 'Çalışma izni/vize gerekiyorsa', 'IBAN hesap numarası']),
            'common_mistakes': json.dumps(['Çok geç başvurmak — doğumdan sonra ilk ay içinde başvurun', 'Yabancı belgelerin onaylı çevirilerinin eksikliği']),
            'timing_patterns': json.dumps({'best_times': 'Sabah saatleri', 'note': 'Online başvuru genellikle şahsen gitmekten daha hızlı'}),
            'tips': json.dumps(['Doğumdan sonra ilk ay içinde başvurun', 'Mümkünse online formu kullanın', 'Ödeme makbuzlarını ve yazışmaları saklayın']),
        },
        'ar': {
            'title': f'حجز موعد في صندوق الأسرة {city_ar}',
            'description': 'يتعامل صندوق الأسرة مع إعانات الأطفال (Kindergeld) و Kinderzuschlag والبدلات العائلية.',
            'booking_steps': json.dumps(['اذهب إلى arbeitsagentur.de', 'اختر "Familie und Kinder"', 'اختر نوع الخدمة (Kindergeld أو Kinderzuschlag وما إلى ذلك)', 'احجز موعدًا عبر الإنترنت أو الهاتف']),
            'documents_required': json.dumps(['هوية/جواز سفر جميع أفراد الأسرة', 'شهادات ميلاد الأطفال', 'تسجيل السكن (Meldebescheinigung)', 'تصريح عمل/تأشيرة إن وجد', 'رقم الحساب البنكي IBAN']),
            'common_mistakes': json.dumps(['التقديم المتأخر — قدم خلال الشهر الأول بعد الولادة', 'نقص الترجمات المعتمدة للوثائق الأجنبية']),
            'timing_patterns': json.dumps({'best_times': 'ساعات الصباح', 'note': 'الطلب عبر الإنترنت غالبًا أسرع من الحضور الشخصي'}),
            'tips': json.dumps(['قدم خلال الشهر الأول بعد الولادة', 'استخدم النموذج الإلكتروني عند الإمكان', 'احتفظ بإيصالات الدفع وجميع المراسلات']),
        },
    }


def _seed_standesamt_knowledge(cursor, now, city_code):
    """Seed Standesamt knowledge for any city (uses city_code to derive display name from cities table)."""
    cursor.execute("SELECT name_en, name_de, name_ua, name_pl, name_tr, name_ar FROM cities WHERE code = ?", (city_code,))
    row = cursor.fetchone()
    if row:
        city_en, city_de, city_ua, city_pl, city_tr, city_ar = (
            row['name_en'], row['name_de'], row['name_ua'] or row['name_en'],
            row['name_pl'] or row['name_en'], row['name_tr'] or row['name_en'],
            row['name_ar'] or row['name_en'],
        )
    else:
        city_en = city_de = city_ua = city_pl = city_tr = city_ar = city_code.capitalize()

    knowledge = {
        'en': {
            'title': f'Booking at Standesamt {city_en}',
            'description': 'The Civil Registry Office handles marriage registration, birth certificates, death certificates, name changes, and apostilles.',
            'booking_steps': json.dumps([f'Go to the official {city_en} Standesamt appointment portal', 'Select your service (marriage, birth certificate, etc.)', 'Choose an available date and time', 'Enter your personal details', 'Confirm booking and note your appointment number']),
            'documents_required': json.dumps(['Valid passports for all parties involved', 'Birth certificates', 'Certificate of no impediment to marriage (if applicable)', 'Current residence registration (Meldebescheinigung)', 'Divorce decree if previously married']),
            'common_mistakes': json.dumps(['Not booking far enough in advance for marriage ceremonies', 'Forgetting certified translations of foreign documents', 'Missing apostille on foreign documents']),
            'timing_patterns': json.dumps({'best_times': 'Morning hours', 'best_days': 'Tuesday to Thursday', 'note': 'Marriage dates book up months in advance'}),
            'tips': json.dumps(['Book marriage appointments 3–6 months ahead', 'Have all foreign documents translated and apostilled', 'Ask about required document list specific to your situation']),
        },
        'de': {
            'title': f'Termin beim Standesamt {city_de}',
            'description': 'Das Standesamt ist zuständig für Eheschließungen, Geburtsurkunden, Sterbeurkunden, Namensänderungen und Apostillen.',
            'booking_steps': json.dumps([f'Rufen Sie das offizielle Terminportal des Standesamts {city_de} auf', 'Gewünschten Dienst auswählen (Hochzeit, Geburtsurkunde usw.)', 'Verfügbares Datum und Uhrzeit wählen', 'Persönliche Daten eingeben', 'Buchung bestätigen und Terminnummer notieren']),
            'documents_required': json.dumps(['Gültige Reisepässe aller Beteiligten', 'Geburtsurkunden', 'Ehefähigkeitszeugnis (falls zutreffend)', 'Aktuelle Meldebescheinigung', 'Scheidungsurteil bei Vorehe']),
            'common_mistakes': json.dumps(['Zu kurzfristige Buchung für Eheschließungen', 'Fehlende beglaubigte Übersetzungen ausländischer Dokumente', 'Fehlende Apostille auf ausländischen Dokumenten']),
            'timing_patterns': json.dumps({'best_times': 'Vormittags', 'best_days': 'Dienstag bis Donnerstag', 'note': 'Hochzeitstermine sind Monate im Voraus ausgebucht'}),
            'tips': json.dumps(['Hochzeitstermin 3–6 Monate im Voraus buchen', 'Ausländische Dokumente übersetzen und mit Apostille versehen lassen', 'Spezifische Dokumentenliste beim Amt erfragen']),
        },
        'ua': {
            'title': f'Запис до Відділу РАЦС {city_ua}',
            'description': 'Відділ РАЦС займається реєстрацією шлюбів, свідоцтвами про народження, смерть, зміною імені та апостилями.',
            'booking_steps': json.dumps([f'Перейдіть на офіційний портал запису Відділу РАЦС {city_ua}', 'Виберіть потрібну послугу (шлюб, свідоцтво про народження тощо)', 'Оберіть дату та час', 'Введіть особисті дані', 'Підтвердіть запис та збережіть номер']),
            'documents_required': json.dumps(['Дійсні паспорти всіх залучених сторін', 'Свідоцтва про народження', 'Свідоцтво про відсутність перешкод для шлюбу (якщо потрібно)', 'Поточна довідка про реєстрацію (Meldebescheinigung)', 'Рішення про розлучення при попередньому шлюбі']),
            'common_mistakes': json.dumps(['Занадто пізнє бронювання для шлюбних церемоній', 'Відсутність завірених перекладів іноземних документів', 'Відсутність апостиля на іноземних документах']),
            'timing_patterns': json.dumps({'best_times': 'Ранкові години', 'best_days': 'Вівторок–четвер', 'note': 'Дати шлюбних церемоній розбираються за місяці наперед'}),
            'tips': json.dumps(['Бронюйте шлюбний запис за 3–6 місяців', 'Перекладіть та апостилюйте всі іноземні документи', 'Уточніть список документів для вашої ситуації']),
        },
        'pl': {
            'title': f'Rezerwacja w Standesamt {city_pl}',
            'description': 'Urząd Stanu Cywilnego zajmuje się zawieraniem małżeństw, aktami urodzenia, aktami zgonu, zmianą nazwiska i apostille.',
            'booking_steps': json.dumps([f'Wejdź na oficjalny portal rezerwacji Standesamt {city_pl}', 'Wybierz usługę (ślub, akt urodzenia itp.)', 'Wybierz dostępny termin', 'Podaj dane osobowe', 'Potwierdź rezerwację i zapisz numer']),
            'documents_required': json.dumps(['Ważne paszporty wszystkich stron', 'Akty urodzenia', 'Zaświadczenie o zdolności do zawarcia małżeństwa (jeśli dotyczy)', 'Aktualne zaświadczenie o zameldowaniu', 'Wyrok rozwodowy jeśli wcześniej w związku małżeńskim']),
            'common_mistakes': json.dumps(['Zbyt późna rezerwacja ceremonii ślubnej', 'Brak certyfikowanych tłumaczeń zagranicznych dokumentów', 'Brak apostille na zagranicznych dokumentach']),
            'timing_patterns': json.dumps({'best_times': 'Godziny poranne', 'best_days': 'Wtorek–czwartek', 'note': 'Terminy ślubów rezerwowane z miesięcznym wyprzedzeniem'}),
            'tips': json.dumps(['Rezerwuj ślub 3–6 miesięcy wcześniej', 'Przetłumacz i apostilluj wszystkie zagraniczne dokumenty', 'Zapytaj o konkretną listę dokumentów dla twojej sytuacji']),
        },
        'tr': {
            'title': f"Standesamt {city_tr}'de Randevu",
            'description': 'Nüfus Müdürlüğü evlilik tescili, doğum belgesi, ölüm belgesi, isim değişikliği ve apostil işlemleriyle ilgilenir.',
            'booking_steps': json.dumps([f'{city_tr} Standesamt resmi randevu portalına gidin', 'Hizmetinizi seçin (evlilik, doğum belgesi vb.)', 'Uygun tarih ve saat seçin', 'Kişisel bilgilerinizi girin', 'Rezervasyonu onaylayın ve numaranızı kaydedin']),
            'documents_required': json.dumps(['Tüm tarafların geçerli pasaportları', 'Doğum belgeleri', 'Evlenmeye engel olmadığına dair belge (gerekiyorsa)', 'Güncel ikamet kaydı (Meldebescheinigung)', 'Önceki evlilikten boşanma kararı']),
            'common_mistakes': json.dumps(['Düğün töreni için çok geç rezervasyon', 'Yabancı belgelerin onaylı çevirilerinin eksikliği', 'Yabancı belgelerde apostil eksikliği']),
            'timing_patterns': json.dumps({'best_times': 'Sabah saatleri', 'best_days': 'Salı–Perşembe', 'note': 'Evlilik tarihleri aylarca önceden doluyor'}),
            'tips': json.dumps(['Evlilik randevusunu 3–6 ay önceden alın', 'Tüm yabancı belgeleri çevirin ve apostil yaptırın', 'Durumunuza özel belge listesini sorun']),
        },
        'ar': {
            'title': f'حجز موعد في مكتب السجل المدني {city_ar}',
            'description': 'يتعامل مكتب السجل المدني مع تسجيل الزواج وشهادات الميلاد والوفاة وتغيير الاسم والأبوستيل.',
            'booking_steps': json.dumps([f'اذهب إلى بوابة الحجز الرسمية لمكتب السجل المدني في {city_ar}', 'اختر خدمتك (زواج، شهادة ميلاد، إلخ)', 'اختر تاريخًا ووقتًا متاحًا', 'أدخل بياناتك الشخصية', 'أكد الحجز وسجل رقم الموعد']),
            'documents_required': json.dumps(['جوازات سفر سارية لجميع الأطراف', 'شهادات الميلاد', 'شهادة خلو موانع الزواج (إن وجدت)', 'تسجيل السكن الحالي (Meldebescheinigung)', 'حكم الطلاق عند الزواج السابق']),
            'common_mistakes': json.dumps(['الحجز المتأخر لمراسم الزفاف', 'نقص الترجمات المعتمدة للوثائق الأجنبية', 'غياب الأبوستيل على الوثائق الأجنبية']),
            'timing_patterns': json.dumps({'best_times': 'ساعات الصباح', 'best_days': 'الثلاثاء–الخميس', 'note': 'تواريخ الزفاف تُحجز قبل أشهر'}),
            'tips': json.dumps(['احجز موعد الزفاف قبل 3–6 أشهر', 'ترجم جميع الوثائق الأجنبية وأضف الأبوستيل', 'اسأل عن قائمة الوثائق المطلوبة لوضعك']),
        },
    }
    _insert_city_knowledge(cursor, now, city_code, 'standesamt', knowledge)


# ═══════════════════════════════════════════════════
# New city seed functions
# ═══════════════════════════════════════════════════

_NEW_CITIES = {
    'muenchen': {
        'row': ('muenchen', 'de', 'München', 'Munich', 'Мюнхен', 'Monachium', 'Münih', 'ميونيخ'),
        'authorities': [
            ('buergeramt', 'Bürgerbüro', 'Citizens Office', 'Бюргербюро', 'Biuro Obywatelskie', 'Vatandaşlık Ofisi', 'مكتب المواطنين', 'https://www48.muenchen.de/buergeransicht/', 'muenchen_kvr'),
            ('auslaenderbehoerde', 'Ausländerbehörde (KVR)', 'Immigration Office (KVR)', 'Міграційна служба (KVR)', 'Urząd ds. Cudzoziemców (KVR)', 'Yabancılar Dairesi (KVR)', 'مكتب شؤون الأجانب (KVR)', 'https://www48.muenchen.de/buergeransicht/', 'muenchen_kvr'),
            ('niederlassungserlaubnis', 'Niederlassungserlaubnis (KVR)', 'Permanent Residence (KVR)', 'Постійне проживання (KVR)', 'Pobyt stały (KVR)', 'Süresiz Oturma (KVR)', 'إقامة دائمة (KVR)', 'https://www48.muenchen.de/buergeransicht/', 'muenchen_kvr'),
            ('personalausweis', 'Personalausweis München', 'German ID Card Munich', 'Посвідчення особи Мюнхен', 'Dowód osobisty Monachium', 'Kimlik Kartı Münih', 'بطاقة الهوية ميونيخ', 'https://www48.muenchen.de/buergeransicht/?serviceId=1063441', 'muenchen_kvr'),
            ('reisepass', 'Reisepass München', 'German Passport Munich', 'Закордонний паспорт Мюнхен', 'Paszport Monachium', 'Pasaport Münih', 'جواز السفر ميونيخ', 'https://www48.muenchen.de/buergeransicht/?serviceId=1063453', 'muenchen_kvr'),
        ],
        'names': ('Munich', 'München', 'Мюнхен', 'Monachium', 'Münih', 'ميونيخ'),
    },
    # Hamburg removed from Premium cities — entry intentionally omitted.
    'frankfurt': {
        'row': ('frankfurt', 'de', 'Frankfurt am Main', 'Frankfurt', 'Франкфурт', 'Frankfurt nad Menem', 'Frankfurt', 'فرانكفورت'),
        'authorities': [
            ('buergeramt', 'Bürgerbüro Frankfurt', 'Citizens Office Frankfurt', 'Бюргербюро Франкфурт', 'Biuro Obywatelskie Frankfurt', 'Vatandaşlık Ofisi Frankfurt', 'مكتب المواطنين فرانكفورت', 'https://tevis.ekom21.de/fra/select2?md=13', 'frankfurt_service'),
            ('auslaenderbehoerde', 'Ausländerbehörde Frankfurt', 'Immigration Office Frankfurt', 'Міграційна служба Франкфурт', 'Urząd ds. Cudzoziemców Frankfurt', 'Yabancılar Dairesi Frankfurt', 'مكتب شؤون الأجانب فرانكفورت', 'https://tevis.ekom21.de/fra/select2?md=5', 'frankfurt_service'),
            ('niederlassungserlaubnis', 'Niederlassungserlaubnis Frankfurt', 'Permanent Residence Frankfurt', 'Постійне проживання Франкфурт', 'Pobyt stały Frankfurt', 'Süresiz Oturma Frankfurt', 'إقامة دائمة فرانكفورت', 'https://tevis.ekom21.de/fra/select2?md=5', 'frankfurt_service'),
            ('fuehrerschein', 'Fahrerlaubnisbehörde Frankfurt', 'Driver\'s License Office Frankfurt', 'Конвертація прав Франкфурт', 'Urząd Prawa Jazdy Frankfurt', 'Ehliyet Dairesi Frankfurt', 'مكتب رخصة القيادة فرانكفورت', 'https://tevis.ekom21.de/fra/select2?md=6', 'frankfurt_service'),
            ('personalausweis', 'Personalausweis Frankfurt', 'German ID Card Frankfurt', 'Посвідчення особи Франкфурт', 'Dowód osobisty Frankfurt', 'Kimlik Kartı Frankfurt', 'بطاقة الهوية فرانكفورت', 'https://tevis.ekom21.de/fra/select2?md=13', 'frankfurt_service'),
            ('reisepass', 'Reisepass Frankfurt', 'German Passport Frankfurt', 'Закордонний паспорт Франкфурт', 'Paszport Frankfurt', 'Pasaport Frankfurt', 'جواز السفر فرانكفورت', 'https://tevis.ekom21.de/fra/select2?md=13', 'frankfurt_service'),
        ],
        'names': ('Frankfurt', 'Frankfurt am Main', 'Франкфурт', 'Frankfurt nad Menem', 'Frankfurt', 'فرانكفورت'),
    },
    'koeln': {
        'row': ('koeln', 'de', 'Köln', 'Cologne', 'Кельн', 'Kolonia', 'Köln', 'كولونيا'),
        'authorities': [
            ('buergeramt', 'Bürgerbüro Köln', 'Citizens Office Cologne', 'Бюргербюро Кельн', 'Biuro Obywatelskie Kolonia', 'Vatandaşlık Ofisi Köln', 'مكتب المواطنين كولونيا', 'https://tevis.krzn.de/tevisweb190/', 'koeln_service'),
            ('auslaenderbehoerde', 'Ausländerbehörde Köln', 'Immigration Office Cologne', 'Міграційна служба Кельн', 'Urząd ds. Cudzoziemców Kolonia', 'Yabancılar Dairesi Köln', 'مكتب شؤون الأجانب كولونيا', 'https://tevis.krzn.de/tevisweb190/', 'koeln_service'),
            ('niederlassungserlaubnis', 'Niederlassungserlaubnis Köln', 'Permanent Residence Cologne', 'Постійне проживання Кельн', 'Pobyt stały Kolonia', 'Süresiz Oturma Köln', 'إقامة دائمة كولونيا', 'https://tevis.krzn.de/tevisweb190/', 'koeln_service'),
            ('fuehrerschein', 'Führerscheinstelle Köln', 'Driver\'s License Office Cologne', 'Конвертація прав Кельн', 'Urząd Prawa Jazdy Kolonia', 'Ehliyet Dairesi Köln', 'مكتب رخصة القيادة كولونيا', 'https://tevis.krzn.de/tevisweb190/', 'koeln_service'),
            ('personalausweis', 'Personalausweis Köln', 'German ID Card Cologne', 'Посвідчення особи Кельн', 'Dowód osobisty Kolonia', 'Kimlik Kartı Köln', 'بطاقة الهوية كولونيا', 'https://tevis.krzn.de/tevisweb190/', 'koeln_service'),
            ('reisepass', 'Reisepass Köln', 'German Passport Cologne', 'Закордонний паспорт Кельн', 'Paszport Kolonia', 'Pasaport Köln', 'جواز السفر كولونيا', 'https://tevis.krzn.de/tevisweb190/', 'koeln_service'),
        ],
        'names': ('Cologne', 'Köln', 'Кельн', 'Kolonia', 'Köln', 'كولونيا'),
    },
    'duesseldorf': {
        'row': ('duesseldorf', 'de', 'Düsseldorf', 'Dusseldorf', 'Дюссельдорф', 'Düsseldorf', 'Düsseldorf', 'دوسلدورف'),
        'authorities': [
            ('buergeramt', 'Bürgerbüro Düsseldorf', 'Citizens Office Düsseldorf', 'Бюргербюро Дюссельдорф', 'Biuro Obywatelskie Düsseldorf', 'Vatandaşlık Ofisi Düsseldorf', 'مكتب المواطنين دوسلدورف', 'https://termine.duesseldorf.de/select2?md=4', 'duesseldorf_tevis'),
            ('auslaenderbehoerde', 'Ausländerbehörde Düsseldorf', 'Immigration Office Düsseldorf', 'Міграційна служба Дюссельдорф', 'Urząd ds. Cudzoziemców Düsseldorf', 'Yabancılar Dairesi Düsseldorf', 'مكتب شؤون الأجانب دوسلدورف', 'https://termine.duesseldorf.de/select2?md=1', 'duesseldorf_tevis'),
            ('niederlassungserlaubnis', 'Niederlassungserlaubnis Düsseldorf', 'Permanent Residence Düsseldorf', 'Постійне проживання Дюссельдорф', 'Pobyt stały Düsseldorf', 'Süresiz Oturma Düsseldorf', 'إقامة دائمة دوسلدورف', 'https://termine.duesseldorf.de/select2?md=1', 'duesseldorf_tevis'),
            ('fuehrerschein', 'Fahrerlaubnisbehörde Düsseldorf', 'Driver\'s License Office Düsseldorf', 'Конвертація прав Дюссельдорф', 'Urząd Prawa Jazdy Düsseldorf', 'Ehliyet Dairesi Düsseldorf', 'مكتب رخصة القيادة دوسلدورف', 'https://termine.duesseldorf.de/select2?md=3', 'duesseldorf_tevis'),
            ('personalausweis', 'Personalausweis Düsseldorf', 'German ID Card Düsseldorf', 'Посвідчення особи Дюссельдорф', 'Dowód osobisty Düsseldorf', 'Kimlik Kartı Düsseldorf', 'بطاقة الهوية دوسلدورف', 'https://termine.duesseldorf.de/select2?md=4', 'duesseldorf_tevis'),
            ('reisepass', 'Reisepass Düsseldorf', 'German Passport Düsseldorf', 'Закордонний паспорт Дюссельдорф', 'Paszport Düsseldorf', 'Pasaport Düsseldorf', 'جواز السفر دوسلدورف', 'https://termine.duesseldorf.de/select2?md=4', 'duesseldorf_tevis'),
        ],
        'names': ('Dusseldorf', 'Düsseldorf', 'Дюссельдорф', 'Düsseldorf', 'Düsseldorf', 'دوسلدورف'),
    },
    'dortmund': {
        'row': ('dortmund', 'de', 'Dortmund', 'Dortmund', 'Дортмунд', 'Dortmund', 'Dortmund', 'دورتموند'),
        'authorities': [
            ('buergeramt', 'Stadtbüro Dortmund', 'Citizens Office Dortmund', 'Міський офіс Дортмунд', 'Urząd Miejski Dortmund', 'Vatandaşlık Ofisi Dortmund', 'مكتب المواطنين دورتموند', 'https://dortmund.termine-reservieren.de/select2?md=3', 'dortmund_tevis'),
            ('auslaenderbehoerde', 'Einwohnermeldewesen Dortmund (Aufenthaltstitel)', 'Immigration Services Dortmund', 'Міграційні послуги Дортмунд', 'Urząd ds. Cudzoziemców Dortmund', 'Yabancılar Hizmetleri Dortmund', 'خدمات الأجانب دورتموند', 'https://dortmund.termine-reservieren.de/select2?md=3', 'dortmund_tevis'),
            ('niederlassungserlaubnis', 'Niederlassungserlaubnis Dortmund', 'Permanent Residence Dortmund', 'Постійне проживання Дортмунд', 'Pobyt stały Dortmund', 'Süresiz Oturma Dortmund', 'إقامة دائمة دورتموند', 'https://dortmund.termine-reservieren.de/select2?md=3', 'dortmund_tevis'),
            ('personalausweis', 'Personalausweis Dortmund', 'German ID Card Dortmund', 'Посвідчення особи Дортмунд', 'Dowód osobisty Dortmund', 'Kimlik Kartı Dortmund', 'بطاقة الهوية دورتموند', 'https://dortmund.termine-reservieren.de/select2?md=3', 'dortmund_tevis'),
            ('reisepass', 'Reisepass Dortmund', 'German Passport Dortmund', 'Закордонний паспорт Дортмунд', 'Paszport Dortmund', 'Pasaport Dortmund', 'جواز السفر دورتموند', 'https://dortmund.termine-reservieren.de/select2?md=3', 'dortmund_tevis'),
        ],
        'names': ('Dortmund', 'Dortmund', 'Дортмунд', 'Dortmund', 'Dortmund', 'دورتموند'),
    },
}


def _seed_new_city(city_code: str):
    """Generic seeder for non-Berlin cities using the _NEW_CITIES config."""
    cfg = _NEW_CITIES[city_code]
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("SELECT COUNT(*) as count FROM cities WHERE code = ?", (city_code,))
        city_exists = cursor.fetchone()['count'] > 0

        if not city_exists:
            cursor.execute("""
                INSERT INTO cities (code, country_code, name_de, name_en, name_ua, name_pl, name_tr, name_ar, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (*cfg['row'], now))

        # Always ensure all authorities exist (INSERT OR IGNORE — idempotent)
        for auth in cfg['authorities']:
            cursor.execute("""
                INSERT OR IGNORE INTO authorities
                (city_code, authority_type, name_de, name_en, name_ua, name_pl, name_tr, name_ar, booking_url, booking_system, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (city_code, *auth, now))

        # Knowledge (always upsert)
        city_en, city_de, city_ua, city_pl, city_tr, city_ar = cfg['names']
        builders = {
            'buergeramt': _build_buergeramt_knowledge,
            'auslaenderbehoerde': _build_auslaenderbehoerde_knowledge,
            'jobcenter': _build_jobcenter_knowledge,
            'familienkasse': _build_familienkasse_knowledge,
        }
        for auth_type, builder in builders.items():
            _insert_city_knowledge(cursor, now, city_code, auth_type,
                                   builder(city_en, city_de, city_ua, city_pl, city_tr, city_ar))
        _seed_standesamt_knowledge(cursor, now, city_code)

        conn.commit()
    logger.info("Termin DB: %s data seeded (city_new=%s)", city_code, not city_exists)


def seed_muenchen_data():
    _seed_new_city('muenchen')



def seed_frankfurt_data():
    _seed_new_city('frankfurt')


def seed_koeln_data():
    _seed_new_city('koeln')


def seed_duesseldorf_data():
    _seed_new_city('duesseldorf')


def seed_dortmund_data():
    _seed_new_city('dortmund')


def _migrate_muenchen_booking_urls():
    """One-time migration: update stale München booking_url values in the authorities table.

    The original seed used INSERT OR IGNORE so rows inserted with old
    www.muenchen.de/rathaus/… URLs were never updated when _NEW_CITIES changed
    to the correct www48.muenchen.de/buergeransicht/ portal.

    This migration runs on every startup but only modifies rows whose booking_url
    still contains the old muenchen.de/rathaus/ path.
    Safe to run multiple times — no-op when URLs are already correct.
    """
    # Authoritative München booking URLs from _NEW_CITIES
    _correct_urls = {
        auth[0]: auth[7]  # authority_type → booking_url (index 7 in the tuple)
        for auth in _NEW_CITIES.get("muenchen", {}).get("authorities", [])
    }
    if not _correct_urls:
        return
    try:
        with get_connection() as conn:
            updated = 0
            for auth_type, correct_url in _correct_urls.items():
                cursor = conn.execute(
                    """UPDATE authorities
                       SET booking_url = ?
                       WHERE city_code = 'muenchen'
                         AND authority_type = ?
                         AND booking_url != ?
                    """,
                    (correct_url, auth_type, correct_url),
                )
                if cursor.rowcount:
                    logger.warning(
                        "MUENCHEN_URL_MIGRATED | authority=%s updated booking_url to %s",
                        auth_type, correct_url,
                    )
                    updated += cursor.rowcount
            conn.commit()
            if updated:
                logger.warning(
                    "MUENCHEN_MIGRATION_DONE | %d row(s) updated to www48.muenchen.de",
                    updated,
                )
    except Exception as _mig_err:
        logger.error("MUENCHEN_MIGRATION_ERROR | %s", _mig_err)


def seed_all_cities():
    """Seed Berlin + all additional cities. Idempotent — safe to call on every startup."""
    seed_berlin_data()
    for city_code in _NEW_CITIES:
        try:
            _seed_new_city(city_code)
        except Exception as e:
            logger.warning("seed_all_cities: failed to seed %s — %s", city_code, e)
    # Fix stale München booking URLs that were locked in by INSERT OR IGNORE
    _migrate_muenchen_booking_urls()


# ═══════════════════════════════════════════════════
# CRUD helpers
# ═══════════════════════════════════════════════════

def get_user(telegram_id: str) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def get_users_with_active_monitoring() -> list:
    """Return all users that had Termin monitoring active at the time of last shutdown.
    Used by the startup resume routine to restart polling sessions."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT telegram_id, city, authority, language FROM users WHERE reminder_active = 1"
            )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error("get_users_with_active_monitoring ERROR: %s", e)
        return []


def get_entitled_users_for_watchdog() -> list:
    """Return users with a currently valid termin entitlement (paid_until > now).

    Unlike get_users_with_active_monitoring(), this queries the termin_entitlements
    table directly so the result is NOT affected by reminder_active being reset
    (e.g. via handle_pause_reminders / deactivate_reminder).  Used exclusively
    by the watchdog loop so it can restart monitoring for any entitled user whose
    poll session died, regardless of the reminder_active flag state.
    """
    try:
        # paid_until is stored as naive-UTC isoformat (datetime.utcnow().isoformat()).
        # We MUST compare with the same naive-UTC format so SQLite lexicographic
        # ordering works correctly.  Using datetime.now(timezone.utc) produces an
        # aware string ("...+00:00") which sorts differently from the naive string
        # ("...") and would incorrectly exclude or include entitlements.
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            cursor = conn.cursor()
            # Use entitlement city/authority as primary source (most reliable),
            # fall back to users table values via COALESCE.
            cursor.execute("""
                SELECT
                    u.telegram_id,
                    COALESCE(e.city, u.city)           AS city,
                    COALESCE(e.authority, u.authority) AS authority,
                    u.language
                FROM users u
                JOIN termin_entitlements e
                    ON CAST(e.user_id AS TEXT) = CAST(u.telegram_id AS TEXT)
                WHERE e.active = 1
                  AND (e.paid_until IS NULL OR e.paid_until > ?)
            """, (now,))
            rows = cursor.fetchall()
        # Filter out rows missing city or authority in Python to keep SQL simple
        result = []
        for row in rows:
            d = dict(row)
            if d.get("city") and d.get("authority"):
                result.append(d)
        return result
    except Exception as e:
        logger.error("get_entitled_users_for_watchdog ERROR: %s", e)
        return []


def create_user(telegram_id: str, language: str = 'en') -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT OR IGNORE INTO users (telegram_id, language, status, has_paid_document, has_paid_termin, created_at, updated_at)
            VALUES (?, ?, 'searching', 0, 0, ?, ?)
        """, (telegram_id, language, now, now))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def update_user(telegram_id: str, **kwargs) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        updates, values = [], []
        allowed = [
            'language', 'mode', 'city', 'authority', 'status',
            'has_paid_document', 'has_paid_termin', 'reminder_interval', 'reminder_active',
            'customer_email', 'termin_email_notified',
        ]
        for key, value in kwargs.items():
            if key in allowed:
                updates.append(f"{key} = ?")
                values.append(value)
        if updates:
            updates.append("updated_at = ?")
            values.append(now)
            values.append(telegram_id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ?", values)
            conn.commit()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def get_customer_email(telegram_id: str) -> str:
    """Return the stored Stripe customer email for a user, or empty string."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT customer_email FROM users WHERE telegram_id = ?",
                (str(telegram_id),),
            )
            row = cursor.fetchone()
        if row:
            return (row["customer_email"] or "").strip()
    except Exception as e:
        logger.warning("get_customer_email failed for %s: %s", telegram_id, e)
    return ""


def is_termin_email_notified(telegram_id: str) -> bool:
    """Return True if a termin slot-found email has already been sent to this user."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT termin_email_notified FROM users WHERE telegram_id = ?",
                (str(telegram_id),),
            )
            row = cursor.fetchone()
        if row:
            return bool(row["termin_email_notified"])
    except Exception as e:
        logger.warning("is_termin_email_notified failed for %s: %s", telegram_id, e)
    return False


def mark_termin_email_notified(telegram_id: str) -> None:
    """Mark that a termin slot-found email has been sent (anti-spam guard)."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET termin_email_notified = 1, updated_at = ? WHERE telegram_id = ?",
                (datetime.now(timezone.utc).isoformat(), str(telegram_id)),
            )
            conn.commit()
    except Exception as e:
        logger.warning("mark_termin_email_notified failed for %s: %s", telegram_id, e)


def reset_termin_email_notified(telegram_id: str) -> None:
    """Reset the email-notified flag so next slot found sends a new email.
    Called when user resumes search after a previous slot was missed."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET termin_email_notified = 0, updated_at = ? WHERE telegram_id = ?",
                (datetime.now(timezone.utc).isoformat(), str(telegram_id)),
            )
            conn.commit()
    except Exception as e:
        logger.warning("reset_termin_email_notified failed for %s: %s", telegram_id, e)


def get_cities() -> list:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cities WHERE is_active = 1")
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_authorities(city_code: str) -> list:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM authorities WHERE city_code = ? AND is_active = 1", (city_code,))
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_knowledge(city_code: str, authority_type: str, language: str) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM knowledge_base
            WHERE city_code = ? AND authority_type = ? AND language = ?
        """, (city_code, authority_type, language))
        row = cursor.fetchone()
        if not row:
            cursor.execute("""
                SELECT * FROM knowledge_base
                WHERE city_code = ? AND authority_type = ? AND language = 'en'
            """, (city_code, authority_type))
            row = cursor.fetchone()
    if row:
        result = dict(row)
        for field in ['booking_steps', 'documents_required', 'common_mistakes', 'tips']:
            if result.get(field):
                try:
                    result[field] = json.loads(result[field])
                except Exception:
                    pass
        if result.get('timing_patterns'):
            try:
                result['timing_patterns'] = json.loads(result['timing_patterns'])
            except Exception:
                pass
        return result
    return None


def get_authority_info(city_code: str, authority_type: str) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM authorities
            WHERE city_code = ? AND authority_type = ?
        """, (city_code, authority_type))
        row = cursor.fetchone()
    return dict(row) if row else None


def create_reminder(
    telegram_id: str,
    city_code: str,
    authority_type: str,
    interval_hours: int,
    profile_id: int = 1,
) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        # Deactivate only reminders for the same profile (other profile keeps running)
        cursor.execute(
            "UPDATE reminders SET is_active = 0 WHERE telegram_id = ? AND profile_id = ?",
            (telegram_id, profile_id),
        )
        cursor.execute(
            """
            INSERT INTO reminders
                (telegram_id, city_code, authority_type, interval_hours, is_active, created_at, profile_id)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (telegram_id, city_code, authority_type, interval_hours, now, profile_id),
        )
        conn.commit()
        update_user(telegram_id, reminder_active=1, reminder_interval=f"{interval_hours}h")
        reminder_id = cursor.lastrowid
        cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def deactivate_reminder(telegram_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE reminders SET is_active = 0 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
    update_user(telegram_id, reminder_active=0)


def get_active_reminders() -> list:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, a.booking_url, a.name_en
            FROM reminders r
            JOIN authorities a ON r.city_code = a.city_code AND r.authority_type = a.authority_type
            WHERE r.is_active = 1
        """)
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def update_reminder_sent(reminder_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("UPDATE reminders SET last_sent = ? WHERE id = ?", (now, reminder_id))
        conn.commit()


# ── Entitlements (Family Bundle V1) ──────────────────────────────────────────

def upsert_entitlement(
    user_id: str,
    plan: str,
    slots_total: int,
    stripe_session_id: str,
    paid_until: str | None = None,
    city: str | None = None,
    authority: str | None = None,
) -> None:
    """
    Insert entitlement row, silently ignore if stripe_session_id already exists.

    Access model:
    - active=1 and found_termin=0 => user can monitor
    - once a Termin is found, mark_termin_found() flips flags and entitlement ends

    city/authority: immutable payment-time values — NOT overwritten by UI navigation.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO termin_entitlements
                    (user_id, plan, slots_total, slots_used, stripe_session_id, active, found_termin, paid_until, city, authority)
                VALUES (?, ?, ?, 0, ?, 1, 0, ?, ?, ?)
                """,
                (str(user_id), plan, slots_total, stripe_session_id or None, paid_until,
                 city or None, authority or None),
            )
            if cursor.rowcount > 0:
                new_id = cursor.lastrowid
                cursor.execute(
                    "UPDATE termin_entitlements SET active = 0 WHERE user_id = ? AND active = 1 AND id != ?",
                    (str(user_id), new_id),
                )
            conn.commit()
        logger.info(
            "upsert_entitlement | user=%s plan=%s session=%s city=%s auth=%s inserted=%s",
            user_id, plan, stripe_session_id, city, authority, cursor.rowcount,
        )
    except Exception as e:
        logger.error("upsert_entitlement ERROR | user=%s err=%s", user_id, e)


def get_entitlement(user_id: str) -> dict | None:
    """Return the most recent entitlement row for a user, or None."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM termin_entitlements WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (str(user_id),),
            )
            row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error("get_entitlement ERROR | user=%s err=%s", user_id, e)
        return None


def is_termin_entitled(user_id: str) -> bool:
    """
    Single source of truth for payment gating.
    New model: entitlement valid until first Termin is found.
    Returns True ONLY when:
      - entitlement row exists
      - active = 1  (set by Stripe webhook after real payment)
      - found_termin = 0  (slot not yet found/consumed)
    No time-limit check — entitlement lasts until first termin found.
    """

    def _is_expired(paid_until_str: str, plan: str) -> bool:
        """Parse paid_until and compare timezone-safely. Fail-closed on parse error."""
        try:
            _expires = datetime.fromisoformat(paid_until_str)
        except (ValueError, TypeError):
            logger.warning(
                "TERMIN_ENTITLEMENT_PARSE_ERROR | user=%s plan=%s paid_until=%r — treating as expired",
                user_id, plan, paid_until_str,
            )
            return True  # fail-closed
        if _expires.tzinfo is not None:
            _now = datetime.now(timezone.utc)
        else:
            _now = datetime.utcnow()
        return _now > _expires

    try:
        ent = get_entitlement(str(user_id))
        if not ent:
            return False
        if ent.get("active", 0) != 1:
            return False
        if ent.get("found_termin", 0) != 0:
            return False
        if ent.get("plan") == "7day" and ent.get("paid_until"):
            if _is_expired(ent["paid_until"], "7day"):
                logger.info("TERMIN_ENTITLEMENT_EXPIRED | user=%s plan=7day", user_id)
                return False
        if ent.get("plan") == "single" and ent.get("paid_until"):
            if _is_expired(ent["paid_until"], "single"):
                logger.info("TERMIN_ENTITLEMENT_EXPIRED | user=%s plan=24h", user_id)
                return False
        if ent.get("plan") == "30day" and ent.get("paid_until"):
            if _is_expired(ent["paid_until"], "30day"):
                logger.info("TERMIN_ENTITLEMENT_EXPIRED | user=%s plan=30day", user_id)
                return False
        return True
    except Exception as e:
        logger.error("is_termin_entitled ERROR | user=%s err=%s", user_id, e)
        return False


def is_termin_active(user_id: str, city: str = None, authority: str = None) -> bool:
    """
    DB-backed check: user has an active, non-expired entitlement.

    Restart-safe alternative to checking the in-memory _sessions dict.
    Optionally filters by city/authority if provided.
    Returns True only when entitlement row exists, active=1, not expired, slot not yet found.
    """
    try:
        record = get_entitlement(str(user_id))
        if not record:
            return False
        if record.get("active", 0) != 1:
            return False
        if record.get("found_termin", 0) != 0:
            return False
        if record.get("paid_until"):
            try:
                from datetime import datetime as _dt_check
                expires = _dt_check.fromisoformat(record["paid_until"])
                if _dt_check.utcnow() > expires:
                    return False
            except Exception:
                pass
        return True
    except Exception as e:
        logger.error("is_termin_active ERROR | user=%s err=%s", user_id, e)
        return False


def mark_termin_found(user_id: str) -> bool:
    """
    Close current entitlement after first found slot.
    Also resets has_paid_termin=0 and disables reminders so the UI correctly
    shows the unpaid/pre-payment state until the user pays again.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE termin_entitlements
                   SET active = 0,
                       found_termin = 1
                 WHERE user_id = ?
                   AND id = (SELECT id FROM termin_entitlements
                             WHERE user_id = ?
                             ORDER BY id DESC LIMIT 1)
                """,
                (str(user_id), str(user_id)),
            )
            changed = cursor.rowcount > 0
            # Atomically reset both stale flags in users table so the UI shows the
            # pre-payment screen and startup resume does not re-launch monitoring.
            # Doing this in one statement avoids a half-reset state on crash.
            cursor.execute(
                """
                UPDATE users
                   SET has_paid_termin = 0,
                       reminder_active  = 0
                 WHERE telegram_id = ?
                """,
                (str(user_id),),
            )
            conn.commit()
        logger.info(
            "TERMIN_ENTITLEMENT_CONSUMED | user=%s changed=%s "
            "has_paid_termin=0 reminder_active=0",
            user_id, changed,
        )
        return changed
    except Exception as e:
        logger.error("mark_termin_found ERROR | user=%s err=%s", user_id, e)
        return False


def reset_user_termin_entitlement(telegram_id: str) -> None:
    """
    Debug helper — completely resets Termin entitlement state for one user.
    Used during testing to simulate a fresh unpaid user so Stripe is always shown.

    PROTECTED: only executes when TERMIN_DEBUG_ALLOW_RESET=1 env var is set.
    Safe to leave in production code — never fires without explicit opt-in.
    """
    import os as _os
    if _os.getenv("TERMIN_DEBUG_ALLOW_RESET", "").strip() != "1":
        logger.warning(
            "reset_user_termin_entitlement blocked | user=%s — "
            "set TERMIN_DEBUG_ALLOW_RESET=1 to enable (dev only)",
            telegram_id,
        )
        return
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE termin_entitlements
                   SET active = 0,
                       found_termin = 1
                 WHERE user_id = ?
                """,
                (str(telegram_id),),
            )
            cursor.execute(
                """
                UPDATE users
                   SET has_paid_termin = 0,
                       reminder_active  = 0
                 WHERE telegram_id = ?
                """,
                (str(telegram_id),),
            )
            conn.commit()
        logger.warning(
            "DEBUG_RESET_TERMIN_USER | user=%s — entitlements deactivated, flags cleared",
            telegram_id,
        )
    except Exception as e:
        logger.error("reset_user_termin_entitlement ERROR | user=%s err=%s", telegram_id, e)


def use_slot(user_id: str) -> bool:
    """Increment slots_used by 1 if slots_used < slots_total. Returns True if granted."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE termin_entitlements
                   SET slots_used = slots_used + 1
                 WHERE user_id = ?
                   AND slots_used < slots_total
                   AND id = (SELECT id FROM termin_entitlements
                              WHERE user_id = ? ORDER BY id DESC LIMIT 1)
                """,
                (str(user_id), str(user_id)),
            )
            granted = cursor.rowcount > 0
            conn.commit()
        logger.info("use_slot | user=%s granted=%s", user_id, granted)
        return granted
    except Exception as e:
        logger.error("use_slot ERROR | user=%s err=%s", user_id, e)
        return False


# ── Family V1: Per-user profiles ─────────────────────────────────────────────

def upsert_user_profile(
    user_id: int,
    profile_id: int,
    city_code: str,
    authority_type: str,
    source_doc: str,
) -> None:
    """Insert or update a user profile row (idempotent)."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO termin_user_profiles
                    (user_id, profile_id, city_code, authority_type, source_doc, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, profile_id) DO UPDATE SET
                    city_code = excluded.city_code,
                    authority_type = excluded.authority_type,
                    source_doc = excluded.source_doc,
                    updated_at = excluded.updated_at
                """,
                (user_id, profile_id, city_code, authority_type, source_doc, now, now),
            )
            conn.commit()
        logger.info("upsert_user_profile | user=%s profile=%s city=%s", user_id, profile_id, city_code)
    except Exception as e:
        logger.error("upsert_user_profile ERROR | user=%s profile=%s err=%s", user_id, profile_id, e)


def get_user_profile(user_id: int, profile_id: int) -> dict | None:
    """Return a user profile row or None."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM termin_user_profiles WHERE user_id = ? AND profile_id = ?",
                (user_id, profile_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error("get_user_profile ERROR | user=%s profile=%s err=%s", user_id, profile_id, e)
        return None


def list_user_profiles(user_id: int) -> dict:
    """Return {1: row_dict_or_None, 2: row_dict_or_None}."""
    result = {1: None, 2: None}
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM termin_user_profiles WHERE user_id = ? ORDER BY profile_id",
                (user_id,),
            )
            for row in cursor.fetchall():
                d = dict(row)
                pid = d.get("profile_id")
                if pid in result:
                    result[pid] = d
    except Exception as e:
        logger.error("list_user_profiles ERROR | user=%s err=%s", user_id, e)
    return result


def set_default_profile_if_missing(user_id: int) -> None:
    """Ensure profile 1 row exists for a user (uses user's current city/authority from users table)."""
    try:
        if get_user_profile(user_id, 1) is not None:
            return
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT city, authority FROM users WHERE telegram_id = ?",
                (str(user_id),),
            )
            row = cursor.fetchone()
        city = (dict(row).get("city") or "") if row else ""
        authority = (dict(row).get("authority") or "") if row else ""
        upsert_user_profile(user_id, 1, city, authority, "")
    except Exception as e:
        logger.error("set_default_profile_if_missing ERROR | user=%s err=%s", user_id, e)


def use_family_slot(user_id: int) -> bool:
    """Consume one family slot for profile 2 activation. Idempotent: profile2 row existing means slot already used."""
    try:
        # If profile 2 already exists, slot was already consumed
        if get_user_profile(user_id, 2) is not None:
            logger.info("use_family_slot | user=%s — profile2 already exists, no extra consume", user_id)
            return True
        # Try to consume via entitlement counter
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE termin_entitlements
                   SET slots_used = slots_used + 1
                 WHERE user_id = ?
                   AND slots_used < slots_total
                   AND plan = 'family'
                   AND id = (SELECT id FROM termin_entitlements
                              WHERE user_id = ? AND plan = 'family'
                              ORDER BY id DESC LIMIT 1)
                """,
                (str(user_id), str(user_id)),
            )
            granted = cursor.rowcount > 0
            conn.commit()
        logger.info("use_family_slot | user=%s granted=%s", user_id, granted)
        return granted
    except Exception as e:
        logger.error("use_family_slot ERROR | user=%s err=%s", user_id, e)
        return False


# ── Active profile persistence ────────────────────────────────────────────────

def set_active_profile(user_id: str, profile_id: int) -> None:
    """Persist active profile choice for user (survives bot restart)."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET active_profile_id = ? WHERE telegram_id = ?",
                (profile_id, str(user_id)),
            )
            conn.commit()
        logger.info("set_active_profile | user=%s profile=%s", user_id, profile_id)
    except Exception as e:
        logger.error("set_active_profile ERROR | user=%s err=%s", user_id, e)


def get_active_profile(user_id: str) -> int:
    """Return persisted active profile (1 or 2), default 1."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT active_profile_id FROM users WHERE telegram_id = ?",
                (str(user_id),),
            )
            row = cursor.fetchone()
        return int(dict(row).get("active_profile_id") or 1) if row else 1
    except Exception as e:
        logger.error("get_active_profile ERROR | user=%s err=%s", user_id, e)
        return 1


# ── Restart-safe registry persistence ────────────────────────────────────────

def set_last_slot_found_at(telegram_id: str) -> None:
    """Persist slot-found timestamp so _slot_found_registry survives restart."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_slot_found_at = ? WHERE telegram_id = ?",
                (now, str(telegram_id)),
            )
            conn.commit()
        logger.info("set_last_slot_found_at | user=%s ts=%s", telegram_id, now)
    except Exception as e:
        logger.error("set_last_slot_found_at ERROR | user=%s err=%s", telegram_id, e)


def get_last_slot_found_at(telegram_id: str) -> str:
    """Return ISO timestamp of last slot notification, or '' if never."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_slot_found_at FROM users WHERE telegram_id = ?",
                (str(telegram_id),),
            )
            row = cursor.fetchone()
        return (row["last_slot_found_at"] or "") if row else ""
    except Exception as e:
        logger.error("get_last_slot_found_at ERROR | user=%s err=%s", telegram_id, e)
        return ""


def get_slot_found_entries() -> dict:
    """Return {telegram_id: last_slot_found_at} for all users where slot was found.

    Used on startup to hydrate _slot_found_registry from DB.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT telegram_id, last_slot_found_at FROM users"
                " WHERE last_slot_found_at IS NOT NULL",
            )
            rows = cursor.fetchall()
        return {str(r["telegram_id"]): r["last_slot_found_at"] for r in rows}
    except Exception as e:
        logger.error("get_slot_found_entries ERROR: %s", e)
        return {}


def get_active_monitoring_expiry() -> dict:
    """Return {user_id: paid_until} for all active, non-consumed entitlements.

    Used on startup to hydrate _monitor_expiry_registry from DB.
    Only returns rows where paid_until IS NOT NULL (time-limited plans).
    """
    try:
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, paid_until FROM termin_entitlements"
                " WHERE active = 1 AND found_termin = 0"
                "   AND paid_until IS NOT NULL AND paid_until > ?",
                (now,),
            )
            rows = cursor.fetchall()
        return {str(r["user_id"]): r["paid_until"] for r in rows}
    except Exception as e:
        logger.error("get_active_monitoring_expiry ERROR: %s", e)
        return {}


def save_entitlement_checkout_url(user_id: str, checkout_url: str) -> None:
    """Persist checkout URL on the most recent entitlement row (best-effort).

    Allows _find_reusable_termin_order to reload the URL after restart.
    """
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE termin_entitlements SET checkout_url = ?"
                " WHERE user_id = ? AND active = 1 AND id = ("
                "   SELECT id FROM termin_entitlements"
                "   WHERE user_id = ? AND active = 1 ORDER BY id DESC LIMIT 1"
                ")",
                (checkout_url, str(user_id), str(user_id)),
            )
            _rows = cursor.rowcount
            conn.commit()
        if _rows == 0:
            # Expected for first purchase: entitlement row is created by webhook
            # AFTER payment, so no active row exists yet at checkout creation time.
            # Reuse will fall back to _find_reusable_termin_order (order table TTL).
            logger.info(
                "save_entitlement_checkout_url | user=%s rows=0 "
                "(no active entitlement yet — first purchase, non-fatal)",
                user_id,
            )
        else:
            logger.debug("save_entitlement_checkout_url | user=%s rows=%d", user_id, _rows)
    except Exception as e:
        logger.error("save_entitlement_checkout_url ERROR | user=%s err=%s", user_id, e)


def get_entitlement_checkout_url(user_id: str) -> str:
    """Return the persisted checkout URL for the latest entitlement, or ''."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT checkout_url FROM termin_entitlements"
                " WHERE user_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
                (str(user_id),),
            )
            row = cursor.fetchone()
        return (row["checkout_url"] or "") if row else ""
    except Exception as e:
        logger.error("get_entitlement_checkout_url ERROR | user=%s err=%s", user_id, e)
        return ""
