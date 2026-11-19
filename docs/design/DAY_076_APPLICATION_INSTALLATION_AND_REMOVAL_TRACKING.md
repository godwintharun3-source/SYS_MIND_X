# Design Note: Day 076 — Track Application Installation and Removal Events Where Observable

## 1. Architectural Objective & Context

SYSTEM MIND X maintains a persistent, temporal, provenance-aware digital twin of host computing state. Software applications represent high-consequence entities that host execution code, process sensitive user data, establish persistence hooks, and define the user's computing environment.

Tracking application installation, upgrade, move, and removal events is essential for:
1. **Application Context Intelligence**: Knowing when new software is introduced, upgraded, or deleted.
2. **Component Ownership Isolation (`SC-02`)**: Distinguishing `SYSTEM_MANAGED` OS applications from `VENDOR_MANAGED` and `USER_MANAGED` applications, guaranteeing that user applications are never automatically modified or updated without explicit user governance.
3. **Auditability & Provenance**: Capturing cryptographic code signatures, developer team IDs, notarization states, and install paths at the precise moment an application is introduced.
4. **Point-in-Time Application History**: Allowing the digital twin to reconstruct exactly which applications were installed on any given device at any historical timestamp $T$.
5. **Universal "Scan != Safe" Invariant (`SC-03`)**: Recording an installation event does not imply safety or absence of malicious capability.

---

## 2. Observation Channels & Detection Strategies

Application lifecycle transitions cannot rely on a single fragile OS telemetry mechanism. SYSTEM MIND X employs a multi-channel detection strategy:

```
+--------------------------------------------------------------------------------+
|                        APPLICATION TELEMETRY CHANNELS                          |
+--------------------------------------------------------------------------------+
             |                                                  |
             v                                                  v
+-------------------------------+              +---------------------------------+
|  Channel A: Periodic Inventory|              |  Channel B: Filesystem Changes  |
|  Scans (/Applications, etc.)  |              |  (macOS FSEvents / fanotify)    |
+-------------------------------+              +---------------------------------+
             |                                                  |
             +------------------------+-------------------------+
                                      |
                                      v
+--------------------------------------------------------------------------------+
|                       APPLICATION LIFECYCLE TRACKER                            |
|             (Diff Evaluation, Transition Classification, Deduplication)        |
+--------------------------------------------------------------------------------+
                                      |
     +--------------------------------+--------------------------------+
     |                                |                                |
     v                                v                                v
+--------------------------+   +--------------------------+   +------------------+
| Relational Lifecycle Log |   | Append-Only Event Store  |   | In-Memory Digital|
| (application_lifecycle_  |   | (SystemEventStore with   |   | Twin Graph       |
|  events table, mig 0011) |   |  SHA-256 Hash Chaining)  |   | (DigitalTwinGraph|
+--------------------------+   +--------------------------+   +------------------+
```

### Channel A: Periodic Inventory Diffing
- Compares consecutive application inventory snapshots (from `crates/system-mind-sensors/src/macos_apps.rs` or Python detectors).
- Correlates applications across snapshots by canonical URN (`urn:systemmind:application:<bundle_id>`), bundle identifier, and installation path.
- Classifies differences into:
  - `APPLICATION_INSTALLED`: Present in new snapshot, absent in old.
  - `APPLICATION_REMOVED`: Absent in new snapshot, present in old.
  - `APPLICATION_UPGRADED`: Present in both, but `version`, `build_version`, or `code_signature` has mutated.
  - `APPLICATION_PATH_MUTATED`: Present in both with identical `bundle_id`, but `install_path` has changed (e.g. moved from `~/Downloads/` to `/Applications/`).

### Channel B: Real-Time Filesystem Change Notifications (FSEvents)
- Intercepts filesystem events on monitored application directories (`/Applications`, `~/Applications`, `/System/Applications`, `/opt`, Homebrew Caskroom).
- Maps raw filesystem flags (`ItemCreated`, `ItemRemoved`, `ItemRenamed`, `ItemModified`) on `.app` directory structures into candidate application lifecycle events.

---

## 3. Application Lifecycle Event Taxonomy

| Event Type | Trigger Condition | Digital Twin Action |
|---|---|---|
| `APPLICATION_INSTALLED` | New application bundle observed on filesystem or inventory | Register new `TwinEntity` (`APPLICATION`), link `HOST -> CONTAINS -> APPLICATION`, persist lifecycle event |
| `APPLICATION_REMOVED` | Application bundle deleted or trashed | Mark `TwinEntity` stale (`is_stale = True`, `stale_reason = "APPLICATION_REMOVED"`), record tombstone timestamp, never delete from history |
| `APPLICATION_UPGRADED` | Existing application version, build, or binary hash updated | Update `TwinEntity` attributes, maintain historical version array in metadata, persist lifecycle event |
| `APPLICATION_PATH_MUTATED` | Application bundle path changed across locations | Update `install_path` attribute on `TwinEntity`, link previous and new path in event |
| `APPLICATION_RESTORED` | Previously removed application reappears | Clear stale marker (`is_stale = False`), restore freshness |

---

## 4. Mathematical & Data Invariants

1. **Component Ownership Guardrails (`SC-02` / `INV-APP-01`)**:
   - All application lifecycle events capture `ownership: ComponentOwnership`.
   - User applications (`USER_MANAGED`) are strictly protected from autonomous system modifications or forced updates.
2. **Canonical Entity URN (`INV-APP-02`)**:
   - Every application entity and lifecycle event references a canonical URN: `urn:systemmind:application:<bundle_id_or_slug>`.
3. **Inviolable 'Scan != Safe' Invariant (`SC-03` / `INV-APP-03`)**:
   - Enforced at SQLite database level via `CHECK (scan_proves_safe = 0)` and Python dataclass validation (`scan_proves_safe: bool = False`).
   - Logging an application install or removal event reflects factual observation, never a guarantee of application safety, trustworthiness, or benign intent.
4. **Append-Only Event Store Integration (`INV-APP-04`)**:
   - Application lifecycle events bridge directly to `SystemEventStore` (`src/system_mind/twin/event_store.py`), maintaining cryptographic SHA-256 hash chaining across the event log.
5. **Lossless Temporal History (`INV-APP-05`)**:
   - Application removal NEVER drops records from SQLite or the property graph. Removed applications are marked with `is_stale = True` and preserved forever for audit and incident analysis.
6. **Zero Ambient Shell Authority (`SC-01` / `INV-APP-06`)**:
   - Purely in-memory and parameterized SQLite execution (`shell=False`). No shell subprocesses are spawned.
