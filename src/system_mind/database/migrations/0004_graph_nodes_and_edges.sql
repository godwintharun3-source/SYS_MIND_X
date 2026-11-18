-- Migration: 0004_graph_nodes_and_edges
-- Description: Dedicated relational tables for property graph nodes and edges in the digital twin

-- UP
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    ownership TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    provenance_source TEXT NOT NULL DEFAULT 'telemetry_pipeline',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_stale INTEGER NOT NULL DEFAULT 0 CHECK (is_stale IN (0, 1)),
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes (node_type);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_ownership ON graph_nodes (ownership);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_is_stale ON graph_nodes (is_stale);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    target_node_id TEXT NOT NULL REFERENCES graph_nodes(node_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    scan_proves_safe INTEGER NOT NULL DEFAULT 0 CHECK (scan_proves_safe = 0)
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges (source_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges (target_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_relation_type ON graph_edges (relation_type);
CREATE INDEX IF NOT EXISTS idx_graph_edges_observed_at ON graph_edges (observed_at);

-- DOWN
DROP INDEX IF EXISTS idx_graph_edges_observed_at;
DROP INDEX IF EXISTS idx_graph_edges_relation_type;
DROP INDEX IF EXISTS idx_graph_edges_target;
DROP INDEX IF EXISTS idx_graph_edges_source;
DROP TABLE IF EXISTS graph_edges;

DROP INDEX IF EXISTS idx_graph_nodes_is_stale;
DROP INDEX IF EXISTS idx_graph_nodes_ownership;
DROP INDEX IF EXISTS idx_graph_nodes_type;
DROP TABLE IF EXISTS graph_nodes;
