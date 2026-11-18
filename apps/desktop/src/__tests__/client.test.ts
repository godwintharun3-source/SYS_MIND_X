import { describe, it } from "node:test";
import assert from "node:assert";
import { SystemMindApiClient } from "../services/client.ts";

describe("SystemMindApiClient", () => {
  it("enforces sandboxed presentation shell boundaries", () => {
    const client = new SystemMindApiClient();
    const info = client.getDesktopShellInfo();
    assert.strictEqual(info.cspEnforced, true);
    assert.strictEqual(info.ambientShellDisabled, true);
    assert.strictEqual(info.appIdentifier, "org.systemmind.desktop");
  });

  it("returns explicit offline error when daemon is unreachable", async () => {
    const client = new SystemMindApiClient("http://127.0.0.1:54321/api/v1");
    const res = await client.getSensorMetrics();
    assert.strictEqual(res.status, "error");
    assert.strictEqual(res.error?.code, "E7001");
    assert.ok(res.error?.message.includes("OFFLINE"));
  });

  it("rejects mutating governance approval when backend is offline", async () => {
    const client = new SystemMindApiClient("http://127.0.0.1:54321/api/v1");
    const customKey = "test-idempotency-key-001";
    const res = await client.submitGovernanceApproval(
      "act-approve-1",
      true,
      "Approved by operator console",
      customKey
    );
    assert.strictEqual(res.status, "error");
    assert.strictEqual(res.error?.code, "E7001");
    assert.ok(res.error?.message.includes("OFFLINE"));
  });

  it("returns explicit error for file trust inspection when offline", async () => {
    const client = new SystemMindApiClient("http://127.0.0.1:54321/api/v1");
    const res = await client.inspectFileTrust("/tmp/unknown_script.sh");
    assert.strictEqual(res.status, "error");
    assert.strictEqual(res.error?.code, "E7001");
  });

  it("returns explicit error for audit ledger when offline", async () => {
    const client = new SystemMindApiClient("http://127.0.0.1:54321/api/v1");
    const res = await client.getAuditLedger();
    assert.strictEqual(res.status, "error");
    assert.strictEqual(res.error?.code, "E7001");
  });
});
