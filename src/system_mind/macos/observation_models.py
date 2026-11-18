"""Data models and taxonomy for macOS observation source timestamps and confidence scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class ConfidenceTier(str, Enum):
    """Categorization of observation confidence reflecting measurement authority."""

    KERNEL_AUTHORITATIVE = "KERNEL_AUTHORITATIVE"  # 0.95 - 1.00: Direct kernel syscall, sysctl, IOKit
    SUBSYSTEM_VERIFIED = "SUBSYSTEM_VERIFIED"      # 0.80 - 0.94: System services (launchd, codesign)
    HEURISTIC_PARSED = "HEURISTIC_PARSED"          # 0.60 - 0.79: Parsed CLI text with heuristics
    DEGRADED_PARTIAL = "DEGRADED_PARTIAL"          # 0.40 - 0.59: Incomplete attributes or restricted access
    ESTIMATED_MOCK = "ESTIMATED_MOCK"              # 0.10 - 0.39: Synthetic simulation fixture


@dataclass(frozen=True)
class SourceTimestamp:
    """High-resolution source timestamp metadata capturing when and where reading occurred."""

    utc_iso: str
    epoch_ms: int
    monotonic_ns: Optional[int] = None
    clock_source: str = "mach_continuous_time"

    def to_dict(self) -> Dict[str, Any]:
        """Convert timestamp to dictionary."""
        return {
            "utc_iso": self.utc_iso,
            "epoch_ms": self.epoch_ms,
            "monotonic_ns": self.monotonic_ns,
            "clock_source": self.clock_source,
        }


@dataclass(frozen=True)
class ObservationConfidence:
    """Confidence assessment with underlying authority tier and penalty factor audit trail."""

    score: float
    tier: ConfidenceTier
    rationale: str
    penalty_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert confidence to dictionary."""
        return {
            "score": round(self.score, 3),
            "tier": self.tier.value,
            "rationale": self.rationale,
            "penalty_factors": list(self.penalty_factors),
        }


def compute_telemetry_digest(payload: Any) -> str:
    """Compute deterministic SHA-256 digest of arbitrary telemetry payload."""
    if hasattr(payload, "to_dict"):
        raw = payload.to_dict()
    elif isinstance(payload, dict):
        raw = payload
    else:
        raw = str(payload)

    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ObservedTelemetryEnvelope(Generic[T]):
    """Unified temporal observation envelope bundling payload, source timestamps, and confidence."""

    observation_id: str
    collector_id: str
    source_timestamp: SourceTimestamp
    observed_at_utc: str
    latency_ms: float
    confidence: ObservationConfidence
    payload_sha256: str
    payload: T
    unavailable_telemetry: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant
    is_mock: bool = False
    observation_status: str = "ACTUAL"  # ACTUAL, MOCK, DEGRADED, UNSUPPORTED

    def to_dict(self) -> Dict[str, Any]:
        """Convert observation envelope to JSON-serializable dictionary."""
        payload_data = self.payload.to_dict() if hasattr(self.payload, "to_dict") else self.payload
        return {
            "observation_id": self.observation_id,
            "collector_id": self.collector_id,
            "source_timestamp": self.source_timestamp.to_dict(),
            "observed_at_utc": self.observed_at_utc,
            "latency_ms": round(self.latency_ms, 2),
            "confidence": self.confidence.to_dict(),
            "payload_sha256": self.payload_sha256,
            "payload": payload_data,
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "scan_proves_safe": self.scan_proves_safe,
            "is_mock": self.is_mock,
            "observation_status": self.observation_status,
        }

    def to_json(self) -> str:
        """Serialize envelope to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class CompanionObservationBatch:
    """Aggregated batch of observation envelopes collected across companion telemetry sensors."""

    batch_id: str
    timestamp_utc: str
    total_observations: int
    observations: Dict[str, ObservedTelemetryEnvelope[Any]] = field(default_factory=dict)
    mean_confidence: float = 1.0
    lowest_confidence_collector: str = ""
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert observation batch to JSON-serializable dictionary."""
        return {
            "batch_id": self.batch_id,
            "timestamp_utc": self.timestamp_utc,
            "total_observations": self.total_observations,
            "observations": {k: v.to_dict() for k, v in self.observations.items()},
            "mean_confidence": round(self.mean_confidence, 3),
            "lowest_confidence_collector": self.lowest_confidence_collector,
            "scan_proves_safe": self.scan_proves_safe,
            "is_mock": self.is_mock,
        }

    def to_json(self) -> str:
        """Serialize batch to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=2)
