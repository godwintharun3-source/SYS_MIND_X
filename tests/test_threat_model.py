"""Unit and contract tests for SYSTEM MIND X STRIDE threat model and trust boundary enforcement."""

import pytest

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
    Reversibility,
)
from system_mind.personas.models import PersonaType
from system_mind.security.threat_model import (
    StrideCategory,
    ThreatModelRegistry,
    ThreatSeverity,
    ThreatVector,
    TrustBoundaryEnforcer,
    TrustZone,
)


def test_threat_model_stride_completeness():
    """Verify that all 6 STRIDE categories are formally represented in the registry."""
    threats = ThreatModelRegistry.get_all_threats()
    assert len(threats) >= 6

    stride_cats = {t.stride_category for t in threats}
    for expected_cat in StrideCategory:
        assert expected_cat in stride_cats, f"STRIDE category {expected_cat} missing from threat model"


def test_threat_model_trust_zone_coverage():
    """Verify that all 6 formal trust zones are addressed in threat sources or targets."""
    threats = ThreatModelRegistry.get_all_threats()
    referenced_zones = set()
    for t in threats:
        referenced_zones.add(t.source_zone)
        referenced_zones.add(t.target_zone)

    for zone in TrustZone:
        assert zone in referenced_zones, f"TrustZone {zone} not referenced in threat vectors"


def test_threat_model_query_by_stride_and_severity():
    """Verify query filtering by STRIDE category and threat severity."""
    tampering_threats = ThreatModelRegistry.get_by_stride(StrideCategory.TAMPERING)
    assert len(tampering_threats) >= 2
    for t in tampering_threats:
        assert t.stride_category == StrideCategory.TAMPERING

    critical_threats = ThreatModelRegistry.get_by_severity(ThreatSeverity.CRITICAL)
    assert len(critical_threats) >= 3
    for t in critical_threats:
        assert t.severity == ThreatSeverity.CRITICAL

    threat = ThreatModelRegistry.get_threat("THREAT-01")
    assert threat.threat_id == "THREAT-01"
    assert threat.stride_category == StrideCategory.ELEVATION_OF_PRIVILEGE

    with pytest.raises(KeyError):
        ThreatModelRegistry.get_threat("NONEXISTENT-THREAT")


def test_rule_of_strict_adjacency_enforcement():
    """Verify that direct AI Control Plane (Zone 2) to Broker (Zone 4) or Kernel (Zone 5) transitions are blocked."""
    action = ActionContract(
        action_id="act-adj-001",
        action_type="service_restart",
        target_component="/Library/LaunchDaemons/com.example.daemon.plist",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=["plist_valid"],
        postconditions=["service_running"],
        rollback_plan="system_mind.recovery.rollback_service",
    )

    # Zone 2 -> Zone 4: Blocked (Bypassing Policy Engine)
    allowed_z2_to_z4, violations_z2_to_z4 = TrustBoundaryEnforcer.validate_zone_transition(
        source_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
        target_zone=TrustZone.ZONE_4_PRIVILEGED_BROKER,
        action=action,
        persona_type=PersonaType.DEVELOPER,
    )
    assert not allowed_z2_to_z4
    assert any("Direct transition from ZONE_2_AI_CONTROL_PLANE to ZONE_4/ZONE_5 is strictly forbidden" in v for v in violations_z2_to_z4)

    # Zone 2 -> Zone 5: Blocked (Bypassing Policy Engine and Broker)
    allowed_z2_to_z5, violations_z2_to_z5 = TrustBoundaryEnforcer.validate_zone_transition(
        source_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
        target_zone=TrustZone.ZONE_5_KERNEL_HARDWARE,
        action=action,
        persona_type=PersonaType.DEVELOPER,
    )
    assert not allowed_z2_to_z5
    assert any("Direct transition from ZONE_2_AI_CONTROL_PLANE to ZONE_4/ZONE_5 is strictly forbidden" in v for v in violations_z2_to_z5)

    # Zone 2 -> Zone 3 (Policy Engine mediation): Permitted
    allowed_z2_to_z3, violations_z2_to_z3 = TrustBoundaryEnforcer.validate_zone_transition(
        source_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
        target_zone=TrustZone.ZONE_3_POLICY_ENGINE,
        action=action,
        persona_type=PersonaType.DEVELOPER,
    )
    assert allowed_z2_to_z3
    assert len(violations_z2_to_z3) == 0


def test_untrusted_zone_0_execution_block():
    """Verify that untrusted external files (Zone 0) cannot execute in Zone 1/5 without isolation."""
    uncontained_action = ActionContract(
        action_id="act-ext-001",
        action_type="file_execute",
        target_component="/tmp/downloads/installer.bin",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        file_containment=FileExecutionContainment.DENIED,
        preconditions=["file_exists"],
        postconditions=["executed"],
    )

    allowed, violations = TrustBoundaryEnforcer.validate_zone_transition(
        source_zone=TrustZone.ZONE_0_UNTRUSTED_EXTERNAL,
        target_zone=TrustZone.ZONE_1_USER_SPACE,
        action=uncontained_action,
        persona_type=PersonaType.DEVELOPER,
    )
    assert not allowed
    assert any("External Zone 0 files cannot execute in Zone 1/5 without verified containment" in v for v in violations)

    # With disposable isolation containment:
    isolated_action = ActionContract(
        action_id="act-ext-002",
        action_type="file_execute",
        target_component="/tmp/downloads/installer.bin",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        file_containment=FileExecutionContainment.DISPOSABLE_ISOLATION,
        preconditions=["file_exists"],
        postconditions=["executed_isolated"],
    )

    allowed_isolated, violations_isolated = TrustBoundaryEnforcer.validate_zone_transition(
        source_zone=TrustZone.ZONE_0_UNTRUSTED_EXTERNAL,
        target_zone=TrustZone.ZONE_1_USER_SPACE,
        action=isolated_action,
        persona_type=PersonaType.DEVELOPER,
    )
    assert allowed_isolated
    assert len(violations_isolated) == 0


def test_boundary_enforcer_blocks_charter_violations():
    """Verify that actions violating core charter invariants are rejected at boundary enforcement."""
    raw_shell_action = ActionContract(
        action_id="act-shell-001",
        action_type="raw_shell_execution",
        target_component="shell",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    allowed, violations = TrustBoundaryEnforcer.validate_zone_transition(
        source_zone=TrustZone.ZONE_3_POLICY_ENGINE,
        target_zone=TrustZone.ZONE_4_PRIVILEGED_BROKER,
        action=raw_shell_action,
        persona_type=PersonaType.ENTERPRISE_ADMIN,
    )
    assert not allowed
    assert any("raw shell execution" in v for v in violations)


def test_boundary_enforcer_blocks_persona_privacy_violations():
    """Verify that privacy boundary breaches are caught during boundary validation."""
    private_read_action = ActionContract(
        action_id="act-priv-001",
        action_type="file_read",
        target_component="~/.ssh/id_rsa",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["file_exists"],
        postconditions=["content_read"],
    )

    allowed, violations = TrustBoundaryEnforcer.validate_zone_transition(
        source_zone=TrustZone.ZONE_1_USER_SPACE,
        target_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
        action=private_read_action,
        persona_type=PersonaType.PERSONAL,
    )
    assert not allowed
    assert any("Privacy Boundary Violation" in v or "privacy path" in v for v in violations)
