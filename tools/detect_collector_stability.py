#!/usr/bin/env python3
"""CLI utility running and auditing telemetry collector stability under sustained event volume."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.packaging.macos_collector_stability import MacOsCollectorStabilityValidator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit telemetry collector stability under sustained event volume."
    )
    parser.add_argument("--json", action="store_true", help="Output audit results in JSON format")
    parser.add_argument("--verbose", action="store_true", help="Display verbose diagnostic details")
    args = parser.parse_args()

    validator = MacOsCollectorStabilityValidator(root_dir=ROOT_DIR)
    result = validator.audit()

    if args.json:
        payload = {
            "valid": result.valid,
            "scenario_count": result.scenario_count,
            "stability_test_valid": result.stability_test_valid,
            "ast_safety_valid": result.ast_safety_valid,
            "scenarios_valid": result.scenarios_valid,
            "rust_sensors_valid": result.rust_sensors_valid,
            "invariants_valid": result.invariants_valid,
            "cli_valid": result.cli_valid,
            "issues": list(result.issues),
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.valid else 1

    print("=" * 78)
    print(" SYSTEM MIND X — Telemetry Collector Stability Under Sustained Volume")
    print("=" * 78)
    print(f"Total Stress Scenarios:     {result.scenario_count}")
    print(f"Stability Tests Present:    {'PASS' if result.stability_test_valid else 'FAIL'}")
    print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, bounded timeouts)' if result.ast_safety_valid else 'FAIL'}")
    print(f"Stress Scenario Coverage:   {'PASS (All 8 stress scenarios verified)' if result.scenarios_valid else 'FAIL'}")
    print(f"Native Rust Sensor Parity:  {'PASS' if result.rust_sensors_valid else 'FAIL'}")
    print(f"Charter Invariant:          {'PASS (scan_proves_safe = False)' if result.invariants_valid else 'FAIL'}")
    print(f"CLI Tool Presence:          {'PASS' if result.cli_valid else 'FAIL'}")
    print("-" * 78)

    if result.issues:
        print("Issues Detected:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("-" * 78)
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: PASSED (All collector stability invariants verified)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
