# SYSTEM MIND X — Local Development Setup Guide

This document provides step-by-step, reproducible instructions for setting up a local development environment for SYSTEM MIND X on supported workstations.

---

## 1. Supported Development Platforms

The primary supported development workstation for Milestone 3 is:
- **macOS (Apple Silicon M1/M2/M3)**: macOS 13+ (Ventura, Sonoma, Sequoia), Darwin arm64.

Secondary tier development targets (for cross-platform parity):
- **Windows 11 x64**: WSL2 (Ubuntu 22.04 LTS) or native PowerShell.
- **Ubuntu Linux**: 22.04 LTS / 24.04 LTS x86_64 or aarch64.

---

## 2. Prerequisites & Toolchain Requirements

Ensure the following tools are installed in your user space before bootstrapping:

| Tool | Required Version | Verification Command | Installation Hint |
|------|------------------|----------------------|-------------------|
| **Python** | `>= 3.10` (3.12 recommended) | `python3 --version` | `brew install python@3.12` or `pyenv` |
| **Rust / Cargo** | `>= 1.75` | `cargo --version` | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| **Node.js** | `>= 18.0` (LTS recommended) | `node --version` | `brew install node` or `nvm` |
| **npm** | `>= 9.0` | `npm --version` | Bundled with Node.js |
| **Git** | `>= 2.20` | `git --version` | `brew install git` |

> [!IMPORTANT]
> **Safety Rule:** All setup operations run strictly in **unprivileged user space**. Never execute setup commands or package installations with `sudo`.

---

## 3. Quickstart (Automated Bootstrap)

Clone the repository and run the automated setup orchestrator:

```bash
# 1. Clone repository
git clone https://github.com/system-mind-x/system-mind.git
cd system-mind

# 2. Inspect environment prerequisites
python3 tools/dev_setup.py check

# 3. Bootstrap local development environment
python3 tools/dev_setup.py bootstrap
```

On macOS or Linux, you can also use the convenience shell wrapper:
```bash
./tools/setup_dev.sh
```

On Windows PowerShell:
```powershell
.\tools\setup_dev.ps1
```

---

## 4. Manual Step-by-Step Setup

If you prefer to configure each tier manually, follow these steps:

### Step 1: Environment Configuration
Create a local `.env` configuration file from the template:
```bash
cp .env.example .env
```
By default, the profile binds to loopback `127.0.0.1` on port `8080` with strict invariants enabled. Never commit `.env` or credential files to source control.

### Step 2: Python Control Plane Setup
Create and activate an isolated Python virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate

# Install development and testing dependencies
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
```

Verify Python package compilation:
```bash
python3 tools/lint.py
```

### Step 3: Rust System-Agent Workspace Setup
Verify that the Cargo workspace compiles and passes native unit tests:
```bash
cargo check --workspace
cargo test --workspace
```

Verify the native Tauri desktop shell crate:
```bash
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
```

### Step 4: Desktop Frontend Setup
Navigate to the presentation layer workspace and install frontend dependencies:
```bash
cd apps/desktop
npm install
npm test
cd ../..
```

### Step 5: Database Migration Setup
Initialize the local SQLite database schema using the migration engine:
```bash
python3 tools/migrate.py --db var/system_mind.db apply
python3 tools/migrate.py --db var/system_mind.db status
python3 tools/migrate.py --db var/system_mind.db verify
```

---

## 5. Daily Development Tooling

The `tools/` directory provides unified CLI utilities for daily workflows:

- **Check Prerequisites & Health:**
  ```bash
  python3 tools/dev_setup.py check
  ```
- **Run Formatting, AST Safety & Linting:**
  ```bash
  python3 tools/lint.py
  ```
- **Scan for Secret Leaks:**
  ```bash
  python3 tools/check_secrets.py
  ```
- **Run Polyglot Tests:**
  ```bash
  python3 tools/test_runner.py --all
  python3 tools/test_runner.py --unit
  python3 tools/test_runner.py --rust
  python3 tools/test_runner.py --frontend
  ```
- **Manage Database Migrations:**
  ```bash
  python3 tools/migrate.py status
  python3 tools/migrate.py plan
  python3 tools/migrate.py apply
  python3 tools/migrate.py rollback
  ```
- **Track 365-Day Development Plan:**
  ```bash
  python3 tools/day_tracker.py status
  ```
- **Clean Ephemeral Build Artifacts:**
  ```bash
  python3 tools/dev_setup.py clean
  ```

---

## 6. Monorepo Boundary Rules

1. **`src/` (Python Control Plane):** Layer 3–6. Strictly isolated from native OS system calls; all native capabilities route via IPC wire envelopes.
2. **`crates/` (Rust System-Agent):** Layer 1, 2, 6. Pure native Rust; zero dependency on Python runtime environments (`libpython`).
3. **`apps/` (TypeScript / Tauri UI):** Layer 7. Sandboxed presentation layer; zero direct shell execution (`child_process` and `eval` are strictly forbidden).
4. **`schemas/` (Language-Neutral Contracts):** JSON Schema Draft 2020-12 canonical definitions.
5. **`tools/` (Developer Tooling):** Local development automation and CI verification only; never packaged into production releases.

---

## 7. Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| `ModuleNotFoundError: No module named 'system_mind'` | Virtual environment not active or `PYTHONPATH` not set | Run `source .venv/bin/activate` or prefix commands with `PYTHONPATH=src` |
| `Banned ambient shell invocation` in `tools/lint.py` | Code uses `os.system` or `shell=True` | Refactor to `subprocess.run(["cmd", "arg"], shell=False)` in compliance with SC-01 |
| `Secret leak detected` in `tools/check_secrets.py` | Plaintext token or secret in file | Use `SecretStr` / `SecretValue` masking or add file to `.gitignore` |
| `cargo: command not found` | Rust toolchain not in `PATH` | Run `source "$HOME/.cargo/env"` or install Rust via `rustup` |
