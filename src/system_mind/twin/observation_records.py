"""Timestamped system observation records and repository for the temporal digital twin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from system_mind.twin.temporal import ObservationType, ProvenanceStatus, compute_payload_hash


def compute_observation_payload_digest(payload: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 digest of canonical observation payload JSON."""
    return compute_payload_hash(payload)


@dataclass(frozen=True)
class SystemObservationRecord:
    """Discrete, immutable, timestamped system observation record.

    Captures state snapshots or deltas for a specific entity with dual-clock anchoring,
    source provenance, bounded confidence, and strict charter invariants.
    """

    record_id: str
    device_id: str
    entity_urn: str
    collector_id: str
    observation_type: str
    observed_at_iso: str
    observed_at_epoch_ms: int
    source_monotonic_ns: Optional[int] = None
    source_clock: str = "mach_continuous_time"
    confidence_score: float = 1.0
    confidence_tier: str = "KERNEL_AUTHORITATIVE"
    provenance_status: str = "VERIFIED_KERNEL"
    sequence_number: int = 1
    payload_sha256: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    ttl_seconds: float = 60.0
    is_mock: bool = False
    observation_status: str = "ACTUAL"  # ACTUAL, MOCK, DEGRADED, UNSUPPORTED
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant (SC-03)

    def __post_init__(self) -> None:
        """Enforces schema, confidence bounds, and safety invariants."""
        # Invariant SC-03: scan_proves_safe is NEVER true
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")

        # Invariant INV-OBS-03: confidence score bounded in [0.0, 1.0]
        if not (0.0 <= self.confidence_score <= 1.0):
            raise ValueError(
                f"Confidence Score Out of Bounds: {self.confidence_score}. Must be between 0.0 and 1.0."
            )

        # Invariant INV-OBS-01: entity_urn must be valid URN
        if not self.entity_urn or not self.entity_urn.startswith("urn:systemmind:"):
            raise ValueError(
                f"Invalid entity URN: '{self.entity_urn}'. Must start with 'urn:systemmind:'."
            )

        # Invariant INV-OBS-01: device_id must be non-empty
        if not self.device_id or not self.device_id.strip():
            raise ValueError("device_id cannot be empty.")

        # Invariant: mock observations cannot claim kernel authority
        if self.is_mock and self.confidence_tier in ("KERNEL_AUTHORITATIVE", "SUBSYSTEM_VERIFIED"):
            raise ValueError(
                f"Mock Provenance Violation: Mock observations cannot claim '{self.confidence_tier}'."
            )

        # Invariant INV-OBS-05: Payload hash verification
        expected_hash = compute_observation_payload_digest(self.payload)
        if self.payload_sha256 and self.payload_sha256 != expected_hash:
            raise ValueError(
                f"Payload hash mismatch: provided '{self.payload_sha256}' does not match computed '{expected_hash}'."
            )

        if not self.payload_sha256:
            object.__setattr__(self, "payload_sha256", expected_hash)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes record to standard dictionary representation."""
        return {
            "record_id": self.record_id,
            "device_id": self.device_id,
            "entity_urn": self.entity_urn,
            "collector_id": self.collector_id,
            "observation_type": self.observation_type,
            "observed_at_iso": self.observed_at_iso,
            "observed_at_epoch_ms": self.observed_at_epoch_ms,
            "source_monotonic_ns": self.source_monotonic_ns,
            "source_clock": self.source_clock,
            "confidence_score": round(self.confidence_score, 4),
            "confidence_tier": self.confidence_tier,
            "provenance_status": self.provenance_status,
            "sequence_number": self.sequence_number,
            "payload_sha256": self.payload_sha256,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "ttl_seconds": self.ttl_seconds,
            "is_mock": self.is_mock,
            "observation_status": self.observation_status,
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SystemObservationRecord:
        """Constructs a validated SystemObservationRecord from a dictionary."""
        return cls(
            record_id=data["record_id"],
            device_id=data["device_id"],
            entity_urn=data["entity_urn"],
            collector_id=data["collector_id"],
            observation_type=data["observation_type"],
            observed_at_iso=data["observed_at_iso"],
            observed_at_epoch_ms=int(data["observed_at_epoch_ms"]),
            source_monotonic_ns=int(data["source_monotonic_ns"]) if data.get("source_monotonic_ns") is not None else None,
            source_clock=data.get("source_clock", "mach_continuous_time"),
            confidence_score=float(data.get("confidence_score", 1.0)),
            confidence_tier=data.get("confidence_tier", "KERNEL_AUTHORITATIVE"),
            provenance_status=data.get("provenance_status", "VERIFIED_KERNEL"),
            sequence_number=int(data.get("sequence_number", 1)),
            payload_sha256=data.get("payload_sha256", ""),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            ttl_seconds=float(data.get("ttl_seconds", 60.0)),
            is_mock=bool(data.get("is_mock", False)),
            observation_status=data.get("observation_status", "ACTUAL"),
            scan_proves_safe=bool(data.get("scan_proves_safe", False)),
        )

    def to_sqlite_params(self) -> tuple[Any, ...]:
        """Serializes record to tuple of positional SQL bind parameters."""
        return (
            self.record_id,
            self.device_id,
            self.entity_urn,
            self.collector_id,
            self.observation_type,
            self.observed_at_iso,
            self.observed_at_epoch_ms,
            self.source_monotonic_ns,
            self.source_clock,
            self.confidence_score,
            self.confidence_tier,
            self.provenance_status,
            self.sequence_number,
            self.payload_sha256,
            json.dumps(self.payload, sort_keys=True, default=str),
            json.dumps(self.metadata, sort_keys=True, default=str),
            self.ttl_seconds,
            1 if self.is_mock else 0,
            self.observation_status,
            1 if self.scan_proves_safe else 0,
        )

    @classmethod
    def from_sqlite_row(cls, row: sqlite3.Row | tuple[Any, ...]) -> SystemObservationRecord:
        """Constructs a SystemObservationRecord from an SQLite query row."""
        if isinstance(row, sqlite3.Row):
            d = dict(row)
            return cls(
                record_id=d["record_id"],
                device_id=d["device_id"],
                entity_urn=d["entity_urn"],
                collector_id=d["collector_id"],
                observation_type=d["observation_type"],
                observed_at_iso=d["observed_at_iso"],
                observed_at_epoch_ms=int(d["observed_at_epoch_ms"]),
                source_monotonic_ns=int(d["source_monotonic_ns"]) if d["source_monotonic_ns"] is not None else None,
                source_clock=d["source_clock"],
                confidence_score=float(d["confidence_score"]),
                confidence_tier=d["confidence_tier"],
                provenance_status=d["provenance_status"],
                sequence_number=int(d["sequence_number"]),
                payload_sha256=d["payload_sha256"],
                payload=json.loads(d["payload_json"]),
                metadata=json.loads(d["metadata_json"]),
                ttl_seconds=float(d["ttl_seconds"]),
                is_mock=bool(d["is_mock"]),
                observation_status=d["observation_status"],
                scan_proves_safe=bool(d["scan_proves_safe"]),
            )
        else:
            return cls(
                record_id=row[0],
                device_id=row[1],
                entity_urn=row[2],
                collector_id=row[3],
                observation_type=row[4],
                observed_at_iso=row[5],
                observed_at_epoch_ms=int(row[6]),
                source_monotonic_ns=int(row[7]) if row[7] is not None else None,
                source_clock=row[8],
                confidence_score=float(row[9]),
                confidence_tier=row[10],
                provenance_status=row[11],
                sequence_number=int(row[12]),
                payload_sha256=row[13],
                payload=json.loads(row[14]),
                metadata=json.loads(row[15]),
                ttl_seconds=float(row[16]),
                is_mock=bool(row[17]),
                observation_status=row[18],
                scan_proves_safe=bool(row[19]),
            )


class ObservationRecordManager:
    """Manages transactional persistence, querying, and point-in-time state reconstruction."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record_observation(self, record: SystemObservationRecord) -> str:
        """Persists an observation record to SQLite with monotonic sequence enforcement.

        Raises:
            ValueError: On monotonic sequence or timestamp inversion violation.
        """
        # Enforce sequence progression per entity_urn
        cursor = self.conn.execute(
            """
            SELECT sequence_number, observed_at_epoch_ms
            FROM system_observation_records
            WHERE entity_urn = ?
            ORDER BY sequence_number DESC
            LIMIT 1;
            """,
            (record.entity_urn,),
        )
        latest_row = cursor.fetchone()

        if latest_row is not None:
            latest_seq, latest_epoch_ms = latest_row[0], latest_row[1]
            if record.sequence_number <= latest_seq:
                raise ValueError(
                    f"Monotonic Sequence Violation: Entity '{record.entity_urn}' sequence {record.sequence_number} "
                    f"is not greater than latest sequence {latest_seq}."
                )
            if record.observed_at_epoch_ms < latest_epoch_ms:
                raise ValueError(
                    f"Timestamp Inversion Violation: Entity '{record.entity_urn}' timestamp {record.observed_at_epoch_ms}ms "
                    f"is earlier than latest recorded {latest_epoch_ms}ms."
                )

        insert_sql = """
            INSERT INTO system_observation_records (
                record_id, device_id, entity_urn, collector_id, observation_type,
                observed_at_iso, observed_at_epoch_ms, source_monotonic_ns, source_clock,
                confidence_score, confidence_tier, provenance_status, sequence_number,
                payload_sha256, payload_json, metadata_json, ttl_seconds,
                is_mock, observation_status, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(insert_sql, record.to_sqlite_params())
        return record.record_id

    def get_record(self, record_id: str) -> Optional[SystemObservationRecord]:
        """Retrieves a single observation record by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM system_observation_records WHERE record_id = ?;",
            (record_id,),
        )
        row = cursor.fetchone()
        return SystemObservationRecord.from_sqlite_row(row) if row else None

    def get_latest_observation(self, entity_urn: str) -> Optional[SystemObservationRecord]:
        """Retrieves the latest chronological observation for a specific entity URN."""
        cursor = self.conn.execute(
            """
            SELECT * FROM system_observation_records
            WHERE entity_urn = ?
            ORDER BY sequence_number DESC
            LIMIT 1;
            """,
            (entity_urn,),
        )
        row = cursor.fetchone()
        return SystemObservationRecord.from_sqlite_row(row) if row else None

    def get_observations_for_entity(
        self,
        entity_urn: str,
        limit: int = 100,
    ) -> List[SystemObservationRecord]:
        """Retrieves chronological observations for an entity."""
        cursor = self.conn.execute(
            """
            SELECT * FROM system_observation_records
            WHERE entity_urn = ?
            ORDER BY sequence_number ASC
            LIMIT ?;
            """,
            (entity_urn, limit),
        )
        return [SystemObservationRecord.from_sqlite_row(r) for r in cursor.fetchall()]

    def query_observations(
        self,
        entity_urn: Optional[str] = None,
        collector_id: Optional[str] = None,
        since_epoch_ms: Optional[int] = None,
        until_epoch_ms: Optional[int] = None,
        observation_type: Optional[str] = None,
        observation_status: Optional[str] = None,
        include_mock: bool = True,
        limit: int = 100,
    ) -> List[SystemObservationRecord]:
        """Queries observations matching filtering criteria ordered chronologically."""
        clauses: list[str] = []
        params: list[Any] = []

        if entity_urn is not None:
            clauses.append("entity_urn = ?")
            params.append(entity_urn)
        if collector_id is not None:
            clauses.append("collector_id = ?")
            params.append(collector_id)
        if since_epoch_ms is not None:
            clauses.append("observed_at_epoch_ms >= ?")
            params.append(since_epoch_ms)
        if until_epoch_ms is not None:
            clauses.append("observed_at_epoch_ms <= ?")
            params.append(until_epoch_ms)
        if observation_type is not None:
            clauses.append("observation_type = ?")
            params.append(observation_type)
        if observation_status is not None:
            clauses.append("observation_status = ?")
            params.append(observation_status)
        if not include_mock:
            clauses.append("is_mock = 0")

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = f"""
            SELECT * FROM system_observation_records
            {where_str}
            ORDER BY observed_at_epoch_ms ASC, sequence_number ASC
            LIMIT ?;
        """
        params.append(limit)

        cursor = self.conn.execute(query_sql, tuple(params))
        return [SystemObservationRecord.from_sqlite_row(r) for r in cursor.fetchall()]

    def reconstruct_state_at(self, entity_urn: str, target_epoch_ms: int) -> Dict[str, Any]:
        """Reconstructs the state of an entity at a target historical millisecond timestamp.

        Finds the most recent STATE_SNAPSHOT <= target_epoch_ms and replays subsequent
        ATTRIBUTE_DELTA / LIFECYCLE_EVENT records up to target_epoch_ms.
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM system_observation_records
            WHERE entity_urn = ? AND observed_at_epoch_ms <= ?
            ORDER BY sequence_number ASC;
            """,
            (entity_urn, target_epoch_ms),
        )
        records = [SystemObservationRecord.from_sqlite_row(r) for r in cursor.fetchall()]

        if not records:
            return {}

        reconstructed: Dict[str, Any] = {}
        for rec in records:
            if rec.observation_type == ObservationType.STATE_SNAPSHOT.value:
                reconstructed = dict(rec.payload)
            elif rec.observation_type in (
                ObservationType.ATTRIBUTE_DELTA.value,
                ObservationType.LIFECYCLE_EVENT.value,
            ):
                reconstructed.update(rec.payload)

        return reconstructed

    def count_observations(self, entity_urn: Optional[str] = None) -> int:
        """Returns the total number of recorded observations."""
        if entity_urn is not None:
            cursor = self.conn.execute(
                "SELECT COUNT(*) FROM system_observation_records WHERE entity_urn = ?;",
                (entity_urn,),
            )
        else:
            cursor = self.conn.execute("SELECT COUNT(*) FROM system_observation_records;")
        return int(cursor.fetchone()[0])

    def clear_observations(self, entity_urn: Optional[str] = None) -> int:
        """Deletes observation records (primarily for testing and compaction)."""
        if entity_urn is not None:
            cursor = self.conn.execute(
                "DELETE FROM system_observation_records WHERE entity_urn = ?;",
                (entity_urn,),
            )
        else:
            cursor = self.conn.execute("DELETE FROM system_observation_records;")
        return cursor.rowcount

    @staticmethod
    def create_record(
        device_id: str,
        entity_urn: str,
        collector_id: str,
        observation_type: str = ObservationType.STATE_SNAPSHOT.value,
        payload: Optional[Dict[str, Any]] = None,
        observed_at_iso: Optional[str] = None,
        observed_at_epoch_ms: Optional[int] = None,
        source_monotonic_ns: Optional[int] = None,
        source_clock: str = "mach_continuous_time",
        confidence_score: float = 1.0,
        confidence_tier: str = "KERNEL_AUTHORITATIVE",
        provenance_status: str = ProvenanceStatus.VERIFIED_KERNEL.value,
        sequence_number: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: float = 60.0,
        is_mock: bool = False,
        observation_status: str = "ACTUAL",
        record_id: Optional[str] = None,
    ) -> SystemObservationRecord:
        """Factory helper creating a validated SystemObservationRecord with current timestamps."""
        now = datetime.now(timezone.utc)
        iso = observed_at_iso or now.isoformat()
        epoch = observed_at_epoch_ms if observed_at_epoch_ms is not None else int(now.timestamp() * 1000)
        rec_id = record_id or f"obs-{uuid.uuid4().hex[:12]}"
        payload_dict = payload or {}
        meta_dict = metadata or {}

        return SystemObservationRecord(
            record_id=rec_id,
            device_id=device_id,
            entity_urn=entity_urn,
            collector_id=collector_id,
            observation_type=observation_type,
            observed_at_iso=iso,
            observed_at_epoch_ms=epoch,
            source_monotonic_ns=source_monotonic_ns,
            source_clock=source_clock,
            confidence_score=confidence_score,
            confidence_tier=confidence_tier,
            provenance_status=provenance_status,
            sequence_number=sequence_number,
            payload=payload_dict,
            metadata=meta_dict,
            ttl_seconds=ttl_seconds,
            is_mock=is_mock,
            observation_status=observation_status,
            scan_proves_safe=False,
        )
