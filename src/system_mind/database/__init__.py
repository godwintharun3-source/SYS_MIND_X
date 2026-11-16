"""SQLite database, connection manager, and migration infrastructure for SYSTEM MIND X."""

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

__all__ = [
    "DatabaseConfig",
    "DatabaseConnectionManager",
    "get_connection",
    "MIGRATIONS_DIR",
    "load_migrations_from_directory",
    "parse_sql_migration_file",
    "DatabaseMigrator",
    "split_sql_statements",
    "AppliedMigrationRecord",
    "DatabaseIntegrityReport",
    "MigrationDefinition",
    "MigrationDirection",
    "MigrationPlan",
    "MigrationStatus",
]
