#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS application signature and notarization CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.signature_detector import MacAppSignatureDetector
from system_mind.macos.signature_models import (
    MacAppSignatureInfo,
    NotarizationStatus,
    SignatureStatus,
    SigningAuthorityType,
)


def print_signature_table(
    signatures: List[MacAppSignatureInfo],
    collection_method: str,
    total_inspected: int,
    validly_signed: int,
    notarized: int,
    apple_system: int,
    unsigned: int,
    filter_label: str = "",
) -> None:
    """Print formatted terminal report and signature inspection table."""
    print("=" * 125)
    print(" SYSTEM MIND X — macOS Application Signatures & Gatekeeper Notarization Telemetry")
    print("=" * 125)
    print(f"  Collection Method:           {collection_method}")
    print(f"  Total Inspected Bundles:     {total_inspected}")
    print(f"  Validly Signed (Strict):     {validly_signed}")
    print(f"  Notarized / System Verified: {notarized}")
    print(f"  Apple First-Party System:    {apple_system}")
    print(f"  Unsigned Binaries:           {unsigned}")
    print("  Charter Non-Negotiable:      Scan != Safe (All models enforce scan_proves_safe=False)")
    if filter_label:
        print(f"  [Active Filter]              {filter_label}")
    print("-" * 125)

    if signatures:
        print(
            f" {'BUNDLE IDENTIFIER':<30} {'STATUS':<15} {'NOTARIZATION':<24} "
            f"{'AUTHORITY':<16} {'TEAM ID':<12} {'RUNTIME':<8} {'SAFE?'}"
        )
        print("-" * 125)
        for sig in signatures:
            bid_disp = (sig.bundle_id[:27] + "...") if len(sig.bundle_id) > 30 else sig.bundle_id
            team_disp = sig.team_id or "-"
            runtime_disp = "Yes" if sig.is_hardened_runtime else "No"
            safe_disp = "False" if not sig.scan_proves_safe else "True"
            print(
                f" {bid_disp:<30} {sig.signature_status.value:<15} {sig.notarization_status.value:<24} "
                f"{sig.authority_type.value:<16} {team_disp:<12} {runtime_disp:<8} {safe_disp}"
            )
        print("=" * 125)
    else:
        print("  No application signatures matched the query or filter criteria.")
        print("=" * 125)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect macOS application bundle code signatures, CDHashes, and Gatekeeper notarization status read-only.",
    )
    parser.add_argument(
        "--path",
        "-p",
        "--app",
        type=str,
        dest="path",
        default=None,
        help="Path to a specific application bundle (.app) or executable to inspect.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate Apple Silicon application signature telemetry via MockPlatformAdapter.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full signature report as structured JSON.",
    )
    parser.add_argument(
        "--max-apps",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of applications to inspect during inventory discovery.",
    )
    parser.add_argument(
        "--filter",
        choices=["signed", "unsigned", "notarized", "apple", "developer", "adhoc"],
        default=None,
        help="Filter displayed applications by signature or notarization status.",
    )
    parser.add_argument(
        "--notarized",
        action="store_true",
        help="Filter to notarized / Apple system applications only.",
    )
    parser.add_argument(
        "--unsigned",
        action="store_true",
        help="Filter to unsigned applications only.",
    )
    parser.add_argument(
        "--assert-signatures",
        type=int,
        default=0,
        metavar="MIN_COUNT",
        help="Assert at least MIN_COUNT applications inspected (exits non-zero if unsatisfied).",
    )

    args = parser.parse_args()

    detector = MacAppSignatureDetector()

    target_paths: Optional[List[Path | str]] = None
    if args.path:
        target_paths = [args.path]

    report = detector.detect(bundle_paths=target_paths, max_apps=args.max_apps, mock=args.mock)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        if args.assert_signatures > 0 and report.inspected_apps_count < args.assert_signatures:
            sys.stderr.write(
                f"Error: Expected at least {args.assert_signatures} signatures, found {report.inspected_apps_count}\n"
            )
            return 1
        return 0

    signatures_to_display = report.signatures
    filter_label = ""
    if args.filter == "signed":
        signatures_to_display = [s for s in report.signatures if s.signature_status == SignatureStatus.SIGNED_VALID]
        filter_label = "Validly Signed (Strict)"
    elif args.filter == "unsigned" or args.unsigned:
        signatures_to_display = [s for s in report.signatures if s.signature_status == SignatureStatus.UNSIGNED]
        filter_label = "Unsigned Binaries"
    elif args.filter == "notarized" or args.notarized:
        signatures_to_display = [s for s in report.signatures if s.is_notarized]
        filter_label = "Apple Notarized / System Verified"
    elif args.filter == "apple":
        signatures_to_display = [s for s in report.signatures if s.is_apple]
        filter_label = "Apple First-Party Applications"
    elif args.filter == "developer":
        signatures_to_display = [s for s in report.signatures if s.authority_type == SigningAuthorityType.DEVELOPER_ID]
        filter_label = "Identified Developer ID Applications"
    elif args.filter == "adhoc":
        signatures_to_display = [s for s in report.signatures if s.signature_status == SignatureStatus.ADHOC_SIGNED]
        filter_label = "Ad-Hoc Signed Applications"

    print_signature_table(
        signatures=signatures_to_display,
        collection_method=report.collection_method,
        total_inspected=report.inspected_apps_count,
        validly_signed=report.validly_signed_count,
        notarized=report.notarized_count,
        apple_system=report.apple_system_count,
        unsigned=report.unsigned_count,
        filter_label=filter_label,
    )

    if args.assert_signatures > 0 and report.inspected_apps_count < args.assert_signatures:
        sys.stderr.write(
            f"Error: Expected at least {args.assert_signatures} signatures, found {report.inspected_apps_count}\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
