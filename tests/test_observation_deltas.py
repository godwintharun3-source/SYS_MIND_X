"""Comprehensive unit, integration, and invariant tests for Day 074 Consecutive Observation Change Detection."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import pytest

from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.observation_deltas import ObservationDeltasValidator
from system_mind.twin.change_detector import (
    AttributeMutation,
    ChangeClassification,
    ObservationChangeDetector,
    ObservationDelta,
    ObservationDeltaManager,
)
from system_mind.twin.observation_records import (
    ObservationRecordManager,
    SystemObservationRecord,
)


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite database with migrations 0001 through 0009 applied."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0009_up_and_down_lifecycle() -> None:
    """Tests migration 0009 UP and DOWN lifecycle, rollback to version 8, and reapplication."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)

    # 1. Apply up to migration 9
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='observation_deltas';"
    )
    assert cursor.fetchone() is not None, "Table observation_deltas must exist"

    # Verify check constraint scan_proves_safe = 0
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO observation_deltas (
                delta_id, entity_urn, device_id, from_record_id, to_record_id,
                from_sequence, to_sequence, from_epoch_ms, to_epoch_ms,
                time_delta_ms, has_changed, change_classification,
                added_keys_json, removed_keys_json, modified_keys_json,
                change_count, detected_at_iso, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "delta-fail-safe",
                "urn:systemmind:cpu:total",
                "dev-test",
                "rec-1",
                "rec-2",
                1,
                2,
                1700000000000,
                1700000005000,
                5000,
                0,
                "NO_CHANGE",
                "[]",
                "[]",
                "{}",
                0,
                "2026-11-18T12:00:00Z",
                1,  # VIOLATES scan_proves_safe = 0
            ),
        )

    # Verify check constraint has_changed IN (0, 1)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO observation_deltas (
                delta_id, entity_urn, device_id, from_record_id, to_record_id,
                from_sequence, to_sequence, from_epoch_ms, to_epoch_ms,
                time_delta_ms, has_changed, change_classification,
                added_keys_json, removed_keys_json, modified_keys_json,
                change_count, detected_at_iso, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "delta-fail-bool",
                "urn:systemmind:cpu:total",
                "dev-test",
                "rec-1",
                "rec-2",
                1,
                2,
                1700000000000,
                1700000005000,
                5000,
                5,  # VIOLATES has_changed IN (0, 1)
                "NO_CHANGE",
                "[]",
                "[]",
                "{}",
                0,
                "2026-11-18T12:00:00Z",
                0,
            ),
        )

    # 2. Rollback to version 8
    migrator.rollback_to(target_version=8, conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='observation_deltas';"
    )
    assert cursor.fetchone() is None, "Table observation_deltas must be dropped on rollback to 8"

    # 3. Re-apply to version 9
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='observation_deltas';"
    )
    assert cursor.fetchone() is not None, "Table observation_deltas must exist after re-applying 9"
    conn.close()


def test_observation_delta_dataclass_invariants() -> None:
    """Tests ObservationDelta dataclass validation and Charter Invariant SC-03."""
    valid_delta = ObservationDelta(
        delta_id="delta-01",
        entity_urn="urn:systemmind:cpu:total",
        device_id="dev-test",
        from_record_id="rec-1",
        to_record_id="rec-2",
        from_sequence=1,
        to_sequence=2,
        from_epoch_ms=1700000000000,
        to_epoch_ms=1700000005000,
        time_delta_ms=5000,
        has_changed=False,
        change_classification=ChangeClassification.NO_CHANGE.value,
        added_keys=(),
        removed_keys=(),
        modified_keys={},
        change_count=0,
        detected_at_iso="2026-11-18T12:00:00Z",
        scan_proves_safe=False,
    )
    assert valid_delta.delta_id == "delta-01"
    assert "IDENTICAL" in valid_delta.summary()

    # Invariant SC-03: scan_proves_safe cannot be True
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        ObservationDelta(
            delta_id="delta-bad-safe",
            entity_urn="urn:systemmind:cpu:total",
            device_id="dev-test",
            from_record_id="rec-1",
            to_record_id="rec-2",
            from_sequence=1,
            to_sequence=2,
            from_epoch_ms=1700000000000,
            to_epoch_ms=1700000005000,
            time_delta_ms=5000,
            has_changed=False,
            change_classification="NO_CHANGE",
            added_keys=(),
            removed_keys=(),
            modified_keys={},
            change_count=0,
            detected_at_iso="2026-11-18T12:00:00Z",
            scan_proves_safe=True,
        )

    # Invariant: to_sequence must be strictly greater than from_sequence
    with pytest.raises(ValueError, match="Monotonic Sequence Violation"):
        ObservationDelta(
            delta_id="delta-bad-seq",
            entity_urn="urn:systemmind:cpu:total",
            device_id="dev-test",
            from_record_id="rec-1",
            to_record_id="rec-2",
            from_sequence=5,
            to_sequence=5,
            from_epoch_ms=1700000000000,
            to_epoch_ms=1700000005000,
            time_delta_ms=5000,
            has_changed=False,
            change_classification="NO_CHANGE",
            added_keys=(),
            removed_keys=(),
            modified_keys={},
            change_count=0,
            detected_at_iso="2026-11-18T12:00:00Z",
            scan_proves_safe=False,
        )

    # Invariant: to_epoch_ms cannot be earlier than from_epoch_ms
    with pytest.raises(ValueError, match="Timestamp Inversion Violation"):
        ObservationDelta(
            delta_id="delta-bad-time",
            entity_urn="urn:systemmind:cpu:total",
            device_id="dev-test",
            from_record_id="rec-1",
            to_record_id="rec-2",
            from_sequence=1,
            to_sequence=2,
            from_epoch_ms=1700000005000,
            to_epoch_ms=1700000000000,
            time_delta_ms=0,
            has_changed=False,
            change_classification="NO_CHANGE",
            added_keys=(),
            removed_keys=(),
            modified_keys={},
            change_count=0,
            detected_at_iso="2026-11-18T12:00:00Z",
            scan_proves_safe=False,
        )


def test_attribute_mutation_model() -> None:
    """Tests AttributeMutation serialization and fields."""
    mut = AttributeMutation(
        field_name="cpu_pct",
        old_value=12.5,
        new_value=25.0,
        change_type="MODIFIED",
        delta_numeric=12.5,
    )
    d = mut.to_dict()
    assert d["field_name"] == "cpu_pct"
    assert d["old_value"] == 12.5
    assert d["new_value"] == 25.0
    assert d["delta_numeric"] == 12.5
    assert d["change_type"] == "MODIFIED"


def test_digest_fast_path_no_change() -> None:
    """Tests that identical payload digests short-circuit comparison to NO_CHANGE."""
    detector = ObservationChangeDetector()

    rec1 = SystemObservationRecord(
        record_id="rec-1",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={"core_count": 8, "user_pct": 5.0},
        confidence_score=1.0,
        observation_status="ACTUAL",
    )

    rec2 = SystemObservationRecord(
        record_id="rec-2",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"core_count": 8, "user_pct": 5.0},
        confidence_score=1.0,
        observation_status="ACTUAL",
    )

    assert rec1.payload_sha256 == rec2.payload_sha256

    delta = detector.detect_change(rec1, rec2)
    assert not delta.has_changed
    assert delta.change_classification == ChangeClassification.NO_CHANGE.value
    assert delta.change_count == 0
    assert delta.added_keys == ()
    assert delta.removed_keys == ()
    assert delta.modified_keys == {}
    assert delta.time_delta_ms == 5000


def test_entity_and_device_invariance() -> None:
    """Tests rejection of cross-entity and cross-device delta calculations."""
    detector = ObservationChangeDetector()

    rec_cpu = SystemObservationRecord(
        record_id="rec-cpu",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={"util": 10},
    )

    rec_mem = SystemObservationRecord(
        record_id="rec-mem",
        device_id="dev-test",
        entity_urn="urn:systemmind:mem:total",
        collector_id="mock_mem",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"util": 20},
    )

    with pytest.raises(ValueError, match="Entity Mismatch Violation"):
        detector.detect_change(rec_cpu, rec_mem)

    rec_cpu_dev2 = SystemObservationRecord(
        record_id="rec-cpu-dev2",
        device_id="dev-other",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"util": 10},
    )

    with pytest.raises(ValueError, match="Device Mismatch Violation"):
        detector.detect_change(rec_cpu, rec_cpu_dev2)


def test_monotonic_sequence_and_timestamp_validation() -> None:
    """Tests sequence and timestamp monotonicity checks in ObservationChangeDetector."""
    detector = ObservationChangeDetector()

    rec1 = SystemObservationRecord(
        record_id="rec-1",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=5,
        payload={"util": 10},
    )

    rec2 = SystemObservationRecord(
        record_id="rec-2",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=6,
        payload={"util": 15},
    )

    with pytest.raises(ValueError, match="Timestamp Inversion"):
        detector.detect_change(rec1, rec2)

    rec3 = SystemObservationRecord(
        record_id="rec-3",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:10Z",
        observed_at_epoch_ms=1700000010000,
        sequence_number=4,
        payload={"util": 15},
    )

    with pytest.raises(ValueError, match="Monotonic Sequence Violation"):
        detector.detect_change(rec1, rec3)


def test_granular_attribute_mutations_and_delta_numeric() -> None:
    """Tests detection of added, removed, and modified attributes with numerical delta computation."""
    detector = ObservationChangeDetector()

    rec1 = SystemObservationRecord(
        record_id="rec-1",
        device_id="dev-test",
        entity_urn="urn:systemmind:proc:500",
        collector_id="mock_ps",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={
            "pid": 500,
            "name": "worker",
            "threads": 4,
            "temporary_tag": "active",
        },
    )

    rec2 = SystemObservationRecord(
        record_id="rec-2",
        device_id="dev-test",
        entity_urn="urn:systemmind:proc:500",
        collector_id="mock_ps",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={
            "pid": 500,
            "name": "worker",
            "threads": 6,
            "new_feature_flag": True,
        },
    )

    delta = detector.detect_change(rec1, rec2)
    assert delta.has_changed
    assert delta.change_classification == ChangeClassification.ATTRIBUTE_MUTATION.value
    assert delta.added_keys == ("new_feature_flag",)
    assert delta.removed_keys == ("temporary_tag",)
    assert "threads" in delta.modified_keys

    thread_mut = delta.modified_keys["threads"]
    assert thread_mut.old_value == 4
    assert thread_mut.new_value == 6
    assert thread_mut.delta_numeric == 2.0
    assert thread_mut.change_type == "MODIFIED"


def test_semantic_classifications() -> None:
    """Tests all semantic change classifications."""
    detector = ObservationChangeDetector(numeric_thresholds={"cpu_pct": 10.0})

    # 1. SIGNIFICANT_THRESHOLD_BREACH
    rec_cpu1 = SystemObservationRecord(
        record_id="rec-cpu-1",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={"cpu_pct": 15.0},
    )
    rec_cpu2 = SystemObservationRecord(
        record_id="rec-cpu-2",
        device_id="dev-test",
        entity_urn="urn:systemmind:cpu:total",
        collector_id="mock_cpu",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"cpu_pct": 35.0},  # +20.0 >= 10.0 threshold
    )
    delta_thresh = detector.detect_change(rec_cpu1, rec_cpu2)
    assert delta_thresh.change_classification == ChangeClassification.SIGNIFICANT_THRESHOLD_BREACH.value

    # 2. STATUS_DEGRADATION
    rec_stat1 = SystemObservationRecord(
        record_id="rec-stat-1",
        device_id="dev-test",
        entity_urn="urn:systemmind:net:en0",
        collector_id="mock_net",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={"status": "up"},
        observation_status="ACTUAL",
    )
    rec_stat2 = SystemObservationRecord(
        record_id="rec-stat-2",
        device_id="dev-test",
        entity_urn="urn:systemmind:net:en0",
        collector_id="mock_net",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"status": "up"},
        observation_status="DEGRADED",
    )
    delta_stat = detector.detect_change(rec_stat1, rec_stat2)
    assert delta_stat.change_classification == ChangeClassification.STATUS_DEGRADATION.value

    # 3. CONFIDENCE_SHIFT
    rec_conf1 = SystemObservationRecord(
        record_id="rec-conf-1",
        device_id="dev-test",
        entity_urn="urn:systemmind:hw:battery",
        collector_id="mock_batt",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={"cycle_count": 120},
        confidence_score=1.0,
    )
    rec_conf2 = SystemObservationRecord(
        record_id="rec-conf-2",
        device_id="dev-test",
        entity_urn="urn:systemmind:hw:battery",
        collector_id="mock_batt",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"cycle_count": 120},
        confidence_score=0.8,  # shift of 0.2 >= 0.1
    )
    delta_conf = detector.detect_change(rec_conf1, rec_conf2)
    assert delta_conf.change_classification == ChangeClassification.CONFIDENCE_SHIFT.value

    # 4. LIFECYCLE_TRANSITION
    rec_life1 = SystemObservationRecord(
        record_id="rec-life-1",
        device_id="dev-test",
        entity_urn="urn:systemmind:proc:999",
        collector_id="mock_ps",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={"status": "running"},
    )
    rec_life2 = SystemObservationRecord(
        record_id="rec-life-2",
        device_id="dev-test",
        entity_urn="urn:systemmind:proc:999",
        collector_id="mock_ps",
        observation_type="LIFECYCLE_EVENT",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"status": "exited", "exit_code": 0},
    )
    delta_life = detector.detect_change(rec_life1, rec_life2)
    assert delta_life.change_classification == ChangeClassification.LIFECYCLE_TRANSITION.value


def test_observation_delta_manager_persistence_and_queries(memory_db: sqlite3.Connection) -> None:
    """Tests delta persistence and multi-criteria queries in ObservationDeltaManager."""
    obs_mgr = ObservationRecordManager(memory_db)
    delta_mgr = ObservationDeltaManager(memory_db)

    urn = "urn:systemmind:proc:42"
    dev = "dev-persistence"

    # Insert 3 observations
    r1 = SystemObservationRecord(
        record_id="rec-p-1",
        device_id=dev,
        entity_urn=urn,
        collector_id="mock_ps",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:00Z",
        observed_at_epoch_ms=1700000000000,
        sequence_number=1,
        payload={"rss_mb": 100, "cpu_pct": 5.0},
    )
    r2 = SystemObservationRecord(
        record_id="rec-p-2",
        device_id=dev,
        entity_urn=urn,
        collector_id="mock_ps",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:05Z",
        observed_at_epoch_ms=1700000005000,
        sequence_number=2,
        payload={"rss_mb": 120, "cpu_pct": 28.0},  # CPU jump +23%
    )
    r3 = SystemObservationRecord(
        record_id="rec-p-3",
        device_id=dev,
        entity_urn=urn,
        collector_id="mock_ps",
        observation_type="METRIC_SAMPLE",
        observed_at_iso="2026-11-18T12:00:10Z",
        observed_at_epoch_ms=1700000010000,
        sequence_number=3,
        payload={"rss_mb": 120, "cpu_pct": 28.0},  # Identical to r2
    )

    obs_mgr.record_observation(r1)
    obs_mgr.record_observation(r2)
    obs_mgr.record_observation(r3)

    # 1. detect_and_record
    d1 = delta_mgr.detect_and_record(r1, r2)
    assert d1.has_changed
    assert d1.change_classification == ChangeClassification.SIGNIFICANT_THRESHOLD_BREACH.value

    # 2. detect_and_record_consecutive
    d2 = delta_mgr.detect_and_record_consecutive(urn)
    assert d2 is not None
    assert not d2.has_changed
    assert d2.change_classification == ChangeClassification.NO_CHANGE.value

    # 3. get_delta
    fetched_d1 = delta_mgr.get_delta(d1.delta_id)
    assert fetched_d1 is not None
    assert fetched_d1.delta_id == d1.delta_id
    assert fetched_d1.time_delta_ms == 5000
    assert fetched_d1.change_count == 2

    # 4. get_deltas_for_entity
    all_deltas = delta_mgr.get_deltas_for_entity(urn, only_changes=False)
    assert len(all_deltas) == 2

    changed_deltas = delta_mgr.get_deltas_for_entity(urn, only_changes=True)
    assert len(changed_deltas) == 1
    assert changed_deltas[0].delta_id == d1.delta_id

    # 5. query_significant_changes
    sig_deltas = delta_mgr.query_significant_changes(since_epoch_ms=1700000000000)
    assert len(sig_deltas) == 1
    assert sig_deltas[0].delta_id == d1.delta_id


def test_packaging_validator_and_ast_safety() -> None:
    """Tests packaging validator and AST safety verification."""
    result = ObservationDeltasValidator.audit()
    assert result.valid, f"Packaging audit failed with issues: {result.issues}"
    assert result.change_detector_present
    assert result.design_note_present
    assert result.migration_present
    assert result.tool_present
    assert result.ast_safety_valid
    assert result.charter_invariants_valid
    assert result.functional_deltas_valid
