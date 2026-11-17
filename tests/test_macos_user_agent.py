"""Unit, contract, and safety test suite for macOS least-privilege user agent service."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

from system_mind.macos.agent_service_detector import (
    DEFAULT_AGENT_LABEL,
    DEFAULT_PLIST_FILENAME,
    MacUserAgentServiceManager,
)
from system_mind.macos.agent_service_models import (
    AgentServiceState,
    AgentServiceStatusReport,
    LaunchAgentConfig,
)
from system_mind.macos.services_models import ServiceDomain, ServiceStatus
from system_mind.packaging.macos_user_agent import (
    MacOsUserAgentAuditResult,
    MacOsUserAgentValidator,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT_DIR / "tools" / "detect_user_agent.py"


def test_user_agent_models_fidelity() -> None:
    """Verify data model construction, enum mappings, dictionary conversion, and Scan!=Safe invariant."""
    assert AgentServiceState.INSTALLED_ACTIVE.value == "INSTALLED_ACTIVE"
    assert AgentServiceState.INSTALLED_INACTIVE.value == "INSTALLED_INACTIVE"
    assert AgentServiceState.NOT_INSTALLED.value == "NOT_INSTALLED"
    assert AgentServiceState.UNAVAILABLE_PLATFORM.value == "UNAVAILABLE_PLATFORM"
    assert AgentServiceState.MOCK_ACTIVE.value == "MOCK_ACTIVE"

    config = LaunchAgentConfig(
        label="com.systemmind.testagent",
        program_arguments=["/usr/local/bin/test-companion", "--flag"],
        run_at_load=False,
        keep_alive=True,
        limit_load_to_session_type=["Aqua"],
        standard_out_path="~/Library/Logs/system-mind/test.stdout.log",
        standard_error_path="~/Library/Logs/system-mind/test.stderr.log",
        process_type="Background",
        nice=10,
    )
    cfg_dict = config.to_dict()
    assert cfg_dict["label"] == "com.systemmind.testagent"
    assert cfg_dict["program_arguments"] == ["/usr/local/bin/test-companion", "--flag"]
    assert cfg_dict["limit_load_to_session_type"] == ["Aqua"]
    assert cfg_dict["nice"] == 10
    assert cfg_dict["process_type"] == "Background"

    plist_xml = config.to_plist_xml()
    assert '<?xml version="1.0" encoding="UTF-8"?>' in plist_xml
    assert "<!DOCTYPE plist PUBLIC" in plist_xml
    assert "<key>Label</key>" in plist_xml
    assert "<string>com.systemmind.testagent</string>" in plist_xml
    assert "<key>LimitLoadToSessionType</key>" in plist_xml
    assert "<string>Aqua</string>" in plist_xml
    assert "<key>Nice</key>" in plist_xml
    assert "<integer>10</integer>" in plist_xml
    assert "<key>ProcessType</key>" in plist_xml
    assert "<string>Background</string>" in plist_xml

    report = AgentServiceStatusReport(
        label="com.systemmind.testagent",
        domain=ServiceDomain.USER_AGENT,
        state=AgentServiceState.INSTALLED_ACTIVE,
        status=ServiceStatus.RUNNING,
        pid=3456,
        last_exit_code=0,
        plist_path="/Users/test/Library/LaunchAgents/com.systemmind.testagent.plist",
        is_root=False,
        uid=501,
        console_user="developer",
        config=config,
        timestamp="2026-11-17T11:00:00Z",
        host_platform="Darwin",
        scan_proves_safe=False,
        unavailable_telemetry=[],
        is_mock=True,
    )

    # Invariant assertions
    assert report.scan_proves_safe is False
    assert report.is_least_privilege is True
    assert report.is_running is True
    assert report.is_installed is True

    rep_dict = report.to_dict()
    assert rep_dict["label"] == "com.systemmind.testagent"
    assert rep_dict["is_least_privilege"] is True
    assert rep_dict["scan_proves_safe"] is False

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["label"] == "com.systemmind.testagent"
    assert parsed["pid"] == 3456
    assert parsed["scan_proves_safe"] is False


def test_least_privilege_boundary_conditions() -> None:
    """Verify that root processes, system daemons, and UID 0 violate least privilege."""
    config = LaunchAgentConfig()

    # Case 1: Valid unprivileged user agent
    valid_report = AgentServiceStatusReport(
        label="com.systemmind.useragent",
        domain=ServiceDomain.USER_AGENT,
        state=AgentServiceState.INSTALLED_ACTIVE,
        status=ServiceStatus.RUNNING,
        pid=1000,
        last_exit_code=0,
        plist_path="dummy",
        is_root=False,
        uid=501,
        console_user="user",
        config=config,
        timestamp="now",
        host_platform="Darwin",
        scan_proves_safe=False,
        unavailable_telemetry=[],
        is_mock=True,
    )
    assert valid_report.is_least_privilege is True

    # Case 2: Root process (is_root=True)
    root_report = AgentServiceStatusReport(
        label="com.systemmind.useragent",
        domain=ServiceDomain.USER_AGENT,
        state=AgentServiceState.INSTALLED_ACTIVE,
        status=ServiceStatus.RUNNING,
        pid=1000,
        last_exit_code=0,
        plist_path="dummy",
        is_root=True,
        uid=501,
        console_user="user",
        config=config,
        timestamp="now",
        host_platform="Darwin",
        scan_proves_safe=False,
        unavailable_telemetry=[],
        is_mock=True,
    )
    assert root_report.is_least_privilege is False

    # Case 3: UID 0 (root UID)
    uid0_report = AgentServiceStatusReport(
        label="com.systemmind.useragent",
        domain=ServiceDomain.USER_AGENT,
        state=AgentServiceState.INSTALLED_ACTIVE,
        status=ServiceStatus.RUNNING,
        pid=1000,
        last_exit_code=0,
        plist_path="dummy",
        is_root=False,
        uid=0,
        console_user="root",
        config=config,
        timestamp="now",
        host_platform="Darwin",
        scan_proves_safe=False,
        unavailable_telemetry=[],
        is_mock=True,
    )
    assert uid0_report.is_least_privilege is False

    # Case 4: System daemon domain
    daemon_report = AgentServiceStatusReport(
        label="com.systemmind.useragent",
        domain=ServiceDomain.SYSTEM_DAEMON,
        state=AgentServiceState.INSTALLED_ACTIVE,
        status=ServiceStatus.RUNNING,
        pid=1000,
        last_exit_code=0,
        plist_path="dummy",
        is_root=False,
        uid=501,
        console_user="user",
        config=config,
        timestamp="now",
        host_platform="Darwin",
        scan_proves_safe=False,
        unavailable_telemetry=[],
        is_mock=True,
    )
    assert daemon_report.is_least_privilege is False


def test_mock_profiles_simulation() -> None:
    """Verify mock profiles: running, stopped, uninstalled, unsupported."""
    manager = MacUserAgentServiceManager(custom_uid=501)

    # Running
    running = manager.get_mock_status(profile="running")
    assert running.is_running is True
    assert running.is_installed is True
    assert running.state == AgentServiceState.INSTALLED_ACTIVE
    assert running.pid == 4120
    assert running.is_least_privilege is True
    assert running.scan_proves_safe is False
    assert running.is_mock is True

    # Stopped
    stopped = manager.get_mock_status(profile="stopped")
    assert stopped.is_running is False
    assert stopped.is_installed is True
    assert stopped.state == AgentServiceState.INSTALLED_INACTIVE
    assert stopped.pid is None
    assert "process_inactive" in stopped.unavailable_telemetry

    # Uninstalled
    uninstalled = manager.get_mock_status(profile="uninstalled")
    assert uninstalled.is_running is False
    assert uninstalled.is_installed is False
    assert uninstalled.state == AgentServiceState.NOT_INSTALLED
    assert "service_not_installed" in uninstalled.unavailable_telemetry

    # Unsupported
    unsupported = manager.get_mock_status(profile="unsupported")
    assert unsupported.state == AgentServiceState.UNAVAILABLE_PLATFORM
    assert unsupported.domain == ServiceDomain.UNKNOWN
    assert "apple_launchd_unsupported" in unsupported.unavailable_telemetry
    assert "aqua_session_unsupported" in unsupported.unavailable_telemetry


def test_manager_launchctl_parsing_and_fallback() -> None:
    """Verify safe launchctl parsing and graceful fallback logic."""
    manager = MacUserAgentServiceManager(custom_uid=501)

    # Mock launchctl print success
    mock_print_output = "service = {\n\tpid = 7890\n\tlast exit code = 0\n}"
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = mock_print_output
        mock_run.return_value = mock_res

        found, pid, exit_code = manager._query_launchctl_gui()
        assert found is True
        assert pid == 7890
        assert exit_code == 0

    # Mock launchctl print failure, fallback to launchctl list
    with patch("subprocess.run") as mock_run:
        # First call (print) fails
        res_fail = MagicMock()
        res_fail.returncode = 113
        res_fail.stdout = "Could not find service"

        # Second call (list) succeeds
        res_list = MagicMock()
        res_list.returncode = 0
        res_list.stdout = "PID\tStatus\tLabel\n8888\t0\tcom.systemmind.useragent\n"

        mock_run.side_effect = [res_fail, res_list]

        found, pid, exit_code = manager._query_launchctl_gui()
        assert found is True
        assert pid == 8888
        assert exit_code == 0

    # Mock timeout / OSError handling
    with patch("subprocess.run", side_effect=OSError("launchctl not executable")):
        found, pid, exit_code = manager._query_launchctl_gui()
        assert found is False
        assert pid is None
        assert exit_code is None


def test_cli_execution_and_flags() -> None:
    """Verify developer CLI tool supports --mock, --profile, --json, and --generate-plist."""
    # Test --mock --json
    cmd_json = [sys.executable, str(CLI_PATH), "--mock", "--profile", "running", "--json"]
    proc = subprocess.run(cmd_json, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["label"] == "com.systemmind.useragent"
    assert data["state"] == "INSTALLED_ACTIVE"
    assert data["is_least_privilege"] is True
    assert data["scan_proves_safe"] is False

    # Test --mock --profile stopped
    cmd_stopped = [sys.executable, str(CLI_PATH), "--mock", "--profile", "stopped"]
    proc = subprocess.run(cmd_stopped, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "INSTALLED_INACTIVE" in proc.stdout

    # Test --generate-plist
    cmd_plist = [sys.executable, str(CLI_PATH), "--generate-plist"]
    proc = subprocess.run(cmd_plist, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "<key>LimitLoadToSessionType</key>" in proc.stdout
    assert "<string>Aqua</string>" in proc.stdout
    assert "<key>ProcessType</key>" in proc.stdout

    # Test live execution (read-only query)
    cmd_live = [sys.executable, str(CLI_PATH)]
    proc = subprocess.run(cmd_live, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "Least-Privilege User Agent Service Status" in proc.stdout


def test_packaging_validator() -> None:
    """Verify MacOsUserAgentValidator reports valid=True and zero issues."""
    validator = MacOsUserAgentValidator()
    result = validator.audit()

    assert isinstance(result, MacOsUserAgentAuditResult)
    assert result.valid is True
    assert len(result.issues) == 0
    assert result.models_valid is True
    assert result.manager_valid is True
    assert result.cli_valid is True
    assert result.sensors_valid is True
    assert result.safety_valid is True


def test_zero_ambient_shell_authority_and_ast_safety() -> None:
    """Verify SC-01 and lack of forbidden mutating launchctl commands across agent service code."""
    targets = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "agent_service_detector.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "agent_service_models.py",
        CLI_PATH,
    ]

    for target in targets:
        content = target.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(target))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Verify no os.system
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr == "system"
                ):
                    pytest.fail(f"Banned os.system call found in {target.name} at line {node.lineno}")

                # Verify no shell=True
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        pytest.fail(f"Forbidden shell=True keyword found in {target.name} at line {node.lineno}")
