"""Change detection and delta tracking between consecutive system observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import uuid

from system_mind.twin.observation_records import SystemObservationRecord


class ChangeClassification(str, Enum):
    """Semantic classification of detected telemetry changes between consecutive observations."""

    NO_CHANGE = "NO_CHANGE"
    ATTRIBUTE_MUTATION = "ATTRIBUTE_MUTATION"
    SIGNIFICANT_THRESHOLD_BREACH = "SIGNIFICANT_THRESHOLD_BREACH"
    STATUS_DEGRADATION = "STATUS_DEGRADATION"
    CONFIDENCE_SHIFT = "CONFIDENCE_SHIFT"
    LIFECYCLE_TRANSITION = "LIFECYCLE_TRANSITION"


@dataclass(frozen=True)
class AttributeMutation:
    """Granular field-level mutation between two observation payloads."""

    field_name: str
    old_value: Any
    new_value: Any
    change_type: str  # MODIFIED, ADDED, REMOVED
    delta_numeric: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes mutation to dictionary."""
        return {
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_type": self.change_type,
            "delta_numeric": self.delta_numeric,
        }


@dataclass(frozen=True)
class ObservationDelta:
    """Point-in-time delta between two consecutive observations for a specific entity."""

    delta_id: str
    entity_urn: str
    device_id: str
    from_record_id: str
    to_record_id: str
    from_sequence: int
    to_sequence: int
    from_epoch_ms: int
    to_epoch_ms: int
    time_delta_ms: int
    has_changed: bool
    change_classification: str
    added_keys: Tuple[str, ...]
    removed_keys: Tuple[str, ...]
    modified_keys: Dict[str, AttributeMutation]
    change_count: int
    detected_at_iso: str
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces schema consistency and Charter Invariant SC-03."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")
        if self.to_sequence <= self.from_sequence:
            raise ValueError(
                f"Monotonic Sequence Violation: to_sequence ({self.to_sequence}) "
                f"must be strictly greater than from_sequence ({self.from_sequence})."
            )
        if self.to_epoch_ms < self.from_epoch_ms:
            raise ValueError(
                f"Timestamp Inversion Violation: to_epoch_ms ({self.to_epoch_ms}) "
                f"cannot be earlier than from_epoch_ms ({self.from_epoch_ms})."
            )

    def to_sqlite_params(self) -> Tuple[Any, ...]:
        """Serializes record to positional parameters for SQLite insertion."""
        added_json = json.dumps(list(self.added_keys), sort_keys=True)
        removed_json = json.dumps(list(self.removed_keys), sort_keys=True)
        mod_dict = {k: v.to_dict() for k, v in self.modified_keys.items()}
        modified_json = json.dumps(mod_dict, sort_keys=True, default=str)

        return (
            self.delta_id,
            self.entity_urn,
            self.device_id,
            self.from_record_id,
            self.to_record_id,
            self.from_sequence,
            self.to_sequence,
            self.from_epoch_ms,
            self.to_epoch_ms,
            self.time_delta_ms,
            1 if self.has_changed else 0,
            self.change_classification,
            added_json,
            removed_json,
            modified_json,
            self.change_count,
            self.detected_at_iso,
            0,  # scan_proves_safe is always 0
        )

    @classmethod
    def from_sqlite_row(cls, row: Tuple[Any, ...] | sqlite3.Row) -> ObservationDelta:
        """Constructs an ObservationDelta from a SQLite query row."""
        added_keys = tuple(json.loads(row[12]))
        removed_keys = tuple(json.loads(row[13]))
        raw_mod = json.loads(row[14])
        modified_keys = {
            k: AttributeMutation(
                field_name=v["field_name"],
                old_value=v["old_value"],
                new_value=v["new_value"],
                change_type=v["change_type"],
                delta_numeric=v.get("delta_numeric"),
            )
            for k, v in raw_mod.items()
        }

        return cls(
            delta_id=row[0],
            entity_urn=row[1],
            device_id=row[2],
            from_record_id=row[3],
            to_record_id=row[4],
            from_sequence=row[5],
            to_sequence=row[6],
            from_epoch_ms=row[7],
            to_epoch_ms=row[8],
            time_delta_ms=row[9],
            has_changed=bool(row[10]),
            change_classification=row[11],
            added_keys=added_keys,
            removed_keys=removed_keys,
            modified_keys=modified_keys,
            change_count=row[15],
            detected_at_iso=row[16],
            scan_proves_safe=bool(row[17]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes delta to a JSON-compatible dictionary."""
        return {
            "delta_id": self.delta_id,
            "entity_urn": self.entity_urn,
            "device_id": self.device_id,
            "from_record_id": self.from_record_id,
            "to_record_id": self.to_record_id,
            "from_sequence": self.from_sequence,
            "to_sequence": self.to_sequence,
            "from_epoch_ms": self.from_epoch_ms,
            "to_epoch_ms": self.to_epoch_ms,
            "time_delta_ms": self.time_delta_ms,
            "has_changed": self.has_changed,
            "change_classification": self.change_classification,
            "added_keys": list(self.added_keys),
            "removed_keys": list(self.removed_keys),
            "modified_keys": {k: v.to_dict() for k, v in self.modified_keys.items()},
            "change_count": self.change_count,
            "detected_at_iso": self.detected_at_iso,
            "scan_proves_safe": self.scan_proves_safe,
        }

    def summary(self) -> str:
        """Human-readable summary of the detected observation delta."""
        change_str = "MUTATED" if self.has_changed else "IDENTICAL"
        return (
            f"Delta [{self.delta_id[:8]}]: {self.entity_urn} (seq {self.from_sequence} -> {self.to_sequence}) "
            f"[{change_str}: {self.change_classification}] in {self.time_delta_ms}ms "
            f"(+{len(self.added_keys)} added, -{len(self.removed_keys)} removed, ~{len(self.modified_keys)} mod)"
        )


class ObservationChangeDetector:
    """Calculates granular deltas and semantic classifications between consecutive observation records."""

    DEFAULT_NUMERIC_THRESHOLDS = {
        "cpu_pct": 10.0,
        "memory_percent": 10.0,
        "memory_pressure": 1.0,
        "temperature_celsius": 5.0,
        "load_average_1m": 1.5,
    }

    def __init__(self, numeric_thresholds: Optional[Dict[str, float]] = None) -> None:
        """Initialize detector with optional custom numerical change thresholds."""
        self.thresholds = dict(self.DEFAULT_NUMERIC_THRESHOLDS)
        if numeric_thresholds:
            self.thresholds.update(numeric_thresholds)

    def detect_change(
        self,
        prev_record: SystemObservationRecord,
        curr_record: SystemObservationRecord,
        detected_at_iso: Optional[str] = None,
    ) -> ObservationDelta:
        """Compares two consecutive observation records for an entity and computes their delta."""
        # Invariant INV-CHG-01: Entity & device invariance
        if prev_record.entity_urn != curr_record.entity_urn:
            raise ValueError(
                f"Entity Mismatch Violation: Cannot compute delta between different entity URNs "
                f"('{prev_record.entity_urn}' != '{curr_record.entity_urn}')."
            )
        if prev_record.device_id != curr_record.device_id:
            raise ValueError(
                f"Device Mismatch Violation: Cannot compute delta across different devices "
                f"('{prev_record.device_id}' != '{curr_record.device_id}')."
            )

        # Invariant INV-CHG-02: Monotonic sequence progression
        if curr_record.sequence_number <= prev_record.sequence_number:
            raise ValueError(
                f"Monotonic Sequence Violation: curr_record sequence ({curr_record.sequence_number}) "
                f"must be greater than prev_record sequence ({prev_record.sequence_number})."
            )
        if curr_record.observed_at_epoch_ms < prev_record.observed_at_epoch_ms:
            raise ValueError(
                f"Timestamp Inversion: curr_record timestamp ({curr_record.observed_at_epoch_ms}ms) "
                f"is earlier than prev_record timestamp ({prev_record.observed_at_epoch_ms}ms)."
            )

        time_delta_ms = max(0, curr_record.observed_at_epoch_ms - prev_record.observed_at_epoch_ms)
        now_iso = detected_at_iso or datetime.now(timezone.utc).isoformat()
        delta_id = f"delta-{uuid.uuid4().hex[:12]}"

        # Fast path 1: Identical payload digest and nominal attributes
        same_payload = prev_record.payload_sha256 == curr_record.payload_sha256
        same_status = prev_record.observation_status == curr_record.observation_status
        same_confidence = abs(prev_record.confidence_score - curr_record.confidence_score) < 0.0001

        if same_payload and same_status and same_confidence:
            return ObservationDelta(
                delta_id=delta_id,
                entity_urn=curr_record.entity_urn,
                device_id=curr_record.device_id,
                from_record_id=prev_record.record_id,
                to_record_id=curr_record.record_id,
                from_sequence=prev_record.sequence_number,
                to_sequence=curr_record.sequence_number,
                from_epoch_ms=prev_record.observed_at_epoch_ms,
                to_epoch_ms=curr_record.observed_at_epoch_ms,
                time_delta_ms=time_delta_ms,
                has_changed=False,
                change_classification=ChangeClassification.NO_CHANGE.value,
                added_keys=(),
                removed_keys=(),
                modified_keys={},
                change_count=0,
                detected_at_iso=now_iso,
                scan_proves_safe=False,
            )

        # Granular payload comparison
        prev_p = prev_record.payload
        curr_p = curr_record.payload

        prev_keys = set(prev_p.keys())
        curr_keys = set(curr_p.keys())

        added = tuple(sorted(curr_keys - prev_keys))
        removed = tuple(sorted(prev_keys - curr_keys))
        common = sorted(prev_keys & curr_keys)

        modified: Dict[str, AttributeMutation] = {}
        has_threshold_breach = False

        for k in common:
            old_val = prev_p[k]
            new_val = curr_p[k]

            if old_val != new_val:
                delta_num: Optional[float] = None
                if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                    delta_num = round(float(new_val - old_val), 4)
                    thresh = self.thresholds.get(k)
                    if thresh is not None and abs(delta_num) >= thresh:
                        has_threshold_breach = True

                modified[k] = AttributeMutation(
                    field_name=k,
                    old_value=old_val,
                    new_value=new_val,
                    change_type="MODIFIED",
                    delta_numeric=delta_num,
                )

        for k in added:
            modified[k] = AttributeMutation(
                field_name=k,
                old_value=None,
                new_value=curr_p[k],
                change_type="ADDED",
            )

        for k in removed:
            modified[k] = AttributeMutation(
                field_name=k,
                old_value=prev_p[k],
                new_value=None,
                change_type="REMOVED",
            )

        total_changes = len(added) + len(removed) + len([m for m in modified.values() if m.change_type == "MODIFIED"])

        # Determine semantic change classification
        if curr_record.observation_type == "LIFECYCLE_EVENT" or prev_record.observation_type == "LIFECYCLE_EVENT":
            classification = ChangeClassification.LIFECYCLE_TRANSITION.value
        elif curr_record.observation_status != prev_record.observation_status:
            classification = ChangeClassification.STATUS_DEGRADATION.value
        elif abs(curr_record.confidence_score - prev_record.confidence_score) >= 0.1:
            classification = ChangeClassification.CONFIDENCE_SHIFT.value
        elif has_threshold_breach:
            classification = ChangeClassification.SIGNIFICANT_THRESHOLD_BREACH.value
        elif total_changes > 0:
            classification = ChangeClassification.ATTRIBUTE_MUTATION.value
        else:
            classification = ChangeClassification.NO_CHANGE.value

        return ObservationDelta(
            delta_id=delta_id,
            entity_urn=curr_record.entity_urn,
            device_id=curr_record.device_id,
            from_record_id=prev_record.record_id,
            to_record_id=curr_record.record_id,
            from_sequence=prev_record.sequence_number,
            to_sequence=curr_record.sequence_number,
            from_epoch_ms=prev_record.observed_at_epoch_ms,
            to_epoch_ms=curr_record.observed_at_epoch_ms,
            time_delta_ms=time_delta_ms,
            has_changed=total_changes > 0 or classification != ChangeClassification.NO_CHANGE.value,
            change_classification=classification,
            added_keys=added,
            removed_keys=removed,
            modified_keys=modified,
            change_count=total_changes,
            detected_at_iso=now_iso,
            scan_proves_safe=False,
        )


class ObservationDeltaManager:
    """Manages persistent observation deltas and chronological change queries."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the manager with an active SQLite database connection."""
        self.conn = conn
        self.detector = ObservationChangeDetector()

    def record_delta(self, delta: ObservationDelta) -> str:
        """Persists an observation delta into the observation_deltas table."""
        insert_sql = """
            INSERT INTO observation_deltas (
                delta_id, entity_urn, device_id, from_record_id, to_record_id,
                from_sequence, to_sequence, from_epoch_ms, to_epoch_ms,
                time_delta_ms, has_changed, change_classification,
                added_keys_json, removed_keys_json, modified_keys_json,
                change_count, detected_at_iso, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(insert_sql, delta.to_sqlite_params())
        return delta.delta_id

    def detect_and_record(
        self,
        prev_record: SystemObservationRecord,
        curr_record: SystemObservationRecord,
    ) -> ObservationDelta:
        """Computes the delta between two observations and immediately persists it."""
        delta = self.detector.detect_change(prev_record, curr_record)
        self.record_delta(delta)
        return delta

    def detect_and_record_consecutive(self, entity_urn: str) -> Optional[ObservationDelta]:
        """Queries the two latest observation records for an entity and computes/persists their delta."""
        cursor = self.conn.execute(
            """
            SELECT * FROM system_observation_records
            WHERE entity_urn = ?
            ORDER BY sequence_number DESC
            LIMIT 2;
            """,
            (entity_urn,),
        )
        rows = cursor.fetchall()
        if len(rows) < 2:
            return None

        # rows are ordered DESC: rows[0] is latest, rows[1] is previous
        latest_record = SystemObservationRecord.from_sqlite_row(rows[0])
        previous_record = SystemObservationRecord.from_sqlite_row(rows[1])

        return self.detect_and_record(previous_record, latest_record)

    def get_delta(self, delta_id: str) -> Optional[ObservationDelta]:
        """Retrieves a single observation delta by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM observation_deltas WHERE delta_id = ?;",
            (delta_id,),
        )
        row = cursor.fetchone()
        return ObservationDelta.from_sqlite_row(row) if row else None

    def get_deltas_for_entity(
        self,
        entity_urn: str,
        only_changes: bool = False,
        limit: int = 100,
    ) -> List[ObservationDelta]:
        """Retrieves chronological observation deltas for an entity."""
        if only_changes:
            query = """
                SELECT * FROM observation_deltas
                WHERE entity_urn = ? AND has_changed = 1
                ORDER BY to_sequence ASC
                LIMIT ?;
            """
        else:
            query = """
                SELECT * FROM observation_deltas
                WHERE entity_urn = ?
                ORDER BY to_sequence ASC
                LIMIT ?;
            """
        cursor = self.conn.execute(query, (entity_urn, limit))
        return [ObservationDelta.from_sqlite_row(r) for r in cursor.fetchall()]

    def query_significant_changes(
        self,
        since_epoch_ms: Optional[int] = None,
        limit: int = 100,
    ) -> List[ObservationDelta]:
        """Queries deltas classified as significant threshold breaches, lifecycle events, or status degradations."""
        significant_types = (
            ChangeClassification.SIGNIFICANT_THRESHOLD_BREACH.value,
            ChangeClassification.LIFECYCLE_TRANSITION.value,
            ChangeClassification.STATUS_DEGRADATION.value,
        )
        placeholders = ",".join("?" for _ in significant_types)
        params: List[Any] = list(significant_types)

        since_clause = ""
        if since_epoch_ms is not None:
            since_clause = "AND to_epoch_ms >= ?"
            params.append(since_epoch_ms)

        params.append(limit)
        query = f"""
            SELECT * FROM observation_deltas
            WHERE change_classification IN ({placeholders}) {since_clause}
            ORDER BY to_epoch_ms DESC
            LIMIT ?;
        """
        cursor = self.conn.execute(query, tuple(params))
        return [ObservationDelta.from_sqlite_row(r) for r in cursor.fetchall()]
