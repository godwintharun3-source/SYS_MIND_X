# Design Note: Day 066 — Implement Stable Device and Entity Identifiers

## 1. Architectural Context & Motivation
Milestone 5 (Days 066–090) constructs the **Temporal Digital Twin and Event History** for SYSTEM MIND X. The foundation of any temporal property graph or event-sourced digital twin is the absolute stability, uniqueness, and collision resistance of its entity identifiers over time.

In traditional operating system environments, standard identifiers suffer from severe operational limitations:
1. **Volatile Hostnames:** Hostnames change dynamically during network roaming, DHCP lease renewal, or user customization (e.g., `MacBook-Air.local` changing to `MacBook-Air-2.local`).
2. **PID Recycling:** Process IDs (PIDs) are ephemeral 16-bit or 32-bit integers recycled immediately upon process termination. A naive entity ID `proc:1234` causes graph corruption when two distinct processes share the same PID at different points in time.
3. **Privacy Restrictions on Hardware Serials:** Modern operating systems (macOS, Windows, modern Linux) strictly restrict access to raw hardware serial numbers from unprivileged user space. Plaintext serials also violate privacy perimeter invariants (`SC-04`).
4. **Path Relocation:** User applications and files may be renamed or relocated across filesystem volumes while maintaining logical entity identity.

Day 066 formalizes the **SYSTEM MIND X Uniform Resource Name (URN) Entity Architecture**, establishing deterministic, collision-resistant, and privacy-preserving identifier derivation algorithms across all digital twin entities.

---

## 2. Canonical URN Namespace Specification

All digital twin entities are identified by a canonical URN conforming to the formal syntax:
```
urn:systemmind:<entity_domain>:<domain_qualifiers...>
```

### Domain Syntax Matrix
| Entity Domain | URN Pattern | Example | Deterministic Anchors |
|:---|:---|:---|:---|
| **Host Device** | `urn:systemmind:host:<device_id>` | `urn:systemmind:host:d5a1b3c9-4e2f-5a8b-9c1d-7e8f0a1b2c3d` | Stable device UUID / OS installation UUID |
| **OS Kernel** | `urn:systemmind:kernel:<family>:<release>:<arch>` | `urn:systemmind:kernel:darwin:27.3.0:arm64` | Native OS product release & machine arch |
| **CPU Hardware**| `urn:systemmind:cpu:<arch>:<brand_digest>:<cores>` | `urn:systemmind:cpu:arm64:a1b2c3d4e5f6:12` | Architecture, canonical brand string digest, core topology |
| **Memory** | `urn:systemmind:mem:<device_id>:<capacity_bytes>`| `urn:systemmind:mem:d5a1b3c9:17179869184` | Host device ID + physical RAM bytes |
| **Storage Volume**| `urn:systemmind:vol:<volume_uuid_or_mount_digest>` | `urn:systemmind:vol:4B1E8C22-8A2D-4C2E-8E99-7D22B4A1D888` | Filesystem volume UUID or salted mountpoint hash |
| **Network Interface**| `urn:systemmind:net:<device_id>:<if_name>` | `urn:systemmind:net:d5a1b3c9:en0` | Host device ID + physical network interface name |
| **Application** | `urn:systemmind:app:<canonical_identifier>` | `urn:systemmind:app:com.apple.Safari` | `CFBundleIdentifier` (macOS), package name, or binary name |
| **Process** | `urn:systemmind:proc:<device_id>:<start_epoch>:<pid>:<bin_digest>` | `urn:systemmind:proc:d5a1b3c9:1794975297:1234:8f9a2b1c` | Device ID, start timestamp, PID, binary path digest (Anti-PID recycling) |
| **launchd Service**| `urn:systemmind:svc:<domain>:<label>` | `urn:systemmind:svc:gui.501:com.systemmind.useragent` | launchd execution domain + service reverse-DNS label |
| **Filesystem Node**| `urn:systemmind:file:<device_id>:<vol_id>:<path_digest>` | `urn:systemmind:file:d5a1b3c9:vol01:f4e3d2c1` | Host device, volume, and canonical normalized path digest |
| **Package** | `urn:systemmind:pkg:<ecosystem>:<name>:<version>` | `urn:systemmind:pkg:brew:openssl:3.2.1` | Package manager ecosystem, name, SemVer version |

---

## 3. Stable Device Identifier Generation & Persistence

The device identifier (`device_id`) serves as the root anchor for device-scoped entities. It is resolved through a deterministic multi-tier strategy:

```
+-----------------------------------------------------------------------------------------+
|                              Device Identifier Resolution Strategy                      |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
                      +---------------------------------------------+
                      | 1. Read Cached Identifier from Disk         |
                      |    (~/.system-mind/device_id)               |
                      +---------------------------------------------+
                                     /             \
                           [Present]                 [Absent]
                                  /                     \
                                 v                       v
                      +--------------------+  +---------------------------------------------+
                      | Validate UUID Format|  | 2. Query Platform Hardware Anchor           |
                      | & Return Cached ID |  |    (macOS: IOPlatformUUID via ioreg)        |
                      +--------------------+  +---------------------------------------------+
                                                             /             \
                                                   [Available]             [Restricted / Mock]
                                                          /                     \
                                                         v                       v
                                              +--------------------+  +--------------------+
                                              | Hash Anchor with   |  | Generate Stable    |
                                              | Namespace UUIDv5   |  | UUIDv5 from Mock   |
                                              | & Persist to Disk  |  | Platform Profile   |
                                              +--------------------+  +--------------------+
```

### Safety & Privacy Boundaries:
1. **Raw Serial Protection (`INV-ID-01`):** Raw hardware serial numbers are never embedded in plaintext into URN strings or log files; all hardware seeds are hashed with SHA-256 and salted.
2. **Deterministic UUIDv5 Generation (`INV-ID-02`):** Identifiers generated from hardware seeds use RFC 4122 UUIDv5 scoped under a dedicated `NAMESPACE_SYSTEM_MIND` (`6ba7b810-9dad-11d1-80b4-00c04fd430c8`), guaranteeing identical IDs for identical inputs across runs.
3. **Anti-PID Recycling (`INV-ID-03`):** Process entities are temporally qualified with their startup timestamp. Even if two processes reuse PID `4242`, their distinct start times produce distinct URNs, preventing temporal graph collisions.
4. **Zero Ambient Shell Authority (`SC-01`):** Identification queries execute in-memory or via unprivileged APIs without spawning ambient shell processes (`shell=False`).
5. **Universal "Scan != Safe" Invariant (`SC-03`):** Generating a stable identity registers the entity in the digital twin, but does not prove its trustworthiness or safety.

---

## 4. Verification & Acceptance Criteria
- Full test pass rate across unit, contract, integration, and safety suites.
- Polyglot synchronization in Python (`src/system_mind/twin/identity.py`) and Rust (`crates/system-mind-common/src/identity.rs`).
- Programmatic packaging validation confirming all identity components adhere to architectural conventions.
- Developer CLI tool (`tools/detect_stable_identity.py`) verified on live host and mock platform profiles.
- Formalized ADR-077 in `docs/DECISION_LOG.md`.
