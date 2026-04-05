import os
import fitz
import traceback

from backend.form_builder import build_german_form


# 🔍 автоматично визначає документи (через SAMPLE_DATA fallback)
DOCUMENTS = [
    "anmeldung",
    "buergergeld",
    "wohngeld",
    "familienkasse",
]


# 🔧 мінімальні дані (safe)
BASE_DATA = {
    "first_name": "Ivan",
    "last_name": "Ivanov",
    "birth_date": "01.01.1990",
    "city": "Berlin",
    "plz": "10115",
    "street": "Teststrasse 1",
}


# специфічні оверрайди
DOC_OVERRIDES = {
    "buergergeld": {
        "iban": "DE12345678901234567890",
        "has_sv_number": "nein",
        "sv_number": "12345678A123",
    }
}


# ===== PDF TEXT =====
def extract_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        return "".join(page.get_text() for page in doc)
    except Exception:
        return ""


# ===== BUILD SAFE DATA =====
def build_data(doc_type):
    data = BASE_DATA.copy()
    data.update(DOC_OVERRIDES.get(doc_type, {}))
    return data


# ===== VALIDATION =====
def validate(doc_type, data, text):
    errors = []

    if not text:
        errors.append("PDF empty")

    # базова перевірка
    if data.get("first_name") and data["first_name"] not in text:
        errors.append("First name missing")

    if data.get("last_name") and data["last_name"] not in text:
        errors.append("Last name missing")

    # бізнес логіка приклад
    if doc_type == "buergergeld":
        if data.get("has_sv_number") == "nein":
            if "12345678A123" in text:
                errors.append("SV not cleaned")

    return errors


# ===== TEST ONE =====
def run_single(doc_type):
    print(f"\n=== TEST: {doc_type} ===")

    data = build_data(doc_type)

    output_dir = "generated_pdfs"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/{doc_type}.pdf"

    try:
        result = build_german_form(
            doc_type=doc_type,
            user_data=data,
            output_path=output_path,
            is_preview=True
        )
    except Exception as e:
        print("❌ BUILD CRASH")
        print(traceback.format_exc())
        return "crash"

    if not result or not os.path.exists(output_path):
        print("❌ PDF not generated")
        return "fail"

    text = extract_text(output_path)

    errors = validate(doc_type, data, text)

    if errors:
        print("❌ ERRORS:")
        for e in errors:
            print(" -", e)
        return "fail"

    print("✅ OK")
    return "ok"


# ===== RUN ALL =====
def run_all():
    results = {
        "ok": [],
        "fail": [],
        "crash": []
    }

    for doc in DOCUMENTS:
        status = run_single(doc)
        results[status].append(doc)

    print("\n======================")
    print("RESULTS:")

    print(f"✅ OK: {results['ok']}")
    print(f"❌ FAIL: {results['fail']}")
    print(f"💥 CRASH: {results['crash']}")

    if results["fail"] or results["crash"]:
        raise Exception("TESTS FAILED")


if __name__ == "__main__":
    run_all()