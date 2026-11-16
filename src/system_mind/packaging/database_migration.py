"""Automated validator auditing SQLite migration configurations, schemas, and round-trip lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrations import load_migrations_from_directory
from system_mind.database.migrator import DatabaseMigrator
from system_mind.database.models import MigrationDefinition


@dataclass(frozen=True)
class DatabaseMigrationAuditResult:
    """Results of auditing database migration configurations and lifecycle."""

    valid: bool
    issues: tuple[str, ...]
    migration_count: int
    latest_version: int
    lifecycle_roundtrip_ok: bool


class DatabaseMigrationValidator:
    """Programmatic validator verifying SQLite migration infrastructure integrity in CI pipelines."""

    @classmethod
    def audit(cls, migrations_dir: Path | None = None) -> DatabaseMigrationAuditResult:
        """Audits migration files, monotonic ordering, and tests a full in-memory roundtrip."""
        issues: list[str] = []
        lifecycle_ok = False
        latest_ver = 0

        try:
            migrations = load_migrations_from_directory(migrations_dir)
        except Exception as e:
            return DatabaseMigrationAuditResult(
                valid=False,
                issues=(f"Failed to load migrations: {e}",),
                migration_count=0,
                latest_version=0,
                lifecycle_roundtrip_ok=False,
            )

        if not migrations:
            issues.append("No migration files found in migrations directory.")
            return DatabaseMigrationAuditResult(
                valid=False,
                issues=tuple(issues),
                migration_count=0,
                latest_version=0,
                lifecycle_roundtrip_ok=False,
            )

        # 1. Monotonic ordering and completeness
        versions = [m.version for m in migrations]
        for idx, ver in enumerate(versions):
            expected = idx + 1
            if ver != expected:
                issues.append(
                    f"Non-contiguous migration version: found {ver} at index {idx}, expected {expected}."
                )

        latest_ver = versions[-1] if versions else 0

        for m in migrations:
            if not m.up_sql.strip():
                issues.append(f"Migration {m.version:04d}_{m.name} has empty UP SQL.")
            if not m.down_sql.strip():
                issues.append(f"Migration {m.version:04d}_{m.name} has empty DOWN SQL.")

        # 2. Test full in-memory lifecycle: Apply -> Integrity Check -> Rollback -> Re-Apply
        try:
            conn = DatabaseConnectionManager.connect(DatabaseConfig(db_path=":memory:"))
            migrator = DatabaseMigrator(
                db_path=":memory:",
                custom_migrations=migrations,
            )

            # Apply all
            applied = migrator.apply_all(conn=conn)
            if len(applied) != len(migrations):
                issues.append(
                    f"Expected to apply {len(migrations)} migrations, applied {len(applied)}."
                )

            # Verify integrity
            integrity_report = migrator.verify_integrity(conn=conn)
            if not integrity_report.valid:
                issues.extend(integrity_report.issues)

            # Rollback all
            rolled_back = migrator.rollback_to(0, conn=conn)
            if len(rolled_back) != len(migrations):
                issues.append(
                    f"Expected to roll back {len(migrations)} migrations, rolled back {len(rolled_back)}."
                )

            # Re-apply all to verify clean rollback
            reapplied = migrator.apply_all(conn=conn)
            if len(reapplied) != len(migrations):
                issues.append(
                    f"Expected to re-apply {len(migrations)} migrations, reapplied {len(reapplied)}."
                )

            re_report = migrator.verify_integrity(conn=conn)
            if not re_report.valid:
                issues.extend(re_report.issues)

            # Test simulated tamper detection
            tampered_migration = MigrationDefinition(
                version=1,
                name=migrations[0].name,
                up_sql=migrations[0].up_sql + "\n-- Tampered comment",
                down_sql=migrations[0].down_sql,
            )
            tamper_migrator = DatabaseMigrator(
                db_path=":memory:",
                custom_migrations=[tampered_migration] + list(migrations[1:]),
            )
            tamper_report = tamper_migrator.verify_integrity(conn=conn)
            if tamper_report.valid or 1 not in tamper_report.tampered_versions:
                issues.append("Migrator failed to detect altered migration checksum on tampered schema.")

            conn.close()
            lifecycle_ok = True
        except Exception as e:
            issues.append(f"Lifecycle roundtrip test raised unexpected exception: {e}")

        valid = len(issues) == 0
        return DatabaseMigrationAuditResult(
            valid=valid,
            issues=tuple(issues),
            migration_count=len(migrations),
            latest_version=latest_ver,
            lifecycle_roundtrip_ok=lifecycle_ok,
        )
