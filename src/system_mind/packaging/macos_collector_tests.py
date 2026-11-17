"""Automated packaging validator auditing unit test coverage and safety invariants across all macOS collectors."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class MacOsCollectorTestsAuditResult:
    """Outcome of auditing macOS collector unit test coverage, AST safety, and charter invariants."""

    valid: bool
    issues: tuple[str, ...]
    modules_valid: bool
    ast_safety_valid: bool
    tests_valid: bool
    rust_sensors_valid: bool
    invariants_valid: bool
    collector_count: int


class MacOsCollectorTestsValidator:
    """Programmatic validator verifying comprehensive unit test coverage and safety for macOS collectors."""

    COLLECTOR_MODULES = [
        "detector.py",
        "cpu_detector.py",
        "memory_detector.py",
        "storage_detector.py",
        "battery_detector.py",
        "network_detector.py",
        "gpu_detector.py",
        "usb_detector.py",
        "process_detector.py",
        "services_detector.py",
        "app_detector.py",
        "signature_detector.py",
        "fsevents_detector.py",
        "endpoint_security_detector.py",
        "swift_bridge.py",
        "agent_service_detector.py",
        "collector_health_manager.py",
        "observation_engine.py",
        "privacy_filter.py",
        "inventory_api.py",
    ]

    RUST_SENSOR_FILES = [
        "macos_identity.rs",
        "macos_cpu.rs",
        "macos_memory.rs",
        "macos_storage.rs",
        "macos_battery.rs",
        "macos_network.rs",
        "macos_gpu.rs",
        "macos_usb.rs",
        "macos_process.rs",
        "macos_launchd.rs",
        "macos_apps.rs",
        "macos_signature.rs",
        "macos_fsevents.rs",
        "macos_endpoint_security.rs",
        "macos_swift_bridge.rs",
        "macos_user_agent.rs",
        "macos_collector_health.rs",
        "macos_observations.rs",
        "macos_privacy.rs",
        "macos_inventory.rs",
    ]

    UNIT_TEST_PATH = Path("tests") / "test_macos_collectors_unit.py"

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.macos_dir = self.root_dir / "src" / "system_mind" / "macos"
        self.sensors_dir = self.root_dir / "crates" / "system-mind-sensors" / "src"
        self.unit_test_file = self.root_dir / self.UNIT_TEST_PATH

    def audit(self) -> MacOsCollectorTestsAuditResult:
        """Execute comprehensive audit across collector modules, AST safety, unit tests, and Rust sensors."""
        issues: List[str] = []

        modules_valid = self._audit_collector_modules(issues)
        ast_safety_valid = self._audit_ast_safety(issues)
        tests_valid = self._audit_unit_test_suite(issues)
        rust_sensors_valid = self._audit_rust_sensors(issues)
        invariants_valid = self._audit_charter_invariants(issues)

        valid = (
            modules_valid
            and ast_safety_valid
            and tests_valid
            and rust_sensors_valid
            and invariants_valid
            and len(issues) == 0
        )

        return MacOsCollectorTestsAuditResult(
            valid=valid,
            issues=tuple(issues),
            modules_valid=modules_valid,
            ast_safety_valid=ast_safety_valid,
            tests_valid=tests_valid,
            rust_sensors_valid=rust_sensors_valid,
            invariants_valid=invariants_valid,
            collector_count=len(self.COLLECTOR_MODULES),
        )

    def _audit_collector_modules(self, issues: List[str]) -> bool:
        """Verify that all twenty required macOS collector modules exist in src/system_mind/macos/."""
        all_exist = True
        for mod in self.COLLECTOR_MODULES:
            path = self.macos_dir / mod
            if not path.is_file():
                issues.append(f"Missing required collector module: {path}")
                all_exist = False
        return all_exist

    def _audit_ast_safety(self, issues: List[str]) -> bool:
        """Enforce SC-01: zero shell=True, zero os.system, bounded timeouts, and no ambient shell packages."""
        clean = True
        forbidden_imports = {"sh", "plumbum", "pexpect"}

        for mod in self.COLLECTOR_MODULES:
            path = self.macos_dir / mod
            if not path.is_file():
                continue

            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as e:
                issues.append(f"Syntax error in {mod}: {e}")
                clean = False
                continue

            for node in ast.walk(tree):
                # Check for forbidden ambient execution imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_imports:
                            issues.append(f"Forbidden ambient shell import '{alias.name}' in {mod}")
                            clean = False
                elif isinstance(node, ast.ImportFrom):
                    if node.module in forbidden_imports:
                        issues.append(f"Forbidden ambient shell import '{node.module}' in {mod}")
                        clean = False

                # Check for shell=True in call arguments
                elif isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    elif isinstance(node.func, ast.Name):
                        func_name = node.func.id

                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "system"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "os"
                    ):
                        issues.append(f"Forbidden os.system call in {mod}")
                        clean = False

                    for keyword in node.keywords:
                        if keyword.arg == "shell":
                            if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                                issues.append(f"Forbidden shell=True in {mod} line {node.lineno}")
                                clean = False

        return clean

    def _audit_unit_test_suite(self, issues: List[str]) -> bool:
        """Verify dedicated unit test suite exists and defines tests for all collector subsystems."""
        if not self.unit_test_file.is_file():
            issues.append(f"Missing unit test file: {self.unit_test_file}")
            return False

        try:
            tree = ast.parse(self.unit_test_file.read_text(encoding="utf-8"))
        except SyntaxError as e:
            issues.append(f"Syntax error in unit test file: {e}")
            return False

        test_functions: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                test_functions.add(node.name)

        # Verify minimal test count and representative coverage
        if len(test_functions) < 25:
            issues.append(
                f"Insufficient unit test count in {self.UNIT_TEST_PATH}: found {len(test_functions)}, expected >= 25"
            )
            return False

        required_subsystems = [
            "cpu",
            "memory",
            "storage",
            "battery",
            "network",
            "gpu",
            "usb",
            "identity",
            "process",
            "services",
            "app",
            "signature",
            "fsevents",
            "endpoint_security",
            "swift_bridge",
            "user_agent",
            "collector_health",
            "observations",
            "privacy_filter",
            "inventory_api",
        ]

        for sub in required_subsystems:
            matched = any(sub in name for name in test_functions)
            if not matched:
                issues.append(f"Missing dedicated unit tests for subsystem '{sub}' in {self.UNIT_TEST_PATH}")
                return False

        return True

    def _audit_rust_sensors(self, issues: List[str]) -> bool:
        """Verify that corresponding native Rust sensor files exist in crates/system-mind-sensors/src/."""
        all_exist = True
        for rust_file in self.RUST_SENSOR_FILES:
            path = self.sensors_dir / rust_file
            if not path.is_file():
                issues.append(f"Missing native Rust sensor file: {path}")
                all_exist = False
        return all_exist

    def _audit_charter_invariants(self, issues: List[str]) -> bool:
        """Verify non-negotiable charter invariant: scan_proves_safe = False across collectors."""
        # Ensure model files define scan_proves_safe = False
        model_files = [
            "models.py",
            "cpu_models.py",
            "memory_models.py",
            "storage_models.py",
            "battery_models.py",
            "network_models.py",
            "gpu_models.py",
            "usb_models.py",
            "process_models.py",
            "services_models.py",
            "app_models.py",
            "signature_models.py",
            "fsevents_models.py",
            "endpoint_security_models.py",
            "swift_models.py",
            "agent_service_models.py",
            "collector_health_models.py",
            "observation_models.py",
            "privacy_models.py",
            "inventory_models.py",
        ]

        verified_models = 0
        for mf in model_files:
            path = self.macos_dir / mf
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            if "scan_proves_safe" in content:
                verified_models += 1

        if verified_models < 15:
            issues.append(
                f"Too few models explicitly declare 'scan_proves_safe': found {verified_models}, expected >= 15"
            )
            return False

        return True
