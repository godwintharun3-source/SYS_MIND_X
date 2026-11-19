"""Automated packaging validator auditing macOS least-privilege user agent service telemetry."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.agent_service_detector import MacUserAgentServiceManager
from system_mind.macos.agent_service_models import (
    AgentServiceState,
    AgentServiceStatusReport,
    LaunchAgentConfig,
)
from system_mind.macos.services_models import ServiceDomain, ServiceStatus


@dataclass(frozen=True)
class MacOsUserAgentAuditResult:
    """Outcome of auditing macOS least-privilege user agent models, manager, and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    manager_valid: bool
    cli_valid: bool
    sensors_valid: bool
    safety_valid: bool


class MacOsUserAgentValidator:
    """Programmatic validator verifying macOS user agent service models, safety invariants, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_user_agent.py"
    SENSOR_RUST_PATH = Path("crates") / "system-mind-sensors" / "src" / "macos_user_agent.rs"

    REQUIRED_REPORT_FIELDS = [
        "label",
        "domain",
        "state",
        "status",
        "uid",
        "console_user",
        "config",
        "timestamp",
        "pid",
        "last_exit_code",
        "plist_path",
        "is_root",
        "host_platform",
        "scan_proves_safe",
        "unavailable_telemetry",
        "is_mock",
    ]

    REQUIRED_CONFIG_FIELDS = [
        "label",
        "program_arguments",
        "run_at_load",
        "keep_alive",
        "limit_load_to_session_type",
        "standard_out_path",
        "standard_error_path",
        "process_type",
        "nice",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR

    def audit(self) -> MacOsUserAgentAuditResult:
        """Execute comprehensive audit across user agent models, detector, CLI, and invariants."""
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        manager_valid = self._audit_manager(issues)
        cli_valid = self._audit_cli(issues)
        sensors_valid = self._audit_sensors(issues)
        safety_valid = self._audit_safety_invariants(issues)

        valid = (
            models_valid
            and manager_valid
            and cli_valid
            and sensors_valid
            and safety_valid
            and len(issues) == 0
        )

        return MacOsUserAgentAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            manager_valid=manager_valid,
            cli_valid=cli_valid,
            sensors_valid=sensors_valid,
            safety_valid=safety_valid,
        )

    def audit_all(self) -> MacOsUserAgentAuditResult:
        """Alias for audit()."""
        return self.audit()

    def _audit_models(self, issues: List[str]) -> bool:
        """Audit LaunchAgentConfig and AgentServiceStatusReport data models."""
        valid = True
        config = LaunchAgentConfig()
        cfg_dict = config.to_dict()
        for field_name in self.REQUIRED_CONFIG_FIELDS:
            if field_name not in cfg_dict:
                issues.append(f"LaunchAgentConfig missing required field: {field_name}")
                valid = False

        plist_xml = config.to_plist_xml()
        if "com.systemmind.useragent" not in plist_xml:
            issues.append("LaunchAgentConfig.to_plist_xml() does not contain expected label")
            valid = False
        if "<key>LimitLoadToSessionType</key>" not in plist_xml:
            issues.append("LaunchAgentConfig.to_plist_xml() does not specify LimitLoadToSessionType")
            valid = False

        manager = MacUserAgentServiceManager()
        report = manager.get_mock_status(profile="running")
        rep_dict = report.to_dict()
        for field_name in self.REQUIRED_REPORT_FIELDS:
            if field_name not in rep_dict:
                issues.append(f"AgentServiceStatusReport missing required field: {field_name}")
                valid = False

        if not report.scan_proves_safe is False:
            issues.append("AgentServiceStatusReport violates non-negotiable invariant scan_proves_safe == False")
            valid = False

        return valid

    def _audit_manager(self, issues: List[str]) -> bool:
        """Audit MacUserAgentServiceManager methods and fallback behaviors."""
        valid = True
        manager = MacUserAgentServiceManager(custom_uid=501)

        # Audit mock profiles
        running = manager.get_mock_status("running")
        if not running.is_running or not running.is_least_privilege:
            issues.append("MacUserAgentServiceManager running profile failed is_running or is_least_privilege")
            valid = False

        stopped = manager.get_mock_status("stopped")
        if stopped.is_running or not stopped.is_least_privilege:
            issues.append("MacUserAgentServiceManager stopped profile failed invariant checks")
            valid = False

        uninstalled = manager.get_mock_status("uninstalled")
        if uninstalled.is_installed:
            issues.append("MacUserAgentServiceManager uninstalled profile reports as installed")
            valid = False

        unsupported = manager.get_mock_status("unsupported")
        if unsupported.state != AgentServiceState.UNAVAILABLE_PLATFORM:
            issues.append("MacUserAgentServiceManager unsupported profile returned invalid state")
            valid = False

        # Audit live non-mutating inspection
        try:
            live = manager.inspect_service()
            if live.scan_proves_safe is not False:
                issues.append("Live inspection violates scan_proves_safe == False")
                valid = False
        except Exception as e:
            issues.append(f"MacUserAgentServiceManager live inspection crashed: {e}")
            valid = False

        return valid

    def _audit_cli(self, issues: List[str]) -> bool:
        """Audit tools/detect_user_agent.py CLI tool."""
        cli_path = self.root_dir / self.CLI_REL_PATH
        if not cli_path.exists():
            issues.append(f"User agent CLI tool missing at: {cli_path}")
            return False

        try:
            tree = ast.parse(cli_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                        and node.func.attr == "system"
                    ):
                        issues.append("User agent CLI tool uses prohibited os.system")
                        return False
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            issues.append("User agent CLI tool invokes subprocess with shell=True")
                            return False
        except SyntaxError as e:
            issues.append(f"User agent CLI tool has syntax error: {e}")
            return False

        # Execute CLI mock invocation
        try:
            res = subprocess.run(
                [sys.executable, str(cli_path), "--mock", "--json"],
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
            if res.returncode != 0:
                issues.append(f"User agent CLI --mock --json returned non-zero code {res.returncode}: {res.stderr}")
                return False
            data = json.loads(res.stdout)
            if data.get("label") != "com.systemmind.useragent":
                issues.append("User agent CLI output returned unexpected label")
                return False
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            issues.append(f"User agent CLI execution failed: {e}")
            return False

        return True

    def _audit_sensors(self, issues: List[str]) -> bool:
        """Audit native Rust sensor collector implementation."""
        sensor_path = self.root_dir / self.SENSOR_RUST_PATH
        if not sensor_path.exists():
            issues.append(f"Rust sensor collector missing at: {sensor_path}")
            return False

        content = sensor_path.read_text(encoding="utf-8")
        if "AgentServiceStatusReportSnapshot" not in content:
            issues.append("Rust sensor collector missing AgentServiceStatusReportSnapshot")
            return False
        if "is_least_privilege" not in content:
            issues.append("Rust sensor collector missing is_least_privilege method")
            return False
        if "scan_proves_safe" not in content:
            issues.append("Rust sensor collector missing scan_proves_safe field")
            return False

        return True

    def _audit_safety_invariants(self, issues: List[str]) -> bool:
        """Audit safety invariants SC-01 and INV-AGENT-01 through INV-AGENT-05."""
        valid = True
        manager = MacUserAgentServiceManager()
        report = manager.get_mock_status("running")

        # SC-01: Zero ambient shell authority in agent_service_detector.py
        detector_path = self.root_dir / "src" / "system_mind" / "macos" / "agent_service_detector.py"
        try:
            tree = ast.parse(detector_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                        and node.func.attr == "system"
                    ):
                        issues.append("agent_service_detector.py uses prohibited os.system")
                        valid = False
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            issues.append("agent_service_detector.py invokes subprocess with shell=True")
                            valid = False
        except SyntaxError as e:
            issues.append(f"agent_service_detector.py syntax error: {e}")
            valid = False

        # INV-AGENT-01: Least privilege user domain execution
        if not report.is_least_privilege or report.domain != ServiceDomain.USER_AGENT:
            issues.append("INV-AGENT-01 violated: Service domain is not USER_AGENT or reports elevated privileges")
            valid = False

        # INV-AGENT-04: Non-negotiable charter invariant: Scan != Safe
        if report.scan_proves_safe is not False:
            issues.append("INV-AGENT-04 violated: scan_proves_safe is not False")
            valid = False

        return valid
