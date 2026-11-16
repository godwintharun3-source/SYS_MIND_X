#!/usr/bin/env python3
"""CLI developer tool for validating schemas, checking cross-language parity, and generating types."""

import argparse
from pathlib import Path
import sys

# Ensure src is on python path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from system_mind.schemas import SchemaStrategyValidator, TypeGenerator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X Schema Validation and Polyglot Type Generation Tool"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Perform schema compliance check and cross-language parity audit",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate type definitions from canonical JSON schemas",
    )
    parser.add_argument(
        "--target",
        choices=["typescript", "python", "rust", "all"],
        default="all",
        help="Target language for type generation",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory to write generated code files",
    )

    args = parser.parse_args()

    if not args.check and not args.generate:
        # Default behavior: run checks
        args.check = True

    exit_code = 0

    if args.check:
        print("[*] Running JSON Schema Draft compliance validation...")
        schema_report = SchemaStrategyValidator.validate_all_schemas()
        if schema_report.is_valid:
            print(f"    [+] All {len(schema_report.verified_schemas)} canonical schemas passed validation.")
        else:
            print(f"    [-] Schema validation failed with {len(schema_report.errors)} errors:")
            for err in schema_report.errors:
                print(f"        * {err}")
            exit_code = 1

        print("[*] Running cross-language polyglot parity audit...")
        parity_report = SchemaStrategyValidator.verify_cross_language_parity()
        if parity_report.is_valid:
            print(f"    [+] Cross-language parity verified across: {', '.join(parity_report.enums_checked)}")
        else:
            print(f"    [-] Parity audit detected {len(parity_report.drift_issues)} drift issues:")
            for issue in parity_report.drift_issues:
                print(f"        * {issue}")
            exit_code = 1

    if args.generate:
        generator = TypeGenerator()
        bundle = generator.generate_bundle()

        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            if args.target in ("typescript", "all"):
                (args.output_dir / "generated_types.ts").write_text(bundle["typescript"], encoding="utf-8")
                print(f"[+] Wrote TypeScript definitions to: {args.output_dir / 'generated_types.ts'}")
            if args.target in ("python", "all"):
                (args.output_dir / "generated_types.py").write_text(bundle["python"], encoding="utf-8")
                print(f"[+] Wrote Python definitions to: {args.output_dir / 'generated_types.py'}")
            if args.target in ("rust", "all"):
                (args.output_dir / "generated_types.rs").write_text(bundle["rust"], encoding="utf-8")
                print(f"[+] Wrote Rust definitions to: {args.output_dir / 'generated_types.rs'}")
        else:
            target = args.target if args.target != "all" else "typescript"
            print(f"\n--- GENERATED {target.upper()} ---\n")
            print(bundle[target])

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
