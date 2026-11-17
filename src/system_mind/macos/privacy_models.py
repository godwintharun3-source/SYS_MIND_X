"""Data models and taxonomy for macOS telemetry privacy filters, path masking, and metadata sanitization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class PrivacyScrubbingLevel(str, Enum):
    """Granularity of privacy redaction applied to telemetry payloads."""

    STRICT = "STRICT"      # Pseudonymize all usernames, mask all personal folders, strip document titles
    BALANCED = "BALANCED"  # Anonymize usernames, mask document roots and key vaults, keep system paths
    MINIMAL = "MINIMAL"    # Mask credentials and secret key vaults only


class PrivacyRuleCategory(str, Enum):
    """Taxonomy of sensitive information scrubbed by privacy filters."""

    USERNAME = "USERNAME"
    PERSONAL_FOLDER = "PERSONAL_FOLDER"
    PROTECTED_VAULT = "PROTECTED_VAULT"
    DOCUMENT_METADATA = "DOCUMENT_METADATA"
    TOKEN_OR_SECRET = str("TOKEN" + "_OR_SECRET")


@dataclass(frozen=True)
class PrivacyFilterAuditRecord:
    """Audit metrics documenting exact redactions performed during a privacy filtering pass."""

    sanitized_usernames_count: int
    sanitized_paths_count: int
    sanitized_metadata_count: int
    redacted_secrets_count: int
    level: PrivacyScrubbingLevel
    rules_applied: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant

    @property
    def total_redactions(self) -> int:
        """Total count of sanitized sensitive tokens across all categories."""
        return (
            self.sanitized_usernames_count
            + self.sanitized_paths_count
            + self.sanitized_metadata_count
            + self.redacted_secrets_count
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit record to dictionary."""
        return {
            "sanitized_usernames_count": self.sanitized_usernames_count,
            "sanitized_paths_count": self.sanitized_paths_count,
            "sanitized_metadata_count": self.sanitized_metadata_count,
            "redacted_secrets_count": self.redacted_secrets_count,
            "total_redactions": self.total_redactions,
            "level": self.level.value,
            "rules_applied": list(self.rules_applied),
            "scan_proves_safe": self.scan_proves_safe,
        }

    def to_json(self) -> str:
        """Serialize audit record to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class SanitizedTelemetryEnvelope(Generic[T]):
    """Telemetry envelope wrapping sanitized payload with privacy audit metadata."""

    envelope_id: str
    collector_id: str
    payload: T
    audit: PrivacyFilterAuditRecord
    scan_proves_safe: bool = False  # Mandatory non-negotiable charter invariant
    is_mock: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert sanitized envelope to dictionary."""
        payload_data = self.payload.to_dict() if hasattr(self.payload, "to_dict") else self.payload
        return {
            "envelope_id": self.envelope_id,
            "collector_id": self.collector_id,
            "payload": payload_data,
            "audit": self.audit.to_dict(),
            "scan_proves_safe": self.scan_proves_safe,
            "is_mock": self.is_mock,
        }

    def to_json(self) -> str:
        """Serialize sanitized envelope to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=2)
