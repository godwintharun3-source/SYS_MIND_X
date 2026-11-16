//! macOS Darwin launchd services and login-item inventory telemetry sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceDomainSnapshot {
    SystemDaemon,
    SystemAgent,
    GlobalDaemon,
    GlobalAgent,
    UserAgent,
    RuntimeLoaded,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceStatusSnapshot {
    Running,
    LoadedWaiting,
    LoadedFailed,
    DefinitionOnly,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceOwnershipSnapshot {
    SystemManaged,
    VendorManaged,
    UserManaged,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LoginItemKindSnapshot {
    Application,
    Service,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsLaunchdItemSnapshot {
    pub label: String,
    pub pid: Option<u32>,
    pub last_exit_code: Option<i32>,
    pub domain: ServiceDomainSnapshot,
    pub status: ServiceStatusSnapshot,
    pub ownership: ServiceOwnershipSnapshot,
    pub plist_path: Option<String>,
    pub program: Option<String>,
    pub run_at_load: Option<bool>,
    pub keep_alive: Option<bool>,
    pub is_apple: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsLoginItemSnapshot {
    pub name: String,
    pub path: Option<String>,
    pub hidden: bool,
    pub kind: LoginItemKindSnapshot,
    pub ownership: ServiceOwnershipSnapshot,
    pub is_apple: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsServicesSnapshot {
    pub services: Vec<MacOsLaunchdItemSnapshot>,
    pub login_items: Vec<MacOsLoginItemSnapshot>,
    pub total_services_count: usize,
    pub running_services_count: usize,
    pub loaded_services_count: usize,
    pub system_managed_count: usize,
    pub vendor_managed_count: usize,
    pub user_managed_count: usize,
    pub total_login_items_count: usize,
    pub is_mock: bool,
}

impl MacOsServicesSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"total_services\":{},\"running\":{},\"loaded\":{},\"system_managed\":{},\"vendor_managed\":{},\"user_managed\":{},\"login_items\":{},\"mock\":{}}}",
            self.total_services_count,
            self.running_services_count,
            self.loaded_services_count,
            self.system_managed_count,
            self.vendor_managed_count,
            self.user_managed_count,
            self.total_login_items_count,
            self.is_mock
        )
    }
}

pub trait MacOsServicesCollector: Send + Sync {
    fn collect_services(&self) -> MacOsServicesSnapshot;
}

/// Safe mock collector simulating macOS launchd jobs and login items.
#[derive(Debug, Clone)]
pub struct MockMacOsServicesCollector {
    pub services: Vec<MacOsLaunchdItemSnapshot>,
    pub login_items: Vec<MacOsLoginItemSnapshot>,
    pub is_mock: bool,
}

impl MockMacOsServicesCollector {
    pub fn new_apple_silicon() -> Self {
        let finder = MacOsLaunchdItemSnapshot {
            label: "com.apple.Finder".to_string(),
            pid: Some(653),
            last_exit_code: Some(0),
            domain: ServiceDomainSnapshot::SystemAgent,
            status: ServiceStatusSnapshot::Running,
            ownership: ServiceOwnershipSnapshot::SystemManaged,
            plist_path: Some("/System/Library/LaunchAgents/com.apple.Finder.plist".to_string()),
            program: Some(
                "/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder".to_string(),
            ),
            run_at_load: Some(true),
            keep_alive: Some(true),
            is_apple: true,
        };

        let homed = MacOsLaunchdItemSnapshot {
            label: "com.apple.homed".to_string(),
            pid: Some(775),
            last_exit_code: Some(0),
            domain: ServiceDomainSnapshot::SystemAgent,
            status: ServiceStatusSnapshot::Running,
            ownership: ServiceOwnershipSnapshot::SystemManaged,
            plist_path: Some("/System/Library/LaunchAgents/com.apple.homed.plist".to_string()),
            program: Some(
                "/System/Library/PrivateFrameworks/HomeKitDaemon.framework/Support/homed"
                    .to_string(),
            ),
            run_at_load: Some(true),
            keep_alive: Some(true),
            is_apple: true,
        };

        let safari_agent = MacOsLaunchdItemSnapshot {
            label: "com.apple.SafariHistoryServiceAgent".to_string(),
            pid: None,
            last_exit_code: Some(0),
            domain: ServiceDomainSnapshot::SystemAgent,
            status: ServiceStatusSnapshot::LoadedWaiting,
            ownership: ServiceOwnershipSnapshot::SystemManaged,
            plist_path: Some("/System/Library/LaunchAgents/com.apple.SafariHistoryServiceAgent.plist".to_string()),
            program: Some("/System/Library/PrivateFrameworks/SafariShared.framework/Versions/A/XPCServices/SafariHistoryServiceAgent.xpc/Contents/MacOS/SafariHistoryServiceAgent".to_string()),
            run_at_load: Some(false),
            keep_alive: Some(false),
            is_apple: true,
        };

        let warp = MacOsLaunchdItemSnapshot {
            label: "com.cloudflare.1dot1dot1dot1.macos.warp.daemon".to_string(),
            pid: Some(412),
            last_exit_code: Some(0),
            domain: ServiceDomainSnapshot::GlobalDaemon,
            status: ServiceStatusSnapshot::Running,
            ownership: ServiceOwnershipSnapshot::VendorManaged,
            plist_path: Some(
                "/Library/LaunchDaemons/com.cloudflare.1dot1dot1dot1.macos.warp.daemon.plist"
                    .to_string(),
            ),
            program: Some(
                "/Applications/Cloudflare WARP.app/Contents/Resources/warp-svc".to_string(),
            ),
            run_at_load: Some(true),
            keep_alive: Some(true),
            is_apple: false,
        };

        let docker_socket = MacOsLaunchdItemSnapshot {
            label: "com.docker.socket".to_string(),
            pid: None,
            last_exit_code: Some(0),
            domain: ServiceDomainSnapshot::GlobalDaemon,
            status: ServiceStatusSnapshot::LoadedWaiting,
            ownership: ServiceOwnershipSnapshot::VendorManaged,
            plist_path: Some("/Library/LaunchDaemons/com.docker.socket.plist".to_string()),
            program: Some(
                "/Applications/Docker.app/Contents/Resources/socket/com.docker.socket".to_string(),
            ),
            run_at_load: Some(false),
            keep_alive: Some(false),
            is_apple: false,
        };

        let mysql = MacOsLaunchdItemSnapshot {
            label: "homebrew.mxcl.mysql".to_string(),
            pid: Some(892),
            last_exit_code: Some(0),
            domain: ServiceDomainSnapshot::UserAgent,
            status: ServiceStatusSnapshot::Running,
            ownership: ServiceOwnershipSnapshot::UserManaged,
            plist_path: Some(
                "/Users/mockuser/Library/LaunchAgents/homebrew.mxcl.mysql.plist".to_string(),
            ),
            program: Some("/opt/homebrew/opt/mysql/bin/mysqld_safe".to_string()),
            run_at_load: Some(true),
            keep_alive: Some(true),
            is_apple: false,
        };

        let gemini_launcher = MacOsLoginItemSnapshot {
            name: "GeminiAppLauncher".to_string(),
            path: Some("/Applications/GeminiAppLauncher.app".to_string()),
            hidden: false,
            kind: LoginItemKindSnapshot::Application,
            ownership: ServiceOwnershipSnapshot::UserManaged,
            is_apple: false,
        };

        let docker_desktop = MacOsLoginItemSnapshot {
            name: "Docker Desktop".to_string(),
            path: Some("/Applications/Docker.app".to_string()),
            hidden: true,
            kind: LoginItemKindSnapshot::Application,
            ownership: ServiceOwnershipSnapshot::UserManaged,
            is_apple: false,
        };

        Self {
            services: vec![finder, homed, safari_agent, warp, docker_socket, mysql],
            login_items: vec![gemini_launcher, docker_desktop],
            is_mock: true,
        }
    }
}

impl MacOsServicesCollector for MockMacOsServicesCollector {
    fn collect_services(&self) -> MacOsServicesSnapshot {
        let running_count = self
            .services
            .iter()
            .filter(|s| s.status == ServiceStatusSnapshot::Running && s.pid.is_some())
            .count();

        let loaded_count = self
            .services
            .iter()
            .filter(|s| s.status != ServiceStatusSnapshot::DefinitionOnly)
            .count();

        let system_count = self
            .services
            .iter()
            .filter(|s| s.ownership == ServiceOwnershipSnapshot::SystemManaged)
            .count();

        let vendor_count = self
            .services
            .iter()
            .filter(|s| s.ownership == ServiceOwnershipSnapshot::VendorManaged)
            .count();

        let user_count = self
            .services
            .iter()
            .filter(|s| s.ownership == ServiceOwnershipSnapshot::UserManaged)
            .count();

        MacOsServicesSnapshot {
            total_services_count: self.services.len(),
            running_services_count: running_count,
            loaded_services_count: loaded_count,
            system_managed_count: system_count,
            vendor_managed_count: vendor_count,
            user_managed_count: user_count,
            total_login_items_count: self.login_items.len(),
            services: self.services.clone(),
            login_items: self.login_items.clone(),
            is_mock: self.is_mock,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_services_collector_apple_silicon() {
        let collector = MockMacOsServicesCollector::new_apple_silicon();
        let snapshot = collector.collect_services();

        assert_eq!(snapshot.total_services_count, 6);
        assert_eq!(snapshot.running_services_count, 4);
        assert_eq!(snapshot.loaded_services_count, 6);
        assert_eq!(snapshot.system_managed_count, 3);
        assert_eq!(snapshot.vendor_managed_count, 2);
        assert_eq!(snapshot.user_managed_count, 1);
        assert_eq!(snapshot.total_login_items_count, 2);
        assert!(snapshot.is_mock);

        let finder = snapshot
            .services
            .iter()
            .find(|s| s.label == "com.apple.Finder")
            .expect("Finder must exist");
        assert_eq!(finder.pid, Some(653));
        assert_eq!(finder.domain, ServiceDomainSnapshot::SystemAgent);
        assert_eq!(finder.status, ServiceStatusSnapshot::Running);
        assert!(finder.is_apple);
    }

    #[test]
    fn test_json_summary_serialization() {
        let collector = MockMacOsServicesCollector::new_apple_silicon();
        let snapshot = collector.collect_services();
        let summary = snapshot.to_json_summary();

        assert!(summary.contains("\"total_services\":6"));
        assert!(summary.contains("\"running\":4"));
        assert!(summary.contains("\"system_managed\":3"));
        assert!(summary.contains("\"vendor_managed\":2"));
        assert!(summary.contains("\"user_managed\":1"));
        assert!(summary.contains("\"login_items\":2"));
        assert!(summary.contains("\"mock\":true"));
    }

    #[test]
    fn test_services_aggregation() {
        let collector = MockMacOsServicesCollector::new_apple_silicon();
        let snapshot = collector.collect_services();

        let running_labels: Vec<&str> = snapshot
            .services
            .iter()
            .filter(|s| s.status == ServiceStatusSnapshot::Running)
            .map(|s| s.label.as_str())
            .collect();

        assert!(running_labels.contains(&"com.apple.Finder"));
        assert!(running_labels.contains(&"com.apple.homed"));
        assert!(running_labels.contains(&"com.cloudflare.1dot1dot1dot1.macos.warp.daemon"));
        assert!(running_labels.contains(&"homebrew.mxcl.mysql"));

        let login_names: Vec<&str> = snapshot
            .login_items
            .iter()
            .map(|l| l.name.as_str())
            .collect();
        assert!(login_names.contains(&"GeminiAppLauncher"));
        assert!(login_names.contains(&"Docker Desktop"));
    }
}
