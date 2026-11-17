"""Strongly-typed data models for macOS native Swift companion bridge telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Dict, List, Optional


class SwiftThermalState(str, Enum):
    """Categorical Apple Silicon / Darwin thermal pressure levels."""

    NOMINAL = "NOMINAL"
    FAIR = "FAIR"
    SERIOUS = "SERIOUS"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FrontmostAppInfo:
    """Active GUI application holding user input focus in the macOS desktop session."""

    name: str
    bundle_id: str
    pid: int
    path: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert frontmost application details to dictionary."""
        return {
            "name": self.name,
            "bundle_id": self.bundle_id,
            "pid": self.pid,
            "path": self.path,
        }


@dataclass(frozen=True)
class SwiftPermissionStatus:
    """Evaluation of standard macOS user privacy and accessibility permission gates."""

    accessibility_granted: bool
    screen_recording_granted: bool
    full_disk_access_granted: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert permission statuses to dictionary."""
        return {
            "accessibility_granted": self.accessibility_granted,
            "screen_recording_granted": self.screen_recording_granted,
            "full_disk_access_granted": self.full_disk_access_granted,
        }


@dataclass(frozen=True)
class SwiftBridgeTelemetry:
    """Comprehensive snapshot of native macOS telemetry collected via the Swift companion bridge."""

    thermal_state: SwiftThermalState
    frontmost_app: Optional[FrontmostAppInfo]
    permissions: SwiftPermissionStatus
    system_uptime_seconds: float
    console_user: str
    screen_locked: bool
    timestamp: str
    host_platform: str = "Darwin"
    bridge_channel: str = "SWIFT_NATIVE_IPC"
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe
    unavailable_telemetry: List[str] = field(default_factory=list)
    is_mock: bool = False

    @property
    def is_throttled(self) -> bool:
        """Return True if system thermal state indicates throttling or high heat load."""
        return self.thermal_state in (SwiftThermalState.SERIOUS, SwiftThermalState.CRITICAL)

    @property
    def is_operational(self) -> bool:
        """Return True if native Swift bridge communication is live and non-mock."""
        return not self.is_mock and self.host_platform == "Darwin"

    def to_dict(self) -> Dict[str, Any]:
        """Convert bridge telemetry to dictionary representation."""
        return {
            "thermal_state": self.thermal_state.value,
            "frontmost_app": self.frontmost_app.to_dict() if self.frontmost_app else None,
            "permissions": self.permissions.to_dict(),
            "system_uptime_seconds": self.system_uptime_seconds,
            "console_user": self.console_user,
            "screen_locked": self.screen_locked,
            "timestamp": self.timestamp,
            "host_platform": self.host_platform,
            "bridge_channel": self.bridge_channel,
            "scan_proves_safe": self.scan_proves_safe,
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "is_mock": self.is_mock,
            "is_throttled": self.is_throttled,
            "is_operational": self.is_operational,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize bridge telemetry to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
