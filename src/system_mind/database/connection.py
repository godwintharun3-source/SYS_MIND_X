"""SQLite connection factory, safe PRAGMA configurations, and transactional context managers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Generator


@dataclass(frozen=True)
class DatabaseConfig:
    """Configuration options for SQLite database connections."""

    db_path: str = ":memory:"
    foreign_keys: bool = True
    wal_mode: bool = True
    busy_timeout_ms: int = 5000

    @property
    def is_memory(self) -> bool:
        """Checks if the connection targets an in-memory SQLite database."""
        return self.db_path == ":memory:" or self.db_path.startswith("file::memory:")


class DatabaseConnectionManager:
    """Manages SQLite connections with secure defaults and durability PRAGMAs."""

    @staticmethod
    def connect(config: DatabaseConfig | None = None) -> sqlite3.Connection:
        """Opens and configures an SQLite database connection."""
        cfg = config or DatabaseConfig()

        if not cfg.is_memory:
            db_file = Path(cfg.db_path).resolve()
            db_file.parent.mkdir(parents=True, exist_ok=True)
            target = str(db_file)
        else:
            target = cfg.db_path

        # autocommit=False / isolation_level=None allows explicit transaction management
        conn = sqlite3.connect(
            target,
            timeout=cfg.busy_timeout_ms / 1000.0,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row

        # Enforce referential integrity
        if cfg.foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON;")

        # Set lock contention timeout
        conn.execute(f"PRAGMA busy_timeout = {int(cfg.busy_timeout_ms)};")

        # WAL mode is only valid for persistent filesystem databases
        if not cfg.is_memory and cfg.wal_mode:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")

        return conn

    @staticmethod
    @contextmanager
    def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
        """Context manager executing block inside an explicit transaction."""
        conn.execute("BEGIN IMMEDIATE;")
        try:
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise


def get_connection(
    db_path: str = ":memory:",
    foreign_keys: bool = True,
    wal_mode: bool = True,
    busy_timeout_ms: int = 5000,
) -> sqlite3.Connection:
    """Convenience helper to create a configured SQLite connection."""
    config = DatabaseConfig(
        db_path=db_path,
        foreign_keys=foreign_keys,
        wal_mode=wal_mode,
        busy_timeout_ms=busy_timeout_ms,
    )
    return DatabaseConnectionManager.connect(config)
