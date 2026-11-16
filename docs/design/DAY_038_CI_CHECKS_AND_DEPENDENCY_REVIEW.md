# DAY 038 — CI Checks for Formatting, Linting, Tests, and Dependency Review

**Status:** IMPLEMENTED  
**Date:** 2026-11-16  
**Milestone:** Milestone 3 — Repository and development foundation (Days 026–040)  
**System Plane:** CI/CD Automation & Supply-Chain Security (`.github/workflows/`, `tools/`, `src/system_mind/packaging/`)

---

## 1. Architectural Objective & Context

SYSTEM MIND X requires deterministic, automated, and tamper-evident continuous integration (CI) pipelines to uphold charter invariants across all polyglot tiers: Python Control Plane, Rust System-Agent & Broker, and TypeScript Desktop Frontend.

Day 038 establishes:
1. Production-grade GitHub Actions CI workflow definitions (`.github/workflows/ci.yml`).
2. Automated dependency supply-chain security and review workflow (`.github/workflows/dependency-review.yml`).
3. Programmatic dependency auditor (`src/system_mind/packaging/dependency_review.py`).
4. Unified local CI runner CLI (`tools/ci_runner.py`) for pre-push verification in unprivileged user space.
5. Programmatic packaging validator (`src/system_mind/packaging/ci_checks.py`).

---

## 2. Inviolable Safety & Architecture Invariants

The CI and dependency review system enforces five cardinal architectural invariants:

1. **Supply-Chain Determinism & Exact Pinning (INV-CI-01):**
   All production and development Python dependencies must declare exact pinned versions (`package==X.Y.Z`). Float ranges (`>=`, `~=`, `*`) are rejected.
2. **Ambient Execution Library Prohibition (SC-01 / INV-CI-02):**
   Ambient shell execution libraries—including Python packages `sh`, `plumbum`, `pexpect`, `ptyprocess`, `fabric` and Node.js packages `child_process`, `execa`, `shelljs`, `sudo-prompt`, `node-pty`—are strictly banned across all dependency manifests.
3. **Rust Runtime Isolation (INV-CI-03):**
   Rust system agent crates (`system-mind-common`, `system-mind-sensors`, `system-mind-broker`) must remain pure native Rust; dependencies on Python runtime bindings (`pyo3`, `libpython`) or unconfined shell wrappers are forbidden.
4. **Polyglot Test Gate Enforcement (INV-CI-04):**
   CI jobs must execute across all three language tiers. Any failure in Python tests, Rust workspace tests, Tauri desktop tests, or frontend Vitest tests blocks branch merging.
5. **Local Execution Parity (INV-CI-05):**
   Every CI check executed remotely in GitHub Actions must be reproducible locally via `tools/ci_runner.py` in unprivileged user space without requiring administrator or root credentials.

---

## 3. GitHub Actions Workflows Architecture

### 1. `.github/workflows/ci.yml`
Runs on `push` and `pull_request` against `main` and `develop` branches:
- **`lint-and-safety` Job:**
  - Python syntax validation (`py_compile`).
  - AST safety analysis detecting forbidden `os.system` and `subprocess(shell=True)`.
  - Static linting: Black (`black --check`), Flake8 (`flake8`), Mypy (`mypy src/ tools/`).
  - Secret leak scanner (`tools/check_secrets.py`).
  - Cross-language schema parity verification (`tools/generate_types.py --check`).
- **`test-python` Job:**
  - Matrix across Python 3.10, 3.11, 3.12.
  - Executes unit, contract, integration, and e2e test tiers.
- **`test-rust` Job:**
  - `cargo fmt --all -- --check`.
  - `cargo clippy --workspace -- -D warnings`.
  - `cargo test --workspace`.
  - `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`.
- **`test-frontend` Job:**
  - Presentation boundary linting in `apps/desktop/`.
  - Vitest test suite (`npm test`).
- **`database-migrations` Job:**
  - Executes SQLite migration lifecycle (`tools/migrate.py status`, `plan`, `apply`, `verify`).

### 2. `.github/workflows/dependency-review.yml`
- Scans dependency manifests (`requirements.txt`, `requirements-dev.txt`, `Cargo.toml`, `apps/desktop/package.json`).
- Executes `DependencyReviewer` verifying strict pinning and absence of banned ambient execution packages.

---

## 4. Programmatic Dependency Reviewer

`src/system_mind/packaging/dependency_review.py` defines:
- **`BANNED_PYTHON_PACKAGES`**: `{"sh", "plumbum", "pexpect", "ptyprocess", "fabric"}`.
- **`BANNED_NODE_PACKAGES`**: `{"child_process", "execa", "shelljs", "sudo-prompt", "node-pty"}`.
- **`BANNED_RUST_CRATES`**: `{"pyo3", "cpython", "inline-python"}`.
- **`DependencyReviewer.audit()`**: Inspects all package manifests and returns `DependencyReviewResult`.

---

## 5. Local CI Orchestrator (`tools/ci_runner.py`)

Provides a unified non-privileged CLI for developers to run CI stages before pushing:
- `python3 tools/ci_runner.py lint`: Runs AST safety, linting, secrets scan, and schema parity.
- `python3 tools/ci_runner.py test`: Runs polyglot test suites across Python, Rust, and Frontend.
- `python3 tools/ci_runner.py deps`: Runs dependency supply-chain review.
- `python3 tools/ci_runner.py all`: Runs all stages sequentially.
- Supports `--dry-run` and `--json`.
