"""Packaging and safety invariant validator for Day 069 Timestamped System Observation Records."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class SystemObservationsAuditResult:
    """Outcome of auditing Day 069 system observation records, schema, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    migration_present: bool
    models_present: bool
    design_note_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    schema_constraints_valid: bool
    reconstruction_valid: bool


class SystemObservationsValidator:
    """Audits the completeness, safety, and packaging of Day 069 system observation records."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0005_system_observation_records.sql"),
        Path("src/system_mind/twin/observation_records.py"),
        Path("docs/design/DAY_069_TIMESTAMPED_SYSTEM_OBSERVATION_RECORDS.md"),
        Path("tools/detect_system_observations.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> SystemObservationsAuditResult:
        """Executes comprehensive packaging audit across digital twin observation persistence components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        mig_file = base / "src/system_mind/database/migrations/0005_system_observation_records.sql"
        models_file = base / "src/system_mind/twin/observation_records.py"
        design_file = base / "docs/design/DAY_069_TIMESTAMPED_SYSTEM_OBSERVATION_RECORDS.md"
        tool_file = base / "tools/detect_system_observations.py"

        migration_present = mig_file.is_file()
        models_present = models_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [models_file, tool_file]
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
                except Exception as ex:
                    issues.append(f"AST parsing failed for {pf.name}: {ex}")
                    ast_safety_valid = False

        # Schema & Constraint Verification
        schema_constraints_valid = True
        if migration_present:
            mig_content = mig_file.read_text(encoding="utf-8")
            required_phrases = [
                "CREATE TABLE IF NOT EXISTS system_observation_records",
                "record_id TEXT PRIMARY KEY",
                "entity_urn TEXT NOT NULL",
                "observed_at_iso TEXT NOT NULL",
                "observed_at_epoch_ms INTEGER NOT NULL",
                "confidence_score REAL NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)",
                "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)",
                "idx_obs_records_entity_seq",
                "idx_obs_records_observed_at",
                "idx_obs_records_epoch_ms",
                "-- DOWN",
                "DROP TABLE IF EXISTS system_observation_records;",
            ]
            for phrase in required_phrases:
                if phrase not in mig_content:
                    issues.append(f"Migration 0005 missing expected DDL phrase: '{phrase}'")
                    schema_constraints_valid = False

        # Charter Invariant and Python Validation
        charter_invariants_valid = True
        reconstruction_valid = True
        if models_present and migration_present:
            try:
                from system_mind.database.migrator import DatabaseMigrator
                from system_mind.twin.observation_records import (
                    ObservationRecordManager,
                    SystemObservationRecord,
                )

                migrator = DatabaseMigrator(db_path=":memory:")
                conn = migrator._get_connection()
                migrator.apply_all(conn=conn)

                manager = ObservationRecordManager(conn)

                # 1. Charter Invariant SC-03: scan_proves_safe = True must be rejected
                try:
                    SystemObservationRecord(
                        record_id="obs-invalid",
                        device_id="test-device",
                        entity_urn="urn:systemmind:host:test",
                        collector_id="test_collector",
                        observation_type="STATE_SNAPSHOT",
                        observed_at_iso="2026-11-18T11:00:00+00:00",
                        observed_at_epoch_ms=1763463600000,
                        scan_proves_safe=True,  # Prohibited
                    )
                    issues.append("SystemObservationRecord accepted scan_proves_safe=True (Charter SC-03 violation)")
                    charter_invariants_valid = False
                except ValueError:
                    pass  # Correctly rejected

                # 2. Database CHECK constraint rejection for scan_proves_safe = 1
                try:
                    conn.execute(
                        """
                        INSERT INTO system_observation_records (
                            record_id, device_id, entity_urn, collector_id, observation_type,
                            observed_at_iso, observed_at_epoch_ms, confidence_score,
                            confidence_tier, provenance_status, sequence_number,
                            payload_sha256, payload_json, scan_proves_safe
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
                        """,
                        (
                            "obs-bad", "test-dev", "urn:systemmind:host:test", "test",
                            "STATE_SNAPSHOT", "2026-11-18T11:00:00+00:00", 1763463600000,
                            1.0, "KERNEL_AUTHORITATIVE", "VERIFIED_KERNEL", 1,
                            "digest", "{}",
                        ),
                    )
                    issues.append("SQLite accepted INSERT with scan_proves_safe=1 (SC-03 constraint violation)")
                    charter_invariants_valid = False
                except sqlite3.IntegrityError:
                    pass  # Correctly rejected by CHECK constraint

                # 3. Confidence score bounding rejection [0.0, 1.0]
                try:
                    SystemObservationRecord(
                        record_id="obs-invalid-conf",
                        device_id="test-device",
                        entity_urn="urn:systemmind:host:test",
                        collector_id="test_collector",
                        observation_type="STATE_SNAPSHOT",
                        observed_at_iso="2026-11-18T11:00:00+00:00",
                        observed_at_epoch_ms=1763463600000,
                        confidence_score=1.5,  # Out of bounds
                    )
                    issues.append("SystemObservationRecord accepted confidence_score > 1.0")
                    charter_invariants_valid = False
                except ValueError:
                    pass

                # 4. State Reconstruction verification
                r1 = ObservationRecordManager.create_record(
                    device_id="dev-audit-1",
                    entity_urn="urn:systemmind:proc:audit:1",
                    collector_id="test_collector",
                    observation_type="STATE_SNAPSHOT",
                    payload={"status": "running", "cpu_percent": 1.5, "rss_bytes": 102400},
                    observed_at_epoch_ms=1000,
                    sequence_number=1,
                )
                r2 = ObservationRecordManager.create_record(
                    device_id="dev-audit-1",
                    entity_urn="urn:systemmind:proc:audit:1",
                    collector_id="test_collector",
                    observation_type="ATTRIBUTE_DELTA",
                    payload={"cpu_percent": 4.2},
                    observed_at_epoch_ms=2000,
                    sequence_number=2,
                )
                manager.record_observation(r1)
                manager.record_observation(r2)

                state_at_1500 = manager.reconstruct_state_at("urn:systemmind:proc:audit:1", 1500)
                state_at_2500 = manager.reconstruct_state_at("urn:systemmind:proc:audit:1", 2500)

                if state_at_1500.get("cpu_percent") != 1.5:
                    issues.append("Historical state reconstruction at epoch 1500 failed")
                    reconstruction_valid = False
                if state_at_2500.get("cpu_percent") != 4.2:
                    issues.append("Historical state reconstruction at epoch 2500 failed")
                    reconstruction_valid = False

                conn.close()

            except Exception as ex:
                issues.append(f"Charter invariant / reconstruction validation exception: {ex}")
                charter_invariants_valid = False
                reconstruction_valid = False

        overall_valid = (
            len(issues) == 0
            and migration_present
            and models_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and schema_constraints_valid
            and reconstruction_valid
        )

        return SystemObservationsAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            migration_present=migration_present,
            models_present=models_present,
            design_note_present=design_note_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            schema_constraints_valid=schema_constraints_valid,
            reconstruction_valid=reconstruction_valid,
        )
