"""Unit and integration tests for structured logging and sensitive-data redaction."""

from __future__ import annotations

import io
import json
import logging
import pytest

from system_mind.config.secrets import SecretStr
from system_mind.logging import (
    SensitiveDataRedactingFilter,
    StructuredJsonFormatter,
    StructuredLogger,
    configure_logging,
    get_logger,
)
from system_mind.packaging import (
    LoggingConfigAuditResult,
    LoggingConfigValidator,
)


def test_structured_json_formatter_keys_and_schema():
    """Verify that StructuredJsonFormatter outputs valid single-line JSON with all schema keys."""
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="system_mind.control_plane",
        level=logging.INFO,
        pathname="control_plane.py",
        lineno=10,
        msg="operator_action_evaluated",
        args=(),
        exc_info=None,
    )
    record.context = {
        "operation": "update_check",
        "component": "com.apple.SecurityUpdate",
        "trace_id": "tr-uuid-001",
        "span_id": "span-001",
    }

    formatted_str = formatter.format(record)
    assert "\n" not in formatted_str  # Must be single line

    parsed = json.loads(formatted_str)
    assert parsed["level"] == "INFO"
    assert parsed["subsystem"] == "system_mind.control_plane"
    assert parsed["event"] == "operator_action_evaluated"
    assert parsed["trace_id"] == "tr-uuid-001"
    assert parsed["span_id"] == "span-001"
    assert parsed["context"]["operation"] == "update_check"
    assert parsed["context"]["component"] == "com.apple.SecurityUpdate"
    assert parsed["exception"] is None
    assert "T" in parsed["timestamp_iso"]


def test_redacting_filter_sanitizes_tokens_and_headers():
    """Verify SensitiveDataRedactingFilter sanitizes API tokens, bearer headers, and private keys."""
    redactor = SensitiveDataRedactingFilter()

    # 1. Bearer header and GitHub token in msg
    rec1 = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname="t.py",
        lineno=1,
        msg="Failed request with Bearer eyJhbGciOiJIUzI1Ni... and token ghp_111122223333444455556666777788889999",
        args=(),
        exc_info=None,
    )
    redactor.filter(rec1)
    assert "ghp_" not in rec1.msg
    assert "eyJhbGciOiJIUzI1Ni..." not in rec1.msg
    assert "[REDACTED_SECRET]" in rec1.msg

    # 2. Private key block in msg
    rec2 = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="t.py",
        lineno=1,
        msg="Loaded key: -----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
        args=(),
        exc_info=None,
    )
    redactor.filter(rec2)
    assert "MIIEowIBAAKCAQEA" not in rec2.msg
    assert "[REDACTED_SECRET]" in rec2.msg

    # 3. Sensitive arguments (tuple/list/dict)
    rec3 = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="t.py",
        lineno=1,
        msg="User %s attempted login with password %s",
        args=("admin", "SuperSecretPass123!"),
        exc_info=None,
    )
    rec3.context = {"api_key": "sk-live-secret-token-12345", "role": "admin"}
    redactor.filter(rec3)
    assert rec3.context["api_key"] == "[REDACTED_SECRET]"
    assert rec3.context["role"] == "admin"


def test_structured_logger_context_binding():
    """Verify that StructuredLogger.bind() creates immutable scoped context."""
    raw_logger = logging.getLogger("test_context_binding")
    base_logger = StructuredLogger(raw_logger, {"service": "twin_service"})

    child_logger = base_logger.bind(trace_id="tr-abc-123", actor="operator:console")

    assert "service" in base_logger._context
    assert "trace_id" not in base_logger._context  # Parent untouched

    assert child_logger._context["service"] == "twin_service"
    assert child_logger._context["trace_id"] == "tr-abc-123"
    assert child_logger._context["actor"] == "operator:console"


def test_structured_logger_end_to_end_emission_and_redaction():
    """Verify end-to-end emission through StructuredLogger scrubs secrets and formats JSON."""
    buf = io.StringIO()
    configure_logging(level="DEBUG", stream=buf, logger_name="e2e_logger")
    logger = get_logger("e2e_logger")

    raw_token = "ghp_SECRET_TOKEN_DO_NOT_PRINT_0001"
    raw_password = "SuperSecretPassword999!"
    raw_secret_str = SecretStr("internal_signing_key_4444")

    logger.info(
        "operator_session_started",
        operator="admin",
        password=raw_password,
        api_token=raw_token,
        wrapped_key=raw_secret_str,
        safe_metric=42,
    )

    output = buf.getvalue().strip()
    assert output != ""
    assert "\n" not in output  # Single-line JSON

    # Assert no plaintext secrets leaked
    assert raw_token not in output
    assert raw_password not in output
    assert "internal_signing_key_4444" not in output

    parsed = json.loads(output)
    assert parsed["level"] == "INFO"
    assert parsed["event"] == "operator_session_started"
    assert parsed["context"]["operator"] == "admin"
    assert parsed["context"]["safe_metric"] == 42
    assert parsed["context"]["password"] == "[REDACTED_SECRET]"
    assert parsed["context"]["api_token"] == "[REDACTED_SECRET]"
    assert parsed["context"]["wrapped_key"] == "***REDACTED***"


def test_structured_logger_exception_traceback_sanitization():
    """Verify that exception tracebacks containing sensitive tokens are sanitized."""
    buf = io.StringIO()
    configure_logging(level="ERROR", stream=buf, logger_name="exc_logger")
    logger = get_logger("exc_logger")

    secret_in_error = "ghp_CRITICAL_SECRET_IN_TRACEBACK_1234"
    try:
        raise RuntimeError(f"Connection failed to auth server with token: {secret_in_error}")
    except RuntimeError:
        logger.error("database_connection_failed", exc_info=True)

    output = buf.getvalue().strip()
    assert secret_in_error not in output

    parsed = json.loads(output)
    assert parsed["level"] == "ERROR"
    assert parsed["exception"] is not None
    assert "[REDACTED_SECRET]" in parsed["exception"]
    assert secret_in_error not in parsed["exception"]


def test_logging_config_validator_audits_clean():
    """Verify that LoggingConfigValidator passes all audit checks on the codebase."""
    result = LoggingConfigValidator.audit_logging_configuration()

    assert result.is_valid is True
    assert len(result.issues) == 0
    assert result.formatter_configured is True
    assert result.filter_configured is True
    assert result.logger_factory_functional is True
    assert result.redaction_verified is True


def test_structured_logger_level_thresholding():
    """Verify that events below configured logging level are discarded."""
    buf = io.StringIO()
    configure_logging(level="WARNING", stream=buf, logger_name="threshold_logger")
    logger = get_logger("threshold_logger")

    logger.debug("debug_event", key="debug_value")
    logger.info("info_event", key="info_value")
    assert buf.getvalue() == ""

    logger.warning("warning_event", key="warning_value")
    assert "warning_event" in buf.getvalue()


def test_structured_logger_positional_args_redaction():
    """Verify that positional string formatting arguments with tokens are sanitized."""
    buf = io.StringIO()
    configure_logging(level="INFO", stream=buf, logger_name="args_logger")
    logger = get_logger("args_logger")

    token = "ghp_TOKEN_IN_ARGS_99998888"
    logger.info("Connected user %s with key %s", "operator", token)

    output = buf.getvalue().strip()
    assert token not in output
    assert "[REDACTED_SECRET]" in output
