"""Architecture package for SYSTEM MIND X: Layers, component boundaries, AI/native split, and baseline freeze."""

from system_mind.architecture.baseline import (
    ArchitectureBaselineAudit,
    ArchitectureBaselineManifest,
    ArchitectureBaselineRegistry,
    ArchitectureBaselineVerifier,
    ArchitectureComponentSpec,
    BaselineComponentId,
    FreezeStatus,
)
from system_mind.architecture.layers import (
    ArchitectureBoundaryEnforcer,
    ArchitectureLayerId,
    DataflowDirection,
    LayerSpecification,
    SevenLayerArchitectureRegistry,
)
from system_mind.architecture.split import (
    AiNativeSplitValidator,
    ArchitectureDecisionRecord,
    PrivilegeBoundary,
    SplitBoundaryRegistry,
    SystemPlaneId,
)

__all__ = [
    # 7-Layer system
    "ArchitectureLayerId",
    "DataflowDirection",
    "LayerSpecification",
    "SevenLayerArchitectureRegistry",
    "ArchitectureBoundaryEnforcer",
    # AI/Native system split
    "SystemPlaneId",
    "PrivilegeBoundary",
    "ArchitectureDecisionRecord",
    "SplitBoundaryRegistry",
    "AiNativeSplitValidator",
    # Architecture Baseline Freeze
    "BaselineComponentId",
    "FreezeStatus",
    "ArchitectureComponentSpec",
    "ArchitectureBaselineManifest",
    "ArchitectureBaselineAudit",
    "ArchitectureBaselineRegistry",
    "ArchitectureBaselineVerifier",
]
