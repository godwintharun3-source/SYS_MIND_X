//! Core domain types and enums for SYSTEM MIND X.

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CapabilityId {
    TelemetryRead,
    ProcessInspection,
    FileMetadataRead,
    ServiceRestart,
    PackageUpgrade,
    SnapshotRevert,
}

impl CapabilityId {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::TelemetryRead => "system_mind.telemetry.read",
            Self::ProcessInspection => "system_mind.process.inspect",
            Self::FileMetadataRead => "system_mind.file.metadata_read",
            Self::ServiceRestart => "system_mind.service.restart",
            Self::PackageUpgrade => "system_mind.package.upgrade",
            Self::SnapshotRevert => "system_mind.snapshot.revert",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum PrivilegeLevel {
    Unprivileged,
    ElevatedBrokerRequired,
    CriticalPrivileged,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum RiskTier {
    ReadTelemetry,
    LowImpact,
    MediumImpact,
    HighImpact,
    CriticalPrivileged,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FileTrustState {
    UntrustedUnknown,
    Quarantined,
    StaticallyInspected,
    SandboxVerified,
    UserAttested,
    VendorSignedVerified,
    SystemCoreImmutable,
    BlockedMalicious,
}

impl FileTrustState {
    /// Inviolable invariant: Is this file permitted to execute natively on host OS?
    pub fn permits_native_host_execution(&self) -> bool {
        matches!(
            self,
            Self::VendorSignedVerified | Self::SystemCoreImmutable | Self::UserAttested
        )
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ComponentOwnership {
    SystemManaged,
    VendorManaged,
    UserManaged,
}

impl ComponentOwnership {
    /// Inviolable invariant: Can autonomous maintenance mutate this component?
    pub fn permits_autonomous_mutation(&self) -> bool {
        matches!(self, Self::SystemManaged)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ApiStatus {
    Success,
    ClientError,
    ServerError,
    PolicyRejected,
}
