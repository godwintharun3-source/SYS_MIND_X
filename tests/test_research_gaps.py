"""Tests for research-gap analysis and competitor comparison matrix."""

import pytest

from system_mind.research.gaps import (
    ComparisonDimension,
    CompetitorMatrixRegistry,
    CompetitorSystemId,
    ResearchGapAnalyzer,
    ResearchGapId,
    SupportGrade,
)


def test_competitor_matrix_completeness_and_dimensions():
    """Verify that all 7 competitor systems are evaluated across all 8 dimensions."""
    scorecards = CompetitorMatrixRegistry.get_all_competitors()
    assert len(scorecards) == 7

    required_dimensions = set(ComparisonDimension)
    assert len(required_dimensions) == 8

    for card in scorecards:
        assert card.name != ""
        assert card.vendor_or_project != ""
        assert card.summary_analysis != ""
        # Every system must have a score for every single dimension
        assert set(card.scores.keys()) == required_dimensions


def test_system_mind_achieves_full_native_coverage():
    """Verify SYSTEM MIND X achieves FULL_NATIVE across all 8 dimensions."""
    sm_card = CompetitorMatrixRegistry.get_scorecard(CompetitorSystemId.SYSTEM_MIND_X)
    for dim, grade in sm_card.scores.items():
        assert grade == SupportGrade.FULL_NATIVE, f"SYSTEM MIND X dimension '{dim}' was not FULL_NATIVE: {grade}"


def test_competitor_vulnerabilities_accurately_cataloged():
    """Verify known security and privacy anti-patterns in competitors are flagged."""
    # OpenInterpreter raw shell execution is flagged as DANGEROUS_UNRESTRICTED
    oi_card = CompetitorMatrixRegistry.get_scorecard(CompetitorSystemId.OPEN_INTERPRETER)
    assert oi_card.scores[ComparisonDimension.EXECUTION_SAFETY_BROKER] == SupportGrade.DANGEROUS_UNRESTRICTED
    assert oi_card.scores[ComparisonDimension.ZERO_TRUST_FILE_CONFINEMENT] == SupportGrade.DANGEROUS_UNRESTRICTED

    # Windows Recall unencrypted OCR screen capture is flagged as DANGEROUS_UNRESTRICTED
    recall_card = CompetitorMatrixRegistry.get_scorecard(CompetitorSystemId.WINDOWS_COPILOT_RECALL)
    assert recall_card.scores[ComparisonDimension.PRIVACY_PRESERVING_TELEMETRY] == SupportGrade.DANGEROUS_UNRESTRICTED

    # Anthropic Computer Use has no native rollback or temporal digital twin
    claude_card = CompetitorMatrixRegistry.get_scorecard(CompetitorSystemId.ANTHROPIC_COMPUTER_USE)
    assert claude_card.scores[ComparisonDimension.ATOMIC_STATE_ROLLBACK] == SupportGrade.ABSENT_UNSUPPORTED
    assert claude_card.scores[ComparisonDimension.TEMPORAL_DIGITAL_TWIN] == SupportGrade.ABSENT_UNSUPPORTED


def test_research_gaps_completeness():
    """Verify that all 5 industry research gaps are documented with concrete solutions."""
    gaps = CompetitorMatrixRegistry.get_all_gaps()
    assert len(gaps) == 5

    required_gaps = set(ResearchGapId)
    assert {g.gap_id for g in gaps} == required_gaps

    for gap in gaps:
        assert gap.title != ""
        assert gap.description != ""
        assert gap.industry_shortcoming != ""
        assert gap.system_mind_solution != ""
        assert gap.verification_strategy != ""


def test_dimension_ratings_query():
    """Verify querying ratings for a single dimension across all systems."""
    rollback_ratings = CompetitorMatrixRegistry.get_dimension_ratings(ComparisonDimension.ATOMIC_STATE_ROLLBACK)
    assert len(rollback_ratings) == 7
    assert rollback_ratings[CompetitorSystemId.SYSTEM_MIND_X] == SupportGrade.FULL_NATIVE
    assert rollback_ratings[CompetitorSystemId.ANTHROPIC_COMPUTER_USE] == SupportGrade.ABSENT_UNSUPPORTED
    assert rollback_ratings[CompetitorSystemId.OPEN_INTERPRETER] == SupportGrade.ABSENT_UNSUPPORTED


def test_research_gap_analyzer_audit():
    """Verify ResearchGapAnalyzer audits and confirms SYSTEM MIND X competitive lead."""
    audit_results = ResearchGapAnalyzer.verify_system_mind_competitor_lead()
    assert audit_results["system_mind_full_native_coverage"] is True
    assert audit_results["research_gaps_addressed"] is True
    assert audit_results["dangerous_shell_flagged"] is True
    assert audit_results["privacy_leak_flagged"] is True


def test_invalid_queries_raise_keyerror():
    """Verify querying non-existent competitor or gap raises KeyError."""
    with pytest.raises(KeyError):
        CompetitorMatrixRegistry.get_scorecard("NON_EXISTENT_SYSTEM")  # type: ignore

    with pytest.raises(KeyError):
        CompetitorMatrixRegistry.get_gap("NON_EXISTENT_GAP")  # type: ignore
