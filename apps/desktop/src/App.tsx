import React, { useState, useEffect } from "react";
import {
  SystemSensorMetrics,
  DigitalTwinSummary,
  AuditRecordSummary,
  GovernanceActionRequest,
  FileTrustState,
  BackendConnectionState,
} from "./types/api";
import { apiClient } from "./services/client";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"overview" | "governance" | "filetrust" | "audit">("overview");
  const [metrics, setMetrics] = useState<SystemSensorMetrics | null>(null);
  const [twin, setTwin] = useState<DigitalTwinSummary | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecordSummary[]>([]);
  const [inspectPath, setInspectPath] = useState<string>("/tmp/incoming_payload.bin");
  const [trustResult, setTrustResult] = useState<{ path: string; state: FileTrustState; reason: string } | null>(null);
  const [backendStatus, setBackendStatus] = useState<BackendConnectionState>("OFFLINE");
  const [lastCheckTime, setLastCheckTime] = useState<string>(new Date().toLocaleTimeString());

  // Pending governance action
  const [pendingAction, setPendingAction] = useState<GovernanceActionRequest>({
    action_id: "act_029_quarantine_eval",
    action_type: "SANDBOX_VERIFY_EXECUTION",
    target_resource: "/opt/system-mind/payloads/untrusted_blob.bin",
    risk_level: "HIGH",
    component_ownership: "SYSTEM_MANAGED",
    justification: "Verify SHA-256 fingerprint in isolated micro-VM before allowing execution.",
    requires_biometric: true,
    status: "PENDING_REVIEW",
  });

  const [approvalFeedback, setApprovalFeedback] = useState<string | null>(null);
  const [isErrorFeedback, setIsErrorFeedback] = useState<boolean>(false);

  const refreshData = async () => {
    setLastCheckTime(new Date().toLocaleTimeString());

    const sensorRes = await apiClient.getSensorMetrics();
    if (sensorRes.status === "success" && sensorRes.data) {
      setMetrics(sensorRes.data);
      setBackendStatus(sensorRes.data.mock_mode ? "MOCK" : "LIVE");
    } else {
      setMetrics(null);
      setBackendStatus("OFFLINE");
    }

    const twinRes = await apiClient.getDigitalTwinState();
    if (twinRes.status === "success" && twinRes.data) {
      setTwin(twinRes.data);
    } else {
      setTwin(null);
    }

    const auditRes = await apiClient.getAuditLedger();
    if (auditRes.status === "success" && auditRes.data) {
      setAuditRecords(auditRes.data);
    } else {
      setAuditRecords([]);
    }
  };

  useEffect(() => {
    refreshData();
  }, []);

  const handleRefresh = async () => {
    await refreshData();
  };

  const handleInspectPath = async () => {
    const res = await apiClient.inspectFileTrust(inspectPath);
    if (res.status === "success" && res.data) {
      setTrustResult(res.data);
    } else {
      setTrustResult({
        path: inspectPath,
        state: "UNTRUSTED_UNKNOWN",
        reason: res.error?.message || "File trust inspection failed: backend daemon is offline.",
      });
    }
  };

  const handleGovernanceVote = async (approved: boolean) => {
    const res = await apiClient.submitGovernanceApproval(
      pendingAction.action_id,
      approved,
      approved ? "Operator approved micro-VM verification" : "Operator rejected execution"
    );

    if (res.status === "success" && res.data) {
      setPendingAction((prev) => ({
        ...prev,
        status: approved ? "APPROVED" : "REJECTED",
      }));
      setIsErrorFeedback(false);
      setApprovalFeedback(
        `Action ${res.data.action_id} ${res.data.verdict} recorded at ${res.data.recorded_at} (Seq #${res.data.sequence_id || 'chain'})`
      );
    } else {
      setIsErrorFeedback(true);
      setApprovalFeedback(
        `[OPERATION DENIED] ${res.error?.message || "Consequential operation rejected: control plane daemon is OFFLINE."}`
      );
    }
  };

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header">
        <div className="logo-section">
          <span className="logo-badge">SM-X</span>
          <span className="app-title">SYSTEM MIND X Operator Console</span>
        </div>
        <div className="header-status">
          <div className="status-pill">
            <span
              className={`status-dot ${
                backendStatus === "LIVE"
                  ? "green"
                  : backendStatus === "MOCK" || backendStatus === "SIMULATED"
                  ? "amber"
                  : "red"
              }`}
            />
            <span>
              Backend: <strong>{backendStatus}</strong> ({lastCheckTime})
            </span>
          </div>
          <div className="status-pill">
            <span>Identity: <strong>LOCAL_CONSOLE_USER</strong></span>
          </div>
          <div className="status-pill">
            <span>Shell: <strong>Tauri v2 (Safe Window)</strong></span>
          </div>
          <div className="status-pill">
            <span>Epoch: <strong>{twin?.temporal_epoch ?? "OFFLINE"}</strong></span>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="nav-bar">
        <button
          className={`nav-tab ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          Overview & Telemetry
        </button>
        <button
          className={`nav-tab ${activeTab === "governance" ? "active" : ""}`}
          onClick={() => setActiveTab("governance")}
        >
          Governance Approvals
        </button>
        <button
          className={`nav-tab ${activeTab === "filetrust" ? "active" : ""}`}
          onClick={() => setActiveTab("filetrust")}
        >
          File Trust & Sandboxes
        </button>
        <button
          className={`nav-tab ${activeTab === "audit" ? "active" : ""}`}
          onClick={() => setActiveTab("audit")}
        >
          Audit Hash-Chain
        </button>
      </nav>

      {/* Main Content */}
      <main className="main-content">
        {/* Connection Failure Warning Banner */}
        {backendStatus === "OFFLINE" && (
          <div style={{
            padding: "12px 16px",
            backgroundColor: "rgba(248, 81, 73, 0.15)",
            border: "1px solid var(--accent-red)",
            borderRadius: "6px",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            color: "#f85149"
          }}>
            <span style={{ fontSize: "1.2rem" }}>🔌</span>
            <div>
              <strong>Control Plane Daemon Offline:</strong> The backend service at <code>http://127.0.0.1:8765</code> is unreachable.
              Consequential governance actions cannot be approved, and telemetry measurements reflect zero live computer information.
            </div>
            <button className="btn btn-secondary" onClick={handleRefresh} style={{ marginLeft: "auto" }}>
              Retry Connection
            </button>
          </div>
        )}

        {/* Universal Safety Invariant Banner */}
        <div className="invariant-banner">
          <span>⚠️</span>
          <div>
            <strong>Invariant SC-03 Active:</strong> Static or AI scanning does NOT prove a file is safe.
            Quarantined payloads cannot execute natively on host OS. User project dependencies remain strictly USER_MANAGED.
          </div>
        </div>

        {/* Tab 1: Overview */}
        {activeTab === "overview" && (
          <div>
            <div className="dashboard-grid">
              <div className="card">
                <div className="card-header">
                  <span className="card-title">CPU Utilization</span>
                  <button className="btn btn-secondary" onClick={handleRefresh}>Refresh</button>
                </div>
                <div className="metric-value">
                  {metrics ? `${metrics.cpu_usage_pct.toFixed(1)}%` : backendStatus === "OFFLINE" ? "OFFLINE" : "Loading..."}
                </div>
                <div className="metric-sub">
                  Active processes: {metrics?.active_processes ?? (backendStatus === "OFFLINE" ? "Unavailable" : "--")}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">Memory Allocation</span>
                </div>
                <div className="metric-value">
                  {metrics
                    ? `${(metrics.memory_used_mb / 1024).toFixed(1)} GB`
                    : backendStatus === "OFFLINE"
                    ? "OFFLINE"
                    : "Loading..."}
                </div>
                <div className="metric-sub">
                  Total pool: {metrics ? `${(metrics.memory_total_mb / 1024).toFixed(0)} GB` : backendStatus === "OFFLINE" ? "Unavailable" : "--"}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">Digital Twin Graph</span>
                </div>
                <div className="metric-value">
                  {twin ? `${twin.node_count} Nodes` : backendStatus === "OFFLINE" ? "OFFLINE" : "-- Nodes"}
                </div>
                <div className="metric-sub">
                  {twin ? `${twin.edge_count} Topology Edges | ${twin.is_consistent ? "Consistent" : "Drift"}` : "Persistence unavailable"}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">Quarantined Payloads</span>
                </div>
                <div className="metric-value" style={{ color: "var(--accent-red)" }}>
                  {metrics?.quarantined_files_count ?? 0}
                </div>
                <div className="metric-sub">Sandboxed micro-VM execution required</div>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">Tripartite Boundary Status</span>
              </div>
              <p style={{ color: "var(--text-secondary)", marginBottom: "12px" }}>
                Components are partitioned into three immutable governance zones. User projects and developer environments are protected from autonomous mutation.
              </p>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Domain</th>
                    <th>Classification</th>
                    <th>Autonomous Update Policy</th>
                    <th>Isolation Boundary</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Host Kernel & Core OS</td>
                    <td><span className="badge badge-verified">SYSTEM_MANAGED</span></td>
                    <td>Read-only inspection; user must confirm updates</td>
                    <td>Native OS Kernel & SIP/Gatekeeper</td>
                  </tr>
                  <tr>
                    <td>Verified System Mind Extensions</td>
                    <td><span className="badge badge-sandboxed">VENDOR_MANAGED</span></td>
                    <td>Cryptographically signed manifest check</td>
                    <td>Wasm / Broker Daemon Sandbox</td>
                  </tr>
                  <tr>
                    <td>Developer Apps & Projects</td>
                    <td><span className="badge badge-pending">USER_MANAGED</span></td>
                    <td>Strictly Excluded; never auto-mutated</td>
                    <td>Isolated user directory roots</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: Governance Approvals */}
        {activeTab === "governance" && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">Pending Governance Consequential Actions</span>
              <span className="badge badge-pending">{pendingAction.status}</span>
            </div>

            {approvalFeedback && (
              <div style={{
                padding: "8px 12px",
                backgroundColor: isErrorFeedback ? "rgba(248, 81, 73, 0.15)" : "rgba(63, 185, 80, 0.1)",
                border: `1px solid ${isErrorFeedback ? "var(--accent-red)" : "var(--accent-green)"}`,
                borderRadius: "4px",
                marginBottom: "16px",
                color: isErrorFeedback ? "var(--accent-red)" : "var(--accent-green)",
              }}>
                {approvalFeedback}
              </div>
            )}

            <div style={{ marginBottom: "16px", lineHeight: 1.8 }}>
              <div><strong>Action ID:</strong> <span className="mono-text">{pendingAction.action_id}</span></div>
              <div><strong>Operation:</strong> {pendingAction.action_type}</div>
              <div><strong>Target Resource:</strong> <span className="mono-text">{pendingAction.target_resource}</span></div>
              <div><strong>Risk Level:</strong> <span style={{ color: "var(--accent-red)", fontWeight: "bold" }}>{pendingAction.risk_level}</span></div>
              <div><strong>Ownership Boundary:</strong> {pendingAction.component_ownership}</div>
              <div><strong>Justification:</strong> {pendingAction.justification}</div>
              <div><strong>Biometric Required:</strong> {pendingAction.requires_biometric ? "Yes (Hardware Key / TouchID)" : "No"}</div>
            </div>

            {pendingAction.status === "PENDING_REVIEW" ? (
              <div style={{ display: "flex", gap: "12px" }}>
                <button className="btn btn-primary" onClick={() => handleGovernanceVote(true)}>
                  Approve Execution with Idempotency Token
                </button>
                <button className="btn btn-danger" onClick={() => handleGovernanceVote(false)}>
                  Deny & Retain Quarantine
                </button>
              </div>
            ) : (
              <div style={{ color: "var(--text-secondary)" }}>
                Verdict recorded. Further operations require new cryptographic capability ticket.
              </div>
            )}
          </div>
        )}

        {/* Tab 3: File Trust */}
        {activeTab === "filetrust" && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">File Trust Lifecycle Inspector (8-State Model)</span>
            </div>
            <p style={{ color: "var(--text-secondary)", marginBottom: "16px" }}>
              Test and inspect file trust state transitions. Unverified external payloads enter QUARANTINED state by default.
            </p>

            <div style={{ display: "flex", gap: "10px", marginBottom: "16px" }}>
              <input
                type="text"
                value={inspectPath}
                onChange={(e) => setInspectPath(e.target.value)}
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  backgroundColor: "var(--bg-tertiary)",
                  border: "1px solid var(--border-default)",
                  borderRadius: "6px",
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-mono)",
                }}
              />
              <button className="btn btn-secondary" onClick={handleInspectPath}>
                Inspect Trust State
              </button>
            </div>

            {trustResult && (
              <div style={{ padding: "14px", backgroundColor: "var(--bg-tertiary)", borderRadius: "6px", border: "1px solid var(--border-default)" }}>
                <div><strong>Path:</strong> <span className="mono-text">{trustResult.path}</span></div>
                <div style={{ margin: "6px 0" }}>
                  <strong>Trust State:</strong>{" "}
                  <span className="badge badge-quarantine">{trustResult.state}</span>
                </div>
                <div><strong>Reason:</strong> {trustResult.reason}</div>
              </div>
            )}
          </div>
        )}

        {/* Tab 4: Audit Hash-Chain */}
        {activeTab === "audit" && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">Cryptographic Tamper-Evident Audit Ledger</span>
            </div>
            {auditRecords.length === 0 ? (
              <p style={{ color: "var(--text-secondary)" }}>
                {backendStatus === "OFFLINE" ? "Audit ledger unavailable while backend is OFFLINE." : "No audit records recorded yet."}
              </p>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Seq</th>
                    <th>Timestamp</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Status</th>
                    <th>SHA-256 Digest</th>
                  </tr>
                </thead>
                <tbody>
                  {auditRecords.map((rec) => (
                    <tr key={rec.sequence_id}>
                      <td className="mono-text">#{rec.sequence_id}</td>
                      <td>{new Date(rec.timestamp).toLocaleTimeString()}</td>
                      <td><span className="badge badge-sandboxed">{rec.actor}</span></td>
                      <td>{rec.action_name}</td>
                      <td>
                        <span className={`badge ${rec.status === "AUTHORIZED" || rec.status === "EXECUTED" ? "badge-verified" : "badge-quarantine"}`}>
                          {rec.status}
                        </span>
                      </td>
                      <td className="mono-text" title={`Previous: ${rec.previous_hash}`}>
                        {rec.sha256_hash.substring(0, 16)}...
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <div>SYSTEM MIND X Desktop Presentation Scaffold (Milestone 3 / Day 029)</div>
        <div>Zero Kernel Ambient Authority | RFC 7807 Wire Protocol</div>
      </footer>
    </div>
  );
};

export default App;
