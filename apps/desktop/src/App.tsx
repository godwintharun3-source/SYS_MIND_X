import React, { useState, useEffect } from "react";
import {
  SystemSensorMetrics,
  DigitalTwinSummary,
  AuditRecordSummary,
  GovernanceActionRequest,
  FileTrustState,
} from "./types/api";
import { apiClient } from "./services/client";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"overview" | "governance" | "filetrust" | "audit">("overview");
  const [metrics, setMetrics] = useState<SystemSensorMetrics | null>(null);
  const [twin, setTwin] = useState<DigitalTwinSummary | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecordSummary[]>([]);
  const [inspectPath, setInspectPath] = useState<string>("/tmp/incoming_payload.bin");
  const [trustResult, setTrustResult] = useState<{ path: string; state: FileTrustState; reason: string } | null>(null);

  // Sample pending governance action
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

  useEffect(() => {
    // Initial data hydration
    apiClient.getSensorMetrics().then((res) => {
      if (res.data) setMetrics(res.data);
    });
    apiClient.getDigitalTwinState().then((res) => {
      if (res.data) setTwin(res.data);
    });
    apiClient.getAuditLedger().then((res) => {
      if (res.data) setAuditRecords(res.data);
    });
  }, []);

  const handleRefresh = async () => {
    const res = await apiClient.getSensorMetrics();
    if (res.data) setMetrics(res.data);
  };

  const handleInspectPath = async () => {
    const res = await apiClient.inspectFileTrust(inspectPath);
    if (res.data) setTrustResult(res.data);
  };

  const handleGovernanceVote = async (approved: boolean) => {
    const res = await apiClient.submitGovernanceApproval(
      pendingAction.action_id,
      approved,
      approved ? "Operator approved micro-VM verification" : "Operator rejected execution"
    );
    if (res.data) {
      setPendingAction((prev) => ({
        ...prev,
        status: approved ? "APPROVED" : "REJECTED",
      }));
      setApprovalFeedback(
        `Action ${res.data.action_id} ${res.data.verdict} recorded at ${res.data.recorded_at}`
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
            <span className={`status-dot ${metrics?.broker_connected ? "green" : "amber"}`} />
            <span>{metrics?.mock_mode ? "Mock Sensor Telemetry" : "Broker Daemon Connected"}</span>
          </div>
          <div className="status-pill">
            <span>Identity: <strong>LOCAL_CONSOLE_USER</strong></span>
          </div>
          <div className="status-pill">
            <span>Shell: <strong>Tauri v2 (Safe Window)</strong></span>
          </div>
          <div className="status-pill">
            <span>Epoch: <strong>{twin?.temporal_epoch ?? 30}</strong></span>
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
                <div className="metric-value">{metrics ? `${metrics.cpu_usage_pct.toFixed(1)}%` : "Loading..."}</div>
                <div className="metric-sub">Active processes: {metrics?.active_processes ?? "--"}</div>
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">Memory Allocation</span>
                </div>
                <div className="metric-value">
                  {metrics ? `${(metrics.memory_used_mb / 1024).toFixed(1)} GB` : "Loading..."}
                </div>
                <div className="metric-sub">Total pool: {metrics ? `${(metrics.memory_total_mb / 1024).toFixed(0)} GB` : "--"}</div>
              </div>

              <div className="card">
                <div className="card-header">
                  <span className="card-title">Digital Twin Graph</span>
                </div>
                <div className="metric-value">{twin?.node_count ?? "--"} Nodes</div>
                <div className="metric-sub">{twin?.edge_count ?? "--"} Topology Edges | {twin?.is_consistent ? "Consistent" : "Drift Detected"}</div>
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
              <div style={{ padding: "8px 12px", backgroundColor: "rgba(63, 185, 80, 0.1)", border: "1px solid var(--accent-green)", borderRadius: "4px", marginBottom: "16px", color: "var(--accent-green)" }}>
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
