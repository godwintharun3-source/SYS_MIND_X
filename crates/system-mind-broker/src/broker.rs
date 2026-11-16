//! Narrow privileged capability broker enforcing safety preconditions and invariants.

use system_mind_common::{
    compute_payload_fingerprint, ApiStatus, BrokerError, CapabilityId, ComponentOwnership,
    FileTrustState,
};
use system_mind_sensors::{SensorAdapter, SensorSnapshot};

#[derive(Debug, Clone, PartialEq)]
pub struct CapabilityExecutionReceipt {
    pub action_id: String,
    pub capability: CapabilityId,
    pub status: ApiStatus,
    pub fingerprint: String,
    pub duration_ms: f64,
}

pub struct PrivilegedCapabilityBroker {
    sensor_adapter: Box<dyn SensorAdapter>,
}

impl PrivilegedCapabilityBroker {
    pub fn new(sensor_adapter: Box<dyn SensorAdapter>) -> Self {
        Self { sensor_adapter }
    }

    /// Read non-privileged system telemetry snapshot.
    pub fn execute_telemetry_read(&self) -> Result<SensorSnapshot, BrokerError> {
        Ok(self.sensor_adapter.collect_snapshot())
    }

    /// Execute native file launch governed by the "Scan != Safe" invariant.
    pub fn execute_file_launch(
        &self,
        action_id: &str,
        file_path: &str,
        trust_state: FileTrustState,
    ) -> Result<CapabilityExecutionReceipt, BrokerError> {
        // Inviolable Invariant (SC-03 & ADR-030): Scan != Safe.
        // Untrusted, quarantined, or merely scanned files cannot run natively on the host OS.
        if !trust_state.permits_native_host_execution() {
            return Err(BrokerError::precondition_failed(
                format!(
                    "File '{}' with trust state '{:?}' cannot be executed natively on host OS. Quarantined or statically inspected files must run in isolated micro-VM sandboxes.",
                    file_path, trust_state
                ),
                file_path,
                "Promote file trust via verified vendor signature or explicit user attestation.",
            ));
        }

        let fingerprint = compute_payload_fingerprint(file_path.as_bytes());

        Ok(CapabilityExecutionReceipt {
            action_id: action_id.to_string(),
            capability: CapabilityId::FileMetadataRead,
            status: ApiStatus::Success,
            fingerprint,
            duration_ms: 1.5,
        })
    }

    /// Execute component maintenance governed by tripartite ownership rules.
    pub fn execute_maintenance_update(
        &self,
        action_id: &str,
        component_name: &str,
        ownership: ComponentOwnership,
    ) -> Result<CapabilityExecutionReceipt, BrokerError> {
        // Inviolable Invariant (SC-02 & ADR-028): Autonomous maintenance cannot mutate USER_MANAGED components.
        if !ownership.permits_autonomous_mutation() {
            return Err(BrokerError::charter_violation(
                format!(
                    "Autonomous maintenance attempted to mutate '{:?}' component '{}'. User applications and project dependencies require explicit human approval.",
                    ownership, component_name
                ),
                component_name,
            ));
        }

        let fingerprint = compute_payload_fingerprint(component_name.as_bytes());

        Ok(CapabilityExecutionReceipt {
            action_id: action_id.to_string(),
            capability: CapabilityId::PackageUpgrade,
            status: ApiStatus::Success,
            fingerprint,
            duration_ms: 3.2,
        })
    }
}
