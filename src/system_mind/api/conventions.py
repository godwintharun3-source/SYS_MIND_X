"""API convention validators, version negotiators, and structured response builders."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from system_mind.api.models import (
    ApiErrorDetail,
    ApiRequest,
    ApiResponse,
    ApiStatus,
    ApiVersion,
    ErrorCode,
    ErrorCodeCategory,
    VersionCompatibilityResult,
)
from system_mind.audit.ledger import SecretRedactor


class VersionNegotiator:
    """Manages semantic version negotiation and deprecation warnings."""

    SERVER_VERSION = ApiVersion(1, 0, 0)
    MIN_SUPPORTED_VERSION = ApiVersion(1, 0, 0)

    # Documented deprecation schedules
    DEPRECATED_METHODS: Dict[str, str] = {
        "system_mind.legacy.raw_query": (
            "Method 'system_mind.legacy.raw_query' is deprecated since v1.0.0 and will be removed in v2.0.0. "
            "Use 'system_mind.twin.query' instead."
        )
    }

    @classmethod
    def negotiate(cls, client_version_str: str, method_urn: str = "") -> VersionCompatibilityResult:
        """Negotiate client-server version compatibility under SemVer 2.0.0."""
        try:
            client_version = ApiVersion.from_string(client_version_str)
        except ValueError as e:
            return VersionCompatibilityResult(
                is_compatible=False,
                client_version=ApiVersion(0, 0, 0),
                server_version=cls.SERVER_VERSION,
                status_message=str(e),
            )

        # 1. Major version mismatch -> Incompatible breaking change
        if client_version.major != cls.SERVER_VERSION.major:
            return VersionCompatibilityResult(
                is_compatible=False,
                client_version=client_version,
                server_version=cls.SERVER_VERSION,
                status_message=(
                    f"Incompatible major version: Client requested v{client_version}, but server supports v{cls.SERVER_VERSION}. "
                    "Major version bumps indicate breaking contract changes."
                ),
            )

        # 2. Client minor version newer than server -> Incompatible forward reference
        if client_version.minor > cls.SERVER_VERSION.minor:
            return VersionCompatibilityResult(
                is_compatible=False,
                client_version=client_version,
                server_version=cls.SERVER_VERSION,
                status_message=(
                    f"Incompatible client version: Client requested minor v{client_version.minor}, "
                    f"but server is currently at minor v{cls.SERVER_VERSION.minor}."
                ),
            )

        # 3. Check deprecation schedule
        deprecation_warning = cls.DEPRECATED_METHODS.get(method_urn)

        return VersionCompatibilityResult(
            is_compatible=True,
            client_version=client_version,
            server_version=cls.SERVER_VERSION,
            status_message="API version successfully negotiated.",
            deprecation_warning=deprecation_warning,
        )


class ApiErrorFactory:
    """Factory creating sanitized, RFC 7807-compliant structured problem details."""

    @classmethod
    def create(
        cls,
        code: ErrorCode,
        category: ErrorCodeCategory,
        message: str,
        target: str,
        remediation_hint: str,
        is_retryable: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> ApiErrorDetail:
        """Construct a strongly typed ApiErrorDetail with recursive secret scrubbing."""
        clean_details = SecretRedactor.redact(details or {})
        return ApiErrorDetail(
            code=code,
            category=category,
            message=message,
            target=target,
            remediation_hint=remediation_hint,
            is_retryable=is_retryable,
            details=clean_details,
        )

    @classmethod
    def charter_violation(cls, message: str, target: str) -> ApiErrorDetail:
        """Construct standard Charter Invariant Violation error."""
        return cls.create(
            code=ErrorCode.E2001_CHARTER_INVARIANT_BREACH,
            category=ErrorCodeCategory.GOVERNANCE_CHARTER_INVARIANT,
            message=message,
            target=target,
            remediation_hint="Modify request to comply with inviolable product charter constraints (SC-01 to SC-08).",
            is_retryable=False,
        )

    @classmethod
    def precondition_failed(cls, message: str, target: str, hint: str) -> ApiErrorDetail:
        """Construct standard Precondition Failure error."""
        return cls.create(
            code=ErrorCode.E3001_PRECONDITION_FAILED,
            category=ErrorCodeCategory.PRECONDITION_FAILURE,
            message=message,
            target=target,
            remediation_hint=hint,
            is_retryable=True,
        )

    @classmethod
    def version_mismatch(cls, message: str, target: str) -> ApiErrorDetail:
        """Construct standard API Version Mismatch error."""
        return cls.create(
            code=ErrorCode.E1005_API_VERSION_MISMATCH,
            category=ErrorCodeCategory.AUTH_AND_IDENTITY,
            message=message,
            target=target,
            remediation_hint="Update client SDK to match server major version.",
            is_retryable=False,
        )


class ApiEnvelopeValidator:
    """Validates structural compliance and protocol invariants on incoming ApiRequests."""

    _URN_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")

    @classmethod
    def validate_request(cls, request: ApiRequest) -> Optional[ApiErrorDetail]:
        """Validate request headers, URN syntax, version compatibility, and idempotency keys."""
        # 1. Request ID presence
        if not request.request_id or not request.request_id.strip():
            return ApiErrorFactory.create(
                code=ErrorCode.E7002_INVALID_REQUEST_ENVELOPE,
                category=ErrorCodeCategory.SYSTEM_INTERNAL,
                message="Missing required header 'request_id'.",
                target="request_id",
                remediation_hint="Supply a valid UUIDv4 request_id with every API request.",
                is_retryable=False,
            )

        # 2. Method URN format
        if not cls._URN_PATTERN.match(request.method_urn):
            return ApiErrorFactory.create(
                code=ErrorCode.E7002_INVALID_REQUEST_ENVELOPE,
                category=ErrorCodeCategory.SYSTEM_INTERNAL,
                message=f"Invalid method URN '{request.method_urn}'. Must follow dot-delimited pattern (e.g. 'system_mind.twin.query').",
                target="method_urn",
                remediation_hint="Format method as dot-separated lowercase identifiers.",
                is_retryable=False,
            )

        # 3. Version Negotiation
        v_res = VersionNegotiator.negotiate(request.api_version, request.method_urn)
        if not v_res.is_compatible:
            return ApiErrorFactory.version_mismatch(v_res.status_message, target="api_version")

        # 4. Idempotency Key Requirement for Mutating Operations
        if request.is_mutating and not request.idempotency_key:
            return ApiErrorFactory.create(
                code=ErrorCode.E7003_IDEMPOTENCY_KEY_MISSING,
                category=ErrorCodeCategory.SYSTEM_INTERNAL,
                message=f"Mutating method '{request.method_urn}' mandates an 'idempotency_key'.",
                target="idempotency_key",
                remediation_hint="Provide a unique idempotency_key header to prevent duplicate execution of mutating operations.",
                is_retryable=False,
            )

        return None
