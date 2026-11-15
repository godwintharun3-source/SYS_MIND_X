"""Data models for Identity, Role, Approval and Policy Precedence in SYSTEM MIND X."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from system_mind.core.types import ApprovalRequirement, OperationRiskTier


class IdentityType(str, Enum):
    """Classification of requesting actor identities."""

    LOCAL_CONSOLE_USER = "LOCAL_CONSOLE_USER"
    AI_COGNITIVE_PLANNER = "AI_COGNITIVE_PLANNER"
    AUTONOMOUS_MAINTENANCE_DAEMON = "AUTONOMOUS_MAINTENANCE_DAEMON"
    ENTERPRISE_MDM_ADMIN = "ENTERPRISE_MDM_ADMIN"
    SANDBOXED_PEER_AGENT = "SANDBOXED_PEER_AGENT"


class SecurityRoleType(str, Enum):
    """Role-based access authority classes."""

    AI_ADVISORY_PLANNER = "AI_ADVISORY_PLANNER"
    AI_ASSISTED_OPERATOR = "AI_ASSISTED_OPERATOR"
    SYSTEM_SERVICE_DAEMON = "SYSTEM_SERVICE_DAEMON"
    OPERATOR_USER = "OPERATOR_USER"
    SYSTEM_ADMINISTRATOR = "SYSTEM_ADMINISTRATOR"
    ENTERPRISE_CONTROLLER = "ENTERPRISE_CONTROLLER"


class PolicyPrecedenceTier(str, Enum):
    """The 4-tier policy precedence hierarchy where higher tiers strictly override lower tiers."""

    TIER_1_HARD_CHARTER_INVARIANTS = "TIER_1_HARD_CHARTER_INVARIANTS"
    TIER_2_ENTERPRISE_ORGANIZATION_POLICY = "TIER_2_ENTERPRISE_ORGANIZATION_POLICY"
    TIER_3_USER_EXPLICIT_SAFETY_POLICY = "TIER_3_USER_EXPLICIT_SAFETY_POLICY"
    TIER_4_AI_PLANNER_HEURISTIC_PROPOSAL = "TIER_4_AI_PLANNER_HEURISTIC_PROPOSAL"


class PolicyEffect(str, Enum):
    """Effect of a policy rule when matched."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class AuthorizationVerdict(str, Enum):
    """Outcome of governance authorization and precedence resolution."""

    AUTHORIZED = "AUTHORIZED"
    DENIED_CHARTER_INVARIANT = "DENIED_CHARTER_INVARIANT"
    DENIED_ENTERPRISE_POLICY = "DENIED_ENTERPRISE_POLICY"
    DENIED_USER_POLICY = "DENIED_USER_POLICY"
    DENIED_ROLE_AUTHORITY = "DENIED_ROLE_AUTHORITY"
    DENIED_APPROVAL_REQUIRED = "DENIED_APPROVAL_REQUIRED"
    DENIED_UNAUTHENTICATED = "DENIED_UNAUTHENTICATED"


@dataclass(frozen=True)
class ActorIdentity:
    """Strongly typed caller identity initiating an action proposal."""

    identity_id: str
    identity_type: IdentityType
    principal_name: str
    authenticated: bool = True
    auth_mechanism: str = "OS_SESSION"
    session_id: Optional[str] = None


@dataclass(frozen=True)
class SecurityRole:
    """Security role defining permitted capabilities and risk boundaries."""

    role_type: SecurityRoleType
    allowed_capabilities: Set[str]
    max_permitted_risk_tier: OperationRiskTier
    can_mutate_system: bool = False


@dataclass(frozen=True)
class PolicyRule:
    """A discrete governance rule bound to a specific precedence tier."""

    rule_id: str
    tier: PolicyPrecedenceTier
    capability_pattern: str  # Capability name or wildcard (e.g. "broker.fs.*", "*")
    effect: PolicyEffect
    description: str
    is_immutable: bool = False


@dataclass(frozen=True)
class ApprovalEvidence:
    """Cryptographic or human verification evidence confirming action approval."""

    approved_by: str
    approval_requirement: ApprovalRequirement
    timestamp_iso: str
    biometric_verified: bool = False
    token_hash: Optional[str] = None


@dataclass
class PrecedenceResolutionResult:
    """Final determination of the policy precedence engine."""

    verdict: AuthorizationVerdict
    authorized: bool
    effective_tier: PolicyPrecedenceTier
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
