//! Sensor abstractions and non-privileged telemetry collectors.

use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq)]
pub struct SensorSnapshot {
    pub timestamp_epoch_secs: u64,
    pub cpu_usage_pct: f32,
    pub memory_rss_bytes: u64,
    pub disk_available_bytes: u64,
    pub thermal_state: String,
    pub os_platform: String,
}

pub trait SensorAdapter: Send + Sync {
    fn collect_snapshot(&self) -> SensorSnapshot;
    fn platform_name(&self) -> &'static str;
}

/// Safe mock sensor adapter simulating macOS Darwin arm64 platform telemetry.
#[derive(Debug, Default)]
pub struct MockSensorAdapter {
    pub simulated_cpu_pct: f32,
    pub simulated_rss_bytes: u64,
    pub simulated_disk_bytes: u64,
}

impl MockSensorAdapter {
    pub fn new() -> Self {
        Self {
            simulated_cpu_pct: 12.5,
            simulated_rss_bytes: 42_000_000, // 42MB
            simulated_disk_bytes: 120_000_000_000, // 120GB
        }
    }
}

impl SensorAdapter for MockSensorAdapter {
    fn collect_snapshot(&self) -> SensorSnapshot {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        SensorSnapshot {
            timestamp_epoch_secs: now,
            cpu_usage_pct: self.simulated_cpu_pct,
            memory_rss_bytes: self.simulated_rss_bytes,
            disk_available_bytes: self.simulated_disk_bytes,
            thermal_state: "NOMINAL".to_string(),
            os_platform: "macOS (Apple Silicon M1, Darwin 27.0.0)".to_string(),
        }
    }

    fn platform_name(&self) -> &'static str {
        "darwin_arm64_mock"
    }
}
