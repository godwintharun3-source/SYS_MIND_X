"""Collector gap detection, state reconciliation, and temporal healing for the Digital Twin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import uuid

from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import TwinEntity, TwinEntityType


class GapClassification(str, Enum):
    """Semantic classification of telemetry collection gaps."""

    MINOR_JITTER = "MINOR_JITTER"
    COLLECTOR_TIMEOUT = "COLLECTOR_TIMEOUT"
    COLLECTOR_RESTART = "COLLECTOR_RESTART"
    SYSTEM_SLEEP_WAKE = "SYSTEM_SLEEP_WAKE"
    PROLONGED_OUTAGE = "PROLONGED_OUTAGE"


class ReconciliationActionType(str, Enum):
    """Action taken for an entity during state reconciliation after a gap."""

    SUSTAINED_ACROSS_GAP = "SUSTAINED_ACROSS_GAP"
    TERMINATED_DURING_GAP = "TERMINATED_DURING_GAP"
    MARKED_STALE_PENDING_CONFIRMATION = "MARKED_STALE_PENDING_CONFIRMATION"
    SPAWNED_OR_ATTACHED_DURING_GAP = "SPAWNED_OR_ATTACHED_DURING_GAP"


# Domain default expected polling cadences in milliseconds
DOMAIN_DEFAULT_CADENCE_MS: Dict[str, int] = {
    "proc": 5000,
    "cpu": 5000,
    "mem": 5000,
    "gpu": 10000,
    "battery": 15000,
    "net": 10000,
    "disk": 30000,
    "svc": 30000,
    "vol": 30000,
    "app": 60000,
    "kernel": 60000,
    "host": 60000,
}
DEFAULT_FALLBACK_CADENCE_MS = 5000


@dataclass(frozen=True)
class ReconciliationItem:
    """Itemized entity reconciliation action."""

    entity_urn: str
    entity_type: str
    action_type: str  # ReconciliationActionType
    reason: str
    confidence_score: float
    inferred_timestamp_epoch_ms: Optional[int] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes item to dictionary."""
        return {
            "entity_urn": self.entity_urn,
            "entity_type": self.entity_type,
            "action_type": self.action_type,
            "reason": self.reason,
            "confidence_score": self.confidence_score,
            "inferred_timestamp_epoch_ms": self.inferred_timestamp_epoch_ms,
            "attributes": self.attributes,
        }


@dataclass(frozen=True)
class CollectorGap:
    """Represents an identified temporal gap in telemetry collection for a device and domain."""

    gap_id: str
    collector_id: str
    device_id: str
    domain: str
    gap_start_epoch_ms: int
    gap_end_epoch_ms: int
    gap_duration_ms: int
    expected_cadence_ms: int
    gap_classification: str
    detected_at_iso: str
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces schema consistency and Charter Invariant SC-03."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")
        if self.gap_end_epoch_ms <= self.gap_start_epoch_ms:
            raise ValueError(
                f"Invalid Gap Bounds: gap_end_epoch_ms ({self.gap_end_epoch_ms}) "
                f"must be strictly greater than gap_start_epoch_ms ({self.gap_start_epoch_ms})."
            )
        expected_dur = self.gap_end_epoch_ms - self.gap_start_epoch_ms
        if self.gap_duration_ms != expected_dur:
            raise ValueError(
                f"Invalid Gap Duration: gap_duration_ms ({self.gap_duration_ms}) "
                f"must match gap_end - gap_start ({expected_dur})."
            )

    def to_sqlite_params(self) -> Tuple[Any, ...]:
        """Serializes gap to positional parameters for SQLite insertion."""
        return (
            self.gap_id,
            self.collector_id,
            self.device_id,
            self.domain,
            self.gap_start_epoch_ms,
            self.gap_end_epoch_ms,
            self.gap_duration_ms,
            self.expected_cadence_ms,
            self.gap_classification,
            self.detected_at_iso,
            0,  # scan_proves_safe is always 0
        )

    @classmethod
    def from_sqlite_row(cls, row: Tuple[Any, ...] | sqlite3.Row) -> CollectorGap:
        """Constructs a CollectorGap from a SQLite row."""
        return cls(
            gap_id=row[0],
            collector_id=row[1],
            device_id=row[2],
            domain=row[3],
            gap_start_epoch_ms=row[4],
            gap_end_epoch_ms=row[5],
            gap_duration_ms=row[6],
            expected_cadence_ms=row[7],
            gap_classification=row[8],
            detected_at_iso=row[9],
            scan_proves_safe=bool(row[10]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes gap to dictionary."""
        return {
            "gap_id": self.gap_id,
            "collector_id": self.collector_id,
            "device_id": self.device_id,
            "domain": self.domain,
            "gap_start_epoch_ms": self.gap_start_epoch_ms,
            "gap_end_epoch_ms": self.gap_end_epoch_ms,
            "gap_duration_ms": self.gap_duration_ms,
            "expected_cadence_ms": self.expected_cadence_ms,
            "gap_classification": self.gap_classification,
            "detected_at_iso": self.detected_at_iso,
            "scan_proves_safe": self.scan_proves_safe,
        }

    def summary(self) -> str:
        """Human-readable summary of the detected collector gap."""
        return (
            f"CollectorGap [{self.gap_id[:8]}]: {self.collector_id} ({self.domain}) "
            f"on {self.device_id[:8]} lasted {self.gap_duration_ms}ms "
            f"[{self.gap_classification}] (cadence: {self.expected_cadence_ms}ms)"
        )


@dataclass(frozen=True)
class StateReconciliationRecord:
    """Audit record capturing state reconciliation results across a collector gap."""

    reconciliation_id: str
    gap_id: str
    device_id: str
    domain: str
    reconciled_at_iso: str
    reconciled_at_epoch_ms: int
    entities_sustained_count: int
    entities_terminated_count: int
    entities_staled_count: int
    entities_spawned_count: int
    confidence_discount_pct: float
    actions: Tuple[ReconciliationItem, ...]
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces schema consistency and Charter Invariant SC-03."""
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")

    def to_sqlite_params(self) -> Tuple[Any, ...]:
        """Serializes record to positional parameters for SQLite insertion."""
        actions_json = json.dumps([item.to_dict() for item in self.actions], sort_keys=True)
        return (
            self.reconciliation_id,
            self.gap_id,
            self.device_id,
            self.domain,
            self.reconciled_at_iso,
            self.reconciled_at_epoch_ms,
            self.entities_sustained_count,
            self.entities_terminated_count,
            self.entities_staled_count,
            self.entities_spawned_count,
            self.confidence_discount_pct,
            actions_json,
            0,  # scan_proves_safe is always 0
        )

    @classmethod
    def from_sqlite_row(cls, row: Tuple[Any, ...] | sqlite3.Row) -> StateReconciliationRecord:
        """Constructs a StateReconciliationRecord from a SQLite row."""
        raw_actions = json.loads(row[11])
        actions = tuple(
            ReconciliationItem(
                entity_urn=item["entity_urn"],
                entity_type=item["entity_type"],
                action_type=item["action_type"],
                reason=item["reason"],
                confidence_score=item["confidence_score"],
                inferred_timestamp_epoch_ms=item.get("inferred_timestamp_epoch_ms"),
                attributes=item.get("attributes", {}),
            )
            for item in raw_actions
        )

        return cls(
            reconciliation_id=row[0],
            gap_id=row[1],
            device_id=row[2],
            domain=row[3],
            reconciled_at_iso=row[4],
            reconciled_at_epoch_ms=row[5],
            entities_sustained_count=row[6],
            entities_terminated_count=row[7],
            entities_staled_count=row[8],
            entities_spawned_count=row[9],
            confidence_discount_pct=row[10],
            actions=actions,
            scan_proves_safe=bool(row[12]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes record to dictionary."""
        return {
            "reconciliation_id": self.reconciliation_id,
            "gap_id": self.gap_id,
            "device_id": self.device_id,
            "domain": self.domain,
            "reconciled_at_iso": self.reconciled_at_iso,
            "reconciled_at_epoch_ms": self.reconciled_at_epoch_ms,
            "entities_sustained_count": self.entities_sustained_count,
            "entities_terminated_count": self.entities_terminated_count,
            "entities_staled_count": self.entities_staled_count,
            "entities_spawned_count": self.entities_spawned_count,
            "confidence_discount_pct": self.confidence_discount_pct,
            "actions": [a.to_dict() for a in self.actions],
            "scan_proves_safe": self.scan_proves_safe,
        }

    def summary(self) -> str:
        """Human-readable summary of the reconciliation record."""
        return (
            f"Reconciliation [{self.reconciliation_id[:8]}]: Gap {self.gap_id[:8]} ({self.domain}) "
            f"-> {self.entities_sustained_count} sustained, {self.entities_terminated_count} term, "
            f"{self.entities_staled_count} stale, {self.entities_spawned_count} spawned "
            f"(discount: {self.confidence_discount_pct:.1%})"
        )


class CollectorGapDetector:
    """Detects and categorizes time intervals where telemetry collectors stopped reporting."""

    def __init__(
        self,
        domain_cadences: Optional[Dict[str, int]] = None,
        tolerance_multiplier: float = 2.0,
    ) -> None:
        """Initialize detector with optional custom cadences and tolerance multiplier."""
        self.cadences = dict(DOMAIN_DEFAULT_CADENCE_MS)
        if domain_cadences:
            self.cadences.update(domain_cadences)
        self.tolerance_multiplier = max(1.1, tolerance_multiplier)

    def get_cadence(self, domain: str) -> int:
        """Returns expected nominal polling cadence in milliseconds for a domain."""
        return self.cadences.get(domain, DEFAULT_FALLBACK_CADENCE_MS)

    def classify_gap(self, duration_ms: int, cadence_ms: int) -> GapClassification:
        """Determines the semantic classification of a gap based on duration and expected cadence."""
        if duration_ms >= 300000:  # >= 5 minutes
            return GapClassification.PROLONGED_OUTAGE
        elif duration_ms >= 60000:  # >= 1 minute (typical sleep/wake interval)
            return GapClassification.SYSTEM_SLEEP_WAKE
        elif duration_ms >= 30000 or duration_ms >= cadence_ms * 4:
            return GapClassification.COLLECTOR_TIMEOUT
        elif duration_ms >= cadence_ms * 2:
            return GapClassification.MINOR_JITTER
        return GapClassification.MINOR_JITTER

    def detect_gap(
        self,
        prev_epoch_ms: int,
        curr_epoch_ms: int,
        collector_id: str,
        device_id: str,
        domain: str,
        expected_cadence_ms: Optional[int] = None,
        detected_at_iso: Optional[str] = None,
    ) -> Optional[CollectorGap]:
        """Detects whether a gap occurred between two observation timestamps.

        Returns a CollectorGap if duration >= cadence * tolerance, else None.
        """
        if curr_epoch_ms <= prev_epoch_ms:
            return None

        cadence = expected_cadence_ms or self.get_cadence(domain)
        duration_ms = curr_epoch_ms - prev_epoch_ms
        threshold_ms = int(cadence * self.tolerance_multiplier)

        if duration_ms < threshold_ms:
            # Within acceptable timing jitter window
            return None

        classification = self.classify_gap(duration_ms, cadence)
        now_iso = detected_at_iso or datetime.now(timezone.utc).isoformat()
        gap_id = f"gap-{uuid.uuid4().hex[:12]}"

        return CollectorGap(
            gap_id=gap_id,
            collector_id=collector_id,
            device_id=device_id,
            domain=domain,
            gap_start_epoch_ms=prev_epoch_ms,
            gap_end_epoch_ms=curr_epoch_ms,
            gap_duration_ms=duration_ms,
            expected_cadence_ms=cadence,
            gap_classification=classification.value,
            detected_at_iso=now_iso,
            scan_proves_safe=False,
        )


class SystemStateReconciler:
    """Performs state healing and entity reconciliation across an observed collector gap."""

    def __init__(
        self,
        ephemeral_domains: Optional[Set[str]] = None,
        max_discount_pct: float = 0.50,
    ) -> None:
        """Initialize reconciler with ephemeral domains and confidence discount caps."""
        self.ephemeral_domains = ephemeral_domains or {"proc"}
        self.max_discount_pct = max_discount_pct

    def calculate_confidence_discount(self, gap_duration_ms: int) -> float:
        """Calculates epistemic confidence discount percentage based on gap duration."""
        # e.g., 5% base discount + 5% per 30 seconds of gap, capped at max_discount_pct
        seconds = gap_duration_ms / 1000.0
        calculated = 0.05 + (seconds / 30.0) * 0.05
        return round(min(self.max_discount_pct, max(0.05, calculated)), 4)

    def reconcile_state(
        self,
        gap: CollectorGap,
        pre_gap_entities: Sequence[TwinEntity] | Dict[str, TwinEntity],
        post_gap_entities: Sequence[TwinEntity] | Dict[str, TwinEntity],
        reconciled_at_iso: Optional[str] = None,
    ) -> StateReconciliationRecord:
        """Reconciles entity population between pre-gap and post-gap observations."""
        pre_map: Dict[str, TwinEntity] = (
            {e.entity_id: e for e in pre_gap_entities}
            if isinstance(pre_gap_entities, (list, tuple))
            else dict(pre_gap_entities)
        )
        post_map: Dict[str, TwinEntity] = (
            {e.entity_id: e for e in post_gap_entities}
            if isinstance(post_gap_entities, (list, tuple))
            else dict(post_gap_entities)
        )

        pre_urns = set(pre_map.keys())
        post_urns = set(post_map.keys())

        sustained_urns = pre_urns & post_urns
        missing_urns = pre_urns - post_urns
        spawned_urns = post_urns - pre_urns

        discount_pct = self.calculate_confidence_discount(gap.gap_duration_ms)
        now_iso = reconciled_at_iso or datetime.now(timezone.utc).isoformat()
        now_epoch_ms = gap.gap_end_epoch_ms
        inferred_exit_time = gap.gap_start_epoch_ms + (gap.gap_duration_ms // 2)

        actions: List[ReconciliationItem] = []
        sustained_count = 0
        terminated_count = 0
        staled_count = 0
        spawned_count = 0

        # 1. Process sustained entities: present both before and after gap
        for urn in sorted(sustained_urns):
            post_e = post_map[urn]
            base_conf = getattr(post_e, "confidence_score", post_e.attributes.get("confidence_score", 1.0))
            discounted_conf = max(0.1, round(base_conf * (1.0 - discount_pct), 3))
            actions.append(
                ReconciliationItem(
                    entity_urn=urn,
                    entity_type=post_e.entity_type.value if hasattr(post_e.entity_type, "value") else str(post_e.entity_type),
                    action_type=ReconciliationActionType.SUSTAINED_ACROSS_GAP.value,
                    reason=f"Sustained across {gap.gap_duration_ms}ms gap; confidence discounted by {discount_pct:.1%}",
                    confidence_score=discounted_conf,
                    attributes={"pre_gap_confidence": base_conf},
                )
            )
            sustained_count += 1

        # 2. Process missing entities: present before gap, missing after gap
        for urn in sorted(missing_urns):
            pre_e = pre_map[urn]
            etype_str = pre_e.entity_type.value if hasattr(pre_e.entity_type, "value") else str(pre_e.entity_type)
            is_ephemeral = (
                pre_e.entity_type in (TwinEntityType.PROCESS, TwinEntityType.NETWORK_SOCKET)
                or urn.startswith("urn:systemmind:proc:")
                or urn.startswith("urn:systemmind:socket:")
            )

            if is_ephemeral:
                # Ephemeral entity terminated during the gap
                actions.append(
                    ReconciliationItem(
                        entity_urn=urn,
                        entity_type=etype_str,
                        action_type=ReconciliationActionType.TERMINATED_DURING_GAP.value,
                        reason=f"Ephemeral resource disappeared during {gap.gap_duration_ms}ms gap; marked terminated",
                        confidence_score=0.9,
                        inferred_timestamp_epoch_ms=inferred_exit_time,
                        attributes={"inferred_exit_window_ms": gap.gap_duration_ms},
                    )
                )
                terminated_count += 1
            else:
                # Persistent entity marked stale pending re-observation
                actions.append(
                    ReconciliationItem(
                        entity_urn=urn,
                        entity_type=etype_str,
                        action_type=ReconciliationActionType.MARKED_STALE_PENDING_CONFIRMATION.value,
                        reason=f"Persistent resource unobserved after {gap.gap_duration_ms}ms gap; marked stale pending confirmation",
                        confidence_score=0.5,
                        attributes={"gap_duration_ms": gap.gap_duration_ms},
                    )
                )
                staled_count += 1

        # 3. Process spawned entities: new post-gap entities not present pre-gap
        for urn in sorted(spawned_urns):
            post_e = post_map[urn]
            post_conf = getattr(post_e, "confidence_score", post_e.attributes.get("confidence_score", 1.0))
            actions.append(
                ReconciliationItem(
                    entity_urn=urn,
                    entity_type=post_e.entity_type.value if hasattr(post_e.entity_type, "value") else str(post_e.entity_type),
                    action_type=ReconciliationActionType.SPAWNED_OR_ATTACHED_DURING_GAP.value,
                    reason=f"Newly discovered post-gap; spawned or attached during {gap.gap_duration_ms}ms window",
                    confidence_score=post_conf,
                    inferred_timestamp_epoch_ms=inferred_exit_time,
                )
            )
            spawned_count += 1

        reconciliation_id = f"recon-{uuid.uuid4().hex[:12]}"

        return StateReconciliationRecord(
            reconciliation_id=reconciliation_id,
            gap_id=gap.gap_id,
            device_id=gap.device_id,
            domain=gap.domain,
            reconciled_at_iso=now_iso,
            reconciled_at_epoch_ms=now_epoch_ms,
            entities_sustained_count=sustained_count,
            entities_terminated_count=terminated_count,
            entities_staled_count=staled_count,
            entities_spawned_count=spawned_count,
            confidence_discount_pct=discount_pct,
            actions=tuple(actions),
            scan_proves_safe=False,
        )


class StateReconciliationManager:
    """Manages persistence of collector gaps and reconciliation audit records in SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize manager with an active SQLite database connection."""
        self.conn = conn
        self.detector = CollectorGapDetector()
        self.reconciler = SystemStateReconciler()

    def record_gap(self, gap: CollectorGap) -> str:
        """Persists a detected collector gap into the collector_gaps table."""
        insert_sql = """
            INSERT INTO collector_gaps (
                gap_id, collector_id, device_id, domain,
                gap_start_epoch_ms, gap_end_epoch_ms, gap_duration_ms,
                expected_cadence_ms, gap_classification, detected_at_iso,
                scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(insert_sql, gap.to_sqlite_params())
        return gap.gap_id

    def record_reconciliation(self, record: StateReconciliationRecord) -> str:
        """Persists a reconciliation audit record into state_reconciliation_records."""
        insert_sql = """
            INSERT INTO state_reconciliation_records (
                reconciliation_id, gap_id, device_id, domain,
                reconciled_at_iso, reconciled_at_epoch_ms,
                entities_sustained_count, entities_terminated_count,
                entities_staled_count, entities_spawned_count,
                confidence_discount_pct, actions_json, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(insert_sql, record.to_sqlite_params())
        return record.reconciliation_id

    def reconcile_and_record(
        self,
        gap: CollectorGap,
        pre_gap_entities: Sequence[TwinEntity] | Dict[str, TwinEntity],
        post_gap_entities: Sequence[TwinEntity] | Dict[str, TwinEntity],
    ) -> StateReconciliationRecord:
        """Reconciles states across a gap and commits both gap and reconciliation records."""
        # Ensure gap is recorded first
        if not self.get_gap(gap.gap_id):
            self.record_gap(gap)

        record = self.reconciler.reconcile_state(gap, pre_gap_entities, post_gap_entities)
        self.record_reconciliation(record)
        return record

    def get_gap(self, gap_id: str) -> Optional[CollectorGap]:
        """Retrieves a single collector gap by ID."""
        cursor = self.conn.execute("SELECT * FROM collector_gaps WHERE gap_id = ?;", (gap_id,))
        row = cursor.fetchone()
        return CollectorGap.from_sqlite_row(row) if row else None

    def get_reconciliation(self, reconciliation_id: str) -> Optional[StateReconciliationRecord]:
        """Retrieves a single reconciliation record by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM state_reconciliation_records WHERE reconciliation_id = ?;",
            (reconciliation_id,),
        )
        row = cursor.fetchone()
        return StateReconciliationRecord.from_sqlite_row(row) if row else None

    def query_gaps_for_device(
        self,
        device_id: str,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[CollectorGap]:
        """Retrieves historical gaps for a device in chronological order."""
        if domain:
            query = """
                SELECT * FROM collector_gaps
                WHERE device_id = ? AND domain = ?
                ORDER BY gap_end_epoch_ms DESC
                LIMIT ?;
            """
            cursor = self.conn.execute(query, (device_id, domain, limit))
        else:
            query = """
                SELECT * FROM collector_gaps
                WHERE device_id = ?
                ORDER BY gap_end_epoch_ms DESC
                LIMIT ?;
            """
            cursor = self.conn.execute(query, (device_id, limit))
        return [CollectorGap.from_sqlite_row(r) for r in cursor.fetchall()]

    def query_reconciliations_for_gap(self, gap_id: str) -> List[StateReconciliationRecord]:
        """Retrieves reconciliation records for a specific gap."""
        cursor = self.conn.execute(
            "SELECT * FROM state_reconciliation_records WHERE gap_id = ? ORDER BY reconciled_at_epoch_ms ASC;",
            (gap_id,),
        )
        return [StateReconciliationRecord.from_sqlite_row(r) for r in cursor.fetchall()]

    def apply_reconciliation_to_graph(
        self,
        record: StateReconciliationRecord,
        graph: DigitalTwinGraph,
    ) -> None:
        """Applies reconciliation decisions directly to an in-memory DigitalTwinGraph."""
        for item in record.actions:
            if item.action_type == ReconciliationActionType.TERMINATED_DURING_GAP.value:
                # Remove or mark terminated in graph
                if graph.get_entity(item.entity_urn):
                    graph.remove_entity(item.entity_urn)
            elif item.action_type == ReconciliationActionType.MARKED_STALE_PENDING_CONFIRMATION.value:
                # Mark stale in graph
                entity = graph.get_entity(item.entity_urn)
                if entity:
                    # Update entity attributes with stale marker
                    mutated_attrs = dict(entity.attributes)
                    mutated_attrs["is_stale"] = True
                    mutated_attrs["stale_reason"] = "COLLECTOR_GAP"
                    mutated_attrs["confidence_score"] = item.confidence_score
                    staled_entity = TwinEntity(
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        ownership=entity.ownership,
                        attributes=mutated_attrs,
                        created_at=entity.created_at,
                        updated_at=entity.updated_at,
                        provenance_source=entity.provenance_source,
                        is_stale=True,
                    )
                    graph.add_entity(staled_entity)
            elif item.action_type == ReconciliationActionType.SUSTAINED_ACROSS_GAP.value:
                # Update confidence score
                entity = graph.get_entity(item.entity_urn)
                if entity:
                    mutated_attrs = dict(entity.attributes)
                    mutated_attrs["confidence_score"] = item.confidence_score
                    updated_entity = TwinEntity(
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        ownership=entity.ownership,
                        attributes=mutated_attrs,
                        created_at=entity.created_at,
                        updated_at=entity.updated_at,
                        provenance_source=entity.provenance_source,
                        is_stale=entity.is_stale,
                    )
                    graph.add_entity(updated_entity)
