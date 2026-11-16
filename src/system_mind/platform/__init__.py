"""Platform and hardware compatibility matrix and capability parity module for SYSTEM MIND X."""

from system_mind.platform.adapter import (
    FileProvenanceSnapshot,
    FsEventSnapshot,
    HardwareTelemetrySnapshot,
    MockPlatformAdapter,
    MockPlatformProfileFactory,
    PlatformAdapter,
    ProcessTelemetrySnapshot,
    RollbackResult,
    SecurityStateSnapshot,
    SnapshotResult,
    UpdateStageResult,
)
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
    "FileProvenanceSnapshot",
    "FsEventSnapshot",
    "HardwareSpec",
    "HardwareTelemetrySnapshot",
    "MockPlatformAdapter",
    "MockPlatformProfileFactory",
    "ParityEvaluationResult",
    "ParityLevel",
    "PlatformAdapter",
    "PlatformCapabilityDetail",
    "PlatformCapabilityUnsupportedError",
    "PlatformMatrixRegistry",
    "PlatformParitySpecification",
    "PlatformProfile",
    "PlatformTargetId",
    "ProcessTelemetrySnapshot",
    "RollbackResult",
    "SecurityStateSnapshot",
    "SnapshotResult",
    "UpdateStageResult",
]
