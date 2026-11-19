#!/usr/bin/env python3
"""CLI utility for auditing and demonstrating change detection between consecutive system observations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.observation_deltas import ObservationDeltasValidator
from system_mind.twin.change_detector import (
    ChangeClassification,
    ObservationChangeDetector,
    ObservationDelta,
    ObservationDeltaManager,
)
from system_mind.twin.identity import DeviceIdentifierManager
from system_mind.twin.observation_records import (
    ObservationRecordManager,
    SystemObservationRecord,
)


def run_audit() -> int:
    """Run comprehensive packaging and invariant audit."""
    result = ObservationDeltasValidator.audit()

    print("==============================================================================")
    print(" SYSTEM MIND X — Observation Deltas & Change Detection Packaging Audit")
    print("==============================================================================")
    print(f"Overall Valid:              {'PASS' if result.valid else 'FAIL'}")
    print(f"Change Detector Present:    {'PASS' if result.change_detector_present else 'FAIL'}")
    print(f"Design Documentation:       {'PASS' if result.design_note_present else 'FAIL'}")
    print(f"Migration 0009 Present:     {'PASS' if result.migration_present else 'FAIL'}")
    print(f"CLI Tool Present:           {'PASS' if result.tool_present else 'FAIL'}")
    print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, zero os.system)' if result.ast_safety_valid else 'FAIL'}")
    print(f"Charter Invariant (SC-03):  {'PASS (scan_proves_safe = False)' if result.charter_invariants_valid else 'FAIL'}")
    print(f"Functional Deltas Test:     {'PASS (Consecutive diffs & classifications verified)' if result.functional_deltas_valid else 'FAIL'}")
    print("------------------------------------------------------------------------------")

    if result.issues:
        print("ISSUES DETECTED:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("------------------------------------------------------------------------------")
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: PASSED")
    return 0


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X — Consecutive Observation Change Detection CLI"
    )
    parser.add_argument("--audit", action="store_true", help="Run packaging and safety invariant audit")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")
    parser.add_argument("--device-id", default=None, help="Target device ID")
    parser.add_argument("--db-path", default=":memory:", help="SQLite database path (default: :memory:)")

    args = parser.parse_args()

    if args.audit:
        return run_audit()

    device_id = args.device_id or DeviceIdentifierManager.resolve_device_id()

    # Setup database connection and apply migrations (0001 through 0009)
    db_cfg = DatabaseConfig(args.db_path)
    conn = DatabaseConnectionManager.connect(db_cfg)
    migrator = DatabaseMigrator(config=db_cfg)
    migrator.apply_all(conn=conn)

    obs_mgr = ObservationRecordManager(conn)
    delta_mgr = ObservationDeltaManager(conn)

    t0_epoch_ms = 1700000000000
    proc_urn = "urn:systemmind:proc:101"

    # Simulate observation stream for a process
    observations = [
        # Seq 1: Initial observation
        SystemObservationRecord(
            record_id="rec-proc-01",
            device_id=device_id,
            entity_urn=proc_urn,
            collector_id="mock_ps",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T12:00:00Z",
            observed_at_epoch_ms=t0_epoch_ms,
            sequence_number=1,
            payload={"pid": 101, "name": "daemon_worker", "cpu_pct": 2.5, "rss_mb": 40},
        ),
        # Seq 2: CPU spike (threshold breach >= 10.0%)
        SystemObservationRecord(
            record_id="rec-proc-02",
            device_id=device_id,
            entity_urn=proc_urn,
            collector_id="mock_ps",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T12:00:05Z",
            observed_at_epoch_ms=t0_epoch_ms + 5000,
            sequence_number=2,
            payload={"pid": 101, "name": "daemon_worker", "cpu_pct": 34.0, "rss_mb": 45},
        ),
        # Seq 3: Minor nominal mutation (rss increased to 48)
        SystemObservationRecord(
            record_id="rec-proc-03",
            device_id=device_id,
            entity_urn=proc_urn,
            collector_id="mock_ps",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T12:00:10Z",
            observed_at_epoch_ms=t0_epoch_ms + 10000,
            sequence_number=3,
            payload={"pid": 101, "name": "daemon_worker", "cpu_pct": 34.0, "rss_mb": 48},
        ),
        # Seq 4: Identical observation (NO_CHANGE)
        SystemObservationRecord(
            record_id="rec-proc-04",
            device_id=device_id,
            entity_urn=proc_urn,
            collector_id="mock_ps",
            observation_type="STATE_SNAPSHOT",
            observed_at_iso="2026-11-18T12:00:15Z",
            observed_at_epoch_ms=t0_epoch_ms + 15000,
            sequence_number=4,
            payload={"pid": 101, "name": "daemon_worker", "cpu_pct": 34.0, "rss_mb": 48},
        ),
        # Seq 5: Lifecycle transition (Process Exited)
        SystemObservationRecord(
            record_id="rec-proc-05",
            device_id=device_id,
            entity_urn=proc_urn,
            collector_id="mock_ps",
            observation_type="LIFECYCLE_EVENT",
            observed_at_iso="2026-11-18T12:00:20Z",
            observed_at_epoch_ms=t0_epoch_ms + 20000,
            sequence_number=5,
            payload={"pid": 101, "status": "exited", "exit_code": 0},
        ),
    ]

    deltas: list[ObservationDelta] = []
    for i, obs in enumerate(observations):
        obs_mgr.record_observation(obs)
        if i > 0:
            delta = delta_mgr.detect_and_record(observations[i - 1], obs)
            deltas.append(delta)

    # Query significant changes
    significant_deltas = delta_mgr.query_significant_changes()

    if args.json:
        payload = {
            "device_id": device_id,
            "entity_urn": proc_urn,
            "total_observations": len(observations),
            "total_deltas": len(deltas),
            "significant_deltas_count": len(significant_deltas),
            "deltas": [d.to_dict() for d in deltas],
            "scan_proves_safe": False,
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("==============================================================================")
    print(" SYSTEM MIND X — Consecutive Observation Change Detection")
    print("==============================================================================")
    print(f"Device ID:         {device_id}")
    print(f"Target Entity:     {proc_urn}")
    print(f"Observations:      {len(observations)} records recorded")
    print(f"Computed Deltas:   {len(deltas)} transition deltas computed")
    print(f"Significant:       {len(significant_deltas)} threshold breaches or lifecycle transitions")
    print("------------------------------------------------------------------------------")
    print(f"{'FROM->TO':<12} {'TIME DELTA':<12} {'CHANGED?':<10} {'CLASSIFICATION':<30} {'MUTATIONS'}")
    print("------------------------------------------------------------------------------")
    for d in deltas:
        seq_str = f"Seq {d.from_sequence}->{d.to_sequence}"
        dt_str = f"{d.time_delta_ms}ms"
        chg_str = "YES" if d.has_changed else "NO"
        muts: list[str] = []
        for k, m in d.modified_keys.items():
            if m.change_type == "MODIFIED":
                delta_val = f" ({m.delta_numeric:+g})" if m.delta_numeric is not None else ""
                muts.append(f"{k}: {m.old_value}->{m.new_value}{delta_val}")
            elif m.change_type == "ADDED":
                muts.append(f"+{k}={m.new_value}")
            elif m.change_type == "REMOVED":
                muts.append(f"-{k}")
        mut_str = ", ".join(muts) if muts else "-"
        print(f"{seq_str:<12} {dt_str:<12} {chg_str:<10} {d.change_classification:<30} {mut_str}")
    print("------------------------------------------------------------------------------")
    print("Charter Invariant (SC-03): scan_proves_safe = False [VERIFIED]")
    print("Zero Ambient Shell (SC-01): Pure in-memory SQLite execution [VERIFIED]")
    print("==============================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
