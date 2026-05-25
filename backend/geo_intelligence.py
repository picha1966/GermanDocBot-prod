# -*- coding: utf-8 -*-
"""backend/geo_intelligence.py - Географічна інтелігенція v6.0"""

import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# PLZ → BUNDESLAND MAPPING
# ============================================================================

PLZ_TO_BUNDESLAND = {
    '01': 'Sachsen', '02': 'Sachsen', '03': 'Brandenburg', '04': 'Sachsen',
    '06': 'Sachsen-Anhalt', '07': 'Thüringen', '08': 'Sachsen',
    '09': 'Sachsen', '10': 'Berlin', '12': 'Berlin', '13': 'Berlin',
    '14': 'Brandenburg', '15': 'Brandenburg', '16': 'Brandenburg',
    '17': 'Mecklenburg-Vorpommern', '18': 'Mecklenburg-Vorpommern',
    '19': 'Mecklenburg-Vorpommern', '20': 'Hamburg', '21': 'Hamburg',
    '22': 'Hamburg', '23': 'Schleswig-Holstein', '24': 'Schleswig-Holstein',
    '25': 'Schleswig-Holstein', '26': 'Niedersachsen', '27': 'Niedersachsen',
    '28': 'Bremen', '29': 'Niedersachsen', '30': 'Niedersachsen',
    '31': 'Niedersachsen', '32': 'Nordrhein-Westfalen', '33': 'Nordrhein-Westfalen',
    '34': 'Hessen', '35': 'Hessen', '36': 'Hessen', '37': 'Niedersachsen',
    '38': 'Niedersachsen', '39': 'Sachsen-Anhalt', '40': 'Nordrhein-Westfalen',
    '41': 'Nordrhein-Westfalen', '42': 'Nordrhein-Westfalen', '44': 'Nordrhein-Westfalen',
    '45': 'Nordrhein-Westfalen', '46': 'Nordrhein-Westfalen', '47': 'Nordrhein-Westfalen',
    '48': 'Nordrhein-Westfalen', '49': 'Nordrhein-Westfalen', '50': 'Nordrhein-Westfalen',
    '51': 'Nordrhein-Westfalen', '52': 'Nordrhein-Westfalen', '53': 'Nordrhein-Westfalen',
    '54': 'Rheinland-Pfalz', '55': 'Rheinland-Pfalz', '56': 'Rheinland-Pfalz',
    '57': 'Nordrhein-Westfalen', '58': 'Nordrhein-Westfalen', '59': 'Nordrhein-Westfalen',
    '60': 'Hessen', '61': 'Hessen', '63': 'Hessen', '64': 'Hessen',
    '65': 'Hessen', '66': 'Saarland', '67': 'Rheinland-Pfalz',
    '68': 'Baden-Württemberg', '69': 'Baden-Württemberg', '70': 'Baden-Württemberg',
    '71': 'Baden-Württemberg', '72': 'Baden-Württemberg', '73': 'Baden-Württemberg',
    '74': 'Baden-Württemberg', '75': 'Baden-Württemberg', '76': 'Baden-Württemberg',
    '77': 'Baden-Württemberg', '78': 'Baden-Württemberg', '79': 'Baden-Württemberg',
    '80': 'Bayern', '81': 'Bayern', '82': 'Bayern', '83': 'Bayern',
    '84': 'Bayern', '85': 'Bayern', '86': 'Bayern', '87': 'Bayern',
    '88': 'Baden-Württemberg', '89': 'Baden-Württemberg', '90': 'Bayern',
    '91': 'Bayern', '92': 'Bayern', '93': 'Bayern', '94': 'Bayern',
    '95': 'Bayern', '96': 'Bayern', '97': 'Bayern', '98': 'Thüringen',
    '99': 'Thüringen'
}

# ============================================================================
# FAMILIENKASSEN (KINDERGELD, KINDERZUSCHLAG, ELTERNGELD)
# ============================================================================

FAMILIENKASSEN = {
    'Baden-Württemberg': {
        'name': 'Familienkasse Baden-Württemberg West',
        'address': 'Herrnstraße 14',
        'plz': '76133',
        'city': 'Karlsruhe',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Baden-Wuerttemberg-West@arbeitsagentur.de'
    },
    'Bayern': {
        'name': 'Familienkasse Bayern Süd',
        'address': 'Kapuzinerstraße 30',
        'plz': '80337',
        'city': 'München',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Bayern-Sued@arbeitsagentur.de'
    },
    'Berlin': {
        'name': 'Familienkasse Berlin',
        'address': 'Bundesallee 39',
        'plz': '10715',
        'city': 'Berlin',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Berlin@arbeitsagentur.de'
    },
    'Brandenburg': {
        'name': 'Familienkasse Brandenburg',
        'address': 'Wetzlarer Straße 54',
        'plz': '14482',
        'city': 'Potsdam',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Brandenburg@arbeitsagentur.de'
    },
    'Bremen': {
        'name': 'Familienkasse Bremen-Bremerhaven',
        'address': 'Doventorsteinweg 48-52',
        'plz': '28195',
        'city': 'Bremen',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Bremen-Bremerhaven@arbeitsagentur.de'
    },
    'Hamburg': {
        'name': 'Familienkasse Hamburg',
        'address': 'Norderstraße 105',
        'plz': '20097',
        'city': 'Hamburg',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Hamburg@arbeitsagentur.de'
    },
    'Hessen': {
        'name': 'Familienkasse Hessen',
        'address': 'Platterstraße 3',
        'plz': '65193',
        'city': 'Wiesbaden',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Hessen@arbeitsagentur.de'
    },
    'Mecklenburg-Vorpommern': {
        'name': 'Familienkasse Mecklenburg-Vorpommern',
        'address': 'Kopernikusstraße 1a',
        'plz': '18057',
        'city': 'Rostock',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Mecklenburg-Vorpommern@arbeitsagentur.de'
    },
    'Niedersachsen': {
        'name': 'Familienkasse Niedersachsen-Bremen',
        'address': 'Kurt-Schumacher-Allee 16',
        'plz': '30159',
        'city': 'Hannover',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Niedersachsen-Bremen@arbeitsagentur.de'
    },
    'Nordrhein-Westfalen': {
        'name': 'Familienkasse Nordrhein-Westfalen West',
        'address': 'Grafenberger Allee 300',
        'plz': '40237',
        'city': 'Düsseldorf',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Nordrhein-Westfalen-West@arbeitsagentur.de'
    },
    'Rheinland-Pfalz': {
        'name': 'Familienkasse Rheinland-Pfalz-Saarland',
        'address': 'Eschberger Weg 68',
        'plz': '66121',
        'city': 'Saarbrücken',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Rheinland-Pfalz-Saarland@arbeitsagentur.de'
    },
    'Saarland': {
        'name': 'Familienkasse Rheinland-Pfalz-Saarland',
        'address': 'Eschberger Weg 68',
        'plz': '66121',
        'city': 'Saarbrücken',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Rheinland-Pfalz-Saarland@arbeitsagentur.de'
    },
    'Sachsen': {
        'name': 'Familienkasse Sachsen',
        'address': 'Georg-Schumann-Straße 150',
        'plz': '04159',
        'city': 'Leipzig',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Sachsen@arbeitsagentur.de'
    },
    'Sachsen-Anhalt': {
        'name': 'Familienkasse Sachsen-Anhalt-Thüringen',
        'address': 'Hallesche Straße 17',
        'plz': '06112',
        'city': 'Halle (Saale)',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Sachsen-Anhalt-Thueringen@arbeitsagentur.de'
    },
    'Schleswig-Holstein': {
        'name': 'Familienkasse Nord',
        'address': 'Projensdorfer Straße 82',
        'plz': '24106',
        'city': 'Kiel',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Nord@arbeitsagentur.de'
    },
    'Thüringen': {
        'name': 'Familienkasse Sachsen-Anhalt-Thüringen',
        'address': 'Hallesche Straße 17',
        'plz': '06112',
        'city': 'Halle (Saale)',
        'phone': '+49 800 4555530',
        'email': 'Familienkasse-Sachsen-Anhalt-Thueringen@arbeitsagentur.de'
    }
}

# ============================================================================
# ELTERNGELDSTELLEN
# ============================================================================

ELTERNGELDSTELLEN = {
    'Baden-Württemberg': {
        'name': 'Elterngeldstelle Baden-Württemberg',
        'address': 'L-Bank, Schlossplatz 10',
        'plz': '76131',
        'city': 'Karlsruhe',
        'phone': '+49 800 7234946',
        'email': 'elterngeld@l-bank.de'
    },
    'Bayern': {
        'name': 'Zentrum Bayern Familie und Soziales',
        'address': 'Hegelstraße 2',
        'plz': '95447',
        'city': 'Bayreuth',
        'phone': '+49 921 605-0',
        'email': 'elterngeld@zbfs.bayern.de'
    },
    'Berlin': {
        'name': 'Elterngeldstelle Berlin',
        'address': 'Oranienstraße 106',
        'plz': '10969',
        'city': 'Berlin',
        'phone': '+49 30 90229-0',
        'email': 'elterngeld@senweb.berlin.de'
    },
    'Brandenburg': {
        'name': 'Elterngeldstelle Brandenburg',
        'address': 'Steinstraße 104-106',
        'plz': '14480',
        'city': 'Potsdam',
        'phone': '+49 331 8683-777',
        'email': 'elterngeld@msgiv.brandenburg.de'
    },
    'Bremen': {
        'name': 'Elterngeldstelle Bremen',
        'address': 'Bahnhofsplatz 29',
        'plz': '28195',
        'city': 'Bremen',
        'phone': '+49 421 361-6186',
        'email': 'elterngeld@soziales.bremen.de'
    },
    'Hamburg': {
        'name': 'Elterngeldstelle Hamburg',
        'address': 'Hamburger Straße 37',
        'plz': '22083',
        'city': 'Hamburg',
        'phone': '+49 40 428 63-0',
        'email': 'elterngeld@basfi.hamburg.de'
    },
    'Hessen': {
        'name': 'Elterngeldstelle Hessen',
        'address': 'Dostojewskistraße 4',
        'plz': '65187',
        'city': 'Wiesbaden',
        'phone': '+49 611 327-0',
        'email': 'elterngeld@rpda.hessen.de'
    },
    'Mecklenburg-Vorpommern': {
        'name': 'Elterngeldstelle Mecklenburg-Vorpommern',
        'address': 'Werderstraße 124',
        'plz': '19055',
        'city': 'Schwerin',
        'phone': '+49 385 588-0',
        'email': 'elterngeld@lm.mv-regierung.de'
    },
    'Niedersachsen': {
        'name': 'Elterngeldstelle Niedersachsen',
        'address': 'Hannah-Arendt-Platz 2',
        'plz': '30159',
        'city': 'Hannover',
        'phone': '+49 511 120-0',
        'email': 'elterngeld@ms.niedersachsen.de'
    },
    'Nordrhein-Westfalen': {
        'name': 'Elterngeldstelle Nordrhein-Westfalen',
        'address': 'Fürstenwall 25',
        'plz': '40219',
        'city': 'Düsseldorf',
        'phone': '+49 211 855-0',
        'email': 'elterngeld@mags.nrw.de'
    },
    'Rheinland-Pfalz': {
        'name': 'Elterngeldstelle Rheinland-Pfalz',
        'address': 'Bauhofstraße 9',
        'plz': '55116',
        'city': 'Mainz',
        'phone': '+49 6131 16-0',
        'email': 'elterngeld@mffki.rlp.de'
    },
    'Saarland': {
        'name': 'Elterngeldstelle Saarland',
        'address': 'Franz-Josef-Röder-Straße 17',
        'plz': '66119',
        'city': 'Saarbrücken',
        'phone': '+49 681 501-0',
        'email': 'elterngeld@soziales.saarland.de'
    },
    'Sachsen': {
        'name': 'Elterngeldstelle Sachsen',
        'address': 'Augustusweg 19',
        'plz': '01445',
        'city': 'Radebeul',
        'phone': '+49 351 8250-0',
        'email': 'elterngeld@sms.sachsen.de'
    },
    'Sachsen-Anhalt': {
        'name': 'Elterngeldstelle Sachsen-Anhalt',
        'address': 'Turmschanzenstraße 25',
        'plz': '39114',
        'city': 'Magdeburg',
        'phone': '+49 391 567-0',
        'email': 'elterngeld@ms.sachsen-anhalt.de'
    },
    'Schleswig-Holstein': {
        'name': 'Elterngeldstelle Schleswig-Holstein',
        'address': 'Adolf-Westphal-Straße 4',
        'plz': '24143',
        'city': 'Kiel',
        'phone': '+49 431 988-0',
        'email': 'elterngeld@sozmi.landsh.de'
    },
    'Thüringen': {
        'name': 'Elterngeldstelle Thüringen',
        'address': 'Werner-Seelenbinder-Straße 6',
        'plz': '99096',
        'city': 'Erfurt',
        'phone': '+49 361 3798-0',
        'email': 'elterngeld@tmasgff.thueringen.de'
    }
}

# ============================================================================
# JOBCENTER (BÜRGERGELD)
# ============================================================================

JOBCENTER = {
    'Baden-Württemberg': {
        'name': 'Jobcenter Stuttgart',
        'address': 'Rosensteinstraße 11',
        'plz': '70191',
        'city': 'Stuttgart',
        'phone': '+49 711 920-0',
        'email': 'jobcenter-stuttgart@jobcenter-ge.de'
    },
    'Bayern': {
        'name': 'Jobcenter München',
        'address': 'Schwanthalerstraße 64',
        'plz': '80336',
        'city': 'München',
        'phone': '+49 89 5154-0',
        'email': 'jobcenter-muenchen@jobcenter-ge.de'
    },
    'Berlin': {
        'name': 'Jobcenter Berlin Mitte',
        'address': 'Lehrter Straße 66-68',
        'plz': '10557',
        'city': 'Berlin',
        'phone': '+49 30 5555-0',
        'email': 'jobcenter-berlin-mitte@jobcenter-ge.de'
    },
    'Brandenburg': {
        'name': 'Jobcenter Potsdam',
        'address': 'Horstweg 102-108',
        'plz': '14478',
        'city': 'Potsdam',
        'phone': '+49 331 880-0',
        'email': 'jobcenter-potsdam@jobcenter-ge.de'
    },
    'Bremen': {
        'name': 'Jobcenter Bremen',
        'address': 'Doventorsteinweg 48-52',
        'plz': '28195',
        'city': 'Bremen',
        'phone': '+49 421 178-0',
        'email': 'jobcenter-bremen@jobcenter-ge.de'
    },
    'Hamburg': {
        'name': 'Jobcenter Hamburg',
        'address': 'Kurt-Schumacher-Allee 4',
        'plz': '20097',
        'city': 'Hamburg',
        'phone': '+49 40 248-0',
        'email': 'jobcenter-hamburg@jobcenter-ge.de'
    },
    'Hessen': {
        'name': 'Jobcenter Frankfurt',
        'address': 'Gutleutstraße 154-158',
        'plz': '60327',
        'city': 'Frankfurt am Main',
        'phone': '+49 69 2171-0',
        'email': 'jobcenter-frankfurt@jobcenter-ge.de'
    },
    'Mecklenburg-Vorpommern': {
        'name': 'Jobcenter Rostock',
        'address': 'Kopernikusstraße 1a',
        'plz': '18057',
        'city': 'Rostock',
        'phone': '+49 381 2020-0',
        'email': 'jobcenter-rostock@jobcenter-ge.de'
    },
    'Niedersachsen': {
        'name': 'Jobcenter Hannover',
        'address': 'Brühlstraße 9',
        'plz': '30169',
        'city': 'Hannover',
        'phone': '+49 511 919-0',
        'email': 'jobcenter-hannover@jobcenter-ge.de'
    },
    'Nordrhein-Westfalen': {
        'name': 'Jobcenter Köln',
        'address': 'Luxemburger Straße 121',
        'plz': '50939',
        'city': 'Köln',
        'phone': '+49 221 9429-0',
        'email': 'jobcenter-koeln@jobcenter-ge.de'
    },
    'Rheinland-Pfalz': {
        'name': 'Jobcenter Mainz',
        'address': 'Untere Zahlbacher Straße 27',
        'plz': '55131',
        'city': 'Mainz',
        'phone': '+49 6131 248-0',
        'email': 'jobcenter-mainz@jobcenter-ge.de'
    },
    'Saarland': {
        'name': 'Jobcenter Saarbrücken',
        'address': 'Hafenstraße 18',
        'plz': '66111',
        'city': 'Saarbrücken',
        'phone': '+49 681 944-0',
        'email': 'jobcenter-saarbruecken@jobcenter-ge.de'
    },
    'Sachsen': {
        'name': 'Jobcenter Leipzig',
        'address': 'Georg-Schumann-Straße 150',
        'plz': '04159',
        'city': 'Leipzig',
        'phone': '+49 341 913-0',
        'email': 'jobcenter-leipzig@jobcenter-ge.de'
    },
    'Sachsen-Anhalt': {
        'name': 'Jobcenter Magdeburg',
        'address': 'Lübecker Straße 32',
        'plz': '39124',
        'city': 'Magdeburg',
        'phone': '+49 391 62-0',
        'email': 'jobcenter-magdeburg@jobcenter-ge.de'
    },
    'Schleswig-Holstein': {
        'name': 'Jobcenter Kiel',
        'address': 'Projensdorfer Straße 82',
        'plz': '24106',
        'city': 'Kiel',
        'phone': '+49 431 709-0',
        'email': 'jobcenter-kiel@jobcenter-ge.de'
    },
    'Thüringen': {
        'name': 'Jobcenter Erfurt',
        'address': 'Steigerstraße 24',
        'plz': '99096',
        'city': 'Erfurt',
        'phone': '+49 361 302-0',
        'email': 'jobcenter-erfurt@jobcenter-ge.de'
    }
}

# ============================================================================
# WOHNGELDBEHÖRDEN
# ============================================================================

WOHNGELDBEHOERDEN = {
    'Baden-Württemberg': {
        'name': 'Wohngeldstelle Stuttgart',
        'address': 'Eberhardstraße 33',
        'plz': '70173',
        'city': 'Stuttgart',
        'phone': '+49 711 216-0',
        'email': 'wohngeld@stuttgart.de'
    },
    'Bayern': {
        'name': 'Wohngeldstelle München',
        'address': 'Ruppertstraße 19',
        'plz': '80466',
        'city': 'München',
        'phone': '+49 89 233-96000',
        'email': 'wohngeld.kvr@muenchen.de'
    },
    'Berlin': {
        'name': 'Wohngeldstelle Berlin',
        'address': 'Fehrbelliner Platz 1',
        'plz': '10707',
        'city': 'Berlin',
        'phone': '+49 30 90269-0',
        'email': 'wohngeld@ba-mitte.berlin.de'
    },
    'Brandenburg': {
        'name': 'Wohngeldstelle Potsdam',
        'address': 'Friedrich-Ebert-Straße 79-81',
        'plz': '14469',
        'city': 'Potsdam',
        'phone': '+49 331 289-0',
        'email': 'wohngeld@rathaus.potsdam.de'
    },
    'Bremen': {
        'name': 'Wohngeldstelle Bremen',
        'address': 'Contrescarpe 72',
        'plz': '28195',
        'city': 'Bremen',
        'phone': '+49 421 361-0',
        'email': 'wohngeld@soziales.bremen.de'
    },
    'Hamburg': {
        'name': 'Wohngeldstelle Hamburg',
        'address': 'Caffamacherreihe 1-3',
        'plz': '20355',
        'city': 'Hamburg',
        'phone': '+49 40 428 28-0',
        'email': 'wohngeld@hamburg.de'
    },
    'Hessen': {
        'name': 'Wohngeldstelle Frankfurt',
        'address': 'Zeil 3',
        'plz': '60313',
        'city': 'Frankfurt am Main',
        'phone': '+49 69 212-0',
        'email': 'wohngeld@stadt-frankfurt.de'
    },
    'Mecklenburg-Vorpommern': {
        'name': 'Wohngeldstelle Rostock',
        'address': 'Neuer Markt 1',
        'plz': '18055',
        'city': 'Rostock',
        'phone': '+49 381 381-0',
        'email': 'wohngeld@rostock.de'
    },
    'Niedersachsen': {
        'name': 'Wohngeldstelle Hannover',
        'address': 'Leinstraße 14',
        'plz': '30159',
        'city': 'Hannover',
        'phone': '+49 511 168-0',
        'email': 'wohngeld@hannover-stadt.de'
    },
    'Nordrhein-Westfalen': {
        'name': 'Wohngeldstelle Köln',
        'address': 'Willy-Brandt-Platz 2',
        'plz': '50679',
        'city': 'Köln',
        'phone': '+49 221 221-0',
        'email': 'wohngeld@stadt-koeln.de'
    },
    'Rheinland-Pfalz': {
        'name': 'Wohngeldstelle Mainz',
        'address': 'Kaiserstraße 3-5',
        'plz': '55116',
        'city': 'Mainz',
        'phone': '+49 6131 12-0',
        'email': 'wohngeld@stadt.mainz.de'
    },
    'Saarland': {
        'name': 'Wohngeldstelle Saarbrücken',
        'address': 'Rathausplatz 1',
        'plz': '66111',
        'city': 'Saarbrücken',
        'phone': '+49 681 905-0',
        'email': 'wohngeld@saarbruecken.de'
    },
    'Sachsen': {
        'name': 'Wohngeldstelle Leipzig',
        'address': 'Martin-Luther-Ring 4-6',
        'plz': '04109',
        'city': 'Leipzig',
        'phone': '+49 341 123-0',
        'email': 'wohngeld@leipzig.de'
    },
    'Sachsen-Anhalt': {
        'name': 'Wohngeldstelle Magdeburg',
        'address': 'Alter Markt 6',
        'plz': '39104',
        'city': 'Magdeburg',
        'phone': '+49 391 540-0',
        'email': 'wohngeld@magdeburg.de'
    },
    'Schleswig-Holstein': {
        'name': 'Wohngeldstelle Kiel',
        'address': 'Fleethörn 9',
        'plz': '24103',
        'city': 'Kiel',
        'phone': '+49 431 901-0',
        'email': 'wohngeld@kiel.de'
    },
    'Thüringen': {
        'name': 'Wohngeldstelle Erfurt',
        'address': 'Fischmarkt 1',
        'plz': '99084',
        'city': 'Erfurt',
        'phone': '+49 361 655-0',
        'email': 'wohngeld@erfurt.de'
    }
}

# ============================================================================
# BÜRGERÄMTER (ANMELDUNG, ABMELDUNG)
# ============================================================================

BUERGERAEMTER = {
    'Berlin': {
        'name': 'Bürgeramt Berlin Mitte',
        'address': 'Karl-Marx-Allee 31',
        'plz': '10178',
        'city': 'Berlin',
        'phone': '+49 30 90269-0',
        'email': 'buergeramt@ba-mitte.berlin.de'
    },
    'Hamburg': {
        'name': 'Kundenzentrum Hamburg',
        'address': 'Caffamacherreihe 1-3',
        'plz': '20355',
        'city': 'Hamburg',
        'phone': '+49 40 428 28-0',
        'email': 'kundenzentrum@hamburg.de'
    },
    'München': {
        'name': 'Kreisverwaltungsreferat München',
        'address': 'Ruppertstraße 19',
        'plz': '80466',
        'city': 'München',
        'phone': '+49 89 233-96000',
        'email': 'kvr@muenchen.de'
    },
    'Köln': {
        'name': 'Bürgeramt Köln',
        'address': 'Laurenzplatz 1-3',
        'plz': '50667',
        'city': 'Köln',
        'phone': '+49 221 221-0',
        'email': 'buergeramt@stadt-koeln.de'
    },
    'Frankfurt am Main': {
        'name': 'Bürgeramt Frankfurt',
        'address': 'Zeil 3',
        'plz': '60313',
        'city': 'Frankfurt am Main',
        'phone': '+49 69 212-0',
        'email': 'buergeramt@stadt-frankfurt.de'
    },
    'Stuttgart': {
        'name': 'Bürgeramt Stuttgart',
        'address': 'Eberhardstraße 33',
        'plz': '70173',
        'city': 'Stuttgart',
        'phone': '+49 711 216-0',
        'email': 'buergeramt@stuttgart.de'
    },
    'Düsseldorf': {
        'name': 'Bürgeramt Düsseldorf',
        'address': 'Willi-Becker-Allee 10',
        'plz': '40227',
        'city': 'Düsseldorf',
        'phone': '+49 211 89-0',
        'email': 'buergeramt@duesseldorf.de'
    },
    'Dortmund': {
        'name': 'Bürgeramt Dortmund',
        'address': 'Südwall 2-4',
        'plz': '44137',
        'city': 'Dortmund',
        'phone': '+49 231 50-0',
        'email': 'buergerservice@dortmund.de'
    }
}

# ============================================================================
# ОСНОВНІ ФУНКЦІЇ
# ============================================================================

def get_bundesland(plz: str) -> str:
    """
    Визначає федеральну землю за PLZ.
    
    Args:
        plz: Поштовий індекс (5 цифр)
    
    Returns:
        Назва Bundesland
    """
    if not plz or len(plz) < 2:
        return 'Unbekannt'
    
    prefix = plz[:2]
    bundesland = PLZ_TO_BUNDESLAND.get(prefix, 'Unbekannt')
    
    if bundesland != 'Unbekannt':
        logger.info(f"📍 Знайдено землю: {bundesland} для PLZ {plz}")
    
    return bundesland


def get_city_by_plz(plz: str) -> str:
    """Визначає місто за PLZ (спрощена версія)"""
    major_cities = {
        '10': 'Berlin', '12': 'Berlin', '13': 'Berlin',
        '20': 'Hamburg', '22': 'Hamburg',
        '30': 'Hannover',
        '40': 'Düsseldorf', '44': 'Dortmund',
        '50': 'Köln',
        '60': 'Frankfurt am Main',
        '70': 'Stuttgart',
        '80': 'München', '81': 'München',
        '90': 'Nürnberg'
    }
    
    prefix = plz[:2] if len(plz) >= 2 else ''
    return major_cities.get(prefix, get_bundesland(plz))


def get_authority_address(doc_type: str, plz: str) -> Dict[str, str]:
    """
    Отримує адресу відомства залежно від типу документа та PLZ.
    
    Args:
        doc_type: Тип документа (kindergeld, buergergeld, anmeldung, тощо)
        plz: Поштовий індекс
    
    Returns:
        Словник з інформацією про відомство
    """
    bundesland = get_bundesland(plz)
    city = get_city_by_plz(plz)
    doc_type_lower = doc_type.lower()
    
    # Kindergeld, Kinderzuschlag → Familienkasse
    if doc_type_lower in ['kindergeld', 'kinderzuschlag']:
        authority = FAMILIENKASSEN.get(bundesland)
        if authority:
            logger.info(f"✅ Знайдено Familienkasse для {bundesland}")
            return authority
    
    # Elterngeld → Elterngeldstelle
    elif doc_type_lower == 'elterngeld':
        authority = ELTERNGELDSTELLEN.get(bundesland)
        if authority:
            logger.info(f"✅ Знайдено Elterngeldstelle для {bundesland}")
            return authority
    
    # Bürgergeld, Erstausstattung → Jobcenter
    elif doc_type_lower in ['buergergeld', 'erstausstattung']:
        authority = JOBCENTER.get(bundesland)
        if authority:
            logger.info(f"✅ Знайдено Jobcenter для {bundesland}")
            return authority
    
    # Wohngeld → Wohngeldstelle
    elif doc_type_lower == 'wohngeld':
        authority = WOHNGELDBEHOERDEN.get(bundesland)
        if authority:
            logger.info(f"✅ Знайдено Wohngeldstelle для {bundesland}")
            return authority
    
    # Anmeldung, Abmeldung → Bürgeramt
    elif doc_type_lower in ['anmeldung', 'abmeldung']:
        authority = BUERGERAEMTER.get(city)
        if authority:
            logger.info(f"✅ Знайдено Bürgeramt для {city}")
            return authority
    
    # Fallback
    logger.warning(f"⚠️ Відомство не знайдено для {doc_type} в {bundesland}")
    return {
        'name': f'Zuständige Behörde {bundesland}',
        'address': f'Bitte wenden Sie sich an Ihre lokale Behörde in {city}',
        'plz': '',
        'city': city,
        'phone': 'Bitte erfragen',
        'email': ''
    }


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
    'get_authority_address',
    'format_authority_info',
    'get_full_location_info'
]