#!/usr/bin/env python3
"""SYSTEM MIND X — macOS Storage Volumes, APFS and Filesystem Telemetry CLI.

Queries storage volumes, APFS container hierarchy, capacity, free space, Signed System
Volume (SSV) seal status, and FileVault encryption using read-only Darwin mount, statvfs,
and diskutil interfaces in strict compliance with SC-01 and privacy constraints.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def format_bytes(n: int) -> str:
    """Format byte sizes into human-readable notation."""
    if n <= 0:
        return "0 B"
    elif n >= 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024 * 1024):.2f} GB ({n:,} bytes)"
    elif n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB ({n:,} bytes)"
    elif n >= 1024:
        return f"{n / 1024:.1f} KB ({n:,} bytes)"
    return f"{n:,} bytes"


def print_human_report(report) -> None:
    """Render structured human-readable terminal report."""
    print("=" * 80)
    print(" SYSTEM MIND X — macOS Storage Volumes & APFS Telemetry")
    print("=" * 80)
    print(f"  Collection Method:           {report.collection_method}")
    print(f"  Total Internal Capacity:     {format_bytes(report.total_internal_capacity_bytes)}")
    print(f"  Total Internal Available:    {format_bytes(report.total_internal_available_bytes)}")
    print(f"  FileVault Active:            {report.has_filevault_active}")
    print(f"  Signed System Volume (SSV):  {report.has_sealed_system_volume} (Sealed Root)")
    print("-" * 80)
    print(f" Mounted Volumes ({len(report.volumes)} detected):")

    for vol in report.volumes:
        role_tag = f"[{vol.volume_role.value}]"
        ro_tag = "RO" if vol.is_read_only else "RW"
        ssv_tag = " | SSV Sealed" if vol.is_sealed_system_volume else ""
        fv_tag = " | FileVault" if vol.is_filevault_encrypted else ""

        print(f"\n  * {vol.mount_point}  {role_tag} ({vol.volume_name})")
        print(f"    Device:    {vol.device_node} (ID: {vol.device_identifier}) | FS: {vol.filesystem_type.upper()}")
        print(f"    Capacity:  {format_bytes(vol.total_capacity_bytes)} | Used: {format_bytes(vol.used_bytes)} ({vol.used_percent:.1f}%) | Avail: {format_bytes(vol.available_bytes)}")
        print(f"    Security:  {ro_tag}{ssv_tag}{fv_tag} | Internal: {vol.is_internal} | SSD: {vol.is_solid_state}")
        if vol.apfs_container_id:
            print(f"    APFS Cont: {vol.apfs_container_id} | UUID: {vol.volume_uuid or 'N/A'}")

    if report.unavailable_telemetry:
        print("\n" + "-" * 80)
        print(" Unavailable Native Telemetry:")
        for item in report.unavailable_telemetry:
            print(f"  [!] {item}")

    if report.warnings:
        print("\n" + "-" * 80)
        print(" Warnings:")
        for w in report.warnings:
            print(f"  [*] {w}")

    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect macOS storage volumes, APFS container hierarchy, capacity, and filesystem metadata."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw machine-parsable JSON telemetry report.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Synthesize report from simulated Apple Silicon mock platform adapter.",
    )
    parser.add_argument(
        "--check-free-space-gb",
        type=float,
        metavar="GB",
        help="Assert that at least GB gigabytes of free space are available on the primary data volume.",
    )

    args = parser.parse_args()

    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = MacStorageDetector.detect(mock_adapter=mock_adapter)

    if args.check_free_space_gb is not None:
        target_vol = report.primary_data_volume or report.primary_system_volume
        if not target_vol:
            sys.stderr.write("Error: No primary storage volume detected.\n")
            return 1

        required_bytes = int(args.check_free_space_gb * 1024 * 1024 * 1024)
        if target_vol.available_bytes < required_bytes:
            sys.stderr.write(
                f"Storage Precondition Failed: {args.check_free_space_gb:.1f} GB required, but only {target_vol.available_bytes / (1024**3):.2f} GB available on {target_vol.mount_point}.\n"
            )
            return 1
        return 0

    if args.json:
        data = asdict(report)
        print(json.dumps(data, indent=2))
    else:
        print_human_report(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
