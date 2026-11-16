//! Strongly typed error categories and structured problem details.

use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ErrorCodeCategory {
    AuthAndIdentity,
    GovernanceCharterInvariant,
    PreconditionFailure,
    BrokerExecution,
    PostconditionAndRollback,
    PlatformAdapter,
    SystemInternal,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ErrorCode {
    E1001UnauthenticatedIdentity,
    E1002InsufficientRoleAuthority,
    E2001CharterInvariantBreach,
    E2002UserAppAutonomousMutationBlocked,
    E2003UncontainedFileExecutionBlocked,
    E3001PreconditionFailed,
    E3002InsufficientStorage,
    E3003AcPowerRequired,
    E4001CapabilityNotFound,
    E4002BrokerDispatchFailed,
    E5001PostconditionFailedRolledBack,
    E6001PlatformNotSupported,
    E7001InternalServerError,
}

impl ErrorCode {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::E1001UnauthenticatedIdentity => "E1001_UNAUTHENTICATED_IDENTITY",
            Self::E1002InsufficientRoleAuthority => "E1002_INSUFFICIENT_ROLE_AUTHORITY",
            Self::E2001CharterInvariantBreach => "E2001_CHARTER_INVARIANT_BREACH",
            Self::E2002UserAppAutonomousMutationBlocked => "E2002_USER_APP_AUTONOMOUS_MUTATION_BLOCKED",
            Self::E2003UncontainedFileExecutionBlocked => "E2003_UNCONTAINED_FILE_EXECUTION_BLOCKED",
            Self::E3001PreconditionFailed => "E3001_PRECONDITION_FAILED",
            Self::E3002InsufficientStorage => "E3002_INSUFFICIENT_STORAGE",
            Self::E3003AcPowerRequired => "E3003_AC_POWER_REQUIRED",
            Self::E4001CapabilityNotFound => "E4001_CAPABILITY_NOT_FOUND",
            Self::E4002BrokerDispatchFailed => "E4002_BROKER_DISPATCH_FAILED",
            Self::E5001PostconditionFailedRolledBack => "E5001_POSTCONDITION_FAILED_ROLLED_BACK",
            Self::E6001PlatformNotSupported => "E6001_PLATFORM_NOT_SUPPORTED",
            Self::E7001InternalServerError => "E7001_INTERNAL_SERVER_ERROR",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrokerError {
    pub code: ErrorCode,
    pub category: ErrorCodeCategory,
    pub message: String,
    pub target: String,
    pub remediation_hint: String,
    pub is_retryable: bool,
}

impl BrokerError {
    pub fn new(
        code: ErrorCode,
        category: ErrorCodeCategory,
        message: impl Into<String>,
        target: impl Into<String>,
        remediation_hint: impl Into<String>,
        is_retryable: bool,
    ) -> Self {
        Self {
            code,
            category,
            message: message.into(),
            target: target.into(),
            remediation_hint: remediation_hint.into(),
            is_retryable,
        }
    }

    pub fn charter_violation(message: impl Into<String>, target: impl Into<String>) -> Self {
        Self::new(
            ErrorCode::E2001CharterInvariantBreach,
            ErrorCodeCategory::GovernanceCharterInvariant,
            message,
            target,
            "Comply with inviolable product charter constraints.",
            false,
        )
    }

    pub fn precondition_failed(
        message: impl Into<String>,
        target: impl Into<String>,
        hint: impl Into<String>,
    ) -> Self {
        Self::new(
            ErrorCode::E3001PreconditionFailed,
            ErrorCodeCategory::PreconditionFailure,
            message,
            target,
            hint,
            true,
        )
    }
}

impl fmt::Display for BrokerError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "[{}] {} (target: {})",
            self.code.as_str(),
            self.message,
            self.target
        )
    }
}

impl std::error::Error for BrokerError {}
