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
from system_mind.macos.gpu_detector import MacGpuDetector
from system_mind.macos.gpu_models import (
    DisplayConnectionType,
    GpuBusType,
    MacDisplayInfo,
    MacGpuInfo,
    MacGpuReport,
)
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
from system_mind.macos.process_detector import MacProcessDetector
from system_mind.macos.process_models import (
    MacProcessInfo,
    MacProcessReport,
    ProcessRole,
    ProcessState,
)
from system_mind.macos.services_detector import MacServicesDetector
from system_mind.macos.services_models import (
    LoginItemKind,
    MacLaunchdService,
    MacLoginItem,
    MacServicesReport,
    ServiceDomain,
    ServiceOwnership,
    ServiceStatus,
)
from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.storage_models import (
    FilesystemType,
    MacStorageReport,
    MacVolumeInfo,
    VolumeRole,
)
from system_mind.macos.usb_detector import MacUsbDetector
from system_mind.macos.usb_models import (
    MacUsbController,
    MacUsbDevice,
    MacUsbReport,
    UsbDeviceClass,
    UsbSpeed,
)

__all__ = [
    "BatteryChargingState",
    "BatteryHealthCondition",
    "CpuPerfLevelInfo",
    "DisplayConnectionType",
    "FilesystemType",
    "GpuBusType",
    "InterfaceType",
    "LinkState",
    "LoginItemKind",
    "MacArchitecture",
    "MacBatteryDetector",
    "MacBatteryHealthInfo",
    "MacBatteryTelemetryReport",
    "MacCpuHardwareDetector",
    "MacCpuHardwareInfo",
    "MacCpuTelemetryReport",
    "MacDisplayInfo",
    "MacGpuDetector",
    "MacGpuInfo",
    "MacGpuReport",
    "MacHostIdentity",
    "MacLaunchdService",
    "MacLoginItem",
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
    "MacProcessDetector",
    "MacProcessInfo",
    "MacProcessReport",
    "MacServicesDetector",
    "MacServicesReport",
    "MacStorageDetector",
    "MacStorageReport",
    "MacSwapUsage",
    "MacTelemetryReport",
    "MacUsbController",
    "MacUsbDetector",
    "MacUsbDevice",
    "MacUsbReport",
    "MacVmPageStats",
    "MacVolumeInfo",
    "MemoryPressureLevel",
    "PowerSource",
    "ProcessRole",
    "ProcessState",
    "ServiceDomain",
    "ServiceOwnership",
    "ServiceStatus",
    "UsbDeviceClass",
    "UsbSpeed",
    "VolumeRole",
]
