# Design Note: Day 070 — Implement Append-Only System Event Storage

## 1. Architectural Context & Motivation
Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X.
- **Day 066:** Formalized canonical URN entity identifiers (`urn:systemmind:<domain>:<qualifier>`).
- **Day 067:** Created relational database schemas for physical hardware, operating systems, and installed applications.
- **Day 068:** Created graph-node and graph-edge persistence models for directed property graph topology.
- **Day 069:** Implemented timestamped system observation records (`system_observation_records`) capturing state snapshots and deltas.
- **Day 070:** Establishes the foundational **append-only system event storage** (`system_events`) bridging real-time OS state transitions with immutable event-sourcing ledgers.

In an AI-native operating system and governance architecture, system events represent discrete occurrences or lifecycle transitions across hardware, software, processes, files, and networks (e.g. `PROCESS_SPAWNED`, `APP_INSTALLED`, `FILE_MODIFIED`, `NETWORK_INTERFACE_STATE`). To guarantee auditability, forensic fidelity, and state reconstruction:
1. **Append-Only Immutability:** Once committed, system events must never be altered or deleted. Compensating events must be appended rather than mutating historical records. This is enforced directly at the SQLite engine level using database triggers.
2. **Cryptographic Hash Chaining:** Each event links to the cryptographic hash of the previous event (`prev_event_hash`) and computes an immutable block hash (`event_hash`), creating an unbroken tamper-evident ledger across the entire event stream.
3. **Causality & Correlation Tracking:** Events capture distributed transaction tokens (`correlation_id`) and parent event identifiers (`causation_id`) to trace causal relationships across asynchronous subsystem boundaries.
4. **Tripartite Ownership Partitioning:** Every event records explicit `ComponentOwnership` (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`) to isolate user-managed applications and projects.
5. **Universal Safety Invariant (`SC-03`):** Strict structural enforcement that event logging never asserts software safety (`scan_proves_safe = False`).

---

## 2. Relational Schema Architecture

The system event persistence schema is introduced via migration `0006_system_events_storage.sql`.

```
+---------------------------------------------------------------------------------------------------------+
|                          SYSTEM MIND X — Append-Only System Event Storage Schema                        |
+---------------------------------------------------------------------------------------------------------+

  +----------------------------------------------------------------------------------------------------+
  |                                            system_events                                           |
  +----------------------------------------------------------------------------------------------------+
  | sequence_number            | INTEGER PRIMARY KEY AUTOINCREMENT (Monotonic global sequence)         |
  | event_id                   | TEXT UNIQUE NOT NULL (Canonical event UUID, indexed)                  |
  | device_id                  | TEXT NOT NULL (RFC 4122 UUIDv5 device identifier)                     |
  | entity_urn                 | TEXT NOT NULL (Primary entity affected or generating event, indexed)  |
  | event_type                 | TEXT NOT NULL (PROCESS_SPAWNED, APP_INSTALLED, FILE_CHANGED, indexed) |
  | timestamp_iso              | TEXT NOT NULL (ISO 8601 UTC timestamp)                               |
  | timestamp_epoch_ms         | INTEGER NOT NULL (Unix epoch milliseconds, indexed)                   |
  | correlation_id             | TEXT (Optional distributed tracing correlation token, indexed)        |
  | causation_id               | TEXT (Optional parent event ID that caused this occurrence)           |
  | prev_event_hash            | TEXT NOT NULL (Cryptographic SHA-256 hash of previous event)          |
  | payload_sha256             | TEXT NOT NULL (Deterministic SHA-256 hash of payload_json)            |
  | event_hash                 | TEXT NOT NULL (Cryptographic block digest sealing this record)        |
  | payload_json               | TEXT NOT NULL (Canonical JSON payload of event attributes)            |
  | metadata_json              | TEXT NOT NULL DEFAULT '{}' (Extensible metadata, subsystem, tags)     |
  | component_ownership        | TEXT NOT NULL (SYSTEM_MANAGED, VENDOR_MANAGED, USER_MANAGED, indexed) |
  | scan_proves_safe           | INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)               |
  +----------------------------------------------------------------------------------------------------+

  Database Triggers:
  - trg_system_events_prevent_update: Rejects any UPDATE on system_events via RAISE(ABORT).
  - trg_system_events_prevent_delete: Rejects any DELETE on system_events via RAISE(ABORT).
```

---

## 3. Mandatory Safety & Architectural Invariants

1. **Append-Only Immutability (`INV-EVT-01`):** System events cannot be mutated or deleted. Both database-level SQLite triggers and application store methods raise immediate errors if mutation or deletion is attempted.
2. **Cryptographic Hash-Chain Integrity (`INV-EVT-02`):** Genesis event has `prev_event_hash = "0" * 64`. Every subsequent event seals the cryptographic digest of its predecessor:
   $$\text{event\_hash} = \text{SHA256}(\text{prev\_hash} : \text{seq} : \text{event\_id} : \text{timestamp\_iso} : \text{entity\_urn} : \text{event\_type} : \text{payload\_sha256})$$
   Any out-of-order insertion, record alteration, or deletion invalidates the chain.
3. **Component Ownership Isolation (`INV-EVT-03`):** Every event records explicit `ComponentOwnership`, ensuring distinct governance policies for user software versus system components.
4. **Universal "Scan != Safe" Invariant (`INV-EVT-04` / `SC-03`):** Enforced at both SQLite database check constraint level (`CHECK (scan_proves_safe = 0)`) and Python dataclass validation (`scan_proves_safe: bool = False`). Recording an event reflects system observation, never software trustworthiness.
5. **Monotonic Sequential Progression (`INV-EVT-05`):** Events maintain contiguous, strictly increasing global sequence numbers.
6. **Correlation & Causality Tracking (`INV-EVT-06`):** Supports distributed tracing across digital twin subsystems via `correlation_id` and `causation_id`.
7. **Zero Ambient Shell Authority (`SC-01` / `INV-EVT-07`):** All store interactions execute via parameterized SQL with `sqlite3` without spawning ambient shell processes.

---

## 4. Verification and Developer Tooling
- **Packaging Validator:** `SystemEventsValidator` auditing table schema, check constraints, database triggers, AST safety, and hash chain verification.
- **Developer CLI Utility:** `tools/detect_system_events.py` supporting `--audit`, event seeding, tamper detection, trigger rejection demonstrations, and chronological queries.
- **Polyglot Test Suite:** `tests/test_system_event_storage.py` covering schema migrations, trigger enforcement, hash-chain integrity, query filtering, and charter invariants.
