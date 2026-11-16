#!/usr/bin/env python3
"""SYSTEM MIND X — macOS Process Inventory & Resource Usage Telemetry CLI.

Queries active Darwin operating system processes, PID, PPID, owner, CPU %, memory %, RSS bytes,
VSZ bytes, state flags, and component roles using unprivileged Darwin ps in strict compliance
with SC-01 and INV-PROC-04 read-only constraints.
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

from system_mind.macos.process_detector import MacProcessDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def print_human_report(
    report,
    top_cpu: int = 0,
    top_mem: int = 0,
    user_filter: str = "",
) -> None:
    """Render structured human-readable terminal table."""
    print("=" * 95)
    print(" SYSTEM MIND X — macOS Process Inventory & Resource Usage Telemetry")
    print("=" * 95)
    print(f"  Collection Method:           {report.collection_method}")
    print(f"  Total Processes:             {report.total_process_count}")
    print(f"  Running Processes:           {report.running_count}")
    print(f"  Sleeping Processes:          {report.sleeping_count}")
    print(f"  Zombie Processes:            {report.zombie_count}")
    print(f"  System Core Processes:       {report.system_core_count}")
    print(f"  User Desktop Apps:           {report.user_app_count}")
    print(f"  Total CPU Utilization:       {report.total_cpu_percent:.1f}%")
    rss_mb = report.total_rss_bytes / (1024 * 1024)
    print(f"  Total Resident Set Size:     {rss_mb:.1f} MB")

    procs = list(report.processes)
    if user_filter:
        procs = report.filter_by_user(user_filter)
        print(f"  [Filter] Filtered by User:   {user_filter} ({len(procs)} matching)")

    if top_cpu > 0:
        procs = sorted(procs, key=lambda p: p.cpu_percent, reverse=True)[:top_cpu]
        print(f"  [Filter] Displaying Top {top_cpu} by CPU%")
    elif top_mem > 0:
        procs = sorted(procs, key=lambda p: p.rss_bytes, reverse=True)[:top_mem]
        print(f"  [Filter] Displaying Top {top_mem} by Memory (RSS)")
    else:
        # Default preview first 25 processes
        if len(procs) > 25:
            procs = procs[:25]
            print("  [Preview] Displaying first 25 processes (use --top-cpu or --top-mem for more)")

    print("-" * 95)
    header = f"{'PID':>6}  {'PPID':>6}  {'USER':<14}  {'%CPU':>5}  {'RSS (MB)':>9}  {'STATE':<6}  {'ROLE':<15}  {'NAME'}"
    print(header)
    print("-" * 95)

    for p in procs:
        p_rss_mb = p.rss_bytes / (1024 * 1024)
        print(
            f"{p.pid:>6}  {p.ppid:>6}  {p.user[:14]:<14}  {p.cpu_percent:>5.1f}  {p_rss_mb:>9.1f}  {p.state_raw[:6]:<6}  {p.role.value[:15]:<15}  {p.name}"
        )

    if report.warnings:
        print("-" * 95)
        print(" Warnings & Anomalies:")
        for w in report.warnings:
            print(f"  [WARN] {w}")

    if report.unavailable_telemetry:
        print("-" * 95)
        print(" Unavailable Metrics on Host:")
        for u in report.unavailable_telemetry:
            print(f"  [UNAVAILABLE] {u}")

    print("=" * 95)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query macOS active process inventory and resource telemetry using unprivileged ps.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full process inventory as structured JSON.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate Apple Silicon process table via safe mock adapter.",
    )
    parser.add_argument(
        "--top-cpu",
        type=int,
        default=0,
        metavar="N",
        help="Display top N processes ranked by CPU utilization percentage.",
    )
    parser.add_argument(
        "--top-mem",
        type=int,
        default=0,
        metavar="N",
        help="Display top N processes ranked by Resident Set Size (RSS) memory consumption.",
    )
    parser.add_argument(
        "--user",
        type=str,
        default="",
        metavar="USERNAME",
        help="Filter process table to processes owned by USERNAME.",
    )
    parser.add_argument(
        "--assert-processes",
        type=int,
        metavar="MIN_COUNT",
        help="Assert that at least MIN_COUNT active processes are present; exit 1 if fewer.",
    )

    args = parser.parse_args()

    detector = MacProcessDetector()
    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = detector.detect(use_mock=args.mock, mock_adapter=mock_adapter)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print_human_report(
            report,
            top_cpu=args.top_cpu,
            top_mem=args.top_mem,
            user_filter=args.user,
        )

    if args.assert_processes is not None and report.total_process_count < args.assert_processes:
        sys.stderr.write(
            f"Assertion failed: Detected {report.total_process_count} processes, expected at least {args.assert_processes}.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
