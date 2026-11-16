//! macOS Darwin battery state, power source, and health telemetry sensor collector.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PowerSourceState {
    BatteryPower,
    AcPower,
    UpsPower,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BatteryConditionState {
    Normal,
    ReplaceSoon,
    ReplaceNow,
    ServiceBattery,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacOsBatterySnapshot {
    pub is_battery_present: bool,
    pub power_source: PowerSourceState,
    pub state_of_charge_pct: Option<u8>,
    pub is_charging: bool,
    pub is_fully_charged: bool,
    pub is_ac_connected: bool,
    pub time_remaining_mins: Option<u32>,
    pub cycle_count: Option<u32>,
    pub condition: BatteryConditionState,
    pub maximum_capacity_pct: Option<u8>,
    pub is_mock: bool,
}

impl MacOsBatterySnapshot {
    pub fn to_json_summary(&self) -> String {
        format!(
            "{{\"battery_present\":{},\"power_source\":\"{:?}\",\"charge_pct\":{},\"charging\":{},\"ac_connected\":{},\"cycles\":{},\"max_cap\":{},\"mock\":{}}}",
            self.is_battery_present,
            self.power_source,
            self.state_of_charge_pct.map_or("null".to_string(), |v| v.to_string()),
            self.is_charging,
            self.is_ac_connected,
            self.cycle_count.map_or("null".to_string(), |v| v.to_string()),
            self.maximum_capacity_pct.map_or("null".to_string(), |v| v.to_string()),
            self.is_mock
        )
    }
}

pub trait MacOsBatteryCollector: Send + Sync {
    fn collect_battery(&self) -> MacOsBatterySnapshot;
}

/// Safe mock collector simulating macOS power and battery conditions without host interaction.
#[derive(Debug, Clone)]
pub struct MockMacOsBatteryCollector {
    pub is_battery_present: bool,
    pub power_source: PowerSourceState,
    pub charge_pct: u8,
    pub is_charging: bool,
    pub cycle_count: u32,
    pub condition: BatteryConditionState,
    pub max_capacity_pct: u8,
}

impl Default for MockMacOsBatteryCollector {
    fn default() -> Self {
        Self {
            is_battery_present: true,
            power_source: PowerSourceState::BatteryPower,
            charge_pct: 78,
            is_charging: false,
            cycle_count: 182,
            condition: BatteryConditionState::Normal,
            max_capacity_pct: 95,
        }
    }
}

impl MockMacOsBatteryCollector {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_ac_connected() -> Self {
        Self {
            is_battery_present: true,
            power_source: PowerSourceState::AcPower,
            charge_pct: 100,
            is_charging: false,
            cycle_count: 182,
            condition: BatteryConditionState::Normal,
            max_capacity_pct: 95,
        }
    }

    pub fn constrained_battery() -> Self {
        Self {
            is_battery_present: true,
            power_source: PowerSourceState::BatteryPower,
            charge_pct: 14,
            is_charging: false,
            cycle_count: 350,
            condition: BatteryConditionState::Normal,
            max_capacity_pct: 88,
        }
    }

    pub fn desktop_mac() -> Self {
        Self {
            is_battery_present: false,
            power_source: PowerSourceState::AcPower,
            charge_pct: 0,
            is_charging: false,
            cycle_count: 0,
            condition: BatteryConditionState::Unknown,
            max_capacity_pct: 0,
        }
    }
}

impl MacOsBatteryCollector for MockMacOsBatteryCollector {
    fn collect_battery(&self) -> MacOsBatterySnapshot {
        if !self.is_battery_present {
            return MacOsBatterySnapshot {
                is_battery_present: false,
                power_source: PowerSourceState::AcPower,
                state_of_charge_pct: None,
                is_charging: false,
                is_fully_charged: false,
                is_ac_connected: true,
                time_remaining_mins: None,
                cycle_count: None,
                condition: BatteryConditionState::Unknown,
                maximum_capacity_pct: None,
                is_mock: true,
            };
        }

        let is_ac = self.power_source == PowerSourceState::AcPower;
        let is_full = self.charge_pct >= 100;

        MacOsBatterySnapshot {
            is_battery_present: true,
            power_source: self.power_source,
            state_of_charge_pct: Some(self.charge_pct),
            is_charging: self.is_charging,
            is_fully_charged: is_full,
            is_ac_connected: is_ac,
            time_remaining_mins: if is_ac { Some(45) } else { Some(180) },
            cycle_count: Some(self.cycle_count),
            condition: self.condition,
            maximum_capacity_pct: Some(self.max_capacity_pct),
            is_mock: true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mock_macos_battery_collection() {
        let collector = MockMacOsBatteryCollector::new();
        let snapshot = collector.collect_battery();

        assert!(snapshot.is_battery_present);
        assert_eq!(snapshot.power_source, PowerSourceState::BatteryPower);
        assert_eq!(snapshot.state_of_charge_pct, Some(78));
        assert!(!snapshot.is_charging);
        assert!(!snapshot.is_fully_charged);
        assert!(!snapshot.is_ac_connected);
        assert_eq!(snapshot.cycle_count, Some(182));
        assert_eq!(snapshot.condition, BatteryConditionState::Normal);
        assert_eq!(snapshot.maximum_capacity_pct, Some(95));
        assert!(snapshot.is_mock);
    }

    #[test]
    fn test_mock_macos_battery_constrained_and_desktop() {
        let low_batt = MockMacOsBatteryCollector::constrained_battery();
        let snap_low = low_batt.collect_battery();
        assert_eq!(snap_low.state_of_charge_pct, Some(14));
        assert!(!snap_low.is_ac_connected);

        let desktop = MockMacOsBatteryCollector::desktop_mac();
        let snap_desk = desktop.collect_battery();
        assert!(!snap_desk.is_battery_present);
        assert_eq!(snap_desk.power_source, PowerSourceState::AcPower);
        assert!(snap_desk.is_ac_connected);
        assert_eq!(snap_desk.state_of_charge_pct, None);
        assert_eq!(snap_desk.cycle_count, None);
    }

    #[test]
    fn test_mock_macos_battery_json_serialization() {
        let collector = MockMacOsBatteryCollector::with_ac_connected();
        let snapshot = collector.collect_battery();
        let json = snapshot.to_json_summary();

        assert!(json.contains("\"battery_present\":true"));
        assert!(json.contains("\"charge_pct\":100"));
        assert!(json.contains("\"ac_connected\":true"));
        assert!(json.contains("\"cycles\":182"));
        assert!(json.contains("\"max_cap\":95"));
    }
}
