"""Unit and contract tests for application ownership classification and user-app exclusion."""

import pytest

from system_mind.applications import (
    ApplicationOwnershipClassifier,
    ApplicationProfile,
    ApplicationType,
    ExclusionVerdict,
    InstallScope,
    UserAppExclusionEnforcer,
)
from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    Reversibility,
)


def test_application_types_and_models():
    """Verify application types and installation scope enums."""
    assert len(ApplicationType) == 6
    assert len(InstallScope) == 3

    profile = ApplicationProfile(
        app_id="com.example.App",
        display_name="Example App",
        app_type=ApplicationType.USER_DESKTOP_APP,
        install_scope=InstallScope.SYSTEM_WIDE,
        install_path="/Applications/Example.app",
        executable_path="/Applications/Example.app/Contents/MacOS/Example",
        ownership=ComponentOwnership.USER_MANAGED,
        managed_by="installer",
    )
    assert profile.is_excluded_from_autonomous_updates is True


def test_classifier_categorizes_user_desktop_apps():
    """Verify classification of third-party desktop applications across macOS, Windows, and Linux."""
    # macOS user app
    mac_app = ApplicationOwnershipClassifier.classify_path("/Applications/Google Chrome.app")
    assert mac_app.ownership == ComponentOwnership.USER_MANAGED
    assert mac_app.app_type == ApplicationType.USER_DESKTOP_APP
    assert mac_app.is_excluded_from_autonomous_updates is True

    # Windows user app
    win_app = ApplicationOwnershipClassifier.classify_path("C:\\Program Files\\Google\\Chrome\\chrome.exe")
    assert win_app.ownership == ComponentOwnership.USER_MANAGED
    assert win_app.app_type == ApplicationType.USER_DESKTOP_APP

    # Linux user local app
    linux_app = ApplicationOwnershipClassifier.classify_path("~/.local/share/applications/discord.desktop")
    assert linux_app.ownership == ComponentOwnership.USER_MANAGED


def test_classifier_categorizes_project_dependencies():
    """Verify classification of virtual environments, node_modules, and build artifacts."""
    venv_path = "/Users/dev/workspace/.venv/lib/python3.12/site-packages"
    venv_profile = ApplicationOwnershipClassifier.classify_path(venv_path)
    assert venv_profile.ownership == ComponentOwnership.USER_MANAGED
    assert venv_profile.app_type == ApplicationType.PROJECT_DEPENDENCY
    assert venv_profile.install_scope == InstallScope.PROJECT_LOCAL

    node_path = "/Users/dev/project/node_modules/express"
    node_profile = ApplicationOwnershipClassifier.classify_path(node_path)
    assert node_profile.ownership == ComponentOwnership.USER_MANAGED
    assert node_profile.app_type == ApplicationType.PROJECT_DEPENDENCY


def test_classifier_categorizes_developer_configs():
    """Verify classification of user configuration files and dotfiles."""
    zshrc_profile = ApplicationOwnershipClassifier.classify_path("~/.zshrc")
    assert zshrc_profile.ownership == ComponentOwnership.USER_MANAGED
    assert zshrc_profile.app_type == ApplicationType.DEVELOPER_TOOLCHAIN

    gitconfig_profile = ApplicationOwnershipClassifier.classify_path("~/.gitconfig")
    assert gitconfig_profile.ownership == ComponentOwnership.USER_MANAGED


def test_classifier_categorizes_system_core_os():
    """Verify classification of authoritative OS core utilities."""
    # macOS system volume
    mac_core = ApplicationOwnershipClassifier.classify_path("/System/Library/CoreServices/launchd")
    assert mac_core.ownership == ComponentOwnership.SYSTEM_MANAGED
    assert mac_core.app_type == ApplicationType.SYSTEM_CORE
    assert mac_core.is_excluded_from_autonomous_updates is False

    # Windows system core
    win_core = ApplicationOwnershipClassifier.classify_path("C:\\Windows\\System32\\ntoskrnl.exe")
    assert win_core.ownership == ComponentOwnership.SYSTEM_MANAGED
    assert win_core.app_type == ApplicationType.SYSTEM_CORE


def test_exclusion_enforcer_verdicts():
    """Verify exclusion verdict determination for applications, dependencies, and OS components."""
    # 1. User app excluded
    verdict_app = UserAppExclusionEnforcer.evaluate_path("/Applications/Slack.app")
    assert verdict_app.is_excluded is True
    assert verdict_app.matching_rule == "EXCL-RULE-01"

    # 2. Project dependency excluded
    verdict_dep = UserAppExclusionEnforcer.evaluate_path("/home/user/code/venv/bin/activate")
    assert verdict_dep.is_excluded is True
    assert verdict_dep.matching_rule == "EXCL-RULE-03"

    # 3. OS Core eligible for maintenance
    verdict_core = UserAppExclusionEnforcer.evaluate_path("/System/Applications/Utilities/Terminal.app")
    assert verdict_core.is_excluded is False
    assert verdict_core.matching_rule == "SYSTEM_CORE_ELIGIBLE"


def test_exclusion_enforcer_blocks_autonomous_maintenance_of_user_apps():
    """Verify that action contracts attempting autonomous maintenance of user apps are blocked."""
    # Action attempting autonomous update of Google Chrome without user approval
    autonomous_action = ActionContract(
        action_id="act-update-chrome",
        action_type="upgrade_package",
        target_component="/Applications/Google Chrome.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=False,
    )

    allowed, err = UserAppExclusionEnforcer.evaluate_action_exclusion(autonomous_action)
    assert allowed is False
    assert "User-App Exclusion Violation" in err
    assert "Explicit human approval" in err

    # With user_approved=True, update is allowed
    approved_action = ActionContract(
        action_id="act-update-chrome-approved",
        action_type="upgrade_package",
        target_component="/Applications/Google Chrome.app",
        target_ownership=ComponentOwnership.USER_MANAGED,
        risk_tier=OperationRiskTier.MEDIUM_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.USER_EXPLICIT,
        user_approved=True,
    )
    allowed_app, err_app = UserAppExclusionEnforcer.evaluate_action_exclusion(approved_action)
    assert allowed_app is True
    assert err_app is None


def test_exclusion_enforcer_detects_ownership_spoofing():
    """Verify that misrepresenting a user application as SYSTEM_MANAGED is hard-blocked."""
    spoofed_action = ActionContract(
        action_id="act-spoofed-app",
        action_type="clean_cache",
        target_component="/Applications/Slack.app",
        target_ownership=ComponentOwnership.SYSTEM_MANAGED,  # Spoofed!
        risk_tier=OperationRiskTier.LOW_IMPACT,
        reversibility=Reversibility.REVERSIBLE,
        approval_requirement=ApprovalRequirement.NONE,
        user_approved=False,
    )

    allowed, err = UserAppExclusionEnforcer.evaluate_action_exclusion(spoofed_action)
    assert allowed is False
    assert "Component Ownership Spoofing Violation" in err
