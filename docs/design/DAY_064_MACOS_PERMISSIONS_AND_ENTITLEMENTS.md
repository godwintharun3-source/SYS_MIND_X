# DAY 064: Document macOS Permission Prompts and Required Entitlements

## 1. Context & Architectural Goal
As the penultimate day of **Milestone 4: macOS system agent and telemetry (Days 041–065)**, SYSTEM MIND X must formalize and document the comprehensive security, entitlement, and permission architecture governing the read-only macOS companion agent.

On modern macOS (macOS 14 Sonoma and macOS 15 Sequoia on Apple Silicon), Apple enforces multi-tier security perimeters:
1. **Hardened Runtime**: Cryptographically seals binaries against code injection, DYLD tampering, and unverified library loading.
2. **Apple Entitlements**: Code signature capabilities declared in `.entitlements` property lists, validated by the kernel upon process initialization.
3. **Transparency, Consent, and Control (TCC)**: User-consent privacy database managed by `tccd`, mediating access to sensitive personal resources (Filesystem, Screen Capture, Accessibility, Input Monitoring, Media devices).
4. **System Integrity Protection (SIP)**: Authoritative kernel-level filesystem and process protection isolating macOS system roots (`/System`, `/usr/bin`, `/sbin`).

In poorly designed systems, permission management suffers from critical failures:
- **Prompt Fatigue & Nag Loops**: Invasively triggering system dialogs on every launch when permissions are denied.
- **Privilege Creep**: Requesting blanket root access, Full Disk Access, or input monitoring when user-space non-privileged APIs suffice.
- **Ambient Surveillance Abuse**: Stealthily capturing screen buffers, keypresses, or personal documents under the guise of "AI context".
- **Crash on Permission Denial**: Failing to catch `EACCES` / `PermissionError` when accessing protected resources.

Day 064 establishes the **macOS Permissions and Entitlements Architecture**, documenting all prompt triggers, required entitlements, non-goal prohibitions, and deterministic fallback strategies (`docs/MACOS_PERMISSIONS_AND_ENTITLEMENTS.md`, `src/system_mind/macos/permission_models.py`, `src/system_mind/macos/permission_inspector.py`, `crates/system-mind-sensors/src/macos_permissions.rs`).

---

## 2. Invariants & Permission Governance Contracts

| Invariant ID | Rule | Description |
| :--- | :--- | :--- |
| `INV-PERM-01` | **Least-Privilege User Domain** | The companion agent executes strictly within unprivileged user space (`gui/$UID` or user shell); running as root or prompting for `sudo` is strictly prohibited. |
| `INV-PERM-02` | **Non-Intrusive Passive Probes** | Telemetry queries must never trigger intrusive OS prompt loops. If a TCC permission is denied, the agent records the absence and gracefully activates fallback strategies. |
| `INV-PERM-03` | **Strict Prohibition of Input Monitoring** | SYSTEM MIND X explicitly rejects `kTCCServiceListenEvent` (Input Monitoring / Keylogging) and ambient OCR screen dumps (`NG-02`, `SC-01`). |
| `INV-PERM-04` | **Transparent Graceful Degradation** | Every permission denial (FDA, Screen Recording, Accessibility, Endpoint Security) maintains a deterministic fallback path and populates `unavailable_telemetry`. |
| `INV-PERM-05` | **Universal "Scan != Safe" Invariant** | Granted permissions or valid entitlements capture system operational authorization, never software safety. All permission models structurally enforce `scan_proves_safe = False`. |
| `INV-PERM-06` | **Zero Ambient Shell Authority (`SC-01`)** | All permission inspections, status assessments, and probes execute via tokenized argument vectors (`shell=False`) with strict timeouts (<= 5s). |

---

## 3. Entitlements Catalog

### 3.1 Unprivileged User Agent (`com.systemmind.useragent`)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Hardened Runtime Standard Flags -->
    <key>com.apple.security.cs.allow-jit</key>
    <false/>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <false/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <false/>
    <!-- Outbound API wire communication -->
    <key>com.apple.security.network.client</key>
    <true/>
</dict>
</plist>
```

### 3.2 Privileged Security Extension (Optional / Future Day 090+)
- `com.apple.developer.endpoint-security.client`: Requires Apple Developer Program entitlement grant and Enterprise signing certificate. In Milestone 4, this is modeled as `APPLE_RESTRICTED` with transparent user-space fallback to CoreServices FSEvents (`INV-FAULT-03`).

---

## 4. TCC Permissions & Fallback Degradation Matrix

| Permission Type | TCC Service String | Prompt Trigger API | Companion Agent Policy | Graceful Fallback Strategy | Privacy Perimeter Impact |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Full Disk Access** | `kTCCServiceSystemPolicyAllFiles` | Accessing protected directories (e.g. `~/Library/Mail`) | **Optional**. Passive inspection only; zero nag loops. | Gracefully handles `PermissionError` (EACCES), omits protected folders, records `fda_granted = False` in telemetry. | Protected files and personal mailboxes remain completely inaccessible. |
| **Screen Recording** | `kTCCServiceScreenCapture` | `CGWindowListCopyWindowInfo` / `SCShareableContent` | **Optional**. Queries window metadata only when explicitly enabled. | Omits window titles and thumbnails; privacy filter scrubs metadata; reports `screen_recording_granted = False`. | Ambient screen surveillance is structurally prevented (`NG-02`). |
| **Accessibility** | `kTCCServiceAccessibility` | `AXUIElement` / `AXIsProcessTrusted` | **Optional**. Passive focus queries only. | Falls back to `NSWorkspace.frontmostApplication` which requires zero permissions for bundle ID and app name! | Simulated user input and keystroke injection are prohibited. |
| **Files & Folders** | `kTCCServiceSystemPolicyDocumentsFolder`, `kTCCServiceSystemPolicyDownloadsFolder` | Accessing `~/Documents`, `~/Downloads` | **Excluded by Default**. | Explicitly excluded via `DEFAULT_PRIVACY_EXCLUSIONS`. Telemetry focuses on `/Applications`, `/Library`, `/System`. | User documents are never read or exfiltrated by default (`INV-PRIV-02`). |
| **Input Monitoring** | `kTCCServiceListenEvent` | `CGEventTapCreate` / `IOHIDManager` | **PROHIBITED NON-GOAL**. Never requested or implemented. | N/A (Flagged `is_banned_non_goal = True`). | Protects against keylogging, credential snooping, and covert data exfiltration. |
| **AppleEvents** | `kTCCServiceAppleEvents` | `NSAppleScript` / `OSAScript` | **PROHIBITED NON-GOAL** in read-only mode. | N/A (Read-only observation). | Prohibits unmediated cross-application scripting. |

---

## 5. Enterprise MDM Deployment (PPPC Profiles)
For enterprise fleets managed via Mobile Device Management (MDM) solutions (e.g., Jamf Pro, Kandji, Microsoft Intune), system administrators can pre-approve permissions using Apple's Privacy Preferences Policy Control (PPPC) mobileconfig payloads:
- Service: `SystemPolicyAllFiles` (Full Disk Access)
- Service: `Accessibility`
- Identifier: `com.systemmind.useragent`
- CodeRequirement: `anchor apple generic and identifier "com.systemmind.useragent" and (certificate leaf[field.1.2.840.113635.100.6.1.9] /* exists */ or certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */)`

---

## 6. Polyglot Architecture & Safety Verification
- Programmatic inspection: `src/system_mind/macos/permission_inspector.py` maps active system permissions and verifies entitlement constraints.
- Native Rust Sensor: `crates/system-mind-sensors/src/macos_permissions.rs` mirrors data structures and invariants.
- Test Suite: `tests/test_macos_permissions_and_entitlements.py` audits prompt triggers, non-goal exclusions, and charter invariants.
- Packaging Validator: `src/system_mind/packaging/macos_permissions.py` ensures continuous CI compliance.
- Developer CLI: `tools/detect_permissions.py` outputs terminal and JSON audit manifests.
