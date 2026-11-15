# Design Note: Day 011 — Functional Requirements for the Fourteen Intelligence Engines

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Core Architecture / Intelligence Engines / Functional Requirements
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & System Topology

SYSTEM MIND X is structured around fourteen specialized, typed intelligence engines. Rather than routing all reasoning and OS interaction through an undifferentiated monolithic LLM, each engine fulfills a strictly bounded operational role with typed input/output contracts, explicit error states, permission envelopes, and safety constraints.

```
+------------------------------------------------------------------------------------+
|                               THE SYSTEM MIND X TOPOLOGY                           |
+------------------------------------------------------------------------------------+
|                                                                                    |
|  [OBSERVATION ENGINES]                                                             |
|  - ENG-03: Sensor Awareness         --> [ENG-01: Temporal Digital Twin]            |
|  - ENG-02: App Context Intelligence --> [Indexes & Provenance Event Store]         |
|  - ENG-14: Host Companion Agents    -->                                            |
|                                                                                    |
|  [REASONING & SYNTHESIS ENGINES]                                                   |
|  - ENG-11: Knowledge & Cognitive Retrieval Plane                                   |
|  - ENG-08: Developer Lifecycle Intelligence                                        |
|  - ENG-09: Predictive Caretaker & Reporting                                        |
|  - ENG-05: Autonomous OS Maintenance Engine (Strictly System-Managed Only)          |
|  - ENG-06: Universal File Intelligence (Quarantine, Provenance, Metadata)          |
|                                                                                    |
|  [GOVERNANCE & SAFETY BROKERAGE]                                                   |
|  - ENG-04: Adaptive Governance & Policy Engine (Deterministic Rule Invariants)     |
|                                                                                    |
|  [EXECUTION & ENFORCEMENT BROKERAGE]                                               |
|  - ENG-10: Risk-Adaptive Verified Execution Broker (Pre/Post/Rollback)             |
|  - ENG-07: Controlled File Execution & Sandboxing (Disposable Isolation)          |
|  - ENG-12: Universal Capability Registry (Cross-Platform API Contracts)            |
|  - ENG-13: Linux / NixOS System Mind OS Foundation (Declarative Generations)       |
|                                                                                    |
+------------------------------------------------------------------------------------+
```

---

## 2. Functional Requirements Matrix for the Fourteen Engines

### Engine 01: Persistent Temporal Digital Twin (`ENG-01`)
- **Purpose:** Append-only temporal graph/event log recording system configuration, hardware metrics, process states, and file provenance over time.
- **Inputs:** Telemetry snapshots, OS event streams (FSEvents, ETW, eBPF), broker state mutations.
- **Outputs:** Temporal state queries, diffs between timestamps, entity relationship graphs, freshness metrics.
- **Error States:** `CORRUPTED_EVENT_LOG`, `STALE_SNAPSHOT`, `STORAGE_CEILING_REACHED`.
- **Permissions:** Unprivileged user storage access (local SQLite / WAL).
- **Unsupported Platform Behavior:** Degrades to in-memory non-persistent circular buffer if filesystem persistence is unavailable.
- **Safety Boundary:** Never records private user directories (`~/.ssh`, `~/.gnupg`, `~/Documents`) or keystrokes.

### Engine 02: Application Context Intelligence (`ENG-02`)
- **Purpose:** Semantic awareness of active applications, open document contexts, frontmost window focus, and background resource usage.
- **Inputs:** Window server focus events, active process IDs, workspace root descriptors.
- **Outputs:** `ApplicationContextSnapshot` (active app bundle ID, title, workspace mode, focused window ID).
- **Error States:** `ACCESSIBILITY_PERMISSION_DENIED`, `PROCESS_LOOKUP_TIMEOUT`, `ORPHANED_WINDOW_EVENT`.
- **Permissions:** OS Accessibility / Screen Recording permission where strictly required by platform; degrades gracefully if missing.
- **Unsupported Platform Behavior:** Falls back to PID and process commandline polling when accessibility events are unsupported.
- **Safety Boundary:** Strict exclusion of password manager windows, private browser tabs, and sensitive document fields. Zero continuous OCR recording.

### Engine 03: Hardware & OS Sensor Awareness (`ENG-03`)
- **Purpose:** Collects hardware health metrics (CPU thermals, fan speeds, memory pressure, battery cycles, disk wear/SMART).
- **Inputs:** Platform sensor calls (IOKit on macOS, WMI/SMART on Windows, sysfs/hwmon on Linux).
- **Outputs:** `SensorTelemetryReport` with normalized SI units (celsius, percentage, megabytes, cycles).
- **Error States:** `SENSOR_READ_ERROR`, `PERMISSION_REQUIRED_FOR_SMC`, `UNSUPPORTED_HARDWARE_INTERFACE`.
- **Permissions:** Unprivileged read where available; read-only root/admin entitlement for low-level SMART/SMC queries.
- **Unsupported Platform Behavior:** Tags missing sensor values as `PARTIAL` with documented fallback estimates.
- **Safety Boundary:** Purely read-only; zero hardware register writes or overclocking controls.

### Engine 04: Adaptive Governance & Policy Engine (`ENG-04`)
- **Purpose:** Independent, deterministic evaluation of all action contracts against charter invariants, persona governance, and threat constraints.
- **Inputs:** Proposed `ActionContract`, active `UserPersona`, session identity.
- **Outputs:** `PolicyDecision` (`PERMITTED`, `DENIED`, `APPROVAL_REQUIRED`) with explicit violation traces.
- **Error States:** `INVALID_CONTRACT_SCHEMA`, `UNKNOWN_PERSONA`, `CIRCULAR_POLICY_DEPENDENCY`.
- **Permissions:** Runs in unprivileged user space as a deterministic pure function (no OS mutations).
- **Unsupported Platform Behavior:** Platform-agnostic; evaluates identical deterministic logic across all platforms.
- **Safety Boundary:** Totally independent of LLM reasoning; an LLM cannot convince this engine to grant unauthorized access.

### Engine 05: Autonomous OS Maintenance Engine (`ENG-05`)
- **Purpose:** Policy-driven preventative maintenance: cleaning temporary caches, vacuuming systemd journals, rotating system logs, and updating base OS definitions.
- **Inputs:** System health alerts, scheduled maintenance triggers, system idle status, AC power presence.
- **Outputs:** Batch of typed maintenance `ActionContract`s for broker dispatch.
- **Error States:** `SYSTEM_ON_BATTERY_POWER`, `HIGH_SYSTEM_LOAD_DEFERRAL`, `COMPONENT_OWNERSHIP_CONFLICT`.
- **Permissions:** Generates unprivileged contracts; elevated mutations require broker mediation.
- **Unsupported Platform Behavior:** Skips platform-specific tasks (e.g. systemd vacuum on macOS) with explicit log entries.
- **Safety Boundary:** Invariant: Strictly prohibited from touching `USER_MANAGED` components (browsers, IDEs, pip/npm environments).

### Engine 06: Universal File Intelligence & Provenance (`ENG-06`)
- **Purpose:** Tracks file origins (download URL, Mark-of-the-Web, quarantine flags), cryptographic hashes (SHA-256), MIME types, and static heuristic signatures.
- **Inputs:** File paths, filesystem change events, quarantine attributes.
- **Outputs:** `FileProvenanceRecord` (origin, download timestamp, hashes, quarantine state, risk score).
- **Error States:** `FILE_NOT_FOUND`, `READ_PERMISSION_DENIED`, `METADATA_UNAVAILABLE`.
- **Permissions:** Read-only access to monitored filesystem directories.
- **Unsupported Platform Behavior:** Omits platform-specific metadata (e.g. Zone.Identifier on Linux) while maintaining SHA-256 baseline.
- **Safety Boundary:** Invariant: "Scan does not equal safe." A low risk score never entitles native execution without isolation.

### Engine 07: Controlled File Execution & Sandboxing (`ENG-07`)
- **Purpose:** Isolates and detonate untrusted binaries inside disposable micro-VMs, containers, or hardened read-only handlers.
- **Inputs:** Target binary path, execution parameters, containment profile (`DISPOSABLE_ISOLATION` or `HARDENED_VIEWER`).
- **Outputs:** `SandboxedExecutionTrace` (file modifications, network attempts, process tree, exit code).
- **Error States:** `HYPERVISOR_UNAVAILABLE`, `CONTAINER_SPAWN_TIMEOUT`, `SANDBOX_ESCAPE_DETECTED`.
- **Permissions:** Virtualization entitlement (Hypervisor.framework, WHPX, KVM).
- **Unsupported Platform Behavior:** Falls back to `HARDENED_VIEWER` or denies execution if micro-isolation hypervisor is missing.
- **Safety Boundary:** No host filesystem sharing; no ambient host network connectivity during detonation.

### Engine 08: Developer Lifecycle Intelligence (`ENG-08`)
- **Purpose:** Diagnoses developer toolchains, inspects build dependencies, validates compiler flags, and detects corrupted virtual environments.
- **Inputs:** Workspace directory path, project manifests (`pyproject.toml`, `package.json`, `Cargo.toml`).
- **Outputs:** `ToolchainDiagnosticsReport` (installed compilers, missing dependencies, stale locks, path conflicts).
- **Error States:** `UNKNOWN_BUILD_SYSTEM`, `CIRCULAR_DEPENDENCY_GRAPH`, `MANIFEST_SYNTAX_ERROR`.
- **Permissions:** Read-only inspection of developer workspace; workspace-scoped write commands only upon user initiation.
- **Unsupported Platform Behavior:** Uses cross-platform manifest parsing; ignores platform-specific build hooks gracefully.
- **Safety Boundary:** Invariant: Never automatically updates package dependencies or installs external packages without explicit interactive developer consent.

### Engine 09: Predictive Caretaker & Reporting (`ENG-09`)
- **Purpose:** Analyzes temporal telemetry to detect early degradation (disk wear, memory leaks, zombie process accumulation) and explains findings in plain language.
- **Inputs:** Stream of telemetry snapshots from `ENG-01` and `ENG-03`.
- **Outputs:** `CaretakerReport` (health score, degradation alerts, plain-language explanation, recommended actions).
- **Error States:** `INSUFFICIENT_TELEMETRY_HISTORY`, `PREDICTION_ANOMALY_OVERFLOW`.
- **Permissions:** Purely analytical read-only engine.
- **Unsupported Platform Behavior:** Scales analysis scope based on available platform metrics.
- **Safety Boundary:** Recommendations must be approved by the user or validated by `ENG-04` before dispatch to `ENG-10`.

### Engine 10: Risk-Adaptive Verified Execution Broker (`ENG-10`)
- **Purpose:** The narrow, trusted execution daemon that mediates all consequential state mutations on the host OS.
- **Inputs:** Validated `ActionContract` (pre-approved by `ENG-04`).
- **Outputs:** `BrokerExecutionReceipt` (pre-state hash, post-state hash, execution duration, recovery handle).
- **Error States:** `PRECONDITION_FAILED`, `POSTCONDITION_FAILED`, `ROLLBACK_TRIGGERED`, `BROKER_IPC_TIMEOUT`.
- **Permissions:** Runs as isolated daemon with narrow capabilities (or root broker where mandated). AI is never root.
- **Unsupported Platform Behavior:** Delegates to platform-specific execution adapters (`macOSBroker`, `LinuxBroker`, `WindowsBroker`).
- **Safety Boundary:** Invariant: Rejects raw shell execution strings; enforces automated compensation rollback on postcondition failure.

### Engine 11: Knowledge & Cognitive Retrieval Plane (`ENG-11`)
- **Purpose:** Local, offline-capable vector and graph retrieval engine indexing system manuals, configuration schemas, command specifications, and incident playbooks.
- **Inputs:** Natural-language queries, error codes, configuration keys.
- **Outputs:** `RetrievalResult` (relevant manual passages, valid command schemas, remediation playbooks with source attribution).
- **Error States:** `INDEX_CORRUPT`, `QUERY_EMPTY`, `EMBEDDING_MODEL_UNAVAILABLE`.
- **Permissions:** Unprivileged local file reads of indexed documentation.
- **Unsupported Platform Behavior:** Fully portable local SQLite / embedding storage.
- **Safety Boundary:** Never ingests or indexes private directories (`~/.ssh`, `~/.gnupg`, `~/Documents`).

### Engine 12: Universal Capability Registry (`ENG-12`)
- **Purpose:** Normalizes operating system API divergences behind typed platform-agnostic capability contracts.
- **Inputs:** Capability queries (`CAP_STORAGE_SNAPSHOT`, `CAP_SERVICE_MANAGEMENT`, `CAP_FIREWALL_CONTROL`).
- **Outputs:** `CapabilityStatus` (`SUPPORTED`, `PARTIAL`, `UNSUPPORTED`, `MOCK_ONLY`) and platform adapter binding.
- **Error States:** `CAPABILITY_NOT_FOUND`, `ADAPTER_INITIALIZATION_FAILED`.
- **Permissions:** Unprivileged configuration registry.
- **Unsupported Platform Behavior:** Returns explicit `UNSUPPORTED` status with structured remediation instructions.
- **Safety Boundary:** Prevents false capability claims; forbids masking missing capabilities with unverified stubs.

### Engine 13: Linux / NixOS System Mind OS Foundation (`ENG-13`)
- **Purpose:** Manages declarative, reproducible system configuration and atomic generation rollbacks on NixOS / Linux platforms.
- **Inputs:** Declarative system configuration expressions, target generation IDs.
- **Outputs:** `NixGenerationReceipt` (generation number, closure hash, build duration, active generation link).
- **Error States:** `NIX_EVAL_ERROR`, `BUILD_CLOSURE_FAILED`, `ROLLBACK_GENERATION_NOT_FOUND`.
- **Permissions:** Root execution via narrow broker daemon for `nixos-rebuild switch` and `nix-env`.
- **Unsupported Platform Behavior:** Marked `UNSUPPORTED` on macOS/Windows host environments; active exclusively inside Linux / NixOS VMs.
- **Safety Boundary:** Rollback is atomic: failed generation activations automatically fall back to the last known working generation.

### Engine 14: Cross-Platform Host Companion Agents (`ENG-14`)
- **Purpose:** Lightweight native daemons deployed on host operating systems (macOS, Windows, Ubuntu) providing uniform telemetry capture and broker IPC.
- **Inputs:** Local OS notification events, IPC commands from SYSTEM MIND X control plane.
- **Outputs:** Standardized protobuf / JSON-RPC event streams (process lifecycle, mount events, network status).
- **Error States:** `HOST_IPC_DISCONNECTED`, `DAEMON_VERSION_MISMATCH`, `PERMISSION_REVOKED`.
- **Permissions:** Local native daemon entitlements (LaunchDaemon on macOS, Windows Service on Windows, systemd service on Linux).
- **Unsupported Platform Behavior:** Native implementation tailored to each supported platform target.
- **Safety Boundary:** Mutually authenticated local IPC (Unix domain socket / named pipe with PID and UID verification).
