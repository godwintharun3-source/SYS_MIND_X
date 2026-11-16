"""Canonical SQLite migrations and migration file loader for SYSTEM MIND X."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Sequence

from system_mind.database.models import MigrationDefinition

MIGRATIONS_DIR = Path(__file__).resolve().parent
FILENAME_PATTERN = re.compile(r"^(\d+)_([a-zA-Z0-9_]+)\.sql$")


def parse_sql_migration_file(file_path: Path) -> MigrationDefinition:
    """Parses a bidirectional SQLite migration SQL file containing -- UP and -- DOWN markers."""
    match = FILENAME_PATTERN.match(file_path.name)
    if not match:
        raise ValueError(
            f"Invalid migration filename format '{file_path.name}'. Expected '0001_name.sql'."
        )

    version = int(match.group(1))
    name = match.group(2)

    content = file_path.read_text(encoding="utf-8")
    up_idx = content.find("-- UP")
    down_idx = content.find("-- DOWN")

    if up_idx == -1 or down_idx == -1:
        raise ValueError(
            f"Migration file '{file_path.name}' must contain both '-- UP' and '-- DOWN' markers."
        )

    if up_idx >= down_idx:
        raise ValueError(
            f"Migration file '{file_path.name}' has '-- UP' section after '-- DOWN' section."
        )

    up_sql = content[up_idx + len("-- UP") : down_idx].strip()
    down_sql = content[down_idx + len("-- DOWN") :].strip()

    if not up_sql:
        raise ValueError(f"Migration file '{file_path.name}' has empty UP section.")
    if not down_sql:
        raise ValueError(f"Migration file '{file_path.name}' has empty DOWN section.")

    return MigrationDefinition(
        version=version,
        name=name,
        up_sql=up_sql,
        down_sql=down_sql,
    )


def load_migrations_from_directory(directory: Path | None = None) -> list[MigrationDefinition]:
    """Loads and sorts all migration definitions from a directory."""
    target_dir = directory or MIGRATIONS_DIR
    if not target_dir.exists():
        return []

    migrations: list[MigrationDefinition] = []
    sql_files = sorted(target_dir.glob("*.sql"), key=lambda p: p.name)

    for sql_file in sql_files:
        if FILENAME_PATTERN.match(sql_file.name):
            migrations.append(parse_sql_migration_file(sql_file))

    # Validate monotonic sequence
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError(f"Duplicate migration versions detected in {target_dir}: {versions}")

    return migrations


__all__ = [
    "MIGRATIONS_DIR",
    "FILENAME_PATTERN",
    "parse_sql_migration_file",
    "load_migrations_from_directory",
]
