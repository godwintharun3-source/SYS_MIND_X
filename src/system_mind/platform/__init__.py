"""Platform and hardware compatibility matrix and capability parity module for SYSTEM MIND X."""

from system_mind.platform.matrix import (
    HardwareSpec,
    PlatformCapabilityDetail,
    PlatformMatrixRegistry,
    PlatformProfile,
    PlatformTargetId,
)
from system_mind.platform.parity import (
    CapabilityDomain,
    CapabilityParityEvaluator,
    CapabilityParityRegistry,
    ParityEvaluationResult,
    ParityLevel,
    PlatformCapabilityUnsupportedError,
    PlatformParitySpecification,
)

__all__ = [
    "CapabilityDomain",
    "CapabilityParityEvaluator",
    "CapabilityParityRegistry",
    "HardwareSpec",
    "ParityEvaluationResult",
    "ParityLevel",
    "PlatformCapabilityDetail",
    "PlatformCapabilityUnsupportedError",
    "PlatformMatrixRegistry",
    "PlatformParitySpecification",
    "PlatformProfile",
    "PlatformTargetId",
]
