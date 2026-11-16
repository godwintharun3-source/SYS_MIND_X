# DAY 048 — Design Note: macOS USB and Peripheral Inventory Telemetry with Privacy Constraints

**Date:** 2026-11-16  
**Status:** Approved & Implemented  
**Subsystem:** `system_mind.macos` / `crates/system-mind-sensors`  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Author:** SYSTEM MIND X Architecture & Platform Engineering  

---

## 1. Executive Summary & Objective

Workstations interface with a wide range of external and built-in USB peripheral devices: human interface devices (keyboards, mice, trackpads), hardware security keys (FIDO2 / U2F YubiKeys, smartcards), audio/video adapters (webcams, microphones, DACs), external storage volumes (SSDs, USB thumb drives), and communication dongles (USB Ethernet, modems).

While peripheral awareness is vital for system context (e.g. detecting hardware security keys for MFA, knowing whether an external SSD is mounted, or verifying audio/video peripherals), peripheral introspection introduces major **security and privacy risks**:
1. **Device Serial Fingerprinting:** Hardware serial numbers of USB flash drives and security keys can serve as global user trackers across environments.
2. **Untrusted Storage Traversal:** Automated file indexing or directory walks across untrusted USB thumb drives can trigger malicious payload execution or violate user privacy.
3. **Keylogging and Input Interception:** Introspecting HID input streams or keyboard packets represents a severe surveillance vulnerability.

The Day 048 objective is to establish an unprivileged, read-only USB and peripheral inventory collector for the macOS companion agent governed by strict privacy invariants:
- Collect static USB bus topologies, device descriptors (Vendor ID, Product ID, manufacturer, speed, power requirements), and device classes without root elevation.
- Enforce hardware serial number anonymization (`INV-USB-02`) via salted SHA-256 digests (`sha256:<16-char-hex>`).
- Enforce strict exclusion of storage file contents (`INV-USB-03`): USB Mass Storage devices are inventoried at the descriptor level only; external storage filesystems are never opened or traversed.
- Enforce zero input interception (`INV-USB-04`): no HID event monitoring, packet sniffing, or keystroke observation.
- Guarantee strictly read-only non-mutating execution (`INV-USB-05`): zero port resets, power manipulation, or device ejection.
- Provide cross-language parity across Python dataclasses and native Rust sensor structs (`crates/system-mind-sensors`).

---

## 2. Invariants and Architectural Guarantees

- **`SC-01` / `INV-USB-01`: Unprivileged Execution & Zero Ambient Shell Authority**  
  All queries run strictly in user space without requiring `sudo` or administrator privileges. Subprocess calls execute strictly with tokenized argument vectors (`shell=False`) targeting unprivileged `/usr/sbin/system_profiler SPUSBDataType -json` with 10-second timeouts.
- **`INV-USB-02`: Peripheral Hardware Serial Privacy**  
  Raw peripheral serial numbers (`serial_num`) are strictly prohibited from plaintext storage or logging. All serials are hashed with a salted SHA-256 digest (`sha256:<16-char-hex>`).
- **`INV-USB-03`: No Storage Traversal or Content Indexing**  
  For USB Mass Storage devices, the engine captures device descriptors only. Personal files, folders, or document trees on external drives are strictly excluded from inspection.
- **`INV-USB-04`: Passive Descriptors Only (No HID Interception)**  
  For human interface devices, only static descriptors are read. The engine never opens `IOHIDManager`, `CGEventTap`, or user client streams to monitor keystrokes or mouse activity.
- **`INV-USB-05`: Strictly Read-Only Passive Introspection**  
  The engine never issues mutating commands such as USB port power toggles, device re-enumeration, firmware re-flashing, or drive ejections.
- **`INV-USB-06`: Graceful Non-Darwin Fallback**  
  On non-Darwin operating systems (Linux, Windows, CI containers), the engine gracefully falls back to `MockPlatformAdapter` or returns a structured report listing unsupported Darwin commands under `unavailable_telemetry`.
- **`INV-USB-07`: Safe Developer CLI Tooling**  
  `tools/detect_usb.py` provides unprivileged developers and CI pipelines with human-readable output, structured `--json`, safe `--mock`, and assertion flags (`--assert-usb`, `--assert-devices <MIN_COUNT>`).
- **`INV-USB-08`: Programmatic Packaging Validator**  
  `MacOsUsbValidator` in `src/system_mind/packaging/macos_usb.py` audits privacy anonymization, schemas, and CLI operations across development and CI runs.

---

## 3. Data Flow & Subsystem Architecture

```
+--------------------------------------------------------------------------------+
|                         SYSTEM MIND X AGENT & DESKTOP                          |
|             (Presentation Layer / Digital Twin / Reasoning Engine)             |
+--------------------------------------------------------------------------------+
                                       ^
                                       | Strongly Typed Telemetry Report
                                       | (MacUsbReport / MacOsUsbSnapshot)
+--------------------------------------------------------------------------------+
|                         MACOS USB & PERIPHERAL DETECTOR                        |
|             (Python: MacUsbDetector | Rust: MacOsUsbCollector)                 |
+--------------------------------------------------------------------------------+
             |                                                  |
             | Tokenized Subprocess                             | In-Memory Fallback
             v                                                  v
+-------------------------------+              +--------------------------------+
|  /usr/sbin/system_profiler    |              |      MockPlatformAdapter       |
|       SPUSBDataType -json     |              |  (Deterministic M-Series Mock) |
+-------------------------------+              +--------------------------------+
             |
             v
   Parsed SPUSBDataType JSON:
   - USB Controllers & Bus Trees (e.g. AppleT8103USBXHCI)
   - Recursive Hub Downstream Device Trees
   - Device Descriptors (Vendor, Product ID, Manufacturer, Speed, Power)
   - Categorical Classification (HID, Mass Storage, Security Key, Hub, Audio/Video)
   - Salted SHA-256 anonymization for device serial numbers
```

---

## 4. Telemetry Schema & Categorical Enums

### 4.1. Enums
- **`UsbDeviceClass`**:
  - `HUB`: USB Root Hub or external downstream hub.
  - `HUMAN_INTERFACE`: Keyboards, mice, trackpads, drawing tablets, gamepads.
  - `SECURITY_TOKEN`: Hardware security keys (YubiKey, Nitrokey, FIDO2/U2F tokens).
  - `MASS_STORAGE`: Flash drives, external SSDs, SD card readers.
  - `AUDIO_VIDEO`: Webcams, microphones, external audio interfaces, DACs.
  - `COMMUNICATIONS`: USB Ethernet adapters, cellular modems.
  - `WIRELESS`: Bluetooth dongles, proprietary RF receivers.
  - `PRINTER`: Connected printers and multifunction devices.
  - `OTHER`: Unclassified or composite multi-function peripherals.

- **`UsbSpeed`**:
  - `LOW_SPEED_1_5_MBPS`: 1.5 Mbps (USB 1.0/1.1)
  - `FULL_SPEED_12_MBPS`: 12 Mbps (USB 1.1/2.0)
  - `HIGH_SPEED_480_MBPS`: 480 Mbps (USB 2.0)
  - `SUPER_SPEED_5_GBPS`: 5 Gbps (USB 3.0 / USB 3.2 Gen 1)
  - `SUPER_SPEED_PLUS_10_GBPS`: 10 Gbps (USB 3.1 Gen 2 / USB 3.2 Gen 2)
  - `SUPER_SPEED_PLUS_20_GBPS`: 20 Gbps (USB 3.2 Gen 2x2)
  - `USB4_40_GBPS`: 40 Gbps (USB4 / Thunderbolt 4)
  - `UNKNOWN`: Unrecognized or virtual speed specification.

### 4.2. Core Data Models
- **`MacUsbDevice`**:
  - `name`: Human-readable device descriptor (e.g. `"Apple Internal Keyboard / Trackpad"`).
  - `vendor_id`: Vendor identifier string (e.g. `"0x05ac"`).
  - `product_id`: Product identifier string (e.g. `"0x027c"`).
  - `manufacturer`: Device manufacturer (e.g. `"Apple Inc."`, `"Yubico"`).
  - `anonymized_serial_hash`: Truncated SHA-256 digest (`sha256:<16-char-hex>`) satisfying `INV-USB-02`.
  - `device_class`: `UsbDeviceClass` enum value.
  - `speed`: `UsbSpeed` enum value.
  - `speed_text`: Raw speed text (e.g. `"up_to_480_mbit_s"`).
  - `location_id`: Hardware physical port location string (e.g. `"0x01100000 / 1"`).
  - `bus_power_ma`: Required operating current in milliamps (e.g. `500`).
  - `current_used_ma`: Operational current drawn in milliamps.
  - `extra_current_ma`: Additional operating current provided by host in milliamps.
  - `bcd_device`: Firmware device revision code (e.g. `"1.00"`).
  - `is_builtin`: True if device is internal to the Mac enclosure.
  - `is_hub`: True if device operates as a downstream USB hub.
  - `children`: List of downstream `MacUsbDevice` instances connected to this hub.

- **`MacUsbController`**:
  - `name`: Host controller / bus name (e.g. `"USB 3.1 Bus"`, `"AppleT8103USBXHCI"`).
  - `host_controller`: Controller driver name (e.g. `"AppleSynopsysUSB40XHCI"`).
  - `pci_device`: PCI device identifier string.
  - `pci_vendor`: PCI vendor identifier string.
  - `devices`: List of top-level `MacUsbDevice` instances connected to this controller.

- **`MacUsbReport`**:
  - `controllers`: List of `MacUsbController` instances.
  - `total_controller_count`: Total number of USB host controllers discovered.
  - `total_device_count`: Total count of all connected devices (flattened including nested hub devices).
  - `has_external_devices`: True if at least one non-builtin peripheral is connected.
  - `has_security_tokens`: True if at least one hardware security key / FIDO token is detected.
  - `has_mass_storage`: True if at least one USB Mass Storage device is connected.
  - `collected_at_epoch_secs`: Collection epoch timestamp.
  - `collection_method`: `"NATIVE_DARWIN_SYSTEM_PROFILER"` or `"MOCK_PLATFORM_ADAPTER"`.
  - `unavailable_telemetry`: List of unavailable metrics or unsupported OS features.
  - `warnings`: Diagnostic warnings encountered during parsing.

---

## 5. Security & Verification Strategy

1. **Deterministic Salted Hashing**: Test fixtures verify that serials like `"FE0123456789"` are consistently transformed into 23-character strings starting with `"sha256:"` and composed of valid hexadecimal characters.
2. **Subprocess Isolation**: Tokenized argument vectors ensure immunity from shell injection.
3. **Comprehensive Pytest Suite**: Validates mock generation, recursive hub traversal, device classification (HID, Mass Storage, Security Token, Hub, Audio/Video), and non-Darwin fallback.
4. **Rust Sensor Unit Tests**: Validates `crates/system-mind-sensors` collector and mock struct compilation.
5. **CI Runner Integration**: Verified through `tools/ci_runner.py all` and `tools/lint.py`.
