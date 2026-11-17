//! macOS Darwin FSEvents filesystem change notification sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FsEventFlagSnapshot {
    ItemCreated,
    ItemRemoved,
    ItemModified,
    ItemRenamed,
    ItemInodeMetaMod,
    ItemXattrMod,
    ItemChangeOwner,
    ItemCloned,
    ItemIsFile,
    ItemIsDir,
    ItemIsSymlink,
    MustScanSubDirs,
    Mount,
    Unmount,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FsEventNotificationSnapshot {
    pub event_id: u64,
    pub path: String,
    pub flags: Vec<FsEventFlagSnapshot>,
    pub raw_flags: u32,
    pub timestamp: String,
    pub is_file: bool,
    pub is_dir: bool,
    pub is_symlink: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FsEventSnapshotReportSnapshot {
    pub events: Vec<FsEventNotificationSnapshot>,
    pub monitored_paths: Vec<String>,
    pub events_count: usize,
    pub created_count: usize,
    pub modified_count: usize,
    pub removed_count: usize,
    pub renamed_count: usize,
    pub is_mock: bool,
}

pub type FsEventReportSnapshot = FsEventSnapshotReportSnapshot;

impl FsEventSnapshotReportSnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"events_count\":{},\"created\":{},\"modified\":{},\"removed\":{},\"renamed\":{},\"mock\":{}}}",
            self.events_count,
            self.created_count,
            self.modified_count,
            self.removed_count,
            self.renamed_count,
            self.is_mock
        )
    }

    pub fn find_by_path(&self, target_path: &str) -> Option<&FsEventNotificationSnapshot> {
        let clean = target_path.to_lowercase();
        self.events.iter().find(|e| e.path.to_lowercase() == clean)
    }

    pub fn find_by_flag(&self, flag: FsEventFlagSnapshot) -> Vec<&FsEventNotificationSnapshot> {
        self.events
            .iter()
            .filter(|e| e.flags.contains(&flag))
            .collect()
    }
}

pub trait MacOsFsEventsCollector: Send + Sync {
    fn collect_fsevents(&self) -> FsEventSnapshotReportSnapshot;
}

/// Deterministic mock collector providing Apple Silicon FSEvents change notifications.
#[derive(Debug, Clone)]
pub struct MockMacOsFsEventsCollector {
    pub events: Vec<FsEventNotificationSnapshot>,
    pub monitored_paths: Vec<String>,
    pub is_mock: bool,
}

impl MockMacOsFsEventsCollector {
    pub fn new_apple_silicon() -> Self {
        let ev1 = FsEventNotificationSnapshot {
            event_id: 1001,
            path: "/Applications/NewUtility.app".to_string(),
            flags: vec![
                FsEventFlagSnapshot::ItemCreated,
                FsEventFlagSnapshot::ItemIsDir,
            ],
            raw_flags: 0x00020100,
            timestamp: "2026-11-17T04:40:00Z".to_string(),
            is_file: false,
            is_dir: true,
            is_symlink: false,
        };

        let ev2 = FsEventNotificationSnapshot {
            event_id: 1002,
            path: "/System/Applications/Utilities/Terminal.app/Contents/Info.plist".to_string(),
            flags: vec![
                FsEventFlagSnapshot::ItemModified,
                FsEventFlagSnapshot::ItemIsFile,
            ],
            raw_flags: 0x00011000,
            timestamp: "2026-11-17T04:40:01Z".to_string(),
            is_file: true,
            is_dir: false,
            is_symlink: false,
        };

        let ev3 = FsEventNotificationSnapshot {
            event_id: 1003,
            path: "/Library/LaunchDaemons/com.example.service.plist".to_string(),
            flags: vec![
                FsEventFlagSnapshot::ItemCreated,
                FsEventFlagSnapshot::ItemInodeMetaMod,
                FsEventFlagSnapshot::ItemIsFile,
            ],
            raw_flags: 0x00010500,
            timestamp: "2026-11-17T04:40:02Z".to_string(),
            is_file: true,
            is_dir: false,
            is_symlink: false,
        };

        let ev4 = FsEventNotificationSnapshot {
            event_id: 1004,
            path: "/tmp/temporary_build_cache.tmp".to_string(),
            flags: vec![
                FsEventFlagSnapshot::ItemRemoved,
                FsEventFlagSnapshot::ItemIsFile,
            ],
            raw_flags: 0x00010200,
            timestamp: "2026-11-17T04:40:03Z".to_string(),
            is_file: true,
            is_dir: false,
            is_symlink: false,
        };

        let ev5 = FsEventNotificationSnapshot {
            event_id: 1005,
            path: "/Applications/OldTool.app".to_string(),
            flags: vec![
                FsEventFlagSnapshot::ItemRenamed,
                FsEventFlagSnapshot::ItemIsDir,
            ],
            raw_flags: 0x00020800,
            timestamp: "2026-11-17T04:40:04Z".to_string(),
            is_file: false,
            is_dir: true,
            is_symlink: false,
        };

        let events = vec![ev1, ev2, ev3, ev4, ev5];
        let monitored_paths = vec![
            "/Applications".to_string(),
            "/System/Applications".to_string(),
            "/Library/LaunchDaemons".to_string(),
            "/Library/LaunchAgents".to_string(),
            "/tmp".to_string(),
        ];

        Self {
            events,
            monitored_paths,
            is_mock: true,
        }
    }
}

impl MacOsFsEventsCollector for MockMacOsFsEventsCollector {
    fn collect_fsevents(&self) -> FsEventSnapshotReportSnapshot {
        let events_count = self.events.len();
        let created_count = self
            .events
            .iter()
            .filter(|e| e.flags.contains(&FsEventFlagSnapshot::ItemCreated))
            .count();
        let modified_count = self
            .events
            .iter()
            .filter(|e| e.flags.contains(&FsEventFlagSnapshot::ItemModified))
            .count();
        let removed_count = self
            .events
            .iter()
            .filter(|e| e.flags.contains(&FsEventFlagSnapshot::ItemRemoved))
            .count();
        let renamed_count = self
            .events
            .iter()
            .filter(|e| e.flags.contains(&FsEventFlagSnapshot::ItemRenamed))
            .count();

        FsEventSnapshotReportSnapshot {
            events: self.events.clone(),
            monitored_paths: self.monitored_paths.clone(),
            events_count,
            created_count,
            modified_count,
            removed_count,
            renamed_count,
            is_mock: self.is_mock,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_fsevents_collector() {
        let collector = MockMacOsFsEventsCollector::new_apple_silicon();
        let report = collector.collect_fsevents();

        assert_eq!(report.events_count, 5);
        assert_eq!(report.created_count, 2);
        assert_eq!(report.modified_count, 1);
        assert_eq!(report.removed_count, 1);
        assert_eq!(report.renamed_count, 1);
        assert!(report.is_mock);

        let new_app = report.find_by_path("/Applications/NewUtility.app").unwrap();
        assert_eq!(new_app.event_id, 1001);
        assert!(new_app.flags.contains(&FsEventFlagSnapshot::ItemCreated));
        assert!(new_app.is_dir);
        assert!(!new_app.is_file);

        let term_plist = report
            .find_by_path("/System/Applications/Utilities/Terminal.app/Contents/Info.plist")
            .unwrap();
        assert!(term_plist
            .flags
            .contains(&FsEventFlagSnapshot::ItemModified));
        assert!(term_plist.is_file);

        let summary = report.to_json_summary();
        assert!(summary.contains("\"events_count\":5"));
        assert!(summary.contains("\"created\":2"));
        assert!(summary.contains("\"mock\":true"));
    }

    #[test]
    fn test_fsevents_filtering_by_flag() {
        let collector = MockMacOsFsEventsCollector::new_apple_silicon();
        let report = collector.collect_fsevents();

        let created_events = report.find_by_flag(FsEventFlagSnapshot::ItemCreated);
        assert_eq!(created_events.len(), 2);

        let removed_events = report.find_by_flag(FsEventFlagSnapshot::ItemRemoved);
        assert_eq!(removed_events.len(), 1);
        assert_eq!(removed_events[0].path, "/tmp/temporary_build_cache.tmp");
    }

    #[test]
    fn test_fsevents_nonexistent_path_lookup() {
        let collector = MockMacOsFsEventsCollector::new_apple_silicon();
        let report = collector.collect_fsevents();

        assert!(report.find_by_path("/nonexistent/path").is_none());
    }
}
