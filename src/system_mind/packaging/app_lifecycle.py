"""Packaging and safety invariant validator for Day 076 Application Installation and Removal Tracking."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class ApplicationLifecycleAuditResult:
    """Outcome of auditing Day 076 application lifecycle tracking components and invariants."""

    valid: bool
    issues: tuple[str, ...]
    app_lifecycle_present: bool
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


class ApplicationLifecycleValidator:
    """Audits the completeness, safety, and packaging of Day 076 application lifecycle tracking."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0011_application_lifecycle_events.sql"),
        Path("src/system_mind/twin/app_lifecycle.py"),
        Path("docs/design/DAY_076_APPLICATION_INSTALLATION_AND_REMOVAL_TRACKING.md"),
        Path("tools/detect_application_lifecycle.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> ApplicationLifecycleAuditResult:
        """Executes comprehensive packaging audit across application lifecycle tracking components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        migration_file = (
            base / "src/system_mind/database/migrations/0011_application_lifecycle_events.sql"
        )
        module_file = base / "src/system_mind/twin/app_lifecycle.py"
        design_file = (
            base / "docs/design/DAY_076_APPLICATION_INSTALLATION_AND_REMOVAL_TRACKING.md"
        )
        tool_file = base / "tools/detect_application_lifecycle.py"

        migration_present = migration_file.is_file()
        app_lifecycle_present = module_file.is_file()
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
                    "Migration 0011 must contain both '-- UP' and '-- DOWN' markers."
                )
            if "application_lifecycle_events" not in content:
                issues.append(
                    "Migration 0011 must create table application_lifecycle_events."
                )
            if (
                "scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)"
                not in content
            ):
                issues.append(
                    "Migration 0011 must enforce CHECK (scan_proves_safe = 0)."
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
            from system_mind.twin.identity import EntityDomain, create_entity_urn
            from system_mind.twin.app_lifecycle import (
                ApplicationDetectionSource,
                ApplicationLifecycleEvent,
                ApplicationLifecycleEventType,
            )

            test_urn = create_entity_urn(EntityDomain.APPLICATION, "com.test.app")
            ev = ApplicationLifecycleEvent(
                device_id="dev-test-01",
                entity_urn=test_urn,
                event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
                bundle_id="com.test.app",
                app_name="TestApp",
                bundle_path="/Applications/TestApp.app",
                version="1.0.0",
                ownership=ComponentOwnership.USER_MANAGED,
                detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
                scan_proves_safe=False,
            )
            if ev.scan_proves_safe is not False:
                issues.append(
                    "ApplicationLifecycleEvent allowed scan_proves_safe=True."
                )
                charter_invariants_valid = False

            # Test that scan_proves_safe=True raises ValueError
            try:
                ApplicationLifecycleEvent(
                    device_id="dev-test-01",
                    entity_urn=test_urn,
                    event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
                    bundle_id="com.test.app",
                    app_name="TestApp",
                    bundle_path="/Applications/TestApp.app",
                    version="1.0.0",
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append(
                    "ApplicationLifecycleEvent failed to reject scan_proves_safe=True."
                )
                charter_invariants_valid = False
            except ValueError:
                pass  # Correct behavior

        except Exception as e:
            issues.append(f"Failed charter invariants check: {e}")
            charter_invariants_valid = False

        # Functional check on lifecycle tracker
        functional_lifecycle_valid = True
        try:
            from system_mind.twin.app_lifecycle import (
                ApplicationLifecycleManager,
                ApplicationLifecycleTracker,
            )

            prev_inv = [
                {
                    "bundle_id": "com.apple.safari",
                    "app_name": "Safari",
                    "version": "17.0",
                    "install_path": "/Applications/Safari.app",
                    "ownership": "SYSTEM_MANAGED",
                },
                {
                    "bundle_id": "com.spotify.client",
                    "app_name": "Spotify",
                    "version": "1.2.0",
                    "install_path": "/Applications/Spotify.app",
                    "ownership": "USER_MANAGED",
                },
            ]

            curr_inv = [
                {
                    "bundle_id": "com.apple.safari",
                    "app_name": "Safari",
                    "version": "17.1",  # Upgraded
                    "install_path": "/Applications/Safari.app",
                    "ownership": "SYSTEM_MANAGED",
                },
                # Spotify removed
                {
                    "bundle_id": "com.google.chrome",  # Installed
                    "app_name": "Google Chrome",
                    "version": "120.0",
                    "install_path": "/Applications/Google Chrome.app",
                    "ownership": "USER_MANAGED",
                },
            ]

            diff = ApplicationLifecycleTracker.detect_from_inventory_diff(
                previous_inventory=prev_inv,
                current_inventory=curr_inv,
                device_id="dev-test-01",
            )

            if len(diff.installed_apps) != 1:
                issues.append(
                    f"Expected 1 installed app, got {len(diff.installed_apps)}"
                )
                functional_lifecycle_valid = False
            if len(diff.removed_apps) != 1:
                issues.append(f"Expected 1 removed app, got {len(diff.removed_apps)}")
                functional_lifecycle_valid = False
            if len(diff.upgraded_apps) != 1:
                issues.append(f"Expected 1 upgraded app, got {len(diff.upgraded_apps)}")
                functional_lifecycle_valid = False

            # Verify in-memory database persistence
            conn = sqlite3.connect(":memory:")
            migration_text = migration_file.read_text(encoding="utf-8")
            up_part = migration_text.split("-- DOWN")[0].replace("-- UP", "")
            conn.executescript(up_part)

            manager = ApplicationLifecycleManager(conn)
            manager.record_diff(diff)
            events = manager.get_recent_events(limit=10)
            if len(events) != 3:
                issues.append(
                    f"Expected 3 persisted lifecycle events, got {len(events)}"
                )
                functional_lifecycle_valid = False

        except Exception as e:
            issues.append(f"Failed functional application lifecycle check: {e}")
            functional_lifecycle_valid = False

        valid = (
            len(issues) == 0
            and migration_present
            and app_lifecycle_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and functional_lifecycle_valid
        )

        return ApplicationLifecycleAuditResult(
            valid=valid,
            issues=tuple(issues),
            app_lifecycle_present=app_lifecycle_present,
            design_note_present=design_note_present,
            migration_present=migration_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            functional_lifecycle_valid=functional_lifecycle_valid,
            scan_proves_safe=False,
        )
