# -*- coding: utf-8 -*-
"""Турецька мова - backend/texts/tr.py"""

# ============================================================================
# PROJE GİRİŞ METNİ
# ============================================================================

INTRO_TEXT = """Merhaba! 👋

Alman belgelerini ilk seferde kabul edilecek şekilde doldurmanıza
yardımcı oluyoruz — geri gönderilme veya ek ofis ziyaretleri olmadan.

Nasıl çalışır:
Bir formdaki soruları yanıtlarsınız ve size doldurulmuş bir belgenin
hazır örneğini gösteririz. Böylece formun tam olarak nasıl görünmesi gerektiğini görürsünüz
ve verileri hatasız olarak resmi forma aktarabilirsiniz.

Şu tür belgelerle çalışıyoruz:
– ikamet kaydı (Anmeldung)
– sosyal ve aile başvuruları
– mali ve idari formlar

Önemli:
Sizin adınıza belge göndermiyoruz ve bir devlet kurumu değiliz.
Sadece belgelerin düzeltme için geri gönderilmemesi için
belgeleri doğru hazırlamanıza yardımcı oluyoruz.

Başlamak için bir belge kategorisi seçin."""

# ============================================================================
# GDPR / ЮРИДИЧНИЙ ТЕКСТ
# ============================================================================

GDPR_TEXT = """📜 <b>Kullanıcı Sözleşmesi</b>

Bu botu kullanarak aşağıdaki koşulları kabul edersiniz:

<b>1. Kişisel Verilerin İşlenmesi</b>
Bot, kişisel verilerinizi (ad, iletişim bilgileri, belgeler) yalnızca belge hazırlama hizmetleri sunmak amacıyla toplar ve işler.

<b>2. Veri Depolama</b>
• Verileriniz güvenli bir veritabanında saklanır
• Veriler yalnızca belge oluşturma için kullanılır
• Veriler izniniz olmadan üçüncü taraflarla paylaşılMAZ

<b>3. Haklarınız</b>
• Verilerinize erişim hakkı
• Verileri silme hakkı (komut /delete_data)
• Verileri düzeltme hakkı

<b>4. Güvenlik</b>
Verilerinizi korumak için şifreleme ve diğer önlemleri kullanıyoruz.

<b>5. Sorumluluk</b>
Kullanıcı, sağlanan verilerin doğruluğundan sorumludur. Bot, belge oluşturma aracıdır ve hukuki tavsiye sağlamaz.

"Onayla" düğmesine tıklayarak bu koşulları kabul edersiniz."""

# ============================================================================
# TЕКСТИ МЕНЮ ТА КНОПОК
# ============================================================================

MENU_TEXTS = {
    # Вибір мови
    'language_selection': '🌍 Dil seçin:',
    'btn_confirm': '✅ Onayla',
    
    # Головне меню
    'main_menu': '📋 Ana Menü',
    'welcome': '👋 Hoş geldiniz!',
    'select_action': 'Bir işlem seçin:',
    
    # Кнопки головного меню
    'btn_documents': '📄 Belgeler',
    'btn_my_data': '👤 Verilerim',
    'btn_orders': '📦 Siparişlerim',
    'btn_support': '💬 Destek',
    'btn_settings': '⚙️ Ayarlar',
    
    # Документи
    'documents_menu': '📄 Belge türünü seçin:',
    'doc_anmeldung': '🏠 Anmeldung (Kayıt)',
    'doc_kindergeld': '👶 Kindergeld (Çocuk Yardımı)',
    'doc_abmeldung': '📤 Abmeldung (Kayıt İptali)',
    
    # Навігація
    'btn_back': '◀️ Geri',
    'btn_cancel': '❌ İptal',
    
    # Замовлення
    'orders_menu': '📦 Siparişleriniz:',
    'no_orders': 'Henüz siparişiniz yok',
    'order_status_pending': '⏳ İşleniyor',
    'order_status_ready': '✅ Hazır',
    'order_status_paid': '💳 Ödendi',
    
    # Налаштування
    'settings_menu': '⚙️ Ayarlar:',
    'change_language': '🌍 Dil Değiştir',
    'delete_data': '🗑️ Verilerimi Sil',
}

# ============================================================================
# СИСТЕМНІ ПОВІДОМЛЕННЯ
# ============================================================================

MESSAGE_TEXTS = {
    # Успішні операції
    'success_saved': '✅ Veriler başarıyla kaydedildi',
    'success_deleted': '✅ Veriler başarıyla silindi',
    'success_updated': '✅ Veriler başarıyla güncellendi',
    
    # Помилки
    'error_general': '❌ Bir hata oluştu. Lütfen daha sonra tekrar deneyin.',
    'error_invalid_data': '❌ Geçersiz veri. Lütfen girilen değerleri kontrol edin.',
    'error_not_found': '❌ Veri bulunamadı',
    
    # Попередження
    'warning_empty_field': '⚠️ Bu alan boş bırakılamaz',
    'warning_invalid_format': '⚠️ Geçersiz veri formatı',
    
    # Підтвердження
    'confirm_delete': '⚠️ Emin misiniz? Bu işlem geri alınamaz.',
    'confirm_cancel': '⚠️ İptal etmek istediğinizden emin misiniz?',
    
    # Очікування
    'wait_processing': '⏳ İsteğiniz işleniyor...',
    'wait_generating': '⏳ Belge oluşturuluyor...',
    
    # Інше
    'feature_unavailable': '⚠️ Bu özellik geçici olarak kullanılamıyor',
}

# ============================================================================
# ТЕКСТИ ДЛЯ ДОКУМЕНТІВ
# ============================================================================

DOCUMENT_TEXTS = {
    'anmeldung_name': 'Anmeldung (İkamet Kaydı)',
    'anmeldung_desc': "Almanya'da yeni adres kaydı formu",
    'anmeldung_price': '9.99 EUR',
    
    'kindergeld_name': 'Kindergeld (Çocuk Yardımı Başvurusu)',
    'kindergeld_desc': 'Çocuklar için mali destek alma formu',
    'kindergeld_price': '14.99 EUR',
    
    'fill_form': '📝 Formu Doldur',
    'fields_required': 'Zorunlu alanlar yıldız (*) ile işaretlenmiştir',
    
    'order_created': '✅ Sipariş oluşturuldu',
    'order_number': '🆔 Sipariş numarası',
    'preview_ready': '✅ Önizleme hazır',
    'payment_required': '💳 Belgeyi almak için ödeme gerekli',
    'after_payment': 'Ödeme sonrası tamamlanmış PDF belgeyi alacaksınız',
    # My documents library
    'my_documents_btn': '📄 Belgelerim',
    'my_documents_title': '📄 <b>Belgelerim</b>\n\nÖdenen belgeleri buradan tekrar indirebilirsiniz.',
    'my_documents_empty': 'Henüz ödenmiş belgeniz yok.\n\nÖdemeden sonra burada görünecektir.',
    'btn_download_again': '📥 İndir',
    'back_to_menu': '◀️ Menüye dön',
}

WHAT_TO_DO_TEXTS = {
    'what_to_do_btn': '🧭 Ne yapmam gerekiyor?',
    'what_to_do_intro': 'Birkaç soruya cevap verin — durumunuza göre ne yapmanız gerektiğini söyleyeceğim. Karmaşık bürokrasi yok, sadece net bir plan.',
    'step_of': 'Adım %s / %s',
    'exit_flow': 'Çık',
    'q_arrived': 'Almanya\'ya yeni mi geldiniz?',
    'q_new_address': 'Almanya içinde yeni bir adrese mi taşındınız?',
    'q_alone_family': 'Yalnız mı yaşıyorsunuz yoksa ailenizle mi?',
    'q_permanent_address': 'Zaten kalıcı bir adresiniz var mı?',
    'q_housing_type': 'Ne tür bir konutta yaşıyorsunuz?',
    'q_wohnungsgeber': 'Ev sahibi onayınız (Wohnungsgeberbestätigung) var mı?',
    'q_where_before': 'Daha önce nerede yaşıyordunuz?',
    'q_when_moved': 'Ne zaman taşındınız?',
    'q_registered': 'Bürgeramt\'a kayıt oldunuz mu?',
    'q_status': 'Mevcut durumunuz nedir?',
    'opt_yes': 'Evet',
    'opt_no': 'Hayır',
    'opt_alone': 'Yalnız',
    'opt_family': 'Ailemle',
    'opt_rent': 'Kira',
    'opt_own': 'Mülk',
    'opt_other': 'Diğer',
    'opt_abroad': 'Yurtdışında',
    'opt_germany': 'Almanya\'da',
    'opt_nowhere': 'Hiçbir yerde / ilk kez',
    'opt_recent': 'Yakın zamanda (14 gün içinde)',
    'opt_long_ago': 'Uzun süre önce',
    'opt_work': 'Çalışma',
    'opt_study': 'Eğitim',
    'result_must_title': '🔴 Bunu yapmalısınız',
    'result_should_title': '🟡 Bunu öneriyoruz',
    'result_not_needed_title': '⚪ Buna gerek yok',
    'result_notes_title': '⚠️ Bilmeniz iyi olur',
    'result_must_register': '14 gün içinde Bürgeramt\'a adres kaydı (Anmeldung) yaptırın.',
    'result_must_wohnungsgeber': 'Ev sahibi onayı (Wohnungsgeberbestätigung) alın — kayıt için gerekli.',
    'result_should_health': 'Henüz yoksa sağlık sigortası yaptırın.',
    'result_should_bank': 'Maaş ve ödemeler için banka hesabı açın.',
    'result_should_tax_id': 'Vergi kimlik numaranızı (Steuer-ID) alın.',
    'result_not_reg_again': 'Tekrar kayıt olmanıza gerek yok — zaten kayıtlısınız.',
    'result_note_deadline': 'Adres kaydı: taşındıktan sonra 14 gün içinde yapmaya çalışın.',
    'result_note_wohnungsgeber': 'Ev sahibi onayı olmadan kayıt reddedilebilir — formu doldurmasını isteyin.',
    'recommendation_text': 'Verdiğiniz yanıtlara göre önerimiz: Anmeldung.',
    'recommendation_btn': 'Önerilen belgeyi görüntüle',
}

SITUATION_CHECKER_TEXTS = {
    'situation_checker_btn': '🔍 Durumum',
    'sc_intro': 'Birkaç Evet/Hayır sorusuna cevap verin — hangi belgelere ihtiyacınız olduğunu söyleyeceğim (Anmeldung, Abmeldung vb.).',
    'sc_step_of': 'Soru %s / %s',
    'sc_exit': 'Çık',
    'sc_q1': 'Almanya\'ya yeni mi geldiniz?',
    'sc_q2': 'Almanya içinde yeni bir adrese mi taşındınız?',
    'sc_q3': 'Mevcut adresiniz için Bürgeramt\'a zaten kayıt oldunuz mu?',
    'sc_q4': 'Mevcut adresinizden taşınıyor musunuz (kayıt sildirme)?',
    'sc_q5': 'Ev sahibi onayınız (Wohnungsgeberbestätigung) var mı?',
    'sc_q6': 'Aynı evde ailenizle mi yaşıyorsunuz?',
    'sc_yes': 'Evet',
    'sc_no': 'Hayır',
    'result_title': '📋 Verdiğiniz yanıtlara göre:',
    'result_anmeldung_yes': '✔ Anmeldung gerekli',
    'result_anmeldung_no': '✖ Anmeldung gerekmez',
    'result_abmeldung_yes': '✔ Abmeldung gerekli',
    'result_abmeldung_no': '✖ Abmeldung gerekmez',
    'result_deadline_note': '⚠ Taşındıktan sonra kayıt için 14 gününüz var',
    'cta_to_documents': '👉 Belgelere git',
    'sc_result_intro': '✅ Durumunuza göre ihtiyacınız olanlar:',
    'sc_section_residence': '📂 İkamet ve kayıt',
    'sc_section_employment': '📂 İş ve istihdam',
    'sc_section_benefits': '📂 Yardımlar ve destek',
    'sc_doc_anmeldung': '• Anmeldung — adres kaydı',
    'sc_doc_abmeldung': '• Abmeldung — adres kayıt sildirme',
    'sc_doc_steuer_id': '• Steuer-ID — vergi kimlik numarası',
    'sc_how_to_continue': 'ℹ️ Nasıl devam edilir:',
    'sc_step1': '1️⃣ «İkamet ve kayıt» bölümünü açın (veya başka bir bölüm)',
    'sc_step2': '2️⃣ Belgeyi seçin (örn. Anmeldung)',
    'sc_step3': '3️⃣ Formu doldurun',
    'sc_what_next': '👇 Ne yapmak istersiniz?',
    'sc_cta_documents': '📂 Belgelere git',
    'sc_back_menu': '⬅️ Geri',
    'sc_back_to_category': '⬅️ Geri',
    'sc_work_intro': 'Birkaç soruya cevap verin — «İş ve istihdam» kategorisinden hangi belgelerin sizin için olduğunu söyleyeceğim.',
    'sc_work_q1': 'İşten ayrılmayı veya iş sözleşmesini feshetmeyi mi planlıyorsunuz?',
    'sc_work_q2': 'İş kaydı (Gewerbeanmeldung) için yardım mı gerekiyor?',
    'sc_work_q3': 'İş arıyor musunuz veya işsiz olarak kayıt mı olacaksınız?',
    'sc_work_result_docs': '• Kündigung — fesih mektubu şablonu\n• Gewerbeanmeldung — iş kaydı\n• Arbeitslosmeldung / Arbeitslosengeld',
    'sc_benefits_intro': 'Birkaç soruya cevap verin — «Yardımlar ve destek» kategorisinden hangi belgelerin sizin için olduğunu söyleyeceğim.',
    'sc_benefits_q1': 'Sizinle yaşayan çocuklarınız var mı?',
    'sc_benefits_q2': 'Geliriniz asgari düzeyin altında mı?',
    'sc_benefits_q3': 'Kira yardımı (Wohngeld) mı gerekiyor?',
    'sc_benefits_result_docs': '• Kindergeld / Elterngeld / Kinderzuschlag\n• Bürgergeld — temel destek\n• Wohngeld',
    'menu_documents_btn': '📂 Belgeler',
    'menu_language_btn': '🌐 Dil',
    'documents_menu_title': '📂 Belge kategorisi seçin:',
}

LIFE_CHECKLIST_TEXTS = {
    'life_checklist_btn': '✅ Sırada ne var',
    'life_checklist_title': '✅ <b>Sırada ne var</b>\n\nÖnemli adımlar (kısa):',
    'lc_anmeldung': '📝 <b>Anmeldung</b> — Bürgeramt\'ta adres kaydı.',
    'lc_steuer_id': '🆔 <b>Steuer-ID</b> — vergi kimlik numarası.',
    'lc_krankenkasse': '🏥 <b>Krankenkasse</b> — sağlık sigortası.',
    'lc_rundfunkbeitrag': '📻 <b>Rundfunkbeitrag</b> — yayın katkı payı.',
    'lc_schule_kita': '🏫 <b>Okul / Kita</b> — çocuğunuz varsa.',
    'fill_document_btn': 'Belgeyi doldur',
    'back_to_menu': '◀️ Menüye dön',
}

DEADLINES_TEXTS = {
    'deadlines_btn': '⏰ Önemli süreler',
    'deadlines_title': '⏰ <b>Önemli süreler</b>\n\nGüvenilir bilgi (hatırlatma yok):',
    'd_anmeldung': '📝 <b>Anmeldung</b> — taşındıktan sonra 14 gün içinde.',
    'd_ummeldung': '🔄 <b>Ummeldung</b> — adres değişince, mümkünse hemen.',
    'd_kindergeld': '👶 <b>Kindergeld</b> — başvuru 6 aya kadar geriye dönük yapılabilir.',
    'back_to_menu': '◀️ Menüye dön',
}

DOCUMENT_NEXT_STEPS = {
    'anmeldung': (
        '📌 <b>Sonraki adımlar</b>\n\n'
        '📍 <b>Nereye verilir:</b> İkamet adresinizdeki vatandaş bürosu (Bürgeramt / Einwohnermeldeamt).\n\n'
        '⏰ <b>Süre:</b> Taşındıktan sonra <b>14 gün</b> içinde kayıt yaptırmanız gerekir.\n\n'
        '📎 <b>Yanınızda götürün:</b> Kimlik veya pasaport, ev sahibi onayı (Wohnungsgeberbestätigung), doldurulmuş Anmeldung formu.'
    ),
    'kindergeld': (
        '📌 <b>Sonraki adımlar</b>\n\n'
        '📍 <b>Nereye verilir:</b> Federal İş Ajansı Familienkasse veya çevrimiçi başvuru.\n\n'
        '📎 <b>Yanınızda götürün:</b> Doldurulmuş başvuru, kimlik, çocukların doğum belgeleri, gerekirse gelir belgesi.'
    ),
    'abmeldung': (
        '📌 <b>Sonraki adımlar</b>\n\n'
        '📍 <b>Nereye verilir:</b> Son kayıtlı adresinizdeki vatandaş bürosu.\n\n'
        '⏰ <b>Süre:</b> Taşınmadan önce veya hemen sonra vermeniz iyi olur.\n\n'
        '📎 <b>Yanınızda götürün:</b> Kimlik veya pasaport, doldurulmuş Abmeldung formu.'
    ),
}