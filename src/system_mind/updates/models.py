"""Domain models and data contracts for the system-update ownership taxonomy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from system_mind.core.types import ComponentOwnership


class UpdateTier(str, Enum):
    """Maintenance tiers governing update safety, execution authority, and reboot rules."""

    OS_SECURITY_HOTFIX = "OS_SECURITY_HOTFIX"
    SYSTEM_DAEMON_MAINTENANCE = "SYSTEM_DAEMON_MAINTENANCE"
    OS_CUMULATIVE_UPDATE = "OS_CUMULATIVE_UPDATE"
    FIRMWARE_HARDWARE_UPDATE = "FIRMWARE_HARDWARE_UPDATE"
    USER_APP_UPDATE = "USER_APP_UPDATE"
    PROJECT_DEPENDENCY_UPDATE = "PROJECT_DEPENDENCY_UPDATE"


class UpdateLifecycleState(str, Enum):
    """Lifecycle progression states of a system update proposal."""

    DISCOVERED = "DISCOVERED"
    VERIFIED_SIGNATURE = "VERIFIED_SIGNATURE"
    PRECONDITIONS_CONFIRMED = "PRECONDITIONS_CONFIRMED"
    STAGED = "STAGED"
    APPLIED = "APPLIED"
    ROLLED_BACK = "ROLLED_BACK"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class RebootRequirement(str, Enum):
    """Reboot classification for update activation."""

    NO_REBOOT_REQUIRED = "NO_REBOOT_REQUIRED"
    STAGED_MAINTENANCE_REBOOT = "STAGED_MAINTENANCE_REBOOT"
    IMMEDIATE_REBOOT_REQUIRED = "IMMEDIATE_REBOOT_REQUIRED"


@dataclass(frozen=True)
class UpdatePreconditions:
    """Live environment preconditions required before update execution."""

    snapshot_id: Optional[str] = None
    is_ac_power_connected: bool = True
    available_disk_space_bytes: int = 20 * 1024 * 1024 * 1024  # 20 GB
    user_approved: bool = False


@dataclass(frozen=True)
class SystemUpdateProposal:
    """Formal proposal describing a planned software or firmware update."""

    update_id: str
    title: str
    tier: UpdateTier
    ownership: ComponentOwnership
    vendor_name: str
    package_signature_valid: bool
    reboot_requirement: RebootRequirement
    requires_snapshot: bool
    requires_ac_power: bool
    min_disk_space_bytes: int
    target_components: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpdateValidationResult:
    """Outcome of validating a system update proposal against taxonomy policy rules."""

    permitted: bool
    update_id: str
    tier: UpdateTier
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
