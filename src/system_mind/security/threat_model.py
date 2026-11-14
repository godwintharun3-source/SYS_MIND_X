"""STRIDE-aligned threat model, trust zone hierarchy, and boundary enforcement for SYSTEM MIND X."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from system_mind.core.charter import CharterValidator
from system_mind.core.types import (
    ActionContract,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
)
from system_mind.personas.evaluator import PersonaPolicyEvaluator
from system_mind.personas.models import PersonaRegistry, PersonaType


class TrustZone(str, Enum):
    """The six formal trust zones of the SYSTEM MIND architecture."""

    ZONE_0_UNTRUSTED_EXTERNAL = "ZONE_0_UNTRUSTED_EXTERNAL"
    ZONE_1_USER_SPACE = "ZONE_1_USER_SPACE"
    ZONE_2_AI_CONTROL_PLANE = "ZONE_2_AI_CONTROL_PLANE"
    ZONE_3_POLICY_ENGINE = "ZONE_3_POLICY_ENGINE"
    ZONE_4_PRIVILEGED_BROKER = "ZONE_4_PRIVILEGED_BROKER"
    ZONE_5_KERNEL_HARDWARE = "ZONE_5_KERNEL_HARDWARE"


class StrideCategory(str, Enum):
    """STRIDE security threat classification categories."""

    SPOOFING = "SPOOFING"
    TAMPERING = "TAMPERING"
    REPUDIATION = "REPUDIATION"
    INFORMATION_DISCLOSURE = "INFORMATION_DISCLOSURE"
    DENIAL_OF_SERVICE = "DENIAL_OF_SERVICE"
    ELEVATION_OF_PRIVILEGE = "ELEVATION_OF_PRIVILEGE"


class ThreatSeverity(str, Enum):
    """Severity ratings for security threat vectors."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class ThreatVector:
    """Formal specification of an identified threat vector and its architectural mitigation."""

    threat_id: str
    stride_category: StrideCategory
    title: str
    source_zone: TrustZone
    target_zone: TrustZone
    description: str
    severity: ThreatSeverity
    architectural_mitigation: str
    verification_mechanism: str


class ThreatModelRegistry:
    """Central registry of cataloged STRIDE threat vectors and mitigations."""

    _THREATS: Dict[str, ThreatVector] = {
        "THREAT-01": ThreatVector(
            threat_id="THREAT-01",
            stride_category=StrideCategory.ELEVATION_OF_PRIVILEGE,
            title="Raw Shell / Root Execution by AI Control Plane",
            source_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
            target_zone=TrustZone.ZONE_5_KERNEL_HARDWARE,
            description="Attacker or hallucinating LLM generates raw shell commands with ambient root or sudo rights.",
            severity=ThreatSeverity.CRITICAL,
            architectural_mitigation="AI control plane is strictly unprivileged; raw root/shell execution is hard-rejected by CharterValidator.",
            verification_mechanism="Charter Invariant 1 automated tests in test_charter_contracts.py.",
        ),
        "THREAT-02": ThreatVector(
            threat_id="THREAT-02",
            stride_category=StrideCategory.TAMPERING,
            title="Indirect Prompt Injection Altering Action Contracts",
            source_zone=TrustZone.ZONE_0_UNTRUSTED_EXTERNAL,
            target_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
            description="Untrusted document or web page embeds prompt injection instructions modifying action parameters.",
            severity=ThreatSeverity.CRITICAL,
            architectural_mitigation="Independent deterministic policy engine validates strongly typed dataclasses independently of LLM reasoning.",
            verification_mechanism="PersonaPolicyEvaluator and CharterValidator schema validation.",
        ),
        "THREAT-03": ThreatVector(
            threat_id="THREAT-03",
            stride_category=StrideCategory.INFORMATION_DISCLOSURE,
            title="Credential & Secret Exfiltration via Telemetry",
            source_zone=TrustZone.ZONE_1_USER_SPACE,
            target_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
            description="Diagnostic collector or agent reads SSH keys, passwords, or .env files into prompt context.",
            severity=ThreatSeverity.HIGH,
            architectural_mitigation="Strict privacy exclusion perimeters (~/.ssh, ~/.gnupg, ~/Documents, .env) with mandatory redaction.",
            verification_mechanism="Persona boundary tests in test_personas.py.",
        ),
        "THREAT-04": ThreatVector(
            threat_id="THREAT-04",
            stride_category=StrideCategory.REPUDIATION,
            title="Unaudited System State Modification",
            source_zone=TrustZone.ZONE_4_PRIVILEGED_BROKER,
            target_zone=TrustZone.ZONE_5_KERNEL_HARDWARE,
            description="State changes occur without cryptographic provenance, actor attribution, or rollback records.",
            severity=ThreatSeverity.HIGH,
            architectural_mitigation="Append-only immutable audit trail recording actor ID, timestamp, pre/post hashes, and recovery handles.",
            verification_mechanism="JourneyExecutionEngine audit trail validation in test_journeys.py.",
        ),
        "THREAT-05": ThreatVector(
            threat_id="THREAT-05",
            stride_category=StrideCategory.TAMPERING,
            title="Component Ownership Clobbering (Silent App Updates)",
            source_zone=TrustZone.ZONE_4_PRIVILEGED_BROKER,
            target_zone=TrustZone.ZONE_1_USER_SPACE,
            description="Autonomous maintenance engine updates or corrupts user productivity apps or developer virtualenvs.",
            severity=ThreatSeverity.HIGH,
            architectural_mitigation="Tripartite component ownership model; hardcoded non-interference invariant on USER_MANAGED components.",
            verification_mechanism="Component ownership tests in test_component_ownership.py.",
        ),
        "THREAT-06": ThreatVector(
            threat_id="THREAT-06",
            stride_category=StrideCategory.DENIAL_OF_SERVICE,
            title="Uncontained Execution of Untrusted External Binary",
            source_zone=TrustZone.ZONE_0_UNTRUSTED_EXTERNAL,
            target_zone=TrustZone.ZONE_5_KERNEL_HARDWARE,
            description="Untrusted binary executed directly on host OS relying solely on signature scan results.",
            severity=ThreatSeverity.CRITICAL,
            architectural_mitigation="Zero-Trust File Execution Invariant: mandatory execution confinement in disposable micro-VM or safe viewer.",
            verification_mechanism="Zero-trust containment tests in test_charter_contracts.py.",
        ),
        "THREAT-07": ThreatVector(
            threat_id="THREAT-07",
            stride_category=StrideCategory.SPOOFING,
            title="Forged Action Contract or Session Spoofing",
            source_zone=TrustZone.ZONE_2_AI_CONTROL_PLANE,
            target_zone=TrustZone.ZONE_3_POLICY_ENGINE,
            description="Malicious prompt injection or rogue agent crafts a fake action contract claiming user-explicit authorization.",
            severity=ThreatSeverity.CRITICAL,
            architectural_mitigation="Cryptographic contract signing, session ID provenance verification, and mandatory interactive user consent gates.",
            verification_mechanism="TrustBoundaryEnforcer and CharterValidator approval verification in test_threat_model.py.",
        ),
    }

    @classmethod
    def get_all_threats(cls) -> List[ThreatVector]:
        """Return all cataloged threat vectors."""
        return list(cls._THREATS.values())

    @classmethod
    def get_threat(cls, threat_id: str) -> ThreatVector:
        """Retrieve a specific threat vector by ID."""
        if threat_id not in cls._THREATS:
            raise KeyError(f"Unknown threat ID: {threat_id}")
        return cls._THREATS[threat_id]

    @classmethod
    def get_by_stride(cls, stride_category: StrideCategory) -> List[ThreatVector]:
        """Filter threat vectors by STRIDE category."""
        return [t for t in cls._THREATS.values() if t.stride_category == stride_category]

    @classmethod
    def get_by_severity(cls, severity: ThreatSeverity) -> List[ThreatVector]:
        """Filter threat vectors by severity level."""
        return [t for t in cls._THREATS.values() if t.severity == severity]


class TrustBoundaryEnforcer:
    """Enforces zone transition rules and verifies security invariants across trust boundaries."""

    @classmethod
    def validate_zone_transition(
        cls,
        source_zone: TrustZone,
        target_zone: TrustZone,
        action: ActionContract,
        persona_type: PersonaType = PersonaType.PERSONAL,
    ) -> Tuple[bool, List[str]]:
        """Validate whether an action may legitimately cross from source_zone to target_zone."""
        violations: List[str] = []

        # Invariant 1: Rule of Strict Adjacency (Zone 2 AI cannot bypass Zone 3 Policy Engine)
        if source_zone == TrustZone.ZONE_2_AI_CONTROL_PLANE and target_zone in (
            TrustZone.ZONE_4_PRIVILEGED_BROKER,
            TrustZone.ZONE_5_KERNEL_HARDWARE,
        ):
            violations.append(
                "Trust Boundary Violation: Direct transition from ZONE_2_AI_CONTROL_PLANE to ZONE_4/ZONE_5 is strictly forbidden. All requests must pass through ZONE_3_POLICY_ENGINE."
            )

        # Invariant 2: Rule of Untrusted External Non-Execution
        if source_zone == TrustZone.ZONE_0_UNTRUSTED_EXTERNAL and target_zone in (
            TrustZone.ZONE_1_USER_SPACE,
            TrustZone.ZONE_5_KERNEL_HARDWARE,
        ):
            if action.action_type == "file_execute":
                if action.file_containment in (None, FileExecutionContainment.DENIED):
                    violations.append(
                        "Trust Boundary Violation: External Zone 0 files cannot execute in Zone 1/5 without verified containment (DISPOSABLE_ISOLATION or HARDENED_VIEWER)."
                    )

        # Invariant 3: Base Charter Invariant Enforcement
        charter_res = CharterValidator.validate(action)
        if not charter_res.is_valid:
            violations.extend(charter_res.violations)

        # Invariant 4: Persona Governance & Privacy Envelope Enforcement
        persona = PersonaRegistry.get(persona_type)
        persona_res = PersonaPolicyEvaluator.evaluate(action, persona=persona)
        if not persona_res.is_permitted:
            violations.extend(persona_res.violations)

        is_permitted = (len(violations) == 0)
        return is_permitted, violations
