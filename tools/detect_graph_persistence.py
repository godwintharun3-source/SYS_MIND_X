#!/usr/bin/env python3
"""CLI utility for auditing and interacting with digital twin graph node and edge persistence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from system_mind.core.types import ComponentOwnership
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.graph_persistence import GraphPersistenceValidator
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import DeviceIdentifierManager, StableEntityIdGenerator
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinRelationship,
    TwinRelationType,
)
from system_mind.twin.persistence import GraphPersistenceManager


def build_sample_graph(device_id: str) -> DigitalTwinGraph:
    """Construct an in-memory sample DigitalTwinGraph with realistic node and edge hierarchy."""
    g = DigitalTwinGraph()

    host_urn = str(StableEntityIdGenerator.generate_host_urn(device_id))
    kernel_urn = str(StableEntityIdGenerator.generate_kernel_urn("Darwin", "24.0.0", "arm64"))
    proc1_urn = str(StableEntityIdGenerator.generate_process_urn(device_id, 1, 1000, "/sbin/launchd"))
    proc2_urn = str(
        StableEntityIdGenerator.generate_process_urn(
            device_id, 501, 2000, "/usr/local/bin/system-mind-agent"
        )
    )
    app_urn = str(StableEntityIdGenerator.generate_app_urn("com.systemmind.desktop"))

    # Nodes
    g.add_entity(
        TwinEntity(
            entity_id=host_urn,
            entity_type=TwinEntityType.HOST,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            attributes={"model": "Apple Silicon Host", "arch": "arm64"},
            provenance_source="native_ioreg",
        )
    )
    g.add_entity(
        TwinEntity(
            entity_id=kernel_urn,
            entity_type=TwinEntityType.OS_KERNEL,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            attributes={"os_family": "Darwin", "version": "15.0"},
            provenance_source="native_sysctl",
        )
    )
    g.add_entity(
        TwinEntity(
            entity_id=proc1_urn,
            entity_type=TwinEntityType.PROCESS,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            attributes={"name": "launchd", "pid": 1},
            provenance_source="native_proc",
        )
    )
    g.add_entity(
        TwinEntity(
            entity_id=proc2_urn,
            entity_type=TwinEntityType.PROCESS,
            ownership=ComponentOwnership.USER_MANAGED,
            attributes={"name": "system-mind-agent", "pid": 501},
            provenance_source="native_proc",
        )
    )
    g.add_entity(
        TwinEntity(
            entity_id=app_urn,
            entity_type=TwinEntityType.APPLICATION,
            ownership=ComponentOwnership.USER_MANAGED,
            attributes={"bundle_id": "com.systemmind.desktop", "version": "1.0.0"},
            provenance_source="app_detector",
        )
    )

    # Edges
    g.add_relationship(
        TwinRelationship(
            relation_id=f"rel-host-kernel-{device_id[:6]}",
            source_id=host_urn,
            target_id=kernel_urn,
            relation_type=TwinRelationType.CONTAINS,
            confidence=1.0,
        )
    )
    g.add_relationship(
        TwinRelationship(
            relation_id=f"rel-kernel-proc1-{device_id[:6]}",
            source_id=kernel_urn,
            target_id=proc1_urn,
            relation_type=TwinRelationType.ENFORCES_POLICY,
            confidence=0.95,
        )
    )
    g.add_relationship(
        TwinRelationship(
            relation_id=f"rel-proc2-proc1-{device_id[:6]}",
            source_id=proc2_urn,
            target_id=proc1_urn,
            relation_type=TwinRelationType.SPAWNED_BY,
            confidence=1.0,
        )
    )
    g.add_relationship(
        TwinRelationship(
            relation_id=f"rel-proc2-app-{device_id[:6]}",
            source_id=proc2_urn,
            target_id=app_urn,
            relation_type=TwinRelationType.OWNS,
            confidence=0.90,
        )
    )

    return g


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit and inspect digital twin graph node and edge persistence models."
    )
    parser.add_argument("--db", default=":memory:", help="SQLite database path (default: in-memory)")
    parser.add_argument("--audit", action="store_true", help="Execute packaging and safety invariant audit")
    parser.add_argument("--seed-mock", action="store_true", help="Seed sample property graph topology into database")
    parser.add_argument("--query", action="store_true", help="Query and list stored graph nodes and edges")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    if args.audit:
        result = GraphPersistenceValidator.audit(root_dir=ROOT_DIR)
        if args.json:
            payload = {
                "valid": result.valid,
                "issues": list(result.issues),
                "migration_present": result.migration_present,
                "persistence_models_present": result.persistence_models_present,
                "graph_engine_present": result.graph_engine_present,
                "design_note_present": result.design_note_present,
                "tool_present": result.tool_present,
                "ast_safety_valid": result.ast_safety_valid,
                "charter_invariants_valid": result.charter_invariants_valid,
                "graph_roundtrip_valid": result.graph_roundtrip_valid,
            }
            print(json.dumps(payload, indent=2))
            return 0 if result.valid else 1

        print("=" * 78)
        print(" SYSTEM MIND X — Graph Node & Edge Persistence Packaging Audit")
        print("=" * 78)
        print(f"Overall Valid:              {'PASS' if result.valid else 'FAIL'}")
        print(f"Migration 0004:             {'PASS' if result.migration_present else 'FAIL'}")
        print(f"Persistence Models:         {'PASS' if result.persistence_models_present else 'FAIL'}")
        print(f"Graph Engine:               {'PASS' if result.graph_engine_present else 'FAIL'}")
        print(f"Design Documentation:       {'PASS' if result.design_note_present else 'FAIL'}")
        print(f"CLI Tool:                   {'PASS' if result.tool_present else 'FAIL'}")
        print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, zero os.system)' if result.ast_safety_valid else 'FAIL'}")
        print(f"Charter Invariant (SC-03):  {'PASS (scan_proves_safe = False)' if result.charter_invariants_valid else 'FAIL'}")
        print(f"Graph Roundtrip (Up/Down):  {'PASS (Lossless graph reconstruction)' if result.graph_roundtrip_valid else 'FAIL'}")
        print("-" * 78)

        if result.issues:
            print("Issues Detected:")
            for issue in result.issues:
                print(f"  [!] {issue}")
            print("-" * 78)
            print("OVERALL VERDICT: FAILED")
            return 1

        print("OVERALL VERDICT: PASSED")
        return 0

    # Default action: run migrations, optionally seed, and query
    migrator = DatabaseMigrator(db_path=args.db)
    conn = migrator._get_connection()
    try:
        migrator.apply_all(conn=conn)
        mgr = GraphPersistenceManager(conn)
        device_id = DeviceIdentifierManager.resolve_device_id(
            hardware_uuid="mock-hardware-anchor-device-068",
            use_cache=False,
        )

        if args.seed_mock or args.db == ":memory:":
            initial_graph = build_sample_graph(device_id)
            mgr.persist_graph(initial_graph)

        counts = mgr.count_graph_elements()
        reconstructed = mgr.load_graph()
        nodes = mgr.list_nodes()
        edges = mgr.list_edges()

        # Execute sample traversal on reconstructed graph
        agent_proc_urn = str(
            StableEntityIdGenerator.generate_process_urn(
                device_id, 501, 2000, "/usr/local/bin/system-mind-agent"
            )
        )
        ancestors = reconstructed.get_process_ancestors(agent_proc_urn)

        if args.json:
            payload = {
                "db": args.db,
                "device_id": device_id,
                "counts": counts,
                "scan_proves_safe": False,
                "nodes": [n.to_dict() for n in nodes],
                "edges": [e.to_dict() for e in edges],
                "process_ancestors": [a.entity_id for a in ancestors],
            }
            print(json.dumps(payload, indent=2))
            return 0

        print("=" * 78)
        print(" SYSTEM MIND X — Digital Twin Graph Persistence Summary")
        print("=" * 78)
        print(f"Database Target:            {args.db}")
        print(f"Active Device ID:           {device_id}")
        print(f"Graph Nodes Stored:         {counts['nodes']}")
        print(f"Graph Edges Stored:         {counts['edges']}")
        print(f"Total Graph Elements:       {counts['total']}")
        print(f"Charter Invariant:          scan_proves_safe = False (Enforced)")
        print("-" * 78)
        print("Graph Nodes:")
        for n in nodes:
            print(f"  [{n.node_type.value:<16}] [{n.ownership.value:<14}] {n.node_id}")
        print("\nGraph Directed Edges:")
        for e in edges:
            print(
                f"  ({e.relation_type.value:<14}) [conf={e.confidence:.2f}] {e.source_node_id} -> {e.target_node_id}"
            )
        print("\nReconstructed Graph Hierarchy Query (Process SPAWNED_BY Ancestors):")
        print(f"  Target: {agent_proc_urn}")
        for anc in ancestors:
            print(f"    ^ Parent Process: {anc.entity_id} ({anc.attributes.get('name')})")
        print("=" * 78)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
