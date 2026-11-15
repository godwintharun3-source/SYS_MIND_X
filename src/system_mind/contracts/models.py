"""Data models, enums, and typed predicate contracts for Preconditions and Postconditions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.core.types import (
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    PlatformTier,
    Reversibility,
)


class PreconditionType(str, Enum):
    """Categories of pre-execution readiness checks."""

    FILESYSTEM_PATH_STATE = "FILESYSTEM_PATH_STATE"
    STORAGE_CAPACITY = "STORAGE_CAPACITY"
    PROCESS_LIFECYCLE = "PROCESS_LIFECYCLE"
    POWER_AND_THERMAL = "POWER_AND_THERMAL"
    SNAPSHOT_RECOVERY = "SNAPSHOT_RECOVERY"
    DIGITAL_TWIN_FRESHNESS = "DIGITAL_TWIN_FRESHNESS"
    SECURITY_CLEARANCE = "SECURITY_CLEARANCE"


class PostconditionType(str, Enum):
    """Categories of post-execution state verifications."""

    FILESYSTEM_MUTATION = "FILESYSTEM_MUTATION"
    SERVICE_LIFECYCLE = "SERVICE_LIFECYCLE"
    PROCESS_STATE = "PROCESS_STATE"
    PACKAGE_STATE = "PACKAGE_STATE"
    AUDIT_RECEIPT = "AUDIT_RECEIPT"


class RollbackStrategy(str, Enum):
    """Automated compensation and rollback mechanisms."""

    SNAPSHOT_REVERT = "SNAPSHOT_REVERT"
    FILE_BACKUP_RESTORE = "FILE_BACKUP_RESTORE"
    SERVICE_STATE_RESTORE = "SERVICE_STATE_RESTORE"
    PACKAGE_DOWNGRADE = "PACKAGE_DOWNGRADE"
    NOOP_READ_ONLY = "NOOP_READ_ONLY"


class PredicateOperator(str, Enum):
    """Deterministic comparison operators for predicate evaluations."""

    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    IS_TRUE = "IS_TRUE"
    IS_FALSE = "IS_FALSE"
    CONTAINS = "CONTAINS"
    DOES_NOT_CONTAIN = "DOES_NOT_CONTAIN"


@dataclass(frozen=True)
class TypedPrecondition:
    """Strongly typed precondition predicate required prior to capability dispatch."""

    precondition_id: str
    precondition_type: PreconditionType
    target_field: str
    operator: PredicateOperator
    expected_value: Any
    description: str
    is_critical: bool = True


@dataclass(frozen=True)
class TypedPostcondition:
    """Strongly typed postcondition predicate evaluated immediately post-execution."""

    postcondition_id: str
    postcondition_type: PostconditionType
    target_field: str
    operator: PredicateOperator
    expected_value: Any
    description: str


@dataclass(frozen=True)
class RollbackContract:
    """Atomic recovery specification invoked upon postcondition verification failure."""

    strategy: RollbackStrategy
    target_reference: str
    timeout_seconds: int = 60
    requires_user_intervention: bool = False
    compensation_parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TypedActionContract:
    """Strongly typed, machine-verifiable action contract for Layer 6 Broker dispatch."""

    contract_id: str
    capability_id: str
    target_entity_id: str
    target_ownership: ComponentOwnership
    risk_tier: OperationRiskTier
    reversibility: Reversibility
    approval_requirement: ApprovalRequirement
    user_approved: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)
    preconditions: List[TypedPrecondition] = field(default_factory=list)
    postconditions: List[TypedPostcondition] = field(default_factory=list)
    rollback_contract: Optional[RollbackContract] = None
    target_platform: PlatformTier = PlatformTier.TIER_1_HOST_COMPANION
    contract_hash: str = field(default="", init=False)

    def __post_init__(self) -> None:
        """Compute SHA-256 hash of immutable contract specification."""
        spec = {
            "contract_id": self.contract_id,
            "capability_id": self.capability_id,
            "target_entity_id": self.target_entity_id,
            "target_ownership": self.target_ownership.value,
            "risk_tier": self.risk_tier.value,
            "reversibility": self.reversibility.value,
            "parameters": self.parameters,
        }
        raw = json.dumps(spec, sort_keys=True)
        self.contract_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class PreconditionEvaluationResult:
    """Outcome of evaluating all preconditions against observed state."""

    all_satisfied: bool
    evaluations: Dict[str, bool] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)


@dataclass
class PostconditionEvaluationResult:
    """Outcome of evaluating all postconditions against state after execution."""

    all_verified: bool
    evaluations: Dict[str, bool] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    triggers_rollback: bool = False
