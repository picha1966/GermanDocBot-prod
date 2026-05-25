# -*- coding: utf-8 -*-
"""
Berlin Bürgeramt addresses for preview PDFs.
Provides specific authority addresses for Berlin PLZ ranges (10xxx-14xxx).
"""

# Berlin Bürgeramt addresses (for PLZ starting with 10-14)
BERLIN_BUERGERAEMTER = {
    # Central Berlin (Mitte) - PLZ 101xx
    "10115": {
        "name": "Bürgeramt Mitte",
        "address": "Rathausstraße 15",
        "plz": "10115",
        "city": "Berlin",
        "phone": "+49 30 9018-0",
        "website": "https://www.berlin.de/buergeramt/standorte/buergeramt-mitte/",
        "search_url": "https://service.berlin.de/standort/",
    },
    "10117": {
        "name": "Bürgeramt Mitte",
        "address": "Rathausstraße 15",
        "plz": "10117",
        "city": "Berlin",
        "phone": "+49 30 9018-0",
        "website": "https://www.berlin.de/buergeramt/standorte/buergeramt-mitte/",
        "search_url": "https://service.berlin.de/standort/",
    },
    # Default for Berlin (if specific PLZ not found)
    "default_berlin": {
        "name": "Bürgeramt Berlin",
        "address": "Rathausstraße 15",
        "plz": "10115",
        "city": "Berlin",
        "phone": "+49 30 9018-0",
        "website": "https://www.berlin.de/buergeramt/",
        "search_url": "https://service.berlin.de/standort/",
    },
}


def get_berlin_buergeramt(plz: str) -> dict:
    """
    Get Berlin Bürgeramt address for a given PLZ.
    
    Args:
        plz: Postal code (string, e.g., "10117")
    
    Returns:
        Dictionary with authority info (name, address, plz, city, phone, website, search_url)
        Returns default Berlin address if specific PLZ not found
    """
    # Clean PLZ
    plz_clean = str(plz).strip()
    
    # Check if PLZ starts with 10-14 (Berlin range)
    if len(plz_clean) >= 2:
        prefix = plz_clean[:2]
        if prefix in ["10", "11", "12", "13", "14"]:
            # Try exact match first
            if plz_clean in BERLIN_BUERGERAEMTER:
                return BERLIN_BUERGERAEMTER[plz_clean]
            # Fallback to default Berlin
            return BERLIN_BUERGERAEMTER["default_berlin"]
    
    return None


def is_berlin_plz(plz: str) -> bool:
    """
    Check if PLZ belongs to Berlin (starts with 10-14).
    
    Args:
        plz: Postal code (string)
    
    Returns:
        True if PLZ is in Berlin range, False otherwise
    """
    plz_clean = str(plz).strip()
    if len(plz_clean) >= 2:
        prefix = plz_clean[:2]
        return prefix in ["10", "11", "12", "13", "14"]
    return False
