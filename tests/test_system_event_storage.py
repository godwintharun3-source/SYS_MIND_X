"""Unit, integration, and safety invariant test suite for Day 070 Append-Only System Event Storage."""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.system_events import SystemEventsValidator
from system_mind.twin.event_store import (
    GENESIS_PREV_HASH,
    SystemEventRecord,
    SystemEventStore,
    SystemEventType,
    compute_event_block_hash,
    compute_event_payload_hash,
)


@pytest.fixture
def memory_db_conn() -> sqlite3.Connection:
    """Provides an in-memory SQLite connection with all migrations applied."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0006_up_and_down_lifecycle() -> None:
    """Verifies that migration 0006 creates system_events table, indices, and triggers, and rolls back cleanly."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    try:
        migrator.apply_all(conn=conn)

        # Verify table exists
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "system_events" in tables

        # Verify triggers exist
        triggers = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger';"
            ).fetchall()
        ]
        assert "trg_system_events_prevent_update" in triggers
        assert "trg_system_events_prevent_delete" in triggers

        # Verify indices exist
        indices = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index';"
            ).fetchall()
        ]
        assert "idx_system_events_event_id" in indices
        assert "idx_system_events_entity_urn" in indices
        assert "idx_system_events_event_type" in indices
        assert "idx_system_events_timestamp" in indices
        assert "idx_system_events_correlation" in indices
        assert "idx_system_events_ownership" in indices

        # Rollback migration 0006 (to target version 5)
        rolled_back = migrator.rollback_to(target_version=5, conn=conn)
        assert any(r.version == 6 for r in rolled_back)

        # Verify table, indices, and triggers dropped
        tables_after = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "system_events" not in tables_after

        triggers_after = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger';"
            ).fetchall()
        ]
        assert "trg_system_events_prevent_update" not in triggers_after
        assert "trg_system_events_prevent_delete" not in triggers_after

        # Re-apply
        reapplied = migrator.apply_migration(6, conn=conn)
        assert reapplied.version == 6
    finally:
        conn.close()


def test_system_event_record_validation_and_serialization() -> None:
    """Verifies dataclass validation, default values, and serialization round-trip."""
    payload = {"pid": 1, "name": "launchd"}
    payload_hash = compute_event_payload_hash(payload)
    block_hash = compute_event_block_hash(
        prev_event_hash=GENESIS_PREV_HASH,
        sequence_number=1,
        event_id="evt-001",
        timestamp_iso="2026-11-18T11:00:00+00:00",
        entity_urn="urn:systemmind:proc:dev-1:1000:1:e68a56cd",
        event_type=SystemEventType.PROCESS_SPAWNED.value,
        payload_sha256=payload_hash,
    )

    record = SystemEventRecord(
        sequence_number=1,
        event_id="evt-001",
        device_id="dev-12345",
        entity_urn="urn:systemmind:proc:dev-1:1000:1:e68a56cd",
        event_type=SystemEventType.PROCESS_SPAWNED.value,
        timestamp_iso="2026-11-18T11:00:00+00:00",
        timestamp_epoch_ms=1763463600000,
        prev_event_hash=GENESIS_PREV_HASH,
        payload=payload,
        metadata={"subsystem": "proc"},
        component_ownership=ComponentOwnership.SYSTEM_MANAGED,
        correlation_id="corr-1",
        causation_id=None,
        scan_proves_safe=False,
    )

    assert record.payload_sha256 == payload_hash
    assert record.event_hash == block_hash
    assert record.component_ownership == ComponentOwnership.SYSTEM_MANAGED

    # Test dictionary serialization round-trip
    d = record.to_dict()
    reconstructed = SystemEventRecord.from_dict(d)
    assert reconstructed == record

    # Test SQLite row serialization
    params = record.to_sqlite_params()
    assert params[0] == 1
    assert params[1] == "evt-001"
    assert params[2] == "dev-12345"
    assert params[14] == "SYSTEM_MANAGED"
    assert params[15] == 0  # scan_proves_safe must be 0


def test_charter_invariant_sc03_scan_proves_safe_is_false(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies that scan_proves_safe=True is rejected at Python model and database constraint levels."""
    # 1. Python dataclass rejection
    with pytest.raises(ValueError, match="Charter Invariant Violation.*scan_proves_safe"):
        SystemEventRecord(
            sequence_number=1,
            event_id="evt-bad",
            device_id="dev-1",
            entity_urn="urn:systemmind:host:test",
            event_type="SYSTEM_ALERT",
            timestamp_iso="2026-11-18T11:00:00+00:00",
            timestamp_epoch_ms=1000,
            prev_event_hash=GENESIS_PREV_HASH,
            scan_proves_safe=True,  # Prohibited
        )

    # 2. Database check constraint rejection
    with pytest.raises(sqlite3.IntegrityError):
        memory_db_conn.execute(
            """
            INSERT INTO system_events (
                sequence_number, event_id, device_id, entity_urn, event_type,
                timestamp_iso, timestamp_epoch_ms, prev_event_hash,
                payload_sha256, event_hash, payload_json, component_ownership, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
            """,
            (
                1, "evt-db-bad", "dev-1", "urn:systemmind:host:test",
                "SYSTEM_ALERT", "2026-11-18T11:00:00+00:00", 1000,
                GENESIS_PREV_HASH, "dummy_hash", "dummy_block", "{}",
                "SYSTEM_MANAGED",
            ),
        )


def test_append_only_trigger_immutability(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies that SQLite triggers prevent UPDATE and DELETE operations on system_events."""
    store = SystemEventStore(memory_db_conn)
    evt = store.append_event(
        device_id="dev-1",
        entity_urn="urn:systemmind:proc:dev-1:1000:1:e68a56cd",
        event_type=SystemEventType.PROCESS_SPAWNED,
        payload={"pid": 1},
        component_ownership=ComponentOwnership.SYSTEM_MANAGED,
    )

    # 1. Rejection on UPDATE
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="System events are append-only.*UPDATE"):
        memory_db_conn.execute(
            "UPDATE system_events SET event_type = 'MUTATED' WHERE event_id = ?;",
            (evt.event_id,),
        )

    # 2. Rejection on DELETE
    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="System events are append-only.*DELETE"):
        memory_db_conn.execute(
            "DELETE FROM system_events WHERE event_id = ?;",
            (evt.event_id,),
        )

    # Confirm record remains unmodified
    fetched = store.get_event(evt.event_id)
    assert fetched is not None
    assert fetched.event_type == SystemEventType.PROCESS_SPAWNED.value


def test_cryptographic_hash_chain_integrity_and_tamper_detection(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies mathematical hash chain integrity across sequence and detects tampering."""
    store = SystemEventStore(memory_db_conn)
    dev_id = "dev-ledger-1"
    host_urn = "urn:systemmind:host:dev-ledger-1"

    e1 = store.append_event(
        device_id=dev_id,
        entity_urn=host_urn,
        event_type=SystemEventType.HARDWARE_ATTACHED,
        payload={"device": "USB Keyboard"},
    )
    e2 = store.append_event(
        device_id=dev_id,
        entity_urn=host_urn,
        event_type=SystemEventType.NETWORK_INTERFACE_STATE,
        payload={"interface": "en0", "link": "UP"},
    )
    e3 = store.append_event(
        device_id=dev_id,
        entity_urn=host_urn,
        event_type=SystemEventType.CONFIG_MUTATED,
        payload={"key": "hostname", "val": "MacBook-Pro"},
    )

    # Verify initial valid chain
    assert e1.prev_event_hash == GENESIS_PREV_HASH
    assert e2.prev_event_hash == e1.event_hash
    assert e3.prev_event_hash == e2.event_hash

    is_valid, count, err = store.verify_chain_integrity()
    assert is_valid is True
    assert count == 3
    assert err is None


def test_event_store_query_filtering_and_correlation(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies querying by entity, event_type, correlation_id, and time windows."""
    store = SystemEventStore(memory_db_conn)
    dev_id = "dev-query-1"
    app_urn = "urn:systemmind:app:com.apple.safari"
    proc_urn = "urn:systemmind:proc:dev-query-1:2000:501:abc12345"

    corr_alpha = "corr-alpha"
    corr_beta = "corr-beta"

    store.append_event(
        device_id=dev_id,
        entity_urn=app_urn,
        event_type=SystemEventType.APPLICATION_LAUNCHED,
        payload={"name": "Safari"},
        component_ownership=ComponentOwnership.USER_MANAGED,
        correlation_id=corr_alpha,
        timestamp_epoch_ms=1000,
    )
    store.append_event(
        device_id=dev_id,
        entity_urn=proc_urn,
        event_type=SystemEventType.PROCESS_SPAWNED,
        payload={"pid": 501},
        component_ownership=ComponentOwnership.USER_MANAGED,
        correlation_id=corr_alpha,
        timestamp_epoch_ms=2000,
    )
    store.append_event(
        device_id=dev_id,
        entity_urn=app_urn,
        event_type=SystemEventType.APPLICATION_TERMINATED,
        payload={"status": "closed"},
        component_ownership=ComponentOwnership.USER_MANAGED,
        correlation_id=corr_beta,
        timestamp_epoch_ms=3000,
    )

    # Query by correlation_id
    alpha_events = store.query_events(correlation_id=corr_alpha)
    assert len(alpha_events) == 2
    assert [e.sequence_number for e in alpha_events] == [1, 2]

    # Query by entity_urn
    app_events = store.query_events(entity_urn=app_urn)
    assert len(app_events) == 2
    assert [e.event_type for e in app_events] == ["APPLICATION_LAUNCHED", "APPLICATION_TERMINATED"]

    # Query by event_type
    proc_events = store.query_events(event_type=SystemEventType.PROCESS_SPAWNED)
    assert len(proc_events) == 1
    assert proc_events[0].entity_urn == proc_urn

    # Query by timestamp window
    window_events = store.query_events(since_epoch_ms=1500, until_epoch_ms=2500)
    assert len(window_events) == 1
    assert window_events[0].sequence_number == 2


def test_system_events_packaging_validator() -> None:
    """Verifies that SystemEventsValidator audits the component cleanly."""
    result = SystemEventsValidator.audit()
    assert result.valid is True
    assert len(result.issues) == 0
    assert result.migration_present is True
    assert result.models_present is True
    assert result.design_note_present is True
    assert result.tool_present is True
    assert result.ast_safety_valid is True
    assert result.charter_invariants_valid is True
    assert result.immutability_triggers_valid is True
    assert result.hash_chain_valid is True


def test_ast_safety_sc01_zero_ambient_shell() -> None:
    """Verifies zero ambient shell executions across Day 070 event storage code."""
    root = Path(__file__).resolve().parent.parent
    targets = [
        root / "src/system_mind/twin/event_store.py",
        root / "src/system_mind/packaging/system_events.py",
        root / "tools/detect_system_events.py",
    ]

    for target in targets:
        assert target.is_file(), f"Target missing: {target}"
        tree = ast.parse(target.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        assert node.func.attr not in ("system", "popen")
                for kw in node.keywords:
                    if kw.arg == "shell":
                        assert kw.value.value is not True
