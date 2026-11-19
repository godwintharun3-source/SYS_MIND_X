#!/usr/bin/env python3
"""CLI utility for auditing and demonstrating digital twin entity relationship ingestion from collectors."""

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
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import InventorySection, MacOsInventoryRequest
from system_mind.packaging.entity_ingestion import EntityIngestionValidator
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import DeviceIdentifierManager
from system_mind.twin.ingestion import EntityRelationshipIngestor, IngestionResult
from system_mind.twin.models import TwinEntityType, TwinRelationType
from system_mind.twin.persistence import GraphPersistenceManager


def run_audit() -> int:
    """Run comprehensive packaging and invariant audit."""
    result = EntityIngestionValidator.audit()

    print("==============================================================================")
    print(" SYSTEM MIND X — Entity Relationship Ingestion Packaging Audit")
    print("==============================================================================")
    print(f"Overall Valid:              {'PASS' if result.valid else 'FAIL'}")
    print(f"Ingestion Engine Present:   {'PASS' if result.ingestion_engine_present else 'FAIL'}")
    print(f"Design Documentation:       {'PASS' if result.design_note_present else 'FAIL'}")
    print(f"CLI Tool Present:           {'PASS' if result.tool_present else 'FAIL'}")
    print(f"AST Safety (SC-01):         {'PASS (Zero shell=True, zero os.system)' if result.ast_safety_valid else 'FAIL'}")
    print(f"Charter Invariant (SC-03):  {'PASS (scan_proves_safe = False)' if result.charter_invariants_valid else 'FAIL'}")
    print(f"Functional Ingestion:       {'PASS (Referential integrity verified)' if result.functional_ingestion_valid else 'FAIL'}")
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
        description="SYSTEM MIND X — Digital Twin Entity Relationship Ingestion CLI"
    )
    parser.add_argument("--audit", action="store_true", help="Run packaging and safety invariant audit")
    parser.add_argument("--mock", action="store_true", default=True, help="Use mock telemetry collector (default)")
    parser.add_argument("--profile", default="high_fidelity", help="Mock profile (high_fidelity, degraded)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")
    parser.add_argument("--device-id", default=None, help="Explicit target device ID")
    parser.add_argument("--persist", action="store_true", help="Persist ingested graph into in-memory SQLite tables")

    args = parser.parse_args()

    if args.audit:
        return run_audit()

    device_id = args.device_id or DeviceIdentifierManager.resolve_device_id()
    graph = DigitalTwinGraph()

    # Optional in-memory SQLite database setup
    persistence_manager = None
    if args.persist:
        db_cfg = DatabaseConfig(":memory:")
        conn = DatabaseConnectionManager.connect(db_cfg)
        migrator = DatabaseMigrator(config=db_cfg)
        migrator.apply_all(conn=conn)
        persistence_manager = GraphPersistenceManager(conn)

    # Collect telemetry via MacOsInventoryApi
    api = MacOsInventoryApi()
    req = MacOsInventoryRequest(
        sections=[InventorySection.ALL],
        use_mock=args.mock,
        mock_profile=args.profile,
    )
    inv_response = api.get_inventory(req)

    # Execute ingestion
    ingestor = EntityRelationshipIngestor(device_id=device_id)
    result = ingestor.ingest_inventory(
        inventory=inv_response,
        graph=graph,
        persistence_manager=persistence_manager,
    )

    if args.json:
        payload = result.to_dict()
        payload["graph_integrity_valid"] = graph.validate_integrity()[0]
        print(json.dumps(payload, indent=2))
        return 0

    # Human-readable output
    is_valid, violations = graph.validate_integrity()

    print("==============================================================================")
    print(" SYSTEM MIND X — Digital Twin Entity Relationship Ingestion Summary")
    print("==============================================================================")
    print(f"Ingestion ID:               {result.ingestion_id}")
    print(f"Target Device ID:           {result.device_id}")
    print(f"Timestamp:                  {result.timestamp_utc}")
    print(f"Duration:                   {result.duration_ms:.2f} ms")
    print(f"Total Entities Ingested:    {result.entities_ingested}")
    print(f"Total Edges Ingested:       {result.relationships_ingested}")
    print(f"Graph Referential Check:    {'PASS (Zero dangling edges)' if is_valid else 'FAIL'}")
    print(f"Charter Invariant (SC-03):  scan_proves_safe = False (Enforced)")
    print("------------------------------------------------------------------------------")

    # Group entities by type
    print("Entities Ingested by Type:")
    for ent_type in TwinEntityType:
        ents = graph.get_entities_by_type(ent_type)
        if ents:
            print(f"  • {ent_type.value:24} : {len(ents)} entities")

    print("------------------------------------------------------------------------------")
    print("Relationships Ingested by Type:")
    rel_type_counts: dict[str, int] = {}
    for rel in result.relationships:
        rel_type_counts[rel.relation_type.value] = rel_type_counts.get(rel.relation_type.value, 0) + 1
    for rt, cnt in sorted(rel_type_counts.items()):
        print(f"  • {rt:24} : {cnt} edges")

    print("------------------------------------------------------------------------------")
    print("Process Lineage Hierarchy (Sample SPAWNED_BY):")
    spawned_edges = [r for r in result.relationships if r.relation_type == TwinRelationType.SPAWNED_BY]
    if spawned_edges:
        for edge in spawned_edges[:5]:
            child = graph.get_entity(edge.source_id)
            parent = graph.get_entity(edge.target_id)
            c_name = child.attributes.get("name", "unknown") if child else "unknown"
            p_name = parent.attributes.get("name", "unknown") if parent else "unknown"
            print(f"  [Child {edge.properties.get('child_pid')}: {c_name}] -> SPAWNED_BY -> [Parent {edge.properties.get('parent_pid')}: {p_name}]")
    else:
        print("  (No child processes with known parent in sample)")

    print("------------------------------------------------------------------------------")
    print("Application Ownership (Sample OWNS):")
    owns_edges = [r for r in result.relationships if r.relation_type == TwinRelationType.OWNS]
    if owns_edges:
        for edge in owns_edges[:5]:
            app = graph.get_entity(edge.source_id)
            proc = graph.get_entity(edge.target_id)
            a_name = app.attributes.get("name", app.entity_id) if app else edge.source_id
            p_name = proc.attributes.get("name", proc.entity_id) if proc else edge.target_id
            print(f"  [App: {a_name}] -> OWNS -> [Proc {edge.properties.get('pid')}: {p_name}]")
    else:
        print("  (No direct application-to-process ownership links in sample)")

    print("==============================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
