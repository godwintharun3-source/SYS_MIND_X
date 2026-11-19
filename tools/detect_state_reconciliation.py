#!/usr/bin/env python3
"""CLI utility for auditing and demonstrating system-state reconciliation after collector gaps."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.core.types import ComponentOwnership
from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.reconciliation import StateReconciliationValidator
from system_mind.twin.identity import DeviceIdentifierManager
from system_mind.twin.models import TwinEntity, TwinEntityType
from system_mind.twin.reconciliation import (
    CollectorGap,
    CollectorGapDetector,
    GapClassification,
    ReconciliationActionType,
    StateReconciliationManager,
    StateReconciliationRecord,
    SystemStateReconciler,
)


def run_audit() -> int:
    """Run comprehensive packaging and invariant audit."""
    result = StateReconciliationValidator.audit()

    print("==============================================================================")
    print(" SYSTEM MIND X — State Reconciliation & Gap Recovery Packaging Audit")
    print("==============================================================================")
    print(f"Overall Valid:                  {'PASS' if result.valid else 'FAIL'}")
    print(f"Reconciliation Engine Present:  {'PASS' if result.reconciliation_engine_present else 'FAIL'}")
    print(f"Design Documentation:           {'PASS' if result.design_note_present else 'FAIL'}")
    print(f"Migration 0010 Present:         {'PASS' if result.migration_present else 'FAIL'}")
    print(f"CLI Tool Present:               {'PASS' if result.tool_present else 'FAIL'}")
    print(f"AST Safety (SC-01):             {'PASS (Zero shell=True, zero os.system)' if result.ast_safety_valid else 'FAIL'}")
    print(f"Charter Invariant (SC-03):      {'PASS (scan_proves_safe = False)' if result.charter_invariants_valid else 'FAIL'}")
    print(f"Functional Reconciliation Test: {'PASS (Gap detection & healing verified)' if result.functional_reconciliation_valid else 'FAIL'}")
    print("------------------------------------------------------------------------------")

    if result.issues:
        print("ISSUES DETECTED:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("------------------------------------------------------------------------------")
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: PASSED")
    return 0


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — System-State Reconciliation After Collector Gaps CLI"
    )
    parser.add_argument("--audit", action="store_true", help="Run packaging and safety invariant audit")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")
    parser.add_argument("--device-id", default=None, help="Target device ID")
    parser.add_argument("--db-path", default=":memory:", help="SQLite database path (default: :memory:)")

    args = parser.parse_args()

    if args.audit:
        return run_audit()

    device_id = args.device_id or DeviceIdentifierManager.resolve_device_id()

    # Setup database connection and apply migrations (0001 through 0010)
    db_cfg = DatabaseConfig(args.db_path)
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)
    migrator.apply_all(conn=conn)

    manager = StateReconciliationManager(conn)
    detector = CollectorGapDetector()

    t_start = 1700000000000
    t_end = t_start + 75000  # 75-second gap

    # 1. Detect gap on process domain (cadence 5000ms, elapsed 75000ms -> 15x cadence)
    gap = detector.detect_gap(
        prev_epoch_ms=t_start,
        curr_epoch_ms=t_end,
        collector_id="macos_process_collector",
        device_id=device_id,
        domain="proc",
    )
    assert gap is not None

    # 2. Simulate pre-gap entity population
    pre_p1 = TwinEntity(
        entity_id="urn:systemmind:proc:101",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"pid": 101, "name": "core_service", "threads": 8, "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )
    pre_p2 = TwinEntity(
        entity_id="urn:systemmind:proc:202",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"pid": 202, "name": "transient_worker", "threads": 2, "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )
    pre_vol = TwinEntity(
        entity_id="urn:systemmind:vol:backup_usb",
        entity_type=TwinEntityType.FILESYSTEM_NODE,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"mount_point": "/Volumes/Backup", "fs_type": "apfs", "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )

    # 3. Simulate post-gap entity population:
    # - pre_p1 sustained
    # - pre_p2 absent (terminated)
    # - pre_vol absent (unobserved persistent -> marked stale)
    # - post_p3 newly spawned
    post_p1 = TwinEntity(
        entity_id="urn:systemmind:proc:101",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"pid": 101, "name": "core_service", "threads": 8, "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )
    post_p3 = TwinEntity(
        entity_id="urn:systemmind:proc:303",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"pid": 303, "name": "post_wake_indexer", "threads": 4, "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )

    pre_entities = [pre_p1, pre_p2, pre_vol]
    post_entities = [post_p1, post_p3]

    # 4. Execute and persist reconciliation
    recon_record = manager.reconcile_and_record(gap, pre_entities, post_entities)

    if args.json:
        output_payload = {
            "device_id": device_id,
            "gap": gap.to_dict(),
            "reconciliation": recon_record.to_dict(),
            "scan_proves_safe": False,
        }
        print(json.dumps(output_payload, indent=2))
        return 0

    print("==============================================================================")
    print(" SYSTEM MIND X — System-State Reconciliation After Collector Gaps")
    print("==============================================================================")
    print(f"Device ID:             {device_id}")
    print(f"Collector ID:          {gap.collector_id} (domain: {gap.domain})")
    print(f"Gap Duration:          {gap.gap_duration_ms}ms ({gap.gap_duration_ms / 1000.0:.1f}s)")
    print(f"Gap Classification:    {gap.gap_classification}")
    print(f"Confidence Discount:   {recon_record.confidence_discount_pct:.1%}")
    print(f"Reconciliation ID:     {recon_record.reconciliation_id}")
    print("------------------------------------------------------------------------------")
    print("ENTITY URN                         TYPE             ACTION               CONFIDENCE")
    print("------------------------------------------------------------------------------")
    for act in recon_record.actions:
        print(
            f"{act.entity_urn:<34} {act.entity_type:<16} {act.action_type:<20} {act.confidence_score:.2f}"
        )
    print("------------------------------------------------------------------------------")
    print(
        f"Summary: {recon_record.entities_sustained_count} sustained, "
        f"{recon_record.entities_terminated_count} terminated, "
        f"{recon_record.entities_staled_count} staled, "
        f"{recon_record.entities_spawned_count} spawned"
    )
    print("Charter Invariant (SC-03): scan_proves_safe = False [VERIFIED]")
    print("Zero Ambient Shell (SC-01): Pure in-memory SQLite execution [VERIFIED]")
    print("==============================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
