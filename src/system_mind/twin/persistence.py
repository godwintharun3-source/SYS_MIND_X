"""Graph-node and graph-edge persistence models and SQLite repository for the Digital Twin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from system_mind.core.types import ComponentOwnership
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinEntityValidator,
    TwinRelationship,
    TwinRelationType,
)


@dataclass(frozen=True)
class GraphNodeRecord:
    """Relational database persistence representation of a digital twin graph node."""

    node_id: str
    node_type: TwinEntityType
    ownership: ComponentOwnership
    attributes: Dict[str, Any] = field(default_factory=dict)
    provenance_source: str = "telemetry_pipeline"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_stale: bool = False
    scan_proves_safe: bool = False  # Charter invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")
        if not self.node_id or not self.node_id.strip():
            raise ValueError("node_id must not be empty")
        if not isinstance(self.node_type, TwinEntityType):
            raise ValueError(f"Invalid node_type: {self.node_type}")
        if not isinstance(self.ownership, ComponentOwnership):
            raise ValueError(f"Invalid ownership: {self.ownership}")
        if not self.provenance_source or not self.provenance_source.strip():
            raise ValueError("provenance_source must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "ownership": self.ownership.value,
            "attributes": self.attributes,
            "provenance_source": self.provenance_source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_stale": self.is_stale,
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphNodeRecord:
        """Create record from dictionary."""
        node_type = (
            data["node_type"]
            if isinstance(data["node_type"], TwinEntityType)
            else TwinEntityType(data["node_type"])
        )
        ownership = (
            data["ownership"]
            if isinstance(data["ownership"], ComponentOwnership)
            else ComponentOwnership(data["ownership"])
        )
        return cls(
            node_id=data["node_id"],
            node_type=node_type,
            ownership=ownership,
            attributes=data.get("attributes", {}),
            provenance_source=data.get("provenance_source", "telemetry_pipeline"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            is_stale=data.get("is_stale", False),
            scan_proves_safe=data.get("scan_proves_safe", False),
        )

    def to_db_row(self) -> tuple:
        """Serialize to tuple for SQLite INSERT/UPDATE."""
        return (
            self.node_id,
            self.node_type.value,
            self.ownership.value,
            json.dumps(self.attributes, sort_keys=True),
            self.provenance_source,
            self.created_at,
            self.updated_at,
            1 if self.is_stale else 0,
            0,  # scan_proves_safe
        )

    @classmethod
    def from_db_row(cls, row: tuple | sqlite3.Row) -> GraphNodeRecord:
        """Deserialize from SQLite row tuple."""
        raw_attrs = row[3]
        attrs = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
        return cls(
            node_id=row[0],
            node_type=TwinEntityType(row[1]),
            ownership=ComponentOwnership(row[2]),
            attributes=attrs,
            provenance_source=row[4],
            created_at=row[5],
            updated_at=row[6],
            is_stale=bool(row[7]),
            scan_proves_safe=bool(row[8]),
        )

    def to_twin_entity(self) -> TwinEntity:
        """Convert record to an in-memory TwinEntity."""
        return TwinEntity(
            entity_id=self.node_id,
            entity_type=self.node_type,
            ownership=self.ownership,
            attributes=self.attributes,
            created_at=self.created_at,
            updated_at=self.updated_at,
            provenance_source=self.provenance_source,
            is_stale=self.is_stale,
        )

    @classmethod
    def from_twin_entity(cls, entity: TwinEntity) -> GraphNodeRecord:
        """Create a persistence record from an in-memory TwinEntity."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return cls(
            node_id=entity.entity_id,
            node_type=entity.entity_type,
            ownership=entity.ownership,
            attributes=entity.attributes,
            provenance_source=entity.provenance_source or "telemetry_pipeline",
            created_at=entity.created_at or now_iso,
            updated_at=entity.updated_at or now_iso,
            is_stale=entity.is_stale,
            scan_proves_safe=False,
        )


@dataclass(frozen=True)
class GraphEdgeRecord:
    """Relational database persistence representation of a digital twin directed graph edge."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: TwinRelationType
    properties: Dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = 1.0
    scan_proves_safe: bool = False  # Charter invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")
        if not self.edge_id or not self.edge_id.strip():
            raise ValueError("edge_id must not be empty")
        if not self.source_node_id or not self.source_node_id.strip():
            raise ValueError("source_node_id must not be empty")
        if not self.target_node_id or not self.target_node_id.strip():
            raise ValueError("target_node_id must not be empty")
        if not isinstance(self.relation_type, TwinRelationType):
            raise ValueError(f"Invalid relation_type: {self.relation_type}")
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError(f"Confidence score {self.confidence} must be between 0.0 and 1.0")

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation_type": self.relation_type.value,
            "properties": self.properties,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphEdgeRecord:
        """Create record from dictionary."""
        rel_type = (
            data["relation_type"]
            if isinstance(data["relation_type"], TwinRelationType)
            else TwinRelationType(data["relation_type"])
        )
        return cls(
            edge_id=data["edge_id"],
            source_node_id=data["source_node_id"],
            target_node_id=data["target_node_id"],
            relation_type=rel_type,
            properties=data.get("properties", {}),
            observed_at=data.get("observed_at", ""),
            confidence=data.get("confidence", 1.0),
            scan_proves_safe=data.get("scan_proves_safe", False),
        )

    def to_db_row(self) -> tuple:
        """Serialize to tuple for SQLite INSERT/UPDATE."""
        return (
            self.edge_id,
            self.source_node_id,
            self.target_node_id,
            self.relation_type.value,
            json.dumps(self.properties, sort_keys=True),
            self.observed_at,
            self.confidence,
            0,  # scan_proves_safe
        )

    @classmethod
    def from_db_row(cls, row: tuple | sqlite3.Row) -> GraphEdgeRecord:
        """Deserialize from SQLite row tuple."""
        raw_props = row[4]
        props = json.loads(raw_props) if isinstance(raw_props, str) else raw_props
        return cls(
            edge_id=row[0],
            source_node_id=row[1],
            target_node_id=row[2],
            relation_type=TwinRelationType(row[3]),
            properties=props,
            observed_at=row[5],
            confidence=float(row[6]),
            scan_proves_safe=bool(row[7]),
        )

    def to_twin_relationship(self) -> TwinRelationship:
        """Convert record to an in-memory TwinRelationship."""
        return TwinRelationship(
            relation_id=self.edge_id,
            source_id=self.source_node_id,
            target_id=self.target_node_id,
            relation_type=self.relation_type,
            properties=self.properties,
            observed_at=self.observed_at,
            confidence=self.confidence,
        )

    @classmethod
    def from_twin_relationship(cls, rel: TwinRelationship) -> GraphEdgeRecord:
        """Create a persistence record from an in-memory TwinRelationship."""
        now_iso = datetime.now(timezone.utc).isoformat()
        return cls(
            edge_id=rel.relation_id,
            source_node_id=rel.source_id,
            target_node_id=rel.target_id,
            relation_type=rel.relation_type,
            properties=rel.properties,
            observed_at=rel.observed_at or now_iso,
            confidence=rel.confidence,
            scan_proves_safe=False,
        )


class GraphPersistenceManager:
    """Manages transactional persistence, querying, and full graph roundtrips for the Digital Twin."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ==========================================
    # Node CRUD Operations
    # ==========================================

    def save_node(self, node: GraphNodeRecord) -> None:
        """Insert or replace a graph node record."""
        sql = """
            INSERT OR REPLACE INTO graph_nodes (
                node_id, node_type, ownership, attributes_json,
                provenance_source, created_at, updated_at, is_stale,
                scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(sql, node.to_db_row())

        # Also maintain compatibility with legacy twin_entities table
        try:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO twin_entities (
                    entity_id, entity_type, ownership, observed_at, attributes_json
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (
                    node.node_id,
                    node.node_type.value,
                    node.ownership.value,
                    node.updated_at,
                    json.dumps(node.attributes, sort_keys=True),
                ),
            )
        except Exception:
            pass  # Non-blocking if table not present

    def get_node(self, node_id: str) -> Optional[GraphNodeRecord]:
        """Fetch a single graph node by node_id."""
        cursor = self.conn.execute(
            """
            SELECT node_id, node_type, ownership, attributes_json,
                   provenance_source, created_at, updated_at, is_stale,
                   scan_proves_safe
            FROM graph_nodes
            WHERE node_id = ?;
            """,
            (node_id,),
        )
        row = cursor.fetchone()
        return GraphNodeRecord.from_db_row(row) if row else None

    def list_nodes(
        self,
        node_type: Optional[TwinEntityType] = None,
        ownership: Optional[ComponentOwnership] = None,
        is_stale: Optional[bool] = None,
    ) -> List[GraphNodeRecord]:
        """Query graph nodes with optional filtering."""
        conditions = []
        params = []

        if node_type is not None:
            conditions.append("node_type = ?")
            params.append(node_type.value)

        if ownership is not None:
            conditions.append("ownership = ?")
            params.append(ownership.value)

        if is_stale is not None:
            conditions.append("is_stale = ?")
            params.append(1 if is_stale else 0)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT node_id, node_type, ownership, attributes_json,
                   provenance_source, created_at, updated_at, is_stale,
                   scan_proves_safe
            FROM graph_nodes
            {where_clause}
            ORDER BY created_at ASC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        return [GraphNodeRecord.from_db_row(row) for row in cursor.fetchall()]

    def delete_node(self, node_id: str) -> bool:
        """Delete a graph node and cascade incident edges."""
        cursor = self.conn.execute(
            "DELETE FROM graph_nodes WHERE node_id = ?;",
            (node_id,),
        )
        # Also clean up legacy twin_entities table
        try:
            self.conn.execute("DELETE FROM twin_entities WHERE entity_id = ?;", (node_id,))
        except Exception:
            pass
        return cursor.rowcount > 0

    # ==========================================
    # Edge CRUD Operations
    # ==========================================

    def save_edge(self, edge: GraphEdgeRecord) -> None:
        """Insert or replace a graph edge record."""
        sql = """
            INSERT OR REPLACE INTO graph_edges (
                edge_id, source_node_id, target_node_id, relation_type,
                properties_json, observed_at, confidence, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(sql, edge.to_db_row())

        # Also maintain compatibility with legacy twin_relationships table
        try:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO twin_relationships (
                    relationship_id, source_id, target_id, relation_type,
                    created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    edge.edge_id,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.relation_type.value,
                    edge.observed_at,
                    json.dumps(edge.properties, sort_keys=True),
                ),
            )
        except Exception:
            pass

    def get_edge(self, edge_id: str) -> Optional[GraphEdgeRecord]:
        """Fetch a single graph edge by edge_id."""
        cursor = self.conn.execute(
            """
            SELECT edge_id, source_node_id, target_node_id, relation_type,
                   properties_json, observed_at, confidence, scan_proves_safe
            FROM graph_edges
            WHERE edge_id = ?;
            """,
            (edge_id,),
        )
        row = cursor.fetchone()
        return GraphEdgeRecord.from_db_row(row) if row else None

    def list_edges(
        self,
        source_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
        relation_type: Optional[TwinRelationType] = None,
    ) -> List[GraphEdgeRecord]:
        """Query graph edges with optional filtering."""
        conditions = []
        params = []

        if source_node_id is not None:
            conditions.append("source_node_id = ?")
            params.append(source_node_id)

        if target_node_id is not None:
            conditions.append("target_node_id = ?")
            params.append(target_node_id)

        if relation_type is not None:
            conditions.append("relation_type = ?")
            params.append(relation_type.value)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT edge_id, source_node_id, target_node_id, relation_type,
                   properties_json, observed_at, confidence, scan_proves_safe
            FROM graph_edges
            {where_clause}
            ORDER BY observed_at ASC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        return [GraphEdgeRecord.from_db_row(row) for row in cursor.fetchall()]

    def delete_edge(self, edge_id: str) -> bool:
        """Delete a graph edge by edge_id."""
        cursor = self.conn.execute(
            "DELETE FROM graph_edges WHERE edge_id = ?;",
            (edge_id,),
        )
        try:
            self.conn.execute("DELETE FROM twin_relationships WHERE relationship_id = ?;", (edge_id,))
        except Exception:
            pass
        return cursor.rowcount > 0

    # ==========================================
    # Full Graph Persistence & Reconstruction
    # ==========================================

    def persist_graph(self, graph: DigitalTwinGraph) -> Tuple[int, int]:
        """Persist an entire in-memory DigitalTwinGraph into SQLite transactionally."""
        nodes_saved = 0
        edges_saved = 0

        # Validate graph integrity prior to persistence
        is_valid, violations = graph.validate_integrity()
        if not is_valid:
            raise ValueError(f"Cannot persist invalid graph: {'; '.join(violations)}")

        # 1. Save all nodes
        for node_type in TwinEntityType:
            for entity in graph.get_entities_by_type(node_type):
                node_rec = GraphNodeRecord.from_twin_entity(entity)
                self.save_node(node_rec)
                nodes_saved += 1

        # 2. Save all edges
        for rel_id, rel in graph._relationships.items():
            edge_rec = GraphEdgeRecord.from_twin_relationship(rel)
            self.save_edge(edge_rec)
            edges_saved += 1

        return nodes_saved, edges_saved

    def load_graph(self) -> DigitalTwinGraph:
        """Reconstruct an in-memory DigitalTwinGraph from SQLite."""
        graph = DigitalTwinGraph()

        # 1. Load all nodes
        nodes = self.list_nodes()
        for node_rec in nodes:
            graph.add_entity(node_rec.to_twin_entity())

        # 2. Load all edges
        edges = self.list_edges()
        for edge_rec in edges:
            graph.add_relationship(edge_rec.to_twin_relationship())

        return graph

    def count_graph_elements(self) -> Dict[str, int]:
        """Count total graph nodes and edges stored in database."""
        n_cnt = self.conn.execute("SELECT COUNT(*) FROM graph_nodes;").fetchone()[0]
        e_cnt = self.conn.execute("SELECT COUNT(*) FROM graph_edges;").fetchone()[0]
        return {
            "nodes": n_cnt,
            "edges": e_cnt,
            "total": n_cnt + e_cnt,
        }

    def clear_graph(self) -> Tuple[int, int]:
        """Transactionally clear all graph edges and nodes."""
        e_cnt = self.conn.execute("DELETE FROM graph_edges;").rowcount
        n_cnt = self.conn.execute("DELETE FROM graph_nodes;").rowcount
        try:
            self.conn.execute("DELETE FROM twin_relationships;")
            self.conn.execute("DELETE FROM twin_entities;")
        except Exception:
            pass
        return n_cnt, e_cnt
