"""Cross-platform capability parity levels, specifications, registry, and evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from system_mind.platform.matrix import PlatformTargetId


class ParityLevel(str, Enum):
    """The five hierarchical capability parity levels for cross-platform adapters."""

    LEVEL_1_FULL_PARITY = "LEVEL_1_FULL_PARITY"
    LEVEL_2_EQUIVALENT_PARITY = "LEVEL_2_EQUIVALENT_PARITY"
    LEVEL_3_DEGRADED_PARITY = "LEVEL_3_DEGRADED_PARITY"
    LEVEL_4_EMULATED_SIMULATED = "LEVEL_4_EMULATED_SIMULATED"
    LEVEL_5_UNSUPPORTED = "LEVEL_5_UNSUPPORTED"


class CapabilityDomain(str, Enum):
    """Core operating system capability domains evaluated for parity."""

    FS_OBSERVATION = "FS_OBSERVATION"
    PROCESS_TELEMETRY = "PROCESS_TELEMETRY"
    HARDWARE_TELEMETRY = "HARDWARE_TELEMETRY"
    FILE_PROVENANCE = "FILE_PROVENANCE"
    EXECUTION_CONTAINMENT = "EXECUTION_CONTAINMENT"
    SYSTEM_SNAPSHOT_ROLLBACK = "SYSTEM_SNAPSHOT_ROLLBACK"
    SYSTEM_PACKAGE_MAINTENANCE = "SYSTEM_PACKAGE_MAINTENANCE"
    SECURITY_AUTHORITY_ENFORCEMENT = "SECURITY_AUTHORITY_ENFORCEMENT"


class PlatformCapabilityUnsupportedError(Exception):
    """Raised when an operation requests a capability unsupported on the active platform."""


@dataclass(frozen=True)
class PlatformParitySpecification:
    """Formal specification of a platform's implementation of a capability domain."""

    domain: CapabilityDomain
    platform_target: PlatformTargetId
    parity_level: ParityLevel
    native_api: str
    required_entitlements: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    fallback_strategy: str = ""
    is_security_critical: bool = False


@dataclass(frozen=True)
class ParityEvaluationResult:
    """Evaluation output when assessing execution dispatch against parity constraints."""

    permitted: bool
    platform: PlatformTargetId
    domain: CapabilityDomain
    parity_level: ParityLevel
    native_api: str
    active_fallback: Optional[str]
    warnings: List[str] = field(default_factory=list)


class CapabilityParityRegistry:
    """Central registry defining capability parity specifications across all platforms."""

    _SPECIFICATIONS: Dict[Tuple[PlatformTargetId, CapabilityDomain], PlatformParitySpecification] = {
        # =========================================================================
        # macOS on Apple Silicon (Tier 1 Development Host & Companion)
        # =========================================================================
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.FS_OBSERVATION): PlatformParitySpecification(
            domain=CapabilityDomain.FS_OBSERVATION,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="FSEvents.framework (FSEventStreamCreate)",
            required_entitlements=["Full Disk Access (FDA) recommended for user folders"],
            limitations=["FSEvents aggregates rapid successive file mutations into batches"],
            fallback_strategy="",
        ),
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.PROCESS_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.PROCESS_TELEMETRY,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="libproc (proc_pidinfo) + sysctl (KERN_PROC)",
            required_entitlements=["Standard unprivileged token"],
            limitations=["Cannot read environment variables or memory maps of foreign user processes"],
            fallback_strategy="ps / sysctl fallback queries",
        ),
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.HARDWARE_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.HARDWARE_TELEMETRY,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_3_DEGRADED_PARITY,
            native_api="IOKit.framework + sysctl machdep.cpu.thermal_level",
            required_entitlements=["IOKit access"],
            limitations=["Direct thermal sensor probe requires Apple SMC private keys unexposed to non-root processes"],
            fallback_strategy="sysctl machdep.cpu thermal pressure level and battery power metrics",
        ),
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.FILE_PROVENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.FILE_PROVENANCE,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="Extended attributes (com.apple.quarantine) + Gatekeeper spctl + SHA-256",
            required_entitlements=["Standard filesystem read"],
            limitations=["Quarantine xattr stripped if downloaded via curl without quarantine flags"],
            fallback_strategy="",
        ),
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.EXECUTION_CONTAINMENT): PlatformParitySpecification(
            domain=CapabilityDomain.EXECUTION_CONTAINMENT,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="Virtualization.framework / Hypervisor.framework micro-VMs / Docker",
            required_entitlements=["com.apple.security.virtualization"],
            limitations=["sandbox-exec is officially deprecated by Apple; production requires micro-VM or container shim"],
            fallback_strategy="Disposable Docker/Colima container execution",
        ),
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="APFS local snapshots (tmutil snapshot / fs_snapshot_create)",
            required_entitlements=["Standard user helper or root daemon"],
            limitations=["Snapshots require APFS filesystem format"],
            fallback_strategy="",
        ),
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="softwareupdate CLI + sealed system volume validation",
            required_entitlements=["Administrator consent for OS updates"],
            limitations=["Cumulative system updates require staged restart; user applications outside update scope"],
            fallback_strategy="User cache and log pruning only; defer OS upgrade staging to user maintenance window",
        ),
        (PlatformTargetId.MACOS_APPLE_SILICON, CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT): PlatformParitySpecification(
            domain=CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT,
            platform_target=PlatformTargetId.MACOS_APPLE_SILICON,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="System Integrity Protection (SIP) + Gatekeeper + TCC daemon",
            required_entitlements=["Kernel supervisor / native entitlements"],
            limitations=["SIP cannot be disabled or bypassed; must work strictly within granted entitlements"],
            fallback_strategy="",
            is_security_critical=True,
        ),

        # =========================================================================
        # Windows 11 x64 (Tier 2 Companion)
        # =========================================================================
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.FS_OBSERVATION): PlatformParitySpecification(
            domain=CapabilityDomain.FS_OBSERVATION,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="NTFS USN Journal (FSCTL_READ_USN_JOURNAL) + ReadDirectoryChangesW",
            required_entitlements=["Standard user / Backup Operator"],
            limitations=["USN journal requires NTFS formatted volume"],
            fallback_strategy="ReadDirectoryChangesW recursive watcher on non-NTFS volumes",
        ),
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.PROCESS_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.PROCESS_TELEMETRY,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="Event Tracing for Windows (Kernel-Process ETW) + NtQuerySystemInformation",
            required_entitlements=["Standard user token / Performance Log Users"],
            limitations=["High process frequency can cause ETW event drop under extreme load"],
            fallback_strategy="",
        ),
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.HARDWARE_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.HARDWARE_TELEMETRY,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="WMI (MSAcpi_ThermalInformationProvider / Win32_TemperatureProbe)",
            required_entitlements=["Standard user read"],
            limitations=["OEM drivers vary in exposing thermal zones via standard WMI queries"],
            fallback_strategy="ACPI thermal zone polling via Win32 API",
        ),
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.FILE_PROVENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.FILE_PROVENANCE,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="Alternate Data Streams (Zone.Identifier MOTW) + SmartScreen + SHA-256",
            required_entitlements=["Standard filesystem read"],
            limitations=["Zone.Identifier stream stripped on exFAT/FAT32 formatted media"],
            fallback_strategy="Cryptographic hash lookup against internal provenance cache",
        ),
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.EXECUTION_CONTAINMENT): PlatformParitySpecification(
            domain=CapabilityDomain.EXECUTION_CONTAINMENT,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="Windows Sandbox / AppContainer isolation / Hyper-V",
            required_entitlements=["Hyper-V feature enabled (Pro/Enterprise editions)"],
            limitations=["Windows Sandbox unavailable on Windows 11 Home edition without third-party containers"],
            fallback_strategy="AppContainer low-privilege token isolation",
        ),
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="Volume Shadow Copy Service (VSS) + System Restore Points",
            required_entitlements=["Elevated broker service"],
            limitations=["VSS service must be running; restore points require adequate shadow storage allocation"],
            fallback_strategy="Component-level file state backup before mutation",
        ),
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="Windows Update Agent (WUA) API + DISM",
            required_entitlements=["Elevated broker service"],
            limitations=["Cumulative updates require reboot staging; user applications outside update scope"],
            fallback_strategy="Staged download with scheduled restart during user maintenance window",
        ),
        (PlatformTargetId.WINDOWS_11_X64, CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT): PlatformParitySpecification(
            domain=CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT,
            platform_target=PlatformTargetId.WINDOWS_11_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="Windows Defender Application Control (WDAC) + SmartScreen + UAC",
            required_entitlements=["Kernel supervisor / Code Integrity policy"],
            limitations=["WDAC policies must be signed or enforced in audit mode before enforcement"],
            fallback_strategy="",
            is_security_critical=True,
        ),

        # =========================================================================
        # Ubuntu LTS x86_64 (Tier 2 Companion)
        # =========================================================================
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.FS_OBSERVATION): PlatformParitySpecification(
            domain=CapabilityDomain.FS_OBSERVATION,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="fanotify (global filesystem) + inotify (directory watches)",
            required_entitlements=["CAP_SYS_ADMIN for fanotify; unprivileged for inotify"],
            limitations=["fanotify requires elevated capabilities for directory events"],
            fallback_strategy="",
        ),
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.PROCESS_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.PROCESS_TELEMETRY,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="/proc filesystem + eBPF tracepoints (sched_process_exec, exit)",
            required_entitlements=["Standard read for /proc; CAP_BPF for eBPF"],
            limitations=["eBPF requires kernel >= 5.8 for unprivileged tracing maps"],
            fallback_strategy="",
        ),
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.HARDWARE_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.HARDWARE_TELEMETRY,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="/sys/class/hwmon + /sys/class/thermal",
            required_entitlements=["Standard unprivileged read"],
            limitations=["Virtual machine guests may lack emulated thermal sensors"],
            fallback_strategy="",
        ),
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.FILE_PROVENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.FILE_PROVENANCE,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_3_DEGRADED_PARITY,
            native_api="Extended attributes (user.xdg.origin.url) + SHA-256",
            required_entitlements=["Standard filesystem read"],
            limitations=["XDG attributes are populated only by compliant desktop applications; not enforced by kernel"],
            fallback_strategy="Cryptographic hash lookup against digital twin provenance ledger",
        ),
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.EXECUTION_CONTAINMENT): PlatformParitySpecification(
            domain=CapabilityDomain.EXECUTION_CONTAINMENT,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="Linux Landlock LSM + seccomp-bpf + user namespaces + cgroups v2",
            required_entitlements=["Unprivileged user namespaces (kernel >= 5.13)"],
            limitations=["AppArmor profiles may restrict unprivileged user namespace creation on hardened kernels"],
            fallback_strategy="",
        ),
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="Btrfs/ZFS snapshots or Timeshift (rsync / LVM thin pool)",
            required_entitlements=["Broker helper / CAP_SYS_ADMIN"],
            limitations=["Snapshot availability depends on root filesystem type (ext4 falls back to Timeshift rsync)"],
            fallback_strategy="Timeshift rsync snapshot or dpkg status archive rollback",
        ),
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="apt-get unattended-upgrades + needrestart + systemd journal vacuum",
            required_entitlements=["Narrow broker helper daemon via Polkit"],
            limitations=["dpkg frontend lock contention during concurrent admin package operations"],
            fallback_strategy="",
        ),
        (PlatformTargetId.UBUNTU_LTS_X64, CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT): PlatformParitySpecification(
            domain=CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT,
            platform_target=PlatformTargetId.UBUNTU_LTS_X64,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="AppArmor / SELinux + Landlock LSM + Linux capabilities",
            required_entitlements=["Kernel supervisor"],
            limitations=["Security profiles cannot be disabled or weakened"],
            fallback_strategy="",
            is_security_critical=True,
        ),

        # =========================================================================
        # NixOS VM (Tier 3 Prototype OS)
        # =========================================================================
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.FS_OBSERVATION): PlatformParitySpecification(
            domain=CapabilityDomain.FS_OBSERVATION,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="inotify + systemd journal stream",
            required_entitlements=["Standard read"],
            limitations=["Store is immutable; only system generation changes produce discrete profile events"],
            fallback_strategy="inotify user trees + journald system stream",
        ),
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.PROCESS_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.PROCESS_TELEMETRY,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="/proc filesystem + systemd cgroups v2",
            required_entitlements=["Standard read"],
            limitations=["Virtualized VM guest process monitoring only"],
            fallback_strategy="/proc scanning with systemd unit accounting",
        ),
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.HARDWARE_TELEMETRY): PlatformParitySpecification(
            domain=CapabilityDomain.HARDWARE_TELEMETRY,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_3_DEGRADED_PARITY,
            native_api="virtio sysfs + hypervisor guest metrics",
            required_entitlements=["Standard read"],
            limitations=["Physical host thermals and battery levels not passed to guest VM"],
            fallback_strategy="Hypervisor synthetic load and memory ballooning metrics",
        ),
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.FILE_PROVENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.FILE_PROVENANCE,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="Cryptographic NAR hash (/nix/store narHash) + SHA-256",
            required_entitlements=["Standard read"],
            limitations=["Only packages in /nix/store possess cryptographic NAR provenance"],
            fallback_strategy="Standard SHA-256 hashing for user downloads",
        ),
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.EXECUTION_CONTAINMENT): PlatformParitySpecification(
            domain=CapabilityDomain.EXECUTION_CONTAINMENT,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
            native_api="nix-shell --pure + systemd-nspawn ephemeral containers",
            required_entitlements=["Standard user for nix-shell; broker helper for nspawn"],
            limitations=["Pure nix-shell requires local store package availability"],
            fallback_strategy="systemd-nspawn ephemeral containers",
        ),
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_SNAPSHOT_ROLLBACK,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="Nix generation switching (/nix/var/nix/profiles/system) + bootloader rollback",
            required_entitlements=["Broker helper daemon"],
            limitations=["Generations protect system configuration profile, not mutable user files in /home"],
            fallback_strategy="",
        ),
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE): PlatformParitySpecification(
            domain=CapabilityDomain.SYSTEM_PACKAGE_MAINTENANCE,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="nixos-rebuild switch",
            required_entitlements=["Broker helper daemon"],
            limitations=["Requires network access to binary cache or local derivation build"],
            fallback_strategy="",
        ),
        (PlatformTargetId.NIXOS_VM, CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT): PlatformParitySpecification(
            domain=CapabilityDomain.SECURITY_AUTHORITY_ENFORCEMENT,
            platform_target=PlatformTargetId.NIXOS_VM,
            parity_level=ParityLevel.LEVEL_1_FULL_PARITY,
            native_api="Nix store immutability + Linux capabilities + AppArmor",
            required_entitlements=["Kernel supervisor"],
            limitations=["Store is cryptographically read-only by design"],
            fallback_strategy="",
            is_security_critical=True,
        ),
    }

    @classmethod
    def get_spec(cls, platform: PlatformTargetId, domain: CapabilityDomain) -> PlatformParitySpecification:
        """Retrieve the capability parity specification for a given platform and domain."""
        key = (platform, domain)
        if key not in cls._SPECIFICATIONS:
            raise KeyError(f"No parity specification registered for platform '{platform}' and domain '{domain}'.")
        return cls._SPECIFICATIONS[key]

    @classmethod
    def get_platform_specs(cls, platform: PlatformTargetId) -> List[PlatformParitySpecification]:
        """Retrieve all capability parity specifications for a given platform."""
        return [spec for (plat, _), spec in cls._SPECIFICATIONS.items() if plat == platform]

    @classmethod
    def get_domain_specs(cls, domain: CapabilityDomain) -> List[PlatformParitySpecification]:
        """Retrieve all platform specifications for a given capability domain."""
        return [spec for (_, dom), spec in cls._SPECIFICATIONS.items() if dom == domain]

    @classmethod
    def get_all_specs(cls) -> List[PlatformParitySpecification]:
        """Retrieve all cataloged capability parity specifications."""
        return list(cls._SPECIFICATIONS.values())


class CapabilityParityEvaluator:
    """Evaluates cross-platform dispatch requests against capability parity constraints."""

    @classmethod
    def evaluate_dispatch(
        cls,
        platform: PlatformTargetId,
        domain: CapabilityDomain,
        requires_full_parity: bool = False,
    ) -> ParityEvaluationResult:
        """Evaluate whether a capability request can be safely dispatched on the specified platform."""
        spec = CapabilityParityRegistry.get_spec(platform, domain)
        warnings: List[str] = []

        # Parity check
        if spec.parity_level == ParityLevel.LEVEL_5_UNSUPPORTED:
            raise PlatformCapabilityUnsupportedError(
                f"Platform '{platform.value}' does not support capability domain '{domain.value}'."
            )

        if requires_full_parity and spec.parity_level != ParityLevel.LEVEL_1_FULL_PARITY:
            return ParityEvaluationResult(
                permitted=False,
                platform=platform,
                domain=domain,
                parity_level=spec.parity_level,
                native_api=spec.native_api,
                active_fallback=spec.fallback_strategy if spec.fallback_strategy else None,
                warnings=[
                    f"Strict Parity Rejection: Domain '{domain.value}' has '{spec.parity_level.value}' on '{platform.value}', but caller requested strict LEVEL_1_FULL_PARITY."
                ],
            )

        # Warnings for degraded or equivalent parity
        if spec.parity_level == ParityLevel.LEVEL_3_DEGRADED_PARITY:
            warnings.append(
                f"Degraded Parity Warning: Domain '{domain.value}' is degraded on '{platform.value}'. Limitations: {'; '.join(spec.limitations)}. Active fallback: {spec.fallback_strategy}"
            )
        elif spec.parity_level == ParityLevel.LEVEL_2_EQUIVALENT_PARITY:
            warnings.append(
                f"Equivalent Parity Note: Domain '{domain.value}' uses platform-idiomatic API '{spec.native_api}' on '{platform.value}'."
            )
        elif spec.parity_level == ParityLevel.LEVEL_4_EMULATED_SIMULATED:
            warnings.append(
                f"Emulation Warning: Domain '{domain.value}' is emulated/simulated on '{platform.value}'. Active fallback: {spec.fallback_strategy}"
            )

        return ParityEvaluationResult(
            permitted=True,
            platform=platform,
            domain=domain,
            parity_level=spec.parity_level,
            native_api=spec.native_api,
            active_fallback=spec.fallback_strategy if spec.fallback_strategy else None,
            warnings=warnings,
        )

    @classmethod
    def audit_matrix_completeness(cls) -> Tuple[bool, List[str]]:
        """Audit the entire matrix for completeness and invariant adherence."""
        violations: List[str] = []
        all_platforms = [
            PlatformTargetId.MACOS_APPLE_SILICON,
            PlatformTargetId.WINDOWS_11_X64,
            PlatformTargetId.UBUNTU_LTS_X64,
            PlatformTargetId.NIXOS_VM,
        ]
        all_domains = list(CapabilityDomain)

        # Invariant 1: Completeness across all 4 platforms and 8 domains (32 entries)
        for platform in all_platforms:
            for domain in all_domains:
                try:
                    spec = CapabilityParityRegistry.get_spec(platform, domain)
                except KeyError:
                    violations.append(f"Missing Parity Specification: ({platform.value}, {domain.value})")
                    continue

                # Invariant 2: Non-full parity must specify fallback or limitations
                if spec.parity_level in (
                    ParityLevel.LEVEL_2_EQUIVALENT_PARITY,
                    ParityLevel.LEVEL_3_DEGRADED_PARITY,
                    ParityLevel.LEVEL_4_EMULATED_SIMULATED,
                ):
                    if not spec.fallback_strategy and not spec.limitations:
                        violations.append(
                            f"Missing Fallback/Limitations: ({platform.value}, {domain.value}) is {spec.parity_level.value} but lacks fallback or limitations."
                        )

                # Invariant 3: Security critical domains must be LEVEL_1_FULL_PARITY
                if spec.is_security_critical and spec.parity_level != ParityLevel.LEVEL_1_FULL_PARITY:
                    violations.append(
                        f"Security Non-Degradation Violation: Security-critical domain '{domain.value}' on '{platform.value}' must be LEVEL_1_FULL_PARITY; found {spec.parity_level.value}."
                    )

        is_valid = (len(violations) == 0)
        return is_valid, violations
