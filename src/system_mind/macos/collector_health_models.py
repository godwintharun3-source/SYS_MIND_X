"""Data models and taxonomy for macOS collector health, timeouts, and partial-data reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class CollectorStatus(str, Enum):
    """Operational health state of an individual telemetry sensor collector."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    TIMED_OUT = "TIMED_OUT"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    CIRCUIT_BROKEN = "CIRCUIT_BROKEN"


class PartialDataReason(str, Enum):
    """Root cause category for missing or incomplete sensor telemetry."""

    HARDWARE_ABSENT = "HARDWARE_ABSENT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    COMMAND_ERROR = "COMMAND_ERROR"
    PLATFORM_UNSUPPORTED = "PLATFORM_UNSUPPORTED"


@dataclass
class CollectorHealthRecord:
    """Detailed health, latency, and partial-data assessment for a single collector."""

    collector_id: str
    status: CollectorStatus
    latency_ms: float
    timeout_seconds: float
    consecutive_failures: int = 0
    last_success_timestamp: Optional[str] = None
    last_error: Optional[str] = None
    partial_data: bool = False
    partial_reasons: List[PartialDataReason] = field(default_factory=list)
    unavailable_fields: List[str] = field(default_factory=list)

    @property
    def is_operational(self) -> bool:
        """Return True if collector yielded valid (healthy or partial) telemetry."""
        return self.status in (CollectorStatus.HEALTHY, CollectorStatus.DEGRADED)

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to JSON-serializable dictionary."""
        return {
            "collector_id": self.collector_id,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "timeout_seconds": self.timeout_seconds,
            "consecutive_failures": self.consecutive_failures,
            "last_success_timestamp": self.last_success_timestamp,
            "last_error": self.last_error,
            "partial_data": self.partial_data,
            "partial_reasons": [r.value for r in self.partial_reasons],
            "unavailable_fields": list(self.unavailable_fields),
            "is_operational": self.is_operational,
        }

    def to_json(self) -> str:
        """Serialize record to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class CompanionHealthReport:
    """Aggregated health report across all companion telemetry collectors."""

    timestamp: str
    host_platform: str
    total_collectors: int
    healthy_count: int
    degraded_count: int
    failed_count: int
    timed_out_count: int
    unsupported_count: int
    overall_status: CollectorStatus
    collectors: Dict[str, CollectorHealthRecord] = field(default_factory=dict)
    partial_data_present: bool = False
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert companion health report to JSON-serializable dictionary."""
        return {
            "timestamp": self.timestamp,
            "host_platform": self.host_platform,
            "total_collectors": self.total_collectors,
            "healthy_count": self.healthy_count,
            "degraded_count": self.degraded_count,
            "failed_count": self.failed_count,
            "timed_out_count": self.timed_out_count,
            "unsupported_count": self.unsupported_count,
            "overall_status": self.overall_status.value,
            "collectors": {k: v.to_dict() for k, v in self.collectors.items()},
            "partial_data_present": self.partial_data_present,
            "scan_proves_safe": self.scan_proves_safe,
            "is_mock": self.is_mock,
        }

    def to_json(self) -> str:
        """Serialize report to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class CollectorResult(Generic[T]):
    """Container wrapping collector output with associated health and timeout metadata."""

    data: Optional[T]
    health: CollectorHealthRecord
