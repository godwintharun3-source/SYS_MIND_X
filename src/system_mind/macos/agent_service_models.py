"""Strongly-typed data models for least-privilege macOS user agent background service telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Dict, List, Optional

from system_mind.macos.services_models import ServiceDomain, ServiceStatus


class AgentServiceState(str, Enum):
    """Lifecycle registration state of the macOS user agent service."""

    INSTALLED_ACTIVE = "INSTALLED_ACTIVE"
    INSTALLED_INACTIVE = "INSTALLED_INACTIVE"
    NOT_INSTALLED = "NOT_INSTALLED"
    UNAVAILABLE_PLATFORM = "UNAVAILABLE_PLATFORM"
    MOCK_ACTIVE = "MOCK_ACTIVE"


@dataclass(frozen=True)
class LaunchAgentConfig:
    """Declarative Apple launchd LaunchAgent property list configuration."""

    label: str = "com.systemmind.useragent"
    program_arguments: List[str] = field(
        default_factory=lambda: [
            "/usr/local/bin/system-mind-companion",
            "--daemon",
        ]
    )
    run_at_load: bool = False
    keep_alive: bool = True
    limit_load_to_session_type: List[str] = field(default_factory=lambda: ["Aqua"])
    standard_out_path: str = "~/Library/Logs/system-mind/useragent.stdout.log"
    standard_error_path: str = "~/Library/Logs/system-mind/useragent.stderr.log"
    process_type: str = "Background"
    nice: int = 10

    def to_plist_xml(self) -> str:
        """Generate Apple launchd compliant XML property list string."""
        args_xml = "\n".join(f"        <string>{arg}</string>" for arg in self.program_arguments)
        sessions_xml = "\n".join(f"        <string>{s}</string>" for s in self.limit_load_to_session_type)
        run_at_load_val = "true" if self.run_at_load else "false"
        keep_alive_val = "true" if self.keep_alive else "false"

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.label}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>LimitLoadToSessionType</key>
    <array>
{sessions_xml}
    </array>
    <key>ProcessType</key>
    <string>{self.process_type}</string>
    <key>Nice</key>
    <integer>{self.nice}</integer>
    <key>RunAtLoad</key>
    <{run_at_load_val}/>
    <key>KeepAlive</key>
    <{keep_alive_val}/>
    <key>StandardOutPath</key>
    <string>{self.standard_out_path}</string>
    <key>StandardErrorPath</key>
    <string>{self.standard_error_path}</string>
</dict>
</plist>"""

    def to_dict(self) -> Dict[str, Any]:
        """Convert launch agent configuration to dictionary representation."""
        return {
            "label": self.label,
            "program_arguments": list(self.program_arguments),
            "run_at_load": self.run_at_load,
            "keep_alive": self.keep_alive,
            "limit_load_to_session_type": list(self.limit_load_to_session_type),
            "standard_out_path": self.standard_out_path,
            "standard_error_path": self.standard_error_path,
            "process_type": self.process_type,
            "nice": self.nice,
        }


@dataclass(frozen=True)
class AgentServiceStatusReport:
    """Comprehensive status inspection and configuration report for the macOS user agent service."""

    label: str
    domain: ServiceDomain
    state: AgentServiceState
    status: ServiceStatus
    uid: int
    console_user: str
    config: LaunchAgentConfig
    timestamp: str
    pid: Optional[int] = None
    last_exit_code: Optional[int] = None
    plist_path: str = "~/Library/LaunchAgents/com.systemmind.useragent.plist"
    is_root: bool = False
    host_platform: str = "Darwin"
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe
    unavailable_telemetry: List[str] = field(default_factory=list)
    is_mock: bool = False

    @property
    def is_least_privilege(self) -> bool:
        """Verify that the service strictly adheres to least-privilege user execution invariants."""
        return not self.is_root and self.uid != 0 and self.domain == ServiceDomain.USER_AGENT

    @property
    def is_running(self) -> bool:
        """Return True if background user agent process is currently active with a valid PID."""
        return self.status == ServiceStatus.RUNNING and self.pid is not None and self.pid > 0

    @property
    def is_installed(self) -> bool:
        """Return True if service is registered or installed in launchd."""
        return self.state in (AgentServiceState.INSTALLED_ACTIVE, AgentServiceState.INSTALLED_INACTIVE)

    def to_dict(self) -> Dict[str, Any]:
        """Convert user agent status report to dictionary representation."""
        return {
            "label": self.label,
            "domain": self.domain.value,
            "state": self.state.value,
            "status": self.status.value,
            "pid": self.pid,
            "last_exit_code": self.last_exit_code,
            "plist_path": self.plist_path,
            "is_root": self.is_root,
            "uid": self.uid,
            "console_user": self.console_user,
            "config": self.config.to_dict(),
            "timestamp": self.timestamp,
            "host_platform": self.host_platform,
            "scan_proves_safe": self.scan_proves_safe,
            "unavailable_telemetry": list(self.unavailable_telemetry),
            "is_mock": self.is_mock,
            "is_least_privilege": self.is_least_privilege,
            "is_running": self.is_running,
            "is_installed": self.is_installed,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize status report to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
