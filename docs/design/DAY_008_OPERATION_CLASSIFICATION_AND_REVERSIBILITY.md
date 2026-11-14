# Design Note: Day 008 — Operation Classification, Privilege Tiers & Reversibility

- **Date:** 2026-11-14
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Governance / Operations Taxonomy / Risk & Reversibility Classification

---

## 1. Overview & Architectural Motivation

An AI-native computer operator must not treat operating system operations as uniform function calls. Every action carries distinct consequences across three orthogonal axes:
1. **Impact (Risk Tier):** The blast radius of the operation—ranging from non-mutating inspections to destructive, system-wide state alterations.
2. **Privilege Level:** The execution context required—ranging from ambient unprivileged user space to narrow broker-mediated kernel interactions. Under no circumstances does the AI possess ambient root or raw shell rights.
3. **Reversibility & Rollback Strategy:** The degree to which an operation can be rolled back to its pre-state, and the deterministic mechanism for executing that compensation.

Without an unambiguous, typed operational taxonomy, computer agents inevitably suffer from:
- **Privilege Over-granting:** Running routine read or low-risk tasks with elevated root privileges.
- **Silent Irreversible Drift:** Executing destructive mutations without verifiable rollback pre-images.
- **Autonomous Scope Creep:** Modifying user workspaces or applications during autonomous maintenance sweeps.

SYSTEM MIND X implements a **Deterministic Operation Classification Engine** where every system operation is cataloged, classified, and audited before execution.

---

## 2. The Three Dimensional Classification Matrix

```
       [IMPACT / RISK TIER]
       CRITICAL_PRIVILEGED   ▲
       HIGH_IMPACT           │       (Two-Person / Break-Glass, Irreversible)
       MEDIUM_IMPACT         │
       LOW_IMPACT            │   (User-Approved, Reversible)
       READ_ONLY             │───(Autonomous, Zero-Risk)──────────────►
                             └─────────────────────────────────────────►
                             UNPRIVILEGED   USER_CONSENT   ELEVATED_BROKER   [PRIVILEGE]
```

### 2.1 Impact Tiers (`OperationRiskTier`)
- **`READ_ONLY` (Tier 0):** Zero state mutation. Querying host telemetry, reading public log files, inspecting process lists. Safe for continuous, unprompted telemetry collection.
- **`LOW_IMPACT` (Tier 1):** Bounded, ephemeral state mutation. Trimming user caches, rotating application logs. Fully reversible or negligible consequence if lost.
- **`MEDIUM_IMPACT` (Tier 2):** Scoped component state mutation. Restarting background user services, rebuilding local project caches. Requires explicit user prompt unless pre-authorized for system maintenance.
- **`HIGH_IMPACT` (Tier 3):** Broad system configuration or toolchain mutation. Modifying network interface routing, updating system security signatures, altering PATH or developer toolchains. Requires explicit interactive confirmation and active pre-state snapshot.
- **`CRITICAL_PRIVILEGED` (Tier 4):** Irreversible or high-blast-radius system operations. Partition reconfiguration, OS core updates, modifying kernel extension policies, enterprise fleet settings. Requires multi-person approval or cryptographic break-glass tokens; strictly forbidden from autonomous execution.

### 2.2 Privilege Levels (`PrivilegeLevel`)
- **`UNPRIVILEGED_USER`:** Operates within ambient standard user privileges without administrative elevation.
- **`USER_CONSENT_GRANTED`:** Operates in user space but touches user-sensitive areas (e.g. application settings) requiring explicit interactive consent.
- **`ELEVATED_BROKER_REQUIRED`:** Requires administrative/root execution mediated exclusively through the narrow, typed Privileged Broker daemon. The AI model itself remains unprivileged.
- **`HARDWARE_FIRMWARE_ENTITLED`:** Direct low-level interaction with platform hardware, secure enclaves, or firmware (e.g. EFI NVRAM inspection, TPM measurement, SMC queries). Never permits autonomous write access.

### 2.3 Reversibility Degrees & Strategies
- **`REVERSIBLE`:** Deterministic, automated rollback is guaranteed via:
  - `ATOMIC_FILE_RESTORE`: Pre-image copy restored atomically upon postcondition failure.
  - `STATE_INVERSE_ACTION`: Deterministic counter-action (e.g., `systemctl stop` reverses `systemctl start`).
  - `TRANSACTIONAL_SNAPSHOT`: Filesystem-level rollback (APFS snapshot, Btrfs/ZFS snapshot, NixOS generation switch).
- **`PARTIALLY_REVERSIBLE`:** Best-effort state restoration. Some state (e.g. ephemeral timestamps, socket states) cannot be reverted, but primary configuration is restored.
- **`IRREVERSIBLE`:** The operation destroys previous state permanently (e.g., disk vacuum, database compaction, unrecoverable file purge). Requires explicit user acknowledgment and cannot run during unattended maintenance.

---

## 3. Operational Invariants & Governance Rules

1. **Autonomous Maintenance Scope Boundary:**
   $$\forall \text{ op} \in \text{Operations}, \quad \text{op.is\_autonomous} \implies \text{op.target\_ownership} = \text{SYSTEM\_MANAGED} \land \text{op.risk\_tier} \le \text{MEDIUM\_IMPACT}$$
   Autonomous maintenance can **never** modify `USER_MANAGED` components (user apps, virtualenvs, repositories) or execute `HIGH_IMPACT` / `CRITICAL_PRIVILEGED` operations.

2. **Reversibility Mandatory Plan:**
   $$\forall \text{ op} \in \text{Operations}, \quad \text{op.reversibility} = \text{REVERSIBLE} \implies \text{op.rollback\_strategy} \ne \text{NONE} \land \text{op.rollback\_plan} \ne \text{None}$$
   No operation may claim to be reversible without an executable, typed rollback strategy.

3. **Privilege Broker Mediation Invariant:**
   $$\forall \text{ op} \in \text{Operations}, \quad \text{op.privilege\_level} \in \{\text{ELEVATED\_BROKER}, \text{HARDWARE\_FIRMWARE}\} \implies \text{op.action\_type} \ne \text{"raw\_shell"}$$
   Elevated operations must use strongly typed action contracts; ambient shell execution is strictly rejected.

---

## 4. Operation Catalog Schema

Every operation definition conforms to the `SystemOperationDefinition` contract:
```python
@dataclass(frozen=True)
class SystemOperationDefinition:
    operation_id: str
    name: str
    category: str
    target_ownership: ComponentOwnership
    risk_tier: OperationRiskTier
    privilege_level: PrivilegeLevel
    reversibility: Reversibility
    rollback_strategy: RollbackStrategy
    default_approval: ApprovalRequirement
    can_run_autonomously: bool
    required_preconditions: List[str]
    expected_postconditions: List[str]
    description: str
```
