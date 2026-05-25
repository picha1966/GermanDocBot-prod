# -*- coding: utf-8 -*-
"""backend/geo_intelligence.py - Географічна інтелігенція для Німеччини v5.0"""

import logging
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

# ============================================================================
# PLZ ДІАПАЗОНИ ДЛЯ BUNDESLÄNDER
# ============================================================================

PLZ_RANGES = {
    'Baden-Württemberg': [(68000, 69999), (70000, 76999), (77000, 79999), (88000, 89999)],
    'Bayern': [(80000, 87999), (90000, 96999), (97000, 97999)],
    'Berlin': [(10000, 14999)],
    'Brandenburg': [(14400, 16999), (19300, 19399)],
    'Bremen': [(27500, 27580), (28000, 28779)],
    'Hamburg': [(20000, 21999), (22000, 22769)],
    'Hessen': [(34000, 36999), (60000, 63999), (64200, 65999)],
    'Mecklenburg-Vorpommern': [(17000, 19999), (23900, 23999)],
    'Niedersachsen': [(21200, 21449), (21522, 21522), (26000, 27499), (27607, 27809), (28784, 28790), (29000, 31999), (37000, 37999), (38000, 39999), (48400, 48465), (48480, 48495), (48497, 48500), (49000, 49999)],
    'Nordrhein-Westfalen': [(32000, 33999), (34100, 34199), (40000, 48399), (48466, 48479), (48496, 48496), (50000, 53999), (57000, 58999)],
    'Rheinland-Pfalz': [(54000, 56999), (66000, 67999)],
    'Saarland': [(66000, 66999)],
    'Sachsen': [(1000, 9999), (2600, 2999)],
    'Sachsen-Anhalt': [(6000, 6999), (29400, 29549), (38800, 39999)],
    'Schleswig-Holstein': [(22800, 22999), (23000, 23899), (24000, 25999)],
    'Thüringen': [(4600, 4639), (7300, 7999), (36400, 36999), (37300, 37359), (98500, 99999)],
}

# ============================================================================
# BÜRGERÄMTER (ДЛЯ ANMELDUNG)
# ============================================================================

BUERGERAEMTER = {
    'Berlin': {
        'name': 'Bürgeramt Berlin Mitte',
        'address': 'Karl-Marx-Allee 31',
        'plz': '10178',
        'city': 'Berlin',
        'phone': '+49 30 90269-0',
        'email': 'buergeramt@ba-mitte.berlin.de',
        'website': 'https://service.berlin.de'
    },
    'Hamburg': {
        'name': 'Kundenzentrum Hamburg',
        'address': 'Caffamacherreihe 1-3',
        'plz': '20355',
        'city': 'Hamburg',
        'phone': '+49 40 428 28-0',
        'email': 'kundenzentrum@hamburg.de',
        'website': 'https://www.hamburg.de/behoerdenfinder'
    },
    'München': {
        'name': 'Kreisverwaltungsreferat München',
        'address': 'Ruppertstraße 19',
        'plz': '80466',
        'city': 'München',
        'phone': '+49 89 233-96000',
        'email': 'kvr@muenchen.de',
        'website': 'https://www.muenchen.de/kvr'
    },
    'Köln': {
        'name': 'Bürgeramt Köln',
        'address': 'Laurenzplatz 1-3',
        'plz': '50667',
        'city': 'Köln',
        'phone': '+49 221 221-0',
        'email': 'buergeramt@stadt-koeln.de',
        'website': 'https://www.stadt-koeln.de'
    },
    'Frankfurt am Main': {
        'name': 'Bürgeramt Frankfurt',
        'address': 'Zeil 3',
        'plz': '60313',
        'city': 'Frankfurt am Main',
        'phone': '+49 69 212-45148',
        'email': 'buergeramt@stadt-frankfurt.de',
        'website': 'https://frankfurt.de'
    },
    'Stuttgart': {
        'name': 'Bürgeramt Stuttgart',
        'address': 'Eberhardstraße 33',
        'plz': '70173',
        'city': 'Stuttgart',
        'phone': '+49 711 216-0',
        'email': 'buergeramt@stuttgart.de',
        'website': 'https://www.stuttgart.de'
    },
    'Düsseldorf': {
        'name': 'Bürgeramt Düsseldorf',
        'address': 'Willi-Becker-Allee 10',
        'plz': '40227',
        'city': 'Düsseldorf',
        'phone': '+49 211 89-0',
        'email': 'buergeramt@duesseldorf.de',
        'website': 'https://www.duesseldorf.de'
    },
    'Dortmund': {
        'name': 'Bürgeramt Dortmund',
        'address': 'Südwall 2-4',
        'plz': '44137',
        'city': 'Dortmund',
        'phone': '+49 231 50-0',
        'email': 'buergerservice@dortmund.de',
        'website': 'https://www.dortmund.de'
    },
}

# ============================================================================
# FAMILIENKASSEN (ДЛЯ KINDERGELD)
# ============================================================================

FAMILIENKASSEN = {
    'Baden-Württemberg': {
        'name': 'Familienkasse Baden-Württemberg West',
        'address': 'Herrnstraße 14',
        'plz': '76133',
        'city': 'Karlsruhe',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Baden-Wuerttemberg-West@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Bayern': {
        'name': 'Familienkasse Bayern Süd',
        'address': 'Kapuzinerstraße 30',
        'plz': '80337',
        'city': 'München',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Bayern-Sued@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Berlin': {
        'name': 'Familienkasse Berlin',
        'address': 'Bundesallee 39',
        'plz': '10715',
        'city': 'Berlin',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Berlin@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Brandenburg': {
        'name': 'Familienkasse Brandenburg',
        'address': 'Wetzlarer Straße 54',
        'plz': '14482',
        'city': 'Potsdam',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Brandenburg@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Bremen': {
        'name': 'Familienkasse Bremen-Bremerhaven',
        'address': 'Doventorsteinweg 48-52',
        'plz': '28195',
        'city': 'Bremen',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Bremen-Bremerhaven@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Hamburg': {
        'name': 'Familienkasse Hamburg',
        'address': 'Norderstraße 105',
        'plz': '20097',
        'city': 'Hamburg',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Hamburg@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Hessen': {
        'name': 'Familienkasse Hessen',
        'address': 'Platterstraße 3',
        'plz': '65193',
        'city': 'Wiesbaden',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Hessen@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Mecklenburg-Vorpommern': {
        'name': 'Familienkasse Mecklenburg-Vorpommern',
        'address': 'Kopernikusstraße 1a',
        'plz': '18057',
        'city': 'Rostock',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Mecklenburg-Vorpommern@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Niedersachsen': {
        'name': 'Familienkasse Niedersachsen-Bremen',
        'address': 'Kurt-Schumacher-Allee 16',
        'plz': '30159',
        'city': 'Hannover',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Niedersachsen-Bremen@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Nordrhein-Westfalen': {
        'name': 'Familienkasse Nordrhein-Westfalen West',
        'address': 'Grafenberger Allee 300',
        'plz': '40237',
        'city': 'Düsseldorf',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Nordrhein-Westfalen-West@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Rheinland-Pfalz': {
        'name': 'Familienkasse Rheinland-Pfalz-Saarland',
        'address': 'Eschberger Weg 68',
        'plz': '66121',
        'city': 'Saarbrücken',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Rheinland-Pfalz-Saarland@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Saarland': {
        'name': 'Familienkasse Rheinland-Pfalz-Saarland',
        'address': 'Eschberger Weg 68',
        'plz': '66121',
        'city': 'Saarbrücken',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Rheinland-Pfalz-Saarland@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Sachsen': {
        'name': 'Familienkasse Sachsen',
        'address': 'Georg-Schumann-Straße 150',
        'plz': '04159',
        'city': 'Leipzig',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Sachsen@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Sachsen-Anhalt': {
        'name': 'Familienkasse Sachsen-Anhalt-Thüringen',
        'address': 'Hallesche Straße 17',
        'plz': '06112',
        'city': 'Halle (Saale)',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Sachsen-Anhalt-Thueringen@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Schleswig-Holstein': {
        'name': 'Familienkasse Nord',
        'address': 'Projensdorfer Straße 82',
        'plz': '24106',
        'city': 'Kiel',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Nord@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
    'Thüringen': {
        'name': 'Familienkasse Sachsen-Anhalt-Thüringen',
        'address': 'Hallesche Straße 17',
        'plz': '06112',
        'city': 'Halle (Saale)',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Sachsen-Anhalt-Thueringen@arbeitsagentur.de',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    },
}

# ============================================================================
# ВЕЛИКІ МІСТА
# ============================================================================

MAJOR_CITIES = {
    '10': 'Berlin', '12': 'Berlin', '13': 'Berlin',
    '20': 'Hamburg', '22': 'Hamburg',
    '30': 'Hannover',
    '40': 'Düsseldorf', '44': 'Dortmund', '45': 'Essen',
    '50': 'Köln',
    '60': 'Frankfurt am Main',
    '70': 'Stuttgart',
    '80': 'München', '81': 'München',
    '90': 'Nürnberg',
}

# ============================================================================
# ФУНКЦІЇ
# ============================================================================

def get_bundesland(plz: str) -> str:
    """Визначає Bundesland за точним діапазоном PLZ"""
    if not plz or not plz.isdigit():
        return 'Unbekannt'
    
    plz_int = int(plz)
    
    for bundesland, ranges in PLZ_RANGES.items():
        for start, end in ranges:
            if start <= plz_int <= end:
                return bundesland
    
    return 'Unbekannt'


def get_city_by_plz(plz: str) -> str:
    """Визначає місто за PLZ"""
    if not plz or len(plz) < 2:
        return 'Unbekannt'
    
    prefix_2 = plz[:2]
    if prefix_2 in MAJOR_CITIES:
        return MAJOR_CITIES[prefix_2]
    
    bundesland = get_bundesland(plz)
    return f'Region {bundesland}'


def get_buergeramt_info(plz: str) -> Dict[str, str]:
    """Отримує Bürgeramt для Anmeldung"""
    city = get_city_by_plz(plz)
    
    if city in BUERGERAEMTER:
        return BUERGERAEMTER[city]
    
    return {
        'name': f'Bürgeramt {city}',
        'address': f'Зверніться до найближчого Bürgeramt у вашому місті {city}',
        'plz': '',
        'city': city,
        'phone': 'Уточніть номер',
        'email': '',
        'website': ''
    }


def get_familienkasse_info(plz: str) -> Dict[str, str]:
    """Отримує Familienkasse для Kindergeld"""
    bundesland = get_bundesland(plz)
    
    if bundesland in FAMILIENKASSEN:
        return FAMILIENKASSEN[bundesland]
    
    return {
        'name': f'Familienkasse {bundesland}',
        'address': 'Уточніть адресу',
        'plz': '',
        'city': '',
        'phone': '+49 800 4555530',
        'email': '',
        'website': 'https://www.arbeitsagentur.de/familie-und-kinder'
    }


def get_authority_address(doc_type: str, plz: str) -> Dict[str, str]:
    """
    Універсальна функція отримання адреси відомства.
    
    Args:
        doc_type: Тип документа (anmeldung, kindergeld, kinderzuschlag, ...)
        plz: Поштовий індекс
    
    Returns:
        Словник з інформацією про відомство
    """
    doc_type_lower = doc_type.lower()
    
    # Документи Familienkasse
    if doc_type_lower in ['kindergeld', 'kinderzuschlag', 'elterngeld']:
        return get_familienkasse_info(plz)
    
    # Документи Bürgeramt
    elif doc_type_lower in ['anmeldung', 'abmeldung']:
        return get_buergeramt_info(plz)
    
    # За замовчуванням - Bürgeramt
    else:
        return get_buergeramt_info(plz)


def format_authority_info(authority: Dict[str, str]) -> str:
    """
    Форматує інформацію про відомство з емодзі.
    
    Args:
        authority: Словник з інформацією
    
    Returns:
        Відформатований текст
    """
    parts = []
    
    if authority.get('name'):
        parts.append(f"🏢 <b>{authority['name']}</b>")
    
    if authority.get('address'):
        full_address = authority['address']
        if authority.get('plz') and authority.get('city'):
            full_address += f", {authority['plz']} {authority['city']}"
        parts.append(f"📍 {full_address}")
    
    if authority.get('phone'):
        parts.append(f"📞 {authority['phone']}")
    
    if authority.get('email'):
        parts.append(f"📧 {authority['email']}")
    
    if authority.get('website'):
        parts.append(f"🌐 {authority['website']}")
    
    return '\n'.join(parts)


def get_full_location_info(plz: str, doc_type: str = 'anmeldung') -> Tuple[str, str, Dict[str, str]]:
    """
    Отримує повну інформацію про локацію.
    
    Args:
        plz: Поштовий індекс
        doc_type: Тип документа
    
    Returns:
        Кортеж (bundesland, city, authority_info)
    """
    bundesland = get_bundesland(plz)
    city = get_city_by_plz(plz)
    authority = get_authority_address(doc_type, plz)
    
    logger.info(f"📍 PLZ {plz} ({doc_type}): {city}, {bundesland}")
    
    return bundesland, city, authority


# ============================================================================
# ЕКСПОРТ
# ============================================================================

__all__ = [
    'get_bundesland',
    'get_city_by_plz',
    'get_buergeramt_info',
    'get_familienkasse_info',
    'get_authority_address',
    'format_authority_info',
    'get_full_location_info'
]