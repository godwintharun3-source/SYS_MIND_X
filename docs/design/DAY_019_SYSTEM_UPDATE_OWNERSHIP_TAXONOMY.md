# Design Note: Day 019 — System-Update Ownership Taxonomy

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Autonomous OS & System Maintenance (Layer 5/6) / Update Taxonomy / ADR-029
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Architectural Problem

System updates in classical operating systems and modern AI tools are often treated as an undifferentiated stream: running `apt-get upgrade`, `softwareupdate -i -a`, or running firmware update scripts without distinguishing:
- What layer of the hardware/OS stack is being mutated.
- Whether a component is `SYSTEM_MANAGED`, `VENDOR_MANAGED`, or `USER_MANAGED`.
- Whether a reboot is mandatory or can be staged asynchronously.
- What cryptographic rollback snapshot is required to guarantee crash resilience.

Attempting to apply updates indiscriminately causes bricked hardware (e.g. interrupted firmware flashing), broken developer environments (e.g. clobbered runtime toolchains), or unexpected system downtime.

SYSTEM MIND X resolves this by formalizing the **System-Update Ownership Taxonomy**:
1. All updates are cataloged into strict **Maintenance Tiers** (`OS_SECURITY_HOTFIX`, `SYSTEM_DAEMON_MAINTENANCE`, `OS_CUMULATIVE_UPDATE`, `FIRMWARE_HARDWARE_UPDATE`, `USER_APP_UPDATE`, `PROJECT_DEPENDENCY_UPDATE`).
2. Autonomous unattended execution is strictly restricted to low-risk `SYSTEM_MANAGED` components (hotfixes and cache maintenance).
3. `VENDOR_MANAGED` (firmware/EFI) updates mandate explicit user approval, AC power verification, and physical recovery checkpoints.
4. `USER_MANAGED` components remain permanently outside autonomous system update scope (governed by Day 018).

---

## 2. Update Maintenance Tiers & Execution Authority

```
+---------------------------------------------------------------------------------------------------------+
|                                    SYSTEM-UPDATE MAINTENANCE TIERS                                      |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|  [TIER 1: OS_SECURITY_HOTFIX] (SYSTEM_MANAGED)                                                          |
|  - Description: Rapid security definitions, XProtect, Defender signatures, CRL revokes                  |
|  - Impact: LOW_IMPACT | Reversibility: REVERSIBLE | Reboot: NONE                                        |
|  - Autonomous Policy: PERMITTED unattended; immediate execution                                        |
|                                                                                                         |
|  [TIER 2: SYSTEM_DAEMON_MAINTENANCE] (SYSTEM_MANAGED)                                                   |
|  - Description: Journal vacuuming, log rotation, system cache pruning (/var/tmp)                        |
|  - Impact: LOW_IMPACT | Reversibility: REVERSIBLE | Reboot: NONE                                        |
|  - Autonomous Policy: PERMITTED during scheduled idle maintenance windows                               |
|                                                                                                         |
|  [TIER 3: OS_CUMULATIVE_UPDATE] (SYSTEM_MANAGED)                                                        |
|  - Description: OS point releases, kernel security patches, system bundle upgrades                       |
|  - Impact: HIGH_IMPACT | Reversibility: REVERSIBLE (APFS/VSS snapshot) | Reboot: STAGED REBOOT        |
|  - Autonomous Policy: DOWNLOAD & STAGE ONLY; activation requires user maintenance window confirmation   |
|                                                                                                         |
|  [TIER 4: FIRMWARE_HARDWARE_UPDATE] (VENDOR_MANAGED)                                                    |
|  - Description: UEFI BIOS, Apple Silicon T2/SMC firmware, GPU VBIOS, TPM microcode                      |
|  - Impact: CRITICAL_PRIVILEGED | Reversibility: IRREVERSIBLE | Reboot: MANDATORY IMMEDIATE              |
|  - Autonomous Policy: STRICTLY FORBIDDEN; requires explicit human approval + AC power check             |
|                                                                                                         |
|  [TIER 5: USER_APP_UPDATE] (USER_MANAGED)                                                               |
|  - Description: Desktop GUI applications, browsers, IDEs, desktop tools                                 |
|  - Autonomous Policy: ABSOLUTELY EXCLUDED; permitted only via explicit user-initiated request          |
|                                                                                                         |
|  [TIER 6: PROJECT_DEPENDENCY_UPDATE] (USER_MANAGED)                                                     |
|  - Description: pip, npm, cargo, go modules, project virtualenvs                                        |
|  - Autonomous Policy: ABSOLUTELY EXCLUDED; project lockfiles must remain frozen                        |
|                                                                                                         |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Update Lifecycle State Machine

Every system update proposal progresses through a deterministic state machine:

```
[DISCOVERED] ──► [VERIFIED_SIGNATURE] ──► [PRECONDITIONS_CONFIRMED] ──► [STAGED] ──► [APPLIED]
       │                   │                           │                    │             │
       ▼                   ▼                           ▼                    ▼             ▼
  [REJECTED]          [REJECTED]                  [BLOCKED]            [ROLLED_BACK] [COMPLETED]
```

1. **`DISCOVERED`**: Upstream update manifest detected via native OS update query (`softwareupdate -l`, `DISM`, `apt-get check`).
2. **`VERIFIED_SIGNATURE`**: Cryptographic vendor signature verified against native OS root of trust (Apple PKG, Microsoft Authenticode, Ubuntu GPG).
3. **`PRECONDITIONS_CONFIRMED`**: Pre-update safety checks satisfied:
   - Atomic recovery snapshot created (`APFS snapshot`, `VSS restore point`, `Timeshift checkpoint`).
   - AC power verified (battery-only execution blocked for Tiers 3 & 4).
   - Free disk space buffer verified (minimum 10 GB for cumulative OS updates).
4. **`STAGED`**: Update payload downloaded and staged in micro-isolated staging directory.
5. **`APPLIED`**: Package applied to system volume or scheduled for reboot activation.
6. **`POSTCONDITIONS_CHECKED`**: Post-update system health audit (kernel integrity, core service liveness).
7. **`COMPLETED` / `ROLLED_BACK`**: Final success or automatic compensation rollback to snapshot.

---

## 4. Cardinal Invariants of the Update Taxonomy

1. **Autonomous Scope Invariant:**
   $$\text{Caller} = \text{AUTONOMOUS} \implies \text{Tier} \in \{\text{OS\_SECURITY\_HOTFIX}, \text{SYSTEM\_DAEMON\_MAINTENANCE}\}$$
   Autonomous unattended execution is structurally barred from mutating anything outside Tier 1 and Tier 2.

2. **Mandatory Snapshot Precondition:**
   $$\text{Tier} \in \{\text{OS\_CUMULATIVE\_UPDATE}, \text{FIRMWARE\_HARDWARE\_UPDATE}\} \implies \text{RecoverySnapshotCreated} = \text{TRUE}$$
   No consequential system update may commence without an atomic filesystem rollback point.

3. **AC Power Requirement for High-Risk Updates:**
   $$\text{RequiresReboot}(\text{proposal}) \implies \text{PowerSource} = \text{AC\_POWER\_CONNECTED}$$
   Firmware flashing or cumulative OS updates on battery power are hard-blocked to prevent power-loss bricking.

4. **Cryptographic Vendor Attestation:**
   $$\text{ProposalStatus} = \text{APPLIED} \implies \text{VendorSignatureVerified} = \text{TRUE}$$
   Unsigned, self-signed, or untrusted update binaries cannot be executed by the execution broker.

---

## 5. Architectural Decision Record (ADR-029)

- **Title:** System-Update Ownership Taxonomy and Safety Lifecycle
- **Status:** Accepted.
- **Context:** Classical update tools lack formal boundaries, leading to broken developer dependencies, unexpected reboots, or failed firmware flashing.
- **Decision:** SYSTEM MIND X implements a six-tier System-Update Ownership Taxonomy. Autonomous maintenance is limited exclusively to Tier 1 (Security Hotfixes) and Tier 2 (Daemon Maintenance). Cumulative OS updates require snapshotting and reboot scheduling. Firmware updates require AC power and explicit approval. User applications and project dependencies are permanently excluded from autonomous update scope.
- **Consequences:** Eliminates system update collateral damage; guarantees deterministic rollbacks for failed OS updates; protects physical hardware from power-loss flashing failures.
