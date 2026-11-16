# DAY 027 — Architecture Design Note: Python Backend Package and Dependency Configuration

**Component:** Python Control Plane Packaging, Build System & Dependency Pinning  
**Layer:** Layer 3 (Context), Layer 4 (Engines), Layer 5 (Temporal Twin), Layer 6 (Policy)  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Following the establishment of the polyglot monorepo layout in Day 026, Day 027 focuses on establishing the authoritative **Python Backend Package Specification and Dependency Configuration** for the SYSTEM MIND X Control Plane (`src/system_mind`).

In safety-critical systems, ad-hoc `requirements.txt` files with floating version constraints (e.g. `package>=1.0.0`) lead to:
1. **Supply-Chain Dependency Drift**: Upstream minor/patch releases introducing breaking changes, performance regressions, or silent security vulnerabilities.
2. **Ambient Privilege & Code Detonation Risks**: Untrusted third-party packages executing malicious install hooks (`setup.py` arbitrary code execution) or importing unconfined shell execution helpers.
3. **Reproducibility Failures**: Inability to reproduce exact test and runtime environments across development, CI, and deployment targets.

**The SYSTEM MIND Solution:**
- Modern, standards-compliant `pyproject.toml` (PEP 517 / PEP 518 / PEP 621) defining build metadata, entrypoints, and exact package classifiers.
- Pinned dependency configuration (`requirements.txt` and `requirements-dev.txt`) with deterministic versions.
- Standardized package CLI entrypoint (`system-mind`) providing non-privileged administrative introspection (version, status, baseline audit, monorepo boundary check).
- Automated packaging validator (`PackageConfigValidator`) programmatically enforcing dependency pinning, prohibiting forbidden ambient packages, and verifying package metadata.

---

## 2. Package Architecture & Metadata Contract

```
pyproject.toml (PEP 621 Standard)
├── [build-system]: setuptools.build_meta
├── [project]:
│   ├── name: "system-mind-backend"
│   ├── version: "1.0.0"
│   ├── requires-python: ">=3.10"
│   ├── dependencies: Exact pinned production dependencies (Standard Library first)
│   └── scripts: system-mind = "system_mind.cli:main"
├── [project.optional-dependencies]:
│   ├── dev: pytest, pytest-cov
│   ├── types: mypy
│   └── lint: ruff, flake8, black
└── [tool.pytest.ini_options]:
    ├── testpaths: ["tests"]
    └── pythonpath: ["src"]
```

---

## 3. Dependency Invariants & Safety Rules

1. **Standard Library Prioritization**: Core domain models, state machines, and validators must run entirely on Python's standard library (`dataclasses`, `enum`, `hashlib`, `json`, `re`, `pathlib`, `tomllib`) to minimize attack surface.
2. **Strict Pinning Invariant**: Production runtime dependencies must specify exact versions (`package==X.Y.Z`). Floating ranges (`*`, `>=`) in production locks are strictly prohibited.
3. **Prohibited Packages**:
   - Zero ambient shell execution wrappers (e.g. `sh`, `plumbum`, `pexpect` in runtime).
   - Zero unvetted monkey-patching libraries.
   - Zero automatic update mutators.
4. **Non-Privileged CLI**: The `system-mind` CLI command provides read-only inspection and verification (`--version`, `--status`, `--audit-baseline`, `--verify-boundaries`). It is strictly prohibited from running raw shell commands or mutating host OS configurations.

---

## 4. Programmatic Configuration Verification

The `PackageConfigValidator`:
- Parses `pyproject.toml` using `tomllib`.
- Validates that project name is `system-mind-backend`, version is `1.0.0`, and Python requirement is `>=3.10`.
- Scans `dependencies` for unpinned constraints and prohibited packages.
- Validates `[project.scripts]` exposes `system-mind = "system_mind.cli:main"`.
- Validates pytest configuration specifies `testpaths = ["tests"]` and `pythonpath = ["src"]`.
