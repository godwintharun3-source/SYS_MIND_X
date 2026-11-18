"""SQLite database, connection manager, and migration infrastructure for SYSTEM MIND X."""

from system_mind.database.connection import (
    DatabaseConfig,
    DatabaseConnectionManager,
    get_connection,
)
from system_mind.database.entity_models import (
    ApplicationEntityRecord,
    HardwareCategory,
    HardwareEntityRecord,
    OsKernelEntityRecord,
)
from system_mind.database.entity_repo import EntityRepository
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
from system_mind.database.telemetry_repo import TelemetryRepository

__all__ = [
    "ApplicationEntityRecord",
    "AppliedMigrationRecord",
    "DatabaseConfig",
    "DatabaseConnectionManager",
    "DatabaseIntegrityReport",
    "DatabaseMigrator",
    "EntityRepository",
    "HardwareCategory",
    "HardwareEntityRecord",
    "MIGRATIONS_DIR",
    "MigrationDefinition",
    "MigrationDirection",
    "MigrationPlan",
    "MigrationStatus",
    "OsKernelEntityRecord",
    "TelemetryRepository",
    "get_connection",
    "load_migrations_from_directory",
    "parse_sql_migration_file",
    "split_sql_statements",
]
