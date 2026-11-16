#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS launchd services and login-item inventory CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List

# Ensure repository src is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.services_detector import MacServicesDetector
from system_mind.macos.services_models import (
    MacLaunchdService,
    MacLoginItem,
    ServiceDomain,
    ServiceOwnership,
    ServiceStatus,
)


def print_report_table(
    services: List[MacLaunchdService],
    login_items: List[MacLoginItem],
    collection_method: str,
    total_services: int,
    running_services: int,
    loaded_services: int,
    system_count: int,
    vendor_count: int,
    user_count: int,
    filter_label: str = "",
) -> None:
    """Print formatted summary and service/login item tables."""
    print("=" * 105)
    print(" SYSTEM MIND X — macOS launchd Services & Login Items Inventory")
    print("=" * 105)
    print(f"  Collection Method:           {collection_method}")
    print(f"  Total Services Discovered:   {total_services}")
    print(f"  Running Services:            {running_services}")
    print(f"  Loaded in launchd:           {loaded_services}")
    print(f"  System-Managed (Apple):      {system_count}")
    print(f"  Vendor-Managed (3rd-Party):  {vendor_count}")
    print(f"  User-Managed:                {user_count}")
    print(f"  Login Items:                 {len(login_items)}")
    if filter_label:
        print(f"  [Active Filter]              {filter_label}")
    print("-" * 105)

    if services:
        print(f" {'STATUS':<15} {'DOMAIN':<16} {'OWNERSHIP':<16} {'PID':<8} {'LABEL':<45}")
        print("-" * 105)
        for s in services:
            pid_str = str(s.pid) if s.pid is not None else "-"
            label_disp = (s.label[:42] + "...") if len(s.label) > 45 else s.label
            print(f" {s.status.value:<15} {s.domain.value:<16} {s.ownership.value:<16} {pid_str:<8} {label_disp:<45}")
        print("=" * 105)

    if login_items:
        print("\n [Desktop User Login Items]")
        print("-" * 105)
        print(f" {'NAME':<30} {'HIDDEN':<8} {'OWNERSHIP':<16} {'BUNDLE PATH'}")
        print("-" * 105)
        for item in login_items:
            path_str = item.path or "-"
            print(f" {item.name:<30} {str(item.hidden):<8} {item.ownership.value:<16} {path_str}")
        print("=" * 105)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect macOS launchd services and user login items read-only.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full telemetry as formatted JSON",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock platform adapter collection",
    )
    parser.add_argument(
        "--running",
        action="store_true",
        help="Filter to only actively running services (PID > 0)",
    )
    parser.add_argument(
        "--domain",
        type=str,
        choices=[d.value for d in ServiceDomain],
        help="Filter services by execution domain",
    )
    parser.add_argument(
        "--ownership",
        type=str,
        choices=[o.value for o in ServiceOwnership],
        help="Filter services by component ownership tier",
    )
    parser.add_argument(
        "--login-items",
        action="store_true",
        help="Only display desktop user login items",
    )
    parser.add_argument(
        "--assert-services",
        type=int,
        default=0,
        metavar="MIN_COUNT",
        help="Assert at least MIN_COUNT services are discovered (exits non-zero if not satisfied)",
    )

    args = parser.parse_args()

    detector = MacServicesDetector()
    report = detector.detect(mock=args.mock)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        if args.assert_services > 0 and report.total_services_count < args.assert_services:
            sys.stderr.write(
                f"Error: Expected at least {args.assert_services} services, found {report.total_services_count}\n"
            )
            return 1
        return 0

    services = report.services
    filter_desc = []

    if args.running:
        services = [s for s in services if s.is_running]
        filter_desc.append("Running Services Only")

    if args.domain:
        target_domain = ServiceDomain(args.domain)
        services = [s for s in services if s.domain == target_domain]
        filter_desc.append(f"Domain={args.domain}")

    if args.ownership:
        target_ownership = ServiceOwnership(args.ownership)
        services = [s for s in services if s.ownership == target_ownership]
        filter_desc.append(f"Ownership={args.ownership}")

    login_items = report.login_items
    if args.login_items:
        services = []
        filter_desc.append("Login Items Only")

    print_report_table(
        services=services,
        login_items=login_items if not services or args.login_items else report.login_items,
        collection_method=report.collection_method,
        total_services=report.total_services_count,
        running_services=report.running_services_count,
        loaded_services=report.loaded_services_count,
        system_count=report.system_managed_count,
        vendor_count=report.vendor_managed_count,
        user_count=report.user_managed_count,
        filter_label=", ".join(filter_desc) if filter_desc else "",
    )

    if args.assert_services > 0 and report.total_services_count < args.assert_services:
        sys.stderr.write(
            f"Error: Expected at least {args.assert_services} services, found {report.total_services_count}\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
