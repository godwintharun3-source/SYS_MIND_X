"""Typed data contracts and registry for SYSTEM MIND X user personas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set

from system_mind.core.types import ApprovalRequirement, OperationRiskTier


class PersonaType(str, Enum):
    """Target user persona classification."""

    PERSONAL = "PERSONAL"
    DEVELOPER = "DEVELOPER"
    ENTERPRISE_ADMIN = "ENTERPRISE_ADMIN"


@dataclass(frozen=True)
class UserPersona:
    """Specification of an operational persona and its governance envelope."""

    persona_type: PersonaType
    name: str
    description: str
    allowed_risk_tiers: Set[OperationRiskTier]
    default_approval_requirement: ApprovalRequirement
    allowed_monitored_roots: List[str]
    excluded_privacy_paths: List[str]
    can_auto_maintain_system: bool = True
    can_auto_modify_user_apps: bool = False  # Invariant: ALWAYS False
    requires_multi_person_for_critical: bool = False


class PersonaRegistry:
    """Factory and registry for standard verified user personas."""

    _PERSONAS: Dict[PersonaType, UserPersona] = {
        PersonaType.PERSONAL: UserPersona(
            persona_type=PersonaType.PERSONAL,
            name="Personal Computer User",
            description="Everyday desktop/laptop user seeking quiet, safe, automated system health.",
            allowed_risk_tiers={
                OperationRiskTier.READ_ONLY,
                OperationRiskTier.LOW_IMPACT,
                OperationRiskTier.MEDIUM_IMPACT,
            },
            default_approval_requirement=ApprovalRequirement.USER_EXPLICIT,
            allowed_monitored_roots=["/var/log", "/tmp", "system_telemetry"],
            excluded_privacy_paths=[
                "~/Documents",
                "~/Pictures",
                "~/Movies",
                "~/Music",
                "~/Downloads",
                "~/Desktop",
                "~/.ssh",
                "~/.gnupg",
                "~/Library/Keychains",
                "~/AppData",
            ],
            can_auto_maintain_system=True,
            can_auto_modify_user_apps=False,
            requires_multi_person_for_critical=False,
        ),
        PersonaType.DEVELOPER: UserPersona(
            persona_type=PersonaType.DEVELOPER,
            name="Software Developer & Engineering Team",
            description="Engineer requiring toolchain diagnostics, build inspection, and sandboxed test execution.",
            allowed_risk_tiers={
                OperationRiskTier.READ_ONLY,
                OperationRiskTier.LOW_IMPACT,
                OperationRiskTier.MEDIUM_IMPACT,
                OperationRiskTier.HIGH_IMPACT,
            },
            default_approval_requirement=ApprovalRequirement.USER_EXPLICIT,
            allowed_monitored_roots=["/var/log", "/tmp", "system_telemetry", "workspace_roots"],
            excluded_privacy_paths=[
                "~/.ssh",
                "~/.gnupg",
                "~/.aws",
                "~/.azure",
                "~/.config/gcloud",
                "**/.env",
                "**/*.pem",
                "**/*.key",
                "~/Documents",
                "~/Pictures",
            ],
            can_auto_maintain_system=True,
            can_auto_modify_user_apps=False,  # Developers manage their own venvs/dependencies!
            requires_multi_person_for_critical=False,
        ),
        PersonaType.ENTERPRISE_ADMIN: UserPersona(
            persona_type=PersonaType.ENTERPRISE_ADMIN,
            name="Enterprise & IT Administrator",
            description="Systems engineer managing fleet security, compliance, audit, and controlled configuration.",
            allowed_risk_tiers={
                OperationRiskTier.READ_ONLY,
                OperationRiskTier.LOW_IMPACT,
                OperationRiskTier.MEDIUM_IMPACT,
                OperationRiskTier.HIGH_IMPACT,
                OperationRiskTier.CRITICAL_PRIVILEGED,
            },
            default_approval_requirement=ApprovalRequirement.USER_EXPLICIT,
            allowed_monitored_roots=["/etc", "/var/log", "system_telemetry", "security_audit_logs"],
            excluded_privacy_paths=[
                "/Users/*/Documents",
                "/Users/*/Pictures",
                "/Users/*/Desktop",
                "/home/*/Documents",
                "/home/*/Pictures",
                "**/.ssh/id_*",
            ],
            can_auto_maintain_system=True,
            can_auto_modify_user_apps=False,
            requires_multi_person_for_critical=True,
        ),
    }

    @classmethod
    def get(cls, persona_type: PersonaType) -> UserPersona:
        """Retrieve the immutable persona specification."""
        if persona_type not in cls._PERSONAS:
            raise KeyError(f"Unknown persona type: {persona_type}")
        return cls._PERSONAS[persona_type]

    @classmethod
    def all_personas(cls) -> List[UserPersona]:
        """Return all registered personas."""
        return list(cls._PERSONAS.values())
