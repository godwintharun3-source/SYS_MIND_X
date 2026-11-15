# Documentation Boundary (`docs/`)

**Architectural Scope:** Architecture Specifications, Decision Logs & Governance  
**Primary Technologies:** Markdown, GitHub-Flavored Markdown, KaTeX, Mermaid  
**Owner:** System Architecture & Technical Leadership  

---

## 1. Scope & Purpose
The `docs/` workspace contains the authoritative architectural specifications, architecture decision records (`DECISION_LOG.md`), 365-day roadmap (`ROADMAP_365_DAYS.md`), daily execution records (`DAILY_LOG.md`), blockers log (`BLOCKERS.md`), release acceptance gates (`ACCEPTANCE_GATES.md`), and detailed design notes (`docs/design/`).

## 2. Permitted Dependencies
- **Outbound:** None (Self-contained documentation).
- **Inbound:** Referenced by engineers, agents, and verification tooling.

## 3. Boundary Invariants
1. **Source of Truth:** Architectural decisions and charter invariants documented in `docs/` govern all implementation across `apps/`, `crates/`, and `src/`.
2. **Zero Executable Code:** The `docs/` workspace contains only documentation, specifications, and diagrams; executable code must reside in code workspaces.
3. **Traceability:** Every major architectural change must record a corresponding Architecture Decision Record (ADR) in `DECISION_LOG.md`.
