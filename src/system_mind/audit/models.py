"""Data models, schemas, and enums for Cryptographic Audit Events and Data Retention."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.core.types import ComponentOwnership
from system_mind.governance.models import IdentityType


class AuditEventCategory(str, Enum):
    """Categorization of audit events."""

    POLICY_EVALUATION = "POLICY_EVALUATION"
    BROKER_DISPATCH = "BROKER_DISPATCH"
    STATE_MUTATION = "STATE_MUTATION"
    ROLLBACK_EXECUTION = "ROLLBACK_EXECUTION"
    APPROVAL_CONFIRMATION = "APPROVAL_CONFIRMATION"
    SECURITY_ALERT = "SECURITY_ALERT"


class AuditEventSeverity(str, Enum):
    """Severity classification of audit events."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL_SECURITY = "CRITICAL_SECURITY"


class RetentionClass(str, Enum):
    """Storage lifecycle classes governing data retention."""

    CRITICAL_SECURITY = "CRITICAL_SECURITY"
    SYSTEM_MUTATION = "SYSTEM_MUTATION"
    POLICY_DECISION = "POLICY_DECISION"
    DIAGNOSTIC_TELEMETRY = "DIAGNOSTIC_TELEMETRY"
    EPHEMERAL_TRACE = "EPHEMERAL_TRACE"


@dataclass
class AuditEvent:
    """An immutable, cryptographic audit record in the SYSTEM MIND X ledger."""

    event_id: str
    sequence_number: int
    timestamp_iso: str
    event_category: AuditEventCategory
    severity: AuditEventSeverity
    retention_class: RetentionClass
    actor_principal: str
    identity_type: IdentityType
    target_component: str
    target_ownership: ComponentOwnership
    capability_id: str
    contract_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    payload_hash: str = field(default="", init=False)
    prev_event_hash: str = ""
    event_hash: str = field(default="", init=False)

    def compute_hashes(self, prev_hash: str) -> None:
        """Compute canonical payload hash and cryptographic chain event hash."""
        # Canonical JSON payload hash
        canonical_json = json.dumps(self.payload, sort_keys=True, separators=(",", ":"))
        self.payload_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        self.prev_event_hash = prev_hash

        # Cryptographic chain hash binding header fields, prev_hash, and payload_hash
        header = f"{self.event_id}:{self.sequence_number}:{self.timestamp_iso}:{self.event_category.value}:{self.prev_event_hash}:{self.payload_hash}"
        self.event_hash = hashlib.sha256(header.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RetentionPolicySpecification:
    """Formal lifecycle definition for a specific retention tier."""

    retention_class: RetentionClass
    ttl_seconds: int
    is_immutable: bool
    description: str


@dataclass(frozen=True)
class ChainCheckpointRecord:
    """Cryptographic anchor sealing the audit chain when older expired records are purged."""

    checkpoint_id: str
    timestamp_iso: str
    pruned_up_to_sequence: int
    anchor_event_hash: str
    remaining_count: int


@dataclass
class AuditTrailVerification:
    """Result of full cryptographic verification of the audit ledger."""

    is_valid: bool
    verified_event_count: int
    tampered_event_ids: List[str] = field(default_factory=list)
    discrepancies: List[str] = field(default_factory=list)
