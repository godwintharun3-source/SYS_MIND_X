"""Strongly-typed data models for telemetry collector stability under sustained event volume."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional


class EventDropPolicy(str, Enum):
    """Policy applied when the bounded event queue reaches maximum capacity."""

    DROP_OLDEST = "DROP_OLDEST"  # Standard ring buffer: evicts oldest unread events
    DROP_NEWEST = "DROP_NEWEST"  # Backpressure shedding: rejects incoming events
    COALESCE_KEY = "COALESCE_KEY"  # Aggressive coalescing of burst events for same entity


class StabilityPressureLevel(str, Enum):
    """Categorized backpressure level based on queue saturation and arrival throughput."""

    NOMINAL = "NOMINAL"  # Depth < 50%, Throughput < 100 EPS
    ELEVATED = "ELEVATED"  # Depth 50%-80%, Throughput 100-500 EPS
    HIGH_PRESSURE = "HIGH_PRESSURE"  # Depth 80%-95%, Throughput 500-1500 EPS
    SATURATED = "SATURATED"  # Depth >= 95% or Throughput > 1500 EPS (throttling active)


class CollectorOperationalStatus(str, Enum):
    """Operational status of a telemetry collector under load."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    SATURATED = "SATURATED"
    CIRCUIT_BROKEN = "CIRCUIT_BROKEN"


@dataclass
class TelemetryEvent:
    """Individual typed event envelope for high-volume collector streams."""

    event_id: str
    subsystem: str  # e.g. "fsevents", "process", "memory", "cpu", "network"
    event_type: str  # e.g. "file_modified", "file_created", "proc_spawn", "proc_exit"
    target_key: str  # e.g. canonical path, PID, interface name
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    coalesced_count: int = 1
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant!

    def __post_init__(self) -> None:
        # Enforce non-negotiable charter invariant
        self.scan_proves_safe = False

    @property
    def deduplication_key(self) -> str:
        """Composite key used for event deduplication and coalescing."""
        return f"{self.subsystem}:{self.event_type}:{self.target_key}"


@dataclass
class BufferCapacityMetrics:
    """Quantitative metrics measuring bounded queue depth, overflow, and throughput."""

    max_capacity: int
    current_depth: int
    high_water_mark: int
    total_ingested: int
    total_emitted: int
    total_dropped: int
    total_coalesced: int
    drop_policy: EventDropPolicy = EventDropPolicy.DROP_OLDEST
    pressure_level: StabilityPressureLevel = StabilityPressureLevel.NOMINAL
    queue_overflow_detected: bool = False
    is_throttled: bool = False
    drop_ratio: float = 0.0
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant!

    def __post_init__(self) -> None:
        self.scan_proves_safe = False
        if self.total_ingested > 0:
            self.drop_ratio = round(self.total_dropped / float(self.total_ingested), 4)
        else:
            self.drop_ratio = 0.0


@dataclass
class CollectorStabilityReport:
    """Comprehensive stability audit report for telemetry collectors under sustained volume."""

    collector_name: str
    status: CollectorOperationalStatus
    collection_method: str = "IN_MEMORY_STABILITY_ENGINE"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    host_platform: str = "Darwin-Apple-Silicon"
    metrics: BufferCapacityMetrics = field(
        default_factory=lambda: BufferCapacityMetrics(
            max_capacity=5000,
            current_depth=0,
            high_water_mark=0,
            total_ingested=0,
            total_emitted=0,
            total_dropped=0,
            total_coalesced=0,
        )
    )
    peak_throughput_eps: float = 0.0
    average_batch_latency_ms: float = 0.0
    memory_rss_bytes: int = 0
    memory_growth_bytes: int = 0
    coalescing_efficiency_ratio: float = 0.0
    warnings: List[str] = field(default_factory=list)
    unavailable_telemetry: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant!

    def __post_init__(self) -> None:
        self.scan_proves_safe = False
