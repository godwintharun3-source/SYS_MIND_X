#!/usr/bin/env python3
"""SYSTEM MIND X — macOS telemetry collector health, timeout, and partial-data reporting CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.collector_health_manager import (
    CORE_COLLECTORS,
    CollectorHealthManager,
)
from system_mind.macos.collector_health_models import (
    CollectorHealthRecord,
    CollectorStatus,
    CompanionHealthReport,
)


def print_health_table(report: CompanionHealthReport) -> None:
    """Print formatted terminal report and collector health status table."""
    print("=" * 125)
    print(" SYSTEM MIND X — macOS Telemetry Collector Health & Partial-Data Report")
    print("=" * 125)
    print(f"  Host Platform:         {report.host_platform}")
    print(f"  Timestamp (UTC):       {report.timestamp}")
    print(f"  Execution Mode:        {'MOCK FIXTURE' if report.is_mock else 'LIVE COLLECTOR ORCHESTRATION'}")
    print(f"  Overall Status:        {report.overall_status.value}")
    print(f"  Total Collectors:      {report.total_collectors} (Healthy: {report.healthy_count}, "
          f"Degraded: {report.degraded_count}, Timed Out: {report.timed_out_count}, "
          f"Failed: {report.failed_count}, Unsupported: {report.unsupported_count})")
    print(f"  Partial Data Present:  {'Yes (Incomplete Telemetry Captured)' if report.partial_data_present else 'No (Full Parity)'}")
    print("  Charter Invariant:     Scan != Safe (Collector health does not prove host software safety)")
    print("-" * 125)
    print(f"  {'Collector ID':<20} | {'Status':<14} | {'Latency':<10} | {'Timeout':<8} | {'Failures':<8} | {'Partial Data / Notes':<45}")
    print("-" * 125)

    for cid in sorted(report.collectors.keys()):
        rec = report.collectors[cid]
        status_str = rec.status.value
        latency_str = f"{rec.latency_ms:.1f}ms"
        timeout_str = f"{rec.timeout_seconds:.1f}s"
        failures_str = str(rec.consecutive_failures)

        notes_parts: list[str] = []
        if rec.partial_reasons:
            notes_parts.append(f"Reasons: {', '.join(r.value for r in rec.partial_reasons)}")
        if rec.unavailable_fields:
            notes_parts.append(f"Missing: {', '.join(rec.unavailable_fields[:2])}")
        if rec.last_error:
            notes_parts.append(f"Err: {rec.last_error[:30]}")

        notes_str = "; ".join(notes_parts) if notes_parts else "Nominal / Full Parity"
        if len(notes_str) > 45:
            notes_str = notes_str[:42] + "..."

        print(f"  {cid:<20} | {status_str:<14} | {latency_str:<10} | {timeout_str:<8} | {failures_str:<8} | {notes_str:<45}")

    print("=" * 125)


def main() -> int:
    """CLI entrypoint for collector health and partial-data inspection."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Read-only macOS telemetry collector health & partial-data inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock report profile instead of running live collectors",
    )
    parser.add_argument(
        "--profile",
        choices=["healthy", "degraded", "timeout", "unsupported"],
        default="healthy",
        help="Mock profile to simulate (default: healthy)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON data instead of tabular terminal output",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Timeout in seconds per collector (default: 2.0)",
    )
    parser.add_argument(
        "--collector",
        type=str,
        default=None,
        help=f"Inspect a specific collector only: {', '.join(CORE_COLLECTORS)}",
    )

    args = parser.parse_args()

    manager = CollectorHealthManager(default_timeout_seconds=args.timeout)

    report = manager.collect_all_telemetry(use_mock=args.mock, profile=args.profile)

    if args.collector:
        if args.collector not in report.collectors:
            print(f"[!] Unknown collector '{args.collector}'. Available: {', '.join(CORE_COLLECTORS)}", file=sys.stderr)
            return 1
        single_rec = report.collectors[args.collector]
        if args.json:
            print(json.dumps(single_rec.to_dict(), indent=2))
        else:
            print(f"Collector ID:         {single_rec.collector_id}")
            print(f"Status:               {single_rec.status.value}")
            print(f"Latency:              {single_rec.latency_ms:.1f}ms")
            print(f"Timeout Budget:       {single_rec.timeout_seconds:.1f}s")
            print(f"Consecutive Failures: {single_rec.consecutive_failures}")
            print(f"Partial Data:         {single_rec.partial_data}")
            if single_rec.partial_reasons:
                print(f"Partial Reasons:      {', '.join(r.value for r in single_rec.partial_reasons)}")
            if single_rec.unavailable_fields:
                print(f"Unavailable Fields:   {', '.join(single_rec.unavailable_fields)}")
            if single_rec.last_error:
                print(f"Last Error:           {single_rec.last_error}")
        return 0

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_health_table(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
