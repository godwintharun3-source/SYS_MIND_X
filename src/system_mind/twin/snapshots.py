"""Digital twin point-in-time state snapshots, deterministic digests, and topology comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import uuid

from system_mind.core.types import ComponentOwnership
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinRelationship,
    TwinRelationType,
)


class SnapshotTriggerReason(str, Enum):
    """Causal triggers that initiated a point-in-time state snapshot capture."""

    TELEMETRY_SWEEP = "TELEMETRY_SWEEP"
    PRE_MUTATION = "PRE_MUTATION"
    POST_MUTATION = "POST_MUTATION"
    SCHEDULED = "SCHEDULED"
    MANUAL = "MANUAL"
    ALERT_TRIGGERED = "ALERT_TRIGGERED"


def entity_to_canonical_dict(entity: TwinEntity) -> Dict[str, Any]:
    """Serializes a TwinEntity into a deterministic JSON-compatible dictionary."""
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type),
        "ownership": entity.ownership.value if hasattr(entity.ownership, "value") else str(entity.ownership),
        "attributes": dict(sorted(entity.attributes.items())),
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
        "provenance_source": entity.provenance_source,
        "is_stale": entity.is_stale,
    }


def relationship_to_canonical_dict(rel: TwinRelationship) -> Dict[str, Any]:
    """Serializes a TwinRelationship into a deterministic JSON-compatible dictionary."""
    return {
        "relation_id": rel.relation_id,
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "relation_type": rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type),
        "properties": dict(sorted(rel.properties.items())),
        "observed_at": rel.observed_at,
        "confidence": float(rel.confidence),
    }


def compute_graph_state_digest(
    entities: Sequence[TwinEntity],
    relationships: Sequence[TwinRelationship],
) -> str:
    """Computes a deterministic SHA-256 fingerprint over sorted canonical entities and edges."""
    canonical_payload = {
        "entities": [entity_to_canonical_dict(e) for e in sorted(entities, key=lambda x: x.entity_id)],
        "relationships": [
            relationship_to_canonical_dict(r) for r in sorted(relationships, key=lambda x: x.relation_id)
        ],
    }
    raw = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EntityAttributeDiff:
    """Captures granular attribute and staleness mutations for an entity between two snapshots."""

    entity_id: str
    entity_type: str
    ownership: str
    added_or_modified_attributes: Dict[str, Any]
    removed_attributes: List[str]
    is_stale_changed: bool = False
    old_is_stale: bool = False
    new_is_stale: bool = False


@dataclass(frozen=True)
class DigitalTwinSnapshotDiff:
    """Granular comparison outcome between two digital twin state snapshots."""

    from_snapshot_id: str
    to_snapshot_id: str
    device_id: str
    from_epoch_ms: int
    to_epoch_ms: int
    time_delta_seconds: float
    added_entities: Tuple[TwinEntity, ...]
    removed_entities: Tuple[TwinEntity, ...]
    modified_entities: Tuple[EntityAttributeDiff, ...]
    added_relationships: Tuple[TwinRelationship, ...]
    removed_relationships: Tuple[TwinRelationship, ...]
    ownership_changes: Dict[str, int]
    user_managed_affected: bool
    is_identical: bool
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces Charter Invariant SC-03: scan_proves_safe is NEVER True."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")

    def summary(self) -> str:
        """Human-readable summary of graph mutations between snapshots."""
        lines = [
            f"Snapshot Diff: {self.from_snapshot_id[:8]} -> {self.to_snapshot_id[:8]} "
            f"({self.time_delta_seconds:.2f}s elapsed)",
            f"  Entities: +{len(self.added_entities)} added, -{len(self.removed_entities)} removed, "
            f"~{len(self.modified_entities)} modified",
            f"  Relationships: +{len(self.added_relationships)} added, -{len(self.removed_relationships)} removed",
            f"  User Managed Affected: {'YES (WARNING)' if self.user_managed_affected else 'NO (Safe)'}",
            f"  Identical State: {'YES' if self.is_identical else 'NO'}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes diff to a canonical JSON-compatible dictionary."""
        return {
            "from_snapshot_id": self.from_snapshot_id,
            "to_snapshot_id": self.to_snapshot_id,
            "device_id": self.device_id,
            "from_epoch_ms": self.from_epoch_ms,
            "to_epoch_ms": self.to_epoch_ms,
            "time_delta_seconds": self.time_delta_seconds,
            "added_entity_ids": [e.entity_id for e in self.added_entities],
            "removed_entity_ids": [e.entity_id for e in self.removed_entities],
            "modified_entity_ids": [m.entity_id for m in self.modified_entities],
            "added_relationship_ids": [r.relation_id for r in self.added_relationships],
            "removed_relationship_ids": [r.relation_id for r in self.removed_relationships],
            "ownership_changes": self.ownership_changes,
            "user_managed_affected": self.user_managed_affected,
            "is_identical": self.is_identical,
            "scan_proves_safe": self.scan_proves_safe,
        }


@dataclass(frozen=True)
class DigitalTwinSnapshot:
    """Point-in-time coherent state photograph of the digital twin property graph."""

    snapshot_id: str
    device_id: str
    captured_at_iso: str
    captured_at_epoch_ms: int
    sequence_number: int
    trigger_reason: str
    entity_count: int
    relationship_count: int
    state_digest: str
    entities: Tuple[TwinEntity, ...]
    relationships: Tuple[TwinRelationship, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces schema consistency and Charter Invariant SC-03."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")
        if self.entity_count != len(self.entities):
            raise ValueError(
                f"Entity Count Mismatch: entity_count={self.entity_count} does not match len(entities)={len(self.entities)}"
            )
        if self.relationship_count != len(self.relationships):
            raise ValueError(
                f"Relationship Count Mismatch: relationship_count={self.relationship_count} does not match len(relationships)={len(self.relationships)}"
            )

    def to_sqlite_params(self) -> Tuple[Any, ...]:
        """Serializes snapshot fields to positional parameters for SQLite insertion."""
        entities_json = json.dumps(
            [entity_to_canonical_dict(e) for e in self.entities],
            sort_keys=True,
            separators=(",", ":"),
        )
        relationships_json = json.dumps(
            [relationship_to_canonical_dict(r) for r in self.relationships],
            sort_keys=True,
            separators=(",", ":"),
        )
        metadata_json = json.dumps(self.metadata, sort_keys=True, separators=(",", ":"))

        return (
            self.snapshot_id,
            self.device_id,
            self.captured_at_iso,
            self.captured_at_epoch_ms,
            self.sequence_number,
            self.trigger_reason,
            self.entity_count,
            self.relationship_count,
            self.state_digest,
            entities_json,
            relationships_json,
            metadata_json,
            0,  # scan_proves_safe is always 0
        )

    @classmethod
    def from_sqlite_row(cls, row: Tuple[Any, ...] | sqlite3.Row) -> DigitalTwinSnapshot:
        """Constructs a DigitalTwinSnapshot from a raw SQLite query row."""
        raw_entities = json.loads(row[9])
        raw_relationships = json.loads(row[10])
        metadata = json.loads(row[11]) if row[11] else {}

        entities = tuple(
            TwinEntity(
                entity_id=e["entity_id"],
                entity_type=TwinEntityType(e["entity_type"]),
                ownership=ComponentOwnership(e["ownership"]),
                attributes=e.get("attributes", {}),
                created_at=e.get("created_at", ""),
                updated_at=e.get("updated_at", ""),
                provenance_source=e.get("provenance_source", ""),
                is_stale=bool(e.get("is_stale", False)),
            )
            for e in raw_entities
        )

        relationships = tuple(
            TwinRelationship(
                relation_id=r["relation_id"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                relation_type=TwinRelationType(r["relation_type"]),
                properties=r.get("properties", {}),
                observed_at=r.get("observed_at", ""),
                confidence=float(r.get("confidence", 1.0)),
            )
            for r in raw_relationships
        )

        return cls(
            snapshot_id=row[0],
            device_id=row[1],
            captured_at_iso=row[2],
            captured_at_epoch_ms=row[3],
            sequence_number=row[4],
            trigger_reason=row[5],
            entity_count=row[6],
            relationship_count=row[7],
            state_digest=row[8],
            entities=entities,
            relationships=relationships,
            metadata=metadata,
            scan_proves_safe=bool(row[12]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes snapshot to a canonical JSON-compatible dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "device_id": self.device_id,
            "captured_at_iso": self.captured_at_iso,
            "captured_at_epoch_ms": self.captured_at_epoch_ms,
            "sequence_number": self.sequence_number,
            "trigger_reason": self.trigger_reason,
            "entity_count": self.entity_count,
            "relationship_count": self.relationship_count,
            "state_digest": self.state_digest,
            "entities": [entity_to_canonical_dict(e) for e in self.entities],
            "relationships": [relationship_to_canonical_dict(r) for r in self.relationships],
            "metadata": self.metadata,
            "scan_proves_safe": self.scan_proves_safe,
        }


def compare_snapshots(
    from_snapshot: DigitalTwinSnapshot,
    to_snapshot: DigitalTwinSnapshot,
) -> DigitalTwinSnapshotDiff:
    """Compares two snapshots and computes the exact structural diff across entities and edges."""
    time_delta = max(0.0, (to_snapshot.captured_at_epoch_ms - from_snapshot.captured_at_epoch_ms) / 1000.0)

    # 1. Digest equivalence check (O(1) identical check)
    if from_snapshot.state_digest == to_snapshot.state_digest:
        return DigitalTwinSnapshotDiff(
            from_snapshot_id=from_snapshot.snapshot_id,
            to_snapshot_id=to_snapshot.snapshot_id,
            device_id=to_snapshot.device_id,
            from_epoch_ms=from_snapshot.captured_at_epoch_ms,
            to_epoch_ms=to_snapshot.captured_at_epoch_ms,
            time_delta_seconds=time_delta,
            added_entities=(),
            removed_entities=(),
            modified_entities=(),
            added_relationships=(),
            removed_relationships=(),
            ownership_changes={"SYSTEM_MANAGED": 0, "VENDOR_MANAGED": 0, "USER_MANAGED": 0},
            user_managed_affected=False,
            is_identical=True,
            scan_proves_safe=False,
        )

    # 2. Entity comparison
    from_ent_map: Dict[str, TwinEntity] = {e.entity_id: e for e in from_snapshot.entities}
    to_ent_map: Dict[str, TwinEntity] = {e.entity_id: e for e in to_snapshot.entities}

    added_ids = set(to_ent_map.keys()) - set(from_ent_map.keys())
    removed_ids = set(from_ent_map.keys()) - set(to_ent_map.keys())
    common_ids = set(from_ent_map.keys()) & set(to_ent_map.keys())

    added_entities = tuple(to_ent_map[eid] for eid in sorted(added_ids))
    removed_entities = tuple(from_ent_map[eid] for eid in sorted(removed_ids))

    modified_entities_list: List[EntityAttributeDiff] = []
    ownership_changes = {"SYSTEM_MANAGED": 0, "VENDOR_MANAGED": 0, "USER_MANAGED": 0}
    user_managed_affected = False

    for e in added_entities:
        ownership_changes[e.ownership.value] = ownership_changes.get(e.ownership.value, 0) + 1
        if e.ownership == ComponentOwnership.USER_MANAGED:
            user_managed_affected = True

    for e in removed_entities:
        ownership_changes[e.ownership.value] = ownership_changes.get(e.ownership.value, 0) + 1
        if e.ownership == ComponentOwnership.USER_MANAGED:
            user_managed_affected = True

    for eid in sorted(common_ids):
        old_ent = from_ent_map[eid]
        new_ent = to_ent_map[eid]

        added_or_mod: Dict[str, Any] = {}
        removed_attrs: List[str] = []

        for k, v in new_ent.attributes.items():
            if k not in old_ent.attributes or old_ent.attributes[k] != v:
                added_or_mod[k] = v

        for k in old_ent.attributes:
            if k not in new_ent.attributes:
                removed_attrs.append(k)

        is_stale_changed = old_ent.is_stale != new_ent.is_stale

        if added_or_mod or removed_attrs or is_stale_changed:
            modified_entities_list.append(
                EntityAttributeDiff(
                    entity_id=eid,
                    entity_type=new_ent.entity_type.value,
                    ownership=new_ent.ownership.value,
                    added_or_modified_attributes=added_or_mod,
                    removed_attributes=removed_attrs,
                    is_stale_changed=is_stale_changed,
                    old_is_stale=old_ent.is_stale,
                    new_is_stale=new_ent.is_stale,
                )
            )
            ownership_changes[new_ent.ownership.value] = ownership_changes.get(new_ent.ownership.value, 0) + 1
            if new_ent.ownership == ComponentOwnership.USER_MANAGED:
                user_managed_affected = True

    # 3. Relationship comparison
    from_rel_map: Dict[str, TwinRelationship] = {r.relation_id: r for r in from_snapshot.relationships}
    to_rel_map: Dict[str, TwinRelationship] = {r.relation_id: r for r in to_snapshot.relationships}

    added_rel_ids = set(to_rel_map.keys()) - set(from_rel_map.keys())
    removed_rel_ids = set(from_rel_map.keys()) - set(to_rel_map.keys())

    added_relationships = tuple(to_rel_map[rid] for rid in sorted(added_rel_ids))
    removed_relationships = tuple(from_rel_map[rid] for rid in sorted(removed_rel_ids))

    is_identical = (
        len(added_entities) == 0
        and len(removed_entities) == 0
        and len(modified_entities_list) == 0
        and len(added_relationships) == 0
        and len(removed_relationships) == 0
    )

    return DigitalTwinSnapshotDiff(
        from_snapshot_id=from_snapshot.snapshot_id,
        to_snapshot_id=to_snapshot.snapshot_id,
        device_id=to_snapshot.device_id,
        from_epoch_ms=from_snapshot.captured_at_epoch_ms,
        to_epoch_ms=to_snapshot.captured_at_epoch_ms,
        time_delta_seconds=time_delta,
        added_entities=added_entities,
        removed_entities=removed_entities,
        modified_entities=tuple(modified_entities_list),
        added_relationships=added_relationships,
        removed_relationships=removed_relationships,
        ownership_changes=ownership_changes,
        user_managed_affected=user_managed_affected,
        is_identical=is_identical,
        scan_proves_safe=False,
    )


class DigitalTwinSnapshotManager:
    """Manages persistent state snapshots and comparative diffing for the digital twin."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the manager with an active SQLite database connection."""
        self.conn = conn

    def capture_snapshot(
        self,
        graph: DigitalTwinGraph,
        device_id: str,
        trigger_reason: str = SnapshotTriggerReason.TELEMETRY_SWEEP.value,
        metadata: Optional[Dict[str, Any]] = None,
        captured_at_iso: Optional[str] = None,
        captured_at_epoch_ms: Optional[int] = None,
    ) -> DigitalTwinSnapshot:
        """Captures a point-in-time coherent snapshot of the in-memory DigitalTwinGraph and persists it."""
        entities = tuple(graph._entities.values())
        relationships = tuple(graph._relationships.values())

        now_epoch_ms = captured_at_epoch_ms or int(time.time() * 1000)
        now_iso = captured_at_iso or datetime.fromtimestamp(now_epoch_ms / 1000.0, tz=timezone.utc).isoformat()

        # Monotonic sequence numbering per device
        cursor = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_number), 0) FROM digital_twin_snapshots WHERE device_id = ?;",
            (device_id,),
        )
        seq_num = cursor.fetchone()[0] + 1

        state_digest = compute_graph_state_digest(entities, relationships)
        snapshot_id = f"snap-{device_id[:8]}-{seq_num:06d}-{uuid.uuid4().hex[:8]}"

        snapshot = DigitalTwinSnapshot(
            snapshot_id=snapshot_id,
            device_id=device_id,
            captured_at_iso=now_iso,
            captured_at_epoch_ms=now_epoch_ms,
            sequence_number=seq_num,
            trigger_reason=trigger_reason,
            entity_count=len(entities),
            relationship_count=len(relationships),
            state_digest=state_digest,
            entities=entities,
            relationships=relationships,
            metadata=metadata or {},
            scan_proves_safe=False,
        )

        insert_sql = """
            INSERT INTO digital_twin_snapshots (
                snapshot_id, device_id, captured_at_iso, captured_at_epoch_ms,
                sequence_number, trigger_reason, entity_count, relationship_count,
                state_digest, entities_json, relationships_json, metadata_json,
                scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(insert_sql, snapshot.to_sqlite_params())
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[DigitalTwinSnapshot]:
        """Retrieves a single snapshot by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM digital_twin_snapshots WHERE snapshot_id = ?;",
            (snapshot_id,),
        )
        row = cursor.fetchone()
        return DigitalTwinSnapshot.from_sqlite_row(row) if row else None

    def get_latest_snapshot(self, device_id: Optional[str] = None) -> Optional[DigitalTwinSnapshot]:
        """Retrieves the latest chronological snapshot for a device."""
        if device_id:
            query = """
                SELECT * FROM digital_twin_snapshots
                WHERE device_id = ?
                ORDER BY sequence_number DESC
                LIMIT 1;
            """
            cursor = self.conn.execute(query, (device_id,))
        else:
            query = """
                SELECT * FROM digital_twin_snapshots
                ORDER BY captured_at_epoch_ms DESC
                LIMIT 1;
            """
            cursor = self.conn.execute(query)

        row = cursor.fetchone()
        return DigitalTwinSnapshot.from_sqlite_row(row) if row else None

    def list_snapshots(
        self,
        device_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[DigitalTwinSnapshot]:
        """Lists snapshots ordered in reverse-chronological order."""
        if device_id:
            query = """
                SELECT * FROM digital_twin_snapshots
                WHERE device_id = ?
                ORDER BY sequence_number DESC
                LIMIT ?;
            """
            cursor = self.conn.execute(query, (device_id, limit))
        else:
            query = """
                SELECT * FROM digital_twin_snapshots
                ORDER BY captured_at_epoch_ms DESC
                LIMIT ?;
            """
            cursor = self.conn.execute(query, (limit,))

        return [DigitalTwinSnapshot.from_sqlite_row(r) for r in cursor.fetchall()]

    def reconstruct_graph(self, snapshot_id: str) -> DigitalTwinGraph:
        """Losslessly reconstructs an in-memory DigitalTwinGraph from a persistent snapshot."""
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            raise KeyError(f"Snapshot '{snapshot_id}' not found.")

        graph = DigitalTwinGraph()
        for entity in snapshot.entities:
            graph.add_entity(entity)

        for rel in snapshot.relationships:
            graph.add_relationship(rel)

        return graph

    def compare_snapshots_by_id(
        self,
        from_snapshot_id: str,
        to_snapshot_id: str,
    ) -> DigitalTwinSnapshotDiff:
        """Retrieves and compares two snapshots by their IDs."""
        snap_a = self.get_snapshot(from_snapshot_id)
        if snap_a is None:
            raise KeyError(f"Source snapshot '{from_snapshot_id}' not found.")

        snap_b = self.get_snapshot(to_snapshot_id)
        if snap_b is None:
            raise KeyError(f"Target snapshot '{to_snapshot_id}' not found.")

        return compare_snapshots(snap_a, snap_b)
