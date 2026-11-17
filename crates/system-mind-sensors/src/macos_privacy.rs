//! macOS Darwin telemetry privacy filtering, path masking, and metadata sanitization sensor collector.

/// Granularity of privacy redaction applied to telemetry payloads.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrivacyScrubbingLevelSnapshot {
    Strict,
    Balanced,
    Minimal,
}

impl PrivacyScrubbingLevelSnapshot {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Strict => "STRICT",
            Self::Balanced => "BALANCED",
            Self::Minimal => "MINIMAL",
        }
    }
}

/// Taxonomy of sensitive information scrubbed by privacy filters.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PrivacyRuleCategorySnapshot {
    Username,
    PersonalFolder,
    ProtectedVault,
    DocumentMetadata,
    TokenOrSecret,
}

impl PrivacyRuleCategorySnapshot {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Username => "USERNAME",
            Self::PersonalFolder => "PERSONAL_FOLDER",
            Self::ProtectedVault => "PROTECTED_VAULT",
            Self::DocumentMetadata => "DOCUMENT_METADATA",
            Self::TokenOrSecret => "TOKEN_OR_SECRET",
        }
    }
}

/// Audit metrics documenting exact redactions performed during a privacy filtering pass.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PrivacyFilterAuditRecordSnapshot {
    pub sanitized_usernames_count: usize,
    pub sanitized_paths_count: usize,
    pub sanitized_metadata_count: usize,
    pub redacted_secrets_count: usize,
    pub level: PrivacyScrubbingLevelSnapshot,
    pub rules_applied: Vec<String>,
    pub scan_proves_safe: bool, // Mandatory non-negotiable charter invariant: false
}

impl PrivacyFilterAuditRecordSnapshot {
    pub fn total_redactions(&self) -> usize {
        self.sanitized_usernames_count
            + self.sanitized_paths_count
            + self.sanitized_metadata_count
            + self.redacted_secrets_count
    }

    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"level\":\"{}\",\"total_redactions\":{},\"usernames\":{},\"paths\":{},\"metadata\":{},\"secrets\":{},\"scan_proves_safe\":{}}}",
            self.level.as_str(),
            self.total_redactions(),
            self.sanitized_usernames_count,
            self.sanitized_paths_count,
            self.sanitized_metadata_count,
            self.redacted_secrets_count,
            self.scan_proves_safe
        )
    }
}

/// Telemetry envelope wrapping sanitized payload with privacy audit metadata.
#[derive(Debug, Clone, PartialEq)]
pub struct SanitizedTelemetryEnvelopeSnapshot {
    pub envelope_id: String,
    pub collector_id: String,
    pub payload_summary: String,
    pub audit: PrivacyFilterAuditRecordSnapshot,
    pub scan_proves_safe: bool, // Mandatory non-negotiable charter invariant: false
    pub is_mock: bool,
}

impl SanitizedTelemetryEnvelopeSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"envelope_id\":\"{}\",\"collector_id\":\"{}\",\"payload_summary\":\"{}\",\"audit\":{},\"scan_proves_safe\":{},\"mock\":{}}}",
            self.envelope_id,
            self.collector_id,
            self.payload_summary,
            self.audit.to_json_summary(),
            self.scan_proves_safe,
            self.is_mock
        )
    }
}

/// Trait defining contract for macOS privacy sanitization engines.
pub trait MacOsPrivacySanitizer {
    fn sanitize_text(&self, text: &str) -> (String, PrivacyFilterAuditRecordSnapshot);
    fn sanitize_envelope(
        &self,
        envelope_id: &str,
        collector_id: &str,
        payload_summary: &str,
    ) -> SanitizedTelemetryEnvelopeSnapshot;
    fn is_mock(&self) -> bool;
}

/// In-memory privacy filter implementation for Darwin sensor pipelines.
pub struct MacOsPrivacyFilterCollector {
    pub level: PrivacyScrubbingLevelSnapshot,
    pub known_usernames: Vec<String>,
}

impl MacOsPrivacyFilterCollector {
    pub fn new(level: PrivacyScrubbingLevelSnapshot) -> Self {
        Self {
            level,
            known_usernames: vec!["admin".to_string(), "tharungodwin".to_string()],
        }
    }

    pub fn with_usernames(level: PrivacyScrubbingLevelSnapshot, usernames: Vec<String>) -> Self {
        Self {
            level,
            known_usernames: usernames,
        }
    }
}

impl MacOsPrivacySanitizer for MacOsPrivacyFilterCollector {
    fn sanitize_text(&self, text: &str) -> (String, PrivacyFilterAuditRecordSnapshot) {
        let mut cleaned = text.to_string();
        let mut usernames_count = 0;
        let mut paths_count = 0;
        let mut meta_count = 0;
        let mut secrets_count = 0;
        let mut rules = Vec::new();

        // 1. Secret scrubbing
        if cleaned.contains("Bearer ") {
            // Mask bearer tokens
            if let Some(pos) = cleaned.find("Bearer ") {
                let rest = &cleaned[pos + 7..];
                let token_len = rest.find(' ').unwrap_or(rest.len());
                let token = &rest[..token_len];
                if token.len() >= 8 {
                    cleaned =
                        cleaned.replace(&format!("Bearer {}", token), "Bearer <REDACTED_TOKEN>");
                    secrets_count += 1;
                    rules.push("SECRET_BEARER".to_string());
                }
            }
        }

        if cleaned.contains("AKIA") {
            // Mask AWS access key
            if let Some(pos) = cleaned.find("AKIA") {
                if pos + 20 <= cleaned.len() {
                    let key = &cleaned[pos..pos + 20];
                    if key.chars().all(|c| c.is_ascii_alphanumeric()) {
                        cleaned = cleaned.replace(key, "<REDACTED_AWS_KEY>");
                        secrets_count += 1;
                        rules.push("SECRET_AWS_KEY".to_string());
                    }
                }
            }
        }

        if cleaned.contains("ghp_") {
            // Mask GitHub token
            if let Some(pos) = cleaned.find("ghp_") {
                let rest = &cleaned[pos..];
                let token_len = rest
                    .find(|c: char| !c.is_ascii_alphanumeric() && c != '_')
                    .unwrap_or(rest.len());
                if token_len >= 36 {
                    let token = &rest[..token_len];
                    cleaned = cleaned.replace(token, "<REDACTED_GITHUB_TOKEN>");
                    secrets_count += 1;
                    rules.push("SECRET_GITHUB_TOKEN".to_string());
                }
            }
        }

        // 2. Personal folder & key vault path masking
        let protected_vaults = [
            (".ssh", "<PROTECTED_KEY_VAULT>/ssh"),
            (".aws", "<PROTECTED_KEY_VAULT>/aws"),
            (".gnupg", "<PROTECTED_KEY_VAULT>/gnupg"),
            ("Library/Keychains", "<PROTECTED_KEYCHAINS>"),
            ("Library/Safari", "<PROTECTED_BROWSER_DATA>/Safari"),
        ];

        for (vault, repl) in &protected_vaults {
            if cleaned.contains(vault) {
                cleaned = cleaned.replace(vault, repl);
                paths_count += 1;
                rules.push("PROTECTED_VAULT".to_string());
            }
        }

        if self.level == PrivacyScrubbingLevelSnapshot::Strict
            || self.level == PrivacyScrubbingLevelSnapshot::Balanced
        {
            let personal_folders = [
                ("Documents", "<PROTECTED_DOCUMENTS>/<REDACTED_DOCUMENT>"),
                ("Desktop", "<PROTECTED_DESKTOP>/<REDACTED_FILE>"),
                ("Downloads", "<PROTECTED_DOWNLOADS>/<REDACTED_DOWNLOAD>"),
                ("Pictures", "<PROTECTED_PICTURES>/<REDACTED_MEDIA>"),
                ("Movies", "<PROTECTED_MOVIES>/<REDACTED_MEDIA>"),
                ("Music", "<PROTECTED_MUSIC>/<REDACTED_MEDIA>"),
            ];

            for (folder, repl) in &personal_folders {
                let target = format!("/{}", folder);
                if cleaned.contains(&target) {
                    cleaned = cleaned.replace(&target, &format!("/{}", repl));
                    paths_count += 1;
                    rules.push("PERSONAL_FOLDER".to_string());
                }
            }
        }

        // 3. Username pseudonymization
        for user in &self.known_usernames {
            let user_path = format!("/Users/{}", user);
            if cleaned.contains(&user_path) {
                cleaned = cleaned.replace(&user_path, "/Users/user_masked");
                usernames_count += 1;
                rules.push("USERNAME_PATH".to_string());
            }
            let home_path = format!("/home/{}", user);
            if cleaned.contains(&home_path) {
                cleaned = cleaned.replace(&home_path, "/home/user_masked");
                usernames_count += 1;
                rules.push("USERNAME_PATH".to_string());
            }
        }

        // 4. Document metadata & query scrubbing (STRICT or BALANCED)
        if self.level == PrivacyScrubbingLevelSnapshot::Strict
            || self.level == PrivacyScrubbingLevelSnapshot::Balanced
        {
            let doc_extensions = [".pdf", ".docx", ".xlsx", ".pptx", ".keynote", ".pages"];
            for ext in &doc_extensions {
                if cleaned.contains(ext) {
                    meta_count += 1;
                    rules.push("DOCUMENT_METADATA".to_string());
                    break;
                }
            }

            if cleaned.contains('?') && cleaned.contains("https://") {
                if let Some(pos) = cleaned.find('?') {
                    cleaned = format!("{}?<REDACTED_QUERY>", &cleaned[..pos]);
                    meta_count += 1;
                    rules.push("URL_QUERY".to_string());
                }
            }
        }

        rules.sort();
        rules.dedup();

        let audit = PrivacyFilterAuditRecordSnapshot {
            sanitized_usernames_count: usernames_count,
            sanitized_paths_count: paths_count,
            sanitized_metadata_count: meta_count,
            redacted_secrets_count: secrets_count,
            level: self.level,
            rules_applied: rules,
            scan_proves_safe: false, // Mandatory non-negotiable charter invariant
        };

        (cleaned, audit)
    }

    fn sanitize_envelope(
        &self,
        envelope_id: &str,
        collector_id: &str,
        payload_summary: &str,
    ) -> SanitizedTelemetryEnvelopeSnapshot {
        let (clean_summary, audit) = self.sanitize_text(payload_summary);

        SanitizedTelemetryEnvelopeSnapshot {
            envelope_id: format!("sanitized-{}", envelope_id),
            collector_id: collector_id.to_string(),
            payload_summary: clean_summary,
            audit,
            scan_proves_safe: false, // Mandatory non-negotiable charter invariant
            is_mock: false,
        }
    }

    fn is_mock(&self) -> bool {
        false
    }
}

/// Deterministic mock privacy sanitizer for headless test fixtures and platform fallbacks.
pub struct MockMacOsPrivacySanitizer {
    pub level: PrivacyScrubbingLevelSnapshot,
}

impl MockMacOsPrivacySanitizer {
    pub fn new() -> Self {
        Self {
            level: PrivacyScrubbingLevelSnapshot::Balanced,
        }
    }

    pub fn with_level(level: PrivacyScrubbingLevelSnapshot) -> Self {
        Self { level }
    }
}

impl Default for MockMacOsPrivacySanitizer {
    fn default() -> Self {
        Self::new()
    }
}

impl MacOsPrivacySanitizer for MockMacOsPrivacySanitizer {
    fn sanitize_text(&self, text: &str) -> (String, PrivacyFilterAuditRecordSnapshot) {
        let mut rules = Vec::new();
        let mut usernames = 0;
        let mut paths = 0;
        let meta = 0;
        let mut secrets = 0;

        let mut cleaned = text.to_string();

        if cleaned.contains("/Users/") {
            cleaned = cleaned.replace("/Users/tharun", "/Users/user_mock");
            usernames += 1;
            rules.push("MOCK_USERNAME".to_string());
        }

        if cleaned.contains("Documents") {
            cleaned = cleaned.replace("Documents", "<PROTECTED_DOCUMENTS>");
            paths += 1;
            rules.push("MOCK_PATH".to_string());
        }

        if cleaned.contains("secret") || cleaned.contains("token") {
            secrets += 1;
            rules.push("MOCK_SECRET".to_string());
        }

        let audit = PrivacyFilterAuditRecordSnapshot {
            sanitized_usernames_count: usernames,
            sanitized_paths_count: paths,
            sanitized_metadata_count: meta,
            redacted_secrets_count: secrets,
            level: self.level,
            rules_applied: rules,
            scan_proves_safe: false, // Mandatory non-negotiable charter invariant
        };

        (cleaned, audit)
    }

    fn sanitize_envelope(
        &self,
        envelope_id: &str,
        collector_id: &str,
        payload_summary: &str,
    ) -> SanitizedTelemetryEnvelopeSnapshot {
        let (clean_summary, audit) = self.sanitize_text(payload_summary);

        SanitizedTelemetryEnvelopeSnapshot {
            envelope_id: format!("mock-sanitized-{}", envelope_id),
            collector_id: collector_id.to_string(),
            payload_summary: clean_summary,
            audit,
            scan_proves_safe: false, // Mandatory non-negotiable charter invariant
            is_mock: true,
        }
    }

    fn is_mock(&self) -> bool {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_privacy_scrubbing_level_strings() {
        assert_eq!(PrivacyScrubbingLevelSnapshot::Strict.as_str(), "STRICT");
        assert_eq!(PrivacyScrubbingLevelSnapshot::Balanced.as_str(), "BALANCED");
        assert_eq!(PrivacyScrubbingLevelSnapshot::Minimal.as_str(), "MINIMAL");
    }

    #[test]
    fn test_privacy_rule_categories() {
        assert_eq!(PrivacyRuleCategorySnapshot::Username.as_str(), "USERNAME");
        assert_eq!(
            PrivacyRuleCategorySnapshot::PersonalFolder.as_str(),
            "PERSONAL_FOLDER"
        );
        assert_eq!(
            PrivacyRuleCategorySnapshot::ProtectedVault.as_str(),
            "PROTECTED_VAULT"
        );
        assert_eq!(
            PrivacyRuleCategorySnapshot::DocumentMetadata.as_str(),
            "DOCUMENT_METADATA"
        );
        assert_eq!(
            PrivacyRuleCategorySnapshot::TokenOrSecret.as_str(),
            "TOKEN_OR_SECRET"
        );
    }

    #[test]
    fn test_audit_record_total_redactions() {
        let audit = PrivacyFilterAuditRecordSnapshot {
            sanitized_usernames_count: 2,
            sanitized_paths_count: 3,
            sanitized_metadata_count: 1,
            redacted_secrets_count: 4,
            level: PrivacyScrubbingLevelSnapshot::Balanced,
            rules_applied: vec!["R1".to_string(), "R2".to_string()],
            scan_proves_safe: false,
        };

        assert_eq!(audit.total_redactions(), 10);
        assert!(!audit.scan_proves_safe);

        let json = audit.to_json_summary();
        assert!(json.contains("\"total_redactions\":10"));
        assert!(json.contains("\"scan_proves_safe\":false"));
    }

    #[test]
    fn test_path_and_vault_sanitization() {
        let filter = MacOsPrivacyFilterCollector::new(PrivacyScrubbingLevelSnapshot::Balanced);

        let raw = "/Users/tharungodwin/.ssh/id_rsa and /Users/tharungodwin/Documents/report.pdf";
        let (cleaned, audit) = filter.sanitize_text(raw);

        assert!(cleaned.contains("<PROTECTED_KEY_VAULT>/ssh"));
        assert!(cleaned.contains("<PROTECTED_DOCUMENTS>/<REDACTED_DOCUMENT>"));
        assert!(cleaned.contains("/Users/user_masked"));
        assert!(audit.sanitized_paths_count >= 2);
        assert!(audit.sanitized_usernames_count >= 1);
        assert!(!audit.scan_proves_safe);
    }

    #[test]
    fn test_secret_redaction() {
        let filter = MacOsPrivacyFilterCollector::new(PrivacyScrubbingLevelSnapshot::Balanced);

        let raw = "Auth: Bearer secret_token_value_12345678 and key=AKIAIOSFODNN7EXAMPLE12";
        let (cleaned, audit) = filter.sanitize_text(raw);

        assert!(cleaned.contains("Bearer <REDACTED_TOKEN>"));
        assert!(cleaned.contains("<REDACTED_AWS_KEY>"));
        assert_eq!(audit.redacted_secrets_count, 2);
        assert!(!audit.scan_proves_safe);
    }

    #[test]
    fn test_envelope_sanitization_invariants() {
        let filter = MacOsPrivacyFilterCollector::new(PrivacyScrubbingLevelSnapshot::Strict);

        let env =
            filter.sanitize_envelope("env-101", "fsevents", "/Users/admin/Downloads/secret.docx");

        assert_eq!(env.envelope_id, "sanitized-env-101");
        assert_eq!(env.collector_id, "fsevents");
        assert!(!env.scan_proves_safe);
        assert!(!env.audit.scan_proves_safe);
        assert!(!env.is_mock);
        assert!(env.payload_summary.contains("<PROTECTED_DOWNLOADS>"));
    }

    #[test]
    fn test_mock_privacy_sanitizer() {
        let mock = MockMacOsPrivacySanitizer::new();
        assert!(mock.is_mock());

        let env = mock.sanitize_envelope("mock-1", "test", "/Users/tharun/Documents/test.txt");
        assert!(env.is_mock);
        assert!(!env.scan_proves_safe);
        assert!(!env.audit.scan_proves_safe);
        assert!(env.payload_summary.contains("/Users/user_mock"));
        assert!(env.payload_summary.contains("<PROTECTED_DOCUMENTS>"));
    }
}
