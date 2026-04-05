# -*- coding: utf-8 -*-
"""
tools/register_new_doc.py — Helper to validate and onboard a new doc_type.

Usage:
    python tools/register_new_doc.py <doc_type> [--strategy acroform|builder|xfa_overlay]

Checks:
  1. Template file exists (templates/<doc_type>/*.pdf)
  2. DOC_STRATEGY entry exists
  3. DOC_RENDER_MAP entry exists
  4. If acroform: _ACROFORM_MAPPINGS entry exists with ≥1 keys
  5. If acroform: template has AcroForm widgets
  6. Prints registration checklist and next steps
"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path

TEMPLATES_DIR = Path("templates")
PASS = "  ✓"
FAIL = "  ✗"
WARN = "  ⚠"


def check_doc(doc_type: str) -> dict:
    from backend.document_config import DOC_STRATEGY, _ACROFORM_MAPPINGS
    from backend.pdf_renderers import DOC_RENDER_MAP

    issues = []
    info = {}

    # 1. DOC_STRATEGY
    strategy = DOC_STRATEGY.get(doc_type)
    info["doc_strategy"] = strategy
    if not strategy:
        issues.append(f"DOC_STRATEGY missing: add \"{doc_type}\": \"acroform\" to backend/document_config.py")

    # 2. DOC_RENDER_MAP
    render_strategy = DOC_RENDER_MAP.get(doc_type)
    info["render_strategy"] = render_strategy
    if not render_strategy:
        issues.append(f"DOC_RENDER_MAP missing: add \"{doc_type}\": \"acroform\" to backend/pdf_renderers.py")

    # 3. Template files — check alias, new path, and legacy paths
    from backend.document_config import DOC_TEMPLATE_ALIAS
    LEGACY_TEMPLATES = Path("backend/templates")
    _alias_owner = DOC_TEMPLATE_ALIAS.get(doc_type)
    folder = TEMPLATES_DIR / (_alias_owner or doc_type)
    pdfs = []
    if folder.exists():
        pdfs = list(folder.glob("*.pdf"))
    if not pdfs and LEGACY_TEMPLATES.exists():
        for sub in LEGACY_TEMPLATES.glob("**/*.pdf"):
            if doc_type.replace("_", "") in sub.stem.replace("_", "").lower() or doc_type in sub.parent.name:
                pdfs.append(sub)
            # also check alias owner name in legacy
            if _alias_owner and _alias_owner in sub.stem.lower():
                pdfs.append(sub)
    info["template_files"] = [p.name for p in pdfs]
    info["template_paths"] = pdfs   # full Path objects for widget inspection
    info["has_template"] = bool(pdfs)
    info["template_alias"] = _alias_owner
    # Only flag missing template for docs that need one (acroform / xfa_overlay)
    _needs_template = render_strategy not in ("builder_only", "builder", None)
    if not info["has_template"] and _needs_template:
        issues.append(f"No template folder at templates/{doc_type}/ (required for strategy={render_strategy!r})")

    # 4. Mapping (only for acroform)
    mapping = _ACROFORM_MAPPINGS.get(doc_type, {})
    info["mapping_keys"] = len(mapping)
    is_acroform = render_strategy == "acroform"
    if is_acroform and len(mapping) == 0:
        issues.append(f"_ACROFORM_MAPPINGS missing or empty: add {doc_type.upper()}_ACROFORM_MAPPING to backend/document_config.py")

    # 5. AcroForm widgets in template (use full discovered paths)
    widget_count = 0
    if info["has_template"] and info["template_paths"]:
        try:
            import fitz
            for pdf_full_path in info["template_paths"]:
                pdf = fitz.open(str(pdf_full_path))
                for page in pdf:
                    widget_count += sum(1 for _ in page.widgets())
                pdf.close()
        except Exception as e:
            issues.append(f"Could not inspect template: {e}")
    info["widget_count"] = widget_count
    if is_acroform and info["has_template"] and widget_count == 0:
        issues.append("Template has 0 AcroForm widgets — may be XFA-only or flat scan")

    info["issues"] = issues
    return info


def print_report(doc_type: str, info: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  Registration check: {doc_type}")
    print(f"{'='*60}")

    # Template
    alias_note = f" [alias → {info['template_alias']!r}]" if info.get("template_alias") else ""
    if info["has_template"]:
        print(f"{PASS} Template files: {info['template_files']} ({info['widget_count']} widgets){alias_note}")
    else:
        print(f"{FAIL} Template: MISSING — place PDF at templates/{doc_type}/<bundesland>.pdf")

    # DOC_STRATEGY
    if info["doc_strategy"]:
        print(f"{PASS} DOC_STRATEGY: {info['doc_strategy']!r}")
    else:
        print(f"{FAIL} DOC_STRATEGY: MISSING")

    # DOC_RENDER_MAP
    if info["render_strategy"]:
        print(f"{PASS} DOC_RENDER_MAP: {info['render_strategy']!r}")
    else:
        print(f"{FAIL} DOC_RENDER_MAP: MISSING")

    # Mapping
    is_acroform = info["render_strategy"] == "acroform"
    if not is_acroform:
        print(f"{PASS} _ACROFORM_MAPPINGS: N/A (strategy={info['render_strategy']!r})")
    elif info["mapping_keys"] > 0:
        print(f"{PASS} _ACROFORM_MAPPINGS: {info['mapping_keys']} keys")
    else:
        print(f"{FAIL} _ACROFORM_MAPPINGS: EMPTY or MISSING")

    # Issues
    if info["issues"]:
        print(f"\n  Blockers ({len(info['issues'])}):")
        for iss in info["issues"]:
            print(f"    • {iss}")
        print(f"\n  Status: NOT READY")
    else:
        print(f"\n  Status: READY ✓")

    # Next steps checklist
    if info["issues"]:
        print(f"\n  Next steps:")
        if not info["has_template"]:
            print(f"    1. Download official PDF → place in templates/{doc_type}/default.pdf")
            print(f"    2. Run: python tools/extract_pdf_fields.py {doc_type}/default.pdf")
        if not info["doc_strategy"]:
            print(f"    3. Add to DOC_STRATEGY in backend/document_config.py")
        if not info["render_strategy"]:
            print(f"    4. Add to DOC_RENDER_MAP in backend/pdf_renderers.py")
        if is_acroform and info["mapping_keys"] == 0:
            print(f"    5. Create {doc_type.upper()}_ACROFORM_MAPPING dict in backend/document_config.py")
            print(f"    6. Add handlers in get_value_for_pdf_field() for composite fields")
            print(f"    7. Add to _ACROFORM_MAPPINGS dict")
        print(f"    8. Smoke test: python tools/test_pipeline.py (add {doc_type} entry)")
        print(f"    9. Run: python tools/integration_audit.py")
    print()


def main():
    parser = argparse.ArgumentParser(description="Validate new doc_type registration")
    parser.add_argument("doc_type", nargs="?", help="doc_type to check (e.g. 'neues_dokument')")
    parser.add_argument("--all", action="store_true", help="Check ALL registered doc_types")
    args = parser.parse_args()

    if args.all:
        from backend.document_config import DOC_STRATEGY
        from backend.pdf_renderers import DOC_RENDER_MAP
        all_docs = sorted(set(DOC_STRATEGY.keys()) | set(DOC_RENDER_MAP.keys()))
        ready = 0
        for dt in all_docs:
            info = check_doc(dt)
            status = "READY" if not info["issues"] else "NOT READY"
            print(f"  {'✓' if not info['issues'] else '✗'}  {dt:<35s} {info['render_strategy'] or 'MISSING':<14s} "
                  f"{info['mapping_keys']} keys  {info['widget_count']} widgets  {status}")
            if not info["issues"]:
                ready += 1
        print(f"\n  {ready}/{len(all_docs)} doc_types fully registered")
        return

    if not args.doc_type:
        parser.print_help()
        return

    doc_type = args.doc_type.strip().lower()
    info = check_doc(doc_type)
    print_report(doc_type, info)


if __name__ == "__main__":
    main()
