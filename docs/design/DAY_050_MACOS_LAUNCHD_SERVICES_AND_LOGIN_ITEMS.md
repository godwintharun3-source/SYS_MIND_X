# DAY 050: Read-Only macOS launchd Service and Login-Item Telemetry Architecture

## Executive Summary
In macOS, background processes, periodic tasks, and auto-start applications are governed primarily by Darwin's unified init and service management system: `launchd` (PID 1). In addition, desktop user sessions support startup applications registered as user Login Items. 

Following the non-negotiable charter safety invariants—specifically `SC-01` (Zero Ambient Shell Authority), read-only unprivileged operation, and component ownership segregation—SYSTEM MIND X Day 050 establishes a passive, non-mutating telemetry engine for macOS launchd services and login items.

This component catalogs loaded launchd jobs, inspects standard daemon/agent definition plists, classifies service ownership across `SYSTEM_MANAGED`, `VENDOR_MANAGED`, and `USER_MANAGED` tiers, inventories user login items, and guarantees zero mutating operations (`launchctl load/unload/bootout/kill` are strictly banned).

---

## 1. Domain Model and Service Hierarchy

macOS divides services into distinct execution contexts and domains:

1. **System Daemons (`/System/Library/LaunchDaemons`)**:
   - Apple-authored system-wide daemons running as root in the system bootstrap domain.
   - Examples: `com.apple.logd`, `com.apple.kernelmanagerd`.
   - Ownership: `SYSTEM_MANAGED`.
2. **System Agents (`/System/Library/LaunchAgents`)**:
   - Apple-authored GUI session agents loaded on behalf of logged-in users.
   - Examples: `com.apple.Finder`, `com.apple.homed`, `com.apple.bird`.
   - Ownership: `SYSTEM_MANAGED`.
3. **Global Daemons (`/Library/LaunchDaemons`)**:
   - Third-party/administrator background daemons installed system-wide.
   - Examples: `com.cloudflare.1dot1dot1dot1.macos.warp.daemon`, `com.docker.socket`.
   - Ownership: `VENDOR_MANAGED`.
4. **Global Agents (`/Library/LaunchAgents`)**:
   - Third-party/administrator background agents loaded for every user session.
   - Examples: `com.oracle.java.Java-Updater`, `com.avast.hub`.
   - Ownership: `VENDOR_MANAGED`.
5. **User Agents (`~/Library/LaunchAgents`)**:
   - Per-user background agents installed specifically in the user's home directory.
   - Examples: `com.google.GoogleUpdater.wake`, `homebrew.mxcl.mysql`.
   - Ownership: `USER_MANAGED` or `VENDOR_MANAGED`.
6. **Login Items (`System Events` / BTM)**:
   - User applications or helper executables launched automatically when the user logs into their desktop graphical session.
   - Examples: `GeminiAppLauncher`, `Docker Desktop`, `Spotify`.
   - Ownership: `USER_MANAGED` / `VENDOR_MANAGED`.

---

## 2. Invariants & Safety Guarantees

| Invariant | Description | Verification Method |
|---|---|---|
| `SC-01` / `INV-SVC-01` | **Zero Ambient Shell Authority**: All subcommands (`launchctl list`, `osascript`) execute via tokenized argument vectors (`shell=False`) with strict timeouts (<= 5s). | AST static check & unit tests |
| `INV-SVC-02` | **Strictly Read-Only / Zero Mutation**: No `launchctl load`, `unload`, `bootout`, `bootstrap`, `enable`, `disable`, `kickstart`, or `kill`. Only `launchctl list` and read-only file parsing. | AST audit & packaging validator |
| `INV-SVC-03` | **Sensitive Argument Redaction**: Plist arguments and environment variables are scrubbed for credentials and tokens. Only binary paths (`Program` or `ProgramArguments[0]`) are recorded. | Secret leak scanner & unit tests |
| `INV-SVC-04` | **Component Ownership Classification**: Every service and login item is deterministically tagged with `SYSTEM_MANAGED`, `VENDOR_MANAGED`, or `USER_MANAGED`. | Deterministic classifier tests |
| `INV-SVC-05` | **Unprivileged User-Space Operation**: Collection requires zero `sudo` or root privileges. Directory scanning and `launchctl list` execute as the current user. | Host validation |
| `INV-SVC-06` | **Graceful TCC / Permission Fallback**: If Apple Events or System Events are denied by TCC, login items collection reports `unavailable_telemetry` without crashing or blocking. | Fault injection tests |
| `INV-SVC-07` | **Graceful Non-Darwin Fallback**: On non-Darwin hosts (Linux, Windows, CI), delegates to `MockPlatformAdapter` or structured unavailable report. | Mock & multi-platform tests |

---

## 3. Data Schema

### `MacLaunchdService`
- `label`: str (Unique reverse-DNS service identifier, e.g., `"com.apple.Finder"`)
- `pid`: Optional[int] (Running PID if active, None if inactive)
- `last_exit_code`: Optional[int] (Last recorded exit code or signal, e.g. 0, -9)
- `domain`: `ServiceDomain` (`SYSTEM_DAEMON`, `SYSTEM_AGENT`, `GLOBAL_DAEMON`, `GLOBAL_AGENT`, `USER_AGENT`, `RUNTIME_LOADED`)
- `status`: `ServiceStatus` (`RUNNING`, `LOADED_WAITING`, `LOADED_FAILED`, `DEFINITION_ONLY`, `UNKNOWN`)
- `ownership`: `ServiceOwnership` (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`)
- `plist_path`: Optional[str] (Absolute path to `.plist` definition file if identified)
- `program`: Optional[str] (Sanitized executable path of the service binary)
- `run_at_load`: Optional[bool] (Whether launchd automatically starts the service on load)
- `keep_alive`: Optional[bool] (Whether launchd restarts the service if it terminates)
- `is_apple`: bool (Convenience helper: True if Apple-authored core service)

### `MacLoginItem`
- `name`: str (Application or helper name, e.g., `"GeminiAppLauncher"`)
- `path`: Optional[str] (Filesystem path to the application bundle, or None)
- `hidden`: bool (Whether the window is launched hidden at login)
- `kind`: `LoginItemKind` (`APPLICATION`, `SERVICE`, `UNKNOWN`)
- `is_apple`: bool (Whether it is an Apple-authored component)

### `MacServicesReport`
- `collection_method`: str (`"NATIVE_DARWIN_LAUNCHD"`, `"MOCK_PLATFORM_ADAPTER"`)
- `timestamp`: str (ISO 8601 UTC)
- `host_platform`: str
- `services`: List[MacLaunchdService]
- `login_items`: List[MacLoginItem]
- `total_services_count`: int
- `running_services_count`: int
- `loaded_services_count`: int
- `system_managed_count`: int
- `vendor_managed_count`: int
- `user_managed_count`: int
- `total_login_items_count`: int
- `warnings`: List[str]
- `unavailable_telemetry`: List[str]

---

## 4. Query & Parsing Strategy

1. **Active Jobs Query (`/bin/launchctl list`)**:
   - Parses the tab-separated stdout lines: `PID\tStatus\tLabel`.
   - Handles integer PIDs or `-` (converted to `None`).
   - Handles signed integer status codes (e.g., `-9` for `SIGKILL`, `0` for clean exit, positive for exit status).
2. **Filesystem Plist Scanning**:
   - Inspects the 5 standard directories:
     - `/System/Library/LaunchDaemons`
     - `/System/Library/LaunchAgents`
     - `/Library/LaunchDaemons`
     - `/Library/LaunchAgents`
     - `~/Library/LaunchAgents`
   - Uses Python's standard `plistlib.load(f)` (supports both XML and binary Apple plists without external C dependencies).
   - Extracts metadata safely:
     - `Label`: Matches with loaded jobs.
     - `Program` / `ProgramArguments[0]`: Sanitized binary path.
     - `RunAtLoad`: Boolean flag.
     - `KeepAlive`: Boolean or dict evaluation.
3. **Login Items Query**:
   - Executes `/usr/bin/osascript -e 'tell application "System Events" to get {name, path, hidden} of every login item'`.
   - Parses items cleanly. If System Events is not available or Apple Events are restricted by macOS TCC, logs a warning and marks `login_items` as unavailable telemetry rather than halting.

---

## 5. Non-Darwin and Mock Testing

For tests and non-Darwin hosts:
- `detect_mock()` constructs a canonical Apple Silicon launchd report featuring real Darwin services:
  - System agents: `com.apple.Finder`, `com.apple.bird`, `com.apple.homed`
  - Vendor daemons: `com.cloudflare.warp.daemon`, `com.docker.socket`
  - User agents: `homebrew.mxcl.mysql`, `com.google.keystone.agent`
  - User login item: `GeminiAppLauncher`
- The Rust crate `system-mind-sensors` provides `MacOsServicesCollector` and `MockMacOsServicesCollector` mirroring these types.
