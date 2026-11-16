//! End-to-end integration test for the Rust capability broker and native sensor subsystem.

use system_mind_broker::PrivilegedCapabilityBroker;
use system_mind_common::{ApiStatus, CapabilityId, ComponentOwnership, ErrorCode, FileTrustState};
use system_mind_sensors::{MockSensorAdapter, SensorAdapter};

#[test]
fn test_broker_sensor_pipeline_integration() {
    // 1. Collect hardware telemetry through MockSensorAdapter
    let adapter = MockSensorAdapter::new();
    let snapshot = adapter.collect_snapshot();

    assert!(snapshot.os_platform.contains("macOS"));
    assert!(snapshot.cpu_usage_pct >= 0.0);
    assert!(snapshot.memory_rss_bytes > 0);
    assert_eq!(snapshot.thermal_state, "NOMINAL");

    // 2. Authorize telemetry inspection through PrivilegedCapabilityBroker
    let broker = PrivilegedCapabilityBroker::new(Box::new(adapter));
    let telemetry_res = broker.execute_telemetry_read();

    assert!(
        telemetry_res.is_ok(),
        "Telemetry read through broker must succeed"
    );
    let tele_snapshot = telemetry_res.unwrap();
    assert_eq!(tele_snapshot.thermal_state, "NOMINAL");
    assert!(tele_snapshot.os_platform.contains("macOS"));
}

#[test]
fn test_broker_rejects_quarantined_payload_execution() {
    let broker = PrivilegedCapabilityBroker::new(Box::new(MockSensorAdapter::new()));

    // Inviolable invariant SC-03: Scan != Safe
    let result = broker.execute_file_launch(
        "act-quarantine-test",
        "/tmp/untrusted_sample.bin",
        FileTrustState::Quarantined, // Quarantined payload must NOT execute!
    );

    assert!(
        result.is_err(),
        "Broker must reject execution request for Quarantined payload"
    );
    let err = result.err().unwrap();
    assert_eq!(err.code, ErrorCode::E3001PreconditionFailed);
    assert!(err.message.contains("cannot be executed natively"));
}

#[test]
fn test_broker_blocks_unauthorized_user_app_mutation() {
    let broker = PrivilegedCapabilityBroker::new(Box::new(MockSensorAdapter::new()));

    // Charter Invariant: USER_MANAGED components cannot be mutated autonomously
    let result = broker.execute_maintenance_update(
        "act-user-app-test",
        "com.google.Chrome",
        ComponentOwnership::UserManaged, // User managed app!
    );

    assert!(
        result.is_err(),
        "Broker must block autonomous mutation of UserManaged components"
    );
    let err = result.err().unwrap();
    assert_eq!(err.code, ErrorCode::E2001CharterInvariantBreach);
    assert!(err.message.contains("User applications"));
}

#[test]
fn test_broker_executes_immutable_system_core_action() {
    let broker = PrivilegedCapabilityBroker::new(Box::new(MockSensorAdapter::new()));

    let result = broker.execute_file_launch(
        "act-sys-core-test",
        "/System/Library/CoreServices/SystemVersion.plist",
        FileTrustState::SystemCoreImmutable,
    );

    assert!(
        result.is_ok(),
        "System core immutable file launch must succeed"
    );
    let receipt = result.unwrap();
    assert_eq!(receipt.action_id, "act-sys-core-test");
    assert_eq!(receipt.capability, CapabilityId::FileMetadataRead);
    assert_eq!(receipt.status, ApiStatus::Success);
    assert_eq!(receipt.fingerprint.len(), 16);
}
