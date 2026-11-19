"""Domain models, diffing engine, and persistence manager for process start and exit tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from system_mind.core.types import ComponentOwnership
from system_mind.twin.event_store import SystemEventRecord, SystemEventStore, SystemEventType
from system_mind.twin.identity import EntityDomain, EntityUrn, StableEntityIdGenerator
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinRelationship,
    TwinRelationType,
)


class ProcessLifecycleEventType(str, Enum):
    """Categorical classification of process lifecycle state transitions."""

    PROCESS_STARTED = "PROCESS_STARTED"
    PROCESS_FORKED = "PROCESS_FORKED"
    PROCESS_EXITED = "PROCESS_EXITED"
    PROCESS_CRASHED = "PROCESS_CRASHED"
    PROCESS_SIGNALED = "PROCESS_SIGNALED"


class ProcessExitStatus(str, Enum):
    """Normalized process termination category."""

    NORMAL = "NORMAL"
    SIGNALED = "SIGNALED"
    CRASHED = "CRASHED"
    KILLED_OOM = "KILLED_OOM"
    UNKNOWN = "UNKNOWN"


class ProcessDetectionSource(str, Enum):
    """Telemetry channel source for process lifecycle observation."""

    PROCESS_TABLE_DIFF = "PROCESS_TABLE_DIFF"
    ENDPOINT_SECURITY = "ENDPOINT_SECURITY"
    BSM_AUDIT = "BSM_AUDIT"
    EBPF_PROBE = "EBPF_PROBE"
    SYNTHETIC_SIMULATION = "SYNTHETIC_SIMULATION"


@dataclass(frozen=True)
class ProcessLifecycleEvent:
    """Strongly typed atomic record of a process lifecycle transition."""

    event_id: str
    device_id: str
    entity_urn: str
    event_type: ProcessLifecycleEventType
    pid: int
    ppid: int
    process_name: str
    binary_path: str
    command_line: str = ""
    user_name: str = ""
    uid: int = 501
    start_epoch_ms: int = 0
    exit_epoch_ms: Optional[int] = None
    exit_code: Optional[int] = None
    exit_status: ProcessExitStatus = ProcessExitStatus.UNKNOWN
    runtime_ms: Optional[int] = None
    ownership: ComponentOwnership = ComponentOwnership.USER_MANAGED
    detection_source: ProcessDetectionSource = ProcessDetectionSource.PROCESS_TABLE_DIFF
    observed_at_iso: str = ""
    observed_at_epoch_ms: int = 0
    parent_entity_urn: Optional[str] = None
    app_entity_urn: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    scan_proves_safe: bool = False  # Inviolable charter invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")
        if not self.entity_urn.startswith("urn:systemmind:proc:"):
            raise ValueError(f"Invalid process entity URN format: {self.entity_urn}")
        if self.pid < 0:
            raise ValueError(f"PID cannot be negative: {self.pid}")
        if self.start_epoch_ms < 0:
            raise ValueError(f"start_epoch_ms cannot be negative: {self.start_epoch_ms}")
        if self.exit_epoch_ms is not None and self.exit_epoch_ms < self.start_epoch_ms:
            raise ValueError(
                f"exit_epoch_ms ({self.exit_epoch_ms}) cannot precede start_epoch_ms ({self.start_epoch_ms})"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize lifecycle event to JSON-compatible dictionary."""
        return {
            "event_id": self.event_id,
            "device_id": self.device_id,
            "entity_urn": self.entity_urn,
            "event_type": self.event_type.value,
            "pid": self.pid,
            "ppid": self.ppid,
            "process_name": self.process_name,
            "binary_path": self.binary_path,
            "command_line": self.command_line,
            "user_name": self.user_name,
            "uid": self.uid,
            "start_epoch_ms": self.start_epoch_ms,
            "exit_epoch_ms": self.exit_epoch_ms,
            "exit_code": self.exit_code,
            "exit_status": self.exit_status.value,
            "runtime_ms": self.runtime_ms,
            "ownership": self.ownership.value,
            "detection_source": self.detection_source.value,
            "observed_at_iso": self.observed_at_iso,
            "observed_at_epoch_ms": self.observed_at_epoch_ms,
            "parent_entity_urn": self.parent_entity_urn,
            "app_entity_urn": self.app_entity_urn,
            "metadata": dict(self.metadata),
            "scan_proves_safe": self.scan_proves_safe,
        }


@dataclass(frozen=True)
class ProcessLifecycleDiff:
    """Aggregated result of differential process table comparison."""

    started_events: List[ProcessLifecycleEvent] = field(default_factory=list)
    exited_events: List[ProcessLifecycleEvent] = field(default_factory=list)
    forked_events: List[ProcessLifecycleEvent] = field(default_factory=list)
    total_active_processes: int = 0
    diff_timestamp_epoch_ms: int = 0
    scan_proves_safe: bool = False

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")

    @property
    def total_transitions(self) -> int:
        return len(self.started_events) + len(self.exited_events) + len(self.forked_events)

    @property
    def all_events(self) -> List[ProcessLifecycleEvent]:
        return [*self.started_events, *self.exited_events, *self.forked_events]


class ProcessLifecycleTracker:
    """Differential engine for detecting process start and exit events across observation channels."""

    @staticmethod
    def classify_ownership(binary_path: str, is_system_core: bool = False) -> ComponentOwnership:
        """Determines component ownership tier from executable binary path."""
        if is_system_core:
            return ComponentOwnership.SYSTEM_MANAGED

        norm_path = os.path.normpath(binary_path).lower()
        if (
            norm_path.startswith("/system/")
            or norm_path.startswith("/usr/lib")
            or norm_path.startswith("/usr/sbin")
            or norm_path.startswith("/sbin/")
            or norm_path.startswith("/usr/libexec")
        ):
            return ComponentOwnership.SYSTEM_MANAGED

        if (
            norm_path.startswith("/opt/homebrew")
            or norm_path.startswith("/library/")
            or norm_path.startswith("/usr/local")
        ):
            return ComponentOwnership.VENDOR_MANAGED

        return ComponentOwnership.USER_MANAGED

    @classmethod
    def resolve_app_urn_for_binary(cls, binary_path: str) -> Optional[str]:
        """Resolves application bundle canonical URN if binary path resides inside a .app package."""
        norm = os.path.normpath(binary_path)
        m = re.search(r"(/[^/]+\.app)(?:/|$)", norm)
        if m:
            app_bundle_path = m.group(1)
            bundle_name = os.path.basename(app_bundle_path)
            slug = bundle_name.replace(".app", "").lower().replace(" ", "-")
            return f"urn:systemmind:app:{slug}"
        return None

    @classmethod
    def diff_process_tables(
        cls,
        baseline_processes: Sequence[Any],
        current_processes: Sequence[Any],
        device_id: str,
        observed_at_epoch_ms: Optional[int] = None,
        detection_source: ProcessDetectionSource = ProcessDetectionSource.PROCESS_TABLE_DIFF,
    ) -> ProcessLifecycleDiff:
        """Compares consecutive process table snapshots, identifying started, recycled, and exited processes."""
        now_ms = observed_at_epoch_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
        now_iso = datetime.fromtimestamp(now_ms / 1000.0, timezone.utc).isoformat()

        # Helper to extract uniform dict from item (MacProcessInfo or dict)
        def to_proc_dict(item: Any) -> Dict[str, Any]:
            if hasattr(item, "__dict__"):
                return {
                    "pid": getattr(item, "pid", 0),
                    "ppid": getattr(item, "ppid", 0),
                    "uid": getattr(item, "uid", 501),
                    "user": getattr(item, "user", "unknown"),
                    "name": getattr(item, "name", "process"),
                    "command_path": getattr(item, "command_path", ""),
                    "start_time_epoch_ms": getattr(item, "start_time_epoch_ms", now_ms),
                    "is_system_core": getattr(item, "is_system_core", False),
                    "role": getattr(getattr(item, "role", None), "value", "OTHER"),
                }
            elif isinstance(item, dict):
                return {
                    "pid": int(item.get("pid", 0)),
                    "ppid": int(item.get("ppid", 0)),
                    "uid": int(item.get("uid", 501)),
                    "user": str(item.get("user", "unknown")),
                    "name": str(item.get("name", "process")),
                    "command_path": str(item.get("command_path") or item.get("binary_path", "")),
                    "start_time_epoch_ms": int(item.get("start_time_epoch_ms", now_ms)),
                    "is_system_core": bool(item.get("is_system_core", False)),
                    "role": str(item.get("role", "OTHER")),
                }
            return {}

        baseline_map: Dict[int, Dict[str, Any]] = {}
        for p in baseline_processes:
            d = to_proc_dict(p)
            if d.get("pid", 0) > 0:
                baseline_map[d["pid"]] = d

        current_map: Dict[int, Dict[str, Any]] = {}
        for p in current_processes:
            d = to_proc_dict(p)
            if d.get("pid", 0) > 0:
                current_map[d["pid"]] = d

        started_events: List[ProcessLifecycleEvent] = []
        exited_events: List[ProcessLifecycleEvent] = []

        # 1. Detect exited processes (in baseline, not in current, OR PID recycled with newer start time)
        for pid, base_proc in baseline_map.items():
            curr_proc = current_map.get(pid)
            is_recycled = (
                curr_proc is not None
                and curr_proc["start_time_epoch_ms"] > base_proc["start_time_epoch_ms"]
            )

            if curr_proc is None or is_recycled:
                # Process exited
                start_ms = base_proc["start_time_epoch_ms"]
                runtime = max(0, now_ms - start_ms)
                cmd_path = base_proc["command_path"] or base_proc["name"]
                proc_urn = StableEntityIdGenerator.generate_process_urn(
                    device_id=device_id,
                    pid=pid,
                    start_time_epoch_ms=start_ms,
                    binary_path=cmd_path,
                )

                parent_urn = None
                ppid = base_proc["ppid"]
                if ppid in baseline_map:
                    p_info = baseline_map[ppid]
                    parent_urn = StableEntityIdGenerator.generate_process_urn(
                        device_id=device_id,
                        pid=ppid,
                        start_time_epoch_ms=p_info["start_time_epoch_ms"],
                        binary_path=p_info["command_path"] or p_info["name"],
                    ).urn

                app_urn = cls.resolve_app_urn_for_binary(cmd_path)
                ownership = cls.classify_ownership(cmd_path, base_proc["is_system_core"])

                ev_id = f"pevt_{hashlib.sha256(f'EXIT:{proc_urn.urn}:{now_ms}'.encode('utf-8')).hexdigest()[:16]}"
                exited_events.append(
                    ProcessLifecycleEvent(
                        event_id=ev_id,
                        device_id=device_id,
                        entity_urn=proc_urn.urn,
                        event_type=ProcessLifecycleEventType.PROCESS_EXITED,
                        pid=pid,
                        ppid=ppid,
                        process_name=base_proc["name"],
                        binary_path=cmd_path,
                        command_line=base_proc.get("command_path", ""),
                        user_name=base_proc["user"],
                        uid=base_proc["uid"],
                        start_epoch_ms=start_ms,
                        exit_epoch_ms=now_ms,
                        exit_code=None,  # Inferred via diff
                        exit_status=ProcessExitStatus.UNKNOWN,
                        runtime_ms=runtime,
                        ownership=ownership,
                        detection_source=detection_source,
                        observed_at_iso=now_iso,
                        observed_at_epoch_ms=now_ms,
                        parent_entity_urn=parent_urn,
                        app_entity_urn=app_urn,
                        metadata={"inferred_from": "process_table_diff"},
                        scan_proves_safe=False,
                    )
                )

        # 2. Detect started processes (in current, not in baseline, OR PID recycled)
        for pid, curr_proc in current_map.items():
            base_proc = baseline_map.get(pid)
            is_new = base_proc is None or curr_proc["start_time_epoch_ms"] > base_proc["start_time_epoch_ms"]

            if is_new:
                start_ms = curr_proc["start_time_epoch_ms"]
                cmd_path = curr_proc["command_path"] or curr_proc["name"]
                proc_urn = StableEntityIdGenerator.generate_process_urn(
                    device_id=device_id,
                    pid=pid,
                    start_time_epoch_ms=start_ms,
                    binary_path=cmd_path,
                )

                parent_urn = None
                ppid = curr_proc["ppid"]
                if ppid in current_map:
                    p_info = current_map[ppid]
                    parent_urn = StableEntityIdGenerator.generate_process_urn(
                        device_id=device_id,
                        pid=ppid,
                        start_time_epoch_ms=p_info["start_time_epoch_ms"],
                        binary_path=p_info["command_path"] or p_info["name"],
                    ).urn

                app_urn = cls.resolve_app_urn_for_binary(cmd_path)
                ownership = cls.classify_ownership(cmd_path, curr_proc["is_system_core"])

                ev_id = f"pevt_{hashlib.sha256(f'START:{proc_urn.urn}:{now_ms}'.encode('utf-8')).hexdigest()[:16]}"
                started_events.append(
                    ProcessLifecycleEvent(
                        event_id=ev_id,
                        device_id=device_id,
                        entity_urn=proc_urn.urn,
                        event_type=ProcessLifecycleEventType.PROCESS_STARTED,
                        pid=pid,
                        ppid=ppid,
                        process_name=curr_proc["name"],
                        binary_path=cmd_path,
                        command_line=curr_proc.get("command_path", ""),
                        user_name=curr_proc["user"],
                        uid=curr_proc["uid"],
                        start_epoch_ms=start_ms,
                        exit_epoch_ms=None,
                        exit_code=None,
                        exit_status=ProcessExitStatus.UNKNOWN,
                        runtime_ms=None,
                        ownership=ownership,
                        detection_source=detection_source,
                        observed_at_iso=now_iso,
                        observed_at_epoch_ms=now_ms,
                        parent_entity_urn=parent_urn,
                        app_entity_urn=app_urn,
                        metadata={"inferred_from": "process_table_diff"},
                        scan_proves_safe=False,
                    )
                )

        return ProcessLifecycleDiff(
            started_events=started_events,
            exited_events=exited_events,
            forked_events=[],
            total_active_processes=len(current_map),
            diff_timestamp_epoch_ms=now_ms,
            scan_proves_safe=False,
        )

    @classmethod
    def from_endpoint_security_event(
        cls,
        es_event: Any,
        device_id: str,
        start_epoch_ms: Optional[int] = None,
        exit_code: Optional[int] = None,
        observed_at_epoch_ms: Optional[int] = None,
    ) -> Optional[ProcessLifecycleEvent]:
        """Translates an Apple Endpoint Security notification (NOTIFY_EXEC, NOTIFY_FORK, NOTIFY_EXIT) into a ProcessLifecycleEvent."""
        now_ms = observed_at_epoch_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
        now_iso = datetime.fromtimestamp(now_ms / 1000.0, timezone.utc).isoformat()

        # Handle EsEventSample or dict
        if hasattr(es_event, "event_type"):
            raw_type = getattr(es_event.event_type, "value", str(es_event.event_type))
            pid = int(getattr(es_event, "process_pid", 0))
            ppid = int(getattr(es_event, "process_ppid", 0))
            binary_path = str(getattr(es_event, "executable_path", ""))
            cdhash = getattr(es_event, "cdhash", None)
            signing_id = getattr(es_event, "signing_id", None)
            is_platform = getattr(es_event, "is_platform_binary", False)
        elif isinstance(es_event, dict):
            raw_type = str(es_event.get("event_type", ""))
            pid = int(es_event.get("process_pid", 0))
            ppid = int(es_event.get("process_ppid", 0))
            binary_path = str(es_event.get("executable_path", ""))
            cdhash = es_event.get("cdhash")
            signing_id = es_event.get("signing_id")
            is_platform = bool(es_event.get("is_platform_binary", False))
        else:
            return None

        proc_name = os.path.basename(binary_path) or "unknown"
        p_start_ms = start_epoch_ms or (now_ms if "EXIT" not in raw_type else now_ms - 5000)

        proc_urn = StableEntityIdGenerator.generate_process_urn(
            device_id=device_id,
            pid=pid,
            start_time_epoch_ms=p_start_ms,
            binary_path=binary_path,
        )

        app_urn = cls.resolve_app_urn_for_binary(binary_path)
        ownership = cls.classify_ownership(binary_path, is_platform)

        if "EXEC" in raw_type:
            ev_type = ProcessLifecycleEventType.PROCESS_STARTED
            exit_epoch = None
            runtime = None
            exit_status = ProcessExitStatus.UNKNOWN
            ev_exit_code = None
        elif "FORK" in raw_type:
            ev_type = ProcessLifecycleEventType.PROCESS_FORKED
            exit_epoch = None
            runtime = None
            exit_status = ProcessExitStatus.UNKNOWN
            ev_exit_code = None
        elif "EXIT" in raw_type:
            ev_type = ProcessLifecycleEventType.PROCESS_EXITED
            exit_epoch = now_ms
            runtime = max(0, exit_epoch - p_start_ms)
            ev_exit_code = 0 if exit_code is None else exit_code
            exit_status = ProcessExitStatus.NORMAL if ev_exit_code == 0 else ProcessExitStatus.CRASHED
        else:
            return None

        ev_id = f"pevt_{hashlib.sha256(f'ES:{raw_type}:{proc_urn.urn}:{now_ms}'.encode('utf-8')).hexdigest()[:16]}"
        return ProcessLifecycleEvent(
            event_id=ev_id,
            device_id=device_id,
            entity_urn=proc_urn.urn,
            event_type=ev_type,
            pid=pid,
            ppid=ppid,
            process_name=proc_name,
            binary_path=binary_path,
            command_line=binary_path,
            user_name="unknown",
            uid=501,
            start_epoch_ms=p_start_ms,
            exit_epoch_ms=exit_epoch,
            exit_code=ev_exit_code,
            exit_status=exit_status,
            runtime_ms=runtime,
            ownership=ownership,
            detection_source=ProcessDetectionSource.ENDPOINT_SECURITY,
            observed_at_iso=now_iso,
            observed_at_epoch_ms=now_ms,
            parent_entity_urn=None,
            app_entity_urn=app_urn,
            metadata={
                "cdhash": cdhash,
                "signing_id": signing_id,
                "is_platform_binary": is_platform,
            },
            scan_proves_safe=False,
        )

    @classmethod
    def sync_with_digital_twin(
        cls,
        graph: Any,
        events: List[ProcessLifecycleEvent],
        host_urn: Optional[str] = None,
    ) -> int:
        """Synchronizes process lifecycle events into the in-memory DigitalTwinGraph."""
        mutations = 0
        h_urn = host_urn or (
            f"urn:systemmind:host:{events[0].device_id}" if events else "urn:systemmind:host:local"
        )

        # Ensure host exists in graph
        if not graph.get_entity(h_urn):
            graph.add_entity(
                TwinEntity(
                    entity_id=h_urn,
                    entity_type=TwinEntityType.HOST,
                    ownership=ComponentOwnership.SYSTEM_MANAGED,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    updated_at=datetime.now(timezone.utc).isoformat(),
                    provenance_source="host:system",
                )
            )

        for ev in events:
            if ev.event_type in (
                ProcessLifecycleEventType.PROCESS_STARTED,
                ProcessLifecycleEventType.PROCESS_FORKED,
            ):
                # Add or update process node
                proc_entity = TwinEntity(
                    entity_id=ev.entity_urn,
                    entity_type=TwinEntityType.PROCESS,
                    ownership=ev.ownership,
                    attributes={
                        "pid": ev.pid,
                        "ppid": ev.ppid,
                        "process_name": ev.process_name,
                        "binary_path": ev.binary_path,
                        "command_line": ev.command_line,
                        "user_name": ev.user_name,
                        "uid": ev.uid,
                        "start_epoch_ms": ev.start_epoch_ms,
                    },
                    created_at=ev.observed_at_iso,
                    updated_at=ev.observed_at_iso,
                    provenance_source=f"process_lifecycle:{ev.detection_source.value.lower()}",
                    is_stale=False,
                )
                graph.add_entity(proc_entity)
                mutations += 1

                # Connect HOST -> CONTAINS -> PROCESS
                contains_rel = TwinRelationship(
                    relation_id=f"rel_{hashlib.sha256(f'{h_urn}:CONTAINS:{ev.entity_urn}'.encode('utf-8')).hexdigest()[:16]}",
                    source_id=h_urn,
                    target_id=ev.entity_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    confidence=1.0,
                    properties={"pid": ev.pid},
                )
                try:
                    graph.add_relationship(contains_rel)
                    mutations += 1
                except Exception:
                    pass

                # Connect PROCESS -> SPAWNED_BY -> PARENT
                if ev.parent_entity_urn and graph.get_entity(ev.parent_entity_urn):
                    spawn_rel = TwinRelationship(
                        relation_id=f"rel_{hashlib.sha256(f'{ev.entity_urn}:SPAWNED_BY:{ev.parent_entity_urn}'.encode('utf-8')).hexdigest()[:16]}",
                        source_id=ev.entity_urn,
                        target_id=ev.parent_entity_urn,
                        relation_type=TwinRelationType.SPAWNED_BY,
                        confidence=1.0,
                        properties={"ppid": ev.ppid},
                    )
                    try:
                        graph.add_relationship(spawn_rel)
                        mutations += 1
                    except Exception:
                        pass

                # Connect APP -> OWNS -> PROCESS
                if ev.app_entity_urn:
                    # Register app if missing
                    if not graph.get_entity(ev.app_entity_urn):
                        graph.add_entity(
                            TwinEntity(
                                entity_id=ev.app_entity_urn,
                                entity_type=TwinEntityType.APPLICATION,
                                ownership=ev.ownership,
                                created_at=ev.observed_at_iso,
                                updated_at=ev.observed_at_iso,
                                provenance_source="process_lifecycle:inferred_app",
                            )
                        )
                    owns_rel = TwinRelationship(
                        relation_id=f"rel_{hashlib.sha256(f'{ev.app_entity_urn}:OWNS:{ev.entity_urn}'.encode('utf-8')).hexdigest()[:16]}",
                        source_id=ev.app_entity_urn,
                        target_id=ev.entity_urn,
                        relation_type=TwinRelationType.OWNS,
                        confidence=0.95,
                        properties={"pid": ev.pid},
                    )
                    try:
                        graph.add_relationship(owns_rel)
                        mutations += 1
                    except Exception:
                        pass

            elif ev.event_type in (
                ProcessLifecycleEventType.PROCESS_EXITED,
                ProcessLifecycleEventType.PROCESS_CRASHED,
                ProcessLifecycleEventType.PROCESS_SIGNALED,
            ):
                # Mark process node stale with exit metadata
                existing = graph.get_entity(ev.entity_urn)
                if existing:
                    updated_attrs = dict(existing.attributes)
                    updated_attrs["exit_epoch_ms"] = ev.exit_epoch_ms
                    updated_attrs["exit_code"] = ev.exit_code
                    updated_attrs["exit_status"] = ev.exit_status.value
                    updated_attrs["runtime_ms"] = ev.runtime_ms
                    updated_attrs["stale_reason"] = ev.event_type.value
                    updated_attrs["stale_since_epoch_ms"] = ev.exit_epoch_ms

                    updated_entity = TwinEntity(
                        entity_id=existing.entity_id,
                        entity_type=existing.entity_type,
                        ownership=existing.ownership,
                        attributes=updated_attrs,
                        created_at=existing.created_at,
                        updated_at=ev.observed_at_iso,
                        provenance_source=existing.provenance_source,
                        is_stale=True,
                    )
                    graph.add_entity(updated_entity)
                    mutations += 1

        return mutations

    @classmethod
    def sync_with_event_store(
        cls,
        events: List[ProcessLifecycleEvent],
        event_store: SystemEventStore,
        correlation_id: Optional[str] = None,
    ) -> List[SystemEventRecord]:
        """Bridges process lifecycle transitions to append-only SystemEventStore with SHA-256 hash chaining."""
        event_records: List[SystemEventRecord] = []
        for ev in events:
            if ev.event_type in (
                ProcessLifecycleEventType.PROCESS_STARTED,
                ProcessLifecycleEventType.PROCESS_FORKED,
            ):
                sys_type = SystemEventType.PROCESS_SPAWNED
            else:
                sys_type = SystemEventType.PROCESS_EXITED

            payload = {
                "pid": ev.pid,
                "ppid": ev.ppid,
                "process_name": ev.process_name,
                "binary_path": ev.binary_path,
                "command_line": ev.command_line,
                "user_name": ev.user_name,
                "uid": ev.uid,
                "start_epoch_ms": ev.start_epoch_ms,
                "exit_epoch_ms": ev.exit_epoch_ms,
                "exit_code": ev.exit_code,
                "exit_status": ev.exit_status.value,
                "runtime_ms": ev.runtime_ms,
                "ownership": ev.ownership.value,
                "parent_entity_urn": ev.parent_entity_urn,
                "app_entity_urn": ev.app_entity_urn,
            }

            rec = event_store.append_event(
                device_id=ev.device_id,
                entity_urn=ev.entity_urn,
                event_type=sys_type,
                payload=payload,
                component_ownership=ev.ownership,
                correlation_id=correlation_id,
                timestamp_iso=ev.observed_at_iso,
                timestamp_epoch_ms=ev.observed_at_epoch_ms,
            )
            event_records.append(rec)
        return event_records


class ProcessLifecycleManager:
    """Relational repository manager for persistent process lifecycle events in SQLite."""

    @classmethod
    def record_event(cls, conn: sqlite3.Connection, event: ProcessLifecycleEvent) -> None:
        """Persists a single process lifecycle event into process_lifecycle_events."""
        cls.record_events(conn, [event])

    @classmethod
    def record_events(cls, conn: sqlite3.Connection, events: Sequence[ProcessLifecycleEvent]) -> None:
        """Atomically persists a collection of process lifecycle events."""
        if not events:
            return

        stmt = """
        INSERT OR REPLACE INTO process_lifecycle_events (
            event_id, device_id, entity_urn, event_type,
            pid, ppid, process_name, binary_path, command_line,
            user_name, uid, start_epoch_ms, exit_epoch_ms,
            exit_code, exit_status, runtime_ms, ownership,
            detection_source, observed_at_iso, observed_at_epoch_ms,
            parent_entity_urn, app_entity_urn, metadata_json, scan_proves_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        rows = []
        exit_updates = []
        for ev in events:
            rows.append((
                ev.event_id,
                ev.device_id,
                ev.entity_urn,
                ev.event_type.value,
                ev.pid,
                ev.ppid,
                ev.process_name,
                ev.binary_path,
                ev.command_line,
                ev.user_name,
                ev.uid,
                ev.start_epoch_ms,
                ev.exit_epoch_ms,
                ev.exit_code,
                ev.exit_status.value,
                ev.runtime_ms,
                ev.ownership.value,
                ev.detection_source.value,
                ev.observed_at_iso,
                ev.observed_at_epoch_ms,
                ev.parent_entity_urn,
                ev.app_entity_urn,
                json.dumps(ev.metadata, sort_keys=True),
                0,
            ))
            if ev.exit_epoch_ms is not None:
                exit_updates.append((
                    ev.exit_epoch_ms,
                    ev.exit_code,
                    ev.exit_status.value,
                    ev.runtime_ms,
                    ev.entity_urn,
                ))

        with conn:
            conn.executemany(stmt, rows)
            if exit_updates:
                conn.executemany(
                    """
                    UPDATE process_lifecycle_events
                    SET exit_epoch_ms = ?, exit_code = ?, exit_status = ?, runtime_ms = ?
                    WHERE entity_urn = ? AND exit_epoch_ms IS NULL
                    """,
                    exit_updates,
                )

    @classmethod
    def get_events(
        cls,
        conn: sqlite3.Connection,
        device_id: Optional[str] = None,
        entity_urn: Optional[str] = None,
        pid: Optional[int] = None,
        event_type: Optional[ProcessLifecycleEventType] = None,
        limit: int = 100,
    ) -> List[ProcessLifecycleEvent]:
        """Queries process lifecycle events with multi-criteria filtering."""
        clauses = []
        params: List[Any] = []

        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if entity_urn:
            clauses.append("entity_urn = ?")
            params.append(entity_urn)
        if pid is not None:
            clauses.append("pid = ?")
            params.append(pid)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type.value)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
        SELECT
            event_id, device_id, entity_urn, event_type,
            pid, ppid, process_name, binary_path, command_line,
            user_name, uid, start_epoch_ms, exit_epoch_ms,
            exit_code, exit_status, runtime_ms, ownership,
            detection_source, observed_at_iso, observed_at_epoch_ms,
            parent_entity_urn, app_entity_urn, metadata_json, scan_proves_safe
        FROM process_lifecycle_events
        {where_sql}
        ORDER BY observed_at_epoch_ms ASC, pid ASC
        LIMIT ?
        """
        params.append(limit)

        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        results: List[ProcessLifecycleEvent] = []

        for row in cursor.fetchall():
            results.append(
                ProcessLifecycleEvent(
                    event_id=row[0],
                    device_id=row[1],
                    entity_urn=row[2],
                    event_type=ProcessLifecycleEventType(row[3]),
                    pid=row[4],
                    ppid=row[5],
                    process_name=row[6],
                    binary_path=row[7],
                    command_line=row[8],
                    user_name=row[9],
                    uid=row[10],
                    start_epoch_ms=row[11],
                    exit_epoch_ms=row[12],
                    exit_code=row[13],
                    exit_status=ProcessExitStatus(row[14]),
                    runtime_ms=row[15],
                    ownership=ComponentOwnership(row[16]),
                    detection_source=ProcessDetectionSource(row[17]),
                    observed_at_iso=row[18],
                    observed_at_epoch_ms=row[19],
                    parent_entity_urn=row[20],
                    app_entity_urn=row[21],
                    metadata=json.loads(row[22]) if row[22] else {},
                    scan_proves_safe=bool(row[23]),
                )
            )
        return results

    @classmethod
    def get_running_processes_at(
        cls,
        conn: sqlite3.Connection,
        target_epoch_ms: int,
        device_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Point-in-time process reconstruction: returns active running processes at target historical epoch millisecond."""
        params: List[Any] = []
        where_clauses = []
        if device_id:
            where_clauses.append("device_id = ?")
            params.append(device_id)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
        SELECT
            entity_urn, pid, ppid, process_name, binary_path,
            user_name, uid, MIN(start_epoch_ms) as start_epoch_ms,
            MAX(exit_epoch_ms) as exit_epoch_ms, ownership,
            parent_entity_urn, app_entity_urn
        FROM process_lifecycle_events
        {where_sql}
        GROUP BY entity_urn
        HAVING MIN(start_epoch_ms) <= ?
           AND (MAX(exit_epoch_ms) IS NULL OR MAX(exit_epoch_ms) > ?)
        ORDER BY pid ASC
        """
        params.extend([target_epoch_ms, target_epoch_ms])
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        active: List[Dict[str, Any]] = []

        for row in cursor.fetchall():
            active.append({
                "entity_urn": row[0],
                "pid": row[1],
                "ppid": row[2],
                "process_name": row[3],
                "binary_path": row[4],
                "user_name": row[5],
                "uid": row[6],
                "start_epoch_ms": row[7],
                "exit_epoch_ms": row[8],
                "ownership": row[9],
                "parent_entity_urn": row[10],
                "app_entity_urn": row[11],
            })
        return active

    @classmethod
    def get_process_lineage(
        cls,
        conn: sqlite3.Connection,
        entity_urn: str,
    ) -> List[ProcessLifecycleEvent]:
        """Recursively traverses the process parentage tree (PPID ancestry) from child to root."""
        lineage: List[ProcessLifecycleEvent] = []
        curr_urn = entity_urn
        visited = set()

        while curr_urn and curr_urn not in visited:
            visited.add(curr_urn)
            events = cls.get_events(conn, entity_urn=curr_urn, limit=1)
            if not events:
                break
            ev = events[0]
            lineage.append(ev)
            curr_urn = ev.parent_entity_urn

        return lineage
