"""Packaging and safety invariant validator for Day 077 Process Start and Exit Tracking."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class ProcessLifecycleAuditResult:
    """Outcome of auditing Day 077 process start and exit tracking components and invariants."""

    valid: bool
    issues: tuple[str, ...]
    process_lifecycle_present: bool
    design_note_present: bool
    migration_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    functional_lifecycle_valid: bool
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces Charter Invariant SC-03: scan_proves_safe is NEVER True."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")


class ProcessLifecycleValidator:
    """Audits the completeness, safety, and packaging of Day 077 process lifecycle tracking."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0012_process_lifecycle_events.sql"),
        Path("src/system_mind/twin/process_lifecycle.py"),
        Path("docs/design/DAY_077_PROCESS_START_AND_EXIT_TRACKING.md"),
        Path("tools/detect_process_lifecycle.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> ProcessLifecycleAuditResult:
        """Executes comprehensive packaging audit across process lifecycle tracking components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        migration_file = (
            base / "src/system_mind/database/migrations/0012_process_lifecycle_events.sql"
        )
        module_file = base / "src/system_mind/twin/process_lifecycle.py"
        design_file = (
            base / "docs/design/DAY_077_PROCESS_START_AND_EXIT_TRACKING.md"
        )
        tool_file = base / "tools/detect_process_lifecycle.py"

        migration_present = migration_file.is_file()
        process_lifecycle_present = module_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # Check migration file content
        if migration_present:
            content = migration_file.read_text(encoding="utf-8")
            if "-- UP" not in content or "-- DOWN" not in content:
                issues.append(
                    "Migration 0012 must contain both '-- UP' and '-- DOWN' markers."
                )
            if "process_lifecycle_events" not in content:
                issues.append(
                    "Migration 0012 must create table process_lifecycle_events."
                )
            if (
                "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)"
                not in content
            ):
                issues.append(
                    "Migration 0012 must enforce CHECK (scan_proves_safe = 0)."
                )

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [module_file, tool_file]
        for pf in python_files:
            if pf.is_file():
                try:
                    tree = ast.parse(pf.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Attribute):
                                if (
                                    isinstance(node.func.value, ast.Name)
                                    and node.func.value.id == "os"
                                ):
                                    if node.func.attr in ("system", "popen"):
                                        issues.append(
                                            f"Forbidden call to os.{node.func.attr} in {pf.name}"
                                        )
                                        ast_safety_valid = False
                            for kw in node.keywords:
                                if (
                                    kw.arg == "shell"
                                    and isinstance(kw.value, ast.Constant)
                                    and kw.value.value is True
                                ):
                                    issues.append(f"Forbidden shell=True in {pf.name}")
                                    ast_safety_valid = False
                except Exception as e:
                    issues.append(f"Failed to parse AST of {pf.name}: {e}")
                    ast_safety_valid = False

        # Invariant checks on runtime models (SC-03: scan_proves_safe = False)
        charter_invariants_valid = True
        try:
            from system_mind.core.types import ComponentOwnership
            from system_mind.twin.identity import StableEntityIdGenerator
            from system_mind.twin.process_lifecycle import (
                ProcessDetectionSource,
                ProcessExitStatus,
                ProcessLifecycleEvent,
                ProcessLifecycleEventType,
            )

            test_urn = StableEntityIdGenerator.generate_process_urn(
                device_id="dev-test-01",
                pid=1234,
                start_time_epoch_ms=1700000000000,
                binary_path="/usr/bin/python3",
            )
            ev = ProcessLifecycleEvent(
                event_id="pevt_test_01",
                device_id="dev-test-01",
                entity_urn=test_urn.urn,
                event_type=ProcessLifecycleEventType.PROCESS_STARTED,
                pid=1234,
                ppid=1,
                process_name="python3",
                binary_path="/usr/bin/python3",
                command_line="/usr/bin/python3 app.py",
                user_name="tharungodwin",
                uid=501,
                start_epoch_ms=1700000000000,
                ownership=ComponentOwnership.USER_MANAGED,
                detection_source=ProcessDetectionSource.PROCESS_TABLE_DIFF,
                observed_at_iso="2026-11-18T12:00:00Z",
                observed_at_epoch_ms=1700000000000,
                scan_proves_safe=False,
            )
            if ev.scan_proves_safe is not False:
                issues.append("ProcessLifecycleEvent allowed scan_proves_safe=True.")
                charter_invariants_valid = False

            # Test that scan_proves_safe=True raises ValueError
            try:
                ProcessLifecycleEvent(
                    event_id="pevt_test_02",
                    device_id="dev-test-01",
                    entity_urn=test_urn.urn,
                    event_type=ProcessLifecycleEventType.PROCESS_STARTED,
                    pid=1234,
                    ppid=1,
                    process_name="python3",
                    binary_path="/usr/bin/python3",
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append("ProcessLifecycleEvent failed to reject scan_proves_safe=True.")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correct behavior

        except Exception as e:
            issues.append(f"Failed charter invariants check: {e}")
            charter_invariants_valid = False

        # Functional check on lifecycle tracker and database schema
        functional_lifecycle_valid = True
        try:
            from system_mind.twin.process_lifecycle import (
                ProcessLifecycleManager,
                ProcessLifecycleTracker,
            )

            prev_procs = [
                {"pid": 1, "ppid": 0, "name": "launchd", "command_path": "/sbin/launchd", "start_time_epoch_ms": 1000, "is_system_core": True},
                {"pid": 500, "ppid": 1, "name": "zsh", "command_path": "/bin/zsh", "start_time_epoch_ms": 2000, "is_system_core": False},
            ]
            curr_procs = [
                {"pid": 1, "ppid": 0, "name": "launchd", "command_path": "/sbin/launchd", "start_time_epoch_ms": 1000, "is_system_core": True},
                {"pid": 600, "ppid": 500, "name": "git", "command_path": "/usr/bin/git", "start_time_epoch_ms": 3000, "is_system_core": False},
            ]

            diff = ProcessLifecycleTracker.diff_process_tables(
                baseline_processes=prev_procs,
                current_processes=curr_procs,
                device_id="dev-test-01",
                observed_at_epoch_ms=3500,
            )

            # PID 500 exited, PID 600 started
            if len(diff.started_events) != 1 or diff.started_events[0].pid != 600:
                issues.append("ProcessLifecycleTracker diff failed to identify started process 600.")
                functional_lifecycle_valid = False
            if len(diff.exited_events) != 1 or diff.exited_events[0].pid != 500:
                issues.append("ProcessLifecycleTracker diff failed to identify exited process 500.")
                functional_lifecycle_valid = False

            # In-memory SQLite migration test
            if migration_present:
                mem_conn = sqlite3.connect(":memory:")
                cur = mem_conn.cursor()
                up_sql = migration_file.read_text(encoding="utf-8").split("-- UP")[1].split("-- DOWN")[0]
                cur.executescript(up_sql)

                ProcessLifecycleManager.record_events(mem_conn, diff.all_events)
                retrieved = ProcessLifecycleManager.get_events(mem_conn, device_id="dev-test-01")
                if len(retrieved) != 2:
                    issues.append(f"ProcessLifecycleManager stored {len(retrieved)} events, expected 2.")
                    functional_lifecycle_valid = False

                # Point-in-time check at t=2500 (PID 500 was alive, PID 600 was not)
                active_at_2500 = ProcessLifecycleManager.get_running_processes_at(mem_conn, target_epoch_ms=2500, device_id="dev-test-01")
                active_pids = [p["pid"] for p in active_at_2500]
                if 500 not in active_pids or 600 in active_pids:
                    issues.append(f"Point-in-time reconstruction at 2500 failed: active PIDs = {active_pids}")
                    functional_lifecycle_valid = False

                mem_conn.close()

        except Exception as e:
            issues.append(f"Functional process lifecycle check failed: {e}")
            functional_lifecycle_valid = False

        valid = (
            len(issues) == 0
            and migration_present
            and process_lifecycle_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and functional_lifecycle_valid
        )

        return ProcessLifecycleAuditResult(
            valid=valid,
            issues=tuple(issues),
            process_lifecycle_present=process_lifecycle_present,
            design_note_present=design_note_present,
            migration_present=migration_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            functional_lifecycle_valid=functional_lifecycle_valid,
            scan_proves_safe=False,
        )
