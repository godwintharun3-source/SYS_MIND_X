#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS Swift companion bridge telemetry CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.swift_bridge import MacSwiftBridge
from system_mind.macos.swift_models import (
    SwiftBridgeTelemetry,
    SwiftThermalState,
)


def print_swift_telemetry_table(telemetry: SwiftBridgeTelemetry) -> None:
    """Print formatted terminal report and Swift companion telemetry table."""
    app = telemetry.frontmost_app
    perms = telemetry.permissions

    print("=" * 115)
    print(" SYSTEM MIND X — macOS Swift Native Companion Bridge Telemetry")
    print("=" * 115)
    print(f"  Host Platform:         {telemetry.host_platform}")
    print(f"  Bridge Channel:        {telemetry.bridge_channel}")
    print(f"  Execution Mode:        {'MOCK FIXTURE' if telemetry.is_mock else 'LIVE SWIFT IPC'}")
    print(f"  Operational Status:    {'READY (LIVE)' if telemetry.is_operational else 'DEGRADED / SIMULATION'}")
    print(f"  Thermal State:         {telemetry.thermal_state.value} ({'THROTTLED' if telemetry.is_throttled else 'NORMAL'})")
    print("  Charter Invariant:     Scan != Safe (Kernel/GUI telemetry does not prove application safety)")
    print("-" * 115)
    print("  ACTIVE DESKTOP CONTEXT & USER SESSION:")
    if app:
        print(f"    • Frontmost Focus:            {app.name} [PID: {app.pid}]")
        print(f"    • Bundle Identifier:          {app.bundle_id}")
        print(f"    • Application Path:           {app.path}")
    else:
        print("    • Frontmost Focus:            None (Headless / Locked Session)")

    print(f"    • Active Console User:        {telemetry.console_user}")
    print(f"    • System Uptime:              {telemetry.system_uptime_seconds:.1f} seconds")
    print(f"    • Screen Locked:              {'Yes' if telemetry.screen_locked else 'No'}")
    print("-" * 115)
    print("  PRIVACY & ACCESSIBILITY PERMISSION GATES:")
    print(f"    • Accessibility (AX):         {'Granted' if perms.accessibility_granted else 'Restricted (User Scope)'}")
    print(f"    • Full Disk Access:           {'Accessible' if perms.full_disk_access_granted else 'Restricted / User Scope'}")
    print(f"    • Screen Recording:           {'Granted' if perms.screen_recording_granted else 'Restricted'}")
    print("-" * 115)

    if telemetry.unavailable_telemetry:
        print("  UNAVAILABLE TELEMETRY / BRIDGE WARNINGS:")
        for item in telemetry.unavailable_telemetry:
            print(f"    [!] {item}")
        print("-" * 115)


def main() -> int:
    """CLI entrypoint for macOS Swift companion bridge telemetry inspection."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Read-only macOS Swift companion bridge telemetry inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock report profile instead of inspecting live Swift bridge",
    )
    parser.add_argument(
        "--profile",
        choices=["nominal", "throttled", "unsupported"],
        default="nominal",
        help="Mock profile to simulate (default: nominal)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON data instead of tabular terminal output",
    )
    parser.add_argument(
        "--binary",
        type=str,
        default=None,
        help="Custom path to compiled Swift companion binary",
    )
    parser.add_argument(
        "--compile-swift",
        action="store_true",
        help="Compile the native Swift companion package into binary path before execution",
    )

    args = parser.parse_args()

    custom_path = Path(args.binary) if args.binary else None
    bridge = MacSwiftBridge(binary_path=custom_path)

    if args.compile_swift:
        print("[*] Compiling native Swift companion agent package...")
        success = bridge.compile_companion()
        if success:
            print("[+] Swift companion agent compiled successfully.")
        else:
            print("[-] Swift companion agent compilation failed.")
            return 1
    telemetry = bridge.collect(use_mock=args.mock, profile=args.profile)

    if args.json:
        print(telemetry.to_json())
    else:
        print_swift_telemetry_table(telemetry)

    return 0


if __name__ == "__main__":
    sys.exit(main())
