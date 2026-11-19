#!/usr/bin/env python3
"""Developer CLI tool to detect application installation and removal events, audit invariants, and simulate lifecycle transitions."""

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
from system_mind.twin.event_store import SystemEventStore
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import TwinEntity, TwinEntityType
from system_mind.twin.identity import (
    EntityDomain,
    create_entity_urn,
)


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Applies all SQLite schema migrations from 0001 to 0011 in memory."""
    migrations_dir = REPO_ROOT / "src/system_mind/database/migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))
    for mf in migration_files:
        content = mf.read_text(encoding="utf-8")
        up_script = content.split("-- DOWN")[0].replace("-- UP", "")
        conn.executescript(up_script)


def run_audit() -> int:
    """Runs packaging, AST safety, and invariant audit for Day 076."""
    print("[*] SYSTEM MIND X — Application Lifecycle Tracking Invariant Audit")
    print(f"[*] Monorepo root: {REPO_ROOT}")
    print("-" * 65)

    result = ApplicationLifecycleValidator.audit(REPO_ROOT)
    print(f"[*] app_lifecycle_present:    {'PASSED' if result.app_lifecycle_present else 'FAILED'}")
    print(f"[*] design_note_present:      {'PASSED' if result.design_note_present else 'FAILED'}")
    print(f"[*] migration_present:        {'PASSED' if result.migration_present else 'FAILED'}")
    print(f"[*] tool_present:             {'PASSED' if result.tool_present else 'FAILED'}")
    print(f"[*] ast_safety_valid:         {'PASSED' if result.ast_safety_valid else 'FAILED'}")
    print(f"[*] charter_invariants_valid: {'PASSED' if result.charter_invariants_valid else 'FAILED'}")
    print(f"[*] functional_valid:         {'PASSED' if result.functional_lifecycle_valid else 'FAILED'}")
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
    """Simulates multi-channel application lifecycle tracking (inventory diff + FSEvents)."""
    print("[*] SYSTEM MIND X — Application Installation & Removal Tracking Simulation")
    print("-" * 65)

    device_id = "00000000-0000-4000-8000-000000000076"
    host_urn = f"urn:systemmind:host:{device_id}"

    # 1. Initialize in-memory SQLite database with migrations 0001..0011
    print("[1] Initializing in-memory SQLite database and applying migrations 0001..0011...")
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)

    manager = ApplicationLifecycleManager(conn)
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

    # 2. Previous inventory state (T0)
    print("\n[2] Establishing initial application inventory state (T0: 3 applications)...")
    prev_inventory = [
        {
            "bundle_id": "com.apple.Safari",
            "app_name": "Safari",
            "version": "17.0",
            "install_path": "/Applications/Safari.app",
            "ownership": ComponentOwnership.SYSTEM_MANAGED,
            "code_signature": {"authority": "Apple Root CA", "team_id": "APPLE"},
        },
        {
            "bundle_id": "com.apple.dt.Xcode",
            "app_name": "Xcode",
            "version": "15.2",
            "install_path": "/Applications/Xcode.app",
            "ownership": ComponentOwnership.USER_MANAGED,
            "code_signature": {"authority": "Apple Mac OS Application Signing", "team_id": "APPLE"},
        },
        {
            "bundle_id": "com.tinyspeck.slackmacgap",
            "app_name": "Slack",
            "version": "4.36.0",
            "install_path": "/Applications/Slack.app",
            "ownership": ComponentOwnership.USER_MANAGED,
            "code_signature": {"authority": "Developer ID Application", "team_id": "BQR82RBBHL"},
        },
    ]

    for app in prev_inventory:
        print(f"    - {app['app_name']} v{app['version']} ({app['bundle_id']}) at {app['install_path']}")

    # 3. Current inventory state (T1): Safari upgraded, Xcode removed, Slack moved, Spotify installed
    print("\n[3] Evaluating current application inventory state (T1: 4 mutations)...")
    curr_inventory = [
        {
            "bundle_id": "com.apple.Safari",
            "app_name": "Safari",
            "version": "17.2",  # UPGRADED
            "install_path": "/Applications/Safari.app",
            "ownership": ComponentOwnership.SYSTEM_MANAGED,
            "code_signature": {"authority": "Apple Root CA", "team_id": "APPLE"},
        },
        # Xcode removed (absent from curr_inventory)
        {
            "bundle_id": "com.tinyspeck.slackmacgap",
            "app_name": "Slack",
            "version": "4.36.0",
            "install_path": "/Users/developer/Applications/Slack.app",  # PATH MUTATED
            "ownership": ComponentOwnership.USER_MANAGED,
            "code_signature": {"authority": "Developer ID Application", "team_id": "BQR82RBBHL"},
        },
        {
            "bundle_id": "com.spotify.client",  # INSTALLED
            "app_name": "Spotify",
            "version": "1.2.31",
            "install_path": "/Applications/Spotify.app",
            "ownership": ComponentOwnership.USER_MANAGED,
            "code_signature": {"authority": "Developer ID Application", "team_id": "2BD8M834FU"},
        },
    ]

    # 4. Compute ApplicationLifecycleDiff
    diff = ApplicationLifecycleTracker.detect_from_inventory_diff(
        previous_inventory=prev_inventory,
        current_inventory=curr_inventory,
        device_id=device_id,
    )

    print("\n[4] Differential Transition Results:")
    print(f"    - Newly Installed Applications: {len(diff.installed_apps)}")
    for ev in diff.installed_apps:
        print(f"      [+] {ev.app_name} v{ev.version} ({ev.bundle_id}) at {ev.bundle_path}")

    print(f"    - Removed Applications:          {len(diff.removed_apps)}")
    for ev in diff.removed_apps:
        print(f"      [-] {ev.app_name} v{ev.version} ({ev.bundle_id}) previously at {ev.bundle_path}")

    print(f"    - Upgraded Applications:         {len(diff.upgraded_apps)}")
    for ev in diff.upgraded_apps:
        print(f"      [^] {ev.app_name} upgraded: v{ev.previous_version} -> v{ev.version}")

    print(f"    - Path Mutated Applications:     {len(diff.path_mutated_apps)}")
    for ev in diff.path_mutated_apps:
        print(f"      [~] {ev.app_name} moved: {ev.previous_path} -> {ev.bundle_path}")

    # 5. Persist to relational manager
    print("\n[5] Persisting lifecycle transitions to SQLite table 'application_lifecycle_events'...")
    manager.record_diff(diff)
    recent = manager.get_recent_events(limit=10)
    print(f"    [+] Persisted {len(recent)} lifecycle records in database.")

    # 6. Apply to in-memory DigitalTwinGraph
    print("\n[6] Applying lifecycle transitions to in-memory DigitalTwinGraph...")
    # First seed previous entities
    for prev_app in prev_inventory:
        p_d = ApplicationLifecycleTracker._extract_app_dict(prev_app)
        graph.add_entity(
            TwinEntity(
                entity_id=p_d["entity_urn"],
                entity_type=TwinEntityType.APPLICATION,
                ownership=p_d["ownership"],
                attributes={
                    "bundle_id": p_d["bundle_id"],
                    "app_name": p_d["app_name"],
                    "install_path": p_d["install_path"],
                    "version": p_d["version"],
                },
                provenance_source="inventory_seed",
                is_stale=False,
            )
        )

    all_events = diff.installed_apps + diff.removed_apps + diff.upgraded_apps + diff.path_mutated_apps
    ApplicationLifecycleTracker.apply_to_graph(all_events, graph, host_urn=host_urn)

    spotify_urn = diff.installed_apps[0].entity_urn
    xcode_urn = diff.removed_apps[0].entity_urn
    safari_urn = diff.upgraded_apps[0].entity_urn

    print(f"    - Spotify in graph:  {spotify_urn in graph.entities} (is_stale={graph.entities.get(spotify_urn).is_stale if spotify_urn in graph.entities else None})")
    print(f"    - Xcode in graph:    {xcode_urn in graph.entities} (is_stale={graph.entities.get(xcode_urn).is_stale if xcode_urn in graph.entities else None})")
    print(f"    - Safari in graph:   version={graph.entities.get(safari_urn).attributes.get('version') if safari_urn in graph.entities else None}")

    # 7. Bridge to Append-Only SystemEventStore with SHA-256 hash chaining
    print("\n[7] Bridging lifecycle transitions to append-only SystemEventStore with SHA-256 hash chaining...")
    stored_events = ApplicationLifecycleTracker.sync_with_event_store(all_events, event_store)
    print(f"    [+] Appended {len(stored_events)} events to immutable cryptographic ledger.")
    for se in stored_events:
        print(f"      Seq #{se.sequence_number} | {se.event_type} | hash: {se.event_hash[:16]}... | prev: {se.prev_event_hash[:16]}...")

    # 8. Point-in-time state reconstruction
    print("\n[8] Reconstructing installed application state at current time...")
    installed_now = manager.get_installed_applications_at(
        target_epoch_ms=int(datetime.now(timezone.utc).timestamp() * 1000) + 1000,
        device_id=device_id,
    )
    print(f"    [+] Reconstructed {len(installed_now)} installed applications:")
    for app in installed_now:
        print(f"        * {app.app_name} v{app.version} ({app.bundle_id}) at {app.install_path}")

    print("\n[+] Application lifecycle tracking simulation completed successfully.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Day 076 Application Installation & Removal Tracking CLI"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run Day 076 packaging, AST safety, and invariant audit.",
    )
    args = parser.parse_args()

    if args.audit:
        return run_audit()
    return run_simulation()


if __name__ == "__main__":
    sys.exit(main())
