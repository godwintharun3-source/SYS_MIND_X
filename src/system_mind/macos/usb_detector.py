"""Read-only macOS USB and peripheral inventory telemetry detector with privacy constraints."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import logging
from pathlib import Path
import platform
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.usb_models import (
    MacUsbController,
    MacUsbDevice,
    MacUsbReport,
    UsbDeviceClass,
    UsbSpeed,
)

logger = logging.getLogger(__name__)

_USB_SALT = "sysmind-usb-salt:"


class MacUsbDetector:
    """Read-only, passive introspection engine for macOS USB host controllers and peripherals."""

    def __init__(self, salt: str = _USB_SALT) -> None:
        self._salt = salt

    def anonymize_serial(self, raw_serial: Optional[str]) -> Optional[str]:
        """Anonymize hardware peripheral serial numbers using a salted SHA-256 digest (INV-USB-02)."""
        if not raw_serial or not str(raw_serial).strip():
            return None
        clean_serial = str(raw_serial).strip().lower()
        digest = hashlib.sha256(f"{self._salt}{clean_serial}".encode("utf-8")).hexdigest()[:16]
        return f"sha256:{digest}"

    def classify_speed(self, speed_str: Optional[str]) -> UsbSpeed:
        """Classify USB signaling speed string into UsbSpeed enum."""
        if not speed_str:
            return UsbSpeed.UNKNOWN
        s = speed_str.lower()
        if "1.5" in s or "low" in s:
            return UsbSpeed.LOW_SPEED_1_5_MBPS
        elif "12" in s or "full" in s:
            return UsbSpeed.FULL_SPEED_12_MBPS
        elif "480" in s or "high" in s:
            return UsbSpeed.HIGH_SPEED_480_MBPS
        elif "40" in s or "usb4" in s:
            return UsbSpeed.USB4_40_GBPS
        elif "20" in s:
            return UsbSpeed.SUPER_SPEED_PLUS_20_GBPS
        elif "10" in s:
            return UsbSpeed.SUPER_SPEED_PLUS_10_GBPS
        elif "5" in s or "super" in s:
            return UsbSpeed.SUPER_SPEED_5_GBPS
        return UsbSpeed.UNKNOWN

    def classify_device(
        self,
        name: str,
        manufacturer: Optional[str] = None,
        is_hub: bool = False,
    ) -> UsbDeviceClass:
        """Categorize peripheral functionality into UsbDeviceClass enum."""
        if is_hub or "hub" in name.lower():
            return UsbDeviceClass.HUB

        text = f"{name} {manufacturer or ''}".lower()

        # Security tokens (YubiKey, smartcards, FIDO2/U2F)
        if any(k in text for k in ["yubikey", "smartcard", "fido", "ccid", "nitrokey", "solo", "titan", "authenticator", "token"]):
            return UsbDeviceClass.SECURITY_TOKEN

        # Human interface devices
        if any(k in text for k in ["keyboard", "trackpad", "mouse", "touchpad", "gamepad", "joystick", "tablet", "hid", "remote"]):
            return UsbDeviceClass.HUMAN_INTERFACE

        # Mass storage (flash drives, SSDs, external disks)
        if any(k in text for k in ["storage", "disk", "flash", "sandisk", "cruzer", "mass storage", "drive", "card reader"]):
            return UsbDeviceClass.MASS_STORAGE

        # Audio / Video
        if any(k in text for k in ["audio", "microphone", "headset", "speaker", "dac", "camera", "facetime", "webcam", "video"]):
            return UsbDeviceClass.AUDIO_VIDEO

        # Communications / Networking
        if any(k in text for k in ["ethernet", "modem", "wwan", "nic", "network", "lan", "rtl8153", "ax88179"]):
            return UsbDeviceClass.COMMUNICATIONS

        # Wireless receivers
        if any(k in text for k in ["bluetooth", "wireless", "rf receiver", "unifying"]):
            return UsbDeviceClass.WIRELESS

        # Printers
        if any(k in text for k in ["printer", "laserjet", "deskjet"]):
            return UsbDeviceClass.PRINTER

        return UsbDeviceClass.OTHER

    def is_device_builtin(self, name: str, location_id: Optional[str] = None) -> bool:
        """Determine whether the device is internal / built into the host chassis."""
        n = name.lower()
        if any(k in n for k in [
            "apple internal",
            "facetime",
            "ambient light",
            "headset",
            "t2",
            "touch bar",
            "bcm20702",
        ]):
            return True
        if location_id and "built-in" in location_id.lower():
            return True
        return False

    def parse_current_ma(self, raw_val: Any) -> Optional[int]:
        """Safely parse electrical current in milliamps."""
        if raw_val is None:
            return None
        if isinstance(raw_val, int):
            return raw_val
        val_str = str(raw_val).strip()
        match = re.search(r"(\d+)", val_str)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def parse_device_item(self, item: Dict[str, Any]) -> MacUsbDevice:
        """Recursively parse a USB device dictionary and downstream connected hub items."""
        name = item.get("_name", "Unknown USB Device")
        vendor_id = item.get("vendor_id")
        product_id = item.get("product_id")
        manufacturer = item.get("manufacturer")
        raw_serial = item.get("serial_num")
        anonymized_serial = self.anonymize_serial(raw_serial)

        raw_items = item.get("_items", [])
        is_hub = "hub" in name.lower() or bool(raw_items)

        children: List[MacUsbDevice] = []
        if isinstance(raw_items, list):
            for child_item in raw_items:
                if isinstance(child_item, dict):
                    children.append(self.parse_device_item(child_item))

        device_class = self.classify_device(name, manufacturer, is_hub=is_hub)
        speed_text = item.get("speed")
        speed = self.classify_speed(speed_text)
        location_id = item.get("location_id")
        is_builtin = self.is_device_builtin(name, location_id)

        bus_power = self.parse_current_ma(item.get("bus_power"))
        current_used = self.parse_current_ma(item.get("bus_power_used"))
        extra_current = self.parse_current_ma(item.get("extra_current_used"))
        bcd_device = item.get("bcd_device")

        return MacUsbDevice(
            name=name,
            vendor_id=vendor_id,
            product_id=product_id,
            manufacturer=manufacturer,
            anonymized_serial_hash=anonymized_serial,
            device_class=device_class,
            speed=speed,
            speed_text=speed_text,
            location_id=location_id,
            bus_power_ma=bus_power,
            current_used_ma=current_used,
            extra_current_ma=extra_current,
            bcd_device=bcd_device,
            is_builtin=is_builtin,
            is_hub=is_hub,
            children=children,
        )

    def flatten_devices(self, devices: List[MacUsbDevice]) -> List[MacUsbDevice]:
        """Return a flat list of all devices including nested hub children."""
        flat: List[MacUsbDevice] = []
        for dev in devices:
            flat.append(dev)
            if dev.children:
                flat.extend(self.flatten_devices(dev.children))
        return flat

    def parse_spusb_json(
        self,
        data: Dict[str, Any],
    ) -> Tuple[List[MacUsbController], List[str]]:
        """Parse dictionary output from unprivileged `system_profiler SPUSBDataType -json`."""
        controllers: List[MacUsbController] = []
        warnings: List[str] = []

        raw_items = data.get("SPUSBDataType", [])
        if not isinstance(raw_items, list):
            warnings.append("SPUSBDataType root element is not a JSON list")
            return controllers, warnings

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            ctrl_name = item.get("_name", "USB Bus")
            host_ctrl = item.get("host_controller")
            pci_device = item.get("pci_device")
            pci_vendor = item.get("pci_vendor")

            devices: List[MacUsbDevice] = []
            dev_items = item.get("_items", [])
            if isinstance(dev_items, list):
                for d in dev_items:
                    if isinstance(d, dict):
                        devices.append(self.parse_device_item(d))

            controllers.append(
                MacUsbController(
                    name=ctrl_name,
                    host_controller=host_ctrl,
                    pci_device=pci_device,
                    pci_vendor=pci_vendor,
                    devices=devices,
                )
            )

        return controllers, warnings

    def detect_mock(self, mock_adapter: Optional[Any] = None) -> MacUsbReport:
        """Construct deterministic Apple Silicon USB and peripheral telemetry mock (INV-USB-06)."""
        keyboard = MacUsbDevice(
            name="Apple Internal Keyboard / Trackpad",
            vendor_id="0x05ac",
            product_id="0x027c",
            manufacturer="Apple Inc.",
            anonymized_serial_hash=self.anonymize_serial("MOCK-APPLE-KB-SERIAL-2026"),
            device_class=UsbDeviceClass.HUMAN_INTERFACE,
            speed=UsbSpeed.FULL_SPEED_12_MBPS,
            speed_text="up_to_12_mbit_s",
            location_id="0x01100000 / 1",
            bus_power_ma=500,
            current_used_ma=40,
            extra_current_ma=0,
            bcd_device="1.00",
            is_builtin=True,
            is_hub=False,
            children=[],
        )

        camera = MacUsbDevice(
            name="FaceTime HD Camera",
            vendor_id="0x05ac",
            product_id="0x8514",
            manufacturer="Apple Inc.",
            anonymized_serial_hash=self.anonymize_serial("MOCK-APPLE-CAM-SERIAL-2026"),
            device_class=UsbDeviceClass.AUDIO_VIDEO,
            speed=UsbSpeed.HIGH_SPEED_480_MBPS,
            speed_text="up_to_480_mbit_s",
            location_id="0x01200000 / 2",
            bus_power_ma=500,
            current_used_ma=200,
            extra_current_ma=0,
            bcd_device="2.01",
            is_builtin=True,
            is_hub=False,
            children=[],
        )

        controller = MacUsbController(
            name="USB 3.1 Bus",
            host_controller="AppleSynopsysUSB40XHCI",
            pci_device="0x0000",
            pci_vendor="0x106b",
            devices=[keyboard, camera],
        )

        all_devs = self.flatten_devices([keyboard, camera])
        has_ext = any(not d.is_builtin for d in all_devs)
        has_sec = any(d.device_class == UsbDeviceClass.SECURITY_TOKEN for d in all_devs)
        has_storage = any(d.device_class == UsbDeviceClass.MASS_STORAGE for d in all_devs)

        return MacUsbReport(
            controllers=[controller],
            total_controller_count=1,
            total_device_count=len(all_devs),
            has_external_devices=has_ext,
            has_security_tokens=has_sec,
            has_mass_storage=has_storage,
            collected_at_epoch_secs=time.time(),
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )

    def detect(
        self,
        use_mock: bool = False,
        mock_adapter: Optional[Any] = None,
    ) -> MacUsbReport:
        """Perform read-only query of macOS USB and peripheral inventory with unprivileged tools."""
        if use_mock:
            return self.detect_mock(mock_adapter)

        if platform.system() != "Darwin":
            logger.info("Non-Darwin platform detected; falling back to mock platform adapter")
            report = self.detect_mock(mock_adapter)
            return replace(
                report,
                collection_method="NON_DARWIN_MOCK_FALLBACK",
                unavailable_telemetry=["system_profiler SPUSBDataType requires Darwin macOS host"],
            )

        unavailable: List[str] = []
        warnings: List[str] = []

        try:
            cmd = ["/usr/sbin/system_profiler", "SPUSBDataType", "-json"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode != 0:
                warnings.append(f"system_profiler SPUSBDataType exited with code {proc.returncode}")
                return self.detect_mock(mock_adapter)

            data = json.loads(proc.stdout)
            controllers, parse_warnings = self.parse_spusb_json(data)
            warnings.extend(parse_warnings)

            all_devices: List[MacUsbDevice] = []
            for ctrl in controllers:
                all_devices.extend(self.flatten_devices(ctrl.devices))

            has_external = any(not d.is_builtin for d in all_devices)
            has_security = any(d.device_class == UsbDeviceClass.SECURITY_TOKEN for d in all_devices)
            has_storage = any(d.device_class == UsbDeviceClass.MASS_STORAGE for d in all_devices)

            return MacUsbReport(
                controllers=controllers,
                total_controller_count=len(controllers),
                total_device_count=len(all_devices),
                has_external_devices=has_external,
                has_security_tokens=has_security,
                has_mass_storage=has_storage,
                collected_at_epoch_secs=time.time(),
                collection_method="NATIVE_DARWIN_SYSTEM_PROFILER",
                unavailable_telemetry=unavailable,
                warnings=warnings,
            )

        except subprocess.TimeoutExpired:
            warnings.append("system_profiler SPUSBDataType query timed out after 10s")
            return self.detect_mock(mock_adapter)
        except Exception as exc:
            warnings.append(f"USB detection exception: {str(exc)}")
            return self.detect_mock(mock_adapter)
