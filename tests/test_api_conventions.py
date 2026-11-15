"""Unit and contract tests for SYSTEM MIND X API conventions, error model, and versioning."""

import pytest
from system_mind.api.conventions import (
    ApiEnvelopeValidator,
    ApiErrorFactory,
    VersionNegotiator,
)
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
from system_mind.governance.models import ActorIdentity, IdentityType, SecurityRoleType


def _make_actor(
    identity_id: str = "actor-ui-123",
    principal_name: str = "operator@systemmind.local",
    authenticated: bool = True,
) -> ActorIdentity:
    return ActorIdentity(
        identity_id=identity_id,
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name=principal_name,
        authenticated=authenticated,
        session_id="session-xyz-456",
    )


def test_semver_parsing_and_string_representation():
    """Verify semantic version parsing and stringification."""
    v1 = ApiVersion.from_string("1.2.3")
    assert v1.major == 1
    assert v1.minor == 2
    assert v1.patch == 3
    assert str(v1) == "1.2.3"

    v2 = ApiVersion.from_string(" 0.9.15 ")
    assert v2.major == 0
    assert v2.minor == 9
    assert v2.patch == 15

    # Invalid SemVer strings
    invalid_versions = ["v1.0", "1.0", "1.0.0.0", "alpha", "", "1.x.3"]
    for bad in invalid_versions:
        with pytest.raises(ValueError, match="Invalid SemVer string"):
            ApiVersion.from_string(bad)


def test_version_negotiator_compatible_and_incompatible():
    """Verify client-server SemVer negotiation rules."""
    # Server is currently 1.0.0
    res = VersionNegotiator.negotiate("1.0.0")
    assert res.is_compatible is True
    assert res.server_version == ApiVersion(1, 0, 0)
    assert res.client_version == ApiVersion(1, 0, 0)
    assert res.deprecation_warning is None

    # Minor version newer on client than server -> Incompatible
    res_client_newer = VersionNegotiator.negotiate("1.1.0")
    assert res_client_newer.is_compatible is False
    assert "Incompatible client version" in res_client_newer.status_message

    # Major version mismatch -> Incompatible breaking change
    res_major_mismatch = VersionNegotiator.negotiate("2.0.0")
    assert res_major_mismatch.is_compatible is False
    assert "Incompatible major version" in res_major_mismatch.status_message

    res_major_old = VersionNegotiator.negotiate("0.9.0")
    assert res_major_old.is_compatible is False
    assert "Incompatible major version" in res_major_old.status_message

    # Malformed version string -> Incompatible
    res_malformed = VersionNegotiator.negotiate("invalid-semver")
    assert res_malformed.is_compatible is False
    assert "Invalid SemVer string" in res_malformed.status_message


def test_version_negotiator_deprecation_warning():
    """Verify deprecation notices on slated method endpoints."""
    deprecated_urn = "system_mind.legacy.raw_query"
    res = VersionNegotiator.negotiate("1.0.0", method_urn=deprecated_urn)
    assert res.is_compatible is True
    assert res.deprecation_warning is not None
    assert "deprecated since v1.0.0 and will be removed in v2.0.0" in res.deprecation_warning

    # Active non-deprecated method
    res_active = VersionNegotiator.negotiate("1.0.0", method_urn="system_mind.twin.query")
    assert res_active.is_compatible is True
    assert res_active.deprecation_warning is None


def test_api_envelope_validation_missing_headers_and_invalid_urn():
    """Verify structural validation on incoming ApiRequest envelopes."""
    actor = _make_actor()

    # Missing request_id
    req_no_id = ApiRequest(
        request_id="",
        api_version="1.0.0",
        method_urn="system_mind.twin.query",
        caller_identity=actor,
    )
    err = ApiEnvelopeValidator.validate_request(req_no_id)
    assert err is not None
    assert err.code == ErrorCode.E7002_INVALID_REQUEST_ENVELOPE
    assert err.target == "request_id"

    # Invalid method URN syntax
    invalid_urns = ["TwinQuery", "system-mind-query", "system_mind..query", "system_mind.", ".twin"]
    for bad_urn in invalid_urns:
        req_bad_urn = ApiRequest(
            request_id="req-123",
            api_version="1.0.0",
            method_urn=bad_urn,
            caller_identity=actor,
        )
        err = ApiEnvelopeValidator.validate_request(req_bad_urn)
        assert err is not None
        assert err.code == ErrorCode.E7002_INVALID_REQUEST_ENVELOPE
        assert err.target == "method_urn"

    # Incompatible API version
    req_bad_version = ApiRequest(
        request_id="req-123",
        api_version="2.0.0",
        method_urn="system_mind.twin.query",
        caller_identity=actor,
    )
    err = ApiEnvelopeValidator.validate_request(req_bad_version)
    assert err is not None
    assert err.code == ErrorCode.E1005_API_VERSION_MISMATCH
    assert err.target == "api_version"


def test_idempotency_key_enforced_on_mutating_requests():
    """Verify that mutating operations mandate an idempotency_key."""
    actor = _make_actor()

    # Read-only request without idempotency_key is valid
    read_req = ApiRequest(
        request_id="req-read-1",
        api_version="1.0.0",
        method_urn="system_mind.twin.query",
        caller_identity=actor,
        is_mutating=False,
    )
    assert ApiEnvelopeValidator.validate_request(read_req) is None

    # Mutating request without idempotency_key is rejected
    mutating_no_key = ApiRequest(
        request_id="req-mut-1",
        api_version="1.0.0",
        method_urn="system_mind.updates.apply",
        caller_identity=actor,
        is_mutating=True,
        idempotency_key=None,
    )
    err = ApiEnvelopeValidator.validate_request(mutating_no_key)
    assert err is not None
    assert err.code == ErrorCode.E7003_IDEMPOTENCY_KEY_MISSING
    assert err.target == "idempotency_key"
    assert "mandates an 'idempotency_key'" in err.message

    # Mutating request with idempotency_key is valid
    mutating_with_key = ApiRequest(
        request_id="req-mut-2",
        api_version="1.0.0",
        method_urn="system_mind.updates.apply",
        caller_identity=actor,
        is_mutating=True,
        idempotency_key="idemp-uuid-789",
    )
    assert ApiEnvelopeValidator.validate_request(mutating_with_key) is None


def test_api_error_factory_scrubs_secrets():
    """Verify that ApiErrorFactory recursively sanitizes secret tokens."""
    raw_details = {
        "user_email": "operator@systemmind.local",
        "api_token": "ghp_SECRET_TOKEN_9876543210_XYZ",
        "nested": {
            "password": "SuperSecretPassword123!",
            "public_metric": 42,
        },
    }

    err = ApiErrorFactory.create(
        code=ErrorCode.E4001_CAPABILITY_NOT_FOUND,
        category=ErrorCodeCategory.BROKER_EXECUTION,
        message="Requested broker capability not found.",
        target="capability_broker",
        remediation_hint="Check registered capabilities in catalog.",
        is_retryable=False,
        details=raw_details,
    )

    assert err.code == ErrorCode.E4001_CAPABILITY_NOT_FOUND
    assert err.category == ErrorCodeCategory.BROKER_EXECUTION
    # Verify secrets were scrubbed
    assert err.details["api_token"] == "[REDACTED_SECRET]"
    assert err.details["nested"]["password"] == "[REDACTED_SECRET]"
    assert err.details["nested"]["public_metric"] == 42
    assert err.details["user_email"] == "operator@systemmind.local"


def test_rfc7807_error_taxonomy_ranges():
    """Verify categorized error codes and factory helper methods."""
    # Charter violation
    charter_err = ApiErrorFactory.charter_violation(
        message="Cannot mutate user project dependency.",
        target="src/package.json",
    )
    assert charter_err.code == ErrorCode.E2001_CHARTER_INVARIANT_BREACH
    assert charter_err.category == ErrorCodeCategory.GOVERNANCE_CHARTER_INVARIANT
    assert charter_err.is_retryable is False

    # Precondition failure
    pre_err = ApiErrorFactory.precondition_failed(
        message="Insufficient battery level (15% < 50%).",
        target="battery_level",
        hint="Connect system to AC power before maintenance.",
    )
    assert pre_err.code == ErrorCode.E3001_PRECONDITION_FAILED
    assert pre_err.category == ErrorCodeCategory.PRECONDITION_FAILURE
    assert pre_err.is_retryable is True

    # Version mismatch
    ver_err = ApiErrorFactory.version_mismatch(
        message="Major version mismatch.",
        target="api_version",
    )
    assert ver_err.code == ErrorCode.E1005_API_VERSION_MISMATCH
    assert ver_err.category == ErrorCodeCategory.AUTH_AND_IDENTITY
    assert ver_err.is_retryable is False


def test_api_response_envelope_creation():
    """Verify ApiResponse construction, status states, and audit tracking."""
    resp = ApiResponse(
        request_id="req-uuid-1",
        api_version="1.0.0",
        status=ApiStatus.SUCCESS,
        data={"twin_entities_count": 142},
        audit_event_id="audit-evt-777",
        duration_ms=12.4,
        warnings=["DeprecationNotice: system_mind.legacy.raw_query"],
    )
    assert resp.status == ApiStatus.SUCCESS
    assert resp.data["twin_entities_count"] == 142
    assert resp.audit_event_id == "audit-evt-777"
    assert len(resp.warnings) == 1
