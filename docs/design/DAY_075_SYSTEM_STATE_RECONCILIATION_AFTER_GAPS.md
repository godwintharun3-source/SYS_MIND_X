# Design Note: Day 075 — System-State Reconciliation After Collector Gaps

## 1. Architectural Context & Motivation

Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X:
- **Day 069:** Implemented timestamped system observation records (`system_observation_records`).
- **Day 070:** Implemented append-only system event storage (`system_events`) with cryptographic hash chaining.
- **Day 071:** Built entity relationship ingestion from collectors (`EntityRelationshipIngestor`).
- **Day 072:** Added temporal validity intervals and non-destructive stale markers (`entity_temporal_validity`).
- **Day 073:** Implemented state snapshots and snapshot comparison (`digital_twin_snapshots`).
- **Day 074:** Implemented consecutive observation change detection (`observation_deltas`).
- **Day 075:** Establishes **System-State Reconciliation After Collector Gaps** (`collector_gaps`, `state_reconciliation_records`, `CollectorGapDetector`, `SystemStateReconciler`).

In production operating systems, telemetry collectors do not run in continuous, unbroken real time. Collectors experience unavoidable temporal gaps due to:
1. **Host Sleep & Wake Transitions:** Laptops close lids, enter standby, or hibernate, halting timer loops and user-space daemons for minutes, hours, or days.
2. **Process Restarts & Crashes:** Telemetry daemons or companion agents restart following updates or memory pressure.
3. **Sensor Throttling & Timeouts:** Native APIs (e.g. Endpoint Security, sysctl, launchd, CoreServices) may experience timeouts or rate-limiting under high system load.
4. **Network/Subsystem Disconnections:** Monitored peripheral or network adapters temporarily detach.

When collection resumes after an unmonitored window, a naive digital twin would suffer from two failure modes:
- **Ghost Entities:** Entities terminated during the gap (e.g. ephemeral child processes, temporary mount points) remain marked active in memory.
- **False Continuity Assumptions:** Planners assume continuous telemetry existed without epistemic uncertainty, failing to recognize that unseen mutations occurred during the blind spot.

Day 075 solves this by introducing deterministic **Collector Gap Detection** and **System-State Reconciliation**:
1. **$O(1)$ Gap Identification:** Monitors time deltas between consecutive collector runs against expected domain polling cadences ($T_{\text{elapsed}} > \text{cadence} \times \text{tolerance}$).
2. **Gap Classification Hierarchy:** Categorizes gaps into `MINOR_JITTER`, `COLLECTOR_TIMEOUT`, `COLLECTOR_RESTART`, `SYSTEM_SLEEP_WAKE`, and `PROLONGED_OUTAGE`.
3. **Differential State Reconciliation:**
   - **Sustained Entities:** Present before and after gap; validity renewed, but confidence temporarily discounted ($C_{\text{post}} = C_{\text{pre}} \times \delta_{\text{discount}}$) to account for unobserved intermediate states.
   - **Missing Ephemeral Entities:** Processes or temporary resources absent post-gap are marked `TERMINATED_DURING_GAP` with inferred exit timestamps.
   - **Missing Persistent Entities:** Disks, applications, or network interfaces absent post-gap are marked `MARKED_STALE_PENDING_CONFIRMATION` rather than presumed destroyed.
   - **Newly Appeared Entities:** Entities discovered post-gap are recorded as `SPAWNED_OR_ATTACHED_DURING_GAP`.
4. **Relational Schema Architecture:** Migration `0010_collector_gaps_and_reconciliation.sql` stores detected gaps in `collector_gaps` and audit trails in `state_reconciliation_records`.
5. **Universal Invariant (`SC-03`):** Reconciling states heals observational continuity, never software safety. `scan_proves_safe = False` is enforced at schema and model levels.

---

## 2. Relational Schema Architecture

Migration `0010_collector_gaps_and_reconciliation.sql` creates two coordinated tables: `collector_gaps` and `state_reconciliation_records`.

```
+---------------------------------------------------------------------------------------------------------+
|                         SYSTEM MIND X — Collector Gaps & Reconciliation Schema                          |
+---------------------------------------------------------------------------------------------------------+

  +----------------------------------------------------------------------------------------------------+
  |                                      collector_gaps                                                |
  +----------------------------------------------------------------------------------------------------+
  | gap_id                    | TEXT PRIMARY KEY (UUIDv4)                                              |
  | collector_id              | TEXT NOT NULL (Collector identifier, e.g. mock_ps, macos_process)     |
  | device_id                 | TEXT NOT NULL (RFC 4122 device UUID, indexed)                          |
  | domain                    | TEXT NOT NULL (proc, cpu, mem, disk, app, etc., indexed)               |
  | gap_start_epoch_ms        | INTEGER NOT NULL (Timestamp of last observation before gap)           |
  | gap_end_epoch_ms          | INTEGER NOT NULL (Timestamp of first observation after gap)            |
  | gap_duration_ms           | INTEGER NOT NULL (gap_end_epoch_ms - gap_start_epoch_ms)                |
  | expected_cadence_ms       | INTEGER NOT NULL (Configured nominal sampling interval)                |
  | gap_classification        | TEXT NOT NULL (MINOR_JITTER, COLLECTOR_TIMEOUT, SLEEP_WAKE, etc.)       |
  | detected_at_iso           | TEXT NOT NULL (ISO 8601 UTC timestamp of gap detection)               |
  | scan_proves_safe          | INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)                |
  +----------------------------------------------------------------------------------------------------+

  +----------------------------------------------------------------------------------------------------+
  |                                 state_reconciliation_records                                      |
  +----------------------------------------------------------------------------------------------------+
  | reconciliation_id         | TEXT PRIMARY KEY (UUIDv4)                                              |
  | gap_id                    | TEXT NOT NULL REFERENCES collector_gaps(gap_id) ON DELETE CASCADE       |
  | device_id                 | TEXT NOT NULL (RFC 4122 device UUID, indexed)                          |
  | domain                    | TEXT NOT NULL (proc, cpu, etc., indexed)                               |
  | reconciled_at_iso         | TEXT NOT NULL (ISO 8601 UTC timestamp)                                 |
  | reconciled_at_epoch_ms    | INTEGER NOT NULL (Epoch ms timestamp)                                  |
  | entities_sustained_count  | INTEGER NOT NULL DEFAULT 0                                             |
  | entities_terminated_count | INTEGER NOT NULL DEFAULT 0                                             |
  | entities_staled_count     | INTEGER NOT NULL DEFAULT 0                                             |
  | entities_spawned_count    | INTEGER NOT NULL DEFAULT 0                                             |
  | confidence_discount_pct   | REAL NOT NULL DEFAULT 0.0 (e.g. 0.15 for 15% discount)                 |
  | actions_json              | TEXT NOT NULL DEFAULT '[]' (Detailed itemized actions)                 |
  | scan_proves_safe          | INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)                |
  +----------------------------------------------------------------------------------------------------+
```

---

## 3. Mandatory Architectural Invariants

1. **Deterministic Gap Identification (`INV-REC-01`):** A gap is declared if and only if $T_{\text{elapsed}} \ge \text{expected\_cadence} \times \text{tolerance\_multiplier}$ (default multiplier: $2.0$). Single-sample jitter below this threshold is not classified as an outage.
2. **Non-Destructive State Healing (`INV-REC-02`):** Missing entities are NEVER deleted from digital twin storage. Ephemeral entities receive explicit `TERMINATED_DURING_GAP` markers; persistent entities receive `MARKED_STALE_PENDING_CONFIRMATION` markers.
3. **Epistemic Confidence Discounting (`INV-REC-03`):** Unobserved intervals introduce epistemic decay. Sustained entities active across a gap inherit a confidence discount proportional to gap duration, restored only when confirmed by continuous post-gap observations.
4. **Universal 'Scan != Safe' Invariant (`INV-REC-04` / `SC-03`):** Strictly enforced at SQLite database constraint level (`CHECK (scan_proves_safe = 0)`) and in Python dataclasses (`scan_proves_safe: bool = False`). State reconciliation repairs observation gaps, never software safety.
5. **Zero Ambient Shell Authority (`INV-REC-05` / `SC-01`):** All gap calculation, differential reconciliation, and record persistence execute purely in-memory via parameterized SQL statements without shell processes (`shell=False`).
