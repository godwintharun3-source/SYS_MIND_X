"""Architecture package for SYSTEM MIND X: Layers, component boundaries, and AI/native system split."""

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
]
