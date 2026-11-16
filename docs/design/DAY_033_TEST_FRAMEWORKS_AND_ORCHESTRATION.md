# DAY 033 — Architecture Design Note: Polyglot Test Frameworks and Test Orchestration Strategy

**Component:** Testing Infrastructure, Pytest Categorization, Cargo Integration & Polyglot Test Runner  
**Layer:** Cross-Cutting Quality Assurance & Safety Verification  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Today establishes the **Polyglot Test Frameworks and Test Orchestration Strategy**, fulfilling the Day 033 objective of Milestone 3 (Repository and development foundation, Days 026–040).

As a safety-critical system, SYSTEM MIND X mandates a rigorous testing pyramid across all three canonical language tiers:
1. **Python Control Plane (`tests/`)**: Standardized on `pytest` with formal test categorization markers (`unit`, `integration`, `e2e`, `contract`, `safety_critical`), strict marker enforcement, and comprehensive pipeline coverage.
2. **Rust System Agent & Desktop Shell (`crates/`, `apps/desktop/src-tauri/`)**: Native Rust unit tests and integration tests (`tests/broker_integration.rs`) verifying sensor telemetry collection, capability broker authorization, and "Scan != Safe" invariants.
3. **TypeScript Desktop Frontend (`apps/desktop/`)**: Vitest configuration and client unit tests (`src/__tests__/client.test.ts`) verifying wire envelope construction, client UUIDv4 idempotency keys, and offline fallback telemetry.
4. **Unified Test Orchestrator (`tools/test_runner.py`)**: A developer CLI providing selective execution of test tiers (`--unit`, `--integration`, `--e2e`, `--rust`, `--all`) with duration telemetry and failure isolation.

---

## 2. Test Classification Taxonomy

In accordance with ADR-010, ADR-017 (AG-02: Tests & Regression Pass), and ADR-031:

| Test Tier | Marker / Target | Scope & Invariants |
|---|---|---|
| **Unit Tests** | `@pytest.mark.unit`, `cargo test --lib` | Fast, deterministic, memory-only tests verifying isolated functions, validators, and models. Zero external process execution. |
| **Integration Tests** | `@pytest.mark.integration`, `cargo test --test *` | Cross-module pipeline tests verifying interactions between Observation, Temporal Digital Twin, Policy Engine, and Mock Broker. |
| **End-to-End Tests** | `@pytest.mark.e2e` | Simulated full operator sessions from UI `ApiRequest` envelopes through capability authorization, error sanitization, and immutable audit logging. |
| **Contract Tests** | `@pytest.mark.contract` | Mathematical parity and boundary tests ensuring schemas, wire types, and platform matrices match across languages. |
| **Safety-Critical Tests** | `@pytest.mark.safety_critical` | Hard invariant regression tests (SC-01 through SC-08) ensuring raw shell, user-app mutation, and uncontained file executions are blocked unconditionally. |

---

## 3. Directory Layout

```
SYSTEM_MIND_ANTIGRAVITY_365_DAY_PACK/
├── pyproject.toml                         # Pytest markers and configuration
├── tests/
│   ├── test_integration_pipeline.py      # End-to-end Python pipeline integration test
│   ├── test_e2e_governance_session.py    # Operator console E2E governance session test
│   └── test_test_framework_config.py     # Framework configuration and runner tests
├── crates/system-mind-broker/
│   └── tests/
│       └── broker_integration.rs         # Native Rust cross-crate integration test
├── apps/desktop/
│   ├── vitest.config.ts                  # Vitest frontend configuration
│   └── src/__tests__/
│       └── client.test.ts                # TypeScript wire client contract test
├── tools/
│   └── test_runner.py                    # Unified polyglot test orchestrator CLI
└── src/system_mind/packaging/
    └── test_framework.py                 # TestFrameworkValidator for CI gates
```

---

## 4. Programmatic Verification

The `TestFrameworkValidator` (`src/system_mind/packaging/test_framework.py`):
- Verifies registration of all 5 markers in `pyproject.toml` (`unit`, `integration`, `e2e`, `contract`, `safety_critical`).
- Audits the presence of integration tests across Python and Rust workspaces.
- Verifies Vitest configuration in `apps/desktop/`.
- Verifies the operational readiness of `tools/test_runner.py`.
