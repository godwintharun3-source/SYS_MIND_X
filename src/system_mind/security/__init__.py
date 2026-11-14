"""Security package for SYSTEM MIND X: Threat modeling, trust boundaries, product non-goals, and safety constraints."""

from system_mind.security.safety_constraints import (
    ConstraintValidationResult,
    NonGoalCategory,
    NonGoalRegistry,
    ProductNonGoal,
    SafetyConstraint,
    SafetyConstraintCategory,
    SafetyConstraintRegistry,
    SafetyConstraintValidator,
)
from system_mind.security.threat_model import (
    StrideCategory,
    ThreatModelRegistry,
    ThreatSeverity,
    ThreatVector,
    TrustBoundaryEnforcer,
    TrustZone,
)

__all__ = [
    # Threat modeling & trust boundaries
    "TrustZone",
    "StrideCategory",
    "ThreatSeverity",
    "ThreatVector",
    "ThreatModelRegistry",
    "TrustBoundaryEnforcer",
    # Non-goals & explicit safety constraints
    "NonGoalCategory",
    "SafetyConstraintCategory",
    "ProductNonGoal",
    "SafetyConstraint",
    "ConstraintValidationResult",
    "NonGoalRegistry",
    "SafetyConstraintRegistry",
    "SafetyConstraintValidator",
]
