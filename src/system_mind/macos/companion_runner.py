"""Authoritative companion agent runner orchestrating read-only macOS telemetry collection and milestone release."""

from __future__ import annotations

import hashlib
import os
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from system_mind.macos.collector_health_manager import CollectorHealthManager
from system_mind.macos.collector_stability import (
    BoundedEventBuffer,
    CollectorStabilityManager,
)
from system_mind.macos.collector_stability_models import (
    BufferCapacityMetrics,
    TelemetryEvent,
)
from system_mind.macos.companion_models import (
    CompanionCycleTelemetry,
    CompanionExecutionMode,
    CompanionOperationalStatus,
    CompanionRunConfig,
    MacOsCompanionReleaseReport,
)
from system_mind.macos.detector import MacOSIdentityDetector
from system_mind.macos.inventory_api import MacOsInventoryApi
from system_mind.macos.observation_engine import MacOsObservationEngine
from system_mind.macos.permission_inspector import MacOsPermissionInspector
from system_mind.macos.permission_models import PermissionState
from system_mind.macos.privacy_filter import MacPrivacyFilter
from system_mind.macos.privacy_models import PrivacyScrubbingLevel


class MacOsCompanionRunner:
    """Unified read-only companion agent orchestrator for macOS system assessment and monitoring."""

    def __init__(self, config: Optional[CompanionRunConfig] = None) -> None:
        self.config = config or CompanionRunConfig()
        self.inventory_api = MacOsInventoryApi()
        self.health_manager = self.inventory_api.health_manager
        self.observation_engine = self.inventory_api.observation_engine
        self.privacy_filter = MacPrivacyFilter(level=self.config.privacy_level)
        self.stability_manager = CollectorStabilityManager()
        self.event_buffer = self.stability_manager.get_or_create_buffer(subsystem="companion_agent")
        self.permission_inspector = MacOsPermissionInspector()

    @property
    def host_platform(self) -> str:
        """Determines host platform string gracefully."""
        if self.config.use_mock:
            return "macOS 14.4.1 (Darwin 23.4.0) [Apple Silicon Mock]"
        return f"macOS {platform.mac_ver()[0]} (Darwin {platform.release()}) [{platform.machine()}]"

    @property
    def is_apple_silicon(self) -> bool:
        """Determines if the runtime or mock profile targets Apple Silicon."""
        if self.config.use_mock:
            return True
        return platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")

    @property
    def is_least_privilege(self) -> bool:
        """Verifies that the agent is running in unprivileged user space."""
        if hasattr(os, "geteuid"):
            return os.geteuid() != 0
        return True

    def run_cycle(self, cycle_id: int = 1) -> CompanionCycleTelemetry:
        """Executes a single, bounded telemetry observation and aggregation cycle."""
        start_time = time.perf_counter()
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        unavailable: List[str] = []
        is_partial = False

        # 1. Check circuit breaker status
        is_circuit_broken = any(
            f >= self.health_manager.max_consecutive_failures
            for f in self.health_manager._consecutive_failures.values()
        )
        if is_circuit_broken:
            op_status = CompanionOperationalStatus.CIRCUIT_BROKEN
            is_partial = True
            unavailable.append("CIRCUIT_BREAKER_TRIPPED")
        else:
            op_status = CompanionOperationalStatus.HEALTHY_NOMINAL

        # 2. Collect Inventory Summary
        inventory_summary_dict: Optional[Dict[str, Any]] = None
        try:
            inv_summary = self.inventory_api.get_summary(
                use_mock=self.config.use_mock,
                profile=self.config.mock_profile,
            )
            inventory_summary_dict = inv_summary.to_dict()
            if inv_summary.overall_health in ("DEGRADED", "CIRCUIT_BROKEN"):
                is_partial = True
                if op_status != CompanionOperationalStatus.CIRCUIT_BROKEN:
                    op_status = CompanionOperationalStatus.DEGRADED_PARTIAL
        except Exception as e:
            is_partial = True
            unavailable.append(f"INVENTORY_ERROR:{type(e).__name__}")
            if op_status != CompanionOperationalStatus.CIRCUIT_BROKEN:
                op_status = CompanionOperationalStatus.DEGRADED_PARTIAL

        # 3. Collect Observation Batch with provenance and confidence
        observation_dict: Optional[Dict[str, Any]] = None
        try:
            obs_batch = self.observation_engine.collect_batch(
                use_mock=self.config.use_mock,
                profile=self.config.mock_profile,
            )
            observation_dict = obs_batch.to_dict()
            if any(len(env.unavailable_telemetry) > 0 for env in obs_batch.observations.values()):
                is_partial = True
                if op_status != CompanionOperationalStatus.CIRCUIT_BROKEN:
                    op_status = CompanionOperationalStatus.DEGRADED_PARTIAL
        except Exception as e:
            is_partial = True
            unavailable.append(f"OBSERVATION_ERROR:{type(e).__name__}")
            if op_status != CompanionOperationalStatus.CIRCUIT_BROKEN:
                op_status = CompanionOperationalStatus.DEGRADED_PARTIAL

        # 4. Enqueue event into stability manager to assess backpressure
        stability_dict: Optional[Dict[str, Any]] = None
        try:
            event = TelemetryEvent(
                event_id=f"evt-{cycle_id}-{int(time.time()*1000)}",
                subsystem="macos.companion",
                event_type="CYCLE_SAMPLE",
                target_key=f"host:{platform.node()}",
                payload={"cycle_id": cycle_id, "mock": self.config.use_mock},
                scan_proves_safe=False,
            )
            self.event_buffer.ingest(event)
            metrics = self.event_buffer.get_metrics()
            stability_dict = {
                "subsystem": self.event_buffer.subsystem,
                "current_depth": metrics.current_depth,
                "max_capacity": metrics.max_capacity,
                "pressure_level": metrics.pressure_level.value,
                "total_ingested": metrics.total_ingested,
                "total_dropped": metrics.total_dropped,
                "total_coalesced": metrics.total_coalesced,
            }
        except Exception as e:
            unavailable.append(f"STABILITY_ERROR:{type(e).__name__}")

        # 5. Inspect permissions & entitlements
        permission_dict: Optional[Dict[str, Any]] = None
        try:
            manifest = self.permission_inspector.inspect_permissions(mock=self.config.use_mock)
            permission_dict = {
                "companion_mode": manifest.companion_mode,
                "host_platform": manifest.host_platform,
                "timestamp": manifest.timestamp,
                "total_evaluated": len(manifest.permissions),
                "total_granted": sum(1 for st in manifest.active_states.values() if st == PermissionState.GRANTED),
                "total_denied": sum(1 for st in manifest.active_states.values() if st == PermissionState.DENIED),
                "active_states": {k: v.value for k, v in manifest.active_states.items()},
                "warnings": manifest.warnings,
                "unavailable_telemetry": manifest.unavailable_telemetry,
                "scan_proves_safe": False,
            }
            if any(st == PermissionState.DENIED for st in manifest.active_states.values()):
                is_partial = True
                if op_status != CompanionOperationalStatus.CIRCUIT_BROKEN:
                    op_status = CompanionOperationalStatus.DEGRADED_PARTIAL
        except Exception as e:
            unavailable.append(f"PERMISSIONS_ERROR:{type(e).__name__}")

        # 6. Privacy filter audit
        privacy_audit_dict: Optional[Dict[str, Any]] = None
        try:
            test_envelope = {
                "user": os.environ.get("USER", "system_operator"),
                "home": str(os.path.expanduser("~")),
                "status": "active",
            }
            sanitized_envelope, audit_record = self.privacy_filter.sanitize_payload(test_envelope)
            privacy_audit_dict = {
                "sanitized_usernames_count": audit_record.sanitized_usernames_count,
                "sanitized_paths_count": audit_record.sanitized_paths_count,
                "sanitized_metadata_count": audit_record.sanitized_metadata_count,
                "redacted_secrets_count": audit_record.redacted_secrets_count,
                "total_redactions": audit_record.total_redactions,
                "level": audit_record.level.value,
                "rules_applied": audit_record.rules_applied,
                "scan_proves_safe": False,
            }
        except Exception as e:
            unavailable.append(f"PRIVACY_ERROR:{type(e).__name__}")

        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return CompanionCycleTelemetry(
            cycle_id=cycle_id,
            timestamp_utc=timestamp_utc,
            operational_status=op_status,
            duration_ms=duration_ms,
            partial_data=is_partial,
            unavailable_telemetry=sorted(list(set(unavailable))),
            inventory_summary=inventory_summary_dict,
            observation_batch_summary=observation_dict,
            stability_metrics=stability_dict,
            permission_manifest_summary=permission_dict,
            privacy_audit=privacy_audit_dict,
            scan_proves_safe=False,
        )

    def run_snapshot(self) -> MacOsCompanionReleaseReport:
        """Executes a single-shot assessment and compiles the milestone release report."""
        cycle = self.run_cycle(cycle_id=1)
        report_id = f"m4-release-{hashlib.sha256(cycle.timestamp_utc.encode()).hexdigest()[:12]}"

        return MacOsCompanionReleaseReport(
            report_id=report_id,
            host_platform=self.host_platform,
            apple_silicon_native=self.is_apple_silicon,
            cycles_completed=1,
            latest_cycle=cycle,
            all_cycles=[cycle],
            least_privilege_enforced=self.is_least_privilege,
            scan_proves_safe=False,
        )

    def run_daemon(self, stop_event: Optional[threading.Event] = None) -> MacOsCompanionReleaseReport:
        """Runs the continuous observational sampling loop with bounded intervals."""
        all_cycles: List[CompanionCycleTelemetry] = []
        cycle_count = 0
        max_cycles = self.config.max_cycles or 1

        while (stop_event is None or not stop_event.is_set()) and cycle_count < max_cycles:
            cycle_count += 1
            cycle = self.run_cycle(cycle_id=cycle_count)
            all_cycles.append(cycle)

            if cycle_count < max_cycles:
                if stop_event:
                    if stop_event.wait(timeout=self.config.interval_seconds):
                        break
                else:
                    time.sleep(self.config.interval_seconds)

        latest = all_cycles[-1] if all_cycles else None
        ts = latest.timestamp_utc if latest else datetime.now(timezone.utc).isoformat()
        report_id = f"m4-daemon-{hashlib.sha256(ts.encode()).hexdigest()[:12]}"

        return MacOsCompanionReleaseReport(
            report_id=report_id,
            host_platform=self.host_platform,
            apple_silicon_native=self.is_apple_silicon,
            cycles_completed=len(all_cycles),
            latest_cycle=latest,
            all_cycles=all_cycles,
            least_privilege_enforced=self.is_least_privilege,
            scan_proves_safe=False,
        )
