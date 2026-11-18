"""Data contracts and configuration models for the released macOS companion agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.macos.inventory_models import InventorySection
from system_mind.macos.privacy_models import PrivacyScrubbingLevel


class CompanionExecutionMode(str, Enum):
    """Operational execution mode for the companion agent runner."""

    SINGLE_SNAPSHOT = "SINGLE_SNAPSHOT"
    CONTINUOUS_OBSERVER = "CONTINUOUS_OBSERVER"
    HEALTH_DIAGNOSTIC = "HEALTH_DIAGNOSTIC"


class CompanionOperationalStatus(str, Enum):
    """Health and operational availability status of the companion agent."""

    HEALTHY_NOMINAL = "HEALTHY_NOMINAL"
    DEGRADED_PARTIAL = "DEGRADED_PARTIAL"
    CIRCUIT_BROKEN = "CIRCUIT_BROKEN"
    OFFLINE_CONTAINED = "OFFLINE_CONTAINED"


@dataclass(frozen=True)
class CompanionRunConfig:
    """Runtime configuration for macOS companion agent execution."""

    mode: CompanionExecutionMode = CompanionExecutionMode.SINGLE_SNAPSHOT
    interval_seconds: float = 2.0
    max_cycles: Optional[int] = 1
    use_mock: bool = False
    mock_profile: str = "high_fidelity"
    privacy_level: PrivacyScrubbingLevel = PrivacyScrubbingLevel.BALANCED
    sections: Optional[List[InventorySection]] = None
    stability_backpressure: bool = True
    enforce_least_privilege: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "interval_seconds": self.interval_seconds,
            "max_cycles": self.max_cycles,
            "use_mock": self.use_mock,
            "mock_profile": self.mock_profile,
            "privacy_level": self.privacy_level.value,
            "sections": [s.value for s in self.sections] if self.sections else None,
            "stability_backpressure": self.stability_backpressure,
            "enforce_least_privilege": self.enforce_least_privilege,
        }


@dataclass(frozen=True)
class CompanionCycleTelemetry:
    """Telemetry captured during a single sampling cycle of the companion agent."""

    cycle_id: int
    timestamp_utc: str
    operational_status: CompanionOperationalStatus
    duration_ms: float
    partial_data: bool
    unavailable_telemetry: List[str] = field(default_factory=list)
    inventory_summary: Optional[Dict[str, Any]] = None
    observation_batch_summary: Optional[Dict[str, Any]] = None
    stability_metrics: Optional[Dict[str, Any]] = None
    permission_manifest_summary: Optional[Dict[str, Any]] = None
    privacy_audit: Optional[Dict[str, Any]] = None
    scan_proves_safe: bool = False  # Charter invariant: SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "timestamp_utc": self.timestamp_utc,
            "operational_status": self.operational_status.value,
            "duration_ms": self.duration_ms,
            "partial_data": self.partial_data,
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "inventory_summary": self.inventory_summary,
            "observation_batch_summary": self.observation_batch_summary,
            "stability_metrics": self.stability_metrics,
            "permission_manifest_summary": self.permission_manifest_summary,
            "privacy_audit": self.privacy_audit,
            "scan_proves_safe": False,
        }


@dataclass(frozen=True)
class MacOsCompanionReleaseReport:
    """Formal release execution report emitted by the read-only companion agent."""

    report_id: str
    host_platform: str
    apple_silicon_native: bool
    cycles_completed: int
    latest_cycle: Optional[CompanionCycleTelemetry]
    all_cycles: List[CompanionCycleTelemetry] = field(default_factory=list)
    milestone: str = "Milestone 4: macOS System Agent and Telemetry"
    milestone_version: str = "1.0.0"
    execution_domain: str = "gui/$UID (User Agent)"
    least_privilege_enforced: bool = True
    active_collectors_count: int = 20
    charter_invariants_verified: Dict[str, bool] = field(
        default_factory=lambda: {
            "SC-01_ZERO_AMBIENT_SHELL": True,
            "SC-02_USER_APP_IMMUNITY": True,
            "SC-03_SCAN_NOT_SAFE": True,
            "SC-04_PRIVACY_PERIMETERS": True,
            "SC-05_PRESERVE_HOST_SECURITY": True,
        }
    )
    scan_proves_safe: bool = False  # Charter invariant: SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "milestone": self.milestone,
            "milestone_version": self.milestone_version,
            "host_platform": self.host_platform,
            "apple_silicon_native": self.apple_silicon_native,
            "execution_domain": self.execution_domain,
            "least_privilege_enforced": self.least_privilege_enforced,
            "active_collectors_count": self.active_collectors_count,
            "cycles_completed": self.cycles_completed,
            "latest_cycle": self.latest_cycle.to_dict() if self.latest_cycle else None,
            "all_cycles": [c.to_dict() for c in self.all_cycles],
            "charter_invariants_verified": dict(self.charter_invariants_verified),
            "scan_proves_safe": False,
        }
