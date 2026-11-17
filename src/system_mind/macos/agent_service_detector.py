"""Read-only macOS least-privilege user agent service manager and inspector."""

from __future__ import annotations

from datetime import datetime, timezone
import getpass
import logging
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.agent_service_models import (
    AgentServiceState,
    AgentServiceStatusReport,
    LaunchAgentConfig,
)
from system_mind.macos.services_models import ServiceDomain, ServiceStatus

logger = logging.getLogger(__name__)

DEFAULT_AGENT_LABEL = "com.systemmind.useragent"
DEFAULT_PLIST_FILENAME = f"{DEFAULT_AGENT_LABEL}.plist"


class MacUserAgentServiceManager:
    """Read-only inspector and declarative configurator for least-privilege macOS user agents."""

    def __init__(
        self,
        plist_path: Optional[Path] = None,
        custom_uid: Optional[int] = None,
        label: str = DEFAULT_AGENT_LABEL,
    ) -> None:
        self.label = label
        self.uid = custom_uid if custom_uid is not None else (os.geteuid() if hasattr(os, "geteuid") else 501)
        self.console_user = getpass.getuser() if hasattr(getpass, "getuser") else "unknown"
        self.plist_path = plist_path or (Path.home() / "Library" / "LaunchAgents" / DEFAULT_PLIST_FILENAME)

    def is_root(self) -> bool:
        """Return True if executing process holds elevated root authority."""
        return self.uid == 0

    def generate_launchagent_plist(
        self,
        companion_binary: Optional[str] = None,
        run_at_load: bool = False,
    ) -> str:
        """Generate a valid, least-privilege Apple launchd LaunchAgent XML specification."""
        binary = companion_binary or "/usr/local/bin/system-mind-companion"
        config = LaunchAgentConfig(
            label=self.label,
            program_arguments=[binary, "--daemon"],
            run_at_load=run_at_load,
            keep_alive=True,
            limit_load_to_session_type=["Aqua"],
            standard_out_path=f"~/Library/Logs/system-mind/{self.label}.stdout.log",
            standard_error_path=f"~/Library/Logs/system-mind/{self.label}.stderr.log",
            process_type="Background",
            nice=10,
        )
        return config.to_plist_xml()

    def get_status(self) -> AgentServiceStatusReport:
        """Get live or current status report."""
        return self.inspect_service(use_mock=False)

    def get_mock_status(self, profile: str = "running") -> AgentServiceStatusReport:
        """Get deterministic mock status report."""
        return self.inspect_service(use_mock=True, profile=profile)

    def inspect_service(self, use_mock: bool = False, profile: str = "running") -> AgentServiceStatusReport:
        """Inspect the current user agent service registration and runtime status."""
        now_iso = datetime.now(timezone.utc).isoformat()

        if use_mock:
            return self._generate_mock_report(profile=profile, timestamp=now_iso)

        if platform.system() != "Darwin":
            return self._generate_mock_report(profile="unsupported", timestamp=now_iso)

        pid: Optional[int] = None
        last_exit: Optional[int] = None
        service_status = ServiceStatus.UNKNOWN
        service_state = AgentServiceState.NOT_INSTALLED
        unavailable_telemetry: List[str] = []

        plist_on_disk = self.plist_path.exists()

        # Query launchd for registration in gui/$UID domain
        found_in_launchd, raw_pid, raw_exit = self._query_launchctl_gui()

        if found_in_launchd:
            pid = raw_pid
            last_exit = raw_exit
            if pid and pid > 0:
                service_status = ServiceStatus.RUNNING
                service_state = AgentServiceState.INSTALLED_ACTIVE
            else:
                service_status = ServiceStatus.LOADED_WAITING
                service_state = AgentServiceState.INSTALLED_INACTIVE
        elif plist_on_disk:
            service_status = ServiceStatus.DEFINITION_ONLY
            service_state = AgentServiceState.INSTALLED_INACTIVE
        else:
            service_status = ServiceStatus.UNKNOWN
            service_state = AgentServiceState.NOT_INSTALLED
            unavailable_telemetry.append("service_not_registered_in_launchd")

        config = LaunchAgentConfig(
            label=self.label,
            program_arguments=["/usr/local/bin/system-mind-companion", "--daemon"],
            run_at_load=False,
            keep_alive=True,
            limit_load_to_session_type=["Aqua"],
            standard_out_path=f"~/Library/Logs/system-mind/{self.label}.stdout.log",
            standard_error_path=f"~/Library/Logs/system-mind/{self.label}.stderr.log",
            process_type="Background",
            nice=10,
        )

        return AgentServiceStatusReport(
            label=self.label,
            domain=ServiceDomain.USER_AGENT,
            state=service_state,
            status=service_status,
            pid=pid,
            last_exit_code=last_exit,
            plist_path=str(self.plist_path),
            is_root=self.is_root(),
            uid=self.uid,
            console_user=self.console_user,
            config=config,
            timestamp=now_iso,
            host_platform="Darwin",
            scan_proves_safe=False,  # Enforce non-negotiable charter invariant
            unavailable_telemetry=unavailable_telemetry,
            is_mock=False,
        )

    def _query_launchctl_gui(self) -> Tuple[bool, Optional[int], Optional[int]]:
        """Query Darwin launchctl print gui/$UID/<label> safely without mutating state."""
        launchctl_bin = "/bin/launchctl"
        if not Path(launchctl_bin).exists():
            return False, None, None

        domain_target = f"gui/{self.uid}/{self.label}"
        try:
            res = subprocess.run(
                [launchctl_bin, "print", domain_target],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                output = res.stdout
                pid = None
                pid_match = re.search(r"pid\s*=\s*(\d+)", output)
                if pid_match:
                    pid = int(pid_match.group(1))

                last_exit = None
                exit_match = re.search(r"last exit code\s*=\s*(-?\d+)", output)
                if exit_match:
                    last_exit = int(exit_match.group(1))

                return True, pid, last_exit

            # Fallback to launchctl list in user domain
            list_res = subprocess.run(
                [launchctl_bin, "list"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            for line in list_res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[2] == self.label:
                    pid = int(parts[0]) if parts[0] != "-" else None
                    last_exit = int(parts[1]) if parts[1] != "-" else None
                    return True, pid, last_exit

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("launchctl query failed: %s", e)

        return False, None, None

    def _generate_mock_report(self, profile: str, timestamp: str) -> AgentServiceStatusReport:
        """Produce deterministic mock reports across test profiles."""
        default_config = LaunchAgentConfig(
            label=self.label,
            program_arguments=["/usr/local/bin/system-mind-companion", "--daemon"],
            run_at_load=False,
            keep_alive=True,
            limit_load_to_session_type=["Aqua"],
            standard_out_path=f"~/Library/Logs/system-mind/{self.label}.stdout.log",
            standard_error_path=f"~/Library/Logs/system-mind/{self.label}.stderr.log",
            process_type="Background",
            nice=10,
        )

        if profile == "stopped":
            return AgentServiceStatusReport(
                label=self.label,
                domain=ServiceDomain.USER_AGENT,
                state=AgentServiceState.INSTALLED_INACTIVE,
                status=ServiceStatus.LOADED_WAITING,
                pid=None,
                last_exit_code=0,
                plist_path=str(self.plist_path),
                is_root=False,
                uid=501,
                console_user="developer",
                config=default_config,
                timestamp=timestamp,
                host_platform="Darwin",
                scan_proves_safe=False,
                unavailable_telemetry=["process_inactive"],
                is_mock=True,
            )

        elif profile == "uninstalled":
            return AgentServiceStatusReport(
                label=self.label,
                domain=ServiceDomain.USER_AGENT,
                state=AgentServiceState.NOT_INSTALLED,
                status=ServiceStatus.UNKNOWN,
                pid=None,
                last_exit_code=None,
                plist_path=str(self.plist_path),
                is_root=False,
                uid=501,
                console_user="developer",
                config=default_config,
                timestamp=timestamp,
                host_platform="Darwin",
                scan_proves_safe=False,
                unavailable_telemetry=["service_not_installed"],
                is_mock=True,
            )

        elif profile == "unsupported":
            return AgentServiceStatusReport(
                label=self.label,
                domain=ServiceDomain.UNKNOWN,
                state=AgentServiceState.UNAVAILABLE_PLATFORM,
                status=ServiceStatus.UNKNOWN,
                pid=None,
                last_exit_code=None,
                plist_path="None",
                is_root=False,
                uid=1000,
                console_user="linuxuser",
                config=default_config,
                timestamp=timestamp,
                host_platform="Linux",
                scan_proves_safe=False,
                unavailable_telemetry=["apple_launchd_unsupported", "aqua_session_unsupported"],
                is_mock=True,
            )

        # Default profile: "running"
        return AgentServiceStatusReport(
            label=self.label,
            domain=ServiceDomain.USER_AGENT,
            state=AgentServiceState.INSTALLED_ACTIVE,
            status=ServiceStatus.RUNNING,
            pid=4120,
            last_exit_code=0,
            plist_path=str(self.plist_path),
            is_root=False,
            uid=501,
            console_user="developer",
            config=default_config,
            timestamp=timestamp,
            host_platform="Darwin",
            scan_proves_safe=False,
            unavailable_telemetry=[],
            is_mock=True,
        )
