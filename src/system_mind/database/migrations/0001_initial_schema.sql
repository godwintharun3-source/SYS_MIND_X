-- Migration: 0001_initial_schema
-- Description: Core tables for audit ledger, twin entities, relationships, and temporal observations

-- UP
CREATE TABLE IF NOT EXISTS audit_events (
    sequence_number INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    timestamp_iso TEXT NOT NULL,
    actor_urn TEXT NOT NULL,
    action_urn TEXT NOT NULL,
    risk_tier TEXT NOT NULL,
    prev_event_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    retention_tier TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_events_event_id ON audit_events (event_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events (timestamp_iso);

CREATE TABLE IF NOT EXISTS twin_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    ownership TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    attributes_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_twin_entities_type ON twin_entities (entity_type);
CREATE INDEX IF NOT EXISTS idx_twin_entities_ownership ON twin_entities (ownership);

CREATE TABLE IF NOT EXISTS twin_relationships (
    relationship_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES twin_entities(entity_id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES twin_entities(entity_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_twin_relationships_source ON twin_relationships (source_id);
CREATE INDEX IF NOT EXISTS idx_twin_relationships_target ON twin_relationships (target_id);

CREATE TABLE IF NOT EXISTS temporal_observations (
    observation_id TEXT PRIMARY KEY,
    observation_type TEXT NOT NULL,
    source TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp_iso TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    provenance_status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_temporal_observations_sequence ON temporal_observations (sequence);
CREATE INDEX IF NOT EXISTS idx_temporal_observations_type ON temporal_observations (observation_type);

-- DOWN
DROP TABLE IF EXISTS temporal_observations;
DROP TABLE IF EXISTS twin_relationships;
DROP TABLE IF EXISTS twin_entities;
DROP TABLE IF EXISTS audit_events;
