"""Telemetry collector stability engine, bounded event buffer, coalescer, and backpressure manager."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
import platform
import resource
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.collector_stability_models import (
    BufferCapacityMetrics,
    CollectorOperationalStatus,
    CollectorStabilityReport,
    EventDropPolicy,
    StabilityPressureLevel,
    TelemetryEvent,
)

logger = logging.getLogger(__name__)


class BoundedEventBuffer:
    """Thread-safe bounded ring buffer and event coalescer for high-volume collector streams."""

    DEFAULT_CAPACITY: int = 5000
    DEFAULT_COALESCE_WINDOW_MS: float = 100.0

    def __init__(
        self,
        subsystem: str,
        max_capacity: int = DEFAULT_CAPACITY,
        drop_policy: EventDropPolicy = EventDropPolicy.DROP_OLDEST,
        coalesce_window_ms: float = DEFAULT_COALESCE_WINDOW_MS,
    ) -> None:
        if max_capacity <= 0:
            raise ValueError(f"max_capacity must be positive, got {max_capacity}")

        self.subsystem = subsystem
        self.max_capacity = max_capacity
        self.drop_policy = drop_policy
        self.coalesce_window_ms = coalesce_window_ms

        self._lock = threading.Lock()
        self._queue: deque[TelemetryEvent] = deque()
        self._recent_keys: Dict[str, Tuple[TelemetryEvent, float]] = {}

        # Tracking metrics
        self._total_ingested: int = 0
        self._total_emitted: int = 0
        self._total_dropped: int = 0
        self._total_coalesced: int = 0
        self._high_water_mark: int = 0
        self._queue_overflow_detected: bool = False

        # Throughput tracking
        self._window_start_time: float = time.monotonic()
        self._window_event_count: int = 0
        self._last_calculated_eps: float = 0.0

    @property
    def current_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    def _update_throughput(self) -> None:
        """Calculate events-per-second (EPS) across a rolling time window."""
        now = time.monotonic()
        elapsed = now - self._window_start_time
        if elapsed >= 1.0:
            self._last_calculated_eps = self._window_event_count / elapsed
            self._window_start_time = now
            self._window_event_count = 0

    def calculate_pressure_level(self) -> StabilityPressureLevel:
        """Determine backpressure level based on current depth and arrival throughput."""
        with self._lock:
            depth = len(self._queue)
            ratio = depth / float(self.max_capacity)
            eps = self._last_calculated_eps

            if ratio >= 0.95 or eps > 1500.0:
                return StabilityPressureLevel.SATURATED
            elif ratio >= 0.80 or eps > 500.0:
                return StabilityPressureLevel.HIGH_PRESSURE
            elif ratio >= 0.50 or eps > 100.0:
                return StabilityPressureLevel.ELEVATED
            else:
                return StabilityPressureLevel.NOMINAL

    def ingest(self, event: TelemetryEvent) -> bool:
        """Ingest a single telemetry event into the bounded buffer with coalescing.

        Returns:
            bool: True if the event was queued as a new entry,
                  False if coalesced into an existing event or dropped due to backpressure.
        """
        now_mono = time.monotonic()

        with self._lock:
            self._total_ingested += 1
            self._window_event_count += 1
            self._update_throughput()

            # 1. Event Coalescing Check (INV-STAB-03)
            dedup_key = event.deduplication_key
            if dedup_key in self._recent_keys:
                existing_event, last_time = self._recent_keys[dedup_key]
                window_seconds = self.coalesce_window_ms / 1000.0
                if (now_mono - last_time) <= window_seconds:
                    # Coalesce into existing event
                    existing_event.coalesced_count += 1
                    existing_event.payload.update(event.payload)
                    existing_event.timestamp = event.timestamp
                    self._recent_keys[dedup_key] = (existing_event, now_mono)
                    self._total_coalesced += 1
                    return False

            # 2. Capacity & Eviction Check (INV-STAB-01, INV-STAB-02)
            if len(self._queue) >= self.max_capacity:
                self._queue_overflow_detected = True
                if self.drop_policy == EventDropPolicy.DROP_NEWEST:
                    # Drop incoming event
                    self._total_dropped += 1
                    return False
                else:
                    # DROP_OLDEST (or COALESCE_KEY fallback): Evict oldest event
                    evicted = self._queue.popleft()
                    self._total_dropped += 1
                    evicted_key = evicted.deduplication_key
                    if (
                        evicted_key in self._recent_keys
                        and self._recent_keys[evicted_key][0] is evicted
                    ):
                        del self._recent_keys[evicted_key]

            # 3. Queue new event
            self._queue.append(event)
            self._recent_keys[dedup_key] = (event, now_mono)

            # Update high water mark
            current_len = len(self._queue)
            if current_len > self._high_water_mark:
                self._high_water_mark = current_len

            # Clean stale coalescing keys if map exceeds bounds
            if len(self._recent_keys) > (self.max_capacity * 2):
                self._prune_stale_coalescing_keys(now_mono)

            return True

    def _prune_stale_coalescing_keys(self, now_mono: float) -> None:
        """Prune coalescing registry entries older than the coalescing window."""
        window_seconds = self.coalesce_window_ms / 1000.0
        stale_keys = [
            k
            for k, (_, ts) in self._recent_keys.items()
            if (now_mono - ts) > window_seconds
        ]
        for k in stale_keys:
            del self._recent_keys[k]

    def ingest_batch(self, events: List[TelemetryEvent]) -> int:
        """Ingest a batch of events, returning the number of new distinct queued items."""
        queued_count = 0
        for ev in events:
            if self.ingest(ev):
                queued_count += 1
        return queued_count

    def drain(self, max_events: Optional[int] = None) -> List[TelemetryEvent]:
        """Drain up to `max_events` from the buffer in FIFO order."""
        drained: List[TelemetryEvent] = []
        with self._lock:
            limit = max_events if max_events is not None else len(self._queue)
            while self._queue and len(drained) < limit:
                item = self._queue.popleft()
                drained.append(item)
                # Cleanup recent keys entry
                k = item.deduplication_key
                if k in self._recent_keys and self._recent_keys[k][0] is item:
                    del self._recent_keys[k]

            self._total_emitted += len(drained)
        return drained

    def peek(self, count: int = 10) -> List[TelemetryEvent]:
        """Inspect the next `count` events without removing them."""
        with self._lock:
            return list(self._queue)[:count]

    def clear(self) -> None:
        """Reset the buffer state completely."""
        with self._lock:
            self._queue.clear()
            self._recent_keys.clear()
            self._high_water_mark = 0

    def get_metrics(self) -> BufferCapacityMetrics:
        """Snapshot current quantitative buffer metrics."""
        with self._lock:
            depth = len(self._queue)
            eps = self._last_calculated_eps
            ratio = depth / float(self.max_capacity)

            if ratio >= 0.95 or eps > 1500.0:
                pressure = StabilityPressureLevel.SATURATED
                is_throttled = True
            elif ratio >= 0.80 or eps > 500.0:
                pressure = StabilityPressureLevel.HIGH_PRESSURE
                is_throttled = False
            elif ratio >= 0.50 or eps > 100.0:
                pressure = StabilityPressureLevel.ELEVATED
                is_throttled = False
            else:
                pressure = StabilityPressureLevel.NOMINAL
                is_throttled = False

            return BufferCapacityMetrics(
                max_capacity=self.max_capacity,
                current_depth=depth,
                high_water_mark=self._high_water_mark,
                total_ingested=self._total_ingested,
                total_emitted=self._total_emitted,
                total_dropped=self._total_dropped,
                total_coalesced=self._total_coalesced,
                drop_policy=self.drop_policy,
                pressure_level=pressure,
                queue_overflow_detected=self._queue_overflow_detected,
                is_throttled=is_throttled,
                scan_proves_safe=False,
            )


class CollectorStabilityManager:
    """Orchestrates stability monitoring, stress-testing, and backpressure across telemetry collectors."""

    def __init__(self) -> None:
        self._buffers: Dict[str, BoundedEventBuffer] = {}
        self._lock = threading.Lock()

    def get_or_create_buffer(
        self,
        subsystem: str,
        max_capacity: int = BoundedEventBuffer.DEFAULT_CAPACITY,
        drop_policy: EventDropPolicy = EventDropPolicy.DROP_OLDEST,
        coalesce_window_ms: float = BoundedEventBuffer.DEFAULT_COALESCE_WINDOW_MS,
    ) -> BoundedEventBuffer:
        """Retrieve or initialize a bounded event buffer for a subsystem."""
        with self._lock:
            if subsystem not in self._buffers:
                self._buffers[subsystem] = BoundedEventBuffer(
                    subsystem=subsystem,
                    max_capacity=max_capacity,
                    drop_policy=drop_policy,
                    coalesce_window_ms=coalesce_window_ms,
                )
            return self._buffers[subsystem]

    @staticmethod
    def get_memory_rss_bytes() -> int:
        """Retrieve current process resident set size (RSS) in bytes safely."""
        try:
            # ru_maxrss is in bytes on macOS, kilobytes on Linux
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if platform.system() == "Darwin":
                return int(usage)
            else:
                return int(usage * 1024)
        except Exception:
            return 0

    def simulate_fsevents_burst(
        self,
        event_count: int = 10000,
        hot_files_count: int = 20,
        max_capacity: int = 5000,
    ) -> CollectorStabilityReport:
        """Simulate high-volume FSEvents burst stress testing bounded queues and coalescing."""
        buffer = self.get_or_create_buffer(
            subsystem="fsevents",
            max_capacity=max_capacity,
            drop_policy=EventDropPolicy.DROP_OLDEST,
            coalesce_window_ms=500.0,
        )
        buffer.clear()

        rss_before = self.get_memory_rss_bytes()
        start_mono = time.monotonic()

        # Generate burst events with hot files that repeat to trigger coalescing
        hot_paths = [f"/tmp/build_target/file_{i}.o" for i in range(hot_files_count)]
        event_batch: List[TelemetryEvent] = []

        for i in range(event_count):
            path = hot_paths[i % hot_files_count] if (i % 2 == 0) else f"/Applications/App_{i}.app"
            event_type = "file_modified" if (i % 2 == 0) else "file_created"
            ev = TelemetryEvent(
                event_id=f"fsev_{i}",
                subsystem="fsevents",
                event_type=event_type,
                target_key=path,
                payload={"inode": 10000 + i, "size": 1024 * (i % 10)},
            )
            event_batch.append(ev)

        # Ingest in chunks of 500 to simulate batch stream ingestion
        chunk_size = 500
        for chunk_idx in range(0, len(event_batch), chunk_size):
            chunk = event_batch[chunk_idx : chunk_idx + chunk_size]
            buffer.ingest_batch(chunk)

        elapsed = time.monotonic() - start_mono
        rss_after = self.get_memory_rss_bytes()
        growth = max(0, rss_after - rss_before)

        metrics = buffer.get_metrics()
        throughput = event_count / elapsed if elapsed > 0 else 0.0

        # Measure drain latency
        drain_start = time.monotonic()
        drained = buffer.drain(max_events=1000)
        drain_latency_ms = (time.monotonic() - drain_start) * 1000.0

        coalescing_ratio = (
            round(metrics.total_coalesced / float(metrics.total_ingested), 4)
            if metrics.total_ingested > 0
            else 0.0
        )

        status = CollectorOperationalStatus.HEALTHY
        warnings: List[str] = []
        if metrics.queue_overflow_detected:
            warnings.append(
                f"Queue capacity of {max_capacity} exceeded: {metrics.total_dropped} events dropped via {metrics.drop_policy.value}"
            )
        if metrics.pressure_level in (
            StabilityPressureLevel.HIGH_PRESSURE,
            StabilityPressureLevel.SATURATED,
        ):
            status = CollectorOperationalStatus.SATURATED

        return CollectorStabilityReport(
            collector_name="fsevents_collector",
            status=status,
            collection_method="IN_MEMORY_STABILITY_ENGINE",
            timestamp=datetime.now(timezone.utc).isoformat(),
            host_platform=f"{platform.system()}-{platform.machine()}",
            metrics=metrics,
            peak_throughput_eps=round(throughput, 2),
            average_batch_latency_ms=round(drain_latency_ms, 2),
            memory_rss_bytes=rss_after,
            memory_growth_bytes=growth,
            coalescing_efficiency_ratio=coalescing_ratio,
            warnings=warnings,
            unavailable_telemetry=[],
            scan_proves_safe=False,
        )

    def simulate_process_storm(
        self,
        event_count: int = 2000,
        distinct_pids: int = 50,
        max_capacity: int = 1000,
    ) -> CollectorStabilityReport:
        """Simulate high-frequency process creation/exit storms."""
        buffer = self.get_or_create_buffer(
            subsystem="process",
            max_capacity=max_capacity,
            drop_policy=EventDropPolicy.DROP_OLDEST,
            coalesce_window_ms=200.0,
        )
        buffer.clear()

        rss_before = self.get_memory_rss_bytes()
        start_mono = time.monotonic()

        for i in range(event_count):
            pid = 2000 + (i % distinct_pids)
            event_type = "proc_spawn" if (i % 2 == 0) else "proc_exit"
            ev = TelemetryEvent(
                event_id=f"proc_{i}",
                subsystem="process",
                event_type=event_type,
                target_key=str(pid),
                payload={"command": f"/bin/test_worker_{pid}", "cpu_pct": 5.2},
            )
            buffer.ingest(ev)

        elapsed = time.monotonic() - start_mono
        rss_after = self.get_memory_rss_bytes()
        growth = max(0, rss_after - rss_before)

        metrics = buffer.get_metrics()
        throughput = event_count / elapsed if elapsed > 0 else 0.0

        drain_start = time.monotonic()
        drained = buffer.drain(max_events=500)
        drain_latency_ms = (time.monotonic() - drain_start) * 1000.0

        coalescing_ratio = (
            round(metrics.total_coalesced / float(metrics.total_ingested), 4)
            if metrics.total_ingested > 0
            else 0.0
        )

        status = CollectorOperationalStatus.HEALTHY
        warnings: List[str] = []
        if metrics.queue_overflow_detected:
            warnings.append(
                f"Process storm overflowed buffer capacity ({max_capacity}): {metrics.total_dropped} events evicted"
            )

        return CollectorStabilityReport(
            collector_name="process_collector",
            status=status,
            collection_method="IN_MEMORY_STABILITY_ENGINE",
            timestamp=datetime.now(timezone.utc).isoformat(),
            host_platform=f"{platform.system()}-{platform.machine()}",
            metrics=metrics,
            peak_throughput_eps=round(throughput, 2),
            average_batch_latency_ms=round(drain_latency_ms, 2),
            memory_rss_bytes=rss_after,
            memory_growth_bytes=growth,
            coalescing_efficiency_ratio=coalescing_ratio,
            warnings=warnings,
            unavailable_telemetry=[],
            scan_proves_safe=False,
        )
