"""Packaging and safety invariant validator for Day 068 Graph Node and Edge Persistence Models."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class GraphPersistenceAuditResult:
    """Outcome of auditing Day 068 graph persistence models, schemas, and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    migration_present: bool
    persistence_models_present: bool
    graph_engine_present: bool
    design_note_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    graph_roundtrip_valid: bool


class GraphPersistenceValidator:
    """Audits the completeness, safety, and packaging of Day 068 graph persistence models."""

    REQUIRED_FILES = [
        Path("src/system_mind/database/migrations/0004_graph_nodes_and_edges.sql"),
        Path("src/system_mind/twin/persistence.py"),
        Path("src/system_mind/twin/graph.py"),
        Path("docs/design/DAY_068_GRAPH_NODE_AND_EDGE_PERSISTENCE.md"),
        Path("tools/detect_graph_persistence.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> GraphPersistenceAuditResult:
        """Executes comprehensive packaging audit across digital twin graph persistence components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        mig_file = base / "src/system_mind/database/migrations/0004_graph_nodes_and_edges.sql"
        persistence_file = base / "src/system_mind/twin/persistence.py"
        graph_file = base / "src/system_mind/twin/graph.py"
        design_file = base / "docs/design/DAY_068_GRAPH_NODE_AND_EDGE_PERSISTENCE.md"
        tool_file = base / "tools/detect_graph_persistence.py"

        migration_present = mig_file.is_file()
        persistence_models_present = persistence_file.is_file()
        graph_engine_present = graph_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [persistence_file, tool_file]
        for pf in python_files:
            if pf.is_file():
                try:
                    tree = ast.parse(pf.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Attribute):
                                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                    if node.func.attr in ("system", "popen"):
                                        issues.append(f"Forbidden call to os.{node.func.attr} in {pf.name}")
                                        ast_safety_valid = False
                            for kw in node.keywords:
                                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                    issues.append(f"Forbidden shell=True in {pf.name}")
                                    ast_safety_valid = False
                except Exception as e:
                    issues.append(f"Failed to parse AST of {pf.name}: {e}")
                    ast_safety_valid = False

        # Invariant checks on runtime models (SC-03: scan_proves_safe = False)
        charter_invariants_valid = True
        try:
            from system_mind.core.types import ComponentOwnership
            from system_mind.twin.models import TwinEntity, TwinEntityType, TwinRelationship, TwinRelationType
            from system_mind.twin.persistence import (
                GraphEdgeRecord,
                GraphNodeRecord,
                GraphPersistenceManager,
            )

            # Node model checks
            node = GraphNodeRecord(
                node_id="urn:systemmind:host:d5a1b3c9",
                node_type=TwinEntityType.HOST,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
            )
            if node.scan_proves_safe is not False:
                issues.append("GraphNodeRecord violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                GraphNodeRecord(
                    node_id="urn:systemmind:host:d5a1b3c9",
                    node_type=TwinEntityType.HOST,
                    ownership=ComponentOwnership.SYSTEM_MANAGED,
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append("GraphNodeRecord permitted scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correct

            # Edge model checks
            edge = GraphEdgeRecord(
                edge_id="rel-001",
                source_node_id="urn:systemmind:host:d5a1b3c9",
                target_node_id="urn:systemmind:cpu:arm64:001",
                relation_type=TwinRelationType.CONTAINS,
            )
            if edge.scan_proves_safe is not False:
                issues.append("GraphEdgeRecord violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                GraphEdgeRecord(
                    edge_id="rel-001",
                    source_node_id="urn:systemmind:host:d5a1b3c9",
                    target_node_id="urn:systemmind:cpu:arm64:001",
                    relation_type=TwinRelationType.CONTAINS,
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append("GraphEdgeRecord permitted scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correct
        except Exception as e:
            issues.append(f"Failed to inspect graph persistence model invariants: {e}")
            charter_invariants_valid = False

        # In-memory graph roundtrip test
        graph_roundtrip_valid = True
        try:
            from system_mind.database.migrator import DatabaseMigrator
            from system_mind.twin.graph import DigitalTwinGraph

            migrator = DatabaseMigrator(db_path=":memory:")
            conn = migrator._get_connection()
            try:
                migrator.apply_all(conn=conn)
                mgr = GraphPersistenceManager(conn)

                # Construct in-memory graph
                g = DigitalTwinGraph()
                e1 = TwinEntity(
                    entity_id="urn:systemmind:host:test-h1",
                    entity_type=TwinEntityType.HOST,
                    ownership=ComponentOwnership.SYSTEM_MANAGED,
                    provenance_source="test_pipeline",
                )
                e2 = TwinEntity(
                    entity_id="urn:systemmind:proc:test-p1",
                    entity_type=TwinEntityType.PROCESS,
                    ownership=ComponentOwnership.USER_MANAGED,
                    provenance_source="test_pipeline",
                )
                r1 = TwinRelationship(
                    relation_id="rel-h1-p1",
                    source_id=e1.entity_id,
                    target_id=e2.entity_id,
                    relation_type=TwinRelationType.CONTAINS,
                )
                g.add_entity(e1)
                g.add_entity(e2)
                g.add_relationship(r1)

                # Persist to SQLite
                saved_nodes, saved_edges = mgr.persist_graph(g)
                if saved_nodes != 2 or saved_edges != 1:
                    issues.append(f"Unexpected persist counts: {saved_nodes} nodes, {saved_edges} edges")
                    graph_roundtrip_valid = False

                # Load back from SQLite
                reconstructed = mgr.load_graph()
                if reconstructed.entity_count != 2 or reconstructed.relationship_count != 1:
                    issues.append("Failed graph roundtrip: node or relationship count mismatch")
                    graph_roundtrip_valid = False

                # Rollback all migrations to verify teardown
                migrator.rollback_to(0, conn=conn)
            finally:
                conn.close()
        except Exception as e:
            issues.append(f"Failed to execute graph persistence roundtrip: {e}")
            graph_roundtrip_valid = False

        valid = len(issues) == 0

        return GraphPersistenceAuditResult(
            valid=valid,
            issues=tuple(issues),
            migration_present=migration_present,
            persistence_models_present=persistence_models_present,
            graph_engine_present=graph_engine_present,
            design_note_present=design_note_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            graph_roundtrip_valid=graph_roundtrip_valid,
        )
