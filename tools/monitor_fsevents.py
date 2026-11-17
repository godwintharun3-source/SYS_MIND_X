#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS FSEvents filesystem change notifications CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.fsevents_detector import MacFsEventsDetector
from system_mind.macos.fsevents_models import (
    FsEventFlag,
    FsEventNotification,
    FsEventSnapshotReport,
)


def print_events_table(
    events: List[FsEventNotification],
    collection_method: str,
    total_events: int,
    created_count: int,
    modified_count: int,
    removed_count: int,
    renamed_count: int,
    monitored_paths: List[str],
    filter_label: str = "",
) -> None:
    """Print formatted summary and filesystem events table."""
    print("=" * 120)
    print(" SYSTEM MIND X — macOS FSEvents Filesystem Change Notifications Telemetry")
    print("=" * 120)
    print(f"  Collection Method:     {collection_method}")
    print(f"  Monitored Roots:       {len(monitored_paths)} ({', '.join(monitored_paths)})")
    print(f"  Total Events:          {total_events}")
    print(f"  Created:               {created_count}")
    print(f"  Modified:              {modified_count}")
    print(f"  Removed:               {removed_count}")
    print(f"  Renamed:               {renamed_count}")
    print("  Privacy Policy:        Personal folders (~/.ssh, Keychains, credentials) strictly excluded")
    if filter_label:
        print(f"  [Active Filter]        {filter_label}")
    print("-" * 120)

    if events:
        print(f" {'EVENT ID':<10} {'ITEM TYPE':<10} {'FLAGS':<35} {'PATH'}")
        print("-" * 120)
        for ev in events:
            item_type = "DIR" if ev.is_dir else ("SYMLINK" if ev.is_symlink else "FILE")
            flags_str = ", ".join(f.value.replace("ITEM_", "") for f in ev.flags[:3])
            path_disp = (ev.path[:55] + "...") if len(ev.path) > 58 else ev.path
            print(f" {ev.event_id:<10} {item_type:<10} {flags_str:<35} {path_disp}")
        print("=" * 120)
    else:
        print("  No filesystem events matched the query or filter criteria.")
        print("=" * 120)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor and inspect macOS FSEvents filesystem change notifications read-only.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full FSEvents report as structured JSON",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate Apple Silicon FSEvents change notifications via MockPlatformAdapter",
    )
    parser.add_argument(
        "--paths",
        type=str,
        default=None,
        help="Comma-separated list of filesystem paths to monitor",
    )
    parser.add_argument(
        "--flag",
        type=str,
        choices=[f.value for f in FsEventFlag],
        default=None,
        help="Filter events containing a specific FsEventFlag",
    )
    parser.add_argument(
        "--created",
        action="store_true",
        help="Filter to item creation events only",
    )
    parser.add_argument(
        "--modified",
        action="store_true",
        help="Filter to item modification events only",
    )
    parser.add_argument(
        "--removed",
        action="store_true",
        help="Filter to item removal events only",
    )
    parser.add_argument(
        "--renamed",
        action="store_true",
        help="Filter to item rename events only",
    )
    parser.add_argument(
        "--assert-events",
        type=int,
        default=0,
        metavar="MIN_COUNT",
        help="Assert at least MIN_COUNT events discovered/collected (exits non-zero if unsatisfied)",
    )

    args = parser.parse_args()

    paths_list = [p.strip() for p in args.paths.split(",")] if args.paths else None

    detector = MacFsEventsDetector(monitored_paths=paths_list)
    report = detector.detect(mock=args.mock, paths=paths_list)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        if args.assert_events > 0 and report.events_count < args.assert_events:
            sys.stderr.write(
                f"Error: Expected at least {args.assert_events} events, found {report.events_count}\n"
            )
            return 1
        return 0

    events = report.events
    filter_desc = []

    if args.flag:
        target_flag = FsEventFlag(args.flag)
        events = report.filter_by_flag(target_flag)
        filter_desc.append(f"Flag={args.flag}")

    if args.created:
        events = [e for e in events if e.is_created]
        filter_desc.append("Created Only")

    if args.modified:
        events = [e for e in events if e.is_modified]
        filter_desc.append("Modified Only")

    if args.removed:
        events = [e for e in events if e.is_removed]
        filter_desc.append("Removed Only")

    if args.renamed:
        events = [e for e in events if e.is_renamed]
        filter_desc.append("Renamed Only")

    print_events_table(
        events=events,
        collection_method=report.collection_method,
        total_events=report.events_count,
        created_count=report.created_count,
        modified_count=report.modified_count,
        removed_count=report.removed_count,
        renamed_count=report.renamed_count,
        monitored_paths=report.monitored_paths,
        filter_label=", ".join(filter_desc) if filter_desc else "",
    )

    if args.assert_events > 0 and report.events_count < args.assert_events:
        sys.stderr.write(
            f"Error: Expected at least {args.assert_events} events, found {report.events_count}\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
