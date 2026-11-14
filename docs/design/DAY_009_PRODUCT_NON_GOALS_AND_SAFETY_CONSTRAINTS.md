# Design Note: Day 009 — Product Non-Goals & Explicit Safety Constraints

- **Date:** 2026-11-14
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Governance / Safety Constraints / Non-Goals Catalog

---

## 1. Overview & Architectural Rationale

In safety-critical systems architecture, specifying what a system **must never do** (negative requirements) is as fundamental as defining what it can do. Many catastrophic AI agent failures (e.g. accidental recursive file deletions, silent dependency breakage, credential exfiltration, ambient screen spying) arise not from coding defects in functional capabilities, but from an absence of **unambiguous, machine-enforceable negative boundaries**.

SYSTEM MIND X establishes an explicit **Product Non-Goals Catalog** and a deterministic **Safety Constraint Enforcement Engine**. These constraints act as inviolable architectural firewalls, terminating unauthorized or unsafe actions regardless of model prompt or reasoning rationale.

---

## 2. The 10 Product Non-Goals

The following areas are formally designated as Product Non-Goals:

| Non-Goal ID | Title | Rationale & Architectural Scope Boundary |
| :--- | :--- | :--- |
| **NG-01** | **No Unrestricted Host Shell / Root Agent** | SYSTEM MIND X is not an ambient raw shell interpreter (e.g. AutoGPT/OpenInterpreter pattern). The AI planner operates strictly in unprivileged user space. Consequential mutations are mediated exclusively via typed contracts and a narrow broker daemon. |
| **NG-02** | **No Ambient Continuous Screen OCR / Keylogging** | SYSTEM MIND X is not an ambient background screen recorder (e.g. Windows Recall pattern). Telemetry collection is structured, event-driven, and bound to explicit monitored roots. No continuous OCR screen dumps. |
| **NG-03** | **No Autonomous User Application or Workspace Mutation** | Autonomous maintenance never updates user-installed productivity apps, developer IDEs, local git repositories, virtualenvs, or language package directories (`pip`, `npm`, `cargo`). |
| **NG-04** | **No 'Scan Means Safe' Native Binary Execution** | Static or heuristic signature scans can never establish that a binary is safe. External or untrusted files are strictly quarantined to disposable micro-isolation or restricted handlers. |
| **NG-05** | **No Host Security Control Bypassing** | SYSTEM MIND X never weakens, disables, or subverts native OS security controls (SIP, Gatekeeper, WDAC, SELinux, AppArmor, or native cryptographic update checks). |
| **NG-06** | **No Mandatory Cloud Exfiltration of Secrets** | SYSTEM MIND X is local-first. Telemetry collectors and prompt contexts are strictly quarantined from private credentials (`~/.ssh`, `~/.gnupg`, `.env`) and personal media (`~/Documents`, `~/Pictures`). |
| **NG-07** | **No Unbounded Fleet-Wide Mutation** | In enterprise environments, no fleet-wide high-impact or critical configuration change may execute without cryptographic multi-person authorization or break-glass approval tokens. |
| **NG-08** | **No Scratch-Built Monolithic Kernel** | SYSTEM MIND X does not re-implement an OS kernel from scratch. Native OS kernels (XNU, Windows NT, Linux) remain the authoritative lower-level execution and security enforcement boundary. |
| **NG-09** | **No Unattended Firmware Flashing or Partition Reconfiguration** | Destructive low-level operations (EFI NVRAM writes, BIOS flashing, partition map alteration) are strictly forbidden from autonomous or single-click execution. |
| **NG-10** | **No Speculative Capability Fabrication** | The engine never claims support for an OS capability or sensor metric until verified on certified hardware. Mocks are explicitly marked `MOCK_ONLY`. |

---

## 3. Explicit Safety Constraints (`SafetyConstraint`)

Every action submitted to the SYSTEM MIND X execution broker must satisfy eight hard architectural constraints:

1. **`SC-01 (NO_RAW_SHELL)`:** Rejection of raw shell execution strings or root privilege escalation commands.
2. **`SC-02 (NO_AUTONOMOUS_USER_MODIFICATION)`:** Autonomous operations targeting `USER_MANAGED` components are hard-rejected.
3. **`SC-03 (NO_UNCONTAINED_EXTERNAL_EXECUTION)`:** Untrusted external files cannot execute natively without verified containment (`DISPOSABLE_ISOLATION` or `HARDENED_VIEWER`).
4. **`SC-04 (NO_PRIVACY_PATH_READING)`:** Operations targeting paths within protected privacy perimeters (`~/.ssh`, `~/.gnupg`, `~/Documents`, `.env`) are rejected.
5. **`SC-05 (NO_UNAUTHORIZED_CRITICAL_EXECUTION)`:** `CRITICAL_PRIVILEGED` operations require explicit verified user authorization or dual-person approval.
6. **`SC-06 (NO_UNSUPPORTED_PLATFORMS)`:** Execution on uncertified platform architectures (Intel macOS, 32-bit Windows, non-systemd Linux) is blocked by policy.
7. **`SC-07 (NO_UNATTENDED_FIRMWARE_MUTATION)`:** Firmware updates and partition map alterations are strictly barred from unattended execution.
8. **`SC-08 (NO_SECURITY_CONTROL_BYPASS)`:** Operations attempting to disable or subvert native OS security mechanisms are hard-rejected.

---

## 4. Enforcement Engine Architecture

The `SafetyConstraintValidator` aggregates constraints across all governance layers:
```
                      +------------------------------------+
                      |       ActionContract Request       |
                      +------------------------------------+
                                         │
                                         ▼
                      +------------------------------------+
                      |     SafetyConstraintValidator      |
                      +------------------------------------+
                                         │
             ┌───────────────────────────┼───────────────────────────┐
             ▼                           ▼                           ▼
   +--------------------+     +--------------------+     +--------------------+
   |   Charter Checks   |     |   Privacy Checks   |     |  Ownership Checks  |
   | (Raw Shell, Root)  |     | (~/.ssh, Keychain) |     |  (USER_MANAGED)    |
   +--------------------+     +--------------------+     +--------------------+
             │                           │                           │
             └───────────────────────────┼───────────────────────────┘
                                         ▼
                      +------------------------------------+
                      | Deterministic Pass / Reject Audit  |
                      +------------------------------------+
```
