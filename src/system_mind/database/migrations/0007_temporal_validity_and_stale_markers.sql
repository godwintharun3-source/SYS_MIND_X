-- Migration: 0007_temporal_validity_and_stale_markers
-- Description: Temporal validity intervals, domain TTLs, freshness scoring, and non-destructive stale markers

-- UP
CREATE TABLE IF NOT EXISTS entity_temporal_validity (
    entity_urn TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    last_observed_at_iso TEXT NOT NULL,
    last_observed_at_epoch_ms INTEGER NOT NULL,
    valid_until_epoch_ms INTEGER NOT NULL,
    ttl_seconds REAL NOT NULL DEFAULT 60.0,
    freshness_state TEXT NOT NULL DEFAULT 'FRESH',
    staleness_score REAL NOT NULL DEFAULT 0.0 CHECK (staleness_score >= 0.0 AND staleness_score <= 1.0),
    is_stale INTEGER NOT NULL DEFAULT 0 CHECK (is_stale IN (0, 1)),
    stale_reason TEXT,
    marked_stale_at_iso TEXT,
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_entity_validity_device_id ON entity_temporal_validity (device_id);
CREATE INDEX IF NOT EXISTS idx_entity_validity_domain ON entity_temporal_validity (domain);
CREATE INDEX IF NOT EXISTS idx_entity_validity_valid_until ON entity_temporal_validity (valid_until_epoch_ms);
CREATE INDEX IF NOT EXISTS idx_entity_validity_freshness_state ON entity_temporal_validity (freshness_state);
CREATE INDEX IF NOT EXISTS idx_entity_validity_is_stale ON entity_temporal_validity (is_stale);

-- DOWN
DROP INDEX IF EXISTS idx_entity_validity_is_stale;
DROP INDEX IF EXISTS idx_entity_validity_freshness_state;
DROP INDEX IF EXISTS idx_entity_validity_valid_until;
DROP INDEX IF EXISTS idx_entity_validity_domain;
DROP INDEX IF EXISTS idx_entity_validity_device_id;
DROP TABLE IF EXISTS entity_temporal_validity;
