"""Test suite verifying macOS permission prompts, prompt trigger rules, and required entitlements."""

from __future__ import annotations

import ast
from pathlib import Path
import platform
import pytest

from system_mind.macos.permission_inspector import MacOsPermissionInspector
from system_mind.macos.permission_models import (
    EntitlementTier,
    MacEntitlementSpec,
    MacPermissionManifestReport,
    MacPermissionPromptInfo,
    MacPermissionType,
    PermissionState,
    PromptTriggerMode,
)

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.unit
def test_permission_models_initialization_and_invariants() -> None:
    """All permission and entitlement models enforce scan_proves_safe = False (INV-PERM-05)."""
    ent = MacEntitlementSpec(
        entitlement_key="com.apple.security.network.client",
        tier=EntitlementTier.STANDARD_USER,
        description="Network client socket entitlement",
        is_required=True,
        target_component="Agent Wire Client",
        fallback_behavior="Socket fails",
        scan_proves_safe=True,  # Attempting True must be reset to False
    )
    assert ent.scan_proves_safe is False

    info = MacPermissionPromptInfo(
        permission_type=MacPermissionType.FULL_DISK_ACCESS,
        tcc_service_name="kTCCServiceSystemPolicyAllFiles",
        prompt_trigger_mode=PromptTriggerMode.GUIDED_SYSTEM_SETTINGS,
        user_dialog_text="System Settings",
        settings_path="x-apple.systempreferences:...",
        is_strictly_required=False,
        scan_proves_safe=True,
    )
    assert info.scan_proves_safe is False

    report = MacPermissionManifestReport(
        companion_mode="READ_ONLY_USER_COMPANION",
        scan_proves_safe=True,
    )
    assert report.scan_proves_safe is False


@pytest.mark.unit
def test_canonical_permissions_catalog_coverage() -> None:
    """Inspector catalogs all 8 core macOS permission prompt scenarios."""
    inspector = MacOsPermissionInspector()
    perms = inspector.CANONICAL_PERMISSIONS

    assert len(perms) >= 8

    perm_types = {p.permission_type for p in perms}
    expected_types = {
        MacPermissionType.FULL_DISK_ACCESS,
        MacPermissionType.SCREEN_RECORDING,
        MacPermissionType.ACCESSIBILITY,
        MacPermissionType.DOCUMENTS_FOLDER,
        MacPermissionType.DOWNLOADS_FOLDER,
        MacPermissionType.DESKTOP_FOLDER,
        MacPermissionType.INPUT_MONITORING,
        MacPermissionType.ENDPOINT_SECURITY,
    }
    assert expected_types.issubset(perm_types)

    for p in perms:
        assert p.tcc_service_name, f"Missing TCC service name for {p.permission_type}"
        assert p.user_dialog_text, f"Missing prompt dialog text for {p.permission_type}"
        assert p.settings_path, f"Missing settings path for {p.permission_type}"
        assert p.fallback_strategy, f"Missing fallback strategy for {p.permission_type}"
        assert p.scan_proves_safe is False


@pytest.mark.unit
def test_input_monitoring_prohibited_non_goal() -> None:
    """Input Monitoring is strictly cataloged as a prohibited non-goal (INV-PERM-03 / NG-02)."""
    inspector = MacOsPermissionInspector()
    report = inspector.get_manifest_mock()

    input_perm = report.get_permission(MacPermissionType.INPUT_MONITORING)
    assert input_perm is not None
    assert input_perm.is_banned_non_goal is True
    assert input_perm.prompt_trigger_mode == PromptTriggerMode.NEVER_PROMPTED
    assert "PROHIBITED NON-GOAL" in input_perm.fallback_strategy

    assert report.active_states.get(MacPermissionType.INPUT_MONITORING.value) == PermissionState.PROHIBITED_NON_GOAL


@pytest.mark.unit
def test_personal_directories_exclusion_policy() -> None:
    """Personal folders (Documents, Downloads, Desktop) are excluded by policy and never prompted."""
    inspector = MacOsPermissionInspector()
    report = inspector.get_manifest_mock()

    for ptype in (
        MacPermissionType.DOCUMENTS_FOLDER,
        MacPermissionType.DOWNLOADS_FOLDER,
        MacPermissionType.DESKTOP_FOLDER,
    ):
        p_info = report.get_permission(ptype)
        assert p_info is not None
        assert p_info.prompt_trigger_mode == PromptTriggerMode.NEVER_PROMPTED
        assert report.active_states.get(ptype.value) == PermissionState.EXCLUDED_BY_POLICY


@pytest.mark.unit
def test_full_disk_access_passive_probe_and_fallback() -> None:
    """Full Disk Access uses guided system settings without invasive dialog loops (INV-PERM-02)."""
    inspector = MacOsPermissionInspector()
    fda = inspector.inspect_permissions().get_permission(MacPermissionType.FULL_DISK_ACCESS)

    assert fda is not None
    assert fda.prompt_trigger_mode == PromptTriggerMode.GUIDED_SYSTEM_SETTINGS
    assert fda.is_strictly_required is False
    assert "partial_data = True" in fda.fallback_strategy


@pytest.mark.unit
def test_screen_recording_fallback_behavior() -> None:
    """Screen Recording denial falls back to omitting window titles without taking video captures."""
    inspector = MacOsPermissionInspector()
    sc = inspector.inspect_permissions().get_permission(MacPermissionType.SCREEN_RECORDING)

    assert sc is not None
    assert sc.is_strictly_required is False
    assert "Omit window titles" in sc.fallback_strategy


@pytest.mark.unit
def test_accessibility_fallback_to_frontmost_app() -> None:
    """Accessibility denial transparently falls back to NSWorkspace.frontmostApplication."""
    inspector = MacOsPermissionInspector()
    ax = inspector.inspect_permissions().get_permission(MacPermissionType.ACCESSIBILITY)

    assert ax is not None
    assert ax.is_strictly_required is False
    assert "NSWorkspace.frontmostApplication" in ax.fallback_strategy


@pytest.mark.unit
def test_endpoint_security_entitlement_fallback() -> None:
    """Endpoint Security is classified as APPLE_RESTRICTED with transparent FSEvents fallback."""
    inspector = MacOsPermissionInspector()
    report = inspector.get_manifest_mock()

    es_perm = report.get_permission(MacPermissionType.ENDPOINT_SECURITY)
    assert es_perm is not None
    assert "CoreServices FSEvents" in es_perm.fallback_strategy

    es_ent = report.get_entitlement("com.apple.developer.endpoint-security.client")
    assert es_ent is not None
    assert es_ent.tier == EntitlementTier.APPLE_RESTRICTED
    assert es_ent.is_required is False


@pytest.mark.unit
def test_canonical_entitlements_spec_coverage() -> None:
    """Canonical entitlements catalog declares required network and prohibited hardened exceptions."""
    inspector = MacOsPermissionInspector()
    entitlements = inspector.CANONICAL_ENTITLEMENTS

    net_client = next((e for e in entitlements if e.entitlement_key == "com.apple.security.network.client"), None)
    assert net_client is not None
    assert net_client.tier == EntitlementTier.STANDARD_USER
    assert net_client.is_required is True

    jit_exc = next((e for e in entitlements if e.entitlement_key == "com.apple.security.cs.allow-jit"), None)
    assert jit_exc is not None
    assert jit_exc.is_required is False
    assert "Prohibited" in jit_exc.fallback_behavior


@pytest.mark.unit
def test_permission_manifest_mock_and_live_inspection() -> None:
    """Permission inspector emits complete report with warnings and non-goals enforced."""
    inspector = MacOsPermissionInspector()
    report = inspector.inspect_permissions()

    assert report.companion_mode == "READ_ONLY_USER_COMPANION"
    assert report.scan_proves_safe is False
    assert len(report.permissions) >= 8
    assert len(report.entitlements) >= 6
    assert len(report.non_goals_enforced) >= 4


@pytest.mark.unit
def test_documentation_file_presence_and_completeness() -> None:
    """The canonical documentation file docs/MACOS_PERMISSIONS_AND_ENTITLEMENTS.md exists and is complete."""
    doc_path = ROOT_DIR / "docs" / "MACOS_PERMISSIONS_AND_ENTITLEMENTS.md"
    assert doc_path.exists(), f"Missing canonical permissions document: {doc_path}"

    content = doc_path.read_text(encoding="utf-8")
    assert "Full Disk Access" in content
    assert "kTCCServiceScreenCapture" in content
    assert "kTCCServiceAccessibility" in content
    assert "kTCCServiceListenEvent" in content
    assert "PROHIBITED" in content
    assert "Privacy Preferences Policy Control" in content
    assert "Scan != Safe" in content


@pytest.mark.safety_critical
def test_ast_safety_zero_ambient_shell_sc01() -> None:
    """AST safety analysis verifies zero shell=True or os.system across permission engine (SC-01)."""
    target_files = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "permission_inspector.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "permission_models.py",
    ]

    for fpath in target_files:
        assert fpath.exists(), f"File missing: {fpath}"
        source = fpath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        pytest.fail(f"Forbidden os.system detected in {fpath.name}:{node.lineno}")

                for kw in node.keywords:
                    if kw.arg == "shell":
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            pytest.fail(f"Forbidden shell=True in {fpath.name}:{node.lineno}")
