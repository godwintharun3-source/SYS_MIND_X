# DAY 047 — Design Note: macOS GPU and Display Inventory Telemetry

**Date:** 2026-11-16  
**Status:** Approved & Implemented  
**Subsystem:** `system_mind.macos` / `crates/system-mind-sensors`  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Author:** SYSTEM MIND X Architecture & Platform Engineering  

---

## 1. Executive Summary & Objective

Modern workstations rely heavily on graphics processing units (GPUs) and connected visual displays for computing workloads, machine learning acceleration (Metal Performance Shaders / Core ML), and multi-window operator visual interfaces. On macOS, graphics architecture spans integrated Apple Silicon unified memory GPUs (M1, M2, M3, M4 series with shared RAM and Metal 3/4 support), discrete mobile/desktop GPUs (AMD Radeon on Intel MacBooks, Mac Pro), and external graphics adapters (eGPUs over Thunderbolt 3).

The Day 047 objective is to establish an unprivileged, read-only GPU and display inventory collector for the macOS companion agent:
1. Discover all active graphics processors, hardware vendors, core counts, bus interfaces (`BUILTIN` vs `PCIE`), Metal feature family support, and VRAM / unified memory configuration.
2. Enumerate connected physical and virtual displays, native panel pixel grids, logical UI resolutions, refresh rates (Hz), primary display status, internal/external connection types, and Retina scaling.
3. Enforce strict privacy preservation: raw hardware display serial numbers must never be stored, logged, or serialized in plaintext; they are hashed into deterministic salted SHA-256 digests (`sha256:<16-char-hex>`).
4. Maintain zero ambient shell authority (`SC-01`) and read-only non-mutating execution (`INV-GPU-03`).
5. Provide cross-language parity across Python dataclasses and native Rust sensor structs (`crates/system-mind-sensors`).

---

## 2. Invariants and Architectural Guarantees

- **`SC-01` / `INV-GPU-01`: Unprivileged Execution & Zero Ambient Shell Authority**  
  All GPU and display queries execute strictly in user space without requiring `sudo` or root entitlements. Subprocess calls execute strictly with tokenized argument lists (`shell=False`) targeting `/usr/sbin/system_profiler SPDisplaysDataType -json` with bounded 10-second timeouts.
- **`INV-GPU-02`: Display Hardware Serial Privacy**  
  Display serial numbers (`_spdisplays_display-serial-number`) can act as persistent tracking beacons across distinct network environments. Raw display serials are strictly redacted and replaced with a salted SHA-256 digest (`sha256:prefix...`).
- **`INV-GPU-03`: Strictly Read-Only Passive Introspection**  
  The collector never invokes display mutation utilities (e.g. brightness adjustments, display resolution switching, gamma table alteration, mirror toggles, or sleep state controls).
- **`INV-GPU-04`: Graceful Non-Darwin Fallback**  
  On non-Darwin operating systems (Linux, Windows, CI cloud containers without macOS display servers), the engine gracefully falls back to `MockPlatformAdapter` or returns a structured report listing unsupported Darwin commands under `unavailable_telemetry`.
- **`INV-GPU-05`: Cross-Language Type Parity**  
  Strongly typed telemetry models in Python (`src/system_mind/macos/gpu_models.py`) and Rust (`crates/system-mind-sensors/src/macos_gpu.rs`) mirror identical semantics, enum variants, and JSON serializations.
- **`INV-GPU-06`: Safe Developer CLI Tooling**  
  A dedicated CLI tool (`tools/detect_gpu.py`) enables unprivileged developers and CI pipelines to inspect live or mock GPU and display configurations, output structured JSON, or assert display thresholds (`--assert-gpu`, `--assert-displays <MIN_COUNT>`).
- **`INV-GPU-07`: Programmatic Packaging Validator**  
  `MacOsGpuValidator` in `src/system_mind/packaging/macos_gpu.py` audits code safety, field schemas, privacy anonymization, and CLI execution across development and CI runs.

---

## 3. Data Flow & Subsystem Architecture

```
+--------------------------------------------------------------------------------+
|                         SYSTEM MIND X AGENT & DESKTOP                          |
|             (Presentation Layer / Digital Twin / Reasoning Engine)             |
+--------------------------------------------------------------------------------+
                                       ^
                                       | Strongly Typed Telemetry Report
                                       | (MacGpuReport / MacOsGpuSnapshot)
+--------------------------------------------------------------------------------+
|                        MACOS GPU & DISPLAY DETECTOR                            |
|             (Python: MacGpuDetector | Rust: MacOsGpuCollector)                |
+--------------------------------------------------------------------------------+
             |                                                  |
             | Tokenized Subprocess                             | In-Memory Fallback
             v                                                  v
+-------------------------------+              +--------------------------------+
|  /usr/sbin/system_profiler    |              |      MockPlatformAdapter       |
|    SPDisplaysDataType -json   |              |  (Deterministic M-Series Mock) |
+-------------------------------+              +--------------------------------+
             |
             v
   Parsed SPDisplaysDataType JSON:
   - GPU model, vendor, bus, cores, Metal version
   - Display name, IDs, native pixels, refresh rate
   - Salted SHA-256 anonymization for display serials
```

---

## 4. Telemetry Schema & Categorical Enums

### 4.1. Enums
- **`GpuBusType`**:
  - `BUILTIN`: Built-in / integrated GPU (Apple Silicon SoC graphics, Intel Iris/UHD).
  - `PCIE`: PCI-Express discrete graphics (AMD Radeon Pro, NVIDIA GeForce, eGPU).
  - `UNKNOWN`: Unrecognized or virtual graphics adapter.
- **`DisplayConnectionType`**:
  - `INTERNAL`: Built-in laptop display / Retina panel (`spdisplays_internal`).
  - `DISPLAYPORT`: DisplayPort or USB-C DisplayPort Alternate Mode (`spdisplays_displayport`).
  - `HDMI`: High-Definition Multimedia Interface (`spdisplays_hdmi`).
  - `THUNDERBOLT`: Direct Thunderbolt display link (`spdisplays_thunderbolt`).
  - `AIRPLAY`: Virtual AirPlay or Sidecar display.
  - `UNKNOWN`: Unclassified external or synthetic display connection.

### 4.2. Core Data Models
- **`MacDisplayInfo`**: Represents a single physical or virtual display monitor.
  - `name`: Display model name (e.g. `"Color LCD"`, `"Studio Display"`, `"LG UltraFine"`).
  - `display_id`: Darwin display identifier string (e.g. `"1"`).
  - `vendor_id`: Display manufacturer hexadecimal ID (e.g. `"610"` for Apple).
  - `product_id`: Product model hexadecimal ID (e.g. `"a045"`).
  - `anonymized_serial_hash`: Truncated SHA-256 digest (`sha256:<16-char-hex>`) satisfying `INV-GPU-02`.
  - `native_pixels`: Native physical panel resolution (e.g. `"2880 x 1800"`).
  - `resolution`: Current desktop resolution and refresh rate (e.g. `"1440 x 900 @ 60.00Hz"`).
  - `ui_resolution`: Scaled user interface resolution (e.g. `"1440 x 900"`).
  - `refresh_rate_hz`: Numerical refresh rate in Hertz (e.g. `60.0` or `120.0` ProMotion).
  - `is_main`: Boolean indicating if this is the primary macOS menu-bar display.
  - `is_builtin`: Boolean indicating internal laptop display.
  - `is_online`: Boolean indicating active display connection.
  - `is_mirror`: Boolean indicating display mirroring mode.
  - `connection_type`: `DisplayConnectionType` enum value.
  - `pixel_density_retina`: Boolean indicating high-DPI Retina scaling.
  - `ambient_brightness`: Boolean indicating True Tone / ambient light sensor presence.

- **`MacGpuInfo`**: Represents a graphics processing unit.
  - `name`: Chipset / GPU model name (e.g. `"Apple M1"`, `"Apple M3 Max"`).
  - `vendor`: Hardware vendor name (e.g. `"Apple"`, `"AMD"`, `"Intel"`).
  - `core_count`: Number of GPU shader cores / execution units.
  - `bus_type`: `GpuBusType` enum value.
  - `metal_support`: Metal feature set family (e.g. `"spdisplays_metal4"`).
  - `device_type`: Device classification (e.g. `"spdisplays_gpu"`).
  - `vram_bytes`: Available VRAM in bytes (if discrete) or `None` if unified.
  - `vram_text`: Human-readable VRAM description (e.g. `"Unified Memory"`).
  - `displays`: List of `MacDisplayInfo` instances driven by this GPU.

- **`MacGpuReport`**: Authoritative aggregated report.
  - `gpus`: List of `MacGpuInfo` instances.
  - `total_gpu_count`: Total number of GPUs discovered.
  - `total_display_count`: Total number of active displays connected.
  - `primary_display_resolution`: Resolution of the main display.
  - `has_builtin_display`: True if an internal laptop display is present.
  - `has_external_display`: True if at least one external monitor is connected.
  - `collected_at_epoch_secs`: Collection timestamp.
  - `collection_method`: `"NATIVE_DARWIN_SYSTEM_PROFILER"` or `"MOCK_PLATFORM_ADAPTER"`.
  - `unavailable_telemetry`: List of unavailable metrics or unsupported OS features.
  - `warnings`: Diagnostic warnings encountered during parsing.

---

## 5. Security & Verification Strategy

1. **Static Analysis & Secret Redaction**: All test fixtures and sample outputs use sanitized dummy IDs and anonymized hashes.
2. **Subprocess Sandboxing**: Tokenized parameter passing with `shell=False` ensures immunity against command injection.
3. **Comprehensive Pytest Suite**: Validates mock generation, JSON parsing, Apple Silicon / Intel dual-GPU fixtures, serial anonymization, and non-Darwin fallback.
4. **Rust Sensor Unit Tests**: Validates `crates/system-mind-sensors` collector and mock struct compilation.
5. **CI Runner Integration**: Verified through `tools/ci_runner.py all` and `tools/lint.py`.
