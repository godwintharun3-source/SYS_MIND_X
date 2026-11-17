#!/usr/bin/env python3
"""CLI utility running and auditing integration tests with missing sensors and denied permissions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.packaging.macos_integration_faults import MacOsIntegrationFaultsValidator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit integration tests with missing sensors and denied permissions."
    )
    parser.add_argument("--json", action="store_true", help="Output audit results in JSON format")
    parser.add_argument("--verbose", action="store_true", help="Display verbose diagnostic details")
    args = parser.parse_args()

    validator = MacOsIntegrationFaultsValidator(root_dir=ROOT_DIR)
    result = validator.audit()

    if args.json:
        payload = {
            "valid": result.valid,
            "scenario_count": result.scenario_count,
            "integration_test_valid": result.integration_test_valid,
            "ast_safety_valid": result.ast_safety_valid,
            "scenarios_valid": result.scenarios_valid,
            "rust_sensors_valid": result.rust_sensors_valid,
            "invariants_valid": result.invariants_valid,
            "issues": list(result.issues),
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.valid else 1

    print("=" * 78)
    print(" SYSTEM MIND X — macOS Integration Faults & Permission Denials Audit")
    print("=" * 78)
    print(f"Total Fault Scenarios:      {result.scenario_count}")
    print(f"Integration Tests Present:  {'PASS' if result.integration_test_valid else 'FAIL'}")
    print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, bounded timeouts)' if result.ast_safety_valid else 'FAIL'}")
    print(f"Fault Scenario Coverage:    {'PASS (All 8 fault scenarios verified)' if result.scenarios_valid else 'FAIL'}")
    print(f"Native Rust Sensor Parity:  {'PASS' if result.rust_sensors_valid else 'FAIL'}")
    print(f"Charter Invariant:          {'PASS (scan_proves_safe = False)' if result.invariants_valid else 'FAIL'}")
    print("-" * 78)

    if result.issues:
        print("Issues Detected:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("-" * 78)
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: ALL INTEGRATION FAULT CHECKS PASSED")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
