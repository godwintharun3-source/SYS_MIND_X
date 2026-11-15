# Developer Tooling Boundary (`tools/`)

**Architectural Scope:** Cross-Cutting Developer Tooling & Invariant Checkers  
**Primary Technologies:** Python 3.10+, Bash/Zsh  
**Owner:** Developer Productivity & Release Engineering  

---

## 1. Scope & Purpose
The `tools/` workspace contains developer-facing automation, gate verification scripts, local testing utilities, and the 365-day plan progress tracker (`day_tracker.py`).

## 2. Permitted Dependencies
- **Outbound:** `src/` (for gate and policy verification), `schemas/`, `monorepo.json`.
- **Inbound:** Developer terminal invocations and CI/CD pipelines.

## 3. Boundary Invariants
1. **No Production Runtime Inclusion:** Tools code is strictly for local developer workflows and CI verification; it must never be bundled into the production daemon or UI release packages.
2. **Deterministic Verification:** Release gate checks and day tracking scripts must report truthful, evidence-backed results without mocking away failures.
3. **Host Safety:** Developer tools must not modify host macOS configurations, security settings, or system extensions without explicit approval.
