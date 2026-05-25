# -*- coding: utf-8 -*-
"""
Next steps after document generation — document-specific, fully localized.
Reduces user anxiety by answering "what do I do now?".
Available in multiple languages.
"""

from typing import Dict, Optional

# Official blank form URLs (per doc_type). Replace with your preferred links.
OFFICIAL_BLANK_URLS: Dict[str, str] = {
    "anmeldung": "https://www.service.berlin.de/formularserver/formular.php?402878",
    "abmeldung": "https://www.service.berlin.de/formularserver/formular.php?402880",
    "kindergeld": "https://www.arbeitsagentur.de/familie-und-kinder/kindergeld",
    "wohngeld": "https://www.bundesregierung.de/breg-de/themen/wohngeld",
}

# ============================================================================
# OFFICE ADDRESS BLOCK (CONDITIONAL - show only if document has specific office)
# ============================================================================
# doc_type -> dict with office_name, needs_city (if True, use user's city)
OFFICE_INFO: Dict[str, Dict] = {
    "anmeldung": {
        "office_type": "buergeramt",  # generic type for lookup
        "needs_city": True,  # address depends on user's city
    },
    "abmeldung": {
        "office_type": "buergeramt",
        "needs_city": True,
    },
    "ummeldung": {
        "office_type": "buergeramt",
        "needs_city": True,
    },
    "kindergeld": {
        "office_type": "familienkasse",
        "needs_city": False,  # online or regional, no specific address
    },
    "wohngeld": {
        "office_type": "wohngeldstelle",
        "needs_city": True,
    },
}

# Office name label by language
OFFICE_LABEL_BY_LANG: Dict[str, str] = {
    "uk": "🏢 <b>Установа, яка зазвичай приймає цей документ:</b>",
    "ua": "🏢 <b>Установа, яка зазвичай приймає цей документ:</b>",
    "en": "🏢 <b>Office that typically handles this document:</b>",
    "de": "🏢 <b>Behörde, die dieses Dokument bearbeitet:</b>",
    "pl": "🏢 <b>Urząd, który zazwyczaj przyjmuje ten dokument:</b>",
    "tr": "🏢 <b>Bu belgeyi genelde işleyen kurum:</b>",
    "ar": "🏢 <b>الجهة التي تتعامل مع هذا المستند عادةً:</b>",
}

# Generic office names by type (used when no specific address available)
OFFICE_NAME_BY_TYPE: Dict[str, Dict[str, str]] = {
    "buergeramt": {
        "uk": "Bürgeramt / Einwohnermeldeamt",
        "ua": "Bürgeramt / Einwohnermeldeamt",
        "en": "Bürgeramt / Einwohnermeldeamt",
        "de": "Bürgeramt / Einwohnermeldeamt",
        "pl": "Bürgeramt / Einwohnermeldeamt",
        "tr": "Bürgeramt / Einwohnermeldeamt",
        "ar": "Bürgeramt / Einwohnermeldeamt",
    },
    "familienkasse": {
        "uk": "Familienkasse (Bundesagentur für Arbeit)",
        "ua": "Familienkasse (Bundesagentur für Arbeit)",
        "en": "Familienkasse (Family Benefits Office)",
        "de": "Familienkasse (Bundesagentur für Arbeit)",
        "pl": "Familienkasse (Urząd Rodzinny)",
        "tr": "Familienkasse (Aile Yardımları Ofisi)",
        "ar": "Familienkasse (مكتب إعانات الأسرة)",
    },
    "wohngeldstelle": {
        "uk": "Wohngeldstelle (відділ житлової допомоги)",
        "ua": "Wohngeldstelle (відділ житлової допомоги)",
        "en": "Wohngeldstelle (Housing Benefit Office)",
        "de": "Wohngeldstelle",
        "pl": "Wohngeldstelle (Urząd ds. Dodatków Mieszkaniowych)",
        "tr": "Wohngeldstelle (Konut Yardımı Ofisi)",
        "ar": "Wohngeldstelle (مكتب إعانة السكن)",
    },
}

# ============================================================================
# TERMIN LITE - Honest, neutral UX assistance (NO promises, NO concierge)
# ============================================================================

# Documents that require physical visit (show Termin block)
DOCS_REQUIRING_VISIT = ["anmeldung", "abmeldung", "ummeldung", "wohngeld"]

# Documents that are online-only (NO Termin block)
DOCS_ONLINE_ONLY = ["kindergeld", "elterngeld", "kinderzuschlag"]

# Official appointment booking URLs by city.
# Use www48.muenchen.de for München — stadt.muenchen.de/terminvereinbarung/ returns 404.
OFFICIAL_TERMIN_URLS: Dict[str, str] = {
    "berlin":      "https://service.berlin.de/terminvereinbarung/",
    "munich":      "https://www48.muenchen.de/buergeransicht/",   # fixed: old stadt.muenchen.de returns 404
    "muenchen":    "https://www48.muenchen.de/buergeransicht/",   # alias used by Termin module
    "münchen":     "https://www48.muenchen.de/buergeransicht/",   # alias with umlaut
    "hamburg":     "https://serviceportal.hamburg.de/HamburgGateway/Service/Entry/DigiTermin",
    "frankfurt":   "https://tevis.ekom21.de/fra/",
    "cologne":     "https://tevis.krzn.de/tevisweb190/",
    "koeln":       "https://tevis.krzn.de/tevisweb190/",
    "köln":        "https://tevis.krzn.de/tevisweb190/",
    "dusseldorf":  "https://termine.duesseldorf.de/",
    "duesseldorf": "https://termine.duesseldorf.de/",
    "düsseldorf":  "https://termine.duesseldorf.de/",
    "dortmund":    "https://dortmund.termine-reservieren.de/",
    "stuttgart":   "https://www.stuttgart.de/buergerservice/",
}

# Termin Lite title (neutral, factual)
TERMIN_LITE_TITLE: Dict[str, str] = {
    "uk": "🗓 <b>Запис на прийом (Termin)</b>",
    "ua": "🗓 <b>Запис на прийом (Termin)</b>",
    "en": "🗓 <b>Appointment (Termin)</b>",
    "de": "🗓 <b>Termin</b>",
    "pl": "🗓 <b>Wizyta w urzędzie (Termin)</b>",
    "tr": "🗓 <b>Randevu (Termin)</b>",
    "ar": "🗓 <b>الموعد (Termin)</b>",
}

# Termin Lite intro text (neutral, honest - NO promises)
TERMIN_LITE_TEXT: Dict[str, str] = {
    "uk": "Цей документ зазвичай подається особисто в установу.",
    "ua": "Цей документ зазвичай подається особисто в установу.",
    "en": "This document is usually submitted in person at the authority.",
    "de": "Dieses Dokument wird in der Regel persönlich bei der Behörde eingereicht.",
    "pl": "Ten dokument zazwyczaj składa się osobiście w urzędzie.",
    "tr": "Bu belge genellikle kuruma şahsen teslim edilir.",
    "ar": "عادةً ما يُقدَّم هذا المستند شخصياً لدى الجهة المختصة.",
}

# Official booking link label
TERMIN_LINK_LABEL: Dict[str, str] = {
    "uk": "🔗 <b>Офіційний сайт для запису:</b>",
    "ua": "🔗 <b>Офіційний сайт для запису:</b>",
    "en": "🔗 <b>Official appointment booking website:</b>",
    "de": "🔗 <b>Offizielle Terminbuchung:</b>",
    "pl": "🔗 <b>Oficjalna strona do rezerwacji:</b>",
    "tr": "🔗 <b>Resmi randevu sitesi:</b>",
    "ar": "🔗 <b>الموقع الرسمي لحجز الموعد:</b>",
}

# Termin instruction (short, factual - NO promises)
TERMIN_INSTRUCTION: Dict[str, str] = {
    "uk": "ℹ️ Запишіться на прийом безпосередньо на офіційному сайті установи.",
    "ua": "ℹ️ Запишіться на прийом безпосередньо на офіційному сайті установи.",
    "en": "ℹ️ Please book an appointment directly on the official website of the authority.",
    "de": "ℹ️ Bitte buchen Sie einen Termin direkt auf der offiziellen Website der Behörde.",
    "pl": "ℹ️ Proszę umówić wizytę bezpośrednio na oficjalnej stronie urzędu.",
    "tr": "ℹ️ Lütfen randevunuzu doğrudan kurumun resmi web sitesinden alın.",
    "ar": "ℹ️ يرجى حجز موعد مباشرة على الموقع الرسمي للجهة.",
}

# DEPRECATED: Old CTA texts (kept for backward compatibility, but not used)
TERMIN_CTA_TEXT: Dict[str, str] = TERMIN_LITE_TEXT
TERMIN_CTA_BUTTON: Dict[str, str] = {
    "uk": "🗓 Детальніше про запис",
    "ua": "🗓 Детальніше про запис",
    "en": "🗓 More about appointments",
    "de": "🗓 Mehr zum Termin",
    "pl": "🗓 Więcej o wizytach",
    "tr": "🗓 Randevu hakkında",
    "ar": "🗓 المزيد عن المواعيد",
}

# Link label for delivery message — generic (used for docs OTHER than anmeldung)
OFFICIAL_LINK_LABEL_BY_LANG: Dict[str, str] = {
    "uk": "🔗 <b>Офіційний бланк (порожній):</b>",
    "ua": "🔗 <b>Офіційний бланк (порожній):</b>",
    "en": "🔗 <b>Official blank form:</b>",
    "de": "🔗 <b>Offizielles Blankoformular:</b>",
    "pl": "🔗 <b>Oficjalny pusty formularz:</b>",
    "tr": "🔗 <b>Resmi boş form:</b>",
    "ar": "🔗 <b>النموذج الرسمي الفارغ:</b>",
}

# ============================================================================
# ANMELDUNG-SPECIFIC: Berlin provides an online form, NOT a downloadable blank PDF
# ============================================================================

ANMELDUNG_FILLED_EXAMPLE_LABEL: Dict[str, str] = {
    "uk": "📄 <b>Заповнений приклад (НЕ є офіційним документом)</b>",
    "ua": "📄 <b>Заповнений приклад (НЕ є офіційним документом)</b>",
    "en": "📄 <b>Filled example (NOT an official document)</b>",
    "de": "📄 <b>Ausgefülltes Beispiel (KEIN offizielles Dokument)</b>",
    "pl": "📄 <b>Wypełniony przykład (NIE jest oficjalnym dokumentem)</b>",
    "tr": "📄 <b>Doldurulmuş örnek (resmi belge DEĞİLDİR)</b>",
    "ar": "📄 <b>مثال مملوء (ليس مستندًا رسميًا)</b>",
}

ANMELDUNG_ONLINE_FORM_NOTE: Dict[str, str] = {
    "uk": "ℹ️ Берлін не надає окремий порожній PDF. Офіційний документ створюється лише через онлайн-форму.",
    "ua": "ℹ️ Берлін не надає окремий порожній PDF. Офіційний документ створюється лише через онлайн-форму.",
    "en": "ℹ️ Berlin does not provide a separate empty PDF. The official document is created only via the online form.",
    "de": "ℹ️ Berlin stellt kein separates leeres PDF bereit. Das offizielle Dokument wird nur über das Online-Formular erstellt.",
    "pl": "ℹ️ Berlin nie udostępnia osobnego pustego PDF. Oficjalny dokument tworzy się tylko przez formularz online.",
    "tr": "ℹ️ Berlin ayrı bir boş PDF sağlamaz. Resmi belge yalnızca çevrimiçi form aracılığıyla oluşturulur.",
    "ar": "ℹ️ لا توفر برلين ملف PDF فارغًا منفصلًا. يتم إنشاء المستند الرسمي فقط عبر النموذج الإلكتروني.",
}

ANMELDUNG_HOW_TO_STEPS: Dict[str, str] = {
    "uk": (
        "📝 <b>Як отримати офіційний документ:</b>\n"
        "1. Перегляньте заповнений приклад вище\n"
        "2. Відкрийте офіційну онлайн-форму Берліна\n"
        "3. Перенесіть дані в офіційну форму та збережіть/роздрукуйте"
    ),
    "ua": (
        "📝 <b>Як отримати офіційний документ:</b>\n"
        "1. Перегляньте заповнений приклад вище\n"
        "2. Відкрийте офіційну онлайн-форму Берліна\n"
        "3. Перенесіть дані в офіційну форму та збережіть/роздрукуйте"
    ),
    "en": (
        "📝 <b>How to get your official document:</b>\n"
        "1. Review the filled example above\n"
        "2. Open the official Berlin Anmeldung form\n"
        "3. Copy your data into the official form and save/print it"
    ),
    "de": (
        "📝 <b>So erhalten Sie das offizielle Dokument:</b>\n"
        "1. Prüfen Sie das ausgefüllte Beispiel oben\n"
        "2. Öffnen Sie das offizielle Berliner Anmeldungsformular\n"
        "3. Übertragen Sie die Daten in das offizielle Formular und speichern/drucken Sie es"
    ),
    "pl": (
        "📝 <b>Jak uzyskać oficjalny dokument:</b>\n"
        "1. Przejrzyj wypełniony przykład powyżej\n"
        "2. Otwórz oficjalny formularz Berlin Anmeldung\n"
        "3. Przepisz dane do oficjalnego formularza i zapisz/wydrukuj"
    ),
    "tr": (
        "📝 <b>Resmi belgeyi nasıl alırsınız:</b>\n"
        "1. Yukarıdaki doldurulmuş örneği inceleyin\n"
        "2. Resmi Berlin Anmeldung formunu açın\n"
        "3. Verilerinizi resmi forma kopyalayın ve kaydedin/yazdırın"
    ),
    "ar": (
        "📝 <b>كيف تحصل على المستند الرسمي:</b>\n"
        "1. راجع المثال المملوء أعلاه\n"
        "2. افتح نموذج Anmeldung الرسمي لبرلين\n"
        "3. انسخ بياناتك إلى النموذج الرسمي واحفظه/اطبعه"
    ),
}

ANMELDUNG_OPEN_FORM_BTN: Dict[str, str] = {
    "uk": "📋 Відкрити офіційну форму Berlin Anmeldung",
    "ua": "📋 Відкрити офіційну форму Berlin Anmeldung",
    "en": "📋 Open official Berlin Anmeldung form",
    "de": "📋 Offizielles Berliner Anmeldungsformular öffnen",
    "pl": "📋 Otwórz oficjalny formularz Berlin Anmeldung",
    "tr": "📋 Resmi Berlin Anmeldung formunu aç",
    "ar": "📋 افتح نموذج Anmeldung الرسمي لبرلين",
}

# doc_type -> lang -> HTML text block (where to submit, deadline, what to bring)
NEXT_STEPS: Dict[str, Dict[str, str]] = {
    "anmeldung": {
        "uk": (
            "📌 <b>Що робити далі</b>\n\n"
            "• <b>Куди подавати:</b> Відділ реєстрації (Bürgeramt / Einwohnermeldeamt) за вашою адресою.\n"
            "• <b>Термін:</b> Протягом 14 днів після заселення.\n"
            "• <b>Що взяти з собою:</b> Паспорт або ID, підтвердження від орендодавця (Wohnungsgeberbestätigung), заповнений бланк Anmeldung.\n"
            "• Запис часто можливий онлайн на сайті вашого міста."
        ),
        "en": (
            "📌 <b>What to do next</b>\n\n"
            "• <b>Where to submit:</b> Registration office (Bürgeramt / Einwohnermeldeamt) for your address.\n"
            "• <b>Deadline:</b> Within 14 days of moving in.\n"
            "• <b>What to bring:</b> Passport or ID, landlord confirmation (Wohnungsgeberbestätigung), completed Anmeldung form.\n"
            "• You can often book an appointment online on your city's website."
        ),
        "de": (
            "📌 <b>Was Sie als Nächstes tun</b>\n\n"
            "• <b>Wohin einreichen:</b> Bürgeramt / Einwohnermeldeamt für Ihre Adresse.\n"
            "• <b>Frist:</b> Innerhalb von 14 Tagen nach dem Einzug.\n"
            "• <b>Was mitbringen:</b> Reisepass oder Personalausweis, Bestätigung des Wohnungsgebers (Wohnungsgeberbestätigung), ausgefülltes Anmeldungsformular.\n"
            "• Termin oft online auf der Website Ihrer Stadt buchbar."
        ),
        "pl": (
            "📌 <b>Co dalej</b>\n\n"
            "• <b>Gdzie złożyć:</b> Urząd rejestracji (Bürgeramt / Einwohnermeldeamt) dla Twojego adresu.\n"
            "• <b>Termin:</b> W ciągu 14 dni od zamieszkania.\n"
            "• <b>Co zabrać:</b> Paszport lub dowód, potwierdzenie od wynajmującego (Wohnungsgeberbestätigung), wypełniony formularz Anmeldung.\n"
            "• Rezerwacja często online na stronie Twojego miasta."
        ),
        "tr": (
            "📌 <b>Sırada ne var</b>\n\n"
            "• <b>Nereye teslim:</b> Adresinize göre kayıt bürosu (Bürgeramt / Einwohnermeldeamt).\n"
            "• <b>Son tarih:</b> Taşınmanızdan itibaren 14 gün içinde.\n"
            "• <b>Yanınızda götürün:</b> Pasaport veya kimlik, ev sahibi onayı (Wohnungsgeberbestätigung), doldurulmuş Anmeldung formu.\n"
            "• Randevu genelde şehrinizin web sitesinden online alınabilir."
        ),
        "ar": (
            "📌 <b>ماذا تفعل بعد ذلك</b>\n\n"
            "• <b>أين تقدم:</b> مكتب التسجيل (Bürgeramt / Einwohnermeldeamt) حسب عنوانك.\n"
            "• <b>الموعد النهائي:</b> خلال 14 يوماً من الانتقال.\n"
            "• <b>ماذا تحضر:</b> جواز السفر أو الهوية، تأكيد من المالك (Wohnungsgeberbestätigung)، نموذج Anmeldung مكتمل.\n"
            "• يمكن حجز موعد عبر الإنترنت على موقع مدينتك."
        ),
    },
    "abmeldung": {
        "uk": (
            "📌 <b>Що робити далі</b>\n\n"
            "• <b>Куди подавати:</b> Bürgeramt / Einwohnermeldeamt (за останньою адресою).\n"
            "• <b>Що взяти:</b> Паспорт або ID, заповнений бланк Abmeldung.\n"
            "• Можна часто подати поштою або онлайн — залежить від комуни."
        ),
        "en": (
            "📌 <b>What to do next</b>\n\n"
            "• <b>Where to submit:</b> Bürgeramt / Einwohnermeldeamt (at your last address).\n"
            "• <b>What to bring:</b> Passport or ID, completed Abmeldung form.\n"
            "• Often possible by post or online — depends on your municipality."
        ),
        "de": (
            "📌 <b>Was Sie als Nächstes tun</b>\n\n"
            "• <b>Wohin einreichen:</b> Bürgeramt / Einwohnermeldeamt (Ihre letzte Adresse).\n"
            "• <b>Was mitbringen:</b> Reisepass oder Personalausweis, ausgefülltes Abmeldungsformular.\n"
            "• Oft per Post oder online möglich — je nach Kommune."
        ),
        "pl": (
            "📌 <b>Co dalej</b>\n\n"
            "• <b>Gdzie złożyć:</b> Bürgeramt / Einwohnermeldeamt (Twój ostatni adres).\n"
            "• <b>Co zabrać:</b> Paszport lub dowód, wypełniony formularz Abmeldung.\n"
            "• Często pocztą lub online — zależy od gminy."
        ),
        "tr": (
            "📌 <b>Sırada ne var</b>\n\n"
            "• <b>Nereye teslim:</b> Bürgeramt / Einwohnermeldeamt (son adresiniz).\n"
            "• <b>Yanınızda götürün:</b> Pasaport veya kimlik, doldurulmuş Abmeldung formu.\n"
            "• Sıkça posta veya online — belediyeye göre değişir."
        ),
        "ar": (
            "📌 <b>ماذا تفعل بعد ذلك</b>\n\n"
            "• <b>أين تقدم:</b> Bürgeramt / Einwohnermeldeamt (عنوانك الأخير).\n"
            "• <b>ماذا تحضر:</b> جواز السفر أو الهوية، نموذج Abmeldung مكتمل.\n"
            "• غالباً بالبريد أو عبر الإنترنت — حسب البلدية."
        ),
    },
    "kindergeld": {
        "uk": (
            "📌 <b>Що робити далі</b>\n\n"
            "• <b>Куди подавати:</b> Сімейна каса (Familienkasse) при Bundesagentur für Arbeit або податкове управління (Finanzamt) — залежить від регіону.\n"
            "• <b>Що взяти:</b> Заповнена заява Kindergeld, свідоцтва народження дітей, ID/паспорт, можливо довідка про дохід.\n"
            "• Точну адресу можна знайти на сайті Familienkasse."
        ),
        "en": (
            "📌 <b>What to do next</b>\n\n"
            "• <b>Where to submit:</b> Family fund (Familienkasse) at Bundesagentur für Arbeit or tax office (Finanzamt) — depends on region.\n"
            "• <b>What to bring:</b> Completed Kindergeld form, children's birth certificates, ID/passport, possibly proof of income.\n"
            "• Exact address on Familienkasse website."
        ),
        "de": (
            "📌 <b>Was Sie als Nächstes tun</b>\n\n"
            "• <b>Wohin einreichen:</b> Familienkasse der Bundesagentur für Arbeit oder Finanzamt — je nach Region.\n"
            "• <b>Was mitbringen:</b> Ausgefüllter Kindergeldantrag, Geburtsurkunden der Kinder, Ausweis/Reisepass, ggf. Einkommensnachweis.\n"
            "• Zuständige Stelle auf der Website der Familienkasse finden."
        ),
        "pl": (
            "📌 <b>Co dalej</b>\n\n"
            "• <b>Gdzie złożyć:</b> Familienkasse (Bundesagentur für Arbeit) lub Finanzamt — zależy od regionu.\n"
            "• <b>Co zabrać:</b> Wypełniony wniosek Kindergeld, akty urodzenia dzieci, dowód/paszport, ewentualnie zaświadczenie o dochodach.\n"
            "• Adres na stronie Familienkasse."
        ),
        "tr": (
            "📌 <b>Sırada ne var</b>\n\n"
            "• <b>Nereye teslim:</b> Familienkasse (Bundesagentur für Arbeit) veya Finanzamt — bölgeye göre.\n"
            "• <b>Yanınızda götürün:</b> Doldurulmuş Kindergeld formu, çocukların doğum belgeleri, kimlik/pasaport, gerekirse gelir belgesi.\n"
            "• Doğru adres Familienkasse web sitesinde."
        ),
        "ar": (
            "📌 <b>ماذا تفعل بعد ذلك</b>\n\n"
            "• <b>أين تقدم:</b> Familienkasse أو Finanzamt — حسب المنطقة.\n"
            "• <b>ماذا تحضر:</b> نموذج Kindergeld مكتمل، شهادات ميلاد الأطفال، الهوية/جواز السفر، ربما إثبات الدخل.\n"
            "• العنوان الصحيح على موقع Familienkasse."
        ),
    },
    "wohngeld": {
        "uk": (
            "📌 <b>Що робити далі</b>\n\n"
            "• <b>Куди подавати:</b> Wohngeldstelle (часто при районній адміністрації або житловому відділі).\n"
            "• <b>Що взяти:</b> Заповнена заява, довідка про дохід, договір оренди, документи на всіх мешканців.\n"
            "• Точну адресу дивіться на сайті вашого міста/району."
        ),
        "en": (
            "📌 <b>What to do next</b>\n\n"
            "• <b>Where to submit:</b> Wohngeldstelle (often at district or housing office).\n"
            "• <b>What to bring:</b> Completed application, proof of income, rental contract, documents for all household members.\n"
            "• Check your city/district website for the correct office."
        ),
        "de": (
            "📌 <b>Was Sie als Nächstes tun</b>\n\n"
            "• <b>Wohin einreichen:</b> Wohngeldstelle (oft beim Amt für Wohnungswesen / Kreis).\n"
            "• <b>Was mitbringen:</b> Ausgefüllter Antrag, Einkommensnachweis, Mietvertrag, Unterlagen aller Haushaltsmitglieder.\n"
            "• Zuständige Stelle auf der Website Ihrer Stadt/Kreis."
        ),
        "pl": (
            "📌 <b>Co dalej</b>\n\n"
            "• <b>Gdzie złożyć:</b> Wohngeldstelle (często urząd ds. mieszkalnictwa / powiat).\n"
            "• <b>Co zabrać:</b> Wypełniony wniosek, zaświadczenie o dochodach, umowa najmu, dokumenty wszystkich domowników.\n"
            "• Adres na stronie miasta/powiatu."
        ),
        "tr": (
            "📌 <b>Sırada ne var</b>\n\n"
            "• <b>Nereye teslim:</b> Wohngeldstelle (genelde konut dairesi / ilçe).\n"
            "• <b>Yanınızda götürün:</b> Doldurulmuş başvuru, gelir belgesi, kira sözleşmesi, tüm hane bireylerinin belgeleri.\n"
            "• Doğru ofis şehir/ilçe web sitesinde."
        ),
        "ar": (
            "📌 <b>ماذا تفعل بعد ذلك</b>\n\n"
            "• <b>أين تقدم:</b> Wohngeldstelle (غالباً مكتب السكن / الدائرة).\n"
            "• <b>ماذا تحضر:</b> طلب مكتمل، إثبات الدخل، عقد الإيجار، مستندات جميع أفراد الأسرة.\n"
            "• المكتب الصحيح على موقع مدينتك/دائرتك."
        ),
    },
}


def _norm_lang(lang: Optional[str]) -> str:
    if not lang:
        return "uk"
    lang = (lang or "").strip().lower()
    if lang == "ua":
        lang = "uk"
    if lang in ("uk", "en", "de", "pl", "tr", "ar"):
        return lang
    return "uk"


def get_next_steps(doc_type: str, lang: Optional[str] = None) -> Optional[str]:
    """
    Return localized "what to do next" block for the document type.
    Used after preview and after final PDF delivery.
    """
    doc_type = (doc_type or "").strip().lower()
    lang = _norm_lang(lang)
    by_doc = NEXT_STEPS.get(doc_type)
    if not by_doc:
        return None
    return by_doc.get(lang) or by_doc.get("uk") or by_doc.get("en")


# Anmeldung only: short explanation that some fields are intentionally left blank.
# Sent after the paid PDF and before/with delivery message. Key: anmeldung_unfilled_fields_explanation
ANMELDUNG_UNFILLED_FIELDS_EXPLANATION: Dict[str, str] = {
    "uk": (
        "ℹ️ <b>Деякі поля в зразку порожні — це нормально:</b>\n"
        "• Gemeindekennzahl, номер документа, місце підпису зазвичай заповнюють у владі або від руки.\n"
        "• Наданий PDF — коректний заповнений зразок для орієнтиру."
    ),
    "ua": (
        "ℹ️ <b>Деякі поля в зразку порожні — це нормально:</b>\n"
        "• Gemeindekennzahl, номер документа, місце підпису зазвичай заповнюють у владі або від руки.\n"
        "• Наданий PDF — коректний заповнений зразок для орієнтиру."
    ),
    "en": (
        "ℹ️ <b>Some fields in the example are left blank on purpose:</b>\n"
        "• Gemeindekennzahl, ID document number, and place of signature are usually filled by the authority or by hand.\n"
        "• The PDF you received is a correct filled example for reference."
    ),
    "de": (
        "ℹ️ <b>Einige Felder im Beispiel sind absichtlich leer:</b>\n"
        "• Gemeindekennzahl, Ausweisnummer und Unterschriftsort werden in der Regel von der Behörde oder handschriftlich ausgefüllt.\n"
        "• Das gelieferte PDF ist ein korrektes ausgefülltes Beispiel zur Orientierung."
    ),
    "pl": (
        "ℹ️ <b>Niektóre pola w przykładzie są celowo puste:</b>\n"
        "• Gemeindekennzahl, numer dokumentu i miejsce podpisu zwykle uzupełnia urząd lub odręcznie.\n"
        "• Otrzymany PDF to poprawny wypełniony przykład do orientacji."
    ),
    "tr": (
        "ℹ️ <b>Örnekteki bazı alanlar bilerek boş bırakıldı:</b>\n"
        "• Gemeindekennzahl, kimlik belge numarası ve imza yeri genelde yetkili tarafından veya elle doldurulur.\n"
        "• Aldığınız PDF, referans için doğru doldurulmuş bir örnektir."
    ),
    "ar": (
        "ℹ️ <b>بعض الحقول في النموذج فارغة عن قصد:</b>\n"
        "• Gemeindekennzahl ورقم الهوية ومكان التوقيع تُملأ عادةً من الجهة أو بخط اليد.\n"
        "• ملف PDF الذي تلقيته مثال مملوء صحيح للمرجعية."
    ),
}


def _build_anmeldung_delivery_block(lang: str, url: str) -> str:
    """Build the 3-block Anmeldung-specific delivery message (Berlin online form UX)."""
    parts = []
    # Block 1: Filled example label
    parts.append(ANMELDUNG_FILLED_EXAMPLE_LABEL.get(lang, ANMELDUNG_FILLED_EXAMPLE_LABEL["en"]))
    # Block 2: How to get official document + explanatory note
    how_to = ANMELDUNG_HOW_TO_STEPS.get(lang, ANMELDUNG_HOW_TO_STEPS["en"])
    note = ANMELDUNG_ONLINE_FORM_NOTE.get(lang, ANMELDUNG_ONLINE_FORM_NOTE["en"])
    parts.append(f"{how_to}\n\n{note}")
    # Block 3: Action link
    btn_text = ANMELDUNG_OPEN_FORM_BTN.get(lang, ANMELDUNG_OPEN_FORM_BTN["en"])
    parts.append(f"👉 <a href=\"{url}\">{btn_text}</a>")
    return "\n\n".join(parts)


def get_delivery_message(doc_type: str, lang: Optional[str] = None) -> Optional[str]:
    """
    Return message for paid delivery: official blank link + step-by-step instructions.
    Used by deliver_document after sending the filled PDF.
    """
    doc_type = (doc_type or "").strip().lower()
    lang = _norm_lang(lang)
    steps = get_next_steps(doc_type, lang)
    url = OFFICIAL_BLANK_URLS.get(doc_type)

    # Anmeldung-specific: 3-block UX (Berlin online form, no blank PDF)
    if doc_type == "anmeldung" and url:
        block = _build_anmeldung_delivery_block(lang, url)
        return f"{block}\n\n{steps}" if steps else block

    # Generic: other documents
    label = OFFICIAL_LINK_LABEL_BY_LANG.get(lang, OFFICIAL_LINK_LABEL_BY_LANG.get("en", "🔗 <b>Official blank form:</b>"))
    if url and steps:
        return f"{label}\n<a href=\"{url}\">{url}</a>\n\n{steps}"
    if url:
        return f"{label}\n<a href=\"{url}\">{url}</a>"
    return steps


# Anmeldung only: message when required fields are missing at delivery (do not call create_final_pdf).
ANMELDUNG_REQUIRED_FIELDS_MISSING_BY_LANG: Dict[str, str] = {
    "uk": "⚠️ Не заповнені обов’язкові поля (ім’я, дата народження, адреса). Будь ласка, відкрийте форму ще раз, заповніть усі обов’язкові поля та спробуйте оплатити знову.",
    "ua": "⚠️ Не заповнені обов’язкові поля (ім’я, дата народження, адреса). Будь ласка, відкрийте форму ще раз, заповніть усі обов’язкові поля та спробуйте оплатити знову.",
    "en": "⚠️ Required fields are missing (e.g. name, birth date, address). Please reopen the form, fill in all required fields, and try payment again.",
    "de": "⚠️ Pflichtfelder fehlen (z. B. Name, Geburtsdatum, Adresse). Bitte öffnen Sie das Formular erneut, füllen Sie alle Pflichtfelder aus und versuchen Sie die Zahlung erneut.",
    "pl": "⚠️ Brakuje wymaganych pól (np. imię, data urodzenia, adres). Otwórz formularz ponownie, wypełnij wszystkie wymagane pola i spróbuj zapłacić ponownie.",
    "tr": "⚠️ Zorunlu alanlar eksik (ad, doğum tarihi, adres). Lütfen formu tekrar açın, tüm zorunlu alanları doldurun ve ödemeyi tekrar deneyin.",
    "ar": "⚠️ حقول مطلوبة ناقصة (الاسم، تاريخ الميلاد، العنوان). يرجى إعادة فتح النموذج وتعبئة جميع الحقول المطلوبة والمحاولة مرة أخرى.",
}


def get_anmeldung_required_fields_missing_message(lang: Optional[str] = None) -> str:
    """Return localized message when Anmeldung required fields are missing at delivery. Used only for doc_type=anmeldung."""
    return ANMELDUNG_REQUIRED_FIELDS_MISSING_BY_LANG.get(
        _norm_lang(lang),
        ANMELDUNG_REQUIRED_FIELDS_MISSING_BY_LANG.get("en", "Please reopen the form, fill in all required fields, and try again."),
    )


def get_anmeldung_unfilled_fields_message(lang: Optional[str] = None) -> Optional[str]:
    """
    Return short localized explanation that some Anmeldung fields are intentionally not filled.
    Only for doc_type=anmeldung; used after sending the paid PDF (before or with delivery message).
    """
    return ANMELDUNG_UNFILLED_FIELDS_EXPLANATION.get(
        _norm_lang(lang),
        ANMELDUNG_UNFILLED_FIELDS_EXPLANATION.get("en", ""),
    ) or None


# ============================================================================
# NEW: Office Address and Termin CTA Functions
# ============================================================================

def get_office_block(doc_type: str, lang: Optional[str] = None, city: Optional[str] = None) -> Optional[str]:
    """
    Return localized office address block if document has a specific office.
    Returns None if document is universal/online (no specific office).
    
    Args:
        doc_type: Document type (anmeldung, kindergeld, etc.)
        lang: Language code
        city: User's city (optional, for future city-specific addresses)
    """
    doc_type = (doc_type or "").strip().lower()
    lang = _norm_lang(lang)
    
    office_info = OFFICE_INFO.get(doc_type)
    if not office_info:
        return None  # Document has no specific office
    
    office_type = office_info.get("office_type")
    if not office_type:
        return None
    
    # Get office label
    label = OFFICE_LABEL_BY_LANG.get(lang, OFFICE_LABEL_BY_LANG.get("en", "🏢 <b>Office:</b>"))
    
    # Get office name by type
    office_names = OFFICE_NAME_BY_TYPE.get(office_type, {})
    office_name = office_names.get(lang, office_names.get("en", office_type))
    
    # Build office block
    # For now, just show generic office name (future: add specific address if city known)
    return f"{label}\n{office_name}"


def requires_physical_visit(doc_type: str) -> bool:
    """Check if document requires physical visit to authority."""
    doc_type = (doc_type or "").strip().lower()
    return doc_type in DOCS_REQUIRING_VISIT


def get_termin_url(city: Optional[str] = None) -> Optional[str]:
    """Get official appointment booking URL for city.

    Returns None when no city-specific URL is known so callers can show
    a proper support/fallback message instead of a broken or generic link.
    """
    if city:
        city_key = city.strip().lower()
        url = OFFICIAL_TERMIN_URLS.get(city_key)
        if url:
            return url
    return None


def get_termin_lite_block(doc_type: str, lang: Optional[str] = None, city: Optional[str] = None) -> Optional[str]:
    """
    Build Termin Lite block (honest, neutral UX assistance).
    Returns None if document doesn't require physical visit.
    
    NO promises, NO concierge, NO automation.
    Just: office info + official link + short instruction.
    """
    doc_type = (doc_type or "").strip().lower()
    lang = _norm_lang(lang)
    
    # Only show for documents requiring physical visit
    if not requires_physical_visit(doc_type):
        return None
    
    parts = []
    
    # 1. Title
    title = TERMIN_LITE_TITLE.get(lang, TERMIN_LITE_TITLE.get("en", "🗓 <b>Appointment (Termin)</b>"))
    parts.append(title)
    
    # 2. Intro text (neutral, factual)
    intro = TERMIN_LITE_TEXT.get(lang, TERMIN_LITE_TEXT.get("en", ""))
    if intro:
        parts.append(intro)
    
    # 3. Office info
    office_block = get_office_block(doc_type, lang, city)
    if office_block:
        parts.append(office_block)
    
    # 4. Official booking link — only shown when a verified city-specific URL is known.
    # If missing, show a neutral fallback so users still know how to proceed.
    _TERMIN_URL_FALLBACK: Dict[str, str] = {
        "uk": "ℹ️ Посилання для запису доступне на офіційному сайті вашого міста. Введіть у пошуку: «Bürgeramt Termin» + назва міста.",
        "ua": "ℹ️ Посилання для запису доступне на офіційному сайті вашого міста. Введіть у пошуку: «Bürgeramt Termin» + назва міста.",
        "en": "ℹ️ The booking link is available on your city's official website. Search for: «Bürgeramt Termin» + city name.",
        "de": "ℹ️ Den Buchungslink finden Sie auf der offiziellen Website Ihrer Stadt. Suchen Sie nach: «Bürgeramt Termin» + Stadtname.",
        "pl": "ℹ️ Link do rezerwacji znajdziesz na oficjalnej stronie swojego miasta. Wyszukaj: «Bürgeramt Termin» + nazwa miasta.",
        "tr": "ℹ️ Randevu bağlantısı şehrinizin resmi web sitesinde bulunabilir. Aratın: «Bürgeramt Termin» + şehir adı.",
        "ar": "ℹ️ رابط الحجز متاح على الموقع الرسمي لمدينتك. ابحث عن: «Bürgeramt Termin» + اسم المدينة.",
    }
    termin_url = get_termin_url(city)
    if termin_url:
        link_label = TERMIN_LINK_LABEL.get(lang, TERMIN_LINK_LABEL.get("en", "🔗 <b>Official appointment booking:</b>"))
        parts.append(f"{link_label}\n<a href=\"{termin_url}\">{termin_url}</a>")
    else:
        parts.append(_TERMIN_URL_FALLBACK.get(lang, _TERMIN_URL_FALLBACK["en"]))
    
    # 5. Instruction (short, factual)
    instruction = TERMIN_INSTRUCTION.get(lang, TERMIN_INSTRUCTION.get("en", ""))
    if instruction:
        parts.append(instruction)
    
    return "\n\n".join(parts) if len(parts) > 1 else None


def get_termin_cta_text(lang: Optional[str] = None) -> str:
    """Return localized Termin Lite intro text (neutral, no promises)."""
    lang = _norm_lang(lang)
    return TERMIN_LITE_TEXT.get(lang, TERMIN_LITE_TEXT.get("en", TERMIN_LITE_TEXT["uk"]))


def get_termin_cta_button(lang: Optional[str] = None) -> str:
    """Return localized Termin button text (neutral)."""
    lang = _norm_lang(lang)
    return TERMIN_CTA_BUTTON.get(lang, TERMIN_CTA_BUTTON.get("en", TERMIN_CTA_BUTTON["uk"]))


def get_full_post_pdf_message(
    doc_type: str, 
    lang: Optional[str] = None,
    city: Optional[str] = None,
    include_termin_cta: bool = True
) -> str:
    """
    Build complete post-PDF message in correct order:
    1. Official blank link (if available)
    2. Next steps (what to do)
    3. Termin Lite block (if document requires physical visit)
    
    Args:
        doc_type: Document type
        lang: Language code
        city: User's city (optional, for city-specific termin links)
        include_termin_cta: Whether to include Termin Lite block
    """
    parts = []
    lang_norm = _norm_lang(lang)
    url = OFFICIAL_BLANK_URLS.get(doc_type)

    # 1. Official form link — Anmeldung-specific 3-block UX or generic
    if doc_type == "anmeldung" and url:
        parts.append(_build_anmeldung_delivery_block(lang_norm, url))
    elif url:
        label = OFFICIAL_LINK_LABEL_BY_LANG.get(lang_norm, OFFICIAL_LINK_LABEL_BY_LANG.get("en", "🔗 <b>Official blank form:</b>"))
        parts.append(f"{label}\n<a href=\"{url}\">{url}</a>")

    # 2. Next steps
    steps = get_next_steps(doc_type, lang)
    if steps:
        parts.append(steps)

    # 3. Termin Lite block (conditional - only for physical visit documents)
    if include_termin_cta:
        termin_block = get_termin_lite_block(doc_type, lang, city)
        if termin_block:
            parts.append(termin_block)

    return "\n\n".join(parts) if parts else ""
