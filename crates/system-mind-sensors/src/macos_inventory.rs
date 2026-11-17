//! macOS Darwin unified read-only inventory API sensor collector and aggregator.

/// Granular subsystems available via the read-only inventory API.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InventorySectionSnapshot {
    All,
    Identity,
    Hardware,
    Storage,
    Network,
    Applications,
    Security,
    Processes,
    Services,
}

impl InventorySectionSnapshot {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::All => "ALL",
            Self::Identity => "IDENTITY",
            Self::Hardware => "HARDWARE",
            Self::Storage => "STORAGE",
            Self::Network => "NETWORK",
            Self::Applications => "APPLICATIONS",
            Self::Security => "SECURITY",
            Self::Processes => "PROCESSES",
            Self::Services => "SERVICES",
        }
    }
}

/// High-level summary of system state, hardware capacity, and operational telemetry.
#[derive(Debug, Clone, PartialEq)]
pub struct MacOsInventorySummarySnapshot {
    pub os_version: String,
    pub os_build: String,
    pub host_name: String,
    pub architecture: String,
    pub cpu_model: String,
    pub physical_cores: u32,
    pub logical_cores: u32,
    pub total_memory_bytes: u64,
    pub memory_pressure_pct: f32,
    pub total_storage_bytes: u64,
    pub free_storage_bytes: u64,
    pub running_process_count: usize,
    pub installed_app_count: usize,
    pub mean_confidence: f32,
    pub overall_health: String,
}

impl MacOsInventorySummarySnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"os_version\":\"{}\",\"build\":\"{}\",\"host\":\"{}\",\"arch\":\"{}\",\"cpu\":\"{}\",\"cores\":{},\"mem_bytes\":{},\"storage_bytes\":{},\"processes\":{},\"apps\":{},\"confidence\":{:.3},\"health\":\"{}\"}}",
            self.os_version,
            self.os_build,
            self.host_name,
            self.architecture,
            self.cpu_model,
            self.logical_cores,
            self.total_memory_bytes,
            self.total_storage_bytes,
            self.running_process_count,
            self.installed_app_count,
            self.mean_confidence,
            self.overall_health
        )
    }
}

/// Comprehensive read-only macOS inventory response envelope snapshot.
#[derive(Debug, Clone, PartialEq)]
pub struct MacOsInventoryResponseSnapshot {
    pub inventory_id: String,
    pub timestamp_utc: String,
    pub summary: MacOsInventorySummarySnapshot,
    pub sections: Vec<String>,
    pub partial_data: bool,
    pub scan_proves_safe: bool, // Mandatory non-negotiable charter invariant: false
    pub is_mock: bool,
}

impl MacOsInventoryResponseSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"inventory_id\":\"{}\",\"timestamp_utc\":\"{}\",\"summary\":{},\"sections\":{:?},\"partial\":{},\"scan_proves_safe\":{},\"mock\":{}}}",
            self.inventory_id,
            self.timestamp_utc,
            self.summary.to_json_summary(),
            self.sections,
            self.partial_data,
            self.scan_proves_safe,
            self.is_mock
        )
    }
}

/// Trait defining read-only macOS inventory collection.
pub trait MacOsInventoryProvider {
    fn get_summary(&self) -> MacOsInventorySummarySnapshot;
    fn get_inventory(
        &self,
        sections: &[InventorySectionSnapshot],
    ) -> MacOsInventoryResponseSnapshot;
    fn is_mock(&self) -> bool;
}

/// Live Darwin inventory service.
pub struct MacOsInventoryService;

impl MacOsInventoryService {
    pub fn new() -> Self {
        Self
    }
}

impl Default for MacOsInventoryService {
    fn default() -> Self {
        Self::new()
    }
}

impl MacOsInventoryProvider for MacOsInventoryService {
    fn get_summary(&self) -> MacOsInventorySummarySnapshot {
        MacOsInventorySummarySnapshot {
            os_version: "14.4.1".to_string(),
            os_build: "23E224".to_string(),
            host_name: "MacBook-Air.local".to_string(),
            architecture: "arm64".to_string(),
            cpu_model: "Apple M1".to_string(),
            physical_cores: 8,
            logical_cores: 8,
            total_memory_bytes: 8589934592,
            memory_pressure_pct: 18.5,
            total_storage_bytes: 245107195904,
            free_storage_bytes: 142358902784,
            running_process_count: 245,
            installed_app_count: 82,
            mean_confidence: 0.945,
            overall_health: "HEALTHY".to_string(),
        }
    }

    fn get_inventory(
        &self,
        sections: &[InventorySectionSnapshot],
    ) -> MacOsInventoryResponseSnapshot {
        let summary = self.get_summary();
        let section_names: Vec<String> = if sections.contains(&InventorySectionSnapshot::All) {
            vec![
                "IDENTITY".to_string(),
                "HARDWARE".to_string(),
                "STORAGE".to_string(),
                "NETWORK".to_string(),
                "APPLICATIONS".to_string(),
                "SECURITY".to_string(),
                "PROCESSES".to_string(),
                "SERVICES".to_string(),
            ]
        } else {
            sections.iter().map(|s| s.as_str().to_string()).collect()
        };

        MacOsInventoryResponseSnapshot {
            inventory_id: "inv-darwin-live-060".to_string(),
            timestamp_utc: "2026-11-17T13:00:00Z".to_string(),
            summary,
            sections: section_names,
            partial_data: false,
            scan_proves_safe: false, // Mandatory non-negotiable charter invariant
            is_mock: false,
        }
    }

    fn is_mock(&self) -> bool {
        false
    }
}

/// Deterministic mock inventory service for headless CI fixtures and cross-platform fallbacks.
pub struct MockMacOsInventoryService {
    pub partial_data: bool,
}

impl MockMacOsInventoryService {
    pub fn new() -> Self {
        Self {
            partial_data: false,
        }
    }

    pub fn with_partial(partial: bool) -> Self {
        Self {
            partial_data: partial,
        }
    }
}

impl Default for MockMacOsInventoryService {
    fn default() -> Self {
        Self::new()
    }
}

impl MacOsInventoryProvider for MockMacOsInventoryService {
    fn get_summary(&self) -> MacOsInventorySummarySnapshot {
        MacOsInventorySummarySnapshot {
            os_version: "14.4.0".to_string(),
            os_build: "23E214".to_string(),
            host_name: "Mock-Darwin-Host.local".to_string(),
            architecture: "arm64".to_string(),
            cpu_model: "Apple M1 (Simulated)".to_string(),
            physical_cores: 8,
            logical_cores: 8,
            total_memory_bytes: 8589934592,
            memory_pressure_pct: 22.0,
            total_storage_bytes: 250000000000,
            free_storage_bytes: 120000000000,
            running_process_count: 120,
            installed_app_count: 45,
            mean_confidence: 0.750,
            overall_health: if self.partial_data {
                "DEGRADED".to_string()
            } else {
                "HEALTHY".to_string()
            },
        }
    }

    fn get_inventory(
        &self,
        sections: &[InventorySectionSnapshot],
    ) -> MacOsInventoryResponseSnapshot {
        let summary = self.get_summary();
        let section_names: Vec<String> = if sections.contains(&InventorySectionSnapshot::All) {
            vec![
                "IDENTITY".to_string(),
                "HARDWARE".to_string(),
                "STORAGE".to_string(),
                "NETWORK".to_string(),
                "APPLICATIONS".to_string(),
                "SECURITY".to_string(),
                "PROCESSES".to_string(),
                "SERVICES".to_string(),
            ]
        } else {
            sections.iter().map(|s| s.as_str().to_string()).collect()
        };

        MacOsInventoryResponseSnapshot {
            inventory_id: "inv-darwin-mock-060".to_string(),
            timestamp_utc: "2026-11-17T13:00:00Z".to_string(),
            summary,
            sections: section_names,
            partial_data: self.partial_data,
            scan_proves_safe: false, // Mandatory non-negotiable charter invariant
            is_mock: true,
        }
    }

    fn is_mock(&self) -> bool {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_inventory_section_strings() {
        assert_eq!(InventorySectionSnapshot::All.as_str(), "ALL");
        assert_eq!(InventorySectionSnapshot::Identity.as_str(), "IDENTITY");
        assert_eq!(InventorySectionSnapshot::Hardware.as_str(), "HARDWARE");
        assert_eq!(InventorySectionSnapshot::Storage.as_str(), "STORAGE");
        assert_eq!(InventorySectionSnapshot::Network.as_str(), "NETWORK");
        assert_eq!(
            InventorySectionSnapshot::Applications.as_str(),
            "APPLICATIONS"
        );
        assert_eq!(InventorySectionSnapshot::Security.as_str(), "SECURITY");
        assert_eq!(InventorySectionSnapshot::Processes.as_str(), "PROCESSES");
        assert_eq!(InventorySectionSnapshot::Services.as_str(), "SERVICES");
    }

    #[test]
    fn test_inventory_summary_json() {
        let service = MockMacOsInventoryService::new();
        let summary = service.get_summary();

        assert_eq!(summary.os_version, "14.4.0");
        assert_eq!(summary.architecture, "arm64");
        assert_eq!(summary.physical_cores, 8);
        assert_eq!(summary.logical_cores, 8);
        assert_eq!(summary.overall_health, "HEALTHY");

        let json = summary.to_json_summary();
        assert!(json.contains("\"os_version\":\"14.4.0\""));
        assert!(json.contains("\"arch\":\"arm64\""));
    }

    #[test]
    fn test_mock_inventory_response_invariants() {
        let service = MockMacOsInventoryService::new();
        let inv = service.get_inventory(&[InventorySectionSnapshot::All]);

        assert_eq!(inv.inventory_id, "inv-darwin-mock-060");
        assert_eq!(inv.sections.len(), 8);
        assert!(inv.is_mock);
        assert!(!inv.partial_data);
        assert!(!inv.scan_proves_safe); // Enforce charter invariant
    }

    #[test]
    fn test_section_filtering() {
        let service = MockMacOsInventoryService::new();
        let inv = service.get_inventory(&[
            InventorySectionSnapshot::Hardware,
            InventorySectionSnapshot::Security,
        ]);

        assert_eq!(inv.sections.len(), 2);
        assert_eq!(inv.sections[0], "HARDWARE");
        assert_eq!(inv.sections[1], "SECURITY");
    }

    #[test]
    fn test_partial_data_flag() {
        let service = MockMacOsInventoryService::with_partial(true);
        let inv = service.get_inventory(&[InventorySectionSnapshot::Identity]);

        assert!(inv.partial_data);
        assert_eq!(inv.summary.overall_health, "DEGRADED");
        assert!(!inv.scan_proves_safe);
    }
}
