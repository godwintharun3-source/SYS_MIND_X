//! Masked secret value wrappers ensuring zero token leakage in logs and debug formats.

use crate::crypto::compute_payload_fingerprint;
use std::fmt;

/// Strongly typed secret value wrapper that masks contents in `Display` and `Debug` output.
#[derive(Clone, PartialEq, Eq)]
pub struct SecretValue {
    inner: String,
}

impl SecretValue {
    /// Create a new masked secret value.
    pub fn new(secret: impl Into<String>) -> Self {
        Self {
            inner: secret.into(),
        }
    }

    /// Explicitly unmask the raw secret value for authorized cryptographic operations.
    pub fn expose_secret(&self) -> &str {
        &self.inner
    }

    /// Compute a deterministic fingerprint for audit logging without leaking the secret content.
    pub fn fingerprint(&self) -> String {
        compute_payload_fingerprint(self.inner.as_bytes())
    }

    /// Returns the length of the underlying secret in bytes.
    pub fn len(&self) -> usize {
        self.inner.len()
    }

    /// Returns whether the secret is empty.
    pub fn is_empty(&self) -> bool {
        self.inner.is_empty()
    }
}

impl fmt::Display for SecretValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[REDACTED]")
    }
}

impl fmt::Debug for SecretValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "SecretValue([REDACTED])")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_secret_value_masks_in_display_and_debug() {
        let raw_token = "ghp_super_secret_developer_token_999";
        let secret = SecretValue::new(raw_token);

        // Display check
        let display_str = format!("{}", secret);
        assert_eq!(display_str, "[REDACTED]");
        assert!(!display_str.contains(raw_token));

        // Debug check
        let debug_str = format!("{:?}", secret);
        assert_eq!(debug_str, "SecretValue([REDACTED])");
        assert!(!debug_str.contains(raw_token));

        // Raw value only accessible via expose_secret()
        assert_eq!(secret.expose_secret(), raw_token);
    }

    #[test]
    fn test_secret_fingerprint_deterministic_and_safe() {
        let s1 = SecretValue::new("secret-key-alpha");
        let s2 = SecretValue::new("secret-key-alpha");
        let s3 = SecretValue::new("secret-key-beta");

        assert_eq!(s1.fingerprint(), s2.fingerprint());
        assert_ne!(s1.fingerprint(), s3.fingerprint());
        assert_eq!(s1.fingerprint().len(), 16);
    }
}
