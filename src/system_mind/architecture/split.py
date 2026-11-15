"""Architecture decision records, boundary models, and split enforcement for the AI and native system split."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from system_mind.core.charter import CharterValidator
from system_mind.core.types import ActionContract, OperationRiskTier


class SystemPlaneId(str, Enum):
    """The four functional execution planes of the AI/native system split."""

    AI_COGNITIVE_PLANE = "AI_COGNITIVE_PLANE"
    DETERMINISTIC_POLICY_GATE = "DETERMINISTIC_POLICY_GATE"
    NATIVE_EXECUTION_BROKER = "NATIVE_EXECUTION_BROKER"
    NATIVE_KERNEL_AUTHORITY = "NATIVE_KERNEL_AUTHORITY"


class PrivilegeBoundary(str, Enum):
    """Privilege boundaries governing each plane."""

    UNPRIVILEGED_SANDBOX = "UNPRIVILEGED_SANDBOX"
    PURE_EVALUATION_FIREWALL = "PURE_EVALUATION_FIREWALL"
    LEAST_PRIVILEGE_DAEMON = "LEAST_PRIVILEGE_DAEMON"
    KERNEL_SUPERVISOR = "KERNEL_SUPERVISOR"


@dataclass(frozen=True)
class ArchitectureDecisionRecord:
    """Formal specification of an architectural decision record."""

    adr_id: str
    title: str
    status: str
    plane_id: SystemPlaneId
    privilege: PrivilegeBoundary
    context: str
    decision: str
    consequences: List[str]
    invariants: List[str]


class SplitBoundaryRegistry:
    """Central registry of formal ADRs establishing the AI and native system split."""

    _ADRS: Dict[str, ArchitectureDecisionRecord] = {
        "ADR-021": ArchitectureDecisionRecord(
            adr_id="ADR-021",
            title="AI Cognitive Plane as an Untrusted Planner Isolated in User Space",
            status="accepted",
            plane_id=SystemPlaneId.AI_COGNITIVE_PLANE,
            privilege=PrivilegeBoundary.UNPRIVILEGED_SANDBOX,
            context="Monolithic agents executing LLM-generated code directly with ambient shell credentials create fatal prompt injection risks.",
            decision="The AI cognitive plane runs in unprivileged user space with zero OS mutation rights and communicates outward solely via typed declarative ActionContracts.",
            consequences=[
                "All actions require downstream deterministic policy approval.",
                "Prompt injection attacks in external documents cannot trigger native system calls directly.",
                "AI planner is incapable of self-granting administrative entitlements.",
            ],
            invariants=[
                "Caller AI_PLANE cannot execute raw shell commands.",
                "AI planner possesses zero direct IPC sockets to native execution broker.",
            ],
        ),
        "ADR-022": ArchitectureDecisionRecord(
            adr_id="ADR-022",
            title="Narrow Privileged Execution Broker with Cryptographic Provenance and Atomic Rollback",
            status="accepted",
            plane_id=SystemPlaneId.NATIVE_EXECUTION_BROKER,
            privilege=PrivilegeBoundary.LEAST_PRIVILEGE_DAEMON,
            context="Executing administrative actions without precondition checks or rollback handlers causes irreversible system drift.",
            decision="Consequential state modifications are dispatched exclusively through a narrow broker daemon that validates preconditions, enforces atomic rollbacks, and logs SHA-256 audit receipts.",
            consequences=[
                "Eliminates ambient shell authority on the host OS.",
                "Guarantees automated state restoration for reversible actions.",
                "Ensures tamper-evident forensic accountability for all mutations.",
            ],
            invariants=[
                "Broker executes actions only when accompanied by a VerifiedCapabilityGrant.",
                "Postcondition failure triggers automatic reverse-chronological compensation rollback.",
            ],
        ),
        "ADR-023": ArchitectureDecisionRecord(
            adr_id="ADR-023",
            title="Deterministic Non-LLM Invariant Firewall as the Authority Gate",
            status="accepted",
            plane_id=SystemPlaneId.DETERMINISTIC_POLICY_GATE,
            privilege=PrivilegeBoundary.PURE_EVALUATION_FIREWALL,
            context="Security evaluation cannot rely on LLM reasoning or prompt self-policing, which can be bypassed via jailbreaking.",
            decision="An independent deterministic rules engine operating strictly outside LLM weights evaluates all proposed contracts against charter invariants and component ownership.",
            consequences=[
                "The AI model cannot convince the policy engine to bypass a rule.",
                "Security checks are pure functions with zero prompt dependency.",
                "Policy evaluation latency is guaranteed sub-5ms P95.",
            ],
            invariants=[
                "Policy engine evaluates strongly typed contracts independently of LLM reasoning.",
                "Issues VerifiedCapabilityGrant exclusively upon 100% compliance.",
            ],
        ),
        "ADR-024": ArchitectureDecisionRecord(
            adr_id="ADR-024",
            title="Native Operating System Kernel and Security Controls as Authoritative Enforcers",
            status="accepted",
            plane_id=SystemPlaneId.NATIVE_KERNEL_AUTHORITY,
            privilege=PrivilegeBoundary.KERNEL_SUPERVISOR,
            context="User-space software must not attempt to duplicate or circumvent native kernel security controls (SIP, WDAC, AppArmor).",
            decision="Native OS kernels remain the authoritative lower-level security enforcement boundary. SYSTEM MIND X works strictly within native entitlements and never disables native OS controls.",
            consequences=[
                "Ensures physical host stability during development and production.",
                "Guarantees compliance with enterprise endpoint management systems.",
                "Protects the platform's hardware root of trust.",
            ],
            invariants=[
                "Native OS security mechanisms (SIP, Gatekeeper, WDAC) cannot be disabled or weakened.",
                "Zero execution of untrusted external binaries without verified containment.",
            ],
        ),
    }

    @classmethod
    def get_all(cls) -> List[ArchitectureDecisionRecord]:
        """Return all cataloged architecture decision records."""
        return list(cls._ADRS.values())

    @classmethod
    def get(cls, adr_id: str) -> ArchitectureDecisionRecord:
        """Retrieve an architecture decision record by ID."""
        if adr_id not in cls._ADRS:
            raise KeyError(f"Unknown ADR ID: {adr_id}")
        return cls._ADRS[adr_id]

    @classmethod
    def get_by_plane(cls, plane_id: SystemPlaneId) -> List[ArchitectureDecisionRecord]:
        """Filter ADRs by system plane."""
        return [adr for adr in cls._ADRS.values() if adr.plane_id == plane_id]


class AiNativeSplitValidator:
    """Validates runtime actions against the architectural split and ADR invariants."""

    @classmethod
    def validate_execution_request(
        cls,
        source_plane: SystemPlaneId,
        target_plane: SystemPlaneId,
        action: ActionContract,
        has_verified_grant: bool = False,
    ) -> Tuple[bool, List[str]]:
        """Validate an execution dispatch against the AI/native split invariants."""
        violations: List[str] = []

        # Invariant 1: Direct AI Cognitive Plane bypass of Policy Gate is forbidden
        if source_plane == SystemPlaneId.AI_COGNITIVE_PLANE and target_plane in (
            SystemPlaneId.NATIVE_EXECUTION_BROKER,
            SystemPlaneId.NATIVE_KERNEL_AUTHORITY,
        ):
            violations.append(
                "ADR-021 Split Violation: Direct execution dispatch from AI_COGNITIVE_PLANE to NATIVE_EXECUTION_BROKER or KERNEL is strictly prohibited. All actions must traverse the DETERMINISTIC_POLICY_GATE."
            )

        # Invariant 2: Execution broker requires a valid VerifiedCapabilityGrant
        if target_plane == SystemPlaneId.NATIVE_EXECUTION_BROKER and not has_verified_grant:
            violations.append(
                "ADR-022 Split Violation: NATIVE_EXECUTION_BROKER rejects execution request lacking a verified capability grant from DETERMINISTIC_POLICY_GATE."
            )

        # Invariant 3: Rejection of raw shell execution strings
        charter_res = CharterValidator.validate(action)
        if not charter_res.is_valid:
            violations.extend(charter_res.violations)

        # Invariant 4: Native security controls non-bypass (ADR-024)
        target_lower = action.target_component.lower()
        if any(term in target_lower for term in ("csrutil", "sip_disable", "gatekeeper_disable", "wdac_bypass", "setenforce 0")):
            violations.append(
                "ADR-024 Split Violation: Actions attempting to disable or subvert native OS security controls (SIP, Gatekeeper, WDAC) are hard-rejected."
            )

        is_permitted = (len(violations) == 0)
        return is_permitted, violations
