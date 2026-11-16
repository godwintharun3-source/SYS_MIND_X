"""Comprehensive unit, contract, and integration tests for macOS launchd services and login items telemetry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.services_detector import MacServicesDetector
from system_mind.macos.services_models import (
    LoginItemKind,
    MacLaunchdService,
    MacLoginItem,
    MacServicesReport,
    ServiceDomain,
    ServiceOwnership,
    ServiceStatus,
)
from system_mind.packaging.macos_services import (
    MacOsServicesAuditResult,
    MacOsServicesValidator,
)


@pytest.mark.unit
def test_macos_services_detector_mock_mode() -> None:
    """Verify services and login items detection using mock mode."""
    detector = MacServicesDetector()
    report = detector.detect(mock=True)

    assert isinstance(report, MacServicesReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.total_services_count == 8
    assert report.running_services_count == 4
    assert report.loaded_services_count == 8
    assert report.system_managed_count == 3
    assert report.vendor_managed_count == 3
    assert report.user_managed_count == 2
    assert report.total_login_items_count == 2

    # Verify Finder service
    finder = report.find_by_label("com.apple.Finder")
    assert finder is not None
    assert finder.pid == 653
    assert finder.domain == ServiceDomain.SYSTEM_AGENT
    assert finder.status == ServiceStatus.RUNNING
    assert finder.ownership == ServiceOwnership.SYSTEM_MANAGED
    assert finder.is_apple is True
    assert finder.is_running is True
    assert finder.is_system_managed is True

    # Verify user login item
    assert len(report.login_items) == 2
    gemini = report.login_items[0]
    assert gemini.name == "GeminiAppLauncher"
    assert gemini.hidden is False
    assert gemini.kind == LoginItemKind.APPLICATION
    assert gemini.ownership == ServiceOwnership.USER_MANAGED


@pytest.mark.unit
def test_parse_launchctl_line_and_output() -> None:
    """Verify robust parsing of launchctl list stdout lines."""
    detector = MacServicesDetector()

    # Active running process with PID
    res1 = detector.parse_launchctl_line("653\t0\tcom.apple.Finder")
    assert res1 == (653, 0, "com.apple.Finder")

    # Inactive job with dash PID and negative signal exit
    res2 = detector.parse_launchctl_line("-\t-9\tcom.apple.progressd")
    assert res2 == (None, -9, "com.apple.progressd")

    # Positive exit code
    res3 = detector.parse_launchctl_line("-\t78\tcom.custom.failed")
    assert res3 == (None, 78, "com.custom.failed")

    # Header line skipping
    assert detector.parse_launchctl_line("PID\tStatus\tLabel") is None

    # Empty and whitespace lines
    assert detector.parse_launchctl_line("") is None
    assert detector.parse_launchctl_line("   ") is None

    # Full output string parsing
    sample_output = (
        "PID\tStatus\tLabel\n"
        "653\t0\tcom.apple.Finder\n"
        "-\t0\tcom.apple.SafariHistoryServiceAgent\n"
        "892\t0\thomebrew.mxcl.mysql\n"
    )
    parsed = detector.parse_launchctl_output(sample_output)
    assert len(parsed) == 3
    assert parsed[0] == (653, 0, "com.apple.Finder")
    assert parsed[1] == (None, 0, "com.apple.SafariHistoryServiceAgent")
    assert parsed[2] == (892, 0, "homebrew.mxcl.mysql")


@pytest.mark.unit
def test_classify_ownership() -> None:
    """Verify deterministic classification of service component ownership."""
    detector = MacServicesDetector()

    # Apple system agent / daemon
    assert detector.classify_ownership("com.apple.Finder", ServiceDomain.SYSTEM_AGENT) == ServiceOwnership.SYSTEM_MANAGED
    assert detector.classify_ownership("com.apple.logd", ServiceDomain.SYSTEM_DAEMON) == ServiceOwnership.SYSTEM_MANAGED
    assert detector.classify_ownership("custom.label", ServiceDomain.RUNTIME_LOADED, "/System/Library/LaunchAgents/custom.plist") == ServiceOwnership.SYSTEM_MANAGED

    # User agent
    assert detector.classify_ownership("homebrew.mxcl.mysql", ServiceDomain.USER_AGENT) == ServiceOwnership.USER_MANAGED
    assert detector.classify_ownership("com.custom.user", ServiceDomain.RUNTIME_LOADED, "/Users/tharun/Library/LaunchAgents/com.custom.user.plist") == ServiceOwnership.USER_MANAGED

    # Vendor daemon / agent
    assert detector.classify_ownership("com.cloudflare.warp.daemon", ServiceDomain.GLOBAL_DAEMON) == ServiceOwnership.VENDOR_MANAGED
    assert detector.classify_ownership("com.oracle.java.Java-Updater", ServiceDomain.GLOBAL_AGENT) == ServiceOwnership.VENDOR_MANAGED


@pytest.mark.unit
def test_scan_plist_file() -> None:
    """Verify safe launchd plist parsing with binary path extraction."""
    import plistlib

    detector = MacServicesDetector()

    with tempfile.TemporaryDirectory() as tmp_dir:
        plist_path = Path(tmp_dir) / "com.example.service.plist"
        content = {
            "Label": "com.example.service",
            "ProgramArguments": ["/usr/local/bin/my_service", "--token", "secret123"],
            "RunAtLoad": True,
            "KeepAlive": True,
        }
        with open(plist_path, "wb") as fp:
            plistlib.dump(content, fp)

        metadata = detector.scan_plist_file(plist_path)
        assert metadata is not None
        assert metadata["label"] == "com.example.service"
        # Verify argument redaction: only binary path is captured, credentials in args excluded
        assert metadata["program"] == "/usr/local/bin/my_service"
        assert metadata["run_at_load"] is True
        assert metadata["keep_alive"] is True


@pytest.mark.unit
def test_report_query_helpers() -> None:
    """Verify helper query accessors on MacServicesReport."""
    detector = MacServicesDetector()
    report = detector.detect_mock()

    # find_by_label
    assert report.find_by_label("com.apple.Finder") is not None
    assert report.find_by_label("nonexistent.service") is None

    # filter_by_domain
    system_agents = report.filter_by_domain(ServiceDomain.SYSTEM_AGENT)
    assert len(system_agents) == 3
    assert all(s.domain == ServiceDomain.SYSTEM_AGENT for s in system_agents)

    # filter_by_ownership
    system_managed = report.filter_by_ownership(ServiceOwnership.SYSTEM_MANAGED)
    assert len(system_managed) == 3
    vendor_managed = report.filter_by_ownership(ServiceOwnership.VENDOR_MANAGED)
    assert len(vendor_managed) == 3
    user_managed = report.filter_by_ownership(ServiceOwnership.USER_MANAGED)
    assert len(user_managed) == 2

    # get_running_services
    running = report.get_running_services()
    assert len(running) == 4
    assert all(s.is_running for s in running)


@pytest.mark.unit
def test_non_darwin_fallback_behavior() -> None:
    """Verify graceful fallback and unavailable telemetry on non-Darwin platforms."""
    detector = MacServicesDetector()

    with patch("platform.system", return_value="Linux"):
        with patch("platform.machine", return_value="x86_64"):
            report = detector.detect()

            assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
            assert "launchctl" in report.unavailable_telemetry
            assert "osascript_system_events" in report.unavailable_telemetry
            assert any("Non-Darwin" in w for w in report.warnings)
            assert report.total_services_count > 0


@pytest.mark.integration
def test_macos_services_detector_live_on_darwin() -> None:
    """Verify live read-only launchd and login item collection when executing on Darwin."""
    if platform.system() != "Darwin":
        pytest.skip("Live test only runs on Darwin hosts")

    detector = MacServicesDetector()
    report = detector.detect()

    assert report.collection_method == "NATIVE_DARWIN_LAUNCHD"
    assert report.total_services_count > 50
    assert report.running_services_count > 10
    assert report.system_managed_count > 10
    assert len(report.services) == report.total_services_count

    # Check for core Apple service
    finder = report.find_by_label("com.apple.Finder")
    assert finder is not None
    assert finder.is_apple is True


@pytest.mark.contract
def test_macos_services_validator_clean_audit() -> None:
    """Verify that MacOsServicesValidator clean audit passes with 0 issues."""
    audit_res = MacOsServicesValidator.audit()

    assert isinstance(audit_res, MacOsServicesAuditResult)
    assert audit_res.models_valid is True
    assert audit_res.detector_valid is True
    assert audit_res.cli_valid is True
    assert audit_res.safety_valid is True
    assert audit_res.valid is True
    assert len(audit_res.issues) == 0


@pytest.mark.contract
def test_detect_services_cli_execution() -> None:
    """Verify CLI tool execution across mock, json, running, and domain options."""
    cli_path = ROOT_DIR / "tools" / "detect_services.py"
    assert cli_path.exists(), f"CLI tool must exist at {cli_path}"

    # 1. Mock JSON mode
    res_json = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_json.returncode == 0
    payload = json.loads(res_json.stdout)
    assert payload["collection_method"] == "MOCK_PLATFORM_ADAPTER"
    assert payload["total_services_count"] == 8

    # 2. Running filter
    res_running = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--running"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_running.returncode == 0
    assert "Running Services Only" in res_running.stdout

    # 3. Domain filter
    res_domain = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--domain", "GLOBAL_DAEMON"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_domain.returncode == 0
    assert "Domain=GLOBAL_DAEMON" in res_domain.stdout

    # 4. Login items filter
    res_login = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--login-items"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_login.returncode == 0
    assert "GeminiAppLauncher" in res_login.stdout

    # 5. Assertion flag success
    res_assert = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-services", "5"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_assert.returncode == 0


@pytest.mark.unit
def test_services_models_immutability() -> None:
    """Verify that service and login item models are frozen dataclasses."""
    service = MacLaunchdService(
        label="com.apple.test",
        pid=100,
        domain=ServiceDomain.SYSTEM_AGENT,
        status=ServiceStatus.RUNNING,
    )
    with pytest.raises(FrozenInstanceError):
        service.label = "mutated.label"  # type: ignore

    login_item = MacLoginItem(name="TestItem")
    with pytest.raises(FrozenInstanceError):
        login_item.name = "mutated.name"  # type: ignore


@pytest.mark.unit
def test_login_items_query_error_handling() -> None:
    """Verify that query_login_items handles timeouts and errors gracefully."""
    detector = MacServicesDetector()

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=3)):
        items, warnings = detector.query_login_items()
        assert len(items) == 0
        assert any("timed out" in w for w in warnings)

    with patch("subprocess.run", side_effect=OSError("Command not found")):
        items, warnings = detector.query_login_items()
        assert len(items) == 0
        assert any("encountered error" in w for w in warnings)
