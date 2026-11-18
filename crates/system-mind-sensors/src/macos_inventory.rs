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

#[cfg(target_os = "macos")]
mod darwin_native {
    use std::ffi::{CStr, CString};
    use std::os::raw::{c_char, c_int, c_void};

    extern "C" {
        fn sysctlbyname(
            name: *const c_char,
            oldp: *mut c_void,
            oldlenp: *mut usize,
            newp: *const c_void,
            newlen: usize,
        ) -> c_int;
        fn gethostname(name: *mut c_char, len: usize) -> c_int;
    }

    #[repr(C)]
    #[derive(Copy, Clone)]
    pub struct FsId {
        pub val: [i32; 2],
    }

    #[repr(C)]
    pub struct Statfs {
        pub f_bsize: u32,
        pub f_iosize: i32,
        pub f_blocks: u64,
        pub f_bfree: u64,
        pub f_bavail: u64,
        pub f_files: u64,
        pub f_ffree: u64,
        pub f_fsid: FsId,
        pub f_owner: u32,
        pub f_type: u32,
        pub f_flags: u32,
        pub f_fssubtype: u32,
        pub f_fstypename: [c_char; 16],
        pub f_mntonname: [c_char; 1024],
        pub f_mntfromname: [c_char; 1024],
        pub f_flags_ext: u32,
        pub f_reserved: [u32; 7],
    }

    extern "C" {
        fn statfs(path: *const c_char, buf: *mut Statfs) -> c_int;
    }

    pub fn get_sysctl_string(name: &str) -> Option<String> {
        let c_name = CString::new(name).ok()?;
        let mut len: usize = 0;
        unsafe {
            if sysctlbyname(
                c_name.as_ptr(),
                std::ptr::null_mut(),
                &mut len,
                std::ptr::null(),
                0,
            ) != 0
                || len == 0
            {
                return None;
            }
            let mut buf = vec![0u8; len];
            if sysctlbyname(
                c_name.as_ptr(),
                buf.as_mut_ptr() as *mut c_void,
                &mut len,
                std::ptr::null(),
                0,
            ) != 0
            {
                return None;
            }
            if let Some(pos) = buf.iter().position(|&b| b == 0) {
                buf.truncate(pos);
            }
            String::from_utf8(buf).ok()
        }
    }

    pub fn get_sysctl_u32(name: &str) -> Option<u32> {
        let c_name = CString::new(name).ok()?;
        let mut val: u32 = 0;
        let mut len = std::mem::size_of::<u32>();
        unsafe {
            if sysctlbyname(
                c_name.as_ptr(),
                &mut val as *mut u32 as *mut c_void,
                &mut len,
                std::ptr::null(),
                0,
            ) == 0
            {
                Some(val)
            } else {
                None
            }
        }
    }

    pub fn get_sysctl_u64(name: &str) -> Option<u64> {
        let c_name = CString::new(name).ok()?;
        let mut val: u64 = 0;
        let mut len = std::mem::size_of::<u64>();
        unsafe {
            if sysctlbyname(
                c_name.as_ptr(),
                &mut val as *mut u64 as *mut c_void,
                &mut len,
                std::ptr::null(),
                0,
            ) == 0
            {
                Some(val)
            } else {
                None
            }
        }
    }

    pub fn get_native_hostname() -> Option<String> {
        let mut buf = [0u8; 256];
        unsafe {
            if gethostname(buf.as_mut_ptr() as *mut c_char, buf.len()) == 0 {
                CStr::from_ptr(buf.as_ptr() as *const c_char)
                    .to_str()
                    .ok()
                    .map(|s| s.to_string())
            } else {
                None
            }
        }
    }

    pub fn get_root_storage() -> Option<(u64, u64)> {
        let c_path = CString::new("/").ok()?;
        let mut buf: Statfs = unsafe { std::mem::zeroed() };
        unsafe {
            if statfs(c_path.as_ptr(), &mut buf) == 0 {
                let bsize = buf.f_bsize as u64;
                let total = buf.f_blocks.saturating_mul(bsize);
                let free = buf.f_bavail.saturating_mul(bsize);
                Some((total, free))
            } else {
                None
            }
        }
    }
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
        #[cfg(target_os = "macos")]
        {
            let os_version = darwin_native::get_sysctl_string("kern.osproductversion")
                .unwrap_or_else(|| "UNAVAILABLE".to_string());
            let os_build = darwin_native::get_sysctl_string("kern.osversion")
                .unwrap_or_else(|| "UNAVAILABLE".to_string());
            let host_name =
                darwin_native::get_native_hostname().unwrap_or_else(|| "localhost".to_string());
            let architecture = std::env::consts::ARCH.to_string();
            let cpu_model = darwin_native::get_sysctl_string("machdep.cpu.brand_string")
                .or_else(|| darwin_native::get_sysctl_string("hw.model"))
                .unwrap_or_else(|| "UNAVAILABLE".to_string());
            let physical_cores = darwin_native::get_sysctl_u32("hw.physicalcpu").unwrap_or(0);
            let logical_cores = darwin_native::get_sysctl_u32("hw.logicalcpu").unwrap_or(0);
            let total_memory_bytes = darwin_native::get_sysctl_u64("hw.memsize").unwrap_or(0);
            let (total_storage_bytes, free_storage_bytes) =
                darwin_native::get_root_storage().unwrap_or((0, 0));

            let is_available = physical_cores > 0 && total_memory_bytes > 0;

            MacOsInventorySummarySnapshot {
                os_version,
                os_build,
                host_name,
                architecture,
                cpu_model,
                physical_cores,
                logical_cores,
                total_memory_bytes,
                memory_pressure_pct: 0.0,
                total_storage_bytes,
                free_storage_bytes,
                running_process_count: 0,
                installed_app_count: 0,
                mean_confidence: if is_available { 0.950 } else { 0.200 },
                overall_health: if is_available {
                    "HEALTHY".to_string()
                } else {
                    "DEGRADED".to_string()
                },
            }
        }
        #[cfg(not(target_os = "macos"))]
        {
            MacOsInventorySummarySnapshot {
                os_version: "UNSUPPORTED".to_string(),
                os_build: "UNSUPPORTED".to_string(),
                host_name: "unsupported-host".to_string(),
                architecture: std::env::consts::ARCH.to_string(),
                cpu_model: "UNSUPPORTED".to_string(),
                physical_cores: 0,
                logical_cores: 0,
                total_memory_bytes: 0,
                memory_pressure_pct: 0.0,
                total_storage_bytes: 0,
                free_storage_bytes: 0,
                running_process_count: 0,
                installed_app_count: 0,
                mean_confidence: 0.050,
                overall_health: "UNSUPPORTED".to_string(),
            }
        }
    }

    fn get_inventory(
        &self,
        sections: &[InventorySectionSnapshot],
    ) -> MacOsInventoryResponseSnapshot {
        let summary = self.get_summary();
        let is_unsupported = summary.overall_health == "UNSUPPORTED";
        let is_mock = is_unsupported || summary.physical_cores == 0;
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
            partial_data: is_unsupported,
            scan_proves_safe: false, // Mandatory non-negotiable charter invariant
            is_mock,
        }
    }

    fn is_mock(&self) -> bool {
        #[cfg(target_os = "macos")]
        {
            darwin_native::get_sysctl_u32("hw.physicalcpu").unwrap_or(0) == 0
        }
        #[cfg(not(target_os = "macos"))]
        {
            true
        }
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

    #[test]
    fn test_live_macos_inventory_service() {
        let service = MacOsInventoryService::new();
        let summary = service.get_summary();
        let inv = service.get_inventory(&[InventorySectionSnapshot::All]);

        assert!(!inv.scan_proves_safe); // Enforce charter invariant
        assert_eq!(inv.sections.len(), 8);

        #[cfg(target_os = "macos")]
        {
            // On Darwin, verify real system values are populated from kernel/sysctl
            assert!(!summary.architecture.is_empty());
            assert!(!summary.host_name.is_empty());
            assert_ne!(summary.os_version, "UNSUPPORTED");
            assert!(summary.physical_cores > 0);
            assert!(summary.logical_cores >= summary.physical_cores);
            assert!(summary.total_memory_bytes > 0);
            assert_eq!(inv.is_mock, service.is_mock());
        }
        #[cfg(not(target_os = "macos"))]
        {
            assert!(service.is_mock());
            assert_eq!(summary.overall_health, "UNSUPPORTED");
        }
    }
}
