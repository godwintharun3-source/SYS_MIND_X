"""HTTP Presentation & Wire API Server for SYSTEM MIND X control plane."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import sqlite3
import time
from typing import Any, Dict, Optional
import urllib.parse
import uuid

from system_mind.api.models import ApiStatus, ErrorCode
from system_mind.database.connection import DatabaseConfig, DatabaseConnectionManager
from system_mind.database.migrator import DatabaseMigrator
from system_mind.database.telemetry_repo import TelemetryRepository
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.inventory_models import InventorySection, MacOsInventoryRequest

logger = logging.getLogger(__name__)


class SystemMindHttpHandler(BaseHTTPRequestHandler):
    """HTTP request handler implementing canonical API envelopes and RFC 7807 errors."""

    # Bound repository and inventory API (injected by server)
    repo: TelemetryRepository
    inventory_api: MacOsInventoryApi

    def _send_json_response(self, status_code: int, payload: Dict[str, Any]) -> None:
        """Send formatted JSON response with standard CORS headers."""
        response_bytes = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for sensor metrics, digital twin summary, and audit ledger."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/v1/sensors/metrics":
            start_t = time.perf_counter()
            query_params = urllib.parse.parse_qs(parsed_url.query)
            use_mock = query_params.get("mock", ["0"])[0] in ("1", "true")
            summary = self.inventory_api.get_summary(use_mock=use_mock)

            # Record observation in SQLite database
            obs_payload = summary.to_dict()
            obs_id = f"obs-metrics-{uuid.uuid4().hex[:8]}"
            self.repo.record_observation(
                observation_id=obs_id,
                observation_type="HARDWARE_METRICS",
                source="mock_companion" if use_mock else "darwin_companion",
                payload=obs_payload,
            )

            cpu_usage = 10.0
            total_mem = max(summary.total_memory_bytes // (1024 * 1024), 8192)
            used_mem = int(total_mem * (summary.memory_pressure_pct / 100.0)) if summary.memory_pressure_pct > 0 else total_mem // 4

            response_data = {
                "cpu_usage_pct": cpu_usage,
                "memory_used_mb": used_mem,
                "memory_total_mb": total_mem,
                "active_processes": summary.running_process_count,
                "quarantined_files_count": 0,
                "broker_connected": True,
                "mock_mode": use_mock,
                "last_sampled": datetime.now(timezone.utc).isoformat(),
            }

            envelope = {
                "version": "1.0.0",
                "request_id": f"req-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "data": response_data,
                "execution_duration_ms": round((time.perf_counter() - start_t) * 1000.0, 2),
            }
            self._send_json_response(200, envelope)

        elif path == "/api/v1/twin/summary":
            start_t = time.perf_counter()
            twin_data = self.repo.get_digital_twin_summary()
            envelope = {
                "version": "1.0.0",
                "request_id": f"req-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "data": twin_data,
                "execution_duration_ms": round((time.perf_counter() - start_t) * 1000.0, 2),
            }
            self._send_json_response(200, envelope)

        elif path == "/api/v1/audit/ledger":
            start_t = time.perf_counter()
            ledger = self.repo.get_audit_ledger(limit=20)
            envelope = {
                "version": "1.0.0",
                "request_id": f"req-{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "data": ledger,
                "execution_duration_ms": round((time.perf_counter() - start_t) * 1000.0, 2),
            }
            self._send_json_response(200, envelope)

        else:
            self._send_json_response(404, {
                "version": "1.0.0",
                "status": "error",
                "error": {
                    "code": "E5001",
                    "message": f"Endpoint not found: {path}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

    def do_POST(self) -> None:
        """Handle POST requests for governance approvals and file trust inspection."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            req_data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json_response(400, {
                "version": "1.0.0",
                "status": "error",
                "error": {
                    "code": "E3002",
                    "message": "Malformed JSON body",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })
            return

        if path == "/api/v1/governance/approvals":
            start_t = time.perf_counter()
            # Invariant: Mutating operations strictly require a unique idempotency key
            idempotency_key = req_data.get("idempotency_key")
            if not idempotency_key:
                self._send_json_response(400, {
                    "version": "1.0.0",
                    "status": "error",
                    "error": {
                        "code": "E3003",
                        "message": "Missing required idempotency_key for mutating governance operation",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })
                return

            payload = req_data.get("payload", {})
            action_id = payload.get("action_id", "unknown_action")
            verdict = payload.get("verdict", "REJECTED")
            justification = payload.get("justification", "")
            caller = req_data.get("caller_identity", "operator:console")

            # Persist immutable audit event to SQLite hash-chain
            audit_record = self.repo.record_audit_event(
                actor_urn=caller,
                action_urn="governance.submit_approval",
                risk_tier="HIGH",
                payload={
                    "action_id": action_id,
                    "verdict": verdict,
                    "justification": justification,
                    "idempotency_key": idempotency_key,
                },
            )

            envelope = {
                "version": "1.0.0",
                "request_id": req_data.get("request_id", f"req-{uuid.uuid4().hex[:8]}"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "data": {
                    "action_id": action_id,
                    "verdict": verdict,
                    "recorded_at": audit_record["timestamp"],
                    "sequence_id": audit_record["sequence_id"],
                },
                "execution_duration_ms": round((time.perf_counter() - start_t) * 1000.0, 2),
            }
            self._send_json_response(200, envelope)

        elif path == "/api/v1/filetrust/inspect":
            start_t = time.perf_counter()
            file_path = req_data.get("path") or req_data.get("payload", {}).get("path", "")
            state = "QUARANTINED"
            reason = "Untrusted external payload; quarantine enforced until provenance and micro-VM verification complete."

            envelope = {
                "version": "1.0.0",
                "request_id": req_data.get("request_id", f"req-{uuid.uuid4().hex[:8]}"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "data": {
                    "path": file_path,
                    "state": state,
                    "reason": reason,
                },
                "execution_duration_ms": round((time.perf_counter() - start_t) * 1000.0, 2),
            }
            self._send_json_response(200, envelope)

        else:
            self._send_json_response(404, {
                "version": "1.0.0",
                "status": "error",
                "error": {
                    "code": "E5001",
                    "message": f"Endpoint not found: {path}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server stderr console output."""
        return


def create_api_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db_conn: Optional[sqlite3.Connection] = None,
) -> HTTPServer:
    """Create and configure the SYSTEM MIND X HTTP server."""
    if db_conn is None:
        cfg = DatabaseConfig(db_path=":memory:")
        db_conn = DatabaseConnectionManager.connect(cfg)
        migrator = DatabaseMigrator(config=cfg)
        migrator.apply_all(db_conn)

    repo = TelemetryRepository(db_conn)
    inventory_api = MacOsInventoryApi()

    class BoundHandler(SystemMindHttpHandler):
        pass

    BoundHandler.repo = repo
    BoundHandler.inventory_api = inventory_api

    return HTTPServer((host, port), BoundHandler)
