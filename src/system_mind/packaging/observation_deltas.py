"""Packaging and safety invariant validator for Day 074 Consecutive Observation Change Detection."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class ObservationDeltasAuditResult:
    """Outcome of auditing Day 074 observation deltas components and invariants."""

    valid: bool
    issues: tuple[str, ...]
    change_detector_present: bool
    design_note_present: bool
    migration_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    functional_deltas_valid: bool
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces Charter Invariant SC-03: scan_proves_safe is NEVER True."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")


class ObservationDeltasValidator:
    """Audits the completeness, safety, and packaging of Day 074 observation deltas."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0009_observation_deltas.sql"),
        Path("src/system_mind/twin/change_detector.py"),
        Path("docs/design/DAY_074_CONSECUTIVE_OBSERVATION_CHANGE_DETECTION.md"),
        Path("tools/detect_observation_deltas.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> ObservationDeltasAuditResult:
        """Executes comprehensive packaging audit across observation deltas components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        migration_file = base / "src/system_mind/database/migrations/0009_observation_deltas.sql"
        detector_file = base / "src/system_mind/twin/change_detector.py"
        design_file = base / "docs/design/DAY_074_CONSECUTIVE_OBSERVATION_CHANGE_DETECTION.md"
        tool_file = base / "tools/detect_observation_deltas.py"

        migration_present = migration_file.is_file()
        change_detector_present = detector_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # Check migration file content
        if migration_present:
            content = migration_file.read_text(encoding="utf-8")
            if "-- UP" not in content or "-- DOWN" not in content:
                issues.append("Migration 0009 must contain both '-- UP' and '-- DOWN' markers.")
            if "observation_deltas" not in content:
                issues.append("Migration 0009 must create table observation_deltas.")
            if "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)" not in content:
                issues.append("Migration 0009 must enforce CHECK (scan_proves_safe = 0).")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [detector_file, tool_file]
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
            from system_mind.twin.change_detector import ObservationDelta

            delta = ObservationDelta(
                delta_id="delta-test-01",
                entity_urn="urn:systemmind:proc:100",
                device_id="dev-test-1",
                from_record_id="rec-1",
                to_record_id="rec-2",
                from_sequence=1,
                to_sequence=2,
                from_epoch_ms=1000,
                to_epoch_ms=2000,
                time_delta_ms=1000,
                has_changed=False,
                change_classification="NO_CHANGE",
                added_keys=(),
                removed_keys=(),
                modified_keys={},
                change_count=0,
                detected_at_iso="2026-11-18T12:00:00Z",
                scan_proves_safe=False,
            )
            if delta.scan_proves_safe is not False:
                issues.append("ObservationDelta violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                ObservationDelta(
                    delta_id="delta-test-fail",
                    entity_urn="urn:systemmind:proc:100",
                    device_id="dev-test-1",
                    from_record_id="rec-1",
                    to_record_id="rec-2",
                    from_sequence=1,
                    to_sequence=2,
                    from_epoch_ms=1000,
                    to_epoch_ms=2000,
                    time_delta_ms=1000,
                    has_changed=False,
                    change_classification="NO_CHANGE",
                    added_keys=(),
                    removed_keys=(),
                    modified_keys={},
                    change_count=0,
                    detected_at_iso="2026-11-18T12:00:00Z",
                    scan_proves_safe=True,  # VIOLATION
                )
                issues.append("ObservationDelta failed to reject scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correctly rejected
        except Exception as e:
            issues.append(f"Failed charter invariants check: {e}")
            charter_invariants_valid = False

        # Functional change detection test using in-memory database
        functional_deltas_valid = True
        try:
            from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
            from system_mind.database.migrator import DatabaseMigrator
            from system_mind.twin.change_detector import (
                ChangeClassification,
                ObservationChangeDetector,
                ObservationDeltaManager,
            )
            from system_mind.twin.observation_records import (
                ObservationRecordManager,
                SystemObservationRecord,
            )

            db_cfg = DatabaseConfig(":memory:")
            conn = DatabaseConnectionManager.connect(db_cfg)
            migrator = DatabaseMigrator(config=db_cfg)
            migrator.apply_all(conn=conn)

            obs_mgr = ObservationRecordManager(conn)
            delta_mgr = ObservationDeltaManager(conn)

            dev_id = "test-device-uuid"
            urn = "urn:systemmind:proc:555"

            # Observation 1
            rec1 = SystemObservationRecord(
                record_id="rec-01",
                device_id=dev_id,
                entity_urn=urn,
                collector_id="mock_ps",
                observation_type="STATE_SNAPSHOT",
                observed_at_iso="2026-11-18T12:00:00Z",
                observed_at_epoch_ms=1700000000000,
                sequence_number=1,
                payload={"pid": 555, "cpu_pct": 5.0, "status": "running"},
            )
            obs_mgr.record_observation(rec1)

            # Observation 2 (cpu_pct jumps to 25.0 -> threshold breach >= 10.0)
            rec2 = SystemObservationRecord(
                record_id="rec-02",
                device_id=dev_id,
                entity_urn=urn,
                collector_id="mock_ps",
                observation_type="STATE_SNAPSHOT",
                observed_at_iso="2026-11-18T12:00:05Z",
                observed_at_epoch_ms=1700000005000,
                sequence_number=2,
                payload={"pid": 555, "cpu_pct": 25.0, "status": "running"},
            )
            obs_mgr.record_observation(rec2)

            # Compute and record delta
            delta1 = delta_mgr.detect_and_record(rec1, rec2)
            if not delta1.has_changed:
                issues.append("Functional test failed: Delta 1 should report has_changed=True")
                functional_deltas_valid = False
            if delta1.change_classification != ChangeClassification.SIGNIFICANT_THRESHOLD_BREACH.value:
                issues.append(
                    f"Functional test failed: Expected SIGNIFICANT_THRESHOLD_BREACH, got '{delta1.change_classification}'"
                )
                functional_deltas_valid = False

            # Observation 3 (identical payload to observation 2)
            rec3 = SystemObservationRecord(
                record_id="rec-03",
                device_id=dev_id,
                entity_urn=urn,
                collector_id="mock_ps",
                observation_type="STATE_SNAPSHOT",
                observed_at_iso="2026-11-18T12:00:10Z",
                observed_at_epoch_ms=1700000010000,
                sequence_number=3,
                payload={"pid": 555, "cpu_pct": 25.0, "status": "running"},
            )
            obs_mgr.record_observation(rec3)

            delta2 = delta_mgr.detect_and_record(rec2, rec3)
            if delta2.has_changed:
                issues.append("Functional test failed: Delta 2 should report has_changed=False (identical)")
                functional_deltas_valid = False
            if delta2.change_classification != ChangeClassification.NO_CHANGE.value:
                issues.append(f"Functional test failed: Expected NO_CHANGE, got '{delta2.change_classification}'")
                functional_deltas_valid = False

            conn.close()
        except Exception as e:
            issues.append(f"Failed functional deltas check: {e}")
            functional_deltas_valid = False

        overall_valid = (
            len(issues) == 0
            and migration_present
            and change_detector_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and functional_deltas_valid
        )

        return ObservationDeltasAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            change_detector_present=change_detector_present,
            design_note_present=design_note_present,
            migration_present=migration_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            functional_deltas_valid=functional_deltas_valid,
            scan_proves_safe=False,
        )
