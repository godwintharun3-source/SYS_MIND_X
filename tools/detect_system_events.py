#!/usr/bin/env python3
"""CLI utility for auditing and interacting with append-only system event storage."""

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
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.system_events import SystemEventsValidator
from system_mind.twin.event_store import (
    SystemEventRecord,
    SystemEventStore,
    SystemEventType,
)
from system_mind.twin.identity import DeviceIdentifierManager, StableEntityIdGenerator


def seed_sample_events(store: SystemEventStore, device_id: str) -> list[SystemEventRecord]:
    """Populates an in-memory database with representative system events."""
    base_epoch = int(datetime.now(timezone.utc).timestamp() * 1000) - 10000

    host_urn = str(StableEntityIdGenerator.generate_host_urn(device_id))
    app_urn = str(StableEntityIdGenerator.generate_app_urn("com.google.chrome"))
    proc_parent = str(StableEntityIdGenerator.generate_process_urn(device_id, 1, 1000, "/sbin/launchd"))
    proc_child = str(
        StableEntityIdGenerator.generate_process_urn(
            device_id, 501, 2000, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
    )
    file_urn = str(StableEntityIdGenerator.generate_file_urn(device_id, "root_vol", "/etc/hosts"))

    corr_id = "corr-user-launch-001"

    events: list[SystemEventRecord] = []

    # 1. Application Installed
    e1 = store.append_event(
        device_id=device_id,
        entity_urn=app_urn,
        event_type=SystemEventType.APPLICATION_INSTALLED,
        payload={"bundle_id": "com.google.chrome", "version": "130.0.6723.117"},
        component_ownership=ComponentOwnership.USER_MANAGED,
        timestamp_epoch_ms=base_epoch,
        metadata={"installer": "Google Chrome.dmg"},
    )
    events.append(e1)

    # 2. Application Launched (tied to correlation_id)
    e2 = store.append_event(
        device_id=device_id,
        entity_urn=app_urn,
        event_type=SystemEventType.APPLICATION_LAUNCHED,
        payload={"executable": "/Applications/Google Chrome.app", "user": "localuser"},
        component_ownership=ComponentOwnership.USER_MANAGED,
        correlation_id=corr_id,
        causation_id=e1.event_id,
        timestamp_epoch_ms=base_epoch + 1000,
    )
    events.append(e2)

    # 3. Process Spawned (caused by e2)
    e3 = store.append_event(
        device_id=device_id,
        entity_urn=proc_child,
        event_type=SystemEventType.PROCESS_SPAWNED,
        payload={"pid": 45120, "ppid": 1, "parent_urn": proc_parent},
        component_ownership=ComponentOwnership.USER_MANAGED,
        correlation_id=corr_id,
        causation_id=e2.event_id,
        timestamp_epoch_ms=base_epoch + 1200,
    )
    events.append(e3)

    # 4. File Modified (hosts file configuration mutation)
    e4 = store.append_event(
        device_id=device_id,
        entity_urn=file_urn,
        event_type=SystemEventType.FILE_MODIFIED,
        payload={"path": "/etc/hosts", "size_bytes": 412, "action": "updated"},
        component_ownership=ComponentOwnership.SYSTEM_MANAGED,
        timestamp_epoch_ms=base_epoch + 3000,
    )
    events.append(e4)

    # 5. Network Interface State Changed
    e5 = store.append_event(
        device_id=device_id,
        entity_urn=host_urn,
        event_type=SystemEventType.NETWORK_INTERFACE_STATE,
        payload={"interface": "en0", "link_state": "UP", "ip": "192.168.1.100"},
        component_ownership=ComponentOwnership.SYSTEM_MANAGED,
        timestamp_epoch_ms=base_epoch + 4000,
    )
    events.append(e5)

    # 6. Process Exited (child process shutdown)
    e6 = store.append_event(
        device_id=device_id,
        entity_urn=proc_child,
        event_type=SystemEventType.PROCESS_EXITED,
        payload={"pid": 45120, "exit_code": 0, "signal": None},
        component_ownership=ComponentOwnership.USER_MANAGED,
        correlation_id=corr_id,
        causation_id=e3.event_id,
        timestamp_epoch_ms=base_epoch + 5000,
    )
    events.append(e6)

    return events


def run_audit(json_output: bool) -> int:
    """Performs packaging and safety invariant audit for Day 070."""
    result = SystemEventsValidator.audit()

    if json_output:
        payload = {
            "valid": result.valid,
            "issues": list(result.issues),
            "migration_present": result.migration_present,
            "models_present": result.models_present,
            "design_note_present": result.design_note_present,
            "tool_present": result.tool_present,
            "ast_safety_valid": result.ast_safety_valid,
            "charter_invariants_valid": result.charter_invariants_valid,
            "immutability_triggers_valid": result.immutability_triggers_valid,
            "hash_chain_valid": result.hash_chain_valid,
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.valid else 1

    print("=" * 78)
    print(" SYSTEM MIND X — Append-Only System Event Storage Packaging Audit")
    print("=" * 78)
    print(f"Overall Valid:              {'PASS' if result.valid else 'FAIL'}")
    print(f"Migration 0006:             {'PASS' if result.migration_present else 'FAIL'}")
    print(f"Event Store Models:         {'PASS' if result.models_present else 'FAIL'}")
    print(f"Design Documentation:       {'PASS' if result.design_note_present else 'FAIL'}")
    print(f"CLI Utility:                {'PASS' if result.tool_present else 'FAIL'}")
    print(f"AST Safety (SC-01):         {'PASS' if result.ast_safety_valid else 'FAIL'} (Zero shell=True, zero os.system)")
    print(f"Charter Invariant (SC-03):  {'PASS' if result.charter_invariants_valid else 'FAIL'} (scan_proves_safe = False)")
    print(f"Immutability Triggers:      {'PASS' if result.immutability_triggers_valid else 'FAIL'} (UPDATE/DELETE blocked)")
    print(f"Cryptographic Hash Chain:   {'PASS' if result.hash_chain_valid else 'FAIL'} (SHA-256 tamper-evident)")
    print("-" * 78)

    if result.issues:
        print("Audit Issues Found:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("-" * 78)
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: PASSED")
    return 0


def run_inspect(json_output: bool) -> int:
    """Migrates an in-memory database, seeds events, verifies chain, and prints summary."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    migrator.apply_all(conn=conn)

    device_id = DeviceIdentifierManager.resolve_device_id()
    store = SystemEventStore(conn)
    events = seed_sample_events(store, device_id)

    total_events = store.count_events()
    is_valid, verified_count, err = store.verify_chain_integrity()

    # Demonstrate SQLite trigger immutability enforcement
    trigger_enforced = False
    try:
        conn.execute("UPDATE system_events SET event_type = 'TAMPERED' WHERE sequence_number = 1;")
    except (sqlite3.IntegrityError, sqlite3.OperationalError) as ex:
        if "System events are append-only" in str(ex):
            trigger_enforced = True

    # Filtered correlation query
    corr_events = store.query_events(correlation_id="corr-user-launch-001")

    if json_output:
        payload = {
            "device_id": device_id,
            "total_events": total_events,
            "chain_valid": is_valid,
            "verified_count": verified_count,
            "trigger_enforced": trigger_enforced,
            "events": [e.to_dict() for e in events],
            "correlation_query": [e.to_dict() for e in corr_events],
        }
        print(json.dumps(payload, indent=2))
        conn.close()
        return 0

    print("=" * 78)
    print(" SYSTEM MIND X — Append-Only System Event Storage Summary")
    print("=" * 78)
    print(f"Database Target:            :memory:")
    print(f"Active Device ID:           {device_id}")
    print(f"Total Events Appended:      {total_events}")
    print(f"Hash Chain Integrity:       {'VERIFIED (Valid unbroken chain)' if is_valid else f'BROKEN ({err})'}")
    print(f"Database Trigger Protection: {'ACTIVE (UPDATE/DELETE prohibited by engine)' if trigger_enforced else 'INACTIVE'}")
    print(f"Charter Invariant:          scan_proves_safe = False (Enforced)")
    print("-" * 78)
    print("Cryptographically Chained System Events:")
    for e in events:
        ownership_tag = f"[{e.component_ownership.value}]"
        print(
            f"  seq={e.sequence_number:<2} | {e.event_type:<24} | {ownership_tag:<18} | {e.entity_urn}"
        )
        print(f"         time={e.timestamp_iso} | prev_hash={e.prev_event_hash[:12]}... | hash={e.event_hash[:12]}...")
        if e.correlation_id:
            print(f"         corr_id={e.correlation_id} | causation_id={e.causation_id}")
        print(f"         payload={json.dumps(e.payload)}")

    print("-" * 78)
    print("Correlated Transaction Query (corr-user-launch-001):")
    for ce in corr_events:
        print(f"  ^ seq={ce.sequence_number} -> {ce.event_type} on {ce.entity_urn}")
    print("=" * 78)

    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and audit SYSTEM MIND X append-only system event storage."
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run packaging and safety invariant audit on event persistence components.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in structured JSON format.",
    )
    args = parser.parse_args()

    if args.audit:
        return run_audit(args.json)
    return run_inspect(args.json)


if __name__ == "__main__":
    sys.exit(main())
