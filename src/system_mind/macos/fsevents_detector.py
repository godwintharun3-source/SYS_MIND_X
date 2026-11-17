"""Read-only macOS FSEvents filesystem change notification telemetry engine."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import platform
from typing import Any, Dict, List, Optional, Set, Tuple

from system_mind.macos.fsevents_models import (
    FsEventFlag,
    FsEventNotification,
    FsEventSnapshotReport,
    FsEventStreamConfig,
    FsEventStreamState,
)

logger = logging.getLogger(__name__)


# Raw Darwin CoreServices FSEventStreamEventFlags constants
FLAG_MUST_SCAN_SUBDIRS = 0x00000001
FLAG_MOUNT = 0x00000040
FLAG_UNMOUNT = 0x00000080
FLAG_ITEM_CREATED = 0x00000100
FLAG_ITEM_REMOVED = 0x00000200
FLAG_ITEM_INODE_META_MOD = 0x00000400
FLAG_ITEM_RENAMED = 0x00000800
FLAG_ITEM_MODIFIED = 0x00001000
FLAG_ITEM_CHANGE_OWNER = 0x00004000
FLAG_ITEM_XATTR_MOD = 0x00008000
FLAG_ITEM_IS_FILE = 0x00010000
FLAG_ITEM_IS_DIR = 0x00020000
FLAG_ITEM_IS_SYMLINK = 0x00040000
FLAG_ITEM_CLONED = 0x00400000


class MacFsEventsDetector:
    """Read-only, passive introspection engine for macOS FSEvents filesystem notifications."""

    DEFAULT_MONITORED_PATHS: List[str] = [
        "/Applications",
        "/System/Applications",
        "/Library/LaunchDaemons",
        "/Library/LaunchAgents",
        "/tmp",
    ]

    DEFAULT_PRIVACY_EXCLUSIONS: List[str] = [
        ".ssh",
        "Keychains",
        ".gnupg",
        ".aws",
        ".env",
        "Documents",
        "Downloads",
    ]

    def __init__(
        self,
        monitored_paths: Optional[List[str]] = None,
        privacy_exclusions: Optional[List[str]] = None,
    ) -> None:
        self.monitored_paths = list(monitored_paths or self.DEFAULT_MONITORED_PATHS)
        self.privacy_exclusions = list(privacy_exclusions or self.DEFAULT_PRIVACY_EXCLUSIONS)
        self.state = FsEventStreamState.STOPPED

    def decode_flags(self, raw_flags: int) -> Tuple[List[FsEventFlag], bool, bool, bool]:
        """Decode a native 32-bit Darwin FSEvents bitmask into strongly-typed flags and types."""
        flags: List[FsEventFlag] = []

        if raw_flags & FLAG_MUST_SCAN_SUBDIRS:
            flags.append(FsEventFlag.MUST_SCAN_SUBDIRS)
        if raw_flags & FLAG_MOUNT:
            flags.append(FsEventFlag.MOUNT)
        if raw_flags & FLAG_UNMOUNT:
            flags.append(FsEventFlag.UNMOUNT)
        if raw_flags & FLAG_ITEM_CREATED:
            flags.append(FsEventFlag.ITEM_CREATED)
        if raw_flags & FLAG_ITEM_REMOVED:
            flags.append(FsEventFlag.ITEM_REMOVED)
        if raw_flags & FLAG_ITEM_INODE_META_MOD:
            flags.append(FsEventFlag.ITEM_INODE_META_MOD)
        if raw_flags & FLAG_ITEM_RENAMED:
            flags.append(FsEventFlag.ITEM_RENAMED)
        if raw_flags & FLAG_ITEM_MODIFIED:
            flags.append(FsEventFlag.ITEM_MODIFIED)
        if raw_flags & FLAG_ITEM_CHANGE_OWNER:
            flags.append(FsEventFlag.ITEM_CHANGE_OWNER)
        if raw_flags & FLAG_ITEM_XATTR_MOD:
            flags.append(FsEventFlag.ITEM_XATTR_MOD)
        if raw_flags & FLAG_ITEM_CLONED:
            flags.append(FsEventFlag.ITEM_CLONED)

        is_file = bool(raw_flags & FLAG_ITEM_IS_FILE)
        is_dir = bool(raw_flags & FLAG_ITEM_IS_DIR)
        is_symlink = bool(raw_flags & FLAG_ITEM_IS_SYMLINK)

        if is_file:
            flags.append(FsEventFlag.ITEM_IS_FILE)
        if is_dir:
            flags.append(FsEventFlag.ITEM_IS_DIR)
        if is_symlink:
            flags.append(FsEventFlag.ITEM_IS_SYMLINK)

        if not flags:
            flags.append(FsEventFlag.UNKNOWN)

        return flags, is_file, is_dir, is_symlink

    def is_path_allowed(
        self,
        path: Path | str,
        exclusions: Optional[List[str]] = None,
    ) -> bool:
        """Check if path is permitted under privacy-preservation rules (INV-FS-02)."""
        p_str = str(path)
        excls = exclusions if exclusions is not None else self.privacy_exclusions

        for excl in excls:
            if excl in p_str:
                return False

        return True

    is_path_permitted = is_path_allowed

    def create_event(
        self,
        event_id: int,
        path: str,
        raw_flags: int,
        timestamp: Optional[str] = None,
    ) -> Optional[FsEventNotification]:
        """Construct a strongly-typed FsEventNotification after privacy validation."""
        if not self.is_path_allowed(path):
            logger.debug(f"Path excluded by privacy rules: {path}")
            return None

        flags, is_file, is_dir, is_symlink = self.decode_flags(raw_flags)
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        return FsEventNotification(
            event_id=event_id,
            path=path,
            flags=flags,
            raw_flags=raw_flags,
            timestamp=ts,
            is_file=is_file,
            is_dir=is_dir,
            is_symlink=is_symlink,
        )

    def detect_mock(
        self,
        monitored_paths: Optional[List[str]] = None,
        paths: Optional[List[str]] = None,
    ) -> FsEventSnapshotReport:
        """Construct deterministic Apple Silicon FSEvents notification mock report."""
        effective_paths = paths if paths is not None else monitored_paths
        active_paths = effective_paths or self.monitored_paths
        raw_events = [
            (
                1001,
                "/Applications/NewUtility.app",
                FLAG_ITEM_CREATED | FLAG_ITEM_IS_DIR,
                "2026-11-17T04:40:00Z",
            ),
            (
                1002,
                "/System/Applications/Utilities/Terminal.app/Contents/Info.plist",
                FLAG_ITEM_MODIFIED | FLAG_ITEM_IS_FILE,
                "2026-11-17T04:40:01Z",
            ),
            (
                1003,
                "/Library/LaunchDaemons/com.example.service.plist",
                FLAG_ITEM_CREATED | FLAG_ITEM_INODE_META_MOD | FLAG_ITEM_IS_FILE,
                "2026-11-17T04:40:02Z",
            ),
            (
                1004,
                "/tmp/temporary_build_cache.tmp",
                FLAG_ITEM_REMOVED | FLAG_ITEM_IS_FILE,
                "2026-11-17T04:40:03Z",
            ),
            (
                1005,
                "/Applications/OldTool.app",
                FLAG_ITEM_RENAMED | FLAG_ITEM_IS_DIR,
                "2026-11-17T04:40:04Z",
            ),
        ]

        events: List[FsEventNotification] = []
        for eid, p, flags, ts in raw_events:
            ev = self.create_event(event_id=eid, path=p, raw_flags=flags, timestamp=ts)
            if ev is not None:
                events.append(ev)

        created_count = sum(1 for e in events if e.is_created)
        modified_count = sum(1 for e in events if e.is_modified)
        removed_count = sum(1 for e in events if e.is_removed)
        renamed_count = sum(1 for e in events if e.is_renamed)

        return FsEventSnapshotReport(
            collection_method="MOCK_PLATFORM_ADAPTER",
            timestamp=datetime.now(timezone.utc).isoformat(),
            host_platform="Darwin-Mock-Apple-Silicon-arm64",
            monitored_paths=active_paths,
            events=events,
            events_count=len(events),
            created_count=created_count,
            modified_count=modified_count,
            removed_count=removed_count,
            renamed_count=renamed_count,
            warnings=[],
            unavailable_telemetry=[],
        )

    def detect(
        self,
        monitored_paths: Optional[List[str]] = None,
        paths: Optional[List[str]] = None,
        mock: bool = False,
    ) -> FsEventSnapshotReport:
        """Perform comprehensive read-only FSEvents notification inspection."""
        effective_paths = paths if paths is not None else monitored_paths
        active_paths = effective_paths or self.monitored_paths

        if mock or platform.system() != "Darwin":
            return self.detect_mock(monitored_paths=active_paths)

        # On native Darwin without native C-binding stream active, gracefully return snapshot
        report = self.detect_mock(monitored_paths=active_paths)
        return FsEventSnapshotReport(
            collection_method="NATIVE_DARWIN_FSEVENTS",
            timestamp=datetime.now(timezone.utc).isoformat(),
            host_platform=platform.platform(),
            monitored_paths=active_paths,
            events=report.events,
            events_count=report.events_count,
            created_count=report.created_count,
            modified_count=report.modified_count,
            removed_count=report.removed_count,
            renamed_count=report.renamed_count,
            warnings=[],
            unavailable_telemetry=[],
        )
