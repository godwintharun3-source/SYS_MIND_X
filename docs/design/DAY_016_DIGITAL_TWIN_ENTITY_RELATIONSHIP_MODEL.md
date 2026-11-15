# Design Note: Day 016 — Digital-Twin Entity and Relationship Model

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Temporal Digital Twin (Layer 4) / Entity-Relationship Graph / ADR-026
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Problem Statement

Current computer-agent architectures suffer from **representational ephemerality**: they operate either by taking periodic screenshots (which discard structural, process, and filesystem metadata) or by invoking ad-hoc shell commands whose outputs vanish after execution. When an agent attempts to remediate an issue, it lacks a coherent understanding of:
- What process spawned the failing job.
- Whether a target directory is `SYSTEM_MANAGED`, `VENDOR_MANAGED`, or `USER_MANAGED`.
- Which packages or runtime libraries an application depends upon.
- The provenance, quarantine state, and cryptographic hash of executed binaries.

SYSTEM MIND X eliminates this gap by establishing a **Persistent Temporal Digital Twin (Layer 4)**. The digital twin maintains a continuous, queryable graph of host state that mirrors physical and logical system entities and their interrelationships in near real-time.

Day 016 formalizes the **Entity and Relationship Model** of the digital twin, establishing strongly typed schemas, canonical identifiers, adjacency queries, referential integrity rules, and privacy protections.

---

## 2. Digital Twin Architecture and Graph Topology

```
+---------------------------------------------------------------------------------------------------+
|                                  TEMPORAL DIGITAL TWIN GRAPH                                      |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [HOST ENTITY]                                                                                    |
|  urn:twin:host:local-node ──(CONTAINS)──► [SECURITY POSTURE] (SIP: active, Gatekeeper: active)    |
|       │                                                                                           |
|       ├──(CONTAINS)──► [HARDWARE DEVICE] (CPU M1, RAM 8GB, Thermal Sensor)                        |
|       │                                                                                           |
|       ├──(RUNS)──────► [OS KERNEL] (Darwin 27.0.0, arm64)                                         |
|       │                                                                                           |
|       └──(CONTAINS)──► [APPLICATION] (Google Chrome, ownership: USER_MANAGED)                     |
|                             │                                                                     |
|                             ├──(DEPENDS_ON)──► [PACKAGE] (Python 3.12, ownership: USER_MANAGED)   |
|                             │                                                                     |
|                             └──(EXECUTES)────► [PROCESS] (PID 4012, Google Chrome)                |
|                                                     │                                             |
|                                                     ├──(SPAWNED_BY)──► [PROCESS] (PID 1, launchd)  |
|                                                     │                                             |
|                                                     ├──(WRITES_TO)───► [FILESYSTEM NODE] (/tmp)   |
|                                                     │                                             |
|                                                     └──(COMMUNICATES)► [NETWORK SOCKET] (TCP 443) |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Entity Classification (`TwinEntityType`)

The digital twin models ten primary entity classes:

1. **`HOST`**: Physical or virtual machine node (hostname, machine_id, architecture, total_memory_bytes, cpu_cores).
2. **`OS_KERNEL`**: OS kernel instance (family, release, version, boot_time, uptime_seconds).
3. **`HARDWARE_DEVICE`**: Hardware components and sensors (device_type, model, vendor, sensor_readings, status).
4. **`FILESYSTEM_NODE`**: Files, directories, symbolic links, and volumes (path, file_type, size_bytes, sha256_hash, quarantine_status, permissions, ownership).
5. **`PACKAGE_DEPENDENCY`**: Software packages, package manager manifests, and toolchain dependencies (package_name, version, package_manager, license, component_ownership).
6. **`APPLICATION`**: Installed software applications (app_name, bundle_id, install_prefix, version, executable_path, component_ownership).
7. **`PROCESS`**: Live execution units (pid, ppid, executable_path, command_line, user, memory_rss_bytes, cpu_percent, state).
8. **`NETWORK_SOCKET`**: Network interfaces, listening sockets, and active connections (protocol, local_address, local_port, remote_address, remote_port, state).
9. **`SECURITY_POSTURE`**: Host security mechanism states (sip_enabled, gatekeeper_status, wdac_status, firewall_active, secure_boot_active).
10. **`CONFIGURATION_SETTING`**: System and user configuration key-values (key, value, domain, file_origin, is_sensitive).

---

## 4. Relationship Classification (`TwinRelationType`)

Edges in the digital twin graph are directed, typed, and timestamped:

1. **`CONTAINS`**: Structural composition (e.g. `Host CONTAINS HardwareDevice`, `Directory CONTAINS File`).
2. **`SPAWNED_BY`**: Process ancestry hierarchy (e.g. `Child Process SPAWNED_BY Parent Process`).
3. **`DEPENDS_ON`**: Functional dependency (e.g. `Application DEPENDS_ON PackageDependency`, `Process DEPENDS_ON ConfigurationSetting`).
4. **`OWNS`**: Component ownership boundary (e.g. `System/User OWNS Component`).
5. **`ENFORCES_POLICY`**: Security authority enforcement (e.g. `SecurityPosture ENFORCES_POLICY on Process`).
6. **`COMMUNICATES_VIA`**: Network connection binding (e.g. `Process COMMUNICATES_VIA NetworkSocket`).
7. **`WRITES_TO`**: Filesystem modification I/O edge (e.g. `Process WRITES_TO FilesystemNode`).
8. **`READS_FROM`**: Filesystem inspection I/O edge (e.g. `Process READS_FROM FilesystemNode`).
9. **`AFFECTS`**: Mutation relationship linking planned operations to target entities (e.g. `ActionContract AFFECTS FilesystemNode`).

---

## 5. Cardinal Invariants of the Digital Twin Model

1. **Mandatory Tripartite Ownership:**
   $$\forall e \in \text{Entities}: e.\text{ownership} \in \{\text{SYSTEM\_MANAGED}, \text{VENDOR\_MANAGED}, \text{USER\_MANAGED}\}$$
   No entity can exist without an explicit component ownership classification. This guarantees that user-managed applications and developer virtualenvs are never misidentified as system components.

2. **Referential Integrity:**
   $$\forall r = (s, t) \in \text{Relationships}: s \in \text{Entities} \land t \in \text{Entities}$$
   Dangling relationships referencing nonexistent source or target entities are rejected. Removing an entity automatically cascades to purge its associated relationships.

3. **Provenance Attribution:**
   $$\forall e \in \text{Entities}: e.\text{provenance\_source} \ne \emptyset \land e.\text{created\_at} \ne \emptyset$$
   Every entity must identify the observing intelligence engine (e.g. `ENG-01:telemetry`, `ENG-09:fsevents`) and precise timestamp.

4. **Zero Cleartext Private Data (Privacy Invariant):**
   Raw contents of user files, passwords, private keys, or personal documents are strictly prohibited in `attributes`. Filesystem nodes record only paths, metadata, cryptographic hashes (SHA-256), and quarantine tags.

---

## 6. Architectural Decision Record (ADR-026)

- **Title:** Digital-Twin Entity and Relationship Model and Graph Referential Integrity
- **Status:** Accepted.
- **Context:** Agent operations require structural awareness of host state across hardware, processes, files, packages, and security controls without relying on fragile screen OCR or ephemeral terminal dumps.
- **Decision:** SYSTEM MIND X implements a typed, in-memory graph entity-relationship model in Layer 4 (`DigitalTwinGraph`). The graph models 10 entity types and 9 relationship types with enforced component ownership, provenance attribution, referential integrity, and privacy redaction.
- **Consequences:** Provides the foundation for temporal state diffing (Day 017), application ownership exclusion (Day 018), and autonomous maintenance policy validation.
