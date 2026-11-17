#!/usr/bin/env python3
"""SYSTEM MIND X — macOS telemetry observation source timestamp and confidence scoring CLI tool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from system_mind.macos.collector_health_manager import CORE_COLLECTORS
from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.macos.observation_models import (
    CompanionObservationBatch,
    ObservedTelemetryEnvelope,
)


def print_observation_batch_table(batch: CompanionObservationBatch) -> None:
    """Print formatted terminal report and observation batch confidence table."""
    print("=" * 130)
    print(" SYSTEM MIND X — macOS Telemetry Observation Provenance & Confidence Report")
    print("=" * 130)
    print(f"  Batch Identifier:      {batch.batch_id}")
    print(f"  Timestamp (UTC):       {batch.timestamp_utc}")
    print(f"  Execution Mode:        {'MOCK FIXTURE' if batch.is_mock else 'LIVE ENRICHED TELEMETRY'}")
    print(f"  Total Observations:    {batch.total_observations}")
    print(f"  Mean Confidence:       {batch.mean_confidence:.3f} / 1.000")
    print(f"  Lowest Confidence:     {batch.lowest_confidence_collector} "
          f"({batch.observations[batch.lowest_confidence_collector].confidence.score:.3f} "
          f"[{batch.observations[batch.lowest_confidence_collector].confidence.tier.value}])" if batch.lowest_confidence_collector in batch.observations else "N/A")
    print("  Charter Invariant:     Scan != Safe (Observation confidence reflects source fidelity, not application safety)")
    print("-" * 130)
    print(f"  {'Collector ID':<18} | {'Clock Source':<22} | {'Latency':<8} | {'Score':<6} | {'Confidence Tier':<22} | {'SHA-256':<16} | {'Notes / Penalties':<24}")
    print("-" * 130)

    for cid in sorted(batch.observations.keys()):
        env = batch.observations[cid]
        clock_str = env.source_timestamp.clock_source
        latency_str = f"{env.latency_ms:.1f}ms"
        score_str = f"{env.confidence.score:.3f}"
        tier_str = env.confidence.tier.value
        hash_str = env.payload_sha256[:16]

        notes_parts: list[str] = []
        if env.confidence.penalty_factors:
            notes_parts.append(f"Penalties: {', '.join(env.confidence.penalty_factors)}")
        elif env.unavailable_telemetry:
            notes_parts.append(f"Missing: {', '.join(env.unavailable_telemetry[:2])}")
        else:
            notes_parts.append("Authoritative")

        notes_str = "; ".join(notes_parts)
        if len(notes_str) > 24:
            notes_str = notes_str[:21] + "..."

        print(f"  {cid:<18} | {clock_str:<22} | {latency_str:<8} | {score_str:<6} | {tier_str:<22} | {hash_str:<16} | {notes_str:<24}")

    print("=" * 130)


def main() -> int:
    """CLI entrypoint for observation source timestamp and confidence inspection."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Read-only macOS telemetry observation source timestamp & confidence inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock observation profile instead of running live collectors",
    )
    parser.add_argument(
        "--profile",
        choices=["high_fidelity", "degraded", "mock_simulation", "unsupported"],
        default="high_fidelity",
        help="Mock profile to simulate (default: high_fidelity)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON data instead of tabular terminal output",
    )
    parser.add_argument(
        "--collector",
        type=str,
        default=None,
        help=f"Inspect a specific collector envelope only: {', '.join(CORE_COLLECTORS)}",
    )

    args = parser.parse_args()

    engine = MacOsObservationEngine()

    batch = engine.collect_batch(use_mock=args.mock, profile=args.profile)

    if args.collector:
        if args.collector not in batch.observations:
            print(f"[!] Unknown collector '{args.collector}'. Available: {', '.join(CORE_COLLECTORS)}", file=sys.stderr)
            return 1
        single_env = batch.observations[args.collector]
        if args.json:
            print(json.dumps(single_env.to_dict(), indent=2))
        else:
            print(f"Observation ID:        {single_env.observation_id}")
            print(f"Collector ID:          {single_env.collector_id}")
            print(f"Source Timestamp UTC:  {single_env.source_timestamp.utc_iso}")
            print(f"Source Epoch (ms):     {single_env.source_timestamp.epoch_ms}")
            print(f"Clock Source:          {single_env.source_timestamp.clock_source}")
            print(f"Latency:               {single_env.latency_ms:.1f}ms")
            print(f"Confidence Score:      {single_env.confidence.score:.3f}")
            print(f"Confidence Tier:       {single_env.confidence.tier.value}")
            print(f"Confidence Rationale:  {single_env.confidence.rationale}")
            print(f"Penalty Factors:       {', '.join(single_env.confidence.penalty_factors) if single_env.confidence.penalty_factors else 'None'}")
            print(f"Payload SHA-256:       {single_env.payload_sha256}")
            print(f"Scan Proves Safe:      {single_env.scan_proves_safe}")
        return 0

    if args.json:
        print(json.dumps(batch.to_dict(), indent=2))
    else:
        print_observation_batch_table(batch)

    return 0


if __name__ == "__main__":
    sys.exit(main())
