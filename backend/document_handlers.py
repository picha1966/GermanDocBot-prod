# -*- coding: utf-8 -*-
# backend/document_handlers.py


class DocumentConfig:
    def __init__(self, names: dict, price: float, template: str):
        """
        names: dict with language keys, e.g. {"de": "...", "pl": "...", "ua": "..."}
        """
        self.names = names
        self.price = price
        self.template = template

    def get_name(self, lang: str) -> str:
        if lang not in self.names:
            raise KeyError(f"Missing translation for language: {lang}")
        return self.names[lang]


# Groups of fields used for autofill (required by bot.py)
AUTOFILL_GROUPS = {
    "personal": ["first_name", "last_name", "birth_date", "birth_place"],
    "address": ["street", "house_number", "postal_code", "city"],
    "bank": ["iban", "bic", "account_holder"],
}


DOCUMENT_CONFIGS = {
    "anmeldung": DocumentConfig(
        names={
            "de": "Anmeldung",
            "pl": "Zameldowanie",
            "ua": "Реєстрація",
            "en": "Registration",
            "tr": "Kayıt",
        },
        price=3.49,
        template="anmeldung_template.pdf",
    ),

    "abmeldung": DocumentConfig(
        names={
            "de": "Abmeldung",
            "pl": "Wymeldowanie",
            "ua": "Зняття з реєстрації",
            "en": "Deregistration",
            "tr": "Kayıt silme",
        },
        price=3.49,
        template="abmeldung_template.pdf",
    ),

    "kindergeld": DocumentConfig(
        names={
            "de": "Kindergeld",
            "pl": "Zasiłek na dzieci",
            "ua": "Допомога на дітей",
            "en": "Child benefit",
            "tr": "Çocuk parası",
        },
        price=3.49,
        template="kindergeld_template.pdf",
    ),

    "wohngeld": DocumentConfig(
        names={
            "de": "Wohngeld",
            "pl": "Dodatek mieszkaniowy",
            "ua": "Допомога на житло",
            "en": "Housing benefit",
            "tr": "Konut yardımı",
        },
        price=3.49,
        template="wohngeld_template.pdf",
    ),
}


def get_document_config(doc_type: str):
    return DOCUMENT_CONFIGS.get(doc_type.lower())


def get_all_document_types():
    return list(DOCUMENT_CONFIGS.keys())