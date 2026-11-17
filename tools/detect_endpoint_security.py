#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS Endpoint Security feasibility and entitlement audit CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.endpoint_security_detector import MacEndpointSecurityDetector
from system_mind.macos.endpoint_security_models import (
    EsClientResultCode,
    EsFeasibilityReport,
    EsStatus,
)


def print_feasibility_table(report: EsFeasibilityReport, audit_only: bool = False) -> None:
    """Print formatted terminal report and Endpoint Security audit table."""
    ent = report.entitlement_check

    print("=" * 115)
    print(" SYSTEM MIND X — macOS Endpoint Security Feasibility & Entitlement Audit")
    print("=" * 115)
    print(f"  Host Platform:         {report.host_platform}")
    print(f"  Feasibility Status:    {report.status.value}")
    print(f"  Native ES Result:      {report.result_code.name} (Code {report.result_code.value})")
    print(f"  Execution Mode:        {'MOCK FIXTURE' if report.is_mock else 'LIVE HOST INSPECTION'}")
    print(f"  Operational Status:    {'READY (ENTITLED)' if report.is_operational else 'RESTRICTED (FALLBACKS ACTIVE)'}")
    print(f"  Requires Escalation:   {'YES (Blocked by least-privilege boundary)' if report.requires_escalation else 'NO'}")
    print("  Charter Invariant:     Scan != Safe (Kernel audit signals do not prove application safety)")
    print("-" * 115)
    print("  ENTITLEMENT & HOST SECURITY AUDIT:")
    print(f"    • Process Execution UID:      {ent.uid} ({'root / elevated' if ent.is_root else 'unprivileged companion user'})")
    print(f"    • System Integrity Protection: {ent.sip_status_raw}")
    print(f"    • Framework Library:          {ent.framework_path} ({'Present' if ent.framework_binary_present else 'Missing'})")
    print(f"    • Required Entitlement:       {ent.entitlement_key}")
    print(f"    • Entitlement Verified:       {'YES (Apple Approved)' if ent.has_endpoint_security_entitlement else 'NO (Requires Apple Business Grant)'}")
    if ent.team_id:
        print(f"    • Developer Team ID:          {ent.team_id}")
    print(f"    • TCC Full Disk Access:       {'Accessible' if ent.tcc_full_disk_access_probable else 'Restricted / User Scope'}")
    print("-" * 115)

    if ent.diagnostics:
        print("  DIAGNOSTIC TRACE:")
        for diag in ent.diagnostics:
            print(f"    [i] {diag}")
        print("-" * 115)

    if not audit_only:
        print("  ACTIVE COMPANION FALLBACK STRATEGIES:")
        for domain, strat in report.fallback_strategies.items():
            print(f"    • {domain.upper():<22}: {strat}")
        print("-" * 115)

        if report.unavailable_telemetry:
            print("  UNAVAILABLE TELEMETRY (Protected by macOS Kernel / Entitlement Boundary):")
            for item in report.unavailable_telemetry:
                print(f"    [!] {item}")
            print("-" * 115)

        if report.sample_events:
            print(f"  CAPTURED / SIMULATED EVENT SAMPLES ({len(report.sample_events)} events):")
            print(f"   {'EVENT ID':<12} {'TYPE':<15} {'ACTION':<8} {'PID':<8} {'EXECUTABLE PATH'}")
            print("   " + "-" * 110)
            for ev in report.sample_events:
                print(f"   {ev.event_id:<12} {ev.event_type.value:<15} {ev.action_type.value:<8} {ev.process_pid:<8} {ev.executable_path}")
            print("-" * 115)


def main() -> int:
    """CLI entrypoint for macOS Endpoint Security feasibility inspection."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Read-only macOS Endpoint Security feasibility & entitlement auditor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock report profile instead of inspecting live host",
    )
    parser.add_argument(
        "--profile",
        choices=["restricted_companion", "entitled_daemon", "unsupported_platform"],
        default="restricted_companion",
        help="Mock profile to simulate (default: restricted_companion)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON data instead of tabular terminal output",
    )
    parser.add_argument(
        "--audit-entitlements",
        action="store_true",
        help="Focus display on entitlement checklist and SIP state",
    )
    parser.add_argument(
        "--target-binary",
        type=str,
        default=None,
        help="Path to binary to inspect code signatures and entitlements (default: python runtime)",
    )

    args = parser.parse_args()

    detector = MacEndpointSecurityDetector(target_binary_path=args.target_binary)
    report = detector.detect(use_mock=args.mock, profile=args.profile)

    if args.json:
        print(report.to_json())
    else:
        print_feasibility_table(report, audit_only=args.audit_entitlements)

    return 0


if __name__ == "__main__":
    sys.exit(main())
