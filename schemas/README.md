# Shared Schemas Boundary (`schemas/`)

**Architectural Layers:** Layer 6 (Typed Action Contracts), Layer 7 (API Wire Envelopes)  
**Primary Technologies:** JSON Schema (Draft 2020-12), Cap'n Proto, Schema IDLs  
**Owner:** Architecture & Systems Integration  

---

## 1. Scope & Purpose
The `schemas/` workspace contains language-neutral, canonical definitions of all system wire contracts, action contracts, error representations, and audit event schemas. It serves as the single source of truth across TypeScript, Rust, and Python components.

## 2. Permitted Dependencies
- **Outbound:** None (Strictly self-contained).
- **Inbound:** `apps/`, `crates/`, `src/`, `tools/`.

## 3. Boundary Invariants
1. **Language-Neutral:** Schemas must not contain language-specific implementations, runtime dependencies, or target-specific bindings.
2. **Backwards Compatibility:** All schema changes must adhere to SemVer 2.0.0 rules; breaking schema changes require a major version bump.
3. **Self-Contained:** Schemas may reference other schemas within `schemas/`, but must never reference external code or repository artifacts.
