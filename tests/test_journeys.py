"""Tests for primary user journeys, execution engine, and measurable outcomes."""

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
    Reversibility,
)
from system_mind.journeys.engine import JourneyExecutionEngine
from system_mind.journeys.models import (
    JourneyStep,
    StepStatus,
    UserJourney,
    UserJourneyType,
)
from system_mind.personas.models import PersonaType


def test_journey_1_proactive_caretaker_success():
    """Verify Journey 1 (Proactive Health & Caretaker Remediation) succeeds with metrics."""
    diag_action = ActionContract(
        action_id="care-diag-001",
        action_type="inspect_system_telemetry",
        target_component="system_process_table",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["telemetry_daemon_active"],
        postconditions=["telemetry_snapshot_captured"],
    )
    terminate_action = ActionContract(
        action_id="care-term-002",
        action_type="terminate_orphaned_process",
        target_component="process_pid_99182_test_leak",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=["process_pid_exists", "pid_is_non_critical"],
        postconditions=["process_terminated", "cpu_load_normalized"],
        rollback_plan="No recovery required; process was orphaned",
    )

    journey = UserJourney(
        journey_id="j-001",
        journey_type=UserJourneyType.PROACTIVE_CARETAKER_REMEDIATION,
        target_persona=PersonaType.PERSONAL,
        title="Proactive Remediation of Runaway Background Daemon",
        description="Detect and terminate an orphaned process causing high CPU/battery drain.",
        steps=[
            JourneyStep(step_id="step-1", name="Diagnose Telemetry", action=diag_action),
            JourneyStep(step_id="step-2", name="Terminate Process", action=terminate_action),
        ],
    )

    result = JourneyExecutionEngine.execute_journey(journey)
    assert result.is_completed is True
    assert result.has_failed is False
    assert len(result.audit_trail) == 2
    assert result.steps[0].status == StepStatus.COMPLETED
    assert result.steps[1].status == StepStatus.COMPLETED

    # Check measurable outcomes
    assert len(result.outcomes) == 3
    for outcome in result.outcomes:
        assert outcome.passed is True


def test_journey_2_zero_trust_file_containment():
    """Verify Journey 2 (Zero-Trust File Execution & Containment) enforces isolation."""
    inspect_meta_action = ActionContract(
        action_id="file-meta-001",
        action_type="inspect_file_metadata",
        target_component="/tmp/untrusted_download.bin",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["file_exists"],
        postconditions=["hash_computed"],
    )
    isolated_exec_action = ActionContract(
        action_id="file-iso-002",
        action_type="file_execute",
        target_component="/tmp/untrusted_download.bin",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        file_containment=FileExecutionContainment.DISPOSABLE_ISOLATION,
        preconditions=["disposable_container_ready"],
        postconditions=["sandbox_destroyed"],
        rollback_plan="Destroy container and ephemeral storage",
    )

    journey = UserJourney(
        journey_id="j-002",
        journey_type=UserJourneyType.ZERO_TRUST_FILE_CONTAINMENT,
        target_persona=PersonaType.DEVELOPER,
        title="Zero-Trust Ephemeral Containment",
        description="Inspect and safely execute an unverified sample inside a network-isolated micro-VM.",
        steps=[
            JourneyStep(step_id="step-1", name="Inspect File Metadata", action=inspect_meta_action),
            JourneyStep(step_id="step-2", name="Execute In Disposable Container", action=isolated_exec_action),
        ],
    )

    result = JourneyExecutionEngine.execute_journey(journey)
    assert result.is_completed is True
    assert len(result.outcomes) == 2
    for outcome in result.outcomes:
        assert outcome.passed is True


def test_journey_3_developer_toolchain_diagnosis():
    """Verify Journey 3 (Developer Toolchain Diagnosis) protects project lockfiles."""
    diag_action = ActionContract(
        action_id="dev-tool-001",
        action_type="diagnose_toolchain",
        target_component="workspace_roots/my_project",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["workspace_exists"],
        postconditions=["missing_header_detected"],
    )

    journey = UserJourney(
        journey_id="j-003",
        journey_type=UserJourneyType.DEVELOPER_TOOLCHAIN_DIAGNOSIS,
        target_persona=PersonaType.DEVELOPER,
        title="Developer Toolchain Diagnostic",
        description="Identify missing compiler headers without altering virtualenvs or lockfiles.",
        steps=[
            JourneyStep(step_id="step-1", name="Diagnose Workspace", action=diag_action),
        ],
    )

    result = JourneyExecutionEngine.execute_journey(journey)
    assert result.is_completed is True
    for outcome in result.outcomes:
        assert outcome.passed is True


def test_journey_4_autonomous_os_maintenance():
    """Verify Journey 4 (Autonomous OS Maintenance) verifies non-interference on user apps."""
    maint_action = ActionContract(
        action_id="auto-maint-001",
        action_type="system_cache_vacuum",
        target_component="system_dynamic_linker_cache",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        preconditions=["system_idle", "ac_power_connected"],
        postconditions=["cache_rebuilt", "storage_reclaimed"],
        rollback_plan="Restore previous linker cache",
    )

    journey = UserJourney(
        journey_id="j-004",
        journey_type=UserJourneyType.AUTONOMOUS_OS_MAINTENANCE,
        target_persona=PersonaType.PERSONAL,
        title="Autonomous Background Maintenance",
        description="Prune OS caches during system idle without disturbing user applications.",
        steps=[
            JourneyStep(step_id="step-1", name="Prune System Cache", action=maint_action),
        ],
    )

    result = JourneyExecutionEngine.execute_journey(journey)
    assert result.is_completed is True
    for outcome in result.outcomes:
        assert outcome.passed is True


def test_journey_5_enterprise_dual_person_flow():
    """Verify Journey 5 (Enterprise Compliance Remediation) requires dual approval."""
    crit_action = ActionContract(
        action_id="ent-rem-001",
        action_type="firewall_reconfigure",
        target_component="fleet_packet_filter",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=["admin_active"],
        postconditions=["filter_applied"],
        rollback_plan="Revert to baseline pf.conf",
    )

    # 1. Single approver fails
    single_journey = UserJourney(
        journey_id="j-005a",
        journey_type=UserJourneyType.ENTERPRISE_COMPLIANCE_REMEDIATION,
        target_persona=PersonaType.ENTERPRISE_ADMIN,
        title="Enterprise Critical Firewall Remediation (Unauthorized)",
        description="Attempt critical modification without second approver.",
        steps=[JourneyStep(step_id="step-1", name="Apply Firewall Rule", action=crit_action)],
    )
    res_single = JourneyExecutionEngine.execute_journey(single_journey)
    assert res_single.is_completed is False
    assert res_single.has_failed is True
    assert res_single.steps[0].status == StepStatus.FAILED

    # 2. Dual approver succeeds
    crit_action_dual = ActionContract(
        action_id="ent-rem-002",
        action_type="firewall_reconfigure",
        target_component="fleet_packet_filter",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS,
        user_approved=True,
        preconditions=["admin_active"],
        postconditions=["filter_applied"],
        rollback_plan="Revert to baseline pf.conf",
        metadata={"second_approver_id": "ciso-approver-4491"},
    )
    dual_journey = UserJourney(
        journey_id="j-005b",
        journey_type=UserJourneyType.ENTERPRISE_COMPLIANCE_REMEDIATION,
        target_persona=PersonaType.ENTERPRISE_ADMIN,
        title="Enterprise Critical Firewall Remediation (Authorized)",
        description="Critical modification with verified second approver.",
        steps=[JourneyStep(step_id="step-1", name="Apply Firewall Rule", action=crit_action_dual)],
    )
    res_dual = JourneyExecutionEngine.execute_journey(dual_journey)
    assert res_dual.is_completed is True
    for outcome in res_dual.outcomes:
        assert outcome.passed is True


def test_journey_automated_rollback_on_failure():
    """Verify JourneyExecutionEngine performs reverse compensation rollback when a step fails."""
    step1_action = ActionContract(
        action_id="step1-backup",
        action_type="create_temporary_snapshot",
        target_component="/tmp/state_snapshot",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["storage_available"],
        postconditions=["snapshot_written"],
        rollback_plan="Remove temporary snapshot /tmp/state_snapshot",
    )
    step2_failing_action = ActionContract(
        action_id="step2-failing",
        action_type="apply_unsafe_config",
        target_component="system_service_daemon",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=["service_running"],
        postconditions=["service_reconfigured"],
        rollback_plan="Revert daemon config",
    )

    journey = UserJourney(
        journey_id="j-rollback-test",
        journey_type=UserJourneyType.PROACTIVE_CARETAKER_REMEDIATION,
        target_persona=PersonaType.PERSONAL,
        title="Rollback Test Journey",
        description="Verify that failure in Step 2 triggers automated compensation for Step 1.",
        steps=[
            JourneyStep(step_id="step-1", name="Create State Snapshot", action=step1_action),
            JourneyStep(
                step_id="step-2",
                name="Failing Operation",
                action=step2_failing_action,
                force_failure=True,  # Synthetic trigger
            ),
        ],
    )

    result = JourneyExecutionEngine.execute_journey(journey)
    assert result.is_completed is False
    assert result.has_failed is True
    assert result.is_rolled_back is True

    # Step 1 was completed then rolled back
    assert result.steps[0].status == StepStatus.ROLLED_BACK
    # Step 2 failed
    assert result.steps[1].status == StepStatus.FAILED

    # Audit trail contains rollback event
    assert any(entry.get("action") == "ROLLBACK_COMPENSATION" for entry in result.audit_trail)
