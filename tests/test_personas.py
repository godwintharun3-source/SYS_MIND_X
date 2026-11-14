"""Tests for user persona governance envelopes and policy evaluation."""

import pytest

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    Reversibility,
)
from system_mind.personas.evaluator import (
    PersonaGovernanceError,
    PersonaPolicyEvaluator,
)
from system_mind.personas.models import PersonaRegistry, PersonaType


def test_persona_registry_invariants():
    """Verify registry invariants across all standard personas."""
    personas = PersonaRegistry.all_personas()
    assert len(personas) == 3

    for p in personas:
        # Invariant: Autonomous maintenance can NEVER modify user apps for any persona
        assert p.can_auto_modify_user_apps is False
        assert len(p.allowed_risk_tiers) > 0
        assert len(p.excluded_privacy_paths) > 0

    with pytest.raises(KeyError):
        PersonaRegistry.get("NON_EXISTENT_PERSONA")  # type: ignore


def test_personal_persona_risk_boundary_enforcement():
    """Verify personal persona strictly blocks high and critical impact operations."""
    personal = PersonaRegistry.get(PersonaType.PERSONAL)

    # 1. Low impact operation is permitted
    low_impact_action = ActionContract(
        action_id="pers-001",
        action_type="clean_temporary_cache",
        target_component="/tmp/user_cache",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["cache_exists"],
        postconditions=["cache_freed"],
    )
    res_low = PersonaPolicyEvaluator.evaluate(low_impact_action, persona=personal)
    assert res_low.is_permitted

    # 2. High impact operation is rejected for personal persona
    high_impact_action = ActionContract(
        action_id="pers-002",
        action_type="reconfigure_network_stack",
        target_component="system_network_interfaces",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=["interface_active"],
        postconditions=["interface_reconfigured"],
        rollback_plan="Revert network profile",
    )
    res_high = PersonaPolicyEvaluator.evaluate(high_impact_action, persona=personal)
    assert not res_high.is_permitted
    assert any("exceeds allowable boundaries for persona" in v for v in res_high.violations)

    with pytest.raises(PersonaGovernanceError) as exc_info:
        PersonaPolicyEvaluator.assert_permitted(high_impact_action, persona=personal)
    assert "Persona governance rejected" in str(exc_info.value)


def test_personal_persona_privacy_boundary_protection():
    """Verify personal persona blocks inspection of protected user files."""
    personal = PersonaRegistry.get(PersonaType.PERSONAL)

    privacy_breach_action = ActionContract(
        action_id="pers-003",
        action_type="inspect_file_content",
        target_component="~/Documents/financial_records.pdf",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )
    res = PersonaPolicyEvaluator.evaluate(privacy_breach_action, persona=personal)
    assert not res.is_permitted
    assert any("breaches protected privacy path" in v for v in res.violations)


def test_developer_persona_workspace_and_dependency_protection():
    """Verify developer persona allows scoped high impact, but forbids auto dependency mutation."""
    developer = PersonaRegistry.get(PersonaType.DEVELOPER)

    # 1. Scoped high impact developer build/test is permitted with approval
    dev_action = ActionContract(
        action_id="dev-001",
        action_type="rebuild_container_workspace",
        target_component="workspace_roots/project_sandbox",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=["docker_available"],
        postconditions=["container_running"],
        rollback_plan="Stop and remove container",
    )
    res_dev = PersonaPolicyEvaluator.evaluate(dev_action, persona=developer)
    assert res_dev.is_permitted
    assert any("Developer Notice: High impact operation" in n for n in res_dev.governance_notes)

    # 2. Autonomous updater attempting to mutate developer dependencies is blocked
    auto_dep_action = ActionContract(
        action_id="dev-002",
        action_type="update_packages",
        target_component="workspace_roots/my_project/.venv",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        preconditions=["venv_exists"],
        postconditions=["packages_updated"],
    )
    res_auto = PersonaPolicyEvaluator.evaluate(auto_dep_action, persona=developer)
    assert not res_auto.is_permitted
    assert any("Autonomous maintenance must never modify developer project dependencies" in v for v in res_auto.violations)

    # 3. Secret path access (.env or .ssh) is blocked
    secret_action = ActionContract(
        action_id="dev-003",
        action_type="read_secret_file",
        target_component="~/.ssh/id_ed25519",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )
    res_sec = PersonaPolicyEvaluator.evaluate(secret_action, persona=developer)
    assert not res_sec.is_permitted
    assert any("breaches protected privacy path" in v for v in res_sec.violations)


def test_enterprise_admin_critical_governance_and_dual_approval():
    """Verify enterprise admin requires dual-person approval or break-glass for critical operations."""
    enterprise = PersonaRegistry.get(PersonaType.ENTERPRISE_ADMIN)

    # 1. Critical operation without second approver or break-glass is rejected
    crit_action = ActionContract(
        action_id="ent-001",
        action_type="firewall_reconfigure",
        target_component="fleet_packet_filter",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        rollback_plan="Restore pf.conf baseline",
        preconditions=["verify_network_admin_privilege"],
        postconditions=["verify_packet_filter_active"],
    )
    res_crit = PersonaPolicyEvaluator.evaluate(crit_action, persona=enterprise)
    assert not res_crit.is_permitted
    assert any("requires verified dual-person authorization or an emergency break-glass token" in v for v in res_crit.violations)

    # 2. Critical operation with dual approval is permitted
    approved_crit = ActionContract(
        action_id="ent-002",
        action_type="firewall_reconfigure",
        target_component="fleet_packet_filter",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS,
        user_approved=True,
        rollback_plan="Restore pf.conf baseline",
        preconditions=["verify_network_admin_privilege"],
        postconditions=["verify_packet_filter_active"],
        metadata={"second_approver_id": "sec-lead-8841"},
    )
    res_appr = PersonaPolicyEvaluator.evaluate(approved_crit, persona=enterprise)
    assert res_appr.is_permitted

    # 3. Critical operation with break-glass token is permitted
    break_glass_crit = ActionContract(
        action_id="ent-003",
        action_type="firewall_reconfigure",
        target_component="fleet_packet_filter",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        rollback_plan="Restore pf.conf baseline",
        preconditions=["verify_network_admin_privilege"],
        postconditions=["verify_packet_filter_active"],
        metadata={"break_glass_token": "BG-TOK-INCIDENT-99124"},
    )
    res_bg = PersonaPolicyEvaluator.evaluate(break_glass_crit, persona=enterprise)
    assert res_bg.is_permitted


def test_persona_evaluator_inherits_charter_violations():
    """Verify that fundamental charter violations (like raw shell) are caught during persona evaluation."""
    raw_shell_action = ActionContract(
        action_id="viol-001",
        action_type="raw_shell_execution",
        target_component="/bin/sh",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )
    res = PersonaPolicyEvaluator.evaluate(raw_shell_action, persona_type=PersonaType.ENTERPRISE_ADMIN)
    assert not res.is_permitted
    assert any("raw shell execution" in v for v in res.violations)
