//! macOS Darwin installed applications and bundle identifiers sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ApplicationCategorySnapshot {
    CoreSystem,
    DeveloperTool,
    WebBrowser,
    Productivity,
    Utility,
    Media,
    Other,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppOwnershipSnapshot {
    SystemManaged,
    VendorManaged,
    UserManaged,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsAppItemSnapshot {
    pub name: String,
    pub bundle_id: String,
    pub bundle_path: String,
    pub version: String,
    pub build_version: Option<String>,
    pub executable_name: Option<String>,
    pub min_os_version: Option<String>,
    pub ownership: AppOwnershipSnapshot,
    pub category: ApplicationCategorySnapshot,
    pub is_apple: bool,
    pub is_user_app: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsAppInventorySnapshot {
    pub applications: Vec<MacOsAppItemSnapshot>,
    pub total_applications_count: usize,
    pub system_managed_count: usize,
    pub vendor_managed_count: usize,
    pub user_managed_count: usize,
    pub is_mock: bool,
}

impl MacOsAppInventorySnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"total_apps\":{},\"system_managed\":{},\"vendor_managed\":{},\"user_managed\":{},\"mock\":{}}}",
            self.total_applications_count,
            self.system_managed_count,
            self.vendor_managed_count,
            self.user_managed_count,
            self.is_mock
        )
    }
}

pub trait MacOsAppCollector: Send + Sync {
    fn collect_apps(&self) -> MacOsAppInventorySnapshot;
}

/// Safe mock collector simulating installed macOS application bundles.
#[derive(Debug, Clone)]
pub struct MockMacOsAppCollector {
    pub applications: Vec<MacOsAppItemSnapshot>,
    pub is_mock: bool,
}

impl MockMacOsAppCollector {
    pub fn new_apple_silicon() -> Self {
        let safari = MacOsAppItemSnapshot {
            name: "Safari".to_string(),
            bundle_id: "com.apple.Safari".to_string(),
            bundle_path: "/System/Applications/Safari.app".to_string(),
            version: "18.0".to_string(),
            build_version: Some("20619.1.26.31.7".to_string()),
            executable_name: Some("Safari".to_string()),
            min_os_version: Some("15.0".to_string()),
            ownership: AppOwnershipSnapshot::SystemManaged,
            category: ApplicationCategorySnapshot::WebBrowser,
            is_apple: true,
            is_user_app: false,
        };

        let terminal = MacOsAppItemSnapshot {
            name: "Terminal".to_string(),
            bundle_id: "com.apple.Terminal".to_string(),
            bundle_path: "/System/Applications/Utilities/Terminal.app".to_string(),
            version: "2.15".to_string(),
            build_version: Some("453".to_string()),
            executable_name: Some("Terminal".to_string()),
            min_os_version: Some("15.0".to_string()),
            ownership: AppOwnershipSnapshot::SystemManaged,
            category: ApplicationCategorySnapshot::DeveloperTool,
            is_apple: true,
            is_user_app: false,
        };

        let chrome = MacOsAppItemSnapshot {
            name: "Google Chrome".to_string(),
            bundle_id: "com.google.Chrome".to_string(),
            bundle_path: "/Applications/Google Chrome.app".to_string(),
            version: "157.0.8103.51".to_string(),
            build_version: Some("8103.51".to_string()),
            executable_name: Some("Google Chrome".to_string()),
            min_os_version: Some("10.15.0".to_string()),
            ownership: AppOwnershipSnapshot::VendorManaged,
            category: ApplicationCategorySnapshot::WebBrowser,
            is_apple: false,
            is_user_app: true,
        };

        let vscode = MacOsAppItemSnapshot {
            name: "Visual Studio Code".to_string(),
            bundle_id: "com.microsoft.VSCode".to_string(),
            bundle_path: "/Applications/Visual Studio Code.app".to_string(),
            version: "1.95.0".to_string(),
            build_version: Some("1.95.0".to_string()),
            executable_name: Some("Code".to_string()),
            min_os_version: Some("10.15.0".to_string()),
            ownership: AppOwnershipSnapshot::VendorManaged,
            category: ApplicationCategorySnapshot::DeveloperTool,
            is_apple: false,
            is_user_app: true,
        };

        let custom_tool = MacOsAppItemSnapshot {
            name: "CustomTool".to_string(),
            bundle_id: "com.user.CustomTool".to_string(),
            bundle_path: "/Users/mockuser/Applications/CustomTool.app".to_string(),
            version: "1.0.0".to_string(),
            build_version: Some("1".to_string()),
            executable_name: Some("CustomTool".to_string()),
            min_os_version: Some("12.0".to_string()),
            ownership: AppOwnershipSnapshot::UserManaged,
            category: ApplicationCategorySnapshot::Utility,
            is_apple: false,
            is_user_app: true,
        };

        Self {
            applications: vec![safari, terminal, chrome, vscode, custom_tool],
            is_mock: true,
        }
    }
}

impl MacOsAppCollector for MockMacOsAppCollector {
    fn collect_apps(&self) -> MacOsAppInventorySnapshot {
        let system_count = self
            .applications
            .iter()
            .filter(|a| a.ownership == AppOwnershipSnapshot::SystemManaged)
            .count();

        let vendor_count = self
            .applications
            .iter()
            .filter(|a| a.ownership == AppOwnershipSnapshot::VendorManaged)
            .count();

        let user_count = self
            .applications
            .iter()
            .filter(|a| a.ownership == AppOwnershipSnapshot::UserManaged)
            .count();

        MacOsAppInventorySnapshot {
            total_applications_count: self.applications.len(),
            system_managed_count: system_count,
            vendor_managed_count: vendor_count,
            user_managed_count: user_count,
            applications: self.applications.clone(),
            is_mock: self.is_mock,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_app_collector_apple_silicon() {
        let collector = MockMacOsAppCollector::new_apple_silicon();
        let snapshot = collector.collect_apps();

        assert_eq!(snapshot.total_applications_count, 5);
        assert_eq!(snapshot.system_managed_count, 2);
        assert_eq!(snapshot.vendor_managed_count, 2);
        assert_eq!(snapshot.user_managed_count, 1);
        assert!(snapshot.is_mock);

        let chrome = snapshot
            .applications
            .iter()
            .find(|a| a.bundle_id == "com.google.Chrome")
            .expect("Chrome must exist");
        assert_eq!(chrome.name, "Google Chrome");
        assert_eq!(chrome.category, ApplicationCategorySnapshot::WebBrowser);
        assert_eq!(chrome.ownership, AppOwnershipSnapshot::VendorManaged);
        assert!(!chrome.is_apple);
        assert!(chrome.is_user_app);
    }

    #[test]
    fn test_json_summary_serialization() {
        let collector = MockMacOsAppCollector::new_apple_silicon();
        let snapshot = collector.collect_apps();
        let summary = snapshot.to_json_summary();

        assert!(summary.contains("\"total_apps\":5"));
        assert!(summary.contains("\"system_managed\":2"));
        assert!(summary.contains("\"vendor_managed\":2"));
        assert!(summary.contains("\"user_managed\":1"));
        assert!(summary.contains("\"mock\":true"));
    }

    #[test]
    fn test_apps_aggregation_and_categories() {
        let collector = MockMacOsAppCollector::new_apple_silicon();
        let snapshot = collector.collect_apps();

        let browser_count = snapshot
            .applications
            .iter()
            .filter(|a| a.category == ApplicationCategorySnapshot::WebBrowser)
            .count();
        assert_eq!(browser_count, 2); // Safari and Chrome

        let dev_count = snapshot
            .applications
            .iter()
            .filter(|a| a.category == ApplicationCategorySnapshot::DeveloperTool)
            .count();
        assert_eq!(dev_count, 2); // Terminal and VS Code
    }
}
