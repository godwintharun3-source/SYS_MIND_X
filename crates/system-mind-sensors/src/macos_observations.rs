//! macOS Darwin observation source timestamps and confidence scoring sensor collector.

use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConfidenceTierSnapshot {
    KernelAuthoritative,
    SubsystemVerified,
    HeuristicParsed,
    DegradedPartial,
    EstimatedMock,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SourceTimestampSnapshot {
    pub utc_iso: String,
    pub epoch_ms: u64,
    pub monotonic_ns: Option<u64>,
    pub clock_source: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ObservationConfidenceSnapshot {
    pub score: f32,
    pub tier: ConfidenceTierSnapshot,
    pub rationale: String,
    pub penalty_factors: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ObservedTelemetryEnvelopeSnapshot {
    pub observation_id: String,
    pub collector_id: String,
    pub source_timestamp: SourceTimestampSnapshot,
    pub observed_at_utc: String,
    pub latency_ms: f64,
    pub confidence: ObservationConfidenceSnapshot,
    pub payload_sha256: String,
    pub scan_proves_safe: bool,
    pub is_mock: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CompanionObservationBatchSnapshot {
    pub batch_id: String,
    pub timestamp_utc: String,
    pub total_observations: usize,
    pub observations: HashMap<String, ObservedTelemetryEnvelopeSnapshot>,
    pub mean_confidence: f32,
    pub lowest_confidence_collector: String,
    pub scan_proves_safe: bool,
    pub is_mock: bool,
}

impl CompanionObservationBatchSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"batch_id\":\"{}\",\"total_observations\":{},\"mean_confidence\":{:.3},\"lowest_collector\":\"{}\",\"scan_proves_safe\":{},\"mock\":{}}}",
            self.batch_id,
            self.total_observations,
            self.mean_confidence,
            self.lowest_confidence_collector,
            self.scan_proves_safe,
            self.is_mock
        )
    }
}

pub trait MacOsObservationCollector {
    fn collect_batch(&self) -> Result<CompanionObservationBatchSnapshot, String>;
}

pub struct MockMacOsObservationCollector {
    pub profile: String,
}

impl MockMacOsObservationCollector {
    pub fn new(profile: &str) -> Self {
        Self {
            profile: profile.to_string(),
        }
    }
}

impl Default for MockMacOsObservationCollector {
    fn default() -> Self {
        Self::new("high_fidelity")
    }
}

pub const MOCK_OBSERVATION_COLLECTORS: [&str; 16] = [
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
];

impl MacOsObservationCollector for MockMacOsObservationCollector {
    fn collect_batch(&self) -> Result<CompanionObservationBatchSnapshot, String> {
        let mut map = HashMap::new();
        let timestamp = "2026-11-17T12:00:00Z".to_string();
        let batch_id = "batch-mock-058".to_string();

        match self.profile.as_str() {
            "degraded" => {
                for &cid in &MOCK_OBSERVATION_COLLECTORS {
                    let (score, tier, penalty) = match cid {
                        "battery" => (
                            0.75,
                            ConfidenceTierSnapshot::HeuristicParsed,
                            vec!["hardware_absent_desktop".to_string()],
                        ),
                        "endpoint_security" => (
                            0.50,
                            ConfidenceTierSnapshot::DegradedPartial,
                            vec!["missing_permission_or_entitlement".to_string()],
                        ),
                        _ => (
                            0.95,
                            ConfidenceTierSnapshot::KernelAuthoritative,
                            Vec::new(),
                        ),
                    };

                    map.insert(
                        cid.to_string(),
                        ObservedTelemetryEnvelopeSnapshot {
                            observation_id: format!("obs-{}-mock", cid),
                            collector_id: cid.to_string(),
                            source_timestamp: SourceTimestampSnapshot {
                                utc_iso: timestamp.clone(),
                                epoch_ms: 1794916800000,
                                monotonic_ns: Some(42000000),
                                clock_source: "mock_clock".to_string(),
                            },
                            observed_at_utc: timestamp.clone(),
                            latency_ms: 12.0,
                            confidence: ObservationConfidenceSnapshot {
                                score,
                                tier,
                                rationale: format!("Simulated {} telemetry", cid),
                                penalty_factors: penalty,
                            },
                            payload_sha256:
                                "a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef"
                                    .to_string(),
                            scan_proves_safe: false,
                            is_mock: true,
                        },
                    );
                }
                let mean = map.values().map(|e| e.confidence.score).sum::<f32>() / map.len() as f32;
                Ok(CompanionObservationBatchSnapshot {
                    batch_id,
                    timestamp_utc: timestamp,
                    total_observations: 16,
                    observations: map,
                    mean_confidence: mean,
                    lowest_confidence_collector: "endpoint_security".to_string(),
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
            "mock_simulation" => {
                for &cid in &MOCK_OBSERVATION_COLLECTORS {
                    map.insert(
                        cid.to_string(),
                        ObservedTelemetryEnvelopeSnapshot {
                            observation_id: format!("obs-{}-mock", cid),
                            collector_id: cid.to_string(),
                            source_timestamp: SourceTimestampSnapshot {
                                utc_iso: timestamp.clone(),
                                epoch_ms: 1794916800000,
                                monotonic_ns: None,
                                clock_source: "mock_clock".to_string(),
                            },
                            observed_at_utc: timestamp.clone(),
                            latency_ms: 5.0,
                            confidence: ObservationConfidenceSnapshot {
                                score: 0.35,
                                tier: ConfidenceTierSnapshot::EstimatedMock,
                                rationale: "Synthetic mock profile".to_string(),
                                penalty_factors: vec!["synthetic_mock_fixture".to_string()],
                            },
                            payload_sha256:
                                "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
                                    .to_string(),
                            scan_proves_safe: false,
                            is_mock: true,
                        },
                    );
                }
                Ok(CompanionObservationBatchSnapshot {
                    batch_id,
                    timestamp_utc: timestamp,
                    total_observations: 16,
                    observations: map,
                    mean_confidence: 0.35,
                    lowest_confidence_collector: "identity".to_string(),
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
            "unsupported" => {
                for &cid in &MOCK_OBSERVATION_COLLECTORS {
                    map.insert(
                        cid.to_string(),
                        ObservedTelemetryEnvelopeSnapshot {
                            observation_id: format!("obs-{}-unsupported", cid),
                            collector_id: cid.to_string(),
                            source_timestamp: SourceTimestampSnapshot {
                                utc_iso: timestamp.clone(),
                                epoch_ms: 1794916800000,
                                monotonic_ns: None,
                                clock_source: "system_clock_utc".to_string(),
                            },
                            observed_at_utc: timestamp.clone(),
                            latency_ms: 0.5,
                            confidence: ObservationConfidenceSnapshot {
                                score: 0.10,
                                tier: ConfidenceTierSnapshot::EstimatedMock,
                                rationale: "Non-Darwin platform".to_string(),
                                penalty_factors: vec!["platform_unsupported".to_string()],
                            },
                            payload_sha256:
                                "0000000000000000000000000000000000000000000000000000000000000000"
                                    .to_string(),
                            scan_proves_safe: false,
                            is_mock: true,
                        },
                    );
                }
                Ok(CompanionObservationBatchSnapshot {
                    batch_id,
                    timestamp_utc: timestamp,
                    total_observations: 16,
                    observations: map,
                    mean_confidence: 0.10,
                    lowest_confidence_collector: "identity".to_string(),
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
            _ => {
                // high_fidelity mock simulation (strictly is_mock=true)
                for &cid in &MOCK_OBSERVATION_COLLECTORS {
                    map.insert(
                        cid.to_string(),
                        ObservedTelemetryEnvelopeSnapshot {
                            observation_id: format!("obs-{}-high", cid),
                            collector_id: cid.to_string(),
                            source_timestamp: SourceTimestampSnapshot {
                                utc_iso: timestamp.clone(),
                                epoch_ms: 1794916800000,
                                monotonic_ns: Some(55000000),
                                clock_source: "mock_clock".to_string(),
                            },
                            observed_at_utc: timestamp.clone(),
                            latency_ms: 10.0,
                            confidence: ObservationConfidenceSnapshot {
                                score: 0.35,
                                tier: ConfidenceTierSnapshot::EstimatedMock,
                                rationale: format!(
                                    "Simulated high-fidelity mock fixture for {}",
                                    cid
                                ),
                                penalty_factors: vec!["synthetic_mock_fixture".to_string()],
                            },
                            payload_sha256:
                                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
                                    .to_string(),
                            scan_proves_safe: false,
                            is_mock: true,
                        },
                    );
                }
                Ok(CompanionObservationBatchSnapshot {
                    batch_id,
                    timestamp_utc: timestamp,
                    total_observations: 16,
                    observations: map,
                    mean_confidence: 0.35,
                    lowest_confidence_collector: "identity".to_string(),
                    scan_proves_safe: false,
                    is_mock: true,
                })
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_observation_high_fidelity() {
        let collector = MockMacOsObservationCollector::new("high_fidelity");
        let batch = collector
            .collect_batch()
            .expect("collect observation batch");

        assert_eq!(batch.total_observations, 16);
        assert!(!batch.scan_proves_safe); // INV-OBS-05
        assert!(batch.is_mock);

        let cpu_env = batch.observations.get("cpu").expect("cpu observation");
        assert_eq!(cpu_env.collector_id, "cpu");
        assert_eq!(cpu_env.source_timestamp.clock_source, "mock_clock");
        assert_eq!(
            cpu_env.confidence.tier,
            ConfidenceTierSnapshot::EstimatedMock
        );
        assert!(!cpu_env.scan_proves_safe);
        assert!(cpu_env.is_mock);
    }

    #[test]
    fn test_mock_observation_degraded() {
        let collector = MockMacOsObservationCollector::new("degraded");
        let batch = collector.collect_batch().expect("degraded batch");

        assert_eq!(batch.total_observations, 16);
        assert!(batch.is_mock);
        assert_eq!(batch.lowest_confidence_collector, "endpoint_security");

        let es_env = batch.observations.get("endpoint_security").unwrap();
        assert_eq!(es_env.confidence.score, 0.50);
        assert_eq!(
            es_env.confidence.tier,
            ConfidenceTierSnapshot::DegradedPartial
        );
        assert!(es_env.is_mock);
        assert!(es_env
            .confidence
            .penalty_factors
            .contains(&"missing_permission_or_entitlement".to_string()));
    }

    #[test]
    fn test_mock_observation_mock_simulation() {
        let collector = MockMacOsObservationCollector::new("mock_simulation");
        let batch = collector.collect_batch().expect("mock simulation batch");

        assert!(batch.is_mock);
        assert_eq!(batch.mean_confidence, 0.35);

        let any_env = batch.observations.get("storage").unwrap();
        assert_eq!(
            any_env.confidence.tier,
            ConfidenceTierSnapshot::EstimatedMock
        );
        assert_eq!(any_env.source_timestamp.clock_source, "mock_clock");
    }

    #[test]
    fn test_mock_observation_unsupported() {
        let collector = MockMacOsObservationCollector::new("unsupported");
        let batch = collector.collect_batch().expect("unsupported batch");

        assert!(batch.is_mock);
        assert_eq!(batch.mean_confidence, 0.10);
    }

    #[test]
    fn test_scan_proves_safe_invariant() {
        let collector = MockMacOsObservationCollector::default();
        let batch = collector.collect_batch().unwrap();
        assert!(!batch.scan_proves_safe);
    }

    #[test]
    fn test_json_summary_serialization() {
        let collector = MockMacOsObservationCollector::new("high_fidelity");
        let batch = collector.collect_batch().unwrap();
        let summary = batch.to_json_summary();

        assert!(summary.contains("\"total_observations\":16"));
        assert!(summary.contains("\"scan_proves_safe\":false"));
        assert!(summary.contains("\"mean_confidence\":0.350"));
        assert!(summary.contains("\"mock\":true"));
    }
}
