"""Comprehensive unit, integration, and safety invariant tests for Day 077 Process Start and Exit Tracking."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List
import uuid

import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.packaging.process_lifecycle import ProcessLifecycleValidator
from system_mind.twin.event_store import GENESIS_PREV_HASH, SystemEventStore, SystemEventType
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import StableEntityIdGenerator
from system_mind.twin.models import TwinEntity, TwinEntityType, TwinRelationType
from system_mind.twin.process_lifecycle import (
    ProcessDetectionSource,
    ProcessExitStatus,
    ProcessLifecycleDiff,
    ProcessLifecycleEvent,
    ProcessLifecycleEventType,
    ProcessLifecycleManager,
    ProcessLifecycleTracker,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_full_schema() -> str:
    """Combines all migrations 0001 through 0012 into a complete UP SQL script."""
    migrations_dir = REPO_ROOT / "src/system_mind/database/migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    script_parts = []
    for mf in migration_files:
        content = mf.read_text(encoding="utf-8")
        up_script = content.split("-- DOWN")[0].replace("-- UP", "")
        script_parts.append(up_script)
    return "\n;\n".join(script_parts)


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite database initialized with all schemas."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(get_full_schema())
    return conn


# --- Test 1: Migration 0012 UP and DOWN Lifecycle & Check Constraint ---

def test_migration_0012_up_and_down():
    """Verifies Migration 0012 schema creation, constraint enforcement, and rollback."""
    conn = sqlite3.connect(":memory:")
    # First apply prior migrations 0001..0011
    migrations_dir = REPO_ROOT / "src/system_mind/database/migrations"
    prior_files = sorted([f for f in migrations_dir.glob("*.sql") if not f.name.startswith("0012")])
    for pf in prior_files:
        content = pf.read_text(encoding="utf-8")
        conn.executescript(content.split("-- DOWN")[0].replace("-- UP", ""))

    migration_0012 = migrations_dir / "0012_process_lifecycle_events.sql"
    content = migration_0012.read_text(encoding="utf-8")
    up_sql = content.split("-- DOWN")[0].replace("-- UP", "")
    down_sql = content.split("-- DOWN")[1]

    # 1. Apply UP migration
    conn.executescript(up_sql)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='process_lifecycle_events'")
    assert cur.fetchone() is not None

    # Check indexes exist
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='process_lifecycle_events'")
    indexes = [row[0] for row in cur.fetchall()]
    assert "idx_proc_lifecycle_events_device_id" in indexes
    assert "idx_proc_lifecycle_events_entity_urn" in indexes
    assert "idx_proc_lifecycle_events_pid" in indexes
    assert "idx_proc_lifecycle_events_event_type" in indexes
    assert "idx_proc_lifecycle_events_epoch_ms" in indexes
    assert "idx_proc_lifecycle_events_ownership" in indexes
    assert "idx_proc_lifecycle_events_start_exit" in indexes

    # 2. Test SC-03 invariant: CHECK (scan_proves_safe = 0)
    valid_stmt = """
    INSERT INTO process_lifecycle_events (
        event_id, device_id, entity_urn, event_type, pid, ppid,
        process_name, binary_path, command_line, user_name, uid,
        start_epoch_ms, exit_epoch_ms, exit_code, exit_status,
        runtime_ms, ownership, detection_source, observed_at_iso,
        observed_at_epoch_ms, parent_entity_urn, app_entity_urn,
        metadata_json, scan_proves_safe
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cur.execute(
        valid_stmt,
        (
            "pevt-valid", "dev-1", "urn:systemmind:proc:dev1:1000:100:bin", "PROCESS_STARTED", 100, 1,
            "daemon", "/sbin/daemon", "/sbin/daemon", "root", 0,
            1000, None, None, "UNKNOWN", None, "SYSTEM_MANAGED",
            "PROCESS_TABLE_DIFF", "2026-11-18T12:00:00Z", 1000,
            None, None, "{}", 0
        )
    )

    # Attempt inserting scan_proves_safe = 1 -> must fail with IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute(
            valid_stmt,
            (
                "pevt-invalid", "dev-1", "urn:systemmind:proc:dev1:1000:101:bin", "PROCESS_STARTED", 101, 1,
                "bad", "/bin/bad", "/bin/bad", "root", 0,
                1000, None, None, "UNKNOWN", None, "SYSTEM_MANAGED",
                "PROCESS_TABLE_DIFF", "2026-11-18T12:00:00Z", 1000,
                None, None, "{}", 1  # VIOLATION
            )
        )

    # 3. Apply DOWN migration and verify complete rollback
    conn.executescript(down_sql)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='process_lifecycle_events'")
    assert cur.fetchone() is None
    conn.close()


# --- Test 2: ProcessLifecycleEvent Dataclass & Invariants ---

def test_process_lifecycle_event_dataclass_and_invariants():
    """Verifies ProcessLifecycleEvent field validation, SC-03 invariant, and temporal rules."""
    proc_urn = StableEntityIdGenerator.generate_process_urn("dev-1", 42, 1000, "/usr/bin/python3").urn
    ev = ProcessLifecycleEvent(
        event_id="pevt-1",
        device_id="dev-1",
        entity_urn=proc_urn,
        event_type=ProcessLifecycleEventType.PROCESS_STARTED,
        pid=42,
        ppid=1,
        process_name="python3",
        binary_path="/usr/bin/python3",
        command_line="python3 script.py",
        user_name="user",
        uid=501,
        start_epoch_ms=1000,
        scan_proves_safe=False,
    )
    assert ev.scan_proves_safe is False
    assert ev.entity_urn.startswith("urn:systemmind:proc:")

    # Enforce SC-03 invariant: scan_proves_safe=True must raise ValueError
    with pytest.raises(ValueError, match="Charter invariant violation"):
        ProcessLifecycleEvent(
            event_id="pevt-bad",
            device_id="dev-1",
            entity_urn=proc_urn,
            event_type=ProcessLifecycleEventType.PROCESS_STARTED,
            pid=42,
            ppid=1,
            process_name="python3",
            binary_path="/usr/bin/python3",
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    # Inverted temporal rule: exit_epoch_ms < start_epoch_ms must raise ValueError
    with pytest.raises(ValueError, match="cannot precede start_epoch_ms"):
        ProcessLifecycleEvent(
            event_id="pevt-inverted",
            device_id="dev-1",
            entity_urn=proc_urn,
            event_type=ProcessLifecycleEventType.PROCESS_EXITED,
            pid=42,
            ppid=1,
            process_name="python3",
            binary_path="/usr/bin/python3",
            start_epoch_ms=2000,
            exit_epoch_ms=1000,
            scan_proves_safe=False,
        )


# --- Test 3: Process Table Diffing, Starts, Exits, and PID Recycling ---

def test_process_table_diff_started_exited_and_pid_recycling():
    """Verifies diff_process_tables handles new processes, exits, and recycled PIDs."""
    device_id = "00000000-0000-4000-8000-000000000077"
    t0 = 1700000000000
    t1 = t0 + 5000

    baseline = [
        {"pid": 1, "ppid": 0, "name": "launchd", "command_path": "/sbin/launchd", "start_time_epoch_ms": t0 - 10000, "is_system_core": True},
        {"pid": 200, "ppid": 1, "name": "zsh", "command_path": "/bin/zsh", "start_time_epoch_ms": t0 - 5000, "is_system_core": False},
        {"pid": 300, "ppid": 200, "name": "curl", "command_path": "/usr/bin/curl", "start_time_epoch_ms": t0 - 1000, "is_system_core": False},
    ]

    # At t1:
    # PID 300 (curl) exited.
    # PID 400 (python3) started.
    # PID 300 was RECYCLED by OS with a new start time for 'sleep'!
    current = [
        {"pid": 1, "ppid": 0, "name": "launchd", "command_path": "/sbin/launchd", "start_time_epoch_ms": t0 - 10000, "is_system_core": True},
        {"pid": 200, "ppid": 1, "name": "zsh", "command_path": "/bin/zsh", "start_time_epoch_ms": t0 - 5000, "is_system_core": False},
        {"pid": 300, "ppid": 200, "name": "sleep", "command_path": "/bin/sleep", "start_time_epoch_ms": t1 - 100, "is_system_core": False},
        {"pid": 400, "ppid": 200, "name": "python3", "command_path": "/opt/homebrew/bin/python3", "start_time_epoch_ms": t1 - 2000, "is_system_core": False},
    ]

    diff = ProcessLifecycleTracker.diff_process_tables(
        baseline_processes=baseline,
        current_processes=current,
        device_id=device_id,
        observed_at_epoch_ms=t1,
    )

    # Should detect 2 started (PID 300 sleep, PID 400 python3) and 1 exited (PID 300 curl)
    assert len(diff.started_events) == 2
    assert len(diff.exited_events) == 1
    assert diff.total_transitions == 3

    started_pids = {ev.pid: ev for ev in diff.started_events}
    assert 400 in started_pids
    assert started_pids[400].process_name == "python3"
    assert 300 in started_pids
    assert started_pids[300].process_name == "sleep"

    exited_ev = diff.exited_events[0]
    assert exited_ev.pid == 300
    assert exited_ev.process_name == "curl"
    assert exited_ev.exit_epoch_ms == t1

    # Verify that the two PID 300 processes have distinct entity URNs due to start time & binary hash
    assert started_pids[300].entity_urn != exited_ev.entity_urn


# --- Test 4: Endpoint Security Event Translation ---

def test_endpoint_security_event_translation():
    """Verifies translating raw Endpoint Security notifications into typed lifecycle events."""
    device_id = "00000000-0000-4000-8000-000000000077"

    # NOTIFY_EXEC
    exec_sample = {
        "event_type": "NOTIFY_EXEC",
        "process_pid": 555,
        "process_ppid": 1,
        "executable_path": "/usr/bin/git",
        "is_platform_binary": True,
        "cdhash": "fedcba9876543210",
        "signing_id": "com.apple.git",
    }
    exec_ev = ProcessLifecycleTracker.from_endpoint_security_event(
        es_event=exec_sample,
        device_id=device_id,
        start_epoch_ms=1700000005000,
        observed_at_epoch_ms=1700000005000,
    )
    assert exec_ev is not None
    assert exec_ev.event_type == ProcessLifecycleEventType.PROCESS_STARTED
    assert exec_ev.pid == 555
    assert exec_ev.exit_epoch_ms is None

    # NOTIFY_EXIT
    exit_sample = {
        "event_type": "NOTIFY_EXIT",
        "process_pid": 555,
        "process_ppid": 1,
        "executable_path": "/usr/bin/git",
        "is_platform_binary": True,
    }
    exit_ev = ProcessLifecycleTracker.from_endpoint_security_event(
        es_event=exit_sample,
        device_id=device_id,
        start_epoch_ms=1700000005000,
        exit_code=0,
        observed_at_epoch_ms=1700000008000,
    )
    assert exit_ev is not None
    assert exit_ev.event_type == ProcessLifecycleEventType.PROCESS_EXITED
    assert exit_ev.pid == 555
    assert exit_ev.exit_code == 0
    assert exit_ev.exit_status == ProcessExitStatus.NORMAL
    assert exit_ev.runtime_ms == 3000


# --- Test 5: Ownership Classification and Application Association ---

def test_ownership_classification_and_app_association():
    """Verifies component ownership isolation (SC-02) and .app bundle recognition."""
    # System core binary
    assert ProcessLifecycleTracker.classify_ownership("/sbin/launchd") == ComponentOwnership.SYSTEM_MANAGED
    assert ProcessLifecycleTracker.classify_ownership("/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder") == ComponentOwnership.SYSTEM_MANAGED

    # Vendor binary
    assert ProcessLifecycleTracker.classify_ownership("/opt/homebrew/bin/node") == ComponentOwnership.VENDOR_MANAGED
    assert ProcessLifecycleTracker.classify_ownership("/Library/Application Support/Vendor/daemon") == ComponentOwnership.VENDOR_MANAGED

    # User binary
    assert ProcessLifecycleTracker.classify_ownership("/Users/tharun/bin/tool") == ComponentOwnership.USER_MANAGED
    assert ProcessLifecycleTracker.classify_ownership("/Applications/Visual Studio Code.app/Contents/MacOS/Electron") == ComponentOwnership.USER_MANAGED

    # App bundle URN resolution
    app_urn = ProcessLifecycleTracker.resolve_app_urn_for_binary("/Applications/Safari.app/Contents/MacOS/Safari")
    assert app_urn == "urn:systemmind:app:safari"

    app_urn_space = ProcessLifecycleTracker.resolve_app_urn_for_binary("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    assert app_urn_space == "urn:systemmind:app:google-chrome"

    # Non-app binary returns None
    assert ProcessLifecycleTracker.resolve_app_urn_for_binary("/usr/bin/git") is None


# --- Test 6: Digital Twin Graph Synchronization ---

def test_digital_twin_graph_synchronization():
    """Verifies synchronizing process lifecycle events into the in-memory DigitalTwinGraph."""
    graph = DigitalTwinGraph()
    device_id = "00000000-0000-4000-8000-000000000077"
    host_urn = f"urn:systemmind:host:{device_id}"

    t0 = 1700000000000
    parent_urn = StableEntityIdGenerator.generate_process_urn(device_id, 100, t0 - 5000, "/bin/zsh").urn
    child_urn = StableEntityIdGenerator.generate_process_urn(device_id, 200, t0, "/Applications/Safari.app/Contents/MacOS/Safari").urn

    # Pre-register parent process
    graph.add_entity(
        TwinEntity(
            entity_id=parent_urn,
            entity_type=TwinEntityType.PROCESS,
            ownership=ComponentOwnership.USER_MANAGED,
            attributes={"pid": 100, "process_name": "zsh"},
            provenance_source="test_detector",
        )
    )

    start_ev = ProcessLifecycleEvent(
        event_id="pevt-start",
        device_id=device_id,
        entity_urn=child_urn,
        event_type=ProcessLifecycleEventType.PROCESS_STARTED,
        pid=200,
        ppid=100,
        process_name="Safari",
        binary_path="/Applications/Safari.app/Contents/MacOS/Safari",
        start_epoch_ms=t0,
        ownership=ComponentOwnership.USER_MANAGED,
        parent_entity_urn=parent_urn,
        app_entity_urn="urn:systemmind:app:safari",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=t0,
    )

    mutations = ProcessLifecycleTracker.sync_with_digital_twin(graph, [start_ev], host_urn=host_urn)
    assert mutations > 0

    # Verify process entity exists in graph
    proc_entity = graph.get_entity(child_urn)
    assert proc_entity is not None
    assert proc_entity.entity_type == TwinEntityType.PROCESS
    assert proc_entity.is_stale is False

    # Verify relations: HOST -> CONTAINS -> PROCESS, PROCESS -> SPAWNED_BY -> PARENT, APP -> OWNS -> PROCESS
    contains_rel = graph.get_relationship(f"rel_{StableEntityIdGenerator.hash_token(f'{host_urn}:CONTAINS:{child_urn}', 16)}")
    assert contains_rel is not None
    assert contains_rel.relation_type == TwinRelationType.CONTAINS

    spawn_rel = graph.get_relationship(f"rel_{StableEntityIdGenerator.hash_token(f'{child_urn}:SPAWNED_BY:{parent_urn}', 16)}")
    assert spawn_rel is not None
    assert spawn_rel.relation_type == TwinRelationType.SPAWNED_BY

    # Now simulate exit event
    exit_ev = ProcessLifecycleEvent(
        event_id="pevt-exit",
        device_id=device_id,
        entity_urn=child_urn,
        event_type=ProcessLifecycleEventType.PROCESS_EXITED,
        pid=200,
        ppid=100,
        process_name="Safari",
        binary_path="/Applications/Safari.app/Contents/MacOS/Safari",
        start_epoch_ms=t0,
        exit_epoch_ms=t0 + 10000,
        exit_code=0,
        exit_status=ProcessExitStatus.NORMAL,
        runtime_ms=10000,
        ownership=ComponentOwnership.USER_MANAGED,
        observed_at_iso="2026-11-18T12:00:10Z",
        observed_at_epoch_ms=t0 + 10000,
    )

    ProcessLifecycleTracker.sync_with_digital_twin(graph, [exit_ev], host_urn=host_urn)

    # Invariant: Exited process must be marked stale, NEVER deleted from graph
    updated_proc = graph.get_entity(child_urn)
    assert updated_proc is not None
    assert updated_proc.is_stale is True
    assert updated_proc.attributes["exit_code"] == 0
    assert updated_proc.attributes["runtime_ms"] == 10000


# --- Test 7: Append-Only Event Store Cryptographic Hash Chaining ---

def test_event_store_cryptographic_hash_chaining(memory_db: sqlite3.Connection):
    """Verifies process lifecycle transitions integrate into SystemEventStore with SHA-256 hash chaining."""
    event_store = SystemEventStore(memory_db)
    device_id = "00000000-0000-4000-8000-000000000077"

    t0 = 1700000000000
    proc_urn = StableEntityIdGenerator.generate_process_urn(device_id, 777, t0, "/bin/echo").urn

    start_ev = ProcessLifecycleEvent(
        event_id="pevt-s",
        device_id=device_id,
        entity_urn=proc_urn,
        event_type=ProcessLifecycleEventType.PROCESS_STARTED,
        pid=777,
        ppid=1,
        process_name="echo",
        binary_path="/bin/echo",
        start_epoch_ms=t0,
        observed_at_epoch_ms=t0,
    )

    exit_ev = ProcessLifecycleEvent(
        event_id="pevt-e",
        device_id=device_id,
        entity_urn=proc_urn,
        event_type=ProcessLifecycleEventType.PROCESS_EXITED,
        pid=777,
        ppid=1,
        process_name="echo",
        binary_path="/bin/echo",
        start_epoch_ms=t0,
        exit_epoch_ms=t0 + 50,
        exit_code=0,
        runtime_ms=50,
        observed_at_epoch_ms=t0 + 50,
    )

    recs = ProcessLifecycleTracker.sync_with_event_store([start_ev, exit_ev], event_store)
    assert len(recs) == 2
    assert recs[0].event_type == SystemEventType.PROCESS_SPAWNED.value
    assert recs[1].event_type == SystemEventType.PROCESS_EXITED.value

    # Verify unbroken cryptographic hash chain
    is_valid, count, err = event_store.verify_chain_integrity()
    assert is_valid is True
    assert count == 2
    assert err is None


# --- Test 8: ProcessLifecycleManager Persistence and Point-in-Time Reconstruction ---

def test_process_lifecycle_manager_persistence_and_point_in_time(memory_db: sqlite3.Connection):
    """Verifies relational persistence and point-in-time process reconstruction."""
    device_id = "00000000-0000-4000-8000-000000000077"
    t0 = 1700000000000  # t = 0

    # Process 1: launchd (started at t0 - 100,000 ms, never exits)
    urn_launchd = StableEntityIdGenerator.generate_process_urn(device_id, 1, t0 - 100000, "/sbin/launchd").urn
    ev_launchd = ProcessLifecycleEvent(
        event_id="pevt-1",
        device_id=device_id,
        entity_urn=urn_launchd,
        event_type=ProcessLifecycleEventType.PROCESS_STARTED,
        pid=1,
        ppid=0,
        process_name="launchd",
        binary_path="/sbin/launchd",
        start_epoch_ms=t0 - 100000,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        observed_at_epoch_ms=t0,
    )

    # Process 2: short_worker (started at t0 + 1,000 ms, exited at t0 + 4,000 ms)
    urn_worker = StableEntityIdGenerator.generate_process_urn(device_id, 50, t0 + 1000, "/usr/bin/worker").urn
    ev_worker_start = ProcessLifecycleEvent(
        event_id="pevt-2",
        device_id=device_id,
        entity_urn=urn_worker,
        event_type=ProcessLifecycleEventType.PROCESS_STARTED,
        pid=50,
        ppid=1,
        process_name="worker",
        binary_path="/usr/bin/worker",
        start_epoch_ms=t0 + 1000,
        ownership=ComponentOwnership.USER_MANAGED,
        parent_entity_urn=urn_launchd,
        observed_at_epoch_ms=t0 + 1000,
    )
    ev_worker_exit = ProcessLifecycleEvent(
        event_id="pevt-3",
        device_id=device_id,
        entity_urn=urn_worker,
        event_type=ProcessLifecycleEventType.PROCESS_EXITED,
        pid=50,
        ppid=1,
        process_name="worker",
        binary_path="/usr/bin/worker",
        start_epoch_ms=t0 + 1000,
        exit_epoch_ms=t0 + 4000,
        exit_code=0,
        runtime_ms=3000,
        ownership=ComponentOwnership.USER_MANAGED,
        parent_entity_urn=urn_launchd,
        observed_at_epoch_ms=t0 + 4000,
    )

    # Process 3: late_task (started at t0 + 6,000 ms, still running)
    urn_late = StableEntityIdGenerator.generate_process_urn(device_id, 80, t0 + 6000, "/usr/bin/late").urn
    ev_late = ProcessLifecycleEvent(
        event_id="pevt-4",
        device_id=device_id,
        entity_urn=urn_late,
        event_type=ProcessLifecycleEventType.PROCESS_STARTED,
        pid=80,
        ppid=1,
        process_name="late",
        binary_path="/usr/bin/late",
        start_epoch_ms=t0 + 6000,
        ownership=ComponentOwnership.USER_MANAGED,
        parent_entity_urn=urn_launchd,
        observed_at_epoch_ms=t0 + 6000,
    )

    ProcessLifecycleManager.record_events(memory_db, [ev_launchd, ev_worker_start, ev_worker_exit, ev_late])

    # Query events
    events = ProcessLifecycleManager.get_events(memory_db, device_id=device_id)
    assert len(events) == 4

    # Point-in-Time Check 1: At t = t0 + 2,000 ms:
    # PID 1 is running, PID 50 is running. PID 80 has not started.
    active_at_2000 = ProcessLifecycleManager.get_running_processes_at(memory_db, target_epoch_ms=t0 + 2000, device_id=device_id)
    active_pids_2000 = {p["pid"] for p in active_at_2000}
    assert active_pids_2000 == {1, 50}

    # Point-in-Time Check 2: At t = t0 + 5,000 ms:
    # PID 1 is running. PID 50 exited at 4000 ms. PID 80 has not started.
    active_at_5000 = ProcessLifecycleManager.get_running_processes_at(memory_db, target_epoch_ms=t0 + 5000, device_id=device_id)
    active_pids_5000 = {p["pid"] for p in active_at_5000}
    assert active_pids_5000 == {1}

    # Point-in-Time Check 3: At t = t0 + 7,000 ms:
    # PID 1 is running, PID 80 is running. PID 50 is dead.
    active_at_7000 = ProcessLifecycleManager.get_running_processes_at(memory_db, target_epoch_ms=t0 + 7000, device_id=device_id)
    active_pids_7000 = {p["pid"] for p in active_at_7000}
    assert active_pids_7000 == {1, 80}

    # Lineage ancestry check for PID 50 -> PID 1
    lineage = ProcessLifecycleManager.get_process_lineage(memory_db, urn_worker)
    assert len(lineage) == 2
    assert lineage[0].pid == 50
    assert lineage[1].pid == 1


# --- Test 9: Packaging Validator and AST Safety Audit ---

def test_process_lifecycle_packaging_and_ast_safety():
    """Verifies that ProcessLifecycleValidator completes with zero issues and verifies SC-01 AST safety."""
    result = ProcessLifecycleValidator.audit(REPO_ROOT)
    assert result.valid is True
    assert result.issues == ()
    assert result.process_lifecycle_present is True
    assert result.design_note_present is True
    assert result.migration_present is True
    assert result.tool_present is True
    assert result.ast_safety_valid is True
    assert result.charter_invariants_valid is True
    assert result.functional_lifecycle_valid is True
    assert result.scan_proves_safe is False
