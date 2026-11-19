-- Migration: 0008_digital_twin_state_snapshots
-- Description: Point-in-time digital twin state snapshots, canonical state digests, and topology comparison

-- UP
CREATE TABLE IF NOT EXISTS digital_twin_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    captured_at_iso TEXT NOT NULL,
    captured_at_epoch_ms INTEGER NOT NULL,
    sequence_number INTEGER NOT NULL,
    trigger_reason TEXT NOT NULL,
    entity_count INTEGER NOT NULL,
    relationship_count INTEGER NOT NULL,
    state_digest TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    relationships_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_twin_snapshots_device_id ON digital_twin_snapshots (device_id);
CREATE INDEX IF NOT EXISTS idx_twin_snapshots_captured_at ON digital_twin_snapshots (captured_at_epoch_ms);
CREATE INDEX IF NOT EXISTS idx_twin_snapshots_sequence ON digital_twin_snapshots (sequence_number);
CREATE INDEX IF NOT EXISTS idx_twin_snapshots_digest ON digital_twin_snapshots (state_digest);

-- DOWN
DROP INDEX IF EXISTS idx_twin_snapshots_digest;
DROP INDEX IF EXISTS idx_twin_snapshots_sequence;
DROP INDEX IF EXISTS idx_twin_snapshots_captured_at;
DROP INDEX IF EXISTS idx_twin_snapshots_device_id;
DROP TABLE IF EXISTS digital_twin_snapshots;
