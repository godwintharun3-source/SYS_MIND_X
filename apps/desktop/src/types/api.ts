/**
 * SYSTEM MIND X - Desktop Frontend Wire Protocol & Architectural Types
 * 
 * Invariants:
 * 1. Strictly conforms to Day 024 API Wire Envelopes (ApiRequest, ApiResponse, ApiErrorDetail).
 * 2. Mirrors the 8-state File Trust lifecycle (SC-03: Scan != Safe).
 * 3. Enforces Component Ownership boundaries (SYSTEM_MANAGED, VENDOR_MANAGED, USER_MANAGED).
 */

export type ApiStatus = "success" | "error" | "pending" | "accepted";

export type ErrorCode =
  // E1000..E1999: System & Runtime Failures
  | "E1000" // Internal Error
  | "E1001" // Service Unavailable
  | "E1002" // Timeout
  // E2000..E2999: Authentication, Identity & Permissions
  | "E2001" // Unauthorized
  | "E2002" // Forbidden / Insufficient Privileges
  | "E2003" // Token Expired
  // E3000..E3999: Validation & Envelope Invariants
  | "E3001" // Missing Required Field
  | "E3002" // Invalid Format / Schema Mismatch
  | "E3003" // Missing Mutating Idempotency Key
  // E4000..E4999: Deterministic Policy Engine Violations
  | "E4001" // Policy Denied
  | "E4002" // Boundary Violation
  | "E4003" // Quarantined File Execution Attempt
  // E5000..E5999: Resource & Entity States
  | "E5001" // Resource Not Found
  | "E5002" // Resource Conflict / Stale State
  // E6000..E6999: Concurrency & Idempotency
  | "E6001" // Idempotency Conflict
  | "E6002" // Concurrent Mutation In Progress
  // E7000..E7999: Upstream & OS Platform Failures
  | "E7001" // Upstream Daemon Unreachable
  | "E7002"; // Unsupported OS Capability

/**
 * Inviolable 8-State File Trust Lifecycle.
 * SC-03: A static or AI scan NEVER proves a file is safe.
 */
export type FileTrustState =
  | "QUARANTINED"
  | "VERIFIED"
  | "SANDBOXED"
  | "BLOCKED"
  | "ALLOWLISTED"
  | "PROVENANCE_PENDING"
  | "SECURITY_REVOKED"
  | "STATIC_ANALYSIS_FAILED";

/**
 * Tripartite Component Ownership Boundary.
 * USER_MANAGED components and project dependencies are outside automatic system updates.
 */
export type ComponentOwnership =
  | "SYSTEM_MANAGED"
  | "VENDOR_MANAGED"
  | "USER_MANAGED";

/**
 * Standard RFC 7807 problem detail envelope.
 */
export interface ApiErrorDetail {
  code: ErrorCode;
  message: string;
  target?: string;
  details?: Record<string, unknown>;
  timestamp: string;
  request_id?: string;
}

/**
 * Unified API Request Envelope.
 * Mutating operations strictly require a unique idempotency_key.
 */
export interface ApiRequest<T = unknown> {
  version: string;
  request_id: string;
  timestamp: string;
  caller_identity: string;
  operation: string;
  payload: T;
  idempotency_key?: string;
}

/**
 * Unified API Response Envelope.
 */
export interface ApiResponse<T = unknown> {
  version: string;
  request_id: string;
  timestamp: string;
  status: ApiStatus;
  data?: T;
  error?: ApiErrorDetail;
  execution_duration_ms?: number;
}

/**
 * Hardware Telemetry & Sensor State.
 */
export interface SystemSensorMetrics {
  cpu_usage_pct: number;
  memory_used_mb: number;
  memory_total_mb: number;
  active_processes: number;
  quarantined_files_count: number;
  broker_connected: boolean;
  mock_mode: boolean;
  last_sampled: string;
}

/**
 * Digital Twin State Summary.
 */
export interface DigitalTwinSummary {
  node_count: number;
  edge_count: number;
  temporal_epoch: number;
  is_consistent: boolean;
  unresolved_drift: boolean;
}

/**
 * Audit Hash-Chain Ledger Entry.
 */
export interface AuditRecordSummary {
  sequence_id: number;
  timestamp: string;
  actor: string;
  action_name: string;
  status: "AUTHORIZED" | "DENIED" | "EXECUTED" | "FAILED";
  sha256_hash: string;
  previous_hash: string;
}

/**
 * Operator Governance Action Prompt.
 */
export interface GovernanceActionRequest {
  action_id: string;
  action_type: string;
  target_resource: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  component_ownership: ComponentOwnership;
  justification: string;
  requires_biometric: boolean;
  status: "PENDING_REVIEW" | "APPROVED" | "REJECTED";
}
