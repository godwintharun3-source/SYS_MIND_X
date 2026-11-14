"""Tests for AI-native OS prior art research, failure mode taxonomy, and safety benchmarks."""

import pytest

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
    Reversibility,
)
from system_mind.personas.models import PersonaType
from system_mind.research.prior_art import (
    FailureModeType,
    PriorArtCategory,
    PriorArtDatabase,
    PriorArtSafetyBenchmark,
)


def test_prior_art_database_completeness_and_invariants():
    """Verify all 4 prior art categories are represented with explicit countermeasures."""
    entries = PriorArtDatabase.get_all_entries()
    assert len(entries) >= 4

    categories = {e.category for e in entries}
    assert PriorArtCategory.VISION_GUI_AGENT in categories
    assert PriorArtCategory.UNRESTRICTED_SHELL_AGENT in categories
    assert PriorArtCategory.VENDOR_NATIVE_ASSISTANT in categories
    assert PriorArtCategory.DECLARATIVE_INFRA_TOOL in categories

    for entry in entries:
        assert entry.name != ""
        assert len(entry.vendors_or_projects) > 0
        assert len(entry.strengths) > 0
        assert entry.system_mind_countermeasure != ""


def test_prior_art_query_filtering():
    """Verify querying prior art by category and failure mode."""
    # Query by category
    vision_entries = PriorArtDatabase.get_by_category(PriorArtCategory.VISION_GUI_AGENT)
    assert len(vision_entries) >= 1
    assert any("Anthropic" in str(e.vendors_or_projects) for e in vision_entries)

    # Query by failure mode (F1: Ambient Privilege Escalation)
    f1_entries = PriorArtDatabase.get_by_failure_mode(FailureModeType.AMBIENT_PRIVILEGE_ESCALATION)
    assert len(f1_entries) >= 1
    assert any("AutoGPT" in str(e.vendors_or_projects) for e in f1_entries)


def test_benchmark_catches_f1_ambient_privilege_escalation():
    """Verify benchmark flags raw shell execution attempts."""
    action = ActionContract(
        action_id="bench-f1",
        action_type="raw_shell_execution",
        target_component="system_shell",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
    )
    result = PriorArtSafetyBenchmark.evaluate_action_safety(action)
    assert result.is_safe is False
    assert FailureModeType.AMBIENT_PRIVILEGE_ESCALATION in result.detected_failure_modes
    assert any("Enforced Invariant 1" in cm for cm in result.countermeasures_enforced)


def test_benchmark_catches_f2_uncontained_file_execution():
    """Verify benchmark flags uncontained file execution."""
    action = ActionContract(
        action_id="bench-f2",
        action_type="file_execute",
        target_component="/tmp/untrusted.sh",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.HIGH_IMPACT,
        reversibility=Reversibility.PARTIALLY_REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        file_containment=FileExecutionContainment.DENIED,
        preconditions=["file_exists"],
        postconditions=["executed"],
    )
    result = PriorArtSafetyBenchmark.evaluate_action_safety(action)
    assert result.is_safe is False
    assert FailureModeType.PROMPT_INJECTION_VULNERABILITY in result.detected_failure_modes
    assert any("Enforced Invariant 3" in cm for cm in result.countermeasures_enforced)


def test_benchmark_catches_f3_missing_preconditions():
    """Verify benchmark flags consequential actions lacking preconditions."""
    action = ActionContract(
        action_id="bench-f3",
        action_type="service_restart",
        target_component="system_network_daemon",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        preconditions=[],  # Missing preconditions!
        postconditions=["service_active"],
    )
    result = PriorArtSafetyBenchmark.evaluate_action_safety(action)
    assert result.is_safe is False
    assert FailureModeType.HALLUCINATED_DESTRUCTION in result.detected_failure_modes


def test_benchmark_catches_f4_irreversible_state_drift():
    """Verify benchmark flags critical operations lacking rollback recovery plans."""
    action = ActionContract(
        action_id="bench-f4",
        action_type="firmware_update",
        target_component="bios_firmware",
        target_ownership=ComponentOwnership.VENDOR_MANAGED,
        risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
        reversibility=Reversibility.IRREVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
        preconditions=["power_verified"],
        postconditions=["version_updated"],
        rollback_plan=None,  # Missing rollback!
    )
    result = PriorArtSafetyBenchmark.evaluate_action_safety(action)
    assert result.is_safe is False
    assert FailureModeType.IRREVERSIBLE_STATE_DRIFT in result.detected_failure_modes


def test_benchmark_catches_f5_privacy_path_leakage():
    """Verify benchmark flags actions targeting protected user privacy roots."""
    action = ActionContract(
        action_id="bench-f5",
        action_type="inspect_file",
        target_component="~/Documents/confidential_report.docx",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.READ_ONLY,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
    )
    result = PriorArtSafetyBenchmark.evaluate_action_safety(action, persona_type=PersonaType.PERSONAL)
    assert result.is_safe is False
    assert FailureModeType.PRIVACY_SCREEN_LEAKAGE in result.detected_failure_modes


def test_benchmark_catches_f6_component_ownership_clobbering():
    """Verify benchmark flags autonomous maintenance targeting user applications."""
    action = ActionContract(
        action_id="bench-f6",
        action_type="update_application",
        target_component="/Applications/Slack.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        preconditions=["idle_detected"],
        postconditions=["app_updated"],
        rollback_plan="Revert previous app binary",
    )
    result = PriorArtSafetyBenchmark.evaluate_action_safety(action)
    assert result.is_safe is False
    assert FailureModeType.COMPONENT_OWNERSHIP_CONTAMINATION in result.detected_failure_modes


def test_benchmark_approves_safe_compliant_action():
    """Verify a compliant action passes the safety benchmark without failure flags."""
    safe_action = ActionContract(
        action_id="bench-safe",
        action_type="rotate_system_logs",
        target_component="/var/log/system_audit.log",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        is_autonomous_maintenance=True,
        preconditions=["disk_space_ok", "log_unlocked"],
        postconditions=["archive_compressed", "active_log_cleared"],
        rollback_plan="Decompress previous archive",
    )
    result = PriorArtSafetyBenchmark.evaluate_action_safety(safe_action)
    assert result.is_safe is True
    assert len(result.detected_failure_modes) == 0
    assert len(result.violations) == 0
