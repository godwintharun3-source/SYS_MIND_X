#!/usr/bin/env python3
"""SYSTEM MIND X — macOS USB & Peripheral Inventory Telemetry CLI.

Queries connected USB controllers and peripheral devices (keyboards, trackpads, security tokens,
mass storage, audio/video devices) using read-only Darwin system_profiler SPUSBDataType in strict
compliance with SC-01 and INV-USB-02 privacy constraints.
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

from system_mind.macos.usb_detector import MacUsbDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def print_device_tree(device, indent: str = "        ") -> None:
    """Recursively render a USB device and its connected children."""
    builtin_tag = " [BUILT-IN]" if device.is_builtin else " [EXTERNAL]"
    hub_tag = " [HUB]" if device.is_hub else ""
    class_tag = f" [{device.device_class.value}]"
    print(f"{indent}* {device.name}{builtin_tag}{hub_tag}{class_tag}")

    details = []
    if device.vendor_id or device.product_id:
        details.append(f"VID/PID: {device.vendor_id or 'N/A'}:{device.product_id or 'N/A'}")
    if device.manufacturer:
        details.append(f"Mfr: {device.manufacturer}")
    if device.speed.value != "UNKNOWN":
        details.append(f"Speed: {device.speed.value}")
    if details:
        print(f"{indent}  { ' | '.join(details) }")

    power_details = []
    if device.bus_power_ma is not None:
        power_details.append(f"Req: {device.bus_power_ma} mA")
    if device.current_used_ma is not None:
        power_details.append(f"Used: {device.current_used_ma} mA")
    if power_details:
        print(f"{indent}  Current: { ' | '.join(power_details) }")

    if device.anonymized_serial_hash:
        print(f"{indent}  Serial Hash: {device.anonymized_serial_hash} (INV-USB-02 anonymized)")

    if device.location_id:
        print(f"{indent}  Location ID: {device.location_id}")

    for child in device.children:
        print_device_tree(child, indent + "    ")


def print_human_report(report) -> None:
    """Render structured human-readable terminal report."""
    print("=" * 80)
    print(" SYSTEM MIND X — macOS USB & Peripheral Inventory Telemetry")
    print("=" * 80)
    print(f"  Collection Method:           {report.collection_method}")
    print(f"  Total USB Controllers:       {report.total_controller_count}")
    print(f"  Total Devices Discovered:    {report.total_device_count}")
    print(f"  External Devices Present:    {'Yes' if report.has_external_devices else 'No'}")
    print(f"  Security Keys / Tokens:      {'Detected' if report.has_security_tokens else 'None'}")
    print(f"  Mass Storage Devices:        {'Detected' if report.has_mass_storage else 'None'}")

    print("-" * 80)
    print(f" USB Host Controllers ({len(report.controllers)} total):")

    for i, ctrl in enumerate(report.controllers, start=1):
        print(f"\n  [{i}] {ctrl.name}")
        if ctrl.host_controller:
            print(f"      Driver: {ctrl.host_controller}")
        if ctrl.pci_device or ctrl.pci_vendor:
            print(f"      PCI IDs: Vendor={ctrl.pci_vendor or 'N/A'}, Device={ctrl.pci_device or 'N/A'}")

        if ctrl.devices:
            print(f"      Connected Devices ({len(ctrl.devices)} root):")
            for dev in ctrl.devices:
                print_device_tree(dev, indent="        ")
        else:
            print("      Connected Devices: None")

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
        description="Query macOS USB controllers and peripheral inventory using unprivileged Darwin APIs.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full telemetry snapshot as structured JSON.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate Apple Silicon USB and peripheral telemetry via safe mock adapter.",
    )
    parser.add_argument(
        "--assert-usb",
        action="store_true",
        help="Assert that at least one USB controller was successfully detected; exit 1 if zero.",
    )
    parser.add_argument(
        "--assert-devices",
        type=int,
        metavar="MIN_COUNT",
        help="Assert that at least MIN_COUNT devices were detected; exit 1 if fewer.",
    )

    args = parser.parse_args()

    detector = MacUsbDetector()
    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = detector.detect(use_mock=args.mock, mock_adapter=mock_adapter)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print_human_report(report)

    if args.assert_usb and report.total_controller_count < 1:
        sys.stderr.write("Assertion failed: Zero USB controllers detected.\n")
        return 1

    if args.assert_devices is not None and report.total_device_count < args.assert_devices:
        sys.stderr.write(
            f"Assertion failed: Detected {report.total_device_count} devices, expected at least {args.assert_devices}.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
