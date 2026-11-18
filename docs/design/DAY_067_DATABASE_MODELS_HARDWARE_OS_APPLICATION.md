# Design Note: Day 067 — Create Database Models for Hardware, OS, and Application Entities

## 1. Architectural Context & Motivation
Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X. On Day 066, the architecture formalized canonical, deterministic Uniform Resource Names (URNs) across eleven entity domains (`urn:systemmind:<domain>:<qualifier>`).

On Day 067, the engineering objective is to establish strongly typed, relational database models and schema migrations for the three foundational entity categories:
1. **Hardware Entities:** Persistent representations of physical and architectural hardware assets (Host, CPU, Memory, Storage Volume, Network Interface, GPU, Battery, USB controller/peripherals).
2. **OS Kernel Entities:** Operating system identity, kernel release, product build, hardware architecture, and native security posture (SIP, Gatekeeper, FileVault, firewall).
3. **Application Entities:** Installed software applications, bundle identifiers, install paths, code signatures, and tripartite component ownership classification (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`).

Traditional agent architectures either store flat, unindexed JSON blobs or conflate system software with user applications. Day 067 establishes structured SQLite schemas with typed indexes, foreign key integrity, provenance tracking, and tamper-resistant constraints.

---

## 2. Relational Schema Architecture

The entity tables are integrated into the existing migration framework via migration `0003_hardware_os_application_entities.sql`.

```
+---------------------------------------------------------------------------------------------------------+
|                                  SYSTEM MIND X — Entity Relational Schema                                |
+---------------------------------------------------------------------------------------------------------+

  +---------------------------------+        +---------------------------------+
  |        hardware_entities        |        |        os_kernel_entities       |
  +---------------------------------+        +---------------------------------+
  | entity_urn (PK, TEXT)           |        | entity_urn (PK, TEXT)           |
  | device_id (TEXT, indexed)       |        | device_id (TEXT, indexed)       |
  | category (TEXT, indexed)        |        | os_family (TEXT)                |
  | model_name (TEXT)               |        | product_version (TEXT)          |
  | vendor (TEXT)                   |        | build_version (TEXT)            |
  | serial_hash (TEXT)              |        | kernel_release (TEXT)           |
  | attributes_json (TEXT)          |        | architecture (TEXT)             |
  | observed_at (TEXT, indexed)     |        | security_posture_json (TEXT)    |
  | provenance_source (TEXT)        |        | observed_at (TEXT, indexed)     |
  | scan_proves_safe (INT, CHECK=0) |        | provenance_source (TEXT)        |
  +---------------------------------+        | scan_proves_safe (INT, CHECK=0) |
                                             +---------------------------------+

                                             +---------------------------------+
                                             |       application_entities      |
                                             +---------------------------------+
                                             | entity_urn (PK, TEXT)           |
                                             | device_id (TEXT, indexed)       |
                                             | bundle_id (TEXT, indexed)       |
                                             | app_name (TEXT)                 |
                                             | version (TEXT)                  |
                                             | install_path (TEXT)             |
                                             | ownership (TEXT, indexed)       |
                                             | code_signature_json (TEXT)      |
                                             | observed_at (TEXT, indexed)     |
                                             | provenance_source (TEXT)        |
                                             | scan_proves_safe (INT, CHECK=0) |
                                             +---------------------------------+
```

---

## 3. Mandatory Safety & Architectural Invariants

1. **Relational Entity Integrity (`INV-DB-01`):** All entities are keyed by their canonical URN adhering to RFC 4122 / URN specifications (`urn:systemmind:<domain>:<qualifier>`).
2. **Privacy Preservation (`INV-DB-02` / `SC-04`):** Raw hardware serial numbers and personal user account paths are never stored unhashed in tables or logs. Serials are stored as SHA-256 digests (`serial_hash`).
3. **Tripartite Component Ownership (`INV-DB-03`):** Every application entity records explicit `ComponentOwnership` (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, or `USER_MANAGED`). Queries and policies can strictly filter and isolate user applications from autonomous maintenance mutations.
4. **Inviolable "Scan != Safe" Invariant (`INV-DB-04` / `SC-03`):** The schema enforces `scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)` at the SQLite database engine level, and `scan_proves_safe: bool = False` at the Python dataclass level. No database record can assert or imply safety.
5. **Reversible Migrations (`INV-DB-05`):** All migration files contain paired, deterministic `-- UP` and `-- DOWN` clauses, validated by `DatabaseMigrationValidator` in CI pipelines.
6. **Zero Ambient Shell Authority (`SC-01` / `INV-DB-06`):** Database queries and model manipulations execute entirely in-memory using parameterized SQL queries with zero ambient shell processes.

---

## 4. Verification & Acceptance Criteria
- Migration `0003_hardware_os_application_entities.sql` successfully applies and rolls back cleanly under `DatabaseMigrator`.
- Python models (`HardwareEntityRecord`, `OsKernelEntityRecord`, `ApplicationEntityRecord`) in `src/system_mind/database/entity_models.py` pass full round-trip serialization and invariant checks.
- Entity repository (`EntityRepository`) in `src/system_mind/database/entity_repo.py` provides transactional CRUD and indexed filtering.
- Developer CLI tool (`tools/detect_database_entities.py`) seeds mock records and audits database state.
- Automated packaging validator (`DatabaseEntitiesValidator`) in `src/system_mind/packaging/database_entities.py` passes AST safety and file completeness.
- Comprehensive test suite in `tests/test_database_entity_models.py` passes 100%.
- Formalized ADR-078 in `docs/DECISION_LOG.md`.
