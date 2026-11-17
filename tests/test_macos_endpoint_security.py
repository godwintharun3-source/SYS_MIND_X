"""Unit, contract, and safety test suite for macOS Endpoint Security feasibility and entitlement telemetry."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import pytest

from system_mind.macos.endpoint_security_detector import (
    ENDPOINT_SECURITY_ENTITLEMENT,
    MacEndpointSecurityDetector,
)
from system_mind.macos.endpoint_security_models import (
    EsActionType,
    EsClientResultCode,
    EsEntitlementCheck,
    EsEventSample,
    EsEventType,
    EsFeasibilityReport,
    EsStatus,
)
from system_mind.packaging.macos_endpoint_security import (
    MacOsEndpointSecurityAuditResult,
    MacOsEndpointSecurityValidator,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT_DIR / "tools" / "detect_endpoint_security.py"


def test_endpoint_security_models_fidelity() -> None:
    """Verify data model construction, enum mappings, dictionary conversion, and Scan!=Safe invariant."""
    assert EsClientResultCode.SUCCESS.value == 0
    assert EsClientResultCode.ERR_NOT_ENTITLED.value == 3
    assert EsClientResultCode.ERR_NOT_PRIVILEGED.value == 5

    assert EsStatus.AVAILABLE_ENTITLED.value == "AVAILABLE_ENTITLED"
    assert EsStatus.RESTRICTED_NOT_ROOT.value == "RESTRICTED_NOT_ROOT"
    assert EsStatus.RESTRICTED_MISSING_ENTITLEMENT.value == "RESTRICTED_MISSING_ENTITLEMENT"

    assert EsEventType.NOTIFY_EXEC.value == "NOTIFY_EXEC"
    assert EsEventType.AUTH_EXEC.value == "AUTH_EXEC"
    assert EsActionType.NOTIFY.value == "NOTIFY"
    assert EsActionType.AUTH.value == "AUTH"

    ent = EsEntitlementCheck(
        has_endpoint_security_entitlement=False,
        is_root=False,
        uid=501,
        sip_enabled=True,
        sip_status_raw="System Integrity Protection status: enabled.",
        tcc_full_disk_access_probable=False,
        framework_binary_present=True,
        framework_path="/System/Library/Frameworks/EndpointSecurity.framework",
        team_id=None,
        diagnostics=["Test diagnostic message"],
    )
    ent_dict = ent.to_dict()
    assert ent_dict["uid"] == 501
    assert ent_dict["entitlement_key"] == ENDPOINT_SECURITY_ENTITLEMENT
    assert ent_dict["sip_enabled"] is True

    sample = EsEventSample(
        event_id="EVT-001",
        event_type=EsEventType.NOTIFY_EXEC,
        action_type=EsActionType.NOTIFY,
        timestamp="2026-11-17T10:00:00Z",
        process_pid=1234,
        process_ppid=1,
        executable_path="/usr/bin/git",
    )
    sample_dict = sample.to_dict()
    assert sample_dict["process_pid"] == 1234
    assert sample_dict["event_type"] == "NOTIFY_EXEC"

    report = EsFeasibilityReport(
        status=EsStatus.RESTRICTED_NOT_ROOT,
        result_code=EsClientResultCode.ERR_NOT_PRIVILEGED,
        entitlement_check=ent,
        supported_event_types=[EsEventType.NOTIFY_EXEC, EsEventType.NOTIFY_OPEN],
        fallback_strategies={"filesystem": "FSEvents", "process_table": "sysctl"},
        sample_events=[sample],
        timestamp="2026-11-17T10:00:00Z",
        unavailable_telemetry=["kernel_auth_interception"],
        scan_proves_safe=False,
        is_mock=True,
    )

    # Invariant assertion
    assert report.scan_proves_safe is False
    assert report.requires_escalation is True
    assert report.is_operational is False
    assert report.has_fallback is True

    rep_dict = report.to_dict()
    assert rep_dict["status"] == "RESTRICTED_NOT_ROOT"
    assert rep_dict["result_code"] == 5
    assert rep_dict["result_code_name"] == "ERR_NOT_PRIVILEGED"
    assert rep_dict["scan_proves_safe"] is False

    json_str = report.to_json()
    parsed = json.loads(json_str)
    assert parsed["status"] == "RESTRICTED_NOT_ROOT"
    assert parsed["scan_proves_safe"] is False


def test_endpoint_security_detector_mock_restricted_companion() -> None:
    """Verify mock restricted companion profile simulates least-privilege user agent constraints."""
    detector = MacEndpointSecurityDetector()
    report = detector.detect(use_mock=True, profile="restricted_companion")

    assert report.status == EsStatus.RESTRICTED_NOT_ROOT
    assert report.result_code == EsClientResultCode.ERR_NOT_PRIVILEGED
    assert report.entitlement_check.is_root is False
    assert report.entitlement_check.has_endpoint_security_entitlement is False
    assert report.scan_proves_safe is False
    assert report.requires_escalation is True
    assert report.is_operational is False
    assert report.has_fallback is True

    # Check fallbacks
    assert "filesystem" in report.fallback_strategies
    assert "process_lifecycle" in report.fallback_strategies
    assert "Apple CoreServices FSEvents" in report.fallback_strategies["filesystem"]

    # Check unavailable telemetry documented
    assert "kernel_auth_interception" in report.unavailable_telemetry
    assert "realtime_es_event_stream" in report.unavailable_telemetry


def test_endpoint_security_detector_mock_entitled_daemon() -> None:
    """Verify mock entitled daemon profile simulates enterprise LaunchDaemon with full entitlements."""
    detector = MacEndpointSecurityDetector()
    report = detector.detect(use_mock=True, profile="entitled_daemon")

    assert report.status == EsStatus.AVAILABLE_ENTITLED
    assert report.result_code == EsClientResultCode.SUCCESS
    assert report.entitlement_check.is_root is True
    assert report.entitlement_check.has_endpoint_security_entitlement is True
    assert report.entitlement_check.team_id == "EQHXZ8M8AV"
    assert report.scan_proves_safe is False  # Invariant: even entitled daemon does not prove safety
    assert report.requires_escalation is False
    assert len(report.sample_events) == 2
    assert report.sample_events[0].process_pid == 1024
    assert report.sample_events[0].executable_path == "/usr/bin/git"


def test_endpoint_security_detector_mock_unsupported_platform() -> None:
    """Verify mock unsupported platform profile simulates non-Darwin execution."""
    detector = MacEndpointSecurityDetector()
    report = detector.detect(use_mock=True, profile="unsupported_platform")

    assert report.status == EsStatus.UNAVAILABLE_PLATFORM
    assert report.result_code == EsClientResultCode.ERR_INTERNAL
    assert report.host_platform == "Linux"
    assert report.scan_proves_safe is False
    assert "apple_endpoint_security_framework" in report.unavailable_telemetry


def test_endpoint_security_detector_live_host_inspection() -> None:
    """Verify live inspection runs safely in user space without privilege escalation or crashes."""
    detector = MacEndpointSecurityDetector()
    report = detector.detect(use_mock=False)

    assert report.scan_proves_safe is False
    assert report.is_mock is False
    assert report.timestamp is not None
    assert report.has_fallback is True

    if sys.platform == "darwin":
        assert report.host_platform == "Darwin"
        # On normal development host, user agent runs unprivileged
        assert report.status in (
            EsStatus.RESTRICTED_NOT_ROOT,
            EsStatus.RESTRICTED_MISSING_ENTITLEMENT,
            EsStatus.AVAILABLE_ENTITLED,
        )
        assert report.result_code in (
            EsClientResultCode.ERR_NOT_PRIVILEGED,
            EsClientResultCode.ERR_NOT_ENTITLED,
            EsClientResultCode.SUCCESS,
        )
    else:
        assert report.status == EsStatus.UNAVAILABLE_PLATFORM


def test_endpoint_security_inspect_entitlements_live() -> None:
    """Verify inspect_entitlements reads host state without modifying host configuration."""
    detector = MacEndpointSecurityDetector()
    ent = detector.inspect_entitlements()

    assert ent.entitlement_key == ENDPOINT_SECURITY_ENTITLEMENT
    assert ent.uid >= 0
    assert len(ent.diagnostics) >= 3
    assert isinstance(ent.sip_status_raw, str)


def test_endpoint_security_cli_mock_and_json() -> None:
    """Verify developer CLI tool supports formatted output, mock profiles, and JSON schemas."""
    assert CLI_PATH.exists()

    # 1. Test mock json output
    res = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--json"],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "RESTRICTED_NOT_ROOT"
    assert data["result_code"] == 5
    assert data["scan_proves_safe"] is False
    assert "filesystem" in data["fallback_strategies"]

    # 2. Test entitled daemon mock
    res_daemon = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--profile", "entitled_daemon", "--json"],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )
    assert res_daemon.returncode == 0
    data_daemon = json.loads(res_daemon.stdout)
    assert data_daemon["status"] == "AVAILABLE_ENTITLED"
    assert data_daemon["result_code"] == 0
    assert data_daemon["scan_proves_safe"] is False
    assert len(data_daemon["sample_events"]) == 2

    # 3. Test audit-entitlements table
    res_audit = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--audit-entitlements"],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )
    assert res_audit.returncode == 0
    assert "ENTITLEMENT & HOST SECURITY AUDIT" in res_audit.stdout
    assert "Scan != Safe" in res_audit.stdout


def test_endpoint_security_cli_live_execution() -> None:
    """Verify developer CLI tool executes cleanly against live host without sudo."""
    res = subprocess.run(
        [sys.executable, str(CLI_PATH)],
        capture_output=True,
        text=True,
        timeout=5.0,
        check=False,
    )
    assert res.returncode == 0
    assert "Endpoint Security Feasibility & Entitlement Audit" in res.stdout
    assert "Scan != Safe" in res.stdout
    assert "ACTIVE COMPANION FALLBACK STRATEGIES" in res.stdout


def test_endpoint_security_packaging_validator() -> None:
    """Verify programmatic packaging validator passes with 100% compliance across all audits."""
    validator = MacOsEndpointSecurityValidator()
    result = validator.audit_all()

    assert result.valid is True
    assert len(result.issues) == 0, f"Validator found unexpected issues: {result.issues}"
    assert result.models_valid is True
    assert result.detector_valid is True
    assert result.cli_valid is True
    assert result.safety_valid is True


def test_endpoint_security_ast_safety_and_zero_ambient_shell() -> None:
    """Verify AST safety: zero shell=True invocations and bounded timeouts on all subprocess calls."""
    files_to_scan = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "endpoint_security_models.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "endpoint_security_detector.py",
        ROOT_DIR / "src" / "system_mind" / "packaging" / "macos_endpoint_security.py",
        CLI_PATH,
    ]

    for filepath in files_to_scan:
        assert filepath.exists()
        tree = ast.parse(filepath.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "shell":
                        if isinstance(keyword.value, ast.Constant):
                            assert keyword.value.value is False, f"shell=True found in {filepath.name}:{node.lineno}"

                # Check timeout for subprocess executions
                if isinstance(node.func, ast.Attribute) and node.func.attr in ("run", "Popen", "check_output"):
                    timeout_present = any(kw.arg == "timeout" for kw in node.keywords)
                    assert timeout_present, f"subprocess call in {filepath.name}:{node.lineno} missing timeout"
