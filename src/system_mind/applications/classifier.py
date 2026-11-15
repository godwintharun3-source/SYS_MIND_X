"""Classifier for software applications, dependencies, and component ownership."""

from __future__ import annotations

import os
from typing import Optional

from system_mind.applications.models import (
    ApplicationProfile,
    ApplicationType,
    InstallScope,
)
from system_mind.core.types import ComponentOwnership


class ApplicationOwnershipClassifier:
    """Classifies host applications and paths into the tripartite component ownership model."""

    # Explicit OS Core Paths that are SYSTEM_MANAGED
    SYSTEM_CORE_PREFIXES = (
        "/system/",
        "/system/applications/",
        "/system/library/",
        "/usr/standalone/",
        "c:\\windows\\",
        "c:\\windows\\system32\\",
        "/lib/systemd/",
        "/etc/systemd/",
    )

    # Project Dependency and Environment Patterns (USER_MANAGED)
    PROJECT_DEPENDENCY_PATTERNS = (
        "node_modules",
        ".venv",
        "/venv/",
        "site-packages",
        "/target/debug/",
        "/target/release/",
        "/vendor/bundle/",
        ".gem/ruby",
    )

    # Developer Configuration and Dotfile Patterns (USER_MANAGED)
    DEVELOPER_CONFIG_PATTERNS = (
        ".zshrc",
        ".bashrc",
        ".bash_profile",
        ".gitconfig",
        "/.ssh/",
        "/.config/",
        "/.aws/",
    )

    # User Application Directories
    USER_APP_PREFIXES = (
        "/applications/",
        "~/applications/",
        "/opt/",
        "/usr/local/cellar/",
        "/usr/local/caskroom/",
        "c:\\program files\\",
        "c:\\program files (x86)\\",
        "appdata\\local\\",
        "appdata\\roaming\\",
        "~/.local/share/applications/",
        "~/.local/bin/",
        "/home/",
    )

    @classmethod
    def classify_path(cls, path: str) -> ApplicationProfile:
        """Classify a given path or application bundle into an ApplicationProfile."""
        normalized_path = path.strip().replace("\\", "/").lower()

        # 1. Check Project Dependencies (Highest precedence for workspace safety)
        if any(pat in normalized_path for pat in cls.PROJECT_DEPENDENCY_PATTERNS):
            return ApplicationProfile(
                app_id=f"dep:{os.path.basename(path)}",
                display_name=os.path.basename(path) or "Project Dependency",
                app_type=ApplicationType.PROJECT_DEPENDENCY,
                install_scope=InstallScope.PROJECT_LOCAL,
                install_path=path,
                executable_path=path,
                ownership=ComponentOwnership.USER_MANAGED,
                managed_by="project_package_manager",
                is_excluded_from_autonomous_updates=True,
            )

        # 2. Check Developer Dotfiles and Configs
        if any(pat in normalized_path for pat in cls.DEVELOPER_CONFIG_PATTERNS):
            return ApplicationProfile(
                app_id=f"config:{os.path.basename(path)}",
                display_name=os.path.basename(path) or "User Configuration",
                app_type=ApplicationType.DEVELOPER_TOOLCHAIN,
                install_scope=InstallScope.USER_LOCAL,
                install_path=path,
                executable_path=path,
                ownership=ComponentOwnership.USER_MANAGED,
                managed_by="user_customization",
                is_excluded_from_autonomous_updates=True,
            )

        # 3. Check System Core OS Components
        # Note: /System/Applications/ is OS core, whereas /Applications/ is user-managed third party
        if any(normalized_path.startswith(prefix.replace("\\", "/")) for prefix in cls.SYSTEM_CORE_PREFIXES):
            return ApplicationProfile(
                app_id=f"system:{os.path.basename(path)}",
                display_name=os.path.basename(path) or "OS Core Component",
                app_type=ApplicationType.SYSTEM_CORE,
                install_scope=InstallScope.SYSTEM_WIDE,
                install_path=path,
                executable_path=path,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                managed_by="os_vendor",
                is_excluded_from_autonomous_updates=False,
            )

        # 4. Check User Applications (e.g. /Applications/Google Chrome.app, Slack, VS Code)
        # Invariant 1: Fail-safe default to USER_MANAGED
        app_name = os.path.basename(path).replace(".app", "").replace(".exe", "")
        return ApplicationProfile(
            app_id=f"userapp:{app_name.lower().replace(' ', '_')}",
            display_name=app_name or "User Application",
            app_type=ApplicationType.USER_DESKTOP_APP,
            install_scope=InstallScope.SYSTEM_WIDE if path.startswith("/Applications") or "program files" in normalized_path else InstallScope.USER_LOCAL,
            install_path=path,
            executable_path=path,
            ownership=ComponentOwnership.USER_MANAGED,
            managed_by="user_installer",
            is_excluded_from_autonomous_updates=True,
        )
