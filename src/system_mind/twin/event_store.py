"""Append-only system event storage with cryptographic hash chaining and immutability for the digital twin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from system_mind.core.types import ComponentOwnership

GENESIS_PREV_HASH = "0" * 64


class SystemEventType(str, Enum):
    """Categorization of discrete system state transitions and lifecycle events."""

    PROCESS_SPAWNED = "PROCESS_SPAWNED"
    PROCESS_EXITED = "PROCESS_EXITED"
    APPLICATION_INSTALLED = "APPLICATION_INSTALLED"
    APPLICATION_UNINSTALLED = "APPLICATION_UNINSTALLED"
    APPLICATION_LAUNCHED = "APPLICATION_LAUNCHED"
    APPLICATION_TERMINATED = "APPLICATION_TERMINATED"
    FILE_CREATED = "FILE_CREATED"
    FILE_MODIFIED = "FILE_MODIFIED"
    FILE_DELETED = "FILE_DELETED"
    NETWORK_INTERFACE_STATE = "NETWORK_INTERFACE_STATE"
    SERVICE_STATE_CHANGED = "SERVICE_STATE_CHANGED"
    HARDWARE_ATTACHED = "HARDWARE_ATTACHED"
    HARDWARE_DETACHED = "HARDWARE_DETACHED"
    CONFIG_MUTATED = "CONFIG_MUTATED"
    SYSTEM_ALERT = "SYSTEM_ALERT"


def compute_event_payload_hash(payload: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 digest of canonical event payload JSON."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_event_block_hash(
    prev_event_hash: str,
    sequence_number: int,
    event_id: str,
    timestamp_iso: str,
    entity_urn: str,
    event_type: str,
    payload_sha256: str,
) -> str:
    """Computes the cryptographic block hash sealing this event in the ledger chain."""
    raw = (
        f"{prev_event_hash}:{sequence_number}:{event_id}:{timestamp_iso}:"
        f"{entity_urn}:{event_type}:{payload_sha256}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SystemEventRecord:
    """Immutable, cryptographically chained system event record.

    Captures a discrete state occurrence or lifecycle transition for an entity,
    sealed with SHA-256 hash chaining to ensure mathematical tamper evidence.
    """

    sequence_number: int
    event_id: str
    device_id: str
    entity_urn: str
    event_type: str
    timestamp_iso: str
    timestamp_epoch_ms: int
    prev_event_hash: str
    payload_sha256: str = ""
    event_hash: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    component_ownership: ComponentOwnership = ComponentOwnership.SYSTEM_MANAGED
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant (SC-03)

    def __post_init__(self) -> None:
        """Enforces schema integrity and non-negotiable charter invariants."""
        # Invariant SC-03: scan_proves_safe must always be False
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")

        # Invariant INV-EVT-01: entity_urn must be valid URN
        if not self.entity_urn or not self.entity_urn.startswith("urn:systemmind:"):
            raise ValueError(
                f"Invalid entity URN: '{self.entity_urn}'. Must start with 'urn:systemmind:'."
            )

        # Invariant INV-EVT-01: device_id cannot be empty
        if not self.device_id or not self.device_id.strip():
            raise ValueError("device_id cannot be empty.")

        # Validate payload hash
        expected_payload_hash = compute_event_payload_hash(self.payload)
        if self.payload_sha256 and self.payload_sha256 != expected_payload_hash:
            raise ValueError(
                f"Payload hash mismatch: provided '{self.payload_sha256}' does not match computed '{expected_payload_hash}'."
            )
        if not self.payload_sha256:
            object.__setattr__(self, "payload_sha256", expected_payload_hash)

        # Validate event block hash
        expected_block_hash = compute_event_block_hash(
            prev_event_hash=self.prev_event_hash,
            sequence_number=self.sequence_number,
            event_id=self.event_id,
            timestamp_iso=self.timestamp_iso,
            entity_urn=self.entity_urn,
            event_type=self.event_type,
            payload_sha256=self.payload_sha256,
        )
        if self.event_hash and self.event_hash != expected_block_hash:
            raise ValueError(
                f"Event hash mismatch: provided '{self.event_hash}' does not match computed '{expected_block_hash}'."
            )
        if not self.event_hash:
            object.__setattr__(self, "event_hash", expected_block_hash)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes event record to dictionary representation."""
        return {
            "sequence_number": self.sequence_number,
            "event_id": self.event_id,
            "device_id": self.device_id,
            "entity_urn": self.entity_urn,
            "event_type": self.event_type,
            "timestamp_iso": self.timestamp_iso,
            "timestamp_epoch_ms": self.timestamp_epoch_ms,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "prev_event_hash": self.prev_event_hash,
            "payload_sha256": self.payload_sha256,
            "event_hash": self.event_hash,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "component_ownership": self.component_ownership.value if isinstance(self.component_ownership, ComponentOwnership) else str(self.component_ownership),
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SystemEventRecord:
        """Constructs a validated SystemEventRecord from a dictionary."""
        ownership_val = data.get("component_ownership", ComponentOwnership.SYSTEM_MANAGED.value)
        try:
            ownership = ComponentOwnership(ownership_val)
        except ValueError:
            ownership = ComponentOwnership.SYSTEM_MANAGED

        return cls(
            sequence_number=int(data["sequence_number"]),
            event_id=data["event_id"],
            device_id=data["device_id"],
            entity_urn=data["entity_urn"],
            event_type=data["event_type"],
            timestamp_iso=data["timestamp_iso"],
            timestamp_epoch_ms=int(data["timestamp_epoch_ms"]),
            prev_event_hash=data["prev_event_hash"],
            payload_sha256=data.get("payload_sha256", ""),
            event_hash=data.get("event_hash", ""),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            component_ownership=ownership,
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            scan_proves_safe=bool(data.get("scan_proves_safe", False)),
        )

    def to_sqlite_params(self) -> tuple[Any, ...]:
        """Serializes record to tuple of positional SQL bind parameters."""
        ownership_str = self.component_ownership.value if isinstance(self.component_ownership, ComponentOwnership) else str(self.component_ownership)
        return (
            self.sequence_number,
            self.event_id,
            self.device_id,
            self.entity_urn,
            self.event_type,
            self.timestamp_iso,
            self.timestamp_epoch_ms,
            self.correlation_id,
            self.causation_id,
            self.prev_event_hash,
            self.payload_sha256,
            self.event_hash,
            json.dumps(self.payload, sort_keys=True, default=str),
            json.dumps(self.metadata, sort_keys=True, default=str),
            ownership_str,
            1 if self.scan_proves_safe else 0,
        )

    @classmethod
    def from_sqlite_row(cls, row: sqlite3.Row | tuple[Any, ...]) -> SystemEventRecord:
        """Constructs a SystemEventRecord from an SQLite query row."""
        if isinstance(row, sqlite3.Row):
            d = dict(row)
            try:
                ownership = ComponentOwnership(d["component_ownership"])
            except ValueError:
                ownership = ComponentOwnership.SYSTEM_MANAGED
            return cls(
                sequence_number=int(d["sequence_number"]),
                event_id=d["event_id"],
                device_id=d["device_id"],
                entity_urn=d["entity_urn"],
                event_type=d["event_type"],
                timestamp_iso=d["timestamp_iso"],
                timestamp_epoch_ms=int(d["timestamp_epoch_ms"]),
                correlation_id=d["correlation_id"],
                causation_id=d["causation_id"],
                prev_event_hash=d["prev_event_hash"],
                payload_sha256=d["payload_sha256"],
                event_hash=d["event_hash"],
                payload=json.loads(d["payload_json"]),
                metadata=json.loads(d["metadata_json"]),
                component_ownership=ownership,
                scan_proves_safe=bool(d["scan_proves_safe"]),
            )
        else:
            try:
                ownership = ComponentOwnership(row[14])
            except ValueError:
                ownership = ComponentOwnership.SYSTEM_MANAGED
            return cls(
                sequence_number=int(row[0]),
                event_id=row[1],
                device_id=row[2],
                entity_urn=row[3],
                event_type=row[4],
                timestamp_iso=row[5],
                timestamp_epoch_ms=int(row[6]),
                correlation_id=row[7],
                causation_id=row[8],
                prev_event_hash=row[9],
                payload_sha256=row[10],
                event_hash=row[11],
                payload=json.loads(row[12]),
                metadata=json.loads(row[13]),
                component_ownership=ownership,
                scan_proves_safe=bool(row[15]),
            )


class SystemEventStore:
    """Append-only cryptographic event store managing system events."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def append_event(
        self,
        device_id: str,
        entity_urn: str,
        event_type: str | SystemEventType,
        payload: Dict[str, Any],
        component_ownership: ComponentOwnership | str = ComponentOwnership.SYSTEM_MANAGED,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp_iso: Optional[str] = None,
        timestamp_epoch_ms: Optional[int] = None,
        event_id: Optional[str] = None,
    ) -> SystemEventRecord:
        """Appends an event to the ledger, computing cryptographic hash chaining atomically."""
        now = datetime.now(timezone.utc)
        iso = timestamp_iso or now.isoformat()
        epoch = timestamp_epoch_ms if timestamp_epoch_ms is not None else int(now.timestamp() * 1000)
        evt_id = event_id or f"evt-{uuid.uuid4().hex[:12]}"
        evt_type = event_type.value if isinstance(event_type, SystemEventType) else str(event_type)

        ownership = (
            component_ownership
            if isinstance(component_ownership, ComponentOwnership)
            else ComponentOwnership(component_ownership)
        )

        cursor = self.conn.execute(
            """
            SELECT sequence_number, event_hash
            FROM system_events
            ORDER BY sequence_number DESC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        if row:
            next_seq = row[0] + 1
            prev_hash = row[1]
        else:
            next_seq = 1
            prev_hash = GENESIS_PREV_HASH

        payload_dict = dict(payload)
        metadata_dict = dict(metadata or {})
        payload_hash = compute_event_payload_hash(payload_dict)
        block_hash = compute_event_block_hash(
            prev_event_hash=prev_hash,
            sequence_number=next_seq,
            event_id=evt_id,
            timestamp_iso=iso,
            entity_urn=entity_urn,
            event_type=evt_type,
            payload_sha256=payload_hash,
        )

        record = SystemEventRecord(
            sequence_number=next_seq,
            event_id=evt_id,
            device_id=device_id,
            entity_urn=entity_urn,
            event_type=evt_type,
            timestamp_iso=iso,
            timestamp_epoch_ms=epoch,
            prev_event_hash=prev_hash,
            payload_sha256=payload_hash,
            event_hash=block_hash,
            payload=payload_dict,
            metadata=metadata_dict,
            component_ownership=ownership,
            correlation_id=correlation_id,
            causation_id=causation_id,
            scan_proves_safe=False,
        )

        insert_sql = """
            INSERT INTO system_events (
                sequence_number, event_id, device_id, entity_urn, event_type,
                timestamp_iso, timestamp_epoch_ms, correlation_id, causation_id,
                prev_event_hash, payload_sha256, event_hash, payload_json,
                metadata_json, component_ownership, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(insert_sql, record.to_sqlite_params())
        return record

    def get_event(self, event_id: str) -> Optional[SystemEventRecord]:
        """Retrieves a single system event by its unique event_id."""
        cursor = self.conn.execute(
            "SELECT * FROM system_events WHERE event_id = ?;",
            (event_id,),
        )
        row = cursor.fetchone()
        return SystemEventRecord.from_sqlite_row(row) if row else None

    def get_event_by_sequence(self, sequence_number: int) -> Optional[SystemEventRecord]:
        """Retrieves a single system event by its global sequence number."""
        cursor = self.conn.execute(
            "SELECT * FROM system_events WHERE sequence_number = ?;",
            (sequence_number,),
        )
        row = cursor.fetchone()
        return SystemEventRecord.from_sqlite_row(row) if row else None

    def get_latest_event(self) -> Optional[SystemEventRecord]:
        """Retrieves the latest appended system event."""
        cursor = self.conn.execute(
            "SELECT * FROM system_events ORDER BY sequence_number DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        return SystemEventRecord.from_sqlite_row(row) if row else None

    def query_events(
        self,
        entity_urn: Optional[str] = None,
        event_type: Optional[str | SystemEventType] = None,
        correlation_id: Optional[str] = None,
        ownership: Optional[ComponentOwnership | str] = None,
        since_epoch_ms: Optional[int] = None,
        until_epoch_ms: Optional[int] = None,
        limit: int = 100,
    ) -> List[SystemEventRecord]:
        """Queries events matching filter criteria ordered chronologically by sequence number."""
        clauses: list[str] = []
        params: list[Any] = []

        if entity_urn is not None:
            clauses.append("entity_urn = ?")
            params.append(entity_urn)
        if event_type is not None:
            t = event_type.value if isinstance(event_type, SystemEventType) else str(event_type)
            clauses.append("event_type = ?")
            params.append(t)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if ownership is not None:
            o = ownership.value if isinstance(ownership, ComponentOwnership) else str(ownership)
            clauses.append("component_ownership = ?")
            params.append(o)
        if since_epoch_ms is not None:
            clauses.append("timestamp_epoch_ms >= ?")
            params.append(since_epoch_ms)
        if until_epoch_ms is not None:
            clauses.append("timestamp_epoch_ms <= ?")
            params.append(until_epoch_ms)

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = f"""
            SELECT * FROM system_events
            {where_str}
            ORDER BY sequence_number ASC
            LIMIT ?;
        """
        params.append(limit)

        cursor = self.conn.execute(query_sql, tuple(params))
        return [SystemEventRecord.from_sqlite_row(r) for r in cursor.fetchall()]

    def verify_chain_integrity(self) -> tuple[bool, int, Optional[str]]:
        """Verifies mathematical cryptographic hash-chain integrity across all stored events.

        Returns:
            tuple of (is_valid, verified_events_count, error_message)
        """
        cursor = self.conn.execute("SELECT * FROM system_events ORDER BY sequence_number ASC;")
        rows = cursor.fetchall()

        if not rows:
            return True, 0, None

        expected_prev_hash = GENESIS_PREV_HASH
        expected_seq = 1

        for row in rows:
            record = SystemEventRecord.from_sqlite_row(row)

            # 1. Sequence monotonicity check
            if record.sequence_number != expected_seq:
                return (
                    False,
                    expected_seq - 1,
                    f"Sequence Broken: Expected sequence {expected_seq}, found {record.sequence_number}.",
                )

            # 2. Previous hash link check
            if record.prev_event_hash != expected_prev_hash:
                return (
                    False,
                    expected_seq - 1,
                    f"Chain Invalidation: Event {record.event_id} prev_event_hash '{record.prev_event_hash}' "
                    f"does not match expected '{expected_prev_hash}'.",
                )

            # 3. Payload integrity check
            recomputed_payload_hash = compute_event_payload_hash(record.payload)
            if record.payload_sha256 != recomputed_payload_hash:
                return (
                    False,
                    expected_seq - 1,
                    f"Payload Tampering: Event {record.event_id} payload_sha256 '{record.payload_sha256}' "
                    f"does not match recomputed '{recomputed_payload_hash}'.",
                )

            # 4. Block hash verification
            recomputed_block_hash = compute_event_block_hash(
                prev_event_hash=record.prev_event_hash,
                sequence_number=record.sequence_number,
                event_id=record.event_id,
                timestamp_iso=record.timestamp_iso,
                entity_urn=record.entity_urn,
                event_type=record.event_type,
                payload_sha256=record.payload_sha256,
            )
            if record.event_hash != recomputed_block_hash:
                return (
                    False,
                    expected_seq - 1,
                    f"Block Hash Invalidation: Event {record.event_id} event_hash '{record.event_hash}' "
                    f"does not match recomputed '{recomputed_block_hash}'.",
                )

            expected_prev_hash = record.event_hash
            expected_seq += 1

        return True, len(rows), None

    def count_events(self) -> int:
        """Returns the total number of events in the ledger."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM system_events;")
        return int(cursor.fetchone()[0])
