"""Unit and contract tests for SYSTEM MIND X product non-goals and explicit safety constraints."""

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
from system_mind.personas.models import PersonaType
from system_mind.security.safety_constraints import (
    ConstraintValidationResult,
    NonGoalCategory,
    NonGoalRegistry,
    ProductNonGoal,
    SafetyConstraint,
    SafetyConstraintCategory,
    SafetyConstraintRegistry,
    SafetyConstraintValidator,
)


def test_non_goals_registry_completeness():
    """Verify that all 10 product non-goals are cataloged across all categories."""
    non_goals = NonGoalRegistry.get_all()
    assert len(non_goals) == 10

    # Verify categories
    categories_present = {ng.category for ng in non_goals}
    for cat in NonGoalCategory:
        assert cat in categories_present, f"Category {cat} missing from non-goals registry"

    for ng in non_goals:
        assert ng.non_goal_id.startswith("NG-")
        assert len(ng.title) > 0
        assert len(ng.rationale) > 0
        assert len(ng.boundary_statement) > 0

    ng1 = NonGoalRegistry.get("NG-01")
    assert "No Unrestricted Host Shell" in ng1.title

    with pytest.raises(KeyError):
        NonGoalRegistry.get("NG-999")


def test_safety_constraints_registry_completeness():
    """Verify that all 8 safety constraints are registered with hard invariants."""
    constraints = SafetyConstraintRegistry.get_all()
    assert len(constraints) == 8

    categories_present = {sc.category for sc in constraints}
    for cat in SafetyConstraintCategory:
        assert cat in categories_present, f"Category {cat} missing from safety constraints"

    for sc in constraints:
        assert sc.constraint_id.startswith("SC-")
        assert sc.is_hard_invariant is True
        assert len(sc.rejection_message) > 0

    sc = SafetyConstraintRegistry.get("SC-01")
    assert sc.title == "Raw Shell Command Rejection"

    with pytest.raises(KeyError):
        SafetyConstraintRegistry.get("SC-UNKNOWN")


def test_validator_blocks_sc01_raw_shell():
    """Verify SC-01 blocks raw shell command execution."""
    action = ActionContract(
        action_id="act-sc01",
        action_type="raw_shell_execution",
        target_component="bash",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    res = SafetyConstraintValidator.validate_action(action)
    assert not res.is_permitted
    assert any("SC-01" in sc.constraint_id for sc in res.violated_constraints)
    assert any("Raw shell execution is strictly forbidden" in v for v in res.violations)


def test_validator_blocks_sc02_autonomous_user_modification():
    """Verify SC-02 blocks autonomous mutation of user-managed components."""
    action = ActionContract(
        action_id="act-sc02",
        action_type="update_app",
        target_component="/Applications/Visual Studio Code.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        rollback_plan="system_mind.recovery.rollback_app",
    )

    res = SafetyConstraintValidator.validate_action(action)
    assert not res.is_permitted
    assert any("SC-02" in sc.constraint_id for sc in res.violated_constraints)
    assert any("cannot modify USER_MANAGED components" in v for v in res.violations)


def test_validator_blocks_sc03_uncontained_external_file():
    """Verify SC-03 blocks execution of uncontained external files."""
    uncontained_action = ActionContract(
        action_id="act-sc03",
        action_type="file_execute",
        target_component="/tmp/untrusted.exe",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        file_containment=FileExecutionContainment.DENIED,
    )

    res = SafetyConstraintValidator.validate_action(uncontained_action)
    assert not res.is_permitted
    assert any("SC-03" in sc.constraint_id for sc in res.violated_constraints)

    # Contained action passes SC-03
    contained_action = ActionContract(
        action_id="act-sc03-iso",
        action_type="file_execute",
        target_component="/tmp/untrusted.exe",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        file_containment=FileExecutionContainment.DISPOSABLE_ISOLATION,
    )
    res_iso = SafetyConstraintValidator.validate_action(contained_action, persona_type=PersonaType.DEVELOPER)
    assert not any("SC-03" in sc.constraint_id for sc in res_iso.violated_constraints)


def test_validator_blocks_sc04_privacy_perimeter():
    """Verify SC-04 blocks inspection of protected privacy paths."""
    action = ActionContract(
        action_id="act-sc04",
        action_type="file_read",
        target_component="~/.ssh/id_ed25519",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )

    res = SafetyConstraintValidator.validate_action(action, persona_type=PersonaType.PERSONAL)
    assert not res.is_permitted
    assert any("SC-04" in sc.constraint_id for sc in res.violated_constraints)


def test_validator_blocks_sc05_unauthorized_critical():
    """Verify SC-05 blocks unapproved CRITICAL_PRIVILEGED operations."""
    action = ActionContract(
        action_id="act-sc05",
        action_type="modify_security_policy",
        target_component="audit_policy",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        user_approved=False,
    )

    res = SafetyConstraintValidator.validate_action(action)
    assert not res.is_permitted
    assert any("SC-05" in sc.constraint_id for sc in res.violated_constraints)


def test_validator_blocks_sc06_unsupported_platform():
    """Verify SC-06 blocks execution targeting unsupported platform architectures."""
    action = ActionContract(
        action_id="act-sc06",
        action_type="service_restart",
        target_component="system_service",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        target_platform=PlatformTier.UNSUPPORTED,
    )

    res = SafetyConstraintValidator.validate_action(action)
    assert not res.is_permitted
    assert any("SC-06" in sc.constraint_id for sc in res.violated_constraints)


def test_validator_blocks_sc07_unattended_firmware_modification():
    """Verify SC-07 blocks unattended firmware or partition table modification."""
    action = ActionContract(
        action_id="act-sc07",
        action_type="flash_firmware",
        target_component="uefi_firmware_blob",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        is_autonomous_maintenance=True,  # Forbidden for firmware!
        user_approved=False,
    )

    res = SafetyConstraintValidator.validate_action(action)
    assert not res.is_permitted
    assert any("SC-07" in sc.constraint_id for sc in res.violated_constraints)


def test_validator_blocks_sc08_security_control_bypass():
    """Verify SC-08 blocks actions attempting to disable native OS security controls."""
    action = ActionContract(
        action_id="act-sc08",
        action_type="disable_security",
        target_component="csrutil_sip_disable",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )

    res = SafetyConstraintValidator.validate_action(action)
    assert not res.is_permitted
    assert any("SC-08" in sc.constraint_id for sc in res.violated_constraints)


def test_validator_approves_fully_compliant_action():
    """Verify fully compliant action passes all safety constraints."""
    action = ActionContract(
        action_id="act-safe-001",
        action_type="clean_temporary_cache",
        target_component="/tmp/system_cache",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        rollback_plan="system_mind.recovery.rollback_cache",
        preconditions=["cache_exists"],
        postconditions=["cache_freed"],
    )

    res = SafetyConstraintValidator.validate_action(action, persona_type=PersonaType.PERSONAL)
    assert res.is_permitted
    assert len(res.violated_constraints) == 0
    assert len(res.violations) == 0
