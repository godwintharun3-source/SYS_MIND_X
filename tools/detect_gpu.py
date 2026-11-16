#!/usr/bin/env python3
"""SYSTEM MIND X — macOS GPU & Display Inventory Telemetry CLI.

Queries active graphics processors, core counts, Metal feature support, VRAM, and connected
displays (native panel pixels, UI resolution, refresh rate, Retina status) using read-only
Darwin system_profiler SPDisplaysDataType interface in strict compliance with SC-01 and INV-GPU-02.
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

from system_mind.macos.gpu_detector import MacGpuDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def print_human_report(report) -> None:
    """Render structured human-readable terminal report."""
    print("=" * 80)
    print(" SYSTEM MIND X — macOS GPU & Display Inventory Telemetry")
    print("=" * 80)
    print(f"  Collection Method:           {report.collection_method}")
    print(f"  Total GPUs Discovered:       {report.total_gpu_count}")
    print(f"  Total Displays Connected:    {report.total_display_count}")
    print(f"  Primary Display Resolution:  {report.primary_display_resolution or 'None'}")
    print(f"  Internal Built-in Display:   {'Yes' if report.has_builtin_display else 'No'}")
    print(f"  External Display Connected:  {'Yes' if report.has_external_display else 'No'}")

    print("-" * 80)
    print(f" Graphics Processing Units ({len(report.gpus)} total):")

    for i, gpu in enumerate(report.gpus, start=1):
        core_str = f"{gpu.core_count} cores" if gpu.core_count else "Unknown cores"
        print(f"\n  [{i}] {gpu.name} ({gpu.vendor})")
        print(f"      Interconnect Bus: {gpu.bus_type.value} | Cores: {core_str} | Device Type: {gpu.device_type}")

        if gpu.metal_support:
            print(f"      Metal Support:    {gpu.metal_support}")
        if gpu.vram_text:
            print(f"      VRAM / Memory:    {gpu.vram_text}")

        if gpu.displays:
            print(f"      Connected Displays ({len(gpu.displays)} total):")
            for d in gpu.displays:
                main_tag = " [MAIN DISPLAY]" if d.is_main else ""
                builtin_tag = " [BUILT-IN]" if d.is_builtin else " [EXTERNAL]"
                retina_tag = " [RETINA]" if d.pixel_density_retina else ""
                print(f"        * {d.name}{main_tag}{builtin_tag}{retina_tag}")
                print(f"          Connection: {d.connection_type.value} | Online: {d.is_online} | Mirroring: {d.is_mirror}")

                if d.resolution:
                    print(f"          Active UI Resolution: {d.resolution}")
                if d.native_pixels:
                    print(f"          Native Panel Pixels:  {d.native_pixels}")
                if d.refresh_rate_hz:
                    print(f"          Refresh Rate:         {d.refresh_rate_hz:.2f} Hz")
                if d.display_id:
                    print(f"          Darwin Display ID:    {d.display_id}")
                if d.vendor_id or d.product_id:
                    print(f"          Vendor ID / Product:  {d.vendor_id or 'N/A'} / {d.product_id or 'N/A'}")
                if d.anonymized_serial_hash:
                    print(f"          Display Serial Hash:  {d.anonymized_serial_hash} (INV-GPU-02 anonymized)")
                if d.ambient_brightness:
                    print("          Ambient True Tone:    Supported")
        else:
            print("      Connected Displays: None (Headless or Virtual)")

    if report.warnings:
        print("-" * 80)
        print(" Warnings & Anomalies:")
        for w in report.warnings:
            print(f"  [WARN] {w}")

    if report.unavailable_telemetry:
        print("-" * 80)
        print(" Unavailable Metrics on Host:")
        for u in report.unavailable_telemetry:
            print(f"  [UNAVAILABLE] {u}")

    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query macOS GPU and connected display inventory using unprivileged Darwin APIs.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full telemetry snapshot as structured JSON.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate Apple Silicon GPU and display telemetry via safe mock adapter.",
    )
    parser.add_argument(
        "--assert-gpu",
        action="store_true",
        help="Assert that at least one GPU was successfully detected; exit 1 if zero.",
    )
    parser.add_argument(
        "--assert-displays",
        type=int,
        metavar="MIN_COUNT",
        help="Assert that at least MIN_COUNT connected displays were detected; exit 1 if fewer.",
    )

    args = parser.parse_args()

    detector = MacGpuDetector()
    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = detector.detect(use_mock=args.mock, mock_adapter=mock_adapter)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print_human_report(report)

    if args.assert_gpu and report.total_gpu_count < 1:
        sys.stderr.write("Assertion failed: Zero GPUs detected.\n")
        return 1

    if args.assert_displays is not None and report.total_display_count < args.assert_displays:
        sys.stderr.write(
            f"Assertion failed: Detected {report.total_display_count} displays, expected at least {args.assert_displays}.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
