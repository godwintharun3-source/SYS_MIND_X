"""Deterministic validation and predicate rule evaluation engine for Action Contracts."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from system_mind.contracts.models import (
    PostconditionEvaluationResult,
    PredicateOperator,
    PreconditionEvaluationResult,
    RollbackStrategy,
    TypedActionContract,
    TypedPostcondition,
    TypedPrecondition,
)
from system_mind.core.types import (
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
    ValidationResult,
)


class ActionContractValidator:
    """Validates Action Contract structure, parameter safety, and invariant rules."""

    # Shell injection and meta-character patterns
    _INJECTION_PATTERN = re.compile(r"(\||;|&&|\|\||`|\$\(|\brm\s+-rf\b|\bsudo\b|\bbash\s+-c\b|\bsh\s+-c\b)")

    @classmethod
    def sanitize_parameters(cls, parameters: Dict[str, Any]) -> List[str]:
        """Scan parameter dictionary for shell metacharacters and command injection attempts."""
        violations: List[str] = []
        for key, val in parameters.items():
            if isinstance(val, str):
                if cls._INJECTION_PATTERN.search(val):
                    violations.append(
                        f"ParameterSanitizationViolation: Parameter '{key}' contains forbidden shell "
                        f"metacharacters or dangerous commands: '{val}'"
                    )
            elif isinstance(val, dict):
                violations.extend(cls.sanitize_parameters(val))
            elif isinstance(val, list):
                for idx, item in enumerate(val):
                    if isinstance(item, str) and cls._INJECTION_PATTERN.search(item):
                        violations.append(
                            f"ParameterSanitizationViolation: Parameter '{key}[{idx}]' contains forbidden shell "
                            f"metacharacters: '{item}'"
                        )
        return violations

    @classmethod
    def validate_contract(cls, contract: TypedActionContract) -> ValidationResult:
        """Validate TypedActionContract against machine-enforceable safety invariants."""
        violations: List[str] = []
        warnings: List[str] = []

        # 1. Parameter sanitization (Zero Shell Injection)
        violations.extend(cls.sanitize_parameters(contract.parameters))

        # 2. Consequential operations must specify typed preconditions and postconditions
        is_consequential = contract.risk_tier in {
            OperationRiskTier.MEDIUM_IMPACT,
            OperationRiskTier.HIGH_IMPACT,
            OperationRiskTier.CRITICAL_PRIVILEGED,
        }
        if is_consequential:
            if not contract.preconditions:
                violations.append(
                    f"PreconditionMissingViolation: Consequential operation '{contract.contract_id}' "
                    f"of risk tier {contract.risk_tier.value} mandates at least one typed precondition."
                )
            if not contract.postconditions:
                violations.append(
                    f"PostconditionMissingViolation: Consequential operation '{contract.contract_id}' "
                    f"of risk tier {contract.risk_tier.value} mandates at least one typed postcondition."
                )

        # 3. Mandatory Rollback Strategy for High & Critical Privileged Operations
        if contract.risk_tier in {OperationRiskTier.HIGH_IMPACT, OperationRiskTier.CRITICAL_PRIVILEGED}:
            if not contract.rollback_contract:
                violations.append(
                    f"RollbackContractMissingViolation: High impact/critical operation '{contract.contract_id}' "
                    "mandates an executable RollbackContract."
                )
            elif contract.rollback_contract.strategy == RollbackStrategy.NOOP_READ_ONLY:
                violations.append(
                    f"InvalidRollbackStrategyViolation: Operation '{contract.contract_id}' of risk tier "
                    f"{contract.risk_tier.value} cannot use NOOP_READ_ONLY rollback strategy."
                )

        # 4. User-Managed Component Protection (Tripartite Ownership Rule)
        if contract.target_ownership == ComponentOwnership.USER_MANAGED and not contract.user_approved:
            violations.append(
                f"UserManagedOwnershipViolation: Mutating operation on USER_MANAGED component "
                f"'{contract.target_entity_id}' strictly mandates explicit user approval (user_approved=True)."
            )

        # 5. Critical Privileged Approval Enforcement
        if contract.risk_tier == OperationRiskTier.CRITICAL_PRIVILEGED:
            if contract.approval_requirement == ApprovalRequirement.NONE:
                violations.append(
                    f"ApprovalRequirementViolation: Critical privileged contract '{contract.contract_id}' "
                    "cannot have ApprovalRequirement.NONE."
                )
            if not contract.user_approved:
                violations.append(
                    f"UserApprovalMandatoryViolation: Critical privileged contract '{contract.contract_id}' "
                    "mandates confirmed user approval before broker dispatch."
                )

        # 6. Unsupported Platform Rejection
        if contract.target_platform == PlatformTier.UNSUPPORTED:
            violations.append(
                f"UnsupportedPlatformViolation: Contract target platform is {contract.target_platform.value}."
            )

        # 7. Irreversible Action Confirmation
        if contract.reversibility == Reversibility.IRREVERSIBLE:
            if not contract.user_approved:
                violations.append(
                    f"IrreversibleActionApprovalViolation: Irreversible contract '{contract.contract_id}' "
                    "requires explicit user approval."
                )
            else:
                warnings.append(
                    f"IrreversibleActionWarning: Contract '{contract.contract_id}' cannot be automatically rolled back."
                )

        return ValidationResult(
            is_valid=(len(violations) == 0),
            violations=violations,
            warnings=warnings,
        )


class ContractRuleEvaluator:
    """Evaluates typed preconditions and postconditions against observed environment state."""

    @classmethod
    def evaluate_predicate(cls, operator: PredicateOperator, actual: Any, expected: Any) -> bool:
        """Deterministically evaluate an operand pair under the specified predicate operator."""
        if operator == PredicateOperator.EQUALS:
            return actual == expected
        if operator == PredicateOperator.NOT_EQUALS:
            return actual != expected
        if operator == PredicateOperator.GREATER_THAN_OR_EQUAL:
            return actual >= expected
        if operator == PredicateOperator.LESS_THAN_OR_EQUAL:
            return actual <= expected
        if operator == PredicateOperator.IS_TRUE:
            return bool(actual) is True
        if operator == PredicateOperator.IS_FALSE:
            return bool(actual) is False
        if operator == PredicateOperator.CONTAINS:
            return expected in actual
        if operator == PredicateOperator.DOES_NOT_CONTAIN:
            return expected not in actual
        return False

    @classmethod
    def evaluate_preconditions(
        cls,
        contract: TypedActionContract,
        system_state: Dict[str, Any],
    ) -> PreconditionEvaluationResult:
        """Evaluate all typed preconditions of a contract against observed system state."""
        evaluations: Dict[str, bool] = {}
        failures: List[str] = []

        for pre in contract.preconditions:
            if pre.target_field not in system_state:
                evaluations[pre.precondition_id] = False
                failures.append(
                    f"PreconditionMissingState: Target field '{pre.target_field}' required by "
                    f"precondition '{pre.precondition_id}' ({pre.precondition_type.value}) is missing from system state."
                )
                continue

            actual_val = system_state[pre.target_field]
            try:
                satisfied = cls.evaluate_predicate(pre.operator, actual_val, pre.expected_value)
            except Exception as e:
                satisfied = False

            evaluations[pre.precondition_id] = satisfied
            if not satisfied:
                failures.append(
                    f"PreconditionFailed: Precondition '{pre.precondition_id}' ({pre.description}) failed. "
                    f"Field '{pre.target_field}' expected {pre.operator.value} {pre.expected_value}, got {actual_val}."
                )

        return PreconditionEvaluationResult(
            all_satisfied=(len(failures) == 0),
            evaluations=evaluations,
            failures=failures,
        )

    @classmethod
    def evaluate_postconditions(
        cls,
        contract: TypedActionContract,
        post_execution_state: Dict[str, Any],
    ) -> PostconditionEvaluationResult:
        """Evaluate all typed postconditions post-execution; triggers rollback if any fail."""
        evaluations: Dict[str, bool] = {}
        failures: List[str] = []

        for post in contract.postconditions:
            if post.target_field not in post_execution_state:
                evaluations[post.postcondition_id] = False
                failures.append(
                    f"PostconditionMissingState: Post-execution field '{post.target_field}' required by "
                    f"postcondition '{post.postcondition_id}' ({post.postcondition_type.value}) is missing."
                )
                continue

            actual_val = post_execution_state[post.target_field]
            try:
                verified = cls.evaluate_predicate(post.operator, actual_val, post.expected_value)
            except Exception as e:
                verified = False

            evaluations[post.postcondition_id] = verified
            if not verified:
                failures.append(
                    f"PostconditionFailed: Postcondition '{post.postcondition_id}' ({post.description}) failed. "
                    f"Field '{post.target_field}' expected {post.operator.value} {post.expected_value}, got {actual_val}."
                )

        all_verified = len(failures) == 0
        triggers_rollback = not all_verified and contract.rollback_contract is not None

        return PostconditionEvaluationResult(
            all_verified=all_verified,
            evaluations=evaluations,
            failures=failures,
            triggers_rollback=triggers_rollback,
        )
