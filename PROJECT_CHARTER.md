# SYSTEM MIND X - Project Charter

## Product definition
SYSTEM MIND X is a universal AI computer-operation and governance platform. It acts as the primary high-level intelligent operator across supported operating systems, while native kernels and native security mechanisms remain responsible for low-level execution and enforcement.

## Primary capabilities
1. Persistent computer digital twin.
2. Application context intelligence.
3. Hardware and OS awareness.
4. Context-aware system governance and policy proposals.
5. Autonomous maintenance of OS-managed components, excluding user-installed apps and user project dependencies.
6. Universal file intelligence, provenance, static inspection and controlled execution.
7. Developer lifecycle assistance.
8. Predictive diagnosis and caretaker reporting.
9. Typed, risk-aware, permission-controlled and independently verified actions.
10. Linux-based SYSTEM MIND OS prototype using NixOS rather than a new kernel.

## Target users
- Personal computer users.
- Developers and software engineering teams.
- IT administrators and enterprises.

## First-release support matrix (bounded)
- macOS on Apple Silicon: companion agent and desktop control where public APIs/entitlements permit.
- Windows 11 x64: companion agent and supported native controls.
- Ubuntu LTS x86_64: Linux companion agent.
- NixOS x86_64 and ARM64 virtual-machine images: SYSTEM MIND OS alpha.

This is a target matrix, not a claim of already achieved support. Other distributions, macOS versions, Windows editions, OEM hardware, firmware and specialised peripherals require later validation.

## Explicit exclusions for v1.0
- A brand-new kernel.
- Unrestricted execution of arbitrary files.
- Guaranteed detection of all malware or all zero-day threats.
- Automatically updating user-installed applications or developer project dependencies.
- Universal support for every hardware device or firmware vendor.
- Unattended high-impact firmware, bootloader, partition, firewall or security-policy changes.

## Completion definition
The 365-day plan targets a feature-complete first release for the bounded support matrix, with documented limits, repeatable tests, recovery procedures, signed builds where feasible, and a benchmark report. Ongoing security updates, additional device support and model improvements continue after v1.0.
