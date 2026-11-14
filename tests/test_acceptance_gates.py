"""Unit and contract tests for SYSTEM MIND X research questions and release acceptance gates."""

import pytest

from system_mind.governance.gates import (
    AcceptanceGate,
    AcceptanceGateId,
    AcceptanceGateRegistry,
    GateStatus,
    GateVerificationReport,
    ReleaseGateVerifier,
    ResearchQuestion,
    ResearchQuestionId,
    ResearchQuestionRegistry,
)


def test_research_questions_registry_completeness():
    """Verify that all 8 core research questions are cataloged and approved."""
    questions = ResearchQuestionRegistry.get_all()
    assert len(questions) == 8

    for q in questions:
        assert q.question_id.startswith("RQ-")
        assert len(q.title) > 0
        assert len(q.question) > 0
        assert len(q.hypothesis) > 0
        assert len(q.verification_strategy) > 0
        assert q.is_approved is True

    rq1 = ResearchQuestionRegistry.get("RQ-01")
    assert rq1.title == "Policy-Broker Decoupling"
    assert "deterministic" in rq1.question.lower()

    with pytest.raises(KeyError):
        ResearchQuestionRegistry.get("RQ-UNKNOWN")


def test_acceptance_gates_registry_completeness():
    """Verify that all 8 first-release acceptance gates are cataloged with mandatory invariants."""
    gates = AcceptanceGateRegistry.get_all()
    assert len(gates) == 8

    for g in gates:
        assert g.gate_id.startswith("AG-")
        assert len(g.name) > 0
        assert len(g.description) > 0
        assert g.mandatory is True
        assert len(g.invariants) > 0

    ag1 = AcceptanceGateRegistry.get("AG-01")
    assert ag1.name == "Functional Completeness"

    with pytest.raises(KeyError):
        AcceptanceGateRegistry.get("AG-UNKNOWN")


def test_release_gate_verifier_all_passed():
    """Verify ReleaseGateVerifier returns all_passed=True when all 8 gates pass."""
    report = ReleaseGateVerifier.audit_release_readiness(
        has_contracts=True,
        has_unhandled_stubs=False,
        tests_run=82,
        tests_failed=0,
        boundary_violations=0,
        raw_shell_attempted=False,
        rollback_handlers_verified=True,
        uncertified_platform_claimed=False,
        design_notes_present=True,
        adr_logged=True,
        secrets_redacted=True,
        human_reviewed=True,
    )

    assert report.all_passed is True
    assert len(report.violations) == 0
    assert len(report.gate_results) == 8
    for gate_id, status in report.gate_results.items():
        assert status == GateStatus.PASSED, f"Gate {gate_id} failed unexpectedly: {status}"


def test_release_gate_verifier_catches_test_failure():
    """Verify AG-02 failure when tests fail."""
    report = ReleaseGateVerifier.audit_release_readiness(
        tests_run=82,
        tests_failed=2,
    )
    assert report.all_passed is False
    assert report.gate_results["AG-02"] == GateStatus.FAILED
    assert any("AG-02 Test Gate Failed" in v for v in report.violations)


def test_release_gate_verifier_catches_security_violation():
    """Verify AG-03 failure when boundary violations or raw shell attempts occur."""
    report = ReleaseGateVerifier.audit_release_readiness(
        boundary_violations=1,
    )
    assert report.all_passed is False
    assert report.gate_results["AG-03"] == GateStatus.FAILED
    assert any("AG-03 Security Gate Failed" in v for v in report.violations)

    report_shell = ReleaseGateVerifier.audit_release_readiness(
        raw_shell_attempted=True,
    )
    assert report_shell.all_passed is False
    assert report_shell.gate_results["AG-03"] == GateStatus.FAILED


def test_release_gate_verifier_catches_missing_rollback():
    """Verify AG-04 failure when rollback handlers are unverified."""
    report = ReleaseGateVerifier.audit_release_readiness(
        rollback_handlers_verified=False,
    )
    assert report.all_passed is False
    assert report.gate_results["AG-04"] == GateStatus.FAILED
    assert any("AG-04 Reliability Gate Failed" in v for v in report.violations)


def test_release_gate_verifier_catches_uncertified_platform():
    """Verify AG-05 failure when uncertified platforms are claimed."""
    report = ReleaseGateVerifier.audit_release_readiness(
        uncertified_platform_claimed=True,
    )
    assert report.all_passed is False
    assert report.gate_results["AG-05"] == GateStatus.FAILED
    assert any("AG-05 Platform Gate Failed" in v for v in report.violations)


def test_release_gate_verifier_catches_unredacted_secrets():
    """Verify AG-07 failure when unredacted secrets are detected."""
    report = ReleaseGateVerifier.audit_release_readiness(
        secrets_redacted=False,
    )
    assert report.all_passed is False
    assert report.gate_results["AG-07"] == GateStatus.FAILED
    assert any("AG-07 Evidence Gate Failed" in v for v in report.violations)


def test_release_gate_verifier_pending_human_review():
    """Verify AG-08 is PENDING_REVIEW when human has not confirmed review."""
    report = ReleaseGateVerifier.audit_release_readiness(
        human_reviewed=False,
    )
    assert report.all_passed is False
    assert report.gate_results["AG-08"] == GateStatus.PENDING_REVIEW
    assert any("AG-08 Human Review Gate Pending" in v for v in report.violations)
