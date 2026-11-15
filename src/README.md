# Python Control Plane Boundary (`src/`)

**Architectural Layers:** Layer 3 (Application Context), Layer 4 (Intelligence Engines), Layer 5 (Temporal Twin), Layer 6 (Deterministic Policy Engine)  
**Primary Technologies:** Python 3.10+, Pytest, Dataclasses, Type Annotations  
**Owner:** Cognitive Systems, AI Planning & Policy Engineering  

---

## 1. Scope & Purpose
The `src/system_mind` workspace contains the high-level cognitive reasoning, modeling, and policy evaluation systems:
- `engines/`: 14 intelligence engines generating typed proposals.
- `twin/`: Temporal digital twin property graph and freshness evaluation.
- `governance/`: 4-tier deterministic policy precedence and identity verification.
- `applications/`: Tripartite application ownership classifier and exclusion enforcer.
- `updates/`: System update taxonomy and safety lifecycle validator.
- `files/`: File trust state machine and "Scan != Safe" policy evaluator.
- `contracts/`: Typed action contracts and precondition/postcondition rules.
- `audit/`: Immutable cryptographic audit ledger and secret redactor.
- `api/`: API wire envelopes, RFC 7807 error model, and SemVer 2.0.0 negotiator.

## 2. Permitted Dependencies
- **Outbound:** `schemas/` (data contracts), `crates/` (via external IPC capability calls only).
- **Inbound:** External clients via API envelopes.

## 3. Boundary Invariants
1. **Observer & Planner Only:** Python code acts strictly as an observer, analyzer, planner, and policy verifier; it is never granted ambient root or raw shell access.
2. **Deterministic Non-LLM Policy:** Policy decisions and safety constraint checks run deterministically without relying on LLM self-evaluation.
3. **No Direct Host Mutation:** The Python runtime cannot perform privileged host mutations directly; all actions must route through typed action contracts to the Rust capability broker.
