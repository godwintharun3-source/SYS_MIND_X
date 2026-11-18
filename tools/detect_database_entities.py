#!/usr/bin/env python3
"""CLI utility for auditing and interacting with digital twin database entity models."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.core.types import ComponentOwnership
from system_mind.database.entity_models import (
    ApplicationEntityRecord,
    HardwareCategory,
    HardwareEntityRecord,
    OsKernelEntityRecord,
)
from system_mind.database.entity_repo import EntityRepository
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.database_entities import DatabaseEntitiesValidator
from system_mind.twin.identity import DeviceIdentifierManager, StableEntityIdGenerator


def seed_sample_entities(repo: EntityRepository, device_id: str) -> None:
    """Seed sample hardware, OS, and application entity records."""
    # 1. Hardware Entities
    host_urn = str(StableEntityIdGenerator.generate_host_urn(device_id))
    repo.save_hardware_entity(
        HardwareEntityRecord(
            entity_urn=host_urn,
            device_id=device_id,
            category=HardwareCategory.HOST,
            model_name="MacBookAir10,1 (Apple Silicon M1)",
            vendor="Apple Inc.",
            serial_hash=StableEntityIdGenerator.hash_token("MOCK-SERIAL-001"),
            attributes={"cpu_arch": "arm64", "p_cores": 4, "e_cores": 4},
            provenance_source="native_ioreg",
        )
    )

    cpu_urn = str(StableEntityIdGenerator.generate_cpu_urn("arm64", "Apple M1", 8))
    repo.save_hardware_entity(
        HardwareEntityRecord(
            entity_urn=cpu_urn,
            device_id=device_id,
            category=HardwareCategory.CPU,
            model_name="Apple M1",
            vendor="Apple Inc.",
            attributes={"cores_total": 8, "cores_p": 4, "cores_e": 4, "frequency_mhz": 3200},
            provenance_source="native_sysctl",
        )
    )

    mem_urn = str(StableEntityIdGenerator.generate_memory_urn(device_id, 17179869184))
    repo.save_hardware_entity(
        HardwareEntityRecord(
            entity_urn=mem_urn,
            device_id=device_id,
            category=HardwareCategory.MEMORY,
            model_name="Unified LPDDR4X",
            attributes={"total_bytes": 17179869184, "page_size": 16384},
            provenance_source="native_vm_stat",
        )
    )

    # 2. OS Kernel Entity
    kernel_urn = str(StableEntityIdGenerator.generate_kernel_urn("Darwin", "24.0.0", "arm64"))
    repo.save_os_kernel_entity(
        OsKernelEntityRecord(
            entity_urn=kernel_urn,
            device_id=device_id,
            os_family="Darwin",
            product_version="15.0",
            build_version="24A348",
            kernel_release="24.0.0",
            architecture="arm64",
            security_posture={
                "sip_enabled": True,
                "gatekeeper_enabled": True,
                "filevault_enabled": True,
                "firewall_enabled": True,
            },
            provenance_source="native_sysctl",
        )
    )

    # 3. Application Entities (with ownership tiers)
    app1_urn = str(StableEntityIdGenerator.generate_app_urn("com.apple.finder"))
    repo.save_application_entity(
        ApplicationEntityRecord(
            entity_urn=app1_urn,
            device_id=device_id,
            bundle_id="com.apple.finder",
            app_name="Finder",
            version="15.0",
            install_path="/System/Library/CoreServices/Finder.app",
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            code_signature={"signed": True, "apple_signed": True, "notarized": True},
            provenance_source="app_detector",
        )
    )

    app2_urn = str(StableEntityIdGenerator.generate_app_urn("com.google.chrome"))
    repo.save_application_entity(
        ApplicationEntityRecord(
            entity_urn=app2_urn,
            device_id=device_id,
            bundle_id="com.google.Chrome",
            app_name="Google Chrome",
            version="130.0.6723.117",
            install_path="/Applications/Google Chrome.app",
            ownership=ComponentOwnership.VENDOR_MANAGED,
            code_signature={"signed": True, "apple_signed": False, "notarized": True},
            provenance_source="app_detector",
        )
    )

    app3_urn = str(StableEntityIdGenerator.generate_app_urn("com.user.localproject"))
    repo.save_application_entity(
        ApplicationEntityRecord(
            entity_urn=app3_urn,
            device_id=device_id,
            bundle_id="com.user.localproject",
            app_name="Local Project Tool",
            version="0.1.0",
            install_path="/Users/user/Projects/localproject/bin/tool",
            ownership=ComponentOwnership.USER_MANAGED,
            code_signature={"signed": False, "apple_signed": False, "notarized": False},
            provenance_source="app_detector",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit and inspect digital twin database entity models for Hardware, OS, and Applications."
    )
    parser.add_argument("--db", default=":memory:", help="SQLite database path (default: in-memory)")
    parser.add_argument("--audit", action="store_true", help="Execute packaging and safety invariant audit")
    parser.add_argument("--seed-mock", action="store_true", help="Seed sample mock hardware, OS, and app records")
    parser.add_argument("--query", action="store_true", help="Query and list stored database entities")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    if args.audit:
        result = DatabaseEntitiesValidator.audit(root_dir=ROOT_DIR)
        if args.json:
            payload = {
                "valid": result.valid,
                "issues": list(result.issues),
                "migration_present": result.migration_present,
                "models_present": result.models_present,
                "repository_present": result.repository_present,
                "design_note_present": result.design_note_present,
                "tool_present": result.tool_present,
                "ast_safety_valid": result.ast_safety_valid,
                "charter_invariants_valid": result.charter_invariants_valid,
                "lifecycle_roundtrip_valid": result.lifecycle_roundtrip_valid,
            }
            print(json.dumps(payload, indent=2))
            return 0 if result.valid else 1

        print("=" * 78)
        print(" SYSTEM MIND X — Digital Twin Database Entities Packaging Audit")
        print("=" * 78)
        print(f"Overall Valid:              {'PASS' if result.valid else 'FAIL'}")
        print(f"Migration 0003:             {'PASS' if result.migration_present else 'FAIL'}")
        print(f"Entity Models:              {'PASS' if result.models_present else 'FAIL'}")
        print(f"Entity Repository:          {'PASS' if result.repository_present else 'FAIL'}")
        print(f"Design Documentation:       {'PASS' if result.design_note_present else 'FAIL'}")
        print(f"CLI Tool:                   {'PASS' if result.tool_present else 'FAIL'}")
        print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, zero os.system)' if result.ast_safety_valid else 'FAIL'}")
        print(f"Charter Invariant (SC-03):  {'PASS (scan_proves_safe = False)' if result.charter_invariants_valid else 'FAIL'}")
        print(f"Migration Lifecycle:        {'PASS (Roundtrip Up/Down verified)' if result.lifecycle_roundtrip_valid else 'FAIL'}")
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

    # Default action: run migrations, optionally seed, and query
    migrator = DatabaseMigrator(db_path=args.db)
    conn = migrator._get_connection()
    try:
        migrator.apply_all(conn=conn)
        repo = EntityRepository(conn)
        device_id = DeviceIdentifierManager.resolve_device_id(
            hardware_uuid="mock-hardware-anchor-device-067",
            use_cache=False,
        )

        if args.seed_mock or args.db == ":memory:":
            seed_sample_entities(repo, device_id)

        counts = repo.count_entities()
        hw_list = repo.list_hardware_entities()
        os_list = repo.list_os_kernel_entities()
        app_list = repo.list_application_entities()

        if args.json:
            payload = {
                "db": args.db,
                "device_id": device_id,
                "counts": counts,
                "scan_proves_safe": False,
                "hardware": [h.to_dict() for h in hw_list],
                "os_kernel": [o.to_dict() for o in os_list],
                "applications": [a.to_dict() for a in app_list],
            }
            print(json.dumps(payload, indent=2))
            return 0

        print("=" * 78)
        print(" SYSTEM MIND X — Digital Twin Database Entities Summary")
        print("=" * 78)
        print(f"Database Target:            {args.db}")
        print(f"Active Device ID:           {device_id}")
        print(f"Hardware Entities:          {counts['hardware']}")
        print(f"OS Kernel Entities:         {counts['os_kernel']}")
        print(f"Application Entities:       {counts['applications']}")
        print(f"Total Stored Entities:      {counts['total']}")
        print(f"Charter Invariant:          scan_proves_safe = False (Enforced)")
        print("-" * 78)
        print("Hardware Entities:")
        for h in hw_list:
            print(f"  [{h.category.value:<8}] {h.model_name:<30} -> {h.entity_urn}")
        print("\nOS Kernel Entities:")
        for o in os_list:
            print(f"  [{o.os_family:<8}] {o.product_version} ({o.build_version}) -> {o.entity_urn}")
        print("\nApplication Entities:")
        for a in app_list:
            print(f"  [{a.ownership.value:<15}] {a.app_name:<22} -> {a.entity_urn}")
        print("=" * 78)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
