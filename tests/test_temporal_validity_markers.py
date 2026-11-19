"""Comprehensive unit, integration, and invariant tests for Day 072 Temporal Validity & Stale Markers."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.temporal_validity import TemporalValidityValidator
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import DeviceIdentifierManager
from system_mind.twin.models import TwinEntity, TwinEntityType
from system_mind.twin.validity import (
    DOMAIN_DEFAULT_TTLS,
    DEFAULT_FALLBACK_TTL,
    EntityTemporalValidity,
    FreshnessState,
    StaleReason,
    TemporalValidityManager,
)


@pytest.fixture
def memory_db() -> sqlite3.Connection:
    """Fixture providing an initialized SQLite database with all migrations applied."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0007_up_and_down_lifecycle() -> None:
    """Tests migration 0007 UP and DOWN lifecycle, including rollback and reapplication."""
    db_cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)

    # 1. Apply up to migration 7
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_temporal_validity';"
    )
    assert cursor.fetchone() is not None, "Table entity_temporal_validity must exist"

    # Verify check constraint scan_proves_safe = 0
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO entity_temporal_validity (
                entity_urn, device_id, domain, last_observed_at_iso,
                last_observed_at_epoch_ms, valid_until_epoch_ms, ttl_seconds,
                freshness_state, staleness_score, is_stale, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "urn:systemmind:proc:fail",
                "dev-1",
                "proc",
                "2026-11-18T12:00:00Z",
                1000,
                2000,
                15.0,
                "FRESH",
                0.0,
                0,
                1,  # VIOLATES scan_proves_safe = 0
            ),
        )

    # 2. Rollback to version 6
    migrator.rollback_to(target_version=6, conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_temporal_validity';"
    )
    assert cursor.fetchone() is None, "Table entity_temporal_validity must be dropped on rollback to 6"

    # 3. Re-apply to version 7
    migrator.apply_all(conn=conn)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_temporal_validity';"
    )
    assert cursor.fetchone() is not None, "Table entity_temporal_validity must exist after re-applying 7"
    conn.close()


def test_entity_temporal_validity_model_invariants() -> None:
    """Tests EntityTemporalValidity dataclass invariant enforcement."""
    # Valid construction
    rec = EntityTemporalValidity(
        entity_urn="urn:systemmind:proc:101",
        device_id="8b14bd5b-dcd4-5d39-af4e-3e95c72e53ab",
        domain="proc",
        last_observed_at_iso="2026-11-18T12:00:00Z",
        last_observed_at_epoch_ms=1700000000000,
        valid_until_epoch_ms=1700000015000,
        ttl_seconds=15.0,
        freshness_state="FRESH",
        staleness_score=0.0,
        is_stale=False,
        scan_proves_safe=False,
    )
    assert rec.entity_urn == "urn:systemmind:proc:101"
    assert rec.scan_proves_safe is False

    # Invariant SC-03: scan_proves_safe must be False
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        EntityTemporalValidity(
            entity_urn="urn:systemmind:proc:101",
            device_id="8b14bd5b-dcd4-5d39-af4e-3e95c72e53ab",
            domain="proc",
            last_observed_at_iso="2026-11-18T12:00:00Z",
            last_observed_at_epoch_ms=1700000000000,
            valid_until_epoch_ms=1700000015000,
            ttl_seconds=15.0,
            freshness_state="FRESH",
            staleness_score=0.0,
            is_stale=False,
            scan_proves_safe=True,  # VIOLATION
        )

    # Invariant INV-VAL-03: staleness score bounded
    with pytest.raises(ValueError, match="Staleness Score Out of Bounds"):
        EntityTemporalValidity(
            entity_urn="urn:systemmind:proc:101",
            device_id="8b14bd5b-dcd4-5d39-af4e-3e95c72e53ab",
            domain="proc",
            last_observed_at_iso="2026-11-18T12:00:00Z",
            last_observed_at_epoch_ms=1700000000000,
            valid_until_epoch_ms=1700000015000,
            staleness_score=1.5,  # OUT OF BOUNDS
        )

    # Invariant INV-VAL-02: valid_until >= last_observed_at
    with pytest.raises(ValueError, match="Temporal Validity Inversion"):
        EntityTemporalValidity(
            entity_urn="urn:systemmind:proc:101",
            device_id="8b14bd5b-dcd4-5d39-af4e-3e95c72e53ab",
            domain="proc",
            last_observed_at_iso="2026-11-18T12:00:00Z",
            last_observed_at_epoch_ms=1700000015000,
            valid_until_epoch_ms=1700000000000,  # INVERSION
        )


def test_freshness_evaluation_lifecycle() -> None:
    """Tests deterministic 5-state freshness decay lifecycle."""
    t0 = 1700000000000
    ttl = 20.0
    max_stale = 60.0

    # 1. 0s elapsed -> FRESH, score = 0.0
    state, score = TemporalValidityManager.evaluate_freshness(t0, t0, ttl, max_stale)
    assert state == FreshnessState.FRESH
    assert score == 0.0

    # 2. 5s elapsed (half window = 10s) -> FRESH, score = 0.125
    state, score = TemporalValidityManager.evaluate_freshness(t0, t0 + 5000, ttl, max_stale)
    assert state == FreshnessState.FRESH
    assert 0.0 < score <= 0.5

    # 3. 15s elapsed (between ttl/2 and ttl) -> AGING, 0.5 < score <= 0.8
    state, score = TemporalValidityManager.evaluate_freshness(t0, t0 + 15000, ttl, max_stale)
    assert state == FreshnessState.AGING
    assert 0.5 < score <= 0.8

    # 4. 30s elapsed (between ttl and max_stale) -> STALE, 0.8 < score <= 1.0
    state, score = TemporalValidityManager.evaluate_freshness(t0, t0 + 30000, ttl, max_stale)
    assert state == FreshnessState.STALE
    assert 0.8 < score <= 1.0

    # 5. 70s elapsed (> max_stale) -> EXPIRED, score = 1.0
    state, score = TemporalValidityManager.evaluate_freshness(t0, t0 + 70000, ttl, max_stale)
    assert state == FreshnessState.EXPIRED
    assert score == 1.0


def test_domain_ttl_defaults() -> None:
    """Verifies domain-specific default TTLs and fallback handling."""
    assert DOMAIN_DEFAULT_TTLS["proc"] == (15.0, 45.0)
    assert DOMAIN_DEFAULT_TTLS["cpu"] == (30.0, 90.0)
    assert DOMAIN_DEFAULT_TTLS["net"] == (45.0, 120.0)
    assert DOMAIN_DEFAULT_TTLS["svc"] == (120.0, 600.0)
    assert DOMAIN_DEFAULT_TTLS["vol"] == (300.0, 1800.0)
    assert DOMAIN_DEFAULT_TTLS["app"] == (3600.0, 86400.0)
    assert DOMAIN_DEFAULT_TTLS["host"] == (86400.0, 604800.0)

    # Fallback for unknown domain
    ttl, max_stale = TemporalValidityManager.get_domain_ttls("custom_peripheral")
    assert (ttl, max_stale) == DEFAULT_FALLBACK_TTL


def test_record_entity_observation_and_query(memory_db: sqlite3.Connection) -> None:
    """Tests recording observations and querying active/stale records."""
    manager = TemporalValidityManager(memory_db)
    dev_id = "test-device-uuid"
    t0 = 1700000000000
    t0_iso = "2026-11-18T12:00:00Z"

    # Record host observation
    host_rec = manager.record_entity_observation(
        entity_urn="urn:systemmind:host:mach-1",
        device_id=dev_id,
        observed_at_iso=t0_iso,
        observed_at_epoch_ms=t0,
    )
    assert host_rec.domain == "host"
    assert host_rec.ttl_seconds == 86400.0
    assert host_rec.valid_until_epoch_ms == t0 + 86400000
    assert host_rec.is_stale is False

    # Record process observation with explicit TTL
    proc_rec = manager.record_entity_observation(
        entity_urn="urn:systemmind:proc:500",
        device_id=dev_id,
        observed_at_iso=t0_iso,
        observed_at_epoch_ms=t0,
        ttl_seconds=10.0,
    )
    assert proc_rec.domain == "proc"
    assert proc_rec.ttl_seconds == 10.0
    assert proc_rec.valid_until_epoch_ms == t0 + 10000

    # Query single entity
    fetched = manager.get_validity("urn:systemmind:proc:500")
    assert fetched is not None
    assert fetched.entity_urn == "urn:systemmind:proc:500"
    assert fetched.is_stale is False

    # List all active
    active = manager.list_active_entities()
    assert len(active) == 2
    assert {r.entity_urn for r in active} == {"urn:systemmind:host:mach-1", "urn:systemmind:proc:500"}


def test_non_destructive_staleness_marking(memory_db: sqlite3.Connection) -> None:
    """Tests that marking an entity stale preserves it in database history (non-destructive)."""
    manager = TemporalValidityManager(memory_db)
    dev_id = "test-device-uuid"
    t0 = 1700000000000
    t0_iso = "2026-11-18T12:00:00Z"

    manager.record_entity_observation(
        entity_urn="urn:systemmind:proc:201",
        device_id=dev_id,
        observed_at_iso=t0_iso,
        observed_at_epoch_ms=t0,
        ttl_seconds=15.0,
    )

    # Mark stale due to process exit
    stale_rec = manager.mark_stale(
        entity_urn="urn:systemmind:proc:201",
        reason=StaleReason.PROCESS_EXIT,
        marked_at_iso="2026-11-18T12:00:10Z",
    )
    assert stale_rec is not None
    assert stale_rec.is_stale is True
    assert stale_rec.stale_reason == StaleReason.PROCESS_EXIT.value
    assert stale_rec.freshness_state == FreshnessState.STALE.value

    # Check non-destructive persistence: entity still exists in table
    all_recs = manager.list_validity_records()
    assert len(all_recs) == 1
    assert all_recs[0].entity_urn == "urn:systemmind:proc:201"

    stale_list = manager.list_stale_entities()
    assert len(stale_list) == 1

    active_list = manager.list_active_entities()
    assert len(active_list) == 0


def test_reversible_freshness(memory_db: sqlite3.Connection) -> None:
    """Tests that a fresh observation clears stale markers and extends validity."""
    manager = TemporalValidityManager(memory_db)
    dev_id = "test-device-uuid"
    t0 = 1700000000000
    t0_iso = "2026-11-18T12:00:00Z"

    # Step 1: Record initial observation
    manager.record_entity_observation(
        entity_urn="urn:systemmind:svc:sshd",
        device_id=dev_id,
        observed_at_iso=t0_iso,
        observed_at_epoch_ms=t0,
        ttl_seconds=120.0,
    )

    # Step 2: Mark stale (e.g. service temporarily stopped)
    manager.mark_stale(
        entity_urn="urn:systemmind:svc:sshd",
        reason=StaleReason.SERVICE_STOPPED,
    )
    stale = manager.get_validity("urn:systemmind:svc:sshd")
    assert stale is not None and stale.is_stale is True

    # Step 3: Reversible Freshness - service restarts and is observed again
    t1 = t0 + 60000
    t1_iso = "2026-11-18T12:01:00Z"
    refreshed = manager.record_entity_observation(
        entity_urn="urn:systemmind:svc:sshd",
        device_id=dev_id,
        observed_at_iso=t1_iso,
        observed_at_epoch_ms=t1,
        ttl_seconds=120.0,
    )
    assert refreshed.is_stale is False
    assert refreshed.stale_reason is None
    assert refreshed.freshness_state == FreshnessState.FRESH.value
    assert refreshed.staleness_score == 0.0
    assert refreshed.valid_until_epoch_ms == t1 + 120000

    # Ensure persistence reflects cleared state
    fetched = manager.get_validity("urn:systemmind:svc:sshd")
    assert fetched is not None
    assert fetched.is_stale is False
    assert fetched.stale_reason is None


def test_reconcile_missing_entities(memory_db: sqlite3.Connection) -> None:
    """Tests marking active domain entities stale when missing from telemetry sweep."""
    manager = TemporalValidityManager(memory_db)
    dev_id = "test-device-uuid"
    t0 = 1700000000000
    t0_iso = "2026-11-18T12:00:00Z"

    # Record 3 processes
    manager.record_entity_observation("urn:systemmind:proc:1", dev_id, t0_iso, t0)
    manager.record_entity_observation("urn:systemmind:proc:2", dev_id, t0_iso, t0)
    manager.record_entity_observation("urn:systemmind:proc:3", dev_id, t0_iso, t0)

    # Next telemetry scan only observed proc:1 and proc:2 (proc:3 vanished)
    missing = manager.reconcile_missing_entities(
        observed_urns=["urn:systemmind:proc:1", "urn:systemmind:proc:2"],
        domain="proc",
        device_id=dev_id,
    )

    assert len(missing) == 1
    assert missing[0].entity_urn == "urn:systemmind:proc:3"
    assert missing[0].is_stale is True
    assert missing[0].stale_reason == StaleReason.UNOBSERVED_IN_SCAN.value

    # Verify proc:1 and proc:2 remain active
    active = manager.list_active_entities(domain="proc")
    assert len(active) == 2
    assert {r.entity_urn for r in active} == {"urn:systemmind:proc:1", "urn:systemmind:proc:2"}


def test_scan_and_update_expired(memory_db: sqlite3.Connection) -> None:
    """Tests time-advancement scan transitioning expired entities."""
    manager = TemporalValidityManager(memory_db)
    dev_id = "test-device-uuid"
    t0 = 1700000000000
    t0_iso = "2026-11-18T12:00:00Z"

    # Process with TTL 15s (valid until t0 + 15000, max stale t0 + 45000)
    manager.record_entity_observation(
        entity_urn="urn:systemmind:proc:777",
        device_id=dev_id,
        observed_at_iso=t0_iso,
        observed_at_epoch_ms=t0,
        ttl_seconds=15.0,
    )

    # 10s elapsed: not expired yet
    expired_10s = manager.scan_and_update_expired(current_epoch_ms=t0 + 10000)
    assert len(expired_10s) == 0

    # 25s elapsed: validity expired (> 15s), entered STALE window
    expired_25s = manager.scan_and_update_expired(current_epoch_ms=t0 + 25000)
    assert len(expired_25s) == 1
    assert expired_25s[0].entity_urn == "urn:systemmind:proc:777"
    assert expired_25s[0].is_stale is True
    assert expired_25s[0].stale_reason == StaleReason.TTL_EXPIRED.value


def test_sync_graph_staleness(memory_db: sqlite3.Connection) -> None:
    """Tests synchronizing staleness from validity manager into in-memory DigitalTwinGraph."""
    manager = TemporalValidityManager(memory_db)
    graph = DigitalTwinGraph()
    dev_id = "test-device-uuid"
    t0 = 1700000000000
    t0_iso = "2026-11-18T12:00:00Z"

    urn = "urn:systemmind:proc:888"
    manager.record_entity_observation(urn, dev_id, t0_iso, t0, ttl_seconds=15.0)

    graph.add_entity(
        TwinEntity(
            entity_id=urn,
            entity_type=TwinEntityType.PROCESS,
            ownership=ComponentOwnership.USER_MANAGED,
            created_at=t0_iso,
            updated_at=t0_iso,
            provenance_source="telemetry_pipeline",
            is_stale=False,
        )
    )

    # Mark stale in DB
    manager.mark_stale(urn, StaleReason.PROCESS_EXIT)

    # Synchronize into graph
    synced_count = manager.sync_graph_staleness(graph=graph, current_epoch_ms=t0 + 20000)
    assert synced_count == 1

    entity = graph.get_entity(urn)
    assert entity is not None
    assert entity.is_stale is True


def test_packaging_validator_and_ast_safety() -> None:
    """Tests that the packaging validator passes and verifies AST safety (SC-01 & SC-03)."""
    audit = TemporalValidityValidator.audit()
    assert audit.valid is True
    assert len(audit.issues) == 0
    assert audit.validity_engine_present is True
    assert audit.migration_present is True
    assert audit.design_note_present is True
    assert audit.tool_present is True
    assert audit.ast_safety_valid is True
    assert audit.charter_invariants_valid is True
    assert audit.functional_validity_valid is True
    assert audit.scan_proves_safe is False
