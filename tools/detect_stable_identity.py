#!/usr/bin/env python3
"""CLI utility resolving stable device identifiers and auditing digital twin entity URNs."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.packaging.twin_identity import TwinIdentityValidator
from system_mind.twin.identity import (
    DeviceIdentifierManager,
    EntityDomain,
    StableEntityIdGenerator,
    validate_entity_urn,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve stable device identifier and generate canonical digital twin entity URNs."
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--mock", action="store_true", help="Use mock platform profile instead of live hardware anchor")
    parser.add_argument("--audit", action="store_true", help="Execute packaging and safety invariant audit")
    parser.add_argument("--verbose", action="store_true", help="Display verbose diagnostic details")
    args = parser.parse_args()

    if args.audit:
        result = TwinIdentityValidator.audit(root_dir=ROOT_DIR)
        if args.json:
            payload = {
                "valid": result.valid,
                "issues": list(result.issues),
                "python_identity_present": result.python_identity_present,
                "rust_identity_present": result.rust_identity_present,
                "design_note_present": result.design_note_present,
                "tool_present": result.tool_present,
                "ast_safety_valid": result.ast_safety_valid,
                "charter_invariants_valid": result.charter_invariants_valid,
                "domains_count": result.domains_count,
            }
            print(json.dumps(payload, indent=2))
            return 0 if result.valid else 1

        print("=" * 78)
        print(" SYSTEM MIND X — Digital Twin Entity Identity Packaging Audit")
        print("=" * 78)
        print(f"Overall Valid:              {'PASS' if result.valid else 'FAIL'}")
        print(f"Python Module:              {'PASS' if result.python_identity_present else 'FAIL'}")
        print(f"Rust Module:                {'PASS' if result.rust_identity_present else 'FAIL'}")
        print(f"Design Documentation:       {'PASS' if result.design_note_present else 'FAIL'}")
        print(f"CLI Tool Present:           {'PASS' if result.tool_present else 'FAIL'}")
        print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, zero os.system)' if result.ast_safety_valid else 'FAIL'}")
        print(f"Charter Invariant (SC-03):  {'PASS (scan_proves_safe = False)' if result.charter_invariants_valid else 'FAIL'}")
        print(f"Canonical Domains:          {result.domains_count} domains registered")
        print("-" * 78)

        if result.issues:
            print("Issues Detected:")
            for issue in result.issues:
                print(f"  [!] {issue}")
            print("-" * 78)
            print("OVERALL VERDICT: FAILED")
            return 1

        print("OVERALL VERDICT: PASSED")
        return 0

    # Resolve device ID
    if args.mock:
        device_id = DeviceIdentifierManager.resolve_device_id(
            hardware_uuid="mock-hardware-anchor-uuid-00000000-0000",
            use_cache=False,
        )
        mode = "MOCK_SIMULATION"
    else:
        device_id = DeviceIdentifierManager.resolve_device_id(use_cache=True)
        mode = "LIVE_SYSTEM"

    now_epoch_ms = int(time.time() * 1000)

    # Derive sample URNs across all entity domains
    urns = {
        "host": str(StableEntityIdGenerator.generate_host_urn(device_id)),
        "kernel": str(
            StableEntityIdGenerator.generate_kernel_urn(
                platform.system(), platform.release(), platform.machine()
            )
        ),
        "cpu": str(
            StableEntityIdGenerator.generate_cpu_urn(
                platform.machine() or "arm64",
                "Apple M-Series Simulated" if args.mock else platform.processor() or "Apple M3",
                core_count=12,
            )
        ),
        "memory": str(StableEntityIdGenerator.generate_memory_urn(device_id, 34359738368)),
        "storage_volume": str(
            StableEntityIdGenerator.generate_storage_volume_urn(
                device_id, "4B1E8C22-8A2D-4C2E-8E99-7D22B4A1D888"
            )
        ),
        "network_interface": str(
            StableEntityIdGenerator.generate_network_interface_urn(device_id, "en0")
        ),
        "application": str(
            StableEntityIdGenerator.generate_app_urn("com.systemmind.operator")
        ),
        "process": str(
            StableEntityIdGenerator.generate_process_urn(
                device_id,
                pid=1234,
                start_time_epoch_ms=now_epoch_ms,
                binary_path="/usr/local/bin/system-mind-agent",
            )
        ),
        "service": str(
            StableEntityIdGenerator.generate_service_urn(
                "gui.501", "com.systemmind.useragent"
            )
        ),
        "file": str(
            StableEntityIdGenerator.generate_file_urn(
                device_id, "vol_root", "/System/Library/CoreServices/SystemVersion.plist"
            )
        ),
        "package": str(
            StableEntityIdGenerator.generate_package_urn("brew", "openssl@3", "3.2.1")
        ),
    }

    all_valid = all(validate_entity_urn(u) for u in urns.values())

    if args.json:
        payload = {
            "mode": mode,
            "device_id": device_id,
            "all_urns_valid": all_valid,
            "scan_proves_safe": False,
            "urns": urns,
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("=" * 78)
    print(" SYSTEM MIND X — Digital Twin Entity Identity Resolution")
    print("=" * 78)
    print(f"Collection Mode:        {mode}")
    print(f"Stable Device ID:       {device_id}")
    print(f"Charter Invariant:      scan_proves_safe = False (Enforced)")
    print(f"URN Syntax Validity:    {'ALL VALID' if all_valid else 'SYNTAX ERROR'}")
    print("-" * 78)
    print("Canonical Entity URN Samples:")
    for domain_name, urn_str in urns.items():
        print(f"  {domain_name:<18} -> {urn_str}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
