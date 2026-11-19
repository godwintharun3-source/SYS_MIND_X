# Design Note: Day 072 — Add Temporal Validity and Stale-Observation Markers

## 1. Architectural Context & Motivation

Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X.
- **Day 066:** Formalized canonical URN entity identifiers (`urn:systemmind:<domain>:<qualifier>`).
- **Day 067:** Created relational database models for physical hardware, operating systems, and installed applications.
- **Day 068:** Created graph-node and graph-edge persistence models for property graph topology.
- **Day 069:** Implemented timestamped system observation records (`system_observation_records`).
- **Day 070:** Implemented append-only system event storage (`system_events`) with cryptographic hash chaining.
- **Day 071:** Built entity relationship ingestion from collectors (`EntityRelationshipIngestor`).
- **Day 072:** Establishes **temporal validity windows** and **stale-observation markers** (`entity_temporal_validity` and `TemporalValidityManager`) to track observational freshness, manage entity lifecycle decay, and mark unobserved/expired facts without data loss.

In an AI-native computer operator, facts asserted by the digital twin have finite temporal validity:
1. **Dynamic Entities Decay Fast:** Short-lived entities like transient child processes or socket connections become obsolete within seconds.
2. **Static Entities Persist:** Storage volumes, hardware models, and installed applications remain valid for hours or days.
3. **Non-Destructive Staleness:** When an entity is terminated, unmounted, or unobserved during a telemetry sweep, it must **never be deleted** from the historical graph or event log. Instead, it is marked with an explicit stale marker (`is_stale = 1`, `stale_reason = "UNOBSERVED_IN_SCAN"`, `freshness_state = "STALE"`), preserving the historical timeline for forensic reconstruction.
4. **Reversible Freshness:** If a subsequent telemetry sweep observes the entity again (e.g. process was alive or service restarted), the stale marker is cleared (`is_stale = 0`, `freshness_state = "FRESH"`), opening a new temporal validity window.
5. **Universal Invariant (`SC-03`):** Observational freshness reflects measurement age, never software safety. `scan_proves_safe = False` is enforced at schema and model levels.

---

## 2. Relational Schema Architecture

Migration `0007_temporal_validity_and_stale_markers.sql` creates the `entity_temporal_validity` table.

```
+---------------------------------------------------------------------------------------------------------+
|                       SYSTEM MIND X — Entity Temporal Validity & Stale Markers Schema                   |
+---------------------------------------------------------------------------------------------------------+

  +----------------------------------------------------------------------------------------------------+
  |                                   entity_temporal_validity                                         |
  +----------------------------------------------------------------------------------------------------+
  | entity_urn                 | TEXT PRIMARY KEY (Canonical URN, e.g. urn:systemmind:proc:...)        |
  | device_id                  | TEXT NOT NULL (RFC 4122 device UUIDv5, indexed)                       |
  | domain                     | TEXT NOT NULL (Canonical entity domain: host, proc, app, vol, indexed)|
  | last_observed_at_iso       | TEXT NOT NULL (ISO 8601 UTC timestamp of last reading)               |
  | last_observed_at_epoch_ms  | INTEGER NOT NULL (Unix epoch milliseconds of last reading)           |
  | valid_until_epoch_ms       | INTEGER NOT NULL (Unix epoch ms after which observation is stale, idx)|
  | ttl_seconds                | REAL NOT NULL DEFAULT 60.0 (Domain-specific time-to-live)             |
  | freshness_state            | TEXT NOT NULL DEFAULT 'FRESH' (FRESH, AGING, STALE, EXPIRED, idx)    |
  | staleness_score            | REAL NOT NULL DEFAULT 0.0 CHECK (staleness_score BETWEEN 0.0 AND 1.0) |
  | is_stale                   | INTEGER NOT NULL DEFAULT 0 CHECK (is_stale IN (0, 1), indexed)       |
  | stale_reason               | TEXT (TTL_EXPIRED, UNOBSERVED_IN_SCAN, PROCESS_EXIT, UNMOUNTED, etc.) |
  | marked_stale_at_iso        | TEXT (Timestamp when staleness marker was applied)                   |
  | scan_proves_safe           | INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)               |
  +----------------------------------------------------------------------------------------------------+
```

---

## 3. Domain-Specific Temporal Validity Windows

| Entity Domain | Default TTL (`ttl_seconds`) | Max Staleness (`max_staleness_seconds`) | Typical Invalidation Trigger |
| :--- | :--- | :--- | :--- |
| `proc` (Processes) | 15.0s | 45.0s | Process exit, PID unobserved in scan |
| `cpu`, `mem`, `gpu`, `battery` | 30.0s | 90.0s | Continuous telemetry sweep |
| `net` (Network Interfaces/Sockets) | 45.0s | 120.0s | Interface down, socket close |
| `svc` (Launchd Services) | 120.0s | 600.0s | launchctl unload / bootout |
| `vol` / `file` (Storage Volumes) | 300.0s | 1800.0s | Volume unmount / eject |
| `app` (Installed Applications) | 3600.0s | 86400.0s | App bundle removed / deleted |
| `kernel` / `host` (OS / Machine) | 86400.0s | 604800.0s | OS reboot, kernel panic |

---

## 4. Mandatory Safety & Architectural Invariants

1. **Canonical Entity Scope (`INV-VAL-01`):** All validity records bind to valid canonical URNs (`urn:systemmind:<domain>:<qualifier>`) and RFC 4122 device UUIDs.
2. **Dual-Time Validity Bounds (`INV-VAL-02`):** Every record tracks `last_observed_at_epoch_ms` and computes `valid_until_epoch_ms = last_observed_at_epoch_ms + int(ttl_seconds * 1000)`.
3. **Five-State Freshness Lifecycle (`INV-VAL-03`):** Transitions deterministically through `FRESH` (0.0 to 0.5 score), `AGING` (0.5 to 0.8), `STALE` (0.8 to 1.0), `EXPIRED` (1.0), and `TOMBSTONED` (1.0).
4. **Non-Destructive Staleness Invalidation (`INV-VAL-04`):** Expired or missing observations are marked stale (`is_stale = 1`, `stale_reason = ...`), NEVER deleted from history.
5. **Universal 'Scan != Safe' Invariant (`SC-03` / `INV-VAL-05`):** Strictly enforced at SQLite database constraint level (`CHECK (scan_proves_safe = 0)`) and in Python dataclasses (`scan_proves_safe: bool = False`). Staleness evaluation reflects observational freshness, never software safety.
6. **Reversible Invalidation (`INV-VAL-06`):** When a fresh observation arrives for an entity previously marked stale, the marker is cleared (`is_stale = False`, `freshness_state = FRESH`, `staleness_score = 0.0`), pushing the validity boundary forward.
7. **Graph Synchronization (`INV-VAL-07`):** When staleness is evaluated, in-memory `DigitalTwinGraph` entities and SQLite persistent `graph_nodes` have their `is_stale` markers synchronized.
8. **Zero Ambient Shell Authority (`SC-01` / `INV-VAL-08`):** All validity evaluation and database interactions execute purely in-memory via parameterized SQL statements without shell processes (`shell=False`).
