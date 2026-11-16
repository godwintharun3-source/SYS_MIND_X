//! macOS Darwin USB and peripheral inventory telemetry sensor collector with privacy constraints.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UsbDeviceClassState {
    Hub,
    HumanInterface,
    SecurityToken,
    MassStorage,
    AudioVideo,
    Communications,
    Wireless,
    Printer,
    Other,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UsbSpeedState {
    LowSpeed1_5Mbps,
    FullSpeed12Mbps,
    HighSpeed480Mbps,
    SuperSpeed5Gbps,
    SuperSpeedPlus10Gbps,
    SuperSpeedPlus20Gbps,
    Usb4_40Gbps,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsUsbDeviceSnapshot {
    pub name: String,
    pub vendor_id: Option<String>,
    pub product_id: Option<String>,
    pub manufacturer: Option<String>,
    pub anonymized_serial_hash: Option<String>,
    pub device_class: UsbDeviceClassState,
    pub speed: UsbSpeedState,
    pub location_id: Option<String>,
    pub bus_power_ma: Option<u32>,
    pub current_used_ma: Option<u32>,
    pub is_builtin: bool,
    pub is_hub: bool,
    pub children: Vec<MacOsUsbDeviceSnapshot>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsUsbControllerSnapshot {
    pub name: String,
    pub host_controller: Option<String>,
    pub devices: Vec<MacOsUsbDeviceSnapshot>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsUsbSnapshot {
    pub controllers: Vec<MacOsUsbControllerSnapshot>,
    pub total_controller_count: usize,
    pub total_device_count: usize,
    pub has_external_devices: bool,
    pub has_security_tokens: bool,
    pub has_mass_storage: bool,
    pub is_mock: bool,
}

impl MacOsUsbSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"controllers\":{},\"total_devices\":{},\"external\":{},\"security_tokens\":{},\"mass_storage\":{},\"mock\":{}}}",
            self.total_controller_count,
            self.total_device_count,
            self.has_external_devices,
            self.has_security_tokens,
            self.has_mass_storage,
            self.is_mock
        )
    }
}

pub trait MacOsUsbCollector: Send + Sync {
    fn collect_usb(&self) -> MacOsUsbSnapshot;
}

fn count_devices_recursive(devices: &[MacOsUsbDeviceSnapshot]) -> usize {
    let mut count = devices.len();
    for d in devices {
        if !d.children.is_empty() {
            count += count_devices_recursive(&d.children);
        }
    }
    count
}

fn check_has_external(devices: &[MacOsUsbDeviceSnapshot]) -> bool {
    devices
        .iter()
        .any(|d| !d.is_builtin || check_has_external(&d.children))
}

fn check_has_class(devices: &[MacOsUsbDeviceSnapshot], target: UsbDeviceClassState) -> bool {
    devices
        .iter()
        .any(|d| d.device_class == target || check_has_class(&d.children, target))
}

/// Safe mock collector simulating macOS USB host controllers and peripherals.
#[derive(Debug, Clone)]
pub struct MockMacOsUsbCollector {
    pub controllers: Vec<MacOsUsbControllerSnapshot>,
    pub is_mock: bool,
}

impl MockMacOsUsbCollector {
    pub fn new_apple_silicon() -> Self {
        let keyboard = MacOsUsbDeviceSnapshot {
            name: "Apple Internal Keyboard / Trackpad".to_string(),
            vendor_id: Some("0x05ac".to_string()),
            product_id: Some("0x027c".to_string()),
            manufacturer: Some("Apple Inc.".to_string()),
            anonymized_serial_hash: Some("sha256:e3b0c44298fc1c14".to_string()),
            device_class: UsbDeviceClassState::HumanInterface,
            speed: UsbSpeedState::FullSpeed12Mbps,
            location_id: Some("0x01100000 / 1".to_string()),
            bus_power_ma: Some(500),
            current_used_ma: Some(40),
            is_builtin: true,
            is_hub: false,
            children: Vec::new(),
        };

        let camera = MacOsUsbDeviceSnapshot {
            name: "FaceTime HD Camera".to_string(),
            vendor_id: Some("0x05ac".to_string()),
            product_id: Some("0x8514".to_string()),
            manufacturer: Some("Apple Inc.".to_string()),
            anonymized_serial_hash: Some("sha256:56789abcdef01234".to_string()),
            device_class: UsbDeviceClassState::AudioVideo,
            speed: UsbSpeedState::HighSpeed480Mbps,
            location_id: Some("0x01200000 / 2".to_string()),
            bus_power_ma: Some(500),
            current_used_ma: Some(200),
            is_builtin: true,
            is_hub: false,
            children: Vec::new(),
        };

        let controller = MacOsUsbControllerSnapshot {
            name: "USB 3.1 Bus".to_string(),
            host_controller: Some("AppleSynopsysUSB40XHCI".to_string()),
            devices: vec![keyboard, camera],
        };

        Self {
            controllers: vec![controller],
            is_mock: true,
        }
    }
}

impl MacOsUsbCollector for MockMacOsUsbCollector {
    fn collect_usb(&self) -> MacOsUsbSnapshot {
        let total_devices: usize = self
            .controllers
            .iter()
            .map(|c| count_devices_recursive(&c.devices))
            .sum();

        let has_external = self
            .controllers
            .iter()
            .any(|c| check_has_external(&c.devices));

        let has_security = self
            .controllers
            .iter()
            .any(|c| check_has_class(&c.devices, UsbDeviceClassState::SecurityToken));

        let has_storage = self
            .controllers
            .iter()
            .any(|c| check_has_class(&c.devices, UsbDeviceClassState::MassStorage));

        MacOsUsbSnapshot {
            total_controller_count: self.controllers.len(),
            total_device_count: total_devices,
            has_external_devices: has_external,
            has_security_tokens: has_security,
            has_mass_storage: has_storage,
            controllers: self.controllers.clone(),
            is_mock: self.is_mock,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_usb_collector_apple_silicon() {
        let collector = MockMacOsUsbCollector::new_apple_silicon();
        let snapshot = collector.collect_usb();

        assert_eq!(snapshot.total_controller_count, 1);
        assert_eq!(snapshot.total_device_count, 2);
        assert!(!snapshot.has_external_devices);
        assert!(!snapshot.has_security_tokens);
        assert!(!snapshot.has_mass_storage);
        assert!(snapshot.is_mock);

        let ctrl = &snapshot.controllers[0];
        assert_eq!(ctrl.name, "USB 3.1 Bus");
        assert_eq!(
            ctrl.host_controller.as_deref(),
            Some("AppleSynopsysUSB40XHCI")
        );
        assert_eq!(ctrl.devices.len(), 2);

        let kb = &ctrl.devices[0];
        assert_eq!(kb.name, "Apple Internal Keyboard / Trackpad");
        assert_eq!(kb.device_class, UsbDeviceClassState::HumanInterface);
        assert_eq!(kb.speed, UsbSpeedState::FullSpeed12Mbps);
        assert!(kb.is_builtin);
        assert!(kb.anonymized_serial_hash.is_some());
        assert!(kb
            .anonymized_serial_hash
            .as_ref()
            .unwrap()
            .starts_with("sha256:"));

        let cam = &ctrl.devices[1];
        assert_eq!(cam.name, "FaceTime HD Camera");
        assert_eq!(cam.device_class, UsbDeviceClassState::AudioVideo);
        assert_eq!(cam.speed, UsbSpeedState::HighSpeed480Mbps);
        assert!(cam.is_builtin);
    }

    #[test]
    fn test_json_summary_serialization() {
        let collector = MockMacOsUsbCollector::new_apple_silicon();
        let snapshot = collector.collect_usb();
        let json = snapshot.to_json_summary();

        assert!(json.contains("\"controllers\":1"));
        assert!(json.contains("\"total_devices\":2"));
        assert!(json.contains("\"external\":false"));
        assert!(json.contains("\"mock\":true"));
    }

    #[test]
    fn test_recursive_hub_and_peripheral_detection() {
        let yubikey = MacOsUsbDeviceSnapshot {
            name: "YubiKey 5 NFC".to_string(),
            vendor_id: Some("0x1050".to_string()),
            product_id: Some("0x0407".to_string()),
            manufacturer: Some("Yubico".to_string()),
            anonymized_serial_hash: Some("sha256:1234567890abcdef".to_string()),
            device_class: UsbDeviceClassState::SecurityToken,
            speed: UsbSpeedState::FullSpeed12Mbps,
            location_id: Some("0x02110000 / 3".to_string()),
            bus_power_ma: Some(100),
            current_used_ma: Some(30),
            is_builtin: false,
            is_hub: false,
            children: Vec::new(),
        };

        let flash_drive = MacOsUsbDeviceSnapshot {
            name: "SanDisk Extreme SSD".to_string(),
            vendor_id: Some("0x0781".to_string()),
            product_id: Some("0x5583".to_string()),
            manufacturer: Some("SanDisk".to_string()),
            anonymized_serial_hash: Some("sha256:abcdef0123456789".to_string()),
            device_class: UsbDeviceClassState::MassStorage,
            speed: UsbSpeedState::SuperSpeedPlus10Gbps,
            location_id: Some("0x02120000 / 4".to_string()),
            bus_power_ma: Some(900),
            current_used_ma: Some(896),
            is_builtin: false,
            is_hub: false,
            children: Vec::new(),
        };

        let hub = MacOsUsbDeviceSnapshot {
            name: "USB 3.0 Hub".to_string(),
            vendor_id: Some("0x2109".to_string()),
            product_id: Some("0x0813".to_string()),
            manufacturer: Some("VIA Labs, Inc.".to_string()),
            anonymized_serial_hash: None,
            device_class: UsbDeviceClassState::Hub,
            speed: UsbSpeedState::SuperSpeed5Gbps,
            location_id: Some("0x02100000 / 2".to_string()),
            bus_power_ma: None,
            current_used_ma: None,
            is_builtin: false,
            is_hub: true,
            children: vec![yubikey, flash_drive],
        };

        let controller = MacOsUsbControllerSnapshot {
            name: "USB 3.1 Bus".to_string(),
            host_controller: Some("AppleSynopsysUSB40XHCI".to_string()),
            devices: vec![hub],
        };

        let collector = MockMacOsUsbCollector {
            controllers: vec![controller],
            is_mock: false,
        };

        let snapshot = collector.collect_usb();
        assert_eq!(snapshot.total_controller_count, 1);
        assert_eq!(snapshot.total_device_count, 3); // hub + 2 children
        assert!(snapshot.has_external_devices);
        assert!(snapshot.has_security_tokens);
        assert!(snapshot.has_mass_storage);
    }
}
