"""Data contracts, models, and schemas for the read-only macOS inventory API."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Dict, List, Optional

from system_mind.macos.privacy_models import (
    PrivacyFilterAuditRecord,
    PrivacyScrubbingLevel,
)


class InventorySection(str, Enum):
    """Granular subsystems available via the read-only inventory API."""

    ALL = "ALL"
    IDENTITY = "IDENTITY"          # OS version, build, kernel, architecture, host identity
    HARDWARE = "HARDWARE"          # CPU, Memory, GPU, Displays, USB, Battery
    STORAGE = "STORAGE"            # Volumes, APFS container, mount flags, FileVault
    NETWORK = "NETWORK"            # Interfaces, routing, DNS, link states
    APPLICATIONS = "APPLICATIONS"  # Installed application bundles, versions, categories
    SECURITY = "SECURITY"          # Code signatures, notarization, Endpoint Security
    PROCESSES = "PROCESSES"        # Process table, PIDs, roles, resource usage
    SERVICES = "SERVICES"          # Launchd services, login items, user agent


@dataclass
class MacOsInventoryRequest:
    """Request specification for querying the read-only macOS inventory."""

    sections: List[InventorySection] = field(default_factory=lambda: [InventorySection.ALL])
    privacy_level: PrivacyScrubbingLevel = PrivacyScrubbingLevel.BALANCED
    use_mock: bool = False
    mock_profile: str = "high_fidelity"
    include_observations: bool = True
    include_audit: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert inventory request to dictionary."""
        return {
            "sections": [s.value for s in self.sections],
            "privacy_level": self.privacy_level.value,
            "use_mock": self.use_mock,
            "mock_profile": self.mock_profile,
            "include_observations": self.include_observations,
            "include_audit": self.include_audit,
        }


@dataclass(frozen=True)
class MacOsInventorySummary:
    """High-level summary of system state, capacity, and operational telemetry."""

    os_version: str
    os_build: str
    host_name: str
    architecture: str
    cpu_model: str
    physical_cores: int
    logical_cores: int
    total_memory_bytes: int
    memory_pressure_pct: float
    total_storage_bytes: int
    free_storage_bytes: int
    running_process_count: int
    installed_app_count: int
    mean_confidence: float
    overall_health: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary."""
        return {
            "os_version": self.os_version,
            "os_build": self.os_build,
            "host_name": self.host_name,
            "architecture": self.architecture,
            "cpu_model": self.cpu_model,
            "physical_cores": self.physical_cores,
            "logical_cores": self.logical_cores,
            "total_memory_bytes": self.total_memory_bytes,
            "memory_pressure_pct": round(self.memory_pressure_pct, 2),
            "total_storage_bytes": self.total_storage_bytes,
            "free_storage_bytes": self.free_storage_bytes,
            "running_process_count": self.running_process_count,
            "installed_app_count": self.installed_app_count,
            "mean_confidence": round(self.mean_confidence, 3),
            "overall_health": self.overall_health,
        }


@dataclass
class MacOsInventoryResponse:
    """Comprehensive read-only macOS inventory response envelope."""

    inventory_id: str
    timestamp_utc: str
    summary: MacOsInventorySummary
    sections: Dict[str, Any]
    observations: Optional[Dict[str, Any]] = None
    health: Optional[Dict[str, Any]] = None
    privacy_audit: Optional[Dict[str, Any]] = None
    partial_data: bool = False
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert inventory response to dictionary."""
        return {
            "inventory_id": self.inventory_id,
            "timestamp_utc": self.timestamp_utc,
            "summary": self.summary.to_dict(),
            "sections": self.sections,
            "observations": self.observations,
            "health": self.health,
            "privacy_audit": self.privacy_audit,
            "partial_data": self.partial_data,
            "scan_proves_safe": self.scan_proves_safe,
            "is_mock": self.is_mock,
        }

    def to_json(self) -> str:
        """Serialize inventory response to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=2)
