# Developer Tooling Boundary (`tools/`)

**Architectural Scope:** Cross-Cutting Developer Tooling & Invariant Checkers  
**Primary Technologies:** Python 3.10+, Bash/Zsh  
**Owner:** Developer Productivity & Release Engineering  

---

## 1. Scope & Purpose
The `tools/` workspace contains developer-facing automation, gate verification scripts, local testing utilities, and the 365-day plan progress tracker (`day_tracker.py`).

## 2. Permitted Dependencies
- **Outbound:** `src/` (for gate and policy verification), `schemas/`, `monorepo.json`.
- **Inbound:** Developer terminal invocations and CI/CD pipelines.

## 3. Boundary Invariants
1. **No Production Runtime Inclusion:** Tools code is strictly for local developer workflows and CI verification; it must never be bundled into the production daemon or UI release packages.
2. **Deterministic Verification:** Release gate checks and day tracking scripts must report truthful, evidence-backed results without mocking away failures.
3. **Host Safety:** Developer tools must not modify host macOS configurations, security settings, or system extensions without explicit approval.

## 4. Developer Tools Catalog

| Script / Tool | Primary Purpose | Invocation Example |
|---------------|-----------------|--------------------|
| `tools/dev_setup.py` | Local development bootstrap & prerequisite diagnostics | `python3 tools/dev_setup.py check` |
| `tools/setup_dev.sh` | Unprivileged POSIX shell wrapper for macOS / Linux | `./tools/setup_dev.sh` |
| `tools/setup_dev.ps1` | Unprivileged PowerShell wrapper for Windows 11 | `.\tools\setup_dev.ps1` |
| `tools/ci_runner.py` | Local multi-tier CI pipeline runner & dependency auditor | `python3 tools/ci_runner.py all` |
| `tools/mock_platform_cli.py` | Mock platform adapter inspection, telemetry & matrix audit | `python3 tools/mock_platform_cli.py inspect` |
| `tools/clean_clone_verifier.py` | Clean-clone bootstrap verification and telemetry recorder | `python3 tools/clean_clone_verifier.py` |
| `tools/detect_macos.py` | macOS product version, build, architecture & host identity | `python3 tools/detect_macos.py` |
| `tools/detect_cpu.py` | macOS CPU model, core counts, P/E topology & hardware cache | `python3 tools/detect_cpu.py` |
| `tools/detect_memory.py` | macOS memory capacity, VM page breakdown, swap & pressure | `python3 tools/detect_memory.py` |
| `tools/detect_storage.py` | macOS storage volumes, APFS container, SSV seal & FileVault | `python3 tools/detect_storage.py` |
| `tools/detect_battery.py` | macOS battery state, power source, charging dynamics & health | `python3 tools/detect_battery.py` |
| `tools/detect_network.py` | macOS network interfaces, link states, routing & DNS metadata | `python3 tools/detect_network.py` |
| `tools/detect_gpu.py` | macOS GPU model, core count, Metal support & display inventory | `python3 tools/detect_gpu.py` |
| `tools/detect_usb.py` | macOS USB controllers, device descriptors & peripheral inventory | `python3 tools/detect_usb.py` |
| `tools/detect_processes.py` | macOS process table, PID, owner, resource usage & role telemetry | `python3 tools/detect_processes.py` |
| `tools/detect_services.py` | macOS launchd services, status, ownership & login-item inventory | `python3 tools/detect_services.py` |
| `tools/detect_apps.py` | macOS installed application bundles, versions & bundle identifiers | `python3 tools/detect_apps.py` |
| `tools/detect_signatures.py` | macOS application signatures, CDHash & Gatekeeper notarization | `python3 tools/detect_signatures.py` |
| `tools/detect_fsevents.py` | macOS FSEvents filesystem change notifications inspection | `python3 tools/detect_fsevents.py` |
| `tools/monitor_fsevents.py` | macOS FSEvents-based filesystem change notification monitor | `python3 tools/monitor_fsevents.py` |
| `tools/detect_endpoint_security.py` | macOS Endpoint Security feasibility, entitlement limits & fallbacks | `python3 tools/detect_endpoint_security.py` |
| `tools/migrate.py` | SQLite database migration & integrity auditor | `python3 tools/migrate.py status` |
| `tools/test_runner.py` | Unified polyglot test orchestrator (Pytest, Cargo, Vitest) | `python3 tools/test_runner.py --all` |
| `tools/lint.py` | AST zero-ambient-shell checker & multi-tier static linter | `python3 tools/lint.py` |
| `tools/check_secrets.py` | High-entropy secret and credential file scanner | `python3 tools/check_secrets.py` |
| `tools/generate_types.py` | Canonical JSON Schema cross-language type generator | `python3 tools/generate_types.py --check` |
| `tools/day_tracker.py` | 365-day plan progress state machine & gate reviewer | `python3 tools/day_tracker.py status` |

