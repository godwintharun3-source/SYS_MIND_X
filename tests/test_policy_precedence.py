"""Tests for Identity, Role, Approval, and Policy Precedence Hierarchy in SYSTEM MIND X."""

from __future__ import annotations

import pytest

from system_mind.contracts.models import TypedActionContract
from system_mind.core.types import (
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)
from system_mind.governance.models import (
    ActorIdentity,
    AuthorizationVerdict,
    IdentityType,
    PolicyEffect,
    PolicyPrecedenceTier,
    PolicyRule,
    SecurityRole,
    SecurityRoleType,
)
from system_mind.governance.precedence import PolicyPrecedenceEngine


def test_unauthenticated_identity_rejected():
    """Verify that unauthenticated callers are rejected immediately."""
    unauth_identity = ActorIdentity(
        identity_id="caller-unauth",
        identity_type=IdentityType.SANDBOXED_PEER_AGENT,
        principal_name="untrusted_agent",
        authenticated=False,
    )
    role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.AI_ADVISORY_PLANNER]
    contract = TypedActionContract(
        contract_id="act-001",
        capability_id="telemetry.read",
        target_entity_id="entity-sys",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )

    result = PolicyPrecedenceEngine.evaluate_authorization(
        identity=unauth_identity,
        role=role,
        contract=contract,
    )
    assert result.authorized is False
    assert result.verdict == AuthorizationVerdict.DENIED_UNAUTHENTICATED


def test_tier_1_hard_invariants_override_all_roles():
    """Verify that Tier 1 Charter Invariants cannot be overridden even by SYSTEM_ADMINISTRATOR."""
    admin_identity = ActorIdentity(
        identity_id="admin-001",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name="admin",
        authenticated=True,
    )
    admin_role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.SYSTEM_ADMINISTRATOR]

    # Attempt 1: Raw shell execution
    raw_shell_contract = TypedActionContract(
        contract_id="act-shell",
        capability_id="broker.raw_shell",
        target_entity_id="shell",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )
    res_shell = PolicyPrecedenceEngine.evaluate_authorization(
        identity=admin_identity,
        role=admin_role,
        contract=raw_shell_contract,
        approval_confirmed=True,
    )
    assert res_shell.authorized is False
    assert res_shell.verdict == AuthorizationVerdict.DENIED_CHARTER_INVARIANT
    assert res_shell.effective_tier == PolicyPrecedenceTier.TIER_1_HARD_CHARTER_INVARIANTS

    # Attempt 2: Disabling SIP
    sip_contract = TypedActionContract(
        contract_id="act-sip",
        capability_id="broker.security.disable_sip",
        target_entity_id="sip",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )
    res_sip = PolicyPrecedenceEngine.evaluate_authorization(
        identity=admin_identity,
        role=admin_role,
        contract=sip_contract,
        approval_confirmed=True,
    )
    assert res_sip.authorized is False
    assert res_sip.verdict == AuthorizationVerdict.DENIED_CHARTER_INVARIANT


def test_tier_1_autonomous_mutation_of_user_apps_blocked():
    """Verify that autonomous maintenance daemon is blocked from mutating USER_MANAGED components."""
    daemon_identity = ActorIdentity(
        identity_id="daemon-maintenance",
        identity_type=IdentityType.AUTONOMOUS_MAINTENANCE_DAEMON,
        principal_name="system_mind_maintenance_daemon",
        authenticated=True,
    )
    daemon_role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.SYSTEM_SERVICE_DAEMON]

    contract = TypedActionContract(
        contract_id="act-auto-user",
        capability_id="broker.daemon.maintenance",
        target_entity_id="/Applications/Google Chrome.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )

    res = PolicyPrecedenceEngine.evaluate_authorization(
        identity=daemon_identity,
        role=daemon_role,
        contract=contract,
    )
    assert res.authorized is False
    assert res.verdict == AuthorizationVerdict.DENIED_CHARTER_INVARIANT


def test_tier_2_enterprise_policy_overrides_user_and_ai():
    """Verify that Enterprise Organization Policies override user policies and AI proposals."""
    user_identity = ActorIdentity(
        identity_id="user-001",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name="developer",
        authenticated=True,
    )
    user_role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.OPERATOR_USER]

    contract = TypedActionContract(
        contract_id="act-app-install",
        capability_id="broker.app.mutate",
        target_entity_id="com.unapproved.tool",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    enterprise_rules = [
        PolicyRule(
            rule_id="ent-001",
            tier=PolicyPrecedenceTier.TIER_2_ENTERPRISE_ORGANIZATION_POLICY,
            capability_pattern="broker.app.*",
            effect=PolicyEffect.DENY,
            description="Enterprise MDM restricts third-party application mutations.",
        )
    ]
    user_rules = [
        PolicyRule(
            rule_id="usr-001",
            tier=PolicyPrecedenceTier.TIER_3_USER_EXPLICIT_SAFETY_POLICY,
            capability_pattern="broker.app.*",
            effect=PolicyEffect.ALLOW,
            description="User explicitly permits app mutations.",
        )
    ]

    res = PolicyPrecedenceEngine.evaluate_authorization(
        identity=user_identity,
        role=user_role,
        contract=contract,
        enterprise_rules=enterprise_rules,
        user_rules=user_rules,
        approval_confirmed=True,
    )
    assert res.authorized is False
    assert res.verdict == AuthorizationVerdict.DENIED_ENTERPRISE_POLICY
    assert res.effective_tier == PolicyPrecedenceTier.TIER_2_ENTERPRISE_ORGANIZATION_POLICY


def test_tier_3_user_policy_overrides_ai_proposal():
    """Verify that User Safety Policies override AI proposals."""
    ai_identity = ActorIdentity(
        identity_id="ai-planner",
        identity_type=IdentityType.AI_COGNITIVE_PLANNER,
        principal_name="system_mind_caretaker",
        authenticated=True,
    )
    ai_role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.AI_ASSISTED_OPERATOR]

    contract = TypedActionContract(
        contract_id="act-ai-clean",
        capability_id="broker.fs.write",
        target_entity_id="/Users/developer/.private/cache",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    user_rules = [
        PolicyRule(
            rule_id="usr-privacy-01",
            tier=PolicyPrecedenceTier.TIER_3_USER_EXPLICIT_SAFETY_POLICY,
            capability_pattern="broker.fs.*",
            effect=PolicyEffect.DENY,
            description="User privacy perimeter denies access to .private directory.",
        )
    ]

    res = PolicyPrecedenceEngine.evaluate_authorization(
        identity=ai_identity,
        role=ai_role,
        contract=contract,
        user_rules=user_rules,
        approval_confirmed=True,
    )
    assert res.authorized is False
    assert res.verdict == AuthorizationVerdict.DENIED_USER_POLICY
    assert res.effective_tier == PolicyPrecedenceTier.TIER_3_USER_EXPLICIT_SAFETY_POLICY


def test_role_authority_risk_tier_limit():
    """Verify that roles cannot execute actions exceeding their maximum risk tier."""
    planner_identity = ActorIdentity(
        identity_id="ai-planner",
        identity_type=IdentityType.AI_COGNITIVE_PLANNER,
        principal_name="system_mind_advisory",
        authenticated=True,
    )
    advisory_role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.AI_ADVISORY_PLANNER]

    contract = TypedActionContract(
        contract_id="act-mutate",
        capability_id="telemetry.read",
        target_entity_id="entity-fs",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,  # Advisory role only permits READ_ONLY
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )

    res = PolicyPrecedenceEngine.evaluate_authorization(
        identity=planner_identity,
        role=advisory_role,
        contract=contract,
    )
    assert res.authorized is False
    assert res.verdict == AuthorizationVerdict.DENIED_ROLE_AUTHORITY


def test_approval_requirement_and_two_person_biometric_gate():
    """Verify that explicit user approval and dual-person biometric confirmation are enforced."""
    user_identity = ActorIdentity(
        identity_id="user-001",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name="developer",
        authenticated=True,
    )
    user_role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.OPERATOR_USER]

    # Standard USER_EXPLICIT without approval
    contract_user_exp = TypedActionContract(
        contract_id="act-update",
        capability_id="broker.system.snapshot",
        target_entity_id="entity-snap",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=False,
    )
    res_no_app = PolicyPrecedenceEngine.evaluate_authorization(
        identity=user_identity,
        role=user_role,
        contract=contract_user_exp,
        approval_confirmed=False,
    )
    assert res_no_app.authorized is False
    assert res_no_app.verdict == AuthorizationVerdict.DENIED_APPROVAL_REQUIRED

    # Standard USER_EXPLICIT with approval
    res_with_app = PolicyPrecedenceEngine.evaluate_authorization(
        identity=user_identity,
        role=user_role,
        contract=contract_user_exp,
        approval_confirmed=True,
    )
    assert res_with_app.authorized is True
    assert res_with_app.verdict == AuthorizationVerdict.AUTHORIZED

    # TWO_PERSON_OR_BREAK_GLASS requiring biometric
    admin_identity = ActorIdentity(
        identity_id="admin-001",
        identity_type=IdentityType.LOCAL_CONSOLE_USER,
        principal_name="admin",
        authenticated=True,
    )
    admin_role = PolicyPrecedenceEngine.STANDARD_ROLES[SecurityRoleType.SYSTEM_ADMINISTRATOR]
    contract_dual = TypedActionContract(
        contract_id="act-dual",
        capability_id="broker.firmware.flash",
        target_entity_id="uefi-bios",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS,
        user_approved=True,
    )

    # Missing biometric confirmation
    res_no_bio = PolicyPrecedenceEngine.evaluate_authorization(
        identity=admin_identity,
        role=admin_role,
        contract=contract_dual,
        approval_confirmed=True,
        biometric_confirmed=False,
    )
    assert res_no_bio.authorized is False
    assert res_no_bio.verdict == AuthorizationVerdict.DENIED_APPROVAL_REQUIRED
    assert any("DualAuthorizationViolation" in v for v in res_no_bio.violations)

    # With biometric confirmation
    res_bio_ok = PolicyPrecedenceEngine.evaluate_authorization(
        identity=admin_identity,
        role=admin_role,
        contract=contract_dual,
        approval_confirmed=True,
        biometric_confirmed=True,
    )
    assert res_bio_ok.authorized is True
    assert res_bio_ok.verdict == AuthorizationVerdict.AUTHORIZED
