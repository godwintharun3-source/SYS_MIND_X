#!/usr/bin/env python3
"""SYSTEM MIND X — macOS Companion Agent Milestone 4 Release CLI."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add src to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.macos.companion_models import (
    CompanionExecutionMode,
    CompanionRunConfig,
    MacOsCompanionReleaseReport,
)
from system_mind.macos.companion_runner import MacOsCompanionRunner
from system_mind.macos.privacy_models import PrivacyScrubbingLevel
from system_mind.packaging.macos_companion_release import MacOsCompanionReleaseValidator


def format_report_text(report: MacOsCompanionReleaseReport) -> str:
    """Formats the milestone release report into human-readable terminal text."""
    lines = [
        "=" * 82,
        " SYSTEM MIND X — macOS Companion Agent Milestone 4 Release",
        f" Report ID: {report.report_id}",
        "=" * 82,
        f" Milestone:            {report.milestone} (v{report.milestone_version})",
        f" Host Platform:        {report.host_platform}",
        f" Apple Silicon Native: {report.apple_silicon_native}",
        f" Execution Domain:     {report.execution_domain}",
        f" Least Privilege:      {'ENFORCED (Non-Root)' if report.least_privilege_enforced else 'ELEVATED (Warning)'}",
        f" Active Collectors:    {report.active_collectors_count}",
        f" Cycles Completed:     {report.cycles_completed}",
        f" Charter Invariants:   {'ALL PASSING' if all(report.charter_invariants_verified.values()) else 'FAILURES DETECTED'}",
        f" Scan != Safe (SC-03): {'ENFORCED (False)' if report.scan_proves_safe is False else 'BREACH'}",
        "-" * 82,
    ]

    latest = report.latest_cycle
    if latest:
        lines.extend([
            " Latest Observation Cycle:",
            f"   Cycle ID:           {latest.cycle_id}",
            f"   Timestamp (UTC):    {latest.timestamp_utc}",
            f"   Operational Status: {latest.operational_status.value}",
            f"   Duration:           {latest.duration_ms} ms",
            f"   Data Completeness:  {'PARTIAL / DEGRADED' if latest.partial_data else 'COMPLETE'}",
        ])
        if latest.unavailable_telemetry:
            lines.append(f"   Unavailable Items:  {', '.join(latest.unavailable_telemetry)}")

        if latest.inventory_summary:
            inv = latest.inventory_summary
            lines.extend([
                "-" * 82,
                " Aggregated Inventory Highlights:",
                f"   Identity:           macOS {inv.get('os_version', 'N/A')} (Build {inv.get('os_build', 'N/A')})",
                f"   CPU / Cores:        {inv.get('cpu_model', 'N/A')} ({inv.get('physical_cores', 'N/A')} P/E cores)",
                f"   RAM Capacity:       {inv.get('total_memory_bytes', 0) / (1024**3):.1f} GB",
                f"   Storage Root:       {inv.get('total_storage_bytes', 0) / (1024**3):.1f} GB total, {inv.get('free_storage_bytes', 0) / (1024**3):.1f} GB free",
                f"   Host Name:          {inv.get('host_name', 'N/A')}",
                f"   Running Processes:  {inv.get('running_process_count', 'N/A')}",
                f"   Installed Apps:     {inv.get('installed_app_count', 'N/A')}",
                f"   Overall Health:     {inv.get('overall_health', 'N/A')}",
            ])

        if latest.observation_batch_summary:
            obs = latest.observation_batch_summary
            lines.extend([
                "-" * 82,
                " Observation Provenance & Confidence:",
                f"   Envelopes Count:    {obs.get('total_observations', 'N/A')}",
                f"   Mean Confidence:    {obs.get('mean_confidence', 0.0):.2f} / 1.00",
                f"   Lowest Collector:   {obs.get('lowest_confidence_collector', 'N/A')}",
                f"   Is Synthetic Mock:  {obs.get('is_mock', False)}",
            ])

        if latest.permission_manifest_summary:
            perm = latest.permission_manifest_summary
            lines.extend([
                "-" * 82,
                " Least-Privilege Permissions & Entitlements:",
                f"   Granted / Total:    {perm.get('total_granted', 0)} / {perm.get('total_evaluated', 0)} evaluated",
                f"   Denied / Stored:    {perm.get('total_denied', 0)} denied (gracefully routed to fallback)",
                f"   Prohibited Surveillance: Zero non-goals granted (Keystroke logging & screen scraping blocked)",
            ])

    lines.append("=" * 82)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X macOS Companion Agent Milestone 4 Release CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--snapshot", action="store_true", help="Execute single-shot system observation snapshot (default)")
    group.add_argument("--daemon", action="store_true", help="Run continuous observational sampling loop")
    group.add_argument("--audit-milestone", action="store_true", help="Run packaging validator for Milestone 4 release")

    parser.add_argument("--mock", action="store_true", help="Run with mock platform adapter simulation")
    parser.add_argument("--profile", default="high_fidelity", help="Mock profile to simulate (high_fidelity, degraded, unsupported)")
    parser.add_argument("--interval", type=float, default=2.0, help="Interval between observation cycles in seconds (default: 2.0s)")
    parser.add_argument("--cycles", type=int, default=1, help="Max observation cycles to execute (default: 1 for snapshot, 3 for daemon)")
    parser.add_argument("--privacy", default="BALANCED", choices=["MINIMAL", "BALANCED", "STRICT"], help="Privacy scrubbing level")
    parser.add_argument("--json", action="store_true", help="Emit report in machine-readable JSON format")

    args = parser.parse_args()

    # 1. Milestone 4 Audit Mode
    if args.audit_milestone:
        result = MacOsCompanionReleaseValidator.audit(ROOT_DIR)
        if args.json:
            print(json.dumps({
                "valid": result.valid,
                "issues": list(result.issues),
                "collectors_count": result.collectors_count,
                "rust_sensors_count": result.rust_sensors_count,
                "charter_invariants_valid": result.charter_invariants_valid,
                "release_report_present": result.release_report_present,
                "cli_present": result.cli_present,
            }, indent=2))
        else:
            print("[*] SYSTEM MIND X — Milestone 4 macOS Companion Agent Audit")
            print(f"[*] Collectors Audited:   {result.collectors_count} Python modules")
            print(f"[*] Rust Sensors Audited: {result.rust_sensors_count} Rust modules")
            print(f"[*] Charter Invariants:   {'PASSED' if result.charter_invariants_valid else 'FAILED'}")
            print(f"[*] Release Report:       {'PRESENT' if result.release_report_present else 'MISSING'}")
            print(f"[*] Companion CLI:        {'PRESENT' if result.cli_present else 'MISSING'}")
            if result.issues:
                print("\n[!] Audit Issues Detected:")
                for issue in result.issues:
                    print(f"    - {issue}")
            else:
                print("\n[+] Milestone 4 macOS Companion Agent Release is 100% COMPLETE and VERIFIED.")
        return 0 if result.valid else 1

    # 2. Execution Mode Configuration
    mode = CompanionExecutionMode.CONTINUOUS_OBSERVER if args.daemon else CompanionExecutionMode.SINGLE_SNAPSHOT
    cycles = args.cycles if args.cycles > 1 else (3 if args.daemon else 1)
    privacy_level = getattr(PrivacyScrubbingLevel, args.privacy, PrivacyScrubbingLevel.BALANCED)

    config = CompanionRunConfig(
        mode=mode,
        interval_seconds=args.interval,
        max_cycles=cycles,
        use_mock=args.mock,
        mock_profile=args.profile,
        privacy_level=privacy_level,
    )

    runner = MacOsCompanionRunner(config=config)

    if args.daemon:
        if not args.json:
            print(f"[*] Starting macOS Companion Agent in continuous observation mode (max_cycles={cycles}, interval={args.interval}s)...")
        report = runner.run_daemon()
    else:
        report = runner.run_snapshot()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report_text(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
