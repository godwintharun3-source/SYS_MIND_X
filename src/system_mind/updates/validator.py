"""Policy validator enforcing the System-Update Ownership Taxonomy and safety gates."""

from __future__ import annotations

from typing import List, Tuple

from system_mind.core.types import ComponentOwnership
from system_mind.updates.models import (
    SystemUpdateProposal,
    UpdatePreconditions,
    UpdateTier,
    UpdateValidationResult,
)
from system_mind.updates.taxonomy import SystemUpdateTaxonomyRegistry


class SystemUpdatePolicyValidator:
    """Validates update proposals against taxonomy rules, component ownership, and safety preconditions."""

    @classmethod
    def validate_proposal(
        cls,
        proposal: SystemUpdateProposal,
        preconditions: UpdatePreconditions,
        is_autonomous_caller: bool = False,
    ) -> UpdateValidationResult:
        """Validate whether an update proposal is permitted to execute under current preconditions."""
        violations: List[str] = []
        warnings: List[str] = []

        spec = SystemUpdateTaxonomyRegistry.get_tier_spec(proposal.tier)

        # 1. Autonomous Scope Invariant (Invariant 1)
        if is_autonomous_caller and not spec.autonomous_eligible:
            violations.append(
                f"Autonomous Scope Violation: Tier '{proposal.tier.value}' ({spec.display_name}) is strictly "
                f"excluded from autonomous unattended execution."
            )

        # 2. Cryptographic Vendor Signature Check (Invariant 4)
        if not proposal.package_signature_valid:
            violations.append(
                f"Untrusted Package Signature: Update '{proposal.update_id}' lacks a valid cryptographic vendor signature."
            )

        # 3. Mandatory Recovery Snapshot Precondition (Invariant 2)
        if spec.requires_snapshot or proposal.requires_snapshot:
            if not preconditions.snapshot_id or not preconditions.snapshot_id.strip():
                violations.append(
                    f"Snapshot Precondition Failure: Update tier '{proposal.tier.value}' requires an atomic filesystem "
                    f"recovery snapshot before execution."
                )

        # 4. Mandatory AC Power Precondition (Invariant 3)
        if spec.requires_ac_power or proposal.requires_ac_power:
            if not preconditions.is_ac_power_connected:
                violations.append(
                    f"Power Precondition Failure: Update tier '{proposal.tier.value}' requires AC power; "
                    f"execution on battery power is prohibited to prevent power-loss corruption."
                )

        # 5. Free Storage Buffer Check
        if preconditions.available_disk_space_bytes < spec.min_disk_space_bytes:
            req_gb = spec.min_disk_space_bytes / (1024**3)
            avail_gb = preconditions.available_disk_space_bytes / (1024**3)
            violations.append(
                f"Storage Precondition Failure: Requires at least {req_gb:.1f} GB free disk space, "
                f"but only {avail_gb:.1f} GB is available."
            )

        # 6. Explicit User Approval Requirement for Non-Autonomous Tiers
        if not spec.autonomous_eligible and not preconditions.user_approved:
            violations.append(
                f"User Approval Required: Update tier '{proposal.tier.value}' cannot proceed without explicit human consent (user_approved=True)."
            )

        # Warnings for staged reboots
        if spec.reboot_requirement.value != "NO_REBOOT_REQUIRED":
            warnings.append(
                f"Reboot Notice: Activation requires {spec.reboot_requirement.value}. Defer to user maintenance window."
            )

        permitted = (len(violations) == 0)
        return UpdateValidationResult(
            permitted=permitted,
            update_id=proposal.update_id,
            tier=proposal.tier,
            violations=violations,
            warnings=warnings,
        )
