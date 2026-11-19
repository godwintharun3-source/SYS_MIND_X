"""Application installation, removal, and lifecycle tracking for the temporal digital twin.

Provides observable state transition tracking, multi-channel detection
(periodic inventory diffing, real-time filesystem notifications),
in-memory graph synchronization, append-only event store bridging with
cryptographic hash chaining, and point-in-time installed application reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import sqlite3
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union
import uuid

if TYPE_CHECKING:
    from system_mind.database.entity_models import ApplicationEntityRecord

from system_mind.core.types import ComponentOwnership
from system_mind.twin.event_store import (
    SystemEventRecord,
    SystemEventStore,
    SystemEventType,
)
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinRelationship,
    TwinRelationType,
)
from system_mind.twin.identity import (
    EntityDomain,
    create_entity_urn,
    validate_entity_urn,
)


class ApplicationLifecycleEventType(str, Enum):
    """Categorization of application lifecycle state transitions."""

    APPLICATION_INSTALLED = "APPLICATION_INSTALLED"
    APPLICATION_REMOVED = "APPLICATION_REMOVED"
    APPLICATION_UPGRADED = "APPLICATION_UPGRADED"
    APPLICATION_PATH_MUTATED = "APPLICATION_PATH_MUTATED"
    APPLICATION_RESTORED = "APPLICATION_RESTORED"


class ApplicationDetectionSource(str, Enum):
    """Origin telemetry channel through which the application event was observed."""

    INVENTORY_DIFF = "INVENTORY_DIFF"
    FSEVENTS_NOTIFICATION = "FSEVENTS_NOTIFICATION"
    PACKAGE_RECEIPT = "PACKAGE_RECEIPT"
    BUNDLE_METADATA = "BUNDLE_METADATA"


def sanitize_bundle_id_for_urn(bundle_id: str) -> str:
    """Normalizes bundle ID into a valid URN slug."""
    clean = bundle_id.strip().lower().replace(" ", "-")
    # Replace any non-alphanumeric chars with hyphen, keeping dots
    out = []
    for ch in clean:
        if ch.isalnum() or ch in (".", "-", "_"):
            out.append(ch)
        else:
            out.append("-")
    result = "".join(out).strip("-")
    return result if result else "unknown-app"


@dataclass(frozen=True)
class ApplicationLifecycleEvent:
    """Immutable record of an application installation, removal, or lifecycle transition."""

    device_id: str
    entity_urn: str
    event_type: ApplicationLifecycleEventType
    bundle_id: str
    app_name: str
    bundle_path: str
    version: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    previous_version: Optional[str] = None
    previous_path: Optional[str] = None
    ownership: ComponentOwnership = ComponentOwnership.USER_MANAGED
    detection_source: ApplicationDetectionSource = ApplicationDetectionSource.INVENTORY_DIFF
    observed_at_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    observed_at_epoch_ms: int = field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000)
    )
    code_signature: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    scan_proves_safe: bool = False  # Charter Invariant SC-03

    def __post_init__(self) -> None:
        """Enforces schema integrity and non-negotiable charter invariants."""
        # Invariant SC-03: scan_proves_safe must be False
        if self.scan_proves_safe is not False:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")

        # Invariant INV-APP-02: entity_urn must be valid canonical URN
        if not validate_entity_urn(self.entity_urn):
            raise ValueError(
                f"Invalid canonical entity URN: '{self.entity_urn}'. Must conform to URN schema."
            )

        if not self.device_id or not self.device_id.strip():
            raise ValueError("device_id cannot be empty.")
        if not self.bundle_id or not self.bundle_id.strip():
            raise ValueError("bundle_id cannot be empty.")
        if not self.app_name or not self.app_name.strip():
            raise ValueError("app_name cannot be empty.")
        if not self.bundle_path or not self.bundle_path.strip():
            raise ValueError("bundle_path cannot be empty.")
        if not self.version or not self.version.strip():
            raise ValueError("version cannot be empty.")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes event to dictionary representation."""
        return {
            "event_id": self.event_id,
            "device_id": self.device_id,
            "entity_urn": self.entity_urn,
            "event_type": self.event_type.value,
            "bundle_id": self.bundle_id,
            "app_name": self.app_name,
            "bundle_path": self.bundle_path,
            "version": self.version,
            "previous_version": self.previous_version,
            "previous_path": self.previous_path,
            "ownership": self.ownership.value,
            "detection_source": self.detection_source.value,
            "observed_at_iso": self.observed_at_iso,
            "observed_at_epoch_ms": self.observed_at_epoch_ms,
            "code_signature": self.code_signature,
            "metadata": self.metadata,
            "scan_proves_safe": self.scan_proves_safe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ApplicationLifecycleEvent:
        """Constructs an ApplicationLifecycleEvent from a dictionary."""
        ev_type = (
            ApplicationLifecycleEventType(data["event_type"])
            if isinstance(data["event_type"], str)
            else data["event_type"]
        )
        src = (
            ApplicationDetectionSource(data["detection_source"])
            if isinstance(data["detection_source"], str)
            else data["detection_source"]
        )
        ownership = (
            ComponentOwnership(data["ownership"])
            if isinstance(data["ownership"], str)
            else data["ownership"]
        )

        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            device_id=data["device_id"],
            entity_urn=data["entity_urn"],
            event_type=ev_type,
            bundle_id=data["bundle_id"],
            app_name=data["app_name"],
            bundle_path=data["bundle_path"],
            version=data["version"],
            previous_version=data.get("previous_version"),
            previous_path=data.get("previous_path"),
            ownership=ownership,
            detection_source=src,
            observed_at_iso=data.get(
                "observed_at_iso", datetime.now(timezone.utc).isoformat()
            ),
            observed_at_epoch_ms=data.get(
                "observed_at_epoch_ms",
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ),
            code_signature=data.get("code_signature", {}),
            metadata=data.get("metadata", {}),
            scan_proves_safe=bool(data.get("scan_proves_safe", False)),
        )

    def to_sqlite_params(self) -> Tuple[Any, ...]:
        """Serializes event to positional tuple for SQLite INSERT."""
        return (
            self.event_id,
            self.device_id,
            self.entity_urn,
            self.event_type.value,
            self.bundle_id,
            self.app_name,
            self.bundle_path,
            self.version,
            self.previous_version,
            self.previous_path,
            self.ownership.value,
            self.detection_source.value,
            self.observed_at_iso,
            self.observed_at_epoch_ms,
            json.dumps(self.code_signature, sort_keys=True, default=str),
            json.dumps(self.metadata, sort_keys=True, default=str),
            1 if self.scan_proves_safe else 0,
        )

    @classmethod
    def from_sqlite_row(
        cls, row: Union[sqlite3.Row, Tuple[Any, ...]]
    ) -> ApplicationLifecycleEvent:
        """Constructs an ApplicationLifecycleEvent from an SQLite query row."""
        if isinstance(row, sqlite3.Row):
            d = dict(row)
            return cls(
                event_id=d["event_id"],
                device_id=d["device_id"],
                entity_urn=d["entity_urn"],
                event_type=ApplicationLifecycleEventType(d["event_type"]),
                bundle_id=d["bundle_id"],
                app_name=d["app_name"],
                bundle_path=d["bundle_path"],
                version=d["version"],
                previous_version=d["previous_version"],
                previous_path=d["previous_path"],
                ownership=ComponentOwnership(d["ownership"]),
                detection_source=ApplicationDetectionSource(d["detection_source"]),
                observed_at_iso=d["observed_at_iso"],
                observed_at_epoch_ms=int(d["observed_at_epoch_ms"]),
                code_signature=json.loads(d["code_signature_json"]),
                metadata=json.loads(d["metadata_json"]),
                scan_proves_safe=bool(d["scan_proves_safe"]),
            )
        else:
            return cls(
                event_id=row[0],
                device_id=row[1],
                entity_urn=row[2],
                event_type=ApplicationLifecycleEventType(row[3]),
                bundle_id=row[4],
                app_name=row[5],
                bundle_path=row[6],
                version=row[7],
                previous_version=row[8],
                previous_path=row[9],
                ownership=ComponentOwnership(row[10]),
                detection_source=ApplicationDetectionSource(row[11]),
                observed_at_iso=row[12],
                observed_at_epoch_ms=int(row[13]),
                code_signature=json.loads(row[14]) if isinstance(row[14], str) else row[14],
                metadata=json.loads(row[15]) if isinstance(row[15], str) else row[15],
                scan_proves_safe=bool(row[16]),
            )


@dataclass(frozen=True)
class ApplicationLifecycleDiff:
    """Summary of application additions, removals, upgrades, and mutations across observations."""

    installed_apps: List[ApplicationLifecycleEvent] = field(default_factory=list)
    removed_apps: List[ApplicationLifecycleEvent] = field(default_factory=list)
    upgraded_apps: List[ApplicationLifecycleEvent] = field(default_factory=list)
    path_mutated_apps: List[ApplicationLifecycleEvent] = field(default_factory=list)
    unchanged_apps_count: int = 0
    evaluated_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    scan_proves_safe: bool = False  # Charter Invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter Invariant Violation (SC-03): scan_proves_safe must be False.")

    @property
    def total_mutations(self) -> int:
        """Returns the total number of mutated applications in this diff."""
        return (
            len(self.installed_apps)
            + len(self.removed_apps)
            + len(self.upgraded_apps)
            + len(self.path_mutated_apps)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes diff summary to dictionary."""
        return {
            "installed_count": len(self.installed_apps),
            "removed_count": len(self.removed_apps),
            "upgraded_count": len(self.upgraded_apps),
            "path_mutated_count": len(self.path_mutated_apps),
            "unchanged_apps_count": self.unchanged_apps_count,
            "total_mutations": self.total_mutations,
            "evaluated_at_iso": self.evaluated_at_iso,
            "scan_proves_safe": self.scan_proves_safe,
            "installed": [e.to_dict() for e in self.installed_apps],
            "removed": [e.to_dict() for e in self.removed_apps],
            "upgraded": [e.to_dict() for e in self.upgraded_apps],
            "path_mutated": [e.to_dict() for e in self.path_mutated_apps],
        }


class ApplicationLifecycleTracker:
    """Differential engine for detecting application installation, upgrade, path mutation, and removal."""

    @classmethod
    def _extract_app_dict(
        cls, app_item: Union[Any, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Normalizes an application record or dict into a standardized dictionary."""
        if hasattr(app_item, "bundle_id") and hasattr(app_item, "install_path") and not isinstance(app_item, dict):
            return {
                "bundle_id": app_item.bundle_id,
                "app_name": app_item.app_name,
                "version": app_item.version,
                "install_path": app_item.install_path,
                "ownership": app_item.ownership,
                "code_signature": getattr(app_item, "code_signature", {}),
                "entity_urn": app_item.entity_urn,
            }
        else:
            bundle_id = app_item.get("bundle_id") or app_item.get("id") or ""
            app_name = (
                app_item.get("app_name")
                or app_item.get("name")
                or app_item.get("display_name")
                or "Unknown"
            )
            version = str(app_item.get("version", "1.0.0"))
            install_path = (
                app_item.get("install_path")
                or app_item.get("bundle_path")
                or app_item.get("path")
                or f"/Applications/{app_name}.app"
            )
            ownership_raw = app_item.get("ownership", ComponentOwnership.USER_MANAGED)
            ownership = (
                ComponentOwnership(ownership_raw)
                if isinstance(ownership_raw, str)
                else ownership_raw
            )
            entity_urn = app_item.get(
                "entity_urn",
                create_entity_urn(
                    EntityDomain.APPLICATION, sanitize_bundle_id_for_urn(bundle_id)
                ),
            )
            return {
                "bundle_id": bundle_id,
                "app_name": app_name,
                "version": version,
                "install_path": install_path,
                "ownership": ownership,
                "code_signature": app_item.get("code_signature", {}),
                "entity_urn": entity_urn,
            }

    @classmethod
    def detect_from_inventory_diff(
        cls,
        previous_inventory: List[Union[ApplicationEntityRecord, Dict[str, Any]]],
        current_inventory: List[Union[ApplicationEntityRecord, Dict[str, Any]]],
        device_id: str,
        timestamp_iso: Optional[str] = None,
    ) -> ApplicationLifecycleDiff:
        """Detects application lifecycle state transitions between two successive inventory observations."""
        now_iso = timestamp_iso or datetime.now(timezone.utc).isoformat()
        now_epoch = int(datetime.fromisoformat(now_iso).timestamp() * 1000)

        prev_map: Dict[str, Dict[str, Any]] = {}
        for item in previous_inventory:
            d = cls._extract_app_dict(item)
            key = d["bundle_id"] if d["bundle_id"] else d["install_path"]
            prev_map[key] = d

        curr_map: Dict[str, Dict[str, Any]] = {}
        for item in current_inventory:
            d = cls._extract_app_dict(item)
            key = d["bundle_id"] if d["bundle_id"] else d["install_path"]
            curr_map[key] = d

        installed_events: List[ApplicationLifecycleEvent] = []
        removed_events: List[ApplicationLifecycleEvent] = []
        upgraded_events: List[ApplicationLifecycleEvent] = []
        path_mutated_events: List[ApplicationLifecycleEvent] = []
        unchanged_count = 0

        # Check applications in current inventory
        for key, curr_app in curr_map.items():
            if key not in prev_map:
                # Check if it was moved from another path (matching bundle_id)
                moved_from = None
                for p_key, p_app in prev_map.items():
                    if (
                        p_app["bundle_id"] == curr_app["bundle_id"]
                        and p_app["install_path"] != curr_app["install_path"]
                        and p_key not in curr_map
                    ):
                        moved_from = p_app
                        break

                if moved_from is not None:
                    # Application path mutation / rename
                    path_mutated_events.append(
                        ApplicationLifecycleEvent(
                            device_id=device_id,
                            entity_urn=curr_app["entity_urn"],
                            event_type=ApplicationLifecycleEventType.APPLICATION_PATH_MUTATED,
                            bundle_id=curr_app["bundle_id"],
                            app_name=curr_app["app_name"],
                            bundle_path=curr_app["install_path"],
                            version=curr_app["version"],
                            previous_version=moved_from["version"],
                            previous_path=moved_from["install_path"],
                            ownership=curr_app["ownership"],
                            detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
                            observed_at_iso=now_iso,
                            observed_at_epoch_ms=now_epoch,
                            code_signature=curr_app.get("code_signature", {}),
                            scan_proves_safe=False,
                        )
                    )
                else:
                    # Brand new installation
                    installed_events.append(
                        ApplicationLifecycleEvent(
                            device_id=device_id,
                            entity_urn=curr_app["entity_urn"],
                            event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
                            bundle_id=curr_app["bundle_id"],
                            app_name=curr_app["app_name"],
                            bundle_path=curr_app["install_path"],
                            version=curr_app["version"],
                            previous_version=None,
                            previous_path=None,
                            ownership=curr_app["ownership"],
                            detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
                            observed_at_iso=now_iso,
                            observed_at_epoch_ms=now_epoch,
                            code_signature=curr_app.get("code_signature", {}),
                            scan_proves_safe=False,
                        )
                    )
            else:
                prev_app = prev_map[key]
                # Compare version and attributes
                v_prev = str(prev_app.get("version", ""))
                v_curr = str(curr_app.get("version", ""))
                path_prev = str(prev_app.get("install_path", ""))
                path_curr = str(curr_app.get("install_path", ""))

                if v_prev != v_curr:
                    # Version upgrade
                    upgraded_events.append(
                        ApplicationLifecycleEvent(
                            device_id=device_id,
                            entity_urn=curr_app["entity_urn"],
                            event_type=ApplicationLifecycleEventType.APPLICATION_UPGRADED,
                            bundle_id=curr_app["bundle_id"],
                            app_name=curr_app["app_name"],
                            bundle_path=curr_app["install_path"],
                            version=v_curr,
                            previous_version=v_prev,
                            previous_path=path_prev if path_prev != path_curr else None,
                            ownership=curr_app["ownership"],
                            detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
                            observed_at_iso=now_iso,
                            observed_at_epoch_ms=now_epoch,
                            code_signature=curr_app.get("code_signature", {}),
                            scan_proves_safe=False,
                        )
                    )
                elif path_prev != path_curr:
                    # Path mutation
                    path_mutated_events.append(
                        ApplicationLifecycleEvent(
                            device_id=device_id,
                            entity_urn=curr_app["entity_urn"],
                            event_type=ApplicationLifecycleEventType.APPLICATION_PATH_MUTATED,
                            bundle_id=curr_app["bundle_id"],
                            app_name=curr_app["app_name"],
                            bundle_path=curr_app["install_path"],
                            version=v_curr,
                            previous_version=v_prev,
                            previous_path=path_prev,
                            ownership=curr_app["ownership"],
                            detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
                            observed_at_iso=now_iso,
                            observed_at_epoch_ms=now_epoch,
                            code_signature=curr_app.get("code_signature", {}),
                            scan_proves_safe=False,
                        )
                    )
                else:
                    unchanged_count += 1

        # Check applications in previous inventory that disappeared
        for key, prev_app in prev_map.items():
            if key not in curr_map:
                # Verify it wasn't moved to another path already handled
                was_moved = any(
                    e.bundle_id == prev_app["bundle_id"] for e in path_mutated_events
                )
                if not was_moved:
                    removed_events.append(
                        ApplicationLifecycleEvent(
                            device_id=device_id,
                            entity_urn=prev_app["entity_urn"],
                            event_type=ApplicationLifecycleEventType.APPLICATION_REMOVED,
                            bundle_id=prev_app["bundle_id"],
                            app_name=prev_app["app_name"],
                            bundle_path=prev_app["install_path"],
                            version=prev_app["version"],
                            previous_version=prev_app["version"],
                            previous_path=prev_app["install_path"],
                            ownership=prev_app["ownership"],
                            detection_source=ApplicationDetectionSource.INVENTORY_DIFF,
                            observed_at_iso=now_iso,
                            observed_at_epoch_ms=now_epoch,
                            code_signature=prev_app.get("code_signature", {}),
                            scan_proves_safe=False,
                        )
                    )

        return ApplicationLifecycleDiff(
            installed_apps=installed_events,
            removed_apps=removed_events,
            upgraded_apps=upgraded_events,
            path_mutated_apps=path_mutated_events,
            unchanged_apps_count=unchanged_count,
            evaluated_at_iso=now_iso,
            scan_proves_safe=False,
        )

    @classmethod
    def detect_from_fsevents(
        cls,
        fsevents: List[Dict[str, Any]],
        known_apps_by_path: Dict[str, Dict[str, Any]],
        device_id: str,
    ) -> List[ApplicationLifecycleEvent]:
        """Maps filesystem event notification telemetry on .app paths into application lifecycle events."""
        events: List[ApplicationLifecycleEvent] = []
        now_iso = datetime.now(timezone.utc).isoformat()
        now_epoch = int(datetime.fromisoformat(now_iso).timestamp() * 1000)

        for fse in fsevents:
            path = str(fse.get("path", "")).strip()
            # Only inspect paths that are application bundles (.app)
            if ".app" not in path:
                continue

            # Normalize to root bundle path: e.g. /Applications/Foo.app/Contents/... -> /Applications/Foo.app
            idx = path.find(".app")
            bundle_path = path[: idx + 4]

            flags = fse.get("flags", [])
            raw_flags = fse.get("raw_flags", 0)

            # Determine bundle display name
            app_name = bundle_path.rstrip("/").split("/")[-1].replace(".app", "")
            slug = sanitize_bundle_id_for_urn(app_name)
            urn = create_entity_urn(EntityDomain.APPLICATION, slug)
            bundle_id = f"com.systemmind.app.{slug}"

            # Check if this bundle path was previously known
            known = known_apps_by_path.get(bundle_path, {})
            if known:
                bundle_id = known.get("bundle_id", bundle_id)
                app_name = known.get("app_name", app_name)
                urn = known.get("entity_urn", urn)
                version = str(known.get("version", "1.0.0"))
                ownership = known.get("ownership", ComponentOwnership.USER_MANAGED)
            else:
                version = "1.0.0"
                ownership = ComponentOwnership.USER_MANAGED

            # Inspect flags for removal or creation
            is_removed = (
                "ItemRemoved" in flags
                or "ItemRenamed" in flags
                and not fse.get("is_dir", True)
                or (raw_flags & 0x00000200) != 0  # kFSEventStreamEventFlagItemRemoved
            )
            is_created = (
                "ItemCreated" in flags
                or (raw_flags & 0x00000100) != 0  # kFSEventStreamEventFlagItemCreated
            )

            if is_removed and known:
                events.append(
                    ApplicationLifecycleEvent(
                        device_id=device_id,
                        entity_urn=urn,
                        event_type=ApplicationLifecycleEventType.APPLICATION_REMOVED,
                        bundle_id=bundle_id,
                        app_name=app_name,
                        bundle_path=bundle_path,
                        version=version,
                        previous_version=version,
                        previous_path=bundle_path,
                        ownership=ownership,
                        detection_source=ApplicationDetectionSource.FSEVENTS_NOTIFICATION,
                        observed_at_iso=fse.get("timestamp", now_iso),
                        observed_at_epoch_ms=now_epoch,
                        metadata={"raw_flags": raw_flags, "fsevent_path": path},
                        scan_proves_safe=False,
                    )
                )
            elif is_created and not known:
                events.append(
                    ApplicationLifecycleEvent(
                        device_id=device_id,
                        entity_urn=urn,
                        event_type=ApplicationLifecycleEventType.APPLICATION_INSTALLED,
                        bundle_id=bundle_id,
                        app_name=app_name,
                        bundle_path=bundle_path,
                        version=version,
                        ownership=ownership,
                        detection_source=ApplicationDetectionSource.FSEVENTS_NOTIFICATION,
                        observed_at_iso=fse.get("timestamp", now_iso),
                        observed_at_epoch_ms=now_epoch,
                        metadata={"raw_flags": raw_flags, "fsevent_path": path},
                        scan_proves_safe=False,
                    )
                )

        return events

    @classmethod
    def apply_to_graph(
        cls,
        events: List[ApplicationLifecycleEvent],
        graph: DigitalTwinGraph,
        host_urn: Optional[str] = None,
    ) -> None:
        """Applies application lifecycle state transitions directly to the in-memory DigitalTwinGraph."""
        for ev in events:
            if ev.event_type == ApplicationLifecycleEventType.APPLICATION_INSTALLED:
                entity = TwinEntity(
                    entity_id=ev.entity_urn,
                    entity_type=TwinEntityType.APPLICATION,
                    ownership=ev.ownership,
                    attributes={
                        "bundle_id": ev.bundle_id,
                        "app_name": ev.app_name,
                        "install_path": ev.bundle_path,
                        "version": ev.version,
                        "installed_at_iso": ev.observed_at_iso,
                        "code_signature": ev.code_signature,
                    },
                    created_at=ev.observed_at_iso,
                    updated_at=ev.observed_at_iso,
                    provenance_source=f"lifecycle:{ev.detection_source.value}",
                    is_stale=False,
                )
                graph.add_entity(entity)

                # Link HOST -> CONTAINS -> APPLICATION
                h_urn = host_urn or f"urn:systemmind:host:{ev.device_id}"
                if h_urn in graph.entities:
                    rel = TwinRelationship(
                        relation_id=f"rel-contains-{ev.device_id}-{sanitize_bundle_id_for_urn(ev.bundle_id)}",
                        source_id=h_urn,
                        target_id=ev.entity_urn,
                        relation_type=TwinRelationType.CONTAINS,
                        confidence=1.0,
                        observed_at=ev.observed_at_iso,
                        properties={"installed_via": ev.detection_source.value},
                    )
                    graph.add_relationship(rel)

            elif ev.event_type == ApplicationLifecycleEventType.APPLICATION_REMOVED:
                if ev.entity_urn in graph.entities:
                    existing = graph.entities[ev.entity_urn]
                    updated_attrs = dict(existing.attributes)
                    updated_attrs["tombstoned_at"] = ev.observed_at_iso
                    updated_attrs["stale_reason"] = "APPLICATION_REMOVED"
                    updated_entity = TwinEntity(
                        entity_id=existing.entity_id,
                        entity_type=existing.entity_type,
                        ownership=existing.ownership,
                        attributes=updated_attrs,
                        created_at=existing.created_at,
                        updated_at=ev.observed_at_iso,
                        provenance_source=f"lifecycle:{ev.detection_source.value}",
                        is_stale=True,
                    )
                    graph.add_entity(updated_entity)

            elif ev.event_type == ApplicationLifecycleEventType.APPLICATION_UPGRADED:
                if ev.entity_urn in graph.entities:
                    existing = graph.entities[ev.entity_urn]
                    updated_attrs = dict(existing.attributes)
                    history = list(updated_attrs.get("version_history", []))
                    if ev.previous_version:
                        history.append(
                            {
                                "version": ev.previous_version,
                                "upgraded_at": ev.observed_at_iso,
                            }
                        )
                    updated_attrs["version"] = ev.version
                    updated_attrs["version_history"] = history
                    updated_attrs["last_upgraded_at"] = ev.observed_at_iso
                    updated_entity = TwinEntity(
                        entity_id=existing.entity_id,
                        entity_type=existing.entity_type,
                        ownership=existing.ownership,
                        attributes=updated_attrs,
                        created_at=existing.created_at,
                        updated_at=ev.observed_at_iso,
                        provenance_source=f"lifecycle:{ev.detection_source.value}",
                        is_stale=False,
                    )
                    graph.add_entity(updated_entity)

            elif ev.event_type == ApplicationLifecycleEventType.APPLICATION_PATH_MUTATED:
                if ev.entity_urn in graph.entities:
                    existing = graph.entities[ev.entity_urn]
                    updated_attrs = dict(existing.attributes)
                    updated_attrs["install_path"] = ev.bundle_path
                    updated_attrs["previous_path"] = ev.previous_path
                    updated_attrs["path_mutated_at"] = ev.observed_at_iso
                    updated_entity = TwinEntity(
                        entity_id=existing.entity_id,
                        entity_type=existing.entity_type,
                        ownership=existing.ownership,
                        attributes=updated_attrs,
                        created_at=existing.created_at,
                        updated_at=ev.observed_at_iso,
                        provenance_source=f"lifecycle:{ev.detection_source.value}",
                        is_stale=False,
                    )
                    graph.add_entity(updated_entity)

    @classmethod
    def sync_with_event_store(
        cls,
        events: List[ApplicationLifecycleEvent],
        event_store: SystemEventStore,
        correlation_id: Optional[str] = None,
    ) -> List[SystemEventRecord]:
        """Bridges application lifecycle transitions to append-only SystemEventStore with SHA-256 hash chaining."""
        event_records: List[SystemEventRecord] = []
        for ev in events:
            # Map to SystemEventType
            if ev.event_type == ApplicationLifecycleEventType.APPLICATION_INSTALLED:
                sys_type = SystemEventType.APPLICATION_INSTALLED
            elif ev.event_type == ApplicationLifecycleEventType.APPLICATION_REMOVED:
                sys_type = SystemEventType.APPLICATION_UNINSTALLED
            elif ev.event_type == ApplicationLifecycleEventType.APPLICATION_UPGRADED:
                sys_type = SystemEventType.CONFIG_MUTATED
            else:
                sys_type = SystemEventType.CONFIG_MUTATED

            payload = {
                "bundle_id": ev.bundle_id,
                "app_name": ev.app_name,
                "bundle_path": ev.bundle_path,
                "version": ev.version,
                "previous_version": ev.previous_version,
                "previous_path": ev.previous_path,
                "detection_source": ev.detection_source.value,
                "lifecycle_event_type": ev.event_type.value,
                "code_signature": ev.code_signature,
            }

            metadata = {
                "lifecycle_event_id": ev.event_id,
                "ownership": ev.ownership.value,
            }

            rec = event_store.append_event(
                device_id=ev.device_id,
                entity_urn=ev.entity_urn,
                event_type=sys_type,
                payload=payload,
                metadata=metadata,
                component_ownership=ev.ownership,
                correlation_id=correlation_id,
            )
            event_records.append(rec)

        return event_records


class ApplicationLifecycleManager:
    """Repository manager for storing, querying, and auditing application lifecycle events in SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    def record_event(self, event: ApplicationLifecycleEvent) -> None:
        """Stores a single application lifecycle transition in the relational database."""
        sql = """
        INSERT INTO application_lifecycle_events (
            event_id, device_id, entity_urn, event_type,
            bundle_id, app_name, bundle_path, version,
            previous_version, previous_path, ownership,
            detection_source, observed_at_iso, observed_at_epoch_ms,
            code_signature_json, metadata_json, scan_proves_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self._conn.execute(sql, event.to_sqlite_params())
        self._conn.commit()

    def record_diff(self, diff: ApplicationLifecycleDiff) -> None:
        """Stores all lifecycle transitions from an ApplicationLifecycleDiff in a single transaction."""
        all_events = (
            diff.installed_apps
            + diff.removed_apps
            + diff.upgraded_apps
            + diff.path_mutated_apps
        )
        sql = """
        INSERT INTO application_lifecycle_events (
            event_id, device_id, entity_urn, event_type,
            bundle_id, app_name, bundle_path, version,
            previous_version, previous_path, ownership,
            detection_source, observed_at_iso, observed_at_epoch_ms,
            code_signature_json, metadata_json, scan_proves_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [ev.to_sqlite_params() for ev in all_events]
        self._conn.executemany(sql, params)
        self._conn.commit()

    def get_history(
        self, bundle_id_or_urn: str, device_id: Optional[str] = None
    ) -> List[ApplicationLifecycleEvent]:
        """Retrieves chronological lifecycle transition history for an application."""
        if bundle_id_or_urn.startswith("urn:systemmind:"):
            query = "SELECT * FROM application_lifecycle_events WHERE entity_urn = ?"
            params: List[Any] = [bundle_id_or_urn]
        else:
            query = "SELECT * FROM application_lifecycle_events WHERE bundle_id = ?"
            params = [bundle_id_or_urn]

        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)

        query += " ORDER BY observed_at_epoch_ms ASC"
        cursor = self._conn.execute(query, params)
        return [ApplicationLifecycleEvent.from_sqlite_row(row) for row in cursor.fetchall()]

    def get_recent_events(
        self,
        limit: int = 50,
        event_type: Optional[ApplicationLifecycleEventType] = None,
        device_id: Optional[str] = None,
    ) -> List[ApplicationLifecycleEvent]:
        """Retrieves recent application lifecycle events across the host."""
        query = "SELECT * FROM application_lifecycle_events WHERE 1=1"
        params: List[Any] = []

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)

        query += " ORDER BY observed_at_epoch_ms DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.execute(query, params)
        return [ApplicationLifecycleEvent.from_sqlite_row(row) for row in cursor.fetchall()]

    def get_installed_applications_at(
        self, target_epoch_ms: int, device_id: str
    ) -> List[Any]:
        """Reconstructs the set of installed applications on a device at a specific point in time."""
        from system_mind.database.entity_models import ApplicationEntityRecord
        query = """
        SELECT * FROM application_lifecycle_events
        WHERE device_id = ? AND observed_at_epoch_ms <= ?
        ORDER BY observed_at_epoch_ms ASC
        """
        cursor = self._conn.execute(query, (device_id, target_epoch_ms))
        rows = cursor.fetchall()

        # State map: bundle_id -> latest state
        installed_map: Dict[str, ApplicationLifecycleEvent] = {}

        for row in rows:
            ev = ApplicationLifecycleEvent.from_sqlite_row(row)
            if ev.event_type in (
                ApplicationLifecycleEventType.APPLICATION_INSTALLED,
                ApplicationLifecycleEventType.APPLICATION_UPGRADED,
                ApplicationLifecycleEventType.APPLICATION_PATH_MUTATED,
                ApplicationLifecycleEventType.APPLICATION_RESTORED,
            ):
                installed_map[ev.bundle_id] = ev
            elif ev.event_type == ApplicationLifecycleEventType.APPLICATION_REMOVED:
                installed_map.pop(ev.bundle_id, None)

        records: List[ApplicationEntityRecord] = []
        for ev in installed_map.values():
            records.append(
                ApplicationEntityRecord(
                    entity_urn=ev.entity_urn,
                    device_id=ev.device_id,
                    bundle_id=ev.bundle_id,
                    app_name=ev.app_name,
                    version=ev.version,
                    install_path=ev.bundle_path,
                    ownership=ev.ownership,
                    code_signature=ev.code_signature,
                    observed_at=ev.observed_at_iso,
                    provenance_source=f"reconstructed:{ev.detection_source.value}",
                    scan_proves_safe=False,
                )
            )

        return sorted(records, key=lambda r: r.bundle_id)
