//! macOS permissions, TCC prompt triggers, and code signing entitlements sensor.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MacPermissionTypeSnapshot {
    FullDiskAccess,
    ScreenRecording,
    Accessibility,
    DocumentsFolder,
    DownloadsFolder,
    DesktopFolder,
    InputMonitoring,
    EndpointSecurity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EntitlementTierSnapshot {
    StandardUser,
    HardenedRuntime,
    AppleRestricted,
    ProhibitedNonGoal,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PromptTriggerModeSnapshot {
    ImplicitOsPrompt,
    GuidedSystemSettings,
    PassiveProbe,
    NeverPrompted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PermissionStateSnapshot {
    Granted,
    Denied,
    NotDetermined,
    Restricted,
    ExcludedByPolicy,
    ProhibitedNonGoal,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacEntitlementSpecSnapshot {
    pub entitlement_key: String,
    pub tier: EntitlementTierSnapshot,
    pub description: String,
    pub is_required: bool,
    pub target_component: String,
    pub fallback_behavior: String,
    pub scan_proves_safe: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacPermissionPromptInfoSnapshot {
    pub permission_type: MacPermissionTypeSnapshot,
    pub tcc_service_name: String,
    pub prompt_trigger_mode: PromptTriggerModeSnapshot,
    pub user_dialog_text: String,
    pub settings_path: String,
    pub is_strictly_required: bool,
    pub is_banned_non_goal: bool,
    pub fallback_strategy: String,
    pub scan_proves_safe: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacPermissionManifestReportSnapshot {
    pub companion_mode: String,
    pub host_platform: String,
    pub timestamp: String,
    pub permissions: Vec<MacPermissionPromptInfoSnapshot>,
    pub entitlements: Vec<MacEntitlementSpecSnapshot>,
    pub active_states: Vec<(String, PermissionStateSnapshot)>,
    pub non_goals_enforced: Vec<String>,
    pub warnings: Vec<String>,
    pub unavailable_telemetry: Vec<String>,
    pub scan_proves_safe: bool,
}

impl MacPermissionManifestReportSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"companion_mode\":\"{}\",\"permissions_count\":{},\"entitlements_count\":{},\"non_goals_count\":{},\"scan_proves_safe\":{}}}",
            self.companion_mode,
            self.permissions.len(),
            self.entitlements.len(),
            self.non_goals_enforced.len(),
            self.scan_proves_safe
        )
    }

    pub fn find_permission(
        &self,
        perm_type: MacPermissionTypeSnapshot,
    ) -> Option<&MacPermissionPromptInfoSnapshot> {
        self.permissions
            .iter()
            .find(|p| p.permission_type == perm_type)
    }

    pub fn find_entitlement(&self, key: &str) -> Option<&MacEntitlementSpecSnapshot> {
        self.entitlements.iter().find(|e| e.entitlement_key == key)
    }
}

pub trait MacOsPermissionsCollector: Send + Sync {
    fn collect_permissions_manifest(&self) -> MacPermissionManifestReportSnapshot;
}

/// Deterministic mock sensor providing macOS permission and entitlement manifests.
#[derive(Debug, Clone)]
pub struct MockMacOsPermissionsCollector {
    pub report: MacPermissionManifestReportSnapshot,
}

impl MockMacOsPermissionsCollector {
    pub fn new_unprivileged_companion() -> Self {
        let permissions = vec![
            MacPermissionPromptInfoSnapshot {
                permission_type: MacPermissionTypeSnapshot::FullDiskAccess,
                tcc_service_name: "kTCCServiceSystemPolicyAllFiles".to_string(),
                prompt_trigger_mode: PromptTriggerModeSnapshot::GuidedSystemSettings,
                user_dialog_text: "System Settings > Privacy & Security > Full Disk Access".to_string(),
                settings_path: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles".to_string(),
                is_strictly_required: false,
                is_banned_non_goal: false,
                fallback_strategy: "Gracefully skip protected roots; omit Mail/Safari; report fda_granted = false".to_string(),
                scan_proves_safe: false,
            },
            MacPermissionPromptInfoSnapshot {
                permission_type: MacPermissionTypeSnapshot::ScreenRecording,
                tcc_service_name: "kTCCServiceScreenCapture".to_string(),
                prompt_trigger_mode: PromptTriggerModeSnapshot::ImplicitOsPrompt,
                user_dialog_text: "System Mind would like to record this computer's screen".to_string(),
                settings_path: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture".to_string(),
                is_strictly_required: false,
                is_banned_non_goal: false,
                fallback_strategy: "Omit window titles and thumbnails; scrub metadata; report screen_recording_granted = false".to_string(),
                scan_proves_safe: false,
            },
            MacPermissionPromptInfoSnapshot {
                permission_type: MacPermissionTypeSnapshot::Accessibility,
                tcc_service_name: "kTCCServiceAccessibility".to_string(),
                prompt_trigger_mode: PromptTriggerModeSnapshot::ImplicitOsPrompt,
                user_dialog_text: "System Mind would like to control this computer using accessibility features".to_string(),
                settings_path: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility".to_string(),
                is_strictly_required: false,
                is_banned_non_goal: false,
                fallback_strategy: "Fall back to NSWorkspace.frontmostApplication which requires zero permissions for app/bundle ID".to_string(),
                scan_proves_safe: false,
            },
            MacPermissionPromptInfoSnapshot {
                permission_type: MacPermissionTypeSnapshot::InputMonitoring,
                tcc_service_name: "kTCCServiceListenEvent".to_string(),
                prompt_trigger_mode: PromptTriggerModeSnapshot::NeverPrompted,
                user_dialog_text: "System Mind would like to receive keystrokes from any application".to_string(),
                settings_path: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent".to_string(),
                is_strictly_required: false,
                is_banned_non_goal: true, // Prohibited Non-Goal!
                fallback_strategy: "PROHIBITED NON-GOAL (NG-02): Keystroke logging is strictly disallowed".to_string(),
                scan_proves_safe: false,
            },
            MacPermissionPromptInfoSnapshot {
                permission_type: MacPermissionTypeSnapshot::EndpointSecurity,
                tcc_service_name: "com.apple.developer.endpoint-security.client".to_string(),
                prompt_trigger_mode: PromptTriggerModeSnapshot::PassiveProbe,
                user_dialog_text: "System Extension Blocked: Requires Apple Developer Enterprise Entitlement".to_string(),
                settings_path: "x-apple.systempreferences:com.apple.preference.security?Privacy_SystemExtensions".to_string(),
                is_strictly_required: false,
                is_banned_non_goal: false,
                fallback_strategy: "Transparent fallback to CoreServices FSEvents and Darwin ps (INV-FAULT-03)".to_string(),
                scan_proves_safe: false,
            },
        ];

        let entitlements = vec![
            MacEntitlementSpecSnapshot {
                entitlement_key: "com.apple.security.network.client".to_string(),
                tier: EntitlementTierSnapshot::StandardUser,
                description:
                    "Permits outgoing socket connections to loopback agent API (127.0.0.1)"
                        .to_string(),
                is_required: true,
                target_component: "Desktop Shell & Agent Wire Client".to_string(),
                fallback_behavior: "Fails with network socket creation error if blocked"
                    .to_string(),
                scan_proves_safe: false,
            },
            MacEntitlementSpecSnapshot {
                entitlement_key: "com.apple.security.cs.allow-jit".to_string(),
                tier: EntitlementTierSnapshot::HardenedRuntime,
                description:
                    "Hardened Runtime exception allowing dynamic JIT memory allocation (DISALLOWED)"
                        .to_string(),
                is_required: false,
                target_component: "Companion Agent Core".to_string(),
                fallback_behavior:
                    "Prohibited in companion agent to prevent arbitrary executable memory execution"
                        .to_string(),
                scan_proves_safe: false,
            },
        ];

        let active_states = vec![
            (
                "FULL_DISK_ACCESS".to_string(),
                PermissionStateSnapshot::Denied,
            ),
            (
                "SCREEN_RECORDING".to_string(),
                PermissionStateSnapshot::Denied,
            ),
            (
                "ACCESSIBILITY".to_string(),
                PermissionStateSnapshot::NotDetermined,
            ),
            (
                "INPUT_MONITORING".to_string(),
                PermissionStateSnapshot::ProhibitedNonGoal,
            ),
            (
                "ENDPOINT_SECURITY".to_string(),
                PermissionStateSnapshot::Restricted,
            ),
        ];

        let non_goals_enforced = vec![
            "NG-01: Zero unmediated shell execution".to_string(),
            "NG-02: Zero ambient screen scraping".to_string(),
            "NG-03: Zero keystroke logging".to_string(),
        ];

        let report = MacPermissionManifestReportSnapshot {
            companion_mode: "READ_ONLY_USER_COMPANION".to_string(),
            host_platform: "Darwin-Mock-Apple-Silicon-arm64".to_string(),
            timestamp: "2026-11-17T10:15:00Z".to_string(),
            permissions,
            entitlements,
            active_states,
            non_goals_enforced,
            warnings: vec![
                "Full Disk Access not granted: protected application paths will be skipped"
                    .to_string(),
            ],
            unavailable_telemetry: vec!["protected_user_mail_and_messages".to_string()],
            scan_proves_safe: false,
        };

        Self { report }
    }
}

impl MacOsPermissionsCollector for MockMacOsPermissionsCollector {
    fn collect_permissions_manifest(&self) -> MacPermissionManifestReportSnapshot {
        self.report.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_permissions_manifest_invariants() {
        let collector = MockMacOsPermissionsCollector::new_unprivileged_companion();
        let report = collector.collect_permissions_manifest();

        assert_eq!(report.companion_mode, "READ_ONLY_USER_COMPANION");
        assert!(!report.scan_proves_safe, "Charter invariant violated");

        // Verify Input Monitoring is flagged as prohibited non-goal
        let input_mon = report.find_permission(MacPermissionTypeSnapshot::InputMonitoring);
        assert!(input_mon.is_some());
        assert!(input_mon.unwrap().is_banned_non_goal);
        assert!(!input_mon.unwrap().scan_proves_safe);

        // Verify Network Client entitlement is present and required
        let net_ent = report.find_entitlement("com.apple.security.network.client");
        assert!(net_ent.is_some());
        assert!(net_ent.unwrap().is_required);
        assert!(!net_ent.unwrap().scan_proves_safe);
    }

    #[test]
    fn test_permissions_json_summary() {
        let collector = MockMacOsPermissionsCollector::new_unprivileged_companion();
        let report = collector.collect_permissions_manifest();
        let summary = report.to_json_summary();

        assert!(summary.contains("\"companion_mode\":\"READ_ONLY_USER_COMPANION\""));
        assert!(summary.contains("\"scan_proves_safe\":false"));
    }
}
