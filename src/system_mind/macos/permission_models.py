"""Strongly typed data contracts for macOS permissions, prompt triggers, and code signing entitlements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MacPermissionType(str, Enum):
    """Categorized macOS Transparency, Consent, and Control (TCC) and system permissions."""

    FULL_DISK_ACCESS = "FULL_DISK_ACCESS"
    SCREEN_RECORDING = "SCREEN_RECORDING"
    ACCESSIBILITY = "ACCESSIBILITY"
    DOCUMENTS_FOLDER = "DOCUMENTS_FOLDER"
    DOWNLOADS_FOLDER = "DOWNLOADS_FOLDER"
    DESKTOP_FOLDER = "DESKTOP_FOLDER"
    INPUT_MONITORING = "INPUT_MONITORING"
    APP_SANDBOX = "APP_SANDBOX"
    ENDPOINT_SECURITY = "ENDPOINT_SECURITY"


class EntitlementTier(str, Enum):
    """Security tier classification for code signing entitlements."""

    STANDARD_USER = "STANDARD_USER"  # Standard user-space capabilities (network client, read files)
    HARDENED_RUNTIME = "HARDENED_RUNTIME"  # Hardened runtime exception flags (disallow JIT, library validation)
    APPLE_RESTRICTED = "APPLE_RESTRICTED"  # Restricted enterprise entitlements requiring Apple approval
    PROHIBITED_NON_GOAL = "PROHIBITED_NON_GOAL"  # Explicitly banned entitlements (debugging, ambient execution)


class PromptTriggerMode(str, Enum):
    """Mode by which macOS prompts the user for permission consent."""

    IMPLICIT_OS_PROMPT = "IMPLICIT_OS_PROMPT"  # OS raises native system dialog upon first API call
    GUIDED_SYSTEM_SETTINGS = "GUIDED_SYSTEM_SETTINGS"  # Manual user configuration in macOS System Settings
    PASSIVE_PROBE = "PASSIVE_PROBE"  # Passive non-prompting probe returning boolean authorization
    NEVER_PROMPTED = "NEVER_PROMPTED"  # Strictly excluded by policy; never requested or prompted


class PermissionState(str, Enum):
    """Observed runtime state of a permission or capability grant."""

    GRANTED = "GRANTED"
    DENIED = "DENIED"
    NOT_DETERMINED = "NOT_DETERMINED"
    RESTRICTED = "RESTRICTED"
    EXCLUDED_BY_POLICY = "EXCLUDED_BY_POLICY"
    PROHIBITED_NON_GOAL = "PROHIBITED_NON_GOAL"


@dataclass
class MacEntitlementSpec:
    """Specification of an Apple code signing entitlement and its companion agent policy."""

    entitlement_key: str
    tier: EntitlementTier
    description: str
    is_required: bool
    target_component: str
    fallback_behavior: str
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant!

    def __post_init__(self) -> None:
        self.scan_proves_safe = False


@dataclass
class MacPermissionPromptInfo:
    """Detailed metadata for a macOS permission prompt, trigger API, and fallback path."""

    permission_type: MacPermissionType
    tcc_service_name: str
    prompt_trigger_mode: PromptTriggerMode
    user_dialog_text: str
    settings_path: str
    is_strictly_required: bool
    is_banned_non_goal: bool = False
    fallback_strategy: str = "Report partial telemetry and omit protected data"
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant!

    def __post_init__(self) -> None:
        self.scan_proves_safe = False


@dataclass
class MacPermissionManifestReport:
    """Comprehensive manifest and runtime report of macOS permission prompts and entitlements."""

    companion_mode: str = "READ_ONLY_USER_COMPANION"
    host_platform: str = "Darwin-Apple-Silicon"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    permissions: List[MacPermissionPromptInfo] = field(default_factory=list)
    entitlements: List[MacEntitlementSpec] = field(default_factory=list)
    active_states: Dict[str, PermissionState] = field(default_factory=dict)
    non_goals_enforced: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    unavailable_telemetry: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant!

    def __post_init__(self) -> None:
        self.scan_proves_safe = False

    def get_permission(self, perm_type: MacPermissionType) -> Optional[MacPermissionPromptInfo]:
        """Find permission prompt info by type."""
        for p in self.permissions:
            if p.permission_type == perm_type:
                return p
        return None

    def get_entitlement(self, key: str) -> Optional[MacEntitlementSpec]:
        """Find entitlement specification by key."""
        for e in self.entitlements:
            if e.entitlement_key == key:
                return e
        return None
