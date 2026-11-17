# DAY 054: Prototype Endpoint Security Integration Feasibility and Entitlement Limits

**Date:** 2026-11-17  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Status:** In Progress / Prototyping  
**Author:** SYSTEM MIND X Architecture & Platform Engineering Team  

---

## 1. Executive Summary and Problem Statement

macOS Catalina (10.15) introduced the Apple Endpoint Security framework (`EndpointSecurity.framework`, backed by `libEndpointSecurity.dylib`), deprecating legacy Kernel Authorizations (`kauth`) and TrustedBSD Mandatory Access Control (`mac_framework`) kernel extensions (KEXTs). Endpoint Security (ES) provides a low-level C API (`es_new_client`, `es_subscribe`, `es_event_t`) that allows registered client daemons to monitor and optionally authorize kernel-level security operations, such as binary execution (`ES_EVENT_TYPE_NOTIFY_EXEC` / `ES_EVENT_TYPE_AUTH_EXEC`), file creation/deletion, process forks, and mount operations.

However, Apple strictly gates Endpoint Security behind severe architectural and administrative boundaries:
1. **Restricted Entitlement:** Any binary initializing an ES client via `es_new_client()` must be cryptographically code-signed with the restricted entitlement `com.apple.developer.endpoint-security.client`. This entitlement cannot be self-granted by developers; it requires an explicit business justification, legal agreement, and formal grant from Apple Developer Relations tied to a specific Team ID and bundle ID.
2. **Root Execution Privilege:** The client binary must run as root (`geteuid() == 0`), typically configured as a LaunchDaemon in `/Library/LaunchDaemons` operating in the system domain.
3. **Full Disk Access (FDA) / TCC:** The client process must be granted Full Disk Access in macOS System Settings or via an Enterprise MDM configuration profile.
4. **System Integrity Protection (SIP) Enforcement:** On production macOS hosts with SIP enabled, the Darwin kernel (`kernelmanagerd` and `taskgated`) enforces entitlement signatures at runtime. If an unentitled or unprivileged binary attempts `es_new_client()`, the kernel instantly rejects the client with `ES_NEW_CLIENT_RESULT_ERR_NOT_ENTITLED` or `ES_NEW_CLIENT_RESULT_ERR_NOT_PRIVILEGED`.

Day 054 evaluates the feasibility and entitlement boundaries of Endpoint Security within the SYSTEM MIND X architecture. Because SYSTEM MIND X is designed as a least-privilege user companion agent (Days 041–065) operating without ambient root privileges, attempting to force ES execution on the host would violate foundational charter constraints (`AGENTS.md` and `PROJECT_CHARTER.md`).

Therefore, Day 054 establishes a read-only Endpoint Security feasibility inspector, entitlement auditor, and graceful degradation engine. The engine audits host capabilities, diagnoses entitlement deficiencies, safely records unsupported telemetry, and activates proven user-space fallbacks:
- **Filesystem Telemetry Fallback:** Apple CoreServices FSEvents (`MacFsEventsDetector`, implemented in Day 053).
- **Process Lifecycle Telemetry Fallback:** Darwin `sysctl` and `/bin/ps` process table scanning (`MacProcessDetector`, implemented in Day 049).
- **Service Telemetry Fallback:** `launchd` unprivileged domain queries (`MacServicesDetector`, implemented in Day 050).

---

## 2. Architectural Invariants

| ID | Title | Invariant Specification |
| :--- | :--- | :--- |
| `SC-01` | **Zero Ambient Shell Authority** | All subprocess queries dispatch via tokenized argument lists (`shell=False`) with strict timeouts (<= 3 seconds). No ambient shell invocation (`sh -c`, `bash -c`). |
| `INV-ES-01` | **Least-Privilege Companion Boundary** | The companion agent runs in unprivileged user space. The system NEVER prompts for `sudo`, escalates privileges, or executes root commands to force ES initialization. |
| `INV-ES-02` | **OS Security Integrity Preservation** | The system NEVER modifies, bypasses, or requests disabling of System Integrity Protection (`csrutil disable`), Gatekeeper, AMFI boot arguments (`amfi_get_out_of_my_way=1`), or kernel security configurations. |
| `INV-ES-03` | **Deterministic Entitlement Audit** | Feasibility analysis deterministically maps host state to Apple ES return codes (`ES_NEW_CLIENT_RESULT_ERR_NOT_ENTITLED`, `ES_NEW_CLIENT_RESULT_ERR_NOT_PRIVILEGED`, `ES_NEW_CLIENT_RESULT_ERR_NOT_PERMITTED`) with explicit diagnostic reasoning. |
| `INV-ES-04` | **Transparent Telemetry Fallbacks** | When ES is restricted or unavailable, the system transparently reports fallback mechanisms (FSEvents for filesystem monitoring, `sysctl` for process tracking), ensuring complete observability without privileged dependencies. |
| `INV-ES-05` | **Non-Negotiable Charter Invariant ("Scan != Safe")** | Low-level kernel event monitoring records process and file activity, not behavioral safety. All models structurally enforce `scan_proves_safe = False`. |
| `INV-ES-06` | **Passive Observation Only (Zero Mutating Auth)** | In the companion agent prototype, ES evaluation is purely observational (`NOTIFY` telemetry). Mutating authorization intercepts (`AUTH` events that block or abort operations) require a trusted privileged broker and are strictly inactive. |
| `INV-ES-07` | **Graceful Unsupported / Non-Darwin Fallback** | Non-Darwin hosts gracefully return `UNAVAILABLE_PLATFORM` or deterministic Apple Silicon mock fixtures; native tools never execute on unsupported kernels. |

---

## 3. Threat Model and Risk Boundary (STRIDE Alignment)

| STRIDE Threat | Potential Vulnerability | SYSTEM MIND X Architectural Defense |
| :--- | :--- | :--- |
| **Elevation of Privilege** | Agent attempts to obtain `sudo` or modify SIP configuration to run unapproved ES client. | `INV-ES-01` and `INV-ES-02` strictly prohibit root escalation or SIP modification. Agent operates exclusively in user space. |
| **Denial of Service** | Misconfigured `AUTH` client fails to respond to kernel deadline, causing system-wide hang. | Companion agent enforces passive `NOTIFY` telemetry only (`INV-ES-06`). Zero mutating `AUTH` handlers are registered in unprivileged space. |
| **Information Disclosure** | ES telemetry inspects private user activity across protected documents or personal directories. | Privacy filters exclude personal directory inspection, honoring monitored root perimeters established in Day 053. |
| **Tampering** | External adversary injects forged entitlement or fakes ES capability. | Entitlements are verified cryptographically via `codesign -d --entitlements` against the host kernel state. |
| **Repudiation** | Security events lack cryptographic origin attribution. | Telemetry captures CodeDirectory hashes (`cdhash`), signing identifiers, and Developer Team IDs for every event sample. |

---

## 4. Component Topology and Module Architecture

```
                                +--------------------------------------------+
                                |             SYSTEM MIND X Core             |
                                +--------------------------------------------+
                                                      |
                                     (Queries Telemetry & Feasibility)
                                                      v
                                +--------------------------------------------+
                                |         MacEndpointSecurityDetector        |
                                +--------------------------------------------+
                                       /              |               \
                        (Host Platform Audit)  (Privilege Check)   (Entitlement Audit)
                                     /                |                 \
                                    v                 v                  v
                   +-------------------+     +------------------+    +-------------------+
                   | Darwin 10.15+ OS  |     | os.geteuid() == 0|    | codesign -d       |
                   | Kernel Framework  |     | (Root check)     |    | --entitlements    |
                   +-------------------+     +------------------+    +-------------------+
                                    \                 |                  /
                                     \                |                 /
                                      v               v                v
                                +--------------------------------------------+
                                |            EsFeasibilityReport             |
                                | - status: RESTRICTED_NOT_ROOT / NOT_ENTITLED|
                                | - result_code: ERR_NOT_ENTITLED (3)        |
                                | - scan_proves_safe: False                  |
                                | - fallback_strategies: FSEvents / sysctl   |
                                +--------------------------------------------+
                                         |                         |
                                         v                         v
                       +---------------------------+     +---------------------------+
                       | crates/system-mind-sensors|     | tools/detect_endpoint_... |
                       | (Rust Native Collector)   |     | (CLI Audit Tool)          |
                       +---------------------------+     +---------------------------+
```

---

## 5. Fallback Matrix for Unprivileged Companion Execution

| Telemetry Domain | Privileged Endpoint Security API | Unprivileged Companion Fallback | Invariant Verification |
| :--- | :--- | :--- | :--- |
| **Filesystem Changes** | `es_subscribe(ES_EVENT_TYPE_NOTIFY_CREATE, ...)` | Apple CoreServices FSEvents (`MacFsEventsDetector`, Day 053) | Operates in unprivileged user space; latency coalesced; privacy filtered. |
| **Process Lifecycle** | `es_subscribe(ES_EVENT_TYPE_NOTIFY_EXEC, ...)` | Darwin `sysctl` / `/bin/ps` polling (`MacProcessDetector`, Day 049) | Tokenized `shell=False` arguments; zero credential leakage. |
| **Service Lifecycle** | `es_subscribe(ES_EVENT_TYPE_NOTIFY_FORK, ...)` | `launchctl list` & launchd plist scanner (`MacServicesDetector`, Day 050) | Read-only domain traversal; no root access needed. |
| **Binary Signatures** | Kernel CDHash & Code Signing Validation | `/usr/bin/codesign` & `/usr/sbin/spctl` (`MacSignaturesDetector`, Day 052) | Cryptographic provenance with "Scan != Safe" invariants. |

---

## 6. Verification and Acceptance Plan

1. **Unit Testing:** Verify data models, enum mappings, serialization to dictionary/JSON, and properties.
2. **Entitlement Audit Testing:** Verify diagnosis of non-root execution (`ES_NEW_CLIENT_RESULT_ERR_NOT_PRIVILEGED`) and missing entitlement (`ES_NEW_CLIENT_RESULT_ERR_NOT_ENTITLED`).
3. **Mock Profiles:** Verify `restricted_companion`, `entitled_daemon`, and `unsupported_platform` deterministic fixtures.
4. **Live Host Verification:** Verify that running on the macOS development host executes cleanly in unprivileged user space without requesting root, crashing, or modifying system configurations.
5. **Rust Parity:** Verify `crates/system-mind-sensors/src/macos_endpoint_security.rs` compiles, serializes JSON, and passes all Cargo unit tests.
6. **AST Safety & Tooling:** Run `python3 tools/lint.py`, `python3 tools/check_secrets.py`, and `cargo test --workspace`.
