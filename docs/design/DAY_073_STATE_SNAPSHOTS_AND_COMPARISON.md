# Design Note: Day 073 — State Snapshots and Snapshot Comparison

## 1. Architectural Context & Motivation

Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X:
- **Day 066:** Formalized canonical entity identifiers (`urn:systemmind:<domain>:<qualifier>`).
- **Day 067:** Created relational database persistence models for physical hardware, OS, and applications.
- **Day 068:** Created graph-node and graph-edge persistence models for property graph topology.
- **Day 069:** Implemented timestamped system observation records (`system_observation_records`).
- **Day 070:** Implemented append-only system event storage (`system_events`) with cryptographic hash chaining.
- **Day 071:** Built entity relationship ingestion from collectors (`EntityRelationshipIngestor`).
- **Day 072:** Added temporal validity intervals and non-destructive stale markers (`entity_temporal_validity`).
- **Day 073:** Implements **State Snapshots and Snapshot Comparison** (`DigitalTwinSnapshot`, `DigitalTwinSnapshotDiff`, `DigitalTwinSnapshotManager`).

In an AI-native computer operator, point-in-time state snapshots are foundational for:
1. **Pre/Post Mutation Verification:** Before the Trusted Broker executes any consequential action, a pre-mutation snapshot $S_{\text{pre}}$ is captured. Following execution, a post-mutation snapshot $S_{\text{post}}$ is captured. Comparing $S_{\text{pre}}$ and $S_{\text{post}}$ verifies that only the intended target entities mutated and guarantees non-interference with user-managed applications (`SC-02`).
2. **Deterministic Cryptographic State Fingerprinting:** Every snapshot generates a canonical `state_digest` (SHA-256) over sorted canonical entities and directed relationships. Identical graph states produce identical digests, enabling instant $O(1)$ equality checks.
3. **Lossless Temporal Reconstruction:** Given any historical `snapshot_id`, `DigitalTwinSnapshotManager.reconstruct_graph()` re-instantiates a fully functional in-memory `DigitalTwinGraph` with referential integrity preserved.
4. **Structural Diffing:** Fine-grained comparison calculates:
   - Added entities ($E_B \setminus E_A$).
   - Removed entities ($E_A \setminus E_B$).
   - Modified entities ($E_A \cap E_B$ with attribute or staleness deltas).
   - Added relationships ($R_B \setminus R_A$).
   - Removed relationships ($R_A \setminus R_B$).
   - Component ownership impact metrics (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`).
5. **Universal Invariant (`SC-03`):** State snapshots reflect point-in-time observational configuration, never software trustworthiness. `scan_proves_safe = False` is strictly enforced at schema and model levels.

---

## 2. Relational Schema Architecture

Migration `0008_digital_twin_state_snapshots.sql` creates the `digital_twin_snapshots` table.

```
+---------------------------------------------------------------------------------------------------------+
|                         SYSTEM MIND X — Digital Twin State Snapshots Schema                             |
+---------------------------------------------------------------------------------------------------------+

  +----------------------------------------------------------------------------------------------------+
  |                                   digital_twin_snapshots                                           |
  +----------------------------------------------------------------------------------------------------+
  | snapshot_id               | TEXT PRIMARY KEY (UUIDv4 or deterministic snapshot token)              |
  | device_id                 | TEXT NOT NULL (RFC 4122 device UUIDv5, indexed)                        |
  | captured_at_iso           | TEXT NOT NULL (ISO 8601 UTC timestamp of snapshot capture)             |
  | captured_at_epoch_ms      | INTEGER NOT NULL (Unix epoch milliseconds, indexed)                    |
  | sequence_number           | INTEGER NOT NULL (Monotonic sequence number per device, indexed)       |
  | trigger_reason            | TEXT NOT NULL (TELEMETRY_SWEEP, PRE_MUTATION, POST_MUTATION, etc.)     |
  | entity_count              | INTEGER NOT NULL (Count of entities in snapshot)                       |
  | relationship_count        | INTEGER NOT NULL (Count of directed relationships in snapshot)         |
  | state_digest              | TEXT NOT NULL (Canonical SHA-256 digest of entities & relationships)   |
  | entities_json             | TEXT NOT NULL (Serialized JSON array of TwinEntity models)             |
  | relationships_json        | TEXT NOT NULL (Serialized JSON array of TwinRelationship models)       |
  | metadata_json             | TEXT NOT NULL DEFAULT '{}' (Contextual metadata, e.g. broker action)   |
  | scan_proves_safe          | INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)                |
  +----------------------------------------------------------------------------------------------------+
```

---

## 3. Snapshot Comparison Topology & Diff Mechanics

```
        Snapshot A (T_from)                               Snapshot B (T_to)
     +-----------------------+                         +-----------------------+
     | Entities: E_A         |                         | Entities: E_B         |
     | Relationships: R_A    |                         | Relationships: R_B    |
     | Digest: SHA-256(A)    |                         | Digest: SHA-256(B)    |
     +-----------+-----------+                         +-----------+-----------+
                 \                                                 /
                  \                                               /
                   +---------------------------------------------+
                   |           DigitalTwinSnapshotDiff           |
                   +---------------------------------------------+
                   |  - added_entities      = E_B \ E_A          |
                   |  - removed_entities    = E_A \ E_B          |
                   |  - modified_entities   = delta(E_A & E_B)   |
                   |  - added_relationships = R_B \ R_A          |
                   |  - removed_rel         = R_A \ R_B          |
                   |  - ownership_changes   = {sys, ven, usr}    |
                   |  - user_managed_affected: bool              |
                   |  - is_identical: bool                       |
                   |  - scan_proves_safe: False (SC-03)          |
                   +---------------------------------------------+
```

---

## 4. Mandatory Architectural Invariants

1. **Deterministic Fingerprinting (`INV-SNAP-01`):** Canonical sorting of entities by `entity_id` and relationships by `relation_id` before JSON serialization guarantees that graph state digests are reproducible across runs and architectures.
2. **Monotonic Sequence Progression (`INV-SNAP-02`):** Per device, snapshot sequence numbers strictly increase monotonically with time.
3. **Lossless Graph Reconstruction (`INV-SNAP-03`):** Any captured snapshot can be restored to an active, valid `DigitalTwinGraph` instance matching all entity types, ownership tags, attributes, and relationship connections.
4. **Component Ownership Guardrails (`INV-SNAP-04` / `SC-02`):** Snapshot comparison calculates ownership distribution changes and flags `user_managed_affected = True` if any user-managed application or process was added, modified, or removed.
5. **Universal 'Scan != Safe' Invariant (`INV-SNAP-05` / `SC-03`):** Structurally enforced at database check constraint level (`CHECK (scan_proves_safe = 0)`) and in Python dataclasses (`scan_proves_safe = False`).
6. **Zero Ambient Shell Authority (`INV-SNAP-06` / `SC-01`):** All snapshot extraction, serialization, hashing, and database storage execute purely in-memory via parameterized SQL statements without shell processes (`shell=False`).
