# Design Note: Day 018 — Application Ownership and User-App Exclusion Model

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Application Context & Governance / User-App Exclusion Model / ADR-028
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Problem Statement

A catastrophic failure mode observed across contemporary computer-use agents and autonomous maintenance scripts is **the dependency and user-app clobbering defect**:
- An agent tasked with "optimizing system performance" or "running system updates" runs `brew upgrade --cask --all`, `apt-get upgrade -y`, or updates global pip packages.
- As a consequence, developer pinned runtimes (e.g. Python 3.10 virtualenvs, specific Node versions, database drivers), IDE extensions, or production browser sessions are silently terminated, upgraded, or corrupted.
- This violates the fundamental contract between the operating system agent and the user.

SYSTEM MIND X eliminates this risk through the **Application Ownership and User-App Exclusion Model**:
1. All software on the host is partitioned into the tripartite ownership model: `SYSTEM_MANAGED`, `VENDOR_MANAGED`, and `USER_MANAGED`.
2. All `USER_MANAGED` applications, developer dependencies, IDEs, desktop browsers, and virtual environments are **strictly excluded from autonomous system update and maintenance pipelines**.
3. Updates to user applications can *only* occur when explicitly requested and confirmed by the user through a typed action contract (`user_approved=True`).

Day 018 formalizes the schemas, classification engine, deterministic exclusion rules, and runtime enforcement gates.

---

## 2. Tripartite Application Taxonomy

```
+---------------------------------------------------------------------------------------------------------+
|                                    APPLICATION OWNERSHIP TAXONOMY                                       |
+---------------------------------------------------------------------------------------------------------+
|                                                                                                         |
|  [SYSTEM_MANAGED]                                                                                       |
|  - Scope: Authoritative OS vendor kernel and core utilities                                             |
|  - Examples: macOS Sealed System Volume (/System), Windows CBS/DISM OS packages, Ubuntu systemd packages |
|  - Autonomous Maintenance: PERMITTED within scheduled low-impact maintenance windows                    |
|                                                                                                         |
|  [VENDOR_MANAGED]                                                                                       |
|  - Scope: Hardware OEM firmware, baseband, hardware security modules, and proprietary driver packages  |
|  - Examples: Apple Silicon T2/SMC firmware, UEFI BIOS, NVIDIA kernel drivers, TPM microcode             |
|  - Autonomous Maintenance: STRICTLY PROHIBITED (Requires explicit user confirmation + staging)           |
|                                                                                                         |
|  [USER_MANAGED]                                                                                         |
|  - Scope: Third-party GUI apps, desktop browsers, IDEs, developer toolchains, virtual environments     |
|  - Examples: Google Chrome, Slack, VS Code, Python .venv, node_modules, Homebrew casks, Steam           |
|  - Autonomous Maintenance: ABSOLUTELY EXCLUDED (Zero autonomous mutation under any circumstance)        |
|                                                                                                         |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Core Domain Constructs

### 3.1 Application Type (`ApplicationType`)
- `SYSTEM_CORE`: Pre-installed OS utility or core system daemon.
- `USER_DESKTOP_APP`: User-installed GUI productivity, communication, or media application.
- `DEVELOPER_TOOLCHAIN`: Compilers, runtimes, package managers, and command-line utilities.
- `PROJECT_DEPENDENCY`: Workspace virtual environments, local node_modules, and build targets.
- `USER_CLI_TOOL`: User-compiled or locally installed command-line utilities in user space.
- `BACKGROUND_SERVICE`: User launch agents, cron jobs, or user-space background helpers.

### 3.2 Installation Scope (`InstallScope`)
- `SYSTEM_WIDE`: Installed in root OS directories (`/System`, `/usr/bin`, `C:\Windows`, `C:\Program Files`).
- `USER_LOCAL`: Installed within user home directory (`~/Applications`, `~/.local`, `%LOCALAPPDATA%`).
- `PROJECT_LOCAL`: Nested inside a project repository or workspace directory (`./venv`, `./node_modules`).

### 3.3 Application Profile (`ApplicationProfile`)
- Strongly typed metadata record containing:
  - `app_id`: Canonical reverse-DNS identifier (e.g. `com.google.Chrome`, `com.microsoft.VSCode`).
  - `display_name`: Human-readable application name.
  - `app_type`: `ApplicationType` classification.
  - `install_scope`: `InstallScope` location.
  - `install_path`: Filesystem directory path.
  - `executable_path`: Entrypoint binary path.
  - `ownership`: `ComponentOwnership` (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`).
  - `managed_by`: Packaging authority (`os_vendor`, `homebrew`, `winget`, `apt`, `pip`, `manual`).
  - `is_excluded_from_autonomous_updates`: Boolean flag enforced by policy.

---

## 4. Deterministic Exclusion Rules

The `UserAppExclusionEnforcer` enforces five mandatory exclusion rules:

1. **`EXCL-RULE-01 (Ownership Exclusion)`**:
   Any software classified as `USER_MANAGED` is strictly excluded from autonomous system maintenance.
2. **`EXCL-RULE-02 (Application Bundle Directory Exclusion)`**:
   Paths matching `/Applications/*` (non-Apple system), `~/Applications/*`, `C:\Program Files\*` (non-OS), and `~/.local/share/applications/*` are tagged excluded.
3. **`EXCL-RULE-03 (Developer Workspace and Dependency Exclusion)`**:
   Paths matching `*/node_modules/*`, `*/.venv/*`, `*/venv/*`, `*/target/*`, and `*/site-packages/*` are tagged excluded.
4. **`EXCL-RULE-04 (User Configuration & Dotfile Exclusion)`**:
   Dotfiles and user configs (`~/.zshrc`, `~/.bashrc`, `~/.config/*`, `~/.ssh/*`, `~/.gitconfig`) are strictly excluded from automated modification.
5. **`EXCL-RULE-05 (Active Desktop Browser & IDE Protection)`**:
   Applications identified as interactive browsers or IDEs (`Chrome`, `Safari` user profile, `VS Code`, `Xcode`, `IntelliJ`) cannot be terminated, updated, or reloaded autonomously.

---

## 5. Cardinal Invariants of Application Ownership

1. **Default to Exclusion:**
   $$\text{OwnershipUnknown}(A) \implies \text{Ownership}(A) = \text{USER\_MANAGED} \land \text{IsExcluded}(A) = \text{TRUE}$$
   If an application cannot be unambiguously proven to be an authoritative OS component, it is classified as `USER_MANAGED` and excluded from autonomous maintenance.

2. **Zero Autonomous Mutation of User Applications:**
   $$\text{IsExcluded}(A) \land \text{Caller} = \text{AUTONOMOUS\_MAINTENANCE} \implies \text{DispatchAction} = \text{BLOCKED}$$
   The deterministic policy gate hard-blocks any autonomous maintenance task attempting to modify an excluded application.

3. **Explicit User Approval Prerequisite:**
   $$\text{IsExcluded}(A) \land \text{Action} = \text{UPDATE} \implies \text{UserApproved} = \text{TRUE} \land \text{ApprovalRequirement} \ge \text{USER\_EXPLICIT}$$
   User applications can only be modified when the user explicitly triggers or approves the action.

---

## 6. Architectural Decision Record (ADR-028)

- **Title:** Application Ownership Classification and User-App Exclusion Model
- **Status:** Accepted.
- **Context:** Autonomous AI operating agents often corrupt developer setups and user workflows by upgrading or mutating user-installed applications, packages, and project dependencies.
- **Decision:** SYSTEM MIND X implements a dedicated `ApplicationOwnershipClassifier` and `UserAppExclusionEnforcer`. All applications are classified into tripartite ownership with a strict fail-safe default (`USER_MANAGED`). All user applications, IDEs, browsers, and project dependencies are permanently excluded from autonomous update pipelines.
- **Consequences:** Protects user productivity and development toolchains; eliminates unintended breaking changes to third-party software; enforces explicit human consent for application lifecycle events.
