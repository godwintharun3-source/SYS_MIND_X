# DAY 051: Read-Only macOS Installed Application Inventory and Bundle Identifier Telemetry Architecture

## Executive Summary
In macOS, graphical applications are structured as standardized bundles (`.app` directories) containing executable binaries, resources, localized strings, and a declarative property list manifest: `Contents/Info.plist`. The Info.plist file defines authoritative bundle metadata, most crucially the reverse-DNS bundle identifier (`CFBundleIdentifier`), marketing version (`CFBundleShortVersionString`), build number (`CFBundleVersion`), and main executable name (`CFBundleExecutable`).

Following the SYSTEM MIND X charter safety principles—specifically `SC-01` (Zero Ambient Shell Authority), `SC-02` / `ADR-006` (System updates strictly exclude user applications), and non-privileged user-space operation—Day 051 implements a read-only application inventory detector.

This component catalogs installed applications across standard Darwin application domains (`/Applications`, `/System/Applications`, `/System/Applications/Utilities`, `~/Applications`, and `/System/Library/CoreServices/Applications`), parses bundle metadata using native `plistlib`, classifies component ownership across `SYSTEM_MANAGED`, `VENDOR_MANAGED`, and `USER_MANAGED` tiers, and produces a strongly typed telemetry report with zero mutating operations.

---

## 1. Bundle Structure and Application Domains

macOS organizes applications into distinct directory tiers reflecting maintenance scopes:

1. **System Applications (`/System/Applications`)**:
   - Apple-authored first-party apps sealed within the Signed System Volume (SSV).
   - Examples: `Safari.app`, `Preview.app`, `System Settings.app`, `App Store.app`.
   - Ownership: `SYSTEM_MANAGED`.
2. **System Utilities (`/System/Applications/Utilities`)**:
   - Essential system maintenance and diagnostic tools.
   - Examples: `Terminal.app`, `Activity Monitor.app`, `Disk Utility.app`, `Console.app`.
   - Ownership: `SYSTEM_MANAGED`.
3. **Core Services (`/System/Library/CoreServices/Applications`)**:
   - Fundamental desktop and system UI helper applications.
   - Examples: `Finder.app`, `Archive Utility.app`, `Directory Utility.app`.
   - Ownership: `SYSTEM_MANAGED`.
4. **Global Applications (`/Applications`)**:
   - System-wide third-party, enterprise, or developer desktop applications installed for all users.
   - Examples: `Google Chrome.app`, `Visual Studio Code.app`, `Docker.app`, `Slack.app`.
   - Ownership: `VENDOR_MANAGED` (or `USER_MANAGED` if user-installed).
5. **User Applications (`~/Applications`)**:
   - Per-user installed desktop applications confined to the current user's home directory.
   - Ownership: `USER_MANAGED`.

---

## 2. Invariants & Safety Guarantees

| Invariant | Description | Verification Method |
|---|---|---|
| `SC-01` / `INV-APP-01` | **Zero Ambient Shell Authority**: All queries execute without ambient shell expansion (`shell=False`) using tokenized vectors and strict timeouts (<= 5s). | AST static check & unit tests |
| `INV-APP-02` | **Strictly Read-Only / Zero Mutation**: Zero modification, deletion, renaming, or execution of discovered application bundles. | AST audit & packaging validator |
| `INV-APP-03` | **Autonomous Update Exclusion (`SC-02` / `ADR-006`)**: All non-system applications (`VENDOR_MANAGED` and `USER_MANAGED`) are flagged with `is_user_app=True`, cementing immunity from autonomous agent updates. | Unit tests & contract checks |
| `INV-APP-04` | **Authoritative Bundle Metadata**: Reads `Contents/Info.plist` directly using standard `plistlib` with unprivileged user-space permissions, guaranteeing accurate `CFBundleIdentifier` and version extraction. | Contract tests & live benchmarks |
| `INV-APP-05` | **Sensitive Path Privacy**: Applications located inside user homes outside standard application roots are redacted or categorized safely without exposing private personal documents. | Secret leak scanner & unit tests |
| `INV-APP-06` | **Graceful Non-Darwin Fallback**: On non-Darwin hosts (Linux, Windows, CI), delegates to `MockPlatformAdapter` returning canonical Apple Silicon macOS application profiles. | Mock & multi-platform tests |

---

## 3. Data Schema

### `MacAppInfo`
- `name`: str (Application display name from `CFBundleDisplayName`, `CFBundleName`, or bundle folder stem)
- `bundle_id`: str (Unique reverse-DNS bundle identifier from `CFBundleIdentifier`, e.g. `"com.google.Chrome"`)
- `bundle_path`: str (Absolute filesystem path to the `.app` bundle, e.g. `"/Applications/Google Chrome.app"`)
- `version`: str (Marketing version string from `CFBundleShortVersionString`, e.g. `"157.0.8103.51"`)
- `build_version`: Optional[str] (Internal build number from `CFBundleVersion`)
- `executable_name`: Optional[str] (Binary name from `CFBundleExecutable`)
- `executable_path`: Optional[str] (Absolute path to executable inside `Contents/MacOS/`)
- `min_os_version`: Optional[str] (Minimum compatible OS from `LSMinimumSystemVersion`)
- `ownership`: `ComponentOwnership` (`SYSTEM_MANAGED`, `VENDOR_MANAGED`, `USER_MANAGED`)
- `category`: `ApplicationCategory` (`CORE_SYSTEM`, `DEVELOPER_TOOL`, `WEB_BROWSER`, `PRODUCTIVITY`, `UTILITY`, `MEDIA`, `OTHER`)
- `is_apple`: bool (Convenience helper: True if bundle ID starts with `com.apple.` or bundle path is in `/System/`)
- `is_user_app`: bool (Convenience helper: True if third-party or user application, enforcing SC-02 update immunity)

### `MacAppInventoryReport`
- `collection_method`: str (`"NATIVE_DARWIN_BUNDLE_SCAN"`, `"MOCK_PLATFORM_ADAPTER"`)
- `timestamp`: str (ISO 8601 UTC)
- `host_platform`: str
- `applications`: List[MacAppInfo]
- `total_applications_count`: int
- `system_managed_count`: int
- `vendor_managed_count`: int
- `user_managed_count`: int
- `warnings`: List[str]
- `unavailable_telemetry`: List[str]
- Methods:
  - `find_by_bundle_id(bundle_id: str) -> Optional[MacAppInfo]`
  - `find_by_name(name: str) -> Optional[MacAppInfo]`
  - `filter_by_ownership(ownership: ComponentOwnership) -> List[MacAppInfo]`
  - `filter_by_category(category: ApplicationCategory) -> List[MacAppInfo]`
  - `to_dict() -> Dict[str, Any]`

---

## 4. Query & Discovery Architecture

1. **Direct Bundle Traversal**:
   - Traverses standard roots: `/Applications`, `/System/Applications`, `/System/Applications/Utilities`, `~/Applications`, and `/System/Library/CoreServices/Applications`.
   - Locates `.app` directories.
   - Reads `<app>/Contents/Info.plist` using Python standard `plistlib` (supports XML and Apple binary formats).
   - Achieves high performance (~67ms for 80+ apps on host Apple Silicon).
2. **Optional Spotlight Supplementation**:
   - If `/usr/bin/mdfind` is accessible, executes tokenized `mdfind "kMDItemContentType == 'com.apple.application-bundle'"` with 3-second timeout (`shell=False`) to discover any custom-located application bundles.
3. **Deterministic Classification**:
   - Bundle IDs starting with `com.apple.` or paths located under `/System/` are tagged `SYSTEM_MANAGED` and `is_apple=True`.
   - Applications under `~/Applications` or user directories are tagged `USER_MANAGED`.
   - Standard third-party desktop tools under `/Applications` are tagged `VENDOR_MANAGED`.
   - Categories (`WEB_BROWSER`, `DEVELOPER_TOOL`, `PRODUCTIVITY`, `UTILITY`, `MEDIA`, `CORE_SYSTEM`) are inferred using well-defined bundle identifier patterns.
