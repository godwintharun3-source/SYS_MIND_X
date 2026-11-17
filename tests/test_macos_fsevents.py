"""Comprehensive unit, contract, and integration tests for macOS FSEvents filesystem change notifications."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.fsevents_detector import (
    FLAG_ITEM_CHANGE_OWNER,
    FLAG_ITEM_CLONED,
    FLAG_ITEM_CREATED,
    FLAG_ITEM_INODE_META_MOD,
    FLAG_ITEM_IS_DIR,
    FLAG_ITEM_IS_FILE,
    FLAG_ITEM_IS_SYMLINK,
    FLAG_ITEM_MODIFIED,
    FLAG_ITEM_REMOVED,
    FLAG_ITEM_RENAMED,
    FLAG_ITEM_XATTR_MOD,
    FLAG_MOUNT,
    FLAG_MUST_SCAN_SUBDIRS,
    FLAG_UNMOUNT,
    MacFsEventsDetector,
)
from system_mind.macos.fsevents_models import (
    FsEventFlag,
    FsEventNotification,
    FsEventSnapshotReport,
    FsEventStreamConfig,
    FsEventStreamState,
)
from system_mind.packaging.macos_fsevents import (
    MacOsFsEventsAuditResult,
    MacOsFsEventsValidator,
)


@pytest.mark.unit
def test_fsevents_models_and_serialization() -> None:
    """Verify FsEventNotification dataclass immutability, fields, and properties."""
    ev = FsEventNotification(
        event_id=42,
        path="/Applications/TestApp.app",
        flags=[FsEventFlag.ITEM_CREATED, FsEventFlag.ITEM_IS_DIR],
        raw_flags=0x00020100,
        timestamp="2026-11-17T05:00:00Z",
        is_dir=True,
    )

    assert ev.event_id == 42
    assert ev.path == "/Applications/TestApp.app"
    assert ev.is_created is True
    assert ev.is_removed is False
    assert ev.is_modified is False
    assert ev.is_renamed is False
    assert ev.is_dir is True
    assert ev.is_file is False

    # Verify immutability
    with pytest.raises(FrozenInstanceError):
        ev.event_id = 99  # type: ignore

    # Verify dictionary serialization
    as_dict = ev.to_dict()
    assert as_dict["event_id"] == 42
    assert as_dict["path"] == "/Applications/TestApp.app"
    assert "ITEM_CREATED" in as_dict["flags"]
    assert "ITEM_IS_DIR" in as_dict["flags"]
    assert as_dict["is_created"] is True
    assert as_dict["is_dir"] is True


@pytest.mark.unit
def test_fsevents_snapshot_report_and_filters() -> None:
    """Verify FsEventSnapshotReport query helpers and filtering operations."""
    detector = MacFsEventsDetector()
    report = detector.detect(mock=True)

    assert isinstance(report, FsEventSnapshotReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.events_count == 5
    assert report.created_count == 2
    assert report.modified_count == 1
    assert report.removed_count == 1
    assert report.renamed_count == 1

    # Filter by flag
    created_events = report.filter_by_flag(FsEventFlag.ITEM_CREATED)
    assert len(created_events) == 2
    assert any(e.path == "/Applications/NewUtility.app" for e in created_events)

    # Filter by path prefix
    app_events = report.filter_by_path_prefix("/Applications")
    assert len(app_events) == 2

    # Dictionary serialization
    as_dict = report.to_dict()
    assert as_dict["events_count"] == 5
    assert len(as_dict["events"]) == 5
    assert as_dict["created_count"] == 2


@pytest.mark.unit
def test_fsevents_detector_bitmask_decoding() -> None:
    """Verify bitmask decoding of native Darwin CoreServices FSEvents flags."""
    detector = MacFsEventsDetector()

    # 1. Created Directory
    flags, is_file, is_dir, is_symlink = detector.decode_flags(FLAG_ITEM_CREATED | FLAG_ITEM_IS_DIR)
    assert FsEventFlag.ITEM_CREATED in flags
    assert FsEventFlag.ITEM_IS_DIR in flags
    assert is_dir is True
    assert is_file is False

    # 2. Modified File with Inode Metadata
    flags, is_file, is_dir, is_symlink = detector.decode_flags(
        FLAG_ITEM_MODIFIED | FLAG_ITEM_INODE_META_MOD | FLAG_ITEM_IS_FILE
    )
    assert FsEventFlag.ITEM_MODIFIED in flags
    assert FsEventFlag.ITEM_INODE_META_MOD in flags
    assert is_file is True
    assert is_dir is False

    # 3. Removed Symlink
    flags, is_file, is_dir, is_symlink = detector.decode_flags(FLAG_ITEM_REMOVED | FLAG_ITEM_IS_SYMLINK)
    assert FsEventFlag.ITEM_REMOVED in flags
    assert FsEventFlag.ITEM_IS_SYMLINK in flags
    assert is_symlink is True

    # 4. Renamed, Xattr, Cloned, and Owner Changed
    flags, _, _, _ = detector.decode_flags(
        FLAG_ITEM_RENAMED | FLAG_ITEM_XATTR_MOD | FLAG_ITEM_CLONED | FLAG_ITEM_CHANGE_OWNER
    )
    assert FsEventFlag.ITEM_RENAMED in flags
    assert FsEventFlag.ITEM_XATTR_MOD in flags
    assert FsEventFlag.ITEM_CLONED in flags
    assert FsEventFlag.ITEM_CHANGE_OWNER in flags

    # 5. Volume Mount & Scan Subdirs
    flags, _, _, _ = detector.decode_flags(FLAG_MUST_SCAN_SUBDIRS | FLAG_MOUNT | FLAG_UNMOUNT)
    assert FsEventFlag.MUST_SCAN_SUBDIRS in flags
    assert FsEventFlag.MOUNT in flags
    assert FsEventFlag.UNMOUNT in flags

    # 6. Unknown raw flags
    flags, _, _, _ = detector.decode_flags(0)
    assert flags == [FsEventFlag.UNKNOWN]


@pytest.mark.unit
def test_fsevents_privacy_path_exclusions() -> None:
    """Verify INV-FS-02: Privacy-preserving monitored roots and personal folder exclusion."""
    detector = MacFsEventsDetector()

    # Allowed system and application paths
    assert detector.is_path_allowed("/Applications/Safari.app") is True
    assert detector.is_path_allowed("/System/Applications/Calculator.app") is True
    assert detector.is_path_allowed("/Library/LaunchDaemons/com.apple.sys.plist") is True
    assert detector.is_path_allowed("/tmp/build.log") is True

    # Excluded private user credentials and personal directories
    assert detector.is_path_allowed("/Users/developer/.ssh/id_ed25519") is False
    assert detector.is_path_allowed("/Users/developer/Library/Keychains/login.keychain") is False
    assert detector.is_path_allowed("/Users/developer/.gnupg/secring.gpg") is False
    assert detector.is_path_allowed("/Users/developer/.aws/credentials") is False
    assert detector.is_path_allowed("/Users/developer/.env.production") is False
    assert detector.is_path_allowed("/Users/developer/Documents/taxes.pdf") is False
    assert detector.is_path_allowed("/Users/developer/Downloads/confidential.zip") is False

    # Event construction for excluded path returns None
    ev = detector.create_event(event_id=99, path="/Users/developer/.ssh/id_rsa", raw_flags=FLAG_ITEM_CREATED)
    assert ev is None


@pytest.mark.unit
def test_fsevents_packaging_validator_clean() -> None:
    """Verify that MacOsFsEventsValidator audits cleanly with 0 issues."""
    audit_res = MacOsFsEventsValidator.audit()
    assert isinstance(audit_res, MacOsFsEventsAuditResult)
    assert audit_res.valid is True
    assert len(audit_res.issues) == 0
    assert audit_res.models_valid is True
    assert audit_res.detector_valid is True
    assert audit_res.cli_valid is True
    assert audit_res.safety_valid is True


@pytest.mark.unit
def test_detect_fsevents_cli_mock_and_json() -> None:
    """Verify detect_fsevents CLI tool execution with mock and json flags."""
    cli_path = ROOT_DIR / "tools" / "detect_fsevents.py"
    assert cli_path.exists()

    cmd = [sys.executable, str(cli_path), "--mock", "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0

    data = json.loads(res.stdout)
    assert data["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert data["events_count"] == 5
    assert data["created_count"] == 2
    assert len(data["events"]) == 5

    # Test filtering CLI
    for filt in ["created", "modified", "removed", "renamed", "files", "dirs"]:
        cmd_f = [sys.executable, str(cli_path), "--mock", "--filter", filt]
        res_f = subprocess.run(cmd_f, capture_output=True, text=True, check=False)
        assert res_f.returncode == 0
        assert "SYSTEM MIND X — macOS FSEvents Filesystem Change Notification" in res_f.stdout


@pytest.mark.unit
def test_monitor_fsevents_cli_mock_and_json() -> None:
    """Verify monitor_fsevents CLI tool execution with mock and json flags."""
    cli_path = ROOT_DIR / "tools" / "monitor_fsevents.py"
    if not cli_path.exists():
        pytest.skip("monitor_fsevents CLI not present")

    cmd = [sys.executable, str(cli_path), "--mock", "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0

    data = json.loads(res.stdout)
    assert "events" in data
    assert "collection_method" in data


@pytest.mark.unit
def test_fsevents_stream_config_and_state() -> None:
    """Verify FsEventStreamConfig and FsEventStreamState contracts."""
    config = FsEventStreamConfig(
        paths=["/Applications", "/System/Applications"],
        latency_seconds=0.75,
        flags=0,
        since_when=0,
        private_path_exclusions=["~/.ssh"],
    )
    assert config.latency_seconds == 0.75
    assert len(config.paths) == 2

    c_dict = config.to_dict()
    assert c_dict["latency_seconds"] == 0.75
    assert "/Applications" in c_dict["paths"]

    detector = MacFsEventsDetector()
    assert detector.state == FsEventStreamState.STOPPED


@pytest.mark.integration
def test_live_macos_fsevents_collection() -> None:
    """Verify live snapshot collection on Darwin host environment."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires native Darwin host environment")

    detector = MacFsEventsDetector()
    report = detector.detect(mock=False)

    assert isinstance(report, FsEventSnapshotReport)
    assert report.collection_method in ("NATIVE_DARWIN_FSEVENTS", "MOCK_PLATFORM_ADAPTER")
    assert report.events_count > 0
    assert len(report.monitored_paths) > 0
