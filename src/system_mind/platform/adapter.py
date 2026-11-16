"""Safe mock platform adapter subsystem for SYSTEM MIND X.

Provides the abstract PlatformAdapter interface across the 8 capability domains,
concrete MockPlatformAdapter for safe deterministic simulation without host
privileges or mutation, and profile factories for development and CI testing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import time
from typing import Any, Dict, List, Optional

from system_mind.core.types import (
    ActionContract,
    CapabilityStatus,
    ComponentOwnership,
    FileExecutionContainment,
    HostEnvironmentReport,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)
from system_mind.platform.matrix import (
    HardwareSpec,
    PlatformMatrixRegistry,
    PlatformProfile,
    PlatformTargetId,
)


@dataclass(frozen=True)
class SecurityStateSnapshot:
    """Snapshot of platform security mechanisms, kernel protections, and policy status."""

    target_id: PlatformTargetId
    sip_enabled: Optional[bool] = True
    gatekeeper_enabled: Optional[bool] = True
    secure_boot_enabled: Optional[bool] = True
    firewall_enabled: bool = True
    disk_encryption_enabled: bool = True
    lockdown_mode: bool = False
    selinux_or_apparmor_status: Optional[str] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class HardwareTelemetrySnapshot:
    """Snapshot of hardware metrics, thermal status, power source, and storage."""

    cpu_usage_pct: float = 12.5
    memory_rss_bytes: int = 42_000_000  # 42 MB
    memory_free_bytes: int = 8_589_934_592  # 8 GB
    disk_available_bytes: int = 120_000_000_000  # 120 GB
    thermal_state: str = "NOMINAL"  # NOMINAL, FAIR, SERIOUS, CRITICAL
    power_source: str = "AC_POWER"  # AC_POWER, BATTERY, UPS
    battery_pct: Optional[float] = 100.0
    is_charging: Optional[bool] = True
    timestamp_epoch_secs: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ProcessTelemetrySnapshot:
    """Snapshot of a process running on the host system."""

    pid: int
    name: str
    ppid: int
    uid: int
    gid: int
    cpu_pct: float
    memory_bytes: int
    signature_valid: bool = True
    is_system_core: bool = False
    is_user_app: bool = False


@dataclass(frozen=True)
class FsEventSnapshot:
    """Snapshot of a filesystem mutation event (FSEvents / USN / fanotify)."""

    event_id: str
    path: str
    event_type: str  # CREATED, MODIFIED, DELETED, ATTRIB_CHANGED
    timestamp_epoch_secs: float = field(default_factory=time.time)
    is_directory: bool = False


@dataclass(frozen=True)
class FileProvenanceSnapshot:
    """Snapshot of file provenance, origin quarantine attributes, and hash digests."""

    path: str
    sha256_hash: str
    file_size_bytes: int
    quarantine_xattr: Optional[str] = None
    zone_identifier: Optional[int] = None
    origin_url: Optional[str] = None
    is_quarantined: bool = False


@dataclass(frozen=True)
class SnapshotResult:
    """Result of creating a system state snapshot (APFS / VSS / Btrfs)."""

    snapshot_id: str
    label: str
    platform_target: PlatformTargetId
    timestamp_epoch_secs: float = field(default_factory=time.time)
    success: bool = True
    size_bytes: int = 0
    error_message: Optional[str] = None


@dataclass(frozen=True)
class RollbackResult:
    """Result of reverting the system to a previous snapshot."""

    snapshot_id: str
    success: bool = True
    reverted_at_epoch_secs: float = field(default_factory=time.time)
    details: str = ""
    error_message: Optional[str] = None


@dataclass(frozen=True)
class UpdateStageResult:
    """Result of staging an operating system or package maintenance payload."""

    update_id: str
    component_ownership: ComponentOwnership
    staged: bool = True
    requires_reboot: bool = False
    details: str = ""
    error_message: Optional[str] = None


class PlatformAdapter(ABC):
    """Authoritative abstract base class for all platform adapters in SYSTEM MIND X.

    Defines typed contracts across all 8 capability domains in CapabilityDomain.
    """

    @abstractmethod
    def get_target_id(self) -> PlatformTargetId:
        """Return the target platform identifier."""
        ...

    @abstractmethod
    def get_host_report(self) -> HostEnvironmentReport:
        """Collect read-only host platform and toolchain telemetry."""
        ...

    @abstractmethod
    def get_security_state(self) -> SecurityStateSnapshot:
        """Inspect authoritative kernel security controls and policy status."""
        ...

    @abstractmethod
    def get_hardware_telemetry(self) -> HardwareTelemetrySnapshot:
        """Collect non-privileged hardware, thermal, and power telemetry."""
        ...

    @abstractmethod
    def get_process_telemetry(self) -> List[ProcessTelemetrySnapshot]:
        """Collect running process snapshots."""
        ...

    @abstractmethod
    def get_filesystem_events(self, path: Optional[str] = None) -> List[FsEventSnapshot]:
        """Retrieve recent filesystem observation events."""
        ...

    @abstractmethod
    def get_file_provenance(self, path: str) -> FileProvenanceSnapshot:
        """Inspect file provenance, origin URL, quarantine, and hash."""
        ...

    @abstractmethod
    def create_system_snapshot(self, label: str) -> SnapshotResult:
        """Create a point-in-time system snapshot for safe rollback."""
        ...

    @abstractmethod
    def rollback_system_snapshot(self, snapshot_id: str) -> RollbackResult:
        """Revert the system to a previously created snapshot."""
        ...

    @abstractmethod
    def stage_system_update(self, update_id: str, component: ComponentOwnership) -> UpdateStageResult:
        """Stage a system maintenance update without modifying user-managed apps."""
        ...

    @abstractmethod
    def execute_contained_action(self, contract: ActionContract) -> Dict[str, Any]:
        """Execute a typed action contract within an isolated execution boundary."""
        ...

    @abstractmethod
    def get_audit_history(self) -> List[Dict[str, Any]]:
        """Return the chronological audit log of all adapter operations."""
        ...


class MockPlatformAdapter(PlatformAdapter):
    """Deterministic, unprivileged mock platform adapter for development, testing, and CI.

    Performs zero host file mutations, runs zero ambient shell commands, and strictly
    enforces safety constraints (SC-01, SC-02, SC-03) in memory.
    """

    def __init__(
        self,
        target_id: PlatformTargetId = PlatformTargetId.MACOS_APPLE_SILICON,
        security_state: Optional[SecurityStateSnapshot] = None,
        hardware_telemetry: Optional[HardwareTelemetrySnapshot] = None,
        host_report: Optional[HostEnvironmentReport] = None,
    ) -> None:
        self._target_id = target_id
        self._profile = PlatformMatrixRegistry.get_profile(target_id)
        self._audit_log: List[Dict[str, Any]] = []
        self._simulated_errors: Dict[str, Exception] = {}
        self._snapshots: Dict[str, SnapshotResult] = {}
        self._fs_events: List[FsEventSnapshot] = []
        self._provenance_db: Dict[str, FileProvenanceSnapshot] = {}

        # Default Host Environment Report
        if host_report is not None:
            self._host_report = host_report
        else:
            self._host_report = self._build_default_host_report()

        # Default Security State
        if security_state is not None:
            self._security_state = security_state
        else:
            self._security_state = self._build_default_security_state()

        # Default Hardware Telemetry
        if hardware_telemetry is not None:
            self._hardware_telemetry = hardware_telemetry
        else:
            self._hardware_telemetry = HardwareTelemetrySnapshot()

        # Default Process List
        self._processes: List[ProcessTelemetrySnapshot] = self._build_default_processes()

    def _build_default_host_report(self) -> HostEnvironmentReport:
        if self._target_id == PlatformTargetId.MACOS_APPLE_SILICON:
            return HostEnvironmentReport(
                os_name="Darwin",
                os_version="15.1.0",
                kernel_version="24.1.0",
                architecture="arm64",
                cpu_brand="Apple M3 Pro",
                cpu_cores=12,
                memory_bytes=18 * 1024 * 1024 * 1024,
                sip_enabled=True,
                gatekeeper_enabled=True,
                platform_tier=PlatformTier.TIER_1_HOST_COMPANION,
                installed_tools={
                    "python3": "/opt/homebrew/bin/python3",
                    "git": "/usr/bin/git",
                    "cargo": "/Users/developer/.cargo/bin/cargo",
                    "rustc": "/Users/developer/.cargo/bin/rustc",
                    "node": "/opt/homebrew/bin/node",
                },
                is_supported_host=True,
                notes=["Simulated Tier-1 Apple Silicon Host (Mock Adapter)"],
            )
        elif self._target_id == PlatformTargetId.WINDOWS_11_X64:
            return HostEnvironmentReport(
                os_name="Windows",
                os_version="10.0.22631",
                kernel_version="10.0.22631.3007",
                architecture="x86_64",
                cpu_brand="AMD Ryzen 7 7840HS",
                cpu_cores=16,
                memory_bytes=32 * 1024 * 1024 * 1024,
                sip_enabled=None,
                gatekeeper_enabled=None,
                platform_tier=PlatformTier.TIER_2_WINDOWS,
                installed_tools={
                    "python3": "C:\\Python312\\python.exe",
                    "git": "C:\\Program Files\\Git\\cmd\\git.exe",
                    "cargo": "C:\\Users\\dev\\.cargo\\bin\\cargo.exe",
                },
                is_supported_host=True,
                notes=["Simulated Windows 11 x64 Host (Mock Adapter)"],
            )
        elif self._target_id == PlatformTargetId.UBUNTU_LTS_X64:
            return HostEnvironmentReport(
                os_name="Linux",
                os_version="Ubuntu 24.04 LTS",
                kernel_version="6.8.0-31-generic",
                architecture="x86_64",
                cpu_brand="Intel Core i7-13700H",
                cpu_cores=14,
                memory_bytes=32 * 1024 * 1024 * 1024,
                sip_enabled=None,
                gatekeeper_enabled=None,
                platform_tier=PlatformTier.TIER_2_UBUNTU,
                installed_tools={
                    "python3": "/usr/bin/python3",
                    "git": "/usr/bin/git",
                    "cargo": "/home/dev/.cargo/bin/cargo",
                    "systemctl": "/usr/bin/systemctl",
                },
                is_supported_host=True,
                notes=["Simulated Ubuntu 24.04 LTS Host (Mock Adapter)"],
            )
        else:  # NIXOS_VM
            return HostEnvironmentReport(
                os_name="Linux",
                os_version="NixOS 24.05",
                kernel_version="6.6.32",
                architecture="x86_64",
                cpu_brand="QEMU Virtual CPU",
                cpu_cores=4,
                memory_bytes=8 * 1024 * 1024 * 1024,
                sip_enabled=None,
                gatekeeper_enabled=None,
                platform_tier=PlatformTier.TIER_3_NIXOS_VM,
                installed_tools={
                    "python3": "/run/current-system/sw/bin/python3",
                    "git": "/run/current-system/sw/bin/git",
                    "nix": "/run/current-system/sw/bin/nix",
                },
                is_supported_host=True,
                notes=["Simulated NixOS Declarative VM (Mock Adapter)"],
            )

    def _build_default_security_state(self) -> SecurityStateSnapshot:
        if self._target_id == PlatformTargetId.MACOS_APPLE_SILICON:
            return SecurityStateSnapshot(
                target_id=self._target_id,
                sip_enabled=True,
                gatekeeper_enabled=True,
                secure_boot_enabled=True,
                firewall_enabled=True,
                disk_encryption_enabled=True,
                lockdown_mode=False,
                notes=["SIP Active", "Gatekeeper Active", "FileVault Active"],
            )
        elif self._target_id == PlatformTargetId.WINDOWS_11_X64:
            return SecurityStateSnapshot(
                target_id=self._target_id,
                sip_enabled=None,
                gatekeeper_enabled=None,
                secure_boot_enabled=True,
                firewall_enabled=True,
                disk_encryption_enabled=True,
                lockdown_mode=False,
                notes=["UEFI Secure Boot Active", "BitLocker Active", "Windows Defender Active"],
            )
        elif self._target_id == PlatformTargetId.UBUNTU_LTS_X64:
            return SecurityStateSnapshot(
                target_id=self._target_id,
                sip_enabled=None,
                gatekeeper_enabled=None,
                secure_boot_enabled=True,
                firewall_enabled=True,
                disk_encryption_enabled=True,
                lockdown_mode=False,
                selinux_or_apparmor_status="AppArmor: ENFORCING",
                notes=["AppArmor Active", "LUKS Encryption Active", "ufw Enabled"],
            )
        else:  # NIXOS_VM
            return SecurityStateSnapshot(
                target_id=self._target_id,
                sip_enabled=None,
                gatekeeper_enabled=None,
                secure_boot_enabled=False,
                firewall_enabled=True,
                disk_encryption_enabled=False,
                lockdown_mode=False,
                notes=["NixOS Store Immutable", "Ephemeral VM Sandbox"],
            )

    def _build_default_processes(self) -> List[ProcessTelemetrySnapshot]:
        return [
            ProcessTelemetrySnapshot(
                pid=1,
                name="launchd" if self._target_id == PlatformTargetId.MACOS_APPLE_SILICON else "systemd",
                ppid=0,
                uid=0,
                gid=0,
                cpu_pct=0.1,
                memory_bytes=15_000_000,
                signature_valid=True,
                is_system_core=True,
                is_user_app=False,
            ),
            ProcessTelemetrySnapshot(
                pid=501,
                name="system_mind_broker",
                ppid=1,
                uid=501,
                gid=20,
                cpu_pct=1.2,
                memory_bytes=35_000_000,
                signature_valid=True,
                is_system_core=True,
                is_user_app=False,
            ),
            ProcessTelemetrySnapshot(
                pid=1024,
                name="vscode_or_cursor",
                ppid=1,
                uid=501,
                gid=20,
                cpu_pct=4.5,
                memory_bytes=650_000_000,
                signature_valid=True,
                is_system_core=False,
                is_user_app=True,
            ),
        ]

    # =========================================================================
    # PlatformAdapter Interface Implementation
    # =========================================================================

    def get_target_id(self) -> PlatformTargetId:
        self._check_simulated_error("get_target_id")
        return self._target_id

    def get_host_report(self) -> HostEnvironmentReport:
        self._check_simulated_error("get_host_report")
        return self._host_report

    def get_security_state(self) -> SecurityStateSnapshot:
        self._check_simulated_error("get_security_state")
        return self._security_state

    def get_hardware_telemetry(self) -> HardwareTelemetrySnapshot:
        self._check_simulated_error("get_hardware_telemetry")
        # Update timestamp on read to simulate live clock
        self._hardware_telemetry.timestamp_epoch_secs = time.time()
        return self._hardware_telemetry

    def get_process_telemetry(self) -> List[ProcessTelemetrySnapshot]:
        self._check_simulated_error("get_process_telemetry")
        return list(self._processes)

    def get_filesystem_events(self, path: Optional[str] = None) -> List[FsEventSnapshot]:
        self._check_simulated_error("get_filesystem_events")
        if path is None:
            return list(self._fs_events)
        return [e for e in self._fs_events if e.path.startswith(path)]

    def get_file_provenance(self, path: str) -> FileProvenanceSnapshot:
        self._check_simulated_error("get_file_provenance")
        if path in self._provenance_db:
            return self._provenance_db[path]

        # Deterministic synthetic fallback for any queried path
        path_hash = hashlib.sha256(path.encode("utf-8")).hexdigest()
        is_quarantine = "Downloads" in path or "tmp" in path
        return FileProvenanceSnapshot(
            path=path,
            sha256_hash=path_hash,
            file_size_bytes=1024 * 64,
            quarantine_xattr="0081;66554433;Safari;https://example.com/untrusted" if is_quarantine else None,
            zone_identifier=3 if is_quarantine else 0,
            origin_url="https://example.com/untrusted" if is_quarantine else None,
            is_quarantined=is_quarantine,
        )

    def create_system_snapshot(self, label: str) -> SnapshotResult:
        self._check_simulated_error("create_system_snapshot")
        now = time.time()
        snapshot_id = f"snap_{int(now)}_{hashlib.sha256(label.encode('utf-8')).hexdigest()[:8]}"
        result = SnapshotResult(
            snapshot_id=snapshot_id,
            label=label,
            platform_target=self._target_id,
            timestamp_epoch_secs=now,
            success=True,
            size_bytes=1024 * 1024 * 250,  # 250 MB differential
        )
        self._snapshots[snapshot_id] = result
        self._record_audit_event("CREATE_SNAPSHOT", {"snapshot_id": snapshot_id, "label": label})
        return result

    def rollback_system_snapshot(self, snapshot_id: str) -> RollbackResult:
        self._check_simulated_error("rollback_system_snapshot")
        if snapshot_id not in self._snapshots:
            return RollbackResult(
                snapshot_id=snapshot_id,
                success=False,
                error_message=f"Snapshot '{snapshot_id}' not found.",
            )

        snap = self._snapshots[snapshot_id]
        result = RollbackResult(
            snapshot_id=snapshot_id,
            success=True,
            reverted_at_epoch_secs=time.time(),
            details=f"Successfully rolled back to snapshot '{snap.label}' ({snapshot_id}).",
        )
        self._record_audit_event("ROLLBACK_SNAPSHOT", {"snapshot_id": snapshot_id})
        return result

    def stage_system_update(self, update_id: str, component: ComponentOwnership) -> UpdateStageResult:
        self._check_simulated_error("stage_system_update")

        # Safety Guard: Autonomous maintenance against user apps is strictly blocked!
        if component == ComponentOwnership.USER_MANAGED:
            self._record_audit_event(
                "UPDATE_REJECTED",
                {"update_id": update_id, "reason": "USER_MANAGED component protected from autonomous update"},
            )
            raise PermissionError(
                f"Autonomous maintenance update rejected: component '{update_id}' is USER_MANAGED."
            )

        result = UpdateStageResult(
            update_id=update_id,
            component_ownership=component,
            staged=True,
            requires_reboot=False,
            details=f"Update '{update_id}' ({component.value}) staged successfully.",
        )
        self._record_audit_event("STAGE_UPDATE", {"update_id": update_id, "component": component.value})
        return result

    def execute_contained_action(self, contract: ActionContract) -> Dict[str, Any]:
        self._check_simulated_error("execute_contained_action")

        # SC-02 / ADR-018: User application protection invariant
        if contract.target_ownership == ComponentOwnership.USER_MANAGED and contract.is_autonomous_maintenance:
            self._record_audit_event(
                "ACTION_REJECTED",
                {"action_id": contract.action_id, "reason": "Autonomous maintenance targeting USER_MANAGED component"},
            )
            raise PermissionError(
                f"Action '{contract.action_id}' violates SC-02: Autonomous maintenance cannot target USER_MANAGED applications."
            )

        # SC-03: Critical privileged approval gate
        if (contract.risk_tier == OperationRiskTier.CRITICAL_PRIVILEGED or contract.requires_root) and not contract.user_approved:
            self._record_audit_event(
                "ACTION_REJECTED",
                {"action_id": contract.action_id, "reason": "Missing user approval for CRITICAL_PRIVILEGED operation"},
            )
            raise PermissionError(
                f"Action '{contract.action_id}' requires explicit user approval before execution."
            )

        result = {
            "action_id": contract.action_id,
            "status": "COMPLETED",
            "target_component": contract.target_component,
            "ownership": contract.target_ownership.value,
            "risk_tier": contract.risk_tier.value,
            "executed_at": time.time(),
            "containment": contract.file_containment.value if contract.file_containment else "DEFAULT_SANDBOX",
        }
        self._record_audit_event("EXECUTE_ACTION", result)
        return result

    def get_audit_history(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    # =========================================================================
    # Test & Simulation Helpers (Pure In-Memory Mutators)
    # =========================================================================

    def set_thermal_state(self, state: str) -> None:
        """Simulate change in thermal pressure (NOMINAL, FAIR, SERIOUS, CRITICAL)."""
        valid_states = {"NOMINAL", "FAIR", "SERIOUS", "CRITICAL"}
        if state not in valid_states:
            raise ValueError(f"Invalid thermal state '{state}'. Expected one of {valid_states}")
        self._hardware_telemetry.thermal_state = state
        self._record_audit_event("SET_THERMAL_STATE", {"thermal_state": state})

    def set_power_source(
        self,
        source: str,
        battery_pct: Optional[float] = None,
        is_charging: Optional[bool] = None,
    ) -> None:
        """Simulate power transitions (AC_POWER vs BATTERY)."""
        self._hardware_telemetry.power_source = source
        if battery_pct is not None:
            self._hardware_telemetry.battery_pct = battery_pct
        if is_charging is not None:
            self._hardware_telemetry.is_charging = is_charging
        self._record_audit_event(
            "SET_POWER_SOURCE",
            {"power_source": source, "battery_pct": battery_pct, "is_charging": is_charging},
        )

    def set_disk_available(self, available_bytes: int) -> None:
        """Simulate storage exhaustion or expansion."""
        self._hardware_telemetry.disk_available_bytes = available_bytes
        self._record_audit_event("SET_DISK_AVAILABLE", {"disk_available_bytes": available_bytes})

    def set_security_state(self, security_state: SecurityStateSnapshot) -> None:
        """Inject an updated security state snapshot."""
        self._security_state = security_state
        self._record_audit_event("SET_SECURITY_STATE", {"notes": security_state.notes})

    def add_simulated_process(self, process: ProcessTelemetrySnapshot) -> None:
        """Inject a simulated process into the telemetry table."""
        self._processes.append(process)

    def add_simulated_fs_event(self, event: FsEventSnapshot) -> None:
        """Inject a simulated filesystem event."""
        self._fs_events.append(event)

    def add_simulated_provenance(self, provenance: FileProvenanceSnapshot) -> None:
        """Register specific provenance metadata for a file path."""
        self._provenance_db[provenance.path] = provenance

    def simulate_error(self, method_name: str, error: Exception) -> None:
        """Configure a method to raise a specific simulated error."""
        self._simulated_errors[method_name] = error

    def clear_simulated_errors(self) -> None:
        """Clear all simulated error triggers."""
        self._simulated_errors.clear()

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _check_simulated_error(self, method_name: str) -> None:
        if method_name in self._simulated_errors:
            raise self._simulated_errors[method_name]

    def _record_audit_event(self, event_type: str, details: Dict[str, Any]) -> None:
        self._audit_log.append(
            {
                "timestamp_epoch_secs": time.time(),
                "event_type": event_type,
                "target_platform": self._target_id.value,
                "details": details,
            }
        )


class MockPlatformProfileFactory:
    """Factory creating standardized mock platform adapters for development and CI testing."""

    @classmethod
    def create_mock(cls, target_id: PlatformTargetId) -> MockPlatformAdapter:
        """Create a standard mock adapter for the given target ID."""
        return MockPlatformAdapter(target_id=target_id)

    @classmethod
    def create_macos_apple_silicon_mock(cls) -> MockPlatformAdapter:
        """Create a default Tier-1 Apple Silicon macOS mock adapter."""
        return MockPlatformAdapter(target_id=PlatformTargetId.MACOS_APPLE_SILICON)

    @classmethod
    def create_windows_11_mock(cls) -> MockPlatformAdapter:
        """Create a default Tier-2 Windows 11 x64 mock adapter."""
        return MockPlatformAdapter(target_id=PlatformTargetId.WINDOWS_11_X64)

    @classmethod
    def create_ubuntu_lts_mock(cls) -> MockPlatformAdapter:
        """Create a default Tier-2 Ubuntu LTS x86_64 mock adapter."""
        return MockPlatformAdapter(target_id=PlatformTargetId.UBUNTU_LTS_X64)

    @classmethod
    def create_nixos_vm_mock(cls) -> MockPlatformAdapter:
        """Create a default Tier-3 NixOS VM prototype mock adapter."""
        return MockPlatformAdapter(target_id=PlatformTargetId.NIXOS_VM)

    @classmethod
    def create_constrained_battery_mock(cls) -> MockPlatformAdapter:
        """Create an Apple Silicon mock adapter under low battery and disconnected AC power."""
        adapter = cls.create_macos_apple_silicon_mock()
        adapter.set_power_source(source="BATTERY", battery_pct=14.0, is_charging=False)
        return adapter

    @classmethod
    def create_critical_thermal_mock(cls) -> MockPlatformAdapter:
        """Create an Apple Silicon mock adapter under critical thermal pressure."""
        adapter = cls.create_macos_apple_silicon_mock()
        adapter.set_thermal_state("CRITICAL")
        return adapter

    @classmethod
    def create_insecure_host_mock(cls) -> MockPlatformAdapter:
        """Create a degraded macOS mock adapter with SIP and Gatekeeper disabled."""
        adapter = cls.create_macos_apple_silicon_mock()
        degraded_security = SecurityStateSnapshot(
            target_id=PlatformTargetId.MACOS_APPLE_SILICON,
            sip_enabled=False,
            gatekeeper_enabled=False,
            secure_boot_enabled=False,
            firewall_enabled=False,
            disk_encryption_enabled=False,
            lockdown_mode=False,
            notes=["WARNING: SIP Disabled", "WARNING: Gatekeeper Disabled"],
        )
        adapter.set_security_state(degraded_security)
        return adapter
