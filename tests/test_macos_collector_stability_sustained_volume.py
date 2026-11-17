"""Test suite verifying telemetry collector stability under sustained event volume."""

from __future__ import annotations

import ast
import platform
import threading
import time
from typing import List
import pytest

from system_mind.macos.collector_stability import (
    BoundedEventBuffer,
    CollectorStabilityManager,
)
from system_mind.macos.collector_stability_models import (
    BufferCapacityMetrics,
    CollectorOperationalStatus,
    CollectorStabilityReport,
    EventDropPolicy,
    StabilityPressureLevel,
    TelemetryEvent,
)


@pytest.mark.unit
def test_bounded_event_buffer_initialization_and_validation() -> None:
    """Buffer validates parameters and initializes with nominal baseline metrics."""
    with pytest.raises(ValueError, match="max_capacity must be positive"):
        BoundedEventBuffer(subsystem="test", max_capacity=0)

    buf = BoundedEventBuffer(subsystem="fsevents", max_capacity=100)
    assert buf.subsystem == "fsevents"
    assert buf.max_capacity == 100
    assert buf.current_depth == 0

    metrics = buf.get_metrics()
    assert metrics.current_depth == 0
    assert metrics.high_water_mark == 0
    assert metrics.total_ingested == 0
    assert metrics.total_dropped == 0
    assert metrics.total_coalesced == 0
    assert not metrics.queue_overflow_detected
    assert not metrics.is_throttled
    assert metrics.pressure_level == StabilityPressureLevel.NOMINAL
    assert metrics.scan_proves_safe is False


@pytest.mark.unit
def test_burst_fsevents_10000_events_bounded_capacity() -> None:
    """Sustained burst of 10,000 events must never exceed max_capacity (INV-STAB-01, INV-STAB-02)."""
    capacity = 2000
    total_burst = 10000
    buf = BoundedEventBuffer(
        subsystem="fsevents",
        max_capacity=capacity,
        drop_policy=EventDropPolicy.DROP_OLDEST,
        coalesce_window_ms=0.0,  # Disable coalescing to strictly test capacity bounds
    )

    start_mono = time.monotonic()
    for i in range(total_burst):
        ev = TelemetryEvent(
            event_id=f"ev_{i}",
            subsystem="fsevents",
            event_type="file_created",
            target_key=f"/Applications/UniqueApp_{i}.app",
            payload={"size": i},
        )
        buf.ingest(ev)

    duration = time.monotonic() - start_mono
    metrics = buf.get_metrics()

    # Bounded queue verification
    assert buf.current_depth == capacity
    assert metrics.current_depth == capacity
    assert metrics.max_capacity == capacity
    assert metrics.total_ingested == total_burst
    assert metrics.total_dropped == (total_burst - capacity)
    assert metrics.high_water_mark == capacity
    assert metrics.queue_overflow_detected is True
    assert metrics.drop_ratio == round((total_burst - capacity) / total_burst, 4)
    assert duration < 2.0, f"Burst ingestion took too long: {duration}s"


@pytest.mark.unit
def test_drop_newest_policy_under_saturation() -> None:
    """When drop policy is DROP_NEWEST, incoming events are dropped upon saturation."""
    buf = BoundedEventBuffer(
        subsystem="process",
        max_capacity=50,
        drop_policy=EventDropPolicy.DROP_NEWEST,
        coalesce_window_ms=0.0,
    )

    for i in range(150):
        ev = TelemetryEvent(
            event_id=f"p_{i}",
            subsystem="process",
            event_type="proc_spawn",
            target_key=f"pid_{i}",
        )
        retained = buf.ingest(ev)
        if i < 50:
            assert retained is True
        else:
            assert retained is False

    metrics = buf.get_metrics()
    assert metrics.current_depth == 50
    assert metrics.total_ingested == 150
    assert metrics.total_dropped == 100
    assert metrics.queue_overflow_detected is True

    # Peek confirms first 50 events were retained
    peeked = buf.peek(count=10)
    assert peeked[0].event_id == "p_0"
    assert peeked[9].event_id == "p_9"


@pytest.mark.unit
def test_event_coalescing_efficiency() -> None:
    """Burst modifications to the same file are coalesced into a single entry (INV-STAB-03)."""
    buf = BoundedEventBuffer(
        subsystem="fsevents",
        max_capacity=1000,
        drop_policy=EventDropPolicy.DROP_OLDEST,
        coalesce_window_ms=500.0,  # 500ms coalescing window
    )

    hot_files = [f"/tmp/build/target_{k}.o" for k in range(5)]
    total_events = 500

    for i in range(total_events):
        target = hot_files[i % len(hot_files)]
        ev = TelemetryEvent(
            event_id=f"mod_{i}",
            subsystem="fsevents",
            event_type="file_modified",
            target_key=target,
            payload={"bytes_written": i * 10},
        )
        buf.ingest(ev)

    metrics = buf.get_metrics()
    # 500 events across 5 hot files should result in exactly 5 queued items
    assert metrics.current_depth == 5
    assert metrics.total_ingested == total_events
    assert metrics.total_coalesced == (total_events - len(hot_files))
    assert metrics.total_dropped == 0

    drained = buf.drain()
    assert len(drained) == 5
    for item in drained:
        assert item.coalesced_count == 100


@pytest.mark.unit
def test_process_storm_simulation() -> None:
    """Process storm simulation records correct operational report and latency."""
    manager = CollectorStabilityManager()
    report = manager.simulate_process_storm(
        event_count=1000,
        distinct_pids=25,
        max_capacity=500,
    )

    assert report.collector_name == "process_collector"
    assert report.collection_method == "IN_MEMORY_STABILITY_ENGINE"
    assert report.metrics.total_ingested == 1000
    assert report.metrics.current_depth <= 500
    assert report.peak_throughput_eps > 0.0
    assert report.average_batch_latency_ms < 50.0  # Latency containment
    assert report.scan_proves_safe is False
    assert report.metrics.scan_proves_safe is False


@pytest.mark.unit
def test_fsevents_burst_simulation() -> None:
    """FSEvents burst simulation produces valid stability report with drop warnings."""
    manager = CollectorStabilityManager()
    report = manager.simulate_fsevents_burst(
        event_count=5000,
        hot_files_count=10,
        max_capacity=1000,
    )

    assert report.collector_name == "fsevents_collector"
    assert report.metrics.total_ingested == 5000
    assert report.metrics.max_capacity == 1000
    assert report.metrics.queue_overflow_detected is True
    assert len(report.warnings) > 0
    assert report.status in (CollectorOperationalStatus.HEALTHY, CollectorOperationalStatus.SATURATED)
    assert report.scan_proves_safe is False


@pytest.mark.unit
def test_drain_latency_and_fifo_order() -> None:
    """Draining buffer maintains FIFO ordering and completes within latency threshold."""
    buf = BoundedEventBuffer(
        subsystem="fsevents",
        max_capacity=2000,
        coalesce_window_ms=0.0,
    )

    for i in range(1000):
        buf.ingest(
            TelemetryEvent(
                event_id=f"seq_{i}",
                subsystem="fsevents",
                event_type="change",
                target_key=f"item_{i}",
            )
        )

    drain_start = time.monotonic()
    drained = buf.drain()
    drain_time_ms = (time.monotonic() - drain_start) * 1000.0

    assert len(drained) == 1000
    assert drained[0].event_id == "seq_0"
    assert drained[999].event_id == "seq_999"
    assert drain_time_ms < 50.0, f"Drain took too long: {drain_time_ms}ms"
    assert buf.current_depth == 0


@pytest.mark.unit
def test_multithreaded_concurrency_ingestion_and_draining() -> None:
    """Buffer is thread-safe under concurrent producers and consumers without deadlocks (multithreaded_concurrency)."""
    buf = BoundedEventBuffer(subsystem="telemetry", max_capacity=2000, coalesce_window_ms=0.0)
    num_producers = 4
    events_per_producer = 500
    errors: List[Exception] = []

    def producer_worker(producer_id: int) -> None:
        try:
            for i in range(events_per_producer):
                ev = TelemetryEvent(
                    event_id=f"prod_{producer_id}_{i}",
                    subsystem="telemetry",
                    event_type="tick",
                    target_key=f"sensor_{producer_id}_{i}",
                )
                buf.ingest(ev)
        except Exception as e:
            errors.append(e)

    consumer_drained_count = 0
    consumer_stop = threading.Event()

    def consumer_worker() -> None:
        nonlocal consumer_drained_count
        while not consumer_stop.is_set() or buf.current_depth > 0:
            batch = buf.drain(max_events=100)
            consumer_drained_count += len(batch)
            time.sleep(0.001)

    threads: List[threading.Thread] = []
    for pid in range(num_producers):
        t = threading.Thread(target=producer_worker, args=(pid,))
        threads.append(t)

    consumer_thread = threading.Thread(target=consumer_worker)
    consumer_thread.start()

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    consumer_stop.set()
    consumer_thread.join(timeout=2.0)

    assert len(errors) == 0, f"Thread errors encountered: {errors}"
    metrics = buf.get_metrics()
    assert metrics.total_ingested == (num_producers * events_per_producer)
    assert (metrics.total_emitted + buf.current_depth) == (num_producers * events_per_producer)


@pytest.mark.unit
def test_memory_stability_across_repeated_burst_cycles() -> None:
    """Successive burst and drain cycles do not exhibit monotonic unbounded memory leakage."""
    manager = CollectorStabilityManager()
    buf = manager.get_or_create_buffer(subsystem="fsevents", max_capacity=1000, coalesce_window_ms=0.0)

    rss_initial = manager.get_memory_rss_bytes()

    for cycle in range(5):
        # Ingest 2,000 events
        for i in range(2000):
            buf.ingest(
                TelemetryEvent(
                    event_id=f"cycle_{cycle}_{i}",
                    subsystem="fsevents",
                    event_type="test",
                    target_key=f"file_{i}",
                )
            )
        # Drain all
        buf.drain()

    rss_final = manager.get_memory_rss_bytes()
    growth_mb = (rss_final - rss_initial) / (1024.0 * 1024.0)

    # In Python, RSS can fluctuate slightly due to GC arenas, but should not grow by > 50MB
    assert growth_mb < 50.0, f"Excessive memory growth detected: {growth_mb}MB"


@pytest.mark.unit
def test_adaptive_pressure_level_transitions() -> None:
    """Pressure level transitions accurately across fill ratios."""
    buf = BoundedEventBuffer(subsystem="test", max_capacity=100, coalesce_window_ms=0.0)

    # Nominal: 0%
    assert buf.calculate_pressure_level() == StabilityPressureLevel.NOMINAL

    # Elevated: 60%
    for i in range(60):
        buf.ingest(TelemetryEvent(f"e_{i}", "test", "type", f"k_{i}"))
    assert buf.calculate_pressure_level() == StabilityPressureLevel.ELEVATED

    # High pressure: 85%
    for i in range(60, 85):
        buf.ingest(TelemetryEvent(f"e_{i}", "test", "type", f"k_{i}"))
    assert buf.calculate_pressure_level() == StabilityPressureLevel.HIGH_PRESSURE

    # Saturated: 98%
    for i in range(85, 98):
        buf.ingest(TelemetryEvent(f"e_{i}", "test", "type", f"k_{i}"))
    assert buf.calculate_pressure_level() == StabilityPressureLevel.SATURATED
    metrics = buf.get_metrics()
    assert metrics.is_throttled is True


@pytest.mark.safety_critical
def test_scan_proves_safe_charter_invariant_across_all_stability_models() -> None:
    """All stability models structurally enforce scan_proves_safe = False (INV-STAB-05)."""
    ev = TelemetryEvent(
        event_id="ev_safe",
        subsystem="fsevents",
        event_type="created",
        target_key="/tmp/safe.txt",
        scan_proves_safe=True,  # Attempting to set True must be overridden by __post_init__
    )
    assert ev.scan_proves_safe is False

    metrics = BufferCapacityMetrics(
        max_capacity=100,
        current_depth=10,
        high_water_mark=10,
        total_ingested=10,
        total_emitted=0,
        total_dropped=0,
        total_coalesced=0,
        scan_proves_safe=True,
    )
    assert metrics.scan_proves_safe is False

    report = CollectorStabilityReport(
        collector_name="test_collector",
        status=CollectorOperationalStatus.HEALTHY,
        scan_proves_safe=True,
    )
    assert report.scan_proves_safe is False


@pytest.mark.safety_critical
def test_zero_ambient_shell_authority_ast_check() -> None:
    """AST check verifies zero shell=True or os.system across stability implementation (SC-01)."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent

    target_files = [
        root / "src" / "system_mind" / "macos" / "collector_stability.py",
        root / "src" / "system_mind" / "macos" / "collector_stability_models.py",
    ]

    for fpath in target_files:
        assert fpath.exists(), f"File missing: {fpath}"
        source = fpath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(fpath))

        for node in ast.walk(tree):
            # Check for os.system calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        pytest.fail(f"Forbidden os.system detected in {fpath.name}:{node.lineno}")

                # Check for shell=True in subprocess calls
                for kw in node.keywords:
                    if kw.arg == "shell":
                        if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            pytest.fail(f"Forbidden shell=True detected in {fpath.name}:{node.lineno}")
