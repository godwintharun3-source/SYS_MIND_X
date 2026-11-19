"""Packaging and safety invariant validator for Day 075 System-State Reconciliation After Collector Gaps."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class StateReconciliationAuditResult:
    """Outcome of auditing Day 075 state reconciliation components and invariants."""

    valid: bool
    issues: tuple[str, ...]
    reconciliation_engine_present: bool
    design_note_present: bool
    migration_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    functional_reconciliation_valid: bool
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces Charter Invariant SC-03: scan_proves_safe is NEVER True."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")


class StateReconciliationValidator:
    """Audits the completeness, safety, and packaging of Day 075 state reconciliation."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0010_collector_gaps_and_reconciliation.sql"),
        Path("src/system_mind/twin/reconciliation.py"),
        Path("docs/design/DAY_075_SYSTEM_STATE_RECONCILIATION_AFTER_GAPS.md"),
        Path("tools/detect_state_reconciliation.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> StateReconciliationAuditResult:
        """Executes comprehensive packaging audit across state reconciliation components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        migration_file = base / "src/system_mind/database/migrations/0010_collector_gaps_and_reconciliation.sql"
        reconciliation_file = base / "src/system_mind/twin/reconciliation.py"
        design_file = base / "docs/design/DAY_075_SYSTEM_STATE_RECONCILIATION_AFTER_GAPS.md"
        tool_file = base / "tools/detect_state_reconciliation.py"

        migration_present = migration_file.is_file()
        reconciliation_engine_present = reconciliation_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # Check migration file content
        if migration_present:
            content = migration_file.read_text(encoding="utf-8")
            if "-- UP" not in content or "-- DOWN" not in content:
                issues.append("Migration 0010 must contain both '-- UP' and '-- DOWN' markers.")
            if "collector_gaps" not in content:
                issues.append("Migration 0010 must create table collector_gaps.")
            if "state_reconciliation_records" not in content:
                issues.append("Migration 0010 must create table state_reconciliation_records.")
            if "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)" not in content:
                issues.append("Migration 0010 must enforce CHECK (scan_proves_safe = 0) on both tables.")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [reconciliation_file, tool_file]
        for pf in python_files:
            if pf.is_file():
                try:
                    tree = ast.parse(pf.read_text(encoding="utf-8"), filename=str(pf))
                    for node in ast.walk(tree):
                        # Detect os.system
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                    issues.append(f"AST Safety violation in {pf.name}: os.system invocation detected.")
                                    ast_safety_valid = False
                            # Detect subprocess with shell=True
                            if any(kw.arg == "shell" and getattr(kw.value, "value", None) is True for kw in node.keywords):
                                issues.append(f"AST Safety violation in {pf.name}: subprocess with shell=True detected.")
                                ast_safety_valid = False
                except Exception as e:
                    issues.append(f"AST parsing failed for {pf.name}: {e}")
                    ast_safety_valid = False

        # Charter Invariant Check (SC-03)
        charter_invariants_valid = True
        try:
            from system_mind.twin.reconciliation import CollectorGap, StateReconciliationRecord

            # Verify CollectorGap rejects scan_proves_safe=True
            try:
                CollectorGap(
                    gap_id="gap-fail-safe",
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
                issues.append("CollectorGap failed to reject scan_proves_safe=True.")
                charter_invariants_valid = False
            except ValueError:
                pass

            # Verify StateReconciliationRecord rejects scan_proves_safe=True
            try:
                StateReconciliationRecord(
                    reconciliation_id="recon-fail-safe",
                    gap_id="gap-1",
                    device_id="dev-test",
                    domain="proc",
                    reconciled_at_iso="2026-11-18T12:00:00Z",
                    reconciled_at_epoch_ms=2000,
                    entities_sustained_count=0,
                    entities_terminated_count=0,
                    entities_staled_count=0,
                    entities_spawned_count=0,
                    confidence_discount_pct=0.1,
                    actions=(),
                    scan_proves_safe=True,
                )
                issues.append("StateReconciliationRecord failed to reject scan_proves_safe=True.")
                charter_invariants_valid = False
            except ValueError:
                pass

        except Exception as e:
            issues.append(f"Charter invariant check failed: {e}")
            charter_invariants_valid = False

        # Functional Reconciliation Check
        functional_reconciliation_valid = True
        try:
            from system_mind.core.types import ComponentOwnership
            from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
            from system_mind.database.migrator import DatabaseMigrator
            from system_mind.twin.models import TwinEntity, TwinEntityType
            from system_mind.twin.reconciliation import (
                CollectorGapDetector,
                ReconciliationActionType,
                StateReconciliationManager,
                SystemStateReconciler,
            )

            db_cfg = DatabaseConfig(":memory:")
            conn = DatabaseConnectionManager.connect(db_cfg)
            migrator = DatabaseMigrator(config=db_cfg)
            migrator.apply_all(conn=conn)

            detector = CollectorGapDetector()
            # Detect 65-second gap on proc (expected cadence 5s)
            gap = detector.detect_gap(
                prev_epoch_ms=1700000000000,
                curr_epoch_ms=1700000065000,
                collector_id="mock_ps",
                device_id="dev-reconcile-test",
                domain="proc",
            )
            if not gap:
                issues.append("Failed functional check: gap not detected.")
                functional_reconciliation_valid = False
            elif gap.gap_classification != "SYSTEM_SLEEP_WAKE":
                issues.append(f"Failed functional check: expected SYSTEM_SLEEP_WAKE, got {gap.gap_classification}.")
                functional_reconciliation_valid = False
            else:
                # Setup pre-gap entities
                proc1 = TwinEntity(
                    entity_id="urn:systemmind:proc:100",
                    entity_type=TwinEntityType.PROCESS,
                    ownership=ComponentOwnership.USER_MANAGED,
                    attributes={"pid": 100, "name": "worker", "confidence_score": 1.0},
                    provenance_source="telemetry_collector",
                )
                proc2 = TwinEntity(
                    entity_id="urn:systemmind:proc:101",
                    entity_type=TwinEntityType.PROCESS,
                    ownership=ComponentOwnership.USER_MANAGED,
                    attributes={"pid": 101, "name": "transient_job", "confidence_score": 1.0},
                    provenance_source="telemetry_collector",
                )

                # Setup post-gap entities (proc1 sustained, proc2 absent/terminated, proc3 spawned)
                proc3 = TwinEntity(
                    entity_id="urn:systemmind:proc:102",
                    entity_type=TwinEntityType.PROCESS,
                    ownership=ComponentOwnership.USER_MANAGED,
                    attributes={"pid": 102, "name": "new_daemon", "confidence_score": 1.0},
                    provenance_source="telemetry_collector",
                )

                manager = StateReconciliationManager(conn)
                recon = manager.reconcile_and_record(
                    gap=gap,
                    pre_gap_entities=[proc1, proc2],
                    post_gap_entities=[proc1, proc3],
                )

                if recon.entities_sustained_count != 1:
                    issues.append(f"Failed functional check: expected 1 sustained, got {recon.entities_sustained_count}.")
                    functional_reconciliation_valid = False
                if recon.entities_terminated_count != 1:
                    issues.append(f"Failed functional check: expected 1 terminated, got {recon.entities_terminated_count}.")
                    functional_reconciliation_valid = False
                if recon.entities_spawned_count != 1:
                    issues.append(f"Failed functional check: expected 1 spawned, got {recon.entities_spawned_count}.")
                    functional_reconciliation_valid = False

                # Verify persistence in SQLite
                fetched_gap = manager.get_gap(gap.gap_id)
                if not fetched_gap:
                    issues.append("Failed functional check: gap not persisted.")
                    functional_reconciliation_valid = False

                fetched_recon = manager.get_reconciliation(recon.reconciliation_id)
                if not fetched_recon:
                    issues.append("Failed functional check: reconciliation record not persisted.")
                    functional_reconciliation_valid = False

            conn.close()

        except Exception as e:
            issues.append(f"Failed functional reconciliation check: {e}")
            functional_reconciliation_valid = False

        overall_valid = (
            migration_present
            and reconciliation_engine_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and functional_reconciliation_valid
            and len(issues) == 0
        )

        return StateReconciliationAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            reconciliation_engine_present=reconciliation_engine_present,
            design_note_present=design_note_present,
            migration_present=migration_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            functional_reconciliation_valid=functional_reconciliation_valid,
            scan_proves_safe=False,
        )
