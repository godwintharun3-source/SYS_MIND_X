"""Packaging and safety invariant validator for Day 070 Append-Only System Event Storage."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class SystemEventsAuditResult:
    """Outcome of auditing Day 070 append-only system event storage, schema, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    migration_present: bool
    models_present: bool
    design_note_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    immutability_triggers_valid: bool
    hash_chain_valid: bool


class SystemEventsValidator:
    """Audits the completeness, safety, and packaging of Day 070 append-only system event storage."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0006_system_events_storage.sql"),
        Path("src/system_mind/twin/event_store.py"),
        Path("docs/design/DAY_070_APPEND_ONLY_SYSTEM_EVENT_STORAGE.md"),
        Path("tools/detect_system_events.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> SystemEventsAuditResult:
        """Executes comprehensive packaging audit across system event storage components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        mig_file = base / "src/system_mind/database/migrations/0006_system_events_storage.sql"
        models_file = base / "src/system_mind/twin/event_store.py"
        design_file = base / "docs/design/DAY_070_APPEND_ONLY_SYSTEM_EVENT_STORAGE.md"
        tool_file = base / "tools/detect_system_events.py"

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
        immutability_triggers_valid = True
        if migration_present:
            mig_content = mig_file.read_text(encoding="utf-8")
            required_phrases = [
                "CREATE TABLE IF NOT EXISTS system_events",
                "sequence_number INTEGER PRIMARY KEY AUTOINCREMENT",
                "event_id TEXT UNIQUE NOT NULL",
                "device_id TEXT NOT NULL",
                "entity_urn TEXT NOT NULL",
                "event_type TEXT NOT NULL",
                "prev_event_hash TEXT NOT NULL",
                "event_hash TEXT NOT NULL",
                "component_ownership TEXT NOT NULL",
                "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)",
                "CREATE TRIGGER IF NOT EXISTS trg_system_events_prevent_update",
                "CREATE TRIGGER IF NOT EXISTS trg_system_events_prevent_delete",
                "DROP TRIGGER IF EXISTS trg_system_events_prevent_delete;",
                "DROP TRIGGER IF EXISTS trg_system_events_prevent_update;",
                "DROP TABLE IF EXISTS system_events;",
            ]
            for phrase in required_phrases:
                if phrase not in mig_content:
                    issues.append(f"Migration 0006 missing expected DDL phrase: '{phrase}'")
                    immutability_triggers_valid = False

        # In-Memory Functional Lifecycle & Trigger Verification
        charter_invariants_valid = True
        hash_chain_valid = True
        if models_present and migration_present:
            try:
                from system_mind.core.types import ComponentOwnership
                from system_mind.database.migrator import DatabaseMigrator
                from system_mind.twin.event_store import (
                    SystemEventRecord,
                    SystemEventStore,
                    SystemEventType,
                )

                migrator = DatabaseMigrator(db_path=":memory:")
                conn = migrator._get_connection()
                migrator.apply_all(conn=conn)

                store = SystemEventStore(conn)

                # 1. Charter Invariant SC-03: scan_proves_safe = True rejection
                try:
                    SystemEventRecord(
                        sequence_number=1,
                        event_id="evt-bad",
                        device_id="dev-1",
                        entity_urn="urn:systemmind:host:test",
                        event_type="SYSTEM_ALERT",
                        timestamp_iso="2026-11-18T11:00:00+00:00",
                        timestamp_epoch_ms=1000,
                        prev_event_hash="0" * 64,
                        scan_proves_safe=True,  # Prohibited
                    )
                    issues.append("SystemEventRecord accepted scan_proves_safe=True (Charter SC-03 violation)")
                    charter_invariants_valid = False
                except ValueError:
                    pass

                # 2. Append-only triggers: UPDATE prohibition test
                evt = store.append_event(
                    device_id="dev-audit",
                    entity_urn="urn:systemmind:proc:audit:1",
                    event_type=SystemEventType.PROCESS_SPAWNED,
                    payload={"pid": 1, "name": "launchd"},
                    component_ownership=ComponentOwnership.SYSTEM_MANAGED,
                )
                try:
                    conn.execute(
                        "UPDATE system_events SET event_type = 'TAMPERED' WHERE event_id = ?;",
                        (evt.event_id,),
                    )
                    issues.append("SQLite allowed UPDATE on system_events (immutability trigger failure)")
                    immutability_triggers_valid = False
                except (sqlite3.IntegrityError, sqlite3.OperationalError) as ex:
                    if "System events are append-only" not in str(ex):
                        issues.append(f"Unexpected trigger error message on UPDATE: {ex}")
                        immutability_triggers_valid = False

                # 3. Append-only triggers: DELETE prohibition test
                try:
                    conn.execute(
                        "DELETE FROM system_events WHERE event_id = ?;",
                        (evt.event_id,),
                    )
                    issues.append("SQLite allowed DELETE on system_events (immutability trigger failure)")
                    immutability_triggers_valid = False
                except (sqlite3.IntegrityError, sqlite3.OperationalError) as ex:
                    if "System events are append-only" not in str(ex):
                        issues.append(f"Unexpected trigger error message on DELETE: {ex}")
                        immutability_triggers_valid = False

                # 4. Hash Chain Integrity Test
                store.append_event(
                    device_id="dev-audit",
                    entity_urn="urn:systemmind:proc:audit:1",
                    event_type=SystemEventType.PROCESS_EXITED,
                    payload={"exit_code": 0},
                    component_ownership=ComponentOwnership.SYSTEM_MANAGED,
                )
                is_valid, count, err = store.verify_chain_integrity()
                if not is_valid or count != 2:
                    issues.append(f"Hash chain verification failed: {err}")
                    hash_chain_valid = False

                conn.close()

            except Exception as ex:
                issues.append(f"Event store functional validation error: {ex}")
                charter_invariants_valid = False
                immutability_triggers_valid = False
                hash_chain_valid = False

        overall_valid = (
            len(issues) == 0
            and migration_present
            and models_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and immutability_triggers_valid
            and hash_chain_valid
        )

        return SystemEventsAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            migration_present=migration_present,
            models_present=models_present,
            design_note_present=design_note_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            immutability_triggers_valid=immutability_triggers_valid,
            hash_chain_valid=hash_chain_valid,
        )
