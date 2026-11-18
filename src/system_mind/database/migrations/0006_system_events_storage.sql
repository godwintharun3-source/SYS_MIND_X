-- Migration: 0006_system_events_storage
-- Description: Append-only system event storage with cryptographic hash chaining and immutability triggers

-- UP
CREATE TABLE IF NOT EXISTS system_events (
    sequence_number INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    device_id TEXT NOT NULL,
    entity_urn TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp_iso TEXT NOT NULL,
    timestamp_epoch_ms INTEGER NOT NULL,
    correlation_id TEXT,
    causation_id TEXT,
    prev_event_hash TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    component_ownership TEXT NOT NULL,
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_system_events_event_id ON system_events (event_id);
CREATE INDEX IF NOT EXISTS idx_system_events_entity_urn ON system_events (entity_urn);
CREATE INDEX IF NOT EXISTS idx_system_events_event_type ON system_events (event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_timestamp ON system_events (timestamp_epoch_ms);
CREATE INDEX IF NOT EXISTS idx_system_events_correlation ON system_events (correlation_id);
CREATE INDEX IF NOT EXISTS idx_system_events_ownership ON system_events (component_ownership);

-- Immutability triggers enforcing append-only semantics
CREATE TRIGGER IF NOT EXISTS trg_system_events_prevent_update
BEFORE UPDATE ON system_events
BEGIN
    SELECT RAISE(ABORT, 'System events are append-only: UPDATE is prohibited');
END;

CREATE TRIGGER IF NOT EXISTS trg_system_events_prevent_delete
BEFORE DELETE ON system_events
BEGIN
    SELECT RAISE(ABORT, 'System events are append-only: DELETE is prohibited');
END;

-- DOWN
DROP TRIGGER IF EXISTS trg_system_events_prevent_delete;
DROP TRIGGER IF EXISTS trg_system_events_prevent_update;
DROP INDEX IF EXISTS idx_system_events_ownership;
DROP INDEX IF EXISTS idx_system_events_correlation;
DROP INDEX IF EXISTS idx_system_events_timestamp;
DROP INDEX IF EXISTS idx_system_events_event_type;
DROP INDEX IF EXISTS idx_system_events_entity_urn;
DROP INDEX IF EXISTS idx_system_events_event_id;
DROP TABLE IF EXISTS system_events;
