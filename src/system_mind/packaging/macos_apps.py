"""Automated packaging validator auditing macOS installed application inventory and bundle telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.core.types import ComponentOwnership
from system_mind.macos.app_detector import MacAppDetector
from system_mind.macos.app_models import (
    ApplicationCategory,
    MacAppInfo,
    MacAppInventoryReport,
)


@dataclass(frozen=True)
class MacOsAppAuditResult:
    """Outcome of auditing macOS companion agent application telemetry engine and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    safety_valid: bool


class MacOsAppValidator:
    """Programmatic validator verifying macOS application models, safety invariants, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_apps.py"

    REQUIRED_APP_FIELDS = [
        "name",
        "bundle_id",
        "bundle_path",
        "version",
        "build_version",
        "executable_name",
        "executable_path",
        "min_os_version",
        "ownership",
        "category",
        "is_apple",
        "is_user_app",
    ]

    REQUIRED_REPORT_FIELDS = [
        "collection_method",
        "timestamp",
        "host_platform",
        "applications",
        "total_applications_count",
        "system_managed_count",
        "vendor_managed_count",
        "user_managed_count",
        "warnings",
        "unavailable_telemetry",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MacOsAppAuditResult:
        """Execute comprehensive audit over macOS application inventory telemetry components."""
        instance = cls(root_dir)
        return instance._audit_internal()

    def _audit_internal(self) -> MacOsAppAuditResult:
        issues: List[str] = []

        models_valid = self._audit_models(issues)
        detector_valid, safety_valid = self._audit_detector(issues)
        cli_valid = self._audit_cli(issues)

        valid = models_valid and detector_valid and cli_valid and safety_valid
        return MacOsAppAuditResult(
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
            app = MacAppInfo(
                name="Google Chrome",
                bundle_id="com.google.Chrome",
                bundle_path="/Applications/Google Chrome.app",
                version="157.0.8103.51",
                build_version="8103.51",
                executable_name="Google Chrome",
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                min_os_version="10.15.0",
                ownership=ComponentOwnership.VENDOR_MANAGED,
                category=ApplicationCategory.WEB_BROWSER,
                is_apple=False,
                is_user_app=True,
            )

            for field_name in self.REQUIRED_APP_FIELDS:
                if not hasattr(app, field_name):
                    issues.append(f"MacAppInfo missing required field: {field_name}")
                    passed = False

            if not app.is_user_app:
                issues.append("MacAppInfo.is_user_app returned False for vendor application")
                passed = False

            report = MacAppInventoryReport(
                collection_method="MOCK_TEST",
                timestamp="2026-11-16T12:00:00Z",
                host_platform="macOS-Darwin",
                applications=[app],
                total_applications_count=1,
                system_managed_count=0,
                vendor_managed_count=1,
                user_managed_count=0,
            )

            for field_name in self.REQUIRED_REPORT_FIELDS:
                if not hasattr(report, field_name):
                    issues.append(f"MacAppInventoryReport missing required field: {field_name}")
                    passed = False

            if report.find_by_bundle_id("com.google.Chrome") is None:
                issues.append("MacAppInventoryReport.find_by_bundle_id failed")
                passed = False

            if report.find_by_name("Google Chrome") is None:
                issues.append("MacAppInventoryReport.find_by_name failed")
                passed = False

            if len(report.filter_by_ownership(ComponentOwnership.VENDOR_MANAGED)) != 1:
                issues.append("MacAppInventoryReport.filter_by_ownership failed")
                passed = False

            if len(report.filter_by_category(ApplicationCategory.WEB_BROWSER)) != 1:
                issues.append("MacAppInventoryReport.filter_by_category failed")
                passed = False

        except Exception as exc:
            issues.append(f"Model validation failure: {exc}")
            passed = False

        return passed

    def _audit_detector(self, issues: List[str]) -> tuple[bool, bool]:
        detector_valid = True
        safety_valid = True

        detector = MacAppDetector()

        # 1. Ownership and user-app immunity check
        sys_own, sys_apple, sys_user = detector.classify_ownership("com.apple.Safari", Path("/System/Applications/Safari.app"))
        if sys_own != ComponentOwnership.SYSTEM_MANAGED or not sys_apple or sys_user:
            issues.append("classify_ownership failed for system Safari")
            detector_valid = False

        vnd_own, vnd_apple, vnd_user = detector.classify_ownership("com.google.Chrome", Path("/Applications/Google Chrome.app"))
        if vnd_own != ComponentOwnership.VENDOR_MANAGED or vnd_apple or not vnd_user:
            issues.append("classify_ownership failed for vendor Chrome (must have is_user_app=True for SC-02)")
            detector_valid = False

        # 2. Category classification
        cat_browser = detector.classify_category("com.google.Chrome", "Google Chrome", Path("/Applications/Google Chrome.app"))
        if cat_browser != ApplicationCategory.WEB_BROWSER:
            issues.append(f"classify_category failed for Chrome: {cat_browser}")
            detector_valid = False

        cat_dev = detector.classify_category("com.microsoft.VSCode", "Visual Studio Code", Path("/Applications/Visual Studio Code.app"))
        if cat_dev != ApplicationCategory.DEVELOPER_TOOL:
            issues.append(f"classify_category failed for VS Code: {cat_dev}")
            detector_valid = False

        # 3. Mock mode verification
        mock_report = detector.detect_mock()
        if mock_report.total_applications_count < 5:
            issues.append("Mock report contains insufficient application count")
            detector_valid = False

        # 4. Safety invariant check
        detector_file = self.root_dir / "src" / "system_mind" / "macos" / "app_detector.py"
        if detector_file.exists():
            code = detector_file.read_text(encoding="utf-8")
            if "shell=True" in code:
                issues.append("Safety violation: shell=True found in app_detector.py (SC-01)")
                safety_valid = False

            # Mutating command check
            mutating_cmds = ["rm -rf", "shutil.rmtree", "os.remove", "bundle_path.unlink()"]
            for mc in mutating_cmds:
                if mc in code:
                    issues.append(f"Safety violation: mutating logic '{mc}' found in app_detector.py")
                    safety_valid = False
        else:
            issues.append(f"Detector file not found at: {detector_file}")
            detector_valid = False

        return detector_valid, safety_valid

    def _audit_cli(self, issues: List[str]) -> bool:
        if not self.cli_path.exists():
            issues.append(f"CLI tool does not exist at {self.cli_path}")
            return False

        try:
            cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
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

            if payload.get("total_applications_count", 0) < 5:
                issues.append("CLI JSON output returned fewer than 5 mock applications")
                return False

        except Exception as exc:
            issues.append(f"CLI audit failed with exception: {exc}")
            return False

        return True
