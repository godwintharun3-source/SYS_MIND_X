# Design Note: Day 002 — Target User Personas & Contextual Governance Envelopes

- **Date:** 2026-11-14
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Requirements / Persona Mapping / Governance Envelopes

---

## 1. Overview & Problem Statement

A universal computer-operation platform cannot adopt a one-size-fits-all interaction or authorization model. What is safe and helpful for an enterprise IT administrator (e.g. enforcing fleet-wide security baselines or disabling vulnerable system daemons) could be catastrophic or incomprehensible to a personal consumer. Conversely, developer workflows require rapid experimentation, multiple concurrent runtime environments, and local container execution, yet must never suffer silent contamination of project dependencies or unintended compiler configuration mutations.

Day 002 establishes the **Target User Personas & Contextual Governance Envelopes** for SYSTEM MIND X.

---

## 2. The Three Target Personas

### 2.1 Persona A: The Personal Computer User
- **Archetype:** Everyday desktop/laptop user running macOS or Windows.
- **Goals:**
  - Keep the system fast, responsive, and quiet without technical management overhead.
  - Diagnose unexpected battery drain, high thermals, or sluggish performance in plain language.
  - Organize and locate files without complex folder structures.
  - Protect against deceptive software installers, adware, and malicious downloads.
- **Governance Envelope:**
  - **Permitted Risk Tiers:** `READ_ONLY`, `LOW_IMPACT`. `MEDIUM_IMPACT` allowed only for scheduled quiet maintenance of `SYSTEM_MANAGED` components (e.g., system cache pruning, log compression).
  - **Forbidden Actions:** `HIGH_IMPACT` (system software reconfiguration) and `CRITICAL_PRIVILEGED` (firmware, bootloader, disk partitioning) are blocked by default or require simplified, high-friction, plain-language confirmation dialogues.
  - **Privacy Perimeter:** Absolute exclusion of personal user directories (`~/Documents`, `~/Pictures`, `~/Downloads`, browser history, photo libraries) from content inspection. Only approved monitored roots (e.g., system health metrics, storage volume capacity) are read.
  - **Interaction Style:** Natural-language conversational interface, periodic proactive caretaker reports, single-click "Approve Remediation" actions with transparent explanations.

### 2.2 Persona B: The Software Developer & Engineering Team
- **Archetype:** Full-stack, systems, or data engineer working on macOS Apple Silicon, Windows 11 WSL2, or Ubuntu Linux.
- **Goals:**
  - Understand and resolve broken toolchains, conflicting runtime versions (Node, Python, Rust, Go), and container networking issues.
  - Identify compiler and build bottlenecks, monitor CPU/memory/GPU utilization during heavy compilation or test cycles.
  - Safely inspect and sandbox unknown third-party repositories, scripts, and package dependencies.
  - Accelerate local debugging through temporal state rewind and process execution traces.
- **Governance Envelope:**
  - **Permitted Risk Tiers:** `READ_ONLY`, `LOW_IMPACT`, `MEDIUM_IMPACT`, `HIGH_IMPACT` (within developer workspaces).
  - **Non-Negotiable User-App Boundary:** The autonomous updater is strictly barred from modifying `USER_MANAGED` developer project environments (`.venv`, `node_modules`, `target/`, `Cargo.lock`, active git worktrees). Updates to developer tools require explicit interactive user triggers.
  - **Isolation & Containment:** External scripts, npm/pip install hooks, and untrusted binaries must run in disposable container/micro-VM sandboxes without host volume mounts.
  - **Privacy Perimeter:** Developer source repositories within explicit workspaces can be indexed for symbol/semantic intelligence with user consent. Secrets (`.env`, SSH keys `~/.ssh`, GPG keys, API tokens) are strictly redacted and excluded from all telemetry, models, and logs.
  - **Interaction Style:** Native terminal CLI integration (`sysmind`), IDE plugins, markdown diagnostics, and structured event streaming.

### 2.3 Persona C: The Enterprise & IT Administrator
- **Archetype:** Enterprise systems engineer, SOC analyst, or IT administrator managing corporate macOS, Windows, and Linux fleets.
- **Goals:**
  - Ensure continuous compliance against security standards (NIST SP 800-218 SSDF, CIS benchmarks, SOC2).
  - Detect unauthorized software ("shadow IT"), anomalous privilege escalation, or unpatched OS vulnerabilities without interrupting employee productivity.
  - Remediate security advisories across distributed fleets using verified rollback strategies.
  - Maintain tamper-evident, cryptographically signed audit records for all system state modifications.
- **Governance Envelope:**
  - **Permitted Risk Tiers:** All tiers up to `CRITICAL_PRIVILEGED`, governed strictly by Multi-Person Approval or Break-Glass cryptographic authorization tokens.
  - **Deterministic Policy Supremacy:** Enterprise policy rules are enforced deterministically and cannot be altered or bypassed by the AI control plane.
  - **Privacy & Employee Confidentiality:** Fleet telemetry collects operational metrics, process provenance, and security hashes only. Zero personal data, employee screen captures, or document contents are collected.
  - **Audit Invariant:** Every consequential action emits an immutable audit event containing: timestamp, actor ID, cryptographic pre-state digest, post-state validation evidence, and atomic compensation plan.
  - **Interaction Style:** Headless companion daemon, REST/gRPC management API, structured JSON/OpenTelemetry event export, enterprise policy dashboard.

---

## 3. Persona Comparison Matrix

| Attribute | Personal Consumer | Developer / Engineer | Enterprise IT Admin |
| :--- | :--- | :--- | :--- |
| **Primary Focus** | Frictionless upkeep & safety | Toolchain & workspace agility | Compliance, fleet security & audit |
| **Max Ambient Risk Tier** | `LOW_IMPACT` | `HIGH_IMPACT` (Scoped) | `CRITICAL_PRIVILEGED` (Governed) |
| **Critical Action Approval** | High-friction plain text prompt | Explicit CLI verification flag | Multi-person / Break-glass token |
| **Autonomous System Maintenance** | Permitted for `SYSTEM_MANAGED` | Permitted for `SYSTEM_MANAGED` | Policy-scheduled fleet maintenance |
| **User Application Updates** | Manual user confirmation only | Strictly excluded; user initiated | Enterprise managed catalog only |
| **File Containment Mode** | Hardened viewer / Blocked | Disposable container / VM | Centralized analysis / Sandbox |
| **Monitored Roots** | Storage stats, system logs | Configured project directories | Operating system & security roots |
| **Excluded Privacy Paths** | Documents, Photos, Personal files | `.env`, `id_rsa`, `.ssh`, secrets | Employee personal profiles & data |

---

## 4. Implementation Design in `system_mind.personas`

1. **`PersonaType` Enum:** `PERSONAL`, `DEVELOPER`, `ENTERPRISE_ADMIN`.
2. **`UserPersona` Model:** Typed specification of the persona's allowed risk tiers, approval policies, root directories, privacy exclusion patterns, and capability limits.
3. **`PersonaPolicyEvaluator`:** Evaluates any proposed `ActionContract` against the active persona context. If an action exceeds the persona's governance envelope, it is rejected with a structured `PersonaGovernanceViolation`.
4. **`PersonaRegistry`:** Provides immutable, pre-configured baseline personas adhering strictly to the security rules.
