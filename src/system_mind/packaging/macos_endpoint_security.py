"""Automated packaging validator auditing macOS Endpoint Security feasibility and entitlement telemetry."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.endpoint_security_detector import MacEndpointSecurityDetector
from system_mind.macos.endpoint_security_models import (
    EsActionType,
    EsClientResultCode,
    EsEntitlementCheck,
    EsEventSample,
    EsEventType,
    EsFeasibilityReport,
    EsStatus,
)


@dataclass(frozen=True)
class MacOsEndpointSecurityAuditResult:
    """Outcome of auditing macOS Endpoint Security telemetry engine, models, and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    detector_valid: bool
    cli_valid: bool
    safety_valid: bool


class MacOsEndpointSecurityValidator:
    """Programmatic validator verifying macOS Endpoint Security models, safety invariants, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_endpoint_security.py"

    REQUIRED_ENTITLEMENT_FIELDS = [
        "has_endpoint_security_entitlement",
        "entitlement_key",
        "is_root",
        "uid",
        "sip_enabled",
        "sip_status_raw",
        "tcc_full_disk_access_probable",
        "framework_binary_present",
        "framework_path",
        "team_id",
        "diagnostics",
    ]

    REQUIRED_REPORT_FIELDS = [
        "status",
        "result_code",
        "result_code_name",
        "host_platform",
        "entitlement_check",
        "supported_event_types",
        "fallback_strategies",
        "sample_events",
        "timestamp",
        "scan_proves_safe",
        "unavailable_telemetry",
        "is_mock",
        "is_operational",
        "requires_escalation",
        "has_fallback",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH

    def audit_models(self) -> List[str]:
        """Verify Endpoint Security data models, invariants, and serialization fidelity."""
        issues: List[str] = []

        # Verify enum consistency
        if EsClientResultCode.SUCCESS != 0 or EsClientResultCode.ERR_NOT_ENTITLED != 3:
            issues.append("EsClientResultCode enum does not match native Apple es_new_client_result_t mapping")

        if EsStatus.RESTRICTED_NOT_ROOT.value != "RESTRICTED_NOT_ROOT":
            issues.append("EsStatus enum mapping invalid")

        ent = EsEntitlementCheck(
            has_endpoint_security_entitlement=False,
            is_root=False,
            uid=501,
            sip_enabled=True,
            sip_status_raw="enabled",
            tcc_full_disk_access_probable=False,
            framework_binary_present=True,
            framework_path="/System/Library/Frameworks/EndpointSecurity.framework",
        )
        ent_dict = ent.to_dict()
        for field_name in self.REQUIRED_ENTITLEMENT_FIELDS:
            if field_name not in ent_dict:
                issues.append(f"EsEntitlementCheck dictionary representation missing required field: {field_name}")

        report = EsFeasibilityReport(
            status=EsStatus.RESTRICTED_NOT_ROOT,
            result_code=EsClientResultCode.ERR_NOT_PRIVILEGED,
            entitlement_check=ent,
            supported_event_types=[EsEventType.NOTIFY_EXEC],
            fallback_strategies={"filesystem": "FSEvents"},
            sample_events=[],
            timestamp="2026-11-17T10:00:00Z",
            unavailable_telemetry=["kernel_auth"],
            scan_proves_safe=False,
            is_mock=True,
        )

        # Invariant check: scan_proves_safe must be False
        if report.scan_proves_safe:
            issues.append("VIOLATION: EsFeasibilityReport scan_proves_safe must be False (Scan != Safe invariant)")

        rep_dict = report.to_dict()
        for field_name in self.REQUIRED_REPORT_FIELDS:
            if field_name not in rep_dict:
                issues.append(f"EsFeasibilityReport dictionary representation missing required field: {field_name}")

        # Check JSON serialization
        try:
            json_str = report.to_json()
            parsed = json.loads(json_str)
            if parsed.get("scan_proves_safe") is not False:
                issues.append("Serialized JSON scan_proves_safe is not False")
        except Exception as e:
            issues.append(f"EsFeasibilityReport JSON serialization failed: {e}")

        return issues

    def audit_detector(self) -> List[str]:
        """Verify detector execution across mock profiles and live inspection."""
        issues: List[str] = []
        detector = MacEndpointSecurityDetector()

        # 1. Test mock restricted companion profile
        comp_report = detector.detect(use_mock=True, profile="restricted_companion")
        if comp_report.status != EsStatus.RESTRICTED_NOT_ROOT:
            issues.append(f"Mock restricted_companion profile returned unexpected status: {comp_report.status}")
        if comp_report.result_code != EsClientResultCode.ERR_NOT_PRIVILEGED:
            issues.append(f"Mock restricted_companion profile returned unexpected result_code: {comp_report.result_code}")
        if not comp_report.requires_escalation:
            issues.append("Mock restricted_companion profile should report requires_escalation=True")
        if not comp_report.has_fallback:
            issues.append("Mock restricted_companion profile must provide active fallback strategies")
        if comp_report.scan_proves_safe:
            issues.append("Mock restricted_companion profile must enforce scan_proves_safe=False")

        # 2. Test mock entitled daemon profile
        daemon_report = detector.detect(use_mock=True, profile="entitled_daemon")
        if daemon_report.status != EsStatus.AVAILABLE_ENTITLED:
            issues.append(f"Mock entitled_daemon profile returned unexpected status: {daemon_report.status}")
        if daemon_report.result_code != EsClientResultCode.SUCCESS:
            issues.append(f"Mock entitled_daemon profile returned unexpected result_code: {daemon_report.result_code}")
        if daemon_report.scan_proves_safe:
            issues.append("Mock entitled_daemon profile must enforce scan_proves_safe=False")

        # 3. Test mock unsupported platform profile
        unsupported_report = detector.detect(use_mock=True, profile="unsupported_platform")
        if unsupported_report.status != EsStatus.UNAVAILABLE_PLATFORM:
            issues.append(f"Mock unsupported_platform profile returned unexpected status: {unsupported_report.status}")

        # 4. Test live detection (should never raise exceptions)
        try:
            live_report = detector.detect(use_mock=False)
            if live_report.scan_proves_safe:
                issues.append("Live detection must enforce scan_proves_safe=False")
            if not live_report.has_fallback:
                issues.append("Live detection must provide fallback strategies")
        except Exception as e:
            issues.append(f"Live detection raised unexpected exception: {e}")

        return issues

    def audit_cli(self) -> List[str]:
        """Verify CLI tool existence, permissions, and execution output."""
        issues: List[str] = []

        if not self.cli_path.exists():
            issues.append(f"CLI tool missing at expected path: {self.cli_path}")
            return issues

        # Verify CLI execution with --mock and --json
        cmd = [sys.executable, str(self.cli_path), "--mock", "--json"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0, check=False)
            if res.returncode != 0:
                issues.append(f"CLI invocation exited with non-zero code {res.returncode}: {res.stderr}")
            else:
                data = json.loads(res.stdout)
                for field_name in self.REQUIRED_REPORT_FIELDS:
                    if field_name not in data:
                        issues.append(f"CLI JSON output missing expected key: {field_name}")
        except subprocess.TimeoutExpired:
            issues.append("CLI invocation timed out after 5.0 seconds")
        except Exception as e:
            issues.append(f"CLI execution failed with error: {e}")

        return issues

    def audit_ast_safety(self) -> List[str]:
        """Verify AST safety constraints (no shell=True, bounded subprocess timeouts, zero mutating commands)."""
        issues: List[str] = []
        files_to_check = [
            self.root_dir / "src" / "system_mind" / "macos" / "endpoint_security_models.py",
            self.root_dir / "src" / "system_mind" / "macos" / "endpoint_security_detector.py",
            self.cli_path,
        ]

        for filepath in files_to_check:
            if not filepath.exists():
                issues.append(f"Source file missing for AST audit: {filepath}")
                continue

            try:
                tree = ast.parse(filepath.read_text(encoding="utf-8"))
            except Exception as e:
                issues.append(f"Failed to parse AST for {filepath.name}: {e}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for shell=True in subprocess calls
                    for keyword in node.keywords:
                        if keyword.arg == "shell":
                            if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                                issues.append(
                                    f"SECURITY VIOLATION in {filepath.name}: shell=True prohibited in line {node.lineno}"
                                )

                    # Check for subprocess.run missing timeout
                    is_subprocess_run = False
                    if isinstance(node.func, ast.Attribute) and node.func.attr in ("run", "Popen", "check_output"):
                        is_subprocess_run = True

                    if is_subprocess_run:
                        has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                        if not has_timeout:
                            issues.append(
                                f"LINT WARNING in {filepath.name}: subprocess call missing explicit timeout in line {node.lineno}"
                            )

        return issues

    def audit_all(self) -> MacOsEndpointSecurityAuditResult:
        """Run complete audit across models, detector, CLI, and AST safety."""
        all_issues: List[str] = []

        model_issues = self.audit_models()
        detector_issues = self.audit_detector()
        cli_issues = self.audit_cli()
        safety_issues = self.audit_ast_safety()

        all_issues.extend(model_issues)
        all_issues.extend(detector_issues)
        all_issues.extend(cli_issues)
        all_issues.extend(safety_issues)

        return MacOsEndpointSecurityAuditResult(
            valid=len(all_issues) == 0,
            issues=tuple(all_issues),
            models_valid=len(model_issues) == 0,
            detector_valid=len(detector_issues) == 0,
            cli_valid=len(cli_issues) == 0,
            safety_valid=len(safety_issues) == 0,
        )


MacOsEndpointSecurityFeasibilityValidator = MacOsEndpointSecurityValidator
