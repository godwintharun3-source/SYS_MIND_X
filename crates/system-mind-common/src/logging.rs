//! Structured log record formatting with sensitive data redaction for native Rust components.

use std::fmt;

/// Replaces raw tokens, private key headers, and bearer credentials with redaction markers.
pub fn sanitize_log_text(text: &str) -> String {
    if text.contains("-----BEGIN") && text.contains("PRIVATE KEY-----") {
        return "[REDACTED_SECRET]".to_string();
    }

    if text.starts_with("Bearer ") || text.starts_with("bearer ") {
        return "Bearer [REDACTED_SECRET]".to_string();
    }

    if text.starts_with("ghp_") || text.starts_with("sk-") || text.starts_with("AIzaSy") {
        return "[REDACTED_SECRET]".to_string();
    }

    text.to_string()
}

/// Checks whether a field key name refers to sensitive credentials.
pub fn is_sensitive_key(key: &str) -> bool {
    let lower = key.to_lowercase();
    lower.contains("password")
        || lower.contains("passwd")
        || lower.contains("token")
        || lower.contains("secret")
        || lower.contains("api_key")
        || lower.contains("apikey")
        || lower.contains("credential")
        || lower.contains("private_key")
        || lower.contains("privatekey")
        || lower.contains("auth")
        || lower.contains("bearer")
        || lower.contains("session_id")
}

/// Structured log record serializable to canonical single-line JSON with automatic redaction.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StructuredLogRecord {
    pub timestamp_iso: String,
    pub level: String,
    pub subsystem: String,
    pub event: String,
    pub fields: Vec<(String, String)>,
}

impl StructuredLogRecord {
    pub fn new(
        timestamp_iso: impl Into<String>,
        level: impl Into<String>,
        subsystem: impl Into<String>,
        event: impl Into<String>,
    ) -> Self {
        Self {
            timestamp_iso: timestamp_iso.into(),
            level: level.into(),
            subsystem: subsystem.into(),
            event: event.into(),
            fields: Vec::new(),
        }
    }

    /// Add a key-value context field to the log record.
    pub fn with_field(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.fields.push((key.into(), value.into()));
        self
    }

    /// Serializes the log record to a single-line JSON string with all sensitive data scrubbed.
    pub fn to_json(&self) -> String {
        let clean_event = sanitize_log_text(&self.event);

        let mut fields_json = String::new();
        fields_json.push('{');
        for (i, (k, v)) in self.fields.iter().enumerate() {
            if i > 0 {
                fields_json.push_str(", ");
            }
            let sanitized_v = if is_sensitive_key(k) {
                "[REDACTED_SECRET]".to_string()
            } else {
                sanitize_log_text(v)
            };
            fields_json.push_str(&format!("\"{}\": \"{}\"", k, sanitized_v));
        }
        fields_json.push('}');

        format!(
            "{{\"timestamp_iso\": \"{}\", \"level\": \"{}\", \"subsystem\": \"{}\", \"event\": \"{}\", \"context\": {}}}",
            self.timestamp_iso,
            self.level,
            self.subsystem,
            clean_event,
            fields_json
        )
    }
}

impl fmt::Display for StructuredLogRecord {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_json())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_structured_log_record_json_serialization() {
        let record = StructuredLogRecord::new(
            "2026-11-16T13:45:00Z",
            "INFO",
            "system_mind.broker",
            "capability_authorized",
        )
        .with_field("action_id", "act-001")
        .with_field("duration_ms", "1.5");

        let json_str = record.to_json();
        assert!(json_str.contains("\"level\": \"INFO\""));
        assert!(json_str.contains("\"subsystem\": \"system_mind.broker\""));
        assert!(json_str.contains("\"action_id\": \"act-001\""));
    }

    #[test]
    fn test_structured_log_record_redacts_sensitive_keys() {
        let record = StructuredLogRecord::new(
            "2026-11-16T13:45:00Z",
            "ERROR",
            "system_mind.broker",
            "auth_failed",
        )
        .with_field("user_id", "admin")
        .with_field("api_key", "secret_live_key_9999")
        .with_field("session_token", "eyJhbGciOiJIUzI1Ni...");

        let json_str = record.to_json();
        assert!(!json_str.contains("secret_live_key_9999"));
        assert!(!json_str.contains("eyJhbGciOiJIUzI1Ni..."));
        assert!(json_str.contains("\"api_key\": \"[REDACTED_SECRET]\""));
        assert!(json_str.contains("\"session_token\": \"[REDACTED_SECRET]\""));
        assert!(json_str.contains("\"user_id\": \"admin\""));
    }

    #[test]
    fn test_structured_log_record_redacts_event_with_tokens() {
        let record = StructuredLogRecord::new(
            "2026-11-16T13:45:00Z",
            "WARNING",
            "system_mind.broker",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        );

        let json_str = record.to_json();
        assert!(!json_str.contains("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."));
        assert!(json_str.contains("Bearer [REDACTED_SECRET]"));
    }
}
