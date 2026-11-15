"""Enforces user application exclusion rules to protect user workflows and developer setups."""

from __future__ import annotations

from typing import List, Optional, Tuple

from system_mind.applications.classifier import ApplicationOwnershipClassifier
from system_mind.applications.models import (
    ApplicationProfile,
    ApplicationType,
    ExclusionVerdict,
)
from system_mind.core.types import ActionContract, ComponentOwnership


class UserAppExclusionEnforcer:
    """Enforces deterministic exclusion of user-managed applications and environments."""

    EXCLUSION_RULES = {
        "EXCL-RULE-01": "USER_MANAGED ownership exclusion: All USER_MANAGED components are excluded from autonomous updates.",
        "EXCL-RULE-02": "Application bundle exclusion: Third-party GUI applications are excluded from autonomous OS updates.",
        "EXCL-RULE-03": "Project dependency exclusion: Local virtualenvs, node_modules, and build targets are excluded.",
        "EXCL-RULE-04": "Configuration and dotfile exclusion: User dotfiles and toolchain configs are excluded from modification.",
        "EXCL-RULE-05": "Browser and IDE exclusion: Interactive browsers and development environments cannot be mutated autonomously.",
    }

    @classmethod
    def evaluate_profile(cls, profile: ApplicationProfile) -> ExclusionVerdict:
        """Evaluate an ApplicationProfile against exclusion rules."""
        # Rule 3: Project Dependency
        if profile.app_type == ApplicationType.PROJECT_DEPENDENCY:
            return ExclusionVerdict(
                target_path_or_id=profile.app_id,
                is_excluded=True,
                ownership=profile.ownership,
                reason="Project dependencies and virtual environments are strictly isolated from system updates.",
                matching_rule="EXCL-RULE-03",
                override_permitted=False,
            )

        # Rule 4: Config / Dotfile
        if any(cf in profile.install_path for cf in (".zshrc", ".bashrc", ".gitconfig", ".config")):
            return ExclusionVerdict(
                target_path_or_id=profile.app_id,
                is_excluded=True,
                ownership=profile.ownership,
                reason="User configuration files and dotfiles are protected from automated alteration.",
                matching_rule="EXCL-RULE-04",
                override_permitted=False,
            )

        # Rule 1 & 2: User Desktop App / USER_MANAGED
        if profile.ownership == ComponentOwnership.USER_MANAGED:
            return ExclusionVerdict(
                target_path_or_id=profile.app_id,
                is_excluded=True,
                ownership=profile.ownership,
                reason=f"Application '{profile.display_name}' is user-managed and excluded from autonomous system maintenance.",
                matching_rule="EXCL-RULE-01",
                override_permitted=True,
            )

        # OS Core (Permitted for system maintenance)
        return ExclusionVerdict(
            target_path_or_id=profile.app_id,
            is_excluded=False,
            ownership=profile.ownership,
            reason="Component is part of the authoritative OS core and eligible for system maintenance.",
            matching_rule="SYSTEM_CORE_ELIGIBLE",
            override_permitted=True,
        )

    @classmethod
    def evaluate_path(cls, path: str) -> ExclusionVerdict:
        """Classify a path and evaluate exclusion."""
        profile = ApplicationOwnershipClassifier.classify_path(path)
        return cls.evaluate_profile(profile)

    @classmethod
    def evaluate_action_exclusion(cls, action: ActionContract) -> Tuple[bool, Optional[str]]:
        """Validate whether a planned ActionContract obeys the User-App Exclusion Model."""
        # 1. Path-based defense-in-depth classification
        path_profile = ApplicationOwnershipClassifier.classify_path(action.target_component)

        # 2. Prevent ownership spoofing (claiming a user app is SYSTEM_MANAGED)
        if path_profile.ownership == ComponentOwnership.USER_MANAGED and action.target_ownership != ComponentOwnership.USER_MANAGED:
            return False, (
                f"Component Ownership Spoofing Violation: Target '{action.target_component}' is classified as USER_MANAGED, "
                f"but contract claimed '{action.target_ownership.value}'. Modification is blocked."
            )

        # 3. Autonomous maintenance check on USER_MANAGED components
        is_user_managed = (
            action.target_ownership == ComponentOwnership.USER_MANAGED or
            path_profile.ownership == ComponentOwnership.USER_MANAGED
        )

        if is_user_managed and not action.user_approved:
            return False, (
                f"User-App Exclusion Violation: Target '{action.target_component}' is USER_MANAGED and excluded from autonomous "
                f"system maintenance. Explicit human approval (user_approved=True) is required."
            )

        return True, None
