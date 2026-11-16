"""End-to-end operator console governance session test.

Simulates a complete operator interaction session:
1. Client-Server SemVer negotiation (VersionNegotiator)
2. Read-only sensor telemetry request and envelope validation
3. Untrusted file inspection asserting SC-03 ('Scan != Safe')
4. Mutating request idempotency enforcement (E7003)
5. Mutating governance approval with client idempotency key & immutable audit ledger
6. User application autonomous mutation rejection under SC-02 with RFC 7807 problem details
"""

from __future__ import annotations

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
    ErrorCode,
    ErrorCodeCategory,
)
from system_mind.applications.exclusion import UserAppExclusionEnforcer
from system_mind.applications.models import (
    ApplicationProfile,
    ApplicationType,
    InstallScope,
)
from system_mind.audit.ledger import ImmutableAuditLedger, SecretRedactor
from system_mind.audit.models import (
    AuditEventCategory,
    AuditEventSeverity,
    RetentionClass,
)
from system_mind.contracts.models import (
    ApprovalRequirement,
    OperationRiskTier,
    Reversibility,
    RollbackContract,
    RollbackStrategy,
    TypedActionContract,
)
from system_mind.core.types import ComponentOwnership
from system_mind.files.models import (
    FileCategory,
    FileEvidenceRecord,
    FileTrustState,
    HandlerExecutionMode,
)
from system_mind.files.policy import FileTrustPolicyEvaluator
from system_mind.governance.models import (
    ActorIdentity,
    AuthorizationVerdict,
    IdentityType,
    SecurityRoleType,
)
from system_mind.governance.precedence import PolicyPrecedenceEngine


def _make_operator(
    identity_id: str = "actor-op-console",
    principal_name: str = "operator@systemmind.local",
) -> ActorIdentity:
    return ActorIdentity(
        identity_id=identity_id,
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name=principal_name,
        authenticated=True,
        session_id="sess-e2e-console-001",
    )


@pytest.mark.e2e
@pytest.mark.safety_critical
def test_operator_console_e2e_session():
    """Verify an end-to-end operator session traversing API envelopes, policy, and audit."""
    operator = _make_operator()

    # Step 1: Version Negotiation
    client_version_str = "1.0.0"
    compat_result = VersionNegotiator.negotiate(client_version_str)
    assert compat_result.is_compatible is True
    assert compat_result.deprecation_warning is None

    # Step 2: Read-Only Sensor Telemetry Request
    telemetry_req = ApiRequest(
        request_id="req-e2e-telemetry-01",
        api_version=client_version_str,
        method_urn="system_mind.sensors.get_metrics",
        caller_identity=operator,
        is_mutating=False,
        params={"scope": "hardware_summary"},
    )
    val_err = ApiEnvelopeValidator.validate_request(telemetry_req)
    assert val_err is None

    telemetry_resp = ApiResponse(
        request_id=telemetry_req.request_id,
        api_version=client_version_str,
        status=ApiStatus.SUCCESS,
        data={
            "cpu_usage_pct": 11.8,
            "memory_used_mb": 2048,
            "memory_total_mb": 16384,
            "broker_connected": True,
        },
    )
    assert telemetry_resp.status == ApiStatus.SUCCESS
    assert telemetry_resp.data["broker_connected"] is True

    # Step 3: File Trust Inspection - SC-03 'Scan != Safe' Enforcement
    file_evidence = FileEvidenceRecord(
        file_path="/Users/user/Downloads/unverified_helper.sh",
        sha256_hash="11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff",
        file_size_bytes=1024,
        mime_type="text/x-shellscript",
        category=FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD,
        static_scan_clean=True,  # Scan claims clean!
    )
    trust_eval = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=file_evidence,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
    )
    # Scan != Safe: Native execution must be blocked unconditionally
    assert trust_eval.permitted is False
    assert trust_eval.is_native_execution_allowed is False
    assert any("ScanDoesNotProveSafetyViolation" in v for v in trust_eval.violations)

    # Step 4: Mutating Request Without Idempotency Key -> Rejected by Envelope Validator
    mutating_no_key = ApiRequest(
        request_id="req-e2e-approval-01",
        api_version=client_version_str,
        method_urn="system_mind.governance.submit_approval",
        caller_identity=operator,
        is_mutating=True,
        idempotency_key=None,  # Missing idempotency key!
        params={"action_id": "act-security-remediation-001", "verdict": "APPROVED"},
    )
    err_missing_key = ApiEnvelopeValidator.validate_request(mutating_no_key)
    assert err_missing_key is not None
    assert err_missing_key.code == ErrorCode.E7003_IDEMPOTENCY_KEY_MISSING
    assert err_missing_key.target == "idempotency_key"

    # Step 5: Mutating Request With Client Idempotency Key -> Validated, Evaluated, and Audited
    valid_key = "idemp-uuid-e2e-9999"
    mutating_req = ApiRequest(
        request_id="req-e2e-approval-02",
        api_version=client_version_str,
        method_urn="system_mind.governance.submit_approval",
        caller_identity=operator,
        is_mutating=True,
        idempotency_key=valid_key,
        params={"action_id": "act-security-remediation-001", "verdict": "APPROVED"},
    )
    assert ApiEnvelopeValidator.validate_request(mutating_req) is None

    # Evaluate action contract governance
    contract = TypedActionContract(
        contract_id="act-security-remediation-001",
        capability_id="system_mind.remediation.apply_patch",
        target_entity_id="entity:os:patch",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        rollback_contract=RollbackContract(
            strategy=RollbackStrategy.SNAPSHOT_REVERT,
            target_reference="entity:os:patch",
        ),
    )
    role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.SYSTEM_ADMINISTRATOR]
    precedence_res = PolicyPrecedenceEngine.evaluate_authorization(
        identity=operator,
        role=role,
        contract=contract,
        approval_confirmed=True,
    )
    assert precedence_res.verdict == AuthorizationVerdict.AUTHORIZED

    # Append to Immutable Audit Ledger
    ledger = ImmutableAuditLedger()
    audit_ev = ledger.append_event(
        event_id="evt-e2e-001",
        timestamp_iso="2026-11-16T12:05:00Z",
        event_category=AuditEventCategory.APPROVAL_CONFIRMATION,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.POLICY_DECISION,
        actor_principal=operator.principal_name,
        identity_type=operator.identity_type,
        target_component=contract.target_entity_id,
        target_ownership=contract.target_ownership,
        capability_id=contract.capability_id,
        contract_id=contract.contract_id,
        payload={
            "idempotency_key": valid_key,
            "verdict": "APPROVED",
            "caller_token": "token_session_secret_to_redact",
        },
    )
    assert audit_ev.sequence_number == 1
    assert audit_ev.payload["caller_token"] == SecretRedactor.REDACTION_MARKER
    assert ledger.verify_integrity().is_valid is True


@pytest.mark.e2e
@pytest.mark.safety_critical
def test_e2e_user_app_mutation_blocked_with_rfc7807():
    """Verify that autonomous mutation of a user-managed application returns an RFC 7807 error."""
    operator = _make_operator()

    chrome_app = ApplicationProfile(
        app_id="app:chrome",
        display_name="Google Chrome",
        app_type=ApplicationType.USER_DESKTOP_APP,
        install_scope=InstallScope.USER_LOCAL,
        install_path="/Applications/Google Chrome.app",
        executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ownership=ComponentOwnership.USER_MANAGED,
        managed_by="user",
        is_excluded_from_autonomous_updates=True,
    )

    # 1. Evaluate Exclusion Rule
    verdict = UserAppExclusionEnforcer.evaluate_profile(chrome_app)
    assert verdict.is_excluded is True

    # 2. Construct RFC 7807 problem details
    problem = ApiErrorFactory.create(
        code=ErrorCode.E2002_USER_APP_AUTONOMOUS_MUTATION_BLOCKED,
        category=ErrorCodeCategory.GOVERNANCE_CHARTER_INVARIANT,
        message=f"Autonomous maintenance of USER_MANAGED application '{chrome_app.display_name}' is prohibited.",
        target=chrome_app.app_id,
        remediation_hint="User applications must be updated manually or with explicit user approval.",
        is_retryable=False,
        details={
            "matching_rule": verdict.matching_rule,
            "reason": verdict.reason,
            "auth_token": "bearer_secret_token_12345",
        },
    )

    assert problem.code == ErrorCode.E2002_USER_APP_AUTONOMOUS_MUTATION_BLOCKED
    assert problem.category == ErrorCodeCategory.GOVERNANCE_CHARTER_INVARIANT
    assert problem.is_retryable is False
    # Verify deep secret scrubbing on error detail payloads
    assert problem.details["auth_token"] == SecretRedactor.REDACTION_MARKER
    assert problem.details["matching_rule"] == "EXCL-RULE-01"
