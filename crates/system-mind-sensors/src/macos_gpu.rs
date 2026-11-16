//! macOS Darwin GPU and visual display inventory telemetry sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GpuBusTypeState {
    Builtin,
    Pcie,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DisplayConnectionTypeState {
    Internal,
    DisplayPort,
    Hdmi,
    Thunderbolt,
    AirPlay,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsDisplaySnapshot {
    pub name: String,
    pub display_id: Option<String>,
    pub vendor_id: Option<String>,
    pub product_id: Option<String>,
    pub anonymized_serial_hash: Option<String>,
    pub native_pixels: Option<String>,
    pub resolution: Option<String>,
    pub refresh_rate_hz: Option<f32>,
    pub is_main: bool,
    pub is_builtin: bool,
    pub is_online: bool,
    pub connection_type: DisplayConnectionTypeState,
    pub pixel_density_retina: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsGpuInfoSnapshot {
    pub name: String,
    pub vendor: String,
    pub core_count: Option<u32>,
    pub bus_type: GpuBusTypeState,
    pub metal_support: Option<String>,
    pub vram_text: Option<String>,
    pub displays: Vec<MacOsDisplaySnapshot>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsGpuSnapshot {
    pub gpus: Vec<MacOsGpuInfoSnapshot>,
    pub total_gpu_count: usize,
    pub total_display_count: usize,
    pub primary_display_resolution: Option<String>,
    pub has_builtin_display: bool,
    pub has_external_display: bool,
    pub is_mock: bool,
}

impl MacOsGpuSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"total_gpus\":{},\"total_displays\":{},\"primary_res\":{},\"has_builtin\":{},\"has_external\":{},\"mock\":{}}}",
            self.total_gpu_count,
            self.total_display_count,
            self.primary_display_resolution
                .as_ref()
                .map_or("null".to_string(), |r| format!("\"{}\"", r)),
            self.has_builtin_display,
            self.has_external_display,
            self.is_mock
        )
    }
}

pub trait MacOsGpuCollector: Send + Sync {
    fn collect_gpu(&self) -> MacOsGpuSnapshot;
}

/// Safe mock collector simulating macOS GPU hardware and display configuration.
#[derive(Debug, Clone)]
pub struct MockMacOsGpuCollector {
    pub gpus: Vec<MacOsGpuInfoSnapshot>,
    pub is_mock: bool,
}

impl MockMacOsGpuCollector {
    pub fn new_apple_silicon() -> Self {
        let display = MacOsDisplaySnapshot {
            name: "Color LCD".to_string(),
            display_id: Some("1".to_string()),
            vendor_id: Some("610".to_string()),
            product_id: Some("a045".to_string()),
            anonymized_serial_hash: Some("sha256:d17f41a8bc92e01b".to_string()),
            native_pixels: Some("2880 x 1800".to_string()),
            resolution: Some("1440 x 900 @ 60.00Hz".to_string()),
            refresh_rate_hz: Some(60.0),
            is_main: true,
            is_builtin: true,
            is_online: true,
            connection_type: DisplayConnectionTypeState::Internal,
            pixel_density_retina: true,
        };

        let gpu = MacOsGpuInfoSnapshot {
            name: "Apple M1".to_string(),
            vendor: "Apple".to_string(),
            core_count: Some(8),
            bus_type: GpuBusTypeState::Builtin,
            metal_support: Some("spdisplays_metal4".to_string()),
            vram_text: Some("Unified Memory".to_string()),
            displays: vec![display],
        };

        Self {
            gpus: vec![gpu],
            is_mock: true,
        }
    }
}

impl MacOsGpuCollector for MockMacOsGpuCollector {
    fn collect_gpu(&self) -> MacOsGpuSnapshot {
        let total_displays = self.gpus.iter().map(|g| g.displays.len()).sum();
        let has_builtin = self
            .gpus
            .iter()
            .any(|g| g.displays.iter().any(|d| d.is_builtin));
        let has_external = self
            .gpus
            .iter()
            .any(|g| g.displays.iter().any(|d| !d.is_builtin));

        let primary_res = self
            .gpus
            .iter()
            .flat_map(|g| &g.displays)
            .find(|d| d.is_main)
            .and_then(|d| d.resolution.clone());

        MacOsGpuSnapshot {
            total_gpu_count: self.gpus.len(),
            total_display_count: total_displays,
            primary_display_resolution: primary_res,
            has_builtin_display: has_builtin,
            has_external_display: has_external,
            gpus: self.gpus.clone(),
            is_mock: self.is_mock,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_gpu_collector_apple_silicon() {
        let collector = MockMacOsGpuCollector::new_apple_silicon();
        let snapshot = collector.collect_gpu();

        assert_eq!(snapshot.total_gpu_count, 1);
        assert_eq!(snapshot.total_display_count, 1);
        assert!(snapshot.has_builtin_display);
        assert!(!snapshot.has_external_display);
        assert_eq!(
            snapshot.primary_display_resolution.as_deref(),
            Some("1440 x 900 @ 60.00Hz")
        );
        assert!(snapshot.is_mock);

        let gpu = &snapshot.gpus[0];
        assert_eq!(gpu.name, "Apple M1");
        assert_eq!(gpu.vendor, "Apple");
        assert_eq!(gpu.core_count, Some(8));
        assert_eq!(gpu.bus_type, GpuBusTypeState::Builtin);

        let display = &gpu.displays[0];
        assert_eq!(display.name, "Color LCD");
        assert!(display.is_main);
        assert!(display.is_builtin);
        assert_eq!(
            display.connection_type,
            DisplayConnectionTypeState::Internal
        );
        assert!(display.pixel_density_retina);
        assert_eq!(display.refresh_rate_hz, Some(60.0));
    }

    #[test]
    fn test_json_summary_serialization() {
        let collector = MockMacOsGpuCollector::new_apple_silicon();
        let snapshot = collector.collect_gpu();
        let json = snapshot.to_json_summary();

        assert!(json.contains("\"total_gpus\":1"));
        assert!(json.contains("\"total_displays\":1"));
        assert!(json.contains("\"has_builtin\":true"));
        assert!(json.contains("\"mock\":true"));
    }

    #[test]
    fn test_multi_gpu_and_display_aggregation() {
        let d1 = MacOsDisplaySnapshot {
            name: "Color LCD".to_string(),
            display_id: Some("1".to_string()),
            vendor_id: Some("610".to_string()),
            product_id: Some("a045".to_string()),
            anonymized_serial_hash: Some("sha256:1111222233334444".to_string()),
            native_pixels: Some("2880 x 1800".to_string()),
            resolution: Some("1440 x 900 @ 60.00Hz".to_string()),
            refresh_rate_hz: Some(60.0),
            is_main: true,
            is_builtin: true,
            is_online: true,
            connection_type: DisplayConnectionTypeState::Internal,
            pixel_density_retina: true,
        };

        let d2 = MacOsDisplaySnapshot {
            name: "Studio Display".to_string(),
            display_id: Some("2".to_string()),
            vendor_id: Some("610".to_string()),
            product_id: Some("b100".to_string()),
            anonymized_serial_hash: Some("sha256:5555666677778888".to_string()),
            native_pixels: Some("5120 x 2880".to_string()),
            resolution: Some("2560 x 1440 @ 60.00Hz".to_string()),
            refresh_rate_hz: Some(60.0),
            is_main: false,
            is_builtin: false,
            is_online: true,
            connection_type: DisplayConnectionTypeState::Thunderbolt,
            pixel_density_retina: true,
        };

        let gpu = MacOsGpuInfoSnapshot {
            name: "Apple M3 Max".to_string(),
            vendor: "Apple".to_string(),
            core_count: Some(40),
            bus_type: GpuBusTypeState::Builtin,
            metal_support: Some("spdisplays_metal4".to_string()),
            vram_text: Some("128 GB Unified".to_string()),
            displays: vec![d1, d2],
        };

        let collector = MockMacOsGpuCollector {
            gpus: vec![gpu],
            is_mock: false,
        };
        let snapshot = collector.collect_gpu();

        assert_eq!(snapshot.total_gpu_count, 1);
        assert_eq!(snapshot.total_display_count, 2);
        assert!(snapshot.has_builtin_display);
        assert!(snapshot.has_external_display);
    }
}
