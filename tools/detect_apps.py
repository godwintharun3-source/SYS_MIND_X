#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS installed application inventory CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.core.types import ComponentOwnership
from system_mind.macos.app_detector import MacAppDetector
from system_mind.macos.app_models import ApplicationCategory, MacAppInfo


def print_report_table(
    applications: List[MacAppInfo],
    collection_method: str,
    total_apps: int,
    system_count: int,
    vendor_count: int,
    user_count: int,
    filter_label: str = "",
) -> None:
    """Print formatted summary and application table."""
    print("=" * 115)
    print(" SYSTEM MIND X — macOS Installed Application Inventory & Bundle Identifiers")
    print("=" * 115)
    print(f"  Collection Method:           {collection_method}")
    print(f"  Total Applications:          {total_apps}")
    print(f"  System-Managed (Apple):      {system_count}")
    print(f"  Vendor-Managed (3rd-Party):  {vendor_count}")
    print(f"  User-Managed:                {user_count}")
    if filter_label:
        print(f"  [Active Filter]              {filter_label}")
    print("-" * 115)

    if applications:
        print(f" {'NAME':<24} {'CATEGORY':<16} {'OWNERSHIP':<16} {'VERSION':<12} {'BUNDLE IDENTIFIER'}")
        print("-" * 115)
        for app in applications:
            name_disp = (app.name[:21] + "...") if len(app.name) > 24 else app.name
            ver_disp = (app.version[:10] + "..") if len(app.version) > 12 else app.version
            print(f" {name_disp:<24} {app.category.value:<16} {app.ownership.value:<16} {ver_disp:<12} {app.bundle_id}")
        print("=" * 115)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect macOS installed application bundles and bundle identifiers read-only.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full application inventory as formatted JSON",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock platform adapter collection",
    )
    parser.add_argument(
        "--ownership",
        type=str,
        choices=[o.value for o in ComponentOwnership],
        help="Filter applications by maintenance ownership tier",
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=[c.value for c in ApplicationCategory],
        help="Filter applications by functional category",
    )
    parser.add_argument(
        "--user-apps",
        action="store_true",
        help="Filter to user/third-party applications only (is_user_app=True)",
    )
    parser.add_argument(
        "--system-apps",
        action="store_true",
        help="Filter to Apple system-managed applications only",
    )
    parser.add_argument(
        "--assert-apps",
        type=int,
        default=0,
        metavar="MIN_COUNT",
        help="Assert at least MIN_COUNT applications are discovered (exits non-zero if unsatisfied)",
    )

    args = parser.parse_args()

    detector = MacAppDetector()
    report = detector.detect(mock=args.mock)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        if args.assert_apps > 0 and report.total_applications_count < args.assert_apps:
            sys.stderr.write(
                f"Error: Expected at least {args.assert_apps} applications, found {report.total_applications_count}\n"
            )
            return 1
        return 0

    apps = report.applications
    filter_desc = []

    if args.ownership:
        target_ownership = ComponentOwnership(args.ownership)
        apps = [a for a in apps if a.ownership == target_ownership]
        filter_desc.append(f"Ownership={args.ownership}")

    if args.category:
        target_category = ApplicationCategory(args.category)
        apps = [a for a in apps if a.category == target_category]
        filter_desc.append(f"Category={args.category}")

    if args.user_apps:
        apps = [a for a in apps if a.is_user_app]
        filter_desc.append("User/Third-Party Apps Only")

    if args.system_apps:
        apps = [a for a in apps if a.is_apple]
        filter_desc.append("System Core Apps Only")

    print_report_table(
        applications=apps,
        collection_method=report.collection_method,
        total_apps=report.total_applications_count,
        system_count=report.system_managed_count,
        vendor_count=report.vendor_managed_count,
        user_count=report.user_managed_count,
        filter_label=", ".join(filter_desc) if filter_desc else "",
    )

    if args.assert_apps > 0 and report.total_applications_count < args.assert_apps:
        sys.stderr.write(
            f"Error: Expected at least {args.assert_apps} applications, found {report.total_applications_count}\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
