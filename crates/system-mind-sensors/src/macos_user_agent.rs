//! macOS Darwin least-privilege user agent launchd service sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentServiceStateSnapshot {
    InstalledActive,
    InstalledInactive,
    NotInstalled,
    UnavailablePlatform,
    MockActive,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LaunchAgentConfigSnapshot {
    pub label: String,
    pub program_arguments: Vec<String>,
    pub run_at_load: bool,
    pub keep_alive: bool,
    pub limit_load_to_session_type: Vec<String>,
    pub standard_out_path: String,
    pub standard_error_path: String,
    pub process_type: String,
    pub nice: i32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct AgentServiceStatusReportSnapshot {
    pub label: String,
    pub domain: String,
    pub state: AgentServiceStateSnapshot,
    pub status: String,
    pub pid: Option<u32>,
    pub last_exit_code: Option<i32>,
    pub plist_path: String,
    pub is_root: bool,
    pub uid: u32,
    pub console_user: String,
    pub config: LaunchAgentConfigSnapshot,
    pub timestamp: String,
    pub host_platform: String,
    pub scan_proves_safe: bool,
    pub unavailable_telemetry: Vec<String>,
    pub is_mock: bool,
}

impl AgentServiceStatusReportSnapshot {
    pub fn is_least_privilege(&self) -> bool {
        !self.is_root && self.uid != 0 && self.domain == "USER_AGENT"
    }

    pub fn is_running(&self) -> bool {
        self.state == AgentServiceStateSnapshot::InstalledActive && self.pid.is_some()
    }

    pub fn is_installed(&self) -> bool {
        matches!(
            self.state,
            AgentServiceStateSnapshot::InstalledActive
                | AgentServiceStateSnapshot::InstalledInactive
        )
    }

    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"label\":\"{}\",\"state\":\"{:?}\",\"pid\":{:?},\"least_privilege\":{},\"running\":{},\"scan_proves_safe\":{},\"mock\":{}}}",
            self.label,
            self.state,
            self.pid,
            self.is_least_privilege(),
            self.is_running(),
            self.scan_proves_safe,
            self.is_mock
        )
    }
}

pub trait MacOsUserAgentCollector {
    fn collect(&self) -> Result<AgentServiceStatusReportSnapshot, String>;
}

pub struct MockMacOsUserAgentCollector {
    pub profile: String,
}

impl MockMacOsUserAgentCollector {
    pub fn new(profile: &str) -> Self {
        Self {
            profile: profile.to_string(),
        }
    }
}

impl Default for MockMacOsUserAgentCollector {
    fn default() -> Self {
        Self::new("running")
    }
}

impl MacOsUserAgentCollector for MockMacOsUserAgentCollector {
    fn collect(&self) -> Result<AgentServiceStatusReportSnapshot, String> {
        let config = LaunchAgentConfigSnapshot {
            label: "com.systemmind.useragent".to_string(),
            program_arguments: vec![
                "/usr/local/bin/system-mind-companion".to_string(),
                "--daemon".to_string(),
            ],
            run_at_load: false,
            keep_alive: true,
            limit_load_to_session_type: vec!["Aqua".to_string()],
            standard_out_path: "~/Library/Logs/system-mind/com.systemmind.useragent.stdout.log"
                .to_string(),
            standard_error_path: "~/Library/Logs/system-mind/com.systemmind.useragent.stderr.log"
                .to_string(),
            process_type: "Background".to_string(),
            nice: 10,
        };

        if self.profile == "stopped" {
            return Ok(AgentServiceStatusReportSnapshot {
                label: "com.systemmind.useragent".to_string(),
                domain: "USER_AGENT".to_string(),
                state: AgentServiceStateSnapshot::InstalledInactive,
                status: "LOADED_WAITING".to_string(),
                pid: None,
                last_exit_code: Some(0),
                plist_path: "~/Library/LaunchAgents/com.systemmind.useragent.plist".to_string(),
                is_root: false,
                uid: 501,
                console_user: "developer".to_string(),
                config,
                timestamp: "2026-11-17T11:30:00Z".to_string(),
                host_platform: "Darwin".to_string(),
                scan_proves_safe: false,
                unavailable_telemetry: vec!["process_inactive".to_string()],
                is_mock: true,
            });
        }

        if self.profile == "uninstalled" {
            return Ok(AgentServiceStatusReportSnapshot {
                label: "com.systemmind.useragent".to_string(),
                domain: "USER_AGENT".to_string(),
                state: AgentServiceStateSnapshot::NotInstalled,
                status: "UNKNOWN".to_string(),
                pid: None,
                last_exit_code: None,
                plist_path: "~/Library/LaunchAgents/com.systemmind.useragent.plist".to_string(),
                is_root: false,
                uid: 501,
                console_user: "developer".to_string(),
                config,
                timestamp: "2026-11-17T11:30:00Z".to_string(),
                host_platform: "Darwin".to_string(),
                scan_proves_safe: false,
                unavailable_telemetry: vec!["service_not_installed".to_string()],
                is_mock: true,
            });
        }

        if self.profile == "unsupported" {
            return Ok(AgentServiceStatusReportSnapshot {
                label: "com.systemmind.useragent".to_string(),
                domain: "UNKNOWN".to_string(),
                state: AgentServiceStateSnapshot::UnavailablePlatform,
                status: "UNKNOWN".to_string(),
                pid: None,
                last_exit_code: None,
                plist_path: "None".to_string(),
                is_root: false,
                uid: 1000,
                console_user: "linuxuser".to_string(),
                config,
                timestamp: "2026-11-17T11:30:00Z".to_string(),
                host_platform: "Linux".to_string(),
                scan_proves_safe: false,
                unavailable_telemetry: vec!["apple_launchd_unsupported".to_string()],
                is_mock: true,
            });
        }

        // Default: running
        Ok(AgentServiceStatusReportSnapshot {
            label: "com.systemmind.useragent".to_string(),
            domain: "USER_AGENT".to_string(),
            state: AgentServiceStateSnapshot::InstalledActive,
            status: "RUNNING".to_string(),
            pid: Some(4120),
            last_exit_code: Some(0),
            plist_path: "~/Library/LaunchAgents/com.systemmind.useragent.plist".to_string(),
            is_root: false,
            uid: 501,
            console_user: "developer".to_string(),
            config,
            timestamp: "2026-11-17T11:30:00Z".to_string(),
            host_platform: "Darwin".to_string(),
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
    fn test_mock_user_agent_running() {
        let collector = MockMacOsUserAgentCollector::default();
        let report = collector.collect().expect("collection failed");
        assert_eq!(report.state, AgentServiceStateSnapshot::InstalledActive);
        assert!(report.is_least_privilege());
        assert!(report.is_running());
        assert!(report.is_installed());
        assert!(!report.scan_proves_safe); // Mandatory charter invariant
        assert_eq!(report.pid, Some(4120));
        let json = report.to_json_summary();
        assert!(json.contains("\"least_privilege\":true"));
        assert!(json.contains("\"scan_proves_safe\":false"));
    }

    #[test]
    fn test_mock_user_agent_stopped() {
        let collector = MockMacOsUserAgentCollector::new("stopped");
        let report = collector.collect().expect("collection failed");
        assert_eq!(report.state, AgentServiceStateSnapshot::InstalledInactive);
        assert!(report.is_least_privilege());
        assert!(!report.is_running());
        assert!(report.is_installed());
        assert!(!report.scan_proves_safe);
        assert_eq!(report.pid, None);
    }

    #[test]
    fn test_mock_user_agent_uninstalled() {
        let collector = MockMacOsUserAgentCollector::new("uninstalled");
        let report = collector.collect().expect("collection failed");
        assert_eq!(report.state, AgentServiceStateSnapshot::NotInstalled);
        assert!(!report.is_installed());
        assert!(!report.is_running());
        assert!(!report.scan_proves_safe);
    }

    #[test]
    fn test_mock_user_agent_unsupported() {
        let collector = MockMacOsUserAgentCollector::new("unsupported");
        let report = collector.collect().expect("collection failed");
        assert_eq!(report.state, AgentServiceStateSnapshot::UnavailablePlatform);
        assert_eq!(report.host_platform, "Linux");
        assert!(!report.is_least_privilege()); // Non-user_agent domain
        assert!(!report.scan_proves_safe);
    }
}
