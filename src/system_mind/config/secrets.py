"""Secret masking primitives, secret store abstractions, and secret leak detection."""

from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import re
from typing import Any, Dict, List, Optional


class SecretStr:
    """Strongly typed string wrapper guaranteeing secrets are masked in logging and string formatting."""

    REDACTED_TEXT = "***REDACTED***"

    def __init__(self, secret_value: str) -> None:
        if not isinstance(secret_value, str):
            raise TypeError(f"SecretStr requires a string value, got {type(secret_value).__name__}")
        self._secret_value = secret_value

    def get_secret_value(self) -> str:
        """Explicitly unmasks the raw secret value for authorized cryptographic operations."""
        return self._secret_value

    def hash_fingerprint(self) -> str:
        """Returns a deterministic SHA-256 digest of the secret for audit tracking without leaking content."""
        return hashlib.sha256(self._secret_value.encode("utf-8")).hexdigest()

    def __str__(self) -> str:
        return self.REDACTED_TEXT

    def __repr__(self) -> str:
        return f"SecretStr('{self.REDACTED_TEXT}')"

    def __format__(self, format_spec: str) -> str:
        return self.REDACTED_TEXT

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SecretStr):
            return self._secret_value == other._secret_value
        return False

    def __hash__(self) -> int:
        return hash(self._secret_value)

    def __len__(self) -> int:
        return len(self._secret_value)

    def __bool__(self) -> bool:
        return bool(self._secret_value)


class SecretStore(ABC):
    """Abstract interface for local and platform secret storage backends."""

    @abstractmethod
    def store_secret(self, key: str, secret: SecretStr) -> None:
        """Securely store a secret by key."""
        pass

    @abstractmethod
    def get_secret(self, key: str) -> Optional[SecretStr]:
        """Retrieve a stored secret by key, or None if not found."""
        pass

    @abstractmethod
    def delete_secret(self, key: str) -> bool:
        """Remove a stored secret. Returns True if removed, False if not found."""
        pass

    @abstractmethod
    def has_secret(self, key: str) -> bool:
        """Check whether a secret key exists."""
        pass


class MockMemorySecretStore(SecretStore):
    """In-memory secret store for testing, development, and non-privileged mock execution."""

    def __init__(self) -> None:
        self._store: Dict[str, SecretStr] = {}

    def store_secret(self, key: str, secret: SecretStr) -> None:
        if not isinstance(secret, SecretStr):
            raise TypeError(f"Secret must be an instance of SecretStr, got {type(secret).__name__}")
        self._store[key] = secret

    def get_secret(self, key: str) -> Optional[SecretStr]:
        return self._store.get(key)

    def delete_secret(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def has_secret(self, key: str) -> bool:
        return key in self._store

    def clear(self) -> None:
        self._store.clear()


class SecretLeakDetector:
    """Detects credentials, tokens, and cryptographic private keys in text, files, and data structures."""

    PATTERNS: Dict[str, re.Pattern] = {
        "PRIVATE_KEY_HEADER": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "GITHUB_TOKEN": re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}\b"),
        "GITHUB_FINE_GRAINED": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"),
        "OPENAI_KEY": re.compile(r"\bsk-[A-Za-z0-9_-]{20,64}\b"),
        "ANTHROPIC_KEY": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,120}\b"),
        "GOOGLE_API_KEY": re.compile(r"\bAIzaSy[A-Za-z0-9_-]{33}\b"),
        "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "SLACK_TOKEN": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,72}\b"),
        "EXPLICIT_SECRET_ASSIGNMENT": re.compile(
            r"""(?i)(?:api_?key|password|secret|bearer)\s*[:=]\s*["']([^"'\s]{8,})["']"""
        ),
    }

    @classmethod
    def detect_secrets_in_text(cls, text: str) -> List[str]:
        """Scans arbitrary text and returns descriptions of any detected secret patterns."""
        findings: List[str] = []
        for pattern_name, regex in cls.PATTERNS.items():
            matches = regex.findall(text)
            if matches:
                findings.append(f"Detected pattern '{pattern_name}' (matches: {len(matches)})")
        return findings

    @classmethod
    def detect_secrets_in_dict(cls, data: Dict[str, Any], path: str = "") -> List[str]:
        """Recursively checks dictionary keys and values for raw credentials."""
        findings: List[str] = []
        key_sensitive = re.compile(r"(?i)(password|passwd|token|secret|api_?key|credential|private_?key)")

        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            # Check key name
            if key_sensitive.search(str(key)):
                if isinstance(value, str) and not isinstance(value, SecretStr):
                    if value and value != "***REDACTED***" and value != "[REDACTED_SECRET]":
                        findings.append(f"Unmasked secret value in sensitive key '{current_path}'")

            # Check value if string
            if isinstance(value, str):
                text_findings = cls.detect_secrets_in_text(value)
                for f in text_findings:
                    findings.append(f"{current_path}: {f}")
            elif isinstance(value, dict):
                findings.extend(cls.detect_secrets_in_dict(value, current_path))
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    item_path = f"{current_path}[{idx}]"
                    if isinstance(item, str):
                        for f in cls.detect_secrets_in_text(item):
                            findings.append(f"{item_path}: {f}")
                    elif isinstance(item, dict):
                        findings.extend(cls.detect_secrets_in_dict(item, item_path))

        return findings
