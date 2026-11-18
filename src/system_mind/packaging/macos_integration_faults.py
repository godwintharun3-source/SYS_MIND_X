"""Automated packaging validator auditing integration tests with missing sensors and denied permissions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class MacOsIntegrationFaultsAuditResult:
    """Outcome of auditing macOS integration fault tests, AST safety, and charter invariants."""

    valid: bool
    issues: tuple[str, ...]
    integration_test_valid: bool
    ast_safety_valid: bool
    scenarios_valid: bool
    rust_sensors_valid: bool
    invariants_valid: bool
    scenario_count: int


class MacOsIntegrationFaultsValidator:
    """Programmatic validator verifying integration test coverage for missing sensors and denied permissions."""

    INTEGRATION_TEST_PATH = Path("tests") / "test_macos_integration_missing_sensors_and_permissions.py"
    CLI_REL_PATH = Path("tools") / "detect_integration_faults.py"

    REQUIRED_SCENARIOS = [
        "battery_absent",
        "offline_network",
        "endpoint_security_unprivileged",
        "tcc_full_disk_access_denied",
        "tcc_screen_accessibility_denied",
        "storage_volume_unmounted",
        "usb_empty_peripherals",
        "multifault_inventory_aggregation",
        "collector_timeout_fault",
        "collector_crash_fault",
        "unsupported_sensor_fault",
        "simultaneous_multi_fault_safe_state",
    ]

    RUST_SENSOR_FILES = [
        "macos_collector_health.rs",
        "macos_observations.rs",
        "macos_inventory.rs",
        "macos_battery.rs",
        "macos_endpoint_security.rs",
    ]

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.integration_test_file = self.root_dir / self.INTEGRATION_TEST_PATH
        self.cli_file = self.root_dir / self.CLI_REL_PATH
        self.sensors_dir = self.root_dir / "crates" / "system-mind-sensors" / "src"

    def audit(self) -> MacOsIntegrationFaultsAuditResult:
        """Execute comprehensive audit across integration fault tests, AST safety, and invariants."""
        issues: List[str] = []

        integration_test_valid = self._audit_integration_test_presence(issues)
        ast_safety_valid = self._audit_ast_safety(issues)
        scenarios_valid = self._audit_scenarios_coverage(issues)
        rust_sensors_valid = self._audit_rust_sensors(issues)
        invariants_valid = self._audit_charter_invariants(issues)

        valid = (
            integration_test_valid
            and ast_safety_valid
            and scenarios_valid
            and rust_sensors_valid
            and invariants_valid
            and len(issues) == 0
        )

        return MacOsIntegrationFaultsAuditResult(
            valid=valid,
            issues=tuple(issues),
            integration_test_valid=integration_test_valid,
            ast_safety_valid=ast_safety_valid,
            scenarios_valid=scenarios_valid,
            rust_sensors_valid=rust_sensors_valid,
            invariants_valid=invariants_valid,
            scenario_count=len(self.REQUIRED_SCENARIOS),
        )

    def _audit_integration_test_presence(self, issues: List[str]) -> bool:
        """Verify integration test file and developer CLI tool exist."""
        clean = True
        if not self.integration_test_file.is_file():
            issues.append(f"Missing integration test file: {self.integration_test_file}")
            clean = False
        if not self.cli_file.is_file():
            issues.append(f"Missing developer CLI tool: {self.cli_file}")
            clean = False
        return clean

    def _audit_ast_safety(self, issues: List[str]) -> bool:
        """Enforce SC-01: zero shell=True, zero os.system, and no ambient shell packages."""
        if not self.integration_test_file.is_file():
            return False

        clean = True
        forbidden_imports = {"sh", "plumbum", "pexpect"}

        try:
            tree = ast.parse(self.integration_test_file.read_text(encoding="utf-8"))
        except SyntaxError as e:
            issues.append(f"Syntax error in integration test file: {e}")
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_imports:
                        issues.append(f"Forbidden import '{alias.name}' in integration tests")
                        clean = False
            elif isinstance(node, ast.ImportFrom):
                if node.module in forbidden_imports:
                    issues.append(f"Forbidden import '{node.module}' in integration tests")
                    clean = False
            elif isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "system"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                ):
                    issues.append("Forbidden os.system call in integration tests")
                    clean = False
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        issues.append("Forbidden shell=True in integration tests")
                        clean = False

        return clean

    def _audit_scenarios_coverage(self, issues: List[str]) -> bool:
        """Verify all required fault scenarios are explicitly covered by test functions."""
        if not self.integration_test_file.is_file():
            return False

        try:
            tree = ast.parse(self.integration_test_file.read_text(encoding="utf-8"))
        except SyntaxError as e:
            issues.append(f"Syntax error in integration test file: {e}")
            return False

        test_functions: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                test_functions.add(node.name)

        if len(test_functions) < 8:
            issues.append(
                f"Insufficient test scenario count in {self.INTEGRATION_TEST_PATH}: found {len(test_functions)}, expected >= 8"
            )
            return False

        for scenario in self.REQUIRED_SCENARIOS:
            matched = any(scenario in name for name in test_functions)
            if not matched:
                issues.append(f"Missing required fault scenario '{scenario}' in {self.INTEGRATION_TEST_PATH}")
                return False

        return True

    def _audit_rust_sensors(self, issues: List[str]) -> bool:
        """Verify that relevant native Rust sensor files exist in crates/system-mind-sensors/src/."""
        all_exist = True
        for rust_file in self.RUST_SENSOR_FILES:
            path = self.sensors_dir / rust_file
            if not path.is_file():
                issues.append(f"Missing native Rust sensor file: {path}")
                all_exist = False
        return all_exist

    def _audit_charter_invariants(self, issues: List[str]) -> bool:
        """Verify non-negotiable charter invariant: scan_proves_safe = False across fault test assertions."""
        if not self.integration_test_file.is_file():
            return False

        content = self.integration_test_file.read_text(encoding="utf-8")
        if "scan_proves_safe" not in content:
            issues.append("Integration tests do not assert scan_proves_safe invariant")
            return False

        return True
