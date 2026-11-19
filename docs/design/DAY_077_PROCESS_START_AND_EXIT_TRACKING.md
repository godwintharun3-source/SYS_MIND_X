# Design Note: Day 077 — Track Process Start and Exit Events

## 1. Architectural Objective & Context

SYSTEM MIND X maintains a persistent, temporal, provenance-aware digital twin of host computing state. Operating system processes represent the active execution plane of software on the machine. Every running application, background daemon, maintenance task, and interactive command executes through one or more operating system processes.

Tracking process start and exit events is critical for:
1. **Dynamic Execution Observability**: Capturing process creation, execution arguments, execution ancestry (PPID lineage), user credentials, and termination status.
2. **PID Recycling Collision Resistance**: Operating systems rapidly recycle process identifiers (PIDs). A plain integer PID cannot serve as a temporal primary key. SYSTEM MIND X derives collision-resistant canonical entity URNs binding device ID, start timestamp, PID, and executable path digest.
3. **Application Ownership & Component Boundaries (`SC-02`)**: Linking processes to parent applications (`APPLICATION -> OWNS -> PROCESS`), services (`SERVICE -> OWNS -> PROCESS`), or kernels (`KERNEL -> CONTAINS -> PROCESS`), distinguishing `SYSTEM_MANAGED`, `VENDOR_MANAGED`, and `USER_MANAGED` processes.
4. **Point-in-Time Process State Reconstruction**: Enabling operators and intelligence engines to reconstruct the complete process hierarchy running on any host at any historical epoch millisecond $T$.
5. **Universal "Scan != Safe" Invariant (`SC-03`)**: Recording a process start event does not imply that the binary is safe, approved, or free from malicious behavior.

---

## 2. Telemetry Channels & Observation Strategies

Processes are observed through two complementary telemetry channels:

```
+--------------------------------------------------------------------------------+
|                          PROCESS TELEMETRY CHANNELS                            |
+--------------------------------------------------------------------------------+
             |                                                  |
             v                                                  v
+-------------------------------+              +---------------------------------+
|  Channel A: Periodic Process  |              |  Channel B: Real-Time Event     |
|  Table Snapshots (Polling)    |              |  Stream (Endpoint Security/eBPF)|
+-------------------------------+              +---------------------------------+
             |                                                  |
             +------------------------+-------------------------+
                                      |
                                      v
+--------------------------------------------------------------------------------+
|                         PROCESS LIFECYCLE TRACKER                              |
|           (Diff Evaluation, Lineage Resolution, PID Reuse Handling)            |
+--------------------------------------------------------------------------------+
                                      |
     +--------------------------------+--------------------------------+
     |                                |                                |
     v                                v                                v
+--------------------------+   +--------------------------+   +------------------+
| Relational Lifecycle Log |   | Append-Only Event Store  |   | In-Memory Digital|
| (process_lifecycle_      |   | (SystemEventStore with   |   | Twin Graph       |
|  events table, mig 0012) |   |  SHA-256 Hash Chaining)  |   | (DigitalTwinGraph|
+--------------------------+   +--------------------------+   +------------------+
```

### Channel A: Periodic Process Table Snapshot Diffing
- Compares consecutive process table snapshots (e.g., from `MacProcessReport` / `MacProcessInfo`).
- Diffs running PIDs across snapshots $S_t$ and $S_{t+1}$:
  - **Start**: PID present in $S_{t+1}$ but absent in $S_t$, or present in both with a strictly newer `start_time_epoch_ms` (PID recycling detection).
  - **Exit**: PID present in $S_t$ but absent in $S_{t+1}$. Exit status is marked `UNKNOWN` or `INFERRED_EXIT` when exact exit codes cannot be retrieved via polling.
  - **State Transition**: Process remains active, but state (RUNNING, SLEEPING, STOPPED, ZOMBIE) or resource utilization changes.

### Channel B: Real-Time OS Event Notifications
- Consumes real-time notifications from native subsystems:
  - macOS: Apple Endpoint Security `es_client` (`NOTIFY_EXEC`, `NOTIFY_FORK`, `NOTIFY_EXIT`).
  - Linux: eBPF tracepoints (`sched_process_exec`, `sched_process_exit`).
- Captures exact exit codes, termination signals, and precise execution microsecond timestamps.

---

## 3. Process Lifecycle Event Taxonomy

| Event Type | Description | Digital Twin Action |
|---|---|---|
| `PROCESS_STARTED` | Process launched via `execve` or `posix_spawn` | Register new `TwinEntity` (`TwinEntityType.PROCESS`), establish `SPAWNED_BY`, `OWNS`, and `CONTAINS` edges |
| `PROCESS_FORKED` | Child process created via `fork` / `clone` | Register child process entity linked to parent process via `SPAWNED_BY` |
| `PROCESS_EXITED` | Process terminated normally (`exit(code)`) | Mark entity stale (`is_stale = True`, `stale_reason = "PROCESS_EXITED"`), record exit code and runtime |
| `PROCESS_CRASHED` | Process terminated via fatal signal (SIGSEGV, SIGABRT) | Mark entity stale with reason `PROCESS_CRASHED`, record signal and failure context |
| `PROCESS_SIGNALED` | Process terminated via termination signal (SIGTERM, SIGKILL) | Mark entity stale with reason `PROCESS_SIGNALED`, record terminating signal |

---

## 4. Mathematical Invariants & Data Integrity Rules

1. **PID Collision-Resistant URN Derivation (`INV-PROC-01`)**:
   - Every process entity references a canonical URN derived via:
     $$\text{URN} = \text{urn:systemmind:proc:}\langle\text{device\_id}_{:8}\rangle{:}\langle\text{start\_epoch\_ms}\rangle{:}\langle\text{pid}\rangle{:}\langle\text{sha256}(\text{binary\_path})_{:8}\rangle$$
   - This guarantees that two processes reusing the same integer PID on the same machine never collide in the digital twin.
2. **Temporal Boundedness (`INV-PROC-02`)**:
   - For any exited process:
     $$\text{start\_epoch\_ms} \le \text{exit\_epoch\_ms}$$
     $$\text{runtime\_ms} = \text{exit\_epoch\_ms} - \text{start\_epoch\_ms}$$
3. **Component Ownership Isolation (`SC-02` / `INV-PROC-03`)**:
   - All process events categorize ownership into `SYSTEM_MANAGED`, `VENDOR_MANAGED`, or `USER_MANAGED`.
   - User processes are tracked in read-only observation mode with zero unprompted termination or modification.
4. **Universal "Scan != Safe" Invariant (`SC-03` / `INV-PROC-04`)**:
   - Strictly enforced at SQLite database constraint level (`CHECK (scan_proves_safe = 0)`) and in Python dataclasses (`scan_proves_safe: bool = False`).
   - Logging a process start event reflects execution telemetry, never safety or benign intent.
5. **Cryptographic Event-Store Hash Chaining (`INV-PROC-05`)**:
   - Every process lifecycle transition bridges to `SystemEventStore`, computing cryptographic SHA-256 hash chains across sequential records.
6. **Non-Destructive Graph History (`INV-PROC-06`)**:
   - Exited or crashed processes are never deleted from `DigitalTwinGraph` or SQLite tables; they are marked with `is_stale = True` and retained for temporal queries and root-cause analysis.
7. **Point-in-Time Reconstruction Invariant (`INV-PROC-07`)**:
   - For any query timestamp $T$, a process is classified as running if and only if:
     $$\text{start\_epoch\_ms} \le T \land (\text{exit\_epoch\_ms} \text{ IS NULL} \lor \text{exit\_epoch\_ms} > T)$$
8. **Zero Ambient Shell Authority (`SC-01` / `INV-PROC-08`)**:
   - All tracking, diffing, and database operations execute purely in-memory via parameterized SQL with `shell=False`.
