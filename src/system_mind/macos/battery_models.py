"""Data models for macOS battery state, power sources, charging dynamics, and health telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List, Optional


class PowerSource(str, Enum):
    """Current power source supplying the host system."""

    BATTERY_POWER = "BATTERY_POWER"
    AC_POWER = "AC_POWER"
    UPS_POWER = "UPS_POWER"
    UNKNOWN = "UNKNOWN"


class BatteryHealthCondition(str, Enum):
    """Categorical assessment of battery cell health and service requirements."""

    NORMAL = "NORMAL"                # Good / Normal
    REPLACE_SOON = "REPLACE_SOON"    # Fair / Replace Soon
    REPLACE_NOW = "REPLACE_NOW"      # Poor / Replace Now
    SERVICE_BATTERY = "SERVICE_BATTERY"  # Service Battery / Check Battery
    UNKNOWN = "UNKNOWN"


class BatteryChargingState(str, Enum):
    """Current charging dynamic of the internal battery pack."""

    CHARGING = "CHARGING"
    DISCHARGING = "DISCHARGING"
    CHARGED = "CHARGED"
    FINISHING_CHARGE = "FINISHING_CHARGE"
    NOT_CHARGING = "NOT_CHARGING"    # Connected to AC, but charging held/paused
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MacBatteryHealthInfo:
    """Strongly typed battery health, cycle count, and wear degradation metrics."""

    cycle_count: Optional[int] = None
    condition: BatteryHealthCondition = BatteryHealthCondition.UNKNOWN
    maximum_capacity_percent: Optional[int] = None  # Health % (Apple Silicon)
    device_name: Optional[str] = None
    manufacturer: Optional[str] = None
    anonymized_serial_hash: Optional[str] = None    # Truncated SHA-256 digest (INV-BAT-02)
    firmware_version: Optional[str] = None


@dataclass(frozen=True)
class MacBatteryTelemetryReport:
    """Authoritative aggregated battery and power telemetry report for macOS companion agent."""

    is_battery_present: bool = True
    current_power_source: PowerSource = PowerSource.BATTERY_POWER
    state_of_charge_percent: Optional[int] = None
    charging_state: BatteryChargingState = BatteryChargingState.UNKNOWN
    is_charging: bool = False
    is_fully_charged: bool = False
    is_ac_connected: bool = False
    time_remaining_minutes: Optional[int] = None
    is_below_warning_level: bool = False
    is_low_power_mode_active: bool = False
    health: Optional[MacBatteryHealthInfo] = None
    collected_at_epoch_secs: float = field(default_factory=time.time)
    collection_method: str = "NATIVE_DARWIN_PMSET_SYSTEM_PROFILER"
    unavailable_telemetry: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
