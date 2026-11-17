# DAY 056: Create a Least-Privilege macOS User Agent Service

**Date:** 2026-11-17  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Status:** Completed & Verified  
**Author:** SYSTEM MIND X Architecture & Platform Engineering Team  

---

## 1. Executive Summary and Problem Statement

On macOS, background software components managed by `launchd` belong to two fundamentally distinct architectural categories:
1. **LaunchDaemons (`/Library/LaunchDaemons`, `/System/Library/LaunchDaemons`):**
   - Execute in the `system` domain as `root` (UID 0).
   - Operate outside user graphical login sessions; unable to directly interact with `NSWorkspace`, active GUI focus, or user notification centers.
   - Present a substantial blast radius: a compromised daemon can mutate core OS components, bypass security boundaries, or execute unrestricted root commands.
2. **LaunchAgents (`~/Library/LaunchAgents`, `/Library/LaunchAgents`):**
   - Execute in the `gui/$UID` or `user/$UID` domain as the unprivileged console user (`UID != 0`).
   - Have natural, native access to the user's graphical session (Aqua): thermal throttling states, display sleep notifications, active frontmost application focus, and user defaults.
   - Strictly bounded by standard user privilege limits: cannot modify System Integrity Protection (SIP) protected assets, cannot inspect or mutate other users' home directories, and cannot execute privileged system mutations without explicit elevation.

In accordance with the SYSTEM MIND X Charter (`PROJECT_CHARTER.md`) and Safety Rules (`AGENTS.md`), the architecture strictly prohibits granting the AI or companion system ambient root or administrator authority. Therefore, Day 056 formalizes the **Least-Privilege macOS User Agent Service** (`com.systemmind.useragent`).

The user agent service operates strictly in the `gui/$UID` domain as a standard user process. It orchestrates the native Swift companion bridge (Day 055) and FSEvents telemetry (Day 053) to provide continuous, high-fidelity system observability with zero elevated privileges.

---

## 2. Architectural Invariants

| ID | Title | Invariant Specification |
| :--- | :--- | :--- |
| `SC-01` | **Zero Ambient Shell Authority** | All subprocess queries dispatch via tokenized argument lists (`shell=False`) with strict timeouts (<= 3 seconds). No ambient shell invocation (`sh -c`, `bash -c`). |
| `INV-AGENT-01` | **Least-Privilege User Domain Execution** | The service definition strictly specifies domain `gui/$UID` (User Agent), running under the active user's UID (non-root). It NEVER requires `sudo`, escalates privileges, or executes as a root LaunchDaemon. |
| `INV-AGENT-02` | **Strictly Read-Only Observational Scope** | The user agent service polls and streams read-only telemetry (thermal pressure, frontmost application focus, system uptime, and TCC permissions preflight). It has zero mutating execution authorities. |
| `INV-AGENT-03` | **Declarative LaunchAgent Specification** | The service configuration adheres to Apple launchd LaunchAgent specifications (`com.systemmind.useragent.plist`) declaring `LimitLoadToSessionType = ["Aqua"]`, low process priority (`Nice = 10`), and user-sandboxed log paths (`~/Library/Logs/system-mind/`). |
| `INV-AGENT-04` | **Non-Negotiable Charter Invariant ("Scan != Safe")** | Background user agent telemetry records operational metrics, not application safety; all models and reports structurally enforce `scan_proves_safe = False`. |
| `INV-AGENT-05` | **Safe Mock & Non-Darwin Fallback** | Non-Darwin hosts or unmanaged test environments gracefully return `UNAVAILABLE_PLATFORM` or deterministic simulation fixtures (`running_agent`, `stopped_agent`, `uninstalled_agent`). |

---

## 3. LaunchAgent Service Specification

The declarative property list configuration for `com.systemmind.useragent.plist` is defined as follows:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.systemmind.useragent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/system-mind-companion</string>
        <string>--daemon</string>
    </array>
    <key>LimitLoadToSessionType</key>
    <array>
        <string>Aqua</string>
    </array>
    <key>ProcessType</key>
    <string>Background</string>
    <key>Nice</key>
    <integer>10</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>~/Library/Logs/system-mind/useragent.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>~/Library/Logs/system-mind/useragent.stderr.log</string>
</dict>
</plist>
```

---

## 4. Threat Model and Boundary Controls

| STRIDE Category | Threat Vector | SYSTEM MIND X Architectural Defense |
| :--- | :--- | :--- |
| **Elevation of Privilege** | Rogue agent process attempts to acquire root privileges. | Service is registered in `gui/$UID` (User Agent); `is_root` is verified false. Root escalation is architecturally blocked. |
| **Information Disclosure** | Agent attempts to read other users' documents or private credentials. | Bounded by Darwin POSIX user permissions; cannot read other users' `/Users/*` folders. Privacy path exclusions enforced. |
| **Denial of Service** | Agent loop consumes excessive CPU cycles or thermal budget. | Service is assigned `Nice = 10` and `ProcessType = Background`, ensuring it yields scheduler time to interactive user apps. |
| **Tampering** | External script alters agent plist to execute arbitrary payloads. | Plist location is verified in `~/Library/LaunchAgents` with ownership matching logged-in UID. |

---

## 5. Verification and Acceptance Plan

1. **Strongly Typed Models:** Author data models in `src/system_mind/macos/agent_service_models.py` (`AgentServiceState`, `LaunchAgentConfig`, `AgentServiceStatusReport`).
2. **Service Detector & Plist Generator:** Implement `MacUserAgentServiceManager` in `src/system_mind/macos/agent_service_detector.py`.
3. **Native Rust Sensor Collector:** Author `crates/system-mind-sensors/src/macos_user_agent.rs` with unit tests.
4. **Developer CLI:** Author `tools/detect_user_agent.py` supporting status audit, mock profiles, and declarative plist generation.
5. **Programmatic Validator:** Author `src/system_mind/packaging/macos_user_agent.py`.
6. **Comprehensive Test Suite:** Author `tests/test_macos_user_agent.py` verifying models, least privilege, plist schema, live/mock execution, AST safety, and packaging audits.
