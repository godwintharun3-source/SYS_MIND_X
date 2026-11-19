# Design Note: Day 071 — Build Entity Relationship Ingestion from Collectors

## 1. Architectural Context & Motivation

Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X.
- **Day 066:** Formalized canonical URN entity identifiers (`urn:systemmind:<domain>:<qualifier>`).
- **Day 067:** Created relational database models for physical hardware, operating systems, and installed applications.
- **Day 068:** Created graph-node and graph-edge persistence models for property graph topology.
- **Day 069:** Implemented timestamped system observation records (`system_observation_records`).
- **Day 070:** Implemented append-only system event storage (`system_events`) with cryptographic hash chaining.
- **Day 071:** Establishes the foundational **Entity Relationship Ingestion Engine** (`EntityRelationshipIngestor`) transforming telemetry observations into persistent, directed digital twin graph topology.

Raw telemetry collectors (e.g. `MacOsInventoryApi`, companion observation engines, sensor sweeps) observe fragmented operational metrics across distinct OS domains: CPU architecture, memory pressure, storage volumes, network interfaces, process lists with parent PIDs, launchd daemons, and application bundles. While individual observation envelopes record facts, the **Temporal Digital Twin** requires a coherent, queryable property graph connecting these facts:
1. **Device Containment:** The host device contains its kernel, hardware components (CPU, memory, GPU), storage volumes, and network interfaces.
2. **Process Lineage:** Running processes form an explicit parent-child ancestry tree linked by `SPAWNED_BY` directed edges (`child_proc -> SPAWNED_BY -> parent_proc`).
3. **Application Ownership:** User and system applications own the execution instances of their binaries (`app -> OWNS -> proc`).
4. **Service Management:** Background daemons and user agents supervise and spawn their managed worker processes (`service -> OWNS -> proc`).
5. **Ownership Isolation:** Ingestion deterministically attributes `ComponentOwnership` (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`), ensuring user software is never conflated with system core.

---

## 2. Ingestion Pipeline & Architecture

```
+---------------------------------------------------------------------------------------------------------+
|                               SYSTEM MIND X — Entity Relationship Ingestion                             |
+---------------------------------------------------------------------------------------------------------+

  Telemetry Sources:
  - MacOsInventoryResponse (All Sections)
  - CompanionObservationBatch
  - Raw Telemetry Section Dictionaries (IDENTITY, HARDWARE, STORAGE, NETWORK, APPS, PROCESSES, SERVICES)
                                   |
                                   v
  +----------------------------------------------------------------------------------------------------+
  |                               EntityRelationshipIngestor                                          |
  +----------------------------------------------------------------------------------------------------+
  | 1. Device Context Resolution: StableEntityIdGenerator.resolve_device_id()                         |
  | 2. Entity Extraction:                                                                              |
  |    - Host Entity          (urn:systemmind:host:<device_id>)                                        |
  |    - Kernel Entity        (urn:systemmind:kernel:<os>:<rel>:<arch>)                                |
  |    - Hardware Devices     (CPU, Mem, GPU URNs)                                                     |
  |    - Storage Volumes      (urn:systemmind:vol:<device_id>:<mount>)                                 |
  |    - Network Interfaces   (urn:systemmind:net:<device_id>:<name>)                                  |
  |    - Installed Apps       (urn:systemmind:app:<bundle_or_name>)                                    |
  |    - Running Processes    (urn:systemmind:proc:<device_id>:<time>:<pid>:<path_hash>)               |
  |    - Launchd Services     (urn:systemmind:svc:<domain>:<label>)                                    |
  | 3. Relationship Synthesis:                                                                         |
  |    - Host -> CONTAINS -> Kernel, CPU, Mem, GPU, Volumes, Net, Apps, Services                       |
  |    - Process -> SPAWNED_BY -> Parent Process (ppid traversal)                                     |
  |    - Application -> OWNS -> Process (bundle ID / binary path match)                                |
  |    - Service -> OWNS -> Process (service pid match)                                                |
  | 4. Validation & Graph Injection:                                                                   |
  |    - Referential Integrity Check (Zero dangling edges; entities added prior to relationships)      |
  |    - Charter Invariant SC-03 Verification (scan_proves_safe = False)                               |
  |    - DigitalTwinGraph / GraphPersistenceManager Database Persistence                               |
  +----------------------------------------------------------------------------------------------------+
                                   |
                                   v
  Outputs:
  - IngestionResult (entities, relationships, counts, warnings, duration)
  - DigitalTwinGraph (in-memory directed property graph ready for traversal queries)
  - SQLite Tables: graph_nodes, graph_edges (via GraphPersistenceManager)
```

---

## 3. Mandatory Safety & Architectural Invariants

1. **Canonical Entity Derivation (`INV-INGEST-01`):** All extracted entities must resolve to canonical, typed URNs (`urn:systemmind:<domain>:<qualifier>`) conforming to `EntityUrn` validation.
2. **Referential Integrity & Graph Completeness (`INV-INGEST-02`):** Every ingested relationship must connect valid source and target entities present in the digital twin. Entities are always registered in the graph before relationships are established, preventing dangling pointers.
3. **Structural Semantics (`INV-INGEST-03`):**
   - `HOST -> CONTAINS -> OS_KERNEL`
   - `HOST -> CONTAINS -> HARDWARE_DEVICE`
   - `HOST -> CONTAINS -> FILESYSTEM_NODE` (Volumes)
   - `HOST -> CONTAINS -> NETWORK_SOCKET` (Interfaces)
   - `HOST -> CONTAINS -> APPLICATION`
   - `APPLICATION -> OWNS -> PROCESS`
   - `CHILD_PROCESS -> SPAWNED_BY -> PARENT_PROCESS`
   - `SERVICE -> OWNS -> PROCESS`
4. **Component Ownership Preservation (`INV-INGEST-04`):** Every entity and relationship explicitly preserves the ownership boundary (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`). User applications and user processes must never be classified as `SYSTEM_MANAGED`.
5. **Confidence & Provenance Grounding (`INV-INGEST-05`):** Entities and relationships derive confidence (`0.0 <= confidence <= 1.0`) from source observation metadata. Synthetic simulations cannot claim kernel authority.
6. **Inviolable 'Scan != Safe' Invariant (`SC-03` / `INV-INGEST-06`):** All entities, relationships, records, and result envelopes strictly enforce `scan_proves_safe = False`.
7. **Idempotency & Safe Updates (`INV-INGEST-07`):** Ingestion is idempotent; re-running ingestion updates existing entity attributes and relationships without duplicate primary keys or index corruption.
8. **Zero Ambient Shell Authority (`SC-01` / `INV-INGEST-08`):** All ingestion transformations execute in-memory with zero unmediated shell execution (`shell=False`).
