#!/usr/bin/env python3
"""Run non-destructive host inspection for SYSTEM MIND X and display the report."""

import json
import sys
from pathlib import Path

# Add src to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from system_mind.host.inspector import HostEnvironmentInspector


def main() -> None:
    inspector = HostEnvironmentInspector()
    report = inspector.inspect()

    print("=" * 70)
    print(" SYSTEM MIND X - HOST ENVIRONMENT INSPECTION REPORT (READ-ONLY)")
    print("=" * 70)
    print(f"OS:                  {report.os_name} {report.os_version}")
    print(f"Kernel:              {report.kernel_version}")
    print(f"Architecture:        {report.architecture}")
    print(f"CPU Brand:           {report.cpu_brand}")
    print(f"CPU Cores:           {report.cpu_cores}")
    print(f"Memory (RAM):        {report.memory_bytes / (1024**3):.2f} GB")
    print(f"Platform Tier:       {report.platform_tier.value}")
    print(f"Is Supported Host:   {report.is_supported_host}")
    print(f"SIP Enabled:         {report.sip_enabled}")
    print(f"Gatekeeper Active:   {report.gatekeeper_enabled}")
    print("-" * 70)
    print("Detected Development Tools:")
    for tool, path in sorted(report.installed_tools.items()):
        status = path if path else "NOT FOUND"
        print(f"  - {tool:<20}: {status}")
    print("-" * 70)
    if report.notes:
        print("Inspection Notes:")
        for note in report.notes:
            print(f"  * {note}")
    print("=" * 70)


if __name__ == "__main__":
    main()
