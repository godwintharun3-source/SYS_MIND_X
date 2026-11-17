"""Strongly-typed data models for macOS Endpoint Security integration feasibility and entitlement telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Dict, List, Optional


class EsClientResultCode(int, Enum):
    """Native Darwin Apple Endpoint Security es_new_client_result_t return codes."""

    SUCCESS = 0
    ERR_INVALID_ARGUMENT = 1
    ERR_INTERNAL = 2
    ERR_NOT_ENTITLED = 3
    ERR_NOT_PERMITTED = 4
    ERR_NOT_PRIVILEGED = 5
    ERR_TOO_MANY_CLIENTS = 6


class EsStatus(str, Enum):
    """Categorical status of Apple Endpoint Security feasibility on the host."""

    AVAILABLE_ENTITLED = "AVAILABLE_ENTITLED"
    RESTRICTED_MISSING_ENTITLEMENT = "RESTRICTED_MISSING_ENTITLEMENT"
    RESTRICTED_NOT_ROOT = "RESTRICTED_NOT_ROOT"
    RESTRICTED_SIP_ACTIVE = "RESTRICTED_SIP_ACTIVE"
    UNAVAILABLE_PLATFORM = "UNAVAILABLE_PLATFORM"
    MOCK_ACTIVE = "MOCK_ACTIVE"


class EsEventType(str, Enum):
    """Key macOS Endpoint Security event subscriptions."""

    AUTH_EXEC = "AUTH_EXEC"
    AUTH_OPEN = "AUTH_OPEN"
    NOTIFY_EXEC = "NOTIFY_EXEC"
    NOTIFY_OPEN = "NOTIFY_OPEN"
    NOTIFY_FORK = "NOTIFY_FORK"
    NOTIFY_EXIT = "NOTIFY_EXIT"
    NOTIFY_CREATE = "NOTIFY_CREATE"
    NOTIFY_CLOSE = "NOTIFY_CLOSE"
    NOTIFY_UNLINK = "NOTIFY_UNLINK"
    NOTIFY_MMAP = "NOTIFY_MMAP"
    NOTIFY_SIGNAL = "NOTIFY_SIGNAL"


class EsActionType(str, Enum):
    """Apple Endpoint Security action types (observational notify vs intercepting auth)."""

    AUTH = "AUTH"
    NOTIFY = "NOTIFY"


@dataclass(frozen=True)
class EsEntitlementCheck:
    """Audit of host entitlement, privilege, and environment requirements for Endpoint Security."""

    has_endpoint_security_entitlement: bool
    is_root: bool
    uid: int
    sip_enabled: bool
    sip_status_raw: str
    tcc_full_disk_access_probable: bool
    framework_binary_present: bool
    framework_path: str
    entitlement_key: str = "com.apple.developer.endpoint-security.client"
    team_id: Optional[str] = None
    diagnostics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert entitlement check to dictionary representation."""
        return {
            "has_endpoint_security_entitlement": self.has_endpoint_security_entitlement,
            "entitlement_key": self.entitlement_key,
            "is_root": self.is_root,
            "uid": self.uid,
            "sip_enabled": self.sip_enabled,
            "sip_status_raw": self.sip_status_raw,
            "tcc_full_disk_access_probable": self.tcc_full_disk_access_probable,
            "framework_binary_present": self.framework_binary_present,
            "framework_path": self.framework_path,
            "team_id": self.team_id,
            "diagnostics": list(self.diagnostics),
        }


@dataclass(frozen=True)
class EsEventSample:
    """Sample event notification captured or simulated via Endpoint Security."""

    event_id: str
    event_type: EsEventType
    action_type: EsActionType
    timestamp: str
    process_pid: int
    process_ppid: int
    executable_path: str
    target_path: Optional[str] = None
    cdhash: Optional[str] = None
    signing_id: Optional[str] = None
    team_id: Optional[str] = None
    is_platform_binary: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert event sample to dictionary representation."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "action_type": self.action_type.value,
            "timestamp": self.timestamp,
            "process_pid": self.process_pid,
            "process_ppid": self.process_ppid,
            "executable_path": self.executable_path,
            "target_path": self.target_path,
            "cdhash": self.cdhash,
            "signing_id": self.signing_id,
            "team_id": self.team_id,
            "is_platform_binary": self.is_platform_binary,
        }


@dataclass(frozen=True)
class EsFeasibilityReport:
    """Comprehensive Endpoint Security feasibility assessment, entitlement audit, and fallback telemetry."""

    status: EsStatus
    result_code: EsClientResultCode
    entitlement_check: EsEntitlementCheck
    supported_event_types: List[EsEventType]
    fallback_strategies: Dict[str, str]
    sample_events: List[EsEventSample]
    timestamp: str
    unavailable_telemetry: List[str]
    host_platform: str = "Darwin"
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe
    is_mock: bool = False

    @property
    def is_operational(self) -> bool:
        """Return True only if native Endpoint Security client is fully operational with entitlements."""
        return self.status == EsStatus.AVAILABLE_ENTITLED and not self.is_mock

    @property
    def requires_escalation(self) -> bool:
        """Return True if running Endpoint Security natively would require root or Apple entitlement escalation."""
        return self.status in (
            EsStatus.RESTRICTED_NOT_ROOT,
            EsStatus.RESTRICTED_MISSING_ENTITLEMENT,
            EsStatus.RESTRICTED_SIP_ACTIVE,
        )

    @property
    def has_fallback(self) -> bool:
        """Return True if unprivileged fallback telemetry strategies are configured and active."""
        return len(self.fallback_strategies) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert feasibility report to dictionary representation."""
        return {
            "status": self.status.value,
            "result_code": self.result_code.value,
            "result_code_name": self.result_code.name,
            "host_platform": self.host_platform,
            "entitlement_check": self.entitlement_check.to_dict(),
            "supported_event_types": [e.value for e in self.supported_event_types],
            "fallback_strategies": dict(self.fallback_strategies),
            "sample_events": [ev.to_dict() for ev in self.sample_events],
            "timestamp": self.timestamp,
            "scan_proves_safe": self.scan_proves_safe,
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "is_mock": self.is_mock,
            "is_operational": self.is_operational,
            "requires_escalation": self.requires_escalation,
            "has_fallback": self.has_fallback,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
