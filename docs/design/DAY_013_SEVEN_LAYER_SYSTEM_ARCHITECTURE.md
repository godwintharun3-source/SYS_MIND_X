# Design Note: Day 013 — The Seven-Layer System Architecture & Component Boundaries

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Core Architecture / System Layers / Component Boundaries
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Architectural Hierarchy

To prevent ambient privilege escalation, prompt injection bypasses, and unmediated operating system access, SYSTEM MIND X is structured as a **Seven-Layer Hierarchical Architecture**. 

Every subsystem and intelligence engine is strictly assigned to one of seven formal layers. Communication across layer boundaries is governed by the **Rule of Strict Layer Adjacency** and the **Directional Invariant** (Downward Execution vs Upward Observation).

```
+------------------------------------------------------------------------------------+
|                               THE SEVEN ARCHITECTURAL LAYERS                       |
+------------------------------------------------------------------------------------+
|                                                                                    |
|  LAYER 1: PRESENTATION & INTERFACE LAYER                                           |
|  (Chat UI, Caretaker Dashboard, CLI, Interactive Approval Dialogues)               |
|                                     │                                              |
|                                     ▼ (Structured User Intent)                     |
|  LAYER 2: COGNITIVE PLANNING & CONTEXT PLANE                                       |
|  (Multimodal AI Planner, Context Engine, Knowledge Retrieval ENG-11, App Context)  |
|                                     │                                              |
|                                     ▼ (Typed ActionContract - Declarative)         |
|  LAYER 3: DETERMINISTIC POLICY & GOVERNANCE ENGINE                                 |
|  (Independent Non-LLM Invariant Checker, Persona Evaluator, Safety Constraints)    |
|                                     │                                              |
|                                     ▼ (Verified Capability Grant)                  |
|  LAYER 4: TEMPORAL DIGITAL TWIN & PROVENANCE STORE                                 |
|  (Append-Only Event Store ENG-01, File Provenance ENG-06, SQLite WAL Index)        |
|                                     │                                              |
|                                     ▼ (Pre/Post Assertion Context)                 |
|  LAYER 5: NARROW PRIVILEGED EXECUTION BROKER                                       |
|  (Least-Privilege Broker Daemon ENG-10, Atomic Rollback Compensation Handlers)     |
|                                     │                                              |
|                                     ▼ (Normalized Platform IPC)                    |
|  LAYER 6: PLATFORM CAPABILITY ADAPTERS & SANDBOXING                                |
|  (Capability Registry ENG-12, Disposable Micro-VMs ENG-07, NixOS Engine ENG-13)   |
|                                     │                                              |
|                                     ▼ (Native Kernel APIs / Entitlements)          |
|  LAYER 7: NATIVE OS KERNEL & PHYSICAL HARDWARE                                     |
|  (Native OS Kernels XNU/NT/Linux, SIP, WDAC, TPM, Sensors ENG-03, Daemons ENG-14)  |
|                                                                                    |
+------------------------------------------------------------------------------------+
```

---

## 2. Layer Specifications & Component Envelopes

### Layer 1: Presentation & Interface Layer (`L1_PRESENTATION`)
- **Primary Roles:** User-facing interaction, caretaker health visualization, CLI tooling, explicit user consent prompts.
- **Engines:** UI Viewers, Caretaker Dashboard consumer.
- **Privilege:** Unprivileged user space.
- **Permitted Interactions:** May call Layer 2 for planning and Layer 4 for read-only telemetry queries. Never calls Layer 3, 5, 6, or 7.

### Layer 2: Cognitive Planning & Context Plane (`L2_COGNITIVE_PLANE`)
- **Primary Roles:** Multimodal LLM reasoning, intent decomposition, contextual planning, prompt generation.
- **Engines:** `ENG-02` (App Context), `ENG-08` (Developer Lifecycle), `ENG-09` (Predictive Caretaker), `ENG-11` (Knowledge Retrieval).
- **Privilege:** Strictly unprivileged user process. Possesses zero OS mutation entitlements.
- **Permitted Interactions:** May receive requests from Layer 1; queries Layer 4 (Digital Twin); dispatches proposed actions exclusively to Layer 3 via typed `ActionContract`s. Never calls Layer 5, 6, or 7 directly.

### Layer 3: Deterministic Policy & Governance Engine (`L3_POLICY_ENGINE`)
- **Primary Roles:** Non-LLM rule evaluation, charter invariant enforcement, persona governance envelopes, safety constraint checking (`SC-01..08`).
- **Engines:** `ENG-04` (Adaptive Governance Policy), Charter Validator, Persona Evaluator, Safety Constraint Validator.
- **Privilege:** Unprivileged deterministic pure-function engine.
- **Permitted Interactions:** Receives proposed `ActionContract`s from Layer 2; queries Layer 4 for historical state; issues `VerifiedCapabilityGrant` downward exclusively to Layer 5.

### Layer 4: Temporal Digital Twin & State Store (`L4_DIGITAL_TWIN`)
- **Primary Roles:** Append-only temporal graph, event-sourced host state model, file provenance tracking, snapshot reconciliation.
- **Engines:** `ENG-01` (Digital Twin), `ENG-06` (File Intelligence).
- **Privilege:** Unprivileged local storage access (SQLite WAL).
- **Permitted Interactions:** Serves read queries to Layers 1, 2, 3, and 5; receives validated telemetry event streams from Layer 6/7.

### Layer 5: Narrow Privileged Execution Broker (`L5_EXECUTION_BROKER`)
- **Primary Roles:** Verified capability execution, precondition verification, postcondition assertion, atomic compensation rollbacks, cryptographic audit trails.
- **Engines:** `ENG-10` (Verified Execution Broker).
- **Privilege:** Isolated daemon operating with narrow least-privilege rights (or root broker where mandated).
- **Permitted Interactions:** Accepts execution requests ONLY from Layer 3 with a valid `VerifiedCapabilityGrant`; queries Layer 4 for pre/post-state hashes; dispatches mutations to Layer 6 adapters.

### Layer 6: Platform Capability Adapters & Sandboxing (`L6_PLATFORM_ADAPTERS`)
- **Primary Roles:** OS-specific API normalization, disposable micro-VM isolation, container sandboxing, declarative generation rebuilds.
- **Engines:** `ENG-07` (Sandboxing), `ENG-12` (Capability Registry), `ENG-13` (NixOS Foundation), platform adapters (`macOSAdapter`, `WindowsAdapter`, `LinuxAdapter`).
- **Privilege:** Sandboxed platform execution with explicit entitlements (Hypervisor.framework, KVM, WHPX).
- **Permitted Interactions:** Receives typed dispatch commands from Layer 5; invokes Layer 7 kernel system calls; streams telemetry events to Layer 4.

### Layer 7: Native OS Kernel & Physical Hardware (`L7_KERNEL_HARDWARE`)
- **Primary Roles:** Underlying native OS kernels (Darwin/XNU, Windows NT, Linux), platform security controls (SIP, Gatekeeper, WDAC, SELinux, Landlock), physical hardware sensors, native launch daemons.
- **Engines:** `ENG-03` (Sensors), `ENG-14` (Host Companion Agents), native OS kernels.
- **Privilege:** Kernel and root hardware context.
- **Permitted Interactions:** Invoked by Layer 6 adapters; streams telemetry up to Layer 4 and 6.

---

## 3. The Three Cardinal Architectural Invariants

1. **Rule of Strict Adjacency (Bypass Prevention):**
   No layer may bypass an adjacent layer in the mutating execution path. Specifically, Layer 2 (AI Planner) can never directly invoke Layer 5 (Broker), Layer 6 (Adapters), or Layer 7 (Kernel). All requests must pass through Layer 3 (Deterministic Policy Engine).

2. **Directional Separation Invariant:**
   - **Downward Execution:** Requests to alter state flow strictly downward: Layer 2 -> Layer 3 -> Layer 5 -> Layer 6 -> Layer 7.
   - **Upward Observation:** Telemetry and event streams flow strictly upward: Layer 7 -> Layer 6 -> Layer 4 -> Layer 2.

3. **Autonomous Boundary Invariant:**
   Autonomous maintenance sweeps originating in Layer 2/5 can **never** target components marked `USER_MANAGED` in Layer 4/6.
