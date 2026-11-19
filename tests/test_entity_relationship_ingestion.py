"""Unit, integration, and safety invariant tests for Day 071 Entity Relationship Ingestion."""

from __future__ import annotations

import ast
from pathlib import Path
import pytest
import sqlite3

from system_mind.core.types import ComponentOwnership
from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import InventorySection, MacOsInventoryRequest
from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.packaging.entity_ingestion import (
    EntityIngestionAuditResult,
    EntityIngestionValidator,
)
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.ingestion import (
    EntityRelationshipIngestor,
    IngestionResult,
)
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinRelationship,
    TwinRelationType,
)
from system_mind.twin.persistence import GraphPersistenceManager

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    """Fixture providing an in-memory SQLite database migrated to latest schema."""
    cfg = DatabaseConfig(":memory:")
    conn = DatabaseConnectionManager.connect(cfg)
    migrator = DatabaseMigrator(config=cfg)
    migrator.apply_all(conn=conn)
    return conn


@pytest.fixture
def sample_sections() -> dict:
    """Fixture providing a deterministic multi-domain telemetry snapshot."""
    return {
        "identity": {
            "os_name": "macOS",
            "os_version": "15.1",
            "os_build": "24B83",
            "kernel_release": "24.1.0",
            "architecture": "arm64",
            "host_name": "developer-macbook",
        },
        "hardware": {
            "cpu": {
                "brand_string": "Apple M3 Pro",
                "physical_cores": 12,
                "logical_cores": 12,
                "architecture": "arm64",
            },
            "memory": {
                "total_bytes": 19327352832,
                "page_size": 16384,
            },
            "gpu": {
                "gpus": [{"model": "Apple M3 Pro GPU", "cores": 18, "metal_version": "Metal 3"}],
            },
        },
        "storage": {
            "volumes": [
                {
                    "volume_name": "Macintosh HD",
                    "mount_point": "/",
                    "fs_type": "apfs",
                    "total_bytes": 1000000000000,
                    "free_bytes": 600000000000,
                    "is_boot_volume": True,
                }
            ]
        },
        "network": {
            "interfaces": [
                {
                    "interface_name": "en0",
                    "mac_address_hash": "a1b2c3d4",
                    "ip_address": "192.168.1.50",
                    "link_state": "UP",
                }
            ]
        },
        "applications": {
            "applications": [
                {
                    "name": "Google Chrome",
                    "bundle_id": "com.google.Chrome",
                    "bundle_path": "/Applications/Google Chrome.app",
                    "version": "130.0.6723.117",
                    "ownership": ComponentOwnership.USER_MANAGED.value,
                    "is_user_app": True,
                    "is_apple": False,
                    "executable_name": "Google Chrome",
                },
                {
                    "name": "Safari",
                    "bundle_id": "com.apple.Safari",
                    "bundle_path": "/System/Cryptexes/App/System/Applications/Safari.app",
                    "version": "18.1",
                    "ownership": ComponentOwnership.SYSTEM_MANAGED.value,
                    "is_user_app": False,
                    "is_apple": True,
                    "executable_name": "Safari",
                },
            ]
        },
        "processes": {
            "processes": [
                {
                    "pid": 1,
                    "ppid": 0,
                    "name": "launchd",
                    "command_path": "/sbin/launchd",
                    "ownership": ComponentOwnership.SYSTEM_MANAGED.value,
                    "is_system_core": True,
                },
                {
                    "pid": 1001,
                    "ppid": 1,
                    "name": "Google Chrome",
                    "command_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "ownership": ComponentOwnership.USER_MANAGED.value,
                    "is_user_app": True,
                },
                {
                    "pid": 1002,
                    "ppid": 1001,
                    "name": "Google Chrome Helper",
                    "command_path": "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework/Helpers/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper",
                    "ownership": ComponentOwnership.USER_MANAGED.value,
                    "is_user_app": True,
                },
            ]
        },
        "services": {
            "services": [
                {
                    "label": "com.apple.Finder",
                    "domain": "system_agent",
                    "status": "RUNNING",
                    "program": "/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
                    "pid": 1,
                }
            ]
        },
    }


def test_entity_relationship_ingestion_from_inventory() -> None:
    """Verify ingestion from a full MacOsInventoryResponse creates valid graph topology."""
    api = MacOsInventoryApi()
    req = MacOsInventoryRequest(sections=[InventorySection.ALL], use_mock=True, mock_profile="high_fidelity")
    inv_response = api.get_inventory(req)

    graph = DigitalTwinGraph()
    ingestor = EntityRelationshipIngestor(device_id="8b14bd5b-dcd4-5d39-af4e-3e95c72e53ab")
    result = ingestor.ingest_inventory(inv_response, graph=graph)

    assert isinstance(result, IngestionResult)
    assert result.entities_ingested >= 15
    assert result.relationships_ingested >= 15
    assert result.scan_proves_safe is False

    # Referential integrity check
    is_valid, violations = graph.validate_integrity()
    assert is_valid is True, f"Graph integrity violations: {violations}"

    # Verify Host contains Kernel
    host_ents = graph.get_entities_by_type(TwinEntityType.HOST)
    assert len(host_ents) == 1
    host = host_ents[0]

    kernel_ents = graph.get_entities_by_type(TwinEntityType.OS_KERNEL)
    assert len(kernel_ents) == 1
    kernel = kernel_ents[0]

    host_contains = graph.get_outgoing_relationships(host.entity_id, relation_type=TwinRelationType.CONTAINS)
    contains_targets = {r.target_id for r in host_contains}
    assert kernel.entity_id in contains_targets


def test_entity_relationship_ingestion_from_companion_batch() -> None:
    """Verify ingestion from CompanionObservationBatch builds correct entity graph."""
    engine = MacOsObservationEngine()
    batch = engine.collect_batch(use_mock=True, profile="high_fidelity")

    graph = DigitalTwinGraph()
    ingestor = EntityRelationshipIngestor(device_id="8b14bd5b-dcd4-5d39-af4e-3e95c72e53ab")
    result = ingestor.ingest_companion_batch(batch, graph=graph)

    assert result.entities_ingested > 0
    assert result.relationships_ingested > 0

    is_valid, violations = graph.validate_integrity()
    assert is_valid is True, f"Graph integrity violations: {violations}"


def test_process_lineage_and_hierarchy(sample_sections: dict) -> None:
    """Verify process parent-child ancestry tree (SPAWNED_BY) is properly constructed."""
    graph = DigitalTwinGraph()
    ingestor = EntityRelationshipIngestor(device_id="test-device-uuid")
    result = ingestor.ingest_sections(sample_sections, graph=graph)

    spawned_by_rels = [r for r in result.relationships if r.relation_type == TwinRelationType.SPAWNED_BY]
    assert len(spawned_by_rels) == 2  # PID 1001 -> 1, PID 1002 -> 1001

    # Find helper process (PID 1002)
    helper_urn = [
        ent.entity_id
        for ent in result.entities
        if ent.entity_type == TwinEntityType.PROCESS and ent.attributes.get("pid") == 1002
    ][0]

    # Traverse process ancestry via DigitalTwinGraph
    ancestors = graph.get_process_ancestors(helper_urn)
    assert len(ancestors) == 2  # Chrome (1001) then launchd (1)
    assert ancestors[0].attributes["pid"] == 1001
    assert ancestors[1].attributes["pid"] == 1


def test_application_process_ownership(sample_sections: dict) -> None:
    """Verify Application -> OWNS -> Process edge connects Chrome app bundle to Chrome process."""
    graph = DigitalTwinGraph()
    ingestor = EntityRelationshipIngestor(device_id="test-device-uuid")
    result = ingestor.ingest_sections(sample_sections, graph=graph)

    owns_rels = [r for r in result.relationships if r.relation_type == TwinRelationType.OWNS]
    assert len(owns_rels) >= 1

    # Locate Chrome app and Chrome process
    chrome_app = [e for e in result.entities if e.entity_type == TwinEntityType.APPLICATION and "chrome" in e.entity_id.lower()][0]
    chrome_proc = [e for e in result.entities if e.entity_type == TwinEntityType.PROCESS and e.attributes.get("pid") == 1001][0]

    app_owns = graph.get_outgoing_relationships(chrome_app.entity_id, relation_type=TwinRelationType.OWNS)
    owned_procs = {r.target_id for r in app_owns}
    assert chrome_proc.entity_id in owned_procs

    # Verify ownership category is preserved (USER_MANAGED)
    assert chrome_app.ownership == ComponentOwnership.USER_MANAGED
    assert chrome_proc.ownership == ComponentOwnership.USER_MANAGED


def test_charter_invariant_sc03_scan_proves_safe_is_false() -> None:
    """Verify non-negotiable charter invariant SC-03: scan_proves_safe must always be False."""
    with pytest.raises(ValueError, match="scan_proves_safe must always be False"):
        IngestionResult(
            ingestion_id="test",
            device_id="dev",
            timestamp_utc="2026-11-18T12:00:00Z",
            entities_ingested=0,
            relationships_ingested=0,
            entities=(),
            relationships=(),
            warnings=(),
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    res = IngestionResult(
        ingestion_id="test",
        device_id="dev",
        timestamp_utc="2026-11-18T12:00:00Z",
        entities_ingested=0,
        relationships_ingested=0,
        entities=(),
        relationships=(),
        warnings=(),
    )
    assert res.scan_proves_safe is False
    assert res.to_dict()["scan_proves_safe"] is False


def test_database_persistence_integration(in_memory_db: sqlite3.Connection, sample_sections: dict) -> None:
    """Verify ingested graph persists into SQLite tables graph_nodes and graph_edges."""
    persistence_manager = GraphPersistenceManager(in_memory_db)
    graph = DigitalTwinGraph()
    ingestor = EntityRelationshipIngestor(device_id="persisted-device-uuid")

    result = ingestor.ingest_sections(sample_sections, graph=graph, persistence_manager=persistence_manager)

    # Check database row counts
    nodes_cur = in_memory_db.execute("SELECT COUNT(*) FROM graph_nodes;")
    node_count = nodes_cur.fetchone()[0]
    assert node_count == result.entities_ingested

    edges_cur = in_memory_db.execute("SELECT COUNT(*) FROM graph_edges;")
    edge_count = edges_cur.fetchone()[0]
    assert edge_count == result.relationships_ingested

    # Load back into a fresh graph
    loaded_graph = persistence_manager.load_graph()
    assert loaded_graph.entity_count == graph.entity_count
    assert loaded_graph.relationship_count == graph.relationship_count

    is_valid, violations = loaded_graph.validate_integrity()
    assert is_valid is True, f"Loaded graph integrity violations: {violations}"


def test_idempotent_reingestion(sample_sections: dict) -> None:
    """Verify executing ingestion multiple times on the same graph updates safely without duplicates."""
    graph = DigitalTwinGraph()
    ingestor = EntityRelationshipIngestor(device_id="idempotent-device-uuid")

    # Pass 1
    res1 = ingestor.ingest_sections(sample_sections, graph=graph)
    cnt_nodes1 = graph.entity_count
    cnt_edges1 = graph.relationship_count

    # Pass 2 with updated attribute
    sample_sections["identity"]["host_name"] = "updated-hostname"
    res2 = ingestor.ingest_sections(sample_sections, graph=graph)

    assert graph.entity_count == cnt_nodes1
    assert graph.relationship_count == cnt_edges1

    is_valid, violations = graph.validate_integrity()
    assert is_valid is True, f"Idempotent graph integrity violations: {violations}"


def test_entity_ingestion_packaging_validator() -> None:
    """Verify EntityIngestionValidator clean audit passes with 0 issues."""
    audit_res = EntityIngestionValidator.audit()
    assert isinstance(audit_res, EntityIngestionAuditResult)
    assert audit_res.ingestion_engine_present is True
    assert audit_res.design_note_present is True
    assert audit_res.tool_present is True
    assert audit_res.ast_safety_valid is True
    assert audit_res.charter_invariants_valid is True
    assert audit_res.functional_ingestion_valid is True
    assert audit_res.valid is True
    assert len(audit_res.issues) == 0


def test_ast_safety_sc01_zero_ambient_shell() -> None:
    """Verify AST safety invariant SC-01 (zero shell=True, zero os.system)."""
    target_files = [
        ROOT_DIR / "src" / "system_mind" / "twin" / "ingestion.py",
        ROOT_DIR / "tools" / "detect_entity_ingestion.py",
    ]

    for tf in target_files:
        assert tf.exists(), f"File {tf} must exist"
        tree = ast.parse(tf.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        assert node.func.attr not in ("system", "popen"), f"Forbidden os.{node.func.attr} in {tf.name}"
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is not True, f"Forbidden shell=True in {tf.name}"
