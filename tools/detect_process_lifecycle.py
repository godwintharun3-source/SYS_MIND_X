#!/usr/bin/env python3
"""Developer CLI tool to detect process start and exit events, audit invariants, and simulate process lifecycle transitions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List

# Add src to pythonpath
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.core.types import ComponentOwnership
from system_mind.packaging.process_lifecycle import ProcessLifecycleValidator
from system_mind.twin.event_store import SystemEventStore
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import StableEntityIdGenerator
from system_mind.twin.models import TwinEntity, TwinEntityType
from system_mind.twin.process_lifecycle import (
    ProcessDetectionSource,
    ProcessExitStatus,
    ProcessLifecycleDiff,
    ProcessLifecycleEvent,
    ProcessLifecycleEventType,
    ProcessLifecycleManager,
    ProcessLifecycleTracker,
)


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Applies all SQLite schema migrations from 0001 to 0012 in memory."""
    migrations_dir = REPO_ROOT / "src/system_mind/database/migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    for mf in migration_files:
        content = mf.read_text(encoding="utf-8")
        up_script = content.split("-- DOWN")[0].replace("-- UP", "")
        conn.executescript(up_script)


def run_audit() -> int:
    """Runs packaging, AST safety, and invariant audit for Day 077."""
    print("[*] SYSTEM MIND X — Process Start & Exit Tracking Invariant Audit")
    print(f"[*] Monorepo root: {REPO_ROOT}")
    print("-" * 65)

    result = ProcessLifecycleValidator.audit(REPO_ROOT)
    print(f"[*] process_lifecycle_present: {'PASSED' if result.process_lifecycle_present else 'FAILED'}")
    print(f"[*] design_note_present:       {'PASSED' if result.design_note_present else 'FAILED'}")
    print(f"[*] migration_present:         {'PASSED' if result.migration_present else 'FAILED'}")
    print(f"[*] tool_present:              {'PASSED' if result.tool_present else 'FAILED'}")
    print(f"[*] ast_safety_valid:          {'PASSED' if result.ast_safety_valid else 'FAILED'}")
    print(f"[*] charter_invariants_valid:  {'PASSED' if result.charter_invariants_valid else 'FAILED'}")
    print(f"[*] functional_valid:          {'PASSED' if result.functional_lifecycle_valid else 'FAILED'}")
    print("-" * 65)

    if result.issues:
        print("[!] Audit issues detected:")
        for issue in result.issues:
            print(f"    - {issue}")
        print("\n[FAILED] Audit failed.")
        return 1
    else:
        print(f"[+] All 7 audit checks PASSED. Overall status: {'PASSED' if result.valid else 'FAILED'}")
        return 0


def run_simulation() -> int:
    """Simulates multi-channel process lifecycle tracking (process table diff + Endpoint Security)."""
    print("[*] SYSTEM MIND X — Process Start & Exit Tracking Simulation")
    print("-" * 65)

    device_id = "00000000-0000-4000-8000-000000000077"
    host_urn = f"urn:systemmind:host:{device_id}"

    # 1. Initialize in-memory SQLite database with migrations 0001..0012
    print("[1] Initializing in-memory SQLite database and applying migrations 0001..0012...")
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)

    event_store = SystemEventStore(conn)
    graph = DigitalTwinGraph()

    # Seed host entity in graph
    graph.add_entity(
        TwinEntity(
            entity_id=host_urn,
            entity_type=TwinEntityType.HOST,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            attributes={"hostname": "systemmind-dev", "platform": "darwin"},
            provenance_source="host_inspector",
            is_stale=False,
        )
    )

    t0_epoch_ms = 1700000000000

    # 2. Baseline Process Snapshot (t = 0)
    print("\n[2] Setting baseline process table (t = 0)...")
    baseline_processes = [
        {"pid": 1, "ppid": 0, "name": "launchd", "command_path": "/sbin/launchd", "user": "root", "uid": 0, "start_time_epoch_ms": t0_epoch_ms - 100000, "is_system_core": True},
        {"pid": 150, "ppid": 1, "name": "logd", "command_path": "/usr/libexec/logd", "user": "root", "uid": 0, "start_time_epoch_ms": t0_epoch_ms - 90000, "is_system_core": True},
        {"pid": 300, "ppid": 1, "name": "Terminal", "command_path": "/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t0_epoch_ms - 60000, "is_system_core": False},
        {"pid": 305, "ppid": 300, "name": "login", "command_path": "/usr/bin/login", "user": "root", "uid": 0, "start_time_epoch_ms": t0_epoch_ms - 55000, "is_system_core": True},
        {"pid": 310, "ppid": 305, "name": "zsh", "command_path": "/bin/zsh", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t0_epoch_ms - 50000, "is_system_core": False},
        {"pid": 450, "ppid": 310, "name": "curl", "command_path": "/usr/bin/curl", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t0_epoch_ms - 5000, "is_system_core": False},
    ]
    print(f"    Baseline running processes: {len(baseline_processes)} processes.")
    for p in baseline_processes:
        print(f"      - PID {p['pid']:<5} (PPID {p['ppid']:<5}) {p['name']:<12} -> {p['command_path']}")

    # 3. Observation T1 Snapshot (t = +10s)
    # PID 450 (curl) exited.
    # PID 500 (python3) started.
    # PID 510 (git) started.
    # PID 450 recycled with new start time for 'sleep'!
    t1_epoch_ms = t0_epoch_ms + 10000
    print(f"\n[3] Observing process table at t = +10s ({t1_epoch_ms})...")
    current_processes = [
        {"pid": 1, "ppid": 0, "name": "launchd", "command_path": "/sbin/launchd", "user": "root", "uid": 0, "start_time_epoch_ms": t0_epoch_ms - 100000, "is_system_core": True},
        {"pid": 150, "ppid": 1, "name": "logd", "command_path": "/usr/libexec/logd", "user": "root", "uid": 0, "start_time_epoch_ms": t0_epoch_ms - 90000, "is_system_core": True},
        {"pid": 300, "ppid": 1, "name": "Terminal", "command_path": "/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t0_epoch_ms - 60000, "is_system_core": False},
        {"pid": 305, "ppid": 300, "name": "login", "command_path": "/usr/bin/login", "user": "root", "uid": 0, "start_time_epoch_ms": t0_epoch_ms - 55000, "is_system_core": True},
        {"pid": 310, "ppid": 305, "name": "zsh", "command_path": "/bin/zsh", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t0_epoch_ms - 50000, "is_system_core": False},
        # Recycled PID 450: started at t1 - 2000 ms with 'sleep'
        {"pid": 450, "ppid": 310, "name": "sleep", "command_path": "/bin/sleep", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t1_epoch_ms - 2000, "is_system_core": False},
        # New PID 500: python3
        {"pid": 500, "ppid": 310, "name": "python3", "command_path": "/opt/homebrew/bin/python3", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t1_epoch_ms - 8000, "is_system_core": False},
        # New PID 510: git status
        {"pid": 510, "ppid": 310, "name": "git", "command_path": "/usr/bin/git", "user": "tharungodwin", "uid": 501, "start_time_epoch_ms": t1_epoch_ms - 1000, "is_system_core": False},
    ]

    # Diff evaluation
    diff = ProcessLifecycleTracker.diff_process_tables(
        baseline_processes=baseline_processes,
        current_processes=current_processes,
        device_id=device_id,
        observed_at_epoch_ms=t1_epoch_ms,
    )
    print(f"    [+] Diff detected {diff.total_transitions} lifecycle events:")
    print(f"        - Started: {len(diff.started_events)}")
    print(f"        - Exited:  {len(diff.exited_events)}")

    for ev in diff.all_events:
        print(f"        * [{ev.event_type.value}] PID {ev.pid} ({ev.process_name}) -> URN: {ev.entity_urn} (Ownership: {ev.ownership.value})")

    # 4. Real-time Endpoint Security Event Simulation (Channel B)
    print("\n[4] Simulating real-time Endpoint Security NOTIFY_EXIT event...")
    es_exit_event = {
        "event_type": "NOTIFY_EXIT",
        "action_type": "NOTIFY",
        "process_pid": 510,
        "process_ppid": 310,
        "executable_path": "/usr/bin/git",
        "is_platform_binary": True,
        "cdhash": "a1b2c3d4e5f60077",
    }
    es_ev = ProcessLifecycleTracker.from_endpoint_security_event(
        es_event=es_exit_event,
        device_id=device_id,
        start_epoch_ms=t1_epoch_ms - 1000,
        exit_code=0,
        observed_at_epoch_ms=t1_epoch_ms + 500,
    )
    assert es_ev is not None
    print(f"    [+] Translated ES event -> [{es_ev.event_type.value}] PID {es_ev.pid} (exit_code: {es_ev.exit_code}, runtime: {es_ev.runtime_ms}ms)")

    all_events = [*diff.all_events, es_ev]

    # 5. Persist Lifecycle Events
    print(f"\n[5] Persisting {len(all_events)} events to SQLite schema (process_lifecycle_events)...")
    ProcessLifecycleManager.record_events(conn, all_events)
    persisted = ProcessLifecycleManager.get_events(conn, device_id=device_id)
    print(f"    [+] Successfully persisted and queried {len(persisted)} process lifecycle events.")

    # 6. Synchronize Digital Twin Graph
    print("\n[6] Synchronizing events into in-memory DigitalTwinGraph...")
    mutations = ProcessLifecycleTracker.sync_with_digital_twin(graph, all_events, host_urn=host_urn)
    print(f"    [+] Graph updated with {mutations} entity/relationship mutations.")
    print(f"    [+] Total entities in graph: {len(graph.entities)}")
    print(f"    [+] Total relationships in graph: {len(graph.relationships)}")

    # 7. Bridge to Append-Only SystemEventStore
    print("\n[7] Bridging events to append-only SystemEventStore with SHA-256 hash chaining...")
    event_records = ProcessLifecycleTracker.sync_with_event_store(all_events, event_store, correlation_id="corr-day-077")
    print(f"    [+] Appended {len(event_records)} records to event store.")
    is_valid, count, err = event_store.verify_chain_integrity()
    print(f"    [+] Cryptographic hash-chain integrity verification: {'VERIFIED' if is_valid else 'FAILED'} ({count} blocks)")

    # 8. Point-in-Time Reconstruction Verification
    print("\n[8] Exercising point-in-time process reconstruction...")
    procs_at_t0 = ProcessLifecycleManager.get_running_processes_at(conn, target_epoch_ms=t0_epoch_ms - 1000, device_id=device_id)
    pids_at_t0 = [p["pid"] for p in procs_at_t0]
    print(f"    Active processes at t0-1s: PIDs {pids_at_t0}")

    procs_at_t1 = ProcessLifecycleManager.get_running_processes_at(conn, target_epoch_ms=t1_epoch_ms + 100, device_id=device_id)
    pids_at_t1 = [p["pid"] for p in procs_at_t1]
    print(f"    Active processes at t1+100ms: PIDs {pids_at_t1}")

    # 9. Lineage Ancestry Traversal
    print("\n[9] Traversing process ancestry tree for PID 500 (python3)...")
    lineage = ProcessLifecycleManager.get_process_lineage(conn, diff.started_events[0].entity_urn)
    print(f"    [+] Lineage tree depth: {len(lineage)} frames.")
    for idx, frame in enumerate(lineage):
        print(f"        Step {idx}: PID {frame.pid:<5} ({frame.process_name}) -> {frame.entity_urn}")

    print("\n" + "=" * 65)
    print("[+] DAY 077 PROCESS LIFECYCLE SIMULATION COMPLETED CLEANLY.")
    print("=" * 65)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Day 077 Process Start and Exit Tracking CLI")
    parser.add_argument("--audit", action="store_true", help="Run packaging and invariant audit")
    args = parser.parse_args()

    if args.audit:
        return run_audit()
    return run_simulation()


if __name__ == "__main__":
    sys.exit(main())
