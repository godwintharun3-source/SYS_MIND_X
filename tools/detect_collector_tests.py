#!/usr/bin/env python3
"""CLI utility auditing unit test coverage and safety invariants across all macOS collectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.packaging.macos_collector_tests import MacOsCollectorTestsValidator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit unit test coverage and charter safety invariants across all macOS collectors."
    )
    parser.add_argument("--json", action="store_true", help="Output audit results in JSON format")
    parser.add_argument("--verbose", action="store_true", help="Display verbose diagnostic details")
    args = parser.parse_args()

    validator = MacOsCollectorTestsValidator(root_dir=ROOT_DIR)
    result = validator.audit()

    if args.json:
        payload = {
            "valid": result.valid,
            "collector_count": result.collector_count,
            "modules_valid": result.modules_valid,
            "ast_safety_valid": result.ast_safety_valid,
            "tests_valid": result.tests_valid,
            "rust_sensors_valid": result.rust_sensors_valid,
            "invariants_valid": result.invariants_valid,
            "issues": list(result.issues),
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.valid else 1

    print("=" * 76)
    print(" SYSTEM MIND X — macOS Collector Unit Test & Safety Invariants Audit")
    print("=" * 76)
    print(f"Total Collector Modules:   {result.collector_count}")
    print(f"Modules Installed:         {'PASS' if result.modules_valid else 'FAIL'}")
    print(f"AST Safety (SC-01):        {'PASS (Zero shell=True, bounded timeouts)' if result.ast_safety_valid else 'FAIL'}")
    print(f"Dedicated Unit Tests:      {'PASS' if result.tests_valid else 'FAIL'}")
    print(f"Native Rust Sensors:       {'PASS' if result.rust_sensors_valid else 'FAIL'}")
    print(f"Charter Invariant:         {'PASS (scan_proves_safe = False)' if result.invariants_valid else 'FAIL'}")
    print("-" * 76)

    if result.issues:
        print("Issues Detected:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("-" * 76)
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: ALL AUDITS PASSED")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
