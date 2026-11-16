import { describe, it, expect } from "vitest";
import { SystemMindApiClient } from "../services/client";

describe("SystemMindApiClient", () => {
  it("enforces sandboxed presentation shell boundaries", () => {
    const client = new SystemMindApiClient();
    const info = client.getDesktopShellInfo();
    expect(info.cspEnforced).toBe(true);
    expect(info.ambientShellDisabled).toBe(true);
    expect(info.appIdentifier).toBe("org.systemmind.desktop");
  });

  it("returns offline fallback sensor metrics gracefully", async () => {
    const client = new SystemMindApiClient();
    const res = await client.getSensorMetrics();
    expect(res.status).toBe("success");
    expect(res.data.mock_mode).toBe(true);
    expect(res.data.cpu_usage_pct).toBeGreaterThan(0);
  });

  it("enforces SC-03 quarantine on untrusted file paths", async () => {
    const client = new SystemMindApiClient();
    const res = await client.inspectFileTrust("/tmp/unknown_script.sh");
    expect(res.status).toBe("success");
    expect(res.data.state).toBe("QUARANTINED");
    expect(res.data.reason).toContain("quarantine enforced");
  });

  it("attaches idempotency key to mutating governance approvals", async () => {
    const client = new SystemMindApiClient();
    const customKey = "test-idempotency-key-001";
    const res = await client.submitGovernanceApproval(
      "act-approve-1",
      true,
      "Approved by operator console",
      customKey
    );
    expect(res.status).toBe("success");
    expect(res.data.verdict).toBe("APPROVED");
    expect(res.data.action_id).toBe("act-approve-1");
  });

  it("fetches tamper-evident audit ledger entries", async () => {
    const client = new SystemMindApiClient();
    const res = await client.getAuditLedger();
    expect(res.status).toBe("success");
    expect(res.data.length).toBeGreaterThan(0);
    expect(res.data[0].sha256_hash.length).toBe(64);
  });
});
