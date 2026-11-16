//! SYSTEM MIND X Common: Core types, error models, and cryptographic primitives.

pub mod crypto;
pub mod error;
pub mod logging;
pub mod secret;
pub mod types;

pub use crypto::compute_payload_fingerprint;
pub use error::{BrokerError, ErrorCode, ErrorCodeCategory};
pub use logging::StructuredLogRecord;
pub use secret::SecretValue;
pub use types::{
    ApiStatus, CapabilityId, ComponentOwnership, FileTrustState, PrivilegeLevel, RiskTier,
};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_file_trust_native_execution_invariant() {
        assert!(!FileTrustState::UntrustedUnknown.permits_native_host_execution());
        assert!(!FileTrustState::Quarantined.permits_native_host_execution());
        assert!(!FileTrustState::StaticallyInspected.permits_native_host_execution());
        assert!(!FileTrustState::BlockedMalicious.permits_native_host_execution());

        assert!(FileTrustState::SystemCoreImmutable.permits_native_host_execution());
        assert!(FileTrustState::VendorSignedVerified.permits_native_host_execution());
        assert!(FileTrustState::UserAttested.permits_native_host_execution());
    }

    #[test]
    fn test_component_ownership_mutation_invariant() {
        assert!(ComponentOwnership::SystemManaged.permits_autonomous_mutation());
        assert!(!ComponentOwnership::VendorManaged.permits_autonomous_mutation());
        assert!(!ComponentOwnership::UserManaged.permits_autonomous_mutation());
    }
}
