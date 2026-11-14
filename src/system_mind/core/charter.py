"""Deterministic Charter Rule Enforcer and Action Contract Invariant Validator."""

from __future__ import annotations

from typing import List, Optional

from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    FileExecutionContainment,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
    ValidationResult,
)


class CharterViolationError(Exception):
    """Raised when an operation breaches non-negotiable charter safety constraints."""

    def __init__(self, message: str, violations: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.violations = violations or [message]


class CharterValidator:
    """Evaluates ActionContracts against non-negotiable safety and governance invariants."""

    # High impact action types requiring strict approval and rollback plans
    CRITICAL_ACTION_TYPES = {
        "firmware_update",
        "bootloader_modify",
        "partition_modify",
        "firewall_reconfigure",
        "security_policy_change",
        "major_os_upgrade",
    }

    @classmethod
    def validate(cls, action: ActionContract) -> ValidationResult:
        """Validate an action contract against core charter invariants.

        Returns ValidationResult with is_valid=True if all invariants hold,
        or is_valid=False with a list of specific charter violations.
        """
        violations: List[str] = []
        warnings: List[str] = []

        # Invariant 1: No Unrestricted Raw Shell / Sudo Execution
        if action.action_type in {"raw_shell_execution", "unrestricted_root_shell", "sudo_exec"}:
            violations.append(
                "Violation: Unrestricted root or raw shell execution by the AI control plane is strictly forbidden."
            )

        # Invariant 2: Autonomous Maintenance Exclusion of User/Vendor Components
        if action.is_autonomous_maintenance:
            if action.target_ownership == ComponentOwnership.USER_MANAGED:
                violations.append(
                    f"Violation: Autonomous maintenance engine cannot modify USER_MANAGED component '{action.target_component}'. User applications, project dependencies, and IDEs must never be automatically updated."
                )
            elif action.target_ownership == ComponentOwnership.VENDOR_MANAGED:
                violations.append(
                    f"Violation: Autonomous maintenance engine cannot modify VENDOR_MANAGED component '{action.target_component}'. Vendor/OEM updates require explicit user confirmation."
                )

        # Invariant 3: Zero-Trust File Execution
        if action.action_type == "file_execute":
            if action.file_containment in (None, FileExecutionContainment.DENIED):
                violations.append(
                    "Violation: File execution requires an approved containment strategy (HARDENED_VIEWER, DISPOSABLE_ISOLATION, or verified NATIVE_HOST_TRUSTED)."
                )
            elif action.file_containment == FileExecutionContainment.NATIVE_HOST_TRUSTED:
                provenance_verified = action.metadata.get("provenance_verified", False)
                if not provenance_verified:
                    violations.append(
                        "Violation: Native host execution requires cryptographically verified provenance and trust signatures. Unknown or untrusted files cannot run on the host."
                    )

        # Invariant 4: Critical Privileged Actions Require Explicit User Approval & Rollback Plan
        is_critical = (
            action.risk_tier == OperationRiskTier.CRITICAL_PRIVILEGED
            or action.action_type in cls.CRITICAL_ACTION_TYPES
        )
        if is_critical:
            if action.approval_requirement == ApprovalRequirement.NONE:
                violations.append(
                    "Violation: Critical privileged operations (firmware, bootloader, partition, firewall, security policy) require explicit user approval."
                )
            if not action.user_approved:
                violations.append(
                    "Violation: Action cannot proceed without confirmed user approval."
                )
            if not action.rollback_plan or not action.rollback_plan.strip():
                violations.append(
                    "Violation: Critical privileged operations require a documented, verified recovery/rollback strategy."
                )

        # Invariant 5: Consequential Actions Require Preconditions and Postconditions
        if action.risk_tier in (
            OperationRiskTier.MEDIUM_IMPACT,
            OperationRiskTier.HIGH_IMPACT,
            OperationRiskTier.CRITICAL_PRIVILEGED,
        ):
            if not action.preconditions:
                violations.append(
                    "Violation: Consequential operations require explicit preconditions."
                )
            if not action.postconditions:
                violations.append(
                    "Violation: Consequential operations require explicit postconditions for verification."
                )

        # Invariant 6: Unsupported Platform Policy
        if action.target_platform == PlatformTier.UNSUPPORTED:
            violations.append(
                "Violation: Target platform is outside the supported first-release matrix."
            )

        # Invariant 7: Irreversible Operations Warning / Escalation
        if action.reversibility == Reversibility.IRREVERSIBLE:
            if not action.user_approved:
                violations.append(
                    "Violation: Irreversible state transitions require explicit user confirmation."
                )
            else:
                warnings.append(
                    "Caution: Operation is irreversible; state cannot be automatically recovered."
                )

        return ValidationResult(
            is_valid=(len(violations) == 0),
            violations=violations,
            warnings=warnings,
        )

    @classmethod
    def assert_valid(cls, action: ActionContract) -> None:
        """Enforces validation, raising CharterViolationError on any violation."""
        res = cls.validate(action)
        if not res.is_valid:
            msg = f"Charter violation in action '{action.action_id}': " + "; ".join(res.violations)
            raise CharterViolationError(msg, violations=res.violations)
