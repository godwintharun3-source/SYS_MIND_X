# DAY 032 — Architecture Design Note: Multi-Language Formatting, Linting, and Static Analysis

**Component:** Code Quality Tooling, Linter Configurations & Static Analysis Gate  
**Layer:** Cross-Cutting Developer Tooling & Verification Gates  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Day 032 establishes a deterministic, multi-language **Code Quality, Formatting, Linting, and Static Analysis Framework** across all three canonical monorepo tiers:
1. **Python Control Plane (`src/`, `tools/`, `tests/`)**: Black formatting standards, Flake8 & Ruff linting rules, and Mypy strict type checking configuration.
2. **Rust System Agent & Desktop Shell (`crates/`, `apps/desktop/src-tauri/`)**: `rustfmt.toml` code formatting and `clippy.toml` static analysis linter rules enforcing memory-safety and cognitive complexity bounds.
3. **TypeScript Desktop Frontend (`apps/desktop/`)**: ESLint AST configuration prohibiting ambient execution wrappers (`child_process`, `shelljs`, `eval`) and Prettier formatting specifications.
4. **Unified Verification Orchestration (`tools/lint.py`)**: A non-privileged developer CLI that verifies code style, syntax validity (`py_compile`), AST safety patterns, and pre-commit configurations.
5. **Pre-Commit Gate (`.pre-commit-config.yaml`)**: Standardized hook definitions preventing uninspected code, trailing whitespaces, merge markers, and safety invariant violations from entering Git branches.

---

## 2. Invariants & Security Boundaries

In accordance with ADR-008, ADR-016 (SC-01..SC-08), and ADR-036:
1. **Zero Ambient Shell Enforcement in Linters**:
   - Python AST checks forbid `os.system(...)`, `subprocess.call(..., shell=True)`, and ambient execution imports (`sh`, `plumbum`, `pexpect`).
   - ESLint config forbids Node.js `child_process` and browser `eval(...)` execution.
2. **Safe Default Window & CSP Invariants**:
   - Tauri configs are validated against strict CSP and non-fullscreen defaults.
3. **Deterministic Local Tooling**:
   - All linters and checkers must run locally in unprivileged user space without requiring network downloads, remote telemetry, or elevated permissions.
4. **Lockfile & Version Pinning**:
   - Tool versions and hook configurations are deterministically pinned to prevent supply-chain drift.

---

## 3. Configuration Layout

```
SYSTEM_MIND_ANTIGRAVITY_365_DAY_PACK/
├── .flake8                     # Flake8 style & complexity configuration
├── .pre-commit-config.yaml     # Pre-commit hook definitions for all tiers
├── rustfmt.toml                # Rust standard formatting rules
├── clippy.toml                 # Clippy static analysis and safety rules
├── pyproject.toml              # [tool.black], [tool.mypy], [tool.ruff] configurations
├── apps/desktop/
│   ├── .eslintrc.json          # ESLint strict AST & React security rules
│   └── .prettierrc.json        # Prettier formatting rules for frontend
├── tools/
│   └── lint.py                 # Multi-language linter orchestrator CLI
└── src/system_mind/packaging/
    └── code_quality.py         # CodeQualityValidator for CI pipelines
```

---

## 4. Programmatic Verification

The `CodeQualityValidator` (`src/system_mind/packaging/code_quality.py`):
- Verifies the presence and syntax correctness of all 6 quality configurations.
- Audits `pyproject.toml` to ensure `[tool.black]`, `[tool.mypy]`, and `[tool.ruff]` are declared.
- Verifies that forbidden exception directives (e.g. silencing ambient shell violations) are absent.
- Executes Python syntax compilation and safe static AST safety checks.
