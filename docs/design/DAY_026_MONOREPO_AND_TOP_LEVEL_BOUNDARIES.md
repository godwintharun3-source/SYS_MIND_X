# DAY 026 — Architecture Design Note: Monorepo Architecture and Top-Level Boundaries

**Component:** Developer Foundation, Workspace Boundaries & Monorepo Topology  
**Layer:** Cross-Cutting Infrastructure (Milestone 3: Days 026–040)  
**Date:** 2026-11-15  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Problem Formulation

SYSTEM MIND X is a complex, safety-critical polyglot software system combining:
1. A **High-Level Cognitive Control Plane** written in Python (AI Planning, Temporal Digital Twin, Caretaker Heuristics, Context Engine).
2. A **Narrow Privileged Capability Broker & Native System Daemon** written in Rust (Kernel Sensor Adapters, Sandbox Runner, Precondition/Postcondition Verification, Cryptographic Audit Ledger).
3. A **Desktop UI & Operator Shell** written in React/TypeScript and Tauri (System Visualizer, Approval Dialogs, Privacy Controls).
4. **Shared Schemas & Wire Contracts** defining typed action contracts, API request/response envelopes, and audit event definitions.
5. **Developer Tooling & Invariant Checkers** managing day tracking, release gates, and compliance validation.

In a polyglot system of this scale, an ad-hoc single-folder repository layout or loosely coordinated multi-repo structure leads to:
- **Dependency Drift & Version Desynchronization**: Rust broker contracts and Python planner contracts drifting out of lockstep.
- **Leaky Privilege Boundaries**: High-level UI or Python code attempting direct unmediated file or process mutations, bypassing the narrow privileged broker.
- **Non-Reproducible Builds**: Unclear dependency isolation, conflicting toolchains, and lack of deterministic boundary enforcement.

**The SYSTEM MIND Solution:**  
Establish a **Strictly Boundary-Enforced Polyglot Monorepo** anchored by an explicit workspace manifest (`monorepo.json`), documented boundary contracts (`BOUNDARY.md` / `README.md` per top-level zone), and an automated verification engine (`MonorepoBoundaryValidator`).

---

## 2. Top-Level Monorepo Topology

```
SYSTEM_MIND_X_MONOREPO/
├── apps/                        # Layer 7: Desktop Applications & UI
│   └── desktop/                 # React/TypeScript + Tauri desktop shell
├── crates/                      # Layer 1, 2, 6: Rust System Workspace
│   ├── system-mind-broker/      # Narrow privileged capability broker daemon
│   ├── system-mind-sensors/     # Native OS sensors (macOS, Windows, Linux)
│   └── system-mind-common/      # Core Rust types and hashing primitives
├── src/system_mind/             # Layer 3, 4, 5, 6: Python Control Plane
│   ├── twin/                    # Temporal Digital Twin & Property Graph
│   ├── engines/                 # 14 Intelligence Engines
│   ├── governance/              # Policy Precedence, Roles & Identity
│   ├── audit/                   # Audit Ledger & Secret Redaction
│   └── api/                     # Wire Envelopes, RFC 7807 & SemVer
├── schemas/                     # Shared Language-Neutral Contracts & IDLs
│   ├── action_contracts/        # Typed Action Contract schemas
│   └── api_envelopes/           # Wire envelope JSON schemas
├── docs/                        # Architecture Specs, ADRs, Design Notes
├── tools/                       # Developer Tooling, Gate Verifiers, Day Tracker
├── tests/                       # Cross-cutting Integration, Unit & Contract Tests
├── monorepo.json                # Canonical Machine-Readable Monorepo Manifest
└── pyproject.toml               # Python Workspace & Dependency Config
```

---

## 3. Top-Level Workspace Boundaries & Invariant Matrix

| Workspace | Primary Language | Architectural Layers | Permitted Inbound Dependencies | Permitted Outbound Dependencies | Boundary Invariant |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `apps/` | TypeScript / Rust (Tauri) | Layer 7 (Presentation) | None (End-user interface) | `schemas/`, `api/` (Wire RPC only) | Strictly prohibited from direct host kernel calls or importing internal broker crates. |
| `crates/` | Rust (2021 edition) | Layer 1, 2, 6 (Broker & Sensors) | `apps/` (IPC only), `src/` (IPC only) | `schemas/` | Sole executor of privileged system capabilities. No dependency on Python runtime. |
| `src/` | Python 3.10+ | Layer 3, 4, 5, 6 (Planner/Twin/Policy) | None (Internal service) | `schemas/`, `crates/` (via IPC wire contract) | Non-privileged observer and planner. Cannot bypass broker to mutate host state. |
| `schemas/` | JSON Schema / Cap'n Proto | Layer 6, 7 (Contracts & Envelopes) | `apps/`, `crates/`, `src/`, `tools/` | None (Self-contained) | Strictly language-neutral and self-contained. Zero implementation logic. |
| `tools/` | Python / Shell | Developer Tooling & Verification | CI / Developer invocation | `src/`, `schemas/`, `monorepo.json` | Tooling code cannot be bundled into production binaries or daemon runtime. |
| `docs/` | Markdown / Mermaid / KaTeX | Documentation & Governance | Human operators & agents | None | Source of architectural truth. Zero executable code. |

---

## 4. Boundary Rules & Programmatic Validation

The `MonorepoBoundaryValidator` programmatically evaluates:
1. **Directory Integrity**: All 6 top-level workspaces exist and contain boundary documentation (`README.md` or `BOUNDARY.md`).
2. **Dependency Direction Legality**: Validates the dependency matrix to prevent cyclic or forbidden dependencies (e.g. `apps` importing internal `crates` source directly, or `crates` importing `src`).
3. **Toolchain Segregation**: Verifies that language-specific configuration files reside in their designated workspace boundaries.
4. **Secret & Privacy Perimeter**: Verifies `.gitignore` excludes private artifacts, build outputs, and local environment files from all workspaces.
