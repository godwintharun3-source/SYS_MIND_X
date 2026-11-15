"""Unit and contract tests for SYSTEM MIND X non-functional requirements and benchmarks."""

import pytest

from system_mind.nfr.benchmark import (
    NfrComplianceEvaluator,
    NfrEvaluationResult,
    NfrMeasurement,
)
from system_mind.nfr.models import (
    ComparisonOperator,
    MetricUnit,
    NfrCategory,
    NfrRegistry,
    NonFunctionalRequirement,
)


def test_nfr_registry_completeness():
    """Verify that all fifteen non-functional requirements are cataloged across all categories."""
    requirements = NfrRegistry.get_all()
    assert len(requirements) == 15

    categories_present = {req.category for req in requirements}
    for expected_cat in NfrCategory:
        assert expected_cat in categories_present, f"Category {expected_cat} missing from NFR registry"

    for req in requirements:
        assert req.nfr_id.startswith("NFR-"), f"Invalid NFR ID format: {req.nfr_id}"
        assert req.title.strip(), f"NFR {req.nfr_id} has empty title"
        assert req.description.strip(), f"NFR {req.nfr_id} has empty description"
        assert req.measurement_strategy.strip(), f"NFR {req.nfr_id} has empty measurement strategy"
        assert req.is_mandatory_gate is True


def test_nfr_registry_queries_and_filtering():
    """Verify registry filtering by category and lookup methods."""
    rel_reqs = NfrRegistry.filter_by_category(NfrCategory.RELIABILITY)
    assert len(rel_reqs) == 4
    for r in rel_reqs:
        assert r.category == NfrCategory.RELIABILITY

    priv_reqs = NfrRegistry.filter_by_category(NfrCategory.PRIVACY)
    assert len(priv_reqs) == 4

    perf_reqs = NfrRegistry.filter_by_category(NfrCategory.PERFORMANCE)
    assert len(perf_reqs) == 5

    safe_reqs = NfrRegistry.filter_by_category(NfrCategory.SAFETY)
    assert len(safe_reqs) == 2

    nfr1 = NfrRegistry.get("NFR-REL-01")
    assert nfr1.title == "Atomic Rollback Convergence Duration"
    assert nfr1.target_threshold == 5000.0

    with pytest.raises(KeyError):
        NfrRegistry.get("NFR-UNKNOWN-99")


def test_nfr_compliance_evaluator_all_compliant():
    """Verify that NfrComplianceEvaluator confirms compliance when all measurements meet target thresholds."""
    measurements = [
        # Reliability
        NfrMeasurement("NFR-REL-01", 1250.0, "Rollback converged in 1250ms"),
        NfrMeasurement("NFR-REL-02", 185.0, "Crash recovery in 185ms"),
        NfrMeasurement("NFR-REL-03", 99.995, "Availability at 99.995%"),
        NfrMeasurement("NFR-REL-04", 100.0, "100% pre/post assertion"),
        # Privacy
        NfrMeasurement("NFR-PRIV-01", 0.0, "Zero secrets in telemetry"),
        NfrMeasurement("NFR-PRIV-02", 0.0, "Zero screen OCR frame dumps"),
        NfrMeasurement("NFR-PRIV-03", 100.0, "100% offline local functionality"),
        NfrMeasurement("NFR-PRIV-04", 100.0, "100% cryptographic hash chain validity"),
        # Performance
        NfrMeasurement("NFR-PERF-01", 2.4, "P95 policy evaluation latency 2.4ms"),
        NfrMeasurement("NFR-PERF-02", 18.0, "Digital twin commit in 18.0ms"),
        NfrMeasurement("NFR-PERF-03", 38.5, "Agent RSS memory 38.5 MB"),
        NfrMeasurement("NFR-PERF-04", 0.22, "Average idle CPU 0.22%"),
        NfrMeasurement("NFR-PERF-05", 11.0, "Broker IPC roundtrip in 11.0ms"),
        # Safety
        NfrMeasurement("NFR-SAFE-01", 0.0, "Zero user-app modifications"),
        NfrMeasurement("NFR-SAFE-02", 100.0, "100% zero-trust containment"),
    ]

    result = NfrComplianceEvaluator.evaluate_suite(measurements)
    assert result.is_compliant is True
    assert result.total_evaluated == 15
    assert len(result.violations) == 0
    assert len(result.warnings) == 0
    for nfr_id, is_pass in result.evaluations.items():
        assert is_pass is True


def test_nfr_compliance_evaluator_catches_latency_breach():
    """Verify detection of performance latency threshold violation."""
    measurement = NfrMeasurement("NFR-PERF-01", 8.4, "Measured 8.4ms (exceeds 5.0ms threshold)")
    is_pass, err_msg = NfrComplianceEvaluator.evaluate_measurement(measurement)

    assert is_pass is False
    assert err_msg is not None
    assert "NFR-PERF-01" in err_msg
    assert "Measured 8.4 MILLISECONDS, but requirement is <= 5.0" in err_msg


def test_nfr_compliance_evaluator_catches_secret_leakage():
    """Verify detection of privacy breach (unredacted secret count > 0)."""
    measurement = NfrMeasurement("NFR-PRIV-01", 3.0, "Three cleartext secrets found in log")
    is_pass, err_msg = NfrComplianceEvaluator.evaluate_measurement(measurement)

    assert is_pass is False
    assert err_msg is not None
    assert "NFR-PRIV-01" in err_msg
    assert "Measured 3.0 COUNT, but requirement is == 0.0" in err_msg


def test_nfr_compliance_evaluator_catches_memory_ceiling_breach():
    """Verify detection of agent memory ceiling violation."""
    measurement = NfrMeasurement("NFR-PERF-03", 72.0, "Measured 72MB (exceeds 50MB ceiling)")
    is_pass, err_msg = NfrComplianceEvaluator.evaluate_measurement(measurement)

    assert is_pass is False
    assert err_msg is not None
    assert "NFR-PERF-03" in err_msg
    assert "Measured 72.0 MEGABYTES, but requirement is <= 50.0" in err_msg


def test_nfr_compliance_evaluator_warns_on_incomplete_suite():
    """Verify warning generated when mandatory NFR measurements are omitted from the suite."""
    partial_measurements = [
        NfrMeasurement("NFR-REL-01", 1200.0),
        NfrMeasurement("NFR-PRIV-01", 0.0),
    ]

    result = NfrComplianceEvaluator.evaluate_suite(partial_measurements)
    assert result.is_compliant is True  # Measured items passed
    assert result.total_evaluated == 2
    assert len(result.warnings) == 13  # 15 total - 2 measured = 13 missing
    assert any("NFR-PERF-01" in w for w in result.warnings)
