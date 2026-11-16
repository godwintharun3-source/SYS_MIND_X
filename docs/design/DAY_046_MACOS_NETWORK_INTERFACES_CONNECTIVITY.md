# DAY 046: macOS Network Interfaces, Link State, and Connectivity Metadata Architecture

**Author:** SYSTEM MIND X Engineering Agent  
**Date:** 2026-11-16  
**Status:** In-Progress (Day 046)  
**Milestone:** Milestone 4: macOS system agent and telemetry (Days 041–065)  
**Document ID:** `docs/design/DAY_046_MACOS_NETWORK_INTERFACES_CONNECTIVITY.md`

---

## 1. Executive Summary

Milestone 4 constructs a read-only macOS companion agent operating under **Zero Ambient Shell Authority** (`SC-01`) and strictly without root/administrator privileges. Following identity (Day 041), CPU (Day 042), memory (Day 043), storage (Day 044), and power/battery (Day 045), Day 046 implements passive, read-only introspection of **network interfaces, physical/logical link states, IPv4/IPv6 configurations, default routing gateways, and DNS resolvers**.

Network state and connectivity topology are safety-critical prerequisites for computer operations. System updates, package dependency auditing, and remote policy synchronization require verified Internet reachability (`INV-NET-01`). Simultaneously, local-only offline execution modes mandate continuous verification that network sockets and interfaces remain constrained or disconnected (`INV-NET-04`).

---

## 2. Invariants & Safety Constraints

- **`INV-NET-01` (Unprivileged Read-Only Introspection):** All interface and connectivity metrics are retrieved exclusively via read-only Darwin user-space utilities: `/sbin/ifconfig`, `/usr/sbin/networksetup -listallhardwareports`, `/usr/sbin/scutil --nwi`, `/usr/sbin/scutil --dns`, and `/usr/sbin/netstat -nr -f inet`. Mutating network actions (`ifconfig ... up/down`, `networksetup -set*`, `route add/delete`, modifying DNS or proxy profiles) are strictly prohibited.
- **`INV-NET-02` (Hardware Identifier Privacy & Anonymization):** Network physical interface addresses (MAC addresses) are hardware identifiers. In accordance with `INV-MAC-02` and privacy perimeter rules, raw MAC addresses are hashed using salted SHA-256 digests (`sha256:prefix...`) before inclusion in telemetry exports or logs, preventing tracking across external networks.
- **`INV-NET-03` (Zero Ambient Shell Authority):** All external utility invocations dispatch with explicit argument vectors using `subprocess.run(..., shell=False)` with a strict 5.0-second timeout.
- **`INV-NET-04` (Categorical Interface & Link State Classification):** Accurately classifies interface types (`WIFI`, `ETHERNET`, `LOOPBACK`, `THUNDERBOLT`, `BRIDGE`, `VPN_TUNNEL`, `AWDL`, `OTHER`) and link states (`UP_ACTIVE`, `UP_INACTIVE`, `DOWN`) without ambiguity.
- **`INV-NET-05` (Cross-Platform Graceful Degradation):** On non-Darwin hosts (Linux/Windows/CI environments), execution safely delegates to `MockPlatformAdapter` or returns structured fallback reports populating `unavailable_telemetry`.

---

## 3. Data Model Hierarchy

```
+-------------------------------------------------------------------+
|                        MacNetworkReport                           |
+-------------------------------------------------------------------+
| interfaces: List[MacNetworkInterface]                             |
| primary_interface_name: Optional[str]                             |
| is_online: bool                                                   |
| default_gateway: Optional[str]                                    |
| dns_servers: List[str]                                            |
| search_domains: List[str]                                         |
| collected_at_epoch_secs: float                                    |
| collection_method: str                                            |
| unavailable_telemetry: List[str]                                  |
| warnings: List[str]                                               |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                      MacNetworkInterface                          |
+-------------------------------------------------------------------+
| name: str (e.g. "en0", "lo0")                                     |
| hardware_port: Optional[str] (e.g. "Wi-Fi", "Thunderbolt 1")      |
| interface_type: InterfaceType                                     |
| link_state: LinkState                                             |
| mtu: int                                                          |
| mac_address: Optional[str]                                        |
| anonymized_mac_hash: Optional[str] (sha256:...)                   |
| ip_addresses: List[MacIpAddress]                                  |
| flags: List[str]                                                  |
| is_primary: bool                                                  |
| media: Optional[str]                                              |
+-------------------------------------------------------------------+
```

---

## 4. Collection Architecture

1. **`ifconfig` Parser:**
   - Extracts interface names, status (`active` vs `inactive`), flags (e.g. `UP`, `RUNNING`, `LOOPBACK`), MTU, link media, and raw MAC addresses.
   - Parses all bound IPv4 (`inet`) and IPv6 (`inet6`) addresses with netmasks, prefix lengths, and scopes.
2. **`networksetup -listallhardwareports` Parser:**
   - Correlates low-level device identifiers (e.g. `en0`, `en1`, `bridge0`) with user-facing hardware descriptions ("Wi-Fi", "Thunderbolt Bridge", "Ethernet Adapter").
3. **`scutil --nwi` Parser:**
   - Queries Darwin Network Information (NWI) for authoritative primary route interface designation and IPv4/IPv6 reachability flags.
4. **`scutil --dns` & `netstat -nr -f inet` Parsers:**
   - Resolves system DNS nameservers and default routing gateway IP without elevated socket privileges.
5. **Developer CLI (`tools/detect_network.py`):**
   - Provides human-readable output, structured `--json`, simulated `--mock`, and gate assertions (`--assert-online`, `--assert-interface <NAME>`).

---

## 5. Verification Matrix

| Test Domain | Target Invariant | Methodology |
|:---|:---|:---|
| Live Darwin Detection | `INV-NET-01`, `INV-NET-04` | Executed against host Apple Silicon Darwin kernel. |
| MAC Address Anonymization | `INV-NET-02` | Verifies raw MAC address strings are hashed into SHA-256 digests. |
| Subprocess Tokenization | `INV-NET-03` | Verifies `shell=False` across all command dispatches. |
| Offline / Loopback Mode | `INV-NET-04` | Verifies proper detection when disconnected from WAN. |
| Mock Fallback | `INV-NET-05` | Verified using `MockPlatformAdapter` on simulated network. |
| Rust Parity | Cross-language | Rust collector tests in `crates/system-mind-sensors`. |
| CLI Gate Verification | Operator tooling | Command-line execution with `--mock`, `--json`, and assertion flags. |
