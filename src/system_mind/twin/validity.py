"""Temporal validity windows, freshness scoring, and stale-observation markers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import TwinEntity
from system_mind.twin.temporal import FreshnessState


class StaleReason(str, Enum):
    """Enumeration of causal triggers for marking an entity observation stale."""

    TTL_EXPIRED = "TTL_EXPIRED"
    UNOBSERVED_IN_SCAN = "UNOBSERVED_IN_SCAN"
    PROCESS_EXIT = "PROCESS_EXIT"
    VOLUME_UNMOUNTED = "VOLUME_UNMOUNTED"
    SERVICE_STOPPED = "SERVICE_STOPPED"
    NETWORK_DISCONNECT = "NETWORK_DISCONNECT"
    MANUAL_INVALIDATION = "MANUAL_INVALIDATION"


# Domain-specific default (TTL in seconds, max_staleness in seconds)
DOMAIN_DEFAULT_TTLS: Dict[str, Tuple[float, float]] = {
    "proc": (15.0, 45.0),
    "cpu": (30.0, 90.0),
    "mem": (30.0, 90.0),
    "gpu": (30.0, 90.0),
    "battery": (30.0, 90.0),
    "net": (45.0, 120.0),
    "svc": (120.0, 600.0),
    "vol": (300.0, 1800.0),
    "file": (300.0, 1800.0),
    "app": (3600.0, 86400.0),
    "kernel": (86400.0, 604800.0),
    "host": (86400.0, 604800.0),
}
DEFAULT_FALLBACK_TTL: Tuple[float, float] = (60.0, 300.0)


@dataclass(frozen=True)
class EntityTemporalValidity:
    """Strongly typed model for entity temporal validity, decay scores, and staleness markers.

    Observational freshness reflects measurement age, never software safety.
    Strictly enforces Charter Invariant SC-03: scan_proves_safe = False.
    """

    entity_urn: str
    device_id: str
    domain: str
    last_observed_at_iso: str
    last_observed_at_epoch_ms: int
    valid_until_epoch_ms: int
    ttl_seconds: float = 60.0
    freshness_state: str = FreshnessState.FRESH.value
    staleness_score: float = 0.0
    is_stale: bool = False
    stale_reason: Optional[str] = None
    marked_stale_at_iso: Optional[str] = None
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        """Enforces architectural invariants and validity bounds."""
        # Invariant SC-03: scan_proves_safe is NEVER true
        if self.scan_proves_safe:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")

        # Invariant INV-VAL-03: staleness score bounded in [0.0, 1.0]
        if not (0.0 <= self.staleness_score <= 1.0):
            raise ValueError(
                f"Staleness Score Out of Bounds: {self.staleness_score}. Must be between 0.0 and 1.0."
            )

        # Invariant INV-VAL-02: valid_until must be >= last_observed_at
        if self.valid_until_epoch_ms < self.last_observed_at_epoch_ms:
            raise ValueError(
                f"Temporal Validity Inversion: valid_until_epoch_ms ({self.valid_until_epoch_ms}) "
                f"cannot be earlier than last_observed_at_epoch_ms ({self.last_observed_at_epoch_ms})."
            )

    def to_sqlite_params(self) -> Tuple[Any, ...]:
        """Serializes record fields to positional parameters for SQLite insertion/upsert."""
        return (
            self.entity_urn,
            self.device_id,
            self.domain,
            self.last_observed_at_iso,
            self.last_observed_at_epoch_ms,
            self.valid_until_epoch_ms,
            float(self.ttl_seconds),
            str(self.freshness_state),
            float(self.staleness_score),
            1 if self.is_stale else 0,
            self.stale_reason,
            self.marked_stale_at_iso,
            0,  # scan_proves_safe is always 0
        )

    @classmethod
    def from_sqlite_row(cls, row: Tuple[Any, ...] | sqlite3.Row) -> EntityTemporalValidity:
        """Constructs an EntityTemporalValidity instance from a raw SQLite query row."""
        return cls(
            entity_urn=row[0],
            device_id=row[1],
            domain=row[2],
            last_observed_at_iso=row[3],
            last_observed_at_epoch_ms=row[4],
            valid_until_epoch_ms=row[5],
            ttl_seconds=float(row[6]),
            freshness_state=str(row[7]),
            staleness_score=float(row[8]),
            is_stale=bool(row[9]),
            stale_reason=row[10],
            marked_stale_at_iso=row[11],
            scan_proves_safe=bool(row[12]),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes record to a canonical JSON-compatible dictionary."""
        return {
            "entity_urn": self.entity_urn,
            "device_id": self.device_id,
            "domain": self.domain,
            "last_observed_at_iso": self.last_observed_at_iso,
            "last_observed_at_epoch_ms": self.last_observed_at_epoch_ms,
            "valid_until_epoch_ms": self.valid_until_epoch_ms,
            "ttl_seconds": self.ttl_seconds,
            "freshness_state": self.freshness_state,
            "staleness_score": self.staleness_score,
            "is_stale": self.is_stale,
            "stale_reason": self.stale_reason,
            "marked_stale_at_iso": self.marked_stale_at_iso,
            "scan_proves_safe": self.scan_proves_safe,
        }


class TemporalValidityManager:
    """Manages entity temporal validity, decay evaluation, and non-destructive staleness markers."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the manager with an active SQLite connection."""
        self.conn = conn

    @staticmethod
    def extract_domain_from_urn(urn: str) -> str:
        """Extracts the entity domain from a canonical URN (urn:systemmind:<domain>:<id>)."""
        parts = urn.split(":")
        if len(parts) >= 3 and parts[0] == "urn" and parts[1] == "systemmind":
            return parts[2]
        return "unknown"

    @classmethod
    def get_domain_ttls(cls, domain: str) -> Tuple[float, float]:
        """Returns the (ttl_seconds, max_staleness_seconds) for a domain."""
        return DOMAIN_DEFAULT_TTLS.get(domain, DEFAULT_FALLBACK_TTL)

    @classmethod
    def evaluate_freshness(
        cls,
        last_observed_epoch_ms: int,
        current_epoch_ms: int,
        ttl_seconds: float,
        max_staleness_seconds: float,
    ) -> Tuple[FreshnessState, float]:
        """Evaluates decay score and FreshnessState from elapsed time."""
        elapsed_seconds = max(0.0, (current_epoch_ms - last_observed_epoch_ms) / 1000.0)
        ttl = max(0.001, ttl_seconds)
        max_stale = max(ttl, max_staleness_seconds)

        if elapsed_seconds <= (ttl / 2.0):
            state = FreshnessState.FRESH
            score = (elapsed_seconds / ttl) * 0.5
        elif elapsed_seconds <= ttl:
            state = FreshnessState.AGING
            half_window = ttl / 2.0
            score = 0.5 + 0.3 * ((elapsed_seconds - (ttl / 2.0)) / half_window)
        elif elapsed_seconds <= max_stale:
            state = FreshnessState.STALE
            stale_window = max(0.001, max_stale - ttl)
            score = 0.8 + 0.2 * ((elapsed_seconds - ttl) / stale_window)
        else:
            state = FreshnessState.EXPIRED
            score = 1.0

        return state, round(min(1.0, max(0.0, score)), 4)

    def record_entity_observation(
        self,
        entity_urn: str,
        device_id: str,
        observed_at_iso: str,
        observed_at_epoch_ms: int,
        ttl_seconds: Optional[float] = None,
        domain: Optional[str] = None,
    ) -> EntityTemporalValidity:
        """Records a new or refreshed observation for an entity, opening a valid temporal window.

        Reversible Freshness: If this entity was previously marked stale, this call clears
        is_stale, clears stale_reason, sets freshness_state to FRESH, and extends validity.
        """
        resolved_domain = domain or self.extract_domain_from_urn(entity_urn)
        default_ttl, _ = self.get_domain_ttls(resolved_domain)
        effective_ttl = ttl_seconds if ttl_seconds is not None and ttl_seconds > 0 else default_ttl

        valid_until_epoch_ms = observed_at_epoch_ms + int(effective_ttl * 1000)

        record = EntityTemporalValidity(
            entity_urn=entity_urn,
            device_id=device_id,
            domain=resolved_domain,
            last_observed_at_iso=observed_at_iso,
            last_observed_at_epoch_ms=observed_at_epoch_ms,
            valid_until_epoch_ms=valid_until_epoch_ms,
            ttl_seconds=effective_ttl,
            freshness_state=FreshnessState.FRESH.value,
            staleness_score=0.0,
            is_stale=False,
            stale_reason=None,
            marked_stale_at_iso=None,
            scan_proves_safe=False,
        )

        upsert_sql = """
            INSERT INTO entity_temporal_validity (
                entity_urn, device_id, domain, last_observed_at_iso,
                last_observed_at_epoch_ms, valid_until_epoch_ms, ttl_seconds,
                freshness_state, staleness_score, is_stale, stale_reason,
                marked_stale_at_iso, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_urn) DO UPDATE SET
                device_id = excluded.device_id,
                domain = excluded.domain,
                last_observed_at_iso = excluded.last_observed_at_iso,
                last_observed_at_epoch_ms = excluded.last_observed_at_epoch_ms,
                valid_until_epoch_ms = excluded.valid_until_epoch_ms,
                ttl_seconds = excluded.ttl_seconds,
                freshness_state = excluded.freshness_state,
                staleness_score = excluded.staleness_score,
                is_stale = excluded.is_stale,
                stale_reason = excluded.stale_reason,
                marked_stale_at_iso = excluded.marked_stale_at_iso,
                scan_proves_safe = excluded.scan_proves_safe;
        """
        self.conn.execute(upsert_sql, record.to_sqlite_params())
        return record

    def mark_stale(
        self,
        entity_urn: str,
        reason: str | StaleReason,
        marked_at_iso: Optional[str] = None,
        staleness_score: float = 1.0,
    ) -> Optional[EntityTemporalValidity]:
        """Applies a non-destructive stale marker to an existing entity record."""
        current = self.get_validity(entity_urn)
        if current is None:
            return None

        reason_str = reason.value if isinstance(reason, StaleReason) else str(reason)
        iso_ts = marked_at_iso or datetime.now(timezone.utc).isoformat()
        bounded_score = min(1.0, max(0.8, staleness_score))

        update_sql = """
            UPDATE entity_temporal_validity
            SET is_stale = 1,
                stale_reason = ?,
                marked_stale_at_iso = ?,
                freshness_state = ?,
                staleness_score = ?
            WHERE entity_urn = ?;
        """
        self.conn.execute(
            update_sql,
            (reason_str, iso_ts, FreshnessState.STALE.value, bounded_score, entity_urn),
        )

        return self.get_validity(entity_urn)

    def reconcile_missing_entities(
        self,
        observed_urns: Sequence[str],
        domain: str,
        device_id: Optional[str] = None,
        marked_at_iso: Optional[str] = None,
    ) -> List[EntityTemporalValidity]:
        """Marks any currently active entities in the domain as stale if missing from the scan.

        Non-destructive: entities not seen in the latest scan receive is_stale=1 and
        stale_reason=UNOBSERVED_IN_SCAN, but remain in the database.
        """
        observed_set: Set[str] = set(observed_urns)
        iso_ts = marked_at_iso or datetime.now(timezone.utc).isoformat()

        if device_id:
            query = """
                SELECT entity_urn FROM entity_temporal_validity
                WHERE domain = ? AND device_id = ? AND is_stale = 0;
            """
            cursor = self.conn.execute(query, (domain, device_id))
        else:
            query = """
                SELECT entity_urn FROM entity_temporal_validity
                WHERE domain = ? AND is_stale = 0;
            """
            cursor = self.conn.execute(query, (domain,))

        missing_urns = [row[0] for row in cursor.fetchall() if row[0] not in observed_set]
        updated_records: List[EntityTemporalValidity] = []

        for urn in missing_urns:
            updated = self.mark_stale(
                entity_urn=urn,
                reason=StaleReason.UNOBSERVED_IN_SCAN,
                marked_at_iso=iso_ts,
                staleness_score=0.9,
            )
            if updated:
                updated_records.append(updated)

        return updated_records

    def scan_and_update_expired(
        self,
        current_epoch_ms: int,
        device_id: Optional[str] = None,
    ) -> List[EntityTemporalValidity]:
        """Scans all active records whose validity window has expired and transitions their freshness."""
        if device_id:
            query = """
                SELECT * FROM entity_temporal_validity
                WHERE device_id = ? AND is_stale = 0 AND valid_until_epoch_ms < ?;
            """
            cursor = self.conn.execute(query, (device_id, current_epoch_ms))
        else:
            query = """
                SELECT * FROM entity_temporal_validity
                WHERE is_stale = 0 AND valid_until_epoch_ms < ?;
            """
            cursor = self.conn.execute(query, (current_epoch_ms,))

        expired_records: List[EntityTemporalValidity] = []
        rows = cursor.fetchall()
        iso_now = datetime.fromtimestamp(current_epoch_ms / 1000.0, tz=timezone.utc).isoformat()

        for row in rows:
            record = EntityTemporalValidity.from_sqlite_row(row)
            _, max_stale = self.get_domain_ttls(record.domain)
            new_state, score = self.evaluate_freshness(
                last_observed_epoch_ms=record.last_observed_at_epoch_ms,
                current_epoch_ms=current_epoch_ms,
                ttl_seconds=record.ttl_seconds,
                max_staleness_seconds=max_stale,
            )

            is_stale_flag = 1 if new_state in (FreshnessState.STALE, FreshnessState.EXPIRED) else 0
            stale_reason = StaleReason.TTL_EXPIRED.value if is_stale_flag else None

            update_sql = """
                UPDATE entity_temporal_validity
                SET freshness_state = ?,
                    staleness_score = ?,
                    is_stale = ?,
                    stale_reason = COALESCE(stale_reason, ?),
                    marked_stale_at_iso = CASE WHEN is_stale = 0 AND ? = 1 THEN ? ELSE marked_stale_at_iso END
                WHERE entity_urn = ?;
            """
            self.conn.execute(
                update_sql,
                (
                    new_state.value,
                    score,
                    is_stale_flag,
                    stale_reason,
                    is_stale_flag,
                    iso_now,
                    record.entity_urn,
                ),
            )
            updated = self.get_validity(record.entity_urn)
            if updated:
                expired_records.append(updated)

        return expired_records

    def sync_graph_staleness(self, graph: DigitalTwinGraph, current_epoch_ms: int) -> int:
        """Synchronizes is_stale flags from temporal validity into in-memory DigitalTwinGraph entities.

        Returns the number of entities whose stale state was updated.
        """
        updated_count = 0
        iso_now = datetime.fromtimestamp(current_epoch_ms / 1000.0, tz=timezone.utc).isoformat()

        for entity_id, entity in list(graph._entities.items()):
            validity = self.get_validity(entity_id)
            if validity is not None:
                if entity.is_stale != validity.is_stale:
                    graph.update_entity_attributes(
                        entity_id=entity_id,
                        new_attributes={},
                        updated_at=iso_now,
                        is_stale=validity.is_stale,
                    )
                    updated_count += 1
            else:
                # If no validity record exists, check if entity is beyond fallback TTL
                pass

        return updated_count

    def get_validity(self, entity_urn: str) -> Optional[EntityTemporalValidity]:
        """Retrieves an entity temporal validity record by canonical URN."""
        cursor = self.conn.execute(
            "SELECT * FROM entity_temporal_validity WHERE entity_urn = ?;",
            (entity_urn,),
        )
        row = cursor.fetchone()
        return EntityTemporalValidity.from_sqlite_row(row) if row else None

    def list_validity_records(
        self,
        domain: Optional[str] = None,
        is_stale: Optional[bool] = None,
        limit: int = 1000,
    ) -> List[EntityTemporalValidity]:
        """Lists validity records with optional domain and staleness filtering."""
        clauses: List[str] = []
        params: List[Any] = []

        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if is_stale is not None:
            clauses.append("is_stale = ?")
            params.append(1 if is_stale else 0)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM entity_temporal_validity {where} ORDER BY last_observed_at_epoch_ms DESC LIMIT ?;"
        params.append(limit)

        cursor = self.conn.execute(query, tuple(params))
        return [EntityTemporalValidity.from_sqlite_row(row) for row in cursor.fetchall()]

    def list_stale_entities(self, domain: Optional[str] = None) -> List[EntityTemporalValidity]:
        """Convenience method to list all entities currently marked stale."""
        return self.list_validity_records(domain=domain, is_stale=True)

    def list_active_entities(self, domain: Optional[str] = None) -> List[EntityTemporalValidity]:
        """Convenience method to list all entities currently marked active (not stale)."""
        return self.list_validity_records(domain=domain, is_stale=False)
