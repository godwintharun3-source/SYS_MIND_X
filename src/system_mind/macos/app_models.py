"""Strongly-typed data models for macOS installed applications and bundle identifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.core.types import ComponentOwnership


class ApplicationCategory(str, Enum):
    """Functional classification category for macOS applications."""

    CORE_SYSTEM = "CORE_SYSTEM"
    DEVELOPER_TOOL = "DEVELOPER_TOOL"
    WEB_BROWSER = "WEB_BROWSER"
    PRODUCTIVITY = "PRODUCTIVITY"
    UTILITY = "UTILITY"
    MEDIA = "MEDIA"
    OTHER = "OTHER"


@dataclass(frozen=True)
class MacAppInfo:
    """Strongly-typed representation of a macOS application bundle (.app)."""

    name: str
    bundle_id: str
    bundle_path: str
    version: str = "Unknown"
    build_version: Optional[str] = None
    executable_name: Optional[str] = None
    executable_path: Optional[str] = None
    min_os_version: Optional[str] = None
    ownership: ComponentOwnership = ComponentOwnership.VENDOR_MANAGED
    category: ApplicationCategory = ApplicationCategory.OTHER
    is_apple: bool = False
    is_user_app: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert application metadata model to dictionary representation."""
        return {
            "name": self.name,
            "bundle_id": self.bundle_id,
            "bundle_path": self.bundle_path,
            "version": self.version,
            "build_version": self.build_version,
            "executable_name": self.executable_name,
            "executable_path": self.executable_path,
            "min_os_version": self.min_os_version,
            "ownership": self.ownership.value,
            "category": self.category.value,
            "is_apple": self.is_apple,
            "is_user_app": self.is_user_app,
        }


@dataclass(frozen=True)
class MacAppInventoryReport:
    """Comprehensive read-only telemetry snapshot of installed macOS applications."""

    collection_method: str
    timestamp: str
    host_platform: str
    applications: List[MacAppInfo] = field(default_factory=list)
    total_applications_count: int = 0
    system_managed_count: int = 0
    vendor_managed_count: int = 0
    user_managed_count: int = 0
    warnings: List[str] = field(default_factory=list)
    unavailable_telemetry: List[str] = field(default_factory=list)

    def find_by_bundle_id(self, bundle_id: str) -> Optional[MacAppInfo]:
        """Find an application by its exact reverse-DNS bundle identifier."""
        target = bundle_id.lower()
        for app in self.applications:
            if app.bundle_id.lower() == target:
                return app
        return None

    def find_by_name(self, name: str) -> Optional[MacAppInfo]:
        """Find an application by its display name (case-insensitive)."""
        target = name.lower()
        for app in self.applications:
            if app.name.lower() == target:
                return app
        return None

    def filter_by_ownership(self, ownership: ComponentOwnership) -> List[MacAppInfo]:
        """Filter applications by maintenance component ownership tier."""
        return [app for app in self.applications if app.ownership == ownership]

    def filter_by_category(self, category: ApplicationCategory) -> List[MacAppInfo]:
        """Filter applications by functional category."""
        return [app for app in self.applications if app.category == category]

    def to_dict(self) -> Dict[str, Any]:
        """Convert complete inventory report to dictionary structure."""
        return {
            "collection_method": self.collection_method,
            "timestamp": self.timestamp,
            "host_platform": self.host_platform,
            "total_applications_count": self.total_applications_count,
            "system_managed_count": self.system_managed_count,
            "vendor_managed_count": self.vendor_managed_count,
            "user_managed_count": self.user_managed_count,
            "applications": [app.to_dict() for app in self.applications],
            "warnings": list(self.warnings),
            "unavailable_telemetry": list(self.unavailable_telemetry),
        }
