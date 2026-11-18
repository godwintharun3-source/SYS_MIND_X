"""Unit, integration, and safety invariant test suite for Day 069 Timestamped System Observation Records."""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import pytest

from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.system_observations import SystemObservationsValidator
from system_mind.twin.identity import DeviceIdentifierManager, StableEntityIdGenerator
from system_mind.twin.observation_records import (
    ObservationRecordManager,
    SystemObservationRecord,
    compute_observation_payload_digest,
)
from system_mind.twin.temporal import ObservationType, ProvenanceStatus


@pytest.fixture
def memory_db_conn() -> sqlite3.Connection:
    """Provides an in-memory SQLite connection with all migrations applied."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0005_up_and_down_lifecycle() -> None:
    """Verifies that migration 0005 creates system_observation_records table and rolls back cleanly."""
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
        assert "system_observation_records" in tables

        # Verify indices exist
        indices = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index';"
            ).fetchall()
        ]
        assert "idx_obs_records_entity_seq" in indices
        assert "idx_obs_records_observed_at" in indices
        assert "idx_obs_records_epoch_ms" in indices
        assert "idx_obs_records_collector" in indices
        assert "idx_obs_records_device" in indices
        assert "idx_obs_records_status" in indices

        # Rollback migration 0005 (to target version 4)
        rolled_back = migrator.rollback_to(target_version=4, conn=conn)
        assert any(r.version == 5 for r in rolled_back)

        # Verify table and indices dropped
        tables_after = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "system_observation_records" not in tables_after

        # Re-apply
        reapplied = migrator.apply_migration(5, conn=conn)
        assert reapplied.version == 5
    finally:
        conn.close()


def test_system_observation_record_validation_and_serialization() -> None:
    """Verifies dataclass validation, default values, and serialization round-trip."""
    payload = {"model": "Apple Silicon", "cores": 8}
    digest = compute_observation_payload_digest(payload)

    record = SystemObservationRecord(
        record_id="obs-001",
        device_id="dev-12345",
        entity_urn="urn:systemmind:host:dev-12345",
        collector_id="macos_identity_sensor",
        observation_type=ObservationType.STATE_SNAPSHOT.value,
        observed_at_iso="2026-11-18T11:00:00+00:00",
        observed_at_epoch_ms=1763463600000,
        source_monotonic_ns=100020003000,
        confidence_score=0.98,
        confidence_tier="KERNEL_AUTHORITATIVE",
        provenance_status=ProvenanceStatus.VERIFIED_KERNEL.value,
        sequence_number=1,
        payload=payload,
        metadata={"latency_ms": 1.5},
        scan_proves_safe=False,
    )

    assert record.payload_sha256 == digest
    assert record.is_mock is False
    assert record.observation_status == "ACTUAL"

    # Test dictionary serialization round-trip
    d = record.to_dict()
    reconstructed = SystemObservationRecord.from_dict(d)
    assert reconstructed == record

    # Test SQLite row serialization
    params = record.to_sqlite_params()
    assert params[0] == "obs-001"
    assert params[1] == "dev-12345"
    assert params[2] == "urn:systemmind:host:dev-12345"
    assert params[9] == 0.98
    assert params[19] == 0  # scan_proves_safe in DB must be 0


def test_charter_invariant_sc03_scan_proves_safe_is_false(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies that scan_proves_safe=True is rejected at Python model and database constraint levels."""
    # 1. Python dataclass rejection
    with pytest.raises(ValueError, match="Charter Invariant Violation.*scan_proves_safe"):
        SystemObservationRecord(
            record_id="obs-bad-1",
            device_id="dev-1",
            entity_urn="urn:systemmind:host:dev-1",
            collector_id="test",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T11:00:00+00:00",
            observed_at_epoch_ms=1000,
            scan_proves_safe=True,  # Prohibited
        )

    # 2. Database check constraint rejection
    with pytest.raises(sqlite3.IntegrityError):
        memory_db_conn.execute(
            """
            INSERT INTO system_observation_records (
                record_id, device_id, entity_urn, collector_id, observation_type,
                observed_at_iso, observed_at_epoch_ms, confidence_score,
                confidence_tier, provenance_status, sequence_number,
                payload_sha256, payload_json, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
            """,
            (
                "obs-db-bad", "dev-1", "urn:systemmind:host:dev-1", "test",
                "STATE_SNAPSHOT", "2026-11-18T11:00:00+00:00", 1000,
                1.0, "KERNEL_AUTHORITATIVE", "VERIFIED_KERNEL", 1,
                "dummy_hash", "{}",
            ),
        )


def test_bounded_confidence_score_and_tier_invariants(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies confidence score bounds [0.0, 1.0] and mock tier restrictions."""
    # Rejection: score > 1.0
    with pytest.raises(ValueError, match="Confidence Score Out of Bounds"):
        SystemObservationRecord(
            record_id="obs-conf-high",
            device_id="dev-1",
            entity_urn="urn:systemmind:host:dev-1",
            collector_id="test",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T11:00:00+00:00",
            observed_at_epoch_ms=1000,
            confidence_score=1.01,
        )

    # Rejection: score < 0.0
    with pytest.raises(ValueError, match="Confidence Score Out of Bounds"):
        SystemObservationRecord(
            record_id="obs-conf-low",
            device_id="dev-1",
            entity_urn="urn:systemmind:host:dev-1",
            collector_id="test",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T11:00:00+00:00",
            observed_at_epoch_ms=1000,
            confidence_score=-0.05,
        )

    # Rejection: Mock observation cannot claim kernel authority
    with pytest.raises(ValueError, match="Mock Provenance Violation"):
        SystemObservationRecord(
            record_id="obs-mock-spoof",
            device_id="dev-1",
            entity_urn="urn:systemmind:host:dev-1",
            collector_id="test",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T11:00:00+00:00",
            observed_at_epoch_ms=1000,
            confidence_tier="KERNEL_AUTHORITATIVE",
            is_mock=True,
        )

    # Database check constraint rejection for out-of-bounds score
    with pytest.raises(sqlite3.IntegrityError):
        memory_db_conn.execute(
            """
            INSERT INTO system_observation_records (
                record_id, device_id, entity_urn, collector_id, observation_type,
                observed_at_iso, observed_at_epoch_ms, confidence_score,
                confidence_tier, provenance_status, sequence_number,
                payload_sha256, payload_json, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
            """,
            (
                "obs-db-conf", "dev-1", "urn:systemmind:host:dev-1", "test",
                "STATE_SNAPSHOT", "2026-11-18T11:00:00+00:00", 1000,
                1.5, "KERNEL_AUTHORITATIVE", "VERIFIED_KERNEL", 1,
                "dummy_hash", "{}",
            ),
        )


def test_monotonic_sequence_enforcement(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies that sequence numbers and timestamps progress monotonically per entity."""
    manager = ObservationRecordManager(memory_db_conn)
    entity_urn = "urn:systemmind:proc:dev-1:1000:1:e68a56cd"

    rec1 = ObservationRecordManager.create_record(
        device_id="dev-1",
        entity_urn=entity_urn,
        collector_id="macos_process_sensor",
        payload={"rss": 100},
        observed_at_epoch_ms=1000,
        sequence_number=1,
    )
    manager.record_observation(rec1)

    # Rejection: duplicate sequence number
    rec2_dup = ObservationRecordManager.create_record(
        device_id="dev-1",
        entity_urn=entity_urn,
        collector_id="macos_process_sensor",
        payload={"rss": 110},
        observed_at_epoch_ms=2000,
        sequence_number=1,  # Duplicate seq
    )
    with pytest.raises(ValueError, match="Monotonic Sequence Violation"):
        manager.record_observation(rec2_dup)

    # Rejection: timestamp inversion
    rec2_inv = ObservationRecordManager.create_record(
        device_id="dev-1",
        entity_urn=entity_urn,
        collector_id="macos_process_sensor",
        payload={"rss": 110},
        observed_at_epoch_ms=500,  # Earlier than 1000
        sequence_number=2,
    )
    with pytest.raises(ValueError, match="Timestamp Inversion Violation"):
        manager.record_observation(rec2_inv)

    # Valid progression
    rec2_valid = ObservationRecordManager.create_record(
        device_id="dev-1",
        entity_urn=entity_urn,
        collector_id="macos_process_sensor",
        payload={"rss": 120},
        observed_at_epoch_ms=2000,
        sequence_number=2,
    )
    manager.record_observation(rec2_valid)

    # Independent entity starts with seq 1 cleanly
    rec_other = ObservationRecordManager.create_record(
        device_id="dev-1",
        entity_urn="urn:systemmind:app:com.apple.finder",
        collector_id="macos_app_sensor",
        payload={"version": "14.0"},
        observed_at_epoch_ms=500,
        sequence_number=1,
    )
    manager.record_observation(rec_other)
    assert manager.count_observations() == 3


def test_observation_record_manager_crud_and_query_filtering(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies CRUD operations, retrieval, and multi-parameter filtering."""
    manager = ObservationRecordManager(memory_db_conn)
    dev_id = "dev-test-1"

    host_urn = "urn:systemmind:host:dev-test-1"
    cpu_urn = "urn:systemmind:cpu:arm64:a89eb8736a0e:8"

    r1 = ObservationRecordManager.create_record(
        device_id=dev_id,
        entity_urn=host_urn,
        collector_id="macos_identity_sensor",
        observation_type=ObservationType.STATE_SNAPSHOT.value,
        payload={"model": "M1"},
        observed_at_epoch_ms=1000,
        sequence_number=1,
    )
    r2 = ObservationRecordManager.create_record(
        device_id=dev_id,
        entity_urn=cpu_urn,
        collector_id="macos_cpu_sensor",
        observation_type=ObservationType.STATE_SNAPSHOT.value,
        payload={"usage": 15},
        observed_at_epoch_ms=2000,
        sequence_number=1,
    )
    r3 = ObservationRecordManager.create_record(
        device_id=dev_id,
        entity_urn=cpu_urn,
        collector_id="macos_cpu_sensor",
        observation_type=ObservationType.ATTRIBUTE_DELTA.value,
        payload={"usage": 25},
        observed_at_epoch_ms=3000,
        sequence_number=2,
    )
    r4_mock = ObservationRecordManager.create_record(
        device_id=dev_id,
        entity_urn=cpu_urn,
        collector_id="macos_cpu_sensor",
        observation_type=ObservationType.HEARTBEAT.value,
        payload={"heartbeat": True},
        observed_at_epoch_ms=4000,
        confidence_tier="ESTIMATED_MOCK",
        sequence_number=3,
        is_mock=True,
    )

    manager.record_observation(r1)
    manager.record_observation(r2)
    manager.record_observation(r3)
    manager.record_observation(r4_mock)

    # Test get_record
    retrieved = manager.get_record(r1.record_id)
    assert retrieved is not None
    assert retrieved.entity_urn == host_urn

    # Test get_latest_observation
    latest_cpu = manager.get_latest_observation(cpu_urn)
    assert latest_cpu is not None
    assert latest_cpu.sequence_number == 3
    assert latest_cpu.is_mock is True

    # Test query_observations by collector
    cpu_obs = manager.query_observations(collector_id="macos_cpu_sensor")
    assert len(cpu_obs) == 3

    # Test query_observations excluding mock
    live_cpu_obs = manager.query_observations(collector_id="macos_cpu_sensor", include_mock=False)
    assert len(live_cpu_obs) == 2

    # Test query_observations time window
    window_obs = manager.query_observations(since_epoch_ms=1500, until_epoch_ms=3500)
    assert len(window_obs) == 2
    assert [x.sequence_number for x in window_obs] == [1, 2]


def test_point_in_time_state_reconstruction(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies that an entity's historical state is accurately reconstructed across snapshots and deltas."""
    manager = ObservationRecordManager(memory_db_conn)
    proc_urn = "urn:systemmind:proc:dev-1:1000:501:abc12345"

    # Sequence of observations for process:
    # T=1000: Initial snapshot (name="agent", pid=501, status="running", rss=1000, cpu=2.0)
    # T=2000: Delta 1 (rss=1500, cpu=3.5)
    # T=3000: Delta 2 (cpu=1.2, threads=4)
    # T=4000: Lifecycle event (status="terminated", exit_code=0)

    manager.record_observation(
        ObservationRecordManager.create_record(
            device_id="dev-1",
            entity_urn=proc_urn,
            collector_id="macos_process_sensor",
            observation_type=ObservationType.STATE_SNAPSHOT.value,
            payload={"name": "agent", "pid": 501, "status": "running", "rss": 1000, "cpu": 2.0},
            observed_at_epoch_ms=1000,
            sequence_number=1,
        )
    )
    manager.record_observation(
        ObservationRecordManager.create_record(
            device_id="dev-1",
            entity_urn=proc_urn,
            collector_id="macos_process_sensor",
            observation_type=ObservationType.ATTRIBUTE_DELTA.value,
            payload={"rss": 1500, "cpu": 3.5},
            observed_at_epoch_ms=2000,
            sequence_number=2,
        )
    )
    manager.record_observation(
        ObservationRecordManager.create_record(
            device_id="dev-1",
            entity_urn=proc_urn,
            collector_id="macos_process_sensor",
            observation_type=ObservationType.ATTRIBUTE_DELTA.value,
            payload={"cpu": 1.2, "threads": 4},
            observed_at_epoch_ms=3000,
            sequence_number=3,
        )
    )
    manager.record_observation(
        ObservationRecordManager.create_record(
            device_id="dev-1",
            entity_urn=proc_urn,
            collector_id="macos_process_sensor",
            observation_type=ObservationType.LIFECYCLE_EVENT.value,
            payload={"status": "terminated", "exit_code": 0},
            observed_at_epoch_ms=4000,
            sequence_number=4,
        )
    )

    # 1. Before any observations (T=500)
    assert manager.reconstruct_state_at(proc_urn, 500) == {}

    # 2. At T=1500 (after snapshot, before deltas)
    s1500 = manager.reconstruct_state_at(proc_urn, 1500)
    assert s1500["status"] == "running"
    assert s1500["rss"] == 1000
    assert s1500["cpu"] == 2.0
    assert "threads" not in s1500

    # 3. At T=2500 (after Delta 1)
    s2500 = manager.reconstruct_state_at(proc_urn, 2500)
    assert s2500["rss"] == 1500
    assert s2500["cpu"] == 3.5
    assert s2500["name"] == "agent"

    # 4. At T=3500 (after Delta 2)
    s3500 = manager.reconstruct_state_at(proc_urn, 3500)
    assert s3500["rss"] == 1500
    assert s3500["cpu"] == 1.2
    assert s3500["threads"] == 4
    assert s3500["status"] == "running"

    # 5. At T=4500 (after lifecycle event)
    s4500 = manager.reconstruct_state_at(proc_urn, 4500)
    assert s4500["status"] == "terminated"
    assert s4500["exit_code"] == 0
    assert s4500["rss"] == 1500


def test_system_observations_packaging_validator() -> None:
    """Verifies that SystemObservationsValidator audits the component cleanly."""
    result = SystemObservationsValidator.audit()
    assert result.valid is True
    assert len(result.issues) == 0
    assert result.migration_present is True
    assert result.models_present is True
    assert result.design_note_present is True
    assert result.tool_present is True
    assert result.ast_safety_valid is True
    assert result.charter_invariants_valid is True
    assert result.schema_constraints_valid is True
    assert result.reconstruction_valid is True


def test_ast_safety_sc01_zero_ambient_shell() -> None:
    """Verifies zero ambient shell executions across Day 069 observation persistence code."""
    root = Path(__file__).resolve().parent.parent
    targets = [
        root / "src/system_mind/twin/observation_records.py",
        root / "src/system_mind/packaging/system_observations.py",
        root / "tools/detect_system_observations.py",
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
