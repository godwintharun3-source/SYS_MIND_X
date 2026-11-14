# Design Note: Day 004 — Supported First-Release Platform & Hardware Matrix

- **Date:** 2026-11-14
- **Author:** Principal Software Architect
- **Status:** Draft / Awaiting Review
- **Component:** Architecture / Platform Abstraction / Hardware Matrix

---

## 1. Overview & Policy Standard

A core failure mode of cross-platform agent systems is assuming that operating system APIs are fungible. Native kernels, security architectures, entitlement models, and hardware capabilities diverge profoundly between macOS, Windows, and Linux.

Per SYSTEM MIND X Architecture Rules:
- **No speculative claims:** A platform capability is never claimed as supported until implemented and verified against real APIs or explicit mock adapters.
- **Explicit capability tiering:** Every engine capability must be formally labelled `SUPPORTED`, `PARTIAL`, `MOCK_ONLY`, or `UNSUPPORTED`.
- **Authoritative native controls:** Operating system kernels (XNU, Windows NT, Linux) and native security frameworks (Endpoint Security, WDAC, Landlock) remain authoritative.

---

## 2. The First-Release Supported Matrix

SYSTEM MIND X bounds its v1.0 target release strictly to four targets:

```
+-----------------------------------------------------------------------------------------+
|                               FIRST-RELEASE SUPPORT MATRIX                              |
+-----------------------------------------------------------------------------------------+
| Target ID                | Platform Tier   | Architecture | Primary Role                |
+--------------------------+-----------------+--------------+-----------------------------+
| MACOS_APPLE_SILICON      | Tier 1 (Host)   | arm64 (M1+)  | Dev Host & Companion Target |
| WINDOWS_11_X64           | Tier 2 (Agent)  | x86_64       | Companion Agent             |
| UBUNTU_LTS_X64           | Tier 2 (Agent)  | x86_64       | Linux Companion Agent       |
| NIXOS_VM                 | Tier 3 (OS VM)  | x86_64/arm64 | SYSTEM MIND OS Alpha VM     |
+--------------------------+-----------------+--------------+-----------------------------+
```

### 2.1 Target 1: macOS on Apple Silicon (M1/M2/M3)
- **Kernel & OS:** Darwin 23.0+ / macOS 14.0+ (Sonoma/Sequoia), Apple Silicon (M1/M2/M3/M4, T8103+).
- **Minimum Hardware Spec:** Apple Silicon arm64, 8 cores, 8 GB unified memory, APFS formatted storage.
- **Native Security Primitives:**
  - *System Integrity Protection (SIP):* Mandatory enabled; protects `/System`, `/usr`, `/bin`, `/sbin`.
  - *Gatekeeper & Notarization:* Active assessment of quarantine flags (`com.apple.quarantine`).
  - *Endpoint Security (`EndpointSecurity.framework`):* Process execution, fork, and mount monitoring. Requires developer entitlement `com.apple.developer.endpoint-security.client`.
  - *File Monitoring:* `FSEvents` API for user space file change streaming.
  - *State Snapshots:* APFS local snapshots (`tmutil localsnapshot`) for atomic recovery points.
- **Constraints & Fallbacks:**
  - If Endpoint Security entitlement is ungranted, fallback to read-only `libproc` polling and `FSEvents` with documented `PARTIAL` capability status.
  - Direct firmware manipulation (Apple Silicon Boot ROM / SEP) is strictly forbidden.

### 2.2 Target 2: Windows 11 x64
- **Kernel & OS:** Windows NT 10.0.22621+ (Windows 11 22H2+), x86_64 architecture.
- **Minimum Hardware Spec:** 64-bit 4+ cores, 8 GB RAM, TPM 2.0 active, UEFI Secure Boot, VBS enabled.
- **Native Security Primitives:**
  - *Telemetry:* Event Tracing for Windows (ETW) with Microsoft-Windows-Kernel-Process / File providers.
  - *Application Control:* Windows Defender Application Control (WDAC) and AppLocker.
  - *Recovery Points:* Volume Shadow Copy Service (VSS) for volume restore snapshots.
- **Constraints & Fallbacks:**
  - Unprivileged agent runs in user token session; elevated broker requests require UAC prompt or registered Windows Service broker.
  - Fallback to Win32 Performance Counters (`PdhAddCounter`) if kernel ETW tracing is restricted.

### 2.3 Target 3: Ubuntu LTS x86_64
- **Kernel & OS:** Linux kernel 6.8+ LTS, Ubuntu 24.04 LTS, systemd v255+, glibc 2.39+.
- **Minimum Hardware Spec:** x86_64 4+ cores, 8 GB RAM, systemd init.
- **Native Security Primitives:**
  - *Telemetry & Hooks:* eBPF tracepoints (`sys_enter_execve`, `sched_process_exit`) via `libbpf`.
  - *Filesystem Events:* `fanotify` with `FAN_ACCESS_PERM` / `inotify`.
  - *Process Sandboxing:* Linux Landlock LSM (ABI v3+) and `seccomp-bpf` system call filtering.
  - *Service & Cgroups:* `systemd` user units with cgroups v2 resource ceilings (`CPUQuota`, `MemoryMax`).
- **Constraints & Fallbacks:**
  - If eBPF requires `CAP_BPF` or `CAP_SYS_ADMIN` which is unavailable, fallback to `/proc` polling and `inotify` (`PARTIAL`).

### 2.4 Target 4: NixOS x86_64 & ARM64 (Virtual Machine OS Prototype)
- **Kernel & Architecture:** NixOS Linux 24.05+ / unstable, running inside QEMU / UTM / libvirt isolated hypervisors.
- **Minimum Hardware Spec:** 2+ vCPUs, 4 GB virtual RAM, 20 GB virtual disk.
- **Core Architecture Advantage:**
  - *Declarative Configuration:* Entire system state defined in reproducible `/etc/nixos/configuration.nix`.
  - *Atomic Generation Switching:* Every system update produces a new generation (`/nix/var/nix/profiles/system`).
  - *Instant Zero-Risk Rollback:* Bootloader allows instant reboot into any past known-good generation if an update introduces regression.
  - *Cryptographic Store Closure:* Packages in `/nix/store/<hash>-<name>` are immutable and hash-addressed.

---

## 3. Capability Support Matrix Across Core Engines

| Engine / Capability | macOS Apple Silicon | Windows 11 x64 | Ubuntu LTS x64 | NixOS VM Alpha |
| :--- | :--- | :--- | :--- | :--- |
| **1. Digital Twin Event History** | `SUPPORTED` (FSEvents+libproc) | `SUPPORTED` (ETW+WMI) | `SUPPORTED` (eBPF+inotify) | `SUPPORTED` (Nix+eBPF) |
| **2. Process Telemetry** | `SUPPORTED` (sysctl+libproc) | `SUPPORTED` (ETW) | `SUPPORTED` (/proc+eBPF) | `SUPPORTED` (/proc) |
| **3. Hardware Sensor Monitoring** | `PARTIAL` (sysctl+IOKit)* | `SUPPORTED` (WMI/SMBIOS) | `SUPPORTED` (/sys/class/hwmon)| `PARTIAL` (QEMU virtio) |
| **4. Autonomous OS Maintenance** | `SUPPORTED` (APFS+caches) | `SUPPORTED` (DISM/VSS) | `SUPPORTED` (apt/systemd) | `SUPPORTED` (nix-rebuild) |
| **5. File Provenance Tracking** | `SUPPORTED` (Quarantine+hash)| `SUPPORTED` (MotW+hash) | `SUPPORTED` (xattr+hash) | `SUPPORTED` (nix hashes) |
| **6. Controlled Sandboxing** | `SUPPORTED` (Sandbox.exec) | `PARTIAL` (AppContainer) | `SUPPORTED` (Landlock+cgroups)| `SUPPORTED` (systemd-nspawn)|
| **7. Atomic Rollback Support** | `SUPPORTED` (APFS snapshot) | `SUPPORTED` (VSS snapshot)| `PARTIAL` (Btrfs/LVM only) | `SUPPORTED` (Generations) |

*\*Note on macOS hardware sensors:* Thermal and fan speeds require private IOKit SPI on Apple Silicon; unprivileged collector falls back gracefully to `sysctl machdep.cpu` thermal state.

---

## 4. Unsupported Platforms Policy

To preserve engineering rigor and security integrity, the following environments are explicitly classified as `UNSUPPORTED` for v1.0:
- macOS Intel (x86_64 legacy)
- Windows 10, Windows 8/7, or 32-bit (x86) editions
- Non-systemd Linux distributions (Alpine with musl/OpenRC, Devuan)
- Mobile platforms (iOS, Android)
- Bare-metal installation on non-certified vendor hardware
