# DAY 036 — SQLite Database Migration Infrastructure

**Status:** IMPLEMENTED  
**Date:** 2026-11-16  
**Milestone:** Milestone 3 — Repository and development foundation (Days 026–040)  
**System Plane:** Layer 3 (Temporal Digital Twin & Memory), Layer 4 (Knowledge Graph), Layer 6 (Platform Audit Ledger)

---

## 1. Architectural Objective & Context

SYSTEM MIND X relies on embedded, zero-ambient-overhead persistence for local state storage, including temporal digital twin graph nodes and edges (Days 016–017, Days 066–070), immutable audit ledgers (Day 023), application profiles (Days 091–100), and knowledge caches. SQLite is the authoritative embedded relational engine for local storage on developer hosts and deployed platform agents.

To ensure deterministic, reproducible schema evolution across developer environments, testing frameworks, and production daemons, Day 036 establishes a robust, zero-third-party-dependency database migration subsystem (`src/system_mind/database/`) and developer CLI tool (`tools/migrate.py`).

---

## 2. Cardinal Safety & Architectural Invariants

The migration engine enforces five inviolable architectural invariants:

1. **Strict Transactional Atomicity (INV-DB-01):**
   Every migration executes inside an explicit transactional boundary (`BEGIN TRANSACTION ... COMMIT`). If any statement within an upgrade or rollback fails, the transaction is rolled back immediately, ensuring the database schema is never left in an inconsistent or partially migrated state.

2. **Monotonic Sequencing and Gap Prevention (INV-DB-02):**
   Migrations are indexed by strictly monotonic positive integers (`version: int` e.g. `0001`, `0002`). The migrator guarantees that migrations execute in exact sequential order and prevents out-of-order execution.

3. **Cryptographic Checksum Immutability & Drift Detection (INV-DB-03):**
   Every migration definition generates a deterministic SHA-256 checksum computed over its combined UP and DOWN SQL statements. When a migration is applied, its checksum is sealed into the `_schema_migrations` table. During subsequent runs and integrity audits, the migrator recalculates definition checksums and detects any historical tampering or schema drift.

4. **Bidirectional Reversibility (INV-DB-04):**
   Every migration must provide both forward (`up_sql`) and backward (`down_sql`) definitions. Downgrades/rollbacks are first-class operations supported in both programmatic APIs and developer CLI tooling.

5. **Zero Ambient Shell Authority (SC-01 / INV-DB-05):**
   The migration engine operates exclusively through Python's standard library `sqlite3` driver and typed connection managers. No external sqlite binary, shell wrapper, or child process is invoked.

---

## 3. Schema Migrations Ledger (`_schema_migrations`)

All applied migrations are recorded in a dedicated internal metadata table initialized before any migration runs:

```sql
CREATE TABLE IF NOT EXISTS _schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL,
    execution_time_ms REAL NOT NULL
);
```

### Column Invariants:
- `version`: Monotonic integer primary key matching the migration version number.
- `name`: Human-readable identifier describing the migration purpose (e.g. `initial_schema`).
- `applied_at`: ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) when the migration was committed.
- `checksum`: 64-character lowercase hex SHA-256 digest of the canonical migration content.
- `execution_time_ms`: Monotonic floating-point execution time in milliseconds.

---

## 4. Connection Safety & PRAGMA Policies

The SQLite connection manager (`DatabaseConnectionManager`) enforces secure, high-durability PRAGMA configurations on every connection:

- **Foreign Key Enforcement:**
  `PRAGMA foreign_keys = ON;` is executed on every opened connection to guarantee relational referential integrity.
- **Write-Ahead Logging (WAL):**
  For persistent on-disk databases, `PRAGMA journal_mode = WAL;` is enabled to allow concurrent read operations without blocking writes.
- **Safe Synchronous Setting:**
  `PRAGMA synchronous = NORMAL;` is enabled under WAL mode, providing crash resilience while avoiding excessive fsync stalls.
- **Busy Timeout:**
  `PRAGMA busy_timeout = 5000;` (5,000 milliseconds) is configured to handle transient locks gracefully without immediate failure.
- **Row Factory:**
  Connections configure `sqlite3.Row` for typed, dictionary-like column access.

---

## 5. Canonical Initial Schemas (`0001_initial_schema`)

The foundational schema establishes the core relational tables for SYSTEM MIND X:

1. **`audit_events` (Layer 6 Immutable Audit Ledger):**
   Stores append-only audit records with monotonic sequence numbers, cryptographic actor and action URNs, risk tiers, and SHA-256 hash chains (`prev_event_hash`, `payload_hash`, `event_hash`).
2. **`twin_entities` (Layer 3 Digital Twin Graph Nodes):**
   Stores system entities (hardware devices, OS services, applications, files) with ownership classification (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`) and structured JSON attributes.
3. **`twin_relationships` (Layer 3 Digital Twin Graph Edges):**
   Stores directed relationships between entities (`RUNS_ON`, `DEPENDS_ON`, `OWNS`, etc.) with foreign keys enforcing cascading cleanup on entity removal.
4. **`temporal_observations` (Layer 3 Temporal Observation Store):**
   Stores raw point-in-time sensor telemetry with sequence ordering, source identifiers, payload digests, and provenance verification status.

---

## 6. Migration Subsystem Architecture

The subsystem in `src/system_mind/database/` comprises:

- **`connection.py`**:
  `DatabaseConfig`, `DatabaseConnectionManager`, and the `transaction(conn)` context manager.
- **`models.py`**:
  Typed domain models: `MigrationDefinition`, `AppliedMigrationRecord`, `MigrationPlan`, `DatabaseIntegrityReport`, `MigrationDirection`, and `MigrationStatus`.
- **`migrator.py`**:
  `DatabaseMigrator` providing:
  - `initialize_schema_table(conn)`: Idempotently creates `_schema_migrations`.
  - `get_applied_migrations(conn)`: Returns applied records ordered by version.
  - `plan(direction, target_version)`: Dry-run planning without database mutations.
  - `apply_all()`: Applies all pending migrations in monotonic order within individual transactions.
  - `apply_migration(version)`: Applies a specific single migration.
  - `rollback_last()`: Safely rolls back the most recent applied migration.
  - `rollback_to(target_version)`: Reverts migrations down to the specified target.
  - `verify_integrity()`: Audits applied checksums, checks for skipped versions, and runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
- **`migrations/`**:
  Canonical migration registry containing `0001_initial_schema`.

---

## 7. Developer Tooling & Packaging Verification

1. **`tools/migrate.py` CLI:**
   Provides an unprivileged operator interface:
   - `python3 tools/migrate.py status`: Reports applied/pending counts and current schema version.
   - `python3 tools/migrate.py plan`: Previews pending actions without execution.
   - `python3 tools/migrate.py apply`: Executes pending forward migrations.
   - `python3 tools/migrate.py rollback`: Rolls back the latest applied migration.
   - `python3 tools/migrate.py verify`: Validates database checksums and foreign key integrity.
2. **`src/system_mind/packaging/database_migration.py`:**
   `DatabaseMigrationValidator` verifies that:
   - All migrations are strictly monotonic without number collisions.
   - Every migration has non-empty UP and DOWN SQL.
   - Full migration round-trip lifecycle (`apply` -> `rollback` -> `re-apply`) succeeds on fresh SQLite instance.
   - Tamper detection triggers when migration SQL is altered post-application.
   - PRAGMA checks pass cleanly with zero corruption.
