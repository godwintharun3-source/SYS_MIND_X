# DAY 045: macOS Battery State, Power Source and Health Information Architecture

**Author:** SYSTEM MIND X Engineering Agent  
**Date:** 2026-11-16  
**Status:** In-Progress (Day 045)  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Document ID:** `docs/design/DAY_045_MACOS_BATTERY_STATE_AND_HEALTH.md`

---

## 1. Executive Summary

Milestone 4 constructs a read-only macOS system companion agent that operates with **Zero Ambient Shell Authority** (`SC-01`) and without requiring privileged root or administrator elevation. Following the completion of identity (Day 041), CPU topology (Day 042), memory allocation/pressure (Day 043), and storage volumes/APFS container metadata (Day 044), Day 045 implements comprehensive, passive introspection of **battery state, AC power supply status, charging dynamics, cycle counts, and battery health telemetry**.

Battery and power availability is a safety-critical precondition for consequential operations. System updates, snapshot consolidation, and extensive background indexing must never be initiated when the device is operating under battery power with depleted reserves or without connected AC power (`INV-UPD-06`, `INV-BAT-01`). Furthermore, monitoring cycle counts and condition degradation provides proactive hardware health governance.

---

## 2. Invariants & Safety Constraints

- **`INV-BAT-01` (Unprivileged User-Space Read-Only Introspection):** All battery state and power source metrics are retrieved strictly through non-privileged Darwin tools (`/usr/bin/pmset -g batt` and `/usr/sbin/system_profiler SPPowerDataType -json`). Mutating power assertions (`pmset schedule`, `pmset sleepnow`, modifying sleep timers or hibernatemode) are strictly prohibited.
- **`INV-BAT-02` (Hardware Identifier Privacy & Anonymization):** The battery pack serial number (`sppower_battery_serial_number`) is an immutable hardware identifier. In adherence to `INV-MAC-02`, raw battery serial numbers are never emitted in plaintext logs, reports, or telemetry; they are anonymized into deterministic SHA-256 digests (`sha256:prefix...`).
- **`INV-BAT-03` (Zero Ambient Shell Authority):** All external utility invocations dispatch with explicit argument vectors using `subprocess.run(..., shell=False)` with a strict 5.0-second timeout.
- **`INV-BAT-04` (Desktop & Non-Battery Mac Graceful Handling):** On macOS desktop models (Mac mini, Mac Studio, Mac Pro, iMac) lacking internal batteries, the detector accurately reports `is_battery_present: False`, `current_power_source: PowerSource.AC_POWER`, and `health: None` without crashing or returning error status.
- **`INV-BAT-05` (Cross-Platform Graceful Degradation):** On non-Darwin platforms (Linux/Windows/CI environments), execution safely delegates to `MockPlatformAdapter` or returns structured fallback reports populating `unavailable_telemetry`.

---

## 3. Data Model Hierarchy

```
+-------------------------------------------------------------------+
|                     MacBatteryTelemetryReport                    |
+-------------------------------------------------------------------+
| is_battery_present: bool                                          |
| current_power_source: PowerSource (BATTERY_POWER, AC_POWER, UPS)  |
| state_of_charge_percent: Optional[int] (0..100)                  |
| charging_state: BatteryChargingState (CHARGING, DISCHARGING, etc.) |
| is_charging: bool                                                 |
| is_fully_charged: bool                                            |
| is_ac_connected: bool                                             |
| time_remaining_minutes: Optional[int]                             |
| is_below_warning_level: bool                                      |
| is_low_power_mode_active: bool                                    |
| health: Optional[MacBatteryHealthInfo]                            |
| collected_at_epoch_secs: float                                    |
| collection_method: str                                            |
| unavailable_telemetry: List[str]                                  |
| warnings: List[str]                                               |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                      MacBatteryHealthInfo                         |
+-------------------------------------------------------------------+
| cycle_count: Optional[int]                                        |
| condition: BatteryHealthCondition (NORMAL, REPLACE_SOON, etc.)     |
| maximum_capacity_percent: Optional[int] (e.g. 91%)                |
| device_name: Optional[str]                                        |
| manufacturer: Optional[str]                                       |
| anonymized_serial_hash: Optional[str] (sha256:...)                 |
| firmware_version: Optional[str]                                   |
+-------------------------------------------------------------------+
```

---

## 4. Collection Interfaces & Logic

1. **`pmset -g batt` Parser:**
   - Real-time power source: `'Battery Power'` vs `'AC Power'`.
   - Charging dynamics: `discharging`, `charging`, `charged`, `finishing charge`, `not charging`.
   - Remaining runtime estimation: formatted as `HH:MM remaining`, converted to total minutes.
2. **`system_profiler SPPowerDataType -json` Parser:**
   - Structured JSON output containing `sppower_battery_health_info`, `sppower_battery_charge_info`, `sppower_battery_model_info`, and `sppower_ac_charger_information`.
   - Anonymizes battery pack serial numbers using SHA-256 salt.
   - Extracts cycle count, condition string, and Apple Silicon maximum capacity percentage.
3. **Precondition Space & Power Assertion CLI:**
   - `tools/detect_battery.py` provides developer inspection and programmatic gate checks:
     - `--assert-min-battery-pct <PCT>`: Asserts minimum battery percentage before power-intensive operations.
     - `--assert-ac-power`: Asserts active AC power connection.

---

## 5. Verification Matrix

| Test Domain | Target Invariant | Methodology |
|:---|:---|:---|
| Live Darwin Detection | `INV-BAT-01`, `INV-BAT-04` | Executed against host Apple Silicon Darwin kernel. |
| Battery Serial Anonymization | `INV-BAT-02` | Verifies raw serial strings never exist in report. |
| Subprocess Tokenization | `INV-BAT-03` | Verifies `shell=False` across all command dispatches. |
| Desktop / No-Battery Mode | `INV-BAT-04` | Simulates desktop hardware without internal battery. |
| Mock Fallback | `INV-BAT-05` | Verified using `MockPlatformAdapter` and constrained battery mock. |
| Rust Parity | Cross-language | Rust collector tests in `crates/system-mind-sensors`. |
| CLI Gate Verification | Operator tooling | Command-line execution with `--mock`, `--json`, and assertion flags. |
