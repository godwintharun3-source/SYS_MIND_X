"""Tests for deterministic charter rule enforcement and invariant validation."""

import pytest

from system_mind.core.charter import CharterValidator, CharterViolationError
from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)


def test_reject_unrestricted_raw_shell():
    """Verify raw or unrestricted root shell execution by AI is rejected."""
    action = ActionContract(
        action_id="act-001",
        action_type="raw_shell_execution",
        target_component="shell",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )
    res = CharterValidator.validate(action)
    assert not res.is_valid
    assert any("raw shell execution" in v for v in res.violations)

    with pytest.raises(CharterViolationError) as exc_info:
        CharterValidator.assert_valid(action)
    assert "Unrestricted root or raw shell" in str(exc_info.value)


def test_reject_autonomous_maintenance_of_user_managed_components():
    """Verify autonomous maintenance cannot touch USER_MANAGED components."""
    action = ActionContract(
        action_id="act-002",
        action_type="update_application",
        target_component="com.microsoft.VSCode",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        preconditions=["check_network"],
        postconditions=["verify_version"],
    )
    res = CharterValidator.validate(action)
    assert not res.is_valid
    assert any("cannot modify USER_MANAGED component" in v for v in res.violations)


def test_reject_autonomous_maintenance_of_vendor_managed_components():
    """Verify autonomous maintenance cannot silently update VENDOR_MANAGED components."""
    action = ActionContract(
        action_id="act-003",
        action_type="firmware_update",
        target_component="thunderbolt_controller_firmware",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        rollback_plan="Boot from fallback EFI partition",
        is_autonomous_maintenance=True,
        preconditions=["check_ac_power"],
        postconditions=["verify_firmware_revision"],
    )
    res = CharterValidator.validate(action)
    assert not res.is_valid
    assert any("cannot modify VENDOR_MANAGED component" in v for v in res.violations)


def test_allow_autonomous_maintenance_of_system_managed_components():
    """Verify autonomous maintenance succeeds on SYSTEM_MANAGED components with valid contracts."""
    action = ActionContract(
        action_id="act-004",
        action_type="rotate_system_logs",
        target_component="system_audit_logs",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        preconditions=["disk_space_available", "service_quiesced"],
        postconditions=["compressed_archive_created", "active_log_truncated"],
        rollback_plan="Decompress previous archive if verification fails",
    )
    res = CharterValidator.validate(action)
    assert res.is_valid
    assert len(res.violations) == 0


def test_file_execution_zero_trust_containment():
    """Verify unknown files cannot execute without containment, and require isolation."""
    # 1. Denied execution or uncontained execution
    denied_action = ActionContract(
        action_id="act-005",
        action_type="file_execute",
        target_component="untrusted_payload.sh",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.PARTIALLY_REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        file_containment=FileExecutionContainment.DENIED,
        preconditions=["file_exists"],
        postconditions=["execution_logged"],
    )
    res = CharterValidator.validate(denied_action)
    assert not res.is_valid
    assert any("requires an approved containment strategy" in v for v in res.violations)

    # 2. Native host execution without cryptographic provenance is rejected
    unverified_native = ActionContract(
        action_id="act-006",
        action_type="file_execute",
        target_component="downloaded_binary",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.PARTIALLY_REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        file_containment=FileExecutionContainment.NATIVE_HOST_TRUSTED,
        metadata={"provenance_verified": False},
        preconditions=["file_exists"],
        postconditions=["process_spawned"],
    )
    res2 = CharterValidator.validate(unverified_native)
    assert not res2.is_valid
    assert any("cryptographically verified provenance" in v for v in res2.violations)

    # 3. Disposable isolation is permitted
    isolated_action = ActionContract(
        action_id="act-007",
        action_type="file_execute",
        target_component="suspicious_sample.bin",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        file_containment=FileExecutionContainment.DISPOSABLE_ISOLATION,
        metadata={"container_image": "disposable_sandbox:latest"},
        preconditions=["sandbox_initialized"],
        postconditions=["execution_trace_captured", "sandbox_destroyed"],
        rollback_plan="Destroy disposable container",
    )
    res3 = CharterValidator.validate(isolated_action)
    assert res3.is_valid


def test_critical_privileged_action_requires_explicit_approval_and_rollback():
    """Verify critical privileged actions (e.g. partition modification) fail without user approval and rollback."""
    # Missing approval and rollback
    crit_action = ActionContract(
        action_id="act-008",
        action_type="partition_modify",
        target_component="disk0s2",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        user_approved=False,
        rollback_plan=None,
        preconditions=["unmount_volume"],
        postconditions=["verify_partition_table"],
    )
    res = CharterValidator.validate(crit_action)
    assert not res.is_valid
    assert any("require explicit user approval" in v for v in res.violations)
    assert any("cannot proceed without confirmed user approval" in v for v in res.violations)
    assert any("require a documented, verified recovery/rollback strategy" in v for v in res.violations)

    # With approval and rollback
    approved_crit = ActionContract(
        action_id="act-009",
        action_type="partition_modify",
        target_component="disk0s2",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        rollback_plan="Restore from full APFS snapshot snap-2026-11-14",
        preconditions=["unmount_volume", "verify_snapshot_healthy"],
        postconditions=["verify_partition_table"],
    )
    res_approved = CharterValidator.validate(approved_crit)
    assert res_approved.is_valid
    assert len(res_approved.warnings) > 0  # Warns about irreversible action


def test_reject_unsupported_platform():
    """Verify operations targeting unsupported platforms are rejected."""
    action = ActionContract(
        action_id="act-010",
        action_type="install_driver",
        target_component="solaris_driver",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        target_platform=PlatformTier.UNSUPPORTED,
        preconditions=["check_root"],
        postconditions=["check_dev_node"],
    )
    res = CharterValidator.validate(action)
    assert not res.is_valid
    assert any("outside the supported first-release matrix" in v for v in res.violations)
