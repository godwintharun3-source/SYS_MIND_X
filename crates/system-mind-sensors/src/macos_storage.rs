//! macOS Darwin storage volumes, APFS container hierarchy, and filesystem metadata collector.

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsVolumeSnapshot {
    pub mount_point: String,
    pub device_node: String,
    pub volume_name: String,
    pub filesystem: String,
    pub total_bytes: u64,
    pub used_bytes: u64,
    pub available_bytes: u64,
    pub is_read_only: bool,
    pub is_sealed: bool,
    pub is_encrypted: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsStorageSnapshot {
    pub volumes: Vec<MacOsVolumeSnapshot>,
    pub total_capacity_bytes: u64,
    pub total_available_bytes: u64,
    pub has_filevault: bool,
    pub has_sealed_ssv: bool,
    pub is_mock: bool,
}

impl MacOsStorageSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"volume_count\":{},\"total_capacity\":{},\"total_available\":{},\"filevault\":{},\"ssv_sealed\":{},\"mock\":{}}}",
            self.volumes.len(),
            self.total_capacity_bytes,
            self.total_available_bytes,
            self.has_filevault,
            self.has_sealed_ssv,
            self.is_mock
        )
    }
}

pub trait MacOsStorageCollector: Send + Sync {
    fn collect_storage(&self) -> MacOsStorageSnapshot;
}

/// Safe mock collector simulating macOS APFS container with System (sealed) and Data (FileVault) volumes.
#[derive(Debug, Default)]
pub struct MockMacOsStorageCollector {
    pub simulated_capacity: u64,
    pub simulated_available: u64,
}

impl MockMacOsStorageCollector {
    pub fn new() -> Self {
        Self {
            simulated_capacity: 245_107_195_904, // ~245 GB
            simulated_available: 35_981_094_912, // ~36 GB
        }
    }
}

impl MacOsStorageCollector for MockMacOsStorageCollector {
    fn collect_storage(&self) -> MacOsStorageSnapshot {
        let cap = self.simulated_capacity;
        let avail = self.simulated_available;

        let sys_vol = MacOsVolumeSnapshot {
            mount_point: "/".to_string(),
            device_node: "/dev/disk3s1s1".to_string(),
            volume_name: "Macintosh HD".to_string(),
            filesystem: "apfs".to_string(),
            total_bytes: cap,
            used_bytes: 13_947_080_704,
            available_bytes: avail,
            is_read_only: true,
            is_sealed: true,
            is_encrypted: false,
        };

        let data_vol = MacOsVolumeSnapshot {
            mount_point: "/System/Volumes/Data".to_string(),
            device_node: "/dev/disk3s5".to_string(),
            volume_name: "Data".to_string(),
            filesystem: "apfs".to_string(),
            total_bytes: cap,
            used_bytes: 178_003_226_624,
            available_bytes: avail,
            is_read_only: false,
            is_sealed: false,
            is_encrypted: true,
        };

        MacOsStorageSnapshot {
            volumes: vec![sys_vol, data_vol],
            total_capacity_bytes: cap,
            total_available_bytes: avail,
            has_filevault: true,
            has_sealed_ssv: true,
            is_mock: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_macos_storage_collection() {
        let collector = MockMacOsStorageCollector::new();
        let storage = collector.collect_storage();

        assert_eq!(storage.volumes.len(), 2);
        assert_eq!(storage.total_capacity_bytes, 245_107_195_904);
        assert_eq!(storage.total_available_bytes, 35_981_094_912);
        assert!(storage.has_filevault);
        assert!(storage.has_sealed_ssv);
        assert!(storage.is_mock);

        let sys_vol = &storage.volumes[0];
        assert_eq!(sys_vol.mount_point, "/");
        assert!(sys_vol.is_read_only);
        assert!(sys_vol.is_sealed);

        let data_vol = &storage.volumes[1];
        assert_eq!(data_vol.mount_point, "/System/Volumes/Data");
        assert!(!data_vol.is_read_only);
        assert!(data_vol.is_encrypted);
    }

    #[test]
    fn test_mock_macos_storage_json_serialization() {
        let collector = MockMacOsStorageCollector::new();
        let storage = collector.collect_storage();
        let json = storage.to_json_summary();

        assert!(json.contains("\"volume_count\":2"));
        assert!(json.contains("\"filevault\":true"));
        assert!(json.contains("\"ssv_sealed\":true"));
        assert!(json.contains("\"mock\":true"));
    }

    #[test]
    fn test_mock_macos_storage_capacity_sum() {
        let collector = MockMacOsStorageCollector::new();
        let storage = collector.collect_storage();
        assert!(storage.total_capacity_bytes > storage.total_available_bytes);
        assert!(!storage.volumes.is_empty());
    }
}
