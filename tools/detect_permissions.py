#!/usr/bin/env python3
"""CLI utility inspecting and auditing macOS permission prompts, prompt trigger rules, and required entitlements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.packaging.macos_permissions import MacOsPermissionsValidator
from system_mind.macos.permission_inspector import MacOsPermissionInspector


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit macOS permission prompts, documentation, and required entitlements."
    )
    parser.add_argument("--json", action="store_true", help="Output audit results in JSON format")
    parser.add_argument("--verbose", action="store_true", help="Display verbose diagnostic details")
    args = parser.parse_args()

    validator = MacOsPermissionsValidator(root_dir=ROOT_DIR)
    result = validator.audit()

    inspector = MacOsPermissionInspector()
    manifest = inspector.inspect_permissions()

    if args.json:
        payload = {
            "valid": result.valid,
            "scenario_count": result.scenario_count,
            "doc_valid": result.doc_valid,
            "test_suite_valid": result.test_suite_valid,
            "cli_valid": result.cli_valid,
            "ast_safety_valid": result.ast_safety_valid,
            "scenarios_valid": result.scenarios_valid,
            "rust_sensors_valid": result.rust_sensors_valid,
            "invariants_valid": result.invariants_valid,
            "non_goals_valid": result.non_goals_valid,
            "issues": list(result.issues),
            "manifest": {
                "companion_mode": manifest.companion_mode,
                "host_platform": manifest.host_platform,
                "permissions_count": len(manifest.permissions),
                "entitlements_count": len(manifest.entitlements),
                "non_goals_count": len(manifest.non_goals_enforced),
                "scan_proves_safe": manifest.scan_proves_safe,
                "active_states": {k: v.value for k, v in manifest.active_states.items()},
            },
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.valid else 1

    print("=" * 78)
    print(" SYSTEM MIND X — macOS Permission Prompts & Required Entitlements Audit")
    print("=" * 78)
    print(f"Total Permission Scenarios: {result.scenario_count}")
    print(f"Canonical Documentation:    {'PASS (docs/MACOS_PERMISSIONS_AND_ENTITLEMENTS.md)' if result.doc_valid else 'FAIL'}")
    print(f"Test Suite Present:         {'PASS' if result.test_suite_valid else 'FAIL'}")
    print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, bounded timeouts)' if result.ast_safety_valid else 'FAIL'}")
    print(f"Permission Coverage:        {'PASS (All 8 core scenarios verified)' if result.scenarios_valid else 'FAIL'}")
    print(f"Native Rust Sensor Parity:  {'PASS' if result.rust_sensors_valid else 'FAIL'}")
    print(f"Charter Invariant:          {'PASS (scan_proves_safe = False)' if result.invariants_valid else 'FAIL'}")
    print(f"Prohibited Non-Goals:       {'PASS (Input Monitoring strictly banned)' if result.non_goals_valid else 'FAIL'}")
    print(f"CLI Tool Presence:          {'PASS' if result.cli_valid else 'FAIL'}")
    print("-" * 78)

    print("Active Permission States (Companion Agent User Space):")
    for perm_name, state in manifest.active_states.items():
        print(f"  - {perm_name:<26}: {state.value}")
    print("-" * 78)

    if result.issues:
        print("Issues Detected:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("-" * 78)
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: PASSED (All permission prompts and entitlements verified)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
