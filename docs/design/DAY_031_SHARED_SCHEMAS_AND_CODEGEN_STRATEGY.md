# DAY 031 — Architecture Design Note: Shared Schemas and Generated API Type Strategy

**Component:** Shared IDL Contracts, Code Generation & Cross-Language Parity  
**Layer:** Layer 6 (Typed Action Contracts) & Layer 7 (API Wire Envelopes)  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Today establishes the **Shared Schemas and Generated API Type Strategy** (`schemas/`), fulfilling the Day 031 objective of Milestone 3 (Repository and development foundation, Days 026–040).

SYSTEM MIND X is an inherently polyglot architecture spanning three execution domains:
1. **Python Control Plane (`src/`)**: 14 Intelligence Engines, Temporal Digital Twin, Deterministic Policy Engine.
2. **Rust System Agent (`crates/` & `apps/desktop/src-tauri/`)**: High-performance hardware sensors, narrow capability broker, and native desktop shell.
3. **TypeScript Desktop Frontend (`apps/desktop/`)**: Accessible operator console, telemetry visualizers, and interactive governance approval dialogs.

To prevent structural contract drift, serialization mismatches, and semantic desynchronization across languages, the system establishes `schemas/` as the single canonical source of truth using standardized JSON Schema (Draft 2020-12 / Draft 7).

---

## 2. Core Canonical Schemas

| Schema File | Domain | Core Architectural Invariants Enforced |
|---|---|---|
| `schemas/api_envelope.schema.json` | API Wire Protocol | Unified `ApiRequest`, `ApiResponse`, RFC 7807 problem details, error codes `E1000..E7999`, mandatory `idempotency_key` on mutating operations. |
| `schemas/file_trust.schema.json` | File Trust Lifecycle | Inviolable 8-state model (`QUARANTINED`, `VERIFIED`, `SANDBOXED`, `BLOCKED`, `ALLOWLISTED`, `PROVENANCE_PENDING`, `SECURITY_REVOKED`, `STATIC_ANALYSIS_FAILED`). SC-03: Scan != Safe. |
| `schemas/component_ownership.schema.json` | Component Boundaries | Tripartite ownership (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`). Exclusion of user apps/dependencies from auto-updates. |
| `schemas/action_contract.schema.json` | Execution Broker | Typed action contracts, 5 risk tiers (`READ_ONLY` to `CRITICAL_PRIVILEGED`), pre/post conditions, and mandatory rollback contracts. |
| `schemas/audit_event.schema.json` | Audit & Compliance | Cryptographic SHA-256 hash-chain linkage, actor URNs, deep secret redaction markers, and 5-tier retention classification. |

---

## 3. Polyglot Code Generation & Parity Strategy

```
                          ┌────────────────────────────────┐
                          │   schemas/*.schema.json        │
                          │   (Canonical Source of Truth)   │
                          └───────────────┬────────────────┘
                                          │
                        ┌─────────────────┴─────────────────┐
                        │   Type Generation & Parity Engine │
                        │      (tools/generate_types.py)    │
                        └─────────────────┬─────────────────┘
                ┌─────────────────────────┼─────────────────────────┐
                ▼                         ▼                         ▼
   ┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
   │         Python          │ │       TypeScript        │ │          Rust           │
   │  src/system_mind/api/   │ │   apps/desktop/src/     │ │ crates/system-mind-common │
   │  dataclasses & models   │ │  types/api.ts interfaces│ │      enums & structs      │
   └─────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘
```

The generation strategy supports two complementary modes:
1. **Verification / Dry-Run (CI Mode)**: Programmatically verifies that all target language type definitions and enums match the canonical schemas with zero drift.
2. **Deterministic Code Generation**: Generates strongly typed language models and interfaces directly from the canonical JSON Schemas.

---

## 4. Programmatic Validation Invariants

The `SchemaStrategyValidator` (`src/system_mind/schemas/validator.py`):
1. **Schema Syntax & Metadata**: Validates that all `.schema.json` files parse as valid JSON Schema Draft 2020-12 and declare `$id`, `title`, and `description`.
2. **Cross-Language Enum Parity**: Verifies that every enum variant declared in canonical schemas is present across Python, TypeScript, and Rust definitions without omission or semantic renaming.
3. **Wire Envelope Invariants**: Validates that mutating operations strictly require `idempotency_key`, preventing duplicate dispatch over IPC and network sockets.
