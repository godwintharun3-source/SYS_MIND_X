//! macOS Darwin memory capacity, VM page metrics, swap, and memory pressure collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MemoryPressureState {
    Normal,
    Warn,
    Critical,
    Unknown,
}

impl MemoryPressureState {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Normal => "NORMAL",
            Self::Warn => "WARN",
            Self::Critical => "CRITICAL",
            Self::Unknown => "UNKNOWN",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsMemorySnapshot {
    pub total_bytes: u64,
    pub used_bytes: u64,
    pub free_bytes: u64,
    pub app_bytes: u64,
    pub wired_bytes: u64,
    pub compressed_bytes: u64,
    pub cached_bytes: u64,
    pub swap_total_bytes: u64,
    pub swap_used_bytes: u64,
    pub swap_encrypted: bool,
    pub pressure_state: MemoryPressureState,
    pub pressure_pct: f32,
    pub is_mock: bool,
}

impl MacOsMemorySnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"total\":{},\"used\":{},\"free\":{},\"app\":{},\"wired\":{},\"compressed\":{},\"swap_total\":{},\"swap_used\":{},\"swap_encrypted\":{},\"pressure\":\"{}\",\"pressure_pct\":{:.1},\"mock\":{}}}",
            self.total_bytes,
            self.used_bytes,
            self.free_bytes,
            self.app_bytes,
            self.wired_bytes,
            self.compressed_bytes,
            self.swap_total_bytes,
            self.swap_used_bytes,
            self.swap_encrypted,
            self.pressure_state.as_str(),
            self.pressure_pct,
            self.is_mock
        )
    }
}

pub trait MacOsMemoryCollector: Send + Sync {
    fn collect_memory(&self) -> MacOsMemorySnapshot;
}

/// Safe mock collector simulating macOS Unified Memory metrics and pressure.
#[derive(Debug, Default)]
pub struct MockMacOsMemoryCollector {
    pub simulated_total: u64,
    pub simulated_used: u64,
    pub simulated_pressure: Option<MemoryPressureState>,
    pub simulated_pressure_pct: f32,
}

impl MockMacOsMemoryCollector {
    pub fn new() -> Self {
        Self {
            simulated_total: 8_589_934_592, // 8GB
            simulated_used: 4_831_838_208,  // ~4.5GB
            simulated_pressure: Some(MemoryPressureState::Normal),
            simulated_pressure_pct: 15.0,
        }
    }
}

impl MacOsMemoryCollector for MockMacOsMemoryCollector {
    fn collect_memory(&self) -> MacOsMemorySnapshot {
        let total = self.simulated_total;
        let used = self.simulated_used;
        let app = (used as f64 * 0.55) as u64;
        let wired = (used as f64 * 0.28) as u64;
        let compressed = used.saturating_sub(app + wired);
        let cached = ((total - used) as f64 * 0.55) as u64;
        let free = total.saturating_sub(used + cached);

        MacOsMemorySnapshot {
            total_bytes: total,
            used_bytes: used,
            free_bytes: free,
            app_bytes: app,
            wired_bytes: wired,
            compressed_bytes: compressed,
            cached_bytes: cached,
            swap_total_bytes: 3_221_225_472, // 3GB
            swap_used_bytes: 536_870_912,    // 512MB
            swap_encrypted: true,
            pressure_state: self
                .simulated_pressure
                .unwrap_or(MemoryPressureState::Normal),
            pressure_pct: self.simulated_pressure_pct,
            is_mock: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_macos_memory_collection() {
        let collector = MockMacOsMemoryCollector::new();
        let mem = collector.collect_memory();

        assert_eq!(mem.total_bytes, 8_589_934_592);
        assert_eq!(mem.pressure_state, MemoryPressureState::Normal);
        assert_eq!(mem.pressure_state.as_str(), "NORMAL");
        assert!(mem.swap_encrypted);
        assert!(mem.is_mock);
        assert!(mem.used_bytes > 0);
        assert_eq!(
            mem.app_bytes + mem.wired_bytes + mem.compressed_bytes,
            mem.used_bytes
        );

        let json = mem.to_json_summary();
        assert!(json.contains("\"total\":8589934592"));
        assert!(json.contains("\"pressure\":\"NORMAL\""));
        assert!(json.contains("\"swap_encrypted\":true"));
    }

    #[test]
    fn test_mock_macos_memory_critical_pressure() {
        let mut collector = MockMacOsMemoryCollector::new();
        collector.simulated_pressure = Some(MemoryPressureState::Critical);
        collector.simulated_pressure_pct = 85.5;

        let mem = collector.collect_memory();
        assert_eq!(mem.pressure_state, MemoryPressureState::Critical);
        assert_eq!(mem.pressure_state.as_str(), "CRITICAL");
        assert!((mem.pressure_pct - 85.5).abs() < f32::EPSILON);
    }
}
