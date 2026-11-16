# DAY 030 — Architecture Design Note: Tauri Desktop Shell with a Minimal Safe Window

**Component:** Layer 7 Presentation Layer, Desktop Shell & Window Manager  
**Layer:** Layer 7 (Application & Presentation)  
**Date:** 2026-11-16  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Purpose

Day 030 establishes the **Tauri Desktop Shell with a Minimal Safe Window** (`apps/desktop/src-tauri/`), completing the native desktop container for the SYSTEM MIND X operator console established on Day 029.

The desktop shell wraps the sandboxed React 18 / TypeScript presentation layer inside a hardened native webview host. Its primary responsibilities:
1. **Safe Window Containment**: Configures a non-fullscreen, decorated, centered window with explicit minimum geometry (1280x860 default, 960x640 minimum) that ensures the operator always retains visual awareness of host OS desktop context.
2. **Strict Content Security Policy (CSP)**: Enforces an airtight CSP preventing remote script injection, untrusted CDN resource loading, or unmediated data exfiltration.
3. **Zero Ambient Shell Entitlements**: Explicitly disables Tauri's ambient shell plugin and process execution capabilities (`shell:allow-execute`, `shell:allow-spawn`), ensuring the webview cannot trigger arbitrary native operating system processes.
4. **Typed Native Bridge**: Exposes safe, bounded Tauri commands (`get_shell_info`, `inspect_window_state`, `get_security_status`) that report shell version and security posture without exposing ambient system authority.

---

## 2. Security & Window Invariants

In accordance with ADR-013, ADR-014, ADR-016 (SC-01: Zero Ambient Shell), and ADR-039:
1. **No Ambient Child Process Execution**: The shell must never grant the webview permission to execute arbitrary native binaries or shell scripts. All system mutations must continue to route via typed `ApiRequest` envelopes through the narrow privileged broker daemon.
2. **Mandatory Non-Fullscreen Default**: The operator console must never start in fullscreen mode (`fullscreen: false`), preventing deceptive phishing overlays or obscuring native host alerts.
3. **Air-gapped CSP**:
   ```
   default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*
   ```
   External origin connections and remote script sources are blocked.
4. **Declared Reverse-Domain App Identifier**: `org.systemmind.desktop` uniquely isolates local storage, window preferences, and keychain items.

---

## 3. Directory Layout

```
apps/desktop/src-tauri/
├── Cargo.toml                  # Tauri native shell crate manifest
├── tauri.conf.json             # Tauri v2 configuration (window, CSP, security)
├── capabilities/
│   └── default.json            # Tauri v2 capability grant (restricted core only)
└── src/
    ├── lib.rs                  # Safe command handlers and builder setup
    └── main.rs                 # Native desktop application entrypoint
```

---

## 4. Programmatic Validation

The `TauriShellValidator` (`src/system_mind/packaging/tauri_shell.py`):
- Verifies existence and JSON schema validity of `tauri.conf.json`.
- Validates window configuration (`fullscreen == False`, minimum bounds, decorations).
- Validates CSP rules to prevent script injection vulnerabilities.
- Validates capability definitions to ensure dangerous shell execution capabilities are absent.
- Audits `Cargo.toml` and native source files for structural integrity.
