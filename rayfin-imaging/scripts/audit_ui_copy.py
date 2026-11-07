#!/usr/bin/env python3
"""
CLI Audit Script for Rayfin Plain-Language Healthcare Copy & Fabric Glossary Tooltips.

Verifies:
1. All 7 foundational Microsoft Fabric glossary terms are declared in src/lib/glossary.ts.
2. All 7 terms are referenced and rendered via GlossaryTooltip across src/.
3. No forbidden raw database table names (dbo.patient, dbo.molecular_profile, etc.) or raw TCGA IDs appear as unmapped headlines.
4. Exits with code 0 on clean validation.
"""

import argparse
import os
import re
import sys
from pathlib import Path

REQUIRED_GLOSSARY_TERMS = [
    "OneLake",
    "shortcut",
    "Direct Lake",
    "Eventhouse",
    "Activator",
    "Data Agent",
    "Ontology",
]

FORBIDDEN_HEADLINE_JARGON = [
    re.compile(r"<(h[1-3]|div|span)[^>]*class=[\"'][^\"']*(t-display|sec-title|list-heading)[^\"']*[\"'][^>]*>\s*dbo\.", re.IGNORECASE),
    re.compile(r"<h[1-2][^>]*>\s*dbo\.", re.IGNORECASE),
    re.compile(r"<h1[^>]*>\s*TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}\s*</h1>", re.IGNORECASE),
]


def audit_glossary_dictionary(src_dir: Path) -> list[str]:
    errors = []
    glossary_file = src_dir / "lib" / "glossary.ts"
    if not glossary_file.exists():
        return [f"Missing glossary file: {glossary_file}"]

    content = glossary_file.read_text(encoding="utf-8")
    for term in REQUIRED_GLOSSARY_TERMS:
        # Check that the term is in the GLOSSARY dict
        pattern = re.compile(rf"['\"]?{re.escape(term)}['\"]?\s*:", re.MULTILINE)
        if not pattern.search(content):
            errors.append(f"Glossary dictionary missing required term: '{term}'")

    return errors


def audit_glossary_tooltip_references(src_dir: Path) -> dict[str, list[str]]:
    found_terms = {term: [] for term in REQUIRED_GLOSSARY_TERMS}
    tooltip_re = re.compile(
        r'<GlossaryTooltip[^>]*term=["\']([^"\']+)["\']', re.IGNORECASE
    )

    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith((".tsx", ".ts")):
                continue
            if file.endswith((".test.tsx", ".test.ts", ".d.ts")):
                continue
            file_path = Path(root) / file
            rel_path = file_path.relative_to(src_dir)
            content = file_path.read_text(encoding="utf-8")

            for match in tooltip_re.finditer(content):
                raw_term = match.group(1).strip()
                for term in REQUIRED_GLOSSARY_TERMS:
                    if term.lower() == raw_term.lower():
                        found_terms[term].append(str(rel_path))

    return found_terms


def audit_headlines_for_jargon(src_dir: Path) -> list[str]:
    violations = []
    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".tsx"):
                continue
            if file.endswith((".test.tsx", ".test.ts")):
                continue
            file_path = Path(root) / file
            rel_path = file_path.relative_to(src_dir)
            content = file_path.read_text(encoding="utf-8")

            for pattern in FORBIDDEN_HEADLINE_JARGON:
                for match in pattern.finditer(content):
                    snippet = match.group(0).replace("\n", " ").strip()
                    violations.append(
                        f"Forbidden unmapped jargon in headline at {rel_path}: {snippet}"
                    )

    return violations


def main():
    parser = argparse.ArgumentParser(
        description="Audit Rayfin UI copy for plain-language compliance and Fabric glossary tooltips."
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "src",
        help="Path to rayfin-imaging/src directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run verification without making changes (default: True).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed reference locations.",
    )

    args = parser.parse_args()
    src_dir = args.src_dir

    if not src_dir.exists():
        print(f"Error: Source directory {src_dir} does not exist.", file=sys.stderr)
        sys.exit(1)

    print("=================================================================")
    print(" Rayfin UI Plain-Language Copy & Fabric Glossary Audit")
    print(f" Scanning: {src_dir}")
    print("=================================================================")

    # 1. Audit glossary.ts definitions
    glossary_errors = audit_glossary_dictionary(src_dir)
    if glossary_errors:
        print("\n[FAIL] Glossary dictionary errors in src/lib/glossary.ts:")
        for err in glossary_errors:
            print(f"  - {err}")
    else:
        print(f"\n[PASS] All {len(REQUIRED_GLOSSARY_TERMS)} required Fabric terms declared in src/lib/glossary.ts:")
        for term in REQUIRED_GLOSSARY_TERMS:
            print(f"  ✓ {term}")

    # 2. Audit GlossaryTooltip usages
    term_references = audit_glossary_tooltip_references(src_dir)
    missing_term_refs = [term for term, refs in term_references.items() if not refs]

    if missing_term_refs:
        print("\n[FAIL] Some glossary terms are not referenced via GlossaryTooltip in UI components:")
        for term in missing_term_refs:
            print(f"  - Missing tooltip usage for: '{term}'")
    else:
        print(f"\n[PASS] All {len(REQUIRED_GLOSSARY_TERMS)} glossary terms referenced via GlossaryTooltip in UI components:")
        for term, refs in term_references.items():
            ref_summary = ", ".join(sorted(set(refs)))
            print(f"  ✓ {term:<12} ({len(refs)} reference{'s' if len(refs) != 1 else ''} in {ref_summary})")

    # 3. Audit for forbidden jargon in headlines
    jargon_violations = audit_headlines_for_jargon(src_dir)
    if jargon_violations:
        print("\n[FAIL] Forbidden raw jargon found in headlines:")
        for v in jargon_violations:
            print(f"  - {v}")
    else:
        print("\n[PASS] Zero forbidden raw database table names or unmapped IDs found in headlines.")

    print("\n-----------------------------------------------------------------")
    if glossary_errors or missing_term_refs or jargon_violations:
        print("Audit RESULT: FAILED")
        sys.exit(1)
    else:
        print("Audit RESULT: PASSED (All copy and glossary criteria verified clean)")
        sys.exit(0)


if __name__ == "__main__":
    main()
