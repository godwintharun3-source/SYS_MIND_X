"""Comprehensive unit, integration, and invariant tests for Day 073 State Snapshots and Comparison."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.digital_twin_snapshots import DigitalTwinSnapshotsValidator
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinRelationship,
    TwinRelationType,
)
from system_mind.twin.snapshots import (
    DigitalTwinSnapshot,
    DigitalTwinSnapshotDiff,
    DigitalTwinSnapshotManager,
    EntityAttributeDiff,
    SnapshotTriggerReason,
    compare_snapshots,
    compute_graph_state_digest,
)


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite database with migrations 0001 through 0008 applied."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0008_up_and_down_lifecycle() -> None:
    """Tests migration 0008 UP and DOWN lifecycle, rollback to version 7, and reapplication."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)

    # 1. Apply up to migration 8
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='digital_twin_snapshots';"
    )
    assert cursor.fetchone() is not None, "Table digital_twin_snapshots must exist"

    # Verify check constraint scan_proves_safe = 0
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO digital_twin_snapshots (
                snapshot_id, device_id, captured_at_iso, captured_at_epoch_ms,
                sequence_number, trigger_reason, entity_count, relationship_count,
                state_digest, entities_json, relationships_json, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "snap-fail",
                "dev-1",
                "2026-11-18T12:00:00Z",
                1700000000000,
                1,
                "MANUAL",
                0,
                0,
                "0" * 64,
                "[]",
                "[]",
                1,  # VIOLATES scan_proves_safe = 0
            ),
        )

    # 2. Rollback to version 7
    migrator.rollback_to(target_version=7, conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='digital_twin_snapshots';"
    )
    assert cursor.fetchone() is None, "Table digital_twin_snapshots must be dropped on rollback to 7"

    # 3. Re-apply to version 8
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='digital_twin_snapshots';"
    )
    assert cursor.fetchone() is not None, "Table digital_twin_snapshots must exist after re-applying 8"
    conn.close()


def test_snapshot_dataclass_invariants() -> None:
    """Tests DigitalTwinSnapshot and DigitalTwinSnapshotDiff invariant validation."""
    # Valid snapshot
    snap = DigitalTwinSnapshot(
        snapshot_id="snap-valid-01",
        device_id="test-device-uuid",
        captured_at_iso="2026-11-18T12:00:00Z",
        captured_at_epoch_ms=1700000000000,
        sequence_number=1,
        trigger_reason="TELEMETRY_SWEEP",
        entity_count=0,
        relationship_count=0,
        state_digest="0" * 64,
        entities=(),
        relationships=(),
        scan_proves_safe=False,
    )
    assert snap.snapshot_id == "snap-valid-01"
    assert snap.scan_proves_safe is False

    # Invariant SC-03: scan_proves_safe on snapshot must be False
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        DigitalTwinSnapshot(
            snapshot_id="snap-fail-01",
            device_id="test-device-uuid",
            captured_at_iso="2026-11-18T12:00:00Z",
            captured_at_epoch_ms=1700000000000,
            sequence_number=1,
            trigger_reason="TELEMETRY_SWEEP",
            entity_count=0,
            relationship_count=0,
            state_digest="0" * 64,
            entities=(),
            relationships=(),
            scan_proves_safe=True,  # VIOLATION
        )

    # Entity count mismatch
    with pytest.raises(ValueError, match="Entity Count Mismatch"):
        DigitalTwinSnapshot(
            snapshot_id="snap-fail-02",
            device_id="test-device-uuid",
            captured_at_iso="2026-11-18T12:00:00Z",
            captured_at_epoch_ms=1700000000000,
            sequence_number=1,
            trigger_reason="TELEMETRY_SWEEP",
            entity_count=5,  # MISMATCH
            relationship_count=0,
            state_digest="0" * 64,
            entities=(),
            relationships=(),
        )

    # Invariant SC-03: scan_proves_safe on diff must be False
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        DigitalTwinSnapshotDiff(
            from_snapshot_id="snap-1",
            to_snapshot_id="snap-2",
            device_id="dev-1",
            from_epoch_ms=1000,
            to_epoch_ms=2000,
            time_delta_seconds=1.0,
            added_entities=(),
            removed_entities=(),
            modified_entities=(),
            added_relationships=(),
            removed_relationships=(),
            ownership_changes={},
            user_managed_affected=False,
            is_identical=True,
            scan_proves_safe=True,  # VIOLATION
        )


def test_deterministic_state_digest() -> None:
    """Verifies that entity and edge sorting guarantees deterministic cryptographic digests."""
    e1 = TwinEntity(
        entity_id="urn:systemmind:host:mach-1",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    e2 = TwinEntity(
        entity_id="urn:systemmind:proc:101",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"pid": 101},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    rel1 = TwinRelationship(
        relation_id="rel:host:proc:101",
        source_id="urn:systemmind:host:mach-1",
        target_id="urn:systemmind:proc:101",
        relation_type=TwinRelationType.CONTAINS,
        observed_at="2026-11-18T12:00:00Z",
    )

    digest_forward = compute_graph_state_digest([e1, e2], [rel1])
    digest_reversed = compute_graph_state_digest([e2, e1], [rel1])

    # Must be identical regardless of input list ordering
    assert digest_forward == digest_reversed
    assert len(digest_forward) == 64

    # Modifying an attribute alters the digest
    e2_mutated = TwinEntity(
        entity_id="urn:systemmind:proc:101",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"pid": 101, "cpu_pct": 5.0},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    digest_mutated = compute_graph_state_digest([e1, e2_mutated], [rel1])
    assert digest_mutated != digest_forward


def test_snapshot_capture_and_retrieval(memory_db: sqlite3.Connection) -> None:
    """Tests capturing snapshots from DigitalTwinGraph and querying by ID or device."""
    manager = DigitalTwinSnapshotManager(memory_db)
    dev_id = "test-device-uuid"

    graph = DigitalTwinGraph()
    e1 = TwinEntity(
        entity_id="urn:systemmind:host:node",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    graph.add_entity(e1)

    # 1. Capture first snapshot
    snap1 = manager.capture_snapshot(
        graph=graph,
        device_id=dev_id,
        trigger_reason=SnapshotTriggerReason.TELEMETRY_SWEEP.value,
        captured_at_epoch_ms=1700000000000,
    )
    assert snap1.sequence_number == 1
    assert snap1.entity_count == 1
    assert snap1.relationship_count == 0

    # 2. Capture second snapshot
    snap2 = manager.capture_snapshot(
        graph=graph,
        device_id=dev_id,
        trigger_reason=SnapshotTriggerReason.SCHEDULED.value,
        captured_at_epoch_ms=1700000010000,
    )
    assert snap2.sequence_number == 2

    # Query single snapshot
    fetched = manager.get_snapshot(snap1.snapshot_id)
    assert fetched is not None
    assert fetched.snapshot_id == snap1.snapshot_id
    assert fetched.state_digest == snap1.state_digest

    # Query latest snapshot
    latest = manager.get_latest_snapshot(device_id=dev_id)
    assert latest is not None
    assert latest.snapshot_id == snap2.snapshot_id
    assert latest.sequence_number == 2

    # List snapshots
    snapshots = manager.list_snapshots(device_id=dev_id)
    assert len(snapshots) == 2
    assert snapshots[0].sequence_number == 2  # Reverse-chronological order


def test_identical_snapshot_diff() -> None:
    """Tests that comparing identical snapshots yields empty diff and is_identical=True."""
    e1 = TwinEntity(
        entity_id="urn:systemmind:host:mach-1",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    digest = compute_graph_state_digest([e1], [])

    snap_a = DigitalTwinSnapshot(
        snapshot_id="snap-1",
        device_id="dev-1",
        captured_at_iso="2026-11-18T12:00:00Z",
        captured_at_epoch_ms=1000,
        sequence_number=1,
        trigger_reason="TELEMETRY_SWEEP",
        entity_count=1,
        relationship_count=0,
        state_digest=digest,
        entities=(e1,),
        relationships=(),
    )
    snap_b = DigitalTwinSnapshot(
        snapshot_id="snap-2",
        device_id="dev-1",
        captured_at_iso="2026-11-18T12:00:10Z",
        captured_at_epoch_ms=11000,
        sequence_number=2,
        trigger_reason="SCHEDULED",
        entity_count=1,
        relationship_count=0,
        state_digest=digest,
        entities=(e1,),
        relationships=(),
    )

    diff = compare_snapshots(snap_a, snap_b)
    assert diff.is_identical is True
    assert len(diff.added_entities) == 0
    assert len(diff.removed_entities) == 0
    assert len(diff.modified_entities) == 0
    assert diff.user_managed_affected is False


def test_structural_snapshot_diffing(memory_db: sqlite3.Connection) -> None:
    """Tests granular structural diffing for added, removed, and modified entities."""
    manager = DigitalTwinSnapshotManager(memory_db)
    dev_id = "test-device-uuid"

    host = TwinEntity(
        entity_id="urn:systemmind:host:test",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"cores": 8},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    proc_old = TwinEntity(
        entity_id="urn:systemmind:proc:1",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"name": "p1"},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    proc_stale = TwinEntity(
        entity_id="urn:systemmind:proc:2",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"name": "p2"},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
        is_stale=False,
    )

    graph_a = DigitalTwinGraph()
    graph_a.add_entity(host)
    graph_a.add_entity(proc_old)
    graph_a.add_entity(proc_stale)
    graph_a.add_relationship(
        TwinRelationship("r:1", "urn:systemmind:host:test", "urn:systemmind:proc:1", TwinRelationType.CONTAINS)
    )

    snap_a = manager.capture_snapshot(graph_a, dev_id, captured_at_epoch_ms=1000)

    # Graph B: proc_old removed, proc_stale is now is_stale=True, proc_new added (USER_MANAGED)
    proc_stale_updated = TwinEntity(
        entity_id="urn:systemmind:proc:2",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"name": "p2", "cpu": 0.0},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:01:00Z",
        provenance_source="collector",
        is_stale=True,
    )
    proc_new = TwinEntity(
        entity_id="urn:systemmind:proc:3",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "user_app"},
        created_at="2026-11-18T12:01:00Z",
        updated_at="2026-11-18T12:01:00Z",
        provenance_source="collector",
    )

    graph_b = DigitalTwinGraph()
    graph_b.add_entity(host)
    graph_b.add_entity(proc_stale_updated)
    graph_b.add_entity(proc_new)
    graph_b.add_relationship(
        TwinRelationship("r:2", "urn:systemmind:host:test", "urn:systemmind:proc:3", TwinRelationType.CONTAINS)
    )

    snap_b = manager.capture_snapshot(graph_b, dev_id, captured_at_epoch_ms=2000)

    diff = manager.compare_snapshots_by_id(snap_a.snapshot_id, snap_b.snapshot_id)

    assert diff.is_identical is False
    assert len(diff.added_entities) == 1
    assert diff.added_entities[0].entity_id == "urn:systemmind:proc:3"

    assert len(diff.removed_entities) == 1
    assert diff.removed_entities[0].entity_id == "urn:systemmind:proc:1"

    assert len(diff.modified_entities) == 1
    mod = diff.modified_entities[0]
    assert mod.entity_id == "urn:systemmind:proc:2"
    assert mod.is_stale_changed is True
    assert mod.new_is_stale is True
    assert "cpu" in mod.added_or_modified_attributes

    assert len(diff.added_relationships) == 1
    assert diff.added_relationships[0].relation_id == "r:2"

    assert len(diff.removed_relationships) == 1
    assert diff.removed_relationships[0].relation_id == "r:1"

    # User-managed component affected flag
    assert diff.user_managed_affected is True


def test_user_managed_isolation_detection() -> None:
    """Verifies that modifications only to SYSTEM_MANAGED entities do not flag user_managed_affected."""
    e_sys_1 = TwinEntity(
        entity_id="urn:systemmind:host:mach",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"temp": 45},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    e_sys_2 = TwinEntity(
        entity_id="urn:systemmind:host:mach",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"temp": 50},  # Modified
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:01:00Z",
        provenance_source="collector",
    )

    snap_1 = DigitalTwinSnapshot(
        snapshot_id="s1",
        device_id="d1",
        captured_at_iso="2026-11-18T12:00:00Z",
        captured_at_epoch_ms=1000,
        sequence_number=1,
        trigger_reason="TELEMETRY_SWEEP",
        entity_count=1,
        relationship_count=0,
        state_digest="1" * 64,
        entities=(e_sys_1,),
        relationships=(),
    )
    snap_2 = DigitalTwinSnapshot(
        snapshot_id="s2",
        device_id="d1",
        captured_at_iso="2026-11-18T12:01:00Z",
        captured_at_epoch_ms=2000,
        sequence_number=2,
        trigger_reason="TELEMETRY_SWEEP",
        entity_count=1,
        relationship_count=0,
        state_digest="2" * 64,
        entities=(e_sys_2,),
        relationships=(),
    )

    diff = compare_snapshots(snap_1, snap_2)
    assert diff.is_identical is False
    assert len(diff.modified_entities) == 1
    assert diff.user_managed_affected is False


def test_lossless_graph_reconstruction(memory_db: sqlite3.Connection) -> None:
    """Verifies that DigitalTwinSnapshotManager.reconstruct_graph restores a fully functional graph."""
    manager = DigitalTwinSnapshotManager(memory_db)
    dev_id = "test-device-uuid"

    graph = DigitalTwinGraph()
    e_host = TwinEntity(
        entity_id="urn:systemmind:host:node",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    e_app = TwinEntity(
        entity_id="urn:systemmind:app:editor",
        entity_type=TwinEntityType.APPLICATION,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"bundle_id": "com.test.editor"},
        created_at="2026-11-18T12:00:00Z",
        updated_at="2026-11-18T12:00:00Z",
        provenance_source="collector",
    )
    rel = TwinRelationship(
        relation_id="rel:host:app",
        source_id="urn:systemmind:host:node",
        target_id="urn:systemmind:app:editor",
        relation_type=TwinRelationType.CONTAINS,
        observed_at="2026-11-18T12:00:00Z",
    )
    graph.add_entity(e_host)
    graph.add_entity(e_app)
    graph.add_relationship(rel)

    # Capture snapshot
    snap = manager.capture_snapshot(graph, dev_id)

    # Reconstruct in a fresh graph instance
    reconstructed = manager.reconstruct_graph(snap.snapshot_id)

    assert reconstructed.entity_count == 2
    assert reconstructed.relationship_count == 1

    restored_app = reconstructed.get_entity("urn:systemmind:app:editor")
    assert restored_app is not None
    assert restored_app.ownership == ComponentOwnership.USER_MANAGED
    assert restored_app.attributes["bundle_id"] == "com.test.editor"

    # Query outgoing relationships / traversal
    outgoing = reconstructed.get_outgoing_relationships("urn:systemmind:host:node")
    assert len(outgoing) == 1
    assert outgoing[0].target_id == "urn:systemmind:app:editor"

    # Integrity check
    is_valid, violations = reconstructed.validate_integrity()
    assert is_valid is True
    assert len(violations) == 0


def test_packaging_validator_and_ast_safety() -> None:
    """Tests that the packaging validator passes and verifies AST safety (SC-01 & SC-03)."""
    audit = DigitalTwinSnapshotsValidator.audit()
    assert audit.valid is True
    assert len(audit.issues) == 0
    assert audit.snapshots_engine_present is True
    assert audit.migration_present is True
    assert audit.design_note_present is True
    assert audit.tool_present is True
    assert audit.ast_safety_valid is True
    assert audit.charter_invariants_valid is True
    assert audit.functional_snapshots_valid is True
    assert audit.scan_proves_safe is False
