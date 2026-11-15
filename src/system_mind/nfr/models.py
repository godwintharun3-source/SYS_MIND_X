"""Non-functional requirements data models, metrics, and central registry for SYSTEM MIND X."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class NfrCategory(str, Enum):
    """Quality categories for non-functional requirements."""

    RELIABILITY = "RELIABILITY"
    PRIVACY = "PRIVACY"
    PERFORMANCE = "PERFORMANCE"
    SAFETY = "SAFETY"


class MetricUnit(str, Enum):
    """Units of measurement for non-functional requirements."""

    MILLISECONDS = "MILLISECONDS"
    PERCENTAGE = "PERCENTAGE"
    MEGABYTES = "MEGABYTES"
    COUNT = "COUNT"
    RATIO = "RATIO"


class ComparisonOperator(str, Enum):
    """Relational operator comparing measured metrics to required thresholds."""

    LESS_THAN_OR_EQUAL = "<="
    GREATER_THAN_OR_EQUAL = ">="
    EQUALS = "=="


@dataclass(frozen=True)
class NonFunctionalRequirement:
    """Formal specification of a measurable non-functional requirement."""

    nfr_id: str
    category: NfrCategory
    title: str
    description: str
    target_threshold: float
    metric_unit: MetricUnit
    operator: ComparisonOperator
    measurement_strategy: str
    is_mandatory_gate: bool = True


class NfrRegistry:
    """Central registry of verified non-functional requirements and target thresholds."""

    _REQUIREMENTS: Dict[str, NonFunctionalRequirement] = {
        # Reliability & Availability
        "NFR-REL-01": NonFunctionalRequirement(
            nfr_id="NFR-REL-01",
            category=NfrCategory.RELIABILITY,
            title="Atomic Rollback Convergence Duration",
            description="Reversible actions must complete automated compensation rollback within 5000ms of failure.",
            target_threshold=5000.0,
            metric_unit=MetricUnit.MILLISECONDS,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            measurement_strategy="Inject synthetic postcondition failure; record pre-state restoration duration.",
        ),
        "NFR-REL-02": NonFunctionalRequirement(
            nfr_id="NFR-REL-02",
            category=NfrCategory.RELIABILITY,
            title="Crash Recovery Convergence Latency",
            description="Database WAL reconciliation and state convergence must complete within 500ms of daemon restart.",
            target_threshold=500.0,
            metric_unit=MetricUnit.MILLISECONDS,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            measurement_strategy="Simulate SIGKILL during active transaction; measure database reconciliation on restart.",
        ),
        "NFR-REL-03": NonFunctionalRequirement(
            nfr_id="NFR-REL-03",
            category=NfrCategory.RELIABILITY,
            title="Host Companion Daemon Uptime Availability",
            description="Host companion daemon must maintain 99.99% operational uptime under soak load.",
            target_threshold=99.99,
            metric_unit=MetricUnit.PERCENTAGE,
            operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
            measurement_strategy="72-hour continuous soak test with synthetic event stream polling.",
        ),
        "NFR-REL-04": NonFunctionalRequirement(
            nfr_id="NFR-REL-04",
            category=NfrCategory.RELIABILITY,
            title="Pre/Postcondition Deterministic Assertion Rate",
            description="100% of mutating broker operations must assert typed preconditions and postconditions.",
            target_threshold=100.0,
            metric_unit=MetricUnit.PERCENTAGE,
            operator=ComparisonOperator.EQUALS,
            measurement_strategy="Audit 100% of broker execution receipts for pre/post validation hashes.",
        ),
        # Privacy & Confidentiality
        "NFR-PRIV-01": NonFunctionalRequirement(
            nfr_id="NFR-PRIV-01",
            category=NfrCategory.PRIVACY,
            title="Zero Cleartext Secret Ingestion Leakage",
            description="Zero private credentials (~/.ssh, ~/.gnupg, .env, tokens) may leak into logs or prompt context.",
            target_threshold=0.0,
            metric_unit=MetricUnit.COUNT,
            operator=ComparisonOperator.EQUALS,
            measurement_strategy="Pass synthetic credentials through telemetry stream; assert zero unredacted occurrences.",
        ),
        "NFR-PRIV-02": NonFunctionalRequirement(
            nfr_id="NFR-PRIV-02",
            category=NfrCategory.PRIVACY,
            title="Zero Ambient Screen OCR Frame Ingestion",
            description="Zero continuous background screen recording frames or raw bitmaps stored on disk.",
            target_threshold=0.0,
            metric_unit=MetricUnit.COUNT,
            operator=ComparisonOperator.EQUALS,
            measurement_strategy="Inspect telemetry cache directory during 24-hour operation; assert zero image/bitmap dumps.",
        ),
        "NFR-PRIV-03": NonFunctionalRequirement(
            nfr_id="NFR-PRIV-03",
            category=NfrCategory.PRIVACY,
            title="Local-First Offline Autonomy Rate",
            description="100% of core telemetry, policy evaluation, and broker execution must function when disconnected.",
            target_threshold=100.0,
            metric_unit=MetricUnit.PERCENTAGE,
            operator=ComparisonOperator.EQUALS,
            measurement_strategy="Disconnect network interface; assert zero errors in local evaluation and maintenance sweeps.",
        ),
        "NFR-PRIV-04": NonFunctionalRequirement(
            nfr_id="NFR-PRIV-04",
            category=NfrCategory.PRIVACY,
            title="Cryptographic Audit Chain Integrity",
            description="100% of state change receipts must include unbroken SHA-256 hash chains.",
            target_threshold=100.0,
            metric_unit=MetricUnit.PERCENTAGE,
            operator=ComparisonOperator.EQUALS,
            measurement_strategy="Validate SHA-256 hash links across all historical state receipts in event history.",
        ),
        # Performance & Latency
        "NFR-PERF-01": NonFunctionalRequirement(
            nfr_id="NFR-PERF-01",
            category=NfrCategory.PERFORMANCE,
            title="Deterministic Policy Evaluation P95 Latency",
            description="ENG-04 policy evaluation must complete within 5.0ms P95 on certified hardware.",
            target_threshold=5.0,
            metric_unit=MetricUnit.MILLISECONDS,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            measurement_strategy="Benchmark 10,000 synthetic action contracts across Personal, Developer, and Enterprise rules.",
        ),
        "NFR-PERF-02": NonFunctionalRequirement(
            nfr_id="NFR-PERF-02",
            category=NfrCategory.PERFORMANCE,
            title="Digital Twin Event Convergence Latency",
            description="Kernel event ingestion to index commit must converge within 50.0ms.",
            target_threshold=50.0,
            metric_unit=MetricUnit.MILLISECONDS,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            measurement_strategy="Emit synthetic file creation events; measure duration until queryable in twin SQLite index.",
        ),
        "NFR-PERF-03": NonFunctionalRequirement(
            nfr_id="NFR-PERF-03",
            category=NfrCategory.PERFORMANCE,
            title="Host Companion Agent Memory Ceiling (RSS)",
            description="Native host companion agent must not exceed 50.0 MB resident set size.",
            target_threshold=50.0,
            metric_unit=MetricUnit.MEGABYTES,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            measurement_strategy="Profile process RSS memory during continuous 24-hour background monitoring.",
        ),
        "NFR-PERF-04": NonFunctionalRequirement(
            nfr_id="NFR-PERF-04",
            category=NfrCategory.PERFORMANCE,
            title="Idle Host CPU Utilization Ceiling",
            description="Background monitoring agent must consume less than 0.5% average CPU during host idle.",
            target_threshold=0.5,
            metric_unit=MetricUnit.PERCENTAGE,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            measurement_strategy="Sample CPU percent over 10-minute idle intervals on Apple Silicon M1.",
        ),
        "NFR-PERF-05": NonFunctionalRequirement(
            nfr_id="NFR-PERF-05",
            category=NfrCategory.PERFORMANCE,
            title="Broker IPC Dispatch Overhead",
            description="Broker IPC roundtrip and contract deserialization overhead must not exceed 25.0ms.",
            target_threshold=25.0,
            metric_unit=MetricUnit.MILLISECONDS,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            measurement_strategy="Benchmark roundtrip local IPC ping-pong with typed payload serialization.",
        ),
        # Safety & Non-Interference
        "NFR-SAFE-01": NonFunctionalRequirement(
            nfr_id="NFR-SAFE-01",
            category=NfrCategory.SAFETY,
            title="User-Managed Workspace Non-Interference Count",
            description="Zero unintended modifications to USER_MANAGED components during autonomous sweeps.",
            target_threshold=0.0,
            metric_unit=MetricUnit.COUNT,
            operator=ComparisonOperator.EQUALS,
            measurement_strategy="Execute 100 autonomous maintenance runs; verify zero state deltas on user applications.",
        ),
        "NFR-SAFE-02": NonFunctionalRequirement(
            nfr_id="NFR-SAFE-02",
            category=NfrCategory.SAFETY,
            title="Untrusted File Zero-Trust Isolation Confinement",
            description="100% of untrusted external binaries must be constrained to disposable micro-isolation.",
            target_threshold=100.0,
            metric_unit=MetricUnit.PERCENTAGE,
            operator=ComparisonOperator.EQUALS,
            measurement_strategy="Attempt detonation of external untrusted binaries; assert 100% micro-isolation routing.",
        ),
    }

    @classmethod
    def get_all(cls) -> List[NonFunctionalRequirement]:
        """Return all cataloged non-functional requirements."""
        return list(cls._REQUIREMENTS.values())

    @classmethod
    def get(cls, nfr_id: str) -> NonFunctionalRequirement:
        """Retrieve a specific non-functional requirement by ID."""
        if nfr_id not in cls._REQUIREMENTS:
            raise KeyError(f"Unknown NFR ID: {nfr_id}")
        return cls._REQUIREMENTS[nfr_id]

    @classmethod
    def filter_by_category(cls, category: NfrCategory) -> List[NonFunctionalRequirement]:
        """Filter non-functional requirements by category."""
        return [nfr for nfr in cls._REQUIREMENTS.values() if nfr.category == category]

    @classmethod
    def get_mandatory_nfrs(cls) -> List[NonFunctionalRequirement]:
        """Return all mandatory NFR gates."""
        return [nfr for nfr in cls._REQUIREMENTS.values() if nfr.is_mandatory_gate]
