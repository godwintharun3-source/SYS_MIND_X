"""Context-aware Persona Governance and Policy Evaluator."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import List, Optional

from system_mind.core.charter import CharterValidator
from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
)
from system_mind.personas.models import PersonaRegistry, PersonaType, UserPersona


class PersonaGovernanceError(Exception):
    """Raised when an operation breaches persona-specific governance boundaries."""

    def __init__(self, message: str, violations: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.violations = violations or [message]


@dataclass
class PersonaEvaluationResult:
    """Outcome of evaluating an action within a persona's governance envelope."""

    is_permitted: bool
    persona_type: PersonaType
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    governance_notes: List[str] = field(default_factory=list)


class PersonaPolicyEvaluator:
    """Evaluates ActionContracts against the active UserPersona's governance constraints."""

    @staticmethod
    def _is_path_under_excluded(target: str, pattern: str) -> bool:
        """Check if target component matches or resides within an excluded privacy path."""
        t = target.replace("\\", "/").strip()
        p = pattern.replace("\\", "/").strip()

        # Direct match or glob match
        if fnmatch.fnmatch(t, p) or fnmatch.fnmatch(t, f"{p}/*") or fnmatch.fnmatch(t, f"{p}/**"):
            return True

        # Target is child of excluded directory (e.g. t='~/Documents/file.pdf', p='~/Documents')
        if t.startswith(f"{p}/"):
            return True

        # Handle home-relative matching (e.g. p='~/.ssh', t='/Users/name/.ssh/id_rsa')
        rel_p = p.lstrip("~/")
        if t.startswith(f"{rel_p}/") or f"/{rel_p}/" in t or t.endswith(f"/{rel_p}"):
            return True

        # Wildcard matching (e.g. p='**/.env' or p='**/*.key')
        if fnmatch.fnmatch(t, f"*/{rel_p}") or fnmatch.fnmatch(t, f"*{rel_p}"):
            return True

        return False

    @classmethod
    def evaluate(
        cls,
        action: ActionContract,
        persona: Optional[UserPersona] = None,
        persona_type: Optional[PersonaType] = None,
    ) -> PersonaEvaluationResult:
        """Evaluate an action against persona-specific governance rules."""
        if persona is None:
            ptype = persona_type or PersonaType.PERSONAL
            persona = PersonaRegistry.get(ptype)

        violations: List[str] = []
        warnings: List[str] = []
        notes: List[str] = []

        # 1. Base Charter Invariant Validation First
        charter_res = CharterValidator.validate(action)
        if not charter_res.is_valid:
            violations.extend(charter_res.violations)

        # 2. Risk Tier Boundaries
        if action.risk_tier not in persona.allowed_risk_tiers:
            violations.append(
                f"Governance Violation: Risk tier '{action.risk_tier.value}' exceeds allowable boundaries for persona '{persona.name}'."
            )

        # 3. Privacy Perimeter & Excluded Paths
        target = action.target_component
        for pattern in persona.excluded_privacy_paths:
            if cls._is_path_under_excluded(target, pattern):
                violations.append(
                    f"Privacy Boundary Violation: Target component '{target}' breaches protected privacy path '{pattern}' for persona '{persona.name}'."
                )
                break

        # 4. Multi-Person / Break-Glass Approval Requirement for Critical Enterprise Operations
        if (
            persona.requires_multi_person_for_critical
            and action.risk_tier == OperationRiskTier.CRITICAL_PRIVILEGED
        ):
            has_break_glass = action.metadata.get("break_glass_token") is not None
            has_dual_approval = (
                action.approval_requirement == ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS
                and action.metadata.get("second_approver_id") is not None
            )
            if not (has_break_glass or has_dual_approval):
                violations.append(
                    "Governance Violation: Enterprise critical privileged action requires verified dual-person authorization or an emergency break-glass token."
                )

        # 5. Developer Workspace Invariants
        if persona.persona_type == PersonaType.DEVELOPER:
            if action.is_autonomous_maintenance and action.target_ownership == ComponentOwnership.USER_MANAGED:
                violations.append(
                    "Governance Violation: Autonomous maintenance must never modify developer project dependencies, virtualenvs, or repositories."
                )
            if action.risk_tier == OperationRiskTier.HIGH_IMPACT:
                notes.append(
                    "Developer Notice: High impact operation scoped to active development workspace."
                )

        # 6. Personal User Invariants
        if persona.persona_type == PersonaType.PERSONAL:
            if action.risk_tier == OperationRiskTier.MEDIUM_IMPACT and not action.is_autonomous_maintenance:
                warnings.append(
                    "Personal User Notice: Medium impact action requires plain-language user comprehension review."
                )

        return PersonaEvaluationResult(
            is_permitted=(len(violations) == 0),
            persona_type=persona.persona_type,
            violations=violations,
            warnings=warnings,
            governance_notes=notes,
        )

    @classmethod
    def assert_permitted(
        cls,
        action: ActionContract,
        persona: Optional[UserPersona] = None,
        persona_type: Optional[PersonaType] = None,
    ) -> None:
        """Enforces evaluation, raising PersonaGovernanceError if not permitted."""
        res = cls.evaluate(action, persona=persona, persona_type=persona_type)
        if not res.is_permitted:
            msg = f"Persona governance rejected action '{action.action_id}': " + "; ".join(res.violations)
            raise PersonaGovernanceError(msg, violations=res.violations)
