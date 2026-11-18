"""SQLite database migration orchestrator with transaction safety and tamper detection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from typing import Sequence

from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrations import load_migrations_from_directory
from system_mind.database.models import (
    AppliedMigrationRecord,
    DatabaseIntegrityReport,
    MigrationDefinition,
    MigrationDirection,
    MigrationPlan,
)
from system_mind.logging import get_logger

logger = get_logger("system_mind.database")


def split_sql_statements(script: str) -> list[str]:
    """Splits an SQL script into executable statements, preserving string literals."""
    lines: list[str] = []
    for line in script.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("--"):
            continue
        lines.append(line)
    clean_script = "\n".join(lines)

    statements: list[str] = []
    current: list[str] = []
    in_string = False
    quote_char = ""
    i = 0
    length = len(clean_script)

    while i < length:
        char = clean_script[i]
        if char in ('"', "'"):
            if not in_string:
                in_string = True
                quote_char = char
            elif quote_char == char:
                # Handle escaped quotes, e.g. '' or ""
                if i + 1 < length and clean_script[i + 1] == quote_char:
                    current.append(char)
                    i += 1
                    current.append(char)
                    i += 1
                    continue
                in_string = False
        if char == ";" and not in_string:
            candidate = "".join(current).strip() + ";"
            if sqlite3.complete_statement(candidate):
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
            else:
                current.append(char)
        else:
            current.append(char)
        i += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)

    return statements


class DatabaseMigrator:
    """Manages transactional execution, rollback, and verification of SQLite database migrations."""

    MIGRATIONS_TABLE = "_schema_migrations"

    def __init__(
        self,
        db_path: str = ":memory:",
        migrations_dir: Path | None = None,
        custom_migrations: Sequence[MigrationDefinition] | None = None,
        config: DatabaseConfig | None = None,
    ) -> None:
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self.config = config or DatabaseConfig(db_path=db_path)
        self._custom_migrations = tuple(custom_migrations) if custom_migrations else None

    def _get_connection(self) -> sqlite3.Connection:
        """Internal helper to acquire a configured connection."""
        return DatabaseConnectionManager.connect(self.config)

    def get_registered_migrations(self) -> list[MigrationDefinition]:
        """Returns all registered migration definitions in ascending version order."""
        if self._custom_migrations is not None:
            migrations = sorted(self._custom_migrations, key=lambda m: m.version)
        else:
            migrations = load_migrations_from_directory(self.migrations_dir)

        # Enforce uniqueness and ascending order
        versions = [m.version for m in migrations]
        if len(versions) != len(set(versions)):
            raise ValueError(f"Duplicate migration versions detected: {versions}")
        return migrations

    def initialize_schema_table(self, conn: sqlite3.Connection | None = None) -> None:
        """Initializes the _schema_migrations tracking table if not present."""
        managed = conn is None
        active_conn = self._get_connection() if managed else conn
        assert active_conn is not None

        try:
            active_conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.MIGRATIONS_TABLE} (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    execution_time_ms REAL NOT NULL
                );
                """
            )
            logger.debug(
                "Initialized schema migrations ledger table",
                table=self.MIGRATIONS_TABLE,
                db=self.db_path,
            )
        finally:
            if managed:
                active_conn.close()

    def get_applied_migrations(
        self, conn: sqlite3.Connection | None = None
    ) -> list[AppliedMigrationRecord]:
        """Returns all applied migration records ordered by version ascending."""
        managed = conn is None
        active_conn = self._get_connection() if managed else conn
        assert active_conn is not None

        try:
            self.initialize_schema_table(active_conn)
            cursor = active_conn.execute(
                f"""
                SELECT version, name, applied_at, checksum, execution_time_ms
                FROM {self.MIGRATIONS_TABLE}
                ORDER BY version ASC;
                """
            )
            records = [
                AppliedMigrationRecord(
                    version=row["version"],
                    name=row["name"],
                    applied_at=row["applied_at"],
                    checksum=row["checksum"],
                    execution_time_ms=row["execution_time_ms"],
                )
                for row in cursor.fetchall()
            ]
            return records
        finally:
            if managed:
                active_conn.close()

    def plan(
        self,
        direction: MigrationDirection = MigrationDirection.UP,
        target_version: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> MigrationPlan:
        """Computes a migration plan without mutating the database."""
        registered = self.get_registered_migrations()
        applied = self.get_applied_migrations(conn)
        applied_versions = {a.version for a in applied}
        current_version = max(applied_versions) if applied_versions else 0

        if direction == MigrationDirection.UP:
            pending = [
                m
                for m in registered
                if m.version > current_version
                and (target_version is None or m.version <= target_version)
            ]
            return MigrationPlan(
                direction=direction,
                target_version=target_version,
                migrations=tuple(pending),
                is_noop=len(pending) == 0,
            )
        else:
            # DOWN
            target = 0 if target_version is None else target_version
            registered_by_version = {m.version: m for m in registered}
            to_rollback: list[MigrationDefinition] = []
            for record in reversed(applied):
                if record.version > target:
                    if record.version not in registered_by_version:
                        raise ValueError(
                            f"Cannot roll back version {record.version}: definition not found."
                        )
                    to_rollback.append(registered_by_version[record.version])
            return MigrationPlan(
                direction=direction,
                target_version=target,
                migrations=tuple(to_rollback),
                is_noop=len(to_rollback) == 0,
            )

    def apply_migration(
        self, version: int, conn: sqlite3.Connection | None = None
    ) -> AppliedMigrationRecord:
        """Applies a single migration forward inside an atomic transaction."""
        managed = conn is None
        active_conn = self._get_connection() if managed else conn
        assert active_conn is not None

        try:
            self.initialize_schema_table(active_conn)
            registered = {m.version: m for m in self.get_registered_migrations()}
            if version not in registered:
                raise ValueError(f"Migration version {version} is not registered.")
            migration = registered[version]

            applied = self.get_applied_migrations(active_conn)
            applied_versions = {a.version for a in applied}
            if version in applied_versions:
                raise ValueError(f"Migration {version:04d}_{migration.name} is already applied.")

            # Validate monotonic sequence (no gaps allowed in forward migration)
            expected_next = max(applied_versions) + 1 if applied_versions else 1
            if version != expected_next:
                raise ValueError(
                    f"Out-of-order migration detected: attempting to apply version {version}, "
                    f"but next expected version is {expected_next}."
                )

            logger.info(
                "Applying database migration",
                event="db_migration_apply_started",
                version=migration.version,
                name=migration.name,
                checksum=migration.checksum,
            )

            statements = split_sql_statements(migration.up_sql)
            start_time = time.perf_counter()

            # Execute migration statements and record entry atomically
            active_conn.execute("BEGIN IMMEDIATE;")
            try:
                for stmt in statements:
                    active_conn.execute(stmt)

                duration_ms = (time.perf_counter() - start_time) * 1000.0
                applied_at = datetime.now(timezone.utc).isoformat()

                active_conn.execute(
                    f"""
                    INSERT INTO {self.MIGRATIONS_TABLE} (version, name, applied_at, checksum, execution_time_ms)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        migration.version,
                        migration.name,
                        applied_at,
                        migration.checksum,
                        duration_ms,
                    ),
                )
                active_conn.execute("COMMIT;")
            except Exception as e:
                active_conn.execute("ROLLBACK;")
                logger.error(
                    "Database migration failed; transaction rolled back",
                    event="db_migration_apply_failed",
                    version=migration.version,
                    name=migration.name,
                    error=str(e),
                )
                raise

            record = AppliedMigrationRecord(
                version=migration.version,
                name=migration.name,
                applied_at=applied_at,
                checksum=migration.checksum,
                execution_time_ms=duration_ms,
            )

            logger.info(
                "Database migration applied successfully",
                event="db_migration_apply_completed",
                version=record.version,
                name=record.name,
                duration_ms=round(duration_ms, 2),
            )
            return record
        finally:
            if managed:
                active_conn.close()

    def apply_all(self, conn: sqlite3.Connection | None = None) -> list[AppliedMigrationRecord]:
        """Applies all pending migrations in monotonic order."""
        managed = conn is None
        active_conn = self._get_connection() if managed else conn
        assert active_conn is not None

        try:
            plan = self.plan(MigrationDirection.UP, conn=active_conn)
            results: list[AppliedMigrationRecord] = []
            for migration in plan.migrations:
                record = self.apply_migration(migration.version, conn=active_conn)
                results.append(record)
            return results
        finally:
            if managed:
                active_conn.close()

    def rollback_last(
        self, conn: sqlite3.Connection | None = None
    ) -> AppliedMigrationRecord | None:
        """Rolls back the most recently applied migration."""
        managed = conn is None
        active_conn = self._get_connection() if managed else conn
        assert active_conn is not None

        try:
            applied = self.get_applied_migrations(active_conn)
            if not applied:
                logger.info("No applied migrations to rollback.", event="db_migration_rollback_noop")
                return None

            latest = applied[-1]
            registered = {m.version: m for m in self.get_registered_migrations()}
            if latest.version not in registered:
                raise ValueError(
                    f"Cannot roll back version {latest.version}: definition not found in registry."
                )
            migration = registered[latest.version]

            logger.warning(
                "Rolling back database migration",
                event="db_migration_rollback_started",
                version=latest.version,
                name=latest.name,
            )

            statements = split_sql_statements(migration.down_sql)
            start_time = time.perf_counter()

            active_conn.execute("BEGIN IMMEDIATE;")
            try:
                for stmt in statements:
                    active_conn.execute(stmt)

                active_conn.execute(
                    f"DELETE FROM {self.MIGRATIONS_TABLE} WHERE version = ?;",
                    (latest.version,),
                )
                active_conn.execute("COMMIT;")
            except Exception as e:
                active_conn.execute("ROLLBACK;")
                logger.error(
                    "Database migration rollback failed; transaction rolled back",
                    event="db_migration_rollback_failed",
                    version=latest.version,
                    name=latest.name,
                    error=str(e),
                )
                raise

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info(
                "Database migration rolled back successfully",
                event="db_migration_rollback_completed",
                version=latest.version,
                name=latest.name,
                duration_ms=round(duration_ms, 2),
            )
            return latest
        finally:
            if managed:
                active_conn.close()

    def rollback_to(
        self, target_version: int, conn: sqlite3.Connection | None = None
    ) -> list[AppliedMigrationRecord]:
        """Rolls back applied migrations in descending order down to target_version."""
        if target_version < 0:
            raise ValueError(f"Target version must be non-negative, got: {target_version}")

        managed = conn is None
        active_conn = self._get_connection() if managed else conn
        assert active_conn is not None

        try:
            rolled_back: list[AppliedMigrationRecord] = []
            while True:
                applied = self.get_applied_migrations(active_conn)
                if not applied or applied[-1].version <= target_version:
                    break
                rec = self.rollback_last(active_conn)
                if rec:
                    rolled_back.append(rec)
            return rolled_back
        finally:
            if managed:
                active_conn.close()

    def verify_integrity(
        self, conn: sqlite3.Connection | None = None
    ) -> DatabaseIntegrityReport:
        """Audits database schema integrity, foreign keys, and migration ledger drift."""
        managed = conn is None
        active_conn = self._get_connection() if managed else conn
        assert active_conn is not None

        try:
            issues: list[str] = []
            tampered: list[int] = []

            # 1. Verify PRAGMA integrity
            integrity_rows = active_conn.execute("PRAGMA integrity_check;").fetchall()
            integrity_results = [r[0] for r in integrity_rows]
            if integrity_results != ["ok"]:
                issues.append(f"PRAGMA integrity_check failed: {integrity_results}")

            # 2. Verify PRAGMA foreign keys
            fk_violations = active_conn.execute("PRAGMA foreign_key_check;").fetchall()
            fk_violation_strings = [
                f"Table {r[0]} rowid {r[1]} -> parent {r[2]} fk {r[3]}" for r in fk_violations
            ]
            if fk_violation_strings:
                issues.append(f"Foreign key violations detected: {fk_violation_strings}")

            # 3. Check migration ledger consistency
            applied = self.get_applied_migrations(active_conn)
            registered = {m.version: m for m in self.get_registered_migrations()}

            # Check for non-monotonic sequence or gaps
            applied_versions = [a.version for a in applied]
            for idx, ver in enumerate(applied_versions):
                expected = idx + 1
                if ver != expected:
                    issues.append(
                        f"Non-contiguous migration sequence: index {idx} has version {ver}, expected {expected}."
                    )

            # Check checksum fidelity
            for record in applied:
                if record.version not in registered:
                    issues.append(
                        f"Applied migration {record.version:04d}_{record.name} is missing from registry."
                    )
                else:
                    def_checksum = registered[record.version].checksum
                    if record.checksum != def_checksum:
                        tampered.append(record.version)
                        issues.append(
                            f"Tampered migration detected at version {record.version}: "
                            f"applied checksum={record.checksum[:12]}, registered checksum={def_checksum[:12]}"
                        )
                        logger.critical(
                            "Database migration checksum mismatch detected (tampering/drift)",
                            event="db_migration_tamper_detected",
                            version=record.version,
                            applied_checksum=record.checksum,
                            definition_checksum=def_checksum,
                        )

            latest_version = applied_versions[-1] if applied_versions else None
            pending_count = len([m for m in registered.values() if m.version not in set(applied_versions)])

            valid = len(issues) == 0

            report = DatabaseIntegrityReport(
                valid=valid,
                applied_count=len(applied),
                pending_count=pending_count,
                latest_version=latest_version,
                tampered_versions=tuple(tampered),
                issues=tuple(issues),
                foreign_key_violations=tuple(fk_violation_strings),
            )

            logger.info(
                "Database integrity verification completed",
                event="db_migration_integrity_verified",
                valid=valid,
                applied_count=len(applied),
                tampered_count=len(tampered),
            )
            return report
        finally:
            if managed:
                active_conn.close()
