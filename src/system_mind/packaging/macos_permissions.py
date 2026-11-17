"""Automated packaging validator auditing macOS permission prompts, documentation, and entitlements."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class MacOsPermissionsAuditResult:
    """Outcome of auditing macOS permission documentation, test coverage, AST safety, and charter invariants."""

    valid: bool
    issues: tuple[str, ...]
    doc_valid: bool
    test_suite_valid: bool
    cli_valid: bool
    ast_safety_valid: bool
    scenarios_valid: bool
    rust_sensors_valid: bool
    invariants_valid: bool
    non_goals_valid: bool
    scenario_count: int


class MacOsPermissionsValidator:
    """Programmatic validator verifying documentation and implementation of macOS permissions and entitlements."""

    DOC_REL_PATH = Path("docs") / "MACOS_PERMISSIONS_AND_ENTITLEMENTS.md"
    TEST_REL_PATH = Path("tests") / "test_macos_permissions_and_entitlements.py"
    CLI_REL_PATH = Path("tools") / "detect_permissions.py"

    REQUIRED_SCENARIOS = [
        "FULL_DISK_ACCESS",
        "SCREEN_RECORDING",
        "ACCESSIBILITY",
        "DOCUMENTS_FOLDER",
        "DOWNLOADS_FOLDER",
        "DESKTOP_FOLDER",
        "INPUT_MONITORING",
        "ENDPOINT_SECURITY",
    ]

    RUST_SENSOR_FILE = "macos_permissions.rs"

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or ROOT_DIR
        self.doc_file = self.root_dir / self.DOC_REL_PATH
        self.test_file = self.root_dir / self.TEST_REL_PATH
        self.cli_file = self.root_dir / self.CLI_REL_PATH
        self.sensors_dir = self.root_dir / "crates" / "system-mind-sensors" / "src"

    def audit(self) -> MacOsPermissionsAuditResult:
        """Execute comprehensive audit across permissions documentation, tests, AST safety, and invariants."""
        issues: List[str] = []

        # 1. Verify canonical documentation presence and completeness
        doc_valid = False
        if not self.doc_file.exists():
            issues.append(f"Missing permissions documentation file: {self.DOC_REL_PATH}")
        else:
            try:
                doc_text = self.doc_file.read_text(encoding="utf-8")
                required_doc_markers = [
                    "Full Disk Access",
                    "kTCCServiceScreenCapture",
                    "kTCCServiceAccessibility",
                    "kTCCServiceListenEvent",
                    "Privacy Preferences Policy Control",
                    "Scan != Safe",
                ]
                missing_markers = [m for m in required_doc_markers if m not in doc_text]
                if missing_markers:
                    issues.append(f"Documentation missing key sections: {missing_markers}")
                else:
                    doc_valid = True
            except Exception as e:
                issues.append(f"Failed to read documentation file: {e}")

        # 2. Verify test suite presence
        test_suite_valid = False
        if not self.test_file.exists():
            issues.append(f"Missing permissions test suite: {self.TEST_REL_PATH}")
        else:
            test_suite_valid = True

        # 3. Verify developer CLI presence
        cli_valid = False
        if not self.cli_file.exists():
            issues.append(f"Missing developer CLI tool: {self.CLI_REL_PATH}")
        else:
            cli_valid = True

        # 4. AST safety check (zero shell=True, zero os.system across implementation and tests)
        ast_safety_valid = True
        target_python_files = [
            self.root_dir / "src" / "system_mind" / "macos" / "permission_inspector.py",
            self.root_dir / "src" / "system_mind" / "macos" / "permission_models.py",
            self.test_file,
        ]

        for py_file in target_python_files:
            if not py_file.exists():
                issues.append(f"File missing for AST safety check: {py_file.name}")
                ast_safety_valid = False
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr == "system"
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                        ):
                            issues.append(f"Forbidden os.system in {py_file.name}:{node.lineno}")
                            ast_safety_valid = False

                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(f"Forbidden shell=True in {py_file.name}:{node.lineno}")
                                ast_safety_valid = False
            except Exception as e:
                issues.append(f"Failed to parse AST for {py_file.name}: {e}")
                ast_safety_valid = False

        # 5. Verify all required permission scenarios are covered in inspector & tests
        scenarios_valid = True
        scenario_count = 0
        try:
            from system_mind.macos.permission_inspector import MacOsPermissionInspector
            from system_mind.macos.permission_models import MacPermissionType

            inspector = MacOsPermissionInspector()
            present_types = {p.permission_type.value for p in inspector.CANONICAL_PERMISSIONS}

            for sc in self.REQUIRED_SCENARIOS:
                if sc not in present_types:
                    issues.append(f"Missing canonical permission scenario: {sc}")
                    scenarios_valid = False
                else:
                    scenario_count += 1
        except Exception as e:
            issues.append(f"Failed to import and inspect permissions: {e}")
            scenarios_valid = False

        # 6. Verify native Rust sensor implementation
        rust_sensors_valid = True
        rust_sensor_path = self.sensors_dir / self.RUST_SENSOR_FILE
        if not rust_sensor_path.exists():
            issues.append(f"Missing Rust sensor implementation: {self.RUST_SENSOR_FILE}")
            rust_sensors_valid = False
        else:
            lib_rs = self.sensors_dir / "lib.rs"
            if lib_rs.exists():
                lib_content = lib_rs.read_text(encoding="utf-8")
                if "pub mod macos_permissions;" not in lib_content:
                    issues.append("Rust lib.rs missing pub mod macos_permissions;")
                    rust_sensors_valid = False
            else:
                issues.append("Rust sensors lib.rs missing")
                rust_sensors_valid = False

        # 7. Verify non-negotiable charter invariant (scan_proves_safe = False)
        invariants_valid = True
        try:
            from system_mind.macos.permission_models import (
                EntitlementTier,
                MacEntitlementSpec,
                MacPermissionManifestReport,
                MacPermissionPromptInfo,
                MacPermissionType,
                PromptTriggerMode,
            )

            ent = MacEntitlementSpec(
                entitlement_key="test",
                tier=EntitlementTier.STANDARD_USER,
                description="test",
                is_required=False,
                target_component="test",
                fallback_behavior="test",
                scan_proves_safe=True,
            )
            if ent.scan_proves_safe is not False:
                issues.append("MacEntitlementSpec allowed scan_proves_safe = True")
                invariants_valid = False

            info = MacPermissionPromptInfo(
                permission_type=MacPermissionType.FULL_DISK_ACCESS,
                tcc_service_name="test",
                prompt_trigger_mode=PromptTriggerMode.GUIDED_SYSTEM_SETTINGS,
                user_dialog_text="test",
                settings_path="test",
                is_strictly_required=False,
                scan_proves_safe=True,
            )
            if info.scan_proves_safe is not False:
                issues.append("MacPermissionPromptInfo allowed scan_proves_safe = True")
                invariants_valid = False

            rep = MacPermissionManifestReport(scan_proves_safe=True)
            if rep.scan_proves_safe is not False:
                issues.append("MacPermissionManifestReport allowed scan_proves_safe = True")
                invariants_valid = False
        except Exception as e:
            issues.append(f"Invariant check failed: {e}")
            invariants_valid = False

        # 8. Verify Non-Goals (Input Monitoring prohibited)
        non_goals_valid = True
        try:
            from system_mind.macos.permission_inspector import MacOsPermissionInspector
            from system_mind.macos.permission_models import MacPermissionType

            inspector = MacOsPermissionInspector()
            rep = inspector.get_manifest_mock()
            input_mon = rep.get_permission(MacPermissionType.INPUT_MONITORING)
            if not input_mon or not input_mon.is_banned_non_goal:
                issues.append("Input Monitoring not flagged as prohibited non-goal")
                non_goals_valid = False
        except Exception as e:
            issues.append(f"Failed to verify non-goals: {e}")
            non_goals_valid = False

        valid = (
            doc_valid
            and test_suite_valid
            and cli_valid
            and ast_safety_valid
            and scenarios_valid
            and rust_sensors_valid
            and invariants_valid
            and non_goals_valid
            and len(issues) == 0
        )

        return MacOsPermissionsAuditResult(
            valid=valid,
            issues=tuple(issues),
            doc_valid=doc_valid,
            test_suite_valid=test_suite_valid,
            cli_valid=cli_valid,
            ast_safety_valid=ast_safety_valid,
            scenarios_valid=scenarios_valid,
            rust_sensors_valid=rust_sensors_valid,
            invariants_valid=invariants_valid,
            non_goals_valid=non_goals_valid,
            scenario_count=scenario_count,
        )
