#!/usr/bin/env python3
"""SYSTEM MIND X — macOS Memory Capacity, Pressure and Usage Telemetry CLI.

Queries total physical RAM, Mach VM page statistics (App, Wired, Compressed, Cached, Free),
dynamic swap space, and kernel memory pressure using read-only Darwin sysctl and vm_stat
interfaces in strict compliance with SC-01 and privacy constraints.
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

from system_mind.macos.memory_detector import MacMemoryDetector
from system_mind.macos.memory_models import MemoryPressureLevel
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
    mem = report.memory_info
    pages = report.page_stats

    # Color code pressure indicators if terminal supports ANSI
    pressure_tag = mem.pressure_level.value
    if mem.pressure_level == MemoryPressureLevel.NORMAL:
        color_pressure = f"\033[32m{pressure_tag} (Nominal / Green)\033[0m"
    elif mem.pressure_level == MemoryPressureLevel.WARN:
        color_pressure = f"\033[33m{pressure_tag} (Elevated / Yellow)\033[0m"
    elif mem.pressure_level == MemoryPressureLevel.CRITICAL:
        color_pressure = f"\033[31m{pressure_tag} (Critical / Red)\033[0m"
    else:
        color_pressure = pressure_tag

    print("=" * 80)
    print(" SYSTEM MIND X — macOS Memory Capacity, Usage & Pressure Telemetry")
    print("=" * 80)
    print(f"  Collection Method:     {report.collection_method}")
    print("-" * 80)
    print(" Physical Capacity & Kernel Memory Pressure:")
    print(f"  Total Physical RAM:    {format_bytes(mem.total_physical_bytes)}")
    print(f"  Memory Pressure State: {color_pressure}")
    print(f"  Pressure Index:        {mem.pressure_percentage:.1f}%")
    print("-" * 80)
    print(f" Memory Breakdown (Activity Monitor Semantics) — Used: {mem.used_percent:.1f}%:")
    print(f"  [+] App Memory:        {format_bytes(mem.app_memory_bytes)}")
    print(f"  [+] Wired Memory:      {format_bytes(mem.wired_memory_bytes)}")
    print(f"  [+] Compressed Memory: {format_bytes(mem.compressed_memory_bytes)}")
    print(f"  -------------------------------------------------------------")
    print(f"  [*] Total Memory Used: {format_bytes(mem.total_used_bytes)} ({mem.used_percent:.1f}%)")
    print(f"  [*] Cached Files:      {format_bytes(mem.cached_files_bytes)}")
    print(f"  [*] Free Memory:       {format_bytes(mem.free_bytes)}")
    print("-" * 80)
    print(" Dynamic Swap Space:")
    print(f"  Swap Total:            {format_bytes(mem.swap.total_bytes)}")
    print(f"  Swap Used:             {format_bytes(mem.swap.used_bytes)}")
    print(f"  Swap Free:             {format_bytes(mem.swap.free_bytes)}")
    print(f"  Encrypted On Disk:     {mem.swap.is_encrypted}")
    print("-" * 80)
    print(" Mach Virtual Memory Statistics:")
    print(f"  Page Size:             {pages.page_size_bytes:,} bytes")
    print(f"  Active / Inactive:     {pages.pages_active:,} / {pages.pages_inactive:,} pages")
    print(f"  Purgeable / Speculative: {pages.pages_purgeable:,} / {pages.pages_speculative:,} pages")
    print(f"  Compressions / Decomp: {pages.compressions:,} / {pages.decompressions:,}")
    print(f"  Pageins / Pageouts:    {pages.pageins:,} / {pages.pageouts:,}")
    print(f"  Swapins / Swapouts:    {pages.swapins:,} / {pages.swapouts:,}")

    if report.unavailable_telemetry:
        print("-" * 80)
        print(" Unavailable Native Telemetry:")
        for item in report.unavailable_telemetry:
            print(f"  [!] {item}")

    if report.warnings:
        print("-" * 80)
        print(" Warnings:")
        for w in report.warnings:
            print(f"  [*] {w}")

    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect macOS memory capacity, Mach VM page statistics, swap, and memory pressure."
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
        "--check-pressure",
        action="store_true",
        help="Check memory pressure; exits with code 1 if CRITICAL, 0 otherwise.",
    )

    args = parser.parse_args()

    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = MacMemoryDetector.detect(mock_adapter=mock_adapter)

    if args.check_pressure:
        if report.memory_info.pressure_level == MemoryPressureLevel.CRITICAL:
            sys.stderr.write("Alert: Memory pressure is CRITICAL.\n")
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
