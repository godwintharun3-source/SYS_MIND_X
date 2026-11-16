//! macOS Darwin process inventory and resource telemetry sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProcessStateSnapshot {
    Running,
    Sleeping,
    Stopped,
    Zombie,
    Uninterruptible,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProcessRoleSnapshot {
    SystemCore,
    UserApp,
    DaemonService,
    DeveloperTool,
    Other,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsProcessItemSnapshot {
    pub pid: u32,
    pub ppid: u32,
    pub uid: u32,
    pub user: String,
    pub name: String,
    pub command_path: String,
    pub cpu_pct: f32,
    pub mem_pct: f32,
    pub rss_bytes: u64,
    pub vsz_bytes: u64,
    pub state: ProcessStateSnapshot,
    pub role: ProcessRoleSnapshot,
    pub is_system_core: bool,
    pub is_user_app: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsProcessSnapshot {
    pub processes: Vec<MacOsProcessItemSnapshot>,
    pub total_process_count: usize,
    pub running_count: usize,
    pub sleeping_count: usize,
    pub zombie_count: usize,
    pub system_core_count: usize,
    pub user_app_count: usize,
    pub total_rss_bytes: u64,
    pub is_mock: bool,
}

impl MacOsProcessSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"total_processes\":{},\"running\":{},\"sleeping\":{},\"zombie\":{},\"system_core\":{},\"user_app\":{},\"total_rss_bytes\":{},\"mock\":{}}}",
            self.total_process_count,
            self.running_count,
            self.sleeping_count,
            self.zombie_count,
            self.system_core_count,
            self.user_app_count,
            self.total_rss_bytes,
            self.is_mock
        )
    }
}

pub trait MacOsProcessCollector: Send + Sync {
    fn collect_processes(&self) -> MacOsProcessSnapshot;
}

/// Safe mock collector simulating macOS process table and resource consumption.
#[derive(Debug, Clone)]
pub struct MockMacOsProcessCollector {
    pub processes: Vec<MacOsProcessItemSnapshot>,
    pub is_mock: bool,
}

impl MockMacOsProcessCollector {
    pub fn new_apple_silicon() -> Self {
        let launchd = MacOsProcessItemSnapshot {
            pid: 1,
            ppid: 0,
            uid: 0,
            user: "root".to_string(),
            name: "launchd".to_string(),
            command_path: "/sbin/launchd".to_string(),
            cpu_pct: 0.2,
            mem_pct: 0.1,
            rss_bytes: 16 * 1024 * 1024,
            vsz_bytes: 480 * 1024 * 1024,
            state: ProcessStateSnapshot::Sleeping,
            role: ProcessRoleSnapshot::SystemCore,
            is_system_core: true,
            is_user_app: false,
        };

        let logd = MacOsProcessItemSnapshot {
            pid: 338,
            ppid: 1,
            uid: 0,
            user: "root".to_string(),
            name: "logd".to_string(),
            command_path: "/usr/libexec/logd".to_string(),
            cpu_pct: 0.4,
            mem_pct: 0.1,
            rss_bytes: 12 * 1024 * 1024,
            vsz_bytes: 488 * 1024 * 1024,
            state: ProcessStateSnapshot::Sleeping,
            role: ProcessRoleSnapshot::SystemCore,
            is_system_core: true,
            is_user_app: false,
        };

        let chrome = MacOsProcessItemSnapshot {
            pid: 1200,
            ppid: 1,
            uid: 501,
            user: "tharungodwin".to_string(),
            name: "Google Chrome".to_string(),
            command_path: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                .to_string(),
            cpu_pct: 14.5,
            mem_pct: 2.8,
            rss_bytes: 450 * 1024 * 1024,
            vsz_bytes: 3500 * 1024 * 1024,
            state: ProcessStateSnapshot::Running,
            role: ProcessRoleSnapshot::UserApp,
            is_system_core: false,
            is_user_app: true,
        };

        let python_proc = MacOsProcessItemSnapshot {
            pid: 1500,
            ppid: 1,
            uid: 501,
            user: "tharungodwin".to_string(),
            name: "python3".to_string(),
            command_path: "/usr/local/bin/python3".to_string(),
            cpu_pct: 8.0,
            mem_pct: 0.5,
            rss_bytes: 85 * 1024 * 1024,
            vsz_bytes: 600 * 1024 * 1024,
            state: ProcessStateSnapshot::Running,
            role: ProcessRoleSnapshot::DeveloperTool,
            is_system_core: false,
            is_user_app: false,
        };

        Self {
            processes: vec![launchd, logd, chrome, python_proc],
            is_mock: true,
        }
    }
}

impl MacOsProcessCollector for MockMacOsProcessCollector {
    fn collect_processes(&self) -> MacOsProcessSnapshot {
        let running_cnt = self
            .processes
            .iter()
            .filter(|p| p.state == ProcessStateSnapshot::Running)
            .count();
        let sleeping_cnt = self
            .processes
            .iter()
            .filter(|p| p.state == ProcessStateSnapshot::Sleeping)
            .count();
        let zombie_cnt = self
            .processes
            .iter()
            .filter(|p| p.state == ProcessStateSnapshot::Zombie)
            .count();
        let core_cnt = self.processes.iter().filter(|p| p.is_system_core).count();
        let app_cnt = self.processes.iter().filter(|p| p.is_user_app).count();
        let total_rss = self.processes.iter().map(|p| p.rss_bytes).sum();

        MacOsProcessSnapshot {
            total_process_count: self.processes.len(),
            running_count: running_cnt,
            sleeping_count: sleeping_cnt,
            zombie_count: zombie_cnt,
            system_core_count: core_cnt,
            user_app_count: app_cnt,
            total_rss_bytes: total_rss,
            processes: self.processes.clone(),
            is_mock: self.is_mock,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_process_collector_apple_silicon() {
        let collector = MockMacOsProcessCollector::new_apple_silicon();
        let snapshot = collector.collect_processes();

        assert_eq!(snapshot.total_process_count, 4);
        assert_eq!(snapshot.running_count, 2);
        assert_eq!(snapshot.sleeping_count, 2);
        assert_eq!(snapshot.zombie_count, 0);
        assert_eq!(snapshot.system_core_count, 2);
        assert_eq!(snapshot.user_app_count, 1);
        assert!(snapshot.total_rss_bytes > 0);
        assert!(snapshot.is_mock);

        let launchd = &snapshot.processes[0];
        assert_eq!(launchd.pid, 1);
        assert_eq!(launchd.user, "root");
        assert_eq!(launchd.name, "launchd");
        assert_eq!(launchd.role, ProcessRoleSnapshot::SystemCore);
        assert!(launchd.is_system_core);
        assert!(!launchd.is_user_app);

        let chrome = &snapshot.processes[2];
        assert_eq!(chrome.name, "Google Chrome");
        assert_eq!(chrome.role, ProcessRoleSnapshot::UserApp);
        assert!(!chrome.is_system_core);
        assert!(chrome.is_user_app);

        let py = &snapshot.processes[3];
        assert_eq!(py.name, "python3");
        assert_eq!(py.role, ProcessRoleSnapshot::DeveloperTool);
    }

    #[test]
    fn test_json_summary_serialization() {
        let collector = MockMacOsProcessCollector::new_apple_silicon();
        let snapshot = collector.collect_processes();
        let json = snapshot.to_json_summary();

        assert!(json.contains("\"total_processes\":4"));
        assert!(json.contains("\"running\":2"));
        assert!(json.contains("\"system_core\":2"));
        assert!(json.contains("\"user_app\":1"));
        assert!(json.contains("\"mock\":true"));
    }

    #[test]
    fn test_resource_aggregation() {
        let p1 = MacOsProcessItemSnapshot {
            pid: 10,
            ppid: 1,
            uid: 501,
            user: "dev".to_string(),
            name: "cargo".to_string(),
            command_path: "/bin/cargo".to_string(),
            cpu_pct: 50.0,
            mem_pct: 1.0,
            rss_bytes: 100 * 1024 * 1024,
            vsz_bytes: 200 * 1024 * 1024,
            state: ProcessStateSnapshot::Running,
            role: ProcessRoleSnapshot::DeveloperTool,
            is_system_core: false,
            is_user_app: false,
        };

        let collector = MockMacOsProcessCollector {
            processes: vec![p1],
            is_mock: false,
        };

        let snapshot = collector.collect_processes();
        assert_eq!(snapshot.total_process_count, 1);
        assert_eq!(snapshot.running_count, 1);
        assert_eq!(snapshot.total_rss_bytes, 100 * 1024 * 1024);
    }
}
