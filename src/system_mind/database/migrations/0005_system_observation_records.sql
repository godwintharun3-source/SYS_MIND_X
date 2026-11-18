-- Migration: 0005_system_observation_records
-- Description: Timestamped system observation records for temporal digital twin

-- UP
CREATE TABLE IF NOT EXISTS system_observation_records (
    record_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    entity_urn TEXT NOT NULL,
    collector_id TEXT NOT NULL,
    observation_type TEXT NOT NULL,
    observed_at_iso TEXT NOT NULL,
    observed_at_epoch_ms INTEGER NOT NULL,
    source_monotonic_ns INTEGER,
    source_clock TEXT NOT NULL DEFAULT 'mach_continuous_time',
    confidence_score REAL NOT NULL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    confidence_tier TEXT NOT NULL,
    provenance_status TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    ttl_seconds REAL NOT NULL DEFAULT 60.0,
    is_mock INTEGER NOT NULL DEFAULT 0 CHECK (is_mock IN (0, 1)),
    observation_status TEXT NOT NULL DEFAULT 'ACTUAL',
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_obs_records_entity_seq ON system_observation_records (entity_urn, sequence_number);
CREATE INDEX IF NOT EXISTS idx_obs_records_observed_at ON system_observation_records (observed_at_iso);
CREATE INDEX IF NOT EXISTS idx_obs_records_epoch_ms ON system_observation_records (observed_at_epoch_ms);
CREATE INDEX IF NOT EXISTS idx_obs_records_collector ON system_observation_records (collector_id);
CREATE INDEX IF NOT EXISTS idx_obs_records_device ON system_observation_records (device_id);
CREATE INDEX IF NOT EXISTS idx_obs_records_status ON system_observation_records (observation_status, is_mock);

-- DOWN
DROP INDEX IF EXISTS idx_obs_records_status;
DROP INDEX IF EXISTS idx_obs_records_device;
DROP INDEX IF EXISTS idx_obs_records_collector;
DROP INDEX IF EXISTS idx_obs_records_epoch_ms;
DROP INDEX IF EXISTS idx_obs_records_observed_at;
DROP INDEX IF EXISTS idx_obs_records_entity_seq;
DROP TABLE IF EXISTS system_observation_records;
