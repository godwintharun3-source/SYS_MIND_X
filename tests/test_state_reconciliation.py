"""Comprehensive unit, integration, and invariant tests for Day 075 System-State Reconciliation After Collector Gaps."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.reconciliation import StateReconciliationValidator
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import TwinEntity, TwinEntityType
from system_mind.twin.reconciliation import (
    CollectorGap,
    CollectorGapDetector,
    GapClassification,
    ReconciliationActionType,
    ReconciliationItem,
    StateReconciliationManager,
    StateReconciliationRecord,
    SystemStateReconciler,
)


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite database with migrations 0001 through 0010 applied."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0010_up_and_down_lifecycle() -> None:
    """Tests migration 0010 UP and DOWN lifecycle, rollback to version 9, and reapplication."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)

    # 1. Apply up to migration 10
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='collector_gaps';"
    )
    assert cursor.fetchone() is not None, "Table collector_gaps must exist"

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='state_reconciliation_records';"
    )
    assert cursor.fetchone() is not None, "Table state_reconciliation_records must exist"

    # Verify check constraint scan_proves_safe = 0 on collector_gaps
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO collector_gaps (
                gap_id, collector_id, device_id, domain, gap_start_epoch_ms,
                gap_end_epoch_ms, gap_duration_ms, expected_cadence_ms,
                gap_classification, detected_at_iso, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "gap-fail-safe",
                "mock_ps",
                "dev-test",
                "proc",
                1000,
                2000,
                1000,
                500,
                "MINOR_JITTER",
                "2026-11-18T12:00:00Z",
                1,  # VIOLATES scan_proves_safe = 0
            ),
        )

    # Verify check constraint scan_proves_safe = 0 on state_reconciliation_records
    conn.execute(
        """
        INSERT INTO collector_gaps (
            gap_id, collector_id, device_id, domain, gap_start_epoch_ms,
            gap_end_epoch_ms, gap_duration_ms, expected_cadence_ms,
            gap_classification, detected_at_iso, scan_proves_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            "gap-valid",
            "mock_ps",
            "dev-test",
            "proc",
            1000,
            2000,
            1000,
            500,
            "MINOR_JITTER",
            "2026-11-18T12:00:00Z",
            0,
        ),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO state_reconciliation_records (
                reconciliation_id, gap_id, device_id, domain, reconciled_at_iso,
                reconciled_at_epoch_ms, entities_sustained_count, entities_terminated_count,
                entities_staled_count, entities_spawned_count, confidence_discount_pct,
                actions_json, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "recon-fail-safe",
                "gap-valid",
                "dev-test",
                "proc",
                "2026-11-18T12:00:00Z",
                2000,
                0,
                0,
                0,
                0,
                0.1,
                "[]",
                1,  # VIOLATES scan_proves_safe = 0
            ),
        )

    # 2. Rollback to version 9
    migrator.rollback_to(target_version=9, conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('collector_gaps', 'state_reconciliation_records');"
    )
    assert len(cursor.fetchall()) == 0, "Both tables must be dropped on rollback to 9"

    # 3. Re-apply to version 10
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('collector_gaps', 'state_reconciliation_records');"
    )
    assert len(cursor.fetchall()) == 2, "Both tables must exist after re-applying 10"
    conn.close()


def test_collector_gap_dataclass_invariants() -> None:
    """Tests CollectorGap validation rules and Charter Invariant SC-03."""
    valid_gap = CollectorGap(
        gap_id="gap-01",
        collector_id="mock_ps",
        device_id="dev-test",
        domain="proc",
        gap_start_epoch_ms=1700000000000,
        gap_end_epoch_ms=1700000060000,
        gap_duration_ms=60000,
        expected_cadence_ms=5000,
        gap_classification=GapClassification.SYSTEM_SLEEP_WAKE.value,
        detected_at_iso="2026-11-18T12:00:00Z",
        scan_proves_safe=False,
    )
    assert valid_gap.gap_duration_ms == 60000
    assert "SLEEP_WAKE" in valid_gap.summary()

    # Invariant SC-03: scan_proves_safe cannot be True
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        CollectorGap(
            gap_id="gap-bad-safe",
            collector_id="mock_ps",
            device_id="dev-test",
            domain="proc",
            gap_start_epoch_ms=1000,
            gap_end_epoch_ms=2000,
            gap_duration_ms=1000,
            expected_cadence_ms=500,
            gap_classification="MINOR_JITTER",
            detected_at_iso="2026-11-18T12:00:00Z",
            scan_proves_safe=True,
        )

    # Invariant: gap_end_epoch_ms must be strictly greater than gap_start_epoch_ms
    with pytest.raises(ValueError, match="Invalid Gap Bounds"):
        CollectorGap(
            gap_id="gap-bad-bounds",
            collector_id="mock_ps",
            device_id="dev-test",
            domain="proc",
            gap_start_epoch_ms=2000,
            gap_end_epoch_ms=2000,
            gap_duration_ms=0,
            expected_cadence_ms=500,
            gap_classification="MINOR_JITTER",
            detected_at_iso="2026-11-18T12:00:00Z",
            scan_proves_safe=False,
        )

    # Invariant: duration must match end - start
    with pytest.raises(ValueError, match="Invalid Gap Duration"):
        CollectorGap(
            gap_id="gap-bad-dur",
            collector_id="mock_ps",
            device_id="dev-test",
            domain="proc",
            gap_start_epoch_ms=1000,
            gap_end_epoch_ms=3000,
            gap_duration_ms=1500,  # Expected 2000
            expected_cadence_ms=500,
            gap_classification="MINOR_JITTER",
            detected_at_iso="2026-11-18T12:00:00Z",
            scan_proves_safe=False,
        )


def test_state_reconciliation_record_dataclass_invariants() -> None:
    """Tests StateReconciliationRecord validation rules and Charter Invariant SC-03."""
    item = ReconciliationItem(
        entity_urn="urn:systemmind:proc:99",
        entity_type="PROCESS",
        action_type=ReconciliationActionType.TERMINATED_DURING_GAP.value,
        reason="Disappeared during gap",
        confidence_score=0.9,
    )

    rec = StateReconciliationRecord(
        reconciliation_id="recon-01",
        gap_id="gap-01",
        device_id="dev-test",
        domain="proc",
        reconciled_at_iso="2026-11-18T12:00:00Z",
        reconciled_at_epoch_ms=1700000060000,
        entities_sustained_count=2,
        entities_terminated_count=1,
        entities_staled_count=0,
        entities_spawned_count=0,
        confidence_discount_pct=0.15,
        actions=(item,),
        scan_proves_safe=False,
    )
    assert rec.reconciliation_id == "recon-01"
    assert "sustained" in rec.summary()

    # Invariant SC-03
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        StateReconciliationRecord(
            reconciliation_id="recon-bad-safe",
            gap_id="gap-01",
            device_id="dev-test",
            domain="proc",
            reconciled_at_iso="2026-11-18T12:00:00Z",
            reconciled_at_epoch_ms=1700000060000,
            entities_sustained_count=0,
            entities_terminated_count=0,
            entities_staled_count=0,
            entities_spawned_count=0,
            confidence_discount_pct=0.1,
            actions=(),
            scan_proves_safe=True,
        )


def test_collector_gap_detector_classifications() -> None:
    """Tests gap detection thresholds and semantic classification logic."""
    detector = CollectorGapDetector()

    # 1. Normal nominal jitter below threshold (< 2.0x cadence) -> None
    normal = detector.detect_gap(
        prev_epoch_ms=1000,
        curr_epoch_ms=8000,  # 7000ms < 10000ms threshold
        collector_id="mock_ps",
        device_id="dev-test",
        domain="proc",
    )
    assert normal is None

    # 2. MINOR_JITTER: 2.2x cadence (11000ms for 5000ms cadence)
    jitter = detector.detect_gap(
        prev_epoch_ms=1000,
        curr_epoch_ms=12000,
        collector_id="mock_ps",
        device_id="dev-test",
        domain="proc",
    )
    assert jitter is not None
    assert jitter.gap_classification == GapClassification.MINOR_JITTER.value

    # 3. COLLECTOR_TIMEOUT: 35000ms (7x cadence)
    timeout_gap = detector.detect_gap(
        prev_epoch_ms=1000,
        curr_epoch_ms=36000,
        collector_id="mock_ps",
        device_id="dev-test",
        domain="proc",
    )
    assert timeout_gap is not None
    assert timeout_gap.gap_classification == GapClassification.COLLECTOR_TIMEOUT.value

    # 4. SYSTEM_SLEEP_WAKE: 80000ms (80s >= 60s)
    sleep_gap = detector.detect_gap(
        prev_epoch_ms=1000,
        curr_epoch_ms=81000,
        collector_id="mock_ps",
        device_id="dev-test",
        domain="proc",
    )
    assert sleep_gap is not None
    assert sleep_gap.gap_classification == GapClassification.SYSTEM_SLEEP_WAKE.value

    # 5. PROLONGED_OUTAGE: 400000ms (400s >= 300s)
    outage_gap = detector.detect_gap(
        prev_epoch_ms=1000,
        curr_epoch_ms=401000,
        collector_id="mock_ps",
        device_id="dev-test",
        domain="proc",
    )
    assert outage_gap is not None
    assert outage_gap.gap_classification == GapClassification.PROLONGED_OUTAGE.value


def test_state_reconciler_differential_healing() -> None:
    """Tests differential state reconciliation across sustained, terminated, staled, and spawned entities."""
    reconciler = SystemStateReconciler()

    gap = CollectorGap(
        gap_id="gap-diff-test",
        collector_id="mock_ps",
        device_id="dev-diff",
        domain="proc",
        gap_start_epoch_ms=1700000000000,
        gap_end_epoch_ms=1700000060000,
        gap_duration_ms=60000,
        expected_cadence_ms=5000,
        gap_classification=GapClassification.SYSTEM_SLEEP_WAKE.value,
        detected_at_iso="2026-11-18T12:00:00Z",
    )

    p_sustained = TwinEntity(
        entity_id="urn:systemmind:proc:10",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "daemon", "confidence_score": 1.0},
    )
    p_terminated = TwinEntity(
        entity_id="urn:systemmind:proc:20",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "ephemeral_task", "confidence_score": 1.0},
    )
    vol_staled = TwinEntity(
        entity_id="urn:systemmind:vol:sdcard",
        entity_type=TwinEntityType.FILESYSTEM_NODE,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"mount": "/mnt/sd", "confidence_score": 1.0},
    )
    p_spawned = TwinEntity(
        entity_id="urn:systemmind:proc:30",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "post_wake_helper", "confidence_score": 1.0},
    )

    pre_entities = [p_sustained, p_terminated, vol_staled]
    post_entities = [p_sustained, p_spawned]

    record = reconciler.reconcile_state(gap, pre_entities, post_entities)

    assert record.entities_sustained_count == 1
    assert record.entities_terminated_count == 1
    assert record.entities_staled_count == 1
    assert record.entities_spawned_count == 1
    assert len(record.actions) == 4

    action_map = {a.entity_urn: a for a in record.actions}

    # Sustained entity has discounted confidence
    assert action_map["urn:systemmind:proc:10"].action_type == ReconciliationActionType.SUSTAINED_ACROSS_GAP.value
    assert action_map["urn:systemmind:proc:10"].confidence_score < 1.0

    # Ephemeral process terminated
    assert action_map["urn:systemmind:proc:20"].action_type == ReconciliationActionType.TERMINATED_DURING_GAP.value
    assert action_map["urn:systemmind:proc:20"].inferred_timestamp_epoch_ms == 1700000030000  # midpoint

    # Persistent volume marked stale
    assert action_map["urn:systemmind:vol:sdcard"].action_type == ReconciliationActionType.MARKED_STALE_PENDING_CONFIRMATION.value

    # Spawned process recorded
    assert action_map["urn:systemmind:proc:30"].action_type == ReconciliationActionType.SPAWNED_OR_ATTACHED_DURING_GAP.value


def test_confidence_discounting_curve() -> None:
    """Tests that epistemic confidence discount scales with gap duration and respects maximum cap."""
    reconciler = SystemStateReconciler(max_discount_pct=0.40)

    # Short gap (10s): ~6.7% discount
    d_short = reconciler.calculate_confidence_discount(10000)
    assert 0.05 <= d_short < 0.10

    # Medium gap (60s): ~15% discount
    d_med = reconciler.calculate_confidence_discount(60000)
    assert 0.14 <= d_med <= 0.16

    # Massive gap (1 hour): capped at 40%
    d_huge = reconciler.calculate_confidence_discount(3600000)
    assert d_huge == 0.40


def test_state_reconciliation_manager_persistence_and_queries(memory_db: sqlite3.Connection) -> None:
    """Tests SQLite persistence, foreign key cascading, and querying in StateReconciliationManager."""
    manager = StateReconciliationManager(memory_db)

    gap = CollectorGap(
        gap_id="gap-mgr-test",
        collector_id="mock_ps",
        device_id="dev-mgr",
        domain="proc",
        gap_start_epoch_ms=1700000000000,
        gap_end_epoch_ms=1700000070000,
        gap_duration_ms=70000,
        expected_cadence_ms=5000,
        gap_classification=GapClassification.SYSTEM_SLEEP_WAKE.value,
        detected_at_iso="2026-11-18T12:00:00Z",
    )

    p1 = TwinEntity(
        entity_id="urn:systemmind:proc:500",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "srv"},
    )
    p2 = TwinEntity(
        entity_id="urn:systemmind:proc:501",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "job"},
    )

    recon = manager.reconcile_and_record(gap, [p1, p2], [p1])

    # 1. get_gap
    fetched_gap = manager.get_gap(gap.gap_id)
    assert fetched_gap is not None
    assert fetched_gap.gap_duration_ms == 70000

    # 2. get_reconciliation
    fetched_recon = manager.get_reconciliation(recon.reconciliation_id)
    assert fetched_recon is not None
    assert fetched_recon.entities_sustained_count == 1
    assert fetched_recon.entities_terminated_count == 1
    assert len(fetched_recon.actions) == 2

    # 3. query_gaps_for_device
    gaps = manager.query_gaps_for_device("dev-mgr")
    assert len(gaps) == 1
    assert gaps[0].gap_id == gap.gap_id

    # 4. query_reconciliations_for_gap
    recons = manager.query_reconciliations_for_gap(gap.gap_id)
    assert len(recons) == 1
    assert recons[0].reconciliation_id == recon.reconciliation_id

    # 5. Foreign key cascade: deleting gap cascades to reconciliation records
    memory_db.execute("PRAGMA foreign_keys = ON;")
    memory_db.execute("DELETE FROM collector_gaps WHERE gap_id = ?;", (gap.gap_id,))
    assert manager.get_gap(gap.gap_id) is None
    assert manager.get_reconciliation(recon.reconciliation_id) is None


def test_apply_reconciliation_to_graph() -> None:
    """Tests updating an in-memory DigitalTwinGraph using reconciliation decisions."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)
    migrator.apply_all(conn=conn)

    manager = StateReconciliationManager(conn)
    graph = DigitalTwinGraph()

    p_run = TwinEntity(
        entity_id="urn:systemmind:proc:777",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "long_worker", "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )
    p_term = TwinEntity(
        entity_id="urn:systemmind:proc:888",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "short_job", "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )
    vol_stale = TwinEntity(
        entity_id="urn:systemmind:vol:ext",
        entity_type=TwinEntityType.FILESYSTEM_NODE,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"name": "usb_vol", "confidence_score": 1.0},
        provenance_source="telemetry_collector",
    )

    graph.add_entity(p_run)
    graph.add_entity(p_term)
    graph.add_entity(vol_stale)

    gap = CollectorGap(
        gap_id="gap-graph-test",
        collector_id="mock_ps",
        device_id="dev-graph",
        domain="proc",
        gap_start_epoch_ms=1000,
        gap_end_epoch_ms=70000,
        gap_duration_ms=69000,
        expected_cadence_ms=5000,
        gap_classification=GapClassification.SYSTEM_SLEEP_WAKE.value,
        detected_at_iso="2026-11-18T12:00:00Z",
    )

    # Post-gap: p_run sustained, p_term absent (terminated), vol_stale absent (staled)
    recon = manager.reconcile_and_record(gap, [p_run, p_term, vol_stale], [p_run])

    # Apply to graph
    manager.apply_reconciliation_to_graph(recon, graph)

    # p_term must be removed
    assert graph.get_entity("urn:systemmind:proc:888") is None

    # p_run must remain with discounted confidence
    updated_run = graph.get_entity("urn:systemmind:proc:777")
    assert updated_run is not None
    assert updated_run.attributes["confidence_score"] < 1.0

    # vol_stale must be marked stale
    updated_vol = graph.get_entity("urn:systemmind:vol:ext")
    assert updated_vol is not None
    assert updated_vol.is_stale is True
    assert updated_vol.attributes["stale_reason"] == "COLLECTOR_GAP"
    conn.close()


def test_packaging_validator_and_ast_safety() -> None:
    """Tests packaging validator and AST safety verification."""
    result = StateReconciliationValidator.audit()
    assert result.valid, f"Packaging audit failed with issues: {result.issues}"
    assert result.reconciliation_engine_present
    assert result.design_note_present
    assert result.migration_present
    assert result.tool_present
    assert result.ast_safety_valid
    assert result.charter_invariants_valid
    assert result.functional_reconciliation_valid
