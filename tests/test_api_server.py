"""Unit, contract, and database integration tests for SYSTEM MIND X Backend HTTP API server."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import threading
import time
import unittest
import urllib.request
import urllib.error

from system_mind.api.server import create_api_server
from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestApiServer(unittest.TestCase):
    """End-to-end integration tests for backend HTTP server with SQLite persistence."""

    server: any
    server_thread: threading.Thread
    base_url: str
    db_conn: any

    @classmethod
    def setUpClass(cls) -> None:
        cfg = DatabaseConfig(db_path=":memory:", check_same_thread=False)
        cls.db_conn = DatabaseConnectionManager.connect(cfg)
        migrator = DatabaseMigrator(config=cfg)
        migrator.apply_all(cls.db_conn)

        # Start HTTP server on local ephemeral port
        cls.server = create_api_server(host="127.0.0.1", port=0, db_conn=cls.db_conn)
        port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{port}/api/v1"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.db_conn.close()

    def _http_get(self, path: str) -> tuple[int, dict]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as e:
            data = json.loads(e.read().decode("utf-8"))
            return e.code, data

    def _http_post(self, path: str, payload: dict) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as e:
            data = json.loads(e.read().decode("utf-8"))
            return e.code, data

    def test_sensors_metrics_persists_to_sqlite(self) -> None:
        """Verify GET /sensors/metrics returns live telemetry and records temporal observation in SQLite."""
        status, res = self._http_get("/sensors/metrics?mock=1")
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "success")
        self.assertIn("data", res)
        self.assertGreater(res["data"]["memory_total_mb"], 0)

        # Verify observation record inserted into SQLite
        cursor = self.db_conn.execute("SELECT COUNT(*) FROM temporal_observations;")
        count = cursor.fetchone()[0]
        self.assertGreaterEqual(count, 1)

    def test_twin_summary_endpoint(self) -> None:
        """Verify GET /twin/summary returns digital twin state from database."""
        status, res = self._http_get("/twin/summary")
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "success")
        self.assertIn("node_count", res["data"])
        self.assertIn("edge_count", res["data"])
        self.assertTrue(res["data"]["is_consistent"])

    def test_governance_approval_requires_idempotency_key(self) -> None:
        """Verify POST /governance/approvals rejects requests without idempotency_key (E3003)."""
        payload = {
            "caller_identity": "operator:test",
            "operation": "governance.submit_approval",
            "payload": {"action_id": "act-test-01", "verdict": "APPROVED"},
        }
        status, res = self._http_post("/governance/approvals", payload)
        self.assertEqual(status, 400)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error"]["code"], "E3003")

    def test_governance_approval_persists_to_audit_ledger(self) -> None:
        """Verify POST /governance/approvals records chained audit event in SQLite."""
        payload = {
            "idempotency_key": "idemp-test-9999",
            "caller_identity": "operator:test",
            "operation": "governance.submit_approval",
            "payload": {
                "action_id": "act-test-approve",
                "verdict": "APPROVED",
                "justification": "Operator manually attested",
            },
        }
        status, res = self._http_post("/governance/approvals", payload)
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["verdict"], "APPROVED")

        # Verify audit record in database
        cursor = self.db_conn.execute(
            "SELECT action_urn, risk_tier, prev_event_hash, event_hash FROM audit_events ORDER BY sequence_number DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "governance.submit_approval")
        self.assertEqual(row[1], "HIGH")
        self.assertEqual(len(row[3]), 64)  # SHA-256 hash length

    def test_audit_ledger_query(self) -> None:
        """Verify GET /audit/ledger retrieves recent tamper-evident entries from SQLite."""
        # Ensure at least one entry exists
        self._http_post("/governance/approvals", {
            "idempotency_key": "idemp-setup-audit-query",
            "caller_identity": "operator:test",
            "operation": "governance.submit_approval",
            "payload": {"action_id": "act-setup", "verdict": "APPROVED"},
        })
        status, res = self._http_get("/audit/ledger")
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "success")
        self.assertIsInstance(res["data"], list)
        self.assertGreaterEqual(len(res["data"]), 1)
        self.assertEqual(res["data"][0]["action_name"], "governance.submit_approval")

    def test_filetrust_inspect(self) -> None:
        """Verify POST /filetrust/inspect enforces 8-state quarantine."""
        status, res = self._http_post("/filetrust/inspect", {"path": "/tmp/untrusted.bin"})
        self.assertEqual(status, 200)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["data"]["state"], "QUARANTINED")

    def test_unknown_endpoint_returns_rfc7807_error(self) -> None:
        """Verify unknown endpoint returns 404 with E5001 code."""
        status, res = self._http_get("/nonexistent/endpoint")
        self.assertEqual(status, 404)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error"]["code"], "E5001")

    def test_ast_safety_sc01(self) -> None:
        """Verify SC-01 zero shell=True and zero os.system in server module."""
        server_path = ROOT_DIR / "src" / "system_mind" / "api" / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "system"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                ):
                    self.fail("Forbidden os.system in server.py")
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        self.fail("Forbidden shell=True in server.py")


if __name__ == "__main__":
    unittest.main()
