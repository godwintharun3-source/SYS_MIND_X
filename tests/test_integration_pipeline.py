"""Integration test for the cross-module control plane pipeline.

Verifies the integration between:
1. Temporal Observation & Digital Twin Graph
2. Deterministic Policy Precedence Engine
3. Typed Action Contracts & Precondition Evaluator
4. Immutable Audit Ledger with Cryptographic Hash Chaining
5. Charter Safety Invariants (SC-01, SC-02, SC-03)
"""

from __future__ import annotations

import pytest

from system_mind.applications.models import (
    ApplicationProfile,
    ApplicationType,
    InstallScope,
)
from system_mind.applications.exclusion import UserAppExclusionEnforcer
from system_mind.audit.ledger import ImmutableAuditLedger, SecretRedactor
from system_mind.audit.models import AuditEventCategory, AuditEventSeverity, RetentionClass
from system_mind.contracts.models import (
    ApprovalRequirement,
    OperationRiskTier,
    PostconditionType,
    PreconditionType,
    PredicateOperator,
    Reversibility,
    RollbackContract,
    RollbackStrategy,
    TypedActionContract,
    TypedPostcondition,
    TypedPrecondition,
)
from system_mind.contracts.rules import ContractRuleEvaluator
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
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
)
from system_mind.twin.temporal import (
    FreshnessEvaluator,
    FreshnessMetadata,
    FreshnessState,
    ObservationType,
    ProvenanceMetadata,
    ProvenanceStatus,
    TemporalObservation,
)


@pytest.mark.integration
@pytest.mark.safety_critical
def test_full_governance_and_execution_pipeline():
    """Verify end-to-end flow from observation through twin, policy, contract, and audit."""
    # 1. Observation & Digital Twin Phase
    graph = DigitalTwinGraph()
    system_entity = TwinEntity(
        entity_id="entity:sys:macos",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="sensor.host_telemetry",
        attributes={"os_platform": "macOS", "arch": "arm64", "kernel": "Darwin 27.0.0"},
    )
    graph.add_entity(system_entity)

    obs_state = {"cpu_usage_pct": 14.2, "thermal_state": "NOMINAL"}
    obs = TemporalObservation(
        observation_id="obs:sensor:cpu:001",
        entity_id=system_entity.entity_id,
        observed_at="2026-11-16T12:00:00Z",
        observation_seq=1,
        observation_type=ObservationType.STATE_SNAPSHOT,
        observed_state=obs_state,
        provenance=ProvenanceMetadata(
            source_engine="ENG-01:telemetry",
            collector_method="mock_sensors",
            payload_sha256="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
            verification_status=ProvenanceStatus.VERIFIED_KERNEL,
        ),
        freshness=FreshnessMetadata(ttl_seconds=30.0, max_acceptable_staleness_seconds=60.0),
    )
    fresh_eval = FreshnessEvaluator.evaluate(obs, "2026-11-16T12:00:05Z")
    assert fresh_eval.freshness_state == FreshnessState.FRESH

    # 2. Action Contract Definition
    contract = TypedActionContract(
        contract_id="contract:sec-update:001",
        capability_id="system_mind.update.system_component",
        target_entity_id="entity:sys:macos",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=[
            TypedPrecondition(
                precondition_id="pre:disk-space",
                precondition_type=PreconditionType.STORAGE_CAPACITY,
                target_field="free_space_bytes",
                operator=PredicateOperator.GREATER_THAN_OR_EQUAL,
                expected_value=5000000000,
                description="Requires 5GB storage for security update",
            )
        ],
        postconditions=[
            TypedPostcondition(
                postcondition_id="post:service-active",
                postcondition_type=PostconditionType.SERVICE_LIFECYCLE,
                target_field="service_status",
                operator=PredicateOperator.EQUALS,
                expected_value="running",
                description="Security service must remain active",
            )
        ],
        rollback_contract=RollbackContract(
            strategy=RollbackStrategy.SNAPSHOT_REVERT,
            target_reference="com.apple.SecurityUpdate",
        ),
    )

    # 3. Policy Precedence Engine Phase
    operator_actor = ActorIdentity(
        identity_id="act:op:01",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name="admin@systemmind.local",
        authenticated=True,
    )
    role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.SYSTEM_ADMINISTRATOR]

    eval_result = PolicyPrecedenceEngine.evaluate_authorization(
        identity=operator_actor,
        role=role,
        contract=contract,
    )
    assert eval_result.verdict == AuthorizationVerdict.AUTHORIZED

    # 4. Action Precondition Evaluation Phase
    contract_eval = ContractRuleEvaluator()
    pre_result = contract_eval.evaluate_preconditions(
        contract=contract,
        system_state={"free_space_bytes": 100_000_000_000},
    )
    assert pre_result.all_satisfied is True

    # 5. Tamper-Evident Audit Ledger Phase
    ledger = ImmutableAuditLedger()
    event = ledger.append_event(
        event_id="evt:pipe:001",
        timestamp_iso="2026-11-16T12:00:05Z",
        event_category=AuditEventCategory.STATE_MUTATION,
        severity=AuditEventSeverity.INFO,
        retention_class=RetentionClass.SYSTEM_MUTATION,
        actor_principal=operator_actor.principal_name,
        identity_type=operator_actor.identity_type,
        target_component=contract.target_entity_id,
        target_ownership=contract.target_ownership,
        capability_id=contract.capability_id,
        contract_id=contract.contract_id,
        payload={
            "package": "com.apple.SecurityUpdate",
            "contract_id": contract.contract_id,
            "secret_key": "api_key_secret_must_be_redacted",
        },
    )

    assert event.sequence_number == 1
    # Secret redaction check
    assert event.payload["secret_key"] == SecretRedactor.REDACTION_MARKER
    assert len(event.event_hash) == 64
    assert ledger.verify_integrity().is_valid is True


@pytest.mark.integration
@pytest.mark.safety_critical
def test_pipeline_enforces_user_app_and_scan_not_safe_invariants():
    """Verify that user app mutation and quarantined execution fail across the pipeline."""
    # SC-02 Check: User Application Protection
    profile = ApplicationProfile(
        app_id="app:vscode",
        display_name="Visual Studio Code",
        app_type=ApplicationType.DEVELOPER_TOOLCHAIN,
        install_scope=InstallScope.USER_LOCAL,
        install_path="/Applications/Visual Studio Code.app",
        executable_path="/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
        ownership=ComponentOwnership.USER_MANAGED,
        managed_by="user",
        is_excluded_from_autonomous_updates=True,
    )
    exclusion_result = UserAppExclusionEnforcer.evaluate_profile(profile)
    assert exclusion_result.is_excluded is True
    assert "user-managed" in exclusion_result.reason.lower()

    # SC-03 Check: Scan != Safe
    evidence_quarantine = FileEvidenceRecord(
        file_path="/tmp/untrusted.bin",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=4096,
        mime_type="application/octet-stream",
        category=FileCategory.EXECUTABLE_BINARY,
        has_quarantine_marker=True,
    )
    quarantine_eval = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=evidence_quarantine,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
    )
    assert quarantine_eval.permitted is False
    assert quarantine_eval.is_native_execution_allowed is False

    # Statically inspected file still blocked from native execution under SC-03
    evidence_scanned = FileEvidenceRecord(
        file_path="/tmp/scanned.bin",
        sha256_hash="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        file_size_bytes=2048,
        mime_type="text/x-shellscript",
        category=FileCategory.SCRIPT_OR_INTERPRETER_PAYLOAD,
        static_scan_clean=True,
    )
    inspected_eval = FileTrustPolicyEvaluator.validate_handler_request(
        evidence=evidence_scanned,
        requested_mode=HandlerExecutionMode.NATIVE_HOST_EXECUTION,
    )
    assert inspected_eval.permitted is False
    assert inspected_eval.is_native_execution_allowed is False
    assert any("ScanDoesNotProveSafetyViolation" in v for v in inspected_eval.violations)
