# Design Note: Day 001 — Product Thesis, Charter Contracts & Read-Only Host Inspection

- **Date:** 2026-11-14
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Core Architecture / Charter / Host Telemetry Foundation

---

## 1. Context & Motivation

Current computer-use AI agents interact with operating systems using brittle techniques:
1. **Blind Bash Execution:** Direct execution of arbitrary bash/cmd scripts with ambient user privileges (or elevated sudo privileges), making the system vulnerable to prompt injection, hallucinated flags (e.g. `rm -rf /*`), and unrecoverable changes.
2. **Vision-Only Screen Manipulation:** Scraping pixels and synthesizing mouse clicks, which lacks semantic state knowledge, fails during headless/background execution, and cannot inspect system internals or enforce security invariants.

SYSTEM MIND X introduces an architectural paradigm: **Bifurcated AI-Native Computing**. The AI operates as the cognition and planning plane, while deterministic native software (the Policy Engine and Privileged Execution Broker) maintains strict control over state changes.

---

## 2. Core Architectural Pillars

### Pillar 1: Separation of Concerns
- **Control Plane (AI Cognitive Layer):** Translates high-level goals into structured, typed intent requests. Synthesizes explanations and queries historical telemetry.
- **Independent Policy Engine (Deterministic Layer):** Non-LLM rule evaluator written in deterministic code. Checks preconditions, authorization, ownership classification, and risk tiers.
- **Narrow Privileged Broker (Enforcement Layer):** Runs with minimal necessary privileges. Executes single typed actions, records pre- and post-condition evidence, and generates cryptographic audit trails.
- **Native OS Platform Adapters:** OS-specific bindings (Apple Endpoint Security, Windows ETW/WDAC, Linux eBPF/Landlock).

### Pillar 2: Tripartite Component Ownership Model
Every software artifact on the system belongs to one of three ownership domains:
1. `SYSTEM_MANAGED`: Native OS libraries, system daemons, core security patches. Autonomous maintenance allowed if risk tier <= MEDIUM and post-condition rollback is available.
2. `VENDOR_MANAGED`: Firmware, GPU/audio drivers, OEM management utilities. Advisory only; requires explicit user approval and recovery planning.
3. `USER_MANAGED`: User productivity applications (browsers, Slack, VSCode), user projects, package manager libraries (`pip`, `npm`, `cargo`, `go` modules in user space). **Strictly excluded from autonomous updates.**

### Pillar 3: Zero-Trust File Execution
- Static signatures and heuristic scans are evidence, not proof of safety ("Scan != Safe").
- Unknown files cannot run on the host without containment.
- Bounded execution pathways:
  - *Hardened viewer* (read-only, memory safe)
  - *Ephemeral disposable VM / sandbox* (no network, zero host volume access)
  - *Native host execution* (only with verified cryptographic provenance and user policy rule)

---

## 3. Scope of Day 001 Implementation

For Day 001, we deliver:
1. **Charter Contract Types (`system_mind.core.types`):**
   - Formal enumeration of ownership classes, risk tiers, reversibility, approval policies, platform tiers, and capability support status.
   - Dataclasses defining typed action requests, execution plans, and inspection reports.
2. **Charter Rule Validator (`system_mind.core.charter`):**
   - Independent deterministic validator enforcing the non-negotiable rules:
     - Rejection of unrestricted root/sudo commands.
     - Rejection of autonomous updates targeting `USER_MANAGED` components.
     - Rejection of unconfined execution of untrusted files.
     - Enforcement of explicit approvals for `CRITICAL_PRIVILEGED` or `HIGH_IMPACT` actions.
3. **Read-Only Host Environment Inspector (`system_mind.host.inspector`):**
   - Deterministic, non-destructive probe of the host platform.
   - Gathers: kernel version, architecture, CPU model, memory, SIP status, Gatekeeper status, available developer tools (Python, Rust, Docker, Nix, QEMU).
   - Never writes to or alters host system configuration.
   - Includes full mock adapter capability to simulate Windows 11, Ubuntu Linux, and NixOS environments safely on macOS Apple Silicon.
4. **Comprehensive Unit & Contract Test Suite (`tests/`):**
   - 100% test coverage for charter invariants and host inspection logic.
