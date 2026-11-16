# DAY 028 — Architecture Design Note: Rust System-Agent Workspace and Crate Boundaries

**Component:** Native System Daemon, Capability Broker & Kernel Sensor Workspace  
**Layer:** Layer 1 (Physical Sensors), Layer 2 (Capability Broker), Layer 6 (Narrow Trusted Broker)  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Today establishes the **Rust System-Agent Workspace and Crate Boundaries** (`crates/`), fulfilling the Day 028 objective of Milestone 3 (Repository and development foundation, Days 026–040).

In SYSTEM MIND X, native operating system execution and hardware sensor collection are bifurcated from the high-level Python AI cognitive planner (ADR-021 through ADR-024). The native broker must run as a high-performance, memory-safe, statically verified system daemon with minimal resource footprint (<50MB baseline RSS, ADR-012) and zero reliance on Python runtimes.

To maintain strict boundary encapsulation, the native system-agent is organized into three segregated crates:
1. **`system-mind-common`** (Foundational): Core types, capability identifiers, privilege levels, risk tiers, file trust states, RFC 7807 error categories, and canonical SHA-256 hashing primitives. Completely decoupled from platform APIs.
2. **`system-mind-sensors`** (Layer 1 & 2): Native sensor adapters (macOS, Windows, Linux) and non-privileged telemetry collection (CPU, memory, disk, thermal, process state).
3. **`system-mind-broker`** (Layer 6 Daemon): The narrow, privileged capability broker enforcing precondition/postcondition verification, the "Scan != Safe" invariant, user-application mutation guards, and atomic rollback triggering.

---

## 2. Crate Architecture & Dependency Graph

```
crates/
├── system-mind-common/               [Leaf Crate: Pure Types, Errors, Hashes]
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── types.rs
│       ├── error.rs
│       └── crypto.rs
│
├── system-mind-sensors/              [Depends on: system-mind-common]
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── telemetry.rs
│       └── adapters/
│           ├── mod.rs
│           └── mock.rs
│
└── system-mind-broker/               [Depends on: system-mind-common, system-mind-sensors]
    ├── Cargo.toml
    └── src/
        ├── lib.rs
        ├── broker.rs
        └── main.rs
```

### Dependency Invariant Direction
$$\text{system-mind-broker} \longrightarrow \text{system-mind-sensors} \longrightarrow \text{system-mind-common}$$
- **Zero Circular Dependencies**: Strict acyclic dependency flow.
- **Zero Python Runtime Dependency**: Crates compile into standalone native binaries without linking against `libpython`.
- **Zero Raw Shell Execution**: Capability dispatch is mediated through strongly typed capability enums and verified grants.

---

## 3. Crate Boundary Specifications

| Crate Name | Role | Primary Modules | Allowed Inbound | Allowed Outbound |
| :--- | :--- | :--- | :--- | :--- |
| `system-mind-common` | Core domain types & serialization | `types`, `error`, `crypto` | `system-mind-sensors`, `system-mind-broker` | Standard library only |
| `system-mind-sensors`| Telemetry & sensor abstraction | `telemetry`, `adapters` | `system-mind-broker` | `system-mind-common` |
| `system-mind-broker` | Narrow privileged daemon | `broker`, `main` | External clients via IPC | `system-mind-common`, `system-mind-sensors` |

---

## 4. Safety & Security Invariants

1. **Precondition Gating**: The broker mathematically prohibits capability dispatch if preconditions evaluate to false.
2. **Scan != Safe Enforced**: Untrusted files cannot be dispatched to native host execution; broker rejects unverified execution requests with `PreconditionFailure`.
3. **Tripartite Ownership Guard**: Autonomous maintenance calls attempting to mutate `USER_MANAGED` components are rejected with `GovernanceCharterInvariant`.
4. **Non-Privileged Host Execution**: During development and testing, all platform actions run through mock adapters without requiring elevated root or administrator privileges on the developer's macOS machine.
