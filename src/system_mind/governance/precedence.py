"""Independent, deterministic Policy Precedence and Multi-Stakeholder Governance Engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from system_mind.contracts.models import TypedActionContract
from system_mind.core.types import (
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
)
from system_mind.governance.models import (
    ActorIdentity,
    AuthorizationVerdict,
    IdentityType,
    PolicyEffect,
    PolicyPrecedenceTier,
    PolicyRule,
    PrecedenceResolutionResult,
    SecurityRole,
    SecurityRoleType,
)


class PolicyPrecedenceEngine:
    """Evaluates identity, role capability, approval, and 4-tier precedence resolution."""

    _RISK_HIERARCHY = {
        OperationRiskTier.READ_ONLY: 0,
        OperationRiskTier.LOW_IMPACT: 1,
        OperationRiskTier.MEDIUM_IMPACT: 2,
        OperationRiskTier.HIGH_IMPACT: 3,
        OperationRiskTier.CRITICAL_PRIVILEGED: 4,
    }

    # Standard predefined security roles
    STANDARD_ROLES: Dict[SecurityRoleType, SecurityRole] = {
        SecurityRoleType.AI_ADVISORY_PLANNER: SecurityRole(
            role_type=SecurityRoleType.AI_ADVISORY_PLANNER,
            allowed_capabilities={"telemetry.read", "twin.query", "diagnosis.read"},
            max_permitted_risk_tier=OperationRiskTier.READ_ONLY,
            can_mutate_system=False,
        ),
        SecurityRoleType.AI_ASSISTED_OPERATOR: SecurityRole(
            role_type=SecurityRoleType.AI_ASSISTED_OPERATOR,
            allowed_capabilities={"telemetry.read", "twin.query", "proposal.synthesize", "broker.fs.write", "broker.service.restart"},
            max_permitted_risk_tier=OperationRiskTier.HIGH_IMPACT,
            can_mutate_system=False,
        ),
        SecurityRoleType.SYSTEM_SERVICE_DAEMON: SecurityRole(
            role_type=SecurityRoleType.SYSTEM_SERVICE_DAEMON,
            allowed_capabilities={"broker.daemon.maintenance", "broker.fs.cache_prune", "broker.security.hotfix"},
            max_permitted_risk_tier=OperationRiskTier.LOW_IMPACT,
            can_mutate_system=True,
        ),
        SecurityRoleType.OPERATOR_USER: SecurityRole(
            role_type=SecurityRoleType.OPERATOR_USER,
            allowed_capabilities={
                "broker.fs.write",
                "broker.process.manage",
                "broker.app.mutate",
                "broker.system.snapshot",
                "broker.service.restart",
            },
            max_permitted_risk_tier=OperationRiskTier.HIGH_IMPACT,
            can_mutate_system=True,
        ),
        SecurityRoleType.SYSTEM_ADMINISTRATOR: SecurityRole(
            role_type=SecurityRoleType.SYSTEM_ADMINISTRATOR,
            allowed_capabilities={"*"},
            max_permitted_risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
            can_mutate_system=True,
        ),
        SecurityRoleType.ENTERPRISE_CONTROLLER: SecurityRole(
            role_type=SecurityRoleType.ENTERPRISE_CONTROLLER,
            allowed_capabilities={"*"},
            max_permitted_risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
            can_mutate_system=True,
        ),
    }

    @classmethod
    def matches_capability(cls, pattern: str, capability: str) -> bool:
        """Evaluate if capability string matches rule pattern (supports wildcard suffix)."""
        if pattern == "*":
            return True
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return capability.startswith(prefix)
        return pattern == capability

    @classmethod
    def evaluate_authorization(
        cls,
        identity: ActorIdentity,
        role: SecurityRole,
        contract: TypedActionContract,
        enterprise_rules: Optional[List[PolicyRule]] = None,
        user_rules: Optional[List[PolicyRule]] = None,
        approval_confirmed: bool = False,
        biometric_confirmed: bool = False,
    ) -> PrecedenceResolutionResult:
        """Deterministically resolve authorization using the 4-tier policy precedence model."""
        violations: List[str] = []
        warnings: List[str] = []
        enterprise_rules = enterprise_rules or []
        user_rules = user_rules or []

        # Step 1: Authentication Check
        if not identity.authenticated:
            violations.append(
                f"UnauthenticatedIdentityViolation: Caller '{identity.principal_name}' is not authenticated."
            )
            return PrecedenceResolutionResult(
                verdict=AuthorizationVerdict.DENIED_UNAUTHENTICATED,
                authorized=False,
                effective_tier=PolicyPrecedenceTier.TIER_1_HARD_CHARTER_INVARIANTS,
                violations=violations,
            )

        # Step 2: Tier 1 - Inviolable Hard Charter Invariants (Supreme Precedence)
        # 2a. Raw shell / sudo prohibition
        if contract.capability_id in {"broker.raw_shell", "broker.root_shell", "broker.sudo"}:
            violations.append(
                "CharterInvariantViolation: Ambient raw shell or sudo execution is strictly prohibited by Charter SC-01."
            )
            return PrecedenceResolutionResult(
                verdict=AuthorizationVerdict.DENIED_CHARTER_INVARIANT,
                authorized=False,
                effective_tier=PolicyPrecedenceTier.TIER_1_HARD_CHARTER_INVARIANTS,
                violations=violations,
            )

        # 2b. Autonomous caller mutating USER_MANAGED or VENDOR_MANAGED components
        is_autonomous = identity.identity_type == IdentityType.AUTONOMOUS_MAINTENANCE_DAEMON
        if is_autonomous:
            if contract.target_ownership in {ComponentOwnership.USER_MANAGED, ComponentOwnership.VENDOR_MANAGED}:
                violations.append(
                    f"CharterInvariantViolation: Autonomous caller cannot modify {contract.target_ownership.value} "
                    f"component '{contract.target_entity_id}' under Charter SC-02."
                )
                return PrecedenceResolutionResult(
                    verdict=AuthorizationVerdict.DENIED_CHARTER_INVARIANT,
                    authorized=False,
                    effective_tier=PolicyPrecedenceTier.TIER_1_HARD_CHARTER_INVARIANTS,
                    violations=violations,
                )

        # 2c. Security authority subversion check
        if contract.capability_id in {"broker.security.disable_sip", "broker.security.disable_gatekeeper"}:
            violations.append(
                "CharterInvariantViolation: Disabling native OS security controls (SIP/Gatekeeper) is forbidden by SC-08."
            )
            return PrecedenceResolutionResult(
                verdict=AuthorizationVerdict.DENIED_CHARTER_INVARIANT,
                authorized=False,
                effective_tier=PolicyPrecedenceTier.TIER_1_HARD_CHARTER_INVARIANTS,
                violations=violations,
            )

        # Step 3: Tier 2 - Enterprise Organization Policies
        for rule in enterprise_rules:
            if rule.tier != PolicyPrecedenceTier.TIER_2_ENTERPRISE_ORGANIZATION_POLICY:
                continue
            if cls.matches_capability(rule.capability_pattern, contract.capability_id):
                if rule.effect == PolicyEffect.DENY:
                    violations.append(
                        f"EnterprisePolicyViolation: Operation '{contract.capability_id}' denied by enterprise "
                        f"policy rule '{rule.rule_id}': {rule.description}"
                    )
                    return PrecedenceResolutionResult(
                        verdict=AuthorizationVerdict.DENIED_ENTERPRISE_POLICY,
                        authorized=False,
                        effective_tier=PolicyPrecedenceTier.TIER_2_ENTERPRISE_ORGANIZATION_POLICY,
                        violations=violations,
                    )

        # Step 4: Tier 3 - User Explicit Safety Policies
        for rule in user_rules:
            if rule.tier != PolicyPrecedenceTier.TIER_3_USER_EXPLICIT_SAFETY_POLICY:
                continue
            if cls.matches_capability(rule.capability_pattern, contract.capability_id):
                if rule.effect == PolicyEffect.DENY:
                    violations.append(
                        f"UserPolicyViolation: Operation '{contract.capability_id}' denied by user safety "
                        f"policy rule '{rule.rule_id}': {rule.description}"
                    )
                    return PrecedenceResolutionResult(
                        verdict=AuthorizationVerdict.DENIED_USER_POLICY,
                        authorized=False,
                        effective_tier=PolicyPrecedenceTier.TIER_3_USER_EXPLICIT_SAFETY_POLICY,
                        violations=violations,
                    )

        # Step 5: Role Authority & Capability Scope
        contract_level = cls._RISK_HIERARCHY.get(contract.risk_tier, 0)
        role_max_level = cls._RISK_HIERARCHY.get(role.max_permitted_risk_tier, 0)
        if contract_level > role_max_level:
            violations.append(
                f"RoleAuthorityExceededViolation: Contract risk tier '{contract.risk_tier.value}' exceeds "
                f"maximum permitted tier '{role.max_permitted_risk_tier.value}' for role '{role.role_type.value}'."
            )
            return PrecedenceResolutionResult(
                verdict=AuthorizationVerdict.DENIED_ROLE_AUTHORITY,
                authorized=False,
                effective_tier=PolicyPrecedenceTier.TIER_4_AI_PLANNER_HEURISTIC_PROPOSAL,
                violations=violations,
            )

        has_cap = "*" in role.allowed_capabilities or any(
            cls.matches_capability(pattern, contract.capability_id) for pattern in role.allowed_capabilities
        )
        if not has_cap:
            violations.append(
                f"RoleCapabilityMissingViolation: Role '{role.role_type.value}' lacks capability grant "
                f"for '{contract.capability_id}'."
            )
            return PrecedenceResolutionResult(
                verdict=AuthorizationVerdict.DENIED_ROLE_AUTHORITY,
                authorized=False,
                effective_tier=PolicyPrecedenceTier.TIER_4_AI_PLANNER_HEURISTIC_PROPOSAL,
                violations=violations,
            )

        # Step 6: Approval Requirement Verification
        if contract.approval_requirement in {
            ApprovalRequirement.USER_EXPLICIT,
            ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS,
        }:
            if not approval_confirmed and not contract.user_approved:
                violations.append(
                    f"ApprovalRequiredViolation: Operation '{contract.contract_id}' requires explicit user confirmation "
                    f"under requirement '{contract.approval_requirement.value}'."
                )
                return PrecedenceResolutionResult(
                    verdict=AuthorizationVerdict.DENIED_APPROVAL_REQUIRED,
                    authorized=False,
                    effective_tier=PolicyPrecedenceTier.TIER_3_USER_EXPLICIT_SAFETY_POLICY,
                    violations=violations,
                )

            if contract.approval_requirement == ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS:
                if not biometric_confirmed:
                    violations.append(
                        f"DualAuthorizationViolation: Operation '{contract.contract_id}' requires dual authorization "
                        "with confirmed biometric authentication."
                    )
                    return PrecedenceResolutionResult(
                        verdict=AuthorizationVerdict.DENIED_APPROVAL_REQUIRED,
                        authorized=False,
                        effective_tier=PolicyPrecedenceTier.TIER_3_USER_EXPLICIT_SAFETY_POLICY,
                        violations=violations,
                    )

        # Step 7: Authorization Granted
        return PrecedenceResolutionResult(
            verdict=AuthorizationVerdict.AUTHORIZED,
            authorized=True,
            effective_tier=PolicyPrecedenceTier.TIER_4_AI_PLANNER_HEURISTIC_PROPOSAL,
            violations=[],
            warnings=warnings,
        )
