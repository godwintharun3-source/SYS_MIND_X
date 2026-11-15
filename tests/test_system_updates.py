"""Unit and contract tests for the System-Update Ownership Taxonomy and safety validator."""

import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.updates import (
    RebootRequirement,
    SystemUpdatePolicyValidator,
    SystemUpdateProposal,
    SystemUpdateTaxonomyRegistry,
    UpdateLifecycleState,
    UpdatePreconditions,
    UpdateTier,
)


def test_system_update_taxonomy_registry_completeness():
    """Verify that all 6 maintenance tiers and lifecycle states are cataloged."""
    assert len(UpdateTier) == 6
    assert len(UpdateLifecycleState) == 8
    assert len(RebootRequirement) == 3

    specs = SystemUpdateTaxonomyRegistry.get_all_specs()
    assert len(specs) == 6

    # Verify lookups
    hotfix_spec = SystemUpdateTaxonomyRegistry.get_tier_spec(UpdateTier.OS_SECURITY_HOTFIX)
    assert hotfix_spec.ownership == ComponentOwnership.SYSTEM_MANAGED
    assert hotfix_spec.autonomous_eligible is True

    firmware_spec = SystemUpdateTaxonomyRegistry.get_tier_spec(UpdateTier.FIRMWARE_HARDWARE_UPDATE)
    assert firmware_spec.ownership == ComponentOwnership.VENDOR_MANAGED
    assert firmware_spec.autonomous_eligible is False
    assert firmware_spec.requires_ac_power is True
    assert firmware_spec.requires_snapshot is True


def test_autonomous_security_hotfix_allowed():
    """Verify that low-impact security hotfixes are permitted for autonomous callers."""
    proposal = SystemUpdateProposal(
        update_id="upd-sec-001",
        title="macOS XProtect Definitions Update",
        tier=UpdateTier.OS_SECURITY_HOTFIX,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        vendor_name="Apple Inc.",
        package_signature_valid=True,
        reboot_requirement=RebootRequirement.NO_REBOOT_REQUIRED,
        requires_snapshot=False,
        requires_ac_power=False,
        min_disk_space_bytes=100 * 1024 * 1024,
    )
    preconditions = UpdatePreconditions(
        snapshot_id=None,
        is_ac_power_connected=False,  # Allowed for low-impact hotfix
        available_disk_space_bytes=5 * 1024 * 1024 * 1024,
        user_approved=False,
    )

    result = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=preconditions,
        is_autonomous_caller=True,
    )
    assert result.permitted is True
    assert len(result.violations) == 0


def test_autonomous_caller_blocked_from_cumulative_os_updates():
    """Verify that cumulative OS updates are blocked for autonomous callers (Invariant 1)."""
    proposal = SystemUpdateProposal(
        update_id="upd-os-14.2",
        title="macOS Sonoma 14.2 Cumulative Update",
        tier=UpdateTier.OS_CUMULATIVE_UPDATE,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        vendor_name="Apple Inc.",
        package_signature_valid=True,
        reboot_requirement=RebootRequirement.STAGED_MAINTENANCE_REBOOT,
        requires_snapshot=True,
        requires_ac_power=True,
        min_disk_space_bytes=10 * 1024 * 1024 * 1024,
    )
    preconditions = UpdatePreconditions(
        snapshot_id="com.apple.TimeMachine.snapshot.20261115",
        is_ac_power_connected=True,
        available_disk_space_bytes=25 * 1024 * 1024 * 1024,
        user_approved=False,
    )

    result = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=preconditions,
        is_autonomous_caller=True,
    )
    assert result.permitted is False
    assert any("Autonomous Scope Violation" in v for v in result.violations)


def test_autonomous_caller_blocked_from_firmware_and_user_apps():
    """Verify that firmware and user application updates are barred from autonomous execution."""
    # 1. Firmware update
    firmware_prop = SystemUpdateProposal(
        update_id="upd-fw-smc",
        title="Apple Silicon T2/SMC Firmware Update",
        tier=UpdateTier.FIRMWARE_HARDWARE_UPDATE,
        ownership=ComponentOwnership.VENDOR_MANAGED,
        vendor_name="Apple Inc.",
        package_signature_valid=True,
        reboot_requirement=RebootRequirement.IMMEDIATE_REBOOT_REQUIRED,
        requires_snapshot=True,
        requires_ac_power=True,
        min_disk_space_bytes=500 * 1024 * 1024,
    )
    res_fw = SystemUpdatePolicyValidator.validate_proposal(
        proposal=firmware_prop,
        preconditions=UpdatePreconditions(),
        is_autonomous_caller=True,
    )
    assert res_fw.permitted is False
    assert any("Autonomous Scope Violation" in v for v in res_fw.violations)

    # 2. User App update
    user_app_prop = SystemUpdateProposal(
        update_id="upd-app-slack",
        title="Slack Desktop Update",
        tier=UpdateTier.USER_APP_UPDATE,
        ownership=ComponentOwnership.USER_MANAGED,
        vendor_name="Slack Technologies",
        package_signature_valid=True,
        reboot_requirement=RebootRequirement.NO_REBOOT_REQUIRED,
        requires_snapshot=False,
        requires_ac_power=False,
        min_disk_space_bytes=500 * 1024 * 1024,
    )
    res_app = SystemUpdatePolicyValidator.validate_proposal(
        proposal=user_app_prop,
        preconditions=UpdatePreconditions(),
        is_autonomous_caller=True,
    )
    assert res_app.permitted is False
    assert any("Autonomous Scope Violation" in v for v in res_app.violations)


def test_untrusted_signature_rejected():
    """Verify that update packages with invalid or untrusted signatures are hard-rejected (Invariant 4)."""
    proposal = SystemUpdateProposal(
        update_id="upd-unsigned",
        title="Unsigned Kernel Patch",
        tier=UpdateTier.OS_SECURITY_HOTFIX,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        vendor_name="Unknown",
        package_signature_valid=False,  # Unsigned!
        reboot_requirement=RebootRequirement.NO_REBOOT_REQUIRED,
        requires_snapshot=False,
        requires_ac_power=False,
        min_disk_space_bytes=10 * 1024 * 1024,
    )
    result = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=UpdatePreconditions(),
        is_autonomous_caller=False,
    )
    assert result.permitted is False
    assert any("Untrusted Package Signature" in v for v in result.violations)


def test_cumulative_update_requires_snapshot_and_ac_power():
    """Verify snapshot and AC power preconditions for cumulative updates."""
    proposal = SystemUpdateProposal(
        update_id="upd-os-cumulative",
        title="Ubuntu 24.04.1 Point Release",
        tier=UpdateTier.OS_CUMULATIVE_UPDATE,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        vendor_name="Canonical Ltd.",
        package_signature_valid=True,
        reboot_requirement=RebootRequirement.STAGED_MAINTENANCE_REBOOT,
        requires_snapshot=True,
        requires_ac_power=True,
        min_disk_space_bytes=10 * 1024 * 1024 * 1024,
    )

    # Missing Snapshot
    res_no_snap = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=UpdatePreconditions(snapshot_id="", is_ac_power_connected=True, user_approved=True),
        is_autonomous_caller=False,
    )
    assert res_no_snap.permitted is False
    assert any("Snapshot Precondition Failure" in v for v in res_no_snap.violations)

    # Missing AC Power (Battery-only)
    res_no_power = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=UpdatePreconditions(snapshot_id="snap-001", is_ac_power_connected=False, user_approved=True),
        is_autonomous_caller=False,
    )
    assert res_no_power.permitted is False
    assert any("Power Precondition Failure" in v for v in res_no_power.violations)

    # Fully Compliant (Snapshot + AC Power + User Approval)
    res_ok = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=UpdatePreconditions(
            snapshot_id="snap-001",
            is_ac_power_connected=True,
            available_disk_space_bytes=30 * 1024 * 1024 * 1024,
            user_approved=True,
        ),
        is_autonomous_caller=False,
    )
    assert res_ok.permitted is True
    assert len(res_ok.violations) == 0


def test_firmware_update_requires_user_approval_and_ac_power():
    """Verify that firmware flashing mandates explicit user approval, AC power, and snapshot."""
    proposal = SystemUpdateProposal(
        update_id="upd-uefi-bios",
        title="Dell Precision UEFI BIOS 1.14.0",
        tier=UpdateTier.FIRMWARE_HARDWARE_UPDATE,
        ownership=ComponentOwnership.VENDOR_MANAGED,
        vendor_name="Dell Technologies",
        package_signature_valid=True,
        reboot_requirement=RebootRequirement.IMMEDIATE_REBOOT_REQUIRED,
        requires_snapshot=True,
        requires_ac_power=True,
        min_disk_space_bytes=100 * 1024 * 1024,
    )

    # Missing user approval
    res_unapproved = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=UpdatePreconditions(snapshot_id="snap-pre-fw", is_ac_power_connected=True, user_approved=False),
        is_autonomous_caller=False,
    )
    assert res_unapproved.permitted is False
    assert any("User Approval Required" in v for v in res_unapproved.violations)

    # Fully approved and compliant
    res_approved = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=UpdatePreconditions(snapshot_id="snap-pre-fw", is_ac_power_connected=True, user_approved=True),
        is_autonomous_caller=False,
    )
    assert res_approved.permitted is True


def test_insufficient_disk_space_rejected():
    """Verify that update proposals are rejected when free storage is below required buffer."""
    proposal = SystemUpdateProposal(
        update_id="upd-big-os",
        title="Major OS Cumulative Update",
        tier=UpdateTier.OS_CUMULATIVE_UPDATE,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        vendor_name="Microsoft Corp.",
        package_signature_valid=True,
        reboot_requirement=RebootRequirement.STAGED_MAINTENANCE_REBOOT,
        requires_snapshot=True,
        requires_ac_power=True,
        min_disk_space_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
    )
    preconditions = UpdatePreconditions(
        snapshot_id="vss-shadow-001",
        is_ac_power_connected=True,
        available_disk_space_bytes=2 * 1024 * 1024 * 1024,  # Only 2 GB available!
        user_approved=True,
    )

    result = SystemUpdatePolicyValidator.validate_proposal(
        proposal=proposal,
        preconditions=preconditions,
        is_autonomous_caller=False,
    )
    assert result.permitted is False
    assert any("Storage Precondition Failure" in v for v in result.violations)
