"""Unit and contract tests for the AI and native system split architecture decision records."""

import pytest

from system_mind.architecture.split import (
    AiNativeSplitValidator,
    ArchitectureDecisionRecord,
    PrivilegeBoundary,
    SplitBoundaryRegistry,
    SystemPlaneId,
)
from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    Reversibility,
)


def test_split_boundary_registry_completeness():
    """Verify that all four foundational AI/native split ADRs are registered and accepted."""
    adrs = SplitBoundaryRegistry.get_all()
    assert len(adrs) == 4

    expected_adrs = {"ADR-021", "ADR-022", "ADR-023", "ADR-024"}
    registered_adrs = {adr.adr_id for adr in adrs}
    assert registered_adrs == expected_adrs

    for adr in adrs:
        assert adr.status == "accepted"
        assert adr.title.strip()
        assert adr.context.strip()
        assert adr.decision.strip()
        assert len(adr.consequences) > 0
        assert len(adr.invariants) > 0


def test_split_registry_lookups():
    """Verify ADR retrieval by ID and filtering by system plane."""
    adr21 = SplitBoundaryRegistry.get("ADR-021")
    assert adr21.adr_id == "ADR-021"
    assert adr21.plane_id == SystemPlaneId.AI_COGNITIVE_PLANE
    assert adr21.privilege == PrivilegeBoundary.UNPRIVILEGED_SANDBOX

    adr22 = SplitBoundaryRegistry.get("ADR-022")
    assert adr22.plane_id == SystemPlaneId.NATIVE_EXECUTION_BROKER

    broker_adrs = SplitBoundaryRegistry.get_by_plane(SystemPlaneId.NATIVE_EXECUTION_BROKER)
    assert len(broker_adrs) == 1
    assert broker_adrs[0].adr_id == "ADR-022"

    with pytest.raises(KeyError):
        SplitBoundaryRegistry.get("ADR-999")


def test_validator_blocks_direct_ai_to_broker_bypass():
    """Verify that direct AI plane to broker/kernel bypass is strictly blocked (ADR-021)."""
    action = ActionContract(
        action_id="act-split-001",
        action_type="clean_cache",
        target_component="/tmp/cache",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["cache_exists"],
        postconditions=["cache_cleared"],
        rollback_plan="system_mind.recovery.rollback_cache",
    )

    # Direct AI -> Broker: Blocked
    permitted, violations = AiNativeSplitValidator.validate_execution_request(
        source_plane=SystemPlaneId.AI_COGNITIVE_PLANE,
        target_plane=SystemPlaneId.NATIVE_EXECUTION_BROKER,
        action=action,
        has_verified_grant=False,
    )
    assert permitted is False
    assert any("ADR-021 Split Violation: Direct execution dispatch" in v for v in violations)

    # Direct AI -> Kernel: Blocked
    permitted_k, violations_k = AiNativeSplitValidator.validate_execution_request(
        source_plane=SystemPlaneId.AI_COGNITIVE_PLANE,
        target_plane=SystemPlaneId.NATIVE_KERNEL_AUTHORITY,
        action=action,
    )
    assert permitted_k is False
    assert any("ADR-021 Split Violation" in v for v in violations_k)


def test_validator_enforces_verified_capability_grant_for_broker():
    """Verify that broker execution rejects requests lacking a verified capability grant (ADR-022)."""
    action = ActionContract(
        action_id="act-split-002",
        action_type="clean_cache",
        target_component="/tmp/cache",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["cache_exists"],
        postconditions=["cache_cleared"],
        rollback_plan="system_mind.recovery.rollback_cache",
    )

    # Dispatch to Broker without VerifiedCapabilityGrant: Blocked
    permitted_no_grant, violations_no_grant = AiNativeSplitValidator.validate_execution_request(
        source_plane=SystemPlaneId.DETERMINISTIC_POLICY_GATE,
        target_plane=SystemPlaneId.NATIVE_EXECUTION_BROKER,
        action=action,
        has_verified_grant=False,
    )
    assert permitted_no_grant is False
    assert any("lacking a verified capability grant" in v for v in violations_no_grant)

    # Dispatch to Broker WITH VerifiedCapabilityGrant: Permitted
    permitted_grant, violations_grant = AiNativeSplitValidator.validate_execution_request(
        source_plane=SystemPlaneId.DETERMINISTIC_POLICY_GATE,
        target_plane=SystemPlaneId.NATIVE_EXECUTION_BROKER,
        action=action,
        has_verified_grant=True,
    )
    assert permitted_grant is True
    assert len(violations_grant) == 0


def test_validator_blocks_raw_shell_in_split():
    """Verify that raw shell execution commands are rejected during split validation."""
    raw_shell_action = ActionContract(
        action_id="act-shell-split",
        action_type="raw_shell_execution",
        target_component="bash",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    permitted, violations = AiNativeSplitValidator.validate_execution_request(
        source_plane=SystemPlaneId.DETERMINISTIC_POLICY_GATE,
        target_plane=SystemPlaneId.NATIVE_EXECUTION_BROKER,
        action=raw_shell_action,
        has_verified_grant=True,
    )
    assert permitted is False
    assert any("raw shell execution" in v for v in violations)


def test_validator_blocks_native_security_subversion():
    """Verify that actions attempting to disable native OS security controls are hard-rejected (ADR-024)."""
    subversive_action = ActionContract(
        action_id="act-subvert-split",
        action_type="modify_security",
        target_component="csrutil_sip_disable",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    permitted, violations = AiNativeSplitValidator.validate_execution_request(
        source_plane=SystemPlaneId.DETERMINISTIC_POLICY_GATE,
        target_plane=SystemPlaneId.NATIVE_EXECUTION_BROKER,
        action=subversive_action,
        has_verified_grant=True,
    )
    assert permitted is False
    assert any("ADR-024 Split Violation: Actions attempting to disable or subvert native OS security controls" in v for v in violations)
