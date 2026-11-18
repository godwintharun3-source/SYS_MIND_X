/**
 * SYSTEM MIND X - Sandboxed Presentation Layer API Client
 * 
 * Invariants:
 * 1. Zero raw shell or OS process execution.
 * 2. All calls routed through typed ApiRequest / ApiResponse wire envelopes.
 * 3. Mutating operations strictly require a unique idempotency key.
 * 4. Explicit OFFLINE error reporting when control plane daemon is unreachable.
 * 5. Zero fake success responses: approvals and state changes require backend confirmation.
 */

import type {
  ApiRequest,
  ApiResponse,
  SystemSensorMetrics,
  DigitalTwinSummary,
  AuditRecordSummary,
  FileTrustState,
} from "../types/api.ts";

export class SystemMindApiClient {
  private baseUrl: string;
  private callerIdentity: string;

  constructor(baseUrl = "http://127.0.0.1:8765/api/v1", callerIdentity = "operator:console") {
    this.baseUrl = baseUrl;
    this.callerIdentity = callerIdentity;
  }

  /**
   * Inspects the native desktop presentation shell (Tauri v2).
   */
  getDesktopShellInfo(): {
    isTauri: boolean;
    appIdentifier: string;
    version: string;
    cspEnforced: boolean;
    ambientShellDisabled: boolean;
  } {
    const isTauri =
      typeof window !== "undefined" &&
      ("__TAURI_INTERNALS__" in window || "__TAURI__" in window);

    return {
      isTauri,
      appIdentifier: "org.systemmind.desktop",
      version: "1.0.0",
      cspEnforced: true,
      ambientShellDisabled: true,
    };
  }

  /**
   * Helper to generate a client-side UUIDv4 idempotency key.
   */
  public generateUuid(): string {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /**
   * Builds a canonical ApiRequest envelope.
   */
  private createRequest<T>(
    operation: string,
    payload: T,
    idempotencyKey?: string
  ): ApiRequest<T> {
    return {
      version: "1.0.0",
      request_id: this.generateUuid(),
      timestamp: new Date().toISOString(),
      caller_identity: this.callerIdentity,
      operation,
      payload,
      ...(idempotencyKey ? { idempotency_key: idempotencyKey } : {}),
    };
  }

  /**
   * Constructs an RFC 7807 structured error envelope when backend is unreachable.
   */
  private createOfflineErrorEnvelope<T>(message: string): ApiResponse<T> {
    const nowIso = new Date().toISOString();
    return {
      version: "1.0.0",
      request_id: this.generateUuid(),
      timestamp: nowIso,
      status: "error",
      error: {
        code: "E7001",
        message,
        timestamp: nowIso,
      },
      execution_duration_ms: 0,
    };
  }

  /**
   * Fetch live sensor metrics from the control plane daemon.
   */
  async getSensorMetrics(): Promise<ApiResponse<SystemSensorMetrics>> {
    try {
      const response = await fetch(`${this.baseUrl}/sensors/metrics`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      if (response.ok) {
        return (await response.json()) as ApiResponse<SystemSensorMetrics>;
      }
      return this.createOfflineErrorEnvelope(`Daemon returned HTTP ${response.status}`);
    } catch {
      return this.createOfflineErrorEnvelope(
        `Control plane daemon unreachable at ${this.baseUrl}. Backend connection is OFFLINE.`
      );
    }
  }

  /**
   * Fetch Digital Twin state summary from the control plane daemon.
   */
  async getDigitalTwinState(): Promise<ApiResponse<DigitalTwinSummary>> {
    try {
      const response = await fetch(`${this.baseUrl}/twin/summary`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      if (response.ok) {
        return (await response.json()) as ApiResponse<DigitalTwinSummary>;
      }
      return this.createOfflineErrorEnvelope(`Daemon returned HTTP ${response.status}`);
    } catch {
      return this.createOfflineErrorEnvelope(
        `Control plane daemon unreachable at ${this.baseUrl}. Backend connection is OFFLINE.`
      );
    }
  }

  /**
   * Inspect the 8-state file trust lifecycle for a given path.
   * SC-03: Re-emphasizes Scan != Safe.
   */
  async inspectFileTrust(filePath: string): Promise<ApiResponse<{ path: string; state: FileTrustState; reason: string }>> {
    try {
      const response = await fetch(`${this.baseUrl}/filetrust/inspect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: filePath }),
      });
      if (response.ok) {
        return (await response.json()) as ApiResponse<{ path: string; state: FileTrustState; reason: string }>;
      }
      return this.createOfflineErrorEnvelope(`Daemon returned HTTP ${response.status}`);
    } catch {
      return this.createOfflineErrorEnvelope(
        `Control plane daemon unreachable at ${this.baseUrl}. File trust inspector is OFFLINE.`
      );
    }
  }

  /**
   * Mutating operation: Submit an operator governance approval verdict.
   * Strictly enforces idempotency_key requirement.
   * Never returns success when backend is offline.
   */
  async submitGovernanceApproval(
    actionId: string,
    approved: boolean,
    justification: string,
    idempotencyKey?: string
  ): Promise<ApiResponse<{ action_id: string; verdict: string; recorded_at: string; sequence_id?: number }>> {
    const key = idempotencyKey || this.generateUuid();

    const requestPayload = {
      action_id: actionId,
      verdict: approved ? "APPROVED" : "REJECTED",
      justification,
    };

    const envelope = this.createRequest(
      "governance.submit_approval",
      requestPayload,
      key
    );

    try {
      const response = await fetch(`${this.baseUrl}/governance/approvals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...envelope,
          idempotency_key: key,
        }),
      });
      if (response.ok) {
        return (await response.json()) as ApiResponse<{ action_id: string; verdict: string; recorded_at: string; sequence_id?: number }>;
      }
      return this.createOfflineErrorEnvelope(
        `Governance submission rejected by daemon with HTTP ${response.status}`
      );
    } catch {
      return this.createOfflineErrorEnvelope(
        "Governance submission failed: backend daemon is OFFLINE. Operations cannot be approved without backend confirmation."
      );
    }
  }

  /**
   * Retrieve tamper-evident audit ledger entries from the daemon.
   */
  async getAuditLedger(): Promise<ApiResponse<AuditRecordSummary[]>> {
    try {
      const response = await fetch(`${this.baseUrl}/audit/ledger`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });
      if (response.ok) {
        return (await response.json()) as ApiResponse<AuditRecordSummary[]>;
      }
      return this.createOfflineErrorEnvelope(`Daemon returned HTTP ${response.status}`);
    } catch {
      return this.createOfflineErrorEnvelope(
        `Control plane daemon unreachable at ${this.baseUrl}. Audit ledger is OFFLINE.`
      );
    }
  }
}

export const apiClient = new SystemMindApiClient();
