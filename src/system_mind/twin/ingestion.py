"""Entity relationship ingestion engine transforming collector telemetry into Digital Twin graph topology."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from system_mind.core.types import ComponentOwnership
from system_mind.twin.graph import DigitalTwinGraph
from system_mind.twin.identity import (
    DeviceIdentifierManager,
    EntityDomain,
    EntityUrn,
    StableEntityIdGenerator,
)
from system_mind.twin.models import (
    TwinEntity,
    TwinEntityType,
    TwinEntityValidator,
    TwinRelationship,
    TwinRelationType,
)
from system_mind.twin.persistence import GraphPersistenceManager


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of ingesting telemetry collector observations into the Digital Twin."""

    ingestion_id: str
    device_id: str
    timestamp_utc: str
    entities_ingested: int
    relationships_ingested: int
    entities: tuple[TwinEntity, ...]
    relationships: tuple[TwinRelationship, ...]
    warnings: tuple[str, ...]
    duration_ms: float = 0.0
    scan_proves_safe: bool = False  # Charter non-negotiable invariant SC-03

    def __post_init__(self) -> None:
        if self.scan_proves_safe is not False:
            raise ValueError("Charter invariant violation: scan_proves_safe must always be False")
        if not self.ingestion_id or not self.ingestion_id.strip():
            raise ValueError("ingestion_id must not be empty")
        if not self.device_id or not self.device_id.strip():
            raise ValueError("device_id must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "ingestion_id": self.ingestion_id,
            "device_id": self.device_id,
            "timestamp_utc": self.timestamp_utc,
            "entities_ingested": self.entities_ingested,
            "relationships_ingested": self.relationships_ingested,
            "entities_count": len(self.entities),
            "relationships_count": len(self.relationships),
            "warnings": list(self.warnings),
            "duration_ms": round(self.duration_ms, 2),
            "scan_proves_safe": self.scan_proves_safe,
        }


class EntityRelationshipIngestor:
    """Ingests collector telemetry reports and synthesizes directed entity relationships in the Digital Twin."""

    def __init__(self, device_id: Optional[str] = None) -> None:
        self.device_id = device_id or DeviceIdentifierManager.resolve_device_id()

    @staticmethod
    def _generate_relation_id(source_id: str, rel_type: TwinRelationType, target_id: str) -> str:
        """Derive deterministic relation identifier from source, type, and target."""
        raw = f"{source_id}:{rel_type.value}:{target_id}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"rel:{digest}"

    @staticmethod
    def _now_iso() -> str:
        """Return current UTC ISO 8601 timestamp."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _find_section(sections: Dict[str, Any], key: str) -> Dict[str, Any]:
        """Case-insensitively locate section dictionary."""
        val = sections.get(key.upper()) or sections.get(key.lower()) or sections.get(key)
        return val if isinstance(val, dict) else {}

    def ingest_inventory(
        self,
        inventory: Any,
        graph: Optional[DigitalTwinGraph] = None,
        persistence_manager: Optional[GraphPersistenceManager] = None,
    ) -> IngestionResult:
        """Ingest a complete MacOsInventoryResponse or serialized dictionary into the digital twin."""
        start_time = time.perf_counter()
        inv_dict = inventory.to_dict() if hasattr(inventory, "to_dict") else inventory
        if not isinstance(inv_dict, dict):
            raise TypeError(f"Inventory must be a dict or support to_dict(), got {type(inventory)}")

        sections = inv_dict.get("sections", {})
        summary = inv_dict.get("summary", {})
        timestamp = inv_dict.get("timestamp_utc", self._now_iso())

        return self._ingest_internal(
            sections=sections,
            summary=summary,
            base_timestamp=timestamp,
            provenance="macos_inventory_api",
            graph=graph,
            persistence_manager=persistence_manager,
            start_time=start_time,
        )

    def ingest_companion_batch(
        self,
        batch: Any,
        graph: Optional[DigitalTwinGraph] = None,
        persistence_manager: Optional[GraphPersistenceManager] = None,
    ) -> IngestionResult:
        """Ingest a CompanionObservationBatch into the digital twin."""
        start_time = time.perf_counter()
        batch_dict = batch.to_dict() if hasattr(batch, "to_dict") else batch
        if not isinstance(batch_dict, dict):
            raise TypeError(f"Batch must be a dict or support to_dict(), got {type(batch)}")

        raw_observations = batch_dict.get("observations", {})
        timestamp = batch_dict.get("timestamp_utc", self._now_iso())

        # Unpack observation envelopes into standard sections
        sections: Dict[str, Any] = {}
        for coll_id, env in raw_observations.items():
            payload = env.get("payload", {}) if isinstance(env, dict) else getattr(env, "payload", {})
            payload_data = payload.to_dict() if hasattr(payload, "to_dict") else payload
            coll_lower = coll_id.lower()
            if "identity" in coll_lower:
                sections["IDENTITY"] = payload_data
            elif "hardware" in coll_lower or "cpu" in coll_lower:
                if "HARDWARE" not in sections:
                    sections["HARDWARE"] = {}
                sections["HARDWARE"]["cpu"] = payload_data
            elif "memory" in coll_lower:
                if "HARDWARE" not in sections:
                    sections["HARDWARE"] = {}
                sections["HARDWARE"]["memory"] = payload_data
            elif "gpu" in coll_lower:
                if "HARDWARE" not in sections:
                    sections["HARDWARE"] = {}
                sections["HARDWARE"]["gpu"] = payload_data
            elif "storage" in coll_lower:
                sections["STORAGE"] = payload_data
            elif "network" in coll_lower:
                sections["NETWORK"] = payload_data
            elif "app" in coll_lower:
                sections["APPLICATIONS"] = payload_data
            elif "proc" in coll_lower:
                sections["PROCESSES"] = payload_data
            elif "service" in coll_lower or "launchd" in coll_lower:
                sections["SERVICES"] = payload_data

        return self._ingest_internal(
            sections=sections,
            summary={},
            base_timestamp=timestamp,
            provenance="companion_observation_batch",
            graph=graph,
            persistence_manager=persistence_manager,
            start_time=start_time,
        )

    def ingest_sections(
        self,
        sections: Dict[str, Any],
        summary: Optional[Dict[str, Any]] = None,
        base_timestamp: Optional[str] = None,
        provenance: str = "telemetry_collector",
        graph: Optional[DigitalTwinGraph] = None,
        persistence_manager: Optional[GraphPersistenceManager] = None,
    ) -> IngestionResult:
        """Ingest raw telemetry section dictionary directly."""
        start_time = time.perf_counter()
        return self._ingest_internal(
            sections=sections,
            summary=summary or {},
            base_timestamp=base_timestamp or self._now_iso(),
            provenance=provenance,
            graph=graph,
            persistence_manager=persistence_manager,
            start_time=start_time,
        )

    def _ingest_internal(
        self,
        sections: Dict[str, Any],
        summary: Dict[str, Any],
        base_timestamp: str,
        provenance: str,
        graph: Optional[DigitalTwinGraph],
        persistence_manager: Optional[GraphPersistenceManager],
        start_time: float,
    ) -> IngestionResult:
        """Internal multi-stage pipeline extracting entities, synthesizing relationships, and committing."""
        target_graph = graph if graph is not None else DigitalTwinGraph()
        warnings: List[str] = []
        collected_entities: List[TwinEntity] = []
        collected_relationships: List[TwinRelationship] = []

        # 1. Extract Host and Kernel entities
        identity_data = self._find_section(sections, "identity")
        host_entity, kernel_entity, host_kernel_rel = self._extract_host_and_kernel(
            identity_data, summary, base_timestamp, provenance
        )
        collected_entities.append(host_entity)
        collected_entities.append(kernel_entity)
        collected_relationships.append(host_kernel_rel)
        host_urn = host_entity.entity_id

        # 2. Extract Hardware entities (CPU, Memory, GPU)
        hw_data = self._find_section(sections, "hardware")
        hw_entities, hw_rels = self._extract_hardware(hw_data, host_urn, base_timestamp, provenance)
        collected_entities.extend(hw_entities)
        collected_relationships.extend(hw_rels)

        # 3. Extract Storage entities (Volumes)
        storage_data = self._find_section(sections, "storage")
        storage_entities, storage_rels = self._extract_storage(
            storage_data, host_urn, base_timestamp, provenance
        )
        collected_entities.extend(storage_entities)
        collected_relationships.extend(storage_rels)

        # 4. Extract Network interfaces
        network_data = self._find_section(sections, "network")
        net_entities, net_rels = self._extract_network(
            network_data, host_urn, base_timestamp, provenance
        )
        collected_entities.extend(net_entities)
        collected_relationships.extend(net_rels)

        # 5. Extract Applications and build lookup map for process ownership mapping
        apps_data = self._find_section(sections, "applications")
        app_entities, app_rels, app_lookup = self._extract_applications(
            apps_data, host_urn, base_timestamp, provenance
        )
        collected_entities.extend(app_entities)
        collected_relationships.extend(app_rels)

        # 6. Extract Processes and build process hierarchy (SPAWNED_BY) and app ownership (OWNS)
        proc_data = self._find_section(sections, "processes")
        proc_entities, proc_rels, pid_to_urn = self._extract_processes(
            proc_data, host_urn, kernel_entity.entity_id, app_lookup, base_timestamp, provenance
        )
        collected_entities.extend(proc_entities)
        collected_relationships.extend(proc_rels)

        # 7. Extract Services and associate with running processes where applicable
        services_data = self._find_section(sections, "services")
        svc_entities, svc_rels = self._extract_services(
            services_data, host_urn, pid_to_urn, base_timestamp, provenance
        )
        collected_entities.extend(svc_entities)
        collected_relationships.extend(svc_rels)

        # 8. Deduplicate and Add Entities to Graph
        entity_map: Dict[str, TwinEntity] = {}
        for ent in collected_entities:
            entity_map[ent.entity_id] = ent

        for ent in entity_map.values():
            try:
                target_graph.add_entity(ent)
            except Exception as exc:
                warnings.append(f"Failed to add entity '{ent.entity_id}': {exc}")

        # 9. Deduplicate and Add Relationships to Graph (Strict Referential Integrity)
        rel_map: Dict[str, TwinRelationship] = {}
        for rel in collected_relationships:
            # Check source and target exist
            if rel.source_id not in entity_map:
                warnings.append(f"Skipping dangling relationship: source '{rel.source_id}' missing")
                continue
            if rel.target_id not in entity_map:
                warnings.append(f"Skipping dangling relationship: target '{rel.target_id}' missing")
                continue
            rel_map[rel.relation_id] = rel

        for rel in rel_map.values():
            try:
                # Remove existing relation with same ID for safe idempotency
                if target_graph.get_relationship(rel.relation_id) is not None:
                    target_graph.remove_relationship(rel.relation_id)
                target_graph.add_relationship(rel)
            except Exception as exc:
                warnings.append(f"Failed to add relationship '{rel.relation_id}': {exc}")

        # 10. Persist to SQLite if manager is provided
        if persistence_manager is not None:
            try:
                persistence_manager.persist_graph(target_graph)
            except Exception as exc:
                warnings.append(f"Database graph persistence warning: {exc}")

        duration = (time.perf_counter() - start_time) * 1000.0
        ingestion_id = f"ingest-{hashlib.sha256(f'{self.device_id}:{base_timestamp}'.encode('utf-8')).hexdigest()[:12]}"

        return IngestionResult(
            ingestion_id=ingestion_id,
            device_id=self.device_id,
            timestamp_utc=base_timestamp,
            entities_ingested=len(entity_map),
            relationships_ingested=len(rel_map),
            entities=tuple(entity_map.values()),
            relationships=tuple(rel_map.values()),
            warnings=tuple(warnings),
            duration_ms=duration,
            scan_proves_safe=False,
        )

    # =========================================================================
    # Granular Extraction Helpers
    # =========================================================================

    def _extract_host_and_kernel(
        self,
        identity: Dict[str, Any],
        summary: Dict[str, Any],
        timestamp: str,
        provenance: str,
    ) -> Tuple[TwinEntity, TwinEntity, TwinRelationship]:
        """Extract Host device entity, OS kernel entity, and Host -> CONTAINS -> Kernel edge."""
        host_urn = StableEntityIdGenerator.generate_host_urn(self.device_id).urn
        # Safely unpack nested version_info and identity if present
        raw_version = identity.get("version_info") if isinstance(identity.get("version_info"), dict) else {}
        os_name = raw_version.get("os_name") or identity.get("os_name") or summary.get("os_version", "macOS")
        os_ver = raw_version.get("product_version") or identity.get("os_version") or summary.get("os_version", "15.0")
        os_build = raw_version.get("build_version") or identity.get("os_build") or summary.get("os_build", "24A335")
        kernel_rel = raw_version.get("kernel_release") or identity.get("kernel_release", "24.0.0")

        # Safely resolve architecture string
        raw_arch = identity.get("architecture")
        if isinstance(raw_arch, dict):
            arch = raw_arch.get("machine", "arm64")
        elif isinstance(raw_arch, str):
            arch = raw_arch
        else:
            arch = summary.get("architecture", "arm64")

        raw_id = identity.get("identity") if isinstance(identity.get("identity"), dict) else {}
        hostname = raw_id.get("hostname") or identity.get("host_name") or summary.get("host_name", "localhost")
        serial_hash = raw_id.get("anonymized_serial_hash") or identity.get("serial_hash", "")

        host_attrs = {
            "device_id": self.device_id,
            "host_name": hostname,
            "architecture": arch,
            "hardware_model": identity.get("hardware_model", "Apple Silicon"),
            "serial_hash": serial_hash,
        }
        host_entity = TwinEntity(
            entity_id=host_urn,
            entity_type=TwinEntityType.HOST,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            attributes=host_attrs,
            created_at=timestamp,
            updated_at=timestamp,
            provenance_source=f"{provenance}:identity",
            is_stale=False,
        )

        kernel_urn = StableEntityIdGenerator.generate_kernel_urn("darwin", kernel_rel, arch).urn
        kernel_attrs = {
            "os_name": os_name,
            "os_version": os_ver,
            "os_build": os_build,
            "kernel_release": kernel_rel,
            "architecture": arch,
        }
        kernel_entity = TwinEntity(
            entity_id=kernel_urn,
            entity_type=TwinEntityType.OS_KERNEL,
            ownership=ComponentOwnership.SYSTEM_MANAGED,
            attributes=kernel_attrs,
            created_at=timestamp,
            updated_at=timestamp,
            provenance_source=f"{provenance}:kernel",
            is_stale=False,
        )

        rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, kernel_urn)
        host_kernel_rel = TwinRelationship(
            relation_id=rel_id,
            source_id=host_urn,
            target_id=kernel_urn,
            relation_type=TwinRelationType.CONTAINS,
            properties={"subsystem": "operating_system"},
            observed_at=timestamp,
            confidence=1.0,
        )

        return host_entity, kernel_entity, host_kernel_rel

    def _extract_hardware(
        self,
        hardware: Dict[str, Any],
        host_urn: str,
        timestamp: str,
        provenance: str,
    ) -> Tuple[List[TwinEntity], List[TwinRelationship]]:
        """Extract CPU, Memory, and GPU hardware device entities and containment edges."""
        entities: List[TwinEntity] = []
        relationships: List[TwinRelationship] = []

        # 1. CPU Hardware
        cpu_data = hardware.get("cpu", {})
        if cpu_data:
            arch = cpu_data.get("architecture", "arm64")
            brand = cpu_data.get("brand_string") or cpu_data.get("model", "Apple M-Series")
            cores = cpu_data.get("logical_cores") or cpu_data.get("physical_cores", 8)

            cpu_urn = StableEntityIdGenerator.generate_cpu_urn(arch, brand, cores).urn
            cpu_entity = TwinEntity(
                entity_id=cpu_urn,
                entity_type=TwinEntityType.HARDWARE_DEVICE,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                attributes={
                    "category": "cpu",
                    "brand_string": brand,
                    "physical_cores": cpu_data.get("physical_cores", cores),
                    "logical_cores": cores,
                    "architecture": arch,
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:cpu",
            )
            entities.append(cpu_entity)

            rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, cpu_urn)
            relationships.append(
                TwinRelationship(
                    relation_id=rel_id,
                    source_id=host_urn,
                    target_id=cpu_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    properties={"component": "cpu"},
                    observed_at=timestamp,
                    confidence=1.0,
                )
            )

        # 2. Physical Memory
        mem_data = hardware.get("memory", {})
        if mem_data:
            total_bytes = mem_data.get("total_bytes") or mem_data.get("total_physical_bytes", 8589934592)
            mem_urn = StableEntityIdGenerator.generate_memory_urn(self.device_id, total_bytes).urn
            mem_entity = TwinEntity(
                entity_id=mem_urn,
                entity_type=TwinEntityType.HARDWARE_DEVICE,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                attributes={
                    "category": "memory",
                    "total_bytes": total_bytes,
                    "page_size": mem_data.get("page_size", 16384),
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:memory",
            )
            entities.append(mem_entity)

            rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, mem_urn)
            relationships.append(
                TwinRelationship(
                    relation_id=rel_id,
                    source_id=host_urn,
                    target_id=mem_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    properties={"component": "memory"},
                    observed_at=timestamp,
                    confidence=1.0,
                )
            )

        # 3. GPU / Display Hardware
        gpu_data = hardware.get("gpu", {})
        gpus = gpu_data.get("gpus", []) if isinstance(gpu_data, dict) else []
        for idx, gpu in enumerate(gpus):
            model = gpu.get("model", "Apple GPU")
            cores = gpu.get("cores", 8)
            model_digest = StableEntityIdGenerator.hash_token(f"{model}:{cores}", 8)
            gpu_urn = f"urn:systemmind:{EntityDomain.HOST.value}:{self.device_id[:8]}:gpu:{model_digest}"
            gpu_entity = TwinEntity(
                entity_id=gpu_urn,
                entity_type=TwinEntityType.HARDWARE_DEVICE,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                attributes={
                    "category": "gpu",
                    "model": model,
                    "cores": cores,
                    "metal_version": gpu.get("metal_version", "Metal 3"),
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:gpu",
            )
            entities.append(gpu_entity)

            rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, gpu_urn)
            relationships.append(
                TwinRelationship(
                    relation_id=rel_id,
                    source_id=host_urn,
                    target_id=gpu_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    properties={"component": "gpu", "index": idx},
                    observed_at=timestamp,
                    confidence=1.0,
                )
            )

        return entities, relationships

    def _extract_storage(
        self,
        storage: Dict[str, Any],
        host_urn: str,
        timestamp: str,
        provenance: str,
    ) -> Tuple[List[TwinEntity], List[TwinRelationship]]:
        """Extract storage volume entities and host containment edges."""
        entities: List[TwinEntity] = []
        relationships: List[TwinRelationship] = []

        volumes = storage.get("volumes", []) if isinstance(storage, dict) else []
        for vol in volumes:
            mount = vol.get("mount_point", "/")
            vol_urn = StableEntityIdGenerator.generate_storage_volume_urn(self.device_id, mount).urn

            vol_entity = TwinEntity(
                entity_id=vol_urn,
                entity_type=TwinEntityType.FILESYSTEM_NODE,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                attributes={
                    "category": "storage_volume",
                    "volume_name": vol.get("volume_name", "Macintosh HD"),
                    "mount_point": mount,
                    "fs_type": vol.get("fs_type", "apfs"),
                    "total_bytes": vol.get("total_bytes", 0),
                    "free_bytes": vol.get("free_bytes", 0),
                    "is_boot_volume": vol.get("is_boot_volume", mount == "/"),
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:storage",
            )
            entities.append(vol_entity)

            rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, vol_urn)
            relationships.append(
                TwinRelationship(
                    relation_id=rel_id,
                    source_id=host_urn,
                    target_id=vol_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    properties={"mount_point": mount},
                    observed_at=timestamp,
                    confidence=1.0,
                )
            )

        return entities, relationships

    def _extract_network(
        self,
        network: Dict[str, Any],
        host_urn: str,
        timestamp: str,
        provenance: str,
    ) -> Tuple[List[TwinEntity], List[TwinRelationship]]:
        """Extract network interface entities and host containment edges."""
        entities: List[TwinEntity] = []
        relationships: List[TwinRelationship] = []

        interfaces = network.get("interfaces", []) if isinstance(network, dict) else []
        for iface in interfaces:
            if_name = iface.get("interface_name", "en0")
            if_urn = StableEntityIdGenerator.generate_network_interface_urn(self.device_id, if_name).urn

            if_entity = TwinEntity(
                entity_id=if_urn,
                entity_type=TwinEntityType.NETWORK_SOCKET,
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                attributes={
                    "interface_name": if_name,
                    "mac_address_hash": iface.get("mac_address_hash", ""),
                    "ip_address": iface.get("ip_address", ""),
                    "link_state": iface.get("link_state", "UP"),
                    "is_up": iface.get("is_up", True),
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:network",
            )
            entities.append(if_entity)

            rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, if_urn)
            relationships.append(
                TwinRelationship(
                    relation_id=rel_id,
                    source_id=host_urn,
                    target_id=if_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    properties={"interface": if_name},
                    observed_at=timestamp,
                    confidence=1.0,
                )
            )

        return entities, relationships

    def _extract_applications(
        self,
        apps_data: Dict[str, Any],
        host_urn: str,
        timestamp: str,
        provenance: str,
    ) -> Tuple[List[TwinEntity], List[TwinRelationship], Dict[str, str]]:
        """Extract application entities, containment edges, and indexed lookup dictionary for process mapping."""
        entities: List[TwinEntity] = []
        relationships: List[TwinRelationship] = []
        app_lookup: Dict[str, str] = {}  # token -> app_urn

        apps = apps_data.get("applications", []) if isinstance(apps_data, dict) else []
        for app in apps:
            bundle_id = app.get("bundle_id") or app.get("name", "unknown_app")
            app_urn = StableEntityIdGenerator.generate_app_urn(bundle_id).urn

            # Ownership classification
            is_apple = app.get("is_apple", False)
            raw_own = app.get("ownership")
            if raw_own == ComponentOwnership.SYSTEM_MANAGED.value or (is_apple and not raw_own):
                ownership = ComponentOwnership.SYSTEM_MANAGED
            elif raw_own == ComponentOwnership.USER_MANAGED.value or app.get("is_user_app", True):
                ownership = ComponentOwnership.USER_MANAGED
            else:
                ownership = ComponentOwnership.VENDOR_MANAGED

            bundle_path = app.get("bundle_path", "")
            exec_name = app.get("executable_name", "")
            exec_path = app.get("executable_path", "")
            app_name = app.get("name", "")

            app_entity = TwinEntity(
                entity_id=app_urn,
                entity_type=TwinEntityType.APPLICATION,
                ownership=ownership,
                attributes={
                    "name": app_name,
                    "bundle_id": bundle_id,
                    "bundle_path": bundle_path,
                    "version": app.get("version", "1.0.0"),
                    "is_apple": is_apple,
                    "category": app.get("category", "OTHER"),
                    "executable_name": exec_name,
                    "executable_path": exec_path,
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:apps",
            )
            entities.append(app_entity)

            # Register containment edge
            rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, app_urn)
            relationships.append(
                TwinRelationship(
                    relation_id=rel_id,
                    source_id=host_urn,
                    target_id=app_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    properties={"bundle_id": bundle_id},
                    observed_at=timestamp,
                    confidence=1.0,
                )
            )

            # Index for process lookup
            if bundle_id:
                app_lookup[bundle_id.lower()] = app_urn
            if app_name:
                app_lookup[app_name.lower()] = app_urn
            if exec_name:
                app_lookup[exec_name.lower()] = app_urn
            if bundle_path:
                app_lookup[bundle_path.lower()] = app_urn
            if exec_path:
                app_lookup[exec_path.lower()] = app_urn

        return entities, relationships, app_lookup

    def _extract_processes(
        self,
        proc_data: Dict[str, Any],
        host_urn: str,
        kernel_urn: str,
        app_lookup: Dict[str, str],
        timestamp: str,
        provenance: str,
    ) -> Tuple[List[TwinEntity], List[TwinRelationship], Dict[int, str]]:
        """Extract process entities, process ancestry tree (SPAWNED_BY), and app ownership (OWNS)."""
        entities: List[TwinEntity] = []
        relationships: List[TwinRelationship] = []
        pid_to_urn: Dict[int, str] = {}
        proc_records: List[Dict[str, Any]] = []

        raw_procs = proc_data.get("processes", []) if isinstance(proc_data, dict) else []

        # Pass 1: Build Process Entities & map PID -> URN
        for proc in raw_procs:
            pid = int(proc.get("pid", 0))
            if pid <= 0:
                continue

            ppid = int(proc.get("ppid", 0))
            cmd_path = proc.get("command_path") or proc.get("name", "process")
            # Synthesize deterministic start time if not provided to guarantee idempotent URNs
            start_epoch = int(proc.get("start_time_epoch_ms") or (1700000000000 - (pid * 1000)))

            proc_urn = StableEntityIdGenerator.generate_process_urn(
                self.device_id, pid, start_epoch, cmd_path
            ).urn
            pid_to_urn[pid] = proc_urn

            # Determine ownership
            is_system_core = proc.get("is_system_core", False)
            raw_own = proc.get("ownership")
            if raw_own == ComponentOwnership.SYSTEM_MANAGED.value or is_system_core or pid == 1:
                ownership = ComponentOwnership.SYSTEM_MANAGED
            elif raw_own == ComponentOwnership.VENDOR_MANAGED.value:
                ownership = ComponentOwnership.VENDOR_MANAGED
            else:
                ownership = ComponentOwnership.USER_MANAGED

            proc_entity = TwinEntity(
                entity_id=proc_urn,
                entity_type=TwinEntityType.PROCESS,
                ownership=ownership,
                attributes={
                    "pid": pid,
                    "ppid": ppid,
                    "name": proc.get("name", "unknown"),
                    "command_path": cmd_path,
                    "user": proc.get("user", "root" if ownership == ComponentOwnership.SYSTEM_MANAGED else "user"),
                    "cpu_percent": float(proc.get("cpu_percent", 0.0)),
                    "rss_bytes": int(proc.get("rss_bytes", 0)),
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:processes",
            )
            entities.append(proc_entity)
            proc_records.append({"pid": pid, "ppid": ppid, "urn": proc_urn, "cmd_path": cmd_path, "name": proc.get("name", "")})

        # Pass 2: Establish Relationships (SPAWNED_BY and OWNS)
        for p in proc_records:
            pid = p["pid"]
            ppid = p["ppid"]
            proc_urn = p["urn"]
            cmd_path = p["cmd_path"].lower()
            name = p["name"].lower()

            # A. Process Lineage: Child -> SPAWNED_BY -> Parent
            if ppid > 0 and ppid in pid_to_urn:
                parent_urn = pid_to_urn[ppid]
                rel_id = self._generate_relation_id(proc_urn, TwinRelationType.SPAWNED_BY, parent_urn)
                relationships.append(
                    TwinRelationship(
                        relation_id=rel_id,
                        source_id=proc_urn,
                        target_id=parent_urn,
                        relation_type=TwinRelationType.SPAWNED_BY,
                        properties={"child_pid": pid, "parent_pid": ppid},
                        observed_at=timestamp,
                        confidence=0.95,
                    )
                )

            # B. Application Ownership: App -> OWNS -> Process
            matched_app_urn: Optional[str] = None
            # Check exact executable path
            if cmd_path in app_lookup:
                matched_app_urn = app_lookup[cmd_path]
            # Check bundle path prefix (e.g., /Applications/Safari.app/Contents/MacOS/Safari)
            if not matched_app_urn:
                for lookup_key, app_urn in app_lookup.items():
                    if lookup_key.endswith(".app") and lookup_key in cmd_path:
                        matched_app_urn = app_urn
                        break
            # Check process name
            if not matched_app_urn and name in app_lookup:
                matched_app_urn = app_lookup[name]

            if matched_app_urn:
                rel_id = self._generate_relation_id(matched_app_urn, TwinRelationType.OWNS, proc_urn)
                relationships.append(
                    TwinRelationship(
                        relation_id=rel_id,
                        source_id=matched_app_urn,
                        target_id=proc_urn,
                        relation_type=TwinRelationType.OWNS,
                        properties={"pid": pid, "match_type": "app_bundle"},
                        observed_at=timestamp,
                        confidence=0.90,
                    )
                )
            else:
                # If unmapped system core process, associate with kernel / host
                owner_target = kernel_urn if pid == 1 or "launchd" in cmd_path or "kernel" in cmd_path else host_urn
                rel_id = self._generate_relation_id(owner_target, TwinRelationType.CONTAINS, proc_urn)
                relationships.append(
                    TwinRelationship(
                        relation_id=rel_id,
                        source_id=owner_target,
                        target_id=proc_urn,
                        relation_type=TwinRelationType.CONTAINS,
                        properties={"pid": pid, "unmapped_system_process": True},
                        observed_at=timestamp,
                        confidence=0.80,
                    )
                )

        return entities, relationships, pid_to_urn

    def _extract_services(
        self,
        services_data: Dict[str, Any],
        host_urn: str,
        pid_to_urn: Dict[int, str],
        timestamp: str,
        provenance: str,
    ) -> Tuple[List[TwinEntity], List[TwinRelationship]]:
        """Extract launchd background service entities and service -> process ownership edges."""
        entities: List[TwinEntity] = []
        relationships: List[TwinRelationship] = []

        services = services_data.get("services", []) if isinstance(services_data, dict) else []
        for svc in services:
            label = svc.get("label", "unknown_service")
            domain = svc.get("domain", "system_daemon")
            svc_urn = StableEntityIdGenerator.generate_service_urn(domain, label).urn

            raw_own = svc.get("ownership")
            if raw_own == ComponentOwnership.USER_MANAGED.value:
                ownership = ComponentOwnership.USER_MANAGED
            elif raw_own == ComponentOwnership.VENDOR_MANAGED.value:
                ownership = ComponentOwnership.VENDOR_MANAGED
            else:
                ownership = ComponentOwnership.SYSTEM_MANAGED

            pid = svc.get("pid")
            svc_entity = TwinEntity(
                entity_id=svc_urn,
                entity_type=TwinEntityType.CONFIGURATION_SETTING,
                ownership=ownership,
                attributes={
                    "category": "launchd_service",
                    "label": label,
                    "domain": domain,
                    "status": svc.get("status", "LOADED"),
                    "program": svc.get("program", ""),
                    "pid": pid,
                },
                created_at=timestamp,
                updated_at=timestamp,
                provenance_source=f"{provenance}:services",
            )
            entities.append(svc_entity)

            # Host -> CONTAINS -> Service
            rel_id = self._generate_relation_id(host_urn, TwinRelationType.CONTAINS, svc_urn)
            relationships.append(
                TwinRelationship(
                    relation_id=rel_id,
                    source_id=host_urn,
                    target_id=svc_urn,
                    relation_type=TwinRelationType.CONTAINS,
                    properties={"service_label": label},
                    observed_at=timestamp,
                    confidence=1.0,
                )
            )

            # Service -> OWNS -> Process (if PID is active and mapped)
            if pid and isinstance(pid, int) and pid in pid_to_urn:
                proc_urn = pid_to_urn[pid]
                rel_id = self._generate_relation_id(svc_urn, TwinRelationType.OWNS, proc_urn)
                relationships.append(
                    TwinRelationship(
                        relation_id=rel_id,
                        source_id=svc_urn,
                        target_id=proc_urn,
                        relation_type=TwinRelationType.OWNS,
                        properties={"pid": pid, "daemon_supervision": True},
                        observed_at=timestamp,
                        confidence=0.95,
                    )
                )

        return entities, relationships
