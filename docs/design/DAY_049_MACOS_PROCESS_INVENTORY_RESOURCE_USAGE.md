# DAY 049 — Design Note: macOS Process Inventory with PID, Owner and Resource Usage

**Date:** 2026-11-16  
**Status:** Approved & Implemented  
**Subsystem:** `system_mind.macos` / `crates/system-mind-sensors`  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Author:** SYSTEM MIND X Architecture & Platform Engineering  

---

## 1. Executive Summary & Objective

In an autonomous operator and governance architecture, real-time awareness of active running processes is essential for:
1. Detecting abnormal resource consumption (CPU saturation, memory leaks, runaway loops).
2. Distinguishing protected system components (`SYSTEM_CORE`) from third-party desktop applications (`USER_APP`), developer runtimes (`DEVELOPER_TOOL`), and background services (`DAEMON_SERVICE`).
3. Feeding the persistent temporal digital twin with process execution timelines and ownership metadata.

At the same time, process introspection introduces critical **security and privacy constraints**:
- **Zero Mutating Actions (`INV-PROC-04`):** The process engine is strictly read-only. It must never terminate, suspend, signal (`SIGKILL`, `SIGTERM`), or reprioritize processes without verified capability contracts and human approvals.
- **Privacy Protection (`INV-PROC-02`):** Command paths (`comm`) identify executable binaries without exposing potentially sensitive inline argument credentials (tokens, passwords, private directory paths).
- **Zero Ambient Shell Authority (`SC-01` / `INV-PROC-01`):** All queries execute strictly in user space via tokenized argument lists (`shell=False`) targeting `/bin/ps -axo pid,ppid,uid,user,%cpu,%mem,rss,vsz,stat,comm` without requiring root or `sudo`.

The Day 049 objective is to implement an unprivileged, read-only macOS process inventory collector providing structured PID, PPID, UID, user, CPU %, memory %, RSS bytes, VSZ bytes, operational state, and component role classification.

---

## 2. Invariants and Architectural Guarantees

- **`SC-01` / `INV-PROC-01`: Unprivileged Execution & Zero Ambient Shell Authority**  
  All process introspection runs strictly in unprivileged user space. Subprocess invocations use tokenized argument lists (`shell=False`) with strict timeouts (5 seconds).
- **`INV-PROC-02`: Sensitive Argument Redaction & Path Integrity**  
  By capturing standard executable paths (`comm`) rather than unconfined raw command argument buffers (`args`), the collector prevents leaking secrets passed as CLI flags.
- **`INV-PROC-03`: Process Ownership & Role Classification**  
  Every discovered process is classified into a typed `ProcessRole`:
  - `SYSTEM_CORE`: Root or system core services (`uid == 0`, `/System/`, `/sbin/`, `/usr/libexec/`, `/usr/sbin/`).
  - `USER_APP`: User desktop applications located in `/Applications/` or `~/Applications/`.
  - `DAEMON_SERVICE`: Background launchd agents and daemons.
  - `DEVELOPER_TOOL`: Toolchain processes (`python`, `cargo`, `rustc`, `node`, `git`, `clang`, `zsh`).
  - `OTHER`: Unclassified user processes.
- **`INV-PROC-04`: Strictly Read-Only Passive Introspection**  
  The engine is purely passive. Commands modifying process state (`kill`, `pkill`, `renice`, `killall`) are strictly excluded.
- **`INV-PROC-05`: Cross-Language Type Parity**  
  Python dataclasses (`src/system_mind/macos/process_models.py`) and native Rust structs (`crates/system-mind-sensors/src/macos_process.rs`) maintain strict semantic and behavioral parity.
- **`INV-PROC-06`: Safe Developer CLI Tooling**  
  `tools/detect_processes.py` enables inspection of running processes with sorting (`--top-cpu`, `--top-mem`), filtering (`--user`), JSON output (`--json`), and assertion thresholds (`--assert-processes <MIN_COUNT>`).
- **`INV-PROC-07`: Programmatic Packaging Validator**  
  `MacOsProcessValidator` in `src/system_mind/packaging/macos_process.py` audits schema completeness, role categorization, and CLI safety across CI.
- **`INV-PROC-08`: Graceful Non-Darwin Fallback**  
  On non-Darwin operating systems, execution delegates to `MockPlatformAdapter` or returns structured reports with `unavailable_telemetry`.

---

## 3. Data Flow & Subsystem Architecture

```
+--------------------------------------------------------------------------------+
|                         SYSTEM MIND X AGENT & DESKTOP                          |
|             (Presentation Layer / Digital Twin / Reasoning Engine)             |
+--------------------------------------------------------------------------------+
                                       ^
                                       | Strongly Typed Telemetry Report
                                       | (MacProcessReport / MacOsProcessSnapshot)
+--------------------------------------------------------------------------------+
|                       MACOS PROCESS INVENTORY DETECTOR                         |
|             (Python: MacProcessDetector | Rust: MacOsProcessCollector)         |
+--------------------------------------------------------------------------------+
             |                                                  |
             | Tokenized Subprocess                             | In-Memory Fallback
             v                                                  v
+-------------------------------+              +--------------------------------+
|  /bin/ps -axo                 |              |      MockPlatformAdapter       |
|  pid,ppid,uid,user,%cpu,%mem, |              |  (Deterministic M-Series Mock) |
|  rss,vsz,stat,comm            |              +--------------------------------+
+-------------------------------+
             |
             v
   Parsed Process Table:
   - PID, PPID, UID, USER
   - CPU % and Memory %
   - RSS (Resident Set Size) and VSZ (Virtual Size) in bytes
   - Process State (RUNNING, SLEEPING, STOPPED, ZOMBIE, UNINTERRUPTIBLE)
   - Role Classification (SYSTEM_CORE, USER_APP, DEVELOPER_TOOL, DAEMON_SERVICE)
```

---

## 4. Telemetry Schema & Categorical Enums

### 4.1. Enums
- **`ProcessState`**:
  - `RUNNING`: Process is actively executing on a CPU core (`R`).
  - `SLEEPING`: Process is in interruptible sleep waiting for I/O or events (`S`, `I`).
  - `STOPPED`: Process has been paused or stopped by job control or debugger (`T`).
  - `ZOMBIE`: Process has terminated but has not been reaped by parent (`Z`).
  - `UNINTERRUPTIBLE`: Process is in uninterruptible disk wait (`U`, `D`).
  - `UNKNOWN`: Unrecognized process state flag.
- **`ProcessRole`**:
  - `SYSTEM_CORE`: Core operating system infrastructure (`launchd`, `logd`, `fseventsd`).
  - `USER_APP`: User desktop GUI applications (`/Applications/Google Chrome.app`, etc.).
  - `DAEMON_SERVICE`: System and user background launchd services.
  - `DEVELOPER_TOOL`: Compilers, interpreters, source control (`cargo`, `python3`, `git`).
  - `OTHER`: Unclassified processes.

### 4.2. Core Data Models
- **`MacProcessInfo`**:
  - `pid`: Process identifier integer.
  - `ppid`: Parent process identifier integer.
  - `uid`: User ID of process owner integer.
  - `user`: Username string (e.g. `"root"`, `"tharungodwin"`).
  - `name`: Binary basename string (e.g. `"launchd"`, `"Google Chrome"`).
  - `command_path`: Full executable binary path (e.g. `"/sbin/launchd"`).
  - `cpu_percent`: Instantaneous CPU utilization percentage float.
  - `memory_percent`: Physical memory utilization percentage float.
  - `rss_bytes`: Resident Set Size memory consumption in bytes.
  - `vsz_bytes`: Virtual memory size in bytes.
  - `state`: `ProcessState` enum value.
  - `state_raw`: Raw Darwin state code string (e.g. `"Ss"`, `"R+"`).
  - `role`: `ProcessRole` enum value.
  - `is_system_core`: Boolean flag indicating core OS privilege/infrastructure.
  - `is_user_app`: Boolean flag indicating user-managed application.

- **`MacProcessReport`**:
  - `processes`: List of `MacProcessInfo` records.
  - `total_process_count`: Total active processes discovered.
  - `running_count`: Count of running processes.
  - `sleeping_count`: Count of sleeping processes.
  - `zombie_count`: Count of zombie processes.
  - `system_core_count`: Count of system core processes.
  - `user_app_count`: Count of user desktop applications.
  - `total_cpu_percent`: Sum of CPU utilization across all processes.
  - `total_rss_bytes`: Sum of resident set size across all processes.
  - `collected_at_epoch_secs`: Collection epoch timestamp float.
  - `collection_method`: `"NATIVE_DARWIN_PS"` or `"MOCK_PLATFORM_ADAPTER"`.
  - `unavailable_telemetry`: List of unavailable telemetry metrics.
  - `warnings`: Diagnostic warnings encountered during parsing.

---

## 5. Security & Verification Strategy

1. **Subprocess Tokenization**: Invocations use `shell=False` preventing ambient command injection.
2. **Deterministic Mock Simulation**: Safe mock adapter provides predictable process tables for CI pipelines.
3. **Comprehensive Pytest Suite**: Validates mock generation, multi-word process path parsing, state transitions, role classification, filtering, and non-Darwin fallback.
4. **Rust Sensor Unit Tests**: Validates `crates/system-mind-sensors` collector and mock struct compilation.
5. **CI Runner Integration**: Verified through `tools/ci_runner.py all` and `tools/lint.py`.
