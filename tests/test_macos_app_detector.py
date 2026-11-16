"""Comprehensive unit, contract, and integration tests for macOS installed application inventory and bundle identifiers."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.core.types import ComponentOwnership
from system_mind.macos.app_detector import MacAppDetector
from system_mind.macos.app_models import (
    ApplicationCategory,
    MacAppInfo,
    MacAppInventoryReport,
)
from system_mind.packaging.macos_apps import (
    MacOsAppAuditResult,
    MacOsAppValidator,
)


@pytest.mark.unit
def test_macos_app_detector_mock_mode() -> None:
    """Verify application inventory detection in mock mode."""
    detector = MacAppDetector()
    report = detector.detect(mock=True)

    assert isinstance(report, MacAppInventoryReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.total_applications_count == 7
    assert report.system_managed_count == 3
    assert report.vendor_managed_count == 3
    assert report.user_managed_count == 1
    assert len(report.applications) == 7

    # Verify Safari app
    safari = report.find_by_bundle_id("com.apple.Safari")
    assert safari is not None
    assert safari.name == "Safari"
    assert safari.bundle_path == "/System/Applications/Safari.app"
    assert safari.version == "18.0"
    assert safari.ownership == ComponentOwnership.SYSTEM_MANAGED
    assert safari.category == ApplicationCategory.WEB_BROWSER
    assert safari.is_apple is True
    assert safari.is_user_app is False

    # Verify VS Code app
    vscode = report.find_by_bundle_id("com.microsoft.VSCode")
    assert vscode is not None
    assert vscode.name == "Visual Studio Code"
    assert vscode.ownership == ComponentOwnership.VENDOR_MANAGED
    assert vscode.category == ApplicationCategory.DEVELOPER_TOOL
    assert vscode.is_apple is False
    assert vscode.is_user_app is True

    # Verify custom user app
    custom = report.find_by_bundle_id("com.user.CustomTool")
    assert custom is not None
    assert custom.name == "CustomTool"
    assert custom.ownership == ComponentOwnership.USER_MANAGED
    assert custom.category == ApplicationCategory.UTILITY
    assert custom.is_user_app is True

    # Test query helpers: find_by_name, filter_by_ownership, filter_by_category
    assert report.find_by_name("safari") is not None
    assert report.find_by_name("nonexistent") is None
    sys_apps = report.filter_by_ownership(ComponentOwnership.SYSTEM_MANAGED)
    assert len(sys_apps) == 3
    browsers = report.filter_by_category(ApplicationCategory.WEB_BROWSER)
    assert len(browsers) == 2


@pytest.mark.unit
def test_non_darwin_or_live_detection() -> None:
    """Verify live detection or graceful fallback when executing on Darwin / non-Darwin."""
    detector = MacAppDetector()
    if platform.system() == "Darwin":
        report = detector.detect(mock=False)
        assert isinstance(report, MacAppInventoryReport)
        assert report.total_applications_count > 0
    else:
        with patch("platform.system", return_value="Linux"):
            report = detector.detect(mock=False)
            assert isinstance(report, MacAppInventoryReport)
            assert report.collection_method == "MOCK_PLATFORM_ADAPTER"


@pytest.mark.unit
def test_app_info_and_report_serialization() -> None:
    """Verify serialization to dictionary and JSON compatibility."""
    detector = MacAppDetector()
    report = detector.detect(mock=True)
    report_dict = report.to_dict()

    assert report_dict["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert report_dict["total_applications_count"] == 7
    assert report_dict["system_managed_count"] == 3
    assert report_dict["vendor_managed_count"] == 3
    assert report_dict["user_managed_count"] == 1
    assert len(report_dict["applications"]) == 7

    # Validate JSON round-trip
    dumped = json.dumps(report_dict)
    loaded = json.loads(dumped)
    assert loaded["total_applications_count"] == 7
    assert loaded["applications"][0]["name"] == "Safari"


@pytest.mark.unit
def test_app_models_frozen_immutability() -> None:
    """Verify data models are immutable frozen dataclasses."""
    app = MacAppInfo(
        name="TestApp",
        bundle_id="com.test.app",
        bundle_path="/Applications/TestApp.app",
        version="1.0",
    )
    with pytest.raises(FrozenInstanceError):
        app.name = "MutatedName"  # type: ignore[misc]

    report = MacAppInventoryReport(
        collection_method="MOCK",
        timestamp="2026-11-16T12:00:00Z",
        host_platform="macOS",
        total_applications_count=1,
        system_managed_count=0,
        vendor_managed_count=1,
        user_managed_count=0,
        applications=(app,),
    )
    with pytest.raises(FrozenInstanceError):
        report.total_applications_count = 99  # type: ignore[misc]


@pytest.mark.unit
def test_classify_category() -> None:
    """Verify functional category classification heuristics."""
    detector = MacAppDetector()

    # Web browser
    assert detector.classify_category("com.apple.Safari", "Safari", Path("/Applications/Safari.app")) == ApplicationCategory.WEB_BROWSER
    assert detector.classify_category("com.google.Chrome", "Google Chrome", Path("/Applications/Google Chrome.app")) == ApplicationCategory.WEB_BROWSER
    assert detector.classify_category("org.mozilla.firefox", "Firefox", Path("/Applications/Firefox.app")) == ApplicationCategory.WEB_BROWSER

    # Developer tool
    assert detector.classify_category("com.microsoft.VSCode", "Code", Path("/Applications/Visual Studio Code.app")) == ApplicationCategory.DEVELOPER_TOOL
    assert detector.classify_category("com.apple.dt.Xcode", "Xcode", Path("/Applications/Xcode.app")) == ApplicationCategory.DEVELOPER_TOOL
    assert detector.classify_category("com.apple.Terminal", "Terminal", Path("/Applications/Utilities/Terminal.app")) == ApplicationCategory.DEVELOPER_TOOL
    assert detector.classify_category("com.docker.docker", "Docker Desktop", Path("/Applications/Docker.app")) == ApplicationCategory.DEVELOPER_TOOL

    # Core system
    assert detector.classify_category("com.apple.finder", "Finder", Path("/System/Library/CoreServices/Finder.app")) == ApplicationCategory.CORE_SYSTEM
    assert detector.classify_category("com.apple.systempreferences", "System Settings", Path("/System/Applications/System Settings.app")) == ApplicationCategory.CORE_SYSTEM

    # Media
    assert detector.classify_category("com.spotify.client", "Spotify", Path("/Applications/Spotify.app")) == ApplicationCategory.MEDIA
    assert detector.classify_category("org.videolan.vlc", "VLC", Path("/Applications/VLC.app")) == ApplicationCategory.MEDIA

    # Productivity
    assert detector.classify_category("com.tinyspeck.slackmacgap", "Slack", Path("/Applications/Slack.app")) == ApplicationCategory.PRODUCTIVITY
    assert detector.classify_category("com.apple.Notes", "Notes", Path("/Applications/Notes.app")) == ApplicationCategory.PRODUCTIVITY

    # Utility
    assert detector.classify_category("com.apple.DiskUtility", "Disk Utility", Path("/System/Applications/Utilities/Disk Utility.app")) == ApplicationCategory.UTILITY

    # Other fallback
    assert detector.classify_category("com.unknown.arbitrary", "RandomApp", Path("/Applications/RandomApp.app")) == ApplicationCategory.OTHER


@pytest.mark.unit
def test_ownership_classification() -> None:
    """Verify ownership classification rules based on path and bundle id."""
    detector = MacAppDetector()

    # System managed
    own1, is_apple1, is_user1 = detector.classify_ownership("com.apple.Safari", Path("/System/Applications/Safari.app"))
    assert own1 == ComponentOwnership.SYSTEM_MANAGED
    assert is_apple1 is True
    assert is_user1 is False

    own2, is_apple2, is_user2 = detector.classify_ownership("com.apple.finder", Path("/System/Library/CoreServices/Finder.app"))
    assert own2 == ComponentOwnership.SYSTEM_MANAGED
    assert is_apple2 is True
    assert is_user2 is False

    # Vendor managed (third-party in /Applications)
    own3, is_apple3, is_user3 = detector.classify_ownership("com.google.Chrome", Path("/Applications/Google Chrome.app"))
    assert own3 == ComponentOwnership.VENDOR_MANAGED
    assert is_apple3 is False
    assert is_user3 is True

    own4, is_apple4, is_user4 = detector.classify_ownership("com.microsoft.VSCode", Path("/Applications/Visual Studio Code.app"))
    assert own4 == ComponentOwnership.VENDOR_MANAGED
    assert is_apple4 is False
    assert is_user4 is True

    # User managed (in user home Applications directory)
    user_app_path = Path.home() / "Applications" / "CustomTool.app"
    own5, is_apple5, is_user5 = detector.classify_ownership("com.user.CustomTool", user_app_path)
    assert own5 == ComponentOwnership.USER_MANAGED
    assert is_apple5 is False
    assert is_user5 is True


@pytest.mark.unit
def test_scan_bundle_corrupted_or_missing_plist() -> None:
    """Verify robust handling of corrupted or missing Info.plist files."""
    detector = MacAppDetector()

    with tempfile.TemporaryDirectory() as tmpdir:
        fake_app = Path(tmpdir) / "Broken.app"
        fake_app.mkdir()

        # No Contents directory
        assert detector.scan_bundle(fake_app) is None

        # Contents directory with missing Info.plist
        contents_dir = fake_app / "Contents"
        contents_dir.mkdir()
        assert detector.scan_bundle(fake_app) is None

        # Corrupted non-plist content
        plist_path = contents_dir / "Info.plist"
        plist_path.write_text("NOT A VALID PLIST CONTENT XML")
        assert detector.scan_bundle(fake_app) is None


@pytest.mark.unit
def test_scan_bundle_valid_plist() -> None:
    """Verify inspection of a valid synthesized application bundle."""
    detector = MacAppDetector()

    with tempfile.TemporaryDirectory() as tmpdir:
        app_path = Path(tmpdir) / "SampleTestApp.app"
        contents = app_path / "Contents"
        macos_dir = contents / "MacOS"
        macos_dir.mkdir(parents=True)

        exec_path = macos_dir / "SampleTestApp"
        exec_path.write_text("#!/bin/sh\nexit 0\n")

        plist_data = {
            "CFBundleIdentifier": "com.sample.TestApp",
            "CFBundleName": "SampleTestApp",
            "CFBundleShortVersionString": "2.4.1",
            "CFBundleVersion": "142",
            "CFBundleExecutable": "SampleTestApp",
            "LSMinimumSystemVersion": "13.0",
        }
        with open(contents / "Info.plist", "wb") as fp:
            plistlib.dump(plist_data, fp)

        info = detector.scan_bundle(app_path)
        assert info is not None
        assert info.name == "SampleTestApp"
        assert info.bundle_id == "com.sample.TestApp"
        assert info.version == "2.4.1"
        assert info.build_version == "142"
        assert info.executable_name == "SampleTestApp"
        assert info.min_os_version == "13.0"
        assert info.is_apple is False


@pytest.mark.unit
def test_macos_app_validator_audit() -> None:
    """Verify that MacOsAppValidator audit passes cleanly with 0 issues."""
    audit_res = MacOsAppValidator.audit()
    assert isinstance(audit_res, MacOsAppAuditResult)
    assert audit_res.valid is True
    assert len(audit_res.issues) == 0
    assert audit_res.models_valid is True
    assert audit_res.detector_valid is True
    assert audit_res.cli_valid is True
    assert audit_res.safety_valid is True


@pytest.mark.integration
def test_cli_detect_apps_mock_execution() -> None:
    """Verify tools/detect_apps.py executes in mock mode and returns valid formatted output."""
    cli_path = ROOT_DIR / "tools" / "detect_apps.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--mock"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "macOS Installed Application Inventory" in proc.stdout
    assert "Safari" in proc.stdout
    assert "com.apple.Safari" in proc.stdout
    assert "Google Chrome" in proc.stdout


@pytest.mark.integration
def test_cli_detect_apps_json_execution() -> None:
    """Verify tools/detect_apps.py executes with --json --mock and emits valid JSON."""
    cli_path = ROOT_DIR / "tools" / "detect_apps.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--json", "--mock"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    parsed = json.loads(proc.stdout)
    assert parsed["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert parsed["total_applications_count"] == 7
    assert len(parsed["applications"]) == 7
