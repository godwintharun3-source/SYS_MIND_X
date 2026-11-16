//! Diagnostic hashing and fingerprint helpers for SYSTEM MIND X contracts.

use std::collections::hash_map::DefaultHasher;
use std::hash::Hasher;

/// Compute a deterministic 64-bit hexadecimal fingerprint from input bytes.
pub fn compute_payload_fingerprint(data: &[u8]) -> String {
    let mut hasher = DefaultHasher::new();
    hasher.write(data);
    let hash_val = hasher.finish();
    format!("{:016x}", hash_val)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_payload_fingerprint() {
        let h1 = compute_payload_fingerprint(b"system-mind-payload-1");
        let h2 = compute_payload_fingerprint(b"system-mind-payload-1");
        let h3 = compute_payload_fingerprint(b"system-mind-payload-2");

        assert_eq!(h1, h2);
        assert_ne!(h1, h3);
        assert_eq!(h1.len(), 16);
    }
}
