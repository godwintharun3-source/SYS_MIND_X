"""Read-only macOS battery state, power source, and health telemetry detector."""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

from system_mind.macos.battery_models import (
    BatteryChargingState,
    BatteryHealthCondition,
    MacBatteryHealthInfo,
    MacBatteryTelemetryReport,
    PowerSource,
)

logger = logging.getLogger(__name__)

_SERIAL_SALT = "sysmind-battery-salt:"


class MacBatteryDetector:
    """Read-only, passive introspection engine for macOS battery, power source, and health."""

    def __init__(self, salt: str = _SERIAL_SALT) -> None:
        self._salt = salt

    def anonymize_serial(self, raw_serial: Optional[str]) -> Optional[str]:
        """Anonymize hardware battery serial numbers using a salted SHA-256 digest (INV-BAT-02)."""
        if not raw_serial or not raw_serial.strip():
            return None
        clean_serial = raw_serial.strip()
        digest = hashlib.sha256(f"{self._salt}{clean_serial}".encode("utf-8")).hexdigest()[:16]
        return f"sha256:{digest}"

    def parse_condition_string(self, raw_condition: Optional[str]) -> BatteryHealthCondition:
        """Map raw Darwin condition strings to strongly typed BatteryHealthCondition enum."""
        if not raw_condition:
            return BatteryHealthCondition.UNKNOWN
        cond_lower = raw_condition.strip().lower()
        if "normal" in cond_lower or "good" in cond_lower:
            return BatteryHealthCondition.NORMAL
        elif "replace soon" in cond_lower or "fair" in cond_lower:
            return BatteryHealthCondition.REPLACE_SOON
        elif "replace now" in cond_lower or "poor" in cond_lower:
            return BatteryHealthCondition.REPLACE_NOW
        elif "service" in cond_lower or "check" in cond_lower:
            return BatteryHealthCondition.SERVICE_BATTERY
        return BatteryHealthCondition.UNKNOWN

    def parse_pmset_output(self, output: str) -> Dict[str, Any]:
        """Parse text output from unprivileged `pmset -g batt` command."""
        result: Dict[str, Any] = {
            "power_source": PowerSource.UNKNOWN,
            "is_battery_present": False,
            "state_of_charge_percent": None,
            "charging_state": BatteryChargingState.UNKNOWN,
            "is_charging": False,
            "is_fully_charged": False,
            "is_ac_connected": False,
            "time_remaining_minutes": None,
        }

        if not output:
            return result

        lines = [line.strip() for line in output.splitlines() if line.strip()]

        for line in lines:
            if line.startswith("Now drawing from"):
                if "'Battery Power'" in line or "Battery Power" in line:
                    result["power_source"] = PowerSource.BATTERY_POWER
                    result["is_ac_connected"] = False
                elif "'AC Power'" in line or "AC Power" in line:
                    result["power_source"] = PowerSource.AC_POWER
                    result["is_ac_connected"] = True
                elif "'UPS Power'" in line or "UPS Power" in line:
                    result["power_source"] = PowerSource.UPS_POWER
                    result["is_ac_connected"] = False

            elif "InternalBattery" in line:
                result["is_battery_present"] = True

                # Parse percentage: e.g. "42%;"
                pct_match = re.search(r"(\d+)%", line)
                if pct_match:
                    result["state_of_charge_percent"] = int(pct_match.group(1))

                # Parse charging dynamics
                line_lower = line.lower()
                if "discharging" in line_lower:
                    result["charging_state"] = BatteryChargingState.DISCHARGING
                    result["is_charging"] = False
                elif "finishing charge" in line_lower:
                    result["charging_state"] = BatteryChargingState.FINISHING_CHARGE
                    result["is_charging"] = True
                elif "charging" in line_lower and "not charging" not in line_lower:
                    result["charging_state"] = BatteryChargingState.CHARGING
                    result["is_charging"] = True
                elif "charged" in line_lower:
                    result["charging_state"] = BatteryChargingState.CHARGED
                    result["is_charging"] = False
                    result["is_fully_charged"] = True
                elif "not charging" in line_lower or "ac attached" in line_lower:
                    result["charging_state"] = BatteryChargingState.NOT_CHARGING
                    result["is_charging"] = False

                # Parse time remaining: e.g. "4:24 remaining"
                time_match = re.search(r"(\d+):(\d+)\s+remaining", line)
                if time_match:
                    hours = int(time_match.group(1))
                    mins = int(time_match.group(2))
                    result["time_remaining_minutes"] = hours * 60 + mins

        return result

    def parse_system_profiler_output(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse structured dictionary from `system_profiler SPPowerDataType -json`."""
        result: Dict[str, Any] = {
            "has_battery_info": False,
            "cycle_count": None,
            "condition": BatteryHealthCondition.UNKNOWN,
            "maximum_capacity_percent": None,
            "device_name": None,
            "anonymized_serial_hash": None,
            "firmware_version": None,
            "is_below_warning_level": False,
            "is_charging": False,
            "is_fully_charged": False,
            "is_ac_charger_connected": False,
            "state_of_charge_percent": None,
            "is_low_power_mode_active": False,
        }

        power_items = data.get("SPPowerDataType", [])
        if not isinstance(power_items, list):
            return result

        for item in power_items:
            if not isinstance(item, dict):
                continue

            name = item.get("_name", "")

            if name == "spbattery_information":
                result["has_battery_info"] = True

                # Charge info
                charge_info = item.get("sppower_battery_charge_info", {})
                if isinstance(charge_info, dict):
                    warn = str(charge_info.get("sppower_battery_at_warn_level", "")).upper()
                    result["is_below_warning_level"] = (warn == "TRUE" or warn == "YES")

                    full = str(charge_info.get("sppower_battery_fully_charged", "")).upper()
                    result["is_fully_charged"] = (full == "TRUE" or full == "YES")

                    chg = str(charge_info.get("sppower_battery_is_charging", "")).upper()
                    result["is_charging"] = (chg == "TRUE" or chg == "YES")

                    soc = charge_info.get("sppower_battery_state_of_charge")
                    if isinstance(soc, (int, float)):
                        result["state_of_charge_percent"] = int(soc)

                # Health info
                health_info = item.get("sppower_battery_health_info", {})
                if isinstance(health_info, dict):
                    cycles = health_info.get("sppower_battery_cycle_count")
                    if isinstance(cycles, (int, float)):
                        result["cycle_count"] = int(cycles)

                    cond_str = health_info.get("sppower_battery_health")
                    if isinstance(cond_str, str):
                        result["condition"] = self.parse_condition_string(cond_str)

                    max_cap = health_info.get("sppower_battery_health_maximum_capacity")
                    if isinstance(max_cap, str) and "%" in max_cap:
                        digits = re.sub(r"[^\d]", "", max_cap)
                        if digits:
                            result["maximum_capacity_percent"] = int(digits)
                    elif isinstance(max_cap, (int, float)):
                        result["maximum_capacity_percent"] = int(max_cap)

                # Model info
                model_info = item.get("sppower_battery_model_info", {})
                if isinstance(model_info, dict):
                    dev_name = model_info.get("sppower_battery_device_name")
                    if isinstance(dev_name, str):
                        result["device_name"] = dev_name.strip()

                    firmware = model_info.get("sppower_battery_firmware_version")
                    if isinstance(firmware, str):
                        result["firmware_version"] = firmware.strip()

                    raw_serial = model_info.get("sppower_battery_serial_number")
                    if isinstance(raw_serial, str):
                        result["anonymized_serial_hash"] = self.anonymize_serial(raw_serial)

            elif name == "sppower_information":
                # Check low power mode
                batt_power = item.get("Battery Power", {})
                if isinstance(batt_power, dict):
                    lpm = str(batt_power.get("LowPowerMode", "")).lower()
                    if lpm in ("yes", "true", "1"):
                        result["is_low_power_mode_active"] = True

                ac_power = item.get("AC Power", {})
                if isinstance(ac_power, dict) and not result["is_low_power_mode_active"]:
                    lpm = str(ac_power.get("LowPowerMode", "")).lower()
                    if lpm in ("yes", "true", "1"):
                        result["is_low_power_mode_active"] = True

            elif name == "sppower_ac_charger_information":
                conn = str(item.get("sppower_battery_charger_connected", "")).upper()
                result["is_ac_charger_connected"] = (conn == "TRUE" or conn == "YES")

        return result

    def detect(
        self,
        use_mock: bool = False,
        mock_adapter: Optional[Any] = None,
    ) -> MacBatteryTelemetryReport:
        """Collect battery state, charging dynamics, and health metrics."""
        if use_mock:
            return self._detect_via_mock(mock_adapter)

        if platform.system() != "Darwin":
            logger.info("Non-Darwin platform detected; returning mock fallback.")
            return self._detect_via_mock(mock_adapter)

        return self._detect_via_darwin()

    def _detect_via_darwin(self) -> MacBatteryTelemetryReport:
        """Execute unprivileged pmset and system_profiler commands on macOS host."""
        unavailable: List[str] = []
        warnings: List[str] = []

        pmset_data: Dict[str, Any] = {}
        profiler_data: Dict[str, Any] = {}

        # 1. Query pmset -g batt
        try:
            pmset_proc = subprocess.run(
                ["/usr/bin/pmset", "-g", "batt"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if pmset_proc.returncode == 0:
                pmset_data = self.parse_pmset_output(pmset_proc.stdout)
            else:
                unavailable.append("/usr/bin/pmset -g batt")
                warnings.append(f"pmset exited with code {pmset_proc.returncode}: {pmset_proc.stderr.strip()}")
        except Exception as exc:
            unavailable.append("/usr/bin/pmset -g batt")
            warnings.append(f"Failed to execute pmset: {exc}")

        # 2. Query system_profiler SPPowerDataType -json
        try:
            prof_proc = subprocess.run(
                ["/usr/sbin/system_profiler", "SPPowerDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if prof_proc.returncode == 0 and prof_proc.stdout.strip():
                try:
                    parsed_json = json.loads(prof_proc.stdout)
                    profiler_data = self.parse_system_profiler_output(parsed_json)
                except Exception as json_err:
                    warnings.append(f"Failed to parse system_profiler JSON: {json_err}")
            else:
                unavailable.append("/usr/sbin/system_profiler SPPowerDataType")
                warnings.append(f"system_profiler exited with code {prof_proc.returncode}")
        except Exception as exc:
            unavailable.append("/usr/sbin/system_profiler SPPowerDataType")
            warnings.append(f"Failed to execute system_profiler: {exc}")

        # Determine battery presence
        is_battery_present = (
            pmset_data.get("is_battery_present", False)
            or profiler_data.get("has_battery_info", False)
        )

        # Power source deduction
        power_source = pmset_data.get("power_source", PowerSource.UNKNOWN)
        if power_source == PowerSource.UNKNOWN:
            if not is_battery_present or profiler_data.get("is_ac_charger_connected", False):
                power_source = PowerSource.AC_POWER
            else:
                power_source = PowerSource.BATTERY_POWER

        # State of charge %
        soc = pmset_data.get("state_of_charge_percent")
        if soc is None:
            soc = profiler_data.get("state_of_charge_percent")

        # Charging state
        charging_state = pmset_data.get("charging_state", BatteryChargingState.UNKNOWN)
        is_charging = pmset_data.get("is_charging", False) or profiler_data.get("is_charging", False)
        is_fully_charged = pmset_data.get("is_fully_charged", False) or profiler_data.get("is_fully_charged", False)

        is_ac_connected = (
            pmset_data.get("is_ac_connected", False)
            or profiler_data.get("is_ac_charger_connected", False)
            or (power_source == PowerSource.AC_POWER)
        )

        time_remaining = pmset_data.get("time_remaining_minutes")
        below_warning = profiler_data.get("is_below_warning_level", False)
        low_power_mode = profiler_data.get("is_low_power_mode_active", False)

        # Build health info if battery is present
        health_info: Optional[MacBatteryHealthInfo] = None
        if is_battery_present:
            health_info = MacBatteryHealthInfo(
                cycle_count=profiler_data.get("cycle_count"),
                condition=profiler_data.get("condition", BatteryHealthCondition.UNKNOWN),
                maximum_capacity_percent=profiler_data.get("maximum_capacity_percent"),
                device_name=profiler_data.get("device_name"),
                anonymized_serial_hash=profiler_data.get("anonymized_serial_hash"),
                firmware_version=profiler_data.get("firmware_version"),
            )

        return MacBatteryTelemetryReport(
            is_battery_present=is_battery_present,
            current_power_source=power_source,
            state_of_charge_percent=soc,
            charging_state=charging_state,
            is_charging=is_charging,
            is_fully_charged=is_fully_charged,
            is_ac_connected=is_ac_connected,
            time_remaining_minutes=time_remaining,
            is_below_warning_level=below_warning,
            is_low_power_mode_active=low_power_mode,
            health=health_info,
            collected_at_epoch_secs=time.time(),
            collection_method="NATIVE_DARWIN_PMSET_SYSTEM_PROFILER",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )

    def _detect_via_mock(self, mock_adapter: Optional[Any] = None) -> MacBatteryTelemetryReport:
        """Generate deterministic simulated battery telemetry report."""
        power_source = PowerSource.BATTERY_POWER
        battery_pct = 78
        is_charging = False
        is_ac_connected = False
        low_power_mode = False

        if mock_adapter is not None and hasattr(mock_adapter, "get_hardware_telemetry"):
            hw = mock_adapter.get_hardware_telemetry()
            raw_source = getattr(hw, "power_source", "BATTERY")
            if "AC" in str(raw_source).upper():
                power_source = PowerSource.AC_POWER
                is_ac_connected = True
            else:
                power_source = PowerSource.BATTERY_POWER
                is_ac_connected = False

            pct_val = getattr(hw, "battery_pct", None)
            if pct_val is not None:
                battery_pct = int(pct_val)
            is_charging = bool(getattr(hw, "is_charging", False))

        charging_state = (
            BatteryChargingState.CHARGING if is_charging else BatteryChargingState.DISCHARGING
        )
        if is_ac_connected and battery_pct >= 100:
            charging_state = BatteryChargingState.CHARGED

        health = MacBatteryHealthInfo(
            cycle_count=182,
            condition=BatteryHealthCondition.NORMAL,
            maximum_capacity_percent=95,
            device_name="bq20z451",
            manufacturer="Apple",
            anonymized_serial_hash=self.anonymize_serial("MOCK-APPLE-BATTERY-PACK-2026"),
            firmware_version="0x00001002",
        )

        return MacBatteryTelemetryReport(
            is_battery_present=True,
            current_power_source=power_source,
            state_of_charge_percent=battery_pct,
            charging_state=charging_state,
            is_charging=is_charging,
            is_fully_charged=(battery_pct >= 100),
            is_ac_connected=is_ac_connected,
            time_remaining_minutes=180 if not is_charging else 45,
            is_below_warning_level=(battery_pct <= 15),
            is_low_power_mode_active=low_power_mode,
            health=health,
            collected_at_epoch_secs=time.time(),
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )
