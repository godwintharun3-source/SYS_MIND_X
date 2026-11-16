"""Data models for macOS storage volumes, APFS container topology, capacity, and filesystem metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List, Optional


class VolumeRole(str, Enum):
    """Functional role of a mounted filesystem volume in the macOS storage topology."""

    SYSTEM = "SYSTEM"                      # Boot root volume (Signed System Volume, SSV, read-only)
    DATA = "DATA"                          # User data volume (/System/Volumes/Data, read-write)
    VM = "VM"                              # Virtual memory swap volume (/System/Volumes/VM)
    PREBOOT = "PREBOOT"                    # Preboot booter disk (/System/Volumes/Preboot)
    UPDATE = "UPDATE"                      # Staged system updates (/System/Volumes/Update)
    RECOVERY = "RECOVERY"                  # macOS recovery environment
    HARDWARE = "HARDWARE"                  # Hardware diagnostics / iSCPreboot
    USER_EXTERNAL = "USER_EXTERNAL"        # External removable volume or disk image (/Volumes/...)
    SYSTEM_SYNTHETIC = "SYSTEM_SYNTHETIC"  # Synthetic device mount (e.g., /dev)
    GENERIC = "GENERIC"                    # Unclassified filesystem mount


class FilesystemType(str, Enum):
    """Categorical filesystem types commonly encountered on Darwin."""

    APFS = "apfs"
    HFS_PLUS = "hfs"
    DEVFS = "devfs"
    AUTOFS = "autofs"
    MSDOS = "msdos"
    EXFAT = "exfat"
    OTHER = "other"


@dataclass(frozen=True)
class MacVolumeInfo:
    """Strongly typed metadata and capacity metrics for a single mounted volume."""

    device_node: str
    device_identifier: str
    mount_point: str
    volume_name: str
    filesystem_type: str
    volume_role: VolumeRole
    total_capacity_bytes: int
    used_bytes: int
    available_bytes: int
    used_percent: float
    is_read_only: bool = False
    is_sealed_system_volume: bool = False
    is_filevault_encrypted: bool = False
    is_internal: bool = True
    is_solid_state: bool = True
    volume_uuid: Optional[str] = None
    apfs_container_id: Optional[str] = None
    mount_flags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class MacStorageReport:
    """Authoritative aggregated storage telemetry report for macOS companion agent."""

    volumes: List[MacVolumeInfo]
    primary_system_volume: Optional[MacVolumeInfo] = None
    primary_data_volume: Optional[MacVolumeInfo] = None
    total_internal_capacity_bytes: int = 0
    total_internal_available_bytes: int = 0
    has_filevault_active: bool = False
    has_sealed_system_volume: bool = False
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_STATVFS_DISKUTIL"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
