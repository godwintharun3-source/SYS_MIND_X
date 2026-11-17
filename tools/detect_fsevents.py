#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS FSEvents filesystem change notification CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.fsevents_detector import MacFsEventsDetector
from system_mind.macos.fsevents_models import (
    FsEventFlag,
    FsEventNotification,
    FsEventSnapshotReport,
)


def print_fsevents_table(
    events: List[FsEventNotification],
    collection_method: str,
    total_events: int,
    created: int,
    modified: int,
    removed: int,
    renamed: int,
    monitored_paths: List[str],
    filter_label: str = "",
) -> None:
    """Print formatted terminal report and FSEvents notification table."""
    print("=" * 125)
    print(" SYSTEM MIND X — macOS FSEvents Filesystem Change Notification Telemetry")
    print("=" * 125)
    print(f"  Collection Method:    {collection_method}")
    print(f"  Total Events:         {total_events}")
    print(f"  Created Items:        {created}")
    print(f"  Modified Items:       {modified}")
    print(f"  Removed / Deleted:    {removed}")
    print(f"  Renamed / Moved:      {renamed}")
    print(f"  Monitored Roots:      {', '.join(monitored_paths[:3])}")
    print("  Privacy Invariant:    Excluded Personal Roots (Documents, Downloads, ~/.ssh, Keychains)")
    if filter_label:
        print(f"  [Active Filter]       {filter_label}")
    print("-" * 125)

    if events:
        print(f" {'ID':<6} {'LIFECYCLE':<14} {'TYPE':<10} {'PATH':<60} {'TIMESTAMP'}")
        print("-" * 125)
        for ev in events:
            # Determine primary lifecycle label
            if ev.is_created:
                action = "CREATED"
            elif ev.is_removed:
                action = "REMOVED"
            elif ev.is_renamed:
                action = "RENAMED"
            elif ev.is_modified:
                action = "MODIFIED"
            else:
                action = "METADATA"

            if ev.is_dir:
                item_type = "DIR"
            elif ev.is_symlink:
                item_type = "SYMLINK"
            elif ev.is_file:
                item_type = "FILE"
            else:
                item_type = "UNKNOWN"

            path_disp = (ev.path[:57] + "...") if len(ev.path) > 60 else ev.path
            ts_disp = ev.timestamp[:19]
            print(f" {ev.event_id:<6} {action:<14} {item_type:<10} {path_disp:<60} {ts_disp}")
        print("=" * 125)
    else:
        print("  No filesystem events matched the query or filter criteria.")
        print("=" * 125)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect macOS FSEvents filesystem change notifications read-only.",
    )
    parser.add_argument(
        "--paths",
        "-p",
        nargs="+",
        default=None,
        help="Monitored directory paths to inspect.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate Apple Silicon FSEvents change notifications via MockPlatformAdapter.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit full FSEvents report as structured JSON.",
    )
    parser.add_argument(
        "--filter",
        choices=["created", "modified", "removed", "renamed", "files", "dirs"],
        default=None,
        help="Filter displayed events by action or target type.",
    )

    args = parser.parse_args()

    detector = MacFsEventsDetector()
    report = detector.detect(monitored_paths=args.paths, mock=args.mock)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    events_to_display = report.events
    filter_label = ""
    if args.filter == "created":
        events_to_display = [e for e in report.events if e.is_created]
        filter_label = "Created Items"
    elif args.filter == "modified":
        events_to_display = [e for e in report.events if e.is_modified]
        filter_label = "Modified Items"
    elif args.filter == "removed":
        events_to_display = [e for e in report.events if e.is_removed]
        filter_label = "Removed Items"
    elif args.filter == "renamed":
        events_to_display = [e for e in report.events if e.is_renamed]
        filter_label = "Renamed Items"
    elif args.filter == "files":
        events_to_display = [e for e in report.events if e.is_file]
        filter_label = "Regular Files"
    elif args.filter == "dirs":
        events_to_display = [e for e in report.events if e.is_dir]
        filter_label = "Directories"

    print_fsevents_table(
        events=events_to_display,
        collection_method=report.collection_method,
        total_events=report.events_count,
        created=report.created_count,
        modified=report.modified_count,
        removed=report.removed_count,
        renamed=report.renamed_count,
        monitored_paths=report.monitored_paths,
        filter_label=filter_label,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
