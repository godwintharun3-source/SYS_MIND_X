//! SYSTEM MIND X Sensors: Hardware sensor abstractions and telemetry collection.

pub mod macos_apps;
pub mod macos_battery;
pub mod macos_collector_health;
pub mod macos_cpu;
pub mod macos_endpoint_security;
pub mod macos_fsevents;
pub mod macos_gpu;
pub mod macos_identity;
pub mod macos_launchd;
pub mod macos_memory;
pub mod macos_network;
pub mod macos_process;
pub mod macos_signature;
pub mod macos_storage;
pub mod macos_swift_bridge;
pub mod macos_usb;
pub mod macos_user_agent;
pub mod telemetry;

pub use macos_apps::{
    AppOwnershipSnapshot, ApplicationCategorySnapshot, MacOsAppCollector,
    MacOsAppInventorySnapshot, MacOsAppItemSnapshot, MockMacOsAppCollector,
};
pub use macos_battery::{
    BatteryConditionState, MacOsBatteryCollector, MacOsBatterySnapshot, MockMacOsBatteryCollector,
    PowerSourceState,
};
pub use macos_collector_health::{
    CollectorHealthRecordSnapshot, CollectorStatusSnapshot, CompanionHealthReportSnapshot,
    MacOsCollectorHealthTracker, MockMacOsCollectorHealthTracker, PartialDataReasonSnapshot,
};
pub use macos_cpu::{MacOsCpuCollector, MacOsCpuSnapshot, MockMacOsCpuCollector};
pub use macos_endpoint_security::{
    EsActionTypeSnapshot, EsClientResultCodeSnapshot, EsEntitlementCheckSnapshot,
    EsEventSampleSnapshot, EsEventTypeSnapshot, EsFeasibilityReportSnapshot, EsStatusSnapshot,
    MacOsEndpointSecurityCollector, MockMacOsEndpointSecurityCollector,
};
pub use macos_fsevents::{
    FsEventFlagSnapshot, FsEventNotificationSnapshot, FsEventReportSnapshot,
    MacOsFsEventsCollector, MockMacOsFsEventsCollector,
};
pub use macos_gpu::{
    DisplayConnectionTypeState, GpuBusTypeState, MacOsDisplaySnapshot, MacOsGpuCollector,
    MacOsGpuInfoSnapshot, MacOsGpuSnapshot, MockMacOsGpuCollector,
};
pub use macos_identity::{
    MacOsIdentityCollector, MacOsIdentitySnapshot, MockMacOsIdentityCollector,
};
pub use macos_launchd::{
    LoginItemKindSnapshot, MacOsLaunchdItemSnapshot, MacOsLoginItemSnapshot,
    MacOsServicesCollector, MacOsServicesSnapshot, MockMacOsServicesCollector,
    ServiceDomainSnapshot, ServiceOwnershipSnapshot, ServiceStatusSnapshot,
};
pub use macos_memory::{
    MacOsMemoryCollector, MacOsMemorySnapshot, MemoryPressureState, MockMacOsMemoryCollector,
};
pub use macos_network::{
    InterfaceTypeState, LinkStatusState, MacOsInterfaceSnapshot, MacOsNetworkCollector,
    MacOsNetworkSnapshot, MockMacOsNetworkCollector,
};
pub use macos_process::{
    MacOsProcessCollector, MacOsProcessItemSnapshot, MacOsProcessSnapshot,
    MockMacOsProcessCollector, ProcessRoleSnapshot, ProcessStateSnapshot,
};
pub use macos_signature::{
    MacOsAppSignatureItemSnapshot, MacOsAppSignatureReportSnapshot, MacOsSignatureCollector,
    MockMacOsSignatureCollector, NotarizationStatusSnapshot, SignatureStatusSnapshot,
    SigningAuthorityTypeSnapshot,
};
pub use macos_storage::{
    MacOsStorageCollector, MacOsStorageSnapshot, MacOsVolumeSnapshot, MockMacOsStorageCollector,
};
pub use macos_swift_bridge::{
    FrontmostAppSnapshot, MacOsSwiftBridgeCollector, MockMacOsSwiftBridgeCollector,
    SwiftBridgeTelemetrySnapshot, SwiftPermissionStatusSnapshot, SwiftThermalStateSnapshot,
};
pub use macos_usb::{
    MacOsUsbCollector, MacOsUsbControllerSnapshot, MacOsUsbDeviceSnapshot, MacOsUsbSnapshot,
    MockMacOsUsbCollector, UsbDeviceClassState, UsbSpeedState,
};
pub use macos_user_agent::{
    AgentServiceStateSnapshot, AgentServiceStatusReportSnapshot, LaunchAgentConfigSnapshot,
    MacOsUserAgentCollector, MockMacOsUserAgentCollector,
};
pub use telemetry::{MockSensorAdapter, SensorAdapter, SensorSnapshot};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_sensor_collection() {
        let adapter = MockSensorAdapter::new();
        let snapshot = adapter.collect_snapshot();

        assert_eq!(adapter.platform_name(), "darwin_arm64_mock");
        assert!(snapshot.timestamp_epoch_secs > 0);
        assert!(snapshot.cpu_usage_pct >= 0.0);
        assert_eq!(snapshot.thermal_state, "NOMINAL");
        assert!(snapshot.os_platform.contains("macOS"));
    }
}
