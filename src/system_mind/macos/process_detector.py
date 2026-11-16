"""Read-only macOS process inventory and resource usage telemetry detector."""

from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path
import platform
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.process_models import (
    MacProcessInfo,
    MacProcessReport,
    ProcessRole,
    ProcessState,
)

logger = logging.getLogger(__name__)


class MacProcessDetector:
    """Read-only, passive introspection engine for macOS processes and resource metrics."""

    def classify_state(self, raw_stat: str) -> ProcessState:
        """Map Darwin process status flags to ProcessState enum."""
        if not raw_stat:
            return ProcessState.UNKNOWN
        primary = raw_stat[0].upper()
        if primary == "R":
            return ProcessState.RUNNING
        elif primary in ("S", "I"):
            return ProcessState.SLEEPING
        elif primary == "T":
            return ProcessState.STOPPED
        elif primary == "Z":
            return ProcessState.ZOMBIE
        elif primary in ("U", "D"):
            return ProcessState.UNINTERRUPTIBLE
        return ProcessState.UNKNOWN

    def classify_role(
        self,
        uid: int,
        user: str,
        comm: str,
    ) -> Tuple[ProcessRole, bool, bool]:
        """Classify process role, system core flag, and user application flag."""
        comm_lower = comm.lower()

        # System core OS processes
        if uid == 0 or any(
            comm.startswith(p)
            for p in (
                "/sbin/",
                "/usr/libexec/",
                "/System/Library/CoreServices/",
                "/System/Library/Frameworks/",
            )
        ):
            return ProcessRole.SYSTEM_CORE, True, False

        # User desktop applications
        if "/applications/" in comm_lower:
            return ProcessRole.USER_APP, False, True

        # Developer tools and CLI compilers/interpreters
        bin_name = Path(comm).name.lower()
        if any(
            t in bin_name
            for t in (
                "python",
                "python3",
                "cargo",
                "rustc",
                "node",
                "git",
                "clang",
                "gcc",
                "zsh",
                "bash",
                "pytest",
                "vite",
                "npm",
            )
        ):
            return ProcessRole.DEVELOPER_TOOL, False, False

        # Background launchd daemons / services
        if "daemon" in comm_lower or "agent" in comm_lower or "helper" in comm_lower:
            return ProcessRole.DAEMON_SERVICE, False, False

        return ProcessRole.OTHER, False, False

    def parse_ps_line(self, line: str) -> Optional[MacProcessInfo]:
        """Parse a single line from `ps -axo pid,ppid,uid,user,%cpu,%mem,rss,vsz,stat,comm`."""
        if not line or not line.strip():
            return None

        parts = line.strip().split(None, 9)
        if len(parts) < 10:
            return None

        # Ignore header line if present
        if parts[0] == "PID":
            return None

        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            uid = int(parts[2])
            user = parts[3]
            cpu_percent = float(parts[4])
            memory_percent = float(parts[5])
            # ps outputs RSS and VSZ in kilobytes; convert to bytes
            rss_bytes = int(parts[6]) * 1024
            vsz_bytes = int(parts[7]) * 1024
            stat_raw = parts[8]
            command_path = parts[9]
            name = Path(command_path).name or command_path

            state = self.classify_state(stat_raw)
            role, is_system_core, is_user_app = self.classify_role(uid, user, command_path)

            return MacProcessInfo(
                pid=pid,
                ppid=ppid,
                uid=uid,
                user=user,
                name=name,
                command_path=command_path,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                rss_bytes=rss_bytes,
                vsz_bytes=vsz_bytes,
                state=state,
                state_raw=stat_raw,
                role=role,
                is_system_core=is_system_core,
                is_user_app=is_user_app,
            )
        except (ValueError, IndexError):
            return None

    def parse_ps_output(self, output: str) -> Tuple[List[MacProcessInfo], List[str]]:
        """Parse entire ps text output into a list of MacProcessInfo records."""
        processes: List[MacProcessInfo] = []
        warnings: List[str] = []

        for line in output.splitlines():
            proc = self.parse_ps_line(line)
            if proc is not None:
                processes.append(proc)

        return processes, warnings

    def detect_mock(self, mock_adapter: Optional[Any] = None) -> MacProcessReport:
        """Construct deterministic Apple Silicon process telemetry mock (INV-PROC-08)."""
        launchd = MacProcessInfo(
            pid=1,
            ppid=0,
            uid=0,
            user="root",
            name="launchd",
            command_path="/sbin/launchd",
            cpu_percent=0.2,
            memory_percent=0.1,
            rss_bytes=16 * 1024 * 1024,
            vsz_bytes=480 * 1024 * 1024,
            state=ProcessState.SLEEPING,
            state_raw="Ss",
            role=ProcessRole.SYSTEM_CORE,
            is_system_core=True,
            is_user_app=False,
        )

        logd = MacProcessInfo(
            pid=338,
            ppid=1,
            uid=0,
            user="root",
            name="logd",
            command_path="/usr/libexec/logd",
            cpu_percent=0.4,
            memory_percent=0.1,
            rss_bytes=12 * 1024 * 1024,
            vsz_bytes=488 * 1024 * 1024,
            state=ProcessState.SLEEPING,
            state_raw="Ss",
            role=ProcessRole.SYSTEM_CORE,
            is_system_core=True,
            is_user_app=False,
        )

        chrome = MacProcessInfo(
            pid=1200,
            ppid=1,
            uid=501,
            user="tharungodwin",
            name="Google Chrome",
            command_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            cpu_percent=14.5,
            memory_percent=2.8,
            rss_bytes=450 * 1024 * 1024,
            vsz_bytes=3500 * 1024 * 1024,
            state=ProcessState.RUNNING,
            state_raw="R+",
            role=ProcessRole.USER_APP,
            is_system_core=False,
            is_user_app=True,
        )

        python_proc = MacProcessInfo(
            pid=1500,
            ppid=1,
            uid=501,
            user="tharungodwin",
            name="python3",
            command_path="/usr/local/bin/python3",
            cpu_percent=8.0,
            memory_percent=0.5,
            rss_bytes=85 * 1024 * 1024,
            vsz_bytes=600 * 1024 * 1024,
            state=ProcessState.RUNNING,
            state_raw="R",
            role=ProcessRole.DEVELOPER_TOOL,
            is_system_core=False,
            is_user_app=False,
        )

        procs = [launchd, logd, chrome, python_proc]
        running_cnt = sum(1 for p in procs if p.state == ProcessState.RUNNING)
        sleeping_cnt = sum(1 for p in procs if p.state == ProcessState.SLEEPING)
        zombie_cnt = sum(1 for p in procs if p.state == ProcessState.ZOMBIE)
        core_cnt = sum(1 for p in procs if p.is_system_core)
        app_cnt = sum(1 for p in procs if p.is_user_app)
        total_cpu = sum(p.cpu_percent for p in procs)
        total_rss = sum(p.rss_bytes for p in procs)

        return MacProcessReport(
            processes=procs,
            total_process_count=len(procs),
            running_count=running_cnt,
            sleeping_count=sleeping_cnt,
            zombie_count=zombie_cnt,
            system_core_count=core_cnt,
            user_app_count=app_cnt,
            total_cpu_percent=round(total_cpu, 2),
            total_rss_bytes=total_rss,
            collected_at_epoch_secs=time.time(),
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )

    def detect(
        self,
        use_mock: bool = False,
        mock_adapter: Optional[Any] = None,
    ) -> MacProcessReport:
        """Perform read-only query of macOS active process table with unprivileged ps."""
        if use_mock:
            return self.detect_mock(mock_adapter)

        if platform.system() != "Darwin":
            logger.info("Non-Darwin platform detected; falling back to mock platform adapter")
            report = self.detect_mock(mock_adapter)
            return replace(
                report,
                collection_method="NON_DARWIN_MOCK_FALLBACK",
                unavailable_telemetry=["ps Darwin options require Darwin macOS host"],
            )

        unavailable: List[str] = []
        warnings: List[str] = []

        try:
            cmd = ["/bin/ps", "-axo", "pid,ppid,uid,user,%cpu,%mem,rss,vsz,stat,comm"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode != 0:
                warnings.append(f"ps exited with non-zero code {proc.returncode}")
                return self.detect_mock(mock_adapter)

            processes, parse_warnings = self.parse_ps_output(proc.stdout)
            warnings.extend(parse_warnings)

            running_cnt = sum(1 for p in processes if p.state == ProcessState.RUNNING)
            sleeping_cnt = sum(1 for p in processes if p.state == ProcessState.SLEEPING)
            zombie_cnt = sum(1 for p in processes if p.state == ProcessState.ZOMBIE)
            core_cnt = sum(1 for p in processes if p.is_system_core)
            app_cnt = sum(1 for p in processes if p.is_user_app)
            total_cpu = sum(p.cpu_percent for p in processes)
            total_rss = sum(p.rss_bytes for p in processes)

            return MacProcessReport(
                processes=processes,
                total_process_count=len(processes),
                running_count=running_cnt,
                sleeping_count=sleeping_cnt,
                zombie_count=zombie_cnt,
                system_core_count=core_cnt,
                user_app_count=app_cnt,
                total_cpu_percent=round(total_cpu, 2),
                total_rss_bytes=total_rss,
                collected_at_epoch_secs=time.time(),
                collection_method="NATIVE_DARWIN_PS",
                unavailable_telemetry=unavailable,
                warnings=warnings,
            )

        except subprocess.TimeoutExpired:
            warnings.append("ps query timed out after 5s")
            return self.detect_mock(mock_adapter)
        except Exception as exc:
            warnings.append(f"Process detection exception: {str(exc)}")
            return self.detect_mock(mock_adapter)
