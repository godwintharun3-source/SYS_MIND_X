"""macOS system agent and read-only telemetry collection module for SYSTEM MIND X."""

from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.models import (
    MacArchitecture,
    MacHostIdentity,
    MacOSVersionInfo,
    MacTelemetryReport,
)

__all__ = [
    "MacArchitecture",
    "MacHostIdentity",
    "MacOSIdentityDetector",
    "MacOSVersionInfo",
    "MacTelemetryReport",
]
