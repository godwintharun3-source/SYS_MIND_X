# DAY 053: Read-Only macOS FSEvents-Based Filesystem Change Notifications Architecture

## Executive Summary
Real-time awareness of system and application modifications is foundational to SYSTEM MIND X's Temporal Digital Twin. On macOS Darwin, the authoritative, kernel-assisted facility for monitoring filesystem events across large directory trees is the **File System Events (FSEvents)** subsystem provided by Apple's `CoreServices` framework.

Unlike legacy UNIX `kqueue(2)` or `poll(2)` which bind to individual file descriptors and rapidly exhaust process file limits on deep application bundles, FSEvents operates at the filesystem vnode layer. It aggregates hierarchical changes with bounded kernel latency, coalescing high-frequency events and reporting structural lifecycle mutations (file and directory creation, modification, deletion, attribute changes, symlinks, and clones).

In strict adherence to the SYSTEM MIND X charter—specifically `SC-01` (Zero Ambient Shell Authority & Read-Only Invariance) and explicit privacy boundaries forbidding default observation of personal user directories—Day 053 establishes a passive, non-mutating FSEvents telemetry engine.

---

## 1. Architectural Foundations & Invariants

| Invariant | Description | Enforcement Method |
|---|---|---|
| `SC-01` / `INV-FS-01` | **Zero Ambient Shell Authority & Pure Read-Only Observation**: The engine monitors change notifications passively. No mutating filesystem commands (`rm`, `mkdir`, `touch`, `chmod`, `chown`) are executed. Subprocess calls enforce `shell=False`. | Static AST safety analysis, validator checks, and contract tests |
| `INV-FS-02` | **Privacy-Preserving Monitored Roots & Exclusions**: Personal document folders (`~/Documents`, `~/Downloads`, `~/.ssh`, `~/Library/Keychains`, credentials) are strictly excluded from automated default monitoring. Only explicit system roots (`/Applications`, `/System/Applications`, `/Library/LaunchDaemons`, `/tmp`) or user-configured directories are monitored. | Deterministic path exclusion filter |
| `INV-FS-03` | **Event Flag Classification & Lifecycle Modeling**: Decodes native 32-bit Darwin bitmask flags into categorical lifecycle events (`ItemCreated`, `ItemRemoved`, `ItemModified`, `ItemRenamed`, `ItemInodeMetaMod`, `ItemXattrMod`, `ItemChangeOwner`, `ItemCloned`, `MustScanSubDirs`) with structural type flags (`is_file`, `is_dir`, `is_symlink`). | Bitmask decoding and enum mapping |
| `INV-FS-04` | **Coalescing & Latency Throttling**: Supports configurable notification coalescence latency (default 0.5s–1.0s) and bounded event queues to prevent event storms during large batch installations or compiler builds. | Configurable stream latency and ring buffer queue |
| `INV-FS-05` | **Graceful Non-Darwin Fallback & Mock Subsystem**: On Linux, Windows, or non-Darwin CI, the engine delegates to `MockFsEventsAdapter`, providing deterministic Apple Silicon simulation fixtures without breaking cross-platform test suites. | Polymorphic engine design and MockPlatformAdapter integration |

---

## 2. CoreServices FSEvent Flag Bitmask Specification

Native macOS `FSEventStreamEventFlags` (from `<CoreServices/CoreServices.h>`):

```c
enum {
  kFSEventStreamEventFlagNone                = 0x00000000,
  kFSEventStreamEventFlagMustScanSubDirs     = 0x00000001,
  kFSEventStreamEventFlagUserDropped         = 0x00000002,
  kFSEventStreamEventFlagKernelDropped       = 0x00000004,
  kFSEventStreamEventFlagEventIdsWrapped     = 0x00000008,
  kFSEventStreamEventFlagHistoryDone         = 0x00000010,
  kFSEventStreamEventFlagRootChanged         = 0x00000020,
  kFSEventStreamEventFlagMount               = 0x00000040,
  kFSEventStreamEventFlagUnmount             = 0x00000080,
  kFSEventStreamEventFlagItemCreated         = 0x00000100,
  kFSEventStreamEventFlagItemRemoved         = 0x00000200,
  kFSEventStreamEventFlagItemInodeMetaMod    = 0x00000400,
  kFSEventStreamEventFlagItemRenamed         = 0x00000800,
  kFSEventStreamEventFlagItemModified        = 0x00001000,
  kFSEventStreamEventFlagItemFinderInfoMod   = 0x00002000,
  kFSEventStreamEventFlagItemChangeOwner     = 0x00004000,
  kFSEventStreamEventFlagItemXattrMod        = 0x00008000,
  kFSEventStreamEventFlagItemIsFile          = 0x00010000,
  kFSEventStreamEventFlagItemIsDir           = 0x00020000,
  kFSEventStreamEventFlagItemIsSymlink       = 0x00040000,
  kFSEventStreamEventFlagItemOwnEvent        = 0x00080000,
  kFSEventStreamEventFlagItemIsHardlink      = 0x00100000,
  kFSEventStreamEventFlagItemIsLastHardlink  = 0x00200000,
  kFSEventStreamEventFlagItemCloned          = 0x00400000
};
```

---

## 3. Data Schema

### `FsEventFlag`
- `ITEM_CREATED`: New file or directory created
- `ITEM_REMOVED`: Item unlinked / deleted
- `ITEM_MODIFIED`: Content data modified
- `ITEM_RENAMED`: Item renamed or moved
- `ITEM_INODE_META_MOD`: POSIX inode metadata changed (permissions, timestamps)
- `ITEM_XATTR_MOD`: Extended attributes modified
- `ITEM_CHANGE_OWNER`: UID/GID ownership altered
- `ITEM_CLONED`: APFS block clone created
- `ITEM_IS_FILE`: Target is a regular file
- `ITEM_IS_DIR`: Target is a directory
- `ITEM_IS_SYMLINK`: Target is a symbolic link
- `MUST_SCAN_SUBDIRS`: Coalesced event requiring directory rescanning
- `MOUNT`: Filesystem mount point attached
- `UNMOUNT`: Filesystem mount point detached
- `UNKNOWN`: Unrecognized or future flag

### `FsEventNotification`
- `event_id`: int (monotonic uint64 event identifier)
- `path`: str (absolute normalized filesystem path)
- `flags`: List[FsEventFlag] (categorical decoded flags)
- `raw_flags`: int (raw 32-bit Darwin bitmask)
- `timestamp`: str (ISO 8601 UTC timestamp)
- `is_file`: bool
- `is_dir`: bool
- `is_symlink`: bool

### `FsEventSnapshotReport`
- `collection_method`: str (`"NATIVE_DARWIN_FSEVENTS"`, `"MOCK_PLATFORM_ADAPTER"`)
- `timestamp`: str (ISO 8601 UTC)
- `host_platform`: str
- `monitored_paths`: List[str]
- `events`: List[FsEventNotification]
- `events_count`: int
- `created_count`: int
- `modified_count`: int
- `removed_count`: int
- `renamed_count`: int
- `warnings`: List[str]
- `unavailable_telemetry`: List[str]

---

## 4. Operational Telemetry & Component Boundaries

1. **Python Telemetry Engine (`src/system_mind/macos/fsevents_detector.py`)**:
   - Manages passive notification listening, bitfield decoding, and path exclusion checks.
   - Provides `MacFsEventsDetector` supporting snapshot polling, streaming event generators, and deterministic mock event profiles.
2. **Native Rust Sensor Collector (`crates/system-mind-sensors/src/macos_fsevents.rs`)**:
   - Mirrors data contracts in Rust with `FsEventFlagSnapshot`, `FsEventNotificationSnapshot`, `FsEventReportSnapshot`, and `MockMacOsFsEventsCollector`.
3. **Developer CLI (`tools/monitor_fsevents.py`)**:
   - Allows operators to test and inspect filesystem event streams in real time with formatted tables or JSON output.
4. **Packaging Validator (`src/system_mind/packaging/macos_fsevents.py`)**:
   - Audits AST for zero mutating file commands, verifies zero `shell=True`, and tests CLI execution.
