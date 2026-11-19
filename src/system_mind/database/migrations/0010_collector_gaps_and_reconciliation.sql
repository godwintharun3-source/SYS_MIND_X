-- Migration: 0010_collector_gaps_and_reconciliation
-- Description: Collector gap detection, state reconciliation audit records, and temporal healing

-- UP
CREATE TABLE IF NOT EXISTS collector_gaps (
    gap_id TEXT PRIMARY KEY,
    collector_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    gap_start_epoch_ms INTEGER NOT NULL,
    gap_end_epoch_ms INTEGER NOT NULL,
    gap_duration_ms INTEGER NOT NULL,
    expected_cadence_ms INTEGER NOT NULL,
    gap_classification TEXT NOT NULL,
    detected_at_iso TEXT NOT NULL,
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_collector_gaps_collector_id ON collector_gaps (collector_id);
CREATE INDEX IF NOT EXISTS idx_collector_gaps_device_id ON collector_gaps (device_id);
CREATE INDEX IF NOT EXISTS idx_collector_gaps_domain ON collector_gaps (domain);
CREATE INDEX IF NOT EXISTS idx_collector_gaps_duration ON collector_gaps (gap_duration_ms);
CREATE INDEX IF NOT EXISTS idx_collector_gaps_start_end ON collector_gaps (gap_start_epoch_ms, gap_end_epoch_ms);

CREATE TABLE IF NOT EXISTS state_reconciliation_records (
    reconciliation_id TEXT PRIMARY KEY,
    gap_id TEXT NOT NULL REFERENCES collector_gaps(gap_id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    reconciled_at_iso TEXT NOT NULL,
    reconciled_at_epoch_ms INTEGER NOT NULL,
    entities_sustained_count INTEGER NOT NULL DEFAULT 0,
    entities_terminated_count INTEGER NOT NULL DEFAULT 0,
    entities_staled_count INTEGER NOT NULL DEFAULT 0,
    entities_spawned_count INTEGER NOT NULL DEFAULT 0,
    confidence_discount_pct REAL NOT NULL DEFAULT 0.0,
    actions_json TEXT NOT NULL DEFAULT '[]',
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_reconciliation_gap_id ON state_reconciliation_records (gap_id);
CREATE INDEX IF NOT EXISTS idx_reconciliation_device_id ON state_reconciliation_records (device_id);
CREATE INDEX IF NOT EXISTS idx_reconciliation_domain ON state_reconciliation_records (domain);
CREATE INDEX IF NOT EXISTS idx_reconciliation_epoch_ms ON state_reconciliation_records (reconciled_at_epoch_ms);

-- DOWN
DROP INDEX IF EXISTS idx_reconciliation_epoch_ms;
DROP INDEX IF EXISTS idx_reconciliation_domain;
DROP INDEX IF EXISTS idx_reconciliation_device_id;
DROP INDEX IF EXISTS idx_reconciliation_gap_id;
DROP TABLE IF EXISTS state_reconciliation_records;

DROP INDEX IF EXISTS idx_collector_gaps_start_end;
DROP INDEX IF EXISTS idx_collector_gaps_duration;
DROP INDEX IF EXISTS idx_collector_gaps_domain;
DROP INDEX IF EXISTS idx_collector_gaps_device_id;
DROP INDEX IF EXISTS idx_collector_gaps_collector_id;
DROP TABLE IF EXISTS collector_gaps;
