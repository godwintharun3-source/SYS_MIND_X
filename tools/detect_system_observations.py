#!/usr/bin/env python3
"""CLI utility for auditing and interacting with timestamped system observation records."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.system_observations import SystemObservationsValidator
from system_mind.twin.identity import DeviceIdentifierManager, StableEntityIdGenerator
from system_mind.twin.observation_records import (
    ObservationRecordManager,
    SystemObservationRecord,
)
from system_mind.twin.temporal import ObservationType, ProvenanceStatus


def seed_sample_observations(manager: ObservationRecordManager, device_id: str) -> list[SystemObservationRecord]:
    """Populates an in-memory database with representative system observation records."""
    base_epoch = int(datetime.now(timezone.utc).timestamp() * 1000) - 10000

    host_urn = str(StableEntityIdGenerator.generate_host_urn(device_id))
    cpu_urn = str(StableEntityIdGenerator.generate_cpu_urn("arm64", "Apple M1", 8))
    proc_urn = str(StableEntityIdGenerator.generate_process_urn(device_id, 1, 1000, "/sbin/launchd"))
    app_urn = str(StableEntityIdGenerator.generate_app_urn("com.systemmind.desktop"))

    records: list[SystemObservationRecord] = [
        # 1. Host Hardware Observation (STATE_SNAPSHOT)
        ObservationRecordManager.create_record(
            device_id=device_id,
            entity_urn=host_urn,
            collector_id="macos_identity_sensor",
            observation_type=ObservationType.STATE_SNAPSHOT.value,
            payload={"model": "MacBookPro17,1", "arch": "arm64", "cores": 8, "ram_gb": 8},
            observed_at_epoch_ms=base_epoch,
            confidence_score=1.0,
            confidence_tier="KERNEL_AUTHORITATIVE",
            provenance_status=ProvenanceStatus.VERIFIED_KERNEL.value,
            sequence_number=1,
            metadata={"collector_latency_ms": 1.2},
        ),
        # 2. CPU Metric Snapshot
        ObservationRecordManager.create_record(
            device_id=device_id,
            entity_urn=cpu_urn,
            collector_id="macos_cpu_sensor",
            observation_type=ObservationType.STATE_SNAPSHOT.value,
            payload={"user_percent": 12.4, "sys_percent": 4.8, "idle_percent": 82.8},
            observed_at_epoch_ms=base_epoch + 1000,
            confidence_score=0.98,
            confidence_tier="KERNEL_AUTHORITATIVE",
            provenance_status=ProvenanceStatus.VERIFIED_KERNEL.value,
            sequence_number=1,
            metadata={"collector_latency_ms": 0.8},
        ),
        # 3. CPU Metric Delta
        ObservationRecordManager.create_record(
            device_id=device_id,
            entity_urn=cpu_urn,
            collector_id="macos_cpu_sensor",
            observation_type=ObservationType.ATTRIBUTE_DELTA.value,
            payload={"user_percent": 18.2, "idle_percent": 77.0},
            observed_at_epoch_ms=base_epoch + 2000,
            confidence_score=0.98,
            confidence_tier="KERNEL_AUTHORITATIVE",
            provenance_status=ProvenanceStatus.VERIFIED_KERNEL.value,
            sequence_number=2,
            metadata={"collector_latency_ms": 0.7},
        ),
        # 4. Process State Snapshot
        ObservationRecordManager.create_record(
            device_id=device_id,
            entity_urn=proc_urn,
            collector_id="macos_process_sensor",
            observation_type=ObservationType.STATE_SNAPSHOT.value,
            payload={"name": "launchd", "pid": 1, "status": "running", "rss_bytes": 14500000},
            observed_at_epoch_ms=base_epoch + 3000,
            confidence_score=0.92,
            confidence_tier="SUBSYSTEM_VERIFIED",
            provenance_status=ProvenanceStatus.VERIFIED_BROKER.value,
            sequence_number=1,
            metadata={"collector_latency_ms": 2.1},
        ),
        # 5. Process Lifecycle Event (ATTRIBUTE_DELTA)
        ObservationRecordManager.create_record(
            device_id=device_id,
            entity_urn=proc_urn,
            collector_id="macos_process_sensor",
            observation_type=ObservationType.ATTRIBUTE_DELTA.value,
            payload={"rss_bytes": 14900000, "threads": 4},
            observed_at_epoch_ms=base_epoch + 4000,
            confidence_score=0.92,
            confidence_tier="SUBSYSTEM_VERIFIED",
            provenance_status=ProvenanceStatus.VERIFIED_BROKER.value,
            sequence_number=2,
            metadata={"collector_latency_ms": 1.9},
        ),
        # 6. Application Security Attestation
        ObservationRecordManager.create_record(
            device_id=device_id,
            entity_urn=app_urn,
            collector_id="macos_signature_sensor",
            observation_type=ObservationType.SECURITY_ATTESTATION.value,
            payload={"bundle_id": "com.systemmind.desktop", "signed": True, "notarized": True},
            observed_at_epoch_ms=base_epoch + 5000,
            confidence_score=0.88,
            confidence_tier="SUBSYSTEM_VERIFIED",
            provenance_status=ProvenanceStatus.VERIFIED_BROKER.value,
            sequence_number=1,
            metadata={"collector_latency_ms": 3.4},
        ),
    ]

    for rec in records:
        manager.record_observation(rec)

    return records


def run_audit(json_output: bool) -> int:
    """Performs packaging and safety invariant audit for Day 069."""
    result = SystemObservationsValidator.audit()

    if json_output:
        payload = {
            "valid": result.valid,
            "issues": list(result.issues),
            "migration_present": result.migration_present,
            "models_present": result.models_present,
            "design_note_present": result.design_note_present,
            "tool_present": result.tool_present,
            "ast_safety_valid": result.ast_safety_valid,
            "charter_invariants_valid": result.charter_invariants_valid,
            "schema_constraints_valid": result.schema_constraints_valid,
            "reconstruction_valid": result.reconstruction_valid,
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.valid else 1

    print("=" * 78)
    print(" SYSTEM MIND X — Timestamped System Observation Records Packaging Audit")
    print("=" * 78)
    print(f"Overall Valid:              {'PASS' if result.valid else 'FAIL'}")
    print(f"Migration 0005:             {'PASS' if result.migration_present else 'FAIL'}")
    print(f"Persistence Models:         {'PASS' if result.models_present else 'FAIL'}")
    print(f"Design Documentation:       {'PASS' if result.design_note_present else 'FAIL'}")
    print(f"CLI Utility:                {'PASS' if result.tool_present else 'FAIL'}")
    print(f"AST Safety (SC-01):         {'PASS' if result.ast_safety_valid else 'FAIL'} (Zero shell=True, zero os.system)")
    print(f"Charter Invariant (SC-03):  {'PASS' if result.charter_invariants_valid else 'FAIL'} (scan_proves_safe = False)")
    print(f"Schema Constraints:         {'PASS' if result.schema_constraints_valid else 'FAIL'} (Confidence [0, 1], CHECK=0)")
    print(f"State Reconstruction:       {'PASS' if result.reconstruction_valid else 'FAIL'} (Point-in-time delta replay)")
    print("-" * 78)

    if result.issues:
        print("Audit Issues Found:")
        for issue in result.issues:
            print(f"  [!] {issue}")
        print("-" * 78)
        print("OVERALL VERDICT: FAILED")
        return 1

    print("OVERALL VERDICT: PASSED")
    return 0


def run_inspect(json_output: bool) -> int:
    """Migrates an in-memory database, seeds sample observation records, and prints summary."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    migrator.apply_all(conn=conn)

    device_id = DeviceIdentifierManager.resolve_device_id()
    manager = ObservationRecordManager(conn)
    records = seed_sample_observations(manager, device_id)

    total_records = manager.count_observations()
    all_observations = manager.query_observations(limit=100)

    # Historical state reconstruction demonstration
    cpu_urn = str(StableEntityIdGenerator.generate_cpu_urn("arm64", "Apple M1", 8))
    first_cpu_obs = manager.get_observations_for_entity(cpu_urn)[0]
    second_cpu_obs = manager.get_observations_for_entity(cpu_urn)[1]

    state_before_delta = manager.reconstruct_state_at(cpu_urn, first_cpu_obs.observed_at_epoch_ms)
    state_after_delta = manager.reconstruct_state_at(cpu_urn, second_cpu_obs.observed_at_epoch_ms)

    if json_output:
        payload = {
            "device_id": device_id,
            "total_records": total_records,
            "observations": [r.to_dict() for r in all_observations],
            "state_reconstruction": {
                "entity_urn": cpu_urn,
                "state_at_t1": state_before_delta,
                "state_at_t2": state_after_delta,
            },
        }
        print(json.dumps(payload, indent=2))
        conn.close()
        return 0

    print("=" * 78)
    print(" SYSTEM MIND X — Timestamped System Observation Records Summary")
    print("=" * 78)
    print(f"Database Target:            :memory:")
    print(f"Active Device ID:           {device_id}")
    print(f"Total Observations Stored:  {total_records}")
    print(f"Charter Invariant:          scan_proves_safe = False (Enforced)")
    print("-" * 78)
    print("Chronological Observations:")
    for r in all_observations:
        mock_tag = "[MOCK]" if r.is_mock else "[LIVE]"
        print(
            f"  {mock_tag:<6} [{r.confidence_tier:<20}] [conf={r.confidence_score:.2f}] "
            f"seq={r.sequence_number:<2} | {r.entity_urn}"
        )
        print(f"         type={r.observation_type} | collector={r.collector_id} | time={r.observed_at_iso}")
        print(f"         payload={json.dumps(r.payload)}")

    print("-" * 78)
    print("Point-in-Time State Reconstruction Query:")
    print(f"  Target Entity: {cpu_urn}")
    print(f"  Reconstructed State at T1 ({first_cpu_obs.observed_at_iso}):")
    print(f"    {json.dumps(state_before_delta)}")
    print(f"  Reconstructed State at T2 ({second_cpu_obs.observed_at_iso}, post-delta):")
    print(f"    {json.dumps(state_after_delta)}")
    print("=" * 78)

    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and audit SYSTEM MIND X timestamped system observation records."
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run packaging and safety invariant audit on observation persistence components.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in structured JSON format.",
    )
    args = parser.parse_args()

    if args.audit:
        return run_audit(args.json)
    return run_inspect(args.json)


if __name__ == "__main__":
    sys.exit(main())
