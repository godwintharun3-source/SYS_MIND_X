"""Compliance evaluation and measurement benchmarking for non-functional requirements."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from system_mind.nfr.models import (
    ComparisonOperator,
    MetricUnit,
    NfrCategory,
    NfrRegistry,
    NonFunctionalRequirement,
)


@dataclass(frozen=True)
class NfrMeasurement:
    """A verified quantitative benchmark measurement corresponding to an NFR."""

    nfr_id: str
    measured_value: float
    notes: str = ""


@dataclass
class NfrEvaluationResult:
    """Consolidated compliance report across evaluated NFR measurements."""

    is_compliant: bool
    total_evaluated: int
    evaluations: Dict[str, bool] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class NfrComplianceEvaluator:
    """Evaluates benchmark measurements against established NFR target thresholds."""

    _EPSILON = 1e-6

    @classmethod
    def evaluate_measurement(cls, measurement: NfrMeasurement) -> Tuple[bool, Optional[str]]:
        """Evaluate a single measurement against its registered NFR definition."""
        try:
            nfr = NfrRegistry.get(measurement.nfr_id)
        except KeyError as e:
            return False, f"Evaluation Error: Unknown requirement '{measurement.nfr_id}'."

        passed = False
        target = nfr.target_threshold
        val = measurement.measured_value

        if nfr.operator == ComparisonOperator.LESS_THAN_OR_EQUAL:
            passed = val <= (target + cls._EPSILON)
        elif nfr.operator == ComparisonOperator.GREATER_THAN_OR_EQUAL:
            passed = val >= (target - cls._EPSILON)
        elif nfr.operator == ComparisonOperator.EQUALS:
            passed = math.isclose(val, target, abs_tol=cls._EPSILON)

        if passed:
            return True, None

        violation_msg = (
            f"NFR Non-Compliance [{nfr.nfr_id} - {nfr.title}]: "
            f"Measured {val} {nfr.metric_unit.value}, but requirement is {nfr.operator.value} {target} {nfr.metric_unit.value}."
        )
        return False, violation_msg

    @classmethod
    def evaluate_suite(cls, measurements: List[NfrMeasurement]) -> NfrEvaluationResult:
        """Evaluate a full suite of NFR benchmark measurements."""
        evaluations: Dict[str, bool] = {}
        violations: List[str] = []
        warnings: List[str] = []

        measured_ids = {m.nfr_id for m in measurements}
        for measurement in measurements:
            is_pass, err_msg = cls.evaluate_measurement(measurement)
            evaluations[measurement.nfr_id] = is_pass
            if not is_pass and err_msg:
                violations.append(err_msg)

        # Check for missing mandatory NFR measurements
        for mandatory_nfr in NfrRegistry.get_mandatory_nfrs():
            if mandatory_nfr.nfr_id not in measured_ids:
                warnings.append(
                    f"Incomplete Suite: Mandatory requirement '{mandatory_nfr.nfr_id}' has not been measured in this benchmark."
                )

        is_compliant = (len(violations) == 0 and len(evaluations) > 0 and all(evaluations.values()))
        return NfrEvaluationResult(
            is_compliant=is_compliant,
            total_evaluated=len(evaluations),
            evaluations=evaluations,
            violations=violations,
            warnings=warnings,
        )
