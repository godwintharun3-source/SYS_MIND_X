#!/usr/bin/env python3
"""SYSTEM MIND X — Mock Platform Adapter Developer CLI.

Provides command-line inspection, telemetry queries, and compatibility matrix
audits using the safe mock platform adapter. Runs completely in memory with zero
host mutation and zero elevated privileges.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

# Ensure repository root src/ is on PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.core.types import PlatformTier
from system_mind.platform.adapter import (
    MockPlatformAdapter,
    MockPlatformProfileFactory,
    PlatformAdapter,
)
from system_mind.platform.matrix import (
    PlatformMatrixRegistry,
    PlatformTargetId,
)


def format_bytes(byte_count: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if byte_count < 1024.0:
            return f"{byte_count:.1f} {unit}"
        byte_count /= 1024.0
    return f"{byte_count:.1f} PB"


def handle_inspect(adapter: MockPlatformAdapter, as_json: bool) -> int:
    """Inspect simulated host report and security state."""
    host = adapter.get_host_report()
    sec = adapter.get_security_state()

    if as_json:
        payload = {
            "target_id": adapter.get_target_id().value,
            "host_report": asdict(host),
            "security_state": asdict(sec),
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print("================================================================================")
    print(f" SYSTEM MIND X — Mock Platform Inspection [{adapter.get_target_id().value}]")
    print("================================================================================")
    print(f"  OS Name:           {host.os_name} {host.os_version} ({host.architecture})")
    print(f"  Kernel Version:    {host.kernel_version}")
    print(f"  CPU Brand:         {host.cpu_brand} ({host.cpu_cores} cores)")
    print(f"  Total Memory:      {format_bytes(host.memory_bytes)}")
    print(f"  Platform Tier:     {host.platform_tier.value}")
    print(f"  Supported Host:    {host.is_supported_host}")
    print("--------------------------------------------------------------------------------")
    print(" Security Controls:")
    print(f"  SIP Enabled:       {sec.sip_enabled}")
    print(f"  Gatekeeper:        {sec.gatekeeper_enabled}")
    print(f"  Secure Boot:       {sec.secure_boot_enabled}")
    print(f"  Firewall:          {sec.firewall_enabled}")
    print(f"  Disk Encryption:   {sec.disk_encryption_enabled}")
    print(f"  Lockdown Mode:     {sec.lockdown_mode}")
    if sec.selinux_or_apparmor_status:
        print(f"  LSM Status:        {sec.selinux_or_apparmor_status}")
    if sec.notes:
        print(f"  Notes:             {', '.join(sec.notes)}")
    print("================================================================================")
    return 0


def handle_telemetry(adapter: MockPlatformAdapter, as_json: bool) -> int:
    """Output hardware and process telemetry."""
    hw = adapter.get_hardware_telemetry()
    procs = adapter.get_process_telemetry()

    if as_json:
        payload = {
            "target_id": adapter.get_target_id().value,
            "hardware_telemetry": asdict(hw),
            "processes": [asdict(p) for p in procs],
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print("================================================================================")
    print(f" SYSTEM MIND X — Hardware & Process Telemetry [{adapter.get_target_id().value}]")
    print("================================================================================")
    print(f"  CPU Usage:         {hw.cpu_usage_pct:.1f}%")
    print(f"  Memory RSS:        {format_bytes(hw.memory_rss_bytes)}")
    print(f"  Free Memory:       {format_bytes(hw.memory_free_bytes)}")
    print(f"  Available Disk:    {format_bytes(hw.disk_available_bytes)}")
    print(f"  Thermal State:     {hw.thermal_state}")
    print(f"  Power Source:      {hw.power_source} (Battery: {hw.battery_pct}%, Charging: {hw.is_charging})")
    print("--------------------------------------------------------------------------------")
    print(f"  Running Processes ({len(procs)}):")
    print(f"   {'PID':<6} {'PPID':<6} {'CPU%':<6} {'RSS':<10} {'OWNERSHIP':<12} {'NAME'}")
    for p in procs:
        ownership = "SYSTEM" if p.is_system_core else ("USER_APP" if p.is_user_app else "OTHER")
        print(f"   {p.pid:<6} {p.ppid:<6} {p.cpu_pct:<6.1f} {format_bytes(p.memory_bytes):<10} {ownership:<12} {p.name}")
    print("================================================================================")
    return 0


def handle_audit_matrix(as_json: bool) -> int:
    """Audit all 4 first-release target profiles for matrix compatibility."""
    results = []
    overall_valid = True

    for target in PlatformTargetId:
        adapter = MockPlatformProfileFactory.create_mock(target)
        host = adapter.get_host_report()
        sec = adapter.get_security_state()
        compatible, diagnostics = PlatformMatrixRegistry.validate_host_compatibility(host)

        status_entry = {
            "target_id": target.value,
            "compatible": compatible,
            "diagnostics": diagnostics,
            "security_valid": sec.firewall_enabled,
        }
        if not compatible:
            overall_valid = False
        results.append(status_entry)

    if as_json:
        print(json.dumps({"overall_valid": overall_valid, "targets": results}, indent=2))
        return 0 if overall_valid else 1

    print("================================================================================")
    print(" SYSTEM MIND X — Mock Platform Matrix Audit")
    print("================================================================================")
    for r in results:
        status_symbol = "[+]" if r["compatible"] else "[-]"
        diag = f" (Diagnostics: {r['diagnostics']})" if r["diagnostics"] else ""
        print(f"  {status_symbol} {r['target_id']:<24} Compatible: {r['compatible']}{diag}")
    print("--------------------------------------------------------------------------------")
    print(f" Overall Status: {'PASSED' if overall_valid else 'FAILED'}")
    print("================================================================================")
    return 0 if overall_valid else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Mock Platform Adapter CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="top_json",
        help="Output results in JSON format",
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect host report and security state")
    inspect_parser.add_argument(
        "--target",
        choices=[t.value for t in PlatformTargetId],
        default=PlatformTargetId.MACOS_APPLE_SILICON.value,
        help="Platform target to inspect (default: MACOS_APPLE_SILICON)",
    )
    inspect_parser.add_argument("--json", action="store_true", dest="sub_json", help="Output JSON")

    # telemetry
    telemetry_parser = subparsers.add_parser("telemetry", help="Query hardware and process telemetry")
    telemetry_parser.add_argument(
        "--target",
        choices=[t.value for t in PlatformTargetId],
        default=PlatformTargetId.MACOS_APPLE_SILICON.value,
        help="Platform target to query (default: MACOS_APPLE_SILICON)",
    )
    telemetry_parser.add_argument("--json", action="store_true", dest="sub_json", help="Output JSON")

    # audit-matrix
    audit_parser = subparsers.add_parser("audit-matrix", help="Audit all supported platform targets")
    audit_parser.add_argument("--json", action="store_true", dest="sub_json", help="Output JSON")

    args = parser.parse_args()
    as_json = bool(getattr(args, "top_json", False) or getattr(args, "sub_json", False))

    if not args.subcommand or args.subcommand == "inspect":
        target_str = getattr(args, "target", PlatformTargetId.MACOS_APPLE_SILICON.value)
        target = PlatformTargetId(target_str)
        adapter = MockPlatformProfileFactory.create_mock(target)
        return handle_inspect(adapter, as_json)
    elif args.subcommand == "telemetry":
        target = PlatformTargetId(args.target)
        adapter = MockPlatformProfileFactory.create_mock(target)
        return handle_telemetry(adapter, as_json)
    elif args.subcommand == "audit-matrix":
        return handle_audit_matrix(as_json)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
