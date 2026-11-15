"""Data models and validation for the Temporal Digital Twin entity-relationship graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.core.types import ComponentOwnership


class TwinEntityType(str, Enum):
    """Primary entity types represented in the digital twin."""

    HOST = "HOST"
    OS_KERNEL = "OS_KERNEL"
    HARDWARE_DEVICE = "HARDWARE_DEVICE"
    FILESYSTEM_NODE = "FILESYSTEM_NODE"
    PACKAGE_DEPENDENCY = "PACKAGE_DEPENDENCY"
    APPLICATION = "APPLICATION"
    PROCESS = "PROCESS"
    NETWORK_SOCKET = "NETWORK_SOCKET"
    SECURITY_POSTURE = "SECURITY_POSTURE"
    CONFIGURATION_SETTING = "CONFIGURATION_SETTING"


class TwinRelationType(str, Enum):
    """Directed edge types connecting entities in the digital twin."""

    CONTAINS = "CONTAINS"
    SPAWNED_BY = "SPAWNED_BY"
    DEPENDS_ON = "DEPENDS_ON"
    OWNS = "OWNS"
    ENFORCES_POLICY = "ENFORCES_POLICY"
    COMMUNICATES_VIA = "COMMUNICATES_VIA"
    WRITES_TO = "WRITES_TO"
    READS_FROM = "READS_FROM"
    AFFECTS = "AFFECTS"


@dataclass(frozen=True)
class TwinEntity:
    """Strongly typed representation of an observed host entity."""

    entity_id: str
    entity_type: TwinEntityType
    ownership: ComponentOwnership
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    provenance_source: str = ""
    is_stale: bool = False


@dataclass(frozen=True)
class TwinRelationship:
    """Strongly typed directed relationship (edge) between two digital twin entities."""

    relation_id: str
    source_id: str
    target_id: str
    relation_type: TwinRelationType
    properties: Dict[str, Any] = field(default_factory=dict)
    observed_at: str = ""
    confidence: float = 1.0


class TwinEntityValidator:
    """Validates digital twin entities and relationships against architectural invariants."""

    PROHIBITED_SENSITIVE_KEYS = {
        "password",
        "secret",
        "token",
        "private_key",
        "api_key",
        "credential",
    }

    @classmethod
    def validate_entity(cls, entity: TwinEntity) -> List[str]:
        """Validate an entity against mandatory ownership, provenance, and privacy invariants."""
        violations: List[str] = []

        if not entity.entity_id or not entity.entity_id.strip():
            violations.append("Entity ID cannot be empty.")

        if not isinstance(entity.entity_type, TwinEntityType):
            violations.append(f"Invalid entity type: {entity.entity_type}")

        if not isinstance(entity.ownership, ComponentOwnership):
            violations.append(f"Invalid component ownership: {entity.ownership}")

        if not entity.provenance_source or not entity.provenance_source.strip():
            violations.append("Provenance source cannot be empty (Invariant 3).")

        # Privacy checks (Invariant 4)
        for key in entity.attributes:
            key_lower = key.lower()
            if any(sens in key_lower for sens in cls.PROHIBITED_SENSITIVE_KEYS):
                violations.append(
                    f"Privacy Violation: Attribute key '{key}' contains sensitive credential patterns."
                )

        return violations

    @classmethod
    def validate_relationship(cls, relation: TwinRelationship) -> List[str]:
        """Validate a relationship schema."""
        violations: List[str] = []

        if not relation.relation_id or not relation.relation_id.strip():
            violations.append("Relation ID cannot be empty.")

        if not relation.source_id or not relation.source_id.strip():
            violations.append("Source ID cannot be empty.")

        if not relation.target_id or not relation.target_id.strip():
            violations.append("Target ID cannot be empty.")

        if not isinstance(relation.relation_type, TwinRelationType):
            violations.append(f"Invalid relation type: {relation.relation_type}")

        if relation.confidence < 0.0 or relation.confidence > 1.0:
            violations.append(f"Confidence score {relation.confidence} must be between 0.0 and 1.0.")

        return violations
