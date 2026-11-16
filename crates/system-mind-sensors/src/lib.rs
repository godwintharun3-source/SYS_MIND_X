//! SYSTEM MIND X Sensors: Hardware sensor abstractions and telemetry collection.

pub mod macos_cpu;
pub mod macos_identity;
pub mod macos_memory;
pub mod telemetry;

pub use macos_cpu::{MacOsCpuCollector, MacOsCpuSnapshot, MockMacOsCpuCollector};
pub use macos_identity::{
    MacOsIdentityCollector, MacOsIdentitySnapshot, MockMacOsIdentityCollector,
};
pub use macos_memory::{
    MacOsMemoryCollector, MacOsMemorySnapshot, MemoryPressureState, MockMacOsMemoryCollector,
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
