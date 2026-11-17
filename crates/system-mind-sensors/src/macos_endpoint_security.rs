//! macOS Darwin Endpoint Security integration feasibility and entitlement sensor collector.

use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EsClientResultCodeSnapshot {
    Success = 0,
    ErrInvalidArgument = 1,
    ErrInternal = 2,
    ErrNotEntitled = 3,
    ErrNotPermitted = 4,
    ErrNotPrivileged = 5,
    ErrTooManyClients = 6,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EsStatusSnapshot {
    AvailableEntitled,
    RestrictedMissingEntitlement,
    RestrictedNotRoot,
    RestrictedSipActive,
    UnavailablePlatform,
    MockActive,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EsEventTypeSnapshot {
    AuthExec,
    AuthOpen,
    NotifyExec,
    NotifyOpen,
    NotifyFork,
    NotifyExit,
    NotifyCreate,
    NotifyClose,
    NotifyUnlink,
    NotifyMmap,
    NotifySignal,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EsActionTypeSnapshot {
    Auth,
    Notify,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EsEntitlementCheckSnapshot {
    pub has_endpoint_security_entitlement: bool,
    pub is_root: bool,
    pub uid: u32,
    pub sip_enabled: bool,
    pub sip_status_raw: String,
    pub tcc_full_disk_access_probable: bool,
    pub framework_binary_present: bool,
    pub framework_path: String,
    pub entitlement_key: String,
    pub team_id: Option<String>,
    pub diagnostics: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EsEventSampleSnapshot {
    pub event_id: String,
    pub event_type: EsEventTypeSnapshot,
    pub action_type: EsActionTypeSnapshot,
    pub timestamp: String,
    pub process_pid: u32,
    pub process_ppid: u32,
    pub executable_path: String,
    pub target_path: Option<String>,
    pub cdhash: Option<String>,
    pub signing_id: Option<String>,
    pub team_id: Option<String>,
    pub is_platform_binary: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EsFeasibilityReportSnapshot {
    pub status: EsStatusSnapshot,
    pub result_code: EsClientResultCodeSnapshot,
    pub entitlement_check: EsEntitlementCheckSnapshot,
    pub supported_event_types: Vec<EsEventTypeSnapshot>,
    pub fallback_strategies: HashMap<String, String>,
    pub sample_events: Vec<EsEventSampleSnapshot>,
    pub timestamp: String,
    pub unavailable_telemetry: Vec<String>,
    pub host_platform: String,
    pub scan_proves_safe: bool,
    pub is_mock: bool,
}

impl EsFeasibilityReportSnapshot {
    pub fn is_operational(&self) -> bool {
        self.status == EsStatusSnapshot::AvailableEntitled && !self.is_mock
    }

    pub fn requires_escalation(&self) -> bool {
        matches!(
            self.status,
            EsStatusSnapshot::RestrictedNotRoot
                | EsStatusSnapshot::RestrictedMissingEntitlement
                | EsStatusSnapshot::RestrictedSipActive
        )
    }

    pub fn has_fallback(&self) -> bool {
        !self.fallback_strategies.is_empty()
    }

    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"status\":\"{:?}\",\"result_code\":{},\"operational\":{},\"requires_escalation\":{},\"fallback_count\":{},\"scan_proves_safe\":{},\"mock\":{}}}",
            self.status,
            self.result_code as u32,
            self.is_operational(),
            self.requires_escalation(),
            self.fallback_strategies.len(),
            self.scan_proves_safe,
            self.is_mock
        )
    }
}

pub trait MacOsEndpointSecurityCollector {
    fn collect(&self) -> Result<EsFeasibilityReportSnapshot, String>;
}

pub struct MockMacOsEndpointSecurityCollector {
    pub profile: String,
}

impl MockMacOsEndpointSecurityCollector {
    pub fn new(profile: &str) -> Self {
        Self {
            profile: profile.to_string(),
        }
    }
}

impl Default for MockMacOsEndpointSecurityCollector {
    fn default() -> Self {
        Self::new("restricted_companion")
    }
}

impl MacOsEndpointSecurityCollector for MockMacOsEndpointSecurityCollector {
    fn collect(&self) -> Result<EsFeasibilityReportSnapshot, String> {
        let mut fallbacks = HashMap::new();
        fallbacks.insert(
            "filesystem".to_string(),
            "Apple CoreServices FSEvents (MacFsEventsDetector)".to_string(),
        );
        fallbacks.insert(
            "process_lifecycle".to_string(),
            "Darwin sysctl / /bin/ps (MacProcessDetector)".to_string(),
        );

        if self.profile == "entitled_daemon" {
            let ent = EsEntitlementCheckSnapshot {
                has_endpoint_security_entitlement: true,
                is_root: true,
                uid: 0,
                sip_enabled: true,
                sip_status_raw: "System Integrity Protection status: enabled.".to_string(),
                tcc_full_disk_access_probable: true,
                framework_binary_present: true,
                framework_path: "/System/Library/Frameworks/EndpointSecurity.framework".to_string(),
                entitlement_key: "com.apple.developer.endpoint-security.client".to_string(),
                team_id: Some("EQHXZ8M8AV".to_string()),
                diagnostics: vec![
                    "Process UID: 0 (root privileged system daemon)".to_string(),
                    "Entitlement verified".to_string(),
                ],
            };
            let sample = EsEventSampleSnapshot {
                event_id: "ES-EV-001".to_string(),
                event_type: EsEventTypeSnapshot::NotifyExec,
                action_type: EsActionTypeSnapshot::Notify,
                timestamp: "2026-11-17T10:00:00Z".to_string(),
                process_pid: 1024,
                process_ppid: 1,
                executable_path: "/usr/bin/git".to_string(),
                target_path: None,
                cdhash: Some("0123456789abcdef0123456789abcdef01234567".to_string()),
                signing_id: Some("com.apple.git".to_string()),
                team_id: None,
                is_platform_binary: true,
            };
            return Ok(EsFeasibilityReportSnapshot {
                status: EsStatusSnapshot::AvailableEntitled,
                result_code: EsClientResultCodeSnapshot::Success,
                entitlement_check: ent,
                supported_event_types: vec![
                    EsEventTypeSnapshot::NotifyExec,
                    EsEventTypeSnapshot::NotifyOpen,
                    EsEventTypeSnapshot::NotifyFork,
                    EsEventTypeSnapshot::NotifyExit,
                    EsEventTypeSnapshot::NotifyCreate,
                ],
                fallback_strategies: fallbacks,
                sample_events: vec![sample],
                timestamp: "2026-11-17T10:00:00Z".to_string(),
                unavailable_telemetry: vec![],
                host_platform: "Darwin".to_string(),
                scan_proves_safe: false,
                is_mock: true,
            });
        }

        if self.profile == "unsupported_platform" {
            let ent = EsEntitlementCheckSnapshot {
                has_endpoint_security_entitlement: false,
                is_root: false,
                uid: 1000,
                sip_enabled: false,
                sip_status_raw: "Linux kernel".to_string(),
                tcc_full_disk_access_probable: false,
                framework_binary_present: false,
                framework_path: "None".to_string(),
                entitlement_key: "com.apple.developer.endpoint-security.client".to_string(),
                team_id: None,
                diagnostics: vec![
                    "EndpointSecurity unsupported on non-Darwin platforms".to_string()
                ],
            };
            return Ok(EsFeasibilityReportSnapshot {
                status: EsStatusSnapshot::UnavailablePlatform,
                result_code: EsClientResultCodeSnapshot::ErrInternal,
                entitlement_check: ent,
                supported_event_types: vec![],
                fallback_strategies: fallbacks,
                sample_events: vec![],
                timestamp: "2026-11-17T10:00:00Z".to_string(),
                unavailable_telemetry: vec!["apple_endpoint_security_framework".to_string()],
                host_platform: "Linux".to_string(),
                scan_proves_safe: false,
                is_mock: true,
            });
        }

        // Default: restricted_companion
        let ent = EsEntitlementCheckSnapshot {
            has_endpoint_security_entitlement: false,
            is_root: false,
            uid: 501,
            sip_enabled: true,
            sip_status_raw: "System Integrity Protection status: enabled.".to_string(),
            tcc_full_disk_access_probable: false,
            framework_binary_present: true,
            framework_path: "/System/Library/Frameworks/EndpointSecurity.framework".to_string(),
            entitlement_key: "com.apple.developer.endpoint-security.client".to_string(),
            team_id: None,
            diagnostics: vec![
                "Process UID: 501 (unprivileged companion agent)".to_string(),
                "Entitlement 'com.apple.developer.endpoint-security.client': Missing".to_string(),
            ],
        };
        Ok(EsFeasibilityReportSnapshot {
            status: EsStatusSnapshot::RestrictedNotRoot,
            result_code: EsClientResultCodeSnapshot::ErrNotPrivileged,
            entitlement_check: ent,
            supported_event_types: vec![
                EsEventTypeSnapshot::NotifyExec,
                EsEventTypeSnapshot::NotifyOpen,
                EsEventTypeSnapshot::NotifyFork,
                EsEventTypeSnapshot::NotifyExit,
            ],
            fallback_strategies: fallbacks,
            sample_events: vec![],
            timestamp: "2026-11-17T10:00:00Z".to_string(),
            unavailable_telemetry: vec![
                "kernel_auth_interception".to_string(),
                "realtime_es_event_stream".to_string(),
            ],
            host_platform: "Darwin".to_string(),
            scan_proves_safe: false,
            is_mock: true,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_restricted_companion_collector() {
        let collector = MockMacOsEndpointSecurityCollector::default();
        let report = collector.collect().expect("collection failed");
        assert_eq!(report.status, EsStatusSnapshot::RestrictedNotRoot);
        assert_eq!(
            report.result_code,
            EsClientResultCodeSnapshot::ErrNotPrivileged
        );
        assert!(!report.scan_proves_safe); // Mandatory charter invariant
        assert!(report.requires_escalation());
        assert!(!report.is_operational());
        assert!(report.has_fallback());
        let json = report.to_json_summary();
        assert!(json.contains("\"requires_escalation\":true"));
        assert!(json.contains("\"scan_proves_safe\":false"));
    }

    #[test]
    fn test_mock_entitled_daemon_collector() {
        let collector = MockMacOsEndpointSecurityCollector::new("entitled_daemon");
        let report = collector.collect().expect("collection failed");
        assert_eq!(report.status, EsStatusSnapshot::AvailableEntitled);
        assert_eq!(report.result_code, EsClientResultCodeSnapshot::Success);
        assert!(!report.scan_proves_safe);
        assert_eq!(report.sample_events.len(), 1);
        assert_eq!(report.sample_events[0].process_pid, 1024);
        assert!(report.has_fallback());
    }

    #[test]
    fn test_mock_unsupported_platform_collector() {
        let collector = MockMacOsEndpointSecurityCollector::new("unsupported_platform");
        let report = collector.collect().expect("collection failed");
        assert_eq!(report.status, EsStatusSnapshot::UnavailablePlatform);
        assert_eq!(report.host_platform, "Linux");
        assert!(!report.scan_proves_safe);
    }
}
