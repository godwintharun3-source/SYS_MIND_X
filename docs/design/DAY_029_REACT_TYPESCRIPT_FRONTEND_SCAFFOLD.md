# DAY 029 — Architecture Design Note: React and TypeScript Desktop Frontend Scaffold

**Component:** Layer 7 Presentation Layer, Desktop UI & Operator Shell  
**Layer:** Layer 7 (Application & Presentation)  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Today establishes the **React and TypeScript Desktop Frontend Scaffold** (`apps/desktop/`), fulfilling the Day 029 objective of Milestone 3 (Repository and development foundation, Days 026–040).

The desktop frontend serves as the primary operator window into SYSTEM MIND X:
1. **Temporal Twin & Sensor Telemetry Visualizer**: Displays live hardware metrics, process containment trees, and digital twin topology.
2. **Governance & Approval Terminal**: Renders multi-stakeholder approval dialogs, policy precedence evaluation explanations, and biometric confirmation prompts for high/critical operations.
3. **File Trust & Sandbox Inspection**: Visualizes the 8-state file trust lifecycle, enforces the "Scan != Safe" invariant, and presents sandboxed micro-VM file execution status.
4. **Audit Ledger Inspector**: Displays tamper-evident SHA-256 cryptographic hash-chains, secret redaction verification, and retention checkpoint anchors.

---

## 2. Presentation Layer Boundary Invariants

In accordance with ADR-013 (Seven-Layer Architecture), ADR-021..024 (AI & Native Split), and ADR-036 (Monorepo Workspace Boundaries):
1. **Zero Direct Kernel Execution**: The UI layer is strictly sandboxed. It cannot invoke raw OS syscalls, execute unmediated shell commands, or link directly against internal Rust broker crates.
2. **Wire Protocol Mediation**: All interactions with the Python control plane and the Rust system agent must occur over typed `ApiRequest` and `ApiResponse` envelopes via IPC sockets or localhost HTTP/WebSocket endpoints.
3. **Mandatory Idempotency for Mutating Actions**: All mutating actions initiated from the UI must provide a unique UUIDv4 `idempotency_key` to prevent duplicate execution upon network retry or user multi-click.
4. **Transparent Explanations**: The UI must never display deceptive or decorative controls that claim a file is "100% safe" after a static scan (honoring SC-03 and ADR-030).

---

## 3. Desktop Application Architecture

```
apps/desktop/
├── package.json               # Package metadata (@system-mind/desktop v1.0.0)
├── tsconfig.json              # Strict TypeScript configuration
├── tsconfig.node.json         # Node/Vite build toolchain TypeScript config
├── vite.config.ts             # Vite bundler configuration (port 1420)
├── index.html                 # Single page application HTML host
└── src/
    ├── main.tsx               # React root mount
    ├── App.tsx                # Operator dashboard & navigation
    ├── types/
    │   └── api.ts             # TypeScript wire types (ApiRequest, ApiResponse, ErrorCode)
    ├── services/
    │   └── client.ts          # Strongly typed wire client with idempotency generation
    └── styles/
        └── index.css          # Core layout and dark-mode styling
```

---

## 4. Programmatic Scaffold Validation

The `FrontendScaffoldValidator` (in `src/system_mind/packaging/frontend_scaffold.py`):
- Verifies existence and valid JSON syntax of `apps/desktop/package.json`.
- Validates that banned ambient execution packages (e.g. `child_process`, `shelljs`, `execa`) are absent from frontend dependencies.
- Validates `tsconfig.json` enforces `strict: true`.
- Validates `vite.config.ts` and `index.html` presence.
- Verifies that TypeScript wire contracts (`api.ts`) reflect all 8 file trust states and API wire envelope fields.
