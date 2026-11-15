# DAY 020 — Architecture Design Note: File Trust States and Supported File-Handler Policy

**Component:** Universal File Intelligence & Controlled Execution (`ENG-06`, `ENG-07`)  
**Layer:** Layer 4 (Digital Twin & World Model) / Layer 5 (Adaptive Policy Engine)  
**Date:** 2026-11-15  
**Author:** Principal Software Architect & SYSTEM MIND Core Team  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Problem Formulation

Modern AI computer agents routinely suffer from disastrous security vulnerabilities caused by the **Ambient Execution Fallacy**: when an agent downloads or encounters an external file (script, binary, document, archive), it frequently invokes the host shell (`python script.py`, `bash install.sh`, `open document.pdf`) under the naive assumption that an automated antivirus or static string scan proves the file is safe.

In adversarial and real-world environments:
1. **Scans do not prove safety ("Scan != Safe")**: Advanced persistent threats, zero-days, polyglot payloads, and living-off-the-land scripts easily bypass static scanners and heuristic antivirus rules.
2. **Quarantine attributes are routinely ignored**: Tools often bypass or strip macOS `com.apple.quarantine` or Windows Mark-of-the-Web (Zone.Identifier) streams, executing untrusted payloads without native Gatekeeper or SmartScreen validation.
3. **MIME type spoofing & extension confusion**: Renaming malicious executables (`malware.exe` to `invoice.pdf` or `payload.sh` to `notes.txt`) tricks unhardened parsers into arbitrary code execution.
4. **Lack of handler confinement**: Opening an active document or untrusted script with an unconfined host application grants full host filesystem and network access.

**The SYSTEM MIND Solution:**  
SYSTEM MIND X establishes an explicit, deterministic **File Trust State Machine** and **Supported File-Handler Policy Engine**. The architecture enforces a zero-trust execution model:
- No file is ever executed natively on the host unless it is cryptographically verified as an immutable OS core component, or possesses a valid, notarized vendor signature with explicit user consent.
- Static scanning and heuristic inspections move a file to `STATICALLY_INSPECTED` at best; a clean scan **never** authorizes native host execution.
- External, downloaded, or untrusted files are strictly confined to `STATIC_PARSER_ONLY`, `HARDENED_ISOLATED_VIEWER`, or `DISPOSABLE_SANDBOX_EXECUTION` (disposable micro-VMs / Landlock/Seatbelt sandboxes).

---

## 2. File Trust State Machine

```
+-----------------------------------------------------------------------------+
|                               FILE INGESTION                                |
|             (Web Download, Email Attachment, USB, Local Staging)            |
+-----------------------------------------------------------------------------+
                                       |
                   +-------------------+-------------------+
                   | Has Quarantine Marker?                |
                   v                                       v
         [ QUARANTINED ]                        [ UNTRUSTED_UNKNOWN ]
                   |                                       |
                   +-------------------+-------------------+
                                       |
                                       v
                        [ STATIC SCAN & HEURISTICS ]
                                       |
                +----------------------+----------------------+
                | Clean?                                      | Malicious?
                v                                             v
     [ STATICALLY_INSPECTED ]                       [ BLOCKED_MALICIOUS ]
  (Scan != Safe: NO Native Exec)                    (ALL Access DENIED)
                |
                +----------------------+
                |                      |
                v                      v
     [ SANDBOX DETONATION ]   [ CRYPTOGRAPHIC SIGNATURE & ORIGIN ]
                |                      |
                v                      +----------------------+
      [ SANDBOX_VERIFIED ]             |                      |
        (Micro-VM Trace)               v                      v
                |            [ VENDOR_SIGNED_OK ]   [ SYSTEM_CORE_VERIFIED ]
                |                      |                      |
                v                      v                      v
       [ USER ATTESTATION ]  [ USER_ATTESTED ]      [ SYSTEM_CORE_IMMUTABLE ]
  (Explicit Human Confirmation)        |                      |
                \                      |                      /
                 +---------------------+---------------------+
                                       |
                                       v
                         [ NATIVE HOST EXECUTION ]
                    (Strictly Gated, Preconditions Met)
```

### Discrete Trust States

1. **`UNTRUSTED_UNKNOWN`**: The default entry state for any newly observed, untracked, or externally received file. Unprivileged inspection only; zero execution.
2. **`QUARANTINED`**: File tagged with native quarantine metadata (`com.apple.quarantine` on macOS, Zone.Identifier on Windows, or untrusted browser download mark). Native execution prohibited; must remain quarantined until triaged.
3. **`STATICALLY_INSPECTED`**: File has undergone magic bytes validation, SHA-256 calculation, MIME classification, and static vulnerability heuristics. **Invariant**: "Scan != Safe" — this state explicitly prohibits native host execution.
4. **`SANDBOX_VERIFIED`**: File has undergone automated detonation within a disposable micro-VM / isolated sandbox environment with clean system call and network traces.
5. **`USER_ATTESTED`**: The human user has reviewed the provenance, hash, and threat profile, and explicitly attested trust (`user_approved=True`).
6. **`VENDOR_SIGNED_VERIFIED`**: File contains an unrevoked, cryptographically valid signature from an authorized software vendor (Apple Developer ID with Notarization, Microsoft Authenticode, or Linux distribution vendor).
7. **`SYSTEM_CORE_IMMUTABLE`**: File resides in a cryptographically sealed, SIP-protected, or read-only OS directory (`/System/Library`, `/usr/lib` on ostree/NixOS, `C:\Windows\System32`) with valid OS root attestation.
8. **`BLOCKED_MALICIOUS`**: Known malware hash, revoked certificate, spoofed identity, or malicious behavior detected during sandbox detonation. All handlers return `DENIED`.

---

## 3. Supported File-Handler Policy

### Handler Execution Modes

- **`DENIED`**: File handling is strictly rejected.
- **`STATIC_PARSER_ONLY`**: The file may be processed only by a memory-safe, unprivileged parser with zero subprocess spawning, zero network access, and zero shell invocation.
- **`HARDENED_ISOLATED_VIEWER`**: The file may be rendered in an isolated sandbox viewer with active scripting, JIT compilers, network sockets, and inter-process communication explicitly disabled.
- **`DISPOSABLE_SANDBOX_EXECUTION`**: The file may be executed exclusively within a disposable micro-VM (Hypervisor.framework, KVM, WHPX) or ephemeral container with read-only guest filesystem and zero host network access.
- **`NATIVE_HOST_EXECUTION`**: The file may be dispatched for execution directly on the native host OS kernel.

### File Category to Handler Confinement Matrix

| File Category | Trust State | Allowed Handler Modes | Max Mode | Native Host Exec? |
| :--- | :--- | :--- | :--- | :--- |
| **All Categories** | `BLOCKED_MALICIOUS` | `[DENIED]` | `DENIED` | **NO (Hard Block)** |
| **PASSIVE_DOCUMENT_DATA** | `UNTRUSTED_UNKNOWN` / `QUARANTINED` | `[STATIC_PARSER_ONLY]` | `STATIC_PARSER_ONLY` | **NO** |
| **PASSIVE_DOCUMENT_DATA** | `STATICALLY_INSPECTED` | `[STATIC_PARSER_ONLY, HARDENED_ISOLATED_VIEWER]` | `HARDENED_ISOLATED_VIEWER` | **NO** |
| **ACTIVE_DOCUMENT** | `UNTRUSTED_UNKNOWN` / `QUARANTINED` | `[DENIED]` | `DENIED` | **NO** |
| **ACTIVE_DOCUMENT** | `STATICALLY_INSPECTED` | `[HARDENED_ISOLATED_VIEWER, DISPOSABLE_SANDBOX_EXECUTION]` | `DISPOSABLE_SANDBOX_EXECUTION` | **NO** |
| **SCRIPT_OR_INTERPRETER** | `UNTRUSTED_UNKNOWN` / `QUARANTINED` | `[STATIC_PARSER_ONLY]` | `STATIC_PARSER_ONLY` | **NO** |
| **SCRIPT_OR_INTERPRETER** | `STATICALLY_INSPECTED` / `SANDBOX_VERIFIED` | `[STATIC_PARSER_ONLY, DISPOSABLE_SANDBOX_EXECUTION]` | `DISPOSABLE_SANDBOX_EXECUTION` | **NO** |
| **SCRIPT_OR_INTERPRETER** | `USER_ATTESTED` | `[STATIC_PARSER_ONLY, DISPOSABLE_SANDBOX_EXECUTION, NATIVE_HOST_EXECUTION]` | `NATIVE_HOST_EXECUTION` | **YES (With User Approval)** |
| **EXECUTABLE_BINARY** | `UNTRUSTED_UNKNOWN` / `QUARANTINED` / `STATICALLY_INSPECTED` | `[DENIED]` | `DENIED` | **NO (Hard Block)** |
| **EXECUTABLE_BINARY** | `SANDBOX_VERIFIED` | `[DISPOSABLE_SANDBOX_EXECUTION]` | `DISPOSABLE_SANDBOX_EXECUTION` | **NO** |
| **EXECUTABLE_BINARY** | `VENDOR_SIGNED_VERIFIED` | `[DISPOSABLE_SANDBOX_EXECUTION, NATIVE_HOST_EXECUTION]` | `NATIVE_HOST_EXECUTION` | **YES (Vendor Attested)** |
| **EXECUTABLE_BINARY** | `SYSTEM_CORE_IMMUTABLE` | `[DISPOSABLE_SANDBOX_EXECUTION, NATIVE_HOST_EXECUTION]` | `NATIVE_HOST_EXECUTION` | **YES (System Native)** |

---

## 4. Inviolable Security Invariants

1. **Scan != Safe Invariant**: Static vulnerability scanning, regex inspection, or antivirus signatures indicating "clean" **never** grants native host execution permissions. Static cleanliness moves a file to `STATICALLY_INSPECTED` at best.
2. **Quarantine Containment Invariant**: Files carrying native quarantine xattrs (`com.apple.quarantine`, Zone.Identifier) cannot be opened by unconfined native handlers and cannot execute natively without explicit user dequarantine.
3. **Execution Isolation Invariant**: Unsigned or untrusted binaries and scripts are strictly restricted to `DISPOSABLE_SANDBOX_EXECUTION`. Ambient execution on the host shell is completely blocked.
4. **Active Content Segregation**: Active documents with embedded macros or dynamic scripts must never be opened by passive text parsers or default unconfined office suites.
5. **System Core Path and Provenance Veracity**: A file path claiming system core status (`/System/Library/...`, `C:\Windows\System32\...`) must be verified against root mount read-only status and valid OS vendor signature. Spoofed system paths in temporary directories are immediately classified as `BLOCKED_MALICIOUS`.
