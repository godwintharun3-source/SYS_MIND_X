"""Packaging and safety invariant validator for Day 073 State Snapshots and Snapshot Comparison."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class DigitalTwinSnapshotsAuditResult:
    """Outcome of auditing Day 073 state snapshots components and invariants."""

    valid: bool
    issues: tuple[str, ...]
    snapshots_engine_present: bool
    design_note_present: bool
    migration_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    functional_snapshots_valid: bool
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces Charter Invariant SC-03: scan_proves_safe is NEVER True."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")


class DigitalTwinSnapshotsValidator:
    """Audits the completeness, safety, and packaging of Day 073 state snapshots."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0008_digital_twin_state_snapshots.sql"),
        Path("src/system_mind/twin/snapshots.py"),
        Path("docs/design/DAY_073_STATE_SNAPSHOTS_AND_COMPARISON.md"),
        Path("tools/detect_state_snapshots.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> DigitalTwinSnapshotsAuditResult:
        """Executes comprehensive packaging audit across state snapshots components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        migration_file = base / "src/system_mind/database/migrations/0008_digital_twin_state_snapshots.sql"
        snapshots_file = base / "src/system_mind/twin/snapshots.py"
        design_file = base / "docs/design/DAY_073_STATE_SNAPSHOTS_AND_COMPARISON.md"
        tool_file = base / "tools/detect_state_snapshots.py"

        migration_present = migration_file.is_file()
        snapshots_engine_present = snapshots_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # Check migration file content
        if migration_present:
            content = migration_file.read_text(encoding="utf-8")
            if "-- UP" not in content or "-- DOWN" not in content:
                issues.append("Migration 0008 must contain both '-- UP' and '-- DOWN' markers.")
            if "digital_twin_snapshots" not in content:
                issues.append("Migration 0008 must create table digital_twin_snapshots.")
            if "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)" not in content:
                issues.append("Migration 0008 must enforce CHECK (scan_proves_safe = 0).")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [snapshots_file, tool_file]
        for pf in python_files:
            if pf.is_file():
                try:
                    tree = ast.parse(pf.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Attribute):
                                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                    if node.func.attr in ("system", "popen"):
                                        issues.append(f"Forbidden call to os.{node.func.attr} in {pf.name}")
                                        ast_safety_valid = False
                            for kw in node.keywords:
                                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                    issues.append(f"Forbidden shell=True in {pf.name}")
                                    ast_safety_valid = False
                except Exception as e:
                    issues.append(f"Failed to parse AST of {pf.name}: {e}")
                    ast_safety_valid = False

        # Invariant checks on runtime models (SC-03: scan_proves_safe = False)
        charter_invariants_valid = True
        try:
            from system_mind.twin.snapshots import DigitalTwinSnapshot, DigitalTwinSnapshotDiff

            snap = DigitalTwinSnapshot(
                snapshot_id="snap-test-01",
                device_id="dev-test-1",
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
            if snap.scan_proves_safe is not False:
                issues.append("DigitalTwinSnapshot violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                DigitalTwinSnapshot(
                    snapshot_id="snap-test-fail",
                    device_id="dev-test-1",
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
                issues.append("DigitalTwinSnapshot failed to reject scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correctly rejected
        except Exception as e:
            issues.append(f"Failed charter invariants check: {e}")
            charter_invariants_valid = False

        # Functional state snapshot capture, diffing, and reconstruction test
        functional_snapshots_valid = True
        try:
            from system_mind.core.types import ComponentOwnership
            from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
            from system_mind.database.migrator import DatabaseMigrator
            from system_mind.twin.graph import DigitalTwinGraph
            from system_mind.twin.models import (
                TwinEntity,
                TwinEntityType,
                TwinRelationship,
                TwinRelationType,
            )
            from system_mind.twin.snapshots import DigitalTwinSnapshotManager

            db_cfg = DatabaseConfig(":memory:")
            conn = DatabaseConnectionManager.connect(db_cfg)
            migrator = DatabaseMigrator(config=db_cfg)
            migrator.apply_all(conn=conn)

            mgr = DigitalTwinSnapshotManager(conn)
            dev_id = "test-device-uuid"

            # 1. Build initial graph
            graph1 = DigitalTwinGraph()
            e1 = TwinEntity(
                entity_id="urn:systemmind:host:mach-1",
                entity_type=TwinEntityType.HOST,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                created_at="2026-11-18T12:00:00Z",
                updated_at="2026-11-18T12:00:00Z",
                provenance_source="telemetry_collector",
            )
            e2 = TwinEntity(
                entity_id="urn:systemmind:proc:100",
                entity_type=TwinEntityType.PROCESS,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                attributes={"pid": 100, "name": "launchd"},
                created_at="2026-11-18T12:00:00Z",
                updated_at="2026-11-18T12:00:00Z",
                provenance_source="telemetry_collector",
            )
            graph1.add_entity(e1)
            graph1.add_entity(e2)
            rel1 = TwinRelationship(
                relation_id="rel:host:proc:100",
                source_id="urn:systemmind:host:mach-1",
                target_id="urn:systemmind:proc:100",
                relation_type=TwinRelationType.CONTAINS,
                observed_at="2026-11-18T12:00:00Z",
            )
            graph1.add_relationship(rel1)

            # Capture Snapshot 1
            snap1 = mgr.capture_snapshot(
                graph=graph1,
                device_id=dev_id,
                trigger_reason="TELEMETRY_SWEEP",
                captured_at_epoch_ms=1700000000000,
            )
            if snap1.entity_count != 2 or snap1.relationship_count != 1:
                issues.append("Functional test failed: Snapshot 1 entity or relationship count mismatch")
                functional_snapshots_valid = False

            # 2. Modify graph: add a user application process
            graph2 = DigitalTwinGraph()
            graph2.add_entity(e1)
            e3 = TwinEntity(
                entity_id="urn:systemmind:proc:200",
                entity_type=TwinEntityType.PROCESS,
                ownership=ComponentOwnership.USER_MANAGED,
                attributes={"pid": 200, "name": "custom_app"},
                created_at="2026-11-18T12:01:00Z",
                updated_at="2026-11-18T12:01:00Z",
                provenance_source="telemetry_collector",
            )
            graph2.add_entity(e3)
            rel2 = TwinRelationship(
                relation_id="rel:host:proc:200",
                source_id="urn:systemmind:host:mach-1",
                target_id="urn:systemmind:proc:200",
                relation_type=TwinRelationType.CONTAINS,
                observed_at="2026-11-18T12:01:00Z",
            )
            graph2.add_relationship(rel2)

            # Capture Snapshot 2
            snap2 = mgr.capture_snapshot(
                graph=graph2,
                device_id=dev_id,
                trigger_reason="POST_MUTATION",
                captured_at_epoch_ms=1700000060000,
            )

            # 3. Compare Snapshots
            diff = mgr.compare_snapshots_by_id(snap1.snapshot_id, snap2.snapshot_id)
            if len(diff.added_entities) != 1 or diff.added_entities[0].entity_id != "urn:systemmind:proc:200":
                issues.append("Functional test failed: Diff did not report added entity proc:200")
                functional_snapshots_valid = False

            if len(diff.removed_entities) != 1 or diff.removed_entities[0].entity_id != "urn:systemmind:proc:100":
                issues.append("Functional test failed: Diff did not report removed entity proc:100")
                functional_snapshots_valid = False

            if not diff.user_managed_affected:
                issues.append("Functional test failed: Diff failed to flag user_managed_affected=True")
                functional_snapshots_valid = False

            # 4. Reconstruct graph from Snapshot 1
            reconstructed = mgr.reconstruct_graph(snap1.snapshot_id)
            if reconstructed.entity_count != 2 or reconstructed.relationship_count != 1:
                issues.append("Functional test failed: Reconstructed graph counts do not match original")
                functional_snapshots_valid = False

            conn.close()
        except Exception as e:
            issues.append(f"Failed functional snapshots check: {e}")
            functional_snapshots_valid = False

        overall_valid = (
            len(issues) == 0
            and migration_present
            and snapshots_engine_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and functional_snapshots_valid
        )

        return DigitalTwinSnapshotsAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            snapshots_engine_present=snapshots_engine_present,
            design_note_present=design_note_present,
            migration_present=migration_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            functional_snapshots_valid=functional_snapshots_valid,
            scan_proves_safe=False,
        )
