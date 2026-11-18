# Design Note: Day 069 — Implement Timestamped System Observation Records

## 1. Architectural Context & Motivation
Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X.
- **Day 066:** Formalized canonical URN entity identifiers (`urn:systemmind:<domain>:<qualifier>`).
- **Day 067:** Created relational database schemas for physical hardware, operating systems, and installed applications.
- **Day 068:** Created graph-node and graph-edge persistence models for directed property graph topology.
- **Day 069:** Establishes durable, high-resolution, **timestamped system observation records** bridging telemetry collection pipelines with persistent temporal storage.

In computer governance and temporal system modeling, observation records are discrete, timestamped assertions of an entity's physical or logical state captured by a telemetry collector. To maintain full provenance, auditability, and temporal fidelity across restarts, observation records require:
1. **Dual Time Anchoring:** Standard UTC ISO 8601 wall-clock timestamps (`observed_at_iso`) paired with millisecond Unix epoch integers (`observed_at_epoch_ms`) for high-speed chronological range indexing, alongside optional monotonic nanosecond counts (`source_monotonic_ns`) to eliminate clock-skew anomalies.
2. **Entity URN Binding:** Direct association with stable canonical URNs (`entity_urn`) defined in Day 066 and device IDs (`device_id`).
3. **Bounded Confidence & Provenance Tiering:** Mathematical confidence bounds (`0.0 <= score <= 1.0`), authority tiering (`KERNEL_AUTHORITATIVE`, `SUBSYSTEM_VERIFIED`, etc.), and provenance verification status (`VERIFIED_KERNEL`, `VERIFIED_BROKER`, `SYNTHETIC_TEST`).
4. **Cryptographic Payload Sealing:** Deterministic SHA-256 digesting of canonical JSON payloads to ensure tamper detection.
5. **Universal Safety Invariant (`SC-03`):** Strict structural enforcement that observation collection never asserts software safety (`scan_proves_safe = False`).

---

## 2. Relational Schema Architecture

The observation persistence schema is introduced via migration `0005_system_observation_records.sql`.

```
+---------------------------------------------------------------------------------------------------------+
|                        SYSTEM MIND X — System Observation Records Relational Schema                      |
+---------------------------------------------------------------------------------------------------------+

  +----------------------------------------------------------------------------------------------------+
  |                                     system_observation_records                                     |
  +----------------------------------------------------------------------------------------------------+
  | record_id                  | TEXT PRIMARY KEY (e.g. obs-<uuid4> or urn:systemmind:obs:<uuid4>)     |
  | device_id                  | TEXT NOT NULL (RFC 4122 UUIDv5 device identifier)                     |
  | entity_urn                 | TEXT NOT NULL (Canonical entity URN, indexed)                         |
  | collector_id               | TEXT NOT NULL (Origin sensor/collector identifier, indexed)           |
  | observation_type           | TEXT NOT NULL (STATE_SNAPSHOT, ATTRIBUTE_DELTA, LIFECYCLE_EVENT, ...)  |
  | observed_at_iso            | TEXT NOT NULL (ISO 8601 UTC timestamp, indexed)                      |
  | observed_at_epoch_ms       | INTEGER NOT NULL (Unix epoch milliseconds, indexed)                   |
  | source_monotonic_ns        | INTEGER (Optional mach_continuous_time nanoseconds)                   |
  | source_clock               | TEXT NOT NULL DEFAULT 'mach_continuous_time'                          |
  | confidence_score           | REAL NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0) |
  | confidence_tier            | TEXT NOT NULL (KERNEL_AUTHORITATIVE, SUBSYSTEM_VERIFIED, ...)         |
  | provenance_status          | TEXT NOT NULL (VERIFIED_KERNEL, VERIFIED_BROKER, ...)                 |
  | sequence_number            | INTEGER NOT NULL (Monotonic sequence per entity, indexed)             |
  | payload_sha256             | TEXT NOT NULL (Deterministic SHA-256 hash of payload_json)            |
  | payload_json               | TEXT NOT NULL (Canonical JSON representation of observed state)       |
  | metadata_json              | TEXT NOT NULL DEFAULT '{}' (Extensible metadata, latency, penalties)  |
  | ttl_seconds                | REAL NOT NULL DEFAULT 60.0 (Freshness validity window)                |
  | is_mock                    | INTEGER NOT NULL DEFAULT 0 CHECK (is_mock IN (0, 1))                  |
  | observation_status         | TEXT NOT NULL DEFAULT 'ACTUAL' (ACTUAL, MOCK, DEGRADED, UNSUPPORTED)   |
  | scan_proves_safe           | INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)               |
  +----------------------------------------------------------------------------------------------------+
```

### Relational Features:
1. **Composite Chronological Indexing:** Index `idx_obs_records_entity_seq` on `(entity_urn, sequence_number)` provides fast sequential ordering per entity.
2. **Temporal Window Indexing:** Indices on `observed_at_iso` and `observed_at_epoch_ms` support millisecond-level range scans and historical point-in-time state reconstruction.
3. **Data Integrity & Bounded Checks:** SQLite check constraints enforce `0.0 <= confidence_score <= 1.0`, binary flags (`is_mock IN (0, 1)`), and non-negotiable `scan_proves_safe = 0`.

---

## 3. Mandatory Safety & Architectural Invariants

1. **Canonical Entity & Device Scoping (`INV-OBS-01`):** Every observation record must bind a valid entity URN conforming to `urn:systemmind:<domain>:<qualifier>` and an anchored RFC 4122 device UUID.
2. **Dual-Clock High-Resolution Time Anchoring (`INV-OBS-02`):** Every record captures both UTC ISO 8601 wall-clock time and integer epoch milliseconds (`observed_at_epoch_ms`), with optional monotonic nanoseconds.
3. **Bounded Confidence & Provenance Tiering (`INV-OBS-03`):** `0.0 <= confidence_score <= 1.0` is strictly enforced in SQLite schema and Python dataclass; authority tier must align with source provenance (synthetic fixtures must be `ESTIMATED_MOCK` or `SYNTHETIC_TEST` with `is_mock=1`).
4. **Universal "Scan != Safe" Invariant (`INV-OBS-04` / `SC-03`):** Structurally enforced at database schema check constraint (`CHECK (scan_proves_safe = 0)`) and dataclass validation (`scan_proves_safe: bool = False`). Telemetry collection captures system observations, never software safety.
5. **Payload Integrity & Cryptographic Provenance (`INV-OBS-05`):** `payload_sha256` must match the deterministic SHA-256 digest of canonical JSON payload bytes.
6. **Monotonic Sequence Enforcement (`INV-OBS-06`):** For any given `entity_urn`, subsequent observations must increment `sequence_number` monotonically.
7. **Zero Ambient Shell Authority (`SC-01` / `INV-OBS-07`):** All repository and manager interactions execute via parameterized SQL with `sqlite3` without spawning ambient shell processes.

---

## 4. Verification and Developer Tooling
- **Packaging Validator:** `SystemObservationValidator` auditing table schema, check constraints, indexes, AST safety, and model round-tripping.
- **Developer CLI Utility:** `tools/detect_system_observations.py` supporting `--audit`, record seeding, chronological querying, and state reconstruction.
- **Polyglot Test Suite:** `tests/test_system_observation_records.py` covering schema migrations, validation, sequence monotonicity, point-in-time state reconstruction, and charter invariants.
