"""macOS system agent and read-only telemetry collection module for SYSTEM MIND X."""

from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.macos.battery_models import (
    BatteryChargingState,
    BatteryHealthCondition,
    MacBatteryHealthInfo,
    MacBatteryTelemetryReport,
    PowerSource,
)
from system_mind.macos.cpu_detector import MacCpuHardwareDetector
from system_mind.macos.cpu_models import (
    CpuPerfLevelInfo,
    MacCpuHardwareInfo,
    MacCpuTelemetryReport,
)
from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.memory_detector import MacMemoryDetector
from system_mind.macos.memory_models import (
    MacMemoryBreakdown,
    MacMemoryTelemetryReport,
    MacSwapUsage,
    MacVmPageStats,
    MemoryPressureLevel,
)
from system_mind.macos.models import (
    MacArchitecture,
    MacHostIdentity,
    MacOSVersionInfo,
    MacTelemetryReport,
)
from system_mind.macos.network_detector import MacNetworkDetector
from system_mind.macos.network_models import (
    InterfaceType,
    LinkState,
    MacIpAddress,
    MacNetworkInterface,
    MacNetworkReport,
    MacNetworkRoute,
)
from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.storage_models import (
    FilesystemType,
    MacStorageReport,
    MacVolumeInfo,
    VolumeRole,
)

__all__ = [
    "BatteryChargingState",
    "BatteryHealthCondition",
    "CpuPerfLevelInfo",
    "FilesystemType",
    "InterfaceType",
    "LinkState",
    "MacArchitecture",
    "MacBatteryDetector",
    "MacBatteryHealthInfo",
    "MacBatteryTelemetryReport",
    "MacCpuHardwareDetector",
    "MacCpuHardwareInfo",
    "MacCpuTelemetryReport",
    "MacHostIdentity",
    "MacOSIdentityDetector",
    "MacOSVersionInfo",
    "MacIpAddress",
    "MacMemoryBreakdown",
    "MacMemoryDetector",
    "MacMemoryTelemetryReport",
    "MacNetworkDetector",
    "MacNetworkInterface",
    "MacNetworkReport",
    "MacNetworkRoute",
    "MacStorageDetector",
    "MacStorageReport",
    "MacSwapUsage",
    "MacTelemetryReport",
    "MacVmPageStats",
    "MacVolumeInfo",
    "MemoryPressureLevel",
    "PowerSource",
    "VolumeRole",
]
