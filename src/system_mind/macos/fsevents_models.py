"""Strongly-typed data models for macOS FSEvents filesystem change notification telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FsEventFlag(str, Enum):
    """Categorical decoded FSEvents lifecycle and item type flags."""

    ITEM_CREATED = "ITEM_CREATED"
    ITEM_REMOVED = "ITEM_REMOVED"
    ITEM_MODIFIED = "ITEM_MODIFIED"
    ITEM_RENAMED = "ITEM_RENAMED"
    ITEM_INODE_META_MOD = "ITEM_INODE_META_MOD"
    ITEM_XATTR_MOD = "ITEM_XATTR_MOD"
    ITEM_CHANGE_OWNER = "ITEM_CHANGE_OWNER"
    ITEM_CLONED = "ITEM_CLONED"
    ITEM_IS_FILE = "ITEM_IS_FILE"
    ITEM_IS_DIR = "ITEM_IS_DIR"
    ITEM_IS_SYMLINK = "ITEM_IS_SYMLINK"
    MUST_SCAN_SUBDIRS = "MUST_SCAN_SUBDIRS"
    MOUNT = "MOUNT"
    UNMOUNT = "UNMOUNT"
    UNKNOWN = "UNKNOWN"


class FsEventStreamState(str, Enum):
    """Operational state of the filesystem notification stream."""

    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class FsEventNotification:
    """Strongly-typed filesystem change event notification emitted by FSEvents."""

    event_id: int
    path: str
    flags: List[FsEventFlag]
    raw_flags: int
    timestamp: str
    is_file: bool = False
    is_dir: bool = False
    is_symlink: bool = False

    @property
    def is_created(self) -> bool:
        """Return True if event represents an item creation."""
        return FsEventFlag.ITEM_CREATED in self.flags

    @property
    def is_removed(self) -> bool:
        """Return True if event represents an item removal/deletion."""
        return FsEventFlag.ITEM_REMOVED in self.flags

    @property
    def is_modified(self) -> bool:
        """Return True if event represents a content modification."""
        return FsEventFlag.ITEM_MODIFIED in self.flags

    @property
    def is_renamed(self) -> bool:
        """Return True if event represents an item rename or move."""
        return FsEventFlag.ITEM_RENAMED in self.flags

    def to_dict(self) -> Dict[str, Any]:
        """Convert event notification to dictionary representation."""
        return {
            "event_id": self.event_id,
            "path": self.path,
            "flags": [f.value for f in self.flags],
            "raw_flags": self.raw_flags,
            "timestamp": self.timestamp,
            "is_file": self.is_file,
            "is_dir": self.is_dir,
            "is_symlink": self.is_symlink,
            "is_created": self.is_created,
            "is_removed": self.is_removed,
            "is_modified": self.is_modified,
            "is_renamed": self.is_renamed,
        }


@dataclass(frozen=True)
class FsEventStreamConfig:
    """Configuration parameters for initializing an FSEvent notification stream."""

    paths: List[str]
    latency_seconds: float = 0.5
    flags: int = 0
    since_when: int = 0
    private_path_exclusions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert stream configuration to dictionary structure."""
        return {
            "paths": list(self.paths),
            "latency_seconds": self.latency_seconds,
            "flags": self.flags,
            "since_when": self.since_when,
            "private_path_exclusions": list(self.private_path_exclusions),
        }


@dataclass(frozen=True)
class FsEventSnapshotReport:
    """Comprehensive read-only telemetry snapshot of monitored filesystem events."""

    collection_method: str
    timestamp: str
    host_platform: str
    monitored_paths: List[str]
    events: List[FsEventNotification] = field(default_factory=list)
    events_count: int = 0
    created_count: int = 0
    modified_count: int = 0
    removed_count: int = 0
    renamed_count: int = 0
    warnings: List[str] = field(default_factory=list)
    unavailable_telemetry: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe

    def filter_by_flag(self, flag: FsEventFlag) -> List[FsEventNotification]:
        """Filter events containing a specific FsEventFlag."""
        return [e for e in self.events if flag in e.flags]

    def filter_by_path_prefix(self, prefix: str) -> List[FsEventNotification]:
        """Filter events whose path starts with the given prefix."""
        p_clean = prefix.rstrip("/")
        return [e for e in self.events if e.path.startswith(p_clean)]

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot report to dictionary structure."""
        return {
            "collection_method": self.collection_method,
            "timestamp": self.timestamp,
            "host_platform": self.host_platform,
            "monitored_paths": list(self.monitored_paths),
            "events_count": self.events_count,
            "created_count": self.created_count,
            "modified_count": self.modified_count,
            "removed_count": self.removed_count,
            "renamed_count": self.renamed_count,
            "events": [e.to_dict() for e in self.events],
            "warnings": list(self.warnings),
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "scan_proves_safe": self.scan_proves_safe,
        }
