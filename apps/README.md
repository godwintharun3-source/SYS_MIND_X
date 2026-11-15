# Apps Boundary (`apps/`)

**Architectural Layer:** Layer 7 (Application & Presentation)  
**Primary Technologies:** TypeScript, React, TailwindCSS, Tauri v2  
**Owner:** Frontend & UX Engineering  

---

## 1. Scope & Purpose
The `apps/` workspace contains the user-facing desktop presentation interfaces, status visualizers, interactive capability approval dialogs, and the native Tauri application shell.

## 2. Permitted Dependencies
- **Outbound:** `schemas/` (shared type definitions and API wire envelopes).
- **Inbound:** None (Top-level application entry point).

## 3. Boundary Invariants
1. **Zero Direct Kernel Execution:** The frontend application is strictly prohibited from invoking raw native OS syscalls or privileged shell commands.
2. **Wire Protocol Mediation:** All interactions with the Python control plane and the Rust system agent must occur over typed `ApiRequest` and `ApiResponse` envelopes via IPC sockets or localhost HTTP/WebSocket endpoints.
3. **No Direct Crate Imports:** The UI layer must not link against or import internal Rust broker crates; all capability invocations route through the authenticated, audited capability broker interface.
