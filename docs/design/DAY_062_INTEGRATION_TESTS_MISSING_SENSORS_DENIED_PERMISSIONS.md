# Design Note: DAY-062 — Integration Testing Under Missing Sensors and Denied Permissions

## 1. Context and Problem Statement
In production deployments, the SYSTEM MIND X macOS companion agent operates within an unprivileged, multi-tenant, least-privilege desktop environment. Operating system telemetry cannot assume optimal hardware presence or all-powerful privileges:
- **Missing Sensors & Heterogeneous Hardware:**
  - Desktop Apple Silicon (Mac Studio, Mac Pro, Mac mini) has no battery subsystem (`pmset -g batt` indicates AC power with zero internal battery).
  - Headless servers or virtualized testing hosts lack built-in Retina displays or external monitors.
  - Air-gapped or offline development environments lack active Wi-Fi/Ethernet links, presenting only loopback interfaces (`lo0`).
  - Intel-based legacy Macs lack asymmetric Apple Silicon Performance and Efficiency core topology.
  - Bare host USB topologies lack external peripherals, containing only built-in host controllers.
- **Permission Denials & OS Security Confinement:**
  - Standard user execution strictly denies `root` / `sudo` access, precluding native initialization of the macOS Endpoint Security subsystem (`ES_NEW_CLIENT_RESULT_ERR_NOT_PRIVILEGED`).
  - Production binary distribution lacks Apple-restricted development entitlements (`com.apple.developer.endpoint-security.client`), returning `ES_NEW_CLIENT_RESULT_ERR_NOT_ENTITLED`.
  - Apple TCC (Transparency, Consent, and Control) gates deny Full Disk Access (FDA), Accessibility, or Screen Recording permissions to unprivileged companion processes.
  - System launchd domains (`/System/Library/LaunchDaemons`) reject user-level inspection or mutation, confining the agent to `gui/$UID`.

The architecture must prove through deterministic integration tests that **sensor absence or permission denials never cause unhandled exceptions, orchestrator deadlocks, silent telemetry omissions, or safety invariant violations**.

---

## 2. Architectural Principles & Safety Invariants

### 2.1 Principle of Graceful Partial-Data Transparency (`INV-FAULT-01`)
When any sensor or subsystem is absent or denied access:
- The aggregation layer (`CollectorHealthManager`, `MacOsObservationEngine`, and `MacOsInventoryApi`) must continue execution, bounding every sensor query within strict timeout envelopes (<= 2.0s).
- The resulting payload must explicitly set `partial_data = True` and populate `unavailable_telemetry` or `unavailable_fields` with typed root-cause categorizations (`HARDWARE_ABSENT`, `PERMISSION_DENIED`, `PLATFORM_UNSUPPORTED`, `TIMEOUT`, `COMMAND_ERROR`).

### 2.2 Unwavering "Scan != Safe" Invariant (`INV-FAULT-02`)
In accordance with the SYSTEM MIND X Product Charter and ADR-008:
- Partial, degraded, or restricted scans must never imply safety.
- Regardless of whether zero anomalies are detected due to denied permissions or missing sensors, all emitted envelopes, reports, and API responses must structurally enforce `scan_proves_safe = False`.

### 2.3 Transparent Fallback Telemetry (`INV-FAULT-03`)
When low-level kernel APIs (such as Endpoint Security) are restricted due to permissions or entitlements:
- The system must transparently activate user-space fallback mechanisms (e.g. Apple CoreServices FSEvents for filesystem event streams, Darwin `ps` for process lifecycles, and launchd user domain queries).
- Fallback activations must be explicitly reported in the telemetry envelope.

### 2.4 Deterministic Confidence Penalty Propagation (`INV-FAULT-04`)
Data quality scores computed by `MacOsObservationEngine` must deduct explicit, auditable penalties:
- Hardware absent: -0.20 deduction
- Permission / entitlement denied: -0.35 deduction
- Text parsing heuristic fallback: -0.20 deduction
- Mock simulation profile: -0.60 deduction
The resulting confidence score must accurately reflect reduced visibility.

### 2.5 Zero Ambient Shell Authority (`SC-01` / `INV-FAULT-05`)
All fault injection, simulated permission denials, and degraded integration runs must execute via tokenized argument vectors with `shell=False` and timeouts <= 5s.

---

## 3. Integration Fault Injection Matrix

| Test Scenario ID | Subsystem Target | Injected Fault / Condition | Expected Behavior & Output | Invariants Verified |
|---|---|---|---|---|
| **INT-FAULT-01** | Battery Hardware | Desktop Mac with AC power only (`pmset` reports no battery) | `is_battery_present = False`, `power_source = AC_POWER`, battery health is None; inventory populates `battery: null`; confidence reflects missing hardware. | `partial_data = True`, `scan_proves_safe = False` |
| **INT-FAULT-02** | Network Connectivity | Air-gapped / Offline host (all interfaces down except `lo0`) | `is_online = False`, default gateway is None, DNS list is empty; interfaces report loopback only; health marks nominal offline state. | `scan_proves_safe = False`, zero network stalls |
| **INT-FAULT-03** | Endpoint Security | Non-root caller & missing ES entitlement | Returns `ES_NEW_CLIENT_RESULT_ERR_NOT_PRIVILEGED` & `ERR_NOT_ENTITLED`; transparently activates FSEvents and ps fallbacks; confidence tier reflects heuristic parsing. | `scan_proves_safe = False`, zero privilege escalation |
| **INT-FAULT-04** | TCC Full Disk Access | Denied access to protected directory (`~/Library/Mail` -> EACCES) | `PermissionError` caught; path added to `unavailable_telemetry`; health reports `PERMISSION_DENIED`; app scanner skips without aborting. | `partial_data = True`, `scan_proves_safe = False` |
| **INT-FAULT-05** | TCC Desktop & Focus | Denied Screen Recording & Accessibility | Swift bridge reports `screen_recording_granted = False`, `accessibility_granted = False`; window titles and captures cleanly omitted. | `scan_proves_safe = False`, zero private data leak |
| **INT-FAULT-06** | Storage & Mounts | Unmounted APFS volume / corrupted mount entry | `statvfs` failure caught; volume recorded with `is_available = False`; remaining volumes enumerated successfully. | `partial_data = True`, `scan_proves_safe = False` |
| **INT-FAULT-07** | USB Peripheral Bus | Zero external USB devices (root host controller only) | USB detector returns built-in controllers with 0 external peripherals; `has_external_devices = False`; inventory handles empty list. | `scan_proves_safe = False` |
| **INT-FAULT-08** | Multi-Fault Aggregation | Desktop + Air-gapped + Non-root ES + Denied FDA simultaneously | `MacOsInventoryApi.get_inventory()` completes in < 2.0s; aggregates all available sections; populates partial data; applies privacy filter; preserves all charter invariants. | `partial_data = True`, `scan_proves_safe = False`, `is_mutating = False` |

---

## 4. Verification and Packaging Strategy
1. **Integration Test Suite (`tests/test_macos_integration_missing_sensors_and_permissions.py`)**:
   - Comprehensive end-to-end integration tests simulating missing hardware, denied TCC permissions, unprivileged ES execution, and composite multi-fault states.
2. **Packaging Validator (`src/system_mind/packaging/macos_integration_faults.py`)**:
   - Programmatically audits integration test presence, AST zero-ambient-shell safety, and structural invariant enforcement.
3. **Developer CLI Tool (`tools/detect_integration_faults.py`)**:
   - Interactive command-line test runner executing fault-injected integration scenarios and printing diagnostic status reports.
4. **Rust Sensor Parity (`crates/system-mind-sensors/`)**:
   - Native Rust tests verifying degraded and missing sensor snapshots.
