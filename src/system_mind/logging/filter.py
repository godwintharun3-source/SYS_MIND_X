"""Logging filter that scrubs sensitive credentials, keys, and tokens from log records."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from system_mind.audit.ledger import SecretRedactor
from system_mind.config.secrets import SecretLeakDetector, SecretStr


class SensitiveDataRedactingFilter(logging.Filter):
    """Intercepts LogRecord instances and redacts credentials from messages, arguments, and context."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitizes record attributes in-place before handlers format or emit the record."""
        # 1. Sanitize message string
        if isinstance(record.msg, str):
            record.msg = self.sanitize_string(record.msg)
        elif isinstance(record.msg, dict):
            record.msg = SecretRedactor.redact(record.msg)

        # 2. Sanitize positional arguments (args)
        if record.args:
            if isinstance(record.args, dict):
                record.args = SecretRedactor.redact(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(self.sanitize_argument(arg) for arg in record.args)
            elif isinstance(record.args, list):
                record.args = [self.sanitize_argument(arg) for arg in record.args]

        # 3. Sanitize extra context dictionary if attached
        if hasattr(record, "context") and isinstance(record.context, dict):
            record.context = SecretRedactor.redact(record.context)

        return True

    @classmethod
    def sanitize_string(cls, text: str) -> str:
        """Replaces known API tokens, bearer headers, and private key blocks in free-form strings."""
        if not text:
            return text

        sanitized = text

        # Check private key headers
        if "-----BEGIN " in sanitized and "PRIVATE KEY-----" in sanitized:
            sanitized = re.sub(
                r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                SecretRedactor.REDACTION_MARKER,
                sanitized,
                flags=re.DOTALL,
            )
            sanitized = re.sub(
                r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                SecretRedactor.REDACTION_MARKER,
                sanitized,
            )

        # Check Bearer authorization tokens
        sanitized = re.sub(
            r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*",
            f"Bearer {SecretRedactor.REDACTION_MARKER}",
            sanitized,
        )

        # Check GitHub token prefixes
        sanitized = re.sub(
            r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{10,255}\b",
            SecretRedactor.REDACTION_MARKER,
            sanitized,
        )
        sanitized = re.sub(
            r"\bgithub_pat_[A-Za-z0-9_]{10,255}\b",
            SecretRedactor.REDACTION_MARKER,
            sanitized,
        )

        # Check OpenAI / Anthropic keys
        sanitized = re.sub(
            r"\bsk-ant-[A-Za-z0-9_-]{10,120}\b",
            SecretRedactor.REDACTION_MARKER,
            sanitized,
        )
        sanitized = re.sub(
            r"\bsk-[A-Za-z0-9_-]{10,64}\b",
            SecretRedactor.REDACTION_MARKER,
            sanitized,
        )

        # Check Google API keys
        sanitized = re.sub(
            r"\bAIzaSy[A-Za-z0-9_-]{10,64}\b",
            SecretRedactor.REDACTION_MARKER,
            sanitized,
        )

        # Check AWS access keys
        sanitized = re.sub(
            r"\bAKIA[0-9A-Z]{16}\b",
            SecretRedactor.REDACTION_MARKER,
            sanitized,
        )

        return sanitized

    @classmethod
    def sanitize_argument(cls, arg: Any) -> Any:
        """Sanitizes an individual log argument."""
        if isinstance(arg, SecretStr):
            return str(arg)
        if isinstance(arg, str):
            return cls.sanitize_string(arg)
        if isinstance(arg, (dict, list)):
            return SecretRedactor.redact(arg)
        return arg
