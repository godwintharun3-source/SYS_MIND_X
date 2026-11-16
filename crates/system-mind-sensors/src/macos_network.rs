//! macOS Darwin network interfaces, link states, and connectivity telemetry collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InterfaceTypeState {
    Loopback,
    Wifi,
    Ethernet,
    Thunderbolt,
    Bridge,
    VpnTunnel,
    Awdl,
    Other,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LinkStatusState {
    UpActive,
    UpInactive,
    Down,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsInterfaceSnapshot {
    pub name: String,
    pub interface_type: InterfaceTypeState,
    pub link_status: LinkStatusState,
    pub mtu: u32,
    pub primary: bool,
    pub has_ipv4: bool,
    pub has_ipv6: bool,
    pub anonymized_mac: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsNetworkSnapshot {
    pub interfaces: Vec<MacOsInterfaceSnapshot>,
    pub primary_interface: Option<String>,
    pub is_online: bool,
    pub default_gateway: Option<String>,
    pub dns_server_count: usize,
    pub is_mock: bool,
}

impl MacOsNetworkSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"interface_count\":{},\"primary\":\"{}\",\"is_online\":{},\"default_gw\":\"{}\",\"dns_count\":{},\"mock\":{}}}",
            self.interfaces.len(),
            self.primary_interface.as_deref().unwrap_or("none"),
            self.is_online,
            self.default_gateway.as_deref().unwrap_or("none"),
            self.dns_server_count,
            self.is_mock
        )
    }
}

pub trait MacOsNetworkCollector: Send + Sync {
    fn collect_network(&self) -> MacOsNetworkSnapshot;
}

/// Safe mock collector simulating macOS network interfaces and WAN connectivity without host interaction.
#[derive(Debug, Clone)]
pub struct MockMacOsNetworkCollector {
    pub is_online: bool,
    pub default_gateway: Option<String>,
    pub primary_interface: String,
}

impl Default for MockMacOsNetworkCollector {
    fn default() -> Self {
        Self {
            is_online: true,
            default_gateway: Some("192.168.1.1".to_string()),
            primary_interface: "en0".to_string(),
        }
    }
}

impl MockMacOsNetworkCollector {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn offline() -> Self {
        Self {
            is_online: false,
            default_gateway: None,
            primary_interface: "lo0".to_string(),
        }
    }
}

impl MacOsNetworkCollector for MockMacOsNetworkCollector {
    fn collect_network(&self) -> MacOsNetworkSnapshot {
        let lo0 = MacOsInterfaceSnapshot {
            name: "lo0".to_string(),
            interface_type: InterfaceTypeState::Loopback,
            link_status: LinkStatusState::UpActive,
            mtu: 16384,
            primary: false,
            has_ipv4: true,
            has_ipv6: true,
            anonymized_mac: None,
        };

        if !self.is_online {
            return MacOsNetworkSnapshot {
                interfaces: vec![lo0],
                primary_interface: Some("lo0".to_string()),
                is_online: false,
                default_gateway: None,
                dns_server_count: 0,
                is_mock: true,
            };
        }

        let en0 = MacOsInterfaceSnapshot {
            name: self.primary_interface.clone(),
            interface_type: InterfaceTypeState::Wifi,
            link_status: LinkStatusState::UpActive,
            mtu: 1500,
            primary: true,
            has_ipv4: true,
            has_ipv6: true,
            anonymized_mac: Some("sha256:ca018c908c350000".to_string()),
        };

        MacOsNetworkSnapshot {
            interfaces: vec![lo0, en0],
            primary_interface: Some(self.primary_interface.clone()),
            is_online: true,
            default_gateway: self.default_gateway.clone(),
            dns_server_count: 2,
            is_mock: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_macos_network_collection() {
        let collector = MockMacOsNetworkCollector::new();
        let snapshot = collector.collect_network();

        assert_eq!(snapshot.interfaces.len(), 2);
        assert_eq!(snapshot.primary_interface, Some("en0".to_string()));
        assert!(snapshot.is_online);
        assert_eq!(snapshot.default_gateway, Some("192.168.1.1".to_string()));
        assert_eq!(snapshot.dns_server_count, 2);
        assert!(snapshot.is_mock);

        let en0 = &snapshot.interfaces[1];
        assert_eq!(en0.name, "en0");
        assert_eq!(en0.interface_type, InterfaceTypeState::Wifi);
        assert_eq!(en0.link_status, LinkStatusState::UpActive);
        assert!(en0.primary);
        assert!(en0.has_ipv4);
        assert!(en0.has_ipv6);
        assert!(en0.anonymized_mac.as_ref().unwrap().starts_with("sha256:"));
    }

    #[test]
    fn test_mock_macos_network_offline() {
        let offline_collector = MockMacOsNetworkCollector::offline();
        let snapshot = offline_collector.collect_network();

        assert_eq!(snapshot.interfaces.len(), 1);
        assert!(!snapshot.is_online);
        assert_eq!(snapshot.default_gateway, None);
        assert_eq!(snapshot.dns_server_count, 0);
        assert_eq!(
            snapshot.interfaces[0].interface_type,
            InterfaceTypeState::Loopback
        );
    }

    #[test]
    fn test_mock_macos_network_json_serialization() {
        let collector = MockMacOsNetworkCollector::new();
        let snapshot = collector.collect_network();
        let json = snapshot.to_json_summary();

        assert!(json.contains("\"interface_count\":2"));
        assert!(json.contains("\"primary\":\"en0\""));
        assert!(json.contains("\"is_online\":true"));
        assert!(json.contains("\"default_gw\":\"192.168.1.1\""));
    }
}
