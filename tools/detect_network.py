#!/usr/bin/env python3
"""SYSTEM MIND X — macOS Network Interfaces and Connectivity Telemetry CLI.

Queries network interfaces, link states, MTU, IP addresses, default gateway, and DNS
nameservers using read-only Darwin ifconfig, networksetup, scutil, and netstat interfaces
in strict compliance with SC-01 and privacy constraints.
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

from system_mind.macos.network_detector import MacNetworkDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def print_human_report(report) -> None:
    """Render structured human-readable terminal report."""
    print("=" * 80)
    print(" SYSTEM MIND X — macOS Network Interfaces & Connectivity Telemetry")
    print("=" * 80)
    print(f"  Collection Method:           {report.collection_method}")
    print(f"  Primary Interface:           {report.primary_interface_name or 'None'}")
    print(f"  WAN Internet Connectivity:   {report.is_online}")
    print(f"  Default IPv4 Gateway:        {report.default_gateway or 'None'}")

    dns_str = ", ".join(report.dns_servers) if report.dns_servers else "None"
    print(f"  Configured DNS Nameservers:  {dns_str}")

    if report.search_domains:
        print(f"  DNS Search Domains:          {', '.join(report.search_domains)}")

    print("-" * 80)
    print(f" Detected Network Interfaces ({len(report.interfaces)} total):")

    for iface in report.interfaces:
        primary_tag = " [PRIMARY]" if iface.is_primary else ""
        port_desc = f" ({iface.hardware_port})" if iface.hardware_port else ""
        print(f"\n  * {iface.name}{primary_tag}{port_desc}")
        print(f"    Type:       {iface.interface_type.value} | Link State: {iface.link_state.value} | MTU: {iface.mtu}")

        if iface.anonymized_mac_hash:
            print(f"    MAC (Hash): {iface.anonymized_mac_hash} (anonymized for privacy)")
        elif iface.mac_address:
            print(f"    MAC:        {iface.mac_address}")

        if iface.media:
            print(f"    Media:      {iface.media}")

        if iface.flags:
            print(f"    Flags:      <{','.join(iface.flags)}>")

        if iface.ip_addresses:
            print("    IP Bindings:")
            for ip in iface.ip_addresses:
                mask_str = f" netmask {ip.netmask}" if ip.netmask else ""
                pref_str = f"/{ip.prefixlen}" if ip.prefixlen is not None else ""
                scope_str = f" scope {ip.scope}" if ip.scope else ""
                bcast_str = f" broadcast {ip.broadcast}" if ip.broadcast else ""
                print(f"      - [{ip.family.upper()}] {ip.address}{pref_str}{mask_str}{bcast_str}{scope_str}")

    if report.warnings:
        print("-" * 80)
        print(" Collector Warnings:")
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
        description="SYSTEM MIND X — macOS Network Interfaces & Connectivity Telemetry CLI",
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
        "--assert-online",
        action="store_true",
        help="Assert that host has active Internet connectivity; exit with 1 if offline",
    )
    parser.add_argument(
        "--assert-interface",
        type=str,
        metavar="IFACE_NAME",
        help="Assert that specified interface exists and is active; exit with 1 if absent/down",
    )

    args = parser.parse_args()

    detector = MacNetworkDetector()
    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = detector.detect(use_mock=args.mock, mock_adapter=mock_adapter)

    # Evaluate assertion gates
    if args.assert_online:
        if not report.is_online:
            if not args.json:
                print("[-] Precondition FAILED: Host is offline or lacks a default gateway route.", file=sys.stderr)
            sys.exit(1)

    if args.assert_interface:
        target_name = args.assert_interface.strip()
        matched = [i for i in report.interfaces if i.name == target_name]
        if not matched:
            if not args.json:
                print(f"[-] Precondition FAILED: Interface '{target_name}' not found.", file=sys.stderr)
            sys.exit(1)
        if matched[0].link_state.value != "UP_ACTIVE":
            if not args.json:
                print(
                    f"[-] Precondition FAILED: Interface '{target_name}' link state is {matched[0].link_state.value}, expected UP_ACTIVE.",
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
