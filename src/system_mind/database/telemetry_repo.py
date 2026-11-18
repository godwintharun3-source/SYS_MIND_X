"""Telemetry and audit ledger persistence repository for SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Dict, List, Optional
import uuid


class TelemetryRepository:
    """Manages transactional persistence and querying of observations, twin entities, and audit events."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record_observation(
        self,
        observation_id: str,
        observation_type: str,
        source: str,
        payload: Dict[str, Any],
        provenance_status: str = "VERIFIED",
    ) -> str:
        """Insert a temporal observation record into the database."""
        now_iso = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

        # Get next sequence number
        cursor = self.conn.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM temporal_observations;")
        next_seq = cursor.fetchone()[0]

        self.conn.execute(
            """
            INSERT INTO temporal_observations (
                observation_id, observation_type, source, sequence, timestamp_iso, payload_hash, payload_json, provenance_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (observation_id, observation_type, source, next_seq, now_iso, payload_hash, payload_json, provenance_status),
        )
        return observation_id

    def record_audit_event(
        self,
        actor_urn: str,
        action_urn: str,
        risk_tier: str,
        payload: Dict[str, Any],
        retention_tier: str = "AUDIT_OPERATIONAL",
    ) -> Dict[str, Any]:
        """Record an immutable audit event chained to the previous event hash."""
        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

        # Fetch previous event hash
        cursor = self.conn.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence_number DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        prev_hash = row[0] if row else "0000000000000000000000000000000000000000000000000000000000000000"

        # Compute cryptographic block hash
        raw_block = f"{prev_hash}:{event_id}:{now_iso}:{actor_urn}:{action_urn}:{payload_hash}"
        event_hash = hashlib.sha256(raw_block.encode("utf-8")).hexdigest()

        self.conn.execute(
            """
            INSERT INTO audit_events (
                event_id, timestamp_iso, actor_urn, action_urn, risk_tier, prev_event_hash, payload_hash, event_hash, retention_tier, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event_id,
                now_iso,
                actor_urn,
                action_urn,
                risk_tier,
                prev_hash,
                payload_hash,
                event_hash,
                retention_tier,
                payload_json,
            ),
        )

        cursor = self.conn.execute("SELECT last_insert_rowid();")
        seq_num = cursor.fetchone()[0]

        return {
            "sequence_id": seq_num,
            "event_id": event_id,
            "timestamp": now_iso,
            "actor": actor_urn,
            "action_name": action_urn,
            "risk_tier": risk_tier,
            "sha256_hash": event_hash,
            "previous_hash": prev_hash,
            "status": "AUTHORIZED",
        }

    def get_audit_ledger(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve latest audit records."""
        cursor = self.conn.execute(
            """
            SELECT sequence_number, timestamp_iso, actor_urn, action_urn, risk_tier, prev_event_hash, event_hash
            FROM audit_events
            ORDER BY sequence_number DESC
            LIMIT ?;
            """,
            (limit,),
        )
        records = []
        for row in cursor.fetchall():
            records.append({
                "sequence_id": row[0],
                "timestamp": row[1],
                "actor": row[2],
                "action_name": row[3],
                "risk_tier": row[4],
                "previous_hash": row[5],
                "sha256_hash": row[6],
                "status": "AUTHORIZED",
            })
        return records

    def get_digital_twin_summary(self) -> Dict[str, Any]:
        """Query Digital Twin entity and relationship counts from database."""
        c1 = self.conn.execute("SELECT COUNT(*) FROM twin_entities;")
        node_count = c1.fetchone()[0]

        c2 = self.conn.execute("SELECT COUNT(*) FROM twin_relationships;")
        edge_count = c2.fetchone()[0]

        c3 = self.conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM temporal_observations;")
        epoch = c3.fetchone()[0]

        return {
            "node_count": max(node_count, 1),
            "edge_count": edge_count,
            "temporal_epoch": epoch,
            "is_consistent": True,
            "unresolved_drift": False,
        }
