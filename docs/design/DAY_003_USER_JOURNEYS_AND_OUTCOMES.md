# Design Note: Day 003 — Primary User Journeys & Measurable Outcomes

- **Date:** 2026-11-14
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Requirements / User Journeys / Verification Metrics

---

## 1. Overview & Objective

Day 003 translates the product thesis (Day 001) and target personas (Day 002) into **Primary User Journeys** with **Measurable Quantitative Outcomes**. Every journey represents an end-to-end operational workflow executed through the bifurcated architecture:
1. High-level intent and planning in the AI Control Plane.
2. Independent, non-LLM policy evaluation and persona boundary checks.
3. Narrow broker execution with preconditions, postconditions, and audit records.
4. Automated rollback in the event of partial failure.

---

## 2. The Five Primary User Journeys

### Journey 1: Proactive Health & Caretaker Remediation
- **Target Persona:** Personal Consumer (`PersonaType.PERSONAL`)
- **Trigger:** System telemetry detects an anomalous runaway background process consuming excessive CPU/thermal budget.
- **Workflow Steps:**
  1. *Observe:* Telemetry collector gathers process resource statistics.
  2. *Diagnose:* Caretaker engine identifies orphaned process (`test_leak_daemon`) consuming 95% CPU with no active GUI window.
  3. *Propose:* Synthesizes an explainable, plain-language action contract with risk tier `LOW_IMPACT`.
  4. *Authorize:* Asks user for single-click confirmation ("A background process is causing high battery drain. May I terminate it?").
  5. *Execute:* Narrow broker terminates the specific process ID after verifying pre-conditions (process exists, belongs to non-critical system user).
  6. *Verify:* Postcondition confirms process has terminated and CPU load drops below 10%.
- **Measurable Outcomes:**
  - Mean time to diagnostic: `< 5.0 seconds`.
  - False positive rate: `< 0.1%`.
  - Process termination accuracy: `100%` (zero termination of protected kernel daemons).
  - Post-remediation thermal/CPU recovery verified within `3.0 seconds`.

### Journey 2: Zero-Trust Suspicious File Inspection & Containment
- **Target Persona:** Personal Consumer & Developer (`PersonaType.PERSONAL`, `PersonaType.DEVELOPER`)
- **Trigger:** User downloads or receives an unknown executable or script from an external network origin.
- **Workflow Steps:**
  1. *Detect:* File monitor detects new file creation in download root.
  2. *Static Provenance:* Inspects file origin, quarantine flags (`com.apple.quarantine`), and cryptographic SHA-256 hash.
  3. *Invariant Check:* Enforces "Scan != Safe". Static heuristics cannot certify safety; direct host execution is denied (`FileExecutionContainment.DENIED`).
  4. *Confinement Selection:* User is offered:
     - Safe rendering in read-only memory-safe viewer (`HARDENED_VIEWER`).
     - Execution inside an ephemeral, network-isolated disposable container (`DISPOSABLE_ISOLATION`).
  5. *Execute in Isolation:* Micro-VM / container spins up without host filesystem mounts and with no ambient network access.
  6. *Cleanup:* Container is terminated and destroyed; execution traces logged.
- **Measurable Outcomes:**
  - Host filesystem isolation: `100%` (zero host filesystem writes).
  - Network egress leakage: `0 bytes` (strict offline policy unless explicitly permitted).
  - Ephemeral environment initialization latency: `< 2.5 seconds`.
  - Complete container teardown and artifact destruction: `< 1.0 second`.

### Journey 3: Developer Broken Toolchain Diagnostic & Safe Workspace
- **Target Persona:** Software Developer (`PersonaType.DEVELOPER`)
- **Trigger:** Developer encounters a failed build or broken dependency environment (e.g. ABI mismatch, missing system header).
- **Workflow Steps:**
  1. *Trigger:* Developer invokes `sysmind diagnose toolchain` within workspace root.
  2. *Inspect:* Inspector inspects compiler versions, lockfiles, and missing dynamic libraries.
  3. *Invariant Enforcement:* Protects `USER_MANAGED` dependencies. Autonomous updater cannot silently rewrite `Cargo.lock`, `.venv`, or `package.json`.
  4. *Propose:* Generates remediation recommendation (e.g. install missing build tool via package manager) with explicit developer approval.
  5. *Execute:* Broker executes scoped build environment setup within declared workspace.
  6. *Verify:* Verifies toolchain resolution without contaminating user global packages.
- **Measurable Outcomes:**
  - Root cause diagnostic precision: `> 95%`.
  - User-managed project files protected: `100%` (zero unprompted modifications).
  - Diagnostic execution time: `< 3.0 seconds`.

### Journey 4: Autonomous OS Maintenance & Component Protection
- **Target Persona:** All Personas (scheduled background task)
- **Trigger:** Scheduled idle maintenance window triggers on AC power.
- **Workflow Steps:**
  1. *Pre-flight:* Verifies system idle status, battery/AC power, and storage capacity.
  2. *Scope Check:* Confirms targets are strictly `ComponentOwnership.SYSTEM_MANAGED` (system cache pruning, log compression, dynamic linker cache update).
  3. *Snapshot:* Creates lightweight rollback restore point.
  4. *Execute:* Broker executes maintenance actions under medium risk tier.
  5. *Verify:* Confirms postconditions (reclaimed space, healthy service status). User apps (`Slack`, `Chrome`, `VSCode`, user virtualenvs) confirmed untouched.
  6. *Audit:* Records maintenance event in tamper-evident log.
- **Measurable Outcomes:**
  - Non-interference invariant: `100%` of `USER_MANAGED` components untouched.
  - Reversible recovery point availability: `100%`.
  - Unscheduled user disruption: `0 seconds` (cancels if user activity detected).

### Journey 5: Enterprise Compliance Audit & Dual-Person Critical Remediation
- **Target Persona:** Enterprise & IT Administrator (`PersonaType.ENTERPRISE_ADMIN`)
- **Trigger:** Fleet compliance monitor flags unauthorized firewall rule modification or missing security policy.
- **Workflow Steps:**
  1. *Detect:* Continuous audit agent flags compliance drift against CIS / NIST baseline.
  2. *Contract Generation:* Proposes `CRITICAL_PRIVILEGED` firewall reconfiguration contract.
  3. *Policy Evaluation:* Persona evaluator detects enterprise profile and blocks single-person execution.
  4. *Authorization:* Requires dual-person cryptographic signature (`TWO_PERSON_OR_BREAK_GLASS`) or incident break-glass token.
  5. *Execute:* Broker applies configuration atomically with active rollback plan.
  6. *Post-verification:* Verifies firewall rule active and network traffic uninhibited. Emits cryptographic audit event.
- **Measurable Outcomes:**
  - Dual-person enforcement rate: `100%` for critical operations without break-glass.
  - Cryptographic audit trail completeness: `100%`.
  - Automated compensation rollback success: `100%` on synthetic failure tests.
