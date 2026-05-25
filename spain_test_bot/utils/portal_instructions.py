"""
Spain Test Bot — portal booking instructions.

Provides step-by-step guidance shown to users right before they open the
official booking site, mirroring the German bot's guided-flow UX.

Structure:
  get_portal_instructions(city, service, lang) → str

All instructions are in {service_step} template format so the exact
service name is injected dynamically (always in Spanish, since the
site is always Spanish regardless of user language).

Portal types:
  GENERIC_ES   — default for all sede.gob.es flows (Extranjería, etc.)

City-specific overrides can be added to _CITY_PORTAL_MAP later.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ── Official service names (Spanish, as they appear on the website) ───────────
# Key = svc_key used throughout the bot
_SERVICE_LABEL: dict[str, str] = {
    "nie":          "NIE / TIE (Extranjería)",
    "renovacion":   "Renovación de Residencia",
    "huellas":      "Toma de Huellas",
    "autorizacion": "Autorización de Regreso",
    "certificados": "Certificados / Otros trámites",
}

# ── "Select:" prefix in each language ────────────────────────────────────────
_SELECT_PREFIX: dict[str, str] = {
    "es": "👉 SELECCIONA:",
    "en": "👉 SELECT:",
    "uk": "👉 ОБЕРІТЬ:",
    "pl": "👉 WYBIERZ:",
    "ro": "👉 SELECTEAZĂ:",
    "ar": "👉 اختر:",
}

# ── Per-portal step-by-step instructions ─────────────────────────────────────
# {service_step} is replaced dynamically with the localised select line
# (e.g. "👉 SELECT: NIE / TIE (Extranjería)")

_PORTAL_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "GENERIC_ES": {
        "es": (
            "👉 Ahora se abrirá el sitio oficial de citas:\n"
            "\n"
            "1. Haz clic en «Aceptar» <i>(cookies)</i>\n"
            "2. Selecciona tu provincia\n"
            "3. {service_step}\n"
            "4. Haz clic en «Aceptar»\n"
            "5. Elige la fecha y hora disponible\n"
            "6. Confirma tu cita\n"
            "\n"
            "⚠️ Actúa rápido — los huecos desaparecen en minutos"
        ),
        "en": (
            "👉 The official booking site is now opening:\n"
            "\n"
            "1. Click «Aceptar» <i>(accept cookies)</i>\n"
            "2. Select your province\n"
            "3. {service_step}\n"
            "4. Click «Aceptar»\n"
            "5. Choose an available date and time\n"
            "6. Confirm your appointment\n"
            "\n"
            "⚠️ Act fast — citas can disappear quickly"
        ),
        "uk": (
            "👉 Зараз відкриється офіційний сайт запису:\n"
            "\n"
            "1. Натисніть «Aceptar» <i>(прийняти cookies)</i>\n"
            "2. Оберіть провінцію\n"
            "3. {service_step}\n"
            "4. Натисніть «Aceptar»\n"
            "5. Виберіть доступну дату і час\n"
            "6. Підтвердіть запис\n"
            "\n"
            "⚠️ Дій швидко — записи (citas) зникають за хвилини"
        ),
        "pl": (
            "👉 Teraz otworzy się oficjalna strona rezerwacji:\n"
            "\n"
            "1. Kliknij «Aceptar» <i>(akceptuj cookies)</i>\n"
            "2. Wybierz prowincję\n"
            "3. {service_step}\n"
            "4. Kliknij «Aceptar»\n"
            "5. Wybierz dostępną datę i godzinę\n"
            "6. Potwierdź wizytę\n"
            "\n"
            "⚠️ Działaj szybko — terminy znikają w minutach"
        ),
        "ro": (
            "👉 Acum se deschide site-ul oficial de programări:\n"
            "\n"
            "1. Apasă «Aceptar» <i>(acceptă cookies)</i>\n"
            "2. Selectează provincia\n"
            "3. {service_step}\n"
            "4. Apasă «Aceptar»\n"
            "5. Alege data și ora disponibilă\n"
            "6. Confirmă programarea\n"
            "\n"
            "⚠️ Acționează rapid — citas dispar în minute"
        ),
        "ar": (
            "👉 سيفتح الآن الموقع الرسمي للحجز:\n"
            "\n"
            "1. اضغط على «Aceptar» <i>(قبول الكوكيز)</i>\n"
            "2. اختر المقاطعة\n"
            "3. {service_step}\n"
            "4. اضغط «Aceptar»\n"
            "5. اختر التاريخ والوقت المتاح\n"
            "6. أكّد موعدك\n"
            "\n"
            "⚠️ تصرف بسرعة — تختفي المواعيد في دقائق"
        ),
    },
}

# ── City → portal override map (extend as needed) ────────────────────────────
# All cities currently use GENERIC_ES; add city-specific keys here when needed
_CITY_PORTAL_MAP: dict[str, str] = {}   # e.g. "barcelona": "BARCELONA_SPECIFIC"

_DEFAULT_PORTAL = "GENERIC_ES"


# ── Public API ────────────────────────────────────────────────────────────────

def get_portal_instructions(city: str, service: str, lang: str) -> str:
    """
    Return localised step-by-step booking instructions.

    - city:    city key ("barcelona", "madrid", …)
    - service: svc_key ("nie", "renovacion", …)
    - lang:    language code ("es", "en", "uk", "pl", "ro", "ar")

    Always returns a non-empty string. Never raises.
    """
    try:
        portal_key = _CITY_PORTAL_MAP.get(city.lower(), _DEFAULT_PORTAL)
        portal     = _PORTAL_INSTRUCTIONS.get(portal_key, _PORTAL_INSTRUCTIONS[_DEFAULT_PORTAL])

        lang_key = lang.lower()
        template = portal.get(lang_key) or portal.get("en") or next(iter(portal.values()))

        # Build the service step line
        svc_label  = _SERVICE_LABEL.get(service.lower(), "")
        select_pfx = _SELECT_PREFIX.get(lang_key, _SELECT_PREFIX["en"])

        if svc_label:
            service_step = f"{select_pfx} <b>{svc_label}</b>"
        else:
            # Graceful fallback: no bold hint, just skip the select prefix
            service_step = select_pfx

        return template.format(service_step=service_step)

    except Exception as exc:
        logger.error("PORTAL_INSTRUCTIONS_ERROR | city=%s svc=%s lang=%s err=%s", city, service, lang, exc)
        # Last-resort fallback — always safe
        return "👉 Open the booking page and follow the on-screen steps."
