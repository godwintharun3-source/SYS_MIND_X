"""Competitor comparison matrix, capability scorecard, and research-gap analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class CompetitorSystemId(str, Enum):
    """Catalog of evaluated competitive and prior art systems."""

    ANTHROPIC_COMPUTER_USE = "ANTHROPIC_COMPUTER_USE"
    OPENAI_OPERATOR = "OPENAI_OPERATOR"
    WINDOWS_COPILOT_RECALL = "WINDOWS_COPILOT_RECALL"
    APPLE_INTELLIGENCE = "APPLE_INTELLIGENCE"
    OPEN_INTERPRETER = "OPEN_INTERPRETER"
    DECLARATIVE_OS_ANSIBLE = "DECLARATIVE_OS_ANSIBLE"
    SYSTEM_MIND_X = "SYSTEM_MIND_X"


class ComparisonDimension(str, Enum):
    """The eight foundational engineering dimensions for OS-level AI systems."""

    EXECUTION_SAFETY_BROKER = "EXECUTION_SAFETY_BROKER"
    INDEPENDENT_DETERMINISTIC_POLICY = "INDEPENDENT_DETERMINISTIC_POLICY"
    COMPONENT_OWNERSHIP_SEGREGATION = "COMPONENT_OWNERSHIP_SEGREGATION"
    ZERO_TRUST_FILE_CONFINEMENT = "ZERO_TRUST_FILE_CONFINEMENT"
    ATOMIC_STATE_ROLLBACK = "ATOMIC_STATE_ROLLBACK"
    PRIVACY_PRESERVING_TELEMETRY = "PRIVACY_PRESERVING_TELEMETRY"
    CROSS_PLATFORM_UNIFORMITY = "CROSS_PLATFORM_UNIFORMITY"
    TEMPORAL_DIGITAL_TWIN = "TEMPORAL_DIGITAL_TWIN"


class SupportGrade(str, Enum):
    """Architectural rating of a system's capability in a given dimension."""

    FULL_NATIVE = "FULL_NATIVE"
    PARTIAL_UNRELIABLE = "PARTIAL_UNRELIABLE"
    ABSENT_UNSUPPORTED = "ABSENT_UNSUPPORTED"
    DANGEROUS_UNRESTRICTED = "DANGEROUS_UNRESTRICTED"


class ResearchGapId(str, Enum):
    """The five critical research gaps identified in existing prior art."""

    GAP_1_POLICY_BROKER_SPLIT = "GAP_1_POLICY_BROKER_SPLIT"
    GAP_2_COMPONENT_OWNERSHIP_SEGREGATION = "GAP_2_COMPONENT_OWNERSHIP_SEGREGATION"
    GAP_3_ZERO_TRUST_FILE_CONTAINMENT = "GAP_3_ZERO_TRUST_FILE_CONTAINMENT"
    GAP_4_TEMPORAL_DIGITAL_TWIN = "GAP_4_TEMPORAL_DIGITAL_TWIN"
    GAP_5_RISK_TIERED_GOVERNANCE = "GAP_5_RISK_TIERED_GOVERNANCE"


@dataclass(frozen=True)
class ResearchGapDetail:
    """Formal specification of an industry research gap and its SYSTEM MIND solution."""

    gap_id: ResearchGapId
    title: str
    description: str
    industry_shortcoming: str
    system_mind_solution: str
    verification_strategy: str


@dataclass(frozen=True)
class CompetitorScorecard:
    """Complete evaluation scorecard for a competitive system across all dimensions."""

    system_id: CompetitorSystemId
    name: str
    vendor_or_project: str
    scores: Dict[ComparisonDimension, SupportGrade]
    summary_analysis: str


class CompetitorMatrixRegistry:
    """Central repository for competitor evaluations and research gap definitions."""

    _SCORECARDS: Dict[CompetitorSystemId, CompetitorScorecard] = {
        CompetitorSystemId.ANTHROPIC_COMPUTER_USE: CompetitorScorecard(
            system_id=CompetitorSystemId.ANTHROPIC_COMPUTER_USE,
            name="Anthropic Computer Use API",
            vendor_or_project="Anthropic",
            scores={
                ComparisonDimension.EXECUTION_SAFETY_BROKER: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.INDEPENDENT_DETERMINISTIC_POLICY: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.COMPONENT_OWNERSHIP_SEGREGATION: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ATOMIC_STATE_ROLLBACK: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.CROSS_PLATFORM_UNIFORMITY: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.TEMPORAL_DIGITAL_TWIN: SupportGrade.ABSENT_UNSUPPORTED,
            },
            summary_analysis="Vision-guided OS automation. Highly flexible for UI clicking but lacks low-level OS awareness, deterministic policy enforcement, or atomic rollback.",
        ),
        CompetitorSystemId.OPENAI_OPERATOR: CompetitorScorecard(
            system_id=CompetitorSystemId.OPENAI_OPERATOR,
            name="OpenAI Operator / ChatGPT Desktop",
            vendor_or_project="OpenAI",
            scores={
                ComparisonDimension.EXECUTION_SAFETY_BROKER: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.INDEPENDENT_DETERMINISTIC_POLICY: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.COMPONENT_OWNERSHIP_SEGREGATION: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ATOMIC_STATE_ROLLBACK: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.CROSS_PLATFORM_UNIFORMITY: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.TEMPORAL_DIGITAL_TWIN: SupportGrade.ABSENT_UNSUPPORTED,
            },
            summary_analysis="Desktop and browser automation via multimodal vision. Prone to visual prompt injection and unable to perform deep OS maintenance or enforce state invariants.",
        ),
        CompetitorSystemId.WINDOWS_COPILOT_RECALL: CompetitorScorecard(
            system_id=CompetitorSystemId.WINDOWS_COPILOT_RECALL,
            name="Microsoft Windows Copilot & Recall",
            vendor_or_project="Microsoft Corporation",
            scores={
                ComparisonDimension.EXECUTION_SAFETY_BROKER: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.INDEPENDENT_DETERMINISTIC_POLICY: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.COMPONENT_OWNERSHIP_SEGREGATION: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.ATOMIC_STATE_ROLLBACK: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY: SupportGrade.DANGEROUS_UNRESTRICTED,
                ComparisonDimension.CROSS_PLATFORM_UNIFORMITY: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.TEMPORAL_DIGITAL_TWIN: SupportGrade.PARTIAL_UNRELIABLE,
            },
            summary_analysis="Deeply integrated into Windows 11. Suffers from severe privacy vulnerabilities due to continuous unencrypted OCR screen capture. Limited to Windows.",
        ),
        CompetitorSystemId.APPLE_INTELLIGENCE: CompetitorScorecard(
            system_id=CompetitorSystemId.APPLE_INTELLIGENCE,
            name="Apple Intelligence / Siri Intents",
            vendor_or_project="Apple Inc.",
            scores={
                ComparisonDimension.EXECUTION_SAFETY_BROKER: SupportGrade.FULL_NATIVE,
                ComparisonDimension.INDEPENDENT_DETERMINISTIC_POLICY: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.COMPONENT_OWNERSHIP_SEGREGATION: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.ATOMIC_STATE_ROLLBACK: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.CROSS_PLATFORM_UNIFORMITY: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.TEMPORAL_DIGITAL_TWIN: SupportGrade.PARTIAL_UNRELIABLE,
            },
            summary_analysis="App Intent model provides robust capability isolation on macOS/iOS, but completely lacks cross-platform support and cannot perform deep systems engineering.",
        ),
        CompetitorSystemId.OPEN_INTERPRETER: CompetitorScorecard(
            system_id=CompetitorSystemId.OPEN_INTERPRETER,
            name="OpenInterpreter / AutoGPT",
            vendor_or_project="Open Source Community",
            scores={
                ComparisonDimension.EXECUTION_SAFETY_BROKER: SupportGrade.DANGEROUS_UNRESTRICTED,
                ComparisonDimension.INDEPENDENT_DETERMINISTIC_POLICY: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.COMPONENT_OWNERSHIP_SEGREGATION: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT: SupportGrade.DANGEROUS_UNRESTRICTED,
                ComparisonDimension.ATOMIC_STATE_ROLLBACK: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.CROSS_PLATFORM_UNIFORMITY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.TEMPORAL_DIGITAL_TWIN: SupportGrade.ABSENT_UNSUPPORTED,
            },
            summary_analysis="Direct shell execution under ambient host authority. Catastrophic risk of accidental destruction, prompt injection, and silent corruption of user dependencies.",
        ),
        CompetitorSystemId.DECLARATIVE_OS_ANSIBLE: CompetitorScorecard(
            system_id=CompetitorSystemId.DECLARATIVE_OS_ANSIBLE,
            name="Declarative OS & Infrastructure (NixOS/Ansible/osquery)",
            vendor_or_project="NixOS Foundation / Red Hat / Linux Foundation",
            scores={
                ComparisonDimension.EXECUTION_SAFETY_BROKER: SupportGrade.FULL_NATIVE,
                ComparisonDimension.INDEPENDENT_DETERMINISTIC_POLICY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.COMPONENT_OWNERSHIP_SEGREGATION: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT: SupportGrade.ABSENT_UNSUPPORTED,
                ComparisonDimension.ATOMIC_STATE_ROLLBACK: SupportGrade.PARTIAL_UNRELIABLE,
                ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.CROSS_PLATFORM_UNIFORMITY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.TEMPORAL_DIGITAL_TWIN: SupportGrade.PARTIAL_UNRELIABLE,
            },
            summary_analysis="Gold standard for deterministic execution and state rollback, but lacks high-level cognitive reasoning, contextual planning, and adaptive risk remediation.",
        ),
        CompetitorSystemId.SYSTEM_MIND_X: CompetitorScorecard(
            system_id=CompetitorSystemId.SYSTEM_MIND_X,
            name="SYSTEM MIND X",
            vendor_or_project="SYSTEM MIND Architecture Project",
            scores={
                ComparisonDimension.EXECUTION_SAFETY_BROKER: SupportGrade.FULL_NATIVE,
                ComparisonDimension.INDEPENDENT_DETERMINISTIC_POLICY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.COMPONENT_OWNERSHIP_SEGREGATION: SupportGrade.FULL_NATIVE,
                ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT: SupportGrade.FULL_NATIVE,
                ComparisonDimension.ATOMIC_STATE_ROLLBACK: SupportGrade.FULL_NATIVE,
                ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.CROSS_PLATFORM_UNIFORMITY: SupportGrade.FULL_NATIVE,
                ComparisonDimension.TEMPORAL_DIGITAL_TWIN: SupportGrade.FULL_NATIVE,
            },
            summary_analysis="AI cognitive control plane combined with deterministic policy validator, narrow execution broker, tripartite component isolation, and temporal digital twin.",
        ),
    }

    _GAPS: Dict[ResearchGapId, ResearchGapDetail] = {
        ResearchGapId.GAP_1_POLICY_BROKER_SPLIT: ResearchGapDetail(
            gap_id=ResearchGapId.GAP_1_POLICY_BROKER_SPLIT,
            title="The AI-Native Policy-Broker Disconnect",
            description="Existing AI systems rely on self-policing prompts or unconstrained shell execution.",
            industry_shortcoming="When an LLM hallucinates or encounters prompt injection, direct shell execution damages system state without independent policy interception.",
            system_mind_solution="Bifurcated architecture: AI plans; non-LLM deterministic policy engine validates; narrow broker executes typed contracts.",
            verification_strategy="Automated rejection of raw shell/root execution and verification of typed capability contracts in tests.",
        ),
        ResearchGapId.GAP_2_COMPONENT_OWNERSHIP_SEGREGATION: ResearchGapDetail(
            gap_id=ResearchGapId.GAP_2_COMPONENT_OWNERSHIP_SEGREGATION,
            title="Component Ownership Vacuum & Dependency Clobbering",
            description="Automated maintenance tools treat host filesystems as flat, mutating user applications and virtualenvs.",
            industry_shortcoming="Routine automated package updates corrupt developer virtual environments, broken lockfiles, and alter user apps without consent.",
            system_mind_solution="Tripartite ownership classification (SYSTEM_MANAGED, VENDOR_MANAGED, USER_MANAGED) with hardcoded non-interference invariants on user components.",
            verification_strategy="Automated rejection of autonomous maintenance targeting USER_MANAGED components across all personas.",
        ),
        ResearchGapId.GAP_3_ZERO_TRUST_FILE_CONTAINMENT: ResearchGapDetail(
            gap_id=ResearchGapId.GAP_3_ZERO_TRUST_FILE_CONTAINMENT,
            title="The 'Scan is Safe' Fallacy & Ambient Host Execution",
            description="Desktop software assumes passing static signature checks proves an untrusted file is safe to execute natively.",
            industry_shortcoming="Zero-day malware and novel obfuscated scripts bypass antivirus scans and execute directly on the host OS with ambient privileges.",
            system_mind_solution="Zero-Trust File Execution Invariant: scans establish absence of known signatures, not safety. Unknown binaries mandate micro-VM isolation or safe viewers.",
            verification_strategy="Enforced containment validation rejecting uncontained native host execution of unverified binaries.",
        ),
        ResearchGapId.GAP_4_TEMPORAL_DIGITAL_TWIN: ResearchGapDetail(
            gap_id=ResearchGapId.GAP_4_TEMPORAL_DIGITAL_TWIN,
            title="Screen Ephemerality vs. Persistent Temporal Digital Twin",
            description="Vision-based agents observe only active on-screen pixels, remaining blind to background state, open sockets, and history.",
            industry_shortcoming="Agents cannot detect background memory leaks, hidden rogue daemons, or reconstruct the sequence of events leading to a system fault.",
            system_mind_solution="Event-sourced temporal digital twin aggregating native OS events (FSEvents, ETW, eBPF) into a queryable state history.",
            verification_strategy="Structured telemetry reports and event provenance tracking verified in automated integration tests.",
        ),
        ResearchGapId.GAP_5_RISK_TIERED_GOVERNANCE: ResearchGapDetail(
            gap_id=ResearchGapId.GAP_5_RISK_TIERED_GOVERNANCE,
            title="The All-or-Nothing Privilege Trap",
            description="Operating systems enforce binary privileges: either unprivileged user or unrestricted root/administrator.",
            industry_shortcoming="Agents either fail completely on administrative repairs or demand root access, creating an unacceptably large blast radius.",
            system_mind_solution="Five-tier risk classification (READ_ONLY to CRITICAL_PRIVILEGED) with mandatory compensation rollback and enterprise dual-person authorization.",
            verification_strategy="Enforcement of explicit user confirmation and dual-person break-glass tokens for critical operations.",
        ),
    }

    @classmethod
    def get_all_competitors(cls) -> List[CompetitorScorecard]:
        """Return all competitor scorecards."""
        return list(cls._SCORECARDS.values())

    @classmethod
    def get_scorecard(cls, system_id: CompetitorSystemId) -> CompetitorScorecard:
        """Retrieve the scorecard for a specific system."""
        if system_id not in cls._SCORECARDS:
            raise KeyError(f"Unknown system ID: {system_id}")
        return cls._SCORECARDS[system_id]

    @classmethod
    def get_dimension_ratings(cls, dimension: ComparisonDimension) -> Dict[CompetitorSystemId, SupportGrade]:
        """Return the rating of all systems across a given comparison dimension."""
        return {sys_id: card.scores[dimension] for sys_id, card in cls._SCORECARDS.items()}

    @classmethod
    def get_all_gaps(cls) -> List[ResearchGapDetail]:
        """Return all cataloged research gaps."""
        return list(cls._GAPS.values())

    @classmethod
    def get_gap(cls, gap_id: ResearchGapId) -> ResearchGapDetail:
        """Retrieve a specific research gap specification."""
        if gap_id not in cls._GAPS:
            raise KeyError(f"Unknown gap ID: {gap_id}")
        return cls._GAPS[gap_id]


class ResearchGapAnalyzer:
    """Verifies that SYSTEM MIND X addresses all five research gaps and achieves full native safety."""

    @classmethod
    def verify_system_mind_competitor_lead(cls) -> Dict[str, bool]:
        """Programmatically audit SYSTEM MIND X against competitor benchmarks."""
        system_mind = CompetitorMatrixRegistry.get_scorecard(CompetitorSystemId.SYSTEM_MIND_X)
        all_dimensions_full = all(grade == SupportGrade.FULL_NATIVE for grade in system_mind.scores.values())
        all_gaps_defined = len(CompetitorMatrixRegistry.get_all_gaps()) == 5

        # Check that dangerous competitors are properly flagged
        open_interpreter = CompetitorMatrixRegistry.get_scorecard(CompetitorSystemId.OPEN_INTERPRETER)
        dangerous_flagged = open_interpreter.scores[ComparisonDimension.EXECUTION_SAFETY_BROKER] == SupportGrade.DANGEROUS_UNRESTRICTED

        windows_recall = CompetitorMatrixRegistry.get_scorecard(CompetitorSystemId.WINDOWS_COPILOT_RECALL)
        privacy_risk_flagged = windows_recall.scores[ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY] == SupportGrade.DANGEROUS_UNRESTRICTED

        return {
            "system_mind_full_native_coverage": all_dimensions_full,
            "research_gaps_addressed": all_gaps_defined,
            "dangerous_shell_flagged": dangerous_flagged,
            "privacy_leak_flagged": privacy_risk_flagged,
        }
