"""Unit and contract tests for SYSTEM MIND X operation classification and reversibility."""

import pytest

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)
from system_mind.operations.classification import (
    OperationCatalogRegistry,
    OperationClassificationResult,
    OperationClassifier,
    PrivilegeLevel,
    RollbackStrategy,
    SystemOperationDefinition,
)


def test_operation_catalog_completeness_and_invariants():
    """Verify that the operation catalog represents all risk tiers, privilege levels, and reversibility states."""
    ops = OperationCatalogRegistry.all_operations()
    assert len(ops) >= 12

    # Verify risk tiers representation
    risk_tiers_present = {op.risk_tier for op in ops}
    for r in OperationRiskTier:
        assert r in risk_tiers_present, f"Risk tier {r} missing from operation catalog"

    # Verify privilege levels representation
    priv_levels_present = {op.privilege_level for op in ops}
    for p in PrivilegeLevel:
        assert p in priv_levels_present, f"Privilege level {p} missing from operation catalog"

    # Verify reversibility representation
    reversibility_present = {op.reversibility for op in ops}
    for rev in Reversibility:
        assert rev in reversibility_present, f"Reversibility {rev} missing from operation catalog"

    # Precondition and postcondition completeness
    for op in ops:
        assert len(op.required_preconditions) > 0, f"Operation {op.operation_id} has empty preconditions"
        assert len(op.expected_postconditions) > 0, f"Operation {op.operation_id} has empty postconditions"


def test_autonomous_maintenance_invariants_in_catalog():
    """Verify that catalog-level operations eligible for autonomous runs strictly obey safety bounds."""
    auto_ops = OperationCatalogRegistry.get_autonomous_eligible_operations()
    assert len(auto_ops) >= 6

    for op in auto_ops:
        # Invariant 1: Autonomous operations can ONLY target SYSTEM_MANAGED components
        assert op.target_ownership == ComponentOwnership.SYSTEM_MANAGED, (
            f"Autonomous operation {op.operation_id} targets non-system component: {op.target_ownership}"
        )
        # Invariant 2: Autonomous operations can NEVER exceed MEDIUM_IMPACT
        assert op.risk_tier in (
            OperationRiskTier.READ_ONLY,
            OperationRiskTier.LOW_IMPACT,
            OperationRiskTier.MEDIUM_IMPACT,
        ), f"Autonomous operation {op.operation_id} has forbidden risk tier: {op.risk_tier}"


def test_catalog_filtering_methods():
    """Verify catalog query and filter functions."""
    read_only_ops = OperationCatalogRegistry.filter_by_risk_tier(OperationRiskTier.READ_ONLY)
    assert len(read_only_ops) >= 3
    for op in read_only_ops:
        assert op.risk_tier == OperationRiskTier.READ_ONLY

    broker_ops = OperationCatalogRegistry.filter_by_privilege_level(PrivilegeLevel.ELEVATED_BROKER_REQUIRED)
    assert len(broker_ops) >= 5
    for op in broker_ops:
        assert op.privilege_level == PrivilegeLevel.ELEVATED_BROKER_REQUIRED

    reversible_ops = OperationCatalogRegistry.filter_by_reversibility(Reversibility.REVERSIBLE)
    assert len(reversible_ops) >= 8

    op = OperationCatalogRegistry.get("OP-MAINT-01")
    assert op.operation_id == "OP-MAINT-01"
    assert op.name == "Vacuum Temporary Caches"

    with pytest.raises(KeyError):
        OperationCatalogRegistry.get("NONEXISTENT-OP")


def test_classifier_permits_safe_autonomous_operation():
    """Verify classifier validates a safe, compliant autonomous maintenance action."""
    action = ActionContract(
        action_id="act-maint-001",
        action_type="vacuum_caches",
        target_component="/tmp/user_cache",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        rollback_plan="system_mind.recovery.rollback_cache",
        preconditions=["cache_exists"],
        postconditions=["cache_cleared"],
    )

    res = OperationClassifier.classify_and_validate(action, operation_id="OP-MAINT-01")
    assert res.is_valid
    assert len(res.violations) == 0
    assert res.operation is not None
    assert res.operation.operation_id == "OP-MAINT-01"


def test_classifier_rejects_autonomous_user_managed_operation():
    """Verify classifier strictly rejects autonomous attempts to modify USER_MANAGED components."""
    action = ActionContract(
        action_id="act-user-app-001",
        action_type="update_application",
        target_component="/Applications/Slack.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        rollback_plan="system_mind.recovery.rollback_app",
    )

    res = OperationClassifier.classify_and_validate(action)
    assert not res.is_valid
    assert any("strictly limited to SYSTEM_MANAGED components" in v for v in res.violations)


def test_classifier_rejects_autonomous_high_impact_operation():
    """Verify classifier strictly rejects autonomous attempts to run HIGH_IMPACT or CRITICAL actions."""
    action = ActionContract(
        action_id="act-high-auto-001",
        action_type="reconfigure_firewall",
        target_component="com.apple.pf",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        rollback_plan="system_mind.recovery.restore_firewall",
    )

    res = OperationClassifier.classify_and_validate(action, operation_id="OP-SYS-01")
    assert not res.is_valid
    assert any("cannot execute operations exceeding MEDIUM_IMPACT" in v for v in res.violations)


def test_classifier_enforces_critical_privileged_approvals():
    """Verify critical privileged actions require user explicit approval and cannot have ApprovalRequirement.NONE."""
    unapproved_critical = ActionContract(
        action_id="act-crit-001",
        action_type="apply_os_core_update",
        target_component="darwin_kernel_update",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,  # Forbidden for critical
        user_approved=False,                            # Forbidden for critical
        rollback_plan="system_mind.recovery.snapshot_rollback",
    )

    res = OperationClassifier.classify_and_validate(unapproved_critical, operation_id="OP-SYS-02")
    assert not res.is_valid
    assert any("cannot have ApprovalRequirement.NONE" in v for v in res.violations)
    assert any("require explicit verified user authorization" in v for v in res.violations)


def test_classifier_rejects_raw_shell_execution():
    """Verify classifier rejects raw shell execution invariant violation."""
    raw_shell_action = ActionContract(
        action_id="act-shell-001",
        action_type="raw_shell_execution",
        target_component="shell",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    res = OperationClassifier.classify_and_validate(raw_shell_action)
    assert not res.is_valid
    assert any("raw shell execution" in v for v in res.violations)
