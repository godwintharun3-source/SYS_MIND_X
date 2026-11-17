# DAY 063: Test Collector Stability Under Sustained Event Volume

## 1. Context & Architectural Goal
As part of **Milestone 4: macOS system agent and telemetry (Days 041–065)**, SYSTEM MIND X implements a read-only companion agent collecting high-resolution telemetry across macOS hardware, system services, running processes, and filesystem mutations (via FSEvents and Endpoint Security fallbacks).

In active production environments, telemetry collectors encounter extreme spikes and sustained high-volume event streams, including:
1. Massive filesystem churn from build systems (e.g. `cargo build`, `npm install`, Git checkouts) generating 10,000+ FSEvents notifications per minute.
2. Process storms from short-lived child processes, shell scripts, or build toolchains spawning and terminating rapidly.
3. Sustained high-frequency polling from diagnostic engines, digital-twin reconciliation loops, and inventory aggregation queries.

Without strict architectural stability controls, sustained event volume causes catastrophic companion agent failure:
- **Unbounded Memory Growth / OOM**: Event queues accumulating unbounded event objects until the macOS kernel terminates the process via jetsam or OOM killer.
- **Thread Starvation & Deadlock**: Unsynchronized or coarsely locked event queues stalling the agent main loop or UI communication channel.
- **Latency Spikes**: Batch draining and serialization taking hundreds of milliseconds, blocking timely telemetry delivery.
- **Silent Event Loss**: Dropping critical telemetry without diagnostic counters, misleading operators and digital-twin state engines.

Day 063 establishes the **Collector Stability Engine**, **Bounded Event Ring Buffer**, **Event Coalescer**, and **Adaptive Backpressure Throttler** (`src/system_mind/macos/collector_stability.py`, `src/system_mind/macos/collector_stability_models.py`, `crates/system-mind-sensors/src/macos_stability.rs`), verified through rigorous stress testing under sustained high-volume workloads.

---

## 2. Invariants & Stability Contracts

| Invariant ID | Rule | Description |
| :--- | :--- | :--- |
| `INV-STAB-01` | **Bounded Memory Footprint** | All collector event buffers enforce hard upper-bound capacities (`max_capacity`, default 5,000 events); memory growth is strictly bounded and independent of total incoming event count. |
| `INV-STAB-02` | **Deterministic Drop Telemetry** | When buffer capacity is saturated, the system applies deterministic eviction (`DROP_OLDEST` or `DROP_NEWEST`) and precisely records drop metrics (`total_dropped`, `queue_overflow_detected`, `drop_ratio`). |
| `INV-STAB-03` | **Event Coalescing & Deduplication** | Rapid successive events targeting the same resource (`subsystem`, `target_key`, `event_type`) within a coalescing time window are merged into a single event with an incremented `coalesced_count`, reducing memory and downstream processing load. |
| `INV-STAB-04` | **Adaptive Backpressure & Throttling** | The collector monitors event ingestion throughput (events per second) and buffer depth, dynamically transitioning between pressure states (`NOMINAL`, `ELEVATED`, `HIGH_PRESSURE`, `SATURATED`) and signaling backpressure. |
| `INV-STAB-05` | **Universal "Scan != Safe" Invariant** | High-volume event batches, saturated queues, and drop telemetry structurally enforce `scan_proves_safe = False`. Under no circumstances can sustained volume or high collector throughput imply that host state or monitored software is safe. |
| `INV-STAB-06` | **Zero Ambient Shell Authority (`SC-01`)** | All stability monitoring, event buffers, and stress harnesses operate purely in user-space memory without invoking shell interpreters (`shell=True`, `os.system`) or mutating host operating system state. |

---

## 3. Core Architectural Components

### 3.1 Bounded Event Ring Buffer (`BoundedEventBuffer`)
A thread-safe, high-performance in-memory ring buffer implementing:
- **Configurable Capacity**: Default `max_capacity = 5000` items.
- **Thread-Safety**: Concurrency control via fine-grained `threading.Lock` protecting queue state during concurrent ingestion and consumption.
- **Eviction Policies**:
  - `DROP_OLDEST`: Default ring-buffer behavior. When full, evicts oldest unread events to retain freshest system state.
  - `DROP_NEWEST`: Backpressure shedding behavior. Rejects new arrivals until existing queue drains.
- **Capacity Tracking**: High-water mark, current depth, total ingested, total emitted, and total dropped counters.

### 3.2 Event Coalescer (`EventCoalescer`)
Reduces event volume by coalescing repeated operations on identical target entities:
- Keyed by `(subsystem, target_key, event_type)`.
- Temporal coalescing window (configurable, default 100ms).
- Increments `coalesced_count` and updates payload with latest state snapshot, preventing duplicate events from flooding down-stream collectors.

### 3.3 Collector Stability Manager (`CollectorStabilityManager`)
Coordinates stability across all active telemetry collectors:
- Dynamically calculates throughput: `events_per_second` (EPS) over rolling time windows.
- Calculates adaptive pressure level:
  - `NOMINAL`: Queue depth < 50%, EPS < 100.
  - `ELEVATED`: Queue depth 50%–80%, EPS 100–500.
  - `HIGH_PRESSURE`: Queue depth 80%–95%, EPS 500–1,500.
  - `SATURATED`: Queue depth >= 95% or EPS > 1,500 (throttling active, drop warning flagged).
- Coordinates with `CollectorHealthManager`: trips collector circuit breakers if extreme thrashing persists.
- Computes comprehensive `CollectorStabilityReport` capturing memory RSS, throughput, latency, and drop statistics.

---

## 4. Sustained Volume Stress Scenarios

The stability test suite (`tests/test_macos_collector_stability_sustained_volume.py`) rigorously validates:
1. **Burst FSEvents Ingestion (10,000+ events)**: Ingests 10,000 rapid file creation and modification events; verifies queue depth never exceeds `max_capacity`, dropped counters match exact overflow math, and execution completes in < 500ms.
2. **Event Coalescing Efficiency**: Ingests 1,000 rapid file modifications to the same 10 hot files; verifies coalescing consolidates 1,000 events down to 10 entries with `coalesced_count = 100` each (99% volume reduction).
3. **Process Storm Simulation**: Simulates 2,000 rapid process spawn/exit events; verifies process table collector stability without thread exhaustion.
4. **Memory Footprint Containment**: Repeatedly ingests and drains 20,000 events across 10 sustained cycles; verifies memory footprint does not show monotonic unbounded growth.
5. **Batch Drain Latency Containment**: Drains full buffers (5,000 events); verifies drain latency remains < 50ms per batch.
6. **Concurrent Ingestion & Draining**: Simulates multi-threaded producers (FSEvents thread, Process poller) and single consumer thread concurrently; verifies zero race conditions, deadlocks, or data corruption.
7. **Adaptive Throttling & Saturated State**: Pushes buffer past high-water mark; verifies `pressure_level == SATURATED` and `is_throttled == True`.
8. **Universal Charter Invariant**: Verifies all emitted batches, drop reports, and stability metrics enforce `scan_proves_safe = False`.

---

## 5. Polyglot Parity (Rust & Python)
A corresponding Rust implementation in `crates/system-mind-sensors/src/macos_stability.rs` mirrors the stability data structures (`CollectorStabilityReportSnapshot`, `BufferCapacityMetricsSnapshot`, `StabilityPressureLevelSnapshot`, `EventDropPolicySnapshot`) ensuring full polyglot type parity across the workspace.

---

## 6. Security and Compliance
- **Zero Mutating Host Impact**: All stress testing runs against synthetic in-memory event generators; no actual disk files are created on the host or rapid processes spawned.
- **Zero Ambient Shell Authority (`SC-01`)**: Pure in-memory Python and Rust; zero `shell=True` or `os.system`.
- **Scan != Safe (`INV-STAB-05`)**: Guaranteed across all reports and models.
