-- Migration: 0011_application_lifecycle_events
-- Description: Dedicated relational schema for application lifecycle transitions (install, remove, upgrade, path mutation) with strict SC-03 invariant check

-- UP
CREATE TABLE IF NOT EXISTS application_lifecycle_events (
    event_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    entity_urn TEXT NOT NULL,
    event_type TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    app_name TEXT NOT NULL,
    bundle_path TEXT NOT NULL,
    version TEXT NOT NULL,
    previous_version TEXT,
    previous_path TEXT,
    ownership TEXT NOT NULL,
    detection_source TEXT NOT NULL,
    observed_at_iso TEXT NOT NULL,
    observed_at_epoch_ms INTEGER NOT NULL,
    code_signature_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_app_lifecycle_events_device_id ON application_lifecycle_events (device_id);
CREATE INDEX IF NOT EXISTS idx_app_lifecycle_events_entity_urn ON application_lifecycle_events (entity_urn);
CREATE INDEX IF NOT EXISTS idx_app_lifecycle_events_bundle_id ON application_lifecycle_events (bundle_id);
CREATE INDEX IF NOT EXISTS idx_app_lifecycle_events_event_type ON application_lifecycle_events (event_type);
CREATE INDEX IF NOT EXISTS idx_app_lifecycle_events_epoch_ms ON application_lifecycle_events (observed_at_epoch_ms);
CREATE INDEX IF NOT EXISTS idx_app_lifecycle_events_ownership ON application_lifecycle_events (ownership);

-- DOWN
DROP INDEX IF EXISTS idx_app_lifecycle_events_ownership;
DROP INDEX IF EXISTS idx_app_lifecycle_events_epoch_ms;
DROP INDEX IF EXISTS idx_app_lifecycle_events_event_type;
DROP INDEX IF EXISTS idx_app_lifecycle_events_bundle_id;
DROP INDEX IF EXISTS idx_app_lifecycle_events_entity_urn;
DROP INDEX IF EXISTS idx_app_lifecycle_events_device_id;
DROP TABLE IF EXISTS application_lifecycle_events;
