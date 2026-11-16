-- Migration: 0002_add_component_ownership_indices
-- Description: Additional indices for entity observation timestamp and observation payload hash

-- UP
CREATE INDEX IF NOT EXISTS idx_twin_entities_observed_at ON twin_entities (observed_at);
CREATE INDEX IF NOT EXISTS idx_temporal_observations_payload_hash ON temporal_observations (payload_hash);

-- DOWN
DROP INDEX IF EXISTS idx_temporal_observations_payload_hash;
DROP INDEX IF EXISTS idx_twin_entities_observed_at;
