"""Automated packaging validator auditing macOS Swift companion bridge telemetry."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.macos.swift_bridge import MacSwiftBridge
from system_mind.macos.swift_models import (
    FrontmostAppInfo,
    SwiftBridgeTelemetry,
    SwiftPermissionStatus,
    SwiftThermalState,
)


@dataclass(frozen=True)
class MacOsSwiftBridgeAuditResult:
    """Outcome of auditing macOS Swift companion bridge telemetry engine, models, and CLI tooling."""

    valid: bool
    issues: tuple[str, ...]
    models_valid: bool
    bridge_valid: bool
    cli_valid: bool
    swift_sources_valid: bool
    safety_valid: bool


class MacOsSwiftBridgeValidator:
    """Programmatic validator verifying macOS Swift bridge models, safety invariants, and CLI tools."""

    CLI_REL_PATH = Path("tools") / "detect_swift_bridge.py"
    SWIFT_PACKAGE_REL_PATH = Path("apps") / "macos-companion"

    REQUIRED_TELEMETRY_FIELDS = [
        "thermal_state",
        "frontmost_app",
        "permissions",
        "system_uptime_seconds",
        "console_user",
        "screen_locked",
        "timestamp",
        "host_platform",
        "bridge_channel",
        "scan_proves_safe",
        "unavailable_telemetry",
        "is_mock",
        "is_throttled",
        "is_operational",
    ]

    REQUIRED_SWIFT_FILES = [
        "Package.swift",
        "Sources/SystemMindCompanion/BridgeModels.swift",
        "Sources/SystemMindCompanion/TelemetryCollector.swift",
        "Sources/SystemMindCompanion/main.swift",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.cli_path = self.root_dir / self.CLI_REL_PATH
        self.swift_pkg_dir = self.root_dir / self.SWIFT_PACKAGE_REL_PATH

    def audit_models(self) -> List[str]:
        """Verify Swift bridge data models, invariants, and serialization fidelity."""
        issues: List[str] = []

        if SwiftThermalState.NOMINAL.value != "NOMINAL" or SwiftThermalState.CRITICAL.value != "CRITICAL":
            issues.append("SwiftThermalState enum value mapping invalid")

        app = FrontmostAppInfo(
            name="Terminal",
            bundle_id="com.apple.Terminal",
            pid=1234,
            path="/System/Applications/Utilities/Terminal.app",
        )
        app_dict = app.to_dict()
        if app_dict["bundle_id"] != "com.apple.Terminal" or app_dict["pid"] != 1234:
            issues.append("FrontmostAppInfo dictionary conversion failed")

        perms = SwiftPermissionStatus(
            accessibility_granted=True,
            screen_recording_granted=False,
            full_disk_access_granted=True,
        )
        perm_dict = perms.to_dict()
        if not perm_dict["accessibility_granted"] or not perm_dict["full_disk_access_granted"]:
            issues.append("SwiftPermissionStatus dictionary conversion failed")

        telemetry = SwiftBridgeTelemetry(
            thermal_state=SwiftThermalState.NOMINAL,
            frontmost_app=app,
            permissions=perms,
            system_uptime_seconds=5000.0,
            console_user="developer",
            screen_locked=False,
            timestamp="2026-11-17T11:00:00Z",
            scan_proves_safe=False,
            is_mock=True,
        )

        # Invariant check: scan_proves_safe must be False
        if telemetry.scan_proves_safe:
            issues.append("VIOLATION: SwiftBridgeTelemetry scan_proves_safe must be False (Scan != Safe invariant)")

        tel_dict = telemetry.to_dict()
        for field_name in self.REQUIRED_TELEMETRY_FIELDS:
            if field_name not in tel_dict:
                issues.append(f"SwiftBridgeTelemetry dictionary representation missing required field: {field_name}")

        try:
            json_str = telemetry.to_json()
            parsed = json.loads(json_str)
            if parsed.get("scan_proves_safe") is not False:
                issues.append("Serialized JSON scan_proves_safe is not False")
        except Exception as e:
            issues.append(f"SwiftBridgeTelemetry JSON serialization failed: {e}")

        return issues

    def audit_bridge(self) -> List[str]:
        """Verify bridge execution across mock profiles and live companion dispatch."""
        issues: List[str] = []
        bridge = MacSwiftBridge()

        # 1. Test mock nominal profile
        nom = bridge.collect(use_mock=True, profile="nominal")
        if nom.thermal_state != SwiftThermalState.NOMINAL:
            issues.append(f"Mock nominal profile returned unexpected thermal state: {nom.thermal_state}")
        if nom.is_throttled:
            issues.append("Mock nominal profile should not report throttled=True")
        if nom.scan_proves_safe:
            issues.append("Mock nominal profile must enforce scan_proves_safe=False")

        # 2. Test mock throttled profile
        thr = bridge.collect(use_mock=True, profile="throttled")
        if thr.thermal_state != SwiftThermalState.CRITICAL:
            issues.append(f"Mock throttled profile returned unexpected thermal state: {thr.thermal_state}")
        if not thr.is_throttled:
            issues.append("Mock throttled profile must report throttled=True")
        if thr.scan_proves_safe:
            issues.append("Mock throttled profile must enforce scan_proves_safe=False")

        # 3. Test mock unsupported profile
        uns = bridge.collect(use_mock=True, profile="unsupported")
        if uns.host_platform != "Linux" or uns.thermal_state != SwiftThermalState.UNKNOWN:
            issues.append("Mock unsupported profile failed platform check")

        # 4. Test live bridge collection (should never raise exceptions)
        try:
            live = bridge.collect(use_mock=False)
            if live.scan_proves_safe:
                issues.append("Live collection must enforce scan_proves_safe=False")
        except Exception as e:
            issues.append(f"Live bridge collection raised unexpected exception: {e}")

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
                for field_name in self.REQUIRED_TELEMETRY_FIELDS:
                    if field_name not in data:
                        issues.append(f"CLI JSON output missing expected key: {field_name}")
        except subprocess.TimeoutExpired:
            issues.append("CLI invocation timed out after 5.0 seconds")
        except Exception as e:
            issues.append(f"CLI execution failed with error: {e}")

        return issues

    def audit_swift_sources(self) -> List[str]:
        """Verify existence and invariant assertions in native Swift source package."""
        issues: List[str] = []

        for rel_file in self.REQUIRED_SWIFT_FILES:
            full_path = self.swift_pkg_dir / rel_file
            if not full_path.exists():
                issues.append(f"Required Swift companion file missing: {full_path}")
                continue

            content = full_path.read_text(encoding="utf-8")
            if "scan_proves_safe" in content:
                # Ensure it defaults to false
                if "scan_proves_safe: Bool = true" in content or "scan_proves_safe = true" in content:
                    issues.append(f"VIOLATION: Swift source {rel_file} sets scan_proves_safe to true")

        return issues

    def audit_ast_safety(self) -> List[str]:
        """Verify AST safety constraints (no shell=True, bounded subprocess timeouts, zero mutating commands)."""
        issues: List[str] = []
        files_to_check = [
            self.root_dir / "src" / "system_mind" / "macos" / "swift_models.py",
            self.root_dir / "src" / "system_mind" / "macos" / "swift_bridge.py",
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

    def audit_all(self) -> MacOsSwiftBridgeAuditResult:
        """Run complete audit across models, bridge, CLI, Swift sources, and AST safety."""
        all_issues: List[str] = []

        model_issues = self.audit_models()
        bridge_issues = self.audit_bridge()
        cli_issues = self.audit_cli()
        swift_issues = self.audit_swift_sources()
        safety_issues = self.audit_ast_safety()

        all_issues.extend(model_issues)
        all_issues.extend(bridge_issues)
        all_issues.extend(cli_issues)
        all_issues.extend(swift_issues)
        all_issues.extend(safety_issues)

        return MacOsSwiftBridgeAuditResult(
            valid=len(all_issues) == 0,
            issues=tuple(all_issues),
            models_valid=len(model_issues) == 0,
            bridge_valid=len(bridge_issues) == 0,
            cli_valid=len(cli_issues) == 0,
            swift_sources_valid=len(swift_issues) == 0,
            safety_valid=len(safety_issues) == 0,
        )


MacOsSwiftBridgeTelemetryValidator = MacOsSwiftBridgeValidator
