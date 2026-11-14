"""Tests for component ownership boundaries and maintenance isolation."""

import pytest

from system_mind.core.charter import CharterValidator, CharterViolationError
from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    Reversibility,
)


@pytest.mark.parametrize(
    "component_name,ownership,is_auto,should_pass",
    [
        # System managed components
        ("macos_xnu_kernel_cache", ComponentOwnership.SYSTEM_MANAGED, True, True),
        ("system_security_definitions", ComponentOwnership.SYSTEM_MANAGED, True, True),
        ("systemd_journal_vacuum", ComponentOwnership.SYSTEM_MANAGED, True, True),
        # User managed components: must NEVER be automatically updated
        ("/Applications/Google Chrome.app", ComponentOwnership.USER_MANAGED, True, False),
        ("pip_packages_in_venv", ComponentOwnership.USER_MANAGED, True, False),
        ("npm_node_modules", ComponentOwnership.USER_MANAGED, True, False),
        ("dotfiles_zshrc", ComponentOwnership.USER_MANAGED, True, False),
        # User managed components: explicit user-initiated action with approval is allowed
        ("/Applications/Google Chrome.app", ComponentOwnership.USER_MANAGED, False, True),
        ("pip_packages_in_venv", ComponentOwnership.USER_MANAGED, False, True),
        # Vendor managed components: autonomous update forbidden, requires user confirmation
        ("apple_t2_firmware", ComponentOwnership.VENDOR_MANAGED, True, False),
    ],
)
def test_ownership_maintenance_policies(component_name, ownership, is_auto, should_pass):
    action = ActionContract(
        action_id="test-own-001",
        action_type="maintenance_action",
        target_component=component_name,
        target_ownership=ownership,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT if not is_auto else ApprovalRequirement.NONE,
        user_approved=not is_auto,
        is_autonomous_maintenance=is_auto,
        preconditions=["check_system_ready"],
        postconditions=["verify_integrity"],
        rollback_plan="Revert operation snapshot",
    )
    result = CharterValidator.validate(action)
    if should_pass:
        assert result.is_valid, f"Expected valid for {component_name}, got violations: {result.violations}"
    else:
        assert not result.is_valid, f"Expected violation for {component_name}, but passed!"
        assert any(
            "cannot modify" in v for v in result.violations
        )
