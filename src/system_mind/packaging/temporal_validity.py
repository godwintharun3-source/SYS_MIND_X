"""Packaging and safety invariant validator for Day 072 Temporal Validity and Stale Markers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class TemporalValidityAuditResult:
    """Outcome of auditing Day 072 temporal validity components and invariants."""

    valid: bool
    issues: tuple[str, ...]
    validity_engine_present: bool
    design_note_present: bool
    migration_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    functional_validity_valid: bool
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces Charter Invariant SC-03: scan_proves_safe is NEVER True."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")


class TemporalValidityValidator:
    """Audits the completeness, safety, and packaging of Day 072 temporal validity."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0007_temporal_validity_and_stale_markers.sql"),
        Path("src/system_mind/twin/validity.py"),
        Path("docs/design/DAY_072_TEMPORAL_VALIDITY_AND_STALE_MARKERS.md"),
        Path("tools/detect_temporal_validity.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> TemporalValidityAuditResult:
        """Executes comprehensive packaging audit across temporal validity components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        migration_file = base / "src/system_mind/database/migrations/0007_temporal_validity_and_stale_markers.sql"
        validity_file = base / "src/system_mind/twin/validity.py"
        design_file = base / "docs/design/DAY_072_TEMPORAL_VALIDITY_AND_STALE_MARKERS.md"
        tool_file = base / "tools/detect_temporal_validity.py"

        migration_present = migration_file.is_file()
        validity_engine_present = validity_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # Check migration file content
        if migration_present:
            content = migration_file.read_text(encoding="utf-8")
            if "-- UP" not in content or "-- DOWN" not in content:
                issues.append("Migration 0007 must contain both '-- UP' and '-- DOWN' markers.")
            if "entity_temporal_validity" not in content:
                issues.append("Migration 0007 must create table entity_temporal_validity.")
            if "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)" not in content:
                issues.append("Migration 0007 must enforce CHECK (scan_proves_safe = 0).")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [validity_file, tool_file]
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
            from system_mind.twin.validity import EntityTemporalValidity

            valid_record = EntityTemporalValidity(
                entity_urn="urn:systemmind:proc:1001",
                device_id="d1111111-2222-3333-4444-555555555555",
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
            if valid_record.scan_proves_safe is not False:
                issues.append("EntityTemporalValidity violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                EntityTemporalValidity(
                    entity_urn="urn:systemmind:proc:1001",
                    device_id="d1111111-2222-3333-4444-555555555555",
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
                issues.append("EntityTemporalValidity failed to reject scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correctly rejected
        except Exception as e:
            issues.append(f"Failed charter invariants check: {e}")
            charter_invariants_valid = False

        # Functional validity test using in-memory database
        functional_validity_valid = True
        try:
            from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
            from system_mind.database.migrator import DatabaseMigrator
            from system_mind.twin.validity import FreshnessState, StaleReason, TemporalValidityManager

            db_cfg = DatabaseConfig(":memory:")
            conn = DatabaseConnectionManager.connect(db_cfg)
            migrator = DatabaseMigrator(config=db_cfg)
            migrator.apply_all(conn=conn)

            mgr = TemporalValidityManager(conn)

            # 1. Record observation
            t0 = 1700000000000
            rec = mgr.record_entity_observation(
                entity_urn="urn:systemmind:proc:9999",
                device_id="test-device-uuid",
                observed_at_iso="2026-11-18T12:00:00Z",
                observed_at_epoch_ms=t0,
                ttl_seconds=15.0,
            )
            if rec.is_stale is not False or rec.freshness_state != FreshnessState.FRESH.value:
                issues.append("Functional test failed: Initial observation is not FRESH / not stale")
                functional_validity_valid = False

            # 2. Mark stale
            stale_rec = mgr.mark_stale(
                entity_urn="urn:systemmind:proc:9999",
                reason=StaleReason.PROCESS_EXIT,
            )
            if not stale_rec or not stale_rec.is_stale or stale_rec.stale_reason != StaleReason.PROCESS_EXIT.value:
                issues.append("Functional test failed: Mark stale did not set is_stale or stale_reason")
                functional_validity_valid = False

            # 3. Reversible freshness
            t1 = t0 + 20000
            refreshed_rec = mgr.record_entity_observation(
                entity_urn="urn:systemmind:proc:9999",
                device_id="test-device-uuid",
                observed_at_iso="2026-11-18T12:00:20Z",
                observed_at_epoch_ms=t1,
                ttl_seconds=15.0,
            )
            if refreshed_rec.is_stale or refreshed_rec.stale_reason is not None:
                issues.append("Functional test failed: Reversible freshness failed to clear stale markers")
                functional_validity_valid = False

            conn.close()
        except Exception as e:
            issues.append(f"Failed functional validity check: {e}")
            functional_validity_valid = False

        overall_valid = (
            len(issues) == 0
            and migration_present
            and validity_engine_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and functional_validity_valid
        )

        return TemporalValidityAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            validity_engine_present=validity_engine_present,
            design_note_present=design_note_present,
            migration_present=migration_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            functional_validity_valid=functional_validity_valid,
            scan_proves_safe=False,
        )
