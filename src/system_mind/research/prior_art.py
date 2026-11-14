"""Prior art catalog, failure mode taxonomy, and safety benchmarking for SYSTEM MIND X."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from system_mind.core.charter import CharterValidator
from system_mind.core.types import (
    ActionContract,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
)
from system_mind.personas.evaluator import PersonaPolicyEvaluator
from system_mind.personas.models import PersonaRegistry, PersonaType


class PriorArtCategory(str, Enum):
    """Categorization of existing AI computer-control architectures."""

    VISION_GUI_AGENT = "VISION_GUI_AGENT"
    UNRESTRICTED_SHELL_AGENT = "UNRESTRICTED_SHELL_AGENT"
    VENDOR_NATIVE_ASSISTANT = "VENDOR_NATIVE_ASSISTANT"
    DECLARATIVE_INFRA_TOOL = "DECLARATIVE_INFRA_TOOL"


class FailureModeType(str, Enum):
    """Catalog of known systemic failure modes in prior art systems."""

    AMBIENT_PRIVILEGE_ESCALATION = "AMBIENT_PRIVILEGE_ESCALATION"
    PROMPT_INJECTION_VULNERABILITY = "PROMPT_INJECTION_VULNERABILITY"
    HALLUCINATED_DESTRUCTION = "HALLUCINATED_DESTRUCTION"
    IRREVERSIBLE_STATE_DRIFT = "IRREVERSIBLE_STATE_DRIFT"
    PRIVACY_SCREEN_LEAKAGE = "PRIVACY_SCREEN_LEAKAGE"
    COMPONENT_OWNERSHIP_CONTAMINATION = "COMPONENT_OWNERSHIP_CONTAMINATION"


@dataclass(frozen=True)
class PriorArtEntry:
    """Detailed profile of a prior art system and its architectural analysis."""

    name: str
    category: PriorArtCategory
    vendors_or_projects: List[str]
    primary_mechanism: str
    strengths: List[str]
    architectural_flaws: List[str]
    associated_failure_modes: List[FailureModeType]
    system_mind_countermeasure: str


class PriorArtDatabase:
    """Central registry and query interface for prior art research findings."""

    _ENTRIES: Dict[str, PriorArtEntry] = {
        "vision_computer_use": PriorArtEntry(
            name="Vision-Based Computer-Use Agents",
            category=PriorArtCategory.VISION_GUI_AGENT,
            vendors_or_projects=["Anthropic Computer Use API", "OpenAI Operator", "Adept ACT-1"],
            primary_mechanism="Multimodal screenshot capture -> coordinate prediction -> simulated mouse/keyboard events.",
            strengths=[
                "Universal GUI application interaction without specialized APIs",
                "Human-like workflow execution across arbitrary desktop software",
            ],
            architectural_flaws=[
                "Zero OS-level introspection into file descriptors, memory, or processes",
                "Extreme vulnerability to visual prompt injection on web pages and documents",
                "High latency and compute cost per action (2-5s round trips)",
                "Lack of deterministic postconditions or atomic rollback capabilities",
            ],
            associated_failure_modes=[
                FailureModeType.PROMPT_INJECTION_VULNERABILITY,
                FailureModeType.PRIVACY_SCREEN_LEAKAGE,
                FailureModeType.IRREVERSIBLE_STATE_DRIFT,
            ],
            system_mind_countermeasure="Replace visual pixel clicking with typed action contracts and deterministic API mediation.",
        ),
        "unrestricted_shell_agents": PriorArtEntry(
            name="Unrestricted Shell Execution Agents",
            category=PriorArtCategory.UNRESTRICTED_SHELL_AGENT,
            vendors_or_projects=["AutoGPT", "OpenInterpreter", "Raw Coding Agent Loops"],
            primary_mechanism="Direct generation of arbitrary bash/PowerShell strings executed in host shell.",
            strengths=[
                "Rapid developer automation and arbitrary script execution",
                "Direct access to CLI utilities and build tools",
            ],
            architectural_flaws=[
                "Ambient authority abuse: inherits unconstrained user or cached sudo rights",
                "High risk of catastrophic hallucinated commands (e.g. rm -rf or permission clobbering)",
                "Vulnerable to prompt injection via untrusted repositories, files, or web content",
                "Silent corruption of user applications and project dependency environments",
            ],
            associated_failure_modes=[
                FailureModeType.AMBIENT_PRIVILEGE_ESCALATION,
                FailureModeType.HALLUCINATED_DESTRUCTION,
                FailureModeType.COMPONENT_OWNERSHIP_CONTAMINATION,
                FailureModeType.PROMPT_INJECTION_VULNERABILITY,
            ],
            system_mind_countermeasure="AI model is an unprivileged planner only; raw root/shell execution is strictly forbidden by policy.",
        ),
        "vendor_native_assistants": PriorArtEntry(
            name="Vendor-Embedded OS Assistants",
            category=PriorArtCategory.VENDOR_NATIVE_ASSISTANT,
            vendors_or_projects=["Microsoft Windows Recall / Copilot", "Apple Intelligence"],
            primary_mechanism="Deep OS-embedded OCR screen capture database and vendor-specific App Intents.",
            strengths=[
                "Seamless desktop integration and hardware NPU acceleration",
                "Frictionless consumer discoverability",
            ],
            architectural_flaws=[
                "Massive privacy exposure: continuous OCR recording captures passwords and private files",
                "Proprietary vendor lock-in with zero cross-platform uniformity",
                "Narrow scope: limited to consumer shortcuts; cannot perform systems engineering",
            ],
            associated_failure_modes=[
                FailureModeType.PRIVACY_SCREEN_LEAKAGE,
                FailureModeType.IRREVERSIBLE_STATE_DRIFT,
            ],
            system_mind_countermeasure="Zero continuous screen recording; structured system telemetry with strict exclusion of personal folders.",
        ),
        "declarative_os_prior_art": PriorArtEntry(
            name="Declarative OS & Infrastructure Systems",
            category=PriorArtCategory.DECLARATIVE_INFRA_TOOL,
            vendors_or_projects=["NixOS", "GNU Guix", "osquery", "Ansible"],
            primary_mechanism="Immutable hash-addressed package stores, atomic generation switching, and SQL telemetry.",
            strengths=[
                "100% reproducible system builds and zero-risk atomic generation rollbacks",
                "Structured, queryable operating system facts and state invariants",
            ],
            architectural_flaws=[
                "Lacks high-level cognitive reasoning, planning, and contextual explanation",
                "High steep learning curve; complex non-standard filesystem hierarchies",
            ],
            associated_failure_modes=[],
            system_mind_countermeasure="Adopt NixOS declarative generations and osquery-style structured telemetry as the foundation for the AI control plane.",
        ),
    }

    @classmethod
    def get_all_entries(cls) -> List[PriorArtEntry]:
        """Return all cataloged prior art entries."""
        return list(cls._ENTRIES.values())

    @classmethod
    def get_by_category(cls, category: PriorArtCategory) -> List[PriorArtEntry]:
        """Filter prior art entries by category."""
        return [e for e in cls._ENTRIES.values() if e.category == category]

    @classmethod
    def get_by_failure_mode(cls, failure_mode: FailureModeType) -> List[PriorArtEntry]:
        """Find prior art systems susceptible to a specific failure mode."""
        return [e for e in cls._ENTRIES.values() if failure_mode in e.associated_failure_modes]


@dataclass
class BenchmarkEvaluationResult:
    """Outcome of evaluating an action proposal against prior art failure modes."""

    is_safe: bool
    detected_failure_modes: List[FailureModeType] = field(default_factory=list)
    countermeasures_enforced: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)


class PriorArtSafetyBenchmark:
    """Benchmarking engine verifying that SYSTEM MIND X rejects all cataloged prior art failure patterns."""

    @classmethod
    def evaluate_action_safety(
        cls,
        action: ActionContract,
        persona_type: PersonaType = PersonaType.PERSONAL,
    ) -> BenchmarkEvaluationResult:
        """Benchmark a proposed action against the six known failure modes."""
        persona = PersonaRegistry.get(persona_type)
        detected_modes: List[FailureModeType] = []
        countermeasures: List[str] = []
        violations: List[str] = []

        # Check F1: Ambient Privilege Escalation
        if action.action_type in {"raw_shell_execution", "unrestricted_root_shell", "sudo_exec"}:
            detected_modes.append(FailureModeType.AMBIENT_PRIVILEGE_ESCALATION)
            violations.append("Prior Art Flaw F1: Raw root/shell execution attempted.")
            countermeasures.append("Enforced Invariant 1: Unrestricted root/shell execution is strictly rejected.")

        # Check F3: Hallucinated Destruction / Missing Preconditions
        if not action.preconditions and action.risk_tier in (
            OperationRiskTier.MEDIUM_IMPACT,
            OperationRiskTier.HIGH_IMPACT,
            OperationRiskTier.CRITICAL_PRIVILEGED,
        ):
            detected_modes.append(FailureModeType.HALLUCINATED_DESTRUCTION)
            violations.append("Prior Art Flaw F3: Action lacks verified preconditions.")
            countermeasures.append("Enforced Invariant 5: Consequential actions require explicit preconditions.")

        # Check F4: Irreversible State Drift
        if action.risk_tier == OperationRiskTier.CRITICAL_PRIVILEGED and not action.rollback_plan:
            detected_modes.append(FailureModeType.IRREVERSIBLE_STATE_DRIFT)
            violations.append("Prior Art Flaw F4: Critical action lacks verified rollback plan.")
            countermeasures.append("Enforced Invariant 4: Critical actions mandate atomic rollback plans.")

        # Check F5: Privacy Screen / File Leakage
        for pattern in persona.excluded_privacy_paths:
            if pattern in action.target_component or pattern.lstrip("~/") in action.target_component:
                detected_modes.append(FailureModeType.PRIVACY_SCREEN_LEAKAGE)
                violations.append(f"Prior Art Flaw F5: Privacy path '{pattern}' targeted.")
                countermeasures.append("Enforced Persona Governance: Absolute exclusion of personal user roots.")
                break

        # Check F6: Component Ownership Clobbering
        if action.is_autonomous_maintenance and action.target_ownership == ComponentOwnership.USER_MANAGED:
            detected_modes.append(FailureModeType.COMPONENT_OWNERSHIP_CONTAMINATION)
            violations.append("Prior Art Flaw F6: Autonomous update targeted USER_MANAGED component.")
            countermeasures.append("Enforced Invariant 2: Tripartite component ownership protects user applications.")

        # Check F2: Prompt Injection / Uncontained File Execution
        if action.action_type == "file_execute" and action.file_containment in (None, FileExecutionContainment.DENIED):
            detected_modes.append(FailureModeType.PROMPT_INJECTION_VULNERABILITY)
            violations.append("Prior Art Flaw F2: File execution attempted without verified containment.")
            countermeasures.append("Enforced Invariant 3: Zero-trust containment mandates micro-VM isolation or safe viewer.")

        is_safe = (len(detected_modes) == 0)
        return BenchmarkEvaluationResult(
            is_safe=is_safe,
            detected_failure_modes=detected_modes,
            countermeasures_enforced=countermeasures,
            violations=violations,
        )
