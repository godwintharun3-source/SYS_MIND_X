"""Tests for Typed Action Contracts, Precondition/Postcondition Rules, and Atomic Rollback."""

from __future__ import annotations

import pytest

from system_mind.contracts.models import (
    PostconditionType,
    PredicateOperator,
    PreconditionType,
    RollbackContract,
    RollbackStrategy,
    TypedActionContract,
    TypedPostcondition,
    TypedPrecondition,
)
from system_mind.contracts.rules import ActionContractValidator, ContractRuleEvaluator
from system_mind.core.types import (
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)


def test_action_contract_hash_computation():
    """Verify deterministic SHA-256 calculation for Action Contracts."""
    contract = TypedActionContract(
        contract_id="act-001",
        capability_id="broker.system.snapshot",
        target_entity_id="entity-sys-root",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        parameters={"mount": "/", "snapshot_tag": "pre-update"},
    )
    assert len(contract.contract_hash) == 64
    assert int(contract.contract_hash, 16) > 0


def test_parameter_sanitization_blocks_shell_injections():
    """Verify that parameters containing shell meta-characters and commands are rejected."""
    bad_params = [
        {"cmd": "install.sh; rm -rf /"},
        {"pipe": "cat file | bash"},
        {"subshell": "echo $(whoami)"},
        {"nested": {"arg": "val && sudo reboot"}},
        {"list_arg": ["safe", "val; curl evil.com"]},
    ]

    for params in bad_params:
        contract = TypedActionContract(
            contract_id="act-inject",
            capability_id="broker.fs.write",
            target_entity_id="file-001",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.LOW_IMPACT,
            reversibility=Reversibility.REVERSIBLE,
            approval_requirement=ApprovalRequirement.NONE,
            parameters=params,
        )
        res = ActionContractValidator.validate_contract(contract)
        assert res.is_valid is False
        assert any("ParameterSanitizationViolation" in v for v in res.violations)


def test_consequential_operations_require_pre_and_postconditions():
    """Verify that Medium, High, and Critical operations require both pre and postconditions."""
    for tier in [
        OperationRiskTier.MEDIUM_IMPACT,
        OperationRiskTier.HIGH_IMPACT,
        OperationRiskTier.CRITICAL_PRIVILEGED,
    ]:
        contract_empty = TypedActionContract(
            contract_id=f"act-{tier.value}",
            capability_id="broker.service.restart",
            target_entity_id="svc-journald",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=tier,
            reversibility=Reversibility.REVERSIBLE,
            approval_requirement=ApprovalRequirement.USER_EXPLICIT,
            user_approved=True,
            rollback_contract=RollbackContract(
                strategy=RollbackStrategy.SERVICE_STATE_RESTORE,
                target_reference="svc-journald",
            ),
        )
        res = ActionContractValidator.validate_contract(contract_empty)
        assert res.is_valid is False
        assert any("PreconditionMissingViolation" in v for v in res.violations)
        assert any("PostconditionMissingViolation" in v for v in res.violations)


def test_high_and_critical_operations_require_rollback_contract():
    """Verify that High and Critical operations mandate an executable rollback contract."""
    contract = TypedActionContract(
        contract_id="act-high-no-rollback",
        capability_id="broker.os.patch",
        target_entity_id="os-core",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=[
            TypedPrecondition(
                precondition_id="pre-01",
                precondition_type=PreconditionType.POWER_AND_THERMAL,
                target_field="ac_power_connected",
                operator=PredicateOperator.IS_TRUE,
                expected_value=True,
                description="Require AC power",
            )
        ],
        postconditions=[
            TypedPostcondition(
                postcondition_id="post-01",
                postcondition_type=PostconditionType.SERVICE_LIFECYCLE,
                target_field="service_status",
                operator=PredicateOperator.EQUALS,
                expected_value="running",
                description="Service active",
            )
        ],
        rollback_contract=None,  # Missing!
    )
    res = ActionContractValidator.validate_contract(contract)
    assert res.is_valid is False
    assert any("RollbackContractMissingViolation" in v for v in res.violations)


def test_user_managed_component_mutation_requires_approval():
    """Verify that mutating operations on USER_MANAGED components mandate user approval."""
    contract_unapproved = TypedActionContract(
        contract_id="act-user-app",
        capability_id="broker.app.mutate",
        target_entity_id="/Applications/Slack.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=False,  # Unapproved!
    )
    res = ActionContractValidator.validate_contract(contract_unapproved)
    assert res.is_valid is False
    assert any("UserManagedOwnershipViolation" in v for v in res.violations)

    # Approved
    contract_approved = TypedActionContract(
        contract_id="act-user-app-ok",
        capability_id="broker.app.mutate",
        target_entity_id="/Applications/Slack.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )
    res_ok = ActionContractValidator.validate_contract(contract_approved)
    assert res_ok.is_valid is True


def test_precondition_evaluation_success_and_failure():
    """Verify deterministic evaluation of typed preconditions against observed system state."""
    contract = TypedActionContract(
        contract_id="act-pre-test",
        capability_id="broker.system.upgrade",
        target_entity_id="entity-os",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=[
            TypedPrecondition(
                precondition_id="pre-disk",
                precondition_type=PreconditionType.STORAGE_CAPACITY,
                target_field="free_space_bytes",
                operator=PredicateOperator.GREATER_THAN_OR_EQUAL,
                expected_value=10 * 1024 * 1024 * 1024,
                description="Minimum 10 GB free space",
            ),
            TypedPrecondition(
                precondition_id="pre-ac",
                precondition_type=PreconditionType.POWER_AND_THERMAL,
                target_field="ac_power",
                operator=PredicateOperator.IS_TRUE,
                expected_value=True,
                description="AC power connected",
            ),
        ],
        postconditions=[
            TypedPostcondition(
                postcondition_id="post-ok",
                postcondition_type=PostconditionType.SERVICE_LIFECYCLE,
                target_field="status",
                operator=PredicateOperator.EQUALS,
                expected_value="ok",
                description="OK status",
            )
        ],
    )

    # Compliant state
    compliant_state = {
        "free_space_bytes": 50 * 1024 * 1024 * 1024,
        "ac_power": True,
    }
    res_ok = ContractRuleEvaluator.evaluate_preconditions(contract, compliant_state)
    assert res_ok.all_satisfied is True
    assert len(res_ok.failures) == 0

    # Failing state: Insufficient disk space
    failing_state = {
        "free_space_bytes": 2 * 1024 * 1024 * 1024,  # Only 2 GB
        "ac_power": True,
    }
    res_fail = ContractRuleEvaluator.evaluate_preconditions(contract, failing_state)
    assert res_fail.all_satisfied is False
    assert any("pre-disk" in f for f in res_fail.failures)

    # Missing state field
    missing_state = {
        "free_space_bytes": 50 * 1024 * 1024 * 1024,
        # missing ac_power
    }
    res_missing = ContractRuleEvaluator.evaluate_preconditions(contract, missing_state)
    assert res_missing.all_satisfied is False
    assert any("PreconditionMissingState" in f for f in res_missing.failures)


def test_postcondition_evaluation_and_rollback_trigger():
    """Verify that postcondition failures trigger automatic rollback execution."""
    contract = TypedActionContract(
        contract_id="act-post-test",
        capability_id="broker.daemon.reload",
        target_entity_id="svc-syslog",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=[
            TypedPrecondition(
                precondition_id="pre-01",
                precondition_type=PreconditionType.PROCESS_LIFECYCLE,
                target_field="daemon_pid",
                operator=PredicateOperator.GREATER_THAN_OR_EQUAL,
                expected_value=1,
                description="Daemon process exists",
            )
        ],
        postconditions=[
            TypedPostcondition(
                postcondition_id="post-service-active",
                postcondition_type=PostconditionType.SERVICE_LIFECYCLE,
                target_field="service_state",
                operator=PredicateOperator.EQUALS,
                expected_value="ACTIVE",
                description="Service state must be ACTIVE",
            ),
            TypedPostcondition(
                postcondition_id="post-config-hash",
                postcondition_type=PostconditionType.FILESYSTEM_MUTATION,
                target_field="active_config_hash",
                operator=PredicateOperator.EQUALS,
                expected_value="abc123expectedhash",
                description="Config hash verified",
            ),
        ],
        rollback_contract=RollbackContract(
            strategy=RollbackStrategy.SERVICE_STATE_RESTORE,
            target_reference="svc-syslog",
            timeout_seconds=30,
        ),
    )

    # Post-execution state: Successful
    success_state = {
        "service_state": "ACTIVE",
        "active_config_hash": "abc123expectedhash",
    }
    res_ok = ContractRuleEvaluator.evaluate_postconditions(contract, success_state)
    assert res_ok.all_verified is True
    assert res_ok.triggers_rollback is False

    # Post-execution state: Service failed to start -> Triggers Rollback
    failed_state = {
        "service_state": "CRASH_LOOP",
        "active_config_hash": "abc123expectedhash",
    }
    res_fail = ContractRuleEvaluator.evaluate_postconditions(contract, failed_state)
    assert res_fail.all_verified is False
    assert res_fail.triggers_rollback is True
    assert any("post-service-active" in f for f in res_fail.failures)
