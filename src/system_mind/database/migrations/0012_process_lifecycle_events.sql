-- Migration: 0012_process_lifecycle_events
-- Description: Dedicated relational schema for process lifecycle events (start, exit, fork, crash) with strict SC-03 invariant check

-- UP
CREATE TABLE IF NOT EXISTS process_lifecycle_events (
    event_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    entity_urn TEXT NOT NULL,
    event_type TEXT NOT NULL,
    pid INTEGER NOT NULL,
    ppid INTEGER NOT NULL,
    process_name TEXT NOT NULL,
    binary_path TEXT NOT NULL,
    command_line TEXT NOT NULL DEFAULT '',
    user_name TEXT NOT NULL,
    uid INTEGER NOT NULL,
    start_epoch_ms INTEGER NOT NULL,
    exit_epoch_ms INTEGER,
    exit_code INTEGER,
    exit_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    runtime_ms INTEGER,
    ownership TEXT NOT NULL,
    detection_source TEXT NOT NULL,
    observed_at_iso TEXT NOT NULL,
    observed_at_epoch_ms INTEGER NOT NULL,
    parent_entity_urn TEXT,
    app_entity_urn TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_proc_lifecycle_events_device_id ON process_lifecycle_events (device_id);
CREATE INDEX IF NOT EXISTS idx_proc_lifecycle_events_entity_urn ON process_lifecycle_events (entity_urn);
CREATE INDEX IF NOT EXISTS idx_proc_lifecycle_events_pid ON process_lifecycle_events (pid);
CREATE INDEX IF NOT EXISTS idx_proc_lifecycle_events_event_type ON process_lifecycle_events (event_type);
CREATE INDEX IF NOT EXISTS idx_proc_lifecycle_events_epoch_ms ON process_lifecycle_events (observed_at_epoch_ms);
CREATE INDEX IF NOT EXISTS idx_proc_lifecycle_events_ownership ON process_lifecycle_events (ownership);
CREATE INDEX IF NOT EXISTS idx_proc_lifecycle_events_start_exit ON process_lifecycle_events (start_epoch_ms, exit_epoch_ms);

-- DOWN
DROP INDEX IF EXISTS idx_proc_lifecycle_events_start_exit;
DROP INDEX IF EXISTS idx_proc_lifecycle_events_ownership;
DROP INDEX IF EXISTS idx_proc_lifecycle_events_epoch_ms;
DROP INDEX IF EXISTS idx_proc_lifecycle_events_event_type;
DROP INDEX IF EXISTS idx_proc_lifecycle_events_pid;
DROP INDEX IF EXISTS idx_proc_lifecycle_events_entity_urn;
DROP INDEX IF EXISTS idx_proc_lifecycle_events_device_id;
DROP TABLE IF EXISTS process_lifecycle_events;
