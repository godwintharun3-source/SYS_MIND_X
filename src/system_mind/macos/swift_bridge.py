"""Read-only macOS Swift companion agent bridge boundary."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional

from system_mind.macos.swift_models import (
    FrontmostAppInfo,
    SwiftBridgeTelemetry,
    SwiftPermissionStatus,
    SwiftThermalState,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SWIFT_BINARY = REPO_ROOT / "apps" / "macos-companion" / "bin" / "SystemMindCompanion"


class MacSwiftBridge:
    """Dispatches read-only telemetry queries across the Swift-to-Python bridge boundary."""

    def __init__(self, binary_path: Optional[Path] = None) -> None:
        self.binary_path = binary_path or DEFAULT_SWIFT_BINARY

    def is_binary_available(self) -> bool:
        """Check if compiled native Swift companion binary exists and is executable."""
        return self.binary_path.exists() and os.access(self.binary_path, os.X_OK)

    def compile_companion(self) -> bool:
        """Compile the native Swift companion sources into the binary path."""
        if platform.system() != "Darwin":
            return False

        pkg_sources = [
            REPO_ROOT / "apps" / "macos-companion" / "Sources" / "SystemMindCompanion" / "BridgeModels.swift",
            REPO_ROOT / "apps" / "macos-companion" / "Sources" / "SystemMindCompanion" / "TelemetryCollector.swift",
            REPO_ROOT / "apps" / "macos-companion" / "Sources" / "SystemMindCompanion" / "main.swift",
        ]
        if not all(p.exists() for p in pkg_sources):
            logger.error("Required Swift source files missing for compilation.")
            return False

        self.binary_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            res = subprocess.run(
                ["/usr/bin/swiftc", *[str(p) for p in pkg_sources], "-o", str(self.binary_path)],
                capture_output=True,
                text=True,
                timeout=60.0,
                check=False,
            )
            return res.returncode == 0 and self.is_binary_available()
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.error("Swift companion compilation failed: %s", e)
            return False

    def collect(self, use_mock: bool = False, profile: str = "nominal") -> SwiftBridgeTelemetry:
        """Collect native macOS desktop telemetry through Swift bridge or deterministic simulation."""
        now_iso = datetime.now(timezone.utc).isoformat()

        if use_mock:
            return self._generate_mock_telemetry(profile=profile, timestamp=now_iso)

        if platform.system() != "Darwin":
            return self._generate_mock_telemetry(profile="unsupported", timestamp=now_iso)

        if not self.is_binary_available():
            logger.warning("Native Swift companion binary not found at %s. Falling back to mock.", self.binary_path)
            fallback = self._generate_mock_telemetry(profile="nominal", timestamp=now_iso)
            return SwiftBridgeTelemetry(
                thermal_state=fallback.thermal_state,
                frontmost_app=fallback.frontmost_app,
                permissions=fallback.permissions,
                system_uptime_seconds=fallback.system_uptime_seconds,
                console_user=fallback.console_user,
                screen_locked=fallback.screen_locked,
                timestamp=now_iso,
                host_platform="Darwin",
                bridge_channel="MOCK_FALLBACK_BINARY_MISSING",
                scan_proves_safe=False,
                unavailable_telemetry=["native_swift_binary_missing"],
                is_mock=True,
            )

        try:
            res = subprocess.run(
                [str(self.binary_path)],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode != 0:
                logger.error("Swift companion exited with code %d: %s", res.returncode, res.stderr)
                return self._generate_error_telemetry(f"Binary error {res.returncode}", now_iso)

            data = json.loads(res.stdout)
            return self._parse_telemetry_payload(data)

        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            logger.error("Swift bridge invocation failed: %s", e)
            return self._generate_error_telemetry(str(e), now_iso)

    def _parse_telemetry_payload(self, data: Dict[str, Any]) -> SwiftBridgeTelemetry:
        """Parse native Swift JSON payload into strongly typed SwiftBridgeTelemetry."""
        thermal_raw = data.get("thermal_state", "UNKNOWN").upper()
        try:
            thermal_state = SwiftThermalState(thermal_raw)
        except ValueError:
            thermal_state = SwiftThermalState.UNKNOWN

        frontmost_dict = data.get("frontmost_app")
        frontmost_app = None
        if frontmost_dict and isinstance(frontmost_dict, dict):
            frontmost_app = FrontmostAppInfo(
                name=frontmost_dict.get("name", "Unknown"),
                bundle_id=frontmost_dict.get("bundle_id", "unknown.bundle.id"),
                pid=int(frontmost_dict.get("pid", 0)),
                path=frontmost_dict.get("path", ""),
            )

        perm_dict = data.get("permissions", {})
        permissions = SwiftPermissionStatus(
            accessibility_granted=bool(perm_dict.get("accessibility_granted", False)),
            screen_recording_granted=bool(perm_dict.get("screen_recording_granted", False)),
            full_disk_access_granted=bool(perm_dict.get("full_disk_access_granted", False)),
        )

        return SwiftBridgeTelemetry(
            thermal_state=thermal_state,
            frontmost_app=frontmost_app,
            permissions=permissions,
            system_uptime_seconds=float(data.get("system_uptime_seconds", 0.0)),
            console_user=str(data.get("console_user", "unknown")),
            screen_locked=bool(data.get("screen_locked", False)),
            timestamp=str(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
            host_platform=str(data.get("host_platform", "Darwin")),
            bridge_channel=str(data.get("bridge_channel", "SWIFT_NATIVE_IPC")),
            scan_proves_safe=False,  # Enforce non-negotiable charter invariant
            unavailable_telemetry=list(data.get("unavailable_telemetry", [])),
            is_mock=bool(data.get("is_mock", False)),
        )

    def _generate_error_telemetry(self, error_msg: str, timestamp: str) -> SwiftBridgeTelemetry:
        """Produce graceful error telemetry record when live dispatch fails."""
        return SwiftBridgeTelemetry(
            thermal_state=SwiftThermalState.UNKNOWN,
            frontmost_app=None,
            permissions=SwiftPermissionStatus(False, False, False),
            system_uptime_seconds=0.0,
            console_user="unknown",
            screen_locked=False,
            timestamp=timestamp,
            host_platform="Darwin",
            bridge_channel="ERROR_DEGRADED",
            scan_proves_safe=False,
            unavailable_telemetry=[f"bridge_dispatch_failure: {error_msg}"],
            is_mock=True,
        )

    def _generate_mock_telemetry(self, profile: str, timestamp: str) -> SwiftBridgeTelemetry:
        """Produce deterministic mock telemetry across test profiles."""
        if profile == "throttled":
            return SwiftBridgeTelemetry(
                thermal_state=SwiftThermalState.CRITICAL,
                frontmost_app=FrontmostAppInfo(
                    name="Final Cut Pro",
                    bundle_id="com.apple.FinalCut",
                    pid=8842,
                    path="/Applications/Final Cut Pro.app",
                ),
                permissions=SwiftPermissionStatus(
                    accessibility_granted=True,
                    screen_recording_granted=True,
                    full_disk_access_granted=True,
                ),
                system_uptime_seconds=98765.4,
                console_user="operator",
                screen_locked=False,
                timestamp=timestamp,
                host_platform="Darwin",
                bridge_channel="MOCK_THROTTLED",
                scan_proves_safe=False,
                unavailable_telemetry=[],
                is_mock=True,
            )

        elif profile == "unsupported":
            return SwiftBridgeTelemetry(
                thermal_state=SwiftThermalState.UNKNOWN,
                frontmost_app=None,
                permissions=SwiftPermissionStatus(False, False, False),
                system_uptime_seconds=0.0,
                console_user="unknown",
                screen_locked=False,
                timestamp=timestamp,
                host_platform="Linux",
                bridge_channel="UNSUPPORTED_PLATFORM",
                scan_proves_safe=False,
                unavailable_telemetry=["apple_frameworks_unsupported", "appkit_unavailable"],
                is_mock=True,
            )

        # Default profile: "nominal"
        return SwiftBridgeTelemetry(
            thermal_state=SwiftThermalState.NOMINAL,
            frontmost_app=FrontmostAppInfo(
                name="Terminal",
                bundle_id="com.apple.Terminal",
                pid=4210,
                path="/System/Applications/Utilities/Terminal.app",
            ),
            permissions=SwiftPermissionStatus(
                accessibility_granted=False,
                screen_recording_granted=False,
                full_disk_access_granted=True,
            ),
            system_uptime_seconds=12345.6,
            console_user="developer",
            screen_locked=False,
            timestamp=timestamp,
            host_platform="Darwin",
            bridge_channel="MOCK_NOMINAL",
            scan_proves_safe=False,
            unavailable_telemetry=[],
            is_mock=True,
        )
