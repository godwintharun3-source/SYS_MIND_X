"""macOS system agent and read-only telemetry collection module for SYSTEM MIND X."""

from system_mind.macos.agent_service_detector import MacUserAgentServiceManager
from system_mind.macos.agent_service_models import (
    AgentServiceState,
    AgentServiceStatusReport,
    LaunchAgentConfig,
)
from system_mind.macos.app_detector import MacAppDetector
from system_mind.macos.app_models import (
    ApplicationCategory,
    MacAppInfo,
    MacAppInventoryReport,
)
from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.macos.battery_models import (
    BatteryChargingState,
    BatteryHealthCondition,
    MacBatteryHealthInfo,
    MacBatteryTelemetryReport,
    PowerSource,
)
from system_mind.macos.collector_health_manager import (
    CollectorHealthManager,
    CORE_COLLECTORS,
)
from system_mind.macos.collector_health_models import (
    CollectorHealthRecord,
    CollectorResult,
    CollectorStatus,
    CompanionHealthReport,
    PartialDataReason,
)
from system_mind.macos.cpu_detector import MacCpuHardwareDetector
from system_mind.macos.cpu_models import (
    CpuPerfLevelInfo,
    MacCpuHardwareInfo,
    MacCpuTelemetryReport,
)
from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.endpoint_security_detector import MacEndpointSecurityDetector
from system_mind.macos.endpoint_security_models import (
    EsActionType,
    EsClientResultCode,
    EsEntitlementCheck,
    EsEventSample,
    EsEventType,
    EsFeasibilityReport,
    EsStatus,
)
from system_mind.macos.fsevents_detector import MacFsEventsDetector
from system_mind.macos.fsevents_models import (
    FsEventFlag,
    FsEventNotification,
    FsEventSnapshotReport,
    FsEventStreamConfig,
    FsEventStreamState,
)
from system_mind.macos.gpu_detector import MacGpuDetector
from system_mind.macos.gpu_models import (
    DisplayConnectionType,
    GpuBusType,
    MacDisplayInfo,
    MacGpuInfo,
    MacGpuReport,
)
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import (
    InventorySection,
    MacOsInventoryRequest,
    MacOsInventoryResponse,
    MacOsInventorySummary,
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
from system_mind.macos.observation_engine import (
    BASE_COLLECTOR_CONFIDENCE,
    MacOsObservationEngine,
)
from system_mind.macos.observation_models import (
    CompanionObservationBatch,
    ConfidenceTier,
    ObservationConfidence,
    ObservedTelemetryEnvelope,
    SourceTimestamp,
    compute_telemetry_digest,
)
from system_mind.macos.privacy_filter import (
    KEY_VAULT_PATTERNS,
    PERSONAL_FOLDERS,
    SECRET_PATTERNS,
    MacPrivacyFilter,
)
from system_mind.macos.privacy_models import (
    PrivacyFilterAuditRecord,
    PrivacyRuleCategory,
    PrivacyScrubbingLevel,
    SanitizedTelemetryEnvelope,
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
from system_mind.macos.signature_detector import MacAppSignatureDetector
from system_mind.macos.signature_models import (
    MacAppSignatureInfo,
    MacAppSignatureReport,
    NotarizationStatus,
    SignatureStatus,
    SigningAuthorityType,
)
from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.storage_models import (
    FilesystemType,
    MacStorageReport,
    MacVolumeInfo,
    VolumeRole,
)
from system_mind.macos.swift_bridge import MacSwiftBridge
from system_mind.macos.swift_models import (
    FrontmostAppInfo,
    SwiftBridgeTelemetry,
    SwiftPermissionStatus,
    SwiftThermalState,
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
    "AgentServiceState",
    "AgentServiceStatusReport",
    "ApplicationCategory",
    "BASE_COLLECTOR_CONFIDENCE",
    "BatteryChargingState",
    "BatteryHealthCondition",
    "CollectorHealthManager",
    "CollectorHealthRecord",
    "CollectorResult",
    "CollectorStatus",
    "CompanionHealthReport",
    "CompanionObservationBatch",
    "ConfidenceTier",
    "CORE_COLLECTORS",
    "CpuPerfLevelInfo",
    "DisplayConnectionType",
    "EsActionType",
    "EsClientResultCode",
    "EsEntitlementCheck",
    "EsEventSample",
    "EsEventType",
    "EsFeasibilityReport",
    "EsStatus",
    "FilesystemType",
    "FrontmostAppInfo",
    "FsEventFlag",
    "FsEventNotification",
    "FsEventSnapshotReport",
    "FsEventStreamConfig",
    "FsEventStreamState",
    "GpuBusType",
    "InterfaceType",
    "InventorySection",
    "KEY_VAULT_PATTERNS",
    "LaunchAgentConfig",
    "LinkState",
    "LoginItemKind",
    "MacAppDetector",
    "MacAppInfo",
    "MacAppInventoryReport",
    "MacAppSignatureDetector",
    "MacAppSignatureInfo",
    "MacAppSignatureReport",
    "MacArchitecture",
    "MacBatteryDetector",
    "MacBatteryHealthInfo",
    "MacBatteryTelemetryReport",
    "MacCpuHardwareDetector",
    "MacCpuHardwareInfo",
    "MacCpuTelemetryReport",
    "MacDisplayInfo",
    "MacEndpointSecurityDetector",
    "MacFsEventsDetector",
    "MacGpuDetector",
    "MacGpuInfo",
    "MacGpuReport",
    "MacHostIdentity",
    "MacLaunchdService",
    "MacLoginItem",
    "MacOSIdentityDetector",
    "MacOSVersionInfo",
    "MacOsInventoryApi",
    "MacOsInventoryRequest",
    "MacOsInventoryResponse",
    "MacOsInventorySummary",
    "MacIpAddress",
    "MacMemoryBreakdown",
    "MacMemoryDetector",
    "MacMemoryTelemetryReport",
    "MacNetworkDetector",
    "MacNetworkInterface",
    "MacNetworkReport",
    "MacNetworkRoute",
    "MacOsObservationEngine",
    "MacPrivacyFilter",
    "MacProcessDetector",
    "MacProcessInfo",
    "MacProcessReport",
    "MacServicesDetector",
    "MacServicesReport",
    "MacStorageDetector",
    "MacStorageReport",
    "MacSwapUsage",
    "MacSwiftBridge",
    "MacTelemetryReport",
    "MacUsbController",
    "MacUsbDetector",
    "MacUsbDevice",
    "MacUsbReport",
    "MacUserAgentServiceManager",
    "MacVmPageStats",
    "MacVolumeInfo",
    "MemoryPressureLevel",
    "NotarizationStatus",
    "ObservationConfidence",
    "ObservedTelemetryEnvelope",
    "PERSONAL_FOLDERS",
    "PowerSource",
    "PrivacyFilterAuditRecord",
    "PrivacyRuleCategory",
    "PrivacyScrubbingLevel",
    "ProcessRole",
    "ProcessState",
    "SanitizedTelemetryEnvelope",
    "SECRET_PATTERNS",
    "ServiceDomain",
    "ServiceOwnership",
    "ServiceStatus",
    "SignatureStatus",
    "SigningAuthorityType",
    "SourceTimestamp",
    "SwiftBridgeTelemetry",
    "SwiftPermissionStatus",
    "SwiftThermalState",
    "UsbDeviceClass",
    "UsbSpeed",
    "VolumeRole",
]
