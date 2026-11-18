# SYSTEM MIND X — Priority Corrective Engineering Review Report
**Task Identifier:** `CORRECTIVE-REVIEW-062`  
**Date:** 2026-11-17  
**Trigger:** Post-Day 062 Review Findings during Day 064 Execution  
**Project State:** Day 064 implemented (`awaiting_review`), Last Reviewed Day: 063  
**Roadmap Status:** PAUSED (Normal roadmap halted pending user review of this corrective review)

---

## 1. Executive Summary

During the development of SYSTEM MIND X, while Day 064 was marked `awaiting_review`, an engineering review identified seven critical quality and architecture issues originating in the Day 062 implementation and related subsystems. 

In accordance with `AGENTS.md` and project governance rules, normal day-by-day roadmap progression was immediately paused. Rather than resetting repository history or advancing prematurely to Day 065, the repository entered corrective maintenance mode under development task `CORRECTIVE-REVIEW-062`.

All seven engineering issues have been resolved, verified against native Darwin APIs and robust mock fixtures, and audited for zero regression. The polyglot test suite now passes with 100% success across 703 verified backend/sensor tests (607 Python + 94 Rust workspace + 2 Tauri shell) plus 5 native TypeScript desktop frontend tests (708 total passing tests).

---

## 2. Actual Project State Reconciliation

Before applying changes, the entire workspace, git commit graph, and state tracker were audited:

### 2.1 Timeline and Milestone Reconciliation
1. **Day 061 (Reviewed Complete):** Consolidated unit tests for all 20 macOS collectors (`tests/test_macos_collectors_unit.py`) with universal `scan_proves_safe = False` enforcement (ADR-071). Approved by user in commit `3bba89a` / `26fe6d7`.
2. **Day 062 (Reviewed Complete with Findings):** Integration tests for sensor absence and permission denials (`tests/test_macos_integration_missing_sensors_and_permissions.py`) (ADR-072). Approved by user in commit `26fe6d7`.
3. **Day 063 (Reviewed Complete):** Telemetry collector stability under sustained event volume with bounded ring buffers, event coalescing, and backpressure (ADR-073). Implemented in commit `d3c588a` and reviewed/approved by user in commit `70005ba` (`last_reviewed_completed_day: 63`).
4. **Day 064 (Implemented, Awaiting Review):** Permission prompts and required entitlements documentation (`docs/MACOS_PERMISSIONS_AND_ENTITLEMENTS.md`), models, inspector, and tests implemented in commit `79fa705` (`current_day: 64`, `status: "awaiting_review"`).
5. **Git History & Working Tree Integrity:** Git history is linear and clean on branch `develop`. All Day 063 and Day 064 implementations are preserved without data loss or truncation.

### 2.2 Reconciled State Matrix
| Milestone Day | Topic | Git Commit | State Tracker Status | Review Status |
|:---|:---|:---|:---|:---|
| **Day 061** | Unit Tests for All Collectors | `3bba89a` | Completed | **User Approved** |
| **Day 062** | Missing Sensor Integration | `26fe6d7` | Completed (Reviewed) | **Corrective Review Addressed** |
| **Day 063** | Collector Stability Under Volume | `70005ba` | Completed | **User Approved** |
| **Day 064** | Permissions & Entitlements | `79fa705` | `awaiting_review` | **Pending Final Review** |
| **CORRECTIVE-062**| Priority Engineering Fixes | Working Tree | `awaiting_user_review` | **Ready for Review** |
| **Day 065** | macOS Final Milestone Review | Not Started | Paused | Blocked on Day 064/Corrective |

---

## 3. Resolution of the Seven Identified Engineering Issues

### Issue 1: Mock Provenance and Confidence Scoring
- **Files Modified:**
  - `src/system_mind/macos/observation_models.py`
  - `src/system_mind/macos/observation_engine.py`
  - `src/system_mind/packaging/macos_observations.py`
  - `tests/test_macos_observations.py`
  - `crates/system-mind-sensors/src/macos_observations.rs`
- **Root Cause:**
  Synthetic mock observation batches were previously generating confidence profiles without explicitly setting `is_mock=True` on all envelopes, and simulated profiles risked claiming authoritative tiers (`KERNEL_AUTHORITATIVE`).
- **Resolution:**
  - Added `observation_status: str = "ACTUAL"` to `ObservedTelemetryEnvelope` (distinguishing `ACTUAL`, `MOCK`, `DEGRADED`, and `UNSUPPORTED`).
  - Enforced that whenever `use_mock=True` or synthetic profiles are evaluated, all envelopes strictly set `is_mock = True` and `clock_source = "mock_clock"`.
  - Added architectural assertions in `MacOsObservationEngine` and `MockMacOsObservationCollector`: mock observations are strictly prohibited from holding `ConfidenceTier.KERNEL_AUTHORITATIVE` or `ConfidenceTier.SUBSYSTEM_VERIFIED`.
  - Synchronized Rust `macos_observations.rs` mock implementations to set `is_mock = true` and `ConfidenceTier::EstimatedMock`.

### Issue 2: Rust macOS Inventory Hardcoded Values
- **Files Modified:**
  - `crates/system-mind-sensors/src/macos_inventory.rs`
- **Root Cause:**
  `crates/system-mind-sensors/src/macos_inventory.rs` previously contained hardcoded static strings ("Darwin", "Apple M2 Pro", "32 GB") that could be misinterpreted as live machine telemetry.
- **Resolution:**
  - Removed all hardcoded static machine, CPU, RAM, and OS values.
  - Implemented real Darwin native collection in `darwin_native` submodule using `libc` sysctl and filesystem APIs:
    - `sysctlbyname("kern.osproductversion")` for real macOS version (e.g., "14.4.1").
    - `sysctlbyname("kern.osversion")` for real Darwin build string (e.g., "23E224").
    - `sysctlbyname("machdep.cpu.brand_string")` for genuine CPU brand string (e.g., "Apple M1", "Apple M3 Pro").
    - `sysctlbyname("hw.physicalcpu")` and `sysctlbyname("hw.logicalcpu")` for real physical/logical core counts.
    - `sysctlbyname("hw.memsize")` for exact physical RAM bytes.
    - `gethostname` for host name.
    - `statfs("/")` for exact root filesystem capacity and free bytes.
  - On non-Darwin hosts or if any native call fails, fields are explicitly marked as `UNSUPPORTED` with `is_mock: true`.
  - Added native unit test `test_live_macos_inventory_service` asserting real system property retrieval without hardcoded fixtures.

### Issue 3: Collector Timeout and Aggregation Deadlines
- **Files Modified:**
  - `src/system_mind/macos/collector_health_manager.py`
  - `tests/test_macos_collector_health.py`
- **Root Cause:**
  In `CollectorHealthManager.aggregate_telemetry()`, the execution used a `with ThreadPoolExecutor() as executor:` context manager. In Python, exiting that context manager automatically invokes `shutdown(wait=True)`, which blocks the caller until hung threads terminate, completely nullifying `future.result(timeout=...)`.
- **Resolution:**
  - Refactored `CollectorHealthManager` to manage `ThreadPoolExecutor` manually:
    - Invokes `executor.shutdown(wait=False, cancel_futures=True)`.
    - Hung worker threads are detached safely without stalling the caller.
  - Added a global aggregation deadline (`total_aggregation_deadline_seconds`, default 5.0s):
    - If total elapsed wall-clock time across collectors exceeds the deadline, remaining pending collectors are cancelled and recorded as `TIMEOUT` with partial data preserved.
  - Added targeted regression tests: `test_collector_timeout_non_blocking_containment` (asserting a 5s hung collector returns in < 1.0s) and `test_total_aggregation_deadline_bounding`.

### Issue 4: Day 062 Integration and Fault-Injection Tests
- **Files Modified:**
  - `tests/test_macos_integration_missing_sensors_and_permissions.py`
  - `src/system_mind/packaging/macos_integration_faults.py`
- **Root Cause:**
  Integration fault scenarios did not cover collector crashes, worker thread timeouts, unsupported sensor returns, or simultaneous multi-fault aggregate safe states.
- **Resolution:**
  - Added 4 new integration fault test scenarios:
    1. `test_integration_collector_timeout_fault`: Injects hanging collector and verifies non-blocking partial return with `TIMEOUT` categorization.
    2. `test_integration_collector_crash_fault`: Injects simulated unexpected exception (`RuntimeError: Sensor hardware probe fault`) and verifies graceful partial return with `COMMAND_ERROR`.
    3. `test_integration_unsupported_sensor_fault`: Injects `PlatformUnsupportedError` and verifies typed `PLATFORM_UNSUPPORTED` root cause.
    4. `test_integration_simultaneous_multi_fault_safe_state`: Injects concurrent missing battery, offline network, denied FDA, unprivileged ES, and a crashing collector simultaneously. Asserts execution succeeds in < 0.5s, `partial_data=True`, and `scan_proves_safe=False` is preserved.
  - Updated `MacOsIntegrationFaultsValidator` to require 12 canonical fault scenarios.

### Issue 5: Frontend Live vs Offline Transparency
- **Files Modified:**
  - `apps/desktop/src/types/api.ts`
  - `apps/desktop/src/services/client.ts`
  - `apps/desktop/src/App.tsx`
- **Root Cause:**
  The desktop client scaffold fell back to static mock data on network errors with synthetic `status: "success"`, misleading users during daemon downtime. Mutating governance approval requests also returned fake success.
- **Resolution:**
  - Added typed `BackendConnectionState` (`CONNECTED_LIVE`, `OFFLINE_DISCONNECTED`, `DEGRADED_MOCK`).
  - Removed all fake `status: "success"` fallbacks in `apps/desktop/src/services/client.ts`.
  - Network failures return RFC 7807 problem details with error code `E7001_NETWORK_FAILURE`.
  - Mutating governance approvals explicitly fail with an error when the daemon is offline.
  - Updated `apps/desktop/src/App.tsx`:
    - Added live/offline status badge in the header.
    - Added an prominent offline warning banner with a manual "Retry Connection" button.
    - Added error alerts if governance approvals fail while offline.
    - Rendered explicit telemetry timestamps and provenance tags.

### Issue 6: Real Backend API and Telemetry Database Persistence
- **Files Created/Modified:**
  - `src/system_mind/api/server.py` (New real HTTP API server)
  - `src/system_mind/database/telemetry_repo.py` (New SQLite telemetry repository)
  - `src/system_mind/database/connection.py` (Added `check_same_thread: bool = False`)
  - `tests/test_api_server.py` (New test suite, 8/8 passed)
- **Root Cause:**
  The frontend expected REST API endpoints that were only specified in design contracts, without a live HTTP server daemon or database persistence layer connecting incoming telemetry to SQLite.
- **Resolution:**
  - Created `TelemetryRepository` in `src/system_mind/database/telemetry_repo.py`:
    - Persists temporal observations into `temporal_observations`.
    - Persists cryptographic audit log entries into `audit_events` with SHA-256 hash chaining.
    - Provides point-in-time digital twin summary aggregation.
  - Implemented `SystemMindApiServer` using Python native `http.server.HTTPServer` with zero unpinned third-party web frameworks:
    - `GET /api/v1/sensors/metrics`: Returns live or mock sensor metrics and records temporal observation.
    - `GET /api/v1/twin/summary`: Returns unified system inventory state.
    - `POST /api/v1/governance/approvals`: Enforces client `idempotency_key`, validates approval payload, and persists audit event into the immutable ledger.
    - `POST /api/v1/filetrust/inspect`: Evaluates 8-state file trust policy and returns handler mode.
    - `GET /api/v1/audit/ledger`: Returns cryptographically chained audit events.
    - Unmatched endpoints return RFC 7807 problem details with `E4004_NOT_FOUND`.
  - Updated `src/system_mind/database/connection.py` to allow multi-threaded SQLite connection pooling (`check_same_thread=False`).

### Issue 7: Desktop Frontend Test Runner and CI Detection
- **Files Modified:**
  - `apps/desktop/package.json`
  - `apps/desktop/src/__tests__/client.test.ts`
- **Root Cause:**
  `apps/desktop/package.json` had a placeholder `"test": "echo 'Frontend tests passed'"` that masked test outcomes and prevented CI from failing on real frontend errors.
- **Resolution:**
  - Updated `package.json` to use Node 22 native test runner:
    `"test": "node --test --experimental-strip-types src/__tests__/*.test.ts"`
  - Migrated `apps/desktop/src/__tests__/client.test.ts` to standard `node:test` and `node:assert`:
    - Tests typed RFC 7807 problem details on offline daemon.
    - Tests mandatory UUIDv4 `idempotency_key` generation on mutating approvals.
    - Tests prohibition of direct ambient shell execution (`child_process`, `execa`).
    - Tests rejection of mutating approvals when disconnected.
  - Verified `python3 tools/test_runner.py --frontend` runs the suite and correctly propagates non-zero exit codes on failure.

---

## 4. Fourteen Intelligence Engines Architectural Audit

All 14 intelligence engines specified on Day 011 were audited against current repository code, runtime behavior, and test suites:

| Engine ID | Name | Maturity Tier | Implementation State | Execution Mode | Verified Invariants |
|:---|:---|:---|:---|:---|:---|
| **ENG-01** | Persistent Temporal Digital Twin | Foundation | `IMPLEMENTED` | In-Memory Graph + SQLite (`telemetry_repo.py`) | SC-04, Append-Only |
| **ENG-02** | Application Context & Dependencies | Foundation | `IMPLEMENTED` | Live Darwin Plist + Ownership Classifier | SC-02, Update Immunity |
| **ENG-03** | Sensor Awareness Engine | Foundation | `LIVE` (macOS) / `MOCKED` (Other) | Live Darwin `sysctl`, `statfs`, `ps`, `ifconfig` | SC-01, SC-03 |
| **ENG-04** | Deterministic Policy & Governance | Execution | `IMPLEMENTED` | Pure Deterministic Rule Engine + Rust Broker | SC-01, Multi-Tier Precedence |
| **ENG-05** | Autonomous Maintenance Engine | Planning | `DESIGNED` | Taxonomy & Rollback Contracts defined | SC-02, Maintenance Boundaries |
| **ENG-06** | File Intelligence & Trust Engine | Analysis | `IMPLEMENTED` | 8-State Trust Model + Codesign + FSEvents | SC-01, SC-03 (Scan != Safe) |
| **ENG-07** | Controlled Sandboxing Engine | Execution | `DESIGNED` / `MOCKED` | Contract Specifications & Mock Profiles | Boundary Isolation |
| **ENG-08** | Developer Lifecycle Engine | Analysis | `DESIGNED` | Project Exclusion Rules & Secret Scanner | SC-02, Dev Tool Immunity |
| **ENG-09** | Predictive Caretaker Engine | Planning | `DESIGNED` | Pressure Indicators & Stability Backpressure | NFR Evaluation |
| **ENG-10** | Verified Execution Broker | Execution | `IMPLEMENTED` | Native Rust Broker (`system-mind-broker`) | SC-01, SC-02, SC-03 |
| **ENG-11** | Knowledge Retrieval & RAG | Foundation | `DESIGNED` | Structured Schema Contracts | Read-Only Boundary |
| **ENG-12** | Universal Capability Registry | Foundation | `IMPLEMENTED` | 5-Tier Parity Matrix (`parity.py`) | Platform Parity Bounds |
| **ENG-13** | NixOS & System Mind OS Engine | Platform | `DESIGNED` / `BLOCKED` | Matrix Defined, Tracked in `BLOCKERS.md` | Disposable VM Isolation |
| **ENG-14** | Host Companion Agents Engine | Platform | `LIVE` (macOS) / `DESIGNED` (Other) | Unprivileged LaunchAgent + Swift Bridge | SC-01, Least Privilege |

---

## 5. Subsystem Status & Platform Capability Matrix

### 5.1 Platform Adapters Status
- **macOS (Apple Silicon & Intel):** `LIVE` / `VERIFIED`. Twenty hardware and OS collectors operational via native Darwin utilities (`sysctl`, `vm_stat`, `statfs`, `scutil`, `ifconfig`, `pmset`, `system_profiler`, `ps`, `launchctl`, `codesign`, `spctl`, FSEvents).
- **Windows 11 x64:** `DESIGNED` / `MOCKED`. Full behavioral simulation provided by `MockPlatformAdapter` using `PlatformProfile.WINDOWS_11_X64`. Native WMI/ETW/Win32 scheduled for Milestone 9 (Days 211–265).
- **Ubuntu LTS x86_64:** `DESIGNED` / `MOCKED`. Full behavioral simulation provided by `MockPlatformAdapter` using `PlatformProfile.UBUNTU_LTS_X64`. Native procfs/eBPF/systemd scheduled for Milestone 7 (Days 141–200).
- **NixOS VM:** `DESIGNED` / `BLOCKED_ON_PREREQUISITES`. Scheduled for Milestone 11 (Days 301–330). QEMU and Nix host tooling prerequisites tracked in `docs/BLOCKERS.md`.

### 5.2 Architectural Property Verification
1. **AI / Native System Split:** Verified. The AI model operates purely as a planner and explainer. Consequential operations route through typed action contracts (`TypedActionContract`) validated by the deterministic policy engine and dispatched to the native Rust broker (`system-mind-broker`).
2. **Deterministic Policy Engine:** Verified. Policy precedence (`CRITICAL_SAFETY > ENTERPRISE_OVERRIDE > USER_PREFERENCE > AI_RECOMMENDATION`) executes deterministically without LLM inference.
3. **Zero Ambient Shell Authority (`SC-01`):** Verified. Zero instances of `shell=True`, `os.system()`, or ambient shell libraries (`sh`, `plumbum`, `execa`, `child_process`). All subprocess invocations use tokenized argument arrays with bounded timeouts.
4. **"Scan != Safe" Invariant (`SC-03`):** Verified. All 20 collector models, observation envelopes, stability buffers, permissions manifests, and file trust policies structurally enforce `scan_proves_safe = False`.
5. **Component Ownership Segregation (`SC-02`):** Verified. Applications and launchd services are categorized into `SYSTEM_MANAGED`, `VENDOR_MANAGED`, and `USER_MANAGED`. Autonomous updates targeting user-managed items are strictly rejected.

---

## 6. Verification Test Results

All verification suites were executed locally in unprivileged user space:

| Test Suite | Framework | Tests Run | Result | Duration |
|:---|:---|:---|:---|:---|
| **Python Unit / Integration / Contract** | `pytest 9.1.1` | 607 passed | **PASSED** | 58.4s |
| **Rust Sensors & Broker Workspace** | `cargo test --workspace` | 94 passed | **PASSED** | 2.22s |
| **Rust Desktop Shell (Tauri)** | `cargo test --manifest-path apps/desktop/...` | 2 passed | **PASSED** | 0.01s |
| **Desktop Frontend Scaffold** | Node 22 `--test` | 5 passed | **PASSED** | 0.15s |
| **Secret Scan (818 files)** | `tools/check_secrets.py` | 818 scanned, 0 leaks | **PASSED** | 1.8s |
| **AST Safety & Linters** | `tools/lint.py --all` | AST + Clippy + ESLint | **PASSED** | 3.5s |
| **Full Local CI Runner** | `tools/ci_runner.py all` | Multi-stage pipeline | **PASSED** | 78.2s |

---

## 7. Limitations, Technical Debt, and Open Blockers

1. **Endpoint Security Entitlement:** In companion mode, the macOS agent executes strictly in unprivileged user space (`gui/$UID`), gracefully degrading when `com.apple.developer.endpoint-security.client` is absent. A privileged broker daemon for ES `AUTH` events is scheduled for Milestone 6.
2. **NixOS VM Tooling:** QEMU and Nix tools are not installed on the host. This remains an intentional, documented non-blocker for Milestones 1–10, tracked in `docs/BLOCKERS.md`.
3. **Desktop Native Window:** The Tauri frontend runs as a Vite webview or browser client during development. Packaging as a signed `.app` bundle will occur in Milestone 12.

---

## 8. Handoff & Next Steps

1. **Human Review of `CORRECTIVE-REVIEW-062`:** The user should inspect this report and the underlying diff.
2. **Resume Normal Roadmap:** Upon user approval:
   - Complete the human review of Day 064 (`python3 tools/day_tracker.py complete --day 64`).
   - Advance tracker to Day 065 (`python3 tools/day_tracker.py start --day 65`).
   - Execute Day 065 (Milestone 4 Conclusion & macOS System Agent Milestone Review).
