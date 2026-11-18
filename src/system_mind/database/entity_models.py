"""Database entity models and serialization for Hardware, OS Kernel, and Application digital twin entities."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import sqlite3
from typing import Any, Dict, Optional

from system_mind.core.types import ComponentOwnership
from system_mind.twin.identity import validate_entity_urn


class HardwareCategory(str, Enum):
    """Categorization of hardware entities in the digital twin."""

    HOST = "HOST"
    CPU = "CPU"
    MEMORY = "MEMORY"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    GPU = "GPU"
    BATTERY = "BATTERY"
    USB = "USB"
    PERIPHERAL = "PERIPHERAL"


@dataclass(frozen=True)
class HardwareEntityRecord:
    """Relational database entity record representing a hardware component."""

    entity_urn: str
    device_id: str
    category: HardwareCategory
    model_name: str
    vendor: str = ""
    serial_hash: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance_source: str = "native_sensor"
    scan_proves_safe: bool = False  # Charter invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")
        if not validate_entity_urn(self.entity_urn):
            raise ValueError(f"Invalid canonical entity URN: {self.entity_urn}")
        if not self.device_id.strip():
            raise ValueError("device_id must not be empty")
        if not self.model_name.strip():
            raise ValueError("model_name must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "entity_urn": self.entity_urn,
            "device_id": self.device_id,
            "category": self.category.value,
            "model_name": self.model_name,
            "vendor": self.vendor,
            "serial_hash": self.serial_hash,
            "attributes": self.attributes,
            "observed_at": self.observed_at,
            "provenance_source": self.provenance_source,
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HardwareEntityRecord:
        """Create record from dictionary."""
        category_val = data["category"]
        category = category_val if isinstance(category_val, HardwareCategory) else HardwareCategory(category_val)
        return cls(
            entity_urn=data["entity_urn"],
            device_id=data["device_id"],
            category=category,
            model_name=data["model_name"],
            vendor=data.get("vendor", ""),
            serial_hash=data.get("serial_hash", ""),
            attributes=data.get("attributes", {}),
            observed_at=data.get("observed_at", ""),
            provenance_source=data.get("provenance_source", "native_sensor"),
            scan_proves_safe=data.get("scan_proves_safe", False),
        )

    def to_db_row(self) -> tuple:
        """Serialize to tuple for SQLite INSERT/UPDATE."""
        return (
            self.entity_urn,
            self.device_id,
            self.category.value,
            self.model_name,
            self.vendor,
            self.serial_hash,
            json.dumps(self.attributes, sort_keys=True),
            self.observed_at,
            self.provenance_source,
            0,  # scan_proves_safe
        )

    @classmethod
    def from_db_row(cls, row: tuple | sqlite3.Row) -> HardwareEntityRecord:
        """Deserialize from SQLite row tuple."""
        raw_attrs = row[6]
        attrs = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
        return cls(
            entity_urn=row[0],
            device_id=row[1],
            category=HardwareCategory(row[2]),
            model_name=row[3],
            vendor=row[4],
            serial_hash=row[5],
            attributes=attrs,
            observed_at=row[7],
            provenance_source=row[8],
            scan_proves_safe=bool(row[9]),
        )


@dataclass(frozen=True)
class OsKernelEntityRecord:
    """Relational database entity record representing an OS Kernel and host environment."""

    entity_urn: str
    device_id: str
    os_family: str
    product_version: str
    build_version: str
    kernel_release: str
    architecture: str
    security_posture: Dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance_source: str = "native_sysctl"
    scan_proves_safe: bool = False  # Charter invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")
        if not validate_entity_urn(self.entity_urn):
            raise ValueError(f"Invalid canonical entity URN: {self.entity_urn}")
        if not self.device_id.strip():
            raise ValueError("device_id must not be empty")
        if not self.os_family.strip():
            raise ValueError("os_family must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "entity_urn": self.entity_urn,
            "device_id": self.device_id,
            "os_family": self.os_family,
            "product_version": self.product_version,
            "build_version": self.build_version,
            "kernel_release": self.kernel_release,
            "architecture": self.architecture,
            "security_posture": self.security_posture,
            "observed_at": self.observed_at,
            "provenance_source": self.provenance_source,
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OsKernelEntityRecord:
        """Create record from dictionary."""
        return cls(
            entity_urn=data["entity_urn"],
            device_id=data["device_id"],
            os_family=data["os_family"],
            product_version=data["product_version"],
            build_version=data["build_version"],
            kernel_release=data["kernel_release"],
            architecture=data["architecture"],
            security_posture=data.get("security_posture", {}),
            observed_at=data.get("observed_at", ""),
            provenance_source=data.get("provenance_source", "native_sysctl"),
            scan_proves_safe=data.get("scan_proves_safe", False),
        )

    def to_db_row(self) -> tuple:
        """Serialize to tuple for SQLite INSERT/UPDATE."""
        return (
            self.entity_urn,
            self.device_id,
            self.os_family,
            self.product_version,
            self.build_version,
            self.kernel_release,
            self.architecture,
            json.dumps(self.security_posture, sort_keys=True),
            self.observed_at,
            self.provenance_source,
            0,  # scan_proves_safe
        )

    @classmethod
    def from_db_row(cls, row: tuple | sqlite3.Row) -> OsKernelEntityRecord:
        """Deserialize from SQLite row tuple."""
        raw_sec = row[7]
        sec = json.loads(raw_sec) if isinstance(raw_sec, str) else raw_sec
        return cls(
            entity_urn=row[0],
            device_id=row[1],
            os_family=row[2],
            product_version=row[3],
            build_version=row[4],
            kernel_release=row[5],
            architecture=row[6],
            security_posture=sec,
            observed_at=row[8],
            provenance_source=row[9],
            scan_proves_safe=bool(row[10]),
        )


@dataclass(frozen=True)
class ApplicationEntityRecord:
    """Relational database entity record representing an installed software application."""

    entity_urn: str
    device_id: str
    bundle_id: str
    app_name: str
    version: str
    install_path: str
    ownership: ComponentOwnership
    code_signature: Dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance_source: str = "app_detector"
    scan_proves_safe: bool = False  # Charter invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")
        if not validate_entity_urn(self.entity_urn):
            raise ValueError(f"Invalid canonical entity URN: {self.entity_urn}")
        if not self.device_id.strip():
            raise ValueError("device_id must not be empty")
        if not self.bundle_id.strip():
            raise ValueError("bundle_id must not be empty")
        if not self.app_name.strip():
            raise ValueError("app_name must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "entity_urn": self.entity_urn,
            "device_id": self.device_id,
            "bundle_id": self.bundle_id,
            "app_name": self.app_name,
            "version": self.version,
            "install_path": self.install_path,
            "ownership": self.ownership.value,
            "code_signature": self.code_signature,
            "observed_at": self.observed_at,
            "provenance_source": self.provenance_source,
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ApplicationEntityRecord:
        """Create record from dictionary."""
        ownership_val = data["ownership"]
        ownership = ownership_val if isinstance(ownership_val, ComponentOwnership) else ComponentOwnership(ownership_val)
        return cls(
            entity_urn=data["entity_urn"],
            device_id=data["device_id"],
            bundle_id=data["bundle_id"],
            app_name=data["app_name"],
            version=data["version"],
            install_path=data["install_path"],
            ownership=ownership,
            code_signature=data.get("code_signature", {}),
            observed_at=data.get("observed_at", ""),
            provenance_source=data.get("provenance_source", "app_detector"),
            scan_proves_safe=data.get("scan_proves_safe", False),
        )

    def to_db_row(self) -> tuple:
        """Serialize to tuple for SQLite INSERT/UPDATE."""
        return (
            self.entity_urn,
            self.device_id,
            self.bundle_id,
            self.app_name,
            self.version,
            self.install_path,
            self.ownership.value,
            json.dumps(self.code_signature, sort_keys=True),
            self.observed_at,
            self.provenance_source,
            0,  # scan_proves_safe
        )

    @classmethod
    def from_db_row(cls, row: tuple | sqlite3.Row) -> ApplicationEntityRecord:
        """Deserialize from SQLite row tuple."""
        raw_sig = row[7]
        sig = json.loads(raw_sig) if isinstance(raw_sig, str) else raw_sig
        return cls(
            entity_urn=row[0],
            device_id=row[1],
            bundle_id=row[2],
            app_name=row[3],
            version=row[4],
            install_path=row[5],
            ownership=ComponentOwnership(row[6]),
            code_signature=sig,
            observed_at=row[8],
            provenance_source=row[9],
            scan_proves_safe=bool(row[10]),
        )
