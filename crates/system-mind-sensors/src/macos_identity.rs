//! macOS Darwin platform version, architecture, and identity collector.

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsIdentitySnapshot {
    pub os_name: String,
    pub os_version: String,
    pub build_version: String,
    pub darwin_kernel_release: String,
    pub architecture: String,
    pub is_apple_silicon: bool,
    pub is_rosetta_translated: bool,
    pub hostname: String,
    pub anonymized_serial_hash: Option<String>,
    pub is_mock: bool,
}

impl MacOsIdentitySnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"os_name\":\"{}\",\"os_version\":\"{}\",\"build\":\"{}\",\"kernel\":\"{}\",\"arch\":\"{}\",\"apple_silicon\":{},\"rosetta\":{},\"hostname\":\"{}\",\"mock\":{}}}",
            self.os_name,
            self.os_version,
            self.build_version,
            self.darwin_kernel_release,
            self.architecture,
            self.is_apple_silicon,
            self.is_rosetta_translated,
            self.hostname,
            self.is_mock
        )
    }
}

pub trait MacOsIdentityCollector: Send + Sync {
    fn collect_identity(&self) -> MacOsIdentitySnapshot;
}

/// Safe mock collector simulating Apple Silicon macOS Darwin environment.
#[derive(Debug, Default)]
pub struct MockMacOsIdentityCollector {
    pub simulated_version: String,
    pub simulated_build: String,
    pub simulated_arch: String,
}

impl MockMacOsIdentityCollector {
    pub fn new() -> Self {
        Self {
            simulated_version: "15.1.0".to_string(),
            simulated_build: "24B83".to_string(),
            simulated_arch: "arm64".to_string(),
        }
    }
}

impl MacOsIdentityCollector for MockMacOsIdentityCollector {
    fn collect_identity(&self) -> MacOsIdentitySnapshot {
        MacOsIdentitySnapshot {
            os_name: "macOS".to_string(),
            os_version: self.simulated_version.clone(),
            build_version: self.simulated_build.clone(),
            darwin_kernel_release: "24.1.0".to_string(),
            architecture: self.simulated_arch.clone(),
            is_apple_silicon: self.simulated_arch == "arm64" || self.simulated_arch == "aarch64",
            is_rosetta_translated: false,
            hostname: "apple-silicon-companion.local".to_string(),
            anonymized_serial_hash: Some("sha256:e3b0c44298fc1c14".to_string()),
            is_mock: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_macos_identity_collection() {
        let collector = MockMacOsIdentityCollector::new();
        let identity = collector.collect_identity();

        assert_eq!(identity.os_name, "macOS");
        assert_eq!(identity.os_version, "15.1.0");
        assert_eq!(identity.architecture, "arm64");
        assert!(identity.is_apple_silicon);
        assert!(!identity.is_rosetta_translated);
        assert!(identity.is_mock);
        assert!(identity.anonymized_serial_hash.is_some());

        let json = identity.to_json_summary();
        assert!(json.contains("\"apple_silicon\":true"));
        assert!(json.contains("\"arch\":\"arm64\""));
    }

    #[test]
    fn test_mock_macos_identity_intel_simulation() {
        let mut collector = MockMacOsIdentityCollector::new();
        collector.simulated_arch = "x86_64".to_string();
        let identity = collector.collect_identity();

        assert_eq!(identity.architecture, "x86_64");
        assert!(!identity.is_apple_silicon);
    }

    #[test]
    fn test_mock_macos_identity_preview_version() {
        let mut collector = MockMacOsIdentityCollector::new();
        collector.simulated_version = "27.0.0".to_string();
        collector.simulated_build = "27A100".to_string();
        let identity = collector.collect_identity();

        assert_eq!(identity.os_version, "27.0.0");
        assert_eq!(identity.build_version, "27A100");
    }
}
