"""Packaging and safety invariant validator for Day 067 Database Entity Models."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class DatabaseEntitiesAuditResult:
    """Outcome of auditing Day 067 database models, schemas, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    migration_present: bool
    models_present: bool
    repository_present: bool
    design_note_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    lifecycle_roundtrip_valid: bool


class DatabaseEntitiesValidator:
    """Audits the completeness, safety, and packaging of Day 067 database entity models."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0003_hardware_os_application_entities.sql"),
        Path("src/system_mind/database/entity_models.py"),
        Path("src/system_mind/database/entity_repo.py"),
        Path("docs/design/DAY_067_DATABASE_MODELS_HARDWARE_OS_APPLICATION.md"),
        Path("tools/detect_database_entities.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> DatabaseEntitiesAuditResult:
        """Executes comprehensive packaging audit across database entity components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        mig_file = base / "src/system_mind/database/migrations/0003_hardware_os_application_entities.sql"
        models_file = base / "src/system_mind/database/entity_models.py"
        repo_file = base / "src/system_mind/database/entity_repo.py"
        design_file = base / "docs/design/DAY_067_DATABASE_MODELS_HARDWARE_OS_APPLICATION.md"
        tool_file = base / "tools/detect_database_entities.py"

        migration_present = mig_file.is_file()
        models_present = models_file.is_file()
        repository_present = repo_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [models_file, repo_file, tool_file]
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
            from system_mind.core.types import ComponentOwnership
            from system_mind.database.entity_models import (
                ApplicationEntityRecord,
                HardwareCategory,
                HardwareEntityRecord,
                OsKernelEntityRecord,
            )

            # Test hardware model
            hw = HardwareEntityRecord(
                entity_urn="urn:systemmind:host:d5a1b3c9",
                device_id="d5a1b3c9",
                category=HardwareCategory.HOST,
                model_name="Apple Silicon Virtual Host",
            )
            if hw.scan_proves_safe is not False:
                issues.append("HardwareEntityRecord violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                HardwareEntityRecord(
                    entity_urn="urn:systemmind:host:d5a1b3c9",
                    device_id="d5a1b3c9",
                    category=HardwareCategory.HOST,
                    model_name="Apple Silicon Virtual Host",
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append("HardwareEntityRecord permitted scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correct

            # Test application model
            app = ApplicationEntityRecord(
                entity_urn="urn:systemmind:app:com.apple.safari",
                device_id="d5a1b3c9",
                bundle_id="com.apple.Safari",
                app_name="Safari",
                version="18.0",
                install_path="/Applications/Safari.app",
                ownership=ComponentOwnership.SYSTEM_MANAGED,
            )
            if app.scan_proves_safe is not False:
                issues.append("ApplicationEntityRecord violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                ApplicationEntityRecord(
                    entity_urn="urn:systemmind:app:com.apple.safari",
                    device_id="d5a1b3c9",
                    bundle_id="com.apple.Safari",
                    app_name="Safari",
                    version="18.0",
                    install_path="/Applications/Safari.app",
                    ownership=ComponentOwnership.SYSTEM_MANAGED,
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append("ApplicationEntityRecord permitted scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correct
        except Exception as e:
            issues.append(f"Failed to inspect entity model invariants: {e}")
            charter_invariants_valid = False

        # Lifecycle roundtrip test in an in-memory SQLite database
        lifecycle_roundtrip_valid = True
        try:
            from system_mind.database.entity_repo import EntityRepository
            from system_mind.database.migrator import DatabaseMigrator

            migrator = DatabaseMigrator(db_path=":memory:")
            conn = migrator._get_connection()
            try:
                migrator.apply_all(conn=conn)
                repo = EntityRepository(conn)

                # Insert and retrieve hardware entity
                repo.save_hardware_entity(hw)
                fetched_hw = repo.get_hardware_entity(hw.entity_urn)
                if not fetched_hw or fetched_hw.model_name != hw.model_name:
                    issues.append("Failed to round-trip HardwareEntityRecord through SQLite")
                    lifecycle_roundtrip_valid = False

                # Insert and retrieve application entity
                repo.save_application_entity(app)
                fetched_app = repo.get_application_entity(app.entity_urn)
                if not fetched_app or fetched_app.app_name != app.app_name:
                    issues.append("Failed to round-trip ApplicationEntityRecord through SQLite")
                    lifecycle_roundtrip_valid = False

                # Rollback all migrations to verify teardown
                migrator.rollback_to(0, conn=conn)
            finally:
                conn.close()
        except Exception as e:
            issues.append(f"Failed to execute SQLite migration lifecycle roundtrip: {e}")
            lifecycle_roundtrip_valid = False

        valid = len(issues) == 0

        return DatabaseEntitiesAuditResult(
            valid=valid,
            issues=tuple(issues),
            migration_present=migration_present,
            models_present=models_present,
            repository_present=repository_present,
            design_note_present=design_note_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            lifecycle_roundtrip_valid=lifecycle_roundtrip_valid,
        )
