import re


def validate_buergergeld(data: dict):
    errors = []
    warnings = []

    # REQUIRED
    required_fields = [
        "first_name",
        "last_name",
        "birth_date",
        "street",
        "city",
    ]

    # Optional fields — warn but do not block delivery
    if not data.get("plz"):
        warnings.append("plz is missing (recommended)")

    for field in required_fields:
        if not data.get(field):
            errors.append(f"{field} is required")

    # PLZ
    plz = data.get("plz")
    if plz and not re.match(r"^\d{5}$", plz):
        errors.append("Invalid PLZ format (must be 5 digits)")

    # IBAN
    iban = data.get("iban")
    if iban:
        iban_clean = iban.replace(" ", "")
        if not re.match(r"^[A-Z]{2}\d{20}$", iban_clean):
            errors.append("Invalid IBAN format")

    # DATE
    birth_date = data.get("birth_date")
    if birth_date:
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", birth_date):
            errors.append("Birth date must be DD.MM.YYYY")

    # LOGIC
    if data.get("employment_status") == "unemployed":
        if not data.get("jobcenter_customer"):
            warnings.append("Jobcenter number is usually required")

    # ANDERE LEISTUNGEN — soft validation (PDF fields 39–45)
    if (data.get("has_andere_leistungen") or "").strip().lower() in ("ja", "yes", "true", "1"):
        if not (data.get("leistungsart") or "").strip():
            warnings.append("leistungsart is recommended when andere Leistungen is Ja (PDF field 39)")
        if not (data.get("leistungstraeger_name") or "").strip():
            warnings.append("leistungstraeger_name is recommended when andere Leistungen is Ja (PDF fields 40–44)")

    # KRANKENVERSICHERUNG — soft validation (PDF fields 76–77)
    if (data.get("has_health_insurance") or "").strip().lower() in ("ja", "yes", "true", "1"):
        if not (data.get("krankenkasse_name") or "").strip():
            warnings.append("krankenkasse_name is recommended when krankenversichert is Ja (PDF field 76)")
        if not (data.get("versicherungsnummer") or "").strip():
            warnings.append("versicherungsnummer is recommended when krankenversichert is Ja (PDF field 77)")

    return {
        "errors": errors,
        "warnings": warnings,
        "is_valid": len(errors) == 0,
    }
