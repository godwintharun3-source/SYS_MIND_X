# DAY 021 — Architecture Design Note: Typed Action Contracts and Precondition/Postcondition Rules

**Component:** Risk-Adaptive Verified Execution Broker & Contracts (`ENG-10`, `ENG-04`)  
**Layer:** Layer 5 (Adaptive Policy Engine) / Layer 6 (Trusted Capability Broker)  
**Date:** 2026-11-15  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Problem Formulation

In conventional "computer-use" AI agent frameworks, actions are generated as unstructured strings (e.g. bash commands like `rm -rf /tmp/cache/*` or `powershell.exe -Command Restart-Service`). This design contains three fatal architectural flaws:
1. **Unchecked State Assumptions**: The agent executes commands assuming the host environment is in a specific state (e.g. process stopped, power plugged in, snapshot exists, disk space available). If that assumption is wrong, execution causes system corruption or unrecoverable power-loss failure.
2. **Silent Post-Execution Drift**: Agents assume execution succeeded based merely on exit code `0`. In reality, silent filesystem failures, lingering zombie processes, partial writes, or corrupted configs leave the host in an undefined state with zero automated verification.
3. **Absence of Atomic Rollback**: When a modification fails halfway through, there is no typed mechanism to reverse the mutation, leading to cascading failures.

**The SYSTEM MIND Solution:**  
SYSTEM MIND X establishes **Typed Action Contracts** governed by explicit, deterministic **Precondition and Postcondition Rules**:
- Actions are strictly typed data contracts (`TypedActionContract`) with structured parameters, required capability grants, and SHA-256 contract hashes. Free-form shell commands are prohibited.
- **Preconditions** are machine-verified predicates evaluated against the observed host and digital-twin state before the broker touches system state. If a single precondition fails, capability dispatch is blocked.
- **Postconditions** are deterministic verification predicates evaluated immediately following execution. If postconditions fail, the broker automatically invokes a typed **Rollback Contract**.

---

## 2. Action Contract Execution Lifecycle

```
+-----------------------------------------------------------------------------+
|                         LAYER 5: AI CONTROL PLANE                           |
|       (Proposes TypedActionContract with Pre/Postconditions & Rollback)     |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                       ACTION CONTRACT VALIDATOR                             |
|  - Parameter Sanitization (No shell injections, no raw shell pipes)        |
|  - Invariant Verification (Consequential operations require pre/post rules)  |
|  - Rollback Completeness (Critical/High operations require rollback plan)    |
+-----------------------------------------------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
|                     PRECONDITION RULE EVALUATION                            |
|       Evaluates all TypedPreconditions against Observed System State        |
+-----------------------------------------------------------------------------+
                   |                                       |
         [ Preconditions Failed ]               [ All Preconditions Passed ]
                   |                                       |
                   v                                       v
          [ DISPATCH BLOCKED ]               +-----------------------------+
        (Emits Diagnostic Log)               |   LAYER 6: TRUSTED BROKER   |
                                             |  (Dispatches Native Action) |
                                             +-----------------------------+
                                                           |
                                                           v
                                             +-----------------------------+
                                             | POSTCONDITION VERIFICATION  |
                                             +-----------------------------+
                                                           |
                                      +--------------------+--------------------+
                                      | All Passed?                             | Any Failed?
                                      v                                         v
                            [ EXECUTION SUCCESS ]                      [ ATOMIC ROLLBACK ]
                           (Audit Receipt Signed)                   (Executes Rollback Plan)
```

---

## 3. Strongly Typed Precondition Taxonomy

Preconditions are typed predicate rules (`TypedPrecondition`) evaluated deterministically:

| Precondition Type | Evaluated Parameters | Validation Target | Failure Diagnostic |
| :--- | :--- | :--- | :--- |
| **`FILESYSTEM_PATH_STATE`** | `path`, `expected_exists`, `is_file`, `is_dir` | Verifies target path presence/absence and filesystem node type. | `PathStatePreconditionFailure: Path does not match required state.` |
| **`STORAGE_CAPACITY`** | `mount_point`, `min_free_bytes` | Verifies sufficient free disk space buffer before staging updates. | `StorageCapacityPreconditionFailure: Insufficient disk space.` |
| **`PROCESS_LIFECYCLE`** | `process_name`, `pid`, `must_be_running` | Verifies daemon or conflicting process state before mutation. | `ProcessLifecyclePreconditionFailure: Conflicting process running.` |
| **`POWER_AND_THERMAL`** | `require_ac_power`, `min_battery_pct` | Verifies AC power connection and battery charge for high-risk operations. | `PowerPreconditionFailure: Operation requires AC mains power.` |
| **`SNAPSHOT_RECOVERY`** | `snapshot_id`, `provider` | Verifies an atomic recovery snapshot exists before irreversible steps. | `SnapshotPreconditionFailure: Recovery snapshot missing.` |
| **`DIGITAL_TWIN_FRESHNESS`**| `entity_id`, `max_age_seconds` | Verifies observation telemetry is not stale or expired. | `StaleTwinPreconditionFailure: Entity observation exceeds freshness TTL.` |
| **`SECURITY_CLEARANCE`** | `user_approved`, `capability_token` | Verifies explicit user consent and valid broker entitlement tokens. | `SecurityClearancePreconditionFailure: Missing user approval.` |

---

## 4. Strongly Typed Postcondition Taxonomy

Postconditions (`TypedPostcondition`) verify that the intended state transition completed successfully:

| Postcondition Type | Target Parameters | Verification Target | Failure Action |
| :--- | :--- | :--- | :--- |
| **`FILESYSTEM_MUTATION`** | `path`, `expected_exists`, `expected_sha256` | Verifies file written, deleted, or matches cryptographic hash. | Triggers Rollback |
| **`SERVICE_LIFECYCLE`** | `service_name`, `expected_active` | Verifies daemon or service transitioned to active or inactive. | Triggers Rollback |
| **`PROCESS_STATE`** | `pid`, `expected_terminated` | Verifies target process exited and released locked file handles. | Triggers Rollback |
| **`AUDIT_RECEIPT`** | `audit_event_id`, `receipt_signed` | Verifies Layer 6 audit daemon recorded signed immutable ledger entry. | Triggers Rollback |

---

## 5. Strongly Typed Rollback Contract

Rollback contracts (`RollbackContract`) define atomic inverse operations:
- **`SNAPSHOT_REVERT`**: Reverts the filesystem to the pre-action APFS, VSS, or Btrfs snapshot.
- **`FILE_BACKUP_RESTORE`**: Restores target files from an isolated pre-execution shadow copy.
- **`SERVICE_STATE_RESTORE`**: Restarts or restores previous daemon configuration and service state.
- **`PACKAGE_DOWNGRADE`**: Reinstalls previous verified package version from local package cache.

---

## 6. Inviolable Safety Invariants

1. **Consequential Operations Rule**: Any action with `risk_tier` of `MEDIUM_IMPACT`, `HIGH_IMPACT`, or `CRITICAL_PRIVILEGED` must specify at least one typed precondition and at least one typed postcondition.
2. **Mandatory Rollback Rule**: Any action with `risk_tier` of `HIGH_IMPACT` or `CRITICAL_PRIVILEGED` must define a valid `RollbackContract`.
3. **Parameter Injection Prevention**: Action contract parameters are strongly typed dictionaries. Parameters containing shell meta-characters (`|`, `;`, `&&`, `` ` ``, `$()`, `rm -rf`, `sudo`) are hard-rejected during contract validation.
4. **Precondition Gating Invariant**: The Trusted Broker is mathematically prohibited from dispatching capability grants if any precondition evaluation returns `satisfied=False`.
5. **Postcondition Failure Rollback Invariant**: If any postcondition evaluation returns `verified=False`, the broker marks the operation failed, aborts completion, and immediately executes the rollback contract.
