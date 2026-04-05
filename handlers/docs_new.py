# -*- coding: utf-8 -*-
"""
handlers/docs_new.py - WebApp + PDF Preview (aiogram 2.x)
IMPORTANT:
- No global dp usage here
- Use register_docs_handlers(dp) from bot.py



RECENT CHANGES:
- Added payment gating to handle_final_pdf() - requires payment before generating full sample PDF
- Added _check_payment_status() helper to verify user payment status
- Removed stuck ReplyKeyboard after form completion (added ReplyKeyboardRemove() calls)
- Updated UX: form completion state tracking prevents showing "Почати заповнення" button after completion
- Added "Back" buttons to all screens for consistent navigation

UX FLOW RULES (CRITICAL - DO NOT BREAK):
1. "Почати заповнення" button:
   - Appears ONLY before WebApp form (in process_doc_choice() and handle_edit_answers())
   - MUST be removed immediately after form submission (handle_webapp_data())
   - NEVER appears after preview or final PDF

2. "Назад" button:
   - MUST exist on ALL screens except: /start, WebApp form itself, final PDF delivery screen
   - Returns to immediately previous logical state (back_to_main callback)

3. Payment gating:
   - handle_final_pdf() ALWAYS checks payment status before generating
   - stripe_handler.deliver_document() is safe - called AFTER payment verification
   - NO other paths should call create_final_pdf() without payment check

4. Keyboard hygiene:
   - ReplyKeyboardRemove() MUST be called after:
     * Form submission (handle_webapp_data())
     * Preview PDF delivery (_generate_preview_and_send())
     * Final PDF delivery (handle_final_pdf())

5. PDF naming:
   - Preview PDF: "PDF-роз'яснення документа" (1 page explanation, watermarked)
   - Full PDF: "Повний зразок документа" (multi-page, requires payment, no watermark)

6. DATA PERSISTENCE (CRITICAL - DO NOT BREAK):
   - _PENDING_PREVIEWS[(user_id, doc_type)] stores questionnaire data in-memory
   - Data MUST persist across ALL navigation:
     * Category selection (handle_category_selection)
     * Document selection (process_doc_choice)
     * Back buttons (handle_back_to_main, handle_back_to_main_menu)
     * Language change (handle_language_selection, handle_set_language_from_menu)
   - Data is ONLY cleared by:
     * _cleanup_old_previews() - removes entries older than 20 minutes (automatic TTL, applies to all entries)
     * Explicit "Start over" action (not implemented yet)
   - Data is persisted to disk (_pending_previews.json) on every form submission and restored on bot restart
   - NEVER clear data during normal navigation or errors
   - When opening WebApp, pre-fill with saved_answers if available
   - When changing language, update lang/user_lang in existing _PENDING_PREVIEWS entry
"""

import os
import json
import logging
import time
from typing import Dict, Any, Optional, Tuple

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    WebAppInfo,
    InputFile,
)
from aiogram.dispatcher.filters import Command
from pathlib import Path

from backend.document_config import get_requires_bundesland
from backend.geo_intelligence import get_authority_address, format_authority_info
from backend.pdf_generator import create_preview, create_final_pdf, OUTPUT_DIR

try:
    from utils.helpers import get_user_lang
except ImportError:

    def get_user_lang(user_id: int) -> str:
        return "uk"


try:
    import fitz

    _FITZ_AVAILABLE = True
except Exception:
    _FITZ_AVAILABLE = False

logger = logging.getLogger(__name__)

# Load WEBAPP_URL from environment or config
WEBAPP_BASE_URL = os.getenv("WEBAPP_URL", "").strip()
if not WEBAPP_BASE_URL:
    try:
        import config

        WEBAPP_BASE_URL = getattr(config, "WEBAPP_URL", "").strip()
    except (ImportError, AttributeError):
        pass
if not WEBAPP_BASE_URL:
    logger.warning("⚠️ WEBAPP_URL not found in env or config - WebApp may not work")

_PENDING_PREVIEWS: Dict[Tuple[int, str], Dict[str, Any]] = {}
_PENDING_PREVIEWS_PATH = OUTPUT_DIR / "_pending_previews.json"


def _save_previews() -> None:
    """Persist _PENDING_PREVIEWS to disk so data survives bot restarts."""
    try:
        serializable = {f"{k[0]}:{k[1]}": v for k, v in _PENDING_PREVIEWS.items()}
        _PENDING_PREVIEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_PENDING_PREVIEWS_PATH, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("Failed to persist _PENDING_PREVIEWS: %s", e)


def _load_previews() -> None:
    """Load _PENDING_PREVIEWS from disk on startup, skipping expired entries (>20 min)."""
    try:
        if not _PENDING_PREVIEWS_PATH.exists():
            return
        with open(_PENDING_PREVIEWS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cutoff = time.time() - 1200  # 20 minutes
        loaded = 0
        for raw_key, entry in data.items():
            if entry.get("created_at", 0) < cutoff:
                continue
            parts = raw_key.split(":", 1)
            if len(parts) != 2:
                continue
            try:
                user_id = int(parts[0])
            except ValueError:
                continue
            _PENDING_PREVIEWS[(user_id, parts[1])] = entry
            loaded += 1
        if loaded:
            logger.info(
                "Restored %d pending preview(s) from disk after restart", loaded
            )
    except Exception as e:
        logger.warning("Failed to load persisted _PENDING_PREVIEWS: %s", e)


_load_previews()


def _get_latest_pending(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Return the most recently created pending entry for a user across ALL doc_types.
    Used by handlers that do not carry doc_type in their callback_data.
    """
    uid = _uid(user_id)
    matches = [(k, v) for k, v in _PENDING_PREVIEWS.items() if k[0] == uid]
    if not matches:
        return None
    _, best = max(matches, key=lambda kv: kv[1].get("created_at", 0))
    return best


# Single sentence shown ABOVE the PDF — explains this screen is for checking form data
_PREVIEW_EXPLANATION_TEXTS = {
    "uk": "📋 Це перевірка правильності заповнення даних анкети.",
    "ua": "📋 Це перевірка правильності заповнення даних анкети.",
    "en": "📋 This is a check of the correctness of the information you entered in the form.",
    "de": "📋 Dies ist eine Überprüfung der Richtigkeit der von Ihnen eingegebenen Formulardaten.",
    "pl": "📋 To sprawdzenie poprawności danych wprowadzonych w formularzu.",
    "tr": "📋 Bu, forma girdiğiniz bilgilerin doğruluğunun kontrolüdür.",
    "ar": "📋 هذا فحص لصحة البيانات التي أدخلتها في النموذج.",
}

# Localized fallback for "form received" (used when _build_post_form_confirmation_menu returns None)
_FORM_RECEIVED_TEXTS = {
    "uk": "✅ Анкету отримано. Оберіть дію:",
    "en": "✅ Form received. Choose an action:",
    "de": "✅ Formular erhalten. Wählen Sie eine Aktion:",
    "pl": "✅ Formularz otrzymany. Wybierz akcję:",
    "tr": "✅ Form alındı. Bir işlem seçin:",
    "ar": "✅ تم استلام النموذج. اختر إجراءً:",
}

_NO_DOC_SELECTED_TEXTS = {
    "uk": "⚠️ Будь ласка, спочатку оберіть документ з меню, щоб почати заповнення.",
    "en": "⚠️ Please select a document from the menu first.",
    "de": "⚠️ Bitte wählen Sie zuerst ein Dokument aus dem Menü.",
    "pl": "⚠️ Proszę najpierw wybrać dokument z menu.",
    "tr": "⚠️ Lütfen önce menüden bir belge seçin.",
    "ar": "⚠️ يرجى اختيار مستند من القائمة أولاً.",
}

_ONBOARDING_INCOMPLETE_TEXTS = {
    "uk": "⚠️ Будь ласка, спочатку завершіть реєстрацію через /start",
    "en": "⚠️ Please complete onboarding first via /start",
    "de": "⚠️ Bitte schließen Sie zuerst die Registrierung über /start ab",
    "pl": "⚠️ Proszę najpierw zakończyć rejestrację przez /start",
    "tr": "⚠️ Lütfen önce /start ile kaydı tamamlayın",
    "ar": "⚠️ يرجى إكمال التسجيل أولاً عبر /start",
}

_WEBAPP_URL_MISSING_TEXTS = {
    "uk": "⚠️ WebApp URL не налаштований. Зверніться до адміністратора.",
    "en": "⚠️ WebApp URL is not configured. Contact the administrator.",
    "de": "⚠️ WebApp-URL ist nicht konfiguriert. Kontaktieren Sie den Administrator.",
    "pl": "⚠️ URL aplikacji nie jest skonfigurowany. Skontaktuj się z administratorem.",
    "tr": "⚠️ WebApp URL'si yapılandırılmamış. Yöneticiyle iletişime geçin.",
    "ar": "⚠️ رابط التطبيق غير مُعدّ. تواصل مع المشرف.",
}

_PREVIEW_FAILED_TEXTS = {
    "uk": "❌ Не вдалося створити приклад документа. Спробуйте, будь ласка, ще раз або поверніться до меню.",
    "en": "❌ Failed to create document preview. Please try again or go back to the menu.",
    "de": "❌ Dokumentenvorschau konnte nicht erstellt werden. Bitte versuchen Sie es erneut.",
    "pl": "❌ Nie udało się utworzyć podglądu dokumentu. Spróbuj ponownie lub wróć do menu.",
    "tr": "❌ Belge önizlemesi oluşturulamadı. Lütfen tekrar deneyin veya menüye dönün.",
    "ar": "❌ فشل في إنشاء معاينة المستند. يرجى المحاولة مرة أخرى أو العودة إلى القائمة.",
}


def _get_form_received_text(lang: str) -> str:
    return _FORM_RECEIVED_TEXTS.get(lang, _FORM_RECEIVED_TEXTS["en"])


def _uid(x):
    """Normalize user_id to int for _PENDING_PREVIEWS dict key consistency."""
    try:
        return int(x)
    except (ValueError, TypeError):
        return x


def _check_onboarding_complete(user_id: int) -> bool:
    """Check if user has completed onboarding (GDPR accepted)"""
    try:
        from utils.helpers import get_db

        db = get_db()
        profile = db.get_profile(user_id)
        if not profile:
            return False
        gdpr_value = profile.get("gdpr_accepted", 0)
        return (gdpr_value == 1) if gdpr_value is not None else False
    except Exception as e:
        logger.error(f"❌ Error checking onboarding status for user {user_id}: {e}")
        return False


def _norm_lang(lang: Optional[str], user_id: Optional[int] = None) -> str:
    """Normalize language code to consistent format."""
    lang = (lang or "").strip().lower()
    if lang == "ua":
        lang = "uk"
    if lang in ("uk", "en", "de", "pl", "tr", "ar"):
        return lang
    if user_id:
        try:
            fallback = (get_user_lang(user_id) or "uk").strip().lower()
            if fallback == "ua":
                fallback = "uk"
            return (
                fallback if fallback in ("uk", "en", "de", "pl", "tr", "ar") else "uk"
            )
        except Exception:
            return "uk"
    return "uk"


def _make_onepage_watermarked_preview(source_path: str) -> Optional[str]:
    """
    Copy the full preview PDF to a separate output path so the original
    file can be cleaned up independently.

    All pages are preserved.  The preview watermark and reassurance text
    are already embedded by _FormBuilder._apply_watermark() — no second
    watermark is added here.
    """
    if not _FITZ_AVAILABLE:
        return None
    if not source_path or not os.path.exists(source_path):
        return None
    try:
        doc = fitz.open(source_path)
        if doc.page_count < 1:
            return None
        out_path = str(OUTPUT_DIR / f"preview_processed_{int(time.time()*1000)}.pdf")
        doc.save(out_path)
        doc.close()
        return out_path
    except Exception as e:
        logger.warning(f"⚠️ Failed to copy preview PDF: {e}")
        return None


def _cleanup_old_previews(exclude_user_id: Optional[int] = None) -> None:
    """
    Remove pending previews older than 20 minutes (TTL cleanup).

    CRITICAL: This function ONLY removes expired entries (>20 min old).
    It does NOT clear active user data during navigation.
    Active questionnaire data must be preserved across navigation.

    Args:
        exclude_user_id: If provided, this user_id will NOT be deleted even if expired.
    """
    current_time = time.time()
    exclude_uid = _uid(exclude_user_id) if exclude_user_id is not None else None
    # Keys are now (user_id, doc_type) tuples — unpack accordingly.
    expired_keys = [
        key
        for key, data in _PENDING_PREVIEWS.items()
        if key[0] != exclude_uid  # Exclude current user from cleanup
        and data.get("created_at", 0) > 0  # Only delete entries with valid created_at
        and current_time - data.get("created_at", 0) > 1200  # 20 minutes
    ]
    for key in expired_keys:
        data_age = current_time - _PENDING_PREVIEWS[key].get("created_at", 0)
        _PENDING_PREVIEWS.pop(key, None)
        logger.info(
            f"🗑️ DEBUG: DELETED _PENDING_PREVIEWS[{key}] - reason: TTL expired (age: {data_age:.1f}s, >1200s)"
        )


_PREVIEW_DISCLAIMER_TEXTS = {
    "uk": "Це заповнений зразок для орієнтування — не офіційний документ",
    "ua": "Це заповнений зразок для орієнтування — не офіційний документ",
    "en": "This is a filled example for reference only — not an official document",
    "de": "Dies ist ein ausgefülltes Beispiel zur Orientierung – kein offizielles Dokument",
    "pl": "To wypełniony przykład orientacyjny — nie jest oficjalnym dokumentem",
    "tr": "Bu yalnızca referans amaçlı doldurulmuş bir örnektir — resmi belge değildir",
    "ar": "هذا مثال مملوء للاسترشاد فقط — وليس وثيقة رسمية",
}


def _add_preview_watermark(
    source_path: str, user_id: int, doc_type: str, lang: str = "de"
) -> Optional[str]:
    """
    Add PREVIEW watermark to demo PDF using PyMuPDF.
    Creates temporary file with watermark overlay.
    """
    try:
        import fitz  # PyMuPDF

        # Open source PDF
        doc = fitz.open(source_path)
        if doc.page_count < 1:
            return None

        # Create temporary output path
        import tempfile

        temp_fd, temp_path = tempfile.mkstemp(
            suffix="_watermarked.pdf", prefix=f"demo_{user_id}_{doc_type}_"
        )
        os.close(temp_fd)  # Close file descriptor, keep path

        _disclaimer = _PREVIEW_DISCLAIMER_TEXTS.get(
            lang, _PREVIEW_DISCLAIMER_TEXTS["en"]
        )

        # Add top red disclaimer line to each page — no watermark overlay
        for page in doc:
            rect = page.rect
            page_width = rect.width
            page.insert_text(
                fitz.Point(page_width * 0.05, 18),
                _disclaimer,
                fontname="helv",
                fontsize=9,
                color=(0.85, 0, 0),
            )

        # Save watermarked PDF
        doc.save(temp_path)
        doc.close()

        logger.info(
            f"WATERMARK_ADDED: {temp_path} for user {user_id} doc_type {doc_type} lang {lang}"
        )
        return temp_path

    except Exception as e:
        logger.warning(f"Failed to add watermark to demo PDF: {e}")
        return None


def _cleanup_old_preview_files() -> None:
    """Clean up old preview_*.pdf files older than 20 minutes."""
    try:
        import glob

        current_time = time.time()
        preview_pattern = str(OUTPUT_DIR / "preview_*.pdf")

        for filepath in glob.glob(preview_pattern):
            try:
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > 1200:
                    os.remove(filepath)
                    logger.debug(f"🧹 Cleaned up old preview file: {filepath}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to cleanup preview file {filepath}: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Preview file cleanup failed: {e}")


def _webapp_url(
    doc_type: str,
    lang: str = "uk",
    saved_answers: Optional[Dict[str, Any]] = None,
    chat_id: Optional[int] = None,
) -> str:
    """
    Build WebApp URL for the NEW multi-language form (6 languages, radio buttons).

    CRITICAL: This function MUST point to the NEW form, not the old Ukrainian-only form.
    The new form is located at webapp/index.html and supports:
    - 6 languages: uk, en, de, pl, tr, ar
    - Radio button language selector
    - Modern UI with proper form handling
    - Pre-filling form fields from saved answers

    Args:
        doc_type: Document type (e.g., 'anmeldung', 'kindergeld')
        lang: User language code (normalized automatically)
        saved_answers: Optional dict of saved answers to pre-fill the form
        chat_id: Optional Telegram chat_id for HTTP fallback (post-form menu)

    Returns:
        Full WebApp URL with doc_type, lang, and optionally saved_data, chat_id parameters
    """
    if not WEBAPP_BASE_URL:
        logger.error("❌ WEBAPP_BASE_URL is not configured - WebApp will not work!")
        return ""

    lang = _norm_lang(lang)

    # CRITICAL: Use doc_type parameter (new form expects this)
    # The new form accepts both 'doc_type' and 'doc', but 'doc_type' is preferred
    # OLD form used 'doc' parameter - NEW form uses 'doc_type'
    sep = "&" if "?" in WEBAPP_BASE_URL else "?"

    # Build URL with doc_type parameter for the NEW multi-language form
    url = f"{WEBAPP_BASE_URL}{sep}doc_type={doc_type}&lang={lang}&v={int(time.time()*1000)}"
    if chat_id is not None:
        url += f"&chat_id={chat_id}"

    # If saved answers exist, encode them as base64 JSON and add to URL
    # This allows the WebApp to pre-fill the form when reopened
    if saved_answers and len(saved_answers) > 0:
        try:
            import base64

            answers_json = json.dumps(saved_answers)
            answers_b64 = base64.urlsafe_b64encode(answers_json.encode("utf-8")).decode(
                "utf-8"
            )
            url += f"&saved_data={answers_b64}"
            logger.debug(
                f"🔗 WebApp URL includes saved_data: {len(saved_answers)} fields"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to encode saved answers for WebApp URL: {e}")

    logger.info("WEBAPP_URL_BUILT | doc_type=%s lang=%s url=%s", doc_type, lang, url)
    return url


def _get_webapp_button_text(lang: str) -> str:
    """Get localized WebApp button text. Fallback to 'en' if lang missing, NOT 'uk'."""
    texts = {
        "uk": "📝 Почати заповнення",
        "ua": "📝 Почати заповнення",
        "en": "📝 Start filling",
        "de": "📝 Ausfüllen beginnen",
        "pl": "📝 Zacznij wypełniać",
        "tr": "📝 Doldurmaya başla",
        "ar": "📝 ابدأ التعبئة",
    }
    # CRITICAL: Fallback to 'en', NOT 'uk'
    return texts.get(lang, texts.get("en", "📝 Start filling"))


def _get_flow_before_form_text(lang: str) -> str:
    """Three-line clarity block: time + what you get + why it matters."""
    texts = {
        "uk": (
            "⏱ Займе ~4 хвилини\n"
            "📄 Ви отримаєте заповнений зразок готовий до здачі\n"
            "⚠️ Допомагає уникнути відмови через помилки"
        ),
        "ua": (
            "⏱ Займе ~4 хвилини\n"
            "📄 Ви отримаєте заповнений зразок готовий до здачі\n"
            "⚠️ Допомагає уникнути відмови через помилки"
        ),
        "en": (
            "⏱ Takes ~4 minutes\n"
            "📄 You will get a filled example ready to submit\n"
            "⚠️ Helps avoid rejection due to formatting errors"
        ),
        "de": (
            "⏱ Dauert ~4 Minuten\n"
            "📄 Sie erhalten ein ausgefülltes Muster zur Einreichung\n"
            "⚠️ Verhindert Ablehnung durch Formatfehler"
        ),
        "pl": (
            "⏱ Zajmie ~4 minuty\n"
            "📄 Otrzymasz wypełniony wzór gotowy do złożenia\n"
            "⚠️ Pomaga uniknąć odrzucenia z powodu błędów"
        ),
        "tr": (
            "⏱ ~4 dakika sürer\n"
            "📄 Teslime hazır doldurulmuş bir örnek alacaksınız\n"
            "⚠️ Format hatalarından kaynaklanan reddi önler"
        ),
        "ar": (
            "⏱ يستغرق ~4 دقائق\n"
            "📄 ستحصل على مثال مملوء جاهز للتقديم\n"
            "⚠️ يساعد على تجنب الرفض بسبب أخطاء التنسيق"
        ),
    }
    return texts.get(lang, texts.get("en", "⏱ Takes ~4 minutes\n📄 Filled example ready to submit\n⚠️ Helps avoid rejection"))


def _get_preparing_document_text(lang: str) -> str:
    """Intermediate state after form submission — confirms receipt and signals work in progress."""
    from backend.translations import ui as _ui
    return _ui("form_submitted", lang)


# ── PRE-FORM PREVIEW ──────────────────────────────────────────────────────────
# Sample data used to render the "preview before form" image.
# Shows what the user's filled document will look like (generic German names).
_PREVIEW_SAMPLE_DATA: dict = {
    "first_name": "Maria",
    "last_name": "Müller",
    "birth_date": "15.03.1990",
    "vorname": "Maria",
    "nachname": "Müller",
    "geburtsdatum": "15.03.1990",
    "geburtsort": "Berlin",
    "nationalitaet": "ukrainisch",
    "nationality": "ukrainian",
    "strasse": "Musterstraße 12",
    "hausnummer": "12",
    "plz": "10115",
    "ort": "Berlin",
    "bundesland": "Berlin",
    "einzugsdatum": "01.04.2024",
    "auszugsdatum": "01.04.2024",
    "move_in_date": "01.04.2024",
    "email": "maria.mueller@example.com",
    "phone": "+49 30 12345678",
    "mb_vm_nachname": "Müller",
    "mb_vm_vorname": "Maria",
    "mb_m_nachname": "Müller",
    "mb_m_vorname": "Maria",
    "vl_nachname": "Müller",
    "vl_vorname": "Maria",
}


def _get_preform_preview_bytes(doc_type: str) -> bytes | None:
    """
    Generate a PNG snippet of the real template filled with sample data.
    Returns raw PNG bytes or None if generation is not possible.
    Cached in memory to avoid repeated PDF rendering for the same doc_type.
    """
    if not _FITZ_AVAILABLE:
        return None
    cache_key = f"_preform_preview_{doc_type}"
    cached = _PENDING_PREVIEWS.get(("__preview_cache__", cache_key))
    if cached is not None:
        return cached.get("png") if cached else None
    try:
        from backend.pdf_preview import create_template_snippet_image
        png = create_template_snippet_image(
            doc_type=doc_type,
            user_data=_PREVIEW_SAMPLE_DATA,
            lang="de",
        )
        _PENDING_PREVIEWS[("__preview_cache__", cache_key)] = {"png": png}
        return png
    except Exception as _exc:
        logger.debug("preform_preview: %s: %s", doc_type, _exc)
        _PENDING_PREVIEWS[("__preview_cache__", cache_key)] = None
        return None


# Preform card caption texts (shown above the form button)
_PREFORM_CARD_TEXTS: dict = {
    "uk": (
        "👆 <b>Так виглядає ваш заповнений документ</b>\n\n"
        "Ми заповнимо його вашими даними.\n"
        "Займе ~4 хвилини."
    ),
    "ua": (
        "👆 <b>Так виглядає ваш заповнений документ</b>\n\n"
        "Ми заповнимо його вашими даними.\n"
        "Займе ~4 хвилини."
    ),
    "en": (
        "👆 <b>This is what your filled document looks like</b>\n\n"
        "We'll fill it with your data.\n"
        "Takes ~4 minutes."
    ),
    "de": (
        "👆 <b>So sieht Ihr ausgefülltes Dokument aus</b>\n\n"
        "Wir füllen es mit Ihren Daten aus.\n"
        "Dauert ~4 Minuten."
    ),
    "pl": (
        "👆 <b>Tak wygląda wypełniony dokument</b>\n\n"
        "Uzupełnimy go Twoimi danymi.\n"
        "Zajmie ~4 minuty."
    ),
    "tr": (
        "👆 <b>Doldurulmuş belgeniz böyle görünüyor</b>\n\n"
        "Belgeyi verilerinizle dolduracağız.\n"
        "~4 dakika sürer."
    ),
    "ar": (
        "👆 <b>هكذا يبدو مستندك المملوء</b>\n\n"
        "سنملؤه ببياناتك.\n"
        "يستغرق ~4 دقائق."
    ),
}

_DOC_GERMAN_NAMES = {
    "anmeldung": "Anmeldung",
    "abmeldung": "Abmeldung",
    "ummeldung": "Ummeldung",
    "wohnungsgeberbestaetigung": "Wohnungsgeberbestätigung",
    "meldebescheinigung": "Meldebescheinigung",
    "anmeldung_familie": "Anmeldung Familie",
    "kindergeld": "Kindergeld",
    "elterngeld": "Elterngeld",
    "kinderzuschlag": "Kinderzuschlag",
    "unterhaltsvorschuss": "Unterhaltsvorschuss",
    "anlage_kind": "Anlage Kind",
    "steuer_id_kind": "Steuer-ID Kind",
    "buergergeld": "Bürgergeld",
    "wohngeld": "Wohngeld",
    "arbeitslosengeld_1": "Arbeitslosengeld I",
    "arbeitslosengeld_2": "Arbeitslosengeld II",
    "krankenversicherung_anmeldung": "Krankenversicherung Anmeldung",
    "sozialversicherungsnummer": "Sozialversicherungsnummer",
    "arbeitserlaubnis": "Arbeitserlaubnis",
    "steuererklaerung": "Steuererklärung",
    "gewerbeanmeldung": "Gewerbeanmeldung",
    "kuendigung": "Kündigung",
    "arbeitslosmeldung": "Arbeitslosmeldung",
    "aufenthaltstitel": "Aufenthaltstitel",
}

# Short one-liner explaining WHY the user needs this document (per doc_type, per lang).
# DE intentionally omitted — for DE the German name alone is self-explanatory.
_DOC_INTRO = {
    "anmeldung": {
        "ua": "Обов'язкова реєстрація — 14 днів після переїзду. Прострочення = штраф",
        "uk": "Обов'язкова реєстрація — 14 днів після переїзду. Прострочення = штраф",
        "en": "Required within 14 days of moving. Late registration = fine",
        "de": "Pflichtanmeldung innerhalb 14 Tagen nach Umzug. Verspätung = Bußgeld",
        "pl": "Obowiązkowa rejestracja w 14 dni od przeprowadzki. Opóźnienie = kara",
        "tr": "Taşınmadan sonra 14 gün içinde zorunlu. Gecikme = para cezası",
        "ar": "تسجيل إلزامي خلال 14 يومًا. التأخر = غرامة",
    },
    "abmeldung": {
        "ua": "Потрібно при виїзді з Німеччини",
        "uk": "Потрібно при виїзді з Німеччини",
        "en": "Required when leaving Germany",
        "de": "Erforderlich beim Wegzug aus Deutschland",
        "pl": "Wymagane przy wyjeździe z Niemiec",
        "tr": "Almanya'dan ayrılırken gereklidir",
        "ar": "مطلوب عند مغادرة ألمانيا",
    },
    "ummeldung": {
        "ua": "Потрібно при переїзді на нову адресу в Німеччині",
        "uk": "Потрібно при переїзді на нову адресу в Німеччині",
        "en": "Required when moving to a new address within Germany",
        "de": "Erforderlich bei Umzug innerhalb Deutschlands",
        "pl": "Wymagane przy zmianie adresu w Niemczech",
        "tr": "Almanya içinde adres değişikliğinde gereklidir",
        "ar": "مطلوب عند الانتقال إلى عنوان جديد في ألمانيا",
    },
    "wohnungsgeberbestaetigung": {
        "ua": "Орендодавець повинен видати для вашої реєстрації",
        "uk": "Орендодавець повинен видати для вашої реєстрації",
        "en": "Your landlord must provide this for your registration",
        "de": "Muss vom Vermieter für Ihre Anmeldung ausgestellt werden",
        "pl": "Wynajmujący musi dostarczyć do rejestracji",
        "tr": "Ev sahibiniz kayıt için bunu sağlamalıdır",
        "ar": "يجب أن يقدمه المالك لتسجيلك",
    },
    "meldebescheinigung": {
        "ua": "Офіційне підтвердження вашої зареєстрованої адреси",
        "uk": "Офіційне підтвердження вашої зареєстрованої адреси",
        "en": "Official proof of your registered address",
        "de": "Offizieller Nachweis Ihrer gemeldeten Adresse",
        "pl": "Oficjalny dowód zarejestrowanego adresu",
        "tr": "Kayıtlı adresinizin resmi kanıtı",
        "ar": "إثبات رسمي لعنوانك المسجل",
    },
    "kindergeld": {
        "ua": "Допомога до €250/міс на дитину. Заяву можна подати лише за останні 6 місяців — кожен місяць затримки = втрата €250",
        "uk": "Допомога до €250/міс на дитину. Заяву можна подати лише за останні 6 місяців — кожен місяць затримки = втрата €250",
        "en": "Up to €250/month per child. Claim is retroactive only 6 months — every month of delay = €250 lost",
        "de": "Bis zu €250/Monat pro Kind. Rückwirkend nur 6 Monate — jeder Monat Verzögerung = €250 verloren",
        "pl": "Do €250/mies. na dziecko. Wniosek retroaktywny tylko 6 miesięcy — każdy miesiąc opóźnienia = strata €250",
        "tr": "Çocuk başına aylık €250'ye kadar. Geriye dönük yalnızca 6 ay — her ay gecikme = €250 kayıp",
        "ar": "حتى €250/شهر لكل طفل. الطلب رجعي لـ 6 أشهر فقط — كل شهر تأخير = €250 ضائعة",
    },
    "elterngeld": {
        "ua": "Допомога до €1 800/міс після народження. Подати протягом 3 місяців від пологів",
        "uk": "Допомога до €1 800/міс після народження. Подати протягом 3 місяців від пологів",
        "en": "Up to €1,800/month after birth. Apply within 3 months of delivery",
        "de": "Bis zu €1.800/Monat nach der Geburt. Antrag innerhalb 3 Monate stellen",
        "pl": "Do €1 800/mies. po urodzeniu. Złóż wniosek w ciągu 3 miesięcy od porodu",
        "tr": "Doğum sonrası aylık €1.800'e kadar. Doğumdan itibaren 3 ay içinde başvur",
        "ar": "حتى €1,800/شهر بعد الولادة. تقدم بالطلب خلال 3 أشهر من الولادة",
    },
    "kinderzuschlag": {
        "ua": "Додаткова допомога для сімей з низьким доходом",
        "uk": "Додаткова допомога для сімей з низьким доходом",
        "en": "Extra benefit for low-income families with children",
        "de": "Zusatzleistung für Familien mit geringem Einkommen",
        "pl": "Dodatkowy zasiłek dla rodzin o niskich dochodach",
        "tr": "Düşük gelirli aileler için ek yardım",
        "ar": "إعانة إضافية للعائلات ذات الدخل المنخفض",
    },
    "unterhaltsvorschuss": {
        "ua": "Аванс по аліментах від держави для одиноких батьків",
        "uk": "Аванс по аліментах від держави для одиноких батьків",
        "en": "State child support advance for single parents",
        "de": "Staatlicher Unterhaltsvorschuss für Alleinerziehende",
        "pl": "Zaliczka alimentacyjna dla samotnych rodziców",
        "tr": "Tek ebeveynler için devlet nafaka avansı",
        "ar": "سلفة نفقة حكومية للوالدين العازبين",
    },
    "buergergeld": {
        "ua": "Допомога до €563/міс від Jobcenter. Одна помилка в заяві = відмова на місяць без виплат",
        "uk": "Допомога до €563/міс від Jobcenter. Одна помилка в заяві = відмова на місяць без виплат",
        "en": "Up to €563/month from Jobcenter. One form error = month without payment",
        "de": "Bis zu €563/Monat vom Jobcenter. Ein Fehler = Monat ohne Zahlung",
        "pl": "Do €563/mies. z Jobcenter. Jeden błąd w formularzu = miesiąc bez wypłaty",
        "tr": "Jobcenter'dan aylık €563'e kadar. Bir form hatası = ödemesiz ay",
        "ar": "حتى €563/شهر من مركز التوظيف. خطأ واحد = شهر بدون مدفوعات",
    },
    "wohngeld": {
        "ua": "Допомога для зменшення витрат на оренду",
        "uk": "Допомога для зменшення витрат на оренду",
        "en": "Housing benefit to reduce rent costs",
        "de": "Wohngeld zur Senkung der Mietkosten",
        "pl": "Dodatek mieszkaniowy na obniżenie czynszu",
        "tr": "Kira maliyetlerini azaltmak için konut yardımı",
        "ar": "بدل سكن لتقليل تكاليف الإيجار",
    },
    "arbeitslosengeld_1": {
        "ua": "Допомога по безробіттю після звільнення",
        "uk": "Допомога по безробіттю після звільнення",
        "en": "Unemployment benefit after job loss",
        "de": "Arbeitslosengeld nach Jobverlust",
        "pl": "Zasiłek dla bezrobotnych po utracie pracy",
        "tr": "İş kaybından sonra işsizlik yardımı",
        "ar": "إعانة بطالة بعد فقدان الوظيفة",
    },
    "gewerbeanmeldung": {
        "ua": "Реєстрація підприємницької діяльності",
        "uk": "Реєстрація підприємницької діяльності",
        "en": "Register a business or freelance activity",
        "de": "Gewerbeanmeldung für selbstständige Tätigkeit",
        "pl": "Rejestracja działalności gospodarczej",
        "tr": "İş veya serbest faaliyet kaydı",
        "ar": "تسجيل نشاط تجاري أو حر",
    },
    "kuendigung": {
        "ua": "Шаблон листа для розірвання трудового договору",
        "uk": "Шаблон листа для розірвання трудового договору",
        "en": "Letter template for employment termination",
        "de": "Vorlage für ein Kündigungsschreiben",
        "pl": "Szablon wypowiedzenia umowy o pracę",
        "tr": "İş sözleşmesi fesih mektubu şablonu",
        "ar": "نموذج رسالة إنهاء عقد العمل",
    },
    "aufenthaltstitel": {
        "ua": "Подовження дозволу на перебування. Помилка в документах = ризик для права жити в Німеччині",
        "uk": "Подовження дозволу на перебування. Помилка в документах = ризик для права жити в Німеччині",
        "en": "Residence permit extension. A form error risks your right to stay in Germany",
        "de": "Verlängerung des Aufenthaltstitels. Fehler riskieren Ihr Aufenthaltsrecht",
        "pl": "Przedłużenie tytułu pobytowego. Błąd = ryzyko dla prawa pobytu",
        "tr": "Oturma izni uzatma. Form hatası, Almanya'da kalma hakkınızı riske atar",
        "ar": "تمديد تصريح الإقامة. خطأ في الأوراق = خطر على حقك في البقاء",
    },
}

# "What you get" — same for all documents, per language.
_DOC_RESULT_LINE = {
    "ua": "Ви отримаєте заповнений приклад документа",
    "uk": "Ви отримаєте заповнений приклад документа",
    "en": "You will get a filled document example",
    "de": "Sie erhalten ein ausgefülltes Dokumentenbeispiel",
    "pl": "Otrzymasz wypełniony przykład dokumentu",
    "tr": "Doldurulmuş bir belge örneği alacaksınız",
    "ar": "ستحصل على مثال مملوء للمستند",
}


# ---------------------------------------------------------------------------
#  "Frequent mistakes" block — per-document, per-language.
#  Shown on preview-explanation and pre-payment screens.
# ---------------------------------------------------------------------------

_MISTAKES_HEADER = {
    "ua": "Часті причини відмови:",
    "uk": "Часті причини відмови:",
    "en": "Often rejected for:",
    "de": "Haeufig abgelehnt wegen:",
    "pl": "Częste przyczyny odrzucenia:",
    "tr": "Sık ret nedenleri:",
    "ar": "أسباب الرفض الشائعة:",
}

_DOC_COMMON_MISTAKES: dict = {
    "anmeldung": {
        "ua": [
            "Відсутня Wohnungsgeberbestätigung від орендодавця",
            "Реєстрація пізніше ніж 14 днів після переїзду",
            "Неповна або неправильна адреса",
        ],
        "en": [
            "Missing Wohnungsgeberbestätigung from landlord",
            "Registration later than 14 days after moving",
            "Incomplete or incorrect address",
        ],
        "de": [
            "Fehlende Wohnungsgeberbestätigung",
            "Anmeldung spaeter als 14 Tage nach Einzug",
            "Unvollstaendige oder falsche Adresse",
        ],
        "pl": [
            "Brak Wohnungsgeberbestätigung od wynajmującego",
            "Rejestracja później niż 14 dni od przeprowadzki",
            "Niepełny lub błędny adres",
        ],
        "tr": [
            "Ev sahibinden Wohnungsgeberbestätigung eksik",
            "Taşınmadan 14 gün sonra kayıt",
            "Eksik veya yanlış adres",
        ],
        "ar": [
            "عدم تقديم Wohnungsgeberbestätigung من المالك",
            "التسجيل بعد 14 يومًا من الانتقال",
            "عنوان غير كامل أو غير صحيح",
        ],
    },
    "abmeldung": {
        "ua": [
            "Не вказана дата виїзду",
            "Неповна попередня адреса",
            "Зняття з реєстрації після від'їзду без поштової адреси",
        ],
        "en": [
            "Missing move-out date",
            "Incomplete previous address",
            "Deregistering after leaving without a postal address",
        ],
        "de": [
            "Fehlendes Auszugsdatum",
            "Unvollstaendige bisherige Adresse",
            "Abmeldung nach Abreise ohne Postanschrift",
        ],
        "pl": [
            "Brak daty wyprowadzki",
            "Niepełny poprzedni adres",
            "Wyrejestrowanie po wyjeździe bez adresu pocztowego",
        ],
        "tr": [
            "Taşınma tarihi eksik",
            "Eksik önceki adres",
            "Posta adresi olmadan ayrıldıktan sonra kayıt silme",
        ],
        "ar": [
            "عدم تحديد تاريخ المغادرة",
            "عنوان سابق غير مكتمل",
            "إلغاء التسجيل بعد المغادرة بدون عنوان بريدي",
        ],
    },
    "ummeldung": {
        "ua": [
            "Відсутня нова Wohnungsgeberbestätigung",
            "Переоформлення пізніше ніж 14 днів",
            "Помилка в попередній адресі реєстрації",
        ],
        "en": [
            "Missing new Wohnungsgeberbestätigung",
            "Re-registration later than 14 days",
            "Error in previous registration address",
        ],
        "de": [
            "Fehlende neue Wohnungsgeberbestätigung",
            "Ummeldung spaeter als 14 Tage",
            "Fehler in der bisherigen Meldeadresse",
        ],
        "pl": [
            "Brak nowego Wohnungsgeberbestätigung",
            "Przerejestracja później niż 14 dni",
            "Błąd w poprzednim adresie rejestracji",
        ],
        "tr": [
            "Yeni Wohnungsgeberbestätigung eksik",
            "14 günden geç yeniden kayıt",
            "Önceki kayıt adresinde hata",
        ],
        "ar": [
            "عدم تقديم Wohnungsgeberbestätigung جديد",
            "إعادة التسجيل بعد 14 يومًا",
            "خطأ في عنوان التسجيل السابق",
        ],
    },
    "wohnungsgeberbestaetigung": {
        "ua": [
            "Відсутній підпис орендодавця",
            "Неповна адреса об'єкта",
            "Неправильна дата заселення",
        ],
        "en": [
            "Missing landlord signature",
            "Incomplete property address",
            "Incorrect move-in date",
        ],
        "de": [
            "Fehlende Unterschrift des Vermieters",
            "Unvollstaendige Objektadresse",
            "Falsches Einzugsdatum",
        ],
        "pl": [
            "Brak podpisu wynajmującego",
            "Niepełny adres nieruchomości",
            "Błędna data zameldowania",
        ],
        "tr": [
            "Ev sahibinin imzası eksik",
            "Eksik mülk adresi",
            "Yanlış taşınma tarihi",
        ],
        "ar": [
            "عدم وجود توقيع المالك",
            "عنوان العقار غير مكتمل",
            "تاريخ انتقال غير صحيح",
        ],
    },
    "kindergeld": {
        "ua": [
            "Відсутнє свідоцтво про народження дитини",
            "Неповні банківські реквізити (IBAN)",
            "Не вказаний Steuer-ID батька або дитини",
        ],
        "en": [
            "Missing child's birth certificate",
            "Incomplete bank details (IBAN)",
            "Missing Steuer-ID for parent or child",
        ],
        "de": [
            "Fehlende Geburtsurkunde des Kindes",
            "Unvollstaendige Bankverbindung (IBAN)",
            "Fehlende Steuer-ID des Elternteils oder Kindes",
        ],
        "pl": [
            "Brak aktu urodzenia dziecka",
            "Niepełne dane bankowe (IBAN)",
            "Brak Steuer-ID rodzica lub dziecka",
        ],
        "tr": [
            "Çocuğun doğum belgesi eksik",
            "Eksik banka bilgileri (IBAN)",
            "Ebeveyn veya çocuk için Steuer-ID eksik",
        ],
        "ar": [
            "عدم تقديم شهادة ميلاد الطفل",
            "بيانات مصرفية غير مكتملة (IBAN)",
            "عدم وجود Steuer-ID للوالد أو الطفل",
        ],
    },
    "buergergeld": {
        "ua": [
            "Відсутній договір оренди або підтвердження оплати",
            "Неповна декларація про доходи",
            "Не додані копії документів, що посвідчують особу",
        ],
        "en": [
            "Missing rental contract or proof of rent",
            "Incomplete income declaration",
            "Missing copies of ID documents",
        ],
        "de": [
            "Fehlender Mietvertrag oder Mietnachweis",
            "Unvollstaendige Einkommenserklaerung",
            "Fehlende Kopien der Ausweisdokumente",
        ],
        "pl": [
            "Brak umowy najmu lub potwierdzenia czynszu",
            "Niepełna deklaracja dochodów",
            "Brak kopii dokumentów tożsamości",
        ],
        "tr": [
            "Kira sözleşmesi veya kira kanıtı eksik",
            "Eksik gelir beyanı",
            "Kimlik belgesi kopyaları eksik",
        ],
        "ar": [
            "عدم تقديم عقد الإيجار أو إثبات الإيجار",
            "إقرار دخل غير مكتمل",
            "عدم تقديم نسخ من وثائق الهوية",
        ],
    },
}

# Generic fallback for documents without custom mistakes.
_GENERIC_MISTAKES = {
    "ua": [
        "Незаповнені або пропущені обов'язкові поля",
        "Помилки в особистих даних (ім'я, дата народження)",
        "Відсутній підпис там, де він потрібен",
    ],
    "en": [
        "Incomplete or missing required fields",
        "Errors in personal data (name, date of birth)",
        "Missing signature where required",
    ],
    "de": [
        "Unvollstaendige oder fehlende Pflichtfelder",
        "Fehler bei persoenlichen Daten (Name, Geburtsdatum)",
        "Fehlende Unterschrift",
    ],
    "pl": [
        "Niewypełnione lub brakujące wymagane pola",
        "Błędy w danych osobowych (imię, data urodzenia)",
        "Brak podpisu tam, gdzie jest wymagany",
    ],
    "tr": [
        "Eksik veya boş bırakılmış zorunlu alanlar",
        "Kişisel bilgilerde hatalar (isim, doğum tarihi)",
        "Gerekli yerlerde eksik imza",
    ],
    "ar": [
        "حقول مطلوبة غير مكتملة أو مفقودة",
        "أخطاء في البيانات الشخصية (الاسم، تاريخ الميلاد)",
        "توقيع مفقود حيث يكون مطلوبًا",
    ],
}


def _get_mistakes_block(doc_type: str, lang: str) -> str:
    """Build a short 'frequent mistakes' text block for the given document and language."""
    if lang == "uk":
        lang = "ua"
    doc_mistakes = _DOC_COMMON_MISTAKES.get(doc_type, {})
    items = doc_mistakes.get(lang, doc_mistakes.get("en", []))
    if not items:
        items = _GENERIC_MISTAKES.get(lang, _GENERIC_MISTAKES.get("en", []))
    if not items:
        return ""
    header = _MISTAKES_HEADER.get(lang, _MISTAKES_HEADER.get("en", ""))
    bullets = "\n".join(f"• {item}" for item in items)
    return f"{header}\n{bullets}"


# ---------------------------------------------------------------------------
#  "Why this check matters" — merged value block (difficulty + price reason).
#  Two non-overlapping bullets: what's at stake + what we verify.
#  Pre-payment only.
# ---------------------------------------------------------------------------

_DOC_CHECK_VALUE = {
    "anmeldung": {
        "ua": [
            "14-денний дедлайн — пізня реєстрація призводить до відмови",
            "Перевіряємо адресу, дати та формат до подачі",
        ],
        "en": [
            "14-day deadline — late registration leads to rejection",
            "We verify address, dates, and format before you submit",
        ],
        "de": [
            "14-Tage-Frist — verspaetete Anmeldung fuehrt zur Ablehnung",
            "Adresse, Daten und Format werden vorab geprueft",
        ],
        "pl": [
            "14-dniowy termin — spóźniona rejestracja oznacza odrzucenie",
            "Weryfikujemy adres, daty i format przed złożeniem",
        ],
        "tr": [
            "14 günlük süre — geç kayıt reddedilir",
            "Adres, tarih ve formatı göndermeden önce kontrol ederiz",
        ],
        "ar": [
            "مهلة 14 يومًا — التسجيل المتأخر يؤدي إلى الرفض",
            "نتحقق من العنوان والتواريخ والتنسيق قبل التقديم",
        ],
    },
    "ummeldung": {
        "ua": [
            "Потрібне нове підтвердження від орендодавця; суворий дедлайн",
            "Перевіряємо адреси та дати на відповідність вимогам",
        ],
        "en": [
            "New landlord confirmation required; strict deadline",
            "We verify addresses and dates against requirements",
        ],
        "de": [
            "Neue Wohnungsgeberbestätigung noetig; strenge Frist",
            "Adressen und Daten werden auf Anforderungen geprueft",
        ],
        "pl": [
            "Nowe potwierdzenie wynajmującego wymagane; ścisły termin",
            "Weryfikujemy adresy i daty pod kątem wymogów",
        ],
        "tr": [
            "Yeni ev sahibi onayı ve katı süre gerekli",
            "Adres ve tarihleri gereksinimlere göre kontrol ederiz",
        ],
        "ar": [
            "تأكيد جديد من المالك مطلوب؛ موعد نهائي صارم",
            "نتحقق من العناوين والتواريخ وفقًا للمتطلبات",
        ],
    },
    "abmeldung": {
        "ua": [
            "Точна дата виїзду і повна адреса — інакше відмова",
            "Перевіряємо повноту даних та формат перед подачею",
        ],
        "en": [
            "Exact move-out date and full address — otherwise rejected",
            "We check data completeness and format before submission",
        ],
        "de": [
            "Auszugsdatum und vollstaendige Adresse erforderlich",
            "Vollstaendigkeit und Format werden vorab geprueft",
        ],
        "pl": [
            "Dokładna data wyprowadzki i pełny adres — inaczej odrzucenie",
            "Sprawdzamy kompletność danych i format przed złożeniem",
        ],
        "tr": [
            "Kesin taşınma tarihi ve tam adres — aksi halde ret",
            "Veri bütünlüğü ve formatı göndermeden önce kontrol ederiz",
        ],
        "ar": [
            "تاريخ مغادرة دقيق وعنوان كامل — وإلا يُرفض",
            "نتحقق من اكتمال البيانات والتنسيق قبل التقديم",
        ],
    },
    "wohnungsgeberbestaetigung": {
        "ua": [
            "Кожне поле має збігатися з даними Bürgeramt — навіть дрібна помилка = відмова",
            "Звіряємо всі поля з офіційними вимогами",
        ],
        "en": [
            "Every field must match Buergeramt records — even a small error means rejection",
            "We verify all fields against official requirements",
        ],
        "de": [
            "Jedes Feld muss exakt mit den Buergeramt-Daten stimmen",
            "Alle Felder werden gegen offizielle Anforderungen geprueft",
        ],
        "pl": [
            "Każde pole musi pasować do danych Bürgeramt — nawet mały błąd = odrzucenie",
            "Weryfikujemy wszystkie pola pod kątem oficjalnych wymogów",
        ],
        "tr": [
            "Her alan Bürgeramt kayıtlarıyla eşleşmeli — küçük hata bile ret",
            "Tüm alanları resmi gereksinimlere göre kontrol ederiz",
        ],
        "ar": [
            "يجب تطابق كل حقل مع سجلات Bürgeramt — أي خطأ صغير يعني الرفض",
            "نتحقق من جميع الحقول وفقًا للمتطلبات الرسمية",
        ],
    },
    "kindergeld": {
        "ua": [
            "Дані з кількох джерел (Steuer-ID, свідоцтво, IBAN) мають точно збігатися",
            "Звіряємо все між собою — невідповідність блокує заявку",
        ],
        "en": [
            "Data from multiple sources (Steuer-ID, birth certificate, IBAN) must match exactly",
            "We cross-check everything — any mismatch blocks the application",
        ],
        "de": [
            "Daten aus mehreren Quellen (Steuer-ID, Geburtsurkunde, IBAN) muessen exakt stimmen",
            "Alles wird auf Uebereinstimmung geprueft",
        ],
        "pl": [
            "Dane z wielu źródeł (Steuer-ID, akt urodzenia, IBAN) muszą się dokładnie zgadzać",
            "Sprawdzamy zgodność wszystkich danych",
        ],
        "tr": [
            "Birden fazla kaynaktan veriler (Steuer-ID, doğum belgesi, IBAN) tam eşleşmeli",
            "Her şeyi çapraz kontrol ederiz — uyumsuzluk başvuruyu engeller",
        ],
        "ar": [
            "بيانات من مصادر متعددة (Steuer-ID، شهادة ميلاد، IBAN) يجب أن تتطابق",
            "نتحقق من تطابق كل شيء — أي اختلاف يوقف الطلب",
        ],
    },
    "buergergeld": {
        "ua": [
            "Багато обов'язкових додатків — пропуск одного блокує всю заявку",
            "Кожен додаток перевіряємо окремо на повноту",
        ],
        "en": [
            "Many required attachments — one missing blocks the entire application",
            "We verify each attachment separately for completeness",
        ],
        "de": [
            "Viele Pflichtanlagen — ein fehlendes blockiert den Antrag",
            "Jede Anlage wird einzeln auf Vollstaendigkeit geprueft",
        ],
        "pl": [
            "Wiele wymaganych załączników — brak jednego blokuje wniosek",
            "Każdy załącznik weryfikujemy osobno pod kątem kompletności",
        ],
        "tr": [
            "Çok sayıda zorunlu ek — biri eksikse başvuru durur",
            "Her eki eksiksizlik açısından ayrı ayrı kontrol ederiz",
        ],
        "ar": [
            "مرفقات كثيرة مطلوبة — نقص أي منها يوقف الطلب",
            "نتحقق من كل مرفق على حدة للتأكد من اكتماله",
        ],
    },
    "wohngeld": {
        "ua": [
            "Помилка в доході або оренді затримує всю заявку",
            "Перевіряємо розрахунки на точність перед подачею",
        ],
        "en": [
            "Income or rent errors delay the entire application",
            "We verify calculations for accuracy before submission",
        ],
        "de": [
            "Fehler bei Einkommen oder Miete verzoegern den Antrag",
            "Berechnungen werden vorab auf Genauigkeit geprueft",
        ],
        "pl": [
            "Błąd w dochodach lub czynszu opóźnia cały wniosek",
            "Weryfikujemy obliczenia przed złożeniem",
        ],
        "tr": [
            "Gelir veya kira hatası tüm başvuruyu geciktirir",
            "Hesaplamaları göndermeden önce doğruluk açısından kontrol ederiz",
        ],
        "ar": [
            "خطأ في الدخل أو الإيجار يؤخر الطلب بالكامل",
            "نتحقق من الحسابات قبل التقديم",
        ],
    },
}

_GENERIC_CHECK_VALUE = {
    "ua": [
        "Суворі вимоги до формату та повноти",
        "Перевіряємо всі поля перед подачею",
    ],
    "en": [
        "Strict formatting and completeness requirements",
        "We verify all fields before submission",
    ],
    "de": [
        "Strenge Anforderungen an Format und Vollstaendigkeit",
        "Alle Felder werden vorab geprueft",
    ],
    "pl": [
        "Surowe wymagania formatu i kompletności",
        "Weryfikujemy wszystkie pola przed złożeniem",
    ],
    "tr": [
        "Katı format ve eksiksizlik gereksinimleri",
        "Göndermeden önce tüm alanları kontrol ederiz",
    ],
    "ar": [
        "متطلبات صارمة للتنسيق والاكتمال",
        "نتحقق من جميع الحقول قبل التقديم",
    ],
}


def _get_check_value_block(doc_type: str, lang: str) -> str:
    """Return merged 'why this check matters' block, or empty string."""
    if lang == "uk":
        lang = "ua"
    doc_items = _DOC_CHECK_VALUE.get(doc_type, {})
    items = doc_items.get(lang, doc_items.get("en", []))
    if not items:
        items = _GENERIC_CHECK_VALUE.get(lang, _GENERIC_CHECK_VALUE.get("en", []))
    if not items:
        return ""
    _header = {
        "ua": "Що ми перевіряємо і чому це важливо:",
        "en": "Why this check matters:",
        "de": "Warum diese Pruefung wichtig ist:",
        "pl": "Dlaczego ta weryfikacja jest ważna:",
        "tr": "Bu kontrol neden önemli:",
        "ar": "لماذا هذا الفحص مهم:",
    }
    h = _header.get(lang, _header.get("en", ""))
    bullets = "\n".join(f"• {item}" for item in items)
    return f"{h}\n{bullets}"


def _get_doc_intro_message(doc_type: str, lang: str) -> str:
    """Pre-form intro screen: doc name, urgency hint, common mistakes (2), benefit, price+time."""
    if lang == "uk":
        lang = "ua"

    # --- price ---
    try:
        from bot_config.pricing import PDF_PRICES as _PDF_PRICES
        _price = _PDF_PRICES.get(doc_type)
        if _price is None:
            logger.error("PRICE_MISSING_CRITICAL intro screen: doc_type=%r", doc_type)
    except Exception as _e:
        logger.error("PRICE_LOOKUP_ERROR intro screen: doc_type=%r err=%s", doc_type, _e)
        _price = None

    # --- document name ---
    german = _DOC_GERMAN_NAMES.get(doc_type, doc_type)

    # --- urgency line (doc-specific, only where meaningful) ---
    _urgency = {
        "anmeldung": {
            "ua": "⚠️ Потрібно зробити протягом <b>14 днів</b> після переїзду",
            "en": "⚠️ Must be done within <b>14 days</b> after moving",
            "de": "⚠️ Muss innerhalb von <b>14 Tagen</b> nach dem Umzug erledigt werden",
            "pl": "⚠️ Należy złożyć w ciągu <b>14 dni</b> od przeprowadzki",
            "tr": "⚠️ Taşınmadan sonra <b>14 gün</b> içinde yapılmalıdır",
            "ar": "⚠️ يجب إتمامه خلال <b>14 يومًا</b> من الانتقال",
        },
        "ummeldung": {
            "ua": "⚠️ Потрібно зробити протягом <b>14 днів</b> після переїзду на нову адресу",
            "en": "⚠️ Must be done within <b>14 days</b> of moving to a new address",
            "de": "⚠️ Muss innerhalb von <b>14 Tagen</b> nach dem Umzug erledigt werden",
            "pl": "⚠️ Należy złożyć w ciągu <b>14 dni</b> od zmiany adresu",
            "tr": "⚠️ Yeni adrese taşındıktan sonra <b>14 gün</b> içinde yapılmalıdır",
            "ar": "⚠️ يجب إتمامه خلال <b>14 يومًا</b> من الانتقال إلى عنوان جديد",
        },
        "aufenthaltstitel": {
            "ua": "⚠️ Помилки можуть призвести до відмови",
            "en": "⚠️ Mistakes can lead to rejection",
            "de": "⚠️ Fehler können zur Ablehnung führen",
            "pl": "⚠️ Błędy mogą skutkować odmową",
            "tr": "⚠️ Hatalar redde yol açabilir",
            "ar": "⚠️ الأخطاء قد تؤدي إلى الرفض",
        },
        "kindergeld": {
            "ua": "⚠️ Подайте якнайшвидше — виплати не діють заднім числом більше 6 місяців",
            "en": "⚠️ Apply ASAP — benefits are not retroactive beyond 6 months",
            "de": "⚠️ Schnell beantragen — Leistungen werden max. 6 Monate rückwirkend gezahlt",
            "pl": "⚠️ Złóż jak najszybciej — świadczenia nie działają wstecz powyżej 6 miesięcy",
            "tr": "⚠️ En kısa sürede başvurun — ödemeler 6 aydan fazla geriye dönük geçerli değil",
            "ar": "⚠️ تقدم في أسرع وقت — المدفوعات لا تُطبَّق بأثر رجعي لأكثر من 6 أشهر",
        },
        "elterngeld": {
            "ua": "⚠️ Подайте протягом 3 місяців після народження — виплати не переносяться",
            "en": "⚠️ Apply within 3 months of birth — payments cannot be deferred",
            "de": "⚠️ Innerhalb von 3 Monaten nach Geburt beantragen — Monate verfallen sonst",
            "pl": "⚠️ Złóż w ciągu 3 miesięcy od urodzenia — miesiące przepadają",
            "tr": "⚠️ Doğumdan sonra 3 ay içinde başvurun — aylar ertelenemiyor",
            "ar": "⚠️ تقدم خلال 3 أشهر من الولادة — الأشهر لا يمكن تأجيلها",
        },
    }

    # --- mistakes block (2 bullets, doc-specific where different) ---
    _mistakes_map = {
        "wohnungsgeberbestaetigung": {
            "ua": "❗ Часто повертають через помилки:\n• пропущені поля\n• неправильні дані орендодавця",
            "en": "❗ Common mistakes:\n• missing required fields\n• incorrect landlord details",
            "de": "❗ Häufige Fehler:\n• fehlende Pflichtfelder\n• falsche Vermieterangaben",
            "pl": "❗ Częste błędy:\n• brakujące wymagane pola\n• nieprawidłowe dane wynajmującego",
            "tr": "❗ Sık yapılan hatalar:\n• eksik zorunlu alanlar\n• yanlış ev sahibi bilgileri",
            "ar": "❗ الأخطاء الشائعة:\n• حقول مطلوبة مفقودة\n• بيانات المالك غير صحيحة",
        },
        "meldebescheinigung": {
            "ua": "❗ Часто повертають через помилки:\n• пропущені поля\n• неправильні дані про житло",
            "en": "❗ Common mistakes:\n• missing required fields\n• incorrect housing details",
            "de": "❗ Häufige Fehler:\n• fehlende Pflichtfelder\n• falsche Wohnungsangaben",
            "pl": "❗ Częste błędy:\n• brakujące wymagane pola\n• nieprawidłowe dane mieszkania",
            "tr": "❗ Sık yapılan hatalar:\n• eksik zorunlu alanlar\n• yanlış konut bilgileri",
            "ar": "❗ الأخطاء الشائعة:\n• حقول مطلوبة مفقودة\n• بيانات السكن غير صحيحة",
        },
    }
    _mistakes_generic = {
        "ua": "❗ Часто відмовляють через помилки:\n• пропущені поля\n• неправильні дати або адреса",
        "en": "❗ Common mistakes:\n• missing required fields\n• wrong date or address format",
        "de": "❗ Häufige Fehler:\n• fehlende Pflichtfelder\n• falsches Datums- oder Adressformat",
        "pl": "❗ Częste błędy:\n• brakujące wymagane pola\n• nieprawidłowy format dat lub adresu",
        "tr": "❗ Sık yapılan hatalar:\n• eksik zorunlu alanlar\n• yanlış tarih veya adres formatı",
        "ar": "❗ الأخطاء الشائعة:\n• حقول مطلوبة مفقودة\n• تنسيق تاريخ أو عنوان غير صحيح",
    }
    mistakes_block = _mistakes_map.get(doc_type, _mistakes_generic)

    # --- benefit line (one line) ---
    _benefit = {
        "ua": "✅ Перевіряємо перед подачею, щоб не повернули",
        "en": "✅ We check before submission so it won't be rejected",
        "de": "✅ Wir prüfen vor Einreichung, damit es nicht zurückkommt",
        "pl": "✅ Sprawdzamy przed złożeniem, żeby nie zwrócili",
        "tr": "✅ İade edilmemesi için teslim öncesi kontrol ederiz",
        "ar": "✅ نتحقق قبل التقديم حتى لا يُرفض",
    }

    # --- time label ---
    _time = {
        "ua": "4 хвилини", "en": "4 minutes", "de": "4 Minuten",
        "pl": "4 minuty", "tr": "4 dakika", "ar": "4 دقائق",
    }

    price_line = (
        f"💶 <b>€{_price:.2f}</b> · ⏱ {_time.get(lang, '~4 minutes')}"
        if _price is not None else ""
    )

    parts = [f"📄 <b>{german}</b>"]

    urgency = _urgency.get(doc_type, {}).get(lang, "")
    if urgency:
        parts.append(urgency)

    parts.append(mistakes_block.get(lang, mistakes_block["en"]))
    parts.append(_benefit.get(lang, _benefit["en"]))
    if price_line:
        parts.append(price_line)

    return "\n\n".join(parts)


# Backward-compatible alias (edit flow, preview reopen, deeplink may reference old name)
_get_opening_form_message = _get_doc_intro_message


def _get_opening_form_edit_message(doc_type: str, lang: str) -> str:
    """Get localized 'opening form for editing' message. Fallback to 'en' if lang missing, NOT 'uk'."""
    texts = {
        "uk": f"✏️ Відкриваю анкету для редагування ({doc_type})...",
        "en": f"✏️ Opening form for editing ({doc_type})...",
        "de": f"✏️ Öffne Formular zum Bearbeiten ({doc_type})...",
        "pl": f"✏️ Otwieram formularz do edycji ({doc_type})...",
        "tr": f"✏️ Düzenleme için form açılıyor ({doc_type})...",
        "ar": f"✏️ فتح النموذج للتحرير ({doc_type})...",
    }
    # CRITICAL: Fallback to 'en', NOT 'uk'
    return texts.get(
        lang, texts.get("en", f"✏️ Opening form for editing ({doc_type})...")
    )


def _make_webapp_reply_kb(url: str, lang: str = "en") -> ReplyKeyboardMarkup:
    """
    DEPRECATED: This function is kept for backward compatibility but should not be used.
    Use _make_webapp_inline_kb() instead for clean inline buttons.
    """
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    button_text = _get_webapp_button_text(lang)
    kb.add(KeyboardButton(text=button_text, web_app=WebAppInfo(url=url)))
    return kb


def _make_webapp_inline_kb(url: str, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Create inline keyboard with WebApp button.
    This replaces the large persistent ReplyKeyboard button with a clean inline button.

    IMPORTANT: Using InlineKeyboard with WebAppInfo still ensures Telegram delivers data as
    Message(web_app_data) => aiogram message_handler(content_types=WEB_APP_DATA) will fire.

    Args:
        url: WebApp URL
        lang: User language code (defaults to 'en', NOT 'uk')

    Returns:
        InlineKeyboardMarkup with WebApp button
    """
    kb = InlineKeyboardMarkup(row_width=1)
    button_text = _get_webapp_inline_button_text(lang)
    kb.add(InlineKeyboardButton(text=button_text, web_app=WebAppInfo(url=url)))
    return kb


def _get_webapp_inline_button_text(lang: str) -> str:
    """Get localized inline WebApp button text. Fallback to 'en' if lang missing, NOT 'uk'."""
    texts = {
        "uk": "👉 Заповнити за 4 хвилини",
        "ua": "👉 Заповнити за 4 хвилини",
        "en": "👉 Fill in 4 minutes",
        "de": "👉 In 4 Minuten ausfüllen",
        "pl": "👉 Wypełnij w 4 minuty",
        "tr": "👉 4 dakikada doldur",
        "ar": "👉 أكمل في 4 دقائق",
    }
    # CRITICAL: Fallback to 'en', NOT 'uk'
    return texts.get(lang, texts.get("en", "👉 Fill in 4 minutes"))


def _get_doc_prices() -> dict:
    """Return {doc_type: price} mapping for all registered doc_types."""
    try:
        from bot_config.pricing import get_prices

        return get_prices()
    except Exception:
        pass
    try:
        from backend.settings import Settings

        pm = Settings().pricing
        from bot_config.menu_structure import CATEGORY_DOCS

        all_docs = [dt for docs in CATEGORY_DOCS.values() for dt in docs]
        return {dt: pm.get_price(dt) for dt in all_docs}
    except Exception:
        from bot_config.pricing import DEFAULT_PRICES

        return dict(DEFAULT_PRICES)


def _make_main_menu_kb(lang: str = "uk") -> InlineKeyboardMarkup:
    """Create main menu with 7 MVP document choices, each labelled with its price."""
    lang = _norm_lang(lang)

    _MVP_DOCS = [
        "anmeldung",
        "ummeldung",
        "wohnungsgeberbestaetigung",
        "wohngeld",
        "kindergeld",
        "buergergeld",
        "aufenthaltstitel",
    ]

    doc_labels = {
        "en": {
            "anmeldung": "📝 Anmeldung (Registration)",
            "ummeldung": "🔄 Ummeldung (Address change)",
            "wohnungsgeberbestaetigung": "📋 Wohnungsgeberbestätigung",
            "wohngeld": "🏠 Wohngeld (Housing benefit)",
            "kindergeld": "👶 Kindergeld (Child benefit)",
            "buergergeld": "💶 Bürgergeld (Financial aid)",
            "aufenthaltstitel": "🛂 Aufenthaltstitel (Residence permit)",
        },
        "de": {
            "anmeldung": "📝 Anmeldung",
            "ummeldung": "🔄 Ummeldung",
            "wohnungsgeberbestaetigung": "📋 Wohnungsgeberbestätigung",
            "wohngeld": "🏠 Wohngeld",
            "kindergeld": "👶 Kindergeld",
            "buergergeld": "💶 Bürgergeld",
            "aufenthaltstitel": "🛂 Aufenthaltstitel",
        },
        "uk": {
            "anmeldung": "📝 Anmeldung (Реєстрація)",
            "ummeldung": "🔄 Ummeldung (Зміна адреси)",
            "wohnungsgeberbestaetigung": "📋 Wohnungsgeberbestätigung",
            "wohngeld": "🏠 Wohngeld (Житлова допомога)",
            "kindergeld": "👶 Kindergeld (Допомога на дітей)",
            "buergergeld": "💶 Bürgergeld (Фінансова допомога)",
            "aufenthaltstitel": "🛂 Aufenthaltstitel (Дозвіл на проживання)",
        },
        "pl": {
            "anmeldung": "📝 Anmeldung (Rejestracja)",
            "ummeldung": "🔄 Ummeldung (Zmiana adresu)",
            "wohnungsgeberbestaetigung": "📋 Wohnungsgeberbestätigung",
            "wohngeld": "🏠 Wohngeld",
            "kindergeld": "👶 Kindergeld",
            "buergergeld": "💶 Bürgergeld",
            "aufenthaltstitel": "🛂 Aufenthaltstitel",
        },
        "tr": {
            "anmeldung": "📝 Anmeldung (Kayıt)",
            "ummeldung": "🔄 Ummeldung (Adres değişikliği)",
            "wohnungsgeberbestaetigung": "📋 Wohnungsgeberbestätigung",
            "wohngeld": "🏠 Wohngeld",
            "kindergeld": "👶 Kindergeld",
            "buergergeld": "💶 Bürgergeld",
            "aufenthaltstitel": "🛂 Aufenthaltstitel",
        },
        "ar": {
            "anmeldung": "📝 Anmeldung (التسجيل)",
            "ummeldung": "🔄 Ummeldung (تغيير العنوان)",
            "wohnungsgeberbestaetigung": "📋 Wohnungsgeberbestätigung",
            "wohngeld": "🏠 Wohngeld",
            "kindergeld": "👶 Kindergeld",
            "buergergeld": "💶 Bürgergeld",
            "aufenthaltstitel": "🛂 Aufenthaltstitel",
        },
    }

    labels = doc_labels.get(lang, doc_labels["en"])
    prices = _get_doc_prices()

    kb = InlineKeyboardMarkup(row_width=1)
    for dt in _MVP_DOCS:
        base_label = labels.get(dt, dt)
        price = prices.get(dt)
        # Append price tag so users can compare before clicking
        label_with_price = f"{base_label} — €{price:.2f}" if price else base_label
        kb.add(InlineKeyboardButton(text=label_with_price, callback_data=f"doc_{dt}"))

    return kb


def _make_back_inline_kb(lang: str = "uk") -> InlineKeyboardMarkup:
    """Create two nav buttons: ⬅️ Back → back_to_main_menu, 🏠 Main Menu → main_menu."""
    from handlers.nav import make_nav_kb
    return make_nav_kb(lang, back_cb="back_to_main_menu")


def _has_meaningful_user_data(answers: Dict[str, Any]) -> bool:
    """Check if answers dict contains meaningful user data (not just empty/authority fields)."""
    if not answers:
        return False

    # Filter out authority fields, bundesland, doc_type, lang, and internal fields
    # Same logic as in pdf_generator.py
    meaningful_fields = []
    for key, value in answers.items():
        if key.startswith("authority_") or key in (
            "bundesland",
            "doc_type",
            "lang",
            "user_lang",
            "created_at",
        ):
            continue
        value_str = str(value).strip() if value is not None else ""
        if value_str and value_str.lower() not in ("none", "null", "n/a", "na", ""):
            meaningful_fields.append(key)

    return len(meaningful_fields) > 0


# Один чіткий дисклеймер довіри (не на кожному екрані — лише на екрані оплати/превʼю)
TRUST_DISCLAIMER = {
    "uk": "Ми не є державним органом. Ми допомагаємо заповнити документи за зразком.",
    "en": "We are not a government authority. We help fill out documents by sample.",
    "de": "Wir sind keine Behörde. Wir helfen, Dokumente nach Vorlage auszufüllen.",
    "pl": "Nie jesteśmy organem państwowym. Pomagamy wypełniać dokumenty według wzoru.",
    "tr": "Devlet kurumu değiliz. Belgeleri örnekteki gibi doldurmanıza yardımcı oluyoruz.",
    "ar": "نحن لسنا جهة حكومية. نساعد في ملء المستندات حسب النموذج.",
}


def _get_value_message_texts(lang: str) -> Dict[str, str]:
    """
    Get localized core value message texts.
    Keys: headline, subtitle, before_payment, preview_append, pdf_footer, done
    """
    lang = _norm_lang(lang)

    texts = {
        "en": {
            "headline": "Fill in the application so it is accepted the first time",
            "subtitle": "The bot helps you correctly fill in all required fields.",
            "before_payment": (
                "This service helps you avoid mistakes and prepare the application correctly, "
                "so it is not returned by the authority."
            ),
            "preview_append": (
                "The purpose of this preview is to help you fill in the official form correctly, "
                "so your application can be accepted the first time."
            ),
            "pdf_footer": (
                "Prepared to help you correctly fill in the official application "
                "and avoid rejection due to missing or incorrect information."
            ),
            "done": (
                "Use this preview to transfer your answers into the official form. "
                "This helps your application be accepted the first time."
            ),
        },
        "de": {
            "headline": "Füllen Sie den Antrag aus, damit er beim ersten Mal angenommen wird",
            "subtitle": "Der Bot hilft Ihnen, alle erforderlichen Felder korrekt auszufüllen.",
            "before_payment": (
                "Dieser Service hilft Ihnen, Fehler zu vermeiden und den Antrag korrekt vorzubereiten, "
                "damit er nicht von der Behörde zurückgesandt wird."
            ),
            "preview_append": (
                "Der Zweck dieser Vorschau ist, Ihnen zu helfen, das offizielle Formular korrekt auszufüllen, "
                "damit Ihr Antrag beim ersten Mal angenommen werden kann."
            ),
            "pdf_footer": (
                "Vorbereitet, um Ihnen zu helfen, den offiziellen Antrag korrekt auszufüllen "
                "und eine Ablehnung aufgrund fehlender oder falscher Informationen zu vermeiden."
            ),
            "done": (
                "Verwenden Sie diese Vorschau, um Ihre Antworten in das offizielle Formular zu übertragen. "
                "Dies hilft Ihrem Antrag, beim ersten Mal angenommen zu werden."
            ),
        },
        "uk": {
            "headline": "Заповніть заяву так, щоб її прийняли з першого разу",
            "subtitle": "Бот допомагає правильно заповнити всі обов'язкові поля.",
            "before_payment": (
                "Цей сервіс допомагає уникнути помилок і правильно підготувати заяву, "
                "щоб установа не повернула її назад."
            ),
            "preview_append": (
                "Мета цього превʼю — допомогти правильно заповнити офіційну форму, "
                "щоб вашу заяву прийняли з першого разу."
            ),
            "pdf_footer": (
                "Підготовлено, щоб допомогти правильно заповнити офіційну заяву "
                "і уникнути відмови через відсутні або неправильні дані."
            ),
            "done": (
                "Використовуйте це превʼю, щоб перенести відповіді до офіційної форми. "
                "Це допоможе прийняти вашу заяву з першого разу."
            ),
        },
        "pl": {
            "headline": "Wypełnij wniosek tak, aby został przyjęty za pierwszym razem",
            "subtitle": "Bot pomaga poprawnie wypełnić wszystkie wymagane pola.",
            "before_payment": (
                "Ta usługa pomaga unikać błędów i prawidłowo przygotować wniosek, "
                "aby nie został odesłany przez urząd."
            ),
            "preview_append": (
                "Celem tego podglądu jest pomoc w prawidłowym wypełnieniu oficjalnego formularza, "
                "aby wniosek został przyjęty za pierwszym razem."
            ),
            "pdf_footer": (
                "Przygotowane, aby pomóc prawidłowo wypełnić oficjalny wniosek "
                "i uniknąć odrzucenia z powodu brakujących lub nieprawidłowych informacji."
            ),
            "done": (
                "Użyj tego podglądu, aby przenieść odpowiedzi do oficjalnego formularza. "
                "To pomoże zaakceptować wniosek za pierwszym razem."
            ),
        },
        "tr": {
            "headline": "Başvuruyu ilk seferde kabul edilecek şekilde doldurun",
            "subtitle": "Bot, tüm gerekli alanları doğru doldurmanıza yardımcı olur.",
            "before_payment": (
                "Bu hizmet, hataları önlemenize ve başvuruyu doğru hazırlamanıza yardımcı olur, "
                "böylece makam tarafından geri gönderilmez."
            ),
            "preview_append": (
                "Bu önizlemenin amacı, resmi formu doğru doldurmanıza yardımcı olmaktır, "
                "böylece başvurunuz ilk seferde kabul edilebilir."
            ),
            "pdf_footer": (
                "Resmi başvuruyu doğru doldurmak ve eksik veya yanlış bilgiler nedeniyle "
                "reddedilmekten kaçınmak için hazırlanmıştır."
            ),
            "done": (
                "Cevaplarınızı resmi forma aktarmak için bu önizlemeyi kullanın. "
                "Bu, başvurunuzun ilk seferde kabul edilmesine yardımcı olur."
            ),
        },
        "ar": {
            "headline": "املأ الطلب بحيث يتم قبوله من المرة الأولى",
            "subtitle": "يساعدك البوت على ملء جميع الحقول المطلوبة بشكل صحيح.",
            "before_payment": (
                "تساعدك هذه الخدمة على تجنب الأخطاء وإعداد الطلب بشكل صحيح، "
                "بحيث لا يتم إرجاعه من قبل الجهة الرسمية."
            ),
            "preview_append": (
                "الغرض من هذه المعاينة هو مساعدتك على ملء النموذج الرسمي بشكل صحيح، "
                "بحيث يمكن قبول طلبك من المرة الأولى."
            ),
            "pdf_footer": (
                "تم الإعداد لمساعدتك على ملء الطلب الرسمي بشكل صحيح "
                "وتجنب الرفض بسبب معلومات مفقودة أو غير صحيحة."
            ),
            "done": (
                "استخدم هذه المعاينة لنقل إجاباتك إلى النموذج الرسمي. "
                "يساعد هذا على قبول طلبك من المرة الأولى."
            ),
        },
    }
    return texts.get(lang, texts["en"])


def _get_preview_explanation_texts(lang: str) -> Dict[str, str]:
    """
    Get localized preview explanation texts.
    Returns dict with: title, text, bullets, warning, button, button_short, microtext, back
    """
    lang = _norm_lang(lang)

    texts = {
        "en": {
            "title": "What you'll get",
            "text": (
                "This is an example of a completed document — so you can see how the form should look.\n"
                "It will help you fill out all fields correctly without mistakes.\n\n"
                "German authorities only accept official forms.\n"
                "This preview shows exactly what information you need to enter into the official form."
            ),
            "bullets": (
                "• All required fields are filled\n"
                "• No missing or incorrect information\n"
                "• Clear overview of your answers\n"
                "• Much higher chance your application is accepted"
            ),
            "warning": (
                "⚠️ This PDF is not submitted to the authority.\n"
                "After viewing, you'll need to transfer the data to the official form\n"
                "(PDF or online form provided by your local authority)."
            ),
            "button": "Show document example (€3.49)",
            "button_short": "📄 Show example",
            "microtext": "Takes less than 1 minute",
            "back": "← Back",
            "home": "🏠 Main menu",
        },
        "de": {
            "title": "Was Sie erhalten",
            "text": (
                "Dies ist ein Beispiel für ein ausgefülltes Dokument — so sehen Sie, wie das Formular aussehen soll.\n"
                "Es hilft Ihnen, alle Felder korrekt ohne Fehler auszufüllen.\n\n"
                "Deutsche Behörden akzeptieren nur offizielle Formulare.\n"
                "Diese Vorschau zeigt genau, welche Informationen Sie in das offizielle Formular eintragen müssen."
            ),
            "bullets": (
                "• Alle Pflichtfelder sind ausgefüllt\n"
                "• Keine fehlenden oder falschen Angaben\n"
                "• Übersichtliche Zusammenfassung Ihrer Antworten\n"
                "• Deutlich höhere Chance, dass Ihr Antrag angenommen wird"
            ),
            "warning": (
                "⚠️ Dieses PDF wird nicht bei der Behörde eingereicht.\n"
                "Nach der Ansicht müssen Sie die Daten in das offizielle Formular\n"
                "(PDF oder Online-Formular Ihrer Behörde) übertragen."
            ),
            "button": "Dokumentbeispiel anzeigen (€3.49)",
            "button_short": "📄 Beispiel anzeigen",
            "microtext": "Dauert weniger als 1 Minute",
            "back": "← Zurück",
            "home": "🏠 Hauptmenü",
        },
        "uk": {
            "title": "Що ви отримаєте",
            "text": (
                "Це приклад заповненого документа — так ви побачите, як має виглядати форма.\n"
                "Він допоможе вам правильно заповнити всі поля без помилок.\n\n"
                "Німецькі установи приймають лише офіційні форми.\n"
                "Це превʼю показує, яку саме інформацію потрібно внести до офіційної анкети."
            ),
            "bullets": (
                "• Всі обов'язкові поля заповнені\n"
                "• Немає пропущених або неправильних даних\n"
                "• Зрозумілий огляд ваших відповідей\n"
                "• Набагато вищі шанси, що заяву приймуть"
            ),
            "warning": (
                "⚠️ Цей PDF не подається до установи.\n"
                "Після перегляду вам потрібно буде перенести дані в офіційну форму\n"
                "(PDF або онлайн-форму вашої установи)."
            ),
            "button": "Показати приклад документа (€3.49)",
            "button_short": "📄 Показати приклад",
            "microtext": "Займає менше 1 хвилини",
            "back": "← Назад",
            "home": "🏠 Головне меню",
        },
        "pl": {
            "title": "Co otrzymasz",
            "text": (
                "To przykład wypełnionego dokumentu — zobaczysz, jak powinien wyglądać formularz.\n"
                "Pomoże Ci poprawnie wypełnić wszystkie pola bez błędów.\n\n"
                "Niemieckie urzędy akceptują tylko oficjalne formularze.\n"
                "Ten podgląd pokazuje dokładnie, jakie informacje należy wpisać do oficjalnego formularza."
            ),
            "bullets": (
                "• Wszystkie wymagane pola są wypełnione\n"
                "• Brak brakujących lub nieprawidłowych danych\n"
                "• Czytelny podgląd wszystkich odpowiedzi\n"
                "• Znacznie większa szansa, że wniosek zostanie przyjęty"
            ),
            "warning": (
                "⚠️ Ten PDF nie jest składany w urzędzie.\n"
                "Po przejrzeniu będziesz musiał przenieść dane do oficjalnego formularza\n"
                "(PDF lub formularz online właściwego urzędu)."
            ),
            "button": "Pokaż przykład dokumentu (€3.49)",
            "button_short": "📄 Pokaż przykład",
            "microtext": "Zajmuje mniej niż 1 minutę",
            "back": "← Wstecz",
            "home": "🏠 Menu główne",
        },
        "tr": {
            "title": "Ne alacaksınız",
            "text": (
                "Bu, doldurulmuş bir belgenin örneğidir — formun nasıl görünmesi gerektiğini göreceksiniz.\n"
                "Tüm alanları hatasız doldurmanıza yardımcı olacaktır.\n\n"
                "Alman makamları yalnızca resmi formları kabul eder.\n"
                "Bu önizleme, resmi forma hangi bilgilerin girilmesi gerektiğini açıkça gösterir."
            ),
            "bullets": (
                "• Tüm zorunlu alanlar doldurulmuştur\n"
                "• Eksik veya hatalı bilgi yoktur\n"
                "• Yanıtlarınızın net bir özeti\n"
                "• Başvurunun kabul edilme ihtimali çok daha yüksektir"
            ),
            "warning": (
                "⚠️ Bu PDF kuruma gönderilmez.\n"
                "Görüntüledikten sonra bilgileri resmi forma\n"
                "(PDF veya kurumun çevrimiçi formu) aktarmanız gerekecektir."
            ),
            "button": "Belge örneğini göster (€3.49)",
            "button_short": "📄 Örnek göster",
            "microtext": "1 dakikadan az sürer",
            "back": "← Geri",
            "home": "🏠 Ana menü",
        },
        "ar": {
            "title": "ما ستحصل عليه",
            "text": (
                "هذا مثال على مستند مكتمل — سترى كيف يجب أن يبدو النموذج.\n"
                "سيساعدك على ملء جميع الحقول بشكل صحيح دون أخطاء.\n\n"
                "تقبل الجهات الألمانية فقط النماذج الرسمية.\n"
                "تُظهر هذه المعاينة بالضبط المعلومات التي يجب إدخالها في النموذج الرسمي."
            ),
            "bullets": (
                "• جميع الحقول الإلزامية مملوءة\n"
                "• بدون معلومات ناقصة أو خاطئة\n"
                "• عرض واضح لجميع إجاباتك\n"
                "• فرصة أعلى بكثير لقبول الطلب"
            ),
            "warning": (
                "⚠️ لا يتم تقديم هذا PDF إلى الجهة الرسمية.\n"
                "بعد المشاهدة، ستحتاج إلى نقل المعلومات إلى النموذج الرسمي\n"
                "(PDF أو النموذج الإلكتروني الخاص بالجهة)."
            ),
            "button": "عرض مثال المستند (€3.49)",
            "button_short": "📄 عرض المثال",
            "microtext": "يستغرق أقل من دقيقة واحدة",
            "back": "← رجوع",
            "home": "🏠 القائمة الرئيسية",
        },
    }
    return texts.get(lang, texts["en"])


def _get_about_project_text(lang: str) -> str:
    """Get multilingual 'About the project' text."""
    lang = _norm_lang(lang)

    error_messages = {
        "de": "ℹ️ <b>Informationen</b>\n\nInformationen sind in Ihrer Sprache noch nicht verfügbar.",
        "en": "ℹ️ <b>Information</b>\n\nInformation is not available in your language yet.",
        "uk": "ℹ️ <b>Інформація</b>\n\nІнформація ще не доступна вашою мовою.",
        "pl": "ℹ️ <b>Informacja</b>\n\nInformacja nie jest jeszcze dostępna w Twoim języku.",
        "tr": "ℹ️ <b>Bilgi</b>\n\nBilgi henüz dilinizde mevcut değil.",
        "ar": "ℹ️ <b>معلومات</b>\n\nالمعلومات غير متاحة بلغتك بعد.",
    }

    texts = {
        "de": (
            "ℹ️ <b>Über diesen Service</b>\n\n"
            "<b>Was ich mache</b>\n"
            "Ich helfe Ihnen, deutsche Dokumente korrekt auszufüllen. "
            "Ich biete keine Rechtsberatung — nur Hilfe mit Formularen.\n\n"
            "<b>Unterstützte Dokumente:</b>\n"
            "• Anmeldung (Wohnsitzanmeldung)\n"
            "• Abmeldung (Wohnsitzabmeldung)\n"
            "• Bürgergeld\n"
            "• Kindergeld\n"
            "• Wohngeld\n"
            "• Weitere Formulare\n\n"
            "<b>Wie es funktioniert:</b>\n"
            "1. Formular ausfüllen\n"
            "2. Bezahlen\n"
            "3. Fertiges Dokumentbeispiel erhalten\n\n"
            "💡 <i>Dieser Service wurde von Menschen erstellt, die selbst durch die deutsche Bürokratie gegangen sind.</i>\n\n"
            "<b>Zum Datenschutz:</b>\n"
            "Ihre Daten werden nur während der Vorbereitung gespeichert. Danach wird alles gelöscht."
        ),
        "en": (
            "ℹ️ <b>About this service</b>\n\n"
            "<b>What I do</b>\n"
            "I help you fill out German documents correctly. "
            "I don't provide legal advice — just help with forms.\n\n"
            "<b>Supported documents:</b>\n"
            "• Anmeldung (residence registration)\n"
            "• Abmeldung (residence deregistration)\n"
            "• Bürgergeld (citizen's allowance)\n"
            "• Kindergeld (child benefit)\n"
            "• Wohngeld (housing benefit)\n"
            "• Other forms\n\n"
            "<b>How it works:</b>\n"
            "1. Fill in the form\n"
            "2. Pay\n"
            "3. Get your ready document example\n\n"
            "💡 <i>This service was created by people who personally went through German bureaucracy.</i>\n\n"
            "<b>About privacy:</b>\n"
            "Your data is stored only while preparing your document. After that, everything is deleted."
        ),
        "uk": (
            "ℹ️ <b>Про цей сервіс</b>\n\n"
            "<b>Що я роблю?</b>\n"
            "Я допомагаю правильно заповнити німецькі документи. "
            "Не надаю юридичних консультацій — лише допомагаю з формами.\n\n"
            "<b>Які документи підтримуються:</b>\n"
            "• Anmeldung (реєстрація місця проживання)\n"
            "• Abmeldung (зняття з реєстрації)\n"
            "• Bürgergeld (допомога громадянам)\n"
            "• Kindergeld (допомога на дітей)\n"
            "• Wohngeld (допомога на житло)\n"
            "• Інші форми\n\n"
            "<b>Як це працює:</b>\n"
            "1. Заповніть форму\n"
            "2. Оплатіть\n"
            "3. Отримайте готовий приклад документа\n\n"
            "💡 <i>Цей сервіс створили люди, які самі пройшли через німецьку бюрократію.</i>\n\n"
            "<b>Про конфіденційність:</b>\n"
            "Ваші дані зберігаються лише під час підготовки документа. Після цього все видаляється."
        ),
    }
    return texts.get(lang, error_messages.get(lang, error_messages["uk"]))


async def handle_webapp_data(message: types.Message):
    """
    WebApp data handler - receives WEB_APP_DATA from Telegram WebApp.
    Flow: parse -> store _PENDING_PREVIEWS -> remove ReplyKeyboard -> one post-form message -> return.
    FIX: Use message.bot (aiogram 2) so handler works without context; send via bot.send_message().
    """
    logger.info(
        "WEB_APP_DATA received chat_id=%s", message.chat.id if message.chat else None
    )
    bot = getattr(message, "bot", None)
    if not bot:
        logger.error("handle_webapp_data: message.bot is None")
        return
    chat_id = message.chat.id
    user_id = _uid(message.from_user.id) if message.from_user else None
    logger.info("ENTER handle_webapp_data user_id=%s", user_id)
    raw = getattr(getattr(message, "web_app_data", None), "data", None) or ""
    _early_lang = _norm_lang(None, user_id)

    _ONBOARDING_MSG = {
        "uk": "⚠️ Будь ласка, спочатку завершіть реєстрацію через /start",
        "en": "⚠️ Please complete onboarding first via /start",
        "de": "⚠️ Bitte schließen Sie zuerst die Registrierung über /start ab",
        "pl": "⚠️ Proszę najpierw zakończyć rejestrację przez /start",
        "tr": "⚠️ Lütfen önce /start ile kaydı tamamlayın",
        "ar": "⚠️ يرجى إكمال التسجيل أولاً عبر /start",
    }
    _NO_DATA_MSG = {
        "uk": "❌ Дані не отримано. Спробуйте, будь ласка, ще раз.",
        "en": "❌ No data received. Please try again.",
        "de": "❌ Keine Daten erhalten. Bitte versuchen Sie es erneut.",
        "pl": "❌ Nie otrzymano danych. Proszę spróbować ponownie.",
        "tr": "❌ Veri alınamadı. Lütfen tekrar deneyin.",
        "ar": "❌ لم يتم استلام البيانات. يرجى المحاولة مرة أخرى.",
    }
    _PARSE_ERR_MSG = {
        "uk": "❌ Помилка обробки даних. Спробуйте, будь ласка, ще раз.",
        "en": "❌ Data processing error. Please try again.",
        "de": "❌ Fehler bei der Datenverarbeitung. Bitte versuchen Sie es erneut.",
        "pl": "❌ Błąd przetwarzania danych. Proszę spróbować ponownie.",
        "tr": "❌ Veri işleme hatası. Lütfen tekrar deneyin.",
        "ar": "❌ خطأ في معالجة البيانات. يرجى المحاولة مرة أخرى.",
    }

    if not _check_onboarding_complete(user_id):
        await bot.send_message(
            chat_id, _ONBOARDING_MSG.get(_early_lang, _ONBOARDING_MSG["en"])
        )
        return
    if not hasattr(message, "web_app_data") or not message.web_app_data:
        await bot.send_message(
            chat_id,
            _NO_DATA_MSG.get(_early_lang, _NO_DATA_MSG["en"]),
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    try:
        logger.info("handle_webapp_data parsing raw len=%s", len(raw))
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        await bot.send_message(
            chat_id,
            _PARSE_ERR_MSG.get(_early_lang, _PARSE_ERR_MSG["en"]),
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    answers: Dict[str, Any] = data.get("user_answers") or data.get("answers", {})
    doc_type: str = data.get("doc_type", "unknown")
    user_lang = _norm_lang(data.get("lang") or data.get("user_lang"), user_id)
    logger.info(
        "ANSWERS_RECEIVED: user_id=%s doc_type=%s answers_count=%s",
        user_id,
        doc_type,
        len(answers) if isinstance(answers, dict) else 0,
    )
    # Trace: log birth_place exactly as received from WebApp before any normalization
    logger.info(
        "WEBAPP_BIRTH_PLACE_TRACE: user_id=%s doc_type=%s birth_place=%r child_birth_place=%r",
        user_id,
        doc_type,
        (answers or {}).get("birth_place"),
        (answers or {}).get("child_birth_place"),
    )
    # Trace: log gender keys as received from WebApp — confirm presence/absence before any normalization
    logger.info(
        "WEBAPP_GENDER_TRACE: user_id=%s doc_type=%s gender=%r person2_gender=%r person1_gender=%r keys=%s",
        user_id,
        doc_type,
        (answers or {}).get("gender"),
        (answers or {}).get("person2_gender"),
        (answers or {}).get("person1_gender"),
        sorted((answers or {}).keys()),
    )
    if not doc_type or doc_type == "unknown":
        await bot.send_message(
            chat_id,
            _NO_DOC_SELECTED_TEXTS.get(user_lang, _NO_DOC_SELECTED_TEXTS["en"]),
            reply_markup=_make_main_menu_kb(user_lang),
        )
        return
    if not isinstance(answers, dict):
        answers = {}
    _PENDING_PREVIEWS[(user_id, doc_type)] = {
        "answers": answers.copy(),
        "doc_type": doc_type,
        "created_at": time.time(),
        "lang": user_lang,
        "user_lang": user_lang,
        "status": "ready",
    }
    _save_previews()
    # TEMP DEBUG: when saved to _PENDING_PREVIEWS
    logger.info(
        "ANSWERS_SAVED: user_id=%s doc_type=%s _PENDING_PREVIEWS_keys=%s",
        user_id,
        doc_type,
        len(answers),
    )
    # UX: Проміжний стан "Готуємо приклад…", потім DRAFT (preview PDF), потім меню оплати
    try:
        # Typing indicator — confirms form was received and work began
        try:
            await bot.send_chat_action(chat_id, "typing")
            import asyncio as _asyncio_wad
            await _asyncio_wad.sleep(0.5)
        except Exception:
            pass

        preparing_text = _get_preparing_document_text(user_lang)
        await bot.send_message(chat_id, preparing_text, parse_mode="HTML")
        logger.info(
            "handle_webapp_data sending DRAFT first user_id=%s doc_type=%s",
            user_id,
            doc_type,
        )
        await _generate_preview_and_send(message, answers, doc_type, None, user_lang)
        logger.info("POST_FORM_DRAFT_SENT user_id=%s doc_type=%s", user_id, doc_type)
    except Exception as e:
        logger.exception("handle_webapp_data draft failed user_id=%s: %s", user_id, e)
        try:
            post_form_text, menu_kb = _build_post_form_confirmation_menu(
                doc_type, user_lang
            )
            await bot.send_message(
                chat_id,
                post_form_text or _get_form_received_text(user_lang),
                reply_markup=menu_kb,
            )
        except Exception as e2:
            logger.exception(
                "POST_FORM_MENU_FALLBACK_FAILED user_id=%s error=%s", user_id, e2
            )
    return


async def _send_draft_then_menu_via_bot(
    bot, chat_id: int, user_id: int, doc_type: str, user_lang: str
) -> None:
    """
    Send "Preparing…" status, then DRAFT (preview PDF), then menu with Pay for full PDF.
    Used when form is submitted via HTTP (no message object). Full PDF only after payment.
    """
    uid = _uid(user_id)
    pending = _PENDING_PREVIEWS.get((uid, doc_type))
    if not pending or not pending.get("answers"):
        post_form_text, menu_kb = _build_post_form_confirmation_menu(
            doc_type, user_lang
        )
        await bot.send_message(
            chat_id,
            post_form_text or _get_form_received_text(user_lang),
            reply_markup=menu_kb,
        )
        return
    answers = pending.get("answers")
    authority_info = (
        pending.get("authority_info") if get_requires_bundesland(doc_type) else None
    )
    from backend.pdf_generator import _has_meaningful_user_data_for_preview

    if not _has_meaningful_user_data_for_preview(answers):
        post_form_text, menu_kb = _build_post_form_confirmation_menu(
            doc_type, user_lang
        )
        await bot.send_message(
            chat_id,
            post_form_text or _get_form_received_text(user_lang),
            reply_markup=menu_kb,
        )
        return
    _DRAFT_CAPTION_TEXTS = {
        "uk": (
            "📄 Прев'ю документа готове\n\n"
            "Це зразок для перевірки ваших даних перед оплатою.\n"
            "Перевірте:\n"
            "• ім'я та прізвище\n"
            "• адресу\n"
            "• дати\n"
            "• дані інших осіб\n\n"
            "⚠️ Це не офіційний документ — лише зразок для самоперевірки."
        ),
        "en": (
            "📄 Preview document is ready\n\n"
            "This is a sample to review your data before purchase.\n"
            "Please check:\n"
            "• first and last name\n"
            "• address\n"
            "• dates\n"
            "• other persons' data\n\n"
            "⚠️ This is NOT an official document — it is a sample for your review."
        ),
        "de": (
            "📄 Vorschau des Dokuments ist bereit\n\n"
            "Dies ist ein Muster zur Überprüfung Ihrer Daten vor dem Kauf.\n"
            "Bitte prüfen:\n"
            "• Vor- und Nachname\n"
            "• Adresse\n"
            "• Datumsangaben\n"
            "• Daten anderer Personen\n\n"
            "⚠️ Kein offizielles Dokument — nur ein Muster zur Selbstprüfung."
        ),
        "pl": (
            "📄 Podgląd dokumentu gotowy\n\n"
            "To wzór do sprawdzenia Twoich danych przed zakupem.\n"
            "Sprawdź:\n"
            "• imię i nazwisko\n"
            "• adres\n"
            "• daty\n"
            "• dane innych osób\n\n"
            "⚠️ To NIE jest oficjalny dokument — tylko wzór do samodzielnej weryfikacji."
        ),
        "tr": (
            "📄 Belge önizlemesi hazır\n\n"
            "Bu, satın almadan önce verilerinizi incelemeniz için bir örnektir.\n"
            "Lütfen kontrol edin:\n"
            "• adı ve soyadı\n"
            "• adresi\n"
            "• tarihleri\n"
            "• diğer kişilerin verileri\n\n"
            "⚠️ Bu resmi bir belge DEĞİLDİR — yalnızca kendi kontrolünüz için bir örnektir."
        ),
        "ar": (
            "📄 معاينة المستند جاهزة\n\n"
            "هذا نموذج لمراجعة بياناتك قبل الشراء.\n"
            "يرجى التحقق من:\n"
            "• الاسم الأول والأخير\n"
            "• العنوان\n"
            "• التواريخ\n"
            "• بيانات الأشخاص الآخرين\n\n"
            "⚠️ هذا ليس مستندًا رسميًا — مجرد نموذج للمراجعة الذاتية."
        ),
    }
    _draft_caption = _DRAFT_CAPTION_TEXTS.get(user_lang, _DRAFT_CAPTION_TEXTS["en"])
    _snippet_caption_http = {
        "uk": (
            "🔍 Ось як виглядатиме ваш документ\n\n"
            "Перевірте, що ім'я, прізвище та дата народження вказані правильно.\n\n"
            "💳 Повний документ буде готовий одразу після оплати.\n\n"
            "🔒 Якщо є помилка — виправимо безкоштовно"
        ),
        "en": (
            "🔍 This is how your document will look\n\n"
            "Please verify that your name and date of birth are correct.\n\n"
            "💳 The full document will be ready immediately after payment.\n\n"
            "🔒 If something is wrong — we fix it for free"
        ),
        "de": (
            "🔍 So sieht Ihr Dokument aus\n\n"
            "Bitte prüfen Sie, ob Name und Geburtsdatum korrekt sind.\n\n"
            "💳 Das vollständige Dokument steht sofort nach der Zahlung bereit.\n\n"
            "🔒 Bei Fehlern korrigieren wir kostenlos"
        ),
        "pl": (
            "🔍 Tak będzie wyglądał Twój dokument\n\n"
            "Sprawdź, czy imię, nazwisko i data urodzenia są poprawne.\n\n"
            "💳 Pełny dokument będzie gotowy natychmiast po płatności.\n\n"
            "🔒 Jeśli coś jest nie tak — poprawiamy bezpłatnie"
        ),
        "tr": (
            "🔍 Belgeniz böyle görünecek\n\n"
            "Lütfen adınızın ve doğum tarihinizin doğru olduğunu kontrol edin.\n\n"
            "💳 Tam belge ödemenin hemen ardından hazır olacak.\n\n"
            "🔒 Hata varsa ücretsiz düzeltiriz"
        ),
        "ar": (
            "🔍 هكذا سيبدو مستندك\n\n"
            "يرجى التحقق من أن اسمك وتاريخ ميلادك صحيحان.\n\n"
            "💳 سيكون المستند الكامل جاهزًا فور إتمام الدفع.\n\n"
            "🔒 إذا كان هناك خطأ — سنصلحه مجانًا"
        ),
    }.get(user_lang, "🔍 Document preview — verify your name and date of birth.")

    _, menu_kb = _build_post_form_confirmation_menu(doc_type, user_lang)

    # ── Try real-template snippet photo first ─────────────────────────────────
    _http_bundesland = (authority_info or {}).get("bundesland") if authority_info else None
    _snippet_sent_http = False
    try:
        from backend.pdf_preview import create_template_snippet_image
        from io import BytesIO as _BytesIO

        _png = create_template_snippet_image(
            doc_type=doc_type,
            user_data=answers,
            lang=user_lang or "de",
            bundesland=_http_bundesland,
        )
        if _png:
            await bot.send_photo(
                chat_id,
                _BytesIO(_png),
                caption=_snippet_caption_http,
                reply_markup=menu_kb,
            )
            _snippet_sent_http = True
            logger.info(
                "✅ HTTP snippet photo sent chat_id=%s doc_type=%s (%d B)",
                chat_id, doc_type, len(_png),
            )
    except Exception as _he:
        logger.debug("pdf_preview HTTP snippet failed (fallback): %s", _he)

    if _snippet_sent_http:
        return

    if doc_type == "kiz":
        await bot.send_message(
            chat_id,
            _PREVIEW_FAILED_TEXTS.get(user_lang, _PREVIEW_FAILED_TEXTS["en"]),
            reply_markup=menu_kb,
        )
        return

    # ── Fallback: unofficial review-sheet PDF ─────────────────────────────────
    preview_path = None
    processed_path = None
    try:
        preview_path = create_preview(
            user_id=user_id,
            user_data=answers,
            doc_type=doc_type,
            authority_info=authority_info,
            user_lang=user_lang,
        )
        if not preview_path or not os.path.exists(preview_path):
            raise RuntimeError("create_preview failed")
        try:
            processed_path = _make_onepage_watermarked_preview(preview_path)
        except Exception:
            pass
        send_path = processed_path or preview_path
        # ONE message: document + caption + inline keyboard
        await bot.send_document(
            chat_id, InputFile(send_path), caption=_draft_caption, reply_markup=menu_kb
        )
    except Exception as e:
        logger.warning("_send_draft_then_menu_via_bot preview failed: %s", e)
        post_form_text, menu_kb = _build_post_form_confirmation_menu(
            doc_type, user_lang
        )
        await bot.send_message(
            chat_id,
            post_form_text or _get_form_received_text(user_lang),
            reply_markup=menu_kb,
        )
    finally:
        for path in (processed_path, preview_path):
            if path and path != preview_path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if preview_path and os.path.exists(preview_path):
            try:
                os.remove(preview_path)
            except Exception:
                pass


async def send_post_form_menu_via_http(
    bot, chat_id: int, doc_type: str, user_lang: str, answers: dict
) -> bool:
    """
    Відправка пост-форми меню з HTTP /webapp-submit (обхід WEB_APP_DATA).
    CRITICAL: First send DRAFT (preview PDF), then menu with Pay — never full PDF without payment.
    """
    user_id = chat_id
    if not isinstance(answers, dict):
        answers = {}
    user_lang = _norm_lang(user_lang, user_id)
    _PENDING_PREVIEWS[(user_id, doc_type)] = {
        "answers": answers.copy(),
        "doc_type": doc_type,
        "created_at": time.time(),
        "lang": user_lang,
        "user_lang": user_lang,
        "status": "ready",
    }
    _save_previews()
    try:
        await _send_draft_then_menu_via_bot(bot, chat_id, user_id, doc_type, user_lang)
        logger.info(
            "POST_FORM_DRAFT_SENT via HTTP chat_id=%s doc_type=%s", chat_id, doc_type
        )
        return True
    except Exception as e:
        logger.exception(
            "send_post_form_menu_via_http failed chat_id=%s: %s", chat_id, e
        )
        try:
            post_form_text, menu_kb = _build_post_form_confirmation_menu(
                doc_type, user_lang
            )
            await bot.send_message(
                chat_id,
                post_form_text or _get_form_received_text(user_lang),
                reply_markup=menu_kb,
            )
            return True
        except Exception as e2:
            logger.exception(
                "POST_FORM_MENU_FALLBACK_FAILED chat_id=%s: %s", chat_id, e2
            )
            return False


async def cmd_testpdf(message: types.Message):
    """Test command for PDF generation."""
    user_id = _uid(message.from_user.id)

    test_data = {
        "firstname": "Test",
        "lastname": "User",
        "plz": "10115",
        "city": "Berlin",
    }

    doc_type = "anmeldung"

    try:
        preview_path = create_preview(
            user_id=user_id,
            user_data=test_data,
            doc_type=doc_type,
            authority_info=None,
            user_lang="uk",
        )

        if not preview_path or not os.path.exists(preview_path):
            raise RuntimeError(f"Preview not created: {preview_path}")

        await message.answer_document(
            InputFile(preview_path), caption=f"🧪 TEST PREVIEW {doc_type.upper()}"
        )
    except Exception as e:
        logger.error(f"❌ /testpdf failed: {e}", exc_info=True)
        await message.answer(
            "❌ /testpdf error. Check console."
        )  # admin-only, EN is fine


async def process_doc_choice(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle document choice callback (doc_<type>)."""

    # 1) Ack callback IMMEDIATELY (avoid Telegram "loading" spinner / frozen button)
    await callback_query.answer()

    try:
        # 2) ENTER log
        logger.warning(
            "DOC_CHOICE_ENTER user_id=%s data=%s",
            callback_query.from_user.id if callback_query.from_user else None,
            callback_query.data,
        )

        # 2.1) Defensive: clear leftover FSM state from other flows (e.g. Termin payment)
        try:
            current = await state.get_state()
            if current and current.startswith("TerminStates:"):
                await state.finish()
        except Exception:
            pass

        # 3) Basic safety
        if not callback_query.from_user or not callback_query.data:
            logger.error("DOC_CHOICE_INVALID callback_query missing from_user/data")
            return

        user_id = _uid(callback_query.from_user.id)

        logger.info(
            "process_doc_choice called user_id=%s callback_data=%s",
            user_id,
            callback_query.data,
        )

        # 4) Onboarding gate
        if not _check_onboarding_complete(user_id):
            _olang = _norm_lang(None, user_id)
            await callback_query.message.answer(
                _ONBOARDING_INCOMPLETE_TEXTS.get(
                    _olang, _ONBOARDING_INCOMPLETE_TEXTS["en"]
                )
            )
            return

        # 5) Parse doc_type + lang
        doc_type = callback_query.data.replace("doc_", "")
        user_lang = _norm_lang(None, user_id)

        logger.warning(
            "DOC_CHOICE_SHOW_INTRO user_id=%s doc_type=%s",
            callback_query.from_user.id if callback_query.from_user else None,
            doc_type,
        )

        # 6) Show pre-form intro screen (price + validation info)
        # Intro text + flow description combined (removes the need for a separate step message)
        intro_text = _get_doc_intro_message(doc_type, user_lang)
        flow_line = _get_flow_before_form_text(user_lang)
        combined_text = f"{intro_text}\n\n{flow_line}"

        # Build WebApp URL directly — clicking the button opens the WebApp immediately
        chat_id = (
            callback_query.message.chat.id
            if callback_query.message and callback_query.message.chat
            else None
        )
        webapp_url_direct = _webapp_url(
            doc_type, user_lang, saved_answers=None, chat_id=chat_id
        )

        kb_intro = InlineKeyboardMarkup(row_width=1)
        if webapp_url_direct:
            kb_intro.add(
                InlineKeyboardButton(
                    text=_get_webapp_inline_button_text(user_lang),
                    web_app=WebAppInfo(url=webapp_url_direct),
                )
            )
            logger.info(
                "WEBAPP_BTN_TYPE | user_id=%s doc=%s btn=web_app url=%s",
                user_id, doc_type, webapp_url_direct,
            )
        else:
            # Fallback: two-step if WebApp URL unavailable (WEBAPP_BASE_URL not configured)
            _start_btn = {
                "ua": "📝 Почати заповнення",
                "uk": "📝 Почати заповнення",
                "en": "📝 Start filling form",
                "de": "📝 Formular ausfüllen",
                "pl": "📝 Rozpocznij wypełnianie",
                "tr": "📝 Formu doldurmaya başla",
                "ar": "📝 ابدأ ملء النموذج",
            }
            kb_intro.add(
                InlineKeyboardButton(
                    text=_start_btn.get(user_lang, _start_btn["en"]),
                    callback_data=f"start_form_{doc_type}",
                )
            )
            logger.warning(
                "WEBAPP_BTN_TYPE | user_id=%s doc=%s btn=callback_fallback "
                "(WEBAPP_BASE_URL not configured)",
                user_id, doc_type,
            )
        from handlers.nav import nav_back_text, nav_home_text
        kb_intro.add(InlineKeyboardButton(text=nav_back_text(user_lang), callback_data="back_to_main_menu"))
        kb_intro.add(InlineKeyboardButton(text=nav_home_text(user_lang), callback_data="main_menu"))

        # Show pre-form intro (price, validation info, CTA to open the form).
        # The real preview with user's own data is shown AFTER form submission.
        await callback_query.message.answer(
            combined_text, parse_mode="HTML", reply_markup=kb_intro
        )

        # FUNNEL POINT 1: confirm intro message was sent with WebApp button
        logger.info(
            "FUNNEL | step=webapp_intro_sent user_id=%s doc=%s lang=%s",
            user_id,
            doc_type,
            user_lang,
        )

    except Exception as e:
        logger.exception(f"process_doc_choice crashed: {e}")
        try:
            _err_texts = {
                "uk": "❌ Виникла помилка. Спробуйте ще раз.",
                "ua": "❌ Виникла помилка. Спробуйте ще раз.",
                "en": "❌ An error occurred. Please try again.",
                "de": "❌ Ein Fehler ist aufgetreten. Bitte versuchen Sie es erneut.",
                "pl": "❌ Wystąpił błąd. Spróbuj ponownie.",
                "tr": "❌ Bir hata oluştu. Lütfen tekrar deneyin.",
                "ar": "❌ حدث خطأ. يرجى المحاولة مرة أخرى.",
            }
            _err_lang = _norm_lang(None, callback_query.from_user.id if callback_query.from_user else None)
            await callback_query.answer(
                _err_texts.get(_err_lang, _err_texts["en"]),
                show_alert=True,
            )
        except Exception:
            pass


async def handle_start_form(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle start_form_{doc_type} callback — open WebApp form after user saw the intro screen."""
    await callback_query.answer()
    try:
        if not callback_query.from_user or not callback_query.data:
            return

        user_id = _uid(callback_query.from_user.id)
        doc_type = callback_query.data.replace("start_form_", "")
        user_lang = _norm_lang(None, user_id)

        chat_id = (
            callback_query.message.chat.id
            if callback_query.message and callback_query.message.chat
            else None
        )
        url = _webapp_url(doc_type, user_lang, saved_answers=None, chat_id=chat_id)

        logger.info(
            "START_FORM_OPEN_WEBAPP doc_type=%s url=%s user_id=%s",
            doc_type,
            url,
            user_id,
        )

        if not url:
            logger.error(
                "WebApp URL is empty for user_id=%s doc_type=%s", user_id, doc_type
            )
            await callback_query.message.answer(
                _WEBAPP_URL_MISSING_TEXTS.get(
                    user_lang, _WEBAPP_URL_MISSING_TEXTS["en"]
                )
            )
            return

        kb_webapp = _make_webapp_inline_kb(url, user_lang)
        from handlers.nav import nav_back_text, nav_home_text
        kb_webapp.add(InlineKeyboardButton(text=nav_back_text(user_lang), callback_data="back_to_main_menu"))
        kb_webapp.add(InlineKeyboardButton(text=nav_home_text(user_lang), callback_data="main_menu"))

        # Open WebApp directly — no intermediate "Далі: анкета → …" step message
        try:
            await callback_query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback_query.message.answer(
            _get_flow_before_form_text(user_lang),
            parse_mode="HTML",
            reply_markup=kb_webapp,
        )
    except Exception as e:
        logger.exception(f"handle_start_form crashed: {e}")


async def _generate_preview_and_send(
    message: types.Message,
    answers: Dict[str, Any],
    doc_type: str,
    authority_info: Optional[Dict[str, Any]],
    user_lang: Optional[str] = None,
) -> None:
    """
    Helper to generate preview + send to chat with proper logging and caption.

    CRITICAL: Preview PDF MUST contain user-entered data.
    If no meaningful data exists, preview generation is blocked and an error message is shown.
    """
    # CRITICAL FIX: Ensure user_id is int (not str) for _PENDING_PREVIEWS dict key
    user_id = _uid(message.from_user.id)
    user_lang = _norm_lang(user_lang, user_id)

    # CRITICAL FIX: Read answers ONLY from _PENDING_PREVIEWS[(user_id, doc_type)]["answers"]
    # DO NOT use passed answers parameter - always read from _PENDING_PREVIEWS
    uid = _uid(user_id)
    pending = _PENDING_PREVIEWS.get((uid, doc_type))
    if pending and pending.get("answers"):
        answers = pending.get("answers")
        doc_type = pending.get("doc_type", doc_type)
        authority_info = (
            pending.get("authority_info", authority_info)
            if get_requires_bundesland(doc_type)
            else None
        )
        logger.debug(
            "Using answers from _PENDING_PREVIEWS[(%s, %s)]: %s fields",
            uid,
            doc_type,
            len(answers),
        )
    else:
        logger.warning(
            "No data in _PENDING_PREVIEWS[(%s, %s)], using passed answers parameter",
            uid,
            doc_type,
        )

    # CRITICAL: Log answers before passing to PDF generator
    logger.info(
        f"▶️ Starting preview generation: user={user_id} doc_type={doc_type} lang={user_lang} use_authority={bool(authority_info)}"
    )
    logger.info(f"📋 Preview answers count: {len(answers) if answers else 0}")
    if answers:
        logger.info(
            f"📋 Preview answers keys: {list(answers.keys())[:10]}..."
        )  # First 10 keys
    else:
        logger.warning(
            "⚠️ Preview answers is EMPTY - preview PDF will have no user data!"
        )

    # CRITICAL VALIDATION: Check if meaningful data exists before generating preview
    from backend.pdf_generator import _has_meaningful_user_data_for_preview

    if not _has_meaningful_user_data_for_preview(answers):
        error_texts = {
            "en": "❌ <b>Cannot generate preview</b>\n\nNo user data found. Please fill in the form and try again.",
            "de": "❌ <b>Vorschau kann nicht erstellt werden</b>\n\nKeine Benutzerdaten gefunden. Bitte füllen Sie das Formular aus und versuchen Sie es erneut.",
            "uk": "❌ <b>Неможливо створити превʼю</b>\n\nДані користувача не знайдено. Будь ласка, заповніть форму та спробуйте ще раз.",
            "pl": "❌ <b>Nie można wygenerować podglądu</b>\n\nNie znaleziono danych użytkownika. Proszę wypełnić formularz i spróbować ponownie.",
            "tr": "❌ <b>Önizleme oluşturulamıyor</b>\n\nKullanıcı verisi bulunamadı. Lütfen formu doldurun ve tekrar deneyin.",
            "ar": "❌ <b>لا يمكن إنشاء المعاينة</b>\n\nلم يتم العثور على بيانات المستخدم. يرجى ملء النموذج والمحاولة مرة أخرى.",
        }
        error_text = error_texts.get(user_lang, error_texts["uk"])
        await message.answer(
            error_text, parse_mode="HTML", reply_markup=_make_back_inline_kb(user_lang)
        )
        logger.error(
            f"❌ Preview generation blocked for user {user_id}: No meaningful data"
        )
        return

    # VALIDATION GATE: Run form validation BEFORE generating preview PDF
    # Critical errors → block preview + show localized error message
    # Warnings → allow preview but show notice after PDF
    _preview_warnings = []
    if (doc_type or "").strip().lower() == "anmeldung":
        try:
            from backend.form_validation import (
                validate_anmeldung_form,
                get_validation_errors_localized,
            )

            _pv_valid, _pv_errors, _pv_warns = validate_anmeldung_form(
                answers, user_lang
            )
            if not _pv_valid and _pv_errors:
                localized_errs = get_validation_errors_localized(_pv_errors, user_lang)
                err_lines = [
                    e.get("message", e.get("message_key", "")) for e in localized_errs
                ]
                _joined = "\n• ".join(err_lines)
                _PREVIEW_BLOCK_MSG = {
                    "uk": "❌ <b>Неможливо створити превʼю</b>\n\nВиправте помилки у формі:\n• "
                    + _joined,
                    "en": "❌ <b>Cannot generate preview</b>\n\nPlease fix the following errors:\n• "
                    + _joined,
                    "de": "❌ <b>Vorschau nicht möglich</b>\n\nBitte korrigieren Sie folgende Fehler:\n• "
                    + _joined,
                    "pl": "❌ <b>Nie można wygenerować podglądu</b>\n\nPopraw błędy:\n• "
                    + _joined,
                    "tr": "❌ <b>Önizleme oluşturulamıyor</b>\n\nHataları düzeltin:\n• "
                    + _joined,
                    "ar": "❌ <b>لا يمكن إنشاء المعاينة</b>\n\nيرجى تصحيح الأخطاء:\n• "
                    + _joined,
                }
                msg = _PREVIEW_BLOCK_MSG.get(
                    user_lang, _PREVIEW_BLOCK_MSG.get("en", "")
                )
                await message.answer(
                    msg, parse_mode="HTML", reply_markup=_make_back_inline_kb(user_lang)
                )
                logger.warning(
                    f"❌ Preview blocked for user {user_id}: {len(_pv_errors)} validation errors"
                )
                return
            if _pv_warns:
                _preview_warnings = get_validation_errors_localized(
                    _pv_warns, user_lang
                )
        except Exception as e:
            logger.warning("Pre-preview validation failed (non-blocking): %s", e)

    # Caption shown when the snippet is a REAL template image (premium UX)
    # Snippet caption — shown with real template PNG preview (best case)
    _SNIPPET_CAPTION_TEXTS = {
        "uk": (
            "🔍 <b>Ось ваш документ — перевірте дані</b>\n\n"
            "✅ Ім'я, прізвище та дата народження на місці?\n\n"
            "📄 Це приклад заповнення — фінальний PDF буде повністю сформований після оплати\n\n"
            "🔒 Якщо є помилка — виправимо безкоштовно"
        ),
        "en": (
            "🔍 <b>Here is your document — check the details</b>\n\n"
            "✅ Is your name and date of birth correct?\n\n"
            "📄 This is a fill preview — the final PDF will be fully generated after payment\n\n"
            "🔒 If something is wrong — we fix it for free"
        ),
        "de": (
            "🔍 <b>Ihr Dokument — bitte Daten prüfen</b>\n\n"
            "✅ Name und Geburtsdatum korrekt?\n\n"
            "📄 Dies ist eine Vorschau — das finale PDF wird nach der Zahlung vollständig erstellt\n\n"
            "🔒 Bei Fehlern korrigieren wir kostenlos"
        ),
        "pl": (
            "🔍 <b>Oto Twój dokument — sprawdź dane</b>\n\n"
            "✅ Imię, nazwisko i data urodzenia są poprawne?\n\n"
            "📄 To jest podgląd — finalny PDF zostanie w pełni wygenerowany po płatności\n\n"
            "🔒 Jeśli coś jest nie tak — poprawimy za darmo"
        ),
        "tr": (
            "🔍 <b>İşte belgeniz — verileri kontrol edin</b>\n\n"
            "✅ Adınız ve doğum tarihiniz doğru mu?\n\n"
            "📄 Bu bir önizlemedir — nihai PDF ödeme sonrasında tam olarak oluşturulacak\n\n"
            "🔒 Hata varsa — ücretsiz düzeltiriz"
        ),
        "ar": (
            "🔍 <b>ها هو مستندك — تحقق من البيانات</b>\n\n"
            "✅ هل اسمك وتاريخ ميلادك صحيحان؟\n\n"
            "📄 هذا مثال للتعبئة — سيتم إنشاء ملف PDF النهائي بالكامل بعد الدفع\n\n"
            "🔒 إذا كان هناك خطأ — نصلحه مجاناً"
        ),
    }
    # Fallback caption — shown with plain data-review PDF when snippet unavailable
    _PREVIEW_CAPTION_TEXTS = {
        "uk": (
            "📄 <b>Документ готовий — перевірте перед оплатою</b>\n\n"
            "Перевірте:\n"
            "• ім'я та прізвище\n"
            "• адресу\n"
            "• дати\n"
            "• дані інших осіб\n\n"
            "📄 Це приклад заповнення — фінальний PDF буде повністю сформований після оплати\n\n"
            "🔒 Якщо є помилка — виправимо безкоштовно"
        ),
        "en": (
            "📄 <b>Document ready — review before payment</b>\n\n"
            "Please check:\n"
            "• first and last name\n"
            "• address\n"
            "• dates\n"
            "• other persons' data\n\n"
            "📄 This is a fill preview — the final PDF will be fully generated after payment\n\n"
            "🔒 If something is wrong — we fix it for free"
        ),
        "de": (
            "📄 <b>Dokument bereit — bitte vor der Zahlung prüfen</b>\n\n"
            "Bitte prüfen:\n"
            "• Vor- und Nachname\n"
            "• Adresse\n"
            "• Datumsangaben\n"
            "• Daten anderer Personen\n\n"
            "📄 Dies ist eine Vorschau — das finale PDF wird nach der Zahlung vollständig erstellt\n\n"
            "🔒 Bei Fehlern korrigieren wir kostenlos"
        ),
        "pl": (
            "📄 <b>Dokument gotowy — sprawdź przed płatnością</b>\n\n"
            "Sprawdź:\n"
            "• imię i nazwisko\n"
            "• adres\n"
            "• daty\n"
            "• dane innych osób\n\n"
            "📄 To jest podgląd — finalny PDF zostanie w pełni wygenerowany po płatności\n\n"
            "🔒 Jeśli coś jest nie tak — poprawimy za darmo"
        ),
        "tr": (
            "📄 <b>Belge hazır — ödeme öncesi kontrol edin</b>\n\n"
            "Lütfen kontrol edin:\n"
            "• adı ve soyadı\n"
            "• adresi\n"
            "• tarihleri\n"
            "• diğer kişilerin verileri\n\n"
            "📄 Bu bir önizlemedir — nihai PDF ödeme sonrasında tam olarak oluşturulacak\n\n"
            "🔒 Hata varsa — ücretsiz düzeltiriz"
        ),
        "ar": (
            "📄 <b>المستند جاهز — راجع قبل الدفع</b>\n\n"
            "يرجى التحقق من:\n"
            "• الاسم الأول والأخير\n"
            "• العنوان\n"
            "• التواريخ\n"
            "• بيانات الأشخاص الآخرين\n\n"
            "📄 هذا مثال للتعبئة — سيتم إنشاء ملف PDF النهائي بالكامل بعد الدفع\n\n"
            "🔒 إذا كان هناك خطأ — نصلحه مجاناً"
        ),
    }
    _preview_caption = _PREVIEW_CAPTION_TEXTS.get(
        user_lang, _PREVIEW_CAPTION_TEXTS["en"]
    )

    # ── Resolve document price for keyboard labels ───────────────────────────
    _doc_price: float = 0.0
    try:
        _prices_map = _get_doc_prices()
        _doc_price = float(_prices_map.get(doc_type, 0) or 0)
    except Exception:
        pass

    # Bundle price: doc + Termin monitoring with ~15% saving vs buying separately.
    # Termin standalone = €4.99; bundle saves the user ~€1–2.
    _TERMIN_STANDALONE = 4.99
    _bundle_price = round(_doc_price + _TERMIN_STANDALONE * 0.75, 2) if _doc_price else 0.0

    # Build inline keyboard before the send so it can be attached directly to the document
    _button_final_texts = {
        "en": f"💳 Get the filled document — ready to submit  €{_doc_price:.2f}" if _doc_price else "💳 Get the filled document — ready to submit",
        "de": f"💳 Ausgefülltes Dokument erhalten — einreichbereit  €{_doc_price:.2f}" if _doc_price else "💳 Ausgefülltes Dokument erhalten — einreichbereit",
        "uk": f"💳 Отримати документ — готовий до подачі  €{_doc_price:.2f}" if _doc_price else "💳 Отримати документ — готовий до подачі",
        "ua": f"💳 Отримати документ — готовий до подачі  €{_doc_price:.2f}" if _doc_price else "💳 Отримати документ — готовий до подачі",
        "pl": f"💳 Otrzymaj dokument — gotowy do złożenia  €{_doc_price:.2f}" if _doc_price else "💳 Otrzymaj dokument — gotowy do złożenia",
        "tr": f"💳 Belgeyi al — teslime hazır  €{_doc_price:.2f}" if _doc_price else "💳 Belgeyi al — teslime hazır",
        "ar": f"💳 احصل على المستند — جاهز للتقديم  €{_doc_price:.2f}" if _doc_price else "💳 احصل على المستند — جاهز للتقديم",
    }

    # Bundle button — Document + Termin 24/7 monitoring at a combined price
    _bundle_texts = {
        "en": f"📅 Bundle: Document + Termin 24/7 — €{_bundle_price:.2f}  (save €{_TERMIN_STANDALONE - _TERMIN_STANDALONE * 0.75:.2f})",
        "de": f"📅 Bundle: Dokument + Termin 24/7 — €{_bundle_price:.2f}  (spare €{_TERMIN_STANDALONE - _TERMIN_STANDALONE * 0.75:.2f})",
        "uk": f"📅 Комплект: Документ + Termin 24/7 — €{_bundle_price:.2f}  (економія €{_TERMIN_STANDALONE - _TERMIN_STANDALONE * 0.75:.2f})",
        "ua": f"📅 Комплект: Документ + Termin 24/7 — €{_bundle_price:.2f}  (економія €{_TERMIN_STANDALONE - _TERMIN_STANDALONE * 0.75:.2f})",
        "pl": f"📅 Pakiet: Dokument + Termin 24/7 — €{_bundle_price:.2f}  (oszczędność €{_TERMIN_STANDALONE - _TERMIN_STANDALONE * 0.75:.2f})",
        "tr": f"📅 Paket: Belge + Termin 24/7 — €{_bundle_price:.2f}  (€{_TERMIN_STANDALONE - _TERMIN_STANDALONE * 0.75:.2f} tasarruf)",
        "ar": f"📅 حزمة: مستند + Termin 24/7 — €{_bundle_price:.2f}  (وفر €{_TERMIN_STANDALONE - _TERMIN_STANDALONE * 0.75:.2f})",
    }

    _button_edit_texts = {
        "en": "✏️ Edit answers",
        "de": "✏️ Antworten bearbeiten",
        "uk": "✏️ Редагувати відповіді",
        "pl": "✏️ Edytuj odpowiedzi",
        "tr": "✏️ Cevapları düzenle",
        "ar": "✏️ تحرير الإجابات",
    }

    kb = InlineKeyboardMarkup(row_width=1)
    # Primary CTA — document only
    kb.add(
        InlineKeyboardButton(
            text=_button_final_texts.get(user_lang, _button_final_texts["uk"]),
            callback_data=f"final_pdf_{doc_type}",
        )
    )
    # Bundle CTA — document + Termin (shown only when we have a meaningful price)
    if _bundle_price > 0:
        kb.add(
            InlineKeyboardButton(
                text=_bundle_texts.get(user_lang, _bundle_texts["en"]),
                callback_data=f"bundle_doc_termin_{doc_type}",
            )
        )
    kb.add(
        InlineKeyboardButton(
            text=_button_edit_texts.get(user_lang, _button_edit_texts["uk"]),
            callback_data="edit_answers",
        )
    )
    from handlers.nav import nav_back_text, nav_home_text
    kb.add(InlineKeyboardButton(text=nav_back_text(user_lang), callback_data="back_to_main_menu"))
    kb.add(InlineKeyboardButton(text=nav_home_text(user_lang), callback_data="main_menu"))

    # ── Try real-template snippet (PNG photo) first ──────────────────────────
    _snippet_caption = _SNIPPET_CAPTION_TEXTS.get(user_lang, _SNIPPET_CAPTION_TEXTS["en"])
    _bundesland = (authority_info or {}).get("bundesland") if authority_info else None
    _snippet_sent = False
    try:
        from backend.pdf_preview import create_template_snippet_image
        from io import BytesIO as _BytesIO

        _png_bytes = create_template_snippet_image(
            doc_type=doc_type,
            user_data=answers,
            lang=user_lang or "de",
            bundesland=_bundesland,
        )
        if _png_bytes:
            await message.answer_photo(
                photo=_BytesIO(_png_bytes),
                caption=_snippet_caption,
                reply_markup=kb,
            )
            _snippet_sent = True
            logger.info(
                "✅ Template snippet photo sent to user=%s doc_type=%s (%d B)",
                user_id, doc_type, len(_png_bytes),
            )
    except Exception as _snip_err:
        logger.debug("pdf_preview snippet failed (will fall back): %s", _snip_err)

    # If snippet was sent successfully, save state and return
    if _snippet_sent:
        uid = _uid(user_id)
        existing_entry = _PENDING_PREVIEWS.get((uid, doc_type))
        original_created_at = (
            existing_entry.get("created_at") if existing_entry else None
        )
        _PENDING_PREVIEWS[(uid, doc_type)] = {
            "answers": answers,
            "doc_type": doc_type,
            "authority_info": authority_info,
            "created_at": original_created_at or time.time(),
            "lang": user_lang,
            "user_lang": user_lang,
        }
        _save_previews()
        return

    if doc_type == "kiz":
        await message.answer(
            _PREVIEW_FAILED_TEXTS.get(user_lang, _PREVIEW_FAILED_TEXTS["en"]),
            reply_markup=kb,
        )
        return

    # ── Fallback: unofficial review-sheet PDF ────────────────────────────────
    try:
        preview_path = create_preview(
            user_id=user_id,
            user_data=answers,  # Pass answers as user_data
            doc_type=doc_type,
            authority_info=authority_info,
            user_lang=user_lang,
        )

        if not preview_path:
            raise RuntimeError(
                "create_preview returned None/empty - preview generation failed"
            )

        if not os.path.exists(preview_path):
            raise FileNotFoundError(preview_path)

        logger.info("✅ Preview PDF generated: %s", preview_path)

        processed_path = None
        try:
            processed_path = _make_onepage_watermarked_preview(preview_path)
        except Exception as e:
            logger.warning(f"⚠️ Failed to create one-page watermarked preview: {e}")

        send_path = processed_path or preview_path

        sent_successfully = False
        try:
            # ONE message: document + caption + inline keyboard (no separate pre/post messages)
            await message.answer_document(
                InputFile(send_path),
                caption=_preview_caption,
                reply_markup=kb,
            )
            sent_successfully = True
        except Exception as send_error:
            logger.error(
                f"❌ Failed to send preview PDF to user {user_id}: {send_error}",
                exc_info=True,
            )
            raise
        finally:
            if processed_path and processed_path != preview_path:
                try:
                    if os.path.exists(processed_path):
                        os.remove(processed_path)
                        logger.debug(
                            f"🧹 Cleaned up processed preview file: {processed_path}"
                        )
                except Exception as cleanup_error:
                    logger.warning(
                        f"⚠️ Failed to cleanup processed preview file {processed_path}: {cleanup_error}"
                    )
            if sent_successfully:
                try:
                    if os.path.exists(preview_path):
                        os.remove(preview_path)
                        logger.debug(f"🧹 Cleaned up preview file: {preview_path}")
                    _cleanup_old_preview_files()
                except Exception as cleanup_error:
                    logger.warning(
                        f"⚠️ Failed to cleanup preview file {preview_path}: {cleanup_error}"
                    )

        # CRITICAL FIX: Preserve original created_at timestamp to maintain TTL logic
        # If entry exists, keep its created_at; otherwise use current time
        uid = _uid(user_id)
        existing_entry = _PENDING_PREVIEWS.get((uid, doc_type))
        original_created_at = (
            existing_entry.get("created_at") if existing_entry else None
        )
        created_at = original_created_at if original_created_at else time.time()

        _PENDING_PREVIEWS[(uid, doc_type)] = {
            "answers": answers,
            "doc_type": doc_type,
            "authority_info": authority_info,
            "created_at": created_at,
            "lang": user_lang,
            "user_lang": user_lang,
        }

        # Show soft validation warnings after preview (non-blocking, advisory only)
        if _preview_warnings:
            _warn_lines = [
                w.get("message", "") for w in _preview_warnings if w.get("message")
            ]
            if _warn_lines:
                _warn_joined = "\n• ".join(_warn_lines)
                _WARN_HEADER = {
                    "uk": "⚠️ <b>Зверніть увагу:</b>\n• ",
                    "en": "⚠️ <b>Please note:</b>\n• ",
                    "de": "⚠️ <b>Bitte beachten:</b>\n• ",
                    "pl": "⚠️ <b>Uwaga:</b>\n• ",
                    "tr": "⚠️ <b>Dikkat:</b>\n• ",
                    "ar": "⚠️ <b>يرجى الانتباه:</b>\n• ",
                }
                _warn_msg = (
                    _WARN_HEADER.get(user_lang, _WARN_HEADER["en"]) + _warn_joined
                )
                try:
                    await message.answer(_warn_msg, parse_mode="HTML")
                except Exception:
                    pass  # non-blocking: warning display failure must never break flow

    except Exception as e:
        logger.error(
            f"❌ PDF preview generation failed for user {user_id} doc_type={doc_type}: {e}",
            exc_info=True,
        )
        # CRITICAL FIX: Do NOT clear user data on error - user might want to try again or edit
        # Only cleanup expired entries, not active user data
        # _PENDING_PREVIEWS.pop((uid, doc_type), None)  # REMOVED - preserve data on error
        await message.answer(
            _PREVIEW_FAILED_TEXTS.get(user_lang, _PREVIEW_FAILED_TEXTS["en"]),
            reply_markup=_make_back_inline_kb(user_lang),
        )


def _format_field_label(key: str, lang: str = "uk") -> str:
    """
    Format field key into human-readable label.
    Maps common field keys to localized labels.
    """
    field_labels = {
        "uk": {
            "first_name": "Ім'я",
            "last_name": "Прізвище",
            "plz": "Поштовий індекс",
            "city": "Місто",
            "street": "Вулиця",
            "house_number": "Номер будинку",
            "land": "Країна",
            "birthday": "Дата народження",
            "email": "Email",
            "phone": "Телефон",
        },
        "en": {
            "first_name": "First Name",
            "last_name": "Last Name",
            "plz": "Postal Code",
            "city": "City",
            "street": "Street",
            "house_number": "House Number",
            "land": "Country",
            "birthday": "Birthday",
            "email": "Email",
            "phone": "Phone",
        },
        "de": {
            "first_name": "Vorname",
            "last_name": "Nachname",
            "plz": "Postleitzahl",
            "city": "Stadt",
            "street": "Straße",
            "house_number": "Hausnummer",
            "land": "Land",
            "birthday": "Geburtsdatum",
            "email": "Email",
            "phone": "Telefon",
        },
        "pl": {
            "first_name": "Imię",
            "last_name": "Nazwisko",
            "plz": "Kod pocztowy",
            "city": "Miasto",
            "street": "Ulica",
            "house_number": "Numer domu",
            "land": "Kraj",
            "birthday": "Data urodzenia",
            "email": "Email",
            "phone": "Telefon",
        },
        "tr": {
            "first_name": "Ad",
            "last_name": "Soyad",
            "plz": "Posta kodu",
            "city": "Şehir",
            "street": "Sokak",
            "house_number": "Ev numarası",
            "land": "Ülke",
            "birthday": "Doğum tarihi",
            "email": "E-posta",
            "phone": "Telefon",
        },
        "ar": {
            "first_name": "الاسم الأول",
            "last_name": "اسم العائلة",
            "plz": "الرمز البريدي",
            "city": "المدينة",
            "street": "الشارع",
            "house_number": "رقم المنزل",
            "land": "البلد",
            "birthday": "تاريخ الميلاد",
            "email": "البريد الإلكتروني",
            "phone": "الهاتف",
        },
        "ua": None,
    }
    if field_labels.get("ua") is None:
        field_labels["ua"] = field_labels["uk"]

    labels = field_labels.get(lang) or field_labels.get("ua") or field_labels["uk"]
    return labels.get(key, key.replace("_", " ").title())


async def _show_confirmation_with_data(
    message: types.Message,
    answers: Dict[str, Any],
    doc_type: str,
    user_lang: str,
) -> None:
    logger.error("🔥 ENTERED _show_confirmation_with_data")

    """
    REQUIRED FIX: Show confirmation screen with ALL filled fields preview.
    This is the MANDATORY visible confirmation after WebApp submit.
    
    Shows:
    - ✅ "Анкету успішно отримано"
    - 📋 Text preview of ALL filled fields (key: value)
    - ✏️ Button: "Редагувати анкету" (reopen WebApp with existing data)
    - ➡️ Button: "Продовжити" (continue to payment)
    """
    user_id = _uid(message.from_user.id)

    # Build data preview text
    preview_lines = []
    for key, value in sorted(answers.items()):
        if value and str(value).strip():
            label = _format_field_label(key, user_lang)
            preview_lines.append(f"<b>{label}:</b> {str(value).strip()}")

    preview_text = "\n".join(preview_lines) if preview_lines else "—"

    # Confirmation message texts
    confirmation_texts = {
        "uk": (
            "✅ <b>Анкету успішно отримано</b>\n\n"
            "📋 <b>Заповнені поля:</b>\n"
            f"{preview_text}\n\n"
            "Перевірте дані. Якщо все правильно, натисніть 'Продовжити'."
        ),
        "en": (
            "✅ <b>Form successfully received</b>\n\n"
            "📋 <b>Filled fields:</b>\n"
            f"{preview_text}\n\n"
            "Please review the data. If everything is correct, press 'Continue'."
        ),
        "de": (
            "✅ <b>Formular erfolgreich erhalten</b>\n\n"
            "📋 <b>Ausgefüllte Felder:</b>\n"
            f"{preview_text}\n\n"
            "Bitte überprüfen Sie die Daten. Wenn alles korrekt ist, drücken Sie 'Weiter'."
        ),
        "pl": (
            "✅ <b>Formularz został otrzymany</b>\n\n"
            "📋 <b>Wypełnione pola:</b>\n"
            f"{preview_text}\n\n"
            "Proszę sprawdzić dane. Jeśli wszystko jest poprawne, naciśnij 'Kontynuuj'."
        ),
        "tr": (
            "✅ <b>Form başarıyla alındı</b>\n\n"
            "📋 <b>Doldurulan alanlar:</b>\n"
            f"{preview_text}\n\n"
            "Lütfen verileri kontrol edin. Her şey doğruysa 'Devam' düğmesine basın."
        ),
        "ar": (
            "✅ <b>تم استلام النموذج بنجاح</b>\n\n"
            "📋 <b>الحقول المملوءة:</b>\n"
            f"{preview_text}\n\n"
            "يرجى مراجعة البيانات. إذا كان كل شيء صحيحًا، اضغط على 'متابعة'."
        ),
    }

    confirmation_text = confirmation_texts.get(user_lang, confirmation_texts["uk"])

    # Guard against empty text
    if not confirmation_text or len(confirmation_text.strip()) == 0:
        confirmation_text = "✅ Form received. Please review and continue."

    # Create keyboard with required buttons
    kb = InlineKeyboardMarkup(row_width=1)

    # Button: "Редагувати анкету" (Edit form)
    edit_button_texts = {
        "uk": "✏️ Редагувати анкету",
        "en": "✏️ Edit form",
        "de": "✏️ Formular bearbeiten",
        "pl": "✏️ Edytuj formularz",
        "tr": "✏️ Formu düzenle",
        "ar": "✏️ تعديل النموذج",
    }
    kb.add(
        InlineKeyboardButton(
            text=edit_button_texts.get(user_lang, edit_button_texts["uk"]),
            callback_data="edit_answers",
        )
    )

    # Button: "Продовжити" (Continue)
    continue_button_texts = {
        "uk": "➡️ Продовжити",
        "en": "➡️ Continue",
        "de": "➡️ Weiter",
        "pl": "➡️ Kontynuuj",
        "tr": "➡️ Devam",
        "ar": "➡️ متابعة",
    }
    kb.add(
        InlineKeyboardButton(
            text=continue_button_texts.get(user_lang, continue_button_texts["uk"]),
            callback_data=f"final_pdf_{doc_type}",
        )
    )
    from handlers.nav import nav_back_text, nav_home_text
    kb.add(InlineKeyboardButton(text=nav_back_text(user_lang), callback_data="back_to_main_menu"))
    kb.add(InlineKeyboardButton(text=nav_home_text(user_lang), callback_data="main_menu"))

    # Send confirmation message
    try:
        logger.info(f"📤 Sending confirmation with data preview to user {user_id}")
        await message.answer(confirmation_text, parse_mode="HTML", reply_markup=kb)
        logger.info(f"✅ Confirmation screen sent to user {user_id}")
    except Exception as e:
        logger.error(
            f"❌ Failed to send confirmation to user {user_id}: {e}", exc_info=True
        )
        # Fallback: send without HTML
        try:
            plain_text = confirmation_text.replace("<b>", "").replace("</b>", "")
            await message.answer(plain_text, reply_markup=kb)
        except Exception as e2:
            logger.critical(
                f"❌ CRITICAL: Cannot send confirmation to user {user_id}: {e2}",
                exc_info=True,
            )


async def _show_preview_explanation(
    message: types.Message,
    answers: Dict[str, Any],
    doc_type: str,
    authority_info: Optional[Dict[str, Any]],
    user_lang: Optional[str] = None,
) -> None:
    """
    Show text-only screen before payment (preview PDF removed).
    Replaces preview PDF functionality with text message.

    CRITICAL: Uses data from _PENDING_PREVIEWS (single source of truth).
    Do NOT regenerate or modify data - use exactly what was saved in handle_webapp_data.
    """
    user_id = _uid(message.from_user.id)
    user_lang = _norm_lang(user_lang, user_id)

    # CRITICAL FIX: Use existing data from _PENDING_PREVIEWS (single source of truth)
    # This ensures preview always shows the EXACT data entered by the user
    uid = _uid(user_id)
    pending = _PENDING_PREVIEWS.get((uid, doc_type))
    if pending and pending.get("answers"):
        # Use the saved data (exact user input)
        answers = pending.get("answers")
        doc_type = pending.get("doc_type", doc_type)
        authority_info = pending.get("authority_info", authority_info)
        logger.debug(
            f"✅ Using saved data from _PENDING_PREVIEWS[({uid}, {doc_type})]: {len(answers)} fields"
        )
    else:
        # Fallback: validate and use provided data (should not happen in normal flow)
        logger.warning(
            f"⚠️ No saved data in _PENDING_PREVIEWS[({uid}, {doc_type})] for user {user_id}, using provided data"
        )
        if not answers or len(answers) == 0:
            error_texts = {
                "uk": "❌ <b>Помилка</b>\n\nДані анкети не отримано. Будь ласка, заповніть форму ще раз.",
                "en": "❌ <b>Error</b>\n\nForm data not received. Please fill out the form again.",
                "de": "❌ <b>Fehler</b>\n\nFormulardaten nicht empfangen. Bitte füllen Sie das Formular erneut aus.",
                "pl": "❌ <b>Błąd</b>\n\nDane formularza nie zostały odebrane. Proszę wypełnić formularz ponownie.",
                "tr": "❌ <b>Hata</b>\n\nForm verisi alınmadı. Lütfen formu tekrar doldurun.",
                "ar": "❌ <b>خطأ</b>\n\nلم يتم استلام بيانات النموذج. يرجى ملء النموذج مرة أخرى.",
            }
            error_text = error_texts.get(user_lang, error_texts["uk"])
            await message.answer(
                error_text,
                parse_mode="HTML",
                reply_markup=_make_back_inline_kb(user_lang),
            )
            return
        # Store fallback data
        # CRITICAL FIX: Preserve original created_at if entry exists, otherwise use current time
        uid = _uid(user_id)
        existing_entry = _PENDING_PREVIEWS.get((uid, doc_type))
        original_created_at = (
            existing_entry.get("created_at") if existing_entry else None
        )
        created_at = original_created_at if original_created_at else time.time()

        _PENDING_PREVIEWS[(uid, doc_type)] = {
            "answers": answers.copy(),
            "doc_type": doc_type,
            "authority_info": authority_info.copy() if authority_info else None,
            "created_at": created_at,
            "waiting_confirmation": True,
            "lang": user_lang,
            "user_lang": user_lang,
        }

    logger.info(
        f"📋 Showing preview explanation with {len(answers)} fields, doc_type={doc_type}"
    )

    # Get price for this document type — CRITICAL: never show €0.00 to user
    from bot_config.pricing import PDF_PRICES as _PDF_PRICES

    price = _PDF_PRICES.get(doc_type)
    if price is None:
        logger.error(
            "PRICE_MISSING_CRITICAL preview screen: doc_type=%r — aborting payment UI",
            doc_type,
        )
        _price_err = {
            "uk": "⚠️ Ціна для цього документа тимчасово недоступна. Зверніться до підтримки.",
            "ua": "⚠️ Ціна для цього документа тимчасово недоступна. Зверніться до підтримки.",
            "en": "⚠️ Price for this document is temporarily unavailable. Please contact support.",
            "de": "⚠️ Der Preis für dieses Dokument ist vorübergehend nicht verfügbar. Bitte Support kontaktieren.",
            "pl": "⚠️ Cena tego dokumentu jest tymczasowo niedostępna. Skontaktuj się z pomocą.",
            "tr": "⚠️ Bu belgenin fiyatı geçici olarak mevcut değil. Destek ile iletişime geçin.",
            "ar": "⚠️ سعر هذه الوثيقة غير متاح مؤقتاً. تواصل مع الدعم.",
        }
        try:
            await bot.send_message(user_id, _price_err.get(user_lang, _price_err["en"]))
        except Exception:
            pass
        return

    # Text message - human, calm, trustworthy tone — для всіх мов (ua=uk)
    message_texts = {
        "uk": (
            "✅ <b>Анкету успішно заповнено</b>\n\n"
            "📋 <b>Що ви отримаєте після оплати:</b>\n"
            "• заповнений приклад документа — щоб уникнути помилок\n"
            "• посилання на офіційну форму\n"
            "• коротку інструкцію з подачі документа\n\n"
            "Це не офіційний документ. Це заповнений зразок-підказка, "
            "який допоможе вам правильно заповнити офіційну форму."
        ),
        "ua": (
            "✅ <b>Анкету успішно заповнено</b>\n\n"
            "📋 <b>Що ви отримаєте після оплати:</b>\n"
            "• заповнений приклад документа — щоб уникнути помилок\n"
            "• посилання на офіційну форму\n"
            "• коротку інструкцію з подачі документа\n\n"
            "Це не офіційний документ. Це заповнений зразок-підказка, "
            "який допоможе вам правильно заповнити офіційну форму."
        ),
        "en": (
            "✅ <b>Form successfully completed</b>\n\n"
            "📋 <b>What you'll get after payment:</b>\n"
            "• filled document example — to help you avoid mistakes\n"
            "• link to the official form\n"
            "• short instructions for submitting the document\n\n"
            "This is not an official document. It is a filled guidance example "
            "to help you fill out the official form correctly."
        ),
        "de": (
            "✅ <b>Formular erfolgreich ausgefüllt</b>\n\n"
            "📋 <b>Was Sie nach der Zahlung erhalten:</b>\n"
            "• ausgefülltes Dokumentenbeispiel zur Fehlervermeidung\n"
            "• Link zum offiziellen Formular\n"
            "• kurze Anleitung zur Einreichung\n\n"
            "Kein offizielles Dokument. Ein ausgefuelltes Muster als Ausfuellhilfe "
            "fuer das offizielle Formular."
        ),
        "pl": (
            "✅ <b>Formularz wypełniony</b>\n\n"
            "📋 <b>Co otrzymasz po opłacie:</b>\n"
            "• wypełniony przykład dokumentu — aby uniknąć błędów\n"
            "• link do oficjalnego formularza\n"
            "• krótką instrukcję składania dokumentu\n\n"
            "To nie jest oficjalny dokument. To wypełniony wzór-podpowiedź, "
            "który pomoże Ci prawidłowo wypełnić oficjalny formularz."
        ),
        "tr": (
            "✅ <b>Form başarıyla tamamlandı</b>\n\n"
            "📋 <b>Ödemeden sonra ne alacaksınız:</b>\n"
            "• doldurulmuş belge örneği — hata yapmamak için\n"
            "• resmi form bağlantısı\n"
            "• belge sunumu için kısa talimatlar\n\n"
            "Bu resmi bir belge değildir. Resmi formu doğru doldurmanıza "
            "yardımcı olacak doldurulmuş bir rehber örnektir."
        ),
        "ar": (
            "✅ <b>تم ملء النموذج بنجاح</b>\n\n"
            "📋 <b>ما ستحصل عليه بعد الدفع:</b>\n"
            "• مثال مملوء للمستند — لتجنب الأخطاء\n"
            "• رابط النموذج الرسمي\n"
            "• تعليمات موجزة لتقديم المستند\n\n"
            "هذا ليس مستندًا رسميًا. إنه نموذج إرشادي مملوء "
            "لمساعدتك في ملء النموذج الرسمي بشكل صحيح."
        ),
    }

    # ua/uk — однаковий текст для української
    message_text = message_texts.get(
        user_lang, message_texts.get("ua", message_texts.get("uk", message_texts["en"]))
    )

    # Append "frequent mistakes" block (below disclaimer, above CTA)
    _mistakes = _get_mistakes_block(doc_type, user_lang)
    if _mistakes:
        message_text += f"\n\n{_mistakes}"

    # CRITICAL FIX: Guard against empty text (TASK 3)
    if not message_text or len(message_text.strip()) == 0:
        logger.error(
            f"❌ CRITICAL: message_text is EMPTY for user {user_id}, lang {user_lang}"
        )
        _empty_fb = {
            "uk": "✅ Анкету заповнено. Перейдіть до оплати.",
            "ua": "✅ Анкету заповнено. Перейдіть до оплати.",
            "en": "✅ Form completed. Please proceed with payment.",
            "de": "✅ Formular ausgefüllt. Bitte fahren Sie mit der Zahlung fort.",
            "pl": "✅ Formularz wypełniony. Przejdź do płatności.",
            "tr": "✅ Form tamamlandı. Lütfen ödemeye geçin.",
            "ar": "✅ تم ملء النموذج. يرجى المتابعة للدفع.",
        }
        message_text = _empty_fb.get(user_lang, _empty_fb["en"])

    # Create keyboard with payment and back buttons only
    kb = InlineKeyboardMarkup(row_width=1)

    # Single CTA — consistent label across all payment screens
    payment_button_texts = {
        "uk": f"💳 Оплатити €{price:.2f}",
        "ua": f"💳 Оплатити €{price:.2f}",
        "en": f"💳 Pay €{price:.2f}",
        "de": f"💳 Bezahlen €{price:.2f}",
        "pl": f"💳 Zapłać €{price:.2f}",
        "tr": f"💳 Öde €{price:.2f}",
        "ar": f"💳 ادفع €{price:.2f}",
    }
    final_payment_text = payment_button_texts.get(
        user_lang, payment_button_texts.get("ua", payment_button_texts["en"])
    )
    kb.add(
        InlineKeyboardButton(
            text=final_payment_text, callback_data=f"final_pdf_{doc_type}"
        )
    )

    back_button_texts = {
        "uk": "✏️ Виправити анкету",
        "ua": "✏️ Виправити анкету",
        "en": "✏️ Edit form",
        "de": "✏️ Formular bearbeiten",
        "pl": "✏️ Popraw ankietę",
        "tr": "✏️ Formu düzenle",
        "ar": "✏️ تعديل النموذج",
    }
    back_button_text = back_button_texts.get(
        user_lang, back_button_texts.get("ua", back_button_texts["en"])
    )
    kb.add(InlineKeyboardButton(text=back_button_text, callback_data="edit_answers"))

    # === DEMO PDF PREVIEW (before payment) ===
    # Send sample PDF so user sees what they'll get after payment
    _demo_captions = {
        "uk": "📄 <b>Приклад заповненого документа</b>\n\nОсь так виглядатиме ваш документ після оплати. Всі поля будуть заповнені на основі ваших даних.",
        "ua": "📄 <b>Приклад заповненого документа</b>\n\nОсь так виглядатиме ваш документ після оплати. Всі поля будуть заповнені на основі ваших даних.",
        "en": "📄 <b>Example of a filled document</b>\n\nThis is how your document will look after payment. All fields will be filled based on your data.",
        "de": "📄 <b>Beispiel eines ausgefüllten Dokuments</b>\n\nSo wird Ihr Dokument nach der Zahlung aussehen. Alle Felder werden basierend auf Ihren Daten ausgefüllt.",
        "pl": "📄 <b>Przykład wypełnionego dokumentu</b>\n\nTak będzie wyglądał Twój dokument po opłacie. Wszystkie pola zostaną wypełnione na podstawie Twoich danych.",
        "tr": "📄 <b>Doldurulmuş belge örneği</b>\n\nÖdemeden sonra belgeniz böyle görünecek. Tüm alanlar verilerinize göre doldurulacaktır.",
        "ar": "📄 <b>مثال على مستند مملوء</b>\n\nهكذا سيبدو مستندك بعد الدفع. سيتم ملء جميع الحقول استنادًا إلى بياناتك.",
    }
    _demo_paths = {
        "anmeldung": "generated_pdfs/_qa/anmeldung_preview.pdf",
        "abmeldung": "generated_pdfs/_qa/abmeldung_preview.pdf",
        "ummeldung": "generated_pdfs/_qa/ummeldung_preview.pdf",
        "wohngeld": "generated_pdfs/_qa/wohngeld_preview.pdf",
        "kindergeld": "generated_pdfs/_qa/kindergeld_preview.pdf",
        "buergergeld": "generated_pdfs/_qa/buergergeld_preview.pdf",
        "aufenthaltstitel": "generated_pdfs/_qa/aufenthaltstitel_preview.pdf",
        "wohnungsgeberbestaetigung": "generated_pdfs/_qa/wohnungsgeberbestaetigung_preview.pdf",
    }
    _watermark_temp_path = None
    try:
        _demo_path = _demo_paths.get(doc_type)
        if _demo_path and os.path.exists(_demo_path):
            _demo_caption = _demo_captions.get(user_lang, _demo_captions["en"])
            # Add PREVIEW watermark to demo PDF
            _watermark_temp_path = _add_preview_watermark(_demo_path, user_id, doc_type, lang=user_lang)
            _send_path = _watermark_temp_path if _watermark_temp_path else _demo_path
            await message.answer_document(
                InputFile(_send_path), caption=_demo_caption, parse_mode="HTML",
                reply_markup=ReplyKeyboardRemove(),
            )
            logger.info(f"DEMO_PDF_SENT user_id={user_id} doc_type={doc_type}")
    except Exception as _demo_err:
        logger.debug(f"Demo PDF send failed (non-critical): {_demo_err}")
    finally:
        # Cleanup temporary watermarked file
        if _watermark_temp_path and os.path.exists(_watermark_temp_path):
            try:
                os.remove(_watermark_temp_path)
            except Exception:
                pass

    # TASK 3 & 4: GUARANTEE VISIBLE MESSAGE - Guard against empty text
    if not message_text or len(message_text.strip()) == 0:
        logger.error(
            f"❌ CRITICAL: message_text is EMPTY in _show_preview_explanation for user {user_id}"
        )
        _empty_fb2 = {
            "uk": "✅ Анкету заповнено. Перейдіть до оплати.",
            "ua": "✅ Анкету заповнено. Перейдіть до оплати.",
            "en": "✅ Form completed. Please proceed with payment.",
            "de": "✅ Formular ausgefüllt. Bitte fahren Sie mit der Zahlung fort.",
            "pl": "✅ Formularz wypełniony. Przejdź do płatności.",
            "tr": "✅ Form tamamlandı. Lütfen ödemeye geçin.",
            "ar": "✅ تم ملء النموذج. يرجى المتابعة للدفع.",
        }
        message_text = _empty_fb2.get(user_lang, _empty_fb2["en"])

    # Now send the main message with inline buttons (this also ensures keyboard stays removed)
    try:
        logger.info(
            f"📤 Sending preview explanation message to user {user_id} (text length: {len(message_text)})"
        )
        await message.answer(message_text, parse_mode="HTML", reply_markup=kb)
        logger.info(
            f"✅ Preview explanation message sent successfully to user {user_id}"
        )
    except Exception as e:
        logger.error(
            f"❌ CRITICAL: Failed to send preview explanation message to user {user_id}: {e}",
            exc_info=True,
        )
        # Fallback: send without HTML
        try:
            plain_text = (
                message_text.replace("<b>", "")
                .replace("</b>", "")
                .replace("<i>", "")
                .replace("</i>", "")
            )
            await message.answer(plain_text, reply_markup=kb)
        except Exception as e2:
            logger.critical(
                f"❌ CRITICAL: Cannot send ANY preview message to user {user_id}: {e2}",
                exc_info=True,
            )
            # Last resort — localized
            _lr = {
                "uk": "✅ Анкету заповнено.",
                "ua": "✅ Анкету заповнено.",
                "en": "✅ Form completed.",
                "de": "✅ Formular ausgefüllt.",
                "pl": "✅ Formularz wypełniony.",
                "tr": "✅ Form tamamlandı.",
                "ar": "✅ تم ملء النموذج.",
            }
            await message.answer(_lr.get(user_lang, _lr["en"]), reply_markup=kb)


# DEPRECATED: Authority choice handlers removed
# Address is now ALWAYS auto-filled silently by PLZ - no user interaction needed
# These handlers are kept for backward compatibility but should never be called
# If called, they will redirect to preview explanation with auto-filled authority


async def _handle_authority_choice(
    callback_query: types.CallbackQuery, use_auto: bool
) -> None:
    """
    DEPRECATED: Authority choice is no longer shown to users.
    Address is always auto-filled silently.
    This handler exists only for backward compatibility.
    """
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)

    if not _check_onboarding_complete(user_id):
        return

    uid = _uid(user_id)
    pending = _get_latest_pending(user_id)
    if not pending or not pending.get("answers"):
        _cleanup_old_previews(exclude_user_id=uid)
        pending = _get_latest_pending(user_id)

    if not pending:
        return

    answers: Dict[str, Any] = pending.get("answers") or {}
    doc_type: str = pending.get("doc_type") or "unknown"
    authority_info: Optional[Dict[str, Any]] = (
        pending.get("authority_info") if get_requires_bundesland(doc_type) else None
    )
    user_lang_raw: Optional[str] = pending.get("lang") or pending.get("user_lang")
    user_lang = _norm_lang(user_lang_raw, user_id)

    # CRITICAL FIX: Preserve original created_at timestamp to maintain TTL logic
    original_created_at = pending.get("created_at") if pending else None
    created_at = original_created_at if original_created_at else time.time()

    _PENDING_PREVIEWS[(uid, doc_type)] = {
        "answers": answers,
        "doc_type": doc_type,
        "authority_info": authority_info,  # Always use auto-filled authority
        "created_at": created_at,
        "lang": user_lang,
        "user_lang": user_lang,
    }

    await _show_preview_explanation(
        callback_query.message, answers, doc_type, authority_info, user_lang
    )


async def authority_use_auto(callback_query: types.CallbackQuery):
    """DEPRECATED: Authority choice removed - always uses auto authority."""
    await _handle_authority_choice(callback_query, use_auto=True)


async def authority_manual(callback_query: types.CallbackQuery):
    """DEPRECATED: Authority choice removed - always uses auto authority."""
    await _handle_authority_choice(
        callback_query, use_auto=True
    )  # Changed to always use auto


async def handle_generate_preview_pdf(callback_query: types.CallbackQuery):
    """
    DISABLED: Preview PDF functionality removed.
    This handler is kept for backward compatibility but does nothing.
    Users should use payment flow instead.
    """
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)
    user_lang = _norm_lang(None, user_id)

    disabled_texts = {
        "uk": "❌ Превʼю PDF більше не доступне.\n\nБудь ласка, використайте кнопку оплати для отримання готового прикладу документа.",
        "en": "❌ Preview PDF is no longer available.\n\nPlease use the payment button to get the ready document example.",
        "de": "❌ PDF-Vorschau ist nicht mehr verfügbar.\n\nBitte verwenden Sie die Zahlungsschaltfläche, um das fertige Dokumentbeispiel zu erhalten.",
        "pl": "❌ Podgląd PDF nie jest już dostępny.\n\nProszę użyć przycisku płatności, aby otrzymać gotowy przykład dokumentu.",
        "tr": "❌ PDF önizleme artık mevcut değil.\n\nLütfen hazır belge örneğini almak için ödeme düğmesini kullanın.",
        "ar": "❌ معاينة PDF لم تعد متاحة.\n\nيرجى استخدام زر الدفع للحصول على مثال المستند الجاهز.",
    }
    disabled_text = disabled_texts.get(user_lang, disabled_texts["uk"])

    await callback_query.message.answer(disabled_text)


def _check_payment_status(
    user_id: int,
    doc_type: str,
    current_order_id: Optional[int] = None,
) -> tuple[bool, Optional[int]]:
    """
    Check if user has paid for this document.
    CRITICAL: «Вже оплачено» тільки для замовлення цього прев'ю (current_order_id), не для старих замовлень.

    - Якщо current_order_id задано: перевіряємо ТІЛЬКИ це замовлення (той, що створили для цього прев'ю).
    - Якщо не задано: перевіряємо будь-яке оплачене замовлення user+doc_type (для зворотної сумісності).

    Returns:
        (is_paid: bool, order_id: Optional[int])
    """
    try:
        from utils.helpers import get_db
        from backend.database import OrderStatus

        db = get_db()
        if not hasattr(db, "get_order") and not hasattr(db, "get_user_orders"):
            return False, None

        # Режим «тільки замовлення цього прев'ю» — старі записи в БД не рахуються
        if current_order_id is not None:
            order = db.get_order(current_order_id)
            if not order or order.get("user_id") != user_id:
                return False, None
            if (order.get("doc_type") or "").strip().lower() != (
                doc_type or ""
            ).strip().lower():
                return False, None
            status = (order.get("status") or "").strip().lower()
            if status not in (
                OrderStatus.PAID.value,
                OrderStatus.SENT.value,
                OrderStatus.DOWNLOADED.value,
            ):
                return False, None
            logger.info(
                f"✅ Payment confirmed for current order order_id={current_order_id}"
            )
            return True, current_order_id

        # Загальний пошук (без current_order_id)
        if not hasattr(db, "get_user_orders"):
            return False, None
        orders = db.get_user_orders(user_id, limit=10)
        for order in orders:
            if (order.get("doc_type") or "").strip().lower() != (
                doc_type or ""
            ).strip().lower():
                continue
            status = (order.get("status") or "").strip().lower()
            if status not in (
                OrderStatus.PAID.value,
                OrderStatus.SENT.value,
                OrderStatus.DOWNLOADED.value,
            ):
                continue
            logger.info(
                f"✅ Payment confirmed for user {user_id}, doc_type {doc_type}, order_id {order.get('order_id')}"
            )
            return True, order.get("order_id")

        return False, None
    except Exception as e:
        logger.warning(
            f"⚠️ Payment check failed for user {user_id}, doc_type {doc_type}: {e}"
        )
        return False, None


async def handle_consent_accept(callback_query: types.CallbackQuery):
    """
    User confirmed personal data consent.
    Set flag in _PENDING_PREVIEWS and re-trigger final_pdf flow.
    """
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)
    uid = _uid(user_id)
    # Extract doc_type from callback_data: "consent_accept_{doc_type}"
    doc_type = callback_query.data.replace("consent_accept_", "") or "unknown"
    pending = _PENDING_PREVIEWS.get((uid, doc_type))
    if not pending:
        return True

    pending["personal_data_consent"] = True
    logger.info("CONSENT_ACCEPTED: user_id=%s doc_type=%s", user_id, doc_type)

    # Also persist consent in main DB
    try:
        from utils.helpers import get_db

        db = get_db()
        db.set_gdpr_consent(int(user_id), True)
    except Exception:
        pass

    # Re-trigger the payment flow by simulating the original callback
    callback_query.data = f"final_pdf_{doc_type}"
    await handle_final_pdf(callback_query)
    return True


async def handle_final_pdf(callback_query: types.CallbackQuery):
    """
    Generate final PDF without watermark after payment confirmation.

    PAYMENT GATING: This function now requires payment before generating the full sample PDF.
    """
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)
    # ISOLATION FIX: extract doc_type from callback_data — never rely on the slot's doc_type
    doc_type: str = callback_query.data.replace("final_pdf_", "") or "unknown"

    logger.info(
        "PAYMENT_CLICKED user_id=%s doc_type=%s",
        user_id, doc_type,
    )

    if not _check_onboarding_complete(user_id):
        logger.warning("PAYMENT_BLOCKED_ONBOARDING user_id=%s", user_id)
        return

    uid = _uid(user_id)
    pending = _PENDING_PREVIEWS.get((uid, doc_type))

    if not pending:
        logger.warning(
            "PAYMENT_NO_PENDING user_id=%s doc_type=%s — prompting user to re-open form",
            user_id, doc_type,
        )
        # Give visible feedback instead of silent fail — user's session may have expired
        user_lang = _norm_lang(None, user_id)
        _no_session_texts = {
            "uk": (
                "⚠️ <b>Сесія закінчилась</b>\n\n"
                "Будь ласка, заповніть анкету ще раз — дані не збереглися."
            ),
            "en": (
                "⚠️ <b>Session expired</b>\n\n"
                "Please fill in the form again — your data was not saved."
            ),
            "de": (
                "⚠️ <b>Sitzung abgelaufen</b>\n\n"
                "Bitte füllen Sie das Formular erneut aus — die Daten wurden nicht gespeichert."
            ),
            "pl": (
                "⚠️ <b>Sesja wygasła</b>\n\n"
                "Proszę wypełnić formularz jeszcze raz — dane nie zostały zapisane."
            ),
            "tr": (
                "⚠️ <b>Oturum sona erdi</b>\n\n"
                "Lütfen formu tekrar doldurun — verileriniz kaydedilmedi."
            ),
            "ar": (
                "⚠️ <b>انتهت الجلسة</b>\n\n"
                "يرجى ملء النموذج مرة أخرى — لم يتم حفظ بياناتك."
            ),
        }
        from handlers.nav import nav_home_text
        _retry_kb = InlineKeyboardMarkup(row_width=1)
        _retry_kb.add(InlineKeyboardButton(
            text={"uk": "📋 Заповнити анкету", "en": "📋 Fill form", "de": "📋 Formular ausfüllen",
                  "pl": "📋 Wypełnij formularz", "tr": "📋 Formu doldur", "ar": "📋 ملء النموذج"
                  }.get(user_lang, "📋 Fill form"),
            callback_data=f"doc_{doc_type}",
        ))
        _retry_kb.add(InlineKeyboardButton(
            text=nav_home_text(user_lang), callback_data="main_menu"
        ))
        try:
            await callback_query.message.answer(
                _no_session_texts.get(user_lang, _no_session_texts["en"]),
                parse_mode="HTML",
                reply_markup=_retry_kb,
            )
        except Exception:
            pass
        return

    # Read answers from the doc_type-scoped slot — guaranteed correct document
    answers: Dict[str, Any] = pending.get("answers") or {}
    authority_info: Optional[Dict[str, Any]] = (
        pending.get("authority_info") if get_requires_bundesland(doc_type) else None
    )
    user_lang_raw: Optional[str] = pending.get("lang") or pending.get("user_lang")
    user_lang = _norm_lang(user_lang_raw, user_id)

    # PAYMENT GATING: «Вже оплачено» тільки для замовлення ЦЬОГО прев'ю. Старі замовлення в БД не враховуємо.
    order_id_for_this_preview = pending.get("order_id")
    if order_id_for_this_preview is not None:
        is_paid, order_id = _check_payment_status(
            user_id, doc_type, current_order_id=order_id_for_this_preview
        )
    else:
        # Ще не створювали замовлення для цього прев'ю — одразу потрібна оплата, не дивимось старі записи
        is_paid, order_id = False, None
    logger.info(
        f"PAYMENT_CHECK user_id={user_id} doc_type={doc_type} order_id_for_preview={order_id_for_this_preview} is_paid={is_paid}"
    )

    # Uncomment the block below to re-enable free document credits.
    # _free_credit_used = False
    # if not is_paid:
    #     try:
    #         ... (free credit delivery code preserved for future re-activation)
    #     except Exception as _credit_err:
    #         logger.debug("FREE_CREDIT_CHECK_FAILED: %s", _credit_err)

    if not is_paid:
        logger.info(f"🔒 Payment required for user {user_id}, doc_type {doc_type}")

        # STRICT: Anmeldung — block payment if form validation fails (placeholders, required, format, PLZ/city, dates, authority)
        # TASK 4: errors → block; warnings → show notice but allow payment
        if (doc_type or "").strip().lower() == "anmeldung":
            try:
                from backend.form_validation import (
                    validate_anmeldung_form,
                    get_validation_errors_localized,
                )

                valid, val_errors, val_warnings = validate_anmeldung_form(
                    answers, user_lang
                )
                if not valid and val_errors:
                    localized = get_validation_errors_localized(val_errors, user_lang)
                    err_lines = [
                        e.get("message", e.get("message_key", "")) for e in localized
                    ]
                    _err_joined = "\n• ".join(err_lines)
                    VALIDATION_BLOCK_MSG = {
                        "uk": "⚠️ <b>Не можна перейти до оплати</b>\n\nВиправте помилки у формі:\n• "
                        + _err_joined,
                        "ua": "⚠️ <b>Не можна перейти до оплати</b>\n\nВиправте помилки у формі:\n• "
                        + _err_joined,
                        "en": "⚠️ <b>Cannot proceed to payment</b>\n\nPlease fix the following errors in the form:\n• "
                        + _err_joined,
                        "de": "⚠️ <b>Zahlung nicht möglich</b>\n\nBitte korrigieren Sie folgende Fehler im Formular:\n• "
                        + _err_joined,
                        "pl": "⚠️ <b>Nie można przejść do płatności</b>\n\nPopraw błędy w formularzu:\n• "
                        + _err_joined,
                        "tr": "⚠️ <b>Ödemeye geçilemiyor</b>\n\nFormdaki hataları düzeltin:\n• "
                        + _err_joined,
                        "ar": "⚠️ <b>لا يمكن المتابعة للدفع</b>\n\nيرجى تصحيح الأخطاء في النموذج:\n• "
                        + _err_joined,
                    }
                    msg = VALIDATION_BLOCK_MSG.get(
                        user_lang, VALIDATION_BLOCK_MSG.get("en", "")
                    )
                    from handlers.nav import nav_home_text
                    _back_form_btn = {
                        "uk": "← Повернутися до форми",
                        "en": "← Back to form",
                        "de": "← Zurück zum Formular",
                        "pl": "← Powrót do formularza",
                        "tr": "← Forma geri dön",
                        "ar": "← العودة إلى النموذج",
                    }
                    kb = InlineKeyboardMarkup(row_width=1)
                    kb.add(
                        InlineKeyboardButton(
                            text=_back_form_btn.get(user_lang, _back_form_btn["en"]),
                            callback_data="back_to_main_menu",
                        )
                    )
                    kb.add(
                        InlineKeyboardButton(
                            text=nav_home_text(user_lang),
                            callback_data="main_menu",
                        )
                    )
                    await callback_query.message.answer(
                        msg, parse_mode="HTML", reply_markup=kb
                    )
                    return
                # TASK 4: Warnings — show notice ONCE, then allow payment to proceed
                # Guard: only show the warning if it hasn't been shown for this form session.
                # The flag resets automatically when the user re-submits / edits the form
                # (because handle_webapp_data creates a fresh _PENDING_PREVIEWS entry).
                if val_warnings and not pending.get("warn_shown"):
                    localized_warns = get_validation_errors_localized(
                        val_warnings, user_lang
                    )
                    warn_lines = [
                        w.get("message", "")
                        for w in localized_warns
                        if w.get("message")
                    ]
                    if warn_lines:
                        _wj = "\n• ".join(warn_lines)
                        _WARN_NOTICE = {
                            "uk": "ℹ️ <b>Важливо:</b>\n• " + _wj,
                            "en": "ℹ️ <b>Important:</b>\n• " + _wj,
                            "de": "ℹ️ <b>Wichtig:</b>\n• " + _wj,
                            "pl": "ℹ️ <b>Ważne:</b>\n• " + _wj,
                            "tr": "ℹ️ <b>Önemli:</b>\n• " + _wj,
                            "ar": "ℹ️ <b>مهم:</b>\n• " + _wj,
                        }
                        try:
                            await callback_query.message.answer(
                                _WARN_NOTICE.get(user_lang, _WARN_NOTICE["en"]),
                                parse_mode="HTML",
                            )
                            pending["warn_shown"] = True
                        except Exception:
                            pass  # non-blocking: warning display failure must never break payment
            except Exception as e:
                logger.warning("Anmeldung form validation check failed: %s", e)

        from bot_config.pricing import PDF_PRICES as _PDF_PRICES

        price = _PDF_PRICES.get(doc_type)
        if price is None:
            logger.error(
                "PRICE_MISSING_CRITICAL payment initiation: doc_type=%r — blocked Stripe call",
                doc_type,
            )
            _err_texts = {
                "uk": "⚠️ Ціна для цього документа тимчасово недоступна. Зверніться до підтримки.",
                "ua": "⚠️ Ціна для цього документа тимчасово недоступна. Зверніться до підтримки.",
                "en": "⚠️ Price for this document is temporarily unavailable. Please contact support.",
                "de": "⚠️ Der Preis für dieses Dokument ist vorübergehend nicht verfügbar.",
                "pl": "⚠️ Cena tego dokumentu jest tymczasowo niedostępna.",
                "tr": "⚠️ Bu belgenin fiyatı geçici olarak mevcut değil.",
                "ar": "⚠️ سعر هذه الوثيقة غير متاح مؤقتاً.",
            }
            _lang_key = user_lang if user_lang in _err_texts else "en"
            try:
                await callback_query.answer(_err_texts[_lang_key], show_alert=True)
            except Exception:
                pass
            return

        logger.info(
            "PAYMENT_INIT user_id=%s doc_type=%s price=%.2f order_id=%s",
            user_id, doc_type, price, order_id_for_this_preview,
        )

        # Form data persistence: payment must NEVER rely only on in-memory data. Persist to order before paywall.
        if not answers or len(answers) == 0:
            return
        order_id_for_payment = order_id_for_this_preview
        try:
            from utils.helpers import get_db
            from backend.database import OrderStatus as _OrdSt

            db = get_db()

            # Guard: discard stale order_id if it belongs to a different doc_type or is already completed.
            # This prevents success_url from embedding an old order_id (e.g. from a prior payment session).
            if order_id_for_payment is not None and hasattr(db, "get_order"):
                _existing = db.get_order(order_id_for_payment)
                _existing_doc = (
                    (_existing.get("doc_type") or "").strip().lower()
                    if _existing
                    else ""
                )
                _existing_status = (
                    (_existing.get("status") or "").strip().lower() if _existing else ""
                )
                _stale = (
                    not _existing
                    or _existing_doc != (doc_type or "").strip().lower()
                    or _existing_status
                    in (_OrdSt.PAID.value, _OrdSt.SENT.value, _OrdSt.DOWNLOADED.value)
                )
                if _stale:
                    logger.info(
                        "ORDER_ID_STALE: discarding order_id=%s (doc=%s status=%s) for new doc_type=%s",
                        order_id_for_payment,
                        _existing_doc,
                        _existing_status,
                        doc_type,
                    )
                    order_id_for_payment = None
                    _PENDING_PREVIEWS[(uid, doc_type)]["order_id"] = None

            # CRITICAL: Log answers before persisting for debugging
            answers_json = json.dumps(answers)
            logger.info(
                "PAYMENT_PERSIST_START: user_id=%s order_id=%s answers_fields=%s answers_len=%s",
                user_id,
                order_id_for_payment,
                len(answers),
                len(answers_json),
            )

            if order_id_for_payment is not None and hasattr(
                db, "update_order_user_data"
            ):
                # Refresh order with current form data so delivery never loses it
                update_result = db.update_order_user_data(
                    order_id_for_payment, answers_json
                )
                if update_result:
                    logger.info(
                        "PAYMENT_DATA_UPDATED: order_id=%s answers_fields=%s",
                        order_id_for_payment,
                        len(answers),
                    )
                else:
                    logger.warning(
                        "PAYMENT_DATA_UPDATE_FAILED: order_id=%s — row not found in DB, "
                        "falling back to create_order so user_data is persisted",
                        order_id_for_payment,
                    )
                    order_id_for_payment = None
                    if (uid, doc_type) in _PENDING_PREVIEWS:
                        _PENDING_PREVIEWS[(uid, doc_type)]["order_id"] = None
            if order_id_for_payment is None and hasattr(db, "create_order"):
                logger.info(
                    f"CREATE_ORDER DEBUG | user_id={user_id} "
                    f"doc_type={doc_type} "
                    f"user_data_exists={bool(answers_json)} "
                    f"user_data_type={type(answers_json)}"
                )
                order_id_for_payment = db.create_order(
                    user_id=user_id,
                    doc_type=doc_type,
                    amount=price,
                    user_data=answers_json,
                    lang=user_lang,
                )
                if order_id_for_payment is not None:
                    _PENDING_PREVIEWS[(uid, doc_type)][
                        "order_id"
                    ] = order_id_for_payment
                logger.info(
                    "PAYMENT_ORDER_CREATED: order_id=%s user_id=%s doc_type=%s answers_count=%s",
                    order_id_for_payment,
                    user_id,
                    doc_type,
                    len(answers),
                )
                # FUNNEL POINT 2: form submitted and order created
                logger.info(
                    "FUNNEL | step=form_submitted user_id=%s doc=%s order_id=%s",
                    user_id,
                    doc_type,
                    order_id_for_payment,
                )
                if order_id_for_payment is not None:
                    saved_order = db.get_order(order_id_for_payment)
                    logger.info(
                        f"ORDER_SAVED DEBUG | order_id={order_id_for_payment} "
                        f"user_data_saved={bool(saved_order.get('user_data') if saved_order else None)}"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Failed to create/update order: {e}")

        # ── CONSENT GATE: require personal data consent before showing paywall ──
        if not pending.get("personal_data_consent"):
            _consent_text = {
                "uk": (
                    "🔒 <b>Згода на обробку даних</b>\n\n"
                    "Я погоджуюсь на обробку персональних даних "
                    "та підтверджую, що ознайомлений з умовами сервісу.\n\n"
                    "<i>Ваші дані використовуються тільки для формування документа.</i>"
                ),
                "ua": (
                    "🔒 <b>Згода на обробку даних</b>\n\n"
                    "Я погоджуюсь на обробку персональних даних "
                    "та підтверджую, що ознайомлений з умовами сервісу.\n\n"
                    "<i>Ваші дані використовуються тільки для формування документа.</i>"
                ),
                "en": (
                    "🔒 <b>Data processing consent</b>\n\n"
                    "I agree to the processing of my personal data "
                    "and confirm that I have read the terms of service.\n\n"
                    "<i>Your data is used only to generate the document.</i>"
                ),
                "de": (
                    "🔒 <b>Einwilligung zur Datenverarbeitung</b>\n\n"
                    "Ich stimme der Verarbeitung meiner personenbezogenen Daten zu "
                    "und bestätige, die Nutzungsbedingungen gelesen zu haben.\n\n"
                    "<i>Ihre Daten werden ausschließlich zur Dokumenterstellung verwendet.</i>"
                ),
                "pl": (
                    "🔒 <b>Zgoda na przetwarzanie danych</b>\n\n"
                    "Wyrażam zgodę na przetwarzanie moich danych osobowych "
                    "i potwierdzam zapoznanie się z regulaminem.\n\n"
                    "<i>Twoje dane są wykorzystywane wyłącznie do przygotowania dokumentu.</i>"
                ),
                "tr": (
                    "🔒 <b>Veri işleme onayı</b>\n\n"
                    "Kişisel verilerimin işlenmesine onay veriyorum "
                    "ve hizmet şartlarını okuduğumu kabul ediyorum.\n\n"
                    "<i>Verileriniz yalnızca belge oluşturmak için kullanılır.</i>"
                ),
                "ar": (
                    "🔒 <b>الموافقة على معالجة البيانات</b>\n\n"
                    "أوافق على معالجة بياناتي الشخصية "
                    "وأؤكد أنني قرأت شروط الخدمة.\n\n"
                    "<i>يتم استخدام بياناتك فقط لإنشاء المستند.</i>"
                ),
            }
            _consent_btn = {
                "uk": "✅ Погоджуюсь — продовжити",
                "ua": "✅ Погоджуюсь — продовжити",
                "en": "✅ I agree — continue",
                "de": "✅ Ich stimme zu — weiter",
                "pl": "✅ Zgadzam się — kontynuuj",
                "tr": "✅ Kabul ediyorum — devam et",
                "ar": "✅ أوافق — متابعة",
            }
            _consent_back = {
                "uk": "⬅️ Назад",
                "ua": "⬅️ Назад",
                "en": "⬅️ Back",
                "de": "⬅️ Zurück",
                "pl": "⬅️ Wstecz",
                "tr": "⬅️ Geri",
                "ar": "⬅️ رجوع",
            }
            from handlers.nav import nav_home_text
            consent_kb = InlineKeyboardMarkup(row_width=1)
            consent_kb.add(
                InlineKeyboardButton(
                    text=_consent_btn.get(user_lang, _consent_btn["en"]),
                    callback_data=f"consent_accept_{doc_type}",
                )
            )
            consent_kb.add(
                InlineKeyboardButton(
                    text=_consent_back.get(user_lang, _consent_back["en"]),
                    callback_data="show_post_form_menu",
                )
            )
            consent_kb.add(
                InlineKeyboardButton(
                    text=nav_home_text(user_lang),
                    callback_data="main_menu",
                )
            )
            await callback_query.message.answer(
                _consent_text.get(user_lang, _consent_text["en"]),
                parse_mode="HTML",
                reply_markup=consent_kb,
            )
            return

        # Paywall: ultra-short confirmation — price + Stripe button (value props already shown on post-form)
        _pay_body = {
            "uk": f"💳 <b>Оплата — €{price:.2f}</b>\n\nЗаповнений приклад + офіційна форма + інструкція.",
            "ua": f"💳 <b>Оплата — €{price:.2f}</b>\n\nЗаповнений приклад + офіційна форма + інструкція.",
            "en": f"💳 <b>Payment — €{price:.2f}</b>\n\nFilled example + official form + instructions.",
            "de": f"💳 <b>Zahlung — €{price:.2f}</b>\n\nAusgefülltes Beispiel + offizielles Formular + Anleitung.",
            "pl": f"💳 <b>Płatność — €{price:.2f}</b>\n\nWypełniony przykład + oficjalny formularz + instrukcja.",
            "tr": f"💳 <b>Ödeme — €{price:.2f}</b>\n\nDoldurulmuş örnek + resmi form + talimatlar.",
            "ar": f"💳 <b>الدفع — €{price:.2f}</b>\n\nمثال مملوء + النموذج الرسمي + التعليمات.",
        }
        payment_text = _pay_body.get(user_lang, _pay_body.get("ua", _pay_body["en"]))

        kb = InlineKeyboardMarkup(row_width=1)
        pay_button_texts = {
            "uk": f"💳 Оплатити €{price:.2f}",
            "ua": f"💳 Оплатити €{price:.2f}",
            "en": f"💳 Pay €{price:.2f}",
            "de": f"💳 Bezahlen €{price:.2f}",
            "pl": f"💳 Zapłać €{price:.2f}",
            "tr": f"💳 Öde €{price:.2f}",
            "ar": f"💳 ادفع €{price:.2f}",
        }
        pay_btn = pay_button_texts.get(
            user_lang, pay_button_texts.get("ua", pay_button_texts["en"])
        )

        # 1 CLICK = STRIPE: create session here and show URL button (no callback "pay_" that required second click)
        # Idempotency: do NOT create new checkout if order is already PROCESSING (payment check in progress)
        checkout_url = None
        if order_id_for_payment:
            try:
                import config
                from handlers.stripe_handler import get_stripe_handler
                from backend.database import OrderStatus

                db = get_db()
                order_row = (
                    db.get_order(order_id_for_payment)
                    if hasattr(db, "get_order")
                    else None
                )
                if (
                    order_row
                    and (order_row.get("status") or "").strip().lower()
                    == OrderStatus.PROCESSING.value
                ):
                    # Payment is already in progress — show informational message, not silence
                    logger.info(
                        "PAYMENT_PROCESSING_ALREADY user_id=%s order_id=%s",
                        user_id, order_id_for_payment,
                    )
                    _proc_texts = {
                        "uk": "⏳ Ваш платіж обробляється. Зачекайте кілька секунд та перевірте ще раз.",
                        "en": "⏳ Your payment is being processed. Please wait a moment and check again.",
                        "de": "⏳ Ihre Zahlung wird verarbeitet. Bitte warten Sie einen Moment.",
                        "pl": "⏳ Twoja płatność jest przetwarzana. Poczekaj chwilę i sprawdź ponownie.",
                        "tr": "⏳ Ödemeniz işleniyor. Lütfen bir an bekleyin.",
                        "ar": "⏳ جارٍ معالجة دفعتك. يرجى الانتظار لحظة.",
                    }
                    try:
                        await callback_query.answer(
                            _proc_texts.get(user_lang, _proc_texts["en"]),
                            show_alert=True,
                        )
                    except Exception:
                        pass
                    return
                stripe = get_stripe_handler()
                webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
                success_url = f"{webapp_url}/payment-success?order_id={order_id_for_payment}&lang={user_lang}"
                cancel_url = f"{webapp_url}/payment-cancel?order_id={order_id_for_payment}&lang={user_lang}"
                logger.info(
                    "STRIPE_SESSION_CREATED | order_id=%s success_url=%s",
                    order_id_for_payment,
                    success_url,
                )
                discount = (
                    order_row.get("discount", 0) if isinstance(order_row, dict) else 0
                )
                promo_code = (
                    order_row.get("promo_code") if isinstance(order_row, dict) else None
                )
                _customer_email_for_stripe = (answers.get("email") or "").strip() or None
                result = await stripe.create_checkout_session(
                    order_id=order_id_for_payment,
                    user_id=user_id,
                    doc_type=doc_type,
                    price=price,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    discount=discount,
                    promo_code=promo_code,
                    user_lang=user_lang,
                    customer_email=_customer_email_for_stripe,
                )
                if result.success:
                    db.update_order_status(
                        order_id_for_payment,
                        OrderStatus.PENDING,
                        stripe_session_id=result.session_id,
                    )
                    if hasattr(db, "create_payment"):
                        db.create_payment(
                            order_id_for_payment, user_id, price, result.session_id
                        )
                    checkout_url = result.checkout_url
                    logger.info(
                        "PAYMENT_CHECKOUT_CREATED | order_id=%s user_id=%s doc_type=%s"
                        " amount=%.2f session_id=%s checkout_url=%s",
                        order_id_for_payment,
                        user_id,
                        doc_type,
                        price,
                        result.session_id,
                        checkout_url,
                    )
                    logger.info(
                        "PAYMENT_URL_CREATED user_id=%s order_id=%s url_len=%d",
                        user_id, order_id_for_payment, len(checkout_url or ""),
                    )
                else:
                    logger.error(
                        "STRIPE_CHECKOUT_FAILED | order_id=%s error=%s",
                        order_id_for_payment,
                        result.error,
                    )
            except Exception:
                logger.error(
                    "STRIPE_CHECKOUT_EXCEPTION | order_id=%s",
                    order_id_for_payment,
                    exc_info=True,
                )

        _stripe_fail_texts = {
            "uk": "⚠️ Не вдалося створити платіжну сесію. Спробуйте ще раз.",
            "ua": "⚠️ Не вдалося створити платіжну сесію. Спробуйте ще раз.",
            "en": "⚠️ Could not create a payment session. Please try again.",
            "de": "⚠️ Zahlungssitzung konnte nicht erstellt werden. Bitte versuchen Sie es erneut.",
            "pl": "⚠️ Nie udało się utworzyć sesji płatności. Spróbuj ponownie.",
            "tr": "⚠️ Ödeme oturumu oluşturulamadı. Lütfen tekrar deneyin.",
            "ar": "⚠️ تعذّر إنشاء جلسة الدفع. يرجى المحاولة مرة أخرى.",
        }
        _retry_btn_texts = {
            "uk": "🔁 Спробувати ще раз",
            "ua": "🔁 Спробувати ще раз",
            "en": "🔁 Try again",
            "de": "🔁 Erneut versuchen",
            "pl": "🔁 Spróbuj ponownie",
            "tr": "🔁 Tekrar dene",
            "ar": "🔁 حاول مرة أخرى",
        }

        from backend.translations import ui as _ui
        if checkout_url:
            kb.add(InlineKeyboardButton(text=pay_btn, url=checkout_url))
            # Stripe sessions expire after 24 h. If the user returns later and
            # the URL is dead, this callback creates a fresh session silently.
            kb.add(InlineKeyboardButton(
                text=_ui("refresh_payment", user_lang),
                callback_data=f"final_pdf_{doc_type}",
            ))
        elif order_id_for_payment:
            # Stripe session could not be created — inform user and offer a retry.
            payment_text += "\n\n" + _ui("payment_session_failed", user_lang)
            kb.add(
                InlineKeyboardButton(
                    text=_ui("try_again", user_lang),
                    callback_data="show_post_form_menu",
                )
            )
        else:
            payment_text += "\n\n⚠️ Payment system is temporarily unavailable. Please contact support."

        _paywall_back = {
            "uk": "⬅️ Назад",
            "ua": "⬅️ Назад",
            "en": "⬅️ Back",
            "de": "⬅️ Zurück",
            "pl": "⬅️ Wstecz",
            "tr": "⬅️ Geri",
            "ar": "⬅️ رجوع",
        }
        kb.add(
            InlineKeyboardButton(
                text=_paywall_back.get(user_lang, _paywall_back["en"]),
                callback_data="show_post_form_menu",
            )
        )
        from handlers.nav import nav_home_text
        kb.add(
            InlineKeyboardButton(
                text=nav_home_text(user_lang),
                callback_data="main_menu",
            )
        )

        await callback_query.message.answer(
            payment_text, parse_mode="HTML", reply_markup=kb
        )
        return

    # Тільки якщо is_paid=True (є замовлення з status=PAID/SENT/DOWNLOADED; stripe_session_id не потрібен для доставки).
    # Full PDF доставляється лише після Stripe webhook; тут — лише «надіслати документ знову».
    logger.info(
        f"PAID_STATE user_id={user_id} doc_type={doc_type} order_id={order_id} — showing resend"
    )
    resend_texts = {
        "uk": "✅ Ви вже оплатили цей документ. Натисніть нижче, щоб отримати PDF знову.",
        "ua": "✅ Ви вже оплатили цей документ. Натисніть нижче, щоб отримати PDF знову.",
        "en": "✅ You have already paid for this document. Tap below to get the PDF again.",
        "de": "✅ Sie haben dieses Dokument bereits bezahlt. Tippen Sie unten, um das PDF erneut zu erhalten.",
        "pl": "✅ Opłaciłeś już ten dokument. Naciśnij poniżej, aby ponownie otrzymać PDF.",
        "tr": "✅ Bu belgeyi zaten ödediniz. PDF'i tekrar almak için aşağıya dokunun.",
        "ar": "✅ لقد دفعت بالفعل مقابل هذا المستند. انقر أدناه للحصول على PDF مرة أخرى.",
    }
    resend_text = resend_texts.get(
        user_lang, resend_texts.get("ua", resend_texts["en"])
    )
    resend_btn_texts = {
        "uk": "📄 Надіслати документ знову",
        "ua": "📄 Надіслати документ знову",
        "en": "📄 Send document again",
        "de": "📄 Dokument erneut senden",
        "pl": "📄 Wyślij dokument ponownie",
        "tr": "📄 Belgeyi tekrar gönder",
        "ar": "📄 إرسال المستند مرة أخرى",
    }
    resend_btn = resend_btn_texts.get(
        user_lang, resend_btn_texts.get("ua", resend_btn_texts["en"])
    )
    kb_resend = InlineKeyboardMarkup(row_width=1)
    kb_resend.add(
        InlineKeyboardButton(text=resend_btn, callback_data=f"resend_doc_{order_id}")
    )
    from handlers.nav import nav_home_text
    kb_resend.add(
        InlineKeyboardButton(
            text=nav_home_text(user_lang),
            callback_data="main_menu",
        )
    )
    await callback_query.message.answer(resend_text, reply_markup=kb_resend)
    return


async def handle_resend_document(callback_query: types.CallbackQuery):
    """Resend full PDF after payment (only for paid orders). Callback protection: answer first."""
    await callback_query.answer()
    try:
        order_id = int(callback_query.data.split("_")[-1])
    except (IndexError, ValueError):
        user_id = callback_query.from_user.id if callback_query.from_user else None
        _inv_lang = _norm_lang(None, user_id)
        _inv_texts = {
            "uk": "❌ Невірний запит. Спробуйте ще раз.",
            "ua": "❌ Невірний запит. Спробуйте ще раз.",
            "en": "❌ Invalid request. Please try again.",
            "de": "❌ Ungültige Anfrage. Bitte versuchen Sie es erneut.",
            "pl": "❌ Nieprawidłowe żądanie. Spróbuj ponownie.",
            "tr": "❌ Geçersiz istek. Lütfen tekrar deneyin.",
            "ar": "❌ طلب غير صالح. يرجى المحاولة مرة أخرى.",
        }
        await callback_query.message.answer(_inv_texts.get(_inv_lang, _inv_texts["en"]))
        return
    user_id = callback_query.from_user.id
    user_lang = _norm_lang(None, user_id)
    from handlers.stripe_handler import deliver_document

    await deliver_document(callback_query.message, order_id, user_id, force_resend=True)
    sent_msg = {
        "uk": "✅ Документ надіслано.",
        "ua": "✅ Документ надіслано.",
        "en": "✅ Document sent.",
        "de": "✅ Dokument gesendet.",
        "pl": "✅ Dokument wysłany.",
        "tr": "✅ Belge gönderildi.",
        "ar": "✅ تم إرسال المستند.",
    }.get(user_lang, "✅ Document sent.")
    # Navigation after delivery — prevent dead-end
    from handlers.nav import make_nav_kb
    _nav_kb = make_nav_kb(user_lang, back_cb="back_to_main_menu")
    await callback_query.message.answer(sent_msg, reply_markup=_nav_kb)


async def handle_about_project(callback_query: types.CallbackQuery):
    """Show informational message about the project/service in user's language."""
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)

    if not _check_onboarding_complete(user_id):
        return

    user_lang = _norm_lang(None, user_id)

    text = _get_about_project_text(user_lang)
    kb = _make_back_inline_kb(user_lang)

    await callback_query.message.answer(text, parse_mode="HTML", reply_markup=kb)


async def handle_info_about_project(callback_query: types.CallbackQuery):
    """Handle info_about_project callback - same as about_project"""
    await handle_about_project(callback_query)


async def handle_edit_answers(callback_query: types.CallbackQuery):
    """Re-open WebApp for editing answers with same doc_type context."""
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)
    if not _check_onboarding_complete(user_id):
        return
    uid = _uid(user_id)
    pending = _get_latest_pending(user_id)
    doc_type: Optional[str] = pending.get("doc_type") if pending else None
    if not doc_type or doc_type == "unknown":
        user_lang = _norm_lang(None, user_id)
        re_select_texts = {
            "uk": "Оберіть документ з меню ще раз, щоб відкрити анкету.",
            "en": "Please select the document from the menu again to open the form.",
            "de": "Bitte wählen Sie das Dokument erneut aus dem Menü, um das Formular zu öffnen.",
            "pl": "Wybierz ponownie dokument z menu, aby otworzyć formularz.",
            "tr": "Formu açmak için lütfen menüden belgeyi tekrar seçin.",
            "ar": "يرجى اختيار المستند من القائمة مرة أخرى لفتح النموذج.",
        }
        await callback_query.message.answer(
            re_select_texts.get(user_lang, re_select_texts["uk"]),
            reply_markup=_make_back_inline_kb(user_lang),
        )
        return
    user_lang_raw: Optional[str] = pending.get("lang") or pending.get("user_lang")
    user_lang = _norm_lang(user_lang_raw, user_id)

    # Get saved answers to pre-fill the form when reopening
    saved_answers: Optional[Dict[str, Any]] = pending.get("answers")

    url = _webapp_url(doc_type, user_lang, saved_answers=saved_answers)

    if not url:
        logger.error(f"❌ WebApp URL is empty for user {user_id}, doc_type {doc_type}")
        return

    # CRITICAL: Get user language and use it for localization
    user_lang = _norm_lang(None, user_id)
    logger.info(f"UI_LANG={user_lang} doc_type={doc_type} key=opening_form_edit")

    opening_message = _get_opening_form_edit_message(doc_type, user_lang)

    # TASK 2: REMOVE "ПОЧАТИ ЗАПОВНЕННЯ" AFTER SUBMIT
    # Create inline keyboard with WebApp button and Back button
    # This replaces the large persistent ReplyKeyboard button with clean inline buttons
    # IMPORTANT: Use InlineKeyboard ONLY - never use ReplyKeyboard after form submission
    kb_webapp = _make_webapp_inline_kb(url, user_lang)
    from handlers.nav import nav_back_text, nav_home_text
    kb_webapp.add(InlineKeyboardButton(text=nav_back_text(user_lang), callback_data="back_to_main_menu"))
    kb_webapp.add(InlineKeyboardButton(text=nav_home_text(user_lang), callback_data="main_menu"))

    # CRITICAL: Use ReplyKeyboardRemove() to ensure no persistent keyboard appears
    await callback_query.message.answer(
        opening_message,
        reply_markup=kb_webapp,
    )


async def handle_back_to_main(callback_query: types.CallbackQuery):
    """Handle back to main menu button - restore full document menu."""
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)

    if not _check_onboarding_complete(user_id):
        return

    uid = _uid(user_id)
    _active = _get_latest_pending(user_id)
    if not _active or not _active.get("answers"):
        _cleanup_old_previews(exclude_user_id=uid)

    user_lang = _norm_lang(None, user_id)

    pending = _get_latest_pending(user_id)
    if pending and pending.get("answers"):
        doc_type = pending.get("doc_type", "document")
        continue_texts = {
            "en": f"🏠 <b>Main menu</b>\n\nYou have an unfinished form for {doc_type.upper()}.\n\nSelect a document:",
            "de": f"🏠 <b>Hauptmenü</b>\n\nSie haben ein unvollständiges Formular für {doc_type.upper()}.\n\nWählen Sie ein Dokument:",
            "uk": f"🏠 <b>Головне меню</b>\n\nУ вас є незавершена анкета для {doc_type.upper()}.\n\nОберіть документ:",
            "pl": f"🏠 <b>Menu główne</b>\n\nMasz niedokończony formularz dla {doc_type.upper()}.\n\nWybierz dokument:",
            "tr": f"🏠 <b>Ana menü</b>\n\n{doc_type.upper()} için tamamlanmamış bir formunuz var.\n\nBelge seçin:",
            "ar": f"🏠 <b>القائمة الرئيسية</b>\n\nلديك نموذج غير مكتمل لـ {doc_type.upper()}.\n\nاختر مستندًا:",
        }
        menu_text = continue_texts.get(user_lang, continue_texts["uk"])
    else:
        main_menu_texts = {
            "en": "🏠 <b>Main menu</b>\n\nSelect a document to continue:",
            "de": "🏠 <b>Hauptmenü</b>\n\nWählen Sie ein Dokument, um fortzufahren:",
            "uk": "🏠 <b>Головне меню</b>\n\nОберіть документ для продовження:",
            "pl": "🏠 <b>Menu główne</b>\n\nWybierz dokument, aby kontynuować:",
            "tr": "🏠 <b>Ana menü</b>\n\nDevam etmek için bir belge seçin:",
            "ar": "🏠 <b>القائمة الرئيسية</b>\n\nاختر مستندًا للمتابعة:",
        }
        menu_text = main_menu_texts.get(user_lang, main_menu_texts["uk"])

    await callback_query.message.answer(
        menu_text,
        parse_mode="HTML",
        reply_markup=_make_main_menu_kb(user_lang),
    )


async def handle_intro_continue_wrapper(callback_query: types.CallbackQuery):
    """Wrapper for intro_continue callback - delegates to start.py handler."""
    try:
        from handlers.start import handle_intro_continue

        await handle_intro_continue(callback_query)
    except ImportError:
        logger.error("❌ Cannot import handle_intro_continue from handlers.start")
        _ha = {
            "uk": "⚠️ Функція тимчасово недоступна",
            "en": "⚠️ Handler not available",
            "de": "⚠️ Funktion vorübergehend nicht verfügbar",
            "pl": "⚠️ Funkcja tymczasowo niedostępna",
            "tr": "⚠️ İşlev geçici olarak kullanılamıyor",
            "ar": "⚠️ الوظيفة غير متاحة مؤقتاً",
        }
        await callback_query.answer(
            _ha.get(_norm_lang(None, callback_query.from_user.id), _ha["en"]),
            show_alert=True,
        )


async def handle_category_selection_wrapper(callback_query: types.CallbackQuery):
    """Wrapper for category_* callbacks - delegates to start.py handler."""
    try:
        from handlers.start import handle_category_selection

        await handle_category_selection(callback_query)
    except ImportError:
        logger.error("❌ Cannot import handle_category_selection from handlers.start")
        _ha = {
            "uk": "⚠️ Функція тимчасово недоступна",
            "en": "⚠️ Handler not available",
            "de": "⚠️ Funktion vorübergehend nicht verfügbar",
            "pl": "⚠️ Funkcja tymczasowo niedostępna",
            "tr": "⚠️ İşlev geçici olarak kullanılamıyor",
            "ar": "⚠️ الوظيفة غير متاحة مؤقتاً",
        }
        await callback_query.answer(
            _ha.get(_norm_lang(None, callback_query.from_user.id), _ha["en"]),
            show_alert=True,
        )


def _build_post_form_confirmation_menu(
    doc_type: str, user_lang: str
) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Build the full post-form confirmation menu (text + inline keyboard).
    Used by:
    - handle_webapp_data (primary WEB_APP_DATA path)
    - show_post_form_menu (explicit callback)
    - process_doc_choice fallback (when form already completed).
    """
    # Get price for buttons — CRITICAL: never render €0.00
    from bot_config.pricing import PDF_PRICES as _PDF_PRICES

    price = _PDF_PRICES.get(doc_type)
    if price is None:
        logger.error("PRICE_MISSING_CRITICAL post-form menu: doc_type=%r", doc_type)
        price = None  # handled below in button label

    post_form_texts = {
        "uk": (
            "✅ Анкету успішно заповнено\n\n"
            "• Повний заповнений приклад документа\n"
            "• Посилання на офіційну форму\n"
            "• Інструкція з подачі\n\n"
            "⚠️ Це технічний генератор PDF, не юридична консультація. Перевірте документ перед подачею."
        ),
        "ua": (
            "✅ Анкету успішно заповнено\n\n"
            "• Повний заповнений приклад документа\n"
            "• Посилання на офіційну форму\n"
            "• Інструкція з подачі\n\n"
            "⚠️ Це технічний генератор PDF, не юридична консультація. Перевірте документ перед подачею."
        ),
        "en": (
            "✅ Form successfully completed\n\n"
            "• Fully filled document example\n"
            "• Link to the official form\n"
            "• Submission instructions\n\n"
            "⚠️ This is a PDF generation tool, not legal advice. Please verify the document before submission."
        ),
        "de": (
            "✅ Formular erfolgreich ausgefüllt\n\n"
            "• Vollständig ausgefülltes Dokumentenbeispiel\n"
            "• Link zum offiziellen Formular\n"
            "• Anleitung zur Einreichung\n\n"
            "⚠️ Dies ist ein PDF-Generator, keine Rechtsberatung. Bitte prüfen Sie das Dokument vor der Einreichung."
        ),
        "pl": (
            "✅ Formularz wypełniony pomyślnie\n\n"
            "• Pełny wypełniony przykład dokumentu\n"
            "• Link do oficjalnego formularza\n"
            "• Instrukcja składania\n\n"
            "⚠️ To narzędzie do generowania PDF, nie porada prawna. Sprawdź dokument przed złożeniem."
        ),
        "tr": (
            "✅ Form başarıyla tamamlandı\n\n"
            "• Tam doldurulmuş belge örneği\n"
            "• Resmi form bağlantısı\n"
            "• Sunma talimatları\n\n"
            "⚠️ Bu bir PDF oluşturma aracıdır, hukuki danışmanlık değildir. Lütfen belgeyi göndermeden önce kontrol edin."
        ),
        "ar": (
            "✅ تم ملء النموذج بنجاح\n\n"
            "• مثال كامل لمستند مملوء\n"
            "• رابط النموذج الرسمي\n"
            "• تعليمات التقديم\n\n"
            "⚠️ هذه أداة لإنشاء ملفات PDF وليست استشارة قانونية. يرجى التحقق من المستند قبل التقديم."
        ),
    }
    post_form_text = post_form_texts.get(
        user_lang, post_form_texts.get("ua", post_form_texts["en"])
    )

    kb = InlineKeyboardMarkup(row_width=1)

    # Single CTA button — never show €0.00
    if price is not None:
        payment_button_texts = {
            "uk": f"💳 Оплатити €{price:.2f}",
            "ua": f"💳 Оплатити €{price:.2f}",
            "en": f"💳 Pay €{price:.2f}",
            "de": f"💳 Bezahlen €{price:.2f}",
            "pl": f"💳 Zapłać €{price:.2f}",
            "tr": f"💳 Öde €{price:.2f}",
            "ar": f"💳 ادفع €{price:.2f}",
        }
        kb.add(
            InlineKeyboardButton(
                text=payment_button_texts.get(
                    user_lang,
                    payment_button_texts.get("ua", payment_button_texts["en"]),
                ),
                callback_data=f"final_pdf_{doc_type}",
            )
        )
    else:
        # Price missing — show support button instead of broken pay button
        _no_price = {
            "uk": "⚠️ Ціна недоступна — зверніться до підтримки",
            "ua": "⚠️ Ціна недоступна — зверніться до підтримки",
            "en": "⚠️ Price unavailable — contact support",
            "de": "⚠️ Preis nicht verfügbar — Support kontaktieren",
            "pl": "⚠️ Cena niedostępna — skontaktuj się z pomocą",
            "tr": "⚠️ Fiyat mevcut değil — desteğe başvurun",
            "ar": "⚠️ السعر غير متاح — تواصل مع الدعم",
        }
        kb.add(
            InlineKeyboardButton(
                text=_no_price.get(user_lang, _no_price["en"]),
                callback_data="contact_support",
            )
        )

    back_button_texts = {
        "uk": "✏️ Виправити анкету",
        "ua": "✏️ Виправити анкету",
        "en": "✏️ Edit form",
        "de": "✏️ Formular bearbeiten",
        "pl": "✏️ Popraw ankietę",
        "tr": "✏️ Formu düzenle",
        "ar": "✏️ تعديل النموذج",
    }
    kb.add(
        InlineKeyboardButton(
            text=back_button_texts.get(
                user_lang, back_button_texts.get("ua", back_button_texts["en"])
            ),
            callback_data="edit_answers",
        )
    )

    return post_form_text, kb


async def show_post_form_menu(callback_query: types.CallbackQuery):
    """
    Show the full post-form confirmation menu.
    This is called when user presses "Continue" after WebApp data is saved.
    """
    await callback_query.answer()
    uid = _uid(callback_query.from_user.id)
    pending = _get_latest_pending(uid)
    if not pending or not pending.get("doc_type") or not pending.get("answers"):
        error_texts = {
            "uk": "⚠️ Дані не знайдено. Будь ласка, заповніть анкету ще раз.",
            "en": "⚠️ Data not found. Please fill out the form again.",
            "de": "⚠️ Daten nicht gefunden. Bitte füllen Sie das Formular erneut aus.",
            "pl": "⚠️ Nie znaleziono danych. Proszę wypełnić formularz ponownie.",
            "tr": "⚠️ Veri bulunamadı. Lütfen formu tekrar doldurun.",
            "ar": "⚠️ لم يتم العثور على البيانات. يرجى ملء النموذج مرة أخرى.",
        }
        user_lang = _norm_lang(None, uid)
        error_text = error_texts.get(user_lang, error_texts["uk"])

        await callback_query.message.answer(error_text)

        doc_type = pending.get("doc_type") if pending else "anmeldung"
        url = _webapp_url(doc_type, user_lang)
        if url:
            kb = _make_webapp_inline_kb(url, user_lang)
            reopen_texts = {
                "uk": "Відкрити анкету ще раз:",
                "en": "Open form again:",
                "de": "Formular erneut öffnen:",
                "pl": "Otwórz formularz ponownie:",
                "tr": "Formu tekrar aç:",
                "ar": "افتح النموذج مرة أخرى:",
            }
            await callback_query.message.answer(
                reopen_texts.get(user_lang, reopen_texts["uk"]), reply_markup=kb
            )
        return
    doc_type = pending.get("doc_type")
    user_lang = pending.get("user_lang") or pending.get("lang") or _norm_lang(None, uid)
    post_form_text, kb = _build_post_form_confirmation_menu(doc_type, user_lang)
    await callback_query.message.answer(post_form_text, reply_markup=kb)
    from aiogram import types


import json
import logging

logger = logging.getLogger(__name__)


async def _handle_webapp_data_legacy(message: types.Message):
    logger.warning("🔥 WEB_APP_DATA HANDLER TRIGGERED")

    try:
        raw = message.web_app_data.data
        logger.warning(f"RAW DATA: {raw}")

        data = json.loads(raw)

        doc_type = data.get("doc_type")
        lang = data.get("lang")
        user_answers = data.get("user_answers", {})

        logger.warning(
            "PARSED WEBAPP_DATA doc_type=%s lang=%s fields=%s",
            doc_type,
            lang,
            list(user_answers.keys()),
        )

        _recv = {
            "uk": "✅ Дані отримано",
            "en": "✅ Data received",
            "de": "✅ Daten empfangen",
            "pl": "✅ Dane otrzymane",
            "tr": "✅ Veri alındı",
            "ar": "✅ تم استلام البيانات",
        }
        _ul = _norm_lang(lang) if lang else "uk"
        await message.answer(
            f"{_recv.get(_ul, _recv['en'])}\n"
            f"Документ: {doc_type}\n"
            f"Полів: {len(user_answers)}"
        )

    except Exception:
        logger.exception("❌ WEB_APP_DATA ERROR")
        _err = {
            "uk": "❌ Помилка обробки WebApp даних",
            "en": "❌ WebApp data processing error",
            "de": "❌ WebApp-Datenverarbeitungsfehler",
            "pl": "❌ Błąd przetwarzania danych WebApp",
            "tr": "❌ WebApp veri işleme hatası",
            "ar": "❌ خطأ في معالجة بيانات WebApp",
        }
        _ul2 = "uk"
        try:
            _ul2 = _norm_lang(None, message.from_user.id)
        except Exception:
            pass
        await message.answer(_err.get(_ul2, _err["en"]))


async def handle_bundle_doc_termin(callback_query: types.CallbackQuery):
    """
    User tapped 'Bundle: Document + Termin 24/7'.

    Creates a Stripe checkout session at the bundle price.
    After successful payment bot.py activates:
      – PDF generation (doc order)
      – Termin monitoring (termin entitlement)
    The metadata key `order_type = "bundle"` signals this to bot.py.
    """
    await callback_query.answer()
    user_id = _uid(callback_query.from_user.id)
    doc_type: str = callback_query.data.replace("bundle_doc_termin_", "") or "unknown"
    pending = _PENDING_PREVIEWS.get((user_id, doc_type))
    if not pending:
        return

    user_lang_raw = pending.get("lang") or pending.get("user_lang")
    user_lang = _norm_lang(user_lang_raw, user_id)

    # Compute bundle price the same way the keyboard did
    _doc_price: float = 0.0
    try:
        _prices_map = _get_doc_prices()
        _doc_price = float(_prices_map.get(doc_type, 0) or 0)
    except Exception:
        pass
    _TERMIN_STANDALONE = 4.99
    _bundle_price = round(_doc_price + _TERMIN_STANDALONE * 0.75, 2) if _doc_price else 0.0

    if _bundle_price <= 0:
        # No price — fall back to regular document payment
        fake_cb = callback_query
        fake_cb.data = f"final_pdf_{doc_type}"
        await handle_final_pdf(fake_cb)
        return

    # Create or reuse order with bundle metadata
    try:
        db = get_db()
        answers = pending.get("answers") or {}
        import json as _json

        order_id_for_bundle = pending.get("bundle_order_id")
        if not order_id_for_bundle:
            order_id_for_bundle = db.create_order(
                user_id=user_id,
                doc_type=doc_type,
                amount=_bundle_price,
                user_data=_json.dumps(answers, ensure_ascii=False),
                lang=user_lang,
            )
            pending["bundle_order_id"] = order_id_for_bundle
            logger.info(
                "BUNDLE_ORDER_CREATED | order_id=%s user=%s doc=%s price=%.2f",
                order_id_for_bundle, user_id, doc_type, _bundle_price,
            )

        stripe = get_stripe_handler()
        webapp_url = os.getenv("WEBAPP_URL", "").split("/form")[0].rstrip("/")
        success_url = f"{webapp_url}/payment-success?order_id={order_id_for_bundle}&lang={user_lang}"
        cancel_url  = f"{webapp_url}/payment-cancel?order_id={order_id_for_bundle}&lang={user_lang}"

        _bundle_customer_email = (answers.get("email") or "").strip() or None
        result = await stripe.create_checkout_session(
            order_id=order_id_for_bundle,
            user_id=user_id,
            doc_type=doc_type,
            price=_bundle_price,
            success_url=success_url,
            cancel_url=cancel_url,
            user_lang=user_lang,
            customer_email=_bundle_customer_email,
            extra_metadata={"bundle": "true"},
        )

        if result.success:
            from backend.database import OrderStatus
            db.update_order_status(
                order_id_for_bundle,
                OrderStatus.PENDING,
                stripe_session_id=result.session_id,
            )
            # Send pay button to user
            _pay_texts = {
                "uk": f"📅 Комплект: Документ + Termin 24/7 — €{_bundle_price:.2f}\n\nОплата включає:\n• Заповнений документ\n• Моніторинг Termin протягом 24 год",
                "ua": f"📅 Комплект: Документ + Termin 24/7 — €{_bundle_price:.2f}\n\nОплата включає:\n• Заповнений документ\n• Моніторинг Termin протягом 24 год",
                "en": f"📅 Bundle: Document + Termin 24/7 — €{_bundle_price:.2f}\n\nIncludes:\n• Filled document\n• Termin monitoring for 24 hours",
                "de": f"📅 Bundle: Dokument + Termin 24/7 — €{_bundle_price:.2f}\n\nEnthält:\n• Ausgefülltes Dokument\n• Terminüberwachung für 24 Stunden",
                "pl": f"📅 Pakiet: Dokument + Termin 24/7 — €{_bundle_price:.2f}\n\nZawiera:\n• Wypełniony dokument\n• Monitoring Termin przez 24 godziny",
                "tr": f"📅 Paket: Belge + Termin 24/7 — €{_bundle_price:.2f}\n\nİçerir:\n• Doldurulmuş belge\n• 24 saat Termin takibi",
                "ar": f"📅 حزمة: مستند + Termin 24/7 — €{_bundle_price:.2f}\n\nيشمل:\n• المستند المملوء\n• مراقبة Termin لمدة 24 ساعة",
            }
            _pay_btn_texts = {
                "uk": f"💳 Оплатити €{_bundle_price:.2f}",
                "ua": f"💳 Оплатити €{_bundle_price:.2f}",
                "en": f"💳 Pay €{_bundle_price:.2f}",
                "de": f"💳 Zahlen €{_bundle_price:.2f}",
                "pl": f"💳 Zapłać €{_bundle_price:.2f}",
                "tr": f"💳 Öde €{_bundle_price:.2f}",
                "ar": f"💳 ادفع €{_bundle_price:.2f}",
            }
            _kb = InlineKeyboardMarkup(row_width=1)
            _kb.add(InlineKeyboardButton(
                text=_pay_btn_texts.get(user_lang, _pay_btn_texts["en"]),
                url=result.checkout_url,
            ))
            await callback_query.message.answer(
                _pay_texts.get(user_lang, _pay_texts["en"]),
                reply_markup=_kb,
            )
            logger.info(
                "BUNDLE_CHECKOUT_CREATED | order=%s user=%s price=%.2f url=%s",
                order_id_for_bundle, user_id, _bundle_price, result.checkout_url,
            )
        else:
            logger.error("BUNDLE_CHECKOUT_FAILED | order=%s err=%s", order_id_for_bundle, result.error)

    except Exception:
        logger.error("BUNDLE_HANDLER_ERROR | user=%s doc=%s", user_id, doc_type, exc_info=True)


def register_docs_handlers(dp: "types.Dispatcher"):
    """Register handlers (aiogram 2.x). Call this from bot.py after dp is created.
    NOTE: intro_continue and category_* are handled by start.py — NOT registered here.
    """
    import logging as _lg

    _lg.getLogger(__name__).warning("DOCS_DISPATCHER_ID=%s", id(dp))

    # WEB_APP_DATA handler (REQUIRED)

    logger.info("✅ WEB_APP_DATA handler registered in docs_new")

    dp.register_message_handler(cmd_testpdf, commands=["testpdf"])

    # intro_continue → handled by start.py (handle_intro_continue)
    # category_*    → handled by start.py (handle_category_selection)
    # DO NOT register duplicates here.

    # Register doc_* handlers - handles doc_anmeldung, doc_aufenthaltstitel, etc.
    # CRITICAL: This must match doc_anmeldung, doc_aufenthaltstitel, etc.
    dp.register_callback_query_handler(
        process_doc_choice, lambda c: c.data and c.data.startswith("doc_"), state="*"
    )
    dp.register_callback_query_handler(
        handle_start_form,
        lambda c: c.data and c.data.startswith("start_form_"),
        state="*",
    )
    logger.info("✅ Registered handler for doc_* and start_form_* callbacks")
    dp.register_callback_query_handler(
        authority_use_auto, lambda c: c.data and c.data == "auth_use_auto", state="*"
    )
    dp.register_callback_query_handler(
        authority_manual, lambda c: c.data and c.data == "auth_manual", state="*"
    )
    dp.register_callback_query_handler(
        handle_generate_preview_pdf,
        lambda c: c.data and c.data == "generate_preview_pdf",
        state="*",
    )
    # state="*" is required on ALL post-form handlers so they fire even when the user
    # has a leftover FSM state from a previous flow (e.g. Termin, old-style Anmeldung).
    # Without it, _catch_all_callback intercepts the callback and the button "does nothing".
    dp.register_callback_query_handler(
        handle_consent_accept,
        lambda c: c.data and c.data.startswith("consent_accept_"),
        state="*",
    )
    dp.register_callback_query_handler(
        handle_final_pdf,
        lambda c: c.data and c.data.startswith("final_pdf_"),
        state="*",
    )
    dp.register_callback_query_handler(
        handle_bundle_doc_termin,
        lambda c: c.data and c.data.startswith("bundle_doc_termin_"),
        state="*",
    )
    dp.register_callback_query_handler(
        handle_resend_document,
        lambda c: c.data and c.data.startswith("resend_doc_"),
        state="*",
    )
    dp.register_callback_query_handler(
        handle_edit_answers,
        lambda c: c.data and c.data == "edit_answers",
        state="*",
    )
    dp.register_callback_query_handler(
        show_post_form_menu,
        lambda c: c.data and c.data == "show_post_form_menu",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_about_project,
        lambda c: c.data and c.data == "about_project",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_info_about_project,
        lambda c: c.data and c.data == "info_about_project",
        state="*",
    )
    # Backward-compat: old cached messages may still send back_to_main
    dp.register_callback_query_handler(
        handle_back_to_main,
        lambda c: c.data and c.data == "back_to_main",
        state="*",
    )

    logger.info("✅ docs_new handlers registered")
