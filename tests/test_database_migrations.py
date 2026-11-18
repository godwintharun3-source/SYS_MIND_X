"""Unit, integration, and contract tests for SQLite database migration infrastructure."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import pytest

from system_mind.database.connection import (
    DatabaseConfig,
    DatabaseConnectionManager,
    get_connection,
)
from system_mind.database.migrations import (
    MIGRATIONS_DIR,
    load_migrations_from_directory,
    parse_sql_migration_file,
)
from system_mind.database.migrator import DatabaseMigrator, split_sql_statements
from system_mind.database.models import (
    AppliedMigrationRecord,
    DatabaseIntegrityReport,
    MigrationDefinition,
    MigrationDirection,
    MigrationPlan,
    MigrationStatus,
)
from system_mind.packaging.database_migration import DatabaseMigrationValidator


@pytest.mark.unit
def test_migration_definition_checksum_computation_and_invariants() -> None:
    """Verifies MigrationDefinition validation, immutability, and deterministic checksum computation."""
    up_sql = "CREATE TABLE users (id INT PRIMARY KEY);"
    down_sql = "DROP TABLE users;"

    expected_checksum = MigrationDefinition.compute_checksum(up_sql, down_sql)
    assert len(expected_checksum) == 64

    migration = MigrationDefinition(
        version=1,
        name="create_users",
        up_sql=up_sql,
        down_sql=down_sql,
    )
    assert migration.checksum == expected_checksum
    assert migration.version == 1
    assert migration.name == "create_users"

    # Checksum mismatch should raise ValueError
    with pytest.raises(ValueError, match="Checksum mismatch"):
        MigrationDefinition(
            version=1,
            name="create_users",
            up_sql=up_sql,
            down_sql=down_sql,
            checksum="bad_checksum_hash",
        )

    # Invalid version <= 0
    with pytest.raises(ValueError, match="positive integer"):
        MigrationDefinition(
            version=0,
            name="invalid_ver",
            up_sql=up_sql,
            down_sql=down_sql,
        )

    # Empty up_sql
    with pytest.raises(ValueError, match="up_sql must not be empty"):
        MigrationDefinition(
            version=1,
            name="empty_up",
            up_sql="   ",
            down_sql=down_sql,
        )

    # Empty down_sql (non-reversible)
    with pytest.raises(ValueError, match="down_sql must not be empty"):
        MigrationDefinition(
            version=1,
            name="empty_down",
            up_sql=up_sql,
            down_sql="   ",
        )


@pytest.mark.unit
def test_sql_statement_splitter() -> None:
    """Verifies that split_sql_statements cleanly handles comments, semicolons, and quotes."""
    script = """
    -- Leading comment
    CREATE TABLE items (
        id INT PRIMARY KEY,
        label TEXT NOT NULL
    );
    -- Insert statements
    INSERT INTO items VALUES (1, 'val; with semicolon');
    INSERT INTO items VALUES (2, 'val with ''quoted'' word');
    """
    stmts = split_sql_statements(script)
    assert len(stmts) == 3
    assert stmts[0].startswith("CREATE TABLE items")
    assert "val; with semicolon" in stmts[1]
    assert "val with ''quoted'' word" in stmts[2]


@pytest.mark.unit
def test_load_migrations_from_canonical_directory() -> None:
    """Verifies loading canonical migrations from MIGRATIONS_DIR."""
    migrations = load_migrations_from_directory(MIGRATIONS_DIR)
    assert len(migrations) >= 2

    # Check monotonic versions starting at 1
    versions = [m.version for m in migrations]
    assert versions == list(range(1, len(migrations) + 1))

    m1 = migrations[0]
    assert m1.version == 1
    assert m1.name == "initial_schema"
    assert "audit_events" in m1.up_sql
    assert "twin_entities" in m1.up_sql
    assert "twin_relationships" in m1.up_sql
    assert "temporal_observations" in m1.up_sql
    assert "DROP TABLE IF EXISTS audit_events" in m1.down_sql


@pytest.mark.unit
def test_connection_manager_pragmas_and_transactions() -> None:
    """Verifies that DatabaseConnectionManager enforces foreign keys and transaction boundaries."""
    conn = get_connection(":memory:")
    try:
        # Check foreign keys
        fk_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert fk_enabled == 1

        # Check busy timeout
        timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert timeout == 5000

        # Test transaction commit
        conn.execute("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT);")
        with DatabaseConnectionManager.transaction(conn):
            conn.execute("INSERT INTO kv VALUES ('key1', 'val1');")

        row = conn.execute("SELECT v FROM kv WHERE k = 'key1';").fetchone()
        assert row["v"] == "val1"

        # Test transaction rollback on exception
        with pytest.raises(RuntimeError):
            with DatabaseConnectionManager.transaction(conn):
                conn.execute("INSERT INTO kv VALUES ('key2', 'val2');")
                raise RuntimeError("Simulated failure")

        row2 = conn.execute("SELECT v FROM kv WHERE k = 'key2';").fetchone()
        assert row2 is None
    finally:
        conn.close()


@pytest.mark.integration
def test_migrator_schema_table_initialization_and_empty_state() -> None:
    """Verifies that DatabaseMigrator initializes tracking ledger and reports empty applied list."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    try:
        migrator.initialize_schema_table(conn)
        applied = migrator.get_applied_migrations(conn)
        assert applied == []

        plan = migrator.plan(MigrationDirection.UP, conn=conn)
        assert not plan.is_noop
        assert len(plan.migrations) >= 2
    finally:
        conn.close()


@pytest.mark.integration
def test_migrator_forward_application_and_monotonicity() -> None:
    """Verifies forward migration execution, record creation, and monotonic enforcement."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    try:
        # Apply migration 1
        rec1 = migrator.apply_migration(1, conn=conn)
        assert rec1.version == 1
        assert rec1.name == "initial_schema"
        assert rec1.execution_time_ms >= 0.0

        applied = migrator.get_applied_migrations(conn)
        assert len(applied) == 1
        assert applied[0].version == 1

        # Applying migration 1 again should fail
        with pytest.raises(ValueError, match="already applied"):
            migrator.apply_migration(1, conn=conn)

        # Applying non-existent version should fail
        with pytest.raises(ValueError, match="not registered"):
            migrator.apply_migration(999, conn=conn)

        # Apply migration 2
        rec2 = migrator.apply_migration(2, conn=conn)
        assert rec2.version == 2
        assert rec2.name == "add_component_ownership_indices"

        applied2 = migrator.get_applied_migrations(conn)
        assert len(applied2) == 2
    finally:
        conn.close()


@pytest.mark.integration
def test_migrator_transactional_atomicity_on_statement_failure() -> None:
    """Verifies that an error in any migration statement causes complete rollback without tracking."""
    failing_migration = MigrationDefinition(
        version=1,
        name="failing_migration",
        up_sql="""
        CREATE TABLE ok_table (id INT PRIMARY KEY);
        CREATE TABLE ok_table (id INT PRIMARY KEY); -- duplicate table causes error
        """,
        down_sql="DROP TABLE IF EXISTS ok_table;",
    )

    migrator = DatabaseMigrator(
        db_path=":memory:",
        custom_migrations=[failing_migration],
    )
    conn = migrator._get_connection()
    try:
        with pytest.raises(sqlite3.OperationalError, match="already exists"):
            migrator.apply_migration(1, conn=conn)

        # Verify that ok_table was rolled back
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ok_table';"
        ).fetchall()
        assert len(tables) == 0

        # Verify that _schema_migrations does NOT contain version 1
        applied = migrator.get_applied_migrations(conn)
        assert len(applied) == 0
    finally:
        conn.close()


@pytest.mark.integration
def test_migrator_rollback_last_and_rollback_to() -> None:
    """Verifies rollback of latest migration and rollback to target version."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    try:
        # Apply all migrations
        migrator.apply_all(conn=conn)
        applied = migrator.get_applied_migrations(conn)
        assert len(applied) >= 2
        latest_ver = max(m.version for m in applied)

        # Rollback last migration
        rolled_back = migrator.rollback_last(conn=conn)
        assert rolled_back is not None
        assert rolled_back.version == latest_ver

        applied_after_1 = migrator.get_applied_migrations(conn)
        assert len(applied_after_1) == len(applied) - 1

        # Rollback down to 0
        rolled_back_all = migrator.rollback_to(0, conn=conn)
        assert len(rolled_back_all) == len(applied_after_1)

        applied_after_all = migrator.get_applied_migrations(conn)
        assert len(applied_after_all) == 0

        # Tables from version 1 should be dropped
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('audit_events', 'twin_entities');"
        ).fetchall()
        assert len(tables) == 0
    finally:
        conn.close()


@pytest.mark.integration
def test_foreign_key_referential_integrity_and_cascade() -> None:
    """Verifies that relational foreign keys and ON DELETE CASCADE are active."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    try:
        migrator.apply_all(conn=conn)

        # Insert parent entity
        conn.execute(
            """
            INSERT INTO twin_entities (entity_id, entity_type, ownership, observed_at, attributes_json)
            VALUES ('ent-1', 'SERVICE', 'SYSTEM_MANAGED', '2026-11-16T12:00:00Z', '{}');
            """
        )
        conn.execute(
            """
            INSERT INTO twin_entities (entity_id, entity_type, ownership, observed_at, attributes_json)
            VALUES ('ent-2', 'PROCESS', 'SYSTEM_MANAGED', '2026-11-16T12:00:00Z', '{}');
            """
        )

        # Insert child relationship
        conn.execute(
            """
            INSERT INTO twin_relationships (relationship_id, source_id, target_id, relation_type, created_at, metadata_json)
            VALUES ('rel-1', 'ent-1', 'ent-2', 'SPAWNS', '2026-11-16T12:00:00Z', '{}');
            """
        )

        # Inserting relationship pointing to non-existent target should fail
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            conn.execute(
                """
                INSERT INTO twin_relationships (relationship_id, source_id, target_id, relation_type, created_at, metadata_json)
                VALUES ('rel-bad', 'ent-1', 'ent-nonexistent', 'DEPENDS_ON', '2026-11-16T12:00:00Z', '{}');
                """
            )

        # Delete parent entity ent-2; should cascade and delete rel-1
        conn.execute("DELETE FROM twin_entities WHERE entity_id = 'ent-2';")
        rel = conn.execute("SELECT * FROM twin_relationships WHERE relationship_id = 'rel-1';").fetchone()
        assert rel is None
    finally:
        conn.close()


@pytest.mark.contract
def test_migrator_checksum_tamper_detection() -> None:
    """Verifies that modifying migration SQL after application triggers tamper detection."""
    m1 = MigrationDefinition(
        version=1,
        name="initial_state",
        up_sql="CREATE TABLE dummy (id INT PRIMARY KEY);",
        down_sql="DROP TABLE dummy;",
    )
    migrator = DatabaseMigrator(db_path=":memory:", custom_migrations=[m1])
    conn = migrator._get_connection()
    try:
        migrator.apply_all(conn=conn)
        clean_report = migrator.verify_integrity(conn=conn)
        assert clean_report.valid is True
        assert len(clean_report.tampered_versions) == 0

        # Simulate tampering by loading an altered definition
        m1_tampered = MigrationDefinition(
            version=1,
            name="initial_state",
            up_sql="CREATE TABLE dummy (id INT PRIMARY KEY); -- altered",
            down_sql="DROP TABLE dummy;",
        )
        tamper_migrator = DatabaseMigrator(db_path=":memory:", custom_migrations=[m1_tampered])
        tamper_report = tamper_migrator.verify_integrity(conn=conn)

        assert tamper_report.valid is False
        assert 1 in tamper_report.tampered_versions
        assert any("Tampered migration" in issue for issue in tamper_report.issues)
    finally:
        conn.close()


@pytest.mark.contract
def test_database_migration_validator_audits_clean() -> None:
    """Verifies that DatabaseMigrationValidator passes clean on repository migration set."""
    result = DatabaseMigrationValidator.audit(MIGRATIONS_DIR)
    assert result.valid is True
    assert result.migration_count >= 2
    assert result.latest_version >= 2
    assert result.lifecycle_roundtrip_ok is True
    assert len(result.issues) == 0


@pytest.mark.integration
def test_migrate_cli_end_to_end(tmp_path: Path) -> None:
    """Verifies the tools/migrate.py CLI commands (plan, apply, status, verify, rollback)."""
    db_file = tmp_path / "test_cli.db"
    cli_path = Path(__file__).resolve().parent.parent / "tools" / "migrate.py"

    # 1. Plan
    res = subprocess.run(
        [sys.executable, str(cli_path), "--db", str(db_file), "--json", "plan"],
        capture_output=True,
        text=True,
        check=True,
    )
    plan_data = json.loads(res.stdout)
    assert plan_data["direction"] == "UP"
    assert len(plan_data["migrations"]) >= 2

    # 2. Apply
    res = subprocess.run(
        [sys.executable, str(cli_path), "--db", str(db_file), "--json", "apply"],
        capture_output=True,
        text=True,
        check=True,
    )
    apply_data = json.loads(res.stdout)
    assert len(apply_data["applied"]) >= 2

    # 3. Status
    res = subprocess.run(
        [sys.executable, str(cli_path), "--db", str(db_file), "--json", "status"],
        capture_output=True,
        text=True,
        check=True,
    )
    status_data = json.loads(res.stdout)
    assert status_data["applied_count"] >= 2
    assert status_data["pending_count"] == 0
    assert status_data["integrity_valid"] is True

    # 4. Verify
    res = subprocess.run(
        [sys.executable, str(cli_path), "--db", str(db_file), "--json", "verify"],
        capture_output=True,
        text=True,
        check=True,
    )
    verify_data = json.loads(res.stdout)
    assert verify_data["valid"] is True

    # 5. Rollback
    res = subprocess.run(
        [sys.executable, str(cli_path), "--db", str(db_file), "--json", "rollback"],
        capture_output=True,
        text=True,
        check=True,
    )
    rollback_data = json.loads(res.stdout)
    assert len(rollback_data["rolled_back"]) == 1
    assert rollback_data["rolled_back"][0]["version"] == len(apply_data["applied"])
