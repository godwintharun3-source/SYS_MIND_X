"""Strongly-typed data models for macOS application signatures and notarization telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SignatureStatus(str, Enum):
    """Cryptographic code signature verification status."""

    SIGNED_VALID = "SIGNED_VALID"  # Valid signature matching CodeDirectory and root CA
    SIGNED_INVALID = "SIGNED_INVALID"  # Signature exists but corrupted, tampered, or expired
    UNSIGNED = "UNSIGNED"  # No Mach-O code signature present
    ADHOC_SIGNED = "ADHOC_SIGNED"  # Ad-hoc signed without root CA anchor
    UNKNOWN = "UNKNOWN"  # Inspection inconclusive or unsupported platform


class NotarizationStatus(str, Enum):
    """Apple Gatekeeper notarization status."""

    NOTARIZED_DEVELOPER_ID = "NOTARIZED_DEVELOPER_ID"  # Valid Apple notarization ticket confirmed
    APPLE_SYSTEM = "APPLE_SYSTEM"  # First-party Apple macOS system binary
    MAC_APP_STORE = "MAC_APP_STORE"  # Mac App Store verified receipt/signing
    NOT_NOTARIZED = "NOT_NOTARIZED"  # Signed developer binary without Apple notarization ticket
    REJECTED = "REJECTED"  # Rejected by Gatekeeper policy
    NOT_APPLICABLE = "NOT_APPLICABLE"  # Unsigned or ad-hoc binary
    UNKNOWN = "UNKNOWN"  # Unassessed or unsupported platform


class SigningAuthorityType(str, Enum):
    """Type of certificate authority anchor."""

    APPLE_SYSTEM = "APPLE_SYSTEM"  # Apple Inc. Software Signing
    DEVELOPER_ID = "DEVELOPER_ID"  # Apple Developer Program identified developer
    APP_STORE = "APP_STORE"  # Mac App Store verified certificate
    ADHOC = "ADHOC"  # Ad-hoc local signing (-)
    THIRD_PARTY_CA = "THIRD_PARTY_CA"  # Custom or corporate enterprise CA
    UNSIGNED = "UNSIGNED"  # Unsigned
    UNKNOWN = "UNKNOWN"  # Unverified


@dataclass(frozen=True)
class MacAppSignatureInfo:
    """Strongly-typed code signature and notarization metadata for a macOS application bundle."""

    bundle_id: str
    bundle_path: str
    executable_path: Optional[str] = None
    signature_status: SignatureStatus = SignatureStatus.UNKNOWN
    notarization_status: NotarizationStatus = NotarizationStatus.UNKNOWN
    authority_type: SigningAuthorityType = SigningAuthorityType.UNKNOWN
    authorities: List[str] = field(default_factory=list)
    team_id: Optional[str] = None
    cdhash: Optional[str] = None
    is_hardened_runtime: bool = False
    is_apple: bool = False
    is_valid: bool = False
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe

    @property
    def is_signed(self) -> bool:
        """Return True if application has a valid code signature."""
        return self.signature_status == SignatureStatus.SIGNED_VALID

    @property
    def is_notarized(self) -> bool:
        """Return True if application is notarized by Apple or is an Apple system component."""
        return self.notarization_status in (
            NotarizationStatus.NOTARIZED_DEVELOPER_ID,
            NotarizationStatus.APPLE_SYSTEM,
            NotarizationStatus.MAC_APP_STORE,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert signature model to dictionary representation."""
        return {
            "bundle_id": self.bundle_id,
            "bundle_path": self.bundle_path,
            "executable_path": self.executable_path,
            "signature_status": self.signature_status.value,
            "notarization_status": self.notarization_status.value,
            "authority_type": self.authority_type.value,
            "authorities": list(self.authorities),
            "team_id": self.team_id,
            "cdhash": self.cdhash,
            "is_hardened_runtime": self.is_hardened_runtime,
            "is_apple": self.is_apple,
            "is_valid": self.is_valid,
            "is_signed": self.is_signed,
            "is_notarized": self.is_notarized,
            "scan_proves_safe": self.scan_proves_safe,
        }


@dataclass(frozen=True)
class MacAppSignatureReport:
    """Comprehensive read-only telemetry snapshot of application signatures and notarization."""

    collection_method: str
    timestamp: str
    host_platform: str
    signatures: List[MacAppSignatureInfo] = field(default_factory=list)
    inspected_apps_count: int = 0
    validly_signed_count: int = 0
    notarized_count: int = 0
    apple_system_count: int = 0
    unsigned_count: int = 0
    warnings: List[str] = field(default_factory=list)
    unavailable_telemetry: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe

    def find_by_bundle_id(self, bundle_id: str) -> Optional[MacAppSignatureInfo]:
        """Find signature metadata by exact reverse-DNS bundle identifier."""
        target = bundle_id.lower()
        for s in self.signatures:
            if s.bundle_id.lower() == target:
                return s
        return None

    def find_by_bundle_path(self, bundle_path: str) -> Optional[MacAppSignatureInfo]:
        """Find signature metadata by application bundle path."""
        target = bundle_path.rstrip("/").lower()
        for s in self.signatures:
            if s.bundle_path.rstrip("/").lower() == target:
                return s
        return None

    def filter_by_status(self, status: SignatureStatus) -> List[MacAppSignatureInfo]:
        """Filter signatures by verification status."""
        return [s for s in self.signatures if s.signature_status == status]

    def filter_by_notarization(self, status: NotarizationStatus) -> List[MacAppSignatureInfo]:
        """Filter signatures by Gatekeeper notarization status."""
        return [s for s in self.signatures if s.notarization_status == status]

    def filter_by_authority(self, authority_type: SigningAuthorityType) -> List[MacAppSignatureInfo]:
        """Filter signatures by signing authority type."""
        return [s for s in self.signatures if s.authority_type == authority_type]

    def to_dict(self) -> Dict[str, Any]:
        """Convert complete signature report to dictionary structure."""
        return {
            "collection_method": self.collection_method,
            "timestamp": self.timestamp,
            "host_platform": self.host_platform,
            "inspected_apps_count": self.inspected_apps_count,
            "validly_signed_count": self.validly_signed_count,
            "notarized_count": self.notarized_count,
            "apple_system_count": self.apple_system_count,
            "unsigned_count": self.unsigned_count,
            "signatures": [s.to_dict() for s in self.signatures],
            "warnings": list(self.warnings),
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "scan_proves_safe": self.scan_proves_safe,
        }
