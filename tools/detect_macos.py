#!/usr/bin/env python3
"""SYSTEM MIND X — macOS Platform and Host Identity Detector CLI.

Collects and displays macOS product version, Darwin kernel release, Apple Silicon
architecture, Rosetta 2 translation state, and privacy-preserving host identity.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.platform.adapter import MockPlatformProfileFactory


def format_report_text(report_data: dict) -> str:
    """Format the telemetry report as human-readable text."""
    v = report_data["version_info"]
    a = report_data["architecture"]
    i = report_data["identity"]

    lines = [
        "================================================================================",
        " SYSTEM MIND X — macOS Companion Agent Platform & Identity Detection",
        "================================================================================",
        f"  Collection Method:     {report_data['collection_method']}",
        "--------------------------------------------------------------------------------",
        " Operating System & Darwin Kernel:",
        f"  Product Name:          {v['product_name']}",
        f"  Product Version:       {v['product_version']} (Major: {v['major_version']}, Minor: {v['minor_version']}, Patch: {v['patch_version']})",
        f"  Build Version:         {v['build_version']}",
        f"  Darwin Kernel Release: {v['darwin_kernel_release']}",
        f"  Marketing Name:        {v['marketing_name']}",
        "--------------------------------------------------------------------------------",
        " Processor & Architecture:",
        f"  Machine Architecture:  {a['machine']} ({a['pointer_size_bits']}-bit, {a['byte_order']}-endian)",
        f"  Apple Silicon Silicon: {a['is_apple_silicon']}",
        f"  Rosetta 2 Translated:  {a['is_rosetta_translated']}",
        "--------------------------------------------------------------------------------",
        " Host Identity & Privacy Metadata:",
        f"  Hostname:              {i['hostname']}",
        f"  Computer Name:         {i['computer_name']}",
        f"  Local Hostname:        {i['local_host_name']}",
        f"  Platform UUID:         {i['platform_uuid'] or 'N/A'}",
        f"  Anonymized Serial:     {i['anonymized_serial_hash'] or 'N/A'}",
        f"  Virtual Machine:       {i['is_virtual_machine']}",
        "================================================================================",
    ]

    if report_data["unavailable_telemetry"]:
        lines.append(f"  Unavailable: {', '.join(report_data['unavailable_telemetry'])}")
    if report_data["warnings"]:
        lines.append(f"  Warnings:    {', '.join(report_data['warnings'])}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — macOS Platform and Host Identity Detector CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in structured JSON format",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Simulate Apple Silicon macOS detection using MockPlatformAdapter",
    )
    parser.add_argument(
        "--strict-apple-silicon",
        action="store_true",
        help="Exit with non-zero status if target is not verified Apple Silicon",
    )

    args = parser.parse_args()

    mock_adapter = None
    if args.mock:
        mock_adapter = MockPlatformProfileFactory.create_macos_apple_silicon_mock()

    report = MacOSIdentityDetector.detect(mock_adapter=mock_adapter)
    report_dict = asdict(report)

    if args.json:
        print(json.dumps(report_dict, indent=2))
    else:
        print(format_report_text(report_dict))

    if args.strict_apple_silicon and not report.architecture.is_apple_silicon:
        sys.stderr.write("[!] Error: Host is not verified Apple Silicon architecture.\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
