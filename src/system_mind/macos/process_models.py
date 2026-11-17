"""Data models for macOS process inventory and resource usage telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List, Optional


class ProcessState(str, Enum):
    """Operational execution state of a Darwin OS process."""

    RUNNING = "RUNNING"                    # Active on CPU (R)
    SLEEPING = "SLEEPING"                  # Interruptible sleep waiting for event/IO (S, I)
    STOPPED = "STOPPED"                    # Suspended or paused by signal/debugger (T)
    ZOMBIE = "ZOMBIE"                      # Terminated waiting for parent reap (Z)
    UNINTERRUPTIBLE = "UNINTERRUPTIBLE"    # Uninterruptible disk or hardware sleep (U, D)
    UNKNOWN = "UNKNOWN"                    # Unrecognized process state


class ProcessRole(str, Enum):
    """Categorical classification of process ownership, origin, and architectural tier."""

    SYSTEM_CORE = "SYSTEM_CORE"        # Root-level or core operating system service (launchd, logd)
    USER_APP = "USER_APP"              # User desktop application (/Applications, ~/Applications)
    DAEMON_SERVICE = "DAEMON_SERVICE"  # Background launchd service or system agent
    DEVELOPER_TOOL = "DEVELOPER_TOOL"  # Compiler, interpreter, CLI tool (python, cargo, git)
    OTHER = "OTHER"                    # General or unclassified process


@dataclass(frozen=True)
class MacProcessInfo:
    """Strongly typed snapshot of an individual running process."""

    pid: int
    ppid: int
    uid: int
    user: str
    name: str
    command_path: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    rss_bytes: int = 0
    vsz_bytes: int = 0
    state: ProcessState = ProcessState.UNKNOWN
    state_raw: str = ""
    role: ProcessRole = ProcessRole.OTHER
    is_system_core: bool = False
    is_user_app: bool = False


@dataclass(frozen=True)
class MacProcessReport:
    """Authoritative aggregated process table report for macOS companion agent."""

    processes: List[MacProcessInfo] = field(default_factory=list)
    total_process_count: int = 0
    running_count: int = 0
    sleeping_count: int = 0
    zombie_count: int = 0
    system_core_count: int = 0
    user_app_count: int = 0
    total_cpu_percent: float = 0.0
    total_rss_bytes: int = 0
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_PS"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scan_proves_safe: bool = False  # Charter non-negotiable invariant: Scan != Safe

    def get_top_cpu(self, limit: int = 10) -> List[MacProcessInfo]:
        """Return the top N processes ranked by instantaneous CPU percentage."""
        return sorted(self.processes, key=lambda p: p.cpu_percent, reverse=True)[:limit]

    def get_top_memory(self, limit: int = 10) -> List[MacProcessInfo]:
        """Return the top N processes ranked by Resident Set Size (RSS) memory consumption."""
        return sorted(self.processes, key=lambda p: p.rss_bytes, reverse=True)[:limit]

    def filter_by_user(self, username: str) -> List[MacProcessInfo]:
        """Filter process table to processes owned by a specific username."""
        target = username.lower().strip()
        return [p for p in self.processes if p.user.lower() == target]

    def find_by_pid(self, pid: int) -> Optional[MacProcessInfo]:
        """Lookup a specific process entry by its process identifier (PID)."""
        for p in self.processes:
            if p.pid == pid:
                return p
        return None
