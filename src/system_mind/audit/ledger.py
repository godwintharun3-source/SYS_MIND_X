"""Immutable cryptographic audit ledger with automated secret redaction and retention management."""

from __future__ import annotations

import datetime
import json
import re
from typing import Any, Dict, List, Optional

from system_mind.audit.models import (
    AuditEvent,
    AuditEventCategory,
    AuditEventSeverity,
    AuditTrailVerification,
    ChainCheckpointRecord,
    RetentionClass,
    RetentionPolicySpecification,
)
from system_mind.core.types import ComponentOwnership
from system_mind.governance.models import IdentityType


class SecretRedactor:
    """Recursively scans data payloads and redacts credentials, keys, and tokens."""

    REDACTION_MARKER = "[REDACTED_SECRET]"
    _KEY_PATTERN = re.compile(
        r"(?i)(password|passwd|token|secret|api_?key|credential|private_?key|auth|bearer|cookie|session_?id)"
    )
    _PEM_PATTERN = re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----")

    @classmethod
    def redact(cls, data: Any) -> Any:
        """Deep recursive sanitization of nested dictionaries, lists, and strings."""
        if isinstance(data, dict):
            sanitized: Dict[str, Any] = {}
            for k, v in data.items():
                if cls._KEY_PATTERN.search(str(k)):
                    sanitized[k] = cls.REDACTION_MARKER
                else:
                    sanitized[k] = cls.redact(v)
            return sanitized

        if isinstance(data, list):
            return [cls.redact(item) for item in data]

        if isinstance(data, str):
            if cls._PEM_PATTERN.search(data) or data.startswith("Bearer "):
                return cls.REDACTION_MARKER
            return data

        return data


class ImmutableAuditLedger:
    """Append-only cryptographic audit ledger enforcing hash-chain integrity and retention rules."""

    GENESIS_PREV_HASH = "0" * 64

    # Default retention policy specifications across the 5 tiers
    RETENTION_SPECIFICATIONS: Dict[RetentionClass, RetentionPolicySpecification] = {
        RetentionClass.CRITICAL_SECURITY: RetentionPolicySpecification(
            retention_class=RetentionClass.CRITICAL_SECURITY,
            ttl_seconds=365 * 86400,  # 365 days
            is_immutable=True,
            description="Security alerts, invariant breaches, and critical system mutations. Immutable; zero automated pruning.",
        ),
        RetentionClass.SYSTEM_MUTATION: RetentionPolicySpecification(
            retention_class=RetentionClass.SYSTEM_MUTATION,
            ttl_seconds=90 * 86400,  # 90 days
            is_immutable=False,
            description="OS patching, daemon maintenance, and system configuration updates.",
        ),
        RetentionClass.POLICY_DECISION: RetentionPolicySpecification(
            retention_class=RetentionClass.POLICY_DECISION,
            ttl_seconds=30 * 86400,  # 30 days
            is_immutable=False,
            description="Governance evaluations, approval verifications, and policy checks.",
        ),
        RetentionClass.DIAGNOSTIC_TELEMETRY: RetentionPolicySpecification(
            retention_class=RetentionClass.DIAGNOSTIC_TELEMETRY,
            ttl_seconds=14 * 86400,  # 14 days
            is_immutable=False,
            description="Periodic sensor telemetry, CPU metrics, and frontmost window focus shifts.",
        ),
        RetentionClass.EPHEMERAL_TRACE: RetentionPolicySpecification(
            retention_class=RetentionClass.EPHEMERAL_TRACE,
            ttl_seconds=2 * 86400,  # 48 hours
            is_immutable=False,
            description="Micro-VM sandbox execution traces and ephemeral diagnostic dumps.",
        ),
    }

    def __init__(self) -> None:
        self._events: List[AuditEvent] = []
        self._checkpoints: List[ChainCheckpointRecord] = []
        self._next_sequence: int = 1
        self._anchor_hash: str = self.GENESIS_PREV_HASH

    @property
    def event_count(self) -> int:
        """Total number of active events currently in the ledger."""
        return len(self._events)

    @property
    def latest_event(self) -> Optional[AuditEvent]:
        """Return the most recently appended audit event."""
        return self._events[-1] if self._events else None

    @property
    def checkpoints(self) -> List[ChainCheckpointRecord]:
        """List of chain checkpoint anchor records."""
        return list(self._checkpoints)

    def append_event(
        self,
        event_id: str,
        timestamp_iso: str,
        event_category: AuditEventCategory,
        severity: AuditEventSeverity,
        retention_class: RetentionClass,
        actor_principal: str,
        identity_type: IdentityType,
        target_component: str,
        target_ownership: ComponentOwnership,
        capability_id: str,
        payload: Dict[str, Any],
        contract_id: Optional[str] = None,
    ) -> AuditEvent:
        """Sanitize, hash, and append an immutable audit event to the ledger."""
        # 1. Deep secret redaction
        clean_payload = SecretRedactor.redact(payload)

        # 2. Derive previous hash (latest event or anchor hash)
        prev_hash = self.latest_event.event_hash if self.latest_event else self._anchor_hash

        # 3. Instantiate and compute hashes
        event = AuditEvent(
            event_id=event_id,
            sequence_number=self._next_sequence,
            timestamp_iso=timestamp_iso,
            event_category=event_category,
            severity=severity,
            retention_class=retention_class,
            actor_principal=actor_principal,
            identity_type=identity_type,
            target_component=target_component,
            target_ownership=target_ownership,
            capability_id=capability_id,
            contract_id=contract_id,
            payload=clean_payload,
        )
        event.compute_hashes(prev_hash)

        self._events.append(event)
        self._next_sequence += 1
        return event

    def verify_integrity(self) -> AuditTrailVerification:
        """Cryptographically verify all event hashes and chain links in the ledger."""
        discrepancies: List[str] = []
        tampered_ids: List[str] = []

        expected_prev_hash = self._anchor_hash

        for event in self._events:
            # Check 1: Chain linkage
            if event.prev_event_hash != expected_prev_hash:
                tampered_ids.append(event.event_id)
                discrepancies.append(
                    f"ChainBroken: Event '{event.event_id}' (seq: {event.sequence_number}) prev_event_hash "
                    f"'{event.prev_event_hash}' does not match expected '{expected_prev_hash}'."
                )

            # Check 2: Payload integrity
            canonical_json = json.dumps(event.payload, sort_keys=True, separators=(",", ":"))
            import hashlib
            computed_payload_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
            if event.payload_hash != computed_payload_hash:
                tampered_ids.append(event.event_id)
                discrepancies.append(
                    f"PayloadTampered: Event '{event.event_id}' payload hash mismatch. "
                    f"Recorded: '{event.payload_hash}', recomputed: '{computed_payload_hash}'."
                )

            # Check 3: Header & event hash integrity
            header = f"{event.event_id}:{event.sequence_number}:{event.timestamp_iso}:{event.event_category.value}:{event.prev_event_hash}:{computed_payload_hash}"
            computed_event_hash = hashlib.sha256(header.encode("utf-8")).hexdigest()
            if event.event_hash != computed_event_hash:
                tampered_ids.append(event.event_id)
                discrepancies.append(
                    f"EventHeaderTampered: Event '{event.event_id}' header hash mismatch. "
                    f"Recorded: '{event.event_hash}', recomputed: '{computed_event_hash}'."
                )

            expected_prev_hash = event.event_hash

        return AuditTrailVerification(
            is_valid=(len(discrepancies) == 0),
            verified_event_count=len(self._events),
            tampered_event_ids=list(set(tampered_ids)),
            discrepancies=discrepancies,
        )

    def prune_expired_events(
        self,
        current_time_iso: str,
        checkpoint_id: Optional[str] = None,
    ) -> Optional[ChainCheckpointRecord]:
        """Prune events exceeding their retention TTL while preserving immutable critical records."""
        now = datetime.datetime.fromisoformat(current_time_iso.replace("Z", "+00:00"))

        retained: List[AuditEvent] = []
        pruned_count = 0
        last_pruned_sequence = 0
        last_pruned_hash = self._anchor_hash

        for event in self._events:
            spec = self.RETENTION_SPECIFICATIONS.get(event.retention_class)
            event_time = datetime.datetime.fromisoformat(event.timestamp_iso.replace("Z", "+00:00"))
            age_seconds = (now - event_time).total_seconds()

            # Immutable retention class is NEVER pruned
            if spec and spec.is_immutable:
                retained.append(event)
                continue

            # Check TTL expiration
            if spec and age_seconds > spec.ttl_seconds:
                pruned_count += 1
                last_pruned_sequence = event.sequence_number
                last_pruned_hash = event.event_hash
            else:
                retained.append(event)

        if pruned_count == 0:
            return None

        # Create cryptographic checkpoint anchor
        cp_id = checkpoint_id or f"checkpoint-seq-{last_pruned_sequence}"
        checkpoint = ChainCheckpointRecord(
            checkpoint_id=cp_id,
            timestamp_iso=current_time_iso,
            pruned_up_to_sequence=last_pruned_sequence,
            anchor_event_hash=last_pruned_hash,
            remaining_count=len(retained),
        )
        self._checkpoints.append(checkpoint)

        # Update anchor hash if all prior events were pruned
        if retained and retained[0].prev_event_hash == last_pruned_hash:
            self._anchor_hash = last_pruned_hash

        self._events = retained
        return checkpoint
