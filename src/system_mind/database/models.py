"""Data models, enums, and structures for SQLite database migrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib


class MigrationStatus(str, Enum):
    """Execution status of a database migration."""

    PENDING = "PENDING"
    APPLIED = "APPLIED"
    ROLLED_BACK = "ROLLED_BACK"
    TAMPERED = "TAMPERED"


class MigrationDirection(str, Enum):
    """Direction of a migration operation."""

    UP = "UP"
    DOWN = "DOWN"


@dataclass(frozen=True)
class MigrationDefinition:
    """Specification of a reversible database migration."""

    version: int
    name: str
    up_sql: str
    down_sql: str
    checksum: str = field(default="")

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise ValueError(f"Migration version must be a positive integer, got: {self.version}")
        if not self.name.strip():
            raise ValueError("Migration name must not be empty.")
        if not self.up_sql.strip():
            raise ValueError("Migration up_sql must not be empty.")
        if not self.down_sql.strip():
            raise ValueError("Migration down_sql must not be empty (migrations must be reversible).")

        expected_checksum = self.compute_checksum(self.up_sql, self.down_sql)
        if not self.checksum:
            object.__setattr__(self, "checksum", expected_checksum)
        elif self.checksum != expected_checksum:
            raise ValueError(
                f"Checksum mismatch for migration {self.version:04d}_{self.name}: "
                f"provided {self.checksum}, expected {expected_checksum}"
            )

    @staticmethod
    def compute_checksum(up_sql: str, down_sql: str) -> str:
        """Computes deterministic SHA-256 digest over normalized migration SQL."""
        content = f"UP:\n{up_sql.strip()}\nDOWN:\n{down_sql.strip()}".encode("utf-8")
        return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class AppliedMigrationRecord:
    """Record of an applied database migration stored in the database."""

    version: int
    name: str
    applied_at: str
    checksum: str
    execution_time_ms: float

    def to_dict(self) -> dict[str, object]:
        """Converts to dictionary for logging and serialization."""
        return {
            "version": self.version,
            "name": self.name,
            "applied_at": self.applied_at,
            "checksum": self.checksum,
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


@dataclass(frozen=True)
class MigrationPlan:
    """Execution plan previewing pending migration operations."""

    direction: MigrationDirection
    target_version: int | None
    migrations: tuple[MigrationDefinition, ...]
    is_noop: bool

    def summary(self) -> str:
        """Returns human-readable summary of the plan."""
        if self.is_noop:
            return f"Plan: No-op ({self.direction.value} - database already at target state)."
        versions = ", ".join(f"{m.version:04d}_{m.name}" for m in self.migrations)
        return f"Plan: {self.direction.value} {len(self.migrations)} migration(s) [{versions}]"


@dataclass(frozen=True)
class DatabaseIntegrityReport:
    """Audit report for database schema and migration ledger integrity."""

    valid: bool
    applied_count: int
    pending_count: int
    latest_version: int | None
    tampered_versions: tuple[int, ...] = ()
    issues: tuple[str, ...] = ()
    foreign_key_violations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Converts audit report to dictionary."""
        return {
            "valid": self.valid,
            "applied_count": self.applied_count,
            "pending_count": self.pending_count,
            "latest_version": self.latest_version,
            "tampered_versions": list(self.tampered_versions),
            "issues": list(self.issues),
            "foreign_key_violations": list(self.foreign_key_violations),
        }
