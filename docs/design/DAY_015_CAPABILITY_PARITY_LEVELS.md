# Design Note: Day 015 — Cross-Platform Capability Parity Levels

- **Date:** 2026-11-15
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Platform Matrix / Capability Parity Framework / ADR-025
- **Milestone:** Milestone 2: Requirements and Architecture Specification (Days 011–025)

---

## 1. Overview & Architectural Problem

Operating systems are fundamentally non-fungible. While classical cross-platform runtime layers (such as Java, Electron, or POSIX shims) attempt to flatten OS differences into lowest-common-denominator abstractions, an AI-native computer operation platform cannot afford such loss of fidelity. 

SYSTEM MIND X interacts directly with kernel facilities, hardware sensors, security controls, filesystem journals, and process supervisors. Forcing identical low-level behavior across macOS Darwin/XNU, Windows NT, and Linux is both technically impossible and architecturally dangerous:
- macOS uses APFS local snapshots, FSEvents, `com.apple.quarantine`, and System Integrity Protection (SIP).
- Windows uses Volume Shadow Copy (VSS), the NTFS USN Journal, `Zone.Identifier` Mark-of-the-Web (MOTW), and Windows Defender Application Control (WDAC).
- Linux uses eBPF tracepoints, fanotify/inotify, Landlock LSM, cgroups v2, and AppArmor/SELinux.

Attempting to treat these distinct subsystems as interchangeable causes fatal bugs, silent security bypasses, or hallucinated platform capabilities. To resolve this, Day 015 formalizes **Cross-Platform Capability Parity Levels**, establishing explicit parity ratings, native API mappings, documented degradation boundaries, and deterministic fallback strategies across all supported platform targets.

---

## 2. The Five Parity Levels

```
+-----------------------------------------------------------------------------------------+
|                              CAPABILITY PARITY HIERARCHY                                |
+-----------------------------------------------------------------------------------------+
| Level 1: FULL_PARITY                                                                    |
| - Fully native OS implementation. Zero functional degradation. Matches target SLA.     |
+-----------------------------------------------------------------------------------------+
| Level 2: EQUIVALENT_PARITY                                                              |
| - Functionally equivalent via platform-idiomatic alternative APIs. Negligible delta.    |
+-----------------------------------------------------------------------------------------+
| Level 3: DEGRADED_PARITY                                                                |
| - Partial functionality due to platform security, missing hardware, or API limitations. |
| - Documented degradation flags and active fallback strategy required.                   |
+-----------------------------------------------------------------------------------------+
| Level 4: EMULATED_SIMULATED                                                             |
| - Non-native execution (micro-VM, user-space polling, container shim, mock adapter).    |
+-----------------------------------------------------------------------------------------+
| Level 5: UNSUPPORTED                                                                    |
| - Primitive absent or prohibited by platform security policy. Hard-rejected fast.       |
+-----------------------------------------------------------------------------------------+
```

1. **`LEVEL_1_FULL_PARITY` (Full Native Parity)**: The platform provides first-class native kernel or OS APIs with comprehensive capability coverage meeting all quantitative NFRs (latency, reliability, throughput).
2. **`LEVEL_2_EQUIVALENT_PARITY` (Platform-Idiomatic Equivalent)**: The platform provides an alternative native mechanism that achieves the same high-level objective through platform-specific constructs (e.g. NTFS USN Journal + ETW instead of FSEvents).
3. **`LEVEL_3_DEGRADED_PARITY` (Documented Degraded Parity)**: The capability is available but bounded by platform design, missing entitlements, or hardware differences (e.g., Apple Silicon thermal sensor readings requiring private SMC keys on unprivileged processes). The system must expose explicit degradation flags.
4. **`LEVEL_4_EMULATED_SIMULATED` (Emulated / Simulated)**: The capability is not provided natively by the OS kernel, but is synthesized via user-space emulation, containerization, or virtualization (e.g., disposable Docker container on macOS when Landlock is unavailable).
5. **`LEVEL_5_UNSUPPORTED` (Explicitly Unsupported)**: The platform fundamentally lacks the capability, or policy forbids attempting to implement it (e.g., direct kernel memory mutation without SIP disablement). Must fail fast with `PlatformCapabilityUnsupportedError`; never spoofed.

---

## 3. Core Capability Domains and Cross-Platform Parity

SYSTEM MIND X evaluates capability parity across eight core operational domains:

### 3.1 Filesystem Event Streaming (`FS_OBSERVATION`)
- **macOS (Apple Silicon)**: `LEVEL_1_FULL_PARITY` via `FSEvents.framework` (`FSEventStreamCreate`). Granular event batching with sub-5ms notification latency.
- **Windows 11 x64**: `LEVEL_2_EQUIVALENT_PARITY` via NTFS USN Journal (`FSCTL_READ_USN_JOURNAL`) and `ReadDirectoryChangesW`. Persistent journal enables catch-up across reboots.
- **Ubuntu LTS x64**: `LEVEL_1_FULL_PARITY` via `fanotify` (filesystem-wide) and `inotify` (directory trees). Sub-millisecond kernel delivery.
- **NixOS VM**: `LEVEL_2_EQUIVALENT_PARITY` via `inotify` and immutable `/nix/store` generation tracking.

### 3.2 Process Telemetry & Tree Monitoring (`PROCESS_TELEMETRY`)
- **macOS (Apple Silicon)**: `LEVEL_2_EQUIVALENT_PARITY` via `libproc` (`proc_pidinfo`) and `sysctl`. Process tree inspection supported; foreign environment variable reads restricted without root.
- **Windows 11 x64**: `LEVEL_1_FULL_PARITY` via Event Tracing for Windows (`Microsoft-Windows-Kernel-Process` ETW provider) and `NtQuerySystemInformation`. Complete lifecycle tracking.
- **Ubuntu LTS x64**: `LEVEL_1_FULL_PARITY` via `/proc` filesystem and eBPF tracepoints (`sched_process_exec`, `sched_process_exit`). Zero polling overhead.
- **NixOS VM**: `LEVEL_2_EQUIVALENT_PARITY` via `/proc` and systemd cgroups v2 accounting.

### 3.3 Hardware Sensors & Thermal Monitoring (`HARDWARE_TELEMETRY`)
- **macOS (Apple Silicon)**: `LEVEL_3_DEGRADED_PARITY`. IOKit provides battery/power metrics; thermal sensors require private Apple Silicon SMC keys on unprivileged processes. Fallback to `sysctl machdep.cpu.thermal_level`.
- **Windows 11 x64**: `LEVEL_2_EQUIVALENT_PARITY` via WMI (`Win32_TemperatureProbe`, ACPI Thermal Zones). Dependent on OEM ACPI driver exposure.
- **Ubuntu LTS x64**: `LEVEL_1_FULL_PARITY` via `/sys/class/hwmon` and `/sys/class/thermal`. Direct standardized sensor access.
- **NixOS VM**: `LEVEL_3_DEGRADED_PARITY`. Virtualized guest sysfs; physical thermal readings not passed through virtual hypervisor.

### 3.4 File Provenance & Quarantine Metadata (`FILE_PROVENANCE`)
- **macOS (Apple Silicon)**: `LEVEL_1_FULL_PARITY` via `com.apple.quarantine` extended attribute, Gatekeeper assessment, and cryptographic SHA-256 validation.
- **Windows 11 x64**: `LEVEL_2_EQUIVALENT_PARITY` via Alternate Data Streams (`Zone.Identifier` MOTW) and SmartScreen reputation. ADS stripped on non-NTFS volumes.
- **Ubuntu LTS x64**: `LEVEL_3_DEGRADED_PARITY` via `user.xdg.origin.url` extended attribute. Populated by compliant browsers/downloaders, but not kernel-enforced.
- **NixOS VM**: `LEVEL_2_EQUIVALENT_PARITY` via cryptographic NAR hashes (`/nix/store` SHA-256) for packages and SHA-256 for user files.

### 3.5 Execution Containment & Micro-Isolation (`EXECUTION_CONTAINMENT`)
- **macOS (Apple Silicon)**: `LEVEL_2_EQUIVALENT_PARITY` via Virtualization.framework / Hypervisor.framework micro-VMs and disposable Docker containers (`sandbox-exec` is deprecated).
- **Windows 11 x64**: `LEVEL_2_EQUIVALENT_PARITY` via Windows Sandbox and AppContainer isolation (Hyper-V required; Windows Home falls back to AppContainer).
- **Ubuntu LTS x64**: `LEVEL_1_FULL_PARITY` via Linux Landlock LSM, seccomp-bpf, and unprivileged user namespaces. Unprivileged zero-overhead sandboxing.
- **NixOS VM**: `LEVEL_2_EQUIVALENT_PARITY` via `nix-shell --pure` and `systemd-nspawn` ephemeral containers.

### 3.6 System Snapshot & Atomic Rollback (`SYSTEM_SNAPSHOT_ROLLBACK`)
- **macOS (Apple Silicon)**: `LEVEL_1_FULL_PARITY` via APFS local snapshots (`tmutil snapshot`, `fs_snapshot_create`). Instantaneous copy-on-write state checkpointing.
- **Windows 11 x64**: `LEVEL_2_EQUIVALENT_PARITY` via Volume Shadow Copy Service (VSS) and Windows System Restore Points. Requires VSS service availability.
- **Ubuntu LTS x64**: `LEVEL_2_EQUIVALENT_PARITY` via Btrfs/ZFS snapshots or Timeshift/LVM thin pools. Fallback to package state journal on ext4.
- **NixOS VM**: `LEVEL_1_FULL_PARITY` via immutable Nix generations. Deterministic atomic generation switching with guaranteed bootloader rollback.

### 3.7 System Package Maintenance (`SYSTEM_PACKAGE_MAINTENANCE`)
- **macOS (Apple Silicon)**: `LEVEL_2_EQUIVALENT_PARITY` via `softwareupdate` CLI and sealed system volume verification. Reboots required for system bundle updates; user apps strictly excluded.
- **Windows 11 x64**: `LEVEL_2_EQUIVALENT_PARITY` via Windows Update Agent (WUA) / DISM. Requires staged reboot for cumulative OS updates; user apps strictly excluded.
- **Ubuntu LTS x64**: `LEVEL_1_FULL_PARITY` via `apt-get unattended-upgrades` and `needrestart`. In-place service restart without mandatory full reboot.
- **NixOS VM**: `LEVEL_1_FULL_PARITY` via `nixos-rebuild switch`. Declarative configuration activation with instant generational rollback.

### 3.8 Security Authority Enforcement (`SECURITY_AUTHORITY_ENFORCEMENT`)
- **macOS (Apple Silicon)**: `LEVEL_1_FULL_PARITY` via System Integrity Protection (SIP), Gatekeeper, and Transparency, Consent, and Control (TCC). Authoritative kernel enforcement.
- **Windows 11 x64**: `LEVEL_1_FULL_PARITY` via Windows Defender Application Control (WDAC), SmartScreen, and User Account Control (UAC).
- **Ubuntu LTS x64**: `LEVEL_1_FULL_PARITY` via AppArmor / SELinux, Landlock LSM, and Linux capabilities (`cap_set_proc`).
- **NixOS VM**: `LEVEL_1_FULL_PARITY` via Nix store immutability, Linux capabilities, and AppArmor profiles.

---

## 4. Cardinal Invariants of Capability Parity

1. **Non-Fungibility & Zero Spoofing:**
   $$\text{PlatformParity}(P, D) \ne \text{FULL\_PARITY} \implies \text{DegradationWarning}(P, D) \ne \emptyset$$
   A platform adapter must never report `FULL_PARITY` if native OS limitations require fallbacks or omit features.

2. **Mandatory Fallback Specification:**
   Every capability rated `EQUIVALENT_PARITY`, `DEGRADED_PARITY`, or `EMULATED_SIMULATED` must specify a concrete, non-empty `fallback_strategy`.

3. **Fast-Failure on Unsupported Capabilities:**
   Invoking an unsupported capability (`LEVEL_5_UNSUPPORTED`) must immediately raise `PlatformCapabilityUnsupportedError`, preventing silent no-ops.

4. **Security Non-Degradation:**
   Platform parity adapters must never bypass or lower native OS security protections (SIP, WDAC, AppArmor) to achieve synthetic parity.

---

## 5. Architectural Decision Record (ADR-025)

- **Title:** Cross-Platform Capability Parity Levels and Adapter Contracts
- **Status:** Accepted.
- **Context:** Treating heterogeneous OS platforms as uniform environments causes catastrophic failures when platform-specific security, filesystem, or process semantics differ.
- **Decision:** All system capabilities across macOS, Windows, and Linux are cataloged with explicit five-tier parity levels (`LEVEL_1_FULL_PARITY` through `LEVEL_5_UNSUPPORTED`). The `CapabilityParityEvaluator` enforces typed contracts, documented degradation warnings, and mandatory fallback definitions before broker execution.
- **Consequences:** Eliminates platform hallucination; enables fine-grained risk assessment tailored to native OS capabilities; preserves host stability across all targets.
