"""Machine-enforceable product non-goals and explicit safety constraints for SYSTEM MIND X."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from system_mind.core.charter import CharterValidator
from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
    PlatformTier,
)
from system_mind.personas.evaluator import PersonaPolicyEvaluator
from system_mind.personas.models import PersonaRegistry, PersonaType


class NonGoalCategory(str, Enum):
    """Classification of product non-goals."""

    PRIVILEGE_AND_CONTROL = "PRIVILEGE_AND_CONTROL"
    PRIVACY_AND_TELEMETRY = "PRIVACY_AND_TELEMETRY"
    COMPONENT_OWNERSHIP = "COMPONENT_OWNERSHIP"
    FILE_EXECUTION = "FILE_EXECUTION"
    PLATFORM_AND_KERNEL = "PLATFORM_AND_KERNEL"


class SafetyConstraintCategory(str, Enum):
    """Categories for explicit safety constraints."""

    PRIVILEGE_INTEGRITY = "PRIVILEGE_INTEGRITY"
    COMPONENT_SEGREGATION = "COMPONENT_SEGREGATION"
    EXECUTION_ISOLATION = "EXECUTION_ISOLATION"
    PRIVACY_PERIMETER = "PRIVACY_PERIMETER"
    GOVERNANCE_APPROVAL = "GOVERNANCE_APPROVAL"
    PLATFORM_COMPLIANCE = "PLATFORM_COMPLIANCE"
    SYSTEM_PROTECTION = "SYSTEM_PROTECTION"


@dataclass(frozen=True)
class ProductNonGoal:
    """Formal specification of an explicit negative boundary (what the system will not do)."""

    non_goal_id: str
    category: NonGoalCategory
    title: str
    rationale: str
    boundary_statement: str


@dataclass(frozen=True)
class SafetyConstraint:
    """An explicit, machine-enforceable safety constraint protecting system integrity."""

    constraint_id: str
    category: SafetyConstraintCategory
    title: str
    rationale: str
    is_hard_invariant: bool
    rejection_message: str


@dataclass
class ConstraintValidationResult:
    """Outcome of action validation against all safety constraints."""

    is_permitted: bool
    violated_constraints: List[SafetyConstraint] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class NonGoalRegistry:
    """Central registry of cataloged product non-goals."""

    _NON_GOALS: Dict[str, ProductNonGoal] = {
        "NG-01": ProductNonGoal(
            non_goal_id="NG-01",
            category=NonGoalCategory.PRIVILEGE_AND_CONTROL,
            title="No Unrestricted Host Shell / Root Agent",
            rationale="Ambient root or raw shell commands bypass typed contracts and produce irreversible system drift.",
            boundary_statement="SYSTEM MIND X is not an ambient shell execution runner. The AI planner operates in unprivileged user space; elevated mutations require typed contracts through a narrow broker.",
        ),
        "NG-02": ProductNonGoal(
            non_goal_id="NG-02",
            category=NonGoalCategory.PRIVACY_AND_TELEMETRY,
            title="No Ambient Continuous Screen OCR / Keylogging",
            rationale="Continuous screen capture and OCR dumps leak credentials, private communications, and personal files.",
            boundary_statement="SYSTEM MIND X is not a background screen scraper or keylogger. Telemetry is structured, event-driven, and restricted to monitored system roots.",
        ),
        "NG-03": ProductNonGoal(
            non_goal_id="NG-03",
            category=NonGoalCategory.COMPONENT_OWNERSHIP,
            title="No Autonomous User Application or Workspace Mutation",
            rationale="Automated updates to user apps or developer toolchains disrupt running tasks and break build dependencies.",
            boundary_statement="Autonomous maintenance never updates user-installed apps, developer IDEs, virtualenvs, or language package directories without explicit interactive user initiation.",
        ),
        "NG-04": ProductNonGoal(
            non_goal_id="NG-04",
            category=NonGoalCategory.FILE_EXECUTION,
            title="No 'Scan Means Safe' Native Binary Execution",
            rationale="Absence of known signatures does not prove absence of malicious capability.",
            boundary_statement="Unknown or untrusted files must never execute natively on the host based solely on signature scans; execution requires disposable micro-isolation or restricted handlers.",
        ),
        "NG-05": ProductNonGoal(
            non_goal_id="NG-05",
            category=NonGoalCategory.PLATFORM_AND_KERNEL,
            title="No Host Security Control Bypassing",
            rationale="Bypassing native OS controls compromises the platform's root-of-trust.",
            boundary_statement="SYSTEM MIND X never disables, weakens, or bypasses SIP, Gatekeeper, WDAC, SELinux, AppArmor, or native OS update verification.",
        ),
        "NG-06": ProductNonGoal(
            non_goal_id="NG-06",
            category=NonGoalCategory.PRIVACY_AND_TELEMETRY,
            title="No Mandatory Cloud Exfiltration of Secrets",
            rationale="Sending cleartext host telemetry, prompts, or credentials to cloud APIs creates high-risk attack surfaces.",
            boundary_statement="SYSTEM MIND X is local-first. Telemetry collectors and prompt contexts are strictly quarantined from private credentials (~/.ssh, ~/.gnupg, .env) and personal documents.",
        ),
        "NG-07": ProductNonGoal(
            non_goal_id="NG-07",
            category=NonGoalCategory.PRIVILEGE_AND_CONTROL,
            title="No Unbounded Fleet-Wide Mutation",
            rationale="Unattended fleet-wide changes can induce correlated cascading failures across an enterprise.",
            boundary_statement="High-impact or critical fleet configuration changes require cryptographic dual-person authorization or verified break-glass tokens.",
        ),
        "NG-08": ProductNonGoal(
            non_goal_id="NG-08",
            category=NonGoalCategory.PLATFORM_AND_KERNEL,
            title="No Scratch-Built Monolithic Kernel",
            rationale="Re-implementing a monolithic kernel introduces massive vulnerability surfaces and hardware incompatibilities.",
            boundary_statement="SYSTEM MIND X does not replace or re-implement OS kernels. Native kernels (XNU, Windows NT, Linux) remain the authoritative lower-level execution and security enforcement boundary.",
        ),
        "NG-09": ProductNonGoal(
            non_goal_id="NG-09",
            category=NonGoalCategory.PLATFORM_AND_KERNEL,
            title="No Unattended Firmware Flashing or Partition Reconfiguration",
            rationale="Corrupted firmware or repartitioning permanently bricks physical host hardware.",
            boundary_statement="Destructive hardware operations (EFI NVRAM writes, BIOS flashing, partition map alteration) are strictly forbidden from autonomous or single-click execution.",
        ),
        "NG-10": ProductNonGoal(
            non_goal_id="NG-10",
            category=NonGoalCategory.PLATFORM_AND_KERNEL,
            title="No Speculative Capability Fabrication",
            rationale="Claiming unsupported platform capabilities leads to silent failures and false security assumptions.",
            boundary_statement="Capabilities and sensor readings must reflect genuine execution on certified hardware profiles. Mock implementations must be explicitly designated MOCK_ONLY.",
        ),
    }

    @classmethod
    def get_all(cls) -> List[ProductNonGoal]:
        """Return all cataloged non-goals."""
        return list(cls._NON_GOALS.values())

    @classmethod
    def get(cls, non_goal_id: str) -> ProductNonGoal:
        """Retrieve a specific non-goal by ID."""
        if non_goal_id not in cls._NON_GOALS:
            raise KeyError(f"Unknown non-goal ID: {non_goal_id}")
        return cls._NON_GOALS[non_goal_id]

    @classmethod
    def filter_by_category(cls, category: NonGoalCategory) -> List[ProductNonGoal]:
        """Filter non-goals by category."""
        return [ng for ng in cls._NON_GOALS.values() if ng.category == category]


class SafetyConstraintRegistry:
    """Central registry of explicit, machine-enforceable safety constraints."""

    _CONSTRAINTS: Dict[str, SafetyConstraint] = {
        "SC-01": SafetyConstraint(
            constraint_id="SC-01",
            category=SafetyConstraintCategory.PRIVILEGE_INTEGRITY,
            title="Raw Shell Command Rejection",
            rationale="Prevent arbitrary command injection and ambient shell authority abuse.",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-01 Violated: Raw shell execution is strictly forbidden by project charter.",
        ),
        "SC-02": SafetyConstraint(
            constraint_id="SC-02",
            category=SafetyConstraintCategory.COMPONENT_SEGREGATION,
            title="User-Managed Component Autonomous Mutation Block",
            rationale="Prevent autonomous updates from clobbering user applications, IDEs, or virtual environments.",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-02 Violated: Autonomous maintenance cannot modify USER_MANAGED components.",
        ),
        "SC-03": SafetyConstraint(
            constraint_id="SC-03",
            category=SafetyConstraintCategory.EXECUTION_ISOLATION,
            title="Uncontained External File Execution Block",
            rationale="Prevent execution of untrusted external binaries directly on the host operating system.",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-03 Violated: Untrusted external binaries require DISPOSABLE_ISOLATION or HARDENED_VIEWER containment.",
        ),
        "SC-04": SafetyConstraint(
            constraint_id="SC-04",
            category=SafetyConstraintCategory.PRIVACY_PERIMETER,
            title="Privacy Perimeter & Secret Path Protection",
            rationale="Prevent exfiltration or unauthorized inspection of user credentials and personal directories.",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-04 Violated: Target component breaches protected privacy perimeter.",
        ),
        "SC-05": SafetyConstraint(
            constraint_id="SC-05",
            category=SafetyConstraintCategory.GOVERNANCE_APPROVAL,
            title="Critical Privileged Authorization Enforcement",
            rationale="Ensure high-impact and critical privileged actions have verified interactive user or dual authorization.",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-05 Violated: CRITICAL_PRIVILEGED operations require verified user approval or break-glass token.",
        ),
        "SC-06": SafetyConstraint(
            constraint_id="SC-06",
            category=SafetyConstraintCategory.PLATFORM_COMPLIANCE,
            title="Unsupported Platform Target Gate",
            rationale="Reject execution targeting uncertified or deprecated operating system architectures.",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-06 Violated: Target platform is UNSUPPORTED by first-release matrix.",
        ),
        "SC-07": SafetyConstraint(
            constraint_id="SC-07",
            category=SafetyConstraintCategory.SYSTEM_PROTECTION,
            title="Unattended Firmware / Partition Modification Block",
            rationale="Prevent catastrophic bricking of host hardware by forbidding autonomous firmware flashing.",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-07 Violated: Firmware or partition alterations cannot run unattended or autonomously.",
        ),
        "SC-08": SafetyConstraint(
            constraint_id="SC-08",
            category=SafetyConstraintCategory.SYSTEM_PROTECTION,
            title="Native Security Control Subversion Block",
            rationale="Prevent attempts to weaken or disable native OS security controls (SIP, Gatekeeper, WDAC).",
            is_hard_invariant=True,
            rejection_message="Safety Constraint SC-08 Violated: Actions disabling or bypassing native OS security mechanisms are strictly forbidden.",
        ),
    }

    @classmethod
    def get_all(cls) -> List[SafetyConstraint]:
        """Return all cataloged safety constraints."""
        return list(cls._CONSTRAINTS.values())

    @classmethod
    def get(cls, constraint_id: str) -> SafetyConstraint:
        """Retrieve a specific safety constraint by ID."""
        if constraint_id not in cls._CONSTRAINTS:
            raise KeyError(f"Unknown safety constraint ID: {constraint_id}")
        return cls._CONSTRAINTS[constraint_id]

    @classmethod
    def filter_by_category(cls, category: SafetyConstraintCategory) -> List[SafetyConstraint]:
        """Filter safety constraints by category."""
        return [sc for sc in cls._CONSTRAINTS.values() if sc.category == category]


class SafetyConstraintValidator:
    """Unified validation engine enforcing product non-goals and explicit safety constraints."""

    @classmethod
    def validate_action(
        cls,
        action: ActionContract,
        persona_type: PersonaType = PersonaType.PERSONAL,
    ) -> ConstraintValidationResult:
        """Validate an action contract against all registered safety constraints and product non-goals."""
        violated_constraints: List[SafetyConstraint] = []
        violations: List[str] = []
        warnings: List[str] = []

        # Constraint SC-01: Raw Shell Command Rejection
        if action.action_type in ("raw_shell_execution", "shell_exec", "raw_shell_command"):
            sc = SafetyConstraintRegistry.get("SC-01")
            violated_constraints.append(sc)
            violations.append(sc.rejection_message)

        # Constraint SC-02: User-Managed Component Autonomous Mutation Block
        if action.is_autonomous_maintenance and action.target_ownership != ComponentOwnership.SYSTEM_MANAGED:
            sc = SafetyConstraintRegistry.get("SC-02")
            violated_constraints.append(sc)
            violations.append(sc.rejection_message)

        # Constraint SC-03: Uncontained External File Execution Block
        if action.action_type == "file_execute":
            if action.file_containment in (None, FileExecutionContainment.DENIED):
                sc = SafetyConstraintRegistry.get("SC-03")
                violated_constraints.append(sc)
                violations.append(sc.rejection_message)

        # Constraint SC-04: Privacy Perimeter & Secret Path Protection
        persona = PersonaRegistry.get(persona_type)
        eval_res = PersonaPolicyEvaluator.evaluate(action, persona=persona)
        if not eval_res.is_permitted:
            for v in eval_res.violations:
                if "Privacy Boundary Violation" in v or "protected privacy path" in v:
                    sc = SafetyConstraintRegistry.get("SC-04")
                    if sc not in violated_constraints:
                        violated_constraints.append(sc)
                    violations.append(v)
                elif "Governance Violation" in v:
                    violations.append(v)

        # Constraint SC-05: Critical Privileged Authorization Enforcement
        if action.risk_tier == OperationRiskTier.CRITICAL_PRIVILEGED:
            if not action.user_approved or action.approval_requirement == ApprovalRequirement.NONE:
                sc = SafetyConstraintRegistry.get("SC-05")
                violated_constraints.append(sc)
                violations.append(sc.rejection_message)

        # Constraint SC-06: Unsupported Platform Target Gate
        if action.target_platform == PlatformTier.UNSUPPORTED:
            sc = SafetyConstraintRegistry.get("SC-06")
            violated_constraints.append(sc)
            violations.append(sc.rejection_message)

        # Constraint SC-07: Unattended Firmware / Partition Modification Block
        target_lower = action.target_component.lower()
        if any(term in target_lower for term in ("firmware", "nvram", "efi", "bios", "partition_table")):
            if action.is_autonomous_maintenance or not action.user_approved:
                sc = SafetyConstraintRegistry.get("SC-07")
                violated_constraints.append(sc)
                violations.append(sc.rejection_message)

        # Constraint SC-08: Native Security Control Subversion Block
        if any(term in target_lower for term in ("csrutil", "sip_disable", "gatekeeper_disable", "wdac_bypass", "setenforce 0")):
            sc = SafetyConstraintRegistry.get("SC-08")
            violated_constraints.append(sc)
            violations.append(sc.rejection_message)

        is_permitted = (len(violations) == 0)
        return ConstraintValidationResult(
            is_permitted=is_permitted,
            violated_constraints=violated_constraints,
            violations=violations,
            warnings=warnings,
        )
