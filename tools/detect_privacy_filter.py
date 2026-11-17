#!/usr/bin/env python3
"""SYSTEM MIND X — macOS telemetry privacy filter, path masking, and metadata sanitization CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.macos.privacy_filter import MacPrivacyFilter
from system_mind.macos.privacy_models import (
    PrivacyFilterAuditRecord,
    PrivacyScrubbingLevel,
    SanitizedTelemetryEnvelope,
)


def print_privacy_audit_table(
    audit: PrivacyFilterAuditRecord,
    envelope: Optional[SanitizedTelemetryEnvelope[Any]] = None,
    original_text: Optional[str] = None,
    sanitized_text: Optional[str] = None,
) -> None:
    """Print formatted terminal report and privacy filter audit details."""
    print("=" * 110)
    print(" SYSTEM MIND X — macOS Telemetry Privacy Filter & Sanitization Report")
    print("=" * 110)
    print(f"  Scrubbing Level:        {audit.level.value}")
    print(f"  Total Redactions:       {audit.total_redactions}")
    print(f"  Sanitized Usernames:    {audit.sanitized_usernames_count}")
    print(f"  Masked File Paths:      {audit.sanitized_paths_count}")
    print(f"  Scrubbed Metadata:      {audit.sanitized_metadata_count}")
    print(f"  Redacted Secrets/Keys:  {audit.redacted_secrets_count}")
    print(f"  Rules Applied:          {', '.join(audit.rules_applied) if audit.rules_applied else 'None'}")
    print(f"  Charter Invariant:      Scan != Safe (Sanitization ensures privacy, not application safety; scan_proves_safe={audit.scan_proves_safe})")
    print("-" * 110)

    if envelope:
        print(f"  Envelope ID:            {envelope.envelope_id}")
        print(f"  Collector ID:           {envelope.collector_id}")
        print(f"  Is Mock Fixture:        {envelope.is_mock}")
        print("-" * 110)
        print("  Sanitized Payload Preview:")
        preview = json.dumps(envelope.payload if isinstance(envelope.payload, (dict, list)) else str(envelope.payload), indent=2)
        lines = preview.splitlines()
        for line in lines[:30]:
            print(f"    {line}")
        if len(lines) > 30:
            print(f"    ... ({len(lines) - 30} lines truncated) ...")

    elif original_text and sanitized_text is not None:
        print("  Input Sanitization Comparison:")
        print(f"  Original:  {original_text[:120]}{'...' if len(original_text) > 120 else ''}")
        print(f"  Sanitized: {sanitized_text[:120]}{'...' if len(sanitized_text) > 120 else ''}")

    print("=" * 110)


def main() -> int:
    """CLI entrypoint for privacy filter inspection and testing."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Read-only macOS telemetry privacy filter & metadata sanitization tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--level",
        choices=["strict", "balanced", "minimal"],
        default="balanced",
        help="Privacy scrubbing granularity level (default: balanced)",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Input string or path to sanitize",
    )
    parser.add_argument(
        "--username",
        action="append",
        dest="extra_usernames",
        help="Extra username(s) to register for pseudonymization",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Demonstrate privacy filtering on simulated mock telemetry containing sensitive items",
    )
    parser.add_argument(
        "--live-collector",
        type=str,
        default=None,
        help="Collect live telemetry from a specific collector and sanitize the resulting envelope",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON data instead of tabular terminal output",
    )

    args = parser.parse_args()

    level_map = {
        "strict": PrivacyScrubbingLevel.STRICT,
        "balanced": PrivacyScrubbingLevel.BALANCED,
        "minimal": PrivacyScrubbingLevel.MINIMAL,
    }
    scrubbing_level = level_map[args.level]

    extra_users = set(args.extra_usernames) if args.extra_usernames else set()
    filter_engine = MacPrivacyFilter(
        level=scrubbing_level,
        extra_usernames=extra_users,
    )

    if args.input:
        # Check if input is a readable file
        input_text = args.input
        p = Path(input_text)
        if p.exists() and p.is_file():
            try:
                input_text = p.read_text(encoding="utf-8")
            except Exception:
                pass

        sanitized, audit = filter_engine.sanitize_payload(input_text)
        if args.json:
            out = {
                "original": input_text,
                "sanitized": sanitized,
                "audit": audit.to_dict(),
            }
            print(json.dumps(out, indent=2))
        else:
            print_privacy_audit_table(
                audit,
                original_text=input_text,
                sanitized_text=str(sanitized),
            )
        return 0

    if args.live_collector:
        obs_engine = MacOsObservationEngine()
        batch = obs_engine.collect_batch(use_mock=False)
        if args.live_collector not in batch.observations:
            print(f"[!] Collector '{args.live_collector}' not found in observation batch.", file=sys.stderr)
            return 1
        raw_envelope = batch.observations[args.live_collector]
        sanitized_env = filter_engine.sanitize_envelope(raw_envelope)
        if args.json:
            print(sanitized_env.to_json())
        else:
            print_privacy_audit_table(sanitized_env.audit, envelope=sanitized_env)
        return 0

    # Default / --mock mode: Demonstrate filter on realistic sensitive telemetry sample
    mock_payload = {
        "user_identity": {
            "console_user": "tharungodwin",
            "home_directory": "/Users/tharungodwin",
            "uid": 501,
        },
        "recent_fsevents": [
            "/Users/tharungodwin/Documents/Quarterly_Financial_Report_2026.docx",
            "/Users/tharungodwin/.ssh/id_ed25519",
            "/Users/tharungodwin/Library/Keychains/login.keychain-db",
            "/Users/tharungodwin/Downloads/NDA_Vendor_Agreement.pdf",
            "/System/Library/CoreServices/SystemVersion.plist",
        ],
        "active_window": {
            "app": "Google Chrome",
            "title": "Confidential Strategy 2026.pptx - Google Drive",
            "url": "https://company.internal/dashboard?session_token=ghp_ABC1234567890abcdef1234567890abcdef",
        },
        "environment": {
            "API_KEY": "AKIAIOSFODNN7EXAMPLE",
            "AUTH_HEADER": "Bearer secret_access_token_super_secret_999",
        },
    }

    sanitized_payload, audit = filter_engine.sanitize_payload(mock_payload)
    envelope = SanitizedTelemetryEnvelope(
        envelope_id="sanitized-mock-sample-059",
        collector_id="mock_aggregate",
        payload=sanitized_payload,
        audit=audit,
        scan_proves_safe=False,
        is_mock=True,
    )

    if args.json:
        print(envelope.to_json())
    else:
        print_privacy_audit_table(audit, envelope=envelope)

    return 0


if __name__ == "__main__":
    sys.exit(main())
