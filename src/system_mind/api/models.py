"""Data contracts, error models, and semantic versioning primitives for the SYSTEM MIND X API."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.governance.models import ActorIdentity


class ApiStatus(str, Enum):
    """Wire status of an API response envelope."""

    SUCCESS = "SUCCESS"
    CLIENT_ERROR = "CLIENT_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    POLICY_REJECTED = "POLICY_REJECTED"


class ErrorCodeCategory(str, Enum):
    """Broad classification of system error codes."""

    AUTH_AND_IDENTITY = "AUTH_AND_IDENTITY"
    GOVERNANCE_CHARTER_INVARIANT = "GOVERNANCE_CHARTER_INVARIANT"
    PRECONDITION_FAILURE = "PRECONDITION_FAILURE"
    BROKER_EXECUTION = "BROKER_EXECUTION"
    POSTCONDITION_AND_ROLLBACK = "POSTCONDITION_AND_ROLLBACK"
    PLATFORM_ADAPTER = "PLATFORM_ADAPTER"
    SYSTEM_INTERNAL = "SYSTEM_INTERNAL"


class ErrorCode(str, Enum):
    """Machine-readable, strongly typed error codes categorized by range."""

    # E1000..E1999: Authentication, Identity & Approval
    E1001_UNAUTHENTICATED_IDENTITY = "E1001_UNAUTHENTICATED_IDENTITY"
    E1002_INSUFFICIENT_ROLE_AUTHORITY = "E1002_INSUFFICIENT_ROLE_AUTHORITY"
    E1003_APPROVAL_REQUIRED = "E1003_APPROVAL_REQUIRED"
    E1004_BIOMETRIC_CONFIRMATION_MISSING = "E1004_BIOMETRIC_CONFIRMATION_MISSING"
    E1005_API_VERSION_MISMATCH = "E1005_API_VERSION_MISMATCH"

    # E2000..E2999: Governance & Charter Invariant Violations (Non-retryable)
    E2001_CHARTER_INVARIANT_BREACH = "E2001_CHARTER_INVARIANT_BREACH"
    E2002_USER_APP_AUTONOMOUS_MUTATION_BLOCKED = "E2002_USER_APP_AUTONOMOUS_MUTATION_BLOCKED"
    E2003_UNCONTAINED_FILE_EXECUTION_BLOCKED = "E2003_UNCONTAINED_FILE_EXECUTION_BLOCKED"
    E2004_SECURITY_CONTROL_SUBVERSION_BLOCKED = "E2004_SECURITY_CONTROL_SUBVERSION_BLOCKED"
    E2005_ENTERPRISE_POLICY_VIOLATION = "E2005_ENTERPRISE_POLICY_VIOLATION"

    # E3000..E3999: Precondition Failures
    E3001_PRECONDITION_FAILED = "E3001_PRECONDITION_FAILED"
    E3002_INSUFFICIENT_STORAGE = "E3002_INSUFFICIENT_STORAGE"
    E3003_AC_POWER_REQUIRED = "E3003_AC_POWER_REQUIRED"
    E3004_RECOVERY_SNAPSHOT_MISSING = "E3004_RECOVERY_SNAPSHOT_MISSING"

    # E4000..E4999: Broker Capability & Dispatch Failures
    E4001_CAPABILITY_NOT_FOUND = "E4001_CAPABILITY_NOT_FOUND"
    E4002_BROKER_DISPATCH_FAILED = "E4002_BROKER_DISPATCH_FAILED"
    E4003_BROKER_TIMEOUT = "E4003_BROKER_TIMEOUT"

    # E5000..E5999: Postcondition Failures & Atomic Rollback
    E5001_POSTCONDITION_FAILED_ROLLED_BACK = "E5001_POSTCONDITION_FAILED_ROLLED_BACK"
    E5002_ROLLBACK_EXECUTION_FAILED = "E5002_ROLLBACK_EXECUTION_FAILED"

    # E6000..E6999: Platform Adapter & Parity
    E6001_PLATFORM_NOT_SUPPORTED = "E6001_PLATFORM_NOT_SUPPORTED"
    E6002_CAPABILITY_DEGRADED = "E6002_CAPABILITY_DEGRADED"

    # E7000..E7999: System Internal & Request Malformation
    E7001_INTERNAL_SERVER_ERROR = "E7001_INTERNAL_SERVER_ERROR"
    E7002_INVALID_REQUEST_ENVELOPE = "E7002_INVALID_REQUEST_ENVELOPE"
    E7003_IDEMPOTENCY_KEY_MISSING = "E7003_IDEMPOTENCY_KEY_MISSING"


@dataclass(frozen=True)
class ApiErrorDetail:
    """RFC 7807-inspired structured problem details with actionable remediation."""

    code: ErrorCode
    category: ErrorCodeCategory
    message: str
    target: str
    remediation_hint: str
    is_retryable: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApiVersion:
    """Semantic Version (SemVer 2.0.0: MAJOR.MINOR.PATCH)."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def from_string(cls, version_str: str) -> ApiVersion:
        """Parse semantic version string (e.g. '1.2.3')."""
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str.strip())
        if not match:
            raise ValueError(f"Invalid SemVer string: '{version_str}'. Must follow MAJOR.MINOR.PATCH format.")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )


@dataclass(frozen=True)
class VersionCompatibilityResult:
    """Outcome of API client-server version negotiation."""

    is_compatible: bool
    client_version: ApiVersion
    server_version: ApiVersion
    status_message: str
    deprecation_warning: Optional[str] = None


@dataclass
class ApiRequest:
    """Standard wire envelope for API requests across execution planes."""

    request_id: str
    api_version: str
    method_urn: str
    caller_identity: ActorIdentity
    params: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    timestamp_iso: str = ""
    is_mutating: bool = False


@dataclass
class ApiResponse:
    """Standard wire envelope for API responses."""

    request_id: str
    api_version: str
    status: ApiStatus
    data: Optional[Any] = None
    error: Optional[ApiErrorDetail] = None
    audit_event_id: Optional[str] = None
    duration_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
