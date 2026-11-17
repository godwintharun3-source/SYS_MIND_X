"""Read-only macOS permission, prompt trigger, and entitlement inspection engine."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import platform
from typing import Any, Dict, List, Optional

from system_mind.macos.permission_models import (
    EntitlementTier,
    MacEntitlementSpec,
    MacPermissionManifestReport,
    MacPermissionPromptInfo,
    MacPermissionType,
    PermissionState,
    PromptTriggerMode,
)

logger = logging.getLogger(__name__)


class MacOsPermissionInspector:
    """Read-only introspection engine evaluating macOS permissions, prompt triggers, and entitlements."""

    CANONICAL_PERMISSIONS: List[MacPermissionPromptInfo] = [
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.FULL_DISK_ACCESS,
            tcc_service_name="kTCCServiceSystemPolicyAllFiles",
            prompt_trigger_mode=PromptTriggerMode.GUIDED_SYSTEM_SETTINGS,
            user_dialog_text="System Settings > Privacy & Security > Full Disk Access",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
            is_strictly_required=False,
            is_banned_non_goal=False,
            fallback_strategy="Gracefully skip protected roots; omit Mail/Safari directories; report fda_granted = False and partial_data = True",
            scan_proves_safe=False,
        ),
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.SCREEN_RECORDING,
            tcc_service_name="kTCCServiceScreenCapture",
            prompt_trigger_mode=PromptTriggerMode.IMPLICIT_OS_PROMPT,
            user_dialog_text="System Mind would like to record this computer's screen",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            is_strictly_required=False,
            is_banned_non_goal=False,
            fallback_strategy="Omit window titles and thumbnails; scrub residual window metadata; report screen_recording_granted = False",
            scan_proves_safe=False,
        ),
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.ACCESSIBILITY,
            tcc_service_name="kTCCServiceAccessibility",
            prompt_trigger_mode=PromptTriggerMode.IMPLICIT_OS_PROMPT,
            user_dialog_text="System Mind would like to control this computer using accessibility features",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            is_strictly_required=False,
            is_banned_non_goal=False,
            fallback_strategy="Fall back to NSWorkspace.frontmostApplication which requires zero accessibility permissions for app/bundle ID",
            scan_proves_safe=False,
        ),
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.DOCUMENTS_FOLDER,
            tcc_service_name="kTCCServiceSystemPolicyDocumentsFolder",
            prompt_trigger_mode=PromptTriggerMode.NEVER_PROMPTED,
            user_dialog_text="System Mind would like to access files in your Documents folder",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_RemovableVolume",
            is_strictly_required=False,
            is_banned_non_goal=False,
            fallback_strategy="Excluded by default via DEFAULT_PRIVACY_EXCLUSIONS; personal directories are never probed",
            scan_proves_safe=False,
        ),
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.DOWNLOADS_FOLDER,
            tcc_service_name="kTCCServiceSystemPolicyDownloadsFolder",
            prompt_trigger_mode=PromptTriggerMode.NEVER_PROMPTED,
            user_dialog_text="System Mind would like to access files in your Downloads folder",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_RemovableVolume",
            is_strictly_required=False,
            is_banned_non_goal=False,
            fallback_strategy="Excluded by default via DEFAULT_PRIVACY_EXCLUSIONS; personal directories are never probed",
            scan_proves_safe=False,
        ),
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.DESKTOP_FOLDER,
            tcc_service_name="kTCCServiceSystemPolicyDesktopFolder",
            prompt_trigger_mode=PromptTriggerMode.NEVER_PROMPTED,
            user_dialog_text="System Mind would like to access files in your Desktop folder",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_RemovableVolume",
            is_strictly_required=False,
            is_banned_non_goal=False,
            fallback_strategy="Excluded by default via DEFAULT_PRIVACY_EXCLUSIONS; personal directories are never probed",
            scan_proves_safe=False,
        ),
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.INPUT_MONITORING,
            tcc_service_name="kTCCServiceListenEvent",
            prompt_trigger_mode=PromptTriggerMode.NEVER_PROMPTED,
            user_dialog_text="System Mind would like to receive keystrokes from any application",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
            is_strictly_required=False,
            is_banned_non_goal=True,
            fallback_strategy="PROHIBITED NON-GOAL (NG-02): Keystroke logging, input monitoring, and ambient keyboard sniffing are strictly prohibited",
            scan_proves_safe=False,
        ),
        MacPermissionPromptInfo(
            permission_type=MacPermissionType.ENDPOINT_SECURITY,
            tcc_service_name="com.apple.developer.endpoint-security.client",
            prompt_trigger_mode=PromptTriggerMode.PASSIVE_PROBE,
            user_dialog_text="System Extension Blocked: Requires Apple Developer Enterprise Entitlement",
            settings_path="x-apple.systempreferences:com.apple.preference.security?Privacy_SystemExtensions",
            is_strictly_required=False,
            is_banned_non_goal=False,
            fallback_strategy="Transparent user-space fallback to CoreServices FSEvents and Darwin ps (INV-FAULT-03)",
            scan_proves_safe=False,
        ),
    ]

    CANONICAL_ENTITLEMENTS: List[MacEntitlementSpec] = [
        MacEntitlementSpec(
            entitlement_key="com.apple.security.network.client",
            tier=EntitlementTier.STANDARD_USER,
            description="Permits outgoing socket connections to loopback agent API (127.0.0.1) and remote brokers",
            is_required=True,
            target_component="Desktop Shell & Agent Wire Client",
            fallback_behavior="Fails with network socket creation error if blocked",
            scan_proves_safe=False,
        ),
        MacEntitlementSpec(
            entitlement_key="com.apple.security.files.user-selected.read-only",
            tier=EntitlementTier.STANDARD_USER,
            description="Permits read-only ingestion of user-selected diagnostic logs via native file dialogs",
            is_required=False,
            target_component="Desktop Presentation Shell",
            fallback_behavior="File dialogs cannot return paths outside sandboxed container",
            scan_proves_safe=False,
        ),
        MacEntitlementSpec(
            entitlement_key="com.apple.security.cs.allow-jit",
            tier=EntitlementTier.HARDENED_RUNTIME,
            description="Hardened Runtime exception allowing dynamic JIT memory allocation (DISALLOWED)",
            is_required=False,
            target_component="Companion Agent Core",
            fallback_behavior="Prohibited in companion agent to prevent arbitrary executable memory execution",
            scan_proves_safe=False,
        ),
        MacEntitlementSpec(
            entitlement_key="com.apple.security.cs.allow-unsigned-executable-memory",
            tier=EntitlementTier.HARDENED_RUNTIME,
            description="Hardened Runtime exception allowing unsigned executable memory (DISALLOWED)",
            is_required=False,
            target_component="Companion Agent Core",
            fallback_behavior="Prohibited in companion agent to enforce code integrity",
            scan_proves_safe=False,
        ),
        MacEntitlementSpec(
            entitlement_key="com.apple.security.cs.disable-library-validation",
            tier=EntitlementTier.HARDENED_RUNTIME,
            description="Hardened Runtime exception allowing loading unsigned or external dylibs (DISALLOWED)",
            is_required=False,
            target_component="Companion Agent Core",
            fallback_behavior="Prohibited in companion agent; all libraries must match Apple or Team ID",
            scan_proves_safe=False,
        ),
        MacEntitlementSpec(
            entitlement_key="com.apple.developer.endpoint-security.client",
            tier=EntitlementTier.APPLE_RESTRICTED,
            description="Authoritative Endpoint Security subscription entitlement requiring Apple Enterprise grant",
            is_required=False,
            target_component="Future System Daemon",
            fallback_behavior="Transparent fallback to user-space CoreServices FSEvents and Darwin ps (INV-FAULT-03)",
            scan_proves_safe=False,
        ),
    ]

    NON_GOALS_ENFORCED: List[str] = [
        "NG-01: Zero unmediated shell execution or raw root privilege escalation",
        "NG-02: Zero ambient screen scraping or continuous video surveillance",
        "NG-03: Zero keystroke logging (kTCCServiceListenEvent strictly prohibited)",
        "NG-04: Zero automated modification of user applications or personal project environments",
        "NG-05: Non-intrusive telemetry collection (zero user-prompt loops on permission denial)",
    ]

    def __init__(self) -> None:
        pass

    @staticmethod
    def probe_full_disk_access() -> PermissionState:
        """Non-intrusive probe checking whether Full Disk Access is active.

        Tests read access to user-space protected directory probe without triggering a UI prompt.
        """
        if platform.system() != "Darwin":
            return PermissionState.NOT_DETERMINED

        # Testing read access to ~/Library/Mail which is protected by kTCCServiceSystemPolicyAllFiles
        mail_probe = Path.home() / "Library" / "Mail"
        if not mail_probe.exists():
            return PermissionState.NOT_DETERMINED

        try:
            # os.access check does NOT trigger a user dialog prompt in macOS TCC
            if os.access(mail_probe, os.R_OK):
                return PermissionState.GRANTED
            return PermissionState.DENIED
        except Exception:
            return PermissionState.DENIED

    def inspect_permissions(self, mock: bool = False) -> MacPermissionManifestReport:
        """Inspect macOS permission prompt triggers, entitlement specs, and active states."""
        is_darwin = platform.system() == "Darwin" and not mock

        active_states: Dict[str, PermissionState] = {}

        if is_darwin:
            # FDA passive probe
            active_states[MacPermissionType.FULL_DISK_ACCESS.value] = self.probe_full_disk_access()

            # Personal directories are excluded by policy
            active_states[MacPermissionType.DOCUMENTS_FOLDER.value] = PermissionState.EXCLUDED_BY_POLICY
            active_states[MacPermissionType.DOWNLOADS_FOLDER.value] = PermissionState.EXCLUDED_BY_POLICY
            active_states[MacPermissionType.DESKTOP_FOLDER.value] = PermissionState.EXCLUDED_BY_POLICY

            # Input monitoring is a banned non-goal
            active_states[MacPermissionType.INPUT_MONITORING.value] = PermissionState.PROHIBITED_NON_GOAL

            # Screen recording & accessibility are not determined without user prompt
            active_states[MacPermissionType.SCREEN_RECORDING.value] = PermissionState.NOT_DETERMINED
            active_states[MacPermissionType.ACCESSIBILITY.value] = PermissionState.NOT_DETERMINED

            # Endpoint security is restricted in user-agent companion
            active_states[MacPermissionType.ENDPOINT_SECURITY.value] = PermissionState.RESTRICTED
        else:
            # Deterministic mock states
            active_states[MacPermissionType.FULL_DISK_ACCESS.value] = PermissionState.DENIED
            active_states[MacPermissionType.SCREEN_RECORDING.value] = PermissionState.DENIED
            active_states[MacPermissionType.ACCESSIBILITY.value] = PermissionState.NOT_DETERMINED
            active_states[MacPermissionType.DOCUMENTS_FOLDER.value] = PermissionState.EXCLUDED_BY_POLICY
            active_states[MacPermissionType.DOWNLOADS_FOLDER.value] = PermissionState.EXCLUDED_BY_POLICY
            active_states[MacPermissionType.DESKTOP_FOLDER.value] = PermissionState.EXCLUDED_BY_POLICY
            active_states[MacPermissionType.INPUT_MONITORING.value] = PermissionState.PROHIBITED_NON_GOAL
            active_states[MacPermissionType.ENDPOINT_SECURITY.value] = PermissionState.RESTRICTED

        warnings: List[str] = []
        unavailable_telemetry: List[str] = []

        if active_states.get(MacPermissionType.FULL_DISK_ACCESS.value) == PermissionState.DENIED:
            warnings.append("Full Disk Access not granted: protected application paths will be skipped")
            unavailable_telemetry.append("protected_user_mail_and_messages")

        if active_states.get(MacPermissionType.SCREEN_RECORDING.value) == PermissionState.DENIED:
            unavailable_telemetry.append("window_titles_and_thumbnails")

        host_label = (
            f"{platform.system()}-{platform.machine()}"
            if is_darwin
            else "Darwin-Mock-Apple-Silicon-arm64"
        )

        return MacPermissionManifestReport(
            companion_mode="READ_ONLY_USER_COMPANION",
            host_platform=host_label,
            timestamp=datetime.now(timezone.utc).isoformat(),
            permissions=list(self.CANONICAL_PERMISSIONS),
            entitlements=list(self.CANONICAL_ENTITLEMENTS),
            active_states=active_states,
            non_goals_enforced=list(self.NON_GOALS_ENFORCED),
            warnings=warnings,
            unavailable_telemetry=unavailable_telemetry,
            scan_proves_safe=False,
        )

    def get_manifest_mock(self) -> MacPermissionManifestReport:
        """Construct deterministic mock manifest for testing and non-Darwin environments."""
        return self.inspect_permissions(mock=True)
