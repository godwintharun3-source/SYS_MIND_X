# Design Note: Day 065 — Release the First Read-Only macOS System-Agent Milestone

## 1. Architectural Context & Objective
SYSTEM MIND X Milestone 4 (Days 041–065) has systematically constructed the complete read-only macOS platform agent and telemetry subsystem. Over 24 consecutive days and the priority corrective engineering review (`CORRECTIVE-REVIEW-062`), twenty distinct hardware, software, security, process, and service collectors were engineered alongside observation enrichment, privacy filtering, collector stability buffers, and least-privilege permission models.

Day 065 delivers the capstone release for Milestone 4:
1. Orchestrating all 20 collectors, observation confidence scoring, privacy filtering, collector health circuit breaking, event stability coalescing, and permission auditing into an authoritative, unprivileged companion agent runner (`src/system_mind/macos/companion_runner.py`).
2. Providing single-shot system snapshot (`run_snapshot()`) and continuous observational telemetry (`run_daemon()`) modes with bounded execution deadlines and adaptive backpressure.
3. Certifying the Milestone 4 architecture baseline freeze across all 25 days, verifying zero ambient shell authority (`SC-01`), user-managed application immunity (`SC-02`), and universal "Scan != Safe" enforcement (`SC-03`).
4. Releasing the developer CLI tool (`tools/run_macos_companion.py`) and formal release audit report (`docs/records/MACOS_COMPANION_AGENT_MILESTONE_4_REPORT.md`).

---

## 2. Seven Core Safety & Operational Invariants

To guarantee that the released companion agent operates strictly as an observational companion without causing host disruption or security bypasses, the following architectural invariants are enforced:

- **INV-COMP-01 (Strictly Read-Only User Space Execution):**
  The companion agent executes entirely within the unprivileged user session domain (`gui/$UID` or unprivileged terminal shell). It never invokes `sudo`, requests root privileges, or mutates operating system settings, kernel extensions, or system files.
- **INV-COMP-02 (Zero Ambient Shell Authority - SC-01):**
  All collector probes, system queries, and Swift bridge invocations execute via explicit tokenized argument vectors with `shell=False`. Unmediated shell execution (`os.system`, `subprocess(..., shell=True)`, `eval`) is strictly prohibited and validated via AST analysis.
- **INV-COMP-03 (Universal "Scan != Safe" Invariant - SC-03):**
  Every data contract, cycle telemetry record, and release report structurally enforces `scan_proves_safe = False`. Under no circumstances does extensive telemetry collection, valid codesigning, or clean security status imply behavioral software trustworthiness.
- **INV-COMP-04 (Deterministic Privacy Filtering & Secret Redaction - SC-04):**
  All collected inventory sections and telemetry envelopes pass through `MacPrivacyFilter` prior to serialization or emission. Usernames are pseudonymized, personal directories (`~/Documents`, `~/Desktop`, `~/.ssh`) are masked, and secrets/tokens are redacted.
- **INV-COMP-05 (Bounded Non-Blocking Execution Deadlines):**
  Collector health management bounds individual collector execution (<= 2.0s) and total aggregation deadlines (<= 5.0s) using detached thread pool worker management (`executor.shutdown(wait=False, cancel_futures=True)`). Hung sensor probes can never hang the companion agent.
- **INV-COMP-06 (Adaptive Backpressure & Queue Bounding):**
  During continuous observation mode, ring buffers enforce hard capacity limits (default 5,000 events) and dynamic backpressure throttling across `NOMINAL`, `ELEVATED`, `HIGH_PRESSURE`, and `SATURATED` tiers. Event bursts are coalesced to prevent memory growth.
- **INV-COMP-07 (Passive Non-Intrusive Permission Probing):**
  Permission and entitlement audits use passive probes (e.g. `os.access` checks) and never trigger intrusive user-facing TCC dialog prompt loops. Denied permissions degrade transparently into `unavailable_telemetry` with `partial_data = True`.

---

## 3. Component Architecture & Data Flow

```
+-----------------------------------------------------------------------------------------+
|                                    User Application                                     |
|                   (Tauri Desktop / REST API Client / Developer CLI)                    |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                  MacOsCompanionRunner (src/system_mind/macos/companion_runner.py)      |
+-----------------------------------------------------------------------------------------+
         |                                   |                                   |
         v                                   v                                   v
+--------------------+              +--------------------+              +--------------------+
| CollectorHealth    |              | MacOsInventoryApi  |              | MacPrivacyFilter   |
| - Timeout Envelopes|              | - 20 Collectors    |              | - Username Hashes  |
| - Circuit Breaker  |              | - System Sections  |              | - Path Masking     |
| - Aggregation Cap  |              | - Fallbacks        |              | - Secret Scrubbing |
+--------------------+              +--------------------+              +--------------------+
         |                                   |                                   |
         +-----------------------------------+-----------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|            MacOsObservationEngine & MacCollectorStabilityManager                        |
|  - Mach Boot Clocks / Nanosecond Timestamps / Clock Provenance                          |
|  - 5-Tier Confidence Scoring (KernelAuthoritative -> EstimatedMock)                     |
|  - Bounded Event Queues, Coalescing, and Backpressure Throttling                        |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                  CompanionCycleTelemetry / MacOsCompanionReleaseReport                  |
|  - All Invariants Verified                                                              |
|  - scan_proves_safe = False (Structural Charter Invariant)                              |
+-----------------------------------------------------------------------------------------+
```

---

## 4. Milestone 4 Component Inventory

The 25 components comprising Milestone 4 are cataloged below:
1. **Day 041:** Version, build, architecture and host identity detection (`src/system_mind/macos/detector.py`, `crates/system-mind-sensors/src/macos_identity.rs`).
2. **Day 042:** CPU model, core counts, and cache hierarchy (`cpu_detector.py`, `macos_cpu.rs`).
3. **Day 043:** Memory capacity, Mach VM statistics, and pressure levels (`memory_detector.py`, `macos_memory.rs`).
4. **Day 044:** Storage volumes, APFS containers, and filesystem metadata (`storage_detector.py`, `macos_storage.rs`).
5. **Day 045:** Battery presence, power source, and health telemetry (`battery_detector.py`, `macos_battery.rs`).
6. **Day 046:** Network interfaces, link states, and gateway routing (`network_detector.py`, `macos_network.rs`).
7. **Day 047:** GPU architecture, Metal feature support, and display inventory (`gpu_detector.py`, `macos_gpu.rs`).
8. **Day 048:** USB host controllers, peripheral descriptors, and hierarchy (`usb_detector.py`, `macos_usb.rs`).
9. **Day 049:** Process table inventory, resource usage, and role classification (`process_detector.py`, `macos_process.rs`).
10. **Day 050:** launchd services, execution domains, and login-item inventory (`services_detector.py`, `macos_launchd.rs`).
11. **Day 051:** Installed GUI applications, bundle IDs, and ownership categorization (`app_detector.py`, `macos_apps.rs`).
12. **Day 052:** Application signatures, Developer ID notarization, and CDHash (`signature_detector.py`, `macos_signature.rs`).
13. **Day 053:** CoreServices FSEvents filesystem change notifications (`fsevents_detector.py`, `macos_fsevents.rs`).
14. **Day 054:** Endpoint Security integration feasibility and entitlement boundaries (`endpoint_security_detector.py`, `macos_endpoint_security.rs`).
15. **Day 055:** Swift companion agent bridge and native Darwin telemetry (`swift_bridge.py`, `apps/macos-companion/`, `macos_swift_bridge.rs`).
16. **Day 056:** Least-privilege macOS user agent LaunchAgent service manager (`agent_service_detector.py`, `macos_user_agent.rs`).
17. **Day 057:** Telemetry collector health, non-blocking timeouts, and partial-data reporting (`collector_health_manager.py`, `macos_collector_health.rs`).
18. **Day 058:** Source timestamps, clock provenance, and multi-tier confidence scoring (`observation_engine.py`, `macos_observations.rs`).
19. **Day 059:** Telemetry privacy filtering, path masking, and metadata sanitization (`privacy_filter.py`, `macos_privacy.rs`).
20. **Day 060:** Read-only macOS inventory API and unified system aggregation (`inventory_api.py`, `macos_inventory.rs`).
21. **Day 061:** Consolidated unit tests for all twenty hardware and OS collectors (`tests/test_macos_collectors_unit.py`).
22. **Day 062:** Integration tests under missing sensors, air-gapped networks, and TCC denials (`tests/test_macos_integration_missing_sensors_and_permissions.py`).
23. **Day 063:** Telemetry collector stability under sustained event volume with bounded ring buffers (`collector_stability.py`, `macos_stability.rs`).
24. **Day 064:** macOS permission prompts, TCC prompt trigger rules, and required entitlements (`permission_inspector.py`, `macos_permissions.rs`).
25. **Day 065:** Release of the first read-only macOS system-agent milestone (`companion_runner.py`, `companion_models.py`, `tools/run_macos_companion.py`).

---

## 5. Verification & Acceptance Criteria
- Full test pass rate across unit, contract, integration, and safety suites.
- Programmatic packaging validation confirming all 25 milestone components exist, adhere to naming conventions, and enforce core invariants.
- Milestone release record certified in `docs/records/MACOS_COMPANION_AGENT_MILESTONE_4_REPORT.md`.
- Zero compiler warnings, zero secret leaks, zero lint violations.
