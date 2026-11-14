"""Platform and hardware compatibility matrix for SYSTEM MIND X first release."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from system_mind.core.types import (
    CapabilityStatus,
    HostEnvironmentReport,
    PlatformTier,
)


class PlatformTargetId(str, Enum):
    """Supported first-release platform target identifiers."""

    MACOS_APPLE_SILICON = "MACOS_APPLE_SILICON"
    WINDOWS_11_X64 = "WINDOWS_11_X64"
    UBUNTU_LTS_X64 = "UBUNTU_LTS_X64"
    NIXOS_VM = "NIXOS_VM"


@dataclass(frozen=True)
class HardwareSpec:
    """Hardware requirements and constraints for a platform target."""

    architecture: str
    min_cpu_cores: int
    min_ram_bytes: int
    required_features: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlatformCapabilityDetail:
    """Granular capability implementation status and fallback strategy."""

    capability_id: str
    capability_name: str
    status: CapabilityStatus
    native_api: str
    entitlement_or_permission: str
    limitations: List[str] = field(default_factory=list)
    fallback_strategy: str = ""


@dataclass(frozen=True)
class PlatformProfile:
    """Complete platform compatibility profile."""

    target_id: PlatformTargetId
    display_name: str
    platform_tier: PlatformTier
    kernel_family: str
    hardware_spec: HardwareSpec
    capabilities: Dict[str, PlatformCapabilityDetail]
    is_development_host: bool = False


class PlatformMatrixRegistry:
    """Central registry for supported first-release platform profiles and capability matrices."""

    _PROFILES: Dict[PlatformTargetId, PlatformProfile] = {
        PlatformTargetId.MACOS_APPLE_SILICON: PlatformProfile(
            target_id=PlatformTargetId.MACOS_APPLE_SILICON,
            display_name="macOS on Apple Silicon (M1/M2/M3)",
            platform_tier=PlatformTier.TIER_1_HOST_COMPANION,
            kernel_family="Darwin / XNU",
            hardware_spec=HardwareSpec(
                architecture="arm64",
                min_cpu_cores=8,
                min_ram_bytes=8 * 1024 * 1024 * 1024,  # 8 GB
                required_features=["Apple Silicon", "APFS", "SIP active"],
            ),
            is_development_host=True,
            capabilities={
                "digital_twin_events": PlatformCapabilityDetail(
                    capability_id="digital_twin_events",
                    capability_name="Digital Twin Event History",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="FSEvents.framework + libproc",
                    entitlement_or_permission="Full Disk Access (FDA) recommended for all user paths",
                    limitations=["FSEvents aggregates batch changes during rapid file mutations"],
                    fallback_strategy="Directory polling with stat / hash comparison",
                ),
                "process_telemetry": PlatformCapabilityDetail(
                    capability_id="process_telemetry",
                    capability_name="Process Telemetry & Monitoring",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="sysctl + proc_pidinfo",
                    entitlement_or_permission="Standard unprivileged read",
                    limitations=["Cannot read environment variables of foreign user processes"],
                    fallback_strategy="ps / sysctl fallback",
                ),
                "hardware_sensors": PlatformCapabilityDetail(
                    capability_id="hardware_sensors",
                    capability_name="Hardware Sensor Monitoring",
                    status=CapabilityStatus.PARTIAL,
                    native_api="IOKit.framework + sysctl",
                    entitlement_or_permission="IOKit access",
                    limitations=["Thermal sensors require private Apple Silicon SMC keys on non-root"],
                    fallback_strategy="sysctl machdep.cpu thermal pressure level",
                ),
                "autonomous_os_maintenance": PlatformCapabilityDetail(
                    capability_id="autonomous_os_maintenance",
                    capability_name="Autonomous OS Maintenance",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="APFS local snapshots (tmutil) + system cache pruning",
                    entitlement_or_permission="User interactive or helper daemon",
                    limitations=["Cannot modify sealed system volume without disabling SIP (strictly forbidden)"],
                    fallback_strategy="User cache and log pruning only",
                ),
                "file_provenance": PlatformCapabilityDetail(
                    capability_id="file_provenance",
                    capability_name="File Provenance & Quarantine Tracking",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="getxattr(com.apple.quarantine) + SHA-256",
                    entitlement_or_permission="Standard filesystem read",
                    limitations=["Quarantine flag removed if downloaded via non-quarantine-aware tools (e.g. curl)"],
                    fallback_strategy="SHA-256 hash lookup and origin heuristics",
                ),
                "controlled_sandboxing": PlatformCapabilityDetail(
                    capability_id="controlled_sandboxing",
                    capability_name="Controlled Sandboxing & Micro-Isolation",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="sandbox-exec / Docker / Hypervisor.framework",
                    entitlement_or_permission="Virtualization entitlement for hypervisor",
                    limitations=["sandbox-exec is officially deprecated by Apple; transitioning to micro-VMs"],
                    fallback_strategy="Disposable Docker/Colima container execution",
                ),
            },
        ),
        PlatformTargetId.WINDOWS_11_X64: PlatformProfile(
            target_id=PlatformTargetId.WINDOWS_11_X64,
            display_name="Windows 11 x64",
            platform_tier=PlatformTier.TIER_2_WINDOWS,
            kernel_family="Windows NT",
            hardware_spec=HardwareSpec(
                architecture="x86_64",
                min_cpu_cores=4,
                min_ram_bytes=8 * 1024 * 1024 * 1024,
                required_features=["TPM 2.0", "UEFI Secure Boot", "VBS"],
            ),
            is_development_host=False,
            capabilities={
                "digital_twin_events": PlatformCapabilityDetail(
                    capability_id="digital_twin_events",
                    capability_name="Digital Twin Event History",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="Event Tracing for Windows (ETW) + USN Journal",
                    entitlement_or_permission="Administrator / Event Log Readers",
                    limitations=["USN journal requires NTFS volume"],
                    fallback_strategy="ReadDirectoryChangesW directory monitoring",
                ),
                "process_telemetry": PlatformCapabilityDetail(
                    capability_id="process_telemetry",
                    capability_name="Process Telemetry & Monitoring",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="WMI / PDH Performance Counters + ETW",
                    entitlement_or_permission="Standard user token",
                    limitations=["WMI can exhibit latency during heavy system load"],
                    fallback_strategy="Toolhelp32Snapshot / NtQuerySystemInformation",
                ),
                "hardware_sensors": PlatformCapabilityDetail(
                    capability_id="hardware_sensors",
                    capability_name="Hardware Sensor Monitoring",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="WMI (Win32_TemperatureProbe / SMBIOS)",
                    entitlement_or_permission="Standard read",
                    limitations=["OEM drivers vary in sensor exposure"],
                    fallback_strategy="ACPI thermal zone polling",
                ),
                "autonomous_os_maintenance": PlatformCapabilityDetail(
                    capability_id="autonomous_os_maintenance",
                    capability_name="Autonomous OS Maintenance",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="DISM / Volume Shadow Copy (VSS)",
                    entitlement_or_permission="Elevated Broker Service",
                    limitations=["VSS requires active Volume Shadow Copy service"],
                    fallback_strategy="Staged update with recovery restore point",
                ),
                "file_provenance": PlatformCapabilityDetail(
                    capability_id="file_provenance",
                    capability_name="File Provenance & Mark-of-the-Web",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="Zone.Identifier Alternate Data Stream (ADS) + SHA-256",
                    entitlement_or_permission="Standard filesystem read",
                    limitations=["ADS stripped on FAT32/exFAT filesystems"],
                    fallback_strategy="File hash database and origin tracking",
                ),
                "controlled_sandboxing": PlatformCapabilityDetail(
                    capability_id="controlled_sandboxing",
                    capability_name="Controlled Sandboxing & Micro-Isolation",
                    status=CapabilityStatus.PARTIAL,
                    native_api="Windows Sandbox / AppContainer / Hyper-V",
                    entitlement_or_permission="Hyper-V role enabled",
                    limitations=["Windows Sandbox not available on Windows 11 Home edition"],
                    fallback_strategy="AppContainer low-privilege isolation",
                ),
            },
        ),
        PlatformTargetId.UBUNTU_LTS_X64: PlatformProfile(
            target_id=PlatformTargetId.UBUNTU_LTS_X64,
            display_name="Ubuntu LTS x86_64",
            platform_tier=PlatformTier.TIER_2_UBUNTU,
            kernel_family="Linux Kernel",
            hardware_spec=HardwareSpec(
                architecture="x86_64",
                min_cpu_cores=4,
                min_ram_bytes=8 * 1024 * 1024 * 1024,
                required_features=["systemd", "cgroups v2", "eBPF support"],
            ),
            is_development_host=False,
            capabilities={
                "digital_twin_events": PlatformCapabilityDetail(
                    capability_id="digital_twin_events",
                    capability_name="Digital Twin Event History",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="fanotify + inotify + eBPF",
                    entitlement_or_permission="CAP_SYS_ADMIN recommended for fanotify",
                    limitations=["fanotify requires privileged capabilities"],
                    fallback_strategy="inotify recursive directory watch",
                ),
                "process_telemetry": PlatformCapabilityDetail(
                    capability_id="process_telemetry",
                    capability_name="Process Telemetry & Monitoring",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="/proc filesystem + eBPF tracepoints",
                    entitlement_or_permission="Standard read for /proc",
                    limitations=["High process churn can miss ephemeral short-lived processes without eBPF"],
                    fallback_strategy="/proc scan loop with PID cgroup accounting",
                ),
                "hardware_sensors": PlatformCapabilityDetail(
                    capability_id="hardware_sensors",
                    capability_name="Hardware Sensor Monitoring",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="/sys/class/hwmon + /sys/class/thermal",
                    entitlement_or_permission="Standard read",
                    limitations=["Virtual machine guests may lack physical thermal sensor emulation"],
                    fallback_strategy="Graceful empty sensor collection with status note",
                ),
                "autonomous_os_maintenance": PlatformCapabilityDetail(
                    capability_id="autonomous_os_maintenance",
                    capability_name="Autonomous OS Maintenance",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="apt-get unattended-upgrades + systemd journal vacuum",
                    entitlement_or_permission="Polkit / Narrow Broker helper",
                    limitations=["Package locks (dpkg lock) prevent concurrent updates"],
                    fallback_strategy="Deferred maintenance queue with retry backoff",
                ),
                "file_provenance": PlatformCapabilityDetail(
                    capability_id="file_provenance",
                    capability_name="File Provenance & Extended Attributes",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="getfattr (user.xdg.origin.url) + SHA-256",
                    entitlement_or_permission="Standard filesystem read",
                    limitations=["XDG origin attributes depend on browser implementation"],
                    fallback_strategy="Cryptographic hash lookup",
                ),
                "controlled_sandboxing": PlatformCapabilityDetail(
                    capability_id="controlled_sandboxing",
                    capability_name="Controlled Sandboxing & Micro-Isolation",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="Linux Landlock LSM + seccomp-bpf + namespaces",
                    entitlement_or_permission="Unprivileged user namespaces (kernel >= 5.13)",
                    limitations=["AppArmor or kernel configs may restrict unprivileged user namespaces"],
                    fallback_strategy="systemd-run with DynamicUser=yes and ProtectSystem=strict",
                ),
            },
        ),
        PlatformTargetId.NIXOS_VM: PlatformProfile(
            target_id=PlatformTargetId.NIXOS_VM,
            display_name="NixOS x86_64/ARM64 (VM Prototype)",
            platform_tier=PlatformTier.TIER_3_NIXOS_VM,
            kernel_family="Linux Kernel (Declarative)",
            hardware_spec=HardwareSpec(
                architecture="x86_64, arm64",
                min_cpu_cores=2,
                min_ram_bytes=4 * 1024 * 1024 * 1024,  # 4 GB virtual
                required_features=["QEMU/UTM hypervisor", "Nix store", "GRUB/systemd-boot"],
            ),
            is_development_host=False,
            capabilities={
                "digital_twin_events": PlatformCapabilityDetail(
                    capability_id="digital_twin_events",
                    capability_name="Digital Twin Event History",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="Nix generation history + systemd journal",
                    entitlement_or_permission="Standard read",
                    limitations=["Store is immutable; only system configuration profile changes emit generations"],
                    fallback_strategy="Journald event stream",
                ),
                "process_telemetry": PlatformCapabilityDetail(
                    capability_id="process_telemetry",
                    capability_name="Process Telemetry & Monitoring",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="/proc + systemd cgroups",
                    entitlement_or_permission="Standard read",
                    limitations=["VM virtualized CPU telemetry only"],
                    fallback_strategy="/proc polling",
                ),
                "hardware_sensors": PlatformCapabilityDetail(
                    capability_id="hardware_sensors",
                    capability_name="Hardware Sensor Monitoring",
                    status=CapabilityStatus.PARTIAL,
                    native_api="virtio-balloon + virtual sysfs",
                    entitlement_or_permission="Standard read",
                    limitations=["Physical silicon thermal readings not passed through virtual hypervisor"],
                    fallback_strategy="Hypervisor memory and CPU load metrics",
                ),
                "autonomous_os_maintenance": PlatformCapabilityDetail(
                    capability_id="autonomous_os_maintenance",
                    capability_name="Autonomous OS Maintenance",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="nixos-rebuild switch + /nix/var/nix/profiles/system",
                    entitlement_or_permission="Broker helper with nix-env access",
                    limitations=["Requires network access to binary cache or local derivation build"],
                    fallback_strategy="Atomic generational rollback via bootloader generation selection",
                ),
                "file_provenance": PlatformCapabilityDetail(
                    capability_id="file_provenance",
                    capability_name="File Provenance & Store Integrity",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="nix-store --verify + SHA-256 narHash",
                    entitlement_or_permission="Standard read",
                    limitations=["Only packages in /nix/store have cryptographic NAR signatures"],
                    fallback_strategy="Standard SHA-256 hash inspection for user downloads",
                ),
                "controlled_sandboxing": PlatformCapabilityDetail(
                    capability_id="controlled_sandboxing",
                    capability_name="Controlled Sandboxing & Micro-Isolation",
                    status=CapabilityStatus.SUPPORTED,
                    native_api="nix-shell --pure / systemd-nspawn",
                    entitlement_or_permission="Standard read / broker service",
                    limitations=["Pure nix-shell requires local package derivations"],
                    fallback_strategy="systemd-nspawn ephemeral container",
                ),
            },
        ),
    }

    @classmethod
    def get_profile(cls, target_id: PlatformTargetId) -> PlatformProfile:
        """Retrieve the platform compatibility profile."""
        if target_id not in cls._PROFILES:
            raise KeyError(f"Target '{target_id}' is not in the supported platform matrix.")
        return cls._PROFILES[target_id]

    @classmethod
    def get_all_profiles(cls) -> List[PlatformProfile]:
        """Return all supported platform profiles."""
        return list(cls._PROFILES.values())

    @classmethod
    def get_capability_status(cls, target_id: PlatformTargetId, capability_id: str) -> CapabilityStatus:
        """Query the status of a specific capability on a target platform."""
        profile = cls.get_profile(target_id)
        if capability_id not in profile.capabilities:
            return CapabilityStatus.UNSUPPORTED
        return profile.capabilities[capability_id].status

    @classmethod
    def validate_host_compatibility(cls, report: HostEnvironmentReport) -> Tuple[bool, List[str]]:
        """Validate a host environment report against the supported hardware matrix."""
        diagnostics: List[str] = []

        # 1. Platform & OS Identification
        target_id: Optional[PlatformTargetId] = None
        if report.os_name == "Darwin" and report.architecture in ("arm64", "aarch64"):
            target_id = PlatformTargetId.MACOS_APPLE_SILICON
        elif report.os_name == "Windows" and report.architecture in ("x86_64", "AMD64"):
            target_id = PlatformTargetId.WINDOWS_11_X64
        elif report.os_name == "Linux" and report.architecture in ("x86_64", "amd64"):
            target_id = PlatformTargetId.UBUNTU_LTS_X64

        if target_id is None:
            diagnostics.append(
                f"Unsupported Host: OS '{report.os_name}' on architecture '{report.architecture}' is outside the first-release support matrix."
            )
            return False, diagnostics

        profile = cls.get_profile(target_id)
        spec = profile.hardware_spec

        # 2. Hardware Resource Checks
        if report.memory_bytes < spec.min_ram_bytes:
            ram_gb = report.memory_bytes / (1024**3)
            min_gb = spec.min_ram_bytes / (1024**3)
            diagnostics.append(
                f"Insufficient Memory: Host has {ram_gb:.1f} GB RAM; minimum required for {profile.display_name} is {min_gb:.1f} GB."
            )

        if report.cpu_cores < spec.min_cpu_cores:
            diagnostics.append(
                f"Insufficient CPU Cores: Host has {report.cpu_cores} cores; minimum required for {profile.display_name} is {spec.min_cpu_cores}."
            )

        # 3. macOS Security Checks
        if target_id == PlatformTargetId.MACOS_APPLE_SILICON:
            if report.sip_enabled is False:
                diagnostics.append(
                    "Security Warning: macOS System Integrity Protection (SIP) is disabled; production safety guarantees require SIP enabled."
                )

        is_compatible = (len(diagnostics) == 0)
        return is_compatible, diagnostics
