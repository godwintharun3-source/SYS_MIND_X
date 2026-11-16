"""Read-only macOS launchd services and login-item inventory detector."""

from __future__ import annotations

import logging
from pathlib import Path
import platform
import plistlib
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.services_models import (
    LoginItemKind,
    MacLaunchdService,
    MacLoginItem,
    MacServicesReport,
    ServiceDomain,
    ServiceOwnership,
    ServiceStatus,
)

logger = logging.getLogger(__name__)


class MacServicesDetector:
    """Read-only, passive introspection engine for macOS launchd services and login items."""

    def parse_launchctl_line(self, line: str) -> Optional[Tuple[Optional[int], Optional[int], str]]:
        """Parse a single line from `/bin/launchctl list`.

        Format: `PID\tStatus\tLabel`
        PID: integer or '-' (not running)
        Status: integer exit code (0, non-zero, or negative signal)
        Label: unique string identifier
        """
        if not line or not line.strip():
            return None

        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            return None

        # Ignore header line if present
        if parts[0] == "PID" and parts[1] == "Status":
            return None

        # Parse PID
        pid: Optional[int] = None
        if parts[0] != "-":
            try:
                pid = int(parts[0])
            except ValueError:
                pid = None

        # Parse exit code
        last_exit_code: Optional[int] = None
        try:
            last_exit_code = int(parts[1])
        except ValueError:
            last_exit_code = None

        label = parts[2].strip()
        if not label:
            return None

        return pid, last_exit_code, label

    def parse_launchctl_output(self, output: str) -> List[Tuple[Optional[int], Optional[int], str]]:
        """Parse entire stdout of `launchctl list`."""
        results: List[Tuple[Optional[int], Optional[int], str]] = []
        for line in output.splitlines():
            item = self.parse_launchctl_line(line)
            if item is not None:
                results.append(item)
        return results

    def scan_plist_file(self, plist_path: Path) -> Optional[Dict[str, Any]]:
        """Safely parse a single launchd plist file using standard plistlib."""
        try:
            with open(plist_path, "rb") as fp:
                data = plistlib.load(fp)
            if not isinstance(data, dict):
                return None

            label = data.get("Label")
            if not label or not isinstance(label, str):
                label = plist_path.stem

            # Extract program binary path safely without raw arguments with secrets
            program: Optional[str] = None
            if "Program" in data and isinstance(data["Program"], str):
                program = data["Program"]
            elif "ProgramArguments" in data and isinstance(data["ProgramArguments"], list) and data["ProgramArguments"]:
                first_arg = data["ProgramArguments"][0]
                if isinstance(first_arg, str):
                    program = first_arg

            run_at_load: Optional[bool] = None
            if "RunAtLoad" in data:
                run_at_load = bool(data["RunAtLoad"])

            keep_alive: Optional[bool] = None
            if "KeepAlive" in data:
                keep_alive = bool(data["KeepAlive"])

            return {
                "label": label,
                "plist_path": str(plist_path),
                "program": program,
                "run_at_load": run_at_load,
                "keep_alive": keep_alive,
            }
        except Exception as exc:
            logger.debug(f"Could not parse plist {plist_path}: {exc}")
            return None

    def scan_plist_directories(
        self,
        directories: Optional[List[Tuple[Path, ServiceDomain]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Scan standard macOS launchd configuration directories for service definitions."""
        if directories is None:
            directories = [
                (Path("/System/Library/LaunchDaemons"), ServiceDomain.SYSTEM_DAEMON),
                (Path("/System/Library/LaunchAgents"), ServiceDomain.SYSTEM_AGENT),
                (Path("/Library/LaunchDaemons"), ServiceDomain.GLOBAL_DAEMON),
                (Path("/Library/LaunchAgents"), ServiceDomain.GLOBAL_AGENT),
                (Path.home() / "Library/LaunchAgents", ServiceDomain.USER_AGENT),
            ]

        definitions: Dict[str, Dict[str, Any]] = {}

        for dir_path, domain in directories:
            if not dir_path.exists() or not dir_path.is_dir():
                continue

            try:
                for entry in dir_path.glob("*.plist"):
                    metadata = self.scan_plist_file(entry)
                    if metadata:
                        label = metadata["label"]
                        metadata["domain"] = domain
                        # Prefer user or global overrides if label duplicates
                        definitions[label] = metadata
            except (PermissionError, OSError) as exc:
                logger.debug(f"Permission denied scanning {dir_path}: {exc}")

        return definitions

    def classify_ownership(
        self,
        label: str,
        domain: ServiceDomain,
        plist_path: Optional[str] = None,
    ) -> ServiceOwnership:
        """Deterministically classify service ownership into SYSTEM, VENDOR, or USER."""
        if (
            domain in (ServiceDomain.SYSTEM_DAEMON, ServiceDomain.SYSTEM_AGENT)
            or label.startswith("com.apple.")
            or (plist_path and plist_path.startswith("/System/"))
        ):
            return ServiceOwnership.SYSTEM_MANAGED

        if domain == ServiceDomain.USER_AGENT or (plist_path and "/Users/" in plist_path):
            return ServiceOwnership.USER_MANAGED

        return ServiceOwnership.VENDOR_MANAGED

    def query_login_items(self) -> Tuple[List[MacLoginItem], List[str]]:
        """Query user login items via unprivileged System Events AppleScript."""
        items: List[MacLoginItem] = []
        warnings: List[str] = []

        if platform.system() != "Darwin":
            return items, warnings

        # Non-mutating read-only AppleScript query with 3-second timeout
        script = (
            'tell application "System Events"\n'
            "    set out to {}\n"
            "    repeat with itm in every login item\n"
            '        set end of out to (name of itm & "|" & (path of itm as text) & "|" & (hidden of itm as text))\n'
            "    end repeat\n"
            "    return out\n"
            "end tell"
        )

        cmd = ["/usr/bin/osascript", "-e", script]
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0:
                raw_out = res.stdout.strip()
                if raw_out:
                    # AppleScript returns comma-delimited list of strings
                    entries = [e.strip() for e in raw_out.split(", ") if e.strip()]
                    for entry in entries:
                        parts = entry.split("|")
                        if len(parts) >= 3:
                            name = parts[0].strip()
                            path_str = parts[1].strip()
                            hidden_str = parts[2].strip().lower()

                            path_val = None if path_str in ("missing value", "") else path_str
                            hidden = hidden_str == "true"
                            is_apple = (
                                path_val.startswith("/System/")
                                if path_val
                                else name.lower().startswith("apple")
                            )

                            ownership = (
                                ServiceOwnership.SYSTEM_MANAGED
                                if is_apple
                                else ServiceOwnership.USER_MANAGED
                            )

                            items.append(
                                MacLoginItem(
                                    name=name,
                                    path=path_val,
                                    hidden=hidden,
                                    kind=LoginItemKind.APPLICATION,
                                    ownership=ownership,
                                    is_apple=is_apple,
                                )
                            )
            else:
                warnings.append(f"Login items query returned exit code {res.returncode}")
        except subprocess.TimeoutExpired:
            warnings.append("Login items query timed out after 3 seconds")
        except Exception as exc:
            warnings.append(f"Login items query encountered error: {exc}")

        return items, warnings

    def detect_mock(self, mock_adapter: Optional[Any] = None) -> MacServicesReport:
        """Construct realistic Apple Silicon macOS launchd services and login-item mock."""
        services: List[MacLaunchdService] = [
            MacLaunchdService(
                label="com.apple.Finder",
                pid=653,
                last_exit_code=0,
                domain=ServiceDomain.SYSTEM_AGENT,
                status=ServiceStatus.RUNNING,
                ownership=ServiceOwnership.SYSTEM_MANAGED,
                plist_path="/System/Library/LaunchAgents/com.apple.Finder.plist",
                program="/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
                run_at_load=True,
                keep_alive=True,
                is_apple=True,
            ),
            MacLaunchdService(
                label="com.apple.homed",
                pid=775,
                last_exit_code=0,
                domain=ServiceDomain.SYSTEM_AGENT,
                status=ServiceStatus.RUNNING,
                ownership=ServiceOwnership.SYSTEM_MANAGED,
                plist_path="/System/Library/LaunchAgents/com.apple.homed.plist",
                program="/System/Library/PrivateFrameworks/HomeKitDaemon.framework/Support/homed",
                run_at_load=True,
                keep_alive=True,
                is_apple=True,
            ),
            MacLaunchdService(
                label="com.apple.SafariHistoryServiceAgent",
                pid=None,
                last_exit_code=0,
                domain=ServiceDomain.SYSTEM_AGENT,
                status=ServiceStatus.LOADED_WAITING,
                ownership=ServiceOwnership.SYSTEM_MANAGED,
                plist_path="/System/Library/LaunchAgents/com.apple.SafariHistoryServiceAgent.plist",
                program="/System/Library/PrivateFrameworks/SafariShared.framework/Versions/A/XPCServices/SafariHistoryServiceAgent.xpc/Contents/MacOS/SafariHistoryServiceAgent",
                run_at_load=False,
                keep_alive=False,
                is_apple=True,
            ),
            MacLaunchdService(
                label="com.cloudflare.1dot1dot1dot1.macos.warp.daemon",
                pid=412,
                last_exit_code=0,
                domain=ServiceDomain.GLOBAL_DAEMON,
                status=ServiceStatus.RUNNING,
                ownership=ServiceOwnership.VENDOR_MANAGED,
                plist_path="/Library/LaunchDaemons/com.cloudflare.1dot1dot1dot1.macos.warp.daemon.plist",
                program="/Applications/Cloudflare WARP.app/Contents/Resources/warp-svc",
                run_at_load=True,
                keep_alive=True,
                is_apple=False,
            ),
            MacLaunchdService(
                label="com.docker.socket",
                pid=None,
                last_exit_code=0,
                domain=ServiceDomain.GLOBAL_DAEMON,
                status=ServiceStatus.LOADED_WAITING,
                ownership=ServiceOwnership.VENDOR_MANAGED,
                plist_path="/Library/LaunchDaemons/com.docker.socket.plist",
                program="/Applications/Docker.app/Contents/Resources/socket/com.docker.socket",
                run_at_load=False,
                keep_alive=False,
                is_apple=False,
            ),
            MacLaunchdService(
                label="homebrew.mxcl.mysql",
                pid=892,
                last_exit_code=0,
                domain=ServiceDomain.USER_AGENT,
                status=ServiceStatus.RUNNING,
                ownership=ServiceOwnership.USER_MANAGED,
                plist_path="/Users/mockuser/Library/LaunchAgents/homebrew.mxcl.mysql.plist",
                program="/opt/homebrew/opt/mysql/bin/mysqld_safe",
                run_at_load=True,
                keep_alive=True,
                is_apple=False,
            ),
            MacLaunchdService(
                label="com.google.keystone.agent",
                pid=None,
                last_exit_code=0,
                domain=ServiceDomain.USER_AGENT,
                status=ServiceStatus.LOADED_WAITING,
                ownership=ServiceOwnership.USER_MANAGED,
                plist_path="/Users/mockuser/Library/LaunchAgents/com.google.keystone.agent.plist",
                program="/Users/mockuser/Library/Google/GoogleSoftwareUpdate/GoogleSoftwareUpdate.bundle/Contents/MacOS/GoogleSoftwareUpdateAgent",
                run_at_load=False,
                keep_alive=False,
                is_apple=False,
            ),
            MacLaunchdService(
                label="com.example.failed.service",
                pid=None,
                last_exit_code=78,
                domain=ServiceDomain.RUNTIME_LOADED,
                status=ServiceStatus.LOADED_FAILED,
                ownership=ServiceOwnership.VENDOR_MANAGED,
                plist_path=None,
                program=None,
                run_at_load=None,
                keep_alive=None,
                is_apple=False,
            ),
        ]

        login_items: List[MacLoginItem] = [
            MacLoginItem(
                name="GeminiAppLauncher",
                path="/Applications/GeminiAppLauncher.app",
                hidden=False,
                kind=LoginItemKind.APPLICATION,
                ownership=ServiceOwnership.USER_MANAGED,
                is_apple=False,
            ),
            MacLoginItem(
                name="Docker Desktop",
                path="/Applications/Docker.app",
                hidden=True,
                kind=LoginItemKind.APPLICATION,
                ownership=ServiceOwnership.USER_MANAGED,
                is_apple=False,
            ),
        ]

        running_count = sum(1 for s in services if s.is_running)
        loaded_count = sum(1 for s in services if s.status != ServiceStatus.DEFINITION_ONLY)
        system_count = sum(1 for s in services if s.ownership == ServiceOwnership.SYSTEM_MANAGED)
        vendor_count = sum(1 for s in services if s.ownership == ServiceOwnership.VENDOR_MANAGED)
        user_count = sum(1 for s in services if s.ownership == ServiceOwnership.USER_MANAGED)

        return MacServicesReport(
            collection_method="MOCK_PLATFORM_ADAPTER",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            host_platform="macOS-Darwin-arm64-AppleSilicon-Mock",
            services=services,
            login_items=login_items,
            total_services_count=len(services),
            running_services_count=running_count,
            loaded_services_count=loaded_count,
            system_managed_count=system_count,
            vendor_managed_count=vendor_count,
            user_managed_count=user_count,
            total_login_items_count=len(login_items),
            warnings=[],
            unavailable_telemetry=[],
        )

    def detect(
        self,
        mock: bool = False,
        mock_adapter: Optional[Any] = None,
    ) -> MacServicesReport:
        """Inspect macOS launchd jobs and login items in read-only user space."""
        if mock or platform.system() != "Darwin":
            report = self.detect_mock(mock_adapter)
            if platform.system() != "Darwin":
                unavailable = list(report.unavailable_telemetry)
                unavailable.extend(["launchctl", "osascript_system_events"])
                return MacServicesReport(
                    collection_method="MOCK_PLATFORM_ADAPTER",
                    timestamp=report.timestamp,
                    host_platform=f"{platform.system()}-{platform.machine()}",
                    services=report.services,
                    login_items=report.login_items,
                    total_services_count=report.total_services_count,
                    running_services_count=report.running_services_count,
                    loaded_services_count=report.loaded_services_count,
                    system_managed_count=report.system_managed_count,
                    vendor_managed_count=report.vendor_managed_count,
                    user_managed_count=report.user_managed_count,
                    total_login_items_count=report.total_login_items_count,
                    warnings=["Non-Darwin host platform; returning simulated Apple Silicon services"],
                    unavailable_telemetry=unavailable,
                )
            return report

        warnings: List[str] = []
        unavailable_telemetry: List[str] = []

        # 1. Query loaded jobs via `/bin/launchctl list`
        launchctl_output = ""
        try:
            cmd = ["/bin/launchctl", "list"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0:
                launchctl_output = res.stdout
            else:
                warnings.append(f"launchctl list exited with code {res.returncode}")
        except subprocess.TimeoutExpired:
            warnings.append("launchctl list timed out after 5 seconds")
            unavailable_telemetry.append("launchctl_list")
        except Exception as exc:
            warnings.append(f"launchctl list failed: {exc}")
            unavailable_telemetry.append("launchctl_list")

        loaded_jobs = self.parse_launchctl_output(launchctl_output)

        # 2. Scan standard plist directories for service definitions
        plist_definitions = self.scan_plist_directories()

        # 3. Correlate loaded jobs with plist definitions
        services_map: Dict[str, MacLaunchdService] = {}

        for pid, exit_code, label in loaded_jobs:
            meta = plist_definitions.get(label)
            domain = meta["domain"] if meta else ServiceDomain.RUNTIME_LOADED
            plist_path = meta["plist_path"] if meta else None
            program = meta["program"] if meta else None
            run_at_load = meta["run_at_load"] if meta else None
            keep_alive = meta["keep_alive"] if meta else None

            # Determine status
            if pid is not None and pid > 0:
                status = ServiceStatus.RUNNING
            elif exit_code == 0:
                status = ServiceStatus.LOADED_WAITING
            else:
                status = ServiceStatus.LOADED_FAILED

            ownership = self.classify_ownership(label, domain, plist_path)
            is_apple = label.startswith("com.apple.") or domain in (
                ServiceDomain.SYSTEM_DAEMON,
                ServiceDomain.SYSTEM_AGENT,
            )

            service = MacLaunchdService(
                label=label,
                pid=pid,
                last_exit_code=exit_code,
                domain=domain,
                status=status,
                ownership=ownership,
                plist_path=plist_path,
                program=program,
                run_at_load=run_at_load,
                keep_alive=keep_alive,
                is_apple=is_apple,
            )
            services_map[label] = service

        # 4. Include known plists not currently active in user's launchctl session
        for label, meta in plist_definitions.items():
            if label not in services_map:
                domain = meta["domain"]
                plist_path = meta["plist_path"]
                program = meta["program"]
                run_at_load = meta["run_at_load"]
                keep_alive = meta["keep_alive"]

                ownership = self.classify_ownership(label, domain, plist_path)
                is_apple = label.startswith("com.apple.") or domain in (
                    ServiceDomain.SYSTEM_DAEMON,
                    ServiceDomain.SYSTEM_AGENT,
                )

                services_map[label] = MacLaunchdService(
                    label=label,
                    pid=None,
                    last_exit_code=None,
                    domain=domain,
                    status=ServiceStatus.DEFINITION_ONLY,
                    ownership=ownership,
                    plist_path=plist_path,
                    program=program,
                    run_at_load=run_at_load,
                    keep_alive=keep_alive,
                    is_apple=is_apple,
                )

        services = sorted(services_map.values(), key=lambda s: s.label.lower())

        # 5. Query user login items
        login_items, login_warnings = self.query_login_items()
        if login_warnings:
            warnings.extend(login_warnings)
            unavailable_telemetry.append("login_items_system_events")

        running_count = sum(1 for s in services if s.is_running)
        loaded_count = sum(1 for s in services if s.status != ServiceStatus.DEFINITION_ONLY)
        system_count = sum(1 for s in services if s.ownership == ServiceOwnership.SYSTEM_MANAGED)
        vendor_count = sum(1 for s in services if s.ownership == ServiceOwnership.VENDOR_MANAGED)
        user_count = sum(1 for s in services if s.ownership == ServiceOwnership.USER_MANAGED)

        return MacServicesReport(
            collection_method="NATIVE_DARWIN_LAUNCHD",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            host_platform=f"{platform.system()}-{platform.machine()}",
            services=services,
            login_items=login_items,
            total_services_count=len(services),
            running_services_count=running_count,
            loaded_services_count=loaded_count,
            system_managed_count=system_count,
            vendor_managed_count=vendor_count,
            user_managed_count=user_count,
            total_login_items_count=len(login_items),
            warnings=warnings,
            unavailable_telemetry=unavailable_telemetry,
        )
