# Design Note: Day 074 — Change Detection Between Consecutive Observations

## 1. Architectural Context & Motivation

Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X:
- **Day 069:** Implemented timestamped system observation records (`system_observation_records`).
- **Day 070:** Implemented append-only system event storage (`system_events`) with cryptographic hash chaining.
- **Day 071:** Built entity relationship ingestion from collectors (`EntityRelationshipIngestor`).
- **Day 072:** Added temporal validity intervals and non-destructive stale markers (`entity_temporal_validity`).
- **Day 073:** Implemented state snapshots and snapshot comparison (`digital_twin_snapshots`).
- **Day 074:** Establishes **Change Detection Between Consecutive Observations** (`observation_deltas`, `ObservationDelta`, `ObservationChangeDetector`, `ObservationDeltaManager`).

In continuous telemetry aggregation, re-reading full JSON payloads for every temporal query is computationally inefficient ($O(K \cdot N)$ payload parsing). Consecutive observation change detection introduces:
1. **$O(1)$ Digest Pre-Filtering:** By comparing cryptographic payload digests ($O_A.\text{payload\_sha256} == O_B.\text{payload\_sha256}$), identical observations skip full JSON deserialization and comparison immediately (`has_changed = False`, `change_classification = "NO_CHANGE"`).
2. **Granular Attribute-Level Deltas:** When payloads differ, the detector computes:
   - `added_attributes`: newly appeared telemetry fields.
   - `removed_attributes`: fields dropped in subsequent observation.
   - `modified_attributes`: fields with value transitions (`old_value`, `new_value`, `change_type`).
3. **Semantic Change Classification:** Transitions are categorized by operational significance:
   - `NO_CHANGE`: payload hashes match.
   - `ATTRIBUTE_MUTATION`: nominal telemetry evolution (e.g. counter increment).
   - `SIGNIFICANT_THRESHOLD_BREACH`: threshold excursions (e.g. CPU spike, memory pressure transition).
   - `STATUS_DEGRADATION`: collector degraded or partial data reported.
   - `CONFIDENCE_SHIFT`: confidence score drift.
   - `LIFECYCLE_TRANSITION`: process spawn, exit, service stop, volume unmount.
4. **Relational Delta Indexing:** Migration `0009_observation_deltas.sql` persists deltas with foreign keys referencing `system_observation_records`, enabling sub-millisecond timeline queries for state changes without table scanning.
5. **Universal Invariant (`SC-03`):** Detecting observation deltas reflects physical measurement difference, never software safety. `scan_proves_safe = False` is enforced at schema and model levels.

---

## 2. Relational Schema Architecture

Migration `0009_observation_deltas.sql` creates the `observation_deltas` table.

```
+---------------------------------------------------------------------------------------------------------+
|                         SYSTEM MIND X — Observation Deltas Schema                                       |
+---------------------------------------------------------------------------------------------------------+

  +----------------------------------------------------------------------------------------------------+
  |                                      observation_deltas                                            |
  +----------------------------------------------------------------------------------------------------+
  | delta_id                  | TEXT PRIMARY KEY (UUIDv4)                                              |
  | entity_urn                | TEXT NOT NULL (Canonical entity URN, indexed)                          |
  | device_id                 | TEXT NOT NULL (RFC 4122 device UUIDv5, indexed)                        |
  | from_record_id            | TEXT NOT NULL REFERENCES system_observation_records(record_id) ON DEL  |
  | to_record_id              | TEXT NOT NULL REFERENCES system_observation_records(record_id) ON DEL  |
  | from_sequence             | INTEGER NOT NULL (Source observation sequence)                         |
  | to_sequence               | INTEGER NOT NULL (Target observation sequence)                         |
  | from_epoch_ms             | INTEGER NOT NULL (Source timestamp ms)                                 |
  | to_epoch_ms               | INTEGER NOT NULL (Target timestamp ms)                                 |
  | time_delta_ms             | INTEGER NOT NULL (Elapsed time between observations)                   |
  | has_changed               | INTEGER NOT NULL CHECK (has_changed IN (0, 1), indexed)                |
  | change_classification     | TEXT NOT NULL (NO_CHANGE, ATTRIBUTE_MUTATION, etc., indexed)           |
  | added_keys_json           | TEXT NOT NULL DEFAULT '[]'                                             |
  | removed_keys_json         | TEXT NOT NULL DEFAULT '[]'                                             |
  | modified_keys_json        | TEXT NOT NULL DEFAULT '{}'                                             |
  | change_count              | INTEGER NOT NULL DEFAULT 0                                             |
  | detected_at_iso           | TEXT NOT NULL (ISO 8601 UTC timestamp of change detection)              |
  | scan_proves_safe          | INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)                |
  +----------------------------------------------------------------------------------------------------+
```

---

## 3. Mandatory Architectural Invariants

1. **Entity Invariance (`INV-CHG-01`):** Consecutive observation change detection strictly mandates that both observation records bind to identical `entity_urn` and `device_id`. Cross-entity diffing is rejected.
2. **Monotonic Sequence Progression (`INV-CHG-02`):** The target observation must have `to_sequence > from_sequence` and non-inverted timestamp `to_epoch_ms >= from_epoch_ms`.
3. **Payload Digest Pre-Filter (`INV-CHG-03`):** If `from_record.payload_sha256 == to_record.payload_sha256` and statuses/confidences match, `has_changed = False` is evaluated without full JSON deep comparison.
4. **Universal 'Scan != Safe' Invariant (`INV-CHG-04` / `SC-03`):** Strictly enforced at SQLite database constraint level (`CHECK (scan_proves_safe = 0)`) and in Python dataclasses (`scan_proves_safe: bool = False`).
5. **Zero Ambient Shell Authority (`INV-CHG-05` / `SC-01`):** All change detection, payload comparison, and delta persistence execute purely in-memory via parameterized SQL statements without shell processes (`shell=False`).
