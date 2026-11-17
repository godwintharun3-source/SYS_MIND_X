# DAY 055: Swift-to-Rust and Swift-to-Python Bridge Boundary

**Date:** 2026-11-17  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Status:** In Progress  
**Author:** SYSTEM MIND X Architecture & Platform Engineering Team  

---

## 1. Executive Summary and Architectural Context

macOS provides a rich set of platform-specific frameworks (`AppKit`, `Foundation`, `IOKit`, `OSLog`, `CoreWLAN`, `UniformTypeIdentifiers`, `SMAppService`) that are natively designed for Swift and Objective-C. While SYSTEM MIND X utilizes Python for its intelligence and temporal digital twin (Layers 3–6) and Rust for its physical sensor abstraction and privileged broker (Layers 1–2, 6), invoking modern macOS user-session APIs directly from C or Python subprocess pipes presents several challenges:
1. **ABI Fragility and Memory Safety:** Calling Objective-C runtime functions directly via `ctypes` or `objc` FFI in Python or Rust is error-prone, lacks compile-time safety, and easily leads to reference counting crashes.
2. **User Session Scope (`USER_AGENT`):** Modern macOS user experience APIs (such as `NSWorkspace.shared.frontmostApplication`, window server metadata, and display power assertions) are only accessible within the user's graphical login session. A daemon running as a launchd system daemon cannot reliably access these APIs.
3. **Least Privilege Invariants (`SC-01` / `INV-SWIFT-01`):** The companion agent must run with standard user permissions, collecting read-only telemetry without escalating privileges or executing unrestricted shell commands.

Day 055 establishes the **Swift-to-Rust and Swift-to-Python Bridge Boundary**. The architecture introduces a lightweight, memory-safe native Swift companion agent (`SystemMindCompanion` in `apps/macos-companion/`) communicating with the Python control plane and the Rust sensor framework via a typed wire IPC protocol (line-delimited JSON / JSON-RPC 2.0).

---

## 2. Architectural Invariants

| ID | Title | Invariant Specification |
| :--- | :--- | :--- |
| `SC-01` | **Zero Ambient Shell Authority** | Subprocess bridge calls dispatch via tokenized argument lists (`shell=False`) with strict timeouts (<= 3 seconds). No shell wrappers (`sh -c`, `bash -c`). |
| `INV-SWIFT-01` | **Least-Privilege User Companion Boundary** | The Swift companion runs strictly in unprivileged user space (`USER_AGENT` / login session). It never prompts for `sudo`, escalates privileges, or executes root operations. |
| `INV-SWIFT-02` | **Strict Typed Wire Contract** | All communication across language boundaries adheres to strongly typed JSON-RPC 2.0 schemas. Unstructured strings and raw error codes are rejected. |
| `INV-SWIFT-03` | **Strictly Read-Only Telemetry** | The bridge exposes strictly observational queries (e.g., thermal state, frontmost app, system uptime, TCC permissions status). Mutating window manager, accessibility, or system state actions are strictly excluded. |
| `INV-SWIFT-04` | **Non-Negotiable Charter Invariant ("Scan != Safe")** | Telemetry collected via the Swift bridge reports system observations, not behavioral safety. All models structurally enforce `scan_proves_safe = False`. |
| `INV-SWIFT-05` | **Graceful Fallback & Mock Degradation** | If Swift compiler/binary is unavailable, or when running on non-Darwin platforms (Linux/Windows), the bridge gracefully falls back to deterministic mock fixtures and records unsupported capabilities in `unavailable_telemetry`. |

---

## 3. Bridge Topology and Wire Protocol

```
    +-----------------------------+           +-----------------------------+
    |   Python Control Plane      |           |     Rust System Sensors     |
    | (src/system_mind/macos/)    |           | (crates/system-mind-sensors)|
    +-----------------------------+           +-----------------------------+
                   \                                         /
                    \                                       /
                     v                                     v
         +-------------------------------------------------------------+
         |                Typed Wire Protocol (JSON-RPC)               |
         |        Tokenized Subprocess Vector (shell=False)            |
         +-------------------------------------------------------------+
                                        |
                                        v
         +-------------------------------------------------------------+
         |               Native Swift Companion Agent                  |
         |                 (apps/macos-companion)                      |
         |                                                             |
         |  • ProcessInfo.processInfo.thermalState (Thermal Telemetry)  |
         |  • NSWorkspace.shared.frontmostApplication (Active Focus)   |
         |  • IOKit / IOPMPowerSource (Display / Power State)          |
         |  • System Uptime & Console User                             |
         |  • TCC Permissions Probe (Read-Only Preflight)             |
         +-------------------------------------------------------------+
```

### Protocol Schema (JSON-RPC 2.0)
- **Request:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": "req-001",
    "method": "get_system_telemetry",
    "params": {}
  }
  ```
- **Response:**
  ```json
  {
    "jsonrpc": "2.0",
    "id": "req-001",
    "result": {
      "thermal_state": "NOMINAL",
      "frontmost_app": {
        "name": "Terminal",
        "bundle_id": "com.apple.Terminal",
        "pid": 4210,
        "path": "/System/Applications/Utilities/Terminal.app"
      },
      "permissions": {
        "accessibility_granted": false,
        "screen_recording_granted": false,
        "full_disk_access_granted": true
      },
      "system_uptime_seconds": 84210.5,
      "console_user": "tharungodwin",
      "screen_locked": false,
      "timestamp": "2026-11-17T11:00:00Z",
      "host_platform": "Darwin",
      "bridge_channel": "SWIFT_NATIVE_IPC",
      "scan_proves_safe": false,
      "unavailable_telemetry": [],
      "is_mock": false
    }
  }
  ```

---

## 4. Verification and Acceptance Plan

1. **Native Swift Package:** Create `Package.swift` and Swift sources in `apps/macos-companion/Sources/SystemMindCompanion/`.
2. **Strongly Typed Models:** Implement Python data models in `src/system_mind/macos/swift_models.py` and Rust structs in `crates/system-mind-sensors/src/macos_swift_bridge.rs`.
3. **Bridge Engine:** Implement `MacSwiftBridge` in `src/system_mind/macos/swift_bridge.py` supporting live binary dispatch and deterministic mock fixtures.
4. **Developer CLI:** Build `tools/detect_swift_bridge.py` supporting table, `--mock`, and `--json`.
5. **Packaging Validator:** Implement `src/system_mind/packaging/macos_swift_bridge.py`.
6. **Test Suite:** Author `tests/test_macos_swift_bridge.py` verifying contracts, live/mock execution, AST safety, and packaging audits.
