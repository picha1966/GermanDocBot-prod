def run_single_test(doc_type):
    print(f"\n=== TEST: {doc_type} ===")

    data = SAMPLE_DATA.get(doc_type)

    if not data:
        raise Exception(f"No data for {doc_type}")

    # ✅ правильний виклик
    pdf_path = create_final_pdf(doc_type, data)

    if not pdf_path:
        raise Exception("PDF path is empty")

    if not os.path.exists(pdf_path):
        raise Exception(f"PDF not generated: {pdf_path}")

    fields = extract_fields(pdf_path)

    print(f"Fields found: {len(fields)}")

    errors = validate_pdf_logic(doc_type, fields)

    if errors:
        print("❌ ERRORS:")
        for e in errors:
            print(" -", e)
        raise Exception(f"{doc_type} FAILED")

    print("✅ OK")