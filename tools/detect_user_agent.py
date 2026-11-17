#!/usr/bin/env python3
"""SYSTEM MIND X — Read-only macOS least-privilege user agent service CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.agent_service_detector import MacUserAgentServiceManager
from system_mind.macos.agent_service_models import (
    AgentServiceState,
    AgentServiceStatusReport,
    LaunchAgentConfig,
)


def print_user_agent_table(report: AgentServiceStatusReport) -> None:
    """Print formatted terminal report and user agent status table."""
    domain_str = report.domain.value if hasattr(report.domain, "value") else str(report.domain)
    status_str = report.status.value if hasattr(report.status, "value") else str(report.status)
    state_str = report.state.value if hasattr(report.state, "value") else str(report.state)

    print("=" * 115)
    print(" SYSTEM MIND X — macOS Least-Privilege User Agent Service Status")
    print("=" * 115)
    print(f"  Host Platform:         {report.host_platform}")
    print(f"  Execution Domain:      {domain_str} (User Graphical Login Session)")
    print(f"  Execution Mode:        {'MOCK FIXTURE' if report.is_mock else 'LIVE LAUNCHD QUERY'}")
    print(f"  Service Label:         {report.label}")
    print(f"  Service State:         {state_str} ({status_str})")
    print(f"  Process ID (PID):      {report.pid if report.pid is not None else 'None (Inactive)'}")
    print(f"  Last Exit Code:        {report.last_exit_code if report.last_exit_code is not None else 'N/A'}")
    print(f"  Plist Path:            {report.plist_path}")
    print("-" * 115)
    print("  SECURITY & LEAST-PRIVILEGE AUDIT:")
    print(f"    • Least-Privilege:            {'COMPLIANT (Non-Root User Agent)' if report.is_least_privilege else 'VIOLATION / ELEVATED'}")
    print(f"    • Root Process:               {'YES (VIOLATION)' if report.is_root else 'No (UID != 0)'}")
    print(f"    • User ID (UID):              {report.uid}")
    print(f"    • Console User:               {report.console_user}")
    print("    • Mutation Authority:         READ-ONLY (Host launchctl mutating commands disabled)")
    print("    • Charter Invariant:          Scan != Safe (Agent telemetry does not prove application safety)")
    print("-" * 115)
    print("  LAUNCHAGENT CONFIGURATION DECLARATION:")
    cfg = report.config
    print(f"    • Program Arguments:          {' '.join(cfg.program_arguments)}")
    print(f"    • Session Types:              {', '.join(cfg.limit_load_to_session_type)}")
    print(f"    • Run At Load:                {cfg.run_at_load}")
    print(f"    • Keep Alive:                 {cfg.keep_alive}")
    print(f"    • Scheduling Priority (Nice): {cfg.nice} (Low priority background)")
    print(f"    • Process Type:               {cfg.process_type}")
    print(f"    • Stdout Log Path:            {cfg.standard_out_path}")
    print(f"    • Stderr Log Path:            {cfg.standard_error_path}")
    print("-" * 115)

    if report.unavailable_telemetry:
        print("  UNAVAILABLE TELEMETRY / AUDIT WARNINGS:")
        for item in report.unavailable_telemetry:
            print(f"    [!] {item}")
        print("-" * 115)


def main() -> int:
    """CLI entrypoint for macOS user agent service status inspection."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Read-only macOS least-privilege user agent service status inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock report profile instead of querying live launchctl",
    )
    parser.add_argument(
        "--profile",
        choices=["running", "stopped", "uninstalled", "unsupported"],
        default="running",
        help="Mock profile to simulate (default: running)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON data instead of tabular terminal output",
    )
    parser.add_argument(
        "--generate-plist",
        action="store_true",
        help="Generate and print Apple-compliant launchd XML Property List content to stdout",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="com.systemmind.useragent",
        help="LaunchAgent service label (default: com.systemmind.useragent)",
    )

    args = parser.parse_args()

    manager = MacUserAgentServiceManager(label=args.label)

    if args.generate_plist:
        config = LaunchAgentConfig(label=args.label)
        print(config.to_plist_xml())
        return 0

    if args.mock:
        report = manager.get_mock_status(profile=args.profile)
    else:
        report = manager.get_status()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_user_agent_table(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
