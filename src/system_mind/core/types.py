"""Typed action contracts, ownership classes, risk tiers, and capability contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ComponentOwnership(str, Enum):
    """Classification of system components to enforce maintenance boundaries."""

    SYSTEM_MANAGED = "SYSTEM_MANAGED"
    VENDOR_MANAGED = "VENDOR_MANAGED"
    USER_MANAGED = "USER_MANAGED"


class OperationRiskTier(str, Enum):
    """Risk tiers for system operations."""

    READ_ONLY = "READ_ONLY"
    LOW_IMPACT = "LOW_IMPACT"
    MEDIUM_IMPACT = "MEDIUM_IMPACT"
    HIGH_IMPACT = "HIGH_IMPACT"
    CRITICAL_PRIVILEGED = "CRITICAL_PRIVILEGED"


class Reversibility(str, Enum):
    """Degree of automated rollback capability."""

    REVERSIBLE = "REVERSIBLE"
    PARTIALLY_REVERSIBLE = "PARTIALLY_REVERSIBLE"
    IRREVERSIBLE = "IRREVERSIBLE"


class PlatformTier(str, Enum):
    """First-release platform classification tiers."""

    TIER_1_HOST_COMPANION = "macOS Apple Silicon (M1/M2/M3)"
    TIER_2_WINDOWS = "Windows 11 x64"
    TIER_2_UBUNTU = "Ubuntu LTS x86_64"
    TIER_3_NIXOS_VM = "NixOS x86_64/ARM64 (VM Prototype)"
    UNSUPPORTED = "Unsupported Platform"


class CapabilityStatus(str, Enum):
    """State of capability verification."""

    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    MOCK_ONLY = "MOCK_ONLY"


class ApprovalRequirement(str, Enum):
    """Approval gate requirement."""

    NONE = "NONE"
    USER_EXPLICIT = "USER_EXPLICIT"
    TWO_PERSON_OR_BREAK_GLASS = "TWO_PERSON_OR_BREAK_GLASS"


class FileExecutionContainment(str, Enum):
    """Execution containment modes for file execution."""

    DENIED = "DENIED"
    HARDENED_VIEWER = "HARDENED_VIEWER"
    DISPOSABLE_ISOLATION = "DISPOSABLE_ISOLATION"
    NATIVE_HOST_TRUSTED = "NATIVE_HOST_TRUSTED"


@dataclass
class ActionContract:
    """Typed action contract for broker execution."""

    action_id: str
    action_type: str
    target_component: str
    target_ownership: ComponentOwnership
    risk_tier: OperationRiskTier
    reversibility: Reversibility
    approval_requirement: ApprovalRequirement
    user_approved: bool = False
    requires_root: bool = False
    target_platform: PlatformTier = PlatformTier.TIER_1_HOST_COMPANION
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    rollback_plan: Optional[str] = None
    file_containment: Optional[FileExecutionContainment] = None
    is_autonomous_maintenance: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Outcome of deterministic policy and charter validation."""

    is_valid: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class HostEnvironmentReport:
    """Read-only inspection report of the host platform."""

    os_name: str
    os_version: str
    kernel_version: str
    architecture: str
    cpu_brand: str
    cpu_cores: int
    memory_bytes: int
    sip_enabled: Optional[bool]
    gatekeeper_enabled: Optional[bool]
    platform_tier: PlatformTier
    installed_tools: Dict[str, Optional[str]] = field(default_factory=dict)
    is_supported_host: bool = False
    notes: List[str] = field(default_factory=list)
