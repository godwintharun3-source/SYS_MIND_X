#!/usr/bin/env python3
"""SYSTEM MIND X — macOS Battery State, Power Source and Health Telemetry CLI.

Queries battery presence, state of charge, AC power connectivity, charging dynamics,
cycle count, condition, and maximum capacity health using read-only Darwin pmset and
system_profiler interfaces in strict compliance with SC-01 and privacy constraints.
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

from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def print_human_report(report) -> None:
    """Render structured human-readable terminal report."""
    print("=" * 80)
    print(" SYSTEM MIND X — macOS Battery State & Health Telemetry")
    print("=" * 80)
    print(f"  Collection Method:           {report.collection_method}")
    print(f"  Battery Present:             {report.is_battery_present}")
    print(f"  Current Power Source:        {report.current_power_source.value}")
    print(f"  AC Power Connected:          {report.is_ac_connected}")

    if report.is_battery_present:
        soc_str = f"{report.state_of_charge_percent}%" if report.state_of_charge_percent is not None else "Unknown"
        print(f"  State of Charge:             {soc_str}")
        print(f"  Charging State:              {report.charging_state.value}")
        print(f"  Is Charging:                 {report.is_charging}")
        print(f"  Fully Charged:               {report.is_fully_charged}")

        if report.time_remaining_minutes is not None:
            hours = report.time_remaining_minutes // 60
            mins = report.time_remaining_minutes % 60
            print(f"  Time Remaining:              {hours}h {mins:02d}m ({report.time_remaining_minutes} mins)")
        else:
            print("  Time Remaining:              (Calculating or on AC power)")

        print(f"  Low Power Mode Active:       {report.is_low_power_mode_active}")
        print(f"  Below Warning Level:         {report.is_below_warning_level}")

        if report.health:
            h = report.health
            print("-" * 80)
            print(" Battery Health & Hardware Properties:")
            cycles_str = f"{h.cycle_count:,}" if h.cycle_count is not None else "N/A"
            print(f"  * Cycle Count:               {cycles_str}")
            print(f"  * Condition Assessment:      {h.condition.value}")
            max_cap_str = f"{h.maximum_capacity_percent}%" if h.maximum_capacity_percent is not None else "N/A"
            print(f"  * Maximum Capacity (Health): {max_cap_str}")
            if h.device_name:
                print(f"  * Device Controller:         {h.device_name}")
            if h.firmware_version:
                print(f"  * Firmware Version:          {h.firmware_version}")
            if h.anonymized_serial_hash:
                print(f"  * Battery Serial (SHA-256):  {h.anonymized_serial_hash} (anonymized for privacy)")
    else:
        print("  Notice:                      No internal battery detected (Desktop Mac / VM).")

    if report.warnings:
        print("-" * 80)
        print(" Warnings / Collector Diagnostics:")
        for w in report.warnings:
            print(f"  ! {w}")

    if report.unavailable_telemetry:
        print("-" * 80)
        print(" Unavailable Darwin Interfaces:")
        for u in report.unavailable_telemetry:
            print(f"  - {u}")

    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — macOS Battery State, Power Source and Health Telemetry CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw telemetry report as structured JSON",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock platform adapter simulation",
    )
    parser.add_argument(
        "--assert-min-battery-pct",
        type=int,
        metavar="PCT",
        help="Assert that battery charge is >= PCT; exit with 1 if battery is low or absent",
    )
    parser.add_argument(
        "--assert-ac-power",
        action="store_true",
        help="Assert that the host is connected to AC power; exit with 1 if running on battery",
    )

    args = parser.parse_args()

    detector = MacBatteryDetector()
    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = detector.detect(use_mock=args.mock, mock_adapter=mock_adapter)

    # Evaluate assertion gates
    if args.assert_ac_power:
        if not report.is_ac_connected:
            if not args.json:
                print("[-] Precondition FAILED: Host is operating on battery power, not connected to AC.", file=sys.stderr)
            sys.exit(1)

    if args.assert_min_battery_pct is not None:
        if not report.is_battery_present:
            # If desktop Mac on AC, passes by definition
            if not report.is_ac_connected:
                if not args.json:
                    print("[-] Precondition FAILED: No battery present and AC disconnected.", file=sys.stderr)
                sys.exit(1)
        else:
            current_soc = report.state_of_charge_percent or 0
            if current_soc < args.assert_min_battery_pct:
                if not args.json:
                    print(
                        f"[-] Precondition FAILED: Battery charge ({current_soc}%) is below required threshold ({args.assert_min_battery_pct}%).",
                        file=sys.stderr,
                    )
                sys.exit(1)

    if args.json:
        report_dict = asdict(report)
        print(json.dumps(report_dict, indent=2))
    else:
        print_human_report(report)


if __name__ == "__main__":
    main()
