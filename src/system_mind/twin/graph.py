"""In-memory graph store and query engine for the Temporal Digital Twin."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from system_mind.core.types import ComponentOwnership
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinEntityValidator,
    TwinRelationship,
    TwinRelationType,
)


class DigitalTwinGraph:
    """In-memory directed property graph representing the host digital twin state."""

    def __init__(self) -> None:
        self._entities: Dict[str, TwinEntity] = {}
        self._relationships: Dict[str, TwinRelationship] = {}
        self._outgoing_adj: Dict[str, List[str]] = {}
        self._incoming_adj: Dict[str, List[str]] = {}
        self._type_index: Dict[TwinEntityType, Set[str]] = {t: set() for t in TwinEntityType}
        self._ownership_index: Dict[ComponentOwnership, Set[str]] = {o: set() for o in ComponentOwnership}

    @property
    def entity_count(self) -> int:
        """Return the number of entities in the graph."""
        return len(self._entities)

    @property
    def relationship_count(self) -> int:
        """Return the number of relationships in the graph."""
        return len(self._relationships)

    def add_entity(self, entity: TwinEntity) -> None:
        """Add an entity to the digital twin graph after validating invariants."""
        violations = TwinEntityValidator.validate_entity(entity)
        if violations:
            raise ValueError(f"Entity validation failed: {'; '.join(violations)}")

        # If entity already exists, remove from previous index entries
        if entity.entity_id in self._entities:
            old_entity = self._entities[entity.entity_id]
            self._type_index[old_entity.entity_type].discard(entity.entity_id)
            self._ownership_index[old_entity.ownership].discard(entity.entity_id)

        self._entities[entity.entity_id] = entity
        self._type_index[entity.entity_type].add(entity.entity_id)
        self._ownership_index[entity.ownership].add(entity.entity_id)

        if entity.entity_id not in self._outgoing_adj:
            self._outgoing_adj[entity.entity_id] = []
        if entity.entity_id not in self._incoming_adj:
            self._incoming_adj[entity.entity_id] = []

    def get_entity(self, entity_id: str) -> Optional[TwinEntity]:
        """Retrieve an entity by its unique ID."""
        return self._entities.get(entity_id)

    def update_entity_attributes(
        self,
        entity_id: str,
        new_attributes: Dict[str, Any],
        updated_at: str = "",
        is_stale: bool = False,
    ) -> TwinEntity:
        """Update the attributes of an existing entity."""
        if entity_id not in self._entities:
            raise KeyError(f"Entity '{entity_id}' not found in digital twin.")

        current = self._entities[entity_id]
        merged_attrs = dict(current.attributes)
        merged_attrs.update(new_attributes)

        updated_entity = TwinEntity(
            entity_id=current.entity_id,
            entity_type=current.entity_type,
            ownership=current.ownership,
            attributes=merged_attrs,
            created_at=current.created_at,
            updated_at=updated_at or current.updated_at,
            provenance_source=current.provenance_source,
            is_stale=is_stale,
        )

        violations = TwinEntityValidator.validate_entity(updated_entity)
        if violations:
            raise ValueError(f"Updated entity validation failed: {'; '.join(violations)}")

        self._entities[entity_id] = updated_entity
        return updated_entity

    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity and cascade removal of all incident relationships."""
        if entity_id not in self._entities:
            return False

        entity = self._entities[entity_id]
        self._type_index[entity.entity_type].discard(entity_id)
        self._ownership_index[entity.ownership].discard(entity_id)
        del self._entities[entity_id]

        # Cascade removal of incident relationships
        outgoing_rels = list(self._outgoing_adj.get(entity_id, []))
        for rel_id in outgoing_rels:
            self.remove_relationship(rel_id)

        incoming_rels = list(self._incoming_adj.get(entity_id, []))
        for rel_id in incoming_rels:
            self.remove_relationship(rel_id)

        self._outgoing_adj.pop(entity_id, None)
        self._incoming_adj.pop(entity_id, None)
        return True

    def add_relationship(self, relation: TwinRelationship) -> None:
        """Add a directed relationship between two existing entities."""
        violations = TwinEntityValidator.validate_relationship(relation)
        if violations:
            raise ValueError(f"Relationship validation failed: {'; '.join(violations)}")

        # Referential integrity check (Invariant 2)
        if relation.source_id not in self._entities:
            raise KeyError(f"Source entity '{relation.source_id}' does not exist in the digital twin.")
        if relation.target_id not in self._entities:
            raise KeyError(f"Target entity '{relation.target_id}' does not exist in the digital twin.")

        self._relationships[relation.relation_id] = relation
        self._outgoing_adj[relation.source_id].append(relation.relation_id)
        self._incoming_adj[relation.target_id].append(relation.relation_id)

    def get_relationship(self, relation_id: str) -> Optional[TwinRelationship]:
        """Retrieve a relationship by ID."""
        return self._relationships.get(relation_id)

    def remove_relationship(self, relation_id: str) -> bool:
        """Remove a relationship by ID."""
        if relation_id not in self._relationships:
            return False

        rel = self._relationships[relation_id]
        if rel.source_id in self._outgoing_adj:
            self._outgoing_adj[rel.source_id] = [
                rid for rid in self._outgoing_adj[rel.source_id] if rid != relation_id
            ]
        if rel.target_id in self._incoming_adj:
            self._incoming_adj[rel.target_id] = [
                rid for rid in self._incoming_adj[rel.target_id] if rid != relation_id
            ]

        del self._relationships[relation_id]
        return True

    def get_entities_by_type(self, entity_type: TwinEntityType) -> List[TwinEntity]:
        """Retrieve all entities of a given entity type."""
        entity_ids = self._type_index.get(entity_type, set())
        return [self._entities[eid] for eid in entity_ids if eid in self._entities]

    def get_entities_by_ownership(self, ownership: ComponentOwnership) -> List[TwinEntity]:
        """Retrieve all entities with a given component ownership."""
        entity_ids = self._ownership_index.get(ownership, set())
        return [self._entities[eid] for eid in entity_ids if eid in self._entities]

    def get_outgoing_relationships(
        self,
        entity_id: str,
        relation_type: Optional[TwinRelationType] = None,
    ) -> List[TwinRelationship]:
        """Retrieve outgoing relationships from an entity, optionally filtered by type."""
        rel_ids = self._outgoing_adj.get(entity_id, [])
        rels = [self._relationships[rid] for rid in rel_ids if rid in self._relationships]
        if relation_type is not None:
            rels = [r for r in rels if r.relation_type == relation_type]
        return rels

    def get_incoming_relationships(
        self,
        entity_id: str,
        relation_type: Optional[TwinRelationType] = None,
    ) -> List[TwinRelationship]:
        """Retrieve incoming relationships to an entity, optionally filtered by type."""
        rel_ids = self._incoming_adj.get(entity_id, [])
        rels = [self._relationships[rid] for rid in rel_ids if rid in self._relationships]
        if relation_type is not None:
            rels = [r for r in rels if r.relation_type == relation_type]
        return rels

    def get_process_ancestors(self, process_entity_id: str, max_depth: int = 10) -> List[TwinEntity]:
        """Traverse process hierarchy upward via SPAWNED_BY edges."""
        ancestors: List[TwinEntity] = []
        current_id = process_entity_id
        depth = 0

        while depth < max_depth:
            # Outgoing SPAWNED_BY edges: Process A SPAWNED_BY Process B
            spawned_by_edges = self.get_outgoing_relationships(
                current_id, relation_type=TwinRelationType.SPAWNED_BY
            )
            if not spawned_by_edges:
                break

            parent_id = spawned_by_edges[0].target_id
            parent_entity = self.get_entity(parent_id)
            if parent_entity is None:
                break

            ancestors.append(parent_entity)
            current_id = parent_id
            depth += 1

        return ancestors

    def get_dependencies(self, entity_id: str, max_depth: int = 5) -> List[TwinEntity]:
        """Traverse functional dependency graph outward via DEPENDS_ON edges."""
        visited: Set[str] = set()
        dependencies: List[TwinEntity] = []
        queue: List[Tuple[str, int]] = [(entity_id, 0)]

        while queue:
            curr_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            deps = self.get_outgoing_relationships(curr_id, relation_type=TwinRelationType.DEPENDS_ON)
            for d in deps:
                target_id = d.target_id
                if target_id not in visited and target_id in self._entities:
                    visited.add(target_id)
                    dep_entity = self._entities[target_id]
                    dependencies.append(dep_entity)
                    queue.append((target_id, depth + 1))

        return dependencies

    def validate_integrity(self) -> Tuple[bool, List[str]]:
        """Validate entire graph referential integrity and invariant adherence."""
        violations: List[str] = []

        # 1. Check all entities satisfy validation rules
        for entity in self._entities.values():
            e_violations = TwinEntityValidator.validate_entity(entity)
            violations.extend(e_violations)

        # 2. Check all relationships connect existing entities
        for rel in self._relationships.values():
            r_violations = TwinEntityValidator.validate_relationship(rel)
            violations.extend(r_violations)

            if rel.source_id not in self._entities:
                violations.append(
                    f"Dangling Relationship: Source '{rel.source_id}' does not exist in graph."
                )
            if rel.target_id not in self._entities:
                violations.append(
                    f"Dangling Relationship: Target '{rel.target_id}' does not exist in graph."
                )

        is_valid = (len(violations) == 0)
        return is_valid, violations

    def clear(self) -> None:
        """Clear all entities and relationships."""
        self._entities.clear()
        self._relationships.clear()
        self._outgoing_adj.clear()
        self._incoming_adj.clear()
        for t in TwinEntityType:
            self._type_index[t].clear()
        for o in ComponentOwnership:
            self._ownership_index[o].clear()
