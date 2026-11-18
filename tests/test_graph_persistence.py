"""Unit, integration, and safety invariant test suite for Day 068 Graph Node and Edge Persistence Models."""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import pytest

from system_mind.core.types import ComponentOwnership
from system_mind.database.migrator import DatabaseMigrator
from system_mind.packaging.graph_persistence import GraphPersistenceValidator
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import StableEntityIdGenerator
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinRelationship,
    TwinRelationType,
)
from system_mind.twin.persistence import (
    GraphEdgeRecord,
    GraphNodeRecord,
    GraphPersistenceManager,
)


@pytest.fixture
def memory_db_conn() -> sqlite3.Connection:
    """Provides an in-memory SQLite connection with all migrations applied."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    migrator.apply_all(conn=conn)
    yield conn
    conn.close()


def test_migration_0004_up_and_down_lifecycle() -> None:
    """Verifies that migration 0004 creates graph tables/indices and rolls back cleanly."""
    migrator = DatabaseMigrator(db_path=":memory:")
    conn = migrator._get_connection()
    try:
        migrator.apply_all(conn=conn)

        # Verify tables exist
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "graph_nodes" in tables
        assert "graph_edges" in tables

        # Rollback migration 0004 and later migrations down to version 3
        rolled_back = migrator.rollback_to(target_version=3, conn=conn)
        assert any(r.version == 4 for r in rolled_back)

        # Verify tables dropped
        tables_after = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "graph_nodes" not in tables_after
        assert "graph_edges" not in tables_after

        # Re-apply
        reapplied = migrator.apply_migration(4, conn=conn)
        assert reapplied.version == 4
    finally:
        conn.close()


def test_graph_node_record_validation_and_serialization(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies GraphNodeRecord validation, serialization, and check constraints."""
    node_id = "urn:systemmind:host:d5a1b3c9"
    node = GraphNodeRecord(
        node_id=node_id,
        node_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"model": "Apple Silicon Host"},
        provenance_source="native_ioreg",
    )

    # Invariant: scan_proves_safe is strictly False
    assert node.scan_proves_safe is False
    with pytest.raises(ValueError, match="Charter invariant violation"):
        GraphNodeRecord(
            node_id=node_id,
            node_type=TwinEntityType.HOST,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    # Empty node_id rejected
    with pytest.raises(ValueError, match="node_id must not be empty"):
        GraphNodeRecord(
            node_id="",
            node_type=TwinEntityType.HOST,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
        )

    # Test roundtrip dict serialization
    d = node.to_dict()
    assert d["node_id"] == node_id
    assert d["node_type"] == "HOST"
    assert d["ownership"] == "SYSTEM_MANAGED"
    from_d = GraphNodeRecord.from_dict(d)
    assert from_d == node

    # Test conversion to/from TwinEntity
    twin_entity = node.to_twin_entity()
    assert twin_entity.entity_id == node.node_id
    assert twin_entity.entity_type == TwinEntityType.HOST
    converted_back = GraphNodeRecord.from_twin_entity(twin_entity)
    assert converted_back.node_id == node.node_id

    # Database level check constraint verification (SC-03)
    with pytest.raises(sqlite3.IntegrityError):
        memory_db_conn.execute(
            """
            INSERT INTO graph_nodes (
                node_id, node_type, ownership, created_at, updated_at, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (node_id, "HOST", "SYSTEM_MANAGED", "2026-11-18T00:00:00Z", "2026-11-18T00:00:00Z", 1),
        )


def test_graph_edge_record_validation_and_serialization(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies GraphEdgeRecord validation, serialization, confidence bounds, and constraints."""
    edge = GraphEdgeRecord(
        edge_id="rel-001",
        source_node_id="urn:systemmind:host:d5a1b3c9",
        target_node_id="urn:systemmind:kernel:darwin:24.0.0",
        relation_type=TwinRelationType.CONTAINS,
        properties={"slot": 0},
        confidence=0.95,
    )

    # Invariant: scan_proves_safe is strictly False
    assert edge.scan_proves_safe is False
    with pytest.raises(ValueError, match="Charter invariant violation"):
        GraphEdgeRecord(
            edge_id="rel-001",
            source_node_id="urn:systemmind:host:d5a1b3c9",
            target_node_id="urn:systemmind:kernel:darwin:24.0.0",
            relation_type=TwinRelationType.CONTAINS,
            scan_proves_safe=True,  # type: ignore[arg-type]
        )

    # Confidence score out of bounds
    with pytest.raises(ValueError, match="Confidence score"):
        GraphEdgeRecord(
            edge_id="rel-001",
            source_node_id="urn:systemmind:host:d5a1b3c9",
            target_node_id="urn:systemmind:kernel:darwin:24.0.0",
            relation_type=TwinRelationType.CONTAINS,
            confidence=1.5,
        )

    # Dict roundtrip
    d = edge.to_dict()
    assert d["edge_id"] == "rel-001"
    assert d["relation_type"] == "CONTAINS"
    assert d["confidence"] == 0.95
    from_d = GraphEdgeRecord.from_dict(d)
    assert from_d == edge

    # TwinRelationship conversion
    twin_rel = edge.to_twin_relationship()
    assert twin_rel.relation_id == edge.edge_id
    assert twin_rel.relation_type == TwinRelationType.CONTAINS
    converted_back = GraphEdgeRecord.from_twin_relationship(twin_rel)
    assert converted_back.edge_id == edge.edge_id


def test_graph_persistence_manager_node_crud(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies GraphPersistenceManager CRUD operations on nodes."""
    mgr = GraphPersistenceManager(memory_db_conn)

    node1 = GraphNodeRecord(
        node_id="urn:systemmind:host:d5a1b3c9",
        node_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"cores": 8},
    )
    node2 = GraphNodeRecord(
        node_id="urn:systemmind:app:com.apple.safari",
        node_type=TwinEntityType.APPLICATION,
        ownership=ComponentOwnership.VENDOR_MANAGED,
        is_stale=True,
    )

    mgr.save_node(node1)
    mgr.save_node(node2)

    # Get node
    fetched = mgr.get_node(node1.node_id)
    assert fetched is not None
    assert fetched.node_type == TwinEntityType.HOST
    assert fetched.attributes["cores"] == 8

    # List nodes with filtering
    hosts = mgr.list_nodes(node_type=TwinEntityType.HOST)
    assert len(hosts) == 1
    assert hosts[0].node_id == node1.node_id

    stale_nodes = mgr.list_nodes(is_stale=True)
    assert len(stale_nodes) == 1
    assert stale_nodes[0].node_id == node2.node_id

    # Delete node
    assert mgr.delete_node(node1.node_id) is True
    assert mgr.get_node(node1.node_id) is None


def test_graph_persistence_manager_edge_crud(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies GraphPersistenceManager CRUD operations on edges."""
    mgr = GraphPersistenceManager(memory_db_conn)

    # Insert prerequisite nodes
    n1 = GraphNodeRecord(
        node_id="urn:systemmind:host:d5a1b3c9",
        node_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
    )
    n2 = GraphNodeRecord(
        node_id="urn:systemmind:kernel:darwin",
        node_type=TwinEntityType.OS_KERNEL,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
    )
    mgr.save_node(n1)
    mgr.save_node(n2)

    edge = GraphEdgeRecord(
        edge_id="rel-h-k",
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relation_type=TwinRelationType.CONTAINS,
        confidence=1.0,
    )
    mgr.save_edge(edge)

    fetched = mgr.get_edge("rel-h-k")
    assert fetched is not None
    assert fetched.source_node_id == n1.node_id
    assert fetched.relation_type == TwinRelationType.CONTAINS

    # Filter edges
    by_source = mgr.list_edges(source_node_id=n1.node_id)
    assert len(by_source) == 1

    by_type = mgr.list_edges(relation_type=TwinRelationType.CONTAINS)
    assert len(by_type) == 1

    assert mgr.delete_edge("rel-h-k") is True
    assert mgr.get_edge("rel-h-k") is None


def test_graph_foreign_key_referential_integrity_and_cascade(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies SQLite foreign key constraints and cascading edge deletion."""
    mgr = GraphPersistenceManager(memory_db_conn)

    n1 = GraphNodeRecord(
        node_id="urn:systemmind:host:d5a1b3c9",
        node_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
    )
    n2 = GraphNodeRecord(
        node_id="urn:systemmind:kernel:darwin",
        node_type=TwinEntityType.OS_KERNEL,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
    )
    mgr.save_node(n1)
    mgr.save_node(n2)

    edge = GraphEdgeRecord(
        edge_id="rel-cascade-test",
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relation_type=TwinRelationType.CONTAINS,
    )
    mgr.save_edge(edge)

    # Deleting source node must cascade delete edge
    assert mgr.delete_node(n1.node_id) is True
    assert mgr.get_edge("rel-cascade-test") is None

    # Inserting edge referencing non-existent node must raise IntegrityError
    orphan_edge = GraphEdgeRecord(
        edge_id="rel-orphan",
        source_node_id="urn:systemmind:nonexistent:source",
        target_node_id=n2.node_id,
        relation_type=TwinRelationType.CONTAINS,
    )
    with pytest.raises(sqlite3.IntegrityError):
        mgr.save_edge(orphan_edge)


def test_full_graph_persist_and_load_roundtrip(memory_db_conn: sqlite3.Connection) -> None:
    """Verifies that an in-memory DigitalTwinGraph round-trips losslessly through SQLite."""
    mgr = GraphPersistenceManager(memory_db_conn)

    # Build rich in-memory graph
    g = DigitalTwinGraph()
    e_host = TwinEntity(
        entity_id="urn:systemmind:host:h1",
        entity_type=TwinEntityType.HOST,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="test_sensor",
    )
    e_kernel = TwinEntity(
        entity_id="urn:systemmind:kernel:k1",
        entity_type=TwinEntityType.OS_KERNEL,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        provenance_source="test_sensor",
    )
    e_proc1 = TwinEntity(
        entity_id="urn:systemmind:proc:p1",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.SYSTEM_MANAGED,
        attributes={"name": "launchd", "pid": 1},
        provenance_source="test_sensor",
    )
    e_proc2 = TwinEntity(
        entity_id="urn:systemmind:proc:p2",
        entity_type=TwinEntityType.PROCESS,
        ownership=ComponentOwnership.USER_MANAGED,
        attributes={"name": "agent", "pid": 100},
        provenance_source="test_sensor",
    )
    e_app = TwinEntity(
        entity_id="urn:systemmind:app:a1",
        entity_type=TwinEntityType.APPLICATION,
        ownership=ComponentOwnership.USER_MANAGED,
        provenance_source="test_sensor",
    )

    g.add_entity(e_host)
    g.add_entity(e_kernel)
    g.add_entity(e_proc1)
    g.add_entity(e_proc2)
    g.add_entity(e_app)

    g.add_relationship(
        TwinRelationship(
            relation_id="rel-1",
            source_id=e_host.entity_id,
            target_id=e_kernel.entity_id,
            relation_type=TwinRelationType.CONTAINS,
        )
    )
    g.add_relationship(
        TwinRelationship(
            relation_id="rel-2",
            source_id=e_kernel.entity_id,
            target_id=e_proc1.entity_id,
            relation_type=TwinRelationType.ENFORCES_POLICY,
        )
    )
    g.add_relationship(
        TwinRelationship(
            relation_id="rel-3",
            source_id=e_proc2.entity_id,
            target_id=e_proc1.entity_id,
            relation_type=TwinRelationType.SPAWNED_BY,
        )
    )
    g.add_relationship(
        TwinRelationship(
            relation_id="rel-4",
            source_id=e_proc2.entity_id,
            target_id=e_app.entity_id,
            relation_type=TwinRelationType.OWNS,
        )
    )

    # Persist graph
    saved_nodes, saved_edges = mgr.persist_graph(g)
    assert saved_nodes == 5
    assert saved_edges == 4

    # Load graph back
    reconstructed = mgr.load_graph()
    assert reconstructed.entity_count == 5
    assert reconstructed.relationship_count == 4

    # Verify graph traversal queries on reconstructed graph
    ancestors = reconstructed.get_process_ancestors(e_proc2.entity_id)
    assert len(ancestors) == 1
    assert ancestors[0].entity_id == e_proc1.entity_id

    # Verify integrity of reconstructed graph
    is_valid, violations = reconstructed.validate_integrity()
    assert is_valid is True
    assert violations == []


def test_graph_persistence_packaging_validator() -> None:
    """Verifies that GraphPersistenceValidator audits cleanly."""
    result = GraphPersistenceValidator.audit()
    assert result.valid is True
    assert result.issues == ()
    assert result.migration_present is True
    assert result.persistence_models_present is True
    assert result.graph_engine_present is True
    assert result.design_note_present is True
    assert result.tool_present is True
    assert result.ast_safety_valid is True
    assert result.charter_invariants_valid is True
    assert result.graph_roundtrip_valid is True


def test_ast_safety_sc01_zero_ambient_shell() -> None:
    """SC-01 AST check: zero ambient shell authority across graph persistence files."""
    root = Path(__file__).resolve().parent.parent
    files_to_check = [
        root / "src/system_mind/twin/persistence.py",
        root / "src/system_mind/packaging/graph_persistence.py",
        root / "tools/detect_graph_persistence.py",
    ]

    for f in files_to_check:
        assert f.is_file()
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        assert node.func.attr not in ("system", "popen")
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is False
