# macOS Security Architecture: Permissions, Prompts, and Required Entitlements

## 1. Executive Summary & Core Security Principles

SYSTEM MIND X is designed from first principles as an AI-native universal computer operator and governance system founded on least privilege, deterministic boundaries, and verified security controls. The macOS companion agent (Milestone 4, Days 041–065) operates strictly in user space as a read-only telemetry engine.

### Core Security Tenets
1. **Zero Ambient Shell Authority (`SC-01`)**: The companion agent never executes unmediated shell commands (`shell=True`, `os.system`). All native operating system queries dispatch via tokenized argument vectors with bounded execution timeouts (<= 5s).
2. **Unprivileged User Domain Execution (`INV-PERM-01`)**: The companion agent executes under the console user's login session (`gui/$UID` or user shell). It does not require root escalation (`sudo`), setuid binaries, or kernel extensions.
3. **Passive Non-Intrusive Telemetry (`INV-PERM-02`)**: System inspection is strictly observational. Telemetry queries never trigger repetitive user prompt loops; missing permissions or absent sensors degrade gracefully into typed partial-data reports.
4. **Explicit Non-Goals & Privacy Boundaries (`INV-PERM-03`)**: Ambient keylogging (`kTCCServiceListenEvent`), continuous OCR screen dumps (`NG-02`), and personal document scraping are strictly prohibited architectural non-goals.
5. **Universal "Scan != Safe" Invariant (`INV-PERM-05`)**: Permission grants or valid entitlements capture operating system operational authorization, never software safety. All permission models structurally enforce `scan_proves_safe = False`.

---

## 2. macOS Security Framework Hierarchy

```
┌──────────────────────────────────────────────────────────────┐
│                   System Integrity Protection (SIP)          │
│          (/System, /usr/bin, /sbin, kernel, NVRAM immutable) │
├──────────────────────────────────────────────────────────────┤
│               Transparency, Consent & Control (TCC)          │
│       (Full Disk Access, Screen Capture, Accessibility)      │
├──────────────────────────────────────────────────────────────┤
│                 Apple Developer Entitlements                 │
│    (Endpoint Security Client, Hardened Runtime Flags)        │
├──────────────────────────────────────────────────────────────┤
│                      Hardened Runtime                        │
│   (Code Signing Integrity, DYLD Protection, JIT Disallowed)  │
├──────────────────────────────────────────────────────────────┤
│               SYSTEM MIND X macOS Companion Agent            │
│         (Unprivileged User Space, Read-Only Telemetry)       │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Entitlements Catalog

Code signature entitlements define capabilities granted to signed executables by the kernel. The companion agent maintains an explicit policy for every entitlement:

| Entitlement Key | Tier | Required / Optional | Target Component | Description & Fallback Strategy |
| :--- | :--- | :--- | :--- | :--- |
| `com.apple.security.network.client` | `STANDARD_USER` | **Required** | Desktop App / Agent | Permits outgoing network sockets to loopback API (`127.0.0.1`) and configured remote brokers. |
| `com.apple.security.files.user-selected.read-only` | `STANDARD_USER` | **Optional** | Desktop App | Permits user-selected diagnostic log ingestion via open dialogs without full disk access. |
| `com.apple.security.cs.allow-jit` | `HARDENED_RUNTIME` | **Prohibited** | Companion Agent | JIT execution is disallowed in the companion agent to enforce code immutability. |
| `com.apple.security.cs.allow-unsigned-executable-memory` | `HARDENED_RUNTIME` | **Prohibited** | Companion Agent | Disallowed to prevent arbitrary dynamic memory payload execution. |
| `com.apple.security.cs.disable-library-validation` | `HARDENED_RUNTIME` | **Prohibited** | Companion Agent | Enforces that all dynamically loaded libraries must match Apple or Developer Team ID. |
| `com.apple.developer.endpoint-security.client` | `APPLE_RESTRICTED` | **Optional (Future)** | Daemon Service | Requires Apple Enterprise Entitlement. **Milestone 4 Fallback**: Gracefully falls back to CoreServices FSEvents and Darwin `ps`. |

### Standard Hardened Runtime Entitlements Template (`com.systemmind.useragent.entitlements`)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-jit</key>
    <false/>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <false/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <false/>
    <key>com.apple.security.network.client</key>
    <true/>
</dict>
</plist>
```

---

## 4. TCC Permissions & User Prompt Catalog

Apple's Transparency, Consent, and Control (TCC) framework manages user privacy permissions. SYSTEM MIND X categorizes every TCC service according to prompt triggers, companion policies, and fallback degradation paths:

### 4.1 Full Disk Access (FDA)
- **TCC Service Identifier**: `kTCCServiceSystemPolicyAllFiles`
- **System Settings Location**: *Privacy & Security > Full Disk Access*
- **Prompt Trigger Behavior**: macOS does not emit an automatic system dialog for Full Disk Access; accessing a protected directory (e.g. `~/Library/Mail`, `~/Library/Safari`, `/Library/Application Support/com.apple.TCC`) silently raises `EACCES` (`PermissionError`).
- **Companion Agent Policy**: **Optional**. The agent never nags or prompts invasively. Protected files are omitted, privacy filters scrub metadata, and `fda_granted = False` is recorded in telemetry.
- **Graceful Fallback**: Inspects public system paths (`/Applications`, `/System/Applications`, `/Library/LaunchDaemons`, `/tmp`); reports `partial_data = True` with `PARTIAL_DATA_REASON: PERMISSION_DENIED`.

### 4.2 Screen Recording
- **TCC Service Identifier**: `kTCCServiceScreenCapture`
- **System Settings Location**: *Privacy & Security > Screen Recording*
- **Prompt Trigger Behavior**: Triggered by native window capture calls (`CGWindowListCopyWindowInfo`, `SCShareableContent`). An OS dialog displays: *"System Mind would like to record this computer's screen"*.
- **Companion Agent Policy**: **Optional**. Queries window metadata only when explicitly requested by user diagnostics.
- **Graceful Fallback**: If denied or not granted, window titles are omitted; privacy filters scrub residual window metadata; reports `screen_recording_granted = False`. The agent never takes continuous background video captures.

### 4.3 Accessibility
- **TCC Service Identifier**: `kTCCServiceAccessibility`
- **System Settings Location**: *Privacy & Security > Accessibility*
- **Prompt Trigger Behavior**: Triggered by Accessibility API probes (`AXUIElementCopyAttributeValue`, `AXIsProcessTrusted`).
- **Companion Agent Policy**: **Optional**. Used strictly for read-only focus application queries.
- **Graceful Fallback**: If denied, falls back to `NSWorkspace.frontmostApplication`, which requires **zero** Accessibility permissions for basic application name, bundle identifier, and PID! Simulated clicks and keypress injection are prohibited non-goals.

### 4.4 Files and Folders (Personal Directories)
- **TCC Service Identifiers**:
  - `kTCCServiceSystemPolicyDocumentsFolder`
  - `kTCCServiceSystemPolicyDownloadsFolder`
  - `kTCCServiceSystemPolicyDesktopFolder`
- **System Settings Location**: *Privacy & Security > Files and Folders*
- **Companion Agent Policy**: **Excluded by Default**. Personal directories (`~/Documents`, `~/Downloads`, `~/Desktop`) are filtered out by `DEFAULT_PRIVACY_EXCLUSIONS`. The companion agent does not probe these paths, eliminating user prompt fatigue.

### 4.5 Input Monitoring (`kTCCServiceListenEvent`) — PROHIBITED NON-GOAL
- **Status**: **STRICTLY PROHIBITED**.
- **Rationale**: SYSTEM MIND X rejects ambient keystroke logging, keyboard sniffing, and background credential interception (`NG-02`, `SC-01`). The companion agent never requests `kTCCServiceListenEvent` or invokes `CGEventTapCreate`.

### 4.6 Automation / AppleEvents (`kTCCServiceAppleEvents`) — PROHIBITED NON-GOAL
- **Status**: **STRICTLY PROHIBITED IN READ-ONLY MODE**.
- **Rationale**: Unmediated AppleScript execution across third-party applications violates least privilege and component ownership boundaries.

---

## 5. Comprehensive Permission Degradation Matrix

| Permission | Service Name | Trigger API | User Prompt Style | Granted Capability | Denied Fallback Strategy | Privacy Perimeter Impact |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Full Disk Access** | `kTCCServiceSystemPolicyAllFiles` | Filesystem access to protected roots | Guided System Settings navigation | Complete filesystem inventory across protected application directories | Gracefully skips protected roots; records `fda_granted = False` and `partial_data = True` | Personal mail, Safari history, and protected messages remain untouched |
| **Screen Recording** | `kTCCServiceScreenCapture` | Window list API (`CGWindowList`) | Native OS prompt dialog | Active window titles and display coordinates | Omits window titles and thumbnails; scrubs metadata; reports `screen_recording_granted = False` | Zero ambient screen dumps or covert visual surveillance |
| **Accessibility** | `kTCCServiceAccessibility` | Accessibility API (`AXUIElement`) | Native OS prompt dialog | Read-only UI element focus tracking | Falls back to `NSWorkspace.frontmostApplication` (zero permissions needed for app/PID) | Simulated mouse/keyboard injection is structurally prevented |
| **Documents Folder** | `kTCCServiceSystemPolicyDocumentsFolder` | Filesystem access to `~/Documents` | Native OS prompt dialog | Scoped reading of personal documents | Excluded by default via privacy exclusion list; never probed | Personal documents are never inspected or exfiltrated |
| **Downloads Folder** | `kTCCServiceSystemPolicyDownloadsFolder` | Filesystem access to `~/Downloads` | Native OS prompt dialog | Scoped reading of downloaded files | Excluded by default via privacy exclusion list; never probed | Downloaded files remain completely private |
| **Input Monitoring** | `kTCCServiceListenEvent` | Event taps (`CGEventTap`) | Native OS prompt dialog | **None (Prohibited)** | Flagged `is_banned_non_goal = True`; never requested | Keystroke privacy and credential entry are completely protected |
| **Endpoint Security** | `com.apple.developer.endpoint-security.client` | Kernel ES Client (`es_new_client`) | System Extension approval | Authoritative kernel-level process and file event stream | Transparently falls back to user-space CoreServices FSEvents and Darwin `ps` | Operates safely without root escalation |

---

## 6. Enterprise MDM Deployment (PPPC Profiles)

In enterprise managed environments, IT administrators can pre-configure TCC permissions for the SYSTEM MIND companion agent using Mobile Device Management (MDM) configuration profiles (e.g., Jamf Pro, Kandji, Microsoft Intune).

### Privacy Preferences Policy Control (PPPC) Specification
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadIdentifier</key>
    <string>com.systemmind.tcc.configuration</string>
    <key>PayloadType</key>
    <string>com.apple.TCC.configuration-profile-policy</string>
    <key>PayloadUUID</key>
    <string>4A2B8C9D-E1F2-43A5-9B6C-7D8E9F0A1B2C</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
    <key>Services</key>
    <dict>
        <key>SystemPolicyAllFiles</key>
        <array>
            <dict>
                <key>Identifier</key>
                <string>com.systemmind.useragent</string>
                <key>IdentifierType</key>
                <string>bundleID</string>
                <key>CodeRequirement</key>
                <string>anchor apple generic and identifier "com.systemmind.useragent" and (certificate leaf[field.1.2.840.113635.100.6.1.9] /* exists */ or certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */)</string>
                <key>Allowed</key>
                <true/>
                <key>Comment</key>
                <string>Allow read-only telemetry collection for system administration</string>
            </dict>
        </array>
    </dict>
</dict>
</plist>
```

---

## 7. Security Invariants & Compliance Verification

1. **Scan != Safe (`INV-PERM-05`)**: Permission manifests and reports indicate system access authorization, never software trustworthiness.
2. **Zero Ambient Shell (`SC-01` / `INV-PERM-06`)**: All permission audits and capability probes execute purely through memory and safe APIs; zero `os.system` or `shell=True`.
3. **Continuous Automated Regression Gating**: `MacOsPermissionsValidator` programmatically audits that all 8 core permission scenarios, required entitlements, and non-goal bans remain actively enforced in CI before release.
