-- Migration: 0003_hardware_os_application_entities
-- Description: Dedicated relational tables for hardware, OS kernel, and application digital twin entities

-- UP
CREATE TABLE IF NOT EXISTS hardware_entities (
    entity_urn TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    category TEXT NOT NULL,
    model_name TEXT NOT NULL,
    vendor TEXT NOT NULL DEFAULT '',
    serial_hash TEXT NOT NULL DEFAULT '',
    attributes_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    provenance_source TEXT NOT NULL,
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_hardware_entities_device_id ON hardware_entities (device_id);
CREATE INDEX IF NOT EXISTS idx_hardware_entities_category ON hardware_entities (category);
CREATE INDEX IF NOT EXISTS idx_hardware_entities_observed_at ON hardware_entities (observed_at);

CREATE TABLE IF NOT EXISTS os_kernel_entities (
    entity_urn TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    os_family TEXT NOT NULL,
    product_version TEXT NOT NULL,
    build_version TEXT NOT NULL,
    kernel_release TEXT NOT NULL,
    architecture TEXT NOT NULL,
    security_posture_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    provenance_source TEXT NOT NULL,
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_os_kernel_entities_device_id ON os_kernel_entities (device_id);
CREATE INDEX IF NOT EXISTS idx_os_kernel_entities_os_family ON os_kernel_entities (os_family);
CREATE INDEX IF NOT EXISTS idx_os_kernel_entities_observed_at ON os_kernel_entities (observed_at);

CREATE TABLE IF NOT EXISTS application_entities (
    entity_urn TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    app_name TEXT NOT NULL,
    version TEXT NOT NULL,
    install_path TEXT NOT NULL,
    ownership TEXT NOT NULL,
    code_signature_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    provenance_source TEXT NOT NULL,
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_application_entities_device_id ON application_entities (device_id);
CREATE INDEX IF NOT EXISTS idx_application_entities_bundle_id ON application_entities (bundle_id);
CREATE INDEX IF NOT EXISTS idx_application_entities_ownership ON application_entities (ownership);
CREATE INDEX IF NOT EXISTS idx_application_entities_observed_at ON application_entities (observed_at);

-- DOWN
DROP INDEX IF EXISTS idx_application_entities_observed_at;
DROP INDEX IF EXISTS idx_application_entities_ownership;
DROP INDEX IF EXISTS idx_application_entities_bundle_id;
DROP INDEX IF EXISTS idx_application_entities_device_id;
DROP TABLE IF EXISTS application_entities;

DROP INDEX IF EXISTS idx_os_kernel_entities_observed_at;
DROP INDEX IF EXISTS idx_os_kernel_entities_os_family;
DROP INDEX IF EXISTS idx_os_kernel_entities_device_id;
DROP TABLE IF EXISTS os_kernel_entities;

DROP INDEX IF EXISTS idx_hardware_entities_observed_at;
DROP INDEX IF EXISTS idx_hardware_entities_category;
DROP INDEX IF EXISTS idx_hardware_entities_device_id;
DROP TABLE IF EXISTS hardware_entities;
