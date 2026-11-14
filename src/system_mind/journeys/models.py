"""Data contracts and schemas for SYSTEM MIND X user journeys and measurable outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.core.types import ActionContract
from system_mind.personas.models import PersonaType


class UserJourneyType(str, Enum):
    """Primary user journey workflows."""

    PROACTIVE_CARETAKER_REMEDIATION = "PROACTIVE_CARETAKER_REMEDIATION"
    ZERO_TRUST_FILE_CONTAINMENT = "ZERO_TRUST_FILE_CONTAINMENT"
    DEVELOPER_TOOLCHAIN_DIAGNOSIS = "DEVELOPER_TOOLCHAIN_DIAGNOSIS"
    AUTONOMOUS_OS_MAINTENANCE = "AUTONOMOUS_OS_MAINTENANCE"
    ENTERPRISE_COMPLIANCE_REMEDIATION = "ENTERPRISE_COMPLIANCE_REMEDIATION"


class StepStatus(str, Enum):
    """Execution status of an individual journey step."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class MeasurableOutcome:
    """Quantitative metric verifying journey success against acceptance criteria."""

    metric_name: str
    target_value: float
    actual_value: float
    unit: str
    passed: bool
    details: str = ""


@dataclass
class JourneyStep:
    """Discrete operational step within a user journey."""

    step_id: str
    name: str
    action: ActionContract
    status: StepStatus = StepStatus.PENDING
    compensation_action: Optional[ActionContract] = None
    execution_log: List[str] = field(default_factory=list)
    simulated_duration_seconds: float = 0.1
    force_failure: bool = False  # Used for testing rollback mechanics


@dataclass
class UserJourney:
    """End-to-end user journey specification and execution record."""

    journey_id: str
    journey_type: UserJourneyType
    target_persona: PersonaType
    title: str
    description: str
    steps: List[JourneyStep]
    outcomes: List[MeasurableOutcome] = field(default_factory=list)
    is_completed: bool = False
    has_failed: bool = False
    is_rolled_back: bool = False
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
