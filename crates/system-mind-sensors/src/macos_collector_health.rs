//! macOS Darwin telemetry collector health, timeout, and partial-data reporting sensor.

use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CollectorStatusSnapshot {
    Healthy,
    Degraded,
    TimedOut,
    Failed,
    Unsupported,
    CircuitBroken,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PartialDataReasonSnapshot {
    HardwareAbsent,
    PermissionDenied,
    Timeout,
    CommandError,
    PlatformUnsupported,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CollectorHealthRecordSnapshot {
    pub collector_id: String,
    pub status: CollectorStatusSnapshot,
    pub latency_ms: f64,
    pub timeout_seconds: f64,
    pub consecutive_failures: u32,
    pub last_success_timestamp: Option<String>,
    pub last_error: Option<String>,
    pub partial_data: bool,
    pub partial_reasons: Vec<PartialDataReasonSnapshot>,
    pub unavailable_fields: Vec<String>,
}

impl CollectorHealthRecordSnapshot {
    pub fn is_operational(&self) -> bool {
        matches!(
            self.status,
            CollectorStatusSnapshot::Healthy | CollectorStatusSnapshot::Degraded
        )
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct CompanionHealthReportSnapshot {
    pub timestamp: String,
    pub host_platform: String,
    pub total_collectors: usize,
    pub healthy_count: usize,
    pub degraded_count: usize,
    pub failed_count: usize,
    pub timed_out_count: usize,
    pub unsupported_count: usize,
    pub overall_status: CollectorStatusSnapshot,
    pub collectors: HashMap<String, CollectorHealthRecordSnapshot>,
    pub partial_data_present: bool,
    pub scan_proves_safe: bool,
    pub is_mock: bool,
}

impl CompanionHealthReportSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"overall_status\":\"{:?}\",\"total_collectors\":{},\"healthy\":{},\"degraded\":{},\"timed_out\":{},\"failed\":{},\"unsupported\":{},\"partial\":{},\"scan_proves_safe\":{},\"mock\":{}}}",
            self.overall_status,
            self.total_collectors,
            self.healthy_count,
            self.degraded_count,
            self.timed_out_count,
            self.failed_count,
            self.unsupported_count,
            self.partial_data_present,
            self.scan_proves_safe,
            self.is_mock
        )
    }
}

pub trait MacOsCollectorHealthTracker {
    fn collect_report(&self) -> Result<CompanionHealthReportSnapshot, String>;
}

pub struct MockMacOsCollectorHealthTracker {
    pub profile: String,
}

impl MockMacOsCollectorHealthTracker {
    pub fn new(profile: &str) -> Self {
        Self {
            profile: profile.to_string(),
        }
    }
}

impl Default for MockMacOsCollectorHealthTracker {
    fn default() -> Self {
        Self::new("healthy")
    }
}

pub const MOCK_CORE_COLLECTORS: [&str; 16] = [
    "identity",
    "cpu",
    "memory",
    "storage",
    "battery",
    "network",
    "gpu",
    "usb",
    "processes",
    "services",
    "apps",
    "signatures",
    "fsevents",
    "endpoint_security",
    "swift_bridge",
    "user_agent",
];

impl MacOsCollectorHealthTracker for MockMacOsCollectorHealthTracker {
    fn collect_report(&self) -> Result<CompanionHealthReportSnapshot, String> {
        let mut map = HashMap::new();
        let timestamp = "2026-11-17T11:45:00Z".to_string();

        match self.profile.as_str() {
            "degraded" => {
                for &c in &MOCK_CORE_COLLECTORS {
                    if c == "battery" {
                        map.insert(
                            c.to_string(),
                            CollectorHealthRecordSnapshot {
                                collector_id: c.to_string(),
                                status: CollectorStatusSnapshot::Degraded,
                                latency_ms: 12.4,
                                timeout_seconds: 2.0,
                                consecutive_failures: 0,
                                last_success_timestamp: Some(timestamp.clone()),
                                last_error: None,
                                partial_data: true,
                                partial_reasons: vec![PartialDataReasonSnapshot::HardwareAbsent],
                                unavailable_fields: vec!["no_battery_hardware_desktop".to_string()],
                            },
                        );
                    } else if c == "endpoint_security" {
                        map.insert(
                            c.to_string(),
                            CollectorHealthRecordSnapshot {
                                collector_id: c.to_string(),
                                status: CollectorStatusSnapshot::Degraded,
                                latency_ms: 8.1,
                                timeout_seconds: 2.0,
                                consecutive_failures: 0,
                                last_success_timestamp: Some(timestamp.clone()),
                                last_error: None,
                                partial_data: true,
                                partial_reasons: vec![PartialDataReasonSnapshot::PermissionDenied],
                                unavailable_fields: vec![
                                    "endpoint_security_unentitled_companion".to_string()
                                ],
                            },
                        );
                    } else {
                        map.insert(
                            c.to_string(),
                            CollectorHealthRecordSnapshot {
                                collector_id: c.to_string(),
                                status: CollectorStatusSnapshot::Healthy,
                                latency_ms: 15.0,
                                timeout_seconds: 2.0,
                                consecutive_failures: 0,
                                last_success_timestamp: Some(timestamp.clone()),
                                last_error: None,
                                partial_data: false,
                                partial_reasons: Vec::new(),
                                unavailable_fields: Vec::new(),
                            },
                        );
                    }
                }
                Ok(CompanionHealthReportSnapshot {
                    timestamp,
                    host_platform: "Darwin".to_string(),
                    total_collectors: 16,
                    healthy_count: 14,
                    degraded_count: 2,
                    failed_count: 0,
                    timed_out_count: 0,
                    unsupported_count: 0,
                    overall_status: CollectorStatusSnapshot::Degraded,
                    collectors: map,
                    partial_data_present: true,
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
            "timeout" => {
                for &c in &MOCK_CORE_COLLECTORS {
                    if c == "fsevents" || c == "user_agent" {
                        map.insert(
                            c.to_string(),
                            CollectorHealthRecordSnapshot {
                                collector_id: c.to_string(),
                                status: CollectorStatusSnapshot::TimedOut,
                                latency_ms: 2000.0,
                                timeout_seconds: 2.0,
                                consecutive_failures: 1,
                                last_success_timestamp: None,
                                last_error: Some(
                                    "Collector exceeded timeout budget of 2.00s".to_string(),
                                ),
                                partial_data: true,
                                partial_reasons: vec![PartialDataReasonSnapshot::Timeout],
                                unavailable_fields: vec![format!("{}_timeout", c)],
                            },
                        );
                    } else {
                        map.insert(
                            c.to_string(),
                            CollectorHealthRecordSnapshot {
                                collector_id: c.to_string(),
                                status: CollectorStatusSnapshot::Healthy,
                                latency_ms: 10.0,
                                timeout_seconds: 2.0,
                                consecutive_failures: 0,
                                last_success_timestamp: Some(timestamp.clone()),
                                last_error: None,
                                partial_data: false,
                                partial_reasons: Vec::new(),
                                unavailable_fields: Vec::new(),
                            },
                        );
                    }
                }
                Ok(CompanionHealthReportSnapshot {
                    timestamp,
                    host_platform: "Darwin".to_string(),
                    total_collectors: 16,
                    healthy_count: 14,
                    degraded_count: 0,
                    failed_count: 0,
                    timed_out_count: 2,
                    unsupported_count: 0,
                    overall_status: CollectorStatusSnapshot::Degraded,
                    collectors: map,
                    partial_data_present: true,
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
            "unsupported" => {
                for &c in &MOCK_CORE_COLLECTORS {
                    map.insert(
                        c.to_string(),
                        CollectorHealthRecordSnapshot {
                            collector_id: c.to_string(),
                            status: CollectorStatusSnapshot::Unsupported,
                            latency_ms: 0.5,
                            timeout_seconds: 2.0,
                            consecutive_failures: 0,
                            last_success_timestamp: None,
                            last_error: Some("Non-Darwin operating system".to_string()),
                            partial_data: true,
                            partial_reasons: vec![PartialDataReasonSnapshot::PlatformUnsupported],
                            unavailable_fields: vec![format!("{}_darwin_unsupported", c)],
                        },
                    );
                }
                Ok(CompanionHealthReportSnapshot {
                    timestamp,
                    host_platform: "Linux".to_string(),
                    total_collectors: 16,
                    healthy_count: 0,
                    degraded_count: 0,
                    failed_count: 0,
                    timed_out_count: 0,
                    unsupported_count: 16,
                    overall_status: CollectorStatusSnapshot::Unsupported,
                    collectors: map,
                    partial_data_present: true,
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
            _ => {
                // healthy
                for &c in &MOCK_CORE_COLLECTORS {
                    map.insert(
                        c.to_string(),
                        CollectorHealthRecordSnapshot {
                            collector_id: c.to_string(),
                            status: CollectorStatusSnapshot::Healthy,
                            latency_ms: 12.5,
                            timeout_seconds: 2.0,
                            consecutive_failures: 0,
                            last_success_timestamp: Some(timestamp.clone()),
                            last_error: None,
                            partial_data: false,
                            partial_reasons: Vec::new(),
                            unavailable_fields: Vec::new(),
                        },
                    );
                }
                Ok(CompanionHealthReportSnapshot {
                    timestamp,
                    host_platform: "Darwin".to_string(),
                    total_collectors: 16,
                    healthy_count: 16,
                    degraded_count: 0,
                    failed_count: 0,
                    timed_out_count: 0,
                    unsupported_count: 0,
                    overall_status: CollectorStatusSnapshot::Healthy,
                    collectors: map,
                    partial_data_present: false,
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_collector_health_healthy() {
        let tracker = MockMacOsCollectorHealthTracker::new("healthy");
        let report = tracker.collect_report().expect("health report collection");

        assert_eq!(report.overall_status, CollectorStatusSnapshot::Healthy);
        assert_eq!(report.total_collectors, 16);
        assert_eq!(report.healthy_count, 16);
        assert_eq!(report.degraded_count, 0);
        assert_eq!(report.failed_count, 0);
        assert_eq!(report.timed_out_count, 0);
        assert!(!report.partial_data_present);
        assert!(!report.scan_proves_safe); // INV-HEALTH-04
        assert!(report.is_mock);

        let cpu_record = report.collectors.get("cpu").expect("cpu collector record");
        assert_eq!(cpu_record.status, CollectorStatusSnapshot::Healthy);
        assert!(cpu_record.is_operational());
        assert!(!cpu_record.partial_data);
    }

    #[test]
    fn test_mock_collector_health_degraded() {
        let tracker = MockMacOsCollectorHealthTracker::new("degraded");
        let report = tracker.collect_report().expect("degraded health report");

        assert_eq!(report.overall_status, CollectorStatusSnapshot::Degraded);
        assert_eq!(report.degraded_count, 2);
        assert_eq!(report.healthy_count, 14);
        assert!(report.partial_data_present);

        let battery = report.collectors.get("battery").expect("battery record");
        assert_eq!(battery.status, CollectorStatusSnapshot::Degraded);
        assert!(battery.partial_data);
        assert_eq!(
            battery.partial_reasons,
            vec![PartialDataReasonSnapshot::HardwareAbsent]
        );
        assert!(battery.is_operational());
    }

    #[test]
    fn test_mock_collector_health_timeout() {
        let tracker = MockMacOsCollectorHealthTracker::new("timeout");
        let report = tracker.collect_report().expect("timeout health report");

        assert_eq!(report.overall_status, CollectorStatusSnapshot::Degraded);
        assert_eq!(report.timed_out_count, 2);

        let fsevents = report.collectors.get("fsevents").expect("fsevents record");
        assert_eq!(fsevents.status, CollectorStatusSnapshot::TimedOut);
        assert!(fsevents.partial_data);
        assert_eq!(fsevents.consecutive_failures, 1);
        assert!(!fsevents.is_operational());
    }

    #[test]
    fn test_mock_collector_health_unsupported() {
        let tracker = MockMacOsCollectorHealthTracker::new("unsupported");
        let report = tracker.collect_report().expect("unsupported report");

        assert_eq!(report.overall_status, CollectorStatusSnapshot::Unsupported);
        assert_eq!(report.unsupported_count, 16);
        assert_eq!(report.healthy_count, 0);
        assert_eq!(report.host_platform, "Linux");
    }

    #[test]
    fn test_scan_proves_safe_invariant() {
        let tracker = MockMacOsCollectorHealthTracker::default();
        let report = tracker.collect_report().unwrap();
        assert!(!report.scan_proves_safe);
    }

    #[test]
    fn test_json_summary_serialization() {
        let tracker = MockMacOsCollectorHealthTracker::new("healthy");
        let report = tracker.collect_report().unwrap();
        let summary = report.to_json_summary();

        assert!(summary.contains("\"overall_status\":\"Healthy\""));
        assert!(summary.contains("\"total_collectors\":16"));
        assert!(summary.contains("\"scan_proves_safe\":false"));
    }
}
