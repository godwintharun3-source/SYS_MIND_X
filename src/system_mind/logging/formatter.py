"""Canonical JSON structured log formatter with sensitive-data scrubbing."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional

from system_mind.audit.ledger import SecretRedactor
from system_mind.logging.filter import SensitiveDataRedactingFilter


class StructuredJsonFormatter(logging.Formatter):
    """Formats LogRecord instances into single-line JSON objects with deep redaction."""

    # Standard internal LogRecord attributes to exclude from structured context
    RESERVED_ATTRS = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "id",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "trace_id",
        "span_id",
        "context",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Serializes the log record to a single-line JSON string."""
        # Ensure redacting filter logic has run
        record_msg = record.getMessage()
        sanitized_msg = SensitiveDataRedactingFilter.sanitize_string(record_msg)

        # 1. Base log structure
        timestamp_iso = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

        # 2. Extract correlation IDs
        context_data = getattr(record, "context", {})
        if not isinstance(context_data, dict):
            context_data = {"raw_context": str(context_data)}

        trace_id = getattr(record, "trace_id", context_data.get("trace_id"))
        span_id = getattr(record, "span_id", context_data.get("span_id"))

        # 3. Collect extra context attributes passed to logger
        merged_context: Dict[str, Any] = dict(context_data)
        for key, val in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                merged_context[key] = val

        # Deep redaction on context
        sanitized_context = SecretRedactor.redact(merged_context)

        # 4. Format exception if present
        exception_str: Optional[str] = None
        if record.exc_info:
            formatted_exc = self.formatException(record.exc_info)
            exception_str = SensitiveDataRedactingFilter.sanitize_string(formatted_exc)

        # 5. Assemble structured payload
        payload = {
            "timestamp_iso": timestamp_iso,
            "level": record.levelname,
            "subsystem": record.name,
            "event": sanitized_msg,
            "trace_id": trace_id,
            "span_id": span_id,
            "context": sanitized_context,
            "exception": exception_str,
        }

        # Return single-line JSON string
        return json.dumps(payload, default=self._json_default, ensure_ascii=False)

    @staticmethod
    def _json_default(obj: Any) -> Any:
        """Fallback serializer for custom classes and SecretStr instances."""
        if hasattr(obj, "__str__"):
            return str(obj)
        return repr(obj)
