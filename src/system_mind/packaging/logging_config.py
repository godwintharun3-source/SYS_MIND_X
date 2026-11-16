"""Validator for structured logging configurations, JSON formatting, and automated redaction."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
import logging
from typing import List

from system_mind.logging.filter import SensitiveDataRedactingFilter
from system_mind.logging.formatter import StructuredJsonFormatter
from system_mind.logging.logger import StructuredLogger, configure_logging, get_logger


@dataclass(frozen=True)
class LoggingConfigAuditResult:
    """Audit outcome for structured logging configurations and sensitive data scrubbing."""

    __test__ = False
    is_valid: bool
    formatter_configured: bool
    filter_configured: bool
    logger_factory_functional: bool
    redaction_verified: bool
    issues: List[str] = field(default_factory=list)


class LoggingConfigValidator:
    """Enforces presence and security correctness of structured JSON logging and sensitive data scrubbing."""

    __test__ = False

    @classmethod
    def audit_logging_configuration(cls) -> LoggingConfigAuditResult:
        """Audits the structured logging pipeline, JSON schema compliance, and redaction efficacy."""
        issues: List[str] = []
        formatter_ok = False
        filter_ok = False
        factory_ok = False
        redaction_ok = False

        # 1. Test SensitiveDataRedactingFilter
        try:
            redactor = SensitiveDataRedactingFilter()
            record = logging.LogRecord(
                name="test.audit",
                level=logging.INFO,
                pathname="audit.py",
                lineno=1,
                msg="User authenticated with token ghp_111122223333444455556666777788889999",
                args=(),
                exc_info=None,
            )
            record.context = {"api_key": "secret_key_12345", "public_id": "user_42"}
            redactor.filter(record)

            if "ghp_" in record.msg:
                issues.append("SensitiveDataRedactingFilter failed to redact GitHub token in record.msg.")
            elif record.context.get("api_key") != "[REDACTED_SECRET]":
                issues.append("SensitiveDataRedactingFilter failed to redact sensitive key in record.context.")
            else:
                filter_ok = True
        except Exception as e:
            issues.append(f"SensitiveDataRedactingFilter evaluation raised exception: {e}")

        # 2. Test StructuredJsonFormatter
        try:
            formatter = StructuredJsonFormatter()
            record2 = logging.LogRecord(
                name="system_mind.twin",
                level=logging.INFO,
                pathname="twin.py",
                lineno=42,
                msg="entity_updated",
                args=(),
                exc_info=None,
            )
            record2.context = {"entity_id": "entity:sys:macos", "trace_id": "tr-001"}
            output_json = formatter.format(record2)

            parsed = json.loads(output_json)
            required_keys = {"timestamp_iso", "level", "subsystem", "event", "context"}
            missing_keys = required_keys - set(parsed.keys())
            if missing_keys:
                issues.append(f"StructuredJsonFormatter missing required schema keys: {sorted(missing_keys)}")
            else:
                formatter_ok = True
        except Exception as e:
            issues.append(f"StructuredJsonFormatter evaluation raised exception: {e}")

        # 3. Test StructuredLogger factory and end-to-end emission with redaction
        try:
            buf = io.StringIO()
            configure_logging(level="DEBUG", stream=buf, logger_name="audit_test_logger")
            test_logger = get_logger("audit_test_logger")

            if not isinstance(test_logger, StructuredLogger):
                issues.append(f"get_logger did not return StructuredLogger instance, got {type(test_logger).__name__}")
            else:
                factory_ok = True

                # Emit test event with sensitive data
                test_logger.info(
                    "user_login",
                    username="operator",
                    password="SuperSecretPassword123!",
                    bearer_token="Bearer eyJhbGciOiJIUzI1Ni...",
                    trace_id="tr-test-123",
                )

                log_output = buf.getvalue().strip()
                if not log_output:
                    issues.append("StructuredLogger failed to emit log record to stream.")
                else:
                    parsed_log = json.loads(log_output)
                    ctx = parsed_log.get("context", {})
                    if "SuperSecretPassword123!" in log_output or "eyJhbGciOiJIUzI1Ni..." in log_output:
                        issues.append("Plaintext secret leaked through StructuredLogger emission!")
                    elif ctx.get("password") != "[REDACTED_SECRET]" or ctx.get("bearer_token") != "[REDACTED_SECRET]":
                        issues.append("Sensitive keys in StructuredLogger context were not redacted!")
                    else:
                        redaction_ok = True
        except Exception as e:
            issues.append(f"StructuredLogger end-to-end audit raised exception: {e}")

        is_valid = len(issues) == 0

        return LoggingConfigAuditResult(
            is_valid=is_valid,
            formatter_configured=formatter_ok,
            filter_configured=filter_ok,
            logger_factory_functional=factory_ok,
            redaction_verified=redaction_ok,
            issues=issues,
        )
