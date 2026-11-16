//! SYSTEM MIND X Broker: Narrow privileged capability broker daemon.

pub mod broker;

pub use broker::{CapabilityExecutionReceipt, PrivilegedCapabilityBroker};

#[cfg(test)]
mod tests {
    use super::*;
    use system_mind_common::{ComponentOwnership, FileTrustState};
    use system_mind_sensors::MockSensorAdapter;

    #[test]
    fn test_broker_telemetry_execution() {
        let broker = PrivilegedCapabilityBroker::new(Box::new(MockSensorAdapter::new()));
        let res = broker.execute_telemetry_read().unwrap();
        assert_eq!(res.thermal_state, "NOMINAL");
        assert!(res.cpu_usage_pct >= 0.0);
    }

    #[test]
    fn test_broker_enforces_scan_not_safe_invariant() {
        let broker = PrivilegedCapabilityBroker::new(Box::new(MockSensorAdapter::new()));

        // Quarantined file rejected
        let res_quarantined = broker.execute_file_launch(
            "act-1",
            "/tmp/untrusted.bin",
            FileTrustState::Quarantined,
        );
        assert!(res_quarantined.is_err());
        assert!(res_quarantined.unwrap_err().message.contains("cannot be executed natively"));

        // Statically inspected file still rejected under "Scan != Safe"
        let res_inspected = broker.execute_file_launch(
            "act-2",
            "/tmp/scanned.bin",
            FileTrustState::StaticallyInspected,
        );
        assert!(res_inspected.is_err());

        // Immutable system core binary accepted
        let res_sys = broker.execute_file_launch(
            "act-3",
            "/System/Library/CoreServices/SystemVersion.plist",
            FileTrustState::SystemCoreImmutable,
        );
        assert!(res_sys.is_ok());
    }

    #[test]
    fn test_broker_enforces_user_app_ownership_guard() {
        let broker = PrivilegedCapabilityBroker::new(Box::new(MockSensorAdapter::new()));

        // User application mutation rejected
        let res_user_app = broker.execute_maintenance_update(
            "act-update-1",
            "com.google.Chrome",
            ComponentOwnership::UserManaged,
        );
        assert!(res_user_app.is_err());
        assert!(res_user_app.unwrap_err().message.contains("User applications"));

        // System managed component accepted
        let res_system = broker.execute_maintenance_update(
            "act-update-2",
            "com.apple.SecurityUpdate",
            ComponentOwnership::SystemManaged,
        );
        assert!(res_system.is_ok());
    }
}
