"""Orchestrator and health manager for macOS telemetry collectors with timeout and partial-data reporting."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
import logging
from pathlib import Path
import platform
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from system_mind.macos.collector_health_models import (
    CollectorHealthRecord,
    CollectorResult,
    CollectorStatus,
    CompanionHealthReport,
    PartialDataReason,
)

T = TypeVar("T")
logger = logging.getLogger(__name__)

DEFAULT_COLLECTOR_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3

CORE_COLLECTORS = [
    "identity",
    "cpu",
    "memory",
    "storage",
    "battery",
    "network",
    "gpu",
    "usb",
    "processes",
    "services",
    "apps",
    "signatures",
    "fsevents",
    "endpoint_security",
    "swift_bridge",
    "user_agent",
]


class CollectorHealthManager:
    """Manages telemetry collector health, enforces latency budgets, and aggregates partial data."""

    def __init__(
        self,
        default_timeout_seconds: float = DEFAULT_COLLECTOR_TIMEOUT_SECONDS,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
    ) -> None:
        self.default_timeout_seconds = default_timeout_seconds
        self.max_consecutive_failures = max_consecutive_failures
        self._consecutive_failures: Dict[str, int] = {c: 0 for c in CORE_COLLECTORS}
        self._last_success: Dict[str, Optional[str]] = {c: None for c in CORE_COLLECTORS}

    def reset_collector(self, collector_id: str) -> None:
        """Reset consecutive failure counter for a specific collector (unbreaking circuit breaker)."""
        self._consecutive_failures[collector_id] = 0

    def reset_all(self) -> None:
        """Reset consecutive failure counters across all collectors."""
        for c in self._consecutive_failures:
            self._consecutive_failures[c] = 0

    def get_consecutive_failures(self, collector_id: str) -> int:
        """Return the current consecutive failure count for a collector."""
        return self._consecutive_failures.get(collector_id, 0)

    def execute_collector(
        self,
        collector_id: str,
        collector_fn: Callable[[], T],
        timeout_seconds: Optional[float] = None,
        fallback_fn: Optional[Callable[[], Optional[T]]] = None,
    ) -> CollectorResult[T]:
        """Execute a collector function within an isolated timeout envelope and track health metrics."""
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        start_time = time.perf_counter()

        # Check circuit breaker
        current_failures = self._consecutive_failures.get(collector_id, 0)
        if current_failures >= self.max_consecutive_failures:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            health = CollectorHealthRecord(
                collector_id=collector_id,
                status=CollectorStatus.CIRCUIT_BROKEN,
                latency_ms=elapsed_ms,
                timeout_seconds=effective_timeout,
                consecutive_failures=current_failures,
                last_success_timestamp=self._last_success.get(collector_id),
                last_error="Circuit breaker tripped after multiple consecutive failures",
                partial_data=True,
                partial_reasons=[PartialDataReason.COMMAND_ERROR],
                unavailable_fields=[f"{collector_id}_circuit_broken"],
            )
            fallback_data = fallback_fn() if fallback_fn else None
            return CollectorResult(data=fallback_data, health=health)

        # Execute with timeout via ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(collector_fn)
                data = future.result(timeout=effective_timeout)

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            now_iso = datetime.now(timezone.utc).isoformat()
            self._consecutive_failures[collector_id] = 0
            self._last_success[collector_id] = now_iso

            # Inspect data for partial flags
            partial_reasons: List[PartialDataReason] = []
            unavailable_fields: List[str] = []

            if hasattr(data, "unavailable_telemetry") and getattr(data, "unavailable_telemetry"):
                raw_unavailable = getattr(data, "unavailable_telemetry")
                unavailable_fields.extend(str(item) for item in raw_unavailable)

                # Categorize partial reasons
                for item in unavailable_fields:
                    item_lower = item.lower()
                    if any(k in item_lower for k in ["battery", "hardware", "not_present", "no_device", "absent"]):
                        if PartialDataReason.HARDWARE_ABSENT not in partial_reasons:
                            partial_reasons.append(PartialDataReason.HARDWARE_ABSENT)
                    elif any(k in item_lower for k in ["permission", "entitlement", "tcc", "restricted", "denied"]):
                        if PartialDataReason.PERMISSION_DENIED not in partial_reasons:
                            partial_reasons.append(PartialDataReason.PERMISSION_DENIED)
                    elif any(k in item_lower for k in ["unsupported", "platform", "non_darwin"]):
                        if PartialDataReason.PLATFORM_UNSUPPORTED not in partial_reasons:
                            partial_reasons.append(PartialDataReason.PLATFORM_UNSUPPORTED)
                    else:
                        if PartialDataReason.COMMAND_ERROR not in partial_reasons:
                            partial_reasons.append(PartialDataReason.COMMAND_ERROR)

            # Check specific partial conditions
            if collector_id == "battery" and hasattr(data, "has_battery") and not getattr(data, "has_battery"):
                if PartialDataReason.HARDWARE_ABSENT not in partial_reasons:
                    partial_reasons.append(PartialDataReason.HARDWARE_ABSENT)

            status = CollectorStatus.DEGRADED if (partial_reasons or unavailable_fields) else CollectorStatus.HEALTHY
            partial_data = len(partial_reasons) > 0 or len(unavailable_fields) > 0

            health = CollectorHealthRecord(
                collector_id=collector_id,
                status=status,
                latency_ms=elapsed_ms,
                timeout_seconds=effective_timeout,
                consecutive_failures=0,
                last_success_timestamp=now_iso,
                last_error=None,
                partial_data=partial_data,
                partial_reasons=partial_reasons,
                unavailable_fields=unavailable_fields,
            )
            return CollectorResult(data=data, health=health)

        except FuturesTimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            self._consecutive_failures[collector_id] = self._consecutive_failures.get(collector_id, 0) + 1
            health = CollectorHealthRecord(
                collector_id=collector_id,
                status=CollectorStatus.TIMED_OUT,
                latency_ms=elapsed_ms,
                timeout_seconds=effective_timeout,
                consecutive_failures=self._consecutive_failures[collector_id],
                last_success_timestamp=self._last_success.get(collector_id),
                last_error=f"Collector exceeded timeout budget of {effective_timeout:.2f}s",
                partial_data=True,
                partial_reasons=[PartialDataReason.TIMEOUT],
                unavailable_fields=[f"{collector_id}_timeout"],
            )
            fallback_data = fallback_fn() if fallback_fn else None
            return CollectorResult(data=fallback_data, health=health)

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            self._consecutive_failures[collector_id] = self._consecutive_failures.get(collector_id, 0) + 1
            health = CollectorHealthRecord(
                collector_id=collector_id,
                status=CollectorStatus.FAILED,
                latency_ms=elapsed_ms,
                timeout_seconds=effective_timeout,
                consecutive_failures=self._consecutive_failures[collector_id],
                last_success_timestamp=self._last_success.get(collector_id),
                last_error=str(e),
                partial_data=True,
                partial_reasons=[PartialDataReason.COMMAND_ERROR],
                unavailable_fields=[f"{collector_id}_error"],
            )
            fallback_data = fallback_fn() if fallback_fn else None
            return CollectorResult(data=fallback_data, health=health)

    def collect_all_telemetry(
        self,
        use_mock: bool = False,
        profile: str = "healthy",
    ) -> CompanionHealthReport:
        """Run or aggregate telemetry collection across all 16 core macOS collectors."""
        now_iso = datetime.now(timezone.utc).isoformat()

        if use_mock:
            return self._generate_mock_report(profile=profile, timestamp=now_iso)

        if platform.system() != "Darwin":
            return self._generate_mock_report(profile="unsupported", timestamp=now_iso)

        # Lazy imports of underlying detectors
        from system_mind.macos.app_detector import MacOsAppDetector
        from system_mind.macos.battery_detector import MacOsBatteryDetector
        from system_mind.macos.cpu_detector import MacOsCpuDetector
        from system_mind.macos.detector import MacOsIdentityDetector
        from system_mind.macos.endpoint_security_detector import MacOsEndpointSecurityDetector
        from system_mind.macos.fsevents_detector import MacOsFsEventsDetector
        from system_mind.macos.gpu_detector import MacOsGpuDetector
        from system_mind.macos.memory_detector import MacOsMemoryDetector
        from system_mind.macos.network_detector import MacOsNetworkDetector
        from system_mind.macos.process_detector import MacOsProcessDetector
        from system_mind.macos.services_detector import MacOsServicesDetector
        from system_mind.macos.signature_detector import MacOsSignatureDetector
        from system_mind.macos.storage_detector import MacOsStorageDetector
        from system_mind.macos.swift_bridge import MacSwiftBridge
        from system_mind.macos.agent_service_detector import MacUserAgentServiceManager
        from system_mind.macos.usb_detector import MacOsUsbDetector

        collectors_map: Dict[str, Callable[[], Any]] = {
            "identity": lambda: MacOsIdentityDetector().detect(),
            "cpu": lambda: MacOsCpuDetector().detect(),
            "memory": lambda: MacOsMemoryDetector().detect(),
            "storage": lambda: MacOsStorageDetector().detect(),
            "battery": lambda: MacOsBatteryDetector().detect(),
            "network": lambda: MacOsNetworkDetector().detect(),
            "gpu": lambda: MacOsGpuDetector().detect(),
            "usb": lambda: MacOsUsbDetector().detect(),
            "processes": lambda: MacOsProcessDetector().detect(),
            "services": lambda: MacOsServicesDetector().detect(),
            "apps": lambda: MacOsAppDetector().detect(),
            "signatures": lambda: MacOsSignatureDetector().detect(),
            "fsevents": lambda: MacOsFsEventsDetector().detect(),
            "endpoint_security": lambda: MacOsEndpointSecurityDetector().detect(),
            "swift_bridge": lambda: MacSwiftBridge().collect(),
            "user_agent": lambda: MacUserAgentServiceManager().get_status(),
        }

        records: Dict[str, CollectorHealthRecord] = {}

        for c_id, c_fn in collectors_map.items():
            result = self.execute_collector(c_id, c_fn)
            records[c_id] = result.health

        healthy_cnt = sum(1 for r in records.values() if r.status == CollectorStatus.HEALTHY)
        degraded_cnt = sum(1 for r in records.values() if r.status == CollectorStatus.DEGRADED)
        failed_cnt = sum(1 for r in records.values() if r.status == CollectorStatus.FAILED)
        timed_out_cnt = sum(1 for r in records.values() if r.status == CollectorStatus.TIMED_OUT)
        unsupported_cnt = sum(1 for r in records.values() if r.status == CollectorStatus.UNSUPPORTED)
        partial_present = any(r.partial_data for r in records.values())

        if failed_cnt > len(records) // 2:
            overall = CollectorStatus.FAILED
        elif failed_cnt > 0 or timed_out_cnt > 0 or degraded_cnt > 0:
            overall = CollectorStatus.DEGRADED
        else:
            overall = CollectorStatus.HEALTHY

        return CompanionHealthReport(
            timestamp=now_iso,
            host_platform="Darwin",
            total_collectors=len(records),
            healthy_count=healthy_cnt,
            degraded_count=degraded_cnt,
            failed_count=failed_cnt,
            timed_out_count=timed_out_cnt,
            unsupported_count=unsupported_cnt,
            overall_status=overall,
            collectors=records,
            partial_data_present=partial_present,
            scan_proves_safe=False,  # Enforce non-negotiable charter invariant
            is_mock=False,
        )

    def _generate_mock_report(self, profile: str, timestamp: str) -> CompanionHealthReport:
        """Produce deterministic mock reports across standard testing profiles."""
        records: Dict[str, CollectorHealthRecord] = {}

        if profile == "degraded":
            for c in CORE_COLLECTORS:
                if c == "battery":
                    records[c] = CollectorHealthRecord(
                        collector_id=c,
                        status=CollectorStatus.DEGRADED,
                        latency_ms=12.4,
                        timeout_seconds=self.default_timeout_seconds,
                        consecutive_failures=0,
                        last_success_timestamp=timestamp,
                        last_error=None,
                        partial_data=True,
                        partial_reasons=[PartialDataReason.HARDWARE_ABSENT],
                        unavailable_fields=["no_battery_hardware_desktop"],
                    )
                elif c == "endpoint_security":
                    records[c] = CollectorHealthRecord(
                        collector_id=c,
                        status=CollectorStatus.DEGRADED,
                        latency_ms=8.1,
                        timeout_seconds=self.default_timeout_seconds,
                        consecutive_failures=0,
                        last_success_timestamp=timestamp,
                        last_error=None,
                        partial_data=True,
                        partial_reasons=[PartialDataReason.PERMISSION_DENIED],
                        unavailable_fields=["endpoint_security_unentitled_companion"],
                    )
                else:
                    records[c] = CollectorHealthRecord(
                        collector_id=c,
                        status=CollectorStatus.HEALTHY,
                        latency_ms=15.0,
                        timeout_seconds=self.default_timeout_seconds,
                        consecutive_failures=0,
                        last_success_timestamp=timestamp,
                        last_error=None,
                        partial_data=False,
                    )
            return CompanionHealthReport(
                timestamp=timestamp,
                host_platform="Darwin",
                total_collectors=len(CORE_COLLECTORS),
                healthy_count=len(CORE_COLLECTORS) - 2,
                degraded_count=2,
                failed_count=0,
                timed_out_count=0,
                unsupported_count=0,
                overall_status=CollectorStatus.DEGRADED,
                collectors=records,
                partial_data_present=True,
                scan_proves_safe=False,
                is_mock=True,
            )

        elif profile == "timeout":
            for c in CORE_COLLECTORS:
                if c in ("fsevents", "user_agent"):
                    records[c] = CollectorHealthRecord(
                        collector_id=c,
                        status=CollectorStatus.TIMED_OUT,
                        latency_ms=self.default_timeout_seconds * 1000.0,
                        timeout_seconds=self.default_timeout_seconds,
                        consecutive_failures=1,
                        last_success_timestamp=None,
                        last_error=f"Collector exceeded timeout budget of {self.default_timeout_seconds}s",
                        partial_data=True,
                        partial_reasons=[PartialDataReason.TIMEOUT],
                        unavailable_fields=[f"{c}_timeout"],
                    )
                else:
                    records[c] = CollectorHealthRecord(
                        collector_id=c,
                        status=CollectorStatus.HEALTHY,
                        latency_ms=10.0,
                        timeout_seconds=self.default_timeout_seconds,
                        consecutive_failures=0,
                        last_success_timestamp=timestamp,
                        last_error=None,
                        partial_data=False,
                    )
            return CompanionHealthReport(
                timestamp=timestamp,
                host_platform="Darwin",
                total_collectors=len(CORE_COLLECTORS),
                healthy_count=len(CORE_COLLECTORS) - 2,
                degraded_count=0,
                failed_count=0,
                timed_out_count=2,
                unsupported_count=0,
                overall_status=CollectorStatus.DEGRADED,
                collectors=records,
                partial_data_present=True,
                scan_proves_safe=False,
                is_mock=True,
            )

        elif profile == "unsupported":
            for c in CORE_COLLECTORS:
                records[c] = CollectorHealthRecord(
                    collector_id=c,
                    status=CollectorStatus.UNSUPPORTED,
                    latency_ms=0.5,
                    timeout_seconds=self.default_timeout_seconds,
                    consecutive_failures=0,
                    last_success_timestamp=None,
                    last_error="Non-Darwin operating system",
                    partial_data=True,
                    partial_reasons=[PartialDataReason.PLATFORM_UNSUPPORTED],
                    unavailable_fields=[f"{c}_darwin_unsupported"],
                )
            return CompanionHealthReport(
                timestamp=timestamp,
                host_platform="Linux",
                total_collectors=len(CORE_COLLECTORS),
                healthy_count=0,
                degraded_count=0,
                failed_count=0,
                timed_out_count=0,
                unsupported_count=len(CORE_COLLECTORS),
                overall_status=CollectorStatus.UNSUPPORTED,
                collectors=records,
                partial_data_present=True,
                scan_proves_safe=False,
                is_mock=True,
            )

        # Default "healthy" profile
        for c in CORE_COLLECTORS:
            records[c] = CollectorHealthRecord(
                collector_id=c,
                status=CollectorStatus.HEALTHY,
                latency_ms=12.5,
                timeout_seconds=self.default_timeout_seconds,
                consecutive_failures=0,
                last_success_timestamp=timestamp,
                last_error=None,
                partial_data=False,
            )
        return CompanionHealthReport(
            timestamp=timestamp,
            host_platform="Darwin",
            total_collectors=len(CORE_COLLECTORS),
            healthy_count=len(CORE_COLLECTORS),
            degraded_count=0,
            failed_count=0,
            timed_out_count=0,
            unsupported_count=0,
            overall_status=CollectorStatus.HEALTHY,
            collectors=records,
            partial_data_present=False,
            scan_proves_safe=False,
            is_mock=True,
        )
