"""
Spain Test Bot — service selection + on-demand appointment checker.

Flow (new UX):
  Service tapped → ACTION SCREEN (city + service + choice buttons)
  [🔎 Check now]  → run checker → show result
  [🎯 1 / 🔥 3 / 🚀 5 citas] → payment flow
  [💬 Support]    → support contact
  [◀️ Back]       → back to services

Services:
  1. svc_nie         — NIE / TIE (Extranjería)        [top 3]
  2. svc_renovacion  — Renovación de residencia        [top 3]
  3. svc_huellas     — Toma de huellas                 [top 3]
  4. svc_autorizacion — Autorización de regreso        [extra]
  5. svc_certificados — Certificados / Otros           [extra]

callback_data: svc_nie / svc_renovacion / svc_huellas / svc_autorizacion / svc_certificados
               more_services   (reads city from FSM)
               back_to_cities  (returns to city selection)
               check_now       (manual checker trigger)
               support         (contact support)
"""

from __future__ import annotations

import logging

from aiogram import types
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.lang_store import get_lang

logger = logging.getLogger(__name__)


# ── Service definitions ────────────────────────────────────────────────────────
# key → {lang: display_name}  +  checker_authority (maps to spain_checker keys)

SERVICES: dict[str, dict] = {
    "nie": {
        "labels": {
            "es": "🪪 NIE / TIE — Extranjería",
            "en": "🪪 NIE / TIE — Immigration",
            "uk": "🪪 NIE / TIE — Відомство у справах іноземців",
            "pl": "🪪 NIE / TIE — Urząd ds. cudzoziemców",
            "ro": "🪪 NIE / TIE — Imigrație",
            "ar": "🪪 NIE / TIE — هيئة الأجانب",
        },
        "authority": "nie",
        "top3": True,
    },
    "renovacion": {
        "labels": {
            "es": "🔄 Renovación de residencia",
            "en": "🔄 Residence renewal",
            "uk": "🔄 Поновлення виду на проживання",
            "pl": "🔄 Odnowienie zezwolenia na pobyt",
            "ro": "🔄 Reînnoire rezidență",
            "ar": "🔄 تجديد الإقامة",
        },
        "authority": "residencia",
        "top3": True,
    },
    "huellas": {
        "labels": {
            "es": "🖐 Toma de huellas",
            "en": "🖐 Fingerprinting",
            "uk": "🖐 Зняття відбитків пальців",
            "pl": "🖐 Pobieranie odcisków palców",
            "ro": "🖐 Amprente digitale",
            "ar": "🖐 أخذ البصمات",
        },
        "authority": "extranjeria",
        "top3": True,
    },
    "autorizacion": {
        "labels": {
            "es": "✈️ Autorización de regreso",
            "en": "✈️ Return authorization",
            "uk": "✈️ Дозвіл на повернення",
            "pl": "✈️ Zezwolenie na powrót",
            "ro": "✈️ Autorizație de întoarcere",
            "ar": "✈️ تصريح العودة",
        },
        "authority": "extranjeria",
        "top3": False,
    },
    "certificados": {
        "labels": {
            "es": "📋 Certificados / Otros trámites",
            "en": "📋 Certificates / Other services",
            "uk": "📋 Довідки / Інші послуги",
            "pl": "📋 Zaświadczenia / Inne usługi",
            "ro": "📋 Certificate / Alte servicii",
            "ar": "📋 شهادات / خدمات أخرى",
        },
        "authority": "extranjeria",
        "top3": False,
    },
}

# ── City display names (short, for messages) ──────────────────────────────────
_CITY_NAMES: dict[str, dict[str, str]] = {
    "barcelona":  {"es": "Barcelona",  "en": "Barcelona",  "uk": "Барселона",  "pl": "Barcelona",  "ro": "Barcelona",  "ar": "برشلونة"},
    "madrid":     {"es": "Madrid",     "en": "Madrid",     "uk": "Мадрид",     "pl": "Madryt",     "ro": "Madrid",     "ar": "مدريد"},
    "valencia":   {"es": "Valencia",   "en": "Valencia",   "uk": "Валенсія",   "pl": "Walencja",   "ro": "Valencia",   "ar": "بلنسية"},
    "sevilla":    {"es": "Sevilla",    "en": "Seville",    "uk": "Севілья",    "pl": "Sewilla",    "ro": "Sevilla",    "ar": "إشبيلية"},
    "malaga":     {"es": "Málaga",     "en": "Málaga",     "uk": "Малага",     "pl": "Malaga",     "ro": "Málaga",     "ar": "مالقة"},
}

# ── UI text dicts (all 6 langs) ───────────────────────────────────────────────

_SERVICE_HEADER: dict[str, str] = {
    "es": "📄 <b>Selecciona el trámite</b>\n\n📍 {city}\n\nElige el tipo de cita que necesitas:",
    "en": "📄 <b>Select service</b>\n\n📍 {city}\n\nChoose the type of appointment you need:",
    "uk": "📄 <b>Оберіть послугу</b>\n\n📍 {city}\n\nВибери тип запису:",
    "pl": "📄 <b>Wybierz usługę</b>\n\n📍 {city}\n\nWybierz typ wizyty:",
    "ro": "📄 <b>Selectează serviciul</b>\n\n📍 {city}\n\nAlege tipul de programare:",
    "ar": "📄 <b>اختر الخدمة</b>\n\n📍 {city}\n\nاختر نوع الموعد الذي تحتاجه:",
}

_BTN_MORE: dict[str, str] = {
    "es": "➕ Más trámites",
    "en": "➕ More services",
    "uk": "➕ Більше послуг",
    "pl": "➕ Więcej usług",
    "ro": "➕ Mai multe servicii",
    "ar": "➕ خدمات إضافية",
}

_BTN_BACK_CITIES: dict[str, str] = {
    "es": "◀️ Cambiar ciudad",
    "en": "◀️ Change city",
    "uk": "◀️ Змінити місто",
    "pl": "◀️ Zmień miasto",
    "ro": "◀️ Schimbă orașul",
    "ar": "◀️ تغيير المدينة",
}

# ── Action screen (shown immediately after service selection) ──────────────────

_ACTION_SCREEN: dict[str, str] = {
    "es": (
        "📍 <b>{city}</b>\n"
        "📄 <b>{service}</b>\n\n"
        "❗ Las citas aparecen de forma aleatoria y desaparecen en 1–3 minutos\n"
        "👥 Usuarios ya encuentran citas a diario con nuestro bot\n\n"
        "⏱ Revisamos las citas cada 30–60 segundos\n"
        "📲 En cuanto aparezca una cita — te avisaremos al instante\n"
        "🎯 <b>Planes:</b>\n"
        "• 1 cita — €6.99\n"
        "• 3 citas — €14.99  ✅ Recomendado\n"
        "• 5 citas — €24.99  💎 Máxima probabilidad\n\n"
        "🤖 El bot funciona automáticamente 24/7\n"
        "ℹ️ No garantizamos una cita — aumentamos tus probabilidades\n\n"
        "¿Qué quieres hacer?"
    ),
    "en": (
        "📍 <b>{city}</b>\n"
        "📄 <b>{service}</b>\n\n"
        "❗ Appointments appear randomly and disappear within 1–3 minutes\n"
        "👥 Users are already finding citas daily with our bot\n\n"
        "⏱ We check every 30–60 seconds\n"
        "📲 As soon as an appointment appears — you get notified instantly\n"
        "🎯 <b>Plans:</b>\n"
        "• 1 appointment — €6.99\n"
        "• 3 appointments — €14.99  ✅ Recommended\n"
        "• 5 appointments — €24.99  💎 Maximum chance\n\n"
        "🤖 Bot works automatically 24/7\n"
        "ℹ️ We do not guarantee a booking — we increase your chances\n\n"
        "What would you like to do?"
    ),
    "uk": (
        "📍 <b>{city}</b>\n"
        "📄 <b>{service}</b>\n\n"
        "❗ Записи з'являються випадково і зникають за 1–3 хвилини\n"
        "👥 Користувачі вже знаходять citas щодня через наш бот\n\n"
        "⏱ Перевіряємо кожні 30–60 секунд\n"
        "📲 Як тільки з'явиться запис — ти одразу отримаєш повідомлення\n"
        "🎯 <b>Тарифи:</b>\n"
        "• 1 запис — €6.99\n"
        "• 3 записи — €14.99  ✅ Рекомендується\n"
        "• 5 записів — €24.99  💎 Максимальний шанс\n\n"
        "🤖 Бот працює автоматично 24/7\n"
        "ℹ️ Ми не гарантуємо запис — ми збільшуємо твої шанси\n\n"
        "Що хочеш зробити?"
    ),
    "pl": (
        "📍 <b>{city}</b>\n"
        "📄 <b>{service}</b>\n\n"
        "❗ Terminy pojawiają się losowo i znikają w ciągu 1–3 minut\n"
        "👥 Użytkownicy już codziennie znajdują citas przez naszego bota\n\n"
        "⏱ Sprawdzamy co 30–60 sekund\n"
        "📲 Gdy tylko pojawi się termin — natychmiast dostaniesz powiadomienie\n"
        "🎯 <b>Plany:</b>\n"
        "• 1 termin — €6.99\n"
        "• 3 terminy — €14.99  ✅ Polecane\n"
        "• 5 terminów — €24.99  💎 Maksymalne szanse\n\n"
        "🤖 Bot działa automatycznie 24/7\n"
        "ℹ️ Nie gwarantujemy wizyty — zwiększamy Twoje szanse\n\n"
        "Co chcesz zrobić?"
    ),
    "ro": (
        "📍 <b>{city}</b>\n"
        "📄 <b>{service}</b>\n\n"
        "❗ Programările apar aleatoriu și dispar în 1–3 minute\n"
        "👥 Utilizatori găsesc deja citas zilnic prin botul nostru\n\n"
        "⏱ Verificăm la fiecare 30–60 secunde\n"
        "📲 Imediat ce apare o programare — primești notificare\n"
        "🎯 <b>Planuri:</b>\n"
        "• 1 programare — €6.99\n"
        "• 3 programări — €14.99  ✅ Recomandat\n"
        "• 5 programări — €24.99  💎 Șanse maxime\n\n"
        "🤖 Botul funcționează automat 24/7\n"
        "ℹ️ Nu garantăm o programare — îți creștem șansele\n\n"
        "Ce vrei să faci?"
    ),
    "ar": (
        "📍 <b>{city}</b>\n"
        "📄 <b>{service}</b>\n\n"
        "❗ المواعيد تظهر بشكل عشوائي وتختفي خلال 1–3 دقائق\n"
        "👥 المستخدمون يجدون citas يوميًا عبر بوتنا\n\n"
        "⏱ نفحص كل 30–60 ثانية\n"
        "📲 بمجرد ظهور موعد — سيتم إشعارك فورًا\n"
        "🎯 <b>الخطط:</b>\n"
        "• موعد واحد — €6.99\n"
        "• 3 مواعيد — €14.99  ✅ موصى به\n"
        "• 5 مواعيد — €24.99  💎 أقصى فرصة\n\n"
        "🤖 البوت يعمل تلقائيًا 24/7\n"
        "ℹ️ نحن لا نضمن الموعد — بل نزيد فرصك\n\n"
        "ماذا تريد أن تفعل؟"
    ),
}

_BTN_CHECK_NOW: dict[str, str] = {
    "es": "🔎 Probar manualmente",
    "en": "🔎 Try manually",
    "uk": "🔎 Спробувати вручну",
    "pl": "🔎 Spróbuj ręcznie",
    "ro": "🔎 Încearcă manual",
    "ar": "🔎 جرّب يدويًا",
}

_BTN_PLAN_1CITA: dict[str, str] = {
    "es": "🎯 1 cita — €6.99",
    "en": "🎯 1 appointment — €6.99",
    "uk": "🎯 1 запис — €6.99",
    "pl": "🎯 1 termin — €6.99",
    "ro": "🎯 1 programare — €6.99",
    "ar": "🎯 موعد واحد — €6.99",
}

_BTN_PLAN_3CITAS: dict[str, str] = {
    "es": "🔥 3 citas — €14.99  ✅ Recomendado",
    "en": "🔥 3 appointments — €14.99  ✅ Recommended",
    "uk": "🔥 3 записи — €14.99  ✅ Рекомендується",
    "pl": "🔥 3 terminy — €14.99  ✅ Polecane",
    "ro": "🔥 3 programări — €14.99  ✅ Recomandat",
    "ar": "🔥 3 مواعيد — €14.99  ✅ موصى به",
}

_BTN_PLAN_5CITAS: dict[str, str] = {
    "es": "🚀 5 citas — €24.99  💎 Máxima probabilidad",
    "en": "🚀 5 appointments — €24.99  💎 Maximum chance",
    "uk": "🚀 5 записів — €24.99  💎 Максимальний шанс",
    "pl": "🚀 5 terminów — €24.99  💎 Maksymalne szanse",
    "ro": "🚀 5 programări — €24.99  💎 Șanse maxime",
    "ar": "🚀 5 مواعيد — €24.99  💎 أقصى فرصة",
}

_BTN_SUPPORT: dict[str, str] = {
    "es": "💬 Soporte",
    "en": "💬 Support",
    "uk": "💬 Підтримка",
    "pl": "💬 Wsparcie",
    "ro": "💬 Suport",
    "ar": "💬 الدعم",
}

_BTN_BACK_SVC: dict[str, str] = {
    "es": "◀️ Cambiar ciudad / trámite",
    "en": "◀️ Change city / service",
    "uk": "◀️ Змінити місто / послугу",
    "pl": "◀️ Zmień miasto / usługę",
    "ro": "◀️ Schimbă orașul / serviciul",
    "ar": "◀️ تغيير المدينة / الخدمة",
}

# ── Checking screen (shown during active search) ───────────────────────────────

_CHECKING: dict[str, str] = {
    "es": "🔍 <b>Comprobando citas disponibles…</b>\n\n📍 {city}\n📄 {service}\n\n⏱ Puede tardar hasta 10 segundos",
    "en": "🔍 <b>Checking available appointments (citas)…</b>\n\n📍 {city}\n📄 {service}\n\n⏱ This may take up to 10 seconds",
    "uk": "🔍 <b>Перевіряємо доступні записи (citas)…</b>\n\n📍 {city}\n📄 {service}\n\n⏱ Це може зайняти до 10 секунд",
    "pl": "🔍 <b>Sprawdzamy dostępne wizyty (citas)…</b>\n\n📍 {city}\n📄 {service}\n\n⏱ Może to potrwać do 10 sekund",
    "ro": "🔍 <b>Se verifică programările (citas) disponibile…</b>\n\n📍 {city}\n📄 {service}\n\n⏱ Poate dura până la 10 secunde",
    "ar": "🔍 <b>يجري التحقق من المواعيد المتاحة (citas)…</b>\n\n📍 {city}\n📄 {service}\n\n⏱ قد يستغرق هذا حتى 10 ثوانٍ",
}

# ── No appointments screen ─────────────────────────────────────────────────────

_NO_SLOTS: dict[str, str] = {
    "es": (
        "❌ <b>No hay citas disponibles en este momento</b>\n\n"
        "💡 Acabas de comprobarlo — pero las citas pueden aparecer\n"
        "en los próximos 30 segundos y desaparecer antes de que vuelvas a revisar\n\n"
        "🤖 Nuestro bot comprueba automáticamente cada 30–60 segundos\n"
        "📲 Y te avisa al instante — para que no te lo pierdas\n\n"
        "👉 Mientras tú revisas manualmente — otros ya lo hacen automáticamente"
    ),
    "en": (
        "❌ <b>No available appointments (citas) right now</b>\n\n"
        "💡 You just checked — but citas can appear in the next 30 seconds\n"
        "and disappear before you check again manually\n\n"
        "🤖 Our bot checks automatically every 30–60 seconds\n"
        "📲 And notifies you instantly — so you never miss one\n\n"
        "👉 While you check manually — others are already catching them automatically"
    ),
    "uk": (
        "❌ <b>Зараз немає вільних записів (citas)</b>\n\n"
        "💡 Ти тільки що перевірив — але citas можуть з'явитися\n"
        "вже за 30 секунд і зникнути до наступної ручної перевірки\n\n"
        "🤖 Наш бот перевіряє автоматично кожні 30–60 секунд\n"
        "📲 І повідомляє миттєво — щоб ти не пропустив\n\n"
        "👉 Поки ти перевіряєш вручну — інші вже ловлять їх автоматично"
    ),
    "pl": (
        "❌ <b>Brak dostępnych wizyt (citas) w tej chwili</b>\n\n"
        "💡 Właśnie sprawdziłeś — ale citas mogą pojawić się\n"
        "w ciągu 30 sekund i zniknąć zanim sprawdzisz ponownie\n\n"
        "🤖 Nasz bot sprawdza automatycznie co 30–60 sekund\n"
        "📲 I powiadamia natychmiast — żebyś nie przegapił\n\n"
        "👉 Podczas gdy Ty sprawdzasz ręcznie — inni robią to automatycznie"
    ),
    "ro": (
        "❌ <b>Nu există programări (citas) disponibile acum</b>\n\n"
        "💡 Tocmai ai verificat — dar citas pot apărea\n"
        "în 30 de secunde și dispărea înainte să verifici din nou\n\n"
        "🤖 Botul nostru verifică automat la fiecare 30–60 secunde\n"
        "📲 Și te anunță imediat — ca să nu ratezi nimic\n\n"
        "👉 În timp ce tu verifici manual — alții deja o fac automat"
    ),
    "ar": (
        "❌ <b>لا توجد مواعيد (citas) متاحة الآن</b>\n\n"
        "💡 لقد تحققت للتو — لكن citas قد تظهر\n"
        "خلال 30 ثانية وتختفي قبل أن تتحقق مرة أخرى\n\n"
        "🤖 يفحص بوتنا تلقائيًا كل 30–60 ثانية\n"
        "📲 ويُخطرك فوراً — حتى لا تفوتك الفرصة\n\n"
        "👉 بينما تتحقق يدويًا — الآخرون يفعلون ذلك تلقائيًا بالفعل"
    ),
}

_BTN_TRY_AGAIN: dict[str, str] = {
    "es": "🔎 Intentar de nuevo",
    "en": "🔎 Try again",
    "uk": "🔎 Спробувати ще раз",
    "pl": "🔎 Spróbuj ponownie",
    "ro": "🔎 Încearcă din nou",
    "ar": "🔎 حاول مرة أخرى",
}

# ── Appointment found screen ───────────────────────────────────────────────────

_FOUND_HEADER: dict[str, str] = {
    "es": "🔥 <b>¡Cita encontrada!</b>",
    "en": "🔥 <b>Appointment found!</b>",
    "uk": "🔥 <b>Запис знайдено!</b>",
    "pl": "🔥 <b>Znaleziono wizytę!</b>",
    "ro": "🔥 <b>Programare găsită!</b>",
    "ar": "🔥 <b>تم العثور على موعد!</b>",
}

_FOUND_URGENCY: dict[str, str] = {
    "es": "⚠️ <b>¡Actúa ya!</b> — puede desaparecer en 1–2 minutos",
    "en": "⚠️ <b>Act now!</b> — it may disappear within 1–2 minutes",
    "uk": "⚠️ <b>Дій зараз!</b> — може зникнути за 1–2 хвилини",
    "pl": "⚠️ <b>Działaj teraz!</b> — może zniknąć w ciągu 1–2 minut",
    "ro": "⚠️ <b>Acționează acum!</b> — poate dispărea în 1–2 minute",
    "ar": "⚠️ <b>تصرف الآن!</b> — قد يختفي خلال 1–2 دقيقة",
}

_FOUND_BOOK_BTN: dict[str, str] = {
    "es": "👉 Reservar ahora — antes de que desaparezca",
    "en": "👉 Book now — before it disappears",
    "uk": "👉 Записатись зараз — поки не зникло",
    "pl": "👉 Zarezerwuj teraz — zanim zniknie",
    "ro": "👉 Rezervă acum — înainte să dispară",
    "ar": "👉 احجز الآن — قبل أن يختفي",
}

# ── Support screen ─────────────────────────────────────────────────────────────

_SUPPORT_TEXT: dict[str, str] = {
    "es": "💬 <b>Soporte</b>\n\n💬 Contáctanos: @SpainCitasSupport",
    "en": "💬 <b>Support</b>\n\n💬 Contact support: @SpainCitasSupport",
    "uk": "💬 <b>Підтримка</b>\n\n💬 Напишіть нам: @SpainCitasSupport",
    "pl": "💬 <b>Wsparcie</b>\n\n💬 Napisz do nas: @SpainCitasSupport",
    "ro": "💬 <b>Suport</b>\n\n💬 Contactează-ne: @SpainCitasSupport",
    "ar": "💬 <b>الدعم</b>\n\n💬 تواصل مع الدعم: @SpainCitasSupport",
}

# ── Monitor upsell header (used in no-slots screen) ───────────────────────────

_MONITOR_UPSELL_HEADER: dict[str, str] = {
    "es": "🚀 <b>Activa la búsqueda automática:</b>",
    "en": "🚀 <b>Activate automatic search:</b>",
    "uk": "🚀 <b>Увімкни автоматичний пошук:</b>",
    "pl": "🚀 <b>Włącz automatyczne wyszukiwanie:</b>",
    "ro": "🚀 <b>Activează căutarea automată:</b>",
    "ar": "🚀 <b>فعّل البحث التلقائي:</b>",
}


def _t(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get("en") or next(iter(d.values()))


def _city_name(city_key: str, lang: str) -> str:
    return _t(_CITY_NAMES.get(city_key, {"en": city_key.title()}), lang)


# ── Service selection screen ──────────────────────────────────────────────────

async def show_services(
    message: types.Message,
    lang: str,
    city: str,
    show_all: bool = False,
) -> None:
    """Show top 3 services (+ More button) or all 5 when show_all=True."""
    city_display = _city_name(city, lang)
    header = _t(_SERVICE_HEADER, lang).format(city=city_display)

    kb = InlineKeyboardMarkup(row_width=1)

    for svc_key, svc in SERVICES.items():
        if not show_all and not svc["top3"]:
            continue
        kb.add(InlineKeyboardButton(
            _t(svc["labels"], lang),
            callback_data=f"svc_{svc_key}",
        ))

    if not show_all:
        kb.add(InlineKeyboardButton(_t(_BTN_MORE, lang), callback_data="more_services"))

    kb.add(InlineKeyboardButton(_t(_BTN_BACK_CITIES, lang), callback_data="back_to_cities"))

    await message.answer(header, parse_mode="HTML", reply_markup=kb)


# ── Action screen keyboard ────────────────────────────────────────────────────

def _action_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_PLAN_1CITA,  lang), callback_data="buy_1cita"))
    kb.add(InlineKeyboardButton(_t(_BTN_PLAN_3CITAS, lang), callback_data="buy_3citas"))
    kb.add(InlineKeyboardButton(_t(_BTN_PLAN_5CITAS, lang), callback_data="buy_5citas"))
    kb.add(InlineKeyboardButton(_t(_BTN_CHECK_NOW,   lang), callback_data="check_now"))
    kb.add(InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton(_t(_BTN_SUPPORT,     lang), callback_data="support"),
        InlineKeyboardButton(_t(_BTN_BACK_CITIES, lang), callback_data="back_to_cities"),
    ))
    return kb


# ── Callbacks ─────────────────────────────────────────────────────────────────

async def handle_more_services(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Expand to show all 5 services."""
    await callback.answer()
    lang = get_lang(callback.from_user.id)
    data = await state.get_data()
    city = data.get("city", "barcelona")

    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_services(callback.message, lang, city, show_all=True)


async def handle_back_to_cities(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return to city selection."""
    await callback.answer()
    lang = get_lang(callback.from_user.id)

    try:
        await callback.message.delete()
    except Exception:
        pass

    from handlers.city_select import show_city_selection
    await show_city_selection(callback.message, lang)


async def handle_service_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User tapped a service → show ACTION SCREEN (no automatic checker)."""
    await callback.answer()

    svc_key = callback.data.replace("svc_", "")
    if svc_key not in SERVICES:
        logger.warning("SERVICE_UNKNOWN | svc=%s", svc_key)
        return

    lang      = get_lang(callback.from_user.id)
    data      = await state.get_data()
    city      = data.get("city", "barcelona")
    authority = SERVICES[svc_key]["authority"]

    # Persist svc / authority so check_now and monitoring handlers can read them
    await state.update_data(svc=svc_key, authority=authority)

    city_display = _city_name(city, lang)
    svc_display  = _t(SERVICES[svc_key]["labels"], lang)

    logger.info(
        "SERVICE_SELECTED | user=%s city=%s svc=%s auth=%s lang=%s",
        callback.from_user.id, city, svc_key, authority, lang,
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    # ── Build action screen keyboard: paid plans first, free check below ─────
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(_t(_BTN_PLAN_1CITA,  lang), callback_data="buy_1cita"))
    kb.add(InlineKeyboardButton(_t(_BTN_PLAN_3CITAS, lang), callback_data="buy_3citas"))
    kb.add(InlineKeyboardButton(_t(_BTN_PLAN_5CITAS, lang), callback_data="buy_5citas"))
    kb.add(InlineKeyboardButton(_t(_BTN_CHECK_NOW,   lang), callback_data="check_now"))
    kb.row(
        InlineKeyboardButton(_t(_BTN_SUPPORT,     lang), callback_data="support"),
        InlineKeyboardButton(_t(_BTN_BACK_CITIES, lang), callback_data="back_to_cities"),
    )

    await callback.message.answer(
        _t(_ACTION_SCREEN, lang).format(city=city_display, service=svc_display),
        parse_mode="HTML",
        reply_markup=kb,
    )


async def handle_check_now(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User tapped [🔎 Check now] → run checker → show result."""
    await callback.answer()

    lang = get_lang(callback.from_user.id)
    data = await state.get_data()

    city      = data.get("city", "barcelona")
    svc_key   = data.get("svc", "")
    authority = data.get("authority", "")

    if not svc_key or svc_key not in SERVICES:
        logger.warning("CHECK_NOW_NO_SVC | user=%s", callback.from_user.id)
        return

    if not authority:
        authority = SERVICES[svc_key]["authority"]

    city_display = _city_name(city, lang)
    svc_display  = _t(SERVICES[svc_key]["labels"], lang)

    logger.info(
        "CHECK_NOW | user=%s city=%s svc=%s auth=%s",
        callback.from_user.id, city, svc_key, authority,
    )

    try:
        await callback.message.delete()
    except Exception:
        pass

    # Show "searching" progress message
    checking_msg = await callback.message.answer(
        _t(_CHECKING, lang).format(city=city_display, service=svc_display),
        parse_mode="HTML",
    )

    # ── Run checker ────────────────────────────────────────────────────────────
    result: list = []
    try:
        from utils.spain_checker import check_spain_termin
        result = await check_spain_termin(city, authority)
    except Exception as exc:
        logger.error("CHECK_NOW_ERROR | city=%s svc=%s err=%s", city, svc_key, exc)

    try:
        await checking_msg.delete()
    except Exception:
        pass

    # ── No appointments ────────────────────────────────────────────────────────
    if not result:
        no_slots_text = (
            _t(_NO_SLOTS, lang)
            + "\n\n"
            + _t(_MONITOR_UPSELL_HEADER, lang)
        )
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton(_t(_BTN_PLAN_1CITA,  lang), callback_data="buy_1cita"))
        kb.add(InlineKeyboardButton(_t(_BTN_PLAN_3CITAS, lang), callback_data="buy_3citas"))
        kb.add(InlineKeyboardButton(_t(_BTN_PLAN_5CITAS, lang), callback_data="buy_5citas"))
        kb.row(
            InlineKeyboardButton(_t(_BTN_TRY_AGAIN, lang), callback_data="check_now"),
            InlineKeyboardButton(_t(_BTN_SUPPORT,   lang), callback_data="support"),
        )
        kb.add(InlineKeyboardButton(_t(_BTN_BACK_SVC, lang), callback_data="back_to_cities"))
        await callback.message.answer(no_slots_text, parse_mode="HTML", reply_markup=kb)
        return

    # ── Appointments found ─────────────────────────────────────────────────────
    from utils.portal_instructions import get_portal_instructions
    instructions = get_portal_instructions(city, svc_key, lang)

    for i, slot in enumerate(result[:3], 1):
        date     = slot.get("date")     or "—"
        time_str = slot.get("time")     or "—"
        location = slot.get("location") or city_display
        url      = slot.get("url")      or ""

        slot_text = (
            f"{_t(_FOUND_HEADER, lang)}\n\n"
            f"📍 {location}\n"
            f"📄 {svc_display}\n"
            f"📅 {date}  ⏰ {time_str}\n\n"
            f"{_t(_FOUND_URGENCY, lang)}\n\n"
            f"{instructions}"
        )

        kb_slot = InlineKeyboardMarkup(row_width=1)
        if url:
            kb_slot.add(InlineKeyboardButton(_t(_FOUND_BOOK_BTN, lang), url=url))
        if i == len(result[:3]):
            kb_slot.row(
                InlineKeyboardButton(_t(_BTN_TRY_AGAIN, lang), callback_data="check_now"),
                InlineKeyboardButton(_t(_BTN_BACK_SVC,  lang), callback_data="back_to_cities"),
            )

        await callback.message.answer(
            slot_text,
            parse_mode="HTML",
            reply_markup=kb_slot,
            disable_web_page_preview=True,
        )


async def handle_support(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show support contact info."""
    await callback.answer()
    lang = get_lang(callback.from_user.id)
    await callback.message.answer(_t(_SUPPORT_TEXT, lang), parse_mode="HTML")


# ── Registration ──────────────────────────────────────────────────────────────

def register(dp: Dispatcher) -> None:
    dp.register_callback_query_handler(
        handle_service_selected,
        lambda c: c.data and c.data.startswith("svc_") and c.data[4:] in SERVICES,
        state="*",
    )
    dp.register_callback_query_handler(
        handle_more_services,
        lambda c: c.data == "more_services",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_back_to_cities,
        lambda c: c.data == "back_to_cities",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_check_now,
        lambda c: c.data == "check_now",
        state="*",
    )
    dp.register_callback_query_handler(
        handle_support,
        lambda c: c.data == "support",
        state="*",
    )
