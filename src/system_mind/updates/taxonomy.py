"""Central registry cataloging system-update maintenance tiers and safety specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from system_mind.core.types import ComponentOwnership
from system_mind.platform.matrix import PlatformTargetId
from system_mind.updates.models import RebootRequirement, UpdateTier


@dataclass(frozen=True)
class UpdateTierSpecification:
    """Formal safety specification governing an update maintenance tier."""

    tier: UpdateTier
    display_name: str
    ownership: ComponentOwnership
    autonomous_eligible: bool
    reboot_requirement: RebootRequirement
    requires_snapshot: bool
    requires_ac_power: bool
    min_disk_space_bytes: int
    description: str


class SystemUpdateTaxonomyRegistry:
    """Central registry defining system-update taxonomy rules and maintenance tiers."""

    _TIERS: Dict[UpdateTier, UpdateTierSpecification] = {
        UpdateTier.OS_SECURITY_HOTFIX: UpdateTierSpecification(
            tier=UpdateTier.OS_SECURITY_HOTFIX,
            display_name="Operating System Security Hotfix",
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            autonomous_eligible=True,
            reboot_requirement=RebootRequirement.NO_REBOOT_REQUIRED,
            requires_snapshot=False,
            requires_ac_power=False,
            min_disk_space_bytes=500 * 1024 * 1024,  # 500 MB
            description="Rapid security definitions, XProtect, Defender signatures, and security database updates.",
        ),
        UpdateTier.SYSTEM_DAEMON_MAINTENANCE: UpdateTierSpecification(
            tier=UpdateTier.SYSTEM_DAEMON_MAINTENANCE,
            display_name="System Daemon Maintenance & Pruning",
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            autonomous_eligible=True,
            reboot_requirement=RebootRequirement.NO_REBOOT_REQUIRED,
            requires_snapshot=False,
            requires_ac_power=False,
            min_disk_space_bytes=100 * 1024 * 1024,  # 100 MB
            description="Log journal vacuuming, audit log rotation, and system-managed temporary file pruning.",
        ),
        UpdateTier.OS_CUMULATIVE_UPDATE: UpdateTierSpecification(
            tier=UpdateTier.OS_CUMULATIVE_UPDATE,
            display_name="Operating System Cumulative Update",
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            autonomous_eligible=False,  # Download/stage only, activation requires user consent
            reboot_requirement=RebootRequirement.STAGED_MAINTENANCE_REBOOT,
            requires_snapshot=True,
            requires_ac_power=True,
            min_disk_space_bytes=10 * 1024 * 1024 * 1024,  # 10 GB
            description="OS point releases, cumulative kernel security patches, and system volume updates.",
        ),
        UpdateTier.FIRMWARE_HARDWARE_UPDATE: UpdateTierSpecification(
            tier=UpdateTier.FIRMWARE_HARDWARE_UPDATE,
            display_name="Firmware & Hardware Component Update",
            ownership=ComponentOwnership.VENDOR_MANAGED,
            autonomous_eligible=False,
            reboot_requirement=RebootRequirement.IMMEDIATE_REBOOT_REQUIRED,
            requires_snapshot=True,
            requires_ac_power=True,
            min_disk_space_bytes=1 * 1024 * 1024 * 1024,  # 1 GB
            description="UEFI BIOS, Apple Silicon T2/SMC firmware, GPU VBIOS, and TPM microcode flashing.",
        ),
        UpdateTier.USER_APP_UPDATE: UpdateTierSpecification(
            tier=UpdateTier.USER_APP_UPDATE,
            display_name="User Application Update",
            ownership=ComponentOwnership.USER_MANAGED,
            autonomous_eligible=False,
            reboot_requirement=RebootRequirement.NO_REBOOT_REQUIRED,
            requires_snapshot=False,
            requires_ac_power=False,
            min_disk_space_bytes=1 * 1024 * 1024 * 1024,
            description="Third-party GUI desktop applications, browsers, and desktop utilities.",
        ),
        UpdateTier.PROJECT_DEPENDENCY_UPDATE: UpdateTierSpecification(
            tier=UpdateTier.PROJECT_DEPENDENCY_UPDATE,
            display_name="Project Dependency & Toolchain Update",
            ownership=ComponentOwnership.USER_MANAGED,
            autonomous_eligible=False,
            reboot_requirement=RebootRequirement.NO_REBOOT_REQUIRED,
            requires_snapshot=False,
            requires_ac_power=False,
            min_disk_space_bytes=500 * 1024 * 1024,
            description="Workspace package dependencies (pip, npm, cargo) and virtual environments.",
        ),
    }

    @classmethod
    def get_tier_spec(cls, tier: UpdateTier) -> UpdateTierSpecification:
        """Retrieve the specification for a given update tier."""
        if tier not in cls._TIERS:
            raise KeyError(f"Unknown update maintenance tier: '{tier}'")
        return cls._TIERS[tier]

    @classmethod
    def get_all_specs(cls) -> List[UpdateTierSpecification]:
        """Return all cataloged update tier specifications."""
        return list(cls._TIERS.values())
