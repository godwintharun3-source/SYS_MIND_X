"""Strongly-typed data models for macOS launchd services and login items telemetry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ServiceDomain(str, Enum):
    """Execution context and location domain for launchd services."""

    SYSTEM_DAEMON = "SYSTEM_DAEMON"  # /System/Library/LaunchDaemons
    SYSTEM_AGENT = "SYSTEM_AGENT"  # /System/Library/LaunchAgents
    GLOBAL_DAEMON = "GLOBAL_DAEMON"  # /Library/LaunchDaemons
    GLOBAL_AGENT = "GLOBAL_AGENT"  # /Library/LaunchAgents
    USER_AGENT = "USER_AGENT"  # ~/Library/LaunchAgents
    RUNTIME_LOADED = "RUNTIME_LOADED"  # Reported by launchctl list without mapped plist
    UNKNOWN = "UNKNOWN"


class ServiceStatus(str, Enum):
    """Runtime execution status of a launchd service."""

    RUNNING = "RUNNING"  # Active process with PID > 0
    LOADED_WAITING = "LOADED_WAITING"  # Loaded in launchd, PID is None, exit code 0
    LOADED_FAILED = "LOADED_FAILED"  # Loaded in launchd, PID is None, exit code != 0
    DEFINITION_ONLY = "DEFINITION_ONLY"  # Present on disk, not currently loaded
    UNKNOWN = "UNKNOWN"


class ServiceOwnership(str, Enum):
    """Maintenance and ownership classification tier."""

    SYSTEM_MANAGED = "SYSTEM_MANAGED"  # Apple macOS core operating system
    VENDOR_MANAGED = "VENDOR_MANAGED"  # Third-party vendor applications & daemons
    USER_MANAGED = "USER_MANAGED"  # User desktop preferences or custom scripts


class LoginItemKind(str, Enum):
    """Classification of startup login items."""

    APPLICATION = "APPLICATION"  # User desktop GUI application (.app)
    SERVICE = "SERVICE"  # Background agent or helper tool
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MacLaunchdService:
    """Strongly-typed representation of a single macOS launchd service."""

    label: str
    pid: Optional[int] = None
    last_exit_code: Optional[int] = None
    domain: ServiceDomain = ServiceDomain.UNKNOWN
    status: ServiceStatus = ServiceStatus.UNKNOWN
    ownership: ServiceOwnership = ServiceOwnership.VENDOR_MANAGED
    plist_path: Optional[str] = None
    program: Optional[str] = None
    run_at_load: Optional[bool] = None
    keep_alive: Optional[bool] = None
    is_apple: bool = False

    @property
    def is_running(self) -> bool:
        """Return True if this service is actively running with a valid PID."""
        return self.status == ServiceStatus.RUNNING and self.pid is not None and self.pid > 0

    @property
    def is_system_managed(self) -> bool:
        """Return True if this is an Apple core system-managed service."""
        return self.ownership == ServiceOwnership.SYSTEM_MANAGED

    def to_dict(self) -> Dict[str, Any]:
        """Convert service model to dictionary representation."""
        return {
            "label": self.label,
            "pid": self.pid,
            "last_exit_code": self.last_exit_code,
            "domain": self.domain.value,
            "status": self.status.value,
            "ownership": self.ownership.value,
            "plist_path": self.plist_path,
            "program": self.program,
            "run_at_load": self.run_at_load,
            "keep_alive": self.keep_alive,
            "is_apple": self.is_apple,
            "is_running": self.is_running,
        }


@dataclass(frozen=True)
class MacLoginItem:
    """Strongly-typed representation of a desktop user session login item."""

    name: str
    path: Optional[str] = None
    hidden: bool = False
    kind: LoginItemKind = LoginItemKind.APPLICATION
    ownership: ServiceOwnership = ServiceOwnership.USER_MANAGED
    is_apple: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert login item model to dictionary representation."""
        return {
            "name": self.name,
            "path": self.path,
            "hidden": self.hidden,
            "kind": self.kind.value,
            "ownership": self.ownership.value,
            "is_apple": self.is_apple,
        }


@dataclass(frozen=True)
class MacServicesReport:
    """Comprehensive read-only telemetry snapshot of macOS services and login items."""

    collection_method: str
    timestamp: str
    host_platform: str
    services: List[MacLaunchdService] = field(default_factory=list)
    login_items: List[MacLoginItem] = field(default_factory=list)
    total_services_count: int = 0
    running_services_count: int = 0
    loaded_services_count: int = 0
    system_managed_count: int = 0
    vendor_managed_count: int = 0
    user_managed_count: int = 0
    total_login_items_count: int = 0
    warnings: List[str] = field(default_factory=list)
    unavailable_telemetry: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe

    def find_by_label(self, label: str) -> Optional[MacLaunchdService]:
        """Find a launchd service by its exact label string."""
        for s in self.services:
            if s.label == label:
                return s
        return None

    def filter_by_domain(self, domain: ServiceDomain) -> List[MacLaunchdService]:
        """Filter launchd services by execution domain."""
        return [s for s in self.services if s.domain == domain]

    def filter_by_ownership(self, ownership: ServiceOwnership) -> List[MacLaunchdService]:
        """Filter launchd services by component ownership tier."""
        return [s for s in self.services if s.ownership == ownership]

    def get_running_services(self) -> List[MacLaunchdService]:
        """Retrieve all services currently executing with an active PID."""
        return [s for s in self.services if s.is_running]

    def to_dict(self) -> Dict[str, Any]:
        """Convert complete report to dictionary structure."""
        return {
            "collection_method": self.collection_method,
            "timestamp": self.timestamp,
            "host_platform": self.host_platform,
            "total_services_count": self.total_services_count,
            "running_services_count": self.running_services_count,
            "loaded_services_count": self.loaded_services_count,
            "system_managed_count": self.system_managed_count,
            "vendor_managed_count": self.vendor_managed_count,
            "user_managed_count": self.user_managed_count,
            "total_login_items_count": self.total_login_items_count,
            "services": [s.to_dict() for s in self.services],
            "login_items": [item.to_dict() for item in self.login_items],
            "warnings": list(self.warnings),
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "scan_proves_safe": self.scan_proves_safe,
        }
