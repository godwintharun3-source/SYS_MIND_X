//! macOS Swift native companion bridge sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SwiftThermalStateSnapshot {
    Nominal,
    Fair,
    Serious,
    Critical,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FrontmostAppSnapshot {
    pub name: String,
    pub bundle_id: String,
    pub pid: i32,
    pub path: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SwiftPermissionStatusSnapshot {
    pub accessibility_granted: bool,
    pub screen_recording_granted: bool,
    pub full_disk_access_granted: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SwiftBridgeTelemetrySnapshot {
    pub thermal_state: SwiftThermalStateSnapshot,
    pub frontmost_app: Option<FrontmostAppSnapshot>,
    pub permissions: SwiftPermissionStatusSnapshot,
    pub system_uptime_seconds: f64,
    pub console_user: String,
    pub screen_locked: bool,
    pub timestamp: String,
    pub host_platform: String,
    pub bridge_channel: String,
    pub scan_proves_safe: bool,
    pub unavailable_telemetry: Vec<String>,
    pub is_mock: bool,
}

impl SwiftBridgeTelemetrySnapshot {
    pub fn is_throttled(&self) -> bool {
        matches!(
            self.thermal_state,
            SwiftThermalStateSnapshot::Serious | SwiftThermalStateSnapshot::Critical
        )
    }

    pub fn is_operational(&self) -> bool {
        !self.is_mock && self.host_platform == "Darwin"
    }

    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"thermal_state\":\"{:?}\",\"uptime\":{:.1},\"throttled\":{},\"operational\":{},\"scan_proves_safe\":{},\"mock\":{}}}",
            self.thermal_state,
            self.system_uptime_seconds,
            self.is_throttled(),
            self.is_operational(),
            self.scan_proves_safe,
            self.is_mock
        )
    }
}

pub trait MacOsSwiftBridgeCollector {
    fn collect(&self) -> Result<SwiftBridgeTelemetrySnapshot, String>;
}

pub struct MockMacOsSwiftBridgeCollector {
    pub profile: String,
}

impl MockMacOsSwiftBridgeCollector {
    pub fn new(profile: &str) -> Self {
        Self {
            profile: profile.to_string(),
        }
    }
}

impl Default for MockMacOsSwiftBridgeCollector {
    fn default() -> Self {
        Self::new("nominal")
    }
}

impl MacOsSwiftBridgeCollector for MockMacOsSwiftBridgeCollector {
    fn collect(&self) -> Result<SwiftBridgeTelemetrySnapshot, String> {
        if self.profile == "throttled" {
            return Ok(SwiftBridgeTelemetrySnapshot {
                thermal_state: SwiftThermalStateSnapshot::Critical,
                frontmost_app: Some(FrontmostAppSnapshot {
                    name: "Final Cut Pro".to_string(),
                    bundle_id: "com.apple.FinalCut".to_string(),
                    pid: 8842,
                    path: "/Applications/Final Cut Pro.app".to_string(),
                }),
                permissions: SwiftPermissionStatusSnapshot {
                    accessibility_granted: true,
                    screen_recording_granted: true,
                    full_disk_access_granted: true,
                },
                system_uptime_seconds: 98765.4,
                console_user: "operator".to_string(),
                screen_locked: false,
                timestamp: "2026-11-17T11:00:00Z".to_string(),
                host_platform: "Darwin".to_string(),
                bridge_channel: "MOCK_THROTTLED".to_string(),
                scan_proves_safe: false,
                unavailable_telemetry: vec![],
                is_mock: true,
            });
        }

        if self.profile == "unsupported" {
            return Ok(SwiftBridgeTelemetrySnapshot {
                thermal_state: SwiftThermalStateSnapshot::Unknown,
                frontmost_app: None,
                permissions: SwiftPermissionStatusSnapshot {
                    accessibility_granted: false,
                    screen_recording_granted: false,
                    full_disk_access_granted: false,
                },
                system_uptime_seconds: 0.0,
                console_user: "unknown".to_string(),
                screen_locked: false,
                timestamp: "2026-11-17T11:00:00Z".to_string(),
                host_platform: "Linux".to_string(),
                bridge_channel: "UNSUPPORTED_PLATFORM".to_string(),
                scan_proves_safe: false,
                unavailable_telemetry: vec!["apple_frameworks_unsupported".to_string()],
                is_mock: true,
            });
        }

        // Default: nominal
        Ok(SwiftBridgeTelemetrySnapshot {
            thermal_state: SwiftThermalStateSnapshot::Nominal,
            frontmost_app: Some(FrontmostAppSnapshot {
                name: "Terminal".to_string(),
                bundle_id: "com.apple.Terminal".to_string(),
                pid: 4210,
                path: "/System/Applications/Utilities/Terminal.app".to_string(),
            }),
            permissions: SwiftPermissionStatusSnapshot {
                accessibility_granted: false,
                screen_recording_granted: false,
                full_disk_access_granted: true,
            },
            system_uptime_seconds: 12345.6,
            console_user: "developer".to_string(),
            screen_locked: false,
            timestamp: "2026-11-17T11:00:00Z".to_string(),
            host_platform: "Darwin".to_string(),
            bridge_channel: "MOCK_NOMINAL".to_string(),
            scan_proves_safe: false,
            unavailable_telemetry: vec![],
            is_mock: true,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_swift_bridge_nominal() {
        let collector = MockMacOsSwiftBridgeCollector::default();
        let telemetry = collector.collect().expect("collection failed");
        assert_eq!(telemetry.thermal_state, SwiftThermalStateSnapshot::Nominal);
        assert!(!telemetry.is_throttled());
        assert!(!telemetry.scan_proves_safe); // Non-negotiable charter invariant
        assert!(telemetry.frontmost_app.is_some());
        let app = telemetry.frontmost_app.as_ref().unwrap();
        assert_eq!(app.bundle_id, "com.apple.Terminal");
        let json = telemetry.to_json_summary();
        assert!(json.contains("\"thermal_state\":\"Nominal\""));
        assert!(json.contains("\"scan_proves_safe\":false"));
    }

    #[test]
    fn test_mock_swift_bridge_throttled() {
        let collector = MockMacOsSwiftBridgeCollector::new("throttled");
        let telemetry = collector.collect().expect("collection failed");
        assert_eq!(telemetry.thermal_state, SwiftThermalStateSnapshot::Critical);
        assert!(telemetry.is_throttled());
        assert!(!telemetry.scan_proves_safe);
        assert_eq!(telemetry.console_user, "operator");
    }

    #[test]
    fn test_mock_swift_bridge_unsupported() {
        let collector = MockMacOsSwiftBridgeCollector::new("unsupported");
        let telemetry = collector.collect().expect("collection failed");
        assert_eq!(telemetry.thermal_state, SwiftThermalStateSnapshot::Unknown);
        assert_eq!(telemetry.host_platform, "Linux");
        assert!(!telemetry.scan_proves_safe);
        assert!(!telemetry.is_operational());
    }
}
