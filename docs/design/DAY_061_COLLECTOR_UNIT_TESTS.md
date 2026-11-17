# Design Note: DAY-061 — Comprehensive Unit Testing and Fault-Tolerant Mock Verification for macOS Telemetry Collectors

## 1. Context and Problem Statement
Milestone 4 (Days 041–065) has systematically constructed twenty distinct telemetry, inspection, security, and aggregation collectors in `src/system_mind/macos/` and corresponding native Rust sensors in `crates/system-mind-sensors/src/`:
1. `detector.py`: macOS host identity, Darwin kernel build, Apple Silicon processor architecture, and marketing version.
2. `cpu_detector.py`: CPU brand, hardware model, symmetric/asymmetric core topology (P/E cores), cache hierarchy, and frequency.
3. `memory_detector.py`: Physical memory, Mach VM page statistics, swap metrics, and memory pressure levels.
4. `storage_detector.py`: Mounted storage volumes, statvfs metrics, APFS container roles, and filesystem flags.
5. `battery_detector.py`: Battery hardware info, pmset charging states, cycle counts, health condition, and desktop AC power fallback.
6. `network_detector.py`: Interface classification (Wi-Fi, Ethernet, loopback, cellular), IP addresses, routing table, and DNS resolvers.
7. `gpu_detector.py`: GPU accelerators, Metal support tiers, display resolution, and refresh rates.
8. `usb_detector.py`: USB controllers, recursive hub tree flattening, current draw (mA), and device classes.
9. `process_detector.py`: Process table entries, PID/PPID hierarchy, CPU/memory usage, process states, and role classification.
10. `services_detector.py`: Launchd user agents, system daemons, login items, and exit code interpretation.
11. `app_detector.py`: Installed applications, Info.plist metadata, bundle identifiers, and ownership tiers.
12. `signature_detector.py`: Code signatures, signing authority chain, CDHash, Gatekeeper spctl assessments, and notarization status.
13. `fsevents_detector.py`: Apple CoreServices FSEvents filesystem change monitoring, 32-bit bitmask decoding, and root containment.
14. `endpoint_security_detector.py`: Endpoint Security framework feasibility analysis, entitlement audits, and non-privileged fallbacks.
15. `swift_bridge.py`: Native Swift companion bridge telemetry, ProcessInfo thermal states, and frontmost application tracking.
16. `agent_service_detector.py`: Least-privilege LaunchAgent service management in `gui/$UID` user session.
17. `collector_health_manager.py`: Collector timeout isolation envelopes, circuit breaker trip thresholds, and partial-data categorization.
18. `observation_engine.py`: Clock source provenance (`mach_continuous_time`), confidence scoring, and cryptographic payload digests.
19. `privacy_filter.py`: Username pseudonymization (`user_XXXXXX`), personal path masking, key vault protection, and secret scrubbing.
20. `inventory_api.py`: Read-only unified aggregation across all eight core subsystems with RFC 7807 problem details.

While individual test files were authored during each collector's introduction, Day 061 requires a rigorous, consolidated unit test matrix verifying:
- Internal parser resilience against malformed, truncated, or unexpected CLI/sysctl output.
- Bounded fallback behavior when hardware sensors or Darwin utilities are missing or return errors.
- Structural enforcement of the non-negotiable charter invariant: **"Scan != Safe"** (`scan_proves_safe = False`) across all models and reports.
- Zero ambient shell authority (`shell=False` strictly enforced across all subprocess invocations, timeouts <= 5s).
- Deterministic mock adapter execution enabling 100% offline, cross-platform CI verification without touching developer host settings.

---

## 2. Architectural Principles & Safety Invariants

### 2.1 Principle of Fault-Tolerant Parsing (`INV-TEST-01`)
Collectors must never raise uncaught exceptions on unexpected native OS output.
- Corrupted sysctl strings, truncated `vm_stat` outputs, missing plist keys, or malformed `ps` lines must be gracefully handled with structured fallbacks.
- When native queries fail, the failure must be captured in `unavailable_telemetry` or `warnings` without crashing the collector.

### 2.2 Strict Invariant Enforcement: "Scan != Safe" (`INV-TEST-02`)
In accordance with the SYSTEM MIND X Product Charter and ADR-008:
- No telemetry collector, signature assessment, or inventory report can ever assert that a system or application is "safe".
- Every model and response object must structurally enforce `scan_proves_safe = False`.

### 2.3 Zero Ambient Shell Authority (`SC-01` / `INV-TEST-03`)
All telemetry collection subprocesses must dispatch via tokenized argument vectors with `shell=False`.
- Subprocess invocations must be bounded by explicit timeouts (<= 5s) to prevent orchestrator deadlocks.
- AST analysis must verify that no collector imports or uses `shell=True`, `os.system`, `subprocess.Popen(..., shell=True)`, or ambient shell libraries (`sh`, `plumbum`, `pexpect`).

### 2.4 Least-Privilege & Read-Only Confinement (`SC-02` / `INV-TEST-04`)
All telemetry collectors must operate purely within unprivileged user space.
- No collector may execute `sudo`, request administrator privileges, or modify host filesystem or launchd configuration.
- Mutating operations must be structurally rejected.

---

## 3. Collector Unit Test Specification Matrix

| Collector Subsystem | Target Module | Unit Test Scope & Injected Faults | Safety Contract |
|---|---|---|---|
| **Identity** | `detector.py` | Marketing name resolution across macOS 10.14 through 27 Preview; `sw_vers` vs plist fallback; Rosetta 2 translation detection; non-Darwin fallback. | `scan_proves_safe = False`, `shell=False` |
| **CPU** | `cpu_detector.py` | `_get_sysctl_str` and `_get_sysctl_int` fault injection (non-zero RC, garbage text); P/E core asymmetric topology parsing; symmetric simulation; cache size calculation. | `scan_proves_safe = False`, `shell=False` |
| **Memory** | `memory_detector.py` | Mach VM page stats parsing (`vm_stat`), truncated buffer handling; swap usage parsing; pressure level thresholds (`NORMAL`, `WARN`, `CRITICAL`). | `scan_proves_safe = False`, `shell=False` |
| **Storage** | `storage_detector.py` | `mount` command output parsing; APFS container role detection; `statvfs` calculation (total, free, used %); sealed system volume flag decoding. | `scan_proves_safe = False`, `shell=False` |
| **Battery** | `battery_detector.py` | `pmset -g batt` parser across charging, discharging, AC attached states; desktop Mac AC power detection (no battery); serial pseudonymization. | `scan_proves_safe = False`, `shell=False` |
| **Network** | `network_detector.py` | Interface classification (Wi-Fi, Ethernet, loopback, cellular); `ifconfig` IP parsing; `netstat` route parsing; DNS resolver extraction; MAC address masking. | `scan_proves_safe = False`, `shell=False` |
| **GPU** | `gpu_detector.py` | `SPDisplaysDataType` parser; Metal 3/2/unsupported detection; display resolution and ProMotion refresh rate parsing; multi-GPU aggregation. | `scan_proves_safe = False`, `shell=False` |
| **USB** | `usb_detector.py` | `SPUSBDataType` recursive tree flattening; power draw (mA) calculation; serial number anonymization; root hub vs peripheral classification. | `scan_proves_safe = False`, `shell=False` |
| **Processes** | `process_detector.py` | `ps` line parser; PID/PPID mapping; process state character decoding (`R`, `S`, `U`, `Z`, `T`); role classification (`SYSTEM_CORE`, `BACKGROUND_DAEMON`, `USER_APP`). | `scan_proves_safe = False`, `shell=False` |
| **Services** | `services_detector.py` | `launchctl list` parser; domain separation (`gui/$UID` User Agent vs `/Library/LaunchDaemons` System Daemon); login items scanning; exit codes. | `scan_proves_safe = False`, `shell=False` |
| **Applications** | `app_detector.py` | `Info.plist` metadata extraction; bundle ID validation; category heuristic classification; ownership categorization (`SYSTEM_MANAGED`, `USER_MANAGED`). | `scan_proves_safe = False`, `shell=False` |
| **Signatures** | `signature_detector.py` | `codesign` parser (TeamID, Authority, CDHash); `spctl` assessment parsing; ad-hoc vs signed vs notarized; invariant that signed != safe. | `scan_proves_safe = False`, `shell=False` |
| **FSEvents** | `fsevents_detector.py` | 32-bit CoreServices bitmask decoding (`ITEM_CREATED`, `ITEM_MODIFIED`, `ITEM_REMOVED`); monitored root containment; strict privacy exclusions (`~/.ssh`, `~/Documents`). | `scan_proves_safe = False`, `shell=False` |
| **Endpoint Security**| `endpoint_security_detector.py`| Feasibility assessment; unprivileged companion fallback (`ES_NEW_CLIENT_RESULT_ERR_NOT_PRIVILEGED`); SIP status check; transparent telemetry fallbacks. | `scan_proves_safe = False`, `shell=False` |
| **Swift Bridge** | `swift_bridge.py` | JSON wire protocol encoding/decoding; ProcessInfo thermal state classification (`nominal`, `fair`, `serious`, `critical`); frontmost application tracking. | `scan_proves_safe = False`, `shell=False` |
| **User Agent** | `agent_service_detector.py` | LaunchAgent plist generation; session type enforcement (`LimitLoadToSessionType = ["Aqua"]`); domain verification (`gui/$UID`); status inspection. | `scan_proves_safe = False`, `shell=False` |
| **Collector Health** | `collector_health_manager.py` | Per-collector timeout isolation envelopes; circuit breaker tripping after consecutive errors; partial-data root cause categorization. | `scan_proves_safe = False`, `shell=False` |
| **Observations** | `observation_engine.py` | Clock source provenance; multi-tier confidence scoring in `[0.0, 1.0]`; explicit penalty deductions; canonical SHA-256 payload digests. | `scan_proves_safe = False`, `shell=False` |
| **Privacy Filter** | `privacy_filter.py` | Deterministic username pseudonymization (`user_XXXXXX`); personal path masking; key vault protection; secret and high-entropy token scrubbing. | `scan_proves_safe = False`, `shell=False` |
| **Inventory API** | `inventory_api.py` | Read-only query semantics (mutating requests rejected with `E2001`); 8-section aggregation; executive summary calculation; RFC 7807 error format. | `scan_proves_safe = False`, `shell=False` |

---

## 4. Verification & Validation Strategy
1. **Unit Test Suite (`tests/test_macos_collectors_unit.py`)**:
   - Minimum 32 high-precision unit tests targeting every hardware and OS collector.
   - Comprehensive AST inspection validating zero `shell=True` and structural presence of `scan_proves_safe = False`.
2. **Packaging Validator (`src/system_mind/packaging/macos_collector_tests.py`)**:
   - `MacOsCollectorTestsValidator` programmatically auditing collector modules, AST safety, unit test presence, and Rust sensor parity.
3. **Rust Sensor Unit Tests (`crates/system-mind-sensors/`)**:
   - Expanded unit tests verifying boundary states, empty payloads, and serialization across native Rust collectors.
4. **Developer Tooling (`tools/detect_collector_tests.py`)**:
   - CLI tool outputting tabular audit of all collectors, test counts, safety guarantees, and mock capabilities.
