"""Automated packaging validator auditing the Mock Platform Adapter subsystem."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)
from system_mind.platform.adapter import (
    MockPlatformAdapter,
    MockPlatformProfileFactory,
    PlatformAdapter,
)
from system_mind.platform.matrix import (
    PlatformMatrixRegistry,
    PlatformTargetId,
)


@dataclass(frozen=True)
class MockPlatformAuditResult:
    """Outcome of auditing the mock platform adapter subsystem."""

    valid: bool
    issues: tuple[str, ...]
    adapter_interface_valid: bool
    mock_profiles_valid: bool
    safety_invariants_valid: bool
    cli_runner_valid: bool


class MockPlatformValidator:
    """Programmatic validator verifying the completeness, safety, and tooling of mock platform adapters."""

    REQUIRED_ADAPTER_METHODS = [
        "get_target_id",
        "get_host_report",
        "get_security_state",
        "get_hardware_telemetry",
        "get_process_telemetry",
        "get_filesystem_events",
        "get_file_provenance",
        "create_system_snapshot",
        "rollback_system_snapshot",
        "stage_system_update",
        "execute_contained_action",
        "get_audit_history",
    ]

    REQUIRED_TARGETS = [
        PlatformTargetId.MACOS_APPLE_SILICON,
        PlatformTargetId.WINDOWS_11_X64,
        PlatformTargetId.UBUNTU_LTS_X64,
        PlatformTargetId.NIXOS_VM,
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> MockPlatformAuditResult:
        """Execute comprehensive audit across adapter interface, profiles, safety invariants, and CLI tool."""
        base_dir = root_dir or ROOT_DIR
        issues: List[str] = []
        adapter_ok = True
        profiles_ok = True
        safety_ok = True
        cli_ok = True

        # 1. Audit PlatformAdapter ABC and MockPlatformAdapter adherence
        for method_name in cls.REQUIRED_ADAPTER_METHODS:
            if not hasattr(PlatformAdapter, method_name):
                issues.append(f"PlatformAdapter ABC missing required contract method: {method_name}")
                adapter_ok = False
            if not hasattr(MockPlatformAdapter, method_name):
                issues.append(f"MockPlatformAdapter missing implementation for: {method_name}")
                adapter_ok = False

        if not issubclass(MockPlatformAdapter, PlatformAdapter):
            issues.append("MockPlatformAdapter does not inherit from PlatformAdapter ABC")
            adapter_ok = False

        # 2. Audit all 4 platform target profiles
        for target in cls.REQUIRED_TARGETS:
            try:
                mock = MockPlatformProfileFactory.create_mock(target)
                report = mock.get_host_report()
                compatible, diags = PlatformMatrixRegistry.validate_host_compatibility(report)
                if not compatible:
                    issues.append(f"Mock profile for {target.value} failed matrix validation: {diags}")
                    profiles_ok = False
                sec = mock.get_security_state()
                if sec is None or not sec.firewall_enabled:
                    issues.append(f"Mock profile for {target.value} has invalid security state")
                    profiles_ok = False
            except Exception as exc:
                issues.append(f"Failed instantiating mock profile for {target.value}: {exc}")
                profiles_ok = False

        # 3. Audit safety invariants (SC-01 zero mutation, SC-02 user app protection, SC-03 approval gates)
        try:
            adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

            # Test 3a: Autonomous maintenance against USER_MANAGED component MUST fail
            forbidden_contract = ActionContract(
                action_id="act_test_user_app_mutation",
                action_type="UPDATE_PACKAGE",
                target_component="com.google.Chrome",
                target_ownership=ComponentOwnership.USER_MANAGED,
                risk_tier=OperationRiskTier.MEDIUM_IMPACT,
                reversibility=Reversibility.REVERSIBLE,
                approval_requirement=ApprovalRequirement.NONE,
                is_autonomous_maintenance=True,
            )
            try:
                adapter.execute_contained_action(forbidden_contract)
                issues.append("Safety violation: autonomous maintenance against USER_MANAGED app was not blocked")
                safety_ok = False
            except PermissionError:
                pass  # Correctly rejected

            # Test 3b: Staging system update for USER_MANAGED component MUST fail
            try:
                adapter.stage_system_update("com.microsoft.VSCode", ComponentOwnership.USER_MANAGED)
                issues.append("Safety violation: system update staging for USER_MANAGED app was not blocked")
                safety_ok = False
            except PermissionError:
                pass  # Correctly rejected

            # Test 3c: Critical privileged operation without user approval MUST fail
            unapproved_contract = ActionContract(
                action_id="act_test_unapproved_critical",
                action_type="MODIFY_BOOTLOADER",
                target_component="bootloader",
                target_ownership=ComponentOwnership.SYSTEM_MANAGED,
                risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
                reversibility=Reversibility.IRREVERSIBLE,
                approval_requirement=ApprovalRequirement.USER_EXPLICIT,
                user_approved=False,
            )
            try:
                adapter.execute_contained_action(unapproved_contract)
                issues.append("Safety violation: unapproved CRITICAL_PRIVILEGED action was not blocked")
                safety_ok = False
            except PermissionError:
                pass  # Correctly rejected

            # Test 3d: Audit log contains recorded safety rejections
            audit_events = adapter.get_audit_history()
            rejection_events = [e for e in audit_events if e.get("event_type") in ("ACTION_REJECTED", "UPDATE_REJECTED")]
            if len(rejection_events) < 3:
                issues.append(f"Audit log incomplete: expected at least 3 rejection events, found {len(rejection_events)}")
                safety_ok = False

        except Exception as exc:
            issues.append(f"Failed verifying safety invariants: {exc}")
            safety_ok = False

        # 4. Audit developer CLI tool
        cli_path = base_dir / "tools" / "mock_platform_cli.py"
        if not cli_path.exists():
            issues.append("Missing developer CLI tool: tools/mock_platform_cli.py")
            cli_ok = False
        else:
            try:
                result = subprocess.run(
                    [sys.executable, str(cli_path), "audit-matrix", "--json"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if result.returncode != 0:
                    issues.append(f"tools/mock_platform_cli.py audit-matrix failed with return code {result.returncode}")
                    cli_ok = False
            except Exception as exc:
                issues.append(f"Failed executing tools/mock_platform_cli.py: {exc}")
                cli_ok = False

        overall_valid = adapter_ok and profiles_ok and safety_ok and cli_ok and (len(issues) == 0)
        return MockPlatformAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            adapter_interface_valid=adapter_ok,
            mock_profiles_valid=profiles_ok,
            safety_invariants_valid=safety_ok,
            cli_runner_valid=cli_ok,
        )
