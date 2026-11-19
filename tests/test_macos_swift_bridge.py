"""Unit, contract, and safety test suite for macOS Swift companion bridge telemetry."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import pytest

from system_mind.macos.swift_bridge import (
    DEFAULT_SWIFT_BINARY,
    MacSwiftBridge,
)
from system_mind.macos.swift_models import (
    FrontmostAppInfo,
    SwiftBridgeTelemetry,
    SwiftPermissionStatus,
    SwiftThermalState,
)
from system_mind.packaging.macos_swift_bridge import (
    MacOsSwiftBridgeAuditResult,
    MacOsSwiftBridgeValidator,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT_DIR / "tools" / "detect_swift_bridge.py"


def test_swift_bridge_models_fidelity() -> None:
    """Verify data model construction, enum mappings, dictionary conversion, and Scan!=Safe invariant."""
    assert SwiftThermalState.NOMINAL.value == "NOMINAL"
    assert SwiftThermalState.FAIR.value == "FAIR"
    assert SwiftThermalState.SERIOUS.value == "SERIOUS"
    assert SwiftThermalState.CRITICAL.value == "CRITICAL"
    assert SwiftThermalState.UNKNOWN.value == "UNKNOWN"

    app = FrontmostAppInfo(
        name="Terminal",
        bundle_id="com.apple.Terminal",
        pid=1234,
        path="/System/Applications/Utilities/Terminal.app",
    )
    app_dict = app.to_dict()
    assert app_dict["name"] == "Terminal"
    assert app_dict["bundle_id"] == "com.apple.Terminal"
    assert app_dict["pid"] == 1234

    perms = SwiftPermissionStatus(
        accessibility_granted=True,
        screen_recording_granted=False,
        full_disk_access_granted=True,
    )
    perm_dict = perms.to_dict()
    assert perm_dict["accessibility_granted"] is True
    assert perm_dict["screen_recording_granted"] is False
    assert perm_dict["full_disk_access_granted"] is True

    telemetry = SwiftBridgeTelemetry(
        thermal_state=SwiftThermalState.NOMINAL,
        frontmost_app=app,
        permissions=perms,
        system_uptime_seconds=5432.1,
        console_user="developer",
        screen_locked=False,
        timestamp="2026-11-17T11:00:00Z",
        host_platform="Darwin",
        bridge_channel="SWIFT_NATIVE_IPC",
        scan_proves_safe=False,
        unavailable_telemetry=[],
        is_mock=True,
    )

    # Invariant assertions
    assert telemetry.scan_proves_safe is False
    assert telemetry.is_throttled is False
    assert telemetry.is_operational is False  # is_mock is True

    tel_dict = telemetry.to_dict()
    assert tel_dict["thermal_state"] == "NOMINAL"
    assert tel_dict["system_uptime_seconds"] == 5432.1
    assert tel_dict["scan_proves_safe"] is False

    json_str = telemetry.to_json()
    parsed = json.loads(json_str)
    assert parsed["thermal_state"] == "NOMINAL"
    assert parsed["scan_proves_safe"] is False


def test_swift_bridge_mock_nominal() -> None:
    """Verify mock nominal profile simulates normal thermal and execution conditions."""
    bridge = MacSwiftBridge()
    telemetry = bridge.collect(use_mock=True, profile="nominal")

    assert telemetry.thermal_state == SwiftThermalState.NOMINAL
    assert telemetry.is_throttled is False
    assert telemetry.scan_proves_safe is False
    assert telemetry.frontmost_app is not None
    assert telemetry.frontmost_app.bundle_id == "com.apple.Terminal"
    assert telemetry.console_user == "developer"
    assert telemetry.bridge_channel == "MOCK_NOMINAL"


def test_swift_bridge_mock_throttled() -> None:
    """Verify mock throttled profile simulates critical thermal load and active GUI task."""
    bridge = MacSwiftBridge()
    telemetry = bridge.collect(use_mock=True, profile="throttled")

    assert telemetry.thermal_state == SwiftThermalState.CRITICAL
    assert telemetry.is_throttled is True
    assert telemetry.scan_proves_safe is False
    assert telemetry.frontmost_app is not None
    assert telemetry.frontmost_app.name == "Final Cut Pro"
    assert telemetry.console_user == "operator"
    assert telemetry.bridge_channel == "MOCK_THROTTLED"


def test_swift_bridge_mock_unsupported() -> None:
    """Verify mock unsupported profile simulates non-Darwin host execution."""
    bridge = MacSwiftBridge()
    telemetry = bridge.collect(use_mock=True, profile="unsupported")

    assert telemetry.thermal_state == SwiftThermalState.UNKNOWN
    assert telemetry.host_platform == "Linux"
    assert telemetry.scan_proves_safe is False
    assert telemetry.bridge_channel == "UNSUPPORTED_PLATFORM"
    assert "apple_frameworks_unsupported" in telemetry.unavailable_telemetry


def test_swift_bridge_live_collection_on_darwin() -> None:
    """Verify live bridge executes against compiled companion binary or degrades cleanly."""
    bridge = MacSwiftBridge()
    telemetry = bridge.collect(use_mock=False)

    assert telemetry.scan_proves_safe is False
    assert telemetry.timestamp is not None

    if sys.platform == "darwin":
        assert telemetry.host_platform == "Darwin"
        assert telemetry.thermal_state in (
            SwiftThermalState.NOMINAL,
            SwiftThermalState.FAIR,
            SwiftThermalState.SERIOUS,
            SwiftThermalState.CRITICAL,
            SwiftThermalState.UNKNOWN,
        )
    else:
        assert telemetry.host_platform != "Darwin"


def test_swift_bridge_missing_binary_graceful_fallback(tmp_path: Path) -> None:
    """Verify bridge gracefully handles missing companion binary without crashing."""
    fake_path = tmp_path / "nonexistent_companion"
    bridge = MacSwiftBridge(binary_path=fake_path)

    assert bridge.is_binary_available() is False
    telemetry = bridge.collect(use_mock=False)

    assert telemetry.scan_proves_safe is False
    assert telemetry.is_mock is True
    assert "native_swift_binary_missing" in telemetry.unavailable_telemetry


def test_swift_bridge_cli_mock_and_json() -> None:
    """Verify developer CLI tool supports formatted output, mock profiles, and JSON schemas."""
    assert CLI_PATH.exists()

    # 1. Test mock json output
    res = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--json"],
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["thermal_state"] == "NOMINAL"
    assert data["scan_proves_safe"] is False
    assert data["bridge_channel"] == "MOCK_NOMINAL"

    # 2. Test throttled mock json output
    res_thr = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--profile", "throttled", "--json"],
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    assert res_thr.returncode == 0
    data_thr = json.loads(res_thr.stdout)
    assert data_thr["thermal_state"] == "CRITICAL"
    assert data_thr["is_throttled"] is True
    assert data_thr["scan_proves_safe"] is False

    # 3. Test tabular output
    res_table = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock"],
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    assert res_table.returncode == 0
    assert "Swift Native Companion Bridge Telemetry" in res_table.stdout
    assert "Scan != Safe" in res_table.stdout


def test_swift_bridge_cli_live_execution() -> None:
    """Verify developer CLI tool executes cleanly against live host without sudo."""
    res = subprocess.run(
        [sys.executable, str(CLI_PATH)],
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    assert res.returncode == 0
    assert "Swift Native Companion Bridge Telemetry" in res.stdout
    assert "Scan != Safe" in res.stdout


def test_swift_companion_swift_sources() -> None:
    """Verify presence and validity of Swift package sources."""
    pkg_dir = ROOT_DIR / "apps" / "macos-companion"
    assert (pkg_dir / "Package.swift").exists()
    assert (pkg_dir / "Sources" / "SystemMindCompanion" / "BridgeModels.swift").exists()
    assert (pkg_dir / "Sources" / "SystemMindCompanion" / "TelemetryCollector.swift").exists()
    assert (pkg_dir / "Sources" / "SystemMindCompanion" / "main.swift").exists()


def test_swift_bridge_packaging_validator() -> None:
    """Verify programmatic packaging validator passes with 100% compliance across all audits."""
    validator = MacOsSwiftBridgeValidator()
    result = validator.audit_all()

    assert result.valid is True
    assert len(result.issues) == 0, f"Validator found unexpected issues: {result.issues}"
    assert result.models_valid is True
    assert result.bridge_valid is True
    assert result.cli_valid is True
    assert result.swift_sources_valid is True
    assert result.safety_valid is True


def test_swift_bridge_ast_safety_and_zero_ambient_shell() -> None:
    """Verify AST safety: zero shell=True invocations and bounded timeouts on all subprocess calls."""
    files_to_scan = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "swift_models.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "swift_bridge.py",
        ROOT_DIR / "src" / "system_mind" / "packaging" / "macos_swift_bridge.py",
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
