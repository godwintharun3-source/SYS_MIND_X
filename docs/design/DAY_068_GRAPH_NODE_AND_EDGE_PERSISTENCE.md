# Design Note: Day 068 — Create Graph-Node and Graph-Edge Persistence Models

## 1. Architectural Context & Motivation
Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X.
- **Day 066:** Formalized canonical URN entity identifiers (`urn:systemmind:<domain>:<qualifier>`).
- **Day 067:** Created relational database schemas for physical hardware, operating systems, and installed applications.
- **Day 068:** Bridges the in-memory directed property graph (`DigitalTwinGraph`) with persistent SQLite storage by establishing dedicated **graph-node** and **graph-edge** persistence models.

In operating systems and computer administration, system components form a rich, dynamic directed property graph:
- A `PROCESS` is `SPAWNED_BY` another `PROCESS`.
- An `APPLICATION` `OWNS` binary executables and configuration files.
- A `SERVICE` `DEPENDS_ON` other background daemons and network sockets.
- An operating system kernel `ENFORCES_POLICY` on running workloads.

While earlier milestones defined an in-memory graph (`DigitalTwinGraph`), agent restarts, host reboots, or daemon crashes would destroy this property graph. Day 068 establishes durable relational persistence schemas, strongly typed serialization models, and a transactional `GraphPersistenceManager` capable of saving, querying, and reconstructing the complete digital twin graph.

---

## 2. Relational Schema Architecture

The graph persistence tables are introduced via migration `0004_graph_nodes_and_edges.sql`.

```
+---------------------------------------------------------------------------------------------------------+
|                              SYSTEM MIND X — Graph Node & Edge Relational Schema                        |
+---------------------------------------------------------------------------------------------------------+

  +---------------------------------+        +---------------------------------+
  |           graph_nodes           |        |           graph_edges           |
  +---------------------------------+        +---------------------------------+
  | node_id (PK, TEXT)              |<---+   | edge_id (PK, TEXT)              |
  | node_type (TEXT, indexed)       |    +---| source_node_id (TEXT, FK, idx)  |
  | ownership (TEXT, indexed)       |    +---| target_node_id (TEXT, FK, idx)  |
  | attributes_json (TEXT)          |        | relation_type (TEXT, indexed)   |
  | provenance_source (TEXT)        |        | properties_json (TEXT)          |
  | created_at (TEXT)               |        | observed_at (TEXT, indexed)     |
  | updated_at (TEXT)               |        | confidence (REAL, [0.0, 1.0])   |
  | is_stale (INT, [0, 1], indexed) |        | scan_proves_safe (INT, CHECK=0) |
  | scan_proves_safe (INT, CHECK=0) |        +---------------------------------+
  +---------------------------------+
```

### Relational Features:
1. **Foreign Key Integrity:** `graph_edges.source_node_id` and `target_node_id` reference `graph_nodes.node_id` with `ON DELETE CASCADE`. Removing a node automatically cascades removal of incident edges.
2. **Confidence Bounding:** `confidence` on graph edges is constrained to `[0.0, 1.0]` at the database engine level.
3. **Staleness Tracking:** `is_stale` is tracked as an indexed binary flag (`0` = active, `1` = stale), supporting temporal query filtering.

---

## 3. Mandatory Safety & Architectural Invariants

1. **Graph Referential Integrity (`INV-GRAPH-01`):** A relationship (edge) cannot exist without valid, existing source and target nodes. Dangling edges are rejected by foreign key constraints and graph validators.
2. **Universal "Scan != Safe" Invariant (`INV-GRAPH-02` / `SC-03`):** Both `graph_nodes` and `graph_edges` enforce `scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)` in SQLite DDL, and `scan_proves_safe: bool = False` in Python models. Representing an entity or relationship in the digital twin does not imply that the software or connection is safe.
3. **Tripartite Ownership Partitioning (`INV-GRAPH-03`):** Every node records explicit `ComponentOwnership` (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`).
4. **Lossless Graph Round-Trip Reconstruction (`INV-GRAPH-04`):** Serializing `DigitalTwinGraph` into SQLite and reconstructing it from disk produces an isomorphic graph with identical node counts, edge counts, indices, attributes, and adjacency lists.
5. **Reversible Migration Lifecycle (`INV-GRAPH-05`):** Migration `0004` includes complete, deterministic `-- UP` and `-- DOWN` definitions, verified in CI by `DatabaseMigrationValidator`.
6. **Zero Ambient Shell Authority (`SC-01` / `INV-GRAPH-06`):** All database operations execute through parameterized SQL queries via `sqlite3` without spawning ambient shell processes.

---

## 4. Verification & Acceptance Criteria
- Migration `0004_graph_nodes_and_edges.sql` applies and rolls back cleanly under `DatabaseMigrator`.
- Python models (`GraphNodeRecord`, `GraphEdgeRecord`) pass full serialization roundtrips and invariant enforcement.
- `GraphPersistenceManager` provides CRUD operations, bulk graph persistence (`persist_graph`), and in-memory reconstruction (`load_graph`).
- In-memory graph traversal queries (`get_dependencies`, `get_process_ancestors`, `validate_integrity`) work seamlessly on graphs reconstructed from SQLite.
- Developer CLI tool (`tools/detect_graph_persistence.py`) verifies migration, seeds mock graph topology, and performs packaging audits.
- Packaging validator (`GraphPersistenceValidator`) in `src/system_mind/packaging/graph_persistence.py` passes AST safety and file completeness audits.
- Comprehensive test suite in `tests/test_graph_persistence.py` passes 100%.
- Formalized ADR-079 in `docs/DECISION_LOG.md`.
