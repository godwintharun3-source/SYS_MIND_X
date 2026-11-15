# Crates Boundary (`crates/`)

**Architectural Layers:** Layer 1 (Physical Sensors), Layer 2 (Capability Broker), Layer 6 (Narrow Trusted Broker Daemon)  
**Primary Technologies:** Rust (2021 Edition, Cargo Workspace)  
**Owner:** System Daemon & Core Platform Engineering  

---

## 1. Scope & Purpose
The `crates/` workspace contains the narrow, privileged system-agent daemon and native operating system capability adapters:
- `system-mind-broker`: The audited, least-privilege daemon executing validated capability grants.
- `system-mind-sensors`: Native hardware telemetry and filesystem event taps (macOS Endpoint Security/FSEvents, Windows ETW, Linux eBPF).
- `system-mind-common`: Core Rust types, cryptographic hash chaining, and serialization contracts.

## 2. Permitted Dependencies
- **Outbound:** `schemas/` (action contract and envelope schemas).
- **Inbound:** External clients via authenticated IPC wire protocol (`ApiRequest`/`ApiResponse`).

## 3. Boundary Invariants
1. **Sole Privileged Executor:** The Rust system broker is the sole privileged component with authority to invoke platform capability APIs.
2. **Deterministic Capability Verification:** Capabilities are only dispatched after verifying typed preconditions and caller authorization.
3. **Zero Python Dependency:** The Rust system daemon must compile into a standalone native binary without embedding or depending on the Python interpreter.
