//! macOS telemetry collector stability under sustained event volume sensor.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventDropPolicySnapshot {
    DropOldest,
    DropNewest,
    CoalesceKey,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StabilityPressureLevelSnapshot {
    Nominal,
    Elevated,
    HighPressure,
    Saturated,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CollectorOperationalStatusSnapshot {
    Healthy,
    Degraded,
    Saturated,
    CircuitBroken,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TelemetryEventSnapshot {
    pub event_id: String,
    pub subsystem: String,
    pub event_type: String,
    pub target_key: String,
    pub payload_summary: String,
    pub timestamp: String,
    pub source_timestamp_ns: u64,
    pub coalesced_count: usize,
    pub scan_proves_safe: bool,
}

impl TelemetryEventSnapshot {
    pub fn new(
        event_id: impl Into<String>,
        subsystem: impl Into<String>,
        event_type: impl Into<String>,
        target_key: impl Into<String>,
    ) -> Self {
        Self {
            event_id: event_id.into(),
            subsystem: subsystem.into(),
            event_type: event_type.into(),
            target_key: target_key.into(),
            payload_summary: "{}".to_string(),
            timestamp: "2026-11-17T09:30:00Z".to_string(),
            source_timestamp_ns: 1731835800000000000,
            coalesced_count: 1,
            scan_proves_safe: false, // Invariant INV-STAB-05
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct BufferCapacityMetricsSnapshot {
    pub max_capacity: usize,
    pub current_depth: usize,
    pub high_water_mark: usize,
    pub total_ingested: usize,
    pub total_emitted: usize,
    pub total_dropped: usize,
    pub total_coalesced: usize,
    pub drop_policy: EventDropPolicySnapshot,
    pub pressure_level: StabilityPressureLevelSnapshot,
    pub queue_overflow_detected: bool,
    pub is_throttled: bool,
    pub drop_ratio: f64,
    pub scan_proves_safe: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CollectorStabilityReportSnapshot {
    pub collector_name: String,
    pub status: CollectorOperationalStatusSnapshot,
    pub collection_method: String,
    pub timestamp: String,
    pub host_platform: String,
    pub metrics: BufferCapacityMetricsSnapshot,
    pub peak_throughput_eps: f64,
    pub average_batch_latency_ms: f64,
    pub memory_rss_bytes: u64,
    pub memory_growth_bytes: u64,
    pub coalescing_efficiency_ratio: f64,
    pub warnings: Vec<String>,
    pub unavailable_telemetry: Vec<String>,
    pub scan_proves_safe: bool,
}

impl CollectorStabilityReportSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"collector\":\"{}\",\"status\":\"{:?}\",\"ingested\":{},\"dropped\":{},\"coalesced\":{},\"depth\":{},\"overflow\":{},\"scan_proves_safe\":{}}}",
            self.collector_name,
            self.status,
            self.metrics.total_ingested,
            self.metrics.total_dropped,
            self.metrics.total_coalesced,
            self.metrics.current_depth,
            self.metrics.queue_overflow_detected,
            self.scan_proves_safe
        )
    }
}

pub trait MacOsCollectorStabilitySensor: Send + Sync {
    fn collect_stability_report(&self) -> CollectorStabilityReportSnapshot;
}

/// Deterministic mock stability sensor providing sustained event volume telemetry.
#[derive(Debug, Clone)]
pub struct MockMacOsCollectorStabilitySensor {
    pub report: CollectorStabilityReportSnapshot,
}

impl MockMacOsCollectorStabilitySensor {
    pub fn new_fsevents_burst(total_ingested: usize, max_capacity: usize) -> Self {
        let overflow = total_ingested > max_capacity;
        let dropped = if overflow {
            total_ingested - max_capacity
        } else {
            0
        };
        let coalesced = (total_ingested as f64 * 0.45) as usize;
        let depth = if overflow {
            max_capacity
        } else {
            total_ingested - coalesced
        };
        let drop_ratio = if total_ingested > 0 {
            dropped as f64 / total_ingested as f64
        } else {
            0.0
        };

        let metrics = BufferCapacityMetricsSnapshot {
            max_capacity,
            current_depth: depth,
            high_water_mark: max_capacity,
            total_ingested,
            total_emitted: 0,
            total_dropped: dropped,
            total_coalesced: coalesced,
            drop_policy: EventDropPolicySnapshot::DropOldest,
            pressure_level: if overflow {
                StabilityPressureLevelSnapshot::Saturated
            } else {
                StabilityPressureLevelSnapshot::Nominal
            },
            queue_overflow_detected: overflow,
            is_throttled: overflow,
            drop_ratio,
            scan_proves_safe: false,
        };

        let report = CollectorStabilityReportSnapshot {
            collector_name: "fsevents_collector".to_string(),
            status: if overflow {
                CollectorOperationalStatusSnapshot::Saturated
            } else {
                CollectorOperationalStatusSnapshot::Healthy
            },
            collection_method: "MOCK_STABILITY_ENGINE".to_string(),
            timestamp: "2026-11-17T09:30:00Z".to_string(),
            host_platform: "Darwin-Mock-Apple-Silicon-arm64".to_string(),
            metrics,
            peak_throughput_eps: 12500.0,
            average_batch_latency_ms: 12.4,
            memory_rss_bytes: 42 * 1024 * 1024,
            memory_growth_bytes: 512 * 1024,
            coalescing_efficiency_ratio: 0.45,
            warnings: if overflow {
                vec![format!(
                    "Queue overflow detected: {} events evicted via DropOldest",
                    dropped
                )]
            } else {
                vec![]
            },
            unavailable_telemetry: vec![],
            scan_proves_safe: false,
        };

        Self { report }
    }

    pub fn new_process_storm(total_procs: usize, max_capacity: usize) -> Self {
        let overflow = total_procs > max_capacity;
        let dropped = if overflow {
            total_procs - max_capacity
        } else {
            0
        };
        let metrics = BufferCapacityMetricsSnapshot {
            max_capacity,
            current_depth: if overflow { max_capacity } else { total_procs },
            high_water_mark: if overflow { max_capacity } else { total_procs },
            total_ingested: total_procs,
            total_emitted: 0,
            total_dropped: dropped,
            total_coalesced: 200,
            drop_policy: EventDropPolicySnapshot::DropOldest,
            pressure_level: if overflow {
                StabilityPressureLevelSnapshot::HighPressure
            } else {
                StabilityPressureLevelSnapshot::Nominal
            },
            queue_overflow_detected: overflow,
            is_throttled: overflow,
            drop_ratio: if total_procs > 0 {
                dropped as f64 / total_procs as f64
            } else {
                0.0
            },
            scan_proves_safe: false,
        };

        let report = CollectorStabilityReportSnapshot {
            collector_name: "process_collector".to_string(),
            status: CollectorOperationalStatusSnapshot::Healthy,
            collection_method: "MOCK_STABILITY_ENGINE".to_string(),
            timestamp: "2026-11-17T09:30:00Z".to_string(),
            host_platform: "Darwin-Mock-Apple-Silicon-arm64".to_string(),
            metrics,
            peak_throughput_eps: 8500.0,
            average_batch_latency_ms: 8.2,
            memory_rss_bytes: 38 * 1024 * 1024,
            memory_growth_bytes: 256 * 1024,
            coalescing_efficiency_ratio: 0.10,
            warnings: vec![],
            unavailable_telemetry: vec![],
            scan_proves_safe: false,
        };

        Self { report }
    }
}

impl MacOsCollectorStabilitySensor for MockMacOsCollectorStabilitySensor {
    fn collect_stability_report(&self) -> CollectorStabilityReportSnapshot {
        self.report.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_telemetry_event_charter_invariant() {
        let ev = TelemetryEventSnapshot::new("ev1", "fsevents", "file_modified", "/tmp/test.log");
        assert!(!ev.scan_proves_safe, "Scan != Safe invariant violated");
        assert_eq!(ev.coalesced_count, 1);
    }

    #[test]
    fn test_mock_fsevents_burst_stability() {
        let sensor = MockMacOsCollectorStabilitySensor::new_fsevents_burst(10000, 5000);
        let report = sensor.collect_stability_report();

        assert_eq!(report.collector_name, "fsevents_collector");
        assert_eq!(report.metrics.max_capacity, 5000);
        assert_eq!(report.metrics.total_ingested, 10000);
        assert_eq!(report.metrics.total_dropped, 5000);
        assert!(report.metrics.queue_overflow_detected);
        assert_eq!(
            report.metrics.pressure_level,
            StabilityPressureLevelSnapshot::Saturated
        );
        assert!(!report.scan_proves_safe, "Charter invariant violated");
        assert!(
            !report.metrics.scan_proves_safe,
            "Charter invariant violated"
        );
    }

    #[test]
    fn test_mock_process_storm_stability() {
        let sensor = MockMacOsCollectorStabilitySensor::new_process_storm(2000, 5000);
        let report = sensor.collect_stability_report();

        assert_eq!(report.collector_name, "process_collector");
        assert_eq!(report.metrics.total_ingested, 2000);
        assert_eq!(report.metrics.total_dropped, 0);
        assert!(!report.metrics.queue_overflow_detected);
        assert_eq!(
            report.metrics.pressure_level,
            StabilityPressureLevelSnapshot::Nominal
        );
        assert!(!report.scan_proves_safe, "Charter invariant violated");
    }

    #[test]
    fn test_stability_json_summary() {
        let sensor = MockMacOsCollectorStabilitySensor::new_fsevents_burst(1000, 2000);
        let report = sensor.collect_stability_report();
        let summary = report.to_json_summary();

        assert!(summary.contains("\"collector\":\"fsevents_collector\""));
        assert!(summary.contains("\"scan_proves_safe\":false"));
    }
}
