# -*- coding: utf-8 -*-
"""
Centralized preview texts for PDF generation.
All preview texts are stored here per document type and language.
Language codes: ua (uk→ua), en, de, pl, tr, ar.
Rule: NO fallback to default language — use user's chosen language or raise.
"""

# Мови, які підтримуються для превʼю. Без fallback — якщо мова не тут, явна помилка.
SUPPORTED_PREVIEW_LANGS = ("ua", "uk", "en", "de", "pl", "tr", "ar")


def _normalize_preview_lang(lang: str) -> str:
    """Нормалізує код мови (uk→ua). Якщо мова не підтримується — ValueError."""
    if not lang:
        raise ValueError("Preview language is required (no fallback)")
    lang = (lang or "").strip().lower()
    if lang == "uk":
        lang = "ua"
    if lang not in ("ua", "en", "de", "pl", "tr", "ar"):
        raise ValueError("Preview language not supported: {!r}. Use one of: ua, en, de, pl, tr, ar.".format(lang))
    return lang


# Ключовий блок полів для превʼю (одна секція з реальними даними) — по одному на тип документа.
PREVIEW_KEY_BLOCK = {
    "anmeldung": ["last_name", "first_name", "birth_date", "birth_place", "street", "house_number", "postal_code", "city", "move_in_date"],
    "abmeldung": ["last_name", "first_name", "street", "house_number", "postal_code", "city", "move_out_date"],
    "ummeldung": ["last_name", "first_name", "street", "house_number", "postal_code", "city", "move_in_date"],
    "wohnungsgeberbestaetigung": ["last_name", "first_name", "street", "postal_code", "city", "landlord_name"],
    "meldebescheinigung": ["last_name", "first_name", "street", "postal_code", "city"],
    "anmeldung_familie": ["last_name", "first_name", "street", "postal_code", "city", "move_in_date"],
    "kindergeld": ["last_name", "first_name", "street", "postal_code", "city"],
    "elterngeld": ["last_name", "first_name", "birth_date", "street", "postal_code", "city"],
    "kinderzuschlag": [
        "last_name",
        "first_name",
        "street",
        "postal_code",
        "city",
        "child1_first_name",
        "child1_last_name",
    ],
    "unterhaltsvorschuss": ["last_name", "first_name", "street", "postal_code", "city"],
    "anlage_kind": ["last_name", "first_name", "street", "postal_code", "city"],
    "steuer_id_kind": ["last_name", "first_name", "birth_date", "birth_place", "street", "city"],
    "buergergeld": ["last_name", "first_name", "street", "postal_code", "city"],
    "wohngeld": ["last_name", "first_name", "street", "postal_code", "city"],
    "arbeitslosengeld_1": ["last_name", "first_name", "street", "postal_code", "city"],
    "arbeitslosengeld_2": ["last_name", "first_name", "street", "postal_code", "city"],
    "krankenversicherung_anmeldung": ["last_name", "first_name", "street", "postal_code", "city"],
    "sozialversicherungsnummer": ["last_name", "first_name", "birth_date", "street", "postal_code", "city"],
    "arbeitserlaubnis": ["last_name", "first_name", "birth_date", "street", "postal_code", "city"],
    "steuererklaerung": ["last_name", "first_name", "street", "postal_code", "city"],
    "gewerbeanmeldung": ["last_name", "first_name", "street", "postal_code", "city"],
    "kuendigung": ["last_name", "first_name", "street", "postal_code", "city"],
    "arbeitslosmeldung": ["last_name", "first_name", "street", "postal_code", "city"],
}


def get_preview_key_block_fields(doc_type: str) -> list:
    """Повертає список ключів полів для ключового блоку превʼю (одна секція з даними)."""
    return list(PREVIEW_KEY_BLOCK.get(doc_type, ["last_name", "first_name", "street", "postal_code", "city"]))


# Текст «що в повному PDF» (розділи/сторінки) — мовою користувача.
PREVIEW_FULL_STRUCTURE = {
    "ua": "Сторінки 2–8 повного PDF: додаткові розділи (будуть заповнені після оплати).",
    "en": "Pages 2–8 of full PDF: additional sections (filled after payment).",
    "de": "Seiten 2–8 des vollständigen PDFs: weitere Abschnitte (nach Zahlung ausgefüllt).",
    "pl": "Strony 2–8 pełnego PDF: dodatkowe sekcje (wypełnione po płatności).",
    "tr": "Tam PDF'in sayfa 2–8: ek bölümler (ödeme sonrası doldurulur).",
    "ar": "الصفحات 2–8 من PDF الكامل: أقسام إضافية (تُملأ بعد الدفع).",
}


def get_preview_full_structure_text(lang: str) -> str:
    """Текст про структуру повного документа (що буде після оплати). Без fallback."""
    lang = _normalize_preview_lang(lang)
    return PREVIEW_FULL_STRUCTURE.get(lang, PREVIEW_FULL_STRUCTURE["en"])


# Текст «повний документ після оплати»
PREVIEW_AFTER_PAYMENT = {
    "ua": "Повний документ (6–8 сторінок) буде доступний після оплати.",
    "en": "Full document (6–8 pages) available after payment.",
    "de": "Vollständiges Dokument (6–8 Seiten) nach Zahlung verfügbar.",
    "pl": "Pełny dokument (6–8 stron) dostępny po płatności.",
    "tr": "Tam belge (6–8 sayfa) ödeme sonrası kullanılabilir.",
    "ar": "المستند الكامل (6–8 صفحات) متاح بعد الدفع.",
}


def get_preview_after_payment_text(lang: str) -> str:
    """Текст «повний документ після оплати». Без fallback."""
    lang = _normalize_preview_lang(lang)
    return PREVIEW_AFTER_PAYMENT.get(lang, PREVIEW_AFTER_PAYMENT["en"])


PREVIEW_TEXTS = {
    "anmeldung": {
        "ua": {
            "title": "Anmeldung (реєстрація місця проживання)",
            "description": "Цей документ потрібен, щоб офіційно зареєструвати ваше місце проживання в Німеччині. Після заповнення його зазвичай подають до місцевого органу (Bürgeramt).",
            "structure": "Форма зазвичай має кілька сторінок (близько 9), і в ній легко припуститися помилки. Вона містить особисті дані, адресу проживання, дату переїзду та дані орендодавця.",
            "preview_note": "Це приклад заповненого документа на основі ваших відповідей.\n⚠️ Це не офіційний документ — це допомога, щоб ви побачили, як має виглядати форма.",
            "what_next": "Превʼю допоможе вам правильно заповнити офіційну форму і уникнути помилок, через які документ можуть повернути.\n\nПісля оплати ви отримаєте готовий приклад усіх сторінок та посилання на офіційну онлайн-форму.",
        },
        "pl": {
            "title": "Anmeldung (rejestracja miejsca zamieszkania)",
            "description": "Ten dokument jest potrzebny, aby oficjalnie zarejestrować Twoje miejsce zamieszkania w Niemczech. Po wypełnieniu zwykle składa się go w lokalnym urzędzie (Bürgeramt).",
            "structure": "Formularz zwykle ma kilka stron (około 9) i łatwo w nim o pomyłkę. Zawiera dane osobowe, adres zamieszkania, datę przeprowadzki oraz dane wynajmującego.",
            "preview_note": "To przykład wypełnionego dokumentu na podstawie Twoich odpowiedzi.\n⚠️ To nie jest oficjalny dokument — to pomoc, żebyś zobaczył, jak powinien wyglądać formularz.",
            "what_next": "Podgląd pomoże Ci prawidłowo wypełnić oficjalny formularz i uniknąć błędów, przez które dokument może zostać zwrócony.\nPo opłaceniu otrzymasz gotowy przykład wszystkich stron oraz link do oficjalnego formularza online.",
        },
        "en": {
            "title": "Anmeldung (residence registration)",
            "description": "This document is needed to officially register your residence in Germany. After filling it out, it's usually submitted to the local authority (Bürgeramt).",
            "structure": "The form usually has several pages (around 9), and it's easy to make mistakes. It contains personal data, residence address, move-in date, and landlord information.",
            "preview_note": "This is an example of a completed document based on your answers.\n⚠️ This is not an official document — it's help so you can see how the form should look.",
            "what_next": "The preview will help you correctly fill out the official form and avoid mistakes that could cause the document to be returned.\nAfter payment, you'll receive a ready example of all pages and a link to the official online form.",
        },
        "de": {
            "title": "Anmeldung (Wohnsitzanmeldung)",
            "description": "Dieses Dokument wird benötigt, um Ihren Wohnsitz in Deutschland offiziell anzumelden. Nach dem Ausfüllen wird es normalerweise beim örtlichen Bürgeramt eingereicht.",
            "structure": "Das Formular hat normalerweise mehrere Seiten (etwa 9), und es ist leicht, Fehler zu machen. Es enthält persönliche Daten, Wohnadresse, Einzugsdatum und Vermieterdaten.",
            "preview_note": "Dies ist ein Beispiel für ein ausgefülltes Dokument basierend auf Ihren Antworten.\n⚠️ Dies ist kein offizielles Dokument — es ist eine Hilfe, damit Sie sehen können, wie das Formular aussehen soll.",
            "what_next": "Die Vorschau hilft Ihnen, das offizielle Formular korrekt auszufüllen und Fehler zu vermeiden, die dazu führen könnten, dass das Dokument zurückgegeben wird.\nNach der Zahlung erhalten Sie ein fertiges Beispiel aller Seiten und einen Link zum offiziellen Online-Formular.",
        },
        "tr": {
            "title": "Anmeldung (ikamet kaydı)",
            "description": "Bu belge, Almanya'da ikamet yerinizi resmi olarak kaydetmek için gereklidir. Doldurduktan sonra genellikle yerel makama (Bürgeramt) sunulur.",
            "structure": "Form genellikle birkaç sayfadan oluşur (yaklaşık 9) ve hata yapmak kolaydır. Kişisel veriler, ikamet adresi, taşınma tarihi ve ev sahibi bilgilerini içerir.",
            "preview_note": "Bu, yanıtlarınıza dayalı doldurulmuş bir belgenin örneğidir.\n⚠️ Bu resmi bir belge değildir — formun nasıl görünmesi gerektiğini görmeniz için bir yardımdır.",
            "what_next": "Önizleme, resmi formu doğru şekilde doldurmanıza ve belgenin geri gönderilmesine neden olabilecek hatalardan kaçınmanıza yardımcı olacaktır.\nÖdeme sonrasında, tüm sayfaların hazır bir örneğini ve resmi çevrimiçi formun bağlantısını alacaksınız.",
        },
        "ar": {
            "title": "Anmeldung (تسجيل الإقامة)",
            "description": "هذا المستند مطلوب لتسجيل إقامتك رسمياً في ألمانيا. بعد ملئه، يُقدم عادةً إلى السلطة المحلية (Bürgeramt).",
            "structure": "يتكون النموذج عادةً من عدة صفحات (حوالي 9)، ومن السهل ارتكاب الأخطاء. يحتوي على البيانات الشخصية وعنوان الإقامة وتاريخ الانتقال ومعلومات المالك.",
            "preview_note": "هذا مثال على مستند مكتمل بناءً على إجاباتك.\n⚠️ هذا ليس مستنداً رسمياً — إنه مساعدة لترى كيف يجب أن يبدو النموذج.",
            "what_next": "ستساعدك المعاينة على ملء النموذج الرسمي بشكل صحيح وتجنب الأخطاء التي قد تؤدي إلى إرجاع المستند.\nبعد الدفع، ستحصل على مثال جاهز لجميع الصفحات ورابط إلى النموذج الرسمي عبر الإنترنت.",
        },
    },
    # TODO: Add other document types (abmeldung, kindergeld, etc.) as needed
}


def _generic_preview_blocks(doc_type: str, lang: str) -> dict:
    """Генерує мінімальні блоки превʼю для типу документа без повного PREVIEW_TEXTS."""
    title_by_lang = {
        "ua": {"anmeldung": "Anmeldung (реєстрація)", "abmeldung": "Abmeldung", "ummeldung": "Ummeldung", "kindergeld": "Kindergeld"},
        "en": {"anmeldung": "Anmeldung (registration)", "abmeldung": "Abmeldung", "ummeldung": "Ummeldung", "kindergeld": "Kindergeld"},
        "de": {"anmeldung": "Anmeldung", "abmeldung": "Abmeldung", "ummeldung": "Ummeldung", "kindergeld": "Kindergeld"},
    }
    titles = title_by_lang.get(lang, title_by_lang["en"])
    title = titles.get(doc_type, doc_type.replace("_", " ").title())
    desc = {
        "ua": "Цей документ потрібен для офіційних цілей у Німеччині. Превʼю показує приклад заповнення на основі ваших відповідей.",
        "en": "This document is required for official purposes in Germany. The preview shows an example filled from your answers.",
        "de": "Dieses Dokument wird für behördliche Zwecke in Deutschland benötigt. Die Vorschau zeigt ein Beispiel basierend auf Ihren Angaben.",
        "pl": "Ten dokument jest wymagany do celów urzędowych w Niemczech. Podgląd pokazuje przykład wypełnienia na podstawie Twoich odpowiedzi.",
        "tr": "Bu belge Almanya'da resmi amaçlar için gereklidir. Önizleme, yanıtlarınıza dayalı bir örnek gösterir.",
        "ar": "هذا المستند مطلوب للأغراض الرسمية في ألمانيا. تعرض المعاينة مثالاً مملوءاً بناءً على إجاباتك.",
    }.get(lang, "")
    structure = get_preview_full_structure_text(lang)
    preview_note = {
        "ua": "Це приклад заповнення на основі ваших відповідей.\n⚠️ Це не офіційний документ.",
        "en": "This is an example based on your answers.\n⚠️ This is not an official document.",
        "de": "Dies ist ein Beispiel basierend auf Ihren Angaben.\n⚠️ Dies ist kein offizielles Dokument.",
    }.get(lang, "")
    what_next = get_preview_after_payment_text(lang)
    return {"title": title, "description": desc, "structure": structure, "preview_note": preview_note, "what_next": what_next}


def get_preview_blocks(doc_type: str, lang: str) -> dict:
    """
    Повертає локалізовані блоки превʼю для типу документа.
    Мова = обрана користувачем. Без fallback — якщо мова не підтримується, ValueError.
    """
    lang = _normalize_preview_lang(lang)
    doc_texts = PREVIEW_TEXTS.get(doc_type, {})
    blocks = doc_texts.get(lang)
    if blocks:
        return blocks
    return _generic_preview_blocks(doc_type, lang)


# Інформаційний блок превʼю (сіра рамка внизу): превʼю, не офіційний документ, що отримає після оплати, мета сервісу.
# Джерело тексту — user_lang / order["lang"]. Fallback на en, якщо перекладу немає.
PREVIEW_DISCLAIMER_TEXTS = {
    "ua": [
        "Це превʼю — приклад заповнення. Документ не є офіційним.",
        "Після оплати ви отримаєте: повний приклад (усі сторінки) та посилання на офіційний бланк.",
        "Мета сервісу — допомогти заповнити документ правильно з першого разу."
    ],
    "uk": [
        "Це превʼю — приклад заповнення. Документ не є офіційним.",
        "Після оплати ви отримаєте: повний приклад (усі сторінки) та посилання на офіційний бланк.",
        "Мета сервісу — допомогти заповнити документ правильно з першого разу."
    ],
    "en": [
        "This is a preview — an example of completion. This document is not official.",
        "After payment you receive: full example (all pages) and link to the official form.",
        "Our goal is to help you fill in the document correctly the first time."
    ],
    "de": [
        "Dies ist eine Vorschau — ein Ausfüllbeispiel. Dieses Dokument ist nicht offiziell.",
        "Nach der Zahlung erhalten Sie: vollständiges Beispiel (alle Seiten) und Link zum offiziellen Formular.",
        "Unser Ziel: Ihnen helfen, das Dokument beim ersten Mal richtig auszufüllen."
    ],
    "pl": [
        "To jest podgląd — przykład wypełnienia. Dokument nie jest oficjalny.",
        "Po opłaceniu otrzymasz: pełny przykład (wszystkie strony) i link do oficjalnego formularza.",
        "Celem serwisu jest pomoc w prawidłowym wypełnieniu dokumentu za pierwszym razem."
    ],
    "tr": [
        "Bu bir önizlemedir — doldurma örneği. Belge resmi değildir.",
        "Ödeme sonrası alacaksınız: tam örnek (tüm sayfalar) ve resmi formun linki.",
        "Hizmetimizin amacı, belgeyi ilk seferde doğru doldurmanıza yardımcı olmaktır."
    ],
    "ar": [
        "هذه معاينة — مثال على الملء. المستند غير رسمي.",
        "بعد الدفع تحصل على: مثال كامل (جميع الصفحات) ورابط النموذج الرسمي.",
        "هدف الخدمة هو مساعدتك في ملء المستند بشكل صحيح من المرة الأولى."
    ]
}


def get_preview_disclaimer(lang: str) -> list:
    """
    Повертає локалізований текст інформаційного блоку превʼю (user_lang).
    Fallback на English, якщо мови немає в словнику.
    """
    try:
        lang = _normalize_preview_lang(lang or "")
    except (ValueError, TypeError):
        lang = "en"
    return PREVIEW_DISCLAIMER_TEXTS.get(lang, PREVIEW_DISCLAIMER_TEXTS["en"])


# Authority block texts (localized)
AUTHORITY_BLOCK_TEXTS = {
    "ua": {
        "title": "Куди подають цей документ",
        "content": "За вашим поштовим індексом ваше місце проживання знаходиться в федеральній землі {bundesland}.\nПісля заповнення документ зазвичай подають до місцевого {authority_type}.\n\nЦя інформація допоможе вам орієнтуватися.\nЗавжди перевіряйте актуальні деталі на офіційному сайті міста.",
        "address_title": "Адреса установи:",
        "search_link": "Знайти найближчий орган",
    },
    "pl": {
        "title": "Gdzie składa się ten dokument",
        "content": "Zgodnie z Twoim kodem pocztowym Twoje miejsce zamieszkania znajduje się w kraju związkowym {bundesland}.\nPo wypełnieniu dokument zwykle składa się w lokalnym {authority_type}.\n\nTa informacja pomoże Ci się zorientować.\nZawsze sprawdzaj aktualne szczegóły na oficjalnej stronie miasta.",
        "address_title": "Adres urzędu:",
        "search_link": "Znajdź najbliższy urząd",
    },
    "en": {
        "title": "Where this document is submitted",
        "content": "Based on your postal code, your residence is in the federal state {bundesland}.\nAfter filling it out, the document is usually submitted to the local {authority_type}.\n\nThis information will help you get oriented.\nAlways check current details on the official city website.",
        "address_title": "Authority address:",
        "search_link": "Find nearest authority",
    },
    "de": {
        "title": "Wo dieses Dokument eingereicht wird",
        "content": "Basierend auf Ihrer Postleitzahl befindet sich Ihr Wohnsitz im Bundesland {bundesland}.\nNach dem Ausfüllen wird das Dokument normalerweise beim örtlichen {authority_type} eingereicht.\n\nDiese Informationen helfen Ihnen bei der Orientierung.\nBitte überprüfen Sie immer aktuelle Details auf der offiziellen Stadtwebsite.",
        "address_title": "Behördenadresse:",
        "search_link": "Nächste Behörde finden",
    },
    "tr": {
        "title": "Bu belge nereye sunulur",
        "content": "Posta kodunuza göre, ikamet yeriniz {bundesland} federal eyaletindedir.\nDoldurduktan sonra belge genellikle yerel {authority_type}'a sunulur.\n\nBu bilgiler size yön vermenize yardımcı olacaktır.\nDetayları her zaman resmi şehir web sitesinde doğrulayın.",
        "address_title": "Makam adresi:",
        "search_link": "En yakın makamı bul",
    },
    "ar": {
        "title": "أين يتم تقديم هذا المستند",
        "content": "بناءً على الرمز البريدي الخاص بك، تقع إقامتك في الولاية الاتحادية {bundesland}.\nبعد ملئه، يُقدم المستند عادةً إلى {authority_type} المحلي.\n\nهذه المعلومات ستساعدك على التوجه.\nتحقق دائماً من التفاصيل الحالية على الموقع الرسمي للمدينة.",
        "address_title": "عنوان الجهة:",
        "search_link": "العثور على أقرب جهة",
    },
}


def get_authority_block_text(lang: str) -> dict:
    """
    Get localized authority block text.
    
    Args:
        lang: Language code (ua, en, de, pl, tr, ar)
    
    Returns:
        Dictionary with authority block texts. No fallback — raises if language not supported.
    """
    lang = _normalize_preview_lang(lang)
    if lang not in AUTHORITY_BLOCK_TEXTS:
        raise ValueError("Authority block not available for language: {!r}".format(lang))
    return AUTHORITY_BLOCK_TEXTS[lang]


# Universal explanatory block (applies to ALL documents)
# This block clearly communicates the value of the project
UNIVERSAL_EXPLANATORY_BLOCK = {
    "ua": {
        "title": "Що ви отримаєте",
        "paragraph1": "⚠️ Це не офіційний документ.",
        "paragraph2": "Цей приклад показує, як правильно заповнити форму на основі ваших відповідей. Ми допомагаємо вам уникнути помилок і запобігти поверненню заяви.",
        "paragraph3": "Після оплати ви отримаєте повний приклад усіх сторінок (зазвичай близько 9), правильно заповнених на основі ваших відповідей — як зразок.",
        "paragraph4": "Також після оплати ви отримаєте посилання, де можна завантажити офіційний чистий бланк з державного сайту.",
    },
    "en": {
        "title": "What you'll get",
        "paragraph1": "⚠️ This is not an official document.",
        "paragraph2": "This preview shows an example of how to correctly fill in the form based on your answers. We help you avoid mistakes and prevent application returns.",
        "paragraph3": "After proceeding and paying, you'll receive a full example of the document — all pages (usually around 9), correctly filled based on your answers. This example serves as a reference to transfer data into the official form without errors or rejections.",
        "paragraph4": "You will also receive a link to download the official blank form from the official government website.",
    },
    "de": {
        "title": "Was Sie erhalten",
        "paragraph1": "⚠️ Dies ist kein offizielles Dokument.",
        "paragraph2": "Diese Vorschau zeigt ein Beispiel, wie das Formular korrekt ausgefüllt wird, basierend auf Ihren Antworten. Wir helfen Ihnen, Fehler zu vermeiden und Antragsrückgaben zu verhindern.",
        "paragraph3": "Nach dem Fortfahren und der Zahlung erhalten Sie ein vollständiges Beispiel des Dokuments — alle Seiten (normalerweise etwa 9), korrekt ausgefüllt basierend auf Ihren Antworten. Dieses Beispiel dient als Referenz, um Daten fehlerfrei und ohne Ablehnungen in das offizielle Formular zu übertragen.",
        "paragraph4": "Sie erhalten auch einen Link zum Herunterladen des offiziellen Blankoformulars von der offiziellen Regierungswebsite.",
    },
    "pl": {
        "title": "Co otrzymasz",
        "paragraph1": "⚠️ To nie jest oficjalny dokument.",
        "paragraph2": "Ten podgląd pokazuje przykład, jak poprawnie wypełnić formularz na podstawie Twoich odpowiedzi. Pomagamy Ci uniknąć błędów i zapobiec zwrotowi wniosku.",
        "paragraph3": "Po przejściu dalej i opłaceniu otrzymasz pełny przykład dokumentu — wszystkie strony (zwykle około 9), poprawnie wypełnione na podstawie Twoich odpowiedzi. Ten przykład służy jako odniesienie do przeniesienia danych do oficjalnego formularza bez błędów i odrzuceń.",
        "paragraph4": "Otrzymasz także link do pobrania oficjalnego czystego formularza ze strony rządowej.",
    },
    "tr": {
        "title": "Ne alacaksınız",
        "paragraph1": "⚠️ Bu resmi bir belge değildir.",
        "paragraph2": "Bu önizleme, yanıtlarınıza dayalı olarak formun nasıl doğru doldurulacağının bir örneğini gösterir. Hatalardan kaçınmanıza ve başvuru iadelerini önlemenize yardımcı oluyoruz.",
        "paragraph3": "Devam edip ödeme yaptıktan sonra, belgenin tam bir örneğini alacaksınız — tüm sayfalar (genellikle yaklaşık 9), yanıtlarınıza dayalı olarak doğru şekilde doldurulmuş. Bu örnek, verileri hatasız ve reddedilmeden resmi forma aktarmak için bir referans olarak hizmet eder.",
        "paragraph4": "Ayrıca resmi boş formu resmi devlet web sitesinden indirmek için bir bağlantı alacaksınız.",
    },
    "ar": {
        "title": "ما ستحصل عليه",
        "paragraph1": "⚠️ هذا ليس مستنداً رسمياً.",
        "paragraph2": "تُظهر هذه المعاينة مثالاً على كيفية ملء النموذج بشكل صحيح بناءً على إجاباتك. نساعدك على تجنب الأخطاء ومنع إرجاع الطلب.",
        "paragraph3": "بعد المتابعة والدفع، ستحصل على مثال كامل للمستند — جميع الصفحات (عادةً حوالي 9)، مملوءة بشكل صحيح بناءً على إجاباتك. يخدم هذا المثال كمرجع لنقل البيانات إلى النموذج الرسمي دون أخطاء أو رفض.",
        "paragraph4": "ستحصل أيضاً على رابط لتنزيل النموذج الرسمي الفارغ من موقع الحكومة الرسمي.",
    },
}


def get_universal_explanatory_block(lang: str) -> dict:
    """
    Get localized universal explanatory block text.
    This block applies to ALL documents and clearly communicates the value of the project.
    
    Args:
        lang: Language code (ua, en, de, pl, tr, ar)
    
    Returns:
        Dictionary with universal explanatory block texts. No fallback — raises if language not supported.
    """
    lang = _normalize_preview_lang(lang)
    if lang not in UNIVERSAL_EXPLANATORY_BLOCK:
        raise ValueError("Universal explanatory block not available for language: {!r}".format(lang))
    return UNIVERSAL_EXPLANATORY_BLOCK[lang]
