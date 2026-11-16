#!/usr/bin/env python3
"""SYSTEM MIND X — macOS CPU and Compute Hardware Telemetry CLI.

Queries processor model, hardware architecture, core topology (Performance vs.
Efficiency cores), cache hierarchy, and vector/SIMD extensions using read-only Darwin
sysctl interfaces in strict compliance with SC-01 and privacy constraints.
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

from system_mind.macos.cpu_detector import MacCpuHardwareDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def format_bytes(n: int) -> str:
    """Format byte sizes into human-readable notation."""
    if n <= 0:
        return "N/A"
    elif n >= 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024 * 1024):.2f} GB ({n:,} bytes)"
    elif n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB ({n:,} bytes)"
    elif n >= 1024:
        return f"{n / 1024:.1f} KB ({n:,} bytes)"
    return f"{n:,} bytes"


def print_human_report(report) -> None:
    """Render structured human-readable terminal report."""
    info = report.cpu_info
    print("=" * 80)
    print(" SYSTEM MIND X — macOS CPU & Compute Hardware Telemetry")
    print("=" * 80)
    print(f"  Collection Method:     {report.collection_method}")
    print("-" * 80)
    print(" Processor & Architecture:")
    print(f"  CPU Brand String:      {info.cpu_brand_string}")
    print(f"  Hardware Model:        {info.hardware_model}")
    print(f"  Timebase Frequency:    {info.timebase_frequency_hz:,} Hz")
    print(f"  Virtual Page Size:     {info.page_size_bytes:,} bytes")
    print(f"  Physical Memory:       {format_bytes(info.physical_memory_bytes)}")
    print("-" * 80)
    print(" Core Topology:")
    print(f"  Total Physical Cores:  {info.total_physical_cores}")
    print(f"  Total Logical Cores:   {info.total_logical_cores}")
    print(f"  Performance Cores:     {info.performance_cores}")
    print(f"  Efficiency Cores:      {info.efficiency_cores}")
    print(f"  Heterogeneous Hybrid:  {info.is_heterogeneous_core_topology}")
    print(f"  Performance Levels:    {info.num_perf_levels}")

    if info.perf_levels:
        print(" Performance Level Breakdown:")
        for pl in info.perf_levels:
            print(f"   - Level {pl.level} ({pl.name}): {pl.logical_cores} cores | L1I: {format_bytes(pl.l1i_cache_bytes)} | L1D: {format_bytes(pl.l1d_cache_bytes)} | L2: {format_bytes(pl.l2_cache_bytes)}")

    print("-" * 80)
    print(" Cache Hierarchy:")
    print(f"  Cache Line Size:       {info.cache_line_size_bytes} bytes")
    print(f"  L1 Instruction Cache:  {format_bytes(info.l1i_cache_bytes)}")
    print(f"  L1 Data Cache:         {format_bytes(info.l1d_cache_bytes)}")
    print(f"  L2 Shared Cache:       {format_bytes(info.l2_cache_bytes)}")
    print(f"  L3 System Cache:       {format_bytes(info.l3_cache_bytes)}")
    print("-" * 80)
    print(f" Supported Vector / Hardware Features ({len(info.supported_features)} active):")
    feat_line = ", ".join(info.supported_features[:10])
    if len(info.supported_features) > 10:
        feat_line += f" ... (+{len(info.supported_features) - 10} more)"
    print(f"  {feat_line or 'None detected'}")

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
        description="Inspect macOS CPU core counts, topology, cache hierarchy, and hardware properties."
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
        "--strict-apple-silicon",
        action="store_true",
        help="Enforce that processor architecture is Apple Silicon (fail if Intel or generic).",
    )

    args = parser.parse_args()

    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = MacCpuHardwareDetector.detect(mock_adapter=mock_adapter)

    if args.strict_apple_silicon:
        # Check if Apple Silicon
        is_apple_silicon = "Apple" in report.cpu_info.cpu_brand_string or (
            report.cpu_info.is_heterogeneous_core_topology and report.cpu_info.performance_cores > 0
        )
        if not is_apple_silicon:
            sys.stderr.write(
                f"Error: Host is not Apple Silicon (detected CPU brand: '{report.cpu_info.cpu_brand_string}').\n"
            )
            return 1

    if args.json:
        data = asdict(report)
        print(json.dumps(data, indent=2))
    else:
        print_human_report(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
