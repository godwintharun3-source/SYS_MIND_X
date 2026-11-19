-- Migration: 0009_observation_deltas
-- Description: Indexed delta tracking and change detection between consecutive system observations

-- UP
CREATE TABLE IF NOT EXISTS observation_deltas (
    delta_id TEXT PRIMARY KEY,
    entity_urn TEXT NOT NULL,
    device_id TEXT NOT NULL,
    from_record_id TEXT NOT NULL REFERENCES system_observation_records(record_id) ON DELETE CASCADE,
    to_record_id TEXT NOT NULL REFERENCES system_observation_records(record_id) ON DELETE CASCADE,
    from_sequence INTEGER NOT NULL,
    to_sequence INTEGER NOT NULL,
    from_epoch_ms INTEGER NOT NULL,
    to_epoch_ms INTEGER NOT NULL,
    time_delta_ms INTEGER NOT NULL,
    has_changed INTEGER NOT NULL CHECK (has_changed IN (0, 1)),
    change_classification TEXT NOT NULL,
    added_keys_json TEXT NOT NULL DEFAULT '[]',
    removed_keys_json TEXT NOT NULL DEFAULT '[]',
    modified_keys_json TEXT NOT NULL DEFAULT '{}',
    change_count INTEGER NOT NULL DEFAULT 0,
    detected_at_iso TEXT NOT NULL,
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_obs_deltas_entity_urn ON observation_deltas (entity_urn);
CREATE INDEX IF NOT EXISTS idx_obs_deltas_device_id ON observation_deltas (device_id);
CREATE INDEX IF NOT EXISTS idx_obs_deltas_has_changed ON observation_deltas (has_changed);
CREATE INDEX IF NOT EXISTS idx_obs_deltas_classification ON observation_deltas (change_classification);
CREATE INDEX IF NOT EXISTS idx_obs_deltas_to_epoch_ms ON observation_deltas (to_epoch_ms);
CREATE INDEX IF NOT EXISTS idx_obs_deltas_from_to_seq ON observation_deltas (entity_urn, from_sequence, to_sequence);

-- DOWN
DROP INDEX IF EXISTS idx_obs_deltas_from_to_seq;
DROP INDEX IF EXISTS idx_obs_deltas_to_epoch_ms;
DROP INDEX IF EXISTS idx_obs_deltas_classification;
DROP INDEX IF EXISTS idx_obs_deltas_has_changed;
DROP INDEX IF EXISTS idx_obs_deltas_device_id;
DROP INDEX IF EXISTS idx_obs_deltas_entity_urn;
DROP TABLE IF EXISTS observation_deltas;
