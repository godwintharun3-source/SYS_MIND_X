"""Telemetry observation enrichment engine applying source timestamps and deterministic confidence scoring."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import platform
import time
from typing import Any, Dict, List, Optional
import uuid

from system_mind.macos.collector_health_manager import (
    CORE_COLLECTORS,
    CollectorHealthManager,
)
from system_mind.macos.observation_models import (
    CompanionObservationBatch,
    ConfidenceTier,
    ObservationConfidence,
    ObservedTelemetryEnvelope,
    SourceTimestamp,
    compute_telemetry_digest,
)

logger = logging.getLogger(__name__)

BASE_COLLECTOR_CONFIDENCE: Dict[str, tuple[float, str]] = {
    "identity": (0.98, "Direct Darwin sysctl / product version query"),
    "cpu": (0.98, "Direct Darwin sysctl / mach processor info syscall"),
    "memory": (0.95, "Darwin vm_stat / sysctl virtual memory pages"),
    "storage": (0.92, "APFS diskutil / statvfs filesystem metadata"),
    "battery": (0.95, "IOKit AppleSmartBattery hardware registry"),
    "network": (0.92, "Darwin getifaddrs / routing table query"),
    "gpu": (0.90, "IOKit registry / Metal device descriptor"),
    "usb": (0.90, "IOKit IOUSBDevice descriptor registry"),
    "processes": (0.85, "Darwin sysctl / proc_pidinfo process table"),
    "services": (0.88, "Darwin launchctl print user domain query"),
    "apps": (0.85, "NSWorkspace / LaunchServices / Info.plist bundle parser"),
    "signatures": (0.88, "Security framework / codesign CDHash verification"),
    "fsevents": (0.90, "CoreServices FSEvents change notification stream"),
    "endpoint_security": (0.85, "EndpointSecurity framework client audit"),
    "swift_bridge": (0.88, "Native Swift companion bridge IPC"),
    "user_agent": (0.88, "LaunchAgent gui/$UID status inspection"),
}


class MacOsObservationEngine:
    """Enriches raw macOS telemetry with source timestamps, clock metadata, and confidence scores."""

    def __init__(self, clock_source: Optional[str] = None) -> None:
        self.default_clock_source = clock_source or (
            "mach_continuous_time" if platform.system() == "Darwin" else "system_clock_utc"
        )
        self.health_manager = CollectorHealthManager()

    def capture_source_timestamp(self, is_mock: bool = False) -> SourceTimestamp:
        """Capture high-resolution source timestamp and monotonic clock ticks."""
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        now_epoch_ms = int(now_dt.timestamp() * 1000)

        monotonic_ns: Optional[int] = None
        if hasattr(time, "clock_gettime_ns") and hasattr(time, "CLOCK_MONOTONIC"):
            try:
                monotonic_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
            except OSError:
                monotonic_ns = None

        clock_source = "mock_clock" if is_mock else self.default_clock_source

        return SourceTimestamp(
            utc_iso=now_iso,
            epoch_ms=now_epoch_ms,
            monotonic_ns=monotonic_ns,
            clock_source=clock_source,
        )

    def calculate_confidence(
        self,
        collector_id: str,
        payload: Any,
        is_mock: bool = False,
    ) -> ObservationConfidence:
        """Calculate continuous confidence score in [0.0, 1.0] and assign confidence tier."""
        base_score, rationale = BASE_COLLECTOR_CONFIDENCE.get(
            collector_id,
            (0.80, "Generic unclassified telemetry collector"),
        )
        penalty_factors: List[str] = []
        score = base_score

        # Deduct penalties for mock execution
        if is_mock:
            penalty_factors.append("synthetic_mock_fixture")
            score -= 0.60

        # Inspect payload for missing or unavailable fields
        unavailable_fields: List[str] = []
        if hasattr(payload, "unavailable_telemetry") and getattr(payload, "unavailable_telemetry"):
            unavailable_fields = [str(item) for item in getattr(payload, "unavailable_telemetry")]
        elif isinstance(payload, dict) and "unavailable_telemetry" in payload:
            unavailable_fields = [str(item) for item in payload["unavailable_telemetry"]]

        for item in unavailable_fields:
            item_lower = item.lower()
            if any(k in item_lower for k in ["battery", "hardware", "not_present"]):
                if "hardware_absent_desktop" not in penalty_factors:
                    penalty_factors.append("hardware_absent_desktop")
                    score -= 0.20
            elif any(k in item_lower for k in ["permission", "entitlement", "tcc", "not_entitled"]):
                if "missing_permission_or_entitlement" not in penalty_factors:
                    penalty_factors.append("missing_permission_or_entitlement")
                    score -= 0.35
            elif any(k in item_lower for k in ["unsupported", "non_darwin", "platform"]):
                if "platform_unsupported" not in penalty_factors:
                    penalty_factors.append("platform_unsupported")
                    score -= 0.40
            else:
                factor_name = f"degraded_{item}"
                if factor_name not in penalty_factors:
                    penalty_factors.append(factor_name)
                    score -= 0.15

        # Battery-specific hardware absent check
        if collector_id == "battery" and hasattr(payload, "has_battery") and not getattr(payload, "has_battery"):
            if "hardware_absent_desktop" not in penalty_factors:
                penalty_factors.append("hardware_absent_desktop")
                score -= 0.20

        # Clamp score between 0.05 and 1.00 and round to 3 decimal places
        final_score = round(max(0.05, min(1.00, score)), 3)

        # Assign tier - Mock results and unsupported data must NEVER be KERNEL_AUTHORITATIVE
        if is_mock or final_score < 0.40:
            tier = ConfidenceTier.ESTIMATED_MOCK
        elif "platform_unsupported" in penalty_factors or any("unsupported" in str(u).lower() for u in unavailable_fields):
            tier = ConfidenceTier.ESTIMATED_MOCK
        elif final_score < 0.60:
            tier = ConfidenceTier.DEGRADED_PARTIAL
        elif final_score < 0.80:
            tier = ConfidenceTier.HEURISTIC_PARSED
        elif final_score < 0.95:
            tier = ConfidenceTier.SUBSYSTEM_VERIFIED
        else:
            tier = ConfidenceTier.KERNEL_AUTHORITATIVE

        if penalty_factors:
            rationale = f"{rationale} (Penalties: {', '.join(penalty_factors)})"

        return ObservationConfidence(
            score=final_score,
            tier=tier,
            rationale=rationale,
            penalty_factors=penalty_factors,
        )

    def enrich_observation(
        self,
        collector_id: str,
        payload: Any,
        latency_ms: float = 10.0,
        is_mock: bool = False,
    ) -> ObservedTelemetryEnvelope[Any]:
        """Wrap raw collector telemetry with source timestamp, confidence, and payload digest."""
        source_ts = self.capture_source_timestamp(is_mock=is_mock)
        confidence = self.calculate_confidence(collector_id, payload, is_mock=is_mock)
        digest = compute_telemetry_digest(payload)

        unavailable_fields: List[str] = []
        if hasattr(payload, "unavailable_telemetry") and getattr(payload, "unavailable_telemetry"):
            unavailable_fields = [str(item) for item in getattr(payload, "unavailable_telemetry")]
        elif isinstance(payload, dict) and "unavailable_telemetry" in payload:
            unavailable_fields = [str(item) for item in payload["unavailable_telemetry"]]

        # Distinguish actual, mock, degraded, and unsupported observations
        if is_mock:
            if any("unsupported" in f.lower() for f in unavailable_fields) or "platform_unsupported" in confidence.penalty_factors:
                obs_status = "UNSUPPORTED"
            elif unavailable_fields or any(p in confidence.penalty_factors for p in ["hardware_absent_desktop", "missing_permission_or_entitlement"]):
                obs_status = "DEGRADED"
            else:
                obs_status = "MOCK"
        else:
            if any("unsupported" in f.lower() for f in unavailable_fields) or "platform_unsupported" in confidence.penalty_factors:
                obs_status = "UNSUPPORTED"
            elif unavailable_fields or any(p in confidence.penalty_factors for p in ["hardware_absent_desktop", "missing_permission_or_entitlement"]):
                obs_status = "DEGRADED"
            else:
                obs_status = "ACTUAL"

        obs_id = f"obs-{collector_id}-{uuid.uuid4().hex[:12]}"

        return ObservedTelemetryEnvelope(
            observation_id=obs_id,
            collector_id=collector_id,
            source_timestamp=source_ts,
            observed_at_utc=source_ts.utc_iso,
            latency_ms=latency_ms,
            confidence=confidence,
            payload_sha256=digest,
            payload=payload,
            unavailable_telemetry=unavailable_fields,
            scan_proves_safe=False,  # Enforce non-negotiable charter invariant
            is_mock=is_mock,
            observation_status=obs_status,
        )

    def collect_batch(
        self,
        use_mock: bool = False,
        profile: str = "high_fidelity",
    ) -> CompanionObservationBatch:
        """Collect or simulate enriched observation envelopes across all 16 core collectors."""
        batch_id = f"batch-{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        if use_mock:
            return self._generate_mock_batch(batch_id=batch_id, profile=profile, timestamp=now_iso)

        if platform.system() != "Darwin":
            return self._generate_mock_batch(batch_id=batch_id, profile="unsupported", timestamp=now_iso)

        # Lazy imports of native detectors
        from system_mind.macos.app_detector import MacAppDetector
        from system_mind.macos.battery_detector import MacBatteryDetector
        from system_mind.macos.cpu_detector import MacCpuHardwareDetector
        from system_mind.macos.detector import MacOSIdentityDetector
        from system_mind.macos.endpoint_security_detector import MacEndpointSecurityDetector
        from system_mind.macos.fsevents_detector import MacFsEventsDetector
        from system_mind.macos.gpu_detector import MacGpuDetector
        from system_mind.macos.memory_detector import MacMemoryDetector
        from system_mind.macos.network_detector import MacNetworkDetector
        from system_mind.macos.process_detector import MacProcessDetector
        from system_mind.macos.services_detector import MacServicesDetector
        from system_mind.macos.signature_detector import MacAppSignatureDetector
        from system_mind.macos.storage_detector import MacStorageDetector
        from system_mind.macos.swift_bridge import MacSwiftBridge
        from system_mind.macos.agent_service_detector import MacUserAgentServiceManager
        from system_mind.macos.usb_detector import MacUsbDetector

        collectors_map = {
            "identity": lambda: MacOSIdentityDetector.detect(),
            "cpu": lambda: MacCpuHardwareDetector.detect(),
            "memory": lambda: MacMemoryDetector.detect(),
            "storage": lambda: MacStorageDetector.detect(),
            "battery": lambda: MacBatteryDetector().detect(),
            "network": lambda: MacNetworkDetector().detect(),
            "gpu": lambda: MacGpuDetector().detect(),
            "usb": lambda: MacUsbDetector().detect(),
            "processes": lambda: MacProcessDetector().detect(),
            "services": lambda: MacServicesDetector().detect(),
            "apps": lambda: MacAppDetector().detect(),
            "signatures": lambda: MacAppSignatureDetector().detect(),
            "fsevents": lambda: MacFsEventsDetector().detect(),
            "endpoint_security": lambda: MacEndpointSecurityDetector().detect(),
            "swift_bridge": lambda: MacSwiftBridge().collect(),
            "user_agent": lambda: MacUserAgentServiceManager().inspect_service(),
        }

        observations: Dict[str, ObservedTelemetryEnvelope[Any]] = {}

        for cid, cfn in collectors_map.items():
            start_t = time.perf_counter()
            result = self.health_manager.execute_collector(cid, cfn)
            latency = (time.perf_counter() - start_t) * 1000.0

            env = self.enrich_observation(
                collector_id=cid,
                payload=result.data,
                latency_ms=latency,
                is_mock=False,
            )
            observations[cid] = env

        scores = [env.confidence.score for env in observations.values()]
        mean_conf = sum(scores) / len(scores) if scores else 1.0

        lowest_cid = min(observations.keys(), key=lambda k: observations[k].confidence.score)

        return CompanionObservationBatch(
            batch_id=batch_id,
            timestamp_utc=now_iso,
            total_observations=len(observations),
            observations=observations,
            mean_confidence=mean_conf,
            lowest_confidence_collector=lowest_cid,
            scan_proves_safe=False,
            is_mock=False,
        )

    def _generate_mock_batch(
        self,
        batch_id: str,
        profile: str,
        timestamp: str,
    ) -> CompanionObservationBatch:
        """Produce deterministic mock observation batch across test profiles."""
        observations: Dict[str, ObservedTelemetryEnvelope[Any]] = {}

        for cid in CORE_COLLECTORS:
            base_score, rationale = BASE_COLLECTOR_CONFIDENCE.get(cid, (0.85, "Mock observation"))
            penalty_factors: List[str] = []

            if profile == "unsupported":
                payload = {"status": "UNSUPPORTED", "platform": "Linux", "unavailable_telemetry": [f"{cid}_darwin_unsupported"]}
                env = self.enrich_observation(cid, payload, latency_ms=0.5, is_mock=True)
            elif profile == "mock_simulation":
                payload = {"collector": cid, "status": "MOCK_ACTIVE", "metric": 42}
                env = self.enrich_observation(cid, payload, latency_ms=5.0, is_mock=True)
            elif profile == "degraded":
                if cid == "battery":
                    payload = {"has_battery": False, "unavailable_telemetry": ["no_battery_hardware_desktop"]}
                elif cid == "endpoint_security":
                    payload = {"entitled": False, "unavailable_telemetry": ["endpoint_security_unentitled_companion"]}
                else:
                    payload = {"collector": cid, "status": "NOMINAL", "sample": 100}
                # Simulate mock execution with partial degradations (strictly is_mock=True)
                env = self.enrich_observation(cid, payload, latency_ms=12.0, is_mock=True)
            else:
                # default "high_fidelity" synthetic mock profile (strictly is_mock=True)
                payload = {"collector": cid, "status": "NOMINAL", "sample": 100}
                env = self.enrich_observation(cid, payload, latency_ms=10.0, is_mock=True)

            observations[cid] = env

        scores = [env.confidence.score for env in observations.values()]
        mean_conf = sum(scores) / len(scores) if scores else 1.0
        lowest_cid = min(observations.keys(), key=lambda k: observations[k].confidence.score)

        return CompanionObservationBatch(
            batch_id=batch_id,
            timestamp_utc=timestamp,
            total_observations=len(observations),
            observations=observations,
            mean_confidence=mean_conf,
            lowest_confidence_collector=lowest_cid,
            scan_proves_safe=False,
            is_mock=True,
        )
