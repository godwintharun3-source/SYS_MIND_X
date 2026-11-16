"""Comprehensive unit, contract, and integration tests for macOS process inventory and resource telemetry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.macos.process_detector import MacProcessDetector
from system_mind.macos.process_models import (
    MacProcessInfo,
    MacProcessReport,
    ProcessRole,
    ProcessState,
)
from system_mind.packaging.macos_process import (
    MacOsProcessAuditResult,
    MacOsProcessValidator,
)
from system_mind.platform.adapter import MockPlatformProfileFactory


@pytest.mark.unit
def test_macos_process_detector_mock_mode() -> None:
    """Verify process inventory detection using safe MockPlatformAdapter."""
    detector = MacProcessDetector()
    mock = MockPlatformProfileFactory.create_macos_apple_silicon_mock()
    report = detector.detect(use_mock=True, mock_adapter=mock)

    assert isinstance(report, MacProcessReport)
    assert report.collection_method == "MOCK_PLATFORM_ADAPTER"
    assert report.total_process_count == 4
    assert report.running_count == 2
    assert report.sleeping_count == 2
    assert report.zombie_count == 0
    assert report.system_core_count == 2
    assert report.user_app_count == 1
    assert report.total_cpu_percent > 0.0
    assert report.total_rss_bytes > 0

    # Verify launchd (PID 1)
    launchd = report.find_by_pid(1)
    assert launchd is not None
    assert launchd.name == "launchd"
    assert launchd.user == "root"
    assert launchd.role == ProcessRole.SYSTEM_CORE
    assert launchd.is_system_core is True
    assert launchd.is_user_app is False

    # Verify Google Chrome (user app)
    chrome = report.find_by_pid(1200)
    assert chrome is not None
    assert chrome.name == "Google Chrome"
    assert chrome.role == ProcessRole.USER_APP
    assert chrome.is_system_core is False
    assert chrome.is_user_app is True

    # Verify python3 (developer tool)
    py = report.find_by_pid(1500)
    assert py is not None
    assert py.name == "python3"
    assert py.role == ProcessRole.DEVELOPER_TOOL


@pytest.mark.unit
def test_parse_ps_line_and_output() -> None:
    """Verify parsing realistic Darwin ps output lines with spaces in paths."""
    detector = MacProcessDetector()

    sample_output = (
        "  PID  PPID   UID USER              %CPU %MEM    RSS      VSZ STAT COMM\n"
        "    1     0     0 root               0.2  0.1  13760 488724880 Ss   /sbin/launchd\n"
        "  338     1     0 root               0.3  0.1   8944 488909136 Ss   /usr/libexec/logd\n"
        " 1200     1   501 tharungodwin      14.5  2.8 460800 358400000 R+   /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
        " 1500  1200   501 tharungodwin       5.2  0.5  81920  61440000 S    /usr/local/bin/python3\n"
    )

    processes, warnings = detector.parse_ps_output(sample_output)
    assert len(warnings) == 0
    assert len(processes) == 4

    p0 = processes[0]
    assert p0.pid == 1
    assert p0.ppid == 0
    assert p0.uid == 0
    assert p0.user == "root"
    assert p0.cpu_percent == 0.2
    assert p0.memory_percent == 0.1
    assert p0.rss_bytes == 13760 * 1024
    assert p0.vsz_bytes == 488724880 * 1024
    assert p0.state == ProcessState.SLEEPING
    assert p0.state_raw == "Ss"
    assert p0.command_path == "/sbin/launchd"
    assert p0.name == "launchd"
    assert p0.role == ProcessRole.SYSTEM_CORE
    assert p0.is_system_core is True

    # Check process with spaces in executable path
    p2 = processes[2]
    assert p2.pid == 1200
    assert p2.user == "tharungodwin"
    assert p2.command_path == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert p2.name == "Google Chrome"
    assert p2.role == ProcessRole.USER_APP
    assert p2.is_user_app is True
    assert p2.state == ProcessState.RUNNING


@pytest.mark.unit
def test_classify_state() -> None:
    """Verify mapping of Darwin status flags to ProcessState enum."""
    detector = MacProcessDetector()

    assert detector.classify_state("R") == ProcessState.RUNNING
    assert detector.classify_state("R+") == ProcessState.RUNNING
    assert detector.classify_state("S") == ProcessState.SLEEPING
    assert detector.classify_state("Ss") == ProcessState.SLEEPING
    assert detector.classify_state("I") == ProcessState.SLEEPING
    assert detector.classify_state("T") == ProcessState.STOPPED
    assert detector.classify_state("Z") == ProcessState.ZOMBIE
    assert detector.classify_state("U") == ProcessState.UNINTERRUPTIBLE
    assert detector.classify_state("D") == ProcessState.UNINTERRUPTIBLE
    assert detector.classify_state("?") == ProcessState.UNKNOWN
    assert detector.classify_state("") == ProcessState.UNKNOWN


@pytest.mark.unit
def test_classify_role_and_ownership() -> None:
    """Verify process role categorization and component ownership classification."""
    detector = MacProcessDetector()

    # Root system core
    role, is_core, is_app = detector.classify_role(0, "root", "/sbin/launchd")
    assert role == ProcessRole.SYSTEM_CORE
    assert is_core is True
    assert is_app is False

    # CoreServices system core
    role, is_core, is_app = detector.classify_role(
        501, "dev", "/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder"
    )
    assert role == ProcessRole.SYSTEM_CORE
    assert is_core is True
    assert is_app is False

    # User application
    role, is_core, is_app = detector.classify_role(
        501, "dev", "/Applications/Visual Studio Code.app/Contents/MacOS/Electron"
    )
    assert role == ProcessRole.USER_APP
    assert is_core is False
    assert is_app is True

    # Developer tools
    role, is_core, is_app = detector.classify_role(501, "dev", "/Users/dev/.cargo/bin/cargo")
    assert role == ProcessRole.DEVELOPER_TOOL
    assert is_core is False
    assert is_app is False

    role, is_core, is_app = detector.classify_role(501, "dev", "/usr/bin/git")
    assert role == ProcessRole.DEVELOPER_TOOL

    role, is_core, is_app = detector.classify_role(501, "dev", "/opt/homebrew/bin/python3")
    assert role == ProcessRole.DEVELOPER_TOOL

    # Background service
    role, is_core, is_app = detector.classify_role(501, "dev", "/usr/local/bin/cloud_agent")
    assert role == ProcessRole.DAEMON_SERVICE


@pytest.mark.unit
def test_report_query_helpers() -> None:
    """Verify MacProcessReport sorting, filtering, and lookup helper methods."""
    p1 = MacProcessInfo(
        pid=10,
        ppid=1,
        uid=0,
        user="root",
        name="low_cpu",
        command_path="/bin/low",
        cpu_percent=1.0,
        rss_bytes=100 * 1024 * 1024,
    )
    p2 = MacProcessInfo(
        pid=20,
        ppid=1,
        uid=501,
        user="alice",
        name="high_cpu",
        command_path="/bin/high",
        cpu_percent=85.0,
        rss_bytes=20 * 1024 * 1024,
    )
    p3 = MacProcessInfo(
        pid=30,
        ppid=1,
        uid=501,
        user="alice",
        name="high_mem",
        command_path="/bin/mem",
        cpu_percent=10.0,
        rss_bytes=500 * 1024 * 1024,
    )

    report = MacProcessReport(processes=[p1, p2, p3])

    # Top CPU
    top_cpu = report.get_top_cpu(2)
    assert len(top_cpu) == 2
    assert top_cpu[0].pid == 20
    assert top_cpu[1].pid == 30

    # Top Memory
    top_mem = report.get_top_memory(2)
    assert len(top_mem) == 2
    assert top_mem[0].pid == 30
    assert top_mem[1].pid == 10

    # Filter by user
    alice_procs = report.filter_by_user("alice")
    assert len(alice_procs) == 2
    assert {p.pid for p in alice_procs} == {20, 30}

    root_procs = report.filter_by_user("ROOT")
    assert len(root_procs) == 1
    assert root_procs[0].pid == 10

    # Find by PID
    assert report.find_by_pid(20) == p2
    assert report.find_by_pid(9999) is None


@pytest.mark.unit
def test_non_darwin_fallback_behavior() -> None:
    """Verify that execution on non-Darwin platforms gracefully falls back."""
    detector = MacProcessDetector()

    with patch("platform.system", return_value="Linux"):
        report = detector.detect()
        assert report.collection_method == "NON_DARWIN_MOCK_FALLBACK"
        assert len(report.unavailable_telemetry) > 0
        assert "Darwin" in report.unavailable_telemetry[0]
        assert report.total_process_count == 4


@pytest.mark.integration
def test_macos_process_detector_live_on_darwin() -> None:
    """Verify live macOS process inventory collection if running on Darwin."""
    if platform.system() != "Darwin":
        pytest.skip("Test requires Darwin macOS host environment")

    detector = MacProcessDetector()
    report = detector.detect()

    assert isinstance(report, MacProcessReport)
    assert report.collection_method == "NATIVE_DARWIN_PS"
    assert report.total_process_count >= 10
    assert report.total_cpu_percent >= 0.0
    assert report.total_rss_bytes > 0

    # launchd (PID 1) must be present on all Darwin hosts
    launchd = report.find_by_pid(1)
    assert launchd is not None
    assert launchd.pid == 1
    assert launchd.user == "root"
    assert launchd.is_system_core is True


@pytest.mark.contract
def test_macos_process_validator_clean_audit() -> None:
    """Verify MacOsProcessValidator reports zero issues on repository code."""
    result = MacOsProcessValidator.audit(ROOT_DIR)
    assert isinstance(result, MacOsProcessAuditResult)
    assert result.valid is True
    assert result.models_valid is True
    assert result.detector_valid is True
    assert result.cli_valid is True
    assert result.safety_valid is True
    assert result.issues == ()


@pytest.mark.contract
def test_detect_processes_cli_execution() -> None:
    """Verify tools/detect_processes.py runs cleanly with CLI arguments."""
    cli_path = ROOT_DIR / "tools" / "detect_processes.py"

    # Test --mock
    proc_mock = subprocess.run(
        [sys.executable, str(cli_path), "--mock"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_mock.returncode == 0
    assert "SYSTEM MIND X — macOS Process Inventory & Resource Usage Telemetry" in proc_mock.stdout
    assert "launchd" in proc_mock.stdout

    # Test --mock --json
    proc_json = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_json.returncode == 0
    data = json.loads(proc_json.stdout)
    assert data["total_process_count"] == 4
    assert len(data["processes"]) == 4

    # Test sorting & filtering
    proc_top = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--top-cpu", "2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_top.returncode == 0
    assert "Top 2 by CPU%" in proc_top.stdout

    proc_user = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--user", "root"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_user.returncode == 0
    assert "Filtered by User:   root" in proc_user.stdout

    # Test assertions
    proc_assert_ok = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-processes", "2"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_assert_ok.returncode == 0

    proc_assert_fail = subprocess.run(
        [sys.executable, str(cli_path), "--mock", "--assert-processes", "999"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_assert_fail.returncode == 1


@pytest.mark.unit
def test_process_models_immutability() -> None:
    """Verify that all process telemetry dataclasses are strictly frozen."""
    proc = MacProcessInfo(
        pid=1,
        ppid=0,
        uid=0,
        user="root",
        name="launchd",
        command_path="/sbin/launchd",
    )
    with pytest.raises(FrozenInstanceError):
        proc.name = "modified_launchd"  # type: ignore

    report = MacProcessReport(processes=[proc])
    with pytest.raises(FrozenInstanceError):
        report.total_process_count = 50  # type: ignore


@pytest.mark.unit
def test_parse_malformed_ps_lines() -> None:
    """Verify graceful handling of empty or truncated lines."""
    detector = MacProcessDetector()
    assert detector.parse_ps_line("") is None
    assert detector.parse_ps_line("   ") is None
    assert detector.parse_ps_line("PID PPID UID USER %CPU %MEM RSS VSZ STAT COMM") is None
    assert detector.parse_ps_line("1 0 0 root 0.1") is None
