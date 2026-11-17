//! macOS Darwin application code signature and notarization telemetry sensor collector.
//!
//! Enforces unprivileged read-only operation and the non-negotiable charter invariant: Scan != Safe.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SignatureStatusSnapshot {
    SignedValid,
    SignedInvalid,
    Unsigned,
    AdhocSigned,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NotarizationStatusSnapshot {
    NotarizedDeveloperId,
    AppleSystem,
    MacAppStore,
    NotNotarized,
    Rejected,
    NotApplicable,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SigningAuthorityTypeSnapshot {
    AppleSystem,
    DeveloperId,
    AppStore,
    Adhoc,
    ThirdPartyCa,
    Unsigned,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsAppSignatureItemSnapshot {
    pub bundle_id: String,
    pub bundle_path: String,
    pub executable_path: Option<String>,
    pub signature_status: SignatureStatusSnapshot,
    pub notarization_status: NotarizationStatusSnapshot,
    pub authority_type: SigningAuthorityTypeSnapshot,
    pub authorities: Vec<String>,
    pub team_id: Option<String>,
    pub cdhash: Option<String>,
    pub is_hardened_runtime: bool,
    pub is_apple: bool,
    pub is_valid: bool,
    pub scan_proves_safe: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsAppSignatureReportSnapshot {
    pub signatures: Vec<MacOsAppSignatureItemSnapshot>,
    pub total_signatures_count: usize,
    pub validly_signed_count: usize,
    pub notarized_count: usize,
    pub apple_system_count: usize,
    pub unsigned_count: usize,
    pub is_mock: bool,
}

impl MacOsAppSignatureReportSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"total_signatures\":{},\"validly_signed\":{},\"notarized\":{},\"apple_system\":{},\"unsigned\":{},\"mock\":{}}}",
            self.total_signatures_count,
            self.validly_signed_count,
            self.notarized_count,
            self.apple_system_count,
            self.unsigned_count,
            self.is_mock
        )
    }
}

pub trait MacOsSignatureCollector: Send + Sync {
    fn collect_signatures(&self) -> MacOsAppSignatureReportSnapshot;
}

/// Safe mock collector simulating macOS code signatures and notarization metadata.
#[derive(Debug, Clone)]
pub struct MockMacOsSignatureCollector {
    pub signatures: Vec<MacOsAppSignatureItemSnapshot>,
    pub is_mock: bool,
}

impl MockMacOsSignatureCollector {
    pub fn new_apple_silicon() -> Self {
        let terminal = MacOsAppSignatureItemSnapshot {
            bundle_id: "com.apple.Terminal".to_string(),
            bundle_path: "/System/Applications/Utilities/Terminal.app".to_string(),
            executable_path: Some(
                "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal".to_string(),
            ),
            signature_status: SignatureStatusSnapshot::SignedValid,
            notarization_status: NotarizationStatusSnapshot::AppleSystem,
            authority_type: SigningAuthorityTypeSnapshot::AppleSystem,
            authorities: vec![
                "macOS Software Signing".to_string(),
                "Apple Code Signing Certification Authority".to_string(),
                "Apple Root CA".to_string(),
            ],
            team_id: None,
            cdhash: Some("c04973400ce57f4c162573a4c91ea897d3961c41".to_string()),
            is_hardened_runtime: false,
            is_apple: true,
            is_valid: true,
            scan_proves_safe: false,
        };

        let chrome = MacOsAppSignatureItemSnapshot {
            bundle_id: "com.google.Chrome".to_string(),
            bundle_path: "/Applications/Google Chrome.app".to_string(),
            executable_path: Some(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome".to_string(),
            ),
            signature_status: SignatureStatusSnapshot::SignedValid,
            notarization_status: NotarizationStatusSnapshot::NotarizedDeveloperId,
            authority_type: SigningAuthorityTypeSnapshot::DeveloperId,
            authorities: vec![
                "Developer ID Application: Google LLC (EQHXZ8M8AV)".to_string(),
                "Developer ID Certification Authority".to_string(),
                "Apple Root CA".to_string(),
            ],
            team_id: Some("EQHXZ8M8AV".to_string()),
            cdhash: Some("ef9751368c315d7f2c8a1a071d0805b972935a66".to_string()),
            is_hardened_runtime: true,
            is_apple: false,
            is_valid: true,
            scan_proves_safe: false,
        };

        let vscode = MacOsAppSignatureItemSnapshot {
            bundle_id: "com.microsoft.VSCode".to_string(),
            bundle_path: "/Applications/Visual Studio Code.app".to_string(),
            executable_path: Some(
                "/Applications/Visual Studio Code.app/Contents/MacOS/Electron".to_string(),
            ),
            signature_status: SignatureStatusSnapshot::SignedValid,
            notarization_status: NotarizationStatusSnapshot::NotarizedDeveloperId,
            authority_type: SigningAuthorityTypeSnapshot::DeveloperId,
            authorities: vec![
                "Developer ID Application: Microsoft Corporation (UBF8T346G9)".to_string(),
                "Developer ID Certification Authority".to_string(),
                "Apple Root CA".to_string(),
            ],
            team_id: Some("UBF8T346G9".to_string()),
            cdhash: Some("5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b".to_string()),
            is_hardened_runtime: true,
            is_apple: false,
            is_valid: true,
            scan_proves_safe: false,
        };

        let unsigned_app = MacOsAppSignatureItemSnapshot {
            bundle_id: "dev.systemmind.test-unsigned".to_string(),
            bundle_path: "/Applications/UnsignedTool.app".to_string(),
            executable_path: Some("/Applications/UnsignedTool.app/Contents/MacOS/tool".to_string()),
            signature_status: SignatureStatusSnapshot::Unsigned,
            notarization_status: NotarizationStatusSnapshot::NotApplicable,
            authority_type: SigningAuthorityTypeSnapshot::Unsigned,
            authorities: vec![],
            team_id: None,
            cdhash: None,
            is_hardened_runtime: false,
            is_apple: false,
            is_valid: false,
            scan_proves_safe: false,
        };

        let tampered_app = MacOsAppSignatureItemSnapshot {
            bundle_id: "dev.systemmind.test-tampered".to_string(),
            bundle_path: "/Applications/TamperedTool.app".to_string(),
            executable_path: Some("/Applications/TamperedTool.app/Contents/MacOS/tool".to_string()),
            signature_status: SignatureStatusSnapshot::SignedInvalid,
            notarization_status: NotarizationStatusSnapshot::Rejected,
            authority_type: SigningAuthorityTypeSnapshot::DeveloperId,
            authorities: vec![
                "Developer ID Application: Untrusted Third Party (TAMPER1234)".to_string(),
                "Developer ID Certification Authority".to_string(),
                "Apple Root CA".to_string(),
            ],
            team_id: Some("TAMPER1234".to_string()),
            cdhash: Some("0000000000000000000000000000000000000000".to_string()),
            is_hardened_runtime: false,
            is_apple: false,
            is_valid: false,
            scan_proves_safe: false,
        };

        let signatures = vec![terminal, chrome, vscode, unsigned_app, tampered_app];

        Self {
            signatures,
            is_mock: true,
        }
    }
}

impl MacOsSignatureCollector for MockMacOsSignatureCollector {
    fn collect_signatures(&self) -> MacOsAppSignatureReportSnapshot {
        let total_signatures_count = self.signatures.len();
        let validly_signed_count = self.signatures.iter().filter(|s| s.is_valid).count();
        let notarized_count = self
            .signatures
            .iter()
            .filter(|s| {
                matches!(
                    s.notarization_status,
                    NotarizationStatusSnapshot::NotarizedDeveloperId
                        | NotarizationStatusSnapshot::AppleSystem
                        | NotarizationStatusSnapshot::MacAppStore
                )
            })
            .count();
        let apple_system_count = self.signatures.iter().filter(|s| s.is_apple).count();
        let unsigned_count = self
            .signatures
            .iter()
            .filter(|s| s.signature_status == SignatureStatusSnapshot::Unsigned)
            .count();

        MacOsAppSignatureReportSnapshot {
            signatures: self.signatures.clone(),
            total_signatures_count,
            validly_signed_count,
            notarized_count,
            apple_system_count,
            unsigned_count,
            is_mock: self.is_mock,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_signature_collector_apple_silicon() {
        let collector = MockMacOsSignatureCollector::new_apple_silicon();
        let snapshot = collector.collect_signatures();

        assert_eq!(snapshot.total_signatures_count, 5);
        assert_eq!(snapshot.validly_signed_count, 3);
        assert_eq!(snapshot.notarized_count, 3);
        assert_eq!(snapshot.apple_system_count, 1);
        assert_eq!(snapshot.unsigned_count, 1);
        assert!(snapshot.is_mock);

        let chrome = snapshot
            .signatures
            .iter()
            .find(|s| s.bundle_id == "com.google.Chrome")
            .expect("Chrome must exist");
        assert_eq!(
            chrome.authority_type,
            SigningAuthorityTypeSnapshot::DeveloperId
        );
        assert_eq!(chrome.team_id.as_deref(), Some("EQHXZ8M8AV"));
        assert!(chrome.is_hardened_runtime);
        assert!(chrome.is_valid);
        assert!(!chrome.is_apple);
    }

    #[test]
    fn test_scan_proves_safe_invariant() {
        let collector = MockMacOsSignatureCollector::new_apple_silicon();
        let snapshot = collector.collect_signatures();

        // Enforce the charter invariant across all signature records
        for item in &snapshot.signatures {
            assert!(
                !item.scan_proves_safe,
                "Charter invariant violation: scan_proves_safe must always be false"
            );
        }
    }

    #[test]
    fn test_json_summary_serialization() {
        let collector = MockMacOsSignatureCollector::new_apple_silicon();
        let snapshot = collector.collect_signatures();
        let summary = snapshot.to_json_summary();

        assert!(summary.contains("\"total_signatures\":5"));
        assert!(summary.contains("\"validly_signed\":3"));
        assert!(summary.contains("\"notarized\":3"));
        assert!(summary.contains("\"apple_system\":1"));
        assert!(summary.contains("\"unsigned\":1"));
        assert!(summary.contains("\"mock\":true"));
    }
}
