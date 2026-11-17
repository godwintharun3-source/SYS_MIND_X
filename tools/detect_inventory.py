#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS inventory inspection and telemetry aggregator CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import (
    InventorySection,
    MacOsInventoryRequest,
    MacOsInventoryResponse,
    MacOsInventorySummary,
)
from system_mind.macos.privacy_models import PrivacyScrubbingLevel


def _format_bytes(num_bytes: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def print_inventory_summary_table(summary: MacOsInventorySummary) -> None:
    """Print formatted terminal overview for inventory summary."""
    print("=" * 100)
    print(" SYSTEM MIND X — macOS Inventory Executive Summary")
    print("=" * 100)
    print(f"  Operating System:    macOS {summary.os_version} (Build {summary.os_build})")
    print(f"  Host / Architecture: {summary.host_name} [{summary.architecture}]")
    print(f"  Processor:           {summary.cpu_model} ({summary.physical_cores} P-cores / {summary.logical_cores} Threads)")
    print(f"  Memory Capacity:     {_format_bytes(summary.total_memory_bytes)} (Pressure: {summary.memory_pressure_pct:.1f}%)")
    print(f"  Storage Capacity:    {_format_bytes(summary.total_storage_bytes)} (Free: {_format_bytes(summary.free_storage_bytes)})")
    print(f"  Runtime Processes:   {summary.running_process_count} active PIDs")
    print(f"  Installed Apps:      {summary.installed_app_count} application bundles")
    print(f"  Mean Confidence:     {summary.mean_confidence:.3f} / 1.000")
    print(f"  Overall Health:      {summary.overall_health}")
    print("  Charter Invariant:   Scan != Safe (Inventory completeness != application safety)")
    print("=" * 100)


def print_full_inventory_table(response: MacOsInventoryResponse) -> None:
    """Print formatted terminal report covering the entire inventory envelope."""
    print_inventory_summary_table(response.summary)
    print(f"  Inventory ID:        {response.inventory_id}")
    print(f"  Timestamp (UTC):     {response.timestamp_utc}")
    print(f"  Execution Mode:      {'MOCK SIMULATION' if response.is_mock else 'LIVE DARWIN TELEMETRY'}")
    print(f"  Partial Data:        {response.partial_data}")
    print(f"  Charter Invariant:   scan_proves_safe={response.scan_proves_safe}")

    if response.privacy_audit:
        print("-" * 100)
        print("  Privacy Redaction Metrics:")
        audit = response.privacy_audit
        print(f"    Scrubbing Level:   {audit.get('level', 'N/A')}")
        print(f"    Total Redactions:  {audit.get('total_redactions', 0)}")
        print(f"    Masked Usernames:  {audit.get('sanitized_usernames_count', 0)}")
        print(f"    Masked Paths:      {audit.get('sanitized_paths_count', 0)}")
        print(f"    Scrubbed Metadata: {audit.get('sanitized_metadata_count', 0)}")
        print(f"    Redacted Secrets:  {audit.get('redacted_secrets_count', 0)}")
        print(f"    Rules Applied:     {', '.join(audit.get('rules_applied', []))}")

    print("-" * 100)
    print("  Aggregated Inventory Sections:")
    for section_name in sorted(response.sections.keys()):
        sec_data = response.sections[section_name]
        items_count = len(sec_data) if isinstance(sec_data, (dict, list)) else "Available"
        print(f"    [{section_name.upper():<14}] -> {items_count} attributes/entries")

    print("=" * 100)


def main() -> int:
    """CLI entrypoint for macOS inventory inspection."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Read-only macOS inventory inspection & aggregation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--section",
        choices=["all", "identity", "hardware", "storage", "network", "applications", "security", "processes", "services"],
        default="all",
        help="Subsystem section to query (default: all)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Output high-level system summary only",
    )
    parser.add_argument(
        "--level",
        choices=["strict", "balanced", "minimal"],
        default="balanced",
        help="Privacy scrubbing granularity level (default: balanced)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock platform adapters and simulation profiles",
    )
    parser.add_argument(
        "--profile",
        choices=["high_fidelity", "degraded", "mock_simulation", "unsupported"],
        default="high_fidelity",
        help="Mock profile for observation confidence simulation (default: high_fidelity)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON data instead of tabular terminal output",
    )

    args = parser.parse_args()

    api = MacOsInventoryApi()

    if args.summary:
        summary = api.get_summary(use_mock=args.mock, profile=args.profile)
        if args.json:
            print(json.dumps(summary.to_dict(), indent=2))
        else:
            print_inventory_summary_table(summary)
        return 0

    level_map = {
        "strict": PrivacyScrubbingLevel.STRICT,
        "balanced": PrivacyScrubbingLevel.BALANCED,
        "minimal": PrivacyScrubbingLevel.MINIMAL,
    }
    privacy_level = level_map[args.level]

    section_map = {
        "all": InventorySection.ALL,
        "identity": InventorySection.IDENTITY,
        "hardware": InventorySection.HARDWARE,
        "storage": InventorySection.STORAGE,
        "network": InventorySection.NETWORK,
        "applications": InventorySection.APPLICATIONS,
        "security": InventorySection.SECURITY,
        "processes": InventorySection.PROCESSES,
        "services": InventorySection.SERVICES,
    }
    chosen_section = section_map[args.section]

    req = MacOsInventoryRequest(
        sections=[chosen_section],
        privacy_level=privacy_level,
        use_mock=args.mock,
        mock_profile=args.profile,
    )

    response = api.get_inventory(req)

    if args.json:
        print(response.to_json())
    else:
        print_full_inventory_table(response)

    return 0


if __name__ == "__main__":
    sys.exit(main())
