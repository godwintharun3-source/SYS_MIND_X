//! macOS Darwin CPU topology, core counts, and compute hardware collector.

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsCpuSnapshot {
    pub cpu_brand: String,
    pub hardware_model: String,
    pub physical_cores: u32,
    pub logical_cores: u32,
    pub performance_cores: u32,
    pub efficiency_cores: u32,
    pub num_perf_levels: u32,
    pub cache_line_size: u32,
    pub l1i_cache_bytes: u64,
    pub l1d_cache_bytes: u64,
    pub l2_cache_bytes: u64,
    pub timebase_freq_hz: u64,
    pub page_size_bytes: u32,
    pub total_memory_bytes: u64,
    pub has_neon: bool,
    pub has_floating_point: bool,
    pub is_heterogeneous: bool,
    pub is_mock: bool,
}

impl MacOsCpuSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"cpu_brand\":\"{}\",\"model\":\"{}\",\"physical_cores\":{},\"logical_cores\":{},\"p_cores\":{},\"e_cores\":{},\"cache_line\":{},\"page_size\":{},\"neon\":{},\"fp\":{},\"heterogeneous\":{},\"mock\":{}}}",
            self.cpu_brand,
            self.hardware_model,
            self.physical_cores,
            self.logical_cores,
            self.performance_cores,
            self.efficiency_cores,
            self.cache_line_size,
            self.page_size_bytes,
            self.has_neon,
            self.has_floating_point,
            self.is_heterogeneous,
            self.is_mock
        )
    }
}

pub trait MacOsCpuCollector: Send + Sync {
    fn collect_cpu(&self) -> MacOsCpuSnapshot;
}

/// Safe mock collector simulating Apple Silicon CPU compute hardware.
#[derive(Debug, Default)]
pub struct MockMacOsCpuCollector {
    pub simulated_brand: String,
    pub simulated_model: String,
    pub simulated_cores: u32,
    pub simulated_p_cores: u32,
    pub simulated_e_cores: u32,
}

impl MockMacOsCpuCollector {
    pub fn new() -> Self {
        Self {
            simulated_brand: "Apple M1".to_string(),
            simulated_model: "MacBookAir10,1".to_string(),
            simulated_cores: 8,
            simulated_p_cores: 4,
            simulated_e_cores: 4,
        }
    }
}

impl MacOsCpuCollector for MockMacOsCpuCollector {
    fn collect_cpu(&self) -> MacOsCpuSnapshot {
        MacOsCpuSnapshot {
            cpu_brand: self.simulated_brand.clone(),
            hardware_model: self.simulated_model.clone(),
            physical_cores: self.simulated_cores,
            logical_cores: self.simulated_cores,
            performance_cores: self.simulated_p_cores,
            efficiency_cores: self.simulated_e_cores,
            num_perf_levels: if self.simulated_e_cores > 0 { 2 } else { 1 },
            cache_line_size: 128,
            l1i_cache_bytes: 131072,
            l1d_cache_bytes: 65536,
            l2_cache_bytes: 4194304,
            timebase_freq_hz: 24_000_000,
            page_size_bytes: 16384,
            total_memory_bytes: 8_589_934_592,
            has_neon: true,
            has_floating_point: true,
            is_heterogeneous: self.simulated_p_cores > 0 && self.simulated_e_cores > 0,
            is_mock: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_macos_cpu_collection() {
        let collector = MockMacOsCpuCollector::new();
        let cpu = collector.collect_cpu();

        assert_eq!(cpu.cpu_brand, "Apple M1");
        assert_eq!(cpu.hardware_model, "MacBookAir10,1");
        assert_eq!(cpu.physical_cores, 8);
        assert_eq!(cpu.performance_cores, 4);
        assert_eq!(cpu.efficiency_cores, 4);
        assert_eq!(cpu.num_perf_levels, 2);
        assert_eq!(cpu.cache_line_size, 128);
        assert_eq!(cpu.page_size_bytes, 16384);
        assert!(cpu.has_neon);
        assert!(cpu.has_floating_point);
        assert!(cpu.is_heterogeneous);
        assert!(cpu.is_mock);

        let json = cpu.to_json_summary();
        assert!(json.contains("\"cpu_brand\":\"Apple M1\""));
        assert!(json.contains("\"p_cores\":4"));
        assert!(json.contains("\"e_cores\":4"));
        assert!(json.contains("\"heterogeneous\":true"));
    }

    #[test]
    fn test_mock_macos_cpu_symmetric_simulation() {
        let mut collector = MockMacOsCpuCollector::new();
        collector.simulated_brand = "Intel Core i9".to_string();
        collector.simulated_p_cores = 8;
        collector.simulated_e_cores = 0;

        let cpu = collector.collect_cpu();
        assert_eq!(cpu.cpu_brand, "Intel Core i9");
        assert_eq!(cpu.num_perf_levels, 1);
        assert!(!cpu.is_heterogeneous);
    }
}
