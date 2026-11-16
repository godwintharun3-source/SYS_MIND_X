# DAY 037 — Local Development Scripts and Reproducible Setup Instructions

**Status:** IMPLEMENTED  
**Date:** 2026-11-16  
**Milestone:** Milestone 3 — Repository and development foundation (Days 026–040)  
**System Plane:** Cross-Cutting Developer Tooling (`tools/`, `docs/`)

---

## 1. Architectural Objective & Context

SYSTEM MIND X is a polyglot monorepo comprising three tier-specific runtimes: Python 3.12 (Control Plane, Digital Twin, and Policy Engine in `src/`), Rust 1.75+ (Hardware Sensors and Privileged Capability Broker in `crates/`), and TypeScript / React 18 / Tauri v2 (Desktop Presentation Shell in `apps/desktop/`).

To guarantee developer reproducibility, onboarding deterministic reliability, and strict compliance with safety boundaries across clean clones and development workstations, Day 037 establishes:
1. Unified unprivileged developer setup tooling (`tools/dev_setup.py`).
2. POSIX and PowerShell developer convenience wrappers (`tools/setup_dev.sh`, `tools/setup_dev.ps1`).
3. Authoritative step-by-step setup documentation (`docs/DEVELOPMENT_SETUP.md`).
4. Programmatic packaging validator (`src/system_mind/packaging/dev_setup.py`).

---

## 2. Inviolable Safety & Security Constraints

The local development infrastructure strictly adheres to the project charter:

1. **Zero Privileged Host Mutation (SC-01 / SC-06):**
   Setup scripts NEVER execute `sudo`, modify system partitions, tamper with macOS System Integrity Protection (SIP), Gatekeeper, Windows Defender, Linux AppArmor/SELinux, system startup daemons, or OS kernel extensions. All operations occur in unprivileged user space.

2. **User Application Non-Interference (SC-02):**
   Setup scripts do NOT install, modify, or update system-wide user applications, global interpreters, or foreign project dependencies. All dependencies reside strictly within workspace-local directories (`.venv/`, `crates/target/`, `apps/desktop/node_modules/`).

3. **Loopback & Isolated Defaults:**
   Environment defaults bind strictly to `127.0.0.1` on unprivileged user-space ports (1024–65535). Production flags and remote network listeners are prohibited by default.

4. **Zero Ambient Shell Invocation (SC-01):**
   The Python orchestrator (`tools/dev_setup.py`) dispatches toolchain commands as explicit argument lists (`subprocess.run([cmd, ...], shell=False)`); raw shell string evaluation (`shell=True`, `os.system`) is strictly banned.

5. **Bounded Workspace Traversal:**
   The artifact cleanup engine enforces boundary checks, guaranteeing deletions remain strictly confined within the workspace root.

---

## 3. Toolchain & Prerequisite Specification

| Component | Minimum Version | Verified Target | Purpose |
|-----------|-----------------|-----------------|---------|
| **Python** | `>= 3.10` | `3.12.6` | Control Plane, Digital Twin, Policy Engine, Tools |
| **Rust / Cargo** | `>= 1.75` | `1.75+` (2021 Edition) | System-Agent Workspace, Sensors, Broker Daemon |
| **Node.js** | `>= 18.0` | `v20+` LTS | Desktop Operator Console Frontend |
| **npm** | `>= 9.0` | `v10+` | Frontend package management |
| **Git** | `>= 2.20` | `2.39+` | Monorepo source control & day tracker verification |
| **SQLite** | `>= 3.35` | Built-in Python standard library | Local persistence & temporal observation store |

---

## 4. Developer Orchestrator CLI (`tools/dev_setup.py`)

The developer CLI provides three primary subcommands:

### 1. `check`
Audits the developer's workstation for required toolchains, active Python virtual environment, environment configuration files (`.env`), and database persistence state. Emits human-readable reports with actionable remediation advice, or structured JSON via `--json`.

### 2. `bootstrap`
Orchestrates end-to-end unprivileged repository setup:
- Verifies toolchains and reports missing prerequisites.
- Generates `.env` from `.env.example` if absent (with safe loopback defaults).
- Validates Python dependencies.
- Runs Rust workspace validation (`cargo check --workspace`).
- Applies database migrations via `tools/migrate.py`.
- Runs syntax, AST safety, and secret leak verification via `tools/lint.py`.
- Executes smoke tests via `tools/test_runner.py --unit`.
- Supports `--dry-run` to preview actions without execution.

### 3. `clean`
Safely purges ephemeral build artifacts (`target/`, `build/`, `dist/`, `.pytest_cache/`, `__pycache__`) within the repository boundaries.

---

## 5. Shell Wrappers

- **`tools/setup_dev.sh`**:
  POSIX-compliant shell script (macOS/Linux) that inspects Python availability and delegates execution to `tools/dev_setup.py`.
- **`tools/setup_dev.ps1`**:
  PowerShell script for Windows 11 x64 developer parity.

---

## 6. Programmatic CI Validation (`DevSetupValidator`)

The packaging validator `src/system_mind/packaging/dev_setup.py` audits:
- Presence and completeness of `docs/DEVELOPMENT_SETUP.md`.
- Presence and executable permissions of `tools/dev_setup.py` and `tools/setup_dev.sh`.
- Prerequisite checker execution and JSON schema conformity.
- Safe path containment in the artifact cleanup engine.
- Absence of banned ambient shell invocations (`shell=True`, `os.system`).
