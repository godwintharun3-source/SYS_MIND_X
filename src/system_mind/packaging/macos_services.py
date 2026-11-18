"""Automated packaging validator auditing macOS launchd services and login-item telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

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


@dataclass(frozen=True)
class MacOsServicesAuditResult:
    """Outcome of auditing macOS companion agent services telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    safety_valid: bool


class MacOsServicesValidator:
    """Programmatic validator verifying macOS services data models, safety rules, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_services.py"

    REQUIRED_SERVICE_FIELDS = [
        "label",
        "pid",
        "last_exit_code",
        "domain",
        "status",
        "ownership",
        "plist_path",
        "program",
        "run_at_load",
        "keep_alive",
        "is_apple",
    ]

    REQUIRED_LOGIN_ITEM_FIELDS = [
        "name",
        "path",
        "hidden",
        "kind",
        "ownership",
        "is_apple",
    ]

    REQUIRED_REPORT_FIELDS = [
        "collection_method",
        "timestamp",
        "host_platform",
        "services",
        "login_items",
        "total_services_count",
        "running_services_count",
        "loaded_services_count",
        "system_managed_count",
        "vendor_managed_count",
        "user_managed_count",
        "total_login_items_count",
        "warnings",
        "unavailable_telemetry",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsServicesAuditResult:
        """Execute comprehensive audit over macOS services telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsServicesAuditResult:
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        detector_valid, safety_valid = self._audit_detector(issues)
        cli_valid = self._audit_cli(issues)

        valid = models_valid and detector_valid and cli_valid and safety_valid
        return MacOsServicesAuditResult(
            valid=valid,
            issues=tuple(issues),
            models_valid=models_valid,
            detector_valid=detector_valid,
            cli_valid=cli_valid,
            safety_valid=safety_valid,
        )

    def _audit_models(self, issues: List[str]) -> bool:
        passed = True
        try:
            service = MacLaunchdService(
                label="com.apple.Finder",
                pid=653,
                last_exit_code=0,
                domain=ServiceDomain.SYSTEM_AGENT,
                status=ServiceStatus.RUNNING,
                ownership=ServiceOwnership.SYSTEM_MANAGED,
                plist_path="/System/Library/LaunchAgents/com.apple.Finder.plist",
                program="/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
                run_at_load=True,
                keep_alive=True,
                is_apple=True,
            )

            for field_name in self.REQUIRED_SERVICE_FIELDS:
                if not hasattr(service, field_name):
                    issues.append(f"MacLaunchdService missing required field: {field_name}")
                    passed = False

            if not service.is_running:
                issues.append("MacLaunchdService.is_running returned False for running service")
                passed = False

            if not service.is_system_managed:
                issues.append("MacLaunchdService.is_system_managed returned False for system service")
                passed = False

            login_item = MacLoginItem(
                name="GeminiAppLauncher",
                path="/Applications/GeminiAppLauncher.app",
                hidden=False,
                kind=LoginItemKind.APPLICATION,
                ownership=ServiceOwnership.USER_MANAGED,
                is_apple=False,
            )

            for field_name in self.REQUIRED_LOGIN_ITEM_FIELDS:
                if not hasattr(login_item, field_name):
                    issues.append(f"MacLoginItem missing required field: {field_name}")
                    passed = False

            report = MacServicesReport(
                collection_method="MOCK_TEST",
                timestamp="2026-11-16T12:00:00Z",
                host_platform="macOS-Darwin",
                services=[service],
                login_items=[login_item],
                total_services_count=1,
                running_services_count=1,
                loaded_services_count=1,
                system_managed_count=1,
                vendor_managed_count=0,
                user_managed_count=0,
                total_login_items_count=1,
            )

            for field_name in self.REQUIRED_REPORT_FIELDS:
                if not hasattr(report, field_name):
                    issues.append(f"MacServicesReport missing required field: {field_name}")
                    passed = False

            if report.find_by_label("com.apple.Finder") is None:
                issues.append("MacServicesReport.find_by_label failed to locate service")
                passed = False

            if len(report.filter_by_domain(ServiceDomain.SYSTEM_AGENT)) != 1:
                issues.append("MacServicesReport.filter_by_domain failed")
                passed = False

            if len(report.filter_by_ownership(ServiceOwnership.SYSTEM_MANAGED)) != 1:
                issues.append("MacServicesReport.filter_by_ownership failed")
                passed = False

            if len(report.get_running_services()) != 1:
                issues.append("MacServicesReport.get_running_services failed")
                passed = False

        except Exception as exc:
            issues.append(f"Model validation exception: {exc}")
            passed = False

        return passed

    def _audit_detector(self, issues: List[str]) -> tuple[bool, bool]:
        detector_valid = True
        safety_valid = True

        detector = MacServicesDetector()

        # 1. Verify line parsing
        parsed = detector.parse_launchctl_line("653\t0\tcom.apple.Finder")
        if parsed != (653, 0, "com.apple.Finder"):
            issues.append(f"parse_launchctl_line returned unexpected result: {parsed}")
            detector_valid = False

        parsed_dash = detector.parse_launchctl_line("-\t0\tcom.apple.SafariHistoryServiceAgent")
        if parsed_dash != (None, 0, "com.apple.SafariHistoryServiceAgent"):
            issues.append(f"parse_launchctl_line with dash returned unexpected result: {parsed_dash}")
            detector_valid = False

        # 2. Verify ownership classifier
        apple_own = detector.classify_ownership("com.apple.Finder", ServiceDomain.SYSTEM_AGENT)
        if apple_own != ServiceOwnership.SYSTEM_MANAGED:
            issues.append(f"classify_ownership failed for Apple service: {apple_own}")
            detector_valid = False

        user_own = detector.classify_ownership("homebrew.mxcl.mysql", ServiceDomain.USER_AGENT)
        if user_own != ServiceOwnership.USER_MANAGED:
            issues.append(f"classify_ownership failed for User agent: {user_own}")
            detector_valid = False

        vendor_own = detector.classify_ownership("com.cloudflare.warp.daemon", ServiceDomain.GLOBAL_DAEMON)
        if vendor_own != ServiceOwnership.VENDOR_MANAGED:
            issues.append(f"classify_ownership failed for Vendor daemon: {vendor_own}")
            detector_valid = False

        # 3. Verify mock mode
        mock_report = detector.detect_mock()
        if mock_report.total_services_count < 5:
            issues.append("Mock report contains insufficient service count")
            detector_valid = False

        if mock_report.total_login_items_count < 1:
            issues.append("Mock report missing login items")
            detector_valid = False

        # 4. Safety invariant check
        detector_file = self.root_dir / "src" / "system_mind" / "macos" / "services_detector.py"
        if detector_file.exists():
            code = detector_file.read_text(encoding="utf-8")
            if "shell=True" in code:
                issues.append("Safety violation: shell=True found in services_detector.py (SC-01)")
                safety_valid = False

            # Check for mutating launchctl commands
            mutating_cmds = ["launchctl load", "launchctl unload", "launchctl bootout", "launchctl bootstrap", "launchctl kill", "launchctl remove"]
            for mc in mutating_cmds:
                if mc in code:
                    issues.append(f"Safety violation: mutating command '{mc}' found in services_detector.py")
                    safety_valid = False
        else:
            issues.append(f"Detector file not found at: {detector_file}")
            detector_valid = False

        return detector_valid, safety_valid

    def _audit_cli(self, issues: List[str]) -> bool:
        if not self.cli_path.exists():
            issues.append(f"CLI tool does not exist at {self.cli_path}")
            return False

        # Verify CLI execution in mock JSON mode
        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if res.returncode != 0:
                issues.append(f"CLI invocation exited with code {res.returncode}: {res.stderr}")
                return False

            payload = json.loads(res.stdout)
            for key in self.REQUIRED_REPORT_FIELDS:
                if key not in payload:
                    issues.append(f"CLI JSON output missing key: {key}")
                    return False

            if payload.get("total_services_count", 0) < 5:
                issues.append("CLI JSON output returned fewer than 5 mock services")
                return False

        except Exception as exc:
            issues.append(f"CLI audit failed with exception: {exc}")
            return False

        return True
