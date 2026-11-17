"""Read-only macOS Inventory API service orchestrating telemetry collection, privacy filtering, and health reporting."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from enum import Enum
import hashlib
import time
from typing import Any, Dict, List, Optional, Set

from system_mind.api.models import (
    ApiErrorDetail,
    ApiRequest,
    ApiResponse,
    ApiStatus,
    ErrorCode,
    ErrorCodeCategory,
)
from system_mind.macos.agent_service_detector import MacUserAgentServiceManager
from system_mind.macos.app_detector import MacAppDetector
from system_mind.macos.battery_detector import MacBatteryDetector
from system_mind.macos.collector_health_manager import CollectorHealthManager
from system_mind.macos.cpu_detector import MacCpuHardwareDetector
from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.endpoint_security_detector import MacEndpointSecurityDetector
from system_mind.macos.fsevents_detector import MacFsEventsDetector
from system_mind.macos.gpu_detector import MacGpuDetector
from system_mind.macos.inventory_models import (
    InventorySection,
    MacOsInventoryRequest,
    MacOsInventoryResponse,
    MacOsInventorySummary,
)
from system_mind.macos.memory_detector import MacMemoryDetector
from system_mind.macos.network_detector import MacNetworkDetector
from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.macos.privacy_filter import MacPrivacyFilter
from system_mind.macos.privacy_models import PrivacyScrubbingLevel
from system_mind.macos.process_detector import MacProcessDetector
from system_mind.macos.services_detector import MacServicesDetector
from system_mind.macos.signature_detector import MacAppSignatureDetector
from system_mind.macos.storage_detector import MacStorageDetector
from system_mind.macos.swift_bridge import MacSwiftBridge
from system_mind.macos.usb_detector import MacUsbDetector
from system_mind.platform.adapter import MockPlatformAdapter
from system_mind.platform.matrix import PlatformTargetId


def _serialize(obj: Any) -> Any:
    """Recursively convert dataclasses, models, enums, lists, and dicts to plain serializable Python structures."""
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        try:
            return obj.to_dict()
        except Exception:
            pass
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        try:
            return dataclasses.asdict(obj)
        except Exception:
            pass
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, Enum):
        return obj.value
    return obj


class MacOsInventoryApi:
    """Unified read-only API service aggregating macOS hardware, software, security, and process telemetry."""

    API_VERSION = "1.0.0"

    def __init__(self) -> None:
        self.health_manager = CollectorHealthManager()
        self.observation_engine = MacOsObservationEngine()

    def _collect_raw_section(self, section: InventorySection, use_mock: bool, profile: str) -> Dict[str, Any]:
        """Collect telemetry data for an individual inventory section."""
        adapter = MockPlatformAdapter(PlatformTargetId.MACOS_APPLE_SILICON) if use_mock else None

        if section == InventorySection.IDENTITY:
            report = MacOSIdentityDetector.detect(mock_adapter=adapter)
            return _serialize(report)

        elif section == InventorySection.HARDWARE:
            cpu_rep = MacCpuHardwareDetector.detect(mock_adapter=adapter)
            mem_rep = MacMemoryDetector.detect(mock_adapter=adapter)
            gpu_rep = MacGpuDetector().detect(use_mock=use_mock, mock_adapter=adapter)
            usb_rep = MacUsbDetector().detect(use_mock=use_mock, mock_adapter=adapter)
            bat_rep = MacBatteryDetector().detect(use_mock=use_mock, mock_adapter=adapter)

            return {
                "cpu": _serialize(cpu_rep),
                "memory": _serialize(mem_rep),
                "gpu": _serialize(gpu_rep),
                "usb": _serialize(usb_rep),
                "battery": _serialize(bat_rep),
            }

        elif section == InventorySection.STORAGE:
            storage_rep = MacStorageDetector.detect(mock_adapter=adapter)
            return _serialize(storage_rep)

        elif section == InventorySection.NETWORK:
            net_rep = MacNetworkDetector().detect(use_mock=use_mock, mock_adapter=adapter)
            return _serialize(net_rep)

        elif section == InventorySection.APPLICATIONS:
            app_rep = MacAppDetector().detect(mock=use_mock, mock_adapter=adapter)
            return _serialize(app_rep)

        elif section == InventorySection.SECURITY:
            sig_rep = MacAppSignatureDetector().detect(mock=use_mock)
            es_rep = MacEndpointSecurityDetector().detect(use_mock=use_mock)
            return {
                "signatures": _serialize(sig_rep),
                "endpoint_security": _serialize(es_rep),
            }

        elif section == InventorySection.PROCESSES:
            proc_rep = MacProcessDetector().detect(use_mock=use_mock, mock_adapter=adapter)
            return _serialize(proc_rep)

        elif section == InventorySection.SERVICES:
            srv_rep = MacServicesDetector().detect(mock=use_mock, mock_adapter=adapter)
            swift_rep = MacSwiftBridge().collect(use_mock=use_mock)
            ua_rep = MacUserAgentServiceManager().inspect_service(use_mock=use_mock)
            return {
                "launchd_and_login_items": _serialize(srv_rep),
                "swift_companion": _serialize(swift_rep),
                "user_agent": _serialize(ua_rep),
            }

        return {}

    def get_summary(self, use_mock: bool = False, profile: str = "high_fidelity") -> MacOsInventorySummary:
        """Compute high-level summary of system state and capacity."""
        adapter = MockPlatformAdapter(PlatformTargetId.MACOS_APPLE_SILICON) if use_mock else None
        ident = MacOSIdentityDetector.detect(mock_adapter=adapter)
        cpu = MacCpuHardwareDetector.detect(mock_adapter=adapter)
        mem = MacMemoryDetector.detect(mock_adapter=adapter)
        storage = MacStorageDetector.detect(mock_adapter=adapter)
        proc = MacProcessDetector().detect(use_mock=use_mock, mock_adapter=adapter)
        apps = MacAppDetector().detect(mock=use_mock, mock_adapter=adapter)

        obs_batch = self.observation_engine.collect_batch(use_mock=use_mock, profile=profile)
        health_rep = self.health_manager.collect_all_telemetry(use_mock=use_mock, profile=profile)

        # Calculate total and free storage
        total_storage = sum(vol.total_capacity_bytes for vol in storage.volumes)
        free_storage = sum(vol.available_bytes for vol in storage.volumes)

        return MacOsInventorySummary(
            os_version=ident.version_info.product_version,
            os_build=ident.version_info.build_version,
            host_name=ident.identity.hostname,
            architecture=ident.architecture.machine,
            cpu_model=cpu.cpu_info.cpu_brand_string,
            physical_cores=cpu.cpu_info.total_physical_cores,
            logical_cores=cpu.cpu_info.total_logical_cores,
            total_memory_bytes=mem.memory_info.total_physical_bytes,
            memory_pressure_pct=mem.memory_info.pressure_percentage,
            total_storage_bytes=total_storage,
            free_storage_bytes=free_storage,
            running_process_count=proc.total_process_count,
            installed_app_count=apps.total_applications_count,
            mean_confidence=obs_batch.mean_confidence,
            overall_health=health_rep.overall_status.value,
        )

    def get_inventory(self, request: Optional[MacOsInventoryRequest] = None) -> MacOsInventoryResponse:
        """Execute aggregated read-only macOS inventory collection with privacy scrubbing and confidence metrics."""
        req = request or MacOsInventoryRequest()

        target_sections: List[InventorySection] = []
        if InventorySection.ALL in req.sections:
            target_sections = [
                InventorySection.IDENTITY,
                InventorySection.HARDWARE,
                InventorySection.STORAGE,
                InventorySection.NETWORK,
                InventorySection.APPLICATIONS,
                InventorySection.SECURITY,
                InventorySection.PROCESSES,
                InventorySection.SERVICES,
            ]
        else:
            target_sections = [s for s in req.sections if s != InventorySection.ALL]

        raw_sections: Dict[str, Any] = {}
        for s in target_sections:
            raw_sections[s.value.lower()] = self._collect_raw_section(s, req.use_mock, req.mock_profile)

        summary = self.get_summary(use_mock=req.use_mock, profile=req.mock_profile)

        # Observations and health reports
        obs_dict: Optional[Dict[str, Any]] = None
        if req.include_observations:
            obs_batch = self.observation_engine.collect_batch(use_mock=req.use_mock, profile=req.mock_profile)
            obs_dict = obs_batch.to_dict()

        health_rep = self.health_manager.collect_all_telemetry(use_mock=req.use_mock, profile=req.mock_profile)
        health_dict = health_rep.to_dict()

        # Privacy Filter Sanitization Pass
        privacy_filter = MacPrivacyFilter(level=req.privacy_level)
        clean_sections, audit = privacy_filter.sanitize_payload(raw_sections)

        clean_obs: Optional[Dict[str, Any]] = None
        if obs_dict:
            clean_obs, _ = privacy_filter.sanitize_payload(obs_dict)

        clean_health, _ = privacy_filter.sanitize_payload(health_dict)

        inv_id = f"inventory-{hashlib.sha256(f'{datetime.now(timezone.utc).isoformat()}-{req.use_mock}'.encode()).hexdigest()[:12]}"
        partial_data = health_rep.partial_data_present

        return MacOsInventoryResponse(
            inventory_id=inv_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            sections=clean_sections,
            observations=clean_obs,
            health=clean_health,
            privacy_audit=audit.to_dict() if req.include_audit else None,
            partial_data=partial_data,
            scan_proves_safe=False,  # Enforce non-negotiable charter invariant
            is_mock=req.use_mock,
        )

    def get_section(
        self,
        section: InventorySection,
        privacy_level: PrivacyScrubbingLevel = PrivacyScrubbingLevel.BALANCED,
        use_mock: bool = False,
    ) -> Dict[str, Any]:
        """Retrieve and sanitize a single isolated inventory section."""
        raw = self._collect_raw_section(section, use_mock=use_mock, profile="high_fidelity")
        pf = MacPrivacyFilter(level=privacy_level)
        clean, _ = pf.sanitize_payload(raw)
        return clean

    def handle_api_request(self, api_req: ApiRequest) -> ApiResponse:
        """Handle standard wire API request adherence to RFC 7807 conventions."""
        start_time = time.time()

        # Reject any mutating request by charter invariant
        if api_req.is_mutating:
            err = ApiErrorDetail(
                code=ErrorCode.E2001_CHARTER_INVARIANT_BREACH,
                category=ErrorCodeCategory.GOVERNANCE_CHARTER_INVARIANT,
                message="Mutating operations are strictly prohibited on the read-only macOS inventory API.",
                target=api_req.method_urn,
                remediation_hint="Use read-only query envelopes (is_mutating=False).",
                is_retryable=False,
            )
            return ApiResponse(
                request_id=api_req.request_id,
                api_version=self.API_VERSION,
                status=ApiStatus.POLICY_REJECTED,
                data=None,
                error=err,
                duration_ms=(time.time() - start_time) * 1000.0,
            )

        if api_req.method_urn == "urn:systemmind:macos:inventory:summary":
            use_mock = bool(api_req.params.get("use_mock", False))
            summary = self.get_summary(use_mock=use_mock)
            return ApiResponse(
                request_id=api_req.request_id,
                api_version=self.API_VERSION,
                status=ApiStatus.SUCCESS,
                data=summary.to_dict(),
                duration_ms=(time.time() - start_time) * 1000.0,
            )

        elif api_req.method_urn in ("urn:systemmind:macos:inventory:get", "urn:systemmind:macos:inventory:section"):
            use_mock = bool(api_req.params.get("use_mock", False))
            level_str = api_req.params.get("privacy_level", "BALANCED")
            try:
                level = PrivacyScrubbingLevel(level_str)
            except ValueError:
                level = PrivacyScrubbingLevel.BALANCED

            sec_strings = api_req.params.get("sections", ["ALL"])
            sections: List[InventorySection] = []
            for s in sec_strings:
                try:
                    sections.append(InventorySection(s))
                except ValueError:
                    pass
            if not sections:
                sections = [InventorySection.ALL]

            req = MacOsInventoryRequest(
                sections=sections,
                privacy_level=level,
                use_mock=use_mock,
            )
            inv_res = self.get_inventory(req)

            return ApiResponse(
                request_id=api_req.request_id,
                api_version=self.API_VERSION,
                status=ApiStatus.SUCCESS,
                data=inv_res.to_dict(),
                duration_ms=(time.time() - start_time) * 1000.0,
            )

        else:
            err = ApiErrorDetail(
                code=ErrorCode.E4001_CAPABILITY_NOT_FOUND,
                category=ErrorCodeCategory.BROKER_EXECUTION,
                message=f"Unknown method URN: {api_req.method_urn}",
                target=api_req.method_urn,
                remediation_hint="Supported methods: urn:systemmind:macos:inventory:get, urn:systemmind:macos:inventory:summary",
                is_retryable=False,
            )
            return ApiResponse(
                request_id=api_req.request_id,
                api_version=self.API_VERSION,
                status=ApiStatus.CLIENT_ERROR,
                data=None,
                error=err,
                duration_ms=(time.time() - start_time) * 1000.0,
            )
