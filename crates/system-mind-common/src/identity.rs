//! Canonical entity and device identifier URN architecture for SYSTEM MIND X.
//!
//! Provides deterministic, collision-resistant, and privacy-preserving
//! Uniform Resource Name (URN) identifiers for temporal digital twin entities.

use crate::crypto::compute_payload_fingerprint;
use std::fmt;

/// Canonical domains supported in System Mind entity URNs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum EntityDomain {
    Host,
    Kernel,
    Cpu,
    Memory,
    StorageVolume,
    NetworkInterface,
    Application,
    Process,
    Service,
    FilesystemNode,
    Package,
}

impl EntityDomain {
    /// Return the canonical domain label as a string slice.
    pub fn as_str(&self) -> &'static str {
        match self {
            EntityDomain::Host => "host",
            EntityDomain::Kernel => "kernel",
            EntityDomain::Cpu => "cpu",
            EntityDomain::Memory => "mem",
            EntityDomain::StorageVolume => "vol",
            EntityDomain::NetworkInterface => "net",
            EntityDomain::Application => "app",
            EntityDomain::Process => "proc",
            EntityDomain::Service => "svc",
            EntityDomain::FilesystemNode => "file",
            EntityDomain::Package => "pkg",
        }
    }

    /// Parse an entity domain from a string slice.
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "host" => Some(EntityDomain::Host),
            "kernel" => Some(EntityDomain::Kernel),
            "cpu" => Some(EntityDomain::Cpu),
            "mem" => Some(EntityDomain::Memory),
            "vol" => Some(EntityDomain::StorageVolume),
            "net" => Some(EntityDomain::NetworkInterface),
            "app" => Some(EntityDomain::Application),
            "proc" => Some(EntityDomain::Process),
            "svc" => Some(EntityDomain::Service),
            "file" => Some(EntityDomain::FilesystemNode),
            "pkg" => Some(EntityDomain::Package),
            _ => None,
        }
    }
}

impl fmt::Display for EntityDomain {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

/// Strongly typed representation of a canonical digital twin entity URN.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct EntityUrn {
    pub domain: EntityDomain,
    pub qualifier: String,
    pub urn: String,
    /// Mandatory charter invariant SC-03: scan_proves_safe is structurally false.
    pub scan_proves_safe: bool,
}

impl EntityUrn {
    /// Construct a new EntityUrn, enforcing canonical syntax and safety invariants.
    pub fn new(domain: EntityDomain, qualifier: impl Into<String>) -> Result<Self, String> {
        let q = qualifier.into();
        if q.is_empty() {
            return Err("URN qualifier cannot be empty".to_string());
        }
        let urn = format!("urn:systemmind:{}:{}", domain.as_str(), q);
        Ok(Self {
            domain,
            qualifier: q,
            urn,
            scan_proves_safe: false,
        })
    }

    /// Parse and validate a canonical URN string.
    pub fn parse(urn_string: &str) -> Result<Self, String> {
        let prefix = "urn:systemmind:";
        if !urn_string.starts_with(prefix) {
            return Err(format!("Invalid entity URN prefix: {}", urn_string));
        }

        let rest = &urn_string[prefix.len()..];
        let colon_idx = rest
            .find(':')
            .ok_or_else(|| format!("Missing qualifier delimiter in entity URN: {}", urn_string))?;

        let domain_str = &rest[..colon_idx];
        let qualifier = &rest[colon_idx + 1..];

        if qualifier.is_empty() {
            return Err("Empty qualifier in entity URN".to_string());
        }

        let domain = EntityDomain::from_str(domain_str)
            .ok_or_else(|| format!("Unknown entity domain in URN: {}", domain_str))?;

        Ok(Self {
            domain,
            qualifier: qualifier.to_string(),
            urn: urn_string.to_string(),
            scan_proves_safe: false,
        })
    }

    /// Returns the URN as a string slice.
    pub fn as_str(&self) -> &str {
        &self.urn
    }
}

impl fmt::Display for EntityUrn {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.urn)
    }
}

/// Helper function to compute a deterministic hash token of specified length.
pub fn hash_token(data: &str, length: usize) -> String {
    let fp = compute_payload_fingerprint(data.as_bytes());
    if length >= fp.len() {
        fp
    } else {
        fp[..length].to_string()
    }
}

/// Helper to sanitize identifier components (allowing a-z, A-Z, 0-9, _, ., -).
fn sanitize_qualifier_part(s: &str) -> String {
    s.chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '_' || c == '.' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

/// Generate canonical host device URN.
pub fn generate_host_urn(device_id: &str) -> Result<EntityUrn, String> {
    let clean_id = device_id.trim();
    EntityUrn::new(EntityDomain::Host, clean_id)
}

/// Generate canonical OS kernel URN.
pub fn generate_kernel_urn(
    os_family: &str,
    kernel_release: &str,
    arch: &str,
) -> Result<EntityUrn, String> {
    let clean_os = os_family.trim().to_lowercase();
    let clean_rel = kernel_release.trim().to_lowercase();
    let clean_arch = arch.trim().to_lowercase();
    let qualifier = format!("{}:{}:{}", clean_os, clean_rel, clean_arch);
    EntityUrn::new(EntityDomain::Kernel, qualifier)
}

/// Generate canonical CPU hardware URN.
pub fn generate_cpu_urn(
    arch: &str,
    brand_string: &str,
    core_count: u32,
) -> Result<EntityUrn, String> {
    let clean_arch = arch.trim().to_lowercase();
    let brand_digest = hash_token(brand_string.trim(), 12);
    let qualifier = format!("{}:{}:{}", clean_arch, brand_digest, core_count);
    EntityUrn::new(EntityDomain::Cpu, qualifier)
}

/// Generate canonical physical memory URN.
pub fn generate_memory_urn(device_id: &str, capacity_bytes: u64) -> Result<EntityUrn, String> {
    let clean_id = device_id.trim();
    let id_prefix = if clean_id.len() >= 8 {
        &clean_id[..8]
    } else {
        clean_id
    };
    let qualifier = format!("{}:{}", id_prefix, capacity_bytes);
    EntityUrn::new(EntityDomain::Memory, qualifier)
}

/// Generate canonical storage volume URN.
pub fn generate_storage_volume_urn(
    device_id: &str,
    volume_uuid_or_mount: &str,
) -> Result<EntityUrn, String> {
    let clean_id = device_id.trim();
    let id_prefix = if clean_id.len() >= 8 {
        &clean_id[..8]
    } else {
        clean_id
    };
    let vol_digest = hash_token(volume_uuid_or_mount.trim(), 16);
    let qualifier = format!("{}:{}", id_prefix, vol_digest);
    EntityUrn::new(EntityDomain::StorageVolume, qualifier)
}

/// Generate canonical network interface URN.
pub fn generate_network_interface_urn(device_id: &str, if_name: &str) -> Result<EntityUrn, String> {
    let clean_id = device_id.trim();
    let id_prefix = if clean_id.len() >= 8 {
        &clean_id[..8]
    } else {
        clean_id
    };
    let clean_if = if_name.trim().to_lowercase();
    let qualifier = format!("{}:{}", id_prefix, clean_if);
    EntityUrn::new(EntityDomain::NetworkInterface, qualifier)
}

/// Generate canonical application URN.
pub fn generate_app_urn(bundle_id_or_name: &str) -> Result<EntityUrn, String> {
    let clean_app = bundle_id_or_name.trim().to_lowercase();
    let safe_app = sanitize_qualifier_part(&clean_app);
    EntityUrn::new(EntityDomain::Application, safe_app)
}

/// Generate temporally qualified process URN to prevent PID recycling collisions.
pub fn generate_process_urn(
    device_id: &str,
    pid: u32,
    start_time_epoch_ms: u64,
    binary_path: &str,
) -> Result<EntityUrn, String> {
    let clean_id = device_id.trim();
    let id_prefix = if clean_id.len() >= 8 {
        &clean_id[..8]
    } else {
        clean_id
    };
    let path_digest = hash_token(binary_path.trim(), 8);
    let qualifier = format!(
        "{}:{}:{}:{}",
        id_prefix, start_time_epoch_ms, pid, path_digest
    );
    EntityUrn::new(EntityDomain::Process, qualifier)
}

/// Generate canonical background service URN.
pub fn generate_service_urn(domain: &str, service_label: &str) -> Result<EntityUrn, String> {
    let clean_domain = sanitize_qualifier_part(&domain.trim().to_lowercase());
    let clean_label = sanitize_qualifier_part(service_label.trim());
    let qualifier = format!("{}:{}", clean_domain, clean_label);
    EntityUrn::new(EntityDomain::Service, qualifier)
}

/// Generate canonical filesystem node URN with privacy-preserving path hashing.
pub fn generate_file_urn(
    device_id: &str,
    volume_id: &str,
    canonical_path: &str,
) -> Result<EntityUrn, String> {
    let clean_id = device_id.trim();
    let id_prefix = if clean_id.len() >= 8 {
        &clean_id[..8]
    } else {
        clean_id
    };
    let clean_vol = hash_token(volume_id.trim(), 8);
    let clean_path = hash_token(canonical_path.trim(), 16);
    let qualifier = format!("{}:{}:{}", id_prefix, clean_vol, clean_path);
    EntityUrn::new(EntityDomain::FilesystemNode, qualifier)
}

/// Generate canonical software package dependency URN.
pub fn generate_package_urn(
    ecosystem: &str,
    name: &str,
    version: &str,
) -> Result<EntityUrn, String> {
    let clean_eco = ecosystem.trim().to_lowercase();
    let clean_name = sanitize_qualifier_part(&name.trim().to_lowercase());
    let clean_ver = sanitize_qualifier_part(version.trim());
    let qualifier = format!("{}:{}:{}", clean_eco, clean_name, clean_ver);
    EntityUrn::new(EntityDomain::Package, qualifier)
}

/// Validate that a string conforms to the canonical System Mind URN specification.
pub fn validate_entity_urn(urn_string: &str) -> bool {
    EntityUrn::parse(urn_string).is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_entity_domain_round_trip() {
        let domains = [
            EntityDomain::Host,
            EntityDomain::Kernel,
            EntityDomain::Cpu,
            EntityDomain::Memory,
            EntityDomain::StorageVolume,
            EntityDomain::NetworkInterface,
            EntityDomain::Application,
            EntityDomain::Process,
            EntityDomain::Service,
            EntityDomain::FilesystemNode,
            EntityDomain::Package,
        ];

        for d in domains {
            let s = d.as_str();
            assert_eq!(EntityDomain::from_str(s), Some(d));
        }
        assert_eq!(EntityDomain::from_str("invalid_domain"), None);
    }

    #[test]
    fn test_entity_urn_creation_and_parsing() {
        let urn = EntityUrn::new(EntityDomain::Host, "d5a1b3c9-4e2f-5a8b").unwrap();
        assert_eq!(urn.as_str(), "urn:systemmind:host:d5a1b3c9-4e2f-5a8b");
        assert!(!urn.scan_proves_safe);

        let parsed = EntityUrn::parse("urn:systemmind:host:d5a1b3c9-4e2f-5a8b").unwrap();
        assert_eq!(parsed.domain, EntityDomain::Host);
        assert_eq!(parsed.qualifier, "d5a1b3c9-4e2f-5a8b");
        assert!(!parsed.scan_proves_safe);

        assert!(EntityUrn::parse("not:a:urn").is_err());
        assert!(EntityUrn::parse("urn:systemmind:unknown:foo").is_err());
        assert!(EntityUrn::parse("urn:systemmind:host:").is_err());
    }

    #[test]
    fn test_process_urn_prevents_pid_recycling_collision() {
        let device_id = "d5a1b3c9-4e2f-5a8b";
        let pid = 4242;
        let bin_path = "/usr/bin/python3";

        // Two processes with identical PID but distinct start times
        let urn1 = generate_process_urn(device_id, pid, 1700000000, bin_path).unwrap();
        let urn2 = generate_process_urn(device_id, pid, 1700005000, bin_path).unwrap();

        assert_ne!(urn1.urn, urn2.urn);
        assert!(urn1
            .urn
            .starts_with("urn:systemmind:proc:d5a1b3c9:1700000000:4242:"));
        assert!(urn2
            .urn
            .starts_with("urn:systemmind:proc:d5a1b3c9:1700005000:4242:"));
    }

    #[test]
    fn test_charter_invariant_scan_proves_safe_is_false() {
        let app_urn = generate_app_urn("com.apple.Safari").unwrap();
        assert!(!app_urn.scan_proves_safe);

        let file_urn = generate_file_urn("d5a1b3c9", "vol1", "/etc/hosts").unwrap();
        assert!(!file_urn.scan_proves_safe);
    }

    #[test]
    fn test_validate_entity_urn() {
        assert!(validate_entity_urn("urn:systemmind:app:com.apple.safari"));
        assert!(!validate_entity_urn("urn:systemmind:bad_domain:qualifier"));
        assert!(!validate_entity_urn("arbitrary_string"));
    }
}
