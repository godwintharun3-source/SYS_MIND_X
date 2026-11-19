"""Comprehensive unit, integration, and safety invariant tests for Day 076 Application Lifecycle Tracking."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List
import uuid

import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.database.entity_models import ApplicationEntityRecord
from system_mind.packaging.app_lifecycle import ApplicationLifecycleValidator
from system_mind.twin.app_lifecycle import (
    ApplicationDetectionSource,
    ApplicationLifecycleDiff,
    ApplicationLifecycleEvent,
    ApplicationLifecycleEventType,
    ApplicationLifecycleManager,
    ApplicationLifecycleTracker,
    sanitize_bundle_id_for_urn,
)
from system_mind.twin.event_store import GENESIS_PREV_HASH, SystemEventStore
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import EntityDomain, create_entity_urn
from system_mind.twin.models import TwinEntity, TwinEntityType, TwinRelationType

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_full_schema() -> str:
    """Combines all migrations 0001 through 0011 into a complete UP SQL script."""
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


# --- Test 1: Migration 0011 UP and DOWN Lifecycle & Check Constraint ---

def test_migration_0011_up_and_down():
    """Verifies Migration 0011 schema creation, constraint enforcement, and rollback."""
    conn = sqlite3.connect(":memory:")
    # First apply prior migrations 0001..0010
    migrations_dir = REPO_ROOT / "src/system_mind/database/migrations"
    prior_files = sorted([f for f in migrations_dir.glob("*.sql") if not f.name.startswith("0011")])
    for pf in prior_files:
        conn.executescript(pf.read_text(encoding="utf-8").split("-- DOWN")[0].replace("-- UP", ""))

    migration_0011 = migrations_dir / "0011_application_lifecycle_events.sql"
    content = migration_0011.read_text(encoding="utf-8")
    up_script, down_script = content.split("-- DOWN")
    up_script = up_script.replace("-- UP", "")

    # Execute UP
    conn.executescript(up_script)

    # Verify table and indexes exist
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='application_lifecycle_events'")
    assert cursor.fetchone() is not None

    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='application_lifecycle_events'")
    indexes = {row[0] for row in cursor.fetchall()}
    assert "idx_app_lifecycle_events_device_id" in indexes
    assert "idx_app_lifecycle_events_entity_urn" in indexes
    assert "idx_app_lifecycle_events_bundle_id" in indexes
    assert "idx_app_lifecycle_events_event_type" in indexes
    assert "idx_app_lifecycle_events_epoch_ms" in indexes
    assert "idx_app_lifecycle_events_ownership" in indexes

    # Verify Charter Invariant SC-03: scan_proves_safe check constraint
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO application_lifecycle_events (
                event_id, device_id, entity_urn, event_type,
                bundle_id, app_name, bundle_path, version,
                ownership, detection_source, observed_at_iso,
                observed_at_epoch_ms, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                "ev-test-fail",
                "dev-01",
                "urn:systemmind:app:com.fail",
                "APPLICATION_INSTALLED",
                "com.fail",
                "FailApp",
                "/Applications/Fail.app",
                "1.0.0",
                "USER_MANAGED",
                "INVENTORY_DIFF",
                "2026-11-18T12:00:00Z",
                1700000000000,
            ),
        )

    # Execute DOWN
    conn.executescript(down_script)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='application_lifecycle_events'")
    assert cursor.fetchone() is None


# --- Test 2: Dataclass Invariants & Serialization ---

def test_application_lifecycle_event_dataclass_invariants():
    """Verifies ApplicationLifecycleEvent validation, invariant enforcement, and serialization."""
    device_id = "00000000-0000-4000-8000-000000000001"
    urn = create_entity_urn(EntityDomain.APPLICATION, "com.test.app")

    # Invariant SC-03: scan_proves_safe must be False
    with pytest.raises(ValueError, match="SC-03"):
        ApplicationLifecycleEvent(
            device_id=device_id,
            entity_urn=urn,
            event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
            bundle_id="com.test.app",
            app_name="TestApp",
            bundle_path="/Applications/TestApp.app",
            version="1.0.0",
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    # Invariant INV-APP-02: invalid entity URN
    with pytest.raises(ValueError, match="Invalid canonical entity URN"):
        ApplicationLifecycleEvent(
            device_id=device_id,
            entity_urn="invalid-urn-syntax",
            event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
            bundle_id="com.test.app",
            app_name="TestApp",
            bundle_path="/Applications/TestApp.app",
            version="1.0.0",
        )

    # Empty field validations
    with pytest.raises(ValueError, match="device_id cannot be empty"):
        ApplicationLifecycleEvent(
            device_id="",
            entity_urn=urn,
            event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
            bundle_id="com.test.app",
            app_name="TestApp",
            bundle_path="/Applications/TestApp.app",
            version="1.0.0",
        )

    with pytest.raises(ValueError, match="bundle_id cannot be empty"):
        ApplicationLifecycleEvent(
            device_id=device_id,
            entity_urn=urn,
            event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
            bundle_id="",
            app_name="TestApp",
            bundle_path="/Applications/TestApp.app",
            version="1.0.0",
        )

    # Valid event round-trip
    event = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=urn,
        event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
        bundle_id="com.test.app",
        app_name="TestApp",
        bundle_path="/Applications/TestApp.app",
        version="1.2.3",
        previous_version=None,
        previous_path=None,
        ownership=ComponentOwnership.USER_MANAGED,
        detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
        code_signature={"team_id": "ABC12345", "authority": "Developer ID Application"},
        scan_proves_safe=False,
    )

    d = event.to_dict()
    assert d["bundle_id"] == "com.test.app"
    assert d["scan_proves_safe"] is False

    restored = ApplicationLifecycleEvent.from_dict(d)
    assert restored.event_id == event.event_id
    assert restored.bundle_path == "/Applications/TestApp.app"
    assert restored.code_signature["team_id"] == "ABC12345"


# --- Test 3: Inventory Diff Detection ---

def test_detect_from_inventory_diff_lifecycle():
    """Verifies detection of install, remove, upgrade, and path mutation across inventory diffs."""
    device_id = "00000000-0000-4000-8000-000000000002"

    t0_inventory = [
        {
            "bundle_id": "com.apple.Safari",
            "app_name": "Safari",
            "version": "17.0",
            "install_path": "/Applications/Safari.app",
            "ownership": ComponentOwnership.SYSTEM_MANAGED,
        },
        {
            "bundle_id": "com.apple.dt.Xcode",
            "app_name": "Xcode",
            "version": "15.0",
            "install_path": "/Applications/Xcode.app",
            "ownership": ComponentOwnership.USER_MANAGED,
        },
        {
            "bundle_id": "com.slack.Slack",
            "app_name": "Slack",
            "version": "4.35.0",
            "install_path": "/Applications/Slack.app",
            "ownership": ComponentOwnership.USER_MANAGED,
        },
    ]

    t1_inventory = [
        {
            "bundle_id": "com.apple.Safari",
            "app_name": "Safari",
            "version": "17.2",  # Upgraded
            "install_path": "/Applications/Safari.app",
            "ownership": ComponentOwnership.SYSTEM_MANAGED,
        },
        # Xcode removed
        {
            "bundle_id": "com.slack.Slack",
            "app_name": "Slack",
            "version": "4.35.0",
            "install_path": "/Users/developer/Applications/Slack.app",  # Path mutated
            "ownership": ComponentOwnership.USER_MANAGED,
        },
        {
            "bundle_id": "com.google.Chrome",  # Newly installed
            "app_name": "Google Chrome",
            "version": "120.0.6099.109",
            "install_path": "/Applications/Google Chrome.app",
            "ownership": ComponentOwnership.USER_MANAGED,
        },
    ]

    diff = ApplicationLifecycleTracker.detect_from_inventory_diff(
        previous_inventory=t0_inventory,
        current_inventory=t1_inventory,
        device_id=device_id,
    )

    assert len(diff.installed_apps) == 1
    assert diff.installed_apps[0].bundle_id == "com.google.Chrome"
    assert diff.installed_apps[0].event_type == ApplicationLifecycleEventType.APPLICATION_INSTALLED

    assert len(diff.removed_apps) == 1
    assert diff.removed_apps[0].bundle_id == "com.apple.dt.Xcode"
    assert diff.removed_apps[0].event_type == ApplicationLifecycleEventType.APPLICATION_REMOVED

    assert len(diff.upgraded_apps) == 1
    assert diff.upgraded_apps[0].bundle_id == "com.apple.Safari"
    assert diff.upgraded_apps[0].previous_version == "17.0"
    assert diff.upgraded_apps[0].version == "17.2"
    assert diff.upgraded_apps[0].event_type == ApplicationLifecycleEventType.APPLICATION_UPGRADED

    assert len(diff.path_mutated_apps) == 1
    assert diff.path_mutated_apps[0].bundle_id == "com.slack.Slack"
    assert diff.path_mutated_apps[0].previous_path == "/Applications/Slack.app"
    assert diff.path_mutated_apps[0].bundle_path == "/Users/developer/Applications/Slack.app"
    assert diff.path_mutated_apps[0].event_type == ApplicationLifecycleEventType.APPLICATION_PATH_MUTATED

    assert diff.unchanged_apps_count == 0
    assert diff.total_mutations == 4
    assert diff.scan_proves_safe is False


# --- Test 4: Filesystem Event Notification (FSEvents) Mapping ---

def test_detect_from_fsevents_mapping():
    """Verifies that filesystem events on .app paths map accurately to lifecycle events."""
    device_id = "00000000-0000-4000-8000-000000000003"
    known_apps = {
        "/Applications/Existing.app": {
            "bundle_id": "com.existing.app",
            "app_name": "Existing",
            "version": "1.0",
            "entity_urn": "urn:systemmind:app:com.existing.app",
            "ownership": ComponentOwnership.USER_MANAGED,
        }
    }

    fsevents = [
        # 1. New application bundle created
        {
            "path": "/Applications/NewApp.app",
            "flags": ["ItemCreated", "ItemIsDir"],
            "raw_flags": 0x00000100,
            "timestamp": "2026-11-18T14:00:00Z",
            "is_dir": True,
        },
        # 2. Existing application bundle removed
        {
            "path": "/Applications/Existing.app",
            "flags": ["ItemRemoved"],
            "raw_flags": 0x00000200,
            "timestamp": "2026-11-18T14:01:00Z",
            "is_dir": True,
        },
        # 3. Unrelated document file modified (must be ignored)
        {
            "path": "/Users/developer/Documents/notes.txt",
            "flags": ["ItemModified"],
            "raw_flags": 0x00001000,
            "timestamp": "2026-11-18T14:02:00Z",
            "is_dir": False,
        },
    ]

    events = ApplicationLifecycleTracker.detect_from_fsevents(
        fsevents=fsevents,
        known_apps_by_path=known_apps,
        device_id=device_id,
    )

    assert len(events) == 2
    types = [e.event_type for e in events]
    assert ApplicationLifecycleEventType.APPLICATION_INSTALLED in types
    assert ApplicationLifecycleEventType.APPLICATION_REMOVED in types

    installed = [e for e in events if e.event_type == ApplicationLifecycleEventType.APPLICATION_INSTALLED][0]
    assert installed.bundle_path == "/Applications/NewApp.app"
    assert installed.detection_source == ApplicationDetectionSource.FSEVENTS_NOTIFICATION

    removed = [e for e in events if e.event_type == ApplicationLifecycleEventType.APPLICATION_REMOVED][0]
    assert removed.bundle_path == "/Applications/Existing.app"
    assert removed.bundle_id == "com.existing.app"


# --- Test 5: In-Memory DigitalTwinGraph Synchronization ---

def test_in_memory_graph_synchronization():
    """Verifies that lifecycle events update entities and relationships in DigitalTwinGraph."""
    graph = DigitalTwinGraph()
    device_id = "00000000-0000-4000-8000-000000000004"
    host_urn = f"urn:systemmind:host:{device_id}"

    # Register host entity
    graph.add_entity(
        TwinEntity(
            entity_id=host_urn,
            entity_type=TwinEntityType.HOST,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            provenance_source="host_detector",
            is_stale=False,
        )
    )

    app_urn = create_entity_urn(EntityDomain.APPLICATION, "com.test.sync")

    # 1. Install application
    install_ev = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=app_urn,
        event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
        bundle_id="com.test.sync",
        app_name="SyncApp",
        bundle_path="/Applications/SyncApp.app",
        version="1.0.0",
        ownership=ComponentOwnership.USER_MANAGED,
        detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
    )
    ApplicationLifecycleTracker.apply_to_graph([install_ev], graph, host_urn=host_urn)

    assert app_urn in graph.entities
    entity = graph.get_entity(app_urn)
    assert entity is not None
    assert entity.is_stale is False
    assert entity.attributes["version"] == "1.0.0"

    # Verify HOST -> CONTAINS -> APPLICATION edge
    rels = graph.get_outgoing_relationships(host_urn, relation_type=TwinRelationType.CONTAINS)
    assert any(r.target_id == app_urn for r in rels)

    # 2. Upgrade application
    upgrade_ev = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=app_urn,
        event_type=ApplicationLifecycleEventType.APPLICATION_UPGRADED,
        bundle_id="com.test.sync",
        app_name="SyncApp",
        bundle_path="/Applications/SyncApp.app",
        version="1.1.0",
        previous_version="1.0.0",
        ownership=ComponentOwnership.USER_MANAGED,
        detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
    )
    ApplicationLifecycleTracker.apply_to_graph([upgrade_ev], graph, host_urn=host_urn)
    upgraded = graph.get_entity(app_urn)
    assert upgraded is not None
    assert upgraded.attributes["version"] == "1.1.0"
    assert len(upgraded.attributes["version_history"]) == 1
    assert upgraded.attributes["version_history"][0]["version"] == "1.0.0"

    # 3. Remove application
    remove_ev = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=app_urn,
        event_type=ApplicationLifecycleEventType.APPLICATION_REMOVED,
        bundle_id="com.test.sync",
        app_name="SyncApp",
        bundle_path="/Applications/SyncApp.app",
        version="1.1.0",
        ownership=ComponentOwnership.USER_MANAGED,
        detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
    )
    ApplicationLifecycleTracker.apply_to_graph([remove_ev], graph, host_urn=host_urn)
    removed = graph.get_entity(app_urn)
    assert removed is not None  # Not deleted!
    assert removed.is_stale is True
    assert removed.attributes["stale_reason"] == "APPLICATION_REMOVED"


# --- Test 6: Append-Only SystemEventStore Integration & Cryptographic Chaining ---

def test_append_only_event_store_integration(memory_db: sqlite3.Connection):
    """Verifies that lifecycle transitions bridge into SystemEventStore with SHA-256 hash chaining."""
    event_store = SystemEventStore(memory_db)
    device_id = "00000000-0000-4000-8000-000000000005"
    app_urn = create_entity_urn(EntityDomain.APPLICATION, "com.chain.app")

    events = [
        ApplicationLifecycleEvent(
            device_id=device_id,
            entity_urn=app_urn,
            event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
            bundle_id="com.chain.app",
            app_name="ChainApp",
            bundle_path="/Applications/ChainApp.app",
            version="1.0.0",
            ownership=ComponentOwnership.USER_MANAGED,
        ),
        ApplicationLifecycleEvent(
            device_id=device_id,
            entity_urn=app_urn,
            event_type=ApplicationLifecycleEventType.APPLICATION_UPGRADED,
            bundle_id="com.chain.app",
            app_name="ChainApp",
            bundle_path="/Applications/ChainApp.app",
            version="1.1.0",
            previous_version="1.0.0",
            ownership=ComponentOwnership.USER_MANAGED,
        ),
        ApplicationLifecycleEvent(
            device_id=device_id,
            entity_urn=app_urn,
            event_type=ApplicationLifecycleEventType.APPLICATION_REMOVED,
            bundle_id="com.chain.app",
            app_name="ChainApp",
            bundle_path="/Applications/ChainApp.app",
            version="1.1.0",
            ownership=ComponentOwnership.USER_MANAGED,
        ),
    ]

    stored = ApplicationLifecycleTracker.sync_with_event_store(events, event_store)
    assert len(stored) == 3

    # Check contiguous sequence progression
    assert stored[0].sequence_number == 1
    assert stored[1].sequence_number == 2
    assert stored[2].sequence_number == 3

    # Check cryptographic hash chaining
    assert stored[0].prev_event_hash == GENESIS_PREV_HASH
    assert stored[1].prev_event_hash == stored[0].event_hash
    assert stored[2].prev_event_hash == stored[1].event_hash

    # Verify immutability triggers on system_events table
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute("UPDATE system_events SET payload_json = '{}' WHERE sequence_number = 1")
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute("DELETE FROM system_events WHERE sequence_number = 1")


# --- Test 7: Point-in-Time Application State Reconstruction ---

def test_point_in_time_installed_application_reconstruction(memory_db: sqlite3.Connection):
    """Verifies that installed applications can be reconstructed at any historical point in time."""
    manager = ApplicationLifecycleManager(memory_db)
    device_id = "00000000-0000-4000-8000-000000000006"

    t0 = 1000
    t1 = 2000
    t2 = 3000

    # At T0: App A (v1) and App B (v1) installed
    ev_a0 = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=create_entity_urn(EntityDomain.APPLICATION, "com.app.a"),
        event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
        bundle_id="com.app.a",
        app_name="AppA",
        bundle_path="/Applications/AppA.app",
        version="1.0",
        observed_at_epoch_ms=t0,
    )
    ev_b0 = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=create_entity_urn(EntityDomain.APPLICATION, "com.app.b"),
        event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
        bundle_id="com.app.b",
        app_name="AppB",
        bundle_path="/Applications/AppB.app",
        version="1.0",
        observed_at_epoch_ms=t0,
    )
    manager.record_event(ev_a0)
    manager.record_event(ev_b0)

    # At T1: App A upgraded to v2, App C (v1) installed
    ev_a1 = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=create_entity_urn(EntityDomain.APPLICATION, "com.app.a"),
        event_type=ApplicationLifecycleEventType.APPLICATION_UPGRADED,
        bundle_id="com.app.a",
        app_name="AppA",
        bundle_path="/Applications/AppA.app",
        version="2.0",
        previous_version="1.0",
        observed_at_epoch_ms=t1,
    )
    ev_c1 = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=create_entity_urn(EntityDomain.APPLICATION, "com.app.c"),
        event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
        bundle_id="com.app.c",
        app_name="AppC",
        bundle_path="/Applications/AppC.app",
        version="1.0",
        observed_at_epoch_ms=t1,
    )
    manager.record_event(ev_a1)
    manager.record_event(ev_c1)

    # At T2: App B removed
    ev_b2 = ApplicationLifecycleEvent(
        device_id=device_id,
        entity_urn=create_entity_urn(EntityDomain.APPLICATION, "com.app.b"),
        event_type=ApplicationLifecycleEventType.APPLICATION_REMOVED,
        bundle_id="com.app.b",
        app_name="AppB",
        bundle_path="/Applications/AppB.app",
        version="1.0",
        observed_at_epoch_ms=t2,
    )
    manager.record_event(ev_b2)

    # Query at T0: expected App A (v1) and App B (v1)
    apps_at_t0 = manager.get_installed_applications_at(target_epoch_ms=t0, device_id=device_id)
    assert len(apps_at_t0) == 2
    map_t0 = {a.bundle_id: a.version for a in apps_at_t0}
    assert map_t0["com.app.a"] == "1.0"
    assert map_t0["com.app.b"] == "1.0"

    # Query at T1: expected App A (v2), App B (v1), App C (v1)
    apps_at_t1 = manager.get_installed_applications_at(target_epoch_ms=t1, device_id=device_id)
    assert len(apps_at_t1) == 3
    map_t1 = {a.bundle_id: a.version for a in apps_at_t1}
    assert map_t1["com.app.a"] == "2.0"
    assert map_t1["com.app.b"] == "1.0"
    assert map_t1["com.app.c"] == "1.0"

    # Query at T2: expected App A (v2), App C (v1) - App B excluded!
    apps_at_t2 = manager.get_installed_applications_at(target_epoch_ms=t2, device_id=device_id)
    assert len(apps_at_t2) == 2
    map_t2 = {a.bundle_id: a.version for a in apps_at_t2}
    assert "com.app.b" not in map_t2
    assert map_t2["com.app.a"] == "2.0"
    assert map_t2["com.app.c"] == "1.0"


# --- Test 8: Component Ownership Preservation (SC-02) ---

def test_component_ownership_preservation():
    """Verifies that application lifecycle tracking strictly preserves component ownership."""
    device_id = "00000000-0000-4000-8000-000000000007"
    inv = [
        {
            "bundle_id": "com.apple.finder",
            "app_name": "Finder",
            "version": "14.0",
            "install_path": "/System/Library/CoreServices/Finder.app",
            "ownership": ComponentOwnership.SYSTEM_MANAGED,
        },
        {
            "bundle_id": "com.microsoft.VSCode",
            "app_name": "Visual Studio Code",
            "version": "1.85.0",
            "install_path": "/Applications/Visual Studio Code.app",
            "ownership": ComponentOwnership.USER_MANAGED,
        },
    ]

    diff = ApplicationLifecycleTracker.detect_from_inventory_diff(
        previous_inventory=[],
        current_inventory=inv,
        device_id=device_id,
    )

    by_bundle = {e.bundle_id: e for e in diff.installed_apps}
    assert by_bundle["com.apple.finder"].ownership == ComponentOwnership.SYSTEM_MANAGED
    assert by_bundle["com.microsoft.VSCode"].ownership == ComponentOwnership.USER_MANAGED


# --- Test 9: AST Safety & Zero Ambient Shell Authority (SC-01) ---

def test_ast_safety_and_no_ambient_shell():
    """Verifies AST safety and strict absence of ambient shell execution in application lifecycle files."""
    audit_res = ApplicationLifecycleValidator.audit(REPO_ROOT)
    assert audit_res.ast_safety_valid is True
    assert audit_res.charter_invariants_valid is True
    assert audit_res.valid is True
    assert len(audit_res.issues) == 0
